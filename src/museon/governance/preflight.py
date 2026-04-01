"""PreflightGate — 啟動前驗證門（胸腺）.

模擬生物免疫系統的「胸腺」機制：
  - 在 Gateway main() 中、uvicorn 啟動前執行
  - 驗證必要 API Key 是否存在且非 placeholder
  - 驗證 MUSEON_HOME 目錄是否存在
  - 驗證 Setup Wizard 是否已完成

失敗處理：
  - 致命錯誤（failures）→ exit(0) 避免 launchd 無限重啟
  - 非致命警告（warnings）→ 記錄但允許啟動

關鍵設計：
  - exit(0) 而非 exit(1)：launchd KeepAlive.SuccessfulExit=false
    只在非零退出碼時觸發重啟。exit(0) = 正常退出 = 不重啟。
  - Placeholder 偵測涵蓋常見模板值（your-、placeholder、xxx 等）
  - 零 LLM 依賴，純 CPU 字串比對

DSE 參考：
  - K8s CrashLoopBackOff 的根因通常是配置錯誤
  - systemd ConditionPathExists/ConditionEnvironment 的 preflight 概念
  - 生物胸腺在 T 細胞成熟前篩選異常細胞
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 結果模型
# ═══════════════════════════════════════════


@dataclass
class PreflightResult:
    """預檢結果."""

    passed: bool
    failures: List[str] = field(default_factory=list)   # 致命問題
    warnings: List[str] = field(default_factory=list)   # 非致命提示

    def summary(self) -> str:
        """人類可讀的摘要."""
        if self.passed:
            parts = ["PreflightGate: PASSED"]
            if self.warnings:
                parts.append(f"（{len(self.warnings)} 個警告）")
            return " ".join(parts)
        return (
            f"PreflightGate: FAILED — "
            f"{len(self.failures)} 個致命問題, "
            f"{len(self.warnings)} 個警告"
        )


# ═══════════════════════════════════════════
# PreflightGate
# ═══════════════════════════════════════════


class PreflightGate:
    """啟動前驗證門 — 生物體的胸腺.

    在 main() 中、uvicorn 啟動前執行。
    失敗時由呼叫者決定 exit(0)，避免觸發 launchd 重啟迴圈。

    使用方式::

        gate = PreflightGate()
        result = gate.run()
        if not result.passed:
            for f in result.failures:
                logger.error(f"Preflight FATAL: {f}")
            sys.exit(0)
    """

    # Placeholder 常見模式
    PLACEHOLDER_PATTERNS: List[str] = [
        "your-",
        "placeholder",
        "xxx",
        "todo",
        "change-me",
        "change_me",
        "insert-",
        "insert_",
        "replace-",
        "replace_",
        "example",
        "test-key",
        "test_key",
        "put-your",
        "put_your",
        "fill-in",
        "fill_in",
    ]

    # 必要 API Key：(環境變數名, 預期前綴 or None)
    # 注意：ANTHROPIC_API_KEY 已移至 OPTIONAL（MUSEON 使用 Max CLI OAuth，API Key 僅為備援）
    REQUIRED_KEYS: List[Tuple[str, Optional[str]]] = []

    # 選填 API Key：有值就驗證格式，沒值只發警告
    # ANTHROPIC_API_KEY 已完全移除（MUSEON 統一使用 Claude MAX CLI OAuth）
    OPTIONAL_KEYS: List[Tuple[str, Optional[str]]] = [
        ("TELEGRAM_BOT_TOKEN", None),
        ("DIFY_API_KEY", None),
    ]

    def run(self) -> PreflightResult:
        """執行所有預檢.

        Returns:
            PreflightResult: 包含 passed, failures, warnings
        """
        failures: List[str] = []
        warnings: List[str] = []

        # ── 1. 必要 API Key 檢查 ──
        self._check_required_keys(failures, warnings)

        # ── 2. 選填 API Key 檢查 ──
        self._check_optional_keys(warnings)

        # ── 3. MUSEON_HOME 目錄存在性 ──
        self._check_museon_home(failures)

        # ── 4. Setup Wizard 完成狀態 ──
        self._check_setup_done(failures)

        # ── 5. .env 檔案存在性 ──
        self._check_env_file(warnings)

        passed = len(failures) == 0
        result = PreflightResult(
            passed=passed, failures=failures, warnings=warnings
        )

        # 記錄結果
        if passed:
            logger.info(result.summary())
        else:
            logger.error(result.summary())

        return result

    # ─── 內部檢查方法 ───────────────────────────

    def _check_required_keys(
        self, failures: List[str], warnings: List[str]
    ) -> None:
        """檢查必要 API Key."""
        for key, prefix in self.REQUIRED_KEYS:
            val = os.environ.get(key, "").strip()
            if not val:
                failures.append(f"{key} 未設定")
            elif self._is_placeholder(val):
                failures.append(
                    f"{key} 是 placeholder 值 — 請在 .env 中填入真實 Key"
                )
            elif prefix and not val.startswith(prefix):
                warnings.append(
                    f"{key} 格式異常（預期前綴 '{prefix}'）"
                )

    def _check_optional_keys(self, warnings: List[str]) -> None:
        """檢查選填 API Key（有值就驗證，沒值不報錯）."""
        for key, prefix in self.OPTIONAL_KEYS:
            val = os.environ.get(key, "").strip()
            if not val:
                # 沒設定 = 該功能不啟用，不算錯誤
                continue
            if self._is_placeholder(val):
                warnings.append(
                    f"{key} 是 placeholder 值，該功能將停用"
                )
            elif prefix and not val.startswith(prefix):
                warnings.append(
                    f"{key} 格式異常（預期前綴 '{prefix}'）"
                )

    def _check_museon_home(self, failures: List[str]) -> None:
        """檢查 MUSEON_HOME 目錄."""
        home = os.environ.get("MUSEON_HOME", "").strip()
        if home and not Path(home).is_dir():
            failures.append(f"MUSEON_HOME={home} 目錄不存在")

    def _check_setup_done(self, failures: List[str]) -> None:
        """檢查 Setup Wizard 是否已完成."""
        setup_done = os.environ.get("MUSEON_SETUP_DONE", "").strip()
        if setup_done == "0":
            failures.append(
                "MUSEON_SETUP_DONE=0 — Setup Wizard 尚未完成，"
                "請先執行 Setup Wizard 或在 .env 中設定 MUSEON_SETUP_DONE=1"
            )

    def _check_env_file(self, warnings: List[str]) -> None:
        """檢查 .env 檔案是否存在."""
        env_path = self._find_env_file()
        if env_path is None:
            warnings.append("找不到 .env 檔案 — 環境變數可能不完整")

    # ─── 工具方法 ───────────────────────────────

    def _is_placeholder(self, value: str) -> bool:
        """偵測 placeholder 值.

        Args:
            value: 要檢查的值

        Returns:
            True 如果值看起來像 placeholder
        """
        lower = value.lower().strip()
        if not lower:
            return False
        return any(pattern in lower for pattern in self.PLACEHOLDER_PATTERNS)

    @staticmethod
    def _find_env_file() -> Optional[Path]:
        """找到 .env 檔案路徑.

        解析順序：
        1. $MUSEON_HOME/.env
        2. 從 governance/ 目錄向上找 pyproject.toml
        3. ~/MUSEON/.env
        """
        # 1. MUSEON_HOME
        home = os.environ.get("MUSEON_HOME", "")
        if home:
            candidate = Path(home) / ".env"
            if candidate.exists():
                return candidate

        # 2. 從此檔案向上找
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "pyproject.toml").exists():
                candidate = parent / ".env"
                if candidate.exists():
                    return candidate

        # 3. Fallback
        candidate = Path.home() / "MUSEON" / ".env"
        if candidate.exists():
            return candidate

        return None
