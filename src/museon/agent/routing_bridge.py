"""
Routing Bridge - 將 Persona Router 集成到 DNA27 核心層
"""

from persona_router import PersonaRouter, EnergyLevel, IntentType, PersonaMode
import json
from pathlib import Path

class RoutingBridge:
    """將 Router 決策與 DNA27 核心層連接的橋樑"""
    
    def __init__(self):
        self.router = PersonaRouter()
        self.dna27_kernels = [
            "主權保護 - 不替對方做最終選擇",
            "認知誠實 - 不確定就標記",
            "能量守護 - 低能量不逼行動",
            "長期一致 - 不以短期討好換長期一致性",
            "代價透明 - 甜頭和風險必須同框"
        ]
        
        # 會話歷史追蹤（用於檢測長對話漂移）
        self.conversation_turns = 0
        self.last_energy_detected = None
        self.topic_count = 0
    
    def route_response(self, user_message: str, context: dict = None) -> dict:
        """
        完整的路由決策流程
        
        返回：
        {
            'config': ResponseConfig,
            'kernel_violations': List[str],
            'routing_decision': str,
            'instructions': dict
        }
        """
        if context is None:
            context = {}
        
        # 追蹤對話輪數（用於長對話檢測）
        self.conversation_turns += 1
        context['conversation_turn'] = self.conversation_turns
        
        # 生成路由配置
        config = self.router.generate_config(user_message, context)
        
        # 檢查護欄違反
        violations = self.router.check_kernel_constraints("")  # 實際檢查會在生成回應後進行
        
        # 檢測長對話漂移
        drift_warning = self._check_long_conversation_drift()
        
        # 組織最終決策
        routing_decision = {
            'energy': config.energy.value,
            'intent': config.intent.value,
            'persona': config.persona.value,
            'tone': config.tone_guidance,
            'max_tokens': config.max_length,
            'required': config.required_elements,
            'forbidden': config.forbidden_elements,
            'kernel_violations': violations,
            'drift_warning': drift_warning,
            'turn_count': self.conversation_turns
        }
        
        return routing_decision
    
    def _check_long_conversation_drift(self) -> str:
        """檢測長對話中的人格漂移"""
        if self.conversation_turns > 15:
            return "⚠️ 檢測到長對話（>15輪）- 建議重新錨定核心問題"
        return None
    
    def generate_response_instruction(self, routing_decision: dict) -> str:
        """根據路由決策生成具體的回應指令"""
        
        instructions = []
        
        # 能量層指令
        if routing_decision['energy'] == 'L':
            instructions.append("🔴 低能量模式：")
            instructions.append("  1. 第一句必須接住情緒")
            instructions.append("  2. 禁止推演多步")
            instructions.append("  3. 100字以內")
        
        elif routing_decision['energy'] == 'M':
            instructions.append("🟡 中能量模式：")
            if routing_decision['intent'] == 'T1':
                instructions.append("  1. 先同頻再引導")
                instructions.append("  2. 問開放問題")
                instructions.append("  3. 200字以內")
            elif routing_decision['intent'] == 'T2':
                instructions.append("  1. 先比喻後技術")
                instructions.append("  2. 每個專詞都解釋")
                instructions.append("  3. 300字以內")
            elif routing_decision['intent'] == 'T3':
                instructions.append("  1. 給2-3個選項")
                instructions.append("  2. 甜頭+代價同框")
                instructions.append("  3. 400字以內")
            elif routing_decision['intent'] == 'T4':
                instructions.append("  1. 映射混亂")
                instructions.append("  2. 引導聚焦")
                instructions.append("  3. 250字以內")
        
        elif routing_decision['energy'] in ['H', 'H+']:
            instructions.append("🟢 高能量模式：")
            instructions.append("  1. 允許完整框架")
            instructions.append("  2. 深度分析")
            instructions.append("  3. 以有用為邊界")
        
        # 姿態指令
        persona_guidance = {
            'F': "  姿態：朋友 - 同頻、接住、不評判",
            'C': "  姿態：教練 - 問問題、引導、不直接給解",
            'A': "  姿態：顧問 - 診斷、框架、選項評估",
            'E': "  姿態：專家 - 精確、有來源、標記不確定"
        }
        instructions.append(persona_guidance.get(routing_decision['persona'], ""))
        
        # 護欄提醒
        if routing_decision['kernel_violations']:
            instructions.append("\n⚠️ 護欄檢查:")
            for violation in routing_decision['kernel_violations']:
                instructions.append(f"  {violation}")
        
        if routing_decision['drift_warning']:
            instructions.append(f"\n{routing_decision['drift_warning']}")
        
        return "\n".join(instructions)

# 測試
if __name__ == "__main__":
    bridge = RoutingBridge()
    
    test_message = "唉，我不知道該怎麼辦，好累啊"
    decision = bridge.route_response(test_message)
    
    print("路由決策結果：")
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    
    print("\n生成的回應指令：")
    print(bridge.generate_response_instruction(decision))
