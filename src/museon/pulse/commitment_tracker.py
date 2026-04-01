"""CommitmentTracker — 承諾追蹤系統.

讓 MUSEON 言出必行。掃描回覆中的承諾，追蹤到期狀態，
並在逾期時透過 ProactiveBridge 主動提醒使用者。

核心流程：
  1. scan_and_register() — 回覆後掃描承諾模式並登記
  2. check_fulfillment() — 每次互動檢查是否兌現了之前的承諾
  3. get_overdue_commitments() — 取得逾期承諾（供 ProactiveBridge 注入）
  4. build_commitment_context() — 產生注入 system_prompt 的承諾提醒

設計原則：
  - 純 CPU regex 偵測，零 LLM 調用
  - 中文時間表達式解析（明天、稍後、下週...）
  - 承諾兌現 → ANIMA zhen +2
  - 承諾逾期 → ANIMA zhen -1
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))


# ═══════════════════════════════════════════
# 承諾模式偵測（純 CPU regex）
# 策略：只捕捉含時間錨點的承諾，避免即時行為被誤登記
# ═══════════════════════════════════════════

# 時間錨點關鍵字（供 parse_due_time 及 _detect_commitment 共用）
_TEMPORAL_KEYWORDS = [
    "明天早上", "明天晚上", "明早", "明天", "後天",
    "今晚", "稍後", "等一下", "待會",
    "一小時後", "兩小時後", "半小時後",
    "下週", "下禮拜", "下個月",
]

# 動作關鍵字（供 pattern 及 _is_fulfilled 共用）
_ACTION_KEYWORDS = (
    "幫|替|給|為|查|找|做|準備|整理|安排|研究|分析|追蹤|更新|回覆|處理|確認|完成"
)

# 只保留含時間錨點的承諾 pattern（同一句同時含時間詞 + 動作詞才算）
_TEMPORAL_COMMITMENT_PATTERNS = [
    # 時間詞在前，動作詞在後
    re.compile(
        r"(?:明[天日早]|後天|下[週周禮拜]+|今[天晚]|稍[後晚]|等[一下會]|過[一會陣]|待會)"
        r"[^。！？\n]*"
        r"(?:" + _ACTION_KEYWORDS + r")"
    ),
    # 動作詞在前，時間詞在後
    re.compile(
        r"(?:" + _ACTION_KEYWORDS + r")"
        r"[^。！？\n]*"
        r"(?:明[天日早]|後天|下[週周禮拜]+|今[天晚]|稍[後晚]|等[一下會]|過[一會陣]|待會)"
    ),
    # N 小時/天/週後 + 動作詞
    re.compile(
        r"(?:\d+|一|兩|三)\s*(?:小時|天|日|週|周)[後内內]"
        r"[^。！？\n]*"
        r"(?:" + _ACTION_KEYWORDS + r")"
    ),
]

# 排除模式 — 這些不是承諾，只是建議或假設
_EXCLUSION_PATTERNS = [
    re.compile(r"你可以"),        # 建議使用者做
    re.compile(r"你[會來要]"),    # 描述使用者的行為
    re.compile(r"如果我"),        # 假設句
    re.compile(r"要是我"),        # 假設句
    re.compile(r"假如我"),        # 假設句
    re.compile(r"^\s*[-–—•]\s"),  # 列表項（建議/行動清單，非 MUSEON 承諾）
    re.compile(r"[嗎呢？?]\s*$"),  # 問句（詢問使用者，非承諾）
    re.compile(r"需要我.*嗎"),    # 「需要我幫你做X嗎」是詢問，不是承諾
]

# 排除：已在同一句完成的即時行為（動作詞 + 結果詞在同一句）
_INSTANT_ACTION_EXCLUSION = re.compile(
    r"(?:幫你|替你|給你)[^。！？\n]{0,100}(?:了|完成|好了|出來|如下|以下)"
)


# ═══════════════════════════════════════════
# 中文時間表達式解析器
# ═══════════════════════════════════════════

def parse_due_time(
    time_hint: str,
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    """將中文時間表達式轉換為 datetime.

    Args:
        time_hint: 時間提示字串（如 "明天早上", "稍後"）
        now: 當前時間（預設為現在）

    Returns:
        datetime 或 None（無法解析時）
    """
    if now is None:
        now = datetime.now(TZ8)

    # 確保 now 有 timezone
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ8)

    mapping = {
        "明天早上": now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1),
        "明天晚上": now.replace(hour=20, minute=0, second=0, microsecond=0) + timedelta(days=1),
        "明天": now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1),
        "後天": now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=2),
        "今晚": now.replace(hour=20, minute=0, second=0, microsecond=0),
        "稍後": now + timedelta(hours=1),
        "等一下": now + timedelta(minutes=30),
        "待會": now + timedelta(minutes=30),
        "一小時後": now + timedelta(hours=1),
        "兩小時後": now + timedelta(hours=2),
        "半小時後": now + timedelta(minutes=30),
        "下週": now + timedelta(weeks=1),
        "下個月": now + timedelta(days=30),
    }

    result = mapping.get(time_hint)

    # 如果「今晚」但已經過了 20:00，設為明天晚上
    if time_hint == "今晚" and result and result <= now:
        result += timedelta(days=1)

    return result


# ═══════════════════════════════════════════
# CommitmentTracker
# ═══════════════════════════════════════════

class CommitmentTracker:
    """承諾追蹤器 — 讓 MUSEON 言出必行.

    掃描、登記、追蹤、兌現承諾的完整生命週期。
    """

    def __init__(self, pulse_db: Any = None):
        """初始化.

        Args:
            pulse_db: PulseDB 實例（用於持久化承諾）
        """
        self._db = pulse_db
        self._seq = 0  # 序號計數器

    def _gen_id(self) -> str:
        """產生唯一承諾 ID."""
        self._seq += 1
        ts = datetime.now(TZ8).strftime("%Y%m%d_%H%M%S")
        return f"commitment_{ts}_{self._seq}"

    # ── 掃描回覆中的承諾 ──

    def scan_and_register(
        self,
        response: str,
        user_message: str = "",
        session_id: str = "",
    ) -> List[Dict[str, Any]]:
        """掃描回覆文本中的承諾，並登記到 PulseDB.

        Args:
            response: MUSEON 的回覆文本
            user_message: 使用者的原始訊息
            session_id: 會話 ID

        Returns:
            偵測到並登記的承諾列表
        """
        if not self._db or not response:
            return []

        commitments_found = []

        # 將回覆切成句子（按句號、問號、感嘆號、換行分割）
        sentences = re.split(r"[。！？\n]+", response)

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 5:
                continue

            # 檢查排除模式
            if any(p.search(sentence) for p in _EXCLUSION_PATTERNS):
                continue

            # 偵測承諾模式
            commitment = self._detect_commitment(sentence)
            if commitment:
                commitment_id = self._gen_id()
                promise_text = commitment["promise_text"]
                promise_type = commitment["type"]
                due_at = commitment.get("due_at")

                try:
                    self._db.add_commitment(
                        commitment_id=commitment_id,
                        session_id=session_id,
                        promise_text=promise_text,
                        promise_type=promise_type,
                        due_at=due_at.isoformat() if due_at else None,
                        user_message=user_message,
                        our_response_snippet=sentence[:500],
                    )
                    commitments_found.append({
                        "id": commitment_id,
                        "promise_text": promise_text,
                        "type": promise_type,
                        "due_at": due_at.isoformat() if due_at else None,
                    })
                except Exception as e:
                    logger.warning(f"[Commitment] 登記失敗: {e}")

        if commitments_found:
            logger.info(
                f"[Commitment] 掃描到 {len(commitments_found)} 筆承諾: "
                f"{[c['promise_text'][:30] for c in commitments_found]}"
            )

        return commitments_found

    def _detect_commitment(
        self, sentence: str,
    ) -> Optional[Dict[str, Any]]:
        """偵測單句中的承諾（只接受含時間錨點的承諾）.

        策略：
        1. 先排除即時行為（動作詞 + 結果詞同句 = 已完成，不是承諾）
        2. 只有符合 _TEMPORAL_COMMITMENT_PATTERNS 的句子才算承諾
        3. 解析時間錨點推算 due_at

        Returns:
            {'promise_text': ..., 'type': ..., 'due_at': ...} 或 None
        """
        now = datetime.now(TZ8)

        # 排除：即時完成行為（同一句話已兌現）
        if _INSTANT_ACTION_EXCLUSION.search(sentence):
            return None

        # 必須符合含時間錨點的承諾 pattern
        matched = False
        for pattern in _TEMPORAL_COMMITMENT_PATTERNS:
            if pattern.search(sentence):
                matched = True
                break

        if not matched:
            return None

        # 解析時間 hint → due_at
        due_at = None
        for hint in _TEMPORAL_KEYWORDS:
            if hint in sentence:
                due_at = parse_due_time(hint, now)
                if due_at:
                    break

        # 如果完全解析不出時間，預設 24 小時後到期
        if due_at is None:
            due_at = now + timedelta(hours=24)

        return {
            "promise_text": sentence[:200],
            "type": "temporal",
            "due_at": due_at,
        }

    # ── 兌現檢查 ──

    def check_fulfillment(
        self,
        response: str,
        user_message: str = "",
    ) -> List[str]:
        """檢查本次回覆/互動是否兌現了之前的承諾.

        純 CPU 判定：
        - 承諾文本的關鍵詞出現在本次回覆中
        - 使用者主動確認完成

        Returns:
            兌現的承諾 ID 列表
        """
        if not self._db:
            return []

        fulfilled_ids = []

        try:
            pending = self._db.get_pending_commitments()
            overdue = self._db.get_overdue_commitments()
            all_active = pending + overdue
        except Exception:
            return []

        response_lower = response.lower() if response else ""
        user_lower = user_message.lower() if user_message else ""

        for commitment in all_active:
            promise = commitment.get("promise_text", "")
            cid = commitment.get("id", "")

            if self._is_fulfilled(promise, response_lower, user_lower):
                try:
                    self._db.fulfill_commitment(cid)
                    fulfilled_ids.append(cid)
                except Exception as e:
                    logger.warning(f"[Commitment] 兌現更新失敗: {e}")

        if fulfilled_ids:
            logger.info(f"[Commitment] 本次兌現: {fulfilled_ids}")

        return fulfilled_ids

    def _is_fulfilled(
        self,
        promise_text: str,
        response_lower: str,
        user_lower: str,
    ) -> bool:
        """判斷承諾是否被兌現.

        策略：提取承諾中的動詞+賓語，看回覆中是否包含。
        """
        if not promise_text:
            return False

        # 提取承諾中的關鍵動作詞
        action_words = re.findall(
            r"(?:查|找|做|準備|整理|安排|研究|分析|追蹤|更新|回覆|處理|提醒|通知)",
            promise_text,
        )

        if not action_words:
            return False

        # 回覆中出現了承諾的動作 + 回覆長度足夠（表示確實在做事而非空談）
        matched_actions = sum(
            1 for w in action_words if w in response_lower
        )

        # 至少一半的動作詞出現在回覆中
        if matched_actions >= max(1, len(action_words) // 2):
            return True

        # 使用者確認完成
        user_confirm_patterns = ["完成", "好了", "收到", "謝謝", "感謝", "不用了"]
        if any(p in user_lower for p in user_confirm_patterns):
            # 使用者確認 + 回覆中有相關內容
            if matched_actions >= 1:
                return True

        return False

    # ── 查詢 ──

    def get_overdue_commitments(self) -> List[Dict]:
        """取得逾期承諾."""
        if not self._db:
            return []
        try:
            return self._db.get_overdue_commitments()
        except Exception:
            return []

    def get_due_soon(self, hours: int = 2) -> List[Dict]:
        """取得即將到期的承諾."""
        if not self._db:
            return []
        try:
            return self._db.get_due_soon_commitments(hours=hours)
        except Exception:
            return []

    def get_pending(self) -> List[Dict]:
        """取得所有待兌現承諾."""
        if not self._db:
            return []
        try:
            return self._db.get_pending_commitments()
        except Exception:
            return []

    # ── 承諾上下文建構（注入 system prompt）──

    def build_commitment_context(self) -> str:
        """產生承諾提醒上下文，供注入 system_prompt.

        Returns:
            承諾提醒文字（空字串 = 無承諾需處理）
        """
        if not self._db:
            return ""

        parts = []

        try:
            overdue = self._db.get_overdue_commitments()
            if overdue:
                parts.append("⚠️ 你有逾期未兌現的承諾（必須優先處理）：")
                for c in overdue[:5]:
                    parts.append(
                        f"  - {c['promise_text'][:80]}"
                        f"（原定 {c.get('due_at', '未指定時間')}）"
                    )
                parts.append(
                    "請在回覆中自然提及這些承諾，並說明進展或道歉。"
                )
                parts.append("")
        except Exception as e:
            logger.debug(f"[COMMITMENT_TRACKER] operation failed (degraded): {e}")

        try:
            due_soon = self._db.get_due_soon_commitments(hours=2)
            if due_soon:
                parts.append("⏰ 即將到期的承諾：")
                for c in due_soon[:3]:
                    parts.append(
                        f"  - {c['promise_text'][:80]}"
                        f"（到期 {c.get('due_at', '?')}）"
                    )
                parts.append("")
        except Exception as e:
            logger.debug(f"[COMMITMENT_TRACKER] operation failed (degraded): {e}")

        if not parts:
            return ""

        return "\n## 承諾追蹤\n\n" + "\n".join(parts)

    # ── 定期檢查（由 CronEngine 呼叫）──

    def periodic_check(self) -> Dict[str, Any]:
        """定期承諾檢查（每 15 分鐘由 CronEngine 觸發）.

        1. 標記逾期承諾
        2. 遞增逾期承諾的跟進次數
        3. 回傳需要處理的承諾摘要

        Returns:
            {'overdue_count': N, 'due_soon_count': N, 'overdue_ids': [...]}
        """
        if not self._db:
            return {"overdue_count": 0, "due_soon_count": 0, "overdue_ids": []}

        try:
            overdue_ids = self._db.mark_overdue_commitments()
            for cid in overdue_ids:
                self._db.increment_follow_up(cid)

            due_soon = self._db.get_due_soon_commitments(hours=2)

            return {
                "overdue_count": len(overdue_ids),
                "due_soon_count": len(due_soon),
                "overdue_ids": overdue_ids,
            }
        except Exception as e:
            logger.warning(f"[Commitment] 定期檢查失敗: {e}")
            return {"overdue_count": 0, "due_soon_count": 0, "overdue_ids": []}
