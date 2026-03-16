"""Memory Gate — 記憶寫入前的意圖分類與衝突偵測閘門.

在記憶持久化管線的最前端，判斷使用者訊息的意圖類型，
決定是否應該寫入記憶、跳過記憶、或觸發事實更正流程。

核心解決的問題：「越否認越強化」迴圈。
當使用者糾正錯誤記憶時（如「沒有7個新同仁」），
如果不先判斷意圖就直接寫入，糾正句子本身會成為新的記憶信號。

設計原則：
- 純 CPU 規則引擎，零 LLM 成本
- 寧可多攔截（高召回率），由下游精確判斷
- 不影響既有管線，只做前置過濾
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── 否定/糾正偵測規則 ──────────────────────────────────────

# 直接否定信號（命中即觸發糾正模式）
_CORRECTION_SIGNALS: List[str] = [
    # 直接否定
    "不是", "沒有", "才沒有", "不對", "錯了",
    # 糾正既有記憶
    "你記錯", "你搞錯", "你弄錯", "你搞混", "你誤會",
    "哪來的", "沒那回事", "沒有這",
    # 重複糾正的不耐
    "要我講多少遍", "講幾遍", "我說過了", "跟你說過",
    "已經說過", "又來了", "又搞錯", "你怎麼又",
    # 命令停止
    "別再說", "別再提", "不要再",
    # 質疑來源
    "誰說的", "我沒說過",
    # 正式糾正
    "我糾正", "我更正", "修正一下", "不是這樣", "才不是",
    "錯了啦", "不對啦",
]

# 邊界類信號（需要搭配事實關鍵字才觸發）
_BOUNDARY_SIGNALS: List[str] = [
    "停", "夠了", "別", "不要", "不用",
]

# 事實相關關鍵字（與 brain.py _FACT_PATTERNS + _ROLE_KEYWORDS 對齊）
_FACT_KEYWORDS: List[str] = [
    # occupation
    "工作", "職業", "公司", "任職", "上班", "老闆", "創業", "員工",
    # family
    "家人", "老婆", "太太", "兒子", "女兒", "小孩", "爸爸", "媽媽", "孩子",
    # location
    "住在", "台北", "台中", "台灣", "搬到",
    # education
    "大學", "碩士", "博士", "畢業", "學校",
    # hobby
    "喜歡", "興趣",
    # roles
    "團隊", "管理", "績效",
    # numbers (commonly misremembered)
    "個人", "個員工", "個同仁", "位員工", "位同仁",
]

# 問句信號
_QUESTION_PATTERNS: List[str] = [
    "為什麼", "怎麼", "可以嗎", "什麼是", "如何", "有沒有",
    "是什麼", "怎麼做", "可不可以",
]

# 數字+量詞的 regex（用於偵測「沒有 7 個」這類否定數字的模式）
_NUM_PATTERN = re.compile(r"[沒不]有?\s*\d+\s*[個位名]")


@dataclass
class MemoryIntent:
    """記憶意圖分類結果."""

    type: str  # "assertion" | "correction" | "denial" | "question" | "command"
    confidence: float  # 0.0-1.0
    correction_signals: List[str] = field(default_factory=list)
    fact_keywords_hit: List[str] = field(default_factory=list)


@dataclass
class MemoryAction:
    """記憶操作決策."""

    action: str  # "ADD" | "SKIP" | "CORRECT"
    reason: str
    suppress_primals: bool = False
    suppress_facts: bool = False
    trigger_correction: bool = False


class MemoryGate:
    """記憶寫入前的意圖分類與操作決策閘門.

    純 CPU 規則引擎，零 LLM 成本。
    在 brain.py Step 9 之前執行，決定是否允許記憶寫入。
    """

    def classify_intent(self, content: str) -> MemoryIntent:
        """分類使用者訊息的記憶意圖.

        三層判斷：
        1. 是否包含糾正信號？
        2. 是否包含事實關鍵字？
        3. 糾正信號 + 事實關鍵字 = correction（高信心）
           糾正信號 alone = denial（中信心）
           事實關鍵字 alone = assertion
           都沒有 = 普通訊息
        """
        if len(content) < 2:
            return MemoryIntent(type="assertion", confidence=0.1)

        # 問句偵測
        is_question = (
            content.rstrip().endswith("？")
            or content.rstrip().endswith("?")
            or any(q in content for q in _QUESTION_PATTERNS)
        )

        # 糾正信號偵測
        correction_hits = [s for s in _CORRECTION_SIGNALS if s in content]

        # 邊界信號 + 事實關鍵字組合偵測
        boundary_hits = [s for s in _BOUNDARY_SIGNALS if s in content]
        fact_hits = [k for k in _FACT_KEYWORDS if k in content]

        # 數字否定偵測（「沒有7個」「不是12個」等）
        has_num_negation = bool(_NUM_PATTERN.search(content))

        # 組合判斷
        if correction_hits and fact_hits:
            # 高信心糾正：明確的糾正信號 + 事實關鍵字
            return MemoryIntent(
                type="correction",
                confidence=0.9,
                correction_signals=correction_hits,
                fact_keywords_hit=fact_hits,
            )

        if correction_hits and has_num_negation:
            # 數字否定糾正：「沒有7個員工」
            return MemoryIntent(
                type="correction",
                confidence=0.85,
                correction_signals=correction_hits,
                fact_keywords_hit=[],
            )

        if len(correction_hits) >= 2:
            # 多重糾正信號（即使沒事實關鍵字也很可能是糾正）
            return MemoryIntent(
                type="correction",
                confidence=0.8,
                correction_signals=correction_hits,
                fact_keywords_hit=fact_hits,
            )

        if boundary_hits and fact_hits:
            # 邊界 + 事實 = 可能是否認（「別再說員工的事」）
            return MemoryIntent(
                type="denial",
                confidence=0.7,
                correction_signals=boundary_hits,
                fact_keywords_hit=fact_hits,
            )

        if correction_hits:
            # 單個糾正信號但沒事實關鍵字 = 低信心
            # 可能是正常對話中的否定（「不是這樣做」）
            return MemoryIntent(
                type="denial",
                confidence=0.5,
                correction_signals=correction_hits,
                fact_keywords_hit=[],
            )

        if is_question:
            return MemoryIntent(type="question", confidence=0.7)

        return MemoryIntent(
            type="assertion",
            confidence=0.6,
            fact_keywords_hit=fact_hits,
        )

    def decide_action(self, intent: MemoryIntent) -> MemoryAction:
        """根據意圖決定記憶操作.

        決策矩陣：
        - correction (conf >= 0.7) → CORRECT: 跳過記憶寫入 + 觸發事實更正
        - correction (conf < 0.7)  → SKIP: 跳過八原語，保留七層觀察
        - denial (conf >= 0.7)     → SKIP: 跳過八原語和事實寫入
        - denial (conf < 0.7)      → ADD: 正常寫入（低信心不攔截）
        - question                 → ADD: 正常寫入（問題是正常互動）
        - assertion                → ADD: 正常寫入
        """
        if intent.type == "correction" and intent.confidence >= 0.7:
            return MemoryAction(
                action="CORRECT",
                reason=f"糾正偵測 (conf={intent.confidence:.2f}, "
                       f"signals={intent.correction_signals[:3]})",
                suppress_primals=True,
                suppress_facts=True,
                trigger_correction=True,
            )

        if intent.type == "correction" and intent.confidence >= 0.5:
            # 中等信心：跳過八原語但不觸發完整糾正
            return MemoryAction(
                action="SKIP",
                reason=f"疑似糾正 (conf={intent.confidence:.2f})",
                suppress_primals=True,
                suppress_facts=True,
                trigger_correction=False,
            )

        if intent.type == "denial" and intent.confidence >= 0.7:
            return MemoryAction(
                action="SKIP",
                reason=f"否認偵測 (conf={intent.confidence:.2f}, "
                       f"signals={intent.correction_signals[:3]})",
                suppress_primals=True,
                suppress_facts=True,
                trigger_correction=False,
            )

        if intent.type == "denial" and intent.confidence >= 0.5:
            # 低信心否認：只跳過八原語，保留七層其他觀察
            return MemoryAction(
                action="ADD",
                reason=f"低信心否認 (conf={intent.confidence:.2f})，保守放行",
                suppress_primals=True,
                suppress_facts=False,
                trigger_correction=False,
            )

        # 所有其他情況：正常寫入
        return MemoryAction(
            action="ADD",
            reason=f"正常寫入 (type={intent.type})",
            suppress_primals=False,
            suppress_facts=False,
            trigger_correction=False,
        )
