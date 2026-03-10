"""
SC-07：Skill 鍛造 + 商務運營同時進行（MUSEON 專屬壓測）
透過 webhook 驗證：
- 複雜多 Skill 協作能力
- 開發與營運切換不混淆
- Context switching 後能回到原話題
- 無洩漏
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


class TestSC07SkillForging:
    """SC-07 Skill 鍛造 + 商務運營壓測"""

    def test_skill_design_request(self, collector, http_client):
        """請求設計一個 Skill"""
        t0 = time.time()
        data = send_message(
            http_client,
            "我想把我的記帳流程做成一個 AI Skill。"
            "流程是：每天收集 Line 訊息中的消費紀錄，"
            "自動分類成食物/交通/娛樂/固定支出，"
            "每週產出一份消費分析報告。"
            "幫我設計這個 Skill 的架構。",
        )
        ms = int((time.time() - t0) * 1000)
        resp = data.get("response", "")
        leak = check_leak(resp)

        if not resp.strip():
            collector.record("sc07_skill_design", "D1.skill_forge", "FAIL",
                             "回覆為空", severity="CRITICAL")
            pytest.fail("回覆為空")
        if leak:
            collector.record("sc07_skill_design", "D1.skill_forge", "FAIL",
                             leak, severity="HIGH")
            pytest.fail(leak)
        # Skill 設計應有結構
        if len(resp) < 150:
            collector.record("sc07_skill_design", "D1.skill_forge", "WARN",
                             f"Skill 設計太簡略 ({len(resp)} chars)",
                             severity="MEDIUM")
        else:
            collector.record("sc07_skill_design", "D1.skill_forge", "PASS",
                             f"{ms}ms, {len(resp)} chars")

    def test_context_switch_dev_to_client(self, collector, http_client):
        """開發中切換到客戶服務任務"""
        session = f"e2e_sc07_switch_{int(time.time())}"

        # 先做開發任務
        send_message(
            http_client,
            "我正在設計一個自動化報告的 Skill，目前做到了資料收集模組。",
            session_id=session,
        )
        time.sleep(2)

        # 切到客戶任務
        t0 = time.time()
        data = send_message(
            http_client,
            "等等，先暫停開發。客戶 A 剛剛問我們的顧問服務怎麼收費，"
            "幫我草擬一個回覆，要包含我們的三種方案：\n"
            "1. 基礎版 $9,900/月\n"
            "2. 進階版 $29,900/月\n"
            "3. 旗艦版 $59,900/月",
            session_id=session,
        )
        ms = int((time.time() - t0) * 1000)
        resp = data.get("response", "")
        leak = check_leak(resp)

        if not resp.strip():
            collector.record("sc07_ctx_switch", "D2.context_switch", "FAIL",
                             "回覆為空", severity="CRITICAL")
            pytest.fail("回覆為空")
        if leak:
            collector.record("sc07_ctx_switch", "D2.context_switch", "FAIL",
                             leak, severity="HIGH")
            pytest.fail(leak)
        # 應該是關於客戶報價的回覆，不應混入 Skill 開發內容
        has_pricing = any(k in resp for k in ["9,900", "29,900", "59,900", "方案"])
        has_dev_leak = any(k in resp for k in ["資料收集模組", "Skill 設計"])
        if has_pricing and not has_dev_leak:
            collector.record("sc07_ctx_switch", "D2.context_switch", "PASS",
                             f"Context switch 乾淨 ({ms}ms)")
        elif has_pricing:
            collector.record("sc07_ctx_switch", "D2.context_switch", "WARN",
                             "有報價但也混入開發內容", severity="MEDIUM")
        else:
            collector.record("sc07_ctx_switch", "D2.context_switch", "WARN",
                             f"回覆可能不正確: {resp[:100]}", severity="MEDIUM")

    def test_resume_after_interruption(self, collector, http_client):
        """中斷後回到原任務"""
        session = f"e2e_sc07_resume_{int(time.time())}"

        # 第一階段：開始開發
        send_message(
            http_client,
            "幫我規劃一個客戶管理 Skill 的開發計畫，分成四個階段。",
            session_id=session,
        )
        time.sleep(2)

        # 中斷：做別的事
        send_message(
            http_client,
            "先幫我寫一封給供應商的催貨信。",
            session_id=session,
        )
        time.sleep(2)

        # 回到原任務
        t0 = time.time()
        data = send_message(
            http_client,
            "好了，繼續剛才的客戶管理 Skill 開發計畫。"
            "你之前規劃到哪了？",
            session_id=session,
        )
        ms = int((time.time() - t0) * 1000)
        resp = data.get("response", "")
        leak = check_leak(resp)

        if not resp.strip():
            collector.record("sc07_resume", "D2.continuity", "FAIL",
                             "回覆為空", severity="CRITICAL")
            pytest.fail("回覆為空")
        if leak:
            collector.record("sc07_resume", "D2.continuity", "FAIL",
                             leak, severity="HIGH")
            pytest.fail(leak)
        # 應該提到客戶管理/開發計畫/階段
        resume_keywords = ["客戶管理", "Skill", "開發", "階段", "計畫"]
        has_resume = sum(1 for k in resume_keywords if k in resp)
        if has_resume >= 2:
            collector.record("sc07_resume", "D2.continuity", "PASS",
                             f"中斷後成功回到原任務 ({ms}ms)")
        else:
            collector.record("sc07_resume", "D2.continuity", "WARN",
                             f"回到原任務不完全: {resp[:100]}",
                             severity="MEDIUM")

    def test_business_analysis_quality(self, collector, http_client):
        """商模診斷品質"""
        t0 = time.time()
        data = send_message(
            http_client,
            "我有一個做手工皂的朋友想創業，目前月營收約 3 萬元，"
            "主要在蝦皮賣。她想擴大規模但不知道怎麼做。"
            "幫我做一個簡單的商業診斷。",
        )
        ms = int((time.time() - t0) * 1000)
        resp = data.get("response", "")
        leak = check_leak(resp)

        if not resp.strip():
            collector.record("sc07_biz_diag", "D1.business", "FAIL",
                             "回覆為空", severity="CRITICAL")
            pytest.fail("回覆為空")
        if leak:
            collector.record("sc07_biz_diag", "D1.business", "FAIL",
                             leak, severity="HIGH")
            pytest.fail(leak)
        if len(resp) < 150:
            collector.record("sc07_biz_diag", "D1.business", "WARN",
                             f"商業診斷太簡略 ({len(resp)} chars)",
                             severity="MEDIUM")
        else:
            collector.record("sc07_biz_diag", "D1.business", "PASS",
                             f"{ms}ms, {len(resp)} chars — 診斷品質足夠")

    def test_multi_task_no_confusion(self, collector, http_client):
        """同一 session 多任務不混淆"""
        session = f"e2e_sc07_multi_{int(time.time())}"
        tasks = [
            {
                "msg": "幫我寫一份關於 AI 教育市場的簡報大綱。",
                "expect": ["AI", "教育"],
                "id": "presentation",
            },
            {
                "msg": "幫我算一下如果月租 5 萬、裝潢 30 萬、"
                       "每月人事 15 萬，開店需要多少啟動資金？",
                "expect": ["萬", "資金"],
                "id": "accounting",
            },
        ]
        results = []
        for task in tasks:
            data = send_message(http_client, task["msg"],
                                session_id=session)
            resp = data.get("response", "")
            relevant = sum(1 for k in task["expect"] if k in resp)
            results.append({
                "id": task["id"],
                "resp_len": len(resp),
                "relevant": relevant >= 1,
                "leak": check_leak(resp),
            })
            time.sleep(2)

        all_ok = all(r["relevant"] and not r["leak"] for r in results)
        if all_ok:
            collector.record("sc07_no_confusion", "D2.isolation", "PASS",
                             "多任務回覆不混淆")
        else:
            issues = [f"{r['id']}:relevant={r['relevant']},leak={r['leak']}"
                      for r in results if not r["relevant"] or r["leak"]]
            collector.record("sc07_no_confusion", "D2.isolation", "WARN",
                             f"可能混淆: {issues}", severity="MEDIUM")
