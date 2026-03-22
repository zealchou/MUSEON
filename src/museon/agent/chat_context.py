"""ChatContext — Brain 每回合的顯式上下文物件.

L2-S1: 消滅 self._current_metadata 等 7+ 個隱性 per-turn 變數，
改為顯式傳遞的 dataclass。所有方法從 ctx.xxx 取值，
IDE type checking 能提供自動完成，避免 NameError 等隱性狀態 Bug。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ChatContext:
    """單次 chat() 呼叫的完整上下文.

    由 Brain.chat() 開頭建立，傳入需要上下文的方法。
    取代 self._current_metadata / self._is_group_session 等 per-turn 變數。
    """

    # ── 來源資訊 ──
    metadata: Optional[Dict[str, Any]] = None
    source: str = ""
    session_id: str = ""
    user_id: str = ""

    # ── 群組上下文 ──
    is_group_session: bool = False
    group_sender: str = ""

    @property
    def group_id(self) -> str:
        """回傳群組 ID（非群組時為空字串）."""
        if self.metadata and self.is_group_session:
            return str(self.metadata.get("group_id", ""))
        return ""

    @property
    def chat_scope(self) -> str:
        """回傳 memory recall 用的 scope filter."""
        gid = self.group_id
        return f"group:{gid}" if gid else ""

    # ── 模式標記 ──
    skillhub_mode: Optional[str] = None  # "skill_builder" / "workflow_executor"
    self_modification_detected: bool = False
    current_source: str = ""

    # ── 收集器（per-turn 累積）──
    pending_artifacts: List[Any] = field(default_factory=list)

    # ── 路由結果（chat 過程中填入）──
    multiagent_auxiliaries: List[Any] = field(default_factory=list)

    @classmethod
    def from_chat_args(
        cls,
        metadata: Optional[Dict[str, Any]] = None,
        source: str = "",
        session_id: str = "",
        user_id: str = "",
    ) -> "ChatContext":
        """從 chat() 的參數建立 ChatContext."""
        is_group = bool(metadata and metadata.get("is_group"))
        group_sender = (metadata or {}).get("sender_name", "")

        # SkillHub 模式偵測
        skillhub_mode = None
        if source == "dashboard" and session_id.startswith("dashboard_skill_builder"):
            skillhub_mode = "skill_builder"
        elif source == "dashboard" and session_id.startswith("dashboard_workflow"):
            skillhub_mode = "workflow_executor"

        # 自我修改偵測
        self_mod = False
        if source in ("claude_code", "mcp"):
            self_mod = True

        return cls(
            metadata=metadata,
            source=source,
            session_id=session_id,
            user_id=user_id,
            is_group_session=is_group,
            group_sender=group_sender,
            skillhub_mode=skillhub_mode,
            self_modification_detected=self_mod,
            current_source=source,
        )
