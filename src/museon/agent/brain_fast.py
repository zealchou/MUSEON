"""
BrainFast — L1 接待層（Sonnet）。

設計原則：
- 讀 context_cache + 歷史 → 呼叫 Sonnet（不帶 tool_use）
- Sonnet 自己判斷能回就回，需要深度就輸出 escalation JSON
- Python 只做解析，不做分流判斷
- 每次重讀 pending_insights（L4 回饋迴路）
- 回覆後 fire-and-forget L4 觀察者
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BrainFast:
    """L1 接待層：Sonnet + escalation JSON。"""

    def __init__(self, data_dir: str, llm_adapter=None):
        self.data_dir = Path(data_dir)
        self._llm_adapter = llm_adapter
        self._cache_dir = self.data_dir / "_system" / "context_cache"

        # 啟動時讀一次 persona_digest（不常變，可快取）
        self._persona_digest = self._read_cache("persona_digest.md")

        # 從 ANIMA_MC 取名字
        self._boss_name = "使用者"
        self._museon_name = "MUSEON"
        mc_path = self.data_dir / "ANIMA_MC.json"
        if mc_path.exists():
            try:
                mc = json.loads(mc_path.read_text(encoding="utf-8"))
                self._boss_name = mc.get("boss", {}).get("name", "使用者")
                self._museon_name = mc.get("identity", {}).get("name", "MUSEON")
            except Exception:
                pass

        # Session 歷史 in-memory 快取
        self._sessions: Dict[str, List[Dict[str, str]]] = {}

        # InputSanitizer（可選）
        self._input_sanitizer = None
        try:
            from museon.agent.input_sanitizer import InputSanitizer
            self._input_sanitizer = InputSanitizer()
        except Exception:
            pass

        # 命名儀式
        self._ceremony = None
        try:
            from museon.agent.ceremony import NamingCeremony
            ceremony_path = self.data_dir / "ANIMA_MC.json"
            if ceremony_path.exists():
                mc = json.loads(ceremony_path.read_text(encoding="utf-8"))
                if not mc.get("ceremony", {}).get("completed", False):
                    self._ceremony = NamingCeremony(str(self.data_dir))
        except Exception:
            pass

        # L2 BrainDeep（lazy init）
        self._deep_brain = None

        logger.info(
            f"BrainFast v2 (L1 Sonnet) initialized | "
            f"persona={len(self._persona_digest)}chars | name={self._museon_name}"
        )

    # ═══════════════════════════════════════
    # 核心處理
    # ═══════════════════════════════════════

    async def process(
        self,
        content: str,
        session_id: str,
        user_id: str = "",
        source: str = "telegram",
        metadata: Optional[Dict] = None,
    ) -> str:
        """L1 主流程：Sonnet 自主判斷 + escalation。"""
        _start = time.time()
        _report = (metadata or {}).get("_progress_cb") or (lambda s, d="": None)

        # ── Step 1: 命名儀式（早返回）──
        if self._ceremony and self._ceremony.is_ceremony_needed():
            try:
                return await self._handle_ceremony(content, session_id)
            except Exception as e:
                logger.warning(f"Ceremony failed: {e}")

        # ── Step 2: InputSanitizer（安全邊界）──
        _report("🛡️ 安全檢查", "InputSanitizer 掃描")
        if self._input_sanitizer:
            try:
                _trusted_ids = {
                    "boss",
                    *[uid.strip() for uid in os.environ.get("TELEGRAM_TRUSTED_IDS", "").split(",") if uid.strip()],
                }
                trust = "TRUSTED" if user_id in _trusted_ids else "UNKNOWN"
                scan = await self._input_sanitizer.sanitize(content=content, source=source, trust_level=trust)
                if not scan["is_safe"]:
                    logger.warning(f"InputSanitizer blocked: {scan['threats_detected']}")
                    return "我注意到這則訊息包含一些我無法處理的內容。如果你有其他問題，歡迎換個方式問我。"
            except Exception as e:
                logger.debug(f"InputSanitizer failed (passthrough): {e}")

        # ── Step 3: 組建 prompt（每次重讀 L4 回饋）──
        _report("📝 組建提示詞", "載入人格 + 規則 + 記憶")
        system_prompt = self._build_prompt(session_id)

        # ── Step 4: 讀歷史 + 呼叫 Sonnet（不帶 tool_use）──
        _report("💬 Sonnet 思考中", "等待 AI 回應...")
        history = self._get_history(session_id)
        messages = list(history)
        messages.append({"role": "user", "content": content})

        if len(messages) > 20:
            messages = messages[-20:]

        response_text = ""
        try:
            if self._llm_adapter:
                resp = await self._llm_adapter.call(
                    system_prompt=system_prompt,
                    messages=messages,
                    model="sonnet",
                    max_tokens=4096,
                )
                response_text = resp.text if resp and resp.text else ""
        except Exception as e:
            logger.error(f"[L1] Sonnet call failed: {e}")

        # ── Step 5: 解析 escalation 信號 ──
        _report("🔀 解析回應", "判斷是否需要深度分析")
        escalation = self._parse_escalation(response_text)

        if escalation:
            reason = escalation.get("reason", "")
            _report("🧠 升級到深度分析", f"L2 接手：{reason[:30]}")
            logger.info(f"[L1] escalating to L2 | reason: {reason}")

            # 委派給 L2 BrainDeep（Opus）
            deep_response = await self._delegate_to_l2(
                content, session_id, user_id, source, metadata,
                escalation_reason=reason,
                history=history,
            )
            if deep_response:
                response_text = deep_response
            else:
                # L2 失敗，fallback：用 escalation JSON 後面的等待訊息
                lines = response_text.strip().split("\n", 1)
                response_text = lines[1].strip() if len(lines) > 1 else "讓我想想..."
                # 嘗試 legacy fallback
                legacy = await self._legacy_fallback(content, session_id, user_id, source, metadata)
                if legacy:
                    response_text = legacy
        else:
            # L1 直接回覆（去掉可能的 JSON 殘留）
            response_text = response_text.strip()

        # 兜底
        if not response_text or not response_text.strip():
            response_text = "你好！有什麼我可以幫你的嗎？"
            logger.warning("[L1] empty response, using fallback")

        # ── Step 6: 寫歷史 ──
        history.append({"role": "user", "content": content})
        history.append({"role": "assistant", "content": response_text})
        self._save_history(session_id, history)

        _elapsed = time.time() - _start
        _layer = "L2→L1" if escalation else "L1"
        logger.info(f"[{_layer}] done in {_elapsed:.1f}s | {len(response_text)} chars | session={session_id}")

        _report("✅ 完成", "準備發送回覆...")

        # ── Step 7: L4 觀察者（fire-and-forget）──
        asyncio.ensure_future(
            self._observe(session_id, user_id, content, response_text)
        )

        # ── Step 8: 清空已消費的 pending_insights ──
        self._consume_insights()

        return response_text

    # ═══════════════════════════════════════
    # Prompt 組建（每次重讀 L4 回饋）
    # ═══════════════════════════════════════

    def _build_prompt(self, session_id: str) -> str:
        """組建 L1 system prompt：context_cache + L4 回饋 + escalation 指引。"""
        parts = []

        # 基礎身份
        parts.append(f"你是 {self._museon_name}，{self._boss_name} 的 AI 夥伴。")
        parts.append("用繁體中文自然回覆。不提及任何系統內部術語。")
        parts.append("")

        # persona_digest
        if self._persona_digest:
            parts.append(self._persona_digest)
            parts.append("")

        # active_rules（每次重讀，Top-5）
        rules = self._read_cache_json("active_rules.json")
        if rules:
            parts.append("## 行動準則")
            for r in rules.get("rules", [])[:5]:
                parts.append(f"- {r.get('summary', '')}")
            parts.append("")

        # user_summary（每次重讀，L4 可能更新了）
        user = self._read_cache_json("user_summary.json")
        if user:
            strengths = user.get("strengths", [])
            if strengths:
                domains = [f"{s['domain']}({s['level']})" for s in strengths[:3]]
                parts.append(f"## 使用者專長：{', '.join(domains)}")
                parts.append("")

        # self_summary
        self_state = self._read_cache_json("self_summary.json")
        if self_state:
            traits = self_state.get("core_traits", [])
            if traits:
                parts.append(f"## 你的特質：{', '.join(traits)}")
                parts.append("")

        # L4 回饋：pending_insights（每次重讀）
        insights = self._read_pending_insights()
        if insights:
            parts.append("## 背景觀察提示（來自上次互動）")
            parts.append("只有在與當前對話自然相關時才融入回覆，不相關就忽略：")
            for ins in insights[:5]:
                parts.append(f"- [{ins.get('type', '?')}] {ins.get('content', '')[:100]}")
            parts.append("")

        # Escalation 機制
        parts.append("## 重要：Escalation 機制")
        parts.append("如果你判斷這則訊息需要以下任何能力，你必須在回覆的**第一行**輸出 JSON，然後換行寫一句簡短等待訊息：")
        parts.append('{"escalate": true, "reason": "簡述原因"}')
        parts.append("")
        parts.append("需要 escalate 的情境：")
        parts.append("- 需要搜尋網路或查詢記憶")
        parts.append("- 需要深度分析、比較、推演、多步驟推理")
        parts.append("- 需要產出文件、報告、計畫")
        parts.append("- 需要執行任務（出晨報、跑腳本等）")
        parts.append("- 涉及 /指令")
        parts.append("- 你不確定的事實性問題")
        parts.append("- 需要查詢外部服務")
        parts.append("")
        parts.append("不需要 escalate（你直接回）：")
        parts.append("- 招呼、問候、告別、簡單確認")
        parts.append("- 情緒表達、表情符號、閒聊")
        parts.append("- 你能根據人格準則直接回答的問題")
        parts.append("")

        return "\n".join(parts)

    # ═══════════════════════════════════════
    # Escalation 解析
    # ═══════════════════════════════════════

    def _parse_escalation(self, response_text: str) -> Optional[Dict]:
        """解析 L1 回覆中的 escalation JSON 信號。"""
        if not response_text:
            return None
        first_line = response_text.strip().split("\n", 1)[0].strip()
        if not first_line.startswith("{"):
            return None
        try:
            signal = json.loads(first_line)
            if signal.get("escalate"):
                return signal
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    # ═══════════════════════════════════════
    # L2 委派
    # ═══════════════════════════════════════

    async def _delegate_to_l2(
        self, content: str, session_id: str, user_id: str,
        source: str, metadata: Optional[Dict],
        escalation_reason: str = "", history: Optional[List] = None,
    ) -> Optional[str]:
        """委派給 L2 BrainDeep（Opus + tool_use）。"""
        try:
            if self._deep_brain is None:
                from museon.agent.brain_deep import BrainDeep
                from museon.gateway.server import _get_brain
                legacy = _get_brain()
                self._deep_brain = BrainDeep(
                    data_dir=str(self.data_dir),
                    llm_adapter=legacy._llm_adapter,
                    tool_executor=legacy._tool_executor,
                )

            resp = await self._deep_brain.process(
                content=content,
                session_id=session_id,
                user_id=user_id,
                source=source,
                metadata=metadata,
                escalation_reason=escalation_reason,
                history=history,
            )
            if resp and resp.strip():
                logger.info(f"[L1→L2] delegation success, {len(resp)} chars")
                return resp
        except Exception as e:
            logger.warning(f"[L1→L2] BrainDeep failed: {e}")
        return None

    async def _legacy_fallback(
        self, content: str, session_id: str, user_id: str,
        source: str, metadata: Optional[Dict],
    ) -> Optional[str]:
        """Legacy fallback — 當 BrainDeep 失敗時回退到 brain.py。"""
        try:
            from museon.gateway.server import _get_brain
            legacy = _get_brain()
            resp = await legacy.process(
                content=content, session_id=session_id,
                user_id=user_id, source=source, metadata=metadata or {},
            )
            text = resp.text if hasattr(resp, "text") else str(resp) if resp else ""
            if text and text.strip():
                logger.info(f"[L1] legacy fallback success, {len(text)} chars")
                return text
        except Exception as e:
            logger.warning(f"[L1] legacy fallback also failed: {e}")
        return None

    # ═══════════════════════════════════════
    # L4 觀察者
    # ═══════════════════════════════════════

    async def _observe(
        self, session_id: str, user_id: str,
        user_message: str, museon_reply: str,
    ):
        """L4 背景觀察：四管道即時學習。"""
        try:
            from museon.agent.brain_observer import observe
            await observe(
                data_dir=self.data_dir,
                session_id=session_id,
                user_id=user_id,
                user_message=user_message,
                museon_reply=museon_reply,
                llm_adapter=self._llm_adapter,
            )
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"[L4] error (non-fatal): {e}")

    # ═══════════════════════════════════════
    # L4 回饋讀取
    # ═══════════════════════════════════════

    def _read_pending_insights(self) -> List[Dict]:
        """讀取 L4 寫入的 pending_insights。"""
        fp = self._cache_dir / "pending_insights.json"
        if fp.exists():
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                return data.get("insights", [])
            except Exception:
                pass
        return []

    def _consume_insights(self):
        """清空已消費的 pending_insights。"""
        fp = self._cache_dir / "pending_insights.json"
        if fp.exists():
            try:
                fp.write_text(
                    json.dumps({"updated_at": datetime.now().isoformat(), "insights": []},
                               ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass

    # ═══════════════════════════════════════
    # Cache 讀取
    # ═══════════════════════════════════════

    def _read_cache(self, filename: str) -> str:
        p = self._cache_dir / filename
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception:
                pass
        return ""

    def _read_cache_json(self, filename: str) -> Dict:
        p = self._cache_dir / filename
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    # ═══════════════════════════════════════
    # 歷史管理
    # ═══════════════════════════════════════

    def _get_history(self, session_id: str) -> list:
        if session_id in self._sessions:
            return list(self._sessions[session_id])

        history = []
        session_path = self.data_dir / "_system" / "sessions" / f"{session_id}.json"
        if session_path.exists():
            try:
                data = json.loads(session_path.read_text(encoding="utf-8"))
                raw_history = data.get("history", [])
                history = raw_history[-20:]
            except Exception as e:
                logger.warning(f"[L1] History load failed: {e}")

        self._sessions[session_id] = history
        return list(history)

    def _save_history(self, session_id: str, history: list):
        if len(history) > 40:
            history = history[-40:]

        self._sessions[session_id] = history

        session_path = self.data_dir / "_system" / "sessions" / f"{session_id}.json"
        try:
            if session_path.exists():
                data = json.loads(session_path.read_text(encoding="utf-8"))
            else:
                data = {}
            data["history"] = history
            data["updated_at"] = datetime.now().isoformat()
            session_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[L1] History save failed: {e}")

    # ═══════════════════════════════════════
    # 命名儀式
    # ═══════════════════════════════════════

    async def _handle_ceremony(self, content: str, session_id: str) -> str:
        if not self._ceremony:
            return ""
        try:
            result = self._ceremony.process_response(content)
            if result.get("completed"):
                self._ceremony = None
                self._persona_digest = self._read_cache("persona_digest.md")
            return result.get("response", "")
        except Exception as e:
            logger.warning(f"Ceremony error: {e}")
            return "命名儀式遇到問題，請再試一次。"

    # ═══════════════════════════════════════
    # 相容性方法（供外部呼叫）
    # ═══════════════════════════════════════

    def reload_context_cache(self):
        """重新載入 persona（nightly 或手動更新後）。"""
        self._persona_digest = self._read_cache("persona_digest.md")
        logger.info("BrainFast: persona reloaded")

    def reload_persona(self):
        """相容性別名。"""
        self.reload_context_cache()
