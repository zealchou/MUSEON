"""Proactive Intelligence — 主動情報引擎.

P0: 關係溫度預警 + 群組徵兆偵測
P1: 會前簡報 + 承諾追蹤
P2: 機會偵測 + 決策守護
P3: 跨群組情報整合

設計原則：
- 只讀不寫（觀察者模式，不修改原始資料）
- 產出 pending signals 供 ProactiveDispatcher 決定是否推播
- 推播走私訊，群組裡不說話
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 徵兆偵測關鍵詞
_COMMITMENT_KEYWORDS = [
    "下週給", "明天給", "我來處理", "我負責", "幫你", "寄給你",
    "這週內", "三天內", "盡快給", "回覆你", "報價", "提案",
]
_OPPORTUNITY_KEYWORDS = [
    "想做", "在找", "需要", "有沒有推薦", "想了解", "考慮",
    "預算", "想改", "想換", "品牌重塑", "系統化", "導入 AI",
]
_RISK_KEYWORDS = [
    "成本壓力", "考慮其他", "暫停", "延後", "再想想", "先不要",
    "太貴", "不確定", "退出", "離開", "算了",
]


class ProactiveIntel:
    """主動情報引擎."""

    def __init__(self, data_dir: Path | str):
        self.data_dir = Path(data_dir)
        self._signals_path = self.data_dir / "_system" / "ares" / "pending_signals.json"
        self._signals_path.parent.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════
    # P0: 關係溫度預警
    # ═══════════════════════════════════════

    def scan_relationship_alerts(self) -> list[dict[str, Any]]:
        """掃描所有 Ares profiles，找出需要預警的關係.

        Returns: [{profile_id, name, alert_type, message, urgency}]
        """
        from museon.ares.profile_store import ProfileStore
        store = ProfileStore(self.data_dir)
        alerts = []

        for pid, entry in store.list_all().items():
            profile = store.load(pid)
            if not profile:
                continue

            temp = profile.get("temperature", {})
            inter = profile.get("L4_interactions", {})
            last = inter.get("last_interaction")
            name = profile["L1_facts"]["name"]

            # 1. 長時間無互動預警
            if last:
                try:
                    days_since = (datetime.now() - datetime.fromisoformat(last)).days
                except Exception:
                    days_since = 999

                if days_since >= 14 and temp.get("level") in ("warm", "hot"):
                    alerts.append({
                        "profile_id": pid,
                        "name": name,
                        "alert_type": "cooling",
                        "message": f"⚠️ {name} 已經 {days_since} 天沒有互動，關係可能降溫。建議本週主動聯繫。",
                        "urgency": "medium",
                    })
                elif days_since >= 30:
                    alerts.append({
                        "profile_id": pid,
                        "name": name,
                        "alert_type": "cold",
                        "message": f"🥶 {name} 已超過 {days_since} 天無互動，關係已冷。需要重新暖場。",
                        "urgency": "high",
                    })

            # 2. 連續負面互動預警
            neg = inter.get("negative_count", 0)
            total = inter.get("total_count", 0)
            if total >= 3 and neg / total > 0.5:
                alerts.append({
                    "profile_id": pid,
                    "name": name,
                    "alert_type": "negative_trend",
                    "message": f"📉 {name} 的互動中負面佔比超過 50%（{neg}/{total}）。需要調整互動策略。",
                    "urgency": "high",
                })

        return alerts

    # ═══════════════════════════════════════
    # P0: 群組徵兆偵測
    # ═══════════════════════════════════════

    def detect_signals_from_message(
        self, sender_name: str, content: str, chat_id: int | str = "",
    ) -> list[dict[str, Any]]:
        """從單則群組訊息偵測徵兆.

        在 L4 觀察者中呼叫，靜默偵測不回覆群組。
        Returns: [{signal_type, sender, content_snippet, suggestion, urgency}]
        """
        signals = []
        content_lower = content.lower()

        # 承諾偵測
        for kw in _COMMITMENT_KEYWORDS:
            if kw in content:
                signals.append({
                    "signal_type": "commitment",
                    "sender": sender_name,
                    "content_snippet": content[:100],
                    "suggestion": f"📌 你剛對 {sender_name} 承諾了「{kw}」相關的事。要不要設個提醒確保如期完成？",
                    "urgency": "medium",
                    "chat_id": str(chat_id),
                })
                break

        # 機會偵測
        for kw in _OPPORTUNITY_KEYWORDS:
            if kw in content:
                signals.append({
                    "signal_type": "opportunity",
                    "sender": sender_name,
                    "content_snippet": content[:100],
                    "suggestion": f"💰 {sender_name} 提到「{kw}」——這可能是一個服務機會。要不要主動了解他的需求？",
                    "urgency": "medium",
                    "chat_id": str(chat_id),
                })
                break

        # 風險偵測
        for kw in _RISK_KEYWORDS:
            if kw in content:
                signals.append({
                    "signal_type": "risk",
                    "sender": sender_name,
                    "content_snippet": content[:100],
                    "suggestion": f"⚠️ {sender_name} 提到「{kw}」——可能有流失風險。建議主動關心，不要等他正式提出。",
                    "urgency": "high",
                    "chat_id": str(chat_id),
                })
                break

        return signals

    # ═══════════════════════════════════════
    # P1: 承諾追蹤
    # ═══════════════════════════════════════

    def detect_my_commitments(self, content: str, recipient: str = "") -> list[dict[str, Any]]:
        """偵測「我」對別人做的承諾.

        在 Zeal 發送訊息時呼叫。
        """
        commitments = []
        for kw in _COMMITMENT_KEYWORDS:
            if kw in content:
                commitments.append({
                    "type": "my_commitment",
                    "keyword": kw,
                    "to": recipient,
                    "content": content[:100],
                    "detected_at": datetime.now().isoformat(),
                    "due_reminder": (datetime.now() + timedelta(days=3)).isoformat(),
                })
                break
        return commitments

    # ═══════════════════════════════════════
    # P2: 機會偵測（增強版，結合人格）
    # ═══════════════════════════════════════

    def enrich_opportunity_with_personality(
        self, signal: dict[str, Any],
    ) -> dict[str, Any]:
        """用 Ares 人格資料增強機會偵測結果."""
        try:
            from museon.ares.profile_store import ProfileStore
            store = ProfileStore(self.data_dir)
            profiles = store.search(signal.get("sender", ""))
            if profiles:
                p = profiles[0]
                code = p["L2_personality"].get("wan_miu_code")
                if code:
                    signal["personality"] = code
                    # P 型（保護型）→ 先展示 ROI
                    if code.startswith("P"):
                        signal["approach"] = "先展示具體 ROI 和案例，不要談願景"
                    # A 型（利他型）→ 談共同目標
                    elif code.startswith("A"):
                        signal["approach"] = "從共同目標和使命切入，他會主動投入"
        except Exception:
            pass
        return signal

    # ═══════════════════════════════════════
    # 信號持久化
    # ═══════════════════════════════════════

    def save_signals(self, signals: list[dict[str, Any]]) -> None:
        """儲存待推播的信號."""
        existing = self._load_signals()
        existing.extend(signals)
        # 只保留最近 24 小時
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        existing = [s for s in existing if s.get("detected_at", "") > cutoff or "detected_at" not in s]
        tmp = self._signals_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
        tmp.rename(self._signals_path)

    def consume_signals(self) -> list[dict[str, Any]]:
        """讀取並清空待推播信號."""
        signals = self._load_signals()
        if signals:
            self._signals_path.write_text("[]")
        return signals

    def _load_signals(self) -> list[dict[str, Any]]:
        if self._signals_path.exists():
            try:
                return json.loads(self._signals_path.read_text())
            except Exception:
                return []
        return []
