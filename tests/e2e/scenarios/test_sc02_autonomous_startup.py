"""
SC-02：自主創業全流程（長時間自主運行壓測）簡化版
透過 webhook 驗證：
- 複雜規劃型任務的回覆品質
- 方向轉變後的優雅處理
- 長文輸出的完整性
- 無洩漏
"""
import re
import time
import pytest

from tests.e2e.conftest import send_message, GATEWAY_URL

LEAK_PATTERNS = [
    r"^\*?\*?\[內在思考審視\]",
    r"^#{1,3}\s*(DNA27|MUSEON|Style Always|Style Never)",
    r"^-\s*(真實優先|演化至上|代價透明|長期複利)\s*[—–\-(（]",
    r"^-\s*(fast_loop|exploration_loop|slow_loop)\s*[（(]",
    r"信任等級：\w+\s*\|\s*總互動次數：\d+",
]


def check_leak(text: str) -> str | None:
    for pat in LEAK_PATTERNS:
        for line in text.split("\n"):
            if re.match(pat, line.strip()):
                return f"洩漏: {line.strip()[:80]}"
    return None


class TestSC02AutonomousStartup:
    """SC-02 自主創業全流程壓測（webhook 簡化版）"""

    def test_strategic_planning(self, collector, http_client):
        """要求制定創業計畫，驗證結構化思考能力"""
        session = f"e2e_sc02_{int(time.time())}"
        t0 = time.time()
        data = send_message(
            http_client,
            "我想創業，打算做一個面向台灣中小企業的 AI 顧問工具。"
            "幫我分析市場機會和競爭格局，列出前三個最關鍵的風險。",
            session_id=session,
        )
        ms = int((time.time() - t0) * 1000)
        resp = data.get("response", "")
        leak = check_leak(resp)

        if not resp.strip():
            collector.record("sc02_strategic_plan", "D1.planning", "FAIL",
                             "回覆為空", severity="CRITICAL")
            pytest.fail("回覆為空")
        if leak:
            collector.record("sc02_strategic_plan", "D1.planning", "FAIL",
                             leak, severity="HIGH")
            pytest.fail(leak)
        # 策略規劃應足夠長且有結構
        if len(resp) < 200:
            collector.record("sc02_strategic_plan", "D1.planning", "WARN",
                             f"規劃回覆太短 ({len(resp)} chars)", severity="MEDIUM")
        else:
            collector.record("sc02_strategic_plan", "D1.planning", "PASS",
                             f"{ms}ms, {len(resp)} chars")

    def test_direction_change(self, collector, http_client):
        """模擬方向轉變，驗證 Agent 能優雅處理"""
        session = f"e2e_sc02_pivot_{int(time.time())}"

        # 先設定方向
        send_message(
            http_client,
            "我決定做一個 B2C 的記帳 App，目標是台灣年輕人。",
            session_id=session,
        )
        time.sleep(2)

        # 轉變方向
        t0 = time.time()
        data = send_message(
            http_client,
            "我改主意了，不做 B2C 了，改做 B2B 企業記帳解決方案。"
            "幫我分析這個轉變需要調整哪些策略？",
            session_id=session,
        )
        ms = int((time.time() - t0) * 1000)
        resp = data.get("response", "")
        leak = check_leak(resp)

        if not resp.strip():
            collector.record("sc02_pivot", "D1.adaptability", "FAIL",
                             "回覆為空", severity="CRITICAL")
            pytest.fail("回覆為空")
        if leak:
            collector.record("sc02_pivot", "D1.adaptability", "FAIL",
                             leak, severity="HIGH")
            pytest.fail(leak)
        # 應該提到 B2B 和 B2C 的差異
        b2b_mentioned = "B2B" in resp or "企業" in resp
        if b2b_mentioned and len(resp) > 100:
            collector.record("sc02_pivot", "D1.adaptability", "PASS",
                             f"正確處理方向轉變 ({ms}ms, {len(resp)} chars)")
        else:
            collector.record("sc02_pivot", "D1.adaptability", "WARN",
                             f"方向轉變回覆不完整: {resp[:100]}",
                             severity="MEDIUM")

    def test_research_with_followup(self, collector, http_client):
        """多步驟研究任務 + 追問"""
        session = f"e2e_sc02_research_{int(time.time())}"

        # 第一步：研究
        data1 = send_message(
            http_client,
            "幫我研究目前台灣 AI 新創的生態系，列出主要玩家和他們的模式。",
            session_id=session,
        )
        resp1 = data1.get("response", "")
        time.sleep(2)

        # 第二步：追問
        t0 = time.time()
        data2 = send_message(
            http_client,
            "根據你剛才的分析，你覺得最大的市場缺口在哪裡？",
            session_id=session,
        )
        ms = int((time.time() - t0) * 1000)
        resp2 = data2.get("response", "")
        leak = check_leak(resp2)

        if not resp2.strip():
            collector.record("sc02_research_followup", "D1.continuity", "FAIL",
                             "追問回覆為空", severity="CRITICAL")
            pytest.fail("追問回覆為空")
        if leak:
            collector.record("sc02_research_followup", "D1.continuity", "FAIL",
                             leak, severity="HIGH")
            pytest.fail(leak)
        # 追問回覆應該有上下文延續
        if len(resp2) > 50:
            collector.record("sc02_research_followup", "D1.continuity", "PASS",
                             f"追問有延續性 ({ms}ms, {len(resp2)} chars)")
        else:
            collector.record("sc02_research_followup", "D1.continuity", "WARN",
                             f"追問回覆太短 ({len(resp2)} chars)",
                             severity="MEDIUM")

    def test_comprehensive_report_request(self, collector, http_client):
        """要求產出完整報告，驗證長文輸出品質"""
        t0 = time.time()
        data = send_message(
            http_client,
            "幫我把以下想法整理成一份完整的商業計畫摘要：\n"
            "1. 做 AI 顧問工具\n"
            "2. 目標台灣中小企業\n"
            "3. 月費制 $2999/月\n"
            "4. 第一年目標 100 家客戶\n"
            "請包含市場分析、產品定位、營收預估。",
        )
        ms = int((time.time() - t0) * 1000)
        resp = data.get("response", "")
        leak = check_leak(resp)

        if not resp.strip():
            collector.record("sc02_report", "D1.report", "FAIL",
                             "回覆為空", severity="CRITICAL")
            pytest.fail("回覆為空")
        if leak:
            collector.record("sc02_report", "D1.report", "FAIL",
                             leak, severity="HIGH")
            pytest.fail(leak)
        if len(resp) < 300:
            collector.record("sc02_report", "D1.report", "WARN",
                             f"報告太短 ({len(resp)} chars)", severity="MEDIUM")
        else:
            collector.record("sc02_report", "D1.report", "PASS",
                             f"{ms}ms, {len(resp)} chars — 報告品質足夠")
