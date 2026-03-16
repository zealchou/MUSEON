"""RefractoryGuard — 跨重啟斷路器（不應期）.

模擬生物神經元的「不應期」機制：
  - 連續啟動失敗 → 遞增冷卻時間
  - 失敗次數過多 → 進入休眠（不再重啟）
  - 外部干預（修改 .env 或刪除 state 檔案）→ 喚醒
  - 1 小時無失敗 → 自然痊癒（計數歸零）

狀態持久化：
  - ~/.museon/refractory_state.json
  - 跨 process 重啟保留失敗計數和休眠狀態

退避表（對照 K8s CrashLoopBackOff）：
  - 1-2 次失敗：正常重啟，無等待
  - 3-5 次失敗：30 秒冷卻
  - 6-9 次失敗：5 分鐘冷卻
  - 10+ 次失敗：休眠（exit(0) 不重啟，等外部干預）

半開試探（對照 Circuit Breaker half-open）：
  - 休眠超過 30 分鐘 → 自動進入半開狀態
  - 半開時允許一次試探性重啟
  - 試探成功 → 清零、完全恢復
  - 試探失敗 → 回到休眠、失敗計數 +1

喚醒條件：
  - .env 檔案 mtime 變更（使用者修改了配置）
  - refractory_state.json 被刪除
  - 30 分鐘半開試探（自動）
  - 6 小時完全喚醒（自動）

DSE 參考：
  - K8s CrashLoopBackOff: 10s→20s→40s→...→300s cap
  - systemd StartLimitBurst: N 次失敗後停止重啟
  - 生物神經元不應期：動作電位後的冷卻期
  - Erlang OTP: max_restarts / max_seconds supervisor 策略
  - Netflix Hystrix: closed→open→half-open 三態斷路器
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

# 退避等級表：(失敗次數下限, 上限) → 冷卻秒數 (None = 休眠)
BACKOFF_LEVELS: List[Tuple[int, int, Optional[int]]] = [
    (1, 2, 0),         # 正常重啟，無等待
    (3, 5, 30),        # 30 秒冷卻
    (6, 9, 300),       # 5 分鐘冷卻
    (10, 999, None),   # 休眠
]

HEAL_TIMEOUT_SECS = 3600       # 1 小時無失敗 = 自然痊癒
AUTO_WAKE_SECS = 21600         # 6 小時自動嘗試修復一次
HALF_OPEN_SECS = 1800          # 30 分鐘後自動半開（試探性恢復）


# ═══════════════════════════════════════════
# 狀態模型
# ═══════════════════════════════════════════


@dataclass
class RefractoryState:
    """跨重啟持久化的斷路器狀態."""

    failure_count: int = 0
    last_failure_ts: float = 0.0
    hibernating: bool = False
    hibernate_reason: str = ""
    env_mtime: float = 0.0
    half_open: bool = False            # 半開試探狀態
    half_open_since: float = 0.0       # 進入半開的時間戳


# ═══════════════════════════════════════════
# RefractoryGuard
# ═══════════════════════════════════════════


class RefractoryGuard:
    """跨重啟斷路器 — 生物神經元的不應期.

    狀態持久化到 ~/.museon/refractory_state.json。
    在 Gateway main() 中、Preflight 之後執行。

    使用方式::

        guard = RefractoryGuard()
        action, wait_secs = guard.check()

        if action == "hibernate":
            logger.warning("休眠中")
            sys.exit(0)
        elif action == "backoff":
            time.sleep(wait_secs)
        # action == "proceed" → 正常啟動

    啟動成功後呼叫::

        guard.record_success()  # 清零計數器
    """

    STATE_DIR = Path.home() / ".museon"
    STATE_FILE = Path.home() / ".museon" / "refractory_state.json"

    def check(self) -> Tuple[str, int]:
        """檢查當前狀態，決定行動.

        Returns:
            ("proceed", 0)     → 正常啟動（含半開試探）
            ("backoff", secs)  → 需等待 N 秒後重啟
            ("hibernate", 0)   → 休眠，由呼叫者 exit(0)
        """
        state = self._load_state()

        # ── 半開狀態：允許試探性重啟 ──
        if state.half_open:
            logger.info(
                "RefractoryGuard: 半開狀態，允許一次試探性重啟"
            )
            return ("proceed", 0)

        # ── 檢查是否在休眠中 ──
        if state.hibernating:
            # 1. 外部干預（.env 變更 / 6 小時自動）→ 完全喚醒
            if self._should_wake(state):
                logger.info(
                    "RefractoryGuard: 偵測到外部干預，從休眠中喚醒"
                )
                state.hibernating = False
                state.half_open = False
                state.half_open_since = 0.0
                state.failure_count = 0
                state.hibernate_reason = ""
                self._save_state(state)
                return ("proceed", 0)

            # 2. 半開試探：休眠超過 HALF_OPEN_SECS → 進入半開
            if state.last_failure_ts > 0:
                elapsed = time.time() - state.last_failure_ts
                if elapsed > HALF_OPEN_SECS:
                    logger.info(
                        f"RefractoryGuard: 休眠 {elapsed:.0f}s，"
                        f"進入半開試探狀態"
                    )
                    state.half_open = True
                    state.half_open_since = time.time()
                    self._save_state(state)
                    return ("proceed", 0)

            logger.warning(
                f"RefractoryGuard: 仍在休眠中"
                f"（原因: {state.hibernate_reason}，"
                f"失敗 {state.failure_count} 次）"
            )
            return ("hibernate", 0)

        # ── 檢查是否自然痊癒 ──
        if state.failure_count > 0:
            elapsed = time.time() - state.last_failure_ts
            if elapsed > HEAL_TIMEOUT_SECS:
                logger.info(
                    f"RefractoryGuard: {elapsed:.0f}s 無失敗，自然痊癒"
                )
                state.failure_count = 0
                self._save_state(state)
                return ("proceed", 0)

        # ── 首次啟動或無失敗記錄 ──
        if state.failure_count == 0:
            return ("proceed", 0)

        # ── 查退避表 ──
        for lo, hi, wait in BACKOFF_LEVELS:
            if lo <= state.failure_count <= hi:
                if wait is None:
                    return ("hibernate", 0)
                if wait > 0:
                    logger.warning(
                        f"RefractoryGuard: 第 {state.failure_count} 次失敗，"
                        f"冷卻 {wait} 秒"
                    )
                    return ("backoff", wait)
                return ("proceed", 0)

        # 不應到達
        return ("proceed", 0)

    def record_failure(self, reason: str = "") -> None:
        """記錄一次啟動失敗.

        Args:
            reason: 失敗原因（用於休眠日誌）
        """
        state = self._load_state()
        state.failure_count += 1
        state.last_failure_ts = time.time()

        # 記錄當前 .env mtime（供喚醒比對）
        env_path = self._find_env_file()
        if env_path:
            try:
                state.env_mtime = env_path.stat().st_mtime
            except OSError as e:
                logger.debug(f"[REFRACTORY] file stat failed (degraded): {e}")

        # ── 半開試探失敗 → 回到休眠 ──
        if state.half_open:
            state.half_open = False
            state.half_open_since = 0.0
            state.hibernating = True
            state.hibernate_reason = (
                reason or "半開試探失敗，回到休眠"
            )
            logger.warning(
                f"RefractoryGuard: 半開試探失敗（{state.hibernate_reason}），"
                f"回到休眠（失敗 {state.failure_count} 次）"
            )
            self._save_state(state)
            return

        # 達到休眠門檻
        if state.failure_count >= 10:
            state.hibernating = True
            state.hibernate_reason = reason or "連續失敗超過 10 次"
            logger.error(
                f"RefractoryGuard: 進入休眠（{state.hibernate_reason}）"
            )

        self._save_state(state)
        logger.warning(
            f"RefractoryGuard: 記錄失敗 #{state.failure_count}"
            f"（原因: {reason}）"
        )

    def record_success(self) -> None:
        """記錄啟動成功 — 清零計數器.

        若在半開試探狀態下成功，則完全恢復（關閉斷路器）。
        """
        state = self._load_state()
        if state.half_open:
            logger.info(
                "RefractoryGuard: 半開試探成功！完全恢復"
                f"（從 {state.failure_count} 次失敗中恢復）"
            )
        elif state.failure_count > 0 or state.hibernating:
            logger.info(
                f"RefractoryGuard: 啟動成功，"
                f"清零失敗計數（原計 {state.failure_count}）"
            )
        state.failure_count = 0
        state.hibernating = False
        state.hibernate_reason = ""
        state.half_open = False
        state.half_open_since = 0.0
        self._save_state(state)

    def get_state(self) -> RefractoryState:
        """取得當前狀態（供健康檢查用）."""
        return self._load_state()

    # ─── 內部方法 ───────────────────────────────

    def _should_wake(self, state: RefractoryState) -> bool:
        """判斷是否應從休眠中完全喚醒（非半開）.

        完全喚醒條件（重置計數器）：
        1. .env 檔案 mtime 變了（使用者修改了配置）
        2. 6 小時自動嘗試修復一次
        3. state 檔案被外部刪除（由 _load_state 處理）

        注意：半開試探（30 分鐘）在 check() 中處理，不在此方法中。
        """
        # 1. .env mtime 變更
        env_path = self._find_env_file()
        if env_path:
            try:
                current_mtime = env_path.stat().st_mtime
                if state.env_mtime > 0 and current_mtime > state.env_mtime:
                    return True
            except OSError as e:
                logger.debug(f"[REFRACTORY] file stat failed (degraded): {e}")

        # 2. 24 小時自動嘗試
        if state.last_failure_ts > 0:
            elapsed = time.time() - state.last_failure_ts
            if elapsed > AUTO_WAKE_SECS:
                return True

        return False

    def _load_state(self) -> RefractoryState:
        """從磁碟載入狀態."""
        if not self.STATE_FILE.exists():
            return RefractoryState()
        try:
            data = json.loads(
                self.STATE_FILE.read_text(encoding="utf-8")
            )
            return RefractoryState(
                failure_count=data.get("failure_count", 0),
                last_failure_ts=data.get("last_failure_ts", 0.0),
                hibernating=data.get("hibernating", False),
                hibernate_reason=data.get("hibernate_reason", ""),
                env_mtime=data.get("env_mtime", 0.0),
                half_open=data.get("half_open", False),
                half_open_since=data.get("half_open_since", 0.0),
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                f"RefractoryGuard: 無法讀取 {self.STATE_FILE}: {e}，"
                f"重置為初始狀態"
            )
            return RefractoryState()

    def _save_state(self, state: RefractoryState) -> None:
        """持久化狀態到磁碟."""
        try:
            self.STATE_DIR.mkdir(parents=True, exist_ok=True)
            self.STATE_FILE.write_text(
                json.dumps(asdict(state), indent=2),
                encoding="utf-8",
            )
        except OSError as e:
            logger.error(
                f"RefractoryGuard: 無法寫入 {self.STATE_FILE}: {e}"
            )

    @staticmethod
    def _find_env_file() -> Optional[Path]:
        """找到 .env 檔案路徑.

        解析順序：
        1. $MUSEON_HOME/.env
        2. 從此檔案向上找 pyproject.toml
        3. ~/MUSEON/.env
        """
        home = os.environ.get("MUSEON_HOME", "")
        if home:
            candidate = Path(home) / ".env"
            if candidate.exists():
                return candidate

        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "pyproject.toml").exists():
                if parent.name == ".runtime":
                    candidate = parent.parent / ".env"
                else:
                    candidate = parent / ".env"
                if candidate.exists():
                    return candidate

        candidate = Path.home() / "MUSEON" / ".env"
        if candidate.exists():
            return candidate

        return None
