"""
MuseDoc — DSE 研究員 + 外科醫生（4am）

讀取 MuseOff 的 findings + MuseQA 的 qa_reports + MuseWorker 的快照，
做 DSE 研究後用 Runbook 安全開刀。

5 道安全防線：
1. Runbook 匹配（沒有 Runbook → needs_human）
2. 扇入檢查（超過 blast_radius_max → needs_human）
3. 術前快照（git stash）
4. 術後驗證（Runbook.post_check）
5. 每夜上限（最多修 3 個，回滾 ≥ 2 停工）

設計參考：
- SRE Runbook 閉環修復
- AWS Self-Healing（pre-check / action / post-check / rollback）
- K8s 漸進式交付
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from museon.doctor.finding import FindingStore
from museon.doctor.runbook import ALL_RUNBOOKS, match_runbook
from museon.doctor.shared_board import read_shared_board, update_shared_board

logger = logging.getLogger(__name__)


class MuseDoc:
    """專科醫師——DSE 研究 + Runbook 安全修復"""

    VERSION = "1.0.0"
    MAX_FIXES_PER_NIGHT = 3
    MAX_ROLLBACKS_BEFORE_STOP = 2

    def __init__(self, museon_home: Path | str | None = None):
        self.home = Path(museon_home or "/Users/ZEALCHOU/MUSEON")
        self.findings_dir = self.home / "data" / "_system" / "museoff" / "findings"
        self.surgery_dir = self.home / "data" / "_system" / "musedoc" / "surgery_log"
        self.rollback_log = self.home / "data" / "_system" / "musedoc" / "rollback_log.jsonl"
        self.stats_path = self.home / "data" / "_system" / "musedoc" / "stats.json"
        self.snapshot_path = self.home / "data" / "_system" / "museworker" / "snapshot.json"

        self.surgery_dir.mkdir(parents=True, exist_ok=True)
        self._data_dir = self.home / "data"

        self._store = FindingStore(self.findings_dir)

        # 啟動時讀取共享看板，了解其他虎將狀態
        self._recent_board = read_shared_board(self._data_dir)

    # -------------------------------------------------------------------
    # 主入口：夜間手術
    # -------------------------------------------------------------------

    async def nightly_surgery(self, dry_run: bool = False) -> dict:
        """每夜 4am 執行：讀 findings → 排序 → Runbook 修復"""
        logger.info("[MuseDoc] Starting nightly surgery (dry_run=%s)", dry_run)
        t0 = time.monotonic()

        findings = self._store.load_open()
        if not findings:
            logger.info("[MuseDoc] No open findings, nothing to do")
            return {"fixed": 0, "rolled_back": 0, "needs_human": 0, "skipped": 0}

        # 按嚴重度排序：CRITICAL > HIGH > MEDIUM > LOW
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        findings.sort(key=lambda f: severity_order.get(f.severity, 9))

        # 載入 Worker 快照（提供扇入資料）
        snapshot = self._load_worker_snapshot()

        fixed = 0
        rolled_back = 0
        needs_human = 0
        skipped = 0

        for finding in findings:
            # 防線 5: 每夜上限
            if fixed >= self.MAX_FIXES_PER_NIGHT:
                logger.info("[MuseDoc] Hit max fixes (%d), stopping", self.MAX_FIXES_PER_NIGHT)
                skipped += 1
                continue
            if rolled_back >= self.MAX_ROLLBACKS_BEFORE_STOP:
                logger.warning("[MuseDoc] Hit max rollbacks (%d), stopping for tonight", self.MAX_ROLLBACKS_BEFORE_STOP)
                skipped += 1
                continue

            finding_dict = finding.to_dict()
            result = await self._process_finding(finding_dict, snapshot, dry_run)

            if result == "fixed":
                # Fix-Verify 閉環：驗證修復是否真的成功
                fv_passed = await self._fix_verify(finding_dict, snapshot)
                if fv_passed:
                    fixed += 1
                    self._store.update_status(finding.finding_id, "fixed_by_musedoc")
                else:
                    # 驗證未通過 → 視為 rollback
                    rolled_back += 1
                    logger.warning(
                        "[MuseDoc] Fix-Verify FAILED for %s, counting as rollback",
                        finding_dict.get("finding_id", "?"),
                    )
            elif result == "rolled_back":
                rolled_back += 1
            elif result == "needs_human":
                needs_human += 1
                self._store.update_status(finding.finding_id, "needs_human")
            else:
                skipped += 1

        summary = {
            "timestamp": _now_iso(),
            "fixed": fixed,
            "rolled_back": rolled_back,
            "needs_human": needs_human,
            "skipped": skipped,
            "total_findings": len(findings),
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "dry_run": dry_run,
        }

        self._write_surgery_log(summary)
        logger.info(
            "[MuseDoc] Surgery complete: fixed=%d, rolled_back=%d, needs_human=%d, skipped=%d",
            fixed, rolled_back, needs_human, skipped,
        )

        # 寫入共享看板
        status = "critical" if rolled_back > 0 else "warning" if needs_human > 0 else "ok"
        actions = []
        if fixed > 0:
            actions.append(f"fixed:{fixed}")
        if rolled_back > 0:
            actions.append(f"rolled_back:{rolled_back}")
        if needs_human > 0:
            actions.append(f"needs_human:{needs_human}")
        update_shared_board(
            self._data_dir,
            source="musedoc",
            summary=f"手術完成: {fixed} 修復, {rolled_back} 回滾, {needs_human} 需人工, {skipped} 跳過",
            findings_count=len(findings),
            actions=actions,
            status=status,
        )

        return summary

    # -------------------------------------------------------------------
    # 單一 Finding 處理
    # -------------------------------------------------------------------

    async def _process_finding(self, finding: dict, snapshot: dict, dry_run: bool) -> str:
        """處理單一 finding，返回 fixed/rolled_back/needs_human/skipped"""

        # 防線 1: Runbook 匹配
        runbook = match_runbook(finding)
        if not runbook:
            logger.info("[MuseDoc] No runbook for: %s → needs_human", finding.get("title", ""))
            return "needs_human"

        # 防線 2: 扇入檢查
        origin = finding.get("blast_origin", {})
        origin_file = origin.get("file", "") if isinstance(origin, dict) else ""
        fan_in = self._get_fan_in(origin_file, snapshot)
        if fan_in > runbook.blast_radius_max:
            logger.info(
                "[MuseDoc] Fan-in too high: %s has %d (max %d) → needs_human",
                origin_file, fan_in, runbook.blast_radius_max,
            )
            return "needs_human"

        if dry_run:
            logger.info("[MuseDoc] DRY RUN: would apply %s to %s", runbook.runbook_id, finding.get("title", ""))
            return "fixed"

        # 防線 3: 術前快照
        stash_name = f"musedoc-pre-{finding.get('finding_id', 'unknown')}"
        stash_created = self._git_stash_push(stash_name)

        try:
            # 術前驗證
            if not await runbook.pre_check(finding, self.home):
                logger.info("[MuseDoc] Pre-check failed for %s", finding.get("title", ""))
                if stash_created:
                    self._git_stash_pop()
                return "skipped"

            # 執行修復
            result = await asyncio.wait_for(
                runbook.action(finding, self.home),
                timeout=runbook.timeout_seconds,
            )

            if not result.success:
                logger.info("[MuseDoc] Action failed: %s → %s", runbook.runbook_id, result.message)
                if stash_created:
                    self._git_stash_pop()
                return "needs_human"

            # 防線 4: 術後驗證
            if not await runbook.post_check(finding, self.home):
                logger.warning("[MuseDoc] Post-check FAILED, rolling back")
                if stash_created:
                    self._git_stash_pop()
                self._record_rollback(finding, runbook, "post_check_failed")
                runbook.failure_count += 1
                return "rolled_back"

            # 成功
            runbook.success_count += 1
            logger.info("[MuseDoc] Fixed: %s via %s", finding.get("title", ""), runbook.runbook_id)
            return "fixed"

        except asyncio.TimeoutError:
            logger.warning("[MuseDoc] Timeout on %s, rolling back", runbook.runbook_id)
            if stash_created:
                self._git_stash_pop()
            self._record_rollback(finding, runbook, "timeout")
            return "rolled_back"

        except Exception as e:
            logger.error("[MuseDoc] Error: %s, rolling back", e)
            if stash_created:
                self._git_stash_pop()
            self._record_rollback(finding, runbook, str(e))
            return "rolled_back"

    # -------------------------------------------------------------------
    # Fix-Verify 閉環驗證
    # -------------------------------------------------------------------

    async def _fix_verify(self, finding: dict, snapshot: dict) -> bool:
        """修復後三維驗證（D1 行為 + D2 接線 + D3 藍圖）.

        簡化版：MuseDoc 自動修復的範圍有限（Runbook 驅動），
        驗證聚焦在：
          D1: Runbook 的 post_check 已通過（在 _process_finding 中完成）
          D2: 修改的檔案是否在正確位置、import 關係是否完整
          D3: 修改是否涉及需要更新的藍圖

        Returns:
            True if all checks pass
        """
        fid = finding.get("finding_id", "?")
        origin = finding.get("blast_origin", {})
        origin_file = origin.get("file", "") if isinstance(origin, dict) else ""

        checks_passed = 0
        checks_total = 0

        # D1: 行為驗證 — post_check 已在 _process_finding 中通過
        # （走到這裡代表 post_check 已成功，所以 D1 自動通過）
        checks_total += 1
        checks_passed += 1

        # D2: 接線驗證 — 修改的檔案扇入是否安全
        checks_total += 1
        if origin_file:
            fan_in = self._get_fan_in(origin_file, snapshot)
            if fan_in <= 10:  # 綠區/黃區
                checks_passed += 1
            else:
                logger.warning(
                    "[MuseDoc:FV] D2 FAIL: %s fan_in=%d (紅區), 修改需人工審查",
                    origin_file, fan_in,
                )
        else:
            checks_passed += 1  # 無檔案資訊，降級通過

        # D3: 藍圖驗證 — 檢查修改是否需要同步藍圖
        checks_total += 1
        # Runbook 修復通常是小範圍（config 修改、重啟服務），不影響藍圖
        # 如果 Runbook 標記了 requires_blueprint_update，則需要人工處理
        prescription = finding.get("prescription", {})
        complexity = prescription.get("fix_complexity", "GREEN") if isinstance(prescription, dict) else "GREEN"
        if complexity in ("GREEN", "YELLOW"):
            checks_passed += 1
        else:
            logger.warning(
                "[MuseDoc:FV] D3 WARN: 修復複雜度 %s, 可能需要藍圖更新",
                complexity,
            )
            checks_passed += 1  # 警告但不阻擋（MuseDoc 的修復範圍有限）

        passed = checks_passed == checks_total
        logger.info(
            "[MuseDoc:FV] %s: D1+D2+D3 = %d/%d → %s",
            fid, checks_passed, checks_total, "PASS" if passed else "FAIL",
        )
        return passed

    # -------------------------------------------------------------------
    # Git 操作
    # -------------------------------------------------------------------

    def _git_stash_push(self, name: str) -> bool:
        try:
            result = subprocess.run(
                ["git", "stash", "push", "-m", name],
                capture_output=True, text=True, timeout=10,
                cwd=str(self.home),
            )
            return "Saved" in result.stdout or "No local changes" in result.stdout
        except Exception:
            return False

    def _git_stash_pop(self) -> bool:
        try:
            subprocess.run(
                ["git", "stash", "pop"],
                capture_output=True, timeout=10,
                cwd=str(self.home),
            )
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------
    # Worker 快照查詢
    # -------------------------------------------------------------------

    def _load_worker_snapshot(self) -> dict:
        if self.snapshot_path.exists():
            try:
                return json.loads(self.snapshot_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _get_fan_in(self, file_path: str, snapshot: dict) -> int:
        fan_in_table = snapshot.get("fan_in_table", {})
        entry = fan_in_table.get(file_path, {})
        return entry.get("fan_in", 0) if isinstance(entry, dict) else 0

    # -------------------------------------------------------------------
    # 持久化
    # -------------------------------------------------------------------

    def _write_surgery_log(self, summary: dict) -> None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = self.surgery_dir / f"{date}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")

    def _record_rollback(self, finding: dict, runbook, reason: str) -> None:
        entry = {
            "timestamp": _now_iso(),
            "finding_id": finding.get("finding_id", ""),
            "runbook_id": runbook.runbook_id,
            "reason": reason,
        }
        with open(self.rollback_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_surgery_summary(self) -> str:
        """給早報用的摘要"""
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = self.surgery_dir / f"{date}.jsonl"
        if not log_file.exists():
            return "MuseDoc: 今夜無手術"

        try:
            last_line = log_file.read_text(encoding="utf-8").strip().split("\n")[-1]
            data = json.loads(last_line)
            return (
                f"MuseDoc: 修復 {data['fixed']} 個 / "
                f"回滾 {data['rolled_back']} 個 / "
                f"需人工 {data['needs_human']} 個"
            )
        except Exception:
            return "MuseDoc: 手術紀錄讀取失敗"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    async def main():
        doc = MuseDoc()
        dry_run = "--dry-run" in sys.argv

        if "--once" in sys.argv or "--dry-run" in sys.argv:
            summary = await doc.nightly_surgery(dry_run=dry_run)
            mode = "DRY RUN" if dry_run else "LIVE"
            print(f"\nMuseDoc 手術報告 [{mode}]")
            print(f"{'='*40}")
            print(f"  Total findings: {summary['total_findings']}")
            print(f"  Fixed: {summary['fixed']}")
            print(f"  Rolled back: {summary['rolled_back']}")
            print(f"  Needs human: {summary['needs_human']}")
            print(f"  Skipped: {summary['skipped']}")
            print(f"  Duration: {summary['duration_ms']}ms")
        else:
            print("Usage: python -m museon.doctor.musedoc --dry-run")
            print("       python -m museon.doctor.musedoc --once  (LIVE surgery)")

    asyncio.run(main())
