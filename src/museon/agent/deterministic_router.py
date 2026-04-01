"""DeterministicRouter — 規則式任務分解器.

L3-A1: 取代 LLM Orchestrator 的確定性路由。
用規則式分解取代 Sonnet LLM 呼叫，消除 51% 的 JSON 解析失敗率。
LLM 降級為可選的 focus 描述填充（容錯，失敗用預設描述）。

設計原則：
- 確定性 > 靈活性（成功率 100% > LLM 的 49%）
- Skill 排序按 Hub 優先級（情緒先行 → 戰略 → 分析 → 執行）
- depth/model 由 is_simple 旗標決定：簡單 → haiku/quick，否則 → sonnet/standard
- 優先級/模型偏好/依賴關係由 Skill Manifest 驅動，非硬編碼

v1.1: 三項外部化——
  1. 優先級由 hub 欄位映射（不再硬編碼 Skill 名稱）
  2. model_preference 由 Manifest 欄位驅動
  3. depends_on 由 io.inputs 推導
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ── Hub → 優先級映射（越小越先執行）──
# 語義順序：情緒承接 → 思維品質 → 戰略診斷 → 市場分析 → 設計建構
#           → 語言產出 → 技術產品 → 演化治理 → 工作流範本
_HUB_PRIORITY = {
    "thinking": 0,    # 情緒承接 + 思維類（resonance, dharma, shadow...）
    "core": 1,        # 核心中間件（deep-think, query-clarity...）
    "business": 2,    # 戰略 / 診斷類（master-strategy, business-12...）
    "market": 3,      # 分析 / 研究類（market-core, risk-matrix...）
    "creative": 4,    # 語言 / 美感 / 產出類（text-alchemy, c15...）
    "product": 5,     # 技術 / 產品類（dse, acsf, report-forge...）
    "evolution": 6,   # 演化 / 治理類（sandbox-lab, qa-auditor...）
    "infra": 7,       # 基礎設施（knowledge-lattice, eval-engine...）
    "workflow": 8,    # 工作流範本（不應被選為 worker，但作為兜底）
}
_DEFAULT_PRIORITY = 5


def _get_priority(skill: Dict[str, Any]) -> int:
    """從 Skill 的 hub 欄位推導優先級."""
    hub = skill.get("hub", "")
    return _HUB_PRIORITY.get(hub, _DEFAULT_PRIORITY)


def _get_model_preference(
    skill: Dict[str, Any], default_model: str,
) -> str:
    """從 Skill 的 model_preference 欄位決定模型.

    優先順序：Manifest 欄位 > 迴圈預設值
    """
    manifest_pref = skill.get("model_preference", "")
    if manifest_pref in ("sonnet", "haiku", "opus"):
        return manifest_pref
    return default_model


def _build_depends_on(
    selected: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """從 io.inputs 推導任務間依賴關係.

    規則：若 Skill A 的 io.inputs 中有 from: Skill B，
    且 B 也在本次 selected 中，則 A depends_on B。
    """
    selected_names: Set[str] = {s.get("name", "") for s in selected}
    deps: Dict[str, List[str]] = {}

    for skill in selected:
        name = skill.get("name", "")
        io_inputs = skill.get("io_inputs", [])
        skill_deps = []
        for inp in io_inputs:
            from_skill = inp.get("from", "")
            if from_skill in selected_names and from_skill != name:
                skill_deps.append(from_skill)
        deps[name] = skill_deps

    return deps


def decompose(
    user_request: str,
    matched_skills: List[Dict[str, Any]],
    is_simple: bool = False,
    max_tasks: int = 5,
) -> List[Dict[str, Any]]:
    """確定性任務分解.

    Args:
        user_request: 使用者原始訊息
        matched_skills: DNA27 匹配的 Skill 清單
        is_simple: 簡單請求時使用 haiku/quick，否則使用 sonnet/standard
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

    # Step 2: 排序——按 Hub 優先級（從 Manifest hub 欄位驅動）
    worker_skills.sort(key=_get_priority)

    # Step 3: 取 top-N（不超過 max_tasks）
    selected = worker_skills[:max_tasks]

    # Step 4: 決定 depth 和 model（簡單 → haiku/quick，否則 → sonnet/standard）
    if is_simple:
        default_depth = "quick"
        default_model = "haiku"
    else:
        default_depth = "standard"
        default_model = "sonnet"

    # Step 5: 從 io.inputs 推導依賴關係
    deps_map = _build_depends_on(selected)

    # Step 6: 產出 TaskPackage 相容 dict
    tasks = []
    for i, skill in enumerate(selected):
        name = skill.get("name", "unknown")
        desc = skill.get("description", "")
        model = _get_model_preference(skill, default_model)

        tasks.append({
            "skill_name": name,
            "skill_focus": desc[:200] if desc else f"執行 {name} 分析",
            "skill_depth": default_depth,
            "expected_output": f"{name} 的分析結論",
            "execution_order": i,
            "depends_on": deps_map.get(name, []),
            "model_preference": model,
        })

    logger.info(
        f"[DeterministicRouter] 分解完成: {len(tasks)} tasks "
        f"from {len(matched_skills)} matched, is_simple={is_simple}"
    )
    return tasks
