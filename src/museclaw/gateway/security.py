"""Security Gate - HMAC validation, rate limiting, input sanitization."""

import hmac
import hashlib
import re
import time
from collections import defaultdict
from typing import Dict, List


class SecurityGate:
    """
    Layer 1-2 security: HMAC validation, rate limiting, input sanitization.

    This is the first line of defense before messages enter the Gateway.
    """

    # Dangerous patterns that indicate command injection or malicious input
    DANGEROUS_PATTERNS = [
        r"\$\(",  # Command substitution $(...)
        r"`",  # Backtick command execution
        r"(rm|cat|curl|wget|nc|bash|sh|python)\s+-[a-zA-Z]",  # Commands with flags
        r";\s*(rm|cat|curl|wget|nc|bash|sh|python)",  # Command chaining
        r"&&\s*(rm|cat|curl|wget|nc|bash|sh|python|malicious)",  # Command chaining with &&
        r"\|\s*(nc|bash|sh)",  # Piping to dangerous commands
        r"DROP\s+TABLE",  # SQL injection
        r"<script",  # XSS
        r"javascript:",  # XSS
        r"\.\./",  # Path traversal
    ]

    def __init__(
        self,
        hmac_secret: str = "default_secret_change_me",
        rate_limit_per_minute: int = 60,
    ) -> None:
        self._hmac_secret = hmac_secret
        self._rate_limit = rate_limit_per_minute
        self._rate_tracker: Dict[str, List[float]] = defaultdict(list)

    def validate_hmac(self, payload: bytes, signature: str) -> bool:
        """
        Validate HMAC signature.

        Args:
            payload: The raw message payload
            signature: The HMAC signature to validate

        Returns:
            True if signature is valid, False otherwise
        """
        expected = hmac.new(self._hmac_secret.encode(), payload, hashlib.sha256).hexdigest()

        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected, signature)

    def check_rate_limit(self, user_id: str) -> bool:
        """
        Check if user is within rate limit.

        Args:
            user_id: The user identifier

        Returns:
            True if within limit, False if exceeded
        """
        now = time.time()
        cutoff = now - 60  # 1 minute ago

        # Remove old timestamps
        self._rate_tracker[user_id] = [ts for ts in self._rate_tracker[user_id] if ts > cutoff]

        # Check limit
        if len(self._rate_tracker[user_id]) >= self._rate_limit:
            return False

        # Add current timestamp
        self._rate_tracker[user_id].append(now)
        return True

    def sanitize_input(self, content: str) -> str:
        """
        Sanitize and validate input content.

        Args:
            content: The input content to sanitize

        Returns:
            The sanitized content

        Raises:
            ValueError: If content contains suspicious patterns
        """
        # Check for dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                raise ValueError(f"Suspicious pattern detected: {pattern}")

        # Additional length check
        if len(content) > 50000:  # 50KB limit
            raise ValueError("Content too large")

        return content

    def validate_source(self, source: str) -> bool:
        """
        Validate that source is from allowed list.

        Args:
            source: The message source

        Returns:
            True if source is allowed, False otherwise
        """
        allowed_sources = ["telegram", "line", "webhook", "electron", "heartbeat", "cron"]
        return source in allowed_sources
