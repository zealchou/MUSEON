"""Knowledge Lattice -- 知識晶格結晶化引擎.

將對話中驗證過的洞見、失敗教訓、成功模式
萃取為可索引、可連結、可演化的知識結晶（Crystal）
形成跨對話持續成長的智慧資產網路。

核心命題：知識量本身無用，知識的結構、連結、可用性才是關鍵。

設計原則：
- Crystal Protocol: 四類結晶 x GEO 四層 x 再結晶演算法
- Crystal Chain Protocol: CUID x DAG x 共振指數
- 安全護欄：假設/證據/限制三元組，矛盾保留不消除
"""

import json
import logging
import math
import threading
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from museon.core.data_bus import DataContract, StoreSpec, StoreEngine, TTLTier

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 常數定義
# ═══════════════════════════════════════════

# 結晶類型
CRYSTAL_TYPE_INSIGHT = "Insight"
CRYSTAL_TYPE_PATTERN = "Pattern"
CRYSTAL_TYPE_LESSON = "Lesson"
CRYSTAL_TYPE_HYPOTHESIS = "Hypothesis"

CRYSTAL_TYPES = [
    CRYSTAL_TYPE_INSIGHT,
    CRYSTAL_TYPE_PATTERN,
    CRYSTAL_TYPE_LESSON,
    CRYSTAL_TYPE_HYPOTHESIS,
]

# CUID 類型縮寫映射
CUID_TYPE_MAP = {
    CRYSTAL_TYPE_INSIGHT: "INS",
    CRYSTAL_TYPE_PATTERN: "PAT",
    CRYSTAL_TYPE_LESSON: "LES",
    CRYSTAL_TYPE_HYPOTHESIS: "HYP",
}

# 反向映射：縮寫 -> 類型
CUID_REVERSE_MAP = {v: k for k, v in CUID_TYPE_MAP.items()}

# 連結類型
LINK_TYPES = ["supports", "contradicts", "extends", "derived_from", "related"]

# 驗證等級
VERIFICATION_LEVELS = ["hypothetical", "observed", "tested", "proven"]

# 共振指數閾值
RI_CORE_THRESHOLD = 0.7       # 核心知識
RI_ACTIVE_THRESHOLD = 0.2     # 活躍知識
RI_ARCHIVE_THRESHOLD = 0.05   # 歸檔閾值

# 時間窗口
HYPOTHESIS_WINDOW_DAYS = 30   # Hypothesis 驗證窗口
ARCHIVE_STALE_DAYS = 90       # 歸檔天數閾值

# 再結晶參數
SIMILARITY_MERGE_THRESHOLD = 0.70  # 70% 相似度合併閾值
HYPOTHESIS_UPGRADE_COUNT = 3       # 升級所需成功次數
INSIGHT_DOWNGRADE_COUNT = 2        # 降級所需反證次數
FRAGMENT_CONSOLIDATION_COUNT = 5   # 碎片整合閾值
RECRYSTALLIZE_INTERVAL = 20        # 每 N 顆新結晶觸發輕量再結晶

# 自動召回
MAX_PROACTIVE_PUSH = 2  # 每次對話最多主動推送次數


# ═══════════════════════════════════════════
# 資料結構
# ═══════════════════════════════════════════

@dataclass
class Crystal:
    """知識結晶 -- 結構化的知識單元.

    每顆結晶包含 GEO 四層結構、假設/證據/限制三元組，
    以及共振指數等元資料。
    """

    # 唯一識別碼（KL-{INS|PAT|LES|HYP}-{0001}）
    cuid: str

    # 結晶類型：Insight / Pattern / Lesson / Hypothesis
    crystal_type: str

    # ── GEO 四層結構 ──
    # G1: 一句話核心摘要（<30 字，電梯測試）
    g1_summary: str
    # G2: MECE 拆解（互斥完備，冗餘率 < 10%）
    g2_structure: List[str]
    # G3: Root Inquiry（問題背後的問題）
    g3_root_inquiry: str
    # G4: 洞見 + 限制條件
    g4_insights: List[str]

    # ── 假設/證據/限制三元組 ──
    assumption: str    # 此結晶的基本假設
    evidence: str      # 支持結論的具體證據
    limitation: str    # 此結論失效的條件

    # ── 驗證等級 ──
    # hypothetical / observed / tested / proven
    verification_level: str = "hypothetical"

    # ── 時間戳記 ──
    created_at: str = ""
    updated_at: str = ""

    # ── 狀態 ──
    archived: bool = False

    # ── 共振指數相關 ──
    ri_score: float = 0.0
    reference_count: int = 0
    last_referenced: str = ""

    # ── 分類與領域 ──
    tags: List[str] = field(default_factory=list)
    domain: str = ""

    # ── 額外元資料 ──
    # Hypothesis 成功應用次數（升級用）
    success_count: int = 0
    # Insight 反證次數（降級用）
    counter_evidence_count: int = 0
    # 來源上下文
    source_context: str = ""
    # 狀態標記（disputed, merged, pending_recrystallization, quarantined, provisional 等）
    status: str = "active"

    # ── 外向型進化欄位 ──
    # 來源追溯（outward_self / outward_service / 空=內部產生）
    origin: str = ""

    def __post_init__(self) -> None:
        """初始化預設時間戳記."""
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        if not self.last_referenced:
            self.last_referenced = now

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Crystal":
        """從字典反序列化.

        Args:
            data: 結晶的字典表示

        Returns:
            Crystal 實例

        Raises:
            ValueError: 缺少必要欄位
        """
        if not isinstance(data, dict):
            raise ValueError(f"Crystal.from_dict: 預期 dict，收到 {type(data).__name__}")

        # 必要欄位檢查
        _REQUIRED = ("cuid", "crystal_type", "g1_summary")
        missing = [f for f in _REQUIRED if f not in data or not data[f]]
        if missing:
            raise ValueError(
                f"Crystal.from_dict: 缺少必要欄位 {missing}"
            )

        # 處理可能缺少的欄位（向後相容）
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}

        # 確保 list 類型欄位不為 None
        for list_field in ("g2_structure", "g4_insights", "tags"):
            if list_field in filtered and filtered[list_field] is None:
                filtered[list_field] = []

        return cls(**filtered)


@dataclass
class CrystalLink:
    """結晶之間的有向連結.

    連結類型：supports, contradicts, extends, derived_from, related
    """

    from_cuid: str         # 起點結晶 CUID
    to_cuid: str           # 終點結晶 CUID
    link_type: str         # 連結類型
    confidence: float = 1.0  # 連結信心度 (0-1)
    created_at: str = ""

    def __post_init__(self) -> None:
        """初始化預設時間戳記."""
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrystalLink":
        """從字典反序列化.

        Args:
            data: 連結的字典表示

        Returns:
            CrystalLink 實例
        """
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


# ═══════════════════════════════════════════
# Crystal DAG -- 知識的有向無環圖
# ═══════════════════════════════════════════

class CrystalDAG:
    """管理結晶之間的有向無環圖（DAG）.

    功能：
    - 新增/移除連結
    - 環路偵測（DFS）
    - 2-hop 可達性查詢
    - 連結密度計算
    """

    def __init__(self) -> None:
        """初始化空的 DAG."""
        # 鄰接表：from_cuid -> [(to_cuid, link)]
        self._adjacency: Dict[str, List[CrystalLink]] = defaultdict(list)
        # 反向鄰接表（用於反向查詢）：to_cuid -> [(from_cuid, link)]
        self._reverse_adjacency: Dict[str, List[CrystalLink]] = defaultdict(list)
        # 所有節點集合
        self._nodes: Set[str] = set()
        # 執行緒鎖
        self._lock = threading.Lock()

    def add_node(self, cuid: str) -> None:
        """新增節點（結晶）到 DAG.

        Args:
            cuid: 結晶的唯一識別碼
        """
        with self._lock:
            self._nodes.add(cuid)

    def add_link(self, link: CrystalLink) -> bool:
        """新增有向邊，若會形成環路則拒絕.

        使用 DFS 偵測環路：在新增邊之前，檢查從 to_cuid 是否可達 from_cuid。
        若可達，代表新增此邊會形成環路。

        Args:
            link: 要新增的連結

        Returns:
            True 表示成功新增，False 表示會形成環路而拒絕
        """
        with self._lock:
            # 自環檢查
            if link.from_cuid == link.to_cuid:
                logger.warning(
                    f"拒絕自環連結: {link.from_cuid} -> {link.to_cuid}"
                )
                return False

            # 環路偵測：檢查從 to_cuid 出發是否可達 from_cuid
            if self._would_create_cycle(link.from_cuid, link.to_cuid):
                logger.warning(
                    f"拒絕環路連結: {link.from_cuid} -> {link.to_cuid}"
                )
                return False

            # 新增連結
            self._adjacency[link.from_cuid].append(link)
            self._reverse_adjacency[link.to_cuid].append(link)
            self._nodes.add(link.from_cuid)
            self._nodes.add(link.to_cuid)
            return True

    def _would_create_cycle(self, from_cuid: str, to_cuid: str) -> bool:
        """使用 DFS 檢查新增 from_cuid -> to_cuid 是否會造成環路.

        策略：從 to_cuid 出發沿 DAG 方向走，看能否到達 from_cuid。
        若能到達，代表新增此邊會形成環路。

        Args:
            from_cuid: 邊的起點
            to_cuid: 邊的終點

        Returns:
            True 表示會形成環路
        """
        visited: Set[str] = set()
        stack = [to_cuid]

        while stack:
            current = stack.pop()
            if current == from_cuid:
                return True
            if current in visited:
                continue
            visited.add(current)
            # 沿著出邊繼續搜尋
            for link in self._adjacency.get(current, []):
                if link.to_cuid not in visited:
                    stack.append(link.to_cuid)

        return False

    def remove_link(self, from_cuid: str, to_cuid: str) -> bool:
        """移除指定的有向邊.

        Args:
            from_cuid: 起點 CUID
            to_cuid: 終點 CUID

        Returns:
            True 表示成功移除
        """
        with self._lock:
            original_len = len(self._adjacency.get(from_cuid, []))
            self._adjacency[from_cuid] = [
                link for link in self._adjacency.get(from_cuid, [])
                if link.to_cuid != to_cuid
            ]
            self._reverse_adjacency[to_cuid] = [
                link for link in self._reverse_adjacency.get(to_cuid, [])
                if link.from_cuid != from_cuid
            ]
            return len(self._adjacency.get(from_cuid, [])) < original_len

    def get_neighbors(self, cuid: str, hops: int = 1) -> List[str]:
        """取得指定 hop 數內的所有相關結晶（雙向）.

        Args:
            cuid: 起點 CUID
            hops: 最大跳數（預設 1）

        Returns:
            相關結晶的 CUID 列表
        """
        visited: Set[str] = set()
        current_level = {cuid}

        for _ in range(hops):
            next_level: Set[str] = set()
            for node in current_level:
                # 正向鄰居
                for link in self._adjacency.get(node, []):
                    if link.to_cuid not in visited and link.to_cuid != cuid:
                        next_level.add(link.to_cuid)
                # 反向鄰居
                for link in self._reverse_adjacency.get(node, []):
                    if link.from_cuid not in visited and link.from_cuid != cuid:
                        next_level.add(link.from_cuid)
            visited.update(current_level)
            current_level = next_level

        visited.update(current_level)
        visited.discard(cuid)
        return list(visited)

    def get_outgoing_links(self, cuid: str) -> List[CrystalLink]:
        """取得指定結晶的所有出邊.

        Args:
            cuid: 結晶 CUID

        Returns:
            出邊列表
        """
        return list(self._adjacency.get(cuid, []))

    def get_incoming_links(self, cuid: str) -> List[CrystalLink]:
        """取得指定結晶的所有入邊.

        Args:
            cuid: 結晶 CUID

        Returns:
            入邊列表
        """
        return list(self._reverse_adjacency.get(cuid, []))

    def get_links_by_type(self, cuid: str, link_type: str) -> List[CrystalLink]:
        """取得指定類型的所有連結（出邊 + 入邊）.

        Args:
            cuid: 結晶 CUID
            link_type: 連結類型

        Returns:
            符合類型的連結列表
        """
        links = []
        for link in self._adjacency.get(cuid, []):
            if link.link_type == link_type:
                links.append(link)
        for link in self._reverse_adjacency.get(cuid, []):
            if link.link_type == link_type:
                links.append(link)
        return links

    def get_all_links(self) -> List[CrystalLink]:
        """取得 DAG 中的所有連結.

        Returns:
            所有連結的列表
        """
        all_links: List[CrystalLink] = []
        for links in self._adjacency.values():
            all_links.extend(links)
        return all_links

    def get_link_density(self) -> float:
        """計算連結密度 = 邊數 / (節點數 * (節點數 - 1)).

        Returns:
            連結密度 (0-1)
        """
        node_count = len(self._nodes)
        if node_count <= 1:
            return 0.0
        edge_count = sum(len(links) for links in self._adjacency.values())
        max_edges = node_count * (node_count - 1)
        return edge_count / max_edges

    def get_isolated_nodes(self, all_cuids: List[str]) -> List[str]:
        """找出零連結的孤立結晶.

        Args:
            all_cuids: 所有結晶的 CUID 列表

        Returns:
            孤立結晶的 CUID 列表
        """
        isolated = []
        for cuid in all_cuids:
            outgoing = len(self._adjacency.get(cuid, []))
            incoming = len(self._reverse_adjacency.get(cuid, []))
            if outgoing == 0 and incoming == 0:
                isolated.append(cuid)
        return isolated

    def load_links(self, links: List[CrystalLink]) -> None:
        """從列表載入所有連結（用於持久化恢復）.

        Args:
            links: 連結列表
        """
        with self._lock:
            self._adjacency.clear()
            self._reverse_adjacency.clear()
            for link in links:
                self._adjacency[link.from_cuid].append(link)
                self._reverse_adjacency[link.to_cuid].append(link)
                self._nodes.add(link.from_cuid)
                self._nodes.add(link.to_cuid)


# ═══════════════════════════════════════════
# 共振指數計算器
# ═══════════════════════════════════════════

class ResonanceCalculator:
    """計算結晶的共振指數（Resonance Index）.

    公式：RI = (0.3 x Freq + 0.4 x Depth + 0.3 x Quality) x exp(-0.03 x days)

    其中：
    - Freq: 使用頻率（正規化 0-1）
    - Depth: 分析深度（基於 GEO 四層填寫完整度，0-1）
    - Quality: 平均品質分數（0-1）
    - days: 距離最後引用的天數
    - exp(-0.03 x days): 衰減因子
    """

    # 頻率正規化的最大參考次數（超過此值視為 1.0）
    MAX_REFERENCE_COUNT: int = 50

    @staticmethod
    def calculate(crystal: Crystal) -> float:
        """計算單顆結晶的共振指數.

        Args:
            crystal: 要計算的結晶

        Returns:
            共振指數 (0-1 的浮點數)
        """
        freq = ResonanceCalculator._calc_freq(crystal)
        depth = ResonanceCalculator._calc_depth(crystal)
        quality = ResonanceCalculator._calc_quality(crystal)
        days = ResonanceCalculator._calc_days_since_last_ref(crystal)

        # RI = (0.3 x Freq + 0.4 x Depth + 0.3 x Quality) x exp(-0.03 x days)
        base_score = 0.3 * freq + 0.4 * depth + 0.3 * quality
        decay = math.exp(-0.03 * days)
        ri = base_score * decay

        return round(ri, 4)

    @staticmethod
    def _calc_freq(crystal: Crystal) -> float:
        """計算使用頻率（正規化 0-1）.

        Args:
            crystal: 結晶

        Returns:
            正規化後的頻率值
        """
        return min(
            crystal.reference_count / ResonanceCalculator.MAX_REFERENCE_COUNT,
            1.0,
        )

    @staticmethod
    def _calc_depth(crystal: Crystal) -> float:
        """計算分析深度（基於 GEO 四層填寫完整度）.

        每層各佔 0.25，全部填寫得 1.0。

        Args:
            crystal: 結晶

        Returns:
            深度分數 (0-1)
        """
        score = 0.0

        # G1: 有摘要且 < 30 字
        if crystal.g1_summary and len(crystal.g1_summary) > 0:
            score += 0.25

        # G2: 有 MECE 拆解（至少 2 項）
        if crystal.g2_structure and len(crystal.g2_structure) >= 2:
            score += 0.25

        # G3: 有 Root Inquiry
        if crystal.g3_root_inquiry and len(crystal.g3_root_inquiry) > 0:
            score += 0.25

        # G4: 有洞見（至少 1 項）
        if crystal.g4_insights and len(crystal.g4_insights) >= 1:
            score += 0.25

        return score

    @staticmethod
    def _calc_quality(crystal: Crystal) -> float:
        """計算結晶品質分數（基於驗證等級和結構完整度）.

        Args:
            crystal: 結晶

        Returns:
            品質分數 (0-1)
        """
        # 基於驗證等級
        level_scores = {
            "hypothetical": 0.2,
            "observed": 0.5,
            "tested": 0.8,
            "proven": 1.0,
        }
        level_score = level_scores.get(crystal.verification_level, 0.2)

        # 三元組完整度加分
        triplet_score = 0.0
        if crystal.assumption:
            triplet_score += 0.33
        if crystal.evidence:
            triplet_score += 0.34
        if crystal.limitation:
            triplet_score += 0.33

        # 綜合：70% 驗證等級 + 30% 三元組完整度
        return 0.7 * level_score + 0.3 * triplet_score

    @staticmethod
    def _calc_days_since_last_ref(crystal: Crystal) -> float:
        """計算距離最後引用的天數.

        Args:
            crystal: 結晶

        Returns:
            天數（浮點數）
        """
        try:
            last_ref = datetime.fromisoformat(crystal.last_referenced)
            delta = datetime.now() - last_ref
            return max(delta.total_seconds() / 86400.0, 0.0)
        except (ValueError, TypeError):
            return 0.0


# ═══════════════════════════════════════════
# 結晶化流程器
# ═══════════════════════════════════════════

class Crystallizer:
    """結晶化五步驟流程.

    1. capture: 原始捕獲（記錄觸發情境）
    2. refine: 結構精煉（填寫 GEO 四層）
    3. link_discovery: 連結發現（掃描現有結晶網路）
    4. quality_check: 品質閘檢查（四道 Gate）
    5. register: 註冊入庫（分配 CUID，加入晶格）
    """

    def __init__(
        self,
        crystals: Dict[str, Crystal],
        dag: CrystalDAG,
    ) -> None:
        """初始化結晶化流程器.

        Args:
            crystals: 現有結晶字典（cuid -> Crystal）
            dag: 結晶 DAG
        """
        self._crystals = crystals
        self._dag = dag

    def capture(
        self,
        raw_material: str,
        source_context: str = "",
        crystal_type: str = CRYSTAL_TYPE_HYPOTHESIS,
    ) -> Dict[str, Any]:
        """Step 1: 原始捕獲 -- 記錄觸發情境，判定結晶類型.

        Args:
            raw_material: 原始對話素材
            source_context: 來源上下文（對話摘要等）
            crystal_type: 預判的結晶類型

        Returns:
            捕獲結果字典（包含原始素材和初步類型）
        """
        if crystal_type not in CRYSTAL_TYPES:
            crystal_type = CRYSTAL_TYPE_HYPOTHESIS

        captured = {
            "raw_material": raw_material,
            "source_context": source_context,
            "crystal_type": crystal_type,
            "captured_at": datetime.now().isoformat(),
        }

        logger.info(
            f"結晶化 Step 1 完成：原始捕獲 | type={crystal_type}"
        )
        return captured

    def refine(
        self,
        captured: Dict[str, Any],
        g1_summary: str = "",
        g2_structure: Optional[List[str]] = None,
        g3_root_inquiry: str = "",
        g4_insights: Optional[List[str]] = None,
        assumption: str = "",
        evidence: str = "",
        limitation: str = "",
        tags: Optional[List[str]] = None,
        domain: str = "",
    ) -> Dict[str, Any]:
        """Step 2: 結構精煉 -- 填寫 GEO 四層與三元組.

        若未提供結構化內容，則從原始素材中萃取。

        Args:
            captured: Step 1 的捕獲結果
            g1_summary: G1 摘要（一句話）
            g2_structure: G2 MECE 拆解
            g3_root_inquiry: G3 Root Inquiry
            g4_insights: G4 洞見列表
            assumption: 基本假設
            evidence: 支持證據
            limitation: 限制條件
            tags: 標籤
            domain: 領域

        Returns:
            精煉結果字典
        """
        raw = captured.get("raw_material", "")

        # 若未提供 G1，從原始素材取前 30 字作為摘要
        if not g1_summary:
            g1_summary = raw[:80].strip()

        # 若未提供 G2，留空（避免與 G1 重複）
        if not g2_structure:
            g2_structure = []

        # 若未提供 G3，使用通用引導問題（避免複製 raw_material）
        if not g3_root_inquiry:
            g3_root_inquiry = "這個觀察背後的核心問題是什麼？"

        # 若未提供 G4，留空（避免與 G1 重複）
        if not g4_insights:
            g4_insights = []

        # 三元組預設值
        if not assumption:
            assumption = "待釐清"
        if not evidence:
            evidence = f"來源：{captured.get('source_context', '對話觀察')}"
        if not limitation:
            limitation = "適用範圍待確認"

        refined = {
            **captured,
            "g1_summary": g1_summary,
            "g2_structure": g2_structure,
            "g3_root_inquiry": g3_root_inquiry,
            "g4_insights": g4_insights,
            "assumption": assumption,
            "evidence": evidence,
            "limitation": limitation,
            "tags": tags or [],
            "domain": domain,
        }

        logger.info("結晶化 Step 2 完成：結構精煉")
        return refined

    def link_discovery(
        self, refined: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
        """Step 3: 連結發現 -- 掃描現有結晶，找出語義相關的結晶.

        使用簡易文字相似度比對（SequenceMatcher）。

        Args:
            refined: Step 2 的精煉結果

        Returns:
            (更新後的精煉結果, 發現的連結候選列表)
        """
        g1 = refined.get("g1_summary", "")
        discovered_links: List[Dict[str, str]] = []

        new_type = refined.get("crystal_type", "Insight")

        for cuid, crystal in self._crystals.items():
            if crystal.archived:
                continue

            # 計算 G1 摘要的文字相似度
            similarity = SequenceMatcher(
                None, g1, crystal.g1_summary
            ).ratio()

            if similarity > SIMILARITY_MERGE_THRESHOLD:
                # 高度相似 -- extends（對同一主題的延伸/更新）
                discovered_links.append({
                    "target_cuid": cuid,
                    "link_type": "extends",
                    "similarity": str(round(similarity, 3)),
                    "note": "高度相似，可能是延伸或需要合併",
                })
            elif similarity > 0.5:
                # 中高相似度 -- 語義分類
                # Lesson 遇到 Hypothesis = 可能支持或矛盾
                existing_type = crystal.crystal_type
                if (
                    (new_type == "Lesson" and existing_type == "Hypothesis")
                    or (new_type == "Hypothesis" and existing_type == "Lesson")
                ):
                    discovered_links.append({
                        "target_cuid": cuid,
                        "link_type": "supports",
                        "similarity": str(round(similarity, 3)),
                        "note": "經驗與假說互相佐證",
                    })
                elif new_type == existing_type:
                    discovered_links.append({
                        "target_cuid": cuid,
                        "link_type": "supports",
                        "similarity": str(round(similarity, 3)),
                        "note": "同類型結晶，相互支持",
                    })
                else:
                    discovered_links.append({
                        "target_cuid": cuid,
                        "link_type": "supports",
                        "similarity": str(round(similarity, 3)),
                        "note": "中高相似度，語義支持",
                    })
            elif similarity > 0.3:
                # 中度相似 -- 相關連結
                discovered_links.append({
                    "target_cuid": cuid,
                    "link_type": "related",
                    "similarity": str(round(similarity, 3)),
                    "note": "語義相關",
                })

        refined["discovered_links"] = discovered_links

        logger.info(
            f"結晶化 Step 3 完成：發現 {len(discovered_links)} 個連結候選"
        )
        return refined, discovered_links

    def quality_check(
        self,
        refined: Dict[str, Any],
        mode: str = "strict",
    ) -> Tuple[bool, List[str]]:
        """Step 4: 品質閘檢查 -- 四道 Gate 依序驗證.

        Gate 0 (G0): 非重複檢查
        Gate 1 (G1): 摘要通過電梯測試（< 30 字）
        Gate 2 (G2): MECE 冗餘率 < 10%
        Gate 3 (G3): Root Inquiry 存在

        Args:
            refined: Step 2/3 的精煉結果
            mode: "strict" (人工結晶，全 Gate 強制) |
                  "auto" (自動結晶，G2/G3 降級為 warning 不阻擋)

        Returns:
            (是否全部通過, 未通過的問題列表)
        """
        issues: List[str] = []
        warnings: List[str] = []

        # Gate 0: 非重複檢查（嚴格模式和自動模式都強制）
        g1 = refined.get("g1_summary", "")
        for cuid, crystal in self._crystals.items():
            if crystal.archived:
                continue
            sim = SequenceMatcher(None, g1, crystal.g1_summary).ratio()
            if sim > 0.9:
                issues.append(
                    f"G0 失敗：與 {cuid} 高度重複 "
                    f"(相似度 {sim:.2f})"
                )
                break

        # Gate 1: 電梯測試 -- G1 摘要必須存在（兩種模式都強制）
        if not g1.strip():
            issues.append("G1 失敗：摘要為空")

        # Gate 2: MECE 冗餘率 < 10%
        g2 = refined.get("g2_structure", [])
        if len(g2) < 2:
            if mode == "auto":
                # auto 模式：G2 降級為 warning，不阻擋結晶
                warnings.append("G2 警告：MECE 拆解不足（auto 模式放行）")
            else:
                issues.append("G2 失敗：MECE 拆解不足（至少需要 2 個面向）")
        else:
            redundancy = self._calc_redundancy(g2)
            threshold = 0.20 if mode == "auto" else 0.10
            if redundancy > threshold:
                if mode == "auto":
                    warnings.append(
                        f"G2 警告：冗餘率 {redundancy:.1%}（auto 模式放行）"
                    )
                else:
                    issues.append(
                        f"G2 失敗：冗餘率 {redundancy:.1%} 超過 10% 閾值"
                    )

        # Gate 3: Root Inquiry 存在
        g3 = refined.get("g3_root_inquiry", "")
        if not g3.strip():
            if mode == "auto":
                warnings.append("G3 警告：Root Inquiry 為空（auto 模式放行）")
            else:
                issues.append("G3 失敗：Root Inquiry 為空")

        passed = len(issues) == 0

        log_parts = [
            f"結晶化 Step 4 完成：品質閘 {'通過' if passed else '未通過'}",
            f"mode={mode}",
            f"問題數: {len(issues)}",
        ]
        if warnings:
            log_parts.append(f"警告數: {len(warnings)}")
        logger.info(" | ".join(log_parts))

        # 將 warnings 附加到結果（不影響 passed 判定，但讓呼叫端可見）
        if warnings:
            issues.extend(warnings)

        return passed, issues

    def register(
        self,
        refined: Dict[str, Any],
        cuid: str,
    ) -> Crystal:
        """Step 5: 註冊入庫 -- 建立 Crystal 實例.

        Args:
            refined: 經過精煉和檢查的結晶資料
            cuid: 已分配的 CUID

        Returns:
            新建立的 Crystal 實例
        """
        # 決定驗證等級
        crystal_type = refined.get("crystal_type", CRYSTAL_TYPE_HYPOTHESIS)
        verification_map = {
            CRYSTAL_TYPE_INSIGHT: "proven",
            CRYSTAL_TYPE_PATTERN: "observed",
            CRYSTAL_TYPE_LESSON: "observed",
            CRYSTAL_TYPE_HYPOTHESIS: "hypothetical",
        }
        verification_level = verification_map.get(
            crystal_type, "hypothetical"
        )

        crystal = Crystal(
            cuid=cuid,
            crystal_type=crystal_type,
            g1_summary=refined.get("g1_summary", ""),
            g2_structure=refined.get("g2_structure", []),
            g3_root_inquiry=refined.get("g3_root_inquiry", ""),
            g4_insights=refined.get("g4_insights", []),
            assumption=refined.get("assumption", ""),
            evidence=refined.get("evidence", ""),
            limitation=refined.get("limitation", ""),
            verification_level=verification_level,
            tags=refined.get("tags", []),
            domain=refined.get("domain", ""),
            source_context=refined.get("source_context", ""),
        )

        # 計算初始共振指數
        crystal.ri_score = ResonanceCalculator.calculate(crystal)

        logger.info(
            f"結晶化 Step 5 完成：註冊入庫 | "
            f"cuid={cuid} type={crystal_type} ri={crystal.ri_score}"
        )
        return crystal

    @staticmethod
    def _calc_redundancy(items: List[str]) -> float:
        """計算列表項目之間的冗餘率.

        取所有兩兩配對的最大相似度作為冗餘率。

        Args:
            items: G2 拆解項目列表

        Returns:
            冗餘率 (0-1)
        """
        if len(items) < 2:
            return 0.0

        max_sim = 0.0
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                sim = SequenceMatcher(None, items[i], items[j]).ratio()
                max_sim = max(max_sim, sim)

        return max_sim


# ═══════════════════════════════════════════
# 再結晶引擎
# ═══════════════════════════════════════════

class RecrystallizationEngine:
    """再結晶引擎 -- 知識的演化.

    功能：
    - 冗餘偵測與合併建議（> 70% 相似）
    - 矛盾偵測與標記（不強制消除）
    - 過期偵測與歸檔（90 天 RI < 0.05）
    - 升級候選偵測（Hypothesis -> Pattern）
    - 降級候選偵測（Insight -> Pattern）
    - 碎片整合偵測（5+ 同領域小結晶）
    """

    def __init__(
        self,
        crystals: Dict[str, Crystal],
        dag: CrystalDAG,
    ) -> None:
        """初始化再結晶引擎.

        Args:
            crystals: 結晶字典（cuid -> Crystal）
            dag: 結晶 DAG
        """
        self._crystals = crystals
        self._dag = dag

    def detect_redundancy(self) -> List[Tuple[str, str, float]]:
        """偵測語義重疊超過 70% 的結晶對.

        Returns:
            重疊結晶對列表：[(cuid_a, cuid_b, similarity)]
        """
        redundant_pairs: List[Tuple[str, str, float]] = []
        active_cuids = [
            cuid for cuid, c in self._crystals.items()
            if not c.archived and c.status != "merged"
        ]

        for i in range(len(active_cuids)):
            for j in range(i + 1, len(active_cuids)):
                cuid_a = active_cuids[i]
                cuid_b = active_cuids[j]
                crystal_a = self._crystals[cuid_a]
                crystal_b = self._crystals[cuid_b]

                similarity = self._calc_crystal_similarity(
                    crystal_a, crystal_b
                )

                if similarity >= SIMILARITY_MERGE_THRESHOLD:
                    redundant_pairs.append((cuid_a, cuid_b, similarity))

        logger.info(f"再結晶：發現 {len(redundant_pairs)} 對冗餘結晶")
        return redundant_pairs

    def detect_contradictions(self) -> List[Tuple[str, str]]:
        """偵測矛盾結晶（通過 DAG 中的 contradicts 連結）.

        Returns:
            矛盾結晶對列表：[(cuid_a, cuid_b)]
        """
        contradictions: List[Tuple[str, str]] = []
        seen: Set[Tuple[str, str]] = set()

        for link in self._dag.get_all_links():
            if link.link_type == "contradicts":
                pair = tuple(sorted([link.from_cuid, link.to_cuid]))
                if pair not in seen:
                    seen.add(pair)
                    contradictions.append((link.from_cuid, link.to_cuid))

        return contradictions

    def detect_stale(self) -> List[str]:
        """偵測 90 天未使用且 RI < 0.05 的過期結晶.

        Returns:
            過期結晶的 CUID 列表
        """
        stale: List[str] = []
        now = datetime.now()

        for cuid, crystal in self._crystals.items():
            if crystal.archived:
                continue

            # 計算最新 RI
            ri = ResonanceCalculator.calculate(crystal)

            # 計算距離最後引用的天數
            try:
                last_ref = datetime.fromisoformat(crystal.last_referenced)
                days_since = (now - last_ref).days
            except (ValueError, TypeError):
                days_since = 0

            if ri < RI_ARCHIVE_THRESHOLD and days_since >= ARCHIVE_STALE_DAYS:
                stale.append(cuid)

        logger.info(f"再結晶：發現 {len(stale)} 顆過期結晶")
        return stale

    def detect_upgrade_candidates(self) -> List[str]:
        """偵測可升級的 Hypothesis（成功 3 次以上）.

        Returns:
            升級候選的 CUID 列表
        """
        candidates: List[str] = []

        for cuid, crystal in self._crystals.items():
            if crystal.archived:
                continue
            if (
                crystal.crystal_type == CRYSTAL_TYPE_HYPOTHESIS
                and crystal.success_count >= HYPOTHESIS_UPGRADE_COUNT
            ):
                candidates.append(cuid)

        return candidates

    def detect_downgrade_candidates(self) -> List[str]:
        """偵測需降級的 Insight（反證 2 次以上）.

        Returns:
            降級候選的 CUID 列表
        """
        candidates: List[str] = []

        for cuid, crystal in self._crystals.items():
            if crystal.archived:
                continue
            if (
                crystal.crystal_type == CRYSTAL_TYPE_INSIGHT
                and crystal.counter_evidence_count >= INSIGHT_DOWNGRADE_COUNT
            ):
                candidates.append(cuid)

        return candidates

    def detect_fragments(self) -> Dict[str, List[str]]:
        """偵測同領域 5+ 小型結晶（碎片化）.

        Returns:
            碎片化領域字典：{domain -> [cuid, ...]}
        """
        domain_crystals: Dict[str, List[str]] = defaultdict(list)

        for cuid, crystal in self._crystals.items():
            if crystal.archived or not crystal.domain:
                continue
            domain_crystals[crystal.domain].append(cuid)

        # 篩選 5+ 的領域
        fragments = {
            domain: cuids
            for domain, cuids in domain_crystals.items()
            if len(cuids) >= FRAGMENT_CONSOLIDATION_COUNT
        }

        return fragments

    def detect_expired_hypotheses(self) -> List[str]:
        """偵測超過 30 天驗證窗口的 Hypothesis.

        Returns:
            過期 Hypothesis 的 CUID 列表
        """
        expired: List[str] = []
        now = datetime.now()

        for cuid, crystal in self._crystals.items():
            if crystal.archived:
                continue
            if crystal.crystal_type != CRYSTAL_TYPE_HYPOTHESIS:
                continue

            try:
                created = datetime.fromisoformat(crystal.created_at)
                days_since = (now - created).days
                if days_since > HYPOTHESIS_WINDOW_DAYS:
                    expired.append(cuid)
            except (ValueError, TypeError):
                continue

        return expired

    def merge_crystals(
        self,
        cuid_a: str,
        cuid_b: str,
        new_cuid: str,
    ) -> Optional[Crystal]:
        """合併兩顆結晶為一顆新結晶.

        保留兩者的精華，舊結晶標記為 merged。

        Args:
            cuid_a: 第一顆結晶的 CUID
            cuid_b: 第二顆結晶的 CUID
            new_cuid: 新結晶的 CUID

        Returns:
            合併後的新結晶，或 None（若找不到原始結晶）
        """
        crystal_a = self._crystals.get(cuid_a)
        crystal_b = self._crystals.get(cuid_b)

        if not crystal_a or not crystal_b:
            return None

        # 選擇較高驗證等級的類型
        level_order = {v: i for i, v in enumerate(VERIFICATION_LEVELS)}
        if (
            level_order.get(crystal_a.verification_level, 0)
            >= level_order.get(crystal_b.verification_level, 0)
        ):
            primary = crystal_a
            secondary = crystal_b
        else:
            primary = crystal_b
            secondary = crystal_a

        # 合併 GEO 結構
        merged_g2 = list(set(primary.g2_structure + secondary.g2_structure))
        merged_g4 = list(set(primary.g4_insights + secondary.g4_insights))
        merged_tags = list(set(primary.tags + secondary.tags))

        merged = Crystal(
            cuid=new_cuid,
            crystal_type=primary.crystal_type,
            g1_summary=primary.g1_summary,
            g2_structure=merged_g2,
            g3_root_inquiry=primary.g3_root_inquiry,
            g4_insights=merged_g4,
            assumption=primary.assumption,
            evidence=f"{primary.evidence}; {secondary.evidence}",
            limitation=f"{primary.limitation}; {secondary.limitation}",
            verification_level=primary.verification_level,
            tags=merged_tags,
            domain=primary.domain or secondary.domain,
            reference_count=primary.reference_count + secondary.reference_count,
            source_context=(
                f"合併自 {cuid_a} 和 {cuid_b}"
            ),
        )

        # 標記舊結晶為已合併
        crystal_a.status = "merged"
        crystal_a.archived = True
        crystal_a.updated_at = datetime.now().isoformat()
        crystal_b.status = "merged"
        crystal_b.archived = True
        crystal_b.updated_at = datetime.now().isoformat()

        # 在 DAG 中建立 derived_from 連結
        self._dag.add_link(CrystalLink(
            from_cuid=new_cuid,
            to_cuid=cuid_a,
            link_type="derived_from",
        ))
        self._dag.add_link(CrystalLink(
            from_cuid=new_cuid,
            to_cuid=cuid_b,
            link_type="derived_from",
        ))

        logger.info(
            f"再結晶：合併 {cuid_a} + {cuid_b} -> {new_cuid}"
        )
        return merged

    def upgrade_crystal(self, cuid: str) -> bool:
        """升級結晶類型.

        Hypothesis -> Pattern (成功 3 次以上)
        Pattern -> Insight (跨情境驗證)

        Args:
            cuid: 要升級的結晶 CUID

        Returns:
            True 表示升級成功
        """
        crystal = self._crystals.get(cuid)
        if not crystal:
            return False

        old_type = crystal.crystal_type
        old_level = crystal.verification_level

        if crystal.crystal_type == CRYSTAL_TYPE_HYPOTHESIS:
            crystal.crystal_type = CRYSTAL_TYPE_PATTERN
            crystal.verification_level = "observed"
        elif crystal.crystal_type == CRYSTAL_TYPE_PATTERN:
            crystal.crystal_type = CRYSTAL_TYPE_INSIGHT
            crystal.verification_level = "tested"
        elif crystal.crystal_type == CRYSTAL_TYPE_LESSON:
            crystal.crystal_type = CRYSTAL_TYPE_INSIGHT
            crystal.verification_level = "tested"
        else:
            logger.info(f"結晶 {cuid} 已是最高等級 Insight，無法升級")
            return False

        crystal.updated_at = datetime.now().isoformat()

        logger.info(
            f"再結晶：升級 {cuid} | "
            f"{old_type}({old_level}) -> "
            f"{crystal.crystal_type}({crystal.verification_level})"
        )
        return True

    def downgrade_crystal(self, cuid: str, reason: str = "") -> bool:
        """降級結晶類型（Insight -> Pattern after 2+ 反證）.

        Args:
            cuid: 要降級的結晶 CUID
            reason: 降級原因

        Returns:
            True 表示降級成功
        """
        crystal = self._crystals.get(cuid)
        if not crystal:
            return False

        old_type = crystal.crystal_type

        if crystal.crystal_type == CRYSTAL_TYPE_INSIGHT:
            crystal.crystal_type = CRYSTAL_TYPE_PATTERN
            crystal.verification_level = "observed"
        elif crystal.crystal_type == CRYSTAL_TYPE_PATTERN:
            crystal.crystal_type = CRYSTAL_TYPE_HYPOTHESIS
            crystal.verification_level = "hypothetical"
        else:
            logger.info(
                f"結晶 {cuid} 類型為 {crystal.crystal_type}，無法再降級"
            )
            return False

        crystal.updated_at = datetime.now().isoformat()

        if reason:
            crystal.source_context += f" | 降級原因: {reason}"

        logger.info(
            f"再結晶：降級 {cuid} | {old_type} -> {crystal.crystal_type}"
            f" | 原因: {reason}"
        )
        return True

    def archive_crystal(self, cuid: str) -> bool:
        """歸檔結晶（不刪除，標記為已歸檔）.

        Args:
            cuid: 要歸檔的結晶 CUID

        Returns:
            True 表示歸檔成功
        """
        crystal = self._crystals.get(cuid)
        if not crystal:
            return False

        crystal.archived = True
        crystal.status = "archived"
        crystal.updated_at = datetime.now().isoformat()

        logger.info(f"再結晶：歸檔 {cuid}")
        return True

    @staticmethod
    def _calc_crystal_similarity(a: Crystal, b: Crystal) -> float:
        """計算兩顆結晶之間的綜合相似度.

        綜合 G1 摘要、G2 結構、標籤的相似度。

        Args:
            a: 第一顆結晶
            b: 第二顆結晶

        Returns:
            相似度 (0-1)
        """
        # G1 摘要相似度（權重 50%）
        g1_sim = SequenceMatcher(None, a.g1_summary, b.g1_summary).ratio()

        # G2 結構相似度（權重 30%）
        g2_text_a = " ".join(a.g2_structure)
        g2_text_b = " ".join(b.g2_structure)
        g2_sim = SequenceMatcher(None, g2_text_a, g2_text_b).ratio()

        # 標籤重疊度（權重 20%）
        tags_a = set(a.tags)
        tags_b = set(b.tags)
        if tags_a or tags_b:
            tag_sim = len(tags_a & tags_b) / max(
                len(tags_a | tags_b), 1
            )
        else:
            tag_sim = 0.0

        return 0.5 * g1_sim + 0.3 * g2_sim + 0.2 * tag_sim


# ═══════════════════════════════════════════
# 持久化存儲
# ═══════════════════════════════════════════

class LatticeStore(DataContract):
    """知識晶格持久化存儲.

    檔案結構：
    - data/lattice/crystals.json     -- 所有活躍結晶
    - data/lattice/links.json        -- 所有連結
    - data/lattice/archive.json      -- 已歸檔結晶
    - data/lattice/cuid_counter.json -- CUID 序號計數器
    """

    @classmethod
    def store_spec(cls) -> StoreSpec:
        return StoreSpec(
            name="lattice_store",
            engine=StoreEngine.JSON,
            ttl=TTLTier.PERMANENT,
            description="知識晶格結晶化存儲",
            tables=["crystals.json", "links.json", "archive.json", "cuid_counter.json"],
        )

    def health_check(self) -> Dict[str, Any]:
        try:
            files = {
                "crystals": self._crystals_path,
                "links": self._links_path,
                "archive": self._archive_path,
                "counter": self._counter_path,
            }
            sizes = {}
            for k, p in files.items():
                sizes[k] = p.stat().st_size if p.exists() else 0
            return {"status": "ok", "file_sizes": sizes}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def __init__(self, data_dir: str = "data") -> None:
        """初始化存儲.

        Args:
            data_dir: 資料根目錄
        """
        self._base_path = Path(data_dir) / "lattice"
        self._base_path.mkdir(parents=True, exist_ok=True)

        self._crystals_path = self._base_path / "crystals.json"
        self._links_path = self._base_path / "links.json"
        self._archive_path = self._base_path / "archive.json"
        self._counter_path = self._base_path / "cuid_counter.json"

        # 執行緒鎖（檔案操作安全）
        self._lock = threading.Lock()

    # ── 結晶存取 ──

    def load_crystals(self) -> Dict[str, Crystal]:
        """載入所有活躍結晶.

        Returns:
            結晶字典（cuid -> Crystal）
        """
        with self._lock:
            data = self._read_json(self._crystals_path, default=[])
            crystals: Dict[str, Crystal] = {}
            for item in data:
                try:
                    crystal = Crystal.from_dict(item)
                    crystals[crystal.cuid] = crystal
                except Exception as e:
                    logger.error(f"載入結晶失敗: {e}")
            return crystals

    def save_crystals(self, crystals: Dict[str, Crystal]) -> None:
        """儲存所有活躍結晶.

        Args:
            crystals: 結晶字典
        """
        with self._lock:
            data = [c.to_dict() for c in crystals.values()]
            self._write_json(self._crystals_path, data)

    # ── 連結存取 ──

    def load_links(self) -> List[CrystalLink]:
        """載入所有連結.

        Returns:
            連結列表
        """
        with self._lock:
            data = self._read_json(self._links_path, default=[])
            links: List[CrystalLink] = []
            for item in data:
                try:
                    links.append(CrystalLink.from_dict(item))
                except Exception as e:
                    logger.error(f"載入連結失敗: {e}")
            return links

    def save_links(self, links: List[CrystalLink]) -> None:
        """儲存所有連結.

        Args:
            links: 連結列表
        """
        with self._lock:
            data = [link.to_dict() for link in links]
            self._write_json(self._links_path, data)

    # ── 歸檔存取 ──

    def load_archive(self) -> Dict[str, Crystal]:
        """載入已歸檔結晶.

        Returns:
            歸檔結晶字典
        """
        with self._lock:
            data = self._read_json(self._archive_path, default=[])
            archive: Dict[str, Crystal] = {}
            for item in data:
                try:
                    crystal = Crystal.from_dict(item)
                    archive[crystal.cuid] = crystal
                except Exception as e:
                    logger.error(f"載入歸檔結晶失敗: {e}")
            return archive

    def save_archive(self, archive: Dict[str, Crystal]) -> None:
        """儲存歸檔結晶.

        Args:
            archive: 歸檔結晶字典
        """
        with self._lock:
            data = [c.to_dict() for c in archive.values()]
            self._write_json(self._archive_path, data)

    # ── CUID 計數器 ──

    def load_counters(self) -> Dict[str, int]:
        """載入 CUID 序號計數器.

        Returns:
            計數器字典（type_abbr -> seq）
        """
        with self._lock:
            return self._read_json(
                self._counter_path,
                default={"INS": 0, "PAT": 0, "LES": 0, "HYP": 0},
            )

    def save_counters(self, counters: Dict[str, int]) -> None:
        """儲存 CUID 序號計數器.

        Args:
            counters: 計數器字典
        """
        with self._lock:
            self._write_json(self._counter_path, counters)

    # ── 內部工具 ──

    @staticmethod
    def _read_json(path: Path, default: Any = None) -> Any:
        """讀取 JSON 檔案.

        Args:
            path: 檔案路徑
            default: 檔案不存在或解析失敗時的預設值

        Returns:
            解析後的 Python 物件
        """
        if not path.exists():
            return default if default is not None else {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"讀取 JSON 失敗 ({path}): {e}")
            return default if default is not None else {}

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        """寫入 JSON 檔案（原子寫入）.

        先寫到暫存檔再改名，避免寫入中斷導致資料損毀。

        Args:
            path: 目標檔案路徑
            data: 要寫入的資料
        """
        tmp_path = path.with_suffix(".tmp")
        try:
            tmp_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_path.replace(path)
        except OSError as e:
            logger.error(f"寫入 JSON 失敗 ({path}): {e}")
            # 清理暫存檔
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError as e:
                    logger.debug(f"[KNOWLEDGE_LATTICE] operation failed (degraded): {e}")


# ═══════════════════════════════════════════
# 主引擎 -- Knowledge Lattice
# ═══════════════════════════════════════════

class KnowledgeLattice:
    """知識晶格主引擎.

    整合結晶化流程、DAG 管理、共振指數、再結晶引擎，
    提供完整的知識累積與演化介面。

    用法：
        lattice = KnowledgeLattice(data_dir="data")
        crystal = lattice.crystallize("原始素材", "來源上下文")
        results = lattice.recall("搜尋關鍵字")
        lattice.recrystallize()
    """

    def __init__(self, data_dir: str = "data") -> None:
        """初始化知識晶格.

        Args:
            data_dir: 資料根目錄
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 持久化存儲
        self._store = LatticeStore(data_dir=data_dir)

        # 載入結晶和連結
        self._crystals: Dict[str, Crystal] = self._store.load_crystals()
        self._archive: Dict[str, Crystal] = self._store.load_archive()

        # DAG
        self._dag = CrystalDAG()
        links = self._store.load_links()
        self._dag.load_links(links)
        # 確保所有結晶節點都在 DAG 中
        for cuid in self._crystals:
            self._dag.add_node(cuid)

        # CUID 計數器
        self._counters: Dict[str, int] = self._store.load_counters()

        # 結晶化流程器
        self._crystallizer = Crystallizer(
            crystals=self._crystals,
            dag=self._dag,
        )

        # 再結晶引擎
        self._recrystallizer = RecrystallizationEngine(
            crystals=self._crystals,
            dag=self._dag,
        )

        # 自上次再結晶以來的新增結晶計數
        self._crystals_since_last_recrystallize: int = 0

        # 執行緒鎖
        self._lock = threading.Lock()

        # VectorBridge（Qdrant 語義搜尋，靜默失敗）
        self._vector_bridge = None

        logger.info(
            f"Knowledge Lattice 初始化完成 | "
            f"結晶: {len(self._crystals)} | "
            f"歸檔: {len(self._archive)} | "
            f"連結: {len(self._dag.get_all_links())}"
        )

    # ═══════════════════════════════════════════
    # VectorBridge 整合（靜默失敗）
    # ═══════════════════════════════════════════

    def _get_vector_bridge(self):
        """Lazy 取得 VectorBridge（靜默失敗）."""
        if self._vector_bridge is not None:
            return self._vector_bridge
        try:
            from museon.vector.vector_bridge import VectorBridge
            vb = VectorBridge(workspace=self.data_dir)
            if vb.is_available():
                self._vector_bridge = vb
                return vb
        except Exception as e:
            logger.debug(f"[KNOWLEDGE_LATTICE] vector failed (degraded): {e}")
        return None

    def _vector_index_crystal(self, crystal: "Crystal") -> None:
        """將結晶索引到 Qdrant crystals collection（靜默失敗）."""
        try:
            vb = self._get_vector_bridge()
            if vb is None:
                return
            # 組合可搜尋文本：G1 摘要 + tags + domain
            text = " ".join([
                crystal.g1_summary,
                " ".join(crystal.tags),
                crystal.domain,
                crystal.g3_root_inquiry,
            ]).strip()
            if not text:
                return
            metadata = {
                "crystal_type": crystal.crystal_type,
                "verification_level": crystal.verification_level,
                "domain": crystal.domain,
            }
            vb.index("crystals", crystal.cuid, text, metadata=metadata)
        except Exception:
            logger.debug("向量索引失敗，不影響主流程", exc_info=True)

    def _vector_recall_crystals(
        self, query: str, limit: int,
    ) -> List[Tuple[str, float]]:
        """從 Qdrant crystals collection 語義搜尋（靜默失敗回傳空 list）.

        Returns:
            [(cuid, score), ...]
        """
        try:
            vb = self._get_vector_bridge()
            if vb is None:
                return []
            results = vb.search("crystals", query, limit=limit)
            return [
                (r["id"], r["score"])
                for r in results
            ]
        except Exception:
            return []

    # ═══════════════════════════════════════════
    # 核心 API
    # ═══════════════════════════════════════════

    def crystallize(
        self,
        raw_material: str,
        source_context: str = "",
        crystal_type: str = CRYSTAL_TYPE_HYPOTHESIS,
        g1_summary: str = "",
        g2_structure: Optional[List[str]] = None,
        g3_root_inquiry: str = "",
        g4_insights: Optional[List[str]] = None,
        assumption: str = "",
        evidence: str = "",
        limitation: str = "",
        tags: Optional[List[str]] = None,
        domain: str = "",
        mode: str = "strict",
    ) -> Crystal:
        """完整五步驟結晶化流程.

        Args:
            raw_material: 原始對話素材
            source_context: 來源上下文
            crystal_type: 結晶類型
            g1_summary: G1 摘要（可選，自動萃取）
            g2_structure: G2 MECE 拆解（可選）
            g3_root_inquiry: G3 Root Inquiry（可選）
            g4_insights: G4 洞見（可選）
            assumption: 基本假設
            evidence: 支持證據
            limitation: 限制條件
            tags: 標籤
            domain: 領域
            mode: "strict" (人工/高品質結晶) |
                  "auto" (自動結晶，G2/G3 放寬)

        Returns:
            新建立的 Crystal 實例
        """
        # 參數驗證
        if not raw_material or not isinstance(raw_material, str):
            raise ValueError(
                f"crystallize: raw_material 必須為非空字串，"
                f"收到 {type(raw_material).__name__}"
            )
        if crystal_type not in CRYSTAL_TYPES:
            logger.warning(
                f"crystallize: 無效的 crystal_type '{crystal_type}'，"
                f"降級為 {CRYSTAL_TYPE_HYPOTHESIS}"
            )
            crystal_type = CRYSTAL_TYPE_HYPOTHESIS

        with self._lock:
            # Step 1: 原始捕獲
            captured = self._crystallizer.capture(
                raw_material=raw_material,
                source_context=source_context,
                crystal_type=crystal_type,
            )

            # Step 2: 結構精煉
            refined = self._crystallizer.refine(
                captured=captured,
                g1_summary=g1_summary,
                g2_structure=g2_structure,
                g3_root_inquiry=g3_root_inquiry,
                g4_insights=g4_insights,
                assumption=assumption,
                evidence=evidence,
                limitation=limitation,
                tags=tags,
                domain=domain,
            )

            # Step 3: 連結發現
            refined, discovered_links = self._crystallizer.link_discovery(
                refined
            )

            # Step 4: 品質閘檢查（mode 透傳至 G2/G3 閾值）
            passed, issues = self._crystallizer.quality_check(refined, mode=mode)
            if not passed:
                logger.warning(
                    f"品質閘未通過，標記為 quarantine: {issues}"
                )
                refined["quality_issues"] = issues
                refined["status"] = "quarantine"
            else:
                refined["status"] = "verified"

            # Step 5: 分配 CUID 並註冊
            cuid = self._generate_cuid(crystal_type)
            crystal = self._crystallizer.register(
                refined=refined, cuid=cuid
            )

            # 加入晶格
            self._crystals[cuid] = crystal
            self._dag.add_node(cuid)

            # 語義索引到 Qdrant（靜默失敗）
            self._vector_index_crystal(crystal)

            # quarantine crystal 不建立連結
            if refined.get("status") == "quarantine":
                logger.info(f"Crystal {cuid} quarantined — skipping link creation")
                self._persist()
                return crystal

            # 建立發現的連結
            for link_info in discovered_links:
                target_cuid = link_info.get("target_cuid", "")
                link_type = link_info.get("link_type", "related")
                if target_cuid and target_cuid in self._crystals:
                    self.add_link(
                        from_cuid=cuid,
                        to_cuid=target_cuid,
                        link_type=link_type,
                        confidence=float(
                            link_info.get("similarity", "0.5")
                        ),
                    )

            # 持久化
            self._persist()

            # 發布 CRYSTAL_CREATED（ActivityLogger 訂閱）
            try:
                from museon.core.event_bus import get_event_bus, CRYSTAL_CREATED
                get_event_bus().publish(CRYSTAL_CREATED, {
                    "cuid": cuid,
                    "crystal_type": crystal_type,
                    "domain": domain,
                    "source_context": source_context[:100],
                    "links_count": len(discovered_links),
                })
            except Exception as e:
                logger.debug(f"[KNOWLEDGE_LATTICE] crystal failed (degraded): {e}")

            # 檢查是否需要觸發輕量再結晶
            self._crystals_since_last_recrystallize += 1
            if (
                self._crystals_since_last_recrystallize
                >= RECRYSTALLIZE_INTERVAL
            ):
                logger.info(
                    f"已新增 {RECRYSTALLIZE_INTERVAL} 顆結晶，"
                    f"觸發輕量再結晶掃描"
                )
                self._crystals_since_last_recrystallize = 0
                # 輕量掃描（不自動執行，僅偵測）
                self._light_recrystallize_scan()

            return crystal

    def recall(
        self,
        query: str,
        top_n: int = 5,
    ) -> List[Crystal]:
        """語義搜尋結晶（Qdrant-primary 架構）.

        三階段搜尋：
          1. Primary: Qdrant 向量語義搜尋（crystals collection）
          2. Fallback: 關鍵字 + SequenceMatcher（Qdrant 不可用或不足時）
        合併評分：vector_score * 0.5 + keyword * 0.2 + RI * 0.3

        Args:
            query: 搜尋查詢
            top_n: 返回結果數量

        Returns:
            按相關度排序的結晶列表
        """
        if not query.strip():
            return []

        scored: List[Tuple[float, Crystal]] = []
        seen_cuids: set = set()

        # ── 階段 1（Primary）：Qdrant 向量語義搜尋 ──
        vector_hits = self._vector_recall_crystals(query, top_n * 2)
        vector_score_map: Dict[str, float] = {
            cuid: score for cuid, score in vector_hits
        }

        for cuid, v_score in vector_hits:
            crystal = self._crystals.get(cuid)
            if crystal is None or crystal.archived:
                continue
            if cuid in seen_cuids:
                continue
            seen_cuids.add(cuid)

            ri = ResonanceCalculator.calculate(crystal)
            # vector_score * 0.5 + RI * 0.3 + small keyword bonus * 0.2
            keyword_score = self._keyword_match_score(query, crystal)
            combined = (
                0.5 * v_score
                + 0.2 * keyword_score
                + 0.3 * ri
            )
            scored.append((combined, crystal))

        # ── 階段 2（Fallback）：SequenceMatcher + 關鍵字 ──
        # 執行 fallback 若 Qdrant 結果不足
        if len(scored) < top_n:
            for cuid, crystal in self._crystals.items():
                if crystal.archived or cuid in seen_cuids:
                    continue

                keyword_score = self._keyword_match_score(query, crystal)
                similarity_score = SequenceMatcher(
                    None, query, crystal.g1_summary
                ).ratio()
                ri = ResonanceCalculator.calculate(crystal)

                # 若此 cuid 也有向量分數（理論上不會，但防守）
                v_score = vector_score_map.get(cuid, 0.0)
                if v_score > 0:
                    combined = (
                        0.5 * v_score
                        + 0.2 * keyword_score
                        + 0.3 * ri
                    )
                else:
                    # 純 fallback 評分
                    combined = (
                        0.4 * keyword_score
                        + 0.3 * similarity_score
                        + 0.3 * ri
                    )

                if combined > 0.05:
                    scored.append((combined, crystal))

        # 按綜合分數降序排列
        scored.sort(key=lambda x: x[0], reverse=True)

        results = [crystal for _, crystal in scored[:top_n]]

        # 更新被引用結晶的參考計數
        now = datetime.now().isoformat()
        for crystal in results:
            crystal.reference_count += 1
            crystal.last_referenced = now
            crystal.ri_score = ResonanceCalculator.calculate(crystal)

        if results:
            self._persist()

        logger.info(
            f"召回查詢: '{query}' | 結果: {len(results)} 顆結晶"
        )
        return results

    def auto_recall(
        self,
        context: str,
        max_push: int = MAX_PROACTIVE_PUSH,
    ) -> List[Crystal]:
        """自動召回 -- 根據對話上下文主動推送相關結晶.

        Args:
            context: 當前對話上下文
            max_push: 最大推送數量

        Returns:
            推薦的結晶列表（最多 max_push 個）
        """
        results = self.recall(query=context, top_n=max_push)
        if results:
            logger.info(
                f"自動召回: 推送 {len(results)} 顆結晶"
            )
        return results

    # ── Layer 2: Crystal Chain Traversal（鏈式召回）──

    def recall_with_chains(
        self,
        context: str,
        max_push: int = 10,
        chain_hops: int = 1,
        chain_types: Optional[List[str]] = None,
    ) -> List[Crystal]:
        """鏈式召回 — 先語義召回核心結晶，再沿 DAG 鏈接擴展相關結晶.

        DNA27 Neural Tract BDD Spec §11:
          - 先做 recall() 取得種子結晶
          - 對每顆種子，沿 DAG 的 supports/extends/related 邊擴展
          - 去重後按 RI 排序，回傳 max_push 個

        Args:
            context: 查詢上下文
            max_push: 最終回傳結晶數上限
            chain_hops: DAG 擴展跳數（預設 1-hop）
            chain_types: 要追蹤的連結類型（預設 supports/extends/related）

        Returns:
            擴展後的結晶列表
        """
        if chain_types is None:
            chain_types = ["supports", "extends", "related"]

        # Phase 1: 語義種子（取 max_push 的一半作為種子）
        seed_count = max(3, max_push // 2)
        seeds = self.recall(query=context, top_n=seed_count)
        if not seeds:
            return []

        # Phase 2: DAG 鏈式擴展
        seen_cuids: set = {c.cuid for c in seeds}
        chain_crystals: List[Crystal] = []

        for seed in seeds:
            # 取得鄰居
            neighbor_cuids = self._dag.get_neighbors(
                seed.cuid, hops=chain_hops,
            )

            for ncuid in neighbor_cuids:
                if ncuid in seen_cuids:
                    continue

                # 檢查連結類型是否在允許列表
                links = self._dag.get_links_by_type(seed.cuid, "")
                # 取得所有與 seed 相關的連結
                all_links = (
                    self._dag.get_outgoing_links(seed.cuid)
                    + self._dag.get_incoming_links(seed.cuid)
                )
                relevant = any(
                    link.link_type in chain_types
                    and (link.to_cuid == ncuid or link.from_cuid == ncuid)
                    for link in all_links
                )
                if not relevant:
                    continue

                # 載入結晶
                crystal = self._crystals.get(ncuid)
                if crystal and not crystal.archived:
                    chain_crystals.append(crystal)
                    seen_cuids.add(ncuid)

        # Phase 3: 合併 + 排序（種子優先，鏈接結晶按 RI 排序）
        all_results = seeds + sorted(
            chain_crystals, key=lambda c: c.ri_score, reverse=True,
        )

        # 截斷到 max_push
        results = all_results[:max_push]

        if len(results) > len(seeds):
            logger.info(
                f"鏈式召回: 種子 {len(seeds)} + 鏈接 "
                f"{len(results) - len(seeds)} = {len(results)} 顆"
            )

        return results

    # ── Layer 3: Crystal Compression（結晶壓縮）──

    def compress_crystals(
        self,
        crystals: List["Crystal"],
        max_chars: int = 600,
    ) -> str:
        """將多顆結晶壓縮為精簡文本，用於 token 預算不足時.

        DNA27 Neural Tract BDD Spec §6 LayeredContent:
          - 當結晶數量超過閾值（如 >8 顆），壓縮為摘要
          - 純 Python 零 LLM（不用 Haiku）
          - 保留最重要的資訊：G1 摘要 + 結晶類型 + RI 分數

        策略：
          1. 按 RI 排序（高 RI 優先）
          2. 高 RI (≥0.5) 結晶：G1 + G4 第一條洞見
          3. 中 RI (≥0.2) 結晶：僅 G1 摘要
          4. 低 RI (<0.2) 結晶：合併為「相關主題」清單

        Args:
            crystals: 要壓縮的結晶列表
            max_chars: 壓縮後最大字元數

        Returns:
            壓縮後的文本
        """
        if not crystals:
            return ""

        # 按 RI 排序
        sorted_c = sorted(crystals, key=lambda c: c.ri_score, reverse=True)

        lines: List[str] = []
        char_count = 0

        for c in sorted_c:
            if char_count >= max_chars:
                break

            if c.ri_score >= 0.5:
                # 高 RI：G1 + G4 第一條
                line = f"- 【{c.crystal_type}】{c.g1_summary}"
                if c.g4_insights:
                    line += f"（{c.g4_insights[0][:40]}）"
            elif c.ri_score >= 0.2:
                # 中 RI：僅 G1
                line = f"- {c.g1_summary}"
            else:
                # 低 RI：極簡
                line = f"- {c.g1_summary[:30]}..."

            if char_count + len(line) > max_chars:
                break

            lines.append(line)
            char_count += len(line) + 1  # +1 for newline

        if not lines:
            return ""

        return "\n".join(lines)

    def add_link(
        self,
        from_cuid: str,
        to_cuid: str,
        link_type: str,
        confidence: float = 1.0,
    ) -> bool:
        """新增結晶連結（含環路偵測）.

        Args:
            from_cuid: 起點結晶 CUID
            to_cuid: 終點結晶 CUID
            link_type: 連結類型（supports/contradicts/extends/derived_from/related）
            confidence: 連結信心度 (0-1)

        Returns:
            True 表示成功新增
        """
        if link_type not in LINK_TYPES:
            logger.warning(f"無效的連結類型: {link_type}")
            return False

        if from_cuid not in self._crystals and from_cuid not in self._archive:
            logger.warning(f"起點結晶不存在: {from_cuid}")
            return False
        if to_cuid not in self._crystals and to_cuid not in self._archive:
            logger.warning(f"終點結晶不存在: {to_cuid}")
            return False

        link = CrystalLink(
            from_cuid=from_cuid,
            to_cuid=to_cuid,
            link_type=link_type,
            confidence=confidence,
        )

        success = self._dag.add_link(link)

        if success:
            # 若為矛盾連結，標記兩顆結晶為 disputed
            if link_type == "contradicts":
                for cuid in [from_cuid, to_cuid]:
                    if cuid in self._crystals:
                        self._crystals[cuid].status = "disputed"
                        self._crystals[cuid].updated_at = (
                            datetime.now().isoformat()
                        )

            self._persist()
            logger.info(
                f"新增連結: {from_cuid} -[{link_type}]-> {to_cuid}"
            )

        return success

    def get_resonance(self, cuid: str) -> float:
        """計算指定結晶的共振指數.

        Args:
            cuid: 結晶 CUID

        Returns:
            共振指數 (0-1)
        """
        crystal = self._crystals.get(cuid)
        if not crystal:
            crystal = self._archive.get(cuid)
        if not crystal:
            return 0.0

        ri = ResonanceCalculator.calculate(crystal)
        crystal.ri_score = ri
        return ri

    def recrystallize(self) -> Dict[str, Any]:
        """執行完整再結晶掃描.

        偵測冗餘、矛盾、過期、升級/降級候選、碎片化，
        回傳建議列表（不自動執行合併等操作）。

        Returns:
            再結晶報告字典
        """
        with self._lock:
            report: Dict[str, Any] = {
                "timestamp": datetime.now().isoformat(),
                "redundancy": [],
                "contradictions": [],
                "stale": [],
                "upgrade_candidates": [],
                "downgrade_candidates": [],
                "fragments": {},
                "expired_hypotheses": [],
            }

            # 冗餘偵測
            redundant = self._recrystallizer.detect_redundancy()
            report["redundancy"] = [
                {
                    "cuid_a": a,
                    "cuid_b": b,
                    "similarity": round(s, 3),
                }
                for a, b, s in redundant
            ]

            # 矛盾偵測
            contradictions = self._recrystallizer.detect_contradictions()
            report["contradictions"] = [
                {"cuid_a": a, "cuid_b": b}
                for a, b in contradictions
            ]

            # 過期偵測
            report["stale"] = self._recrystallizer.detect_stale()

            # 升級候選
            report["upgrade_candidates"] = (
                self._recrystallizer.detect_upgrade_candidates()
            )

            # 降級候選
            report["downgrade_candidates"] = (
                self._recrystallizer.detect_downgrade_candidates()
            )

            # 碎片化偵測
            report["fragments"] = self._recrystallizer.detect_fragments()

            # 過期 Hypothesis
            report["expired_hypotheses"] = (
                self._recrystallizer.detect_expired_hypotheses()
            )

            logger.info(
                f"再結晶完成 | "
                f"冗餘: {len(report['redundancy'])} | "
                f"矛盾: {len(report['contradictions'])} | "
                f"過期: {len(report['stale'])} | "
                f"升級: {len(report['upgrade_candidates'])} | "
                f"降級: {len(report['downgrade_candidates'])}"
            )

            return report

    def upgrade_crystal(self, cuid: str) -> bool:
        """升級結晶.

        Hypothesis -> Pattern (成功 3+ 次)
        Pattern -> Insight (跨情境驗證)

        Args:
            cuid: 結晶 CUID

        Returns:
            True 表示升級成功
        """
        with self._lock:
            success = self._recrystallizer.upgrade_crystal(cuid)
            if success:
                crystal = self._crystals.get(cuid)
                if crystal:
                    crystal.ri_score = ResonanceCalculator.calculate(crystal)
                self._persist()
            return success

    def downgrade_crystal(self, cuid: str, reason: str = "") -> bool:
        """降級結晶（Insight -> Pattern after 2+ 反證）.

        Args:
            cuid: 結晶 CUID
            reason: 降級原因

        Returns:
            True 表示降級成功
        """
        with self._lock:
            success = self._recrystallizer.downgrade_crystal(cuid, reason)
            if success:
                crystal = self._crystals.get(cuid)
                if crystal:
                    crystal.ri_score = ResonanceCalculator.calculate(crystal)
                self._persist()
            return success

    def archive_stale(self) -> List[str]:
        """歸檔低 RI 的過期結晶.

        將 90 天未使用且 RI < 0.05 的結晶移到歸檔區。

        Returns:
            被歸檔的結晶 CUID 列表
        """
        with self._lock:
            stale_cuids = self._recrystallizer.detect_stale()
            archived: List[str] = []

            for cuid in stale_cuids:
                crystal = self._crystals.get(cuid)
                if crystal:
                    self._recrystallizer.archive_crystal(cuid)
                    # 移到歸檔區
                    self._archive[cuid] = crystal
                    del self._crystals[cuid]
                    archived.append(cuid)

            if archived:
                self._persist()
                logger.info(
                    f"歸檔完成: {len(archived)} 顆結晶已歸檔"
                )

            return archived

    def health_report(self) -> Dict[str, Any]:
        """產生知識晶格健康報告.

        包含：結晶總數、類型分布、平均 RI、連結密度、
        歸檔數、活躍率、孤立結晶、領域覆蓋度。

        Returns:
            健康報告字典
        """
        # 類型分布
        type_counts: Dict[str, int] = defaultdict(int)
        total_ri = 0.0
        active_count = 0
        now = datetime.now()
        recently_referenced = 0

        for crystal in self._crystals.values():
            if crystal.archived:
                continue
            type_counts[crystal.crystal_type] += 1
            ri = ResonanceCalculator.calculate(crystal)
            total_ri += ri
            active_count += 1

            # 近 90 天被引用
            try:
                last_ref = datetime.fromisoformat(crystal.last_referenced)
                if (now - last_ref).days <= 90:
                    recently_referenced += 1
            except (ValueError, TypeError) as e:
                logger.debug(f"[KNOWLEDGE_LATTICE] crystal failed (degraded): {e}")

        avg_ri = total_ri / active_count if active_count > 0 else 0.0
        active_rate = (
            recently_referenced / active_count if active_count > 0 else 0.0
        )

        # 孤立結晶
        all_cuids = [
            c for c in self._crystals if not self._crystals[c].archived
        ]
        isolated = self._dag.get_isolated_nodes(all_cuids)

        # 領域分布
        domain_counts: Dict[str, int] = defaultdict(int)
        for crystal in self._crystals.values():
            if crystal.archived:
                continue
            if crystal.domain:
                domain_counts[crystal.domain] += 1

        # 盲點警告（結晶數 <= 2 的領域）
        blind_spots = [
            domain for domain, count in domain_counts.items() if count <= 2
        ]

        report = {
            "total_crystals": active_count,
            "archived_crystals": len(self._archive),
            "type_distribution": dict(type_counts),
            "average_ri": round(avg_ri, 4),
            "active_rate_90d": round(active_rate, 4),
            "link_density": round(self._dag.get_link_density(), 4),
            "total_links": len(self._dag.get_all_links()),
            "isolated_crystals": isolated,
            "isolated_count": len(isolated),
            "domain_distribution": dict(domain_counts),
            "blind_spots": blind_spots,
            "timestamp": now.isoformat(),
        }

        return report

    def post_conversation_scan(
        self,
        conversation_data: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        """對話結束後掃描結晶化候選.

        靜默掃描對話內容，識別潛在的結晶候選。

        Args:
            conversation_data: 對話紀錄（role + content）

        Returns:
            候選列表（每個候選包含原始素材和建議類型）
        """
        candidates: List[Dict[str, Any]] = []

        if not conversation_data:
            return candidates

        # 參數驗證：確保 conversation_data 格式正確
        if not isinstance(conversation_data, list):
            logger.warning(
                f"post_conversation_scan: 預期 list，收到 "
                f"{type(conversation_data).__name__}，跳過掃描"
            )
            return candidates

        # 安全提取訊息 — 防禦任何非 dict 的 entry
        user_messages: List[str] = []
        assistant_messages: List[str] = []
        for m in conversation_data:
            if not isinstance(m, dict):
                continue
            content = m.get("content") if isinstance(m, dict) else None
            if not isinstance(content, str) or not content.strip():
                continue
            role = m.get("role", "")
            if role == "user":
                user_messages.append(content)
            elif role == "assistant":
                assistant_messages.append(content)

        if not user_messages and not assistant_messages:
            return candidates

        try:
            combined_text = " ".join(user_messages + assistant_messages)

            # 啟發式識別候選
            # 規則 1: 助理回覆中包含分析性內容（長回覆）
            for msg in assistant_messages:
                if len(msg) > 500:
                    candidates.append({
                        "raw_material": msg[:500],
                        "suggested_type": CRYSTAL_TYPE_HYPOTHESIS,
                        "reason": "長篇分析性回覆",
                    })

            # 規則 2: 對話中出現錯誤修正（Lesson 候選）
            error_keywords = ["錯誤", "修正", "抱歉", "失誤", "改正", "更正"]
            for segment in combined_text.split("。"):
                if any(kw in segment for kw in error_keywords):
                    candidates.append({
                        "raw_material": segment.strip()[:300],
                        "suggested_type": CRYSTAL_TYPE_LESSON,
                        "reason": "偵測到錯誤修正模式",
                    })
                    break

            # 規則 3: 重複出現的主題（Pattern 候選）
            topic_freq: Dict[str, int] = defaultdict(int)
            for msg in user_messages:
                words = msg.replace("，", " ").replace("。", " ").split()
                for word in words:
                    if len(word) >= 4:
                        topic_freq[word] += 1

            for topic, freq in topic_freq.items():
                if freq >= 3:
                    candidates.append({
                        "raw_material": f"重複主題: {topic}",
                        "suggested_type": CRYSTAL_TYPE_PATTERN,
                        "reason": f"主題 '{topic}' 出現 {freq} 次",
                    })

            # 規則 4: Insight 候選 — 助理回覆包含結構化分析標記
            insight_markers = ["分析", "結論", "洞見", "發現", "根因", "策略"]
            for msg in assistant_messages:
                if len(msg) > 200 and sum(
                    1 for mk in insight_markers if mk in msg
                ) >= 2:
                    candidates.append({
                        "raw_material": msg[:500],
                        "suggested_type": CRYSTAL_TYPE_INSIGHT,
                        "reason": "含多個分析標記的結構化洞見",
                    })
                    break

        except Exception as e:
            logger.warning(f"結晶候選識別過程異常: {e}")

        if candidates:
            logger.info(
                f"對話掃描完成: 發現 {len(candidates)} 個結晶化候選"
            )
        return candidates

    def auto_crystallize_candidates(
        self,
        candidates: List[Dict[str, Any]],
        source_context: str = "",
    ) -> List[str]:
        """自動將高信心候選轉為真正的結晶.

        Args:
            candidates: post_conversation_scan 回傳的候選列表
            source_context: 來源上下文描述

        Returns:
            成功結晶化的 CUID 列表
        """
        created_cuids: List[str] = []
        for candidate in candidates:
            raw = candidate.get("raw_material", "")
            ctype = candidate.get("suggested_type", CRYSTAL_TYPE_HYPOTHESIS)
            reason = candidate.get("reason", "")
            if not raw or len(raw) < 20:
                continue
            try:
                crystal = self.crystallize(
                    raw_material=raw,
                    source_context=source_context or f"自動結晶: {reason}",
                    crystal_type=ctype,
                )
                created_cuids.append(crystal.cuid)
                logger.info(
                    f"自動結晶成功: {crystal.cuid} "
                    f"(type={ctype}, reason={reason})"
                )
            except Exception as e:
                logger.warning(f"自動結晶失敗: {e}")
        return created_cuids

    def nightly_maintenance(self) -> Dict[str, Any]:
        """夜間維護 -- 完整健康同步與再結晶（含自動執行）.

        包含：
        1. 更新所有結晶的共振指數
        2. 歸檔過期結晶
        3. 執行完整再結晶掃描
        4. ★ 自動執行再結晶動作（合併/升級/降級/歸檔）
        5. 產生健康報告

        Returns:
            維護報告
        """
        logger.info("Nightly maintenance 開始")

        with self._lock:
            # 1. 更新所有結晶的 RI（衰減計算）
            for crystal in self._crystals.values():
                if not crystal.archived:
                    crystal.ri_score = ResonanceCalculator.calculate(crystal)

        # 2. 歸檔過期結晶
        archived = self.archive_stale()

        # 3. 完整再結晶掃描
        recrystallize_report = self.recrystallize()

        # ═══ 4. ★ 自動執行再結晶動作 ═══
        actions_taken = self._execute_recrystallization(recrystallize_report)

        # 5. 健康報告
        health = self.health_report()

        # 持久化
        self._persist()

        maintenance_report = {
            "timestamp": datetime.now().isoformat(),
            "ri_updated": len(self._crystals),
            "archived": archived,
            "archived_count": len(archived),
            "recrystallize_report": recrystallize_report,
            "actions_taken": actions_taken,
            "health": health,
        }

        logger.info(
            f"Nightly maintenance 完成 | "
            f"RI 更新: {len(self._crystals)} | "
            f"歸檔: {len(archived)} | "
            f"動作: {actions_taken.get('summary', '無')}"
        )

        return maintenance_report

    def _execute_recrystallization(
        self, report: Dict[str, Any]
    ) -> Dict[str, Any]:
        """★ 根據再結晶掃描結果，自動執行合併/升級/降級/歸檔動作.

        這是從「記錄型系統」跨越到「自驅型系統」的關鍵方法。
        不再只是偵測問題然後等人處理，而是自動執行安全的修復動作。

        安全護欄：
        - 每次維護最多合併 5 對結晶（避免過度合併）
        - 每次最多升級 10 顆、降級 5 顆
        - 所有動作都有完整日誌
        - 合併前檢查相似度閾值

        Args:
            report: recrystallize() 產出的掃描報告

        Returns:
            已執行動作的摘要
        """
        actions = {
            "merged": 0,
            "upgraded": 0,
            "downgraded": 0,
            "stale_archived": 0,
            "expired_hyp_archived": 0,
            "details": [],
        }

        # ── 1. 合併冗餘結晶（每次最多 5 對）──
        redundancy = report.get("redundancy", [])
        merge_limit = 5
        for pair in redundancy[:merge_limit]:
            cuid_a = pair.get("cuid_a", "")
            cuid_b = pair.get("cuid_b", "")
            similarity = pair.get("similarity", 0)

            if not cuid_a or not cuid_b:
                continue
            if cuid_a not in self._crystals or cuid_b not in self._crystals:
                continue
            if similarity < SIMILARITY_MERGE_THRESHOLD:
                continue

            # 生成新 CUID
            crystal_a = self._crystals[cuid_a]
            new_cuid = self._generate_cuid(crystal_a.crystal_type)

            try:
                merged = self._recrystallizer.merge_crystals(
                    cuid_a, cuid_b, new_cuid
                )
                if merged:
                    # 將合併結果加入晶格
                    merged.ri_score = ResonanceCalculator.calculate(merged)
                    self._crystals[new_cuid] = merged
                    # 舊結晶移入歸檔
                    if cuid_a in self._crystals:
                        self._archive[cuid_a] = self._crystals.pop(cuid_a)
                    if cuid_b in self._crystals:
                        self._archive[cuid_b] = self._crystals.pop(cuid_b)
                    actions["merged"] += 1
                    actions["details"].append(
                        f"合併: {cuid_a} + {cuid_b} → {new_cuid} "
                        f"(相似度 {similarity:.2f})"
                    )
            except Exception as e:
                logger.warning(f"再結晶合併失敗 {cuid_a}+{cuid_b}: {e}")

        # ── 2. 升級 Hypothesis → Pattern（成功 3+ 次）──
        upgrade_limit = 10
        for cuid in report.get("upgrade_candidates", [])[:upgrade_limit]:
            if cuid not in self._crystals:
                continue
            crystal = self._crystals[cuid]
            old_type = crystal.crystal_type
            if self._recrystallizer.upgrade_crystal(cuid):
                actions["upgraded"] += 1
                actions["details"].append(
                    f"升級: {cuid} | {old_type} → {crystal.crystal_type}"
                )

        # ── 3. 降級 Insight → Pattern（反證 2+ 次）──
        downgrade_limit = 5
        for cuid in report.get("downgrade_candidates", [])[:downgrade_limit]:
            if cuid not in self._crystals:
                continue
            crystal = self._crystals[cuid]
            old_type = crystal.crystal_type
            if self._recrystallizer.downgrade_crystal(
                cuid, reason="反證次數達到閾值"
            ):
                actions["downgraded"] += 1
                actions["details"].append(
                    f"降級: {cuid} | {old_type} → {crystal.crystal_type}"
                )

        # ── 4. 歸檔過期結晶（RI < 0.05 且 90+ 天未引用）──
        for cuid in report.get("stale", []):
            if cuid not in self._crystals:
                continue
            self._recrystallizer.archive_crystal(cuid)
            self._archive[cuid] = self._crystals.pop(cuid)
            actions["stale_archived"] += 1

        # ── 5. 歸檔過期 Hypothesis（超過 30 天驗證窗口）──
        for cuid in report.get("expired_hypotheses", []):
            if cuid not in self._crystals:
                continue
            self._recrystallizer.archive_crystal(cuid)
            self._archive[cuid] = self._crystals.pop(cuid)
            actions["expired_hyp_archived"] += 1

        # 摘要
        total = sum(v for k, v in actions.items() if k != "details" and k != "summary")
        actions["summary"] = (
            f"合併{actions['merged']} 升級{actions['upgraded']} "
            f"降級{actions['downgraded']} 歸檔{actions['stale_archived'] + actions['expired_hyp_archived']}"
        )

        if total > 0:
            logger.info(
                f"再結晶自動執行完成 | {actions['summary']}"
            )
        else:
            logger.info("再結晶掃描完成，無需執行動作")

        return actions

    # ═══════════════════════════════════════════
    # 輔助 API
    # ═══════════════════════════════════════════

    def get_crystal(self, cuid: str) -> Optional[Crystal]:
        """取得指定結晶.

        Args:
            cuid: 結晶 CUID

        Returns:
            Crystal 實例，或 None
        """
        crystal = self._crystals.get(cuid)
        if crystal:
            return crystal
        return self._archive.get(cuid)

    def get_all_crystals(self, include_archived: bool = False) -> List[Crystal]:
        """取得所有結晶.

        Args:
            include_archived: 是否包含已歸檔的結晶

        Returns:
            結晶列表
        """
        crystals = [
            c for c in self._crystals.values() if not c.archived
        ]
        if include_archived:
            crystals.extend(self._archive.values())
        return crystals

    def record_success(self, cuid: str) -> None:
        """記錄結晶被成功應用一次（用於 Hypothesis 升級追蹤）.

        Args:
            cuid: 結晶 CUID
        """
        crystal = self._crystals.get(cuid)
        if crystal:
            crystal.success_count += 1
            crystal.reference_count += 1
            crystal.last_referenced = datetime.now().isoformat()
            crystal.ri_score = ResonanceCalculator.calculate(crystal)
            self._persist()

    def record_counter_evidence(self, cuid: str) -> None:
        """記錄結晶的反證（用於 Insight 降級追蹤）.

        Args:
            cuid: 結晶 CUID
        """
        crystal = self._crystals.get(cuid)
        if crystal:
            crystal.counter_evidence_count += 1
            crystal.updated_at = datetime.now().isoformat()
            self._persist()

    def get_neighbors(self, cuid: str, hops: int = 2) -> List[Crystal]:
        """取得指定結晶的鄰近結晶（預設 2-hop）.

        Args:
            cuid: 起點結晶 CUID
            hops: 最大跳數

        Returns:
            鄰近結晶列表
        """
        neighbor_cuids = self._dag.get_neighbors(cuid, hops=hops)
        return [
            self._crystals[c]
            for c in neighbor_cuids
            if c in self._crystals and not self._crystals[c].archived
        ]

    def get_crystal_count(self) -> int:
        """取得活躍結晶數量.

        Returns:
            活躍結晶數量
        """
        return sum(
            1 for c in self._crystals.values() if not c.archived
        )

    # ═══════════════════════════════════════════
    # DNA27 記憶整合
    # ═══════════════════════════════════════════

    def upgrade_from_memory(
        self,
        memory_layer: str,
        content: str,
        source_context: str = "",
    ) -> Optional[Crystal]:
        """從 DNA27 記憶層升級為結晶.

        升級路徑：
        - L0 (sensory/工作) -> Hypothesis
        - L1 (short-term/免疫) -> Lesson
        - L2 (working/事件) -> Pattern
        - L3 (long-term/技能) -> Insight

        Args:
            memory_layer: 記憶層標識（L0/L1/L2/L3）
            content: 記憶內容
            source_context: 來源上下文

        Returns:
            新建立的 Crystal，或 None
        """
        layer_type_map = {
            "L0": CRYSTAL_TYPE_HYPOTHESIS,
            "L1": CRYSTAL_TYPE_LESSON,
            "L2": CRYSTAL_TYPE_PATTERN,
            "L3": CRYSTAL_TYPE_INSIGHT,
        }

        crystal_type = layer_type_map.get(memory_layer)
        if not crystal_type:
            logger.warning(f"無法識別的記憶層: {memory_layer}")
            return None

        return self.crystallize(
            raw_material=content,
            source_context=f"DNA27 記憶升級 ({memory_layer}): {source_context}",
            crystal_type=crystal_type,
        )

    # ═══════════════════════════════════════════
    # 內部方法
    # ═══════════════════════════════════════════

    def _generate_cuid(self, crystal_type: str) -> str:
        """生成 CUID（Crystal Unique ID）.

        格式：KL-{INS|PAT|LES|HYP}-{0001}

        Args:
            crystal_type: 結晶類型

        Returns:
            新的 CUID 字串
        """
        type_abbr = CUID_TYPE_MAP.get(crystal_type, "HYP")

        # 遞增序號
        current = self._counters.get(type_abbr, 0) + 1
        self._counters[type_abbr] = current

        # 格式化為四位數零補齊
        cuid = f"KL-{type_abbr}-{current:04d}"

        # 持久化計數器
        self._store.save_counters(self._counters)

        return cuid

    def _persist(self) -> None:
        """持久化所有資料到磁碟."""
        try:
            self._store.save_crystals(self._crystals)
            self._store.save_links(self._dag.get_all_links())
            self._store.save_archive(self._archive)
        except AttributeError as e:
            logger.error(
                f"KnowledgeLattice._persist 方法名稱不匹配"
                f"（可能是 stale .pyc）: {e}"
            )
        except Exception as e:
            logger.error(f"KnowledgeLattice._persist 失敗: {e}")

    def _keyword_match_score(self, query: str, crystal: Crystal) -> float:
        """計算關鍵字匹配分數.

        檢查查詢字串中的詞彙是否出現在結晶的各個欄位中。

        Args:
            query: 查詢字串
            crystal: 目標結晶

        Returns:
            匹配分數 (0-1)
        """
        # 建立搜尋文本池
        search_pool = " ".join([
            crystal.g1_summary,
            " ".join(crystal.g2_structure),
            crystal.g3_root_inquiry,
            " ".join(crystal.g4_insights),
            " ".join(crystal.tags),
            crystal.domain,
        ]).lower()

        query_lower = query.lower()

        # 整個查詢字串的匹配
        if query_lower in search_pool:
            return 1.0

        # 逐詞匹配
        words = query_lower.split()
        if not words:
            return 0.0

        matched = sum(1 for w in words if w in search_pool)
        return matched / len(words)

    def _light_recrystallize_scan(self) -> None:
        """輕量再結晶掃描（每 20 顆結晶觸發）.

        僅偵測並記錄問題，不自動執行操作。
        """
        redundant = self._recrystallizer.detect_redundancy()
        upgrade = self._recrystallizer.detect_upgrade_candidates()
        expired = self._recrystallizer.detect_expired_hypotheses()

        if redundant or upgrade or expired:
            logger.info(
                f"輕量再結晶掃描結果 | "
                f"冗餘: {len(redundant)} | "
                f"升級候選: {len(upgrade)} | "
                f"過期假設: {len(expired)}"
            )

    # ── MemGPT-style Tiered Recall（分層結晶召回）──

    def recall_tiered(
        self,
        context: str,
        max_push: int = 10,
        budget_remaining: Optional[int] = None,
    ) -> List[Crystal]:
        """MemGPT 分層結晶召回 — Hot/Warm/Cold 三層策略.

        靈感來源：MemGPT 的 in-context / external / archival 記憶分層。
        將結晶依 RI 分為三層，以不同策略注入 context window：

        - Tier-0 (Hot): RI >= 0.7（CORE）→ 無條件注入（常駐 context）
        - Tier-1 (Warm): 0.2 <= RI < 0.7（ACTIVE）→ 語義搜尋後注入
        - Tier-2 (Cold): RI < 0.2 → 僅在顯式查詢時才拉取（此方法不處理）

        與原有 recall_with_chains 的差別：
        - recall_with_chains：所有結晶統一語義搜尋，高 RI 的不一定被選中
        - recall_tiered：先保證 Hot 結晶必定注入，再用剩餘名額搜尋 Warm 層

        Args:
            context: 查詢上下文
            max_push: 結晶注入上限（含 Hot + Warm）
            budget_remaining: 剩餘 token 預算（可選，用於動態調整）

        Returns:
            分層召回的結晶列表（Hot 在前，Warm 在後）
        """
        if not context or not context.strip():
            return []

        # Phase 1: 分類所有活躍結晶
        hot_crystals: List[Crystal] = []
        warm_cuids: Set[str] = set()

        for cuid, crystal in self._crystals.items():
            if crystal.archived:
                continue
            ri = ResonanceCalculator.calculate(crystal)
            crystal.ri_score = ri  # 順便更新快取

            if ri >= RI_CORE_THRESHOLD:
                hot_crystals.append(crystal)
            elif ri >= RI_ACTIVE_THRESHOLD:
                warm_cuids.add(cuid)

        # Phase 2: Hot 結晶無條件注入（按 RI 排序取 top）
        hot_crystals.sort(key=lambda c: c.ri_score, reverse=True)
        hot_budget = min(len(hot_crystals), max(1, max_push // 2))
        selected_hot = hot_crystals[:hot_budget]

        # Phase 3: 剩餘名額用語義搜尋 Warm 結晶
        remaining_slots = max_push - len(selected_hot)
        selected_warm: List[Crystal] = []

        if remaining_slots > 0 and warm_cuids:
            # 用 recall_with_chains 搜尋，再過濾只保留 Warm 層
            try:
                chain_results = self.recall_with_chains(
                    context=context,
                    max_push=remaining_slots * 2,  # 多取一些再過濾
                    chain_hops=1,
                    chain_types=["supports", "extends", "related"],
                )
            except Exception:
                logger.debug("recall_tiered: chain_recall fallback", exc_info=True)
                chain_results = self.recall(query=context, top_n=remaining_slots * 2)

            seen_hot = {c.cuid for c in selected_hot}
            for crystal in chain_results:
                if crystal.cuid in seen_hot:
                    continue
                if crystal.cuid in warm_cuids:
                    selected_warm.append(crystal)
                    if len(selected_warm) >= remaining_slots:
                        break

        results = selected_hot + selected_warm

        # 過濾低分結晶（與 brain.py 原有邏輯一致）
        results = [c for c in results if c.ri_score >= RI_ARCHIVE_THRESHOLD]

        logger.info(
            f"分層召回: Hot={len(selected_hot)} + "
            f"Warm={len(selected_warm)} = {len(results)} 顆 "
            f"(max_push={max_push}, "
            f"total_hot={len(hot_crystals)}, "
            f"total_warm={len(warm_cuids)})"
        )

        return results
