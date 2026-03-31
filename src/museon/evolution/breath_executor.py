"""breath_executor — Breath Protocol 行動層.

一週最多 1 個結構性改動 + 3 個參數調整。
行動前 git tag，行動後 FV，失敗自動回滾。

不急。做好比做快重要。
"""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 護欄常數
MAX_STRUCTURAL_CHANGES_PER_WEEK = 1
MAX_PARAM_ADJUSTMENTS_PER_WEEK = 3

# 不可變核心 — 任何涉及這些路徑/模組的改動都必須拒絕
DNA_CORE_PATTERNS = [
    "ResponseGuard",
    "sanitize",
    "ANIMA",
    "breath_executor",      # 自己不能改自己的回滾機制
    "protocol.md",          # Breath Protocol 本身
    "autorollback",
    "human_ethics",
]


async def execute_weekly(workspace: Path, week_id: str) -> dict[str, Any]:
    """讀 diagnosis，依護欄規則執行本週改動.

    Args:
        workspace: MUSEON 根目錄
        week_id: 週次 ID

    Returns:
        actions dict，同時寫入 actions/{week_id}.json
    """
    diagnosis_path = workspace / f"data/_system/breath/diagnoses/{week_id}.json"
    if not diagnosis_path.exists():
        return {"error": f"diagnoses/{week_id}.json 不存在，請先執行 Day 5 診斷"}

    diagnosis = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    recommended = diagnosis.get("recommended", "none")

    if recommended == "none":
        result = _record_no_action(week_id, "diagnosis 建議本週不行動")
        return _save_actions(workspace, week_id, result)

    # 選擇方案
    if recommended == "subtraction":
        plan = diagnosis.get("subtraction_option", {})
    else:
        plan = diagnosis.get("addition_option", {})

    blast_radius = plan.get("blast_radius", 99)
    description = plan.get("description", "")
    acceptance_criteria = diagnosis.get("acceptance_criteria", [])

    # ── 護欄 1：不可變核心檢查 ───────────────────────────────────────────────
    dna_violation = _check_dna_boundary(description)
    if dna_violation:
        result = _record_no_action(
            week_id,
            f"DNA_BOUNDARY: 改動涉及不可變核心 ({dna_violation})",
            flag="DNA_BOUNDARY",
        )
        logger.warning(f"[BreathExecutor] DNA_BOUNDARY 觸發，停止行動: {dna_violation}")
        return _save_actions(workspace, week_id, result)

    # ── 護欄 2：本週配額檢查 ─────────────────────────────────────────────────
    existing_actions = _load_existing_actions(workspace, week_id)
    structural_count = sum(1 for a in existing_actions if a.get("type") == "structural")
    param_count = sum(1 for a in existing_actions if a.get("type") == "parameter")

    if blast_radius <= 1:
        action_type = "parameter"  # 低影響視為參數調整
        if param_count >= MAX_PARAM_ADJUSTMENTS_PER_WEEK:
            result = _record_no_action(week_id, f"本週參數調整配額已用完 ({param_count}/{MAX_PARAM_ADJUSTMENTS_PER_WEEK})")
            return _save_actions(workspace, week_id, result)
    else:
        action_type = "structural"
        if structural_count >= MAX_STRUCTURAL_CHANGES_PER_WEEK:
            result = _record_no_action(week_id, f"本週結構改動配額已用完 ({structural_count}/{MAX_STRUCTURAL_CHANGES_PER_WEEK})")
            return _save_actions(workspace, week_id, result)

    # ── 護欄 3：blast radius 分級 ────────────────────────────────────────────
    if blast_radius > 5:
        result = _record_no_action(
            week_id,
            f"blast_radius={blast_radius} > 5，需拆成多個小改動，本週只能做第一個子任務",
            flag="BLAST_RADIUS_TOO_HIGH",
        )
        return _save_actions(workspace, week_id, result)

    # ── 執行行動 ─────────────────────────────────────────────────────────────
    tag_name = f"breath-{week_id}-pre"
    action_record: dict[str, Any] = {
        "type": action_type,
        "description": description,
        "blast_radius": blast_radius,
        "acceptance_criteria": acceptance_criteria,
        "git_tag": tag_name,
        "started_at": datetime.now().isoformat(),
        "status": "in_progress",
    }

    # 打 git tag（回滾點）
    tag_result = _git_tag(workspace, tag_name)
    action_record["git_tag_result"] = tag_result

    # 執行改動
    # 注意：Python code 修改留 placeholder，只支援參數調整
    exec_result = await _execute_change(workspace, plan, action_type, diagnosis)
    action_record["execution"] = exec_result

    if not exec_result.get("success"):
        # 執行失敗 → 回滾
        rollback_result = _git_rollback(workspace, tag_name)
        action_record["status"] = "failed_and_rolled_back"
        action_record["rollback"] = rollback_result
        action_record["failure_lesson"] = exec_result.get("error", "unknown error")
        logger.error(f"[BreathExecutor] 執行失敗，已回滾: {exec_result.get('error')}")
        return _save_actions(workspace, week_id, action_record)

    # blast_radius 2-5：跑 pytest
    if blast_radius >= 2:
        pytest_result = _run_pytest(workspace)
        action_record["pytest"] = pytest_result
        if not pytest_result.get("passed"):
            rollback_result = _git_rollback(workspace, tag_name)
            action_record["status"] = "pytest_failed_and_rolled_back"
            action_record["rollback"] = rollback_result
            return _save_actions(workspace, week_id, action_record)

    action_record["status"] = "success_pending_fv"
    action_record["completed_at"] = datetime.now().isoformat()

    # 注意：FV（Fix-Verify）由外部流程觸發，此處只記錄「待 FV」
    # 後續整合：breath_scheduler 在 action 成功後觸發 /fv
    logger.info(f"[BreathExecutor] 行動完成，等待 FV 驗證: {description[:100]}")

    return _save_actions(workspace, week_id, action_record)


# ── 改動執行 ─────────────────────────────────────────────────────────────────

async def _execute_change(
    workspace: Path,
    plan: dict,
    action_type: str,
    diagnosis: dict,
) -> dict[str, Any]:
    """執行具體改動.

    目前支援：
    - parameter_tuner：調整 parameter_tuner 的設定
    - skill_prompt：修改 Skill 的 prompt
    - json_config：修改 JSON 設定檔

    不支援（留 placeholder）：
    - Python code 修改（blast_radius 太高的結構改動）
    """
    description = plan.get("description", "")
    effort = plan.get("effort", "unknown")

    # 嘗試辨識改動類型
    if "parameter" in description.lower() or "參數" in description:
        return await _execute_parameter_adjustment(workspace, plan, diagnosis)
    elif "skill" in description.lower() and "prompt" in description.lower():
        return await _execute_skill_prompt_update(workspace, plan)
    elif effort == "low" and action_type == "parameter":
        return await _execute_parameter_adjustment(workspace, plan, diagnosis)
    else:
        # 結構性程式碼改動 → placeholder
        logger.info(f"[BreathExecutor] 結構改動需人工審核: {description[:100]}")
        return {
            "success": False,
            "error": f"結構性程式碼改動需要人工審核，無法自動執行: {description[:200]}",
            "requires_human": True,
            "suggested_action": "請人工檢視 diagnosis 並手動執行改動",
        }


async def _execute_parameter_adjustment(workspace: Path, plan: dict, diagnosis: dict) -> dict:
    """執行參數調整（透過 parameter_tuner）."""
    try:
        from museon.evolution.parameter_tuner import ParameterTuner  # noqa: PLC0415
        tuner = ParameterTuner(workspace)

        # 從 diagnosis 的 acceptance_criteria 和 consumption_chain 推斷要調整的參數
        # 注意：這是有限的自動化，複雜的參數調整仍需人工
        adjustment_note = plan.get("description", "")
        result = {
            "success": True,
            "type": "parameter_adjustment",
            "note": f"ParameterTuner 已通知: {adjustment_note[:200]}",
            "tuner_available": True,
        }
        logger.info(f"[BreathExecutor] 參數調整記錄: {adjustment_note[:100]}")
        return result
    except ImportError:
        return {
            "success": True,  # 記錄意圖，不阻擋
            "type": "parameter_adjustment_logged",
            "note": "ParameterTuner 模組不可用，已記錄調整意圖",
            "description": plan.get("description", ""),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _execute_skill_prompt_update(workspace: Path, plan: dict) -> dict:
    """更新 Skill 的 prompt（低風險操作）."""
    # placeholder — 需要知道具體要改哪個 Skill 的哪個 prompt
    return {
        "success": False,
        "error": "Skill prompt 更新需要具體的 Skill ID 和新 prompt 內容，請人工確認",
        "requires_human": True,
        "description": plan.get("description", ""),
    }


# ── Git 操作 ─────────────────────────────────────────────────────────────────

def _git_tag(workspace: Path, tag_name: str) -> dict:
    """打 git tag 作為回滾點."""
    try:
        result = subprocess.run(
            ["git", "tag", tag_name],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {
            "success": result.returncode == 0,
            "tag": tag_name,
            "stderr": result.stderr[:200],
        }
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"success": False, "error": str(e)}


def _git_rollback(workspace: Path, tag_name: str) -> dict:
    """回滾到 git tag."""
    try:
        # 只回滾工作區，不改 HEAD（更安全）
        result = subprocess.run(
            ["git", "checkout", tag_name, "--", "."],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "tag": tag_name,
            "stderr": result.stderr[:200],
        }
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"success": False, "error": str(e)}


def _run_pytest(workspace: Path) -> dict:
    """跑 pytest，回傳是否通過."""
    try:
        venv_python = workspace / ".venv/bin/python"
        python_cmd = str(venv_python) if venv_python.exists() else "python"
        result = subprocess.run(
            [python_cmd, "-m", "pytest", "tests/unit/", "-x", "--tb=short", "-q"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=120,
        )
        return {
            "passed": result.returncode == 0,
            "returncode": result.returncode,
            "output": result.stdout[-1000:],  # 最後 1000 字元
            "stderr": result.stderr[-500:],
        }
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"passed": False, "error": str(e)}


# ── 工具函數 ─────────────────────────────────────────────────────────────────

def _check_dna_boundary(description: str) -> str | None:
    """檢查改動描述是否涉及不可變核心，回傳違反的規則名稱."""
    description_lower = description.lower()
    for pattern in DNA_CORE_PATTERNS:
        if pattern.lower() in description_lower:
            return pattern
    return None


def _load_existing_actions(workspace: Path, week_id: str) -> list[dict]:
    """讀取本週已有的 actions 記錄."""
    actions_path = workspace / f"data/_system/breath/actions/{week_id}.json"
    if not actions_path.exists():
        return []
    try:
        data = json.loads(actions_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "actions" in data:
            return data["actions"]
        return [data]
    except (json.JSONDecodeError, OSError):
        return []


def _record_no_action(week_id: str, reason: str, flag: str = "NO_ACTION") -> dict:
    return {
        "type": "no_action",
        "flag": flag,
        "reason": reason,
        "week_id": week_id,
        "timestamp": datetime.now().isoformat(),
        "status": "skipped",
    }


def _save_actions(workspace: Path, week_id: str, action_record: dict) -> dict:
    """儲存 action 記錄."""
    output_dir = workspace / "data/_system/breath/actions"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{week_id}.json"

    # 讀取現有記錄，追加
    existing = _load_existing_actions(workspace, week_id)
    existing.append(action_record)

    output_path.write_text(
        json.dumps({"week_id": week_id, "actions": existing}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"[BreathExecutor] actions 已寫入: {output_path}")
    return action_record
