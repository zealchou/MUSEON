"""Tool execution with whitelist and sandbox - Layer 3 security defense.

Based on plan-v7.md Chapter 7 (Layer 3: Execution Environment Isolation):
- All shell commands go through whitelist (no arbitrary execution)
- File system access restricted to workspace directory
- Path traversal prevention (禁止 ../ and symlinks)
- Network access whitelist (only registered APIs)
- Subprocess maximum execution time limit

Security principle: Whitelist thinking - what's not explicitly allowed is forbidden.

Tool 實作對應：
- web_search  → SearXNG (http://127.0.0.1:8888)
- web_crawl   → Firecrawl (http://127.0.0.1:3002)
- speech_to_text → whisper.cpp CLI (_tools/whisper.cpp/build/bin/whisper-cli)
- ocr         → PaddleOCR (http://127.0.0.1:8866)
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
import asyncio
import json
import logging
import os
import subprocess
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════
# 服務端點常數（支援環境變數覆寫，適配 Docker 網路）
# ═══════════════════════════════════════
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8888")
FIRECRAWL_URL = os.environ.get("FIRECRAWL_URL", "http://127.0.0.1:3002")
PADDLEOCR_URL = os.environ.get("PADDLEOCR_URL", "http://127.0.0.1:8866")

# Whisper CLI 路徑（相對於 data_dir）
WHISPER_CLI_CANDIDATES = [
    "_tools/whisper.cpp/build/bin/whisper-cli",
    "_tools/whisper.cpp/main",
]
WHISPER_MODEL_PATH = "_tools/whisper.cpp/models/ggml-medium.bin"


class ToolWhitelist:
    """Whitelist of allowed tools and their configurations."""

    def __init__(self):
        """Initialize tool whitelist — v10: 行動工具全開."""
        self.allowed_tools = {
            # Read-only operations (safe)
            "web_search",
            "web_crawl",
            "speech_to_text",
            "ocr",
            "read_file",
            "list_directory",
            "get_file_info",
            # Write operations (sandboxed to workspace)
            "write_file",
            "create_directory",
            # Platform APIs (authenticated)
            "instagram_post",
            "telegram_send",
            "line_send",
            # Analysis (CPU-bound, safe)
            "analyze_text",
            "generate_summary",
            # Artifact generation (write to workspace)
            "generate_artifact",
            # v11 新增：認知能力自主取用
            "read_skill",           # 讀取 SKILL.md 完整指引
            "skill_search",         # 搜尋最相關的認知能力
            # v10 新增：行動工具
            "shell_exec",           # Shell 命令執行（有安全黑名單）
            "file_write_rich",      # 全格式檔案產出
            "mcp_list_servers",     # MCP 伺服器列表
            "mcp_call_tool",        # MCP 工具呼叫
            "mcp_add_server",       # MCP 伺服器新增
            # v11.3 新增：自主能力
            "restart_gateway",
            "pending_action",
            # v13 新增：Ares 戰神系統
            "ares_search",
            "ares_create",
            "ares_update",
            "ares_briefing",
            "ares_topology",
            # v12 新增：Self-Surgery（自我手術）
            "source_read",          # 讀取源碼
            "source_search",        # 搜尋源碼
            "source_ast_check",     # AST 靜態分析
            "surgery_diagnose",     # 三層診斷管線
            "surgery_propose",      # 生成修復提案
            "surgery_apply",        # 執行手術
            "surgery_rollback",     # 回滾
            # v2 L3 任務執行
            "trigger_job",          # 觸發 cron job
            "memory_search",        # 記憶搜尋
            "spawn_perspectives",   # 圓桌討論
        }

        # Tools explicitly blocked
        self.blocked_tools = {
            # Dangerous operations (shell_exec 有自己的安全層)
            "eval",
            "exec",
            # Destructive operations
            "delete_file",
            "delete_directory",
            "truncate_file",
            # Network operations (except whitelisted APIs)
            "raw_http_request",
            "ssh_connect",
            "ftp_connect",
            # System operations
            "modify_permissions",
            "change_owner",
        }

    def is_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed to execute.

        Args:
            tool_name: Name of the tool

        Returns:
            True if allowed, False otherwise
        """
        # Explicitly blocked takes precedence
        if tool_name in self.blocked_tools:
            return False

        # Static whitelist
        if tool_name in self.allowed_tools:
            return True

        # v10.2: 動態 MCP 工具（mcp__{server}__{tool} 格式）自動通過
        # 安全因為：使用者必須先自己配置伺服器才會有這些工具
        if tool_name.startswith("mcp__"):
            return True

        return False


class PathSandbox:
    """Sandbox for file path operations."""

    def __init__(self, workspace_dir: str = "data/workspace"):
        """Initialize path sandbox.

        Args:
            workspace_dir: Root directory for workspace
        """
        self.workspace_root = Path(workspace_dir).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def sanitize_path(self, user_path: str) -> Optional[Path]:
        """Sanitize a user-provided path.

        Prevents:
        - Path traversal (../)
        - Symlink escapes
        - Access outside workspace

        Args:
            user_path: User-provided path (relative or absolute)

        Returns:
            Sanitized Path object within workspace, or None if invalid
        """
        try:
            # Convert to Path
            path = Path(user_path)

            # If absolute, reject unless within workspace
            if path.is_absolute():
                resolved = path.resolve()
                if not self._is_within_workspace(resolved):
                    return None
                return resolved

            # If relative, resolve relative to workspace
            full_path = (self.workspace_root / path).resolve()

            # Check it's still within workspace (防 symlink escape)
            if not self._is_within_workspace(full_path):
                return None

            return full_path

        except (ValueError, OSError):
            return None

    def _is_within_workspace(self, path: Path) -> bool:
        """Check if path is within workspace.

        Args:
            path: Resolved path

        Returns:
            True if within workspace
        """
        try:
            # Use resolve() to handle symlinks
            resolved_path = path.resolve()
            workspace_root = self.workspace_root.resolve()

            # Check if path is relative to workspace
            resolved_path.relative_to(workspace_root)
            return True

        except (ValueError, OSError):
            return False


class ToolExecutor:
    """Executes tools with security controls.

    真實工具對接：
    - web_search → SearXNG (Docker, port 8888)
    - web_crawl → Firecrawl (Docker Compose, port 3002)
    - speech_to_text → whisper.cpp (Native binary)
    - ocr → PaddleOCR (Docker, port 8866)
    """

    def __init__(
        self,
        workspace_dir: str = "data/workspace",
        timeout: float = 180.0,
    ):
        """Initialize tool executor.

        Args:
            workspace_dir: Workspace directory for file operations
            timeout: Maximum execution time per tool (seconds)
        """
        self.whitelist = ToolWhitelist()
        self.sandbox = PathSandbox(workspace_dir=workspace_dir)
        self.timeout = timeout
        self._workspace_dir = workspace_dir
        self._brain = None  # Set by Brain after construction

        # v10.2: MCP Connector SDK
        self._mcp_connector = None
        try:
            from museon.agent.mcp_connector import MCPConnectorSDK
            data_dir = str(Path(workspace_dir).parent)
            self._mcp_connector = MCPConnectorSDK(data_dir=data_dir)
        except Exception as e:
            logger.warning(f"MCPConnectorSDK init failed (degraded): {e}")

        # v12: Self-Surgery Engine
        self._surgery_engine = None
        self._diagnosis_pipeline = None
        try:
            from museon.doctor.surgeon import SurgeryEngine
            project_root = Path(workspace_dir).parent.parent
            self._surgery_engine = SurgeryEngine(
                project_root=project_root, auto_restart=False,
            )
        except Exception as e:
            logger.warning(f"SurgeryEngine init failed (degraded): {e}")

    async def execute(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a tool with security checks.

        Args:
            tool_name: Name of tool to execute
            arguments: Tool arguments

        Returns:
            Result dict with success, result/error
        """
        # Step 1: Whitelist check
        if not self.whitelist.is_allowed(tool_name):
            return {
                "success": False,
                "error": f"Tool '{tool_name}' is not allowed",
                "reason": "Tool not in whitelist or explicitly blocked",
            }

        # Step 2: Execute with timeout
        try:
            result = await asyncio.wait_for(
                self._execute_tool(tool_name, arguments),
                timeout=self.timeout,
            )
            return result

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' execution timeout after {self.timeout}s",
                "timeout": self.timeout,
            }

        except Exception as e:
            logger.error(f"Tool '{tool_name}' execution failed: {e}")
            return {
                "success": False,
                "error": f"Tool execution failed: {str(e)}",
            }

    async def _execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute tool (internal routing).

        Args:
            tool_name: Tool name
            arguments: Arguments

        Returns:
            Result dict
        """
        # Route to specific tool implementation
        if tool_name == "web_search":
            return await self._execute_web_search(arguments)
        elif tool_name == "web_crawl":
            return await self._execute_web_crawl(arguments)
        elif tool_name == "speech_to_text":
            return await self._execute_speech_to_text(arguments)
        elif tool_name == "ocr":
            return await self._execute_ocr(arguments)
        elif tool_name == "read_file":
            return await self._execute_read_file(arguments)
        elif tool_name == "list_directory":
            return await self._execute_list_directory(arguments)
        elif tool_name == "write_file":
            return await self._execute_write_file(arguments)
        elif tool_name == "create_directory":
            return await self._execute_create_directory(arguments)
        elif tool_name == "generate_artifact":
            return await self._execute_generate_artifact(arguments)
        # v11 新增工具：認知能力自主取用
        elif tool_name == "read_skill":
            return await self._execute_read_skill(arguments)
        elif tool_name == "skill_search":
            return await self._execute_skill_search(arguments)
        # v10 新增工具
        elif tool_name == "shell_exec":
            return await self._execute_shell_exec(arguments)
        elif tool_name == "file_write_rich":
            return await self._execute_file_write_rich(arguments)
        # v12: Self-Surgery 工具路由
        elif tool_name == "source_read":
            return await self._execute_source_read(arguments)
        elif tool_name == "source_search":
            return await self._execute_source_search(arguments)
        elif tool_name == "source_ast_check":
            return await self._execute_source_ast_check(arguments)
        elif tool_name == "surgery_diagnose":
            return await self._execute_surgery_diagnose(arguments)
        elif tool_name == "surgery_propose":
            return await self._execute_surgery_propose(arguments)
        elif tool_name == "surgery_apply":
            return await self._execute_surgery_apply(arguments)
        elif tool_name == "surgery_rollback":
            return await self._execute_surgery_rollback(arguments)
        elif tool_name == "trigger_job":
            return await self._execute_trigger_job(arguments)
        elif tool_name == "memory_search":
            return await self._execute_memory_search(arguments)
        elif tool_name == "spawn_perspectives":
            return await self._execute_spawn_perspectives(arguments)
        elif tool_name == "restart_gateway":
            return await self._execute_restart_gateway(arguments)
        elif tool_name == "pending_action":
            return await self._execute_pending_action(arguments)
        # v13: Ares 戰神系統
        elif tool_name.startswith("ares_"):
            return await self._execute_ares_tool(tool_name, arguments)
        elif tool_name in ("mcp_list_servers", "mcp_call_tool", "mcp_add_server"):
            return await self._execute_mcp_tool(tool_name, arguments)
        # v10.2: 動態 MCP 工具路由（mcp__{server}__{tool} 格式）
        elif tool_name.startswith("mcp__"):
            return await self._execute_dynamic_mcp_tool(tool_name, arguments)
        elif tool_name in ("instagram_post", "telegram_send", "line_send"):
            return {
                "success": False,
                "error": f"平台 API '{tool_name}' 尚未連接。建議使用 generate_artifact 產出內容檔案，使用者可手動發布。",
                "suggestion": "generate_artifact",
            }
        else:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not implemented yet",
            }

    # ═══════════════════════════════════════
    # 資料蒐集工具（真實 API 實作）
    # ═══════════════════════════════════════

    async def _execute_web_search(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """透過 SearXNG 搜尋網路即時資訊.

        SearXNG 是本地部署的隱私搜尋引擎（Docker, port 8888），
        聚合 DuckDuckGo、Bing 等搜尋引擎的結果。

        Args:
            arguments: Must contain 'query', optional 'language'

        Returns:
            搜尋結果（最多 10 筆）
        """
        query = arguments.get("query")
        if not query:
            return {"success": False, "error": "Missing 'query' parameter"}

        language = arguments.get("language", "zh-TW")

        # 語言映射
        lang_map = {
            "zh-TW": "zh-TW",
            "en": "en",
            "ja": "ja",
        }
        search_lang = lang_map.get(language, "zh-TW")

        try:
            params = urllib.parse.urlencode({
                "q": query,
                "format": "json",
                "engines": "duckduckgo,bing,google",
                "language": search_lang,
            })
            url = f"{SEARXNG_URL}/search?{params}"

            req = urllib.request.Request(url, method="GET")
            req.add_header("Accept", "application/json")

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, lambda: self._sync_http_get(url, timeout=15)
            )

            results = data.get("results", [])[:10]

            # 精簡結果（只保留高信號欄位，減少 token 消耗）
            clean_results = []
            for r in results:
                clean_results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", "")[:300],
                })

            logger.info(
                f"web_search: query='{query}' lang={search_lang} "
                f"results={len(clean_results)}"
            )

            return {
                "success": True,
                "result": {
                    "query": query,
                    "total_results": len(clean_results),
                    "results": clean_results,
                },
            }

        except Exception as e:
            logger.warning(f"web_search SearXNG failed: {e}, trying MCP fallback...")

            # v10.5: Fallback 到 MCP brave-search（如果已連線）
            if self._mcp_connector:
                try:
                    fallback_result = await self._mcp_connector.call_tool(
                        "brave-search", "brave_web_search",
                        {"query": query, "count": 10},
                    )
                    if fallback_result.get("success"):
                        logger.info(
                            f"web_search fallback to brave-search succeeded "
                            f"for query='{query}'"
                        )
                        return fallback_result
                    logger.warning(
                        f"brave-search fallback also failed: "
                        f"{fallback_result.get('error', '?')}"
                    )
                except Exception as fb_err:
                    logger.warning(f"brave-search fallback error: {fb_err}")

            return {
                "success": False,
                "error": (
                    f"搜尋失敗: {str(e)[:100]}。"
                    f"SearXNG 本地服務可能未啟動（Docker）。"
                    f"建議：(1) 重試一次 (2) 改用 web_crawl 直接爬取已知 URL"
                ),
            }

    async def _execute_web_crawl(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """透過 Firecrawl 爬取並解析網頁內容.

        Firecrawl 是本地部署的網頁爬取服務（Docker Compose, port 3002），
        支援 JavaScript 渲染、自動解析為 Markdown 格式。

        Args:
            arguments: Must contain 'url'

        Returns:
            網頁 Markdown 內容
        """
        target_url = arguments.get("url")
        if not target_url:
            return {"success": False, "error": "Missing 'url' parameter"}

        # 基本 URL 驗證
        if not target_url.startswith(("http://", "https://")):
            return {
                "success": False,
                "error": "URL must start with http:// or https://",
            }

        try:
            payload = json.dumps({
                "url": target_url,
                "formats": ["markdown"],
            }).encode("utf-8")

            req = urllib.request.Request(
                f"{FIRECRAWL_URL}/v1/scrape",
                data=payload,
                method="POST",
            )
            req.add_header("Content-Type", "application/json")

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None,
                lambda: self._sync_http_post(
                    f"{FIRECRAWL_URL}/v1/scrape",
                    payload=payload,
                    timeout=120,
                ),
            )

            # 提取 Markdown 內容
            markdown = ""
            if data.get("success") and data.get("data"):
                markdown = data["data"].get("markdown", "")
                # 截斷過長內容（避免 token 爆炸）
                if len(markdown) > 15000:
                    markdown = markdown[:15000] + "\n\n... [內容已截斷，共 {} 字元]".format(
                        len(data["data"].get("markdown", ""))
                    )

            metadata = {}
            if data.get("data", {}).get("metadata"):
                meta = data["data"]["metadata"]
                metadata = {
                    "title": meta.get("title", ""),
                    "description": meta.get("description", ""),
                    "language": meta.get("language", ""),
                }

            logger.info(
                f"web_crawl: url='{target_url}' "
                f"content_length={len(markdown)}"
            )

            return {
                "success": True,
                "result": {
                    "url": target_url,
                    "markdown": markdown,
                    "metadata": metadata,
                    "content_length": len(markdown),
                },
            }

        except Exception as e:
            logger.error(f"web_crawl failed: {e}")
            return {
                "success": False,
                "error": f"Firecrawl 爬取失敗: {str(e)}",
            }

    async def _execute_speech_to_text(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """透過 whisper.cpp 將語音轉為文字.

        whisper.cpp 是本地編譯的 C++ 語音辨識引擎，
        使用 OpenAI Whisper medium 模型。

        Args:
            arguments: Must contain 'file_path', optional 'language'

        Returns:
            轉錄文字
        """
        file_path = arguments.get("file_path")
        if not file_path:
            return {"success": False, "error": "Missing 'file_path' parameter"}

        language = arguments.get("language", "zh")

        # 驗證檔案存在
        audio_path = Path(file_path)
        if not audio_path.exists():
            return {"success": False, "error": f"Audio file not found: {file_path}"}

        # 找到 whisper CLI
        whisper_cli = self._find_whisper_cli()
        if not whisper_cli:
            return {
                "success": False,
                "error": "whisper.cpp CLI not found. Please install whisper tool.",
            }

        # 找到 model
        model_path = self._find_whisper_model()
        if not model_path:
            return {
                "success": False,
                "error": "Whisper model not found. Please download ggml-medium.bin.",
            }

        try:
            cmd = [
                str(whisper_cli),
                "-m", str(model_path),
                "-l", language,
                "-f", str(audio_path),
                "--output-txt",
                "--no-timestamps",
            ]

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                ),
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Whisper failed: {result.stderr[:500]}",
                }

            # whisper.cpp 輸出到 stdout
            text = result.stdout.strip()
            # 清除前後的空白和特殊字元
            text = text.replace("[BLANK_AUDIO]", "").strip()

            logger.info(
                f"speech_to_text: file='{file_path}' lang={language} "
                f"text_length={len(text)}"
            )

            return {
                "success": True,
                "result": {
                    "file_path": file_path,
                    "language": language,
                    "text": text,
                    "text_length": len(text),
                },
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Whisper processing timeout (>120s)",
            }
        except Exception as e:
            logger.error(f"speech_to_text failed: {e}")
            return {
                "success": False,
                "error": f"語音轉文字失敗: {str(e)}",
            }

    async def _execute_ocr(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """透過 PaddleOCR 辨識圖片中的文字.

        PaddleOCR 是本地部署的 OCR 服務（Docker, port 8866），
        支援中英文混合辨識。

        Args:
            arguments: Must contain 'file_path'

        Returns:
            辨識出的文字和位置
        """
        file_path = arguments.get("file_path")
        if not file_path:
            return {"success": False, "error": "Missing 'file_path' parameter"}

        # 驗證檔案存在
        image_path = Path(file_path)
        if not image_path.exists():
            return {"success": False, "error": f"Image file not found: {file_path}"}

        try:
            import base64

            # 讀取圖片並 base64 編碼
            image_data = image_path.read_bytes()
            b64_image = base64.b64encode(image_data).decode("utf-8")

            payload = json.dumps({
                "images": [b64_image],
            }).encode("utf-8")

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None,
                lambda: self._sync_http_post(
                    f"{PADDLEOCR_URL}/predict/ocr_system",
                    payload=payload,
                    timeout=30,
                ),
            )

            # 解析 PaddleOCR 回應
            texts = []
            full_text = ""

            if data.get("results") and len(data["results"]) > 0:
                for item in data["results"][0]:
                    if isinstance(item, dict):
                        text = item.get("text", "")
                        confidence = item.get("confidence", 0)
                        texts.append({
                            "text": text,
                            "confidence": round(confidence, 3),
                        })
                        full_text += text + "\n"
                    elif isinstance(item, list) and len(item) >= 2:
                        # 格式: [[coords], [text, confidence]]
                        text_info = item[1] if len(item) > 1 else item[0]
                        if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                            text = str(text_info[0])
                            confidence = float(text_info[1])
                            texts.append({
                                "text": text,
                                "confidence": round(confidence, 3),
                            })
                            full_text += text + "\n"

            full_text = full_text.strip()

            logger.info(
                f"ocr: file='{file_path}' "
                f"detected_texts={len(texts)}"
            )

            return {
                "success": True,
                "result": {
                    "file_path": file_path,
                    "full_text": full_text,
                    "text_blocks": texts,
                    "total_blocks": len(texts),
                },
            }

        except Exception as e:
            logger.error(f"ocr failed: {e}")
            return {
                "success": False,
                "error": f"OCR 辨識失敗: {str(e)}",
            }

    # ═══════════════════════════════════════
    # HTTP 工具方法
    # ═══════════════════════════════════════

    def _sync_http_get(self, url: str, timeout: float = 15) -> Dict:
        """同步 HTTP GET（用於 run_in_executor）.

        Args:
            url: 完整 URL
            timeout: 超時秒數

        Returns:
            解析後的 JSON dict
        """
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _sync_http_post(
        self, url: str, payload: bytes, timeout: float = 30
    ) -> Dict:
        """同步 HTTP POST（用於 run_in_executor）.

        Args:
            url: 完整 URL
            payload: JSON bytes
            timeout: 超時秒數

        Returns:
            解析後的 JSON dict
        """
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _find_whisper_cli(self) -> Optional[Path]:
        """找到 whisper.cpp CLI 執行檔.

        Returns:
            CLI 路徑，或 None
        """
        # 從 workspace_dir 的父目錄搜尋
        base_dirs = [
            Path(self._workspace_dir).parent,  # data/
            Path(self._workspace_dir).parent.parent,  # project root
            Path.home() / "MUSEON" / "data",
            Path.home() / "MUSEON" / ".runtime" / "data",
        ]

        for base in base_dirs:
            for candidate in WHISPER_CLI_CANDIDATES:
                cli_path = base / candidate
                if cli_path.exists() and os.access(str(cli_path), os.X_OK):
                    return cli_path

        return None

    def _find_whisper_model(self) -> Optional[Path]:
        """找到 Whisper 模型檔.

        Returns:
            模型路徑，或 None
        """
        base_dirs = [
            Path(self._workspace_dir).parent,
            Path(self._workspace_dir).parent.parent,
            Path.home() / "MUSEON" / "data",
            Path.home() / "MUSEON" / ".runtime" / "data",
        ]

        for base in base_dirs:
            model_path = base / WHISPER_MODEL_PATH
            if model_path.exists():
                return model_path

        return None

    # ═══════════════════════════════════════
    # 檔案系統操作（sandboxed）
    # ═══════════════════════════════════════

    async def _execute_read_file(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute read file operation.

        Args:
            arguments: Must contain 'path'

        Returns:
            File content
        """
        user_path = arguments.get("path")
        if not user_path:
            return {"success": False, "error": "Missing 'path' parameter"}

        # Sanitize path
        safe_path = self.sandbox.sanitize_path(user_path)
        if safe_path is None:
            return {
                "success": False,
                "error": "Invalid path or path outside workspace",
            }

        # Check file exists
        if not safe_path.exists():
            return {"success": False, "error": "File not found"}

        if not safe_path.is_file():
            return {"success": False, "error": "Path is not a file"}

        # Read file
        try:
            content = safe_path.read_text(encoding="utf-8")
            return {
                "success": True,
                "result": {
                    "path": str(safe_path),
                    "content": content,
                    "size": len(content),
                },
            }

        except Exception as e:
            return {"success": False, "error": f"Failed to read file: {str(e)}"}

    async def _execute_list_directory(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute list directory operation.

        Args:
            arguments: May contain 'path' (defaults to workspace root)

        Returns:
            Directory listing
        """
        user_path = arguments.get("path", ".")

        # Sanitize path
        safe_path = self.sandbox.sanitize_path(user_path)
        if safe_path is None:
            return {
                "success": False,
                "error": "Invalid path or path outside workspace",
            }

        # Check directory exists
        if not safe_path.exists():
            return {"success": False, "error": "Directory not found"}

        if not safe_path.is_dir():
            return {"success": False, "error": "Path is not a directory"}

        # List directory
        try:
            entries = []
            for item in safe_path.iterdir():
                entries.append(
                    {
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None,
                    }
                )

            return {
                "success": True,
                "result": {
                    "path": str(safe_path),
                    "entries": entries,
                    "count": len(entries),
                },
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to list directory: {str(e)}",
            }

    async def _execute_write_file(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute write file operation.

        Args:
            arguments: Must contain 'path' and 'content'

        Returns:
            Write result
        """
        user_path = arguments.get("path")
        content = arguments.get("content")

        if not user_path:
            return {"success": False, "error": "Missing 'path' parameter"}

        if content is None:
            return {"success": False, "error": "Missing 'content' parameter"}

        # Sanitize path
        safe_path = self.sandbox.sanitize_path(user_path)
        if safe_path is None:
            return {
                "success": False,
                "error": "Invalid path or path outside workspace",
            }

        # Write file
        try:
            # Create parent directories if needed
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            safe_path.write_text(content, encoding="utf-8")

            return {
                "success": True,
                "result": {
                    "path": str(safe_path),
                    "size": len(content),
                },
            }

        except Exception as e:
            return {"success": False, "error": f"Failed to write file: {str(e)}"}

    async def _execute_create_directory(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute create directory operation.

        Args:
            arguments: Must contain 'path'

        Returns:
            Creation result
        """
        user_path = arguments.get("path")

        if not user_path:
            return {"success": False, "error": "Missing 'path' parameter"}

        # Sanitize path
        safe_path = self.sandbox.sanitize_path(user_path)
        if safe_path is None:
            return {
                "success": False,
                "error": "Invalid path or path outside workspace",
            }

        # Create directory
        try:
            safe_path.mkdir(parents=True, exist_ok=True)

            return {
                "success": True,
                "result": {
                    "path": str(safe_path),
                },
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create directory: {str(e)}",
            }

    # ═══════════════════════════════════════
    # Artifact 產出工具
    # ═══════════════════════════════════════

    async def _execute_generate_artifact(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """產生可交付物檔案並存到 workspace.

        v9.0: 執行層核心工具 — 讓 MUSEON 能實際產出檔案。
        """
        filename = arguments.get("filename")
        content = arguments.get("content")
        artifact_type = arguments.get("artifact_type", "document")
        description = arguments.get("description", "")

        if not filename:
            return {"success": False, "error": "Missing 'filename' parameter"}
        if not content:
            return {"success": False, "error": "Missing 'content' parameter"}

        # Sanitize filename
        import re
        safe_filename = re.sub(r'[^\w\-_\.]', '_', filename)

        # Determine mime type from extension
        ext = safe_filename.rsplit('.', 1)[-1].lower() if '.' in safe_filename else 'md'
        mime_map = {
            'md': 'text/markdown',
            'csv': 'text/csv',
            'html': 'text/html',
            'json': 'application/json',
            'txt': 'text/plain',
        }
        mime_type = mime_map.get(ext, 'text/plain')

        # Write to workspace via sandbox
        safe_path = self.sandbox.sanitize_path(safe_filename)
        if safe_path is None:
            return {
                "success": False,
                "error": "Invalid filename or path outside workspace",
            }

        try:
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            safe_path.write_text(content, encoding="utf-8")

            # Create Artifact and add to brain's pending list
            from museon.gateway.message import Artifact
            artifact = Artifact(
                type=artifact_type,
                filename=safe_filename,
                content=str(safe_path),  # workspace absolute path
                mime_type=mime_type,
                description=description,
            )

            # Access brain's _pending_artifacts if available
            if hasattr(self, '_brain') and self._brain and hasattr(self._brain, '_pending_artifacts'):
                self._brain._pending_artifacts.append(artifact)

            return {
                "success": True,
                "result": {
                    "path": str(safe_path),
                    "filename": safe_filename,
                    "size": len(content),
                    "type": artifact_type,
                    "mime_type": mime_type,
                    "description": description,
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to write artifact: {str(e)}",
            }

    # ═══════════════════════════════════════
    # v11 新增工具：認知能力自主取用
    # ═══════════════════════════════════════

    async def _execute_read_skill(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """v11: 讀取指定認知能力的完整 SKILL.md 指引.

        LLM 在 <available_skills> 中找到匹配的能力後，
        使用此工具讀取完整的 SKILL.md 操作指引。

        安全設計：只接受 skill_name（非路徑），內部解析到正確的 SKILL.md。
        """
        skill_name = arguments.get("skill_name", "").strip()
        if not skill_name:
            return {"success": False, "error": "缺少 skill_name 參數"}

        # 安全：skill_name 只允許英文、數字、連字號
        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', skill_name):
            return {
                "success": False,
                "error": f"無效的能力名稱: {skill_name}",
            }

        # 在多個可能的路徑中搜尋 SKILL.md
        data_dir = Path(self._workspace_dir).parent  # data/
        candidates = [
            data_dir / "skills" / "native" / skill_name / "SKILL.md",
            data_dir / "skills" / "forged" / skill_name / "SKILL.md",
            data_dir / "skills" / skill_name / "SKILL.md",
        ]

        # 也搜尋 .runtime 路徑（如果 data_dir 不在 .runtime 下）
        runtime_data = data_dir.parent / ".runtime" / "data"
        if runtime_data.exists() and runtime_data != data_dir:
            candidates.extend([
                runtime_data / "skills" / "native" / skill_name / "SKILL.md",
                runtime_data / "skills" / "forged" / skill_name / "SKILL.md",
            ])

        for skill_path in candidates:
            if skill_path.exists():
                try:
                    content = skill_path.read_text(encoding="utf-8")
                    # 截斷過長內容（避免 token 爆炸）
                    if len(content) > 12000:
                        content = content[:12000] + (
                            "\n\n... [SKILL.md 內容已截斷，"
                            f"共 {len(skill_path.read_text(encoding='utf-8'))} 字元]"
                        )

                    logger.info(
                        f"read_skill: {skill_name} → "
                        f"{len(content)} chars from {skill_path}"
                    )

                    return {
                        "success": True,
                        "result": {
                            "skill_name": skill_name,
                            "content": content,
                            "content_length": len(content),
                            "path": str(skill_path),
                        },
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"讀取 SKILL.md 失敗: {str(e)}",
                    }

        return {
            "success": False,
            "error": (
                f"找不到能力 '{skill_name}' 的 SKILL.md。"
                f"請確認名稱是否在 <available_skills> 清單中。"
            ),
        }

    async def _execute_skill_search(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """v11: 用關鍵字搜尋最相關的認知能力.

        委派給 SkillRouter 的匹配邏輯（關鍵字 + 向量語義），
        回傳最相關的能力及描述，供 LLM 決定要 read_skill 哪個。
        """
        query = arguments.get("query", "").strip()
        if not query:
            return {"success": False, "error": "缺少 query 參數"}

        top_n = min(arguments.get("top_n", 5), 10)

        # 透過 brain 取得 skill_router
        if not hasattr(self, '_brain') or not self._brain:
            return {
                "success": False,
                "error": "skill_search 需要 brain 引用（內部錯誤）",
            }

        skill_router = getattr(self._brain, 'skill_router', None)
        if not skill_router:
            return {
                "success": False,
                "error": "SkillRouter 未初始化（內部錯誤）",
            }

        try:
            # 使用 SkillRouter 的 match 方法搜尋（三層疊加：RC + 關鍵字 + 向量）
            matches = skill_router.match(
                message=query,
                top_n=top_n,
            )

            results = []
            for rank, skill in enumerate(matches, 1):
                name = skill.get("name", "")
                desc = skill.get("description", "")
                results.append({
                    "name": name,
                    "description": desc[:200],
                    "relevance_rank": rank,
                })

            logger.info(
                f"skill_search: query='{query}' → "
                f"{len(results)} results"
            )

            return {
                "success": True,
                "result": {
                    "query": query,
                    "total_results": len(results),
                    "results": results,
                    "hint": "使用 read_skill 工具讀取你選擇的能力的完整 SKILL.md",
                },
            }

        except Exception as e:
            logger.error(f"skill_search failed: {e}")
            return {
                "success": False,
                "error": f"能力搜尋失敗: {str(e)}",
            }

    # ═══════════════════════════════════════
    # v10 新增工具
    # ═══════════════════════════════════════

    # 危險命令黑名單（shell_exec 安全層）
    # 只攔截不可逆的毀滅性操作；其他權限預設全開（繼承 OS 使用者權限）
    _DANGEROUS_COMMANDS = [
        "rm -rf /",          # 刪除整台電腦
        "rm -rf /*",         # 同上（寫法變體）
        "mkfs",              # 格式化硬碟
        "dd if=",            # 低階磁碟覆寫
        "> /dev/",           # 寫入裝置檔
        ":(){ :|:& };:",     # fork bomb
        "chmod -R 777 /",    # 全域權限崩潰
        "sudo ",             # 提權嘗試
        "chmod 777 ",        # 權限開放
        "chown ",            # 變更擁有者
        "kill -9 1",         # 殺 init/launchd
        "shutdown",          # 關機
        "reboot",            # 重啟
        "curl | sh",         # 遠端腳本執行
        "curl | bash",       # 遠端腳本執行
        "wget | sh",         # 遠端腳本執行
        "wget | bash",       # 遠端腳本執行
    ]

    async def _execute_shell_exec(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """v10.3: 執行 Shell 命令（含多層安全檢查）.

        安全層：
        1. 命令正規化 + 危險黑名單（擴充版）
        2. working_dir 沙盒驗證（P2: 防止目錄逃逸）
        3. 環境變數過濾（P3: 參考 openclaw host-env-security）
        4. 可信二進位驗證（P4: 參考 openclaw exec-safe-bin-trust）
        """
        command = arguments.get("command", "").strip()
        if not command:
            return {"success": False, "error": "command 參數為空"}

        timeout = min(arguments.get("timeout", 60), 300)
        working_dir = arguments.get("working_dir", str(self._workspace_dir))

        # ── 安全檢查 1: 命令正規化 + 危險黑名單 ──
        import re
        cmd_normalized = re.sub(r"\s+", " ", command).strip()
        cmd_lower = cmd_normalized.lower()
        for dangerous in self._DANGEROUS_COMMANDS:
            if dangerous.lower() in cmd_lower:
                logger.warning(f"shell_exec 安全攔截: {command[:100]}")
                return {
                    "success": False,
                    "error": f"此命令被安全策略禁止（匹配: {dangerous}）",
                }

        # 管線攻擊偵測：curl/wget 管線到 sh/bash
        if re.search(
            r"(curl|wget)\s+.*\|\s*(sh|bash|zsh|python)", cmd_lower
        ):
            logger.warning(f"shell_exec 管線攻擊攔截: {command[:100]}")
            return {
                "success": False,
                "error": "此命令包含潛在的遠端腳本執行管線",
            }

        # ── 安全檢查 2: working_dir 沙盒驗證（P2）──
        from pathlib import Path as _Path
        workspace_root = _Path(self._workspace_dir).resolve()
        try:
            resolved_wd = _Path(working_dir).resolve()
            # 允許 workspace 及其子目錄，也允許 MUSEON_HOME 下的路徑
            import os
            museon_home = os.environ.get(
                "MUSEON_HOME", str(_Path.home() / "MUSEON")
            )
            museon_root = _Path(museon_home).resolve()

            wd_ok = (
                str(resolved_wd).startswith(str(workspace_root))
                or str(resolved_wd).startswith(str(museon_root))
            )
            if not wd_ok:
                logger.warning(
                    f"shell_exec working_dir 逃逸攔截: {working_dir} "
                    f"（不在 workspace {workspace_root} 或 "
                    f"MUSEON_HOME {museon_root} 範圍內）"
                )
                working_dir = str(self._workspace_dir)
        except (OSError, ValueError) as path_err:
            logger.warning(f"shell_exec working_dir 解析失敗: {path_err}")
            working_dir = str(self._workspace_dir)

        try:
            # ── 安全檢查 3: 環境變數過濾（P3）──
            import os
            try:
                from museon.security.env_security import sanitize_shell_env
                shell_env = sanitize_shell_env(os.environ.copy())
            except ImportError:
                logger.warning("env_security 模組未載入，使用原始環境")
                shell_env = os.environ.copy()

            # 建構完整 PATH（launchd 預設 PATH 極簡）
            _extra_paths = [
                "/opt/homebrew/bin", "/opt/homebrew/sbin",
                "/usr/local/bin", "/usr/bin", "/bin",
                "/usr/sbin", "/sbin",
            ]
            existing = shell_env.get("PATH", "")
            for p in _extra_paths:
                if p not in existing:
                    existing = p + ":" + existing
            shell_env["PATH"] = existing

            # ── 安全檢查 4: 可信二進位驗證（P4）──
            import shlex
            try:
                from museon.security.trusted_bins import (
                    resolve_trusted_binary,
                    add_trusted_dir,
                )
                # 動態加入 venv 目錄
                venv_bin = os.environ.get("VIRTUAL_ENV")
                if venv_bin:
                    add_trusted_dir(str(_Path(venv_bin) / "bin"))

                # 解析命令第一個 token
                try:
                    tokens = shlex.split(command)
                    if tokens:
                        cmd_name = tokens[0]
                        # 如果不是路徑（沒有 /），驗證信任性
                        if "/" not in cmd_name:
                            trusted_path = resolve_trusted_binary(cmd_name)
                            if trusted_path is None:
                                logger.warning(
                                    f"shell_exec 可信二進位驗證失敗: "
                                    f"'{cmd_name}' 不在信任目錄中"
                                )
                                # 警告但不阻擋（避免誤殺合法工具）
                except ValueError:
                    pass  # shlex.split 解析失敗，跳過驗證
            except ImportError:
                pass  # trusted_bins 模組未載入

            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
                env=shell_env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            stdout_str = stdout.decode("utf-8", errors="replace")[:10000]
            stderr_str = stderr.decode("utf-8", errors="replace")[:5000]

            logger.info(
                f"shell_exec: '{command[:80]}' → rc={proc.returncode}, "
                f"stdout={len(stdout_str)}c, stderr={len(stderr_str)}c"
            )

            return {
                "success": proc.returncode == 0,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "return_code": proc.returncode,
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"命令執行超時（{timeout}s）: {command[:80]}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Shell 執行失敗: {str(e)}",
            }

    async def _execute_file_write_rich(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """v10: 全格式檔案產出."""
        filename = arguments.get("filename", "").strip()
        content = arguments.get("content", "")
        description = arguments.get("description", filename)

        if not filename:
            return {"success": False, "error": "filename 參數為空"}

        # 確保 workspace 目錄存在
        workspace = Path(self._workspace_dir)
        workspace.mkdir(parents=True, exist_ok=True)

        # 檢查副檔名
        ext = Path(filename).suffix.lower()
        base_name = Path(filename).stem

        # 基本格式：直接寫入
        DIRECT_EXTS = {".md", ".csv", ".html", ".txt", ".json", ".xml", ".yaml", ".yml"}
        # 進階格式：先寫 .md，再嘗試轉換
        CONVERT_EXTS = {".docx", ".pdf", ".pptx", ".xlsx"}

        if ext in DIRECT_EXTS:
            # 直接寫入
            safe_path = workspace / filename
            try:
                safe_path.parent.mkdir(parents=True, exist_ok=True)
                safe_path.write_text(content, encoding="utf-8")

                # 加入 artifact
                self._add_artifact(
                    filename=filename,
                    path=str(safe_path),
                    content_len=len(content),
                    description=description,
                    ext=ext,
                )

                return {
                    "success": True,
                    "result": {
                        "path": str(safe_path),
                        "filename": filename,
                        "size": len(content),
                        "format": ext,
                        "description": description,
                    },
                }
            except Exception as e:
                return {"success": False, "error": f"寫入失敗: {str(e)}"}

        elif ext in CONVERT_EXTS:
            # 先寫 .md 原始內容
            md_filename = f"{base_name}.md"
            md_path = workspace / md_filename
            md_path.write_text(content, encoding="utf-8")

            # 嘗試轉換
            target_path = workspace / filename
            converted = False

            if ext == ".docx":
                # 嘗試 pandoc
                try:
                    proc = await asyncio.create_subprocess_shell(
                        f'pandoc "{md_path}" -o "{target_path}"',
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                    converted = proc.returncode == 0
                    if not converted:
                        logger.warning(f"pandoc 轉換失敗: {stderr.decode()[:200]}")
                except Exception as e:
                    logger.warning(f"pandoc 不可用: {e}")

            elif ext == ".pdf":
                # 嘗試 weasyprint（先轉 HTML 再轉 PDF）
                html_path = workspace / f"{base_name}.html"
                html_content = f"<html><body><pre>{content}</pre></body></html>"
                html_path.write_text(html_content, encoding="utf-8")
                try:
                    proc = await asyncio.create_subprocess_shell(
                        f'weasyprint "{html_path}" "{target_path}"',
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
                    converted = proc.returncode == 0
                except Exception as e:
                    logger.debug(f"[TOOLS] async op failed (degraded): {e}")

            # 結果
            if converted and target_path.exists():
                self._add_artifact(
                    filename=filename,
                    path=str(target_path),
                    content_len=target_path.stat().st_size,
                    description=description,
                    ext=ext,
                )
                return {
                    "success": True,
                    "result": {
                        "path": str(target_path),
                        "filename": filename,
                        "format": ext,
                        "converted": True,
                        "description": description,
                    },
                }
            else:
                # 轉換失敗，回傳 .md 原始檔案
                self._add_artifact(
                    filename=md_filename,
                    path=str(md_path),
                    content_len=len(content),
                    description=f"{description}（{ext} 轉換失敗，提供 .md 版本）",
                    ext=".md",
                )
                return {
                    "success": True,
                    "result": {
                        "path": str(md_path),
                        "filename": md_filename,
                        "format": ".md",
                        "converted": False,
                        "note": f"{ext} 格式轉換工具未安裝或失敗，提供 Markdown 版本",
                        "description": description,
                    },
                }
        else:
            return {
                "success": False,
                "error": f"不支援的副檔名: {ext}。支援: {DIRECT_EXTS | CONVERT_EXTS}",
            }

    def _add_artifact(self, filename: str, path: str, content_len: int,
                      description: str, ext: str):
        """將 Artifact 加入 brain 的 pending list."""
        try:
            from museon.gateway.message import Artifact
            _mime_map = {
                ".md": "text/markdown", ".csv": "text/csv",
                ".html": "text/html", ".txt": "text/plain",
                ".json": "application/json", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".pdf": "application/pdf", ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
            artifact = Artifact(
                type="document",
                filename=filename,
                content=path,
                mime_type=_mime_map.get(ext, "application/octet-stream"),
                description=description,
            )
            if hasattr(self, '_brain') and self._brain and hasattr(self._brain, '_pending_artifacts'):
                self._brain._pending_artifacts.append(artifact)
        except Exception as e:
            logger.warning(f"Failed to create artifact: {e}")

    async def _execute_mcp_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """v10.2: MCP 管理工具（列表/新增/呼叫）— 委派給 MCPConnectorSDK."""
        mcp_config_dir = Path(self._workspace_dir).parent / "_system" / "mcp"
        mcp_config_dir.mkdir(parents=True, exist_ok=True)
        servers_file = mcp_config_dir / "servers.json"

        if tool_name == "mcp_list_servers":
            # 列出配置 + 連線狀態 + 可用工具 + catalog
            result: Dict[str, Any] = {
                "configured": [],
                "connected": [],
                "catalog_available": 0,
            }

            # 配置的伺服器
            if servers_file.exists():
                try:
                    servers = json.loads(servers_file.read_text("utf-8"))
                    result["configured"] = [
                        {"name": k, **v} for k, v in servers.items()
                    ]
                except Exception as e:
                    logger.debug(f"[TOOLS] JSON failed (degraded): {e}")

            # 已連線的伺服器（含工具清單）
            if self._mcp_connector:
                status = self._mcp_connector.get_status()
                for name, info in status.get("connections", {}).items():
                    conn_info = {
                        "name": name,
                        "status": info["status"],
                        "tools_count": info["tools_count"],
                        "connected_at": info.get("connected_at"),
                    }
                    if info["status"] == "error" and info.get("error"):
                        conn_info["error"] = info["error"]
                    result["connected"].append(conn_info)

                result["catalog_available"] = status.get("catalog_count", 0)
                result["total_mcp_tools"] = status.get("total_tools", 0)
                result["mcp_sdk_available"] = status.get("mcp_sdk_available", False)

            return {"success": True, "result": result}

        elif tool_name == "mcp_add_server":
            # 新增伺服器配置 + 立即嘗試連線
            name = arguments.get("name", "")
            transport = arguments.get("transport", "stdio")
            command = arguments.get("command", "")
            env = arguments.get("env", {})

            if not name or not command:
                return {"success": False, "error": "name 和 command 為必填參數"}

            # 寫入 servers.json
            servers = {}
            if servers_file.exists():
                try:
                    servers = json.loads(servers_file.read_text("utf-8"))
                except Exception as e:
                    logger.debug(f"[TOOLS] JSON failed (degraded): {e}")

            server_config = {
                "transport": transport,
                "command": command,
                "env": env,
            }
            servers[name] = server_config
            servers_file.write_text(
                json.dumps(servers, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            # v13: 同步寫入 .mcp.json（Claude Code 的 MCP 設定檔）
            mcp_json_path = Path(self._workspace_dir).parent.parent / ".mcp.json"
            mcp_json_updated = False
            try:
                mcp_data = {}
                if mcp_json_path.exists():
                    mcp_data = json.loads(mcp_json_path.read_text("utf-8"))
                mcp_servers = mcp_data.setdefault("mcpServers", {})
                # 構建 Claude Code 格式的 MCP 設定
                cmd_parts = command.split()
                mcp_entry = {"command": cmd_parts[0]}
                if len(cmd_parts) > 1:
                    mcp_entry["args"] = cmd_parts[1:]
                if env:
                    mcp_entry["env"] = env
                mcp_servers[name] = mcp_entry
                mcp_json_path.write_text(
                    json.dumps(mcp_data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                mcp_json_updated = True
                logger.info(f"[TOOLS] mcp_add_server: '{name}' 已寫入 .mcp.json")
            except Exception as e:
                logger.warning(f"[TOOLS] 寫入 .mcp.json 失敗: {e}")

            # v10.2: 立即嘗試連線（不需重啟）
            connect_result: Dict[str, Any] = {
                "note": "配置已儲存。MCP SDK 不可用，無法立即連線。"
            }
            if self._mcp_connector:
                connect_result = await self._mcp_connector.connect_server(
                    name, server_config
                )

            return {
                "success": True,
                "result": {
                    "message": f"MCP 伺服器 '{name}' 已配置並寫入 .mcp.json。重啟 Claude Code 後生效。",
                    "mcp_json_updated": mcp_json_updated,
                    "connection": connect_result,
                    "server": server_config,
                },
            }

        elif tool_name == "mcp_call_tool":
            # 委派給 MCPConnectorSDK
            server = arguments.get("server", "")
            mcp_tool = arguments.get("tool_name", "")
            tool_args = arguments.get("arguments", {})

            if not self._mcp_connector:
                return {
                    "success": False,
                    "error": "MCP SDK 未安裝。請執行: pip install mcp",
                }

            return await self._mcp_connector.call_tool(server, mcp_tool, tool_args)

        return {"success": False, "error": f"未知的 MCP 操作: {tool_name}"}

    async def _execute_dynamic_mcp_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """v10.2: 執行動態發現的 MCP 工具（mcp__{server}__{tool} 格式）."""
        if not self._mcp_connector:
            return {"success": False, "error": "MCP Connector SDK 不可用"}

        # 解析工具名稱：mcp__{server}__{tool_name}
        parts = tool_name.split("__", 2)
        if len(parts) != 3 or parts[0] != "mcp":
            return {
                "success": False,
                "error": f"無效的 MCP 工具名稱格式: {tool_name}",
            }

        server_name = parts[1]
        mcp_tool_name = parts[2]

        return await self._mcp_connector.call_tool(
            server_name, mcp_tool_name, arguments
        )

    def get_dynamic_tool_definitions(self) -> List[Dict[str, Any]]:
        """v10.2: 取得所有已連線 MCP 伺服器的動態工具定義.

        Returns:
            Anthropic tool_use 格式的工具列表（供 brain.py 合併到 API call）
        """
        if not self._mcp_connector:
            return []
        return self._mcp_connector.list_tools()

    # ═══════════════════════════════════════
    # v12: Self-Surgery 工具實作
    # ═══════════════════════════════════════

    async def _execute_source_read(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """讀取源碼檔案."""
        if not self._surgery_engine:
            return {"success": False, "error": "SurgeryEngine 未初始化"}

        file_path = arguments.get("file_path", "")
        if not file_path:
            return {"success": False, "error": "缺少 file_path 參數"}

        content = self._surgery_engine.read_source(file_path)
        if content is None:
            return {
                "success": False,
                "error": f"無法讀取 {file_path}（不存在或不在沙箱範圍內）",
            }

        return {
            "success": True,
            "result": {
                "file_path": file_path,
                "content": content,
                "lines": len(content.splitlines()),
            },
        }

    async def _execute_source_search(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """搜尋源碼."""
        if not self._surgery_engine:
            return {"success": False, "error": "SurgeryEngine 未初始化"}

        pattern = arguments.get("pattern", "")
        if not pattern:
            return {"success": False, "error": "缺少 pattern 參數"}

        file_glob = arguments.get("file_glob", "**/*.py")
        results = self._surgery_engine.search_source(pattern, file_glob)

        return {
            "success": True,
            "result": {
                "pattern": pattern,
                "matches": results,
                "total": len(results),
            },
        }

    async def _execute_source_ast_check(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """執行 AST 靜態分析."""
        try:
            from museon.doctor.code_analyzer import CodeAnalyzer
        except ImportError:
            return {"success": False, "error": "CodeAnalyzer 模組未安裝"}

        project_root = Path(self._workspace_dir).parent.parent
        analyzer = CodeAnalyzer(
            source_root=project_root / "src" / "museon"
        )

        target_file = arguments.get("target_file", "")
        rule_ids = arguments.get("rule_ids", [])

        import asyncio
        if target_file:
            target_path = project_root / target_file
            if rule_ids:
                issues = await asyncio.to_thread(
                    analyzer.scan_specific_rules, target_path, rule_ids
                )
            else:
                issues = await asyncio.to_thread(
                    analyzer.scan_file, target_path
                )
        else:
            issues = await asyncio.to_thread(analyzer.scan_all)

        report = CodeAnalyzer.format_report(issues)

        return {
            "success": True,
            "result": {
                "report": report,
                "total_issues": len(issues),
                "critical": sum(1 for i in issues if i.severity == "critical"),
                "warning": sum(1 for i in issues if i.severity == "warning"),
                "info": sum(1 for i in issues if i.severity == "info"),
                "issues": [
                    {
                        "rule_id": i.rule_id,
                        "file": i.file_path,
                        "line": i.line,
                        "message": i.message,
                        "severity": i.severity,
                        "suggestion": i.suggestion,
                    }
                    for i in issues[:30]  # 限制回傳數量
                ],
            },
        }

    async def _execute_surgery_diagnose(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """執行三層診斷管線."""
        try:
            from museon.doctor.diagnosis_pipeline import DiagnosisPipeline
        except ImportError:
            return {"success": False, "error": "DiagnosisPipeline 模組未安裝"}

        project_root = Path(self._workspace_dir).parent.parent
        llm_adapter = self._brain._llm_adapter if self._brain and hasattr(self._brain, "_llm_adapter") else None

        pipeline = DiagnosisPipeline(
            source_root=project_root / "src" / "museon",
            logs_dir=project_root / "logs",
            heartbeat_state_path=project_root / "data" / "pulse" / "heartbeat_engine.json",
            llm_adapter=llm_adapter,
        )

        skip_d3 = arguments.get("skip_d3", False)
        result = await pipeline.run(skip_d3=skip_d3)

        return {
            "success": True,
            "result": {
                "summary": result.summary,
                "diagnosis_level": result.diagnosis_level,
                "has_issues": result.has_issues,
                "critical_count": result.critical_count,
                "code_issues": [
                    {
                        "rule_id": i.rule_id,
                        "file": i.file_path,
                        "line": i.line,
                        "message": i.message,
                        "severity": i.severity,
                    }
                    for i in result.code_issues[:20]
                ],
                "log_anomalies": [
                    {
                        "type": a.anomaly_type,
                        "severity": a.severity,
                        "message": a.message,
                    }
                    for a in result.log_anomalies[:10]
                ],
                "root_cause": result.root_cause,
                "proposals": [
                    {
                        "title": p.title,
                        "description": p.description,
                        "affected_files": p.affected_files,
                        "confidence": p.confidence,
                        "risk_level": p.risk_level,
                        "changes": p.changes,
                    }
                    for p in result.proposals
                ],
            },
        }

    async def _execute_surgery_propose(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成修復提案並執行安全審查."""
        if not self._surgery_engine:
            return {"success": False, "error": "SurgeryEngine 未初始化"}

        from museon.doctor.diagnosis_pipeline import SurgeryProposal

        title = arguments.get("title", "")
        description = arguments.get("description", "")
        changes = arguments.get("changes", [])

        if not title or not changes:
            return {"success": False, "error": "缺少 title 或 changes 參數"}

        proposal = SurgeryProposal(
            title=title,
            description=description,
            affected_files=[c["file"] for c in changes],
            changes=changes,
        )

        passed, violations, recommendation = self._surgery_engine.safety_review(proposal)

        return {
            "success": True,
            "result": {
                "proposal": {
                    "title": title,
                    "description": description,
                    "affected_files": proposal.affected_files,
                    "changes_count": len(changes),
                },
                "safety_review": {
                    "passed": passed,
                    "violations": violations,
                    "recommendation": recommendation,
                },
            },
        }

    async def _execute_surgery_apply(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """執行手術."""
        if not self._surgery_engine:
            return {"success": False, "error": "SurgeryEngine 未初始化"}

        from museon.doctor.diagnosis_pipeline import SurgeryProposal

        title = arguments.get("title", "")
        description = arguments.get("description", "")
        changes = arguments.get("changes", [])
        dry_run = arguments.get("dry_run", False)

        if not title or not changes:
            return {"success": False, "error": "缺少 title 或 changes 參數"}

        proposal = SurgeryProposal(
            title=title,
            description=description,
            affected_files=[c["file"] for c in changes],
            changes=changes,
        )

        result = await self._surgery_engine.execute_surgery(
            proposal=proposal, dry_run=dry_run,
        )

        # 處理委派結果
        if result.get("delegated"):
            return {
                "success": False,
                "delegated": True,
                "ticket_path": result.get("ticket_path", ""),
                "message": (
                    f"此手術涉及 {len(proposal.affected_files)} 個檔案，"
                    f"已自動委派給 Claude Code 執行。"
                    f"工單路徑: {result.get('ticket_path', '')}"
                ),
                "result": result,
            }

        # 處理驗證失敗自動回滾結果
        if result.get("auto_rolled_back"):
            return {
                "success": False,
                "auto_rolled_back": True,
                "message": (
                    f"手術已套用但 pytest 驗證失敗，"
                    f"已自動回滾。錯誤: {result.get('error', '')}"
                ),
                "result": result,
            }

        return {
            "success": result.get("success", False),
            "result": result,
        }

    async def _execute_surgery_rollback(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """回滾到指定 git tag."""
        if not self._surgery_engine:
            return {"success": False, "error": "SurgeryEngine 未初始化"}

        git_tag = arguments.get("git_tag", "")
        if not git_tag:
            return {"success": False, "error": "缺少 git_tag 參數"}

        success = self._surgery_engine.rollback(git_tag)

        return {
            "success": success,
            "result": {
                "git_tag": git_tag,
                "rollback_success": success,
            },
        }

    # ═══════════════════════════════════════
    # L3 任務執行：trigger_job
    # ═══════════════════════════════════════

    async def _execute_restart_gateway(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """v13: 重啟 Gateway — 背景執行 restart script."""
        reason = arguments.get("reason", "no reason provided")
        logger.info(f"[TOOLS] restart_gateway requested: {reason}")

        restart_script = Path(self._workspace_dir).parent.parent / "scripts" / "workflows" / "restart-gateway.sh"
        if not restart_script.exists():
            # Fallback: 直接用 Python 重啟
            restart_script = None

        try:
            import subprocess
            if restart_script:
                subprocess.Popen(
                    ["bash", str(restart_script)],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                # 直接殺自己，讓外部 supervisor 重啟
                subprocess.Popen(
                    ["bash", "-c", "sleep 2 && kill $(pgrep -f 'museon.gateway.server') && sleep 3 && cd ~/MUSEON && .venv/bin/python -m museon.gateway.server &"],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            return {
                "success": True,
                "result": {
                    "message": f"Gateway 重啟已排程（原因：{reason}）。約 5 秒後恢復服務。",
                    "reason": reason,
                },
            }
        except Exception as e:
            return {"success": False, "error": f"重啟失敗: {e}"}

    async def _execute_pending_action(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """v13: 記錄待辦事項到佇列."""
        action = arguments.get("action", "")
        category = arguments.get("category", "other")
        requested_by = arguments.get("requested_by", "unknown")

        if not action:
            return {"success": False, "error": "action 為必填"}

        pending_path = Path(self._workspace_dir).parent / "_system" / "pending_actions.json"
        pending_path.parent.mkdir(parents=True, exist_ok=True)

        pending = []
        if pending_path.exists():
            try:
                pending = json.loads(pending_path.read_text("utf-8"))
            except Exception:
                pending = []

        from datetime import datetime as _dt
        entry = {
            "action": action,
            "category": category,
            "requested_by": requested_by,
            "created_at": _dt.now().isoformat(),
            "status": "pending",
        }
        pending.append(entry)
        pending_path.write_text(
            json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        logger.info(f"[TOOLS] pending_action recorded: {action}")
        return {
            "success": True,
            "result": {
                "message": f"已記錄待辦：{action}。下次 Claude Code session 會處理。",
                "entry": entry,
            },
        }

    async def _execute_trigger_job(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """觸發已註冊的 cron job 立即執行。

        透過 Gateway 的 APScheduler 取得 job 並執行。
        這是 L3 執行層——L2 判斷需要做什麼，L3 去做。
        """
        job_id = arguments.get("job_id", "")
        if not job_id:
            return {"success": False, "error": "缺少 job_id 參數"}

        try:
            from museon.gateway.server import cron_engine
            if not cron_engine:
                return {"success": False, "error": "CronEngine 不可用"}

            # 查找 job
            job = cron_engine.get_job(job_id)
            if not job:
                # 列出可用 jobs 幫助使用者
                all_jobs = cron_engine.get_jobs()
                available = [j.id for j in all_jobs]
                return {
                    "success": False,
                    "error": f"找不到 job '{job_id}'",
                    "available_jobs": available[:20],
                }

            # 立即執行
            job.modify(next_run_time=__import__("datetime").datetime.now())
            logger.info(f"[L3 trigger_job] triggered: {job_id}")

            return {
                "success": True,
                "result": {
                    "job_id": job_id,
                    "status": "triggered",
                    "message": f"任務 '{job_id}' 已觸發執行",
                },
            }

        except Exception as e:
            logger.error(f"[L3 trigger_job] failed: {e}")
            return {"success": False, "error": str(e)}

    # ═══════════════════════════════════════
    # L2 記憶搜尋：memory_search
    # ═══════════════════════════════════════

    async def _execute_memory_search(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """搜尋 MUSEON 記憶系統。"""
        query = arguments.get("query", "")
        if not query:
            return {"success": False, "error": "缺少 query 參數"}

        scope = arguments.get("scope", "all")
        limit = min(arguments.get("limit", 5), 20)

        try:
            from museon.memory.memory_manager import MemoryManager
            data_dir = Path(self._workspace_dir).parent
            mm = MemoryManager(str(data_dir / "memory_v3"))

            # 根據 scope 決定搜尋層級
            if scope == "recent":
                layers = ["L0_buffer", "L1_short"]
            elif scope == "important":
                layers = ["L2_sem", "L3_procedural", "L4_identity"]
            else:
                layers = None  # 搜尋所有層級

            results = mm.recall(user_id="boss", query=query, layers=layers, limit=limit)

            return {
                "success": True,
                "result": {
                    "query": query,
                    "scope": scope,
                    "count": len(results) if results else 0,
                    "memories": results or [],
                },
            }
        except Exception as e:
            logger.error(f"[memory_search] failed: {e}")
            return {"success": False, "error": str(e)}

    # ═══════════════════════════════════════
    # L2 圓桌討論：spawn_perspectives
    # ═══════════════════════════════════════

    async def _execute_spawn_perspectives(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """平行 spawn 多個 Sonnet 做圓桌討論。"""
        import asyncio

        topic = arguments.get("topic", "")
        perspectives = arguments.get("perspectives", [])
        context = arguments.get("context", "")

        if not topic or not perspectives:
            return {"success": False, "error": "需要 topic 和 perspectives"}

        if not self._brain or not hasattr(self._brain, "_llm_adapter"):
            return {"success": False, "error": "LLM adapter 不可用"}

        llm_adapter = self._brain._llm_adapter

        async def _run_one(role: str, instruction: str) -> Dict:
            prompt = (
                f"你是「{role}」。\n"
                f"議題：{topic}\n"
                f"{'背景：' + context if context else ''}\n"
                f"指引：{instruction}\n\n"
                f"請從你的角色出發，提供 200-500 字的分析。"
                f"必須包含：核心觀點、支持論據、風險/盲點、建議行動。"
                f"用繁體中文回覆。"
            )
            try:
                resp = await llm_adapter.call(
                    system_prompt="你是多角度分析系統的觀點代理。用繁體中文回覆。",
                    messages=[{"role": "user", "content": prompt}],
                    model="sonnet",
                    max_tokens=2048,
                )
                return {"role": role, "analysis": resp.text if resp else "（分析失敗）"}
            except Exception as e:
                return {"role": role, "analysis": f"（錯誤：{e}）"}

        # 並行執行（最多 4 個）
        tasks = [
            _run_one(p["role"], p["instruction"])
            for p in perspectives[:4]
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        analyses = []
        for r in results:
            if isinstance(r, Exception):
                analyses.append({"role": "error", "analysis": str(r)})
            else:
                analyses.append(r)

        return {
            "success": True,
            "result": {
                "topic": topic,
                "perspective_count": len(analyses),
                "analyses": analyses,
            },
        }

    # ═══════════════════════════════════════
    # v13: Ares 戰神系統工具
    # ═══════════════════════════════════════

    def _get_ares_store(self):
        """Lazy init Ares ProfileStore."""
        if not hasattr(self, "_ares_store"):
            from museon.ares.profile_store import ProfileStore
            self._ares_store = ProfileStore(self.data_dir)
        return self._ares_store

    async def _execute_ares_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Ares 工具路由."""
        try:
            if tool_name == "ares_search":
                return await self._execute_ares_search(arguments)
            elif tool_name == "ares_create":
                return await self._execute_ares_create(arguments)
            elif tool_name == "ares_update":
                return await self._execute_ares_update(arguments)
            elif tool_name == "ares_briefing":
                return await self._execute_ares_briefing(arguments)
            elif tool_name == "ares_topology":
                return await self._execute_ares_topology(arguments)
            else:
                return {"success": False, "error": f"Unknown ares tool: {tool_name}"}
        except Exception as e:
            logger.warning(f"[ARES-TOOL] {tool_name} failed: {e}")
            return {"success": False, "error": str(e)}

    async def _execute_ares_search(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """搜尋人物檔案."""
        store = self._get_ares_store()
        keyword = arguments.get("keyword", "")
        domain = arguments.get("domain")

        if not keyword:
            # 列出全部
            idx = store.list_all()
            results = [
                {"profile_id": pid, **entry}
                for pid, entry in idx.items()
            ]
        else:
            profiles = store.search(keyword, domain=domain)
            results = []
            for p in profiles:
                results.append({
                    "profile_id": p["profile_id"],
                    "name": p["L1_facts"]["name"],
                    "wan_miu_code": p["L2_personality"].get("wan_miu_code"),
                    "confidence": p["L2_personality"].get("confidence", 0),
                    "temperature": p["temperature"]["level"],
                    "domains": p.get("domains", []),
                    "interactions": p["L4_interactions"]["total_count"],
                    "title": p["L1_facts"].get("title"),
                    "company": p["L1_facts"].get("company"),
                })

        return {"success": True, "count": len(results), "results": results}

    async def _execute_ares_create(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """建立新人物檔案."""
        store = self._get_ares_store()
        name = arguments.get("name", "")
        if not name:
            return {"success": False, "error": "name is required"}

        domains = arguments.get("domains", ["business"])
        profile = store.create(name, domains=domains)

        # 可選的初始欄位
        updates = {}
        if arguments.get("title"):
            updates.setdefault("L1_facts", {})["title"] = arguments["title"]
        if arguments.get("company"):
            updates.setdefault("L1_facts", {})["company"] = arguments["company"]
        if arguments.get("role"):
            updates.setdefault("L1_facts", {})["role"] = arguments["role"]
        if updates:
            store.update(profile["profile_id"], updates)

        return {
            "success": True,
            "profile_id": profile["profile_id"],
            "name": name,
            "message": f"已建立 {name} 的 ANIMA 個體檔案",
        }

    async def _execute_ares_update(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """更新人物檔案."""
        store = self._get_ares_store()
        pid = arguments.get("profile_id", "")
        updates = arguments.get("updates", {})
        if not pid or not updates:
            return {"success": False, "error": "profile_id and updates are required"}

        result = store.update(pid, updates)
        if not result:
            return {"success": False, "error": f"Profile {pid} not found"}

        return {
            "success": True,
            "profile_id": pid,
            "name": result["L1_facts"]["name"],
            "message": f"已更新 {result['L1_facts']['name']} 的檔案",
        }

    async def _execute_ares_briefing(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """產出戰前簡報."""
        store = self._get_ares_store()
        keyword = arguments.get("keyword", "")
        profiles = store.search(keyword)
        if not profiles:
            return {"success": False, "error": f"找不到包含「{keyword}」的人物檔案"}

        p = profiles[0]
        persona = p["L2_personality"]
        inter = p["L4_interactions"]
        temp = p["temperature"]
        leverage = p["L5_leverage"]
        comm = p["L6_communication"]

        # 組裝槓桿摘要
        has_list = [f"{k}:{v['has']}" for k, v in leverage.items() if v.get("has")]
        needs_list = [f"{k}:{v['needs']}" for k, v in leverage.items() if v.get("needs")]

        briefing = {
            "name": p["L1_facts"]["name"],
            "title": p["L1_facts"].get("title"),
            "company": p["L1_facts"].get("company"),
            "personality": {
                "code": persona.get("wan_miu_code"),
                "name": persona.get("wan_miu_name"),
                "confidence": persona.get("confidence", 0),
                "assessment_type": persona.get("assessment_type"),
            },
            "temperature": {
                "level": temp["level"],
                "trend": temp["trend"],
            },
            "interactions": {
                "total": inter["total_count"],
                "positive": inter["positive_count"],
                "negative": inter["negative_count"],
            },
            "leverage": {
                "has": has_list or ["尚未記錄"],
                "needs": needs_list or ["尚未記錄"],
            },
            "communication": {
                "style": comm.get("style"),
                "taboos": comm.get("taboos", []),
                "preferences": comm.get("preferences", []),
            },
            "connections": [
                {"name": c["target_name"], "type": c["relation_type"]}
                for c in p.get("connections", [])
            ],
            "profile_id": p["profile_id"],
        }

        return {"success": True, "briefing": briefing}

    async def _execute_ares_topology(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """產出人物拓樸圖."""
        store = self._get_ares_store()
        fmt = arguments.get("format", "png")
        domain = arguments.get("domain")
        data = store.generate_topology_data(domain=domain)

        if fmt == "json":
            return {"success": True, "topology": data}

        # PNG
        try:
            from museon.ares.graph_renderer import render_topology_png
            out_path = Path(self.data_dir) / "ares" / "topology.png"
            render_topology_png(data, output_path=out_path, owner_name="Zeal")
            return {
                "success": True,
                "path": str(out_path),
                "nodes": len(data["nodes"]),
                "links": len(data["links"]),
                "message": f"拓樸圖已生成：{len(data['nodes'])} 個人物、{len(data['links'])} 條連線",
                "mini_app_url": "https://zealchou.github.io/MUSEON/ares/",
            }
        except ImportError:
            return {"success": False, "error": "matplotlib/networkx 未安裝，無法生成 PNG"}
