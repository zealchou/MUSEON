"""Group Digest Service — 群組定時摘要服務.

每天 10:00、14:00、17:00 對 Zeal 所在的客戶群組發送：
1. 上次摘要到現在的新對話摘要
2. 待辦清單提醒

安全設計：
- 所有發送走 push_notification → _safe_send（統一 sanitize）
- 每個群組獨立處理，不共享上下文
- Zeal 退群自動停止服務（由 ChatMemberHandler 觸發 digest_enabled=False）
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# Zeal 的 user_id
OWNER_USER_ID = "6969045906"

# 摘要時間表
DIGEST_HOURS = [10, 14, 17]

# 不發摘要的條件：新對話少於 N 條
MIN_MESSAGES_FOR_DIGEST = 3


class GroupDigestService:
    """群組定時摘要服務."""

    def __init__(self, group_store, llm_adapter=None, telegram_adapter=None):
        """
        Args:
            group_store: GroupContextStore instance（讀取群組對話）
            llm_adapter: LLM adapter（用 Haiku 生成摘要）
            telegram_adapter: TelegramAdapter instance（發送摘要）
        """
        self._store = group_store
        self._llm = llm_adapter
        self._tg = telegram_adapter

    async def run_digest_cycle(self) -> Dict[str, Any]:
        """執行一輪摘要推播（所有 Zeal 所在群組）.

        Returns:
            {"groups_processed": N, "groups_sent": M, "groups_skipped": K, "details": [...]}
        """
        # 取得 Zeal 所在的群組
        groups = self._store.get_groups_with_owner(OWNER_USER_ID)
        if not groups:
            logger.info("[GroupDigest] No groups found for owner")
            return {"groups_processed": 0, "groups_sent": 0, "groups_skipped": 0, "details": []}

        results: List[Dict[str, Any]] = []
        sent = 0
        skipped = 0

        for group in groups:
            gid = group["group_id"]
            title = group["title"]

            try:
                # 檢查是否啟用摘要（預設啟用）
                enabled = self._store.get_group_setting(gid, "digest_enabled", True)
                if not enabled:
                    skipped += 1
                    results.append({"group_id": gid, "title": title, "status": "disabled"})
                    continue

                # 取得上次摘要時間
                last_digest = self._store.get_group_setting(gid, "last_digest_at", "")
                if not last_digest:
                    # 首次：只取最近 4 小時
                    since = (datetime.now(TZ8) - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    since = last_digest

                # 取得新對話
                messages = self._store.get_messages_since(gid, since)
                if len(messages) < MIN_MESSAGES_FOR_DIGEST:
                    skipped += 1
                    results.append({
                        "group_id": gid, "title": title,
                        "status": "skipped", "reason": f"only {len(messages)} messages",
                    })
                    continue

                # 生成摘要
                summary = await self._generate_summary(gid, title, messages, since)
                if not summary:
                    skipped += 1
                    results.append({"group_id": gid, "title": title, "status": "generation_failed"})
                    continue

                # 發送前用 getChatMember 確認 Zeal 還在群組
                if self._tg and self._tg.application:
                    try:
                        member = await self._tg.application.bot.get_chat_member(
                            chat_id=gid, user_id=int(OWNER_USER_ID)
                        )
                        if member.status in ("left", "kicked"):
                            logger.info(f"[GroupDigest] Owner not in group {gid}, disabling")
                            self._store.set_group_setting(gid, "digest_enabled", False)
                            skipped += 1
                            results.append({"group_id": gid, "title": title, "status": "owner_left"})
                            continue
                    except Exception as e:
                        logger.debug(f"[GroupDigest] getChatMember check failed for {gid}: {e}")
                        # 檢查失敗不阻擋發送（可能 Bot 不是 admin）

                # 發送到群組
                if self._tg:
                    await self._tg.push_notification(summary, chat_ids=[gid])
                    sent += 1

                # 更新上次摘要時間
                now_str = datetime.now(TZ8).strftime("%Y-%m-%d %H:%M:%S")
                self._store.set_group_setting(gid, "last_digest_at", now_str)

                results.append({"group_id": gid, "title": title, "status": "sent", "msg_count": len(messages)})

            except Exception as e:
                logger.error(f"[GroupDigest] Error processing group {gid}: {e}")
                results.append({"group_id": gid, "title": title, "status": "error", "error": str(e)})

        return {
            "groups_processed": len(groups),
            "groups_sent": sent,
            "groups_skipped": skipped,
            "details": results,
        }

    async def _generate_summary(
        self, group_id: int, title: str, messages: List[Dict], since: str,
    ) -> Optional[str]:
        """用 Haiku 生成群組摘要."""
        if not self._llm:
            # 無 LLM 時用純文字摘要
            return self._fallback_summary(title, messages, since)

        # 組建對話文本
        conversation = "\n".join(
            f"{m['name']}: {m['text'][:200]}" for m in messages if m.get("text")
        )

        # 查承諾（如果有 PulseDB）
        commitment_text = ""
        try:
            from museon.pulse.pulse_db import get_pulse_db
            db_base = str(self._store.db_path).replace("_system/group_context.db", "")
            pdb = get_pulse_db(db_base)
            session_id = f"telegram_group_{abs(group_id)}"
            rows = pdb._conn.execute(
                "SELECT content, status, due_at FROM commitments "
                "WHERE session_id = ? AND status IN ('pending', 'overdue') "
                "ORDER BY due_at ASC LIMIT 5",
                (session_id,),
            ).fetchall()
            if rows:
                commitment_text = "\n\n待辦承諾：\n" + "\n".join(
                    f"- {'⏰ 逾期' if r[1] == 'overdue' else '📌'} {r[0][:80]}" for r in rows
                )
        except Exception:
            pass

        now = datetime.now(TZ8)
        # 判斷時段
        if now.hour < 12:
            period = "早上"
        elif now.hour < 16:
            period = "下午"
        else:
            period = "傍晚"

        prompt = (
            f"你是 MUSEON，在群組「{title}」中提供定時摘要服務。\n"
            f"請根據以下對話內容，用繁體中文撰寫簡潔的群組摘要。\n\n"
            f"時段：{period}摘要\n"
            f"上次摘要時間：{since}\n"
            f"新對話（{len(messages)} 則）：\n"
            f"{conversation[:3000]}\n"
            f"{commitment_text}\n\n"
            f"格式要求：\n"
            f"📋 群組摘要（{since[:10]} ~ {now.strftime('%H:%M')}）\n\n"
            f"💬 對話重點：\n"
            f"- （用 2-5 個要點摘要主要討論內容）\n\n"
            f"📌 待辦提醒：\n"
            f"- （列出待辦事項，沒有就不列這段）\n\n"
            f"請直接輸出摘要，不要加其他說明。保持簡潔（200 字以內）。"
        )

        try:
            response = await self._llm.call(
                system_prompt="你是群組摘要助手，產出簡潔的對話摘要。",
                messages=[{"role": "user", "content": prompt}],
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
            )
            text = response if isinstance(response, str) else getattr(response, "content", str(response))
            return text.strip()
        except Exception as e:
            logger.warning(f"[GroupDigest] LLM summary failed for {group_id}: {e}")
            return self._fallback_summary(title, messages, since)

    def _fallback_summary(self, title: str, messages: List[Dict], since: str) -> str:
        """無 LLM 時的純文字摘要."""
        now = datetime.now(TZ8)
        # 統計發言者
        speakers: Dict[str, int] = {}
        for m in messages:
            name = m.get("name", "Unknown")
            speakers[name] = speakers.get(name, 0) + 1

        speaker_summary = "、".join(f"{name}({count}則)" for name, count in speakers.items())

        return (
            f"📋 群組摘要（{since[:16]} ~ {now.strftime('%H:%M')}）\n\n"
            f"💬 新對話 {len(messages)} 則\n"
            f"發言者：{speaker_summary}\n\n"
            f"（詳細摘要需要 AI 引擎支援）"
        )
