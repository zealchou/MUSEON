"""Shared Assets — 跨部門知識共享.

📌 NOTE: 衰退因子 per-type 差異化設計。
    跑幾天後二次確認哪些類型應 decay=1.0（不衰退）。

依據 MULTI_AGENT_BDD_SPEC §5 實作。
"""

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

ASSET_ID_LENGTH = 12         # UUID hex 前綴
ARCHIVE_THRESHOLD = 0.3      # 低品質歸檔門檻
DEFAULT_DECAY = 0.993        # 每日品質衰退因子

# 📌 Per-type 衰退因子（未來二次確認）
DECAY_BY_TYPE: Dict[str, float] = {
    "report":     0.993,   # 報告：~3 個月自然過期
    "analysis":   0.993,   # 分析
    "plan":       0.996,   # 計畫：~5 個月
    "strategy":   0.998,   # 策略：~10 個月
    "vision":     1.000,   # 願景：不衰退
    "brand":      1.000,   # 品牌：不衰退
    "sop":        0.999,   # SOP：~2 年
    "knowledge":  0.997,   # 知識：~7 個月
}


# ═══════════════════════════════════════════
# SharedAsset
# ═══════════════════════════════════════════

@dataclass
class SharedAsset:
    """共享資產."""

    asset_id: str
    title: str
    content: str
    asset_type: str
    source_dept: str
    gate_level: int
    version: int = 1
    quality_score: float = 0.5
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    archived: bool = False
    archive_reason: str = ""


# ═══════════════════════════════════════════
# SharedAssetLibrary
# ═══════════════════════════════════════════

class SharedAssetLibrary:
    """共享資產庫."""

    def __init__(self, workspace: Path) -> None:
        self._dir = Path(workspace) / "_system" / "shared_assets"
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── CRUD ──

    def publish(
        self,
        title: str,
        content: str,
        asset_type: str,
        source_dept: str,
        gate_level: int = 0,
        quality_score: float = 0.5,
        tags: Optional[List[str]] = None,
    ) -> SharedAsset:
        """發布資產.

        Gate 驗證由呼叫端（MCP tool / API）負責。
        """
        now = datetime.now(TZ_TAIPEI).isoformat()
        asset = SharedAsset(
            asset_id=uuid.uuid4().hex[:ASSET_ID_LENGTH],
            title=title,
            content=content,
            asset_type=asset_type,
            source_dept=source_dept,
            gate_level=gate_level,
            quality_score=quality_score,
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        self._save(asset)
        return asset

    def get(self, asset_id: str) -> Optional[SharedAsset]:
        """取得資產（支援 8 字元前綴）."""
        # 精確匹配
        path = self._dir / f"{asset_id}.json"
        if path.exists():
            return self._load(path)

        # 前綴匹配
        for f in self._dir.glob("*.json"):
            if f.stem.startswith(asset_id):
                return self._load(f)

        return None

    def search(
        self,
        query: str,
        dept_filter: Optional[str] = None,
        asset_type: Optional[str] = None,
    ) -> List[SharedAsset]:
        """搜尋資產（標題 + tags 匹配）."""
        results = []
        for f in self._dir.glob("*.json"):
            asset = self._load(f)
            if asset is None or asset.archived:
                continue

            # 過濾
            if dept_filter and asset.source_dept != dept_filter:
                continue
            if asset_type and asset.asset_type != asset_type:
                continue

            # 搜尋匹配
            if (query in asset.title
                    or any(query in tag for tag in asset.tags)
                    or query in asset.content):
                results.append(asset)

        return results

    def list_all(self, include_archived: bool = False) -> List[SharedAsset]:
        """列出所有資產."""
        results = []
        for f in self._dir.glob("*.json"):
            asset = self._load(f)
            if asset is None:
                continue
            if not include_archived and asset.archived:
                continue
            results.append(asset)
        return results

    # ── 衰退與歸檔 ──

    def decay_all(self) -> int:
        """每日品質衰退.

        依 asset_type 使用不同衰退因子。
        Returns: 受影響資產數。
        """
        affected = 0
        for f in self._dir.glob("*.json"):
            asset = self._load(f)
            if asset is None or asset.archived:
                continue

            factor = DECAY_BY_TYPE.get(asset.asset_type, DEFAULT_DECAY)
            if factor >= 1.0:
                continue  # 不衰退

            old_score = asset.quality_score
            asset.quality_score = round(old_score * factor, 6)
            asset.updated_at = datetime.now(TZ_TAIPEI).isoformat()
            self._save(asset)
            affected += 1

        return affected

    def archive_low_quality(
        self, threshold: float = ARCHIVE_THRESHOLD
    ) -> int:
        """歸檔低品質資產.

        Returns: 歸檔數。
        """
        archived_count = 0
        for f in self._dir.glob("*.json"):
            asset = self._load(f)
            if asset is None or asset.archived:
                continue

            if asset.quality_score < threshold:
                asset.archived = True
                asset.archive_reason = (
                    f"quality_score {asset.quality_score:.4f} "
                    f"< threshold {threshold}"
                )
                asset.updated_at = datetime.now(TZ_TAIPEI).isoformat()
                self._save(asset)
                archived_count += 1

        return archived_count

    # ── Internal ──

    def _save(self, asset: SharedAsset) -> None:
        path = self._dir / f"{asset.asset_id}.json"
        path.write_text(
            json.dumps(asdict(asset), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self, path: Path) -> Optional[SharedAsset]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SharedAsset(**data)
        except Exception:
            logger.warning(f"Failed to load asset: {path}")
            return None
