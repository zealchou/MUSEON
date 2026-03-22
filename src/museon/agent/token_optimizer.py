"""Token Optimizer — LayeredContent 三層壓縮 + TokenBudget 預算制.

依據 DNA27 Neural Tract BDD Spec §5-6 實作：
  - LayeredContent: essence (~10%) / compact (~30%) / full (100%)
  - TokenBudget: 六區預算（core_system/persona/modules/memory/buffer/strategic）
  - 零 LLM 語義重要性打分（純 regex + 位置啟發）

設計原則：
  - 所有壓縮邏輯為純 CPU，不耗 API token
  - 壓縮結果保持原始行順序（非依分數排序）
  - token_cache 避免重複計算
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Constants (BDD Spec §17)
# ═══════════════════════════════════════════

_DEFAULT_TOTAL_BUDGET = 18500  # +1300 for soul context + crystal injection

_DEFAULT_ZONES: Dict[str, int] = {
    "core_system": 3000,
    "persona": 1500,
    "modules": 6000,
    "memory": 2500,   # +500 for knowledge crystal auto_recall injection
    "buffer": 1800,   # +800 for PULSE.md soul context injection
    "strategic": 1000,  # 企業決策脈絡注入
}

_DEFAULT_THRESHOLDS: Dict[str, float] = {
    "full": 1.0,
    "compact": 0.5,
    "essence": 0.2,
}

_ESSENCE_MAX_CHARS = 250
_COMPACT_MAX_CHARS = 900

# Semantic importance scoring patterns (BDD Spec §6.2)
_HEADING_RE = re.compile(r"^#{1,4}\s+.+")
_LABEL_RE = re.compile(r"^[【「\[].+?[】」\]]")
_JSON_KEY_RE = re.compile(r'^\s*"[\w_-]+":\s')
_SECTION_RE = re.compile(r"^[（(].+?[）)]")
_LIST_ITEM_RE = re.compile(r"^\s*[-*•]\s+|^\d+[.)]\s")
_DEFINITION_KW_RE = re.compile(
    r"(?:定義|核心|目的|原則|規則|使命|價值|架構|觸發|條件|"
    r"流程|策略|模式|機制|方法|協議|標準|要求|禁止|必須)"
)
_DECORATION_RE = re.compile(r"^(?:---+|===+|```|═+|\*\*\*+)\s*$")


# ═══════════════════════════════════════════
# LayeredContent
# ═══════════════════════════════════════════


@dataclass
class LayeredContent:
    """三層壓縮內容.

    - essence: ~10%（標題 + 核心關鍵字），≤250 chars
    - compact: ~30%（結構化摘要），≤900 chars
    - full:    100%（原始全文）
    """

    module_id: str
    essence: str = ""
    compact: str = ""
    full: str = ""


def _score_line(line: str, position_ratio: float) -> float:
    """計算單行的語義重要性分數.

    Args:
        line: 文本行
        position_ratio: 行在文件中的位置比 (0.0 ~ 1.0)

    Returns:
        重要性分數 (0.0 ~ 1.0)
    """
    stripped = line.strip()
    if not stripped:
        return 0.0
    if _DECORATION_RE.match(stripped):
        return 0.0

    score = 0.0

    # Pattern matching (additive)
    if _HEADING_RE.match(stripped):
        score += 0.9
    if _LABEL_RE.match(stripped):
        score += 0.8
    if _JSON_KEY_RE.match(stripped):
        score += 0.7
    if _SECTION_RE.match(stripped):
        score += 0.7
    if _LIST_ITEM_RE.match(stripped):
        score += 0.4
    if _DEFINITION_KW_RE.search(stripped):
        score += 0.3

    # Position bonus
    if position_ratio < 0.1:
        score += 0.2
    elif position_ratio < 0.3:
        score += 0.1

    # Long line penalty
    if len(stripped) > 200:
        score *= 0.6

    return min(score, 1.0)


def auto_extract_essence(text: str, max_chars: int = _ESSENCE_MAX_CHARS) -> str:
    """零 LLM 萃取 essence 層（~10%）.

    選取重要性最高的行，保持原始行順序，≤max_chars。
    """
    if not text:
        return ""

    lines = text.splitlines()
    total = len(lines) or 1

    scored: List[Tuple[int, float, str]] = []
    for i, line in enumerate(lines):
        s = _score_line(line, i / total)
        if s > 0:
            scored.append((i, s, line.strip()))

    # 按分數排序選取，直到超過字數上限
    scored.sort(key=lambda x: x[1], reverse=True)

    selected_indices = set()
    char_count = 0
    for idx, score, text_line in scored:
        if char_count + len(text_line) + 1 > max_chars:
            break
        selected_indices.add(idx)
        char_count += len(text_line) + 1  # +1 for newline

    # 按原始行順序重組
    result_lines = [
        scored_item[2]
        for scored_item in sorted(
            (s for s in scored if s[0] in selected_indices),
            key=lambda x: x[0],
        )
    ]

    return "\n".join(result_lines)


def auto_extract_compact(text: str, max_chars: int = _COMPACT_MAX_CHARS) -> str:
    """零 LLM 萃取 compact 層（~30%）.

    保留標題 + 標籤 + 列表項 + 定義行，≤max_chars。
    """
    if not text:
        return ""

    lines = text.splitlines()
    total = len(lines) or 1

    scored: List[Tuple[int, float, str]] = []
    for i, line in enumerate(lines):
        s = _score_line(line, i / total)
        if s >= 0.3:  # compact threshold: 保留中等以上重要性
            scored.append((i, s, line.strip()))

    # 按分數排序選取
    scored.sort(key=lambda x: x[1], reverse=True)

    selected_indices = set()
    char_count = 0
    for idx, score, text_line in scored:
        if char_count + len(text_line) + 1 > max_chars:
            break
        selected_indices.add(idx)
        char_count += len(text_line) + 1

    # 按原始行順序重組
    result_lines = [
        scored_item[2]
        for scored_item in sorted(
            (s for s in scored if s[0] in selected_indices),
            key=lambda x: x[0],
        )
    ]

    return "\n".join(result_lines)


def build_layered_content(module_id: str, full_text: str) -> LayeredContent:
    """建構三層壓縮內容."""
    return LayeredContent(
        module_id=module_id,
        essence=auto_extract_essence(full_text),
        compact=auto_extract_compact(full_text),
        full=full_text,
    )


def select_layer(content: LayeredContent, score: float) -> str:
    """根據重要性分數選擇適當的層.

    Thresholds (BDD Spec §5.3):
      - score >= 1.0 → full
      - score >= 0.5 → compact
      - score >= 0.2 → essence
      - score <  0.2 → skip (empty string)
    """
    if score >= _DEFAULT_THRESHOLDS["full"]:
        return content.full
    elif score >= _DEFAULT_THRESHOLDS["compact"]:
        return content.compact
    elif score >= _DEFAULT_THRESHOLDS["essence"]:
        return content.essence
    else:
        return ""


# ═══════════════════════════════════════════
# Token Estimation
# ═══════════════════════════════════════════

# Cache to avoid recomputation
_token_cache: Dict[int, int] = {}


def estimate_tokens(text: str) -> int:
    """估算文本的 token 數.

    BDD Spec: 中文 len//2, 英文 len//4。
    這裡用混合比估算：中文佔比越高越接近 len//2。
    """
    text_id = id(text)
    if text_id in _token_cache:
        return _token_cache[text_id]

    if not text:
        _token_cache[text_id] = 0
        return 0

    # 計算中文字元比例
    cjk_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    total = len(text) or 1
    cjk_ratio = cjk_count / total

    # 加權平均：中文 //2, 英文 //4
    tokens = int(len(text) * (cjk_ratio / 2 + (1 - cjk_ratio) / 4))
    tokens = max(tokens, 1)

    _token_cache[text_id] = tokens
    return tokens


def clear_token_cache() -> None:
    """清空 token 估算快取."""
    _token_cache.clear()


# ═══════════════════════════════════════════
# TokenBudget Zone Manager
# ═══════════════════════════════════════════


class TokenBudget:
    """五區 token 預算管理器.

    Zones (BDD Spec §5.2):
      - core_system: 3000 (DNA27 core, always full)
      - persona:     1500
      - modules:     6000
      - memory:      2000
      - buffer:      2000
      Total: 17200

    Dynamic allocation (BDD Spec §5.2):
      - when max(tier_scores) > 1.0: modules gets +20% from buffer
    """

    def __init__(
        self,
        zones: Optional[Dict[str, int]] = None,
        total_budget: int = _DEFAULT_TOTAL_BUDGET,
    ):
        self._zones = dict(zones or _DEFAULT_ZONES)
        self._total_budget = total_budget
        self._usage: Dict[str, int] = {k: 0 for k in self._zones}

    def apply_dynamic_allocation(self, max_tier_score: float) -> None:
        """依據最高 tier score 動態調整預算.

        BDD Spec §5.2: max(tier_scores) > 1.0 → modules +20% from buffer.
        """
        if max_tier_score > 1.0:
            bonus = min(
                self._zones.get("buffer", 0),
                self._zones.get("modules", 0) // 5,
            )
            self._zones["modules"] = self._zones.get("modules", 0) + bonus
            self._zones["buffer"] = self._zones.get("buffer", 0) - bonus
            logger.debug(
                f"TokenBudget dynamic: modules +{bonus}, "
                f"buffer -{bonus}"
            )

    def track_usage(self, zone: str, tokens: int) -> None:
        """記錄某區的 token 使用量."""
        if zone in self._usage:
            self._usage[zone] += tokens

    def remaining(self, zone: str) -> int:
        """取得某區剩餘 token."""
        budget = self._zones.get(zone, 0)
        used = self._usage.get(zone, 0)
        return max(budget - used, 0)

    def is_exhausted(self, zone: str) -> bool:
        """檢查某區是否已用完."""
        return self.remaining(zone) <= 0

    def get_zone_budget(self, zone: str) -> int:
        """取得某區的預算上限."""
        return self._zones.get(zone, 0)

    def get_usage(self, zone: str) -> int:
        """取得某區已用量."""
        return self._usage.get(zone, 0)

    def get_all_zones(self) -> Dict[str, Dict[str, int]]:
        """取得所有區的預算 / 已用 / 剩餘."""
        result = {}
        for zone in self._zones:
            result[zone] = {
                "budget": self._zones[zone],
                "used": self._usage.get(zone, 0),
                "remaining": self.remaining(zone),
            }
        return result

    def fit_text_to_zone(self, zone: str, text: str) -> str:
        """將文本截斷到區預算內，並記錄用量.

        Returns:
            截斷後的文本（可能為空字串）
        """
        if self.is_exhausted(zone):
            return ""

        tokens = estimate_tokens(text)
        budget_left = self.remaining(zone)

        if tokens <= budget_left:
            self.track_usage(zone, tokens)
            return text

        # 需要截斷：按比例截斷
        ratio = budget_left / tokens if tokens > 0 else 0
        max_chars = int(len(text) * ratio)
        truncated = text[:max_chars]
        actual_tokens = estimate_tokens(truncated)
        self.track_usage(zone, actual_tokens)
        return truncated

    def reset(self) -> None:
        """重置所有區的使用量."""
        self._usage = {k: 0 for k in self._zones}


# ═══════════════════════════════════════════
# Prompt Caching Helper
# ═══════════════════════════════════════════


def build_cached_system_blocks(
    static_core: str,
    dynamic_sections: List[Dict[str, str]],
) -> List[Dict]:
    """建構帶 cache_control 的 system content blocks.

    BDD Spec §14: static_core 標記 cache_control: {"type": "ephemeral"}，
    動態區段不標記。

    Args:
        static_core: DNA27 核心 + identity（跨 turn 不變）
        dynamic_sections: 動態區段 [{"label": "...", "text": "..."}]

    Returns:
        Anthropic Messages API 的 system content blocks list
    """
    blocks = []

    # Static core — 標記 cache
    if static_core:
        blocks.append({
            "type": "text",
            "text": static_core,
            "cache_control": {"type": "ephemeral"},
        })

    # Dynamic sections — 不標記 cache
    for section in dynamic_sections:
        text = section.get("text", "")
        if text:
            blocks.append({
                "type": "text",
                "text": text,
            })

    return blocks
