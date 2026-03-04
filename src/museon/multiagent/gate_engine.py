"""Gate Engine — 四級內容驗證.

Gate 0: Legality（合法性）→ 複用 SecurityScanner
Gate 1: Feasibility（可行性）→ 最低 20 字元
Gate 2: Completeness（完整性）→ 含標題
Gate 3: Quality（品質）→ 四維評分 ≥ 0.6

依據 MULTI_AGENT_BDD_SPEC §6 實作。
"""

import re
from dataclasses import dataclass, field
from typing import List


# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

GATE1_MIN_LENGTH = 20       # Gate 1 最低字元數
GATE3_MIN_QUALITY = 0.6     # Gate 3 最低品質分

# Gate 3 各維度權重
WEIGHT_LENGTH = 0.30
WEIGHT_STRUCTURE = 0.25
WEIGHT_DATA = 0.20
WEIGHT_RICHNESS = 0.25

# ═══════════════════════════════════════════
# GateResult
# ═══════════════════════════════════════════


@dataclass
class GateResult:
    """驗證結果."""

    passed: bool
    gate_level: int          # 通過的最高 gate（-1 表示全未通過）
    score: float = 0.0       # Gate 3 品質分數
    issues: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════
# GateEngine
# ═══════════════════════════════════════════


class GateEngine:
    """四級內容驗證引擎."""

    def __init__(self) -> None:
        # Gate 0: 複用 SecurityScanner（lazy import 避免循環依賴）
        self._scanner = None

    @property
    def scanner(self):
        if self._scanner is None:
            from museon.security.skill_scanner import SecurityScanner
            self._scanner = SecurityScanner()
        return self._scanner

    def validate(self, content: str) -> GateResult:
        """執行四級驗證.

        依序通過 Gate 0 → 1 → 2 → 3。
        任一級未通過即停止，回傳已通過的最高級。
        """
        issues: List[str] = []

        # ── Gate 0: Legality（複用 SecurityScanner）──
        scan = self.scanner.scan_skill(content)
        if not scan["safe"]:
            issues.append(
                f"prohibited pattern detected: {scan['risk_name']} "
                f"({scan['issue_count']} issues)"
            )
            return GateResult(
                passed=False, gate_level=-1, score=0.0, issues=issues
            )

        # ── Gate 1: Feasibility（最低長度）──
        if len(content) < GATE1_MIN_LENGTH:
            issues.append(
                f"content too short: {len(content)} < {GATE1_MIN_LENGTH} chars"
            )
            return GateResult(
                passed=False, gate_level=0, score=0.0, issues=issues
            )

        # ── Gate 2: Completeness（含標題）──
        has_heading = bool(
            re.search(r"^#{1,6}\s+\S", content, re.MULTILINE)
            or re.search(r"^.+\n[=]{3,}", content, re.MULTILINE)
        )
        if not has_heading:
            issues.append("missing heading (# or === underline)")
            return GateResult(
                passed=False, gate_level=1, score=0.0, issues=issues
            )

        # ── Gate 3: Quality（四維評分）──
        score = self._quality_score(content)
        if score < GATE3_MIN_QUALITY:
            issues.append(
                f"quality too low: {score:.2f} < {GATE3_MIN_QUALITY}"
            )
            return GateResult(
                passed=False, gate_level=2, score=score, issues=issues
            )

        return GateResult(
            passed=True, gate_level=3, score=score, issues=[]
        )

    # ═══════════════════════════════════════
    # Gate 3 品質評分
    # ═══════════════════════════════════════

    def _quality_score(self, content: str) -> float:
        """四維品質評分.

        length(30%) + structure(25%) + data(20%) + richness(25%)
        """
        length = len(content)
        paragraphs = [
            p.strip() for p in content.split("\n\n") if p.strip()
        ]

        # 長度分（30%）
        if length >= 100:
            length_score = WEIGHT_LENGTH
        elif length >= 50:
            length_score = 0.20
        else:
            length_score = 0.10

        # 結構分（25%）— 有標題或列表
        has_structure = bool(
            re.search(r"^#{1,6}\s", content, re.MULTILINE)
            or re.search(r"^[-*]\s", content, re.MULTILINE)
            or re.search(r"^\d+\.\s", content, re.MULTILINE)
        )
        structure_score = WEIGHT_STRUCTURE if has_structure else 0.0

        # 數據分（20%）— 含數字或百分比
        has_data = bool(re.search(r"\d+[%％]|\d{2,}", content))
        data_score = WEIGHT_DATA if has_data else 0.0

        # 豐富度分（25%）— 段落數
        if len(paragraphs) >= 5:
            richness_score = WEIGHT_RICHNESS
        elif len(paragraphs) >= 3:
            richness_score = 0.15
        else:
            richness_score = 0.0

        return length_score + structure_score + data_score + richness_score
