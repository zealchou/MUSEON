"""MCP Connector SDK — MUSEON 的 MCP 伺服器連線管理、工具發現與調用.

v10.2: 讓 MUSEON 能即時連接外部 MCP 伺服器（GitHub、Google Drive、Notion 等），
動態發現工具並暴露給 Claude 調用。

架構：
  - MCPServerConnection: 單個伺服器連線的資料物件
  - MCPConnectorSDK: 主要管理器（連線/斷線/工具發現/調用）
  - MCP_SERVER_CATALOG: 預設推薦伺服器目錄
  - _CAPABILITY_KEYWORDS: 能力缺口偵測關鍵字

設計原則：
  - Graceful degradation: 若 mcp SDK 未安裝，所有方法回傳錯誤而不崩潰
  - 背景任務模式: 每個連線是一個 asyncio.Task，持有 transport context
  - 動態工具名稱: mcp__{server}__{tool} 格式，自動通過 Whitelist
"""

import asyncio
import json
import logging
import os
import shlex
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════
# MCP SDK 可用性檢查（graceful degradation）
# ═══════════════════════════════════════
_MCP_AVAILABLE = False
try:
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.types import CallToolResult, Tool

    _MCP_AVAILABLE = True
except ImportError:
    logger.info("mcp package not installed — MCP Connector SDK disabled")


# ═══════════════════════════════════════
# 預設伺服器目錄（推薦但不預裝）
# ═══════════════════════════════════════
MCP_SERVER_CATALOG: List[Dict[str, Any]] = [
    # ═══ 🔍 搜尋與研究 ═══
    {
        "name": "brave-search",
        "display_name": "Brave Search",
        "description": "透過 Brave Search API 進行網頁搜尋",
        "category": "search",
        "icon": "\U0001f981",
        "transport": "stdio",
        "command": "npx -y @modelcontextprotocol/server-brave-search",
        "auth_required": True,
        "auth_env": ["BRAVE_API_KEY"],
        "auth_guide": "在 Brave Search API 頁面取得免費 API Key",
        "auth_url": "https://brave.com/search/api/",
    },
    {
        "name": "fetch",
        "display_name": "Fetch",
        "description": "抓取任何網頁內容並轉為 Markdown",
        "category": "search",
        "icon": "\U0001f310",
        "transport": "stdio",
        "command": "uvx mcp-server-fetch",
        "auth_required": False,
        "auth_env": [],
        "auth_guide": "",
        "auth_url": "",
    },
    {
        "name": "exa",
        "display_name": "Exa Search",
        "description": "AI 語意搜尋引擎，可深度搜尋網頁內容",
        "category": "search",
        "icon": "\U0001f52c",
        "transport": "stdio",
        "command": "npx -y exa-mcp-server",
        "auth_required": True,
        "auth_env": ["EXA_API_KEY"],
        "auth_guide": "在 Exa 開發者頁面取得 API Key",
        "auth_url": "https://exa.ai/api",
    },
    {
        "name": "perplexity",
        "display_name": "Perplexity",
        "description": "透過 Perplexity AI 進行即時深度研究",
        "category": "search",
        "icon": "\U0001f9e0",
        "transport": "stdio",
        "command": "npx -y @anthropic/mcp-server-perplexity-ask",
        "auth_required": True,
        "auth_env": ["PERPLEXITY_API_KEY"],
        "auth_guide": "在 Perplexity 開發者頁面取得 API Key",
        "auth_url": "https://docs.perplexity.ai/",
    },
    # ═══ 📋 生產力工具 ═══
    {
        "name": "notion",
        "display_name": "Notion",
        "description": "搜尋與管理 Notion 頁面和資料庫",
        "category": "productivity",
        "icon": "\U0001f4dd",
        "transport": "stdio",
        "command": "npx -y @notionhq/notion-mcp-server",
        "auth_required": True,
        "auth_env": ["OPENAPI_MCP_HEADERS"],
        "auth_guide": "在 Notion Integrations 建立 internal integration，取得 API Key",
        "auth_url": "https://www.notion.so/my-integrations",
    },
    {
        "name": "todoist",
        "display_name": "Todoist",
        "description": "管理待辦事項、專案、標籤",
        "category": "productivity",
        "icon": "\u2705",
        "transport": "stdio",
        "command": "npx -y @anthropic/mcp-server-todoist",
        "auth_required": True,
        "auth_env": ["TODOIST_API_TOKEN"],
        "auth_guide": "在 Todoist 設定 > 整合 > 開發者 取得 API Token",
        "auth_url": "https://todoist.com/app/settings/integrations/developer",
    },
    {
        "name": "google-drive",
        "display_name": "Google Drive",
        "description": "搜尋、讀取、管理 Google Drive 檔案",
        "category": "productivity",
        "icon": "\U0001f4c1",
        "transport": "stdio",
        "command": "npx -y @anthropic/mcp-server-gdrive",
        "auth_required": True,
        "auth_env": ["GOOGLE_APPLICATION_CREDENTIALS"],
        "auth_guide": "在 Google Cloud Console 設定 OAuth2 憑證",
        "auth_url": "https://console.cloud.google.com/",
    },
    {
        "name": "linear",
        "display_name": "Linear",
        "description": "管理 Linear Issue、專案、Sprint",
        "category": "productivity",
        "icon": "\U0001f4d0",
        "transport": "sse",
        "command": "https://mcp.linear.app/sse",
        "auth_required": True,
        "auth_env": ["LINEAR_API_KEY"],
        "auth_guide": "在 Linear Settings > API 建立 Personal API Key",
        "auth_url": "https://linear.app/settings/api",
    },
    {
        "name": "sequential-thinking",
        "display_name": "Sequential Thinking",
        "description": "引導 AI 進行結構化逐步推理",
        "category": "productivity",
        "icon": "\U0001f9e9",
        "transport": "stdio",
        "command": "npx -y @modelcontextprotocol/server-sequential-thinking",
        "auth_required": False,
        "auth_env": [],
        "auth_guide": "",
        "auth_url": "",
    },
    # ═══ 💻 開發工具 ═══
    {
        "name": "github",
        "display_name": "GitHub",
        "description": "管理 repo、issue、PR、branch、code search",
        "category": "development",
        "icon": "\U0001f419",
        "transport": "stdio",
        "command": "npx -y @modelcontextprotocol/server-github",
        "auth_required": True,
        "auth_env": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
        "auth_guide": "在 GitHub Settings > Developer settings > Tokens 建立 Token",
        "auth_url": "https://github.com/settings/tokens",
    },
    {
        "name": "filesystem",
        "display_name": "Filesystem",
        "description": "安全讀寫本地檔案、搜尋目錄",
        "category": "development",
        "icon": "\U0001f4c2",
        "transport": "stdio",
        "command": "npx -y @modelcontextprotocol/server-filesystem /Users/ZEALCHOU/MUSEON/data /Users/ZEALCHOU/Downloads /tmp",
        "auth_required": False,
        "auth_env": [],
        "auth_guide": "",
        "auth_url": "",
    },
    {
        "name": "git",
        "display_name": "Git",
        "description": "讀取 Git 歷史、diff、branch、log",
        "category": "development",
        "icon": "\U0001f500",
        "transport": "stdio",
        "command": "uvx mcp-server-git",
        "auth_required": False,
        "auth_env": [],
        "auth_guide": "",
        "auth_url": "",
    },
    {
        "name": "context7",
        "display_name": "Context7",
        "description": "即時查詢任何開源函式庫的最新文件",
        "category": "development",
        "icon": "\U0001f4da",
        "transport": "stdio",
        "command": "npx -y @upstash/context7-mcp@latest",
        "auth_required": False,
        "auth_env": [],
        "auth_guide": "",
        "auth_url": "",
    },
    {
        "name": "sentry",
        "display_name": "Sentry",
        "description": "查詢 Sentry 錯誤報告和效能資料",
        "category": "development",
        "icon": "\U0001f41b",
        "transport": "stdio",
        "command": "npx -y @sentry/mcp-server",
        "auth_required": True,
        "auth_env": ["SENTRY_AUTH_TOKEN"],
        "auth_guide": "在 Sentry Settings > Auth Tokens 建立 Token",
        "auth_url": "https://sentry.io/settings/auth-tokens/",
    },
    # ═══ 💬 溝通與社群 ═══
    {
        "name": "slack",
        "display_name": "Slack",
        "description": "讀取/發送訊息、管理頻道",
        "category": "communication",
        "icon": "\U0001f4ac",
        "transport": "stdio",
        "command": "npx -y @modelcontextprotocol/server-slack",
        "auth_required": True,
        "auth_env": ["SLACK_BOT_TOKEN"],
        "auth_guide": "在 Slack API 頁面建立 Slack Bot，取得 Bot Token",
        "auth_url": "https://api.slack.com/apps",
    },
    {
        "name": "discord",
        "display_name": "Discord",
        "description": "管理 Discord 伺服器、頻道、訊息",
        "category": "communication",
        "icon": "\U0001f3ae",
        "transport": "stdio",
        "command": "npx -y @anthropic/mcp-server-discord",
        "auth_required": True,
        "auth_env": ["DISCORD_BOT_TOKEN"],
        "auth_guide": "在 Discord Developer Portal 建立 Bot，取得 Token",
        "auth_url": "https://discord.com/developers/applications",
    },
    # ═══ 🗃️ 資料庫 ═══
    {
        "name": "postgres",
        "display_name": "PostgreSQL",
        "description": "連線並查詢 PostgreSQL 資料庫",
        "category": "database",
        "icon": "\U0001f418",
        "transport": "stdio",
        "command": "npx -y @modelcontextprotocol/server-postgres",
        "auth_required": True,
        "auth_env": ["POSTGRES_CONNECTION_STRING"],
        "auth_guide": "提供 PostgreSQL 連線字串，格式：postgresql://user:pass@host:5432/db",
        "auth_url": "",
    },
    # ═══ 🔄 工作流自動化 ═══
    {
        "name": "dify",
        "display_name": "Dify 工作流引擎",
        "description": "MuseClaw 的手腳 — 透過 Dify REST API 自主執行工作流、排程任務、跨系統整合",
        "category": "automation",
        "icon": "\U0001f916",
        "transport": "native",
        "command": "",
        "auth_required": True,
        "auth_env": ["DIFY_API_KEY", "DIFY_BASE_URL"],
        "auth_guide": "自架 Dify（docker compose up -d），從 Dify Dashboard → Settings → API Key 取得",
        "auth_url": "https://docs.dify.ai/",
        "native_module": "museclaw.tools.mcp_dify",
    },
]

# 能力缺口偵測關鍵字
_CAPABILITY_KEYWORDS: Dict[str, List[str]] = {
    "brave-search": ["brave", "search api", "網頁搜尋"],
    "fetch": ["fetch", "crawl", "scrape", "抓取", "爬蟲", "網頁內容"],
    "exa": ["exa", "semantic search", "語意搜尋"],
    "perplexity": ["perplexity", "研究", "research"],
    "notion": ["notion", "workspace", "筆記"],
    "todoist": ["todoist", "待辦", "todo", "to-do"],
    "google-drive": ["google drive", "gdrive", "docs", "spreadsheet", "共享", "雲端硬碟"],
    "linear": ["linear", "issue tracking", "sprint"],
    "sequential-thinking": ["step by step", "逐步", "推理", "reasoning"],
    "github": ["github", "repo", "pr", "pull request", "issue", "commit", "branch"],
    "filesystem": ["file system", "directory", "folder", "檔案系統"],
    "git": ["git log", "git diff", "git history", "版本控制"],
    "context7": ["documentation", "library docs", "函式庫文件"],
    "sentry": ["sentry", "error tracking", "bug report", "錯誤追蹤"],
    "slack": ["slack", "channel", "dm", "頻道"],
    "discord": ["discord", "伺服器", "server chat"],
    "postgres": ["postgres", "postgresql", "pg"],
    "dify": ["dify", "workflow", "工作流", "自動化", "排程", "automation", "pipeline"],
}


# ═══════════════════════════════════════
# 資料類
# ═══════════════════════════════════════
@dataclass
class MCPServerConnection:
    """單個 MCP 伺服器連線的狀態與元資料."""

    name: str
    config: Dict[str, Any]
    status: str = "disconnected"  # connecting | connected | error | disconnected
    session: Optional[Any] = None  # ClientSession
    tools: List[Dict[str, Any]] = field(default_factory=list)
    error_message: str = ""
    connected_at: Optional[str] = None
    _task: Optional[asyncio.Task] = None
    _tool_name_map: Dict[str, str] = field(default_factory=dict)  # sanitized→original
    _ready_event: Optional[asyncio.Event] = field(default=None, repr=False)


# ═══════════════════════════════════════
# MCP Connector SDK
# ═══════════════════════════════════════
class MCPConnectorSDK:
    """MUSEON 的 MCP 伺服器連線管理器.

    管理 MCP 伺服器的完整生命週期：
      - 連線/斷線
      - 工具發現與格式轉換
      - 工具調用代理
      - 預設伺服器目錄
      - 能力缺口偵測
    """

    def __init__(self, data_dir: str):
        """初始化 MCP Connector SDK.

        Args:
            data_dir: 資料目錄（包含 _system/mcp/servers.json）
        """
        self._data_dir = Path(data_dir)
        self._mcp_config_dir = self._data_dir / "_system" / "mcp"
        self._mcp_config_dir.mkdir(parents=True, exist_ok=True)
        self._servers_file = self._mcp_config_dir / "servers.json"
        self._connections: Dict[str, MCPServerConnection] = {}
        self._lock = asyncio.Lock()

        if _MCP_AVAILABLE:
            logger.info("MCPConnectorSDK initialized (mcp SDK available)")
        else:
            logger.warning("MCPConnectorSDK initialized (mcp SDK NOT available — degraded mode)")

    # ── 連線管理 ──

    async def connect_server(
        self, name: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """連線到單個 MCP 伺服器.

        Args:
            name: 伺服器名稱
            config: 配置（transport, command, env 等）

        Returns:
            {"success": bool, ...}
        """
        if not _MCP_AVAILABLE:
            return {
                "success": False,
                "error": "MCP SDK 未安裝。請執行: pip install mcp",
            }

        transport = config.get("transport", "stdio")
        command = config.get("command", "")

        if not command and transport == "stdio":
            return {"success": False, "error": f"伺服器 '{name}' 缺少 command 配置"}

        async with self._lock:
            # 已連線 → 回傳現狀
            if name in self._connections:
                conn = self._connections[name]
                if conn.status == "connected":
                    return {
                        "success": True,
                        "message": f"伺服器 '{name}' 已連線",
                        "tools_count": len(conn.tools),
                        "tools": [t["name"] for t in conn.tools],
                    }
                # 之前失敗 → 清除舊連線
                if conn._task and not conn._task.done():
                    conn._task.cancel()
                    try:
                        await conn._task
                    except (asyncio.CancelledError, Exception):
                        pass

            # 建立連線物件
            ready_event = asyncio.Event()
            conn = MCPServerConnection(
                name=name,
                config=config,
                status="connecting",
                _ready_event=ready_event,
            )
            self._connections[name] = conn

            # 啟動背景連線任務
            task = asyncio.create_task(
                self._run_server_connection(name, config),
                name=f"mcp-{name}",
            )
            conn._task = task

        # 等待連線完成（最多 30 秒）
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            conn.status = "error"
            conn.error_message = "連線超時（30 秒）"
            logger.warning(f"MCP server '{name}' connection timeout")
            return {
                "success": False,
                "error": f"伺服器 '{name}' 連線超時",
            }

        # 檢查連線結果
        if conn.status == "connected":
            logger.info(
                f"MCP server '{name}' connected: {len(conn.tools)} tools"
            )
            return {
                "success": True,
                "message": f"伺服器 '{name}' 已連線",
                "tools_count": len(conn.tools),
                "tools": [t["name"] for t in conn.tools],
            }
        else:
            return {
                "success": False,
                "error": f"伺服器 '{name}' 連線失敗: {conn.error_message}",
            }

    async def _run_server_connection(
        self, name: str, config: Dict[str, Any]
    ) -> None:
        """背景任務：持有 transport context 直到取消.

        這是一個長期執行的 coroutine，透過 asyncio context manager
        持有 MCP 伺服器連線。取消此任務即斷線。
        """
        conn = self._connections.get(name)
        if not conn:
            return

        transport = config.get("transport", "stdio")
        command = config.get("command", "")
        env = config.get("env", {})

        try:
            if transport == "stdio":
                await self._run_stdio_connection(name, conn, command, env)
            elif transport == "sse":
                await self._run_sse_connection(name, conn, config)
            elif transport == "streamable_http":
                await self._run_http_connection(name, conn, config)
            else:
                conn.status = "error"
                conn.error_message = f"不支援的 transport: {transport}"
                if conn._ready_event:
                    conn._ready_event.set()

        except asyncio.CancelledError:
            logger.info(f"MCP server '{name}' connection cancelled (shutdown)")
            conn.status = "disconnected"
        except Exception as e:
            logger.error(f"MCP server '{name}' connection error: {e}")
            conn.status = "error"
            conn.error_message = str(e)[:500]
            if conn._ready_event:
                conn._ready_event.set()

    @staticmethod
    def _build_subprocess_env(extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """建構 subprocess 環境變數，確保 PATH 包含 node/npx/uvx 等常見路徑.

        解決 launchd daemon 環境 PATH 過於精簡的問題。
        """
        merged = {**os.environ}
        if extra_env:
            merged.update(extra_env)

        # 常見的可執行檔路徑（node, npx, uvx, pipx 等）
        extra_paths = [
            # Homebrew Node.js（各版本）
            "/opt/homebrew/opt/node@22/bin",
            "/opt/homebrew/opt/node@20/bin",
            "/opt/homebrew/opt/node@18/bin",
            "/opt/homebrew/opt/node/bin",
            # Homebrew 通用
            "/opt/homebrew/bin",
            "/opt/homebrew/sbin",
            # macOS Intel Homebrew
            "/usr/local/opt/node@22/bin",
            "/usr/local/opt/node@20/bin",
            "/usr/local/opt/node/bin",
            "/usr/local/bin",
            # Python / uvx / pipx
            os.path.expanduser("~/.local/bin"),
            "/opt/homebrew/opt/python@3/bin",
            # nvm（掃描最新版本目錄）
            # volta
            os.path.expanduser("~/.volta/bin"),
            # 基礎
            "/usr/bin",
            "/bin",
        ]

        # 嘗試找到 nvm 的最新版本目錄
        nvm_dir = os.path.expanduser("~/.nvm/versions/node")
        if os.path.isdir(nvm_dir):
            try:
                versions = sorted(os.listdir(nvm_dir), reverse=True)
                if versions:
                    extra_paths.insert(0, os.path.join(nvm_dir, versions[0], "bin"))
            except OSError:
                pass

        existing_path = merged.get("PATH", "")
        for p in extra_paths:
            if os.path.isdir(p) and p not in existing_path:
                existing_path = p + ":" + existing_path
        merged["PATH"] = existing_path
        return merged

    async def _run_stdio_connection(
        self,
        name: str,
        conn: MCPServerConnection,
        command: str,
        env: Dict[str, str],
    ) -> None:
        """stdio transport 連線."""
        parts = shlex.split(command)
        if not parts:
            conn.status = "error"
            conn.error_message = "command 為空"
            if conn._ready_event:
                conn._ready_event.set()
            return

        # 合併環境變數（含 PATH 修復）
        merged_env = self._build_subprocess_env(env)

        server_params = StdioServerParameters(
            command=parts[0],
            args=parts[1:] if len(parts) > 1 else [],
            env=merged_env,
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # 發現工具
                tools_result = await session.list_tools()
                conn.session = session
                conn.tools = self._convert_mcp_tools(name, tools_result.tools)
                conn.status = "connected"
                conn.connected_at = datetime.now().isoformat()

                logger.info(
                    f"MCP '{name}' connected via stdio: "
                    f"{len(conn.tools)} tools discovered"
                )

                # 通知等待者
                if conn._ready_event:
                    conn._ready_event.set()

                # 持有連線直到被取消
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    pass

    async def _run_sse_connection(
        self,
        name: str,
        conn: MCPServerConnection,
        config: Dict[str, Any],
    ) -> None:
        """SSE transport 連線."""
        try:
            from mcp.client.sse import sse_client
        except ImportError:
            conn.status = "error"
            conn.error_message = "sse_client 不可用"
            if conn._ready_event:
                conn._ready_event.set()
            return

        url = config.get("url", config.get("command", ""))
        if not url:
            conn.status = "error"
            conn.error_message = "SSE transport 需要 url 配置"
            if conn._ready_event:
                conn._ready_event.set()
            return

        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                conn.session = session
                conn.tools = self._convert_mcp_tools(name, tools_result.tools)
                conn.status = "connected"
                conn.connected_at = datetime.now().isoformat()

                logger.info(
                    f"MCP '{name}' connected via SSE: "
                    f"{len(conn.tools)} tools discovered"
                )

                if conn._ready_event:
                    conn._ready_event.set()

                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    pass

    async def _run_http_connection(
        self,
        name: str,
        conn: MCPServerConnection,
        config: Dict[str, Any],
    ) -> None:
        """Streamable HTTP transport 連線."""
        try:
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError:
            conn.status = "error"
            conn.error_message = "streamablehttp_client 不可用"
            if conn._ready_event:
                conn._ready_event.set()
            return

        url = config.get("url", config.get("command", ""))
        if not url:
            conn.status = "error"
            conn.error_message = "HTTP transport 需要 url 配置"
            if conn._ready_event:
                conn._ready_event.set()
            return

        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                conn.session = session
                conn.tools = self._convert_mcp_tools(name, tools_result.tools)
                conn.status = "connected"
                conn.connected_at = datetime.now().isoformat()

                logger.info(
                    f"MCP '{name}' connected via HTTP: "
                    f"{len(conn.tools)} tools discovered"
                )

                if conn._ready_event:
                    conn._ready_event.set()

                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    pass

    async def disconnect_server(self, name: str) -> Dict[str, Any]:
        """斷開指定伺服器連線."""
        async with self._lock:
            conn = self._connections.pop(name, None)
            if not conn:
                return {"success": True, "message": f"伺服器 '{name}' 不在連線清單中"}

            if conn._task and not conn._task.done():
                conn._task.cancel()
                try:
                    await conn._task
                except (asyncio.CancelledError, Exception):
                    pass

            logger.info(f"MCP server '{name}' disconnected")
            return {"success": True, "message": f"伺服器 '{name}' 已斷線"}

    async def connect_all_configured(self) -> Dict[str, Any]:
        """連線所有 servers.json 中配置的伺服器.

        Returns:
            {"connected": int, "failed": int, "details": [...]}
        """
        if not self._servers_file.exists():
            return {"connected": 0, "failed": 0, "details": []}

        try:
            servers = json.loads(self._servers_file.read_text("utf-8"))
        except Exception as e:
            logger.warning(f"Failed to read servers.json: {e}")
            return {"connected": 0, "failed": 0, "error": str(e)}

        if not servers:
            return {"connected": 0, "failed": 0, "details": []}

        connected = 0
        failed = 0
        details = []

        for name, config in servers.items():
            result = await self.connect_server(name, config)
            if result.get("success"):
                connected += 1
            else:
                failed += 1
            details.append({"name": name, **result})

        return {"connected": connected, "failed": failed, "details": details}

    async def shutdown_all(self) -> None:
        """斷開所有連線（gateway 關閉時呼叫）."""
        names = list(self._connections.keys())
        for name in names:
            await self.disconnect_server(name)
        logger.info(f"MCP shutdown: {len(names)} servers disconnected")

    # ── 工具發現 ──

    def _convert_mcp_tools(
        self, server_name: str, mcp_tools: list
    ) -> List[Dict[str, Any]]:
        """將 MCP Tool 物件轉換為 Anthropic tool_use 格式.

        命名慣例：mcp__{server}__{tool}
        """
        converted = []
        safe_server = self._sanitize_name(server_name)

        for tool in mcp_tools:
            safe_tool = self._sanitize_name(tool.name)
            anthropic_name = f"mcp__{safe_server}__{safe_tool}"

            # 建立 input_schema
            input_schema = getattr(tool, "inputSchema", None)
            if not input_schema:
                input_schema = {"type": "object", "properties": {}}

            anthropic_tool = {
                "name": anthropic_name,
                "description": (
                    f"[MCP: {server_name}] "
                    f"{tool.description or tool.name}"
                ),
                "input_schema": input_schema,
            }
            converted.append(anthropic_tool)

            # 儲存反轉映射
            conn = self._connections.get(server_name)
            if conn:
                conn._tool_name_map[anthropic_name] = tool.name

        return converted

    def list_tools(self) -> List[Dict[str, Any]]:
        """聚合所有已連線伺服器的工具定義.

        Returns:
            Anthropic tool_use 格式的工具列表
        """
        all_tools = []
        for conn in self._connections.values():
            if conn.status == "connected":
                all_tools.extend(conn.tools)
        return all_tools

    # ── 工具調用 ──

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """調用已連線伺服器上的工具.

        Args:
            server_name: 伺服器名稱（sanitized 或 original）
            tool_name: 工具名稱（sanitized 或 original）
            arguments: 工具參數

        Returns:
            {"success": bool, "result": ...} 或 {"success": False, "error": ...}
        """
        if not _MCP_AVAILABLE:
            return {"success": False, "error": "MCP SDK 未安裝"}

        # 查找連線（嘗試 original name 和 sanitized name）
        conn = self._connections.get(server_name)
        if not conn:
            # 嘗試反向查找（sanitized → original）
            for name, c in self._connections.items():
                if self._sanitize_name(name) == server_name:
                    conn = c
                    break

        if not conn:
            return {
                "success": False,
                "error": f"伺服器 '{server_name}' 未連線",
                "hint": "請先使用 mcp_add_server 配置並連線伺服器",
            }

        if conn.status != "connected" or not conn.session:
            return {
                "success": False,
                "error": (
                    f"伺服器 '{server_name}' 狀態: {conn.status}"
                    f"{' — ' + conn.error_message if conn.error_message else ''}"
                ),
            }

        # 還原原始工具名稱
        # 傳入的可能是 sanitized name（從 mcp__{server}__{tool} 拆解出來的）
        original_tool = tool_name
        # 先查找完整的 anthropic name 映射
        for ant_name, orig_name in conn._tool_name_map.items():
            if ant_name.endswith(f"__{tool_name}") or orig_name == tool_name:
                original_tool = orig_name
                break

        try:
            result = await asyncio.wait_for(
                conn.session.call_tool(original_tool, arguments or {}),
                timeout=60.0,
            )

            # 轉換 CallToolResult
            if result.isError:
                error_text = ""
                for content in result.content:
                    if hasattr(content, "text"):
                        error_text += content.text
                return {"success": False, "error": error_text or "MCP 工具執行錯誤"}

            # 提取結果
            result_parts = []
            for content in result.content:
                if hasattr(content, "text"):
                    result_parts.append(content.text)
                elif hasattr(content, "data"):
                    result_parts.append(f"[binary data: {content.mimeType}]")

            return {
                "success": True,
                "result": "\n".join(result_parts) if result_parts else "完成",
            }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"MCP 工具 '{tool_name}' 執行超時（60 秒）",
            }
        except Exception as e:
            logger.error(f"MCP call_tool error: {server_name}/{tool_name}: {e}")
            # 連線可能已斷開
            conn.status = "error"
            conn.error_message = f"呼叫失敗: {str(e)[:200]}"
            return {
                "success": False,
                "error": f"MCP 工具執行失敗: {str(e)[:200]}",
                "hint": "伺服器連線可能已中斷，建議重新連線",
            }

    # ── 目錄與能力缺口 ──

    def get_catalog(self) -> List[Dict[str, Any]]:
        """回傳預設推薦伺服器目錄.

        已連線的伺服器會標記 connected=True。
        """
        result = []
        connected_names = {
            name for name, conn in self._connections.items()
            if conn.status == "connected"
        }
        for entry in MCP_SERVER_CATALOG:
            item = dict(entry)
            item["connected"] = entry["name"] in connected_names
            result.append(item)
        return result

    def detect_capability_gap(
        self, user_intent: str
    ) -> Optional[Dict[str, Any]]:
        """偵測使用者意圖是否匹配未連線的 MCP 伺服器能力.

        Args:
            user_intent: 使用者訊息（原始文字）

        Returns:
            匹配的 catalog 項目 + 建議訊息，或 None
        """
        intent_lower = user_intent.lower()
        connected_names = {
            name for name, conn in self._connections.items()
            if conn.status == "connected"
        }

        for server_name, keywords in _CAPABILITY_KEYWORDS.items():
            # 跳過已連線的
            if server_name in connected_names:
                continue

            matched = [kw for kw in keywords if kw in intent_lower]
            if matched:
                # 找到 catalog 項目
                catalog_entry = next(
                    (e for e in MCP_SERVER_CATALOG if e["name"] == server_name),
                    None,
                )
                if catalog_entry:
                    return {
                        "suggested_server": catalog_entry,
                        "matched_keywords": matched,
                        "message": (
                            f"需要連接 MCP 伺服器 "
                            f"'{catalog_entry['display_name']}' "
                            f"才能使用此功能。"
                            f"{'需要設定 ' + ', '.join(catalog_entry.get('auth_env', [])) if catalog_entry.get('auth_required') else '無需認證，可直接連線。'}"
                        ),
                    }

        return None

    # ── 狀態查詢 ──

    def get_status(self) -> Dict[str, Any]:
        """回傳 MCP 連線器的整體狀態."""
        connections = {}
        for name, conn in self._connections.items():
            connections[name] = {
                "status": conn.status,
                "tools_count": len(conn.tools),
                "error": conn.error_message if conn.error_message else None,
                "connected_at": conn.connected_at,
            }

        return {
            "mcp_sdk_available": _MCP_AVAILABLE,
            "connections": connections,
            "total_connected": sum(
                1 for c in self._connections.values()
                if c.status == "connected"
            ),
            "total_tools": sum(
                len(c.tools)
                for c in self._connections.values()
                if c.status == "connected"
            ),
            "catalog_count": len(MCP_SERVER_CATALOG),
        }

    # ── 工具 ──

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """將名稱中的 - . 空格 替換為 _（Anthropic tool name 限制）."""
        return name.replace("-", "_").replace(".", "_").replace(" ", "_")
