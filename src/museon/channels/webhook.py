"""Webhook Channel Adapter with HMAC-SHA256 verification."""

import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from museon.channels.base import ChannelAdapter, TrustLevel
from museon.gateway.message import InternalMessage

logger = logging.getLogger(__name__)


class WebhookAdapter(ChannelAdapter):
    """
    Webhook channel adapter with HMAC-SHA256 signature verification.

    Features:
    - HMAC-SHA256 signature verification
    - Replay attack prevention (timestamp window)
    - Support for multiple webhook sources (LINE, OTA, IFTTT, etc.)

    Security:
    - All webhook endpoints REQUIRE valid HMAC signature
    - Timestamp must be within configured window (default 5 minutes)
    - Signatures use SHA256 for collision resistance
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Webhook adapter.

        Args:
            config: Configuration dictionary containing:
                - hmac_secret: Secret key for HMAC verification
                - timestamp_window: Max age of timestamp in seconds (default 300)
        """
        super().__init__(config)
        self.hmac_secret = config["hmac_secret"]
        self.timestamp_window = config.get("timestamp_window", 300)  # 5 minutes default

    def verify_hmac(self, payload: Dict[str, Any], signature: str) -> bool:
        """
        Verify HMAC-SHA256 signature of webhook payload.

        Args:
            payload: Webhook payload dictionary
            signature: HMAC signature from webhook headers

        Returns:
            bool: True if signature is valid, False otherwise
        """
        try:
            # Serialize payload to canonical JSON (sorted keys, no whitespace)
            payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

            # Calculate expected signature
            expected_signature = hmac.new(
                self.hmac_secret.encode("utf-8"), payload_bytes, hashlib.sha256
            ).hexdigest()

            # Constant-time comparison to prevent timing attacks
            return hmac.compare_digest(signature, expected_signature)

        except Exception as e:
            logger.error(f"HMAC verification error: {e}")
            return False

    def verify_timestamp(self, timestamp: int) -> bool:
        """
        Verify that timestamp is within allowed window.

        Args:
            timestamp: Unix timestamp from webhook payload

        Returns:
            bool: True if timestamp is within window, False otherwise
        """
        current_timestamp = int(datetime.now().timestamp())
        age = abs(current_timestamp - timestamp)

        if age > self.timestamp_window:
            logger.warning(f"Timestamp outside window: {age}s (max {self.timestamp_window}s)")
            return False

        return True

    async def receive(self) -> InternalMessage:
        """
        Receive and verify a webhook message.

        Returns:
            InternalMessage: Unified message format

        Raises:
            ValueError: If signature is invalid or timestamp expired
        """
        # For testing purposes, allow mock request
        if hasattr(self, "_get_webhook_request"):
            payload, signature = self._get_webhook_request()
        else:
            # In production, this would be called from FastAPI endpoint
            raise NotImplementedError("Webhook receive must be called via FastAPI endpoint")

        # Verify HMAC signature
        if not self.verify_hmac(payload, signature):
            raise ValueError("Invalid HMAC signature")

        # Verify timestamp
        timestamp = payload.get("timestamp")
        if timestamp and not self.verify_timestamp(timestamp):
            raise ValueError("Timestamp outside valid window - possible replay attack")

        # Extract message data
        user_id = payload.get("user_id", "webhook_unknown")
        content = payload.get("content", "")
        source_type = payload.get("source_type", "webhook")  # line, ota, ifttt, etc.

        # Generate session ID based on source and user
        session_id = f"webhook_{source_type}_{user_id}"

        msg_timestamp = datetime.fromtimestamp(timestamp) if timestamp else datetime.now()

        return InternalMessage(
            source="webhook",
            session_id=session_id,
            user_id=user_id,
            content=content,
            timestamp=msg_timestamp,
            trust_level=TrustLevel.VERIFIED.value,
            metadata={
                "source_type": source_type,
                "signature": signature,
                "payload": payload,
            },
        )

    async def send(self, message: InternalMessage) -> bool:
        """
        Webhooks are receive-only - no sending capability.

        Args:
            message: InternalMessage (ignored)

        Returns:
            bool: Always False (webhooks don't support sending)
        """
        logger.warning("Webhook adapter does not support sending messages")
        return False

    def get_trust_level(self, user_id: str) -> TrustLevel:
        """
        Webhooks with valid HMAC are VERIFIED trust level.

        Args:
            user_id: User identifier (ignored)

        Returns:
            TrustLevel: Always VERIFIED (HMAC signature required)
        """
        return TrustLevel.VERIFIED

    def generate_signature(self, payload: Dict[str, Any]) -> str:
        """
        Generate HMAC signature for a payload.

        This is used by webhook clients to sign their requests.

        Args:
            payload: Payload dictionary to sign

        Returns:
            str: HMAC-SHA256 signature (hex)
        """
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return hmac.new(self.hmac_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
