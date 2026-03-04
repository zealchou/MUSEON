"""Context Switcher — 部門切換與對話歷史管理.

壓縮策略：Fallback 截斷（前 5 條 × 60 字）。
📌 未來接入本地 LLM 時可替換 _compress() 方法。

依據 MULTI_AGENT_BDD_SPEC §4 實作。
"""

import logging
from typing import Any, Dict, List, Optional

from museclaw.multiagent.department_config import get_department

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

COMPRESS_MSG_COUNT = 5       # Fallback 取最近 N 條
COMPRESS_MSG_MAX_CHARS = 60  # 每條截取字元數
COMPRESS_MAX_TOTAL = 300     # 壓縮摘要最大字元數


class ContextSwitcher:
    """部門對話切換器."""

    def __init__(self) -> None:
        self._dept_histories: Dict[str, List[Dict[str, str]]] = {}
        self._current_dept: str = "core"
        self._switch_count: int = 0
        self._switch_log: List[Dict[str, Any]] = []   # 切換紀錄

    # ═══════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════

    @property
    def current_dept(self) -> str:
        return self._current_dept

    @property
    def switch_count(self) -> int:
        return self._switch_count

    def get_history(self, dept_id: str) -> List[Dict[str, str]]:
        """取得部門對話歷史."""
        return list(self._dept_histories.get(dept_id, []))

    def add_message(self, role: str, content: str) -> None:
        """新增訊息到當前部門歷史."""
        if self._current_dept not in self._dept_histories:
            self._dept_histories[self._current_dept] = []
        self._dept_histories[self._current_dept].append({
            "role": role,
            "content": content,
        })

    def switch_to(self, dept_id: str) -> Dict[str, Any]:
        """切換至目標部門.

        流程：
        1. 驗證部門存在
        2. 壓縮前一部門的對話歷史
        3. 注入壓縮摘要至目標部門
        4. 更新 _current_dept
        5. 記錄切換

        Returns:
            切換結果 dict.
        """
        dept = get_department(dept_id)
        if dept is None:
            return {"switched": False, "reason": "department_not_found"}

        if dept_id == self._current_dept:
            return {"switched": False, "reason": "already_in_department"}

        old_dept = self._current_dept
        compressed = ""

        # 壓縮前一部門歷史
        old_history = self._dept_histories.get(old_dept, [])
        if old_history:
            compressed = self._compress(old_history)

        # 注入壓縮摘要到目標部門
        if compressed:
            if dept_id not in self._dept_histories:
                self._dept_histories[dept_id] = []
            self._dept_histories[dept_id].append({
                "role": "system",
                "content": f"[{old_dept}→{dept_id}] 前段摘要：{compressed}",
            })

        # 更新狀態
        self._current_dept = dept_id
        self._switch_count += 1
        self._switch_log.append({
            "from": old_dept,
            "to": dept_id,
            "compressed_len": len(compressed),
        })

        logger.info(f"Context switch: {old_dept} -> {dept_id}")

        return {
            "switched": True,
            "from": old_dept,
            "to": dept_id,
            "compressed_len": len(compressed),
        }

    def get_department_prompt(self, dept_id: str) -> str:
        """取得部門角色 prompt."""
        dept = get_department(dept_id)
        return dept.prompt_section if dept else ""

    def get_switch_log(self) -> List[Dict[str, Any]]:
        """取得切換紀錄."""
        return list(self._switch_log)

    def get_stats(self) -> Dict[str, Any]:
        """取得統計資訊（供 Dashboard 用）."""
        dept_msg_counts: Dict[str, int] = {}
        for dept_id, history in self._dept_histories.items():
            dept_msg_counts[dept_id] = len(history)

        return {
            "current_dept": self._current_dept,
            "switch_count": self._switch_count,
            "dept_message_counts": dept_msg_counts,
            "recent_switches": self._switch_log[-10:],
        }

    # ═══════════════════════════════════════
    # Internal — 壓縮
    # ═══════════════════════════════════════

    def _compress(self, history: List[Dict[str, str]]) -> str:
        """Fallback 壓縮：最近 5 條 × 60 字.

        📌 未來可替換為本地 LLM 壓縮。
        """
        recent = history[-COMPRESS_MSG_COUNT:]
        lines = []
        for msg in recent:
            content = msg.get("content", "")
            truncated = content[:COMPRESS_MSG_MAX_CHARS]
            if len(content) > COMPRESS_MSG_MAX_CHARS:
                truncated += "…"
            lines.append(truncated)

        result = "\n".join(lines)
        return result[:COMPRESS_MAX_TOTAL]
