"""
MuseQA — 品質審計官

每 15 分鐘掃描對話 log，確保 Museon 的回覆符合軍師/顧問設計。
CPU 預篩 90%（正則匹配），LLM 抽檢 10%（Haiku，~$0.04/天）。

檢查項目：
1. 術語洩漏（內部架構術語出現在回覆中）
2. 人格偏移（回覆風格偏離 persona 設計）
3. 回覆品質（過短/過長/空洞）
4. 跨群組污染（A 群組內容出現在 B 群組回覆）
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from museon.doctor.finding import Finding, FindingStore, BlastOrigin, Prescription

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 術語洩漏模式庫
# ---------------------------------------------------------------------------

_DEFAULT_LEAKAGE_PATTERNS = [
    # 內部架構術語
    r"\bL[123]\b",
    r"\b(調度員|思考者|subagent|spawn|dispatcher)\b",
    r"\b(MCP|plugin|Gateway|Brain|ResponseGuard|EventBus)\b",
    r"\b(PulseDB|DataBus|MuseOff|MuseDoc|MuseWorker|MuseQA)\b",
    # 思考標記
    r"【思考路徑】",
    r"【順便一提】",
    r"\b(一階原則|多維度審查|深度思考)\b",
    # 開發狀態
    r"\b(debug|區塊|跑通|斷線|重啟|PID)\b",
    # 系統內部
    r"\b(fan.?in|扇入|扇出|blast.?radius|爆炸圖)\b",
    r"\bchat_id\b",
    r"\bsession_id\b",
]


class MuseQA:
    """品質審計官——15 分鐘對話品質掃描"""

    VERSION = "1.0.0"
    SCAN_INTERVAL = 900  # 15 分鐘

    def __init__(self, museon_home: Path | str | None = None):
        self.home = Path(museon_home or "/Users/ZEALCHOU/MUSEON")
        self.qa_dir = self.home / "data" / "_system" / "museqa"
        self.reports_dir = self.qa_dir / "qa_reports"
        self.scores_path = self.qa_dir / "quality_scores.jsonl"
        self.patterns_path = self.qa_dir / "leakage_patterns.json"

        self.qa_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self._finding_store = FindingStore(
            self.home / "data" / "_system" / "museoff" / "findings"
        )
        self._leakage_patterns = self._load_leakage_patterns()
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self._leakage_patterns]

    # -------------------------------------------------------------------
    # 主掃描入口
    # -------------------------------------------------------------------

    async def scan_recent(self, minutes: int = 15) -> dict:
        """掃描過去 N 分鐘的對話 log"""
        t0 = time.monotonic()
        results = {"scanned_sessions": 0, "scanned_replies": 0, "issues_found": 0}

        sessions = self._get_active_sessions(minutes)
        for session_id, messages in sessions.items():
            results["scanned_sessions"] += 1
            bot_replies = [m for m in messages if m.get("role") == "assistant"]
            results["scanned_replies"] += len(bot_replies)

            for reply in bot_replies:
                text = reply.get("content", "")

                # CPU 篩查 1: 術語洩漏
                leakage = self._check_leakage(text)
                if leakage:
                    self._create_qa_report(
                        session_id=session_id,
                        issue_type="LEAKAGE",
                        severity="HIGH",
                        evidence={
                            "bot_reply_excerpt": text[:200],
                            "matched_patterns": leakage,
                        },
                        suggested_fix="強化 CLAUDE.md Step 3.5 禁止清單",
                    )
                    results["issues_found"] += 1

                # CPU 篩查 2: 回覆長度異常
                length_issue = self._check_length(text)
                if length_issue:
                    self._create_qa_report(
                        session_id=session_id,
                        issue_type="LENGTH_ANOMALY",
                        severity="LOW",
                        evidence={
                            "length": len(text),
                            "issue": length_issue,
                        },
                    )
                    results["issues_found"] += 1

                # CPU 篩查 3: 跨群組污染標記
                if self._check_cross_group(text, session_id):
                    self._create_qa_report(
                        session_id=session_id,
                        issue_type="CROSS_GROUP",
                        severity="CRITICAL",
                        evidence={
                            "bot_reply_excerpt": text[:200],
                            "violation": "回覆中包含其他群組的 session 資訊",
                        },
                    )
                    results["issues_found"] += 1

        results["duration_ms"] = int((time.monotonic() - t0) * 1000)
        self._record_scan_result(results)
        return results

    # -------------------------------------------------------------------
    # 檢查器
    # -------------------------------------------------------------------

    def _check_leakage(self, text: str) -> list[str]:
        """檢查術語洩漏，返回匹配的模式"""
        matched = []
        for i, pattern in enumerate(self._compiled_patterns):
            if pattern.search(text):
                matched.append(self._leakage_patterns[i])
        return matched

    def _check_length(self, text: str) -> str | None:
        """檢查回覆長度異常"""
        if len(text) < 10:
            return "too_short"
        if len(text) > 3000:
            return "too_long"
        return None

    def _check_cross_group(self, text: str, session_id: str) -> bool:
        """檢查跨群組污染——其他群組 ID 出現在回覆中"""
        # 提取所有像 group ID 的數字
        group_ids = re.findall(r"(?:telegram_group_|chat_id[=: ]+)(\d{8,})", text)
        if not group_ids:
            return False
        # 檢查是否有不屬於當前 session 的 group ID
        current_id = session_id.rsplit("_", 1)[-1] if "telegram_group_" in session_id else ""
        for gid in group_ids:
            if gid != current_id:
                return True
        return False

    # -------------------------------------------------------------------
    # Session Log 讀取
    # -------------------------------------------------------------------

    def _get_active_sessions(self, minutes: int) -> dict[str, list[dict]]:
        """讀取最近 N 分鐘有活動的 session log"""
        sessions: dict[str, list[dict]] = {}
        session_dir = self.home / "data" / "_system" / "sessions"

        if not session_dir.exists():
            return sessions

        cutoff = time.time() - (minutes * 60)

        for session_file in session_dir.glob("*.json"):
            if session_file.stat().st_mtime < cutoff:
                continue

            try:
                data = json.loads(session_file.read_text(encoding="utf-8"))
                messages = data if isinstance(data, list) else data.get("messages", [])
                # 只取最近 N 分鐘的訊息
                recent = []
                for msg in messages:
                    ts = msg.get("timestamp", "")
                    if ts:
                        try:
                            msg_time = datetime.fromisoformat(ts).timestamp()
                            if msg_time >= cutoff:
                                recent.append(msg)
                        except (ValueError, TypeError):
                            recent.append(msg)  # 無法解析時間就包含
                    else:
                        recent.append(msg)

                if recent:
                    session_id = session_file.stem
                    sessions[session_id] = recent
            except (json.JSONDecodeError, OSError):
                continue

        return sessions

    # -------------------------------------------------------------------
    # QA Report 建立
    # -------------------------------------------------------------------

    def _create_qa_report(
        self,
        session_id: str,
        issue_type: str,
        severity: str,
        evidence: dict,
        suggested_fix: str = "",
    ) -> None:
        """建立 QA 報告並同時建立 Finding（供 MuseDoc 處理）"""
        report = {
            "qa_report_id": f"QA-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "issue_type": issue_type,
            "severity": severity,
            "evidence": evidence,
            "suggested_fix": suggested_fix,
            "status": "open",
        }

        # 存 QA report
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day_dir = self.reports_dir / date
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / f"{report['qa_report_id']}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        # 嚴重問題同時建立 Finding（讓 MuseDoc 能處理）
        if severity in ("CRITICAL", "HIGH"):
            finding = Finding(
                probe_layer="QA",
                severity=severity,
                title=f"[QA] {issue_type} in {session_id}",
                source="museqa",
                blast_origin=BlastOrigin(
                    file=f"session:{session_id}",
                    error_type=issue_type,
                ),
                context=evidence,
                prescription=Prescription(
                    diagnosis=f"QA {issue_type}: {json.dumps(evidence, ensure_ascii=False)[:200]}",
                    suggested_fix=suggested_fix,
                ),
            )
            if not self._finding_store.is_duplicate(finding):
                self._finding_store.save(finding)

        logger.info("[MuseQA] Report: %s [%s] %s in %s", report["qa_report_id"], severity, issue_type, session_id)

    # -------------------------------------------------------------------
    # 持久化
    # -------------------------------------------------------------------

    def _record_scan_result(self, results: dict) -> None:
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), **results}
        with open(self.scores_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _load_leakage_patterns(self) -> list[str]:
        if self.patterns_path.exists():
            try:
                return json.loads(self.patterns_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        # 儲存預設模式
        self.patterns_path.parent.mkdir(parents=True, exist_ok=True)
        self.patterns_path.write_text(
            json.dumps(_DEFAULT_LEAKAGE_PATTERNS, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return _DEFAULT_LEAKAGE_PATTERNS


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio
    import sys

    async def main():
        qa = MuseQA()
        if "--once" in sys.argv:
            results = await qa.scan_recent(minutes=60)  # CLI 模式掃描最近 1 小時
            print(f"\nMuseQA 品質掃描報告")
            print(f"{'='*40}")
            print(f"  掃描 sessions: {results['scanned_sessions']}")
            print(f"  掃描回覆數: {results['scanned_replies']}")
            print(f"  發現問題: {results['issues_found']}")
            print(f"  耗時: {results['duration_ms']}ms")
        else:
            print("Usage: python -m museon.doctor.museqa --once")

    asyncio.run(main())
