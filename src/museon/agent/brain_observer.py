"""
BrainObserver — Layer 2 背景觀察引擎。

設計原則：
- 不阻塞回覆，fire-and-forget
- 失敗靜默，不影響 Layer 1
- < 100 行（功能凍結警戒線）
- 唯一產出：寫入 pending_sayings

觀察什麼：
- 對話中值得記住的事（承諾、日期、情緒變化）
- 使用者可能需要的主動提醒
- 對話品質觀察（回覆是否足夠）
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_OBSERVER_PROMPT = """你是 MUSEON 的背景觀察系統。你的工作是觀察最近的對話，找出值得記住或主動提起的事。

規則：
1. 只輸出 0-2 條洞察，每條一行，格式：[類型] 內容
2. 類型只有：reminder（提醒）、insight（洞察）、concern（關心）
3. 如果對話平淡無奇，什麼都不輸出（輸出「無」）
4. 不要重複對話中已經說過的事
5. 不要輸出系統術語或技術細節

範例輸出：
[reminder] 使用者提到下週四要開會，可以在那天早上提醒
[concern] 使用者連續幾次提到累，可以適時關心

如果沒有值得記錄的，輸出：
無
"""


async def observe(
    session_id: str,
    recent_history: list[dict],
    llm_adapter=None,
) -> None:
    """背景觀察一輪對話，產出洞察寫入 pending_sayings。

    這個函數應該被 fire-and-forget 呼叫（asyncio.create_task）。
    """
    if not llm_adapter or len(recent_history) < 2:
        return

    try:
        # 組建觀察 prompt
        conv_text = "\n".join(
            f"{'使用者' if m['role'] == 'user' else 'MUSEON'}: {m['content'][:200]}"
            for m in recent_history[-10:]
        )

        resp = await asyncio.wait_for(
            llm_adapter.call(
                system_prompt=_OBSERVER_PROMPT,
                messages=[{"role": "user", "content": f"最近對話：\n{conv_text}"}],
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
            ),
            timeout=10.0,
        )

        text = resp.text.strip() if resp and resp.text else ""
        if not text or text == "無":
            return

        # 解析洞察
        from museon.agent.pending_sayings import add_insight
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("[") and "]" in line:
                bracket_end = line.index("]")
                insight_type = line[1:bracket_end].strip()
                content = line[bracket_end + 1:].strip()
                if content and insight_type in ("reminder", "insight", "concern"):
                    add_insight(
                        session_id=session_id,
                        content=content,
                        priority="high" if insight_type == "concern" else "medium",
                        insight_type=insight_type,
                    )

        logger.info(f"[Observer] completed for {session_id}")

    except asyncio.TimeoutError:
        logger.debug("[Observer] timeout, skipping")
    except Exception as e:
        logger.debug(f"[Observer] failed (silent): {e}")
