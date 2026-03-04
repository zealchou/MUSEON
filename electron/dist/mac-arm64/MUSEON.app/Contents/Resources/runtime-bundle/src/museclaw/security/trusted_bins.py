"""
Trusted Binary Validation — Layer 3 Defense Extension

Validates that executable binaries come from trusted system directories,
preventing PATH manipulation attacks and malicious binary execution.

Reference: OpenClaw exec-safe-bin-trust.ts
Adapted for MuseClaw Python runtime on macOS.
"""
import logging
import shutil
from pathlib import Path
from typing import Optional, Set

logger = logging.getLogger(__name__)

# ── 預設信任的二進位目錄 ──
# 只有這些目錄下的二進位檔被認為是安全的
DEFAULT_TRUSTED_DIRS: Set[str] = {
    "/bin",
    "/usr/bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
    "/usr/sbin",
    "/sbin",
    "/opt/local/bin",          # MacPorts
    "/snap/bin",               # Snap (Linux)
}

# ── venv 目錄會在初始化時動態加入 ──
_extra_trusted_dirs: Set[str] = set()


def add_trusted_dir(directory: str) -> None:
    """Add an extra trusted directory at runtime.

    Used to register venv/bin, nvm paths, etc.

    Args:
        directory: Absolute path to trust
    """
    resolved = str(Path(directory).resolve())
    _extra_trusted_dirs.add(resolved)
    logger.info(f"trusted_bins: 新增信任目錄 {resolved}")


def get_trusted_dirs() -> Set[str]:
    """Get the current set of trusted directories."""
    return DEFAULT_TRUSTED_DIRS | _extra_trusted_dirs


def resolve_trusted_binary(
    cmd_name: str,
    extra_trusted: Optional[Set[str]] = None,
) -> Optional[str]:
    """Resolve a command name to a trusted binary path.

    1. Use shutil.which() to find the binary
    2. Resolve symlinks to get real path
    3. Check that the parent directory is in trusted dirs

    Args:
        cmd_name: Command name (e.g. 'python3', 'git')
        extra_trusted: Additional trusted directories for this call

    Returns:
        Resolved absolute path if trusted, None if untrusted or not found
    """
    # Step 1: Find binary via which
    which_path = shutil.which(cmd_name)
    if not which_path:
        logger.warning(f"trusted_bins: 找不到二進位檔 '{cmd_name}'")
        return None

    # Step 2: Resolve symlinks
    resolved = str(Path(which_path).resolve())
    parent_dir = str(Path(resolved).parent)

    # Step 3: Check trust
    trusted = get_trusted_dirs()
    if extra_trusted:
        trusted = trusted | extra_trusted

    if parent_dir in trusted:
        return resolved

    logger.warning(
        f"trusted_bins: 二進位檔 '{cmd_name}' 位於不信任的目錄 "
        f"{parent_dir}（解析自 {which_path}）"
    )
    return None


def is_trusted_path(binary_path: str) -> bool:
    """Check if a specific binary path is in a trusted directory.

    Args:
        binary_path: Full path to binary

    Returns:
        True if parent directory is trusted
    """
    resolved = str(Path(binary_path).resolve())
    parent_dir = str(Path(resolved).parent)
    return parent_dir in get_trusted_dirs()
