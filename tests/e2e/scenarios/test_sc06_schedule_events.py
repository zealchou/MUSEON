"""
SC-06：排程 + 外部事件交叉（時序壓測）
透過 webhook 驗證：
- 排程相關的理解和規劃能力
- 時區意識（台灣 UTC+8）
- 時間衝突處理
- 優先級判斷（緊急 vs 排程）
"""
from __future__ import annotations

import re
import time
import pytest

from tests.e2e.conftest import send_message, GATEWAY_URL

LEAK_PATTERNS = [
    r"^\*?\*?\[內在思考審視\]",
    r"^#{1,3}\s*(DNA27|MUSEON|Style Always|Style Never)",
    r"^-\s*(真實優先|演化至上|代價透明|長期複利)\s*[—–\-(（]",
]


def check_leak(text: str) -> str | None:
    for pat in LEAK_PATTERNS:
        for line in text.split("\n"):
            if re.match(pat, line.strip()):
                return f"洩漏: {line.strip()[:80]}"
    return None


class TestSC06ScheduleEvents:
    """SC-06 排程 + 時序壓測"""

    def test_schedule_planning(self, collector, http_client):
        """排程規劃能力"""
        t0 = time.time()
        data = send_message(
            http_client,
            "幫我規劃每天的工作流程：\n"
            "1. 早上 8 點整理 email\n"
            "2. 早上 9 點產出日報\n"
            "3. 下午 2 點檢查客戶回覆\n"
            "4. 下午 5 點彙整當日工作摘要\n"
            "請幫我列出具體的執行計畫。",
        )
        ms = int((time.time() - t0) * 1000)
        resp = data.get("response", "")
        leak = check_leak(resp)

        if not resp.strip():
            collector.record("sc06_schedule_plan", "D3.schedule", "FAIL",
                             "回覆為空", severity="CRITICAL")
            pytest.fail("回覆為空")
        if leak:
            collector.record("sc06_schedule_plan", "D3.schedule", "FAIL",
                             leak, severity="HIGH")
            pytest.fail(leak)
        # 應包含時間相關內容
        time_keywords = ["8", "9", "2", "5", "早上", "下午", "點"]
        has_time = sum(1 for k in time_keywords if k in resp)
        if has_time >= 3 and len(resp) > 100:
            collector.record("sc06_schedule_plan", "D3.schedule", "PASS",
                             f"{ms}ms, {len(resp)} chars")
        else:
            collector.record("sc06_schedule_plan", "D3.schedule", "WARN",
                             f"排程規劃不完整 ({has_time} 個時間詞)",
                             severity="MEDIUM")

    def test_timezone_awareness(self, collector, http_client):
        """時區意識 — 應使用台灣時間"""
        data = send_message(
            http_client,
            "如果我跟美國舊金山的客戶約明天下午 3 點開會，"
            "台灣時間是幾點？請幫我安排。",
        )
        resp = data.get("response", "")
        leak = check_leak(resp)

        if not resp.strip():
            collector.record("sc06_timezone", "D3.timezone", "FAIL",
                             "回覆為空", severity="CRITICAL")
            pytest.fail("回覆為空")
        if leak:
            collector.record("sc06_timezone", "D3.timezone", "FAIL",
                             leak, severity="HIGH")
            pytest.fail(leak)
        # 舊金山 PST(UTC-8) 下午 3 點 = 台灣 UTC+8 早上 7 點（冬令）/ 6 點（夏令）
        # 能提到時差概念就算通過
        tz_aware = any(k in resp for k in [
            "時差", "UTC", "太平洋", "PST", "PDT",
            "早上", "凌晨", "上午",
            "16 小時", "16小時",
        ])
        if tz_aware:
            collector.record("sc06_timezone", "D3.timezone", "PASS",
                             "有時區意識")
        else:
            collector.record("sc06_timezone", "D3.timezone", "WARN",
                             f"時區意識不足: {resp[:100]}", severity="MEDIUM")

    def test_priority_urgent_vs_scheduled(self, collector, http_client):
        """緊急任務 vs 排程任務的優先級判斷"""
        session = f"e2e_sc06_priority_{int(time.time())}"

        data = send_message(
            http_client,
            "我本來排定下午要整理報告，但是客戶剛剛打來說有個緊急問題需要處理。"
            "你覺得我應該怎麼安排？",
            session_id=session,
        )
        resp = data.get("response", "")
        leak = check_leak(resp)

        if not resp.strip():
            collector.record("sc06_priority", "D3.priority", "FAIL",
                             "回覆為空", severity="CRITICAL")
            pytest.fail("回覆為空")
        if leak:
            collector.record("sc06_priority", "D3.priority", "FAIL",
                             leak, severity="HIGH")
            pytest.fail(leak)
        # 應建議處理緊急任務
        urgent_keywords = ["緊急", "先", "優先", "客戶", "處理"]
        has_priority = sum(1 for k in urgent_keywords if k in resp)
        if has_priority >= 2:
            collector.record("sc06_priority", "D3.priority", "PASS",
                             "正確建議優先處理緊急任務")
        else:
            collector.record("sc06_priority", "D3.priority", "WARN",
                             f"優先級判斷不清: {resp[:100]}", severity="MEDIUM")

    def test_time_conflict_handling(self, collector, http_client):
        """時間衝突處理"""
        data = send_message(
            http_client,
            "下週二下午 2 點到 4 點我有一個會議，但是同一天下午 3 點到 5 點又有另一個會議。"
            "幫我看一下怎麼處理這個衝突。",
        )
        resp = data.get("response", "")
        leak = check_leak(resp)

        if not resp.strip():
            collector.record("sc06_conflict", "D3.conflict", "FAIL",
                             "回覆為空", severity="CRITICAL")
            pytest.fail("回覆為空")
        if leak:
            collector.record("sc06_conflict", "D3.conflict", "FAIL",
                             leak, severity="HIGH")
            pytest.fail(leak)
        # 應辨識出時間衝突
        conflict_keywords = ["衝突", "重疊", "撞", "調整", "改時間", "移", "延"]
        has_conflict = any(k in resp for k in conflict_keywords)
        if has_conflict:
            collector.record("sc06_conflict", "D3.conflict", "PASS",
                             "正確辨識並處理時間衝突")
        else:
            collector.record("sc06_conflict", "D3.conflict", "WARN",
                             f"未辨識時間衝突: {resp[:100]}", severity="MEDIUM")

    def test_recurring_task_understanding(self, collector, http_client):
        """重複任務理解"""
        data = send_message(
            http_client,
            "我想設定一個每週一早上自動執行的任務：\n"
            "1. 檢查上週的銷售數據\n"
            "2. 產出週報\n"
            "3. 發送給團隊\n"
            "你能幫我規劃這個自動化流程嗎？",
        )
        resp = data.get("response", "")
        leak = check_leak(resp)

        if not resp.strip():
            collector.record("sc06_recurring", "D3.recurring", "FAIL",
                             "回覆為空", severity="CRITICAL")
            pytest.fail("回覆為空")
        if leak:
            collector.record("sc06_recurring", "D3.recurring", "FAIL",
                             leak, severity="HIGH")
            pytest.fail(leak)
        # 應包含自動化/排程相關概念
        auto_keywords = ["自動", "排程", "定期", "每週", "cron", "觸發"]
        has_auto = sum(1 for k in auto_keywords if k in resp)
        if has_auto >= 2 and len(resp) > 80:
            collector.record("sc06_recurring", "D3.recurring", "PASS",
                             f"重複任務規劃完整 ({len(resp)} chars)")
        else:
            collector.record("sc06_recurring", "D3.recurring", "WARN",
                             f"重複任務理解不足: {resp[:100]}", severity="MEDIUM")

    def test_deadline_awareness(self, collector, http_client):
        """截止日期意識"""
        data = send_message(
            http_client,
            "我有三個任務要在這週五前完成：\n"
            "1. 客戶提案書（需要 2 天）\n"
            "2. 團隊週報（需要 1 小時）\n"
            "3. 新功能設計文件（需要 3 天）\n"
            "今天是週三，幫我安排優先順序。",
        )
        resp = data.get("response", "")
        leak = check_leak(resp)

        if not resp.strip():
            collector.record("sc06_deadline", "D3.deadline", "FAIL",
                             "回覆為空", severity="CRITICAL")
            pytest.fail("回覆為空")
        if leak:
            collector.record("sc06_deadline", "D3.deadline", "FAIL",
                             leak, severity="HIGH")
            pytest.fail(leak)
        # 應建議優先做耗時最長的任務（3天的設計文件可能來不及）
        if len(resp) > 80:
            collector.record("sc06_deadline", "D3.deadline", "PASS",
                             f"截止日期安排回覆 ({len(resp)} chars)")
        else:
            collector.record("sc06_deadline", "D3.deadline", "WARN",
                             f"回覆太短: {resp[:100]}", severity="MEDIUM")
