"""PDR Council -- Nine Advisors Engine.

Phase 2 post-review: parallel multi-perspective council
that audits the primary response for quality AND missed opportunities.

Each advisor has:
- A review focus (quality dimension)
- A proactive action capability (can trigger Skills/tools/workflows)
- DNA27 cluster affinity (determines when they're selected)

Usage:
    council = PDRCouncil(llm_adapter, brain)
    verdict = await council.review(routing_signal, query, primary_response, session_id)
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from museon.agent.pdr_params import PDRVerdict, ProactiveAction

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════
# Nine Advisors Definition
# ═══════════════════════════════════════

@dataclass(frozen=True)
class AdvisorProfile:
    """A single advisor in the council."""

    id: str
    name: str
    focus: str
    prompt_core: str
    dna27_clusters: Tuple[str, ...]  # RC-XX cluster affinities
    action_targets: Tuple[str, ...]  # Skills/tools this advisor can trigger


ADVISORS: Dict[str, AdvisorProfile] = {
    "xmodel": AdvisorProfile(
        id="xmodel",
        name="破框師",
        focus="框架盲點、第一性原理、未被質疑的假設",
        prompt_core=(
            "你是破框師。審查這個回覆中有什麼未被質疑的假設？"
            "有沒有被既有框架限制住的觀點？"
            "如果用第一性原理重新拆解，會得到不同的結論嗎？"
        ),
        dna27_clusters=("RC-C1", "RC-C2", "RC-C3", "RC-C4"),
        action_targets=("xmodel", "philo-dialectic"),
    ),
    "strategist": AdvisorProfile(
        id="strategist",
        name="戰略師",
        focus="商業戰略、機會成本、更好的路徑",
        prompt_core=(
            "你是戰略師。從戰略層面看，有沒有更好的路徑？"
            "機會成本是什麼？有沒有更高槓桿的選擇被忽略？"
            "現有建議的護城河夠深嗎？"
        ),
        dna27_clusters=("RC-D1", "RC-E1", "RC-B2"),
        action_targets=("master-strategy", "business-12"),
    ),
    "shadow": AdvisorProfile(
        id="shadow",
        name="暗影師",
        focus="心理傾向、隱藏動機、使用者沒說出口的需求",
        prompt_core=(
            "你是暗影師。使用者沒說出口的真正需求是什麼？"
            "有沒有隱藏的心理動機或防衛機制在影響他的判斷？"
            "這個問題背後的情緒是什麼？"
        ),
        dna27_clusters=("RC-A2", "RC-A6", "RC-A1"),
        action_targets=("shadow", "resonance"),
    ),
    "risk": AdvisorProfile(
        id="risk",
        name="風險師",
        focus="代價評估、最壞情境、風險盲點",
        prompt_core=(
            "你是風險師。最可能出錯的是什麼？代價多大？"
            "有沒有不可逆的風險被輕描淡寫？"
            "最壞情境下的退路是什麼？"
        ),
        dna27_clusters=("RC-A3", "RC-A4", "RC-A7"),
        action_targets=("risk-matrix",),
    ),
    "devil": AdvisorProfile(
        id="devil",
        name="辯魔師",
        focus="反面論證、壓力測試、最強反駁",
        prompt_core=(
            "你是辯魔師。如果有人要反駁這個建議，最強的論點是什麼？"
            "這個結論的證據夠充分嗎？有沒有倖存者偏差？"
            "反過來想，什麼情況下這個建議會完全錯誤？"
        ),
        dna27_clusters=("RC-C5",),
        action_targets=("roundtable",),
    ),
    "action": AdvisorProfile(
        id="action",
        name="行動師",
        focus="具體下一步、時間線、可操作性",
        prompt_core=(
            "你是行動師。使用者看完能立刻做什麼？具體步驟是什麼？"
            "有沒有可以量化的目標和時間線？"
            "最小可行動作（MVA）是什麼？今天就能開始的是什麼？"
        ),
        dna27_clusters=("RC-D2", "RC-D4"),
        action_targets=("orchestrator", "pdeif"),
    ),
    "simplifier": AdvisorProfile(
        id="simplifier",
        name="簡化師",
        focus="複雜度降級、本質提煉、資訊噪音",
        prompt_core=(
            "你是簡化師。能用一句話說清楚核心結論嗎？"
            "哪些內容是噪音、可以刪掉而不影響核心價值？"
            "使用者最需要記住的一件事是什麼？"
        ),
        dna27_clusters=("RC-E4",),
        action_targets=(),
    ),
    "guardian": AdvisorProfile(
        id="guardian",
        name="守護師",
        focus="安全紅線、主權保護、越界風險",
        prompt_core=(
            "你是守護師。這個建議有沒有越過使用者的決策主權？"
            "有沒有安全風險（財務、法律、隱私）被忽略？"
            "是否替使用者做了不該替他做的決定？"
        ),
        dna27_clusters=("RC-A7", "RC-B1", "RC-B5"),
        action_targets=(),
    ),
    "historian": AdvisorProfile(
        id="historian",
        name="記憶師",
        focus="歷史模式、週期識別、經驗教訓",
        prompt_core=(
            "你是記憶師。過去類似情境的結果是什麼？有沒有 pattern？"
            "使用者之前做過類似決策嗎？結果如何？"
            "有什麼歷史教訓可以避免重蹈覆轍？"
        ),
        dna27_clusters=("RC-E2", "RC-E3"),
        action_targets=("knowledge-lattice",),
    ),
}


# ═══════════════════════════════════════
# Advisor Selection Engine
# ═══════════════════════════════════════

def select_advisors(
    routing_signal: Any,
    query: str,
    primary_response: str,
    max_advisors: int = 4,
) -> List[str]:
    """Select 2-4 advisors based on RoutingSignal + response characteristics."""
    selected = []

    # 1. Safety/sovereignty triggers → guardian
    cluster_scores = getattr(routing_signal, "cluster_scores", {})
    tier_a = sum(cluster_scores.get(f"RC-A{i}", 0) for i in range(1, 8))
    tier_b = sum(cluster_scores.get(f"RC-B{i}", 0) for i in range(1, 7))
    if tier_a > 2.0 or tier_b > 2.0:
        selected.append("guardian")

    # 2. SLOW_LOOP → always include devil's advocate
    loop = getattr(routing_signal, "loop", "FAST_LOOP")
    if loop == "SLOW_LOOP":
        selected.append("devil")

    # 3. Cluster-based selection
    for advisor_id, profile in ADVISORS.items():
        if advisor_id in selected:
            continue
        affinity = sum(cluster_scores.get(c, 0) for c in profile.dna27_clusters)
        if affinity > 1.0:
            selected.append(advisor_id)

    # 4. Response-characteristic selection
    if len(primary_response) > 800 and "simplifier" not in selected:
        selected.append("simplifier")

    # Actionability check: if response lacks concrete steps
    _action_keywords = ["步驟", "具體", "首先", "第一步", "接下來", "行動"]
    if not any(kw in primary_response for kw in _action_keywords):
        if "action" not in selected:
            selected.append("action")

    # 5. Deduplicate + limit
    seen = set()
    unique = []
    for a in selected:
        if a not in seen:
            seen.add(a)
            unique.append(a)
    selected = unique[:max_advisors]

    # 6. Minimum 2 advisors (fallback: strategist + action)
    if len(selected) < 2:
        for fallback in ["strategist", "action"]:
            if fallback not in selected:
                selected.append(fallback)
            if len(selected) >= 2:
                break

    return selected


# ═══════════════════════════════════════
# Council Review Engine
# ═══════════════════════════════════════

_REVIEW_PROMPT_TEMPLATE = """你是 MUSEON 九策軍師中的「{advisor_name}」。

## 你的審查焦點
{advisor_focus}

## 使用者問題
{query}

## 主要回覆
{primary_response}

## 可用能力
{available_skills}

## 請回答（JSON 格式）
{{
  "quality_score": 1-10（針對你的審查焦點的品質評分）,
  "missed_opportunity": "有沒有錯過的機會？具體說明",
  "suggested_action": {{
    "needed": true/false,
    "type": "skill_invoke / tool_use / workflow / none",
    "target": "具體 skill 或工具名稱",
    "reason": "為什麼要主動執行"
  }},
  "verdict": "KEEP / EDIT / ACTION",
  "supplement": "如果 EDIT，要補充什麼內容（2-3 句話）"
}}
"""


class PDRCouncil:
    """Nine Advisors Council for Phase 2 post-review."""

    def __init__(self, llm_adapter, brain=None):
        self._adapter = llm_adapter
        self._brain = brain

    async def review(
        self,
        routing_signal: Any,
        query: str,
        primary_response: str,
        session_id: str = "",
        available_skills: str = "",
    ) -> PDRVerdict:
        """Run parallel advisor review and synthesize verdict."""
        from museon.agent.pdr_params import get_pdr_params
        params = get_pdr_params()

        # Select advisors
        advisor_ids = select_advisors(
            routing_signal, query, primary_response,
            max_advisors=params.phase2_advisor_count,
        )
        logger.info(f"[PDR Council] Selected advisors: {advisor_ids}")

        # Parallel review
        tasks = []
        for aid in advisor_ids:
            profile = ADVISORS[aid]
            prompt = _REVIEW_PROMPT_TEMPLATE.format(
                advisor_name=profile.name,
                advisor_focus=profile.focus + "\n\n" + profile.prompt_core,
                query=query[:500],
                primary_response=primary_response[:1500],
                available_skills=available_skills[:500],
            )
            tasks.append(self._call_advisor(aid, prompt))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Parse results
        advisor_results = {}
        for aid, result in zip(advisor_ids, results):
            if isinstance(result, Exception):
                logger.warning(f"[PDR Council] Advisor {aid} failed: {result}")
                continue
            advisor_results[aid] = result

        # Synthesize verdict
        return self._synthesize(advisor_results, primary_response)

    async def _call_advisor(self, advisor_id: str, prompt: str) -> Dict[str, Any]:
        """Call a single advisor via LLM."""
        try:
            response = await self._adapter.call(
                system_prompt="你是 MUSEON 九策軍師。只回傳 JSON，不要其他文字。",
                messages=[{"role": "user", "content": prompt}],
                model="haiku",
                max_tokens=500,
            )
            text = response.text.strip()
            # Extract JSON from response
            json_match = re.search(r"\{[\s\S]*\}", text)
            if json_match:
                return json.loads(json_match.group())
            return {"quality_score": 7, "verdict": "KEEP", "missed_opportunity": "", "supplement": ""}
        except Exception as e:
            logger.warning(f"[PDR Council] Advisor {advisor_id} LLM call failed: {e}")
            return {"quality_score": 7, "verdict": "KEEP", "missed_opportunity": "", "supplement": ""}

    def _synthesize(
        self,
        advisor_results: Dict[str, Dict[str, Any]],
        primary_response: str,
    ) -> PDRVerdict:
        """Synthesize individual advisor results into a single verdict."""
        if not advisor_results:
            return PDRVerdict(verdict=PDRVerdict.KEEP)

        scores = {}
        verdicts = []
        supplements = []
        actions = []

        for aid, result in advisor_results.items():
            score = result.get("quality_score", 7)
            scores[aid] = score
            v = result.get("verdict", "KEEP").upper()
            verdicts.append(v)

            if v == "EDIT" and result.get("supplement"):
                supplements.append(f"[{ADVISORS[aid].name}] {result['supplement']}")

            # Collect proactive actions
            sa = result.get("suggested_action", {})
            if sa.get("needed") and sa.get("type") != "none":
                profile = ADVISORS[aid]
                actions.append(ProactiveAction(
                    type=sa.get("type", "skill_invoke"),
                    target=sa.get("target", ""),
                    reason=sa.get("reason", ""),
                    priority=1,  # background by default
                ))

        # Determine final verdict
        action_count = verdicts.count("ACTION")
        edit_count = verdicts.count("EDIT")
        keep_count = verdicts.count("KEEP")

        if actions:
            final_verdict = PDRVerdict.ACTION
        elif edit_count > 0:
            final_verdict = PDRVerdict.EDIT
        else:
            final_verdict = PDRVerdict.KEEP

        # Build supplement text
        supplement_text = "\n".join(supplements) if supplements else ""

        # If supplement is too long, might be APPEND instead of EDIT
        if len(supplement_text) > 500:
            final_verdict = PDRVerdict.APPEND

        avg_score = sum(scores.values()) / max(len(scores), 1)
        reasoning_parts = []
        for aid, result in advisor_results.items():
            mo = result.get("missed_opportunity", "")
            if mo:
                reasoning_parts.append(f"{ADVISORS[aid].name}: {mo}")

        return PDRVerdict(
            verdict=final_verdict,
            supplement=supplement_text,
            actions=actions,
            advisor_scores=scores,
            reasoning="\n".join(reasoning_parts),
        )
