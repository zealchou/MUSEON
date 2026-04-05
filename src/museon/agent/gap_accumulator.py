"""gap_accumulator.py — MUSEON 能力缺口偵測與累積（三軌道：A 聚類/B 品質/C 弱匹配）"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("museon.agent.gap_accumulator")

_SIM_TH = 0.85   # cosine 閾值
_A_NOTE = 3      # Track A 寫 note
_A_EVT  = 5      # Track A 發 event
_B_NOTE = 3      # Track B 寫 note（7 天）
_B_EVT  = 5      # Track B 發 event（7 天）
_DAYS   = 7


# ─── 公開入口（fire-and-forget）───────────────────────────────────────────────

def record_gap(
    workspace: Path,
    query: str,
    matched_skills: list[str],
    confidence: float,
    q_score: float | None,
    user_id: str = "",
    group_id: str = "",
) -> None:
    try:
        _dispatch(workspace, query, matched_skills, confidence, q_score, user_id, group_id)
    except Exception as exc:
        logger.warning("[gap_accumulator] silently swallowed: %s", exc)


def _dispatch(ws, query, matched_skills, confidence, q_score, user_id, group_id):
    now = datetime.now(timezone.utc)
    if confidence < 0.4:
        _track_a(ws, query, matched_skills, confidence, user_id, group_id, now)
    elif confidence <= 0.65 and matched_skills and q_score is not None and q_score < 0.4:
        _track_b(ws, query, matched_skills[0], q_score, user_id, now)
    elif confidence <= 0.65:
        _track_c(ws, query, matched_skills, confidence, q_score, user_id, now)
    elif matched_skills and q_score is not None and q_score < 0.4:
        _track_b(ws, query, matched_skills[0], q_score, user_id, now)


# ─── Track A: 無匹配 → Qdrant 語意聚類 ──────────────────────────────────────

def _track_a(ws, query, matched_skills, confidence, user_id, group_id, now):
    try:
        from museon.vector.vector_bridge import VectorBridge
        vb = VectorBridge(workspace=ws)
    except Exception as exc:
        logger.debug("[gap_accumulator] VectorBridge init: %s", exc)
        return

    hits = []
    try:
        hits = vb.search(collection="gaps", query=query, limit=10, score_threshold=_SIM_TH)
    except Exception as exc:
        logger.debug("[gap_accumulator] Qdrant search: %s", exc)

    # VectorBridge search 回傳扁平 dict（無 payload 子層）
    cluster_id = hits[0].get("cluster_id", str(uuid.uuid4())) if hits else str(uuid.uuid4())
    hit_users = {h.get("user_id", "") for h in hits}
    if user_id:
        hit_users.add(user_id)
    unique_users = len(hit_users - {""})
    discount = 1 if unique_users >= 2 else 0

    try:
        vb.index(collection="gaps", doc_id=f"gap_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}",
                 text=query, metadata={"query": query, "matched_skills": matched_skills,
                 "confidence": confidence, "user_id": user_id, "group_id": group_id,
                 "timestamp": now.isoformat(), "cluster_id": cluster_id})
    except Exception as exc:
        logger.debug("[gap_accumulator] Qdrant index: %s", exc)

    size = len(hits) + 1
    seen: dict[str, None] = {}
    for _q in [h.get("query", "") for h in hits[:4]] + [query]:
        if _q:
            seen[_q] = None
    queries = list(seen)[:5]
    topic = queries[0][:60] if queries else query[:60]

    if size >= _A_NOTE - discount:
        _save_note(ws, f"scout_gap_cluster_{_ts(now)}", {"type": "scout_gap_cluster",
            "topic": topic, "gap_identified": query, "sample_queries": queries,
            "suggested_skill": f"new-skill-{topic.lower().replace(' ','-')[:30]}",
            "source": "gap_accumulator", "created_at": now.isoformat(), "auto_propose": True})
    if size >= _A_EVT - discount:
        _pub("SKILL_GAP_PROPOSAL", {"type": "forge_new", "topic": topic,
            "sample_queries": queries, "cluster_count": size, "unique_users": unique_users})
        _save_req(ws, f"req_{_ts(now)}_forge", {"type": "forge_new", "topic": topic,
            "gap_cluster_summary": f"Repeated unmatched queries: {topic}",
            "sample_queries": queries, "status": "pending_dse", "created_at": now.isoformat()})


# ─── Track B: 品質差 → JSONL 累積 ────────────────────────────────────────────

def _track_b(ws, query, skill_name, q_score, user_id, now):
    path = ws / "_system" / "quality_gaps.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"skill_name": skill_name, "query": query, "q_score": q_score,
                                "user_id": user_id, "timestamp": now.isoformat()}, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("[gap_accumulator] JSONL write: %s", exc)
        return

    cutoff = now - timedelta(days=_DAYS)
    recent: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("skill_name") != skill_name:
                continue
            try:
                ts = datetime.fromisoformat(row["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    recent.append(row)
            except (KeyError, ValueError):
                continue
    except Exception as exc:
        logger.debug("[gap_accumulator] JSONL read: %s", exc)
        return

    cnt = len(recent)
    avg_q = round(sum(r["q_score"] for r in recent) / cnt, 4) if cnt else 0
    failures = [{"query": r["query"], "q_score": r["q_score"]} for r in recent[:5]]

    if cnt >= _B_NOTE:
        _save_note(ws, f"scout_skill_optimize_{_ts(now)}", {"type": "scout_skill_optimize",
            "topic": f"optimize {skill_name}", "gap_identified": f"{skill_name} avg Q={avg_q}",
            "sample_queries": [f["query"] for f in failures[:3]], "suggested_skill": skill_name,
            "source": "gap_accumulator", "created_at": now.isoformat(), "auto_propose": True,
            "existing_skill": skill_name, "avg_q_score": avg_q, "failure_count": cnt})
    if cnt >= _B_EVT:
        _pub("SKILL_REFORGE_PROPOSAL", {"type": "optimize_existing", "skill_name": skill_name,
            "sample_failures": failures, "avg_q_score": avg_q, "failure_count": cnt})
        _save_req(ws, f"req_{_ts(now)}_optimize_{skill_name[:20]}", {"type": "optimize_existing",
            "skill_name": skill_name, "skill_path": f"~/.claude/skills/{skill_name}/SKILL.md",
            "problem_summary": f"{skill_name} Q avg {avg_q}", "sample_failures": failures,
            "avg_q_score": avg_q, "status": "pending_dse", "created_at": now.isoformat()})


# ─── Track C: 弱匹配 → 僅記錄 ───────────────────────────────────────────────

def _track_c(ws, query, matched_skills, confidence, q_score, user_id, now):
    log_path = ws / "_system" / "weak_match_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"query": query, "matched_skills": matched_skills,
                "confidence": confidence, "q_score": q_score, "user_id": user_id,
                "timestamp": now.isoformat()}, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("[gap_accumulator] Track C: %s", exc)


# ─── 工具函式 ─────────────────────────────────────────────────────────────────

def _ts(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M%S")


def _save_note(ws: Path, stem: str, note: dict) -> None:
    d = ws / "_system" / "morphenix" / "notes"
    d.mkdir(parents=True, exist_ok=True)
    try:
        (d / f"{stem}.json").write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[gap_accumulator] note: %s", stem)
    except Exception as exc:
        logger.debug("[gap_accumulator] note write: %s", exc)


def _save_req(ws: Path, stem: str, req: dict) -> None:
    d = ws / "_system" / "skill_requests"
    d.mkdir(parents=True, exist_ok=True)
    try:
        (d / f"{stem}.json").write_text(json.dumps(req, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[gap_accumulator] skill_request: %s", stem)
    except Exception as exc:
        logger.debug("[gap_accumulator] req write: %s", exc)


def _pub(event_type: str, data: dict) -> None:
    try:
        from museon.core.event_bus import EventBus
        EventBus.get_instance().publish(event_type, data)
        logger.info("[gap_accumulator] published %s", event_type)
    except Exception as exc:
        logger.debug("[gap_accumulator] publish %s: %s", event_type, exc)
