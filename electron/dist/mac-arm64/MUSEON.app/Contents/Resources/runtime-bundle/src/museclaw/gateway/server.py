"""Gateway FastAPI Server - Localhost only.

MUSEON Brain 的入口。所有訊息（Telegram, Webhook）都經過 Brain 處理。

Integrates:
- FastAPI webhook endpoint
- Telegram polling adapter
- MuseClawBrain (DNA27 + Skills + ANIMA + Memory)
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
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

from .message import InternalMessage
from .session import SessionManager
from .security import SecurityGate
from .cron import CronEngine

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Configure application-level logging for the museclaw namespace.

    Uvicorn manages its own access logs (stdout → gateway.log via Electron).
    This function sets up the 'museclaw' logger hierarchy so that
    application-level logs (DNA27 routing, skill matching, tool calls, etc.)
    are captured to a dedicated file AND stderr.

    Log file: {runtime_root}/logs/museclaw.log
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
    log_file = log_dir / "museclaw.log"

    # ── Configure the 'museclaw' namespace logger ──
    app_logger = logging.getLogger("museclaw")
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
    1. $MUSECLAW_HOME/.env
    2. Walk up from this file to find pyproject.toml, then .env next to it
    3. Fallback: ~/MuseClaw/.env
    """
    # Try MUSECLAW_HOME first
    home = os.environ.get("MUSECLAW_HOME")
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
    env_file = Path.home() / "MuseClaw" / ".env"
    if env_file.exists():
        _parse_env(env_file)


def _parse_env(env_file: Path) -> None:
    """Parse a .env file and set os.environ.

    .env 是 API Key 的唯一 source of truth。
    系統路徑變數（PATH/PYTHONPATH/MUSECLAW_HOME）由 launchd plist 管理，不覆蓋。
    API Key 類別的變數一律從 .env 載入（覆蓋舊值），確保 Setup Wizard
    更新 Key 後 Gateway 重啟能讀到最新值。
    """
    # 不覆蓋的系統變數（由 launchd plist 或 shell 管理）
    SYSTEM_VARS = {"PATH", "PYTHONPATH", "MUSECLAW_HOME", "HOME", "USER", "SHELL"}

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
    home = os.environ.get("MUSECLAW_HOME")
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
    1. $MUSECLAW_HOME/data
    2. Walk up from this file to find pyproject.toml → data/ next to it
       (or parent/data/ if inside .runtime)
    3. Fallback: ~/MuseClaw/data
    """
    # Try MUSECLAW_HOME first
    home = os.environ.get("MUSECLAW_HOME")
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
    fallback = Path.home() / "MuseClaw" / "data"
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback)


def _get_brain():
    """Get the global brain instance (lazy, thread-safe enough for async)."""
    global _brain
    if _brain is None:
        from museclaw.agent.brain import MuseClawBrain
        data_dir = _resolve_data_dir()
        _brain = MuseClawBrain(data_dir=data_dir)
        logger.info(f"MUSEON Brain initialized with data_dir={data_dir}")
    return _brain


def _reset_brain():
    """Reset brain instance (for testing isolation)."""
    global _brain
    _brain = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="MuseClaw Gateway",
        description="24/7 Life Central - MUSEON Brain routing and session management",
        version="0.2.0",
    )

    # ─── Telegram adapter state ───
    app.state.telegram_adapter = None
    app.state.telegram_pump_task = None

    @app.get("/health")
    async def health_check() -> Dict[str, Any]:
        """Health check endpoint."""
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

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "telegram": telegram_status,
            "brain": brain_status,
            "skills_indexed": skill_count,
            "mcp": mcp_status,
        }

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
            logger.error(f"Invalid JSON: {e}")
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
            logger.error(f"Invalid message format: {e}")
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
            from museclaw.gateway.message import BrainResponse
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
            logger.error(f"Brain processing error: {e}")
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
        adapter = app.state.telegram_adapter
        if not adapter:
            return {"configured": False, "running": False, "last_message_time": None}
        return {
            "configured": True,
            **adapter.get_status(),
        }

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
                except asyncio.CancelledError:
                    pass
                steps.append("已停止訊息泵")

            if app.state.telegram_adapter:
                await app.state.telegram_adapter.stop()
                steps.append("已停止 Telegram adapter")

            # Restart
            bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
            if not bot_token:
                return {"success": False, "steps": steps, "error": "TELEGRAM_BOT_TOKEN 未設定"}

            from museclaw.channels.telegram import TelegramAdapter

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
            from museclaw.gateway.message import BrainResponse
            if isinstance(brain_result, BrainResponse):
                response_text = brain_result.text
            elif brain_result:
                response_text = str(brain_result)

            if response_text and app.state.telegram_adapter:
                from museclaw.gateway.message import InternalMessage
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
            logger.error(f"Telegram inject failed: {e}")
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
        title = payload.get("title", "MuseClaw 通知")
        body = payload.get("body", "")
        emoji = payload.get("emoji", "📢")

        # 純 CPU 模板格式化
        text = f"{emoji} [{source}] {title}\n\n{body}"

        sent = await adapter.push_notification(text)
        return {"success": sent > 0, "sent": sent}

    # ─── Doctor 健檢 & 修復端點（純 CPU）───

    @app.get("/api/doctor/check")
    async def doctor_health_check() -> Dict[str, Any]:
        """執行完整健檢 — 純 CPU, 零 Token"""
        try:
            from museclaw.doctor.health_check import HealthChecker

            checker = HealthChecker()
            report = checker.run_all()
            return report.to_dict()
        except Exception as e:
            return {"error": str(e), "overall": "unknown", "checks": []}

    @app.post("/api/doctor/repair")
    async def doctor_repair(payload: Dict[str, Any]) -> Dict[str, Any]:
        """執行修復動作 — 純 CPU"""
        action = payload.get("action", "")
        if not action:
            return {"error": "missing action parameter"}

        try:
            from museclaw.doctor.auto_repair import AutoRepair

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
                _persist_env_setting("MUSECLAW_DAILY_TOKEN_LIMIT", str(new_limit))

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
        """取得 API Key 設定狀態 — 不回傳 Key 值本身"""
        anthropic = os.environ.get("ANTHROPIC_API_KEY", "")
        telegram = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        return {
            "ANTHROPIC_API_KEY": {
                "configured": bool(anthropic),
                "prefix": anthropic[:8] + "***" if len(anthropic) > 8 else "",
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
            from museclaw.guardian.daemon import GuardianDaemon
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
            from museclaw.guardian.daemon import GuardianDaemon
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

            from museclaw.nightly.morphenix_executor import MorphenixExecutor

            brain = _get_brain()
            source_root = Path(os.environ.get(
                "MUSECLAW_SOURCE_ROOT",
                str(Path(brain.data_dir).parent.parent / "museclaw"),
            ))
            event_bus = None
            try:
                from museclaw.core.event_bus import get_event_bus
                event_bus = get_event_bus()
            except Exception:
                pass

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
            logger.error(f"Morphenix execute API error: {e}")
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
                            except Exception:
                                pass
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
            logger.error(f"Savings breakdown failed: {e}")
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
            from museclaw.nightly.nightly_pipeline import NightlyPipeline
            from museclaw.core.event_bus import get_event_bus

            event_bus = get_event_bus()
            pipeline = NightlyPipeline(
                workspace=brain.data_dir,
                event_bus=event_bus,
                brain=brain,
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
            from museclaw.core.activity_logger import ActivityLogger
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
            from museclaw.core.skill_manager import SkillManager
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
            from museclaw.core.skill_manager import SkillManager
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
            from museclaw.core.skill_manager import SkillManager
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
            from museclaw.core.skill_manager import SkillManager
            mgr = SkillManager(workspace=brain.data_dir)
            return mgr.scan_all()
        except Exception as e:
            return {"error": str(e)}

    # ── Multi-Agent API ──

    @app.get("/api/multiagent/departments")
    async def multiagent_departments() -> Dict[str, Any]:
        """列出全部 10 部門 — 零 token."""
        try:
            from museclaw.multiagent.department_config import get_all_departments
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
            from museclaw.multiagent.shared_assets import SharedAssetLibrary
            lib = SharedAssetLibrary(workspace=brain.data_dir)
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
            from museclaw.multiagent.okr_router import route, soft_route
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
            from museclaw.tools.mcp_dify import check_health
            return check_health()
        except Exception as e:
            return {"healthy": False, "error": str(e), "configured": False}

    @app.get("/api/tools/dify/tools")
    async def dify_tools() -> Dict[str, Any]:
        """列出 Dify MCP 可用工具 — 零 token."""
        try:
            from museclaw.tools.mcp_dify import DIFY_TOOLS
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
                    except Exception:
                        pass
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
                    except Exception:
                        pass
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
            from museclaw.tools.tool_registry import ToolRegistry
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
            from museclaw.tools.tool_registry import ToolRegistry
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
            from museclaw.tools.tool_registry import ToolRegistry
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
            from museclaw.tools.tool_registry import ToolRegistry
            registry = ToolRegistry(workspace=_get_brain().data_dir)
            return registry.toggle_tool(name, enabled)
        except Exception as e:
            return {"success": False, "error": str(e)}

    @app.post("/api/tools/health")
    async def tools_health():
        """執行所有工具健康檢查."""
        try:
            from museclaw.tools.tool_registry import ToolRegistry
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
            from museclaw.tools.tool_registry import ToolRegistry
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
            from museclaw.tools.tool_registry import ToolRegistry
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
                from museclaw.tools.tool_registry import ToolRegistry
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
            from museclaw.tools.tool_registry import ToolRegistry
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
            from museclaw.tools.tool_registry import ToolRegistry
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
            from museclaw.tools.tool_registry import ToolRegistry
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
            except Exception:
                pass

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
            logger.error(f"Setup wizard error: {e}")
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
            from museclaw.tools.tool_registry import ToolRegistry
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
            from museclaw.tools.tool_discovery import ToolDiscovery
            discovery = ToolDiscovery(workspace=_get_brain().data_dir)
            return discovery.get_latest_discoveries()
        except Exception as e:
            return {"error": str(e), "searched": 0, "recommended": []}

    # ── VectorBridge 端點 ──

    @app.get("/api/vector/status")
    async def vector_status():
        """Qdrant 可用性 + 各 collection 統計."""
        try:
            from museclaw.vector.vector_bridge import VectorBridge
            vb = VectorBridge(workspace=_get_brain().data_dir)
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
            from museclaw.vector.vector_bridge import VectorBridge
            vb = VectorBridge(workspace=_get_brain().data_dir)
            results = vb.search(collection, query, limit=limit)
            return {"results": results, "count": len(results)}
        except Exception as e:
            return {"error": str(e), "results": []}

    @app.post("/api/vector/reindex")
    async def vector_reindex(payload: Dict[str, Any] = {}):
        """觸發全量重建索引."""
        try:
            from museclaw.vector.vector_bridge import VectorBridge
            vb = VectorBridge(workspace=_get_brain().data_dir)
            result = vb.ensure_collections()
            return {"success": True, **result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── ExecutionSandbox 端點 ──

    @app.get("/api/sandbox/status")
    async def sandbox_status():
        """Docker 沙盒可用性 + 審計統計."""
        try:
            from museclaw.security.execution_sandbox import ExecutionSandbox
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
            from museclaw.security.execution_sandbox import ExecutionSandbox
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
            from museclaw.evolution.wee_engine import get_wee_engine
            from museclaw.core.event_bus import get_event_bus

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
            from museclaw.doctor.self_diagnosis import SelfDiagnosis
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
            from museclaw.doctor.self_diagnosis import SelfDiagnosis
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
            logger.error(f"MCP status failed: {e}")
            return {"error": str(e)}

    @app.get("/api/mcp/catalog")
    async def mcp_catalog() -> Dict[str, Any]:
        """取得推薦的 MCP 伺服器目錄."""
        try:
            from museclaw.agent.mcp_connector import MCP_SERVER_CATALOG
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
            logger.error(f"MCP catalog failed: {e}")
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
            from museclaw.agent.mcp_connector import MCP_SERVER_CATALOG
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
            logger.error(f"MCP connect failed: {e}")
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
                except Exception:
                    pass

            return result
        except Exception as e:
            logger.error(f"MCP disconnect failed: {e}")
            return {"success": False, "error": str(e)}

    @app.on_event("startup")
    async def startup_event():
        """Initialize services on startup."""
        logger.info("Starting MuseClaw Gateway")

        # ── 早期 port 檢查：避免 20 秒初始化後才發現 port 衝突 ──
        import socket as _sock
        try:
            with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as _s:
                _s.setsockopt(_sock.SOL_SOCKET, _sock.SO_REUSEADDR, 1)
                _s.bind(("127.0.0.1", 8765))
        except OSError:
            logger.error(
                "Port 8765 仍被占用，跳過初始化等待下次重啟。"
                "這避免了 20 秒的無效初始化。"
            )
            return

        # Load .env file
        _load_env_file()

        # ── Initialize MUSEON Brain ──
        brain = _get_brain()
        logger.info(
            f"MUSEON Brain ready | "
            f"skills: {brain.skill_router.get_skill_count()} | "
            f"ceremony_needed: {brain.ceremony.is_ceremony_needed()}"
        )

        # ── Ensure workspace directory exists (v9.0) ──
        workspace_dir = brain.data_dir / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Workspace directory: {workspace_dir}")

        # ── Recover interrupted dispatch plans ──
        try:
            from museclaw.agent.dispatch import recover_active_plans
            recovered = recover_active_plans(brain.data_dir)
            if recovered:
                logger.info(f"Recovered {recovered} interrupted dispatch plan(s)")
        except Exception as e:
            logger.warning(f"Dispatch recovery failed: {e}")

        # ── DNA27 ReflexRouter → Qdrant 索引（首次啟動 + 自我演化基底）──
        try:
            from museclaw.agent.reflex_router import index_reflex_patterns_to_qdrant
            indexed = index_reflex_patterns_to_qdrant(str(brain.data_dir))
            logger.info(f"DNA27 Qdrant indexed: {indexed} reflex patterns")
        except Exception as e:
            logger.warning(f"DNA27 Qdrant indexing failed (degraded): {e}")

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

        # ── Start CronEngine + register system jobs ──
        cron_engine.start()
        _register_system_cron_jobs(brain, app)
        logger.info(
            f"CronEngine started | jobs: {len(cron_engine.get_all_jobs())}"
        )

        # Start Telegram adapter if token is configured (with retry)
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if bot_token:
            max_retries = 3
            telegram_started = False
            for attempt in range(1, max_retries + 1):
                try:
                    from museclaw.channels.telegram import TelegramAdapter

                    trusted_ids_raw = os.environ.get("TELEGRAM_TRUSTED_IDS", "")
                    trusted_ids = [x.strip() for x in trusted_ids_raw.split(",") if x.strip()]

                    adapter = TelegramAdapter({
                        "bot_token": bot_token,
                        "trusted_user_ids": trusted_ids,
                    })
                    await adapter.start()
                    app.state.telegram_adapter = adapter

                    # Start message pump
                    app.state.telegram_pump_task = asyncio.create_task(
                        _telegram_message_pump(adapter)
                    )

                    # ── Connect Pulse EventBus ──
                    try:
                        from museclaw.core.event_bus import get_event_bus
                        from museclaw.pulse.heartbeat_focus import HeartbeatFocus

                        event_bus = get_event_bus()
                        _hf_state = str(brain.data_dir / "pulse" / "heartbeat_focus.json")
                        heartbeat_focus = HeartbeatFocus(state_path=_hf_state)
                        adapter.connect_pulse(event_bus, heartbeat_focus)

                        # ── ProactiveBridge: 心跳→大腦→頻道 ──
                        from museclaw.pulse.proactive_bridge import ProactiveBridge
                        proactive_bridge = ProactiveBridge(
                            brain=brain,
                            event_bus=event_bus,
                            heartbeat_focus=heartbeat_focus,
                        )
                        app.state.proactive_bridge = proactive_bridge
                        logger.info("ProactiveBridge connected to EventBus")

                        # ── VITA PulseEngine: 生命力引擎 ──
                        try:
                            from museclaw.pulse.pulse_db import PulseDB
                            from museclaw.pulse.explorer import Explorer
                            from museclaw.pulse.anima_tracker import AnimaTracker
                            from museclaw.pulse.pulse_engine import PulseEngine

                            pulse_db = PulseDB(
                                db_path=str(brain.data_dir / "pulse" / "pulse.db")
                            )
                            explorer = Explorer(
                                brain=brain,
                                data_dir=str(brain.data_dir),
                                searxng_url="http://127.0.0.1:8888",
                            )
                            anima_tracker = AnimaTracker(
                                anima_path=str(brain.data_dir / "ANIMA_MC.json"),
                                pulse_db=pulse_db,
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
                            logger.info("VITA PulseEngine initialized")
                        except Exception as e:
                            logger.warning(f"VITA PulseEngine init failed (degraded): {e}")
                            app.state.pulse_engine = None
                            app.state.pulse_db = None
                            app.state.anima_tracker = None

                        # ── AutonomousQueue: 自主任務佇列 ──
                        from museclaw.pulse.autonomous_queue import AutonomousQueue
                        autonomous_queue = AutonomousQueue(
                            auth_policy=None,  # 使用預設策略
                            budget_monitor=brain.budget_monitor if brain else None,
                            event_bus=event_bus,
                            state_path=str(brain.data_dir / "_system" / "state" / "autonomous_queue.json"),
                        )
                        app.state.autonomous_queue = autonomous_queue
                        logger.info("AutonomousQueue initialized")

                        # ── Nightly Neural Tract: 管線完成 → ProactiveBridge 上下文注入 ──
                        from museclaw.core.event_bus import NIGHTLY_COMPLETED
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
                            except Exception:
                                pass
                        event_bus.subscribe(NIGHTLY_COMPLETED, _on_nightly_completed)
                        logger.info("Nightly → ProactiveBridge neural tract connected")

                        # ── WEE Neural Tract: BRAIN_RESPONSE_COMPLETE → WEEEngine.auto_cycle ──
                        try:
                            from museclaw.core.event_bus import BRAIN_RESPONSE_COMPLETE
                            from museclaw.evolution.wee_engine import get_wee_engine

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
                                except Exception:
                                    pass

                            event_bus.subscribe(BRAIN_RESPONSE_COMPLETE, _on_brain_response)
                            logger.info("WEE neural tract connected (BRAIN_RESPONSE_COMPLETE → auto_cycle)")
                        except Exception as e:
                            logger.warning(f"WEE integration failed (degraded): {e}")

                        # ── ActivityLogger: EventBus → JSONL 日誌 ──
                        try:
                            from museclaw.core.activity_logger import ActivityLogger as _AL
                            _activity_logger = _AL(data_dir=str(brain.data_dir))
                            app.state.activity_logger = _activity_logger

                            # 訂閱關鍵事件
                            _log_events = [
                                "BRAIN_RESPONSE_COMPLETE",
                                "NIGHTLY_COMPLETED",
                                "PULSE_PROACTIVE_SENT",
                                "PULSE_EXPLORATION_DONE",
                                "MORPHENIX_PROPOSAL_CREATED",
                                "MORPHENIX_EXECUTED",
                                "WEE_CYCLE_COMPLETE",
                                "CRYSTAL_CREATED",
                                "SOUL_RING_DEPOSITED",
                            ]
                            for _evt_name in _log_events:
                                _evt_const = getattr(
                                    __import__("museclaw.core.event_bus", fromlist=[_evt_name]),
                                    _evt_name,
                                    _evt_name,
                                )
                                def _make_handler(name):
                                    def _h(data):
                                        try:
                                            _activity_logger.log(name, data, source="event_bus")
                                        except Exception:
                                            pass
                                    return _h
                                event_bus.subscribe(_evt_const, _make_handler(_evt_name))
                            logger.info("ActivityLogger connected to EventBus (%d events)", len(_log_events))
                        except Exception as e:
                            logger.warning(f"ActivityLogger init failed (degraded): {e}")

                    except Exception as e:
                        logger.warning(f"Pulse integration failed (degraded): {e}")

                    logger.info(
                        f"Telegram adapter started successfully"
                        f" (attempt {attempt}/{max_retries})"
                    )
                    telegram_started = True
                    break
                except Exception as e:
                    logger.error(
                        f"Telegram start attempt {attempt}/{max_retries}"
                        f" failed: {e}"
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(5 * attempt)  # 5s, 10s backoff
            if not telegram_started:
                logger.error(
                    "Telegram adapter failed after all retries — "
                    "will remain offline until Gateway restart"
                )
        else:
            logger.warning("TELEGRAM_BOT_TOKEN not set, Telegram disabled")

    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup on shutdown."""
        logger.info("Shutting down MuseClaw Gateway")

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
            except asyncio.CancelledError:
                pass

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

    return app


async def _progress_updater(
    adapter, chat_id: int, status_msg_id: int
) -> None:
    """背景任務：持續更新進度狀態訊息，讓使用者知道 MuseClaw 還在運作.

    階段設計：
    - 0~3s:   ⏳ 收到，正在思考...（由呼叫端先發送）
    - 3s:     🧠 正在深度思考...
    - 10s:    🔍 正在匹配能力模組...
    - 20s:    💭 正在組建回覆...
    - 40s:    ⏳ 仍在處理中，請稍候...
    - 60s+:   🔄 處理中... 已等待 N 分 M 秒
    - 900s:   ⚠️ 已超過 15 分鐘，仍在持續處理...
              （不中斷，繼續等待，除非使用者主動停止）
    """
    stages = [
        (3, "🧠 正在深度思考..."),
        (10, "🔍 正在匹配能力模組..."),
        (20, "💭 正在組建回覆..."),
        (40, "⏳ 仍在處理中，請稍候..."),
    ]
    LONG_WAIT_THRESHOLD = 900  # 15 分鐘
    long_wait_notified = False

    try:
        start = asyncio.get_event_loop().time()
        stage_idx = 0

        while True:
            await asyncio.sleep(2)
            elapsed = asyncio.get_event_loop().time() - start

            # 已預定的階段
            if stage_idx < len(stages):
                threshold, text = stages[stage_idx]
                if elapsed >= threshold:
                    await adapter.update_processing_status(
                        chat_id, status_msg_id, text
                    )
                    stage_idx += 1
            else:
                mins = int(elapsed) // 60
                secs = int(elapsed) % 60
                if mins > 0:
                    time_str = f"{mins} 分 {secs} 秒"
                else:
                    time_str = f"{secs} 秒"

                # 超過 15 分鐘 → 特殊提醒（但不中斷）
                if elapsed >= LONG_WAIT_THRESHOLD and not long_wait_notified:
                    long_wait_notified = True
                    await adapter.update_processing_status(
                        chat_id, status_msg_id,
                        f"⚠️ 已持續處理 {time_str}，"
                        f"任務仍在進行中。\n"
                        f"如需中斷，請傳送「停止」或「暫停」。",
                    )
                    # 額外發送一則獨立提醒（讓使用者收到通知）
                    try:
                        await adapter.application.bot.send_message(
                            chat_id=chat_id,
                            text=(
                                f"⏰ 目前的任務已運行超過 15 分鐘，"
                                f"仍在持續處理中。\n"
                                f"傳送「停止」可中斷當前任務。"
                            ),
                        )
                    except Exception:
                        pass
                else:
                    await adapter.update_processing_status(
                        chat_id, status_msg_id,
                        f"🔄 處理中... 已等待 {time_str}",
                    )

                await asyncio.sleep(13)  # + 前面的 2s ≈ 15s 間隔

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.debug(f"Progress updater stopped: {e}")


async def _telegram_message_pump(adapter) -> None:
    """Background task: receive Telegram messages and respond.

    所有訊息（包括 /start）都經過 MUSEON Brain 處理。
    /start 會觸發命名儀式（如果尚未完成）。

    進度顯示策略（修復版）：
    1. 收到訊息 → 發送「⏳ 收到，正在思考...」+ 啟動 typing + 啟動進度更新器
    2. 處理中 → typing 持續 + 進度訊息持續更新階段
    3. 完成/失敗 → 先發送回覆 → 再刪除進度訊息 + 停止 typing
       （關鍵：回覆送出後才清理，不留空窗期）
    """
    logger.info("Telegram message pump started")

    # ── 指數退避 + 斷路器狀態 ──
    consecutive_errors = 0
    CIRCUIT_BREAKER_THRESHOLD = 10   # 連續錯誤超過此值 → 斷路器開啟
    CIRCUIT_BREAKER_COOLDOWN = 300   # 斷路器冷卻 5 分鐘
    MAX_BACKOFF = 120                # 最大退避 2 分鐘

    while True:
        try:
            # Wait for next message from Telegram
            message = await adapter.receive()

            username = message.metadata.get("username", "unknown")
            chat_id = message.metadata.get("chat_id")
            logger.info(
                f"Telegram [{username}]: {message.content[:80]}"
            )

            # ── 1. Send processing status + start typing + start progress ──
            status_msg_id = None
            progress_task = None

            if chat_id:
                status_msg_id = await adapter.send_processing_status(
                    chat_id, "⏳ 收到，正在思考..."
                )
                await adapter.start_typing(chat_id)

                # 啟動背景進度更新器
                if status_msg_id:
                    progress_task = asyncio.create_task(
                        _progress_updater(adapter, chat_id, status_msg_id)
                    )

            # ── 2. Route through MUSEON Brain ──
            response_text = None
            brain_result = None  # v9.0: raw BrainResponse
            brain = _get_brain()

            try:
                # /start 觸發命名儀式（Brain 內部處理）
                # /reset 強制重跑命名儀式
                if message.content in ("/start", "/reset"):
                    if message.content == "/reset":
                        # 強制重置儀式狀態
                        brain.ceremony._state = {
                            "stage": "not_started",
                            "completed": False,
                            "name_given": False,
                            "questions_asked": False,
                            "answers_received": False,
                        }
                        brain.ceremony._save_state()
                        # 刪除舊 ANIMA_MC 讓儀式重新建立
                        if brain.anima_mc_path.exists():
                            brain.anima_mc_path.unlink()
                        logger.info("命名儀式已重置 by /reset")

                    if not brain.ceremony.is_ceremony_needed():
                        anima_mc = brain._load_anima_mc()
                        my_name = "MuseClaw"
                        boss_name = "你"
                        if anima_mc:
                            my_name = anima_mc.get("identity", {}).get("name", "MuseClaw")
                            boss_name = anima_mc.get("boss", {}).get("name", "你")
                        response_text = (
                            f"嘿，我在。\n\n"
                            f"我是 {my_name}，{boss_name} 的 AI 夥伴。\n"
                            f"有什麼需要幫忙的嗎？\n\n"
                            f"💡 輸入 /reset 可重新命名"
                        )
                    else:
                        brain_result = await brain.process(
                            content="/start",
                            session_id=message.session_id,
                            user_id=message.user_id,
                            source="telegram",
                        )
                else:
                    brain_result = await brain.process(
                        content=message.content,
                        session_id=message.session_id,
                        user_id=message.user_id,
                        source="telegram",
                    )

                # v9.0: Extract text from BrainResponse
                if brain_result is not None and response_text is None:
                    from museclaw.gateway.message import BrainResponse
                    if isinstance(brain_result, BrainResponse):
                        response_text = brain_result.text
                    else:
                        response_text = str(brain_result) if brain_result else ""

            except Exception as proc_err:
                # Brain 處理失敗（API timeout、離線等）→ 回傳錯誤訊息給使用者
                logger.error(f"Brain processing failed: {proc_err}")
                anima_mc = brain._load_anima_mc()
                name = "MuseClaw"
                if anima_mc:
                    name = anima_mc.get("identity", {}).get("name", "MuseClaw")
                response_text = (
                    f"[{name}] 處理過程發生錯誤，請稍後再試。\n\n"
                    f"錯誤類型：{type(proc_err).__name__}\n"
                    f"如果持續發生，請用 /reset 重新啟動。"
                )

            # ── 3. 停止進度更新器 ──
            if progress_task:
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass

            # ── 4. 先更新進度訊息為「✍️ 正在發送...」──
            if status_msg_id and chat_id:
                await adapter.update_processing_status(
                    chat_id, status_msg_id, "✍️ 回覆準備完成，正在發送..."
                )

            # ── 5. Send actual response（先送回覆，再清理進度）──
            response_msg = InternalMessage(
                source="telegram",
                session_id=message.session_id,
                user_id="museclaw",
                content=response_text,
                timestamp=datetime.now(),
                trust_level="core",
                metadata=message.metadata,
            )

            # v9.0: BrainResponse support (text + artifacts)
            from museclaw.gateway.message import BrainResponse
            if isinstance(brain_result, BrainResponse):
                if hasattr(adapter, 'send_response'):
                    success = await adapter.send_response(response_msg, brain_result)
                else:
                    success = await adapter.send(response_msg)
            else:
                success = await adapter.send(response_msg)
            if not success:
                logger.error(f"Failed to send Telegram response to {message.session_id}")

            # ── 6. 回覆已送出，現在才清理進度訊息 + 停止 typing ──
            if status_msg_id and chat_id:
                await adapter.delete_processing_status(chat_id, status_msg_id)
            if chat_id:
                await adapter.stop_typing(chat_id)

            # ── 7. 推播子代理通知（純 CPU 模板）──
            try:
                notifications = brain.drain_notifications()
                for notif in notifications:
                    notif_text = (
                        f"{notif.get('emoji', '📢')} [{notif.get('source', 'system')}] "
                        f"{notif.get('title', '')}\n\n{notif.get('body', '')}"
                    )
                    await adapter.push_notification(notif_text)
            except Exception as notif_err:
                logger.warning(f"推播通知發送失敗: {notif_err}")

            # ── 訊息處理成功，重置退避計數器 ──
            consecutive_errors = 0

        except asyncio.CancelledError:
            logger.info("Telegram message pump cancelled")
            break
        except Exception as e:
            consecutive_errors += 1

            # ── 確保 progress_task 被清理 ──
            if progress_task and not progress_task.done():
                progress_task.cancel()
                try:
                    await progress_task
                except (asyncio.CancelledError, Exception):
                    pass

            # ── 斷路器模式 ──
            if consecutive_errors >= CIRCUIT_BREAKER_THRESHOLD:
                logger.error(
                    f"Telegram message pump 斷路器開啟：連續 {consecutive_errors} 次錯誤，"
                    f"冷卻 {CIRCUIT_BREAKER_COOLDOWN}s。最後錯誤: {e}"
                )
                await asyncio.sleep(CIRCUIT_BREAKER_COOLDOWN)
                consecutive_errors = 0  # 冷卻後重置，給一次機會
            else:
                # ── 指數退避 + 隨機 jitter ──
                import random
                backoff = min(2 ** consecutive_errors, MAX_BACKOFF)
                jitter = random.uniform(0, backoff * 0.3)
                sleep_time = backoff + jitter
                logger.warning(
                    f"Telegram message pump error ({consecutive_errors}/{CIRCUIT_BREAKER_THRESHOLD}): "
                    f"{e}. 退避 {sleep_time:.1f}s"
                )
                await asyncio.sleep(sleep_time)


# ═══════════════════════════════════════════════════════
# CronEngine 系統排程（Layer 1: 硬編碼，不可動搖）
# ═══════════════════════════════════════════════════════

def _register_system_cron_jobs(brain, app=None) -> None:
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
            from museclaw.nightly.nightly_pipeline import NightlyPipeline, build_nightly_html
            from museclaw.core.event_bus import get_event_bus
            event_bus = get_event_bus()
            pipeline = NightlyPipeline(
                workspace=data_dir,
                event_bus=event_bus,
                brain=brain,
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
            logger.error(f"NightlyPipeline failed: {e}")

        # Phase B: 原有 NightlyJob（記憶融合 + Token 優化 + 鍛造檢查 + 健康報告）
        try:
            from museclaw.nightly.job import NightlyJob
            job = NightlyJob(
                memory_store=brain.memory_store,
                llm_client=None,
                data_dir=data_dir,
            )
            result = await job.run()
            logger.info(f"NightlyJob completed: {result.get('status')}")
        except Exception as e:
            logger.error(f"NightlyJob failed: {e}")

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
                await adapter.push_notification(morning_text)
                logger.info("Morning report pushed to Telegram")
        except Exception as e:
            logger.error(f"Morning report failed: {e}")

    cron_engine.add_job(
        _morning_report, trigger="cron", job_id="nightly-morning-report",
        hour=7, minute=30,
    )

    # ── Job 2: 健康心跳（每 30 分鐘）── 純 CPU
    async def _health_heartbeat():
        """純 CPU 健康檢查：Gateway + Telegram + 記憶系統."""
        try:
            report = {
                "timestamp": datetime.now().isoformat(),
                "gateway": "alive",
                "brain": "alive" if brain else "dead",
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
            logger.error(f"Health heartbeat failed: {e}")

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
            logger.error(f"Memory flush failed: {e}")

    cron_engine.add_job(
        _memory_flush, trigger="interval", job_id="memory-flush",
        hours=6,
    )

    # ── Job 4: Skill 偵查掃描（每天 04:00）── CPU 過濾，LLM 評估
    async def _skill_acquisition_scan():
        """Skill Acquisition Pipeline: 偵測缺口 → 搜尋 → 過濾."""
        try:
            from museclaw.nightly.skill_scout import SkillScout
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
            logger.error(f"Skill acquisition scan failed: {e}")

    cron_engine.add_job(
        _skill_acquisition_scan, trigger="cron", job_id="skill-acquisition-scan",
        hour=4, minute=0,
    )

    # ── Job 5: Guardian L1 巡檢（每 30 分鐘）── 純 CPU
    async def _guardian_l1():
        """Guardian L1: 基礎設施巡檢 — Gateway / Telegram / .env"""
        try:
            from museclaw.guardian.daemon import GuardianDaemon
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
            logger.error(f"Guardian L1 failed: {e}")

    cron_engine.add_job(
        _guardian_l1, trigger="interval", job_id="guardian-l1",
        minutes=30,
    )

    # ── Job 6: Guardian L2+L3 深度巡檢（每 6 小時）── 純 CPU
    async def _guardian_deep():
        """Guardian L2+L3: 資料完整性 + 神經束連通性"""
        try:
            from museclaw.guardian.daemon import GuardianDaemon
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
            logger.error(f"Guardian L2+L3 failed: {e}")

    cron_engine.add_job(
        _guardian_deep, trigger="interval", job_id="guardian-deep",
        hours=6,
    )

    # ── Job 7: 工具自動發現（每天 05:00）── SearXNG 搜尋
    async def _tool_discovery_scan():
        """每天 5am 搜尋新的免費自建 AI 工具."""
        try:
            from museclaw.tools.tool_registry import ToolRegistry
            from museclaw.tools.tool_discovery import ToolDiscovery

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
                    await adapter.push_notification(msg)
            else:
                logger.info("Tool discovery: no new recommendations")
        except Exception as e:
            logger.error(f"Tool discovery scan failed: {e}")

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
            logger.error(f"VITA SysPulse failed: {e}")

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
            logger.error(f"VITA BreathPulse failed: {e}")

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
            logger.error(f"VITA morning failed: {e}")

    # Replace old morning report with VITA morning
    try:
        cron_engine.remove_job("nightly-morning-report")
    except Exception:
        pass
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
            logger.error(f"VITA evening failed: {e}")

    cron_engine.add_job(
        _vita_evening, trigger="cron", job_id="vita-evening",
        hour=22, minute=0,
    )

    # ── Job 11.5: VITA 自主探索（每天 3 次：09:00 / 14:00 / 20:00）──
    async def _vita_exploration(trigger: str):
        """VITA SoulPulse: 自主探索 — 好奇心驅動外出探索世界."""
        try:
            if not app:
                return
            engine = getattr(app.state, "pulse_engine", None)
            if not engine:
                return
            result = await engine.soul_pulse(trigger=trigger)
            action = result.get("action", "?")
            explored = result.get("percrl", {}).get("explore", "skipped")
            logger.info(f"VITA exploration ({trigger}): action={action}, explore={explored}")
        except Exception as e:
            logger.error(f"VITA exploration ({trigger}) failed: {e}")

    async def _vita_morning_exploration():
        await _vita_exploration("morning")

    async def _vita_curiosity_exploration():
        await _vita_exploration("curiosity")

    async def _vita_mission_exploration():
        await _vita_exploration("mission")

    cron_engine.add_job(
        _vita_morning_exploration, trigger="cron", job_id="vita-explore-morning",
        hour=9, minute=0,
    )
    cron_engine.add_job(
        _vita_curiosity_exploration, trigger="cron", job_id="vita-explore-curiosity",
        hour=14, minute=0,
    )
    cron_engine.add_job(
        _vita_mission_exploration, trigger="cron", job_id="vita-explore-mission",
        hour=20, minute=0,
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
                    await adapter.push_notification(msg)
        except Exception as e:
            logger.error(f"Morphenix auto-approve failed: {e}")

    cron_engine.add_job(
        _morphenix_auto_approve, trigger="interval",
        job_id="morphenix-auto-approve",
        hours=6,
    )

    # ── 承諾到期檢查（每 15 分鐘）──
    async def _commitment_periodic_check():
        """定期檢查承諾到期狀態，逾期時透過 ProactiveBridge 推送."""
        try:
            from museclaw.pulse.commitment_tracker import CommitmentTracker
            from museclaw.pulse.pulse_db import PulseDB

            _project_root = _get_project_root()
            _pulse_path = os.path.join(_project_root, "data", "pulse", "pulse.db")
            _pdb = PulseDB(_pulse_path)
            tracker = CommitmentTracker(pulse_db=_pdb)

            result = tracker.periodic_check()
            if result.get("overdue_count", 0) > 0:
                logger.warning(
                    f"[Commitment] 逾期承諾: {result['overdue_count']} 筆 "
                    f"({result['overdue_ids'][:3]})"
                )
                # 透過 Telegram adapter 主動推送逾期提醒
                if adapter and hasattr(adapter, "push_notification"):
                    overdue = tracker.get_overdue_commitments()
                    if overdue:
                        msg = "⚠️ 承諾提醒：\n"
                        for c in overdue[:3]:
                            msg += f"- {c.get('promise_text', '?')[:60]}\n"
                        msg += "\n（霓裳正在處理中，請稍候）"
                        await adapter.push_notification(msg)

                # ANIMA zhen -1 for overdue
                try:
                    for _oid in result.get("overdue_ids", [])[:3]:
                        _pdb.log_anima_change(
                            element="zhen", delta=-1,
                            reason=f"承諾逾期: {_oid}",
                            absolute_after=0,
                        )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Commitment periodic check failed: {e}")

    cron_engine.add_job(
        _commitment_periodic_check, trigger="interval",
        job_id="commitment-check",
        minutes=15,
    )

    logger.info(
        "System cron jobs registered: "
        "nightly-fusion(03:00), health-heartbeat(30min), "
        "memory-flush(6h), skill-acquisition-scan(04:00), "
        "tool-discovery(05:00), guardian-l1(30min), guardian-deep(6h), "
        "vita-sys-pulse(5min), vita-breath-pulse(30min), "
        "vita-morning(07:30), vita-evening(22:00), "
        "morphenix-auto-approve(6h), commitment-check(15min)"
    )


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
        f"server may fail to start"
    )


def main() -> None:
    """Run the Gateway server (localhost only)."""
    # ── Configure application logging BEFORE anything else ──
    _configure_logging()

    # ── Pre-start: 清理殭屍進程（防止 port 衝突）──
    _pre_start_cleanup(8765)

    app = create_app()

    # CRITICAL: Only bind to localhost (127.0.0.1)
    # This prevents remote access to the Gateway
    uvicorn.run(
        app,
        host="127.0.0.1",  # localhost only
        port=8765,
        log_level="info",
    )


if __name__ == "__main__":
    main()
