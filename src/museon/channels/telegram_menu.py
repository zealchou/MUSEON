"""Telegram Menu Adapter — 將通用選單配置轉為 Telegram UI 元件.

職責：
1. Bot Commands 註冊（/指令列表）
2. ReplyKeyboard 持久鍵盤（九宮格快捷按鈕）
3. InlineKeyboard 內嵌按鈕（功能分組展開）
4. MenuButton 設定（左下角 Mini App 按鈕）

與 menu_config.py 搭配：config 定義「有什麼選單」，本模組定義「在 Telegram 怎麼顯示」。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def register_bot_commands(bot: Any) -> None:
    """方案 1：註冊 Bot Commands（使用者輸入 / 時顯示）.

    分兩組：私訊用完整清單，群組用精簡清單。
    """
    try:
        from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats
        from museon.channels.menu_config import BOT_COMMANDS, GROUP_COMMANDS

        # 私訊：完整清單
        commands = [BotCommand(cmd, desc) for cmd, desc in BOT_COMMANDS]
        await bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())

        # 群組：精簡清單（最常用的 + 群組專屬）
        group_cmds = [BotCommand(cmd, desc) for cmd, desc in GROUP_COMMANDS]
        await bot.set_my_commands(group_cmds, scope=BotCommandScopeAllGroupChats())

        logger.info(f"[MENU] Registered commands: DM={len(commands)}, Group={len(group_cmds)}")
    except Exception as e:
        logger.warning(f"[MENU] Failed to register bot commands: {e}")


async def setup_menu_button(bot: Any, chat_id: int | None = None) -> None:
    """方案 4：設定左下角 Menu 按鈕 → 開啟 Mini App.

    chat_id=None → 設定為所有使用者的預設
    chat_id=具體值 → 只為特定使用者設定
    """
    try:
        from telegram import MenuButtonWebApp, WebAppInfo
        from museon.channels.menu_config import MINI_APP_NAV_URL

        menu_button = MenuButtonWebApp(
            text="📋 功能選單",
            web_app=WebAppInfo(url=MINI_APP_NAV_URL),
        )
        await bot.set_chat_menu_button(chat_id=chat_id, menu_button=menu_button)
        logger.info(f"[MENU] MenuButton → Mini App set for {'all' if chat_id is None else chat_id}")
    except Exception as e:
        # 降級：用 Commands 選單
        logger.warning(f"[MENU] MenuButtonWebApp failed, falling back to commands: {e}")
        try:
            from telegram import MenuButtonCommands
            await bot.set_chat_menu_button(
                chat_id=chat_id,
                menu_button=MenuButtonCommands(),
            )
        except Exception:
            pass


def build_reply_keyboard() -> Any:
    """方案 2：建立持久 ReplyKeyboard（九宮格快捷按鈕）."""
    try:
        from telegram import ReplyKeyboardMarkup, KeyboardButton
        from museon.channels.menu_config import QUICK_KEYBOARD

        keyboard = [
            [KeyboardButton(item.label) for item in row]
            for row in QUICK_KEYBOARD
        ]
        return ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder="輸入訊息或點選功能...",
        )
    except Exception as e:
        logger.warning(f"[MENU] Failed to build reply keyboard: {e}")
        return None


def build_inline_menu() -> Any:
    """方案 3：建立 InlineKeyboard 功能選單（/menu 展開用）."""
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from museon.channels.menu_config import MAIN_MENU

        keyboard = []
        for category in MAIN_MENU:
            # 分組標題行
            keyboard.append([
                InlineKeyboardButton(
                    f"{category.emoji} {category.name}",
                    callback_data=f"menu_cat:{category.name}",
                )
            ])
            # 該分組的按鈕（每行 3 個）
            row = []
            for item in category.items:
                row.append(InlineKeyboardButton(
                    f"{item.emoji} {item.label}",
                    callback_data=f"menu_cmd:{item.command}",
                ))
            keyboard.append(row)

        # 底部加入 Mini App 按鈕
        from museon.channels.menu_config import MINI_APP_NAV_URL
        from telegram import WebAppInfo
        keyboard.append([
            InlineKeyboardButton(
                "🌐 開啟互動式面板",
                web_app=WebAppInfo(url=MINI_APP_NAV_URL),
            )
        ])

        return InlineKeyboardMarkup(keyboard)
    except Exception as e:
        logger.warning(f"[MENU] Failed to build inline menu: {e}")
        return None


async def handle_menu_callback(update: Any, context: Any) -> None:
    """處理 InlineKeyboard 的 callback（menu_cmd:/xxx）."""
    try:
        query = update.callback_query
        data = query.data

        if data.startswith("menu_cmd:"):
            command = data.split(":", 1)[1]
            await query.answer()
            # 模擬使用者發送該指令
            await query.message.reply_text(
                f"正在執行 {command}...",
            )
            # 注入為新訊息讓 Brain 處理
            # 透過編輯原訊息提示使用者
        elif data.startswith("menu_cat:"):
            await query.answer(f"展開 {data.split(':', 1)[1]}")
    except Exception as e:
        logger.warning(f"[MENU] Callback handler error: {e}")


async def send_welcome_with_keyboard(
    bot: Any, chat_id: int, user_name: str = "",
) -> None:
    """發送歡迎訊息 + 持久鍵盤."""
    keyboard = build_reply_keyboard()
    welcome = (
        f"👋 {'嗨 ' + user_name + '！' if user_name else '歡迎！'}\n\n"
        "我是 MUSEON，你的 AI 策略幕僚。\n\n"
        "⬇️ 點選下方按鈕快速開始，或直接輸入你的需求。\n"
        "輸入 /menu 可查看完整功能清單。"
    )
    # 統一 sanitize（在 try 外，確保 fallback 也用清理後的文字）
    try:
        from museon.governance.response_guard import ResponseGuard
        welcome = ResponseGuard.sanitize_for_group(welcome, is_group=(int(chat_id) < 0))
    except Exception:
        pass
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=welcome,
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.warning(f"[MENU] Welcome message failed: {e}")
        # 降級：純文字
        await bot.send_message(chat_id=chat_id, text=welcome)


async def send_full_menu(bot: Any, chat_id: int, is_group: bool = False) -> None:
    """發送功能選單（/menu 觸發）.

    群組用精簡版（避免洗版），私訊用完整版。
    """
    if is_group:
        from museon.channels.menu_config import GROUP_INLINE_MENU_TEXT
        inline_menu = build_group_inline_menu()
        text = GROUP_INLINE_MENU_TEXT
    else:
        from museon.channels.menu_config import FULL_MENU_TEXT
        inline_menu = build_inline_menu()
        text = FULL_MENU_TEXT

    # 統一 sanitize（在 try 外，確保 fallback 也用清理後的文字）
    try:
        from museon.governance.response_guard import ResponseGuard
        text = ResponseGuard.sanitize_for_group(text, is_group=is_group)
    except Exception:
        pass
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=inline_menu,
        )
    except Exception as e:
        logger.warning(f"[MENU] Full menu failed: {e}")
        await bot.send_message(chat_id=chat_id, text=text)


def build_group_inline_menu() -> Any:
    """群組專用 InlineKeyboard（精簡版）."""
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
        from museon.channels.menu_config import MINI_APP_NAV_URL

        keyboard = [
            [
                InlineKeyboardButton("🎯 戰神系統", callback_data="menu_cmd:/ares"),
                InlineKeyboardButton("📝 會議記錄", callback_data="menu_cmd:/meeting"),
                InlineKeyboardButton("⚔️ 戰略分析", callback_data="menu_cmd:/strategy"),
            ],
            [
                InlineKeyboardButton("📊 市場分析", callback_data="menu_cmd:/market"),
                InlineKeyboardButton("💡 破框解方", callback_data="menu_cmd:/xmodel"),
                InlineKeyboardButton("💼 商模診斷", callback_data="menu_cmd:/business"),
            ],
            [
                InlineKeyboardButton(
                    "🌐 開啟完整面板",
                    web_app=WebAppInfo(url=MINI_APP_NAV_URL),
                ),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)
    except Exception as e:
        logger.warning(f"[MENU] Group inline menu failed: {e}")
        return None
