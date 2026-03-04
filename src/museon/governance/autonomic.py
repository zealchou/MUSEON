"""Autonomic Layer — 自律神經系統.

模擬生物自律神經的背景修復機制：
  - RepairTask：帶優先級的修復任務
  - RepairQueue：優先佇列
  - AutonomicLayer：每心跳 tick 檢查佇列，有預算就修

能量分配規則：
  - 自律層優先從 reserve_pool 扣費
  - reserve 不足時最多借表層 15% 日預算
  - 大部分修復是 CPU（重啟容器、修復檔案），不花 token
  - 只有「上網找藥方」才花 token

「生病」的外在表現：
  - < 5%：無感（日常代謝）
  - 5-20%：回應稍慢、用詞更簡潔
  - > 20%：降級 haiku、減少主動推送
  - 死亡威脅：表層暫停，全力修復

設計原則：
  - 零 LLM 依賴（修復動作本身是 CPU）
  - 只有需要 LLM 診斷時才花 token
  - 每次 tick 只處理一個任務（避免堵塞心跳）
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import heapq
import json
from pathlib import Path

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 修復任務
# ═══════════════════════════════════════════


class RepairPriority(Enum):
    """修復優先級（數字越小越優先）."""

    CRITICAL = 1    # 死亡威脅（SafetyAnchor 被觸碰）
    HIGH = 2        # 核心功能異常（記憶損壞、DB 故障）
    MEDIUM = 3      # 效能退化（回應變慢、命中率下降）
    LOW = 4         # 輕微問題（日誌堆積、暫存清理）
    ROUTINE = 5     # 例行維護（版本檢查、健康報告）


class RepairCategory(Enum):
    """修復類別."""

    CPU_ONLY = "cpu_only"         # 純 CPU 操作（不花 token）
    TOKEN_LIGHT = "token_light"   # 輕度 token（~$0.01）
    TOKEN_HEAVY = "token_heavy"   # 重度 token（~$0.05+）


@dataclass(order=True)
class RepairTask:
    """帶優先級的修復任務.

    使用 priority 作為排序鍵（heapq 最小堆）。
    """

    priority: int                             # 排序用（RepairPriority.value）
    task_id: str = field(compare=False)       # 任務 ID
    description: str = field(compare=False)   # 任務描述
    category: str = field(compare=False)      # RepairCategory.value
    estimated_cost_usd: float = field(default=0.0, compare=False)
    repair_fn_name: str = field(default="", compare=False)  # 修復函數名稱（供序列化）
    created_at: str = field(default="", compare=False)
    attempts: int = field(default=0, compare=False)
    max_attempts: int = field(default=3, compare=False)
    last_error: str = field(default="", compare=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "priority": self.priority,
            "task_id": self.task_id,
            "description": self.description,
            "category": self.category,
            "estimated_cost_usd": self.estimated_cost_usd,
            "repair_fn_name": self.repair_fn_name,
            "created_at": self.created_at,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "last_error": self.last_error,
        }


# ═══════════════════════════════════════════
# RepairQueue — 優先佇列
# ═══════════════════════════════════════════


class RepairQueue:
    """修復任務優先佇列.

    使用 heapq 實現最小堆（priority 越小越先出）。
    """

    def __init__(self) -> None:
        self._heap: List[RepairTask] = []
        self._task_ids: set = set()  # 防止重複入隊

    def push(self, task: RepairTask) -> bool:
        """入隊.

        Args:
            task: 修復任務

        Returns:
            True = 成功入隊, False = 重複任務
        """
        if task.task_id in self._task_ids:
            return False
        heapq.heappush(self._heap, task)
        self._task_ids.add(task.task_id)
        return True

    def pop(self) -> Optional[RepairTask]:
        """出隊（最高優先級）.

        Returns:
            最高優先級的任務，或 None（佇列為空）
        """
        while self._heap:
            task = heapq.heappop(self._heap)
            if task.task_id in self._task_ids:
                self._task_ids.discard(task.task_id)
                return task
        return None

    def peek(self) -> Optional[RepairTask]:
        """查看最高優先級任務（不移除）."""
        while self._heap:
            if self._heap[0].task_id in self._task_ids:
                return self._heap[0]
            heapq.heappop(self._heap)
        return None

    @property
    def size(self) -> int:
        return len(self._task_ids)

    @property
    def is_empty(self) -> bool:
        return len(self._task_ids) == 0

    def get_all(self) -> List[RepairTask]:
        """取得所有任務（不移除）."""
        return [t for t in self._heap if t.task_id in self._task_ids]


# ═══════════════════════════════════════════
# AutonomicLayer — 自律神經系統
# ═══════════════════════════════════════════


class AutonomicLayer:
    """自律神經系統 — 背景修復層.

    每心跳 tick 檢查佇列，有預算就修。
    大部分修復是 CPU 操作，不花 token。

    使用：
      - enqueue(task)：入隊修復任務
      - tick(token_budget)：心跳觸發（由 HeartbeatEngine 呼叫）
      - assess_impact()：評估整體影響
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self._queue = RepairQueue()
        self._repair_fns: Dict[str, Callable] = {}  # 修復函數註冊表
        self._completed: List[Dict[str, Any]] = []   # 最近完成的任務
        self._failed: List[Dict[str, Any]] = []      # 最近失敗的任務
        self._total_repaired = 0
        self._total_cost_usd = 0.0
        self._data_dir = data_dir

        # 持久化路徑
        self._history_path: Optional[Path] = None
        if data_dir:
            self._history_path = Path(data_dir) / "_system" / "autonomic_history.json"
            self._history_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("AutonomicLayer 初始化完成")

    def register_repair_fn(self, name: str, fn: Callable) -> None:
        """註冊修復函數.

        Args:
            name: 函數名稱（對應 RepairTask.repair_fn_name）
            fn: 修復函數（無參數，回傳 True/False）
        """
        self._repair_fns[name] = fn

    def enqueue(
        self,
        task_id: str,
        description: str,
        priority: RepairPriority = RepairPriority.MEDIUM,
        category: RepairCategory = RepairCategory.CPU_ONLY,
        estimated_cost_usd: float = 0.0,
        repair_fn_name: str = "",
    ) -> bool:
        """入隊修復任務.

        Args:
            task_id: 唯一任務 ID
            description: 任務描述
            priority: 優先級
            category: 類別
            estimated_cost_usd: 預估 token 花費（CPU_ONLY 為 0）
            repair_fn_name: 修復函數名稱

        Returns:
            True = 成功入隊
        """
        task = RepairTask(
            priority=priority.value,
            task_id=task_id,
            description=description,
            category=category.value,
            estimated_cost_usd=estimated_cost_usd,
            repair_fn_name=repair_fn_name,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        result = self._queue.push(task)
        if result:
            logger.info(
                "Autonomic: 入隊修復任務 [%s] priority=%d category=%s",
                task_id, priority.value, category.value,
            )
        return result

    def tick(self, token_budget_manager: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """心跳觸發 — 嘗試執行一個修復任務.

        由 HeartbeatEngine 每 10 秒呼叫。
        每次只處理一個任務（避免堵塞心跳）。

        Args:
            token_budget_manager: TokenBudgetManager 實例（可選）

        Returns:
            執行結果 dict，或 None（無待修復任務）
        """
        if self._queue.is_empty:
            return None

        # 查看最高優先級任務
        task = self._queue.peek()
        if not task:
            return None

        # 預算檢查
        if task.category != RepairCategory.CPU_ONLY.value:
            if token_budget_manager:
                can_afford = token_budget_manager.spend(
                    task.estimated_cost_usd,
                    category="self_repair",
                )
                if not can_afford:
                    # 預算不足 — CRITICAL 任務嘗試借預算
                    if task.priority <= RepairPriority.HIGH.value:
                        logger.warning(
                            "Autonomic: 預算不足但任務為高優先 [%s]，嘗試借預算",
                            task.task_id,
                        )
                    else:
                        return {"skipped": True, "reason": "budget_insufficient", "task_id": task.task_id}

        # 出隊並執行
        task = self._queue.pop()
        if not task:
            return None

        task.attempts += 1
        now = datetime.now(timezone.utc).isoformat()

        # 執行修復
        success = False
        error_msg = ""
        try:
            repair_fn = self._repair_fns.get(task.repair_fn_name)
            if repair_fn:
                success = bool(repair_fn())
            else:
                # 沒有對應的修復函數 — 記錄但視為成功（可能是手動修復）
                logger.warning(
                    "Autonomic: 修復函數 [%s] 未註冊，跳過",
                    task.repair_fn_name,
                )
                success = True
        except Exception as e:
            error_msg = str(e)[:200]
            task.last_error = error_msg
            logger.error("Autonomic: 修復失敗 [%s]: %s", task.task_id, e)

        result = {
            "task_id": task.task_id,
            "description": task.description,
            "priority": task.priority,
            "category": task.category,
            "success": success,
            "attempts": task.attempts,
            "error": error_msg,
            "timestamp": now,
        }

        if success:
            self._total_repaired += 1
            self._total_cost_usd += task.estimated_cost_usd
            self._completed.append(result)
            # 保留最近 20 筆
            if len(self._completed) > 20:
                self._completed = self._completed[-20:]
        else:
            # 重試機制
            if task.attempts < task.max_attempts:
                self._queue.push(task)
                logger.info(
                    "Autonomic: 任務 [%s] 重新入隊 (%d/%d)",
                    task.task_id, task.attempts, task.max_attempts,
                )
            else:
                self._failed.append(result)
                if len(self._failed) > 20:
                    self._failed = self._failed[-20:]
                logger.warning(
                    "Autonomic: 任務 [%s] 達到最大重試次數，放棄",
                    task.task_id,
                )

        return result

    def assess_impact(self) -> str:
        """評估整體影響.

        Returns:
            "light" / "moderate" / "heavy" / "critical"
        """
        queue_size = self._queue.size

        if queue_size == 0:
            return "light"

        # 檢查是否有 CRITICAL 任務
        tasks = self._queue.get_all()
        has_critical = any(t.priority <= RepairPriority.CRITICAL.value for t in tasks)
        has_high = any(t.priority <= RepairPriority.HIGH.value for t in tasks)

        if has_critical:
            return "critical"
        if has_high or queue_size >= 5:
            return "heavy"
        if queue_size >= 2:
            return "moderate"
        return "light"

    def get_sickness_level(self) -> float:
        """取得「生病程度」百分比.

        用於外在表現（回應品質降級等）。

        Returns:
            0.0 ~ 1.0（0 = 健康，1 = 死亡威脅）
        """
        impact = self.assess_impact()
        return {
            "light": 0.0,
            "moderate": 0.1,
            "heavy": 0.3,
            "critical": 0.8,
        }.get(impact, 0.0)

    def get_status(self) -> Dict[str, Any]:
        """取得自律神經狀態."""
        return {
            "queue_size": self._queue.size,
            "impact": self.assess_impact(),
            "sickness_level": self.get_sickness_level(),
            "total_repaired": self._total_repaired,
            "total_cost_usd": round(self._total_cost_usd, 4),
            "recent_completed": len(self._completed),
            "recent_failed": len(self._failed),
            "pending_tasks": [
                t.to_dict() for t in self._queue.get_all()
            ],
        }

    def save_history(self) -> None:
        """儲存歷史記錄."""
        if not self._history_path:
            return
        try:
            data = {
                "total_repaired": self._total_repaired,
                "total_cost_usd": self._total_cost_usd,
                "recent_completed": self._completed[-10:],
                "recent_failed": self._failed[-10:],
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            self._history_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("Autonomic 歷史儲存失敗: %s", e)
