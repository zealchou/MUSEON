"""SCALPEL Lessons — MuseDoc 的自學記憶層.

每次手術完成 + 14 天驗證通過後，將「症狀→因果鏈→修法→結果」
結晶為一條 Lesson。未來分診時先查 Lessons，命中則跳過 DSE 直接套用。

學習閉環：
  手術成功 → pending lesson（14 天觀察期）
  14 天無復發 → confirmed lesson（可自動套用）
  復發 → failed lesson（標記因果鏈錯誤，needs_human）
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class Lesson:
    """一條已學習的修復經驗."""

    lesson_id: str = ""
    created_at: str = ""

    # 症狀特徵（用於未來匹配）
    symptom_pattern: str = ""       # 正則或關鍵字
    finding_severity: str = ""      # CRITICAL/HIGH/MEDIUM/LOW
    blast_origin_file: str = ""     # 出問題的檔案
    error_type: str = ""            # NameError/KeyError/...

    # 因果鏈（DSE 產出）
    causal_chain: str = ""          # "RC-1 → RC-2 → RC-3" 描述
    root_cause: str = ""            # 根因描述

    # 修復方法
    fix_description: str = ""       # 怎麼修的
    runbook_id: str = ""            # 用了哪個 Runbook
    affected_files: list[str] = field(default_factory=list)

    # 結果追蹤
    status: str = "pending"         # pending / confirmed / failed
    surgery_date: str = ""
    verification_date: str = ""     # 14 天後驗證日期
    recurrence_count: int = 0       # 復發次數

    # 衍生防線
    immunity_written: bool = False  # 是否已寫入 Pre-Flight/MuseQA
    new_runbook_id: str = ""        # 是否催生了新 Runbook

    # 信心度
    confidence: float = 0.0         # 初始 DSE 信心度
    verified_confidence: float = 0.0  # 驗證後的信心度

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Lesson:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class LessonStore:
    """Lesson 持久化存儲."""

    def __init__(self, store_path: Path):
        self._path = store_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, lesson: Lesson) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(lesson.to_dict(), ensure_ascii=False) + "\n")
        logger.info("[SCALPEL:Learn] Lesson saved: %s (%s)", lesson.lesson_id, lesson.status)

    def load_all(self) -> list[Lesson]:
        if not self._path.exists():
            return []
        lessons = []
        for line in self._path.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                try:
                    lessons.append(Lesson.from_dict(json.loads(line)))
                except (json.JSONDecodeError, TypeError):
                    continue
        return lessons

    def load_confirmed(self) -> list[Lesson]:
        return [l for l in self.load_all() if l.status == "confirmed"]

    def load_pending(self) -> list[Lesson]:
        return [l for l in self.load_all() if l.status == "pending"]

    def update_status(self, lesson_id: str, status: str, **kwargs) -> bool:
        """更新指定 lesson 的狀態（重寫整個檔案）."""
        lessons = self.load_all()
        found = False
        for l in lessons:
            if l.lesson_id == lesson_id:
                l.status = status
                for k, v in kwargs.items():
                    if hasattr(l, k):
                        setattr(l, k, v)
                found = True
                break
        if found:
            with open(self._path, "w", encoding="utf-8") as f:
                for l in lessons:
                    f.write(json.dumps(l.to_dict(), ensure_ascii=False) + "\n")
        return found

    def match_finding(self, finding: dict) -> Optional[Lesson]:
        """用 finding 的特徵匹配已確認的 lesson.

        匹配邏輯：
        1. error_type 完全匹配
        2. blast_origin_file 匹配（或 symptom_pattern 正則匹配）
        3. 信心度 >= 0.7

        Returns:
            匹配到的 Lesson，或 None
        """
        origin = finding.get("blast_origin", {})
        if isinstance(origin, dict):
            f_error = origin.get("error_type", "")
            f_file = origin.get("file", "")
        else:
            f_error = ""
            f_file = ""

        f_title = finding.get("title", "")

        for lesson in self.load_confirmed():
            if lesson.verified_confidence < 0.7:
                continue

            # error_type 匹配
            if lesson.error_type and lesson.error_type == f_error:
                if lesson.blast_origin_file and lesson.blast_origin_file == f_file:
                    return lesson

            # symptom_pattern 正則匹配
            if lesson.symptom_pattern:
                try:
                    if re.search(lesson.symptom_pattern, f_title, re.IGNORECASE):
                        return lesson
                except re.error:
                    continue

        return None
