"""ANIMA Individual Profile Store — 個體檔案持久化引擎.

管理第三方人物的 ANIMA 七層鏡像檔案。
與 ExternalAnimaManager 互補：
- ExternalAnimaManager：追蹤 Telegram 互動者（自動建檔）
- ProfileStore：追蹤使用者主動建檔的人物（手動建檔）

儲存路徑：data/ares/profiles/{profile_id}.json
索引路徑：data/ares/profiles/_index.json
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 八大槓桿維度
LEVERAGE_DIMENSIONS = [
    "channels",    # 通路
    "technology",  # 技術
    "capital",     # 資金
    "network",     # 人脈
    "brand",       # 品牌
    "systems",     # 系統
    "content",     # 內容
    "time",        # 時間
]

# 場域標籤
VALID_DOMAINS = {"internal", "business", "personal"}


def _default_profile(profile_id: str, name: str) -> dict[str, Any]:
    """建立預設七層鏡像結構."""
    now = datetime.now().isoformat()
    return {
        "version": "1.0.0",
        "profile_id": profile_id,
        "created_at": now,
        "updated_at": now,
        "domains": [],  # ["internal", "business", "personal"]

        # L1: 事實層
        "L1_facts": {
            "name": name,
            "title": None,
            "company": None,
            "role": None,
            "industry": None,
            "notes": [],
        },

        # L2: 人格層
        "L2_personality": {
            "wan_miu_code": None,       # e.g. "PSRU"
            "wan_miu_name": None,       # e.g. "堅定實務者"
            "four_axes": {              # 四軸得分
                "mission": None,        # 天↔地 (A/P)
                "relation": None,       # 火↔水 (O/S)
                "drive": None,          # 山↔澤 (E/R)
                "emotion": None,        # 風↔雷 (M/U)
            },
            "confidence": 0,            # 0-100 置信度
            "assessment_type": None,    # "proxy" | "direct" | "onemuse"
            "observations": [],         # 用於代理評估的觀察記錄
        },

        # L3: 能量層（需要 OneMuse 盤數據）
        "L3_energy": {
            "has_reading": False,
            "inner": {},    # {"天": 3, "風": -2, ...}
            "outer": {},    # {"天": 1, "風": 4, ...}
            "reading_date": None,
        },

        # L4: 互動環
        "L4_interactions": {
            "total_count": 0,
            "positive_count": 0,
            "negative_count": 0,
            "neutral_count": 0,
            "last_interaction": None,
            "combined_reading": None,   # 合盤結果摘要
            "history": [],              # [{date, type, summary, outcome}]
        },

        # L5: 槓桿層
        "L5_leverage": {
            dim: {"has": None, "needs": None, "details": None}
            for dim in LEVERAGE_DIMENSIONS
        },

        # L6: 溝通層
        "L6_communication": {
            "style": None,          # "direct" | "indirect" | "analytical" | "emotional"
            "taboos": [],           # 禁忌事項
            "preferences": [],      # 偏好事項
            "landmines": [],        # 地雷
            "effective_approaches": [],  # 有效的溝通方式
        },

        # L7: 情境面具
        "L7_context_masks": {},    # {場域: {行為差異描述}}

        # 關係溫度
        "temperature": {
            "level": "new",         # "hot" | "warm" | "cold" | "new"
            "trend": "stable",      # "rising" | "stable" | "falling"
            "last_updated": now,
        },

        # 圖連線（People Topology）
        "connections": [],  # [{target_id, relation_type, strength, notes}]
    }


class ProfileStore:
    """ANIMA 個體檔案 CRUD 引擎."""

    def __init__(self, data_dir: Path | str):
        data_dir = Path(data_dir) if not isinstance(data_dir, Path) else data_dir
        self.profiles_dir = data_dir / "ares" / "profiles"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.profiles_dir / "_index.json"
        self._lock = threading.Lock()
        self._ensure_index()

    def _ensure_index(self) -> None:
        if not self._index_path.exists():
            self._save_index({})
        # 防護：index 存在但為空，且有 profile 檔案時自動重建
        try:
            index = self._load_index()
            if not index:
                profile_count = sum(1 for f in self.profiles_dir.glob("*.json") if f.name not in {"_index.json", "_external_map.json"})
                if profile_count > 0:
                    logger.warning(f"[ARES] Empty index with {profile_count} profiles, rebuilding...")
                    self.rebuild_index()
        except Exception:
            pass

    def _load_index(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_index(self, index: dict[str, dict[str, Any]]) -> None:
        tmp = self._index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.rename(self._index_path)

    def _profile_path(self, profile_id: str) -> Path:
        return self.profiles_dir / f"{profile_id}.json"

    # --- CRUD ---

    def create(self, name: str, domains: list[str] | None = None) -> dict[str, Any]:
        """建立新的個體檔案."""
        profile_id = uuid.uuid4().hex[:12]
        profile = _default_profile(profile_id, name)
        if domains:
            profile["domains"] = [d for d in domains if d in VALID_DOMAINS]

        with self._lock:
            self._save_profile(profile)
            index = self._load_index()
            index[profile_id] = {
                "name": name,
                "domains": profile["domains"],
                "wan_miu_code": None,
                "temperature": "new",
                "updated_at": profile["updated_at"],
            }
            self._save_index(index)

        logger.info(f"[ARES] Created profile: {name} ({profile_id})")
        return profile

    def load(self, profile_id: str) -> dict[str, Any] | None:
        """載入個體檔案."""
        path = self._profile_path(profile_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[ARES] Failed to load profile {profile_id}: {e}")
            return None

    def update(self, profile_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        """更新個體檔案的指定欄位."""
        with self._lock:
            profile = self.load(profile_id)
            if not profile:
                return None
            _deep_merge(profile, updates)
            # Phase 4: 自動升級置信度（觀察次數越多越準）
            self._recalc_confidence(profile)
            profile["updated_at"] = datetime.now().isoformat()
            self._save_profile(profile)
            self._update_index_entry(profile)
        return profile

    def delete(self, profile_id: str) -> bool:
        """刪除個體檔案."""
        with self._lock:
            path = self._profile_path(profile_id)
            if path.exists():
                path.unlink()
            index = self._load_index()
            index.pop(profile_id, None)
            self._save_index(index)
        logger.info(f"[ARES] Deleted profile: {profile_id}")
        return True

    def list_all(self) -> dict[str, dict[str, Any]]:
        """列出所有個體的索引摘要."""
        return self._load_index()

    def rebuild_index(self) -> int:
        """從現有 profile 檔案重建 _index.json（用於修復空索引）."""
        skip = {"_index.json", "_external_map.json"}
        index: dict[str, dict[str, Any]] = {}
        for f in self.profiles_dir.glob("*.json"):
            if f.name in skip:
                continue
            try:
                p = json.loads(f.read_text(encoding="utf-8"))
                pid = p.get("profile_id", f.stem)
                index[pid] = {
                    "name": p.get("L1_facts", {}).get("name", "Unknown"),
                    "domains": p.get("domains", []),
                    "wan_miu_code": p.get("L2_personality", {}).get("wan_miu_code"),
                    "temperature": p.get("temperature", {}).get("level", "new"),
                    "updated_at": p.get("updated_at", ""),
                }
            except Exception as e:
                logger.warning(f"[ARES] Failed to read profile {f.name}: {e}")
        with self._lock:
            self._save_index(index)
        logger.info(f"[ARES] Index rebuilt: {len(index)} profiles")
        return len(index)

    def search(self, keyword: str, domain: str | None = None) -> list[dict[str, Any]]:
        """搜尋個體：比對名稱、公司、角色."""
        keyword_lower = keyword.lower()
        results = []
        index = self._load_index()
        for pid, entry in index.items():
            if domain and domain not in entry.get("domains", []):
                continue
            name = (entry.get("name") or "").lower()
            # 去括號比對：「吳明憲(Alan Wu)」→ 也用「吳明憲」和「alan wu」分別比對
            import re as _re
            _name_base = _re.sub(r'\([^)]*\)', '', name).strip()
            _name_paren = _re.search(r'\(([^)]*)\)', name)
            _name_paren_inner = _name_paren.group(1).strip() if _name_paren else ""
            if (keyword_lower in name or (name and name in keyword_lower)
                    or (_name_base and _name_base in keyword_lower)
                    or (_name_paren_inner and _name_paren_inner in keyword_lower)):
                profile = self.load(pid)
                if profile:
                    results.append(profile)
                continue
            # 深度搜尋：載入完整檔案比對公司/角色
            profile = self.load(pid)
            if profile:
                facts = profile.get("L1_facts", {})
                company = (facts.get("company") or "").lower()
                role = (facts.get("role") or "").lower()
                if keyword_lower in company or keyword_lower in role or (company and company in keyword_lower) or (role and role in keyword_lower):
                    results.append(profile)
        return results

    # --- 互動記錄 ---

    def add_interaction(
        self,
        profile_id: str,
        interaction_type: str,
        summary: str,
        outcome: str = "neutral",
    ) -> dict[str, Any] | None:
        """追加互動記錄並更新溫度."""
        with self._lock:
            profile = self.load(profile_id)
            if not profile:
                return None

            now = datetime.now().isoformat()
            record = {
                "date": now,
                "type": interaction_type,
                "summary": summary,
                "outcome": outcome,  # "positive" | "negative" | "neutral"
            }
            profile["L4_interactions"]["history"].append(record)
            profile["L4_interactions"]["total_count"] += 1
            profile["L4_interactions"]["last_interaction"] = now
            if outcome == "positive":
                profile["L4_interactions"]["positive_count"] += 1
            elif outcome == "negative":
                profile["L4_interactions"]["negative_count"] += 1
            else:
                profile["L4_interactions"]["neutral_count"] += 1

            # 更新溫度 + 置信度
            self._recalc_temperature(profile)
            self._recalc_confidence(profile)
            profile["updated_at"] = now
            self._save_profile(profile)
            self._update_index_entry(profile)

        return profile

    # --- 槓桿更新 ---

    def update_leverage(
        self, profile_id: str, dimension: str, has: str | None = None, needs: str | None = None, details: str | None = None,
    ) -> dict[str, Any] | None:
        """更新特定槓桿維度."""
        if dimension not in LEVERAGE_DIMENSIONS:
            logger.warning(f"[ARES] Invalid leverage dimension: {dimension}")
            return None
        updates: dict[str, Any] = {}
        if has is not None:
            updates[f"L5_leverage.{dimension}.has"] = has
        if needs is not None:
            updates[f"L5_leverage.{dimension}.needs"] = needs
        if details is not None:
            updates[f"L5_leverage.{dimension}.details"] = details
        # Flatten for deep merge
        return self.update(profile_id, _unflatten(updates))

    # --- 連線管理（People Topology） ---

    def add_connection(
        self,
        from_id: str,
        to_id: str,
        relation_type: str,
        strength: int = 5,
        notes: str = "",
        bidirectional: bool = True,
    ) -> bool:
        """在兩個個體間建立連線."""
        with self._lock:
            from_p = self.load(from_id)
            to_p = self.load(to_id)
            if not from_p or not to_p:
                return False

            conn = {
                "target_id": to_id,
                "target_name": to_p["L1_facts"]["name"],
                "relation_type": relation_type,
                "strength": strength,
                "notes": notes,
            }
            # 避免重複
            existing = [c for c in from_p["connections"] if c["target_id"] == to_id]
            if existing:
                existing[0].update(conn)
            else:
                from_p["connections"].append(conn)
            from_p["updated_at"] = datetime.now().isoformat()
            self._save_profile(from_p)

            if bidirectional:
                rev_conn = {
                    "target_id": from_id,
                    "target_name": from_p["L1_facts"]["name"],
                    "relation_type": relation_type,
                    "strength": strength,
                    "notes": notes,
                }
                existing_rev = [c for c in to_p["connections"] if c["target_id"] == from_id]
                if existing_rev:
                    existing_rev[0].update(rev_conn)
                else:
                    to_p["connections"].append(rev_conn)
                to_p["updated_at"] = datetime.now().isoformat()
                self._save_profile(to_p)

        return True

    # --- 路徑搜尋（Path Finder） ---

    def find_paths(
        self, from_id: str, to_id: str, max_depth: int = 4,
    ) -> list[list[dict[str, Any]]]:
        """BFS 搜尋從 from_id 到 to_id 的所有路徑（≤ max_depth 層）."""
        paths: list[list[dict[str, Any]]] = []
        queue: list[list[str]] = [[from_id]]

        while queue:
            current_path = queue.pop(0)
            current_id = current_path[-1]

            if current_id == to_id and len(current_path) > 1:
                # 展開路徑為完整人物資訊
                detailed_path = []
                for pid in current_path:
                    p = self.load(pid)
                    if p:
                        detailed_path.append({
                            "profile_id": pid,
                            "name": p["L1_facts"]["name"],
                            "wan_miu_code": p["L2_personality"]["wan_miu_code"],
                            "leverage": p["L5_leverage"],
                        })
                paths.append(detailed_path)
                continue

            if len(current_path) > max_depth:
                continue

            profile = self.load(current_id)
            if not profile:
                continue

            for conn in profile.get("connections", []):
                next_id = conn["target_id"]
                if next_id not in current_path:  # 避免迴圈
                    queue.append(current_path + [next_id])

        return paths

    # --- 連動模擬（Impact Simulator） ---

    def simulate_impact(
        self, event_profile_id: str, event_description: str,
    ) -> list[dict[str, Any]]:
        """模擬一個事件對相關人物的連動影響.

        Returns 受影響人物清單，每個含：
        - profile_id, name, relation, predicted_reaction, risk_level, prevention
        """
        profile = self.load(event_profile_id)
        if not profile:
            return []

        impacts = []
        for conn in profile.get("connections", []):
            target = self.load(conn["target_id"])
            if not target:
                continue
            impacts.append({
                "profile_id": conn["target_id"],
                "name": target["L1_facts"]["name"],
                "relation_type": conn["relation_type"],
                "strength": conn.get("strength", 5),
                "wan_miu_code": target["L2_personality"]["wan_miu_code"],
                "event": event_description,
                # 以下由 LLM 在實際使用時填入
                "predicted_reaction": None,
                "risk_level": None,
                "prevention_strategy": None,
            })
        return impacts

    # --- 圖渲染 ---

    def generate_topology_data(self, domain: str | None = None) -> dict[str, Any]:
        """產出 D3.js / networkx 可用的圖結構資料.

        Returns: {"nodes": [...], "links": [...]}
        """
        index = self._load_index()
        nodes = []
        links = []
        seen_links: set[tuple[str, str]] = set()

        for pid, entry in index.items():
            if domain and domain not in entry.get("domains", []):
                continue
            profile = self.load(pid)
            if not profile:
                continue
            nodes.append({
                "id": pid,
                "name": profile["L1_facts"]["name"],
                "wan_miu_code": profile["L2_personality"]["wan_miu_code"],
                "domains": profile.get("domains", []),
                "temperature": profile["temperature"]["level"],
                "title": profile["L1_facts"].get("title"),
            })
            for conn in profile.get("connections", []):
                link_key = tuple(sorted([pid, conn["target_id"]]))
                if link_key not in seen_links:
                    seen_links.add(link_key)
                    links.append({
                        "source": pid,
                        "target": conn["target_id"],
                        "relation_type": conn["relation_type"],
                        "strength": conn.get("strength", 5),
                    })

        return {"nodes": nodes, "links": links}

    # --- Internal helpers ---

    def _save_profile(self, profile: dict[str, Any]) -> None:
        path = self._profile_path(profile["profile_id"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.rename(path)

    def _update_index_entry(self, profile: dict[str, Any]) -> None:
        index = self._load_index()
        pid = profile["profile_id"]
        index[pid] = {
            "name": profile["L1_facts"]["name"],
            "domains": profile.get("domains", []),
            "wan_miu_code": profile["L2_personality"]["wan_miu_code"],
            "temperature": profile["temperature"]["level"],
            "updated_at": profile["updated_at"],
        }
        self._save_index(index)

    def _recalc_temperature(self, profile: dict[str, Any]) -> None:
        inter = profile["L4_interactions"]
        total = inter["total_count"]
        positive = inter["positive_count"]
        negative = inter["negative_count"]

        if total == 0:
            profile["temperature"] = {"level": "new", "trend": "stable", "last_updated": datetime.now().isoformat()}
            return

        last = inter.get("last_interaction")
        if last:
            try:
                days_since = (datetime.now() - datetime.fromisoformat(last)).days
            except Exception:
                days_since = 999
        else:
            days_since = 999

        ratio = positive / total if total > 0 else 0

        if days_since > 30 or (negative > positive and total >= 3):
            level = "cold"
        elif ratio >= 0.6 and days_since <= 14:
            level = "hot"
        else:
            level = "warm"

        old_level = profile["temperature"].get("level", "new")
        temp_order = {"cold": 0, "new": 1, "warm": 2, "hot": 3}
        old_val = temp_order.get(old_level, 1)
        new_val = temp_order.get(level, 1)
        if new_val > old_val:
            trend = "rising"
        elif new_val < old_val:
            trend = "falling"
        else:
            trend = "stable"

        profile["temperature"] = {
            "level": level,
            "trend": trend,
            "last_updated": datetime.now().isoformat(),
        }


    def _recalc_confidence(self, profile: dict[str, Any]) -> None:
        """Phase 4: 自動升級置信度.

        基於：觀察記錄數 + 互動次數 + 是否有能量盤數據。
        代理評估起始 30-50%，每次新觀察 +5%，每次互動 +2%，有能量盤 +15%，上限 95%。
        """
        persona = profile.get("L2_personality", {})
        if persona.get("assessment_type") == "direct":
            return  # 直接測驗的不需要自動升級

        obs_count = len(persona.get("observations", []))
        inter_count = profile.get("L4_interactions", {}).get("total_count", 0)
        has_energy = profile.get("L3_energy", {}).get("has_reading", False)

        base_conf = 30
        conf = base_conf + (obs_count * 5) + (inter_count * 2) + (15 if has_energy else 0)
        conf = min(conf, 95)

        if conf > persona.get("confidence", 0):
            persona["confidence"] = conf


def _deep_merge(base: dict, updates: dict) -> None:
    """遞迴合併 updates 到 base."""
    for k, v in updates.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _unflatten(flat: dict[str, Any]) -> dict[str, Any]:
    """將 dot-notation key 展開為巢狀 dict.

    e.g. {"L5_leverage.channels.has": "有"} → {"L5_leverage": {"channels": {"has": "有"}}}
    """
    result: dict[str, Any] = {}
    for key, value in flat.items():
        parts = key.split(".")
        current = result
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value
    return result
