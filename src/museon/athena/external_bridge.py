"""External-to-Ares Bridge — 群組成員自動建檔橋接器.

將 ExternalAnimaManager 管理的 Telegram 群組成員資料，
同步到 Ares ProfileStore 的 ANIMA 個體檔案。

設計原則：
- ExternalAnimaManager 繼續管自動觀察（Telegram 互動觸發）
- ProfileStore 管策略分析用的完整畫像
- Bridge 負責單向同步：External → Ares（不反向）
- 已同步的人物用 profile_id 做 mapping

映射檔：data/ares/profiles/_external_map.json
格式：{"telegram_uid": "ares_profile_id", ...}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ExternalBridge:
    """群組成員 → Ares 個體檔案的同步橋接."""

    def __init__(self, profile_store: Any, external_anima_dir: Path | str):
        """
        Args:
            profile_store: ares.profile_store.ProfileStore 實例
            external_anima_dir: ExternalAnimaManager 的 users_dir
                                (data/_system/external_users/)
        """
        self.store = profile_store
        self.ext_dir = Path(external_anima_dir)
        self._map_path = Path(profile_store.profiles_dir) / "_external_map.json"
        self._ensure_map()

    def _ensure_map(self) -> None:
        if not self._map_path.exists():
            self._save_map({})

    def _load_map(self) -> dict[str, str]:
        try:
            return json.loads(self._map_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_map(self, mapping: dict[str, str]) -> None:
        tmp = self._map_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.rename(self._map_path)

    def sync_all(self) -> dict[str, Any]:
        """同步所有 external_users 到 Ares ProfileStore.

        Returns:
            {"created": int, "updated": int, "skipped": int, "errors": int}
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}
        mapping = self._load_map()

        if not self.ext_dir.exists():
            logger.warning(f"[ARES-BRIDGE] External users dir not found: {self.ext_dir}")
            return stats

        for ext_path in self.ext_dir.glob("*.json"):
            uid = ext_path.stem
            try:
                ext_data = json.loads(ext_path.read_text(encoding="utf-8"))
                name = (
                    ext_data.get("display_name")
                    or ext_data.get("profile", {}).get("name")
                    or f"User_{uid[:8]}"
                )

                if uid in mapping:
                    # 已有映射 → 更新
                    profile_id = mapping[uid]
                    existing = self.store.load(profile_id)
                    if existing:
                        updates = self._extract_updates(ext_data)
                        if updates:
                            self.store.update(profile_id, updates)
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        # 映射存在但檔案消失，重建
                        profile = self._create_from_external(name, ext_data)
                        mapping[uid] = profile["profile_id"]
                        stats["created"] += 1
                else:
                    # 新成員 → 建檔
                    profile = self._create_from_external(name, ext_data)
                    mapping[uid] = profile["profile_id"]
                    stats["created"] += 1

            except Exception as e:
                logger.warning(f"[ARES-BRIDGE] Error syncing {uid}: {e}")
                stats["errors"] += 1

        self._save_map(mapping)
        # 索引一致性驗證：確保所有 profile 都在 index 中
        index = self.store._load_index()
        profile_files = {f.stem for f in self.store.profiles_dir.glob("*.json") if f.name not in {"_index.json", "_external_map.json"}}
        missing = profile_files - set(index.keys())
        if missing:
            logger.warning(f"[ARES-BRIDGE] {len(missing)} profiles missing from index, rebuilding...")
            self.store.rebuild_index()
        logger.info(
            f"[ARES-BRIDGE] Sync complete: "
            f"created={stats['created']}, updated={stats['updated']}, "
            f"skipped={stats['skipped']}, errors={stats['errors']}"
        )
        return stats

    def sync_one(self, telegram_uid: str) -> dict[str, Any] | None:
        """同步單一 Telegram 使用者到 Ares."""
        mapping = self._load_map()
        ext_path = self.ext_dir / f"{telegram_uid}.json"

        if not ext_path.exists():
            return None

        ext_data = json.loads(ext_path.read_text(encoding="utf-8"))
        name = (
            ext_data.get("display_name")
            or ext_data.get("profile", {}).get("name")
            or f"User_{telegram_uid[:8]}"
        )

        if telegram_uid in mapping:
            profile_id = mapping[telegram_uid]
            updates = self._extract_updates(ext_data)
            if updates:
                return self.store.update(profile_id, updates)
            return self.store.load(profile_id)
        else:
            profile = self._create_from_external(name, ext_data)
            mapping[telegram_uid] = profile["profile_id"]
            self._save_map(mapping)
            return profile

    def get_profile_id(self, telegram_uid: str) -> str | None:
        """查詢 Telegram UID 對應的 Ares profile_id."""
        mapping = self._load_map()
        return mapping.get(telegram_uid)

    def _create_from_external(self, name: str, ext_data: dict) -> dict[str, Any]:
        """從 external_users 資料建立 Ares profile."""
        profile = self.store.create(name, domains=["business"])

        updates: dict[str, Any] = {}

        # L1: 事實
        ext_profile = ext_data.get("profile", {})
        if ext_profile.get("role"):
            updates.setdefault("L1_facts", {})["role"] = ext_profile["role"]
        if ext_profile.get("business_type") and ext_profile["business_type"] != "unknown":
            updates.setdefault("L1_facts", {})["industry"] = ext_profile["business_type"]

        # L2: 人格（從 ExternalAnima 的 seven_layers 遷移）
        layers = ext_data.get("seven_layers", {})
        if layers.get("L2_personality"):
            observations = layers["L2_personality"]
            if isinstance(observations, list) and observations:
                updates["L2_personality"] = {
                    "observations": observations,
                    "assessment_type": "proxy",
                    "confidence": min(30 + len(observations) * 5, 60),
                }

        # L6: 溝通風格
        if layers.get("L6_communication_style"):
            style_data = layers["L6_communication_style"]
            updates["L6_communication"] = {
                "style": style_data.get("tone", "casual"),
            }

        # L4: 互動數據
        rel = ext_data.get("relationship", {})
        if rel.get("total_interactions", 0) > 0:
            updates["L4_interactions"] = {
                "total_count": rel.get("total_interactions", 0),
                "positive_count": rel.get("positive_signals", 0),
                "negative_count": rel.get("negative_signals", 0),
            }

        # 八原語
        if ext_data.get("eight_primals"):
            updates.setdefault("L2_personality", {})["observations"] = updates.get("L2_personality", {}).get("observations", [])
            # 八原語觀察可作為人格評估的輸入
            for primal, data in ext_data["eight_primals"].items():
                if isinstance(data, dict):
                    updates.setdefault("L2_personality", {}).setdefault("observations", []).append(
                        f"八原語 {primal}: {data}"
                    )

        if updates:
            self.store.update(profile["profile_id"], updates)
            profile = self.store.load(profile["profile_id"]) or profile

        return profile

    def _extract_updates(self, ext_data: dict) -> dict[str, Any]:
        """從 external_users 資料提取可更新的欄位."""
        updates: dict[str, Any] = {}

        # 更新互動統計
        rel = ext_data.get("relationship", {})
        if rel.get("total_interactions", 0) > 0:
            updates["L4_interactions"] = {
                "total_count": rel.get("total_interactions", 0),
                "positive_count": rel.get("positive_signals", 0),
                "negative_count": rel.get("negative_signals", 0),
            }

        # 更新名稱（如果之前是 User_xxx）
        name = ext_data.get("display_name") or ext_data.get("profile", {}).get("name")
        if name and not name.startswith("User_"):
            updates.setdefault("L1_facts", {})["name"] = name

        return updates
