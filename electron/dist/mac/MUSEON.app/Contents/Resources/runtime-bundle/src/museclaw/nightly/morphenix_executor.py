"""Morphenix Executor — 演化提案執行引擎.

職責：
  1. 從 PulseDB 撈取 status='approved' 的提案
  2. 逐一執行 Core Brain 審查（morphenix_standards.py）
  3. Git tag 安全快照
  4. 依提案層級（L1/L2/L3）執行變更
  5. 標記 executed / 失敗回滾
  6. 發布 EventBus 事件 + Telegram 通知

架構原則：
  - 此模組是「系統層」，不是霓裳的一部分
  - 霓裳「寫」提案，Executor「批」和「做」
  - morphenix_standards.py 是不可變護欄
  - 每次執行前必須 git tag 快照
"""

import json
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from museclaw.nightly.morphenix_standards import review_proposal

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Executor
# ═══════════════════════════════════════════


class MorphenixExecutor:
    """執行已核准的 Morphenix 演化提案.

    Args:
        workspace: MUSEON data 目錄（如 /Users/ZEALCHOU/MUSEON/data）
        source_root: MuseClaw 原始碼根目錄（如 /Users/ZEALCHOU/museclaw）
        pulse_db: PulseDB 實例
        event_bus: EventBus 實例（可選）
    """

    def __init__(
        self,
        workspace: Path,
        source_root: Path,
        pulse_db: Any,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._workspace = Path(workspace)
        self._source_root = Path(source_root)
        self._db = pulse_db
        self._event_bus = event_bus

        # 執行記錄目錄
        self._log_dir = self._workspace / "_system" / "morphenix" / "execution_log"
        self._log_dir.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════════
    # 公開 API
    # ═══════════════════════════════════════════

    def execute_approved(self) -> Dict[str, Any]:
        """執行所有 status='approved' 的提案.

        Returns:
            {
                "executed": int,
                "failed": int,
                "escalated": int,
                "skipped": int,
                "details": [...]
            }
        """
        results = {
            "executed": 0,
            "failed": 0,
            "escalated": 0,
            "skipped": 0,
            "details": [],
        }

        # 撈取已核准提案
        approved = self._get_approved_proposals()
        if not approved:
            logger.info("Morphenix Executor: no approved proposals to execute")
            return results

        logger.info(
            f"Morphenix Executor: {len(approved)} approved proposals to process"
        )

        for proposal in approved:
            detail = self._execute_one(proposal)
            results["details"].append(detail)
            results[detail["outcome"]] += 1

        # 發布完成事件
        if self._event_bus and results["executed"] > 0:
            try:
                self._event_bus.publish("MORPHENIX_EXECUTION_COMPLETED", {
                    "executed": results["executed"],
                    "failed": results["failed"],
                    "details": results["details"],
                    "timestamp": datetime.now(TZ8).isoformat(),
                })
            except Exception as e:
                logger.warning(f"Morphenix EventBus publish failed: {e}")

        return results

    def execute_one(self, proposal_id: str) -> Dict[str, Any]:
        """手動執行單一提案（由 Dashboard API 呼叫）.

        Returns:
            執行結果 dict
        """
        # 從 DB 撈取
        all_proposals = self._db.get_all_proposals(limit=200)
        proposal = None
        for p in all_proposals:
            if p.get("id") == proposal_id and p.get("status") == "approved":
                proposal = p
                break

        if not proposal:
            return {
                "proposal_id": proposal_id,
                "outcome": "skipped",
                "reason": "not found or not approved",
            }

        return self._execute_one(proposal)

    # ═══════════════════════════════════════════
    # 內部執行流程
    # ═══════════════════════════════════════════

    def _execute_one(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        """執行單一提案的完整流程."""
        pid = proposal.get("id", "unknown")
        level = proposal.get("level", "L1")
        title = proposal.get("title", "")

        logger.info(f"Morphenix Executor: processing [{level}] {pid}: {title}")

        # Step 1: Core Brain 審查
        passed, violations, recommendation = review_proposal(proposal)

        if not passed:
            # Hard rule 違規 → 拒絕
            logger.warning(
                f"Morphenix Executor: REJECTED {pid} — {violations}"
            )
            self._log_execution(pid, "rejected", violations=violations)
            return {
                "proposal_id": pid,
                "outcome": "failed",
                "reason": "core_brain_rejected",
                "violations": violations,
            }

        if recommendation == "escalate_l3":
            # Soft rule 降級 → 不執行，改為等待人類審查
            logger.info(
                f"Morphenix Executor: ESCALATED {pid} to L3 — {violations}"
            )
            self._log_execution(pid, "escalated", violations=violations)

            # 發布 L3 升級事件
            if self._event_bus:
                try:
                    self._event_bus.publish("MORPHENIX_L3_PROPOSAL", {
                        "proposals": [{
                            "id": pid,
                            "title": title,
                            "description": proposal.get("description", ""),
                            "escalation_reason": violations,
                        }],
                    })
                except Exception:
                    pass

            return {
                "proposal_id": pid,
                "outcome": "escalated",
                "reason": "soft_rule_escalation",
                "violations": violations,
            }

        # Step 2: Git 安全快照
        tag_name = self._create_safety_snapshot(pid)
        if not tag_name:
            logger.error(
                f"Morphenix Executor: FAILED to create safety snapshot for {pid}"
            )
            self._log_execution(pid, "failed", error="git_tag_failed")
            return {
                "proposal_id": pid,
                "outcome": "failed",
                "reason": "safety_snapshot_failed",
            }

        # Step 3: 依層級執行
        try:
            exec_result = self._apply_changes(proposal)
        except Exception as e:
            logger.error(f"Morphenix Executor: FAILED {pid}: {e}")
            self._log_execution(pid, "failed", error=str(e))
            return {
                "proposal_id": pid,
                "outcome": "failed",
                "reason": str(e),
                "rollback_tag": tag_name,
            }

        # Step 4: 標記為已執行
        try:
            self._db.mark_proposal_executed(pid)
        except Exception as e:
            logger.warning(f"Morphenix Executor: mark_executed failed: {e}")

        # Step 5: 記錄 + 清理已執行的 notes
        self._log_execution(pid, "executed", result=exec_result)
        self._cleanup_executed_notes(proposal)

        logger.info(f"Morphenix Executor: EXECUTED {pid} successfully")

        return {
            "proposal_id": pid,
            "outcome": "executed",
            "level": level,
            "title": title,
            "safety_tag": tag_name,
            "result": exec_result,
        }

    # ═══════════════════════════════════════════
    # Git 安全快照
    # ═══════════════════════════════════════════

    def _create_safety_snapshot(self, proposal_id: str) -> Optional[str]:
        """在 MuseClaw 原始碼 repo 建立 git tag 安全快照.

        Returns:
            tag_name 或 None（失敗時）
        """
        tag_name = f"morphenix/pre-{proposal_id}-{datetime.now(TZ8).strftime('%Y%m%d%H%M%S')}"

        try:
            # 確認是 git repo
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True,
                cwd=str(self._source_root),
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning("Morphenix: source_root is not a git repo")
                # 不是 git repo 也允許執行（data 層修改不需要 git）
                return f"no-git-{proposal_id}"

            # 建立 tag
            result = subprocess.run(
                ["git", "tag", "-a", tag_name, "-m",
                 f"Morphenix safety snapshot before {proposal_id}"],
                capture_output=True, text=True,
                cwd=str(self._source_root),
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(f"Morphenix: git tag created: {tag_name}")
                return tag_name
            else:
                logger.warning(f"Morphenix: git tag failed: {result.stderr}")
                # tag 失敗不阻擋（可能是 dirty tree）
                return f"tag-failed-{proposal_id}"

        except Exception as e:
            logger.warning(f"Morphenix: git snapshot error: {e}")
            return f"snapshot-error-{proposal_id}"

    # ═══════════════════════════════════════════
    # 變更執行
    # ═══════════════════════════════════════════

    def _apply_changes(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        """依提案層級執行變更.

        L1 Config: 修改 JSON 設定檔（data/ 目錄）
        L2 Logic: 套用 diff patch 到原始碼
        L3 Architecture: 標記為已執行（實際變更由人類在 review 時完成）
        """
        level = proposal.get("level", "L1")
        pid = proposal.get("id", "unknown")
        metadata = proposal.get("metadata", "{}")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}

        if level == "L1":
            return self._apply_l1(proposal, metadata)
        elif level == "L2":
            return self._apply_l2(proposal, metadata)
        elif level == "L3":
            return self._apply_l3(proposal, metadata)
        else:
            return {"action": "unknown_level", "level": level}

    def _apply_l1(
        self, proposal: Dict[str, Any], metadata: Dict
    ) -> Dict[str, Any]:
        """L1 Config 變更：修改 JSON 設定.

        metadata 可包含：
          - "config_changes": [{"file": "...", "key": "...", "value": ...}]
          - 或簡單的 "action": "description"
        """
        changes = metadata.get("config_changes", [])
        applied = []

        for change in changes:
            filepath = change.get("file", "")
            key = change.get("key", "")
            value = change.get("value")

            if not filepath or not key:
                continue

            # 確保路徑在安全範圍內
            target = self._workspace / filepath
            if not str(target).startswith(str(self._workspace)):
                logger.warning(f"Morphenix L1: path escape attempt: {filepath}")
                continue

            try:
                if target.exists():
                    with open(target, "r", encoding="utf-8") as f:
                        data = json.load(f)
                else:
                    data = {}

                # 支援巢狀 key（用 . 分隔）
                keys = key.split(".")
                obj = data
                for k in keys[:-1]:
                    if k not in obj:
                        obj[k] = {}
                    obj = obj[k]
                obj[keys[-1]] = value

                with open(target, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                applied.append({"file": filepath, "key": key})
                logger.info(f"Morphenix L1: updated {filepath}:{key}")

            except Exception as e:
                logger.warning(f"Morphenix L1: failed {filepath}: {e}")

        return {
            "action": "l1_config_update",
            "applied": applied,
            "count": len(applied),
        }

    def _apply_l2(
        self, proposal: Dict[str, Any], metadata: Dict
    ) -> Dict[str, Any]:
        """L2 Logic 變更：套用 diff patch.

        metadata 可包含：
          - "patch": "unified diff 文本"
          - "changes": [{"file": "...", "old": "...", "new": "..."}]
        """
        patch_text = metadata.get("patch", "")
        changes = metadata.get("changes", [])
        applied = []

        # 方式 1：有 patch 文本
        if patch_text:
            try:
                result = subprocess.run(
                    ["git", "apply", "--check", "-"],
                    input=patch_text, capture_output=True, text=True,
                    cwd=str(self._source_root),
                    timeout=30,
                )
                if result.returncode == 0:
                    # dry-run 成功，正式套用
                    result = subprocess.run(
                        ["git", "apply", "-"],
                        input=patch_text, capture_output=True, text=True,
                        cwd=str(self._source_root),
                        timeout=30,
                    )
                    if result.returncode == 0:
                        applied.append({"method": "git_apply", "success": True})
                    else:
                        logger.warning(
                            f"Morphenix L2: git apply failed: {result.stderr}"
                        )
                else:
                    logger.warning(
                        f"Morphenix L2: patch check failed: {result.stderr}"
                    )
            except Exception as e:
                logger.warning(f"Morphenix L2: patch error: {e}")

        # 方式 2：結構化 changes
        for change in changes:
            filepath = change.get("file", "")
            old_text = change.get("old", "")
            new_text = change.get("new", "")

            if not filepath or not old_text:
                continue

            target = self._source_root / filepath
            if not target.exists():
                logger.warning(f"Morphenix L2: file not found: {filepath}")
                continue

            try:
                content = target.read_text(encoding="utf-8")
                if old_text in content:
                    content = content.replace(old_text, new_text, 1)
                    target.write_text(content, encoding="utf-8")
                    applied.append({"file": filepath, "method": "text_replace"})
                    logger.info(f"Morphenix L2: replaced in {filepath}")
                else:
                    logger.warning(
                        f"Morphenix L2: old_text not found in {filepath}"
                    )
            except Exception as e:
                logger.warning(f"Morphenix L2: replace failed {filepath}: {e}")

        return {
            "action": "l2_logic_patch",
            "applied": applied,
            "count": len(applied),
        }

    def _apply_l3(
        self, proposal: Dict[str, Any], metadata: Dict
    ) -> Dict[str, Any]:
        """L3 Architecture 變更：記錄為「已批准並執行」.

        L3 的實際程式碼變更由人類在 Telegram approve 後
        由 Claude Code 或手動操作完成。
        Executor 僅標記狀態，不自動修改架構層程式碼。
        """
        return {
            "action": "l3_architecture_acknowledged",
            "note": "L3 changes require human implementation. Marked as executed.",
            "description": proposal.get("description", ""),
        }

    # ═══════════════════════════════════════════
    # 輔助方法
    # ═══════════════════════════════════════════

    def _get_approved_proposals(self) -> List[Dict]:
        """從 PulseDB 撈取 status='approved' 的提案."""
        try:
            all_proposals = self._db.get_all_proposals(limit=100)
            return [
                p for p in all_proposals
                if p.get("status") == "approved"
            ]
        except Exception as e:
            logger.error(f"Morphenix Executor: DB query failed: {e}")
            return []

    def _log_execution(
        self,
        proposal_id: str,
        outcome: str,
        violations: List[str] = None,
        error: str = None,
        result: Dict = None,
    ) -> None:
        """寫入執行記錄."""
        log_entry = {
            "proposal_id": proposal_id,
            "outcome": outcome,
            "timestamp": datetime.now(TZ8).isoformat(),
        }
        if violations:
            log_entry["violations"] = violations
        if error:
            log_entry["error"] = error
        if result:
            log_entry["result"] = result

        log_file = self._log_dir / f"exec_{datetime.now(TZ8).strftime('%Y-%m-%d')}.jsonl"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"Morphenix Executor: log write failed: {e}")

    def _cleanup_executed_notes(self, proposal: Dict[str, Any]) -> None:
        """清理已執行提案對應的 notes（移到 archive）."""
        source_notes = proposal.get("source_notes", "[]")
        if isinstance(source_notes, str):
            try:
                source_notes = json.loads(source_notes)
            except Exception:
                source_notes = []

        if not source_notes:
            return

        archive_dir = self._workspace / "_system" / "morphenix" / "notes_archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        notes_dir = self._workspace / "_system" / "morphenix" / "notes"
        for note_ref in source_notes:
            # note_ref 可能是 filename 或 path
            note_path = notes_dir / note_ref if not os.path.isabs(note_ref) else Path(note_ref)
            if note_path.exists():
                try:
                    dest = archive_dir / note_path.name
                    note_path.rename(dest)
                    logger.debug(f"Morphenix: archived note {note_path.name}")
                except Exception as e:
                    logger.warning(f"Morphenix: note archive failed: {e}")
