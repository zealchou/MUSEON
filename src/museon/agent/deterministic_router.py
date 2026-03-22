"""DeterministicRouter — 規則式任務分解器.

L3-A1: 取代 LLM Orchestrator 的確定性路由。
用規則式分解取代 Sonnet LLM 呼叫，消除 51% 的 JSON 解析失敗率。
LLM 降級為可選的 focus 描述填充（容錯，失敗用預設描述）。

設計原則：
- 確定性 > 靈活性（成功率 100% > LLM 的 49%）
- Skill 排序按「情緒先行 → 戰略 → 分析 → 執行」
- depth/model 由 RoutingSignal 決定，不依賴 LLM 判斷
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Skill 類別優先級（越小越先執行）──
_CATEGORY_PRIORITY = {
    # 情緒承接類：永遠排最前
    "resonance": 0,
    "shadow": 0,
    # 思維 / 哲學類
    "deep-think": 1,
    "dharma": 1,
    "philo-dialectic": 1,
    "query-clarity": 1,
    # 戰略 / 診斷類
    "master-strategy": 2,
    "roundtable": 2,
    "decision-tracker": 2,
    "business-12": 2,
    "ssa-consultant": 2,
    # 分析 / 研究類
    "dse": 3,
    "market-core": 3,
    "market-equity": 3,
    "market-crypto": 3,
    "market-macro": 3,
    "sentiment-radar": 3,
    "risk-matrix": 3,
    "investment-masters": 3,
    "env-radar": 3,
    "gap": 3,
    "report-forge": 3,
    # 設計 / 建構類
    "xmodel": 4,
    "pdeif": 4,
    "plan-engine": 4,
    "brand-identity": 4,
    "storytelling-engine": 4,
    # 執行 / 產出類
    "text-alchemy": 5,
    "novel-craft": 5,
    "c15": 5,
    "consultant-communication": 5,
    "aesthetic-sense": 5,
    "info-architect": 5,
    "acsf": 5,
    # 元認知 / 演化類
    "meta-learning": 6,
    "morphenix": 6,
    "eval-engine": 6,
    "wee": 6,
    "knowledge-lattice": 6,
    "sandbox-lab": 6,
    "user-model": 6,
    "system-health-check": 6,
    "qa-auditor": 6,
}

# 預設優先級（未列入的 Skill）
_DEFAULT_PRIORITY = 4


def decompose(
    user_request: str,
    matched_skills: List[Dict[str, Any]],
    routing_signal: Optional[Any] = None,
    max_tasks: int = 5,
) -> List[Dict[str, Any]]:
    """確定性任務分解.

    Args:
        user_request: 使用者原始訊息
        matched_skills: DNA27 匹配的 Skill 清單
        routing_signal: RoutingSignal（含 loop、max_push 等）
        max_tasks: 最大子任務數

    Returns:
        TaskPackage 相容的 dict 列表
    """
    # Step 1: 過濾非 worker 類 Skill
    worker_skills = [
        s for s in matched_skills
        if not s.get("always_on")
        and s.get("type") != "workflow"
    ]

    if not worker_skills:
        return []

    # Step 2: 排序——按類別優先級
    def _priority(skill: Dict) -> int:
        name = skill.get("name", "")
        return _CATEGORY_PRIORITY.get(name, _DEFAULT_PRIORITY)

    worker_skills.sort(key=_priority)

    # Step 3: 取 top-N（不超過 max_tasks）
    selected = worker_skills[:max_tasks]

    # Step 4: 決定 depth 和 model（由 RoutingSignal 驅動）
    loop = "EXPLORATION_LOOP"
    if routing_signal:
        loop = getattr(routing_signal, "loop", "EXPLORATION_LOOP")

    depth_map = {
        "FAST_LOOP": "quick",
        "EXPLORATION_LOOP": "standard",
        "SLOW_LOOP": "deep",
    }
    default_depth = depth_map.get(loop, "standard")

    model_map = {
        "FAST_LOOP": "haiku",
        "EXPLORATION_LOOP": "haiku",
        "SLOW_LOOP": "sonnet",
    }
    default_model = model_map.get(loop, "haiku")

    # Step 5: 產出 TaskPackage 相容 dict
    tasks = []
    for i, skill in enumerate(selected):
        name = skill.get("name", "unknown")
        desc = skill.get("description", "")

        # 深度推理類 Skill 強制 sonnet
        force_sonnet = name in {
            "master-strategy", "roundtable", "dse",
            "philo-dialectic", "report-forge",
        }

        tasks.append({
            "skill_name": name,
            "skill_focus": desc[:200] if desc else f"執行 {name} 分析",
            "skill_depth": default_depth,
            "expected_output": f"{name} 的分析結論",
            "execution_order": i,
            "depends_on": [],
            "model_preference": "sonnet" if force_sonnet else default_model,
        })

    logger.info(
        f"[DeterministicRouter] 分解完成: {len(tasks)} tasks "
        f"from {len(matched_skills)} matched, loop={loop}"
    )
    return tasks
