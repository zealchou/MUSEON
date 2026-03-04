"""
Environment Variable Security — Layer 3 Defense Extension

Filters dangerous environment variables before passing to subprocess execution.
Prevents host environment manipulation attacks (library injection, shell hijacking).

Reference: OpenClaw host-env-security.ts + host-env-security-policy.json
Adapted for MuseClaw Python runtime.
"""
import logging
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

# ── 直接封鎖的變數名稱 ──
# 這些變數可被用來劫持子程序的執行環境
BLOCKED_KEYS: Set[str] = {
    # Node.js / JavaScript
    "NODE_OPTIONS",
    "NODE_PATH",
    # Python
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    # Perl
    "PERL5LIB",
    "PERL5OPT",
    # Ruby
    "RUBYLIB",
    "RUBYOPT",
    # Shell 初始化與控制
    "BASH_ENV",
    "ENV",
    "SHELLOPTS",
    "PS4",
    # 系統級危險變數
    "GCONV_PATH",       # iconv 模組路徑劫持
    "IFS",              # 內部欄位分隔符（可影響 shell 解析）
    "SSLKEYLOGFILE",    # SSL 金鑰洩漏
    "HISTFILE",         # 避免寫入 shell 歷史
}

# ── 前綴封鎖 ──
# 以這些前綴開頭的變數一律移除
BLOCKED_PREFIXES = (
    "DYLD_",        # macOS 動態連結庫注入
    "LD_",          # Linux 動態連結庫注入
    "BASH_FUNC_",   # Bash 函數匯出（ShellShock 類攻擊）
)

# ── 受保護的變數 ──
# 這些變數不可被 agent/overrides 覆蓋
PROTECTED_KEYS: Set[str] = {
    "PATH",
    "HOME",
    "USER",
    "SHELL",
    "LOGNAME",
}

# ── Shell 包裝器允許的 override 變數 ──
SHELL_WRAPPER_ALLOWED_OVERRIDES: Set[str] = {
    "TERM",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LC_MESSAGES",
    "COLORTERM",
    "NO_COLOR",
    "FORCE_COLOR",
}


def _is_blocked_key(key: str) -> bool:
    """Check if an environment variable key is blocked."""
    upper = key.upper()
    if upper in BLOCKED_KEYS:
        return True
    for prefix in BLOCKED_PREFIXES:
        if upper.startswith(prefix):
            return True
    return False


def sanitize_shell_env(
    base_env: Dict[str, str],
    overrides: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Sanitize environment variables for subprocess execution.

    1. Remove blocked keys and prefixes from base_env
    2. Apply overrides (if any), blocking protected keys
    3. Return cleaned environment

    Args:
        base_env: Base environment dict (typically os.environ.copy())
        overrides: Optional overrides from agent/tool request

    Returns:
        Sanitized environment dict
    """
    cleaned = {}
    removed = []

    # Step 1: Filter base environment
    for key, value in base_env.items():
        if _is_blocked_key(key):
            removed.append(key)
        else:
            cleaned[key] = value

    if removed:
        logger.info(f"env_security: 移除 {len(removed)} 個危險環境變數: {removed}")

    # Step 2: Apply overrides (with protection)
    if overrides:
        blocked_overrides = []
        for key, value in overrides.items():
            if key in PROTECTED_KEYS:
                blocked_overrides.append(key)
            elif _is_blocked_key(key):
                blocked_overrides.append(key)
            else:
                cleaned[key] = value

        if blocked_overrides:
            logger.warning(
                f"env_security: 阻擋 {len(blocked_overrides)} 個受保護/危險的覆蓋嘗試: "
                f"{blocked_overrides}"
            )

    return cleaned
