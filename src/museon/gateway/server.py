"""Gateway FastAPI Server - Localhost only.

MUSEON Brain 的入口。所有訊息（Telegram, Webhook）都經過 Brain 處理。

Integrates:
- FastAPI webhook endpoint
- Telegram polling adapter
- MuseonBrain (DNA27 + Skills + ANIMA + Memory)
- Session management (serial per session)
- Security gate (HMAC, rate limiting, input sanitization)
"""

import asyncio
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

from .message import InternalMessage
from .session import SessionManager
from .security import SecurityGate
from .cron import CronEngine
from .session_cleanup import cleanup_dormant_sessions

logger = logging.getLogger("museon.gateway.server")


def _configure_logging() -> None:
    """Configure application-level logging for the museon namespace.

    Uvicorn manages its own access logs (stdout → gateway.log via Electron).
    This function sets up the 'museon' logger hierarchy so that
    application-level logs (DNA27 routing, skill matching, tool calls, etc.)
    are captured to a dedicated file AND stderr.

    Log file: {runtime_root}/logs/museon.log
    """
    import sys

    # ── Resolve log directory ──
    # 1. Walk up from __file__ to find the runtime root (has pyproject.toml)
    # 2. Fallback to ~/MUSEON/logs
    log_dir = None
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            if parent.name == ".runtime":
                log_dir = parent.parent / "logs"
            else:
                log_dir = parent / "logs"
            break

    if log_dir is None:
        log_dir = Path.home() / "MUSEON" / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "museon.log"

    # ── Configure the 'museon' namespace logger ──
    app_logger = logging.getLogger("museon")
    app_logger.setLevel(logging.INFO)

    # Avoid adding duplicate handlers on reload
    if not app_logger.handlers:
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # File handler — dedicated parseable log
        fh = logging.FileHandler(str(log_file), encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        app_logger.addHandler(fh)

        # Stderr handler — captured by Electron to gateway.err
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(logging.INFO)
        sh.setFormatter(fmt)
        app_logger.addHandler(sh)

    # Prevent propagation to root logger (avoids double-output)
    app_logger.propagate = False


# Global instances (singleton pattern for gateway)
session_manager = SessionManager()
security_gate = SecurityGate()
cron_engine = CronEngine()

# MUSEON Brain — 全域實例，在 startup 時初始化
_brain = None


def _load_env_file() -> None:
    """Load .env file into os.environ.

    Resolution order for .env location:
    1. $MUSEON_HOME/.env
    2. Walk up from this file to find pyproject.toml, then .env next to it
    3. Fallback: ~/MUSEON/.env
    """
    # Try MUSEON_HOME first
    home = os.environ.get("MUSEON_HOME")
    if home:
        env_file = Path(home) / ".env"
        if env_file.exists():
            _parse_env(env_file)
            return

    # Walk up from this file
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            # If we're inside .runtime, .env is one level up
            if parent.name == ".runtime":
                env_file = parent.parent / ".env"
            else:
                env_file = parent / ".env"
            if env_file.exists():
                _parse_env(env_file)
                return

    # Fallback
    env_file = Path.home() / "MUSEON" / ".env"
    if env_file.exists():
        _parse_env(env_file)


def _parse_env(env_file: Path) -> None:
    """Parse a .env file and set os.environ.

    .env 是 API Key 的唯一 source of truth。
    系統路徑變數（PATH/PYTHONPATH/MUSEON_HOME）由 launchd plist 管理，不覆蓋。
    API Key 類別的變數一律從 .env 載入（覆蓋舊值），確保 Setup Wizard
    更新 Key 後 Gateway 重啟能讀到最新值。
    """
    # 不覆蓋的系統變數（由 launchd plist 或 shell 管理）
    SYSTEM_VARS = {"PATH", "PYTHONPATH", "MUSEON_HOME", "HOME", "USER", "SHELL"}

    logger.info(f"Loading environment from {env_file}")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        # 系統變數不覆蓋；API Key 等業務變數一律從 .env 載入
        if key in SYSTEM_VARS and key in os.environ:
            continue
        os.environ[key] = value


def _persist_env_setting(key: str, value: str) -> None:
    """Persist a setting to the .env file.

    找到 .env 檔案，如果有相同 key 就更新，沒有就新增。
    """
    # 找到 .env 位置
    home = os.environ.get("MUSEON_HOME")
    env_file = None
    if home:
        candidate = Path(home) / ".env"
        if candidate.exists():
            env_file = candidate

    if not env_file:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "pyproject.toml").exists():
                if parent.name == ".runtime":
                    candidate = parent.parent / ".env"
                else:
                    candidate = parent / ".env"
                if candidate.exists():
                    env_file = candidate
                    break

    if not env_file:
        logger.warning(f"Cannot persist {key}: .env file not found")
        return

    lines = env_file.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"# {key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info(f"Persisted {key} to {env_file}")


def _resolve_data_dir() -> str:
    """Resolve the data directory path.

    Resolution order:
    1. $MUSEON_HOME/data
    2. Walk up from this file to find pyproject.toml → data/ next to it
       (or parent/data/ if inside .runtime)
    3. Fallback: ~/MUSEON/data
    """
    # Try MUSEON_HOME first
    home = os.environ.get("MUSEON_HOME")
    if home:
        data_dir = Path(home) / "data"
        if data_dir.exists():
            return str(data_dir)

    # Walk up from this file
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            # If we're inside .runtime, data/ is one level up
            if parent.name == ".runtime":
                data_dir = parent.parent / "data"
            else:
                data_dir = parent / "data"
            if data_dir.exists():
                return str(data_dir)

    # Fallback
    fallback = Path.home() / "MUSEON" / "data"
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback)


# 全局 LLM 併發限制：最多同時 3 個 brain.process() 呼叫
# 防止多群組同時 @bot 時打爆 API rate limit
_LLM_CONCURRENCY_LIMIT = 3
_llm_semaphore: Optional[asyncio.Semaphore] = None


def _get_llm_semaphore() -> asyncio.Semaphore:
    """取得全局 LLM 併發 Semaphore（lazy init，確保在 event loop 內建立）."""
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(_LLM_CONCURRENCY_LIMIT)
    return _llm_semaphore


def _get_brain():
    """Get the global brain instance (lazy, thread-safe enough for async)."""
    global _brain
    if _brain is None:
        from museon.agent.brain import MuseonBrain
        data_dir = _resolve_data_dir()
        _brain = MuseonBrain(data_dir=data_dir)
        logger.info(f"MUSEON Brain initialized with data_dir={data_dir}")
    return _brain


def _reset_brain():
    """Reset brain instance (for testing isolation)."""
    global _brain
    _brain = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="MUSEON Gateway",
        description="24/7 Life Central - MUSEON Brain routing and session management",
        version="0.2.0",
    )

    # ─── CORS（Observatory / Electron 跨域存取）───
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─── Telegram adapter state ───
    app.state.telegram_adapter = None
    app.state.telegram_pump_task = None

    @app.get("/health")
    async def health_check() -> Dict[str, Any]:
        """Health check endpoint."""
        try:
            telegram_status = "running" if app.state.telegram_adapter else "not configured"
            brain = _get_brain()
            brain_status = "alive" if brain else "not initialized"
            skill_count = brain.skill_router.get_skill_count() if brain else 0

            # v10.2: MCP status
            mcp_status = "disabled"
            if (
                brain
                and hasattr(brain, '_tool_executor')
                and brain._tool_executor
                and hasattr(brain._tool_executor, '_mcp_connector')
                and brain._tool_executor._mcp_connector
            ):
                mcp_info = brain._tool_executor._mcp_connector.get_status()
                connected = mcp_info.get("total_connected", 0)
                total = len(mcp_info.get("connections", {}))
                tools = mcp_info.get("total_tools", 0)
                mcp_status = f"{connected}/{total} servers, {tools} tools"

            # 🛡️ Governor: 三焦式健康報告
            governor_health = {}
            governor = getattr(app.state, 'governor', None)
            if governor:
                governor_health = governor.get_health()

            # 🚢 Bulkhead: 艙壁隔離狀態
            bulkhead = getattr(app.state, 'bulkhead', None)
            bulkhead_status = bulkhead.get_status() if bulkhead else {}
            overall = bulkhead.overall_status if bulkhead else "healthy"

            # Circuit Breaker 狀態
            cb_status = {}
            try:
                from museon.governance.bulkhead import get_brain_circuit_breaker
                cb_status = get_brain_circuit_breaker().get_status()
            except Exception:
                pass

            return {
                "status": overall,
                "timestamp": datetime.now().isoformat(),
                "telegram": telegram_status,
                "brain": brain_status,
                "skills_indexed": skill_count,
                "mcp": mcp_status,
                "governance": governor_health,
                "bulkhead": bulkhead_status,
                "circuit_breaker": cb_status,
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    @app.post("/webhook")
    async def webhook_handler(
        request: Request, x_signature: str = Header(None)
    ) -> JSONResponse:
        """
        Webhook endpoint for external integrations.

        Validates HMAC signature and rate limiting before processing.
        Routes through MUSEON Brain for response generation.
        """
        # Read raw body
        body = await request.body()

        # Validate HMAC if signature provided
        if x_signature:
            if not security_gate.validate_hmac(body, x_signature):
                logger.warning("Invalid HMAC signature")
                raise HTTPException(status_code=403, detail="Invalid signature")

        # Parse JSON
        try:
            data = await request.json()
        except Exception as e:
            logger.error(f"Invalid JSON: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail="Invalid JSON")

        # Extract user_id for rate limiting
        user_id = data.get("user_id", "unknown")

        # Check rate limit
        if not security_gate.check_rate_limit(user_id):
            logger.warning(f"Rate limit exceeded for user {user_id}")
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        # Sanitize input
        try:
            content = security_gate.sanitize_input(data.get("content", ""))
        except ValueError as e:
            logger.warning(f"Suspicious input detected: {e}")
            raise HTTPException(status_code=400, detail=str(e))

        # Create internal message
        try:
            message = InternalMessage(
                source="webhook",
                session_id=data.get("session_id", f"webhook_{user_id}"),
                user_id=user_id,
                content=content,
                timestamp=datetime.now(),
                trust_level=data.get("trust_level", "external"),
                metadata=data.get("metadata", {}),
            )
        except ValueError as e:
            logger.error(f"Invalid message format: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail=str(e))

        # Acquire session lock
        session_id = message.session_id
        if not await session_manager.acquire(session_id):
            # Session is busy, queue the message (simplified: return 202 Accepted)
            return JSONResponse(
                status_code=202, content={"status": "queued", "session_id": session_id}
            )

        try:
            # ── Route through MUSEON Brain ──
            brain = _get_brain()
            result = await brain.process(
                content=message.content,
                session_id=session_id,
                user_id=user_id,
                source="webhook",
            )

            # v9.0: BrainResponse support
            from museon.gateway.message import BrainResponse
            if isinstance(result, BrainResponse):
                response_text = result.text
                response_payload = result.to_dict()
            else:
                response_text = str(result) if result else ""
                response_payload = {"text": response_text, "artifacts": []}

            logger.info(f"Brain responded to webhook/{session_id} ({len(response_text)} chars)")

            return JSONResponse(
                content={
                    "status": "ok",
                    "session_id": session_id,
                    "response": response_text,
                    "brain_response": response_payload,
                }
            )
        except Exception as e:
            logger.error(f"Brain processing error: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": str(e)},
            )
        finally:
            await session_manager.release(session_id)

    # ─── Telegram Management Endpoints ───

    @app.get("/api/telegram/status")
    async def telegram_status() -> Dict[str, Any]:
        """Get Telegram adapter connection status."""
        try:
            adapter = app.state.telegram_adapter
            if not adapter:
                return {"configured": False, "running": False, "last_message_time": None}
            return {
                "configured": True,
                **adapter.get_status(),
            }
        except Exception as e:
            logger.error(f"Telegram status check failed: {e}", exc_info=True)
            return {"configured": False, "error": str(e)}

    @app.post("/api/telegram/restart")
    async def telegram_restart() -> Dict[str, Any]:
        """Restart Telegram adapter (reconnect without restarting Gateway)."""
        steps = []
        try:
            # Stop existing
            if app.state.telegram_pump_task:
                app.state.telegram_pump_task.cancel()
                try:
                    await app.state.telegram_pump_task
                except asyncio.CancelledError as e:
                    logger.debug(f"[SERVER] telegram failed (degraded): {e}")
                steps.append("已停止訊息泵")

            if app.state.telegram_adapter:
                await app.state.telegram_adapter.stop()
                steps.append("已停止 Telegram adapter")

            # Restart
            bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
            if not bot_token:
                return {"success": False, "steps": steps, "error": "TELEGRAM_BOT_TOKEN 未設定"}

            from museon.channels.telegram import TelegramAdapter

            trusted_ids_raw = os.environ.get("TELEGRAM_TRUSTED_IDS", "")
            trusted_ids = [x.strip() for x in trusted_ids_raw.split(",") if x.strip()]

            adapter = TelegramAdapter({
                "bot_token": bot_token,
                "trusted_user_ids": trusted_ids,
            })
            await adapter.start()
            app.state.telegram_adapter = adapter
            steps.append("已重新啟動 Telegram adapter")

            # Restart message pump
            app.state.telegram_pump_task = asyncio.create_task(
                _telegram_message_pump(adapter)
            )
            steps.append("已重新啟動訊息泵")

            return {"success": True, "steps": steps}
        except Exception as e:
            steps.append(f"錯誤：{e}")
            return {"success": False, "steps": steps, "error": str(e)}

    # ─── Dashboard → Brain 注入（DSE 研究等 Dashboard 觸發的任務）───

    @app.post("/api/telegram/inject")
    async def telegram_inject(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        """Dashboard 注入訊息到 Brain，結果透過 Telegram 回覆 owner."""
        text = payload.get("text", "").strip()
        if not text:
            return {"success": False, "error": "text is required"}
        try:
            brain = _get_brain()
            owner_id = os.environ.get("TELEGRAM_OWNER_ID", "6969045906")
            session_id = f"telegram_{owner_id}"

            brain_result = await brain.process(
                content=text,
                session_id=session_id,
                user_id=owner_id,
                source="dashboard",
            )

            # 透過 Telegram 回覆結果
            response_text = ""
            from museon.gateway.message import BrainResponse
            if isinstance(brain_result, BrainResponse):
                response_text = brain_result.text
            elif brain_result:
                response_text = str(brain_result)

            if response_text and app.state.telegram_adapter:
                from museon.gateway.message import InternalMessage
                reply_msg = InternalMessage(
                    source="dashboard",
                    session_id=session_id,
                    user_id="system",
                    content=response_text,
                    timestamp=datetime.now(),
                    trust_level="core",
                    metadata={"chat_id": int(owner_id)},
                )
                await app.state.telegram_adapter.send(reply_msg)

            return {"success": True, "response_length": len(response_text)}
        except Exception as e:
            logger.error(f"Telegram inject failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # ─── Push Notification Endpoint（純 CPU 模板 → Telegram）───

    @app.post("/api/notify")
    async def push_notification(payload: Dict[str, Any]) -> Dict[str, Any]:
        """推播通知到使用者 Telegram — 零 Token.

        Body:
            source: 來源（subagent / cron / system）
            title: 通知標題
            body: 通知內容
            emoji: 可選 emoji
        """
        adapter = app.state.telegram_adapter
        if not adapter:
            return {"success": False, "sent": 0, "error": "Telegram not configured"}

        source = payload.get("source", "system")
        title = payload.get("title", "MUSEON 通知")
        body = payload.get("body", "")
        emoji = payload.get("emoji", "📢")

        # 純 CPU 模板格式化
        text = f"{emoji} [{source}] {title}\n\n{body}"

        try:
            sent = await adapter.push_notification(text)
            return {"success": sent > 0, "sent": sent}
        except Exception as e:
            logger.error(f"Push notification failed: {e}", exc_info=True)
            return {"success": False, "sent": 0, "error": str(e)}

    # ─── Doctor 健檢 & 修復端點（純 CPU）───

    @app.get("/api/doctor/check")
    async def doctor_health_check() -> Dict[str, Any]:
        """執行完整健檢 — 純 CPU, 零 Token"""
        try:
            from museon.doctor.health_check import HealthChecker

            checker = HealthChecker()
            report = checker.run_all()
            result = report.to_dict()
            # 健檢完成 → 推送給 3D 心智圖
            try:
                if hasattr(app.state, "broadcast_doctor_status"):
                    asyncio.ensure_future(app.state.broadcast_doctor_status())
            except Exception:
                pass
            return result
        except Exception as e:
            return {"error": str(e), "overall": "unknown", "checks": []}

    @app.get("/api/doctor/skill-doctor")
    async def doctor_skill_doctor() -> Dict[str, Any]:
        """執行 Skill Doctor 雙層健檢（結構 + 認知）."""
        try:
            import asyncio
            from museon.doctor.system_audit import SystemAuditor

            brain = _get_brain()
            auditor = SystemAuditor(
                museon_home=str(Path(brain.data_dir).parent),
            )
            checks = await asyncio.to_thread(auditor._audit_skill_doctor)
            result_checks = []
            for c in checks:
                result_checks.append({
                    "name": c.name,
                    "status": c.status,
                    "message": c.message,
                    "details": c.details if hasattr(c, "details") else {},
                    "repairable": False,
                    "repair_action": "",
                })
            ok_count = sum(1 for c in result_checks if c["status"] == "ok")
            total = len(result_checks)
            overall = "ok" if ok_count == total else "warning" if ok_count >= total // 2 else "critical"
            return {
                "timestamp": datetime.now().isoformat(),
                "overall": overall,
                "checks": result_checks,
            }
        except Exception as e:
            logger.error("skill-doctor error: %s", e, exc_info=True)
            return {"error": str(e), "overall": "unknown", "checks": []}

    @app.post("/api/doctor/repair")
    async def doctor_repair(payload: Dict[str, Any]) -> Dict[str, Any]:
        """執行修復動作 — 純 CPU"""
        action = payload.get("action", "")
        if not action:
            return {"error": "missing action parameter"}

        try:
            from museon.doctor.auto_repair import AutoRepair

            repair = AutoRepair()
            result = repair.execute(action)
            return {
                "action": result.action,
                "status": result.status.value,
                "message": result.message,
                "duration_ms": result.duration_ms,
            }
        except Exception as e:
            return {"action": action, "status": "failed", "message": str(e)}

    # ─── Self-Surgery 手術端點 ───

    @app.get("/api/doctor/surgery/status")
    async def doctor_surgery_status() -> Dict[str, Any]:
        """取得手術引擎狀態 — 純 CPU"""
        try:
            from museon.doctor.surgeon import SurgeryEngine
            engine = SurgeryEngine(project_root=Path(_resolve_data_dir()).parent)
            return {"success": True, **engine.get_status()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/doctor/surgery/diagnose")
    async def doctor_surgery_diagnose(
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """手動觸發三層診斷管線"""
        try:
            from museon.doctor.diagnosis_pipeline import DiagnosisPipeline

            brain = _get_brain()
            llm_adapter = brain._llm_adapter if hasattr(brain, "_llm_adapter") else None
            _data_dir = _resolve_data_dir()
            project_root = Path(_data_dir).parent

            pipeline = DiagnosisPipeline(
                source_root=project_root / "src" / "museon",
                logs_dir=project_root / "logs",
                heartbeat_state_path=Path(_data_dir) / "pulse" / "heartbeat_engine.json",
                llm_adapter=llm_adapter,
            )

            skip_d3 = payload.get("skip_d3", False)
            result = await pipeline.run(skip_d3=skip_d3)

            return {
                "success": True,
                "summary": result.summary,
                "diagnosis_level": result.diagnosis_level,
                "critical_count": result.critical_count,
                "code_issues_count": len(result.code_issues),
                "log_anomalies_count": len(result.log_anomalies),
                "proposals_count": len(result.proposals),
            }
        except Exception as e:
            logger.error(f"Surgery diagnose failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @app.get("/api/doctor/surgery/log")
    async def doctor_surgery_log() -> Dict[str, Any]:
        """取得手術記錄"""
        try:
            from museon.doctor.surgery_log import SurgeryLog
            log = SurgeryLog(data_dir=Path(_resolve_data_dir()) / "doctor")
            return {
                "success": True,
                "recent": log.recent(20),
                "stats": log.stats(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.get("/api/doctor/code-health")
    async def doctor_code_health() -> Dict[str, Any]:
        """執行 AST 靜態分析 — 純 CPU"""
        try:
            from museon.doctor.code_analyzer import CodeAnalyzer

            project_root = Path(data_dir).parent
            analyzer = CodeAnalyzer(
                source_root=project_root / "src" / "museon"
            )
            import asyncio
            issues = await asyncio.to_thread(analyzer.scan_all)

            result = {
                "success": True,
                "total": len(issues),
                "critical": sum(1 for i in issues if i.severity == "critical"),
                "warning": sum(1 for i in issues if i.severity == "warning"),
                "info": sum(1 for i in issues if i.severity == "info"),
                "issues": [
                    {
                        "rule_id": i.rule_id,
                        "file": i.file_path,
                        "line": i.line,
                        "message": i.message,
                        "severity": i.severity,
                    }
                    for i in issues[:30]
                ],
                "report": CodeAnalyzer.format_report(issues),
            }
            # 分析完成 → 推送給 3D 心智圖
            try:
                if hasattr(app.state, "broadcast_doctor_status"):
                    asyncio.ensure_future(app.state.broadcast_doctor_status())
            except Exception:
                pass
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── Doctor Node Status（3D 心智圖專用）───

    @app.get("/api/doctor/node-status")
    async def doctor_node_status() -> Dict[str, Any]:
        """組合 health_check + code_health，回傳以 node_id 為 key 的診斷映射.

        供 3D 心智圖即時顯示 Doctor 診斷結果。
        """
        from datetime import datetime as _dt

        # ── 預填所有拓撲節點為 ok（與 system-topology.md 同步）──
        _ALL_TOPOLOGY_NODES = [
            # center
            "event-bus",
            # channel
            "user", "telegram", "gateway", "cron", "mcp-server",
            # agent
            "brain", "dna27", "skill-router", "reflex-router", "dispatch",
            "knowledge-lattice", "plan-engine", "metacognition", "intuition",
            "eval-engine", "diary-store", "onboarding", "multiagent",
            "multi-agent-executor", "response-synthesizer", "flywheel-coordinator",
            "primal-detector", "persona-router", "deep-think", "roundtable",
            "investment-masters", "drift-detector", "okr-router", "fact-correction",
            "dendritic-fusion", "recommender",
            # pulse
            "pulse", "heartbeat", "explorer", "silent-digestion", "proactive-bridge",
            "micro-pulse", "pulse-db", "commitment-tracker", "anima-mc-store",
            "anima-tracker", "group-session-proactive",
            # gov
            "governance", "governor", "immunity", "preflight", "refractory",
            "skill-scanner", "sandbox", "telegram-guard", "service-health",
            "guardian", "security", "dendritic-scorer", "footprint", "perception",
            "cognitive-receipt",
            # doctor
            "doctor", "system-audit", "health-check", "self-diagnosis",
            "auto-repair", "surgery", "log-analyzer", "code-analyzer",
            "memory-reset", "observatory",
            # llm
            "llm-router", "budget-mgr", "rate-limit", "llm-cache",
            # data
            "data-bus", "data-watchdog", "memory", "vector-index",
            "group-context-db", "workflow-state-db", "wee", "skills-registry",
            "registry", "skill-synapse", "blueprint-reader", "lord-profile",
            "sparse-embedder",
            # evolution
            "evolution", "outward-trigger", "intention-radar", "digest-engine",
            "research-engine", "evolution-velocity", "feedback-loop",
            "parameter-tuner", "tool-muscle", "trigger-weights",
            # tools
            "tool-registry", "tool-discovery", "dify-scheduler", "image-gen",
            "rss-aggregator", "voice-clone", "zotero-bridge", "mcp-dify",
            "skill-market", "federation-sync",
            # nightly
            "nightly", "morphenix", "curiosity-router", "exploration-bridge",
            "skill-forge-scout", "crystal-actuator", "periodic-cycles",
            "morphenix-validator",
            # installer
            "installer", "installer-daemon", "installer-electron",
            "installer-env", "installer-verifier",
            # external
            "searxng", "qdrant", "firecrawl", "anthropic-api",
        ]

        node_map: Dict[str, Dict[str, Any]] = {
            nid: {"status": "ok", "issues": []} for nid in _ALL_TOPOLOGY_NODES
        }

        def _set_worst(nid: str, status: str, issue: str = ""):
            """設定節點狀態（只往嚴重方向升級）"""
            severity = {"ok": 0, "warning": 1, "critical": 2, "unknown": -1}
            if nid not in node_map:
                node_map[nid] = {"status": "ok", "issues": []}
            cur = severity.get(node_map[nid]["status"], 0)
            new = severity.get(status, 0)
            if new > cur:
                node_map[nid]["status"] = status
            if issue:
                node_map[nid]["issues"].append(issue)

        # ── A. Health Check 12 項 → 映射到節點 ──
        try:
            from museon.doctor.health_check import HealthChecker
            import asyncio as _hc_aio
            checker = HealthChecker()
            report = await _hc_aio.to_thread(checker.run_all)

            # 映射表：檢查名稱關鍵字 → 拓撲節點 ID 列表
            _hc_map = {
                "gateway": ["gateway"],
                "daemon": ["guardian", "installer-daemon"],
                "數據完整性": ["diary-store", "pulse-db", "memory"],
                "核心模組": ["brain", "skill-router", "gateway"],
                "dashboard": ["installer-electron"],
                "app": ["installer-electron"],
                "api key": ["llm-router", "anthropic-api"],
                ".env": ["llm-router"],
                "目錄": ["data-bus"],
                "venv": ["installer-env"],
                "虛擬環境": ["installer-env"],
                "磁碟": ["data-bus"],
                "disk": ["data-bus"],
                "日誌": ["log-analyzer"],
                "log": ["log-analyzer"],
            }

            for chk in report.to_dict().get("checks", []):
                chk_name = chk.get("name", "")
                chk_status = chk.get("status", "ok")
                if chk_status == "ok":
                    continue
                for keyword, nids in _hc_map.items():
                    if keyword.lower() in chk_name.lower():
                        for nid in nids:
                            _set_worst(nid, chk_status, f"[健檢] {chk_name}: {chk.get('message', '')}")
        except Exception as hc_err:
            logger.debug(f"node-status health_check failed: {hc_err}")

        # ── B. Code Analyzer AST → 映射到節點 ──
        try:
            from museon.doctor.code_analyzer import CodeAnalyzer
            import asyncio as _aio

            project_root = Path(data_dir).parent
            analyzer = CodeAnalyzer(source_root=project_root / "src" / "museon")
            issues = await _aio.to_thread(analyzer.scan_all)

            for issue in issues:
                # 路徑轉節點 ID：src/museon/agent/brain.py → brain
                fp = issue.file_path
                parts = Path(fp).parts
                # 找 museon 之後的路徑
                try:
                    idx = list(parts).index("museon")
                    if idx + 2 < len(parts):
                        module_file = parts[idx + 2]  # e.g., "brain.py"
                        nid = module_file.replace(".py", "").replace("_", "-")
                        _set_worst(
                            nid,
                            issue.severity,
                            f"[{issue.rule_id}] {issue.message} ({Path(fp).name}:{issue.line})",
                        )
                except (ValueError, IndexError):
                    pass
        except Exception as ca_err:
            logger.debug(f"node-status code_analyzer failed: {ca_err}")

        # ── 統計 ──
        summary = {"ok": 0, "warning": 0, "critical": 0}
        for v in node_map.values():
            s = v["status"]
            if s in summary:
                summary[s] += 1

        overall = "ok"
        if summary["critical"] > 0:
            overall = "critical"
        elif summary["warning"] > 0:
            overall = "warning"

        return {
            "timestamp": _dt.now().isoformat(),
            "overall": overall,
            "nodes": node_map,
            "summary": summary,
        }

    # ─── Budget 用量端點（純 CPU）───

    @app.get("/api/budget")
    async def get_budget_stats() -> Dict[str, Any]:
        """取得 Token 用量統計 — 純 CPU, 零 Token"""
        try:
            brain = _get_brain()
            if brain.budget_monitor:
                return brain.budget_monitor.get_usage_stats()
            return {
                "daily_limit": 200000,
                "used": 0,
                "remaining": 200000,
                "percentage": 0.0,
                "should_warn": False,
            }
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/budget/limit")
    async def set_budget_limit(payload: Dict[str, Any]) -> Dict[str, Any]:
        """設定每日 Token 預算上限 — 純 CPU

        Body:
            daily_limit: 新的每日 Token 上限（正整數）
        """
        try:
            new_limit = int(payload.get("daily_limit", 0))
            if new_limit <= 0:
                return {"success": False, "error": "daily_limit 必須為正整數"}

            brain = _get_brain()
            if brain.budget_monitor:
                brain.budget_monitor.set_daily_limit(new_limit)

                # 也持久化到 .env
                _persist_env_setting("MUSEON_DAILY_TOKEN_LIMIT", str(new_limit))

                return {
                    "success": True,
                    "daily_limit": new_limit,
                    "message": f"每日 Token 預算已更新為 {new_limit:,}",
                }
            return {"success": False, "error": "BudgetMonitor not initialized"}
        except (ValueError, TypeError) as e:
            return {"success": False, "error": str(e)}

    # ─── Key 狀態端點（純 CPU）───

    @app.get("/api/key-status")
    async def get_key_status() -> Dict[str, Any]:
        """取得認證狀態 — 不回傳 Key 值本身"""
        telegram = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        # OAuth token 來自 ~/.museon/oauth_token
        oauth_path = Path.home() / ".museon" / "oauth_token"
        oauth_exists = oauth_path.exists() and oauth_path.stat().st_size > 0
        return {
            "LLM_AUTH": {
                "method": "CLI OAuth (MAX plan)",
                "oauth_token_file": str(oauth_path),
                "configured": oauth_exists,
            },
            "TELEGRAM_BOT_TOKEN": {
                "configured": bool(telegram),
                "prefix": telegram[:8] + "***" if len(telegram) > 8 else "",
            },
        }

    # ─── Guardian 守護者端點（純 CPU）───

    @app.get("/api/guardian/status")
    async def guardian_status() -> Dict[str, Any]:
        """取得 Guardian 守護者狀態 — 純 CPU, 零 Token"""
        try:
            from museon.guardian.daemon import GuardianDaemon
            brain = _get_brain()
            guardian = GuardianDaemon(
                data_dir=str(brain.data_dir), brain=brain,
            )
            return guardian.get_status()
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/guardian/check")
    async def guardian_full_check() -> Dict[str, Any]:
        """執行 Guardian 完整巡檢（L1+L2+L3）— 純 CPU, 零 Token"""
        try:
            from museon.guardian.daemon import GuardianDaemon
            brain = _get_brain()
            guardian = GuardianDaemon(
                data_dir=str(brain.data_dir), brain=brain,
            )
            l1 = await guardian.run_l1()
            l2 = await guardian.run_l2()
            l3 = await guardian.run_l3()
            return {
                "l1": l1,
                "l2": l2,
                "l3": l3,
                "unresolved": guardian.get_status().get("unresolved", []),
            }
        except Exception as e:
            return {"error": str(e)}

    # ─── VITA 脈搏引擎端點 ───

    @app.get("/api/pulse/status")
    async def pulse_status() -> Dict[str, Any]:
        """取得 VITA PulseEngine 狀態 — Dashboard 用"""
        try:
            engine = getattr(app.state, "pulse_engine", None)
            if not engine:
                return {"error": "PulseEngine not initialized", "active": False}
            return engine.get_status()
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/pulse/anima")
    async def pulse_anima() -> Dict[str, Any]:
        """取得 ANIMA 八元素雷達圖資料"""
        try:
            tracker = getattr(app.state, "anima_tracker", None)
            if not tracker:
                return {"error": "AnimaTracker not initialized"}
            return tracker.get_radar_data()
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/anima/user/group-behaviors")
    async def anima_user_group_behaviors() -> Dict[str, Any]:
        """取得 ANIMA_USER L8 群組行為觀察."""
        try:
            brain = _get_brain()
            dd = getattr(brain, "data_dir", None) or str(Path.home() / "MUSEON" / "data")
            anima_path = Path(dd) / "anima" / "anima_user.json"
            if not anima_path.exists():
                return {"observations": [], "group_stats": {}, "count": 0}
            import json as _json
            anima_user = _json.loads(anima_path.read_text(encoding="utf-8"))
            l8 = anima_user.get("L8_context_behavior_notes", {})
            return {
                "observations": l8.get("observations", [])[-20:],  # 最近 20 筆
                "group_stats": l8.get("group_stats", {}),
                "count": len(l8.get("observations", [])),
            }
        except Exception as e:
            return {"error": str(e), "observations": [], "group_stats": {}}

    @app.get("/api/pulse/explorations")
    async def pulse_explorations() -> Dict[str, Any]:
        """取得今日探索日誌"""
        try:
            db = getattr(app.state, "pulse_db", None)
            if not db:
                return {"explorations": [], "count": 0}
            exps = db.get_today_explorations()
            return {"explorations": exps, "count": len(exps)}
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/pulse/explore")
    async def pulse_trigger_explore(request: Request) -> Dict[str, Any]:
        """手動觸發一次探索"""
        try:
            engine = getattr(app.state, "pulse_engine", None)
            if not engine:
                return {"error": "PulseEngine not initialized"}
            body = await request.json()
            topic = body.get("topic", "AI 技術趨勢")
            result = await engine.soul_pulse(trigger="curiosity", context=f"手動探索: {topic}")
            return result
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/pulse/history")
    async def pulse_history() -> Dict[str, Any]:
        """取得 ANIMA 變化歷史"""
        try:
            db = getattr(app.state, "pulse_db", None)
            if not db:
                return {"history": []}
            return {"history": db.get_anima_history(limit=30)}
        except Exception as e:
            return {"error": str(e)}

    # ── Morphenix Proposals API ──

    @app.get("/api/morphenix/proposals")
    async def morphenix_proposals() -> Dict[str, Any]:
        """取得所有 Morphenix 提案."""
        try:
            db = getattr(app.state, "pulse_db", None)
            if not db:
                return {"proposals": []}
            return {"proposals": db.get_all_proposals(limit=50)}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/morphenix/pending")
    async def morphenix_pending() -> Dict[str, Any]:
        """取得待審核的 Morphenix 提案."""
        try:
            db = getattr(app.state, "pulse_db", None)
            if not db:
                return {"proposals": []}
            return {"proposals": db.get_pending_proposals()}
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/morphenix/approve")
    async def morphenix_approve(request: Request) -> Dict[str, Any]:
        """批准 Morphenix 提案."""
        try:
            body = await request.json()
            proposal_id = body.get("proposal_id")
            if not proposal_id:
                return {"error": "missing proposal_id"}
            db = getattr(app.state, "pulse_db", None)
            if not db:
                return {"error": "pulse_db not available"}
            success = db.approve_proposal(proposal_id, decided_by="dashboard")
            return {"success": success, "proposal_id": proposal_id}
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/morphenix/reject")
    async def morphenix_reject(request: Request) -> Dict[str, Any]:
        """拒絕 Morphenix 提案."""
        try:
            body = await request.json()
            proposal_id = body.get("proposal_id")
            if not proposal_id:
                return {"error": "missing proposal_id"}
            db = getattr(app.state, "pulse_db", None)
            if not db:
                return {"error": "pulse_db not available"}
            success = db.reject_proposal(proposal_id, decided_by="dashboard")
            return {"success": success, "proposal_id": proposal_id}
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/morphenix/execute")
    async def morphenix_execute(request: Request) -> Dict[str, Any]:
        """手動執行已核准的 Morphenix 提案."""
        try:
            body = await request.json()
            proposal_id = body.get("proposal_id")  # optional
            db = getattr(app.state, "pulse_db", None)
            if not db:
                return {"error": "pulse_db not available"}

            from museon.nightly.morphenix_executor import MorphenixExecutor

            brain = _get_brain()
            source_root = Path(os.environ.get(
                "MUSEON_SOURCE_ROOT",
                str(Path(brain.data_dir).parent.parent / "museon"),
            ))
            event_bus = None
            try:
                from museon.core.event_bus import get_event_bus
                event_bus = get_event_bus()
            except Exception as e:
                logger.debug(f"[SERVER] module import failed (degraded): {e}")

            executor = MorphenixExecutor(
                workspace=Path(brain.data_dir),
                source_root=source_root,
                pulse_db=db,
                event_bus=event_bus,
            )

            if proposal_id:
                result = executor.execute_one(proposal_id)
            else:
                result = executor.execute_approved()

            return {"success": True, **result}
        except Exception as e:
            logger.error(f"Morphenix execute API error: {e}", exc_info=True)
            return {"error": str(e)}

    @app.get("/api/morphenix/execution-log")
    async def morphenix_execution_log() -> Dict[str, Any]:
        """取得 Morphenix 執行記錄."""
        try:
            brain = _get_brain()
            log_dir = Path(brain.data_dir) / "_system" / "morphenix" / "execution_log"
            if not log_dir.exists():
                return {"logs": []}

            logs = []
            for f in sorted(log_dir.glob("*.jsonl"), reverse=True)[:7]:
                with open(f, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            try:
                                logs.append(json.loads(line))
                            except Exception as e:
                                logger.debug(f"[SERVER] JSON failed (degraded): {e}")
            return {"logs": logs[:50]}
        except Exception as e:
            return {"error": str(e)}

    # ── Routing Stats API ──

    @app.get("/api/routing/stats")
    async def routing_stats() -> Dict[str, Any]:
        """取得路由統計 — 模型分流 + Token 節省數據."""
        try:
            brain = _get_brain()
            stats_dir = brain.data_dir / "_system" / "budget"
            if not stats_dir.exists():
                return {"haiku": {}, "sonnet": {}, "savings": {}, "today_log": []}

            from datetime import timedelta

            today = datetime.now().date()
            haiku_stats = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
            sonnet_stats = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
            today_log = []

            # 讀取近 7 天的路由統計
            for d in range(7):
                date_str = (today - timedelta(days=d)).isoformat()
                fp = stats_dir / f"routing_log_{date_str}.jsonl"
                if not fp.exists():
                    continue
                for line in fp.read_text(encoding="utf-8").strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    model = entry.get("model", "sonnet")
                    inp = entry.get("input_tokens", 0)
                    out = entry.get("output_tokens", 0)

                    if "haiku" in model:
                        haiku_stats["calls"] += 1
                        haiku_stats["input_tokens"] += inp
                        haiku_stats["output_tokens"] += out
                    else:
                        sonnet_stats["calls"] += 1
                        sonnet_stats["input_tokens"] += inp
                        sonnet_stats["output_tokens"] += out

                    # 當天的 log 用於即時顯示
                    if d == 0:
                        today_log.append({
                            "ts": entry.get("ts", ""),
                            "model": model,
                            "task_type": entry.get("task_type", "unknown"),
                            "tokens": inp + out,
                        })

            # 計算 Haiku 為你省了多少（相較於全部用 Sonnet 的成本）
            haiku_actual_cost = (
                (haiku_stats["input_tokens"] / 1_000_000) * 0.80
                + (haiku_stats["output_tokens"] / 1_000_000) * 4.0
            )
            haiku_if_sonnet_cost = (
                (haiku_stats["input_tokens"] / 1_000_000) * 3.0
                + (haiku_stats["output_tokens"] / 1_000_000) * 15.0
            )
            cost_saved = haiku_if_sonnet_cost - haiku_actual_cost

            total_calls = haiku_stats["calls"] + sonnet_stats["calls"]
            haiku_ratio = (haiku_stats["calls"] / total_calls * 100) if total_calls > 0 else 0

            return {
                "haiku": haiku_stats,
                "sonnet": sonnet_stats,
                "savings": {
                    "cost_saved_usd": round(cost_saved, 4),
                    "haiku_calls": haiku_stats["calls"],
                    "total_calls": total_calls,
                    "haiku_ratio_pct": round(haiku_ratio, 1),
                    "tokens_on_haiku": haiku_stats["input_tokens"] + haiku_stats["output_tokens"],
                },
                "today_log": today_log[-20:],  # 最近 20 筆
            }
        except Exception as e:
            return {"error": str(e), "haiku": {}, "sonnet": {}, "savings": {}}

    # ── Footprint API（認知回執 / 決策軌跡 / Skill 使用）──

    @app.get("/api/footprints/cognitive_trace")
    async def footprints_cognitive(limit: int = 20) -> list:
        """取得最近的認知回執（CognitiveReceipt）."""
        try:
            brain = _get_brain()
            return brain._footprint.get_recent_cognitive(limit)
        except Exception as e:
            logger.warning("footprints_cognitive error: %s", e)
            return []

    @app.get("/api/footprints/decisions")
    async def footprints_decisions(limit: int = 20) -> list:
        """取得最近的決策軌跡（DecisionTrace）."""
        try:
            brain = _get_brain()
            return brain._footprint.get_recent_decisions(limit)
        except Exception as e:
            logger.warning("footprints_decisions error: %s", e)
            return []

    @app.get("/api/footprints/skill_usage")
    async def footprints_skill_usage(limit: int = 50) -> list:
        """取得最近的動作足跡（含 Skill 使用資訊）."""
        try:
            brain = _get_brain()
            actions = brain._footprint.get_recent_actions(limit)
            # 篩選有 skill 資訊的動作
            return [a for a in actions if a.get("action_type") == "skill_routing" or a.get("skills")]
        except Exception as e:
            logger.warning("footprints_skill_usage error: %s", e)
            return []

    # ── Token 節省明細 API ──

    @app.get("/api/savings/breakdown")
    async def savings_breakdown() -> Dict[str, Any]:
        """各策略 Token 節省明細 — 近 7 天累計."""
        try:
            brain = _get_brain()
            stats_dir = brain.data_dir / "_system" / "budget"

            from datetime import timedelta

            today = datetime.now().date()

            # ─── 1. Haiku 路由分流節省 ───
            haiku_input = 0
            haiku_output = 0
            total_input = 0
            total_output = 0
            haiku_calls = 0
            total_calls = 0

            for d in range(7):
                date_str = (today - timedelta(days=d)).isoformat()
                fp = stats_dir / f"routing_log_{date_str}.jsonl"
                if not fp.exists():
                    continue
                for line in fp.read_text(encoding="utf-8").strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    model = entry.get("model", "sonnet")
                    inp = entry.get("input_tokens", 0)
                    out = entry.get("output_tokens", 0)
                    total_input += inp
                    total_output += out
                    total_calls += 1
                    if "haiku" in model:
                        haiku_input += inp
                        haiku_output += out
                        haiku_calls += 1

            # Haiku 分流節省 = 若全用 Sonnet 的費用 - Haiku 實際費用
            haiku_actual = (haiku_input / 1e6) * 0.80 + (haiku_output / 1e6) * 4.0
            haiku_if_sonnet = (haiku_input / 1e6) * 3.0 + (haiku_output / 1e6) * 15.0
            routing_saved_usd = haiku_if_sonnet - haiku_actual
            routing_tokens = haiku_input + haiku_output
            total_tokens_all = total_input + total_output

            # ─── 2. Prompt 快取節省 ───
            cache_read_total = 0
            cache_create_total = 0
            cache_models: Dict[str, int] = {}  # model → cache_read tokens

            for d in range(7):
                date_str = (today - timedelta(days=d)).isoformat()
                fp = stats_dir / f"cache_log_{date_str}.jsonl"
                if not fp.exists():
                    continue
                for line in fp.read_text(encoding="utf-8").strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    cr = entry.get("cache_read", 0)
                    cc = entry.get("cache_create", 0)
                    m = entry.get("model", "sonnet")
                    cache_read_total += cr
                    cache_create_total += cc
                    cache_models[m] = cache_models.get(m, 0) + cr

            # 快取節省 = cache_read * (正常 input 價 - cache_read 價)
            # Sonnet: $3.0 → cache_read $0.30, saving $2.70/MTok
            # Haiku: $0.80 → cache_read $0.08, saving $0.72/MTok
            cache_saved_usd = 0.0
            for m, tokens in cache_models.items():
                if "haiku" in m:
                    cache_saved_usd += (tokens / 1e6) * 0.72
                else:
                    cache_saved_usd += (tokens / 1e6) * 2.70
            cache_tokens = cache_read_total

            # ─── 3. 三層壓縮估算 ───
            # LayeredContent: essence=10%, compact=30%, full=100%
            # 估算: 每次 skill 調用平均壓縮 ~2000 tokens (full→compact 節省 ~70%)
            # 根據 routing log 中 skill 類型的呼叫次數估算
            skill_calls = 0
            for d in range(7):
                date_str = (today - timedelta(days=d)).isoformat()
                fp = stats_dir / f"routing_log_{date_str}.jsonl"
                if not fp.exists():
                    continue
                for line in fp.read_text(encoding="utf-8").strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    if entry.get("task_type") == "skill":
                        skill_calls += 1

            # 估算每次 skill 節省 ~1400 tokens (full 2000 → compact 600)
            compress_tokens = skill_calls * 1400
            # 成本估算（假設 Sonnet input 價）
            compress_saved_usd = (compress_tokens / 1e6) * 3.0

            # ─── 4. 對話壓縮（滑動視窗）───
            # 每輪對話約 ~800 tokens，保留 20 輪 = 16000 tokens
            # 若平均對話 30 輪，壓縮掉 10 輪 = ~8000 tokens
            # 近 7 天按呼叫次數粗估
            conv_compress_tokens = max(0, total_calls - 20) * 800 if total_calls > 20 else 0
            conv_compress_usd = (conv_compress_tokens / 1e6) * 3.0

            # ─── 5. 反射弧攔截節省 ───
            reflex_hits = 0
            reflex_tokens = 0
            for d in range(7):
                date_str = (today - timedelta(days=d)).isoformat()
                fp = stats_dir / f"reflex_log_{date_str}.jsonl"
                if not fp.exists():
                    continue
                for line in fp.read_text(encoding="utf-8").strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    reflex_hits += 1
                    reflex_tokens += entry.get("saved_tokens_est", 2000)
            # 反射弧節省 = 繞過 LLM，省下 Sonnet input+output 成本
            reflex_saved_usd = (reflex_tokens / 1e6) * 3.0

            # ─── 彙總 ───
            total_saved_usd = routing_saved_usd + cache_saved_usd + compress_saved_usd + conv_compress_usd + reflex_saved_usd
            total_tokens_saved = routing_tokens + cache_tokens + compress_tokens + conv_compress_tokens + reflex_tokens
            total_cost = (total_input / 1e6) * 3.0 + (total_output / 1e6) * 15.0  # 近似總成本

            strategies = [
                {
                    "name": "Haiku 路由分流",
                    "icon": "🍃",
                    "color": "#8b5cf6",
                    "tokens_saved": routing_tokens,
                    "cost_saved_usd": round(routing_saved_usd, 4),
                    "percentage": round((routing_tokens / total_tokens_saved * 100) if total_tokens_saved > 0 else 0, 1),
                    "status_text": f"{haiku_calls}/{total_calls} 次分流" if haiku_calls > 0 else "尚未觸發分流",
                },
                {
                    "name": "Prompt 快取",
                    "icon": "⚡",
                    "color": "#f59e0b",
                    "tokens_saved": cache_tokens,
                    "cost_saved_usd": round(cache_saved_usd, 4),
                    "percentage": round((cache_tokens / total_tokens_saved * 100) if total_tokens_saved > 0 else 0, 1),
                    "status_text": f"快取命中 {cache_read_total:,} tok" if cache_read_total > 0 else "尚未產生快取",
                },
                {
                    "name": "三層壓縮",
                    "icon": "📦",
                    "color": "#06b6d4",
                    "tokens_saved": compress_tokens,
                    "cost_saved_usd": round(compress_saved_usd, 4),
                    "percentage": round((compress_tokens / total_tokens_saved * 100) if total_tokens_saved > 0 else 0, 1),
                    "status_text": f"~{skill_calls} 次壓縮" if skill_calls > 0 else "尚未使用技能",
                },
                {
                    "name": "對話滑動視窗",
                    "icon": "🔄",
                    "color": "#10b981",
                    "tokens_saved": conv_compress_tokens,
                    "cost_saved_usd": round(conv_compress_usd, 4),
                    "percentage": round((conv_compress_tokens / total_tokens_saved * 100) if total_tokens_saved > 0 else 0, 1),
                    "status_text": f"壓縮 {max(0, total_calls - 20)} 輪" if conv_compress_tokens > 0 else "保留最近 20 輪",
                },
                {
                    "name": "反射弧攔截",
                    "icon": "🧠",
                    "color": "#ef4444",
                    "tokens_saved": reflex_tokens,
                    "cost_saved_usd": round(reflex_saved_usd, 4),
                    "percentage": round((reflex_tokens / total_tokens_saved * 100) if total_tokens_saved > 0 else 0, 1),
                    "status_text": f"{reflex_hits} 次攔截" if reflex_hits > 0 else "尚未配置模板",
                },
            ]

            return {
                "total_saved_usd": round(total_saved_usd, 4),
                "total_tokens_saved": total_tokens_saved,
                "total_cost_usd": round(total_cost, 4),
                "strategies": strategies,
            }
        except Exception as e:
            logger.error(f"Savings breakdown failed: {e}", exc_info=True)
            return {"error": str(e), "total_saved_usd": 0, "total_tokens_saved": 0, "strategies": []}

    # ── Nightly Pipeline API ──

    @app.get("/api/nightly/status")
    async def nightly_status() -> Dict[str, Any]:
        """取得最近一次夜間整合狀態 — 純 CPU, 零 Token."""
        try:
            brain = _get_brain()
            report_path = brain.data_dir / "_system" / "state" / "nightly_report.json"
            if not report_path.exists():
                return {
                    "status": "never_run",
                    "last_run": None,
                    "next_scheduled": "03:00",
                }
            report = json.loads(report_path.read_text(encoding="utf-8"))
            summary = report.get("summary", {})
            return {
                "status": "ok" if summary.get("error", 0) == 0 else "warning",
                "completed_at": report.get("completed_at"),
                "mode": report.get("mode", "full"),
                "elapsed_seconds": report.get("elapsed_seconds", 0),
                "summary": summary,
                "steps": report.get("steps", {}),
                "errors": report.get("errors", []),
                "next_scheduled": "03:00",
            }
        except Exception as e:
            return {"error": str(e), "status": "unknown"}

    @app.post("/api/nightly/run")
    async def nightly_run_manual() -> Dict[str, Any]:
        """手動觸發凌晨整合管線 — 用於測試."""
        try:
            brain = _get_brain()
            from museon.nightly.nightly_pipeline import NightlyPipeline
            from museon.core.event_bus import get_event_bus

            event_bus = get_event_bus()
            # WP-03: 注入 DendriticScorer 健康閘門
            _gov = getattr(app.state, "governor", None)
            _dendritic = getattr(_gov, "_dendritic", None) if _gov else None
            # 合約 4：補齊 memory_manager + heartbeat_focus（與生產端一致）
            _memory_manager = getattr(brain, "memory_manager", None) or getattr(brain, "_memory_manager", None)
            _heartbeat_focus = getattr(app.state, "heartbeat_focus", None)
            pipeline = NightlyPipeline(
                workspace=brain.data_dir,
                memory_manager=_memory_manager,
                heartbeat_focus=_heartbeat_focus,
                event_bus=event_bus,
                brain=brain,
                dendritic_scorer=_dendritic,
            )
            report = pipeline.run()
            return {"triggered": True, "report": report}
        except Exception as e:
            return {"error": str(e), "triggered": False}

    # ── Activity Log + Daily Summary API ──

    @app.get("/api/activity/recent")
    async def activity_recent() -> Dict[str, Any]:
        """取得最近活動日誌（最新 20 筆）."""
        try:
            brain = _get_brain()
            from museon.core.activity_logger import ActivityLogger
            al = ActivityLogger(data_dir=str(brain.data_dir))
            events = al.recent(limit=20)
            return {"events": events, "count": len(events)}
        except Exception as e:
            return {"events": [], "count": 0, "error": str(e)}

    @app.get("/api/daily-summary/{date}")
    async def daily_summary(date: str) -> Dict[str, Any]:
        """取得指定日期的每日摘要."""
        try:
            brain = _get_brain()
            summary_path = brain.data_dir / "daily_summaries" / f"{date}.json"
            if not summary_path.exists():
                return {"error": "尚無該日摘要", "date": date}
            return json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception as e:
            return {"error": str(e), "date": date}

    @app.get("/api/daily-summaries")
    async def daily_summaries_list() -> Dict[str, Any]:
        """列出所有可用的每日摘要日期."""
        try:
            brain = _get_brain()
            summaries_dir = brain.data_dir / "daily_summaries"
            if not summaries_dir.exists():
                return {"dates": [], "count": 0}
            dates = sorted(
                [f.stem for f in summaries_dir.glob("*.json")],
                reverse=True,
            )
            return {"dates": dates, "count": len(dates)}
        except Exception as e:
            return {"dates": [], "count": 0, "error": str(e)}

    # ── Skills API ──

    @app.get("/api/skills/list")
    async def skills_list() -> Dict[str, Any]:
        """列出所有技能 + lifecycle + stats — 零 token."""
        try:
            brain = _get_brain()
            from museon.core.skill_manager import SkillManager
            mgr = SkillManager(workspace=brain.data_dir)
            skills = mgr.list_skills()
            return {"skills": skills, "count": len(skills)}
        except Exception as e:
            return {"error": str(e), "skills": [], "count": 0}

    @app.get("/api/skills/detail/{name}")
    async def skills_detail(name: str) -> Dict[str, Any]:
        """單一技能詳細資訊 — 零 token."""
        try:
            brain = _get_brain()
            from museon.core.skill_manager import SkillManager
            mgr = SkillManager(workspace=brain.data_dir)
            detail = mgr.get_skill(name)
            if detail is None:
                return {"error": "skill_not_found"}
            return detail
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/skills-status")
    async def skills_status() -> Dict[str, Any]:
        """技能彙總（by lifecycle + total uses）— 零 token."""
        try:
            brain = _get_brain()
            from museon.core.skill_manager import SkillManager
            mgr = SkillManager(workspace=brain.data_dir)
            skills = mgr.list_skills()
            by_lifecycle: Dict[str, int] = {}
            total_uses = 0
            for s in skills:
                lc = s.get("lifecycle", "unknown")
                by_lifecycle[lc] = by_lifecycle.get(lc, 0) + 1
                total_uses += s.get("use_count", 0)
            return {
                "total": len(skills),
                "by_lifecycle": by_lifecycle,
                "total_uses": total_uses,
            }
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/skills/scan")
    async def skills_scan() -> Dict[str, Any]:
        """觸發全部安全掃描 — 零 token."""
        try:
            brain = _get_brain()
            from museon.core.skill_manager import SkillManager
            mgr = SkillManager(workspace=brain.data_dir)
            return await asyncio.to_thread(mgr.scan_all)
        except Exception as e:
            return {"error": str(e)}

    # ── Multi-Agent API ──

    @app.get("/api/multiagent/departments")
    async def multiagent_departments() -> Dict[str, Any]:
        """列出全部 10 部門 — 零 token."""
        try:
            from museon.multiagent.department_config import get_all_departments
            depts = get_all_departments()
            result = []
            for dept_id, dept in depts.items():
                result.append({
                    "dept_id": dept.dept_id,
                    "name": dept.name,
                    "emoji": dept.emoji,
                    "role": dept.role,
                    "flywheel_order": dept.flywheel_order,
                    "next_dept": dept.next_dept,
                })
            return {"departments": result, "count": len(result)}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/multiagent/status")
    async def multiagent_status() -> Dict[str, Any]:
        """飛輪狀態 — 當前部門 + 切換統計."""
        try:
            brain = _get_brain()
            if not brain._multiagent_enabled or not brain._context_switcher:
                return {"enabled": False}
            stats = brain._context_switcher.get_stats()
            stats["enabled"] = True
            return stats
        except Exception as e:
            return {"error": str(e), "enabled": False}

    @app.get("/api/multiagent/assets")
    async def multiagent_assets() -> Dict[str, Any]:
        """共享資產列表 — 零 token."""
        try:
            brain = _get_brain()
            from museon.multiagent.shared_assets import SharedAssetLibrary
            from museon.core.event_bus import get_event_bus
            lib = SharedAssetLibrary(workspace=brain.data_dir, event_bus=get_event_bus())
            assets = lib.list_all()
            return {
                "assets": [
                    {
                        "asset_id": a.asset_id,
                        "title": a.title,
                        "asset_type": a.asset_type,
                        "source_dept": a.source_dept,
                        "quality_score": round(a.quality_score, 4),
                        "gate_level": a.gate_level,
                        "created_at": a.created_at,
                    }
                    for a in assets
                ],
                "count": len(assets),
            }
        except Exception as e:
            return {"error": str(e), "assets": [], "count": 0}

    @app.post("/api/multiagent/route-test")
    async def multiagent_route_test(request: Request) -> Dict[str, Any]:
        """路由測試（除錯用）— 零 token."""
        try:
            body = await request.json()
            message = body.get("message", "")
            from museon.multiagent.okr_router import route, soft_route
            dept_id, confidence = route(message)
            scores = soft_route(message)
            return {
                "message": message,
                "routed_to": dept_id,
                "confidence": confidence,
                "flywheel_scores": scores,
            }
        except Exception as e:
            return {"error": str(e)}

    # ── Dify API ──

    @app.get("/api/tools/dify/status")
    async def dify_status() -> Dict[str, Any]:
        """Dify 工作流引擎連線狀態 — 零 token."""
        try:
            from museon.tools.mcp_dify import check_health
            return check_health()
        except Exception as e:
            return {"healthy": False, "error": str(e), "configured": False}

    @app.get("/api/tools/dify/tools")
    async def dify_tools() -> Dict[str, Any]:
        """列出 Dify MCP 可用工具 — 零 token."""
        try:
            from museon.tools.mcp_dify import DIFY_TOOLS
            return {"tools": DIFY_TOOLS, "count": len(DIFY_TOOLS)}
        except Exception as e:
            return {"error": str(e), "tools": [], "count": 0}

    # ── Dispatch API ──

    @app.get("/api/dispatch/status")
    async def dispatch_status() -> Dict[str, Any]:
        """取得活躍 dispatch plans 狀態 — 零 token."""
        try:
            brain = _get_brain()
            active_dir = brain.data_dir / "dispatch" / "active"
            plans = []
            if active_dir.exists():
                for f in sorted(active_dir.glob("*.json")):
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        plans.append({
                            "plan_id": data.get("plan_id"),
                            "status": data.get("status"),
                            "execution_mode": data.get("execution_mode"),
                            "task_count": len(data.get("tasks", [])),
                            "result_count": len(data.get("results", [])),
                            "created_at": data.get("created_at"),
                        })
                    except Exception as e:
                        logger.debug(f"[SERVER] file stat failed (degraded): {e}")
            return {"active_plans": plans, "count": len(plans)}
        except Exception as e:
            return {"error": str(e), "active_plans": [], "count": 0}

    @app.get("/api/dispatch/history")
    async def dispatch_history() -> Dict[str, Any]:
        """最近 20 筆完成/失敗的 dispatch — 零 token."""
        try:
            brain = _get_brain()
            dispatch_dir = brain.data_dir / "dispatch"
            entries = []
            for subdir in ("completed", "failed"):
                target = dispatch_dir / subdir
                if not target.exists():
                    continue
                for f in sorted(
                    target.glob("*.json"), reverse=True,
                ):
                    try:
                        data = json.loads(
                            f.read_text(encoding="utf-8"),
                        )
                        entries.append({
                            "plan_id": data.get("plan_id"),
                            "status": data.get("status"),
                            "execution_mode": data.get(
                                "execution_mode",
                            ),
                            "user_request": (
                                data.get("user_request", "")[:100]
                            ),
                            "task_count": len(
                                data.get("tasks", []),
                            ),
                            "created_at": data.get("created_at"),
                            "completed_at": data.get(
                                "completed_at",
                            ),
                            "error_message": data.get(
                                "error_message",
                            ),
                            "total_token_usage": data.get(
                                "total_token_usage", {},
                            ),
                        })
                    except Exception as e:
                        logger.debug(f"[SERVER] token failed (degraded): {e}")
            # 按 created_at 倒序，取前 20
            entries.sort(
                key=lambda x: x.get("created_at", ""),
                reverse=True,
            )
            return {
                "history": entries[:20],
                "count": len(entries[:20]),
            }
        except Exception as e:
            return {"error": str(e), "history": [], "count": 0}

    # ── 工具兵器庫端點 ──

    @app.get("/api/tools/list")
    async def tools_list():
        """列出所有工具（含設定 + 狀態）."""
        try:
            from museon.tools.tool_registry import ToolRegistry
            registry = ToolRegistry(workspace=_get_brain().data_dir)
            return {
                "tools": registry.list_tools(),
                "count": len(registry.list_tools()),
            }
        except Exception as e:
            return {"error": str(e), "tools": [], "count": 0}

    @app.get("/api/tools/detail/{name}")
    async def tools_detail(name: str):
        """取得單一工具詳細資訊."""
        try:
            from museon.tools.tool_registry import ToolRegistry
            registry = ToolRegistry(workspace=_get_brain().data_dir)
            tool = registry.get_tool(name)
            if not tool:
                return {"error": f"Tool '{name}' not found"}
            return tool
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/tools-status")
    async def tools_status():
        """工具彙總狀態."""
        try:
            from museon.tools.tool_registry import ToolRegistry
            registry = ToolRegistry(workspace=_get_brain().data_dir)
            return registry.get_status_summary()
        except Exception as e:
            return {"error": str(e), "total": 0, "installed": 0, "enabled": 0}

    @app.post("/api/tools/toggle")
    async def tools_toggle(payload: Dict[str, Any] = {}):
        """切換工具 on/off.

        Body: {"name": "searxng", "enabled": true}
        """
        name = payload.get("name", "")
        enabled = payload.get("enabled", False)
        try:
            from museon.tools.tool_registry import ToolRegistry
            registry = ToolRegistry(workspace=_get_brain().data_dir)
            return registry.toggle_tool(name, enabled)
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/tools/health")
    async def tools_health():
        """執行所有工具健康檢查."""
        try:
            from museon.tools.tool_registry import ToolRegistry
            registry = ToolRegistry(workspace=_get_brain().data_dir)
            return registry.check_all_health()
        except Exception as e:
            return {"error": str(e)}

    # ── Docker 狀態 ──

    @app.get("/api/tools/docker-status")
    async def docker_status():
        """檢查 Docker 安裝與 daemon 狀態.

        Returns: {"installed": bool, "daemon_running": bool, "error": str,
                  "docker_tools": [...]}
        """
        try:
            from museon.tools.tool_registry import ToolRegistry
            registry = ToolRegistry(
                workspace=_get_brain().data_dir, auto_detect=False
            )
            status = registry.check_docker_status()
            status["docker_tools"] = registry.get_docker_dependent_tools()
            return status
        except Exception as e:
            return {
                "installed": False,
                "daemon_running": False,
                "error": str(e),
                "docker_tools": [],
            }

    @app.post("/api/tools/docker-start")
    async def docker_start():
        """嘗試啟動 Docker Desktop.

        Returns: {"success": bool, "message": str}
        """
        try:
            from museon.tools.tool_registry import ToolRegistry
            registry = ToolRegistry(
                workspace=_get_brain().data_dir, auto_detect=False
            )
            return registry.ensure_docker_running(timeout=60)
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "was_already_running": False,
            }

    # ── 工具安裝管理 ──

    # 全域安裝進度追蹤（thread-safe）
    _tool_install_progress: Dict[str, Dict] = {}
    _tool_install_lock = threading.Lock()

    @app.post("/api/tools/install")
    async def tools_install(payload: Dict[str, Any] = {}):
        """安裝單一工具（背景執行）.

        Body: {"name": "searxng"}
        Returns: {"started": true, "name": "searxng"}
        """
        name = payload.get("name", "")
        if not name:
            return {"started": False, "error": "缺少工具名稱"}

        # 檢查是否已在安裝中
        with _tool_install_lock:
            if name in _tool_install_progress and \
               _tool_install_progress[name].get("status") == "installing":
                return {"started": False, "error": "已在安裝中", "name": name}

            _tool_install_progress[name] = {
                "status": "installing",
                "progress": 0,
                "message": "準備安裝...",
                "name": name,
            }

        def _run_install():
            try:
                from museon.tools.tool_registry import ToolRegistry
                registry = ToolRegistry(workspace=_get_brain().data_dir)

                def _on_progress(pct, msg):
                    with _tool_install_lock:
                        _tool_install_progress[name] = {
                            "status": "installing",
                            "progress": pct,
                            "message": msg,
                            "name": name,
                        }

                result = registry.install_tool(name, progress_cb=_on_progress)

                with _tool_install_lock:
                    if result.get("success"):
                        _tool_install_progress[name] = {
                            "status": "installed",
                            "progress": 100,
                            "message": "安裝完成",
                            "name": name,
                            "success": True,
                        }
                    else:
                        # 優先使用 Docker 專用錯誤訊息
                        error_msg = (
                            result.get("error")
                            or result.get("reason")
                            or "安裝失敗"
                        )
                        _tool_install_progress[name] = {
                            "status": "failed",
                            "progress": 0,
                            "message": error_msg,
                            "name": name,
                            "success": False,
                            "docker_issue": result.get("docker_issue", False),
                        }
            except Exception as e:
                with _tool_install_lock:
                    _tool_install_progress[name] = {
                        "status": "failed",
                        "progress": 0,
                        "message": str(e)[:200],
                        "name": name,
                        "success": False,
                    }

        thread = threading.Thread(target=_run_install, daemon=True)
        thread.start()
        return {"started": True, "name": name}

    @app.get("/api/tools/install-progress/{name}")
    async def tools_install_progress(name: str):
        """查詢工具安裝進度.

        Returns: {"status": "installing", "progress": 50, "message": "拉取 Docker Image"}
        """
        with _tool_install_lock:
            info = _tool_install_progress.get(name)
        if info:
            return info
        # 檢查 registry 狀態
        try:
            from museon.tools.tool_registry import ToolRegistry
            registry = ToolRegistry(workspace=_get_brain().data_dir)
            tool = registry.get_tool(name)
            if tool and tool.get("installed"):
                return {
                    "status": "installed", "progress": 100,
                    "message": "已安裝", "name": name, "success": True,
                }
            return {
                "status": "idle", "progress": 0,
                "message": "未安裝", "name": name,
            }
        except Exception:
            return {
                "status": "idle", "progress": 0,
                "message": "未安裝", "name": name,
            }

    @app.post("/api/tools/install-batch")
    async def tools_install_batch(payload: Dict[str, Any] = {}):
        """批次安裝多個工具（依序背景執行）.

        Body: {"tools": ["searxng", "qdrant", "firecrawl"]}
        Returns: {"started": true, "tools": [...], "count": 3}
        """
        tool_names = payload.get("tools", [])
        if not tool_names:
            return {"started": False, "error": "缺少工具清單"}

        with _tool_install_lock:
            for name in tool_names:
                _tool_install_progress[name] = {
                    "status": "queued",
                    "progress": 0,
                    "message": "排隊中...",
                    "name": name,
                }

        def _run_batch():
            from museon.tools.tool_registry import ToolRegistry
            registry = ToolRegistry(workspace=_get_brain().data_dir)

            for name in tool_names:
                with _tool_install_lock:
                    _tool_install_progress[name] = {
                        "status": "installing",
                        "progress": 0,
                        "message": "開始安裝...",
                        "name": name,
                    }

                def _on_progress(pct, msg, _name=name):
                    with _tool_install_lock:
                        _tool_install_progress[_name] = {
                            "status": "installing",
                            "progress": pct,
                            "message": msg,
                            "name": _name,
                        }

                try:
                    result = registry.install_tool(name, progress_cb=_on_progress)
                    with _tool_install_lock:
                        if result.get("success"):
                            _tool_install_progress[name] = {
                                "status": "installed",
                                "progress": 100,
                                "message": "安裝完成",
                                "name": name,
                                "success": True,
                            }
                        else:
                            _tool_install_progress[name] = {
                                "status": "failed",
                                "progress": 0,
                                "message": result.get("reason", "安裝失敗"),
                                "name": name,
                                "success": False,
                            }
                except Exception as e:
                    with _tool_install_lock:
                        _tool_install_progress[name] = {
                            "status": "failed",
                            "progress": 0,
                            "message": str(e)[:200],
                            "name": name,
                            "success": False,
                        }

        thread = threading.Thread(target=_run_batch, daemon=True)
        thread.start()
        return {"started": True, "tools": tool_names, "count": len(tool_names)}

    # ── Setup Wizard（安裝精靈）──

    @app.get("/api/setup/wizard")
    async def setup_wizard():
        """取得安裝精靈的完整步驟與當前進度.

        Dashboard 前端根據此 API 呈現 step-by-step 安裝引導。
        每個步驟包含：prerequisites、要安裝的工具、當前狀態。

        Returns:
            {
                "completed": bool,          # 所有必要步驟是否完成
                "current_step": int,        # 當前應該執行的步驟 (0-based)
                "steps": [...],             # 完整步驟清單
                "mcp_servers_connected": int # 已連線 MCP 伺服器數
            }
        """
        try:
            from museon.tools.tool_registry import ToolRegistry
            registry = ToolRegistry(workspace=_get_brain().data_dir)

            docker_status = registry.check_docker_status()
            tool_list = registry.list_tools()
            tool_states = {t["name"]: t for t in tool_list}

            # Step 0: Docker Desktop
            docker_step = {
                "step": 0,
                "title": "Docker Desktop",
                "description": "Docker 是 4 個核心工具的運行環境",
                "category": "prerequisite",
                "required": True,
                "status": "completed" if docker_status["daemon_running"] else (
                    "ready" if docker_status["installed"] else "missing"
                ),
                "action": (
                    None if docker_status["daemon_running"]
                    else "start" if docker_status["installed"]
                    else "install"
                ),
                "action_label": (
                    None if docker_status["daemon_running"]
                    else "啟動 Docker Desktop" if docker_status["installed"]
                    else "安裝 Docker Desktop"
                ),
                "action_url": (
                    None if docker_status["installed"]
                    else "https://www.docker.com/products/docker-desktop/"
                ),
                "detail": docker_status,
            }

            # Step 1: Core Trio (SearXNG + Qdrant + Firecrawl)
            core_tools = ["searxng", "qdrant", "firecrawl"]
            core_all_ok = all(
                tool_states.get(t, {}).get("installed") and
                tool_states.get(t, {}).get("healthy")
                for t in core_tools
            )
            core_any_installed = any(
                tool_states.get(t, {}).get("installed")
                for t in core_tools
            )
            core_step = {
                "step": 1,
                "title": "核心三件套",
                "description": "搜尋引擎 + 向量記憶庫 + 深度爬取",
                "category": "core",
                "required": True,
                "status": (
                    "completed" if core_all_ok
                    else "partial" if core_any_installed
                    else "pending"
                ),
                "action": None if core_all_ok else "install_batch",
                "action_label": None if core_all_ok else "一鍵安裝核心三件套",
                "tools": [
                    {
                        "name": t,
                        "display_name": tool_states.get(t, {}).get("display_name", t),
                        "emoji": tool_states.get(t, {}).get("emoji", ""),
                        "installed": tool_states.get(t, {}).get("installed", False),
                        "healthy": tool_states.get(t, {}).get("healthy", False),
                        "description": tool_states.get(t, {}).get("description", ""),
                    }
                    for t in core_tools
                ],
                "blocked_by": 0 if not docker_status["daemon_running"] else None,
            }

            # Step 2: Perception (Whisper + PaddleOCR + Kokoro)
            perception_tools = ["whisper", "paddleocr", "kokoro"]
            perception_all_ok = all(
                tool_states.get(t, {}).get("installed")
                for t in perception_tools
            )
            perception_any_installed = any(
                tool_states.get(t, {}).get("installed")
                for t in perception_tools
            )
            perception_step = {
                "step": 2,
                "title": "感知能力",
                "description": "語音轉文字 + 文字辨識 + 語音合成",
                "category": "perception",
                "required": False,
                "status": (
                    "completed" if perception_all_ok
                    else "partial" if perception_any_installed
                    else "pending"
                ),
                "action": None if perception_all_ok else "install_batch",
                "action_label": None if perception_all_ok else "安裝感知能力套件",
                "tools": [
                    {
                        "name": t,
                        "display_name": tool_states.get(t, {}).get("display_name", t),
                        "emoji": tool_states.get(t, {}).get("emoji", ""),
                        "installed": tool_states.get(t, {}).get("installed", False),
                        "healthy": tool_states.get(t, {}).get("healthy", False),
                        "description": tool_states.get(t, {}).get("description", ""),
                        "docker_required": tool_states.get(t, {}).get("install_type") in ("docker", "compose"),
                    }
                    for t in perception_tools
                ],
                "blocked_by": None,  # Whisper/Kokoro 不需 Docker
            }

            # Step 3: MCP Servers
            mcp_connected = 0
            try:
                brain = _get_brain()
                if brain._tool_executor and brain._tool_executor._mcp_connector:
                    conn = brain._tool_executor._mcp_connector._connections
                    mcp_connected = sum(
                        1 for c in conn.values()
                        if c.status == "connected"
                    )
            except Exception as e:
                logger.debug(f"[SERVER] file stat failed (degraded): {e}")

            mcp_step = {
                "step": 3,
                "title": "MCP 外部連接",
                "description": f"已連線 {mcp_connected} 個外部服務（可隨時在 Settings 頁面擴充）",
                "category": "mcp",
                "required": False,
                "status": "completed" if mcp_connected >= 3 else (
                    "partial" if mcp_connected > 0 else "pending"
                ),
                "action": "navigate",
                "action_label": "前往 Settings 連接更多服務",
                "mcp_connected": mcp_connected,
            }

            steps = [docker_step, core_step, perception_step, mcp_step]

            # 決定當前步驟
            current_step = 0
            for s in steps:
                if s["status"] != "completed":
                    current_step = s["step"]
                    break
            else:
                current_step = len(steps)  # 全部完成

            all_required_done = all(
                s["status"] == "completed"
                for s in steps if s.get("required")
            )

            return {
                "completed": all_required_done,
                "current_step": current_step,
                "steps": steps,
                "mcp_servers_connected": mcp_connected,
            }

        except Exception as e:
            logger.error(f"Setup wizard error: {e}", exc_info=True)
            return {
                "completed": False,
                "current_step": 0,
                "steps": [],
                "error": str(e),
            }

    @app.post("/api/setup/install-core")
    async def setup_install_core():
        """安裝精靈：一鍵安裝核心三件套（Docker 前置檢查 + 批次安裝）.

        自動處理：
        1. 檢查 Docker → 嘗試自動啟動
        2. 依序安裝 SearXNG → Qdrant → Firecrawl
        """
        core_tools = ["searxng", "qdrant", "firecrawl"]

        with _tool_install_lock:
            for name in core_tools:
                _tool_install_progress[name] = {
                    "status": "queued",
                    "progress": 0,
                    "message": "排隊中...",
                    "name": name,
                }

        def _run_core_install():
            from museon.tools.tool_registry import ToolRegistry
            registry = ToolRegistry(workspace=_get_brain().data_dir)

            # Docker 前置檢查（只做一次）
            docker_result = registry.ensure_docker_running(timeout=60)
            if not docker_result["success"]:
                for name in core_tools:
                    with _tool_install_lock:
                        _tool_install_progress[name] = {
                            "status": "failed",
                            "progress": 0,
                            "message": docker_result["message"],
                            "name": name,
                            "success": False,
                            "docker_issue": True,
                        }
                return

            for name in core_tools:
                with _tool_install_lock:
                    _tool_install_progress[name] = {
                        "status": "installing",
                        "progress": 0,
                        "message": "開始安裝...",
                        "name": name,
                    }

                def _on_progress(pct, msg, _name=name):
                    with _tool_install_lock:
                        _tool_install_progress[_name] = {
                            "status": "installing",
                            "progress": pct,
                            "message": msg,
                            "name": _name,
                        }

                try:
                    result = registry.install_tool(name, progress_cb=_on_progress)
                    with _tool_install_lock:
                        if result.get("success"):
                            _tool_install_progress[name] = {
                                "status": "installed",
                                "progress": 100,
                                "message": "安裝完成",
                                "name": name,
                                "success": True,
                            }
                        else:
                            _tool_install_progress[name] = {
                                "status": "failed",
                                "progress": 0,
                                "message": result.get("error") or result.get("reason", "安裝失敗"),
                                "name": name,
                                "success": False,
                                "docker_issue": result.get("docker_issue", False),
                            }
                except Exception as e:
                    with _tool_install_lock:
                        _tool_install_progress[name] = {
                            "status": "failed",
                            "progress": 0,
                            "message": str(e)[:200],
                            "name": name,
                            "success": False,
                        }

        thread = threading.Thread(target=_run_core_install, daemon=True)
        thread.start()
        return {
            "started": True,
            "tools": core_tools,
            "message": "正在安裝核心三件套...",
        }

    @app.get("/api/tools/discoveries")
    async def tools_discoveries():
        """取得最近工具發現結果."""
        try:
            from museon.tools.tool_discovery import ToolDiscovery
            discovery = ToolDiscovery(workspace=_get_brain().data_dir)
            return discovery.get_latest_discoveries()
        except Exception as e:
            return {"error": str(e), "searched": 0, "recommended": []}

    # ── VectorBridge 端點 ──

    @app.get("/api/vector/status")
    async def vector_status():
        """Qdrant 可用性 + 各 collection 統計."""
        try:
            from museon.vector.vector_bridge import VectorBridge
            from museon.core.event_bus import get_event_bus
            vb = VectorBridge(workspace=_get_brain().data_dir, event_bus=get_event_bus())
            available = vb.is_available()
            stats = vb.get_stats() if available else {}
            return {
                "available": available,
                "collections": stats,
            }
        except Exception as e:
            return {"available": False, "error": str(e), "collections": {}}

    @app.post("/api/vector/search")
    async def vector_search(payload: Dict[str, Any] = {}):
        """語義搜尋."""
        collection = payload.get("collection", "memories")
        query = payload.get("query", "")
        limit = payload.get("limit", 10)

        if not query:
            return {"error": "query is required", "results": []}

        try:
            from museon.vector.vector_bridge import VectorBridge
            from museon.core.event_bus import get_event_bus
            vb = VectorBridge(workspace=_get_brain().data_dir, event_bus=get_event_bus())
            results = vb.hybrid_search(collection, query, limit=limit)
            return {"results": results, "count": len(results)}
        except Exception as e:
            return {"error": str(e), "results": []}

    @app.post("/api/vector/reindex")
    async def vector_reindex(payload: Dict[str, Any] = {}):
        """觸發全量重建索引（ensure collections + reindex all）."""
        try:
            from museon.vector.vector_bridge import VectorBridge
            from museon.core.event_bus import get_event_bus
            vb = VectorBridge(workspace=_get_brain().data_dir, event_bus=get_event_bus())
            collections_result = vb.ensure_collections()
            reindex_result = vb.reindex_all()
            return {"success": True, "collections": collections_result, **reindex_result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── ExecutionSandbox 端點 ──

    @app.get("/api/sandbox/status")
    async def sandbox_status():
        """Docker 沙盒可用性 + 審計統計."""
        try:
            from museon.security.execution_sandbox import ExecutionSandbox
            sandbox = ExecutionSandbox(workspace=_get_brain().data_dir)
            return {
                "docker_available": sandbox.is_docker_available(),
                "audit_stats": sandbox.get_audit_stats(),
            }
        except Exception as e:
            return {"docker_available": False, "error": str(e)}

    @app.post("/api/sandbox/execute")
    async def sandbox_execute(payload: Dict[str, Any] = {}):
        """在 Docker 沙盒中執行程式碼."""
        code = payload.get("code", "")
        language = payload.get("language", "python")
        timeout = payload.get("timeout", 30)

        if not code:
            return {"success": False, "error": "code is required"}

        try:
            from museon.security.execution_sandbox import ExecutionSandbox
            sandbox = ExecutionSandbox(workspace=_get_brain().data_dir)
            return await sandbox.execute(code, language=language, timeout=timeout)
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 主動互動測試端點 ──

    @app.post("/api/proactive/test")
    async def test_proactive_push(payload: Dict[str, Any] = {}):
        """手動觸發主動自省或直接推送測試訊息.

        Body:
          {"mode": "think"}  — LLM 自省，自行判斷是否推送
          {"mode": "push", "message": "..."}  — 直接推送指定訊息
        """
        mode = payload.get("mode", "think")

        # 直接推送模式
        if mode == "push":
            message = payload.get("message", "")
            if not message:
                return {"error": "message is required for push mode"}
            adapter = getattr(app.state, "telegram_adapter", None)
            if not adapter:
                return {"error": "Telegram adapter not initialized"}
            sent = await adapter.push_notification(message)
            return {"pushed": True, "sent_count": sent, "message": message}

        # LLM 自省模式
        bridge = getattr(app.state, "proactive_bridge", None)
        if not bridge:
            return {"error": "ProactiveBridge not initialized"}
        try:
            result = await bridge.proactive_think()
            return {
                "pushed": result["pushed"],
                "reason": result["reason"],
                "response_preview": result["response"][:200] if result["response"] else "",
                "daily_push_count": bridge.daily_push_count,
            }
        except Exception as e:
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # WEE Status API
    # ═══════════════════════════════════════════

    @app.get("/api/wee/status")
    async def wee_status(user_id: str = "boss"):
        """取得 WEE 自我迭代引擎狀態.

        Query params:
          user_id: 用戶 ID（預設 boss）
        """
        try:
            from museon.evolution.wee_engine import get_wee_engine
            from museon.core.event_bus import get_event_bus

            brain = _get_brain()
            event_bus = get_event_bus()
            wee = get_wee_engine(
                user_id=user_id,
                workspace=brain.data_dir,
                event_bus=event_bus,
                memory_manager=getattr(brain, "memory_manager", None),
            )
            return wee.get_status()
        except Exception as e:
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # Self-Diagnosis API
    # ═══════════════════════════════════════════

    @app.get("/api/self-diagnosis")
    async def self_diagnosis_check():
        """執行自我診斷 — 純 CPU, 零 Token."""
        try:
            from museon.doctor.self_diagnosis import SelfDiagnosis
            diag = SelfDiagnosis(data_dir=str(_get_brain().data_dir))
            report = diag.diagnose(auto_repair=True)
            return {
                **report.to_dict(),
                "report_zh": diag.format_report_zh(report),
            }
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/self-diagnosis/quick")
    async def self_diagnosis_quick():
        """快速自我診斷（核心項目）— 純 CPU, 零 Token."""
        try:
            from museon.doctor.self_diagnosis import SelfDiagnosis
            diag = SelfDiagnosis(data_dir=str(_get_brain().data_dir))
            report = diag.diagnose_quick()
            return {
                **report.to_dict(),
                "report_zh": diag.format_report_zh(report),
            }
        except Exception as e:
            return {"error": str(e)}

    # ─── Workspace File Serving (v9.0) ───

    @app.get("/workspace/{file_path:path}")
    async def serve_workspace_file(file_path: str):
        """Serve workspace files for download (v9.0)."""
        data_dir = Path(_resolve_data_dir())
        full_path = data_dir / "workspace" / file_path
        if not full_path.exists() or not full_path.is_file():
            return {"error": "file_not_found"}
        # Security: prevent path traversal
        workspace_root = (data_dir / "workspace").resolve()
        if not full_path.resolve().is_relative_to(workspace_root):
            return {"error": "access_denied"}
        return FileResponse(
            path=str(full_path),
            filename=full_path.name,
            media_type="application/octet-stream",
        )

    # ═══════════════════════════════════════
    # MCP 連接器管理 API
    # ═══════════════════════════════════════

    @app.get("/api/mcp/status")
    async def mcp_status() -> Dict[str, Any]:
        """取得所有 MCP 伺服器的連線狀態."""
        try:
            brain = _get_brain()
            if (
                hasattr(brain, '_tool_executor')
                and hasattr(brain._tool_executor, '_mcp_connector')
                and brain._tool_executor._mcp_connector
            ):
                return brain._tool_executor._mcp_connector.get_status()
            return {
                "mcp_sdk_available": False,
                "connections": {},
                "total_connected": 0,
                "total_tools": 0,
                "catalog_count": 0,
            }
        except Exception as e:
            logger.error(f"MCP status failed: {e}", exc_info=True)
            return {"error": str(e)}

    @app.get("/api/mcp/catalog")
    async def mcp_catalog() -> Dict[str, Any]:
        """取得推薦的 MCP 伺服器目錄."""
        try:
            from museon.agent.mcp_connector import MCP_SERVER_CATALOG
            # 合併連線狀態
            brain = _get_brain()
            connections = {}
            if (
                hasattr(brain, '_tool_executor')
                and hasattr(brain._tool_executor, '_mcp_connector')
                and brain._tool_executor._mcp_connector
            ):
                status = brain._tool_executor._mcp_connector.get_status()
                connections = status.get("connections", {})

            catalog = []
            for entry in MCP_SERVER_CATALOG:
                name = entry["name"]
                conn = connections.get(name, {})
                catalog.append({
                    **entry,
                    "status": conn.get("status", "disconnected"),
                    "tools_count": conn.get("tools_count", 0),
                    "error": conn.get("error"),
                    "connected_at": conn.get("connected_at"),
                })
            return {"catalog": catalog, "count": len(catalog)}
        except Exception as e:
            logger.error(f"MCP catalog failed: {e}", exc_info=True)
            return {"error": str(e), "catalog": [], "count": 0}

    @app.post("/api/mcp/connect")
    async def mcp_connect(request: Request) -> Dict[str, Any]:
        """連接指定的 MCP 伺服器."""
        try:
            body = await request.json()
            name = body.get("name", "")
            env_vars = body.get("env", {})

            if not name:
                return {"success": False, "error": "缺少伺服器名稱"}

            brain = _get_brain()
            if not (
                hasattr(brain, '_tool_executor')
                and hasattr(brain._tool_executor, '_mcp_connector')
                and brain._tool_executor._mcp_connector
            ):
                return {"success": False, "error": "MCP Connector 未初始化"}

            connector = brain._tool_executor._mcp_connector

            # 找到 catalog 中的配置
            from museon.agent.mcp_connector import MCP_SERVER_CATALOG
            catalog_entry = next(
                (s for s in MCP_SERVER_CATALOG if s["name"] == name), None
            )
            if not catalog_entry:
                return {"success": False, "error": f"不在目錄中：{name}"}

            # 設定 env vars
            for key, value in env_vars.items():
                if value:
                    os.environ[key] = value

            # 儲存到 servers.json
            mcp_config_dir = brain.data_dir / "_system" / "mcp"
            mcp_config_dir.mkdir(parents=True, exist_ok=True)
            servers_file = mcp_config_dir / "servers.json"
            servers = {}
            if servers_file.exists():
                try:
                    servers = json.loads(servers_file.read_text("utf-8"))
                except Exception:
                    servers = {}

            config = {
                "transport": catalog_entry.get("transport", "stdio"),
                "command": catalog_entry.get("command", ""),
                "env": env_vars,
            }
            servers[name] = config
            servers_file.write_text(
                json.dumps(servers, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            # 嘗試連接
            result = await connector.connect_server(name, config)
            return result
        except Exception as e:
            logger.error(f"MCP connect failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @app.post("/api/mcp/disconnect")
    async def mcp_disconnect(request: Request) -> Dict[str, Any]:
        """斷開指定的 MCP 伺服器."""
        try:
            body = await request.json()
            name = body.get("name", "")

            if not name:
                return {"success": False, "error": "缺少伺服器名稱"}

            brain = _get_brain()
            if not (
                hasattr(brain, '_tool_executor')
                and hasattr(brain._tool_executor, '_mcp_connector')
                and brain._tool_executor._mcp_connector
            ):
                return {"success": False, "error": "MCP Connector 未初始化"}

            result = await brain._tool_executor._mcp_connector.disconnect_server(name)

            # 也從 servers.json 移除
            mcp_config_dir = brain.data_dir / "_system" / "mcp"
            servers_file = mcp_config_dir / "servers.json"
            if servers_file.exists():
                try:
                    servers = json.loads(servers_file.read_text("utf-8"))
                    servers.pop(name, None)
                    servers_file.write_text(
                        json.dumps(servers, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                except Exception as e:
                    logger.debug(f"[SERVER] JSON failed (degraded): {e}")

            return result
        except Exception as e:
            logger.error(f"MCP disconnect failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def startup_event():
        """Initialize services on startup."""
        logger.info("Starting MUSEON Gateway")

        # ══════════════════════════════════════════════════════════
        # 🛡️ Governor: 啟動中焦 + 上焦治理
        # 下焦 (GatewayLock) 已由 main() 保證
        # 中焦: ServiceHealthMonitor — Docker 服務健康監控
        # 上焦: 趨勢分析迴圈 — 週期性健康快照 + 警覺信號
        # ══════════════════════════════════════════════════════════
        governor = getattr(app.state, 'governor', None)
        if governor:
            try:
                await governor.start()
                logger.info("🛡️ Governor 三焦治理啟動完成")
            except Exception as e:
                logger.warning(f"Governor start failed (degraded): {e}")

        # 🧬 .env 已由 main() 載入，此處不再重複

        # ══════════════════════════════════════════════════════════
        # 🚢 Layer 2: BulkheadRegistry — 艙壁隔離
        # ══════════════════════════════════════════════════════════
        # 集中式子系統健康追蹤，供 /health 端點使用。
        # 不改動現有 try/except 流程，只在各子系統初始化後記錄狀態。
        # ══════════════════════════════════════════════════════════
        from museon.governance.bulkhead import BulkheadRegistry
        bulkhead = BulkheadRegistry()
        app.state.bulkhead = bulkhead

        # Governor 已在上方啟動，直接記錄狀態
        if governor:
            try:
                # Governor 已成功啟動（否則上方 except 會記錄 warning）
                bulkhead.register("governor", lambda: None, critical=True)
            except Exception as e:
                logger.debug(f"[SERVER] operation failed (degraded): {e}")

        # ── Initialize MUSEON Brain ──
        brain = _get_brain()
        logger.info(
            f"MUSEON Brain ready | "
            f"skills: {brain.skill_router.get_skill_count()} | "
            f"ceremony_needed: {brain.ceremony.is_ceremony_needed()}"
        )
        # 🚢 Bulkhead: Brain 初始化成功
        bulkhead.register("brain", lambda: None, critical=True)

        # 啟動 Brain Worker subprocess（process 隔離）
        try:
            from museon.gateway.brain_worker import init_brain_worker_manager
            _bw = init_brain_worker_manager(data_dir=str(brain.data_dir))
            if _bw:
                logger.info(f"[startup] BrainWorker started, PID={_bw.get_status().get('pid')}")
            else:
                logger.info("[startup] BrainWorker not started, using in-process fallback")
        except Exception as _bw_err:
            logger.warning(f"[startup] BrainWorker init failed (non-fatal): {_bw_err}")

        # 初始化訊息佇列持久化 store
        try:
            from museon.gateway.message_queue_store import get_message_queue_store
            get_message_queue_store(data_dir=brain.data_dir)
            logger.info("[startup] MessageQueueStore initialized")
        except Exception as _mqs_err:
            logger.warning(f"[startup] MessageQueueStore init failed (non-fatal): {_mqs_err}")

        # 注入 Telegram pump 依賴
        init_telegram_pump(
            get_brain=_get_brain,
            get_llm_semaphore=_get_llm_semaphore,
            session_manager=session_manager,
            data_dir=brain.data_dir,
        )

        # Circuit Breaker 通知回調（DM 老闆）
        try:
            from museon.governance.bulkhead import get_brain_circuit_breaker
            _cb = get_brain_circuit_breaker()

            def _cb_notify(event: str, detail: str = ""):
                """Circuit Breaker 狀態變更 → 非同步 DM 老闆.

                時序安全：此回調只在 brain.process() 失敗/成功時觸發，
                而 brain.process() 只在 Telegram adapter 初始化完成後才會被呼叫，
                因此 app.state.telegram_adapter 此時一定已設定。
                仍加 None guard 作為防禦性程式設計。
                """
                _msgs = {
                    "opened": (
                        f"⚠️ Brain Circuit Breaker 已斷路\n\n"
                        f"連續失敗達閾值，自動切換降級回覆。\n"
                        f"錯誤：{detail[:200]}\n\n"
                        f"60 秒後自動試探恢復。"
                    ),
                    "reopened": (
                        f"⚠️ Brain 試探恢復失敗，維持斷路\n\n"
                        f"錯誤：{detail[:200]}"
                    ),
                    "recovered": (
                        "✅ Brain Circuit Breaker 已恢復正常運作"
                    ),
                }
                msg = _msgs.get(event)
                if msg:
                    _tg_adapter = getattr(app.state, "telegram_adapter", None)
                    if _tg_adapter:
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                loop.create_task(_tg_adapter.send_dm_to_owner(msg))
                        except Exception:
                            pass

            _cb.set_notify_callback(_cb_notify)
            logger.info("BrainCircuitBreaker notify callback registered")
        except Exception as _cb_err:
            logger.warning(f"BrainCircuitBreaker setup failed (non-fatal): {_cb_err}")

        # ══════════════════════════════════════════════════════════
        # 🛡️ Phase 3a: Governor ↔ Brain 橋樑連接
        # 打通治理層→大腦的回饋迴路，讓 Brain 能感知系統健康
        # ══════════════════════════════════════════════════════════
        if governor:
            try:
                # Phase 3a: 治理自覺 — Brain 能讀取 GovernanceContext
                brain.set_governor(governor)

                # Phase 2 補完: EventBus → PerceptionEngine 聞診
                if hasattr(brain, '_event_bus') and brain._event_bus:
                    governor.register_event_bus(brain._event_bus)
                    logger.info("🛡️ Governor ↔ EventBus connected")

                logger.info("🛡️ Phase 3a: Governor ↔ Brain bridge established")

                # Phase 3b: VitalSigns 依賴注入 + Preflight
                try:
                    governor.register_vital_signs_deps(
                        llm_adapter=brain._llm_adapter,
                        brain=brain,
                    )
                    preflight_report = await governor.run_vital_preflight()
                    if preflight_report:
                        failed = preflight_report.failed_checks
                        if failed:
                            logger.warning(
                                "🩺 Preflight: %d check(s) FAILED: %s",
                                len(failed),
                                ", ".join(c.name for c in failed),
                            )
                        else:
                            logger.info("🩺 Preflight: all checks PASSED")
                except Exception as e:
                    logger.warning(f"VitalSigns preflight failed (degraded): {e}")

            except Exception as e:
                logger.warning(f"Governor-Brain bridge failed (degraded): {e}")

        # ── Ensure workspace directory exists (v9.0) ──
        workspace_dir = brain.data_dir / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Workspace directory: {workspace_dir}")

        # ── Recover interrupted dispatch plans ──
        try:
            from museon.agent.dispatch import recover_active_plans
            recovered = recover_active_plans(brain.data_dir)
            if recovered:
                logger.info(f"Recovered {recovered} interrupted dispatch plan(s)")
        except Exception as e:
            logger.warning(f"Dispatch recovery failed: {e}")

        # ── DNA27 ReflexRouter → Qdrant 索引（首次啟動 + 自我演化基底）──
        try:
            from museon.agent.reflex_router import index_reflex_patterns_to_qdrant
            indexed = index_reflex_patterns_to_qdrant(str(brain.data_dir))
            logger.info(f"DNA27 Qdrant indexed: {indexed} reflex patterns")
        except Exception as e:
            logger.warning(f"DNA27 Qdrant indexing failed (degraded): {e}")

        # ── Skill 向量索引（全量，確保語意搜尋可用）──
        try:
            from museon.vector.vector_bridge import VectorBridge
            from museon.core.event_bus import get_event_bus
            vb = VectorBridge(workspace=brain.data_dir, event_bus=get_event_bus())
            skill_idx = vb.index_all_skills()
            logger.info(f"[startup] Skills indexed: {skill_idx}")
        except Exception as e:
            logger.warning(f"[startup] Skills index failed (non-fatal): {e}")

        # ── Sparse IDF 驗證（混合檢索基礎設施）──
        try:
            from museon.vector.sparse_embedder import SparseEmbedder
            se = SparseEmbedder(workspace=brain.data_dir)
            if se.is_available() and se.has_idf():
                logger.info(
                    f"[startup] SparseEmbedder IDF ready: "
                    f"{len(se._idf)} terms"
                )
            else:
                reasons = []
                if not se.is_available():
                    reasons.append("jieba not installed")
                if not se.has_idf():
                    reasons.append("IDF table not built (run nightly to build)")
                logger.info(
                    f"[startup] SparseEmbedder unavailable: "
                    f"{', '.join(reasons)} — hybrid search will degrade to pure dense"
                )
        except Exception as e:
            logger.debug(f"[startup] SparseEmbedder check skipped: {e}")

        # ── v10.2: Auto-connect configured MCP servers ──
        try:
            if (
                hasattr(brain, '_tool_executor')
                and brain._tool_executor
                and hasattr(brain._tool_executor, '_mcp_connector')
                and brain._tool_executor._mcp_connector
            ):
                connect_result = await brain._tool_executor._mcp_connector.connect_all_configured()
                connected = connect_result.get("connected", 0)
                failed = connect_result.get("failed", 0)
                logger.info(
                    f"MCP auto-connect: {connected} connected, {failed} failed"
                )
        except Exception as e:
            logger.warning(f"MCP auto-connect failed (degraded): {e}")

        # ── 消費 Guardian mothership_queue（啟動時處理累積的問題）──
        # Guardian daemon 寫入路徑：{data_dir}/guardian/mothership_queue.json
        try:
            _mq_path = brain.data_dir / "guardian" / "mothership_queue.json"
            if _mq_path.exists():
                import json as _json
                _mq_data = _json.loads(_mq_path.read_text(encoding="utf-8"))
                _mq_items = _mq_data if isinstance(_mq_data, list) else _mq_data.get("queue", [])
                if _mq_items:
                    logger.warning(
                        f"[startup] Guardian mothership_queue: {len(_mq_items)} pending items"
                    )
                    for _mq_item in _mq_items[:5]:
                        _mq_msg = _mq_item.get("message", "") if isinstance(_mq_item, dict) else str(_mq_item)
                        _mq_sev = _mq_item.get("severity", "INFO") if isinstance(_mq_item, dict) else "INFO"
                        logger.warning(f"  [Guardian:{_mq_sev}] {_mq_msg[:200]}")
                    # 嚴重問題通知老闆
                    _critical_items = [
                        i for i in _mq_items
                        if isinstance(i, dict) and i.get("severity") in ("CRITICAL", "HIGH")
                    ]
                    if _critical_items and hasattr(app.state, 'telegram_adapter'):
                        _adapter = app.state.telegram_adapter
                        _notify_text = f"Guardian 報告 {len(_critical_items)} 個嚴重問題待處理：\n"
                        for ci in _critical_items[:3]:
                            _notify_text += f"  [{ci.get('severity')}] {ci.get('message', '')[:100]}\n"
                        try:
                            await _adapter.send_dm_to_owner(_notify_text)
                        except Exception as _notify_err:
                            logger.warning(f"[startup] Guardian CRITICAL notification failed: {_notify_err}")
                    # 清空已處理的 queue
                    _mq_path.write_text("[]", encoding="utf-8")
                    logger.info("[startup] Guardian mothership_queue consumed and cleared")
        except Exception as _mq_err:
            logger.warning(f"[startup] mothership_queue read failed: {_mq_err}")

        # ── Start CronEngine + register system jobs ──
        cron_engine.start()
        _register_system_cron_jobs(brain, app, cron_engine)
        _register_external_endpoints(app, brain.data_dir)
        logger.info(
            f"CronEngine started | jobs: {len(cron_engine.get_all_jobs())}"
        )

        # ── SkillHub: 工作流排程初始化 ──
        try:
            from museon.workflow.soft_workflow import WorkflowStore
            from museon.workflow.workflow_engine import WorkflowEngine
            from museon.workflow.workflow_executor import WorkflowExecutor
            from museon.workflow.workflow_scheduler import WorkflowScheduler
            from museon.core.event_bus import get_event_bus

            _wf_store = WorkflowStore(Path(_resolve_data_dir()) / "plans" / "workflows")
            _wf_engine = WorkflowEngine(Path(_resolve_data_dir()), get_event_bus())
            _wf_executor = WorkflowExecutor(brain, _wf_engine, _wf_store, get_event_bus())
            _wf_scheduler = WorkflowScheduler(cron_engine, _wf_store, get_event_bus())
            _wf_scheduler.set_executor(_wf_executor)
            registered_count = _wf_scheduler.register_all()

            app.state.workflow_store = _wf_store
            app.state.workflow_engine = _wf_engine
            app.state.workflow_executor = _wf_executor
            app.state.workflow_scheduler = _wf_scheduler

            _register_skillhub_endpoints(
                app,
                get_brain=_get_brain,
                session_mgr=session_manager,
                cron_eng=cron_engine,
                doctor_status_fn=doctor_node_status,
            )

            logger.info(f"SkillHub started | workflows: {registered_count}")
        except Exception as e:
            logger.warning(f"SkillHub init failed (degraded): {e}")

        # Start Telegram adapter if token is configured (with retry)
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if bot_token:
            # ═══════════════════════════════════════════════════════
            # 🛡️ Governor 下焦: Telegram 受保護啟動
            #
            # 取代舊的 3 次簡單重試：
            # - 指數退避 (2s→3.6s→6.5s→11.7s→21s→30s)
            # - 409 getUpdates 衝突偵測 + 分類處理
            # - 可恢復網路錯誤 vs 不可恢復錯誤分類
            # - Webhook 清理（防止啟動衝突）
            # - 統計追蹤（供 Governor 上焦趨勢分析）
            # ═══════════════════════════════════════════════════════
            from museon.governance.telegram_guard import (
                compute_backoff,
                is_getupdates_conflict,
                is_recoverable_telegram_error,
                PollingStats,
                TELEGRAM_POLL_BACKOFF,
            )

            max_retries = 10  # 從 3 次提高到 10 次
            telegram_started = False
            telegram_stats = PollingStats()
            app.state.telegram_guard_stats = telegram_stats

            for attempt in range(1, max_retries + 1):
                try:
                    from museon.channels.telegram import TelegramAdapter

                    trusted_ids_raw = os.environ.get("TELEGRAM_TRUSTED_IDS", "")
                    trusted_ids = [x.strip() for x in trusted_ids_raw.split(",") if x.strip()]

                    adapter = TelegramAdapter({
                        "bot_token": bot_token,
                        "trusted_user_ids": trusted_ids,
                    })

                    # 🛡️ Webhook 清理 — 防止 409 衝突
                    # 在啟動 polling 之前清除可能殘留的舊 webhook
                    if attempt == 1:
                        try:
                            from telegram import Bot
                            _cleanup_bot = Bot(token=bot_token)
                            await _cleanup_bot.delete_webhook(drop_pending_updates=False)
                            logger.debug("🛡️ Pre-start webhook cleanup done")
                        except Exception as _wh_err:
                            logger.debug(f"Webhook cleanup skipped: {_wh_err}")

                    await adapter.start()
                    app.state.telegram_adapter = adapter

                    # v10.0: 設定 InteractionQueue
                    try:
                        from museon.gateway.interaction import get_interaction_queue
                        _iq = get_interaction_queue()
                        adapter.set_interaction_queue(_iq)
                        logger.info("InteractionQueue connected to TelegramAdapter")
                    except Exception as _iq_err:
                        logger.warning(f"InteractionQueue setup failed (degraded): {_iq_err}")

                    # 記錄啟動成功
                    import time as _time_mod
                    telegram_stats.started_at = _time_mod.time()
                    telegram_stats.last_successful_poll_at = _time_mod.time()
                    telegram_stats.consecutive_errors = 0

                    # Start message pump
                    app.state.telegram_pump_task = asyncio.create_task(
                        _telegram_message_pump(adapter)
                    )

                    # ── Connect Pulse EventBus ──
                    try:
                        from museon.core.event_bus import get_event_bus
                        from museon.pulse.heartbeat_focus import HeartbeatFocus

                        event_bus = get_event_bus()
                        _hf_state = str(brain.data_dir / "pulse" / "heartbeat_focus.json")
                        heartbeat_focus = HeartbeatFocus(state_path=_hf_state)
                        adapter.connect_pulse(event_bus, heartbeat_focus)

                        # ── PI-2 配置初始化：讓 _cfg() 讀取 pulse_config.json ──
                        try:
                            from museon.pulse.pulse_intervention import init_config as _pi_init
                            _pi_init(str(brain.data_dir))
                            logger.info("PulseIntervention config initialized (PI-2 hot-reload ready)")
                        except Exception as _pi_err:
                            logger.warning(f"PulseIntervention config init failed (degraded): {_pi_err}")

                        # ── ProactiveBridge: 心跳→大腦→頻道 ──
                        from museon.pulse.proactive_bridge import ProactiveBridge
                        proactive_bridge = ProactiveBridge(
                            brain=brain,
                            event_bus=event_bus,
                            heartbeat_focus=heartbeat_focus,
                        )
                        app.state.proactive_bridge = proactive_bridge
                        app.state.heartbeat_focus = heartbeat_focus
                        logger.info("ProactiveBridge connected to EventBus")

                        # ── HeartbeatEngine: 驅動 ProactiveBridge 定期自省 ──
                        try:
                            from museon.pulse.heartbeat_engine import get_heartbeat_engine
                            _hb_state = str(brain.data_dir / "pulse" / "heartbeat_engine.json")
                            heartbeat_engine = get_heartbeat_engine(state_path=_hb_state)
                            proactive_bridge.register_with_engine(heartbeat_engine)
                            heartbeat_engine.start()
                            app.state.heartbeat_engine = heartbeat_engine
                            logger.info(
                                "HeartbeatEngine started → ProactiveBridge registered "
                                f"(interval={proactive_bridge.current_interval}s)"
                            )
                        except Exception as _hbe_err:
                            logger.error(f"HeartbeatEngine start failed: {_hbe_err}", exc_info=True)
                            app.state.heartbeat_engine = None

                        # ── VITA PulseEngine: 生命力引擎 ──
                        try:
                            from museon.pulse.pulse_db import get_pulse_db
                            from museon.pulse.explorer import Explorer
                            from museon.pulse.anima_tracker import AnimaTracker
                            from museon.pulse.anima_mc_store import get_anima_mc_store
                            from museon.pulse.pulse_engine import PulseEngine

                            pulse_db = get_pulse_db(brain.data_dir)
                            explorer = Explorer(
                                brain=brain,
                                data_dir=str(brain.data_dir),
                                searxng_url="http://127.0.0.1:8888",
                            )
                            # ★ 取得 AnimaMCStore 單例（Brain 已初始化）
                            _anima_mc_store = get_anima_mc_store(
                                path=brain.data_dir / "ANIMA_MC.json"
                            )
                            anima_tracker = AnimaTracker(
                                anima_path=str(brain.data_dir / "ANIMA_MC.json"),
                                pulse_db=pulse_db,
                                anima_mc_store=_anima_mc_store,
                            )
                            pulse_engine = PulseEngine(
                                brain=brain,
                                event_bus=event_bus,
                                heartbeat_focus=heartbeat_focus,
                                pulse_db=pulse_db,
                                explorer=explorer,
                                anima_tracker=anima_tracker,
                                data_dir=str(brain.data_dir),
                            )
                            app.state.pulse_engine = pulse_engine
                            app.state.pulse_db = pulse_db
                            app.state.anima_tracker = anima_tracker

                            # ── P0-1: PushBudget 全局推送預算 ──
                            try:
                                from museon.pulse.push_budget import PushBudget
                                push_budget = PushBudget(pulse_db=pulse_db)
                                pulse_engine._push_budget = push_budget
                                proactive_bridge._push_budget = push_budget
                                app.state.push_budget = push_budget
                                logger.info(
                                    f"PushBudget injected (today={push_budget.today_count}, "
                                    f"remaining={push_budget.remaining})"
                                )
                            except Exception as _pb_err:
                                logger.warning(f"PushBudget init failed (degraded): {_pb_err}")

                            logger.info("VITA PulseEngine initialized")

                            # ── P2: Governor ↔ PulseDB Incident 橋接 ──
                            _gov_for_pdb = getattr(app.state, "governor", None)
                            if _gov_for_pdb and pulse_db:
                                def _bridge_incident_to_pulsedb(
                                    incident,
                                    _pdb=pulse_db,
                                ):
                                    """將 immunity incident 同步寫入 PulseDB.incidents."""
                                    _pdb.save_incident(
                                        incident_id=incident.incident_id,
                                        incident_type="immunity_event",
                                        module=incident.category,
                                        pattern=incident.symptom_name,
                                        health_delta=(
                                            -10.0
                                            if incident.severity == "severe"
                                            else -5.0
                                        ),
                                        suggested_tier=(
                                            2 if not incident.resolved else 1
                                        ),
                                        raw_log_snippet=(
                                            incident.description[:500]
                                        ),
                                    )

                                _gov_for_pdb.set_incident_callback(
                                    _bridge_incident_to_pulsedb
                                )
                                logger.info(
                                    "🛡️ P2: Governor → PulseDB incident "
                                    "bridge connected"
                                )

                            # ── MicroPulse: 零 LLM 系統健康脈搏 ──
                            try:
                                from museon.pulse.micro_pulse import register_micro_pulse
                                micro_pulse = register_micro_pulse(
                                    heartbeat_focus=heartbeat_focus,
                                    event_bus=event_bus,
                                    workspace=str(brain.data_dir),
                                    anima_mc_store=_anima_mc_store,
                                )
                                app.state.micro_pulse = micro_pulse
                                logger.info(
                                    f"MicroPulse registered → beat every "
                                    f"{micro_pulse._beat_counter} "
                                    f"(interval=1800s)"
                                )
                            except Exception as _mp_err:
                                logger.error(f"MicroPulse start failed: {_mp_err}", exc_info=True)
                                app.state.micro_pulse = None

                            # ── ExplorationBridge: 探索→演化橋樑 ──
                            try:
                                from museon.nightly.exploration_bridge import ExplorationBridge
                                exploration_bridge = ExplorationBridge(
                                    event_bus=event_bus,
                                    workspace=brain.data_dir,
                                )
                                app.state.exploration_bridge = exploration_bridge
                                logger.info("ExplorationBridge initialized (exploration→evolution)")
                            except Exception as _eb_err:
                                logger.warning(f"ExplorationBridge init failed (degraded): {_eb_err}")

                            # ── ImmuneResearch: 免疫研究引擎 ──
                            try:
                                from museon.governance.immune_research import ImmuneResearch
                                immune_research = ImmuneResearch(
                                    brain=brain,
                                    event_bus=event_bus,
                                    workspace=brain.data_dir,
                                    searxng_url="http://127.0.0.1:8888",
                                )
                                app.state.immune_research = immune_research
                                logger.info("ImmuneResearch initialized (immune→research bridge)")
                            except Exception as _ir_err:
                                logger.warning(f"ImmuneResearch init failed (degraded): {_ir_err}")

                            # Phase 3b: ANIMA 成長驅動 — 治理事件映射八元素
                            _gov = getattr(app.state, 'governor', None)
                            if _gov and anima_tracker:
                                try:
                                    _gov.register_anima_tracker(anima_tracker)
                                except Exception as _e:
                                    logger.warning(
                                        f"Phase 3b ANIMA bridge failed: {_e}"
                                    )
                        except Exception as e:
                            logger.warning(f"VITA PulseEngine init failed (degraded): {e}")
                            app.state.pulse_engine = None
                            app.state.pulse_db = None
                            app.state.anima_tracker = None

                        # ── AutonomousQueue: 自主任務佇列 ──
                        from museon.pulse.autonomous_queue import AutonomousQueue
                        autonomous_queue = AutonomousQueue(
                            auth_policy=None,  # 使用預設策略
                            budget_monitor=brain.budget_monitor if brain else None,
                            event_bus=event_bus,
                            state_path=str(brain.data_dir / "_system" / "state" / "autonomous_queue.json"),
                        )
                        app.state.autonomous_queue = autonomous_queue
                        logger.info("AutonomousQueue initialized")

                        # ── Daily Minimum: 每日最低保證（20:00 後 0 推送觸發 companion）──
                        try:
                            proactive_bridge.register_daily_minimum(heartbeat_engine)
                            logger.info("ProactiveBridge daily minimum registered")
                        except Exception as _dm_err:
                            logger.warning(f"Daily minimum registration failed: {_dm_err}")

                        # ── Exploration Neural Tract: 探索結果 → ProactiveBridge context ──
                        from museon.core.event_bus import (
                            EXPLORATION_INSIGHT,
                            EXPLORATION_CRYSTALLIZED,
                        )

                        def _on_exploration_result(data):
                            if not data:
                                return
                            try:
                                title = data.get("topic", "") or data.get("title", "")
                                findings = data.get("findings", "") or data.get("summary", "")
                                summary = findings[:500] if findings else ""
                                hint = f"[探索發現] {title}: {summary}" if summary else f"[探索發現] {title}"
                                proactive_bridge.add_context_hint(hint)
                            except Exception as e:
                                logger.debug(f"[SERVER] operation failed (degraded): {e}")

                        event_bus.subscribe(EXPLORATION_INSIGHT, _on_exploration_result)
                        event_bus.subscribe(EXPLORATION_CRYSTALLIZED, _on_exploration_result)
                        logger.info("Exploration → ProactiveBridge neural tract connected")

                        # ── Nightly Neural Tract: 管線完成 → ProactiveBridge 上下文注入 ──
                        from museon.core.event_bus import NIGHTLY_COMPLETED
                        def _on_nightly_completed(data):
                            try:
                                s = data.get("summary", {})
                                hint = (
                                    f"夜間整合完成: {s.get('ok', 0)}/{s.get('total', 0)} 步驟成功"
                                )
                                errors = data.get("errors", [])
                                if errors:
                                    hint += f", {len(errors)} 個失敗"
                                proactive_bridge.add_context_hint(hint)
                            except Exception as e:
                                logger.debug(f"[SERVER] operation failed (degraded): {e}")
                        event_bus.subscribe(NIGHTLY_COMPLETED, _on_nightly_completed)
                        logger.info("Nightly → ProactiveBridge neural tract connected")

                        # ── Relationship Neural Tract: 情感訊號 → PulseEngine 關係日誌 ──
                        from museon.core.event_bus import RELATIONSHIP_SIGNAL

                        def _on_relationship_signal(data):
                            if not data:
                                return
                            try:
                                note = data.get("note", "")
                                if note and hasattr(app.state, "pulse_engine") and app.state.pulse_engine:
                                    app.state.pulse_engine.add_relationship_note(note)
                            except Exception as e:
                                logger.debug(f"[SERVER] pulse failed (degraded): {e}")

                        event_bus.subscribe(RELATIONSHIP_SIGNAL, _on_relationship_signal)
                        logger.info("Relationship → PulseEngine neural tract connected")

                        # ── WEE Neural Tract: BRAIN_RESPONSE_COMPLETE → WEEEngine.auto_cycle ──
                        try:
                            from museon.core.event_bus import BRAIN_RESPONSE_COMPLETE
                            from museon.evolution.wee_engine import get_wee_engine

                            def _on_brain_response(data):
                                try:
                                    uid = data.get("user_id", "boss")
                                    wee = get_wee_engine(
                                        user_id=uid,
                                        workspace=brain.data_dir,
                                        event_bus=event_bus,
                                        memory_manager=getattr(brain, "memory_manager", None),
                                    )
                                    wee.auto_cycle(data)
                                except Exception as e:
                                    logger.debug(f"[SERVER] WEE failed (degraded): {e}")

                            event_bus.subscribe(BRAIN_RESPONSE_COMPLETE, _on_brain_response)
                            logger.info("WEE neural tract connected (BRAIN_RESPONSE_COMPLETE → auto_cycle)")
                        except Exception as e:
                            logger.warning(f"WEE integration failed (degraded): {e}")

                        # ── ActivityLogger: EventBus → JSONL 日誌 ──
                        try:
                            from museon.core.activity_logger import ActivityLogger as _AL
                            _activity_logger = _AL(data_dir=str(brain.data_dir))
                            app.state.activity_logger = _activity_logger

                            # 訂閱關鍵事件
                            _log_events = [
                                "BRAIN_RESPONSE_COMPLETE",
                                "NIGHTLY_COMPLETED",
                                "NIGHTLY_STARTED",
                                "PULSE_PROACTIVE_SENT",
                                "PULSE_EXPLORATION_DONE",
                                "PULSE_MICRO_BEAT",
                                "AUTONOMOUS_TASK_DONE",
                                "MORPHENIX_PROPOSAL_CREATED",
                                "MORPHENIX_EXECUTION_COMPLETED",
                                "WEE_CYCLE_COMPLETE",
                                "CRYSTAL_CREATED",
                                "SOUL_RING_DEPOSITED",
                            ]
                            for _evt_name in _log_events:
                                _evt_const = getattr(
                                    __import__("museon.core.event_bus", fromlist=[_evt_name]),
                                    _evt_name,
                                    _evt_name,
                                )
                                def _make_handler(name):
                                    def _h(data):
                                        try:
                                            _activity_logger.log(name, data, source="event_bus")
                                        except Exception as e:
                                            logger.debug(f"[SERVER] operation failed (degraded): {e}")
                                    return _h
                                event_bus.subscribe(_evt_const, _make_handler(_evt_name))
                            logger.info("ActivityLogger connected to EventBus (%d events)", len(_log_events))
                        except Exception as e:
                            logger.warning(f"ActivityLogger init failed (degraded): {e}")

                    except Exception as e:
                        logger.warning(f"Pulse integration failed (degraded): {e}")

                    logger.info(
                        f"🛡️ Telegram adapter started successfully"
                        f" (attempt {attempt}/{max_retries})"
                    )
                    telegram_started = True
                    # 🚢 Bulkhead: Telegram 啟動成功
                    bulkhead.register("telegram", lambda: None)

                    # 🛡️ 註冊 Telegram 狀態到 Governor（供三焦健康分析用）
                    if governor:
                        def _telegram_status_fn():
                            stats = app.state.telegram_guard_stats
                            _adapter = app.state.telegram_adapter
                            import time as _t
                            return {
                                "running": _adapter is not None and getattr(_adapter, '_running', False),
                                "uptime_s": round(_t.time() - stats.started_at, 1) if stats.started_at else 0,
                                "total_restarts": stats.total_restarts,
                                "consecutive_errors": stats.consecutive_errors,
                                "conflict_count": stats.conflict_count,
                                "network_error_count": stats.network_error_count,
                                "last_error": stats.last_error,
                            }
                        governor.register_telegram_status(_telegram_status_fn)
                        logger.info("🛡️ Telegram status registered to Governor")

                    break

                except Exception as e:
                    # 🛡️ 分類錯誤：409 衝突 / 可恢復網路錯誤 / 不可恢復
                    is_conflict = is_getupdates_conflict(e)
                    is_recoverable = is_recoverable_telegram_error(e)

                    if is_conflict:
                        telegram_stats.conflict_count += 1
                        err_type = "409 getUpdates conflict"
                    elif is_recoverable:
                        telegram_stats.network_error_count += 1
                        err_type = f"network error ({type(e).__name__})"
                    else:
                        err_type = f"error ({type(e).__name__})"

                    telegram_stats.consecutive_errors += 1
                    telegram_stats.last_error = str(e)

                    logger.error(
                        f"🛡️ Telegram start attempt {attempt}/{max_retries}"
                        f" failed — {err_type}: {e}"
, exc_info=True)

                    # 不可恢復的錯誤且已超過 3 次 → 不再重試
                    if not is_conflict and not is_recoverable and attempt >= 3:
                        logger.error(
                            f"Telegram: unrecoverable error after {attempt} attempts — giving up"
, exc_info=True)
                        break

                    if attempt < max_retries:
                        # 🛡️ 指數退避（取代舊的 5*attempt 線性退避）
                        delay_ms = compute_backoff(TELEGRAM_POLL_BACKOFF, attempt)
                        delay_s = delay_ms / 1000.0
                        logger.info(
                            f"🛡️ Telegram retry #{attempt+1} in {delay_s:.1f}s "
                            f"(exponential backoff)"
                        )
                        await asyncio.sleep(delay_s)

            if not telegram_started:
                telegram_stats.total_restarts = attempt
                logger.error(
                    f"🛡️ Telegram adapter failed after {attempt} retries — "
                    f"conflicts={telegram_stats.conflict_count}, "
                    f"network_errors={telegram_stats.network_error_count}. "
                    f"Will remain offline until Gateway restart"
                )
                # 🚢 Bulkhead: Telegram 啟動失敗（非致命，Gateway 仍可運行）
                bulkhead.mark_degraded(
                    "telegram",
                    f"Failed after {attempt} retries"
                )
                # 以 FAILED 狀態註冊（如果尚未註冊）
                if "telegram" not in bulkhead.get_status():
                    bulkhead.register(
                        "telegram",
                        lambda: (_ for _ in ()).throw(
                            RuntimeError("Telegram startup failed")
                        ),
                    )
        else:
            logger.warning("TELEGRAM_BOT_TOKEN not set, Telegram disabled")

        # ══════════════════════════════════════════════════════════
        # ✅ RefractoryGuard: 啟動成功 — 清零失敗計數器
        # ══════════════════════════════════════════════════════════
        refractory = getattr(app.state, 'refractory', None)
        if refractory:
            refractory.record_success()
            logger.info("✅ RefractoryGuard: 啟動成功，失敗計數歸零")

        # 🚢 Bulkhead: 記錄整體狀態
        logger.info(
            f"🚢 Bulkhead 整體狀態: {bulkhead.overall_status} "
            f"| 子系統: {bulkhead.get_status()}"
        )

    async def shutdown_event():
        """Cleanup on shutdown."""
        logger.info("Shutting down MUSEON Gateway")

        # Stop Brain Worker subprocess
        try:
            from museon.gateway.brain_worker import get_brain_worker_manager
            _bw = get_brain_worker_manager()
            if _bw:
                _bw.stop()
                logger.info("BrainWorker stopped")
        except Exception:
            pass

        # Flush skill usage log before shutdown
        brain = _get_brain()
        if brain:
            brain._flush_skill_usage()
            logger.info("Skill usage log flushed")

        # Stop Telegram pump task
        if app.state.telegram_pump_task:
            app.state.telegram_pump_task.cancel()
            try:
                await app.state.telegram_pump_task
            except asyncio.CancelledError as e:
                logger.debug(f"[SERVER] telegram failed (degraded): {e}")

        # Stop Telegram adapter
        if app.state.telegram_adapter:
            await app.state.telegram_adapter.stop()
            logger.info("Telegram adapter stopped")

        cron_engine.shutdown()

        # v10.2: Shutdown MCP connections
        try:
            if (
                brain
                and hasattr(brain, '_tool_executor')
                and brain._tool_executor
                and hasattr(brain._tool_executor, '_mcp_connector')
                and brain._tool_executor._mcp_connector
            ):
                await brain._tool_executor._mcp_connector.shutdown_all()
                logger.info("MCP connections shut down")
        except Exception as e:
            logger.warning(f"MCP shutdown error: {e}")

        # 🛡️ Governor: 停止所有治理子系統（中焦 + 上焦）
        # Gateway Lock（下焦）由 main() 的 finally 釋放
        governor = getattr(app.state, 'governor', None)
        if governor:
            await governor.stop()
            logger.info("🛡️ Governor: all governance subsystems stopped")

    # 註冊生命週期事件（避免 @app.on_event() DeprecationWarning）
    app.router.on_startup.append(startup_event)
    app.router.on_shutdown.append(shutdown_event)

    return app


# ═══════════════════════════════════════════════════════
# Telegram Message Pump（已拆分到 telegram_pump.py）
# ═══════════════════════════════════════════════════════

from .telegram_pump import (  # noqa: E402
    _progress_updater,
    _handle_telegram_message,
    _telegram_message_pump,
    init_telegram_pump,
)


# ═══════════════════════════════════════════════════════
# API Routes（已拆分到 routes_api.py）
# ═══════════════════════════════════════════════════════

from .routes_api import (  # noqa: E402
    _register_skillhub_endpoints,
    _register_external_endpoints,
)

from .cron_registry import _register_system_cron_jobs  # noqa: E402


def _pre_start_cleanup(port: int = 8765) -> None:
    """啟動前清理 — 確保 port 沒有殭屍進程佔用.

    防止重啟時出現 [Errno 48] address already in use。
    v10.4: 增強版 — 殺進程後重試驗證 port 可用，最多等 15 秒。
    """
    import subprocess as _sp
    import os as _os
    import socket
    import time

    def _port_is_free(p: int) -> bool:
        """嘗試綁定 port，確認真正可用（含 TIME_WAIT）。"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", p))
                return True
        except OSError:
            return False

    # 快速檢查：port 已可用就直接返回
    if _port_is_free(port):
        return

    # 找出佔用 port 的進程並終止
    try:
        result = _sp.run(
            ["lsof", "-i", f":{port}", "-t"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            my_pid = _os.getpid()
            for pid_str in result.stdout.strip().split("\n"):
                try:
                    pid = int(pid_str.strip())
                except ValueError:
                    continue
                if pid != my_pid:
                    logger.warning(
                        f"Pre-start cleanup: killing stale process on port {port} (PID {pid})"
                    )
                    _sp.run(["kill", "-9", str(pid)], capture_output=True, timeout=5)
    except Exception as e:
        logger.debug(f"Pre-start cleanup lsof failed: {e}")

    # 等待 port 真正釋放（最多 15 秒，每秒檢查一次）
    for attempt in range(15):
        time.sleep(1)
        if _port_is_free(port):
            logger.info(f"Pre-start cleanup: port {port} freed after {attempt + 1}s")
            return

    logger.error(
        f"Pre-start cleanup: port {port} still occupied after 15s — "
        f"aborting startup to avoid crash loop (launchd will retry)"
    )
    import sys
    sys.exit(1)


def main() -> None:
    """Run the Gateway server (localhost only)."""
    import sys
    import time as _time

    # ── Configure application logging BEFORE anything else ──
    _configure_logging()

    # ══════════════════════════════════════════════════════════
    # 🧬 Layer 0: 載入 .env（從 startup_event 提前到此處）
    # ══════════════════════════════════════════════════════════
    # Preflight 需要讀取環境變數，所以必須先載入 .env
    _load_env_file()

    # ══════════════════════════════════════════════════════════
    # 🫁 Layer 1: PreflightGate — 胸腺驗證
    # ══════════════════════════════════════════════════════════
    # 在任何服務啟動前驗證配置完整性。
    # 失敗時 exit(0) 避免 launchd 無限重啟迴圈。
    # （KeepAlive.SuccessfulExit=false 只在非零退出碼時重啟）
    # ══════════════════════════════════════════════════════════
    from museon.governance.preflight import PreflightGate
    from museon.governance.refractory import RefractoryGuard

    preflight = PreflightGate()
    preflight_result = preflight.run()

    for w in preflight_result.warnings:
        logger.warning(f"⚠️  Preflight: {w}")

    if not preflight_result.passed:
        for f in preflight_result.failures:
            logger.error(f"🚫 Preflight FATAL: {f}")
        logger.error(
            "Gateway 無法啟動 — 請修正上述問題後重啟。"
            "（exit(0) 避免 launchd 無限重啟）"
        )
        # 記錄失敗到 RefractoryGuard
        RefractoryGuard().record_failure("preflight_failed")
        sys.exit(0)

    # ══════════════════════════════════════════════════════════
    # ⏳ Layer 3: RefractoryGuard — 不應期斷路器
    # ══════════════════════════════════════════════════════════
    # 跨重啟的失敗計數器 + 指數退避。
    # 連續失敗過多 → 休眠（exit(0) 不重啟，等外部干預）。
    # ══════════════════════════════════════════════════════════
    refractory = RefractoryGuard()
    action, wait_secs = refractory.check()

    if action == "hibernate":
        logger.warning(
            "💤 RefractoryGuard: 休眠中（連續失敗過多）。"
            "修改 .env 或刪除 ~/.museon/refractory_state.json 以喚醒。"
        )
        sys.exit(0)
    elif action == "backoff":
        logger.warning(
            f"⏳ RefractoryGuard: 冷卻 {wait_secs} 秒後重試..."
        )
        _time.sleep(wait_secs)

    # ══════════════════════════════════════════════════════════
    # 🛡️ MUSEON Governor — 三焦式運行時治理
    # ══════════════════════════════════════════════════════════
    #
    # 統一治理控制器，取代舊的 _pre_start_cleanup：
    #
    # 下焦: GatewayLock 確保全局唯一實例（PID Lock + 端口探測）
    # 中焦: ServiceHealthMonitor (由 startup_event 啟動)
    # 上焦: 趨勢分析 + 警覺信號 (由 startup_event 啟動)
    #
    # 如果另一個 Gateway 已在運行，直接拋出異常而非 kill -9
    # ══════════════════════════════════════════════════════════
    from museon.governance.governor import Governor
    from museon.governance.gateway_lock import GatewayLockError

    governor = Governor(port=8765)
    try:
        governor.acquire_lock()
    except GatewayLockError as e:
        logger.warning(f"Cannot start Gateway: {e}")
        logger.warning(
            "Another Gateway instance is already running. "
            "Exiting gracefully (exit 0) to prevent launchd restart storm."
        )
        sys.exit(0)  # exit(0) — 告知 launchd 不需重試（SuccessfulExit=false 不觸發）

    # Fallback: 如果 lock 成功但 port 仍被佔用（邊緣情況），
    # 保留舊的清理邏輯作為安全網
    _pre_start_cleanup(8765)

    app = create_app()

    # 將 Governor + RefractoryGuard 掛到 app.state，
    # 供 startup/shutdown/health 使用
    app.state.governor = governor
    app.state.refractory = refractory

    try:
        # CRITICAL: Only bind to localhost (127.0.0.1)
        # This prevents remote access to the Gateway
        # P3 修復：啟用 SO_REUSEADDR 避免 launchd 重啟時 port TIME_WAIT 衝突
        config = uvicorn.Config(
            app,
            host="127.0.0.1",  # localhost only
            port=8765,
            log_level="info",
        )
        server = uvicorn.Server(config)
        server.run()
    finally:
        # 無論如何都要釋放鎖
        governor.release_lock()


if __name__ == "__main__":
    main()
