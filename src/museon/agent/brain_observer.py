"""
L4 觀察者 — 每次回覆後的即時學習引擎（Haiku）。

fire-and-forget，不阻塞主回覆。五個即時寫入管道：
1. memory_v3/L1_short — 短期對話記憶
2. morphenix/notes/ — MetaCog 洞察筆記（供 Nightly 蒸餾成結晶）
3. ANIMA_MC.json — 互動計數 + skill 熟練度（純 CPU）
4. pending_insights.json — L1 回饋迴路
5. signal_cache — 使用者狀態訊號（Haiku 偵測 + 衰減 + suggested_skills）

設計原則：
- 觀察邏輯交給 Haiku LLM（不寫 regex）
- 寫入邏輯是 Python（5 個管道，各 ~20 行）
- 失敗靜默（不影響使用者體驗）
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from museon.agent.signal_skill_map import get_suggested_skills, SIGNAL_DESCRIPTIONS

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))


async def observe(
    data_dir: Path,
    session_id: str,
    user_id: str,
    user_message: str,
    museon_reply: str,
    llm_adapter=None,
    skill_names: Optional[List[str]] = None,
) -> None:
    """L4 觀察主流程。靜默執行，任何錯誤不 raise。"""

    # ── 1. 短期記憶落地（純 CPU）──
    _write_short_memory(data_dir, session_id, user_id, user_message, museon_reply)

    # ── 2. Morphenix 筆記（供 Nightly 蒸餾）──
    # 用 Haiku 判斷是否有值得記錄的洞察
    insight_text = None
    if llm_adapter:
        insight_text = await _haiku_observe(llm_adapter, user_message, museon_reply)

    if insight_text:
        _write_morphenix_note(data_dir, "metacog_insight", insight_text)
        _write_pending_insight(data_dir, session_id, insight_text)

    # ── 3. ANIMA_MC 互動計數（純 CPU）──
    _update_anima_mc_counter(data_dir, skill_names or [])

    # ── 4. lord_profile 領域觀察（純 CPU，僅 boss）──
    if user_id in ("boss", "zeal", ""):
        _update_lord_profile(data_dir, user_message, skill_names or [])

    # ── 5. 訊號快取（Haiku 偵測 + 衰減 + suggested_skills）──
    await _update_signal_cache(
        data_dir, session_id, user_message, museon_reply, llm_adapter
    )


# ═══════════════════════════════════════
# Haiku 觀察（LLM 判斷）
# ═══════════════════════════════════════

async def _haiku_observe(
    llm_adapter,
    user_message: str,
    museon_reply: str,
) -> Optional[str]:
    """用 Haiku 判斷這輪對話是否有值得記錄的洞察。"""
    try:
        resp = await llm_adapter.call(
            system_prompt=(
                "你是 MUSEON 的觀察者。分析這輪對話，判斷是否有值得記錄的洞察。\n"
                "只在以下情況回覆一句話洞察摘要（50字內）：\n"
                "- 使用者提到新目標或計畫\n"
                "- 使用者表達情緒狀態變化\n"
                "- 使用者做了重要決策\n"
                "- 對話中出現可提煉的教訓或模式\n"
                "如果沒有特別值得記錄的，只回覆「無」。"
            ),
            messages=[{
                "role": "user",
                "content": f"使用者：{user_message[:300]}\nMUSEON：{museon_reply[:300]}",
            }],
            model="haiku",
            max_tokens=100,
        )
        text = (resp.text or "").strip()
        if text and text != "無" and len(text) > 2:
            return text
    except Exception as e:
        logger.debug(f"[L4] Haiku observe failed: {e}")
    return None


# ═══════════════════════════════════════
# 管道 1: 短期記憶
# ═══════════════════════════════════════

def _write_short_memory(
    data_dir: Path, session_id: str, user_id: str,
    user_message: str, museon_reply: str,
) -> None:
    """寫入 memory_v3 短期記憶。"""
    try:
        scope = "boss" if user_id in ("boss", "zeal", "") else user_id
        mem_dir = data_dir / "memory_v3" / scope / "L1_short"
        mem_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(TZ_TAIPEI)
        entry = {
            "session_id": session_id,
            "user_message": user_message[:500],
            "museon_reply": museon_reply[:500],
            "timestamp": ts.isoformat(),
        }
        fp = mem_dir / f"{ts.strftime('%Y%m%d_%H%M%S')}.json"
        fp.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.debug(f"[L4] short memory write failed: {e}")


# ═══════════════════════════════════════
# 管道 2: Morphenix 筆記
# ═══════════════════════════════════════

def _write_morphenix_note(data_dir: Path, category: str, content: str) -> None:
    """寫入 morphenix 即時筆記（供 Nightly Step 5.6.5 蒸餾）。"""
    try:
        notes_dir = data_dir / "_system" / "morphenix" / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(TZ_TAIPEI)
        note_id = f"mc_{now.strftime('%Y%m%d_%H%M%S')}_{category}"
        note = {
            "id": note_id,
            "category": category,
            "content": content,
            "source": "L4_observer",
            "created_at": now.isoformat(),
            "priority": "medium",
        }
        fp = notes_dir / f"{note_id}.json"
        fp.write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"[L4 Morphenix] 筆記寫入: {note_id}")
    except Exception as e:
        logger.debug(f"[L4] morphenix note failed: {e}")


# ═══════════════════════════════════════
# 管道 3: ANIMA_MC 計數器
# ═══════════════════════════════════════

def _update_anima_mc_counter(data_dir: Path, skill_names: List[str]) -> None:
    """更新 ANIMA_MC 的互動計數和 skill 熟練度（純 CPU）。"""
    try:
        mc_path = data_dir / "ANIMA_MC.json"
        if not mc_path.exists():
            return
        mc = json.loads(mc_path.read_text(encoding="utf-8"))

        # 互動計數
        mem = mc.setdefault("memory_summary", {})
        mem["total_interactions"] = mem.get("total_interactions", 0) + 1

        evo = mc.setdefault("evolution", {})
        evo["iteration_count"] = evo.get("iteration_count", 0) + 1

        # skill 熟練度
        if skill_names:
            caps = mc.setdefault("capabilities", {})
            loaded = set(caps.get("loaded_skills", []))
            prof = caps.get("skill_proficiency", {})
            for s in skill_names:
                loaded.add(s)
                prof[s] = prof.get(s, 0) + 1
            caps["loaded_skills"] = sorted(loaded)
            caps["skill_proficiency"] = prof

        # 原子寫入
        tmp = mc_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(mc, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.rename(mc_path)
    except Exception as e:
        logger.debug(f"[L4] ANIMA_MC update failed: {e}")


# ═══════════════════════════════════════
# 管道 4: pending_insights（L1 回饋）
# ═══════════════════════════════════════

def _write_pending_insight(data_dir: Path, session_id: str, content: str) -> None:
    """寫入 pending_insights 供 L1 下次讀取。"""
    try:
        fp = data_dir / "_system" / "context_cache" / "pending_insights.json"
        fp.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if fp.exists():
            try:
                existing = json.loads(fp.read_text(encoding="utf-8")).get("insights", [])
            except Exception:
                pass
        ts = datetime.now(TZ_TAIPEI).isoformat()
        existing.append({"type": "observation", "content": content, "created_at": ts, "session_id": session_id})
        if len(existing) > 50:
            existing = existing[-50:]
        fp.write_text(json.dumps({"updated_at": ts, "insights": existing}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.debug(f"[L4] pending insight failed: {e}")


# ═══════════════════════════════════════
# lord_profile 領域觀察
# ═══════════════════════════════════════

_LORD_DOMAIN_KEYWORDS = {
    "business_strategy": ["策略", "商模", "營收", "客戶", "market", "business"],
    "consultant_sales": ["顧問", "銷售", "成交", "客戶", "訪談", "SSA"],
    "ai_architecture": ["AI", "模型", "架構", "Skill", "MUSEON", "agent"],
    "brand_design": ["品牌", "設計", "美感", "視覺", "風格"],
    "emotional_regulation": ["情緒", "壓力", "焦慮", "累", "煩"],
}

_SKILL_DOMAIN_MAP = {
    "master-strategy": "business_strategy",
    "ssa-consultant": "consultant_sales",
    "brand-identity": "brand_design",
    "market-core": "business_strategy",
    "resonance": "emotional_regulation",
    "dharma": "emotional_regulation",
}


def _update_lord_profile(data_dir: Path, content: str, skill_names: List[str]) -> None:
    """更新 lord_profile.json 的領域 evidence_count。"""
    try:
        lord_path = data_dir / "_system" / "lord_profile.json"
        if not lord_path.exists():
            return
        profile = json.loads(lord_path.read_text(encoding="utf-8"))
        domains = profile.get("domains", {})

        matched = set()
        cl = content.lower()
        for domain, keywords in _LORD_DOMAIN_KEYWORDS.items():
            if any(kw.lower() in cl for kw in keywords):
                matched.add(domain)
        for sn in skill_names:
            mapped = _SKILL_DOMAIN_MAP.get(sn)
            if mapped:
                matched.add(mapped)

        if not matched:
            return

        for d in matched:
            if d in domains:
                domains[d]["evidence_count"] = domains[d].get("evidence_count", 0) + 1

        tmp = lord_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.rename(lord_path)
    except Exception as e:
        logger.debug(f"[L4] lord_profile update failed: {e}")


# ═══════════════════════════════════════
# 管道 5: Signal Cache（訊號偵測 + 衰減）
# ═══════════════════════════════════════

_SIGNAL_HAIKU_PROMPT = (
    "分析以下對話，偵測使用者的狀態訊號。\n\n"
    "使用者：{user_msg}\n"
    "回覆：{reply_msg}\n\n"
    "現有訊號：{existing}\n\n"
    "偵測以下訊號（0-1 分，0=不存在）：\n"
    "- decision_anxiety：決策焦慮\n"
    "- stuck_point：卡點\n"
    "- emotional_intensity：情緒強度\n"
    "- relationship_dynamic：人際動態\n"
    "- market_business：商業/市場\n"
    "- growth_seeking：成長渴望\n"
    "- planning_mode：規劃模式\n\n"
    '回覆 JSON：{{"signal_name": score}}（只列 > 0.3 的）\n'
    "加一行 trajectory：用戶思考軌跡（一句話）"
)


async def _haiku_signal_detect(
    llm_adapter,
    user_message: str,
    museon_reply: str,
    existing_summary: str,
) -> Dict[str, float]:
    """用 Haiku 偵測使用者狀態訊號，回傳 {signal: strength}。"""
    try:
        prompt = _SIGNAL_HAIKU_PROMPT.format(
            user_msg=user_message[:300],
            reply_msg=museon_reply[:200],
            existing=existing_summary or "無",
        )
        resp = await llm_adapter.call(
            system_prompt="你是訊號偵測器。只回覆 JSON，不要解釋。",
            messages=[{"role": "user", "content": prompt}],
            model="haiku",
            max_tokens=200,
        )
        text = (resp.text or "").strip()
        # 嘗試從回覆中提取 JSON（可能包含 trajectory 行）
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("{"):
                parsed = json.loads(line)
                # 過濾非訊號欄位和無效值
                return {
                    k: float(v)
                    for k, v in parsed.items()
                    if k in SIGNAL_DESCRIPTIONS and isinstance(v, (int, float)) and v > 0.3
                }
    except Exception as e:
        logger.debug(f"[L4] signal haiku detect failed: {e}")
    return {}


async def _update_signal_cache(
    data_dir: Path,
    session_id: str,
    user_message: str,
    museon_reply: str,
    llm_adapter=None,
) -> None:
    """管道 5: 更新 signal_cache（衰減 + Haiku 偵測 + suggested_skills）。"""
    try:
        cache_dir = data_dir / "_system" / "context_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{session_id}_signals.json"

        now = datetime.now(TZ_TAIPEI)

        # ── 1. 讀取現有 cache ──
        existing_signals: Dict[str, Any] = {}
        last_updated = None
        if cache_path.exists():
            try:
                raw = json.loads(cache_path.read_text(encoding="utf-8"))
                existing_signals = raw.get("signals", {})
                last_updated = raw.get("updated_at")
            except Exception:
                pass

        # ── 2. 衰減（elapsed_days * 0.1）──
        if last_updated and existing_signals:
            try:
                last_dt = datetime.fromisoformat(last_updated)
                elapsed_days = (now - last_dt).total_seconds() / 86400
                decayed = {}
                for sig_name, sig_info in existing_signals.items():
                    old_strength = sig_info.get("strength", 0) if isinstance(sig_info, dict) else float(sig_info)
                    new_strength = old_strength - elapsed_days * 0.1
                    if new_strength > 0.1:
                        if isinstance(sig_info, dict):
                            sig_info["strength"] = round(new_strength, 2)
                            decayed[sig_name] = sig_info
                        else:
                            decayed[sig_name] = {"strength": round(new_strength, 2)}
                existing_signals = decayed
            except Exception:
                pass

        # ── 3. Haiku 偵測新訊號 ──
        new_signals: Dict[str, float] = {}
        if llm_adapter:
            existing_summary = ", ".join(
                f"{k}={v.get('strength', v) if isinstance(v, dict) else v}"
                for k, v in existing_signals.items()
            )
            new_signals = await _haiku_signal_detect(
                llm_adapter, user_message, museon_reply, existing_summary
            )

        # ── 4. 合併（取較高 strength）──
        for sig_name, strength in new_signals.items():
            old = existing_signals.get(sig_name, {})
            old_strength = old.get("strength", 0) if isinstance(old, dict) else float(old) if old else 0
            merged_strength = max(old_strength, strength)
            existing_signals[sig_name] = {
                "strength": round(merged_strength, 2),
                "description": SIGNAL_DESCRIPTIONS.get(sig_name, ""),
                "last_detected": now.isoformat(),
            }

        # ── 5. 生成 suggested_skills ──
        suggested = get_suggested_skills(existing_signals)

        # ── 6. 原子寫入 ──
        cache_data = {
            "session_id": session_id,
            "updated_at": now.isoformat(),
            "signals": existing_signals,
            "suggested_skills": suggested,
        }
        fd, tmp_path = tempfile.mkstemp(
            dir=str(cache_dir), suffix=".json.tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(cache_path))
        except Exception:
            # 清理暫存檔
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        if existing_signals:
            logger.info(f"[L4 Signal] {session_id}: {list(existing_signals.keys())}")
    except Exception as e:
        logger.debug(f"[L4] signal cache update failed: {e}")
