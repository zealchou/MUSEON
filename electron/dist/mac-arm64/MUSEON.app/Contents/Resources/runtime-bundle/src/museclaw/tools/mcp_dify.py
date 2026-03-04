"""Dify MCP Bridge — MuseClaw 原生 Dify 工作流整合.

透過 Dify REST API 讓 MuseClaw 能自主駕馭 Dify 工作流：
- 列出可用工作流與應用
- 執行工作流（blocking / streaming）
- 查詢執行狀態
- 健康檢查

設計原則：
- MuseClaw 是大腦（思考、診斷、策略），Dify 是手腳（執行、分發、排程）
- 此模組讓 MuseClaw 能自主決定何時調用 Dify 工作流
- 所有 API 呼叫走 Dify REST API，不依賴 Dify 內部實作

環境變數：
- DIFY_BASE_URL: Dify API 基底 URL（預設 http://localhost:5001）
- DIFY_API_KEY: Dify API Key（從 Dify Dashboard 取得）
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════
# 設定
# ═══════════════════════════════════════

DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "http://localhost:5001")
DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")

# ═══════════════════════════════════════
# HTTP 工具（使用 httpx 或 fallback urllib）
# ═══════════════════════════════════════

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

try:
    import aiohttp
    _HAS_AIOHTTP = True
except ImportError:
    _HAS_AIOHTTP = False


def _headers() -> Dict[str, str]:
    """建構 API 請求標頭."""
    return {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }


# ═══════════════════════════════════════
# 同步 API（供 tool_registry 健康檢查用）
# ═══════════════════════════════════════

def check_health() -> Dict[str, Any]:
    """檢查 Dify 服務是否可達.

    Returns:
        {"healthy": bool, "base_url": str, "error": str|None}
    """
    if not DIFY_API_KEY:
        return {
            "healthy": False,
            "base_url": DIFY_BASE_URL,
            "error": "DIFY_API_KEY 未設定",
            "configured": False,
        }

    try:
        if _HAS_HTTPX:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(
                    f"{DIFY_BASE_URL}/v1/parameters",
                    headers=_headers(),
                )
                return {
                    "healthy": resp.status_code in (200, 401, 403),
                    "base_url": DIFY_BASE_URL,
                    "status_code": resp.status_code,
                    "configured": True,
                    "error": None if resp.status_code == 200 else f"HTTP {resp.status_code}",
                }
        else:
            import urllib.request
            req = urllib.request.Request(
                f"{DIFY_BASE_URL}/v1/parameters",
                headers=_headers(),
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return {
                    "healthy": True,
                    "base_url": DIFY_BASE_URL,
                    "status_code": resp.status,
                    "configured": True,
                    "error": None,
                }
    except Exception as e:
        return {
            "healthy": False,
            "base_url": DIFY_BASE_URL,
            "configured": True,
            "error": str(e),
        }


# ═══════════════════════════════════════
# 非同步 API（供 Brain 和 MCP tool 使用）
# ═══════════════════════════════════════

async def execute_workflow(
    workflow_id: str,
    inputs: Dict[str, Any],
    response_mode: str = "blocking",
    user: str = "museclaw",
) -> Dict[str, Any]:
    """執行 Dify 工作流.

    Args:
        workflow_id: 工作流 App 的 API Key（每個 Dify App 有獨立 API Key）
        inputs: 工作流輸入參數
        response_mode: "blocking" 或 "streaming"
        user: 使用者識別碼

    Returns:
        Dify API 回應（含 workflow_run_id, outputs, status 等）
    """
    url = f"{DIFY_BASE_URL}/v1/workflows/run"
    payload = {
        "inputs": inputs,
        "response_mode": response_mode,
        "user": user,
    }
    headers = {
        "Authorization": f"Bearer {workflow_id}",
        "Content-Type": "application/json",
    }

    try:
        if _HAS_AIOHTTP:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    result = await resp.json()
                    logger.info(f"[Dify] Workflow executed: status={result.get('data', {}).get('status', 'unknown')}")
                    return result
        elif _HAS_HTTPX:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                result = resp.json()
                logger.info(f"[Dify] Workflow executed: status={result.get('data', {}).get('status', 'unknown')}")
                return result
        else:
            return {"error": "需要 httpx 或 aiohttp 套件"}
    except Exception as e:
        logger.error(f"[Dify] Workflow execution failed: {e}")
        return {"error": str(e)}


async def get_workflow_status(
    workflow_run_id: str,
    api_key: str = "",
) -> Dict[str, Any]:
    """查詢工作流執行狀態.

    Args:
        workflow_run_id: 工作流執行 ID
        api_key: 工作流 App 的 API Key

    Returns:
        執行狀態（status, outputs, elapsed_time 等）
    """
    url = f"{DIFY_BASE_URL}/v1/workflows/run/{workflow_run_id}"
    key = api_key or DIFY_API_KEY
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    try:
        if _HAS_AIOHTTP:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    return await resp.json()
        elif _HAS_HTTPX:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers=headers)
                return resp.json()
        else:
            return {"error": "需要 httpx 或 aiohttp 套件"}
    except Exception as e:
        logger.error(f"[Dify] Status query failed: {e}")
        return {"error": str(e)}


async def send_chat_message(
    app_api_key: str,
    query: str,
    user: str = "museclaw",
    conversation_id: str = "",
    inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """向 Dify Chat App 發送訊息.

    Args:
        app_api_key: Chat App 的 API Key
        query: 使用者訊息
        user: 使用者識別碼
        conversation_id: 對話 ID（空字串 = 新對話）
        inputs: 額外輸入參數

    Returns:
        Dify Chat API 回應
    """
    url = f"{DIFY_BASE_URL}/v1/chat-messages"
    payload = {
        "inputs": inputs or {},
        "query": query,
        "response_mode": "blocking",
        "user": user,
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id

    headers = {
        "Authorization": f"Bearer {app_api_key}",
        "Content-Type": "application/json",
    }

    try:
        if _HAS_AIOHTTP:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    return await resp.json()
        elif _HAS_HTTPX:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                return resp.json()
        else:
            return {"error": "需要 httpx 或 aiohttp 套件"}
    except Exception as e:
        logger.error(f"[Dify] Chat message failed: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════
# MCP Tool 定義（供 Brain tool_use 使用）
# ═══════════════════════════════════════

DIFY_TOOLS = [
    {
        "name": "dify_execute_workflow",
        "description": (
            "執行 Dify 工作流。MuseClaw 可透過此工具自主調用預建的 Dify 自動化工作流，"
            "例如：排程發布社群內容、自動生成週報、觸發客戶通知、執行 ETL 管線等。"
            "workflow_id 為該工作流 App 的 API Key。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_id": {
                    "type": "string",
                    "description": "Dify 工作流 App 的 API Key",
                },
                "inputs": {
                    "type": "object",
                    "description": "工作流輸入參數（key-value 對應工作流 Start 節點定義的變數）",
                },
            },
            "required": ["workflow_id", "inputs"],
        },
    },
    {
        "name": "dify_get_workflow_status",
        "description": (
            "查詢 Dify 工作流的執行狀態。用於追蹤非同步工作流的進度，"
            "確認工作流是否完成、取得輸出結果。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_run_id": {
                    "type": "string",
                    "description": "工作流執行 ID（從 execute_workflow 回傳）",
                },
                "api_key": {
                    "type": "string",
                    "description": "工作流 App 的 API Key",
                },
            },
            "required": ["workflow_run_id"],
        },
    },
    {
        "name": "dify_chat",
        "description": (
            "向 Dify Chat App 發送訊息。適用於需要對話式互動的 Dify 應用，"
            "例如：客戶支援機器人、RAG 知識問答系統。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "app_api_key": {
                    "type": "string",
                    "description": "Dify Chat App 的 API Key",
                },
                "query": {
                    "type": "string",
                    "description": "發送的訊息內容",
                },
                "conversation_id": {
                    "type": "string",
                    "description": "對話 ID（留空 = 開啟新對話）",
                    "default": "",
                },
            },
            "required": ["app_api_key", "query"],
        },
    },
    {
        "name": "dify_health_check",
        "description": "檢查 Dify 服務的連線狀態與可用性。",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


async def handle_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """處理 Dify MCP tool 呼叫.

    由 Brain 的 tool_use pipeline 調用。

    Args:
        tool_name: 工具名稱（dify_execute_workflow 等）
        arguments: 工具參數

    Returns:
        JSON 字串格式的結果
    """
    if tool_name == "dify_execute_workflow":
        result = await execute_workflow(
            workflow_id=arguments["workflow_id"],
            inputs=arguments.get("inputs", {}),
        )
        return json.dumps(result, ensure_ascii=False)

    elif tool_name == "dify_get_workflow_status":
        result = await get_workflow_status(
            workflow_run_id=arguments["workflow_run_id"],
            api_key=arguments.get("api_key", ""),
        )
        return json.dumps(result, ensure_ascii=False)

    elif tool_name == "dify_chat":
        result = await send_chat_message(
            app_api_key=arguments["app_api_key"],
            query=arguments["query"],
            conversation_id=arguments.get("conversation_id", ""),
        )
        return json.dumps(result, ensure_ascii=False)

    elif tool_name == "dify_health_check":
        result = check_health()
        return json.dumps(result, ensure_ascii=False)

    return json.dumps({"error": f"未知工具: {tool_name}"})
