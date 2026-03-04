"""Tests for Anthropic tool_use integration.

覆蓋範圍：
1. TestToolSchemas — tool_schemas.py 定義驗證 + should_enable_tools
2. TestToolExecutorRouting — tools.py 路由 + whitelist
3. TestWebSearch — SearXNG HTTP 呼叫（mock）
4. TestWebCrawl — Firecrawl HTTP 呼叫（mock）
5. TestSpeechToText — whisper.cpp CLI（mock）
6. TestOCR — PaddleOCR HTTP 呼叫（mock）
7. TestBrainToolUseIntegration — brain.py tool_use 迴圈邏輯
8. TestInstallerToolStep — orchestrator _step_tools
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Any
from unittest.mock import patch, MagicMock, AsyncMock

import pytest


# ═══════════════════════════════════════
# 1. TestToolSchemas
# ═══════════════════════════════════════

class TestToolSchemas:
    """tool_schemas.py 定義驗證."""

    def test_tool_definitions_exist(self):
        """TOOL_DEFINITIONS 包含 4 個工具."""
        from museon.agent.tool_schemas import TOOL_DEFINITIONS
        assert len(TOOL_DEFINITIONS) == 4

    def test_tool_definitions_have_required_fields(self):
        """每個工具定義包含 name, description, input_schema."""
        from museon.agent.tool_schemas import TOOL_DEFINITIONS
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool, f"Missing 'name' in tool: {tool}"
            assert "description" in tool, f"Missing 'description' in {tool['name']}"
            assert "input_schema" in tool, f"Missing 'input_schema' in {tool['name']}"
            assert tool["input_schema"]["type"] == "object"
            assert "required" in tool["input_schema"]

    def test_tool_names(self):
        """4 個工具名稱正確."""
        from museon.agent.tool_schemas import TOOL_NAMES
        assert TOOL_NAMES == {"web_search", "web_crawl", "speech_to_text", "ocr"}

    def test_descriptions_are_detailed(self):
        """描述夠詳細（>=50 字元，遵循 best practice）."""
        from museon.agent.tool_schemas import TOOL_DEFINITIONS
        for tool in TOOL_DEFINITIONS:
            assert len(tool["description"]) >= 50, (
                f"Tool '{tool['name']}' description too short: {len(tool['description'])} chars"
            )

    def test_web_search_schema(self):
        """web_search 的 input_schema 正確."""
        from museon.agent.tool_schemas import TOOL_DEFINITIONS
        ws = [t for t in TOOL_DEFINITIONS if t["name"] == "web_search"][0]
        props = ws["input_schema"]["properties"]
        assert "query" in props
        assert ws["input_schema"]["required"] == ["query"]

    def test_web_crawl_schema(self):
        """web_crawl 的 input_schema 正確."""
        from museon.agent.tool_schemas import TOOL_DEFINITIONS
        wc = [t for t in TOOL_DEFINITIONS if t["name"] == "web_crawl"][0]
        props = wc["input_schema"]["properties"]
        assert "url" in props
        assert wc["input_schema"]["required"] == ["url"]

    def test_speech_to_text_schema(self):
        """speech_to_text 的 input_schema 正確."""
        from museon.agent.tool_schemas import TOOL_DEFINITIONS
        stt = [t for t in TOOL_DEFINITIONS if t["name"] == "speech_to_text"][0]
        props = stt["input_schema"]["properties"]
        assert "file_path" in props
        assert stt["input_schema"]["required"] == ["file_path"]

    def test_ocr_schema(self):
        """ocr 的 input_schema 正確."""
        from museon.agent.tool_schemas import TOOL_DEFINITIONS
        ocr_tool = [t for t in TOOL_DEFINITIONS if t["name"] == "ocr"][0]
        props = ocr_tool["input_schema"]["properties"]
        assert "file_path" in props
        assert ocr_tool["input_schema"]["required"] == ["file_path"]


class TestShouldEnableTools:
    """should_enable_tools() 啟發式判斷."""

    def test_empty_content_returns_false(self):
        from museon.agent.tool_schemas import should_enable_tools
        assert should_enable_tools("") is False

    def test_none_content_returns_false(self):
        from museon.agent.tool_schemas import should_enable_tools
        assert should_enable_tools(None) is False

    def test_search_keywords_zh(self):
        """中文搜尋關鍵字觸發."""
        from museon.agent.tool_schemas import should_enable_tools
        assert should_enable_tools("幫我搜尋台灣新聞") is True
        assert should_enable_tools("查一下問題的答案") is True
        assert should_enable_tools("幫我找股價") is True

    def test_search_keywords_en(self):
        """英文搜尋關鍵字觸發."""
        from museon.agent.tool_schemas import should_enable_tools
        assert should_enable_tools("search for latest news") is True
        assert should_enable_tools("look up this topic") is True

    def test_url_detection(self):
        """URL 自動觸發."""
        from museon.agent.tool_schemas import should_enable_tools
        assert should_enable_tools("看看這個 https://example.com") is True
        assert should_enable_tools("http://example.com 這個網頁") is True

    def test_crawl_keywords(self):
        """爬取關鍵字觸發."""
        from museon.agent.tool_schemas import should_enable_tools
        assert should_enable_tools("爬取這個網頁的內容") is True
        assert should_enable_tools("抓取文章") is True

    def test_speech_keywords(self):
        """語音關鍵字觸發."""
        from museon.agent.tool_schemas import should_enable_tools
        assert should_enable_tools("轉錄這段語音") is True
        assert should_enable_tools("這個音檔是什麼內容") is True
        assert should_enable_tools("file.mp3") is True

    def test_ocr_keywords(self):
        """OCR 關鍵字觸發."""
        from museon.agent.tool_schemas import should_enable_tools
        assert should_enable_tools("看看這張圖裡的文字") is True
        assert should_enable_tools("截圖中有什麼") is True
        assert should_enable_tools("辨識這張圖") is True

    def test_normal_conversation_returns_false(self):
        """一般對話不觸發."""
        from museon.agent.tool_schemas import should_enable_tools
        assert should_enable_tools("你好") is False
        assert should_enable_tools("心情如何") is False
        assert should_enable_tools("請問你是誰") is False
        assert should_enable_tools("謝謝你的幫助") is False

    def test_latest_keyword_triggers(self):
        """'最新' 關鍵字觸發（需要即時資訊）."""
        from museon.agent.tool_schemas import should_enable_tools
        assert should_enable_tools("最新的AI趨勢是什麼") is True

    def test_news_keyword_triggers(self):
        """'新聞' 關鍵字觸發."""
        from museon.agent.tool_schemas import should_enable_tools
        assert should_enable_tools("有什麼新聞值得關注") is True


# ═══════════════════════════════════════
# 2. TestToolExecutorRouting
# ═══════════════════════════════════════

class TestToolExecutorRouting:
    """ToolExecutor 路由 + whitelist 測試."""

    def test_whitelist_allows_new_tools(self):
        """whitelist 包含 4 個新工具."""
        from museon.agent.tools import ToolWhitelist
        wl = ToolWhitelist()
        assert wl.is_allowed("web_search")
        assert wl.is_allowed("web_crawl")
        assert wl.is_allowed("speech_to_text")
        assert wl.is_allowed("ocr")

    def test_whitelist_blocks_dangerous_tools(self):
        """危險工具被封鎖."""
        from museon.agent.tools import ToolWhitelist
        wl = ToolWhitelist()
        assert not wl.is_allowed("execute_code")
        assert not wl.is_allowed("system_command")
        assert not wl.is_allowed("eval")

    @pytest.mark.asyncio
    async def test_blocked_tool_execution(self):
        """被封鎖的工具回傳 error."""
        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor.execute("execute_code", {"code": "print('hacked')"})
        assert result["success"] is False
        assert "not allowed" in result["error"]

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        """未實作的工具回傳 error."""
        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor.execute("analyze_text", {"text": "hello"})
        assert result["success"] is False
        assert "not implemented" in result["error"]

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """工具超時回傳 error."""
        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor(timeout=0.001)  # 極短超時
        # web_search 對外部 HTTP 會超時
        result = await executor.execute("web_search", {"query": "test"})
        assert result["success"] is False


# ═══════════════════════════════════════
# 3. TestWebSearch（Mock SearXNG）
# ═══════════════════════════════════════

class TestWebSearch:
    """web_search 工具測試（mock HTTP）."""

    @pytest.mark.asyncio
    async def test_missing_query_returns_error(self):
        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor._execute_web_search({})
        assert result["success"] is False
        assert "Missing" in result["error"]

    @pytest.mark.asyncio
    @patch("museon.agent.tools.ToolExecutor._sync_http_get")
    async def test_successful_search(self, mock_get):
        """成功搜尋回傳結果."""
        mock_get.return_value = {
            "results": [
                {"title": "Test Result 1", "url": "https://example.com/1", "content": "Test content 1"},
                {"title": "Test Result 2", "url": "https://example.com/2", "content": "Test content 2"},
            ]
        }

        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor._execute_web_search({"query": "test"})

        assert result["success"] is True
        assert result["result"]["total_results"] == 2
        assert result["result"]["results"][0]["title"] == "Test Result 1"

    @pytest.mark.asyncio
    @patch("museon.agent.tools.ToolExecutor._sync_http_get")
    async def test_search_with_language(self, mock_get):
        """帶語言參數的搜尋."""
        mock_get.return_value = {"results": []}

        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor._execute_web_search({"query": "test", "language": "en"})

        assert result["success"] is True
        # 確認呼叫了正確的語言參數
        call_url = mock_get.call_args[0][0]
        assert "language=en" in call_url

    @pytest.mark.asyncio
    @patch("museon.agent.tools.ToolExecutor._sync_http_get")
    async def test_max_10_results(self, mock_get):
        """最多回傳 10 筆結果."""
        mock_get.return_value = {
            "results": [{"title": f"Result {i}", "url": f"https://example.com/{i}", "content": f"Content {i}"}
                        for i in range(20)]
        }

        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor._execute_web_search({"query": "test"})

        assert result["success"] is True
        assert result["result"]["total_results"] == 10

    @pytest.mark.asyncio
    @patch("museon.agent.tools.ToolExecutor._sync_http_get")
    async def test_search_error_handling(self, mock_get):
        """搜尋失敗回傳 error."""
        mock_get.side_effect = Exception("Connection refused")

        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor._execute_web_search({"query": "test"})

        assert result["success"] is False
        assert "SearXNG" in result["error"]


# ═══════════════════════════════════════
# 4. TestWebCrawl（Mock Firecrawl）
# ═══════════════════════════════════════

class TestWebCrawl:
    """web_crawl 工具測試（mock HTTP）."""

    @pytest.mark.asyncio
    async def test_missing_url_returns_error(self):
        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor._execute_web_crawl({})
        assert result["success"] is False
        assert "Missing" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_url_returns_error(self):
        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor._execute_web_crawl({"url": "not-a-url"})
        assert result["success"] is False
        assert "http" in result["error"].lower()

    @pytest.mark.asyncio
    @patch("museon.agent.tools.ToolExecutor._sync_http_post")
    async def test_successful_crawl(self, mock_post):
        """成功爬取回傳 markdown."""
        mock_post.return_value = {
            "success": True,
            "data": {
                "markdown": "# Hello World\n\nThis is content.",
                "metadata": {
                    "title": "Test Page",
                    "description": "A test page",
                    "language": "en",
                },
            },
        }

        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor._execute_web_crawl({"url": "https://example.com"})

        assert result["success"] is True
        assert "Hello World" in result["result"]["markdown"]
        assert result["result"]["metadata"]["title"] == "Test Page"

    @pytest.mark.asyncio
    @patch("museon.agent.tools.ToolExecutor._sync_http_post")
    async def test_long_content_truncated(self, mock_post):
        """超長內容被截斷."""
        long_content = "x" * 20000
        mock_post.return_value = {
            "success": True,
            "data": {
                "markdown": long_content,
                "metadata": {},
            },
        }

        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor._execute_web_crawl({"url": "https://example.com"})

        assert result["success"] is True
        assert len(result["result"]["markdown"]) < 16000
        assert "截斷" in result["result"]["markdown"]


# ═══════════════════════════════════════
# 5. TestSpeechToText（Mock whisper CLI）
# ═══════════════════════════════════════

class TestSpeechToText:
    """speech_to_text 工具測試（mock subprocess）."""

    @pytest.mark.asyncio
    async def test_missing_file_path_returns_error(self):
        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor._execute_speech_to_text({})
        assert result["success"] is False
        assert "Missing" in result["error"]

    @pytest.mark.asyncio
    async def test_nonexistent_file_returns_error(self):
        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor._execute_speech_to_text({"file_path": "/nonexistent/file.mp3"})
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_whisper_cli_not_found_returns_error(self):
        """whisper CLI 不存在時回傳錯誤."""
        with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
            from museon.agent.tools import ToolExecutor
            executor = ToolExecutor()
            result = await executor._execute_speech_to_text({"file_path": f.name})
            assert result["success"] is False
            assert "not found" in result["error"].lower() or "install" in result["error"].lower()


# ═══════════════════════════════════════
# 6. TestOCR（Mock PaddleOCR）
# ═══════════════════════════════════════

class TestOCR:
    """ocr 工具測試（mock HTTP）."""

    @pytest.mark.asyncio
    async def test_missing_file_path_returns_error(self):
        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor._execute_ocr({})
        assert result["success"] is False
        assert "Missing" in result["error"]

    @pytest.mark.asyncio
    async def test_nonexistent_file_returns_error(self):
        from museon.agent.tools import ToolExecutor
        executor = ToolExecutor()
        result = await executor._execute_ocr({"file_path": "/nonexistent/image.png"})
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    @patch("museon.agent.tools.ToolExecutor._sync_http_post")
    async def test_successful_ocr(self, mock_post):
        """成功 OCR 回傳辨識文字."""
        mock_post.return_value = {
            "results": [
                [
                    {"text": "Hello", "confidence": 0.99},
                    {"text": "World", "confidence": 0.95},
                ]
            ]
        }

        # 建立暫存圖片檔
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            tmp_path = f.name

        try:
            from museon.agent.tools import ToolExecutor
            executor = ToolExecutor()
            result = await executor._execute_ocr({"file_path": tmp_path})

            assert result["success"] is True
            assert "Hello" in result["result"]["full_text"]
            assert result["result"]["total_blocks"] == 2
        finally:
            os.unlink(tmp_path)


# ═══════════════════════════════════════
# 7. TestBrainToolUseIntegration
# ═══════════════════════════════════════

class TestBrainToolUseIntegration:
    """Brain tool_use 整合測試（不真正呼叫 API）."""

    def test_tool_executor_loaded_in_brain(self):
        """Brain __init__ 載入 ToolExecutor."""
        from museon.agent.brain import MuseonBrain
        with tempfile.TemporaryDirectory() as tmp:
            brain = MuseonBrain(data_dir=tmp)
            assert brain._tool_executor is not None

    def test_should_enable_tools_integration(self):
        """Brain process() 中 should_enable_tools 被呼叫."""
        from museon.agent.tool_schemas import should_enable_tools
        assert should_enable_tools("幫我搜尋最新新聞") is True
        assert should_enable_tools("你好嗎") is False

    def test_call_llm_accepts_enable_tools(self):
        """_call_llm 接受 enable_tools 參數."""
        import inspect
        from museon.agent.brain import MuseonBrain
        sig = inspect.signature(MuseonBrain._call_llm)
        params = list(sig.parameters.keys())
        assert "enable_tools" in params


# ═══════════════════════════════════════
# 8. TestInstallerToolStep
# ═══════════════════════════════════════

class TestInstallerToolStep:
    """orchestrator _step_tools 測試."""

    def test_step_tools_in_steps_list(self):
        """_step_tools 在 STEPS 列表中."""
        from museon.installer.orchestrator import InstallerOrchestrator
        assert "_step_tools" in InstallerOrchestrator.STEPS

    def test_step_tools_label(self):
        """_step_tools 有正確的標籤."""
        from museon.installer.orchestrator import InstallerOrchestrator
        assert InstallerOrchestrator.STEP_LABELS["_step_tools"] == "工具安裝"

    def test_step_tools_before_launch(self):
        """_step_tools 在 _step_launch 之前."""
        from museon.installer.orchestrator import InstallerOrchestrator
        steps = InstallerOrchestrator.STEPS
        tools_idx = steps.index("_step_tools")
        launch_idx = steps.index("_step_launch")
        assert tools_idx < launch_idx

    def test_installer_has_8_steps(self):
        """安裝器現在有 8 個步驟."""
        from museon.installer.orchestrator import InstallerOrchestrator
        assert len(InstallerOrchestrator.STEPS) == 8

    def test_ui_step_names_match(self):
        """UI STEP_NAMES 數量與 STEPS 一致."""
        from museon.installer.ui import InstallerUI
        from museon.installer.orchestrator import InstallerOrchestrator
        assert len(InstallerUI.STEP_NAMES) == len(InstallerOrchestrator.STEPS)

    def test_ui_step_estimates_complete(self):
        """每個 STEP_NAME 都有對應的時間估計."""
        from museon.installer.ui import InstallerUI
        for name in InstallerUI.STEP_NAMES:
            assert name in InstallerUI.STEP_ESTIMATES, f"Missing estimate for: {name}"

    def test_spinner_messages_count(self):
        """spinner 訊息數量與步驟數一致."""
        from museon.installer.__main__ import STEP_SPINNER_MESSAGES
        from museon.installer.orchestrator import InstallerOrchestrator
        assert len(STEP_SPINNER_MESSAGES) == len(InstallerOrchestrator.STEPS)

    @patch("subprocess.run")
    def test_step_tools_no_docker_skips(self, mock_run):
        """Docker 不存在時 _step_tools 跳過."""
        mock_run.side_effect = FileNotFoundError("docker not found")

        from museon.installer.orchestrator import InstallerOrchestrator
        from museon.installer.models import InstallConfig, StepStatus

        with tempfile.TemporaryDirectory() as tmp:
            config = InstallConfig(install_dir=Path(tmp))
            orch = InstallerOrchestrator(config=config, interactive=False)
            result = orch._step_tools()
            assert result.status == StepStatus.SKIPPED

    @patch("subprocess.run")
    def test_step_tools_docker_unavailable_skips(self, mock_run):
        """Docker 未啟動時 _step_tools 跳過."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        from museon.installer.orchestrator import InstallerOrchestrator
        from museon.installer.models import InstallConfig, StepStatus

        with tempfile.TemporaryDirectory() as tmp:
            config = InstallConfig(install_dir=Path(tmp))
            orch = InstallerOrchestrator(config=config, interactive=False)
            result = orch._step_tools()
            assert result.status == StepStatus.SKIPPED


# ═══════════════════════════════════════
# 9. TestToolRegistryLearnings（安裝經驗迭代）
# ═══════════════════════════════════════

class TestToolRegistryLearnings:
    """根據實際安裝經驗的迭代測試."""

    def test_firecrawl_image_uses_new_org(self):
        """Firecrawl image 不再使用已廢棄的 mendableai org."""
        from museon.tools.tool_registry import TOOL_CONFIGS
        config = TOOL_CONFIGS["firecrawl"]
        assert "mendableai" not in config.docker_image
        assert "firecrawl/firecrawl" in config.docker_image

    def test_firecrawl_has_playwright_image_in_extra(self):
        """Firecrawl extra_config 包含獨立的 playwright image."""
        from museon.tools.tool_registry import TOOL_CONFIGS
        config = TOOL_CONFIGS["firecrawl"]
        assert "playwright_image" in config.extra_config
        assert "firecrawl/playwright-service" in config.extra_config["playwright_image"]

    def test_paddleocr_health_url_is_base(self):
        """PaddleOCR health URL 使用 base URL（非 POST-only 端點）."""
        from museon.tools.tool_registry import TOOL_CONFIGS
        config = TOOL_CONFIGS["paddleocr"]
        # 不應該用 /predict/ocr_system（POST-only 會回 405）
        assert config.health_url.rstrip("/") == "http://127.0.0.1:8866"

    def test_health_check_handles_http_error(self):
        """健康檢查能處理 4xx HTTPError（不視為不健康）."""
        import inspect
        from museon.tools.tool_registry import ToolRegistry
        source = inspect.getsource(ToolRegistry._check_tool_health)
        assert "HTTPError" in source

    def test_auto_detect_handles_pip_packages(self):
        """auto_detect 能偵測 pip 安裝的套件."""
        import inspect
        from museon.tools.tool_registry import ToolRegistry
        source = inspect.getsource(ToolRegistry.auto_detect)
        assert "__import__" in source

    def test_compose_template_no_version_key(self):
        """Firecrawl compose 模板不含已廢棄的 version key."""
        import inspect
        from museon.tools.tool_registry import ToolRegistry
        source = inspect.getsource(ToolRegistry._install_firecrawl_compose)
        # version: '3.8' 已被 docker compose 標為 obsolete
        assert "version:" not in source.split("compose_content")[1]

    def test_step_tools_clears_ghcr_credentials(self):
        """_step_tools 在安裝前清除 ghcr.io 憑證."""
        import inspect
        from museon.installer.orchestrator import InstallerOrchestrator
        source = inspect.getsource(InstallerOrchestrator._step_tools)
        assert "docker" in source and "logout" in source and "ghcr.io" in source

    def test_packager_excludes_tools_dir(self):
        """安裝包排除 _tools/ 目錄（防止 3GB+ 模型打包）."""
        from museon.installer.packager import InstallerPackager
        assert "_tools" in InstallerPackager.EXCLUDE_PATTERNS

    def test_packager_has_max_file_size(self):
        """安裝包有最大檔案大小限制."""
        from museon.installer.packager import InstallerPackager
        assert hasattr(InstallerPackager, "MAX_FILE_SIZE_MB")
        assert InstallerPackager.MAX_FILE_SIZE_MB <= 100  # 不超過 100MB

    def test_packager_excludes_large_files(self):
        """_should_exclude 會排除超大檔案."""
        from museon.installer.packager import InstallerPackager
        packager = InstallerPackager()
        with tempfile.TemporaryDirectory() as tmp:
            big_file = Path(tmp) / "huge.bin"
            with open(big_file, "wb") as f:
                f.seek((InstallerPackager.MAX_FILE_SIZE_MB + 1) * 1024 * 1024)
                f.write(b"\x00")
            assert packager._should_exclude(big_file, Path(tmp)) is True
