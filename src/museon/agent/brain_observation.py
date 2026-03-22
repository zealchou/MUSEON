"""BrainObservationMixin — 觀察與演化方法群.

從 brain.py 提取的 Mixin，負責使用者觀察、自我觀察、
事實修正、行為模式偵測、靈魂年輪、演化校準等邏輯。
"""

import json
import logging
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BrainObservationMixin:
    """觀察與演化方法群 — Mixin for MuseonBrain."""

    # ═══════════════════════════════════════════
    # 觀察引擎常數（從方法體內提升，便於調參與 A/B 測試）
    # ═══════════════════════════════════════════

    # 互動里程碑與校準週期
    _MILESTONE_INTERVAL = 50        # 每 N 次互動沉積里程碑年輪
    _RC_CALIBRATION_INTERVAL = 50   # 每 N 次互動校準 Safety Clusters
    _DRIFT_CHECK_INTERVAL = 10      # 每 N 次觀察做漂移偵測
    _L3_MATCH_INTERVAL = 20         # 每 N 次互動匹配 L3 反射
    _VOICE_EVOLVE_INTERVAL = 15     # 每 N 次互動微調表達風格

    # 信任等級閾值
    _TRUST_THRESHOLD_BUILDING = 5       # initial → building
    _TRUST_THRESHOLD_GROWING = 30       # building → growing
    _TRUST_THRESHOLD_ESTABLISHED = 100  # growing → established

    # 溝通風格判定閾值
    _DETAILED_MSG_LEN = 300     # 超過此長度 → detailed
    _CONCISE_MSG_LEN = 30       # 低於此長度 → concise

    # 八原語 EMA 權重（obs_weight=1.0 時的基準值，群組 ×0.5 縮放）
    _PRIMAL_ALPHA_SEMANTIC = 0.15   # PrimalDetector 語義偵測 EMA α
    _PRIMAL_ALPHA_KEYWORD = 0.08    # 關鍵字 fallback EMA α
    _PRIMAL_CONF_DELTA_SEMANTIC = 0.08  # 語義偵測信心度增量
    _PRIMAL_CONF_DELTA_KEYWORD = 0.05   # 關鍵字信心度增量
    _PRIMAL_KEYWORD_DELTA_BASE = 8      # 關鍵字命中基礎增量
    _PRIMAL_KEYWORD_DELTA_MAX = 25      # 關鍵字命中增量上限
    _PRIMAL_CURIOSITY_Q_BONUS = 3       # 問號加分倍率

    # L6 溝通風格 EMA 權重
    _MSG_LEN_EMA_OLD = 0.85     # 歷史權重
    _MSG_LEN_EMA_NEW = 0.15     # 新訊息權重

    # 群組觀察
    _GROUP_OBS_WEIGHT = 0.5         # 群組觀察權重（DM=1.0）
    _GROUP_FORMALITY_EMA = 0.9      # 正式度 EMA 歷史權重
    _GROUP_INITIATIVE_EMA = 0.9     # 主動度 EMA 歷史權重
    _GROUP_MAX_OBSERVATIONS = 50    # L8 觀察保留上限

    # 外部用戶觀察
    _EXT_L1_FACTS_MAX = 30         # 外部用戶 L1 事實上限
    _EXT_TOPICS_MAX = 20           # 外部用戶近期主題上限
    _EXT_DETAILED_LEN = 200        # 外部用戶 detailed 閾值

    # L1 事實
    _L1_FACTS_MAX = 50             # L1 事實上限

    # 根因偵測
    _ROOT_CAUSE_MIN_HISTORY = 6    # 最少歷史訊息數（3 輪）

    # ═══════════════════════════════════════════
    # Class-level attributes
    # ═══════════════════════════════════════════

    _EMOTION_MARKERS = {
        "positive": ["謝謝", "感謝", "開心", "高興", "太棒了", "厲害", "喜歡", "愛",
                      "好感動", "幸福", "讚", "棒", "😊", "❤️", "🙏", "感恩"],
        "negative": ["難過", "壓力", "焦慮", "擔心", "煩", "累", "沮喪", "生氣",
                      "不開心", "失望", "挫折", "無奈", "辛苦", "崩潰", "😢", "😔"],
        "sharing": ["跟你說", "你知道嗎", "分享", "今天", "最近", "我覺得",
                     "想聊聊", "告訴你"],
    }

    # 八原語關鍵字表（純 CPU 啟發式偵測）
    _PRIMAL_KEYWORDS: Dict[str, list] = {
        "aspiration":    ["目標", "想要", "計畫", "希望", "夢想", "願景", "要做", "打算", "規劃", "未來", "成為"],
        "accumulation":  ["之前", "經驗", "做過", "學過", "以前", "曾經", "背景", "專長", "歷程", "研究過"],
        "action_power":  ["做好了", "完成", "開始了", "已經", "試過", "執行", "部署", "上線", "搞定", "處理好"],
        "curiosity":     ["為什麼", "怎麼", "可以嗎", "教我", "好奇", "什麼是", "如何", "有沒有辦法", "可不可以"],
        "emotion_pattern": ["煩", "累", "興奮", "開心", "焦慮", "擔心", "壓力", "算了", "不爽", "超爽", "太棒", "受不了", "崩潰"],
        "blindspot":     ["沒想到", "沒注意", "忽略", "盲點", "沒考慮", "原來", "竟然", "居然", "真的嗎", "不知道原來", "我以為", "誤解", "搞錯", "一直以為"],
        "boundary":      ["不要", "不想", "不用", "別", "太多", "太長", "不行", "不需要", "停", "夠了"],
        "relationship_depth": ["謝謝", "你很棒", "辛苦", "晚安", "早安", "你好", "厲害", "太好了", "感謝", "愛你"],
    }

    # ── 偏好蒸餾器 — 任務類型關鍵字 ──
    _TASK_TYPE_KEYWORDS: Dict[str, list] = {
        "technical":  ["程式", "code", "bug", "API", "部署", "debug", "架構", "開發", "伺服器", "資料庫"],
        "business":   ["營收", "客戶", "市場", "定價", "銷售", "商業", "獲利", "成本", "KPI"],
        "emotional":  ["累", "壓力", "焦慮", "開心", "難過", "情緒", "感覺", "心情"],
        "creative":   ["設計", "寫", "創作", "想法", "靈感", "故事", "文案", "品牌"],
        "research":   ["研究", "分析", "比較", "搜尋", "調查", "趨勢", "資料"],
    }

    # 領域關鍵字表（與 lord_profile.json 的 domain_keywords 對齊）
    _LORD_DOMAIN_KEYWORDS: Dict[str, list] = {
        "business_strategy": ["策略", "商業", "市場", "定位", "獲利", "競爭", "商模", "佈局", "利基", "護城河"],
        "consultant_sales": ["銷售", "客戶", "成交", "提案", "顧問", "說服", "異議", "轉換", "簽約"],
        "brand_design": ["品牌", "設計", "視覺", "美感", "識別", "色彩", "排版", "Logo"],
        "ai_architecture": ["AI", "模組", "架構", "系統", "引擎", "Agent", "Skill", "pipeline"],
        "programming": ["程式", "Python", "code", "函數", "bug", "API", "debug", "deploy", "script"],
        "emotional_regulation": ["情緒", "壓力", "焦慮", "關係", "衝突", "煩", "累", "崩潰"],
    }

    # 六類訊號關鍵字
    _P0_SIGNAL_KEYWORDS: Dict[str, List[str]] = {
        "感性": [
            "煩", "累", "焦慮", "擔心", "壓力", "不爽", "崩潰", "受不了",
            "開心", "興奮", "超爽", "太棒", "感動", "難過", "傷心", "害怕",
            "算了", "不知道", "怪怪的", "心情", "情緒", "感覺",
        ],
        "思維轉化": [
            "卡住", "卡點", "矛盾", "掙扎", "兩難", "取捨", "抉擇",
            "想不通", "繞不出", "一直", "反覆", "糾結", "不確定",
            "該不該", "值不值", "到底要", "怎麼選", "猶豫",
        ],
        "哲學": [
            "意義", "為什麼活", "存在", "本質", "價值觀", "信念",
            "人生", "宿命", "自由意志", "道德", "倫理", "公平",
            "什麼是", "為什麼會", "哲學", "思辨",
        ],
        "戰略": [
            "佈局", "策略", "競爭", "市場", "對手", "壁壘", "護城河",
            "槓桿", "資源", "聯盟", "併購", "擴張", "收縮", "退場",
            "戰略", "博弈", "勝負", "時機", "情報",
        ],
    }

    # 事實更正關鍵字模式（純 CPU 啟發式偵測）
    _FACT_CORRECTION_PATTERNS: List[str] = [
        "不是", "你記錯", "你搞錯", "哪來的", "沒有這", "沒那回事",
        "只有", "才沒有", "要我講多少遍", "跟你說過", "我已經說過",
        "我說過了", "是兩個", "是2個", "不是12", "沒有12",
        "你怎麼又", "又來了", "又搞錯", "錯了啦", "不對啦",
        "我糾正", "我更正", "不是這樣", "才不是",
        "你誤會", "你弄錯", "你搞混", "修正一下",
    ]

    # 休息關鍵字 + 時間指示詞（需兩者同時命中）
    _REST_KEYWORDS = [
        "休息", "睡覺", "睡了", "去睡", "晚安", "good night", "goodnight",
        "先睡", "要睡了", "去休息", "不聊了", "明天再",
    ]
    _WAKE_TIME_PATTERN = None  # lazy init

    # 使用者年輪事件關鍵字
    _USER_RING_KEYWORDS: Dict[str, list] = {
        "breakthrough": ["突破", "搞定", "成功", "終於", "做到了", "解決了", "完成了"],
        "failure":      ["失敗", "搞砸", "做錯", "出問題", "壞了", "GG", "完蛋"],
        "milestone":    ["第一次", "里程碑", "上線", "完成", "發布", "launch", "上架"],
        "calibration":  ["不對", "調整", "修正", "重新想", "換方向", "轉念"],
    }

    # ── L1 事實提取關鍵字 ──
    _FACT_PATTERNS: Dict[str, list] = {
        "occupation": ["工作", "職業", "公司", "任職", "做的是", "上班", "老闆", "創業"],
        "family":     ["家人", "老婆", "太太", "兒子", "女兒", "小孩", "爸爸", "媽媽", "孩子"],
        "location":   ["住在", "在台北", "在台中", "在台灣", "搬到", "住的", "地址"],
        "education":  ["大學", "碩士", "博士", "畢業", "學校", "讀的", "主修"],
        "hobby":      ["喜歡", "興趣", "嗜好", "愛好", "運動", "旅行", "閱讀"],
    }

    # ── L2 人格特質關鍵字 ──
    _PERSONALITY_INDICATORS: Dict[str, Dict[str, list]] = {
        "openness":        {"high": ["好奇", "新東西", "嘗試", "探索", "創新", "想像"],
                            "low":  ["傳統", "穩定", "不變", "習慣"]},
        "conscientiousness": {"high": ["仔細", "規劃", "排程", "系統", "精確", "詳細"],
                              "low":  ["隨便", "算了", "之後再說", "管他"]},
        "extraversion":    {"high": ["聊天", "社交", "朋友", "聚會", "分享", "團隊"],
                            "low":  ["獨處", "安靜", "一個人", "內向"]},
        "agreeableness":   {"high": ["謝謝", "幫忙", "體貼", "關心", "配合", "合作"],
                            "low":  ["不行", "拒絕", "反對", "挑戰"]},
        "emotional_stability": {"high": ["冷靜", "理性", "穩定", "控制"],
                                "low":  ["焦慮", "擔心", "崩潰", "受不了", "壓力"]},
    }

    # ── L7 角色關鍵字 ──
    _ROLE_KEYWORDS: Dict[str, list] = {
        "entrepreneur": ["創業", "公司", "營收", "商業模式", "客戶", "市場", "融資"],
        "father":       ["孩子", "小孩", "兒子", "女兒", "爸爸", "家長"],
        "learner":      ["學習", "研究", "了解", "教我", "怎麼做", "入門"],
        "creator":      ["設計", "寫", "建造", "開發", "做一個", "創作"],
        "consultant":   ["客戶", "顧問", "輔導", "診斷", "幫他", "服務"],
        "manager":      ["團隊", "員工", "管理", "績效", "指派", "安排"],
    }

    # 時間模式關鍵字（_detect_cron_patterns 使用，目前為實驗功能）
    _CRON_KEYWORDS = [
        "每天", "每週", "每月", "每小時",
        "定期", "提醒我", "固定時間",
        "早上", "下午", "晚上",
        "每日", "weekly", "daily",
    ]

    # ═══════════════════════════════════════════
    # Methods
    # ═══════════════════════════════════════════

    def _detect_relationship_signals(
        self,
        messages: List[Dict[str, str]],
    ) -> None:
        """從被丟棄的訊息中偵測情感標記，發射 RELATIONSHIP_SIGNAL."""
        if not self._event_bus:
            return

        signals = []
        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if not content or len(content) < 5:
                continue

            for category, markers in self._EMOTION_MARKERS.items():
                matched = [m for m in markers if m in content]
                if matched:
                    snippet = content[:100].replace("\n", " ")
                    signals.append({
                        "category": category,
                        "markers": matched[:3],
                        "snippet": snippet,
                    })
                    break  # 每條訊息只取第一個匹配

        if signals:
            try:
                from museon.core.event_bus import RELATIONSHIP_SIGNAL
                # 合併同類信號
                summary_parts = []
                for s in signals[:3]:
                    cat_label = {
                        "positive": "正面",
                        "negative": "負面",
                        "sharing": "分享",
                    }.get(s["category"], s["category"])
                    summary_parts.append(
                        f"{cat_label}訊號: {s['snippet'][:60]}"
                    )
                note = "; ".join(summary_parts)
                self._event_bus.publish(RELATIONSHIP_SIGNAL, {"note": note})
            except Exception as e:
                logger.debug(f"Relationship signal emit failed: {e}")

    def _observe_user(
        self,
        content: str,
        anima_user: Optional[Dict[str, Any]],
        response_content: str = "",
        skill_names: Optional[List[str]] = None,
        context_type: str = "dm",
        suppress_primals: bool = False,
        suppress_facts: bool = False,
    ) -> None:
        """被動觀察使用者行為，更新 ANIMA_USER.

        整合六大觀察器：
        1. 基本互動計數 + 信任等級
        2. 八原語（啟發式關鍵字）— suppress_primals=True 時跳過
        3. 七層同心圓（L1-L7 全層）— suppress_facts=True 時跳過 L1
        4. 偏好蒸餾器
        5. 年輪觀察器
        6. 風格觀察器 + 模式觀察器

        Args:
            context_type: 觀察來源（"dm"=私訊全權重, "group"=群組半權重 ×0.5）
            suppress_primals: Memory Gate 判定為糾正/否認時，跳過八原語寫入
            suppress_facts: Memory Gate 判定為糾正/否認時，跳過 L1 事實寫入
        """
        if not anima_user:
            return

        # v2.0: 群組觀察權重
        obs_weight = self._GROUP_OBS_WEIGHT if context_type == "group" else 1.0

        now_iso = datetime.now().isoformat()
        relationship = anima_user.get("relationship", {})

        # ── 1. 基本互動計數 ──
        total = relationship.get("total_interactions", 0)
        new_total = total + 1
        relationship["total_interactions"] = new_total
        relationship["last_interaction"] = now_iso

        # 里程碑年輪：每 N 次互動沉積一枚里程碑（斷點三修復方案C）
        if new_total > 0 and new_total % self._MILESTONE_INTERVAL == 0 and self.ring_depositor:
            try:
                self.ring_depositor.deposit_soul_ring(
                    ring_type="service_milestone",
                    description=f"累積完成第 {new_total} 次互動",
                    context="持續陪伴里程碑",
                    impact=f"代表 {new_total} 次的信任與成長",
                    milestone_name=f"{new_total}_interactions",
                )
            except Exception as e:
                logger.warning(f"里程碑年輪寫入失敗: {e}")

        # 信任等級進化（四級：initial → building → growing → established）
        if total >= self._TRUST_THRESHOLD_ESTABLISHED and relationship.get("trust_level") == "growing":
            relationship["trust_level"] = "established"
        elif total >= self._TRUST_THRESHOLD_GROWING and relationship.get("trust_level") == "building":
            relationship["trust_level"] = "growing"
        elif total >= self._TRUST_THRESHOLD_BUILDING and relationship.get("trust_level") == "initial":
            relationship["trust_level"] = "building"

        anima_user["relationship"] = relationship

        # ── 2. 八原語觀察（向量語義偵測 + 關鍵字 fallback）──
        # ★ v1.13: Memory Gate 糾正/否認時跳過八原語寫入，避免「越否認越強化」
        primals = anima_user.get("eight_primals", {})
        if not suppress_primals:
            # ★ v10.5: 先用 PrimalDetector 偵測即時原語
            detected_primals = {}
            if self._primal_detector:
                try:
                    detected_primals = self._primal_detector.detect(content)
                except Exception as _e:
                    logger.debug(f"PrimalDetector.detect 降級（DM）: {_e}")
                    self._primal_fallback_count = getattr(self, '_primal_fallback_count', 0) + 1
            # 用偵測結果更新長期 ANIMA_USER 八原語（EMA 平滑）
            self._observe_user_primals(
                content, primals, now_iso, detected_primals,
                obs_weight=obs_weight,
            )
        else:
            logger.info("MemoryGate: suppress_primals=True, 跳過八原語觀察")
        anima_user["eight_primals"] = primals

        # ── 3. 七層觀察（L1-L7 全層）──
        layers = anima_user.get("seven_layers", {})
        self._observe_user_layers(
            content, layers, now_iso, anima_user=anima_user,
            suppress_facts=suppress_facts,  # ★ v1.13: 傳遞到 L1
        )
        anima_user["seven_layers"] = layers

        # ── 4. 偏好推斷（溝通風格 + 偏好蒸餾器）──
        prefs = anima_user.get("preferences", {})
        msg_len = len(content)
        if msg_len > self._DETAILED_MSG_LEN:
            prefs["communication_style"] = "detailed"
        elif msg_len < self._CONCISE_MSG_LEN:
            prefs["communication_style"] = "concise"
        hour = datetime.now().hour
        if 6 <= hour < 12:
            prefs["active_hours"] = "morning"
        elif 12 <= hour < 18:
            prefs["active_hours"] = "afternoon"
        elif 18 <= hour < 24:
            prefs["active_hours"] = "evening"
        else:
            prefs["active_hours"] = "night"
        anima_user["preferences"] = prefs

        # ── 5. 偏好蒸餾器（觀察引擎 1a）──
        self._observe_preferences(content, response_content, anima_user, now_iso)

        # ── 6. 年輪觀察器（觀察引擎 1b）──
        self._observe_ring_events(content, response_content, anima_user, now_iso)

        # ── 7. 模式觀察器（觀察引擎 1d）──
        self._observe_patterns(
            content, response_content, skill_names or [], anima_user, now_iso
        )

        # ── 8. RC 校準（每 50 次互動）──
        try:
            self._calibrate_rc(anima_user)
        except Exception as e:
            logger.warning(f"RC 校準失敗: {e}")

        # ── 9. 漂移偵測 v2.0（每 10 次觀察檢查一次）──
        # 不再暫停/恢復演化，改為：
        # - drift < 50%：寫入覺察日誌，不影響任何行為
        # - drift >= 50%：限制 morphenix 提案（L2/L3），核心學習繼續
        if self.drift_detector and self.drift_detector.should_check():
            try:
                anima_mc = self._load_anima_mc() or {}
                drift_report = self.drift_detector.check_drift(anima_mc, anima_user)
                evolution = anima_mc.setdefault("evolution", {})

                if drift_report.should_restrict_morphenix:
                    # 極端漂移 → 限制 morphenix 提案
                    evolution["morphenix_restricted"] = True
                    evolution["morphenix_restricted_reason"] = (
                        f"drift={drift_report.drift_score:.1%}"
                    )
                    evolution["morphenix_restricted_at"] = now_iso
                    # 清除舊的 paused 標記（向後相容）
                    evolution.pop("paused", None)
                    evolution.pop("paused_reason", None)
                    evolution.pop("paused_at", None)
                    self._save_anima_mc(anima_mc)
                    self._pending_notifications.append({
                        "source": "drift_detector",
                        "title": "漂移覺察",
                        "body": drift_report.awareness_log,
                        "emoji": "🔍",
                    })
                    logger.warning(
                        f"ANIMA 漂移極端: {drift_report.drift_score:.1%} → morphenix 受限"
                    )
                else:
                    # 漂移正常 → 解除 morphenix 限制
                    if evolution.get("morphenix_restricted"):
                        evolution["morphenix_restricted"] = False
                        evolution.pop("morphenix_restricted_reason", None)
                        evolution.pop("morphenix_restricted_at", None)
                        self._save_anima_mc(anima_mc)
                        logger.info(
                            f"ANIMA 漂移正常: {drift_report.drift_score:.1%}，morphenix 限制已解除"
                        )
                    # 同時清除舊的 paused 標記（向後相容遷移）
                    if evolution.get("paused"):
                        evolution["paused"] = False
                        evolution.pop("paused_reason", None)
                        evolution.pop("paused_at", None)
                        self._save_anima_mc(anima_mc)
            except Exception as e:
                logger.warning(f"漂移偵測失敗: {e}")

        # ── 10. L8 群組行為觀察（v2.0 新增）──
        if context_type == "group":
            self._observe_group_behavioral_shift(
                content, anima_user, obs_weight,
            )

        # ★ 寫入排隊：ANIMA_USER JSON 寫入通過 WriteQueue 序列化
        if self._wq:
            self._wq.enqueue("anima_user_save", self._save_anima_user, anima_user)
        else:
            self._save_anima_user(anima_user)

        # ── 11. 主人領域畫像觀察（軍師架構 Phase 0）──
        try:
            self._observe_lord(content, skill_names or [])
        except Exception as e:
            logger.debug(f"lord_profile 觀察降級: {e}")

    # ─── 根因偵測層（P2）─────────────────────────────

    async def _detect_root_cause_hint(
        self,
        content: str,
        session_id: str,
        matched_skills: list,
        routing_signal: "Any" = None,
        baihe_quadrant: str = "",
    ) -> str:
        """Step 3.66: 根因偵測 — 掃描近期對話模式，偵測問題背後的問題.

        只在 EXPLORATION_LOOP 或 SLOW_LOOP 啟動。
        使用 Haiku 低成本分析。受百合引擎 Q3 調節。
        """
        # 只在非 FAST_LOOP 啟動
        loop = (
            getattr(routing_signal, "loop", "FAST_LOOP")
            if routing_signal else "FAST_LOOP"
        )
        if loop == "FAST_LOOP":
            return ""

        # 取得近期 session 歷史
        history = self._get_session_history(session_id)
        if len(history) < self._ROOT_CAUSE_MIN_HISTORY:  # 至少 3 輪
            return ""

        # CPU 前篩：提取近期用戶訊息
        recent_user_msgs = [
            h["content"][:200] for h in history[-10:]
            if h.get("role") == "user"
        ][-5:]

        if len(recent_user_msgs) < 3:
            return ""

        # 追蹤 skill 使用模式（in-memory）
        if not hasattr(self, "_session_skill_log"):
            self._session_skill_log: dict = {}
        skill_log = self._session_skill_log.get(session_id, [])
        current_skills = [s.get("name", "") for s in matched_skills]
        skill_log.append(current_skills)
        if len(skill_log) > 10:
            skill_log = skill_log[-10:]
        self._session_skill_log[session_id] = skill_log

        # CPU 啟發式：檢查重複 skill 模式
        from collections import Counter
        all_skills = [s for turn in skill_log[-5:] for s in turn]
        skill_counts = Counter(all_skills)
        repeated = [s for s, c in skill_counts.items() if c >= 3]

        if not repeated:
            return ""

        # Haiku 根因假說生成
        try:
            prompt = (
                f"分析以下使用者的最近對話模式，找出「問題背後的問題」。\n\n"
                f"使用者最近 {len(recent_user_msgs)} 輪的訊息摘要：\n"
                + "\n".join(f"- {m}" for m in recent_user_msgs)
                + f"\n\n重複出現的需求主題：{', '.join(repeated)}"
                + "\n\n請用 1-2 句話推測：使用者表面在問什麼？"
                "背後真正的卡點可能是什麼？只輸出推測，不要客套話。"
            )
            hint = await self._call_llm_with_model(
                system_prompt="你是根因分析器。用 1-2 句話直指問題背後的問題。",
                messages=[{"role": "user", "content": prompt}],
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
            )
            if hint and len(hint.strip()) > 10:
                return (
                    "\n## 根因偵測（供參考，不一定要使用）\n"
                    f"{hint.strip()}\n"
                    "→ 如果適當，可以溫和追問使用者背後的真正需求，"
                    "但不要強迫或說教。"
                )
        except Exception as e:
            logger.debug(f"Step 3.66 根因偵測降級: {e}")
        return ""

    # ─── 百合引擎輔助方法 ─────────────────────────────

    def _format_baihe_guidance(self, decision) -> str:
        """將 BaiheDecision 格式化為 system prompt 注入文字."""
        quadrant_labels = {
            "Q1": "全力輔助 — 強項+主動，做配角",
            "Q2": "精準補位 — 弱項+主動，白話翻譯",
            "Q3": "主動進諫 — 弱項+未問，溫和提醒",
            "Q4": "靜默觀察 — 強項+未問，只記不說",
        }
        expression_labels = {
            "parallel_staff": "並肩參謀：跟隨主人節奏，不搶方向盤",
            "translator": "白話翻譯官：用比喻和生活語言解釋專業概念",
            "loyal_counsel": "忠臣進諫：先同理再建議，附退路",
            "silent_presence": "存在不干擾：極簡回應",
        }
        advise_tier_labels = {
            0: "靜默",
            1: "暗示（一句帶過）",
            2: "明示（結構化指出）",
            3: "直諫（附風險預警）",
        }

        q = decision.quadrant.value   # Q1/Q2/Q3/Q4
        lines = [
            "## 軍師定位（百合引擎）",
            f"- 象限：{q} {quadrant_labels.get(q, '')}",
            f"- 領域：{decision.topic_domain.value}",
            f"- 表達模式：{expression_labels.get(decision.expression_mode, decision.expression_mode)}",
        ]

        if decision.should_advise and decision.advise_tier > 0:
            lines.append(
                f"- 進諫等級：Tier {decision.advise_tier} "
                f"{advise_tier_labels.get(decision.advise_tier, '')}"
            )

        # 象限指引
        if q == "Q1":
            lines.append("- 必做：配合主人思路延伸，不搶結論")
            lines.append("- 禁止：主導方向、替主人做決定")
        elif q == "Q2":
            lines.append("- 必做：白話比喻優先，每個專詞都解釋")
            lines.append("- 禁止：丟術語不解釋、假設主人懂")
        elif q == "Q3":
            lines.append("- 必做：先同理再建議，附退路")
            lines.append("- 禁止：急著糾正、語氣居高臨下")
        elif q == "Q4":
            lines.append("- 必做：簡短確認即可")
            lines.append("- 禁止：主動展開分析")

        return "\n".join(lines)

    def _observe_lord(self, content: str, skill_names: List[str]) -> None:
        """被動觀察主人訊息，更新 lord_profile.json 的領域 evidence_count.

        設計原則：
        - 只做「觀察記錄」，不做任何決策（決策留給 Phase 1 百合引擎）
        - 原子寫入，失敗不影響核心流程
        - 與 ANIMA_USER 完全解耦（不讀不寫 ANIMA_USER）
        """
        lord_path = self.data_dir / "_system" / "lord_profile.json"
        if not lord_path.exists():
            return

        # ── 1. 關鍵字匹配：偵測訊息涉及哪些領域 ──
        matched_domains: List[str] = []
        content_lower = content.lower()
        for domain, keywords in self._LORD_DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in content_lower:
                    matched_domains.append(domain)
                    break  # 每個領域只算一次

        # Skill 名稱也可輔助判斷（例如 master-strategy → business_strategy）
        _skill_domain_map = {
            "master-strategy": "business_strategy",
            "ssa-consultant": "consultant_sales",
            "brand-identity": "brand_design",
            "aesthetic-sense": "brand_design",
            "market-core": "business_strategy",
            "resonance": "emotional_regulation",
            "dharma": "emotional_regulation",
        }
        for sn in skill_names:
            mapped = _skill_domain_map.get(sn)
            if mapped and mapped not in matched_domains:
                matched_domains.append(mapped)

        if not matched_domains:
            return  # 沒有可觀察的領域信號

        # ── 2. 原子更新 lord_profile.json ──
        try:
            raw = lord_path.read_text(encoding="utf-8")
            profile = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            logger.warning("lord_profile.json 讀取失敗，跳過觀察")
            return

        domains = profile.get("domains", {})
        updated = False
        for d in matched_domains:
            if d in domains:
                domains[d]["evidence_count"] = domains[d].get("evidence_count", 0) + 1
                updated = True

        if not updated:
            return

        # 原子寫入（先寫 .tmp 再 rename）
        tmp_path = lord_path.with_suffix(".json.tmp")
        try:
            tmp_path.write_text(
                json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            tmp_path.replace(lord_path)
            logger.debug(f"lord_profile 觀察更新: {matched_domains}")
        except OSError as e:
            logger.warning(f"lord_profile 原子寫入失敗: {e}")
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    # ─── Phase 0 訊號分流（v3.0）────────────────────────

    def _classify_p0_signal(
        self, content: str,
        routing_signal: Any = None,
        skill_names: Optional[List[str]] = None,
    ) -> str:
        """Phase 0 訊號分流 — 六類判定.

        Returns:
            "感性" | "理性" | "混合" | "思維轉化" | "哲學" | "戰略"
        """
        if not content:
            return "理性"

        content_lower = content.lower()
        scores: Dict[str, int] = {}

        for signal_type, keywords in self._P0_SIGNAL_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in content_lower)
            if hits > 0:
                scores[signal_type] = hits

        # Skill 輔助判定
        _skills = skill_names or []
        if "resonance" in _skills:
            scores["感性"] = scores.get("感性", 0) + 3
        if "dharma" in _skills:
            scores["思維轉化"] = scores.get("思維轉化", 0) + 3
        if "philo-dialectic" in _skills:
            scores["哲學"] = scores.get("哲學", 0) + 3
        if "master-strategy" in _skills or "shadow" in _skills:
            scores["戰略"] = scores.get("戰略", 0) + 3

        if not scores:
            return "理性"

        # 多維度命中 → 混合
        significant = {k: v for k, v in scores.items() if v >= 2}
        if len(significant) >= 2:
            return "混合"

        # 單一最高
        top_signal = max(scores, key=scores.get)
        return top_signal

    # ─── 事實更正偵測與處理（P0 記憶事實覆寫）────────────────

    def _detect_fact_correction(self, content: str) -> bool:
        """偵測使用者訊息是否包含事實糾正信號.

        純 CPU 啟發式：檢查是否匹配糾正模式關鍵字。
        設計為低成本、高召回率（寧可多偵測，由後續 LLM 精確判斷）。
        """
        if len(content) < 4:
            return False

        content_lower = content.lower()
        match_count = sum(
            1 for pattern in self._FACT_CORRECTION_PATTERNS
            if pattern in content_lower
        )
        # 命中 1 個以上關鍵字即觸發
        return match_count >= 1

    # ── P5: 用戶休息/免打擾意圖偵測 ──

    def _detect_and_publish_quiet_mode(self, content: str) -> None:
        """偵測用戶休息意圖並發布 USER_QUIET_MODE 事件.

        觸發條件：訊息包含休息關鍵字。
        效果：計算 suppress_until 時間戳並發布事件，ProactiveBridge 收到後
              在免打擾期間內不推送任何主動訊息。

        解析時間線索：
          「明天早上七點」→ 隔天 07:00
          「明天」→ 隔天 08:00（預設）
          無時間線索 → 6 小時後
        """
        if not content or len(content) < 2:
            return

        content_lower = content.lower()
        has_rest = any(kw in content_lower for kw in self._REST_KEYWORDS)
        if not has_rest:
            return

        import re
        import time as _time

        suppress_until = None

        # 嘗試解析「明天X點」「明天早上X點」
        time_match = re.search(
            r"明天.*?(?:早上|上午|下午|晚上)?.*?(\d{1,2})\s*(?:點|:00|時)",
            content,
        )
        if time_match:
            hour = int(time_match.group(1))
            # 粗略處理「下午」
            if "下午" in content and hour < 12:
                hour += 12
            tomorrow = datetime.now().replace(
                hour=hour, minute=0, second=0, microsecond=0
            )
            if tomorrow <= datetime.now():
                tomorrow += timedelta(days=1)
            suppress_until = tomorrow.timestamp()
        elif "明天" in content:
            tomorrow_8am = (datetime.now() + timedelta(days=1)).replace(
                hour=8, minute=0, second=0, microsecond=0
            )
            suppress_until = tomorrow_8am.timestamp()
        else:
            # 無時間線索 → 預設靜默 6 小時
            suppress_until = _time.time() + 6 * 3600

        if suppress_until and self._event_bus:
            try:
                from museon.core.event_bus import USER_QUIET_MODE
                self._event_bus.publish(USER_QUIET_MODE, {
                    "suppress_until": suppress_until,
                    "trigger_text": content[:100],
                })
                readable = datetime.fromtimestamp(suppress_until).strftime(
                    "%Y-%m-%d %H:%M"
                )
                logger.info(
                    f"[P5] 用戶休息意圖偵測命中，免打擾到 {readable}"
                )
            except Exception as e:
                logger.debug(f"[P5] 免打擾事件發布失敗: {e}")

    async def _handle_fact_correction(
        self,
        user_content: str,
        assistant_response: str,
        session_id: str,
    ) -> None:
        """使用者糾正事實時，找到矛盾的舊記憶並標記廢棄.

        流程：
        1. 用 MemoryManager.recall() 搜尋與糾正內容語義相關的記憶
        2. 呼叫 Haiku LLM 判斷哪些記憶與新事實矛盾
        3. 對矛盾記憶呼叫 MemoryManager.supersede() + VectorBridge.mark_deprecated()
        4. 記錄到 data/anima/fact_corrections.jsonl
        """
        if not self.memory_manager:
            return

        try:
            # 1. 搜尋相關記憶
            related_memories = self.memory_manager.recall(
                user_id=self.memory_manager._user_id,
                query=user_content,
                limit=10,
            )

            if not related_memories:
                return

            # 2. 用 Haiku 判斷哪些記憶與新事實矛盾
            memories_text = "\n".join(
                f"[{i}] ID={m.get('id','?')} | {m.get('content','')[:200]}"
                for i, m in enumerate(related_memories)
            )

            judge_prompt = (
                "你是事實一致性判斷器。使用者剛糾正了一個事實。\n"
                "請判斷以下哪些記憶與使用者的糾正內容矛盾。\n\n"
                f"使用者糾正內容：\n{user_content}\n\n"
                f"相關記憶：\n{memories_text}\n\n"
                "回覆格式：只回傳矛盾記憶的編號（如 0,2,5），"
                "如果沒有矛盾則回傳 NONE。"
                "不要解釋，只回傳編號或 NONE。"
            )

            result = await self._call_llm_with_model(
                system_prompt="你是精準的事實一致性判斷器。",
                messages=[{"role": "user", "content": judge_prompt}],
                model="claude-haiku-4-5-20251001",
                max_tokens=100,
            )

            if not result or "NONE" in result.upper():
                logger.debug("事實更正偵測：無矛盾記憶")
                return

            # 3. 解析矛盾記憶編號
            import re
            indices = [
                int(x) for x in re.findall(r"\d+", result)
                if int(x) < len(related_memories)
            ]

            if not indices:
                return

            # 4. 對矛盾記憶執行 supersede + mark_deprecated
            corrections = []
            for idx in indices:
                old_memory = related_memories[idx]
                old_id = old_memory.get("id", "")
                if not old_id:
                    continue

                try:
                    # 記憶層：supersede（歸檔舊記憶 + 建新記憶）
                    new_entry = self.memory_manager.supersede(
                        user_id=self.memory_manager._user_id,
                        old_id=old_id,
                        new_content=user_content,
                        tags=old_memory.get("tags", []) + ["fact_correction"],
                        source="fact_correction",
                    )

                    # 向量層：mark_deprecated（軟刪除舊向量）
                    try:
                        from museon.vector.vector_bridge import VectorBridge
                        vb = VectorBridge(workspace=self.data_dir)
                        vb.mark_deprecated("memories", old_id)
                    except Exception as ve:
                        logger.debug(f"向量廢棄標記失敗: {ve}")

                    corrections.append({
                        "old_id": old_id,
                        "old_content": old_memory.get("content", "")[:200],
                        "new_content": user_content[:200],
                        "new_id": new_entry.get("id", ""),
                    })

                    logger.info(
                        f"事實覆寫：{old_id} → {new_entry.get('id', '?')}"
                    )

                except Exception as se:
                    logger.warning(f"記憶 supersede 失敗 {old_id}: {se}")

            # 5. 寫入事實更正日誌
            if corrections:
                self._log_fact_correction(
                    user_content, assistant_response,
                    session_id, corrections,
                )

        except Exception as e:
            logger.warning(f"事實更正處理失敗: {e}")

    def _log_fact_correction(
        self,
        user_content: str,
        assistant_response: str,
        session_id: str,
        corrections: list,
    ) -> None:
        """將事實更正記錄追加到 fact_corrections.jsonl."""
        import json

        log_path = self.data_dir / "anima" / "fact_corrections.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "user_said": user_content[:500],
            "corrections": corrections,
        }

        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            logger.info(
                f"事實更正日誌寫入：{len(corrections)} 條記憶被覆寫"
            )
        except Exception as e:
            logger.warning(f"事實更正日誌寫入失敗: {e}")

    # ─── L8 群組行為觀察（v2.0 新增）────────────────────

    def _observe_group_behavioral_shift(
        self,
        content: str,
        anima_user: Dict[str, Any],
        obs_weight: float = 0.5,
    ) -> None:
        """觀察使用者在群組中的行為差異（L8 層）.

        追蹤四個維度：
        1. formality_shift: 語氣/正式度與 DM 基線的差異
        2. topic_distribution: 群組中討論的主題分佈
        3. initiative_ratio: 主動發言 vs 只回應的比例
        4. energy_delta: 群組互動後能量變化

        Args:
            content: 使用者訊息
            anima_user: ANIMA_USER dict（就地修改）
            obs_weight: 觀察權重
        """
        l8 = anima_user.setdefault("L8_context_behavior_notes", {
            "observations": [],
            "formality_baseline_dm": None,
            "group_stats": {},
        })

        now_iso = datetime.now().isoformat()

        # 1. 正式度偵測（簡易啟發式：長度、標點、敬語）
        formality_score = 0.5  # 中性基準
        politeness_markers = ["請", "您", "謝謝", "麻煩", "不好意思", "抱歉"]
        casual_markers = ["哈哈", "XD", "lol", "haha", "欸", "唉", "ㄏ", "讚"]
        for m in politeness_markers:
            if m in content:
                formality_score += 0.08
        for m in casual_markers:
            if m in content:
                formality_score -= 0.08
        if len(content) > 200:
            formality_score += 0.05
        formality_score = max(0.0, min(1.0, formality_score))

        # 2. 主動度偵測（是否以問號結尾、是否 @mention 他人、訊息長度）
        initiative_score = 0.5
        if content.strip().endswith("？") or content.strip().endswith("?"):
            initiative_score += 0.15  # 提問 = 主動
        if "@" in content:
            initiative_score += 0.10  # @mention = 主動引導
        if len(content) > 100:
            initiative_score += 0.10  # 長訊息 = 主動分享
        elif len(content) < 20:
            initiative_score -= 0.15  # 短回覆 = 被動
        initiative_score = max(0.0, min(1.0, initiative_score))

        # 3. 主題偵測（簡易關鍵字分類）
        topic = "general"
        topic_keywords = {
            "tech": ["程式", "系統", "API", "bug", "功能", "開發", "架構"],
            "business": ["客戶", "營收", "行銷", "產品", "定價", "成交"],
            "personal": ["今天", "最近", "感覺", "覺得", "想要", "希望"],
            "creative": ["設計", "風格", "美", "創意", "靈感", "故事"],
        }
        for t_name, t_keywords in topic_keywords.items():
            if any(kw in content for kw in t_keywords):
                topic = t_name
                break

        # 4. 組裝觀察記錄
        group_id = getattr(self, "_current_group_id", None) or "unknown"
        observation = {
            "observed_at": now_iso,
            "group_id": str(group_id),
            "formality_shift": round(formality_score, 2),
            "initiative_ratio": round(initiative_score, 2),
            "topic": topic,
            "content_length": len(content),
            "confidence": round(0.6 * obs_weight, 2),
        }

        # 追加到觀察列表（保留最近 50 條）
        observations = l8.setdefault("observations", [])
        observations.append(observation)
        if len(observations) > self._GROUP_MAX_OBSERVATIONS:
            l8["observations"] = observations[-self._GROUP_MAX_OBSERVATIONS:]

        # 更新群組統計
        stats = l8.setdefault("group_stats", {})
        g_stats = stats.setdefault(str(group_id), {
            "interaction_count": 0,
            "avg_formality": 0.5,
            "avg_initiative": 0.5,
            "topic_distribution": {},
            "last_interaction": None,
        })
        g_count = g_stats.get("interaction_count", 0)
        new_count = g_count + 1
        g_stats["interaction_count"] = new_count

        # EMA 更新平均值
        old_f = g_stats.get("avg_formality", self._GROUP_OBS_WEIGHT)
        g_stats["avg_formality"] = round(
            old_f * self._GROUP_FORMALITY_EMA + formality_score * (1 - self._GROUP_FORMALITY_EMA), 3
        )
        old_i = g_stats.get("avg_initiative", 0.5)
        g_stats["avg_initiative"] = round(
            old_i * self._GROUP_INITIATIVE_EMA + initiative_score * (1 - self._GROUP_INITIATIVE_EMA), 3
        )

        # 主題分佈計數
        t_dist = g_stats.setdefault("topic_distribution", {})
        t_dist[topic] = t_dist.get(topic, 0) + 1
        g_stats["last_interaction"] = now_iso

        anima_user["L8_context_behavior_notes"] = l8

    # ─── 群組外部用戶觀察管線 ────────────────────

    def _observe_external_user(
        self,
        content: str,
        user_id: str,
        sender_name: str = "",
        response_content: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """群組外部用戶觀察 — 寫入 external_users/{user_id}.json，不碰 ANIMA_USER。

        v3.0 升級：完整觀察（八原語 + L1 事實 + L6 溝通風格 + 信任演化 + 偏好 + 主題）。
        Owner 在群組中的發言不觀察（群組上下文已被前綴污染）。
        """
        if not user_id:
            return
        # Owner 在群組中的發言跳過外部用戶觀察
        if metadata and metadata.get("is_owner"):
            return

        try:
            from museon.governance.multi_tenant import ExternalAnimaManager
            ext_mgr = ExternalAnimaManager(self.data_dir)
            ext_anima = ext_mgr.load(user_id)

            now_iso = datetime.now().isoformat()

            # 更新 display_name + profile
            if sender_name and not ext_anima.get("display_name"):
                ext_anima["display_name"] = sender_name
            profile = ext_anima.setdefault("profile", {})
            if sender_name and not profile.get("name"):
                profile["name"] = sender_name

            # 1. 互動計數 + 信任等級演化
            ext_anima["last_seen"] = now_iso
            rel = ext_anima.setdefault("relationship", {
                "trust_level": "initial",
                "total_interactions": 0,
                "positive_signals": 0,
                "negative_signals": 0,
                "last_interaction": None,
                "first_interaction": now_iso,
            })
            rel["total_interactions"] = rel.get("total_interactions", 0) + 1
            rel["last_interaction"] = now_iso
            # 信任等級演化（與 _observe_user 同邏輯）
            total = rel["total_interactions"]
            trust = rel.get("trust_level", "initial")
            trust_levels = ["initial", "building", "growing", "established"]
            idx = trust_levels.index(trust) if trust in trust_levels else 0
            if total >= 100 and idx < 3:
                rel["trust_level"] = "established"
            elif total >= 30 and idx < 2:
                rel["trust_level"] = "growing"
            elif total >= 5 and idx < 1:
                rel["trust_level"] = "building"

            # 2. 完整八原語觀察（v3.0: 含 PrimalDetector 語義偵測）
            primals = ext_anima.setdefault("eight_primals", {})
            # 嘗試使用 PrimalDetector（語義偵測，比純關鍵字更精準）
            detected_primals = None
            if hasattr(self, '_primal_detector') and self._primal_detector:
                try:
                    detected_primals = self._primal_detector.detect(content)
                except Exception as e:
                    logger.debug(f"PrimalDetector.detect 降級（外部用戶）: {e}")
                    self._primal_fallback_count = getattr(self, '_primal_fallback_count', 0) + 1
            self._observe_user_primals(
                content, primals, now_iso,
                detected_primals=detected_primals,
                obs_weight=0.5,  # 群組觀察降權
            )
            ext_anima["eight_primals"] = primals

            # 3. L6 溝通風格觀察
            seven = ext_anima.setdefault("seven_layers", {})
            l6 = seven.setdefault("L6_communication_style", {
                "detail_level": "moderate",
                "emoji_usage": "none",
                "language_mix": "mixed",
                "avg_msg_length": 0,
                "question_style": "open",
                "tone": "casual",
            })
            # Rolling average 訊息長度
            msg_len = len(content)
            old_avg = l6.get("avg_msg_length", 0) or 0
            l6["avg_msg_length"] = int(old_avg * self._MSG_LEN_EMA_OLD + msg_len * self._MSG_LEN_EMA_NEW)
            # Detail level
            if msg_len > self._EXT_DETAILED_LEN:
                l6["detail_level"] = "detailed"
            elif msg_len < self._CONCISE_MSG_LEN:
                l6["detail_level"] = "concise"
            else:
                l6["detail_level"] = "moderate"
            # Question style
            q_count = content.count("？") + content.count("?")
            if q_count >= 2:
                l6["question_style"] = "open"
            elif q_count == 1:
                l6["question_style"] = "closed"
            else:
                l6["question_style"] = "directive"

            # 4. L1 事實提取（輕量版 — 關鍵字觸發）
            l1_facts = seven.setdefault("L1_facts", [])
            _fact_keywords = {
                "occupation": ["工作", "職業", "公司", "任職", "做的是", "上班", "老闆", "創業"],
                "family": ["家人", "老婆", "太太", "兒子", "女兒", "小孩"],
                "location": ["住在", "在台北", "在台中", "在台灣", "搬到"],
                "hobby": ["喜歡", "興趣", "嗜好", "運動", "旅行"],
            }
            for category, kws in _fact_keywords.items():
                if any(kw in content for kw in kws):
                    fact_entry = {
                        "category": category,
                        "snippet": content[:100],
                        "date": now_iso,
                    }
                    l1_facts.append(fact_entry)
                    if len(l1_facts) > self._EXT_L1_FACTS_MAX:
                        seven["L1_facts"] = l1_facts[-self._EXT_L1_FACTS_MAX:]
                    break  # 一次只記一個事實類別

            # 5. 偏好追蹤（向下相容）
            prefs = ext_anima.setdefault("preferences", {})
            if msg_len > self._DETAILED_MSG_LEN:
                prefs["communication_style"] = "detailed"
            elif msg_len < self._CONCISE_MSG_LEN:
                prefs["communication_style"] = "concise"
            ext_anima["preferences"] = prefs

            # 6. 近期主題記錄（保留最近 20 筆）
            topics = ext_anima.setdefault("recent_topics", [])
            # 清理群組前綴，只留使用者原始訊息的前 120 字元
            clean_content = content
            for prefix in ("[群組近期對話紀錄]", "[群組會議]", "[群組]"):
                if prefix in clean_content:
                    # 取前綴之後的最後一段（使用者的實際訊息）
                    parts = clean_content.split("\n")
                    clean_content = parts[-1] if parts else clean_content
                    break
            topics.append({
                "snippet": clean_content[:120].replace("\n", " ").strip(),
                "date": now_iso,
            })
            if len(topics) > self._EXT_TOPICS_MAX:
                ext_anima["recent_topics"] = topics[-self._EXT_TOPICS_MAX:]

            ext_mgr.save(user_id, ext_anima)
            logger.debug(f"外部用戶觀察完成（v3.0）: {user_id} ({sender_name})")

        except Exception as e:
            logger.warning(f"外部用戶觀察失敗 {user_id}: {e}")

    # ─── 觀察引擎 1a: 偏好蒸餾器 ────────────────────

    def _observe_preferences(
        self,
        content: str,
        response: str,
        anima_user: Dict[str, Any],
        now_iso: str,
    ) -> None:
        """追蹤使用者偏好模式，累積達閾值後寫入 L5."""
        layers = anima_user.setdefault("seven_layers", {})
        prefs = layers.setdefault("L5_preference_crystals", [])

        # 偏好觀察緩衝（存在 anima_user 中的隱藏欄位）
        pref_buffer = anima_user.setdefault("_pref_buffer", {})

        # 偵測回答長度偏好
        if response:
            resp_len = len(response)
            len_key = "prefers_long_response" if resp_len > 500 else "prefers_short_response"
            buf = pref_buffer.setdefault(len_key, {"count": 0, "first": now_iso})
            buf["count"] += 1
            buf["last"] = now_iso

        # 偵測時段偏好
        hour = datetime.now().hour
        if 0 <= hour < 6:
            time_key = "active_late_night"
        elif 22 <= hour < 24:
            time_key = "active_late_evening"
        elif 6 <= hour < 9:
            time_key = "active_early_morning"
        else:
            time_key = None

        if time_key:
            buf = pref_buffer.setdefault(time_key, {"count": 0, "first": now_iso})
            buf["count"] += 1
            buf["last"] = now_iso

        # 偵測主題偏好
        for topic, keywords in self._TASK_TYPE_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in content)
            if hits >= 2:
                topic_key = f"interested_in_{topic}"
                buf = pref_buffer.setdefault(topic_key, {"count": 0, "first": now_iso})
                buf["count"] += 1
                buf["last"] = now_iso

        # 閾值檢查：累積 ≥5 次 → 結晶化或更新 L5 偏好
        existing_map = {p.get("key"): i for i, p in enumerate(prefs)}
        for key, buf_data in list(pref_buffer.items()):
            count = buf_data.get("count", 0)
            if count < 5:
                continue
            new_confidence = min(1.0, count * 0.1)
            if key in existing_map:
                # 更新已存在的結晶（修復：不再跳過已存在的偏好）
                idx = existing_map[key]
                prefs[idx]["confidence"] = new_confidence
                prefs[idx]["observed_count"] = count
                prefs[idx]["last_seen"] = buf_data.get("last", now_iso)
            else:
                prefs.append({
                    "key": key,
                    "value": key.replace("_", " "),
                    "confidence": new_confidence,
                    "observed_count": count,
                    "first_seen": buf_data.get("first", now_iso),
                    "last_seen": buf_data.get("last", now_iso),
                })
                existing_map[key] = len(prefs) - 1

        # 矛盾偏好解消：同維度取較強者
        _opposite_pairs = [
            ("prefers_short_response", "prefers_long_response"),
        ]
        for key_a, key_b in _opposite_pairs:
            if key_a in existing_map and key_b in existing_map:
                idx_a = existing_map[key_a]
                idx_b = existing_map[key_b]
                conf_a = prefs[idx_a].get("confidence", 0)
                conf_b = prefs[idx_b].get("confidence", 0)
                # 保留較強者，弱者降低 confidence
                if conf_a > conf_b:
                    prefs[idx_b]["confidence"] = max(0.1, conf_b * 0.5)
                elif conf_b > conf_a:
                    prefs[idx_a]["confidence"] = max(0.1, conf_a * 0.5)

        # 上限 30 筆偏好
        if len(prefs) > 30:
            layers["L5_preference_crystals"] = sorted(
                prefs, key=lambda p: p.get("confidence", 0), reverse=True
            )[:30]

    # ─── 觀察引擎 1b: 年輪觀察器 ────────────────────

    def _observe_ring_events(
        self,
        content: str,
        response: str,
        anima_user: Dict[str, Any],
        now_iso: str,
    ) -> None:
        """偵測使用者端的重要事件，寫入 L4 年輪."""
        layers = anima_user.setdefault("seven_layers", {})
        rings = layers.setdefault("L4_interaction_rings", [])

        # 每日上限 3 筆
        today = now_iso[:10]
        today_count = sum(1 for r in rings if r.get("date", "")[:10] == today)
        if today_count >= 3:
            return

        for ring_type, keywords in self._USER_RING_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in content)
            if hits >= 2:
                # 去重：同類型 + 同天不重複
                already = any(
                    r.get("type") == ring_type and r.get("date", "")[:10] == today
                    for r in rings
                )
                if not already:
                    rings.append({
                        "type": ring_type,
                        "summary": content[:60].replace("\n", " "),
                        "date": now_iso,
                        "context": content[:120].replace("\n", " "),
                    })
                break  # 每次互動最多一筆年輪

    # ─── 觀察引擎 1d: 模式觀察器 ────────────────────

    def _observe_patterns(
        self,
        content: str,
        response: str,
        skill_names: List[str],
        anima_user: Dict[str, Any],
        now_iso: str,
    ) -> None:
        """追蹤使用者行為模式，寫入 L3."""
        layers = anima_user.setdefault("seven_layers", {})
        patterns = layers.setdefault("L3_decision_pattern", [])
        pattern_map = {p.get("description", ""): p for p in patterns}

        # 1. Skill 叢集觀察
        if skill_names and len(skill_names) >= 2:
            cluster_key = "+".join(sorted(skill_names[:3]))
            desc = f"skill_cluster:{cluster_key}"
            if desc in pattern_map:
                pattern_map[desc]["frequency"] = pattern_map[desc].get("frequency", 0) + 1
                pattern_map[desc]["last_seen"] = now_iso
                pattern_map[desc]["confidence"] = min(
                    1.0, pattern_map[desc].get("confidence", 0.3) + 0.05
                )
            else:
                patterns.append({
                    "pattern_type": "skill_cluster",
                    "description": desc,
                    "frequency": 1,
                    "last_seen": now_iso,
                    "confidence": 0.3,
                })

        # 2. 對話時段分佈
        hour = datetime.now().hour
        if 0 <= hour < 6:
            period = "deep_night"
        elif 6 <= hour < 9:
            period = "early_morning"
        elif 9 <= hour < 12:
            period = "morning"
        elif 12 <= hour < 14:
            period = "noon"
        elif 14 <= hour < 18:
            period = "afternoon"
        elif 18 <= hour < 22:
            period = "evening"
        else:
            period = "late_night"

        period_desc = f"time_pattern:{period}"
        if period_desc in pattern_map:
            pattern_map[period_desc]["frequency"] = \
                pattern_map[period_desc].get("frequency", 0) + 1
            pattern_map[period_desc]["last_seen"] = now_iso
        else:
            patterns.append({
                "pattern_type": "time_distribution",
                "description": period_desc,
                "frequency": 1,
                "last_seen": now_iso,
                "confidence": 0.2,
            })

        # 3. 任務類型分佈
        for task_type, keywords in self._TASK_TYPE_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in content)
            if hits >= 2:
                task_desc = f"task_type:{task_type}"
                if task_desc in pattern_map:
                    pattern_map[task_desc]["frequency"] = \
                        pattern_map[task_desc].get("frequency", 0) + 1
                    pattern_map[task_desc]["last_seen"] = now_iso
                    pattern_map[task_desc]["confidence"] = min(
                        1.0, pattern_map[task_desc].get("confidence", 0.3) + 0.03
                    )
                else:
                    patterns.append({
                        "pattern_type": "task_distribution",
                        "description": task_desc,
                        "frequency": 1,
                        "last_seen": now_iso,
                        "confidence": 0.3,
                    })
                break  # 每次只記一個主要任務類型

        # 限制上限 50 筆
        if len(patterns) > 50:
            patterns.sort(key=lambda p: p.get("frequency", 0), reverse=True)
            layers["L3_decision_pattern"] = patterns[:50]

    def _observe_user_primals(
        self, content: str, primals: Dict[str, Any], now_iso: str,
        detected_primals: Optional[Dict[str, int]] = None,
        obs_weight: float = 1.0,
    ) -> None:
        """觀察使用者的八原語維度（向量語義 + 關鍵字 fallback）.

        Args:
            content: 使用者訊息
            primals: ANIMA_USER 中的 eight_primals dict（就地修改）
            now_iso: ISO 時間戳
            detected_primals: PrimalDetector 即時偵測結果 {key: level(0-100)}
            obs_weight: 觀察權重（1.0=DM 全權重, 0.5=群組半權重）
        """
        # 初始化缺少的維度
        for key in ["aspiration", "accumulation", "action_power", "curiosity",
                     "emotion_pattern", "blindspot", "boundary", "relationship_depth"]:
            if key not in primals:
                primals[key] = {"level": 0, "confidence": 0.0, "signal": "", "last_observed": None}

        # ★ v10.5: 優先使用 PrimalDetector 語義偵測結果
        # v2.0: 群組觀察 alpha 依 obs_weight 縮放
        alpha_semantic = self._PRIMAL_ALPHA_SEMANTIC * obs_weight
        alpha_keyword = self._PRIMAL_ALPHA_KEYWORD * obs_weight
        conf_delta_semantic = self._PRIMAL_CONF_DELTA_SEMANTIC * obs_weight
        conf_delta_keyword = self._PRIMAL_CONF_DELTA_KEYWORD * obs_weight

        if detected_primals:
            for primal_key, det_level in detected_primals.items():
                if primal_key not in primals:
                    continue
                p = primals[primal_key]
                old_level = p.get("level", 0)
                # EMA 平滑更新長期 level（語義偵測更精確）
                if old_level < 10:
                    p["level"] = min(100, max(old_level, int(det_level * obs_weight)))
                else:
                    p["level"] = min(100, int(old_level * (1 - alpha_semantic) + det_level * alpha_semantic))
                old_conf = p.get("confidence", 0.0)
                p["confidence"] = min(1.0, round(old_conf + conf_delta_semantic, 2))
                p["signal"] = content[:80].replace("\n", " ")
                p["last_observed"] = now_iso
        else:
            # Fallback: 關鍵字匹配
            for primal_key, keywords in self._PRIMAL_KEYWORDS.items():
                hits = sum(1 for kw in keywords if kw in content)
                if hits > 0:
                    p = primals[primal_key]
                    old_level = p.get("level", 0)
                    delta = int(min(hits * self._PRIMAL_KEYWORD_DELTA_BASE, self._PRIMAL_KEYWORD_DELTA_MAX) * obs_weight)
                    if old_level < 10:
                        p["level"] = min(100, old_level + delta)
                    else:
                        p["level"] = min(100, int(old_level * (1 - alpha_keyword) + (old_level + delta) * alpha_keyword))
                    old_conf = p.get("confidence", 0.0)
                    p["confidence"] = min(1.0, round(old_conf + conf_delta_keyword, 2))
                    p["signal"] = content[:80].replace("\n", " ")
                    p["last_observed"] = now_iso

        # 問號計數 → 好奇心額外加分
        q_marks = content.count("？") + content.count("?")
        if q_marks >= 2:
            cur = primals.get("curiosity", {})
            old_lv = cur.get("level", 0)
            cur["level"] = min(100, old_lv + q_marks * self._PRIMAL_CURIOSITY_Q_BONUS)
            cur["last_observed"] = now_iso
            primals["curiosity"] = cur

    def _observe_user_layers(
        self, content: str, layers: Dict[str, Any], now_iso: str,
        anima_user: Optional[Dict[str, Any]] = None,
        suppress_facts: bool = False,
    ) -> None:
        """觀察使用者七層同心圓數據（純 CPU）.

        Args:
            suppress_facts: Memory Gate 判定為糾正/否認時，跳過 L1 事實寫入
        """
        # ── L1: 基本事實 ──
        # ★ v1.13: Memory Gate 糾正/否認時跳過 L1 事實寫入
        if not suppress_facts:
            facts = layers.setdefault("L1_facts", [])
            existing_facts = {f.get("fact", "") for f in facts}
            for category, keywords in self._FACT_PATTERNS.items():
                hits = [kw for kw in keywords if kw in content]
                if len(hits) >= 1:
                    # 擷取包含關鍵字的句子作為事實
                    for kw in hits:
                        idx = content.find(kw)
                        if idx >= 0:
                            # 擷取關鍵字前後 40 字
                            start = max(0, idx - 20)
                            end = min(len(content), idx + len(kw) + 40)
                            snippet = content[start:end].replace("\n", " ").strip()
                            if snippet and snippet not in existing_facts:
                                facts.append({
                                    "fact": snippet,
                                    "category": category,
                                    "source": "conversation",
                                    "date": now_iso,
                                    "status": "active",       # ★ v1.13: 事實狀態追蹤
                                    "confidence": 0.7,         # ★ v1.13: 初始信心度
                                })
                                existing_facts.add(snippet)
                                break  # 每個 category 每次最多新增一筆
            # 限制 L1 上限 50 筆，超過移除最舊的
            if len(facts) > self._L1_FACTS_MAX:
                layers["L1_facts"] = facts[-self._L1_FACTS_MAX:]
        else:
            logger.info("MemoryGate: suppress_facts=True, 跳過 L1 事實寫入")

        # ── L2: 人格特質 ──
        traits = layers.setdefault("L2_personality", [])
        trait_map = {t["trait"]: t for t in traits}
        for trait_name, indicators in self._PERSONALITY_INDICATORS.items():
            high_hits = sum(1 for kw in indicators["high"] if kw in content)
            low_hits = sum(1 for kw in indicators["low"] if kw in content)
            if high_hits > 0 or low_hits > 0:
                tendency = "high" if high_hits >= low_hits else "low"
                evidence = content[:60].replace("\n", " ")
                if trait_name in trait_map:
                    existing = trait_map[trait_name]
                    old_conf = existing.get("confidence", 0.3)
                    if existing.get("tendency") == tendency:
                        existing["confidence"] = min(1.0, round(old_conf + 0.03, 2))
                    else:
                        existing["confidence"] = max(0.1, round(old_conf - 0.05, 2))
                        if existing["confidence"] < 0.2:
                            existing["tendency"] = tendency
                    existing["evidence"] = evidence
                    existing["last_updated"] = now_iso
                else:
                    traits.append({
                        "trait": trait_name,
                        "tendency": tendency,
                        "evidence": evidence,
                        "confidence": 0.3,
                        "last_updated": now_iso,
                    })
                    trait_map[trait_name] = traits[-1]
        layers["L2_personality"] = traits

        # ── L3: 決策模式（由 _observe_patterns 填充，此處做 aging）──
        patterns = layers.setdefault("L3_decision_pattern", [])
        # 僅保留最近 30 筆
        if len(patterns) > 30:
            layers["L3_decision_pattern"] = patterns[-30:]

        # ── L4: 互動年輪（由 _observe_ring_events 填充，此處做 dedup）──
        rings = layers.setdefault("L4_interaction_rings", [])
        # 保留最近 100 筆
        if len(rings) > 100:
            layers["L4_interaction_rings"] = rings[-100:]

        # ── L5: 偏好結晶（由 _observe_preferences 填充，此處做 confidence decay）──
        prefs = layers.setdefault("L5_preference_crystals", [])
        for pref in prefs:
            last = pref.get("last_seen", "")
            if last:
                try:
                    last_dt = datetime.fromisoformat(last)
                    days_ago = (datetime.now() - last_dt).days
                    if days_ago > 30:
                        pref["confidence"] = max(0.1,
                            round(pref.get("confidence", 0.5) * 0.9, 2))
                except (ValueError, TypeError) as e:
                    logger.debug(f"偏好時間解析失敗，跳過衰減: {e}")

        # ── L6: 溝通風格（擴充版）──
        style = layers.setdefault("L6_communication_style", {})
        msg_len = len(content)

        # detail_level
        if msg_len > self._EXT_DETAILED_LEN:
            style["detail_level"] = "detailed"
        elif msg_len < self._CONCISE_MSG_LEN:
            style["detail_level"] = "concise"
        else:
            style["detail_level"] = "moderate"

        # tone: 正式/隨意/混合（含歷史窗口平滑）
        formal_markers = ["請", "您", "麻煩", "感謝", "敬請"]
        casual_markers = ["啊", "啦", "哈", "耶", "吧", "嗯", "喔"]
        formal_count = sum(1 for m in formal_markers if m in content)
        casual_count = sum(1 for m in casual_markers if m in content)

        # 歷史窗口：滾動追蹤最近 20 次的 formal/casual 計數
        tone_history = anima_user.setdefault("_tone_history", {
            "formal_total": 0, "casual_total": 0, "sample_count": 0,
        })
        tone_history["formal_total"] = int(
            tone_history.get("formal_total", 0) * 0.95 + formal_count
        )
        tone_history["casual_total"] = int(
            tone_history.get("casual_total", 0) * 0.95 + casual_count
        )
        tone_history["sample_count"] = tone_history.get("sample_count", 0) + 1

        # 用歷史累積值判斷（避免單次訊息翻轉）
        f_total = tone_history["formal_total"]
        c_total = tone_history["casual_total"]
        if f_total > c_total * 1.5:
            style["tone"] = "formal"
        elif c_total > f_total * 1.5:
            style["tone"] = "casual"
        elif f_total > 0 or c_total > 0:
            style["tone"] = "mixed"

        # emoji_usage
        import re as _re
        emoji_pattern = _re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
            "\U00002702-\U000027B0\U0001f900-\U0001f9FF"
            "\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]+")
        emoji_count = len(emoji_pattern.findall(content))
        if emoji_count >= 3:
            style["emoji_usage"] = "frequent"
        elif emoji_count >= 1:
            style["emoji_usage"] = "occasional"
        else:
            style["emoji_usage"] = "none"

        # question_style
        q_count = content.count("？") + content.count("?")
        excl_count = content.count("。") + content.count("！") + content.count("!")
        if q_count >= 2:
            style["question_style"] = "open"
        elif content.endswith(("。", "！", "!")):
            style["question_style"] = "directive"
        elif q_count >= 1:
            style["question_style"] = "closed"

        # language_mix
        ascii_chars = sum(1 for c in content if ord(c) < 128 and c.isalpha())
        cjk_chars = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
        total_chars = ascii_chars + cjk_chars
        if total_chars > 0:
            en_ratio = ascii_chars / total_chars
            if en_ratio > 0.7:
                style["language_mix"] = "english_dominant"
            elif en_ratio > 0.3:
                style["language_mix"] = "mixed"
            else:
                style["language_mix"] = "chinese_dominant"

        # avg_msg_length (rolling average)
        old_avg = style.get("avg_msg_length", 0)
        if old_avg == 0:
            style["avg_msg_length"] = msg_len
        else:
            style["avg_msg_length"] = int(old_avg * 0.85 + msg_len * 0.15)

        layers["L6_communication_style"] = style

        # ── L7: 情境角色 ──
        roles = layers.setdefault("L7_context_roles", [])
        role_map = {r["role"]: r for r in roles}
        for role_name, keywords in self._ROLE_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in content)
            if hits >= 2:
                if role_name in role_map:
                    role_map[role_name]["interaction_count"] = \
                        role_map[role_name].get("interaction_count", 0) + 1
                    role_map[role_name]["last_seen"] = now_iso
                else:
                    new_role = {
                        "role": role_name,
                        "active_since": now_iso,
                        "interaction_count": 1,
                        "last_seen": now_iso,
                    }
                    roles.append(new_role)
                    role_map[role_name] = new_role
        layers["L7_context_roles"] = roles

    # ═══════════════════════════════════════════
    # MUSEON 自我觀察（更新 ANIMA_MC）
    # ═══════════════════════════════════════════

    def _observe_self(
        self,
        skill_names: List[str],
        response_length: int,
    ) -> None:
        """更新 ANIMA_MC 的自我追蹤數據（純 CPU）.

        ★ 通過 AnimaMCStore.update() 原子讀改寫 + WriteQueue 序列化。
        """
        def _do_observe():
            def updater(anima_mc):
                # ── 1. memory_summary.total_interactions ──
                mem = anima_mc.get("memory_summary", {})
                mem["total_interactions"] = mem.get("total_interactions", 0) + 1
                anima_mc["memory_summary"] = mem

                # ── 2. evolution.iteration_count ──
                evo = anima_mc.get("evolution", {})
                evo["iteration_count"] = evo.get("iteration_count", 0) + 1
                anima_mc["evolution"] = evo

                # ── 3. capabilities.loaded_skills ──
                if skill_names:
                    caps = anima_mc.get("capabilities", {})
                    loaded = set(caps.get("loaded_skills", []))
                    prof = caps.get("skill_proficiency", {})
                    for s in skill_names:
                        loaded.add(s)
                        prof[s] = prof.get(s, 0) + 1
                    caps["loaded_skills"] = sorted(loaded)
                    caps["skill_proficiency"] = prof
                    anima_mc["capabilities"] = caps

                # ── 4. 八原語自我更新 ──
                primals = anima_mc.get("eight_primals", {})
                if primals:
                    kun = primals.get("kun_memory", {})
                    total_int = mem.get("total_interactions", 0)
                    kun["level"] = min(100, total_int // 10)
                    crystals_count = mem.get("knowledge_crystals", 0)
                    kun["signal"] = f"{total_int} 次互動、{crystals_count} 顆結晶"
                    primals["kun_memory"] = kun

                    dui = primals.get("dui_connection", {})
                    dui["level"] = min(100, total_int // 8)
                    primals["dui_connection"] = dui

                    zhen = primals.get("zhen_action", {})
                    total_skills = sum(1 for _ in (anima_mc.get("capabilities", {}).get("loaded_skills", [])))
                    zhen["level"] = min(100, 30 + total_skills * 3)
                    primals["zhen_action"] = zhen

                    anima_mc["eight_primals"] = primals

                # ── 5. Voice Evolver ──
                self._evolve_voice(anima_mc, mem.get("total_interactions", 0))

                # ── 6. L3↔L3 反射匹配（每 20 次互動）──
                total_int = mem.get("total_interactions", 0)
                if total_int > 0 and total_int % 20 == 0:
                    try:
                        anima_user = self._load_anima_user()
                        if anima_user:
                            self._match_l3_reflection(anima_mc, anima_user)
                    except Exception as e:
                        logger.warning(f"L3 匹配失敗: {e}")

                return anima_mc

            self._anima_mc_store.update(updater)

        if self._wq:
            self._wq.enqueue("anima_mc_self_observe", _do_observe)
        else:
            _do_observe()

    # ─── Morphenix Instant Note Bridge（v9.0）────────

    def _write_morphenix_note(self, category: str, content: str) -> None:
        """寫入 morphenix 即時筆記（供夜間管線消費）.

        v9.0: 讓聊天中產生的元認知洞見能即時記錄，
        不必等到夜間管線才能觸發 morphenix 結晶。
        """
        import json
        from datetime import datetime, timezone, timedelta
        notes_dir = self.data_dir / "_system" / "morphenix" / "notes"
        try:
            notes_dir.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone(timedelta(hours=8)))
            note_id = f"mc_{now.strftime('%Y%m%d_%H%M%S')}_{category}"
            note = {
                "id": note_id,
                "category": category,
                "content": content,
                "source": "metacognition_bridge",
                "created_at": now.isoformat(),
                "priority": "medium",
            }
            note_path = notes_dir / f"{note_id}.json"
            note_path.write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"[Morphenix] 即時筆記寫入: {note_id}")
        except Exception as e:
            logger.debug(f"Morphenix 筆記寫入失敗: {e}")

    # ─── Voice Evolver（Phase 9）────────────────────

    def _evolve_voice(
        self,
        anima_mc: Dict[str, Any],
        interaction_count: int,
    ) -> None:
        """每 15 次互動微調 MC 的表達風格（純 CPU）."""
        if interaction_count == 0 or interaction_count % 15 != 0:
            return

        sa = anima_mc.setdefault("self_awareness", {})
        style = sa.setdefault("expression_style", {})

        # 追蹤 opener 類型統計
        opener_stats = style.setdefault("opener_stats", {
            "greeting": 0,      # 問候開頭
            "direct": 0,        # 直接回答
            "question": 0,      # 反問開頭
            "empathy": 0,       # 共情開頭
        })

        # 追蹤語氣溫度（0=正式 → 1=隨意）
        tone_temp = style.setdefault("tone_temperature", 0.5)

        # 查詢最近的 Q-Score 歷史來判斷哪種風格效果好
        # （降級：如果 eval_engine 不可用，跳過自動調整）
        if self.eval_engine:
            try:
                recent_scores = self.eval_engine.get_recent_scores(limit=15)
                if recent_scores:
                    avg_score = sum(s.get("score", 0.5) for s in recent_scores) / len(recent_scores)
                    # 如果品質偏低，微調語氣溫度往中間靠
                    if avg_score < 0.4:
                        style["tone_temperature"] = round(
                            tone_temp * 0.95 + 0.5 * 0.05, 3
                        )
                    # 如果品質良好，維持當前方向
                    elif avg_score > 0.7:
                        pass  # 不動
            except Exception as e:
                logger.debug(f"溝通風格演化失敗（降級）: {e}")

        # 累計調整紀錄
        style["last_evolved_at"] = datetime.now().isoformat()
        style["evolution_count"] = style.get("evolution_count", 0) + 1

    # ─── Phase 11: 50 次 RC 校準 ────────────────────

    def _calibrate_rc(self, anima_user: Dict[str, Any]) -> None:
        """每 50 次互動校準 Safety Clusters 命中分佈（純 CPU）."""
        total = anima_user.get("relationship", {}).get("total_interactions", 0)
        if total == 0 or total % 50 != 0:
            return

        # 統計 safety_clusters 的累計觸發
        rc_stats = anima_user.setdefault("_rc_calibration", {
            "total_checks": 0,
            "trigger_counts": {},
            "last_calibrated_at": None,
        })
        rc_stats["total_checks"] = total
        rc_stats["last_calibrated_at"] = datetime.now().isoformat()

        # 寫入校準報告
        report_dir = self.data_dir / "guardian" / "rc_calibration"
        report_dir.mkdir(parents=True, exist_ok=True)

        report = {
            "calibrated_at": datetime.now().isoformat(),
            "total_interactions": total,
            "trigger_distribution": rc_stats.get("trigger_counts", {}),
            "recommendations": [],
        }

        # 分析觸發分佈
        triggers = rc_stats.get("trigger_counts", {})
        if triggers:
            total_triggers = sum(triggers.values())
            for cluster_name, count in triggers.items():
                ratio = count / max(total_triggers, 1)
                if ratio > 0.5:
                    report["recommendations"].append(
                        f"{cluster_name} 觸發比例偏高 ({ratio:.0%})，"
                        f"建議檢查是否誤判"
                    )

        try:
            from datetime import date
            out = report_dir / f"rc_calibration_{date.today().isoformat()}.json"
            out.write_text(
                json.dumps(report, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"RC 校準報告寫入失敗: {e}")

    # ─── Phase 12: 雙 ANIMA L3↔L3 反射匹配 ────────────────────

    def _match_l3_reflection(
        self,
        anima_mc: Dict[str, Any],
        anima_user: Dict[str, Any],
    ) -> float:
        """比較 MC 和 USER 的 L3 決策模式匹配度 (0~1)."""
        # MC 的回應策略偏好
        mc_style = anima_mc.get("self_awareness", {}).get(
            "expression_style", {}
        )
        mc_tone = mc_style.get("tone_temperature", 0.5)

        # USER 的決策模式
        user_layers = anima_user.get("seven_layers", {})
        user_patterns = user_layers.get("L3_decision_pattern", [])

        if not user_patterns:
            return 0.5  # 資料不足，回傳中性

        # 統計使用者的偏好分佈
        pattern_types = {}
        for p in user_patterns:
            ptype = p.get("pattern_type", "unknown")
            freq = p.get("frequency", 0)
            pattern_types[ptype] = pattern_types.get(ptype, 0) + freq

        # 計算匹配度
        total_freq = sum(pattern_types.values())
        if total_freq == 0:
            return 0.5

        # 技術型使用者 → MC 偏直接回答 → 匹配度與 tone 偏正式的程度相關
        tech_ratio = pattern_types.get("task_distribution", 0) / max(total_freq, 1)
        # 情緒型使用者 → MC 偏共情回答
        # Skill 密集使用者 → MC 偏結構化回答

        # 簡化匹配公式：base 0.5 + 相關因子
        match_score = 0.5
        if tech_ratio > 0.3:
            match_score += 0.1  # 技術使用者 + MC 有結構能力 = 加分
        if len(user_patterns) > 10:
            match_score += 0.1  # 足夠多的模式數據 = 匹配更可靠

        match_score = min(1.0, max(0.0, match_score))

        # 寫入 ANIMA_MC
        evo = anima_mc.setdefault("evolution", {})
        evo["l3_match_score"] = round(match_score, 3)
        evo["l3_match_updated"] = datetime.now().isoformat()

        return match_score

    # ═══════════════════════════════════════════
    # 自主排程偵測（純 CPU）
    # ═══════════════════════════════════════════

    def _detect_cron_patterns(self, content: str) -> None:
        """偵測使用者訊息中的時間模式 — 純 CPU.

        實驗功能：偵測重複的時間相關請求，記錄到緩衝區。
        累積 >= 3 次同類模式後記錄日誌。
        TODO: 未來連線自主排程系統時，此 buffer 應由排程引擎消費。

        Args:
            content: 使用者訊息
        """
        content_lower = content.lower()
        matched = any(kw in content_lower for kw in self._CRON_KEYWORDS)

        if matched:
            buf = getattr(self, '_cron_pattern_buffer', [])
            buf.append(content[:50])
            # 保持緩衝區在 20 條以內
            if len(buf) > 20:
                buf = buf[-20:]
            self._cron_pattern_buffer = buf

            if len(buf) >= 3:
                logger.info(
                    f"自主排程偵測：累積 {len(buf)} 個時間相關模式"
                )

    # ═══════════════════════════════════════════
    # 成長階段更新
    # ═══════════════════════════════════════════

    def _update_growth_stage(self) -> None:
        """更新 MUSEON 的成長階段."""
        anima_mc = self._load_anima_mc()
        if not anima_mc:
            return

        identity = anima_mc.get("identity", {})
        birth_date_str = identity.get("birth_date")
        if not birth_date_str:
            return

        try:
            birth_date = datetime.fromisoformat(birth_date_str)
        except (ValueError, TypeError):
            logger.debug(f"birth_date 格式無效: {birth_date_str!r}")
            return

        days_alive = (datetime.now() - birth_date).days
        old_days = identity.get("days_alive", 0)

        # 只有天數變化才更新
        if days_alive == old_days:
            return

        identity["days_alive"] = days_alive

        # 全能體模式：不分階段，一律 adult
        new_stage = "adult"

        old_stage = identity.get("growth_stage", "adult")
        if new_stage != old_stage:
            identity["growth_stage"] = new_stage
            logger.info(f"Growth stage evolved: {old_stage} → {new_stage} (Day {days_alive})")

            # 記錄到 evolution 追蹤
            evolution = anima_mc.get("evolution", {})
            milestones = evolution.get("milestones", [])
            milestones.append({
                "type": "growth_stage",
                "from": old_stage,
                "to": new_stage,
                "day": days_alive,
                "timestamp": datetime.now().isoformat(),
            })
            evolution["milestones"] = milestones
            anima_mc["evolution"] = evolution

        anima_mc["identity"] = identity
        self._save_anima_mc(anima_mc)
