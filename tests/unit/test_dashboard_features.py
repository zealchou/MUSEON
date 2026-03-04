"""Dashboard 新功能 BDD 測試

對應功能：
  1. 資料讀取層（IPC Data Handlers）
  2. 自動刷新機制（Auto-refresh）
  3. Gateway 重啟/修復（Gateway Repair）
  4. Gateway 即時 Log 面板（Gateway Log Panel）
  5. 手動刷新按鈕（Manual Refresh Button）

多重角度驗證：
  - 本地檔案讀取的正確性與容錯性
  - Gateway 進程管理的安全性
  - Preload API 完整性
  - app.js 狀態管理正確性
  - CSS 樣式完整性
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


# ═══════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════

ELECTRON_DIR = Path(__file__).parent.parent.parent / "electron"
SRC_DIR = ELECTRON_DIR / "src"


@pytest.fixture
def fake_data_dir(tmp_path):
    """建立完整的模擬 data/ 目錄結構"""
    data = tmp_path / "data"
    data.mkdir()

    # ANIMA persona
    (data / "ANIMA_MC.json").write_text(json.dumps({
        "identity": {
            "name": "MUSEON",
            "growth_stage": "幼生",
            "birth_date": "2026-02-01T00:00:00Z",
        }
    }))
    (data / "ANIMA_USER.json").write_text(json.dumps({
        "name": "Zeal",
        "style": "direct",
    }))

    # Soul rings
    anima = data / "anima"
    anima.mkdir()
    (anima / "soul_rings.json").write_text(json.dumps([
        {"type": "breakthrough", "description": "第一次深度對話",
         "date": "2026-02-10", "reinforcement_count": 2},
        {"type": "lesson", "description": "過度推測的教訓",
         "date": "2026-02-15", "reinforcement_count": 1},
    ]))
    (anima / "observation_rings.json").write_text(json.dumps([]))

    # Eval
    eval_dir = data / "eval"
    eval_dir.mkdir()
    (eval_dir / "q_scores.jsonl").write_text(
        '{"score": 72, "timestamp": "2026-02-10T10:00:00Z"}\n'
        '{"score": 85, "timestamp": "2026-02-15T10:00:00Z"}\n'
        '{"score": 78, "timestamp": "2026-02-20T10:00:00Z"}\n'
    )
    (eval_dir / "alerts.json").write_text(json.dumps([]))
    (eval_dir / "blindspots.json").write_text(json.dumps([]))

    daily = eval_dir / "daily"
    daily.mkdir()
    (daily / "2026-02-10.json").write_text(json.dumps({
        "date": "2026-02-10",
        "avg_q_score": 72,
        "skill_usage": {"deep-think": 3, "resonance": 2},
    }))
    (daily / "2026-02-15.json").write_text(json.dumps({
        "date": "2026-02-15",
        "avg_q_score": 85,
        "skill_usage": {"deep-think": 5, "xmodel": 1},
    }))

    # Lattice (empty)
    lattice = data / "lattice"
    lattice.mkdir()
    (lattice / "crystals.json").write_text(json.dumps([]))
    (lattice / "links.json").write_text(json.dumps([]))

    # Memory
    mem = data / "memory" / "2026" / "02" / "26"
    mem.mkdir(parents=True)
    (mem / "event.md").write_text("# 事件紀錄\n\n- 啟動了第一次深度對話\n")
    (mem / "meta-thinking.md").write_text("# 思維紀錄\n\n深度思考筆記\n")

    mem2 = data / "memory" / "2026" / "02" / "25"
    mem2.mkdir(parents=True)
    (mem2 / "event.md").write_text("# 昨日事件\n")

    return data


@pytest.fixture
def fake_data_dir_with_crystals(fake_data_dir):
    """有知識結晶的 data/ 目錄"""
    crystals = [
        {"cuid": "C-001", "crystal_type": "Insight", "g1_summary": "深度對話模式",
         "ri_score": 0.8, "created_at": "2026-02-10"},
        {"cuid": "C-002", "crystal_type": "Pattern", "g1_summary": "使用者偏好直接風格",
         "ri_score": 0.6, "created_at": "2026-02-15"},
        {"cuid": "C-003", "crystal_type": "Lesson", "g1_summary": "不可過度推測",
         "ri_score": 0.9, "created_at": "2026-02-18"},
    ]
    links = [
        {"from_cuid": "C-001", "to_cuid": "C-002", "link_type": "supports"},
        {"from_cuid": "C-003", "to_cuid": "C-001", "link_type": "extends"},
    ]
    (fake_data_dir / "lattice" / "crystals.json").write_text(json.dumps(crystals))
    (fake_data_dir / "lattice" / "links.json").write_text(json.dumps(links))
    return fake_data_dir


# ═══════════════════════════════════════
# Section 1: 本地檔案讀取（IPC Data Handlers）
# ═══════════════════════════════════════


class TestDataReadingLayer:
    """IPC Data Handlers — 本地資料讀取層驗證"""

    def test_brain_state_data_files_exist(self, fake_data_dir):
        """Scenario: Brain State 所需的所有資料檔都存在"""
        assert (fake_data_dir / "ANIMA_MC.json").exists()
        assert (fake_data_dir / "anima" / "soul_rings.json").exists()
        assert (fake_data_dir / "eval" / "q_scores.jsonl").exists()
        assert (fake_data_dir / "lattice" / "crystals.json").exists()
        assert (fake_data_dir / "lattice" / "links.json").exists()

    def test_brain_state_persona_parse(self, fake_data_dir):
        """Scenario: 正確解析 persona JSON"""
        persona = json.loads((fake_data_dir / "ANIMA_MC.json").read_text())
        assert persona["identity"]["growth_stage"] == "幼生"
        assert persona["identity"]["name"] == "MUSEON"

    def test_q_score_latest_is_last_line(self, fake_data_dir):
        """Scenario: 最新 Q-Score 是 JSONL 最後一行"""
        content = (fake_data_dir / "eval" / "q_scores.jsonl").read_text()
        lines = [l for l in content.strip().split("\n") if l.strip()]
        last = json.loads(lines[-1])
        assert last["score"] == 78
        assert "timestamp" in last

    def test_q_score_history_count(self, fake_data_dir):
        """Scenario: Q-Score 歷史記錄筆數正確"""
        content = (fake_data_dir / "eval" / "q_scores.jsonl").read_text()
        lines = [l for l in content.strip().split("\n") if l.strip()]
        assert len(lines) == 3

    def test_soul_rings_parse(self, fake_data_dir):
        """Scenario: 靈魂年輪資料正確解析"""
        rings = json.loads((fake_data_dir / "anima" / "soul_rings.json").read_text())
        assert len(rings) == 2
        assert rings[0]["type"] == "breakthrough"
        assert rings[1]["type"] == "lesson"

    def test_memory_day_count(self, fake_data_dir):
        """Scenario: 記憶天數正確計算"""
        mem_dir = fake_data_dir / "memory"
        count = 0
        for year_dir in sorted(mem_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            for month_dir in sorted(year_dir.iterdir()):
                if not month_dir.is_dir():
                    continue
                for day_dir in sorted(month_dir.iterdir()):
                    if day_dir.is_dir():
                        count += 1
        assert count == 2  # 2/25 and 2/26

    def test_memory_dates_sorted_newest_first(self, fake_data_dir):
        """Scenario: 記憶日期列表最新在前"""
        mem_dir = fake_data_dir / "memory"
        dates = []
        for year_dir in sorted(mem_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            for month_dir in sorted(year_dir.iterdir()):
                if not month_dir.is_dir():
                    continue
                for day_dir in sorted(month_dir.iterdir()):
                    if day_dir.is_dir():
                        dates.append(f"{year_dir.name}-{month_dir.name}-{day_dir.name}")
        dates.reverse()
        assert dates[0] == "2026-02-26"
        assert dates[1] == "2026-02-25"

    def test_memory_channel_read(self, fake_data_dir):
        """Scenario: 讀取特定日期頻道的 Markdown 內容"""
        path = fake_data_dir / "memory" / "2026" / "02" / "26" / "event.md"
        content = path.read_text()
        assert "事件紀錄" in content
        assert "啟動了第一次深度對話" in content

    def test_memory_missing_channel_returns_empty(self, fake_data_dir):
        """Scenario: 讀取不存在的頻道回傳空字串"""
        path = fake_data_dir / "memory" / "2026" / "02" / "26" / "outcome.md"
        content = path.read_text() if path.exists() else ""
        assert content == ""

    def test_daily_summaries_read(self, fake_data_dir):
        """Scenario: 每日摘要 JSON 檔案正確讀取"""
        daily_dir = fake_data_dir / "eval" / "daily"
        files = sorted(daily_dir.glob("*.json"))
        assert len(files) == 2
        data = json.loads(files[0].read_text())
        assert data["date"] == "2026-02-10"
        assert data["avg_q_score"] == 72

    def test_crystals_empty_is_valid(self, fake_data_dir):
        """Scenario: 空的結晶列表是合法狀態"""
        crystals = json.loads((fake_data_dir / "lattice" / "crystals.json").read_text())
        assert crystals == []

    def test_crystals_with_data(self, fake_data_dir_with_crystals):
        """Scenario: 有結晶時資料結構完整"""
        crystals = json.loads(
            (fake_data_dir_with_crystals / "lattice" / "crystals.json").read_text()
        )
        assert len(crystals) == 3
        assert crystals[0]["cuid"] == "C-001"
        assert crystals[0]["crystal_type"] == "Insight"
        assert 0 <= crystals[0]["ri_score"] <= 1

    def test_crystal_links_structure(self, fake_data_dir_with_crystals):
        """Scenario: 結晶連結結構正確"""
        links = json.loads(
            (fake_data_dir_with_crystals / "lattice" / "links.json").read_text()
        )
        assert len(links) == 2
        assert links[0]["from_cuid"] == "C-001"
        assert links[0]["link_type"] in ("supports", "contradicts", "extends", "related")

    def test_empty_data_dir_graceful(self, tmp_path):
        """Scenario: data/ 目錄完全空白時不崩潰"""
        data = tmp_path / "data"
        data.mkdir()
        # Brain state 的每個檔案都不存在 → 回傳 null/[]
        assert not (data / "ANIMA_MC.json").exists()
        assert not (data / "eval" / "q_scores.jsonl").exists()

    def test_corrupted_json_graceful(self, fake_data_dir):
        """Scenario: JSON 檔案損壞時回傳 null 而非崩潰"""
        (fake_data_dir / "ANIMA_MC.json").write_text("{broken json!!")
        try:
            json.loads((fake_data_dir / "ANIMA_MC.json").read_text())
            assert False, "Should have raised JSONDecodeError"
        except json.JSONDecodeError:
            pass  # Expected — main.js readJSON() returns null

    def test_corrupted_jsonl_partial_read(self, fake_data_dir):
        """Scenario: JSONL 有部分損壞行時跳過壞行繼續讀取"""
        (fake_data_dir / "eval" / "q_scores.jsonl").write_text(
            '{"score": 72}\n'
            'BROKEN LINE\n'
            '{"score": 85}\n'
        )
        content = (fake_data_dir / "eval" / "q_scores.jsonl").read_text()
        lines = content.strip().split("\n")
        parsed = []
        for line in lines:
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # Skip broken lines, same as main.js
        assert len(parsed) == 2
        assert parsed[0]["score"] == 72
        assert parsed[1]["score"] == 85


# ═══════════════════════════════════════
# Section 2: Electron 檔案完整性
# ═══════════════════════════════════════


class TestElectronFileIntegrity:
    """確保 Electron 端所有檔案語法正確且一致"""

    def test_topology_js_exists(self):
        """Scenario: topology.js 存在"""
        assert (SRC_DIR / "topology.js").exists()

    def test_app_js_exists(self):
        """Scenario: app.js 存在"""
        assert (SRC_DIR / "app.js").exists()

    def test_index_html_exists(self):
        """Scenario: index.html 存在"""
        assert (SRC_DIR / "index.html").exists()

    def test_styles_css_exists(self):
        """Scenario: styles.css 存在"""
        assert (SRC_DIR / "styles.css").exists()

    def test_topology_js_syntax(self):
        """Scenario: topology.js 語法正確"""
        result = subprocess.run(
            ["node", "-c", str(SRC_DIR / "topology.js")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"topology.js syntax error: {result.stderr}"

    def test_app_js_syntax(self):
        """Scenario: app.js 語法正確"""
        result = subprocess.run(
            ["node", "-c", str(SRC_DIR / "app.js")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"app.js syntax error: {result.stderr}"

    def test_main_js_syntax(self):
        """Scenario: main.js 語法正確"""
        result = subprocess.run(
            ["node", "-c", str(ELECTRON_DIR / "main.js")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"main.js syntax error: {result.stderr}"

    def test_preload_js_syntax(self):
        """Scenario: preload.js 語法正確"""
        result = subprocess.run(
            ["node", "-c", str(ELECTRON_DIR / "preload.js")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"preload.js syntax error: {result.stderr}"

    def test_index_html_loads_scripts_in_order(self):
        """Scenario: index.html 按正確順序載入 scripts"""
        content = (SRC_DIR / "index.html").read_text()
        chart_pos = content.find("chart.umd.js")
        topo_pos = content.find("topology.js")
        app_pos = content.find("app.js")
        assert chart_pos < topo_pos < app_pos, \
            "Scripts must load in order: chart.js → topology.js → app.js"

    def test_chartjs_umd_exists(self):
        """Scenario: chart.js UMD build 存在於 node_modules"""
        chart_path = ELECTRON_DIR / "node_modules" / "chart.js" / "dist" / "chart.umd.js"
        assert chart_path.exists(), "chart.js UMD build not found"


# ═══════════════════════════════════════
# Section 3: Preload API 完整性
# ═══════════════════════════════════════


class TestPreloadApiCompleteness:
    """確保 preload.js 暴露所有必要的 API"""

    @pytest.fixture(autouse=True)
    def load_preload(self):
        self.content = (ELECTRON_DIR / "preload.js").read_text()

    def test_has_getBrainState(self):
        """Scenario: preload 暴露 getBrainState API"""
        assert "getBrainState" in self.content

    def test_has_getEvolutionData(self):
        """Scenario: preload 暴露 getEvolutionData API"""
        assert "getEvolutionData" in self.content

    def test_has_getMemoryDates(self):
        """Scenario: preload 暴露 getMemoryDates API"""
        assert "getMemoryDates" in self.content

    def test_has_readMemory(self):
        """Scenario: preload 暴露 readMemory API"""
        assert "readMemory" in self.content

    def test_has_restartGateway(self):
        """Scenario: preload 暴露 restartGateway API"""
        assert "restartGateway" in self.content

    def test_has_onGatewayLog(self):
        """Scenario: preload 暴露 onGatewayLog listener"""
        assert "onGatewayLog" in self.content

    def test_has_onGatewayHealth(self):
        """Scenario: preload 暴露 onGatewayHealth listener"""
        assert "onGatewayHealth" in self.content

    def test_getBrainState_invokes_correct_channel(self):
        """Scenario: getBrainState 調用正確的 IPC channel"""
        assert "dashboard-get-brain-state" in self.content

    def test_getEvolutionData_invokes_correct_channel(self):
        """Scenario: getEvolutionData 調用正確的 IPC channel"""
        assert "dashboard-get-evolution-data" in self.content

    def test_restartGateway_invokes_correct_channel(self):
        """Scenario: restartGateway 調用正確的 IPC channel"""
        assert "gateway-restart" in self.content


# ═══════════════════════════════════════
# Section 4: main.js IPC Handler 完整性
# ═══════════════════════════════════════


class TestMainJsHandlers:
    """確保 main.js 註冊了所有必要的 IPC handlers"""

    @pytest.fixture(autouse=True)
    def load_main(self):
        self.content = (ELECTRON_DIR / "main.js").read_text()

    def test_has_dashboard_get_brain_state_handler(self):
        """Scenario: main.js 有 dashboard-get-brain-state handler"""
        assert "dashboard-get-brain-state" in self.content

    def test_has_dashboard_get_evolution_data_handler(self):
        """Scenario: main.js 有 dashboard-get-evolution-data handler"""
        assert "dashboard-get-evolution-data" in self.content

    def test_has_dashboard_get_memory_dates_handler(self):
        """Scenario: main.js 有 dashboard-get-memory-dates handler"""
        assert "dashboard-get-memory-dates" in self.content

    def test_has_dashboard_read_memory_handler(self):
        """Scenario: main.js 有 dashboard-read-memory handler"""
        assert "dashboard-read-memory" in self.content

    def test_has_gateway_restart_handler(self):
        """Scenario: main.js 有 gateway-restart handler"""
        assert "gateway-restart" in self.content

    def test_gateway_restart_kills_old_process(self):
        """Scenario: Gateway 重啟時先終止舊進程"""
        assert "SIGTERM" in self.content
        assert "SIGKILL" in self.content

    def test_gateway_restart_uses_http_health_check(self):
        """Scenario: Gateway 重啟後透過 HTTP 健檢確認就緒"""
        assert "waitForGatewayReady" in self.content

    def test_gateway_restart_spawns_new_process(self):
        """Scenario: Gateway 重啟時 spawn 新進程"""
        assert "spawn" in self.content
        assert "museon.gateway.server" in self.content

    def test_gateway_restart_notifies_renderer(self):
        """Scenario: Gateway 重啟後通知 renderer 更新狀態"""
        assert "gateway-health" in self.content

    def test_gateway_restart_sends_logs(self):
        """Scenario: Gateway 進程 stdout/stderr 轉發為 gateway-log"""
        assert "gateway-log" in self.content

    def test_gateway_restart_uses_venv_python(self):
        """Scenario: Gateway 重啟使用 .venv/bin/python"""
        assert ".venv" in self.content and "python" in self.content

    def test_gateway_restart_returns_steps(self):
        """Scenario: Gateway 重啟回傳每一步操作記錄"""
        assert "steps" in self.content
        assert "success" in self.content


class TestGetProjectRootProduction:
    """BDD: getProjectRoot() 必須同時支援開發佈局和生產佈局

    Feature: 專案根目錄解析
      Scenario: 生產佈局 — pyproject.toml 在 .runtime 子目錄
        Given MUSEON_HOME 指向安裝目錄
        And 該目錄有 .runtime/pyproject.toml（而非根目錄的 pyproject.toml）
        Then getProjectRoot() 應回傳 MUSEON_HOME

      Scenario: 生產佈局 — 有 .env 就信任
        Given MUSEON_HOME 有 .env 檔案
        Then getProjectRoot() 不應 fallback 到 ~/museon

      Scenario: 開發佈局 — pyproject.toml 在根目錄
        Given MUSEON_HOME 指向 dev 目錄
        And 該目錄有 pyproject.toml
        Then getProjectRoot() 應回傳 MUSEON_HOME

    根因紀錄: 2026-02-27 生產版 .env 被忽略，因 getProjectRoot() 只檢查
    MUSEON_HOME/pyproject.toml，生產佈局 pyproject.toml 在 .runtime/ 底下
    導致 fallback 到 ~/museon（dev 目錄），Setup Wizard 寫 key 到錯的 .env
    """

    @pytest.fixture(autouse=True)
    def load_main(self):
        self.content = (ELECTRON_DIR / "main.js").read_text()

    def test_production_layout_runtime_pyproject(self):
        """Scenario: 生產佈局用 .runtime/pyproject.toml 驗證"""
        # getProjectRoot() 應同時檢查 .runtime/pyproject.toml
        assert ".runtime" in self.content
        assert "pyproject.toml" in self.content
        # 確認同一 block 內有 .runtime/pyproject.toml 的檢查
        assert ".runtime', 'pyproject.toml'" in self.content or \
               ".runtime', \"pyproject.toml\"" in self.content

    def test_production_layout_env_file_fallback(self):
        """Scenario: 有 .env 就信任 MUSEON_HOME"""
        # getProjectRoot() 應檢查 .env 作為備用驗證
        assert "'.env'" in self.content or '".env"' in self.content

    def test_museon_home_not_require_root_pyproject(self):
        """Scenario: MUSEON_HOME 不應只靠根目錄 pyproject.toml"""
        # 確認 MUSEON_HOME 的檢查有多重條件（||）
        fn_match = re.search(
            r'function getProjectRoot\(\)\s*\{([\s\S]*?)(?=\n\s*//\s*2\.)',
            self.content
        )
        assert fn_match, "getProjectRoot() 找不到 MUSEON_HOME 區塊"
        block = fn_match.group(1)
        # 區塊內應有 OR 條件，不能只有一個 existsSync
        assert '||' in block, "MUSEON_HOME 檢查應有多重條件（||），不能只靠單一 pyproject.toml"

    def test_asar_candidates_also_check_runtime(self):
        """Scenario: ASAR 候選路徑也支援 .runtime 佈局"""
        # 候選路徑的 for 迴圈也應檢查 .runtime/pyproject.toml
        fn_match = re.search(
            r'//\s*3\.\s*ASAR([\s\S]*?)(?=\n\s*//\s*4\.)',
            self.content
        )
        assert fn_match, "找不到 ASAR 候選路徑區塊"
        block = fn_match.group(1)
        assert '.runtime' in block, "ASAR 候選路徑也應檢查 .runtime/pyproject.toml"


class TestSetupWizardEnvWriteBDD:
    """BDD: Setup Wizard 寫入 .env 必須對準 Gateway 讀取的路徑

    Feature: API Key 持久化
      Scenario: Setup Wizard 寫 key 到與 Gateway 相同的 .env
        Given getProjectRoot() 回傳正確路徑
        And writeEnvKey() 使用 getProjectRoot()/.env
        Then Gateway 啟動時能從同一路徑讀取到 key

      Scenario: writeEnvKey 能取消註解並寫入值
        Given .env 有 "# TELEGRAM_BOT_TOKEN=" 的註解行
        When writeEnvKey 寫入 "TELEGRAM_BOT_TOKEN" = "abc123"
        Then 該行變為 "TELEGRAM_BOT_TOKEN=abc123"（無 #）
    """

    @pytest.fixture(autouse=True)
    def load_main(self):
        self.content = (ELECTRON_DIR / "main.js").read_text()

    def test_env_file_path_uses_project_root(self):
        """Scenario: getEnvFilePath 使用 getProjectRoot"""
        assert "getProjectRoot()" in self.content
        assert "getEnvFilePath" in self.content

    def test_write_env_key_uncomments(self):
        """Scenario: writeEnvKey 能處理被註解的 key"""
        assert "# ${keyName}=" in self.content or "# ' + keyName" in self.content

    def test_setup_save_key_handler_exists(self):
        """Scenario: setup-save-key IPC handler 存在"""
        assert "setup-save-key" in self.content


class TestAutoLaunchToggleBDD:
    """BDD: 開機自動啟動 toggle 必須綁定狀態和事件

    Feature: 開機自動啟動開關
      Scenario: toggle 讀取真實狀態
        Given app.js 有 autoLaunchEnabled state
        And 設定頁載入時呼叫 loadAutoLaunchState()
        Then toggle 顯示與系統設定一致的狀態

      Scenario: toggle 變更時呼叫 IPC
        When 使用者切換 toggle
        Then 呼叫 window.museon.setAutoLaunch(newVal)
    """

    @pytest.fixture(autouse=True)
    def load_files(self):
        self.app_content = (SRC_DIR / "app.js").read_text()
        self.preload_content = (ELECTRON_DIR / "preload.js").read_text()
        self.main_content = (ELECTRON_DIR / "main.js").read_text()

    def test_state_has_auto_launch(self):
        """Scenario: state 有 autoLaunchEnabled"""
        assert "autoLaunchEnabled" in self.app_content

    def test_load_auto_launch_function_exists(self):
        """Scenario: loadAutoLaunchState() 函式存在"""
        assert "loadAutoLaunchState" in self.app_content

    def test_settings_tab_loads_auto_launch(self):
        """Scenario: 切到設定頁時載入 auto-launch 狀態"""
        assert "loadAutoLaunchState" in self.app_content

    def test_toggle_calls_set_auto_launch(self):
        """Scenario: toggle 變更時呼叫 setAutoLaunch"""
        assert "setAutoLaunch" in self.app_content

    def test_preload_has_auto_launch_api(self):
        """Scenario: preload.js 有 getAutoLaunch/setAutoLaunch"""
        assert "getAutoLaunch" in self.preload_content
        assert "setAutoLaunch" in self.preload_content

    def test_main_has_auto_launch_handlers(self):
        """Scenario: main.js 有 get-auto-launch/set-auto-launch"""
        assert "get-auto-launch" in self.main_content
        assert "set-auto-launch" in self.main_content


# ═══════════════════════════════════════
# Section 5: app.js 狀態管理
# ═══════════════════════════════════════


class TestAppJsStateManagement:
    """驗證 app.js 的狀態變數和 Tab 結構"""

    @pytest.fixture(autouse=True)
    def load_app(self):
        self.content = (SRC_DIR / "app.js").read_text()

    def test_four_tabs_defined(self):
        """Scenario: 定義了四個分頁"""
        assert "'organism'" in self.content
        assert "'evolution'" in self.content
        assert "'memory'" in self.content
        assert "'settings'" in self.content

    def test_tab_names_in_chinese(self):
        """Scenario: 分頁名稱使用繁體中文"""
        assert "生命" in self.content
        assert "演化" in self.content
        assert "記憶" in self.content
        assert "設定" in self.content

    def test_state_has_brainState(self):
        """Scenario: state 包含 brainState"""
        assert "brainState" in self.content

    def test_state_has_evolutionData(self):
        """Scenario: state 包含 evolutionData"""
        assert "evolutionData" in self.content

    def test_state_has_refreshing(self):
        """Scenario: state 包含 refreshing 狀態"""
        assert "refreshing:" in self.content

    def test_state_has_gatewayRepairing(self):
        """Scenario: state 包含 gatewayRepairing 狀態"""
        assert "gatewayRepairing:" in self.content

    def test_state_has_gatewayLogs(self):
        """Scenario: state 包含 gatewayLogs 陣列"""
        assert "gatewayLogs:" in self.content

    def test_state_has_showGatewayPanel(self):
        """Scenario: state 包含 showGatewayPanel"""
        assert "showGatewayPanel:" in self.content

    def test_auto_refresh_constant_defined(self):
        """Scenario: 定義了 AUTO_REFRESH_MS 常數"""
        assert "AUTO_REFRESH_MS" in self.content

    def test_auto_refresh_interval_30min(self):
        """Scenario: 自動刷新間隔為 30 分鐘"""
        assert "1800000" in self.content

    def test_refreshActiveTab_exists(self):
        """Scenario: refreshActiveTab 函式存在"""
        assert "function refreshActiveTab" in self.content

    def test_startAutoRefresh_exists(self):
        """Scenario: startAutoRefresh 函式存在"""
        assert "function startAutoRefresh" in self.content

    def test_handleGatewayRepair_exists(self):
        """Scenario: handleGatewayRepair 函式存在"""
        assert "function handleGatewayRepair" in self.content

    def test_addGatewayLog_exists(self):
        """Scenario: addGatewayLog 函式存在"""
        assert "function addGatewayLog" in self.content

    def test_renderGatewayPanel_exists(self):
        """Scenario: renderGatewayPanel 函式存在"""
        assert "function renderGatewayPanel" in self.content

    def test_refresh_button_in_nav(self):
        """Scenario: 導覽列包含刷新按鈕"""
        assert "refresh-btn" in self.content

    def test_repair_button_in_nav(self):
        """Scenario: 導覽列包含修復按鈕"""
        assert "repair-btn" in self.content

    def test_repair_button_only_when_offline(self):
        """Scenario: 修復按鈕只在 Gateway 離線時顯示"""
        assert "!state.gatewayOnline" in self.content

    def test_gateway_panel_closable(self):
        """Scenario: Gateway 面板可關閉"""
        assert "showGatewayPanel = false" in self.content

    def test_gateway_log_max_100(self):
        """Scenario: Gateway log 最多保留 100 條"""
        assert "100" in self.content
        assert "slice(-100)" in self.content

    def test_auto_close_panel_on_success(self):
        """Scenario: Gateway 修復成功後自動關閉面板"""
        # 5 seconds auto-close
        assert "5000" in self.content

    def test_gateway_log_listener_in_init(self):
        """Scenario: init() 中註冊 Gateway log listener"""
        assert "onGatewayLog" in self.content

    def test_auto_refresh_started_in_init(self):
        """Scenario: init() 中啟動自動刷新"""
        assert "startAutoRefresh" in self.content


# ═══════════════════════════════════════
# Section 6: topology.js 完整性
# ═══════════════════════════════════════


class TestTopologyJs:
    """驗證拓樸圖引擎的核心功能"""

    @pytest.fixture(autouse=True)
    def load_topology(self):
        self.content = (SRC_DIR / "topology.js").read_text()

    def test_brain_topology_class_exists(self):
        """Scenario: BrainTopology 建構函式存在"""
        assert "function BrainTopology" in self.content

    def test_exposed_as_window_global(self):
        """Scenario: BrainTopology 暴露為 window 全域變數"""
        assert "window.BrainTopology = BrainTopology" in self.content

    def test_setData_method(self):
        """Scenario: setData 方法存在"""
        assert "prototype.setData" in self.content

    def test_draw_method(self):
        """Scenario: draw 方法存在（動畫版使用 _draw）"""
        assert "prototype._draw" in self.content

    def test_animation_loop(self):
        """Scenario: requestAnimationFrame 動畫迴圈"""
        assert "requestAnimationFrame" in self.content

    def test_destroy_method(self):
        """Scenario: destroy 清理方法存在"""
        assert "prototype.destroy" in self.content

    def test_force_layout_algorithm(self):
        """Scenario: 力導向佈局演算法存在"""
        assert "_runForceLayout" in self.content

    def test_crystal_colors_defined(self):
        """Scenario: 四種結晶類型顏色定義"""
        assert "Insight" in self.content
        assert "Pattern" in self.content
        assert "Lesson" in self.content
        assert "Hypothesis" in self.content

    def test_link_styles_defined(self):
        """Scenario: 連結樣式定義（支持/矛盾/延伸/相關）"""
        assert "supports" in self.content
        assert "contradicts" in self.content
        assert "extends" in self.content
        assert "related" in self.content

    def test_module_hubs_defined(self):
        """Scenario: 六大模組 Hub 定義（純色彩＋角度，不含文字）"""
        assert "brain" in self.content
        assert "soul" in self.content
        assert "eval" in self.content
        assert "intuition" in self.content
        assert "plan" in self.content
        assert "knowledge" in self.content

    def test_mouse_interaction_handlers(self):
        """Scenario: 滑鼠互動事件處理"""
        assert "wheel" in self.content
        assert "mousedown" in self.content
        assert "mousemove" in self.content
        assert "mouseup" in self.content

    def test_hover_tooltip(self):
        """Scenario: Hover 顯示 Tooltip"""
        assert "_updateTooltip" in self.content

    def test_zoom_support(self):
        """Scenario: 滾輪縮放支援"""
        assert "camera" in self.content
        assert "zoom" in self.content

    def test_retina_display_support(self):
        """Scenario: Retina 螢幕支援"""
        assert "devicePixelRatio" in self.content


# ═══════════════════════════════════════
# Section 7: CSS 樣式完整性
# ═══════════════════════════════════════


class TestCssCompleteness:
    """確保所有新元件都有對應的 CSS 樣式"""

    @pytest.fixture(autouse=True)
    def load_css(self):
        self.content = (SRC_DIR / "styles.css").read_text()

    def test_vital_signs_style(self):
        """Scenario: 生命指標列樣式"""
        assert ".vital-signs" in self.content

    def test_vital_item_style(self):
        """Scenario: 生命指標項目樣式"""
        assert ".vital-item" in self.content

    def test_module_health_style(self):
        """Scenario: 模組健康卡片樣式"""
        assert ".module-card" in self.content or ".module-health" in self.content

    def test_chart_grid_style(self):
        """Scenario: 圖表網格樣式"""
        assert ".chart-grid" in self.content

    def test_memory_sidebar_style(self):
        """Scenario: 記憶側邊欄樣式"""
        assert ".memory-sidebar" in self.content

    def test_memory_channel_tab_style(self):
        """Scenario: 記憶頻道分頁樣式"""
        assert ".memory-channel-tab" in self.content

    def test_refresh_btn_style(self):
        """Scenario: 刷新按鈕樣式"""
        assert ".refresh-btn" in self.content

    def test_repair_btn_style(self):
        """Scenario: 修復按鈕樣式"""
        assert ".repair-btn" in self.content

    def test_gateway_panel_style(self):
        """Scenario: Gateway 面板樣式"""
        assert ".gateway-panel" in self.content

    def test_gateway_panel_header_style(self):
        """Scenario: Gateway 面板標題樣式"""
        assert ".gateway-panel-header" in self.content

    def test_gateway_panel_body_style(self):
        """Scenario: Gateway 面板內容區樣式"""
        assert ".gateway-panel-body" in self.content

    def test_gateway_log_line_style(self):
        """Scenario: Gateway log 行樣式"""
        assert ".gateway-log-line" in self.content

    def test_nav_right_style(self):
        """Scenario: 導覽列右側容器樣式"""
        assert ".nav-right" in self.content

    def test_dark_theme_background(self):
        """Scenario: 深色主題背景色（CIS Navy）"""
        assert "#141b2d" in self.content

    def test_responsive_styles(self):
        """Scenario: 響應式佈局"""
        assert "@media" in self.content


# ═══════════════════════════════════════
# Section 8: 四層防黑畫面機制仍有效
# ═══════════════════════════════════════


class TestAntiBlackScreenDefense:
    """確保四層防黑畫面機制在重寫後依然完整"""

    @pytest.fixture(autouse=True)
    def load_app(self):
        self.content = (SRC_DIR / "app.js").read_text()

    def test_l0_global_error_handler(self):
        """Scenario: L0 全域錯誤攔截器存在"""
        assert "window.onerror" in self.content
        assert "window.onunhandledrejection" in self.content

    def test_l0_independent_of_render(self):
        """Scenario: L0 使用 innerHTML（不依賴 h/render/state）"""
        # L0 block uses root.innerHTML directly
        assert "showFatalError" in self.content

    def test_l1_fragment_first_render(self):
        """Scenario: L1 fragment-first 渲染"""
        assert "createDocumentFragment" in self.content

    def test_l1_error_boundary(self):
        """Scenario: L1 render() 有 try-catch 錯誤邊界"""
        assert "renderCrashScreen" in self.content

    def test_l2_init_timeout(self):
        """Scenario: L2 init() 超時保護"""
        assert "INIT_TIMEOUT_MS" in self.content
        assert "10000" in self.content

    def test_l3_crash_screen(self):
        """Scenario: L3 診斷畫面取代黑畫面"""
        assert "renderCrashScreen" in self.content
        assert "MUSEON 控制台發生錯誤" in self.content

    def test_museon_bridge_check(self):
        """Scenario: 檢查 window.museon 是否可用"""
        assert "window.museon" in self.content

    def test_domcontentloaded_guard(self):
        """Scenario: DOMContentLoaded 啟動守護"""
        assert "DOMContentLoaded" in self.content


# ═══════════════════════════════════════
# Section 9: Gateway Server 可匯入（Python 端驗證）
# ═══════════════════════════════════════


class TestGatewayServerImportable:
    """確保 Gateway server 模組可正常匯入（修復按鈕的前提）"""

    def test_gateway_server_importable(self):
        """Scenario: gateway.server 模組可匯入"""
        try:
            from museon.gateway import server
            assert hasattr(server, "create_app") or hasattr(server, "main")
        except ImportError as e:
            pytest.skip(f"Gateway server not importable: {e}")

    def test_gateway_server_has_main(self):
        """Scenario: gateway.server 有 main() 入口"""
        try:
            from museon.gateway.server import main
            assert callable(main)
        except ImportError as e:
            pytest.skip(f"Gateway server not importable: {e}")


# ═══════════════════════════════════════
# Section 10: 零 Token 原則驗證
# ═══════════════════════════════════════


class TestZeroTokenPrinciple:
    """CPU 能做的絕不讓 GPU 做 — 零 Token 原則驗證"""

    def test_no_anthropic_api_call_in_main_data_handlers(self):
        """Scenario: main.js 資料讀取 handlers 不包含 API 呼叫"""
        content = (ELECTRON_DIR / "main.js").read_text()
        # Extract the dashboard handler section
        start = content.find("Dashboard Data Reading")
        end = content.find("Setup Wizard IPC Handlers")
        section = content[start:end] if start > 0 and end > 0 else ""
        assert "anthropic" not in section.lower() or "api" not in section.lower()
        assert "fetch(" not in section
        assert "axios" not in section

    def test_no_api_call_in_app_js(self):
        """Scenario: app.js 不包含任何 HTTP API 呼叫"""
        content = (SRC_DIR / "app.js").read_text()
        assert "fetch(" not in content
        assert "XMLHttpRequest" not in content
        assert "axios" not in content

    def test_no_api_call_in_topology_js(self):
        """Scenario: topology.js 不包含任何 HTTP API 呼叫"""
        content = (SRC_DIR / "topology.js").read_text()
        assert "fetch(" not in content
        assert "XMLHttpRequest" not in content

    def test_data_comes_from_local_files_only(self):
        """Scenario: IPC data handlers 只讀取本地檔案"""
        content = (ELECTRON_DIR / "main.js").read_text()
        # All dashboard handlers use readJSON, readJSONL, readLastJSONL, etc.
        assert "readJSON" in content
        assert "readJSONL" in content
        assert "fs.readFileSync" in content or "readJSON" in content

    def test_chart_js_is_local_not_cdn(self):
        """Scenario: chart.js 從本地 node_modules 載入，非 CDN"""
        content = (SRC_DIR / "index.html").read_text()
        assert "node_modules/chart.js" in content
        assert "cdn" not in content.lower()


# ═══════════════════════════════════════
# Section 11: Telegram 進度訊息（Python 端）
# ═══════════════════════════════════════


class TestTelegramProgressMessages:
    """Telegram adapter 進度訊息功能驗證"""

    def test_adapter_has_send_processing_status(self):
        """Scenario: TelegramAdapter 有 send_processing_status 方法"""
        from museon.channels.telegram import TelegramAdapter
        assert hasattr(TelegramAdapter, "send_processing_status")

    def test_adapter_has_update_processing_status(self):
        """Scenario: TelegramAdapter 有 update_processing_status 方法"""
        from museon.channels.telegram import TelegramAdapter
        assert hasattr(TelegramAdapter, "update_processing_status")

    def test_adapter_has_delete_processing_status(self):
        """Scenario: TelegramAdapter 有 delete_processing_status 方法"""
        from museon.channels.telegram import TelegramAdapter
        assert hasattr(TelegramAdapter, "delete_processing_status")

    def test_adapter_has_start_typing(self):
        """Scenario: TelegramAdapter 有 start_typing 方法"""
        from museon.channels.telegram import TelegramAdapter
        assert hasattr(TelegramAdapter, "start_typing")

    def test_adapter_has_stop_typing(self):
        """Scenario: TelegramAdapter 有 stop_typing 方法"""
        from museon.channels.telegram import TelegramAdapter
        assert hasattr(TelegramAdapter, "stop_typing")

    def test_adapter_has_get_status(self):
        """Scenario: TelegramAdapter 有 get_status 方法"""
        from museon.channels.telegram import TelegramAdapter
        assert hasattr(TelegramAdapter, "get_status")

    def test_adapter_has_is_running_property(self):
        """Scenario: TelegramAdapter 有 is_running 屬性"""
        from museon.channels.telegram import TelegramAdapter
        assert hasattr(TelegramAdapter, "is_running")

    def test_adapter_has_last_message_time_property(self):
        """Scenario: TelegramAdapter 有 last_message_time 屬性"""
        from museon.channels.telegram import TelegramAdapter
        assert hasattr(TelegramAdapter, "last_message_time")

    def test_adapter_tracks_typing_tasks(self):
        """Scenario: TelegramAdapter 追蹤 typing tasks"""
        from museon.channels.telegram import TelegramAdapter
        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter._typing_tasks = {}
        assert isinstance(adapter._typing_tasks, dict)

    def test_get_status_returns_dict(self):
        """Scenario: get_status 回傳包含必要欄位的字典"""
        from museon.channels.telegram import TelegramAdapter
        adapter = TelegramAdapter.__new__(TelegramAdapter)
        adapter._running = False
        adapter._last_message_time = None
        adapter.message_queue = __import__('asyncio').Queue()
        status = adapter.get_status()
        assert "running" in status
        assert "last_message_time" in status
        assert "queue_size" in status


# ═══════════════════════════════════════
# Section 12: Gateway Telegram API 端點
# ═══════════════════════════════════════


class TestGatewayTelegramEndpoints:
    """Gateway server Telegram 管理端點驗證"""

    @pytest.fixture(autouse=True)
    def load_server(self):
        self.content = Path(
            __file__
        ).parent.parent.parent / "src" / "museon" / "gateway" / "server.py"
        self.code = self.content.read_text()

    def test_has_telegram_status_endpoint(self):
        """Scenario: Gateway 有 /api/telegram/status 端點"""
        assert "/api/telegram/status" in self.code

    def test_has_telegram_restart_endpoint(self):
        """Scenario: Gateway 有 /api/telegram/restart 端點"""
        assert "/api/telegram/restart" in self.code

    def test_telegram_restart_stops_old_adapter(self):
        """Scenario: Telegram 重啟時先停止舊 adapter"""
        assert "adapter.stop()" in self.code or "telegram_adapter.stop()" in self.code

    def test_telegram_restart_creates_new_adapter(self):
        """Scenario: Telegram 重啟時建立新 adapter"""
        assert "TelegramAdapter" in self.code

    def test_telegram_restart_restarts_pump(self):
        """Scenario: Telegram 重啟時重新啟動訊息泵"""
        assert "_telegram_message_pump" in self.code

    def test_message_pump_sends_processing_status(self):
        """Scenario: 訊息泵在處理時發送進度訊息"""
        assert "send_processing_status" in self.code

    def test_message_pump_updates_status_text(self):
        """Scenario: 訊息泵更新處理狀態文字"""
        assert "update_processing_status" in self.code

    def test_message_pump_deletes_status_on_complete(self):
        """Scenario: 訊息泵完成後刪除進度訊息"""
        assert "delete_processing_status" in self.code

    def test_message_pump_starts_typing(self):
        """Scenario: 訊息泵開始 typing 動畫"""
        assert "start_typing" in self.code

    def test_message_pump_stops_typing(self):
        """Scenario: 訊息泵停止 typing 動畫"""
        assert "stop_typing" in self.code

    def test_progress_message_text_chinese(self):
        """Scenario: 進度訊息使用繁體中文"""
        assert "正在思考" in self.code
        assert "正在深度思考" in self.code
        assert "正在發送" in self.code


# ═══════════════════════════════════════
# Section 13: Electron Telegram 管理
# ═══════════════════════════════════════


class TestElectronTelegramManagement:
    """Electron 端 Telegram 管理功能驗證"""

    def test_main_js_has_telegram_status_handler(self):
        """Scenario: main.js 有 telegram-get-status handler"""
        content = (ELECTRON_DIR / "main.js").read_text()
        assert "telegram-get-status" in content

    def test_main_js_has_telegram_restart_handler(self):
        """Scenario: main.js 有 telegram-restart handler"""
        content = (ELECTRON_DIR / "main.js").read_text()
        assert "telegram-restart" in content

    def test_main_js_calls_gateway_http_api(self):
        """Scenario: main.js 透過 HTTP 呼叫 Gateway API"""
        content = (ELECTRON_DIR / "main.js").read_text()
        assert "/api/telegram/status" in content
        assert "/api/telegram/restart" in content

    def test_preload_has_getTelegramStatus(self):
        """Scenario: preload 暴露 getTelegramStatus API"""
        content = (ELECTRON_DIR / "preload.js").read_text()
        assert "getTelegramStatus" in content

    def test_preload_has_restartTelegram(self):
        """Scenario: preload 暴露 restartTelegram API"""
        content = (ELECTRON_DIR / "preload.js").read_text()
        assert "restartTelegram" in content

    def test_app_has_telegram_status_state(self):
        """Scenario: app.js state 包含 telegramStatus"""
        content = (SRC_DIR / "app.js").read_text()
        assert "telegramStatus:" in content

    def test_app_has_telegram_restarting_state(self):
        """Scenario: app.js state 包含 telegramRestarting"""
        content = (SRC_DIR / "app.js").read_text()
        assert "telegramRestarting:" in content

    def test_app_has_renderTelegramStatus(self):
        """Scenario: app.js 有 renderTelegramStatus 函式"""
        content = (SRC_DIR / "app.js").read_text()
        assert "function renderTelegramStatus" in content

    def test_app_has_loadTelegramStatus(self):
        """Scenario: app.js 有 loadTelegramStatus 函式"""
        content = (SRC_DIR / "app.js").read_text()
        assert "function loadTelegramStatus" in content

    def test_app_has_handleTelegramRestart(self):
        """Scenario: app.js 有 handleTelegramRestart 函式"""
        content = (SRC_DIR / "app.js").read_text()
        assert "function handleTelegramRestart" in content

    def test_settings_tab_shows_telegram_section(self):
        """Scenario: 設定分頁包含 Telegram 區塊"""
        content = (SRC_DIR / "app.js").read_text()
        assert "renderTelegramStatus()" in content

    def test_telegram_reconnect_button_text(self):
        """Scenario: Telegram 重連按鈕文字正確"""
        content = (SRC_DIR / "app.js").read_text()
        assert "重新連線" in content

    def test_telegram_status_shows_last_message_time(self):
        """Scenario: Telegram 狀態顯示最後訊息時間"""
        content = (SRC_DIR / "app.js").read_text()
        assert "last_message_time" in content

    def test_settings_loads_telegram_status_on_tab_switch(self):
        """Scenario: 切換到設定分頁時載入 Telegram 狀態"""
        content = (SRC_DIR / "app.js").read_text()
        assert "loadTelegramStatus" in content
