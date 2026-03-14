"""Footprint — 三層行為足跡追蹤系統.

所有 MUSEON 行為留下可追溯的足跡，系統自動寫入：
  L1 ActionTrace  — 每個外部動作（API 呼叫、檔案操作、訊息發送）— 30 天保留
  L2 DecisionTrace — 為什麼選擇這個 skill/tool、考慮的替代方案 — 90 天保留
  L3 EvolutionTrace — ANIMA 演化、突觸更新、肌肉變化 — 永久保留

設計原則：
  - 零 LLM 依賴，純 CPU 操作
  - JSONL 持久化，append-only
  - 自動清理（NightlyPipeline 呼叫 cleanup）
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from museon.core.data_bus import DataContract, StoreSpec, StoreEngine, TTLTier

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 保留天數
# ═══════════════════════════════════════════

L1_RETENTION_DAYS = 30
L2_RETENTION_DAYS = 90
# L3 永久保留，不清理


# ═══════════════════════════════════════════
# 足跡資料模型
# ═══════════════════════════════════════════


@dataclass
class ActionTrace:
    """L1 — 外部動作足跡."""

    timestamp: str = ""
    action_type: str = ""       # api_call, file_op, message_send, tool_use, docker_op
    target: str = ""            # 目標（URL、檔案路徑、channel 名稱）
    params_summary: str = ""    # 參數摘要（不含敏感資料）
    result_summary: str = ""    # 結果摘要
    token_cost: float = 0.0     # token 消耗（USD）
    duration_ms: float = 0.0    # 執行時間（毫秒）
    success: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActionTrace":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class DecisionTrace:
    """L2 — 決策軌跡."""

    timestamp: str = ""
    decision_type: str = ""     # skill_route, tool_select, model_select, budget_alloc
    chosen: str = ""            # 最終選擇
    alternatives: List[str] = field(default_factory=list)  # 考慮過的替代方案
    reasoning: str = ""         # 選擇理由
    score: Optional[Dict[str, float]] = None  # 5D 評分（如果有）
    context: str = ""           # 相關上下文

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DecisionTrace":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class EvolutionTrace:
    """L3 — 演化記錄（永久保留）."""

    timestamp: str = ""
    layer: str = ""             # psi, synapse, muscle, immune, anima, trigger
    field_path: str = ""        # 變更的欄位路徑
    old_value_summary: str = "" # 舊值摘要
    new_value_summary: str = "" # 新值摘要
    trigger: str = ""           # 觸發來源（哪個觸發器或事件）
    impact: str = ""            # 影響評估

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EvolutionTrace":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════
# FootprintStore — 持久化層
# ═══════════════════════════════════════════


class FootprintStore(DataContract):
    """三層足跡持久化管理.

    儲存結構：
      data/_system/footprints/
        ├── actions.jsonl      (L1)
        ├── decisions.jsonl    (L2)
        └── evolutions.jsonl   (L3)
    """

    @classmethod
    def store_spec(cls) -> StoreSpec:
        return StoreSpec(
            name="footprint_store",
            engine=StoreEngine.JSONL,
            ttl=TTLTier.MEDIUM,  # L1=30d, L2=90d, L3=permanent（取中間值）
            write_mode="append_only",
            description="三層行為足跡 JSONL 追蹤",
            tables=["actions.jsonl", "decisions.jsonl", "evolutions.jsonl"],
        )

    def health_check(self) -> Dict[str, Any]:
        try:
            sizes = {}
            for name, path in [
                ("actions", self._action_path),
                ("decisions", self._decision_path),
                ("evolutions", self._evolution_path),
            ]:
                sizes[name] = path.stat().st_size if path.exists() else 0
            return {"status": "ok", "file_sizes": sizes}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def __init__(self, data_dir: Path):
        self._base_dir = Path(data_dir) / "_system" / "footprints"
        self._base_dir.mkdir(parents=True, exist_ok=True)

        self._action_path = self._base_dir / "actions.jsonl"
        self._decision_path = self._base_dir / "decisions.jsonl"
        self._evolution_path = self._base_dir / "evolutions.jsonl"

        self._lock = threading.Lock()

        logger.info("FootprintStore 初始化完成: %s", self._base_dir)

    # ─── 寫入方法 ─────────────────────────

    def trace_action(
        self,
        action_type: str,
        target: str,
        params_summary: str = "",
        result_summary: str = "",
        token_cost: float = 0.0,
        duration_ms: float = 0.0,
        success: bool = True,
    ) -> None:
        """記錄 L1 外部動作足跡."""
        trace = ActionTrace(
            timestamp=datetime.now(timezone.utc).isoformat(),
            action_type=action_type,
            target=target,
            params_summary=params_summary[:200],
            result_summary=result_summary[:200],
            token_cost=token_cost,
            duration_ms=duration_ms,
            success=success,
        )
        self._append(self._action_path, trace.to_dict())

    def trace_decision(
        self,
        decision_type: str,
        chosen: str,
        alternatives: Optional[List[str]] = None,
        reasoning: str = "",
        score: Optional[Dict[str, float]] = None,
        context: str = "",
    ) -> None:
        """記錄 L2 決策軌跡."""
        trace = DecisionTrace(
            timestamp=datetime.now(timezone.utc).isoformat(),
            decision_type=decision_type,
            chosen=chosen,
            alternatives=alternatives or [],
            reasoning=reasoning[:300],
            score=score,
            context=context[:200],
        )
        self._append(self._decision_path, trace.to_dict())

    def trace_evolution(
        self,
        layer: str,
        field_path: str,
        old_value_summary: str,
        new_value_summary: str,
        trigger: str,
        impact: str = "",
    ) -> None:
        """記錄 L3 演化記錄（永久保留）."""
        trace = EvolutionTrace(
            timestamp=datetime.now(timezone.utc).isoformat(),
            layer=layer,
            field_path=field_path,
            old_value_summary=str(old_value_summary)[:200],
            new_value_summary=str(new_value_summary)[:200],
            trigger=trigger,
            impact=impact[:200],
        )
        self._append(self._evolution_path, trace.to_dict())

    # ─── 讀取方法 ─────────────────────────

    def get_recent_actions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """取得最近的 L1 動作足跡."""
        return self._read_recent(self._action_path, limit)

    def get_recent_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """取得最近的 L2 決策軌跡."""
        return self._read_recent(self._decision_path, limit)

    def get_recent_evolutions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """取得最近的 L3 演化記錄."""
        return self._read_recent(self._evolution_path, limit)

    # ─── 清理方法（由 NightlyPipeline 呼叫）────

    def cleanup(self) -> Dict[str, int]:
        """清理過期足跡.

        Returns:
            清理統計 {"l1_removed": N, "l2_removed": N}
        """
        l1_removed = self._cleanup_file(self._action_path, L1_RETENTION_DAYS)
        l2_removed = self._cleanup_file(self._decision_path, L2_RETENTION_DAYS)
        # L3 不清理
        return {"l1_removed": l1_removed, "l2_removed": l2_removed}

    def get_stats(self) -> Dict[str, Any]:
        """取得足跡統計."""
        return {
            "l1_actions": self._count_lines(self._action_path),
            "l2_decisions": self._count_lines(self._decision_path),
            "l3_evolutions": self._count_lines(self._evolution_path),
        }

    # ─── 內部方法 ─────────────────────────

    def _append(self, path: Path, data: Dict[str, Any]) -> None:
        """Append-only 寫入."""
        with self._lock:
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error("Footprint 寫入失敗 (%s): %s", path.name, e)

    def _read_recent(self, path: Path, limit: int) -> List[Dict[str, Any]]:
        """讀取最近 N 筆."""
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8").strip().split("\n")
            recent = lines[-limit:] if len(lines) > limit else lines
            return [json.loads(line) for line in recent if line.strip()]
        except Exception as e:
            logger.error("Footprint 讀取失敗 (%s): %s", path.name, e)
            return []

    def _cleanup_file(self, path: Path, retention_days: int) -> int:
        """清理超過保留期的記錄."""
        if not path.exists():
            return 0

        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        removed = 0

        try:
            lines = path.read_text(encoding="utf-8").strip().split("\n")
            kept = []
            for line in lines:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    ts = entry.get("timestamp", "")
                    if ts >= cutoff:
                        kept.append(line)
                    else:
                        removed += 1
                except (json.JSONDecodeError, KeyError):
                    kept.append(line)  # 解析失敗的保留

            if removed > 0:
                # 原子性寫入
                tmp_path = path.with_suffix(".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(kept) + "\n" if kept else "")
                    f.flush()
                    os.fsync(f.fileno())
                tmp_path.rename(path)
                logger.info("Footprint 清理 %s: 移除 %d 筆", path.name, removed)

        except Exception as e:
            logger.error("Footprint 清理失敗 (%s): %s", path.name, e)
            return 0

        return removed

    def _count_lines(self, path: Path) -> int:
        """計算檔案行數."""
        if not path.exists():
            return 0
        try:
            return sum(1 for line in path.read_text(encoding="utf-8").strip().split("\n")
                       if line.strip())
        except Exception:
            return 0
