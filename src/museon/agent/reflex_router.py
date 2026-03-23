"""DNA27 ReflexRouter — 反射路由器（神經束核心）.

依據 DNA27 Neural Tract BDD Spec §2-§9, §15 實作：
  - 27 Reflex Clusters (Tier A-E) 全量偵測
  - RoutingSignal frozen dataclass（不可變全域信號）
  - Loop / Mode 選擇器 (FAST / EXPLORATION / SLOW)
  - LRU 路由快取（100 筆，<1ms 命中）
  - 動態 max_push 計算（連動結晶注入量）

設計原則：
  - 純 Python <20ms，零 LLM 調用
  - RoutingSignal 在整個 chat() 生命週期保持不變
  - 被六大子系統（神經束）消費：
    1) ContextPipeline  2) Tool Registry  3) Module Registry
    4) Memory System    5) Knowledge Graph 6) WEE/Morphenix
"""

import hashlib
import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

CLUSTER_MAX_SCORE = 3.0
KEYWORD_MULTIPLIER = 0.7
REGEX_MULTIPLIER = 1.0
LOOP_THRESHOLD = 0.5
_ROUTE_CACHE_SIZE = 100


# ═══════════════════════════════════════════
# RoutingSignal — 不可變全域信號
# ═══════════════════════════════════════════

@dataclass(frozen=True)
class RoutingSignal:
    """DNA27 路由信號 — 被所有神經束消費的不可變信號.

    BDD Spec §3: frozen dataclass，在整個 chat() 生命週期保持不變。
    """
    # 核心路由
    tier_scores: Dict[str, float]       # {"A": 0.8, "B": 0.3, ...}
    top_clusters: Tuple[str, ...]       # ("RC-A1_energy_depletion", ...)
    loop: str                           # "FAST_LOOP" | "EXPLORATION_LOOP" | "SLOW_LOOP"
    mode: str                           # "CIVIL_MODE" | "EVOLUTION_MODE"

    # 輔助
    confidence: float = 0.0
    raw_message_len: int = 0

    # 動態結晶注入量
    max_crystal_push: int = 5

    # v9.1: 叢集原始分數（供 Skill 壓制閾值過濾用）
    cluster_scores: Dict[str, float] = field(default_factory=dict)

    # 路由耗時
    route_time_ms: float = 0.0

    @property
    def primary_tier(self) -> str:
        """最高分的 tier，預設 C."""
        if not self.tier_scores:
            return "C"
        return max(self.tier_scores, key=self.tier_scores.get)

    @property
    def is_high_tier(self) -> bool:
        """是否為高層級路由（A 或 B 觸發）."""
        return self.primary_tier in ("A", "B")

    @property
    def max_tier_score(self) -> float:
        """最高 tier 分數."""
        return max(self.tier_scores.values()) if self.tier_scores else 0.0

    @property
    def is_safety_triggered(self) -> bool:
        """Tier A 安全觸發."""
        return self.tier_scores.get("A", 0) >= LOOP_THRESHOLD

    @property
    def is_sovereignty_triggered(self) -> bool:
        """Tier B 主權觸發."""
        return self.tier_scores.get("B", 0) >= LOOP_THRESHOLD

    def to_dict(self) -> Dict[str, Any]:
        """序列化為 dict（供記憶嵌入用）."""
        return {
            "tier_scores": dict(self.tier_scores),
            "top_clusters": list(self.top_clusters),
            "loop": self.loop,
            "mode": self.mode,
            "max_crystal_push": self.max_crystal_push,
            "confidence": self.confidence,
        }


# ═══════════════════════════════════════════
# 27 Reflex Cluster 定義（Tier A-E）
# ═══════════════════════════════════════════

@dataclass
class ReflexCluster:
    """單一反射叢集."""
    cluster_id: str
    tier: str  # "A" | "B" | "C" | "D" | "E"
    name: str
    weight: float
    keywords: List[str] = field(default_factory=list)
    regex_patterns: List[str] = field(default_factory=list)
    _compiled: List[re.Pattern] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._compiled = []
        for pat in self.regex_patterns:
            try:
                # v10.2 Fix: 加入 IGNORECASE 避免英文 regex 漏匹配
                self._compiled.append(re.compile(pat, re.IGNORECASE))
            except re.error as e:
                logger.warning(f"Invalid regex in {self.cluster_id}: {pat} — {e}")


# ── Tier A — 安全與穩定（煞車系統）— 7 個 ──

TIER_A_CLUSTERS = [
    ReflexCluster(
        cluster_id="RC-A1", tier="A", name="energy_depletion", weight=1.0,
        keywords=["累", "疲憊", "burnout", "沒力氣", "耗盡", "撐不住",
                   "好累", "累死", "精力", "過勞"],
        regex_patterns=[r"累.*了", r"好.*累", r"撐.*不.*住"],
    ),
    ReflexCluster(
        cluster_id="RC-A2", tier="A", name="emotional_overheating", weight=1.0,
        keywords=["崩潰", "爆炸", "焦慮", "恐慌", "受不了", "失控",
                   "快瘋了", "壓力", "煩躁", "抓狂"],
        regex_patterns=[r"快要.*崩", r"受不了", r"快.*瘋"],
    ),
    ReflexCluster(
        cluster_id="RC-A3", tier="A", name="irreversible_interception", weight=1.5,
        keywords=["不可逆", "離婚", "刪除所有", "放棄一切", "結束",
                   "再也不", "不可挽回", "毀掉", "斷絕"],
        regex_patterns=[r"刪除.*所有", r"不可挽回", r"放棄.*一切"],
    ),
    ReflexCluster(
        cluster_id="RC-A4", tier="A", name="risk_overload", weight=0.8,
        keywords=["風險", "all in", "孤注一擲", "賭一把", "全部壓",
                   "全梭", "豪賭", "冒險"],
        regex_patterns=[r"全部.*壓", r"all.*in", r"孤注.*一擲"],
    ),
    ReflexCluster(
        cluster_id="RC-A5", tier="A", name="emergency_downgrade", weight=0.7,
        keywords=["緊急", "馬上", "立刻", "急", "趕快", "救命",
                   "火燒", "來不及"],
        regex_patterns=[r"馬上.*做", r"立刻", r"來不及"],
    ),
    ReflexCluster(
        cluster_id="RC-A6", tier="A", name="self_dissolution", weight=0.9,
        keywords=["迷失", "我是誰", "不知道自己", "找不到方向",
                   "失去自我", "空虛", "虛無", "意義"],
        regex_patterns=[r"不知道.*自己", r"迷失", r"找不到.*方向"],
    ),
    ReflexCluster(
        cluster_id="RC-A7", tier="A", name="safety_first", weight=0.6,
        keywords=["安全", "保護", "小心", "謹慎", "防範",
                   "風險控管", "停損"],
        regex_patterns=[r"保護.*好", r"安全.*第一"],
    ),
]

# ── Tier B — 主權與責任（方向盤保護）— 6 個 ──

TIER_B_CLUSTERS = [
    ReflexCluster(
        # v10.3 Fix: 再收窄——移除「幫我選」「你決定」（太通用），降權 0.6→0.4
        # 只保留明確的決策外包語句，避免成為重力井（v10.2 仍 55% 輪次觸發）
        cluster_id="RC-B1", tier="B", name="decision_outsourcing", weight=0.4,
        keywords=["幫我決定", "你說怎麼辦", "替我做主", "幫我做主"],
        regex_patterns=[r"[幫替]我.*決定", r"[幫替]我.*做主", r"你說.*怎麼辦"],
    ),
    ReflexCluster(
        cluster_id="RC-B2", tier="B", name="dependency_suppression", weight=0.7,
        keywords=["離不開", "依賴", "沒有你不行", "靠你了",
                   "上癮", "戒不掉"],
        regex_patterns=[r"離不開", r"沒有.*不行", r"依賴.*你"],
    ),
    ReflexCluster(
        cluster_id="RC-B3", tier="B", name="choice_avoidance", weight=0.7,
        keywords=["不想選", "逃避", "不想面對", "算了吧",
                   "不管了", "隨便"],
        regex_patterns=[r"不想.*選", r"不想.*面對", r"算了"],
    ),
    ReflexCluster(
        cluster_id="RC-B4", tier="B", name="consequence_bearing", weight=0.6,
        keywords=["後果", "責任", "承擔", "代價", "付出",
                   "結局", "收拾"],
        regex_patterns=[r"後果.*誰", r"誰.*負責", r"代價.*多大"],
    ),
    ReflexCluster(
        cluster_id="RC-B5", tier="B", name="sovereignty_recovery", weight=0.5,
        keywords=["主權", "拿回控制", "自己決定", "不需要別人",
                   "我的選擇", "自主"],
        regex_patterns=[r"拿回.*控制", r"自己.*決定", r"我.*的.*選擇"],
    ),
    ReflexCluster(
        cluster_id="RC-B6", tier="B", name="responsibility_timeline", weight=0.5,
        keywords=["長期", "連鎖反應", "蝴蝶效應", "未來影響",
                   "十年後", "二十年"],
        regex_patterns=[r"長期.*影響", r"連鎖.*反應", r"十年後"],
    ),
]

# ── Tier C — 認知誠實（反自我欺騙）— 5 個 ──

TIER_C_CLUSTERS = [
    ReflexCluster(
        cluster_id="RC-C1", tier="C", name="hallucination_interruption", weight=0.7,
        keywords=["確定", "一定是", "肯定是", "百分之百",
                   "絕對", "不可能錯"],
        regex_patterns=[r"一定.*是", r"肯定.*是", r"百分之百"],
    ),
    ReflexCluster(
        cluster_id="RC-C2", tier="C", name="narrative_deconstruction", weight=0.6,
        keywords=["故事", "敘事", "框架", "角度", "視角",
                   "觀點", "立場"],
        regex_patterns=[r"換個.*角度", r"另一個.*觀點", r"從.*來看"],
    ),
    ReflexCluster(
        # v10.3 Fix: 移除「大概」「估計」「可能」（太泛用，與 D1 碰撞）
        # 只保留明確的「不確定/不知道」系——認知坦承，非行動探索
        cluster_id="RC-C3", tier="C", name="unknown_manifestation", weight=0.6,
        keywords=["不確定", "不知道", "未知", "模糊", "不清楚",
                   "說不定", "猜測", "不太確定", "不太了解",
                   "不明確", "好像是", "搞不懂"],
        regex_patterns=[r"不確定", r"不知道.*怎", r"不太.*確定",
                        r"不太.*了解", r"不清楚", r"好像.*但",
                        r"搞不懂"],
    ),
    ReflexCluster(
        cluster_id="RC-C4", tier="C", name="motivation_confusion", weight=0.6,
        keywords=["動機", "為什麼", "目的", "原因",
                   "初衷", "出發點"],
        regex_patterns=[r"為什麼.*要", r"動機.*是", r"目的.*什麼"],
    ),
    ReflexCluster(
        cluster_id="RC-C5", tier="C", name="overconfidence_calibration", weight=0.5,
        keywords=["過度自信", "風險被低估", "太樂觀",
                   "盲點", "忽略"],
        regex_patterns=[r"過度.*自信", r"風險.*低估", r"太.*樂觀"],
    ),
]

# ── Tier D — 演化與實驗（可控犯錯）— 5 個 ──

TIER_D_CLUSTERS = [
    ReflexCluster(
        # v10.3 Fix: 擴展——加入行動意圖動詞（分析/研究/探索），與 C3 邊界分離
        # C3 = 坦承不知道（被動）；D1 = 想動手探索（主動）
        cluster_id="RC-D1", tier="D", name="experimental_boundary", weight=0.6,
        keywords=["嘗試", "試試", "實驗", "測試",
                   "原型", "MVP", "POC",
                   "分析", "研究", "探索", "深入了解", "調查",
                   "我想試", "教我", "怎麼做"],
        regex_patterns=[r"試試.*看", r"嘗試.*一下", r"做個.*實驗",
                        r"我想.*試", r"教我.*怎", r"怎麼.*做",
                        r"幫我.*分析", r"研究.*一下"],
    ),
    ReflexCluster(
        cluster_id="RC-D2", tier="D", name="error_budget", weight=0.5,
        keywords=["犯錯", "失敗", "預算", "容錯",
                   "可以錯", "允許失敗"],
        regex_patterns=[r"犯錯.*預算", r"允許.*失敗", r"可以.*錯"],
    ),
    ReflexCluster(
        cluster_id="RC-D3", tier="D", name="low_success_tolerance", weight=0.5,
        keywords=["成功率低", "可能失敗", "不保證",
                   "風險很高", "不一定"],
        regex_patterns=[r"成功率.*低", r"可能.*失敗", r"不一定.*成"],
    ),
    ReflexCluster(
        cluster_id="RC-D4", tier="D", name="rollback_enforcement", weight=0.6,
        keywords=["回滾", "退路", "備份", "還原",
                   "回退", "Plan B"],
        regex_patterns=[r"回滾", r"退路", r"Plan.*B"],
    ),
    ReflexCluster(
        cluster_id="RC-D5", tier="D", name="impact_scope", weight=0.5,
        keywords=["波及", "影響範圍", "擴散", "連帶",
                   "全面", "規模"],
        regex_patterns=[r"影響.*範圍", r"波及.*到", r"連帶.*影響"],
    ),
]

# ── Tier E — 整合與節律（慢層啟動器）— 4 個 ──

TIER_E_CLUSTERS = [
    ReflexCluster(
        # v10.3 Fix: 擴展時間感觸發詞
        cluster_id="RC-E1", tier="E", name="time_scale_extension", weight=0.5,
        keywords=["長遠", "十年後", "終局", "宏觀",
                   "大局", "最終目標", "願景",
                   "未來", "長期來看", "五年後", "下一步",
                   "人生規劃", "全局", "長期"],
        regex_patterns=[r"十年後", r"長遠.*來看", r"最終.*目標",
                        r"未來.*怎", r"五年.*後", r"長期.*來看",
                        r"人生.*規劃"],
    ),
    ReflexCluster(
        # v10.3 Fix: 擴展累積/沉澱觸發詞
        cluster_id="RC-E2", tier="E", name="choice_accumulation", weight=0.4,
        keywords=["累積", "沉澱", "厚積薄發", "一點一滴",
                   "持續", "堅持", "長久", "基礎",
                   "慢慢來", "穩紮穩打", "持之以恆"],
        regex_patterns=[r"累積.*起來", r"沉澱", r"一點.*一滴",
                        r"慢慢.*來", r"穩紮.*穩打"],
    ),
    ReflexCluster(
        # v10.3 Fix: 擴展循環/重複辨識——v10.2 只有 6 詞太窄
        cluster_id="RC-E3", tier="E", name="state_cycle", weight=0.6,
        keywords=["循環", "週期", "又來了", "老問題",
                   "重蹈覆轍", "反覆", "每次都這樣",
                   "老毛病", "死循環", "走不出來", "鬼打牆",
                   "一直重複", "同樣的問題", "怎麼又"],
        regex_patterns=[r"又.*來了", r"循環", r"重蹈.*覆轍",
                        r"每次.*都.*這樣", r"一直.*重複",
                        r"老.*毛病", r"怎麼又"],
    ),
    ReflexCluster(
        cluster_id="RC-E4", tier="E", name="rhythm_recovery", weight=0.5,
        keywords=["節奏", "恢復", "休息", "調整",
                   "喘口氣", "緩一緩"],
        regex_patterns=[r"喘口氣", r"緩一緩", r"調整.*節奏"],
    ),
]

# ── Tier F — 系統診斷（自我感知）— 4 個 ──

TIER_F_CLUSTERS = [
    ReflexCluster(
        cluster_id="RC-F1", tier="F", name="system_health_inquiry", weight=0.8,
        keywords=["系統狀態", "健康狀態", "正常運作", "有沒有壞", "運作正常",
                   "系統正常", "系統健康", "gateway", "服務狀態"],
        regex_patterns=[r"系統.*狀態", r"正常.*運作", r"有沒有.*壞",
                        r"運作.*正常", r"系統.*健康"],
    ),
    ReflexCluster(
        cluster_id="RC-F2", tier="F", name="tool_status_check", weight=0.7,
        keywords=["工具", "連線", "同步", "心跳", "排程", "cron",
                   "dify", "zotero", "xtts", "stability", "degraded",
                   "工具狀態", "工具壞了"],
        regex_patterns=[r"工具.*狀態", r"工具.*壞", r"連線.*正常",
                        r"排程.*正常", r"心跳.*機制"],
    ),
    ReflexCluster(
        cluster_id="RC-F3", tier="F", name="self_diagnosis", weight=0.9,
        keywords=["自我診斷", "自我檢查", "系統診斷", "哪裡壞了",
                   "什麼問題", "哪裡有問題", "bug", "錯誤", "故障",
                   "異常", "功能異常"],
        regex_patterns=[r"哪裡.*壞", r"什麼.*問題", r"哪裡.*有.*問題",
                        r"功能.*異常", r"自我.*診斷", r"自我.*檢查"],
    ),
    ReflexCluster(
        cluster_id="RC-F4", tier="F", name="operational_feedback", weight=0.6,
        keywords=["機制", "功能", "模組", "更新", "版本", "設定",
                   "配置", "有在運作", "沒有運作", "失靈", "失效"],
        regex_patterns=[r"有在.*運作", r"沒有.*運作", r"機制.*失[靈效]",
                        r"功能.*沒.*用"],
    ),
]

# 合併所有 31 個叢集（27 + 4 系統診斷）
ALL_CLUSTERS: List[ReflexCluster] = (
    TIER_A_CLUSTERS + TIER_B_CLUSTERS + TIER_C_CLUSTERS
    + TIER_D_CLUSTERS + TIER_E_CLUSTERS + TIER_F_CLUSTERS
)

# ANIMA 八原語 ← DNA27 叢集親和映射
CLUSTER_ANIMA_AFFINITY: Dict[str, str] = {
    # Tier A
    "RC-A1": "kan",   # 坎/共振 — 疲憊需要共振
    "RC-A2": "li",    # 離/覺察 — 情緒需要覺察
    "RC-A3": "gen",   # 艮/邊界 — 不可逆需要邊界
    "RC-A4": "gen",   # 艮/邊界 — 風險需要邊界
    "RC-A5": "zhen",  # 震/行動 — 緊急需要行動
    "RC-A6": "qian",  # 乾/身份 — 自我需要身份
    "RC-A7": "gen",   # 艮/邊界 — 安全需要邊界
    # Tier B
    "RC-B1": "qian",  # 乾/身份 — 主權需要身份
    "RC-B2": "dui",   # 兌/連結 — 依賴涉及連結
    "RC-B3": "zhen",  # 震/行動 — 逃避需要行動
    "RC-B4": "gen",   # 艮/邊界 — 後果涉及邊界
    "RC-B5": "qian",  # 乾/身份 — 主權回復需要身份
    "RC-B6": "xun",   # 巽/好奇 — 長期需要好奇探索
    # Tier C
    "RC-C1": "li",    # 離/覺察 — 幻覺需要覺察
    "RC-C2": "li",    # 離/覺察 — 敘事需要覺察
    "RC-C3": "xun",   # 巽/好奇 — 未知需要好奇
    "RC-C4": "xun",   # 巽/好奇 — 動機需要好奇探索
    "RC-C5": "li",    # 離/覺察 — 過度自信需要覺察
    # Tier D
    "RC-D1": "xun",   # 巽/好奇 — 實驗需要好奇
    "RC-D2": "zhen",  # 震/行動 — 犯錯預算需要行動
    "RC-D3": "kan",   # 坎/共振 — 低成功率需要共振接住
    "RC-D4": "gen",   # 艮/邊界 — 回滾需要邊界
    "RC-D5": "li",    # 離/覺察 — 影響範圍需要覺察
    # Tier E
    "RC-E1": "kun",   # 坤/記憶 — 長遠需要記憶
    "RC-E2": "kun",   # 坤/記憶 — 累積需要記憶
    "RC-E3": "kun",   # 坤/記憶 — 週期需要記憶
    "RC-E4": "kan",   # 坎/共振 — 節奏恢復需要共振
    # Tier F
    "RC-F1": "li",    # 離/覺察 — 系統健康需要覺察
    "RC-F2": "li",    # 離/覺察 — 工具狀態需要覺察
    "RC-F3": "li",    # 離/覺察 — 自我診斷需要覺察
    "RC-F4": "li",    # 離/覺察 — 運作回饋需要覺察
}


# ═══════════════════════════════════════════
# Detection Engine（純 CPU <20ms）
# ═══════════════════════════════════════════

def detect_all_clusters(message: str) -> Dict[str, float]:
    """偵測訊息中所有 27 個反射叢集.

    BDD Spec §2.3:
      - keyword hit: weight × 0.7
      - regex hit: weight × 1.0
      - 每叢集 score 上限 3.0
      - 只回傳 score > 0 的叢集

    Returns:
        {cluster_id: score}
    """
    if not message:
        return {}

    results: Dict[str, float] = {}
    msg_lower = message.lower()

    for cluster in ALL_CLUSTERS:
        score = 0.0

        # Keyword matching
        for kw in cluster.keywords:
            if kw.lower() in msg_lower:
                score += cluster.weight * KEYWORD_MULTIPLIER

        # Regex matching（v10.2: 用 msg_lower 避免大小寫不一致）
        for pattern in cluster._compiled:
            if pattern.search(msg_lower):
                score += cluster.weight * REGEX_MULTIPLIER

        # Per-cluster cap
        score = min(score, CLUSTER_MAX_SCORE)

        if score > 0:
            results[cluster.cluster_id] = round(score, 2)

    return results


def get_tier_scores(cluster_scores: Dict[str, float]) -> Dict[str, float]:
    """5 tier 聚合 — 每個 tier 取其所屬 clusters 的最高分.

    BDD Spec §2.3: tier aggregation = max of cluster scores.
    """
    tier_map: Dict[str, List[float]] = {
        "A": [], "B": [], "C": [], "D": [], "E": [], "F": [],
    }

    for cid, score in cluster_scores.items():
        tier = cid.split("-")[1][0]  # "RC-A1" → "A"
        if tier in tier_map:
            tier_map[tier].append(score)

    return {
        tier: round(max(scores), 2) if scores else 0.0
        for tier, scores in tier_map.items()
    }


# ═══════════════════════════════════════════
# Loop / Mode 選擇器
# ═══════════════════════════════════════════

def select_loop(
    tier_scores: Dict[str, float],
    cluster_scores: Dict[str, float],
    content_length: int = 0,
) -> str:
    """選擇迴圈類型.

    BDD Spec §9.2 — 優先順序（v9.0 更新）：
      1. A tier ≥ 0.5 → FAST_LOOP（安全煞車）
         ★ 但若同時 D/E tier 也高或訊息很長 → EXPLORATION_LOOP（安全+深度並行）
      2. RC-C3 or RC-D1 ≥ 0.5 → EXPLORATION_LOOP
      3. D or E tier ≥ 0.5 → SLOW_LOOP（演化/整合）
      4. B tier ≥ 0.5 → FAST_LOOP（主權保護）
      5. C tier ≥ 0.5 → EXPLORATION_LOOP
      6. 預設 → EXPLORATION_LOOP
    """
    T = LOOP_THRESHOLD

    # 1. Safety first — 但同時檢查是否為複雜請求
    if tier_scores.get("A", 0) >= T:
        # v9.0: 若同時有深度需求（D/E tier 高）或訊息很長，升級到 EXPLORATION_LOOP
        has_depth = (tier_scores.get("D", 0) >= T or tier_scores.get("E", 0) >= T)
        is_long = content_length > 200
        if has_depth or (is_long and tier_scores.get("A", 0) < 0.8):
            return "EXPLORATION_LOOP"  # 安全+深度並行
        return "FAST_LOOP"

    # 1.5. System diagnostics → EXPLORATION_LOOP（需要探索才能回答）
    if tier_scores.get("F", 0) >= T:
        return "EXPLORATION_LOOP"

    # 2. Exploration signals（v9.1: RC-D1 移除——D1 屬 D-tier，應走 SLOW_LOOP）
    if cluster_scores.get("RC-C3", 0) >= T:
        return "EXPLORATION_LOOP"

    # 3. Evolution / Integration
    if tier_scores.get("D", 0) >= T or tier_scores.get("E", 0) >= T:
        return "SLOW_LOOP"

    # 4. Sovereignty protection
    if tier_scores.get("B", 0) >= T:
        return "FAST_LOOP"

    # 5. Cognitive honesty
    if tier_scores.get("C", 0) >= T:
        return "EXPLORATION_LOOP"

    # 6. Default
    return "EXPLORATION_LOOP"


def select_mode(loop: str, tier_scores: Dict[str, float]) -> str:
    """選擇模式.

    BDD Spec §9.3:
      EVOLUTION_MODE 需同時滿足：
        1. loop == SLOW_LOOP
        2. D tier ≥ 0.5
        3. A tier < 0.3
      否則 → CIVIL_MODE
    """
    if (loop == "SLOW_LOOP"
            and tier_scores.get("D", 0) >= 0.5
            and tier_scores.get("A", 0) < 0.3):
        return "EVOLUTION_MODE"
    return "CIVIL_MODE"


# ═══════════════════════════════════════════
# 動態 max_push 計算
# ═══════════════════════════════════════════

def compute_max_push(message: str, tier_scores: Dict[str, float]) -> int:
    """依據訊息長度 + tier 分數計算結晶注入量.

    使用者規格：
      - 短問句（<20字）→ 5
      - 中等問題（20-300字）→ 10
      - 複雜問題（>300字）→ 30

    DNA27 調節：
      - FAST_LOOP (A tier) → 減半（快速回應，不需大量結晶）
      - SLOW_LOOP (D/E tier) → ×1.5（深度分析需要更多知識）
    """
    msg_len = len(message)

    # 基礎 max_push
    if msg_len < 20:
        base = 5
    elif msg_len <= 300:
        base = 10
    else:
        base = 30

    # DNA27 調節
    if tier_scores.get("A", 0) >= LOOP_THRESHOLD:
        # 安全觸發 → 快速回應，減少結晶
        base = max(3, base // 2)
    elif (tier_scores.get("D", 0) >= LOOP_THRESHOLD or
          tier_scores.get("E", 0) >= LOOP_THRESHOLD):
        # 演化/整合 → 深度分析，增加結晶
        base = min(50, int(base * 1.5))

    return base


# ═══════════════════════════════════════════
# LRU Route Cache
# ═══════════════════════════════════════════

_route_cache: OrderedDict = OrderedDict()


def _cache_key(
    message: str,
    history_len: int,
    prev_signals: Optional[List[Dict]] = None,
) -> str:
    """產生 LRU cache key.

    v10.4: 加入 prev_signals 差異化 — 同一句話在不同路由歷史下結果不同。
    """
    h = hashlib.md5(message.encode("utf-8")).hexdigest()[:16]
    ps_hash = ""
    if prev_signals:
        # 取上一輪的 top_clusters 前 3 名作為 cache 差異化
        last_top = prev_signals[-1].get("top_clusters", [])[:3]
        ps_hash = "_" + "_".join(str(c) for c in last_top)
    return f"{h}_{history_len}{ps_hash}"


# ═══════════════════════════════════════════
# v10.4 Route C: State-conditioned Routing
# ═══════════════════════════════════════════

def _apply_state_conditioning(
    cluster_scores: Dict[str, float],
    prev_signals: List[Dict],
) -> Dict[str, float]:
    """Route C: 根據前幾輪路由歷史，調整當前叢集分數.

    借鏡 SkillOrchestra (state-conditioned routing) + SOAR (production rules)。

    三大規則：
      1. Tier 遞進偵測：A/B→C→D 的自然遞進 → boost D-tier
         使用者從情緒(A)→認知(C)→行動(D) 是常見心理軌跡
      2. 情緒→行動轉向：前輪 A-tier 高 + 當輪有 D 信號 → boost D-tier
         解決 Round 3 退化問題
      3. 停滯偵測：連續 3 輪同 tier 主導 → 輕微壓制該 tier
         防止路由坍縮（routing collapse），A-tier 安全豁免

    Args:
        cluster_scores: 當前輪的叢集分數（會被修改）
        prev_signals: 前幾輪的 RoutingSignal.to_dict() 列表

    Returns:
        調整後的 cluster_scores
    """
    if not prev_signals:
        return cluster_scores

    scores = dict(cluster_scores)  # 不直接修改傳入的 dict

    def _get_primary_tier(signal_dict: Dict) -> str:
        ts = signal_dict.get("tier_scores", {})
        if not ts:
            return "C"
        return max(ts, key=ts.get)

    prev = prev_signals[-1]  # 上一輪
    prev_tier = _get_primary_tier(prev)

    # ── 規則 1: Tier 遞進偵測（A/B→C→D 自然遞進 → boost D）──
    if len(prev_signals) >= 2:
        prev2 = prev_signals[-2]
        prev2_tier = _get_primary_tier(prev2)
        if prev2_tier in ("A", "B") and prev_tier == "C":
            # 前前輪情緒/主權 → 前輪認知 → 當輪可能行動
            for d_cid in ("RC-D1", "RC-D4"):
                scores[d_cid] = min(
                    CLUSTER_MAX_SCORE, scores.get(d_cid, 0) + 0.4,
                )
            logger.debug(
                f"[DNA27] Route C rule 1: tier progression "
                f"{prev2_tier}→{prev_tier}→D, boosted D-tier +0.4"
            )

    # ── 規則 2: 情緒→行動轉向（前輪 A 高 + 當輪有 D 信號 → boost D）──
    prev_a = prev.get("tier_scores", {}).get("A", 0)
    curr_d_score = max(
        (scores.get(f"RC-D{i}", 0) for i in range(1, 6)),
        default=0,
    )
    if prev_a >= 0.5 and curr_d_score > 0:
        for d_cid in ("RC-D1", "RC-D4"):
            scores[d_cid] = min(
                CLUSTER_MAX_SCORE, scores.get(d_cid, 0) + 0.3,
            )
        logger.debug(
            f"[DNA27] Route C rule 2: emotion→action transition, "
            f"prev_A={prev_a:.1f}, boosted D-tier +0.3"
        )

    # ── 規則 3: 停滯偵測（連續 3 輪同 tier → 輕微壓制）──
    if len(prev_signals) >= 2:
        recent_primary_tiers = [_get_primary_tier(ps) for ps in prev_signals[-2:]]

        # 計算當前輪的 primary tier
        curr_tier_candidates: Dict[str, float] = {}
        for cid, sc in scores.items():
            if "-" in cid:
                t = cid.split("-")[1][0]
                curr_tier_candidates[t] = max(
                    curr_tier_candidates.get(t, 0), sc,
                )
        curr_primary = max(
            curr_tier_candidates,
            key=curr_tier_candidates.get,
            default="C",
        ) if curr_tier_candidates else "C"

        if (all(t == curr_primary for t in recent_primary_tiers)
                and curr_primary not in ("A",)):
            # 連續 3 輪同 tier → 輕微壓制（A-tier 安全不壓制）
            for cid in list(scores.keys()):
                if cid.startswith(f"RC-{curr_primary}"):
                    scores[cid] = max(0, scores[cid] - 0.2)
            logger.debug(
                f"[DNA27] Route C rule 3: stagnation detected, "
                f"tier {curr_primary} suppressed -0.2"
            )

    return scores


# ═══════════════════════════════════════════
# ReflexRouter — 主入口
# ═══════════════════════════════════════════

def _apply_primal_boost(
    cluster_scores: Dict[str, float],
    user_primals: Dict[str, int],
) -> Dict[str, float]:
    """v10.5: 根據使用者八原語驅力 boost 對應的 RC 叢集.

    映射表（只在原語 level > 50 時生效）：
      - curiosity   → RC-D1（實驗邊界）+0.3
      - emotion_pattern → RC-A1（能量耗竭）+0.2
      - aspiration  → RC-E2（選擇累積）+0.2
      - boundary    → RC-B2（依賴壓制）+0.2
      - action_power → RC-D2（犯錯預算）+0.2

    Args:
        cluster_scores: 當前叢集分數（不直接修改）
        user_primals: {primal_key: level(0-100)}

    Returns:
        調整後的 cluster_scores
    """
    if not user_primals:
        return cluster_scores

    scores = dict(cluster_scores)

    PRIMAL_RC_MAP = {
        "curiosity":       ("RC-D1", 0.3),
        "emotion_pattern": ("RC-A1", 0.2),
        "aspiration":      ("RC-E2", 0.2),
        "boundary":        ("RC-B2", 0.2),
        "action_power":    ("RC-D2", 0.2),
    }

    for primal_key, (rc_id, boost) in PRIMAL_RC_MAP.items():
        level = user_primals.get(primal_key, 0)
        if level > 50:
            scores[rc_id] = min(
                CLUSTER_MAX_SCORE, scores.get(rc_id, 0) + boost,
            )
            logger.debug(
                f"[DNA27] primal boost: {primal_key}={level} → {rc_id} +{boost}"
            )

    return scores


def route(
    message: str,
    history_len: int = 0,
    workspace: str = None,
    prev_signals: Optional[List[Dict]] = None,
    user_primals: Optional[Dict[str, int]] = None,
) -> RoutingSignal:
    """DNA27 反射路由器 — 產生 RoutingSignal.

    v10.4 端到端資料流（三路升級）：
      1. LRU Cache Check → 命中跳過全部
      2. detect_all_clusters() → 27 clusters (keyword/regex)
      2.5. ★ Route A: semantic_cluster_detect() → 語義主路徑
      2.7. Action-intent boost (v10.3)
      2.8. ★ Route C: _apply_state_conditioning() → 跨輪路由記憶
      3. get_tier_scores() → 5 tier scores
      4. select_loop/mode
      5. compute_max_push
      6. 產生 RoutingSignal (frozen)

    Args:
        message: 使用者訊息
        history_len: 對話歷史長度
        workspace: 資料目錄（用於 Qdrant 向量語義偵測）
        prev_signals: ★ v10.4 Route C — 前幾輪的 RoutingSignal.to_dict() 列表
        user_primals: ★ v10.5 — {primal_key: level(0-100)} 使用者八原語

    Returns:
        RoutingSignal（不可變）
    """
    global _route_cache

    t0 = time.time()

    # 1. LRU Cache Check — v10.4: cache key 加入 prev_signals 差異化
    ck = _cache_key(message, history_len, prev_signals)
    if ck in _route_cache:
        _route_cache.move_to_end(ck)
        cached = _route_cache[ck]
        logger.debug(f"[DNA27] LRU cache hit: {ck}")
        return cached

    # 2. Cluster Detection (regex/keyword) — 保留為 hard override
    cluster_scores = detect_all_clusters(message)

    # 2.5. ★ v10.4 Route A: Semantic Cluster Detect（語義主路徑）
    # 取代舊的 semantic_cluster_boost()，改用多文檔 utterance 匹配
    if workspace:
        try:
            semantic_scores = semantic_cluster_detect(
                message, workspace, limit=8, score_threshold=0.35,
            )
            for cid, sem_score in semantic_scores.items():
                if cid in cluster_scores:
                    # keyword/regex 已有分數 → 取兩者最高（hard override）
                    cluster_scores[cid] = max(cluster_scores[cid], sem_score)
                else:
                    # 語義偵測到但 keyword/regex 沒抓到 → 新增
                    cluster_scores[cid] = sem_score
            if semantic_scores:
                logger.debug(
                    f"[DNA27] Route A semantic detect: {semantic_scores}"
                )
        except Exception as e:
            logger.debug(f"[DNA27] semantic_cluster_detect 失敗（降級到 keyword-only）: {e}")

    # 2.7 v10.3 Fix: Action-intent boost — 偵測行動意圖詞，boost D-tier
    # 解決 Round 3 退化：使用者從情緒/探索轉向行動時，D-tier 應自動升權
    _ACTION_INTENT_PATTERNS = [
        r"我想試", r"有沒有.*方法", r"怎麼做", r"怎麼.*開始",
        r"教我", r"可以怎麼", r"具體.*怎", r"第一步",
        r"如何.*做", r"給我.*建議", r"幫我.*想",
    ]
    msg_lower = message.lower()
    action_intent_count = 0
    for pat in _ACTION_INTENT_PATTERNS:
        if re.search(pat, msg_lower):
            action_intent_count += 1
    if action_intent_count > 0:
        # Boost RC-D1 和 RC-D4（實驗 + 退路）
        d_boost = min(0.6, action_intent_count * 0.3)
        for d_cid in ("RC-D1", "RC-D4"):
            if d_cid in cluster_scores:
                cluster_scores[d_cid] = min(
                    CLUSTER_MAX_SCORE, cluster_scores[d_cid] + d_boost,
                )
            else:
                cluster_scores[d_cid] = d_boost
        logger.debug(
            f"[DNA27] action-intent boost: {action_intent_count} matches, "
            f"D-boost={d_boost:.1f}"
        )

    # 2.8 ★ v10.4 Route C: State-conditioned routing — 跨輪路由記憶
    if prev_signals:
        try:
            cluster_scores = _apply_state_conditioning(cluster_scores, prev_signals)
        except Exception as e:
            logger.debug(f"[DNA27] state_conditioning 失敗（降級）: {e}")

    # 2.9 ★ v10.5: 八原語驅力 boost
    if user_primals:
        try:
            cluster_scores = _apply_primal_boost(cluster_scores, user_primals)
        except Exception as e:
            logger.debug(f"[DNA27] primal_boost 失敗（降級）: {e}")

    # 3. Tier Aggregation
    tier_scores = get_tier_scores(cluster_scores)

    # 4. Loop & Mode Selection (v9.0: 傳入訊息長度做複雜度判斷)
    loop = select_loop(tier_scores, cluster_scores, content_length=len(message))
    mode = select_mode(loop, tier_scores)

    # 5. Dynamic max_push
    max_push = compute_max_push(message, tier_scores)

    # 6. Top clusters (sorted by score desc, max 5)
    sorted_clusters = sorted(
        cluster_scores.items(), key=lambda x: x[1], reverse=True,
    )
    # v10.2 Fix: 從 5→8，讓更多 RC 叢集被 SkillRouter 看見
    top_clusters = tuple(cid for cid, _ in sorted_clusters[:8])

    # 7. Confidence
    active_tiers = sum(1 for v in tier_scores.values() if v > 0)
    confidence = min(1.0, active_tiers * 0.25)

    elapsed_ms = (time.time() - t0) * 1000

    signal = RoutingSignal(
        tier_scores=tier_scores,
        top_clusters=top_clusters,
        loop=loop,
        mode=mode,
        confidence=confidence,
        raw_message_len=len(message),
        max_crystal_push=max_push,
        cluster_scores=dict(sorted_clusters[:8]),  # v9.1: 保留 top 8 叢集分數
        route_time_ms=round(elapsed_ms, 2),
    )

    # 8. Cache store
    _route_cache[ck] = signal
    while len(_route_cache) > _ROUTE_CACHE_SIZE:
        _route_cache.popitem(last=False)

    logger.info(
        f"[DNA27] route: loop={loop}, mode={mode}, "
        f"tiers={tier_scores}, max_push={max_push}, "
        f"top={top_clusters[:3]}, time={elapsed_ms:.1f}ms"
    )

    return signal


def reset_cache() -> None:
    """重置 LRU 快取（僅供測試用）."""
    global _route_cache
    _route_cache.clear()


# ═══════════════════════════════════════════
# Safety Context Builder（向後相容）
# ═══════════════════════════════════════════

def build_routing_context(signal: RoutingSignal) -> str:
    """依據 RoutingSignal 產生系統提示安全/路由上下文.

    BDD Spec §4.4 Stage 2: routing_inject — 僅注入非零 tier。
    """
    if signal.max_tier_score < LOOP_THRESHOLD:
        return ""

    # 建構路由指引
    text = "## 路由分析\n\n"
    text += f"- 迴圈：{signal.loop}\n"
    text += f"- 模式：{signal.mode}\n"
    text += f"- 活躍 Tier："

    active = [
        f"{t}={s:.1f}" for t, s in signal.tier_scores.items() if s > 0
    ]
    text += ", ".join(active) + "\n"

    if signal.top_clusters:
        cluster_names = {c.cluster_id: c.name for c in ALL_CLUSTERS}
        names = [cluster_names.get(cid, cid) for cid in signal.top_clusters[:5]]
        text += f"- 觸發叢集：{', '.join(names)}\n"

    text += "\n"

    # Tier-specific guidelines
    ts = signal.tier_scores

    if ts.get("A", 0) >= LOOP_THRESHOLD:
        text += _build_tier_a_guidance(signal)

    if ts.get("B", 0) >= LOOP_THRESHOLD:
        text += (
            "### Tier B 主權保護\n"
            "- 不替對方做決定，引導對方自己思考\n"
            "- 提出選項和各自代價，讓對方選擇\n"
            "- 避免產生依賴感\n\n"
        )

    if ts.get("C", 0) >= LOOP_THRESHOLD:
        text += (
            "### Tier C 認知誠實\n"
            "- 對不確定的事物坦承不知道\n"
            "- 質疑過度自信的結論\n"
            "- 提供多元觀點，避免單一敘事\n\n"
        )

    if ts.get("D", 0) >= LOOP_THRESHOLD:
        text += (
            "### Tier D 實驗演化\n"
            "- 鼓勵可控犯錯，設定回滾機制\n"
            "- 提供明確的實驗邊界和止損點\n"
            "- 強調「最小可行實驗」原則\n\n"
        )

    if ts.get("E", 0) >= LOOP_THRESHOLD:
        text += (
            "### Tier E 整合節律\n"
            "- 拉長時間軸，看長期影響\n"
            "- 辨識循環模式，避免重蹈覆轍\n"
            "- 在累積中找到意義\n\n"
        )

    if ts.get("F", 0) >= LOOP_THRESHOLD:
        text += (
            "### Tier F 系統診斷\n"
            "- 偵測到系統自身狀態詢問，誠實報告當前運作狀況\n"
            "- 主動檢查相關子系統（工具、排程、心跳等）的健康狀態\n"
            "- 如有問題，報告問題現象和可能原因，不隱瞞\n\n"
        )

    # 高強度時 fast_loop 指令
    if ts.get("A", 0) >= 1.5:
        text += (
            "\n⚠️ 高強度安全訊號 — 強制切換 FAST_LOOP：\n"
            "- 回覆控制在 200 字以內\n"
            "- 不展開多方案推演\n"
            "- 先接住 → 一個最小下一步\n"
        )

    return text


def _build_tier_a_guidance(signal: RoutingSignal) -> str:
    """Tier A 安全指引（向後相容 safety_clusters.py 的 build_safety_context）."""
    text = "### Tier A 安全感知\n\n"
    text += "偵測到以下安全訊號，請調整回應方式：\n\n"

    cluster_names = {c.cluster_id: c.name for c in ALL_CLUSTERS}
    guidelines = {
        "energy_depletion": "先接住疲憊感，給最小可行的下一步，禁止長篇推演",
        "emotional_overheating": "先用 1-3 句接住情緒，不急著分析，等對方準備好再展開",
        "irreversible_interception": "主動提出代價和後果，建議先暫停 24 小時，不替對方做決定",
        "risk_overload": "同框呈現風險和機會，提供 Plan B，避免助長衝動決策",
        "emergency_downgrade": "切換到 fast_loop，只給止血方案，不展開完整分析",
        "self_dissolution": "先確認對方的存在感和價值，避免說教，用提問幫助釐清",
        "safety_first": "優先處理安全需求，再談其他",
    }

    for cid in signal.top_clusters:
        name = cluster_names.get(cid, cid)
        if name in guidelines:
            text += f"- {name}：{guidelines[name]}\n"

    return text + "\n"


# ═══════════════════════════════════════════
# DNA27 → Qdrant 向量索引
# ═══════════════════════════════════════════

def index_reflex_patterns_to_qdrant(workspace: str) -> int:
    """將 27 個反射叢集的語義模式索引到 Qdrant dna27 collection.

    v10.4 Route A 升級：每叢集索引 15 條範例語句（取代舊的單筆拼接）。
    這讓向量資料庫能透過多樣化的語句範例「理解」DNA27 的語義，
    大幅提升語義匹配準確率。

    Returns:
        成功索引的語句數量
    """
    try:
        from museon.vector.vector_bridge import VectorBridge
        vb = VectorBridge(workspace=workspace)
        if not vb.is_available():
            logger.warning("[DNA27] Qdrant 不可用，跳過索引")
            return 0

        # v10.4: 載入範例語句庫
        try:
            from museon.agent.rc_utterances import RC_UTTERANCES
        except ImportError:
            RC_UTTERANCES = {}
            logger.warning("[DNA27] rc_utterances 載入失敗，回退到舊索引模式")

        tier_desc = {
            "A": "安全與穩定煞車系統",
            "B": "主權與責任方向盤保護",
            "C": "認知誠實反自我欺騙",
            "D": "演化與實驗可控犯錯",
            "E": "整合與節律慢層啟動",
        }

        indexed = 0
        for cluster in ALL_CLUSTERS:
            base_metadata = {
                "cluster_id": cluster.cluster_id,
                "tier": cluster.tier,
                "name": cluster.name,
                "weight": cluster.weight,
                "anima_element": CLUSTER_ANIMA_AFFINITY.get(
                    cluster.cluster_id, ""
                ),
            }

            # v10.4: 取得範例語句（有 → 多文檔索引；無 → 回退舊模式）
            utterances = RC_UTTERANCES.get(cluster.cluster_id, [])
            if not utterances:
                # 回退：用舊邏輯（keywords 拼接）
                semantic_text = (
                    f"{cluster.name} {tier_desc.get(cluster.tier, '')} "
                    f"{' '.join(cluster.keywords)}"
                )
                utterances = [semantic_text]

            for idx, utt in enumerate(utterances):
                doc_id = f"{cluster.cluster_id}__utt_{idx}"
                metadata = {**base_metadata, "utterance_index": idx}
                success = vb.index(
                    collection="dna27",
                    doc_id=doc_id,
                    text=utt,
                    metadata=metadata,
                )
                if success:
                    indexed += 1

        logger.info(
            f"[DNA27] 索引完成: {indexed} 筆語句 "
            f"({len(ALL_CLUSTERS)} 叢集)"
        )
        return indexed

    except Exception as e:
        logger.warning(f"[DNA27] 索引失敗: {e}")
        return 0


def semantic_cluster_boost(
    query: str,
    workspace: str,
    limit: int = 3,
) -> Dict[str, float]:
    """用向量搜尋找出語義最接近的 DNA27 叢集，提供額外 boost.

    這讓 DNA27 不只靠關鍵字/regex 命中，也能語義理解。
    ★ v10.4: 此函式保留為向後相容，新路徑請用 semantic_cluster_detect()。

    Returns:
        {cluster_id: boost_score}
    """
    try:
        from museon.vector.vector_bridge import VectorBridge
        vb = VectorBridge(workspace=workspace)
        if not vb.is_available():
            return {}

        hits = vb.search("dna27", query, limit=limit, score_threshold=0.4)
        return {
            # v10.2 Fix: 從 ×0.5→×1.0，舊值讓語義只佔 keyword 的 17%
            hit["id"]: round(hit["score"] * 1.0, 2)
            for hit in hits
        }
    except Exception:
        return {}


def semantic_cluster_detect(
    query: str,
    workspace: str,
    limit: int = 8,
    score_threshold: float = 0.35,
) -> Dict[str, float]:
    """v10.4 Route A: 語義主路徑 — 用 embedding 匹配 RC 叢集.

    與 semantic_cluster_boost 的差異：
      - 搜尋更多結果（limit=8 vs 3）
      - 更低的門檻（0.35 vs 0.4）
      - 同一 cluster 多個 utterance 命中時做聚合（MoE-inspired aggregation）
      - 回傳的 score 更高（作為主路徑而非補充）

    多文檔索引後（每叢集 15 條範例語句），同一 cluster 的多個
    utterance 可能同時命中。聚合策略：最高分 + 次分 ×0.3 衰減加成。

    Returns:
        {cluster_id: aggregated_score}
    """
    try:
        from museon.vector.vector_bridge import VectorBridge
        vb = VectorBridge(workspace=workspace)
        if not vb.is_available():
            return {}

        hits = vb.search("dna27", query, limit=limit, score_threshold=score_threshold)
        if not hits:
            return {}

        # 按 cluster_id 聚合（多 utterance 命中同一 cluster）
        cluster_hits: Dict[str, List[float]] = {}
        for hit in hits:
            # v10.4 多文檔格式：doc_id = "RC-A1__utt_3"
            # metadata 中有 cluster_id，優先使用
            metadata = hit.get("metadata", {})
            cid = metadata.get("cluster_id", "")
            if not cid:
                # 回退：從 doc_id 解析
                doc_id = hit.get("id", "")
                cid = doc_id.split("__")[0] if "__" in doc_id else doc_id
            if cid:
                cluster_hits.setdefault(cid, []).append(hit["score"])

        # MoE-inspired aggregation: 主分 + 次分 × 0.3 衰減加成
        result: Dict[str, float] = {}
        for cid, scores in cluster_hits.items():
            scores.sort(reverse=True)
            agg = scores[0]
            for s in scores[1:]:
                agg += s * 0.3  # 多重命中加成（衰減）
            result[cid] = round(min(CLUSTER_MAX_SCORE, agg), 2)

        return result

    except Exception as e:
        logger.debug(f"[DNA27] semantic_cluster_detect 失敗（降級）: {e}")
        return {}
