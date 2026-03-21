"""OutwardTrigger — 外向型進化觸發器.

純 CPU，零 LLM Token。
訂閱現有 EventBus 事件，綜合判斷後發布 OUTWARD_SEARCH_NEEDED 事件。

雙軌設計：
  Track A（自我進化）：高原、架構瓶頸、週期掃描
  Track B（服務進化）：痛覺、預判、失敗

即時 vs 批次：
  HIGH 優先級 → 白天即時觸發（直通 IntentionRadar → ResearchEngine → DigestEngine）
  NORMAL/LOW → 凌晨 3:00 批次掃描
  共用同一個每日配額（DAILY_OUTWARD_CAP）
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══ 常數 ═══

DAILY_OUTWARD_CAP = 3              # 每日最多觸發次數（即時 + 批次合計）
DIRECTION_COOLDOWN_DAYS = 7        # 同方向冷卻天數

# Track A 觸發閾值
PLATEAU_MIN_RUNS = 5               # 高原偵測最少執行次數
PLATEAU_MAX_VARIANCE = 0.5         # 高原方差上限
ARCHITECTURE_NOTE_THRESHOLD = 3    # 架構瓶頸筆記重複閾值

# Track B 觸發閾值
DOMAIN_GAP_MIN_SAMPLES = 3         # 盲點雷達最少樣本
BEHAVIOR_SHIFT_MIN_COUNT = 3       # 行為偏移最少次數（週）
QUALITY_DECLINE_DELTA = 0.15       # 品質下滑差值閾值


class OutwardTrigger:
    """外向型進化觸發器 — 判斷何時該出去找知識.

    HIGH 優先級信號白天即時執行，NORMAL/LOW 排入凌晨批次。
    兩者共用同一個每日配額。
    """

    def __init__(
        self,
        workspace: Path,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._workspace = workspace
        self._event_bus = event_bus

        # 確保狀態目錄與預設檔案存在
        self._ensure_state_files()

        # 方向冷卻記錄：{direction_hash: last_triggered_iso}
        self._cooldown: Dict[str, str] = {}
        self._load_cooldown()

        # 每日計數（從持久化檔案載入）
        self._daily_count = 0
        self._daily_date: Optional[str] = None
        self._load_daily_counter()

        # 累積的信號（NORMAL/LOW 在 Nightly 掃描時一次處理）
        self._pending_signals: List[Dict] = []
        self._load_pending_signals()

        self._subscribe()

    # ─── EventBus 訂閱 ───

    def _subscribe(self) -> None:
        """訂閱相關事件以收集信號."""
        if not self._event_bus:
            return
        try:
            from museon.core.event_bus import (
                SKILL_QUALITY_SCORED,
                USER_FEEDBACK_SIGNAL,
            )
            self._event_bus.subscribe(
                SKILL_QUALITY_SCORED, self._on_skill_quality
            )
            self._event_bus.subscribe(
                USER_FEEDBACK_SIGNAL, self._on_feedback_signal
            )
            logger.info("OutwardTrigger subscribed to EventBus")
        except Exception as e:
            logger.warning(f"OutwardTrigger subscription failed: {e}")

    def _on_skill_quality(self, data: Optional[Dict] = None) -> None:
        """收集技能品質信號（B1 痛覺觸發）.

        HIGH 優先級 → 即時直通；否則存入 pending 等凌晨批次。
        """
        if not data:
            return
        blind_spots = data.get("blind_spots", [])
        for spot in blind_spots:
            signal = {
                "type": "domain_gap",
                "track": "service",
                "trigger_type": "pain",
                "priority": "HIGH",
                "domain": spot.get("domain", "unknown"),
                "skill": spot.get("skill", ""),
                "detail": spot.get("detail", ""),
                "timestamp": datetime.now(TZ8).isoformat(),
            }
            # HIGH → 即時直通
            self._handle_realtime_signal(signal)

    def _on_feedback_signal(self, data: Optional[Dict] = None) -> None:
        """收集品質趨勢信號（B3 失敗觸發）.

        HIGH 優先級 → 即時直通；否則存入 pending 等凌晨批次。
        """
        if not data:
            return
        if data.get("direction") == "declining":
            delta = abs(data.get("delta", 0))
            if delta >= QUALITY_DECLINE_DELTA:
                signal = {
                    "type": "quality_decline",
                    "track": "service",
                    "trigger_type": "failure",
                    "priority": "HIGH",
                    "delta": delta,
                    "recent_mean": data.get("recent_mean", 0),
                    "timestamp": datetime.now(TZ8).isoformat(),
                }
                # HIGH → 即時直通
                self._handle_realtime_signal(signal)

    def _handle_realtime_signal(self, signal: Dict) -> None:
        """處理即時信號：HIGH 直通 pipeline，其他存入 pending."""
        priority = signal.get("priority", "NORMAL")

        if priority == "HIGH":
            # 即時直通：信號 → 搜尋事件 → IntentionRadar → ResearchEngine → DigestEngine
            event = self._signal_to_event(signal)
            if event:
                result = self._try_emit(event)
                if result == "emitted":
                    self._execute_immediate(event)
                else:
                    logger.info(
                        f"OutwardTrigger: HIGH signal skipped: {result}"
                    )
        else:
            # NORMAL/LOW → 存入 pending，等凌晨批次
            self._pending_signals.append(signal)
            self._save_pending_signals()

    def _signal_to_event(self, signal: Dict) -> Optional[Dict]:
        """將原始信號轉為 OUTWARD_SEARCH_NEEDED 事件格式."""
        sig_type = signal.get("type", "")
        now = datetime.now(TZ8)

        if sig_type == "domain_gap":
            return {
                "track": "service",
                "trigger_type": "pain",
                "priority": "HIGH",
                "search_intent": (
                    f"在 '{signal['domain']}' 領域服務品質差，"
                    f"搜尋該領域最佳實踐"
                ),
                "related_skill": signal.get("skill", ""),
                "related_domain": signal["domain"],
                "evidence": {
                    "source": "eval_engine",
                    "data_points": [signal.get("detail", "")],
                },
                "timestamp": now.isoformat(),
            }
        elif sig_type == "quality_decline":
            return {
                "track": "service",
                "trigger_type": "failure",
                "priority": "HIGH",
                "search_intent": (
                    f"服務品質持續下滑 (delta={signal['delta']:.3f})，"
                    f"搜尋改進方法"
                ),
                "related_skill": "",
                "related_domain": "",
                "evidence": {
                    "source": "feedback_loop",
                    "data_points": [
                        f"delta={signal['delta']:.3f}",
                        f"recent_mean={signal['recent_mean']:.3f}",
                    ],
                },
                "timestamp": now.isoformat(),
            }

        return None

    def _execute_immediate(self, event: Dict) -> None:
        """即時執行完整 pipeline：IntentionRadar → ResearchEngine → DigestEngine."""
        try:
            import asyncio
            from museon.evolution.intention_radar import IntentionRadar
            from museon.evolution.digest_engine import DigestEngine
            from museon.research.research_engine import ResearchEngine

            # 1. 發布事件到 EventBus
            if self._event_bus:
                from museon.core.event_bus import OUTWARD_SEARCH_NEEDED
                self._event_bus.publish(OUTWARD_SEARCH_NEEDED, event)

            # 2. IntentionRadar 生成查詢
            radar = IntentionRadar(
                workspace=self._workspace,
                event_bus=self._event_bus,
            )
            queries = radar.generate_queries(event)
            if not queries:
                logger.info("OutwardTrigger: immediate — no queries generated")
                return

            # 3. ResearchEngine 執行搜尋
            research_engine = ResearchEngine(event_bus=self._event_bus)
            digest = DigestEngine(
                workspace=self._workspace,
                event_bus=self._event_bus,
            )

            loop = asyncio.new_event_loop()
            try:
                for query_item in queries:
                    result = loop.run_until_complete(
                        research_engine.research(
                            query=query_item["query"],
                            context_type=query_item.get("context_type", "outward_service"),
                            max_rounds=query_item.get("max_rounds", 2),
                        )
                    )

                    # 4. 有價值的結果送入 DigestEngine
                    if result.is_valuable and result.filtered_summary:
                        digest.ingest(
                            research_result={
                                "filtered_summary": result.filtered_summary,
                                "source_urls": [h.url for h in result.hits if h.url],
                            },
                            search_context={
                                "query": query_item["query"],
                                "track": query_item.get("track", "service"),
                                "trigger_type": query_item.get("trigger_type", ""),
                            },
                        )
            finally:
                loop.close()

            logger.info(
                f"OutwardTrigger: immediate pipeline done — "
                f"{len(queries)} queries, "
                f"[{event['track']}] {event['trigger_type']}"
            )

        except Exception as e:
            logger.warning(f"OutwardTrigger: immediate pipeline failed: {e}")

    # ─── Nightly 掃描入口 ───

    def scan(self) -> Dict:
        """Nightly Step 13.6 入口：掃描所有觸發源，產出搜尋需求.

        與白天即時觸發共用同一個每日配額。

        Returns:
            {
                "triggered": int,
                "events": [OUTWARD_SEARCH_NEEDED, ...],
                "skipped_reasons": [str, ...],
                "daily_used": int,
            }
        """
        self._reset_daily_counter_if_needed()

        events: List[Dict] = []
        skipped: List[str] = []

        # ═══ Track A：自我進化觸發 ═══
        a1 = self._check_plateau()
        a2 = self._check_architecture_bottleneck()
        a3 = self._check_rhythmic()

        for signal in [a1, a2, a3]:
            if signal:
                result = self._try_emit(signal)
                if result == "emitted":
                    events.append(signal)
                else:
                    skipped.append(result)

        # ═══ Track B：服務進化觸發（處理 NORMAL/LOW 的 pending 信號）═══
        b_signals = self._process_pending_signals()
        b2 = self._check_behavior_shift()
        if b2:
            b_signals.append(b2)

        for signal in b_signals:
            result = self._try_emit(signal)
            if result == "emitted":
                events.append(signal)
            else:
                skipped.append(result)

        # 發布事件
        if self._event_bus and events:
            from museon.core.event_bus import OUTWARD_SEARCH_NEEDED
            for event in events:
                self._event_bus.publish(OUTWARD_SEARCH_NEEDED, event)
                logger.info(
                    f"OutwardTrigger: [{event['track']}] "
                    f"{event['trigger_type']} → {event['search_intent'][:50]}"
                )

        # 持久化
        self._save_cooldown()
        self._save_daily_counter()

        return {
            "triggered": len(events),
            "events": events,
            "skipped_reasons": skipped,
            "daily_used": self._daily_count,
        }

    # ─── Track A 檢查方法 ───

    def _check_plateau(self) -> Optional[Dict]:
        """A1：高原觸發 — WEE 某 Skill 評分方差過低."""
        plateau_file = (
            self._workspace / "_system" / "wee" / "plateau_alerts.json"
        )
        if not plateau_file.exists():
            return None

        try:
            with open(plateau_file, "r", encoding="utf-8") as fh:
                alerts = json.load(fh)
        except Exception:
            return None

        # 取最新的高原警報
        active = [
            a for a in alerts
            if a.get("status") == "active"
            and a.get("runs", 0) >= PLATEAU_MIN_RUNS
        ]
        if not active:
            return None

        alert = active[0]
        skill = alert.get("skill", "unknown")
        return {
            "track": "self",
            "trigger_type": "plateau",
            "priority": "NORMAL",
            "search_intent": f"Skill '{skill}' 到達效能高原，搜尋突破性方法",
            "related_skill": skill,
            "related_domain": alert.get("domain", ""),
            "evidence": {
                "source": "wee",
                "data_points": [
                    f"runs={alert.get('runs')}",
                    f"variance={alert.get('variance', 0):.2f}",
                    f"avg_score={alert.get('avg_score', 0):.1f}",
                ],
            },
            "timestamp": datetime.now(TZ8).isoformat(),
        }

    def _check_architecture_bottleneck(self) -> Optional[Dict]:
        """A2：架構瓶頸觸發 — Morphenix 筆記同主題出現 ≥ 3 次."""
        notes_dir = self._workspace / "_system" / "morphenix" / "notes"
        if not notes_dir.exists():
            return None

        # 讀取所有筆記，提取主題
        topic_counts: Dict[str, int] = {}
        topic_examples: Dict[str, str] = {}

        for note_file in notes_dir.glob("*.json"):
            try:
                with open(note_file, "r", encoding="utf-8") as fh:
                    note = json.load(fh)
                topic = note.get("topic", "")
                if topic:
                    normalized = topic.lower().strip()[:50]
                    topic_counts[normalized] = topic_counts.get(normalized, 0) + 1
                    topic_examples[normalized] = topic
            except Exception:
                continue

        # 找出超過閾值的主題
        bottlenecks = [
            (topic, count)
            for topic, count in topic_counts.items()
            if count >= ARCHITECTURE_NOTE_THRESHOLD
        ]
        if not bottlenecks:
            return None

        # 取出現最多次的
        bottlenecks.sort(key=lambda x: x[1], reverse=True)
        top_topic, top_count = bottlenecks[0]
        original_topic = topic_examples.get(top_topic, top_topic)

        return {
            "track": "self",
            "trigger_type": "architecture",
            "priority": "NORMAL",
            "search_intent": f"架構瓶頸 '{original_topic}' 反覆出現 {top_count} 次，搜尋前沿解法",
            "related_skill": "",
            "related_domain": "architecture",
            "evidence": {
                "source": "morphenix_notes",
                "data_points": [
                    f"topic='{original_topic}'",
                    f"occurrences={top_count}",
                ],
            },
            "timestamp": datetime.now(TZ8).isoformat(),
        }

    def _check_rhythmic(self) -> Optional[Dict]:
        """A3：週期掃描觸發 — 每週日執行一次."""
        now = datetime.now(TZ8)
        if now.weekday() != 6:  # 6 = Sunday
            return None

        return {
            "track": "self",
            "trigger_type": "rhythmic",
            "priority": "LOW",
            "search_intent": "AI Agent 產業每週前沿動態掃描",
            "related_skill": "",
            "related_domain": "ai_agent",
            "evidence": {
                "source": "rhythmic",
                "data_points": [f"weekday=Sunday", f"date={now.strftime('%Y-%m-%d')}"],
            },
            "timestamp": now.isoformat(),
        }

    # ─── Track B 檢查方法 ───

    def _process_pending_signals(self) -> List[Dict]:
        """處理凌晨批次的 NORMAL/LOW pending 信號，轉為搜尋事件.

        注意：HIGH 信號已在白天即時處理過，不會出現在 pending 中。
        """
        events: List[Dict] = []

        # B1：痛覺（domain_gap）— NORMAL 級的
        pain_signals = [
            s for s in self._pending_signals if s["type"] == "domain_gap"
        ]
        if pain_signals:
            sig = pain_signals[0]
            events.append({
                "track": "service",
                "trigger_type": "pain",
                "priority": sig.get("priority", "NORMAL"),
                "search_intent": (
                    f"在 '{sig['domain']}' 領域服務品質差，"
                    f"搜尋該領域最佳實踐"
                ),
                "related_skill": sig.get("skill", ""),
                "related_domain": sig["domain"],
                "evidence": {
                    "source": "eval_engine",
                    "data_points": [sig.get("detail", "")],
                },
                "timestamp": datetime.now(TZ8).isoformat(),
            })

        # B3：失敗（quality_decline）— NORMAL 級的
        decline_signals = [
            s for s in self._pending_signals if s["type"] == "quality_decline"
        ]
        if decline_signals:
            sig = decline_signals[0]
            events.append({
                "track": "service",
                "trigger_type": "failure",
                "priority": sig.get("priority", "NORMAL"),
                "search_intent": (
                    f"服務品質持續下滑 (delta={sig['delta']:.3f})，"
                    f"搜尋改進方法"
                ),
                "related_skill": "",
                "related_domain": "",
                "evidence": {
                    "source": "feedback_loop",
                    "data_points": [
                        f"delta={sig['delta']:.3f}",
                        f"recent_mean={sig['recent_mean']:.3f}",
                    ],
                },
                "timestamp": datetime.now(TZ8).isoformat(),
            })

        # 清空 pending
        self._pending_signals.clear()
        self._clear_pending_signals_file()
        return events

    def _check_behavior_shift(self) -> Optional[Dict]:
        """B2：預判觸發 — 使用者行為趨勢偏移."""
        shift_file = (
            self._workspace / "_system" / "outward" / "behavior_shift.json"
        )
        if not shift_file.exists():
            return None

        try:
            with open(shift_file, "r", encoding="utf-8") as fh:
                shifts = json.load(fh)
        except Exception:
            return None

        active = [
            s for s in shifts
            if s.get("count", 0) >= BEHAVIOR_SHIFT_MIN_COUNT
            and s.get("status") == "active"
        ]
        if not active:
            return None

        shift = active[0]
        new_topic = shift.get("topic", "unknown")
        return {
            "track": "service",
            "trigger_type": "curiosity",
            "priority": "NORMAL",
            "search_intent": (
                f"使用者近期開始關注 '{new_topic}'，提前儲備領域知識"
            ),
            "related_skill": "",
            "related_domain": new_topic,
            "evidence": {
                "source": "trigger_weights",
                "data_points": [
                    f"topic='{new_topic}'",
                    f"weekly_count={shift.get('count', 0)}",
                ],
            },
            "timestamp": datetime.now(TZ8).isoformat(),
        }

    # ─── 防洪機制 ───

    def _try_emit(self, signal: Dict) -> str:
        """嘗試發布信號，檢查防洪限制.

        Returns:
            "emitted" 或 被跳過的原因字串
        """
        self._reset_daily_counter_if_needed()

        # 每日上限（即時 + 批次合計）
        if self._daily_count >= DAILY_OUTWARD_CAP:
            return f"daily_cap_reached ({self._daily_count}/{DAILY_OUTWARD_CAP})"

        # 方向冷卻
        direction_key = self._direction_hash(signal)
        if direction_key in self._cooldown:
            last_triggered = self._cooldown[direction_key]
            try:
                last_dt = datetime.fromisoformat(last_triggered)
                cooldown_end = last_dt + timedelta(days=DIRECTION_COOLDOWN_DAYS)
                if datetime.now(TZ8) < cooldown_end:
                    return (
                        f"direction_cooldown: '{signal.get('search_intent', '')[:30]}' "
                        f"until {cooldown_end.strftime('%Y-%m-%d')}"
                    )
            except Exception as e:
                logger.debug(f"[OUTWARD_TRIGGER] trigger failed (degraded): {e}")

        # 通過檢查
        self._daily_count += 1
        self._cooldown[direction_key] = datetime.now(TZ8).isoformat()
        self._save_daily_counter()
        self._save_cooldown()
        return "emitted"

    def _direction_hash(self, signal: Dict) -> str:
        """生成搜尋方向的唯一鍵."""
        parts = [
            signal.get("track", ""),
            signal.get("trigger_type", ""),
            signal.get("related_domain", ""),
            signal.get("related_skill", ""),
        ]
        return ":".join(p.lower().strip() for p in parts if p)

    def _reset_daily_counter_if_needed(self) -> None:
        """若跨日則重置計數器."""
        today = datetime.now(TZ8).strftime("%Y-%m-%d")
        if self._daily_date != today:
            self._daily_count = 0
            self._daily_date = today

    # ─── 狀態檔案初始化 ───

    def _ensure_state_files(self) -> None:
        """確保 outward/ 狀態目錄及預設 JSON 存在.

        解決 outward/ 目錄為空時各 _load_* 方法靜默跳過，
        導致外向演化觸發器永遠不啟動的問題。
        """
        outward_dir = self._workspace / "_system" / "outward"
        outward_dir.mkdir(parents=True, exist_ok=True)

        defaults: Dict[str, Any] = {
            "direction_cooldown.json": {},
            "daily_counter.json": {
                "date": datetime.now(TZ8).strftime("%Y-%m-%d"),
                "count": 0,
            },
            "pending_signals.json": [],
            "behavior_shift.json": [],
        }
        for filename, default_content in defaults.items():
            filepath = outward_dir / filename
            if not filepath.exists():
                try:
                    with open(filepath, "w", encoding="utf-8") as fh:
                        json.dump(default_content, fh, ensure_ascii=False, indent=2)
                    logger.info(f"OutwardTrigger: initialized {filename}")
                except Exception as e:
                    logger.warning(f"OutwardTrigger: init {filename} failed: {e}")

    # ─── 持久化：冷卻記錄 ───

    def _save_cooldown(self) -> None:
        """儲存方向冷卻記錄."""
        outward_dir = self._workspace / "_system" / "outward"
        outward_dir.mkdir(parents=True, exist_ok=True)
        cooldown_file = outward_dir / "direction_cooldown.json"
        try:
            # 清理過期冷卻
            now = datetime.now(TZ8)
            cleaned = {}
            for key, iso_str in self._cooldown.items():
                try:
                    dt = datetime.fromisoformat(iso_str)
                    if now - dt < timedelta(days=DIRECTION_COOLDOWN_DAYS):
                        cleaned[key] = iso_str
                except Exception:
                    continue
            self._cooldown = cleaned

            with open(cooldown_file, "w", encoding="utf-8") as fh:
                json.dump(cleaned, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"OutwardTrigger: save cooldown failed: {e}")

    def _load_cooldown(self) -> None:
        """載入方向冷卻記錄."""
        cooldown_file = (
            self._workspace / "_system" / "outward" / "direction_cooldown.json"
        )
        if cooldown_file.exists():
            try:
                with open(cooldown_file, "r", encoding="utf-8") as fh:
                    self._cooldown = json.load(fh)
            except Exception:
                self._cooldown = {}

    # ─── 持久化：每日計數 ───

    def _save_daily_counter(self) -> None:
        """持久化每日觸發計數（跨實例共享）."""
        outward_dir = self._workspace / "_system" / "outward"
        outward_dir.mkdir(parents=True, exist_ok=True)
        counter_file = outward_dir / "daily_counter.json"
        try:
            with open(counter_file, "w", encoding="utf-8") as fh:
                json.dump({
                    "date": self._daily_date,
                    "count": self._daily_count,
                }, fh)
        except Exception as e:
            logger.error(f"OutwardTrigger: save daily counter failed: {e}")

    def _load_daily_counter(self) -> None:
        """載入每日觸發計數."""
        counter_file = (
            self._workspace / "_system" / "outward" / "daily_counter.json"
        )
        if not counter_file.exists():
            return

        try:
            with open(counter_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            saved_date = data.get("date", "")
            today = datetime.now(TZ8).strftime("%Y-%m-%d")
            if saved_date == today:
                self._daily_count = data.get("count", 0)
                self._daily_date = saved_date
            else:
                # 跨日，重置
                self._daily_count = 0
                self._daily_date = today
        except Exception as e:
            logger.debug(f"[OUTWARD_TRIGGER] JSON failed (degraded): {e}")

    # ─── 持久化：Pending 信號 ───

    def _save_pending_signals(self) -> None:
        """持久化 pending 信號（防止 Gateway 重啟丟失）."""
        outward_dir = self._workspace / "_system" / "outward"
        outward_dir.mkdir(parents=True, exist_ok=True)
        pending_file = outward_dir / "pending_signals.json"
        try:
            with open(pending_file, "w", encoding="utf-8") as fh:
                json.dump(self._pending_signals, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"OutwardTrigger: save pending signals failed: {e}")

    def _load_pending_signals(self) -> None:
        """載入 pending 信號."""
        pending_file = (
            self._workspace / "_system" / "outward" / "pending_signals.json"
        )
        if pending_file.exists():
            try:
                with open(pending_file, "r", encoding="utf-8") as fh:
                    self._pending_signals = json.load(fh)
            except Exception:
                self._pending_signals = []

    def _clear_pending_signals_file(self) -> None:
        """清除 pending 信號檔案."""
        pending_file = (
            self._workspace / "_system" / "outward" / "pending_signals.json"
        )
        try:
            if pending_file.exists():
                pending_file.write_text("[]", encoding="utf-8")
        except Exception as e:
            logger.debug(f"[OUTWARD_TRIGGER] data write failed (degraded): {e}")
