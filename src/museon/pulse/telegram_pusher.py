"""
Telegram 推送器 - 处理主动敲门的消息发送
"""

import asyncio
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class TelegramPusher:
    """通过 Telegram Bot API 推送消息"""
    
    def __init__(self, user_id: int, bot_token: str):
        self.user_id = user_id
        self.bot_token = bot_token
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
        self.history_file = Path(__file__).parent.parent.parent / "data" / "workspace" / "push_history.jsonl"
    
    MAX_TG_LEN = 4096  # Telegram 單則訊息上限

    async def send_message(self, text: str) -> bool:
        """发送消息到用户（P0-3：超长自动分段）"""
        try:
            import aiohttp

            parts = self._split_long_text(text)
            async with aiohttp.ClientSession() as session:
                for i, part in enumerate(parts):
                    url = f"{self.api_url}/sendMessage"
                    data = {
                        "chat_id": self.user_id,
                        "text": part,
                        "parse_mode": "Markdown"
                    }
                    async with session.post(url, json=data, timeout=10) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            if i == len(parts) - 1:
                                self._log_push(text, True, result)
                            logger.info(f"✅ Message part {i+1}/{len(parts)} sent to {self.user_id}")
                        else:
                            self._log_push(text, False, await resp.text())
                            logger.error(f"❌ Failed to send part {i+1}: {resp.status}")
                            return False
                    if i < len(parts) - 1:
                        await asyncio.sleep(0.15)
            return True

        except Exception as e:
            self._log_push(text, False, str(e))
            logger.error(f"❌ Error: {e}")
            return False

    @staticmethod
    def _split_long_text(text: str, max_len: int = 4096) -> list:
        """将超长文字按段落边界切分."""
        if not text or len(text) <= max_len:
            return [text] if text else []
        chunks = []
        remaining = text
        while remaining:
            if len(remaining) <= max_len:
                chunks.append(remaining)
                break
            cut = remaining[:max_len].rfind("\n\n")
            if cut < 500:
                cut = remaining[:max_len].rfind("\n")
            if cut < 500:
                cut = max_len
            chunk = remaining[:cut].rstrip()
            remaining = remaining[cut:].lstrip()
            if chunk:
                chunks.append(chunk)
        return chunks
    
    def _log_push(self, text: str, success: bool, response: Any):
        """记录推送历史"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "user_id": self.user_id,
            "success": success,
            "message_length": len(text),
            "response": str(response)[:200]  # 截断长回应
        }
        
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

class ProactivePushManager:
    """主动推送管理器"""
    
    def __init__(self):
        self.config_file = Path(__file__).parent.parent.parent / "data" / "workspace" / "proactive_config.json"
        self.config = self._load_config()
        self.pusher = TelegramPusher(
            user_id=self.config["telegram_user_id"],
            bot_token=self.config["telegram_bot_token"]
        )
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置"""
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    async def push_proactive_message(self, message: str) -> bool:
        """推送主动消息"""
        if not self.config.get("enabled"):
            logger.warning("⚠️  ProactivePush is disabled")
            return False
        
        return await self.pusher.send_message(message)
    
    async def test_push(self) -> bool:
        """测试推送（用于验证配置）"""
        test_message = """
🤖 **MUSEON 主动敲门系统已激活！**

您现在会收到我的主动提醒：
• 待完成的承诺提醒
• 系统状态异常通知  
• 主动观察和建议

**配置：**
• 敲门间隔: 30 分钟
• 活跃时段: 08:00 - 01:00
• 日敲门上限: 5 次

欢迎回到有心跳的世界 💓
        """
        return await self.pusher.send_message(test_message)

if __name__ == "__main__":
    import sys
    
    async def main():
        manager = ProactivePushManager()
        success = await manager.test_push()
        if success:
            print("\n✅ 测试推送成功！")
            print("你应该在 Telegram 中收到一条激活消息。")
        else:
            print("\n❌ 测试推送失败")
            print("请检查 Telegram Bot Token 和网络连接。")
        
        sys.exit(0 if success else 1)
    
    asyncio.run(main())
