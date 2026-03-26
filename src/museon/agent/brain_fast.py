"""
BrainFast — Layer 1 即時回覆引擎。

設計理念：預設最簡，按需加深。
所有訊息都走這條路，永不失敗，1-3 秒回覆。

6 個步驟：
1. 命名儀式 / 更名攔截（早返回）
2. InputSanitizer（安全閘門）
3. 讀 persona + ANIMA identity
4. 讀歷史（最近 10-20 條）
5. 讀待說清單（有就帶入，沒有就跳過）
6. LLM 呼叫 → 寫歷史 → 回覆

不做的事：
- 不做 DNA27 路由、不做 Skill 匹配、不做結晶注入
- 不做 MultiAgent、不做 P3-Fusion、不做 Dispatch
- 不做 Q-Score 評分、不做知識晶格掃描
- 這些全部是 Layer 2（背景觀察）的事
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
    """Layer 1：極簡即時回覆引擎。"""

    def __init__(self, data_dir: str, llm_adapter=None):
        self.data_dir = Path(data_dir)
        self._llm_adapter = llm_adapter

        # 快取 persona（啟動時讀一次）
        self._persona_text = ""
        self._anima_identity = {}
        self._boss_name = "使用者"
        self._museon_name = "MUSEON"
        self._load_persona()

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

        logger.info(
            f"BrainFast initialized | persona={len(self._persona_text)}chars "
            f"| name={self._museon_name} | boss={self._boss_name}"
        )

    # ═══════════════════════════════════════
    # 初始化
    # ═══════════════════════════════════════

    def _load_persona(self):
        """載入 persona + ANIMA identity（啟動時一次）。"""
        # museon-persona.md
        persona_path = self.data_dir / "_system" / "museon-persona.md"
        if persona_path.exists():
            self._persona_text = persona_path.read_text(encoding="utf-8")[:3000]

        # ANIMA_MC
        mc_path = self.data_dir / "ANIMA_MC.json"
        if mc_path.exists():
            try:
                mc = json.loads(mc_path.read_text(encoding="utf-8"))
                self._anima_identity = mc.get("identity", {})
                self._boss_name = mc.get("boss", {}).get("name", "使用者")
                self._museon_name = self._anima_identity.get("name", "MUSEON")
                # personality
                personality = mc.get("personality", {})
                if personality:
                    traits = personality.get("core_traits", [])
                    style = personality.get("communication_style", "")
                    if traits:
                        self._persona_text += f"\n\n## 核心特質\n{', '.join(traits)}"
                    if style:
                        self._persona_text += f"\n\n## 溝通風格\n{style}"
            except Exception as e:
                logger.warning(f"ANIMA_MC 載入失敗: {e}")

    def reload_persona(self):
        """重新載入 persona（ANIMA 更新後呼叫）。"""
        self._persona_text = ""
        self._load_persona()

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
        """Layer 1 主流程：6 步直達回覆。"""
        _start = time.time()

        # ── Step 1: 命名儀式（早返回）──
        if self._ceremony and self._ceremony.is_ceremony_needed():
            try:
                return await self._handle_ceremony(content, session_id)
            except Exception as e:
                logger.warning(f"Ceremony failed: {e}")

        # ── Step 2: InputSanitizer（安全閘門）──
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

        # ── Step 3: 組建 prompt ──
        system_prompt = self._build_prompt(session_id)

        # ── Step 4: 讀歷史 ──
        history = self._get_history(session_id)
        history.append({"role": "user", "content": content})

        # 裁剪到最近 20 條
        if len(history) > 20:
            history = history[-20:]

        # ── Step 5: 呼叫 LLM（claude -p stream-json，從 assistant message 提取文字）──
        response = ""
        try:
            import subprocess as _sp
            # 組建 prompt：system + 歷史 + 當前訊息
            prompt_parts = []
            if system_prompt:
                prompt_parts.append(f"<system-instructions>\n{system_prompt}\n</system-instructions>\n")
            for m in history:
                role = m.get("role", "user")
                content = m.get("content", "")
                if role == "assistant":
                    prompt_parts.append(f"[Previous assistant response]: {content}")
                else:
                    prompt_parts.append(content)
            prompt_text = "\n".join(prompt_parts)

            proc = await asyncio.create_subprocess_exec(
                "/opt/homebrew/bin/claude", "-p",
                "--model", "sonnet",
                "--output-format", "stream-json",
                "--verbose",
                "--system-prompt", system_prompt,  # 覆蓋 CLAUDE.md 的 L1 調度員指令
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(
                proc.communicate(input=prompt_text.encode("utf-8")),
                timeout=30,
            )
            # 從 stream-json 中提取 assistant text blocks
            import json as _json
            for line in stdout.decode("utf-8", errors="replace").strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = _json.loads(line)
                    if obj.get("type") == "assistant":
                        msg = obj.get("message", {})
                        for block in msg.get("content", []):
                            if block.get("type") == "text" and block.get("text"):
                                response = block["text"]
                except _json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.error(f"[BrainFast] LLM call failed: {e}")

        # 兜底：LLM 失敗時用最基本的回覆
        if not response or not response.strip():
            response = f"你好！有什麼我可以幫你的嗎？"
            logger.warning("[BrainFast] LLM returned empty, using fallback")

        # ── Step 6: 寫歷史 ──
        history.append({"role": "assistant", "content": response})
        self._save_history(session_id, history)

        # ── Layer 2: 背景觀察（fire-and-forget）──
        try:
            from museon.agent.brain_observer import observe
            asyncio.create_task(observe(
                session_id=session_id,
                recent_history=history[-10:],
                llm_adapter=self._llm_adapter,
            ))
        except Exception:
            pass  # Layer 2 失敗靜默

        _elapsed = time.time() - _start
        logger.info(f"[BrainFast] done in {_elapsed:.1f}s | {len(response)} chars | session={session_id}")

        return response

    # ═══════════════════════════════════════
    # Prompt 組建
    # ═══════════════════════════════════════

    def _build_prompt(self, session_id: str) -> str:
        """組建極簡 system prompt：persona + ANIMA + 待說清單。"""
        parts = []

        # 基礎身份
        parts.append(f"你是 {self._museon_name}，{self._boss_name} 的 AI 夥伴。")
        parts.append("用繁體中文自然回覆。")
        parts.append("")

        # Persona
        if self._persona_text:
            parts.append(self._persona_text)
            parts.append("")

        # 待說清單
        from museon.agent.pending_sayings import get_pending
        insights = get_pending(session_id)
        if insights:
            parts.append("## 背景觀察提示")
            parts.append("以下是觀察系統發現的提示。只有在與當前對話自然相關時才融入回覆，不相關就忽略：")
            for item in insights:
                parts.append(f"- [{item['type']}] {item['content']}")
            parts.append("")

        return "\n".join(parts)

    # ═══════════════════════════════════════
    # 歷史管理
    # ═══════════════════════════════════════

    def _get_history(self, session_id: str) -> list:
        """取得 session 歷史（in-memory 快取 + 磁碟 fallback）。"""
        if session_id in self._sessions:
            return self._sessions[session_id]

        # 從磁碟載入
        history = []
        session_path = self.data_dir / "_system" / "sessions" / f"{session_id}.json"
        if session_path.exists():
            try:
                data = json.loads(session_path.read_text(encoding="utf-8"))
                raw_history = data.get("history", [])
                # 只取最近 20 條
                history = raw_history[-20:]
                logger.info(f"[BrainFast] Loaded {len(history)} history from disk for {session_id}")
            except Exception as e:
                logger.warning(f"[BrainFast] History load failed: {e}")

        self._sessions[session_id] = history
        return history

    def _save_history(self, session_id: str, history: list):
        """寫入 session 歷史到 in-memory + 磁碟。"""
        # 裁剪
        if len(history) > 40:
            history = history[-40:]

        self._sessions[session_id] = history

        # 異步寫磁碟（不阻塞回覆）
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
            logger.warning(f"[BrainFast] History save failed: {e}")

    # ═══════════════════════════════════════
    # 命名儀式
    # ═══════════════════════════════════════

    async def _handle_ceremony(self, content: str, session_id: str) -> str:
        """處理命名儀式（保留，因為這是必要的初始互動）。"""
        if not self._ceremony:
            return ""
        try:
            result = self._ceremony.process_response(content)
            if result.get("completed"):
                self._ceremony = None
                self.reload_persona()
            return result.get("response", "")
        except Exception as e:
            logger.warning(f"Ceremony error: {e}")
            return "命名儀式遇到問題，請再試一次。"
