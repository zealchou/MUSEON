"""L4 CPU Observer — 零 token 對話後觀察者.

取代原本 fire-and-forget 的 Haiku agent spawn。
四個職責全部用 CPU 規則引擎完成：
  1. 記憶寫入（直接寫 memory_manager）
  2. 訊號更新（quick_signal_scan）
  3. 使用者摘要檢查（keyword diff）
  4. Session 品質調整（規則引擎）

設計原則：
  - 零 LLM 呼叫，純 CPU + I/O
  - 同步函數（不需要 async），由 brain.py 在回覆後呼叫
  - 失敗靜默降級，不影響回覆流程
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class L4CpuObserver:
    """CPU-only post-reply observer.

    Usage:
        observer = L4CpuObserver(data_dir=Path("~/MUSEON/data"))
        observer.observe(
            session_id="telegram_123",
            chat_id="123",
            user_id="boss",
            user_message="幫我分析台積電",
            museon_reply="好的，讓我來分析...",
        )
    """

    # 問候/閒聊模式 — 不值得寫入記憶
    _GREETING_PATTERNS = frozenset([
        "早安", "午安", "晚安", "你好", "嗨", "哈囉",
        "好", "好的", "收到", "了解", "謝謝", "OK", "ok",
        "嗯", "嗯嗯", "對", "讚", "哈哈", "笑死", "88",
    ])

    # 新偏好指標關鍵字
    _PREFERENCE_KEYWORDS = {
        "communication_style": ["簡短", "詳細", "白話", "專業", "不要太長", "展開說"],
        "domain_interest": ["投資", "品牌", "行銷", "技術", "管理", "設計", "AI"],
        "decision_style": ["快速", "謹慎", "數據", "直覺", "風險", "保守"],
    }

    def __init__(
        self,
        data_dir: Path,
        memory_manager=None,
    ):
        self._data_dir = Path(data_dir)
        self._memory_manager = memory_manager
        self._cache_dir = self._data_dir / "_system" / "context_cache"
        self._adjustment_dir = self._data_dir / "_system" / "session_adjustments"

    def observe(
        self,
        session_id: str,
        chat_id: str,
        user_id: str,
        user_message: str,
        museon_reply: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """執行四步觀察（同步，零 LLM）.

        Returns:
            觀察結果摘要 dict
        """
        result = {
            "memory_written": False,
            "signal_updated": False,
            "preference_detected": False,
            "adjustment_written": False,
            "cache_written": False,
        }

        try:
            result["memory_written"] = self._step1_memory_write(
                session_id, chat_id, user_id, user_message, museon_reply,
            )
        except Exception as e:
            logger.debug(f"[L4-CPU] Step 1 memory write failed: {e}")

        try:
            result["signal_updated"] = self._step2_signal_update(
                session_id, user_message,
            )
        except Exception as e:
            logger.debug(f"[L4-CPU] Step 2 signal update failed: {e}")

        try:
            result["preference_detected"] = self._step3_user_summary_check(
                user_message, museon_reply,
            )
        except Exception as e:
            logger.debug(f"[L4-CPU] Step 3 user summary check failed: {e}")

        try:
            result["adjustment_written"] = self._step4_session_adjustment(
                session_id, user_message, museon_reply,
            )
        except Exception as e:
            logger.debug(f"[L4-CPU] Step 4 session adjustment failed: {e}")

        try:
            result["cache_written"] = self._step5_semantic_cache_write(
                session_id, chat_id, user_message, museon_reply,
            )
        except Exception as e:
            logger.debug(f"[L4-CPU] Step 5 semantic cache write failed: {e}")

        return result

    # ─── Step 1: 記憶寫入 ───

    def _step1_memory_write(
        self, session_id: str, chat_id: str, user_id: str,
        user_message: str, museon_reply: str,
    ) -> bool:
        """規則：訊息 > 20 字 + 非問候 → 寫入記憶."""
        if len(user_message.strip()) < 20:
            return False
        if user_message.strip() in self._GREETING_PATTERNS:
            return False

        if not self._memory_manager:
            return False

        level = "boss/L1_short" if user_id == "boss" else f"{user_id}/L1_short"
        try:
            self._memory_manager.write(
                level=level,
                key=f"l4_{int(time.time())}",
                content=json.dumps({
                    "user_message": user_message[:500],
                    "museon_reply": museon_reply[:500],
                    "session_id": session_id,
                    "chat_id": chat_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False),
            )
            return True
        except Exception as e:
            logger.debug(f"[L4-CPU] Memory write error: {e}")
            return False

    # ─── Step 2: 訊號更新 ───

    def _step2_signal_update(self, session_id: str, user_message: str) -> bool:
        """用 quick_signal_scan 更新 session 的 signal cache."""
        from museon.pulse.signal_keywords import quick_signal_scan

        signals = quick_signal_scan(user_message)
        if not signals:
            return False

        cache_path = self._cache_dir / f"{session_id}_signals.json"
        try:
            # 讀取現有 cache（如果有）並合併（EMA 平滑）
            existing = {}
            if cache_path.exists():
                try:
                    existing = json.loads(cache_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass

            alpha = 0.3  # EMA 權重
            merged = dict(existing)
            for sig, strength in signals.items():
                old = merged.get(sig, 0.0)
                merged[sig] = old * (1 - alpha) + strength * alpha
            merged["_updated_at"] = datetime.now(timezone.utc).isoformat()

            cache_path.write_text(
                json.dumps(merged, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except Exception as e:
            logger.debug(f"[L4-CPU] Signal update error: {e}")
            return False

    # ─── Step 3: 使用者摘要檢查 ───

    def _step3_user_summary_check(
        self, user_message: str, museon_reply: str,
    ) -> bool:
        """偵測使用者訊息中的新偏好/能力指標."""
        detected = {}
        combined = user_message + " " + museon_reply
        for category, keywords in self._PREFERENCE_KEYWORDS.items():
            hits = [kw for kw in keywords if kw in combined]
            if hits:
                detected[category] = hits

        if not detected:
            return False

        # 寫入 pending 偵測（供 Nightly 或手動處理）
        pending_path = self._cache_dir / "pending_preference_updates.jsonl"
        try:
            entry = json.dumps({
                "detected": detected,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_snippet": user_message[:200],
            }, ensure_ascii=False)
            with open(pending_path, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
            return True
        except Exception as e:
            logger.debug(f"[L4-CPU] Preference detection write error: {e}")
            return False

    # ─── Step 4: Session 品質調整 ───

    def _step4_session_adjustment(
        self, session_id: str, user_message: str, museon_reply: str,
    ) -> bool:
        """規則引擎偵測品質問題，寫入 session adjustment."""
        adjustments = []

        # Rule 1: 回覆太長 vs 問題太短
        if len(museon_reply) > 1500 and len(user_message) < 100:
            adjustments.append({
                "trigger": "response_too_long",
                "adjustment": "compress_output",
                "params": {"max_length": 800},
                "expires_after_turns": 3,
            })

        # Rule 2: 回覆中有太多不確定語氣
        uncertain_count = sum(
            1 for phrase in ["我不確定", "可能", "也許", "不太確定", "或許"]
            if phrase in museon_reply
        )
        if uncertain_count >= 3:
            adjustments.append({
                "trigger": "low_confidence",
                "adjustment": "increase_depth",
                "params": {"min_evidence": 2},
                "expires_after_turns": 2,
            })

        if not adjustments:
            return False

        self._adjustment_dir.mkdir(parents=True, exist_ok=True)
        adj_path = self._adjustment_dir / f"{session_id}.json"
        try:
            adj_data = {
                "session_id": session_id,
                "adjustments": adjustments,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            adj_path.write_text(
                json.dumps(adj_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except Exception as e:
            logger.debug(f"[L4-CPU] Session adjustment write error: {e}")
            return False

    # ─── Step 5: 語意快取寫入 ───

    def _step5_semantic_cache_write(
        self, session_id: str, chat_id: str,
        user_message: str, museon_reply: str,
    ) -> bool:
        """寫入 semantic response cache（供下次相似查詢命中）."""
        from museon.pulse.signal_keywords import quick_signal_scan

        signals = quick_signal_scan(user_message)

        try:
            from museon.cache.semantic_response_cache import SemanticResponseCache
            cache = SemanticResponseCache()
            return cache.write(
                chat_id=chat_id,
                query=user_message,
                response=museon_reply,
                signals=signals,
            )
        except Exception as e:
            logger.debug(f"[L4-CPU] Semantic cache write error: {e}")
            return False
