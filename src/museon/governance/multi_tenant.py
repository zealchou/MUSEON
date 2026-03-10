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
from typing import Any, Dict, Optional, Tuple

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
    "MUSEON", "霓裳", "架構", "API key", "token", "子機", "母機",
    "source code", "原始碼", "server", "專利", "商業秘密",
    "技術細節", "後台", "資料庫", "database", "patent",
]


class SensitivityChecker:
    """Classify user messages by sensitivity level."""

    def check(self, text: str) -> Tuple[Optional[str], str]:
        """Return (level, reason). Level is None, 'L1', 'L2', or 'L3' (L3 = highest)."""
        text_lower = text.lower()

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
    """Create and manage per-user anima files for non-owner Telegram users."""

    def __init__(self, data_dir: Path):
        self.users_dir = data_dir / "_system" / "external_users"
        self.users_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: str) -> Path:
        return self.users_dir / f"{user_id}.json"

    def load(self, user_id: str) -> Dict[str, Any]:
        p = self._path(user_id)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "interaction_count": 0,
            "last_seen": None,
            "display_name": None,
            "context_summary": "",
        }

    def update(self, user_id: str, display_name: str = None) -> None:
        anima = self.load(user_id)
        anima["interaction_count"] = anima.get("interaction_count", 0) + 1
        anima["last_seen"] = datetime.now().isoformat()
        if display_name and not anima.get("display_name"):
            anima["display_name"] = display_name
        try:
            self._path(user_id).write_text(
                json.dumps(anima, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"ExternalAnima write failed for {user_id}: {e}")


class EscalationQueue:
    """Manage pending sensitivity escalations to owner.

    Flow:
    1. Group message triggers sensitivity detection
    2. Queue entry created with 10-minute timeout
    3. Owner DMs a response ("可以" / "不行" / "yes" / "no")
    4. Bot replies to group OR politely declines
    5. If timeout → auto-decline
    """

    TIMEOUT_SECONDS = 600  # 10 minutes

    def __init__(self):
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._latest_id: Optional[str] = None

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
        self._latest_id = escalation_id

    def resolve(self, escalation_id: str, allowed: bool) -> bool:
        if escalation_id not in self._pending:
            return False
        self._pending[escalation_id]["resolved"] = True
        self._pending[escalation_id]["allowed"] = allowed
        return True

    def resolve_latest(self, allowed: bool) -> Optional[str]:
        """Resolve the most recent pending escalation (owner replied without specifying ID)."""
        if self._latest_id and self._latest_id in self._pending:
            entry = self._pending[self._latest_id]
            if not entry["resolved"] and not self.is_timed_out(self._latest_id):
                self.resolve(self._latest_id, allowed)
                return self._latest_id
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
        if self._latest_id:
            return self._pending.get(self._latest_id)
        return None

    def purge_old(self) -> None:
        cutoff = datetime.now() - timedelta(hours=2)
        to_delete = [
            k for k, v in self._pending.items()
            if v["created_at"] < cutoff
        ]
        for k in to_delete:
            del self._pending[k]


# ── Singletons ──

_sensitivity_checker = SensitivityChecker()
_escalation_queue = EscalationQueue()


def get_sensitivity_checker() -> SensitivityChecker:
    return _sensitivity_checker


def get_escalation_queue() -> EscalationQueue:
    return _escalation_queue
