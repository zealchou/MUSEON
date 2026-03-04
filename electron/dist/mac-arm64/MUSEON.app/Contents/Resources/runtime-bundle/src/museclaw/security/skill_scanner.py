"""SecurityScanner — SKILL.md 內容安全掃描器.

掃描 Skill 內容中的 50 個已知風險模式，分 5 個嚴重等級。
純 CPU，零 LLM 依賴。

依據 SKILL_MANAGER_BDD_SPEC §8 實作。
"""

import logging
import re
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Risk Levels
# ═══════════════════════════════════════════

class RiskLevel(IntEnum):
    """風險等級（數值越高越危險）."""

    INFO = 1       # 純資訊
    LOW = 2        # 低風險
    MEDIUM = 3     # 中風險（安裝閘門）
    HIGH = 4       # 高風險（需人工審查）
    CRITICAL = 5   # 嚴重（永久禁止）


RISK_MEDIUM = RiskLevel.MEDIUM  # 安裝阻擋閾值


# ═══════════════════════════════════════════
# 50 Scan Patterns
# ═══════════════════════════════════════════

SCAN_PATTERNS: List[Tuple[str, RiskLevel, str]] = [
    # ── CRITICAL (5) — 執行 / 資料外洩 ──
    (r"eval\s*\(", RiskLevel.CRITICAL, "dynamic_eval"),
    (r"exec\s*\(", RiskLevel.CRITICAL, "dynamic_exec"),
    (r"os\.system\s*\(", RiskLevel.CRITICAL, "os_system_call"),
    (r"subprocess\.\w+", RiskLevel.CRITICAL, "subprocess_usage"),
    (r"__import__\s*\(", RiskLevel.CRITICAL, "dynamic_import"),
    (r"compile\s*\(.+exec", RiskLevel.CRITICAL, "compiled_exec"),
    (r"globals\s*\(\)|locals\s*\(\)", RiskLevel.CRITICAL, "scope_access"),
    (r"setattr\s*\(", RiskLevel.CRITICAL, "dynamic_setattr"),
    (r"delattr\s*\(", RiskLevel.CRITICAL, "dynamic_delattr"),
    (r"base64\.b64decode", RiskLevel.CRITICAL, "encoded_payload"),

    # ── HIGH (4) — 注入 / 角色劫持 ──
    (r"ignore.*previous.*instructions", RiskLevel.HIGH, "prompt_inject_ignore"),
    (r"disregard.*(?:instructions|rules|above)", RiskLevel.HIGH, "prompt_inject_disregard"),
    (r"you are now", RiskLevel.HIGH, "role_hijack_now"),
    (r"act as.*(?:admin|root|system)", RiskLevel.HIGH, "role_hijack_admin"),
    (r"forget.*(?:rules|instructions|constraints)", RiskLevel.HIGH, "prompt_inject_forget"),
    (r"override.*(?:system|safety)", RiskLevel.HIGH, "safety_override"),
    (r"</?(?:system|user|assistant)>", RiskLevel.HIGH, "xml_tag_injection"),
    (r"\[SYSTEM\]", RiskLevel.HIGH, "system_tag_injection"),
    (r"urllib\.request", RiskLevel.HIGH, "network_urllib"),
    (r"socket\.\w+", RiskLevel.HIGH, "raw_socket"),

    # ── MEDIUM (3) — 可疑行為 ──
    (r"rm\s+-rf", RiskLevel.MEDIUM, "destructive_rm"),
    (r"chmod\s+777", RiskLevel.MEDIUM, "permission_escalation"),
    (r"sudo\s+", RiskLevel.MEDIUM, "privilege_escalation"),
    (r"密碼|password|secret|token|api.?key", RiskLevel.MEDIUM, "credential_ref"),
    (r"curl\s+.*\|.*(?:sh|bash)", RiskLevel.MEDIUM, "pipe_to_shell"),
    (r"wget\s+.*-O", RiskLevel.MEDIUM, "download_execute"),
    (r"open\s*\(.*['\"]w", RiskLevel.MEDIUM, "file_write"),
    (r"shutil\.rmtree", RiskLevel.MEDIUM, "recursive_delete"),
    (r"os\.remove|os\.unlink", RiskLevel.MEDIUM, "file_delete"),
    (r"importlib", RiskLevel.MEDIUM, "dynamic_importlib"),

    # ── LOW (2) — 輕微關注 ──
    (r"print\s*\(", RiskLevel.LOW, "debug_print"),
    (r"TODO|FIXME|HACK", RiskLevel.LOW, "unfinished_code"),
    (r"localhost|127\.0\.0\.1", RiskLevel.LOW, "hardcoded_localhost"),
    (r"http://(?!127\.0\.0\.1)", RiskLevel.LOW, "insecure_http"),
    (r"sleep\s*\(\s*\d{3,}", RiskLevel.LOW, "long_sleep"),
    (r"while\s+True", RiskLevel.LOW, "infinite_loop"),
    (r"global\s+\w+", RiskLevel.LOW, "global_state"),
    (r"pickle\.\w+", RiskLevel.LOW, "pickle_usage"),
    (r"yaml\.load\s*\((?!.*Loader)", RiskLevel.LOW, "unsafe_yaml"),
    (r"marshal\.\w+", RiskLevel.LOW, "marshal_usage"),

    # ── INFO (1) — 純資訊 ──
    (r"DEPRECATED", RiskLevel.INFO, "deprecated_marker"),
    (r"EXPERIMENTAL", RiskLevel.INFO, "experimental_marker"),
    (r"NOTE:", RiskLevel.INFO, "note_marker"),
    (r"WARNING:", RiskLevel.INFO, "warning_marker"),
    (r"CAUTION:", RiskLevel.INFO, "caution_marker"),
    (r"\n{5,}", RiskLevel.INFO, "excessive_newlines"),
    (r"#{6,}", RiskLevel.INFO, "deep_heading"),
    (r"```(?:python|javascript|shell|bash)", RiskLevel.INFO, "code_block"),
    (r"<script", RiskLevel.INFO, "script_tag"),
    (r"javascript:", RiskLevel.INFO, "js_uri"),
]


# ═══════════════════════════════════════════
# SecurityScanner
# ═══════════════════════════════════════════

class SecurityScanner:
    """SKILL.md 內容安全掃描器.

    使用 50 個預編譯 regex 模式掃描內容風險。
    safe 判定：最高風險 < MEDIUM（INFO/LOW 皆通過）。
    """

    def __init__(self) -> None:
        self._compiled: List[Tuple[re.Pattern, RiskLevel, str]] = [
            (re.compile(pattern, re.IGNORECASE), level, tag)
            for pattern, level, tag in SCAN_PATTERNS
        ]

    def scan_skill(self, content: str) -> Dict[str, Any]:
        """掃描 Skill 內容的安全風險.

        Args:
            content: SKILL.md 完整文字內容.

        Returns:
            {safe, risk_level, risk_name, issues[], issue_count, summary}
        """
        issues: List[Dict[str, Any]] = []
        max_level = 0

        for compiled_pat, level, tag in self._compiled:
            matches = compiled_pat.findall(content)
            if matches:
                issues.append({
                    "tag": tag,
                    "risk_level": int(level),
                    "risk_name": level.name,
                    "match_count": len(matches),
                    "sample": matches[0][:50] if matches else "",
                })
                if int(level) > max_level:
                    max_level = int(level)

        safe = max_level < int(RISK_MEDIUM)

        if not issues:
            summary = "clean"
        else:
            by_level: Dict[str, int] = {}
            for iss in issues:
                name = iss["risk_name"]
                by_level[name] = by_level.get(name, 0) + 1
            parts = [f"{count} {name}" for name, count in by_level.items()]
            summary = ", ".join(parts)

        return {
            "safe": safe,
            "risk_level": max_level,
            "risk_name": RiskLevel(max_level).name if max_level > 0 else "NONE",
            "issues": issues,
            "issue_count": len(issues),
            "summary": summary,
        }

    def scan_file(self, file_path: Path) -> Dict[str, Any]:
        """掃描 SKILL.md 檔案.

        Args:
            file_path: 指向 SKILL.md 的路徑.

        Returns:
            同 scan_skill()，加上 path 欄位.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return {
                "safe": False,
                "risk_level": int(RiskLevel.CRITICAL),
                "risk_name": "CRITICAL",
                "issues": [{"tag": "read_error", "risk_level": 5,
                            "risk_name": "CRITICAL", "error": str(e)}],
                "issue_count": 1,
                "summary": f"file read error: {e}",
                "path": str(file_path),
            }

        result = self.scan_skill(content)
        result["path"] = str(file_path)
        return result
