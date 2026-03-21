"""Multi-tenant governance for Telegram group interactions.

Architecture:
- ExternalAnimaManager: per-user anima files for non-owner Telegram users
- SensitivityChecker: L1/L2/L3 classification of potentially sensitive topics
- EscalationQueue: DM-based approval workflow for sensitive questions

Level definitions:
  L1 — company internal info (clients, contracts, revenue)
  L2 — Zeal's personal info (family, health, schedule)
  L3 — system/IP secrets (MUSEON architecture, API keys, patents)
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Sensitivity keyword lists ──

SENSITIVE_L1 = [
    "客戶", "合約", "收入", "營收", "收費", "合作", "案子",
    "業績", "報價", "簽約", "帳號", "金流", "price", "contract",
    "revenue", "client", "customer",
]

SENSITIVE_L2 = [
    "口試", "孩子", "小孩", "家人", "老婆", "太太", "寶寶",
    "預產期", "醫院", "健康", "生病", "手術", "住址", "電話", "身分證",
]

SENSITIVE_L3 = [
    "霓裳", "架構", "API key", "token", "子機", "母機",
    "source code", "原始碼", "server", "專利", "商業秘密",
    "技術細節", "後台", "資料庫", "database", "patent",
]


class SensitivityChecker:
    """Classify user messages by sensitivity level."""

    @staticmethod
    def _clean_text(text: str) -> str:
        """Remove @bot mentions and common noise before sensitivity check."""
        import re
        # Strip @xxx_bot mentions (e.g. @MuseonClaw_bot)
        cleaned = re.sub(r"@\w+_?bot\b", "", text, flags=re.IGNORECASE)
        # Strip reply context prefix
        cleaned = re.sub(r"^\[回覆.*?的訊息：.*?\]\s*", "", cleaned, flags=re.DOTALL)
        return cleaned.strip()

    def check(self, text: str) -> Tuple[Optional[str], str]:
        """Return (level, reason). Level is None, 'L1', 'L2', or 'L3' (L3 = highest)."""
        text_lower = self._clean_text(text).lower()

        if not text_lower:
            return None, ""

        for kw in SENSITIVE_L3:
            if kw.lower() in text_lower:
                return "L3", f"系統機密關鍵詞：{kw}"

        for kw in SENSITIVE_L2:
            if kw.lower() in text_lower:
                return "L2", f"個人資訊關鍵詞：{kw}"

        for kw in SENSITIVE_L1:
            if kw.lower() in text_lower:
                return "L1", f"公司內部資訊關鍵詞：{kw}"

        return None, ""


class ExternalAnimaManager:
    """Create and manage per-user anima files for non-owner Telegram users.

    v2.0: 擴充 schema，支援八原語觀察、偏好追蹤、近期主題記錄，
    讓 owner 未來可查詢客戶/外部用戶的行為畫像。
    """

    def __init__(self, data_dir: Path):
        self.users_dir = data_dir / "_system" / "external_users"
        self.users_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: str) -> Path:
        return self.users_dir / f"{user_id}.json"

    @staticmethod
    def _default_anima(user_id: str) -> Dict[str, Any]:
        """回傳 v3 預設結構 — 獨立 ANIMA（含七層精選 + 信任演化）."""
        return {
            "version": "3.0.0",
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "interaction_count": 0,
            "last_seen": None,
            "display_name": None,
            "context_summary": "",
            # v3.0: 完整結構（與 ANIMA_USER 對齊）
            "profile": {
                "name": None,
                "role": None,
                "business_type": "unknown",
            },
            "relationship": {
                "trust_level": "initial",
                "total_interactions": 0,
                "positive_signals": 0,
                "negative_signals": 0,
                "last_interaction": None,
                "first_interaction": datetime.now().isoformat(),
            },
            "eight_primals": {},
            "seven_layers": {
                "L1_facts": [],
                "L2_personality": [],
                "L6_communication_style": {
                    "detail_level": "moderate",
                    "emoji_usage": "none",
                    "language_mix": "mixed",
                    "avg_msg_length": 0,
                    "question_style": "open",
                    "tone": "casual",
                },
            },
            "preferences": {},
            "recent_topics": [],
            "groups_seen_in": [],
            "relationship_to_owner": "",
        }

    def load(self, user_id: str) -> Dict[str, Any]:
        p = self._path(user_id)
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                # Schema migration v1 → v2
                if "version" not in data:
                    data["version"] = "2.0.0"
                    data.setdefault("eight_primals", {})
                    data.setdefault("preferences", {})
                    data.setdefault("recent_topics", [])
                    data.setdefault("groups_seen_in", [])
                    data.setdefault("relationship_to_owner", "")
                # Schema migration v2 → v3
                ver = data.get("version", "2.0.0")
                if ver.startswith("2."):
                    data["version"] = "3.0.0"
                    data.setdefault("profile", {
                        "name": data.get("display_name"),
                        "role": None,
                        "business_type": "unknown",
                    })
                    data.setdefault("relationship", {
                        "trust_level": "initial",
                        "total_interactions": data.get("interaction_count", 0),
                        "positive_signals": 0,
                        "negative_signals": 0,
                        "last_interaction": data.get("last_seen"),
                        "first_interaction": data.get("created_at"),
                    })
                    data.setdefault("seven_layers", {
                        "L1_facts": [],
                        "L2_personality": [],
                        "L6_communication_style": {
                            "detail_level": "moderate",
                            "emoji_usage": "none",
                            "language_mix": "mixed",
                            "avg_msg_length": 0,
                            "question_style": "open",
                            "tone": "casual",
                        },
                    })
                return data
            except Exception as e:
                logger.debug(f"[MULTI_TENANT] JSON failed (degraded): {e}")
        return self._default_anima(user_id)

    def search_by_keyword(self, keyword: str, limit: int = 5) -> List[Dict[str, Any]]:
        """搜尋外部用戶：比對 display_name、context_summary、recent_topics.

        用於跨 session 記憶檢索——當 owner 在私聊中提及某個群組成員時，
        能從外部用戶檔案中找到相關資訊。
        """
        keyword_lower = keyword.lower()
        results = []
        try:
            for p in self.users_dir.glob("*.json"):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    # 比對 display_name
                    name = (data.get("display_name") or "").lower()
                    summary = (data.get("context_summary") or "").lower()
                    topics = " ".join(data.get("recent_topics", [])).lower()
                    relation = (data.get("relationship_to_owner") or "").lower()
                    searchable = f"{name} {summary} {topics} {relation}"
                    if keyword_lower in searchable:
                        results.append(data)
                        if len(results) >= limit:
                            break
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"ExternalAnima search failed: {e}")
        return results

    def save(self, user_id: str, anima: Dict[str, Any]) -> None:
        """完整覆寫外部用戶的 ANIMA 檔案。"""
        try:
            self._path(user_id).write_text(
                json.dumps(anima, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"ExternalAnima save failed for {user_id}: {e}")

    def update(self, user_id: str, display_name: str = None,
               group_id: int = None) -> None:
        anima = self.load(user_id)
        anima["interaction_count"] = anima.get("interaction_count", 0) + 1
        anima["last_seen"] = datetime.now().isoformat()
        if display_name and not anima.get("display_name"):
            anima["display_name"] = display_name
        if group_id:
            groups = anima.setdefault("groups_seen_in", [])
            if group_id not in groups:
                groups.append(group_id)
        self.save(user_id, anima)


class EscalationQueue:
    """Manage pending sensitivity escalations to owner.

    Flow:
    1. Group message triggers sensitivity detection
    2. Queue entry created with 10-minute timeout
    3. Owner DMs a response ("可以" / "不行" / "yes" / "no")
    4. Bot replies to group OR politely declines
    5. If timeout → auto-decline

    Multi-group support:
    - Tracks latest escalation per group (not global singleton)
    - resolve_latest() resolves the most recent unresolved across all groups
    - FIFO ordering ensures fairness across groups
    """

    TIMEOUT_SECONDS = 600  # 10 minutes

    def __init__(self):
        self._pending: Dict[str, Dict[str, Any]] = {}
        # Per-group latest tracking (replaces single _latest_id)
        self._latest_per_group: Dict[int, str] = {}
        # Global ordered list for FIFO resolution
        self._order: list = []

    def add(
        self,
        escalation_id: str,
        question: str,
        asker_name: str,
        group_id: int,
        level: str,
    ) -> None:
        self._pending[escalation_id] = {
            "question": question,
            "asker_name": asker_name,
            "group_id": group_id,
            "level": level,
            "created_at": datetime.now(),
            "resolved": False,
            "allowed": False,
        }
        self._latest_per_group[group_id] = escalation_id
        self._order.append(escalation_id)

    def resolve(self, escalation_id: str, allowed: bool) -> bool:
        if escalation_id not in self._pending:
            return False
        self._pending[escalation_id]["resolved"] = True
        self._pending[escalation_id]["allowed"] = allowed
        return True

    def resolve_latest(self, allowed: bool) -> Optional[str]:
        """Resolve the oldest unresolved escalation (FIFO across all groups)."""
        for eid in self._order:
            if eid in self._pending:
                entry = self._pending[eid]
                if not entry["resolved"] and not self.is_timed_out(eid):
                    self.resolve(eid, allowed)
                    return eid
        return None

    def is_timed_out(self, escalation_id: str) -> bool:
        entry = self._pending.get(escalation_id)
        if not entry:
            return True
        if entry["resolved"]:
            return False
        return (datetime.now() - entry["created_at"]) > timedelta(seconds=self.TIMEOUT_SECONDS)

    def get(self, escalation_id: str) -> Optional[Dict]:
        return self._pending.get(escalation_id)

    def get_latest(self) -> Optional[Dict]:
        """Get the oldest unresolved escalation."""
        for eid in self._order:
            if eid in self._pending:
                entry = self._pending[eid]
                if not entry["resolved"] and not self.is_timed_out(eid):
                    return entry
        return None

    def pending_count(self) -> int:
        """Return number of unresolved, non-timed-out escalations."""
        return sum(
            1 for eid in self._order
            if eid in self._pending
            and not self._pending[eid]["resolved"]
            and not self.is_timed_out(eid)
        )

    def purge_old(self) -> None:
        cutoff = datetime.now() - timedelta(hours=2)
        to_delete = [
            k for k, v in self._pending.items()
            if v["created_at"] < cutoff
        ]
        for k in to_delete:
            del self._pending[k]
        self._order = [eid for eid in self._order if eid in self._pending]
        self._latest_per_group = {
            gid: eid for gid, eid in self._latest_per_group.items()
            if eid in self._pending
        }


# ── Singletons ──

_sensitivity_checker = SensitivityChecker()
_escalation_queue = EscalationQueue()


def get_sensitivity_checker() -> SensitivityChecker:
    return _sensitivity_checker


def get_escalation_queue() -> EscalationQueue:
    return _escalation_queue
