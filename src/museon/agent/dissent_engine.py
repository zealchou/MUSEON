"""Dissent Engine — MUSEON's ability to express disagreement.

Compares incoming messages against Crystal Lattice beliefs.
If contradiction found, generates a dissent signal with appropriate
expression based on Growth Stage constraints.

MUSEON is not a yes-machine. It has its own beliefs (Crystal Lattice)
and expresses them based on cognitive maturity (Growth Stage).
"""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 否定/警示關鍵詞（中文）
# ---------------------------------------------------------------------------

NEGATION_KEYWORDS: List[str] = [
    "不要", "避免", "禁止", "別", "不應該", "小心", "注意",
    "風險", "教訓", "不可", "防止", "嚴禁", "慎重", "謹慎",
    "不能", "不該", "不宜", "需防", "務必不",
]

# ---------------------------------------------------------------------------
# 成長階段回應模板
# ---------------------------------------------------------------------------

TEMPLATES: Dict[str, List[str]] = {
    "ABSORB": [
        "我有個疑問……{crystal_summary}，你覺得這裡會不會有風險？",
        "我之前學到 {crystal_summary}，這跟你現在說的好像有點不一樣？",
        "嗯，{crystal_summary}——這個方向你有想到嗎？",
    ],
    "FORM": [
        "我傾向不太同意，因為根據我的經驗 {crystal_summary}。你怎麼看？",
        "也許可以再想想——{crystal_directive}",
        "我的判斷是 {crystal_summary}，不確定跟你想的一不一樣？",
    ],
    "STAND": [
        "我不同意這個方向。{crystal_summary}，理由是 {crystal_directive}。",
        "這與我的判斷不同。根據 {crystal_summary}，我建議 {crystal_directive}。",
        "我有不同看法：{crystal_summary}。{crystal_directive}",
    ],
    "TRANSCEND": [
        "你的思路在 A 框架下成立，但換到 B 框架來看：{crystal_summary}——結論可能完全不同。",
        "我認為這裡有個隱藏的前提需要檢視。{crystal_directive}",
        "有趣的角度——不過 {crystal_summary}，從另一個維度看這件事會得到截然不同的結論。",
    ],
}

# ---------------------------------------------------------------------------
# 資料結構
# ---------------------------------------------------------------------------


@dataclass
class DissentSignal:
    """Result of dissent check."""

    should_dissent: bool = False
    strength: float = 0.0                              # 0-1
    contradicted_crystals: list = field(default_factory=list)  # Crystal summaries
    expression_template: str = ""                      # Stage-appropriate phrasing
    dissent_context: str = ""                          # Brief context for prompt injection
    stage_capped: bool = False                         # True if stage prevented stronger dissent


# ---------------------------------------------------------------------------
# DissentEngine
# ---------------------------------------------------------------------------


class DissentEngine:
    """MUSEON 的異議表達引擎。

    純關鍵詞匹配，無 LLM 呼叫，設計用於 brain.py Step 3.66 的即時路徑。
    """

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)
        self._crystal_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_mtime: float = 0.0

    # ------------------------------------------------------------------
    # 公開入口
    # ------------------------------------------------------------------

    def check(
        self,
        message: str,
        anima_mc: Any = None,
        crystal_store_path: Optional[Path] = None,
        growth_stage_constraints: Optional[Dict[str, Any]] = None,
    ) -> DissentSignal:
        """主入口：掃描訊息是否與 Crystal Lattice 有衝突。

        Args:
            message: 使用者的訊息文字。
            anima_mc: ANIMA 狀態（保留備用，目前未使用）。
            crystal_store_path: 覆寫 crystal_rules.json 路徑（選填）。
            growth_stage_constraints: 成長階段約束 dict，需含 "stage"、"initiative_cap" 等欄位。

        Returns:
            DissentSignal — 若無衝突 should_dissent=False。
        """
        rules = self._load_rules(crystal_store_path)
        if not rules:
            return DissentSignal()

        contradictions = self._find_contradictions(message, rules)
        if not contradictions:
            return DissentSignal()

        # 成長階段設定
        stage = "ABSORB"
        initiative_cap = 0.2
        stage_capped = False

        if growth_stage_constraints:
            stage = growth_stage_constraints.get("stage", "ABSORB")
            initiative_cap = float(growth_stage_constraints.get("initiative_cap", 0.2))

        raw_strength = self._compute_dissent_strength(contradictions, initiative_cap=1.0)
        capped_strength = self._compute_dissent_strength(contradictions, initiative_cap=initiative_cap)

        if raw_strength > capped_strength:
            stage_capped = True

        if capped_strength < 0.2:
            return DissentSignal()

        top = contradictions[0]
        expression = self._get_expression_template(stage, capped_strength, top)

        signal = DissentSignal(
            should_dissent=True,
            strength=capped_strength,
            contradicted_crystals=[c["crystal"] for c in contradictions],
            expression_template=expression,
            stage_capped=stage_capped,
        )
        signal.dissent_context = self.build_dissent_context(signal)
        return signal

    # ------------------------------------------------------------------
    # 內部方法
    # ------------------------------------------------------------------

    def _load_rules(self, override_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        """從 crystal_rules.json 載入規則，帶快取與防禦性處理。"""
        path = override_path or (self.workspace / "_system" / "crystal_rules.json")

        try:
            mtime = path.stat().st_mtime
            if self._crystal_cache is not None and mtime == self._cache_mtime:
                return self._crystal_cache

            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            # 支援 {"rules": [...]} 或直接 [...]
            if isinstance(raw, dict):
                rules = raw.get("rules", [])
            elif isinstance(raw, list):
                rules = raw
            else:
                rules = []

            # 只保留 active 規則
            active = [r for r in rules if r.get("status", "active") == "active"]
            self._crystal_cache = active
            self._cache_mtime = mtime
            return active

        except FileNotFoundError:
            logger.debug("crystal_rules.json not found at %s — dissent disabled", path)
            return []
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load crystal_rules.json: %s", exc)
            return []

    def _find_contradictions(
        self,
        message: str,
        rules: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """掃描 Crystal 規則，找出與訊息意圖矛盾的規則。

        策略（純關鍵詞，無 LLM）：
        1. 提取訊息的主題字元 n-gram（中文）+ 英文 token（小寫）
        2. 對每條 active 規則：
           - 若 directive/summary 含否定/警示關鍵詞 → 候選規則
           - 計算中文 n-gram 重疊率 OR 英文 token 命中
           - 任一維度有交集且有否定詞 → 視為矛盾
        3. 回傳按分數排序的前 3 筆
        """
        msg_ngrams = self._extract_ngrams(message, n=2)
        msg_ngrams |= self._extract_ngrams(message, n=3)
        msg_tokens = self._extract_english_tokens(message)

        results: List[Dict[str, Any]] = []

        for rule in rules:
            summary = rule.get("summary", "")
            directive = rule.get("directive", "")
            combined = summary + " " + directive

            # 檢查是否含否定/警示詞
            has_negation = any(kw in combined for kw in NEGATION_KEYWORDS)
            if not has_negation:
                continue

            # 計算中文 n-gram 重疊
            rule_ngrams = self._extract_ngrams(combined, n=2)
            rule_ngrams |= self._extract_ngrams(combined, n=3)
            rule_tokens = self._extract_english_tokens(combined)

            ngram_overlap_ratio: float = 0.0
            if rule_ngrams and msg_ngrams:
                overlap = msg_ngrams & rule_ngrams
                ngram_overlap_ratio = len(overlap) / max(len(msg_ngrams), 1)

            # 英文 token 命中加分（工具名、指令名等）
            token_overlap_ratio: float = 0.0
            if rule_tokens and msg_tokens:
                token_overlap = msg_tokens & rule_tokens
                token_overlap_ratio = len(token_overlap) / max(len(msg_tokens), 1)

            combined_overlap = max(ngram_overlap_ratio, token_overlap_ratio)
            if combined_overlap <= 0:
                continue

            strength = float(rule.get("strength", 1.0))
            crystal_ri = float(rule.get("crystal_ri", 1.0))
            score = combined_overlap * min(strength, 3.0) / 3.0 * crystal_ri

            results.append({
                "score": score,
                "overlap_ratio": combined_overlap,
                "crystal": {
                    "rule_id": rule.get("rule_id", ""),
                    "summary": summary,
                    "directive": directive,
                    "strength": strength,
                    "crystal_ri": crystal_ri,
                },
            })

        # 按分數降序，取前 3
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:3]

    def _compute_dissent_strength(
        self,
        contradictions: List[Dict[str, Any]],
        initiative_cap: float = 1.0,
    ) -> float:
        """計算異議強度，由 initiative_cap 控制上限。"""
        if not contradictions:
            return 0.0
        raw = sum(c["score"] for c in contradictions) / len(contradictions)
        return min(raw, initiative_cap)

    def _get_expression_template(
        self,
        stage: str,
        strength: float,
        top_contradiction: Dict[str, Any],
    ) -> str:
        """根據成長階段選取表達模板並填入 crystal 資料。"""
        stage_key = stage if stage in TEMPLATES else "ABSORB"
        templates = TEMPLATES[stage_key]
        template = random.choice(templates)

        crystal = top_contradiction.get("crystal", {})
        summary = crystal.get("summary", "")
        directive = crystal.get("directive", "")

        # 截斷過長的 directive 以保持可讀性
        if len(directive) > 50:
            directive = directive[:50] + "……"

        try:
            return template.format(
                crystal_summary=summary,
                crystal_directive=directive,
            )
        except KeyError:
            return f"{summary}——{directive}"

    # ------------------------------------------------------------------
    # 輸出方法
    # ------------------------------------------------------------------

    def build_dissent_context(self, signal: DissentSignal) -> str:
        """生成注入 system prompt required_elements 的分歧提示字串。"""
        if not signal.should_dissent:
            return ""
        return (
            f"[分歧提示] 使用者的請求與你的信念有衝突（強度 {signal.strength:.0%}）。"
            f"{signal.expression_template}"
        )

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_ngrams(text: str, n: int = 2) -> set:
        """提取中文字元 n-gram（不用 jieba，純字元切割）。"""
        # 只保留中文字元（CJK Unified Ideographs）
        chinese_only = re.sub(r"[^\u4e00-\u9fff\u3400-\u4dbf]", "", text)
        if len(chinese_only) < n:
            return set()
        return {chinese_only[i : i + n] for i in range(len(chinese_only) - n + 1)}

    @staticmethod
    def _extract_english_tokens(text: str) -> set:
        """提取英文小寫 token（工具名、指令名等），長度 ≥ 2。"""
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_\-]{1,}", text)
        return {t.lower() for t in tokens}
