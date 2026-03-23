"""BrainP3FusionMixin — P3 策略融合與決策層方法群.

從 brain.py 提取的 Mixin，負責 P2 決策層（重大決策先問後答）、
P3 策略層並行融合（三視角交織）、元認知並行審查等邏輯。
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from museon.agent.brain_types import DecisionSignal, P3FusionSignal

logger = logging.getLogger(__name__)


class BrainP3FusionMixin:
    """P3 策略融合與決策層方法群 — Mixin for MuseonBrain."""

    # ═══════════════════════════════════════════════════════════════════
    # 常數定義（P0 健康檢查常數化）
    # ═══════════════════════════════════════════════════════════════════

    # — P2 決策層 LLM 參數 —
    _P2_QUERY_TRUNCATE_LEN = 300       # P2 視角方法的查詢截斷長度
    _P2_MAX_TOKENS = 100               # P2 視角方法的 LLM 最大 token
    _P2_RESPONSE_TRUNCATE_LEN = 150    # P2 視角回應截斷長度
    _P2_MAX_DECISION_QUESTIONS = 5     # 決策反問最大數量
    _P2_STAKEHOLDER_QUESTION_THRESHOLD = 3  # 觸發利益相關方反問的閾值

    # — P3 策略層 LLM 參數 —
    _P3_QUERY_TRUNCATE_LEN = 400       # P3 視角方法的查詢截斷長度
    _P3_MAX_TOKENS = 150               # P3 視角方法的 LLM 最大 token
    _P3_HAIKU_MODEL = "claude-haiku-4-5-20251001"  # 視角生成使用的輕量模型

    # — P3 信號偵測閾值 —
    _P3_MIN_QUERY_LENGTH = 15          # 觸發 P3 的最短查詢長度
    _P3_CONFIDENCE_BASE = 0.6          # EXPLORATION_LOOP 信心基線
    _P3_CONFIDENCE_EXPLORE_MULTI = 0.7  # v9.1: EXPLORATION_LOOP 多策略 Skill 信心
    _P3_CONFIDENCE_SLOW = 0.75         # SLOW_LOOP 單策略 Skill 信心
    _P3_CONFIDENCE_SLOW_MULTI = 0.9    # SLOW_LOOP 多策略 Skill 信心

    # — P2 決策偵測閾值 —
    _P2_MIN_STAKEHOLDERS = 2           # 觸發重大決策的最低利益相關方數
    _P2_MIN_IMPACT_MONTHS = 3          # 觸發重大決策的最短影響時間（月）
    _P2_DEFAULT_IMPACT_MONTHS = 3      # 預設影響時間（月）
    _P2_CONFLICT_BONUS_STAKEHOLDERS = 2  # 衝突配對命中時的額外利益相關方數
    _P2_CONFIDENCE_BASE = 0.6          # 決策信心基線
    _P2_CONFIDENCE_PER_STAKEHOLDER = 0.1  # 每個利益相關方增加的信心
    _P2_CONFIDENCE_MAX = 0.95          # 決策信心上限

    # — 融合決策權重與閾值 —
    _FUSION_SCORE_BASELINE = 0.5       # 融合分數基線
    _FUSION_WEIGHT_METACOG = 0.4       # MetaCognition 權重 (40%)
    _FUSION_WEIGHT_EVAL = 0.35         # EvalEngine 權重 (35%)
    _FUSION_WEIGHT_HEALTH = 0.25       # Health Score 權重 (25%)
    _FUSION_QSCORE_LOW_THRESHOLD = 0.5  # Q-Score 低分警告閾值
    _FUSION_QSCORE_HIGH_BONUS = 0.1   # Q-Score 高分加分係數
    _FUSION_HEALTH_LOW_THRESHOLD = 50  # Health Score 低分閾值
    _FUSION_HEALTH_ALERT_THRESHOLD = 40  # Health Score 警報閾值
    _FUSION_REVISE_THRESHOLD = 0.3     # 觸發 REVISE 的融合分數閾值

    # — 精煉偏好 —
    _BREVITY_PREF_COUNT_THRESHOLD = 50  # 啟用簡短偏好約束的計數閾值
    _METACOG_FEEDBACK_TRUNCATE_LEN = 80  # MetaCog 回饋日誌截斷長度

    # ═══════════════════════════════════════════════════════════════════
    # P2 決策層 — 重大決策先問後答
    # ═══════════════════════════════════════════════════════════════════

    async def _handle_decision_layer_path(
        self,
        query: str,
        decision_signal: DecisionSignal,
        session_id: str,
        anima_mc: Optional[Dict[str, Any]] = None,
        anima_user: Optional[Dict[str, Any]] = None,
    ) -> str:
        """P2 決策層路徑 — 重大決策先問後答.

        流程：
        1. 並行蒐集 xmodel、master-strategy、shadow 的多角度見解
        2. 綜合為 3-5 個反問點
        3. 組裝回覆：「這是個重大決策。在深入分析之前，我想確認... [反問清單]」
        4. 返回反問回覆，等待使用者下一個 turn 再進行深入分析

        Returns:
            決策層反問回覆文本
        """
        # 步驟 1：並行蒐集多角度見解
        perspectives = await self._gather_decision_perspectives(
            query=query,
            decision_signal=decision_signal,
            anima_mc=anima_mc,
            anima_user=anima_user,
        )

        # 步驟 2：綜合為反問點
        decision_questions = self._synthesize_decision_questions(
            query=query,
            decision_signal=decision_signal,
            perspectives=perspectives,
        )

        # 步驟 3：組裝回覆
        my_name = "MUSEON"
        if anima_mc:
            my_name = anima_mc.get("identity", {}).get("name", "MUSEON")

        decision_response = (
            f"這是個重大決策。{my_name} 先不直接分析，想確認你有沒有考慮過這些角度：\n\n"
        )

        for i, question in enumerate(decision_questions, 1):
            decision_response += f"{i}. {question}\n"

        decision_response += (
            "\n你可以逐個回答，或告訴我哪些已經想過了。"
            "讓我了解你的思路後，我再做更深入的分析。"
        )

        logger.info(f"[決策層] 反問回覆已組裝，共 {len(decision_questions)} 個反問點")

        return decision_response

    def _synthesize_decision_questions(
        self,
        query: str,
        decision_signal: DecisionSignal,
        perspectives: Dict[str, str],
    ) -> List[str]:
        """從多角度見解綜合為 3-5 個反問點.

        策略：
        - 提取 xmodel、master-strategy、shadow 的核心反問
        - 補充決策類型特定的反問
        - 控制在 3-5 個反問

        Returns:
            反問列表 (3-5 個)
        """
        questions = []

        # 從各個角色的見解中提取反問
        if perspectives.get("xmodel"):
            questions.append(perspectives["xmodel"])

        if perspectives.get("master_strategy"):
            questions.append(perspectives["master_strategy"])

        if perspectives.get("shadow"):
            questions.append(perspectives["shadow"])

        # 補充決策類型特定的反問
        type_specific_q = self._get_decision_type_questions(decision_signal)
        if type_specific_q:
            questions.append(type_specific_q)

        # 利益相關方角度反問
        if decision_signal.stakeholders_count >= self._P2_STAKEHOLDER_QUESTION_THRESHOLD:
            questions.append(
                f"涉及 {decision_signal.stakeholders_count} 個利益相關方。"
                "你有充分聽取每方的立場嗎？"
            )

        # 控制在 3-5 個
        questions = [q for q in questions if q]  # 去空值
        return (
            questions[:self._P2_MAX_DECISION_QUESTIONS]
            if len(questions) > self._P2_MAX_DECISION_QUESTIONS
            else questions or ["想想還有什麼沒考慮到的嗎？"]
        )

    def _get_decision_type_questions(self, decision_signal: DecisionSignal) -> str:
        """根據決策類型給出特定反問."""
        decision_type = decision_signal.decision_type

        if decision_type == "financial":
            return "成本與收益的長期回報週期是多少？這個決定會影響現金流嗎？"
        elif decision_type == "organizational":
            return "這個決策對團隊文化和人才留存會有什麼影響？"
        elif decision_type == "product":
            return "這個決策會改變產品的核心價值主張嗎？"
        elif decision_type == "market":
            return "你對市場反應和競爭對手動向有多大的把握？"
        else:
            return "這個決策的不可逆性程度如何？一旦錯了能糾正嗎？"

    async def _gather_decision_perspectives(
        self,
        query: str,
        decision_signal: DecisionSignal,
        anima_mc: Optional[Dict[str, Any]] = None,
        anima_user: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """並行蒐集決策多角度見解（xmodel/master-strategy/shadow 模擬）.

        Returns:
            {
                "xmodel": "...",  # 破框思維角度
                "master_strategy": "...",  # 商業現實角度
                "shadow": "...",  # 心理傾向角度
            }
        """
        perspectives = {}

        # 並行呼叫三個角色（使用 asyncio.gather）
        try:
            results = await asyncio.gather(
                self._xmodel_perspective(query, decision_signal),
                self._master_strategy_perspective(query, decision_signal),
                self._shadow_perspective(query, decision_signal, anima_user),
                return_exceptions=True,
            )

            perspectives["xmodel"] = (
                results[0] if isinstance(results[0], str) else ""
            )
            perspectives["master_strategy"] = (
                results[1] if isinstance(results[1], str) else ""
            )
            perspectives["shadow"] = (
                results[2] if isinstance(results[2], str) else ""
            )

            logger.info(
                "[決策層] 多角度見解蒐集完畢: "
                f"xmodel={len(perspectives['xmodel'])} chars, "
                f"master_strategy={len(perspectives['master_strategy'])} chars, "
                f"shadow={len(perspectives['shadow'])} chars"
            )

        except Exception as e:
            logger.error(f"決策層多角度見解失敗: {e}", exc_info=True)

        return perspectives

    async def _xmodel_perspective(
        self, query: str, decision_signal: DecisionSignal
    ) -> str:
        """xmodel（破框思維）角度 — 有沒有其他框架？"""
        try:
            prompt = (
                f"使用者的決策問題：{query[:self._P2_QUERY_TRUNCATE_LEN]}\n\n"
                f"決策類型：{decision_signal.decision_type}\n"
                f"涉及利益相關方：{decision_signal.stakeholders_count} 個\n\n"
                f"你是 xmodel（破框思維）顧問。在 1-2 句內，"
                f"問一個關於「有沒有我沒想到的框架或視角」的反問。"
            )

            response = await self._call_llm_with_model(
                system_prompt="你是 MUSEON 的破框思維顧問（xmodel）。快速、簡潔、反問式。",
                messages=[{"role": "user", "content": prompt}],
                model=self._P3_HAIKU_MODEL,
                max_tokens=self._P2_MAX_TOKENS,
            )
            return response.strip()[:self._P2_RESPONSE_TRUNCATE_LEN]

        except Exception as e:
            logger.warning(f"xmodel 角度生成失敗: {e}")
            return ""

    async def _master_strategy_perspective(
        self, query: str, decision_signal: DecisionSignal
    ) -> str:
        """master-strategy（商業現實）角度 — 商業現實是什麼？"""
        try:
            prompt = (
                f"使用者的決策問題：{query[:self._P2_QUERY_TRUNCATE_LEN]}\n\n"
                f"決策類型：{decision_signal.decision_type}\n"
                f"影響時間：{decision_signal.impact_horizon_months} 個月\n\n"
                f"你是商業戰略顧問（master-strategy）。在 1-2 句內，"
                f"問一個關於「這個決策的商業現實/代價」的反問。"
            )

            response = await self._call_llm_with_model(
                system_prompt="你是 MUSEON 的商業戰略顧問（master-strategy）。專注商業現實與代價。",
                messages=[{"role": "user", "content": prompt}],
                model=self._P3_HAIKU_MODEL,
                max_tokens=self._P2_MAX_TOKENS,
            )
            return response.strip()[:self._P2_RESPONSE_TRUNCATE_LEN]

        except Exception as e:
            logger.warning(f"master-strategy 角度生成失敗: {e}")
            return ""

    async def _shadow_perspective(
        self,
        query: str,
        decision_signal: DecisionSignal,
        anima_user: Optional[Dict[str, Any]] = None,
    ) -> str:
        """shadow（心理傾向）角度 — 你的心理傾向是什麼？"""
        try:
            user_context = ""
            if anima_user:
                bias = anima_user.get("psychological_bias", "")
                growth = anima_user.get("growth_phase", "")
                if bias:
                    user_context = f"（已知心理傾向：{bias}）"
                if growth:
                    user_context += f"（成長階段：{growth}）"

            prompt = (
                f"使用者的決策問題：{query[:self._P2_QUERY_TRUNCATE_LEN]}\n"
                f"{user_context}\n\n"
                f"你是心理顧問（shadow）。在 1-2 句內，"
                f"問一個關於「你在這個決策中的心理傾向/盲點」的反問。"
            )

            response = await self._call_llm_with_model(
                system_prompt="你是 MUSEON 的心理顧問（shadow）。幫助使用者看見自己的心理傾向。",
                messages=[{"role": "user", "content": prompt}],
                model=self._P3_HAIKU_MODEL,
                max_tokens=self._P2_MAX_TOKENS,
            )
            return response.strip()[:self._P2_RESPONSE_TRUNCATE_LEN]

        except Exception as e:
            logger.warning(f"shadow 角度生成失敗: {e}")
            return ""

    # ═══════════════════════════════════════════════════════════════════
    # P3 策略層並行融合
    # ═══════════════════════════════════════════════════════════════════

    def _detect_p3_strategy_layer_signal(
        self,
        query: str,
        loop_mode: str,
        matched_skills: List[str],
    ) -> P3FusionSignal:
        """偵測「策略層」信號 — P3 並行融合路由核心邏輯.

        判斷條件：
        1. loop_mode 不是 FAST_LOOP（快速問答不需要多角度）
        2. matched_skills 包含至少 1 個策略層 Skill
        3. query 長度 > _P3_MIN_QUERY_LENGTH 字（非簡短問候）

        視角路由：
        - strategy（必選）：master-strategy × xmodel 破框戰略
        - human（人物/關係詞觸發）：shadow 心理動機與博弈
        - risk（商業/市場詞觸發）：代價、機會成本、風險

        Returns:
            P3FusionSignal
        """
        # 快速通道：FAST_LOOP 直接跳過
        if loop_mode == "FAST_LOOP":
            return P3FusionSignal(
                should_fuse=False,
                perspectives=[],
                confidence=0.0,
                reason="FAST_LOOP 模式，跳過 P3",
            )

        # 太短的查詢不需要多角度
        if len(query.strip()) < self._P3_MIN_QUERY_LENGTH:
            return P3FusionSignal(
                should_fuse=False,
                perspectives=[],
                confidence=0.0,
                reason="查詢過短，跳過 P3",
            )

        # 策略層 Skill 清單（命中任一即觸發）
        strategy_skills = {
            "master-strategy", "xmodel", "shadow", "business-12",
            "dse", "market-core", "market-equity", "market-crypto",
            "market-macro", "ssa-consultant", "roundtable",
        }
        matched_strategy = [s for s in matched_skills if s in strategy_skills]
        if not matched_strategy:
            return P3FusionSignal(
                should_fuse=False,
                perspectives=[],
                confidence=0.0,
                reason="未匹配到策略層 Skill",
            )

        # 決定需要哪些視角
        perspectives: List[str] = ["strategy"]  # 策略/破框視角（必選）

        # 含人物/關係詞 → 加入心理視角
        human_keywords = [
            "客戶", "老闆", "團隊", "對方", "合作", "競爭", "談判",
            "關係", "說服", "溝通", "說", "人", "他", "她", "他們",
        ]
        if any(kw in query for kw in human_keywords):
            perspectives.append("human")

        # 含商業/市場/風險詞 → 加入風險視角
        risk_keywords = [
            "市場", "風險", "成本", "利潤", "收益", "投資", "定價",
            "競爭對手", "品牌", "業績", "營收", "獲利", "損失", "機會",
        ]
        if any(kw in query for kw in risk_keywords):
            perspectives.append("risk")

        # v9.1: confidence 動態計算（修復恆定 0.60 問題）
        confidence = self._P3_CONFIDENCE_BASE
        if loop_mode == "SLOW_LOOP" and len(matched_strategy) >= 2:
            confidence = self._P3_CONFIDENCE_SLOW_MULTI
        elif loop_mode == "SLOW_LOOP":
            confidence = self._P3_CONFIDENCE_SLOW
        elif loop_mode == "EXPLORATION_LOOP" and len(matched_strategy) >= 2:
            confidence = self._P3_CONFIDENCE_EXPLORE_MULTI

        return P3FusionSignal(
            should_fuse=True,
            perspectives=perspectives,
            confidence=confidence,
            reason=f"策略層 Skill: {matched_strategy}, loop: {loop_mode}",
        )

    async def _p3_gather_pre_fusion_insights(
        self,
        query: str,
        fusion_signal: P3FusionSignal,
        anima_user: Optional[Dict[str, Any]] = None,
    ) -> str:
        """P3 前置融合 — 在主 LLM 呼叫前並行收集多視角洞察.

        核心改變（v1.22）：視角不再「追加」在主回覆後面，
        而是注入 system_prompt，讓主 LLM 回覆時自然交織多視角。

        Returns:
            注入 system_prompt 的多視角上下文字串，空字串表示無補充
        """
        tasks = []
        perspective_keys = []

        if "strategy" in fusion_signal.perspectives:
            tasks.append(self._p3_strategy_perspective(query))
            perspective_keys.append("strategy")

        if "human" in fusion_signal.perspectives:
            tasks.append(self._p3_human_perspective(query, anima_user))
            perspective_keys.append("human")

        if "risk" in fusion_signal.perspectives:
            tasks.append(self._p3_risk_perspective(query))
            perspective_keys.append("risk")

        if not tasks:
            return ""

        # 並行呼叫（asyncio.gather，return_exceptions=True 確保單個失敗不影響其他）
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 組裝上下文（只取有效結果）
        perspective_labels = {
            "strategy": "戰略破框視角（xmodel × master-strategy）",
            "human": "人心博弈視角（shadow × 心理動機）",
            "risk": "風險代價視角（機會成本 × 隱性風險）",
        }
        valid_insights = []
        for key, result in zip(perspective_keys, results):
            if isinstance(result, Exception) or not result:
                continue
            label = perspective_labels.get(key, key)
            valid_insights.append(f"- {label}：{result.strip()}")

        if not valid_insights:
            return ""

        insights_block = "\n".join(valid_insights)

        return (
            "【六層技術棧前置融合 — 多視角洞察】\n"
            "以下是你的多部門顧問團隊針對使用者問題的預先分析。\n"
            "你的回覆必須自然地交織這些視角的洞察——不是分開列出，"
            "而是融入你的分析、判斷和建議中。讓讀者感受到「這個 AI "
            "真的從多個角度想過了」，而不是「它列了一堆觀點」。\n\n"
            f"{insights_block}\n\n"
            "重要：不要使用「多視角觀察」「從策略角度看」之類的格式化標題，"
            "而是讓這些洞察自然地融入你的回覆結構中。"
        )

    async def _execute_p3_parallel_fusion(
        self,
        query: str,
        fusion_signal: P3FusionSignal,
        anima_user: Optional[Dict[str, Any]] = None,
    ) -> str:
        """P3 策略層並行融合 — 並行呼叫多視角 Haiku，組裝「多視角觀察」.

        DEPRECATED(v1.22): 已被 _p3_gather_pre_fusion_insights 取代。
        僅保留供 nightly/離線場景的向後相容使用。

        Returns:
            多視角補充文字（追加到主回覆末尾），空字串表示無補充
        """
        tasks = []
        labels = []

        if "strategy" in fusion_signal.perspectives:
            tasks.append(self._p3_strategy_perspective(query))
            labels.append("📐 策略層（破框 × 戰略）")

        if "human" in fusion_signal.perspectives:
            tasks.append(self._p3_human_perspective(query, anima_user))
            labels.append("🧠 人心層（動機 × 博弈）")

        if "risk" in fusion_signal.perspectives:
            tasks.append(self._p3_risk_perspective(query))
            labels.append("⚡ 風險層（代價 × 機會）")

        if not tasks:
            return ""

        # 並行呼叫（asyncio.gather，return_exceptions=True 確保單個失敗不影響其他）
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 組裝輸出（只取有效結果）
        valid_parts = []
        for label, result in zip(labels, results):
            if isinstance(result, Exception) or not result:
                continue
            valid_parts.append(f"**{label}**\n{result.strip()}")

        if not valid_parts:
            return ""

        return "\n\n".join(["---\n**MUSEON 多視角觀察**"] + valid_parts)

    async def _p3_strategy_perspective(self, query: str) -> str:
        """P3 策略視角 — 破框思維 × 戰略判斷的融合分析."""
        try:
            prompt = (
                f"使用者的問題：{query[:self._P3_QUERY_TRUNCATE_LEN]}\n\n"
                f"你同時是破框思維顧問（xmodel）和商業戰略顧問（master-strategy）。\n"
                f"在 2-3 句內，指出「使用者可能沒想到的戰略視角或框架盲點」。"
                f"直接切入，不重複問題本身。用繁體中文回答。"
            )
            response = await self._call_llm_with_model(
                system_prompt=(
                    "你是 MUSEON 的策略層顧問，融合 xmodel（破框）和 master-strategy（戰略）。"
                    "簡潔、精準、有洞察力。不要重複使用者說的話，直接給補充視角。繁體中文。"
                ),
                messages=[{"role": "user", "content": prompt}],
                model=self._P3_HAIKU_MODEL,
                max_tokens=self._P3_MAX_TOKENS,
            )
            return response.strip()
        except Exception as e:
            logger.warning(f"[P3] 策略視角生成失敗: {e}")
            return ""

    async def _p3_human_perspective(
        self,
        query: str,
        anima_user: Optional[Dict[str, Any]] = None,
    ) -> str:
        """P3 人心視角 — shadow 心理動機與博弈分析."""
        try:
            user_ctx = ""
            if anima_user:
                bias = anima_user.get("psychological_bias", "")
                if bias:
                    user_ctx = f"（已知心理傾向：{bias}）"

            prompt = (
                f"使用者的問題：{query[:self._P3_QUERY_TRUNCATE_LEN]}\n"
                f"{user_ctx}\n\n"
                f"你是心理顧問（shadow）。在 2-3 句內，"
                f"指出「這個情境中涉及的人心動機、潛在博弈、或需要注意的心理層面」。"
                f"不是泛泛的心理學，是針對這個具體問題的人際洞察。繁體中文。"
            )
            response = await self._call_llm_with_model(
                system_prompt=(
                    "你是 MUSEON 的人心顧問（shadow）。專注人際動態、隱性動機與心理傾向。"
                    "簡潔、有洞察力、針對具體情境。繁體中文。"
                ),
                messages=[{"role": "user", "content": prompt}],
                model=self._P3_HAIKU_MODEL,
                max_tokens=self._P3_MAX_TOKENS,
            )
            return response.strip()
        except Exception as e:
            logger.warning(f"[P3] 人心視角生成失敗: {e}")
            return ""

    async def _p3_risk_perspective(self, query: str) -> str:
        """P3 風險視角 — 商業代價與機會成本分析."""
        try:
            prompt = (
                f"使用者的問題：{query[:self._P3_QUERY_TRUNCATE_LEN]}\n\n"
                f"你是風險管理顧問。在 2-3 句內，"
                f"指出「這個情境中容易被忽略的風險、代價或機會成本」。"
                f"具體、可操作，不是抽象的風險清單。繁體中文。"
            )
            response = await self._call_llm_with_model(
                system_prompt=(
                    "你是 MUSEON 的風險顧問。專注商業代價、機會成本與容易被忽略的風險點。"
                    "簡潔、具體、針對問題。繁體中文。"
                ),
                messages=[{"role": "user", "content": prompt}],
                model=self._P3_HAIKU_MODEL,
                max_tokens=self._P3_MAX_TOKENS,
            )
            return response.strip()
        except Exception as e:
            logger.warning(f"[P3] 風險視角生成失敗: {e}")
            return ""

    def _detect_major_decision_signal(
        self,
        query: str,
        loop_mode: str,
        anima_mc: Optional[Dict[str, Any]] = None,
        anima_user: Optional[Dict[str, Any]] = None,
    ) -> DecisionSignal:
        """偵測「重大決策」信號 — P2 路由核心邏輯.

        判斷條件：
        1. query 包含決策詞彙（「決定」「選擇」「要不要」「該不該」等）
        2. 涉及 2+ 個利益相關方或領域衝突（成本 vs 品質、快速 vs 完美等）
        3. 影響時間尺度 > 3 個月
        4. loop_mode = "SLOW_LOOP"（使用者能量充足）

        Returns:
            DecisionSignal 物件，is_major=True 時觸發決策層路徑
        """
        import re

        # 快速通道：非 SLOW_LOOP 直接回傳 False
        if loop_mode != "SLOW_LOOP":
            return DecisionSignal(
                is_major=False,
                decision_type="",
                confidence=0.0,
                stakeholders_count=0,
                impact_horizon_months=0,
                details="非 SLOW_LOOP 模式，跳過決策層偵測",
            )

        # 判斷條件 1：決策詞彙
        decision_keywords = [
            "決定", "決策", "選擇", "要不要", "該不該", "應不應該",
            "採不採", "做不做", "該怎麼", "如何決定", "哪個更好",
            "比較", "權衡", "取捨", "優先順序", "要... 還是...",
        ]
        has_decision_keyword = any(
            kw in query for kw in decision_keywords
        )

        if not has_decision_keyword:
            return DecisionSignal(
                is_major=False,
                decision_type="",
                confidence=0.0,
                stakeholders_count=0,
                impact_horizon_months=0,
                details="未偵測到決策詞彙",
            )

        # 判斷條件 2：多利益相關方或領域衝突
        conflict_pairs = [
            ("成本", "品質"), ("快", "完美"), ("速度", "精度"),
            ("短期", "長期"), ("收益", "風險"), ("成長", "穩定"),
            ("擴張", "深耕"), ("自動化", "人工"), ("外包", "內建"),
            ("用戶", "成本"), ("廣度", "深度"), ("品牌", "利潤"),
        ]
        conflict_pattern = "|".join(
            f"({c1}|{c2})" for c1, c2 in conflict_pairs
        )
        has_conflict = len(re.findall(conflict_pattern, query)) >= 2

        stakeholders_keywords = [
            "老闆", "團隊", "客戶", "員工", "市場", "競爭對手",
            "合作夥伴", "投資者", "股東", "部門", "跨部門",
        ]
        mentioned_stakeholders = sum(
            1 for sw in stakeholders_keywords if sw in query
        )

        stakeholders_count = mentioned_stakeholders + (
            self._P2_CONFLICT_BONUS_STAKEHOLDERS if has_conflict else 0
        )

        if stakeholders_count < self._P2_MIN_STAKEHOLDERS:
            return DecisionSignal(
                is_major=False,
                decision_type="",
                confidence=0.3,
                stakeholders_count=stakeholders_count,
                impact_horizon_months=0,
                details="利益相關方不足（<2）",
            )

        # 判斷條件 3：影響時間尺度
        time_keywords = {
            "長期": 12,
            "短期": 1,
            "中期": 6,
            "3 年": 36,
            "1 年": 12,
            "半年": 6,
            "一個月": 1,
            "三個月": 3,
            "未來": 12,
            "往後": 12,
        }
        impact_months = self._P2_DEFAULT_IMPACT_MONTHS
        for keyword, months in time_keywords.items():
            if keyword in query:
                impact_months = max(impact_months, months)
                break

        if impact_months <= self._P2_MIN_IMPACT_MONTHS:
            return DecisionSignal(
                is_major=False,
                decision_type="",
                confidence=0.4,
                stakeholders_count=stakeholders_count,
                impact_horizon_months=impact_months,
                details=f"影響時間短（{impact_months} 個月）",
            )

        # 綜合判斷：決定決策類型
        decision_type = "general"
        if any(kw in query for kw in ["成本", "錢", "預算", "投資"]):
            decision_type = "financial"
        elif any(kw in query for kw in ["人", "團隊", "招聘", "組織"]):
            decision_type = "organizational"
        elif any(kw in query for kw in ["產品", "服務", "技術", "功能"]):
            decision_type = "product"
        elif any(kw in query for kw in ["市場", "客戶", "品牌", "銷售"]):
            decision_type = "market"

        confidence = min(
            self._P2_CONFIDENCE_MAX,
            self._P2_CONFIDENCE_BASE + (stakeholders_count * self._P2_CONFIDENCE_PER_STAKEHOLDER),
        )

        return DecisionSignal(
            is_major=True,
            decision_type=decision_type,
            confidence=confidence,
            stakeholders_count=stakeholders_count,
            impact_horizon_months=impact_months,
            details=(
                f"多利益相關方({stakeholders_count}) + "
                f"長期影響({impact_months}月) + "
                f"決策詞彙 + {decision_type}"
            ),
        )

    # ═══════════════════════════════════════════
    # P3 並行融合模式 — 三角度同步審查
    # ═══════════════════════════════════════════

    async def _parallel_review_synthesis(
        self,
        draft_response: str,
        user_query: str,
        response_content: str,
        routing_signal: Optional[Any],
        matched_skills: List[str],
    ) -> Dict[str, Any]:
        """P3 並行融合模式：同時執行 MetaCognition + Eval + Health 三個評分.

        使用 asyncio.gather() 並行執行三個獨立的審查/評分模組，
        避免串行瓶頸，提升即時回覆品質。

        Args:
            draft_response: 初稿回覆文字
            user_query: 使用者輸入
            response_content: 完整回覆內容
            routing_signal: DNA27 路由信號
            matched_skills: 匹配的技能列表

        Returns:
            Dict with keys:
            - pre_review: MetaCognition 結果（dict or None）
            - q_score: EvalEngine 結果（QScore or None）
            - health_score: DendriticScorer 健康分數（float or None）
            - fusion_verdict: 融合決策 ("pass" / "revise" / "alert")
            - thinking_path_summary: P0 思考路徑摘要（str）
        """
        fusion_result = {
            "pre_review": None,
            "q_score": None,
            "health_score": None,
            "fusion_verdict": "pass",
            "thinking_path_summary": "",
        }

        # 謀定而後動：根據 loop 分級決定審查深度
        _loop = getattr(routing_signal, 'loop', 'EXPLORATION_LOOP') if routing_signal else 'EXPLORATION_LOOP'
        _fast_mode = (_loop == "FAST_LOOP")

        # ★ P3 並行融合：準備三個異步任務
        tasks = []
        task_names = []

        # 任務 1: MetaCognition.pre_review()
        if self._metacognition and not _fast_mode:
            async def _meta_task():
                try:
                    return await self._metacognition.pre_review(
                        draft_response=draft_response,
                        user_query=user_query,
                        routing_signal=routing_signal,
                        matched_skills=matched_skills,
                    )
                except Exception as e:
                    logger.debug(f"MetaCognition.pre_review 失敗: {e}")
                    return None

            tasks.append(_meta_task())
            task_names.append("pre_review")

        # 任務 2: EvalEngine.evaluate()
        if self.eval_engine:
            def _eval_task():
                try:
                    return self.eval_engine.evaluate(
                        user_content=user_query,
                        response_content=response_content,
                        matched_skills=matched_skills,
                    )
                except Exception as e:
                    logger.debug(f"EvalEngine.evaluate 失敗: {e}")
                    return None

            # 包裝同步函數為異步（P2: 使用 get_running_loop 取代已棄用的 get_event_loop）
            tasks.append(asyncio.get_running_loop().run_in_executor(None, _eval_task))
            task_names.append("q_score")

        # 任務 3: Health Score（通過 Governor 的 DendriticScorer）
        if self._governor and hasattr(self._governor, 'dendritic_scorer') and not _fast_mode:
            def _health_task():
                try:
                    scorer = self._governor.dendritic_scorer
                    return scorer.calculate_score()
                except Exception as e:
                    logger.debug(f"DendriticScorer.calculate_score 失敗: {e}")
                    return None

            tasks.append(asyncio.get_running_loop().run_in_executor(None, _health_task))
            task_names.append("health_score")

        # ★ 並行執行所有任務（無阻塞等待）
        if tasks:
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for i, (result, task_name) in enumerate(zip(results, task_names)):
                    if isinstance(result, Exception):
                        logger.debug(
                            f"Task '{task_name}' raised exception: {result}"
                        )
                        fusion_result[task_name] = None
                    else:
                        fusion_result[task_name] = result
            except Exception as e:
                logger.warning(f"Parallel review gather 失敗: {e}")

        # ★ P3 融合決策邏輯（基於三角度加權）
        try:
            pre_review = fusion_result.get("pre_review")
            q_score = fusion_result.get("q_score")
            health_score = fusion_result.get("health_score")

            # 提煉思考路徑摘要（P0）
            if pre_review and self._metacognition:
                try:
                    fusion_result["thinking_path_summary"] = (
                        self._metacognition.extract_thinking_summary(
                            pre_review=pre_review,
                            user_query=user_query,
                        )
                    )
                except Exception as e:
                    logger.debug(f"提煉思考摘要失敗: {e}")

            # 融合三角度決策
            fusion_score = self._FUSION_SCORE_BASELINE

            # 角度 1: MetaCognition 建議修改
            if pre_review and pre_review.get("verdict") == "revise":
                fusion_score -= self._FUSION_WEIGHT_METACOG
                logger.info(
                    f"[P3-Fusion] MetaCog 建議修改: "
                    f"{pre_review.get('feedback', '')[:self._METACOG_FEEDBACK_TRUNCATE_LEN]}..."
                )

            # 角度 2: EvalEngine Q-Score
            if q_score:
                if q_score.score < self._FUSION_QSCORE_LOW_THRESHOLD:
                    fusion_score -= (
                        self._FUSION_WEIGHT_EVAL
                        * (self._FUSION_QSCORE_LOW_THRESHOLD - q_score.score)
                        / self._FUSION_QSCORE_LOW_THRESHOLD
                    )
                    logger.debug(
                        f"[P3-Fusion] Q-Score 低分警告: {q_score.score:.3f}"
                    )
                else:
                    fusion_score += (
                        self._FUSION_QSCORE_HIGH_BONUS
                        * (q_score.score - self._FUSION_QSCORE_LOW_THRESHOLD)
                    )

            # 角度 3: Health Score
            if health_score is not None:
                if health_score < self._FUSION_HEALTH_LOW_THRESHOLD:
                    fusion_score -= (
                        self._FUSION_WEIGHT_HEALTH
                        * (self._FUSION_HEALTH_LOW_THRESHOLD - health_score)
                        / self._FUSION_HEALTH_LOW_THRESHOLD
                    )
                    logger.debug(
                        f"[P3-Fusion] Health Score 警告: {health_score:.1f}"
                    )

            # ★ 最終決策
            if fusion_score < self._FUSION_REVISE_THRESHOLD:
                fusion_result["fusion_verdict"] = "revise"
                logger.info("[P3-Fusion] 融合決策: REVISE")
            elif health_score is not None and health_score < self._FUSION_HEALTH_ALERT_THRESHOLD:
                fusion_result["fusion_verdict"] = "alert"
                logger.warning(
                    "[P3-Fusion] 融合決策: ALERT (系統健康度臨界)"
                )
            else:
                fusion_result["fusion_verdict"] = "pass"

            logger.debug(
                f"[P3-Fusion] 完成 | "
                f"meta={pre_review is not None} | "
                f"eval={q_score is not None} | "
                f"health={health_score is not None} | "
                f"verdict={fusion_result['fusion_verdict']}"
            )

        except Exception as e:
            logger.warning(f"P3 融合決策失敗，默認 PASS: {e}")

        return fusion_result

    # ═══════════════════════════════════════════
    # MetaCognition — PreCognition 精煉
    # ═══════════════════════════════════════════

    async def _refine_with_precog_feedback(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        feedback: str,
    ) -> str:
        """根據 PreCognition 審查回饋精煉回覆.

        在原始 system_prompt 末尾追加元認知審查回饋，
        重新呼叫 LLM（Sonnet）生成精煉後的回覆。

        Args:
            system_prompt: 原始系統提示詞
            messages: 對話歷史（不含 draft response）
            feedback: PreCognition 的審查回饋

        Returns:
            精煉後的回覆文字
        """
        # ★ 簡短偏好約束：若使用者偏好簡短回覆，在精煉指令中加入長度限制
        _brevity_constraint = ""
        try:
            _au = self._load_anima_user()
            if _au:
                _psr = _au.get("observations", {}).get("prefers_short_response", {}).get("count", 0)
                if _psr > self._BREVITY_PREF_COUNT_THRESHOLD:
                    _brevity_constraint = (
                        "\n⚡ 重要：使用者偏好簡短回覆。精煉後的回覆必須控制在 2-3 句以內，"
                        "不要過度展開或列舉。"
                    )
        except Exception as e:
            logger.warning(f"[P3] 載入使用者偏好失敗（降級跳過簡短約束）: {e}")

        refined_prompt = (
            system_prompt
            + "\n\n"
            + "【元認知審查回饋】\n"
            + "你的初始回覆經過內部審查，以下是需要注意的修改方向：\n"
            + feedback
            + _brevity_constraint
            + "\n\n"
            + "請根據以上回饋，重新組織你的回覆。不需要提及審查過程。"
        )

        try:
            response = await self._call_llm(
                system_prompt=refined_prompt,
                messages=messages,
            )
            if response:
                logger.info(
                    f"[MetaCog] 精煉完成: "
                    f"原始={len(messages[-1]['content']) if messages else 0}字, "
                    f"精煉={len(response)}字"
                )
                return response
        except Exception as e:
            logger.warning(f"PreCognition 精煉呼叫失敗: {e}")

        # Fallback: 返回空字串（呼叫端會保留原始回覆）
        return ""
