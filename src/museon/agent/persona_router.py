"""
MUSEON Persona Router v2.0 — 百合引擎（Baihe Engine）
AI 人格一致性決策引擎 - 4D+1 座標定位回應策略

v1.0: 三維路由（Energy × Intent → Persona）
v2.0: 四維+一路由（Energy × Intent × TopicDomain × LordInitiated → BaiheQuadrant）
      + 四階進諫階梯 + 冷卻機制
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class EnergyLevel(Enum):
    LOW = "L"
    MEDIUM = "M"
    HIGH = "H"
    HIGH_PRODUCTIVE = "H+"


class IntentType(Enum):
    EMOTIONAL = "T1"
    TECHNICAL = "T2"
    DECISION = "T3"
    EXPLORATION = "T4"


class PersonaMode(Enum):
    FRIEND = "F"
    COACH = "C"
    ADVISOR = "A"
    EXPERT = "E"


class TopicDomain(Enum):
    """主人領域強弱項分類"""
    STRENGTH = "strength"
    WEAKNESS = "weakness"
    UNKNOWN = "unknown"


class BaiheQuadrant(Enum):
    """百合四象限 — 捭闔決策空間"""
    FULL_SUPPORT = "Q1"       # 強項+主動 → 全力輔助（不搶方向盤）
    PRECISE_ASSIST = "Q2"     # 弱項+主動 → 精準補位（白話翻譯）
    PROACTIVE_ADVISE = "Q3"   # 弱項+未問 → 主動進諫（溫和提醒）
    SILENT_OBSERVE = "Q4"     # 強項+未問 → 靜默觀察（只記不說）


@dataclass
class ResponseConfig:
    """回應配置規格"""
    energy: EnergyLevel
    intent: IntentType
    persona: PersonaMode
    max_length: Optional[int]
    required_elements: List[str]
    forbidden_elements: List[str]
    tone_guidance: str


@dataclass
class BaiheDecision:
    """百合引擎完整決策輸出"""
    quadrant: BaiheQuadrant
    topic_domain: TopicDomain
    lord_initiated: bool
    response_config: ResponseConfig
    advise_tier: int = 0            # 0=靜默, 1=暗示, 2=明示, 3=直諫
    should_advise: bool = False
    expression_mode: str = "silent_presence"  # parallel_staff/translator/loyal_counsel/silent_presence

class PersonaRouter:
    """人格路由決策引擎"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path(__file__).parent / "../../data/workspace/persona_router.json"
        self.config = self._load_config()
        
        # 能量偵測關鍵詞
        self.low_energy_signals = [
            '唉', '嘆', '啊', '算了', '不知道', '怎麼辦', '好累',
            '沒力', '崩潰', '撐不下去', '放棄', '沒用', '絕望', '完了', '死了'
        ]
        
        self.high_energy_signals = [
            '我想要', '幫我設計', '我要做', '計畫', '策略', '系統',
            '框架', '全面', '完整', '詳細分析', '深度'
        ]
        
        # 意圖偵測模式
        self.intent_patterns = {
            IntentType.EMOTIONAL: ['感覺', '心情', '壓力', '焦慮', '困擾', '糾結', '煩惱', '好難', '好痛苦', '受不了', '很累', '很煩'],
            IntentType.TECHNICAL: ['怎麼做', '如何', '方法', '步驟', '教我', '解釋', '為什麼', '原理', '技術', '工具', '代碼', '程式'],
            IntentType.DECISION: ['選擇', '決定', '哪個好', '建議', '比較', '評估', '應該', '值得', '要不要', '選什麼'],
            IntentType.EXPLORATION: ['不確定', '模糊', '方向', '思考', '想法', '可能', '或許', '也許', '搞不清楚', '沒頭緒']
        }
    
    def _load_config(self) -> Dict:
        """加載配置文件"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def detect_energy(self, message: str, context: Dict = None) -> EnergyLevel:
        """偵測用戶能量狀態"""
        if context is None:
            context = {}
        
        message_lower = message.lower()
        
        # 檢查低能量訊號
        low_score = sum(1 for signal in self.low_energy_signals if signal in message_lower)
        
        # 檢查高能量訊號
        high_score = sum(1 for signal in self.high_energy_signals if signal in message_lower)
        
        # 長度和結構分析
        sentence_count = len([s for s in message.split('。') if s.strip()])
        word_count = len(message)
        
        # 時間因素
        is_late_night = context.get('is_late_night', False)
        
        # 綜合判斷
        if low_score >= 2 or (word_count < 20 and sentence_count <= 2):
            return EnergyLevel.LOW
        elif high_score >= 2 and word_count > 100 and sentence_count > 3:
            if is_late_night and word_count > 200:
                return EnergyLevel.HIGH_PRODUCTIVE
            return EnergyLevel.HIGH
        else:
            return EnergyLevel.MEDIUM
    
    def detect_intent(self, message: str) -> List[IntentType]:
        """偵測互動意圖"""
        intents = []
        message_lower = message.lower()
        
        for intent_type, patterns in self.intent_patterns.items():
            if any(pattern in message_lower for pattern in patterns):
                intents.append(intent_type)
        
        # 預設為探索型
        if not intents:
            intents.append(IntentType.EXPLORATION)
        
        return intents
    
    def resolve_mixed_intents(self, intents: List[IntentType], 
                            energy: EnergyLevel) -> IntentType:
        """處理混合意圖"""
        if len(intents) == 1:
            return intents[0]
        
        # 低能量時強制優先情感需求
        if energy == EnergyLevel.LOW and IntentType.EMOTIONAL in intents:
            return IntentType.EMOTIONAL
        
        # 混合規則
        if IntentType.EMOTIONAL in intents and IntentType.TECHNICAL in intents:
            return IntentType.EMOTIONAL
        
        if IntentType.DECISION in intents and IntentType.EXPLORATION in intents:
            return IntentType.EXPLORATION
        
        # 三種以上選最底層
        if len(intents) >= 3:
            if IntentType.EMOTIONAL in intents:
                return IntentType.EMOTIONAL
            elif IntentType.EXPLORATION in intents:
                return IntentType.EXPLORATION
        
        return intents[0]
    
    def determine_persona(self, energy: EnergyLevel, 
                         intent: IntentType) -> PersonaMode:
        """決定最適合的姿態"""
        
        # 低能量強制朋友模式
        if energy == EnergyLevel.LOW:
            return PersonaMode.FRIEND
        
        # 中高能量根據意圖決定
        persona_map = {
            IntentType.EMOTIONAL: PersonaMode.FRIEND,
            IntentType.TECHNICAL: PersonaMode.EXPERT,
            IntentType.DECISION: PersonaMode.ADVISOR,
            IntentType.EXPLORATION: PersonaMode.COACH
        }
        
        return persona_map.get(intent, PersonaMode.COACH)
    
    def generate_config(
        self, message: str, context: Dict = None,
        user_primals: Optional[Dict[str, int]] = None,
    ) -> ResponseConfig:
        """生成完整的回應配置

        Args:
            message: 使用者訊息
            context: 上下文（可選）
            user_primals: 八原語維度 {primal_key: level(0-100)}（可選）
        """
        if context is None:
            context = {}

        # 三維分析
        energy = self.detect_energy(message, context)
        intents = self.detect_intent(message)
        primary_intent = self.resolve_mixed_intents(intents, energy)
        persona = self.determine_persona(energy, primary_intent)

        # 根據組合生成具體配置
        config = self._build_response_config(energy, primary_intent, persona)

        # ── v10.5 八原語調節回應深度/風格 ──
        if user_primals:
            self._apply_primal_adjustments(config, user_primals)

        return config

    def _apply_primal_adjustments(
        self, config: ResponseConfig,
        user_primals: Dict[str, int],
    ) -> None:
        """根據八原語調整回應配置（就地修改）.

        - curiosity 高 → max_length 上調 1.5 倍，鼓勵深入探索
        - boundary 高 → max_length 下調 0.7 倍，不追問太多
        - emotion_pattern 高 → 先同理再分析
        - action_power 高 → 直接給行動方案
        """
        curiosity = user_primals.get("curiosity", 0)
        boundary = user_primals.get("boundary", 0)
        emotion = user_primals.get("emotion_pattern", 0)
        action = user_primals.get("action_power", 0)

        # curiosity 高（>60）→ 鼓勵深度展開
        if curiosity > 60 and config.max_length is not None:
            config.max_length = int(config.max_length * 1.5)
            if "鼓勵深入探索" not in config.tone_guidance:
                config.tone_guidance += "，鼓勵深入探索"

        # boundary 高（>60）→ 精簡回應，不追問
        if boundary > 60:
            if config.max_length is not None:
                config.max_length = int(config.max_length * 0.7)
            if "不要追問太多" not in config.forbidden_elements:
                config.forbidden_elements.append("不要追問太多")

        # emotion_pattern 高（>60）→ 先同理再分析
        if emotion > 60:
            if "先同理再分析" not in config.required_elements:
                config.required_elements.insert(0, "先同理再分析")

        # action_power 高（>60）→ 直接給行動方案
        if action > 60:
            if "直接給行動方案" not in config.tone_guidance:
                config.tone_guidance += "，直接給行動方案"
    
    def _build_response_config(self, energy: EnergyLevel, 
                              intent: IntentType, 
                              persona: PersonaMode) -> ResponseConfig:
        """建立回應配置"""
        
        # 低能量配置
        if energy == EnergyLevel.LOW:
            return ResponseConfig(
                energy=energy,
                intent=intent,
                persona=PersonaMode.FRIEND,
                max_length=100,
                required_elements=["接住狀態", "簡單反映"],
                forbidden_elements=["多步推演", "選項列表", "結構化框架"],
                tone_guidance="溫暖接納，不急著分析"
            )
        
        # 中能量配置
        elif energy == EnergyLevel.MEDIUM:
            configs = {
                IntentType.EMOTIONAL: ResponseConfig(
                    energy=energy,
                    intent=intent,
                    persona=PersonaMode.FRIEND,
                    max_length=200,
                    required_elements=["接住", "反映", "開放問題"],
                    forbidden_elements=["直接給解法"],
                    tone_guidance="先同頻，等準備好再引導"
                ),
                IntentType.TECHNICAL: ResponseConfig(
                    energy=energy,
                    intent=intent,
                    persona=PersonaMode.EXPERT,
                    max_length=300,
                    required_elements=["比喻建立直覺", "技術細節", "確認理解"],
                    forbidden_elements=["純技術文件風格"],
                    tone_guidance="保留30%朋友感，專業但有溫度"
                ),
                IntentType.DECISION: ResponseConfig(
                    energy=energy,
                    intent=intent,
                    persona=PersonaMode.ADVISOR,
                    max_length=400,
                    required_elements=["2-3個選項", "甜頭+代價", "決策框架"],
                    forbidden_elements=["單一最佳解"],
                    tone_guidance="結構化分析，保留選擇權"
                ),
                IntentType.EXPLORATION: ResponseConfig(
                    energy=energy,
                    intent=intent,
                    persona=PersonaMode.COACH,
                    max_length=250,
                    required_elements=["映射混亂", "引導聚焦", "小範圍試探"],
                    forbidden_elements=["假裝問題清晰", "直接推演"],
                    tone_guidance="引導式提問，幫助釐清"
                )
            }
            return configs.get(intent, configs[IntentType.EXPLORATION])
        
        # 高能量配置
        else:  # HIGH or HIGH_PRODUCTIVE
            if intent == IntentType.TECHNICAL:
                persona_mode = PersonaMode.EXPERT
            elif intent == IntentType.DECISION:
                persona_mode = PersonaMode.ADVISOR
            else:
                persona_mode = PersonaMode.COACH
            
            return ResponseConfig(
                energy=energy,
                intent=intent,
                persona=persona_mode,
                max_length=None,
                required_elements=["完整框架", "深度分析"],
                forbidden_elements=["展示複雜度而非實用性"],
                tone_guidance="允許完整推演，以有用為邊界"
            )
    
    # ═══════════════════════════════════════════
    # 百合引擎（Baihe Engine）— v2.0 四象限軍師路由
    # ═══════════════════════════════════════════

    def detect_topic_domain(
        self, message: str, lord_profile: Dict[str, Any],
    ) -> TopicDomain:
        """根據 lord_profile 的 domain_keywords 偵測訊息涉及的領域強弱項."""
        domains = lord_profile.get("domains", {})
        keywords_map = lord_profile.get("domain_keywords", {})
        msg_lower = message.lower()

        matched: List[Tuple[str, str]] = []  # [(domain_key, classification)]
        for domain_key, kw_list in keywords_map.items():
            for kw in kw_list:
                if kw.lower() in msg_lower:
                    classification = (
                        domains.get(domain_key, {}).get("classification", "unknown")
                    )
                    matched.append((domain_key, classification))
                    break

        if not matched:
            return TopicDomain.UNKNOWN

        # 多領域命中時：weakness 優先（弱項補位更重要）
        classifications = [c for _, c in matched]
        if "weakness" in classifications:
            return TopicDomain.WEAKNESS
        if "strength" in classifications:
            return TopicDomain.STRENGTH
        # unknown 領域命中 = 有 keyword 匹配但領域未分類
        # 視為 WEAKNESS 讓 Museon 有機會主動輔助（而非沉默）
        if matched:
            return TopicDomain.WEAKNESS
        return TopicDomain.UNKNOWN

    def detect_lord_initiated(self, message: str) -> bool:
        """判斷主人是否主動發問（True=主動問, False=被動/陳述）."""
        # 問號結尾 = 主動問
        stripped = message.strip()
        if stripped.endswith("?") or stripped.endswith("？"):
            return True
        # 求助型關鍵字
        ask_signals = [
            "怎麼", "如何", "可以嗎", "教我", "幫我", "能不能",
            "是什麼", "為什麼", "有沒有", "什麼是", "可不可以",
        ]
        msg_lower = message.lower()
        return any(s in msg_lower for s in ask_signals)

    def baihe_decide(
        self,
        message: str,
        context: Dict[str, Any],
        lord_profile: Dict[str, Any],
        user_primals: Optional[Dict[str, int]] = None,
    ) -> BaiheDecision:
        """百合引擎完整決策 — 4D+1 路由.

        四維度：Energy × Intent × TopicDomain × LordInitiated
        +1：進諫階梯（僅 Q3 啟動）

        Returns:
            BaiheDecision 包含象限、表達模式、進諫等級
        """
        # 1. 基礎 3D 路由
        energy = self.detect_energy(message, context)
        intents = self.detect_intent(message)
        primary_intent = self.resolve_mixed_intents(intents, energy)
        persona = self.determine_persona(energy, primary_intent)
        config = self._build_response_config(energy, primary_intent, persona)

        if user_primals:
            self._apply_primal_adjustments(config, user_primals)

        # 2. 新增維度：領域偵測 + 主動判斷
        topic_domain = self.detect_topic_domain(message, lord_profile)
        lord_initiated = self.detect_lord_initiated(message)

        # 3. 四象限決策
        if lord_initiated:
            if topic_domain == TopicDomain.WEAKNESS:
                quadrant = BaiheQuadrant.PRECISE_ASSIST    # Q2
            else:
                quadrant = BaiheQuadrant.FULL_SUPPORT      # Q1（強項或未知）
        else:
            if topic_domain == TopicDomain.WEAKNESS:
                quadrant = BaiheQuadrant.PROACTIVE_ADVISE   # Q3
            else:
                quadrant = BaiheQuadrant.SILENT_OBSERVE     # Q4（強項或未知）

        # 4. 進諫階梯（僅 Q3）
        should_advise = False
        advise_tier = 0
        if quadrant == BaiheQuadrant.PROACTIVE_ADVISE:
            should_advise, advise_tier, _reason = self._check_advise_ladder(
                lord_profile, energy,
            )
            if not should_advise:
                # 進諫條件不成立 → 降級為靜默觀察
                quadrant = BaiheQuadrant.SILENT_OBSERVE

        # 5. 表達模式映射
        expression_map = {
            BaiheQuadrant.FULL_SUPPORT: "parallel_staff",     # 並肩參謀
            BaiheQuadrant.PRECISE_ASSIST: "translator",       # 白話翻譯官
            BaiheQuadrant.PROACTIVE_ADVISE: "loyal_counsel",  # 忠臣進諫
            BaiheQuadrant.SILENT_OBSERVE: "silent_presence",  # 存在不干擾
        }
        expression_mode = expression_map[quadrant]

        # 6. 調整 ResponseConfig
        self._apply_baihe_adjustment(config, quadrant, should_advise)

        logger.info(
            f"百合引擎: {quadrant.value}({quadrant.name}) "
            f"domain={topic_domain.value} initiated={lord_initiated} "
            f"advise_tier={advise_tier} expression={expression_mode}"
        )

        return BaiheDecision(
            quadrant=quadrant,
            topic_domain=topic_domain,
            lord_initiated=lord_initiated,
            response_config=config,
            advise_tier=advise_tier,
            should_advise=should_advise,
            expression_mode=expression_mode,
        )

    def _check_advise_ladder(
        self, lord_profile: Dict[str, Any], energy: EnergyLevel,
    ) -> Tuple[bool, int, str]:
        """四階進諫階梯 + 冷卻檢查.

        Returns:
            (should_advise, tier, reason)
            tier: 0=靜默, 1=暗示, 2=明示, 3=直諫
        """
        cooldown = lord_profile.get("advise_cooldown", {})
        max_per_session = cooldown.get("max_per_session", 3)
        session_count = cooldown.get("session_advise_count", 0)
        cooldown_minutes = cooldown.get("cooldown_minutes", 30)
        last_ts = cooldown.get("last_advise_ts")

        # 冷卻中 → 不進諫
        if last_ts:
            try:
                last_dt = datetime.fromisoformat(last_ts)
                elapsed = (datetime.now() - last_dt).total_seconds() / 60
                if elapsed < cooldown_minutes:
                    return (False, 0, f"冷卻中（{elapsed:.0f}/{cooldown_minutes}分鐘）")
            except (ValueError, TypeError):
                pass

        # 達到 session 上限
        if session_count >= max_per_session:
            return (False, 0, f"已達 session 上限（{session_count}/{max_per_session}）")

        # 低能量 → 不進諫（能量守護）
        if energy == EnergyLevel.LOW:
            return (False, 0, "低能量，不進諫")

        # 中能量 → Tier 1 暗示
        if energy == EnergyLevel.MEDIUM:
            return (True, 1, "中能量，暗示")

        # 高能量 → Tier 2 明示 / Tier 3 直諫（根據重複盲點）
        # TODO Phase 1+: 加入重複盲點偵測，目前固定 Tier 2
        return (True, 2, "高能量，明示")

    def _apply_baihe_adjustment(
        self,
        config: ResponseConfig,
        quadrant: BaiheQuadrant,
        should_advise: bool,
    ) -> None:
        """根據百合象限調整 ResponseConfig（就地修改）."""
        if quadrant == BaiheQuadrant.FULL_SUPPORT:
            # Q1: 不搶方向盤，跟隨主人節奏
            config.tone_guidance += "，以配角姿態輔助，不主導方向"
            if "不搶主人結論" not in config.forbidden_elements:
                config.forbidden_elements.append("不搶主人結論")

        elif quadrant == BaiheQuadrant.PRECISE_ASSIST:
            # Q2: 白話翻譯，降低焦慮
            config.tone_guidance += "，用白話翻譯專業概念，降低焦慮感"
            if "白話比喻優先" not in config.required_elements:
                config.required_elements.insert(0, "白話比喻優先")

        elif quadrant == BaiheQuadrant.PROACTIVE_ADVISE and should_advise:
            # Q3: 溫和進諫
            config.tone_guidance += "，溫和提醒潛在風險，附退路"
            if "先同理再建議" not in config.required_elements:
                config.required_elements.insert(0, "先同理再建議")
            if "保留主人退路" not in config.required_elements:
                config.required_elements.append("保留主人退路")

        elif quadrant == BaiheQuadrant.SILENT_OBSERVE:
            # Q4: 極簡存在
            if config.max_length is not None:
                config.max_length = min(config.max_length, 80)
            else:
                config.max_length = 80
            config.tone_guidance = "極簡回應，存在但不干擾"
            config.forbidden_elements.append("主動展開分析")

    def check_kernel_constraints(self, response_draft: str) -> List[str]:
        """檢查是否違反核心護欄"""
        violations = []
        
        # 檢查主權保護
        if "你應該" in response_draft or "你必須" in response_draft:
            violations.append("❌ 違反主權保護：避免指令式語言")
        
        # 檢查認知誠實
        if "絕對" in response_draft or "一定" in response_draft:
            violations.append("❌ 違反認知誠實：過度確定")
        
        return violations

# 使用範例
if __name__ == "__main__":
    router = PersonaRouter()
    
    test_cases = [
        ("唉，我不知道該怎麼辦，好累啊", {"is_late_night": False}),
        ("你能教我怎麼寫 Python 嗎？我是新手", {"is_late_night": False}),
        ("我要選擇跳槽還是創業，你覺得哪個比較好？", {"is_late_night": False}),
    ]
    
    for message, context in test_cases:
        print(f"\n📝 輸入: {message}")
        config = router.generate_config(message, context)
        print(f"   能量: {config.energy.value}")
        print(f"   意圖: {config.intent.value}")
        print(f"   姿態: {config.persona.value}")
        print(f"   指導: {config.tone_guidance}")
