"""ToolMuscle — 工具肌肉記憶追蹤系統.

模擬生物肌肉記憶的工具熟練度機制：
  - 使用工具 → proficiency 成長（成功加更多、失敗少扣）
  - 每日萎縮（daily_atrophy）→ 不用的工具漸漸生疏
  - 高熟練度工具 → 優先推薦
  - 休眠工具偵測 → 提醒重新練習

生物隱喻：
  "Use it or lose it." — 肌肉不訓練就萎縮

設計原則：
  - 零 LLM 依賴，純 CPU 啟發式
  - JSON 持久化
  - daily_atrophy → proficiency × 0.99
  - 休眠門檻 → 30 天未使用
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

DAILY_ATROPHY_RATE = 0.99      # 每日萎縮率
DORMANT_DAYS = 30              # 休眠判定天數
SUCCESS_INCREMENT = 0.02       # 成功使用的熟練度增量
FAILURE_DECREMENT = 0.01       # 失敗使用的熟練度減量
MAX_TOOLS = 200                # 最大追蹤工具數


# ═══════════════════════════════════════════
# ToolMuscle 資料模型
# ═══════════════════════════════════════════


@dataclass
class ToolMuscle:
    """單個工具的肌肉記憶."""

    tool_id: str                         # 工具 ID
    proficiency: float = 0.1             # 熟練度（0.0 ~ 1.0）
    total_uses: int = 0                  # 總使用次數
    success_count: int = 0               # 成功次數
    failure_count: int = 0               # 失敗次數
    total_latency_ms: float = 0.0        # 總延遲（毫秒）
    last_used: str = ""                  # 最後使用時間
    created_at: str = ""                 # 首次使用時間

    @property
    def success_rate(self) -> float:
        """成功率."""
        if self.total_uses == 0:
            return 0.0
        return self.success_count / self.total_uses

    @property
    def avg_latency_ms(self) -> float:
        """平均延遲."""
        if self.total_uses == 0:
            return 0.0
        return self.total_latency_ms / self.total_uses

    @property
    def is_dormant(self) -> bool:
        """是否休眠."""
        if not self.last_used:
            return True
        try:
            last = datetime.fromisoformat(self.last_used)
            cutoff = datetime.now(timezone.utc) - timedelta(days=DORMANT_DAYS)
            return last < cutoff
        except (ValueError, TypeError):
            return True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["success_rate"] = round(self.success_rate, 4)
        d["avg_latency_ms"] = round(self.avg_latency_ms, 2)
        d["is_dormant"] = self.is_dormant
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ToolMuscle":
        # 過濾衍生欄位
        valid_keys = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in valid_keys})


# ═══════════════════════════════════════════
# ToolMuscleTracker — 肌肉追蹤器
# ═══════════════════════════════════════════


class ToolMuscleTracker:
    """工具肌肉記憶追蹤器.

    提供：
      - record_use(tool_id, success, latency)：記錄工具使用
      - daily_atrophy()：每日萎縮
      - get_dormant_tools()：取得休眠工具
      - get_recommendation()：取得工具推薦排序
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self._muscles: Dict[str, ToolMuscle] = {}
        self._data_dir = data_dir
        self._file_path: Optional[Path] = None

        if data_dir:
            self._file_path = Path(data_dir) / "_system" / "tool_muscles.json"
            self._file_path.parent.mkdir(parents=True, exist_ok=True)

        self._load()
        logger.info("ToolMuscleTracker 初始化: %d 個工具", len(self._muscles))

    def record_use(
        self,
        tool_id: str,
        success: bool = True,
        latency_ms: float = 0.0,
    ) -> float:
        """記錄工具使用.

        Args:
            tool_id: 工具 ID
            success: 是否成功
            latency_ms: 延遲時間（毫秒）

        Returns:
            更新後的熟練度
        """
        now = datetime.now(timezone.utc).isoformat()

        if tool_id not in self._muscles:
            if len(self._muscles) >= MAX_TOOLS:
                self._prune_dormant()

            self._muscles[tool_id] = ToolMuscle(
                tool_id=tool_id,
                proficiency=SUCCESS_INCREMENT if success else 0.01,
                total_uses=1,
                success_count=1 if success else 0,
                failure_count=0 if success else 1,
                total_latency_ms=latency_ms,
                last_used=now,
                created_at=now,
            )
        else:
            muscle = self._muscles[tool_id]
            muscle.total_uses += 1
            muscle.total_latency_ms += latency_ms
            muscle.last_used = now

            if success:
                muscle.success_count += 1
                muscle.proficiency = min(
                    1.0, muscle.proficiency + SUCCESS_INCREMENT
                )
            else:
                muscle.failure_count += 1
                muscle.proficiency = max(
                    0.01, muscle.proficiency - FAILURE_DECREMENT
                )

        self._save()
        return self._muscles[tool_id].proficiency

    def daily_atrophy(self) -> Dict[str, int]:
        """每日萎縮 — 所有工具熟練度 ×0.99.

        由 NightlyPipeline step_21 呼叫。

        Returns:
            {"atrophied": N, "pruned": M}
        """
        atrophied = 0
        to_prune: List[str] = []

        for tool_id, muscle in self._muscles.items():
            muscle.proficiency *= DAILY_ATROPHY_RATE
            atrophied += 1

            # 極低熟練度 + 休眠 → 修剪
            if muscle.proficiency < 0.005 and muscle.is_dormant:
                to_prune.append(tool_id)

        for tool_id in to_prune:
            del self._muscles[tool_id]

        self._save()

        result = {"atrophied": atrophied, "pruned": len(to_prune)}
        if to_prune:
            logger.info("ToolMuscle atrophy: %s", result)
        return result

    def get_proficiency(self, tool_id: str) -> float:
        """取得工具熟練度.

        Args:
            tool_id: 工具 ID

        Returns:
            熟練度 0.0 ~ 1.0，未知工具回傳 0.0
        """
        muscle = self._muscles.get(tool_id)
        return muscle.proficiency if muscle else 0.0

    def get_dormant_tools(self, days: int = DORMANT_DAYS) -> List[Dict[str, Any]]:
        """取得休眠工具.

        Args:
            days: 休眠判定天數

        Returns:
            休眠工具列表
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        dormant = []

        for muscle in self._muscles.values():
            if not muscle.last_used:
                dormant.append(muscle.to_dict())
                continue
            try:
                last = datetime.fromisoformat(muscle.last_used)
                if last < cutoff:
                    dormant.append(muscle.to_dict())
            except (ValueError, TypeError):
                dormant.append(muscle.to_dict())

        dormant.sort(key=lambda x: x.get("proficiency", 0), reverse=True)
        return dormant

    def get_recommendation(self, candidates: Optional[List[str]] = None) -> List[str]:
        """取得工具推薦排序（按熟練度降序）.

        Args:
            candidates: 候選工具列表（None = 所有工具）

        Returns:
            按熟練度排序的工具 ID 列表
        """
        if candidates is not None:
            tools = [
                (tid, self._muscles[tid].proficiency)
                for tid in candidates
                if tid in self._muscles
            ]
            # 未知工具排最後
            unknown = [tid for tid in candidates if tid not in self._muscles]
            tools.sort(key=lambda x: x[1], reverse=True)
            return [tid for tid, _ in tools] + unknown

        sorted_muscles = sorted(
            self._muscles.values(),
            key=lambda m: m.proficiency,
            reverse=True,
        )
        return [m.tool_id for m in sorted_muscles]

    def get_top_tools(self, limit: int = 10) -> List[Dict[str, Any]]:
        """取得最熟練的工具.

        Args:
            limit: 最大回傳數量

        Returns:
            按熟練度降序排列的工具列表
        """
        sorted_muscles = sorted(
            self._muscles.values(),
            key=lambda m: m.proficiency,
            reverse=True,
        )
        return [m.to_dict() for m in sorted_muscles[:limit]]

    def get_stats(self) -> Dict[str, Any]:
        """取得肌肉記憶統計."""
        if not self._muscles:
            return {
                "total_tools": 0,
                "avg_proficiency": 0.0,
                "max_proficiency": 0.0,
                "dormant_count": 0,
            }

        profs = [m.proficiency for m in self._muscles.values()]
        dormant = sum(1 for m in self._muscles.values() if m.is_dormant)
        return {
            "total_tools": len(self._muscles),
            "avg_proficiency": round(sum(profs) / len(profs), 4),
            "max_proficiency": round(max(profs), 4),
            "dormant_count": dormant,
        }

    # ─── 內部方法 ─────────────────────────

    def _prune_dormant(self) -> None:
        """修剪休眠工具（達到 MAX_TOOLS 時）."""
        dormant = [
            (tid, m.proficiency)
            for tid, m in self._muscles.items()
            if m.is_dormant
        ]
        dormant.sort(key=lambda x: x[1])

        # 移除最弱的休眠工具（至少移除 10%）
        to_remove = dormant[:max(1, len(dormant) // 2)]
        for tid, _ in to_remove:
            del self._muscles[tid]

    def _load(self) -> None:
        """從檔案載入."""
        if not self._file_path or not self._file_path.exists():
            return
        try:
            raw = json.loads(self._file_path.read_text(encoding="utf-8"))
            for tool_id, data in raw.items():
                self._muscles[tool_id] = ToolMuscle.from_dict(data)
        except Exception as e:
            logger.warning("ToolMuscleTracker 載入失敗: %s", e)

    def _save(self) -> None:
        """持久化到檔案."""
        if not self._file_path:
            return
        try:
            data = {k: v.to_dict() for k, v in self._muscles.items()}
            self._file_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("ToolMuscleTracker 儲存失敗: %s", e)
