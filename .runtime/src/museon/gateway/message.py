"""Internal message format for Gateway.

v9.0: Added Artifact + BrainResponse for execution layer support.
v10.0: Added InteractionRequest/Response for cross-channel interactive choices.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional


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
    interaction: Optional["InteractionRequest"] = None  # v10.0: 互動選項

    def has_artifacts(self) -> bool:
        """是否有附件."""
        return len(self.artifacts) > 0

    def has_interaction(self) -> bool:
        """是否需要使用者互動選擇."""
        return self.interaction is not None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON/event payloads."""
        result = {
            "text": self.text,
            "artifacts": [a.to_dict() for a in self.artifacts],
        }
        if self.interaction:
            result["interaction"] = self.interaction.to_dict()
        return result


# ═══════════════════════════════════════════
# v10.0: 跨通道互動層 — InteractionRequest/Response
# ═══════════════════════════════════════════


@dataclass
class ChoiceOption:
    """互動選項的單一選擇項.

    label: 顯示文字（LINE Quick Reply 限 20 字，建議簡短）
    value: callback 回傳值（預設 = label）
    description: 選項說明（Telegram 顯示在按鈕文字旁，Discord 顯示在 Select 下方）
    """

    label: str
    value: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if not self.value:
            self.value = self.label

    def to_dict(self) -> Dict[str, Any]:
        return {"label": self.label, "value": self.value, "description": self.description}


@dataclass
class InteractionRequest:
    """平台無關的互動請求.

    Brain / Skill 產出此物件，ChannelAdapter 負責呈現為平台原生 UI：
    - Telegram → InlineKeyboardMarkup
    - Discord  → Button / Select Menu
    - LINE     → Quick Reply / Flex Message
    - 其他     → 純文字編號清單（fallback）

    設計基準：Telegram callback_data 64 bytes 限制。
    """

    question_id: str              # 唯一 ID（建議 uuid4 hex[:12]）
    question: str                 # 問題文字
    options: List[ChoiceOption]   # 2-8 個選項
    header: str = ""              # 短標題（顯示在選項上方）
    multi_select: bool = False    # 是否允許多選
    timeout_seconds: int = 120    # 等待秒數
    allow_free_text: bool = True  # 是否提供「其他」自由輸入選項
    context: str = ""             # 來源標記（"query-clarity" / "deep-think" / "roundtable"）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "options": [o.to_dict() for o in self.options],
            "header": self.header,
            "multi_select": self.multi_select,
            "timeout_seconds": self.timeout_seconds,
            "allow_free_text": self.allow_free_text,
            "context": self.context,
        }


@dataclass
class InteractionResponse:
    """使用者對 InteractionRequest 的回應.

    selected: 選了哪些 value（單選時為 1 個元素的 list）
    free_text: 使用者選「其他」時的自由輸入
    responder_id: 誰回答的（群組場景下追蹤個人）
    channel: 來自哪個通道（telegram / discord / line）
    timed_out: 是否因超時而產生（此時 selected 為空）
    """

    question_id: str
    selected: List[str] = field(default_factory=list)
    free_text: Optional[str] = None
    responder_id: str = ""
    channel: str = ""
    timed_out: bool = False

    def get_choice_text(self) -> str:
        """取得使用者選擇的文字摘要."""
        if self.free_text:
            return self.free_text
        if self.selected:
            return ", ".join(self.selected)
        return "(未選擇)"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "selected": self.selected,
            "free_text": self.free_text,
            "responder_id": self.responder_id,
            "channel": self.channel,
            "timed_out": self.timed_out,
        }
