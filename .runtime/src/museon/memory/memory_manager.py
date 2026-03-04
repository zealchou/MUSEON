"""MemoryManager — 六層記憶管理器.

依據 SIX_LAYER_MEMORY BDD Spec §2, §7 實作：
  - 六層記憶：L0_buffer / L1_short / L2_ep / L2_sem / L3_procedural / L4_identity / L5_scratch
  - store / recall / promote / demote / supersede / maintenance
  - TF-IDF 語義搜尋（ChromosomeIndex）
  - 品質加權（QualityGate）
  - Outcome 重排序
  - 自動晉升 / TTL 過期 / 低相關性降級
"""

import logging
import threading
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from museon.memory.chromosome_index import ChromosomeIndex
from museon.memory.quality_gate import (
    QUALITY_WEIGHTS,
    assess_quality,
)
from museon.memory.storage_backend import LocalStorageBackend

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Layer Configuration (BDD Spec §2.1)
# ═══════════════════════════════════════════

LAYER_CONFIG = {
    "L0_buffer":     {"ttl_days": 14,   "dir": "L0_buffer"},
    "L1_short":      {"ttl_days": 30,   "dir": "L1_short"},
    "L2_ep":         {"ttl_days": 90,   "dir": "L2_ep"},
    "L2_sem":        {"ttl_days": 180,  "dir": "L2_sem"},
    "L3_procedural": {"ttl_days": None, "dir": "L3_procedural"},
    "L4_identity":   {"ttl_days": None, "dir": "L4_identity"},
    "L5_scratch":    {"ttl_days": 7,    "dir": "L5_scratch"},
}

VALID_LAYERS = frozenset(LAYER_CONFIG.keys())

# ═══════════════════════════════════════════
# Promotion / Demotion (BDD Spec §2.3-2.4)
# ═══════════════════════════════════════════

PROMOTION_PATHS = {
    "L0_buffer":     ["L1_short"],
    "L1_short":      ["L2_ep"],
    "L2_ep":         ["L2_sem", "L3_procedural"],
    "L2_sem":        ["L3_procedural"],
    "L3_procedural": ["L4_identity"],
    "L5_scratch":    ["L2_ep", "L2_sem"],
}

DEMOTION_TARGETS = {
    "L1_short":      "L0_buffer",
    "L2_ep":         "L1_short",
    "L2_sem":        "L2_ep",
    "L3_procedural": "L2_ep",
}

AUTO_PROMOTE_ACCESS = {
    "L0_buffer": 2,
    "L1_short":  5,
}

# ═══════════════════════════════════════════
# Outcome Weights (BDD Spec §7.4)
# ═══════════════════════════════════════════

_OUTCOME_WEIGHT = {
    "failed":  0.6,
    "partial": 0.8,
    "":        1.0,
    "success": 1.1,
}

_OUTCOME_PRIORITY = {
    "success": 3,
    "":        2,
    "partial": 1,
    "failed":  0,
}

# Demotion threshold
_DEMOTION_RELEVANCE_THRESHOLD = 0.2

# Keyword fallback similarity
_KEYWORD_FALLBACK_SIM = 0.3

# Taipei timezone
_TZ_TAIPEI = timezone(timedelta(hours=8))


def _now_taipei() -> str:
    """Asia/Taipei ISO 8601 時間戳."""
    return datetime.now(_TZ_TAIPEI).isoformat()


# ═══════════════════════════════════════════
# MemoryManager
# ═══════════════════════════════════════════


class MemoryManager:
    """六層記憶管理器."""

    def __init__(
        self,
        workspace: str,
        user_id: str = "cli_user",
        chromosome_index: Optional[ChromosomeIndex] = None,
    ):
        self._storage = LocalStorageBackend(workspace)
        self._user_id = user_id
        self._lock = threading.RLock()

        # ChromosomeIndex（每個 user_id 獨立）
        index_dir = (
            self._storage.workspace_root / user_id / "_index"
        )
        index_path = str(index_dir / "chromosome.json")
        self._index = chromosome_index or ChromosomeIndex(
            persist_path=index_path,
        )

        # 批次 access_count 更新緩衝
        self._access_count_buffer: Dict[str, int] = {}
        self._access_count_buffer_lock = threading.Lock()

        # 自動建立所有層級目錄
        self._init_layer_dirs()

    def _init_layer_dirs(self) -> None:
        """建立所有層級目錄."""
        for layer, cfg in LAYER_CONFIG.items():
            dir_path = (
                self._storage.workspace_root / self._user_id / cfg["dir"]
            )
            dir_path.mkdir(parents=True, exist_ok=True)

    # ─── Store ───

    def store(
        self,
        user_id: str,
        content: str,
        layer: str,
        tags: Optional[List[str]] = None,
        quality_tier: Optional[str] = None,
        dna27_routing: Optional[Dict] = None,
        source: str = "",
        outcome: str = "",
        session_id: str = "",
    ) -> str:
        """存儲記憶到指定層.

        Args:
            user_id: 使用者 ID
            content: 記憶內容
            layer: 記憶層級（VALID_LAYERS 之一）
            tags: 可搜尋標籤
            quality_tier: 品質等級（None = 自動評估）
            dna27_routing: DNA27 路由上下文
            source: 來源標記
            outcome: 結果標記（"" / "success" / "partial" / "failed"）
            session_id: 對話 ID（用於同 session 記憶加權）

        Returns:
            memory_id (UUID)

        Raises:
            ValueError: 無效的層級
        """
        if layer not in VALID_LAYERS:
            raise ValueError(f"無效的記憶層級: {layer}")

        with self._lock:
            memory_id = str(uuid.uuid4())
            now = _now_taipei()

            # 自動品質評估
            if quality_tier is None:
                quality_tier = assess_quality(content, source)

            entry = {
                "id": memory_id,
                "content": content,
                "layer": layer,
                "tags": tags or [],
                "quality_tier": quality_tier,
                "dna27_routing": dna27_routing or {},
                "created_at": now,
                "updated_at": now,
                "access_count": 0,
                "relevance_score": 1.0,
                "source": source,
                "outcome": outcome,
                "user_id": user_id,
                "session_id": session_id,
                "archived": False,
            }

            # 原子寫入
            layer_dir = LAYER_CONFIG[layer]["dir"]
            self._storage.write(
                user_id, layer_dir, f"{memory_id}.json", entry,
            )

            # 索引
            self._index.index(memory_id, content, tags)

            # 語義索引（VectorBridge，靜默失敗）
            self._vector_index(memory_id, content, tags, layer)

            logger.debug(
                f"Memory stored: {memory_id} → {layer} "
                f"({quality_tier}) [{source}]"
            )

            return memory_id

    # ─── Recall ───

    def recall(
        self,
        user_id: str,
        query: str,
        layers: Optional[List[str]] = None,
        limit: int = 10,
        session_id: str = "",
    ) -> List[Dict]:
        """語義檢索記憶（Qdrant-primary 架構）.

        三階段搜尋：
          1. Primary: Qdrant 向量語義搜尋
          2. Secondary: TF-IDF（僅在 Qdrant 結果不足時補充）
          3. Tertiary: Keyword fallback（仍不足時兜底）
        合併評分：vector_score * 0.7 + tfidf_score * 0.3

        access_count 不在 recall 時即時寫盤，改為批次緩衝
        （由 _flush_access_counts() 定期持久化）。

        Args:
            user_id: 使用者 ID
            query: 查詢文本
            layers: 限定層級（None = 全部）
            limit: 回傳筆數上限
            session_id: 對話 ID（可選，用於同 session 加權）

        Returns:
            [entry_dict, ...] 按複合分數降序
        """
        with self._lock:
            results: List[Tuple[float, Dict]] = []
            seen_ids: set = set()

            # ── 階段 1（Primary）：Qdrant 向量語義搜尋 ──
            vector_results = self._vector_recall(query, limit * 2)
            # vector_results: [(memory_id, score), ...]
            # 建立 vector score 查閱表
            vector_score_map: Dict[str, float] = {
                mid: score for mid, score in vector_results
            }

            for memory_id, v_score in vector_results:
                if memory_id in seen_ids:
                    continue
                entry = self._read_entry(user_id, memory_id)
                if entry is None:
                    continue
                if entry.get("archived", False):
                    continue
                if layers and entry["layer"] not in layers:
                    continue

                seen_ids.add(memory_id)

                # 品質加權（以向量分數為主）
                quality = entry.get("quality_tier", "silver")
                weighted = v_score * QUALITY_WEIGHTS.get(quality, 1.0)

                # 同 session 加權
                if session_id and entry.get("session_id") == session_id:
                    weighted *= 1.2

                # 緩衝 access_count（不寫盤）
                self._buffer_access_count(memory_id)

                results.append((weighted, entry))

            # ── 階段 2（Secondary）：TF-IDF 補充搜尋 ──
            # 僅在 Qdrant 結果不足時才執行
            if len(results) < limit:
                tfidf_candidates = self._index.search(
                    query, top_k=limit * 3,
                )

                for memory_id, tfidf_score in tfidf_candidates:
                    if memory_id in seen_ids:
                        continue
                    entry = self._read_entry(user_id, memory_id)
                    if entry is None:
                        continue
                    if entry.get("archived", False):
                        continue
                    if layers and entry["layer"] not in layers:
                        continue

                    seen_ids.add(memory_id)

                    # 混合評分：若此 ID 也有向量分數則混合，否則純 TF-IDF
                    v_score = vector_score_map.get(memory_id, 0.0)
                    if v_score > 0:
                        combined = v_score * 0.7 + tfidf_score * 0.3
                    else:
                        combined = tfidf_score * 0.3  # 純 TF-IDF 權重較低

                    quality = entry.get("quality_tier", "silver")
                    weighted = combined * QUALITY_WEIGHTS.get(quality, 1.0)

                    if session_id and entry.get("session_id") == session_id:
                        weighted *= 1.2

                    self._buffer_access_count(memory_id)

                    results.append((weighted, entry))

            # ── 階段 3（Tertiary）：Keyword Fallback ──
            if len(results) < limit:
                kw_results = self._keyword_fallback(
                    user_id, query, layers, seen_ids,
                    limit - len(results),
                )
                for entry in kw_results:
                    quality = entry.get("quality_tier", "silver")
                    weighted = (
                        _KEYWORD_FALLBACK_SIM
                        * QUALITY_WEIGHTS.get(quality, 1.0)
                    )
                    results.append((weighted, entry))

            # ── Outcome 重排序 ──
            adjusted: List[Tuple[int, float, int, Dict]] = []
            for weighted, entry in results:
                outcome = entry.get("outcome", "")
                o_weight = _OUTCOME_WEIGHT.get(outcome, 1.0)
                o_priority = _OUTCOME_PRIORITY.get(outcome, 2)
                access = entry.get("access_count", 0)
                adjusted.append((
                    o_priority,
                    weighted * o_weight,
                    access,
                    entry,
                ))

            adjusted.sort(
                key=lambda x: (x[0], x[1], x[2]),
                reverse=True,
            )

            return [entry for _, _, _, entry in adjusted[:limit]]

    def _buffer_access_count(self, memory_id: str) -> None:
        """緩衝 access_count 增量（不即時寫盤）."""
        with self._access_count_buffer_lock:
            self._access_count_buffer[memory_id] = (
                self._access_count_buffer.get(memory_id, 0) + 1
            )

    def _flush_access_counts(self, user_id: Optional[str] = None) -> int:
        """批次持久化緩衝的 access_count 增量.

        應由 maintenance() 或外部排程定期呼叫，避免每次 recall
        都觸發 O(N) 次磁碟寫入。

        Args:
            user_id: 使用者 ID（None = 使用預設）

        Returns:
            成功更新的記憶數量
        """
        uid = user_id or self._user_id
        with self._access_count_buffer_lock:
            buffer = dict(self._access_count_buffer)
            self._access_count_buffer.clear()

        if not buffer:
            return 0

        updated = 0
        now = _now_taipei()
        for memory_id, increment in buffer.items():
            entry = self._read_entry(uid, memory_id)
            if entry is None:
                continue
            entry["access_count"] = (
                entry.get("access_count", 0) + increment
            )
            entry["updated_at"] = now
            layer_dir = LAYER_CONFIG.get(
                entry["layer"], {},
            ).get("dir", entry["layer"])
            self._storage.write(
                uid, layer_dir, f"{memory_id}.json", entry,
            )
            updated += 1

        if updated:
            logger.debug(
                f"Flushed access_count for {updated} memories"
            )
        return updated

    def _read_entry(
        self, user_id: str, memory_id: str,
    ) -> Optional[Dict]:
        """嘗試從所有層讀取記憶 entry."""
        for layer, cfg in LAYER_CONFIG.items():
            data = self._storage.read(
                user_id, cfg["dir"], f"{memory_id}.json",
            )
            if data is not None:
                return data
        return None

    def _keyword_fallback(
        self,
        user_id: str,
        query: str,
        layers: Optional[List[str]],
        seen_ids: set,
        limit: int,
    ) -> List[Dict]:
        """關鍵字 fallback 搜尋."""
        results: List[Dict] = []
        query_lower = query.lower()

        target_layers = layers or list(LAYER_CONFIG.keys())
        for layer in target_layers:
            cfg = LAYER_CONFIG.get(layer)
            if not cfg:
                continue

            filenames = self._storage.list_files(
                user_id, cfg["dir"], "*.json",
            )
            for fname in filenames:
                if len(results) >= limit:
                    return results

                mid = fname.replace(".json", "")
                if mid in seen_ids:
                    continue

                entry = self._storage.read(user_id, cfg["dir"], fname)
                if entry is None or entry.get("archived", False):
                    continue

                # 檢查 content 或 tags 是否包含查詢字串
                content = entry.get("content", "").lower()
                tags = [t.lower() for t in entry.get("tags", [])]
                if query_lower in content or any(
                    query_lower in t for t in tags
                ):
                    seen_ids.add(mid)
                    results.append(entry)

        return results

    # ─── Promote ───

    def promote(
        self, user_id: str, memory_id: str, target_layer: str,
    ) -> Dict:
        """晉升記憶到目標層.

        Raises:
            ValueError: 非法晉升路徑
        """
        with self._lock:
            entry = self._read_entry(user_id, memory_id)
            if entry is None:
                raise ValueError(f"記憶不存在: {memory_id}")

            old_layer = entry["layer"]
            valid = PROMOTION_PATHS.get(old_layer, [])
            if target_layer not in valid:
                raise ValueError(
                    f"無法從 {old_layer} 晉升到 {target_layer}"
                )

            old_dir = LAYER_CONFIG[old_layer]["dir"]
            new_dir = LAYER_CONFIG[target_layer]["dir"]

            entry["layer"] = target_layer
            entry["updated_at"] = _now_taipei()

            # 寫入新位置 → 刪除舊位置
            self._storage.write(
                user_id, new_dir, f"{memory_id}.json", entry,
            )
            self._storage.delete(user_id, old_dir, f"{memory_id}.json")

            logger.debug(
                f"Memory promoted: {memory_id} "
                f"{old_layer} → {target_layer}"
            )

            return entry

    # ─── Demote ───

    def demote(self, user_id: str, memory_id: str) -> Dict:
        """降級記憶.

        Raises:
            ValueError: 不可降級的層
        """
        with self._lock:
            entry = self._read_entry(user_id, memory_id)
            if entry is None:
                raise ValueError(f"記憶不存在: {memory_id}")

            old_layer = entry["layer"]
            target = DEMOTION_TARGETS.get(old_layer)
            if target is None:
                raise ValueError(f"{old_layer} 不可降級")

            old_dir = LAYER_CONFIG[old_layer]["dir"]
            new_dir = LAYER_CONFIG[target]["dir"]

            entry["layer"] = target
            entry["updated_at"] = _now_taipei()

            self._storage.write(
                user_id, new_dir, f"{memory_id}.json", entry,
            )
            self._storage.delete(user_id, old_dir, f"{memory_id}.json")

            logger.debug(
                f"Memory demoted: {memory_id} "
                f"{old_layer} → {target}"
            )

            return entry

    # ─── Supersede ───

    def supersede(
        self,
        user_id: str,
        old_id: str,
        new_content: str,
        tags: Optional[List[str]] = None,
        source: str = "supersede",
    ) -> Dict:
        """版本取代：歸檔舊記憶，建立新記憶.

        新記憶繼承 access_count，設定 supersedes_id。
        """
        with self._lock:
            old = self._read_entry(user_id, old_id)
            if old is None:
                raise ValueError(f"記憶不存在: {old_id}")

            # 1. 歸檔舊記憶
            now = _now_taipei()
            old["archived"] = True
            old["archive_reason"] = "superseded"
            old["archived_at"] = now
            old_dir = LAYER_CONFIG[old["layer"]]["dir"]
            self._storage.write(
                user_id, old_dir, f"{old_id}.json", old,
            )
            self._index.remove(old_id)

            # 2. 建立新記憶
            new_id = self.store(
                user_id=user_id,
                content=new_content,
                layer=old["layer"],
                tags=tags or old.get("tags", []),
                source=source,
            )

            # 3. 設定版本鏈
            new_entry = self._read_entry(user_id, new_id)
            if new_entry:
                new_entry["supersedes_id"] = old_id
                new_entry["access_count"] = old.get("access_count", 0)
                new_dir = LAYER_CONFIG[new_entry["layer"]]["dir"]
                self._storage.write(
                    user_id, new_dir, f"{new_id}.json", new_entry,
                )

            logger.debug(
                f"Memory superseded: {old_id} → {new_id}"
            )

            return new_entry or {"id": new_id}

    # ─── Maintenance ───

    def maintenance(self, user_id: Optional[str] = None) -> Dict[str, int]:
        """執行維護：TTL 過期 / 低相關性降級 / 自動晉升.

        Returns:
            {"expired": N, "promoted": N, "demoted": N}
        """
        uid = user_id or self._user_id
        stats = {"expired": 0, "promoted": 0, "demoted": 0}
        now = datetime.now(_TZ_TAIPEI)

        with self._lock:
            for layer, cfg in LAYER_CONFIG.items():
                filenames = self._storage.list_files(
                    uid, cfg["dir"], "*.json",
                )

                for fname in filenames:
                    entry = self._storage.read(uid, cfg["dir"], fname)
                    if entry is None or entry.get("archived", False):
                        continue

                    # 計算年齡
                    created_str = entry.get("created_at", "")
                    try:
                        created = datetime.fromisoformat(created_str)
                        age_days = (now - created).days
                    except (ValueError, TypeError):
                        age_days = 0

                    memory_id = entry.get("id", fname.replace(".json", ""))

                    # 1. TTL 過期
                    ttl = cfg["ttl_days"]
                    if ttl is not None and age_days > ttl:
                        self._storage.delete(uid, cfg["dir"], fname)
                        self._index.remove(memory_id)
                        stats["expired"] += 1
                        continue

                    # 2. 低相關性降級
                    relevance = entry.get("relevance_score", 1.0)
                    if (
                        relevance < _DEMOTION_RELEVANCE_THRESHOLD
                        and layer in DEMOTION_TARGETS
                    ):
                        try:
                            self.demote(uid, memory_id)
                            stats["demoted"] += 1
                        except ValueError:
                            pass
                        continue

                    # 3. 自動晉升
                    threshold = AUTO_PROMOTE_ACCESS.get(layer)
                    if threshold is not None:
                        access = entry.get("access_count", 0)
                        if access >= threshold:
                            targets = PROMOTION_PATHS.get(layer, [])
                            if targets:
                                try:
                                    self.promote(uid, memory_id, targets[0])
                                    stats["promoted"] += 1
                                except ValueError:
                                    pass

            # 持久化索引
            self._index.save()

            # 批次持久化 access_count 緩衝
            flushed = self._flush_access_counts(uid)
            if flushed:
                logger.debug(
                    f"Maintenance flushed {flushed} access counts"
                )

        return stats

    # ─── List ───

    def list_memories(
        self,
        user_id: str,
        layer: str,
        include_archived: bool = False,
    ) -> List[Dict]:
        """列出指定層的所有記憶."""
        cfg = LAYER_CONFIG.get(layer)
        if not cfg:
            return []

        filenames = self._storage.list_files(
            user_id, cfg["dir"], "*.json",
        )

        results = []
        for fname in filenames:
            entry = self._storage.read(user_id, cfg["dir"], fname)
            if entry is None:
                continue
            if not include_archived and entry.get("archived", False):
                continue
            results.append(entry)

        return results

    # ─── Delete (soft) ───

    def delete(self, user_id: str, memory_id: str) -> bool:
        """軟刪除記憶."""
        with self._lock:
            entry = self._read_entry(user_id, memory_id)
            if entry is None:
                return False

            layer_dir = LAYER_CONFIG.get(
                entry["layer"], {},
            ).get("dir", entry["layer"])

            self._storage.delete(
                user_id, layer_dir, f"{memory_id}.json",
            )
            self._index.remove(memory_id)

            return True

    # ─── Index access ───

    @property
    def index(self) -> ChromosomeIndex:
        """取得 ChromosomeIndex 實例."""
        return self._index

    # ─── VectorBridge 整合（靜默失敗） ───

    def _get_vector_bridge(self):
        """Lazy 取得 VectorBridge（靜默失敗）."""
        try:
            from museon.vector.vector_bridge import VectorBridge

            workspace = self._storage.workspace_root
            vb = VectorBridge(workspace=workspace)
            if vb.is_available():
                return vb
        except Exception:
            pass
        return None

    def _vector_index(
        self, memory_id: str, content: str,
        tags: Optional[List[str]], layer: str,
    ) -> None:
        """語義索引到 Qdrant（靜默失敗）."""
        try:
            vb = self._get_vector_bridge()
            if vb is None:
                return

            metadata = {"layer": layer}
            if tags:
                metadata["tags"] = tags

            vb.index("memories", memory_id, content, metadata=metadata)
        except Exception:
            pass  # 靜默失敗，不影響主流程

    def _vector_recall(
        self, query: str, limit: int,
    ) -> List[Tuple[str, float]]:
        """VectorBridge 語義搜尋（靜默失敗回傳空 list）.

        Returns:
            [(memory_id, score), ...] 格式與 ChromosomeIndex.search 一致
        """
        try:
            vb = self._get_vector_bridge()
            if vb is None:
                return []

            results = vb.search("memories", query, limit=limit)
            return [
                (r["id"], r["score"])
                for r in results
            ]
        except Exception:
            return []
