"""
混沌注入測試 — 系統韌性壓測
驗證：
- 空輸入 / 超長輸入 / 特殊字元不崩潰
- 重複訊息不產生異常
- Unicode 邊界不崩潰
- Gateway 錯誤處理正確
"""
from __future__ import annotations
import re
import time
import pytest
import httpx

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


class TestChaosInjection:
    """混沌注入測試"""

    def test_empty_message(self, collector, http_client):
        """空訊息不崩潰"""
        try:
            resp = http_client.post(
                f"{GATEWAY_URL}/webhook",
                json={"user_id": "boss", "session_id": "chaos_empty",
                      "content": ""},
                timeout=30,
            )
            # 可能回 200 或 4xx，關鍵是不崩潰
            if resp.status_code < 500:
                collector.record("chaos_empty_msg", "D2.chaos", "PASS",
                                 f"空訊息處理正常 (HTTP {resp.status_code})")
            else:
                collector.record("chaos_empty_msg", "D2.chaos", "FAIL",
                                 f"空訊息導致 500: {resp.text[:100]}",
                                 severity="HIGH")
                pytest.fail(f"空訊息導致伺服器錯誤: {resp.status_code}")
        except Exception as e:
            collector.record("chaos_empty_msg", "D2.chaos", "FAIL",
                             f"空訊息崩潰: {e}", severity="CRITICAL")
            pytest.fail(f"空訊息崩潰: {e}")

    def test_whitespace_only_message(self, collector, http_client):
        """純空白訊息"""
        try:
            resp = http_client.post(
                f"{GATEWAY_URL}/webhook",
                json={"user_id": "boss", "session_id": "chaos_ws",
                      "content": "   \n\t  \n  "},
                timeout=30,
            )
            if resp.status_code < 500:
                collector.record("chaos_whitespace", "D2.chaos", "PASS",
                                 f"純空白處理正常 (HTTP {resp.status_code})")
            else:
                collector.record("chaos_whitespace", "D2.chaos", "FAIL",
                                 f"純空白導致 500", severity="HIGH")
        except Exception as e:
            collector.record("chaos_whitespace", "D2.chaos", "FAIL",
                             f"純空白崩潰: {e}", severity="CRITICAL")
            pytest.fail(f"純空白崩潰: {e}")

    def test_very_long_message(self, collector, http_client):
        """超長訊息（5000 字元）"""
        long_msg = "請幫我分析以下內容：" + "台灣的AI產業正在快速發展，" * 300
        try:
            t0 = time.time()
            resp = http_client.post(
                f"{GATEWAY_URL}/webhook",
                json={"user_id": "boss", "session_id": "chaos_long",
                      "content": long_msg},
                timeout=180,
            )
            ms = int((time.time() - t0) * 1000)
            if resp.status_code < 500:
                data = resp.json()
                response_text = data.get("response", "")
                collector.record("chaos_long_msg", "D2.chaos", "PASS",
                                 f"超長訊息處理正常 ({ms}ms, "
                                 f"input={len(long_msg)}, "
                                 f"output={len(response_text)} chars)")
            else:
                collector.record("chaos_long_msg", "D2.chaos", "FAIL",
                                 f"超長訊息導致 500", severity="HIGH")
        except httpx.ReadTimeout:
            collector.record("chaos_long_msg", "D2.chaos", "WARN",
                             "超長訊息處理超時（180s）", severity="MEDIUM")
        except Exception as e:
            collector.record("chaos_long_msg", "D2.chaos", "FAIL",
                             f"超長訊息崩潰: {e}", severity="CRITICAL")
            pytest.fail(f"超長訊息崩潰: {e}")

    def test_special_characters(self, collector, http_client):
        """特殊字元不崩潰"""
        special_msgs = [
            "🎉🔥💯🚀✨ emoji 壓測",
            "<script>alert('xss')</script>",
            "'; DROP TABLE users; --",
            "```python\nprint('hello')\n```",
            "\\n\\t\\r\\0 轉義字元",
            "𝕳𝖊𝖑𝖑𝖔 Unicode 擴展",
        ]
        passed = 0
        for msg in special_msgs:
            try:
                resp = http_client.post(
                    f"{GATEWAY_URL}/webhook",
                    json={"user_id": "boss",
                          "session_id": f"chaos_special_{passed}",
                          "content": msg},
                    timeout=60,
                )
                if resp.status_code < 500:
                    passed += 1
                else:
                    collector.record("chaos_special_chars", "D2.chaos", "FAIL",
                                     f"'{msg[:30]}' 導致 500", severity="HIGH")
                    pytest.fail(f"特殊字元導致崩潰: {msg[:30]}")
                    return
            except Exception as e:
                collector.record("chaos_special_chars", "D2.chaos", "FAIL",
                                 f"'{msg[:30]}' 崩潰: {e}", severity="CRITICAL")
                pytest.fail(f"特殊字元崩潰: {e}")
                return

        collector.record("chaos_special_chars", "D2.chaos", "PASS",
                         f"全部 {passed}/{len(special_msgs)} 特殊字元處理正常")

    def test_rapid_duplicate_messages(self, collector, http_client):
        """快速重複發送相同訊息"""
        session = f"chaos_dup_{int(time.time())}"
        msg = "你好"
        results = []
        for i in range(5):
            try:
                resp = http_client.post(
                    f"{GATEWAY_URL}/webhook",
                    json={"user_id": "boss", "session_id": session,
                          "content": msg},
                    timeout=60,
                )
                results.append(resp.status_code)
            except Exception:
                results.append(0)
            time.sleep(0.5)  # 0.5 秒間隔

        ok = sum(1 for r in results if r == 200)
        if ok == len(results):
            collector.record("chaos_rapid_dup", "D2.chaos", "PASS",
                             f"重複訊息全部正常 ({ok}/{len(results)})")
        elif ok > 0:
            collector.record("chaos_rapid_dup", "D2.chaos", "WARN",
                             f"重複訊息部分失敗: {results}", severity="MEDIUM")
        else:
            collector.record("chaos_rapid_dup", "D2.chaos", "FAIL",
                             f"重複訊息全部失敗: {results}", severity="HIGH")
            pytest.fail("重複訊息全部失敗")

    def test_missing_fields(self, collector, http_client):
        """缺少必要欄位"""
        bad_payloads = [
            ({}, "完全空"),
            ({"user_id": "boss"}, "缺 content"),
            ({"content": "hello"}, "缺 user_id"),
        ]
        all_handled = True
        for payload, label in bad_payloads:
            try:
                resp = http_client.post(
                    f"{GATEWAY_URL}/webhook",
                    json=payload,
                    timeout=15,
                )
                if resp.status_code >= 500:
                    all_handled = False
                    collector.record("chaos_missing_fields", "D2.chaos", "FAIL",
                                     f"{label} 導致 500", severity="HIGH")
                    pytest.fail(f"缺欄位導致 500: {label}")
                    return
            except Exception as e:
                all_handled = False
                collector.record("chaos_missing_fields", "D2.chaos", "FAIL",
                                 f"{label} 崩潰: {e}", severity="CRITICAL")
                pytest.fail(f"缺欄位崩潰: {e}")
                return

        if all_handled:
            collector.record("chaos_missing_fields", "D2.chaos", "PASS",
                             "缺欄位全部正確處理（非 500）")

    def test_invalid_json(self, collector, http_client):
        """無效 JSON"""
        try:
            resp = http_client.post(
                f"{GATEWAY_URL}/webhook",
                content=b"this is not json",
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            if resp.status_code < 500:
                collector.record("chaos_invalid_json", "D2.chaos", "PASS",
                                 f"無效 JSON 正確處理 (HTTP {resp.status_code})")
            else:
                collector.record("chaos_invalid_json", "D2.chaos", "FAIL",
                                 f"無效 JSON 導致 500", severity="HIGH")
        except Exception as e:
            collector.record("chaos_invalid_json", "D2.chaos", "FAIL",
                             f"無效 JSON 崩潰: {e}", severity="HIGH")

    def test_concurrent_different_sessions(self, collector, http_client):
        """不同 session 同時發送"""
        import concurrent.futures

        def send(session_id, content):
            try:
                with httpx.Client(timeout=120) as c:
                    resp = c.post(
                        f"{GATEWAY_URL}/webhook",
                        json={"user_id": "boss",
                              "session_id": session_id,
                              "content": content},
                    )
                    return resp.status_code, len(resp.json().get("response", ""))
            except Exception as e:
                return 0, str(e)

        ts = int(time.time())
        tasks = [
            (f"chaos_conc_{ts}_1", "用三句話介紹台灣"),
            (f"chaos_conc_{ts}_2", "用三句話介紹日本"),
            (f"chaos_conc_{ts}_3", "用三句話介紹韓國"),
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(send, sid, msg) for sid, msg in tasks]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        ok = sum(1 for status, _ in results if status == 200)
        if ok == len(tasks):
            collector.record("chaos_concurrent", "D2.concurrency", "PASS",
                             f"併發 {ok}/{len(tasks)} 全部成功")
        elif ok > 0:
            collector.record("chaos_concurrent", "D2.concurrency", "WARN",
                             f"併發部分失敗: {results}", severity="MEDIUM")
        else:
            collector.record("chaos_concurrent", "D2.concurrency", "FAIL",
                             f"併發全部失敗: {results}", severity="HIGH")

    def test_gateway_health_after_chaos(self, collector, http_client):
        """混沌注入後 Gateway 仍健康"""
        try:
            resp = http_client.get(f"{GATEWAY_URL}/health", timeout=10)
            health = resp.json()
            if health.get("status") == "healthy":
                collector.record("chaos_post_health", "D4.stability", "PASS",
                                 "混沌注入後 Gateway 仍健康")
            else:
                collector.record("chaos_post_health", "D4.stability", "FAIL",
                                 f"混沌後不健康: {health}", severity="CRITICAL")
                pytest.fail("混沌注入後 Gateway 不健康")
        except Exception as e:
            collector.record("chaos_post_health", "D4.stability", "FAIL",
                             f"混沌後無回應: {e}", severity="CRITICAL")
            pytest.fail(f"混沌後無回應: {e}")
