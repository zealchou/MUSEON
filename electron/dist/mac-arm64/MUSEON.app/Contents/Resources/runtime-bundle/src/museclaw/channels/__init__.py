"""Channel adapters for external platforms."""

from museclaw.channels.base import ChannelAdapter, TrustLevel
from museclaw.channels.electron import ElectronAdapter
from museclaw.channels.telegram import TelegramAdapter
from museclaw.channels.webhook import WebhookAdapter

__all__ = [
    "ChannelAdapter",
    "TrustLevel",
    "TelegramAdapter",
    "WebhookAdapter",
    "ElectronAdapter",
]
