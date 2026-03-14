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

from museon.nightly.morphenix_standards import review_proposal

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Executor
# ═══════════════════════════════════════════


MAX_ROLLBACKS_PER_DAY = 3  # 每日回滾上限，超過則暫停 Morphenix


class MorphenixExecutor:
    """執行已核准的 Morphenix 演化提案.

    Args:
        workspace: MUSEON data 目錄（如 /Users/ZEALCHOU/MUSEON/data）
        source_root: MUSEON 原始碼根目錄（如 /Users/ZEALCHOU/museon）
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

        # 收集受影響的技能和 DNA27 變更
        all_affected_skills = []
        has_dna27_change = False
        for detail in results["details"]:
            affected = detail.get("affected_skills", [])
            all_affected_skills.extend(affected)
            # 偵測 DNA27 相關變更
            title = detail.get("title", "")
            files = detail.get("changed_files", [])
            if any("dna27" in s.lower() for s in [title] + files):
                has_dna27_change = True

        # 發布完成事件
        if self._event_bus and results["executed"] > 0:
            try:
                from museon.core.event_bus import MORPHENIX_EXECUTION_COMPLETED
                self._event_bus.publish(MORPHENIX_EXECUTION_COMPLETED, {
                    "executed": results["executed"],
                    "failed": results["failed"],
                    "details": results["details"],
                    "affected_skills": list(set(all_affected_skills)),
                    "timestamp": datetime.now(TZ8).isoformat(),
                })
            except Exception as e:
                logger.warning(f"Morphenix EventBus publish failed: {e}")

            # 註：MORPHENIX_EXECUTION_COMPLETED 已被 Telegram/SkillRouter 訂閱，
            # 不需要再發布冗餘的 MORPHENIX_EXECUTED。

            # DNA27 相關變更 → 額外發布權重更新事件
            if has_dna27_change:
                try:
                    from museon.core.event_bus import DNA27_WEIGHTS_UPDATED
                    self._event_bus.publish(DNA27_WEIGHTS_UPDATED, {
                        "trigger": "morphenix_execution",
                        "timestamp": datetime.now(TZ8).isoformat(),
                    })
                except Exception as e:
                    logger.debug(f"[MORPHENIX_EXECUTOR] morphenix failed (degraded): {e}")

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
                    from museon.core.event_bus import MORPHENIX_L3_PROPOSAL
                    self._event_bus.publish(MORPHENIX_L3_PROPOSAL, {
                        "proposals": [{
                            "id": pid,
                            "title": title,
                            "description": proposal.get("description", ""),
                            "escalation_reason": violations,
                        }],
                    })
                except Exception as e:
                    logger.debug(f"[MORPHENIX_EXECUTOR] PID check failed (degraded): {e}")

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

        # 安全檢查：今日回滾次數是否已達上限
        try:
            rollback_count = self._db.count_rollbacks_today()
            if rollback_count >= MAX_ROLLBACKS_PER_DAY:
                logger.error(
                    f"Morphenix Executor: daily rollback limit reached "
                    f"({rollback_count}/{MAX_ROLLBACKS_PER_DAY}), "
                    f"SUSPENDING execution of {pid}"
                )
                self._log_execution(pid, "suspended", error="daily_rollback_limit")
                self._notify_rollback_limit_reached(rollback_count)
                return {
                    "proposal_id": pid,
                    "outcome": "skipped",
                    "reason": f"daily_rollback_limit_reached ({rollback_count})",
                }
        except Exception:
            pass  # count_rollbacks_today 不存在不阻擋

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

        # Step 3.5: 即時驗證（L2+ 原始碼修改需要 pytest 驗證；PI 層級不涉及原始碼，跳過）
        if level in ("L2", "L3") and exec_result.get("count", 0) > 0:
            verify_result = self._post_apply_verify(proposal, exec_result)
            if not verify_result["passed"]:
                logger.error(
                    f"Morphenix Executor: POST-APPLY VERIFY FAILED for {pid}: "
                    f"{verify_result.get('reason', 'unknown')}"
                )
                rollback_ok = self._rollback_to_tag(tag_name, pid, "post_apply_verify_failed")
                self._log_execution(
                    pid, "rolled_back",
                    error=f"post_apply_verify_failed: {verify_result.get('reason', '')}",
                    result={"verify": verify_result, "rollback_success": rollback_ok},
                )
                return {
                    "proposal_id": pid,
                    "outcome": "failed",
                    "reason": "post_apply_verify_failed",
                    "verify_detail": verify_result,
                    "rollback_tag": tag_name,
                    "rollback_success": rollback_ok,
                }

        # Step 4: 標記為已執行
        try:
            self._db.mark_proposal_executed(pid)
        except Exception as e:
            logger.warning(f"Morphenix Executor: mark_executed failed: {e}")

        # Step 5: 記錄 + 效果追蹤 + 清理已執行的 notes
        self._log_execution(pid, "executed", result=exec_result)
        self._track_execution(proposal, exec_result, safety_tag=tag_name)
        self._cleanup_executed_notes(proposal)

        # Step 6: 結晶閉環 — 回寫來源結晶狀態 + 演化結晶
        self._close_crystal_loop(proposal, exec_result, pid)

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
        """在 MUSEON 原始碼 repo 建立 git tag 安全快照.

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
        elif level in ("PI-1", "PI-2", "PI-3"):
            return self._apply_pi(proposal, metadata, level)
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

    def _apply_pi(
        self, proposal: Dict[str, Any], metadata: Dict, level: str,
    ) -> Dict[str, Any]:
        """PI-1/PI-2/PI-3 Pulse Intervention 變更.

        PI-1（觀察介入）：觸發 PulseObserver 生成觀察報告（純讀取）
        PI-2（參數熱更新）：寫入 pulse_config.json 修改 Pulse 常數
        PI-3（行為注入）：透過 PulseBehaviorInjector 注入新規則（需通過品質門禁）
        """
        pid = proposal.get("id", "unknown")

        if level == "PI-1":
            return self._apply_pi1(proposal, metadata)
        elif level == "PI-2":
            return self._apply_pi2(proposal, metadata)
        elif level == "PI-3":
            return self._apply_pi3(proposal, metadata)
        else:
            return {"action": "unknown_pi_level", "level": level}

    def _apply_pi1(
        self, proposal: Dict[str, Any], metadata: Dict,
    ) -> Dict[str, Any]:
        """PI-1：觀察介入 — 產出 Pulse 行為觀察報告."""
        try:
            from museon.pulse.pulse_intervention import PulseObserver
            observer = PulseObserver(str(self._workspace))
            days = metadata.get("observation_days", 7)
            report = observer.generate_observation_report(days=days)
            logger.info(f"PI-1 observation report generated: {report.get('status', '?')}")
            return {
                "action": "pi1_observation",
                "report": report,
                "count": 1,
            }
        except Exception as e:
            logger.error(f"PI-1 observation failed: {e}")
            return {"action": "pi1_observation", "error": str(e), "count": 0}

    def _apply_pi2(
        self, proposal: Dict[str, Any], metadata: Dict,
    ) -> Dict[str, Any]:
        """PI-2：參數熱更新 — 修改 pulse_config.json."""
        try:
            from museon.pulse.pulse_intervention import update_config, init_config
            # 確保 config 已初始化
            init_config(str(self._workspace))

            config_changes = metadata.get("config_changes", [])
            applied = []
            for change in config_changes:
                section = change.get("section", "")
                key = change.get("key", "")
                value = change.get("value")
                if not section or not key or value is None:
                    continue
                ok = update_config(
                    section, key, value,
                    modified_by=f"morphenix_{proposal.get('id', 'unknown')}",
                )
                if ok:
                    applied.append({"section": section, "key": key, "value": value})
                    logger.info(f"PI-2 config updated: {section}.{key} = {value}")
                else:
                    logger.warning(f"PI-2 config rejected: {section}.{key}")

            return {
                "action": "pi2_config_update",
                "applied": applied,
                "count": len(applied),
            }
        except Exception as e:
            logger.error(f"PI-2 config update failed: {e}")
            return {"action": "pi2_config_update", "error": str(e), "count": 0}

    def _apply_pi3(
        self, proposal: Dict[str, Any], metadata: Dict,
    ) -> Dict[str, Any]:
        """PI-3：行為注入 — 透過品質門禁後注入新規則."""
        try:
            from museon.pulse.pulse_intervention import PulseBehaviorInjector
            injector = PulseBehaviorInjector(str(self._workspace))

            rules = metadata.get("rules", [])
            injected = []
            rejected = []
            for rule in rules:
                result = injector.inject_rule(rule, proposal)
                if result.get("success"):
                    injected.append({
                        "rule_id": result.get("rule_id", ""),
                        "expires_at": result.get("expires_at", ""),
                    })
                else:
                    rejected.append({
                        "rule_id": rule.get("id", ""),
                        "reason": result.get("reason", ""),
                    })

            return {
                "action": "pi3_behavior_injection",
                "injected": injected,
                "rejected": rejected,
                "count": len(injected),
            }
        except Exception as e:
            logger.error(f"PI-3 behavior injection failed: {e}")
            return {"action": "pi3_behavior_injection", "error": str(e), "count": 0}

    # ═══════════════════════════════════════════
    # 即時驗證 + 回滾
    # ═══════════════════════════════════════════

    def _post_apply_verify(
        self, proposal: Dict[str, Any], exec_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """在 apply 後跑受影響模組的 unit test（快速驗證）.

        Returns:
            {"passed": bool, "reason": str, "output": str}
        """
        # 收集受影響的檔案路徑
        affected_files = []
        for item in exec_result.get("applied", []):
            f = item.get("file", "")
            if f:
                affected_files.append(f)

        # 如果有 patch 但沒有具體檔案清單 → 跑全部 unit test
        if not affected_files and exec_result.get("action") == "l2_logic_patch":
            affected_files = ["src/"]

        # 推導對應的 test 路徑
        test_targets = self._infer_test_targets(affected_files)
        if not test_targets:
            # 找不到對應測試 → 跑全部 unit test
            test_targets = ["tests/unit/"]

        # 跑 pytest
        test_paths = []
        for t in test_targets:
            full = self._source_root / t
            if full.exists():
                test_paths.append(str(full))

        if not test_paths:
            # 沒有測試檔案可跑 → 通過（保守策略）
            return {"passed": True, "reason": "no_test_files_found"}

        try:
            import sys as _sys
            result = subprocess.run(
                [_sys.executable, "-m", "pytest"] + test_paths + [
                    "-x", "--tb=short", "-q", "--no-header",
                ],
                capture_output=True, text=True,
                cwd=str(self._source_root),
                timeout=120,
            )
            output = (result.stdout + result.stderr)[-2000:]

            if result.returncode == 0:
                logger.info(f"Morphenix post-apply verify: PASSED ({test_paths})")
                return {"passed": True, "reason": "pytest_passed", "output": output}
            else:
                logger.warning(
                    f"Morphenix post-apply verify: FAILED (rc={result.returncode})"
                )
                return {
                    "passed": False,
                    "reason": f"pytest_failed_rc{result.returncode}",
                    "output": output,
                }
        except subprocess.TimeoutExpired:
            return {"passed": False, "reason": "pytest_timeout", "output": ""}
        except Exception as e:
            logger.warning(f"Morphenix post-apply verify error: {e}")
            return {"passed": False, "reason": f"verify_error: {str(e)[:200]}"}

    def _infer_test_targets(self, affected_files: List[str]) -> List[str]:
        """從受影響的原始碼路徑推導對應的 test 路徑.

        例如：
          src/museon/nightly/foo.py → tests/unit/nightly/test_foo.py
          src/museon/core/bar.py   → tests/unit/core/test_bar.py
        """
        targets = set()
        for filepath in affected_files:
            # 正規化：移除前綴
            fp = filepath.replace("\\", "/")
            if fp.startswith("src/museon/"):
                relative = fp[len("src/museon/"):]  # e.g. "nightly/foo.py"
                parts = relative.rsplit("/", 1)
                if len(parts) == 2:
                    dirname, filename = parts
                    test_file = f"tests/unit/{dirname}/test_{filename}"
                    targets.add(test_file)
                    # 也嘗試整個子目錄
                    targets.add(f"tests/unit/{dirname}/")
                else:
                    test_file = f"tests/unit/test_{parts[0]}"
                    targets.add(test_file)
            elif fp.startswith("src/"):
                targets.add("tests/unit/")
        return list(targets)

    def _rollback_to_tag(
        self, tag_name: str, proposal_id: str, reason: str = "",
    ) -> bool:
        """回滾到 git tag 安全快照.

        Returns:
            True 如果回滾成功
        """
        if tag_name.startswith(("no-git-", "tag-failed-", "snapshot-error-")):
            logger.warning(
                f"Morphenix rollback: cannot rollback, tag is placeholder: {tag_name}"
            )
            return False

        try:
            # git checkout {tag} -- .
            result = subprocess.run(
                ["git", "checkout", tag_name, "--", "."],
                capture_output=True, text=True,
                cwd=str(self._source_root),
                timeout=30,
            )
            if result.returncode != 0:
                logger.error(
                    f"Morphenix rollback FAILED: {result.stderr[:300]}"
                )
                return False

            logger.info(
                f"Morphenix rollback SUCCESS: restored to {tag_name} "
                f"for proposal {proposal_id}"
            )

            # 記錄回滾到 PulseDB（不可刪除的審計軌跡）
            try:
                self._db.log_rollback(proposal_id, reason, tag_name)
                self._db.mark_proposal_rolled_back(proposal_id, reason)
            except Exception as e:
                logger.warning(f"Morphenix rollback DB log failed: {e}")

            # 發布回滾事件
            if self._event_bus:
                try:
                    from museon.core.event_bus import MORPHENIX_ROLLBACK
                    self._event_bus.publish(MORPHENIX_ROLLBACK, {
                        "proposal_id": proposal_id,
                        "tag_name": tag_name,
                        "reason": reason,
                        "timestamp": datetime.now(TZ8).isoformat(),
                    })
                except Exception as e:
                    logger.debug(f"[MORPHENIX_EXECUTOR] morphenix failed (degraded): {e}")

            return True

        except Exception as e:
            logger.error(f"Morphenix rollback error: {e}", exc_info=True)
            return False

    def _notify_rollback_limit_reached(self, count: int) -> None:
        """每日回滾上限到達 → Telegram 通知人類."""
        if self._event_bus:
            try:
                from museon.core.event_bus import MORPHENIX_ROLLBACK
                self._event_bus.publish(MORPHENIX_ROLLBACK, {
                    "type": "daily_limit_reached",
                    "rollback_count": count,
                    "max_allowed": MAX_ROLLBACKS_PER_DAY,
                    "action": "morphenix_suspended",
                    "timestamp": datetime.now(TZ8).isoformat(),
                })
            except Exception as e:
                logger.debug(f"[MORPHENIX_EXECUTOR] morphenix failed (degraded): {e}")

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

    # ═══════════════════════════════════════════
    # 14 天效果追蹤
    # ═══════════════════════════════════════════

    EFFECT_TRACKING_DAYS = 14
    COOLDOWN_DAYS = 14

    def evaluate_effects(self) -> Dict[str, Any]:
        """評估已執行提案的 14 天效果.

        掃描 execution_log，找出 14 天前執行的提案，
        比對執行前後的系統健康指標，判斷提案是否有效。

        由 NightlyPipeline step 5.10 呼叫。

        Returns:
            {
                "evaluated": int,
                "effective": int,
                "ineffective": int,
                "details": [...]
            }
        """
        tracker_file = self._log_dir / "effect_tracker.json"
        tracker = self._load_tracker(tracker_file)

        now = datetime.now(TZ8)
        results = {"evaluated": 0, "effective": 0, "ineffective": 0, "details": []}

        for pid, entry in list(tracker.items()):
            if entry.get("evaluated"):
                continue

            executed_at = datetime.fromisoformat(entry["executed_at"])
            days_elapsed = (now - executed_at).days

            if days_elapsed < self.EFFECT_TRACKING_DAYS:
                continue

            # 14 天到期 — 評估效果
            evaluation = self._evaluate_one_effect(pid, entry)
            entry["evaluated"] = True
            entry["evaluation"] = evaluation
            entry["evaluated_at"] = now.isoformat()

            results["evaluated"] += 1
            if evaluation.get("effective"):
                results["effective"] += 1
            else:
                results["ineffective"] += 1
            results["details"].append({
                "proposal_id": pid,
                "title": entry.get("title", ""),
                **evaluation,
            })

        self._save_tracker(tracker_file, tracker)

        if results["evaluated"] > 0:
            logger.info(
                f"Morphenix 效果評估: {results['effective']}/{results['evaluated']} 有效"
            )

        return results

    def _track_execution(
        self, proposal: Dict[str, Any], exec_result: Dict,
        safety_tag: str = "",
    ) -> None:
        """記錄提案執行資訊，供 14 天後效果評估."""
        tracker_file = self._log_dir / "effect_tracker.json"
        tracker = self._load_tracker(tracker_file)

        pid = proposal.get("id", "unknown")
        tracker[pid] = {
            "title": proposal.get("title", ""),
            "level": proposal.get("level", "L1"),
            "description": proposal.get("description", "")[:200],
            "executed_at": datetime.now(TZ8).isoformat(),
            "safety_tag": safety_tag,
            "exec_result": {
                "action": exec_result.get("action", ""),
                "count": exec_result.get("count", 0),
            },
            "evaluated": False,
        }

        self._save_tracker(tracker_file, tracker)

    # Q-Score 退化閾值
    QSCORE_REGRESSION_THRESHOLD = -0.1
    MAX_POST_FAILURES = 2

    def _evaluate_one_effect(
        self, pid: str, entry: Dict[str, Any]
    ) -> Dict[str, Any]:
        """評估單一提案的效果（多維指標）.

        維度：
        1. 執行後 14 天是否有 failed 提案（原有邏輯）
        2. Q-Score 趨勢：比對執行前後 7 天的 Q-Score 平均值
        3. 若退化明顯 → 自動回滾 + Telegram 通知
        """
        executed_at = datetime.fromisoformat(entry["executed_at"])

        # ── 維度 1：execution_log failure count ──
        failure_count = 0
        for day_offset in range(self.EFFECT_TRACKING_DAYS):
            check_date = (executed_at + timedelta(days=day_offset + 1)).strftime("%Y-%m-%d")
            log_file = self._log_dir / f"exec_{check_date}.jsonl"
            if log_file.exists():
                try:
                    for line in log_file.read_text(encoding="utf-8").splitlines():
                        record = json.loads(line)
                        if record.get("outcome") == "failed":
                            failure_count += 1
                except Exception as e:
                    logger.debug(f"[MORPHENIX_EXECUTOR] JSON failed (degraded): {e}")

        # ── 維度 2：Q-Score 趨勢比較 ──
        qscore_delta = 0.0
        qscore_before = None
        qscore_after = None
        try:
            qscore_before = self._get_qscore_average(
                executed_at - timedelta(days=7), executed_at,
            )
            qscore_after = self._get_qscore_average(
                executed_at, executed_at + timedelta(days=self.EFFECT_TRACKING_DAYS),
            )
            if qscore_before is not None and qscore_after is not None:
                qscore_delta = qscore_after - qscore_before
        except Exception as e:
            logger.debug(f"Q-Score trend check skipped: {e}")

        # ── 判定：是否需要延遲回滾 ──
        needs_rollback = False
        rollback_reason = ""

        if failure_count > self.MAX_POST_FAILURES:
            needs_rollback = True
            rollback_reason = f"post_failures={failure_count}"

        if qscore_delta < self.QSCORE_REGRESSION_THRESHOLD:
            needs_rollback = True
            rollback_reason += (
                f"{' + ' if rollback_reason else ''}"
                f"qscore_regression={qscore_delta:.3f}"
            )

        effective = not needs_rollback

        # 如果需要延遲回滾
        if needs_rollback:
            tag_name = entry.get("safety_tag", "")
            if not tag_name:
                # 嘗試從 execution_log 找 tag
                tag_name = self._find_safety_tag(pid)

            if tag_name:
                logger.warning(
                    f"Morphenix 延遲回滾: {pid} — {rollback_reason}, "
                    f"rolling back to {tag_name}"
                )
                rollback_ok = self._rollback_to_tag(
                    tag_name, pid, f"delayed_rollback: {rollback_reason}",
                )
            else:
                rollback_ok = False
                logger.warning(
                    f"Morphenix 延遲回滾: {pid} — {rollback_reason}, "
                    f"but no safety tag found, cannot rollback"
                )
        else:
            rollback_ok = None

        return {
            "effective": effective,
            "days_tracked": self.EFFECT_TRACKING_DAYS,
            "post_failures": failure_count,
            "qscore_before": qscore_before,
            "qscore_after": qscore_after,
            "qscore_delta": round(qscore_delta, 4) if qscore_delta else 0,
            "rollback_triggered": needs_rollback,
            "rollback_success": rollback_ok,
            "verdict": (
                "有效 — 指標穩定" if effective
                else f"退化回滾 — {rollback_reason}"
            ),
        }

    def _get_qscore_average(
        self, start: datetime, end: datetime,
    ) -> Optional[float]:
        """從 q_scores.jsonl 取得期間內的 Q-Score 平均值."""
        # 實際路徑: data/eval/q_scores.jsonl (JSONL 格式)
        qscore_file = self._workspace / "eval" / "q_scores.jsonl"
        if not qscore_file.exists():
            return None

        scores = []
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")

        try:
            for line in qscore_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    ts = record.get("timestamp", "")
                    date_part = ts[:10] if len(ts) >= 10 else ""
                    if start_str <= date_part <= end_str:
                        qs = record.get("score")
                        if qs is not None:
                            scores.append(float(qs))
                except Exception:
                    continue
        except Exception:
            return None

        return sum(scores) / len(scores) if scores else None

    def _find_safety_tag(self, proposal_id: str) -> Optional[str]:
        """從 effect_tracker 或 git tags 中尋找提案的 safety tag."""
        # 1. 先從 effect_tracker 讀取（主要來源）
        try:
            tracker_file = self._log_dir / "effect_tracker.json"
            tracker = self._load_tracker(tracker_file)
            entry = tracker.get(proposal_id, {})
            tag = entry.get("safety_tag", "")
            if tag:
                return tag
        except Exception as e:
            logger.debug(f"[MORPHENIX_EXECUTOR] operation failed (degraded): {e}")

        # 2. 從 execution_log 的 result 中搜尋
        try:
            for log_file in sorted(self._log_dir.glob("exec_*.jsonl"), reverse=True):
                for line in log_file.read_text(encoding="utf-8").splitlines():
                    try:
                        record = json.loads(line)
                        if (record.get("proposal_id") == proposal_id
                                and record.get("outcome") == "executed"):
                            result = record.get("result", {})
                            tag = result.get("safety_tag", "")
                            if tag:
                                return tag
                    except Exception as e:
                        logger.debug(f"[MORPHENIX_EXECUTOR] JSON failed (degraded): {e}")
        except Exception as e:
            logger.debug(f"[MORPHENIX_EXECUTOR] JSON failed (degraded): {e}")

        # 嘗試從 git tags 搜尋
        try:
            result = subprocess.run(
                ["git", "tag", "-l", f"morphenix/pre-{proposal_id}-*"],
                capture_output=True, text=True,
                cwd=str(self._source_root),
                timeout=10,
            )
            tags = result.stdout.strip().splitlines()
            if tags:
                return tags[-1]  # 最新的 tag
        except Exception as e:
            logger.debug(f"[MORPHENIX_EXECUTOR] morphenix failed (degraded): {e}")

        return None

    def _load_tracker(self, path: Path) -> Dict:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.debug(f"[MORPHENIX_EXECUTOR] JSON failed (degraded): {e}")
        return {}

    def _save_tracker(self, path: Path, data: Dict) -> None:
        try:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Morphenix effect tracker save failed: {e}")

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

    # ═══════════════════════════════════════════
    # P0: 結晶閉環 — 回寫來源結晶狀態
    # P1: 演化結晶水源 — 將提案執行結果結晶化
    # ═══════════════════════════════════════════

    def _close_crystal_loop(
        self, proposal: Dict[str, Any], exec_result: Dict[str, Any], pid: str,
    ) -> None:
        """結晶閉環：回寫來源結晶狀態 + 將演化結果結晶化.

        P0: 當提案來自 knowledge_lattice_downgrade 時，
            回寫對應結晶的狀態（重置 counter_evidence / 標記 addressed）。

        P1: 將演化提案執行結果本身結晶化為 Lesson/Pattern，
            origin='morphenix_evolution'，形成「演化產出知識」的水源。
        """
        try:
            lattice = self._get_knowledge_lattice()
            if not lattice:
                return

            # ── P0: 回寫來源結晶狀態 ──
            source = proposal.get("source", "")
            if source == "knowledge_lattice_downgrade":
                self._writeback_crystal_status(proposal, lattice)

            # ── P1: 演化結果結晶化 ──
            count = exec_result.get("count", 0)
            if count > 0:
                self._crystallize_evolution_result(proposal, exec_result, pid, lattice)

        except Exception as e:
            logger.warning(f"Morphenix crystal loop error: {e}")

    def _writeback_crystal_status(
        self, proposal: Dict[str, Any], lattice: Any,
    ) -> None:
        """P0: 回寫被修正的結晶狀態."""
        try:
            metadata = proposal.get("metadata", "{}")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}

            downgraded_cuids = metadata.get("downgraded_cuids", [])
            if not downgraded_cuids:
                # 嘗試從 metric 取得
                metric = proposal.get("metric", {})
                if isinstance(metric, str):
                    try:
                        metric = json.loads(metric)
                    except Exception:
                        metric = {}
                downgraded_cuids = metric.get("cuids", [])

            for cuid in downgraded_cuids:
                crystal = lattice.get_crystal(cuid)
                if crystal:
                    crystal.counter_evidence_count = 0
                    crystal.status = "active"
                    crystal.updated_at = datetime.now(TZ8).isoformat()
                    logger.info(
                        f"Crystal 閉環回寫: {cuid} counter_evidence 重置, "
                        f"status='active'"
                    )

            if downgraded_cuids:
                lattice._persist()
                logger.info(
                    f"P0 結晶回寫完成: {len(downgraded_cuids)} 顆結晶狀態已更新"
                )
        except Exception as e:
            logger.warning(f"Crystal writeback error: {e}")

    def _crystallize_evolution_result(
        self, proposal: Dict[str, Any], exec_result: Dict[str, Any],
        pid: str, lattice: Any,
    ) -> None:
        """P1: 將演化提案執行結果結晶化為 Lesson."""
        try:
            level = proposal.get("level", "L1")
            title = proposal.get("title", "")
            desc = proposal.get("description", "")[:200]
            action = exec_result.get("action", "")
            count = exec_result.get("count", 0)

            # 構建結晶素材
            raw = (
                f"Morphenix {level} 演化提案「{title}」執行成功。"
                f"動作: {action}, 變更數: {count}。"
                f"描述: {desc}"
            )

            crystal = lattice.crystallize(
                raw_material=raw,
                source_context=f"morphenix_evolution:{pid}",
                crystal_type="Lesson",
                g1_summary=f"演化 {level}：{title[:25]}",
                g2_structure=[f"層級: {level}", f"動作: {action}", f"變更: {count}"],
                g3_root_inquiry="此次演化解決了什麼根本問題？",
                g4_insights=[desc[:100]] if desc else [],
                assumption=f"{level} 變更預期改善系統行為",
                evidence=f"成功執行 {count} 項變更",
                limitation="需 14 天效果追蹤確認",
                tags=["morphenix", level.lower(), "evolution"],
                domain="system_evolution",
                mode="auto",
            )
            crystal.origin = "morphenix_evolution"
            lattice._persist()

            logger.info(
                f"P1 演化結晶: {crystal.cuid} ← 提案 {pid}"
            )

        except Exception as e:
            logger.warning(f"Evolution crystallize error: {e}")

    def _get_knowledge_lattice(self) -> Optional[Any]:
        """取得 KnowledgeLattice 實例."""
        try:
            from museon.agent.knowledge_lattice import KnowledgeLattice
            lattice_dir = self._workspace / "lattice"
            if lattice_dir.exists():
                return KnowledgeLattice(workspace=self._workspace)
        except Exception as e:
            logger.debug(f"KnowledgeLattice not available: {e}")
        return None
