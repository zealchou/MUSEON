"""Recommender — 推薦引擎 (CrystalStore + Knowledge Graph).

基於使用者互動歷史、知識晶格連結、及探索性注入，
提供混合式推薦，兼顧相關性與意外驚喜。

設計原則：
- 三路混合：協同過濾 + 內容過濾 + 偶然性注入
- 多因子評分：近因性、相關性、新奇性
- 所有外部依賴 try/except 包裹
- 互動歷史持久化到 data/_system/recommendations/interactions.json
- 結晶資料來源：CrystalStore（SQLite WAL）
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

MAX_INTERACTIONS = 5000          # 互動歷史上限
RECENCY_HALF_LIFE_DAYS = 7.0    # 近因性半衰期
NOVELTY_BONUS = 0.3             # 未見過項目的新奇加成
SERENDIPITY_RATIO = 0.2         # 偶然性注入比例
INTERACTION_DECAY = 0.95         # 舊互動衰減因子

# 互動類型權重
ACTION_WEIGHTS: Dict[str, float] = {
    "view": 0.3,
    "click": 0.5,
    "bookmark": 0.8,
    "share": 0.9,
    "rate": 1.0,
    "dismiss": -0.5,
}

# 推薦項目類型
ITEM_TYPES = {"crystal", "reference", "exploration"}


class Recommender:
    """推薦引擎 — 基於 CrystalStore + Knowledge Graph."""

    def __init__(
        self,
        workspace: Optional[str] = None,
        event_bus: Any = None,
        crystal_store: Any = None,
    ) -> None:
        ws = workspace or os.getenv("MUSEON_WORKSPACE", str(Path.home() / "MUSEON"))
        self._workspace = Path(ws)
        self._event_bus = event_bus
        self._crystal_store = crystal_store

        # 互動歷史
        self._interactions_dir = self._workspace / "data" / "_system" / "recommendations"
        self._interactions_dir.mkdir(parents=True, exist_ok=True)
        self._interactions_path = self._interactions_dir / "interactions.json"
        self._interactions: List[Dict] = self._load_interactions()

        # 快取：item_id → 互動統計
        self._item_stats: Dict[str, Dict] = self._build_item_stats()

        logger.info(
            f"Recommender 初始化完成 "
            f"(crystal_store={'connected' if crystal_store else 'degraded'}, "
            f"interactions={len(self._interactions)})"
        )

    # ── Persistence ─────────────────────────────────────

    def _load_interactions(self) -> List[Dict]:
        """載入互動歷史."""
        if self._interactions_path.exists():
            try:
                data = json.loads(self._interactions_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data[-MAX_INTERACTIONS:]
                return []
            except Exception as e:
                logger.warning(f"Failed to load interactions: {e}")
        return []

    def _save_interactions(self) -> None:
        """持久化互動歷史（原子寫入）."""
        try:
            tmp = self._interactions_path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(self._interactions[-MAX_INTERACTIONS:], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self._interactions_path)
        except Exception as e:
            logger.error(f"Failed to save interactions: {e}")

    def _build_item_stats(self) -> Dict[str, Dict]:
        """從互動歷史建構項目統計快取."""
        stats: Dict[str, Dict] = defaultdict(lambda: {
            "total_score": 0.0, "count": 0, "last_seen": None, "actions": defaultdict(int),
        })
        for ix in self._interactions:
            item_id = ix.get("item_id", "")
            if not item_id:
                continue
            action = ix.get("action", "view")
            weight = ACTION_WEIGHTS.get(action, 0.3)
            s = stats[item_id]
            s["total_score"] += weight
            s["count"] += 1
            s["actions"][action] += 1
            s["last_seen"] = ix.get("timestamp")
        return dict(stats)

    # ── Public API ──────────────────────────────────────

    async def get_recommendations(
        self, user_context: Optional[Dict] = None, limit: int = 5
    ) -> List[Dict]:
        """混合推薦：協同過濾 + 內容過濾 + 偶然性注入.

        Args:
            user_context: 使用者上下文（當前話題、最近互動等）
            limit: 推薦數量上限

        Returns:
            List of recommendation dicts: {item_id, item_type, title, score, reason}
        """
        context = user_context or {}
        candidates: List[Dict] = []

        # 1. 協同過濾候選
        try:
            collab_items = self._collaborative_filter(context)
            candidates.extend(collab_items)
        except Exception as e:
            logger.warning(f"Collaborative filter error: {e}")

        # 2. 內容過濾候選
        try:
            content_items = self._content_filter(context)
            candidates.extend(content_items)
        except Exception as e:
            logger.warning(f"Content filter error: {e}")

        # 3. 去重（按 item_id）
        seen: Set[str] = set()
        unique: List[Dict] = []
        for item in candidates:
            iid = item.get("item_id", "")
            if iid and iid not in seen:
                seen.add(iid)
                unique.append(item)

        # 4. 評分排序
        scored = []
        for item in unique:
            item["score"] = self._score_item(item, context)
            scored.append(item)
        scored.sort(key=lambda x: x["score"], reverse=True)

        # 5. 偶然性注入
        result = self._serendipity_injection(scored, ratio=SERENDIPITY_RATIO)

        return result[:limit]

    def record_interaction(
        self, item_id: str, action: str, rating: Optional[float] = None
    ) -> None:
        """記錄使用者互動.

        Args:
            item_id: 項目 ID
            action: 互動類型 (view, click, bookmark, share, rate, dismiss)
            rating: 可選的顯式評分 (0.0~1.0)
        """
        interaction = {
            "item_id": item_id,
            "action": action,
            "rating": rating,
            "timestamp": datetime.now(TZ8).isoformat(),
        }
        self._interactions.append(interaction)

        # 更新快取
        if item_id not in self._item_stats:
            self._item_stats[item_id] = {
                "total_score": 0.0, "count": 0, "last_seen": None, "actions": defaultdict(int),
            }
        s = self._item_stats[item_id]
        weight = ACTION_WEIGHTS.get(action, 0.3)
        if rating is not None:
            weight = rating
        s["total_score"] += weight
        s["count"] += 1
        s["actions"][action] += 1
        s["last_seen"] = interaction["timestamp"]

        self._save_interactions()

        # 發布事件
        try:
            if self._event_bus is not None:
                from museon.core.event_bus import USER_FEEDBACK_SIGNAL
                self._event_bus.publish(USER_FEEDBACK_SIGNAL, {
                    "item_id": item_id,
                    "action": action,
                    "rating": rating,
                    "source": "recommender",
                })
        except Exception as e:
            logger.warning(f"Failed to publish interaction event: {e}")

    # ── Scoring ─────────────────────────────────────────

    def _score_item(self, item: Dict, context: Dict) -> float:
        """多因子評分：近因性 + 相關性 + 新奇性.

        Weights:
            recency  0.3 — 近期互動過的項目衰減
            relevance 0.5 — 與當前上下文的匹配度
            novelty  0.2 — 未見過的項目加成
        """
        item_id = item.get("item_id", "")
        base_score = item.get("score", 0.5)

        # 近因性（見過越久的衰減越少，沒見過的得滿分）
        recency_score = 1.0
        stats = self._item_stats.get(item_id)
        if stats and stats.get("last_seen"):
            try:
                last_dt = datetime.fromisoformat(stats["last_seen"])
                days_ago = (datetime.now(TZ8) - last_dt).total_seconds() / 86400
                recency_score = 1.0 - math.exp(-days_ago / RECENCY_HALF_LIFE_DAYS)
            except Exception:
                recency_score = 0.5

        # 相關性（基於上下文關鍵字匹配）
        relevance_score = self._compute_relevance(item, context)

        # 新奇性（從未互動過 = 高新奇性）
        novelty_score = 1.0 if item_id not in self._item_stats else 0.3

        final = (
            0.3 * recency_score
            + 0.5 * relevance_score
            + 0.2 * novelty_score
        ) * base_score

        return round(final, 4)

    def _compute_relevance(self, item: Dict, context: Dict) -> float:
        """基於關鍵字匹配計算相關性."""
        ctx_keywords = set(context.get("keywords", []))
        ctx_topic = context.get("topic", "").lower()
        if not ctx_keywords and not ctx_topic:
            return 0.5  # 無上下文，給中等分

        item_text = (
            item.get("title", "") + " " + item.get("description", "")
        ).lower()
        item_tags = set(t.lower() for t in item.get("tags", []))

        matches = 0
        total = max(len(ctx_keywords), 1)
        for kw in ctx_keywords:
            if kw.lower() in item_text or kw.lower() in item_tags:
                matches += 1
        keyword_score = matches / total

        topic_score = 0.0
        if ctx_topic and ctx_topic in item_text:
            topic_score = 0.8

        return min(1.0, keyword_score * 0.6 + topic_score * 0.4)

    # ── Filtering Strategies ────────────────────────────

    def _collaborative_filter(self, context: Dict) -> List[Dict]:
        """協同過濾 — 基於互動模式推薦相似項目.

        策略：找出使用者互動過的高分項目，透過 crystal links 找關聯結晶。
        """
        candidates: List[Dict] = []
        if not self._crystal_store:
            return candidates

        # 找出近期互動中的高分項目
        recent = self._interactions[-50:]
        high_score_ids: Set[str] = set()
        for ix in recent:
            action = ix.get("action", "view")
            if ACTION_WEIGHTS.get(action, 0) >= 0.5:
                high_score_ids.add(ix.get("item_id", ""))

        if not high_score_ids:
            return candidates

        # 從 CrystalStore 的 links 表找關聯結晶
        try:
            links = self._crystal_store.load_links()
            # 建立 cuid → crystal 索引（懶載入）
            crystals_by_id: Optional[Dict] = None

            for link in links:
                link_dict = link if isinstance(link, dict) else link.to_dict()
                source = link_dict.get("from_cuid", "")
                target = link_dict.get("to_cuid", "")
                confidence = link_dict.get("confidence", 0.5)

                if source in high_score_ids and target not in high_score_ids:
                    # 懶載入結晶標題
                    if crystals_by_id is None:
                        raw = self._crystal_store.load_crystals_raw()
                        crystals_by_id = {c["cuid"]: c for c in raw}

                    crystal = crystals_by_id.get(target, {})
                    if crystal.get("status", "active") != "active":
                        continue

                    tags = crystal.get("tags", [])
                    if isinstance(tags, str):
                        try:
                            tags = json.loads(tags)
                        except Exception:
                            tags = []

                    candidates.append({
                        "item_id": target,
                        "item_type": "crystal",
                        "title": crystal.get("g1_summary", target),
                        "score": confidence,
                        "reason": "collaborative: linked to crystals you interacted with",
                        "tags": tags,
                        "description": crystal.get("g3_root_inquiry", "")[:100],
                    })
        except Exception as e:
            logger.debug(f"CrystalStore links not available for collab filter: {e}")

        return candidates[:20]

    def _content_filter(self, context: Dict) -> List[Dict]:
        """內容過濾 — 從 CrystalStore 中搜尋匹配當前上下文的結晶.

        策略：掃描活躍結晶的 g1_summary + tags + domain，匹配上下文關鍵字。
        """
        candidates: List[Dict] = []
        topic = context.get("topic", "")
        keywords = context.get("keywords", [])
        search_terms = ([topic] if topic else []) + keywords

        if not search_terms or not self._crystal_store:
            return candidates

        try:
            raw_crystals = self._crystal_store.load_crystals_raw()
            for crystal in raw_crystals:
                if crystal.get("status", "active") != "active":
                    continue

                tags = crystal.get("tags", [])
                if isinstance(tags, str):
                    try:
                        tags = json.loads(tags)
                    except Exception:
                        tags = []

                text = (
                    crystal.get("g1_summary", "")
                    + " " + crystal.get("g3_root_inquiry", "")
                    + " " + crystal.get("domain", "")
                    + " " + " ".join(tags)
                ).lower()

                for term in search_terms:
                    if term.lower() in text:
                        candidates.append({
                            "item_id": crystal.get("cuid", ""),
                            "item_type": "crystal",
                            "title": crystal.get("g1_summary", ""),
                            "score": crystal.get("ri_score", 0.5),
                            "reason": f"content: matches '{term}'",
                            "tags": tags,
                            "description": crystal.get("g3_root_inquiry", "")[:100],
                        })
                        break
        except Exception as e:
            logger.debug(f"Crystal content filter failed: {e}")

        return candidates[:30]

    def _serendipity_injection(
        self, items: List[Dict], ratio: float = 0.2
    ) -> List[Dict]:
        """偶然性注入 — 隨機插入未見過的新奇項目.

        Args:
            items: 已排序的候選項目
            ratio: 注入比例 (0.0~1.0)

        Returns:
            包含偶然性項目的列表
        """
        if not items:
            return items

        inject_count = max(1, int(len(items) * ratio))
        seen_ids = {ix.get("item_id") for ix in self._interactions}

        # 找未互動過的項目作為偶然性候選
        novel_candidates: List[Dict] = []
        for item in items:
            if item.get("item_id") not in seen_ids:
                novel_candidates.append(item)

        # 如果現有候選中沒有新奇項目，從 CrystalStore 隨機取
        if not novel_candidates:
            novel_candidates = self._discover_random_items(limit=inject_count)

        if not novel_candidates:
            return items

        # 隨機選取 inject_count 個
        injected = random.sample(novel_candidates, min(inject_count, len(novel_candidates)))
        for item in injected:
            item["reason"] = "serendipity: novel discovery"
            item["score"] = max(item.get("score", 0.5), NOVELTY_BONUS)

        # 均勻插入到結果列表中
        result = list(items)
        for i, inj in enumerate(injected):
            pos = min(len(result), (i + 1) * max(1, len(result) // (inject_count + 1)))
            if inj not in result:
                result.insert(pos, inj)

        return result

    def _discover_random_items(self, limit: int = 3) -> List[Dict]:
        """從 CrystalStore 隨機發現結晶."""
        all_items: List[Dict] = []
        if not self._crystal_store:
            return all_items
        try:
            raw_crystals = self._crystal_store.load_crystals_raw()
            active = [c for c in raw_crystals if c.get("status", "active") == "active"]
            random.shuffle(active)
            for crystal in active[:limit]:
                tags = crystal.get("tags", [])
                if isinstance(tags, str):
                    try:
                        tags = json.loads(tags)
                    except Exception:
                        tags = []
                all_items.append({
                    "item_id": crystal.get("cuid", ""),
                    "item_type": "crystal",
                    "title": crystal.get("g1_summary", ""),
                    "score": NOVELTY_BONUS,
                    "reason": "serendipity: random crystal",
                    "tags": tags,
                })
        except Exception as e:
            logger.debug(f"[RECOMMENDER] random crystal discovery failed (degraded): {e}")
        return all_items
