"""breath_watcher — Breath Protocol 觀察層.

四條河流的統一收集器。
只觀察、只記錄。不分析、不診斷、不動手。

River 1: Zeal 互動 — 讀 session 摘要 + feedback memory
River 2: 客戶互動 — 讀群組對話品質 + FeedbackLoop + QA
River 3: 自我觀察 — 讀系統指標 + 耦合健康 + 接線完整性
River 4: 外部探索 — 讀 PulseEngine 探索結果 + DigestEngine 成果
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 不可變：觀察期禁止呼叫的模組
_MUTATION_BLACKLIST = frozenset([
    "parameter_tuner",
    "morphenix",
    "skill_installer",
    "breath_executor",
])

OBSERVATION_LOCK = "OBSERVATION_PHASE"  # 觀察期標記


async def collect_observations(workspace: Path) -> dict[str, Any]:
    """收集四條河流的觀察資料，寫入本週 observations JSONL.

    Args:
        workspace: MUSEON 根目錄（~/MUSEON）

    Returns:
        統計 dict：{river_1: N, river_2: N, river_3: N, river_4: N, total: N}
    """
    week_id = datetime.now().strftime("%Y-w%W")
    output_dir = workspace / "data/_system/breath/observations"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{week_id}.jsonl"

    all_observations: list[dict] = []

    # 四條河流並行收集（各自獨立，不依賴彼此）
    r1 = await _collect_zeal_river(workspace)
    r2 = await _collect_client_river(workspace)
    r3 = await _collect_self_river(workspace)
    r4 = await _collect_exploration_river(workspace)

    all_observations.extend(r1)
    all_observations.extend(r2)
    all_observations.extend(r3)
    all_observations.extend(r4)

    # 寫入 JSONL（追加模式，避免同週多次執行覆蓋）
    with output_path.open("a", encoding="utf-8") as f:
        for obs in all_observations:
            f.write(json.dumps(obs, ensure_ascii=False) + "\n")

    stats = {
        "river_1": len(r1),
        "river_2": len(r2),
        "river_3": len(r3),
        "river_4": len(r4),
        "total": len(all_observations),
        "week_id": week_id,
        "output_path": str(output_path),
    }
    logger.info(f"[BreathWatcher] 觀察收集完成: {stats}")
    return stats


# ── River 1：Zeal 互動 ──────────────────────────────────────────────────────

async def _collect_zeal_river(workspace: Path) -> list[dict]:
    """讀最近 7 天的 Claude Code session 摘要 + feedback memory."""
    observations: list[dict] = []
    memory_dir = Path.home() / ".claude/projects/-Users-ZEALCHOU/memory"
    sessions_dir = memory_dir / "sessions"
    cutoff = datetime.now() - timedelta(days=7)

    # Session 摘要
    if sessions_dir.exists():
        for md_file in sorted(sessions_dir.glob("*.md")):
            try:
                # 檔名格式：YYYY-MM-DD_HH-MM_主題.md
                date_str = md_file.stem[:10]
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                if file_date < cutoff:
                    continue
                content = md_file.read_text(encoding="utf-8")
                observations.append({
                    "river": "zeal_interaction",
                    "timestamp": file_date.isoformat(),
                    "type": "session_summary",
                    "content": content[:2000],  # 取前 2000 字元
                    "severity": "info",
                    "source": str(md_file.name),
                })
            except (ValueError, OSError) as e:
                logger.debug(f"[River1] 跳過 {md_file.name}: {e}")

    # Feedback memory
    for fb_file in memory_dir.glob("feedback_*.md"):
        try:
            content = fb_file.read_text(encoding="utf-8")
            observations.append({
                "river": "zeal_interaction",
                "timestamp": datetime.now().isoformat(),
                "type": "feedback_memory",
                "content": content[:1000],
                "severity": "info",
                "source": str(fb_file.name),
            })
        except OSError as e:
            logger.debug(f"[River1] 跳過 feedback {fb_file.name}: {e}")

    logger.debug(f"[River1/Zeal] {len(observations)} 條觀察")
    return observations


# ── River 2：客戶互動 ────────────────────────────────────────────────────────

async def _collect_client_river(workspace: Path) -> list[dict]:
    """讀群組對話品質 + FeedbackLoop + QA 報告."""
    observations: list[dict] = []
    system_dir = workspace / "data/_system"

    # FeedbackLoop daily summary
    fb_summary = system_dir / "feedback_loop/daily_summary.json"
    if fb_summary.exists():
        try:
            data = json.loads(fb_summary.read_text(encoding="utf-8"))
            observations.append({
                "river": "client_interaction",
                "timestamp": datetime.now().isoformat(),
                "type": "feedback_loop_summary",
                "content": data,
                "severity": _infer_severity(data),
                "source": "feedback_loop/daily_summary.json",
            })
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"[River2] feedback_loop/daily_summary.json 讀取失敗: {e}")

    # Doctor shared board（QA 報告）
    shared_board = system_dir / "doctor/shared_board.json"
    if shared_board.exists():
        try:
            data = json.loads(shared_board.read_text(encoding="utf-8"))
            observations.append({
                "river": "client_interaction",
                "timestamp": datetime.now().isoformat(),
                "type": "qa_report",
                "content": data,
                "severity": _infer_severity(data),
                "source": "doctor/shared_board.json",
            })
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"[River2] doctor/shared_board.json 讀取失敗: {e}")

    # awareness_log.jsonl（最近 50 條）
    awareness_log = workspace / "data/memory_v3/awareness_log.jsonl"
    if awareness_log.exists():
        try:
            lines = awareness_log.read_text(encoding="utf-8").strip().splitlines()
            recent = lines[-50:]  # 最近 50 條
            for line in recent:
                try:
                    entry = json.loads(line)
                    observations.append({
                        "river": "client_interaction",
                        "timestamp": entry.get("timestamp", datetime.now().isoformat()),
                        "type": "awareness_log",
                        "content": entry,
                        "severity": entry.get("severity", "info"),
                        "source": "memory_v3/awareness_log.jsonl",
                    })
                except json.JSONDecodeError:
                    pass
        except OSError as e:
            logger.debug(f"[River2] awareness_log.jsonl 讀取失敗: {e}")

    logger.debug(f"[River2/Client] {len(observations)} 條觀察")
    return observations


# ── River 3：自我觀察 ────────────────────────────────────────────────────────

async def _collect_self_river(workspace: Path) -> list[dict]:
    """讀系統指標 + 耦合健康 + 接線完整性."""
    observations: list[dict] = []
    system_dir = workspace / "data/_system"

    # Skill health 檔案
    skill_health_dir = system_dir / "skill_health"
    if skill_health_dir.exists():
        for health_file in sorted(skill_health_dir.glob("*.json"))[-10:]:  # 最近 10 個
            try:
                data = json.loads(health_file.read_text(encoding="utf-8"))
                observations.append({
                    "river": "self_observation",
                    "timestamp": datetime.now().isoformat(),
                    "type": "skill_health",
                    "content": data,
                    "severity": _infer_severity(data),
                    "source": f"skill_health/{health_file.name}",
                })
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"[River3] skill_health/{health_file.name} 讀取失敗: {e}")

    # DendriticScorer health 記錄
    dendritic_log = system_dir / "doctor/dendritic_health.json"
    if dendritic_log.exists():
        try:
            data = json.loads(dendritic_log.read_text(encoding="utf-8"))
            observations.append({
                "river": "self_observation",
                "timestamp": datetime.now().isoformat(),
                "type": "dendritic_health",
                "content": data,
                "severity": _infer_severity(data),
                "source": "doctor/dendritic_health.json",
            })
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"[River3] dendritic_health.json 讀取失敗: {e}")

    # validate_connections.py 結果
    validate_script = workspace / "scripts/validate_connections.py"
    if validate_script.exists():
        try:
            result = subprocess.run(
                ["python", str(validate_script)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(workspace),
            )
            observations.append({
                "river": "self_observation",
                "timestamp": datetime.now().isoformat(),
                "type": "connection_validation",
                "content": {
                    "stdout": result.stdout[:2000],
                    "stderr": result.stderr[:500],
                    "returncode": result.returncode,
                },
                "severity": "error" if result.returncode != 0 else "info",
                "source": "scripts/validate_connections.py",
            })
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug(f"[River3] validate_connections.py 執行失敗: {e}")

    # evolution_velocity 記錄
    velocity_log = system_dir / "evolution/velocity_log.json"
    if velocity_log.exists():
        try:
            data = json.loads(velocity_log.read_text(encoding="utf-8"))
            observations.append({
                "river": "self_observation",
                "timestamp": datetime.now().isoformat(),
                "type": "evolution_velocity",
                "content": data,
                "severity": "info",
                "source": "evolution/velocity_log.json",
            })
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"[River3] velocity_log.json 讀取失敗: {e}")

    logger.debug(f"[River3/Self] {len(observations)} 條觀察")
    return observations


# ── River 4：外部探索 ────────────────────────────────────────────────────────

async def _collect_exploration_river(workspace: Path) -> list[dict]:
    """讀 PulseEngine 探索結果 + DigestEngine 成果."""
    observations: list[dict] = []
    system_dir = workspace / "data/_system"

    # exploration_cooldown.json
    cooldown_file = system_dir / "exploration_cooldown.json"
    if cooldown_file.exists():
        try:
            data = json.loads(cooldown_file.read_text(encoding="utf-8"))
            observations.append({
                "river": "external_exploration",
                "timestamp": datetime.now().isoformat(),
                "type": "exploration_cooldown",
                "content": data,
                "severity": "info",
                "source": "exploration_cooldown.json",
            })
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"[River4] exploration_cooldown.json 讀取失敗: {e}")

    # outward 目錄
    outward_dir = system_dir / "outward"
    if outward_dir.exists():
        for json_file in sorted(outward_dir.glob("*.json"))[-10:]:
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                observations.append({
                    "river": "external_exploration",
                    "timestamp": datetime.now().isoformat(),
                    "type": "outward_result",
                    "content": data,
                    "severity": "info",
                    "source": f"outward/{json_file.name}",
                })
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"[River4] outward/{json_file.name} 讀取失敗: {e}")

    # exploration_digest 目錄
    digest_dir = system_dir / "exploration_digest"
    if digest_dir.exists():
        for json_file in sorted(digest_dir.glob("*.json"))[-5:]:
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                observations.append({
                    "river": "external_exploration",
                    "timestamp": datetime.now().isoformat(),
                    "type": "digest_result",
                    "content": data,
                    "severity": "info",
                    "source": f"exploration_digest/{json_file.name}",
                })
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"[River4] exploration_digest/{json_file.name} 讀取失敗: {e}")

    logger.debug(f"[River4/Exploration] {len(observations)} 條觀察")
    return observations


# ── 工具函數 ─────────────────────────────────────────────────────────────────

def _infer_severity(data: Any) -> str:
    """從資料內容推斷嚴重程度."""
    if isinstance(data, dict):
        # 常見的嚴重程度欄位
        for key in ("severity", "level", "status", "health"):
            val = str(data.get(key, "")).lower()
            if val in ("critical", "error", "fail", "unhealthy"):
                return "error"
            if val in ("warning", "warn", "degraded"):
                return "warning"
    return "info"
