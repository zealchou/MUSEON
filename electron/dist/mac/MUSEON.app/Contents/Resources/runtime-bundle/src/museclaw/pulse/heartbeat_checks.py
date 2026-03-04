"""Evolution Heartbeat — RED/YELLOW/GREEN 三色輪轉.

依據 THREE_LAYER_PULSE BDD Spec §7 實作。

| 色級   | 頻率     | 檢查項目                                      |
|--------|----------|----------------------------------------------|
| RED    | 每次     | 排程健康（≥5 jobs）、記憶層有資料（≥2 層）        |
| YELLOW | 每 2 次  | 進化狀態檔案存在、自主任務 log 檢查              |
| GREEN  | 每 4 次  | skill forge 掃描、待處理課程、待處理突變         |
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from museclaw.core.event_bus import EVOLUTION_HEARTBEAT, EventBus

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

EVOLUTION_HB_INTERVAL = 1800  # 30 分鐘（秒）
MIN_SCHEDULED_JOBS = 5  # RED: 最少排程 job 數
MIN_MEMORY_LAYERS = 2   # RED: 最少記憶層數

# ═══════════════════════════════════════════
# Module-level beat counter
# ═══════════════════════════════════════════

_beat_counter: int = 0


def reset_beat_counter() -> None:
    """重置 beat counter（僅供測試用）."""
    global _beat_counter
    _beat_counter = 0


def get_beat_counter() -> int:
    return _beat_counter


# ═══════════════════════════════════════════
# Main function
# ═══════════════════════════════════════════


def evolution_heartbeat_check(
    workspace: Path,
    event_bus: Optional[EventBus] = None,
    job_count: Optional[int] = None,
) -> Dict:
    """進化心跳三色輪轉檢查.

    Args:
        workspace: 工作目錄
        event_bus: EventBus 實例（可選）
        job_count: 覆寫排程 job 數量（用於測試）
    """
    global _beat_counter
    _beat_counter += 1

    results: Dict = {}

    # RED: 每次心跳（基本健康）
    results["red"] = _check_red(workspace, job_count)

    # YELLOW: 每 2 次心跳
    if _beat_counter % 2 == 0:
        results["yellow"] = _check_yellow(workspace)

    # GREEN: 每 4 次心跳
    if _beat_counter % 4 == 0:
        results["green"] = _check_green(workspace)

    # 發布事件
    if event_bus:
        event_bus.publish(EVOLUTION_HEARTBEAT, results)

    return results


# ═══════════════════════════════════════════
# RED checks（每次）
# ═══════════════════════════════════════════


def _check_red(workspace: Path, job_count: Optional[int] = None) -> Dict:
    """RED 檢查：排程健康 + 記憶層有資料."""
    warnings: List[str] = []

    # 排程健康
    actual_jobs = job_count if job_count is not None else _count_scheduled_jobs()
    if actual_jobs < MIN_SCHEDULED_JOBS:
        warnings.append(
            f"scheduled jobs below threshold: {actual_jobs} < {MIN_SCHEDULED_JOBS}"
        )

    # 記憶層有資料
    memory_layers = _count_memory_layers(workspace)
    if memory_layers < MIN_MEMORY_LAYERS:
        warnings.append(
            f"memory layers below threshold: {memory_layers} < {MIN_MEMORY_LAYERS}"
        )

    return {
        "status": "warning" if warnings else "ok",
        "scheduled_jobs": actual_jobs,
        "memory_layers": memory_layers,
        "warnings": warnings,
    }


def _count_scheduled_jobs() -> int:
    """計算排程器中的 job 數量."""
    try:
        from museclaw.pulse.heartbeat_engine import get_heartbeat_engine
        engine = get_heartbeat_engine()
        return len(engine.status())
    except Exception:
        return 0


def _count_memory_layers(workspace: Path) -> int:
    """計算有資料的記憶層數."""
    memory_dir = workspace / "memory"
    if not memory_dir.exists():
        return 0

    layer_prefixes = [
        "L0_buffer", "L1_short", "L2_ep", "L2_sem",
        "L3_procedural", "L4_identity", "L5_scratch",
    ]
    count = 0
    for prefix in layer_prefixes:
        layer_dirs = list(memory_dir.glob(f"**/{prefix}"))
        for d in layer_dirs:
            if d.is_dir() and any(d.iterdir()):
                count += 1
                break
    return count


# ═══════════════════════════════════════════
# YELLOW checks（每 2 次）
# ═══════════════════════════════════════════


def _check_yellow(workspace: Path) -> Dict:
    """YELLOW 檢查：進化狀態 + 自主任務 log."""
    warnings: List[str] = []

    # 進化狀態檔案存在
    evo_state = workspace / "_system" / "state" / "evolution_state.json"
    evo_exists = evo_state.exists()
    if not evo_exists:
        warnings.append("evolution state file not found")

    # 自主任務 log 檢查
    task_log = workspace / "_system" / "state" / "autonomous_tasks.log"
    task_log_exists = task_log.exists()

    return {
        "status": "warning" if warnings else "ok",
        "evolution_state_exists": evo_exists,
        "task_log_exists": task_log_exists,
        "warnings": warnings,
    }


# ═══════════════════════════════════════════
# GREEN checks（每 4 次）
# ═══════════════════════════════════════════


def _check_green(workspace: Path) -> Dict:
    """GREEN 檢查：skill forge + 待處理課程 + 待處理突變."""
    results: Dict = {
        "skill_forge_scan": False,
        "pending_curriculum": 0,
        "pending_mutations": 0,
    }

    # Skill Forge 掃描
    try:
        forge_dir = workspace / "_system" / "state" / "forge"
        if forge_dir.exists():
            results["skill_forge_scan"] = True
            results["pending_curriculum"] = len(
                list(forge_dir.glob("curriculum_*.json"))
            )
            results["pending_mutations"] = len(
                list(forge_dir.glob("mutation_*.json"))
            )
    except Exception as e:
        logger.error(f"GREEN check error: {e}")

    return results
