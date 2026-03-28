"""Channel adapters for external platforms."""

from museon.channels.base import ChannelAdapter, TrustLevel
from museon.channels.telegram import TelegramAdapter
from museon.channels.webhook import WebhookAdapter

__all__ = [
    "ChannelAdapter",
    "TrustLevel",
    "TelegramAdapter",
    "WebhookAdapter",
]

# Lazy imports for optional adapters (avoid ImportError if deps missing)


def get_slack_adapter():
    from museon.channels.slack import SlackAdapter
    return SlackAdapter


def get_discord_adapter():
    from museon.channels.discord import DiscordAdapter
    return DiscordAdapter


def get_email_adapter():
    from museon.channels.email import EmailAdapter
    return EmailAdapter


def get_mqtt_adapter():
    from museon.channels.mqtt import MQTTAdapter
    return MQTTAdapter


def get_community_adapter():
    from museon.channels.community import CommunityAdapter
    return CommunityAdapter
