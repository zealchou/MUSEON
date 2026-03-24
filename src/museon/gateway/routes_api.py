"""
API Routes — SkillHub + External Integration 端點

從 server.py 拆分出來的 API 端點註冊邏輯。
包含：_register_skillhub_endpoints、_register_external_endpoints。

原檔案：server.py（671 行）
"""

import logging

logger = logging.getLogger("museon.gateway.routes_api")


def _register_skillhub_endpoints(app) -> None:
    """註冊 SkillHub 相關 API 端點."""

    # -- 工作流 CRUD --

    @app.get("/api/workflows")
    async def list_workflows():
        """列出所有軟工作流."""
        try:
            store = app.state.workflow_store
            engine = app.state.workflow_engine
            workflows = store.list_all()
            result = []
            for wf in workflows:
                record = engine.get_workflow(wf.workflow_id)
                result.append({
                    **wf.to_dict(),
                    "total_runs": record.total_runs if record else 0,
                    "success_count": record.success_count if record else 0,
                    "avg_composite": record.avg_composite if record else 0,
                    "lifecycle": record.lifecycle if record else wf.lifecycle,
                })
            return {"workflows": result}
        except Exception as e:
            logger.error(f"list_workflows failed: {e}", exc_info=True)
            return {"workflows": [], "error": str(e)}

    @app.get("/api/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str):
        """工作流詳情 + 最近執行紀錄."""
        try:
            store = app.state.workflow_store
            engine = app.state.workflow_engine
            wf = store.load(workflow_id)
            record = engine.get_workflow(workflow_id)
            executions = engine.get_recent_executions(workflow_id, limit=10)
            return {
                "workflow": wf.to_dict() if wf else None,
                "record": record.to_dict() if record else None,
                "executions": [e.to_dict() for e in executions],
            }
        except Exception as e:
            logger.error(f"get_workflow failed: {e}", exc_info=True)
            return {"workflow": None, "error": str(e)}

    @app.post("/api/workflows")
    async def create_workflow(payload: Dict[str, Any] = Body(...)):
        """從對話草案建立工作流."""
        try:
            from museon.workflow.soft_workflow import create_soft_workflow
            from museon.core.event_bus import get_event_bus

            store = app.state.workflow_store
            engine = app.state.workflow_engine
            scheduler = app.state.workflow_scheduler

            wf = create_soft_workflow(
                name=payload.get("name", "未命名工作流"),
                description=payload.get("description", ""),
                steps=payload.get("steps", []),
                schedule=payload.get("schedule", {}),
                session_id=payload.get("session_id", ""),
                tags=payload.get("tags"),
            )

            # 儲存定義
            store.save(wf)

            # 同步到 WorkflowEngine SQLite
            engine.get_or_create(
                user_id="boss",
                name=wf.name,
                tags=wf.tags,
            )

            # 註冊排程
            if wf.schedule.schedule_type == "cron" and wf.schedule.cron_expression:
                try:
                    scheduler.register(wf.workflow_id)
                except Exception as sched_err:
                    logger.warning(f"Scheduler register failed: {sched_err}")

            # 發布事件
            get_event_bus().publish("WORKFLOW_CREATED", {
                "workflow_id": wf.workflow_id,
                "name": wf.name,
            })

            return {"success": True, "workflow": wf.to_dict()}
        except Exception as e:
            logger.error(f"create_workflow failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @app.post("/api/workflows/{workflow_id}/toggle")
    async def toggle_workflow(workflow_id: str, payload: Dict[str, Any] = Body(...)):
        """啟用/暫停排程."""
        try:
            scheduler = app.state.workflow_scheduler
            active = payload.get("active", True)
            scheduler.toggle(workflow_id, active)
            return {"success": True, "active": active}
        except Exception as e:
            logger.error(f"toggle_workflow failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @app.delete("/api/workflows/{workflow_id}")
    async def delete_workflow(workflow_id: str):
        """刪除工作流."""
        try:
            store = app.state.workflow_store
            scheduler = app.state.workflow_scheduler
            scheduler.unregister(workflow_id)
            deleted = store.delete(workflow_id)
            return {"success": deleted}
        except Exception as e:
            logger.error(f"delete_workflow failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @app.post("/api/workflows/{workflow_id}/run-now")
    async def run_workflow_now(workflow_id: str):
        """手動觸發執行."""
        try:
            scheduler = app.state.workflow_scheduler
            summary = await scheduler.trigger_now(workflow_id)
            return {
                "success": True,
                "summary": summary.to_dict() if summary else None,
            }
        except Exception as e:
            logger.error(f"run_workflow_now failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # -- 技能目錄 --

    @app.get("/api/skills/catalog")
    async def skills_catalog():
        """列出所有技能 + 元資料."""
        try:
            brain = _get_brain()
            raw = getattr(brain.skill_router, '_index', [])
            skills = [
                {
                    "skill_id": s.get("name", ""),
                    "name": s.get("name", ""),
                    "description": s.get("description", ""),
                    "lifecycle": s.get("lifecycle", "unknown"),
                    "origin": s.get("origin", "native"),
                    "always_on": s.get("always_on", False),
                    "emoji": s.get("emoji", ""),
                }
                for s in raw
            ]
            return {"skills": skills}
        except Exception as e:
            logger.error(f"skills_catalog failed: {e}", exc_info=True)
            return {"skills": [], "error": str(e)}

    # -- 儀表板對話 --

    @app.post("/api/dashboard/chat")
    async def dashboard_chat(payload: Dict[str, Any] = Body(...)):
        """獨立 session 的對話式助理."""
        content = payload.get("content", "").strip()
        if not content:
            return {"reply": "", "error": "content is required"}

        context = payload.get("context", "skill_builder")
        sid = payload.get("session_id") or f"dashboard_{context}_{int(datetime.now().timestamp())}"

        if not await session_manager.acquire(sid):
            return JSONResponse(
                status_code=202,
                content={"status": "queued", "session_id": sid},
            )

        try:
            brain = _get_brain()
            result = await brain.process(
                content=content,
                session_id=sid,
                user_id="boss",
                source="dashboard",
            )

            from museon.gateway.message import BrainResponse
            if isinstance(result, BrainResponse):
                return {
                    "reply": result.text,
                    "session_id": sid,
                    "artifacts": [a.to_dict() for a in result.artifacts] if result.artifacts else [],
                }
            return {
                "reply": str(result) if result else "",
                "session_id": sid,
                "artifacts": [],
            }
        except Exception as e:
            logger.error(f"dashboard_chat failed: {e}", exc_info=True)
            return {"reply": "", "session_id": sid, "error": str(e)}
        finally:
            await session_manager.release(sid)

    # -- 任務管理 --

    @app.get("/api/tasks")
    async def list_tasks():
        """列出使用者工作流任務 + 系統排程任務."""
        tasks = []

        # ── Part 1: WorkflowStore 使用者任務 ──
        try:
            store = app.state.workflow_store
            workflows = store.list_all()
            for wf in workflows:
                tasks.append({
                    "task_id": wf.workflow_id,
                    "name": wf.name,
                    "description": wf.description,
                    "schedule_type": wf.schedule.schedule_type,
                    "lifecycle": wf.lifecycle,
                    "active": wf.schedule.active,
                    "cron_expression": wf.schedule.cron_expression,
                    "created_at": wf.created_at,
                    "source": "workflow",
                })
        except Exception as e:
            logger.debug(f"list_tasks workflow part failed: {e}")

        # ── Part 2: 系統排程任務（CronEngine）──
        try:
            registry = getattr(app.state, "system_cron_registry", [])
            for meta in registry:
                job_id = meta["job_id"]
                # 從 CronEngine 讀取實際狀態
                job = cron_engine.get_job(job_id)
                next_run = None
                is_active = job is not None
                if job and hasattr(job, "next_run_time") and job.next_run_time:
                    next_run = job.next_run_time.isoformat()

                tasks.append({
                    "task_id": job_id,
                    "name": meta["name"],
                    "description": f"系統排程：{meta['schedule']}",
                    "schedule_type": "system",
                    "schedule_display": meta["schedule"],
                    "category": meta.get("category", "system"),
                    "uses_llm": meta.get("uses_llm", False),
                    "active": is_active,
                    "next_run": next_run,
                    "source": "system",
                })
        except Exception as e:
            logger.debug(f"list_tasks system part failed: {e}")

        return {"tasks": tasks}

    logger.info("SkillHub API endpoints registered")


# ═══════════════════════════════════════════════════════
# Phase 3-5: 外部整合 API 端點
# ═══════════════════════════════════════════════════════


def _register_external_endpoints(app, data_dir) -> None:
    """註冊 Phase 3-5 外部整合 API 端點."""

    # ── EXT-09: 推薦系統 ──
    @app.get("/api/recommendations")
    async def api_recommendations():
        """取得個人化推薦（使用 Brain 常駐 Recommender 實例）."""
        try:
            brain = app.state.brain
            if brain and brain._recommender:
                items = await brain._recommender.get_recommendations(limit=5)
                return {"recommendations": items, "count": len(items)}
            return {"recommendations": [], "count": 0, "status": "recommender_unavailable"}
        except Exception as e:
            return {"error": str(e), "recommendations": []}

    # ── EXT-15: 技能市場 ──
    @app.get("/api/market/skills")
    async def api_market_list():
        """列出技能市場."""
        try:
            from museon.federation.skill_market import SkillMarket

            market = SkillMarket(workspace=data_dir)
            skills = await market.list_marketplace()
            return {"skills": skills, "count": len(skills)}
        except Exception as e:
            return {"error": str(e), "skills": []}

    @app.post("/api/market/publish")
    async def api_market_publish(payload: Dict[str, Any] = {}):
        """發布技能到市場."""
        skill_id = payload.get("skill_id", "")
        if not skill_id:
            return {"error": "skill_id is required"}
        try:
            from museon.federation.skill_market import SkillMarket

            market = SkillMarket(workspace=data_dir)
            pkg = market.package_skill(skill_id)
            result = await market.publish_skill(
                package_path=pkg.get("path", ""),
                price=payload.get("price", 0.0),
                description=payload.get("description", ""),
            )
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/market/install")
    async def api_market_install(payload: Dict[str, Any] = {}):
        """安裝市場技能."""
        skill_id = payload.get("skill_id", "")
        if not skill_id:
            return {"error": "skill_id is required"}
        try:
            from museon.federation.skill_market import SkillMarket

            market = SkillMarket(workspace=data_dir)
            result = await market.install_skill(skill_id)
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── EXT-01: RSS ──
    @app.get("/api/rss/status")
    async def api_rss_status():
        """RSS 聚合器狀態."""
        try:
            from museon.tools.rss_aggregator import RSSAggregator

            agg = RSSAggregator()
            return {"available": True, "poll_interval": agg.POLL_INTERVAL}
        except Exception as e:
            return {"available": False, "error": str(e)}

    # ── EXT-05: 圖片生成 ──
    @app.post("/api/image/generate")
    async def api_image_generate(payload: Dict[str, Any] = {}):
        """生成圖片."""
        prompt = payload.get("prompt", "")
        if not prompt:
            return {"error": "prompt is required"}
        try:
            from museon.tools.image_gen import ImageGenerator
            from museon.core.event_bus import get_event_bus

            gen = ImageGenerator(
                event_bus=get_event_bus(),
                output_dir=str(data_dir / "generated_images"),
            )
            result = await gen.generate(
                prompt=prompt,
                width=payload.get("width", 1024),
                height=payload.get("height", 1024),
                style=payload.get("style", "photographic"),
            )
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── EXT-06: 語音合成 ──
    @app.post("/api/voice/synthesize")
    async def api_voice_synthesize(payload: Dict[str, Any] = {}):
        """語音合成."""
        text = payload.get("text", "")
        if not text:
            return {"error": "text is required"}
        try:
            from museon.tools.voice_clone import VoiceCloner
            from museon.core.event_bus import get_event_bus

            cloner = VoiceCloner(
                event_bus=get_event_bus(),
                output_dir=str(data_dir / "generated_voices"),
            )
            result = await cloner.synthesize(
                text=text,
                language=payload.get("language", "zh"),
            )
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── EXT-11: Zotero ──
    @app.get("/api/zotero/status")
    async def api_zotero_status():
        """Zotero 同步狀態."""
        try:
            from museon.tools.zotero_bridge import ZoteroBridge

            bridge = ZoteroBridge(workspace=data_dir)
            status = bridge.get_sync_status()
            return {"available": True, **status}
        except Exception as e:
            return {"available": False, "error": str(e)}

    @app.post("/api/zotero/search")
    async def api_zotero_search(payload: Dict[str, Any] = {}):
        """搜尋 Zotero 文獻."""
        query = payload.get("query", "")
        if not query:
            return {"error": "query is required", "results": []}
        try:
            from museon.tools.zotero_bridge import ZoteroBridge
            from museon.core.event_bus import get_event_bus

            bridge = ZoteroBridge(
                event_bus=get_event_bus(),
                workspace=data_dir,
            )
            results = await bridge.search_references(query, limit=payload.get("limit", 10))
            return {"results": results, "count": len(results)}
        except Exception as e:
            return {"error": str(e), "results": []}

    # ── EXT-10: 自動課程 ──
    @app.get("/api/courses")
    async def api_courses_list():
        """列出自動生成的課程."""
        try:
            from museon.nightly.course_generator import CourseGenerator

            gen = CourseGenerator(workspace=data_dir)
            courses = gen.list_courses()
            return {"courses": courses, "count": len(courses)}
        except Exception as e:
            return {"error": str(e), "courses": []}

    # ── EXT-12: 反饋迴圈 ──
    @app.get("/api/feedback/summary")
    async def api_feedback_summary():
        """使用者反饋摘要."""
        try:
            from museon.evolution.feedback_loop import FeedbackLoop
            from museon.core.event_bus import get_event_bus

            loop = FeedbackLoop(
                event_bus=get_event_bus(),
                workspace=data_dir,
            )
            return loop.get_daily_summary()
        except Exception as e:
            return {"error": str(e)}

    # ── EXT-03: Chrome Extension WebSocket ──
    from fastapi import WebSocket as _WebSocket, WebSocketDisconnect

    _extension_clients: list = []

    @app.websocket("/ws/extension")
    async def ws_extension(websocket: _WebSocket):
        """Chrome Extension WebSocket 端點 — 雙向通訊."""
        await websocket.accept()
        _extension_clients.append(websocket)
        logger.info(f"Chrome Extension connected (total: {len(_extension_clients)})")

        try:
            # 發送歡迎訊息
            await websocket.send_json({
                "type": "welcome",
                "message": "Connected to MUSEON Gateway",
                "version": "2.3.0",
            })

            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                    msg_type = data.get("type", "")

                    if msg_type == "extension_hello":
                        logger.info(f"Extension hello: v{data.get('version', '?')}")
                        await websocket.send_json({"type": "ack", "status": "connected"})

                    elif msg_type == "extension_capture":
                        # 記憶捕獲：選取文字 / 頁面擷取
                        try:
                            from museon.core.event_bus import get_event_bus, EXTENSION_CAPTURE
                            eb = get_event_bus()
                            eb.publish(EXTENSION_CAPTURE, {
                                "action": data.get("action", "remember"),
                                "text": data.get("text", ""),
                                "url": data.get("url", ""),
                                "title": data.get("title", ""),
                                "timestamp": data.get("timestamp", ""),
                            })
                        except Exception as e:
                            logger.debug(f"[SERVER] module import failed (degraded): {e}")

                        # 存入記憶
                        brain = _get_brain()
                        if brain and data.get("text"):
                            try:
                                brain.memory_store.store(
                                    content=data["text"],
                                    metadata={
                                        "source": "chrome_extension",
                                        "url": data.get("url", ""),
                                        "title": data.get("title", ""),
                                    },
                                )
                            except Exception as mem_err:
                                logger.debug(f"Extension capture store failed: {mem_err}")

                        await websocket.send_json({
                            "type": "notification",
                            "title": "MUSEON",
                            "message": "已記住！",
                        })

                    elif msg_type == "extension_command":
                        # 指令：問答 / 探索
                        try:
                            from museon.core.event_bus import get_event_bus, EXTENSION_COMMAND
                            eb = get_event_bus()
                            eb.publish(EXTENSION_COMMAND, {
                                "action": data.get("action", "ask"),
                                "query": data.get("query", ""),
                                "context": data.get("context", ""),
                                "timestamp": data.get("timestamp", ""),
                            })
                        except Exception as e:
                            logger.debug(f"[SERVER] module import failed (degraded): {e}")

                        # 用 Brain 處理
                        brain = _get_brain()
                        if brain and data.get("query"):
                            try:
                                result = await brain.think(
                                    query=data["query"],
                                    session_id="extension",
                                )
                                response_text = result.get("response", "（無回應）")
                                await websocket.send_json({
                                    "type": "notification",
                                    "title": "MUSEON",
                                    "message": response_text[:200],
                                })
                            except Exception as think_err:
                                logger.debug(f"Extension command think failed: {think_err}")
                                await websocket.send_json({
                                    "type": "notification",
                                    "title": "MUSEON",
                                    "message": f"處理中遇到問題: {str(think_err)[:100]}",
                                })

                    else:
                        logger.debug(f"Extension unknown msg type: {msg_type}")

                except json.JSONDecodeError:
                    logger.debug("Extension: invalid JSON received")
                except Exception as handler_err:
                    logger.debug(f"Extension handler error: {handler_err}")

        except WebSocketDisconnect as e:
            logger.debug(f"[SERVER] JSON failed (degraded): {e}")
        except Exception as ws_err:
            logger.debug(f"Extension WebSocket error: {ws_err}")
        finally:
            if websocket in _extension_clients:
                _extension_clients.remove(websocket)
            logger.info(f"Chrome Extension disconnected (remaining: {len(_extension_clients)})")

    # 儲存到 app.state 以便其他模組推送通知
    app.state.extension_clients = _extension_clients

    # ── EXT-13: Doctor Monitor WebSocket（3D 心智圖即時診斷）──

    _doctor_monitor_clients: list = []

    async def _broadcast_doctor_status():
        """推送最新 Doctor node-status 給所有 3D 心智圖客戶端."""
        if not _doctor_monitor_clients:
            return
        try:
            status = await doctor_node_status()
            _doctor_status_cache.update(status)
            msg = {"type": "doctor_status", "data": status}
            dead = []
            for client in _doctor_monitor_clients:
                try:
                    await client.send_json(msg)
                except Exception:
                    dead.append(client)
            for c in dead:
                if c in _doctor_monitor_clients:
                    _doctor_monitor_clients.remove(c)
        except Exception as bc_err:
            logger.debug(f"broadcast_doctor_status failed: {bc_err}")

    # 快取最後一次 doctor_node_status 結果，避免 WebSocket 連線時阻塞事件迴圈
    _doctor_status_cache: Dict[str, Any] = {}

    async def _refresh_doctor_cache():
        """背景刷新 Doctor 狀態快取."""
        try:
            _doctor_status_cache.update(await doctor_node_status())
        except Exception as e:
            logger.debug(f"Doctor cache refresh failed: {e}")

    @app.websocket("/ws/doctor-monitor")
    async def ws_doctor_monitor(websocket: _WebSocket):
        """3D 心智圖 Doctor 即時監控端點."""
        await websocket.accept()
        _doctor_monitor_clients.append(websocket)
        logger.info(f"Doctor Monitor connected (total: {len(_doctor_monitor_clients)})")

        try:
            # 連線時推送快取狀態（不阻塞），若無快取則觸發背景刷新
            if _doctor_status_cache:
                await websocket.send_json({"type": "doctor_status", "data": _doctor_status_cache})
            else:
                # 送一個佔位回應，然後背景刷新
                await websocket.send_json({"type": "doctor_status", "data": {
                    "timestamp": "", "overall": "unknown", "nodes": {}, "summary": {}
                }})
                import asyncio as _ws_aio
                _ws_aio.ensure_future(_refresh_and_push(websocket))

            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                    if data.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                    elif data.get("type") == "refresh":
                        try:
                            status = await doctor_node_status()
                            _doctor_status_cache.update(status)
                        except Exception:
                            status = _doctor_status_cache or {
                                "timestamp": "", "overall": "unknown", "nodes": {}, "summary": {}
                            }
                        await websocket.send_json({"type": "doctor_status", "data": status})
                except json.JSONDecodeError:
                    pass

        except WebSocketDisconnect:
            pass
        except Exception as ws_err:
            logger.warning(f"Doctor Monitor WebSocket error: {ws_err}")
        finally:
            if websocket in _doctor_monitor_clients:
                _doctor_monitor_clients.remove(websocket)
            logger.info(f"Doctor Monitor disconnected (remaining: {len(_doctor_monitor_clients)})")

    async def _refresh_and_push(ws: _WebSocket):
        """背景刷新 Doctor 狀態並推送給特定客戶端."""
        try:
            await _refresh_doctor_cache()
            if _doctor_status_cache:
                await ws.send_json({"type": "doctor_status", "data": _doctor_status_cache})
        except Exception as rp_err:
            logger.debug(f"Doctor _refresh_and_push failed: {rp_err}")

    app.state.doctor_monitor_clients = _doctor_monitor_clients
    app.state.broadcast_doctor_status = _broadcast_doctor_status

    logger.info("External integration endpoints registered (Phase 3-5, incl. /ws/extension, /ws/doctor-monitor)")



# ═══════════════════════════════════════════════════════
# CronEngine 系統排程（已拆分到 cron_registry.py）
# ═══════════════════════════════════════════════════════
