"""Tool Registry BDD 測試.

驗證免費工具兵器庫的管理邏輯。
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from museon.tools.tool_registry import (
    CATEGORY_NAMES,
    INSTALL_ORDER,
    TOOL_CONFIGS,
    ToolConfig,
    ToolRegistry,
    ToolState,
)


@pytest.fixture
def registry(tmp_path):
    return ToolRegistry(workspace=tmp_path, auto_detect=False)


class TestToolConfigs:
    """Scenario: 工具設定完整性."""

    def test_six_tools_defined(self):
        assert len(TOOL_CONFIGS) == 6

    def test_all_have_required_fields(self):
        for name, config in TOOL_CONFIGS.items():
            assert config.name == name
            assert config.display_name
            assert config.emoji
            assert config.description
            assert config.category
            assert config.install_type in (
                "docker", "native", "pip", "compose"
            )

    def test_install_order_matches_configs(self):
        assert set(INSTALL_ORDER) == set(TOOL_CONFIGS.keys())

    def test_install_order_length(self):
        assert len(INSTALL_ORDER) == 6

    def test_docker_tools_have_ports(self):
        docker_tools = [
            n for n, c in TOOL_CONFIGS.items()
            if c.install_type == "docker"
        ]
        for name in docker_tools:
            config = TOOL_CONFIGS[name]
            assert config.docker_port > 0
            assert config.docker_image

    def test_category_names_cover_all(self):
        categories = {c.category for c in TOOL_CONFIGS.values()}
        for cat in categories:
            assert cat in CATEGORY_NAMES

    def test_searxng_config(self):
        c = TOOL_CONFIGS["searxng"]
        assert c.install_type == "docker"
        assert c.docker_port == 8888
        assert c.ram_mb == 256

    def test_qdrant_config(self):
        c = TOOL_CONFIGS["qdrant"]
        assert c.install_type == "docker"
        assert c.docker_port == 6333
        assert c.extra_config.get("embedding_model") == "bge-small-zh-v1.5"

    def test_whisper_config(self):
        c = TOOL_CONFIGS["whisper"]
        assert c.install_type == "native"
        assert "large-v3" in c.extra_config.get("model", "")

    def test_firecrawl_config(self):
        c = TOOL_CONFIGS["firecrawl"]
        assert c.install_type == "compose"
        assert c.docker_port == 3002

    def test_paddleocr_image_correct(self):
        """PaddleOCR 使用正確的 Docker image."""
        c = TOOL_CONFIGS["paddleocr"]
        assert c.docker_image == "987846/paddleocr:latest"

    def test_kokoro_install_cmd_is_package_name(self):
        """Kokoro install_cmd 是套件名稱（非完整指令）."""
        c = TOOL_CONFIGS["kokoro"]
        # 應該是套件名稱，不含 pip install
        assert "pip" not in c.install_cmd
        assert c.install_cmd == "kokoro-onnx"

    def test_descriptions_are_chinese(self):
        """所有說明都是繁體中文."""
        for name, config in TOOL_CONFIGS.items():
            # 至少包含一個中文字
            assert any(
                "\u4e00" <= ch <= "\u9fff" for ch in config.description
            ), f"{name} description not in Chinese"

    def test_ports_unique(self):
        """所有 Docker port 不重複."""
        ports = [
            c.docker_port for c in TOOL_CONFIGS.values()
            if c.docker_port > 0
        ]
        assert len(ports) == len(set(ports))

    # ── 必要工具測試 ──

    def test_ollama_removed(self):
        """Ollama 已從工具設定中移除."""
        assert "ollama" not in TOOL_CONFIGS

    def test_install_order_no_ollama(self):
        """INSTALL_ORDER 不含 ollama."""
        assert "ollama" not in INSTALL_ORDER

    def test_required_tools_exist(self):
        """三個必要工具正確標記."""
        required = [
            name for name, cfg in TOOL_CONFIGS.items()
            if cfg.required
        ]
        assert set(required) == {"searxng", "qdrant", "firecrawl"}

    def test_required_field_default_false(self):
        """非必要工具 required 預設 False."""
        optional = [
            name for name, cfg in TOOL_CONFIGS.items()
            if not cfg.required
        ]
        assert len(optional) == 3  # whisper, paddleocr, kokoro

    def test_llm_category_removed(self):
        """llm 類別已移除."""
        assert "llm" not in CATEGORY_NAMES

    def test_required_tools_first_in_install_order(self):
        """必要工具排在安裝順序前面."""
        required_set = {
            name for name, cfg in TOOL_CONFIGS.items()
            if cfg.required
        }
        # 前 3 個應該都是 required
        first_three = set(INSTALL_ORDER[:3])
        assert first_three == required_set


class TestToolRegistry:
    """Scenario: 工具管理中心."""

    def test_init_creates_dir(self, registry, tmp_path):
        assert (tmp_path / "_system" / "tools").is_dir()

    def test_list_tools_returns_6(self, registry):
        tools = registry.list_tools()
        assert len(tools) == 6

    def test_list_tools_order_matches_install_order(self, registry):
        tools = registry.list_tools()
        names = [t["name"] for t in tools]
        assert names == INSTALL_ORDER

    def test_list_tools_fields(self, registry):
        tools = registry.list_tools()
        for tool in tools:
            assert "name" in tool
            assert "display_name" in tool
            assert "emoji" in tool
            assert "description" in tool
            assert "category" in tool
            assert "required" in tool
            assert "installed" in tool
            assert "enabled" in tool
            assert "healthy" in tool

    def test_list_tools_required_field(self, registry):
        """list_tools 回傳包含 required 欄位."""
        tools = registry.list_tools()
        required_names = {t["name"] for t in tools if t["required"]}
        assert required_names == {"searxng", "qdrant", "firecrawl"}

    def test_get_tool(self, registry):
        tool = registry.get_tool("searxng")
        assert tool is not None
        assert tool["display_name"] == "SearXNG"

    def test_get_tool_nonexistent(self, registry):
        assert registry.get_tool("nonexistent") is None

    def test_get_status_summary(self, registry):
        summary = registry.get_status_summary()
        assert summary["total"] == 6
        assert summary["installed"] == 0
        assert summary["enabled"] == 0
        assert summary["healthy"] == 0

    def test_get_install_order(self, registry):
        order = registry.get_install_order()
        assert order == INSTALL_ORDER

    def test_get_not_installed(self, registry):
        not_installed = registry.get_not_installed()
        assert len(not_installed) == 6

    def test_get_required_tools(self, registry):
        required = registry.get_required_tools()
        assert set(required) == {"searxng", "qdrant", "firecrawl"}


class TestToolState:
    """Scenario: 狀態持久化."""

    def test_default_state(self):
        state = ToolState(name="test")
        assert state.installed is False
        assert state.enabled is False
        assert state.healthy is False

    def test_state_persistence(self, tmp_path):
        # Create registry and modify state
        registry = ToolRegistry(workspace=tmp_path)
        registry._states["searxng"].installed = True
        registry._states["searxng"].enabled = True
        registry._save_states()

        # Reload
        registry2 = ToolRegistry(workspace=tmp_path)
        assert registry2._states["searxng"].installed is True
        assert registry2._states["searxng"].enabled is True

    def test_state_file_location(self, tmp_path):
        registry = ToolRegistry(workspace=tmp_path)
        registry._save_states()
        assert (tmp_path / "_system" / "tools" / "registry.json").exists()

    def test_stale_entries_filtered_on_load(self, tmp_path):
        """registry.json 中不在 TOOL_CONFIGS 的殘留項被過濾."""
        state_dir = tmp_path / "_system" / "tools"
        state_dir.mkdir(parents=True, exist_ok=True)
        stale_data = {
            "ollama": {
                "name": "ollama",
                "installed": True,
                "enabled": True,
                "healthy": True,
                "last_health_check": "",
                "last_started": "",
                "install_progress": 0,
                "install_status": "",
                "error_message": "",
            },
            "searxng": {
                "name": "searxng",
                "installed": True,
                "enabled": True,
                "healthy": False,
                "last_health_check": "",
                "last_started": "",
                "install_progress": 100,
                "install_status": "installed",
                "error_message": "",
            },
        }
        (state_dir / "registry.json").write_text(
            json.dumps(stale_data), encoding="utf-8"
        )
        registry = ToolRegistry(workspace=tmp_path)
        assert "ollama" not in registry._states
        assert "searxng" in registry._states
        assert registry._states["searxng"].installed is True

    def test_stale_entries_not_persisted(self, tmp_path):
        """儲存後殘留項不再寫入 registry.json."""
        state_dir = tmp_path / "_system" / "tools"
        state_dir.mkdir(parents=True, exist_ok=True)
        stale_data = {
            "ollama": {
                "name": "ollama", "installed": True, "enabled": True,
                "healthy": True, "last_health_check": "", "last_started": "",
                "install_progress": 0, "install_status": "", "error_message": "",
            },
        }
        (state_dir / "registry.json").write_text(
            json.dumps(stale_data), encoding="utf-8"
        )
        registry = ToolRegistry(workspace=tmp_path)
        registry._save_states()
        saved = json.loads(
            (state_dir / "registry.json").read_text(encoding="utf-8")
        )
        assert "ollama" not in saved


class TestToggle:
    """Scenario: 工具 on/off 開關."""

    def test_toggle_not_installed(self, registry):
        result = registry.toggle_tool("whisper", True)
        assert result["success"] is False
        assert result["reason"] == "not_installed"

    def test_toggle_unknown_tool(self, registry):
        result = registry.toggle_tool("unknown", True)
        assert result["success"] is False
        assert result["reason"] == "tool_not_found"

    def test_toggle_required_tool_off_blocked(self, registry):
        """必要工具禁止關閉."""
        result = registry.toggle_tool("searxng", False)
        assert result["success"] is False
        assert result["reason"] == "required_tool_cannot_disable"

    def test_toggle_required_tool_on_allowed(self, registry):
        """必要工具可以開啟（若已安裝）."""
        registry._states["qdrant"].installed = True
        with patch("museon.tools.tool_registry.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0)
            result = registry.toggle_tool("qdrant", True)
            assert result["success"] is True

    def test_toggle_optional_tool_off_allowed(self, registry):
        """非必要工具可以關閉."""
        registry._states["whisper"].installed = True
        registry._states["whisper"].enabled = True
        result = registry.toggle_tool("whisper", False)
        assert result["success"] is True
        assert result["enabled"] is False

    @patch("museon.tools.tool_registry.subprocess")
    def test_toggle_on_docker(self, mock_subprocess, registry):
        """Docker 工具 toggle on."""
        # 先標記為已安裝
        registry._states["searxng"].installed = True
        registry._states["searxng"].enabled = False

        mock_subprocess.run.return_value = MagicMock(returncode=0)

        result = registry.toggle_tool("searxng", True)
        assert result["success"] is True
        assert result["enabled"] is True

    @patch("museon.tools.tool_registry.subprocess")
    def test_toggle_off_optional_docker(self, mock_subprocess, registry):
        """非必要 Docker 工具 toggle off."""
        registry._states["paddleocr"].installed = True
        registry._states["paddleocr"].enabled = True

        mock_subprocess.run.return_value = MagicMock(returncode=0)

        result = registry.toggle_tool("paddleocr", False)
        assert result["success"] is True
        assert result["enabled"] is False


class TestHealthCheck:
    """Scenario: 健康檢查."""

    def test_health_unknown_tool(self, registry):
        result = registry.check_health("unknown")
        assert result["healthy"] is False
        assert result["reason"] == "unknown_tool"

    def test_health_not_running(self, registry):
        result = registry.check_health("searxng")
        assert result["healthy"] is False
        assert result["reason"] == "not_running"

    def test_check_all_health(self, registry):
        results = registry.check_all_health()
        assert len(results) == 6
        for name, r in results.items():
            assert r["healthy"] is False


class TestInstall:
    """Scenario: 工具安裝."""

    def test_install_unknown_tool(self, registry):
        result = registry.install_tool("unknown")
        assert result["success"] is False

    @patch("museon.tools.tool_registry.subprocess")
    def test_install_docker_success(self, mock_subprocess, registry):
        """Docker 安裝成功."""
        mock_subprocess.run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        mock_subprocess.TimeoutExpired = subprocess_timeout_class()

        # Mock health check
        with patch.object(
            registry, "_wait_for_health", return_value=True
        ):
            result = registry.install_tool("qdrant")

        assert result["success"] is True
        assert result["installed"] is True
        assert result["enabled"] is True

    @patch("museon.tools.tool_registry.subprocess")
    def test_install_docker_pull_fails(self, mock_subprocess, registry):
        """Docker pull 失敗."""
        mock_subprocess.run.return_value = MagicMock(
            returncode=1, stderr="pull error"
        )
        mock_subprocess.TimeoutExpired = subprocess_timeout_class()

        result = registry.install_tool("qdrant")
        assert result["success"] is False

    def test_install_progress_callback(self, registry):
        """進度回調被呼叫."""
        progress_records = []

        def cb(pct, msg):
            progress_records.append((pct, msg))

        with patch.object(
            registry, "_install_docker", return_value=True
        ):
            registry.install_tool("searxng", progress_cb=cb)

        # 至少有開始的進度
        assert len(progress_records) >= 1
        assert progress_records[0][0] == 0  # 0% 開始


class TestAutoDetect:
    """Scenario: 自動偵測已安裝工具."""

    @patch("builtins.__import__", side_effect=ImportError("mocked"))
    @patch("museon.tools.tool_registry.subprocess")
    def test_auto_detect_empty(self, mock_subprocess, mock_import, registry):
        """無已安裝工具（subprocess 失敗 + pip import 失敗）."""
        mock_subprocess.run.return_value = MagicMock(
            returncode=1, stdout="", stderr=""
        )
        detected = registry.auto_detect()
        # 沒有偵測到任何工具
        assert len(detected) == 0

    @patch("museon.tools.tool_registry.subprocess")
    def test_auto_detect_docker_exists(self, mock_subprocess, registry):
        """偵測到已存在的 Docker 容器."""
        def mock_run(args, **kwargs):
            result = MagicMock()
            if "inspect" in args and "museon-searxng" in args:
                result.returncode = 0
                result.stdout = "true"
            else:
                result.returncode = 1
                result.stdout = ""
            return result

        mock_subprocess.run.side_effect = mock_run

        detected = registry.auto_detect()
        assert registry._states["searxng"].installed is True


class TestStatusSummary:
    """Scenario: 彙總狀態."""

    def test_summary_with_enabled_tools(self, registry):
        registry._states["searxng"].installed = True
        registry._states["searxng"].enabled = True
        registry._states["qdrant"].installed = True
        registry._states["qdrant"].enabled = True

        summary = registry.get_status_summary()
        assert summary["installed"] == 2
        assert summary["enabled"] == 2
        assert summary["total_ram_mb"] > 0


def subprocess_timeout_class():
    """Helper to create a mock TimeoutExpired exception class."""
    import subprocess
    return subprocess.TimeoutExpired
