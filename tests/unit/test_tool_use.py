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
        """TOOL_DEFINITIONS 包含 19 個工具（v12 含 7 個 Self-Surgery 工具）."""
        from museon.agent.tool_schemas import TOOL_DEFINITIONS
        assert len(TOOL_DEFINITIONS) == 19

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
        """19 個工具名稱正確（v12 含 Self-Surgery 工具）."""
        from museon.agent.tool_schemas import TOOL_NAMES
        assert TOOL_NAMES == {
            "web_search", "web_crawl", "speech_to_text", "ocr",
            "generate_artifact", "read_skill", "skill_search",
            "shell_exec", "file_write_rich",
            "mcp_list_servers", "mcp_call_tool", "mcp_add_server",
            # v12 Self-Surgery 工具
            "source_read", "source_search", "source_ast_check",
            "surgery_diagnose", "surgery_propose",
            "surgery_apply", "surgery_rollback",
        }

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


class TestToolsAlwaysEnabled:
    """v10: 工具永遠開啟，模型自主決定（移除 should_enable_tools 啟發式閘門）."""

    def test_no_should_enable_tools_function(self):
        """v10 移除了 should_enable_tools，不應存在此函式."""
        import museon.agent.tool_schemas as ts
        assert not hasattr(ts, "should_enable_tools")

    def test_tool_definitions_always_available(self):
        """TOOL_DEFINITIONS 始終可用，不受訊息內容影響."""
        from museon.agent.tool_schemas import TOOL_DEFINITIONS
        assert len(TOOL_DEFINITIONS) > 0

    def test_get_all_tool_definitions_returns_static(self):
        """get_all_tool_definitions 不帶參數時回傳所有靜態工具."""
        from museon.agent.tool_schemas import get_all_tool_definitions, TOOL_DEFINITIONS
        result = get_all_tool_definitions()
        assert len(result) == len(TOOL_DEFINITIONS)

    def test_get_all_tool_definitions_merges_dynamic(self):
        """get_all_tool_definitions 合併動態 MCP 工具（不重複）."""
        from museon.agent.tool_schemas import get_all_tool_definitions, TOOL_DEFINITIONS
        dynamic = [{"name": "mcp__test__hello", "description": "test", "input_schema": {"type": "object", "properties": {}, "required": []}}]
        result = get_all_tool_definitions(dynamic_tools=dynamic)
        assert len(result) == len(TOOL_DEFINITIONS) + 1

    def test_get_all_tool_definitions_no_duplicate(self):
        """get_all_tool_definitions 不加入已存在的工具名稱."""
        from museon.agent.tool_schemas import get_all_tool_definitions, TOOL_DEFINITIONS
        duplicate = [{"name": "web_search", "description": "dup", "input_schema": {"type": "object", "properties": {}, "required": []}}]
        result = get_all_tool_definitions(dynamic_tools=duplicate)
        assert len(result) == len(TOOL_DEFINITIONS)

    def test_tool_names_is_frozenset(self):
        """TOOL_NAMES 是 frozenset（不可變）."""
        from museon.agent.tool_schemas import TOOL_NAMES
        assert isinstance(TOOL_NAMES, frozenset)

    def test_all_definitions_have_name(self):
        """每個工具定義都有 name."""
        from museon.agent.tool_schemas import TOOL_DEFINITIONS
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool

    def test_all_definitions_have_description(self):
        """每個工具定義都有 description."""
        from museon.agent.tool_schemas import TOOL_DEFINITIONS
        for tool in TOOL_DEFINITIONS:
            assert "description" in tool

    def test_all_definitions_have_input_schema(self):
        """每個工具定義都有 input_schema."""
        from museon.agent.tool_schemas import TOOL_DEFINITIONS
        for tool in TOOL_DEFINITIONS:
            assert "input_schema" in tool

    def test_tool_names_match_definitions(self):
        """TOOL_NAMES 與 TOOL_DEFINITIONS 的名稱一致."""
        from museon.agent.tool_schemas import TOOL_NAMES, TOOL_DEFINITIONS
        expected = frozenset(t["name"] for t in TOOL_DEFINITIONS)
        assert TOOL_NAMES == expected


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

    def test_tools_always_enabled_in_v10(self):
        """v10: 工具永遠開啟，should_enable_tools 已移除."""
        import museon.agent.tool_schemas as ts
        assert not hasattr(ts, "should_enable_tools")
        # 工具定義始終可用
        assert len(ts.TOOL_DEFINITIONS) > 0

    def test_call_llm_accepts_enable_tools(self):
        """_call_llm 接受 enable_tools 參數."""
        import inspect
        from museon.agent.brain import MuseonBrain
        sig = inspect.signature(MuseonBrain._call_llm)
        params = list(sig.parameters.keys())
        assert "enable_tools" in params


# ═══════════════════════════════════════
# 8. TestToolRegistryLearnings（安裝經驗迭代）
# ═══════════════════════════════════════
# NOTE: TestInstallerToolStep 已隨 museon.installer 模組移除而刪除

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
        assert config.health_url.rstrip("/") == "http://127.0.0.1:8866"

    def test_health_check_handles_http_error(self):
        """健康檢查能處理 4xx HTTPError."""
        import inspect
        from museon.tools.tool_registry import ToolRegistry
        source = inspect.getsource(ToolRegistry._check_tool_health_detail)
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
        assert "version:" not in source.split("compose_content")[1]
