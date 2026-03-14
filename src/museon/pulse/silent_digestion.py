"""SilentDigestion — 兩次探索之間的靜默消化引擎.

核心命題：我不是在被呼喚時才存在，而是在無聲地持續思考。

三個靜默分析（純 CPU，不呼叫 LLM）：
1. 連結重掃：找出最近探索間被忽略的概念交叉
2. 矛盾偵測：找出相同主題但結論方向相反的探索
3. 盲點偵測：偵測過度飽和的主題叢集

後向加權：根據最新探索更新舊結晶的共振指數（ri_score）。
"""

import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ── 停用詞（中英混合） ──
_STOPWORDS: Set[str] = {
    "的", "了", "和", "是", "在", "與", "或", "及", "到", "為", "從",
    "對", "中", "上", "下", "這", "那", "一個", "一種", "可以", "需要",
    "如何", "什麼", "為什麼", "最", "更", "很", "也", "都", "已", "有",
    "the", "a", "an", "of", "in", "is", "are", "for", "to", "and",
    "or", "with", "on", "at", "by", "as", "it", "its",
}

# 積極詞（暗示正面結論）
_POSITIVE_SIGNALS: Set[str] = {
    "機會", "優勢", "突破", "可行", "有效", "提升", "成長", "進步",
    "promising", "advantage", "effective", "improvement", "opportunity",
}

# 消極詞（暗示負面/風險結論）
_NEGATIVE_SIGNALS: Set[str] = {
    "風險", "問題", "困難", "限制", "挑戰", "失敗", "障礙", "不足",
    "risk", "problem", "failure", "limitation", "challenge", "difficulty",
}


def _extract_keywords(text: str, top_n: int = 20) -> List[str]:
    """從文字提取關鍵詞（中英文分詞簡化版）."""
    if not text:
        return []
    # 中文拆字節（2-4 字詞）+ 英文單詞
    words: List[str] = []
    # 英文詞
    words.extend(re.findall(r"[a-zA-Z]{3,}", text.lower()))
    # 中文片段：取 2-4 字的 n-gram
    zh_text = re.sub(r"[^\u4e00-\u9fff]", " ", text)
    for chunk in zh_text.split():
        for n in (2, 3):
            for i in range(len(chunk) - n + 1):
                words.append(chunk[i : i + n])
    # 過濾停用詞
    filtered = [w for w in words if w not in _STOPWORDS and len(w) >= 2]
    # 按頻率排序取 top_n
    counter = Counter(filtered)
    return [w for w, _ in counter.most_common(top_n)]


def _keyword_overlap(kw_a: List[str], kw_b: List[str]) -> float:
    """計算兩組關鍵詞的 Jaccard 相似度."""
    if not kw_a or not kw_b:
        return 0.0
    set_a, set_b = set(kw_a), set(kw_b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def _sentiment_direction(text: str) -> str:
    """粗略判斷文字的情感方向（positive/negative/neutral）."""
    pos = sum(1 for w in _POSITIVE_SIGNALS if w in text)
    neg = sum(1 for w in _NEGATIVE_SIGNALS if w in text)
    if pos > neg + 1:
        return "positive"
    if neg > pos + 1:
        return "negative"
    return "neutral"


class SilentDigestion:
    """兩次 Pulse 探索之間的靜默消化引擎."""

    # 連結重掃：相似度閾值
    CONNECTION_THRESHOLD = 0.25
    # 矛盾偵測：主題相似度必須夠高
    CONTRADICTION_TOPIC_THRESHOLD = 0.40
    # 盲點偵測：同一叢集在 N 天內出現超過此次數算「飽和」
    BLIND_SPOT_COUNT = 5

    def __init__(
        self,
        db: Any,  # PulseDB
        data_dir: str = "data",
        lattice: Any = None,  # KnowledgeLattice（可選，後向加權用）
    ) -> None:
        self._db = db
        self._data_dir = Path(data_dir)
        self._lattice = lattice
        self._report_dir = self._data_dir / "_system" / "pulse" / "digest_reports"
        self._report_dir.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────
    # 主入口
    # ─────────────────────────────────────────

    def digest(self, days: int = 14) -> Dict[str, Any]:
        """執行靜默消化，返回摘要報告.

        Args:
            days: 往回看幾天的探索記錄

        Returns:
            report dict 含 connections / contradictions / blind_spots / reweighted
        """
        try:
            explorations = self._db.get_explorations_full(days=days, limit=50)
        except Exception as e:
            logger.warning(f"SilentDigestion: failed to load explorations: {e}")
            return {"status": "failed", "reason": str(e)}

        if len(explorations) < 2:
            return {"status": "skipped", "reason": "not enough explorations"}

        # 預計算每筆探索的關鍵詞
        for exp in explorations:
            combined = (exp.get("topic") or "") + " " + (exp.get("findings") or "")
            exp["_keywords"] = _extract_keywords(combined, top_n=20)
            exp["_sentiment"] = _sentiment_direction(exp.get("findings") or "")

        connections = self._scan_connections(explorations)
        contradictions = self._detect_contradictions(explorations)
        blind_spots = self._detect_blind_spots(explorations)
        reweighted = self._backward_reweight(explorations)

        report = {
            "status": "done",
            "generated_at": datetime.now(TZ8).isoformat(),
            "explorations_analyzed": len(explorations),
            "connections": connections,
            "contradictions": contradictions,
            "blind_spots": blind_spots,
            "reweighted_crystals": reweighted,
            "summary": self._build_summary(connections, contradictions, blind_spots, reweighted),
        }

        path = self._save_report(report)
        report["report_path"] = path
        logger.info(
            f"SilentDigestion done: {len(connections)} connections, "
            f"{len(contradictions)} contradictions, {len(blind_spots)} blind spots"
        )
        return report

    # ─────────────────────────────────────────
    # 1. 連結重掃
    # ─────────────────────────────────────────

    def _scan_connections(self, explorations: List[Dict]) -> List[Dict]:
        """找出最近探索間被忽略的概念連結."""
        connections = []
        n = len(explorations)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = explorations[i], explorations[j]
                # 已經是同一個後續主題鏈的跳過（crystal_id 相同）
                if a.get("crystal_id") and a.get("crystal_id") == b.get("crystal_id"):
                    continue
                overlap = _keyword_overlap(a["_keywords"], b["_keywords"])
                if overlap >= self.CONNECTION_THRESHOLD:
                    shared = list(set(a["_keywords"]) & set(b["_keywords"]))[:5]
                    connections.append({
                        "exploration_a": {"id": a.get("id"), "topic": a["topic"]},
                        "exploration_b": {"id": b.get("id"), "topic": b["topic"]},
                        "overlap_score": round(overlap, 3),
                        "shared_concepts": shared,
                    })
        # 按相似度降序，取 top 10
        connections.sort(key=lambda x: x["overlap_score"], reverse=True)
        return connections[:10]

    # ─────────────────────────────────────────
    # 2. 矛盾偵測
    # ─────────────────────────────────────────

    def _detect_contradictions(self, explorations: List[Dict]) -> List[Dict]:
        """找出相同主題但結論方向相反的探索."""
        contradictions = []
        n = len(explorations)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = explorations[i], explorations[j]
                # 主題相似度要夠高才算「同一主題」
                topic_overlap = _keyword_overlap(
                    _extract_keywords(a["topic"]),
                    _extract_keywords(b["topic"]),
                )
                if topic_overlap < self.CONTRADICTION_TOPIC_THRESHOLD:
                    continue
                # 情感方向相反
                if (
                    a["_sentiment"] == "positive"
                    and b["_sentiment"] == "negative"
                ) or (
                    a["_sentiment"] == "negative"
                    and b["_sentiment"] == "positive"
                ):
                    contradictions.append({
                        "exploration_a": {
                            "id": a.get("id"),
                            "topic": a["topic"],
                            "timestamp": a.get("timestamp", ""),
                            "direction": a["_sentiment"],
                        },
                        "exploration_b": {
                            "id": b.get("id"),
                            "topic": b["topic"],
                            "timestamp": b.get("timestamp", ""),
                            "direction": b["_sentiment"],
                        },
                        "topic_overlap": round(topic_overlap, 3),
                        "note": "同主題，不同結論方向——值得深入釐清",
                    })
        return contradictions[:5]

    # ─────────────────────────────────────────
    # 3. 盲點偵測
    # ─────────────────────────────────────────

    def _detect_blind_spots(self, explorations: List[Dict]) -> List[str]:
        """偵測過度飽和的主題叢集.

        把探索按關鍵詞聚類，同一叢集出現次數 >= BLIND_SPOT_COUNT 算飽和。
        """
        if not explorations:
            return []

        # 用最常見關鍵詞作為叢集代表
        cluster_counter: Counter = Counter()
        for exp in explorations:
            top3 = exp["_keywords"][:3]
            for kw in top3:
                cluster_counter[kw] += 1

        blind_spots = [
            kw for kw, count in cluster_counter.most_common(15)
            if count >= self.BLIND_SPOT_COUNT
        ]
        return blind_spots[:8]

    # ─────────────────────────────────────────
    # 4. 後向加權（更新舊結晶的 ri_score）
    # ─────────────────────────────────────────

    def _backward_reweight(self, explorations: List[Dict]) -> Dict[str, float]:
        """根據最新探索更新舊結晶的共振指數.

        邏輯：如果最近 N 次探索的關鍵詞與某個結晶高度重疊，
        說明這個結晶「被驗證」了，ri_score 提升 0.05。
        長時間沒被引用的結晶自然衰減（由 nightly 負責）。

        Returns:
            Dict[crystal_cuid -> new_ri_score]
        """
        if not self._lattice:
            return {}

        try:
            crystals = self._lattice.get_all_crystals()
        except Exception as e:
            logger.warning(f"SilentDigestion backward_reweight: lattice error: {e}")
            return {}

        if not crystals:
            return {}

        # 最近 7 天的探索才參與後向加權
        recent = [
            exp for exp in explorations
            if exp.get("timestamp", "") >= (
                datetime.now(TZ8) - timedelta(days=7)
            ).isoformat()
        ]
        if not recent:
            return {}

        # 合併最近探索關鍵詞
        recent_keywords: Set[str] = set()
        for exp in recent:
            recent_keywords.update(exp["_keywords"])

        updated: Dict[str, float] = {}
        for crystal in crystals:
            # 結晶的關鍵詞來自 g1_summary + g4_insights
            crystal_text = crystal.g1_summary + " " + " ".join(crystal.g4_insights)
            crystal_kws = set(_extract_keywords(crystal_text))
            if not crystal_kws:
                continue
            overlap = len(recent_keywords & crystal_kws) / len(crystal_kws)
            if overlap >= 0.30:  # 30% 以上關鍵詞重疊
                new_score = min(1.0, crystal.ri_score + 0.05 * overlap)
                if new_score != crystal.ri_score:
                    try:
                        crystal.ri_score = new_score
                        # 持久化透過 lattice store 直接寫
                        self._lattice._store.save_crystals(
                            {**self._lattice._store.load_crystals(), crystal.cuid: crystal}
                        )
                        updated[crystal.cuid] = new_score
                    except Exception:
                        pass  # 不阻斷主流程

        return updated

    # ─────────────────────────────────────────
    # 報告
    # ─────────────────────────────────────────

    def _build_summary(
        self,
        connections: List[Dict],
        contradictions: List[Dict],
        blind_spots: List[str],
        reweighted: Dict[str, float],
    ) -> str:
        parts = []
        if connections:
            top = connections[0]
            parts.append(
                f"發現 {len(connections)} 個概念交叉，"
                f"最強連結：「{top['exploration_a']['topic'][:20]}」↔「{top['exploration_b']['topic'][:20]}」"
                f"（相似度 {top['overlap_score']}）"
            )
        if contradictions:
            c = contradictions[0]
            parts.append(
                f"偵測到 {len(contradictions)} 個矛盾觀點，"
                f"例：「{c['exploration_a']['topic'][:20]}」({c['exploration_a']['direction']}) "
                f"vs「{c['exploration_b']['topic'][:20]}」({c['exploration_b']['direction']})"
            )
        if blind_spots:
            parts.append(f"飽和叢集（已過度探索）：{', '.join(blind_spots[:4])}")
        if reweighted:
            parts.append(f"更新了 {len(reweighted)} 個結晶的共振指數")
        return "；".join(parts) if parts else "無顯著發現"

    def _save_report(self, report: Dict) -> str:
        today = datetime.now(TZ8).strftime("%Y-%m-%d")
        path = self._report_dir / f"digest_{today}.json"
        # 若今天已有報告，讀取並合併（取最新）
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"SilentDigestion: failed to save report: {e}")
        return str(path)
