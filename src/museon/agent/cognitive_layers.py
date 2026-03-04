"""CognitiveLayers — MUSEON 認知三層形式化定義

MUSEON 的認知架構分為三個層級，對應不同的反應時間和決策深度：

┌─────────────────────────────────────────────────────────┐
│  System 0 (治理反射, < 10ms)                              │
│  硬編碼，不經 LLM，不可被 Morphenix 修改                    │
│                                                          │
│  governance.governor      — 三焦式分層治理主控制器           │
│  governance.immunity      — 先天+後天免疫引擎              │
│  governance.gateway_lock  — Gateway 唯一實例鎖             │
│  governance.telegram_guard — Telegram 通訊唯一性保證        │
│  governance.service_health — Docker 服務健康監控           │
│  governance.perception    — 望聞問切察覺引擎               │
│  governance.regulation    — PCT 調節引擎                   │
│  governance.context       — GovernanceContext 信號橋樑      │
│  governance.anima_bridge  — 治理→ANIMA 成長驅動            │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  System 1 (直覺, < 100ms)                                │
│  規則 + 啟發式，不經 LLM                                   │
│                                                          │
│  agent.intuition          — 直覺引擎                      │
│  agent.reflex_router      — DNA27 反射路由器（27 叢集）     │
│  agent.safety_anchor      — 安全錨點                      │
│  agent.skill_router       — 技能匹配路由                   │
│  security.sanitizer       — 輸入消毒                      │
│  agent.kernel_guard       — ANIMA 寫入保護                 │
│  agent.drift_detector     — ANIMA 漂移偵測                 │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  System 2 (大腦, 秒級)                                    │
│  需要 LLM，深度思考                                       │
│                                                          │
│  agent.brain              — 大腦核心（29 步 Pipeline）     │
│  agent.metacognition      — 元認知引擎                     │
│  agent.skill_router       — LLM-first 技能路由（v11）      │
│  agent.eval_engine        — 回答品質評分                   │
│  agent.knowledge_lattice  — 知識晶格                      │
│  agent.plan_engine        — 計畫引擎                      │
│  agent.soul_ring          — 靈魂年輪                      │
│                                                          │
│  45 原生 Skill = 開創者 Zeal Chou 的先天認知結晶            │
│  forged skills = MUSEON 自己學到的後天認知                  │
│                                                          │
│  * 原生 Skill 是系統的「先天智慧」，凝聚了開創者              │
│    周逸達（Zeal Chou）多年人生智慧的結晶。                   │
│    MUSEON 有能力反芻優化這些 Skill，使其持續進化。           │
└─────────────────────────────────────────────────────────┘

各層特性對比：
┌────────┬────────────┬──────────────┬───────────────────┐
│ 層級    │ 延遲       │ 可修改性      │ 失敗影響          │
├────────┼────────────┼──────────────┼───────────────────┤
│ Sys 0  │ < 10ms     │ 不可修改      │ 系統完整性受損     │
│ Sys 1  │ < 100ms    │ Morphenix L3 │ 路由品質下降       │
│ Sys 2  │ 秒級       │ Morphenix L2 │ 回答品質下降       │
└────────┴────────────┴──────────────┴───────────────────┘

Phase 3e — 2026-03-03
此模組為形式化定義，目前不被運行時引用。為 Phase 4 鋪路。
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet


class CognitiveLayer(Enum):
    """認知層級。"""

    SYSTEM_0 = "system_0"  # 治理反射（< 10ms）
    SYSTEM_1 = "system_1"  # 直覺（< 100ms）
    SYSTEM_2 = "system_2"  # 大腦（秒級）


# ─── 模組 → 認知層映射 ───

MODULE_LAYER_MAP: Dict[str, CognitiveLayer] = {
    # System 0: 治理反射
    "governance.governor": CognitiveLayer.SYSTEM_0,
    "governance.immunity": CognitiveLayer.SYSTEM_0,
    "governance.gateway_lock": CognitiveLayer.SYSTEM_0,
    "governance.telegram_guard": CognitiveLayer.SYSTEM_0,
    "governance.service_health": CognitiveLayer.SYSTEM_0,
    "governance.perception": CognitiveLayer.SYSTEM_0,
    "governance.regulation": CognitiveLayer.SYSTEM_0,
    "governance.context": CognitiveLayer.SYSTEM_0,
    "governance.anima_bridge": CognitiveLayer.SYSTEM_0,
    # System 1: 直覺
    "agent.intuition": CognitiveLayer.SYSTEM_1,
    "agent.reflex_router": CognitiveLayer.SYSTEM_1,
    "agent.safety_anchor": CognitiveLayer.SYSTEM_1,
    "agent.skill_router": CognitiveLayer.SYSTEM_1,
    "security.sanitizer": CognitiveLayer.SYSTEM_1,
    "agent.kernel_guard": CognitiveLayer.SYSTEM_1,
    "agent.drift_detector": CognitiveLayer.SYSTEM_1,
    # System 2: 大腦
    "agent.brain": CognitiveLayer.SYSTEM_2,
    "agent.metacognition": CognitiveLayer.SYSTEM_2,
    "agent.eval_engine": CognitiveLayer.SYSTEM_2,
    "agent.knowledge_lattice": CognitiveLayer.SYSTEM_2,
    "agent.plan_engine": CognitiveLayer.SYSTEM_2,
    "agent.soul_ring": CognitiveLayer.SYSTEM_2,
}

# ─── 不可修改的模組集合（Morphenix 保護）───

IMMUTABLE_MODULES: FrozenSet[str] = frozenset(
    module
    for module, layer in MODULE_LAYER_MAP.items()
    if layer == CognitiveLayer.SYSTEM_0
)


def get_layer(module_path: str) -> CognitiveLayer:
    """查詢模組所屬的認知層級。

    Args:
        module_path: 模組路徑（如 "governance.governor"）

    Returns:
        CognitiveLayer，未知模組預設歸類為 SYSTEM_2
    """
    return MODULE_LAYER_MAP.get(module_path, CognitiveLayer.SYSTEM_2)


def is_immutable(module_path: str) -> bool:
    """檢查模組是否不可被 Morphenix 修改。"""
    return module_path in IMMUTABLE_MODULES
