"""LLM Adapters — claude -p (MAX) 主要呼叫層 + API fallback.

v1: ClaudeCLIAdapter (subprocess claude -p) + AnthropicAPIAdapter (AsyncAnthropic).
Brain 透過統一的 AdapterResponse 格式使用，無需關心底層實現。
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# API 相容性包裝器（讓 brain.py tool-use 迴圈無需修改）
# ═══════════════════════════════════════════

class _TextBlock:
    """模擬 Anthropic API 的 TextBlock."""
    def __init__(self, text: str):
        self.type = "text"
        self.text = text

    def model_dump(self):
        return {"type": "text", "text": self.text}


class _ToolUseBlock:
    """模擬 Anthropic API 的 ToolUseBlock."""
    def __init__(self, id: str, name: str, input: Dict[str, Any]):
        self.type = "tool_use"
        self.id = id
        self.name = name
        self.input = input

    def model_dump(self):
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}


class _Usage:
    """模擬 Anthropic API 的 Usage."""
    def __init__(self, input_tokens: int, output_tokens: int):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0


class APICompatResponse:
    """將 AdapterResponse 包裝成 Anthropic API 相容格式.

    讓 brain.py 的 tool-use 迴圈幾乎不需修改。
    """
    def __init__(self, adapter_resp: "AdapterResponse"):
        self.stop_reason = adapter_resp.stop_reason
        self.content = []
        if adapter_resp.text:
            self.content.append(_TextBlock(adapter_resp.text))
        for tc in adapter_resp.tool_calls:
            self.content.append(_ToolUseBlock(tc.id, tc.name, tc.input))
        self.usage = _Usage(adapter_resp.input_tokens, adapter_resp.output_tokens)
        self._adapter_resp = adapter_resp

    def model_dump(self):
        return {"stop_reason": self.stop_reason}


# ═══════════════════════════════════════════
# 統一回應格式
# ═══════════════════════════════════════════

@dataclass
class ToolCall:
    """Tool-use 請求."""
    id: str
    name: str
    input: Dict[str, Any]


@dataclass
class AdapterResponse:
    """LLM 回應的統一格式."""
    text: str = ""
    stop_reason: Optional[str] = None  # "end_turn" | "tool_use" | "max_tokens"
    tool_calls: List[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    session_id: Optional[str] = None  # claude -p 的 session ID
    raw: Optional[Dict[str, Any]] = None  # 原始回應


# ═══════════════════════════════════════════
# Adapter Protocol
# ═══════════════════════════════════════════

@runtime_checkable
class LLMAdapter(Protocol):
    """LLM 呼叫的統一介面."""

    async def call(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        model: str = "sonnet",
        max_tokens: int = 8192,
        tools: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
    ) -> AdapterResponse:
        """發送 LLM 請求並返回統一格式回應."""
        ...

    async def close(self) -> None:
        """清理資源."""
        ...


# ═══════════════════════════════════════════
# ClaudeCLIAdapter — 主要（MAX 訂閱方案）
# ═══════════════════════════════════════════

class ClaudeCLIAdapter:
    """透過 claude -p (headless mode) 呼叫 Claude Code MAX.

    這是合法的 Claude Code CLI 使用方式，不會被封鎖。
    每次呼叫啟動一個 subprocess，透過 --output-format json 取得結構化回應。

    認證機制（優先順序）：
    1. 環境變數 CLAUDE_CODE_OAUTH_TOKEN（Claude Desktop 注入）
    2. 持久化 token 文件 ~/.museon/oauth_token（daemon 使用）
    """

    # 模型名稱映射
    MODEL_MAP = {
        "opus": "opus",
        "haiku": "haiku",
        "sonnet": "sonnet",
        "claude-opus-4-6": "opus",
        "claude-sonnet-4-20250514": "sonnet",
        "claude-haiku-4-5-20251001": "haiku",
        # 舊版 fallback
        "claude-3-5-haiku-20241022": "haiku",
        "claude-3-5-sonnet-20241022": "sonnet",
    }

    # OAuth token 持久化路徑
    _TOKEN_FILE = Path.home() / ".museon" / "oauth_token"

    def __init__(self, claude_path: Optional[str] = None):
        self._claude_path = claude_path or "claude"
        self._call_count = 0
        self._total_duration_ms = 0

    def _get_oauth_token(self) -> Optional[str]:
        """取得 OAuth token（環境變數 > 持久化文件）."""
        # 1. 環境變數（Claude Desktop 注入）
        token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if token:
            self._save_token(token)
            return token
        # 2. 持久化文件（launchd daemon 使用）
        if self._TOKEN_FILE.exists():
            try:
                saved = self._TOKEN_FILE.read_text(encoding="utf-8").strip()
                if saved:
                    logger.debug("Using persisted OAuth token from %s", self._TOKEN_FILE)
                    return saved
            except Exception as e:
                logger.debug(f"[ADAPTERS] token failed (degraded): {e}")
        return None

    def _save_token(self, token: str) -> None:
        """將 OAuth token 持久化到文件."""
        try:
            self._TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            self._TOKEN_FILE.write_text(token, encoding="utf-8")
            self._TOKEN_FILE.chmod(0o600)
        except Exception as e:
            logger.debug("Failed to persist OAuth token: %s", e)

    def _map_model(self, model: str) -> str:
        """將各種模型 ID 映射到 claude -p 接受的名稱."""
        return self.MODEL_MAP.get(model, "sonnet")

    def _build_prompt(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """將 system prompt + messages 組裝成 claude -p 的輸入文字.

        claude -p 會自動從 CLAUDE.md 載入系統層指令，
        所以我們把 system_prompt 放在訊息開頭作為額外指引。
        """
        parts = []

        # System prompt 作為指引前綴
        if system_prompt:
            parts.append(f"<system-instructions>\n{system_prompt}\n</system-instructions>\n")

        # Tool definitions（嵌入 prompt 讓 Claude 知道有哪些工具可用）
        if tools:
            tool_desc = self._format_tools_for_prompt(tools)
            parts.append(f"<available-tools>\n{tool_desc}\n</available-tools>\n")
            parts.append(
                "如果你需要使用工具，請用以下 JSON 格式回覆（不要加任何其他文字）：\n"
                '{"tool_calls": [{"name": "工具名稱", "input": {參數}}]}\n'
                "如果不需要使用工具，直接用自然語言回覆。\n"
            )

        # Messages
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, str):
                if role == "user":
                    parts.append(content)
                elif role == "assistant":
                    parts.append(f"[Previous assistant response]: {content}")
            elif isinstance(content, list):
                # 處理結構化 content（tool_result 等）
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            parts.append(item.get("text", ""))
                        elif item.get("type") == "tool_result":
                            parts.append(
                                f"[Tool result for {item.get('tool_use_id', '?')}]: "
                                f"{item.get('content', '')}"
                            )

        return "\n\n".join(parts)

    def _format_tools_for_prompt(self, tools: List[Dict[str, Any]]) -> str:
        """將工具定義格式化為可讀描述."""
        lines = []
        for tool in tools:
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")
            params = tool.get("input_schema", {}).get("properties", {})
            param_str = ", ".join(
                f"{k}: {v.get('type', 'any')}"
                for k, v in params.items()
            )
            lines.append(f"- {name}({param_str}): {desc[:100]}")
        return "\n".join(lines)

    def _parse_tool_calls(self, text: str) -> List[ToolCall]:
        """嘗試從回應文字中解析 tool_calls JSON."""
        text = text.strip()
        # 嘗試整段解析
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "tool_calls" in data:
                calls = []
                for i, tc in enumerate(data["tool_calls"]):
                    calls.append(ToolCall(
                        id=f"cli_tool_{i}_{int(time.time())}",
                        name=tc.get("name", ""),
                        input=tc.get("input", {}),
                    ))
                return calls
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"[ADAPTERS] tool failed (degraded): {e}")

        # 嘗試在文字中找到 JSON 區塊
        import re
        json_match = re.search(r'\{[^{}]*"tool_calls"\s*:\s*\[.*?\]\s*\}', text, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                calls = []
                for i, tc in enumerate(data.get("tool_calls", [])):
                    calls.append(ToolCall(
                        id=f"cli_tool_{i}_{int(time.time())}",
                        name=tc.get("name", ""),
                        input=tc.get("input", {}),
                    ))
                return calls
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"[ADAPTERS] tool failed (degraded): {e}")

        return []

    async def call(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        model: str = "sonnet",
        max_tokens: int = 8192,
        tools: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
    ) -> AdapterResponse:
        """透過 claude -p subprocess 呼叫 LLM.

        Args:
            system_prompt: 系統提示詞
            messages: 對話訊息列表
            model: 模型名稱（會自動映射）
            max_tokens: 最大回覆 token（claude -p 自動管理，此參數供參考）
            tools: 工具定義列表（嵌入 prompt）
            session_id: 前次 session ID（用於 --resume 繼續對話）

        Returns:
            AdapterResponse
        """
        prompt = self._build_prompt(system_prompt, messages, tools)
        cli_model = self._map_model(model)

        # 組裝 command
        cmd = [self._claude_path, "-p", "--output-format", "json", "--model", cli_model]
        if session_id:
            cmd.extend(["--resume", session_id])

        env = os.environ.copy()
        env.pop("CLAUDECODE", None)  # 避免巢狀檢查
        env.pop("ANTHROPIC_API_KEY", None)  # 強制 CLI 使用 OAuth token（Max 訂閱）

        # 確保 OAuth token 可用（launchd daemon 沒有 Claude Desktop 注入的環境變數）
        oauth_token = self._get_oauth_token()
        if oauth_token:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")),
                timeout=3600,  # 1 小時超時（複雜任務可能很久）
            )

            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                # 錯誤可能在 stderr 或 stdout JSON 中
                error_detail = stderr_text[:500] if stderr_text else ""
                if not error_detail and stdout_text:
                    try:
                        err_data = json.loads(stdout_text)
                        error_detail = err_data.get("result", stdout_text[:500])
                    except json.JSONDecodeError:
                        error_detail = stdout_text[:500]
                # 偵測 token 過期：收到 Not logged in 時清除持久化 token
                if "Not logged in" in error_detail or "authentication" in error_detail.lower():
                    logger.warning("OAuth token may be expired, clearing persisted token")
                    if self._TOKEN_FILE.exists():
                        try:
                            self._TOKEN_FILE.unlink()
                        except Exception as e:
                            logger.debug(f"[ADAPTERS] token failed (degraded): {e}")
                logger.error(f"claude -p failed (exit {proc.returncode}): {error_detail}")
                return AdapterResponse(
                    text=f"[claude -p error] {error_detail}",
                    stop_reason="error",
                    model=cli_model,
                )

            # 解析 JSON 回應
            try:
                data = json.loads(stdout_text)
            except json.JSONDecodeError:
                # 非 JSON 回應 → 當作純文字
                return AdapterResponse(
                    text=stdout_text,
                    stop_reason="end_turn",
                    model=cli_model,
                )

            # 提取回應內容
            result_text = data.get("result", "")
            sid = data.get("session_id")
            usage = data.get("usage", {})
            duration = data.get("duration_ms", 0)

            self._call_count += 1
            self._total_duration_ms += duration

            # 檢查是否有 tool_calls
            tool_calls = []
            if tools and result_text:
                tool_calls = self._parse_tool_calls(result_text)

            stop_reason = "end_turn"
            if tool_calls:
                stop_reason = "tool_use"
            elif data.get("is_error"):
                stop_reason = "error"

            return AdapterResponse(
                text=result_text if not tool_calls else "",
                stop_reason=stop_reason,
                tool_calls=tool_calls,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                model=cli_model,
                session_id=sid,
                raw=data,
            )

        except asyncio.TimeoutError:
            logger.error("claude -p timed out after 3600s")
            return AdapterResponse(
                text="[claude -p timeout]",
                stop_reason="error",
                model=cli_model,
            )
        except FileNotFoundError:
            logger.error(f"claude CLI not found at: {self._claude_path}")
            return AdapterResponse(
                text="[claude CLI not found]",
                stop_reason="error",
                model=cli_model,
            )
        except Exception as e:
            logger.error(f"claude -p unexpected error: {e}")
            return AdapterResponse(
                text=f"[claude -p error] {e}",
                stop_reason="error",
                model=cli_model,
            )

    @property
    def stats(self) -> Dict[str, Any]:
        """取得呼叫統計."""
        return {
            "call_count": self._call_count,
            "total_duration_ms": self._total_duration_ms,
            "avg_duration_ms": (
                self._total_duration_ms / self._call_count
                if self._call_count > 0 else 0
            ),
        }

    async def close(self) -> None:
        """ClaudeCLIAdapter 不需要清理."""
        pass


# ═══════════════════════════════════════════
# AnthropicAPIAdapter — 備援（API Key 直接呼叫）
# ═══════════════════════════════════════════

class AnthropicAPIAdapter:
    """原有的 AsyncAnthropic API 呼叫方式，作為 fallback.

    當 claude -p 不可用（未安裝 CLI、MAX 訂閱過期等）時使用。
    需要設定 ANTHROPIC_API_KEY 環境變數。
    """

    MODEL_MAP = {
        "opus": "claude-opus-4-6",
        "haiku": "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-20250514",
    }

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._client = None

    def _get_client(self):
        """懶初始化 AsyncAnthropic client."""
        if self._client is None:
            from anthropic import AsyncAnthropic
            import httpx
            if not self._api_key:
                raise ValueError("ANTHROPIC_API_KEY not set for API fallback")
            self._client = AsyncAnthropic(
                api_key=self._api_key,
                timeout=httpx.Timeout(3600.0, connect=30.0),
            )
        return self._client

    def _resolve_model(self, model: str) -> str:
        """將簡短名稱映射到完整模型 ID."""
        return self.MODEL_MAP.get(model, model)

    async def call(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        model: str = "sonnet",
        max_tokens: int = 8192,
        tools: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
    ) -> AdapterResponse:
        """透過 Anthropic API 直接呼叫.

        Args:
            system_prompt: 系統提示詞
            messages: 對話訊息列表
            model: 模型名稱
            max_tokens: 最大回覆 token
            tools: 工具定義列表（原生 tool-use）
            session_id: 未使用（API 模式無 session 概念）

        Returns:
            AdapterResponse
        """
        client = self._get_client()
        model_id = self._resolve_model(model)

        system_blocks = [{
            "type": "text",
            "text": system_prompt,
            "cache_control": {"type": "ephemeral"},
        }] if system_prompt else []

        create_kwargs: Dict[str, Any] = {
            "model": model_id,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": messages,
        }
        if tools:
            create_kwargs["tools"] = tools
            create_kwargs["tool_choice"] = {"type": "auto"}

        try:
            response = await client.messages.create(**create_kwargs)

            # 提取文字和 tool_calls
            text_parts = []
            tool_calls = []
            for block in response.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_calls.append(ToolCall(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    ))

            usage = response.usage if hasattr(response, "usage") else None

            return AdapterResponse(
                text="\n".join(text_parts),
                stop_reason=response.stop_reason,
                tool_calls=tool_calls,
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
                model=model_id,
                raw={"response": response.model_dump() if hasattr(response, "model_dump") else None},
            )

        except Exception as e:
            logger.error(f"API adapter error: {e}")
            return AdapterResponse(
                text=f"[API error] {e}",
                stop_reason="error",
                model=model_id,
            )

    async def close(self) -> None:
        """關閉 API client."""
        if self._client:
            try:
                await self._client.close()
            except Exception as e:
                logger.debug(f"[ADAPTERS] operation failed (degraded): {e}")
            self._client = None


# ═══════════════════════════════════════════
# FallbackAdapter — CLI 失敗自動切 API
# ═══════════════════════════════════════════

class FallbackAdapter:
    """包裝 CLI + API 雙層 fallback.

    先用 ClaudeCLIAdapter，連續失敗超過閾值後自動切換到 AnthropicAPIAdapter。
    CLI 恢復後會自動切回。
    """

    CLI_FAIL_THRESHOLD = 2  # 連續失敗 N 次就切換
    CLI_RETRY_INTERVAL = 300  # 5 分鐘後自動嘗試 CLI 恢復

    def __init__(self, cli: ClaudeCLIAdapter, api: AnthropicAPIAdapter):
        self._cli = cli
        self._api = api
        self._cli_consecutive_fails = 0
        self._using_api = False
        self._switched_to_api_at: float = 0.0  # 切換到 API 的時間戳（首次切換時設定）

    async def call(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        model: str = "sonnet",
        max_tokens: int = 8192,
        tools: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
    ) -> AdapterResponse:
        # 如果 CLI 連續失敗過多，直接走 API
        if not self._using_api:
            resp = await self._cli.call(
                system_prompt, messages, model, max_tokens, tools, session_id
            )
            if resp.stop_reason == "error":
                self._cli_consecutive_fails += 1
                logger.warning(
                    f"CLI adapter failed ({self._cli_consecutive_fails}/{self.CLI_FAIL_THRESHOLD})"
                )
                if self._cli_consecutive_fails >= self.CLI_FAIL_THRESHOLD:
                    import time as _time
                    logger.info("Switching to API adapter due to CLI failures")
                    self._using_api = True
                    self._switched_to_api_at = _time.time()
                    # 立即用 API 重試這次呼叫
                    return await self._api.call(
                        system_prompt, messages, model, max_tokens, tools, session_id
                    )
                return resp
            else:
                self._cli_consecutive_fails = 0
                return resp

        # 時間型 CLI 恢復：超過 CLI_RETRY_INTERVAL 秒後自動嘗試
        import time as _time
        elapsed = _time.time() - self._switched_to_api_at
        if elapsed >= self.CLI_RETRY_INTERVAL:
            probe = await self._cli.call(
                "test", [{"role": "user", "content": "ping"}], "haiku", 10
            )
            if probe.stop_reason != "error":
                logger.info(
                    f"CLI adapter recovered after {elapsed:.0f}s, switching back"
                )
                self._using_api = False
                self._cli_consecutive_fails = 0
                # 用 CLI 處理本次請求
                return await self._cli.call(
                    system_prompt, messages, model, max_tokens, tools, session_id
                )
            else:
                # 重置計時，再等下一個週期
                self._switched_to_api_at = _time.time()
                logger.debug("CLI probe still failing, stay on API")

        # 使用 API adapter
        resp = await self._api.call(
            system_prompt, messages, model, max_tokens, tools, session_id
        )

        # 若 API 也失敗，立即嘗試 CLI（可能限流已解除）
        if resp.stop_reason == "error":
            logger.info("API also failed, trying CLI immediately")
            cli_resp = await self._cli.call(
                system_prompt, messages, model, max_tokens, tools, session_id
            )
            if cli_resp.stop_reason != "error":
                logger.info("CLI recovered via API-failure fallback, switching back")
                self._using_api = False
                self._cli_consecutive_fails = 0
                return cli_resp

        return resp

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "mode": "api" if self._using_api else "cli",
            "cli_fails": self._cli_consecutive_fails,
            "cli": self._cli.stats if hasattr(self._cli, "stats") else {},
        }

    async def close(self) -> None:
        await self._cli.close()
        await self._api.close()


# ═══════════════════════════════════════════
# Factory — 建立最佳可用的 Adapter
# ═══════════════════════════════════════════

async def create_adapter(prefer_cli: bool = True) -> LLMAdapter:
    """建立最佳可用的 LLM Adapter.

    優先順序：
    1. ClaudeCLIAdapter（如果 claude CLI 可用且 prefer_cli=True）
    2. AnthropicAPIAdapter（如果 ANTHROPIC_API_KEY 可用）
    3. 拋出 RuntimeError

    Args:
        prefer_cli: 是否優先使用 claude -p（預設 True）

    Returns:
        LLMAdapter instance
    """
    if prefer_cli:
        claude_path = _find_claude_cli()
        if claude_path:
            # 檢查 claude CLI 是否可用
            try:
                env = os.environ.copy()
                env.pop("CLAUDECODE", None)
                proc = await asyncio.create_subprocess_exec(
                    claude_path, "--version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                if proc.returncode == 0:
                    version = stdout.decode().strip()
                    logger.info(f"Using ClaudeCLIAdapter (Claude Code {version} at {claude_path})")
                    return ClaudeCLIAdapter(claude_path=claude_path)
            except Exception as e:
                logger.warning(f"claude CLI not available: {e}")
        else:
            logger.warning("claude CLI not found in PATH or common locations")

    # Fallback: API
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        logger.info("Using AnthropicAPIAdapter (API Key fallback)")
        return AnthropicAPIAdapter(api_key=api_key)

    raise RuntimeError(
        "No LLM adapter available. "
        "Install Claude Code CLI (MAX plan) or set ANTHROPIC_API_KEY."
    )


def _find_claude_cli() -> Optional[str]:
    """搜尋 claude CLI 的完整路徑.

    launchd daemon 的 PATH 通常不含使用者 shell 路徑，
    所以需要額外搜尋常見安裝位置。
    """
    import shutil

    # 1. 標準 PATH 搜尋
    found = shutil.which("claude")
    if found:
        return found

    # 2. 常見安裝路徑（macOS）
    common_paths = [
        "/opt/homebrew/bin/claude",
        "/usr/local/bin/claude",
        os.path.expanduser("~/.npm-global/bin/claude"),
        os.path.expanduser("~/.local/bin/claude"),
        os.path.expanduser("~/node_modules/.bin/claude"),
    ]
    for p in common_paths:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p

    return None


def create_adapter_sync(prefer_cli: bool = True) -> LLMAdapter:
    """同步版本的 create_adapter — 用於 Brain.__init__.

    當 CLI 和 API Key 同時可用時，返回 FallbackAdapter（CLI 優先，失敗自動切 API）。
    """
    claude_path = _find_claude_cli() if prefer_cli else None
    api_key = os.getenv("ANTHROPIC_API_KEY")

    # 雙管齊下：CLI + API fallback
    if claude_path and api_key:
        logger.info(
            f"Using FallbackAdapter (CLI at {claude_path} + API fallback)"
        )
        return FallbackAdapter(
            cli=ClaudeCLIAdapter(claude_path=claude_path),
            api=AnthropicAPIAdapter(api_key=api_key),
        )

    # 只有 CLI
    if claude_path:
        logger.info(f"Using ClaudeCLIAdapter (claude CLI found at {claude_path})")
        return ClaudeCLIAdapter(claude_path=claude_path)

    # 只有 API
    if api_key:
        logger.info("Using AnthropicAPIAdapter (API Key)")
        return AnthropicAPIAdapter(api_key=api_key)

    logger.warning("No LLM adapter available — Brain will operate in degraded mode")
    claude_path = _find_claude_cli()
    return ClaudeCLIAdapter(claude_path=claude_path or "claude")
