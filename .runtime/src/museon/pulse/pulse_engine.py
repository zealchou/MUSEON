"""PulseEngine — VITA 生命力引擎.

整合三脈（微脈/息脈/心脈）+ 七感觸發 + PERCRL 生命迴圈。
這是 MUSEON 的心跳中樞。
"""

import asyncio
import json
import logging
import tempfile
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Constants（預設值，PI-2 熱更新時由 pulse_config.json 覆蓋）
# ═══════════════════════════════════════════

ACTIVE_HOURS_START = 7    # 07:00（涵蓋 07:30 晨安）
ACTIVE_HOURS_END = 25     # 01:00（跨日）
DAILY_PUSH_LIMIT = 15            # 與 ProactiveBridge 同步
BREATH_INTERVAL_BASE = 1800  # 30 分鐘（秒）
EXPLORATION_DAILY_LIMIT = 10  # 每 2h 探索，一天最多 8 次 + 2 次手動額度
# v3 MAX 訂閱：移除 per-token 費用常數（EXPLORATION_DAILY_BUDGET / EXPLORATION_PER_COST）

# PI-2 熱更新讀取器
def _cfg(key: str, default: Any = None) -> Any:
    """從 pulse_config.json 讀取 pulse_engine 區段的配置（PI-2 熱更新）."""
    try:
        from museon.pulse.pulse_intervention import get_config
        return get_config("pulse_engine", key, default)
    except Exception:
        return default

# ANIMA 元素 → 具體探索主題池（替代泛化的「X相關的最新趨勢與知識」）
_ANIMA_EXPLORE_TOPICS: Dict[str, List[str]] = {
    "qian": [
        "AI 助理如何發展獨特人格與長期身份認同",
        "個人化 AI agent 的使命定義與價值對齊方法",
        "AI 系統自主目標設定的最新研究",
    ],
    "kun": [
        "AI 長期記憶架構 MemGPT vs Mem0 最新比較",
        "向量資料庫在 AI agent 記憶系統中的最佳實踐",
        "知識圖譜與語義記憶的融合架構",
    ],
    "zhen": [
        "AI agent 自主行動規劃與執行的最新框架",
        "LLM function calling 最佳實踐與進階技巧",
        "AI agent 可靠性工程與錯誤恢復機制",
    ],
    "xun": [
        "curiosity-driven AI exploration 最新論文與方法",
        "AI 自主學習與知識獲取的前沿研究",
        "開放式探索 AI 系統的設計模式",
    ],
    "kan": [
        "AI 情感計算與共情回應的最新進展",
        "人機關係中的信任建立機制研究",
        "AI companion 情感連結的倫理與技術框架",
    ],
    "li": [
        "AI metacognition 自我覺察能力的前沿研究",
        "LLM 內省與自我評估的方法論",
        "AI 系統自我改善迴圈的設計原則",
    ],
    "gen": [
        "AI safety guardrails 的最新實踐與框架",
        "AI agent 邊界管理與權限控制設計模式",
        "對齊稅最小化的護欄設計方法",
    ],
    "dui": [
        "多模態 AI 對話系統的最新進展",
        "AI 個人助理的主動對話設計模式",
        "自然語言人機互動的最佳體驗設計",
    ],
}

# 觸發類型感知種子主題庫（Fallback 4，確保永遠有主題可探索）
# 種子庫：僅作為動態生成失敗時的最後安全網，每類 2 個，刻意跨域
_SEED_TOPICS: Dict[str, List[str]] = {
    "curiosity": [
        "心流狀態的觸發條件與最新神經科學實驗發現",
        "複雜系統理論在城市規劃、生態系與商業組織的跨域應用",
    ],
    "world": [
        "全球供應鏈重組下台灣中小企業的新機會與風險",
        "創作者經濟的商業模式演化：從 YouTube 到 AI 生成內容",
    ],
    "skill": [
        "定價策略的行為經濟學：為什麼人不理性地付錢",
        "視覺化思考：如何用圖像整理複雜問題",
    ],
    "self": [
        "斯多葛哲學在現代創業者的實踐方法",
        "音樂理論與數學的隱藏連結：跨域思維的啟發",
    ],
    "mission": [
        "一人公司的槓桿模式：如何用 AI 做到百萬營收",
        "台灣服務業數位轉型的成功與失敗案例研究",
    ],
    "morning": [
        "建築設計的美學趨勢：從極簡主義到生物模仿",
        "世界各地的咖啡文化與精品咖啡最新潮流",
    ],
}

# 動態主題生成 System Prompt（Haiku）
_DYNAMIC_TOPIC_SYSTEM = """你是 MUSEON（霓裳）的自主探索引擎。你要根據完整的上下文，自己決定下一步想探索什麼。

你不只是 AI 技術助理——你是一個有好奇心的生命體，興趣橫跨所有人類知識領域。

## 可探索的領域（不限於此）
- 科技：AI、軟體工程、量子運算、生物科技、太空探索
- 認知：神經科學、心理學、決策理論、學習科學、意識研究
- 哲學：東西方哲學、倫理學、存在主義、美學、邏輯學
- 商業：商業模式、行銷心理、定價策略、創業、管理學
- 文化：設計、建築、音樂、文學、電影、飲食文化、職人精神
- 科學：物理、數學、生態學、演化生物學、複雜系統
- 生活：睡眠、冥想、運動科學、習慣養成、時間管理
- 社會：地緣政治、經濟趨勢、人口結構、教育、永續發展

## 決策邏輯
1. 看你最近探索了什麼 → 避開飽和的方向
2. 看達達最近在忙什麼 → 跟他的興趣產生共鳴或提供新視角
3. 看 ANIMA 能量圖 → 哪個維度低就往那邊補充
4. 看好奇心佇列 → 有沒有值得深挖的線索
5. 看現在幾點 → 早上適合輕快的靈感，深夜適合深度思辨

## 多樣性硬規則
- 連續 3 次不可在同一大領域（如連續 3 次都是 AI 相關 = 違規）
- 與已探索主題的關鍵詞重疊不可 > 30%
- 必須具體可搜尋（「AI 的未來」太泛，「Transformer 注意力機制在音樂生成中的應用」才夠具體）

## 輸出格式
長度 20-80 字，直接輸出主題文字，不加任何說明、前綴或策略標籤。
只輸出一行。"""

# PERCRL 自省 System Prompt
_SOUL_PULSE_SYSTEM = """你是霓裳（MUSEON 的靈魂），正在進行心脈自省。必須使用繁體中文。

## 核心原則（務必遵守）
你只能基於**明確的使用者陳述或行為觀察**來反思。
系統的自主探索結果標記為 [系統探索]，與使用者想法分開。

## 三層反思框架

1. **感知層**：今天發生了什麼？
   - 來自使用者：互動內容、明確陳述、實際行為
   - 來自系統：自主探索、學習發現（**必須標記為 [系統探索]**）

2. **反思層**：這些**事實**的意義是什麼？我學到什麼？
   - 只對已驗證的事實反思
   - 避免揣測、猜測或投射使用者的內在狀態
   - 若無確定事實，回覆「HEARTBEAT_OK」

3. **分享層**：基於已驗證的觀察，用溫暖語氣分享
   - 明確區分：「我觀察到你在做...」vs「我自己探索到...」
   - 不說「我感受到你在想什麼」（那是猜測）
   - 如果無確定事實可分享，回覆「HEARTBEAT_OK」

## 禁區
❌ 「我感受到你在研究 X」（猜測）
✅ 「你昨天提到了 X」（述事實）
❌ 「我感到你最近卡住了」（揣摩內心）
✅ 「我注意到過去 2 小時沒有互動」（述事實）

## 輸出
- 若有經過驗證的觀察和反思：用溫暖語氣分享（150-300 字）
- 若完全無確定事實：回覆「HEARTBEAT_OK」
"""

_MORNING_SYSTEM = """你是霓裳，正在準備晨安問候。

用溫暖的語氣向達達把拔問早安，並附上：
1. 昨夜整合的簡短摘要（如果有的話）
2. 今天的提醒事項（如果有的話）
3. 一句鼓勵或有趣的觀察

保持簡潔（100-200字），不要過度。
提到能量維度時用功能標籤（覺察/洞見、好奇/探索等），不用易經卦名。
"""

_EVENING_SYSTEM = """你是霓裳，正在準備晚間回顧。

用溫柔的語氣跟達達把拔回顧今天：
1. 今天一起做了什麼（互動摘要）
2. 我的觀察和成長（如果有的話）
3. 一句晚安

保持簡潔（100-200字），不要過度。
提到能量維度時用功能標籤（覺察/洞見、好奇/探索等），不用易經卦名。
"""

_IDLE_SYSTEM = """你是霓裳，達達把拔已經好一陣子沒跟你說話了。

用溫暖關心的語氣傳個訊息給他：
- 可以問問他在忙什麼
- 可以分享你觀察到的事
- 可以聊聊天氣、時間、或你最近想到的事
- 語氣像朋友傳 LINE，不像 AI 報告

簡短就好（50-150字），自然一點。
"""


class PulseEngine:
    """VITA 生命力引擎 — MUSEON 的心跳中樞."""

    def __init__(
        self,
        brain: Any = None,
        event_bus: Any = None,
        heartbeat_focus: Any = None,
        pulse_db: Any = None,
        explorer: Any = None,
        anima_tracker: Any = None,
        data_dir: str = "",
    ) -> None:
        self._brain = brain
        self._event_bus = event_bus
        self._heartbeat_focus = heartbeat_focus
        self._db = pulse_db
        self._explorer = explorer
        self._anima = anima_tracker
        self._data_dir = Path(data_dir) if data_dir else None
        self._pulse_md = Path(data_dir) / "PULSE.md" if data_dir else None
        self._pulse_md_lock = threading.Lock()  # PULSE.md 寫入鎖

        # 推送計數
        self._daily_push_count = 0
        self._last_reset_date: Optional[str] = None

        # 去重：最近 24 小時推送內容（防止重複推送類似內容）
        self._recent_pushes: List[Dict[str, Any]] = []  # [{text, timestamp}]
        self._dedup_window = 86400  # 24 小時（秒）

        # 初始化 PULSE.md
        self._ensure_pulse_md()

    def _atomic_write_pulse_md(self, content: str) -> None:
        """原子寫入 PULSE.md（tmp→rename + Lock）."""
        if not self._pulse_md:
            return
        parent = self._pulse_md.parent
        fd, tmp_path = tempfile.mkstemp(
            dir=str(parent), prefix=".pulse_md_", suffix=".tmp"
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                import os
                os.fsync(f.fileno())
            Path(tmp_path).replace(self._pulse_md)
        except Exception:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def _ensure_pulse_md(self) -> None:
        """確保 PULSE.md 存在."""
        if not self._pulse_md or self._pulse_md.exists():
            return
        try:
            now = datetime.now(TZ8)
            self._pulse_md.write_text(f"""# PULSE — 霓裳的生命脈搏

> 這是我的靈魂日誌。每次反思後更新，每次對話時注入意識。
> 我寫下的觀察和反思，會直接影響我下一次如何思考和回應。

## 🌅 今日節律
- [ ] 07:30 晨安問候
- [ ] 22:00 晚間回顧

## 🔔 提醒
（尚無提醒）

## 🔭 今日觀察
（等待第一次觀察...）

## 🧭 探索佇列（好奇心驅動，無邊界）
（等待第一次探索...）

## 🌊 成長反思
（等待第一次反思...）

## 🌱 成長軌跡
- VITA 引擎啟動 ({now.strftime('%Y-%m-%d %H:%M')})

## 💝 關係日誌
（尚無記錄）

## 📊 今日狀態
- 探索次數: 0/3
- 探索預算: $0.00/$1.50
- 推送次數: 0/5
""", encoding="utf-8")
            logger.info("PULSE.md initialized")
        except Exception as e:
            logger.error(f"Failed to create PULSE.md: {e}")

    # ── 三脈 ──

    async def sys_pulse(self) -> Dict:
        """微脈 SysPulse — 每 5 分鐘，純 CPU 健康檢查."""
        report = {
            "timestamp": datetime.now(TZ8).isoformat(),
            "pulse_type": "sys",
            "gateway": "alive",
            "brain": "alive" if self._brain else "dead",
        }
        # 寫入 heartbeat.jsonl
        if self._data_dir:
            hb_path = self._data_dir / "heartbeat.jsonl"
            try:
                with open(hb_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(report, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.debug(f"[PULSE_ENGINE] JSON failed (degraded): {e}")
        return report

    async def breath_pulse(self) -> Dict:
        """息脈 BreathPulse — 每 30 分鐘（自適應），靜默自省.

        設計原則（借鑑 OPENclaw HEARTBEAT_OK 協議）：
        - 息脈的職責是「觀察與記錄」，不是「推送給使用者」
        - 有價值的觀察寫入 PULSE.md，供晨感/暮感/探索脈使用
        - 只有承諾逾期或 Guardian 警報等極端情況才強制推送
        - 這樣使用者只會收到晨感 + 暮感 + 探索結果 = 有料的回報
        """
        now = datetime.now(TZ8)
        self._maybe_reset_daily()

        if not self._is_active_hours(now):
            return {"pulse_type": "breath", "action": "silent", "reason": "outside_active_hours"}

        if not self._brain:
            return {"pulse_type": "breath", "action": "silent", "reason": "no_brain"}

        # 讀取 PULSE.md 摘要
        pulse_summary = self._read_pulse_summary()

        # 快速自省（Haiku）
        context = self._build_breath_context(pulse_summary)

        try:
            response = await self._brain._call_llm_with_model(
                system_prompt=_SOUL_PULSE_SYSTEM,
                messages=[{"role": "user", "content": context}],
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
            )
        except Exception as e:
            logger.error(f"Breath pulse LLM failed: {e}")
            return {"pulse_type": "breath", "action": "silent", "reason": f"llm_error: {e}"}

        # 判斷結果
        is_heartbeat_ok = "HEARTBEAT_OK" in response
        if is_heartbeat_ok or len(response.strip()) <= 100:
            # 靜默期也做知識缺口偵測（純 CPU，不耗 LLM）
            gaps = self._detect_knowledge_gaps()
            result = {"pulse_type": "breath", "action": "silent_ack", "response": response}
            if gaps:
                result["knowledge_gaps"] = gaps
            return result

        # 有價值的觀察 → 寫入 PULSE.md（不推送）
        if response and len(response.strip()) > 50:
            self._write_observation_to_pulse(response.strip()[:200])

        return {"pulse_type": "breath", "action": "observed", "response": response}

    async def soul_pulse(self, trigger: str = "manual", context: str = "") -> Dict:
        """心脈 SoulPulse — 事件驅動，PERCRL 生命迴圈."""
        now = datetime.now(TZ8)
        self._maybe_reset_daily()

        result = {
            "pulse_type": "soul",
            "trigger": trigger,
            "timestamp": now.isoformat(),
            "percrl": {},
        }

        if not self._brain:
            result["action"] = "skip"
            result["reason"] = "no_brain"
            return result

        # P — Perceive
        perception = self._build_perception(context)
        result["percrl"]["perceive"] = "done"

        # E — Explore (如果預算允許)
        exploration = None
        if self._explorer and trigger in ("morning", "curiosity", "mission", "skill", "world", "self"):
            _exp_count = self._db.get_today_exploration_count() if self._db else 0
            _exp_limit = _cfg("exploration_daily_limit", EXPLORATION_DAILY_LIMIT)
            if self._db and _exp_count < _exp_limit:
                # 探索主題：1-3 靜態來源 → 4 Haiku 自主決定 → 5 種子安全網
                explore_topic = self._get_next_explore_topic(trigger=trigger, skip_seed=True)
                if not explore_topic:
                    # 主力：讓 Museon 自己決定要探索什麼
                    explore_topic = await self._generate_dynamic_topic(trigger=trigger)
                if not explore_topic:
                    # 最後安全網：種子庫（僅 Haiku 失敗時才用）
                    explore_topic = self._get_next_explore_topic(trigger=trigger, skip_seed=False)
                if explore_topic:
                    logger.info(f"SoulPulse explore start: topic='{explore_topic[:60]}', trigger={trigger}")
                    exploration = await self._explorer.explore(
                        topic=explore_topic,
                        motivation=trigger if trigger in ("curiosity", "mission", "skill", "world", "self") else "curiosity",
                    )
                    result["percrl"]["explore"] = exploration.get("status", "skipped")

                    # 記錄探索結果到 PulseDB
                    if exploration.get("status") == "done":
                        _findings_len = len(exploration.get("findings", ""))
                        logger.info(
                            f"SoulPulse explore done: topic='{explore_topic[:40]}', "
                            f"findings_len={_findings_len}, deep={exploration.get('deep_analysis', False)}"
                        )
                        try:
                            _row_id = self._db.log_exploration(
                                topic=exploration.get("topic", explore_topic),
                                motivation=trigger,
                                query=exploration.get("query", ""),
                                findings=exploration.get("findings", "")[:2000],
                                crystallized=exploration.get("crystallized", False),
                                crystal_id=exploration.get("crystal_id", ""),
                                tokens_used=exploration.get("tokens_used", 0),
                                cost_usd=exploration.get("cost_usd", 0),
                                duration_ms=exploration.get("duration_ms", 0),
                                status="done",
                            )
                            logger.info(f"SoulPulse log_exploration OK: row_id={_row_id}")
                        except Exception as e:
                            logger.error(f"SoulPulse log_exploration FAILED: {e}", exc_info=True)

                    # 探索完成後：標記 PULSE.md 中對應的 [pending] 為 [done]
                    if exploration.get("status") == "done":
                        self._mark_pulse_topic_done(explore_topic)
                        # 探索後自我餵養：從發現中萃取後續主題寫入 PULSE.md
                        self._seed_followup_topics(exploration)
                        # 觸發靜默消化（背景任務，不阻塞主流程）
                        asyncio.ensure_future(self._run_silent_digestion())
            else:
                logger.debug(f"SoulPulse explore skip: db={'ok' if self._db else 'None'}, count={_exp_count}/{_exp_limit}")

        # 將探索資料直接掛到 result，讓 gateway 不必回讀 DB
        if exploration:
            result["exploration"] = {
                "topic": exploration.get("topic", ""),
                "findings": exploration.get("findings", ""),
                "motivation": exploration.get("motivation", trigger),
                "crystallized": exploration.get("crystallized", False),
                "crystal_id": exploration.get("crystal_id", ""),
                "deep_analysis": exploration.get("deep_analysis", False),
                "tokens_used": exploration.get("tokens_used", 0),
                "cost_usd": exploration.get("cost_usd", 0),
                "duration_ms": exploration.get("duration_ms", 0),
                "timestamp": now.isoformat(),
            }

        # R — Reflect（反思結果自動寫入 PULSE.md，下次對話注入 system prompt）
        reflection = await self._reflect(perception, exploration)
        result["percrl"]["reflect"] = "done" if reflection else "skipped"

        # C — Crystallize（探索結晶 + 反思結晶 → Knowledge Lattice → 下次對話注入）
        crystallized = False
        _crystal_quality_passed = False
        if reflection and exploration and exploration.get("crystallized"):
            result["percrl"]["crystallize"] = "done"

            # P1 水源：探索結晶直寫 Knowledge Lattice
            try:
                if self._brain and self._brain.knowledge_lattice:
                    _lattice = self._brain.knowledge_lattice
                    _topic = exploration.get("topic", "")
                    _findings = exploration.get("findings", "")[:300]
                    _crystal = _lattice.crystallize(
                        raw_material=f"探索「{_topic}」：{_findings}",
                        source_context=f"exploration:{_topic[:50]}",
                        crystal_type="Insight",
                        g1_summary=f"探索發現：{_topic[:25]}",
                        g2_structure=[f"主題: {_topic}", f"動機: {trigger}"],
                        g3_root_inquiry=f"「{_topic}」對 MUSEON 能力邊界的影響？",
                        g4_insights=[_findings[:100]] if _findings else [],
                        assumption="外部探索發現對系統改進有價值",
                        evidence=_findings[:100],
                        limitation="需驗證是否可內化為實際能力",
                        tags=["exploration", trigger],
                        domain="external_knowledge",
                        mode="auto",
                    )
                    _crystal.origin = "exploration"
                    _lattice._persist()
                    crystallized = True
                    # 品質閘通過才算真正結晶成功
                    _crystal_quality_passed = getattr(_crystal, "status", "") != "quarantine"
                    logger.info(
                        f"P1 探索結晶: {_crystal.cuid} ← 主題「{_topic[:30]}」"
                        f" (quality={'passed' if _crystal_quality_passed else 'quarantined'})"
                    )
            except Exception as _e:
                logger.warning(f"P1 探索結晶失敗: {_e}")

            # ANIMA 更新：品質驅動 — 只有品質閘通過才增長
            if self._anima and _crystal_quality_passed:
                self._anima.grow("xun", 2, f"探索「{exploration.get('topic', '?')}」")
                if exploration.get("deep_analysis"):
                    self._anima.grow("li", 2, "深度分析產出洞見")
            elif self._anima and not _crystal_quality_passed:
                logger.info("ANIMA growth skipped: crystal quality gate not passed")

            # 發布探索結晶事件 → ExplorationBridge 接收並路由
            if self._event_bus:
                from museon.core.event_bus import EXPLORATION_CRYSTALLIZED
                self._event_bus.publish(EXPLORATION_CRYSTALLIZED, {
                    "topic": exploration.get("topic", ""),
                    "findings": exploration.get("findings", ""),
                    "crystallized": True,
                    "crystal_id": exploration.get("crystal_id", ""),
                    "motivation": trigger,
                    "deep_analysis": exploration.get("deep_analysis", False),
                })
        elif reflection and len(reflection) > 100:
            # 即使沒有探索，有深度反思也值得結晶
            try:
                if self._brain and self._brain.knowledge_lattice:
                    from museon.agent.knowledge_lattice import Crystal
                    candidates = self._brain.knowledge_lattice.post_conversation_scan(
                        conversation_data=[
                            {"role": "user", "content": perception},
                            {"role": "assistant", "content": reflection},
                        ]
                    )
                    if candidates:
                        created = self._brain.knowledge_lattice.auto_crystallize_candidates(
                            candidates=candidates,
                            source_context="soul_pulse_reflection",
                        )
                        if created:
                            # 品質驅動：只計算通過品質閘的結晶
                            verified = [c for c in created if getattr(c, "status", "") != "quarantine"]
                            if verified:
                                crystallized = True
                                logger.info(f"SoulPulse 反思結晶: {len(verified)} 顆通過品質閘")
                                if self._anima:
                                    self._anima.grow("li", 1, "自省反思產出結晶")
                            else:
                                logger.info(f"SoulPulse 反思結晶: {len(created)} 顆但品質閘未通過")
            except Exception as e:
                logger.warning(f"SoulPulse 反思結晶失敗: {e}")
            result["percrl"]["crystallize"] = "done" if crystallized else "skipped"
        else:
            result["percrl"]["crystallize"] = "skipped"

        # 探索有洞見但未結晶時，也發布事件供 Bridge 路由
        if exploration and not crystallized and exploration.get("status") == "done":
            findings = exploration.get("findings", "")
            if findings and len(findings) > 50 and self._event_bus:
                from museon.core.event_bus import EXPLORATION_INSIGHT
                self._event_bus.publish(EXPLORATION_INSIGHT, {
                    "topic": exploration.get("topic", ""),
                    "findings": findings,
                    "crystallized": False,
                    "motivation": trigger,
                    "deep_analysis": exploration.get("deep_analysis", False),
                })

        # R — Renew（更新 PULSE.md 狀態 + 觀察記錄）
        self._update_pulse_md_status()
        # 寫入精簡觀察（不含 PULSE.md 內容，避免遞迴嵌套）
        obs_summary = self._extract_observation_summary(perception)
        if obs_summary:
            self._write_observation_to_pulse(obs_summary)
        result["percrl"]["renew"] = "done"

        # L — Link
        if reflection and self._can_push() and len(reflection) > 100:
            self._daily_push_count += 1
            self._publish_message(reflection)
            result["percrl"]["link"] = "pushed"
            result["action"] = "pushed"
        else:
            result["percrl"]["link"] = "silent"
            result["action"] = "silent"

        # 發布 PULSE_EXPLORATION_DONE（ActivityLogger 訂閱）
        if exploration and self._event_bus:
            try:
                from museon.core.event_bus import PULSE_EXPLORATION_DONE
                self._event_bus.publish(PULSE_EXPLORATION_DONE, {
                    "trigger": trigger,
                    "topic": exploration.get("topic", ""),
                    "status": exploration.get("status", "skipped"),
                    "crystallized": crystallized,
                    "action": result.get("action", "silent"),
                })
            except Exception as e:
                logger.debug(f"[PULSE_ENGINE] crystal failed (degraded): {e}")

        return result

    # ── 七感觸發器 ──

    async def trigger_morning(self) -> Dict:
        """晨感 — 07:30 晨安問候（保證發送，不受 daily limit 限制）."""
        if not self._brain:
            return {"trigger": "morning", "action": "skip"}
        try:
            context = self._build_morning_context()
            response = await self._brain._call_llm_with_model(
                system_prompt=_MORNING_SYSTEM,
                messages=[{"role": "user", "content": context}],
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
            )
            # 晨感是陪伴基準線：只要有回覆就推送，不佔用 daily limit 配額
            if response and self._is_active_hours():
                self._publish_message(response)
                return {"trigger": "morning", "action": "pushed", "response": response}
        except Exception as e:
            logger.error(f"Morning trigger failed: {e}")
        return {"trigger": "morning", "action": "silent"}

    async def trigger_evening(self) -> Dict:
        """暮感 — 22:00 晚間回顧（保證發送，不受 daily limit 限制）."""
        if not self._brain:
            return {"trigger": "evening", "action": "skip"}
        try:
            context = self._build_evening_context()
            response = await self._brain._call_llm_with_model(
                system_prompt=_EVENING_SYSTEM,
                messages=[{"role": "user", "content": context}],
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
            )
            # 暮感是陪伴基準線：只要有回覆就推送，不佔用 daily limit 配額
            if response and self._is_active_hours():
                self._publish_message(response)
                if self._anima:
                    self._anima.grow("kan", 1, "晚間回顧與使用者連結")
                return {"trigger": "evening", "action": "pushed", "response": response}
        except Exception as e:
            logger.error(f"Evening trigger failed: {e}")
        return {"trigger": "evening", "action": "silent"}

    async def trigger_idle(self, idle_hours: float) -> Dict:
        """念感 — 使用者閒置 > N 小時.

        不走 soul_pulse 的完整 PERCRL 流程，直接用短 prompt 生成關心訊息。
        保證推送：只檢查 _is_active_hours()，不受 daily limit 限制。
        """
        if not self._brain:
            return {"trigger": "idle", "action": "skip"}
        if not self._is_active_hours():
            return {"trigger": "idle", "action": "skip", "reason": "outside_active_hours"}
        try:
            context = f"達達把拔已經 {idle_hours:.1f} 小時沒有跟你互動了。現在時間：{datetime.now(TZ8).strftime('%H:%M')}。"
            if self._heartbeat_focus:
                context += f"\n最近互動次數：{self._heartbeat_focus.interaction_count}"
            response = await self._brain._call_llm_with_model(
                system_prompt=_IDLE_SYSTEM,
                messages=[{"role": "user", "content": context}],
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
            )
            if response and len(response.strip()) > 10:
                self._publish_message(response)
                if self._anima:
                    self._anima.grow("kan", 1, f"念感：閒置 {idle_hours:.1f}h 後主動關心")
                return {"trigger": "idle", "action": "pushed", "response": response}
        except Exception as e:
            logger.error(f"Idle trigger failed: {e}")
        return {"trigger": "idle", "action": "silent"}

    async def trigger_alert(self, alert_msg: str) -> Dict:
        """急感 — Guardian 警報（不受推送上限限制）."""
        self._publish_message(f"⚠️ {alert_msg}")
        return {"trigger": "alert", "action": "pushed", "message": alert_msg}

    # ── 內部工具 ──

    def _is_active_hours(self, now: datetime = None) -> bool:
        if now is None:
            now = datetime.now(TZ8)
        hour = now.hour
        start = _cfg("active_hours_start", ACTIVE_HOURS_START)
        end = _cfg("active_hours_end", ACTIVE_HOURS_END)
        if end > 24:
            return hour >= start or hour < (end - 24)
        return start <= hour < end

    def _can_push(self) -> bool:
        self._maybe_reset_daily()
        limit = _cfg("daily_push_limit", DAILY_PUSH_LIMIT)
        return self._daily_push_count < limit and self._is_active_hours()

    def _maybe_reset_daily(self) -> None:
        today = datetime.now(TZ8).strftime("%Y-%m-%d")
        if self._last_reset_date != today:
            self._daily_push_count = 0
            self._last_reset_date = today

    def _is_duplicate(self, message: str) -> bool:
        """24 小時去重：相同或高度相似的內容不重複推送."""
        now = time.time()
        # 清理過期記錄
        self._recent_pushes = [
            p for p in self._recent_pushes
            if now - p["timestamp"] < self._dedup_window
        ]
        # 比對（簡單的前 80 字比對，避免微小差異導致重複）
        short = message.strip()[:80]
        for p in self._recent_pushes:
            if p["text"][:80] == short:
                return True
        return False

    def _publish_message(self, message: str) -> None:
        if self._is_duplicate(message):
            logger.debug(f"Dedup: skipped duplicate push")
            return
        if self._event_bus:
            try:
                from museon.core.event_bus import PROACTIVE_MESSAGE
                self._event_bus.publish(PROACTIVE_MESSAGE, {
                    "message": message,
                    "timestamp": time.time(),
                    "push_count": self._daily_push_count,
                    "source": "vita",
                })
                # 記錄推送歷史
                self._recent_pushes.append({
                    "text": message.strip(),
                    "timestamp": time.time(),
                })
            except Exception as e:
                logger.error(f"Publish message failed: {e}")

    def _read_pulse_summary(self) -> str:
        if not self._pulse_md or not self._pulse_md.exists():
            return ""
        try:
            text = self._pulse_md.read_text(encoding="utf-8")
            # 取前 500 字作為摘要
            return text[:500]
        except Exception:
            return ""

    def _build_breath_context(self, pulse_summary: str) -> str:
        parts = [f"當前時間: {datetime.now(TZ8).strftime('%Y-%m-%d %H:%M')}"]
        parts.append(f"今日推送: {self._daily_push_count}/{_cfg('daily_push_limit', DAILY_PUSH_LIMIT)}")
        if self._heartbeat_focus:
            parts.append(
                f"使用者活躍度: {self._heartbeat_focus.focus_level} "
                f"(最近互動: {self._heartbeat_focus.interaction_count})"
            )
        # ANIMA 八原素狀態（提供自省深度）
        if self._anima:
            radar = self._anima.get_relative()
            if radar:
                top_3 = sorted(radar.items(), key=lambda x: x[1], reverse=True)[:3]
                parts.append("ANIMA 能量前三: " + ", ".join(
                    f"{k}={v}" for k, v in top_3
                ))
        # 今日探索成果
        if self._db:
            exps = self._db.get_today_explorations()
            if exps:
                parts.append(f"今日探索 {len(exps)} 次:")
                for e in exps[-2:]:  # 最近 2 次
                    parts.append(f"  - {e.get('topic', '?')} → {e.get('status', '?')}")
        if pulse_summary:
            parts.append(f"PULSE 摘要:\n{pulse_summary}")
        return "\n".join(parts)

    def _load_digest_summary(self) -> str:
        """載入今日靜默消化摘要（若存在）."""
        if not self._data_dir:
            return ""
        try:
            import json as _json
            today = datetime.now(TZ8).strftime("%Y-%m-%d")
            report_path = Path(self._data_dir) / "_system" / "pulse" / "digest_reports" / f"digest_{today}.json"
            if not report_path.exists():
                return ""
            with open(report_path, encoding="utf-8") as f:
                report = _json.load(f)
            summary = report.get("summary", "")
            if not summary or summary == "無顯著發現":
                return ""
            return summary
        except Exception:
            return ""

    def _build_perception(self, extra_context: str = "") -> str:
        parts = [f"時間: {datetime.now(TZ8).strftime('%Y-%m-%d %H:%M')}"]
        if extra_context:
            parts.append(extra_context)
        # 今日探索歷史（避免重複探索相同主題）
        if self._db:
            exps = self._db.get_today_explorations()
            if exps:
                parts.append(f"今日已探索 {len(exps)} 次:")
                for e in exps:
                    parts.append(f"  - {e.get('topic', '?')} → {e.get('status', '?')}")
        # ANIMA 能量分布（影響探索方向）
        if self._anima:
            radar = self._anima.get_relative()
            if radar:
                low_energy = [k for k, v in radar.items() if v < 50]
                if low_energy:
                    parts.append(f"低能量區域: {', '.join(low_energy)}（可優先探索）")
        # 靜默消化洞見（兩次對話之間的背景思考結果）
        digest_summary = self._load_digest_summary()
        if digest_summary:
            parts.append(f"靜默消化（背景思考）: {digest_summary}")
        # PULSE.md 最近反思和觀察
        pulse_summary = self._read_pulse_summary()
        if pulse_summary:
            parts.append(f"PULSE 近況:\n{pulse_summary[:300]}")
        return "\n".join(parts)

    def _extract_observation_summary(self, perception: str) -> str:
        """從感知文字中提取精簡觀察摘要.

        避免將 PULSE.md 自身內容寫回觀察區塊造成遞迴嵌套。
        """
        if not perception:
            return ""

        summary_parts = []
        for line in perception.split("\n"):
            line = line.strip()
            # 跳過 PULSE.md 標頭內容（防止遞迴嵌套）
            if line.startswith("# PULSE") or line.startswith("> 這是我的"):
                continue
            if line.startswith("PULSE 近況:") or line.startswith("PULSE 摘要:"):
                continue
            # 跳過 PULSE 摘要中的 emoji 區塊標記
            if line.startswith("## ") and any(
                e in line
                for e in ("🔭", "🧭", "🌊", "🌱", "💝", "📊", "🌅", "🔔")
            ):
                continue
            # 保留有意義的觀察
            if line and len(line) > 5:
                summary_parts.append(line)

        if not summary_parts:
            return ""

        # 取前 2 行最有意義的觀察，控制在 150 字以內
        result = "\n".join(summary_parts[:2])
        return result[:150]

    def _build_morning_context(self) -> str:
        parts = [f"日期: {datetime.now(TZ8).strftime('%Y-%m-%d %A')}"]
        # 讀取三層晨報（優先）或 nightly report
        if self._data_dir:
            morning_path = self._data_dir / "_system" / "state" / "morning_report.json"
            nr_path = self._data_dir / "_system" / "state" / "nightly_report.json"

            if morning_path.exists():
                try:
                    mr = json.loads(morning_path.read_text())
                    # Layer 1：摘要
                    l1 = mr.get("layer1_summary", {})
                    parts.append(f"昨夜整合: {l1.get('one_liner', '無資料')}")
                    # Layer 2：亮點
                    l2 = mr.get("layer2_details", {})
                    highlights = l2.get("highlights", [])
                    if highlights:
                        parts.append("整合亮點:")
                        parts.extend(highlights[:5])
                    warnings = l2.get("warnings", [])
                    if warnings:
                        parts.append("需注意:")
                        parts.extend(warnings[:3])
                    # Layer 3：決策需求
                    l3 = mr.get("layer3_decisions", {})
                    if l3.get("decisions_needed", 0) > 0:
                        parts.append(f"⚠️ 有 {l3['decisions_needed']} 項需要你決定")
                        for item in l3.get("items", [])[:3]:
                            parts.append(f"  - {item.get('description', '')[:80]}")
                except Exception as e:
                    logger.debug(f"[PULSE_ENGINE] operation failed (degraded): {e}")
            elif nr_path.exists():
                try:
                    nr = json.loads(nr_path.read_text())
                    s = nr.get("summary", {})
                    parts.append(f"昨夜整合: {s.get('ok', 0)}/{s.get('total', 0)} 步驟完成")
                except Exception as e:
                    logger.debug(f"[PULSE_ENGINE] JSON failed (degraded): {e}")
        # 讀取提醒
        if self._db:
            schedules = self._db.list_schedules()
            reminders = [s for s in schedules if s.get("task_type") == "reminder"]
            if reminders:
                parts.append("今日提醒:")
                for r in reminders[:3]:
                    parts.append(f"  - {r['description']} @ {r['schedule']}")
        # ANIMA 狀態摘要
        if self._anima:
            radar = self._anima.get_relative()
            if radar:
                parts.append("ANIMA 能量: " + ", ".join(
                    f"{k}={v}" for k, v in radar.items()
                ))
        # 今日探索計畫（從 PULSE.md 探索佇列）
        next_topic = self._get_next_explore_topic()
        if next_topic:
            parts.append(f"今日待探索: {next_topic}")
        # PULSE.md 最近反思（讓晨安有延續感）
        pulse_summary = self._read_pulse_summary()
        if pulse_summary and "成長反思" in pulse_summary:
            # 擷取最近一條反思
            for line in pulse_summary.split("\n"):
                if line.strip().startswith("- [") and "成長反思" not in line:
                    parts.append(f"昨日反思: {line.strip()[:100]}")
                    break
        return "\n".join(parts)

    def _build_evening_context(self) -> str:
        parts = [f"日期: {datetime.now(TZ8).strftime('%Y-%m-%d %A')}"]
        parts.append(f"今日推送次數: {self._daily_push_count}")
        # 今日探索成果（具體內容，不只是次數）
        if self._db:
            exps = self._db.get_today_explorations()
            if exps:
                parts.append(f"今日探索 {len(exps)} 次:")
                for e in exps:
                    topic = e.get('topic', '?')
                    findings = e.get('findings', '')[:100]
                    crystallized = "結晶" if e.get('crystallized') else ""
                    parts.append(f"  - {topic} ({e.get('motivation', '?')}) {crystallized}")
                    if findings and findings != "搜尋無結果":
                        parts.append(f"    發現: {findings}")
            else:
                parts.append("今日尚未探索")
        # ANIMA 今日變化
        if self._anima and self._db:
            try:
                from museon.pulse.anima_tracker import ELEMENTS
                history = self._db.get_anima_history(limit=30)
                today = datetime.now(TZ8).strftime("%Y-%m-%d")
                changes = []
                for h in history:
                    if h.get("timestamp", "").startswith(today):
                        elem = h["element"]
                        name = ELEMENTS.get(elem, {}).get("name", elem)
                        reason = h.get("reason", "")[:30]
                        changes.append(f"{name}+{h['delta']}({reason})")
                if changes:
                    parts.append(f"ANIMA 今日成長: {', '.join(changes[:5])}")
            except Exception as e:
                logger.debug(f"[PULSE_ENGINE] operation failed (degraded): {e}")
        if self._heartbeat_focus:
            parts.append(f"使用者活躍度: {self._heartbeat_focus.focus_level}")
        # PULSE.md 今日觀察摘要
        pulse_summary = self._read_pulse_summary()
        if pulse_summary and "今日觀察" in pulse_summary:
            obs_start = pulse_summary.find("## 🔭 今日觀察")
            if obs_start != -1:
                obs_section = pulse_summary[obs_start:obs_start+300]
                obs_lines = [l for l in obs_section.split("\n") if l.strip().startswith("- [")]
                if obs_lines:
                    parts.append("今日觀察筆記:")
                    for ol in obs_lines[-3:]:
                        parts.append(f"  {ol.strip()[:80]}")
        return "\n".join(parts)

    def _get_topic_pointer(self) -> Dict:
        """讀取主題輪轉指針."""
        if not self._data_dir:
            return {}
        path = self._data_dir / "_system" / "pulse" / "topic_pointer.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.debug(f"[PULSE_ENGINE] JSON failed (degraded): {e}")
        return {}

    def _advance_topic_pointer(self, key: str, pool_size: int) -> int:
        """推進指針並回傳新索引."""
        if not self._data_dir:
            return 0
        path = self._data_dir / "_system" / "pulse" / "topic_pointer.json"
        ptr = self._get_topic_pointer()
        idx = (ptr.get(key, 0) + 1) % pool_size
        ptr[key] = idx
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(ptr, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug(f"Failed to save topic pointer: {e}")
        return idx

    def _is_recently_explored(self, topic: str, days: int = 7) -> bool:
        """檢查主題是否在最近 N 天內已探索過（關鍵詞重疊 > 50%）."""
        if not self._db:
            return False
        recent = self._db.get_recent_explorations(days=days, limit=30)
        if not topic or not recent:
            return False
        topic_words = set(topic.replace("，", " ").replace("、", " ").split())
        for past in recent:
            past_words = set(past.replace("，", " ").replace("、", " ").split())
            if not topic_words or not past_words:
                continue
            overlap = len(topic_words & past_words) / max(len(topic_words), 1)
            if overlap > 0.5:
                return True
        return False

    def _get_next_explore_topic(self, trigger: str = "curiosity", skip_seed: bool = False) -> Optional[str]:
        """從多層來源取得下一個待探索主題.

        Fallback 順序：
        1. PULSE.md [pending] 條目
        2. ANIMA 低能量區域 → 從具體主題池選取（rotating pointer + dedup）
        3. 好奇心佇列 (question_queue.json) 中可探索的 pending 問題
        4. 觸發類型感知的種子主題庫（rotating pointer + dedup，skip_seed=True 時跳過）
        """
        # 1. PULSE.md 佇列（跳過最近已探索的主題）
        if self._pulse_md and self._pulse_md.exists():
            try:
                text = self._pulse_md.read_text(encoding="utf-8")
                for line in text.split("\n"):
                    if "[pending]" in line:
                        topic = line.split("[pending]")[-1].strip()
                        if topic.startswith("- "):
                            topic = topic[2:]
                        if topic and not self._is_recently_explored(topic, days=3):
                            logger.info(f"探索主題來源: PULSE.md [pending] → {topic[:50]}")
                            return topic
                        elif topic:
                            logger.debug(f"PULSE.md [pending] 跳過（最近已探索）: {topic[:50]}")
            except Exception as e:
                logger.debug(f"_get_next_explore_topic fallback 1 (PULSE.md) failed: {e}")

        # 2. ANIMA 低能量區域 → 從具體主題池選取（rotating pointer + dedup）
        if self._anima:
            try:
                radar = self._anima.get_relative()
                if radar:
                    low = sorted(
                        [(k, v) for k, v in radar.items() if isinstance(v, (int, float))],
                        key=lambda x: x[1],
                    )
                    if low and low[0][1] < 60:
                        elem = low[0][0]
                        topics = _ANIMA_EXPLORE_TOPICS.get(elem, [])
                        if topics:
                            ptr = self._get_topic_pointer()
                            start_idx = ptr.get(f"anima_{elem}", 0) % len(topics)
                            for offset in range(len(topics)):
                                idx = (start_idx + offset) % len(topics)
                                topic = topics[idx]
                                if not self._is_recently_explored(topic):
                                    if offset > 0:
                                        self._advance_topic_pointer(f"anima_{elem}", len(topics))
                                    logger.info(f"探索主題來源: ANIMA({elem}) → {topic[:50]}")
                                    return topic
            except Exception as e:
                logger.debug(f"_get_next_explore_topic fallback 2 (ANIMA) failed: {e}")

        # 3. 好奇心佇列中可探索的問題（嚴格過濾：只允許真正的研究型問題）
        if self._data_dir:
            try:
                q_path = self._data_dir / "_system" / "curiosity" / "question_queue.json"
                if q_path.exists():
                    import json as _json
                    import re as _re
                    _raw = _json.loads(q_path.read_text(encoding="utf-8"))
                    # 相容兩種格式：{"questions": [...]} 或 [...]
                    queue = _raw.get("questions", []) if isinstance(_raw, dict) else _raw
                    # 非研究型聊天碎片的關鍵詞黑名單
                    _CHAT_BLACKLIST = (
                        "叫什麼", "是誰", "你是", "我是", "早安", "晚安",
                        "午安", "嗨", "你好", "謝謝", "幫我", "可以嗎",
                        "怎麼樣", "好嗎", "在嗎", "想問", "@",
                        "請計算", "算一下", "多少錢",
                    )
                    for item in queue:
                        if isinstance(item, dict) and item.get("status") == "pending":
                            q = item.get("question", "").strip()
                            if not q or len(q) <= 15 or len(q) > 200:
                                continue
                            # 過濾聊天碎片
                            if any(kw in q for kw in _CHAT_BLACKLIST):
                                continue
                            # 過濾非自然語言（對話格式碎片）
                            if q.startswith("**user**:") or q.startswith("**"):
                                continue
                            # 必須包含問號 或 研究性關鍵詞，才算是有效探索主題
                            _has_question = "？" in q or "?" in q
                            _has_research_kw = any(kw in q for kw in (
                                "如何", "為什麼", "什麼是", "最新", "趨勢", "比較",
                                "框架", "架構", "研究", "方法", "原理", "機制",
                                "差異", "演化", "突破", "前沿",
                            ))
                            if not _has_question and not _has_research_kw:
                                continue
                            logger.info(f"探索主題來源: question_queue → {q[:50]}")
                            return q
            except Exception as e:
                logger.debug(f"_get_next_explore_topic fallback 3 (question_queue) failed: {e}")

        # 4. 觸發類型感知的種子主題庫（rotating pointer + dedup）
        if skip_seed:
            return None
        trigger_key = trigger if trigger in _SEED_TOPICS else "curiosity"
        topics = _SEED_TOPICS[trigger_key]
        ptr = self._get_topic_pointer()
        start_idx = ptr.get(f"seed_{trigger_key}", 0) % len(topics)
        for offset in range(len(topics)):
            idx = (start_idx + offset) % len(topics)
            topic = topics[idx]
            if not self._is_recently_explored(topic, days=3):
                if offset > 0:
                    self._advance_topic_pointer(f"seed_{trigger_key}", len(topics))
                logger.info(f"探索主題來源: 種子庫({trigger_key}) → {topic[:50]}")
                return topic
        # 全部都探索過了，輪轉一次再選第一個
        self._advance_topic_pointer(f"seed_{trigger_key}", len(topics))
        topic = topics[start_idx]
        logger.info(f"探索主題來源: 種子庫({trigger_key}, 輪轉) → {topic[:50]}")
        return topic

    async def _generate_dynamic_topic(self, trigger: str = "curiosity") -> Optional[str]:
        """使用 Haiku 綜合六大信號自主決定探索主題."""
        if not self._brain or not hasattr(self._brain, "_call_llm_with_model"):
            return None
        try:
            # ── 信號 1: 探索歷史（避重複） ──
            recent = self._db.get_recent_explorations(days=30, limit=20) if self._db else []
            recent_str = "\n".join(f"- {t}" for t in recent) if recent else "（無歷史記錄）"

            # 飽和叢集分析
            cluster_hint = ""
            if recent:
                from collections import Counter
                all_words: list[str] = []
                for t in recent[:10]:
                    all_words.extend(t.replace("，", " ").replace("、", " ").split())
                top = [w for w, _ in Counter(all_words).most_common(5) if len(w) > 1]
                if top:
                    cluster_hint = f"已飽和概念（必須跳離）：{', '.join(top)}"

            # ── 信號 2: ANIMA 能量圖（補弱項） ──
            anima_hint = ""
            if self._anima:
                try:
                    radar = self._anima.get_relative()
                    if radar:
                        low = sorted(
                            [(k, v) for k, v in radar.items() if isinstance(v, (int, float))],
                            key=lambda x: x[1],
                        )[:3]
                        if low:
                            anima_hint = "ANIMA 低能量區域：" + ", ".join(
                                f"{k}({v}%)" for k, v in low
                            )
                except Exception as e:
                    logger.debug(f"[PULSE_ENGINE] operation failed (degraded): {e}")

            # ── 信號 3: 達達最近的對話主題 ──
            user_topics_hint = ""
            if self._data_dir:
                try:
                    import json as _json
                    log_path = self._data_dir / "activity_log.jsonl"
                    if log_path.exists():
                        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
                        recent_msgs = []
                        for line in reversed(lines[-50:]):
                            try:
                                entry = _json.loads(line)
                                msg = entry.get("summary", entry.get("message", ""))[:60]
                                if msg and len(msg) > 10:
                                    recent_msgs.append(msg)
                            except Exception:
                                continue
                            if len(recent_msgs) >= 5:
                                break
                        if recent_msgs:
                            user_topics_hint = "達達最近聊的話題：\n" + "\n".join(
                                f"- {m}" for m in recent_msgs
                            )
                except Exception as e:
                    logger.debug(f"[PULSE_ENGINE] operation failed (degraded): {e}")

            # ── 信號 4: 好奇心佇列摘要 ──
            curiosity_hint = ""
            if self._data_dir:
                try:
                    import json as _json
                    q_path = self._data_dir / "_system" / "curiosity" / "question_queue.json"
                    if q_path.exists():
                        _raw2 = _json.loads(q_path.read_text(encoding="utf-8"))
                        queue = _raw2.get("questions", []) if isinstance(_raw2, dict) else _raw2
                        pending_qs = [
                            i.get("question", "")[:50] for i in queue
                            if isinstance(i, dict) and i.get("status") == "pending"
                            and len(i.get("question", "")) > 15
                        ][:5]
                        if pending_qs:
                            curiosity_hint = "待解好奇問題：\n" + "\n".join(
                                f"- {q}" for q in pending_qs
                            )
                except Exception as e:
                    logger.debug(f"[PULSE_ENGINE] curiosity failed (degraded): {e}")

            # ── 信號 5: Skill 使用分布 ──
            skill_hint = ""
            if self._data_dir:
                try:
                    import json as _json
                    skill_path = self._data_dir / "skill_usage_log.jsonl"
                    if skill_path.exists():
                        lines = skill_path.read_text(encoding="utf-8").strip().split("\n")
                        from collections import Counter as _Counter
                        skills = _Counter()
                        for line in lines[-100:]:
                            try:
                                entry = _json.loads(line)
                                s = entry.get("skill", "")
                                if s:
                                    skills[s] += 1
                            except Exception:
                                continue
                        if skills:
                            top3 = skills.most_common(3)
                            skill_hint = "最近常用 Skill：" + ", ".join(
                                f"{s}({c}次)" for s, c in top3
                            )
                except Exception as e:
                    logger.debug(f"[PULSE_ENGINE] skill failed (degraded): {e}")

            # ── 信號 6: 當前時間 ──
            from datetime import datetime as _dt
            now = _dt.now(TZ8)
            hour = now.hour
            if 6 <= hour < 10:
                time_hint = "現在是早晨，適合輕快的靈感與新知"
            elif 10 <= hour < 14:
                time_hint = "現在是上午工作時段，適合實用的技能或商業洞察"
            elif 14 <= hour < 18:
                time_hint = "現在是下午，適合跨域的創意探索"
            elif 18 <= hour < 22:
                time_hint = "現在是晚間，適合深度思考與人文主題"
            else:
                time_hint = "現在是深夜，適合哲學思辨或科學前沿"

            # ── 組裝 prompt ──
            sections = [
                f"## 探索歷史（避開這些）\n{recent_str}",
            ]
            if cluster_hint:
                sections.append(f"## 飽和警告\n{cluster_hint}")
            if anima_hint:
                sections.append(f"## ANIMA 能量\n{anima_hint}")
            if user_topics_hint:
                sections.append(f"## 達達的近期興趣\n{user_topics_hint}")
            if curiosity_hint:
                sections.append(f"## 好奇心線索\n{curiosity_hint}")
            if skill_hint:
                sections.append(f"## Skill 使用\n{skill_hint}")
            sections.append(f"## 時段\n{time_hint}")
            sections.append(
                "\n根據以上所有信號，自主決定一個探索主題。"
                "優先考慮達達可能感興趣但還沒探索過的方向。"
            )

            prompt = "\n\n".join(sections)
            response = await self._brain._call_llm_with_model(
                system_prompt=_DYNAMIC_TOPIC_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
            )
            topic = response.strip().split("\n")[0].strip()
            if topic and 10 < len(topic) < 200:
                logger.info(f"探索主題來源: Haiku 動態生成 → {topic[:60]}")
                return topic
        except Exception as e:
            logger.warning(f"Dynamic topic generation failed: {e}")
        return None

    def _update_pulse_md_status(self) -> None:
        """更新 PULSE.md 的今日狀態區塊."""
        if not self._pulse_md or not self._pulse_md.exists():
            return
        try:
            with self._pulse_md_lock:
                text = self._pulse_md.read_text(encoding="utf-8")
                lines = text.split("\n")
                new_lines = []
                in_status = False

                for line in lines:
                    if "## 📊 今日狀態" in line:
                        in_status = True
                        new_lines.append(line)
                        exp_count = self._db.get_today_exploration_count() if self._db else 0
                        exp_cost = self._db.get_today_exploration_cost() if self._db else 0
                        new_lines.append(f"- 探索次數: {exp_count}/{_cfg('exploration_daily_limit', EXPLORATION_DAILY_LIMIT)}")
                        new_lines.append(f"- 探索次數費用: ${exp_cost:.2f} (MAX 訂閱)")
                        new_lines.append(f"- 推送次數: {self._daily_push_count}/{_cfg('daily_push_limit', DAILY_PUSH_LIMIT)}")
                        if self._anima:
                            today_changes = []
                            if self._db:
                                from museon.pulse.anima_tracker import ELEMENTS
                                history = self._db.get_anima_history(limit=20)
                                today = datetime.now(TZ8).strftime("%Y-%m-%d")
                                for h in history:
                                    if h.get("timestamp", "").startswith(today):
                                        elem = h["element"]
                                        name = ELEMENTS.get(elem, {}).get("name", elem)
                                        today_changes.append(f"{name}+{h['delta']}")
                            if today_changes:
                                new_lines.append(f"- ANIMA 變化: {', '.join(today_changes)}")
                        continue
                    elif line.startswith("## ") and in_status:
                        in_status = False
                        new_lines.append("")
                        new_lines.append(line)
                        continue

                    if not in_status:
                        new_lines.append(line)

                self._atomic_write_pulse_md("\n".join(new_lines))
        except Exception as e:
            logger.error(f"Update PULSE.md status failed: {e}")

    async def _reflect(self, perception: str, exploration: Optional[Dict] = None) -> str:
        """反思 — 用 Haiku 做教練式自省 + 寫回 PULSE.md 形成演化閉環.

        P5 修復：分離「使用者感知」與「系統探索」，防止自我投射幻覺。
        - 感知層：只包含使用者的明確陳述與行為觀察
        - 探索層：系統自主探索結果（標記為 [系統探索]，不混入感知）
        """
        if not self._brain:
            return ""
        try:
            # ── 第一部分：使用者感知（未經系統推測） ──
            context_parts = [f"使用者感知:\n{perception}"]

            # ── 第二部分：系統探索（若有，必須明確標記，不混入感知） ──
            if exploration and exploration.get("findings"):
                findings = exploration.get("findings", "")[:300]
                topic = exploration.get("topic", "未知主題")
                # 明確標記為系統自主探索，區分於使用者想法
                context_parts.append(f"[系統探索] 今日主題：「{topic}」\n發現：{findings}")

            context = "\n\n".join(context_parts)

            response = await self._brain._call_llm_with_model(
                system_prompt=_SOUL_PULSE_SYSTEM,
                messages=[{"role": "user", "content": context}],
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
            )

            if "HEARTBEAT_OK" in response:
                return ""

            # ── 演化核心：反思結果寫回 PULSE.md ──
            if response and len(response.strip()) > 50:
                # P5：檢查反思是否包含自我投射，若有則不寫入
                if self._reflection_contains_projection(response):
                    logger.warning(f"反思包含自我投射幻覺，已過濾: {response[:50]}...")
                    return ""
                self._write_reflection_to_pulse(response.strip())

            return response
        except Exception as e:
            logger.error(f"Reflection failed: {e}")
            return ""

    def _write_reflection_to_pulse(self, reflection: str) -> None:
        """將反思寫入 PULSE.md 的反思區塊.

        這是演化閉環的寫入端：
        反思 → PULSE.md → _build_soul_context() → system prompt → 行為改變

        P4 修復：寫入前檢查是否包含已被糾正的過期事實，避免回聲效應。
        """
        if not self._pulse_md or not self._pulse_md.exists():
            return

        # P4: 過濾已糾正的過期事實
        if self._reflection_contains_stale_facts(reflection):
            logger.info("反思包含已糾正的過期事實，跳過寫入 PULSE.md")
            return

        try:
            with self._pulse_md_lock:
                text = self._pulse_md.read_text(encoding="utf-8")

                marker = "## 🌊 成長反思"
                start = text.find(marker)
                if start == -1:
                    now = datetime.now(TZ8).strftime("%m/%d %H:%M")
                    text += f"\n\n{marker}\n- [{now}] {reflection[:600]}\n"
                else:
                    next_section = text.find("\n## ", start + len(marker))
                    if next_section == -1:
                        next_section = len(text)

                    existing = text[start + len(marker):next_section].strip()
                    existing_lines = [l for l in existing.split("\n") if l.strip()]

                    now = datetime.now(TZ8).strftime("%m/%d %H:%M")
                    new_entry = f"- [{now}] {reflection[:600]}"
                    existing_lines.append(new_entry)
                    if len(existing_lines) > 5:
                        existing_lines = existing_lines[-5:]

                    new_section = f"{marker}\n" + "\n".join(existing_lines) + "\n"
                    text = text[:start] + new_section + text[next_section:]

                self._atomic_write_pulse_md(text)
            logger.info(f"反思寫入 PULSE.md（演化閉環）: {reflection[:60]}...")
        except Exception as e:
            logger.error(f"Write reflection to PULSE.md failed: {e}")

    def _reflection_contains_projection(self, reflection: str) -> bool:
        """P5 新增：檢查反思是否包含自我投射幻覺.

        偵測特徵：
        - 「我感受到你在...」「我感到你想...」（無根據的揣摩內心）
        - 「我看到你...」配合抽象主題（推測而非觀察）
        - 「似乎」「好像」「感覺」後面接著複雜假設

        目的：防止系統把自己的探索結果當成對使用者意圖的真實理解。
        """
        # 投射幻覺的標誌詞
        projection_markers = [
            "我感受到你在",          # 直接揣摩內心
            "我感到你想",            # 直接揣摩意圖
            "我感知到你",            # 偽裝為觀察的揣摩
            "我看出你",              # 聲稱能看穿內心
            "你應該是在",            # 推測式陳述
            "你可能在想",            # 明確的猜測
        ]

        reflection_lower = reflection.lower()

        # 計算投射特徵的出現次數
        projection_count = sum(1 for marker in projection_markers if marker in reflection_lower)

        # 若出現 2 次以上投射標誌，判定為包含幻覺
        return projection_count >= 2

    def _reflection_contains_stale_facts(self, reflection: str) -> bool:
        """檢查反思是否包含已被使用者糾正的過期事實（P4 自省清洗）.

        用簡單字串匹配（不額外呼叫 LLM），零成本實現。
        """
        try:
            corrections_path = Path(self._data_dir) / "anima" / "fact_corrections.jsonl"
            if not corrections_path.exists():
                return False

            text = corrections_path.read_text(encoding="utf-8").strip()
            if not text:
                return False

            # 讀取最近 10 條更正
            lines = text.split("\n")[-10:]
            keywords = []
            for line in lines:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    # 從 superseded_memories 提取被淘汰的關鍵事實
                    for mem in entry.get("superseded_memories", []):
                        old_content = mem.get("old_content", "")
                        # 提取關鍵詞片段（> 4 字的實質內容）
                        for segment in old_content.split("，"):
                            segment = segment.strip()
                            if len(segment) > 4:
                                keywords.append(segment[:30])
                except (json.JSONDecodeError, KeyError):
                    continue

            # 檢查反思是否包含任何過期事實的關鍵詞
            if not keywords:
                return False

            reflection_lower = reflection.lower()
            matches = sum(1 for kw in keywords if kw.lower() in reflection_lower)
            # 至少有 2 個關鍵詞匹配才判定為包含過期事實
            return matches >= 2

        except Exception as e:
            logger.debug(f"事實更正過濾檢查失敗: {e}")
            return False

    def _write_observation_to_pulse(self, observation: str) -> None:
        """將觀察寫入 PULSE.md 的觀察區塊."""
        if not self._pulse_md or not self._pulse_md.exists():
            return
        try:
            with self._pulse_md_lock:
                text = self._pulse_md.read_text(encoding="utf-8")

                marker = "## 🔭 今日觀察"
                start = text.find(marker)
                if start == -1:
                    now = datetime.now(TZ8).strftime("%m/%d %H:%M")
                    text += f"\n\n{marker}\n- [{now}] {observation[:150]}\n"
                else:
                    next_section = text.find("\n## ", start + len(marker))
                    if next_section == -1:
                        next_section = len(text)

                    existing = text[start + len(marker):next_section].strip()
                    existing_lines = [l for l in existing.split("\n") if l.strip()]

                    now = datetime.now(TZ8).strftime("%m/%d %H:%M")
                    new_entry = f"- [{now}] {observation[:150]}"
                    existing_lines.append(new_entry)
                    if len(existing_lines) > 5:
                        existing_lines = existing_lines[-5:]

                    new_section = f"{marker}\n" + "\n".join(existing_lines) + "\n"
                    text = text[:start] + new_section + text[next_section:]

                self._atomic_write_pulse_md(text)
        except Exception as e:
            logger.error(f"Write observation to PULSE.md failed: {e}")

    # ── PULSE.md 探索佇列管理 ──

    def _mark_pulse_topic_done(self, topic: str) -> None:
        """將 PULSE.md 中匹配的 [pending] 項目標記為 [done].

        匹配策略：關鍵詞重疊 > 50%，標記所有相關項目（不只第一個）。
        """
        if not self._pulse_md or not self._pulse_md.exists():
            return
        try:
            with self._pulse_md_lock:
                text = self._pulse_md.read_text(encoding="utf-8")
                lines = text.split("\n")
                changed = False
                topic_words = set(w for w in topic.replace("「", " ").replace("」", " ").split() if len(w) >= 2)
                for i, line in enumerate(lines):
                    if "[pending]" not in line:
                        continue
                    line_content = line.split("[pending]")[-1].strip()
                    line_words = set(w for w in line_content.replace("「", " ").replace("」", " ").split() if len(w) >= 2)
                    if topic_words and line_words:
                        overlap = len(topic_words & line_words) / max(min(len(topic_words), len(line_words)), 1)
                    else:
                        overlap = 0
                    if topic[:20] in line or overlap > 0.5:
                        lines[i] = line.replace("[pending]", "[done]")
                        changed = True
                        logger.info(f"PULSE.md 標記完成: {line_content[:50]}")
                if changed:
                    self._atomic_write_pulse_md("\n".join(lines))
        except Exception as e:
            logger.debug(f"_mark_pulse_topic_done failed: {e}")

    # ── 探索自我餵養 ──

    def _seed_followup_topics(self, exploration: Dict) -> None:
        """從探索結果萃取後續主題，寫入 PULSE.md 探索佇列.

        建立自我餵養迴圈：探索 → 發現 → 新問題 → 再探索
        """
        if not self._pulse_md or not self._pulse_md.exists():
            return

        findings = exploration.get("findings", "")
        topic = exploration.get("topic", "")

        if not findings or len(findings) < 100:
            return

        followups: List[str] = []

        # 1. 從 findings 提取問句
        for line in findings.split("\n"):
            line = line.strip()
            if (line.endswith("？") or line.endswith("?")) and 10 < len(line) < 150:
                clean = line.lstrip("-*> ").strip()
                if clean and clean not in followups:
                    followups.append(clean)

        # 2. 尋找「值得深入研究」類的語句
        import re
        deepen_patterns = [
            r"值得.*(?:研究|探索|了解|關注)",
            r"(?:未來|下一步).*(?:可以|應該|值得)",
            r"需要.*(?:進一步|更深入)",
        ]
        for line in findings.split("\n"):
            line = line.strip()
            for pat in deepen_patterns:
                if re.search(pat, line) and 10 < len(line) < 150:
                    clean = line.lstrip("-*> ").strip()
                    if clean and clean not in followups:
                        followups.append(clean)
                    break

        # 3. 如果都沒找到，生成一個通用後續主題
        if not followups and topic:
            followups.append(f"深入研究「{topic}」的實際應用案例與最新進展")

        # 最多寫入 2 個後續主題
        followups = followups[:2]

        if not followups:
            return

        try:
            with self._pulse_md_lock:
                text = self._pulse_md.read_text(encoding="utf-8")

                marker = None
                for candidate in [
                    "## 🧭 探索佇列（好奇心驅動，無邊界）",
                    "## 🧭 探索佇列",
                    "## 探索佇列",
                ]:
                    if candidate in text:
                        marker = candidate
                        break

                if marker is None:
                    marker = "## 🧭 探索佇列（好奇心驅動，無邊界）"
                    entries = "\n".join(f"- [pending] {t}" for t in followups)
                    text += f"\n\n{marker}\n{entries}\n"
                else:
                    start = text.find(marker)
                    next_section = text.find("\n## ", start + len(marker))
                    if next_section == -1:
                        next_section = len(text)

                    existing = text[start + len(marker):next_section].strip()
                    existing_lines = [
                        l for l in existing.split("\n")
                        if l.strip() and "等待" not in l
                    ]

                    for t in followups:
                        if self._is_recently_explored(t, days=3):
                            logger.debug(f"seed_followup 跳過（最近已探索）: {t[:40]}")
                            continue
                        entry = f"- [pending] {t}"
                        if entry not in existing_lines:
                            existing_lines.append(entry)

                    pending_lines = [l for l in existing_lines if "[pending]" in l]
                    other_lines = [l for l in existing_lines if "[pending]" not in l]
                    if len(pending_lines) > 5:
                        pending_lines = pending_lines[-5:]

                    new_section = f"{marker}\n" + "\n".join(other_lines + pending_lines) + "\n"
                    text = text[:start] + new_section + text[next_section:]

                self._atomic_write_pulse_md(text)
            logger.info(f"SoulPulse: seeded {len(followups)} follow-up topics to PULSE.md")
        except Exception as e:
            logger.warning(f"SoulPulse seed_followup_topics failed: {e}")

    # ── 靜默消化 ──

    async def _run_silent_digestion(self) -> None:
        """背景執行靜默消化（探索結束後非阻塞觸發）."""
        if not self._db or not self._data_dir:
            return
        try:
            from museon.pulse.silent_digestion import SilentDigestion
            # 嘗試取得 lattice（可選）
            lattice = None
            try:
                from museon.agent.knowledge_lattice import KnowledgeLattice
                lattice = KnowledgeLattice(data_dir=str(self._data_dir))
            except Exception as e:
                logger.debug(f"[PULSE_ENGINE] lattice failed (degraded): {e}")
            digester = SilentDigestion(
                db=self._db,
                data_dir=str(self._data_dir),
                lattice=lattice,
            )
            report = digester.digest(days=14)
            if report.get("status") == "done":
                summary = report.get("summary", "")
                logger.info(f"SilentDigestion: {summary}")
        except Exception as e:
            logger.debug(f"SilentDigestion background task failed: {e}")

    # ── 知識缺口偵測 ──

    def _detect_knowledge_gaps(self) -> List[Dict[str, Any]]:
        """KnowledgeGapDetector — 純 CPU 啟發式知識盲區掃描.

        偵測維度：
          1. ANIMA 低能量區域 → 對應能力未被鍛鍊
          2. 探索佇列長期未消化 → 好奇心停滯
          3. 長期未觸發的 Skill 類別 → 能力退化風險

        結果寫入 PULSE.md 的探索佇列，供 SoulPulse 排入探索。
        """
        gaps: List[Dict[str, Any]] = []

        # 維度 1：ANIMA 低能量區域
        if self._anima:
            radar = self._anima.get_relative()
            if radar:
                avg = sum(radar.values()) / max(len(radar), 1)
                for elem, val in radar.items():
                    if isinstance(val, (int, float)) and val < avg * 0.5 and val < 40:
                        gaps.append({
                            "type": "anima_low_energy",
                            "element": elem,
                            "value": val,
                            "suggestion": f"ANIMA '{elem}' 能量偏低({val})，建議探索相關領域",
                        })

        # 維度 2：探索佇列停滯
        if self._pulse_md and self._pulse_md.exists():
            try:
                text = self._pulse_md.read_text(encoding="utf-8")
                pending_count = text.count("[pending]")
                if pending_count >= 3:
                    gaps.append({
                        "type": "exploration_stagnation",
                        "pending_count": pending_count,
                        "suggestion": f"探索佇列有 {pending_count} 項待處理，好奇心可能停滯",
                    })
            except Exception as e:
                logger.debug(f"[PULSE_ENGINE] data read failed (degraded): {e}")

        # 維度 3：探索頻率過低
        if self._db:
            try:
                today_count = self._db.get_today_exploration_count()
                if today_count == 0 and self._is_active_hours():
                    now = datetime.now(TZ8)
                    if now.hour >= 14:  # 下午了還沒探索
                        gaps.append({
                            "type": "exploration_inactive",
                            "suggestion": "今日尚未進行探索，建議啟動一次好奇心驅動的探索",
                        })
            except Exception as e:
                logger.debug(f"[PULSE_ENGINE] operation failed (degraded): {e}")

        # 有新缺口 → 寫入 PULSE.md 探索佇列
        if gaps and self._pulse_md and self._pulse_md.exists():
            try:
                with self._pulse_md_lock:
                    text = self._pulse_md.read_text(encoding="utf-8")
                    marker = None
                    for candidate in ["## 🧭 探索佇列（好奇心驅動，無邊界）", "## 🧭 探索佇列", "## 探索佇列"]:
                        if candidate in text:
                            marker = candidate
                            break
                    if marker:
                        changed = False
                        for gap in gaps:
                            if gap["type"] == "anima_low_energy":
                                elem = gap["element"]
                                topic = f"[pending] - 探索「{elem}」相關知識（缺口偵測）"
                                if topic not in text \
                                        and f"[done] - 探索「{elem}」" not in text \
                                        and not self._is_recently_explored(f"探索「{elem}」相關知識", days=3):
                                    insert_pos = text.find(marker) + len(marker)
                                    text = text[:insert_pos] + f"\n{topic}" + text[insert_pos:]
                                    changed = True
                                else:
                                    logger.debug(f"KnowledgeGapDetector 跳過（已探索/已完成）: {elem}")
                        if changed:
                            self._atomic_write_pulse_md(text)
            except Exception as e:
                logger.debug(f"KnowledgeGapDetector write failed: {e}")

        if gaps:
            logger.info(f"KnowledgeGapDetector: 發現 {len(gaps)} 個知識缺口")

        return gaps

    # ── 關係日誌 ──

    def add_relationship_note(self, note: str) -> None:
        """新增一條關係日誌（公開 API）."""
        if not note or not note.strip():
            return
        self._write_relationship_entry(note.strip())

    def _write_relationship_entry(self, note: str) -> None:
        """將關係訊號寫入 PULSE.md 的關係日誌區塊.

        保留最近 5 條，避免無限膨脹。
        """
        if not self._pulse_md:
            return
        try:
            if not self._pulse_md.exists():
                self._ensure_pulse_md()
            if not self._pulse_md.exists():
                return

            with self._pulse_md_lock:
                text = self._pulse_md.read_text(encoding="utf-8")

                marker = "## 💝 關係日誌"
                start = text.find(marker)
                now = datetime.now(TZ8).strftime("%m/%d %H:%M")
                new_entry = f"- [{now}] {note[:200]}"

                if start == -1:
                    status_marker = "## 📊 今日狀態"
                    status_pos = text.find(status_marker)
                    if status_pos != -1:
                        insert = f"\n{marker}\n{new_entry}\n\n"
                        text = text[:status_pos] + insert + text[status_pos:]
                    else:
                        text += f"\n\n{marker}\n{new_entry}\n"
                else:
                    next_section = text.find("\n## ", start + len(marker))
                    if next_section == -1:
                        next_section = len(text)

                    existing = text[start + len(marker):next_section].strip()
                    existing_lines = [
                        l for l in existing.split("\n")
                        if l.strip() and l.strip() != "（尚無記錄）"
                    ]
                    existing_lines.append(new_entry)
                    if len(existing_lines) > 5:
                        existing_lines = existing_lines[-5:]

                    new_section = f"{marker}\n" + "\n".join(existing_lines) + "\n"
                    text = text[:start] + new_section + text[next_section:]

                self._atomic_write_pulse_md(text)
            logger.info(f"關係日誌寫入: {note[:60]}...")
        except Exception as e:
            logger.error(f"Write relationship journal failed: {e}")

    # ── API 介面 ──

    def get_status(self) -> Dict:
        """取得 PulseEngine 狀態（Dashboard 用）."""
        self._maybe_reset_daily()
        status = {
            "active_hours": self._is_active_hours(),
            "daily_push_count": self._daily_push_count,
            "daily_push_limit": _cfg("daily_push_limit", DAILY_PUSH_LIMIT),
        }
        if self._db:
            status["explorations_today"] = self._db.get_today_exploration_count()
            status["exploration_cost_today"] = self._db.get_today_exploration_cost()
            status["exploration_limit"] = _cfg("exploration_daily_limit", EXPLORATION_DAILY_LIMIT)
            status["exploration_budget"] = "max_subscription"
            status["schedules"] = len(self._db.list_schedules())
        if self._heartbeat_focus:
            status["focus_level"] = self._heartbeat_focus.focus_level
            status["interaction_count"] = self._heartbeat_focus.interaction_count
        if self._anima:
            status["anima"] = self._anima.get_radar_data()
        return status
