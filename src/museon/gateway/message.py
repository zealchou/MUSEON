"""Internal message format for Gateway.

v9.0: Added Artifact + BrainResponse for execution layer support.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal


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


# ═══════════════════════════════════════════
# v9.0: 執行層支援 — Artifact + BrainResponse
# ═══════════════════════════════════════════


@dataclass
class Artifact:
    """Brain 產出的可交付物.

    當 LLM 使用 generate_artifact 工具時，產出的檔案會以
    Artifact 形式附加到 BrainResponse 中，最終透過 Telegram
    的 send_document 傳送給使用者。

    Types:
        document — .md / .html（計畫書、報告、企劃）
        template — .md / .txt（範本、SOP、文案）
        data     — .json / .csv（分析數據、排程表）
        link     — 外部連結（API 文件、工具推薦）
    """

    type: str           # "document" | "template" | "data" | "link"
    filename: str       # "business_plan.md", "ig_calendar.csv"
    content: str        # workspace 檔案路徑（text-based）或 URL（link type）
    mime_type: str      # "text/markdown", "text/csv", "text/html"
    description: str    # 給使用者看的一句話描述

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON/event payloads."""
        return {
            "type": self.type,
            "filename": self.filename,
            "content": self.content,
            "mime_type": self.mime_type,
            "description": self.description,
        }


@dataclass
class BrainResponse:
    """Brain 回覆的完整結構（v9.0）.

    升級 brain.process() 的返回值：
    - text: 對話回覆（原 str）
    - artifacts: 可交付物列表（檔案/連結）

    向後相容：所有消費端透過 isinstance 判斷：
    - isinstance(result, str) → 舊行為
    - isinstance(result, BrainResponse) → 新行為
    """

    text: str
    artifacts: List[Artifact] = field(default_factory=list)

    def has_artifacts(self) -> bool:
        """是否有附件."""
        return len(self.artifacts) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON/event payloads."""
        return {
            "text": self.text,
            "artifacts": [a.to_dict() for a in self.artifacts],
        }
