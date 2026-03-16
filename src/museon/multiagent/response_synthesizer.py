"""Response Synthesizer — 多部門回覆合成器.

依據施工計畫 Phase 4.5 實作。
將主部門回覆為基底，輔助部門觀點作為補充。
"""

import logging
from typing import List

from museon.multiagent.multi_agent_executor import (
    DepartmentResponse,
    MultiAgentResult,
)

logger = logging.getLogger(__name__)

# 合成模式
SYNTHESIS_SIMPLE = "simple"         # 只用主部門
SYNTHESIS_ANNOTATED = "annotated"   # 主部門 + 輔助註解


def synthesize(result: MultiAgentResult) -> str:
    """合成多部門回覆.

    策略：
    - 只有主部門 → 直接回傳
    - 主部門 + 輔助 → 主回覆 + 補充觀點
    """
    if not result.auxiliaries:
        return result.primary.response

    return _annotated_synthesis(result.primary, result.auxiliaries)


def _annotated_synthesis(
    primary: DepartmentResponse,
    auxiliaries: List[DepartmentResponse],
) -> str:
    """帶註解的合成：主回覆 + 輔助部門補充.

    格式：
    [主部門回覆]

    ---
    💡 多角度補充：
    - ⚡ 雷部：...
    - 🌊 水部：...
    """
    parts = [primary.response]

    # 過濾有效的輔助回覆
    valid_aux = [
        a for a in auxiliaries
        if a.response and not a.error and len(a.response.strip()) > 10
    ]

    if not valid_aux:
        return primary.response

    # 建構補充區塊
    supplements = []
    for aux in valid_aux:
        # 從輔助回覆中提取精華（取前 200 字）
        summary = _extract_key_insight(aux.response)
        if summary:
            supplements.append(f"- {aux.emoji} **{aux.dept_name}**：{summary}")

    if supplements:
        parts.append("\n\n---\n💡 **多角度補充**：")
        parts.extend(supplements)

    return "\n".join(parts)


def _extract_key_insight(response: str, max_len: int = 200) -> str:
    """從部門回覆中提取關鍵洞察.

    策略：取第一段非空內容，截斷到 max_len。
    """
    lines = response.strip().split("\n")

    # 跳過標題行（# 開頭）和空行
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("---"):
            continue

        # 找到第一個有意義的段落
        if len(stripped) > max_len:
            return stripped[:max_len] + "…"
        return stripped

    return ""
