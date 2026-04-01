"""LLM Adapters — claude -p (MAX) 唯一呼叫通道.

v2: 純 ClaudeCLIAdapter（subprocess claude -p）。
已移除 AnthropicAPIAdapter + FallbackAdapter（MUSEON 統一使用 Claude MAX CLI OAuth）。
Brain 透過統一的 AdapterResponse 格式使用，無需關心底層實現。
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
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
    thinking: Optional[str] = None  # Extended Thinking 的思考過程


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
    _TOKEN_BACKUP = Path.home() / ".museon" / "oauth_token.bak"
    # Claude Desktop 可能存放 token 的位置
    _CLAUDE_DESKTOP_SOURCES = [
        Path.home() / ".claude" / ".credentials.json",
        Path.home() / ".config" / "claude" / "credentials.json",
    ]

    def __init__(self, claude_path: Optional[str] = None):
        self._claude_path = claude_path or "claude"
        self._call_count = 0
        self._total_duration_ms = 0
        self._timeout = 3600  # 1 小時超時（與主要呼叫一致）

    def _get_oauth_token(self) -> Optional[str]:
        """取得 OAuth token — 四層來源，絕不輕易放棄.

        優先順序：
        1. 環境變數（Claude Desktop 即時注入）
        2. 持久化文件（~/.museon/oauth_token）
        3. Claude Desktop credentials（~/.claude/.credentials.json）
        4. 備份文件（~/.museon/oauth_token.bak — 永不刪除的最後防線）
        """
        # 1. 環境變數（Claude Desktop 注入，最新鮮）
        token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if token:
            self._save_token(token)
            return token

        # 2. 持久化文件
        if self._TOKEN_FILE.exists():
            try:
                saved = self._TOKEN_FILE.read_text(encoding="utf-8").strip()
                if saved:
                    logger.debug("Using persisted OAuth token from %s", self._TOKEN_FILE)
                    return saved
            except Exception as e:
                logger.debug(f"[ADAPTERS] token read failed: {e}")

        # 3. Claude Desktop credentials（自動續期）
        for cred_path in self._CLAUDE_DESKTOP_SOURCES:
            token = self._read_claude_desktop_token(cred_path)
            if token:
                logger.info(f"[Token] 從 Claude Desktop 取得新 token: {cred_path}")
                self._save_token(token)
                return token

        # 4. 備份文件（最後防線 — 可能過期但值得一試）
        if self._TOKEN_BACKUP.exists():
            try:
                backup = self._TOKEN_BACKUP.read_text(encoding="utf-8").strip()
                if backup:
                    logger.warning("[Token] 使用備份 token（可能已過期，但值得嘗試）")
                    return backup
            except Exception as e:
                logger.debug(f"[ADAPTERS] backup token read failed: {e}")

        return None

    def _read_claude_desktop_token(self, cred_path: Path) -> Optional[str]:
        """從 Claude Desktop credentials 文件讀取 OAuth token."""
        if not cred_path.exists():
            return None
        try:
            data = json.loads(cred_path.read_text(encoding="utf-8"))
            # Claude Desktop 格式：{"oauthToken": "sk-ant-oat01-..."}
            token = data.get("oauthToken") or data.get("oauth_token") or data.get("token")
            if token and token.startswith("sk-ant-"):
                return token
        except Exception as e:
            logger.debug(f"[Token] Claude Desktop credentials 讀取失敗: {e}")
        return None

    def _save_token(self, token: str) -> None:
        """將 OAuth token 持久化到文件 + 備份."""
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
                        elif item.get("type") == "image":
                            # CLI 模式不支援 Vision — graceful degradation
                            parts.append("[圖片已上傳，但 CLI 模式不支援視覺分析。請改用 API 模式。]")
                        elif item.get("type") == "document":
                            # CLI 模式不支援 PDF 文件分析 — graceful degradation
                            parts.append("[PDF 文件已上傳，但 CLI 模式不支援文件分析。請改用 API 模式。]")

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
        *,
        extended_thinking: bool = False,
        thinking_budget: int = 0,
        **kwargs,
    ) -> AdapterResponse:
        """透過 claude -p subprocess 呼叫 LLM.

        Args:
            system_prompt: 系統提示詞
            messages: 對話訊息列表
            model: 模型名稱（會自動映射）
            max_tokens: 最大回覆 token（claude -p 自動管理，此參數供參考）
            tools: 工具定義列表（嵌入 prompt）
            session_id: 前次 session ID（用於 --resume 繼續對話）
            extended_thinking: CLI 模式不支援，接受但忽略
            thinking_budget: CLI 模式不支援，接受但忽略

        Returns:
            AdapterResponse
        """
        if extended_thinking:
            logger.debug("[CLI] extended_thinking requested but CLI mode doesn't support it — ignoring")

        prompt = self._build_prompt(system_prompt, messages, tools)
        cli_model = self._map_model(model)

        # 組裝 command — 不使用 --bare（--bare 禁止 keychain/OAuth 認證）
        cmd = [self._claude_path, "-p", "--output-format", "json", "--model", cli_model]
        if session_id:
            cmd.extend(["--resume", session_id])

        env = os.environ.copy()
        env.pop("CLAUDECODE", None)  # 避免巢狀檢查
        # ⚠️ 關鍵：必須移除 ANTHROPIC_API_KEY，否則 claude -p 會優先用 API key
        # 而不是 OAuth token，導致 "Invalid API key" 錯誤
        env.pop("ANTHROPIC_API_KEY", None)

        # ⚠️ launchd daemon 環境可能缺少 USER，Claude CLI 存取 keychain 需要它
        if "USER" not in env:
            import getpass
            env["USER"] = getpass.getuser()
            logger.info(f"[CLI] Injected USER={env['USER']} for keychain access")

        try:
            prompt_bytes = prompt.encode("utf-8")
            _prompt_mb = len(prompt_bytes) / (1024 * 1024)
            if _prompt_mb > 5:
                logger.warning(
                    f"[CLI] Prompt size {_prompt_mb:.1f}MB — may cause stdin timeout"
                )

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            # stdin 寫入 + drain 使用獨立短超時（30 秒），
            # 防止超大 prompt 卡住 OS pipe buffer
            try:
                proc.stdin.write(prompt_bytes)
                await asyncio.wait_for(proc.stdin.drain(), timeout=30.0)
                proc.stdin.close()
            except asyncio.TimeoutError:
                logger.error(
                    f"[CLI] stdin write timeout (30s) — prompt size {_prompt_mb:.1f}MB"
                )
                proc.kill()
                return AdapterResponse(
                    text="",
                    model=model,
                    stop_reason="error",
                    input_tokens=0,
                    output_tokens=0,
                )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),  # stdin 已關閉，只等 stdout/stderr
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
                # 偵測 token 過期：僅在明確認證錯誤時清除持久化 token
                # 排除 stdin timeout / pipe error 等非認證問題，避免誤刪有效 token
                _AUTH_ERROR_SIGNALS = ("Not logged in", "authentication", "unauthorized", "invalid token")
                _is_auth_error = any(sig in error_detail.lower() for sig in _AUTH_ERROR_SIGNALS)
                _NON_AUTH_SIGNALS = ("no stdin data", "pipe", "timeout", "signal")
                _is_non_auth = any(sig in error_detail.lower() for sig in _NON_AUTH_SIGNALS)
                if _is_auth_error and not _is_non_auth:
                    # P1-2: 永不刪除 token — 改為備份後標記 stale
                    logger.warning("[Token] OAuth token expired/invalid — 備份後標記 stale（不刪除）")
                    if self._TOKEN_FILE.exists():
                        try:
                            # 備份到 .bak（永久保留，最後防線）
                            import shutil
                            shutil.copy2(str(self._TOKEN_FILE), str(self._TOKEN_BACKUP))
                            # 不刪除主檔案，只記錄為 stale
                            _stale_marker = self._TOKEN_FILE.parent / "oauth_token.stale"
                            _stale_marker.write_text(
                                f"stale_at={datetime.now().isoformat()}\nreason={error_detail[:200]}",
                                encoding="utf-8",
                            )
                        except Exception as e:
                            logger.debug(f"[Token] stale 標記失敗: {e}")
                elif _is_auth_error and _is_non_auth:
                    logger.info("[Token] CLI error contains auth signal but also pipe/timeout — keeping token")
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
            # Transient pipe errors (WriteUnixTransport closed) — retry once
            if "Transport" in str(e) or "handler is closed" in str(e):
                logger.warning(f"claude -p transient error, retrying in 2s: {e}")
                await asyncio.sleep(2)
                try:
                    proc2 = await asyncio.create_subprocess_exec(
                        self._claude_path, "-p", cli_model, "--output-format", "json",
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout2, _ = await asyncio.wait_for(
                        proc2.communicate(input=prompt_bytes),
                        timeout=self._timeout,
                    )
                    raw2 = stdout2.decode("utf-8", errors="replace").strip()
                    if raw2:
                        data2 = json.loads(raw2)
                        text2 = data2.get("result", raw2) if isinstance(data2, dict) else raw2
                        return AdapterResponse(text=text2, stop_reason="end_turn", model=cli_model)
                except Exception as e2:
                    logger.error(f"claude -p retry also failed: {e2}")
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

    併發控制：全域 semaphore 限制同時進行的 API 請求數，
    防止多群組同時壓測時觸發 Anthropic 429 rate limit。
    """

    MODEL_MAP = {
        "opus": "claude-opus-4-6",
        "haiku": "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-20250514",
    }

    # 全域併發控制：最多 5 個同時進行的 API 請求
    # 超出的請求會等待（不拒絕），間隔自然拉開
    _global_semaphore: Optional[asyncio.Semaphore] = None
    MAX_CONCURRENT_API_CALLS = 5

    @classmethod
    def _get_semaphore(cls) -> asyncio.Semaphore:
        """懶初始化全域 semaphore（必須在 event loop 內呼叫）."""
        if cls._global_semaphore is None:
            cls._global_semaphore = asyncio.Semaphore(cls.MAX_CONCURRENT_API_CALLS)
        return cls._global_semaphore

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
        *,
        extended_thinking: bool = False,
        thinking_budget: int = 10000,
    ) -> AdapterResponse:
        """透過 Anthropic API 直接呼叫.

        Args:
            system_prompt: 系統提示詞
            messages: 對話訊息列表
            model: 模型名稱
            max_tokens: 最大回覆 token
            tools: 工具定義列表（原生 tool-use）
            session_id: 未使用（API 模式無 session 概念）
            extended_thinking: 啟用 Extended Thinking（Claude 先思考再回答）
            thinking_budget: 思考預算（tokens），預設 10000

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

        # Extended Thinking：讓 Claude 先內部推理再回答
        if extended_thinking:
            create_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }
            # Extended Thinking 需要更高的 max_tokens（thinking + output）
            create_kwargs["max_tokens"] = max(max_tokens, thinking_budget + 8192)
            # Thinking 模式不支援 prompt caching 的 cache_control
            if system_blocks:
                create_kwargs["system"] = [{"type": "text", "text": system_prompt}]

        # L2 併發控制 + L3 rate_limiter 驅動的智慧重試
        from museon.llm.rate_limiter import get_backoff, get_monitor, get_degrader

        _bo = get_backoff()
        _mon = get_monitor()
        _deg = get_degrader()
        _current_model = model_id

        for _attempt in range(_bo._cfg.max_retries + 1):
            try:
                # 更新 create_kwargs 的 model（降級時會變）
                create_kwargs["model"] = _current_model

                sem = self._get_semaphore()
                async with sem:
                    response = await client.messages.create(**create_kwargs)

                # 解析 rate limit headers（如果有）
                if hasattr(response, "_response") and hasattr(response._response, "headers"):
                    _mon.update_from_headers(dict(response._response.headers))

                # 提取文字、thinking 和 tool_calls
                text_parts = []
                thinking_parts = []
                tool_calls = []
                for block in response.content:
                    if getattr(block, "type", None) == "thinking":
                        thinking_parts.append(block.thinking)
                    elif hasattr(block, "text"):
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
                    model=_current_model,
                    raw={"response": response.model_dump() if hasattr(response, "model_dump") else None},
                    thinking="\n".join(thinking_parts) if thinking_parts else None,
                )

            except Exception as e:
                error_type = type(e).__name__
                error_str = str(e)

                # 認證錯誤（401）— 不可重試
                if "authentication" in error_str.lower() or "401" in error_str:
                    logger.error(f"API authentication error (不可重試): {e}")
                    return AdapterResponse(
                        text=f"[API auth error] {e}",
                        stop_reason="auth_error",
                        model=_current_model,
                    )

                # 429 / 529 — 用 rate_limiter 智慧重試
                _is_retryable = (
                    ("rate" in error_str.lower() and "limit" in error_str.lower())
                    or "429" in error_str
                    or "overloaded" in error_str.lower()
                    or "529" in error_str
                )

                if _is_retryable:
                    _mon.record_hit()

                    # 嘗試從 exception 取 retry-after header
                    _retry_after = None
                    if hasattr(e, "response") and hasattr(e.response, "headers"):
                        _ra = e.response.headers.get("retry-after")
                        if _ra:
                            try:
                                _retry_after = float(_ra)
                            except (ValueError, TypeError):
                                pass

                    if _bo.should_retry(_attempt):
                        _delay = _bo.compute_delay(_attempt, _retry_after)
                        logger.warning(
                            f"API 429/529 (attempt {_attempt + 1}): "
                            f"retry in {_delay:.1f}s "
                            f"(retry-after={_retry_after}, model={_current_model})"
                        )
                        await asyncio.sleep(_delay)

                        # 第 2 次重試後嘗試降級 model
                        if _attempt >= 1:
                            _degraded = _deg.degrade(_current_model, reason="rate_limit")
                            if _degraded:
                                _current_model = _degraded
                        continue

                    # 重試耗盡
                    logger.error(
                        f"API rate limit exhausted after {_bo._cfg.max_retries} retries | "
                        f"model={_current_model} hits={_mon.hit_count}"
                    )
                    return AdapterResponse(
                        text="[API rate limit] 重試次數已達上限，請稍後再試。",
                        stop_reason="rate_limited",
                        model=_current_model,
                    )

                logger.error(f"API adapter error ({error_type}): {e}")
                return AdapterResponse(
                    text=f"[API error] {e}",
                    stop_reason="error",
                    model=_current_model,
                )

    # ── Token Counting API ──────────────────────

    async def count_tokens(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        model: str = "sonnet",
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """精確計算 token 數量（使用 Anthropic Token Counting API）.

        比本地估算更準確。用於 token 預算管理、prompt 優化。

        Returns:
            input_tokens 數量，失敗時回傳 -1
        """
        try:
            client = self._get_client()
            model_id = self._resolve_model(model)

            count_kwargs: Dict[str, Any] = {
                "model": model_id,
                "system": [{"type": "text", "text": system_prompt}] if system_prompt else [],
                "messages": messages,
            }
            if tools:
                count_kwargs["tools"] = tools

            result = await client.messages.count_tokens(**count_kwargs)
            return result.input_tokens
        except Exception as e:
            logger.warning(f"[TokenCount] 計數失敗（降級為估算）: {e}")
            return -1

    # ── Batch API ──────────────────────

    async def create_batch(
        self,
        requests: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """建立批次處理任務（50% 折扣，24 小時內完成）.

        適用於 Nightly pipeline 等非即時任務。

        Args:
            requests: 批次請求列表，每個元素為：
                {
                    "custom_id": "unique-id",
                    "params": {
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": "..."}],
                    }
                }

        Returns:
            {"batch_id": "...", "status": "in_progress"} 或 None
        """
        try:
            client = self._get_client()
            batch = await client.messages.batches.create(requests=requests)
            logger.info(
                f"[Batch] 批次已建立 | id={batch.id} | "
                f"requests={len(requests)} | status={batch.processing_status}"
            )
            return {
                "batch_id": batch.id,
                "status": batch.processing_status,
                "created_at": batch.created_at.isoformat() if hasattr(batch, "created_at") else None,
                "request_count": len(requests),
            }
        except Exception as e:
            logger.error(f"[Batch] 批次建立失敗: {e}")
            return None

    async def get_batch_status(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """查詢批次任務狀態."""
        try:
            client = self._get_client()
            batch = await client.messages.batches.retrieve(batch_id)
            return {
                "batch_id": batch.id,
                "status": batch.processing_status,
                "request_counts": {
                    "processing": batch.request_counts.processing,
                    "succeeded": batch.request_counts.succeeded,
                    "errored": batch.request_counts.errored,
                    "canceled": batch.request_counts.canceled,
                    "expired": batch.request_counts.expired,
                },
            }
        except Exception as e:
            logger.error(f"[Batch] 狀態查詢失敗: {e}")
            return None

    async def get_batch_results(self, batch_id: str) -> List[Dict[str, Any]]:
        """取得批次任務結果."""
        try:
            client = self._get_client()
            results = []
            async for result in client.messages.batches.results(batch_id):
                results.append({
                    "custom_id": result.custom_id,
                    "type": result.result.type,
                    "message": result.result.message.model_dump()
                    if hasattr(result.result, "message") and result.result.message
                    else None,
                })
            logger.info(f"[Batch] 取得 {len(results)} 筆結果 | batch_id={batch_id}")
            return results
        except Exception as e:
            logger.error(f"[Batch] 結果取得失敗: {e}")
            return []

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
        *,
        extended_thinking: bool = False,
        thinking_budget: int = 10000,
    ) -> AdapterResponse:
        # Extended Thinking 只在 API 模式下可用
        # CLI 模式下忽略此參數（CLI 不支援 thinking）
        _api_kwargs = {}
        if extended_thinking:
            _api_kwargs = {"extended_thinking": True, "thinking_budget": thinking_budget}

        # 如果 CLI 連續失敗過多，直接走 API
        if not self._using_api:
            # CLI 不支援 extended_thinking，但如果啟用了 thinking，
            # 直接走 API（不浪費 CLI 嘗試）
            if extended_thinking:
                return await self._api.call(
                    system_prompt, messages, model, max_tokens, tools, session_id,
                    **_api_kwargs,
                )
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
                        system_prompt, messages, model, max_tokens, tools, session_id,
                        **_api_kwargs,
                    )
                return resp
            else:
                self._cli_consecutive_fails = 0
                return resp

        # 時間型 CLI 恢復：超過 CLI_RETRY_INTERVAL 秒後自動嘗試
        import time as _time
        elapsed = _time.time() - self._switched_to_api_at
        if elapsed >= self.CLI_RETRY_INTERVAL and not extended_thinking:
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
            system_prompt, messages, model, max_tokens, tools, session_id,
            **_api_kwargs,
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

            # 雙 adapter 同時失敗 — 返回友善降級回覆而非 raw error
            logger.error("DUAL ADAPTER FAILURE: both CLI and API are down")
            return AdapterResponse(
                text=(
                    "⚠️ 系統暫時無法連接 AI 服務（CLI 與 API 均不可用）。"
                    "這通常是暫時性問題，我會在服務恢復後自動重新嘗試。"
                    "如果持續出現，請檢查網路連線或 API Key 設定。"
                ),
                stop_reason="error",
                model=model,
            )

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
    """建立 LLM Adapter（純 CLI 通道）.

    MUSEON 統一使用 Claude MAX CLI OAuth 通道。

    Returns:
        ClaudeCLIAdapter instance
    """
    claude_path = _find_claude_cli()
    if claude_path:
        # 檢查 claude CLI 是否可用
        try:
            env = os.environ.copy()
            env.pop("CLAUDECODE", None)
            env.pop("ANTHROPIC_API_KEY", None)
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

    raise RuntimeError(
        "claude CLI not found. Install Claude Code CLI (MAX plan)."
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

    MUSEON 統一使用 Claude MAX CLI OAuth 通道，不再使用 API Key。
    """
    claude_path = _find_claude_cli()
    if claude_path:
        logger.info(f"Using ClaudeCLIAdapter (Claude MAX CLI at {claude_path})")
        return ClaudeCLIAdapter(claude_path=claude_path)

    logger.warning("claude CLI not found — Brain will operate in degraded mode")
    return ClaudeCLIAdapter(claude_path="claude")
