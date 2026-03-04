"""MetaCognition Engine — 元認知引擎：PreCognition + 雙向觀察迴路.

MUSEON 的「大腦層級」認知系統，超越 DNA27 小腦反射：

PreCognition（回應前審查）：
  - 在 LLM 生成 draft response 後、送出前執行
  - 五維度審查：影響/假設/視角/框架/真實需求
  - 融合 philo-dialectic（哲學思辨）+ xmodel（破框思維）+ deep-think Phase 2
  - 條件觸發：安全場景必審、SLOW_LOOP 必審、FAST_LOOP 跳過

PostCognition（雙向觀察迴路）：
  - predict(): 回應後，預判使用者反應（純 CPU 啟發式）
  - observe(): 下次互動時，比對預判 vs 實際（純 CPU）
  - 預判準確率 → WEE 演化信號 / morphenix 盲點偵測

設計原則：
  - PreCognition 使用 Haiku（~800 tokens/次，~30% 觸發率）
  - PostCognition 零 LLM 成本（純 CPU 啟發式）
  - 所有操作 try/except 包裹，任何故障不影響核心回覆
"""

import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

PRECOG_MODEL = "claude-haiku-4-5-20251001"
PRECOG_MAX_TOKENS = 300

# 觸發 PreCognition 的技能名稱
_PRECOG_TRIGGER_SKILLS = frozenset({
    "philo-dialectic", "xmodel", "deep-think",
    "dharma", "resonance",
})

# PreCognition 審查 System Prompt
# 融合 deep-think Phase 2 + philo-dialectic + xmodel 核心智慧
_PRECOG_SYSTEM_PROMPT = """\
你是 MUSEON 的元認知審查模組。審查一段即將發送給使用者的回覆。

五維度審查：
① 影響 — 這段話可能造成什麼正面/負面影響？有潛在傷害嗎？
② 假設 — 回覆中有哪些未驗證的假設？使用者可能不同意哪些前提？
③ 視角 — 是否只呈現單一觀點？有沒有其他重要觀點被遺漏？
④ 框架 — 是否被困在某個思維框架中？有無跨領域資源或破框思路可引入？
⑤ 真需 — 是否在回答使用者真正的需求，而非只回應表面文字？

判定規則：
- PASS：五項無重大問題 + 回覆已經回答使用者真正的需求
- REVISE（任一成立就建議修改）：
  a. 使用者明確要求「做/寫/產出」但回覆只給建議，沒有可交付物或具體行動
  b. 回覆隱含了 2 個以上未驗證的假設
  c. 回覆中有可能造成負面情緒的措辭（如說教、上對下）
  d. 回覆完全沒有提供使用者可以立即使用的東西（檔案/範本/連結/具體步驟）
- 輸出格式：只回覆「PASS」或 ≤150 字修改方向（不要重寫回覆）

重要：偏好行動，不要只給建議。使用者期待「被完成的事」而非「被建議的事」。"""

# ── PostCognition 反應類型 ──

# 預判指標：掃描 MUSEON 的回覆內容 → 推測使用者可能的反應
REACTION_INDICATORS: Dict[str, Dict[str, Any]] = {
    "acceptance": {
        "response_patterns": [
            "建議", "方案", "步驟", "計畫", "可以試試",
            "推薦", "這樣做", "策略",
        ],
        "confidence": 0.5,
    },
    "deepening": {
        "response_patterns": [
            "因為", "原因是", "本質上", "核心問題",
            "深層來看", "根本上",
        ],
        "confidence": 0.4,
    },
    "emotional": {
        "response_patterns": [
            "理解你", "感受到", "不容易", "辛苦了",
            "陪你", "心疼", "共鳴",
        ],
        "confidence": 0.6,
    },
    "pushback": {
        "response_patterns": [
            "應該", "必須", "一定要", "不能", "絕對",
            "你需要", "這是不對的",
        ],
        "confidence": 0.3,
    },
    "redirect": {
        "response_patterns": [
            "如果你想", "另外", "也可以考慮",
            "換個角度", "除此之外",
        ],
        "confidence": 0.3,
    },
    "follow_up": {
        "response_patterns": [
            "接下來", "下一步", "第一步", "首先",
            "然後", "第二", "第三",
        ],
        "confidence": 0.5,
    },
}

# 觀察指標：掃描使用者的新訊息 → 判定實際反應類型
REACTION_KEYWORDS: Dict[str, List[str]] = {
    "acceptance": [
        "好", "好的", "謝", "了解", "OK", "ok", "感謝",
        "收到", "明白", "嗯", "知道了", "對", "是的",
    ],
    "pushback": [
        "不是", "不對", "但是", "可是", "其實", "不是這樣",
        "我覺得不", "不同意", "不太", "錯了",
    ],
    "deepening": [
        "為什麼", "怎麼", "具體", "舉例", "詳細",
        "展開", "更多", "深入", "什麼意思",
    ],
    "emotional": [
        "感覺", "覺得", "開心", "難過", "感動",
        "謝謝你", "你真的", "溫暖", "安心",
    ],
    "redirect": [
        "另外", "還有", "換個", "其他", "不過我想",
        "別的", "順便", "話說",
    ],
    "follow_up": [
        "那", "所以", "接下來", "下一步", "然後",
        "那我", "怎麼開始", "第一步",
    ],
}

# 近似類型（用於 partial accuracy 計算）
_SIMILAR_TYPES: Dict[str, List[str]] = {
    "acceptance": ["follow_up"],
    "follow_up": ["acceptance", "deepening"],
    "deepening": ["follow_up"],
    "emotional": ["acceptance"],
    "pushback": ["redirect"],
    "redirect": ["pushback", "deepening"],
}


# ═══════════════════════════════════════════
# MetaCognitionEngine
# ═══════════════════════════════════════════


class MetaCognitionEngine:
    """元認知引擎：PreCognition + PostCognition.

    生命週期整合點（brain.py）：
      Step 0.7  → observe_reaction()     — 比對上次預判
      Step 6.2  → pre_review()           — 審查 draft response
      Step 9.7  → predict_reaction()     — 預判使用者反應
    """

    def __init__(
        self,
        pulse_db_path: str,
        brain: Any = None,
    ) -> None:
        self._brain = brain
        self._pulse_db = None

        try:
            from museclaw.pulse.pulse_db import PulseDB
            self._pulse_db = PulseDB(pulse_db_path)
        except Exception as e:
            logger.warning(f"MetaCognition PulseDB 連接失敗: {e}")

    # ════════════════════════════════════════
    # PreCognition — 回應前審查
    # ════════════════════════════════════════

    def should_review(
        self,
        routing_signal: Any = None,
        matched_skills: Optional[List[str]] = None,
        user_query: str = "",
    ) -> bool:
        """判斷是否需要觸發 PreCognition 審查.

        觸發條件（優先順序）：
        1. 安全觸發 (Tier A ≥ 0.5) → 必審
        2. SLOW_LOOP → 必審
        3. 匹配觸發技能 → 必審
        4. FAST_LOOP + 無安全 → 跳過
        5. 使用者問題 > 150 字 → 審查
        6. EXPLORATION_LOOP → 審查
        """
        skills = set(matched_skills or [])

        if routing_signal:
            # 安全觸發 → 必審
            try:
                if routing_signal.is_safety_triggered:
                    return True
            except AttributeError:
                pass

            # SLOW_LOOP → 必審
            try:
                if routing_signal.loop == "SLOW_LOOP":
                    return True
            except AttributeError:
                pass

            # FAST_LOOP → 跳過（速度優先）
            try:
                if routing_signal.loop == "FAST_LOOP":
                    return False
            except AttributeError:
                pass

        # 匹配觸發技能 → 必審
        if skills & _PRECOG_TRIGGER_SKILLS:
            return True

        # 複雜問題 → 審查
        if len(user_query) > 150:
            return True

        # EXPLORATION_LOOP → 審查
        if routing_signal:
            try:
                if routing_signal.loop == "EXPLORATION_LOOP":
                    return True
            except AttributeError:
                pass

        return False

    async def pre_review(
        self,
        draft_response: str,
        user_query: str,
        routing_signal: Any = None,
        matched_skills: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """執行 PreCognition 審查.

        Returns:
            {
                "verdict": "pass" | "revise" | "skipped",
                "feedback": str,  # 修改建議（verdict=revise 時有值）
                "review_time_ms": float,
            }
        """
        # 判斷是否觸發
        if not self.should_review(routing_signal, matched_skills, user_query):
            return {
                "verdict": "skipped",
                "feedback": "",
                "review_time_ms": 0.0,
            }

        # 無 brain → 跳過
        if not self._brain:
            return {
                "verdict": "skipped",
                "feedback": "no_brain",
                "review_time_ms": 0.0,
            }

        start_ms = time.time() * 1000

        # 組建審查上下文
        review_msg = (
            f"【使用者訊息】\n{user_query[:500]}\n\n"
            f"【即將發送的回覆】\n{draft_response[:1500]}"
        )

        # 呼叫 Haiku 審查
        try:
            result = await self._call_review_llm(review_msg)
        except Exception as e:
            logger.warning(f"PreCognition LLM 呼叫失敗: {e}")
            return {
                "verdict": "skipped",
                "feedback": f"llm_error: {e}",
                "review_time_ms": time.time() * 1000 - start_ms,
            }

        elapsed_ms = time.time() * 1000 - start_ms

        # 解析結果
        result_stripped = result.strip()
        if result_stripped.upper() == "PASS" or len(result_stripped) <= 10:
            verdict = "pass"
            feedback = ""
        else:
            verdict = "revise"
            feedback = result_stripped

        logger.info(
            f"[MetaCog] PreCognition: verdict={verdict}, "
            f"time={elapsed_ms:.0f}ms"
        )

        return {
            "verdict": verdict,
            "feedback": feedback,
            "review_time_ms": elapsed_ms,
        }

    async def _call_review_llm(self, review_message: str) -> str:
        """呼叫 Haiku 執行 PreCognition 審查."""
        if hasattr(self._brain, "_call_llm_with_model"):
            return await self._brain._call_llm_with_model(
                system_prompt=_PRECOG_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": review_message}],
                model=PRECOG_MODEL,
                max_tokens=PRECOG_MAX_TOKENS,
            )
        return ""

    # ════════════════════════════════════════
    # PostCognition — 雙向觀察迴路
    # ════════════════════════════════════════

    def predict_reaction(
        self,
        session_id: str,
        user_query: str,
        response: str,
        routing_signal: Any = None,
        matched_skills: Optional[List[str]] = None,
        pre_review: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """預判使用者對本次回覆的反應（純 CPU 啟發式，零 LLM 成本）.

        掃描 response 中的模式 → 選最高匹配度的預測。

        Returns:
            預判結果 dict，或 None（如 PulseDB 不可用）
        """
        if not self._pulse_db:
            return None

        # 掃描回覆內容，匹配反應指標
        best_type = "acceptance"  # 預設：使用者會接受
        best_score = 0.0
        best_confidence = 0.4

        for reaction_type, config in REACTION_INDICATORS.items():
            patterns = config["response_patterns"]
            base_confidence = config["confidence"]
            match_count = sum(1 for p in patterns if p in response)
            if match_count > best_score:
                best_score = match_count
                best_type = reaction_type
                best_confidence = min(0.9, base_confidence + match_count * 0.05)

        # v9.0: 使用者輸入語氣修正（不只看回覆，也看使用者的語氣）
        _CHALLENGE_WORDS = ["為什麼", "可是", "但是", "不是", "不對", "真的嗎",
                            "不能", "做不到", "沒辦法", "你只", "就這樣"]
        _FRUSTRATION_WORDS = ["失望", "不滿", "不爽", "爛", "差", "垃圾",
                              "浪費", "沒用", "廢話", "敷衍"]
        challenge_count = sum(1 for w in _CHALLENGE_WORDS if w in user_query)
        frustration_count = sum(1 for w in _FRUSTRATION_WORDS if w in user_query)

        if challenge_count >= 2 or frustration_count >= 1:
            # 使用者帶質疑/挫折語氣 → pushback 概率提高
            if best_type == "acceptance":
                best_type = "pushback"
                best_confidence = min(0.7, 0.3 + challenge_count * 0.1)
        elif challenge_count == 1 and best_type == "acceptance":
            # 輕微質疑 → 降低 acceptance 信心，可能是 deepening
            best_type = "deepening"
            best_confidence = 0.4

        # v9.0: 前次預判失敗補償 — 如果上次預判 acceptance 但實際不是，本次降低 acceptance
        try:
            if self._pulse_db and best_type == "acceptance":
                prev = self._pulse_db.get_latest_prediction(session_id)
                if prev and prev.get("predicted_reaction_type") == "acceptance":
                    actual = prev.get("actual_reaction_type")
                    if actual and actual != "acceptance":
                        # 上次猜 acceptance 但猜錯 → 本次改預測 follow_up
                        best_type = "follow_up"
                        best_confidence = 0.4
        except Exception:
            pass

        # 路由信號修正
        if routing_signal:
            try:
                # 安全觸發 → 更可能是情感回應
                if routing_signal.is_safety_triggered:
                    if best_type not in ("emotional", "acceptance"):
                        best_type = "emotional"
                        best_confidence = 0.5
            except AttributeError:
                pass

        # 生成預測描述
        _PREDICTION_TEMPLATES = {
            "acceptance": "使用者可能會接受建議或表示了解",
            "deepening": "使用者可能會追問更多細節或原因",
            "emotional": "使用者可能會有情感回應或表達感受",
            "pushback": "使用者可能會有不同看法或提出質疑",
            "redirect": "使用者可能會轉移到其他話題",
            "follow_up": "使用者可能會跟進下一步或行動",
        }
        predicted_reaction = _PREDICTION_TEMPLATES.get(
            best_type, "使用者可能會接受回覆內容"
        )

        # 儲存到 PulseDB
        metacog_id = f"mc_{uuid.uuid4().hex[:12]}"
        try:
            # 取得 pre_review 資訊
            pre_triggered = False
            pre_verdict = "skipped"
            pre_feedback = ""
            pre_revision_applied = False
            pre_review_time_ms = 0.0

            if pre_review:
                pre_verdict = pre_review.get("verdict", "skipped")
                pre_triggered = pre_verdict != "skipped"
                pre_feedback = pre_review.get("feedback", "")
                pre_revision_applied = pre_verdict == "revise"
                pre_review_time_ms = pre_review.get("review_time_ms", 0.0)

            self._pulse_db.add_metacognition(
                metacog_id=metacog_id,
                session_id=session_id,
                pre_triggered=pre_triggered,
                pre_verdict=pre_verdict,
                pre_feedback=pre_feedback[:500] if pre_feedback else None,
                pre_revision_applied=pre_revision_applied,
                pre_review_time_ms=pre_review_time_ms,
                predicted_reaction_type=best_type,
                predicted_reaction=predicted_reaction,
                prediction_confidence=best_confidence,
                routing_loop=getattr(routing_signal, "loop", None),
                routing_mode=getattr(routing_signal, "mode", None),
                matched_skills=list(matched_skills) if matched_skills else None,
                user_message_snippet=user_query[:100],
                response_snippet=response[:100],
            )
        except Exception as e:
            logger.warning(f"MetaCognition 儲存失敗: {e}")
            return None

        return {
            "id": metacog_id,
            "predicted_type": best_type,
            "predicted_reaction": predicted_reaction,
            "confidence": best_confidence,
        }

    def observe_reaction(
        self,
        session_id: str,
        current_user_message: str,
    ) -> Optional[Dict[str, Any]]:
        """比對上次預判 vs 本次使用者實際反應（純 CPU）.

        在每次 process() 開頭呼叫，查看上次的預判是否準確。

        Returns:
            觀察結果 dict，或 None（如無預判或 PulseDB 不可用）
        """
        if not self._pulse_db:
            return None

        # 取得最後一筆未觀察的預測
        try:
            prediction = self._pulse_db.get_latest_prediction(session_id)
        except Exception as e:
            logger.debug(f"取得預測記錄失敗: {e}")
            return None

        if not prediction:
            return None

        predicted_type = prediction.get("predicted_reaction_type")
        if not predicted_type:
            return None

        # 判定使用者實際反應類型
        actual_type = self._classify_reaction(current_user_message)

        # 計算準確率
        accuracy = self._compute_accuracy(predicted_type, actual_type)

        # 更新 PulseDB
        try:
            self._pulse_db.update_observation(
                metacog_id=prediction["id"],
                actual_reaction_type=actual_type,
                prediction_accuracy=accuracy,
                accuracy_method="cpu_heuristic",
            )
        except Exception as e:
            logger.warning(f"更新觀察結果失敗: {e}")

        return {
            "id": prediction["id"],
            "predicted_type": predicted_type,
            "actual_type": actual_type,
            "prediction_accuracy": accuracy,
        }

    def _classify_reaction(self, message: str) -> str:
        """分類使用者訊息的反應類型（純 CPU 關鍵詞匹配）."""
        best_type = "acceptance"  # 預設
        best_score = 0

        for reaction_type, keywords in REACTION_KEYWORDS.items():
            score = 0
            for kw in keywords:
                if kw in message:
                    # 短關鍵詞（1-2 字）要求完整匹配或詞首
                    if len(kw) <= 2:
                        # 簡單位置檢查：出現在開頭或被標點/空格包圍
                        idx = message.find(kw)
                        if idx == 0 or (idx > 0 and message[idx - 1] in "，。！？\n "):
                            score += 2
                        else:
                            score += 1
                    else:
                        score += 2
            if score > best_score:
                best_score = score
                best_type = reaction_type

        return best_type

    def _compute_accuracy(self, predicted: str, actual: str) -> float:
        """計算預判準確率.

        完全匹配 = 1.0
        近似類型 = 0.6
        不匹配 = 0.0
        """
        if predicted == actual:
            return 1.0

        similar = _SIMILAR_TYPES.get(predicted, [])
        if actual in similar:
            return 0.6

        return 0.0

    # ════════════════════════════════════════
    # 演化信號
    # ════════════════════════════════════════

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """取得元認知統計（供 ProactiveBridge / WEE）."""
        if not self._pulse_db:
            return {}

        try:
            accuracy_stats = self._pulse_db.get_prediction_accuracy_stats(days)
            precog_stats = self._pulse_db.get_precognition_stats(days)
            return {
                "avg_accuracy": accuracy_stats.get("avg_accuracy"),
                "accuracy_total": accuracy_stats.get("total", 0),
                "accuracy_by_type": accuracy_stats.get("by_type", {}),
                "revision_rate": precog_stats.get("revision_rate", 0),
                "trigger_rate": precog_stats.get("trigger_rate", 0),
                "precog_total": precog_stats.get("total", 0),
            }
        except Exception as e:
            logger.debug(f"元認知統計查詢失敗: {e}")
            return {}

    def compute_evolution_signal(self, days: int = 7) -> Dict[str, Any]:
        """計算演化信號（供 WEE / morphenix）."""
        stats = self.get_stats(days)
        if not stats or stats.get("accuracy_total", 0) < 5:
            return {"sufficient_data": False}

        avg_acc = stats.get("avg_accuracy", 0.5)
        by_type = stats.get("accuracy_by_type", {})

        # 找出弱項和強項
        weak = [t for t, a in by_type.items() if a < 0.4]
        strong = [t for t, a in by_type.items() if a >= 0.7]

        # 趨勢判斷（簡化：用近 3 天 vs 前 4 天比較）
        trend = "stable"
        try:
            recent = self._pulse_db.get_prediction_accuracy_stats(3)
            older = self._pulse_db.get_prediction_accuracy_stats(7)
            r_acc = recent.get("avg_accuracy", 0.5)
            o_acc = older.get("avg_accuracy", 0.5)
            if r_acc - o_acc > 0.1:
                trend = "improving"
            elif o_acc - r_acc > 0.1:
                trend = "declining"
        except Exception:
            pass

        return {
            "sufficient_data": True,
            "avg_prediction_accuracy": avg_acc,
            "revision_rate": stats.get("revision_rate", 0),
            "weak_prediction_domains": weak,
            "strong_prediction_domains": strong,
            "trend": trend,
        }
