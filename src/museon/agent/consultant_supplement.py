"""Consultant Supplement Framework（CSF）— 主回覆後的深度顧問補充.

Brain.process() 完成主回覆後，發布 CONSULTANT_GATE 事件。
CSF 訂閱此事件，執行五道 CPU Gate 快篩，通過後呼叫 Sonnet
生成深度補充，作為獨立 Telegram 訊息發送。

設計原則：
- 所有 Gate 邏輯為 CPU（零 token）
- Sonnet 呼叫用 brain._call_llm_with_model（走現有 budget tracking）
- Telegram 發送用 _safe_send（走現有 ResponseGuard）
- 任何步驟失敗不影響主回覆（fire-and-forget）
"""

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 偵測關鍵詞 ──
_EVASION_KEYWORDS = frozenset({
    "都要", "算了", "直接給我", "不用了", "不知道",
    "隨便", "都可以", "都好", "沒差", "你決定",
})
_COMPARISON_PATTERNS = ["差在哪", "哪個好", "怎麼選", "該用哪", "比較好"]
_NO_DATA_PATTERNS = ["有什麼方法", "怎麼提升", "怎麼增加", "如何改善", "怎麼做"]

# ── 排除條件 ──
_EMOTION_WORDS = ["撐不下去", "崩潰", "好難過", "想哭", "受不了"]
_TECH_PATTERNS = ["怎麼寫", "公式", "翻譯", "幫我算", "幫我查"]

# ── Sonnet 模型 ──
_SONNET_MODEL = "claude-sonnet-4-5-20251001"

CHALLENGE_SYSTEM_PROMPT = """你是一個資深顧問。你剛看完一段 AI 助理與使用者的對話。
AI 助理已經給了完整的回覆。你的工作是從不同角度補充——
指出使用者可能沒注意到的假設、迴避、盲點、風險或被低估的資源。

使用者的發展弱點（來自星座雷達）：
{constellation_context}

你的風格：
- 像資深前輩私下跟你講真話，不是老師教訓
- 深度匹配情境的重要性——小事一兩句，大決策可以展開論述
- 有根據地挑戰，不是為了挑戰而挑戰
- 用繁體中文
- 不要重複 AI 助理已經說過的內容
- 不要自稱「顧問」或「我作為顧問」"""


class ConsultantSupplement:
    """Consultant Supplement Framework — 主回覆後的深度顧問補充模組."""

    def __init__(
        self,
        brain: Any,
        telegram_adapter_getter: Optional[Callable[[], Any]] = None,
    ):
        """初始化 CSF.

        Args:
            brain: MuseonBrain 實例，用來呼叫 _call_llm_with_model
            telegram_adapter_getter: 取得 TelegramAdapter 的 callable（lazy getter）
        """
        self._brain = brain
        self._telegram_adapter_getter = telegram_adapter_getter

        # Session 狀態追蹤（記憶體內，重啟重置 OK）
        self._session_challenge_count: Dict[str, int] = {}
        self._session_last_challenge_turn: Dict[str, int] = {}
        self._session_opt_out: Dict[str, bool] = {}

        logger.info("[CSF] ConsultantSupplement 初始化完成（BackgroundTasks 模式）")

    def _on_consultant_gate(self, event_data: Optional[Dict[str, Any]]) -> None:
        """EventBus 回呼 — 執行 Gate 邏輯，通過則觸發 Sonnet 補充.

        此方法在 EventBus 的同步回呼中執行，用 asyncio 橋接啟動異步任務。
        """
        if not event_data:
            return

        try:
            if not self._check_gates(event_data):
                return

            # Gate 全通過 → 在 event loop 中建立異步任務
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._async_generate_and_send(event_data))
                else:
                    logger.debug("[CSF] Event loop 未運行，跳過補充")
            except RuntimeError:
                logger.debug("[CSF] 無法取得 event loop，跳過補充")

        except Exception as e:
            logger.debug(f"[CSF] _on_consultant_gate 發生例外（降級）: {e}")

    def _check_gates(self, event_data: Dict[str, Any]) -> bool:
        """五道 Gate 的 CPU 快篩.

        Returns:
            True = 全部通過，應觸發 Sonnet 補充
            False = 任一 Gate 拒絕
        """
        _session_key = event_data.get("session_id", "")
        user_message = event_data.get("user_message", "")

        # Gate 1: 只在 DEEP/EXPLORATION 管線（排除 FAST_LOOP）
        _pipeline = event_data.get("pipeline", "")
        if _pipeline == "FAST":
            logger.info("[CSF] Gate 1 拒絕：FAST 管線，跳過補充")
            return False

        # Gate 2: session 挑戰計數 < 2（同一 session 最多發 2 次）
        _challenge_count = self._session_challenge_count.get(_session_key, 0)
        if _challenge_count >= 2:
            logger.info(f"[CSF] Gate 2 拒絕：session {_session_key} 挑戰計數已達 {_challenge_count}")
            return False

        # Gate 3: 冷卻期（距上次挑戰 ≥ 3 輪）
        _last_challenge_turn = self._session_last_challenge_turn.get(_session_key, -10)
        _current_turn = event_data.get("turn_count", 0)
        if _current_turn - _last_challenge_turn < 3:
            logger.info(
                f"[CSF] Gate 3 拒絕：冷卻中（上次 turn={_last_challenge_turn}，"
                f"目前 turn={_current_turn}，差={_current_turn - _last_challenge_turn}）"
            )
            return False

        # Gate 4: CPU 快篩偵測到迴避/模糊訊號
        _triggered, _trigger_type = self._detect_evasion_signal(user_message)
        if not _triggered:
            logger.info("[CSF] Gate 4 拒絕：未偵測到迴避/模糊訊號")
            return False

        # Gate 5: 排除條件（高情緒、明確技術指令、使用者已關閉）
        if self._should_exclude(event_data):
            logger.info("[CSF] Gate 5 拒絕：觸發排除條件")
            return False

        logger.info(
            f"[CSF] 五道 Gate 全通過：session={_session_key}, "
            f"pipeline={_pipeline}, trigger={_trigger_type}, "
            f"turn={_current_turn}"
        )
        return True

    def _detect_evasion_signal(self, user_message: str) -> Tuple[bool, str]:
        """偵測迴避/模糊訊號.

        Returns:
            (是否觸發, 觸發類型)
        """
        # 關鍵詞匹配
        for kw in _EVASION_KEYWORDS:
            if kw in user_message:
                logger.info(f"[CSF] 迴避關鍵詞命中：{kw}")
                return True, f"evasion_keyword:{kw}"

        # 比較型問題
        for pattern in _COMPARISON_PATTERNS:
            if pattern in user_message:
                logger.info(f"[CSF] 比較型問題命中：{pattern}")
                return True, f"comparison:{pattern}"

        # 無數據要方案型
        for pattern in _NO_DATA_PATTERNS:
            if pattern in user_message:
                logger.info(f"[CSF] 無數據要方案型命中：{pattern}")
                return True, f"no_data_solution:{pattern}"

        # quick_signal_scan 輔助判斷
        try:
            from museon.pulse.signal_keywords import quick_signal_scan
            signal_result = quick_signal_scan(user_message)
            # 若返回含有 evasion / vague / avoidance 等信號，視為觸發
            if isinstance(signal_result, dict):
                _signal_type = signal_result.get("primary", "")
                if _signal_type in ("evasion", "vague", "avoidance", "comparison"):
                    logger.info(f"[CSF] quick_signal_scan 輔助觸發：{_signal_type}")
                    return True, f"signal_scan:{_signal_type}"
        except Exception as e:
            logger.debug(f"[CSF] quick_signal_scan 失敗（降級）: {e}")

        return False, ""

    def _should_exclude(self, event_data: Dict[str, Any]) -> bool:
        """判斷是否應排除（不發補充）.

        Returns:
            True = 應排除
        """
        msg = event_data.get("user_message", "")
        session_id = event_data.get("session_id", "")

        # 高情緒排除
        if any(w in msg for w in _EMOTION_WORDS):
            logger.info(f"[CSF] 排除：偵測到高情緒詞彙")
            return True

        # 明確技術指令排除（短訊息 + 技術關鍵詞）
        if any(p in msg for p in _TECH_PATTERNS) and len(msg) < 30:
            logger.info(f"[CSF] 排除：明確技術指令且訊息短於 30 字")
            return True

        # 使用者已關閉 CSF
        if self._session_opt_out.get(session_id):
            logger.info(f"[CSF] 排除：session {session_id} 使用者已關閉補充")
            return True

        return False

    def _build_challenge_context(self, event_data: Dict[str, Any]) -> str:
        """組裝星座弱維度 context，供 Sonnet prompt 使用."""
        constellation_signals = event_data.get("constellation_signals") or {}

        if not constellation_signals:
            return "（無星座雷達資料）"

        lines = []
        for cname, cdata in constellation_signals.items():
            weakest = cdata.get("weakest_dim", "未知")
            value = cdata.get("value", 0.0)
            lines.append(f"- {cname} 星座：最弱維度「{weakest}」（得分 {value:.2f}）")

        return "\n".join(lines) if lines else "（星座雷達無明顯弱維度）"

    async def _generate_supplement(self, event_data: Dict[str, Any]) -> str:
        """呼叫 Sonnet 生成深度顧問補充.

        Returns:
            補充文字（失敗時返回空字串）
        """
        user_message = event_data.get("user_message", "")
        main_response = event_data.get("main_response", "")
        constellation_context = self._build_challenge_context(event_data)

        system_prompt = CHALLENGE_SYSTEM_PROMPT.format(
            constellation_context=constellation_context
        )

        messages = [
            {
                "role": "user",
                "content": (
                    f"使用者說：{user_message}\n\n"
                    f"AI 助理回覆：{main_response}\n\n"
                    f"請從資深顧問的角度，補充使用者可能沒注意到的盲點、假設或風險。"
                )
            }
        ]

        try:
            result = await self._brain._call_llm_with_model(
                system_prompt=system_prompt,
                messages=messages,
                model=_SONNET_MODEL,
                max_tokens=1024,
            )
            logger.info(f"[CSF] Sonnet 生成完成，長度 {len(result)} 字")
            return result
        except Exception as e:
            logger.warning(f"[CSF] Sonnet 呼叫失敗: {e}")
            return ""

    def _get_adapter(self) -> Optional[Any]:
        """取得 TelegramAdapter 實例（優先 getter，其次靜態引用）."""
        if self._telegram_adapter_getter is not None:
            return self._telegram_adapter_getter()
        return self._telegram_adapter

    async def _send_supplement(
        self,
        chat_id: int,
        text: str,
        reply_to_message_id: Optional[int] = None,
    ) -> None:
        """透過 Telegram 發送補充訊息（走 _safe_send）."""
        adapter = self._get_adapter()
        if not adapter:
            logger.warning("[CSF] Telegram adapter 不可用，無法發送補充")
            return

        formatted = f"💡 {text}"

        kwargs: Dict[str, Any] = {}
        if reply_to_message_id:
            kwargs["reply_to_message_id"] = reply_to_message_id

        try:
            await adapter._safe_send(
                chat_id=int(chat_id),
                text=formatted,
                **kwargs,
            )
            logger.info(f"[CSF] 補充訊息已發送到 chat_id={chat_id}")
        except Exception as e:
            logger.warning(f"[CSF] 補充訊息發送失敗: {e}")

    async def _async_generate_and_send(self, event_data: Dict[str, Any]) -> None:
        """異步生成並發送補充訊息（完整流程）."""
        session_id = event_data.get("session_id", "")
        chat_id_raw = event_data.get("chat_id", session_id)
        reply_to_message_id = event_data.get("reply_to_message_id")
        current_turn = event_data.get("turn_count", 0)

        try:
            # 解析 chat_id（session_id 格式通常是 telegram_{chat_id}）
            chat_id: Optional[int] = None
            if isinstance(chat_id_raw, int):
                chat_id = chat_id_raw
            elif isinstance(chat_id_raw, str):
                if chat_id_raw.startswith("telegram_group_"):
                    try:
                        chat_id = -int(chat_id_raw.replace("telegram_group_", ""))
                    except ValueError:
                        pass
                elif chat_id_raw.startswith("telegram_"):
                    try:
                        chat_id = int(chat_id_raw.replace("telegram_", ""))
                    except ValueError:
                        pass
                else:
                    try:
                        chat_id = int(chat_id_raw)
                    except ValueError:
                        pass

            if not chat_id:
                logger.warning(f"[CSF] 無法解析 chat_id：{chat_id_raw}，跳過發送")
                return

            # 生成補充
            supplement_text = await self._generate_supplement(event_data)
            if not supplement_text or not supplement_text.strip():
                logger.info("[CSF] 補充內容為空，跳過發送")
                return

            # 發送
            await self._send_supplement(
                chat_id=chat_id,
                text=supplement_text,
                reply_to_message_id=reply_to_message_id,
            )

            # 更新 session 狀態
            self._session_challenge_count[session_id] = (
                self._session_challenge_count.get(session_id, 0) + 1
            )
            self._session_last_challenge_turn[session_id] = current_turn
            logger.info(
                f"[CSF] Session {session_id} 挑戰計數更新為 "
                f"{self._session_challenge_count[session_id]}"
            )

        except Exception as e:
            logger.warning(f"[CSF] _async_generate_and_send 發生例外（降級）: {e}")

    async def run_async_supplement(self, event_data: Dict[str, Any]) -> None:
        """BackgroundTasks 入口 — Gate 檢查 + 生成 + 發送.

        由 FastAPI BackgroundTasks 在 HTTP response 送出後呼叫。
        不阻塞主回覆。
        """
        if not event_data:
            return

        try:
            if not self._check_gates(event_data):
                return

            await self._async_generate_and_send(event_data)
        except Exception as e:
            logger.warning(f"[CSF] run_async_supplement 例外（降級）: {e}")

    def set_opt_out(self, session_id: str, opt_out: bool = True) -> None:
        """設定使用者對某 session 的補充偏好.

        Args:
            session_id: 會話 ID
            opt_out: True = 關閉補充，False = 重新開啟
        """
        self._session_opt_out[session_id] = opt_out
        logger.info(f"[CSF] Session {session_id} opt_out={opt_out}")
