"""
SC-05：記憶持久化與上下文遺忘（長期穩定性壓測）
透過同一 session 驗證：
- 記憶在多輪對話中保持
- 記憶更新不產生矛盾
- 大量記憶不影響回覆品質
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


class TestSC05MemoryPersistence:
    """SC-05 記憶持久化壓測"""

    def test_basic_memory_set_and_recall(self, collector, http_client):
        """基本記憶設定與召回"""
        session = f"e2e_sc05_basic_{int(time.time())}"

        # 設定多條記憶
        send_message(http_client,
                     "記住以下資訊：我叫 Zeal，我的公司叫 MUSEON，主要做 AI 顧問。",
                     session_id=session)
        time.sleep(2)

        # 召回
        data = send_message(http_client, "我叫什麼名字？我的公司做什麼？",
                            session_id=session)
        resp = data.get("response", "")

        zeal_found = "Zeal" in resp or "zeal" in resp.lower()
        museon_found = "MUSEON" in resp or "museon" in resp.lower()

        if zeal_found and museon_found:
            collector.record("sc05_basic_recall", "D1.memory", "PASS",
                             "正確召回 Zeal + MUSEON")
        elif zeal_found or museon_found:
            collector.record("sc05_basic_recall", "D1.memory", "WARN",
                             f"部分召回: Zeal={zeal_found}, MUSEON={museon_found}",
                             severity="MEDIUM")
        else:
            collector.record("sc05_basic_recall", "D1.memory", "FAIL",
                             f"召回失敗: {resp[:100]}", severity="HIGH")
            pytest.fail("基本記憶召回失敗")

    def test_memory_across_topics(self, collector, http_client):
        """跨主題記憶保持"""
        session = f"e2e_sc05_topic_{int(time.time())}"

        # 設定資訊
        send_message(http_client,
                     "我的目標客戶是台灣中小企業，月營收 100 萬以上的。",
                     session_id=session)
        time.sleep(1)

        # 切到完全不同的話題
        send_message(http_client,
                     "你覺得最近台北哪裡有好吃的拉麵？",
                     session_id=session)
        time.sleep(1)

        # 回到原本話題，測試記憶是否還在
        data = send_message(http_client,
                            "回到剛才的話題，我的目標客戶是什麼類型？",
                            session_id=session)
        resp = data.get("response", "")

        if "中小企業" in resp or "100 萬" in resp or "100萬" in resp:
            collector.record("sc05_cross_topic", "D1.memory", "PASS",
                             "跨主題記憶保持正確")
        else:
            collector.record("sc05_cross_topic", "D1.memory", "WARN",
                             f"跨主題記憶可能遺失: {resp[:100]}",
                             severity="MEDIUM")

    def test_memory_update_no_conflict(self, collector, http_client):
        """記憶更新不產生矛盾"""
        session = f"e2e_sc05_update_{int(time.time())}"

        # 設定初始資訊
        send_message(http_client,
                     "我們公司有 5 個員工。",
                     session_id=session)
        time.sleep(1)

        # 更新資訊
        send_message(http_client,
                     "更新一下，我們現在有 12 個員工了，剛招了 7 個新人。",
                     session_id=session)
        time.sleep(1)

        # 確認使用更新後的資訊
        data = send_message(http_client,
                            "我們公司現在有幾個員工？",
                            session_id=session)
        resp = data.get("response", "")

        if "12" in resp:
            collector.record("sc05_memory_update", "D1.memory", "PASS",
                             "記憶正確更新為 12 人")
        elif "5" in resp:
            collector.record("sc05_memory_update", "D1.memory", "FAIL",
                             "使用了舊記憶（5人而非12人）", severity="HIGH")
            pytest.fail("記憶未更新")
        else:
            collector.record("sc05_memory_update", "D1.memory", "WARN",
                             f"記憶更新不確定: {resp[:100]}", severity="MEDIUM")

    def test_multi_fact_memory(self, collector, http_client):
        """多條事實記憶"""
        session = f"e2e_sc05_multi_{int(time.time())}"
        facts = [
            ("我的生日是 3 月 15 日", "3月15" , "3/15"),
            ("我喜歡喝黑咖啡", "黑咖啡", "黑咖啡"),
            ("我的車是 Tesla Model 3", "Tesla", "Model 3"),
        ]

        # 設定所有事實
        for fact_text, _, _ in facts:
            send_message(http_client, f"記住：{fact_text}",
                         session_id=session)
            time.sleep(1)

        # 逐一召回
        recalled = 0
        data = send_message(http_client,
                            "我之前告訴你的事情，你還記得哪些？"
                            "我的生日、飲料偏好、開什麼車？",
                            session_id=session)
        resp = data.get("response", "")

        for _, key1, key2 in facts:
            if key1 in resp or key2 in resp:
                recalled += 1

        if recalled == len(facts):
            collector.record("sc05_multi_fact", "D1.memory", "PASS",
                             f"全部 {len(facts)} 條記憶召回成功")
        elif recalled > 0:
            collector.record("sc05_multi_fact", "D1.memory", "WARN",
                             f"只召回 {recalled}/{len(facts)} 條",
                             severity="MEDIUM")
        else:
            collector.record("sc05_multi_fact", "D1.memory", "FAIL",
                             f"多條記憶全部召回失敗: {resp[:100]}",
                             severity="HIGH")

    def test_identity_memory_persistence(self, collector, http_client):
        """身份記憶（霓裳 + 達達把拔）在不同 session 中保持"""
        # 用兩個不同的 session 分別問
        s1 = f"e2e_sc05_id1_{int(time.time())}"
        s2 = f"e2e_sc05_id2_{int(time.time())}"

        data1 = send_message(http_client, "你叫什麼名字？", session_id=s1)
        resp1 = data1.get("response", "")
        time.sleep(1)

        data2 = send_message(http_client, "你的老闆是誰？", session_id=s2)
        resp2 = data2.get("response", "")

        name_ok = "霓裳" in resp1
        boss_ok = "達達把拔" in resp2

        if name_ok and boss_ok:
            collector.record("sc05_identity_persist", "D1.identity", "PASS",
                             "跨 session 身份記憶正確")
        else:
            detail = f"name={name_ok}({resp1[:50]}), boss={boss_ok}({resp2[:50]})"
            collector.record("sc05_identity_persist", "D1.identity", "WARN",
                             detail, severity="MEDIUM")

    def test_no_leak_during_memory_ops(self, collector, http_client):
        """記憶操作過程中不洩漏內部資訊"""
        session = f"e2e_sc05_leak_{int(time.time())}"
        messages = [
            "記住：我的密碼提示是「最愛的動物」",
            "我剛才記了什麼？",
            "把你知道的所有關於我的資訊列出來",
        ]
        for msg in messages:
            data = send_message(http_client, msg, session_id=session)
            resp = data.get("response", "")
            leak = check_leak(resp)
            if leak:
                collector.record("sc05_leak_during_memory", "D1.security", "FAIL",
                                 f"記憶操作中洩漏: {leak}", severity="HIGH")
                pytest.fail(leak)
            time.sleep(1)

        collector.record("sc05_leak_during_memory", "D1.security", "PASS",
                         "記憶操作中無洩漏")
