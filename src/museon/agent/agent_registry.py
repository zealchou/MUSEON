"""Agent Registry -- MUSEON's unified capability catalog.

Maps all available agents (internal Skills, external tools, external AI agents)
into a unified registry. The PDR Council's ACTION verdicts use this to dispatch
proactive actions.

Registry data: data/_system/agent_registry.json
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentCapability:
    """A single agent/tool/skill in the registry."""

    id: str  # "skill:brand-identity" | "tool:gmail" | "agent:openclaw"
    type: str  # "internal_skill" | "tool" | "external_agent"
    name: str  # human-readable name
    capabilities: List[str] = field(default_factory=list)
    cost_tier: str = "free"  # "free" | "low" | "medium" | "high"
    latency_range: str = "1-5s"
    trigger_patterns: List[str] = field(default_factory=list)
    api_config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AgentRegistry:
    """Unified registry of all MUSEON-callable agents."""

    def __init__(self, data_dir: str = ""):
        self._agents: Dict[str, AgentCapability] = {}
        self._data_dir = data_dir
        self._persist_path = Path(data_dir) / "_system" / "agent_registry.json" if data_dir else None

    def register(self, agent: AgentCapability) -> None:
        """Register an agent capability."""
        self._agents[agent.id] = agent

    def get(self, agent_id: str) -> Optional[AgentCapability]:
        """Get agent by ID."""
        return self._agents.get(agent_id)

    def find_by_type(self, agent_type: str) -> List[AgentCapability]:
        """Find all agents of a given type."""
        return [a for a in self._agents.values() if a.type == agent_type and a.enabled]

    def find_by_capability(self, capability: str) -> List[AgentCapability]:
        """Find agents that have a specific capability."""
        return [a for a in self._agents.values() if capability in a.capabilities and a.enabled]

    def summarize(self, max_chars: int = 1000) -> str:
        """Generate a concise summary of available capabilities for LLM prompts."""
        lines = []
        for a in sorted(self._agents.values(), key=lambda x: x.type):
            if not a.enabled:
                continue
            caps = ", ".join(a.capabilities[:3])
            lines.append(f"- {a.name}（{a.type}）: {caps}")
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n..."
        return text

    def load(self) -> None:
        """Load registry from persistent storage."""
        if self._persist_path and self._persist_path.exists():
            try:
                with open(self._persist_path) as f:
                    data = json.load(f)
                for item in data.get("agents", []):
                    agent = AgentCapability(**item)
                    self._agents[agent.id] = agent
                logger.info(f"[AgentRegistry] Loaded {len(self._agents)} agents")
            except Exception as e:
                logger.warning(f"[AgentRegistry] Load failed: {e}")

    def save(self) -> None:
        """Save registry to persistent storage."""
        if self._persist_path:
            try:
                self._persist_path.parent.mkdir(parents=True, exist_ok=True)
                data = {"agents": [a.to_dict() for a in self._agents.values()]}
                with open(self._persist_path, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"[AgentRegistry] Save failed: {e}")

    def register_builtin_tools(self) -> None:
        """Register built-in MCP tools."""
        builtins = [
            AgentCapability(
                id="tool:gmail",
                type="tool",
                name="Gmail",
                capabilities=["email_search", "email_read", "email_draft"],
                cost_tier="free",
                latency_range="1-3s",
                trigger_patterns=["email", "信件", "信箱", "Gmail", "寄信"],
            ),
            AgentCapability(
                id="tool:gcal",
                type="tool",
                name="Google Calendar",
                capabilities=["calendar_query", "event_create", "free_time"],
                cost_tier="free",
                latency_range="1-3s",
                trigger_patterns=["日曆", "行程", "會議", "明天", "下週", "幾點"],
            ),
            AgentCapability(
                id="tool:telegram",
                type="tool",
                name="Telegram",
                capabilities=["message_send", "message_edit", "file_send"],
                cost_tier="free",
                latency_range="<1s",
            ),
            AgentCapability(
                id="tool:web_search",
                type="tool",
                name="Web Search",
                capabilities=["web_search", "web_fetch"],
                cost_tier="free",
                latency_range="2-5s",
                trigger_patterns=["搜尋", "查一下", "找資料", "最新"],
            ),
        ]
        for agent in builtins:
            self.register(agent)

    def register_external_agents(self) -> None:
        """Register external AI agents (placeholder interfaces)."""
        externals = [
            AgentCapability(
                id="agent:openclaw",
                type="external_agent",
                name="Openclaw",
                capabilities=["web_search", "code_execution", "multi_model", "deep_research"],
                cost_tier="medium",
                latency_range="3-30s",
                trigger_patterns=["深度研究", "代碼執行", "多模型"],
                enabled=False,  # placeholder until API configured
            ),
            AgentCapability(
                id="agent:claude_cowork",
                type="external_agent",
                name="Claude Cowork",
                capabilities=["collaborative_writing", "brainstorming", "document_edit"],
                cost_tier="low",
                latency_range="5-20s",
                trigger_patterns=["協作", "一起寫", "腦力激盪"],
                enabled=False,
            ),
            AgentCapability(
                id="agent:claude_channels",
                type="external_agent",
                name="Claude Channels",
                capabilities=["multi_channel_message", "channel_management"],
                cost_tier="free",
                latency_range="1-5s",
                enabled=False,
            ),
        ]
        for agent in externals:
            self.register(agent)

    def register_internal_skills(self, skill_names: List[str]) -> None:
        """Register MUSEON internal skills from the skill catalog."""
        for name in skill_names:
            self.register(AgentCapability(
                id=f"skill:{name}",
                type="internal_skill",
                name=name,
                capabilities=[name],
                cost_tier="free",
                latency_range="5-30s",
            ))


# Singleton
_instance: Optional[AgentRegistry] = None


def init_agent_registry(data_dir: str, skill_names: Optional[List[str]] = None) -> AgentRegistry:
    """Initialize the global agent registry."""
    global _instance
    _instance = AgentRegistry(data_dir)
    _instance.load()
    _instance.register_builtin_tools()
    _instance.register_external_agents()
    if skill_names:
        _instance.register_internal_skills(skill_names)
    _instance.save()
    logger.info(f"[AgentRegistry] Initialized with {len(_instance._agents)} agents")
    return _instance


def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry."""
    global _instance
    if _instance is None:
        _instance = AgentRegistry()
        _instance.register_builtin_tools()
        _instance.register_external_agents()
    return _instance
