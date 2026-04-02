"""DripCampaignEngine — 旅程推進引擎。

管理「每日定時推送內容給客戶」的旅程。
狀態持久化路徑：data/_system/campaigns/{campaign_id}_state.json
詞彙資料路徑：data/_system/campaigns/{campaign_id}_vocabulary.json（依 campaign 而定）
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("museon.scheduling.campaigns")

# 台灣時區（UTC+8）
_TZ8 = timezone(timedelta(hours=8))


def _now_tz8() -> datetime:
    """返回台灣時間的 aware datetime。"""
    return datetime.now(_TZ8)


def _today_str() -> str:
    """返回今天的日期字串 YYYY-MM-DD（台灣時間）。"""
    return _now_tz8().strftime("%Y-%m-%d")


def _atomic_write(path: str, data: dict) -> None:
    """原子寫入：先寫 .tmp 再 rename，防止寫入一半損壞。"""
    tmp_path = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception as exc:
        logger.error("原子寫入失敗 %s: %s", path, exc)
        try:
            os.remove(tmp_path)
        except OSError:
            pass


@dataclass
class CampaignConfig:
    """Campaign 設定。"""
    campaign_id: str           # 例："evvon_sustainability"
    chat_id: str               # 例："-5260398061"
    total_days: int            # 例：90
    schedule_hour: int         # 例：8（代表 08:00）
    schedule_minute: int       # 例：0
    timezone: str              # 例："Asia/Taipei"
    active: bool               # True = 啟用
    extra: dict = field(default_factory=dict)  # 保留擴充欄位


class DripCampaignEngine:
    """旅程推進引擎——管理所有 drip campaign 的排程與狀態。"""

    def __init__(self, data_dir: str = "data") -> None:
        """初始化引擎。

        Args:
            data_dir: MUSEON data 根目錄（例：/Users/ZEALCHOU/MUSEON/data）
        """
        self._data_dir = data_dir
        self._campaigns_dir = os.path.join(data_dir, "_system", "campaigns")
        self._configs: Dict[str, CampaignConfig] = {}
        self._generators: Dict[str, Callable] = {}

        # 確保目錄存在
        try:
            os.makedirs(self._campaigns_dir, exist_ok=True)
        except Exception as exc:
            logger.error("建立 campaigns 目錄失敗: %s", exc)

    # ------------------------------------------------------------------
    # Campaign 註冊
    # ------------------------------------------------------------------

    def register_campaign(
        self,
        config: CampaignConfig,
        content_generator: Callable,
    ) -> None:
        """註冊一個 campaign 和它的內容生成器。

        Args:
            config: CampaignConfig 設定
            content_generator: 簽名為 (campaign_id: str, day: int) -> Optional[str]
        """
        try:
            self._configs[config.campaign_id] = config
            self._generators[config.campaign_id] = content_generator
            logger.info("Campaign 已註冊: %s（共 %d 天）", config.campaign_id, config.total_days)
        except Exception as exc:
            logger.error("register_campaign() 失敗: %s", exc)

    # ------------------------------------------------------------------
    # 狀態讀寫
    # ------------------------------------------------------------------

    def _state_path(self, campaign_id: str) -> str:
        """返回 campaign state 的檔案路徑。"""
        return os.path.join(self._campaigns_dir, f"{campaign_id}_state.json")

    def get_campaign_state(self, campaign_id: str) -> dict:
        """取得 campaign 目前狀態。

        Returns:
            state dict；若找不到則返回帶預設值的 dict。
        """
        try:
            path = self._state_path(campaign_id)
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("Campaign state 不存在: %s，返回預設值", campaign_id)
            return {
                "campaign_id": campaign_id,
                "current_day": 1,
                "started_at": _today_str(),
                "last_sent_date": None,
                "last_sent_day": 0,
                "history": [],
            }
        except Exception as exc:
            logger.error("讀取 campaign state 失敗 %s: %s", campaign_id, exc)
            return {}

    def _save_campaign_state(self, state: dict) -> None:
        """儲存 campaign state。"""
        try:
            campaign_id = state.get("campaign_id", "unknown")
            path = self._state_path(campaign_id)
            _atomic_write(path, state)
        except Exception as exc:
            logger.error("儲存 campaign state 失敗: %s", exc)

    # ------------------------------------------------------------------
    # 日期推進
    # ------------------------------------------------------------------

    def advance_day(self, campaign_id: str) -> int:
        """推進到下一天，返回新的 day 數。

        Returns:
            推進後的 current_day；若發生錯誤返回 -1。
        """
        try:
            state = self.get_campaign_state(campaign_id)
            if not state:
                logger.error("advance_day: 無法讀取 state for %s", campaign_id)
                return -1

            config = self._configs.get(campaign_id)
            current_day = state.get("current_day", 1)
            new_day = current_day + 1

            # 超過總天數就停在最後一天（不循環）
            if config and new_day > config.total_days:
                logger.info(
                    "Campaign %s 已完成所有 %d 天，不再推進",
                    campaign_id,
                    config.total_days,
                )
                return current_day

            state["current_day"] = new_day
            self._save_campaign_state(state)
            logger.info("Campaign %s 推進到 Day %d", campaign_id, new_day)
            return new_day
        except Exception as exc:
            logger.error("advance_day() 失敗 %s: %s", campaign_id, exc)
            return -1

    # ------------------------------------------------------------------
    # 內容生成與排程
    # ------------------------------------------------------------------

    def generate_and_schedule(self, campaign_id: str) -> Optional[str]:
        """生成今天的內容並排程發送。

        邏輯：
        1. 讀取 campaign state，取得 current_day
        2. 如果今天已經發過了（last_sent_date == today），跳過
        3. 呼叫 content_generator(campaign_id, current_day) 取得文字
        4. 呼叫 ScheduledMessageDispatcher.schedule() 排程
        5. advance_day()

        Returns:
            scheduled message id；若跳過或失敗則返回 None。
        """
        try:
            config = self._configs.get(campaign_id)
            if not config:
                logger.error("Campaign 未註冊: %s", campaign_id)
                return None

            if not config.active:
                logger.info("Campaign %s 為非啟用狀態，跳過", campaign_id)
                return None

            state = self.get_campaign_state(campaign_id)
            if not state:
                logger.error("無法取得 campaign state: %s", campaign_id)
                return None

            current_day = state.get("current_day", 1)
            last_sent_date = state.get("last_sent_date")
            today = _today_str()

            # 今天已發過，跳過
            if last_sent_date == today:
                logger.info(
                    "Campaign %s Day %d 今天（%s）已發過，跳過",
                    campaign_id,
                    current_day,
                    today,
                )
                return None

            # 超過總天數，停止
            if current_day > config.total_days:
                logger.info(
                    "Campaign %s 已完成所有 %d 天，停止",
                    campaign_id,
                    config.total_days,
                )
                return None

            # 呼叫內容生成器
            generator = self._generators.get(campaign_id)
            if not generator:
                logger.error("找不到 content_generator: %s", campaign_id)
                return None

            text = generator(campaign_id, current_day)
            if not text:
                logger.warning(
                    "Campaign %s Day %d content_generator 返回空內容，跳過",
                    campaign_id,
                    current_day,
                )
                return None

            # 計算排程時間（今天 schedule_hour:schedule_minute，台灣時間）
            now_tz8 = _now_tz8()
            scheduled_at = now_tz8.replace(
                hour=config.schedule_hour,
                minute=config.schedule_minute,
                second=0,
                microsecond=0,
            )
            # 如果排程時間已過，立即排程（+5 秒緩衝）
            if scheduled_at <= now_tz8:
                scheduled_at = now_tz8 + timedelta(seconds=5)
                logger.info(
                    "Campaign %s 排程時間已過，改為立即發送（+5s）",
                    campaign_id,
                )

            # Lazy import dispatcher，避免循環 import
            from museon.scheduling.dispatcher import ScheduledMessageDispatcher  # noqa: PLC0415
            dispatcher = ScheduledMessageDispatcher(self._data_dir)
            message_id = dispatcher.schedule(
                chat_id=config.chat_id,
                text=text,
                scheduled_at=scheduled_at,
                campaign_id=campaign_id,
                campaign_day=current_day,
            )

            if not message_id:
                logger.error(
                    "Campaign %s Day %d dispatcher.schedule() 返回空 message_id",
                    campaign_id,
                    current_day,
                )
                return None

            # 更新 state
            state["last_sent_date"] = today
            state["last_sent_day"] = current_day
            history_entry = {
                "day": current_day,
                "sent_at": now_tz8.isoformat(),
                "message_id": message_id,
                "status": "scheduled",
            }
            if "history" not in state:
                state["history"] = []
            state["history"].append(history_entry)
            self._save_campaign_state(state)

            # 推進到下一天
            self.advance_day(campaign_id)

            logger.info(
                "Campaign %s Day %d 已排程，message_id=%s，預計發送 %s",
                campaign_id,
                current_day,
                message_id,
                scheduled_at.isoformat(),
            )
            return message_id

        except Exception as exc:
            logger.error("generate_and_schedule() 發生例外 %s: %s", campaign_id, exc)
            return None

    # ------------------------------------------------------------------
    # 批次檢查
    # ------------------------------------------------------------------

    def check_all_campaigns(self) -> List[str]:
        """檢查所有 active campaign，對到期的呼叫 generate_and_schedule()。

        Returns:
            已排程的 message_id 列表（不含 None）。
        """
        scheduled_ids: List[str] = []
        try:
            for campaign_id, config in self._configs.items():
                if not config.active:
                    continue
                try:
                    msg_id = self.generate_and_schedule(campaign_id)
                    if msg_id:
                        scheduled_ids.append(msg_id)
                except Exception as exc:
                    logger.error(
                        "check_all_campaigns: campaign %s 發生例外: %s",
                        campaign_id,
                        exc,
                    )
        except Exception as exc:
            logger.error("check_all_campaigns() 外層例外: %s", exc)

        logger.info(
            "check_all_campaigns 完成，共排程 %d 則訊息",
            len(scheduled_ids),
        )
        return scheduled_ids


# ===========================================================================
# Evvon Sustainability Vocabulary Content Generator
# ===========================================================================

_EVVON_VOCAB_CACHE: Optional[dict] = None
_EVVON_VOCAB_PATH_TEMPLATE = "{data_dir}/_system/campaigns/evvon_vocabulary.json"


def _load_evvon_vocabulary(data_dir: str = "data") -> Optional[dict]:
    """載入 evvon_vocabulary.json，帶快取。"""
    global _EVVON_VOCAB_CACHE
    if _EVVON_VOCAB_CACHE is not None:
        return _EVVON_VOCAB_CACHE

    path = _EVVON_VOCAB_PATH_TEMPLATE.format(data_dir=data_dir)
    try:
        with open(path, "r", encoding="utf-8") as f:
            _EVVON_VOCAB_CACHE = json.load(f)
        return _EVVON_VOCAB_CACHE
    except FileNotFoundError:
        logger.error("evvon_vocabulary.json 不存在: %s", path)
        return None
    except Exception as exc:
        logger.error("讀取 evvon_vocabulary.json 失敗: %s", exc)
        return None


def evvon_sustainability_content(campaign_id: str, day: int) -> Optional[str]:
    """生成 Evvon 永續英文 Day N 的 Telegram 推送文字。

    這個函數只產生 Telegram 訊息文字（不產生 HTML）。
    HTML 報告由 scripts/publish-report.sh 發布。

    Args:
        campaign_id: campaign 識別碼（保留供未來多 campaign 擴充用）
        day: 目前的天數（1-based）

    Returns:
        格式化後的 Telegram 訊息字串；若找不到詞彙資料則返回 None。
    """
    try:
        # 嘗試推算 data_dir（從環境變數或預設值）
        data_dir = os.environ.get("MUSEON_DATA_DIR", os.path.expanduser("~/MUSEON/data"))
        vocab_data = _load_evvon_vocabulary(data_dir)

        if vocab_data is None:
            logger.error("evvon_sustainability_content: 無法載入詞彙資料")
            return None

        # 找到對應的詞彙
        words = vocab_data.get("words", [])
        entry = next((w for w in words if w.get("day") == day), None)

        if entry is None:
            logger.warning(
                "evvon_sustainability_content: Day %d 找不到對應詞彙（共 %d 筆）",
                day,
                len(words),
            )
            return None

        word = entry.get("word", "")
        zh = entry.get("zh", "")
        intro = entry.get("intro", "")
        report_url = (
            f"https://zealchou.github.io/MUSEON/reports/"
            f"sustainability-evvon-day{day:02d}.html"
        )

        message = (
            f"☀️ Good morning Evvon！\n"
            f"\n"
            f"今天是 Day {day:02d} — {word}（{zh}）🌿\n"
            f"\n"
            f"{intro}\n"
            f"\n"
            f"👉 今日學習卡：\n"
            f"{report_url}\n"
            f"\n"
            f"記得看完後用 {word} 造一個句子貼回來喔 ✏️"
        )

        logger.info(
            "evvon_sustainability_content: Day %d — %s 內容已生成",
            day,
            word,
        )
        return message

    except Exception as exc:
        logger.error("evvon_sustainability_content() 發生例外 day=%d: %s", day, exc)
        return None


# ===========================================================================
# 便利函數：建立已設定好的 Evvon Campaign Engine
# ===========================================================================

def make_evvon_engine(data_dir: str = "data") -> DripCampaignEngine:
    """建立並返回已設定好 Evvon Campaign 的引擎。

    Args:
        data_dir: MUSEON data 根目錄

    Returns:
        已呼叫 register_campaign() 的 DripCampaignEngine。
    """
    engine = DripCampaignEngine(data_dir=data_dir)
    config = CampaignConfig(
        campaign_id="evvon_sustainability",
        chat_id="-5260398061",
        total_days=90,
        schedule_hour=8,
        schedule_minute=0,
        timezone="Asia/Taipei",
        active=True,
    )
    engine.register_campaign(config, evvon_sustainability_content)
    return engine
