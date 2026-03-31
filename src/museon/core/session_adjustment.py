"""SessionAdjustment — 覺察後的即時行為調整.

覺察的下一步不是「記住」，是「這一秒開始不一樣」。
SessionAdjustment 是 session-scoped 的行為調整清單，
下一輪 _build_system_prompt() 讀取後立即生效。

存在記憶體中（不持久化），Session 結束後自動清空。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 路徑常數
_AWARENESS_LOG = "data/_system/awareness_log.jsonl"
_PENDING_ADJUSTMENTS = "data/_system/pending_adjustments.json"


# ── 調整類型常數 ───────────────────────────────────────────────────────────────

COMPRESS_OUTPUT = "compress_output"
"""壓縮輸出：回覆改短、減少解釋、只給結論"""

SWITCH_APPROACH = "switch_approach"
"""切換方法：換一個角度或框架處理同一問題"""

DEGRADE_SKILL = "degrade_skill"
"""降級 Skill：某 Skill 暫時停用或降低優先度"""

INCREASE_DEPTH = "increase_depth"
"""加深分析：擴大推論層數、引用更多背景知識"""

SIMPLIFY_LANGUAGE = "simplify_language"
"""簡化語言：使用較白話的表達，減少術語"""


# ── dataclass ──────────────────────────────────────────────────────────────────


@dataclass
class SessionAdjustment:
    """單一行為調整指令.

    使用方式：
        adj = SessionAdjustment(
            trigger="user_confusion_detected",
            adjustment=SIMPLIFY_LANGUAGE,
            params={"max_jargon_per_sentence": 0},
            expires_after_turns=3,
            created_at_turn=5,
        )
        manager.add(session_id, adj)
    """

    trigger: str
    """觸發此調整的原因，例如 'user_confusion_detected'"""

    adjustment: str
    """調整類型（使用上方常數，或任意字串）"""

    params: Dict[str, Any] = field(default_factory=dict)
    """調整參數（傳給 prompt builder 的鍵值對）"""

    expires_after_turns: int = 5
    """幾輪後過期（從 created_at_turn 開始計算，0 = 永不過期）"""

    created_at_turn: int = 0
    """建立時的對話輪次"""

    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    """建立時間（UTC ISO 8601）"""

    def is_active(self, current_turn: int) -> bool:
        """判斷此調整是否仍在有效期內.

        expires_after_turns == 0 表示永不過期。
        """
        if self.expires_after_turns == 0:
            return True
        return current_turn < self.created_at_turn + self.expires_after_turns


# ── Manager ────────────────────────────────────────────────────────────────────


class SessionAdjustmentManager:
    """管理所有 session 的即時行為調整.

    設計為 singleton（可從 Brain 或 server.py 持有單一實例）。
    資料僅存記憶體，重啟後自動清空——這是刻意設計：
    調整是「這一秒不一樣」，不應該在重啟後繼續影響行為。
    """

    def __init__(self) -> None:
        # session_id → 調整清單
        self._adjustments: Dict[str, List[SessionAdjustment]] = {}

    def add(self, session_id: str, adjustment: SessionAdjustment) -> None:
        """新增一條行為調整指令.

        相同 trigger 的調整會取代舊有的（避免重複疊加）。
        """
        if session_id not in self._adjustments:
            self._adjustments[session_id] = []

        # 移除相同 trigger 的舊調整，避免重複
        self._adjustments[session_id] = [
            a for a in self._adjustments[session_id]
            if a.trigger != adjustment.trigger
        ]
        self._adjustments[session_id].append(adjustment)

    def get_active(
        self, session_id: str, current_turn: int
    ) -> List[SessionAdjustment]:
        """取得指定 session 目前有效的調整清單.

        過期的調整會被自動過濾（懶清理，不主動刪除）。
        """
        if session_id not in self._adjustments:
            return []
        return [
            a for a in self._adjustments[session_id]
            if a.is_active(current_turn)
        ]

    def clear(self, session_id: str) -> None:
        """清空指定 session 的所有調整（session 結束時呼叫）."""
        self._adjustments.pop(session_id, None)

    def format_for_prompt(self, session_id: str, current_turn: int) -> str:
        """產出可注入 system prompt 的文字區塊.

        如果沒有有效調整，回傳空字串（不注入任何內容）。

        範例輸出：
            ## 即時行為調整（本輪生效）
            - [compress_output] 壓縮輸出：params={'max_sentences': 3}
            - [simplify_language] 簡化語言：params={}
        """
        active = self.get_active(session_id, current_turn)
        if not active:
            return ""

        lines = ["## 即時行為調整（本輪生效）"]
        for adj in active:
            params_str = f"params={adj.params}" if adj.params else ""
            expires_str = (
                f"（剩 {adj.created_at_turn + adj.expires_after_turns - current_turn} 輪）"
                if adj.expires_after_turns > 0
                else "（永久）"
            )
            lines.append(
                f"- [{adj.adjustment}] trigger={adj.trigger} "
                f"{params_str} {expires_str}"
            )

        return "\n".join(lines)

    def load_from_l4(self, workspace: Path, session_id: str) -> int:
        """從 L4 觀察者寫入的檔案載入 SessionAdjustment.

        L4 用 Write 工具寫入 data/_system/session_adjustments/{session_id}.json，
        Brain 下一輪 _build_system_prompt() 時透過此方法載入。

        Returns: 載入的調整數量
        """
        adj_file = workspace / "data" / "_system" / "session_adjustments" / f"{session_id}.json"
        if not adj_file.exists():
            return 0

        try:
            data = json.loads(adj_file.read_text(encoding="utf-8"))
            count = 0
            for item in data.get("adjustments", []):
                adj = SessionAdjustment(
                    trigger=item.get("trigger", ""),
                    adjustment=item.get("adjustment", ""),
                    params=item.get("params", {}),
                    expires_after_turns=item.get("expires_after_turns", 3),
                    created_at_turn=item.get("created_at_turn", 0),
                )
                self.add(session_id, adj)
                count += 1
            return count
        except Exception:
            return 0

    def session_count(self) -> int:
        """目前管理的 session 數量（供監控用）."""
        return len(self._adjustments)

    def total_adjustments(self) -> int:
        """所有 session 中的調整總數（供監控用）."""
        return sum(len(v) for v in self._adjustments.values())

    # ── 補線 B：record_outcome ──────────────────────────────────────────────────

    def set_workspace(self, workspace: Path) -> None:
        """設定 workspace 路徑，供 record_outcome 持久化使用."""
        self._workspace = workspace

    def record_outcome(
        self,
        session_id: str,
        adjustment: "SessionAdjustment",
        worked: bool,
        context: str = "",
        workspace: Optional[Path] = None,
    ) -> None:
        """行動完成後，自動記錄覺察+行動+結果配對.

        紀錄是行動的副產品，不是另外一個步驟。
        累積同類成功 ≥3 次 → 自動寫入對應 Skill 的 _lessons.json。
        """
        ws = workspace or getattr(self, "_workspace", None)

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trigger": adjustment.trigger,
            "adjustment": adjustment.adjustment,
            "worked": worked,
            "context": context,
            "session_id": session_id,
        }

        # 寫入 awareness_log.jsonl
        if ws is not None:
            log_path = ws / _AWARENESS_LOG
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # 維護 outcome_counts（記憶體內）
        if not hasattr(self, "_outcome_counts"):
            self._outcome_counts: Dict[str, int] = {}

        if worked:
            key = f"{adjustment.trigger}:{adjustment.adjustment}"
            self._outcome_counts[key] = self._outcome_counts.get(key, 0) + 1
            if self._outcome_counts[key] >= 3:
                self._promote_to_lesson(
                    adjustment.trigger,
                    adjustment.adjustment,
                    ws,
                )
                # 重置計數，避免重複升級
                self._outcome_counts[key] = 0

        logger.debug(
            "record_outcome: trigger=%s adjustment=%s worked=%s session=%s",
            adjustment.trigger,
            adjustment.adjustment,
            worked,
            session_id,
        )

    def _promote_to_lesson(
        self,
        trigger: str,
        adjustment: str,
        workspace: Optional[Path],
    ) -> None:
        """累積 3 次成功的調整，升級為 Skill 教訓."""
        lesson = {
            "trigger": trigger,
            "adjustment": adjustment,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
            "source": "record_outcome_accumulation",
        }

        if workspace is None:
            logger.warning(
                "_promote_to_lesson: workspace 未設定，無法寫入教訓（trigger=%s）", trigger
            )
            return

        # 嘗試從 trigger 推導 skill_name
        # trigger 格式可能是 "skill_health_tracker:darwin" 或 "darwin:quality_drop" 等
        skill_name = _infer_skill_name(trigger, adjustment)

        if skill_name:
            skill_lessons_path = (
                workspace / "data" / "skills" / "native" / skill_name / "_lessons.json"
            )
        else:
            skill_lessons_path = workspace / "data" / "_system" / "general_lessons.json"

        skill_lessons_path.parent.mkdir(parents=True, exist_ok=True)

        existing: List[Dict[str, Any]] = []
        if skill_lessons_path.exists():
            try:
                existing = json.loads(skill_lessons_path.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except (json.JSONDecodeError, ValueError):
                existing = []

        existing.append(lesson)
        skill_lessons_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "_promote_to_lesson: 教訓已升級 trigger=%s adjustment=%s → %s",
            trigger,
            adjustment,
            skill_lessons_path,
        )

    # ── 補線 C（session_adjustment 側）：load_pending_from_nightly ───────────────

    def load_pending_from_nightly(self, workspace: Path, session_id: str) -> int:
        """Brain 啟動時呼叫，載入 Nightly 產出的 pending_adjustments.

        載入後清空檔案（一次性消費）。
        返回載入的數量。
        """
        pending_path = workspace / _PENDING_ADJUSTMENTS
        if not pending_path.exists():
            return 0

        try:
            items = json.loads(pending_path.read_text(encoding="utf-8"))
            if not isinstance(items, list):
                return 0
        except (json.JSONDecodeError, ValueError):
            return 0

        count = 0
        for item in items:
            try:
                adj = SessionAdjustment(
                    trigger=item.get("trigger", "nightly_pending"),
                    adjustment=item.get("adjustment", ""),
                    params=item.get("params", {}),
                    expires_after_turns=item.get("expires_after_turns", 5),
                )
                self.add(session_id, adj)
                count += 1
            except (KeyError, TypeError) as e:
                logger.warning("load_pending_from_nightly: 跳過格式錯誤條目 (%s)", e)

        # 一次性消費：清空檔案
        pending_path.write_text("[]", encoding="utf-8")

        logger.info(
            "load_pending_from_nightly: 載入 %d 條 pending adjustments → session %s",
            count,
            session_id,
        )
        return count


# ── 模組級別 helper ────────────────────────────────────────────────────────────


_KNOWN_SKILLS = {
    "darwin", "shadow-muse", "ares", "market-ares", "onemuse-core",
    "brand-project-engine", "talent-match", "biz-collab", "video-strategy",
    "daily-pilot", "plugin-registry",
}


def _infer_skill_name(trigger: str, adjustment: str) -> Optional[str]:
    """從 trigger 或 adjustment 字串中推導 skill_name.

    返回推導出的 skill_name，或 None（表示無法推導，應寫入 general_lessons）。
    """
    # 掃描 trigger 和 adjustment 中是否包含已知 Skill 名稱
    for candidate in (trigger, adjustment):
        for skill in _KNOWN_SKILLS:
            if skill in candidate:
                return skill
    return None


# ── 模組級別單例 ───────────────────────────────────────────────────────────────

# 其他模組可直接 import 使用，不需要自行實例化
_manager: Optional[SessionAdjustmentManager] = None


def get_manager() -> SessionAdjustmentManager:
    """取得全域 SessionAdjustmentManager 單例."""
    global _manager
    if _manager is None:
        _manager = SessionAdjustmentManager()
    return _manager
