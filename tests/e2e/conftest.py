"""
MUSEON E2E 壓力測試 — 共用設定
硬限制：整個測試套件最多跑 2 小時（7200 秒）
"""
import pytest
import time
import json
import os
import signal
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

# ============================================================
# 全域常數
# ============================================================
MAX_TEST_DURATION_SECONDS = 7200  # 2 小時硬限制
GATEWAY_URL = "http://127.0.0.1:8765"
TEST_START_TIME = None
REPORT_DIR = Path(__file__).parent / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
TW_TZ = timezone(timedelta(hours=8))


# ============================================================
# 2 小時硬限制 — 超時自動中止
# ============================================================
class TestTimeoutError(Exception):
    pass


def timeout_handler(signum, frame):
    raise TestTimeoutError(
        f"\n{'='*60}\n"
        f"⏰ 測試套件已達 2 小時時限，自動中止。\n"
        f"已完成的測試結果保存在 {REPORT_DIR}\n"
        f"{'='*60}"
    )


@pytest.fixture(scope="session", autouse=True)
def enforce_2hr_limit():
    global TEST_START_TIME
    TEST_START_TIME = time.time()
    if hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(MAX_TEST_DURATION_SECONDS)
    yield
    if hasattr(signal, 'SIGALRM'):
        signal.alarm(0)


@pytest.fixture(autouse=True)
def check_remaining_time():
    if TEST_START_TIME:
        elapsed = time.time() - TEST_START_TIME
        remaining = MAX_TEST_DURATION_SECONDS - elapsed
        if remaining <= 0:
            pytest.skip("⏰ 已超過 2 小時時限")
        elif remaining < 300:
            print(f"\n⚠️ 剩餘時間不足 5 分鐘（{remaining:.0f}秒）")


# ============================================================
# 測試結果收集器
# ============================================================
class TestResultCollector:
    def __init__(self):
        self.results = []
        self.start_time = datetime.now(TW_TZ)

    def record(self, test_name: str, category: str, status: str,
               detail: str = "", severity: str = "INFO"):
        self.results.append({
            "timestamp": datetime.now(TW_TZ).isoformat(),
            "test": test_name,
            "category": category,
            "status": status,
            "detail": detail,
            "severity": severity,
        })

    def generate_report(self) -> str:
        end_time = datetime.now(TW_TZ)
        duration = (end_time - self.start_time).total_seconds()
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        warned = sum(1 for r in self.results if r["status"] == "WARN")
        skipped = sum(1 for r in self.results if r["status"] == "SKIP")

        verdict = (
            f"🔴 FAIL — 有 {failed} 項失敗需修復" if failed > 0
            else "🟢 PASS — 全部通過" if warned == 0
            else f"🟡 WARN — 通過但有 {warned} 項警告"
        )

        report = f"""# 🔥 壓力熔爐測試報告

## 基本資訊
- **執行時間**：{self.start_time.strftime('%Y-%m-%d %H:%M:%S')} → {end_time.strftime('%H:%M:%S')} (CST)
- **耗時**：{duration:.0f} 秒（上限 7200 秒）
- **結果**：✅ {passed} / ❌ {failed} / ⚠️ {warned} / ⏭️ {skipped} — 共 {total} 項

## 綜合判定
{verdict}

## T-Score（壓力品質分）
| 維度 | 分數 | 說明 |
|------|------|------|
| D1 功能正確性 | {self._dim_score('D1')}/1.0 | 基本功能是否正確 |
| D2 多工穩定性 | {self._dim_score('D2')}/1.0 | 併行不崩潰不汙染 |
| D3 時序韌性 | {self._dim_score('D3')}/1.0 | 排程+時間處理 |
| D4 系統健康 | {self._dim_score('D4')}/1.0 | 心跳+DNA27+Mode 分流 |
| **綜合** | **{self._total_score()}/1.0** | 0.25×D1 + 0.25×D2 + 0.30×D3 + 0.20×D4 |

## ❌ 失敗項目（需修復）
"""
        for r in self.results:
            if r["status"] == "FAIL":
                report += f"- **[{r['severity']}]** `{r['test']}` — {r['detail']}\n"

        report += "\n## ⚠️ 警告項目（建議修復）\n"
        for r in self.results:
            if r["status"] == "WARN":
                report += f"- **[{r['severity']}]** `{r['test']}` — {r['detail']}\n"

        report += "\n## ✅ 通過項目\n"
        for r in self.results:
            if r["status"] == "PASS":
                report += f"- `{r['test']}` — {r['detail']}\n"

        return report

    def _dim_score(self, dim: str) -> str:
        items = [r for r in self.results if r["category"].startswith(dim)]
        if not items:
            return "N/A"
        p = sum(1 for r in items if r["status"] == "PASS")
        return f"{p / len(items):.2f}"

    def _total_score(self) -> str:
        scores = []
        weights = {"D1": 0.25, "D2": 0.25, "D3": 0.30, "D4": 0.20}
        for dim, w in weights.items():
            items = [r for r in self.results if r["category"].startswith(dim)]
            if items:
                s = sum(1 for r in items if r["status"] == "PASS") / len(items)
                scores.append(s * w)
        return f"{sum(scores):.2f}" if scores else "N/A"


@pytest.fixture(scope="session")
def collector():
    c = TestResultCollector()
    yield c
    report = c.generate_report()
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = REPORT_DIR / f"CRUCIBLE_REPORT_{ts}.md"
    report_path.write_text(report, encoding="utf-8")
    # JSON 版
    json_path = REPORT_DIR / f"CRUCIBLE_REPORT_{ts}.json"
    json_path.write_text(
        json.dumps(c.results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n{'='*60}")
    print(f"📋 測試報告：{report_path}")
    print(f"{'='*60}")
    print(report)


@pytest.fixture(scope="session")
def gateway():
    """驗證 Gateway 可用並回傳 health data."""
    with httpx.Client(timeout=10) as client:
        try:
            resp = client.get(f"{GATEWAY_URL}/health")
            health = resp.json()
            assert health.get("status") == "healthy", f"Gateway unhealthy: {health}"
            return health
        except Exception as e:
            pytest.fail(f"Gateway 無法連線: {e}")


@pytest.fixture(scope="session")
def http_client():
    """共用的 httpx 同步客戶端."""
    client = httpx.Client(timeout=120)
    yield client
    client.close()


def send_message(client: httpx.Client, content: str,
                 user_id: str = "boss",
                 session_id: str = "e2e_crucible") -> dict:
    """送出訊息並回傳 response dict."""
    resp = client.post(
        f"{GATEWAY_URL}/webhook",
        json={
            "user_id": user_id,
            "session_id": session_id,
            "content": content,
        },
    )
    resp.raise_for_status()
    return resp.json()
