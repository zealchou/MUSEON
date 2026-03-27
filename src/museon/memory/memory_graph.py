"""Memory Graph — 記憶關聯圖引擎.

在記憶之間建立語意關聯邊，實現跨域洞見推理和主動遺忘。
"""

import json
import logging
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# 關聯類型
EDGE_TYPES = {
    "supports": "支持（同方向證據）",
    "contradicts": "矛盾（反方向證據）",
    "causes": "因果（A 導致 B）",
    "relates_to": "相關（同領域/同主題）",
    "temporal": "時序（A 發生在 B 之前）",
}


class MemoryGraph:
    """記憶關聯圖 — 在記憶之間建立和查詢語意關聯."""

    def __init__(self, data_dir: str) -> None:
        self._graph_dir = Path(data_dir) / "_system" / "memory_graph"
        self._graph_dir.mkdir(parents=True, exist_ok=True)
        self._graph_file = self._graph_dir / "edges.json"
        self._access_file = self._graph_dir / "access_log.json"
        self._lock = threading.Lock()

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        confidence: float = 0.7,
        reason: str = "",
    ) -> None:
        """新增一條關聯邊."""
        if edge_type not in EDGE_TYPES:
            logger.warning(f"未知的關聯類型: {edge_type}，允許的類型: {list(EDGE_TYPES.keys())}")
            return
        edge = {
            "source": source_id,
            "target": target_id,
            "type": edge_type,
            "confidence": confidence,
            "reason": reason,
            "created_at": datetime.now().isoformat(),
        }
        with self._lock:
            data = self._load_edges()
            # 去重：同 source+target+type 不重複
            key = f"{source_id}|{target_id}|{edge_type}"
            data["edges"] = [
                e
                for e in data.get("edges", [])
                if f"{e['source']}|{e['target']}|{e['type']}" != key
            ]
            data["edges"].append(edge)
            self._save_edges(data)

    def get_neighbors(self, memory_id: str, max_depth: int = 1) -> List[Dict[str, Any]]:
        """取得記憶的鄰居（直接關聯的記憶）."""
        data = self._load_edges()
        neighbors = []
        for edge in data.get("edges", []):
            if edge["source"] == memory_id:
                neighbors.append(
                    {"id": edge["target"], "relation": edge["type"], "confidence": edge["confidence"]}
                )
            elif edge["target"] == memory_id:
                neighbors.append(
                    {"id": edge["source"], "relation": edge["type"], "confidence": edge["confidence"]}
                )
        # 記錄存取
        self._record_access(memory_id)
        return neighbors

    def find_contradictions(self) -> List[Dict[str, Any]]:
        """找出所有矛盾的記憶對."""
        data = self._load_edges()
        return [e for e in data.get("edges", []) if e["type"] == "contradicts"]

    def get_stale_memories(self, days: int = 90, min_access: int = 3) -> List[str]:
        """取得過期記憶（超過 N 天未被引用 + 存取次數低於 M）."""
        access = self._load_access()
        cutoff = datetime.now().timestamp() - days * 86400
        stale = []
        for mem_id, info in access.get("memories", {}).items():
            last = info.get("last_accessed_ts", 0)
            count = info.get("access_count", 0)
            if last < cutoff and count < min_access:
                stale.append(mem_id)
        return stale

    def record_memory_write(
        self, memory_id: str, source: str, summary: str, tags: List[str] = None
    ) -> None:
        """記錄一筆新記憶寫入（供後續關聯分析）."""
        with self._lock:
            access = self._load_access()
            if "memories" not in access:
                access["memories"] = {}
            access["memories"][memory_id] = {
                "source": source,
                "summary": summary[:200],
                "tags": tags or [],
                "created_at": datetime.now().isoformat(),
                "last_accessed_ts": datetime.now().timestamp(),
                "access_count": 0,
            }
            self._save_access(access)

    def _record_access(self, memory_id: str) -> None:
        """記錄一次記憶存取."""
        try:
            access = self._load_access()
            if "memories" not in access:
                access["memories"] = {}
            if memory_id in access["memories"]:
                access["memories"][memory_id]["access_count"] = (
                    access["memories"][memory_id].get("access_count", 0) + 1
                )
                access["memories"][memory_id]["last_accessed_ts"] = datetime.now().timestamp()
                self._save_access(access)
        except Exception:
            pass

    def get_stats(self) -> Dict[str, Any]:
        """取得圖譜統計."""
        data = self._load_edges()
        access = self._load_access()
        edges = data.get("edges", [])
        type_counts: Dict[str, int] = {}
        for e in edges:
            t = e.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        return {
            "total_edges": len(edges),
            "total_memories": len(access.get("memories", {})),
            "edge_types": type_counts,
            "stale_90d": len(self.get_stale_memories(90)),
        }

    # ── 持久化 ───────────────────────────────

    def _load_edges(self) -> Dict:
        if not self._graph_file.exists():
            return {"edges": []}
        try:
            return json.loads(self._graph_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"edges": []}

    def _save_edges(self, data: Dict) -> None:
        content = json.dumps(data, ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(self._graph_dir), suffix=".tmp")
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
            os.close(fd)
            os.replace(tmp, str(self._graph_file))
        except Exception:
            os.close(fd)
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def _load_access(self) -> Dict:
        if not self._access_file.exists():
            return {"memories": {}}
        try:
            return json.loads(self._access_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"memories": {}}

    def _save_access(self, data: Dict) -> None:
        content = json.dumps(data, ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(self._graph_dir), suffix=".tmp")
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
            os.close(fd)
            os.replace(tmp, str(self._access_file))
        except Exception:
            os.close(fd)
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
