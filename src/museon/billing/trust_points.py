"""Skill Invocation Counter — Skill 調用次數計量器.

每次 Skill 被調用時記錄一次，持久化到月度 JSON 檔案。
信任點的換算比例由外部定義，本模組只負責「數次數」。

常駐 Skill（dna27, deep-think, c15 等）不計入調用次數。
"""

import json
import logging
import os
import tempfile
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# 常駐 Skill — 不計入調用次數（免費層）
ALWAYS_ON_SKILLS: Set[str] = {
    "dna27",
    "deep-think",
    "c15",
    "query-clarity",
    "user-model",
    "plugin-registry",
    # 系統維運類
    "fix-verify",
    "qa-auditor",
    "sandbox-lab",
    "eval-engine",
    "system-health-check",
    "morphenix",
    "wee",
    "knowledge-lattice",
}


class SkillInvocationCounter:
    """Skill 調用次數計數器 — 按月、按日、按 Skill 追蹤."""

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self._billing_dir: Optional[Path] = None
        if data_dir:
            self._billing_dir = Path(data_dir) / "_system" / "billing"
            try:
                self._billing_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.warning(f"Cannot create billing dir: {e}")
                self._billing_dir = None

        self._lock = threading.Lock()

    # ── 核心：記錄一次調用 ────────────────────────────

    def record(
        self,
        skill_names: List[str],
        session_id: str = "",
        user_id: str = "",
        outcome: str = "",
    ) -> int:
        """記錄一次 Skill 調用，回傳本次計入的 Skill 數量.

        常駐 Skill 不計入。

        Returns:
            本次計入的 billable Skill 調用數
        """
        if not skill_names:
            return 0

        # 過濾常駐 Skill
        billable = [s for s in skill_names if s not in ALWAYS_ON_SKILLS]
        if not billable:
            return 0

        entry = {
            "ts": datetime.now().isoformat(),
            "skills": billable,
            "count": len(billable),
            "session_id": session_id,
            "user_id": user_id,
            "outcome": outcome,
        }

        with self._lock:
            self._append(entry)

        return len(billable)

    # ── 查詢 ─────────────────────────────────────────

    def get_monthly_summary(self, user_id: str = "", month: Optional[date] = None) -> Dict[str, Any]:
        """取得月度 Skill 調用摘要."""
        d = month or date.today()
        data = self._load_month(d)
        entries = data.get("entries", [])
        if user_id:
            entries = [e for e in entries if e.get("user_id") == user_id]

        total_invocations = sum(e.get("count", 0) for e in entries)

        # 按 Skill 彙總
        by_skill: Dict[str, int] = {}
        for e in entries:
            for sk in e.get("skills", []):
                by_skill[sk] = by_skill.get(sk, 0) + 1

        # 按日彙總
        by_day: Dict[str, int] = {}
        for e in entries:
            day = e.get("ts", "")[:10]
            by_day[day] = by_day.get(day, 0) + e.get("count", 0)

        return {
            "month": d.strftime("%Y-%m"),
            "total_invocations": total_invocations,
            "total_entries": len(entries),
            "by_skill": dict(sorted(by_skill.items(), key=lambda x: x[1], reverse=True)),
            "by_day": by_day,
            "user_id": user_id or "all",
        }

    def get_today(self, user_id: str = "") -> Dict[str, Any]:
        """取得今日 Skill 調用摘要."""
        monthly = self.get_monthly_summary(user_id)
        today_key = date.today().isoformat()
        return {
            "date": today_key,
            "invocations_today": monthly["by_day"].get(today_key, 0),
            "invocations_month": monthly["total_invocations"],
        }

    # ── 持久化 ───────────────────────────────────────

    def _month_file(self, d: Optional[date] = None) -> Optional[Path]:
        if not self._billing_dir:
            return None
        d = d or date.today()
        return self._billing_dir / f"skill_invocations_{d.strftime('%Y-%m')}.json"

    def _load_month(self, d: Optional[date] = None) -> Dict[str, Any]:
        fp = self._month_file(d)
        if not fp or not fp.exists():
            return {"entries": []}
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load skill invocations: {e}")
            return {"entries": []}

    def _append(self, entry: Dict[str, Any]) -> None:
        fp = self._month_file()
        if not fp:
            return
        try:
            data = self._load_month()
            data["entries"].append(entry)

            # 原子寫入
            content = json.dumps(data, ensure_ascii=False, indent=2)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(fp.parent), suffix=".tmp", prefix=".si_"
            )
            fd_closed = False
            try:
                os.write(fd, content.encode("utf-8"))
                os.fsync(fd)
                os.close(fd)
                fd_closed = True
                os.replace(tmp_path, str(fp))
            except Exception:
                if not fd_closed:
                    os.close(fd)
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        except OSError as e:
            logger.warning(f"Failed to save skill invocations: {e}")


# ── 全域單例 ─────────────────────────────────────────

_instance: Optional[SkillInvocationCounter] = None
_instance_lock = threading.Lock()


def get_skill_counter(data_dir: Optional[str] = None) -> SkillInvocationCounter:
    """取得全域 SkillInvocationCounter 單例."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SkillInvocationCounter(data_dir=data_dir)
    return _instance
