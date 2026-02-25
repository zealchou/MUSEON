"""Internal message format for Gateway."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Literal


@dataclass
class InternalMessage:
    """
    Unified internal message format.

    All external messages (Telegram, LINE, Webhook, Electron) are converted
    to this format before processing.
    """

    source: str  # telegram, line, webhook, electron
    session_id: str  # Unique identifier for this conversation session
    user_id: str  # User identifier from the source platform
    content: str  # Message content
    timestamp: datetime  # When the message was received
    trust_level: Literal["core", "verified", "external", "untrusted"]
    metadata: Dict[str, Any]  # Additional platform-specific data

    def __post_init__(self) -> None:
        """Validate message fields."""
        if not self.source:
            raise ValueError("source cannot be empty")
        if not self.session_id:
            raise ValueError("session_id cannot be empty")
        if not self.user_id:
            raise ValueError("user_id cannot be empty")
        if not self.content:
            raise ValueError("content cannot be empty")
        if self.trust_level not in ["core", "verified", "external", "untrusted"]:
            raise ValueError(f"Invalid trust_level: {self.trust_level}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source": self.source,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "trust_level": self.trust_level,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InternalMessage":
        """Create InternalMessage from dictionary."""
        return cls(
            source=data["source"],
            session_id=data["session_id"],
            user_id=data["user_id"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            trust_level=data["trust_level"],
            metadata=data.get("metadata", {}),
        )
