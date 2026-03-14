"""Field Consistency Scanner — 欄位一致性掃描器.

DSE 第一性原理解法：消滅魔術字串，自動偵測 JSON 欄位不匹配。

用法：
    python -m museon.doctor.field_scanner --home /Users/ZEALCHOU/MUSEON
"""
from __future__ import annotations

import argparse
import ast
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Schema 契約定義（Single Source of Truth）
# ═══════════════════════════════════════════

ANIMA_MC_SCHEMA: Dict[str, Any] = {
    "version": str,
    "type": str,
    "description": str,
    "identity": {
        "name": str,
        "birth_date": str,
        "growth_stage": str,
        "days_alive": int,
        "naming_ceremony_completed": bool,
    },
    "self_awareness": {
        "who_am_i": str,
        "my_purpose": str,
        "why_i_exist": str,
        "expression_style": {
            "opener_stats": dict,
            "tone_temperature": float,
            "last_evolved_at": str,
            "evolution_count": int,
        },
    },
    "personality": {
        "core_traits": list,
        "communication_style": str,
        "growth_mindset": str,
    },
    "capabilities": {
        "loaded_skills": list,
        "forged_skills": list,
        "skill_proficiency": dict,
    },
    "evolution": {
        "current_stage": str,
        "iteration_count": int,
        "paused": bool,
        "paused_reason": str,
        "paused_at": str,
        "resumed_at": str,
        "resumed_reason": str,
        "l3_match_score": float,
        "l3_match_updated": str,
    },
    "memory_summary": {
        "total_interactions": int,
        "sessions_count": int,
        "knowledge_crystals": int,
    },
    "boss": {
        "name": str,
        "nickname": str,
        "business_type": str,
        "immediate_need": str,
        "main_pain_point": str,
        "raw_answers": str,
        "parsed_at": str,
    },
    "ceremony": {
        "completed": bool,
        "started_at": str,
        "completed_at": str,
    },
    "eight_primal_energies": dict,  # 正式名稱
    "_vita_triggered_thresholds": list,
}

ANIMA_USER_SCHEMA: Dict[str, Any] = {
    "version": str,
    "eight_primals": dict,
    "seven_layers": {
        "L1_facts": list,
        "L2_personality": list,
        "L3_decision_pattern": list,
        "L4_interaction_rings": list,
        "L5_preference_crystals": list,
        "L6_communication_style": {
            "detail_level": str,
            "emoji_usage": str,
            "language_mix": str,
            "avg_msg_length": int,
            "tone": str,
            "question_style": str,
        },
        "L7_context_roles": list,
    },
    "profile": dict,
    "relationship": {
        "total_interactions": int,
    },
    # 隱藏緩衝欄位（internal）
    "_pref_buffer": dict,
    "_tone_history": dict,
    "_rc_calibration": dict,
}

DRIFT_BASELINE_SCHEMA: Dict[str, Any] = {
    "taken_at": str,
    "mc_primals": dict,
    "mc_expression": dict,
    "user_primals": dict,
    "user_L5": list,
    "user_L6": dict,
    "user_L7": list,
}

# 已知的欄位別名映射（允許的同義欄位）
KNOWN_ALIASES: Dict[str, str] = {
    "eight_primals": "eight_primal_energies",  # ANIMA_MC 中的正式名稱
}

# 已知的棄用欄位（應該被移除）
DEPRECATED_FIELDS: Set[str] = set()


# ═══════════════════════════════════════════
# 掃描結果
# ═══════════════════════════════════════════

@dataclass
class FieldAccess:
    """單次欄位存取記錄."""
    file_path: str
    line_number: int
    key: str
    operation: str  # "read" | "write" | "setdefault"
    context: str  # 周圍程式碼片段


@dataclass
class FieldMismatch:
    """欄位不匹配."""
    severity: str  # "critical" | "warning" | "info"
    category: str  # "missing_in_json" | "missing_in_code" | "alias" | "type_mismatch"
    field_key: str
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None


@dataclass
class ScanReport:
    """掃描報告."""
    total_accesses: int = 0
    mismatches: List[FieldMismatch] = field(default_factory=list)
    field_accesses: List[FieldAccess] = field(default_factory=list)
    json_keys: Dict[str, Set[str]] = field(default_factory=dict)  # filename → keys
    code_keys: Dict[str, Set[str]] = field(default_factory=dict)  # filename → keys

    @property
    def critical_count(self) -> int:
        return sum(1 for m in self.mismatches if m.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for m in self.mismatches if m.severity == "warning")


# ═══════════════════════════════════════════
# 掃描引擎
# ═══════════════════════════════════════════

class FieldScanner:
    """欄位一致性掃描器."""

    # 目標 JSON 檔案
    TARGET_FILES = {
        "ANIMA_MC": "ANIMA_MC.json",
        "ANIMA_USER": "ANIMA_USER.json",
        "drift_baseline": "anima/drift_baseline.json",
    }

    # .get() 模式匹配
    _GET_PATTERN = re.compile(
        r'\.get\(\s*["\']([^"\']+)["\']\s*(?:,\s*[^)]+)?\)'
    )
    # ["key"] 模式匹配
    _BRACKET_PATTERN = re.compile(
        r'\[\s*["\']([^"\']+)["\']\s*\]'
    )
    # .setdefault() 模式匹配
    _SETDEFAULT_PATTERN = re.compile(
        r'\.setdefault\(\s*["\']([^"\']+)["\']\s*,'
    )

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.data_dir = workspace / "data"
        self.src_dir = workspace / "src" / "museon"

    def scan(self) -> ScanReport:
        """執行完整掃描."""
        report = ScanReport()

        # Phase 1: 讀取實際 JSON 檔案的 key
        for label, rel_path in self.TARGET_FILES.items():
            json_path = self.data_dir / rel_path
            if json_path.exists():
                keys = self._extract_json_keys(json_path)
                report.json_keys[label] = keys
            else:
                report.mismatches.append(FieldMismatch(
                    severity="warning",
                    category="missing_file",
                    field_key=rel_path,
                    message=f"JSON 檔案不存在: {rel_path}",
                ))

        # Phase 2: 掃描所有 .py 檔案中的 key 存取
        for py_file in self.src_dir.rglob("*.py"):
            accesses = self._scan_python_file(py_file)
            report.field_accesses.extend(accesses)
            report.total_accesses += len(accesses)

        # Phase 3: 交叉比對
        self._cross_reference(report)

        # Phase 4: 檢查已知問題模式
        self._check_known_patterns(report)

        return report

    def _extract_json_keys(
        self, path: Path, prefix: str = ""
    ) -> Set[str]:
        """遞迴提取 JSON 檔案的所有 key 路徑."""
        keys = set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._walk_json(data, prefix, keys)
        except Exception as e:
            logger.warning(f"無法解析 {path}: {e}")
        return keys

    def _walk_json(
        self, obj: Any, prefix: str, keys: Set[str]
    ) -> None:
        """遞迴遍歷 JSON 物件."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                full_key = f"{prefix}.{k}" if prefix else k
                keys.add(k)  # 短 key
                keys.add(full_key)  # 完整路徑
                self._walk_json(v, full_key, keys)

    def _scan_python_file(self, path: Path) -> List[FieldAccess]:
        """掃描單一 Python 檔案中的 key 存取."""
        accesses = []
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return accesses

        lines = content.split("\n")
        rel_path = str(path.relative_to(self.workspace))

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # 跳過註解
            if stripped.startswith("#"):
                continue

            # .get("key") 模式
            for match in self._GET_PATTERN.finditer(line):
                accesses.append(FieldAccess(
                    file_path=rel_path,
                    line_number=i,
                    key=match.group(1),
                    operation="read",
                    context=stripped[:120],
                ))

            # .setdefault("key", ...) 模式
            for match in self._SETDEFAULT_PATTERN.finditer(line):
                accesses.append(FieldAccess(
                    file_path=rel_path,
                    line_number=i,
                    key=match.group(1),
                    operation="setdefault",
                    context=stripped[:120],
                ))

            # ["key"] 模式（只在 dict 賦值或讀取上下文中）
            for match in self._BRACKET_PATTERN.finditer(line):
                key = match.group(1)
                # 排除明顯的非 ANIMA 存取
                if key in ("role", "content", "type", "name", "value",
                           "status", "message", "data", "error", "result",
                           "text", "id", "url", "method", "headers"):
                    continue
                op = "write" if f'["{key}"]' in line and "=" in line else "read"
                accesses.append(FieldAccess(
                    file_path=rel_path,
                    line_number=i,
                    key=key,
                    operation=op,
                    context=stripped[:120],
                ))

        return accesses

    def _cross_reference(self, report: ScanReport) -> None:
        """交叉比對 JSON 實際 key 和程式碼中存取的 key."""
        # 收集程式碼中存取的所有 ANIMA 相關 key
        anima_mc_code_keys: Set[str] = set()
        anima_user_code_keys: Set[str] = set()

        # ANIMA_MC 相關的 key 識別模式
        mc_indicators = {
            "identity", "self_awareness", "personality", "capabilities",
            "evolution", "memory_summary", "boss", "ceremony",
            "eight_primal_energies", "eight_primals",
            "_vita_triggered_thresholds",
            "growth_stage", "days_alive", "birth_date",
            "expression_style", "loaded_skills", "forged_skills",
            "skill_proficiency", "iteration_count", "paused",
            "paused_reason", "paused_at", "resumed_at",
            "total_interactions", "sessions_count", "knowledge_crystals",
            "naming_ceremony_completed",
        }

        # ANIMA_USER 相關的 key 識別模式
        user_indicators = {
            "seven_layers", "eight_primals",
            "L1_facts", "L2_personality", "L3_decision_pattern",
            "L4_interaction_rings", "L5_preference_crystals",
            "L6_communication_style", "L7_context_roles",
            "_pref_buffer", "_tone_history", "_rc_calibration",
            "detail_level", "emoji_usage", "language_mix",
            "avg_msg_length", "tone", "question_style",
            "profile", "relationship",
        }

        for access in report.field_accesses:
            if access.key in mc_indicators:
                anima_mc_code_keys.add(access.key)
            if access.key in user_indicators:
                anima_user_code_keys.add(access.key)

        report.code_keys["ANIMA_MC"] = anima_mc_code_keys
        report.code_keys["ANIMA_USER"] = anima_user_code_keys

        # 檢查：程式碼存取了但 JSON 中不存在的 key
        for label, code_keys in report.code_keys.items():
            json_keys = report.json_keys.get(label, set())
            for key in code_keys:
                if key not in json_keys:
                    # 檢查是否是已知別名
                    alias = KNOWN_ALIASES.get(key)
                    if alias and alias in json_keys:
                        report.mismatches.append(FieldMismatch(
                            severity="warning",
                            category="alias",
                            field_key=key,
                            message=(
                                f"程式碼使用 '{key}'，JSON 中是 '{alias}'"
                                f"（{label}）— 建議統一名稱"
                            ),
                        ))
                    else:
                        # 可能是巢狀 key，不一定是頂層
                        # 只報告明確的頂層 key 不匹配
                        if "." not in key and key.startswith(("eight_", "L")):
                            report.mismatches.append(FieldMismatch(
                                severity="critical",
                                category="missing_in_json",
                                field_key=key,
                                message=(
                                    f"程式碼存取 '{key}'，但 {label}.json "
                                    f"中不存在此欄位"
                                ),
                            ))

    def _check_known_patterns(self, report: ScanReport) -> None:
        """檢查已知的問題模式."""
        # Pattern 1: 同一維度的矛盾偏好
        if "ANIMA_USER" in report.json_keys:
            json_path = self.data_dir / "ANIMA_USER.json"
            if json_path.exists():
                try:
                    data = json.loads(json_path.read_text(encoding="utf-8"))
                    prefs = data.get("seven_layers", {}).get(
                        "L5_preference_crystals", []
                    )
                    pref_keys = [p.get("key", "") for p in prefs]

                    # 檢查 short/long 矛盾
                    if ("prefers_short_response" in pref_keys
                            and "prefers_long_response" in pref_keys):
                        short_conf = next(
                            (p.get("confidence", 0) for p in prefs
                             if p.get("key") == "prefers_short_response"), 0
                        )
                        long_conf = next(
                            (p.get("confidence", 0) for p in prefs
                             if p.get("key") == "prefers_long_response"), 0
                        )
                        if abs(short_conf - long_conf) < 0.3:
                            report.mismatches.append(FieldMismatch(
                                severity="warning",
                                category="contradictory",
                                field_key="L5_preference_crystals",
                                message=(
                                    f"矛盾偏好: prefers_short({short_conf:.1f}) "
                                    f"vs prefers_long({long_conf:.1f})"
                                ),
                            ))
                except Exception as e:
                    logger.debug(f"[FIELD_SCANNER] crystal failed (degraded): {e}")

        # Pattern 2: mc_primals 是否為空
        baseline_path = self.data_dir / "anima" / "drift_baseline.json"
        if baseline_path.exists():
            try:
                bl = json.loads(baseline_path.read_text(encoding="utf-8"))
                if not bl.get("mc_primals"):
                    report.mismatches.append(FieldMismatch(
                        severity="critical",
                        category="empty_data",
                        field_key="mc_primals",
                        message="drift_baseline.json 的 mc_primals 為空 — MC 漂移偵測盲區",
                    ))
            except Exception as e:
                logger.debug(f"[FIELD_SCANNER] JSON failed (degraded): {e}")

        # Pattern 3: soul_rings 是否為空
        soul_path = self.data_dir / "anima" / "soul_rings.json"
        if soul_path.exists():
            try:
                rings = json.loads(soul_path.read_text(encoding="utf-8"))
                if not rings:
                    report.mismatches.append(FieldMismatch(
                        severity="warning",
                        category="empty_data",
                        field_key="soul_rings",
                        message="soul_rings.json 為空 — 靈魂年輪從未寫入",
                    ))
            except Exception as e:
                logger.debug(f"[FIELD_SCANNER] soul failed (degraded): {e}")

        # Pattern 4: PULSE.md 區段標記一致性
        pulse_path = self.data_dir / "PULSE.md"
        if pulse_path.exists():
            try:
                pulse_content = pulse_path.read_text(encoding="utf-8")
                expected_sections = [
                    "## 🌊 成長反思",
                    "## 🔭 今日觀察",
                    "## 🌱 成長軌跡",
                    "## 💝 關係日誌",
                    "## 📊 今日狀態",
                ]
                for section in expected_sections:
                    if section not in pulse_content:
                        report.mismatches.append(FieldMismatch(
                            severity="warning",
                            category="missing_section",
                            field_key=section,
                            message=f"PULSE.md 缺少區段: {section}",
                        ))
            except Exception as e:
                logger.debug(f"[FIELD_SCANNER] pulse failed (degraded): {e}")

    def format_report(self, report: ScanReport) -> str:
        """格式化掃描報告."""
        lines = []
        lines.append("═" * 60)
        lines.append("  MUSEON 欄位一致性掃描報告")
        lines.append("═" * 60)
        lines.append("")
        lines.append(f"  掃描範圍: {self.src_dir}")
        lines.append(f"  總存取點: {report.total_accesses}")
        lines.append(
            f"  問題總數: {len(report.mismatches)} "
            f"(CRITICAL: {report.critical_count}, "
            f"WARNING: {report.warning_count})"
        )
        lines.append("")

        if not report.mismatches:
            lines.append("  ✅ 未發現欄位不匹配問題")
            return "\n".join(lines)

        # 按嚴重度分組
        for severity in ("critical", "warning", "info"):
            items = [m for m in report.mismatches if m.severity == severity]
            if not items:
                continue

            emoji = {"critical": "🔴", "warning": "⚠️", "info": "ℹ️"}[severity]
            lines.append(f"  ─── {emoji} {severity.upper()} ───")
            for m in items:
                lines.append(f"    [{m.category}] {m.field_key}")
                lines.append(f"      {m.message}")
                if m.file_path:
                    lines.append(f"      @ {m.file_path}:{m.line_number}")
                lines.append("")

        # JSON key 統計
        lines.append("  ─── 📊 JSON Key 統計 ───")
        for label, keys in report.json_keys.items():
            lines.append(f"    {label}: {len(keys)} keys")

        lines.append("")
        lines.append("═" * 60)

        overall = "CRITICAL" if report.critical_count > 0 else (
            "WARNING" if report.warning_count > 0 else "OK"
        )
        emoji = {"CRITICAL": "🚫", "WARNING": "⚠️", "OK": "✅"}[overall]
        lines.append(f"  {emoji} 整體狀態: {overall}")
        lines.append("═" * 60)

        return "\n".join(lines)


# ═══════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MUSEON 欄位一致性掃描器"
    )
    parser.add_argument(
        "--home",
        type=str,
        default=".",
        help="MUSEON 專案根目錄",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="輸出 JSON 格式",
    )
    args = parser.parse_args()

    workspace = Path(args.home)
    scanner = FieldScanner(workspace)
    report = scanner.scan()

    if args.json:
        result = {
            "total_accesses": report.total_accesses,
            "critical": report.critical_count,
            "warning": report.warning_count,
            "mismatches": [
                {
                    "severity": m.severity,
                    "category": m.category,
                    "field_key": m.field_key,
                    "message": m.message,
                }
                for m in report.mismatches
            ],
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(scanner.format_report(report))

    sys.exit(1 if report.critical_count > 0 else 0)


if __name__ == "__main__":
    main()
