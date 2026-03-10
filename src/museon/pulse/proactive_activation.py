"""
ProactiveBridge 激活脚本
将 HeartbeatEngine 与 ProactiveBridge 连接
"""

import os
import json
from pathlib import Path
from datetime import datetime

# 配置接收者
TELEGRAM_USER_ID = 6969045906
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8570443079:AAG1EbgVr_JoAAnlNoYdt7XGFvfd9j7dyys")

class ProactiveActivation:
    """激活主动敲门系统"""
    
    def __init__(self):
        self.config_path = Path(__file__).parent.parent.parent / "data" / "workspace" / "proactive_config.json"
        self.config = {
            "enabled": True,
            "telegram_user_id": TELEGRAM_USER_ID,
            "telegram_bot_token": TELEGRAM_BOT_TOKEN,
            "push_interval_seconds": 1800,  # 30 分钟
            "active_hours_start": 8,        # 08:00
            "active_hours_end": 25,         # 01:00 next day
            "daily_push_limit": 5,          # 每天最多 5 次
            "silent_ack_threshold": 100,    # 100字以下静默
            "activated_at": datetime.now().isoformat(),
            "activated_by": "MUSEON",
            "activation_reason": "达达把拔要求激活主动敲门"
        }
    
    def save_config(self):
        """保存配置"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
        print(f"✅ 配置已保存: {self.config_path}")
    
    def verify_config(self):
        """验证配置"""
        checks = [
            ("Telegram User ID", self.config["telegram_user_id"] == 6969045906),
            ("Bot Token", len(self.config["telegram_bot_token"]) > 10),
            ("Push Interval", self.config["push_interval_seconds"] == 1800),
            ("Active Hours", self.config["active_hours_start"] < self.config["active_hours_end"]),
            ("Daily Limit", self.config["daily_push_limit"] > 0),
        ]
        
        print("\n🔍 配置验证：")
        all_pass = True
        for name, result in checks:
            status = "✅" if result else "❌"
            print(f"  {status} {name}")
            if not result:
                all_pass = False
        
        return all_pass
    
    def activate(self):
        """完整激活流程"""
        print("\n🚀 激活 MUSEON 主动敲门系统...\n")
        
        self.save_config()
        
        if self.verify_config():
            print("\n✅ 所有配置检查通过！")
            print(f"\n📊 系统参数：")
            print(f"   接收者 ID: {self.config['telegram_user_id']}")
            print(f"   敲门间隔: {self.config['push_interval_seconds']} 秒（30分钟）")
            print(f"   活跃时段: {self.config['active_hours_start']}:00 - {self.config['active_hours_end']}:00")
            print(f"   日敲门限: {self.config['daily_push_limit']} 次")
            return True
        else:
            print("\n❌ 配置验证失败")
            return False

if __name__ == "__main__":
    activation = ProactiveActivation()
    activation.activate()
