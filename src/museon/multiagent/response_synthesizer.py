"""Response Synthesizer — 多部門回覆重組引擎.

DNA-Inspired 升級（原 Phase 4.5 → Recombination Engine）：
從「主部門 + 補充拼貼」升級為「片段評分 + 交叉重組」。

DNA 類比：
- 舊模式 = DNA 複製（主鏈完整保留 + 輔助鏈截斷附註）
- 新模式 = 染色體交叉互換（Crossover）：
  1. 將主部門和輔助部門的回覆拆成段落（片段）
  2. 對每個片段進行多維評分（相關性、資訊密度、可操作性）
  3. 以主部門為骨架，在特定位置用輔助部門的更優片段替換
  4. 最終輸出是真正的集體智慧，而非拼貼

三種合成模式：
- SIMPLE: 只有主部門，直接回傳（無重組）
- ANNOTATED: 主部門 + 輔助部門簡短註解（舊模式，向後相容）
- RECOMBINED: 片段評分 + 交叉重組（新模式）
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from museon.multiagent.multi_agent_executor import (
    DepartmentResponse,
    MultiAgentResult,
)

logger = logging.getLogger(__name__)

# 合成模式
SYNTHESIS_SIMPLE = "simple"          # 只用主部門
SYNTHESIS_ANNOTATED = "annotated"    # 主部門 + 輔助註解（向後相容）
SYNTHESIS_RECOMBINED = "recombined"  # 片段評分 + 交叉重組（DNA 模式）

# 重組參數
MIN_FRAGMENT_LENGTH = 20         # 片段最小有效長度（字元）
RELEVANCE_WEIGHT = 0.4           # 相關性權重
DENSITY_WEIGHT = 0.3             # 資訊密度權重
ACTIONABILITY_WEIGHT = 0.3       # 可操作性權重
REPLACEMENT_THRESHOLD = 0.25     # 輔助片段分數需高出主片段此比例才替換


# ═══════════════════════════════════════════
# 片段評分資料結構
# ═══════════════════════════════════════════

@dataclass
class ScoredFragment:
    """帶評分的文字片段."""

    text: str
    source_dept: str             # 來源部門 ID
    source_emoji: str            # 來源部門圖標
    relevance: float = 0.0       # 與使用者問題的相關性 (0-1)
    density: float = 0.0         # 資訊密度 (0-1)
    actionability: float = 0.0   # 可操作性 (0-1)

    @property
    def composite_score(self) -> float:
        """加權綜合分數."""
        return (
            self.relevance * RELEVANCE_WEIGHT
            + self.density * DENSITY_WEIGHT
            + self.actionability * ACTIONABILITY_WEIGHT
        )


# ═══════════════════════════════════════════
# 公開 API
# ═══════════════════════════════════════════

def synthesize(
    result: MultiAgentResult,
    mode: str = SYNTHESIS_RECOMBINED,
) -> str:
    """合成多部門回覆.

    策略：
    - 只有主部門 → 直接回傳
    - ANNOTATED → 主回覆 + 補充觀點（向後相容）
    - RECOMBINED → 片段評分 + 交叉重組（DNA 模式）
    """
    if not result.auxiliaries:
        return result.primary.response

    if mode == SYNTHESIS_ANNOTATED:
        return _annotated_synthesis(result.primary, result.auxiliaries)

    return _recombined_synthesis(result.primary, result.auxiliaries)


# ═══════════════════════════════════════════
# 向後相容：帶註解的合成（舊模式）
# ═══════════════════════════════════════════

def _annotated_synthesis(
    primary: DepartmentResponse,
    auxiliaries: List[DepartmentResponse],
) -> str:
    """帶註解的合成：主回覆 + 輔助部門補充."""
    parts = [primary.response]

    valid_aux = [
        a for a in auxiliaries
        if a.response and not a.error and len(a.response.strip()) > 10
    ]

    if not valid_aux:
        return primary.response

    supplements = []
    for aux in valid_aux:
        summary = _extract_key_insight(aux.response)
        if summary:
            supplements.append(f"- {aux.emoji} **{aux.dept_name}**：{summary}")

    if supplements:
        parts.append("\n\n---\n💡 **多角度補充**：")
        parts.extend(supplements)

    return "\n".join(parts)


# ═══════════════════════════════════════════
# DNA 模式：片段評分 + 交叉重組
# ═══════════════════════════════════════════

def _recombined_synthesis(
    primary: DepartmentResponse,
    auxiliaries: List[DepartmentResponse],
) -> str:
    """染色體交叉重組模式.

    流程：
    1. 拆段：將所有回覆拆成段落片段
    2. 評分：對每個片段進行多維評分
    3. 比對：逐段比較主部門 vs 輔助部門片段
    4. 重組：用更優片段替換主部門的弱段落
    5. 標注：被替換的段落標註來源
    """
    valid_aux = [
        a for a in auxiliaries
        if a.response and not a.error and len(a.response.strip()) > 10
    ]

    if not valid_aux:
        return primary.response

    # Step 1: 拆段
    primary_fragments = _split_into_fragments(
        primary.response, primary.dept_id, primary.emoji
    )
    aux_fragments_pool: List[ScoredFragment] = []
    for aux in valid_aux:
        aux_fragments_pool.extend(
            _split_into_fragments(aux.response, aux.dept_id, aux.emoji)
        )

    if not primary_fragments:
        return primary.response

    # Step 2: 評分
    _score_fragments(primary_fragments)
    _score_fragments(aux_fragments_pool)

    # Step 3 & 4: 比對 + 重組
    recombined, replacements = _crossover(primary_fragments, aux_fragments_pool)

    # Step 5: 組裝輸出
    output_parts = [f.text for f in recombined]
    result_text = "\n\n".join(output_parts)

    # 如果有替換發生，附加來源標註
    if replacements:
        sources = set()
        for dept_id, emoji, dept_name in replacements:
            sources.add(f"{emoji} {dept_name}")
        source_note = "、".join(sources)
        result_text += f"\n\n---\n🧬 *本回覆融合了{source_note}的觀點*"

    return result_text


def _split_into_fragments(
    text: str,
    dept_id: str,
    emoji: str,
) -> List[ScoredFragment]:
    """將回覆文字拆成段落片段.

    分割規則：
    - 以雙換行（空行）為主分隔符
    - 過短片段（< MIN_FRAGMENT_LENGTH）向前合併
    - Markdown 標題行保留為段落前綴
    """
    # 以空行分割
    raw_parts = re.split(r"\n\s*\n", text.strip())
    fragments: List[ScoredFragment] = []

    for part in raw_parts:
        part = part.strip()
        if not part:
            continue

        if len(part) < MIN_FRAGMENT_LENGTH and fragments:
            # 過短片段合併到前一個
            fragments[-1].text += "\n\n" + part
        else:
            fragments.append(ScoredFragment(
                text=part,
                source_dept=dept_id,
                source_emoji=emoji,
            ))

    return fragments


def _score_fragments(fragments: List[ScoredFragment]) -> None:
    """對片段進行多維評分（純 CPU 啟發式，零 LLM 成本）.

    三維度：
    - 相關性（relevance）：是否包含實質內容（非套話/問候）
    - 資訊密度（density）：單位長度中的資訊量
    - 可操作性（actionability）：是否包含可執行的建議
    """
    for f in fragments:
        f.relevance = _score_relevance(f.text)
        f.density = _score_density(f.text)
        f.actionability = _score_actionability(f.text)


def _score_relevance(text: str) -> float:
    """相關性評分：是否包含實質內容."""
    score = 0.5  # 基準分

    # 包含具體數據/數字 → 加分
    if re.search(r"\d+", text):
        score += 0.15

    # 包含 Markdown 格式（結構化思考） → 加分
    if re.search(r"[-*]\s|^\d+\.", text, re.MULTILINE):
        score += 0.1

    # 包含引用或例子 → 加分
    if any(w in text for w in ["例如", "比如", "舉例", "案例", "instance"]):
        score += 0.1

    # 純問候/套話 → 減分
    filler_words = ["好的", "了解", "沒問題", "當然", "希望有幫助"]
    if any(text.strip().startswith(w) for w in filler_words):
        score -= 0.2

    return max(0.0, min(1.0, score))


def _score_density(text: str) -> float:
    """資訊密度評分：單位長度中的有效資訊量."""
    if len(text) < 10:
        return 0.1

    # 實詞比例（非停用詞的字數 / 總字數）
    total_chars = len(text)
    # 移除空白和標點
    content_chars = len(re.sub(r"[\s\n\-—*#`>|]", "", text))
    char_ratio = content_chars / total_chars if total_chars > 0 else 0

    # 段落內的資訊元素數量
    info_elements = 0
    info_elements += len(re.findall(r"[-*]\s", text))            # 列表項
    info_elements += len(re.findall(r"\d+[%％]", text))           # 百分比
    info_elements += len(re.findall(r"[A-Z]{2,}", text))          # 縮寫
    info_elements += len(re.findall(r"「[^」]+」", text))         # 引用
    info_elements += len(re.findall(r"\*\*[^*]+\*\*", text))     # 粗體重點

    density = char_ratio * 0.5 + min(info_elements / 8, 0.5)

    return max(0.0, min(1.0, density))


def _score_actionability(text: str) -> float:
    """可操作性評分：是否包含可執行的建議."""
    score = 0.3  # 基準分

    action_words = [
        "步驟", "先", "然後", "接著", "建議", "可以",
        "試試", "執行", "操作", "立刻", "馬上",
        "Step", "step", "TODO", "todo",
    ]

    hit_count = sum(1 for w in action_words if w in text)
    score += min(hit_count * 0.1, 0.4)

    # 包含程式碼區塊 → 高可操作性
    if "```" in text:
        score += 0.2

    # 包含連結 → 加分
    if re.search(r"https?://", text):
        score += 0.1

    return max(0.0, min(1.0, score))


def _crossover(
    primary_fragments: List[ScoredFragment],
    aux_pool: List[ScoredFragment],
) -> Tuple[List[ScoredFragment], List[Tuple[str, str, str]]]:
    """染色體交叉互換：用輔助部門更優片段替換主部門弱片段.

    策略（保守）：
    - 只替換主部門中分數最低的 1-2 個片段
    - 替換只在輔助片段顯著更優時發生（高出 REPLACEMENT_THRESHOLD）
    - 第一段（開場）和最後一段（結尾）不替換（保持連貫性）

    Returns:
        (重組後的片段列表, [(被替換位置的 dept_id, emoji, dept_name), ...])
    """
    if not aux_pool:
        return primary_fragments, []

    replacements: List[Tuple[str, str, str]] = []
    result = list(primary_fragments)

    # 保護首尾段落（exon 保護區）
    replaceable_range = range(1, max(1, len(result) - 1))

    # 找主部門中分數最低的段落
    scored_primary = [
        (i, f.composite_score) for i, f in enumerate(result)
        if i in replaceable_range
    ]
    scored_primary.sort(key=lambda x: x[1])

    # 最多替換 2 個片段（保守策略）
    max_replacements = min(2, len(scored_primary))

    for replace_idx in range(max_replacements):
        if replace_idx >= len(scored_primary):
            break

        target_idx, target_score = scored_primary[replace_idx]

        # 從輔助池中找最佳匹配
        best_aux: Optional[ScoredFragment] = None
        best_aux_score = 0.0

        for aux_f in aux_pool:
            aux_score = aux_f.composite_score
            if aux_score > best_aux_score:
                best_aux_score = aux_score
                best_aux = aux_f

        # 只在顯著更優時替換
        if best_aux and best_aux_score > target_score * (1 + REPLACEMENT_THRESHOLD):
            result[target_idx] = best_aux
            replacements.append((
                best_aux.source_dept,
                best_aux.source_emoji,
                best_aux.source_dept,  # dept_name 用 dept_id 代替
            ))
            # 已使用的片段從池中移除
            aux_pool = [f for f in aux_pool if f is not best_aux]

            logger.info(
                f"[Synthesizer] Crossover: replaced primary fragment "
                f"(score={target_score:.2f}) with {best_aux.source_dept} "
                f"fragment (score={best_aux_score:.2f})"
            )

    return result, replacements


# ═══════════════════════════════════════════
# 工具函數
# ═══════════════════════════════════════════

def _extract_key_insight(response: str, max_len: int = 200) -> str:
    """從部門回覆中提取關鍵洞察.

    策略：取第一段非空內容，截斷到 max_len。
    """
    lines = response.strip().split("\n")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("---"):
            continue

        if len(stripped) > max_len:
            return stripped[:max_len] + "…"
        return stripped

    return ""
