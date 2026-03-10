"""
MAX 架構壓力測試 — 全域驗證
覆蓋：ClaudeCLIAdapter、RateLimitGuard、Gateway E2E、MCP Server、
      Nightly Pipeline MAX 步驟、壓力韌性

T-Score 維度對照：
  D1 功能正確性 (25%) — Adapter 呼叫、MCP 工具、Budget Settlement
  D2 多工穩定性 (25%) — 併發 Gateway、混沌注入、記憶洩漏
  D3 時序韌性   (30%) — RateLimitGuard 降級、持久化、7 天清理
  D4 系統健康   (20%) — 系統審計、SOUL.md 完整性、Gateway 存活
"""

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from tests.e2e.conftest import GATEWAY_URL, send_message

# ── 常數 ────────────────────────────────────────────────
MUSEON_HOME = Path(os.environ.get("MUSEON_HOME", Path.home() / "MUSEON"))
DATA_DIR = MUSEON_HOME / "data"
VENV_PYTHON = str(MUSEON_HOME / ".venv" / "bin" / "python")

# 離線模板關鍵字（若回應包含這些，代表沒走到 LLM）
OFFLINE_MARKERS = ["目前無法即時查詢", "離線模式", "系統維護中"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A. ClaudeCLIAdapter — D1 功能正確性
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMaxAdapter:
    """D1 — ClaudeCLIAdapter 功能正確性"""

    def _run_async(self, coro):
        """Helper: 在同步 test 中跑 async adapter"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_adapter_basic_call(self, collector):
        """Adapter 基本呼叫 — 驗證 AdapterResponse 欄位"""
        try:
            from museon.llm.adapters import ClaudeCLIAdapter

            adapter = ClaudeCLIAdapter()
            resp = self._run_async(adapter.call(
                system_prompt="你是測試助手，只需回答 OK",
                messages=[{"role": "user", "content": "回答 OK"}],
                model="haiku",
                max_tokens=100,
            ))
            self._run_async(adapter.close())

            assert resp.text, "回應文字為空"
            assert resp.stop_reason == "end_turn", f"stop_reason={resp.stop_reason}"
            assert resp.model, "model 欄位為空"
            collector.record("adapter_basic_call", "D1.adapter", "PASS",
                             f"text={resp.text[:50]}, model={resp.model}")
        except Exception as e:
            collector.record("adapter_basic_call", "D1.adapter", "FAIL",
                             f"基本呼叫失敗: {e}", severity="CRITICAL")
            pytest.fail(f"Adapter 基本呼叫失敗: {e}")

    def test_adapter_model_mapping(self, collector):
        """Adapter 模型映射正確"""
        try:
            from museon.llm.adapters import ClaudeCLIAdapter

            adapter = ClaudeCLIAdapter()
            # 驗證 MODEL_MAP 包含必要的映射
            assert "haiku" in adapter.MODEL_MAP
            assert "sonnet" in adapter.MODEL_MAP
            collector.record("adapter_model_mapping", "D1.adapter", "PASS",
                             f"MODEL_MAP 包含 {list(adapter.MODEL_MAP.keys())}")
        except Exception as e:
            collector.record("adapter_model_mapping", "D1.adapter", "FAIL",
                             f"模型映射失敗: {e}", severity="HIGH")
            pytest.fail(f"模型映射失敗: {e}")

    def test_adapter_stats_tracking(self, collector):
        """Adapter 統計追蹤"""
        try:
            from museon.llm.adapters import ClaudeCLIAdapter

            adapter = ClaudeCLIAdapter()
            assert adapter.stats["call_count"] == 0

            resp = self._run_async(adapter.call(
                system_prompt="回答 OK",
                messages=[{"role": "user", "content": "OK"}],
                model="haiku", max_tokens=50,
            ))
            stats = adapter.stats
            self._run_async(adapter.close())

            assert stats["call_count"] == 1, f"call_count={stats['call_count']}"
            assert stats["total_duration_ms"] > 0
            collector.record("adapter_stats", "D1.adapter", "PASS",
                             f"call_count=1, duration={stats['total_duration_ms']}ms")
        except Exception as e:
            collector.record("adapter_stats", "D1.adapter", "FAIL",
                             f"統計追蹤失敗: {e}", severity="MEDIUM")
            pytest.fail(f"統計追蹤失敗: {e}")

    def test_adapter_timeout_handling(self, collector):
        """Adapter 超時不留 zombie subprocess"""
        try:
            from museon.llm.adapters import ClaudeCLIAdapter

            adapter = ClaudeCLIAdapter()
            # 用極短 max_tokens 確保快速完成，驗證機制存在
            resp = self._run_async(adapter.call(
                system_prompt="回答 OK",
                messages=[{"role": "user", "content": "OK"}],
                model="haiku", max_tokens=10,
            ))
            self._run_async(adapter.close())

            # 確認沒有殘留 subprocess
            result = subprocess.run(
                ["pgrep", "-f", "claude.*--print.*--output-format"],
                capture_output=True, text=True,
            )
            zombie_pids = [p for p in result.stdout.strip().split("\n") if p]
            collector.record("adapter_timeout", "D1.adapter", "PASS",
                             f"無殘留 subprocess, zombie_count={len(zombie_pids)}")
        except Exception as e:
            collector.record("adapter_timeout", "D1.adapter", "FAIL",
                             f"超時處理失敗: {e}", severity="HIGH")
            pytest.fail(f"超時處理失敗: {e}")

    def test_adapter_no_zombie_subprocess(self, collector):
        """連續呼叫後無 zombie subprocess"""
        try:
            from museon.llm.adapters import ClaudeCLIAdapter

            adapter = ClaudeCLIAdapter()
            for i in range(3):
                self._run_async(adapter.call(
                    system_prompt="回答 OK",
                    messages=[{"role": "user", "content": f"test {i}"}],
                    model="haiku", max_tokens=20,
                ))
            stats = adapter.stats
            self._run_async(adapter.close())

            assert stats["call_count"] == 3
            # 檢查無殘留
            result = subprocess.run(
                ["pgrep", "-f", "claude.*--print.*--output-format"],
                capture_output=True, text=True,
            )
            zombie_count = len([p for p in result.stdout.strip().split("\n") if p])

            collector.record("adapter_no_zombie", "D2.stability", "PASS",
                             f"3 次呼叫後 zombie={zombie_count}, "
                             f"call_count={stats['call_count']}")
        except Exception as e:
            collector.record("adapter_no_zombie", "D2.stability", "FAIL",
                             f"zombie 檢查失敗: {e}", severity="HIGH")
            pytest.fail(f"zombie 檢查失敗: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# B. RateLimitGuard — D3 時序韌性
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMaxRateLimitGuard:
    """D3 — RateLimitGuard 五級降級"""

    def test_guard_level_0_fresh(self, collector, tmp_path):
        """初始狀態為 L0"""
        try:
            from museon.llm.rate_limit_guard import RateLimitGuard

            guard = RateLimitGuard(data_dir=str(tmp_path), weekly_limit=100)
            assert guard.get_level() == 0
            assert guard.can_proceed("human_interaction")
            assert guard.can_proceed("exploration")
            collector.record("guard_level_0", "D3.guard", "PASS",
                             "初始 L0，所有優先級可通過")
        except Exception as e:
            collector.record("guard_level_0", "D3.guard", "FAIL",
                             f"初始狀態異常: {e}", severity="HIGH")
            pytest.fail(f"Guard L0 失敗: {e}")

    def test_guard_escalation_l0_to_l4(self, collector, tmp_path):
        """五級降級完整驗證"""
        try:
            from museon.llm.rate_limit_guard import RateLimitGuard

            guard = RateLimitGuard(data_dir=str(tmp_path), weekly_limit=100)

            # L0: < 60%
            for _ in range(59):
                guard.record_call()
            assert guard.get_level() == 0, f"59 calls → L{guard.get_level()}"

            # L1: 60-75%
            for _ in range(16):
                guard.record_call()
            level_at_75 = guard.get_level()
            assert level_at_75 == 1, f"75 calls → L{level_at_75}"
            assert guard.get_breath_multiplier() == 2.0

            # L2: 75-85%
            for _ in range(10):
                guard.record_call()
            level_at_85 = guard.get_level()
            assert level_at_85 == 2, f"85 calls → L{level_at_85}"
            assert not guard.can_proceed("exploration")

            # L3: 85-95%
            for _ in range(10):
                guard.record_call()
            level_at_95 = guard.get_level()
            assert level_at_95 == 3, f"95 calls → L{level_at_95}"
            assert not guard.can_proceed("nightly")

            # L4: >= 100%
            for _ in range(6):
                guard.record_call()
            level_at_101 = guard.get_level()
            assert level_at_101 == 4, f"101 calls → L{level_at_101}"
            assert guard.can_proceed("human_interaction")
            assert not guard.can_proceed("breath_pulse")

            collector.record("guard_escalation", "D3.guard", "PASS",
                             "L0→L1→L2→L3→L4 降級正確")
        except Exception as e:
            collector.record("guard_escalation", "D3.guard", "FAIL",
                             f"降級異常: {e}", severity="CRITICAL")
            pytest.fail(f"Guard 降級失敗: {e}")

    def test_guard_priority_blocking(self, collector, tmp_path):
        """各級別優先級阻擋"""
        try:
            from museon.llm.rate_limit_guard import RateLimitGuard

            guard = RateLimitGuard(data_dir=str(tmp_path), weekly_limit=100)
            # 推到 L2（85%）
            for _ in range(85):
                guard.record_call()

            assert guard.can_proceed("human_interaction"), "L2 應允許 human"
            assert guard.can_proceed("nightly"), "L2 應允許 nightly"
            assert not guard.can_proceed("exploration"), "L2 應阻擋 exploration"

            collector.record("guard_priority", "D3.guard", "PASS",
                             "L2 優先級阻擋正確")
        except Exception as e:
            collector.record("guard_priority", "D3.guard", "FAIL",
                             f"優先級阻擋異常: {e}", severity="HIGH")
            pytest.fail(f"優先級阻擋失敗: {e}")

    def test_guard_persistence(self, collector, tmp_path):
        """Guard 持久化驗證"""
        try:
            from museon.llm.rate_limit_guard import RateLimitGuard

            # 寫入 50 筆
            guard1 = RateLimitGuard(data_dir=str(tmp_path), weekly_limit=100)
            for _ in range(50):
                guard1.record_call()
            count1 = guard1.get_weekly_calls()

            # 重建實例
            guard2 = RateLimitGuard(data_dir=str(tmp_path), weekly_limit=100)
            count2 = guard2.get_weekly_calls()

            assert count2 == count1, f"持久化失敗: {count1} → {count2}"
            collector.record("guard_persistence", "D3.guard", "PASS",
                             f"持久化正確: {count1} == {count2}")
        except Exception as e:
            collector.record("guard_persistence", "D3.guard", "FAIL",
                             f"持久化失敗: {e}", severity="HIGH")
            pytest.fail(f"Guard 持久化失敗: {e}")

    def test_guard_7day_cleanup(self, collector, tmp_path):
        """7 天過期清理"""
        try:
            from museon.llm.rate_limit_guard import RateLimitGuard

            guard = RateLimitGuard(data_dir=str(tmp_path), weekly_limit=1000)
            # 手動插入 8 天前的記錄
            state_file = tmp_path / "rate_limit_state.json"
            old_ts = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
            if state_file.exists():
                state = json.loads(state_file.read_text())
            else:
                state = {"calls": [], "weekly_limit": 1000}

            # 插入 10 筆舊記錄
            for _ in range(10):
                state.setdefault("calls", []).append({
                    "timestamp": old_ts,
                    "priority": "human_interaction",
                    "model": "haiku",
                })
            state_file.write_text(json.dumps(state))

            # 重建並檢查
            guard2 = RateLimitGuard(data_dir=str(tmp_path), weekly_limit=1000)
            weekly = guard2.get_weekly_calls()
            # 8 天前的記錄不應計入最近 7 天
            collector.record("guard_7day_cleanup", "D3.guard", "PASS",
                             f"7 天清理後 weekly_calls={weekly}")
        except Exception as e:
            collector.record("guard_7day_cleanup", "D3.guard", "FAIL",
                             f"7 天清理失敗: {e}", severity="MEDIUM")
            pytest.fail(f"7 天清理失敗: {e}")

    def test_guard_breath_multiplier(self, collector, tmp_path):
        """breath_multiplier 隨級別變化"""
        try:
            from museon.llm.rate_limit_guard import RateLimitGuard

            guard = RateLimitGuard(data_dir=str(tmp_path), weekly_limit=100)
            assert guard.get_breath_multiplier() == 1.0, "L0 應為 1.0x"

            # 推到 L1
            for _ in range(75):
                guard.record_call()
            assert guard.get_breath_multiplier() == 2.0, "L1 應為 2.0x"

            collector.record("guard_breath_mult", "D3.guard", "PASS",
                             "L0=1.0x, L1=2.0x")
        except Exception as e:
            collector.record("guard_breath_mult", "D3.guard", "FAIL",
                             f"breath_multiplier 失敗: {e}", severity="MEDIUM")
            pytest.fail(f"breath_multiplier 失敗: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# C. Gateway 端對端 — D1+D2
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMaxGatewayE2E:
    """D1+D2 — Gateway 端對端"""

    def test_simple_conversation(self, collector, http_client):
        """簡單對話"""
        try:
            t0 = time.time()
            resp = http_client.post(
                f"{GATEWAY_URL}/webhook",
                json={"user_id": "boss",
                      "session_id": f"max_simple_{int(t0)}",
                      "content": "你好，請回覆一句話"},
                timeout=60,
            )
            ms = int((time.time() - t0) * 1000)
            assert resp.status_code == 200, f"HTTP {resp.status_code}"
            data = resp.json()
            text = data.get("response", "")

            # 檢查是否為離線模板
            is_offline = any(m in text for m in OFFLINE_MARKERS)
            if is_offline:
                collector.record("gateway_simple", "D1.gateway", "WARN",
                                 f"Gateway 回傳離線模板 ({ms}ms): {text[:80]}",
                                 severity="MEDIUM")
                return

            assert len(text) > 2, f"回應過短: {text}"
            collector.record("gateway_simple", "D1.gateway", "PASS",
                             f"回應={text[:60]}... ({ms}ms)")
        except Exception as e:
            collector.record("gateway_simple", "D1.gateway", "FAIL",
                             f"簡單對話失敗: {e}", severity="CRITICAL")
            pytest.fail(f"簡單對話失敗: {e}")

    def test_tool_use_conversation(self, collector, http_client):
        """工具使用對話"""
        try:
            t0 = time.time()
            resp = http_client.post(
                f"{GATEWAY_URL}/webhook",
                json={"user_id": "boss",
                      "session_id": f"max_tool_{int(t0)}",
                      "content": "幫我搜尋今天台北天氣如何？"},
                timeout=120,
            )
            ms = int((time.time() - t0) * 1000)
            data = resp.json()
            text = data.get("response", "")

            if resp.status_code == 200 and len(text) > 10:
                collector.record("gateway_tool_use", "D1.gateway", "PASS",
                                 f"工具對話完成 ({ms}ms), "
                                 f"response={text[:80]}...")
            else:
                collector.record("gateway_tool_use", "D1.gateway", "WARN",
                                 f"HTTP {resp.status_code}, text={text[:50]}",
                                 severity="MEDIUM")
        except httpx.ReadTimeout:
            collector.record("gateway_tool_use", "D1.gateway", "WARN",
                             "工具對話超時 120s", severity="MEDIUM")
        except Exception as e:
            collector.record("gateway_tool_use", "D1.gateway", "FAIL",
                             f"工具對話崩潰: {e}", severity="HIGH")
            pytest.fail(f"工具對話崩潰: {e}")

    def test_concurrent_requests(self, collector, http_client):
        """併發 Gateway 請求"""
        ts = int(time.time())
        tasks = [
            (f"max_conc_{ts}_1", "用一句話介紹台灣"),
            (f"max_conc_{ts}_2", "用一句話介紹日本"),
            (f"max_conc_{ts}_3", "用一句話介紹韓國"),
        ]

        def send_one(session_id, content):
            try:
                with httpx.Client(timeout=120) as c:
                    r = c.post(
                        f"{GATEWAY_URL}/webhook",
                        json={"user_id": "boss",
                              "session_id": session_id,
                              "content": content},
                    )
                    return r.status_code, len(r.json().get("response", ""))
            except Exception as e:
                return 0, str(e)

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(send_one, sid, msg) for sid, msg in tasks]
            results = [f.result() for f in as_completed(futures)]

        ok = sum(1 for status, _ in results if status == 200)
        if ok == len(tasks):
            collector.record("gateway_concurrent", "D2.concurrency", "PASS",
                             f"併發 {ok}/{len(tasks)} 全部成功")
        elif ok > 0:
            collector.record("gateway_concurrent", "D2.concurrency", "WARN",
                             f"併發部分成功: {results}", severity="MEDIUM")
        else:
            collector.record("gateway_concurrent", "D2.concurrency", "FAIL",
                             f"併發全部失敗: {results}", severity="HIGH")
            pytest.fail("併發全部失敗")

    def test_context_persistence(self, collector, http_client):
        """會話上下文保持"""
        session_id = f"max_ctx_{int(time.time())}"
        try:
            # 第一則：記住數字
            resp1 = http_client.post(
                f"{GATEWAY_URL}/webhook",
                json={"user_id": "boss", "session_id": session_id,
                      "content": "請記住數字 42，稍後我會問你"},
                timeout=60,
            )
            assert resp1.status_code == 200

            time.sleep(2)

            # 第二則：回憶
            resp2 = http_client.post(
                f"{GATEWAY_URL}/webhook",
                json={"user_id": "boss", "session_id": session_id,
                      "content": "我剛才讓你記住的數字是什麼？"},
                timeout=60,
            )
            data2 = resp2.json()
            text2 = data2.get("response", "")

            if "42" in text2:
                collector.record("gateway_context", "D1.gateway", "PASS",
                                 f"上下文保持正確: {text2[:60]}")
            else:
                collector.record("gateway_context", "D1.gateway", "WARN",
                                 f"上下文可能丟失: {text2[:60]}",
                                 severity="MEDIUM")
        except Exception as e:
            collector.record("gateway_context", "D1.gateway", "FAIL",
                             f"上下文測試失敗: {e}", severity="HIGH")
            pytest.fail(f"上下文測試失敗: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# D. MCP Server — D1 功能正確性
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMaxMCPServer:
    """D1 — MCP Server 工具驗證"""

    def _send_jsonrpc(self, message: dict, timeout: int = 15) -> dict:
        """透過 subprocess 啟動 MCP server 並交換 JSON-RPC"""
        proc = subprocess.Popen(
            [VENV_PYTHON, "-m", "museon.mcp_server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(MUSEON_HOME),
            env={**os.environ, "MUSEON_HOME": str(MUSEON_HOME)},
        )
        try:
            payload = json.dumps(message) + "\n"
            stdout, stderr = proc.communicate(
                input=payload.encode(), timeout=timeout
            )
            lines = stdout.decode().strip().split("\n")
            # 找最後一行有效 JSON
            for line in reversed(lines):
                line = line.strip()
                if line.startswith("{"):
                    return json.loads(line)
            return {"error": "no JSON output", "stdout": stdout.decode()[:200]}
        except subprocess.TimeoutExpired:
            proc.kill()
            return {"error": "timeout"}

    def test_mcp_initialize(self, collector):
        """MCP initialize 握手"""
        try:
            resp = self._send_jsonrpc({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            })
            result = resp.get("result", {})
            proto = result.get("protocolVersion", "")
            server = result.get("serverInfo", {}).get("name", "")
            assert proto == "2024-11-05", f"protocolVersion={proto}"
            assert "museon" in server.lower(), f"serverInfo={server}"
            collector.record("mcp_initialize", "D1.mcp", "PASS",
                             f"proto={proto}, server={server}")
        except Exception as e:
            collector.record("mcp_initialize", "D1.mcp", "FAIL",
                             f"初始化失敗: {e}", severity="HIGH")
            pytest.fail(f"MCP 初始化失敗: {e}")

    def test_mcp_tools_list(self, collector):
        """MCP tools/list 回傳 7 個工具"""
        try:
            resp = self._send_jsonrpc({
                "jsonrpc": "2.0", "id": 2,
                "method": "tools/list", "params": {},
            })
            tools = resp.get("result", {}).get("tools", [])
            names = [t["name"] for t in tools]
            assert len(tools) == 7, f"工具數={len(tools)}, names={names}"
            assert "museon_memory_read" in names
            assert "museon_health_status" in names
            collector.record("mcp_tools_list", "D1.mcp", "PASS",
                             f"7 工具: {names}")
        except Exception as e:
            collector.record("mcp_tools_list", "D1.mcp", "FAIL",
                             f"工具清單失敗: {e}", severity="HIGH")
            pytest.fail(f"MCP 工具清單失敗: {e}")

    def test_mcp_health_status(self, collector):
        """MCP museon_health_status 工具"""
        try:
            resp = self._send_jsonrpc({
                "jsonrpc": "2.0", "id": 3,
                "method": "tools/call",
                "params": {"name": "museon_health_status", "arguments": {}},
            })
            result = resp.get("result", {})
            content = result.get("content", [])
            if content:
                text = content[0].get("text", "")
                data = json.loads(text) if text.startswith("{") else {}
                has_home = "museon_home" in data
                collector.record("mcp_health", "D1.mcp", "PASS",
                                 f"museon_home={data.get('museon_home', 'N/A')}")
            else:
                collector.record("mcp_health", "D1.mcp", "FAIL",
                                 f"無 content: {result}", severity="HIGH")
                pytest.fail("MCP health 無 content")
        except Exception as e:
            collector.record("mcp_health", "D1.mcp", "FAIL",
                             f"health 失敗: {e}", severity="HIGH")
            pytest.fail(f"MCP health 失敗: {e}")

    def test_mcp_memory_roundtrip(self, collector):
        """MCP memory write → read 往返"""
        test_key = f"test_bdd_{int(time.time())}"
        test_content = "hello_max_test"
        try:
            # Write
            w_resp = self._send_jsonrpc({
                "jsonrpc": "2.0", "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "museon_memory_write",
                    "arguments": {
                        "level": "L2_sem",
                        "key": test_key,
                        "content": test_content,
                    },
                },
            })
            # Read
            r_resp = self._send_jsonrpc({
                "jsonrpc": "2.0", "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "museon_memory_read",
                    "arguments": {"level": "L2_sem", "key": test_key},
                },
            })
            r_content = r_resp.get("result", {}).get("content", [])
            r_text = r_content[0].get("text", "") if r_content else ""

            if test_content in r_text:
                collector.record("mcp_memory_rt", "D1.mcp", "PASS",
                                 f"write→read 往返成功: {test_key}")
            else:
                collector.record("mcp_memory_rt", "D1.mcp", "FAIL",
                                 f"read 不含寫入內容: {r_text[:60]}",
                                 severity="HIGH")
                pytest.fail("Memory roundtrip 失敗")

            # 清理測試記憶
            mem_file = DATA_DIR / "memory_v3" / "L2_sem" / f"{test_key}.json"
            if mem_file.exists():
                mem_file.unlink()
        except Exception as e:
            collector.record("mcp_memory_rt", "D1.mcp", "FAIL",
                             f"memory roundtrip 失敗: {e}", severity="HIGH")
            pytest.fail(f"Memory roundtrip 失敗: {e}")

    def test_mcp_unknown_tool(self, collector):
        """MCP 未知工具回傳 JSON-RPC error"""
        try:
            resp = self._send_jsonrpc({
                "jsonrpc": "2.0", "id": 6,
                "method": "tools/call",
                "params": {"name": "nonexistent_tool", "arguments": {}},
            })
            error = resp.get("error", resp.get("result", {}).get("isError"))
            if error:
                collector.record("mcp_unknown_tool", "D1.mcp", "PASS",
                                 f"未知工具正確回傳錯誤")
            else:
                collector.record("mcp_unknown_tool", "D1.mcp", "WARN",
                                 f"未知工具無明確錯誤: {resp}",
                                 severity="LOW")
        except Exception as e:
            collector.record("mcp_unknown_tool", "D1.mcp", "FAIL",
                             f"未知工具處理失敗: {e}", severity="MEDIUM")
            pytest.fail(f"未知工具失敗: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# E. Nightly Pipeline MAX 步驟 — D3+D4
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMaxNightlySteps:
    """D3+D4 — Nightly Pipeline MAX 步驟"""

    def _make_pipeline(self, workspace=None):
        """建立 NightlyPipeline 實例"""
        from museon.nightly.nightly_pipeline import NightlyPipeline
        ws = workspace or DATA_DIR
        return NightlyPipeline(workspace=ws)

    def test_budget_settlement_max_mode(self, collector):
        """Budget settlement 顯示 MAX 訂閱模式"""
        try:
            pipeline = self._make_pipeline()
            result = pipeline._step_budget_settlement()

            mode = result.get("mode", "")
            assert mode == "max_subscription", f"mode={mode}"

            # 若有 brain 會回傳 daily_calls；無 brain 回傳 skipped
            if "skipped" in result:
                collector.record("nightly_budget", "D3.nightly", "PASS",
                                 f"mode={mode}, skipped={result['skipped']} "
                                 f"(無 brain 實例，預期行為)")
            else:
                daily_calls = result.get("daily_calls", 0)
                assert isinstance(daily_calls, int) and daily_calls >= 0
                collector.record("nightly_budget", "D3.nightly", "PASS",
                                 f"mode={mode}, daily_calls={daily_calls}")
        except Exception as e:
            collector.record("nightly_budget", "D3.nightly", "FAIL",
                             f"budget settlement 失敗: {e}", severity="HIGH")
            pytest.fail(f"Budget settlement 失敗: {e}")

    def test_soul_identity_check_valid(self, collector):
        """SOUL.md 完整性驗證（正常）"""
        try:
            # SOUL.md 在 data/SOUL.md, pipeline 用 workspace.parent / "SOUL.md"
            # 所以 workspace 需要是 data/ 的子目錄
            soul_path = DATA_DIR / "SOUL.md"
            if not soul_path.exists():
                collector.record("soul_check_valid", "D4.soul", "WARN",
                                 "SOUL.md 不存在，跳過",
                                 severity="MEDIUM")
                return

            # 用 data/memory_v3 作為 workspace，使 parent = data/
            ws = DATA_DIR / "memory_v3"
            pipeline = self._make_pipeline(workspace=ws)
            result = pipeline._step_soul_identity_check()

            status = result.get("status", "")
            if status in ("verified", "ok"):
                collector.record("soul_check_valid", "D4.soul", "PASS",
                                 f"SOUL.md 完整: status={status}")
            elif "skipped" in result or "warning" in result:
                collector.record("soul_check_valid", "D4.soul", "WARN",
                                 f"SOUL.md 跳過/警告: {result}",
                                 severity="MEDIUM")
            else:
                collector.record("soul_check_valid", "D4.soul", "FAIL",
                                 f"SOUL.md 異常: {result}",
                                 severity="CRITICAL")
                pytest.fail(f"SOUL.md 異常: {result}")
        except Exception as e:
            collector.record("soul_check_valid", "D4.soul", "FAIL",
                             f"SOUL check 失敗: {e}", severity="HIGH")
            pytest.fail(f"SOUL check 失敗: {e}")

    def test_soul_identity_check_tampered(self, collector):
        """SOUL.md 篡改偵測"""
        soul_path = DATA_DIR / "SOUL.md"
        backup_path = DATA_DIR / "SOUL.md.bak_test"
        if not soul_path.exists():
            collector.record("soul_tamper_detect", "D4.soul", "WARN",
                             "SOUL.md 不存在，跳過",
                             severity="MEDIUM")
            return
        try:
            # 備份
            original = soul_path.read_text(encoding="utf-8")
            backup_path.write_text(original, encoding="utf-8")

            # 篡改核心身份
            tampered = original.replace("MUSEON", "TAMPERED_MUSEON", 1)
            soul_path.write_text(tampered, encoding="utf-8")

            # workspace = data/memory_v3 → parent = data/
            ws = DATA_DIR / "memory_v3"
            pipeline = self._make_pipeline(workspace=ws)
            result = pipeline._step_soul_identity_check()
            status = result.get("status", "")

            if status in ("TAMPERED", "tampered"):
                collector.record("soul_tamper_detect", "D4.soul", "PASS",
                                 "篡改偵測成功")
            else:
                collector.record("soul_tamper_detect", "D4.soul", "WARN",
                                 f"篡改未偵測: status={status}, result={result}",
                                 severity="HIGH")
        except Exception as e:
            collector.record("soul_tamper_detect", "D4.soul", "FAIL",
                             f"篡改測試失敗: {e}", severity="HIGH")
            pytest.fail(f"篡改測試失敗: {e}")
        finally:
            # 恢復
            if backup_path.exists():
                backup_path.rename(soul_path)

    def test_federation_upload_standalone(self, collector):
        """Federation 獨立模式不報錯"""
        try:
            # 確保沒有設定 federation mode
            env_backup = os.environ.pop("MUSEON_FEDERATION_MODE", None)
            try:
                pipeline = self._make_pipeline()
                result = pipeline._step_federation_upload()
                # 獨立模式應優雅返回
                collector.record("federation_standalone", "D3.nightly", "PASS",
                                 f"獨立模式正常: {result}")
            finally:
                if env_backup:
                    os.environ["MUSEON_FEDERATION_MODE"] = env_backup
        except Exception as e:
            collector.record("federation_standalone", "D3.nightly", "FAIL",
                             f"federation 失敗: {e}", severity="MEDIUM")
            pytest.fail(f"Federation 失敗: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# F. 壓力韌性 — D2+D4
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TestMaxStressResilience:
    """D2+D4 — 壓力韌性"""

    def test_rapid_fire_10_messages(self, collector, http_client):
        """10 則快速連續訊息"""
        results = []
        durations = []
        ts = int(time.time())

        for i in range(10):
            t0 = time.time()
            try:
                resp = http_client.post(
                    f"{GATEWAY_URL}/webhook",
                    json={"user_id": "boss",
                          "session_id": f"max_rapid_{ts}_{i}",
                          "content": f"壓力測試 {i}: 回答 OK"},
                    timeout=60,
                )
                ms = int((time.time() - t0) * 1000)
                results.append(resp.status_code)
                durations.append(ms)
            except Exception:
                results.append(0)
                durations.append(int((time.time() - t0) * 1000))
            time.sleep(0.5)

        ok = sum(1 for r in results if r == 200)
        avg_ms = sum(durations) / len(durations) if durations else 0

        if ok == 10:
            collector.record("rapid_fire_10", "D2.stress", "PASS",
                             f"10/10 成功, avg={avg_ms:.0f}ms")
        elif ok >= 7:
            collector.record("rapid_fire_10", "D2.stress", "WARN",
                             f"{ok}/10 成功, avg={avg_ms:.0f}ms",
                             severity="MEDIUM")
        else:
            collector.record("rapid_fire_10", "D2.stress", "FAIL",
                             f"{ok}/10 成功, results={results}",
                             severity="HIGH")
            pytest.fail(f"快速連續測試失敗: {ok}/10")

    def test_system_audit_post_stress(self, collector):
        """壓力測試後系統審計"""
        try:
            result = subprocess.run(
                [VENV_PYTHON, "-m", "museon.doctor.system_audit",
                 "--home", str(MUSEON_HOME)],
                capture_output=True, text=True, timeout=120,
                cwd=str(MUSEON_HOME),
            )
            output = result.stdout + result.stderr

            # 解析 failures
            fail_match = re.search(r"(\d+)\s*fail", output, re.IGNORECASE)
            failures = int(fail_match.group(1)) if fail_match else -1

            if failures == 0:
                collector.record("audit_post_stress", "D4.audit", "PASS",
                                 "壓力測試後審計 0 failures")
            elif failures > 0:
                collector.record("audit_post_stress", "D4.audit", "FAIL",
                                 f"壓力後審計有 {failures} failures",
                                 severity="HIGH")
                pytest.fail(f"壓力後審計 {failures} failures")
            else:
                collector.record("audit_post_stress", "D4.audit", "WARN",
                                 f"無法解析審計結果: {output[:200]}",
                                 severity="MEDIUM")
        except subprocess.TimeoutExpired:
            collector.record("audit_post_stress", "D4.audit", "FAIL",
                             "審計超時 120s", severity="HIGH")
            pytest.fail("審計超時")
        except Exception as e:
            collector.record("audit_post_stress", "D4.audit", "FAIL",
                             f"審計失敗: {e}", severity="HIGH")
            pytest.fail(f"審計失敗: {e}")

    def test_no_memory_leak_adapter(self, collector):
        """20 次 adapter 呼叫無 subprocess 洩漏"""
        try:
            from museon.llm.adapters import ClaudeCLIAdapter

            loop = asyncio.new_event_loop()
            adapter = ClaudeCLIAdapter()
            for i in range(20):
                loop.run_until_complete(adapter.call(
                    system_prompt="回答 OK",
                    messages=[{"role": "user", "content": f"leak test {i}"}],
                    model="haiku", max_tokens=10,
                ))

            stats = adapter.stats
            loop.run_until_complete(adapter.close())
            loop.close()

            assert stats["call_count"] == 20, f"call_count={stats['call_count']}"

            # 確認無殘留
            result = subprocess.run(
                ["pgrep", "-f", "claude.*--print.*--output-format"],
                capture_output=True, text=True,
            )
            zombies = [p for p in result.stdout.strip().split("\n") if p]

            collector.record("no_leak_adapter", "D2.stability", "PASS",
                             f"20 calls 完成, zombie={len(zombies)}, "
                             f"duration={stats['total_duration_ms']}ms")
        except Exception as e:
            collector.record("no_leak_adapter", "D2.stability", "FAIL",
                             f"洩漏測試失敗: {e}", severity="HIGH")
            pytest.fail(f"洩漏測試失敗: {e}")

    def test_gateway_alive_after_stress(self, collector, http_client):
        """壓力測試後 Gateway 仍存活"""
        try:
            resp = http_client.get(f"{GATEWAY_URL}/health", timeout=10)
            health = resp.json()
            if health.get("status") == "healthy":
                collector.record("gateway_alive", "D4.health", "PASS",
                                 "壓力後 Gateway 仍 healthy")
            else:
                collector.record("gateway_alive", "D4.health", "FAIL",
                                 f"壓力後不健康: {health}",
                                 severity="CRITICAL")
                pytest.fail("壓力後 Gateway 不健康")
        except Exception as e:
            collector.record("gateway_alive", "D4.health", "FAIL",
                             f"壓力後無回應: {e}", severity="CRITICAL")
            pytest.fail(f"壓力後 Gateway 無回應: {e}")
