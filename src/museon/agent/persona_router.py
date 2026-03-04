"""
MUSEON Persona Router v1.0
AI 人格一致性決策引擎 - 三維座標定位回應策略
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass

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
    
    def generate_config(self, message: str, context: Dict = None) -> ResponseConfig:
        """生成完整的回應配置"""
        if context is None:
            context = {}
        
        # 三維分析
        energy = self.detect_energy(message, context)
        intents = self.detect_intent(message)
        primary_intent = self.resolve_mixed_intents(intents, energy)
        persona = self.determine_persona(energy, primary_intent)
        
        # 根據組合生成具體配置
        config = self._build_response_config(energy, primary_intent, persona)
        
        return config
    
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
