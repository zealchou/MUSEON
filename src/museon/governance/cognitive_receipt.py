"""認知回執（Compact Cognitive Receipt）

每次 Brain 回應後自動產生的認知管線摘要，記錄 Python 層看不到的認知決策：
- deep-think P0 訊號分流結果
- query-clarity 品質守門結果
- 使用者能量感知
- C15 語言層啟用狀態
- Resonance 共振觸發
- 三迴圈路由結果
- 前 3 匹配 Skill

每筆 ~30-50 tokens，持久化至 cognitive_trace.jsonl。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List


@dataclass
class CognitiveReceipt:
    """精簡認知回執."""

    # deep-think P0 訊號分流
    p0_signal: str = ""          # "理性" | "感性" | "混合" | "轉化" | "哲學"

    # query-clarity 守門結果
    qc_verdict: str = ""         # "pass" | "clarify" | "skip"

    # 使用者能量感知
    user_energy: str = ""        # "高" | "中" | "低"

    # C15 語言層啟用
    c15_active: bool = False

    # Resonance 共振觸發
    resonance: bool = False

    # 三迴圈路由
    loop: str = ""               # "F" (fast) | "E" (exploration) | "S" (slow)

    # 前 3 匹配 Skill
    top_skills: List[str] = field(default_factory=list)

    # 自由欄位（≤50 字元）
    meta_note: str = ""

    def to_dict(self) -> dict:
        """轉為可序列化 dict."""
        d = asdict(self)
        # 限制 meta_note 長度
        d["meta_note"] = d["meta_note"][:50]
        # 限制 top_skills 數量
        d["top_skills"] = d["top_skills"][:3]
        return d
