"""通用選單配置 — 跨通道共用的選單定義.

所有通道（Telegram / LINE / Discord）共用同一份選單配置，
各通道的 adapter 負責把 MenuConfig 轉成自己的 UI 元件。

設計原則：
- 選單定義跟通道實作分離
- 全中文（台灣使用者）
- 按使用頻率和場景分組
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MenuItem:
    """單一選單項目."""
    label: str          # 按鈕顯示文字（中文）
    command: str        # 對應的 /指令
    emoji: str = ""     # 前綴 emoji
    description: str = ""  # 簡短說明（用於 Bot Commands）
    category: str = ""  # 分組


@dataclass
class MenuCategory:
    """選單分組."""
    name: str
    emoji: str
    items: list[MenuItem] = field(default_factory=list)


# ═══════════════════════════════════════
# 主選單定義（按使用頻率排序）
# ═══════════════════════════════════════

MAIN_MENU: list[MenuCategory] = [
    MenuCategory(
        name="戰略情報",
        emoji="🎯",
        items=[
            MenuItem("戰神系統", "/ares", "🎯", "人物分析＋策略建議", "strategy"),
            MenuItem("能量解讀", "/reading", "🔮", "八方位能量盤分析", "strategy"),
            MenuItem("戰略分析", "/strategy", "⚔️", "九策軍師戰略推演", "strategy"),
        ],
    ),
    MenuCategory(
        name="商業工具",
        emoji="💼",
        items=[
            MenuItem("市場分析", "/market", "📊", "多空研判＋產業分析", "business"),
            MenuItem("商模診斷", "/business", "💡", "十二力商業診斷", "business"),
            MenuItem("顧問銷售", "/ssa", "🤝", "顧問式銷售流程", "business"),
        ],
    ),
    MenuCategory(
        name="創作輸出",
        emoji="✍️",
        items=[
            MenuItem("會議記錄", "/meeting", "📝", "群組對話→戰情報告", "creative"),
            MenuItem("品牌顧問", "/brand", "🏷️", "品牌定位＋視覺識別", "creative"),
            MenuItem("產業報告", "/report", "📋", "付費級深度報告", "creative"),
        ],
    ),
    MenuCategory(
        name="思維工具",
        emoji="🧠",
        items=[
            MenuItem("破框解方", "/xmodel", "💡", "跨領域槓桿推演", "thinking"),
            MenuItem("人格分析", "/wan-miu", "🎭", "萬謬16型人格", "thinking"),
            MenuItem("思維轉化", "/dharma", "🌊", "六步驟認知轉化", "thinking"),
        ],
    ),
]

# 快捷鍵盤（ReplyKeyboard 用，3×3 九宮格）
QUICK_KEYBOARD: list[list[MenuItem]] = [
    [
        MenuItem("🎯 戰神系統", "/ares"),
        MenuItem("🔮 能量解讀", "/reading"),
        MenuItem("⚔️ 戰略分析", "/strategy"),
    ],
    [
        MenuItem("📊 市場分析", "/market"),
        MenuItem("📝 會議記錄", "/meeting"),
        MenuItem("🏷️ 品牌顧問", "/brand"),
    ],
    [
        MenuItem("💡 破框解方", "/xmodel"),
        MenuItem("📋 產業報告", "/report"),
        MenuItem("🧠 更多功能", "/menu"),
    ],
]

# Bot Commands（顯示在 / 選單裡）
BOT_COMMANDS: list[tuple[str, str]] = [
    ("ares", "🎯 戰神系統 — 人物分析＋策略建議"),
    ("reading", "🔮 能量解讀 — 八方位能量盤"),
    ("strategy", "⚔️ 戰略分析 — 九策軍師"),
    ("market", "📊 市場分析 — 多空研判"),
    ("meeting", "📝 會議記錄 — 對話→報告"),
    ("business", "💡 商模診斷 — 十二力框架"),
    ("brand", "🏷️ 品牌顧問 — 定位＋識別"),
    ("ssa", "🤝 顧問銷售 — 成交流程"),
    ("xmodel", "💡 破框解方 — 槓桿推演"),
    ("report", "📋 產業報告 — 深度分析"),
    ("wan_miu", "🎭 人格分析 — 萬謬16型"),
    ("dharma", "🌊 思維轉化 — 認知突破"),
    ("risk", "📈 風險管理 — 資產配置"),
    ("shadow", "🕶️ 人際博弈 — 陰謀辨識"),
    ("help", "❓ 使用說明"),
    ("menu", "📋 功能選單"),
]

# 完整功能清單（/menu 展開用）
FULL_MENU_TEXT = """📋 **MUSEON 完整功能選單**

🎯 **戰略情報**
/ares — 戰神系統（人物分析＋策略建議）
/reading — 能量解讀（八方位能量盤）
/strategy — 戰略分析（九策軍師）
/combined — 合盤比對（雙人能量比對）

💼 **商業工具**
/market — 市場分析（多空研判）
/business — 商模診斷（十二力框架）
/ssa — 顧問銷售（成交流程）
/risk — 風險管理（資產配置）

✍️ **創作輸出**
/meeting — 會議記錄（對話→戰情報告）
/brand — 品牌顧問（定位＋識別）
/report — 產業報告（付費級深度分析）
/text — 文字煉金（各類文案撰寫）

🧠 **思維工具**
/xmodel — 破框解方（槓桿推演）
/wan-miu — 人格分析（萬謬16型）
/dharma — 思維轉化（認知突破）
/philo — 哲學思辨（概念澄清）
/resonance — 感性共振（情緒承接）
/shadow — 人際博弈（陰謀辨識）

📊 **進階分析**
/crypto — 加密貨幣分析
/equity — 股票分析
/macro — 總經分析
/masters — 投資軍師團
/sentiment — 市場情緒雷達
/dse — 深度研究驗證

🔧 **系統**
/plan — 計畫引擎
/learn — 元學習
/blueprint — 人類圖藍圖

💡 直接用中文描述需求也可以，不一定要用指令喔！
"""

# 按鈕文字 → 指令映射（ReplyKeyboard 按鈕點擊時轉換用）
BUTTON_TO_COMMAND: dict[str, str] = {
    "🎯 戰神系統": "/ares",
    "🔮 能量解讀": "/reading",
    "⚔️ 戰略分析": "/strategy",
    "📊 市場分析": "/market",
    "📝 會議記錄": "/meeting",
    "🏷️ 品牌顧問": "/brand",
    "💡 破框解方": "/xmodel",
    "📋 產業報告": "/report",
    "🧠 更多功能": "/menu",
}

# Mini App 導覽頁 URL
MINI_APP_NAV_URL = "https://zealchou.github.io/MUSEON/ares/"
