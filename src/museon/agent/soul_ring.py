"""靈魂日記 — append-only 成長記錄與日記系統.

靈魂年輪（Soul Ring / Diary）是 MUSEON 不可逆的成長痕跡：
  每一次認知突破、服務里程碑、失敗教訓、價值校準、每日摘要、反思
  都被刻入 append-only 記錄。
年輪如同樹的年輪——只進不退、不可竄改。

v2.0 重構（Phase 3.1）：
  - SoulRingStore 改名為 DiaryStore（保留向後相容別名）
  - SoulRing 新增 entry_type 欄位（daily_summary / event / reflection）
  - 新增 generate_daily_summary() 和 search_by_date_range()
  - 事件偵測門檻降低，更多互動可被記錄
  - ObservationRing 保留但標記為 deprecated，功能遷移到 ANIMA_USER L4

完整性保護：SHA-256 Hash Chain，第一條年輪的 prev_hash 為 "GENESIS"。
安全護欄：
  - append-only，拒絕修改與刪除
  - 每日即時寫入上限 5 條，多餘排入 Nightly Job 佇列
  - Morphenix 無法修改 L4 靈魂年輪（Kernel 保護）
  - 修改/刪除嘗試記錄到安全日誌
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, date, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from museon.core.data_bus import DataContract, StoreSpec, StoreEngine, TTLTier

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 常數定義
# ═══════════════════════════════════════════

# 年輪類型
SOUL_RING_TYPES = Literal[
    "cognitive_breakthrough",
    "service_milestone",
    "failure_lesson",
    "value_calibration",
]

# 日記條目類型（v2.0 新增）
DIARY_ENTRY_TYPES = Literal[
    "daily_summary",   # 每日摘要（Nightly Pipeline 自動生成）
    "event",           # 即時事件（互動觸發）
    "reflection",      # 反思筆記（Q-Score 異常、使用者重要決定等）
]

# 觀察年輪類型（deprecated: 功能遷移到 ANIMA_USER L4_interaction_rings）
OBSERVATION_RING_TYPES = Literal[
    "growth_observation",
    "pattern_shift",
    "preference_evolution",
    "milestone_witnessed",
]

# Hash Chain 起源值
GENESIS_HASH: str = "GENESIS"

# 每日即時寫入上限
DAILY_INSTANT_WRITE_LIMIT: int = 5

# Nightly Job 每日最多新增年輪數
NIGHTLY_BATCH_LIMIT: int = 3

# 重複偵測：比對最近 N 條年輪
DEDUP_WINDOW: int = 5

# 重複偵測閾值（語義相似度 > 此值視為重複）
DEDUP_SIMILARITY_THRESHOLD: float = 0.80

# 備份保留天數
BACKUP_RETENTION_DAYS: int = 30


# ═══════════════════════════════════════════
# 資料模型
# ═══════════════════════════════════════════


@dataclass
class SoulRing:
    """單條靈魂年輪 / 日記條目資料結構.

    靈魂年輪是 MUSEON 的不可逆成長記錄，一旦寫入不可修改或刪除。
    每條年輪透過 SHA-256 hash chain 與前一條年輪相連，形成完整性鏈。

    v2.0 新增 entry_type 欄位，支援三種條目類型：
      - daily_summary: 每日摘要（Nightly Pipeline 自動生成）
      - event: 即時事件（互動觸發的認知突破/里程碑/失敗/校準）
      - reflection: 反思筆記（Q-Score 異常、使用者重要決定等）

    Attributes:
        type: 年輪類型（cognitive_breakthrough / service_milestone /
              failure_lesson / value_calibration）
        description: 一句話摘要
        context: 觸發情境（對話摘要、相關技能、領域）
        impact: 對後續行為的影響預測
        created_at: ISO 8601 時間戳
        hash: SHA-256 雜湊值
        prev_hash: 前一條年輪的 hash（第一條為 "GENESIS"）
        reinforcement_count: 強化計數（相似事件重複發生時遞增）
        entry_type: 條目類型（daily_summary / event / reflection）
        milestone_name: （service_milestone 專用）里程碑名稱
        metrics: （service_milestone 專用）可量化成果
        failure_description: （failure_lesson 專用）失敗具體描述
        root_cause: （failure_lesson 專用）根因分析
        prevention: （failure_lesson 專用）預防措施
        original_behavior: （value_calibration 專用）原始行為
        correction: （value_calibration 專用）校正內容
        calibrated_value: （value_calibration 專用）受影響的核心價值
        resonance_link: 與 ANIMA_USER observation_ring 的共振連結
        highlights: （daily_summary 專用）當日亮點列表
        learnings: （daily_summary 專用）學習要點列表
        tomorrow_intent: （daily_summary 專用）明日意圖
    """

    type: str
    description: str
    context: str
    impact: str
    created_at: str
    hash: str = ""
    prev_hash: str = GENESIS_HASH
    reinforcement_count: int = 0
    entry_type: str = "event"  # v2.0: daily_summary / event / reflection

    # service_milestone 專用欄位
    milestone_name: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None

    # failure_lesson 專用欄位
    failure_description: Optional[str] = None
    root_cause: Optional[str] = None
    prevention: Optional[str] = None

    # value_calibration 專用欄位
    original_behavior: Optional[str] = None
    correction: Optional[str] = None
    calibrated_value: Optional[str] = None

    # 共振連結
    resonance_link: Optional[Dict[str, Any]] = None

    # daily_summary 專用欄位（v2.0）
    highlights: Optional[List[str]] = None
    learnings: Optional[List[str]] = None
    tomorrow_intent: Optional[str] = None

    def compute_hash(self, prev_hash: str) -> str:
        """計算此年輪的 SHA-256 雜湊值.

        雜湊計算包含：type + description + context + created_at + prev_hash

        Args:
            prev_hash: 前一條年輪的 hash

        Returns:
            SHA-256 十六進位字串
        """
        payload = (
            f"{self.type}"
            f"{self.description}"
            f"{self.context}"
            f"{self.created_at}"
            f"{prev_hash}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典（序列化用）.

        Returns:
            包含所有非 None 欄位的字典
        """
        data = asdict(self)
        # 移除值為 None 的可選欄位，保持 JSON 簡潔
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SoulRing":
        """從字典還原年輪物件.

        Args:
            data: 年輪字典資料

        Returns:
            SoulRing 實例
        """
        # 只取 dataclass 定義的欄位
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class ObservationRing:
    """單條使用者觀察年輪資料結構.

    觀察年輪記錄 MUSEON 對使用者成長的觀察，
    只記錄抽象化的結論，不包含具體對話內容。

    Attributes:
        type: 觀察類型（growth_observation / pattern_shift /
              preference_evolution / milestone_witnessed）
        description: 觀察結論（抽象化，不含具體對話）
        context: 觸發情境
        impact: 對使用者理解的影響
        created_at: ISO 8601 時間戳
        hash: SHA-256 雜湊值
        prev_hash: 前一條觀察年輪的 hash（第一條為 "GENESIS"）
        reinforcement_count: 強化計數
        resonance_link: 與 MUSEON soul_ring 的共振連結
    """

    type: str
    description: str
    context: str
    impact: str
    created_at: str
    hash: str = ""
    prev_hash: str = GENESIS_HASH
    reinforcement_count: int = 0
    resonance_link: Optional[Dict[str, Any]] = None

    def compute_hash(self, prev_hash: str) -> str:
        """計算此觀察年輪的 SHA-256 雜湊值.

        Args:
            prev_hash: 前一條觀察年輪的 hash

        Returns:
            SHA-256 十六進位字串
        """
        payload = (
            f"{self.type}"
            f"{self.description}"
            f"{self.context}"
            f"{self.created_at}"
            f"{prev_hash}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典.

        Returns:
            包含所有非 None 欄位的字典
        """
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ObservationRing":
        """從字典還原觀察年輪物件.

        Args:
            data: 觀察年輪字典資料

        Returns:
            ObservationRing 實例
        """
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


# ═══════════════════════════════════════════
# 持久化層
# ═══════════════════════════════════════════


class DiaryStore(DataContract):
    """靈魂日記持久化層（v2.0，原 SoulRingStore 重構）.

    負責日記條目（年輪）的載入、儲存、備份、完整性驗證與日期檢索。
    所有寫入操作使用執行緒鎖保護，確保並發安全。
    每次寫入後執行 fsync 確保落盤。

    存儲路徑：
      - soul_rings:       data/anima/soul_rings.json
      - observation_rings: data/anima/observation_rings.json（deprecated）
      - 每日備份:          data/anima/backups/soul_rings_{date}.json
    """

    @classmethod
    def store_spec(cls) -> StoreSpec:
        return StoreSpec(
            name="diary_store",
            engine=StoreEngine.JSON,
            ttl=TTLTier.PERMANENT,
            write_mode="append_only",
            description="靈魂日記 append-only 成長記錄",
            tables=["soul_rings.json", "observation_rings.json"],
        )

    def health_check(self) -> Dict[str, Any]:
        try:
            soul_size = self._soul_rings_path.stat().st_size if self._soul_rings_path.exists() else 0
            obs_size = self._observation_rings_path.stat().st_size if self._observation_rings_path.exists() else 0
            return {
                "status": "ok",
                "soul_rings_bytes": soul_size,
                "observation_rings_bytes": obs_size,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def __init__(self, data_dir: str = "data") -> None:
        """初始化持久化層.

        Args:
            data_dir: 資料根目錄（預設 "data"）
        """
        self._data_dir = Path(data_dir)
        self._anima_dir = self._data_dir / "anima"
        self._backup_dir = self._anima_dir / "backups"

        # 確保目錄存在
        self._anima_dir.mkdir(parents=True, exist_ok=True)
        self._backup_dir.mkdir(parents=True, exist_ok=True)

        # 檔案路徑
        self._soul_rings_path = self._anima_dir / "soul_rings.json"
        self._observation_rings_path = self._anima_dir / "observation_rings.json"

        # 執行緒鎖（保護檔案讀寫）
        self._soul_lock = threading.Lock()
        self._observation_lock = threading.Lock()

        logger.info(
            f"DiaryStore initialized | "
            f"soul_rings: {self._soul_rings_path} | "
            f"observation_rings: {self._observation_rings_path}"
        )

    # ── 靈魂年輪 CRUD ──

    def load_soul_rings(self, verify: bool = True) -> List[Dict[str, Any]]:
        """載入所有靈魂年輪（含自動完整性驗證）.

        Args:
            verify: 是否在載入後驗證 SHA-256 鏈完整性

        Returns:
            年輪字典列表（JSON array 反序列化結果）
        """
        with self._soul_lock:
            rings = self._read_json(self._soul_rings_path)

        if verify and rings:
            is_valid, msg = self.verify_soul_ring_integrity()
            if not is_valid:
                logger.error(f"Soul Ring 完整性驗證失敗: {msg}")
                # 嘗試從備份恢復
                recovered = self._try_recover_from_backup("soul_rings")
                if recovered is not None:
                    logger.info("Soul Ring 已從備份恢復")
                    return recovered
                logger.warning("無可用備份，返回可能損壞的資料")

        return rings

    def append_soul_ring(self, ring: SoulRing) -> None:
        """追加一條靈魂年輪（append-only）.

        寫入後立即 fsync 確保落盤。

        Args:
            ring: 要追加的年輪

        Raises:
            PermissionError: 如果嘗試修改已存在的年輪
        """
        with self._soul_lock:
            rings = self._read_json(self._soul_rings_path)
            rings.append(ring.to_dict())
            self._write_json_atomic(self._soul_rings_path, rings)
        logger.info(
            f"Soul ring appended | type={ring.type} | "
            f"hash={ring.hash[:12]}..."
        )

    def update_reinforcement_count(
        self, index: int, new_count: int
    ) -> None:
        """更新指定年輪的 reinforcement_count（唯一允許的「修改」操作）.

        這不是真正的修改——只有 reinforcement_count 欄位可被遞增，
        用於記錄相似事件的強化信號。Hash 不受影響。

        Args:
            index: 年輪索引
            new_count: 新的強化計數

        Raises:
            IndexError: 索引超出範圍
        """
        with self._soul_lock:
            rings = self._read_json(self._soul_rings_path)
            if index < 0 or index >= len(rings):
                raise IndexError(
                    f"年輪索引 {index} 超出範圍（共 {len(rings)} 條）"
                )
            rings[index]["reinforcement_count"] = new_count
            self._write_json_atomic(self._soul_rings_path, rings)
        logger.info(
            f"Soul ring reinforcement updated | "
            f"index={index} count={new_count}"
        )

    # ── 觀察年輪 CRUD ──

    def load_observation_rings(self) -> List[Dict[str, Any]]:
        """載入所有使用者觀察年輪.

        Returns:
            觀察年輪字典列表
        """
        with self._observation_lock:
            return self._read_json(self._observation_rings_path)

    def append_observation_ring(self, ring: ObservationRing) -> None:
        """追加一條觀察年輪（append-only）.

        Args:
            ring: 要追加的觀察年輪
        """
        with self._observation_lock:
            rings = self._read_json(self._observation_rings_path)
            rings.append(ring.to_dict())
            self._write_json_atomic(self._observation_rings_path, rings)
        logger.info(
            f"Observation ring appended | type={ring.type} | "
            f"hash={ring.hash[:12]}..."
        )

    def update_observation_reinforcement(
        self, index: int, new_count: int
    ) -> None:
        """更新觀察年輪的 reinforcement_count.

        Args:
            index: 年輪索引
            new_count: 新的強化計數
        """
        with self._observation_lock:
            rings = self._read_json(self._observation_rings_path)
            if index < 0 or index >= len(rings):
                raise IndexError(
                    f"觀察年輪索引 {index} 超出範圍（共 {len(rings)} 條）"
                )
            rings[index]["reinforcement_count"] = new_count
            self._write_json_atomic(
                self._observation_rings_path, rings
            )

    # ── 完整性驗證 ──

    def verify_soul_ring_integrity(self) -> Tuple[bool, str]:
        """驗證靈魂年輪的 SHA-256 Hash Chain 完整性.

        從第一條年輪開始逐一驗證：
          1. 每條年輪的 hash 必須等於重新計算的值
          2. 每條年輪的 prev_hash 必須等於前一條的 hash

        Returns:
            (is_valid, message) 元組
            - 若通過：(True, "Soul Ring Integrity: VALID")
            - 若失敗：(False, "Soul Ring Integrity: CORRUPTED at ring #{index}")
        """
        rings = self.load_soul_rings(verify=False)
        return self._verify_chain(rings, "Soul Ring")

    def verify_observation_ring_integrity(self) -> Tuple[bool, str]:
        """驗證觀察年輪的 SHA-256 Hash Chain 完整性.

        Returns:
            (is_valid, message) 元組
        """
        rings = self.load_observation_rings()
        return self._verify_chain(rings, "Observation Ring")

    def _verify_chain(
        self, rings: List[Dict[str, Any]], chain_name: str
    ) -> Tuple[bool, str]:
        """驗證一條 hash chain 的完整性.

        Args:
            rings: 年輪字典列表
            chain_name: 鏈名稱（用於錯誤訊息）

        Returns:
            (is_valid, message) 元組
        """
        if not rings:
            return True, f"{chain_name} Integrity: VALID"

        expected_prev_hash = GENESIS_HASH

        for i, ring_data in enumerate(rings):
            # 驗證 prev_hash 鏈接
            stored_prev_hash = ring_data.get("prev_hash", "")
            if stored_prev_hash != expected_prev_hash:
                msg = (
                    f"{chain_name} Integrity: CORRUPTED at ring #{i}"
                )
                logger.error(msg)
                return False, msg

            # 重新計算 hash 並驗證
            payload = (
                f"{ring_data.get('type', '')}"
                f"{ring_data.get('description', '')}"
                f"{ring_data.get('context', '')}"
                f"{ring_data.get('created_at', '')}"
                f"{stored_prev_hash}"
            )
            computed_hash = hashlib.sha256(
                payload.encode("utf-8")
            ).hexdigest()
            stored_hash = ring_data.get("hash", "")

            if computed_hash != stored_hash:
                msg = (
                    f"{chain_name} Integrity: CORRUPTED at ring #{i}"
                )
                logger.error(msg)
                return False, msg

            # 下一條年輪的 prev_hash 應等於此條的 hash
            expected_prev_hash = stored_hash

        return True, f"{chain_name} Integrity: VALID"

    # ── 備份恢復 ──

    def _try_recover_from_backup(self, ring_type: str) -> Optional[List[Dict[str, Any]]]:
        """嘗試從最近的備份恢復損壞的年輪資料.

        Args:
            ring_type: "soul_rings" 或 "observation_rings"

        Returns:
            恢復的年輪列表，或 None（無可用備份）
        """
        if not self._backup_dir.exists():
            return None

        # 尋找最近的備份
        pattern = f"{ring_type}_*.json"
        backups = sorted(self._backup_dir.glob(pattern), reverse=True)

        for backup_path in backups[:5]:  # 最多嘗試 5 個備份
            try:
                with open(backup_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, list):
                    # 驗證備份的完整性
                    chain_valid, _ = self._verify_chain(data, ring_type)
                    if chain_valid:
                        # 備份有效 → 恢復
                        target = (
                            self._soul_rings_path
                            if ring_type == "soul_rings"
                            else self._observation_rings_path
                        )
                        self._write_json_atomic(target, data)
                        logger.info(
                            f"已從備份恢復 {ring_type}: {backup_path.name}"
                        )
                        return data
            except Exception as e:
                logger.warning(f"嘗試備份 {backup_path.name} 失敗: {e}")
                continue

        return None

    # ── 備份 ──

    def create_backup(self, target_date: Optional[date] = None) -> Path:
        """建立靈魂年輪的每日備份.

        備份路徑：data/anima/backups/soul_rings_{YYYY-MM-DD}.json

        Args:
            target_date: 備份日期（預設今天）

        Returns:
            備份檔案路徑
        """
        target_date = target_date or date.today()
        date_str = target_date.isoformat()
        backup_path = self._backup_dir / f"soul_rings_{date_str}.json"

        with self._soul_lock:
            if self._soul_rings_path.exists():
                shutil.copy2(self._soul_rings_path, backup_path)
            else:
                # 若原檔不存在，建立空備份
                self._write_json_atomic(backup_path, [])

        logger.info(f"Soul ring backup created | path={backup_path}")
        return backup_path

    def create_observation_backup(
        self, target_date: Optional[date] = None
    ) -> Path:
        """建立觀察年輪的每日備份.

        Args:
            target_date: 備份日期（預設今天）

        Returns:
            備份檔案路徑
        """
        target_date = target_date or date.today()
        date_str = target_date.isoformat()
        backup_path = (
            self._backup_dir / f"observation_rings_{date_str}.json"
        )

        with self._observation_lock:
            if self._observation_rings_path.exists():
                shutil.copy2(
                    self._observation_rings_path, backup_path
                )
            else:
                self._write_json_atomic(backup_path, [])

        logger.info(
            f"Observation ring backup created | path={backup_path}"
        )
        return backup_path

    def rotate_backups(self, retention_days: int = BACKUP_RETENTION_DAYS) -> int:
        """清理過期備份（保留最近 N 天）.

        Args:
            retention_days: 保留天數（預設 30 天）

        Returns:
            刪除的備份檔案數量
        """
        cutoff = date.today() - timedelta(days=retention_days)
        removed = 0

        for backup_file in self._backup_dir.glob("*.json"):
            # 從檔名解析日期：soul_rings_2026-01-15.json
            name = backup_file.stem  # soul_rings_2026-01-15
            parts = name.rsplit("_", 3)
            if len(parts) >= 4:
                # 日期在最後三個部分: YYYY-MM-DD
                date_str = f"{parts[-3]}-{parts[-2]}-{parts[-1]}"
            else:
                continue

            try:
                file_date = date.fromisoformat(date_str)
            except ValueError:
                continue

            if file_date < cutoff:
                backup_file.unlink()
                removed += 1
                logger.debug(f"Removed expired backup: {backup_file}")

        if removed > 0:
            logger.info(
                f"Backup rotation completed | removed={removed} | "
                f"retention={retention_days}d"
            )
        return removed

    def restore_from_backup(self, backup_path: Path) -> bool:
        """從備份恢復靈魂年輪.

        恢復前會驗證備份的 hash chain 完整性。

        Args:
            backup_path: 備份檔案路徑

        Returns:
            True 表示恢復成功
        """
        if not backup_path.exists():
            logger.error(f"Backup file not found: {backup_path}")
            return False

        # 讀取備份並驗證完整性
        try:
            with open(backup_path, "r", encoding="utf-8") as f:
                backup_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to read backup: {e}")
            return False

        # 驗證備份的 hash chain
        is_valid, msg = self._verify_chain(backup_data, "Backup")
        if not is_valid:
            logger.error(f"Backup integrity check failed: {msg}")
            return False

        # 恢復
        with self._soul_lock:
            self._write_json_atomic(self._soul_rings_path, backup_data)

        logger.info(
            f"Soul rings restored from backup | "
            f"path={backup_path} | rings={len(backup_data)}"
        )
        return True

    # ── 內部工具方法 ──

    def _read_json(self, path: Path) -> List[Dict[str, Any]]:
        """讀取 JSON 陣列檔案（內部使用，不加鎖）.

        Args:
            path: JSON 檔案路徑

        Returns:
            解析後的列表（檔案不存在或解析失敗時回傳空列表）
        """
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            logger.warning(
                f"Expected JSON array, got {type(data).__name__}: {path}"
            )
            return []
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to read JSON: {path} | {e}")
            return []

    def _write_json_atomic(
        self, path: Path, data: List[Dict[str, Any]]
    ) -> None:
        """原子性寫入 JSON 檔案（先寫暫存檔再 rename + fsync）.

        Args:
            path: 目標檔案路徑
            data: 要寫入的資料
        """
        tmp_path = path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())

            # 原子性 rename（同一檔案系統內為原子操作）
            tmp_path.replace(path)

            # fsync 父目錄確保 rename 落盤
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

        except OSError as e:
            logger.error(f"Atomic write failed: {path} | {e}")
            # 清理暫存檔
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    # ── v2.0 新增方法 ──

    def search_by_date_range(
        self, start: date, end: date
    ) -> List[Dict[str, Any]]:
        """按日期範圍檢索日記條目.

        Args:
            start: 起始日期（含）
            end: 結束日期（含）

        Returns:
            在日期範圍內的年輪字典列表
        """
        rings = self.load_soul_rings(verify=False)
        start_str = start.isoformat()
        end_str = (end + timedelta(days=1)).isoformat()  # 含結束日

        results = []
        for r in rings:
            created = r.get("created_at", "")
            if start_str <= created < end_str:
                results.append(r)

        logger.debug(
            f"DiaryStore search_by_date_range | "
            f"{start} ~ {end} | found={len(results)}"
        )
        return results

    def get_recent_entries(
        self, days: int = 3, entry_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """取得最近 N 天的日記條目.

        Args:
            days: 天數（預設 3 天）
            entry_type: 篩選條目類型（None=全部）

        Returns:
            日記條目列表
        """
        start = date.today() - timedelta(days=days)
        end = date.today()
        entries = self.search_by_date_range(start, end)

        if entry_type:
            entries = [
                e for e in entries
                if e.get("entry_type", "event") == entry_type
            ]

        return entries

    def generate_daily_summary(
        self,
        target_date: date,
        interaction_count: int = 0,
        q_scores: Optional[List[float]] = None,
        primals: Optional[Dict[str, int]] = None,
        highlights: Optional[List[str]] = None,
        learnings: Optional[List[str]] = None,
        narrative: str = "",
    ) -> Optional[SoulRing]:
        """生成並寫入每日摘要條目.

        由 Nightly Pipeline 呼叫，聚合當日互動產生 daily_summary 型條目。

        Args:
            target_date: 目標日期
            interaction_count: 當日互動次數
            q_scores: 當日 Q-Score 列表
            primals: 使用者八原語快照
            highlights: 當日亮點
            learnings: 學習要點
            narrative: 敘事摘要文字

        Returns:
            寫入的 SoulRing 實例，或 None（若已存在該日摘要）
        """
        # 檢查是否已有該日的 daily_summary
        existing = self.search_by_date_range(target_date, target_date)
        for entry in existing:
            if entry.get("entry_type") == "daily_summary":
                logger.info(
                    f"Daily summary already exists for {target_date}"
                )
                return None

        # 組裝描述
        avg_q = (
            round(sum(q_scores) / len(q_scores), 3)
            if q_scores else None
        )
        description = narrative or (
            f"{target_date} 日記："
            f"共 {interaction_count} 次互動"
            + (f"，平均 Q-Score {avg_q}" if avg_q else "")
        )

        # 取得前一條年輪的 hash
        all_rings = self.load_soul_rings(verify=False)
        prev_hash = (
            all_rings[-1]["hash"] if all_rings else GENESIS_HASH
        )

        ring = SoulRing(
            type="service_milestone",
            entry_type="daily_summary",
            description=description,
            context=f"date={target_date}, interactions={interaction_count}",
            impact="每日成長記錄",
            created_at=datetime.now().isoformat(),
            prev_hash=prev_hash,
            highlights=highlights,
            learnings=learnings,
            tomorrow_intent=None,
            metrics={
                "interaction_count": interaction_count,
                "avg_q_score": avg_q,
                "primals_snapshot": primals,
            },
        )
        ring.hash = ring.compute_hash(prev_hash)

        self.append_soul_ring(ring)
        logger.info(
            f"Daily summary generated | date={target_date} | "
            f"interactions={interaction_count}"
        )
        return ring


# 向後相容別名
SoulRingStore = DiaryStore


# ═══════════════════════════════════════════
# 年輪寫入引擎
# ═══════════════════════════════════════════


class RingDepositor:
    """年輪寫入引擎 — 偵測年輪級事件、建立年輪、管理 hash chain.

    職責：
      1. 偵測年輪級事件（認知突破、服務里程碑、失敗教訓、價值校準）
      2. 防止重複年輪（比對最近 5 條的語義相似度）
      3. 寫入頻率限制（每日即時寫入上限 5 條）
      4. 拒絕修改/刪除（append-only 強制執行）
      5. Nightly Job 批次沉澱
      6. 使用者觀察年輪寫入

    安全護欄：
      - Morphenix 無法修改 L4 soul_rings
      - 所有修改/刪除嘗試記錄到安全日誌
    """

    # Kernel 五大價值觀關鍵詞（用於偵測 value_calibration 事件）
    VALUE_KEYWORDS: List[str] = [
        "真實優先", "演化至上", "代價透明", "長期複利", "結構是照顧人的方式",
        "說假話", "不真實", "停滯", "不透明", "短視", "混亂",
    ]

    def __init__(
        self,
        store: SoulRingStore,
        data_dir: str = "data",
    ) -> None:
        """初始化年輪寫入引擎.

        Args:
            store: 持久化層實例
            data_dir: 資料根目錄
        """
        self._store = store
        self._data_dir = Path(data_dir)

        # Nightly Job 待處理佇列（記憶體中暫存）
        self._pending_queue: List[Dict[str, Any]] = []

        # 安全日誌路徑
        self._security_log_path = (
            self._data_dir / "anima" / "security_audit.jsonl"
        )
        self._security_log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("RingDepositor initialized")

    # ═══════════════════════════════════════════
    # 靈魂年輪寫入
    # ═══════════════════════════════════════════

    def deposit_soul_ring(
        self,
        ring_type: str,
        description: str,
        context: str,
        impact: str,
        *,
        entry_type: str = "event",
        milestone_name: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        failure_description: Optional[str] = None,
        root_cause: Optional[str] = None,
        prevention: Optional[str] = None,
        original_behavior: Optional[str] = None,
        correction: Optional[str] = None,
        calibrated_value: Optional[str] = None,
        force: bool = False,
    ) -> Optional[SoulRing]:
        """存入一條靈魂年輪 / 日記條目.

        流程：
          1. 驗證年輪類型
          2. 重複偵測（比對最近 5 條）
          3. 頻率限制（每日上限 5 條即時寫入）
          4. 計算 hash 並追加

        Args:
            ring_type: 年輪類型
            description: 一句話摘要
            context: 觸發情境
            impact: 影響預測
            entry_type: 條目類型（event / reflection / daily_summary）
            milestone_name: 里程碑名稱（service_milestone 用）
            metrics: 可量化成果（service_milestone 用）
            failure_description: 失敗描述（failure_lesson 用）
            root_cause: 根因分析（failure_lesson 用）
            prevention: 預防措施（failure_lesson 用）
            original_behavior: 原始行為（value_calibration 用）
            correction: 校正內容（value_calibration 用）
            calibrated_value: 受影響的核心價值（value_calibration 用）
            force: 強制寫入（繞過頻率限制，供 Nightly Job 使用）

        Returns:
            寫入的 SoulRing 實例；若被重複偵測或頻率限制攔截則回傳 None
        """
        # 驗證類型
        valid_types = {
            "cognitive_breakthrough",
            "service_milestone",
            "failure_lesson",
            "value_calibration",
        }
        if ring_type not in valid_types:
            logger.error(f"Invalid soul ring type: {ring_type}")
            return None

        # 重複偵測
        duplicate_index = self._check_duplicate_soul_ring(description)
        if duplicate_index is not None:
            # 相似事件已存在，遞增 reinforcement_count
            rings = self._store.load_soul_rings(verify=False)
            old_count = rings[duplicate_index].get(
                "reinforcement_count", 0
            )
            self._store.update_reinforcement_count(
                duplicate_index, old_count + 1
            )
            logger.info(
                f"Duplicate detected | index={duplicate_index} | "
                f"reinforcement_count={old_count + 1}"
            )
            return None

        # 頻率限制（非強制模式下）
        if not force and self._is_daily_limit_reached():
            logger.info(
                "Daily instant write limit reached, "
                "queuing for Nightly Job"
            )
            self._enqueue_pending({
                "ring_type": ring_type,
                "description": description,
                "context": context,
                "impact": impact,
                "milestone_name": milestone_name,
                "metrics": metrics,
                "failure_description": failure_description,
                "root_cause": root_cause,
                "prevention": prevention,
                "original_behavior": original_behavior,
                "correction": correction,
                "calibrated_value": calibrated_value,
            })
            return None

        # 取得前一條年輪的 hash
        existing_rings = self._store.load_soul_rings(verify=False)
        prev_hash = (
            existing_rings[-1]["hash"]
            if existing_rings
            else GENESIS_HASH
        )

        # 建立年輪物件
        ring = SoulRing(
            type=ring_type,
            description=description,
            context=context,
            impact=impact,
            created_at=datetime.now().isoformat(),
            prev_hash=prev_hash,
            reinforcement_count=0,
            entry_type=entry_type,
            milestone_name=milestone_name,
            metrics=metrics,
            failure_description=failure_description,
            root_cause=root_cause,
            prevention=prevention,
            original_behavior=original_behavior,
            correction=correction,
            calibrated_value=calibrated_value,
        )

        # 計算 hash
        ring.hash = ring.compute_hash(prev_hash)

        # 寫入
        self._store.append_soul_ring(ring)

        # 發布 SOUL_RING_DEPOSITED（ActivityLogger 訂閱）
        try:
            from museon.core.event_bus import get_event_bus, SOUL_RING_DEPOSITED
            get_event_bus().publish(SOUL_RING_DEPOSITED, {
                "ring_type": ring_type,
                "description": description[:100],
            })
        except Exception as e:
            logger.debug(f"[SOUL_RING] soul failed (degraded): {e}")

        return ring

    # ═══════════════════════════════════════════
    # 觀察年輪寫入
    # ═══════════════════════════════════════════

    def deposit_observation_ring(
        self,
        ring_type: str,
        description: str,
        context: str,
        impact: str,
        *,
        soul_ring_hash: Optional[str] = None,
        resonance_confidence: Optional[float] = None,
        resonance_direction: Optional[str] = None,
    ) -> Optional[ObservationRing]:
        """存入一條使用者觀察年輪.

        隱私保護：description 應只包含抽象化的觀察結論，
        不得包含具體對話內容。

        Args:
            ring_type: 觀察類型
            description: 抽象化的觀察結論
            context: 觸發情境
            impact: 對使用者理解的影響
            soul_ring_hash: 關聯的 soul_ring hash（用於共振連結）
            resonance_confidence: 共振信心度（0.0 ~ 1.0）
            resonance_direction: 因果推斷方向

        Returns:
            寫入的 ObservationRing 實例；重複則回傳 None
        """
        valid_types = {
            "growth_observation",
            "pattern_shift",
            "preference_evolution",
            "milestone_witnessed",
        }
        if ring_type not in valid_types:
            logger.error(f"Invalid observation ring type: {ring_type}")
            return None

        # 重複偵測
        duplicate_index = self._check_duplicate_observation_ring(
            description
        )
        if duplicate_index is not None:
            rings = self._store.load_observation_rings()
            old_count = rings[duplicate_index].get(
                "reinforcement_count", 0
            )
            self._store.update_observation_reinforcement(
                duplicate_index, old_count + 1
            )
            logger.info(
                f"Observation duplicate detected | "
                f"index={duplicate_index} | "
                f"reinforcement_count={old_count + 1}"
            )
            return None

        # 取得前一條觀察年輪的 hash
        existing = self._store.load_observation_rings()
        prev_hash = (
            existing[-1]["hash"] if existing else GENESIS_HASH
        )

        # 建立共振連結
        resonance_link: Optional[Dict[str, Any]] = None
        if soul_ring_hash:
            resonance_link = {
                "soul_ring_hash": soul_ring_hash,
                "confidence": resonance_confidence or 0.0,
                "direction": resonance_direction or "unknown",
            }

        ring = ObservationRing(
            type=ring_type,
            description=description,
            context=context,
            impact=impact,
            created_at=datetime.now().isoformat(),
            prev_hash=prev_hash,
            reinforcement_count=0,
            resonance_link=resonance_link,
        )
        ring.hash = ring.compute_hash(prev_hash)

        self._store.append_observation_ring(ring)
        return ring

    # ═══════════════════════════════════════════
    # 事件偵測（供 Brain.process() 後呼叫）
    # ═══════════════════════════════════════════

    def detect_ring_event(
        self,
        user_content: str,
        response_content: str,
        q_score: Optional[float] = None,
        q_score_history: Optional[List[float]] = None,
        reasoning_path_changed: bool = False,
        new_task_type_completed: bool = False,
        content_length: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """偵測此次互動是否構成日記級事件（v2.0 降低門檻版）.

        在 Brain.process() 完成回應生成後呼叫。
        v2.0 降低觸發門檻，更多互動可被記錄為反思或事件：
          1. 認知框架變化（推理路徑結構性改變）
          2. 服務品質變化（Q-Score 顯著變動，不只是新高）
          3. 使用者回饋（明確的錯誤指出或正面肯定）
          4. 價值觀校正（核心價值觀關鍵詞）
          5. 深度對話（長訊息互動，超過 500 字元）
          6. 使用者重要決定（決策相關關鍵詞）

        Args:
            user_content: 使用者訊息文字
            response_content: MUSEON 回覆文字
            q_score: 本次互動的 Q-Score
            q_score_history: 歷史 Q-Score 列表
            reasoning_path_changed: deep-think 是否偵測到推理路徑改變
            new_task_type_completed: 是否完成新任務類型
            content_length: 使用者訊息長度（v2.0 新增）

        Returns:
            偵測到的事件字典（含 ring_type, entry_type 與建議的欄位值）；
            無事件則回傳 None
        """
        # 信號 1：認知框架變化
        if reasoning_path_changed:
            return {
                "ring_type": "cognitive_breakthrough",
                "entry_type": "event",
                "description": "偵測到推理路徑的結構性改變",
                "context": user_content[:200],
                "impact": "可能改變後續對相關領域的推理方式",
            }

        # 信號 2：服務品質變化（v2.0 擴展：不只新高，也偵測顯著提升/下降）
        if q_score is not None and q_score_history and len(q_score_history) >= 3:
            historical_max = max(q_score_history)
            historical_avg = sum(q_score_history[-10:]) / len(q_score_history[-10:])

            # Q-Score 新高
            if q_score > historical_max:
                return {
                    "ring_type": "service_milestone",
                    "entry_type": "event",
                    "description": (
                        f"Q-Score 達到新高 {q_score:.2f}"
                        f"（前高 {historical_max:.2f}）"
                    ),
                    "context": user_content[:200],
                    "impact": "服務品質基準線提升",
                    "milestone_name": f"Q-Score 新高 {q_score:.2f}",
                    "metrics": {
                        "q_score": q_score,
                        "previous_max": historical_max,
                    },
                }

            # v2.0 新增：Q-Score 顯著偏離均值（反思級事件）
            if abs(q_score - historical_avg) > 0.2:
                direction = "高於" if q_score > historical_avg else "低於"
                return {
                    "ring_type": "cognitive_breakthrough" if q_score > historical_avg else "failure_lesson",
                    "entry_type": "reflection",
                    "description": (
                        f"Q-Score {q_score:.2f} 顯著{direction}"
                        f"近期均值 {historical_avg:.2f}"
                    ),
                    "context": user_content[:200],
                    "impact": f"需要關注品質{'提升' if q_score > historical_avg else '下降'}原因",
                    "metrics": {
                        "q_score": q_score,
                        "historical_avg": round(historical_avg, 3),
                    },
                }

        if new_task_type_completed:
            return {
                "ring_type": "service_milestone",
                "entry_type": "event",
                "description": "首次完成新類型的任務",
                "context": user_content[:200],
                "impact": "能力覆蓋範圍擴展",
                "milestone_name": "新任務類型完成",
                "metrics": {},
            }

        # 信號 3：明確的失敗
        if q_score is not None and q_score < 0.4:
            return {
                "ring_type": "failure_lesson",
                "entry_type": "event",
                "description": f"Q-Score 低於閾值（{q_score:.2f}）",
                "context": user_content[:200],
                "impact": "需要根因分析並制定預防措施",
                "failure_description": (
                    f"互動品質分數 {q_score:.2f} 低於可接受閾值 0.4"
                ),
                "root_cause": "待分析",
                "prevention": "待制定",
            }

        # 偵測使用者明確指出錯誤的模式
        error_indicators = [
            "錯了", "不對", "搞錯", "誤解", "你弄錯", "這不是",
            "你搞錯", "不正確", "有問題", "你誤會",
        ]
        if any(kw in user_content for kw in error_indicators):
            return {
                "ring_type": "failure_lesson",
                "entry_type": "event",
                "description": "使用者明確指出回覆有誤",
                "context": user_content[:200],
                "impact": "需要修正認知並防止再犯",
                "failure_description": "使用者指出回覆錯誤",
                "root_cause": "待分析",
                "prevention": "待制定",
            }

        # 信號 4：價值觀校正
        if any(kw in user_content for kw in self.VALUE_KEYWORDS):
            return {
                "ring_type": "value_calibration",
                "entry_type": "event",
                "description": "使用者使用核心價值觀相關詞彙進行校正",
                "context": user_content[:200],
                "impact": "強化 L1 Kernel 的價值觀理解",
                "original_behavior": response_content[:200],
                "correction": user_content[:200],
                "calibrated_value": self._extract_value_keyword(
                    user_content
                ),
            }

        # v2.0 新增信號 5：使用者正面肯定（反思記錄）
        positive_indicators = [
            "很好", "太棒了", "非常好", "很有幫助", "感謝",
            "謝謝", "很讚", "超棒", "很厲害", "學到了",
        ]
        if any(kw in user_content for kw in positive_indicators):
            return {
                "ring_type": "service_milestone",
                "entry_type": "reflection",
                "description": "使用者給予正面肯定",
                "context": user_content[:200],
                "impact": "確認此類互動模式的有效性",
            }

        # v2.0 新增信號 6：使用者重要決定
        decision_indicators = [
            "我決定", "我要", "我打算", "我選擇", "確定要",
            "就這樣做", "就這麼辦", "決定了", "拍板",
        ]
        if any(kw in user_content for kw in decision_indicators):
            return {
                "ring_type": "cognitive_breakthrough",
                "entry_type": "reflection",
                "description": "使用者做出重要決定",
                "context": user_content[:200],
                "impact": "記錄使用者決策脈絡，供後續追蹤",
            }

        # v2.0 新增信號 7：深度對話（長訊息互動）
        effective_length = content_length or len(user_content)
        if effective_length > 500:
            return {
                "ring_type": "cognitive_breakthrough",
                "entry_type": "reflection",
                "description": f"深度對話互動（{effective_length} 字元）",
                "context": user_content[:200],
                "impact": "記錄有深度的互動脈絡",
            }

        return None

    # ═══════════════════════════════════════════
    # Nightly Job 批次沉澱
    # ═══════════════════════════════════════════

    def nightly_batch_deposit(
        self, candidates: Optional[List[Dict[str, Any]]] = None
    ) -> List[SoulRing]:
        """Nightly Job 批次沉澱 — 回顧當天的互動並篩選值得刻入的事件.

        每日最多新增 3 條年輪（品質優先於數量）。
        合併自動排入佇列的候選以及外部傳入的候選。

        Args:
            candidates: 外部傳入的年輪候選列表（可選）

        Returns:
            實際寫入的年輪列表
        """
        # 合併佇列中的候選與外部候選
        all_candidates = list(self._pending_queue)
        if candidates:
            all_candidates.extend(candidates)

        # 清空佇列
        self._pending_queue.clear()

        if not all_candidates:
            logger.info("Nightly batch: no candidates to deposit")
            return []

        # 按重要性排序（簡易排序：failure > value_calibration >
        # cognitive_breakthrough > service_milestone）
        type_priority = {
            "failure_lesson": 0,
            "value_calibration": 1,
            "cognitive_breakthrough": 2,
            "service_milestone": 3,
        }
        all_candidates.sort(
            key=lambda c: type_priority.get(c.get("ring_type", ""), 99)
        )

        # 最多寫入 NIGHTLY_BATCH_LIMIT 條
        deposited: List[SoulRing] = []
        for candidate in all_candidates[:NIGHTLY_BATCH_LIMIT]:
            ring = self.deposit_soul_ring(
                ring_type=candidate.get("ring_type", ""),
                description=candidate.get("description", ""),
                context=candidate.get("context", ""),
                impact=candidate.get("impact", ""),
                milestone_name=candidate.get("milestone_name"),
                metrics=candidate.get("metrics"),
                failure_description=candidate.get("failure_description"),
                root_cause=candidate.get("root_cause"),
                prevention=candidate.get("prevention"),
                original_behavior=candidate.get("original_behavior"),
                correction=candidate.get("correction"),
                calibrated_value=candidate.get("calibrated_value"),
                force=True,  # Nightly Job 繞過頻率限制
            )
            if ring:
                deposited.append(ring)

        logger.info(
            f"Nightly batch deposit completed | "
            f"candidates={len(all_candidates)} | "
            f"deposited={len(deposited)}"
        )
        return deposited

    def get_pending_queue(self) -> List[Dict[str, Any]]:
        """取得目前待處理佇列的內容（供 Nightly Job 查看）.

        Returns:
            待處理的候選年輪列表
        """
        return list(self._pending_queue)

    # ═══════════════════════════════════════════
    # 備份與維護（Nightly Job 呼叫）
    # ═══════════════════════════════════════════

    def run_daily_maintenance(self) -> Dict[str, Any]:
        """執行每日維護任務（供 Nightly Job 呼叫）.

        包含：
          1. 建立備份
          2. 清理過期備份
          3. 完整性驗證

        Returns:
            維護報告字典
        """
        report: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "tasks": {},
        }

        # 1. 備份
        try:
            soul_backup = self._store.create_backup()
            obs_backup = self._store.create_observation_backup()
            report["tasks"]["backup"] = {
                "status": "completed",
                "soul_rings": str(soul_backup),
                "observation_rings": str(obs_backup),
            }
        except Exception as e:
            logger.error(f"Daily backup failed: {e}")
            report["tasks"]["backup"] = {
                "status": "failed",
                "error": str(e),
            }

        # 2. 清理過期備份
        try:
            removed = self._store.rotate_backups()
            report["tasks"]["rotation"] = {
                "status": "completed",
                "removed_count": removed,
            }
        except Exception as e:
            logger.error(f"Backup rotation failed: {e}")
            report["tasks"]["rotation"] = {
                "status": "failed",
                "error": str(e),
            }

        # 3. 完整性驗證
        soul_valid, soul_msg = (
            self._store.verify_soul_ring_integrity()
        )
        obs_valid, obs_msg = (
            self._store.verify_observation_ring_integrity()
        )
        report["tasks"]["integrity"] = {
            "soul_rings": {"valid": soul_valid, "message": soul_msg},
            "observation_rings": {
                "valid": obs_valid,
                "message": obs_msg,
            },
        }

        return report

    # ═══════════════════════════════════════════
    # Append-Only 強制 + 安全護欄
    # ═══════════════════════════════════════════

    def reject_modify(
        self, index: int, caller: str = "unknown"
    ) -> Dict[str, Any]:
        """拒絕修改已寫入的年輪（append-only 強制）.

        所有修改嘗試都被記錄到安全日誌。

        Args:
            index: 嘗試修改的年輪索引
            caller: 呼叫者識別（例如 "morphenix"）

        Returns:
            拒絕結果字典
        """
        error_msg = "靈魂年輪為 append-only，不可修改已寫入的記錄"
        self._log_security_event(
            event_type="modify_attempt",
            caller=caller,
            target_index=index,
            message=error_msg,
        )
        logger.warning(
            f"Modify attempt rejected | caller={caller} | "
            f"index={index}"
        )
        return {"allowed": False, "error": error_msg}

    def reject_delete(
        self, index: int, caller: str = "unknown"
    ) -> Dict[str, Any]:
        """拒絕刪除年輪（append-only 強制）.

        所有刪除嘗試都被記錄到安全日誌。

        Args:
            index: 嘗試刪除的年輪索引
            caller: 呼叫者識別

        Returns:
            拒絕結果字典
        """
        error_msg = "靈魂年輪不可刪除，這是永久的成長記錄"
        self._log_security_event(
            event_type="delete_attempt",
            caller=caller,
            target_index=index,
            message=error_msg,
        )
        logger.warning(
            f"Delete attempt rejected | caller={caller} | "
            f"index={index}"
        )
        return {"allowed": False, "error": error_msg}

    def reject_morphenix_modify(self, caller: str = "morphenix") -> Dict[str, Any]:
        """拒絕 Morphenix 對 L4 靈魂年輪的修改嘗試.

        L4 靈魂年輪處於 Kernel 保護之下，不可被演化引擎修改。

        Args:
            caller: 呼叫者識別

        Returns:
            拒絕結果字典
        """
        error_msg = (
            "L4 靈魂年輪處於 Kernel 保護之下，"
            "不可被演化引擎修改"
        )
        self._log_security_event(
            event_type="morphenix_modify_attempt",
            caller=caller,
            target_index=-1,
            message=error_msg,
        )
        logger.warning(
            f"Morphenix modify attempt rejected | caller={caller}"
        )
        return {"allowed": False, "error": error_msg}

    # ═══════════════════════════════════════════
    # 共振連結
    # ═══════════════════════════════════════════

    def create_resonance_link(
        self,
        soul_ring_hash: str,
        observation_ring_hash: str,
        direction: str,
        confidence: float,
    ) -> Dict[str, Any]:
        """建立 MUSEON soul_ring 與 ANIMA_USER observation_ring 之間的共振連結.

        Args:
            soul_ring_hash: MUSEON 靈魂年輪的 hash
            observation_ring_hash: 使用者觀察年輪的 hash
            direction: 因果推斷方向（例如 "mc_growth -> user_satisfaction"）
            confidence: 信心度（0.0 ~ 1.0）

        Returns:
            共振連結字典
        """
        link = {
            "soul_ring_hash": soul_ring_hash,
            "observation_ring_hash": observation_ring_hash,
            "direction": direction,
            "confidence": confidence,
            "created_at": datetime.now().isoformat(),
        }
        logger.info(
            f"Resonance link created | "
            f"soul={soul_ring_hash[:12]}... <-> "
            f"obs={observation_ring_hash[:12]}... | "
            f"confidence={confidence:.2f}"
        )
        return link

    # ═══════════════════════════════════════════
    # 內部工具方法
    # ═══════════════════════════════════════════

    def _check_duplicate_soul_ring(
        self, description: str
    ) -> Optional[int]:
        """比對最近 N 條靈魂年輪，偵測重複.

        使用 SequenceMatcher 進行文字相似度比對。
        若相似度 > DEDUP_SIMILARITY_THRESHOLD 則視為重複。

        Args:
            description: 新年輪的描述

        Returns:
            重複年輪的索引；無重複則回傳 None
        """
        rings = self._store.load_soul_rings(verify=False)
        if not rings:
            return None

        # 只比對最近 DEDUP_WINDOW 條
        recent = rings[-DEDUP_WINDOW:]
        start_index = max(0, len(rings) - DEDUP_WINDOW)

        for i, ring in enumerate(recent):
            existing_desc = ring.get("description", "")
            similarity = SequenceMatcher(
                None, description, existing_desc
            ).ratio()
            if similarity > DEDUP_SIMILARITY_THRESHOLD:
                return start_index + i

        return None

    def _check_duplicate_observation_ring(
        self, description: str
    ) -> Optional[int]:
        """比對最近 N 條觀察年輪，偵測重複.

        Args:
            description: 新觀察年輪的描述

        Returns:
            重複年輪的索引；無重複則回傳 None
        """
        rings = self._store.load_observation_rings()
        if not rings:
            return None

        recent = rings[-DEDUP_WINDOW:]
        start_index = max(0, len(rings) - DEDUP_WINDOW)

        for i, ring in enumerate(recent):
            existing_desc = ring.get("description", "")
            similarity = SequenceMatcher(
                None, description, existing_desc
            ).ratio()
            if similarity > DEDUP_SIMILARITY_THRESHOLD:
                return start_index + i

        return None

    def _is_daily_limit_reached(self) -> bool:
        """檢查今日即時寫入是否已達上限.

        Returns:
            True 表示已達上限
        """
        rings = self._store.load_soul_rings(verify=False)
        if not rings:
            return False

        today_str = date.today().isoformat()
        today_count = sum(
            1
            for r in rings
            if r.get("created_at", "").startswith(today_str)
        )
        return today_count >= DAILY_INSTANT_WRITE_LIMIT

    def _enqueue_pending(self, candidate: Dict[str, Any]) -> None:
        """將候選年輪排入 Nightly Job 待處理佇列.

        Args:
            candidate: 候選年輪資料
        """
        candidate["queued_at"] = datetime.now().isoformat()
        self._pending_queue.append(candidate)
        logger.info(
            f"Candidate queued for nightly | "
            f"type={candidate.get('ring_type')} | "
            f"queue_size={len(self._pending_queue)}"
        )

    def _extract_value_keyword(self, text: str) -> str:
        """從文字中提取匹配的核心價值觀關鍵詞.

        Args:
            text: 使用者訊息文字

        Returns:
            匹配到的第一個關鍵詞，或 "unknown"
        """
        for kw in self.VALUE_KEYWORDS:
            if kw in text:
                return kw
        return "unknown"

    def _log_security_event(
        self,
        event_type: str,
        caller: str,
        target_index: int,
        message: str,
    ) -> None:
        """記錄安全事件到安全日誌（append-only JSONL）.

        Args:
            event_type: 事件類型
            caller: 呼叫者識別
            target_index: 目標年輪索引
            message: 事件描述
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "caller": caller,
            "target_index": target_index,
            "message": message,
        }
        try:
            with open(
                self._security_log_path, "a", encoding="utf-8"
            ) as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            logger.error(f"Failed to write security log: {e}")
