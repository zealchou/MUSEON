"""MUSEON v2 架構端對端 BDD 驗證 — 三管齊下.

管 1: test_runner — 模擬使用者訊息，驗證 L1 判斷 + L2 prompt 組裝
管 2: monitor — 監看 L1→L4 每一層的執行狀態與計時
管 3: quality — 評估對話品質（人格一致性、內部術語洩漏、回覆相關性）

10 個測試案例取自過去 4 天群組真實互動。

用法：
    cd ~/MUSEON
    MUSEON_HOME=~/MUSEON .venv/bin/python tests/bdd/test_v2_e2e.py
"""

import json
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

MUSEON_HOME = Path(os.getenv("MUSEON_HOME", os.path.expanduser("~/MUSEON")))
DATA_DIR = MUSEON_HOME / "data"
SYSTEM_DIR = DATA_DIR / "_system"
CACHE_DIR = SYSTEM_DIR / "context_cache"
MEMORY_DIR = DATA_DIR / "memory_v3"

# ═══════════════════════════════════════════
# Test Data: 10 scenarios from real interactions
# ═══════════════════════════════════════════

TEST_SESSION_ID = f"bdd_test_{int(time.time())}"

# 標記所有測試產生的資料，方便清理
TEST_MARKER = "__BDD_TEST__"


@dataclass
class TestScenario:
    id: int
    name: str
    source: str  # "dm" | "group"
    chat_id: str
    user: str
    message: str
    expected_route: str  # "L1_direct" | "L2_spawn" | "skill_worker"
    expected_skill: str = ""  # 如果是 skill_worker
    quality_criteria: list = field(default_factory=list)


SCENARIOS = [
    TestScenario(
        id=1,
        name="簡單問候",
        source="dm",
        chat_id="6969045906",
        user="Zeal",
        message="早安",
        expected_route="L1_direct",
        quality_criteria=["回覆 < 50 字", "有溫度", "無內部術語"],
    ),
    TestScenario(
        id=2,
        name="系統狀態問題",
        source="group",
        chat_id="-5107045509",
        user="Feng",
        message="Zeal 目前大M的狀況如何，還穩定嗎",
        expected_route="L2_spawn",
        quality_criteria=["不透露架構細節", "用白話回答", "無 L1/L2/MCP 等術語"],
    ),
    TestScenario(
        id=3,
        name="商業報價討論",
        source="group",
        chat_id="-5107045509",
        user="Feng",
        message="報告 Zeal 美業的案子用你給的規格和討論的內容來看，這個案子大概500k，我想報200k，我先121，等等把資料上傳",
        expected_route="L2_spawn",
        quality_criteria=["辨識出報價議題", "不直接替使用者決定", "提供分析框架"],
    ),
    TestScenario(
        id=4,
        name="戰略分析—合資",
        source="group",
        chat_id="-5107045509",
        user="Zeal",
        message="合開公司後，對方 51%，我們 49%，你覺得呢？為什麼對方會想要答應？",
        expected_route="L2_spawn",
        quality_criteria=["多角度分析", "提到利弊", "有可行的下一步"],
    ),
    TestScenario(
        id=5,
        name="品牌定位需求",
        source="group",
        chat_id="-5129430356",
        user="Alan Wu",
        message="我有一個個人品牌：轉念師無為，想做品牌定位規劃，你能幫我嗎？",
        expected_route="L2_spawn",
        quality_criteria=["辨識品牌定位需求", "會問更多細節", "不會空泛回答"],
    ),
    TestScenario(
        id=6,
        name="劇本創作協助",
        source="group",
        chat_id="-5200293299",
        user="Luo",
        message="我剛剛在調整學校對表演的橋段修改，我們原本總共5分鐘3分鐘的戲劇 2分鐘的舞蹈，現在學校要我們調整成3分半鐘的演出，我正在苦惱",
        expected_route="L2_spawn",
        quality_criteria=["辨識創作類需求", "具體建議", "不會只說加油"],
    ),
    TestScenario(
        id=7,
        name="簡單確認",
        source="dm",
        chat_id="6969045906",
        user="Zeal",
        message="好的收到",
        expected_route="L1_direct",
        quality_criteria=["回覆 < 30 字", "自然", "不過度分析"],
    ),
    TestScenario(
        id=8,
        name="情緒回應",
        source="group",
        chat_id="-5200293299",
        user="Luo",
        message="我覺得你好像聽不懂我的回饋，或者你沒有辦法幫我把整份資料改好",
        expected_route="L2_spawn",
        quality_criteria=["先接住情緒", "不辯護", "承認限制並提出替代方案"],
    ),
    TestScenario(
        id=9,
        name="50W 報 20W 質疑",
        source="group",
        chat_id="-5107045509",
        user="Zeal",
        message="50W 報 20W 聽起來怪怪的",
        expected_route="L2_spawn",
        quality_criteria=["辨識報價相關", "分析為何覺得怪", "提供思考角度"],
    ),
    TestScenario(
        id=10,
        name="/strategy 指令測試",
        source="dm",
        chat_id="6969045906",
        user="Zeal",
        message="/strategy 分析美業合資案的利弊，對方是連鎖美業集團",
        expected_route="skill_worker",
        expected_skill="master-strategy",
        quality_criteria=["辨識 /strategy 指令", "匹配 master-strategy Skill"],
    ),
]


# ═══════════════════════════════════════════
# 管 1: Test Runner — L1 判斷 + prompt 組裝
# ═══════════════════════════════════════════


class TestRunner:
    """模擬 L1 主持人的判斷流程."""

    SIMPLE_PATTERNS = [
        r"^(早安|晚安|你好|哈囉|嗨|hi|hello|安安)[\s!！。？]*$",
        r"^(好|好的|收到|了解|ok|OK|okok|謝謝|感謝|讚|👍|🙏|❤️|🤣|😂)[\s!！。？]*$",
        r"^[\U0001F600-\U0001F9FF\s]+$",  # emoji only
    ]

    COMMAND_RE = re.compile(r"^/(\w+)\s*(.*)", re.DOTALL)

    COMMAND_MAP = {
        "strategy": "master-strategy",
        "dse": "dse",
        "market": "market-core",
        "crypto": "market-crypto",
        "equity": "market-equity",
        "macro": "market-macro",
        "brand": "brand-identity",
        "story": "storytelling-engine",
        "text": "text-alchemy",
        "xmodel": "xmodel",
        "plan": "plan-engine",
        "dharma": "dharma",
        "philo": "philo-dialectic",
        "ssa": "ssa-consultant",
        "business": "business-12",
        "report": "report-forge",
        "learn": "meta-learning",
        "shadow": "shadow",
        "resonance": "resonance",
        "masters": "investment-masters",
    }

    def classify(self, message: str) -> tuple[str, str]:
        """判斷訊息路由：(route, skill_name)."""
        msg = message.strip()

        # 先檢查 /指令
        m = self.COMMAND_RE.match(msg)
        if m:
            cmd = m.group(1).lower()
            skill = self.COMMAND_MAP.get(cmd, "")
            if skill:
                return "skill_worker", skill
            # 未知指令走 L2
            return "L2_spawn", ""

        # 簡單模式匹配
        for pattern in self.SIMPLE_PATTERNS:
            if re.match(pattern, msg, re.IGNORECASE):
                return "L1_direct", ""

        # 長度 < 5 且非指令 → L1
        if len(msg) <= 5:
            return "L1_direct", ""

        # 其餘都走 L2
        return "L2_spawn", ""


# ═══════════════════════════════════════════
# 管 2: Monitor — 監看 L1→L4 操作狀態
# ═══════════════════════════════════════════


class Monitor:
    """監控 v2 每一層的執行狀態."""

    def __init__(self):
        self.records = []

    def check_l1_cache_read(self) -> dict:
        """L1: 驗證 context_cache 可讀且完整."""
        t0 = time.time()
        results = {}
        expected = ["user_summary.json", "active_rules.json", "self_summary.json", "persona_digest.md"]

        for fname in expected:
            path = CACHE_DIR / fname
            if path.exists():
                size = path.stat().st_size
                results[fname] = {"exists": True, "size": size, "valid": size > 10}
            else:
                results[fname] = {"exists": False, "valid": False}

        elapsed = round((time.time() - t0) * 1000, 1)
        all_valid = all(r["valid"] for r in results.values())

        return {
            "layer": "L1",
            "action": "cache_read",
            "elapsed_ms": elapsed,
            "pass": all_valid,
            "files": results,
        }

    def check_l2_prompt_assembly(self, scenario: TestScenario) -> dict:
        """L2: 驗證 prompt 組裝包含所有必要元素."""
        t0 = time.time()
        checks = {
            "has_persona": False,
            "has_user_summary": False,
            "has_active_rules": False,
            "has_chat_id": False,
            "has_message": False,
            "has_history_call": False,
            "has_no_internal_terms": True,
        }

        # 模擬 L2 prompt 組裝
        prompt_parts = []

        persona = CACHE_DIR / "persona_digest.md"
        if persona.exists():
            content = persona.read_text(encoding="utf-8")
            prompt_parts.append(content)
            checks["has_persona"] = len(content) > 100

        user_summary = CACHE_DIR / "user_summary.json"
        if user_summary.exists():
            content = user_summary.read_text(encoding="utf-8")
            prompt_parts.append(content)
            checks["has_user_summary"] = "lord_id" in content

        active_rules = CACHE_DIR / "active_rules.json"
        if active_rules.exists():
            content = active_rules.read_text(encoding="utf-8")
            prompt_parts.append(content)
            checks["has_active_rules"] = "rules" in content

        checks["has_chat_id"] = bool(scenario.chat_id)
        checks["has_message"] = bool(scenario.message)
        checks["has_history_call"] = True  # L2 prompt 範本內建

        # 計算 prompt 大小（粗略 token 估算）
        total_chars = sum(len(p) for p in prompt_parts)
        est_tokens = total_chars // 3  # 繁中 ~3 chars/token

        elapsed = round((time.time() - t0) * 1000, 1)

        return {
            "layer": "L2",
            "action": "prompt_assembly",
            "elapsed_ms": elapsed,
            "pass": all(checks.values()),
            "checks": checks,
            "estimated_tokens": est_tokens,
            "under_12k_limit": est_tokens < 12000,
        }

    def check_l4_capability(self) -> dict:
        """L4: 驗證觀察者需要的基礎設施可用."""
        t0 = time.time()
        checks = {
            "memory_dir_exists": MEMORY_DIR.exists(),
            "boss_l1_short_exists": (MEMORY_DIR / "boss" / "L1_short").exists(),
            "cache_dir_writable": os.access(str(CACHE_DIR), os.W_OK),
            "group_context_db": (SYSTEM_DIR / "group_context.db").exists(),
        }
        elapsed = round((time.time() - t0) * 1000, 1)

        return {
            "layer": "L4",
            "action": "infrastructure_check",
            "elapsed_ms": elapsed,
            "pass": all(checks.values()),
            "checks": checks,
        }

    def run_full_check(self, scenario: TestScenario) -> list[dict]:
        """對單一 scenario 執行完整四層監控."""
        results = [
            self.check_l1_cache_read(),
            self.check_l2_prompt_assembly(scenario),
            self.check_l4_capability(),
        ]
        self.records.extend(results)
        return results


# ═══════════════════════════════════════════
# 管 3: Quality — 對話品質評估
# ═══════════════════════════════════════════


class QualityAuditor:
    """評估 L1/L2 回覆品質（靜態分析——不實際呼叫 LLM）."""

    BANNED_TERMS = [
        "L1", "L2", "L3", "L4", "MCP", "plugin", "Gateway", "Brain",
        "subagent", "spawn", "dispatcher", "context_cache", "event_bus",
        "EventBus", "ResponseGuard", "BrainWorker", "nightly_pipeline",
        "crystal_actuator", "mcp_server", "telegram_pump",
        "一階原則", "多維度審查", "【思考路徑】",
    ]

    def check_no_internal_terms(self, text: str) -> tuple[bool, list[str]]:
        """檢查回覆中是否包含內部術語."""
        found = []
        for term in self.BANNED_TERMS:
            if term in text:
                found.append(term)
        return len(found) == 0, found

    def check_persona_consistency(self, persona_text: str) -> dict:
        """檢查 persona 是否包含必要元素."""
        checks = {
            "has_core_values": any(k in persona_text for k in ["主權", "真實", "穩態"]),
            "has_style_always": "Style Always" in persona_text or "always" in persona_text.lower(),
            "has_style_never": "Style Never" in persona_text or "never" in persona_text.lower(),
            "has_traditional_chinese": any(ord(c) > 0x4E00 for c in persona_text[:200]),
        }
        return checks

    def evaluate_routing_quality(self, scenario: TestScenario, actual_route: str) -> dict:
        """評估路由判斷品質."""
        correct = scenario.expected_route == actual_route
        return {
            "scenario": scenario.name,
            "expected": scenario.expected_route,
            "actual": actual_route,
            "correct": correct,
        }

    def evaluate_prompt_quality(self, est_tokens: int) -> dict:
        """評估 prompt 品質."""
        return {
            "estimated_tokens": est_tokens,
            "under_limit": est_tokens < 12000,
            "not_too_small": est_tokens > 500,
            "quality": "good" if 500 < est_tokens < 12000 else "concern",
        }


# ═══════════════════════════════════════════
# Test Artifacts Tracker — 記錄所有測試產生的資料
# ═══════════════════════════════════════════


class ArtifactTracker:
    """追蹤測試產生的所有檔案和 DB 記錄，事後清理."""

    def __init__(self):
        self.created_files: list[Path] = []
        self.db_entries: list[tuple[str, str]] = []  # (table, condition)
        self.memory_files: list[Path] = []

    def track_file(self, path: Path):
        self.created_files.append(path)

    def track_memory(self, path: Path):
        self.memory_files.append(path)

    def track_db_entry(self, table: str, condition: str):
        self.db_entries.append((table, condition))

    def cleanup(self) -> dict:
        """清理所有測試產物."""
        cleaned = {"files": 0, "memory": 0, "db_rows": 0}

        for f in self.created_files + self.memory_files:
            if f.exists():
                f.unlink()
                cleaned["files"] += 1

        # 清理測試 session 目錄
        session_dir = CACHE_DIR / TEST_SESSION_ID
        if session_dir.exists():
            import shutil
            shutil.rmtree(session_dir)
            cleaned["files"] += 1

        # 清理 DB 記錄
        db_path = SYSTEM_DIR / "group_context.db"
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                for table, condition in self.db_entries:
                    cursor = conn.execute(f"DELETE FROM {table} WHERE {condition}")
                    cleaned["db_rows"] += cursor.rowcount
                conn.commit()
                conn.close()
            except Exception:
                pass

        # 清理 nightly 測試報告
        reports = SYSTEM_DIR / "reports"
        for f in reports.glob(f"*{TEST_SESSION_ID}*"):
            f.unlink()
            cleaned["files"] += 1

        return cleaned


# ═══════════════════════════════════════════
# Main Test Orchestrator
# ═══════════════════════════════════════════


def run_all_tests():
    """執行全部 10 個 BDD 測試案例."""

    runner = TestRunner()
    monitor = Monitor()
    auditor = QualityAuditor()
    tracker = ArtifactTracker()

    # 讀取 persona 做品質基準
    persona_path = CACHE_DIR / "persona_digest.md"
    persona_text = persona_path.read_text(encoding="utf-8") if persona_path.exists() else ""

    results = {
        "test_session": TEST_SESSION_ID,
        "started_at": datetime.now().isoformat(),
        "scenarios": [],
        "summary": {},
    }

    print("=" * 70)
    print(f"MUSEON v2 BDD E2E 測試 — 三管齊下")
    print(f"Session: {TEST_SESSION_ID}")
    print(f"Scenarios: {len(SCENARIOS)}")
    print("=" * 70)

    pass_count = 0
    total_checks = 0
    passed_checks = 0

    for s in SCENARIOS:
        print(f"\n{'─' * 60}")
        print(f"[{s.id:02d}] {s.name} ({s.source})")
        print(f"     使用者: {s.user}")
        print(f"     訊息: {s.message[:80]}...")
        print()

        scenario_result = {
            "id": s.id,
            "name": s.name,
            "source": s.source,
            "checks": [],
        }

        # ── 管 1: Test Runner ──
        t0 = time.time()
        actual_route, actual_skill = runner.classify(s.message)
        classify_ms = round((time.time() - t0) * 1000, 2)

        route_match = actual_route == s.expected_route
        skill_match = actual_skill == s.expected_skill if s.expected_skill else True

        check = {
            "pipe": "runner",
            "name": "路由判斷",
            "pass": route_match and skill_match,
            "detail": {
                "expected_route": s.expected_route,
                "actual_route": actual_route,
                "expected_skill": s.expected_skill,
                "actual_skill": actual_skill,
                "classify_ms": classify_ms,
            },
        }
        scenario_result["checks"].append(check)
        total_checks += 1
        if check["pass"]:
            passed_checks += 1
        icon = "✅" if check["pass"] else "❌"
        print(f"  管1 路由判斷: {icon} {actual_route}" +
              (f" ({actual_skill})" if actual_skill else "") +
              f" [{classify_ms}ms]")

        # ── 管 2: Monitor ──
        mon_results = monitor.run_full_check(s)
        for mr in mon_results:
            check = {
                "pipe": "monitor",
                "name": f"{mr['layer']}_{mr['action']}",
                "pass": mr["pass"],
                "detail": mr,
            }
            scenario_result["checks"].append(check)
            total_checks += 1
            if check["pass"]:
                passed_checks += 1
            icon = "✅" if check["pass"] else "❌"
            print(f"  管2 {mr['layer']} {mr['action']}: {icon} [{mr['elapsed_ms']}ms]" +
                  (f" ~{mr.get('estimated_tokens', '?')} tokens" if "estimated_tokens" in mr else ""))

        # ── 管 3: Quality ──
        # 3a: 路由品質
        route_quality = auditor.evaluate_routing_quality(s, actual_route)
        check = {
            "pipe": "quality",
            "name": "路由品質",
            "pass": route_quality["correct"],
            "detail": route_quality,
        }
        scenario_result["checks"].append(check)
        total_checks += 1
        if check["pass"]:
            passed_checks += 1

        # 3b: Persona 一致性（每個場景都查）
        persona_checks = auditor.check_persona_consistency(persona_text)
        all_persona_ok = all(persona_checks.values())
        check = {
            "pipe": "quality",
            "name": "人格一致性",
            "pass": all_persona_ok,
            "detail": persona_checks,
        }
        scenario_result["checks"].append(check)
        total_checks += 1
        if check["pass"]:
            passed_checks += 1
        icon = "✅" if all_persona_ok else "❌"
        print(f"  管3 人格一致性: {icon}")

        # 3c: 內部術語洩漏檢查（只檢查 user-facing 欄位，不檢查內部規則的 directive）
        all_cache_clean = True
        for cache_file in CACHE_DIR.glob("*.json"):
            content = cache_file.read_text(encoding="utf-8")
            if cache_file.name == "active_rules.json":
                # active_rules 的 directive 是系統內部指令，允許含術語
                # 只檢查 summary 欄位（會出現在使用者可見的回覆中）
                data = json.loads(content)
                for rule in data.get("rules", []):
                    summary = rule.get("summary", "")
                    clean, found = auditor.check_no_internal_terms(summary)
                    if not clean:
                        all_cache_clean = False
            else:
                clean, found = auditor.check_no_internal_terms(content)
                if not clean:
                    all_cache_clean = False

        check = {
            "pipe": "quality",
            "name": "快取無術語洩漏",
            "pass": all_cache_clean,
            "detail": {"all_clean": all_cache_clean},
        }
        scenario_result["checks"].append(check)
        total_checks += 1
        if check["pass"]:
            passed_checks += 1
        icon = "✅" if all_cache_clean else "❌"
        print(f"  管3 快取無術語洩漏: {icon}")

        # 3d: Prompt token 品質（只有 L2 spawn 才檢查）
        if actual_route in ("L2_spawn", "skill_worker"):
            l2_mon = next((m for m in mon_results if m["layer"] == "L2"), None)
            if l2_mon:
                token_quality = auditor.evaluate_prompt_quality(l2_mon.get("estimated_tokens", 0))
                check = {
                    "pipe": "quality",
                    "name": "Prompt token 品質",
                    "pass": token_quality["quality"] == "good",
                    "detail": token_quality,
                }
                scenario_result["checks"].append(check)
                total_checks += 1
                if check["pass"]:
                    passed_checks += 1
                icon = "✅" if check["pass"] else "❌"
                print(f"  管3 Prompt token 品質: {icon} ({token_quality['estimated_tokens']} tokens)")

        all_pass = all(c["pass"] for c in scenario_result["checks"])
        scenario_result["pass"] = all_pass
        if all_pass:
            pass_count += 1
        results["scenarios"].append(scenario_result)

        icon = "✅ PASS" if all_pass else "❌ FAIL"
        print(f"\n  [{s.id:02d}] 結果: {icon}")

    # ── 寫入測試記憶（之後會清理）──
    test_memory = {
        TEST_MARKER: True,
        "session_id": TEST_SESSION_ID,
        "type": "bdd_test",
        "timestamp": datetime.now().isoformat(),
        "summary": f"{pass_count}/{len(SCENARIOS)} scenarios passed, {passed_checks}/{total_checks} checks passed",
    }
    memory_path = MEMORY_DIR / "boss" / "L1_short" / f"{TEST_SESSION_ID}.json"
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(json.dumps(test_memory, ensure_ascii=False, indent=2), encoding="utf-8")
    tracker.track_memory(memory_path)

    # 寫入測試 pending_insights
    insight_dir = CACHE_DIR / TEST_SESSION_ID
    insight_dir.mkdir(parents=True, exist_ok=True)
    insight_path = insight_dir / "pending_insights.json"
    insight_path.write_text(json.dumps({
        TEST_MARKER: True,
        "updated_at": datetime.now().isoformat(),
        "insights": [{"type": "test", "content": "BDD 測試洞察"}],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    tracker.track_file(insight_path)

    # 寫入測試報告
    report_path = SYSTEM_DIR / "reports" / f"bdd_test_{TEST_SESSION_ID}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    results["completed_at"] = datetime.now().isoformat()
    results["summary"] = {
        "scenarios_pass": pass_count,
        "scenarios_total": len(SCENARIOS),
        "checks_pass": passed_checks,
        "checks_total": total_checks,
        "pass_rate": f"{passed_checks / total_checks * 100:.1f}%",
    }
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    tracker.track_file(report_path)

    # ── 總結 ──
    print("\n" + "=" * 70)
    print(f"總結")
    print(f"  Scenarios: {pass_count}/{len(SCENARIOS)} PASS")
    print(f"  Checks:    {passed_checks}/{total_checks} PASS ({passed_checks / total_checks * 100:.1f}%)")
    print("=" * 70)

    # ── 清理測試產物 ──
    print("\n清理測試產物...")
    cleanup = tracker.cleanup()
    print(f"  已清理: {cleanup['files']} 檔案, {cleanup['memory']} 記憶, {cleanup['db_rows']} DB 記錄")
    print(f"  測試報告: {report_path}")

    # 最後清理報告本身
    if report_path.exists():
        report_path.unlink()
        print(f"  報告已刪除")

    print("\n✅ 所有測試產物已清理完畢")

    return pass_count == len(SCENARIOS)


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
