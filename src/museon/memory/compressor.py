"""Conversation compression to manage context window.

Implements intelligent conversation compression:
- Always preserves recent N messages
- Compresses older messages into summaries
- Extracts key insights and patterns
- Reduces token count while maintaining context

Based on plan-v7.md: nightly job includes memory fusion.
"""

from typing import List, Dict, Any, Optional


class ConversationCompressor:
    """Compresses conversation history to fit within context window."""

    def __init__(
        self,
        preserve_last_n: int = 4,
        summary_ratio: float = 0.3,
    ):
        """Initialize compressor.

        Args:
            preserve_last_n: Number of recent messages to preserve unchanged
            summary_ratio: Target compression ratio for older messages
        """
        self.preserve_last_n = preserve_last_n
        self.summary_ratio = summary_ratio

    def compress(
        self,
        conversation: List[Dict[str, str]],
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """Compress conversation history.

        Strategy:
        1. Always preserve last N messages unchanged
        2. Compress older messages into summary
        3. Extract key patterns and insights

        Args:
            conversation: List of message dicts with role and content
            max_messages: Optional max number of messages in output

        Returns:
            Compressed conversation list
        """
        if len(conversation) <= self.preserve_last_n:
            # Nothing to compress
            return conversation

        # Split into old (to compress) and recent (to preserve)
        old_messages = conversation[: -self.preserve_last_n]
        recent_messages = conversation[-self.preserve_last_n :]

        # Create summary of old messages
        summary = self._create_summary(old_messages)

        # Build compressed conversation
        compressed = []

        if summary:
            compressed.append(
                {
                    "role": "assistant",
                    "content": f"[Previous conversation summary: {summary}]",
                }
            )

        compressed.extend(recent_messages)

        return compressed

    def _create_summary(self, messages: List[Dict[str, str]]) -> str:
        """Create summary of message sequence.

        Args:
            messages: List of messages to summarize

        Returns:
            Summary string
        """
        if not messages:
            return ""

        # Extract key information
        topics = set()
        user_requests = []
        outcomes = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                # Extract user requests
                if len(content) < 200:
                    user_requests.append(content)

                # Extract topics (simple keyword extraction)
                keywords = self._extract_keywords(content)
                topics.update(keywords)

            elif role == "assistant":
                # Look for completion indicators
                if any(
                    phrase in content.lower()
                    for phrase in ["done", "completed", "here is", "created"]
                ):
                    outcomes.append("task completed")

        # Build summary
        summary_parts = []

        if topics:
            topics_str = ", ".join(list(topics)[:5])
            summary_parts.append(f"Topics: {topics_str}")

        if user_requests:
            # Include 1-2 key requests
            summary_parts.append(f"User requested: {user_requests[0]}")

        if outcomes:
            summary_parts.append(f"{len(outcomes)} tasks completed")

        summary = "; ".join(summary_parts)

        if not summary:
            summary = f"Previous {len(messages)} messages"

        return summary

    def _extract_keywords(self, text: str) -> set:
        """Extract keywords from text.

        Simple implementation: extract capitalized words and common nouns.

        Args:
            text: Text to extract from

        Returns:
            Set of keywords
        """
        keywords = set()

        # Split into words
        words = text.split()

        for word in words:
            # Remove punctuation
            word = word.strip(".,!?;:\"'()[]{}").lower()

            # Skip very short words
            if len(word) < 4:
                continue

            # Skip common words
            if word in {
                "this",
                "that",
                "with",
                "have",
                "from",
                "they",
                "would",
                "there",
                "their",
                "what",
                "about",
                "which",
                "when",
                "make",
                "like",
                "time",
                "just",
                "know",
                "take",
                "people",
            }:
                continue

            keywords.add(word)

        # Limit to top keywords
        return set(list(keywords)[:10])

    def estimate_token_count(self, messages: List[Dict[str, str]]) -> int:
        """Estimate token count of message list.

        Uses rough approximation: 1 token ≈ 4 characters.

        Args:
            messages: List of messages

        Returns:
            Estimated token count
        """
        total_chars = 0

        for msg in messages:
            content = msg.get("content", "")
            total_chars += len(content)

        # Rough estimate: 1 token ≈ 4 chars
        return total_chars // 4

    def compress_to_token_limit(
        self,
        conversation: List[Dict[str, str]],
        max_tokens: int,
    ) -> List[Dict[str, str]]:
        """Compress conversation to fit within token limit.

        Args:
            conversation: Conversation history
            max_tokens: Maximum tokens allowed

        Returns:
            Compressed conversation
        """
        current_tokens = self.estimate_token_count(conversation)

        if current_tokens <= max_tokens:
            return conversation

        # Iteratively compress until we fit
        compressed = conversation
        preserve_n = self.preserve_last_n

        while self.estimate_token_count(compressed) > max_tokens:
            # Try compressing with fewer preserved messages
            if preserve_n > 1:
                preserve_n -= 1

            old_messages = compressed[:-preserve_n] if preserve_n > 0 else compressed
            recent_messages = compressed[-preserve_n:] if preserve_n > 0 else []

            summary = self._create_summary(old_messages)

            compressed = []
            if summary:
                compressed.append(
                    {
                        "role": "assistant",
                        "content": f"[Summary: {summary}]",
                    }
                )

            compressed.extend(recent_messages)

            # Safety: don't compress to nothing
            if preserve_n == 0:
                break

        return compressed

    def extract_insights(self, conversation: List[Dict[str, str]]) -> List[str]:
        """Extract key insights from conversation for memory storage.

        Used by nightly job for knowledge crystallization.

        Args:
            conversation: Conversation history

        Returns:
            List of insight strings
        """
        insights = []

        # Look for patterns in user preferences
        user_messages = [msg for msg in conversation if msg.get("role") == "user"]

        if len(user_messages) > 2:
            # Pattern: user communication style
            avg_length = sum(len(msg.get("content", "")) for msg in user_messages) / len(
                user_messages
            )
            if avg_length < 50:
                insights.append("User prefers brief, concise communication")
            elif avg_length > 200:
                insights.append("User provides detailed context in requests")

        # Look for recurring topics
        all_keywords = set()
        for msg in user_messages:
            keywords = self._extract_keywords(msg.get("content", ""))
            all_keywords.update(keywords)

        if all_keywords:
            insights.append(f"Recurring topics: {', '.join(list(all_keywords)[:5])}")

        # Look for feedback patterns
        positive_indicators = ["great", "perfect", "love", "excellent", "thanks"]
        negative_indicators = ["wrong", "no", "not what", "incorrect", "try again"]

        feedback_msgs = [msg.get("content", "").lower() for msg in user_messages]
        positive_count = sum(
            1 for msg in feedback_msgs if any(ind in msg for ind in positive_indicators)
        )
        negative_count = sum(
            1 for msg in feedback_msgs if any(ind in msg for ind in negative_indicators)
        )

        if positive_count > negative_count:
            insights.append("User satisfaction: generally positive")
        elif negative_count > positive_count:
            insights.append("User satisfaction: needs improvement")

        return insights
