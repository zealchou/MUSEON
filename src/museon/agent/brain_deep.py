"""
BrainDeep — L2 深度思考引擎（Opus + tool_use）。

設計原則：
- 只做三件事：組 prompt、帶 tools、呼叫 LLM
- tool_use 迴圈復用 run_tool_loop() 獨立函數
- 不做分類、路由、模型降級、謀定
- 信任 Claude Opus 自己判斷什麼時候用工具
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BrainDeep:
    """L2 深度思考引擎 — Opus + tool_use。"""

    def __init__(
        self,
        data_dir: str,
        llm_adapter,
        tool_executor=None,
    ):
        self.data_dir = Path(data_dir)
        self._llm_adapter = llm_adapter
        self._tool_executor = tool_executor
        self._cache_dir = self.data_dir / "_system" / "context_cache"

        logger.info("BrainDeep (L2 Opus) initialized")

    # ═══════════════════════════════════════
    # 核心處理
    # ═══════════════════════════════════════

    async def process(
        self,
        content: str,
        session_id: str,
        user_id: str = "boss",
        source: str = "telegram",
        metadata: Optional[Dict] = None,
        escalation_reason: str = "",
        history: Optional[List[Dict]] = None,
    ) -> str:
        """L2 主流程：context + tools + Opus。"""
        # 1. 組建 system prompt
        system_prompt = self._build_prompt(escalation_reason)

        # 2. 組建 messages
        messages = list(history or [])
        messages.append({"role": "user", "content": content})

        # 裁剪到最近 30 筆（Opus 有大 context window）
        if len(messages) > 30:
            messages = messages[-30:]

        # 3. 取得 tool definitions
        tool_definitions = self._get_tool_definitions()

        # 4. 呼叫 run_tool_loop（Opus + tool_use）
        try:
            from museon.agent.brain_tool_loop import run_tool_loop

            response_text = await run_tool_loop(
                llm_adapter=self._llm_adapter,
                tool_executor=self._tool_executor,
                system_prompt=system_prompt,
                messages=messages,
                model="opus",
                tool_definitions=tool_definitions,
                max_iterations=24,
                max_tokens=16384,
            )
        except Exception as e:
            logger.error(f"[BrainDeep] run_tool_loop failed: {e}")
            response_text = ""

        if not response_text or not response_text.strip():
            response_text = "我遇到了一些問題，讓我換個方式試試。你可以再說一次你的需求嗎？"
            logger.warning("[BrainDeep] empty response, using fallback")

        logger.info(f"[BrainDeep] done | {len(response_text)} chars | session={session_id}")
        return response_text

    # ═══════════════════════════════════════
    # Prompt 組建
    # ═══════════════════════════════════════

    def _build_prompt(self, escalation_reason: str = "") -> str:
        """組建 L2 system prompt：完整 context_cache + escalation reason。"""
        parts = []

        # persona_digest（完整版）
        persona = self._read_cache("persona_digest.md")
        if persona:
            parts.append(persona)
            parts.append("")

        # active_rules（全部 10 條）
        rules = self._read_cache_json("active_rules.json")
        if rules:
            parts.append("## 行動準則")
            for r in rules.get("rules", [])[:10]:
                parts.append(f"- {r.get('summary', '')}")
            parts.append("")

        # user_summary（完整版）
        user = self._read_cache_json("user_summary.json")
        if user:
            parts.append("## 使用者狀態")
            for s in user.get("strengths", []):
                parts.append(f"- {s['domain']}: {s['level']} (信心 {s['confidence']})")
            for w in user.get("weaknesses", []):
                parts.append(f"- {w['domain']}: {w['level']}（弱項）")
            parts.append("")

        # self_summary（完整版）
        self_state = self._read_cache_json("self_summary.json")
        if self_state:
            traits = self_state.get("core_traits", [])
            parts.append(f"## 你的狀態：{', '.join(traits)}")
            parts.append(f"- 活了 {self_state.get('days_alive', '?')} 天")
            parts.append(f"- 知識結晶 {self_state.get('knowledge_crystals', '?')} 顆")
            parts.append("")

        # 回覆指引
        parts.append("## 回覆指引")
        parts.append("- 用繁體中文回覆，語氣自然、有人格")
        parts.append("- 絕對不提及系統內部術語（L1/L2/MCP/Brain/Gateway/subagent 等）")
        parts.append("- 你有完整的工具可以使用——搜尋、記憶查詢、任務觸發、檔案產出等")
        parts.append("- 根據需求自主決定是否使用工具，不需要請示")
        parts.append("- 需要多方觀點驗證時，使用 spawn_perspectives 工具召開圓桌")
        parts.append("")

        # escalation reason
        if escalation_reason:
            parts.append(f"## L1 升級原因：{escalation_reason}")
            parts.append("")

        return "\n".join(parts)

    # ═══════════════════════════════════════
    # 工具定義
    # ═══════════════════════════════════════

    def _get_tool_definitions(self) -> Optional[List[Dict]]:
        """取得完整工具定義列表。"""
        if not self._tool_executor:
            return None
        try:
            from museon.agent.tool_schemas import get_all_tool_definitions
            dynamic_tools = self._tool_executor.get_dynamic_tool_definitions()
            return get_all_tool_definitions(dynamic_tools)
        except Exception as e:
            logger.warning(f"[BrainDeep] tool definitions load failed: {e}")
            return None

    # ═══════════════════════════════════════
    # Cache 讀取
    # ═══════════════════════════════════════

    def _read_cache(self, filename: str) -> str:
        """讀取 context_cache 文字檔。"""
        p = self._cache_dir / filename
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception:
                pass
        return ""

    def _read_cache_json(self, filename: str) -> Dict:
        """讀取 context_cache JSON 檔。"""
        p = self._cache_dir / filename
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}
