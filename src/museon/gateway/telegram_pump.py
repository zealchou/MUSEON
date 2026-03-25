"""
Telegram Message Pump — Telegram 訊息處理管線

從 server.py 拆分出來的 Telegram 訊息接收、處理、回覆邏輯。
包含：_progress_updater、_handle_telegram_message、_telegram_message_pump。

原檔案：server.py（705 行）
"""

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger("museon.gateway.telegram_pump")

# 由 server.py 在啟動時注入
_server_ctx = {
    "get_brain": None,
    "get_llm_semaphore": None,
    "session_manager": None,
    "data_dir": None,
}


def init_telegram_pump(get_brain, get_llm_semaphore, session_manager, data_dir):
    """由 server.py 在 startup 時呼叫，注入依賴。"""
    _server_ctx["get_brain"] = get_brain
    _server_ctx["get_llm_semaphore"] = get_llm_semaphore
    _server_ctx["session_manager"] = session_manager
    _server_ctx["data_dir"] = data_dir


def _get_brain():
    return _server_ctx["get_brain"]()


def _get_llm_semaphore():
    return _server_ctx["get_llm_semaphore"]()


# 以下函數來自 server.py 原始碼


async def _progress_updater(
    adapter, chat_id: int, status_msg_id: int
) -> None:
    """背景任務：持續更新進度狀態訊息，讓使用者知道 MUSEON 還在運作.

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
            await asyncio.sleep(5)  # 從 2s 提高到 5s，降低 API 呼叫頻率避免 Flood Control
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
                    except Exception as e:
                        logger.debug(f"[SERVER] operation failed (degraded): {e}")
                else:
                    await adapter.update_processing_status(
                        chat_id, status_msg_id,
                        f"🔄 處理中... 已等待 {time_str}",
                    )

                await asyncio.sleep(13)  # + 前面的 2s ≈ 15s 間隔

    except asyncio.CancelledError as e:
        logger.debug(f"[SERVER] async op failed (degraded): {e}")
    except Exception as e:
        logger.debug(f"Progress updater stopped: {e}")


# ═══════════════════════════════════════════
# Brain 90 秒 SLA + Circuit Breaker
# ═══════════════════════════════════════════

_SLA_TIMEOUT_SECONDS = 90


async def _brain_process_with_sla(
    brain,
    adapter,
    chat_id,
    *,
    content: str,
    session_id: str,
    user_id: str,
    source: str = "telegram",
    metadata=None,
    semaphore=None,
):
    """包裝 brain.process()，提供 90 秒 SLA 保證 + Circuit Breaker 保護.

    - 90 秒未完成 → 先送暫時回覆，背景繼續等
    - Circuit Breaker OPEN → 直接返回降級回覆
    - brain.process() 失敗 → 記錄到 Circuit Breaker
    """
    from museon.governance.bulkhead import get_brain_circuit_breaker

    cb = get_brain_circuit_breaker()

    # ── Circuit Breaker 檢查 ──
    if cb.is_open:
        logger.warning(f"BrainCircuitBreaker OPEN — returning fallback for {session_id}")
        return cb.fallback_message

    # ── 實際呼叫 brain.process()（worker subprocess 優先，fallback in-process）──
    async def _do_process():
        # 嘗試用 subprocess worker（process 隔離）
        try:
            from museon.gateway.brain_worker import get_brain_worker_manager
            worker = get_brain_worker_manager()
            if worker:
                _trace = (metadata or {}).get("trace_id", "")
                result_dict = await worker.process(
                    content=content,
                    session_id=session_id,
                    user_id=user_id,
                    source=source,
                    metadata=metadata,
                    trace_id=_trace,
                )
                # 還原為 BrainResponse 或 str
                from museon.gateway.message import BrainResponse
                return BrainResponse(text=result_dict.get("text", ""))
        except Exception as _w_err:
            logger.warning(f"BrainWorker failed, falling back to in-process: {_w_err}")

        # Fallback: in-process brain.process()（使用 token bucket 取代 semaphore）
        try:
            from museon.llm.rate_limiter import get_api_bucket
            _bucket = get_api_bucket()
        except Exception:
            _bucket = semaphore  # 最終 fallback 回 semaphore

        if _bucket:
            async with _bucket:
                return await brain.process(
                    content=content,
                    session_id=session_id,
                    user_id=user_id,
                    source=source,
                    metadata=metadata,
                )
        else:
            return await brain.process(
                content=content,
                session_id=session_id,
                user_id=user_id,
                source=source,
                metadata=metadata,
            )

    brain_task = asyncio.create_task(_do_process())
    sla_notified = False

    try:
        # 先等 90 秒
        result = await asyncio.wait_for(
            asyncio.shield(brain_task), timeout=_SLA_TIMEOUT_SECONDS
        )
        cb.record_success()
        return result
    except asyncio.TimeoutError:
        # 90 秒到了，Brain 還在思考 → 送暫時回覆
        sla_notified = True
        if chat_id:
            try:
                await adapter.application.bot.send_message(
                    chat_id=chat_id,
                    text="這個問題需要多想一下，馬上回覆你 🧠",
                )
            except Exception as e:
                logger.debug(f"SLA interim message send failed: {e}")

    # 繼續等 brain 完成（無上限，由 progress_updater 的 15 分鐘提醒覆蓋）
    try:
        result = await brain_task
        cb.record_success()
        return result
    except Exception as e:
        cb.record_failure(e)
        raise


async def _handle_telegram_message(adapter, message) -> None:
    """Process a single Telegram message (runs concurrently per session).

    從 _telegram_message_pump 提取的獨立處理函數，
    每則訊息 spawn 為獨立 async task，實現多群組/多用戶並行處理。

    進度顯示策略：
    1. 收到訊息 → 發送「⏳ 收到，正在思考...」+ 啟動 typing + 啟動進度更新器
    2. 處理中 → typing 持續 + 進度訊息持續更新階段
    3. 完成/失敗 → 先發送回覆 → 再刪除進度訊息 + 停止 typing
    """
    # ── 跨分支共用 import（避免條件分支內 import 導致 UnboundLocalError）──
    from museon.gateway.message import BrainResponse, InternalMessage

    progress_task = None
    _tid = message.trace_id  # 全鏈路追蹤 ID
    try:
            username = message.metadata.get("username", "unknown")
            chat_id = message.metadata.get("chat_id")
            is_group = message.metadata.get("is_group", False)
            is_owner = message.metadata.get("is_owner", False)
            sender_name = message.metadata.get("sender_name", "")
            group_id = message.metadata.get("group_id")
            logger.info(
                f"[{_tid}] Telegram [{username}]: {message.content[:80]}"
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

            # ── 1.5. 過濾空訊息（不送進 Brain）──
            if message.content in ("[empty]", "") or not message.content.strip():
                logger.info(f"[{_tid}] Skipping empty/placeholder message for session {message.session_id}")
                try:
                    from museon.gateway.message_queue_store import get_message_queue_store
                    get_message_queue_store().mark_done(_tid)
                except Exception:
                    pass
                return

            # ── 2. Route through MUSEON Brain (with session lock + LLM semaphore) ──
            response_text = None
            brain_result = None  # v9.0: raw BrainResponse
            brain = _get_brain()
            _sem = _get_llm_semaphore()

            # Acquire session lock — 排隊等待（不 drop 訊息）+ 優先度 + 預算檢查
            _session_locked = False
            if message.session_id and _server_ctx["session_manager"]:
                # 分類優先度
                from museon.gateway.session import classify_priority
                _priority = classify_priority(
                    message.session_id, is_owner=is_owner
                )

                # Per-tenant 預算檢查
                from museon.llm.rate_limiter import get_tenant_limiter
                _tl = get_tenant_limiter()
                if not _tl.check(message.session_id):
                    logger.warning(
                        f"Session {message.session_id} daily quota exceeded"
                    )
                    response_text = "今日的對話額度已用完，明天再聊 🌙"

                _queue_depth = _server_ctx["session_manager"].get_queue_depth(message.session_id)
                if _queue_depth > 0 and response_text is None:
                    logger.info(
                        f"Session {message.session_id}: queuing "
                        f"(depth={_queue_depth + 1}, P{_priority})"
                    )
                    if status_msg_id and chat_id:
                        await adapter.update_processing_status(
                            chat_id, status_msg_id,
                            f"⏳ 前面還有 {_queue_depth} 則訊息處理中，排隊等候..."
                        )

                if response_text is None:
                    _session_locked = await _server_ctx["session_manager"].wait_and_acquire(
                        message.session_id, timeout=None, priority=_priority
                    )

            try:
                # ── Check if owner is responding to a sensitivity escalation ──
                if not is_group and is_owner:
                    try:
                        from museon.governance.multi_tenant import get_escalation_queue
                        eq = get_escalation_queue()
                        # Bug fix: 剝離 Reply 前綴，只取使用者實際輸入
                        _raw = message.content.strip()
                        import re as _re
                        _stripped = _re.sub(
                            r"^\[回覆.*?的訊息：.*?\]\s*", "", _raw, flags=_re.DOTALL
                        ).strip()
                        content_lower = _stripped.lower() if _stripped else _raw.lower()

                        # Bug fix: 否定詞優先匹配（「不行」「不可以」必須先於「行」「可以」）
                        _DENY_KW = ("不行", "不可以", "不要", "拒絕", "no", "deny", "不准", "別回答")
                        _APPROVE_KW = ("可以", "yes", "ok", "好", "行", "沒問題", "回答")
                        _is_deny = any(kw in content_lower for kw in _DENY_KW)
                        _is_approve = any(kw in content_lower for kw in _APPROVE_KW) and not _is_deny

                        # ── Escalation 精確匹配：優先用 #eid，fallback 用 FIFO ──
                        _target_eid = None
                        import re as _eid_re
                        _eid_match = _eid_re.search(r'#([a-f0-9]{8})', content_lower)
                        if _eid_match:
                            _target_eid = _eid_match.group(1)

                        if _is_approve:
                            # 精確匹配優先
                            if _target_eid:
                                _resolved = eq.resolve_by_id(_target_eid, allowed=True)
                                eid = _target_eid if _resolved else None
                            else:
                                eid = eq.resolve_latest(allowed=True)
                            if eid:
                                entry = eq.get(eid)
                                if entry:
                                    _q = entry.get("question", "")
                                    _gid = entry.get("group_id")
                                    _asker = entry.get("asker_name", "對方")
                                    response_text = f"好，正在回覆 {_asker} 的問題（#{eid}）。"
                                    # Actually process & reply to group
                                    if _gid and _q:
                                        try:
                                            _gr = await brain.process(
                                                content=_q,
                                                session_id=f"telegram_group_{abs(_gid)}",
                                                user_id="external",
                                                source="telegram",
                                                metadata={"permission_level": "external", "sender_name": _asker, "is_group": True},
                                            )
                                            if isinstance(_gr, BrainResponse):
                                                _reply = _gr.text or "好的，讓我想想看。"
                                            else:
                                                _reply = str(_gr) if _gr else "好的，讓我想想看。"
                                            # ⛔ ResponseGuard：驗證 escalation 的 group_id
                                            from museon.governance.response_guard import ResponseGuard
                                            if ResponseGuard.validate_escalation(eid, _gid, _gid, f"escalation_approve asker={_asker}"):
                                                await adapter.application.bot.send_message(
                                                    chat_id=_gid, text=_reply
                                                )
                                                logger.info(f"Group escalation reply sent to {_gid} for {_asker} (eid={eid})")
                                            else:
                                                logger.critical(f"Escalation reply BLOCKED by ResponseGuard: eid={eid} gid={_gid}")
                                        except Exception as _grp_err:
                                            logger.error(f"Group reply after escalation failed: {_grp_err}", exc_info=True)
                        elif _is_deny:
                            if _target_eid:
                                _resolved = eq.resolve_by_id(_target_eid, allowed=False)
                                eid = _target_eid if _resolved else None
                            else:
                                eid = eq.resolve_latest(allowed=False)
                            if eid:
                                entry = eq.get(eid)
                                if entry:
                                    _gid = entry.get("group_id")
                                    _asker = entry.get("asker_name", "對方")
                                    response_text = f"好，已記錄。{_asker} 那邊我會禮貌拒絕（#{eid}）。"
                                    if _gid:
                                        try:
                                            from museon.governance.response_guard import ResponseGuard
                                            if ResponseGuard.validate_escalation(eid, _gid, _gid, f"escalation_deny asker={_asker}"):
                                                await adapter.application.bot.send_message(
                                                    chat_id=_gid,
                                                    text="這個問題目前不方便回答，抱歉。有其他需要歡迎繼續詢問。",
                                                )
                                            else:
                                                logger.critical(f"Escalation decline BLOCKED by ResponseGuard: eid={eid} gid={_gid}")
                                        except Exception as _grp_err:
                                            logger.error(f"Group decline send failed: {_grp_err}", exc_info=True)
                    except Exception as _esc_err:
                        logger.debug(f"Escalation check error: {_esc_err}")

                    # ── Check if owner is responding to a tool authorization ──
                    try:
                        from museon.gateway.authorization import get_tool_auth_queue
                        taq = get_tool_auth_queue()
                        if taq.has_pending():
                            if _is_approve:
                                tid = taq.resolve_latest(approved=True)
                                if tid:
                                    _tentry = taq.get(tid)
                                    _tname = _tentry.get("tool_name", "?") if _tentry else "?"
                                    _tusr = _tentry.get("user_name", "?") if _tentry else "?"
                                    response_text = f"✅ 工具 {_tname} 已允許（{_tusr}）"
                            elif _is_deny:
                                tid = taq.resolve_latest(approved=False)
                                if tid:
                                    _tentry = taq.get(tid)
                                    _tname = _tentry.get("tool_name", "?") if _tentry else "?"
                                    _tusr = _tentry.get("user_name", "?") if _tentry else "?"
                                    response_text = f"❌ 工具 {_tname} 已拒絕（{_tusr}）"
                    except Exception as _auth_err:
                        logger.debug(f"Tool auth check error: {_auth_err}")

                # /start 觸發命名儀式（Brain 內部處理）
                # /reset 強制重跑命名儀式
                if response_text is None and message.content in ("/start", "/reset"):
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
                        my_name = "MUSEON"
                        boss_name = "你"
                        if anima_mc:
                            my_name = anima_mc.get("identity", {}).get("name", "MUSEON")
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
                elif response_text is None:
                    if is_group:
                        # Group message processing (owner or non-owner, @mentioned)
                        # Phase 1: Multi-tenant setup (imports, context, sensitivity check)
                        # Errors here → "忙碌中" for non-owner (setup failure)
                        _mt_ready = False
                        _brain_content = None
                        _brain_metadata = None
                        try:
                            from museon.governance.multi_tenant import (
                                get_sensitivity_checker, get_escalation_queue, ExternalAnimaManager
                            )
                            from museon.governance.group_context import get_group_context_store
                            from pathlib import Path as _Path
                            import uuid as _uuid

                            # Load boss name from ANIMA_MC so Brain recognizes owner
                            _boss_name = ""
                            _owner_ids = set()
                            try:
                                anima_mc = brain._load_anima_mc()
                                if anima_mc:
                                    _boss_name = anima_mc.get("boss", {}).get("name", "")
                                _owner_ids = set(adapter.trusted_user_ids) if hasattr(adapter, "trusted_user_ids") else set()
                            except Exception as e:
                                logger.debug(f"[SERVER] brain failed (degraded): {e}")

                            # Load recent group context for intelligent replies
                            _ctx_store = get_group_context_store()
                            _group_context = _ctx_store.format_context_for_prompt(
                                group_id or 0, limit=20,
                                owner_ids=_owner_ids, boss_name=_boss_name,
                            )

                            if not is_owner:
                                # Sensitivity check for non-owner messages
                                checker = get_sensitivity_checker()
                                level, reason = checker.check(message.content)

                                if level:
                                    eq = get_escalation_queue()
                                    eid = _uuid.uuid4().hex[:8]
                                    eq.add(eid, message.content, sender_name, group_id or 0, level)

                                    dm_text = (
                                        f"【群組敏感問題 - {level}】#{eid}\n\n"
                                        f"{sender_name} 在群組問了：\n「{message.content[:200]}」\n\n"
                                        f"原因：{reason}\n\n"
                                        f"可以回答嗎？\n"
                                        f"回覆「#{eid} 可以」→ 精確回答此問題\n"
                                        f"回覆「#{eid} 不行」→ 精確拒絕此問題\n"
                                        f"或直接「可以」/「不行」→ 處理最舊一則\n"
                                        f"（10 分鐘無回應 → 預設禮貌拒絕）"
                                    )
                                    await adapter.send_dm_to_owner(dm_text)
                                    response_text = f"這個問題我需要先確認一下，稍等。"
                                else:
                                    # Not sensitive: update external anima, prepare content for brain
                                    data_dir = _Path(brain.data_dir)
                                    ext_mgr = ExternalAnimaManager(data_dir)
                                    ext_mgr.update(message.user_id, display_name=sender_name, group_id=group_id)

                                    group_prefix = f"[群組會議] {sender_name} 問：\n"
                                    _brain_content = group_prefix + message.content
                                    if _group_context:
                                        _brain_content = _group_context + "\n\n" + _brain_content
                                    _brain_metadata = {"is_group": True, "sender_name": sender_name}
                                    _mt_ready = True
                            else:
                                # Owner in group: use boss_name so Brain recognizes its boss
                                _display = _boss_name or sender_name
                                group_prefix = f"[群組] {_display}（老闆）說：\n"
                                _brain_content = group_prefix + message.content
                                if _group_context:
                                    _brain_content = _group_context + "\n\n" + _brain_content
                                _brain_metadata = {"is_group": True, "sender_name": _display, "is_owner": True}
                                _mt_ready = True
                        except Exception as _mt_err:
                            logger.error(f"Multi-tenant setup error: {_mt_err}", exc_info=True)
                            if is_owner:
                                # Owner fallback: process without multi-tenant context
                                _brain_content = message.content
                                _brain_metadata = {"is_group": True, "sender_name": sender_name, "is_owner": True}
                                _mt_ready = True
                            else:
                                # Non-owner: multi-tenant setup failed, cannot safely determine sensitivity
                                response_text = "目前系統忙碌中，請稍後再試。"
                                logger.warning(f"Blocked non-owner group msg due to multi-tenant setup error: {_mt_err}")

                        # Phase 2: Brain processing (OUTSIDE multi-tenant try/except)
                        # brain.process() errors propagate to outer handler (line ~3834)
                        # which has proper error messages for both owner and non-owner
                        if _mt_ready and response_text is None:
                            if _brain_metadata is None:
                                _brain_metadata = {}
                            _brain_metadata["trace_id"] = _tid
                            brain_result = await _brain_process_with_sla(
                                brain, adapter, chat_id,
                                content=_brain_content,
                                session_id=message.session_id,
                                user_id=message.user_id,
                                source="telegram",
                                metadata=_brain_metadata,
                                semaphore=_sem,
                            )
                    else:
                        # Normal DM processing (owner or trusted user)
                        _dm_metadata = {**(message.metadata or {}), "trace_id": _tid} if is_group else {"trace_id": _tid}
                        brain_result = await _brain_process_with_sla(
                            brain, adapter, chat_id,
                            content=message.content,
                            session_id=message.session_id,
                            user_id=message.user_id,
                            source="telegram",
                            metadata=_dm_metadata,
                            semaphore=_sem,
                        )

                # v9.0: Extract text from BrainResponse
                if brain_result is not None and response_text is None:
                    if isinstance(brain_result, BrainResponse):
                        response_text = brain_result.text
                        # Per-tenant token 消耗追蹤
                        _used = getattr(brain_result, 'total_tokens', 0)
                        if _used and message.session_id:
                            try:
                                from museon.llm.rate_limiter import get_tenant_limiter
                                get_tenant_limiter().consume(
                                    message.session_id, _used
                                )
                            except Exception:
                                pass
                    else:
                        response_text = str(brain_result) if brain_result else ""

                # ── v10.0: InteractionRequest 互動攔截 ──
                if isinstance(brain_result, BrainResponse) and brain_result.has_interaction():
                    try:
                        from museon.gateway.interaction import get_interaction_queue
                        interaction_req = brain_result.interaction
                        interaction_queue = get_interaction_queue()

                        # 提交到佇列
                        interaction_queue.submit(interaction_req)

                        # 先發送 Brain 的文字回應（說明為什麼要問）
                        if response_text and response_text.strip():
                            pre_msg = InternalMessage(
                                source="telegram",
                                session_id=message.session_id,
                                user_id="museon",
                                content=response_text,
                                timestamp=datetime.now(),
                                trust_level="core",
                                metadata=message.metadata,
                            )
                            await adapter.send(pre_msg)

                        # 呈現互動選項
                        await adapter.present_choices(
                            chat_id=str(chat_id),
                            request=interaction_req,
                            interaction_queue=interaction_queue,
                        )

                        # 停止 typing + 進度（等待使用者選擇期間不顯示 typing）
                        if chat_id:
                            await adapter.stop_typing(chat_id)
                        if progress_task:
                            progress_task.cancel()
                            try:
                                await progress_task
                            except asyncio.CancelledError:
                                pass
                        if status_msg_id and chat_id:
                            await adapter.delete_processing_status(chat_id, status_msg_id)
                            status_msg_id = None

                        # 等待使用者回應
                        interaction_resp = await interaction_queue.wait_for_response(
                            interaction_req.question_id,
                            timeout=interaction_req.timeout_seconds,
                        )

                        # 將使用者選擇回饋給 Brain 做後續處理
                        if interaction_resp and not interaction_resp.timed_out:
                            choice_text = interaction_resp.get_choice_text()
                            logger.info(
                                f"InteractionResponse received: "
                                f"qid={interaction_req.question_id}, choice={choice_text}"
                            )

                            # 重新啟動 typing
                            if chat_id:
                                await adapter.start_typing(chat_id)

                            followup_result = await brain.process(
                                content=f"[使用者選擇] {choice_text}",
                                session_id=message.session_id,
                                user_id=message.user_id,
                                source="telegram",
                                metadata={
                                    **(message.metadata or {}),
                                    "interaction_response": True,
                                    "question_id": interaction_req.question_id,
                                    "original_context": interaction_req.context,
                                },
                            )

                            # 更新 brain_result 和 response_text 為後續回應
                            brain_result = followup_result
                            if isinstance(followup_result, BrainResponse):
                                response_text = followup_result.text
                            elif followup_result:
                                response_text = str(followup_result)
                            else:
                                response_text = ""
                        else:
                            logger.info(
                                f"InteractionRequest timed out: "
                                f"qid={interaction_req.question_id}"
                            )
                            response_text = ""  # 超時不再發送額外訊息

                    except Exception as interaction_err:
                        logger.error(
                            f"InteractionRequest handling failed: {interaction_err}",
                            exc_info=True,
                        )
                        # 降級為純文字回應（已在上方提取）

                # ── 自癒：空回應 fallback（防止 Telegram 拒絕空訊息 or [empty] 佔位符洩漏）──
                if not response_text or not response_text.strip() or response_text.strip() == "[empty]":
                    logger.warning(f"[{_tid}] Brain returned empty/placeholder response, applying fallback")
                    _mc = brain._load_anima_mc()
                    _name = _mc.get("identity", {}).get("name", "霓裳") if _mc else "霓裳"
                    response_text = f"[{_name}] 我剛才想了一下，但沒有組織出回應。你可以再說一次嗎？"

            except Exception as proc_err:
                # Brain 處理失敗（API timeout、離線等）→ 回傳錯誤訊息給使用者
                logger.error(f"Brain processing failed: {proc_err}", exc_info=True)
                anima_mc = brain._load_anima_mc()
                name = "MUSEON"
                if anima_mc:
                    name = anima_mc.get("identity", {}).get("name", "MUSEON")
                # v3.0: 所有用戶統一顯示錯誤細節（含群組外部用戶）
                response_text = (
                    f"[{name}] 處理過程發生錯誤，請稍後再試。\n\n"
                    f"錯誤類型：{type(proc_err).__name__}\n"
                    f"如果持續發生，請用 /reset 重新啟動。"
                )
            finally:
                # Release session lock
                if _session_locked and message.session_id and _server_ctx["session_manager"]:
                    await _server_ctx["session_manager"].release(message.session_id)

            # ── 3. 停止進度更新器 ──
            if progress_task:
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError as e:
                    logger.debug(f"[SERVER] operation failed (degraded): {e}")

            # ── 4. 先更新進度訊息為「✍️ 正在發送...」──
            if status_msg_id and chat_id:
                await adapter.update_processing_status(
                    chat_id, status_msg_id, "✍️ 回覆準備完成，正在發送..."
                )

            # ── 5. Send actual response（先送回覆，再清理進度）──
            # v10.8: L2 結構化剝離 — 移除 AI 內部思考區塊（比 L3 sanitize 更早、更精準）
            import re as _re
            # 剝離整段【標記】...內容（貪婪到下一個【或行尾）
            response_text = _re.sub(
                r"【[^】]{1,20}】[^\n]*(?:\n(?![\n【]).*)*",
                "", response_text,
            ).strip()
            # 剝離「已成功...群組」操作確認句（整行移除）
            response_text = _re.sub(
                r"^.*已成功(?:發送|回覆|傳送).{0,30}(?:群組|訊息|頻道).*$",
                "", response_text, flags=_re.MULTILINE,
            ).strip()
            # 清除剝離後可能殘留的連續空行
            response_text = _re.sub(r"\n{3,}", "\n\n", response_text)

            # v10.7: L3 群組回覆內容清理（最後防線黑名單）+ metadata 深複製 + 跨群驗證
            from museon.governance.response_guard import ResponseGuard
            _is_group = message.metadata.get("is_group", False)
            response_text = ResponseGuard.sanitize_for_group(response_text, _is_group)

            # v10.9: 二次空值防護 — sanitization 後再檢查一次
            # 根因：line 718 的空值檢查在 sanitization 之前，
            # Brain 回覆若全由內部標記組成（【思考路徑】、Skill 路由鏈等），
            # 經 L2 剝離 + ResponseGuard 清理後變成空字串，
            # InternalMessage.__post_init__ 會把 "" 轉成 "[empty]" 並送出。
            if not response_text or not response_text.strip():
                logger.warning(f"[{_tid}] Response became empty after sanitization, applying fallback")
                _mc = brain._load_anima_mc()
                _name = _mc.get("identity", {}).get("name", "MUSEON") if _mc else "MUSEON"
                response_text = f"我想了一下，但沒有組織好回應。可以再說一次嗎？"

            response_msg = InternalMessage(
                source="telegram",
                session_id=message.session_id,
                user_id="museon",
                content=response_text,
                timestamp=datetime.now(),
                trust_level="core",
                metadata={**message.metadata},  # v10.7: 深複製，不共享引用
            )

            # ⛔ v10.7 ResponseGuard：session_id ↔ chat_id 交叉驗證
            _raw_cid = message.metadata.get("chat_id", "")
            _session_group = message.session_id.rsplit("_", 1)[-1] if "telegram_group_" in message.session_id else ""
            _cross_leak = False
            if _session_group and _raw_cid:
                if not ResponseGuard.validate(
                    _session_group, _raw_cid,
                    context=f"pump session={message.session_id}",
                ):
                    _cross_leak = True
            success = False
            if _cross_leak:
                logger.warning("跨群污染已阻擋，本次不發送回覆")
                success = True  # 不算失敗，只是被阻擋
            else:
                # v9.0: BrainResponse support (text + artifacts)
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
                logger.warning(f"[{_tid}] 推播通知發送失敗: {notif_err}")

            # ── 8. 標記訊息處理完成（持久化佇列）──
            try:
                from museon.gateway.message_queue_store import get_message_queue_store
                get_message_queue_store().mark_done(_tid)
            except Exception:
                pass
            logger.info(f"[{_tid}] Message handling completed for {message.session_id}")

    except Exception as handle_err:
        logger.error(f"[{_tid}] Message handler error for {message.session_id}: {handle_err}", exc_info=True)
        try:
            from museon.gateway.message_queue_store import get_message_queue_store
            get_message_queue_store().mark_failed(_tid, str(handle_err))
        except Exception:
            pass
        # ── 確保 progress_task 被清理 ──
        if progress_task and not progress_task.done():
            progress_task.cancel()
            try:
                await progress_task
            except (asyncio.CancelledError, Exception):
                pass


async def _recover_pending_messages(adapter) -> int:
    """Gateway 重啟時恢復未處理的訊息."""
    try:
        from museon.gateway.message_queue_store import get_message_queue_store
        from museon.gateway.message import InternalMessage
        store = get_message_queue_store()
        pending = store.recover_pending()
        if not pending:
            return 0
        logger.info(f"Recovering {len(pending)} pending messages from queue store")
        for msg_dict in pending:
            try:
                message = InternalMessage.from_dict(msg_dict)
                asyncio.create_task(_handle_telegram_message(adapter, message))
                logger.info(f"[{message.trace_id}] Recovered and re-queued")
            except Exception as e:
                trace_id = msg_dict.get("trace_id", "?")
                logger.error(f"[{trace_id}] Failed to recover message: {e}")
                store.mark_failed(trace_id, str(e))
        return len(pending)
    except Exception as e:
        logger.warning(f"Message recovery failed (non-fatal): {e}")
        return 0


async def _telegram_message_pump(adapter) -> None:
    """Background task: receive and dispatch Telegram messages concurrently.

    三層並行架構（L1 調度員模式）：
    - 主迴圈只負責 receive → spawn task → 立刻接下一則
    - 每則訊息的處理（Brain 思考、回覆）在獨立 async task 中執行
    - 不同 session（群組/私訊）完全並行
    - 同一 session 由 session_manager lock 保護不會衝突
    """
    logger.info("Telegram message pump started (concurrent mode)")

    # ── 啟動時恢復未處理訊息 ──
    recovered = await _recover_pending_messages(adapter)
    if recovered:
        logger.info(f"Recovered {recovered} pending messages")

    # ── 指數退避 + 斷路器狀態（僅用於 receive 層級錯誤）──
    consecutive_errors = 0
    CIRCUIT_BREAKER_THRESHOLD = 10
    CIRCUIT_BREAKER_COOLDOWN = 300
    MAX_BACKOFF = 120

    while True:
        try:
            # L1: 接收訊息，立刻 spawn handler，不等結果
            message = await adapter.receive()

            # v11.0: 持久化到 SQLite（crash recovery）
            try:
                from museon.gateway.message_queue_store import get_message_queue_store
                store = get_message_queue_store()
                store.enqueue(message.trace_id, message.to_dict())
            except Exception as _pq_err:
                logger.debug(f"[{message.trace_id}] Queue persist failed (non-fatal): {_pq_err}")

            logger.info(f"[{message.trace_id}] Dispatching message from {message.session_id}")
            asyncio.create_task(_handle_telegram_message(adapter, message))
            consecutive_errors = 0

        except asyncio.CancelledError:
            logger.info("Telegram message pump cancelled")
            break
        except Exception as e:
            consecutive_errors += 1

            if consecutive_errors >= CIRCUIT_BREAKER_THRESHOLD:
                logger.error(
                    f"Telegram message pump 斷路器開啟：連續 {consecutive_errors} 次錯誤，"
                    f"冷卻 {CIRCUIT_BREAKER_COOLDOWN}s。最後錯誤: {e}",
                    exc_info=True,
                )
                await asyncio.sleep(CIRCUIT_BREAKER_COOLDOWN)
                consecutive_errors = 0
            else:
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
# 🔧 SkillHub — 工作流 + 技能 + 任務 API
# ═══════════════════════════════════════════════════════


