"""
Routing Bridge - 將 Persona Router 集成到 DNA27 核心層
"""

from museon.agent.persona_router import (
    PersonaRouter, EnergyLevel, IntentType, PersonaMode,
    TopicDomain, BaiheQuadrant, BaiheDecision,
)
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

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
    
    def route_response(
        self,
        user_message: str,
        context: dict = None,
        lord_profile: Optional[Dict[str, Any]] = None,
        user_primals: Optional[Dict[str, int]] = None,
    ) -> dict:
        """完整的路由決策流程（v2.0 百合引擎版）.

        Returns:
            dict with energy/intent/persona/tone/baihe fields
        """
        if context is None:
            context = {}

        self.conversation_turns += 1
        context['conversation_turn'] = self.conversation_turns

        # 百合引擎路由（如果有 lord_profile）
        baihe_decision: Optional[BaiheDecision] = None
        if lord_profile:
            try:
                baihe_decision = self.router.baihe_decide(
                    user_message, context, lord_profile, user_primals,
                )
            except Exception as e:
                logger.warning(f"百合引擎決策失敗（降級為基礎路由）: {e}")

        if baihe_decision:
            config = baihe_decision.response_config
        else:
            config = self.router.generate_config(user_message, context, user_primals)

        violations = self.router.check_kernel_constraints("")
        drift_warning = self._check_long_conversation_drift()

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
            'turn_count': self.conversation_turns,
        }

        # 百合引擎附加欄位
        if baihe_decision:
            routing_decision['baihe'] = {
                'quadrant': baihe_decision.quadrant.value,
                'quadrant_name': baihe_decision.quadrant.name,
                'topic_domain': baihe_decision.topic_domain.value,
                'lord_initiated': baihe_decision.lord_initiated,
                'advise_tier': baihe_decision.advise_tier,
                'should_advise': baihe_decision.should_advise,
                'expression_mode': baihe_decision.expression_mode,
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
