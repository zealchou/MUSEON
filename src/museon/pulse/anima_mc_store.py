"""AnimaMCStore — ANIMA_MC.json 統一存取層.

解決三種互不相容的寫入策略：
- brain.py: threading.Lock + KernelGuard + WriteQueue
- anima_tracker.py: 原子寫入但無 lock
- micro_pulse.py: 直接寫入，無 lock 無原子

所有模組透過此 Store 讀寫 ANIMA_MC.json，確保：
1. 單一鎖（threading.Lock）防止並發覆蓋
2. 原子寫入（tmp → rename）防止損壞
3. KernelGuard 驗證防止非法修改
4. DataContract 介面接入 DataBus 監控

設計文件：docs/joint-map.md #1 ANIMA_MC.json
影響範圍：docs/blast-radius.md G1 模組組
"""

import json
import logging
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from museon.core.data_bus import DataContract, StoreEngine, StoreSpec, TTLTier

logger = logging.getLogger(__name__)


class AnimaMCStore(DataContract):
    """ANIMA_MC.json 統一存取層 — 單一寫入入口.

    設計原則：
    - 一個資源一個 Owner（本 Store 是 ANIMA_MC.json 的唯一寫入入口）
    - 讀取不需鎖（寫入是原子的，讀到的永遠是完整 JSON）
    - 寫入三重保護：Lock → KernelGuard → 原子寫入
    """

    def __init__(self, path: Path, kernel_guard=None) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._kernel_guard = kernel_guard
        self._write_count = 0
        self._last_write_ts = 0.0

    def set_kernel_guard(self, kernel_guard) -> None:
        """注入 KernelGuard（解決初始化順序：Store 先建，KernelGuard 後建）."""
        self._kernel_guard = kernel_guard

    @property
    def path(self) -> Path:
        """取得 ANIMA_MC.json 路徑（供向後相容）."""
        return self._path

    # ─── 讀取（不需鎖）───────────────────────────

    def load(self) -> Optional[Dict[str, Any]]:
        """讀取 ANIMA_MC.json.

        不需要鎖：寫入是原子的（tmp → rename），
        讀到的永遠是完整的 JSON（不會讀到寫到一半的檔案）。
        """
        if not self._path.exists():
            return None
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"AnimaMCStore load failed: {e}", exc_info=True)
            return None

    # ─── 寫入（Lock + KernelGuard + 原子）────────

    def save(self, data: Dict[str, Any]) -> bool:
        """全量寫入（Lock + KernelGuard + 原子寫入）.

        Args:
            data: 完整的 ANIMA_MC dict

        Returns:
            True 寫入成功，False 被 KernelGuard 拒絕或寫入失敗
        """
        with self._lock:
            return self._save_internal(data)

    def update(
        self, updater: Callable[[Dict[str, Any]], Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Read-Modify-Write 原子操作.

        在鎖內完成讀取→修改→寫入，防止並發覆蓋。

        Args:
            updater: 接收當前 data dict，回傳修改後的 dict

        Returns:
            修改後的 data，或 None（檔案不存在或寫入失敗時）
        """
        with self._lock:
            data = self._load_internal()
            if data is None:
                return None
            modified = updater(data)
            if self._save_internal(modified):
                return modified
            return None

    def update_section(
        self,
        section: str,
        updater: Callable[[Any], Any],
    ) -> bool:
        """更新指定 section（語義便利方法）.

        Args:
            section: 頂層 key 名稱（如 "identity", "eight_primal_energies"）
            updater: 接收 section 的當前值，回傳修改後的值

        Returns:
            True 成功
        """
        with self._lock:
            data = self._load_internal()
            if data is None:
                return False
            data[section] = updater(data.get(section, {}))
            return self._save_internal(data)

    # ─── 內部方法（呼叫者已持有鎖）──────────────

    def _load_internal(self) -> Optional[Dict[str, Any]]:
        """內部讀取（呼叫者已持有鎖）."""
        if not self._path.exists():
            return None
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"AnimaMCStore internal load failed: {e}", exc_info=True)
            return None

    def _backup_before_write(self) -> None:
        """寫入前自動快照 — 保留最近 10 份備份."""
        try:
            if not self._path.exists():
                return

            backup_dir = self._path.parent / "_system" / "backups" / "anima_mc"
            backup_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"anima_mc_{timestamp}.json"

            shutil.copy2(self._path, backup_path)

            # 保留最近 10 份，清理舊的
            backups = sorted(backup_dir.glob("anima_mc_*.json"))
            if len(backups) > 10:
                for old in backups[:-10]:
                    old.unlink()

            logger.debug(f"ANIMA_MC 快照已建立: {backup_path.name}")
        except Exception as e:
            logger.debug(f"ANIMA_MC 快照失敗（降級，不阻斷寫入）: {e}")

    def _save_internal(self, data: Dict[str, Any]) -> bool:
        """內部寫入（呼叫者已持有鎖）.

        流程：快照 → KernelGuard 驗證 → 原子寫入（tmp → rename）
        """
        try:
            # ── 寫入前快照 ──
            self._backup_before_write()
            # ── KernelGuard 驗證 ──
            if self._kernel_guard:
                old_data = self._load_internal()
                decision, violations = self._kernel_guard.validate_write(
                    "ANIMA_MC", old_data, data
                )
                if decision.value == "deny":
                    logger.error(
                        f"KernelGuard DENY ANIMA_MC 寫入: {violations}"
                    )
                    return False
                if violations:
                    logger.warning(
                        f"KernelGuard 警告 ANIMA_MC: {violations}"
                    )

            # ── 原子寫入：先寫 tmp 再 rename ──
            tmp_path = self._path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_path.replace(self._path)

            self._write_count += 1
            self._last_write_ts = time.time()
            return True
        except Exception as e:
            logger.error(f"AnimaMCStore save failed: {e}", exc_info=True)
            return False

    # ─── DataContract 介面 ───────────────────────

    @classmethod
    def store_spec(cls) -> StoreSpec:
        return StoreSpec(
            name="anima_mc",
            engine=StoreEngine.JSON,
            ttl=TTLTier.PERMANENT,
            write_mode="replace",
            description="MUSEON 靈魂核心——身份、人格、能力、演化狀態",
            tables=["ANIMA_MC.json"],
        )

    def health_check(self) -> Dict[str, Any]:
        status = "ok"
        details: Dict[str, Any] = {
            "write_count": self._write_count,
            "last_write_ts": self._last_write_ts,
        }

        if not self._path.exists():
            status = "error"
            details["error"] = "ANIMA_MC.json not found"
        else:
            try:
                data = self.load()
                if data is None:
                    status = "error"
                    details["error"] = "Failed to parse ANIMA_MC.json"
                else:
                    details["size_bytes"] = self._path.stat().st_size
                    details["fields"] = len(data)
                    if "identity" not in data:
                        status = "degraded"
                        details["warning"] = "missing identity section"
            except Exception as e:
                status = "error"
                details["error"] = str(e)

        return {"status": status, **details}


# ════════════════════════════════════════════
# Singleton 工廠
# ════════════════════════════════════════════

_instance: Optional[AnimaMCStore] = None
_instance_lock = threading.Lock()


def get_anima_mc_store(
    path: Optional[Path] = None,
    kernel_guard=None,
) -> AnimaMCStore:
    """取得 AnimaMCStore 單例.

    首次呼叫必須提供 path。之後可不帶參數取得同一實例。
    kernel_guard 可在首次或之後透過 set_kernel_guard() 注入。

    設計模式與 get_pulse_db()、get_event_bus() 一致。
    """
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                if path is None:
                    raise RuntimeError(
                        "AnimaMCStore 尚未初始化：首次呼叫必須提供 path"
                    )
                _instance = AnimaMCStore(path, kernel_guard)
    if kernel_guard and _instance._kernel_guard is None:
        _instance.set_kernel_guard(kernel_guard)
    return _instance


def reset_anima_mc_store() -> None:
    """重置單例（僅供測試使用）."""
    global _instance
    _instance = None
