"""PrimalDetector — 八原語向量語義偵測引擎 v1.0.

用向量語義匹配取代純關鍵字啟發式，偵測使用者訊息中的八原語維度。

偵測流程：
  1. 使用者訊息 → bge-zh embedding
  2. Qdrant cosine search（primals collection）
  3. score > 0.35 → 匹配到原語
  4. MoE 聚合：同一原語多次命中時 主分 + 次分 × 0.3

設計原則：
  - 保留關鍵字作為 fallback（Qdrant 不可用時降級）
  - 純 Python <50ms（向量搜尋 + 聚合）
  - 完整 graceful degradation
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 八原語定義 + 典型表達語料庫
# ═══════════════════════════════════════════

PRIMAL_KEYS = [
    "aspiration",          # 渴望/願景
    "accumulation",        # 累積/沉澱
    "action_power",        # 行動力
    "curiosity",           # 好奇心
    "emotion_pattern",     # 情緒模式
    "blindspot",           # 盲點覺察
    "boundary",            # 邊界感
    "relationship_depth",  # 關係深度
]

# 每個原語的語義描述（供注入使用）
PRIMAL_DESCRIPTIONS: Dict[str, str] = {
    "aspiration": "渴望與願景——對未來的想像、目標設定、夢想追求",
    "accumulation": "累積與沉澱——持續投入、基礎建設、長期堅持",
    "action_power": "行動力——執行意願、動手做、從想法到行動的轉化",
    "curiosity": "好奇心——探索慾望、深入研究、追問為什麼",
    "emotion_pattern": "情緒模式——情緒敏感度、情緒辨識、情緒處理",
    "blindspot": "盲點覺察——自我反省、看見自己看不見的、接受反饋",
    "boundary": "邊界感——個人界限、保護自己、知道什麼不要",
    "relationship_depth": "關係深度——人際連結、信任建立、脆弱展露",
}

# 語義偵測語料庫：每個原語 15-20 條典型中文表達
# 這些語句會被索引到 Qdrant primals collection
PRIMAL_UTTERANCES: Dict[str, List[str]] = {
    "aspiration": [
        "我想成為一個更好的人",
        "我的夢想是有一天能改變世界",
        "我一直在想未來五年要做什麼",
        "我希望能達到更高的成就",
        "我有一個很大的目標想實現",
        "如果可以的話我想做點有意義的事",
        "我想像中理想的生活是這樣的",
        "我渴望一個不同的未來",
        "我一直在規劃下一步要往哪走",
        "我想找到自己真正的使命",
        "我對未來有很多想像和期待",
        "我的願景是建立一個什麼樣的東西",
        "我想突破現在的瓶頸到達新的層次",
        "我對自己有很高的期許",
        "我夢想著有一天能實現這個計畫",
    ],
    "accumulation": [
        "我覺得要慢慢來一步一步建立",
        "急不得要一點一滴累積",
        "我想先打好基礎再往上走",
        "持續做下去總會有成果的",
        "我相信厚積薄發的力量",
        "每天進步一點點就好",
        "基本功很重要不能跳過",
        "我已經持續做這件事很長一段時間了",
        "慢慢累積的東西最有價值",
        "我不急要穩紮穩打",
        "長期的投入一定會有回報",
        "要有耐心不能只看短期",
        "我每天都在練習",
        "把基礎打牢比什麼都重要",
        "我相信時間的複利效應",
    ],
    "action_power": [
        "我想馬上動手做",
        "別想太多先做再說",
        "我需要一個具體的行動計畫",
        "給我第一步我就能開始",
        "我已經等不及要開始了",
        "直接告訴我怎麼做",
        "我想立刻採取行動",
        "執行力是最重要的",
        "想再多不如動手試試",
        "我需要一個可以馬上執行的方案",
        "行動勝於空想",
        "我今天就要開始做這件事",
        "給我一個具體的下一步",
        "我不想再拖了",
        "我要把想法變成行動",
    ],
    "curiosity": [
        "這個很有趣我想知道更多",
        "為什麼會這樣可以深入解釋嗎",
        "我想研究一下這個主題",
        "背後的原理是什麼",
        "我好奇這是怎麼運作的",
        "可以再展開說說嗎",
        "這讓我想到另一個問題",
        "我想深入了解這個領域",
        "有沒有更多相關的資料",
        "這個概念很新奇我想探索看看",
        "為什麼大家都這樣做有沒有其他方式",
        "我對這個有很多疑問",
        "這個現象背後的機制是什麼",
        "我想從不同角度來理解這件事",
        "還有什麼我沒想到的",
        "我越想越覺得這很值得研究",
    ],
    "emotion_pattern": [
        "我最近情緒起伏很大",
        "不知道為什麼突然覺得很低落",
        "我發現自己對這件事有很強的情緒反應",
        "我需要先整理一下自己的感受",
        "這件事讓我很焦慮",
        "我覺得壓力很大喘不過氣",
        "我心裡有一種說不出的不安",
        "每次遇到這種情況我就會很煩躁",
        "我想我需要被理解",
        "這種感覺很複雜我說不清楚",
        "我發現自己的情緒模式",
        "我容易在壓力下崩潰",
        "有時候我會突然覺得很孤單",
        "我需要學會處理這種情緒",
        "我的心情就像在坐雲霄飛車",
    ],
    "blindspot": [
        "你覺得我有什麼盲點嗎",
        "我可能忽略了什麼",
        "我需要有人給我不同的觀點",
        "也許我一直都搞錯了方向",
        "我擔心自己看不見自己的問題",
        "有沒有什麼是我沒想到的",
        "我可能太主觀了",
        "別人對我的看法是什麼",
        "我想聽聽不同的聲音",
        "也許問題在我身上而不是別人",
        "我承認自己可能有偏見",
        "我需要一面鏡子照照自己",
        "我想知道自己的弱點在哪",
        "也許我一直在自我欺騙",
        "我開始反思自己的行為模式",
    ],
    "boundary": [
        "我覺得這件事不適合我",
        "我需要學會說不",
        "別人一直越界我很不舒服",
        "我要保護好自己的時間和精力",
        "這不是我的責任",
        "我覺得需要設立一些底線",
        "我不想被別人的期望綁架",
        "有些事情我不願意妥協",
        "我需要保持自己的界限",
        "我學會拒絕之後輕鬆很多",
        "不是所有要求都要答應",
        "我要先照顧好自己",
        "這超出我的能力範圍了",
        "我要明確哪些是我可以接受的",
        "我需要更好地保護自己",
    ],
    "relationship_depth": [
        "我想和對方建立更深的連結",
        "我覺得跟這個人很有默契",
        "我願意對你展露脆弱的一面",
        "信任是需要慢慢建立的",
        "我想更了解對方在想什麼",
        "這段關係對我來說很重要",
        "我害怕被拒絕所以不敢靠近",
        "我想學會更真誠地表達自己",
        "深層的對話讓我覺得被看見",
        "我渴望一種真正的連結而不是表面的",
        "我想讓對方知道我信任他",
        "我覺得我們之間可以更坦誠",
        "人與人之間的關係需要用心經營",
        "我希望能有一個可以說真心話的人",
        "我願意先踏出那一步",
    ],
}

# 關鍵字 fallback（Qdrant 不可用時降級使用）
# 複用 brain.py 原有的 _PRIMAL_KEYWORDS
PRIMAL_KEYWORDS: Dict[str, List[str]] = {
    "aspiration": [
        "目標", "夢想", "願景", "理想", "期望", "志向", "追求",
        "想成為", "未來想", "渴望",
    ],
    "accumulation": [
        "累積", "沉澱", "基礎", "一步一步", "持續", "耐心",
        "長期", "穩紮穩打", "持之以恆",
    ],
    "action_power": [
        "動手", "執行", "行動", "開始", "馬上", "立刻做",
        "第一步", "怎麼做", "開始做",
    ],
    "curiosity": [
        "好奇", "為什麼", "研究", "深入", "探索", "想知道",
        "有趣", "怎麼回事", "原理",
    ],
    "emotion_pattern": [
        "情緒", "感覺", "焦慮", "壓力", "低落", "煩躁",
        "不安", "崩潰", "心情",
    ],
    "blindspot": [
        "盲點", "忽略", "沒想到", "偏見", "反思", "自我檢討",
        "弱點", "看不見",
    ],
    "boundary": [
        "邊界", "底線", "拒絕", "說不", "保護自己", "不適合",
        "不願意", "界限",
    ],
    "relationship_depth": [
        "連結", "信任", "關係", "脆弱", "坦誠", "真心",
        "靠近", "默契",
    ],
}

# ═══════════════════════════════════════════
# 八原語 → SkillRouter primal_affinity 映射
# 每個技能會在 SKILL.md 宣告自己的 primal affinity
# 這裡提供預設映射供沒有宣告的技能參考
# ═══════════════════════════════════════════

DEFAULT_SKILL_PRIMAL_AFFINITY: Dict[str, Dict[str, float]] = {
    "dse": {"curiosity": 0.8, "action_power": 0.5},
    "xmodel": {"curiosity": 0.6, "action_power": 0.7, "aspiration": 0.5},
    "business-12": {"action_power": 0.6, "accumulation": 0.5, "aspiration": 0.4},
    "ssa-consultant": {"relationship_depth": 0.7, "action_power": 0.5, "boundary": 0.3},
    "resonance": {"emotion_pattern": 0.9, "relationship_depth": 0.6},
    "dharma": {"blindspot": 0.7, "emotion_pattern": 0.5, "curiosity": 0.4},
    "philo-dialectic": {"curiosity": 0.8, "blindspot": 0.6},
    "meta-learning": {"curiosity": 0.9, "accumulation": 0.7},
    "shadow": {"blindspot": 0.8, "boundary": 0.6, "relationship_depth": 0.4},
    "market-core": {"curiosity": 0.5, "action_power": 0.4},
    "master-strategy": {"action_power": 0.6, "aspiration": 0.5, "boundary": 0.4},
    "brand-identity": {"aspiration": 0.6, "accumulation": 0.4},
    "storytelling-engine": {"emotion_pattern": 0.5, "curiosity": 0.4},
    "text-alchemy": {"curiosity": 0.3, "action_power": 0.3},
    "morphenix": {"curiosity": 0.5, "accumulation": 0.4, "blindspot": 0.3},
    "wee": {"accumulation": 0.7, "action_power": 0.5},
    "roundtable": {"blindspot": 0.7, "curiosity": 0.5, "boundary": 0.4},
    "plan-engine": {"action_power": 0.6, "accumulation": 0.4},
}


# ═══════════════════════════════════════════
# PrimalDetector 偵測引擎
# ═══════════════════════════════════════════

class PrimalDetector:
    """八原語向量語義偵測引擎.

    Usage:
        detector = PrimalDetector(workspace=Path("data"))
        result = detector.detect("我很好奇這個是怎麼運作的")
        # result = {"curiosity": 72, "blindspot": 15, ...}
    """

    SCORE_THRESHOLD = 0.35
    SEARCH_LIMIT = 12
    # MoE 衰減係數：同一原語多次命中時 次分 × DECAY
    MOE_DECAY = 0.3

    def __init__(self, workspace, event_bus=None):
        """初始化 PrimalDetector.

        Args:
            workspace: 工作目錄（brain.data_dir）
            event_bus: EventBus 實例（可選）
        """
        from pathlib import Path
        self._workspace = Path(workspace)
        self._event_bus = event_bus
        self._vector_bridge = None
        self._indexed = False

    def _get_vector_bridge(self):
        """Lazy 取得 VectorBridge."""
        if self._vector_bridge is not None:
            return self._vector_bridge
        try:
            from museon.vector.vector_bridge import VectorBridge
            vb = VectorBridge(workspace=self._workspace)
            if vb.is_available():
                self._vector_bridge = vb
                return vb
        except Exception as e:
            logger.debug(f"[PRIMAL] VectorBridge 不可用: {e}")
        return None

    def ensure_indexed(self) -> int:
        """確保八原語語料已索引到 Qdrant.

        Returns:
            成功索引的語句數量
        """
        if self._indexed:
            return 0

        vb = self._get_vector_bridge()
        if vb is None:
            return 0

        indexed = 0
        try:
            for primal_key, utterances in PRIMAL_UTTERANCES.items():
                for idx, utt in enumerate(utterances):
                    doc_id = f"primal_{primal_key}__utt_{idx}"
                    metadata = {
                        "primal_key": primal_key,
                        "utterance_index": idx,
                    }
                    success = vb.index(
                        collection="primals",
                        doc_id=doc_id,
                        text=utt,
                        metadata=metadata,
                    )
                    if success:
                        indexed += 1

            self._indexed = True
            logger.info(f"[PRIMAL] 索引完成: {indexed} 筆語句 (8 原語)")
        except Exception as e:
            logger.warning(f"[PRIMAL] 索引失敗: {e}")

        return indexed

    def detect(self, message: str) -> Dict[str, int]:
        """偵測使用者訊息中的八原語維度.

        優先使用向量語義匹配，Qdrant 不可用時降級到關鍵字。

        Args:
            message: 使用者訊息

        Returns:
            {primal_key: level(0-100), ...} 只回傳 level > 0 的原語
        """
        if not message or not message.strip():
            return {}

        # 嘗試向量偵測
        vb = self._get_vector_bridge()
        if vb is not None and vb.is_available():
            result = self._detect_semantic(message, vb)
            if result:
                return result

        # Fallback: 關鍵字偵測
        return self._detect_keyword(message)

    def _detect_semantic(
        self, message: str, vb,
    ) -> Dict[str, int]:
        """向量語義偵測.

        搜尋 primals collection → MoE 聚合 → 轉換為 level(0-100)
        """
        try:
            hits = vb.search(
                "primals", message,
                limit=self.SEARCH_LIMIT,
                score_threshold=self.SCORE_THRESHOLD,
            )
            if not hits:
                return {}

            # 按 primal_key 聚合
            primal_hits: Dict[str, list] = {}
            for hit in hits:
                metadata = hit.get("metadata", {})
                pk = metadata.get("primal_key", "")
                if not pk:
                    # 從 doc_id 解析: primal_curiosity__utt_3
                    doc_id = hit.get("id", "")
                    if doc_id.startswith("primal_"):
                        pk = doc_id.split("__")[0].replace("primal_", "")
                if pk:
                    primal_hits.setdefault(pk, []).append(hit["score"])

            # MoE 聚合：主分 + 次分 × 0.3 衰減
            result: Dict[str, int] = {}
            for pk, scores in primal_hits.items():
                scores.sort(reverse=True)
                agg = scores[0]
                for s in scores[1:]:
                    agg += s * self.MOE_DECAY

                # 轉換為 0-100 level
                # cosine similarity 通常在 0.35-0.85 之間
                # 映射：0.35 → 15, 0.50 → 40, 0.65 → 65, 0.80 → 90
                level = int(min(100, max(0, (agg - 0.25) * 150)))
                if level > 0:
                    result[pk] = level

            if result:
                logger.debug(f"[PRIMAL] semantic detect: {result}")

            return result

        except Exception as e:
            logger.debug(f"[PRIMAL] semantic detect 失敗（降級到 keyword）: {e}")
            return {}

    def _detect_keyword(self, message: str) -> Dict[str, int]:
        """關鍵字 fallback 偵測."""
        result: Dict[str, int] = {}

        for pk, keywords in PRIMAL_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in message)
            if hits > 0:
                # 每命中一個關鍵字 +20, 上限 80（留空間給向量偵測的精確度）
                level = min(80, hits * 20)
                result[pk] = level

        # 問號計數 → 好奇心額外加分
        q_marks = message.count("？") + message.count("?")
        if q_marks >= 2:
            cur = result.get("curiosity", 0)
            result["curiosity"] = min(100, cur + q_marks * 10)

        if result:
            logger.debug(f"[PRIMAL] keyword detect (fallback): {result}")

        return result

    def get_skill_primal_affinity(self, skill_name: str) -> Dict[str, float]:
        """取得技能的八原語親和度.

        Args:
            skill_name: 技能名稱

        Returns:
            {primal_key: affinity(0.0-1.0), ...}
        """
        return DEFAULT_SKILL_PRIMAL_AFFINITY.get(skill_name, {})
