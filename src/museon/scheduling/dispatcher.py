"""ScheduledMessageDispatcher — 承諾投遞系統核心。

確保 MUSEON 答應客戶要發的訊息一定會發出去。
持久化佇列路徑：data/_system/message_schedule.json
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger("museon.scheduling.dispatcher")

# status 常數
STATUS_PENDING = "pending"
STATUS_DELIVERED = "delivered"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

# 保留已完成紀錄上限
_MAX_COMPLETED_RECORDS = 100


def _load_dotenv(dotenv_path: str) -> dict:
    """從 .env 檔案讀取環境變數（不依賴 python-dotenv）。"""
    result = {}
    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                result[key] = value
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.warning("讀取 .env 失敗: %s", exc)
    return result


def _now_iso() -> str:
    """返回帶時區的 ISO 8601 字串。"""
    return datetime.now(timezone.utc).astimezone().isoformat()


def _parse_dt(dt_str: str) -> datetime:
    """解析 ISO 8601 字串為 aware datetime。"""
    import datetime as dt_module
    # Python 3.7+ fromisoformat 不支援 Z 後綴，手動替換
    dt_str = dt_str.replace("Z", "+00:00")
    return dt_module.datetime.fromisoformat(dt_str)


class ScheduledMessageDispatcher:
    """
    承諾投遞系統。

    排程一則訊息後，即使 Gateway 重啟也會補發——所有狀態都持久化在
    data/_system/message_schedule.json，原子寫入（先寫 .tmp 再 rename）。
    """

    def __init__(self, data_dir: str = "data") -> None:
        self._data_dir = data_dir
        self._queue_path = os.path.join(data_dir, "_system", "message_schedule.json")
        self._bot_token: Optional[str] = self._resolve_token(data_dir)

    # ------------------------------------------------------------------
    # Token 解析
    # ------------------------------------------------------------------

    def _resolve_token(self, data_dir: str) -> Optional[str]:
        """優先從環境變數讀 TELEGRAM_BOT_TOKEN，次之從 .env 檔案。"""
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if token:
            return token
        # 往上找 .env（與 data_dir 同層或專案根目錄）
        candidates = [
            os.path.join(data_dir, "..", ".env"),
            os.path.join(data_dir, "..", "..", ".env"),
            os.path.expanduser("~/MUSEON/.env"),
        ]
        for path in candidates:
            path = os.path.normpath(path)
            env_vars = _load_dotenv(path)
            if "TELEGRAM_BOT_TOKEN" in env_vars:
                return env_vars["TELEGRAM_BOT_TOKEN"]
        logger.warning("找不到 TELEGRAM_BOT_TOKEN，排程訊息無法發送")
        return None

    # ------------------------------------------------------------------
    # 持久化（原子讀寫）
    # ------------------------------------------------------------------

    def _load_queue(self) -> dict:
        """載入持久化佇列；若不存在則返回空結構。"""
        import json
        try:
            with open(self._queue_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"messages": []}
        except Exception as exc:
            logger.error("載入佇列失敗: %s", exc)
            return {"messages": []}

    def _save_queue(self, queue: dict) -> None:
        """原子寫入：先寫 .tmp 再 rename。"""
        import json
        tmp_path = self._queue_path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self._queue_path), exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(queue, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._queue_path)
        except Exception as exc:
            logger.error("寫入佇列失敗: %s", exc)
            # 嘗試清理 tmp
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def _prune_completed(self, messages: list) -> list:
        """
        保留所有 pending/cancelled 紀錄，
        以及最近 _MAX_COMPLETED_RECORDS 筆已完成（delivered/failed）紀錄。
        """
        completed = [
            m for m in messages
            if m.get("status") in (STATUS_DELIVERED, STATUS_FAILED)
        ]
        active = [
            m for m in messages
            if m.get("status") not in (STATUS_DELIVERED, STATUS_FAILED)
        ]
        # completed 依 delivered_at / failed_at 排序，保留最新的
        def _sort_key(m):
            ts = m.get("delivered_at") or m.get("failed_at") or ""
            return ts

        completed.sort(key=_sort_key, reverse=True)
        trimmed = completed[:_MAX_COMPLETED_RECORDS]
        return active + trimmed

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def schedule(
        self,
        chat_id: str,
        text: str,
        scheduled_at: datetime,
        campaign_id: Optional[str] = None,
        campaign_day: Optional[int] = None,
        bypass_quality_gate: bool = True,
    ) -> str:
        """
        排程一則訊息。

        Returns:
            message_id (UUID 字串)
        """
        try:
            # 確保 scheduled_at 是 aware datetime
            if scheduled_at.tzinfo is None:
                scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)

            message_id = str(uuid.uuid4())
            record = {
                "id": message_id,
                "chat_id": str(chat_id),
                "text": text,
                "scheduled_at": scheduled_at.isoformat(),
                "created_at": _now_iso(),
                "delivered_at": None,
                "failed_at": None,
                "retry_count": 0,
                "max_retries": 3,
                "campaign_id": campaign_id,
                "campaign_day": campaign_day,
                "bypass_quality_gate": bypass_quality_gate,
                "status": STATUS_PENDING,
            }
            queue = self._load_queue()
            queue["messages"].append(record)
            queue["messages"] = self._prune_completed(queue["messages"])
            self._save_queue(queue)
            logger.info(
                "已排程訊息 %s → chat_id=%s 於 %s",
                message_id,
                chat_id,
                scheduled_at.isoformat(),
            )
            return message_id
        except Exception as exc:
            logger.error("schedule() 發生例外: %s", exc)
            return ""

    def check_and_send(self) -> List[dict]:
        """
        檢查有沒有到期該發的訊息並發送。

        每分鐘由 cron 呼叫一次。

        Returns:
            已發送（或已標記 failed）的訊息清單。
        """
        sent = []
        try:
            now = datetime.now(timezone.utc).astimezone()
            queue = self._load_queue()
            changed = False

            for msg in queue["messages"]:
                if msg.get("status") != STATUS_PENDING:
                    continue
                try:
                    scheduled_at = _parse_dt(msg["scheduled_at"])
                except Exception:
                    logger.warning("無法解析 scheduled_at: %s", msg.get("scheduled_at"))
                    continue

                if scheduled_at <= now:
                    success = self._send_telegram(msg["chat_id"], msg["text"])
                    if success:
                        msg["status"] = STATUS_DELIVERED
                        msg["delivered_at"] = _now_iso()
                        logger.info("已投遞訊息 %s → chat_id=%s", msg["id"], msg["chat_id"])
                    else:
                        msg["retry_count"] = msg.get("retry_count", 0) + 1
                        if msg["retry_count"] >= msg.get("max_retries", 3):
                            msg["status"] = STATUS_FAILED
                            msg["failed_at"] = _now_iso()
                            logger.error(
                                "訊息 %s 超過重試上限，標記 failed", msg["id"]
                            )
                        else:
                            logger.warning(
                                "訊息 %s 發送失敗，retry_count=%d",
                                msg["id"],
                                msg["retry_count"],
                            )
                    changed = True
                    sent.append(dict(msg))

            if changed:
                queue["messages"] = self._prune_completed(queue["messages"])
                self._save_queue(queue)
        except Exception as exc:
            logger.error("check_and_send() 發生例外: %s", exc)
        return sent

    def replay_on_startup(self) -> List[dict]:
        """
        Gateway 啟動時呼叫。

        找出所有已過期但未投遞的 pending 訊息，立刻補發。

        Returns:
            已補發的訊息清單。
        """
        logger.info("replay_on_startup: 檢查未投遞的過期訊息...")
        try:
            return self.check_and_send()
        except Exception as exc:
            logger.error("replay_on_startup() 發生例外: %s", exc)
            return []

    def cancel(self, message_id: str) -> bool:
        """
        取消排程訊息（只能取消 pending 狀態的訊息）。

        Returns:
            True 若成功取消，False 若找不到或已不是 pending 狀態。
        """
        try:
            queue = self._load_queue()
            for msg in queue["messages"]:
                if msg.get("id") == message_id:
                    if msg.get("status") != STATUS_PENDING:
                        logger.warning(
                            "訊息 %s 狀態為 %s，無法取消", message_id, msg.get("status")
                        )
                        return False
                    msg["status"] = STATUS_CANCELLED
                    self._save_queue(queue)
                    logger.info("已取消訊息 %s", message_id)
                    return True
            logger.warning("找不到訊息 %s", message_id)
            return False
        except Exception as exc:
            logger.error("cancel() 發生例外: %s", exc)
            return False

    def list_pending(self) -> List[dict]:
        """
        列出所有待發送（pending）訊息。

        Returns:
            pending 訊息清單（各為 dict 複本）。
        """
        try:
            queue = self._load_queue()
            return [
                dict(m) for m in queue["messages"]
                if m.get("status") == STATUS_PENDING
            ]
        except Exception as exc:
            logger.error("list_pending() 發生例外: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Telegram 發送（標準庫 urllib.request）
    # ------------------------------------------------------------------

    def _send_telegram(self, chat_id: str, text: str) -> bool:
        """
        直接呼叫 Telegram Bot API 發送訊息。

        使用 urllib.request，不依賴任何第三方 adapter。

        Returns:
            True 發送成功，False 失敗。
        """
        import json
        import urllib.error
        import urllib.parse
        import urllib.request

        if not self._bot_token:
            logger.error("TELEGRAM_BOT_TOKEN 未設定，無法發送")
            return False

        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                if body.get("ok"):
                    return True
                logger.error("Telegram API 回傳 ok=false: %s", body)
                return False
        except urllib.error.HTTPError as exc:
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                err_body = str(exc)
            logger.error("Telegram HTTP 錯誤 %d: %s", exc.code, err_body)
            return False
        except urllib.error.URLError as exc:
            logger.error("Telegram URLError: %s", exc.reason)
            return False
        except Exception as exc:
            logger.error("_send_telegram() 未預期例外: %s", exc)
            return False


# --------------------------------------------------------------------------
# CronEngine 整合
# --------------------------------------------------------------------------

def register_dispatcher_cron(cron_engine, dispatcher: ScheduledMessageDispatcher) -> None:
    """
    將 dispatcher.check_and_send 註冊到 CronEngine，每 60 秒執行一次。

    Args:
        cron_engine: CronEngine 實例（museon.gateway.cron.CronEngine）
        dispatcher:  ScheduledMessageDispatcher 實例
    """
    import asyncio

    async def _async_check_and_send():
        # check_and_send 是同步方法，在 executor 中執行避免阻塞 event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, dispatcher.check_and_send)

    cron_engine.add_job(
        func=_async_check_and_send,
        trigger="interval",
        job_id="scheduled-message-check",
        seconds=60,
    )
    logger.info("已向 CronEngine 註冊 scheduled-message-check（每 60 秒）")
