"""
run_tool_loop — 獨立的 tool-use 迴圈。

從 BrainToolsMixin._call_llm() 提取，不依賴任何 self._* 狀態。
供需要 tool-use 的場景使用。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 常數
_MAX_TOKENS_DEFAULT = 16384
_TOOL_RESULT_TRUNCATE_LEN = 15000
_COMPLEX_KEYWORDS = (
    "搜尋", "查", "找", "search", "分析", "比較",
    "研究", "調查", "趨勢", "幫我做", "產出", "報告",
    "計畫", "企劃", "排程", "generate", "create",
)


async def run_tool_loop(
    llm_adapter,
    tool_executor,
    system_prompt: str,
    messages: List[Dict[str, Any]],
    model: str = "opus",
    tool_definitions: Optional[List[Dict]] = None,
    max_iterations: int = 16,
    max_tokens: int = _MAX_TOKENS_DEFAULT,
) -> str:
    """獨立的 tool-use 迴圈。

    輸入 system_prompt + messages + tools，輸出最終文字回覆。
    邏輯取自 brain_tools.py 第 260-540 行，但不依賴任何 class 狀態。

    Args:
        llm_adapter: LLMAdapter instance (call() method)
        tool_executor: ToolExecutor instance (execute() method)
        system_prompt: System prompt text
        messages: Conversation messages (will be mutated during tool loop)
        model: Model to use ("opus", "sonnet", "haiku")
        tool_definitions: Tool definitions for Claude API
        max_iterations: Max tool-use loop iterations
        max_tokens: Max tokens per LLM call

    Returns:
        Final response text
    """
    from museon.llm.adapters import APICompatResponse

    # 初始 LLM 呼叫（帶 tools）
    adapter_resp = await llm_adapter.call(
        system_prompt=system_prompt,
        messages=messages,
        model=model,
        max_tokens=max_tokens,
        tools=tool_definitions,
    )

    if adapter_resp.stop_reason in ("error", "auth_error", "rate_limited"):
        return adapter_resp.text or ""

    response = APICompatResponse(adapter_resp)

    # 動態決定迴圈上限
    _last_user_msg = ""
    for _m in reversed(messages):
        if _m.get("role") == "user":
            _c = _m.get("content", "")
            _last_user_msg = _c if isinstance(_c, str) else ""
            break
    _is_complex = any(kw in _last_user_msg for kw in _COMPLEX_KEYWORDS)
    if _is_complex:
        max_iterations = max(max_iterations, 24)

    # Tool-use 迴圈
    iteration = 0
    total_tool_calls = 0
    all_tools_failed_break = False
    retry_count: Dict[str, int] = {}

    while (
        response.stop_reason == "tool_use"
        and iteration < max_iterations
        and tool_definitions
        and tool_executor
    ):
        iteration += 1

        # 收集並執行所有 tool_use blocks
        tool_results = []
        failed_tools_this_round = 0

        for block in response.content:
            if block.type == "tool_use":
                total_tool_calls += 1
                logger.info(
                    f"[L2 Tool] #{total_tool_calls}: "
                    f"{block.name}({json.dumps(block.input, ensure_ascii=False)[:200]})"
                )

                result = await tool_executor.execute(
                    tool_name=block.name,
                    arguments=block.input,
                )
                is_error = not result.get("success", False)

                if is_error:
                    failed_tools_this_round += 1
                    error_msg = result.get("error", "未知錯誤")
                    retries = retry_count.get(block.name, 0)

                    if retries < 2:
                        retry_count[block.name] = retries + 1
                        if "timeout" in error_msg.lower() or "超時" in error_msg:
                            hint = "暫時性超時，請重試或改用其他工具。"
                        elif "搜尋失敗" in error_msg or "SearXNG" in error_msg:
                            hint = "搜尋服務不可用，改用 web_crawl 爬取已知 URL。"
                        else:
                            hint = "可以換參數重試或改用其他工具。"
                        result_str = f"[工具失敗] {block.name}: {error_msg}\n{hint}"
                    else:
                        result_str = (
                            f"[工具已重試 2 次仍失敗] {block.name}: {error_msg}\n"
                            f"請用已取得的資料盡力回覆。"
                        )
                else:
                    result_str = json.dumps(result, ensure_ascii=False)
                    if len(result_str) > _TOOL_RESULT_TRUNCATE_LEN:
                        result_str = result_str[:_TOOL_RESULT_TRUNCATE_LEN] + '..."}'

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                    "is_error": is_error,
                })

        # 將 assistant + tool results 加入 messages
        messages.append({
            "role": "assistant",
            "content": [
                block.model_dump() if hasattr(block, "model_dump")
                else {"type": "text", "text": block.text}
                if hasattr(block, "text")
                else {"type": "tool_use", "id": block.id,
                      "name": block.name, "input": block.input}
                for block in response.content
            ],
        })
        messages.append({
            "role": "user",
            "content": tool_results,
        })

        # 全失敗跳出
        _all_exhausted = all(
            retry_count.get(block.name, 0) >= 2
            for block in response.content
            if block.type == "tool_use"
        ) if failed_tools_this_round > 0 else False

        if (
            failed_tools_this_round > 0
            and failed_tools_this_round == len(tool_results)
            and _all_exhausted
        ):
            logger.warning(
                f"所有 {failed_tools_this_round} 個工具失敗（已重試），跳出迴圈"
            )
            all_tools_failed_break = True
            break

        # 再次呼叫 LLM
        adapter_resp = await llm_adapter.call(
            system_prompt=system_prompt,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            tools=tool_definitions,
        )
        response = APICompatResponse(adapter_resp)

    if total_tool_calls > 0:
        logger.info(f"[L2 Tool] loop done: {total_tool_calls} calls, {iteration} iterations")

    # 迴圈結束後的合成回覆（如果被截斷或全失敗）
    if (
        (response.stop_reason == "tool_use" or all_tools_failed_break)
        and total_tool_calls > 0
    ):
        synth_hint = (
            "請根據上面的工具結果，用繁體中文完整回答我的問題。"
            "回覆最後包含一個具體的可操作下一步。"
            if not all_tools_failed_break
            else "工具執行遇到問題。請用繁體中文說明並提供替代方案。"
        )
        messages.append({"role": "user", "content": synth_hint})

        adapter_resp = await llm_adapter.call(
            system_prompt=system_prompt,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
        )
        response = APICompatResponse(adapter_resp)

    # 提取最終文字
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    if getattr(response, "stop_reason", None) == "max_tokens":
        text += "\n\n———\n⚠️ 回覆因長度限制被截斷了。你可以說「繼續」讓我接著說。"

    return text
