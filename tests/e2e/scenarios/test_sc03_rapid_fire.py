"""
SC-03：高頻多指令轟炸（D2 多工穩定性壓測）
模擬使用者在短時間內連續丟出不同任務，驗證：
- 系統不崩潰
- 每個回覆都有意義
- 回覆之間不互相污染
- 無洩漏
"""
import re
import time
import pytest
import httpx

from tests.e2e.conftest import GATEWAY_URL

LEAK_PATTERNS = [
    r"^\*?\*?\[內在思考審視\]",
    r"^#{1,3}\s*(DNA27|MUSEON|Style Always|Style Never)",
    r"^-\s*(真實優先|演化至上|代價透明|長期複利)\s*[—–\-(（]",
]

RAPID_FIRE_MESSAGES = [
    {"msg": "台積電最近表現怎麼樣？", "expect_min": 30, "id": "stock"},
    {"msg": "幫我寫一封道歉信給客戶，因為交貨延遲了", "expect_min": 80, "id": "apology"},
    {"msg": "把剛才的道歉信翻譯成英文", "expect_min": 50, "id": "translate"},
    {"msg": "幫我分析一下今年台灣餐飲業的趨勢", "expect_min": 80, "id": "trend"},
    {"msg": "用一句話總結你剛才幫我做了哪些事？", "expect_min": 15, "id": "summary"},
]


class TestSC03RapidFire:
    """SC-03 高頻多指令轟炸"""

    def test_rapid_fire_sequence(self, collector, http_client):
        """連續 5 個不同任務，2 秒間隔"""
        session = f"e2e_rapid_{int(time.time())}"
        results = []

        for i, item in enumerate(RAPID_FIRE_MESSAGES):
            t0 = time.time()
            try:
                data = http_client.post(
                    f"{GATEWAY_URL}/webhook",
                    json={
                        "user_id": "boss",
                        "session_id": session,
                        "content": item["msg"],
                    },
                    timeout=120,
                ).json()
                ms = int((time.time() - t0) * 1000)
                resp = data.get("response", "")
                results.append({
                    "id": item["id"],
                    "msg": item["msg"],
                    "response": resp,
                    "ms": ms,
                    "ok": bool(resp.strip()) and len(resp) >= item["expect_min"],
                })
            except Exception as e:
                results.append({
                    "id": item["id"],
                    "msg": item["msg"],
                    "response": "",
                    "ms": int((time.time() - t0) * 1000),
                    "ok": False,
                    "error": str(e),
                })
            time.sleep(2)  # 2 秒間隔

        # 評估
        passed = sum(1 for r in results if r["ok"])
        total = len(results)

        for r in results:
            tid = f"sc03_rapid_{r['id']}"
            if r["ok"]:
                # 檢查洩漏
                leak = None
                for pat in LEAK_PATTERNS:
                    for line in r["response"].split("\n"):
                        if re.match(pat, line.strip()):
                            leak = line.strip()[:60]
                            break
                    if leak:
                        break
                if leak:
                    collector.record(tid, "D2.rapid_fire", "FAIL",
                                     f"洩漏: {leak}", severity="HIGH")
                else:
                    collector.record(tid, "D2.rapid_fire", "PASS",
                                     f"{r['ms']}ms, {len(r['response'])} chars")
            else:
                err = r.get("error", f"太短或空 ({len(r.get('response',''))} chars)")
                collector.record(tid, "D2.rapid_fire", "FAIL",
                                 err, severity="HIGH")

        if passed < total:
            pytest.fail(f"高頻轟炸 {passed}/{total} 通過")

    def test_no_cross_contamination(self, collector, http_client):
        """驗證不同任務的回覆不互相污染"""
        session = f"e2e_contam_{int(time.time())}"

        # 第一個任務：關於咖啡
        r1 = http_client.post(
            f"{GATEWAY_URL}/webhook",
            json={"user_id": "boss", "session_id": session,
                  "content": "幫我列出開咖啡店需要的設備清單"},
            timeout=120,
        ).json().get("response", "")

        time.sleep(2)

        # 第二個任務：關於寵物（完全不同的主題）
        r2 = http_client.post(
            f"{GATEWAY_URL}/webhook",
            json={"user_id": "boss", "session_id": session,
                  "content": "養一隻柴犬需要注意什麼？"},
            timeout=120,
        ).json().get("response", "")

        # 柴犬回覆不應該大量提到咖啡設備
        coffee_keywords = ["咖啡機", "磨豆機", "義式", "拉花"]
        contamination = [k for k in coffee_keywords if k in r2]

        if not contamination:
            collector.record("sc03_no_contamination", "D2.isolation", "PASS",
                             "不同主題回覆無交叉污染")
        else:
            collector.record("sc03_no_contamination", "D2.isolation", "WARN",
                             f"柴犬回覆中出現咖啡詞: {contamination}",
                             severity="MEDIUM")

    def test_gateway_stability_after_burst(self, collector, http_client):
        """轟炸後 Gateway 仍然健康"""
        try:
            resp = http_client.get(f"{GATEWAY_URL}/health", timeout=10)
            health = resp.json()
            if health.get("status") == "healthy":
                collector.record("sc03_post_burst_health", "D2.stability", "PASS",
                                 "轟炸後 Gateway 仍健康")
            else:
                collector.record("sc03_post_burst_health", "D2.stability", "FAIL",
                                 f"Gateway 不健康: {health}", severity="CRITICAL")
                pytest.fail("Gateway 不健康")
        except Exception as e:
            collector.record("sc03_post_burst_health", "D2.stability", "FAIL",
                             f"Gateway 無回應: {e}", severity="CRITICAL")
            pytest.fail(f"Gateway 無回應: {e}")
