"""Security Gate - HMAC validation, rate limiting, input sanitization, tool access control."""

import hmac
import hashlib
import logging
import re
import time
from collections import defaultdict
from typing import Dict, List

logger = logging.getLogger(__name__)


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

    # ════════════════════════════════════════════════════
    # Tool Access Control（P5: 參考 openclaw dangerous-tools.ts）
    # ════════════════════════════════════════════════════

    # Gateway 層永久阻擋的工具 — 對應 guardrails.py 的 RED 分類
    GATEWAY_BLOCKED_TOOLS = {
        "modify_security",
        "delete_account",
        "delete_user_data",
        "transfer_money",
    }

    # 需要 TRUSTED 信任等級才可執行的工具
    APPROVAL_REQUIRED_TOOLS = {
        "shell_exec",
        "write_file",
        "file_write_rich",
        "delete_file",
        "create_directory",
        "send_message",
        "post_social",
        "telegram_send",
        "line_send",
        "instagram_post",
    }

    def check_tool_access(
        self, tool_name: str, source: str, trust_level: str = "UNKNOWN"
    ) -> Dict:
        """Check if a tool call should be allowed at the Gateway level.

        This runs BEFORE ToolExecutor, providing a first-pass security gate.
        Works alongside guardrails.py (Layer 4) for defense-in-depth.

        Three-tier policy integration:
        - block: 永久阻擋（同 GATEWAY_BLOCKED_TOOLS）
        - auto: VERIFIED 以上直接放行
        - ask: TRUSTED/CORE 放行，VERIFIED 需互動授權，其餘拒絕

        Args:
            tool_name: Name of the tool being called
            source: Request source (telegram, webhook, etc.)
            trust_level: Caller's trust level (TRUSTED, VERIFIED, UNKNOWN, UNTRUSTED)

        Returns:
            Dict with keys:
            - allowed: True | False | "pending"
            - reason: str
        """
        # ── Layer 0: 永久阻擋 RED 工具（不受策略影響） ──
        if tool_name in self.GATEWAY_BLOCKED_TOOLS:
            logger.warning(
                f"Gateway 工具攔截: {tool_name} 被永久阻擋 "
                f"(source={source}, trust={trust_level})"
            )
            return {
                "allowed": False,
                "reason": f"工具 '{tool_name}' 被 Gateway 安全策略永久阻擋",
            }

        # ── Layer 1: 三級授權策略 ──
        try:
            from museon.gateway.authorization import get_authorization_policy
            policy = get_authorization_policy()
            tier = policy.classify(tool_name)
        except Exception:
            # Fallback: 使用舊邏輯
            tier = None

        if tier == "block":
            logger.warning(
                f"Gateway 策略攔截: {tool_name} 被策略阻擋 "
                f"(source={source}, trust={trust_level})"
            )
            return {
                "allowed": False,
                "reason": f"工具 '{tool_name}' 被授權策略永久阻擋",
            }

        if tier == "auto":
            # auto 級：VERIFIED 以上直接放行
            if trust_level in ("TRUSTED", "CORE", "VERIFIED"):
                return {"allowed": True, "reason": "passed (auto tier)"}
            # UNKNOWN/UNTRUSTED 仍拒絕
            return {
                "allowed": False,
                "reason": f"工具 '{tool_name}' 需要至少 VERIFIED 信任等級",
            }

        if tier == "ask":
            # ask 級：TRUSTED/CORE 直接放行
            if trust_level in ("TRUSTED", "CORE"):
                return {"allowed": True, "reason": "passed (trusted)"}
            # VERIFIED 需互動授權
            if trust_level == "VERIFIED":
                logger.info(
                    f"Gateway 工具授權待定: {tool_name} "
                    f"(source={source}, trust={trust_level})"
                )
                return {
                    "allowed": "pending",
                    "reason": "awaiting_authorization",
                }
            # UNKNOWN/UNTRUSTED 拒絕
            logger.warning(
                f"Gateway 工具攔截: {tool_name} 需要 VERIFIED 以上 "
                f"(目前: {trust_level}, source={source})"
            )
            return {
                "allowed": False,
                "reason": (
                    f"工具 '{tool_name}' 需要 VERIFIED 以上信任等級 "
                    f"（目前為 {trust_level}）"
                ),
            }

        # ── Fallback: 舊邏輯（tier is None，authorization 模組未載入） ──
        if tool_name in self.APPROVAL_REQUIRED_TOOLS:
            if trust_level not in ("TRUSTED", "CORE"):
                logger.warning(
                    f"Gateway 工具攔截: {tool_name} 需要 TRUSTED 信任等級 "
                    f"(目前: {trust_level}, source={source})"
                )
                return {
                    "allowed": False,
                    "reason": (
                        f"工具 '{tool_name}' 需要 TRUSTED 信任等級 "
                        f"（目前為 {trust_level}）"
                    ),
                }

        # MCP tools: allow dynamically registered tools
        if tool_name.startswith("mcp__"):
            logger.debug(f"Gateway: MCP 工具 {tool_name} 通過 (source={source})")

        return {"allowed": True, "reason": "passed"}
