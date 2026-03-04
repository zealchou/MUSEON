"""
Memory Fusion Module

Fuses daily memories across four channels:
- meta_thinking: Strategic insights
- event: What happened
- outcome: Results and consequences
- user_reaction: Boss's feedback

Uses LLM to synthesize cross-channel insights.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryFusion:
    """Handles memory fusion across four channels."""

    def __init__(self, memory_store, llm_client):
        """
        Initialize memory fusion.

        Args:
            memory_store: Memory store instance
            llm_client: LLM client for fusion processing
        """
        self.memory_store = memory_store
        self.llm_client = llm_client

    async def fuse_daily_memories(self, date: str) -> Dict[str, Any]:
        """
        Fuse memories from a specific date across all four channels.

        Args:
            date: Date string in ISO format (YYYY-MM-DD)

        Returns:
            Dict containing fusion results and insights
        """
        logger.info(f"Fusing memories for date: {date}")

        # Load daily log from all channels
        daily_data = await self.memory_store.load_daily_log(date)

        # Check if there's data to process
        if not self._has_data(daily_data):
            logger.info(f"No data to fuse for {date}")
            return {
                "status": "skipped",
                "reason": "no_data",
                "date": date
            }

        # Extract channel data
        channels = self._extract_channels(daily_data)

        # Generate fusion prompt
        fusion_prompt = self._create_fusion_prompt(date, channels)

        # Call LLM for fusion
        try:
            response = await self.llm_client.invoke(
                messages=[{
                    "role": "user",
                    "content": fusion_prompt
                }],
                model="haiku",  # Use Haiku for fusion (cost-effective)
                max_tokens=1000
            )

            insights = response.get("content", "")
            token_usage = response.get("usage", {})

            # Save fused insights
            await self._save_fusion_results(date, insights, channels)

            return {
                "status": "success",
                "date": date,
                "insights": insights,
                "channels_processed": list(channels.keys()),
                "token_usage": token_usage
            }

        except Exception as e:
            logger.error(f"Fusion failed for {date}: {e}")
            return {
                "status": "failed",
                "date": date,
                "error": str(e)
            }

    def _has_data(self, daily_data: Dict[str, Any]) -> bool:
        """Check if there's any data to process."""
        if not daily_data:
            return False

        # Check if any channel has data
        for channel in ["meta_thinking", "event", "outcome", "user_reaction", "conversations"]:
            if daily_data.get(channel) and len(daily_data[channel]) > 0:
                return True

        return False

    def _extract_channels(self, daily_data: Dict[str, Any]) -> Dict[str, List[Any]]:
        """Extract data from each channel."""
        channels = {}

        channel_names = ["meta_thinking", "event", "outcome", "user_reaction"]

        for channel in channel_names:
            if channel in daily_data and daily_data[channel]:
                channels[channel] = daily_data[channel]

        # Also include conversations as context
        if "conversations" in daily_data and daily_data["conversations"]:
            channels["conversations"] = daily_data["conversations"]

        return channels

    def _create_fusion_prompt(self, date: str, channels: Dict[str, List[Any]]) -> str:
        """
        Create fusion prompt for LLM.

        Args:
            date: Date being processed
            channels: Data from each channel

        Returns:
            Fusion prompt string
        """
        prompt_parts = [
            f"# 記憶融合任務 - {date}",
            "",
            "你是 MUSEON 的記憶融合引擎。請分析以下四個記憶通道的資料，產出綜合洞見。",
            "",
            "## 目標",
            "- 找出跨通道的關聯模式",
            "- 提煉可行動的洞見",
            "- 識別需要注意的趨勢",
            "",
            "## 四通道資料",
            ""
        ]

        # Add each channel's data
        for channel_name, items in channels.items():
            prompt_parts.append(f"### {channel_name.replace('_', ' ').title()}")
            prompt_parts.append(f"共 {len(items)} 筆資料:")

            # Add first few items as examples (to avoid token overflow)
            for i, item in enumerate(items[:5], 1):
                item_str = str(item)[:200]  # Truncate long items
                prompt_parts.append(f"{i}. {item_str}")

            if len(items) > 5:
                prompt_parts.append(f"... 以及其他 {len(items) - 5} 筆")

            prompt_parts.append("")

        prompt_parts.extend([
            "## 請產出",
            "1. 關鍵洞見（3-5 條）",
            "2. 跨通道關聯（如果有）",
            "3. 需要注意的模式或趨勢",
            "4. 可行動的建議",
            "",
            "以簡潔的中文條列式回答。"
        ])

        return "\n".join(prompt_parts)

    async def _save_fusion_results(
        self,
        date: str,
        insights: str,
        channels: Dict[str, List[Any]]
    ) -> None:
        """
        Save fusion results to memory.

        Args:
            date: Date of fusion
            insights: Fused insights text
            channels: Original channel data
        """
        fusion_entry = {
            "type": "memory_fusion",
            "date": date,
            "timestamp": datetime.now().isoformat(),
            "insights": insights,
            "channels_count": {
                channel: len(items)
                for channel, items in channels.items()
            }
        }

        # Save to memory store
        await self.memory_store.save_memory(
            channel="meta_thinking",
            content=f"[記憶融合 {date}]\n{insights}",
            metadata=fusion_entry
        )

        logger.info(f"Fusion results saved for {date}")

    async def fuse_weekly_memories(self, end_date: str = None) -> Dict[str, Any]:
        """
        Fuse memories from the past week.

        Args:
            end_date: End date for weekly fusion (defaults to today)

        Returns:
            Weekly fusion results
        """
        if end_date is None:
            end_date = datetime.now().date().isoformat()

        # Fuse each day
        results = []
        for i in range(7):
            date = (datetime.fromisoformat(end_date).date() - timedelta(days=i)).isoformat()
            daily_result = await self.fuse_daily_memories(date)
            results.append(daily_result)

        # Count successes
        successful = sum(1 for r in results if r.get("status") == "success")

        return {
            "status": "completed",
            "end_date": end_date,
            "days_processed": 7,
            "successful_fusions": successful,
            "results": results
        }
