"""VisionLoop — MUSEON 願景迴圈.

每週日 Nightly 自動觸發。
CPU 層：從多個信號源匯聚「MUSEON 應該往哪裡長」的提案。
LLM 層：（未來）由 L2 Opus 做深度願景推演。

信號源：
1. 星座雷達 — 使用者群體最弱維度 → 該領域需要更強的 Skill
2. Skill 命中率 — 低命中 Skill → 可能需要重新設計或淘汰
3. 探索結晶 — 新發現的領域 → 潛在新 Skill 方向
4. 呼吸分析 — 系統結構問題 → 架構演化方向
5. Decision Atlas — 創造者的判斷偏好 → 品味校準

輸出：vision_proposals.json — 最多 3 個願景提案
每個提案包含：方向、理由、信號來源、與六大荒謬的關聯、預估 blast radius
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))


def _scan_constellation_gaps(data_dir: Path) -> List[Dict]:
    """掃描星座系統中的最弱維度."""
    gaps = []
    radar_dir = data_dir / "_system" / "constellations"
    registry_file = radar_dir / "registry.json"
    if not registry_file.exists():
        return gaps

    try:
        registry = json.loads(registry_file.read_text())
        constellations = registry.get("constellations", [])
        # 支援 list 或 dict 格式
        if isinstance(constellations, list):
            items = [(c.get("name", ""), c) for c in constellations]
        else:
            items = constellations.items()
        for cid, meta in items:
            if meta.get("status") != "active":
                continue
            # 讀取該星座的使用者資料
            user_file = radar_dir / cid / "users" / "boss.json"
            if not user_file.exists():
                continue
            user_data = json.loads(user_file.read_text())
            scores = user_data.get("scores", {})
            if not scores:
                continue
            # 找最弱維度
            weakest_dim = min(scores, key=scores.get)
            weakest_val = scores[weakest_dim]
            if weakest_val < 0.4:
                gaps.append({
                    "constellation": cid,
                    "dimension": weakest_dim,
                    "score": weakest_val,
                    "signal": "constellation_gap",
                })
    except Exception as e:
        logger.warning(f"[VISION] constellation scan error: {e}")

    return gaps


def _scan_skill_health(data_dir: Path) -> List[Dict]:
    """掃描 Skill 健康狀態（低命中率/低品質）."""
    signals = []
    health_file = data_dir / "_system" / "skill_health" / "latest.json"
    if not health_file.exists():
        return signals

    try:
        health = json.loads(health_file.read_text())
        for skill_id, metrics in health.items():
            hit_rate = metrics.get("hit_rate", 1.0)
            quality = metrics.get("avg_quality", 1.0)
            if hit_rate < 0.1 and metrics.get("total_invocations", 0) > 5:
                signals.append({
                    "skill": skill_id,
                    "hit_rate": hit_rate,
                    "quality": quality,
                    "signal": "low_hit_rate",
                })
            elif quality < 0.5 and metrics.get("total_invocations", 0) > 3:
                signals.append({
                    "skill": skill_id,
                    "hit_rate": hit_rate,
                    "quality": quality,
                    "signal": "low_quality",
                })
    except Exception as e:
        logger.warning(f"[VISION] skill health scan error: {e}")

    return signals


def _scan_decision_atlas(data_dir: Path) -> List[Dict]:
    """掃描決策圖譜的覆蓋度缺口."""
    signals = []
    atlas_dir = data_dir / "_system" / "decision_atlas"
    if not atlas_dir.exists():
        return signals

    # 統計覆蓋度矩陣
    dimensions = ["self_awareness", "direction", "gap", "accumulation", "leverage", "integration"]
    categories = ["taste", "priority", "boundary", "strategy", "value"]

    coverage = {}
    for f in atlas_dir.glob("da-*.json"):
        try:
            crystal = json.loads(f.read_text())
            dim = crystal.get("absurdity_dimension", "unknown")
            cat = crystal.get("category", "unknown")
            key = f"{dim}:{cat}"
            coverage[key] = coverage.get(key, 0) + 1
        except Exception:
            continue

    # 找完全空白的格子
    total_cells = len(dimensions) * len(categories)
    filled = sum(1 for d in dimensions for c in categories if coverage.get(f"{d}:{c}", 0) > 0)
    coverage_pct = filled / max(total_cells, 1)

    if coverage_pct < 0.5:
        # 找出最空的維度
        dim_counts = {d: sum(coverage.get(f"{d}:{c}", 0) for c in categories) for d in dimensions}
        emptiest = min(dim_counts, key=dim_counts.get)
        signals.append({
            "type": "atlas_gap",
            "dimension": emptiest,
            "coverage_pct": round(coverage_pct, 2),
            "signal": "decision_atlas_gap",
        })

    return signals


def _scan_breath_patterns(data_dir: Path) -> List[Dict]:
    """掃描最近的呼吸分析結果."""
    signals = []
    patterns_dir = data_dir / "_system" / "breath" / "patterns"
    if not patterns_dir.exists():
        return signals

    # 找最新的分析
    pattern_files = sorted(patterns_dir.glob("*.json"), reverse=True)
    if not pattern_files:
        return signals

    try:
        latest = json.loads(pattern_files[0].read_text())
        layers = latest.get("layers", {})
        scope = layers.get("L4_coupling", {}).get("affected_scope", "low")
        suggestions = layers.get("L5_first_principles", {}).get("suggestions", [])

        if scope in ("medium", "high"):
            signals.append({
                "scope": scope,
                "suggestions": [s.get("description", "") for s in suggestions[:2]],
                "signal": "breath_structural",
            })
    except Exception as e:
        logger.warning(f"[VISION] breath scan error: {e}")

    return signals


def generate_vision_proposals(data_dir: Path) -> Dict[str, Any]:
    """匯聚所有信號，產出最多 3 個願景提案.

    只在週日執行。其他天回傳 skip。
    """
    now = datetime.now(TZ_TAIPEI)
    if now.weekday() != 6:  # 6 = Sunday
        return {"status": "skipped", "reason": "only runs on Sunday"}

    # 掃描四個信號源
    constellation_gaps = _scan_constellation_gaps(data_dir)
    skill_signals = _scan_skill_health(data_dir)
    atlas_signals = _scan_decision_atlas(data_dir)
    breath_signals = _scan_breath_patterns(data_dir)

    all_signals = constellation_gaps + skill_signals + atlas_signals + breath_signals

    if not all_signals:
        return {
            "status": "no_signals",
            "timestamp": now.isoformat(),
            "proposals": [],
        }

    # 依信號類型產出提案（最多 3 個）
    proposals = []

    # 優先級 1: 結構性問題（breath）
    for sig in breath_signals[:1]:
        proposals.append({
            "direction": "architecture_evolution",
            "description": f"呼吸分析偵測到結構性問題（scope={sig.get('scope')}），建議優先修復",
            "signal_source": "breath_analyzer",
            "absurdity_link": "integration",
            "blast_radius": "medium",
            "raw_signal": sig,
        })

    # 優先級 2: 使用者缺口（constellation）
    for sig in constellation_gaps[:1]:
        proposals.append({
            "direction": "skill_enhancement",
            "description": f"星座 {sig['constellation']} 的 {sig['dimension']} 維度偏低（{sig['score']:.0%}），建議強化相關 Skill",
            "signal_source": "constellation_radar",
            "absurdity_link": sig.get("dimension", "unknown"),
            "blast_radius": "low",
            "raw_signal": sig,
        })

    # 優先級 3: 決策圖譜覆蓋度缺口
    for sig in atlas_signals[:1]:
        proposals.append({
            "direction": "decision_atlas_enrichment",
            "description": f"決策圖譜覆蓋度 {sig.get('coverage_pct', 0):.0%}，維度 {sig.get('dimension', '?')} 最空，建議主動結晶",
            "signal_source": "decision_atlas",
            "absurdity_link": sig.get("dimension", "unknown"),
            "blast_radius": "low",
            "raw_signal": sig,
        })

    # 優先級 4: Skill 健康問題
    for sig in skill_signals[:1]:
        proposals.append({
            "direction": "skill_optimization",
            "description": f"Skill {sig['skill']} 命中率/品質偏低，建議優化或淘汰",
            "signal_source": "skill_health",
            "absurdity_link": "accumulation",
            "blast_radius": "low",
            "raw_signal": sig,
        })

    # 限制最多 3 個
    proposals = proposals[:3]

    result = {
        "status": "generated",
        "timestamp": now.isoformat(),
        "week_id": f"{now.year}-w{now.isocalendar()[1]:02d}",
        "total_signals": len(all_signals),
        "proposals": proposals,
    }

    # 寫入檔案
    vision_dir = data_dir / "_system" / "breath" / "visions"
    vision_dir.mkdir(parents=True, exist_ok=True)
    vision_file = vision_dir / f"{result['week_id']}.json"
    with open(vision_file, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(f"[VISION] 產出 {len(proposals)} 個願景提案 (from {len(all_signals)} signals)")

    return result
