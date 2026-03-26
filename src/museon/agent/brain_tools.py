"""BrainToolsMixin — LLM 呼叫與工具處理方法群.

從 brain.py 提取的 Mixin，負責 Claude API 呼叫、模型切換、
session 歷史管理、記憶持久化、技能追蹤等邏輯。
"""

import asyncio
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BrainToolsMixin:
    """LLM 呼叫與工具處理方法群 — Mixin for MuseonBrain."""

    # ═══════════════════════════════════════════
    # 常數定義（v1.49: 從方法內收斂至此）
    # ═══════════════════════════════════════════

    # Fallback 模型鏈（Opus → Sonnet → Haiku → 離線）
    _MODEL_CHAIN = [
        "claude-opus-4-6",
        "claude-sonnet-4-20250514",
        "claude-haiku-4-5-20251001",
    ]

    # LLM 呼叫參數
    _MAX_TOKENS_PRIMARY = 16384       # 主要 LLM 呼叫上限
    _MAX_TOKENS_DISPATCH = 8192       # Dispatch/Orchestrator 呼叫上限
    _MAX_TOKENS_HEALTH_PROBE = 10     # 離線 self-probe 上限

    # Tool-Use 迴圈控制
    _MAX_TOOL_ITERATIONS_COMPLEX = 24  # 複雜任務工具迴圈上限
    _MAX_TOOL_ITERATIONS_SIMPLE = 16   # 簡單任務工具迴圈上限
    _TOOL_RESULT_TRUNCATE_LEN = 15000  # 工具結果截斷長度

    # 複雜任務關鍵字（決定工具迴圈上限）
    _COMPLEX_KEYWORDS = (
        "搜尋", "查", "找", "search", "分析", "比較",
        "研究", "調查", "趨勢", "幫我做", "產出", "報告",
        "計畫", "企劃", "排程", "generate", "create",
    )

    # 離線模式
    _OFFLINE_PROBE_INTERVAL = 300  # 秒（5 分鐘自動 probe 恢復）

    # ═══════════════════════════════════════
    # 三管線分類器（Haiku 單 token）
    # ═══════════════════════════════════════

    _CLASSIFY_PROMPT = (
        "Classify the user message complexity. Reply with exactly one uppercase letter, nothing else.\n\n"
        "F — Fast: greetings, acknowledgments, emotional expressions, very short small talk, "
        "simple confirmations, reactions (e.g. 早安, OK, 哈哈, 好的, 謝啦, 讚, 晚安, 收到, 嗯嗯, 笑死)\n"
        "S — Standard: questions, advice requests, information lookups, moderate conversation, "
        "opinions, short tasks (e.g. 今天天氣怎樣, 推薦餐廳, 這個怎麼用, 你覺得呢, 幫我查一下)\n"
        "D — Deep: strategic analysis, multi-step tasks, report generation, complex reasoning, "
        "long detailed requests (e.g. 幫我分析投資組合, 寫一份企劃書, 比較三個方案的優缺點)\n\n"
        "When uncertain, prefer S over F (never under-classify)."
    )
    _CLASSIFY_MAP = {"F": "FAST", "S": "STANDARD", "D": "DEEP"}

    async def _classify_complexity(self, content: str) -> str:
        """用 Haiku 單 token 分類訊息複雜度 → FAST / STANDARD / DEEP.

        500ms timeout，失敗時 fallback 到 STANDARD。
        """
        if not self._llm_adapter or self._offline_flag:
            return "STANDARD"
        try:
            resp = await asyncio.wait_for(
                self._call_llm_with_model(
                    system_prompt=self._CLASSIFY_PROMPT,
                    messages=[{"role": "user", "content": content}],
                    model="claude-haiku-4-5-20251001",
                    max_tokens=1,
                ),
                timeout=2.0,
            )
            label = resp.strip().upper()[:1]
            result = self._CLASSIFY_MAP.get(label, "STANDARD")
            logger.info(f"[Classifier] '{content[:20]}...' → {label} → {result}")
            return result
        except Exception as e:
            logger.warning(f"[Classifier] failed ({e}), fallback → STANDARD")
            return "STANDARD"

    async def _call_llm(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        anima_mc: Optional[Dict[str, Any]] = None,
        enable_tools: bool = False,
        user_content: str = "",
        matched_skills: Optional[List[str]] = None,
        loop: str = "EXPLORATION_LOOP",
    ) -> str:
        """呼叫 Claude API — 含 Router 智能分流 + 多模型 Fallback + Prompt Caching + Tool Use.

        分流策略（Router v4）：
        1. Router 根據訊息內容分類 → Opus（複雜）/ Sonnet（中等）/ Haiku（簡單）
        2. 選定模型失敗 → Fallback 到下一層模型
        3. 都失敗 → 離線模式

        Prompt Caching (BDD Spec §14)：
        將 system prompt 分為 static_core（DNA27 核心，跨 turn 不變）
        和 dynamic sections，static_core 標記 cache_control。
        每 turn 節省 ~3000-4500 input tokens。

        Tool Use (Anthropic API)：
        當 enable_tools=True 時，附帶工具定義讓 Claude 自動調用。
        實作 tool_use 迴圈：Claude 呼叫工具 → 執行 → 回傳結果 → 再次呼叫。
        最多 5 次迭代，避免無限迴圈。

        Args:
            system_prompt: 系統提示詞
            messages: 對話歷史
            anima_mc: ANIMA_MC（用於判斷用哪個模型）
            enable_tools: 是否啟用 tool_use（~400 tokens overhead）
            user_content: 使用者原始訊息（供 Router 分類）
            matched_skills: 匹配到的技能名稱（供 Router 判斷）

        Returns:
            回覆文字
        """
        import time as _time

        # ── 離線模式 self-probe：每 5 分鐘嘗試一次 LLM 呼叫 ──
        _OFFLINE_PROBE_INTERVAL = self._OFFLINE_PROBE_INTERVAL
        if self._offline_flag and self._llm_adapter:
            now = _time.time()
            if now - self._last_offline_probe_ts >= _OFFLINE_PROBE_INTERVAL:
                self._last_offline_probe_ts = now
                logger.info("🔄 Brain: offline self-probe — testing LLM availability...")
                try:
                    probe_resp = await asyncio.wait_for(
                        self._llm_adapter.call(
                            system_prompt="Reply with exactly: OK",
                            messages=[{"role": "user", "content": "health check"}],
                            model="haiku",
                            max_tokens=self._MAX_TOKENS_HEALTH_PROBE,
                        ),
                        timeout=15,
                    )
                    if probe_resp and getattr(probe_resp, "stop_reason", "error") != "error":
                        # LLM 恢復！退出離線模式
                        self._offline_flag = False
                        self._last_offline_probe_ts = 0.0
                        logger.info("🟢 Brain: self-probe succeeded — exiting offline mode")
                        # 通知 VitalSigns
                        if self._governor:
                            try:
                                vs = self._governor.get_vital_signs()
                                if vs:
                                    vs.on_llm_success()
                            except Exception as e:
                                logger.debug(f"VitalSigns.on_llm_success (offline probe) 失敗: {e}")
                except Exception as e:
                    logger.debug(f"Brain: offline self-probe failed: {e}")

        # SafetyAnchor: 快速安全檢查
        if self.safety_anchor:
            if not self.safety_anchor.quick_check(system_prompt):
                logger.error("SafetyAnchor 快速檢查失敗！拒絕回覆。")
                return "系統安全檢查未通過，請聯繫管理員。"

        if not self._llm_adapter:
            return self._offline_response(messages, error_msg="LLM adapter not initialized")

        from museon.llm.adapters import APICompatResponse

        # 建構 Prompt Caching content blocks
        system_blocks = self._build_cached_system(system_prompt)

        # 準備 tool definitions（僅在啟用時附帶，節省 ~400 tokens）
        # v10.2: 動態載入 — 靜態工具 + MCP 伺服器動態發現的工具
        tool_definitions = None
        if enable_tools and self._tool_executor:
            try:
                from museon.agent.tool_schemas import get_all_tool_definitions
                dynamic_tools = self._tool_executor.get_dynamic_tool_definitions()
                tool_definitions = get_all_tool_definitions(dynamic_tools)
                logger.debug(
                    f"Tool-use enabled: {len(tool_definitions)} tools "
                    f"(static + {len(dynamic_tools)} MCP)"
                )
            except ImportError:
                logger.warning("tool_schemas 載入失敗，tool_use 降級關閉")

        # ── Router 智能分流 ──
        _route_decision = {"model": "opus", "reason": "no_router", "task_type": "complex"}
        if self._router and user_content:
            try:
                _route_decision = self._router.classify(
                    message=user_content,
                    session_context={"active_skills": matched_skills or []},
                )
                logger.info(
                    f"Router 分流: model={_route_decision['model']}, "
                    f"reason={_route_decision['reason']}, "
                    f"task_type={_route_decision['task_type']}"
                )
            except Exception as e:
                logger.warning(f"Router 分流失敗（降級 Sonnet）: {e}")

        # 根據 Router 決定模型（三層分流：Opus → Sonnet → Haiku）
        _router_model = _route_decision["model"]
        if _router_model == "opus":
            _ordered_chain = ["opus", "sonnet", "haiku"]
        elif _router_model == "sonnet":
            _ordered_chain = ["sonnet", "opus", "haiku"]
        else:  # haiku
            _ordered_chain = ["haiku", "sonnet", "opus"]

        # 嘗試 Fallback 模型鏈
        last_error = None
        for model in _ordered_chain:
            try:
                # Extended Thinking：SLOW_LOOP 且無 tool-use 時啟用深度推理
                _use_thinking = (
                    loop == "SLOW_LOOP"
                    and not tool_definitions
                    and model in ("opus", "sonnet")
                )

                # 透過 LLMAdapter 呼叫（claude -p 或 API fallback）
                _adapter_resp = await self._llm_adapter.call(
                    system_prompt=system_prompt,
                    messages=messages,
                    model=model,
                    max_tokens=self._MAX_TOKENS_PRIMARY,
                    tools=tool_definitions,
                    extended_thinking=_use_thinking,
                    thinking_budget=10000 if _use_thinking else 0,
                )

                if _adapter_resp.stop_reason == "error":
                    raise RuntimeError(f"Adapter error: {_adapter_resp.text}")

                # P1: 認證錯誤不可重試 — 同一 adapter 的 key 對所有模型都一樣
                if _adapter_resp.stop_reason == "auth_error":
                    logger.error("認證錯誤（不可重試），直接進入離線模式")
                    return self._offline_response(messages, error_msg=_adapter_resp.text)

                # P1: 速率限制 — 不切模型（同一 key 的限制跨模型共享）
                if _adapter_resp.stop_reason == "rate_limited":
                    logger.warning("速率限制，直接進入離線模式（等待限制解除）")
                    return self._offline_response(messages, error_msg=_adapter_resp.text)

                # 包裝為 API 相容格式（讓 tool-use 迴圈無需修改）
                response = APICompatResponse(_adapter_resp)

                # ── Tool-Use 迴圈（v10 韌性版）──
                # Claude 可能要求調用工具（stop_reason="tool_use"），
                # 我們執行工具後把結果送回。
                # v10: 大幅提高迭代上限 + 失敗重試 + context 壓縮
                _last_user_msg = ""
                for _m in reversed(messages):
                    if _m.get("role") == "user":
                        _c = _m.get("content", "")
                        _last_user_msg = _c if isinstance(_c, str) else ""
                        break
                _is_complex = any(kw in _last_user_msg for kw in self._COMPLEX_KEYWORDS)
                MAX_TOOL_ITERATIONS = (
                    self._MAX_TOOL_ITERATIONS_COMPLEX if _is_complex
                    else self._MAX_TOOL_ITERATIONS_SIMPLE
                )
                iteration = 0
                total_tool_calls = 0
                all_tools_failed_break = False
                _retry_count: Dict[str, int] = {}  # v10: 工具失敗重試計數

                while (
                    response.stop_reason == "tool_use"
                    and iteration < MAX_TOOL_ITERATIONS
                    and tool_definitions
                    and self._tool_executor
                ):
                    iteration += 1

                    # 1. 收集所有 tool_use blocks 並執行
                    tool_results = []
                    failed_tools_this_round = 0
                    for block in response.content:
                        if block.type == "tool_use":
                            total_tool_calls += 1
                            logger.info(
                                f"Tool call #{total_tool_calls}: "
                                f"{block.name}({json.dumps(block.input, ensure_ascii=False)[:200]})"
                            )
                            # 執行工具
                            result = await self._tool_executor.execute(
                                tool_name=block.name,
                                arguments=block.input,
                            )
                            is_error = not result.get("success", False)

                            # 格式化工具結果 — v10.5: 失敗時允許重試（最多 2 次）
                            if is_error:
                                failed_tools_this_round += 1
                                error_msg = result.get("error", "未知錯誤")
                                _tool_retries = _retry_count.get(block.name, 0)
                                if _tool_retries < 2:
                                    # v10.5: 允許最多 2 次重試（從 1 次提高）
                                    _retry_count[block.name] = _tool_retries + 1
                                    # 根據失敗類型給出具體重試建議
                                    if "timeout" in error_msg.lower() or "超時" in error_msg:
                                        retry_hint = (
                                            "這是暫時性超時，請立即重試相同工具（不需要換參數）。"
                                            "如果再次超時，改用其他工具完成任務。"
                                        )
                                    elif "搜尋失敗" in error_msg or "SearXNG" in error_msg:
                                        retry_hint = (
                                            "搜尋服務暫時不可用。"
                                            "請嘗試用 web_crawl 直接爬取已知的可靠來源 URL。"
                                        )
                                    elif "未連線" in error_msg or "連線" in error_msg:
                                        retry_hint = (
                                            "外部服務連線異常。"
                                            "請改用其他工具完成任務。"
                                        )
                                    else:
                                        retry_hint = (
                                            "你可以嘗試用不同參數重試此工具，或改用其他工具完成任務。"
                                        )
                                    result_str = (
                                        f"[工具執行失敗] {block.name}: {error_msg}\n"
                                        f"{retry_hint}"
                                    )
                                else:
                                    # 已重試 2 次 → 用已有資料回覆
                                    result_str = (
                                        f"[工具已重試 2 次仍失敗] {block.name}: {error_msg}\n"
                                        f"請用已取得的資料盡力回覆使用者。"
                                        f"不要說「因為超時只能給不完整資料」，"
                                        f"直接說明哪些資訊已取得、哪些暫時無法取得。"
                                    )
                            else:
                                result_str = json.dumps(
                                    result, ensure_ascii=False
                                )
                                # 截斷過長結果（避免 token 爆炸）
                                if len(result_str) > self._TOOL_RESULT_TRUNCATE_LEN:
                                    result_str = result_str[:self._TOOL_RESULT_TRUNCATE_LEN] + '..."}'

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_str,
                                "is_error": is_error,
                            })

                    # 2. 將 assistant response + tool results 加入 messages
                    # 注意：response.content 包含 text + tool_use blocks
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

                    # v10.5: 只有所有工具都失敗且都已重試 2 次才跳出
                    _all_exhausted = all(
                        _retry_count.get(block.name, 0) >= 2
                        for block in response.content
                        if block.type == "tool_use"
                    ) if failed_tools_this_round > 0 else False
                    if (
                        failed_tools_this_round > 0
                        and failed_tools_this_round == len(tool_results)
                        and _all_exhausted
                    ):
                        logger.warning(
                            f"本輪所有 {failed_tools_this_round} 個工具都失敗（已重試），"
                            "跳出 tool-use 迴圈，交由合成回覆處理"
                        )
                        all_tools_failed_break = True
                        break

                    # 3. 再次呼叫 LLM（帶相同 tools）
                    _adapter_resp = await self._llm_adapter.call(
                        system_prompt=system_prompt,
                        messages=messages,
                        model=model,
                        max_tokens=self._MAX_TOKENS_PRIMARY,
                        tools=tool_definitions,
                    )
                    response = APICompatResponse(_adapter_resp)

                if total_tool_calls > 0:
                    logger.info(
                        f"Tool-use loop completed: "
                        f"{total_tool_calls} calls in {iteration} iterations"
                    )

                # ── 如果迴圈因為 max iterations 或全失敗而結束，
                #    強制做最後一次 API 呼叫（不帶 tools）讓 Claude 合成最終回覆 ──
                if (
                    (response.stop_reason == "tool_use" or all_tools_failed_break)
                    and total_tool_calls > 0
                ):
                    if all_tools_failed_break:
                        logger.info(
                            "工具全部失敗，強制合成回覆（不再執行工具）"
                        )
                    else:
                        logger.info(
                            f"Tool-use hit max iterations ({MAX_TOOL_ITERATIONS}), "
                            "forcing final response without tools"
                        )
                        # 只有非 break 的情況才需要再執行最後一輪工具
                        last_tool_results = []
                        for block in response.content:
                            if block.type == "tool_use":
                                result = await self._tool_executor.execute(
                                    tool_name=block.name,
                                    arguments=block.input,
                                )
                                is_err = not result.get("success", False)
                                if is_err:
                                    err_msg = result.get("error", "未知錯誤")
                                    r_str = (
                                        f"[工具執行失敗] {block.name}: {err_msg}\n"
                                        f"請用繁體中文向使用者說明情況。"
                                    )
                                else:
                                    r_str = json.dumps(result, ensure_ascii=False)
                                    if len(r_str) > 8000:
                                        r_str = r_str[:8000] + '..."}'
                                last_tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": r_str,
                                    "is_error": is_err,
                                })

                        if last_tool_results:
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
                                "content": last_tool_results,
                            })

                    # 不帶 tools 的最終呼叫 — v10: 行動導向合成提示
                    synth_messages = messages.copy()
                    synth_hint = (
                        "請根據上面的工具結果，用繁體中文完整回答我的問題。"
                        "如果有產出檔案，告知使用者檔案已準備好。"
                        "回覆最後包含一個具體的可操作下一步。"
                        if not all_tools_failed_break
                        else "工具執行過程中遇到了問題。"
                              "請根據上面的錯誤訊息，用繁體中文向我說明發生了什麼，"
                              "並提供具體的替代方案（如：用其他工具、手動步驟等）。"
                    )
                    synth_messages.append({
                        "role": "user",
                        "content": synth_hint,
                    })
                    _synth_resp = await self._llm_adapter.call(
                        system_prompt=system_prompt,
                        messages=synth_messages,
                        model=model,
                        max_tokens=self._MAX_TOKENS_PRIMARY,
                    )
                    response = APICompatResponse(_synth_resp)

                # 提取最終文字回覆
                text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text += block.text

                # ── v10.5: 偵測 max_tokens 截斷 ──
                # 當 API 回應因 max_tokens 被截斷時，Claude 自己不知道，
                # 使用者會收到不完整的回覆。這裡主動偵測並附加提示。
                if getattr(response, "stop_reason", None) == "max_tokens":
                    logger.warning(
                        f"Response truncated by max_tokens "
                        f"(output_tokens={getattr(response.usage, 'output_tokens', '?')})"
                    )
                    text += "\n\n———\n⚠️ 這則回覆因長度限制被截斷了。你可以說「繼續」讓我接著說完。"

                # 追蹤 Token 用量（含模型識別 + cache 統計）
                if self.budget_monitor and hasattr(response, "usage"):
                    try:
                        self.budget_monitor.track_usage(
                            response.usage.input_tokens,
                            response.usage.output_tokens,
                            model=model,
                        )
                        # Log cache hit info
                        cache_read = getattr(
                            response.usage, "cache_read_input_tokens", 0
                        )
                        cache_create = getattr(
                            response.usage, "cache_creation_input_tokens", 0
                        )
                        if cache_read or cache_create:
                            logger.info(
                                f"Prompt cache: read={cache_read}, "
                                f"create={cache_create}"
                            )
                            # ── 快取統計持久化（供節省報告使用）──
                            try:
                                import json as _cjson
                                cache_dir = self.data_dir / "_system" / "budget"
                                cache_dir.mkdir(parents=True, exist_ok=True)
                                cache_fp = cache_dir / f"cache_log_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
                                cache_entry = {
                                    "ts": datetime.now().isoformat(),
                                    "model": model,
                                    "cache_read": cache_read,
                                    "cache_create": cache_create,
                                    "input_tokens": response.usage.input_tokens,
                                }
                                with open(cache_fp, "a", encoding="utf-8") as cf:
                                    cf.write(_cjson.dumps(cache_entry) + "\n")
                            except Exception as e:
                                logger.debug(f"快取統計寫入失敗: {e}")
                    except Exception as e:
                        logger.debug(f"Token 用量追蹤失敗: {e}")

                # ── 路由統計記錄（P1: routing stats tracking）──
                if self._router and hasattr(response, "usage"):
                    try:
                        self._router.record_routing(
                            data_dir=self.data_dir,
                            model_used=model,
                            task_type=_route_decision.get("task_type", "unknown"),
                            reason=_route_decision.get("reason", "unknown"),
                            input_tokens=response.usage.input_tokens,
                            output_tokens=response.usage.output_tokens,
                        )
                    except Exception as e:
                        logger.debug(f"路由統計記錄失敗: {e}")

                if model != _ordered_chain[0]:
                    logger.warning(f"Fallback 到 {model} 成功（原選 {_ordered_chain[0]}）")

                # 過濾系統提示洩漏
                text = self._strip_system_leakage(text)

                # 安全網：如果 tool_use 後 text 仍為空，回退到友善訊息
                if not text.strip() and total_tool_calls > 0:
                    logger.warning(
                        f"Tool-use 回覆為空 (calls={total_tool_calls}, "
                        f"iterations={iteration})，嘗試補救"
                    )
                    # 從整個對話歷史中提取最後一段 assistant text
                    for msg in reversed(messages):
                        if msg.get("role") == "assistant":
                            c = msg.get("content", "")
                            if isinstance(c, str) and c.strip():
                                text = c.strip()
                                break
                            elif isinstance(c, list):
                                for blk in c:
                                    if isinstance(blk, dict) and blk.get("type") == "text":
                                        t = blk.get("text", "").strip()
                                        if t:
                                            text = t
                                            break
                                if text.strip():
                                    break
                    if not text.strip():
                        text = "抱歉，工具執行過程中未能產生完整回覆，請再試一次或換個方式詢問。"

                # ── LLM 呼叫成功：通知 VitalSigns 重置失敗計數 ──
                if self._governor:
                    try:
                        vs = self._governor.get_vital_signs()
                        if vs:
                            vs.on_llm_success()
                    except Exception as e:
                        logger.debug(f"VitalSigns.on_llm_success 失敗: {e}")

                return text

            except Exception as e:
                last_error = e
                logger.warning(f"模型 {model} 呼叫失敗: {e}")
                continue

        # 所有模型都失敗 → 離線模式
        logger.error(f"所有模型都失敗，進入離線模式。最後錯誤: {last_error}")
        return self._offline_response(messages, error_msg=str(last_error))

    def _build_cached_system(self, system_prompt: str) -> List[Dict]:
        """將 system prompt 分為 static/dynamic blocks 並標記 cache_control.

        BDD Spec §14: static_core (DNA27 核心) 標記
        cache_control: {"type": "ephemeral"}。
        """
        # 用分隔符切割 static core vs dynamic sections
        separator = "\n\n---\n\n"
        parts = system_prompt.split(separator)

        if len(parts) <= 1:
            # 無法分割 → 整段標記 cache
            return [{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }]

        # 第一段 = DNA27 核心（static，跨 turn 不變）
        static_core = parts[0]
        dynamic_text = separator.join(parts[1:])

        blocks = [
            {
                "type": "text",
                "text": static_core,
                "cache_control": {"type": "ephemeral"},
            },
        ]

        if dynamic_text.strip():
            blocks.append({
                "type": "text",
                "text": dynamic_text,
            })

        return blocks

    async def _call_llm_with_model(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 8192,
    ) -> str:
        """指定模型的精簡 LLM 呼叫 — 無 fallback chain + Prompt Caching.

        用於 dispatch 系統的 orchestrator / worker / synthesis 呼叫，
        需要精確控制模型選擇。

        P5 修復：強制繁體中文輸出（貫穿所有子系統）

        Args:
            system_prompt: 系統提示詞
            messages: 對話訊息
            model: 指定模型 ID
            max_tokens: 最大回覆 token 數

        Returns:
            回覆文字（失敗時返回空字串）
        """
        # NOTE: dispatch 內部呼叫不做 SafetyAnchor 檢查
        # 主要 _call_llm() 已經檢查完整 system_prompt
        # dispatch sub-prompt 是內部指令，不含 "真實優先" 等錨點

        if not self._llm_adapter:
            return ""

        # P5 修復：強制繁體中文輸出設定
        # 在 system_prompt 末尾追加語言強制要求（如果還沒有的話）
        if "繁體中文" not in system_prompt and "Traditional Chinese" not in system_prompt:
            system_prompt = system_prompt.rstrip() + "\n\n【強制規則】必須使用繁體中文回覆。"

        try:
            adapter_resp = await self._llm_adapter.call(
                system_prompt=system_prompt,
                messages=messages,
                model=model,
                max_tokens=max_tokens,
            )

            if adapter_resp.stop_reason == "error":
                logger.error(f"_call_llm_with_model({model}) adapter error: {adapter_resp.text}")
                return ""

            text = adapter_resp.text

            # 追蹤用量
            if self.budget_monitor:
                try:
                    self.budget_monitor.track_usage(
                        adapter_resp.input_tokens,
                        adapter_resp.output_tokens,
                        model=model,
                    )
                except Exception as e:
                    logger.debug(f"BudgetMonitor.track_usage 失敗: {e}")

            return text

        except Exception as e:
            logger.error(f"_call_llm_with_model({model}) failed: {e}", exc_info=True)
            return ""

    # ═══════════════════════════════════════════
    # 離線回覆 + 對話歷史管理
    # ═══════════════════════════════════════════

    def _offline_response(
        self, messages: List[Dict[str, str]], error_msg: str = ""
    ) -> str:
        """離線模式 — 純 CPU 回覆.

        不呼叫任何 LLM，基於本地記憶和規則回覆。
        注意：離線回覆不應被存入 session 歷史，
        避免垃圾數據（如 chaos test 產出）被持久化並污染後續對話。
        呼叫端應設定 _offline_flag 讓 process() 跳過歷史儲存。
        """
        self._offline_flag = True  # 標記此次為離線回覆

        # ── Sentinel 觸發：推送離線告警 ──
        if self._governor:
            try:
                vs = self._governor.get_vital_signs()
                if vs:
                    try:
                        loop = asyncio.get_running_loop()
                        asyncio.ensure_future(vs.on_offline_triggered(error_msg))
                    except RuntimeError:
                        # 無 running loop（同步 / daemon thread 情境）→ 新 thread 建立隔離 loop
                        # 避免在呼叫方 thread 上直接 asyncio.run()，防止跨 loop 物件衝突
                        def _trigger_offline(_coro=vs.on_offline_triggered(error_msg)) -> None:
                            try:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                try:
                                    loop.run_until_complete(_coro)
                                finally:
                                    loop.close()
                            except Exception as cleanup_e:
                                logger.debug(f"Event loop cleanup failed: {cleanup_e}")
                        threading.Thread(target=_trigger_offline, daemon=True).start()
            except Exception as _e:
                logger.debug(f"Sentinel trigger failed (non-critical): {_e}")

        # 只取最後一條 user 訊息，忽略之前的 assistant 回覆
        user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_msg = msg.get("content", "")
                break

        # 載入 ANIMA_MC 取得名字
        anima_mc = self._load_anima_mc()
        name = "MUSEON"
        if anima_mc:
            name = anima_mc.get("identity", {}).get("name", "MUSEON")

        return (
            f"目前無法連線到 AI 服務。你的訊息已記錄。\n"
            f"等連線恢復後我會重新處理。\n\n"
            f"收到的訊息：「{user_msg[:100]}」"
        )

    # ═══════════════════════════════════════════
    # 對話歷史管理
    # ═══════════════════════════════════════════

    def _get_session_history(self, session_id: str) -> List[Dict[str, str]]:
        """取得或建立 session 的對話歷史.

        v10.5: 磁碟持久化 — 如果 in-memory 為空，嘗試從磁碟載入。
        避免 gateway 重啟後使用者的對話歷史全部遺失。
        """
        if session_id not in self._sessions:
            # 嘗試從磁碟載入
            loaded = self._load_session_from_disk(session_id)
            self._sessions[session_id] = loaded if loaded else []
        return self._sessions[session_id]

    def _load_session_from_disk(self, session_id: str) -> Optional[List[Dict]]:
        """從磁碟載入 session history（如果存在）.

        包含汙染偵測：過濾掉異常長的訊息（可能來自 chaos test 或其他注入）。
        v1.55: 相容舊格式（純陣列）和新格式（metadata + messages）。
        """
        session_file = self.data_dir / "_system" / "sessions" / f"{session_id}.json"
        if not session_file.exists():
            return None
        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))

            # v1.55: 相容兩種格式
            if isinstance(data, dict) and "messages" in data:
                # 新格式：{ "metadata": {...}, "messages": [...] }
                messages = data.get("messages", [])
            elif isinstance(data, list):
                # 舊格式：直接陣列
                messages = data
            else:
                return None

            # 汙染偵測：過濾異常長或重複模式的訊息
            clean = []
            stripped = 0
            for msg in messages:
                content = msg.get("content", "")
                # 超過 5000 字元且包含高度重複模式 → 視為汙染
                if len(content) > 5000:
                    # 檢查是否有重複子串（取前 50 字元看是否反覆出現）
                    sample = content[:50]
                    if content.count(sample) > 3:
                        stripped += 1
                        continue
                clean.append(msg)
            if stripped:
                logger.warning(
                    f"Session {session_id[:8]}... 清除 {stripped} 條汙染訊息"
                )
                # 回寫清理後的資料（用新格式）
                from datetime import datetime as _dt
                payload = {
                    "metadata": {
                        "last_active": _dt.now().isoformat(),
                    },
                    "messages": clean,
                }
                session_file.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            logger.info(
                f"Session {session_id[:8]}... 從磁碟載入 {len(clean)} 條歷史"
            )
            return clean
        except Exception as e:
            logger.warning(f"載入 session history 失敗: {e}")
        return None

    def _save_session_to_disk(self, session_id: str) -> None:
        """將 session history 持久化到磁碟.

        每輪對話結束後呼叫。只保存 role + content（純文字），
        不保存工具中間訊息（tool_use/tool_result blocks）。

        v1.55: 加入 metadata 層追蹤 last_active 時間戳（用於自動清理機制）。
        """
        history = self._sessions.get(session_id)
        if not history:
            return
        session_dir = self.data_dir / "_system" / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        session_file = session_dir / f"{session_id}.json"
        try:
            # 只保存可序列化的純文字訊息
            clean = []
            for msg in history:
                content = msg.get("content", "")
                if isinstance(content, str):
                    clean.append({"role": msg["role"], "content": content})
                # 跳過 content 為 list（tool_use blocks）的訊息

            # v1.55: 包裝成 metadata + messages 結構
            from datetime import datetime as _dt
            payload = {
                "metadata": {
                    "last_active": _dt.now().isoformat(),
                },
                "messages": clean,
            }
            session_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=1),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"保存 session history 失敗: {e}")

    def _pre_compact_flush(
        self,
        session_id: str,
        dropping: List[Dict[str, str]],
    ) -> None:
        """Pre-compaction flush — 上下文被截斷前，萃取重要資訊寫入每日記憶.

        Inspired by OpenClaw 的 pre-compaction memory flush +
        Claude Code 的 auto memory (MEMORY.md) 模式。

        萃取策略（純 CPU，不呼叫 LLM）：
        1. 使用者的關鍵請求（>20 字的 user 訊息）
        2. AI 回覆中的關鍵片段（前 100 字 + 匹配的 skill 名稱）
        3. 寫入 data/memory/YYYY-MM-DD.md (append-only)
        """
        if not dropping:
            return

        try:
            memory_dir = self.data_dir / "memory"
            memory_dir.mkdir(parents=True, exist_ok=True)

            today = datetime.now().strftime("%Y-%m-%d")
            daily_log = memory_dir / f"{today}.md"

            entries = []
            now_iso = datetime.now().strftime("%H:%M")
            entries.append(f"\n## Session {session_id[:8]} — flush at {now_iso}\n")

            for msg in dropping:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if not content:
                    continue

                if role == "user" and len(content) > 20:
                    # 萃取使用者請求（截斷到 200 字）
                    snippet = content[:200].replace("\n", " ")
                    entries.append(f"- **user**: {snippet}")
                elif role == "assistant" and len(content) > 50:
                    # 萃取 AI 回覆摘要（前 100 字）
                    snippet = content[:100].replace("\n", " ")
                    entries.append(f"- **ai**: {snippet}...")

            if len(entries) > 1:  # 至少有 header + 1 entry
                with open(daily_log, "a", encoding="utf-8") as f:
                    f.write("\n".join(entries) + "\n")
                logger.info(
                    f"Pre-compact flush: {len(entries)-1} entries → {daily_log.name}"
                )

            # 情感訊號偵測 → RELATIONSHIP_SIGNAL
            self._detect_relationship_signals(dropping)

        except Exception as e:
            logger.warning(f"Pre-compact flush 失敗: {e}")

    # ═══════════════════════════════════════════
    # 記憶持久化 + 知識結晶 + 技能追蹤
    # ═══════════════════════════════════════════

    async def _persist_memory(
        self,
        session_id: str,
        user_content: str,
        assistant_content: str,
        matched_skills: List[str],
    ) -> None:
        """持久化到四通道記憶."""
        now = datetime.now()
        ts = now.isoformat()

        # Event Channel: 發生了什麼
        self.memory_store.write({
            "channel": "event",
            "timestamp": ts,
            "trust_level": "TRUSTED",
            "content": {
                "event_type": "user_interaction",
                "session_id": session_id,
                "user_message": user_content[:200],
                "matched_skills": ", ".join(matched_skills),
            },
        })

        # Meta-Thinking Channel: 我怎麼思考的
        self.memory_store.write({
            "channel": "meta-thinking",
            "timestamp": ts,
            "trust_level": "TRUSTED",
            "content": {
                "thought_pattern": f"DNA27 matched: {', '.join(matched_skills) or 'general'}",
                "reasoning": f"User asked about: {user_content[:100]}",
                "outcome": "responded",
                "confidence": 0.8,
            },
        })

        # Outcome Channel: 結果指標
        self.memory_store.write({
            "channel": "outcome",
            "timestamp": ts,
            "trust_level": "VERIFIED",
            "content": {
                "task_id": f"{session_id}_{now.strftime('%H%M%S')}",
                "result": "success",
                "response_length": len(assistant_content),
                "skills_used": ", ".join(matched_skills),
            },
        })

    # ═══════════════════════════════════════════
    # 知識結晶計數更新
    # ═══════════════════════════════════════════

    def _update_crystal_count(self, new_count: int) -> None:
        """更新 ANIMA_MC 中的知識結晶計數.

        ★ 通過 WriteQueue 序列化 + AnimaMCStore.update() 原子讀改寫
        """
        def _do_update():
            try:
                def updater(data):
                    mem = data.get("memory_summary", {})
                    mem["knowledge_crystals"] = mem.get("knowledge_crystals", 0) + new_count
                    data["memory_summary"] = mem
                    return data
                self._anima_mc_store.update(updater)
            except Exception as e:
                logger.warning(f"更新結晶計數失敗: {e}")

        if self._wq:
            self._wq.enqueue("crystal_count_update", _do_update)
        else:
            _do_update()

    # ═══════════════════════════════════════════
    # 技能使用追蹤（WEE/Morphenix）
    # ═══════════════════════════════════════════

    def _track_skill_usage(
        self,
        skill_names: List[str],
        user_content: str,
        response_length: int,
        outcome: str = "",
    ) -> None:
        """追蹤技能使用，供 WEE/Morphenix 自我迭代.

        Args:
            outcome: 執行結果 ("success" / "partial" / "failed" / "")
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "skills": skill_names,
            "trigger_message": user_content[:100],
            "response_length": response_length,
            "outcome": outcome,
        }
        self._skill_usage_log.append(entry)

        # 持久化到磁碟（每 10 次寫入一次）
        if len(self._skill_usage_log) % 10 == 0:
            self._flush_skill_usage()

    def _flush_skill_usage(self) -> None:
        """將技能使用紀錄寫入磁碟."""
        log_path = self.data_dir / "skill_usage_log.jsonl"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                for entry in self._skill_usage_log:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._skill_usage_log.clear()
        except Exception as e:
            logger.error(f"Failed to flush skill usage log: {e}", exc_info=True)
