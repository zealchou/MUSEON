"""
Cron Registry — 系統排程任務註冊中心

從 server.py 拆分出來的 CronEngine 排程註冊邏輯。
包含所有 cron job 定義 + MuseWorker/Off/QA/Doc 自主維運 + 元資料清冊。

原檔案：server.py _register_system_cron_jobs()（1410 行）
"""

import asyncio
import json
import logging
from datetime import datetime

logger = logging.getLogger("museon.gateway.cron_registry")


def _register_system_cron_jobs(brain, app=None, cron_engine=None) -> None:
    """註冊系統級排程任務 — Layer 1.

    所有 job 的設計原則：
    - CPU 優先：能用本地計算就不呼叫 LLM
    - Token 極簡：只有 MemoryFusion 需要 LLM（用最便宜的 Haiku）
    - 每個 job 都有 try/except，單一 job 失敗不影響其他

    Args:
        brain: Brain 實例
        app: FastAPI app 實例（用於存取 app.state.telegram_adapter 等）
    """
    data_dir = brain.data_dir

    # ── Job 1: 夜間整合（每天 03:00）──
    async def _nightly_job():
        """NightlyJob + NightlyPipeline: 雙管線凌晨整合."""
        # Phase A: 18-step pipeline（純 CPU，零 LLM 除 Step 16）
        try:
            from museon.nightly.nightly_pipeline import NightlyPipeline, build_nightly_html
            from museon.core.event_bus import get_event_bus
            event_bus = get_event_bus()
            # WP-03: 注入 DendriticScorer 健康閘門
            _gov = getattr(app.state, "governor", None)
            _dendritic = getattr(_gov, "_dendritic", None) if _gov else None
            # Contract 3: 注入 memory_manager + heartbeat_focus
            _memory_manager = getattr(brain, "memory_manager", None) or getattr(brain, "_memory_manager", None)
            _heartbeat_focus = getattr(app.state, "heartbeat_focus", None)
            pipeline = NightlyPipeline(
                workspace=data_dir,
                memory_manager=_memory_manager,
                heartbeat_focus=_heartbeat_focus,
                event_bus=event_bus,
                brain=brain,
                dendritic_scorer=_dendritic,
            )
            pipeline_report = pipeline.run()
            logger.info(
                f"NightlyPipeline completed: "
                f"{pipeline_report['summary']['ok']}/{pipeline_report['summary']['total']} ok"
            )

            # 推播 HTML 摘要到 Telegram（3 次重試，5s/10s/20s 指數退避）
            try:
                adapter = getattr(app.state, "telegram_adapter", None)
                if adapter:
                    html = build_nightly_html(pipeline_report)
                    for retry in range(3):
                        try:
                            await adapter.push_notification(html)
                            logger.info("Nightly report pushed to Telegram")
                            break
                        except Exception as push_err:
                            wait = 5 * (2 ** retry)
                            logger.warning(f"Nightly push retry {retry+1}/3 (wait {wait}s): {push_err}")
                            await asyncio.sleep(wait)
            except Exception as notif_err:
                logger.warning(f"Nightly Telegram push failed: {notif_err}")
        except Exception as e:
            logger.error(f"NightlyPipeline failed: {e}", exc_info=True)

        # Phase B: 原有 NightlyJob（記憶融合 + Token 優化 + 鍛造檢查 + 健康報告）
        try:
            from museon.nightly.job import NightlyJob
            # 合約 4：注入 brain 的 llm_adapter + 存在性檢查
            _llm_client = getattr(brain, "_llm_adapter", None)
            if not _llm_client:
                logger.warning("NightlyJob: brain._llm_adapter 不存在，記憶融合/批次處理將跳過")
            job = NightlyJob(
                memory_store=brain.memory_store,
                llm_client=_llm_client,
                data_dir=data_dir,
            )
            result = await job.run()
            logger.info(f"NightlyJob completed: {result.get('status')}")
        except Exception as e:
            logger.error(f"NightlyJob failed: {e}", exc_info=True)

    cron_engine.add_job(
        _nightly_job, trigger="cron", job_id="nightly-fusion",
        hour=3, minute=0,
    )

    # ── Job 1.5: 早報推播（每天 07:30）──
    async def _morning_report():
        """讀取前晚報告 + LLM 生成自然語言摘要 → Telegram."""
        try:
            report_path = data_dir / "_system" / "state" / "nightly_report.json"
            if not report_path.exists():
                return

            report = json.loads(report_path.read_text(encoding="utf-8"))
            summary = report.get("summary", {})

            # 用 Brain 生成自然語言摘要
            ok = summary.get("ok", 0)
            total = summary.get("total", 0)
            errors = report.get("errors", [])
            elapsed = report.get("elapsed_seconds", 0)

            morning_text = (
                f"🌅 <b>霓裳晨報</b>\n\n"
                f"昨夜整合: {ok}/{total} 步驟完成 ({elapsed}s)\n"
            )
            if errors:
                morning_text += f"⚠️ {len(errors)} 個步驟需要關注\n"
                for e in errors[:3]:
                    morning_text += f"  · {e.get('step', '?')}\n"
            else:
                morning_text += "✅ 所有步驟正常運行\n"

            morning_text += "\n早安，達達把拔 ☀️"

            adapter = getattr(app.state, "telegram_adapter", None)
            if adapter:
                try:
                    await adapter.push_notification(morning_text)
                    logger.info("Morning report pushed to Telegram")
                except Exception as push_err:
                    logger.warning(f"Morning report push failed: {push_err}")
        except Exception as e:
            logger.error(f"Morning report failed: {e}", exc_info=True)

    cron_engine.add_job(
        _morning_report, trigger="cron", job_id="nightly-morning-report",
        hour=7, minute=30,
    )

    # ── Job 2: 健康心跳（每 30 分鐘）── 純 CPU
    async def _health_heartbeat():
        """健康檢查：Gateway + Brain + LLM 存活."""
        try:
            llm_status = "unchecked"
            # LLM 存活檢查（透過 VitalSigns probe）
            if brain and brain._governor:
                try:
                    vs = brain._governor.get_vital_signs()
                    if vs:
                        result = await vs._check_llm_alive()
                        llm_status = result.status.value  # pass/fail/skip
                except Exception as e:
                    llm_status = f"error: {e}"

            report = {
                "timestamp": datetime.now().isoformat(),
                "gateway": "alive",
                "brain": "alive" if brain else "dead",
                "llm": llm_status,
                "skills": brain.skill_router.get_skill_count() if brain else 0,
            }
            # 寫入心跳日誌（純 CPU 檔案 I/O）
            heartbeat_path = data_dir / "heartbeat.jsonl"
            import json as _json
            with open(heartbeat_path, "a", encoding="utf-8") as f:
                f.write(_json.dumps(report, ensure_ascii=False) + "\n")

            # 保持心跳日誌在合理大小（最多 1000 行）
            if heartbeat_path.stat().st_size > 200_000:
                lines = heartbeat_path.read_text(encoding="utf-8").splitlines()
                heartbeat_path.write_text(
                    "\n".join(lines[-500:]) + "\n", encoding="utf-8"
                )
        except Exception as e:
            logger.error(f"Health heartbeat failed: {e}", exc_info=True)

    cron_engine.add_job(
        _health_heartbeat, trigger="interval", job_id="health-heartbeat",
        minutes=30,
    )

    # ── Job 3: 記憶持久化確認（每 6 小時）── 純 CPU
    async def _memory_flush():
        """純 CPU: 確認記憶已持久化到磁碟."""
        try:
            brain._flush_skill_usage()
            logger.info("Memory flush completed (CPU-only)")
        except Exception as e:
            logger.error(f"Memory flush failed: {e}", exc_info=True)

    cron_engine.add_job(
        _memory_flush, trigger="interval", job_id="memory-flush",
        hours=6,
    )

    # ── Job 4: Skill 偵查掃描（每天 04:00）── CPU 過濾，LLM 評估
    async def _skill_acquisition_scan():
        """Skill Acquisition Pipeline: 偵測缺口 → 搜尋 → 過濾."""
        try:
            from museon.nightly.skill_scout import SkillScout
            scout = SkillScout(data_dir=str(data_dir))

            # CPU-only: 偵測能力缺口
            gaps = scout.detect_capability_gaps(
                quality_history={},  # TODO: 從 eval engine 載入
                usage_data={"unmatched_tasks": {}},  # TODO: 從使用日誌載入
                skill_names=[
                    s.get("name", "") for s in brain.skill_router._index
                ],
            )

            if gaps:
                logger.info(
                    f"SkillScout 偵測到 {len(gaps)} 個能力缺口"
                )
                # CPU-only: 搜尋 + 安全過濾
                for gap in gaps[:3]:
                    candidates = await scout.scan(gap, max_candidates=3)
                    if candidates:
                        logger.info(
                            f"找到 {len(candidates)} 個候選 Skill "
                            f"for gap: {gap.description[:50]}"
                        )
            else:
                logger.info("SkillScout: 無能力缺口")
        except Exception as e:
            logger.error(f"Skill acquisition scan failed: {e}", exc_info=True)

    cron_engine.add_job(
        _skill_acquisition_scan, trigger="cron", job_id="skill-acquisition-scan",
        hour=4, minute=0,
    )

    # ── Job 5: Guardian L1 巡檢（每 30 分鐘）── 純 CPU
    async def _guardian_l1():
        """Guardian L1: 基礎設施巡檢 — Gateway / Telegram / .env"""
        try:
            from museon.guardian.daemon import GuardianDaemon
            guardian = GuardianDaemon(data_dir=str(data_dir), brain=brain)
            result = await guardian.run_l1()
            failed = result.get("summary", {}).get("failed", 0)
            repaired = result.get("summary", {}).get("repaired", 0)
            if failed > 0 or repaired > 0:
                logger.warning(
                    f"Guardian L1: {failed} failed, {repaired} repaired"
                )
            else:
                logger.info("Guardian L1: all ok")
        except Exception as e:
            logger.error(f"Guardian L1 failed: {e}", exc_info=True)

    cron_engine.add_job(
        _guardian_l1, trigger="interval", job_id="guardian-l1",
        minutes=30,
    )

    # ── Job 6: Guardian L2+L3 深度巡檢（每 6 小時）── 純 CPU
    async def _guardian_deep():
        """Guardian L2+L3: 資料完整性 + 神經束連通性"""
        try:
            from museon.guardian.daemon import GuardianDaemon
            guardian = GuardianDaemon(data_dir=str(data_dir), brain=brain)
            l2 = await guardian.run_l2()
            l3 = await guardian.run_l3()
            l2_failed = l2.get("summary", {}).get("failed", 0)
            l3_failed = l3.get("summary", {}).get("failed", 0)
            if l2_failed > 0 or l3_failed > 0:
                logger.warning(
                    f"Guardian L2: {l2_failed} failed | "
                    f"L3: {l3_failed} failed"
                )
            else:
                logger.info("Guardian L2+L3: all ok")
        except Exception as e:
            logger.error(f"Guardian L2+L3 failed: {e}", exc_info=True)

    cron_engine.add_job(
        _guardian_deep, trigger="interval", job_id="guardian-deep",
        hours=6,
    )

    # ── Job 6.5: L5 程式碼健康檢查（每 6 小時）── CodeAnalyzer
    async def _guardian_l5():
        """L5: 程式碼靜態分析健康檢查（純 CPU，零 Token）."""
        try:
            if hasattr(brain, '_guardian') and brain._guardian:
                import asyncio
                result = await asyncio.to_thread(brain._guardian.run_l5)
                critical_count = len([
                    i for i in result.get("issues", [])
                    if i.get("severity") == "critical"
                ])
                if critical_count > 0:
                    logger.warning(
                        f"Guardian L5: {critical_count} 個 critical 問題"
                    )
                else:
                    logger.info(f"Guardian L5: {result.get('summary', 'OK')}")
        except Exception as e:
            logger.error(f"Guardian L5 failed: {e}", exc_info=True)

    cron_engine.add_job(
        _guardian_l5, trigger="interval", job_id="guardian-l5",
        hours=6,
    )

    # ── Job 7: 工具自動發現（每天 05:00）── SearXNG 搜尋
    async def _tool_discovery_scan():
        """每天 5am 搜尋新的免費自建 AI 工具."""
        try:
            from museon.tools.tool_registry import ToolRegistry
            from museon.tools.tool_discovery import ToolDiscovery

            registry = ToolRegistry(workspace=data_dir)
            # 先做健康檢查
            registry.check_all_health()

            # 檢查 SearXNG 是否啟用
            searxng_state = registry._states.get("searxng")
            if not searxng_state or not searxng_state.enabled:
                logger.info("Tool discovery skipped: SearXNG not enabled")
                return

            # 執行發現掃描
            discovery = ToolDiscovery(workspace=data_dir)
            result = discovery.discover()
            recommended = result.get("recommended", [])

            if recommended:
                logger.info(
                    f"Tool discovery found {len(recommended)} "
                    f"recommended tools"
                )
                # 推送通知到 Telegram
                adapter = getattr(app.state, "telegram_adapter", None)
                if adapter and recommended:
                    msg = "📡 <b>工具自動發現</b>\n\n"
                    for tool in recommended[:3]:
                        msg += (
                            f"• {tool.get('title', '?')} "
                            f"(評分: {tool.get('score', 0)}/10)\n"
                        )
                    msg += "\n在儀表板「工具庫」查看詳情"
                    try:
                        await adapter.push_notification(msg)
                    except Exception as push_err:
                        logger.warning(f"Tool discovery push failed: {push_err}")
            else:
                logger.info("Tool discovery: no new recommendations")
        except Exception as e:
            logger.error(f"Tool discovery scan failed: {e}", exc_info=True)

    cron_engine.add_job(
        _tool_discovery_scan, trigger="cron",
        job_id="tool-discovery-scan",
        hour=5, minute=0,
    )

    # ── Job 8: VITA 微脈 SysPulse（每 5 分鐘）── 純 CPU
    async def _vita_sys_pulse():
        """VITA SysPulse: 5 分鐘微脈 — 純 CPU 健康檢查."""
        try:
            if not app:
                return
            engine = getattr(app.state, "pulse_engine", None)
            if not engine:
                return
            await engine.sys_pulse()
        except Exception as e:
            logger.error(f"VITA SysPulse failed: {e}", exc_info=True)

    cron_engine.add_job(
        _vita_sys_pulse, trigger="interval", job_id="vita-sys-pulse",
        minutes=5,
    )

    # ── Job 9: VITA 息脈 BreathPulse（每 30 分鐘）── Haiku LLM
    async def _vita_breath_pulse():
        """VITA BreathPulse: 30 分鐘息脈 — 自適應自省."""
        try:
            if not app:
                return
            engine = getattr(app.state, "pulse_engine", None)
            if not engine:
                # Fallback to ProactiveBridge
                bridge = getattr(app.state, "proactive_bridge", None)
                if bridge:
                    result = await bridge.proactive_think()
                    action = result.get("reason", "?")
                    pushed = result.get("pushed", False)
                    if pushed:
                        logger.info(f"ProactiveBridge pushed: {action}")
                return
            result = await engine.breath_pulse()
            action = result.get("action", "?")
            if action == "pushed":
                logger.info(f"VITA BreathPulse pushed")
            else:
                logger.debug(f"VITA BreathPulse: {action}")
        except Exception as e:
            logger.error(f"VITA BreathPulse failed: {e}", exc_info=True)

    cron_engine.add_job(
        _vita_breath_pulse, trigger="interval", job_id="vita-breath-pulse",
        minutes=30,
    )

    # ── Job 10: VITA 晨感（每天 07:30）── 取代舊早報
    async def _vita_morning():
        """VITA 晨感: 07:30 晨安問候 — 取代舊的 morning_report."""
        try:
            if not app:
                return
            engine = getattr(app.state, "pulse_engine", None)
            if engine:
                result = await engine.trigger_morning()
                logger.info(f"VITA morning: {result.get('action', '?')}")
            else:
                # Fallback to old morning report logic
                await _morning_report()
        except Exception as e:
            logger.error(f"VITA morning failed: {e}", exc_info=True)

    # Replace old morning report with VITA morning
    try:
        cron_engine.remove_job("nightly-morning-report")
    except Exception as e:
        logger.debug(f"[SERVER] operation failed (degraded): {e}")
    cron_engine.add_job(
        _vita_morning, trigger="cron", job_id="vita-morning",
        hour=7, minute=30,
    )

    # ── Job 11: VITA 暮感（每天 22:00）──
    async def _vita_evening():
        """VITA 暮感: 22:00 晚間回顧."""
        try:
            if not app:
                return
            engine = getattr(app.state, "pulse_engine", None)
            if engine:
                result = await engine.trigger_evening()
                logger.info(f"VITA evening: {result.get('action', '?')}")
        except Exception as e:
            logger.error(f"VITA evening failed: {e}", exc_info=True)

    cron_engine.add_job(
        _vita_evening, trigger="cron", job_id="vita-evening",
        hour=22, minute=0,
    )

    # ── Job 11.5: VITA 自主探索（每 2h：07:10 ~ 21:10，共 8 次）──
    # 觸發類型輪替：morning → curiosity → mission → skill → world → self → curiosity → mission
    _EXPLORE_TRIGGERS = ["morning", "curiosity", "mission", "skill", "world", "self", "curiosity", "mission"]

    async def _vita_exploration_auto():
        """VITA SoulPulse: 每 2h 自主探索 + Telegram 回報 + 自動鍛造."""
        try:
            if not app:
                return
            engine = getattr(app.state, "pulse_engine", None)
            if not engine:
                return

            # 根據當日已執行次數輪替 trigger
            _pdb = getattr(app.state, "pulse_db", None)
            today_count = _pdb.get_today_exploration_count() if _pdb else 0
            trigger = _EXPLORE_TRIGGERS[today_count % len(_EXPLORE_TRIGGERS)]

            result = await engine.soul_pulse(trigger=trigger)
            action = result.get("action", "?")
            percrl = result.get("percrl", {})
            explored = percrl.get("explore", "skipped")
            crystallized = percrl.get("crystallize", "skipped")
            logger.info(
                f"VITA auto-explore #{today_count + 1} ({trigger}): "
                f"explore={explored}, crystallize={crystallized}"
            )

            # ── Telegram 回報（直接從 result 取探索資料，不依賴 DB 回讀）──
            adapter = getattr(app.state, "telegram_adapter", None)
            if adapter and explored != "skipped":
                _status = "✅" if explored == "done" else f"⚠️ {explored}"
                _crystal = "💎 已結晶" if crystallized == "done" else "📝 未結晶"
                _trigger_zh = {
                    "curiosity": "好奇心驅動",
                    "world": "世界脈動",
                    "skill": "技能精進",
                    "self": "自我反思",
                    "mission": "使命探索",
                    "morning": "晨間巡禮",
                    "idle": "閒置時自主探索",
                }.get(trigger, trigger)

                # 優先從 result["exploration"] 取資料（pulse_engine 直接掛上的）
                _exp_data = result.get("exploration", {})
                _explore_topic = _exp_data.get("topic", "")
                _findings = _exp_data.get("findings", "")
                _topic_line = f"📌 主題：{_explore_topic}\n" if _explore_topic else ""

                # 建構 findings 摘要（過濾無價值結果）
                _findings_preview = ""
                _NO_VALUE_TAGS = ("搜尋無結果", "無價值發現", "探索失敗")
                if _findings and not any(t in _findings for t in _NO_VALUE_TAGS) and len(_findings) > 20:
                    _findings_preview = f"\n📋 主要發現：\n{_findings[:1200]}\n"

                _msg = (
                    f"🔭 【自主探索 #{today_count + 1}】\n\n"
                    f"動機：{_trigger_zh}\n"
                    f"{_topic_line}"
                    f"探索：{_status}\n"
                    f"結晶：{_crystal}\n"
                    f"行動：{action}"
                    f"{_findings_preview}\n\n"
                    f"有什麼想聊的嗎？"
                )
                try:
                    await adapter.push_notification(_msg)
                except Exception as e:
                    logger.debug(f"Exploration Telegram notify failed: {e}")

                # 生成 HTML 報告附件（使用 result 資料，不依賴 DB）
                if _exp_data and _findings and not any(t in _findings for t in _NO_VALUE_TAGS):
                    try:
                        from museon.pulse.exploration_report import generate_html_report
                        _reports_dir = Path(brain.data_dir) / "_system" / "reports"
                        _reports_dir.mkdir(parents=True, exist_ok=True)
                        _report_path = generate_html_report(_exp_data, _reports_dir)
                        _owner_id = int(adapter.trusted_user_ids[0])
                        await adapter.send_document(
                            _owner_id, str(_report_path), caption="📄 完整探索報告"
                        )
                    except Exception as _re:
                        logger.warning(f"Exploration report send failed: {_re}")

            # ── 探索後自動觸發技能鍛造 ──
            if crystallized == "done" or explored == "done":
                try:
                    from museon.nightly.skill_forge_scout import SkillForgeScout
                    scout = SkillForgeScout(
                        brain=getattr(app.state, "brain", None),
                        event_bus=getattr(app.state, "event_bus", None),
                        workspace=getattr(getattr(app.state, "brain", None), "data_dir", None),
                        pulse_db=_pdb,
                        searxng_url="http://127.0.0.1:8888",
                    )
                    forge_results = await scout.process_queue(max_items=2)
                    forged = sum(1 for r in forge_results if r.get("status") == "done")
                    if forged > 0:
                        logger.info(f"SkillForgeScout: auto-forged {forged} drafts after exploration")
                        if adapter:
                            _forge_msg = (
                                f"🔨 【技能鍛造】探索後自動鍛造\n\n"
                                f"產出 {forged} 份草稿，已提交 Morphenix 審核流程。"
                            )
                            try:
                                await adapter.push_notification(_forge_msg)
                            except Exception as e:
                                logger.debug(f"[SERVER] operation failed (degraded): {e}")
                except Exception as e:
                    logger.debug(f"Auto skill forge after exploration failed: {e}")

        except Exception as e:
            logger.error(f"VITA auto-explore failed: {e}", exc_info=True)

    cron_engine.add_job(
        _vita_exploration_auto, trigger="cron", job_id="vita-explore-auto",
        hour="7,9,11,13,15,17,19,21", minute=10,
    )

    # ── Job 12: Morphenix 72hr 自動批准（每 6 小時檢查）──
    async def _morphenix_auto_approve():
        """72 小時未處理的 L3 提案自動批准."""
        try:
            db = getattr(app.state, "pulse_db", None)
            if not db:
                return
            approved = db.auto_approve_stale_proposals(hours=72)
            if approved:
                logger.info(f"Morphenix auto-approved {len(approved)} stale proposals: {approved}")
                # 發布 MORPHENIX_AUTO_APPROVED 事件
                _ebus = getattr(app.state, "event_bus", None)
                if _ebus:
                    from museon.core.event_bus import MORPHENIX_AUTO_APPROVED
                    _ebus.publish(MORPHENIX_AUTO_APPROVED, {
                        "proposal_ids": approved,
                        "count": len(approved),
                    })
                # 通知 Telegram
                adapter = getattr(app.state, "telegram_adapter", None)
                if adapter:
                    msg = (
                        f"⏰ 【Morphenix 自動批准】\n\n"
                        f"{len(approved)} 個提案超過 72 小時未處理，已自動批准：\n"
                    )
                    for pid in approved:
                        msg += f"  · {pid}\n"
                    msg += "\n霓裳將在下次整合時執行這些演化。"
                    try:
                        await adapter.push_notification(msg)
                    except Exception as push_err:
                        logger.warning(f"Morphenix auto-approve push failed: {push_err}")
        except Exception as e:
            logger.error(f"Morphenix auto-approve failed: {e}", exc_info=True)

    cron_engine.add_job(
        _morphenix_auto_approve, trigger="interval",
        job_id="morphenix-auto-approve",
        hours=6,
    )

    # ── 承諾到期檢查（每 15 分鐘）──
    async def _commitment_periodic_check():
        """定期檢查承諾到期狀態，逾期時透過 ProactiveBridge 推送."""
        try:
            from museon.pulse.commitment_tracker import CommitmentTracker
            from museon.pulse.pulse_db import get_pulse_db

            _pdb = get_pulse_db(data_dir)
            tracker = CommitmentTracker(pulse_db=_pdb)

            result = tracker.periodic_check()
            if result.get("overdue_count", 0) > 0:
                logger.warning(
                    f"[Commitment] 逾期承諾: {result['overdue_count']} 筆 "
                    f"({result['overdue_ids'][:3]})"
                )
                # 透過 Telegram adapter 主動推送逾期提醒
                _tg_adapter = getattr(app, "state", None) and getattr(app.state, "telegram_adapter", None) if app else None
                if _tg_adapter and hasattr(_tg_adapter, "push_notification"):
                    overdue = tracker.get_overdue_commitments()
                    if overdue:
                        msg = "⚠️ 承諾提醒：\n"
                        for c in overdue[:3]:
                            msg += f"- {c.get('promise_text', '?')[:60]}\n"
                        msg += "\n（霓裳正在處理中，請稍候）"
                        try:
                            await _tg_adapter.push_notification(msg)
                        except Exception as push_err:
                            logger.warning(f"Commitment push failed: {push_err}")

                # ANIMA zhen -1 for overdue
                try:
                    for _oid in result.get("overdue_ids", [])[:3]:
                        _pdb.log_anima_change(
                            element="zhen", delta=-1,
                            reason=f"承諾逾期: {_oid}",
                            absolute_after=0,
                        )
                except Exception as e:
                    logger.debug(f"[SERVER] operation failed (degraded): {e}")

        except Exception as e:
            logger.error(f"Commitment periodic check failed: {e}", exc_info=True)

    cron_engine.add_job(
        _commitment_periodic_check, trigger="interval",
        job_id="commitment-check",
        minutes=15,
    )

    # ── Job: 念感 — 使用者閒置偵測（每 60 分鐘）──
    IDLE_CHECK_THRESHOLD_HOURS = 3.0  # 閒置超過 3 小時觸發念感

    async def _vita_idle_check():
        """念感: 檢查使用者閒置時間，超過閾值觸發 trigger_idle."""
        try:
            if not app:
                return
            engine = getattr(app.state, "pulse_engine", None)
            hf = getattr(app.state, "heartbeat_focus", None)
            if not engine or not hf:
                return
            # 從 HeartbeatFocus._interactions 計算最後互動時間
            interactions = getattr(hf, "_interactions", [])
            if not interactions:
                return  # 沒有任何互動記錄，跳過
            import time as _time
            last_interaction = max(interactions)
            idle_hours = (_time.time() - last_interaction) / 3600
            if idle_hours >= IDLE_CHECK_THRESHOLD_HOURS:
                result = await engine.trigger_idle(idle_hours)
                logger.info(f"念感 idle check: idle={idle_hours:.1f}h → {result.get('action', '?')}")
        except Exception as e:
            logger.error(f"念感 idle check failed: {e}", exc_info=True)

    cron_engine.add_job(
        _vita_idle_check, trigger="interval",
        job_id="vita-idle-check",
        minutes=60,
    )

    # ── Job: 自由探索 — 閒置 20 分鐘自動啟動（每 5 分鐘檢查）──
    FREE_EXPLORE_IDLE_MINUTES = 20      # 閒置門檻（分鐘）
    FREE_EXPLORE_COOLDOWN_MINUTES = 30  # 兩次自由探索最短間隔（分鐘）
    _FREE_EXPLORE_TRIGGERS = ["curiosity", "world", "skill", "self", "mission"]
    _last_free_explore: dict = {"ts": 0.0, "count": 0}

    async def _vita_free_explore_on_idle():
        """閒置 20 分鐘 → 自主自由探索（不打擾使用者，探索完再報告）."""
        try:
            if not app:
                return
            engine = getattr(app.state, "pulse_engine", None)
            hf = getattr(app.state, "heartbeat_focus", None)
            if not engine or not hf:
                return

            import time as _time
            now_ts = _time.time()

            # 1. 確認使用者真的閒置 > 20 分鐘
            interactions = getattr(hf, "_interactions", [])
            if not interactions:
                return
            last_interaction = max(interactions)
            idle_minutes = (now_ts - last_interaction) / 60
            if idle_minutes < FREE_EXPLORE_IDLE_MINUTES:
                return

            # 2. 確認距離上次自由探索 > 30 分鐘（避免連續觸發）
            since_last = (now_ts - _last_free_explore["ts"]) / 60
            if since_last < FREE_EXPLORE_COOLDOWN_MINUTES:
                return

            # 3. 確認今日自由探索次數未超上限
            _pdb = getattr(app.state, "pulse_db", None)
            today_count = _pdb.get_today_exploration_count() if _pdb else 0
            from museon.pulse.pulse_engine import EXPLORATION_DAILY_LIMIT
            if today_count >= EXPLORATION_DAILY_LIMIT:
                return

            # 4. 選擇觸發類型（輪替）
            trigger = _FREE_EXPLORE_TRIGGERS[_last_free_explore["count"] % len(_FREE_EXPLORE_TRIGGERS)]
            _last_free_explore["ts"] = now_ts
            _last_free_explore["count"] += 1

            logger.info(
                f"自由探索啟動: idle={idle_minutes:.0f}min, trigger={trigger}, "
                f"count=#{_last_free_explore['count']}"
            )

            result = await engine.soul_pulse(trigger=trigger)
            percrl = result.get("percrl", {})
            explored = percrl.get("explore", "skipped")
            crystallized = percrl.get("crystallize", "skipped")

            logger.info(
                f"自由探索完成 #{_last_free_explore['count']} ({trigger}): "
                f"explore={explored}, crystallize={crystallized}"
            )

            # 5. 探索有結果 → 主動傳給使用者（直接從 result 取資料，不依賴 DB 回讀）
            adapter = getattr(app.state, "telegram_adapter", None)
            if adapter and explored != "skipped":
                # 優先從 result["exploration"] 取資料
                _exp_data = result.get("exploration", {})
                explore_topic = _exp_data.get("topic", "")
                _findings = _exp_data.get("findings", "")

                # 建構 findings 摘要（過濾無價值結果）
                findings_preview = ""
                _NO_VALUE_TAGS = ("搜尋無結果", "無價值發現", "探索失敗")
                if _findings and not any(t in _findings for t in _NO_VALUE_TAGS) and len(_findings) > 20:
                    findings_preview = f"\n\n📋 主要發現：\n{_findings[:1200]}"

                topic_line = f"📌 主題：{explore_topic}\n" if explore_topic else ""
                _crystal_tag = "\n💎 已結晶為長期記憶" if crystallized == "done" else ""
                _msg = (
                    f"🔭 【自由探索回報】\n\n"
                    f"你不在的這 {idle_minutes:.0f} 分鐘，我出去探索了。\n"
                    f"{topic_line}"
                    f"{findings_preview}"
                    f"{_crystal_tag}\n\n"
                    f"有什麼想聊的嗎？"
                ).strip()
                try:
                    await adapter.push_notification(_msg)
                except Exception as _e:
                    logger.debug(f"Free explore notify failed: {_e}")

                # 生成 HTML 報告附件（使用 result 資料，不依賴 DB）
                if _exp_data and _findings and not any(t in _findings for t in _NO_VALUE_TAGS):
                    try:
                        from museon.pulse.exploration_report import generate_html_report
                        _reports_dir = Path(brain.data_dir) / "_system" / "reports"
                        _reports_dir.mkdir(parents=True, exist_ok=True)
                        _report_path = generate_html_report(_exp_data, _reports_dir)
                        _owner_id = int(adapter.trusted_user_ids[0])
                        await adapter.send_document(
                            _owner_id, str(_report_path), caption="📄 完整探索報告"
                        )
                    except Exception as _re:
                        logger.warning(f"Free explore report send failed: {_re}")

        except Exception as e:
            logger.error(f"自由探索 idle job failed: {e}", exc_info=True)

    cron_engine.add_job(
        _vita_free_explore_on_idle, trigger="interval",
        job_id="vita-free-explore-idle",
        minutes=5,
        timeout=300,  # 5 分鐘超時（探索需要時間）
    )

    # ── Job: Companion Watchdog — 看門狗（每 60 分鐘）──
    async def _companion_watchdog():
        """看門狗: 超過 3 小時沒成功推送 → 強制觸發 companion 模式."""
        try:
            if not app:
                return
            bridge = getattr(app.state, "proactive_bridge", None)
            if not bridge:
                return
            result = bridge.watchdog_check()
            if result.get("status") == "alert":
                logger.warning(
                    f"Companion Watchdog 警報: {result.get('hours_silent', '?')}h 無推送 "
                    "→ 強制觸發 companion 模式"
                )
                # 直接在 CronEngine 的 async context 中呼叫 proactive_think
                # 不經 HeartbeatEngine daemon thread，避免跨線程問題
                import asyncio as _asyncio
                try:
                    think_result = await _asyncio.wait_for(
                        bridge.proactive_think(mode="companion"), timeout=60
                    )
                    logger.info(f"Watchdog companion think: {think_result}")
                except _asyncio.TimeoutError:
                    logger.warning("Watchdog companion think 超時 (60s)")
                except Exception as think_err:
                    logger.error(f"Watchdog companion think failed: {think_err}", exc_info=True)
        except Exception as e:
            logger.error(f"Companion watchdog failed: {e}", exc_info=True)

    cron_engine.add_job(
        _companion_watchdog, trigger="interval",
        job_id="companion-watchdog",
        minutes=60,
    )

    # ── Job: Dendritic Health Score tick（每 5 分鐘）──
    async def _dendritic_tick():
        """DendriticScorer 定期 tick — 記錄 Health Score 到 PulseDB."""
        try:
            _gov = getattr(app.state, "governor", None)
            if not _gov or not _gov._dendritic:
                return
            status = _gov._dendritic.tick()
            # 記錄到 PulseDB
            _pdb = getattr(app.state, "pulse_db", None)
            if _pdb:
                _pdb.log_health_score(
                    score=status.get("score", 100),
                    tier=status.get("tier", 0),
                    event_count=status.get("event_count", 0),
                    incident_count=status.get("recent_incidents", 0),
                )
        except Exception as e:
            logger.debug(f"Dendritic tick cron failed: {e}")

    cron_engine.add_job(
        _dendritic_tick, trigger="interval",
        job_id="dendritic-tick",
        minutes=5,
    )

    # ── Job: ExplorationBridge 凌晨批次路由（每天 03:30）──
    async def _exploration_bridge_batch():
        """凌晨批次處理探索路由摘要."""
        try:
            bridge = getattr(app.state, "exploration_bridge", None)
            if bridge:
                from museon.core.event_bus import NIGHTLY_COMPLETED
                bridge._on_nightly_complete({"batch": True})
                logger.info("ExplorationBridge batch route completed")
        except Exception as e:
            logger.debug(f"ExplorationBridge batch failed: {e}")

    cron_engine.add_job(
        _exploration_bridge_batch, trigger="cron",
        job_id="exploration-bridge-batch",
        hour=3, minute=30,
    )

    # ── Job: Curiosity Research（每天 10:00）──
    async def _curiosity_research_job():
        """好奇問題研究 — 從佇列取 2 個問題用 ResearchEngine 研究."""
        try:
            from museon.nightly.curiosity_router import CuriosityRouter
            from museon.research.research_engine import ResearchEngine
            from museon.core.event_bus import get_event_bus

            _eb = get_event_bus()
            research_engine = ResearchEngine(
                brain=brain,
                searxng_url="http://127.0.0.1:8888",
            )
            _pdb = getattr(app.state, "pulse_db", None)
            router = CuriosityRouter(
                research_engine=research_engine,
                event_bus=_eb,
                workspace=data_dir,
                pulse_db=_pdb,
            )
            results = await router.process_queue(max_items=2)
            valuable = sum(1 for r in results if r.get("is_valuable"))
            logger.info(
                f"CuriosityRouter: researched {len(results)}, "
                f"valuable {valuable}"
            )
        except Exception as e:
            logger.error(f"Curiosity research cron failed: {e}", exc_info=True)

    cron_engine.add_job(
        _curiosity_research_job, trigger="cron",
        job_id="curiosity-research",
        hour=10, minute=0,
    )

    # ── Job: Immune Research（每 2 小時）──
    async def _immune_research_job():
        """免疫研究 — 處理 Tier 2 incidents 的待研究佇列."""
        try:
            ir = getattr(app.state, "immune_research", None)
            if not ir:
                return
            results = await ir.process_queue(max_items=2)
            done = sum(1 for r in results if r.status == "done")
            if results:
                logger.info(
                    f"ImmuneResearch: processed {len(results)}, "
                    f"done {done}"
                )
        except Exception as e:
            logger.debug(f"Immune research cron failed: {e}")

    cron_engine.add_job(
        _immune_research_job, trigger="interval",
        job_id="immune-research",
        hours=2,
    )

    # ── WP-07: Tool Health Check (5min) — 含自癒 + 升級 + 自動停用機制 ──
    _tool_fail_counts: dict = {}
    _tool_disabled: dict = {}     # {name: disabled_at_ts}
    _TOOL_RESTART_THRESHOLD = 3   # 連續 3 次失敗 → 自動重啟
    _TOOL_ESCALATE_THRESHOLD = 6  # 連續 6 次失敗 → 升級通知 + 自動停用
    _TOOL_REPROBE_INTERVAL = 600  # 停用後每 10 分鐘嘗試恢復

    async def _tool_health_check_job():
        """定期檢查所有工具健康狀態，偵測降級/恢復.

        自癒邏輯：
          - 連續 N 次失敗 → 嘗試 toggle off/on 重啟
          - 連續 2N 次失敗 → 透過 Telegram 通知使用者介入
          - 恢復時重置計數器並記錄
        """
        try:
            import asyncio as _aio
            from museon.core.event_bus import get_event_bus
            from museon.tools.tool_registry import ToolRegistry

            brain = _get_brain()
            event_bus = get_event_bus()
            registry = ToolRegistry(
                workspace=brain.data_dir,
                event_bus=event_bus,
            )
            results = registry.check_all_health()
            degraded = []

            for name, result in results.items():
                # 跳過已停用或未安裝的工具 — 不計入失敗
                _tool_reason = result.get("reason", "")
                if _tool_reason in ("disabled", "not_running", "not_installed"):
                    continue
                # 跳過已被自動停用的工具（由 re-probe 負責恢復）
                if name in _tool_disabled:
                    continue
                if not result.get("healthy", True):
                    _tool_fail_counts[name] = _tool_fail_counts.get(name, 0) + 1
                    count = _tool_fail_counts[name]
                    degraded.append(name)

                    # 自動重啟（每 N 次嘗試一次）
                    if count == _TOOL_RESTART_THRESHOLD:
                        logger.warning(
                            f"Tool {name}: {count} consecutive failures, "
                            f"attempting auto-restart"
                        )
                        try:
                            registry.toggle_tool(name, False)
                            await _aio.sleep(3)
                            registry.toggle_tool(name, True)
                            logger.info(f"Tool {name}: auto-restart triggered")
                        except Exception as e:
                            logger.warning(f"Tool {name}: auto-restart failed: {e}")

                    # 升級通知 + 自動停用
                    elif count == _TOOL_ESCALATE_THRESHOLD:
                        logger.error(
                            f"Tool {name}: {count} consecutive failures, "
                            f"disabling and escalating"
                        )
                        # 自動停用
                        import time as _t_time
                        _tool_disabled[name] = _t_time.time()
                        try:
                            registry.toggle_tool(name, False)
                        except Exception as e:
                            logger.debug(f"[SERVER] tool failed (degraded): {e}")
                        # 通知
                        _tg = getattr(app, "state", None) and getattr(app.state, "telegram_adapter", None) if app else None
                        if _tg and hasattr(_tg, "push_notification"):
                            try:
                                await _tg.push_notification(
                                    f"⚠️ 工具 {name} 連續 {count} 次健康檢查失敗，"
                                    f"已自動停用。每 30 分鐘嘗試恢復。"
                                )
                            except Exception as e:
                                logger.debug(f"[SERVER] operation failed (degraded): {e}")
                else:
                    # 恢復 — 重置計數器
                    prev = _tool_fail_counts.get(name, 0)
                    if prev > 0:
                        logger.info(
                            f"Tool {name}: recovered after {prev} failures ✓"
                        )
                        # 若之前被停用，重新啟用
                        if name in _tool_disabled:
                            del _tool_disabled[name]
                            try:
                                registry.toggle_tool(name, True)
                                logger.info(f"Tool {name}: re-enabled after recovery")
                            except Exception as e:
                                logger.debug(f"[SERVER] tool failed (degraded): {e}")
                    _tool_fail_counts[name] = 0

            # 已停用工具的定期 re-probe
            import time as _t_time2
            _now_ts = _t_time2.time()
            for disabled_name, disabled_at in list(_tool_disabled.items()):
                if _now_ts - disabled_at >= _TOOL_REPROBE_INTERVAL:
                    logger.info(f"Tool {disabled_name}: re-probing disabled tool")
                    try:
                        registry.toggle_tool(disabled_name, True)
                        await _aio.sleep(3)
                        probe = registry.check_health(disabled_name)
                        if probe and probe.get("healthy"):
                            logger.info(f"Tool {disabled_name}: re-probe succeeded, re-enabled ✓")
                            del _tool_disabled[disabled_name]
                            _tool_fail_counts[disabled_name] = 0
                        else:
                            registry.toggle_tool(disabled_name, False)
                            _tool_disabled[disabled_name] = _now_ts  # 重置 reprobe 計時
                    except Exception as rp_err:
                        logger.debug(f"Tool {disabled_name} re-probe failed: {rp_err}")

            if degraded:
                fail_info = {n: _tool_fail_counts.get(n, 0) for n in degraded}
                logger.warning(f"Tool health check: degraded={fail_info}")
        except Exception as e:
            logger.debug(f"Tool health check cron failed: {e}")

    cron_engine.add_job(
        _tool_health_check_job, trigger="interval",
        job_id="tool-health-check",
        minutes=5,
    )

    # ── 狀態熵清理（每小時）— 防止計數器/cache/session 無限膨脹 ──
    async def _stale_state_cleanup_job():
        """每小時清理過期的暫存狀態."""
        try:
            # 1. 清理 _tool_fail_counts 中已歸零的條目
            stale = [k for k, v in _tool_fail_counts.items() if v == 0]
            for k in stale:
                del _tool_fail_counts[k]
            # 2. 清理過期 session locks
            if session_manager and hasattr(session_manager, 'cleanup_stale'):
                await session_manager.cleanup_stale()
            if stale:
                logger.debug(f"Stale state cleanup: removed {len(stale)} zero counters")
        except Exception as e:
            logger.debug(f"Stale state cleanup failed: {e}")

    cron_engine.add_job(
        _stale_state_cleanup_job, trigger="interval",
        job_id="stale-state-cleanup",
        hours=1,
    )

    # ── WP-04: System Audit Periodic (每天 02:30) ──
    async def _system_audit_periodic():
        """每日定期系統審計 — 發布 AUDIT_COMPLETED + AUDIT_TREND_UPDATED."""
        try:
            from museon.doctor.system_audit import SystemAuditor
            from museon.core.event_bus import get_event_bus

            auditor = SystemAuditor(
                museon_home=str(data_dir),
                event_bus=get_event_bus(),
            )
            report = auditor.run_full_audit()
            logger.info(
                f"System audit periodic: overall={report.overall.value}, "
                f"passed={report.summary.get('ok', 0)}, "
                f"warned={report.summary.get('warning', 0)}, "
                f"failed={report.summary.get('critical', 0)}"
            )
            # 審計完成 → 即時推送給 3D 心智圖
            try:
                if hasattr(app.state, "broadcast_doctor_status"):
                    await app.state.broadcast_doctor_status()
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"System audit periodic cron failed: {e}")

    cron_engine.add_job(
        _system_audit_periodic, trigger="cron",
        job_id="system-audit-periodic",
        hour=2, minute=30,
    )

    # ── EXT-01: RSS Poll (60min) ──
    # 預檢 aiohttp 可用性，缺少時跳過註冊
    import importlib.util as _imp_util
    _has_aiohttp = _imp_util.find_spec("aiohttp") is not None
    if not _has_aiohttp:
        logger.warning("RSS poll cron 跳過註冊：aiohttp 未安裝")
    else:
        async def _rss_poll_job():
            """定期拉取 RSS 新文章."""
            try:
                from museon.tools.rss_aggregator import RSSAggregator
                from museon.core.event_bus import get_event_bus

                brain = _get_brain()
                aggregator = RSSAggregator(
                    event_bus=get_event_bus(),
                    brain=brain,
                )
                items = await aggregator.poll_new_items()
                if items:
                    logger.info(f"RSS poll: {len(items)} new items")
            except Exception as e:
                logger.debug(f"RSS poll cron failed: {e}")

        cron_engine.add_job(
            _rss_poll_job, trigger="interval",
            job_id="rss-poll",
            minutes=60,
        )

    # ── EXT-07: Dify Schedule Sync (15min) ──
    async def _dify_schedule_sync():
        """同步 Dify 排程，觸發到期工作流."""
        try:
            from museon.tools.dify_scheduler import DifyScheduler
            from museon.core.event_bus import get_event_bus

            scheduler = DifyScheduler(event_bus=get_event_bus())
            result = await scheduler.sync_schedules()
            triggered = result.get("triggered", 0)
            if triggered:
                logger.info(f"Dify sync: triggered {triggered} workflows")
        except Exception as e:
            logger.debug(f"Dify schedule sync cron failed: {e}")

    cron_engine.add_job(
        _dify_schedule_sync, trigger="interval",
        job_id="dify-schedule-sync",
        minutes=15,
    )

    # ── EXT-11: Zotero Sync (6h) ──
    async def _zotero_sync_job():
        """定期同步 Zotero 文獻到 Qdrant."""
        try:
            from museon.tools.zotero_bridge import ZoteroBridge
            from museon.core.event_bus import get_event_bus

            bridge = ZoteroBridge(
                event_bus=get_event_bus(),
                workspace=data_dir,
            )
            result = await bridge.sync_items()
            synced = result.get("imported", 0)
            if synced:
                logger.info(f"Zotero sync: imported {synced} items")
        except Exception as e:
            logger.debug(f"Zotero sync cron failed: {e}")

    cron_engine.add_job(
        _zotero_sync_job, trigger="interval",
        job_id="zotero-sync",
        hours=6,
    )

    # ── EXT-04: Email Poll (5min) ──
    async def _email_poll_job():
        """定期拉取 Email 新郵件."""
        try:
            from museon.channels.email import EmailAdapter
            from museon.core.event_bus import get_event_bus

            # 只在設定了 IMAP 的情況下執行
            imap_host = os.environ.get("MUSEON_IMAP_HOST")
            if not imap_host:
                return  # 未設定 Email，靜默跳過

            adapter = EmailAdapter(
                config={
                    "imap_host": imap_host,
                    "imap_port": int(os.environ.get("MUSEON_IMAP_PORT", "993")),
                    "smtp_host": os.environ.get("MUSEON_SMTP_HOST", ""),
                    "smtp_port": int(os.environ.get("MUSEON_SMTP_PORT", "587")),
                    "username": os.environ.get("MUSEON_EMAIL_USER", ""),
                    "password": os.environ.get("MUSEON_EMAIL_PASS", ""),
                },
                event_bus=get_event_bus(),
            )
            messages = await adapter.poll_inbox(max_messages=5)
            if messages:
                logger.info(f"Email poll: {len(messages)} new messages")
        except Exception as e:
            logger.debug(f"Email poll cron failed: {e}")

    cron_engine.add_job(
        _email_poll_job, trigger="interval",
        job_id="email-poll",
        minutes=5,
    )

    # ── EXT-14: Community Scan (每天 09:00) ──
    async def _community_scan_job():
        """每日掃描社群平台關鍵字提及."""
        try:
            from museon.channels.community import CommunityAdapter
            from museon.core.event_bus import get_event_bus

            adapter = CommunityAdapter(
                config={"platforms": ["reddit", "hackernews"]},
                event_bus=get_event_bus(),
            )
            mentions = await adapter.scan_mentions(
                keywords=["MUSEON", "AI assistant", "autonomous AI"],
                limit=10,
            )
            if mentions:
                logger.info(f"Community scan: {len(mentions)} mentions found")
        except Exception as e:
            logger.debug(f"Community scan cron failed: {e}")

    cron_engine.add_job(
        _community_scan_job, trigger="cron",
        job_id="community-scan",
        hour=9, minute=0,
    )

    # ── Job: 每日企業個案晨報（每天 09:05）── LLM
    async def _business_case_daily():
        """每天 09:05：搜尋成功+失敗企業個案 → HBR HTML → GitHub Gist → Telegram."""
        try:
            from museon.nightly.business_case import BusinessCaseDaily
            generator = BusinessCaseDaily(data_dir=data_dir)
            adapter = getattr(app.state, "telegram_adapter", None) if app else None
            url = await generator.run(brain=brain, adapter=adapter)
            if url:
                logger.info(f"BusinessCase daily report uploaded: {url}")
            else:
                logger.warning("BusinessCase daily report: no URL (check GITHUB_TOKEN)")
        except Exception as e:
            logger.error(f"BusinessCase daily job failed: {e}", exc_info=True)

    cron_engine.add_job(
        _business_case_daily, trigger="cron", job_id="business-case-daily",
        hour=9, minute=5,
    )

    # ── Session 清理：自動釋放超過 3 天未互動的舊 session ──
    async def _session_cleanup_job():
        """Cleanup dormant sessions (> 3 days inactive)."""
        try:
            from museon.gateway.session_cleanup import cleanup_dormant_sessions
            stats = await cleanup_dormant_sessions()
            logger.info(
                f"Session cleanup complete: {stats['deleted']} deleted, "
                f"{stats['scanned']} scanned, {stats['errors']} errors"
            )
        except Exception as e:
            logger.error(f"Session cleanup job failed: {e}", exc_info=True)

    cron_engine.add_job(
        _session_cleanup_job, trigger="interval", job_id="session-cleanup",
        hours=1,
    )

    # ── MuseWorker + MuseOff + MuseQA + MuseDoc（自主維運四角色）──
    try:
        from museon.doctor.museworker import MuseWorker
        from museon.doctor.museoff import MuseOff
        from museon.doctor.museqa import MuseQA
        from museon.doctor.musedoc import MuseDoc

        _muse_worker = MuseWorker(data_dir.parent)
        _muse_off = MuseOff(data_dir.parent)
        _muse_qa = MuseQA(data_dir.parent)
        _muse_doc = MuseDoc(data_dir.parent)

        # MuseWorker: 每 3 小時全量快照
        cron_engine.add_job(
            _muse_worker.full_snapshot, trigger="interval", job_id="museworker-snapshot",
            hours=3,
        )
        # MuseOff L0: 每 60 秒 liveness
        cron_engine.add_job(
            _muse_off.probe_liveness, trigger="interval", job_id="museoff-l0",
            seconds=60,
        )
        # MuseOff L1: 每 5 分鐘 readiness
        cron_engine.add_job(
            _muse_off.probe_readiness, trigger="interval", job_id="museoff-l1",
            minutes=5,
        )
        # MuseOff L2: 每 30 分鐘 import guard
        cron_engine.add_job(
            _muse_off.probe_import, trigger="interval", job_id="museoff-l2",
            minutes=30,
        )
        # MuseOff L3: 每 60 分鐘 config validator
        cron_engine.add_job(
            _muse_off.probe_config, trigger="interval", job_id="museoff-l3",
            minutes=60,
        )
        # MuseOff L4: 每 2 小時 regression
        cron_engine.add_job(
            _muse_off.probe_regression, trigger="interval", job_id="museoff-l4",
            hours=2,
        )
        # MuseOff L5: 每 6 小時 chaos
        cron_engine.add_job(
            _muse_off.probe_chaos, trigger="interval", job_id="museoff-l5",
            hours=6,
        )
        # MuseOff L6: 每天 15:00 blueprint drift
        cron_engine.add_job(
            _muse_off.probe_blueprint, trigger="cron", job_id="museoff-l6",
            hour=15, minute=0,
        )
        # MuseOff L7: 每 4 小時管線完整性探測
        cron_engine.add_job(
            _muse_off.probe_pipeline_integrity, trigger="interval", job_id="museoff-l7",
            hours=4,
        )
        # MuseQA: 每 15 分鐘品質掃描
        cron_engine.add_job(
            _muse_qa.scan_recent, trigger="interval", job_id="museqa-scan",
            minutes=15,
        )
        # MuseDoc: 每天 04:00 夜間手術
        cron_engine.add_job(
            _muse_doc.nightly_surgery, trigger="cron", job_id="musedoc-surgery",
            hour=4, minute=0,
        )
        logger.info("MuseWorker + MuseOff + MuseQA + MuseDoc 自主維運系統已啟動")
    except Exception as e:
        logger.warning("自主維運系統啟動失敗（非致命）: %s", e)

    # ── 系統排程任務元資料清冊（供 /api/tasks 使用）──
    _system_cron_registry = [
        {"job_id": "nightly-fusion",         "name": "夜間整合管線",         "schedule": "每天 03:00",     "category": "maintenance", "uses_llm": True},
        {"job_id": "system-audit-periodic",  "name": "系統審計",             "schedule": "每天 02:30",     "category": "maintenance", "uses_llm": False},
        {"job_id": "exploration-bridge-batch","name": "探索路由批次",         "schedule": "每天 03:30",     "category": "exploration", "uses_llm": False},
        {"job_id": "skill-acquisition-scan", "name": "Skill 偵查掃描",      "schedule": "每天 04:00",     "category": "exploration", "uses_llm": True},
        {"job_id": "tool-discovery-scan",    "name": "工具自動發現",         "schedule": "每天 05:00",     "category": "exploration", "uses_llm": False},
        {"job_id": "vita-morning",           "name": "霓裳晨感",             "schedule": "每天 07:30",     "category": "pulse",       "uses_llm": True},
        {"job_id": "community-scan",         "name": "社群關鍵字掃描",       "schedule": "每天 09:00",     "category": "external",    "uses_llm": False},
        {"job_id": "business-case-daily",    "name": "每日市場研究報告",     "schedule": "每天 09:05",     "category": "research",    "uses_llm": True},
        {"job_id": "curiosity-research",     "name": "好奇問題研究",         "schedule": "每天 10:00",     "category": "research",    "uses_llm": True},
        {"job_id": "vita-evening",           "name": "霓裳暮感",             "schedule": "每天 22:00",     "category": "pulse",       "uses_llm": True},
        {"job_id": "vita-explore-auto",      "name": "自主探索（每 2h）",    "schedule": "07:10~21:10/2h", "category": "exploration", "uses_llm": True},
        {"job_id": "health-heartbeat",       "name": "健康心跳",             "schedule": "每 30 分鐘",    "category": "maintenance", "uses_llm": False},
        {"job_id": "vita-breath-pulse",      "name": "VITA 息脈",            "schedule": "每 30 分鐘",    "category": "pulse",       "uses_llm": True},
        {"job_id": "guardian-l1",            "name": "Guardian L1 巡檢",     "schedule": "每 30 分鐘",    "category": "maintenance", "uses_llm": False},
        {"job_id": "commitment-check",       "name": "承諾到期檢查",         "schedule": "每 15 分鐘",    "category": "pulse",       "uses_llm": False},
        {"job_id": "vita-idle-check",        "name": "念感閒置偵測",         "schedule": "每 60 分鐘",    "category": "pulse",       "uses_llm": True},
        {"job_id": "vita-free-explore-idle", "name": "閒置自由探索",          "schedule": "每 5 分鐘偵測",  "category": "exploration", "uses_llm": True},
        {"job_id": "companion-watchdog",     "name": "陪伴者看門狗",         "schedule": "每 60 分鐘",    "category": "pulse",       "uses_llm": True},
        {"job_id": "rss-poll",               "name": "RSS 新文章拉取",       "schedule": "每 60 分鐘",    "category": "external",    "uses_llm": False},
        {"job_id": "dify-schedule-sync",     "name": "Dify 排程同步",        "schedule": "每 15 分鐘",    "category": "external",    "uses_llm": False},
        {"job_id": "memory-flush",           "name": "記憶持久化",           "schedule": "每 6 小時",     "category": "maintenance", "uses_llm": False},
        {"job_id": "guardian-deep",          "name": "Guardian L2+L3 深度巡檢","schedule": "每 6 小時",   "category": "maintenance", "uses_llm": False},
        {"job_id": "guardian-l5",            "name": "Guardian L5 程式碼健康", "schedule": "每 6 小時",     "category": "maintenance", "uses_llm": False},
        {"job_id": "morphenix-auto-approve", "name": "Morphenix 自動批准",   "schedule": "每 6 小時",     "category": "evolution",   "uses_llm": False},
        {"job_id": "zotero-sync",            "name": "Zotero 文獻同步",      "schedule": "每 6 小時",     "category": "external",    "uses_llm": False},
        {"job_id": "immune-research",        "name": "免疫研究",             "schedule": "每 2 小時",     "category": "maintenance", "uses_llm": True},
        {"job_id": "vita-sys-pulse",         "name": "VITA 微脈",            "schedule": "每 5 分鐘",     "category": "pulse",       "uses_llm": False},
        {"job_id": "dendritic-tick",         "name": "Dendritic 健康記錄",   "schedule": "每 5 分鐘",     "category": "maintenance", "uses_llm": False},
        {"job_id": "tool-health-check",      "name": "工具健康檢查",         "schedule": "每 5 分鐘",     "category": "maintenance", "uses_llm": False},
        {"job_id": "email-poll",             "name": "Email 郵件拉取",       "schedule": "每 5 分鐘",     "category": "external",    "uses_llm": False},
        {"job_id": "session-cleanup",        "name": "Session 自動清理",     "schedule": "每 60 分鐘",    "category": "maintenance", "uses_llm": False},
        {"job_id": "museworker-snapshot",   "name": "MuseWorker 全量快照",  "schedule": "每 3 小時",     "category": "autonomous",  "uses_llm": False},
        {"job_id": "museoff-l0",            "name": "MuseOff L0 存活探測",  "schedule": "每 60 秒",      "category": "autonomous",  "uses_llm": False},
        {"job_id": "museoff-l1",            "name": "MuseOff L1 就緒探測",  "schedule": "每 5 分鐘",     "category": "autonomous",  "uses_llm": False},
        {"job_id": "museoff-l2",            "name": "MuseOff L2 import",   "schedule": "每 30 分鐘",    "category": "autonomous",  "uses_llm": False},
        {"job_id": "museoff-l3",            "name": "MuseOff L3 config",   "schedule": "每 60 分鐘",    "category": "autonomous",  "uses_llm": False},
        {"job_id": "museoff-l4",            "name": "MuseOff L4 回歸測試",  "schedule": "每 2 小時",     "category": "autonomous",  "uses_llm": False},
        {"job_id": "museoff-l5",            "name": "MuseOff L5 故障注入",  "schedule": "每 6 小時",     "category": "autonomous",  "uses_llm": False},
        {"job_id": "museoff-l6",            "name": "MuseOff L6 藍圖漂移",  "schedule": "每天 15:00",    "category": "autonomous",  "uses_llm": False},
        {"job_id": "museqa-scan",           "name": "MuseQA 品質掃描",     "schedule": "每 15 分鐘",    "category": "autonomous",  "uses_llm": False},
        {"job_id": "musedoc-surgery",       "name": "MuseDoc 夜間手術",    "schedule": "每天 04:00",    "category": "autonomous",  "uses_llm": False},
    ]

    # 存到 app.state 供 /api/tasks 讀取
    if app:
        app.state.system_cron_registry = _system_cron_registry

    logger.info(
        f"System cron jobs registered: {len(_system_cron_registry)} tasks | "
        "nightly-fusion(03:00), health-heartbeat(30min), "
        "vita-explore-auto(every2h@:10), business-case-daily(09:05), ..."
    )

