"""Channel adapters for external platforms."""

from museon.channels.base import ChannelAdapter, TrustLevel
from museon.channels.electron import ElectronAdapter
from museon.channels.telegram import TelegramAdapter
from museon.channels.webhook import WebhookAdapter

__all__ = [
    "ChannelAdapter",
    "TrustLevel",
    "TelegramAdapter",
    "WebhookAdapter",
    "ElectronAdapter",
]
