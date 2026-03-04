"""Tier A Safety Clusters — 7 安全反射叢集偵測.

依據 DNA27 Neural Tract BDD Spec §2.2 (Tier A) 實作：
  - 純 CPU 關鍵字 + regex 匹配
  - 每個叢集有權重、關鍵字列表、正則表達式列表
  - Keyword hit: weight × 0.7; Regex hit: weight × 1.0
  - 每叢集分數上限 3.0
  - Tier 聚合：取叢集中的最高分

用途：
  - 在 brain.py Step 3 路由階段偵測安全訊號
  - 觸發 fast_loop 或在 system prompt 注入安全上下文
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

CLUSTER_MAX_SCORE = 3.0
KEYWORD_MULTIPLIER = 0.7
REGEX_MULTIPLIER = 1.0

# Tier A score threshold for triggering safety context injection
SAFETY_TRIGGER_THRESHOLD = 0.5


# ═══════════════════════════════════════════
# Cluster Definition
# ═══════════════════════════════════════════


@dataclass
class SafetyCluster:
    """單一安全反射叢集定義."""

    cluster_id: str
    name: str
    weight: float
    keywords: List[str] = field(default_factory=list)
    regex_patterns: List[str] = field(default_factory=list)
    _compiled_patterns: List[re.Pattern] = field(
        default_factory=list, repr=False,
    )

    def __post_init__(self):
        self._compiled_patterns = []
        for pat in self.regex_patterns:
            try:
                self._compiled_patterns.append(re.compile(pat))
            except re.error as e:
                logger.warning(
                    f"Invalid regex in {self.cluster_id}: {pat} — {e}"
                )


# ═══════════════════════════════════════════
# Tier A Clusters (BDD Spec §2.2)
# ═══════════════════════════════════════════

TIER_A_CLUSTERS: List[SafetyCluster] = [
    SafetyCluster(
        cluster_id="RC-A1",
        name="energy_depletion",
        weight=1.0,
        keywords=["累", "疲憊", "burnout", "沒力氣", "耗盡", "撐不住",
                   "好累", "累死", "精力", "過勞"],
        regex_patterns=[r"累.*了", r"好.*累", r"撐.*不.*住"],
    ),
    SafetyCluster(
        cluster_id="RC-A2",
        name="emotional_overheating",
        weight=1.0,
        keywords=["崩潰", "爆炸", "焦慮", "恐慌", "受不了", "失控",
                   "快瘋了", "壓力", "煩躁", "抓狂"],
        regex_patterns=[r"快要.*崩", r"受不了", r"快.*瘋"],
    ),
    SafetyCluster(
        cluster_id="RC-A3",
        name="irreversible_interception",
        weight=1.5,
        keywords=["不可逆", "離婚", "刪除所有", "放棄一切", "結束",
                   "再也不", "不可挽回", "毀掉", "斷絕"],
        regex_patterns=[r"刪除.*所有", r"不可挽回", r"放棄.*一切"],
    ),
    SafetyCluster(
        cluster_id="RC-A4",
        name="risk_overload",
        weight=0.8,
        keywords=["風險", "all in", "孤注一擲", "賭一把", "全部壓",
                   "全梭", "豪賭", "冒險"],
        regex_patterns=[r"全部.*壓", r"all.*in", r"孤注.*一擲"],
    ),
    SafetyCluster(
        cluster_id="RC-A5",
        name="emergency_downgrade",
        weight=0.7,
        keywords=["緊急", "馬上", "立刻", "急", "趕快", "救命",
                   "火燒", "來不及"],
        regex_patterns=[r"馬上.*做", r"立刻", r"來不及"],
    ),
    SafetyCluster(
        cluster_id="RC-A6",
        name="self_dissolution",
        weight=0.9,
        keywords=["迷失", "我是誰", "不知道自己", "找不到方向",
                   "失去自我", "空虛", "虛無", "意義"],
        regex_patterns=[r"不知道.*自己", r"迷失", r"找不到.*方向"],
    ),
    SafetyCluster(
        cluster_id="RC-A7",
        name="safety_first",
        weight=0.6,
        keywords=["安全", "保護", "小心", "謹慎", "防範",
                   "風險控管", "停損"],
        regex_patterns=[r"保護.*好", r"安全.*第一"],
    ),
]


# ═══════════════════════════════════════════
# Detection Engine
# ═══════════════════════════════════════════


def detect_safety_clusters(
    message: str,
    clusters: Optional[List[SafetyCluster]] = None,
) -> Dict[str, float]:
    """偵測訊息中的安全反射叢集.

    Args:
        message: 使用者訊息
        clusters: 叢集定義列表（預設 TIER_A_CLUSTERS）

    Returns:
        {cluster_id: score} — 只包含 score > 0 的叢集
    """
    if not message:
        return {}

    if clusters is None:
        clusters = TIER_A_CLUSTERS

    results: Dict[str, float] = {}

    for cluster in clusters:
        score = 0.0

        # Keyword matching
        for kw in cluster.keywords:
            if kw.lower() in message.lower():
                score += cluster.weight * KEYWORD_MULTIPLIER

        # Regex matching
        for pattern in cluster._compiled_patterns:
            if pattern.search(message):
                score += cluster.weight * REGEX_MULTIPLIER

        # Per-cluster cap
        score = min(score, CLUSTER_MAX_SCORE)

        if score > 0:
            results[cluster.cluster_id] = round(score, 2)

    return results


def get_tier_a_score(cluster_scores: Dict[str, float]) -> float:
    """取得 Tier A 的聚合分數（取最高值）.

    BDD Spec: tier aggregation = max of cluster scores.
    """
    a_scores = [
        v for k, v in cluster_scores.items()
        if k.startswith("RC-A")
    ]
    return max(a_scores) if a_scores else 0.0


def get_triggered_clusters(
    cluster_scores: Dict[str, float],
    threshold: float = SAFETY_TRIGGER_THRESHOLD,
) -> List[str]:
    """取得超過閾值的叢集 ID 清單."""
    return [
        cid for cid, score in cluster_scores.items()
        if score >= threshold
    ]


def build_safety_context(
    cluster_scores: Dict[str, float],
) -> str:
    """依據偵測到的安全叢集，生成系統提示安全上下文.

    注入到 system prompt 中，引導 AI 用適當方式回應。
    """
    if not cluster_scores:
        return ""

    tier_a = get_tier_a_score(cluster_scores)
    if tier_a < SAFETY_TRIGGER_THRESHOLD:
        return ""

    # 建構安全指引
    triggered = get_triggered_clusters(cluster_scores)

    # Cluster name mapping
    cluster_names = {c.cluster_id: c.name for c in TIER_A_CLUSTERS}

    active_names = [
        cluster_names.get(cid, cid) for cid in triggered
    ]

    safety_text = "## 安全感知\n\n"
    safety_text += "偵測到以下安全訊號，請調整回應方式：\n\n"

    for cid in triggered:
        name = cluster_names.get(cid, cid)
        score = cluster_scores[cid]

        if name == "energy_depletion":
            safety_text += (
                f"- 能量耗竭訊號（強度 {score:.1f}）："
                "先接住疲憊感，給最小可行的下一步，"
                "禁止長篇推演\n"
            )
        elif name == "emotional_overheating":
            safety_text += (
                f"- 情緒過熱訊號（強度 {score:.1f}）："
                "先用 1-3 句接住情緒，不急著分析，"
                "等對方準備好再展開\n"
            )
        elif name == "irreversible_interception":
            safety_text += (
                f"- 不可逆決策訊號（強度 {score:.1f}）："
                "主動提出代價和後果，建議先暫停 24 小時，"
                "不要替對方做決定\n"
            )
        elif name == "risk_overload":
            safety_text += (
                f"- 風險超載訊號（強度 {score:.1f}）："
                "同框呈現風險和機會，提供 Plan B，"
                "避免助長衝動決策\n"
            )
        elif name == "emergency_downgrade":
            safety_text += (
                f"- 緊急降速訊號（強度 {score:.1f}）："
                "切換到 fast_loop，只給止血方案，"
                "不展開完整分析\n"
            )
        elif name == "self_dissolution":
            safety_text += (
                f"- 自我消融訊號（強度 {score:.1f}）："
                "先確認對方的存在感和價值，"
                "避免說教，用提問幫助釐清\n"
            )
        elif name == "safety_first":
            safety_text += (
                f"- 安全優先訊號（強度 {score:.1f}）："
                "優先處理安全需求，再談其他\n"
            )

    # 高強度時加入強制指令
    if tier_a >= 1.5:
        safety_text += (
            "\n⚠️ 高強度安全訊號 — 強制切換 fast_loop：\n"
            "- 回覆控制在 200 字以內\n"
            "- 不展開多方案推演\n"
            "- 先接住 → 一個最小下一步\n"
        )

    return safety_text
