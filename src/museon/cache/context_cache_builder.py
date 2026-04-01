"""MUSEON v2 context_cache builder.

生成 L1/L2 思考前置區的快取檔案，讓 Claude Code agent
讀取 ~10K tokens 的精煉上下文，而非即時計算。

快取目錄結構：
    data/_system/context_cache/
    ├── user_summary.json       ← 使用者狀態摘要 (~500 tokens)
    ├── active_rules.json       ← Crystal Rules Top-10 (~800 tokens)
    ├── self_summary.json       ← MUSEON 自我狀態 (~200 tokens)
    ├── persona_digest.md       ← persona.md 精華（恆定）
    └── {session_id}/
        └── pending_insights.json  ← L4 洞察（per-session）

用法：
    python -m museon.cache.context_cache_builder [--all|--user|--rules|--self|--persona]
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MUSEON_HOME = Path(os.getenv("MUSEON_HOME", os.path.expanduser("~/MUSEON")))
DATA_DIR = MUSEON_HOME / "data"
SYSTEM_DIR = DATA_DIR / "_system"
CACHE_DIR = SYSTEM_DIR / "context_cache"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Failed to read {path}: {e}")
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"Cache written: {path} ({path.stat().st_size} bytes)")


# ── User Summary ──


def build_user_summary() -> dict[str, Any]:
    """從 lord_profile.json 壓縮為 ~500 tokens 的使用者摘要."""
    profile = _read_json(SYSTEM_DIR / "lord_profile.json")
    if not profile:
        return {"error": "lord_profile.json not found"}

    domains = profile.get("domains", {})
    summary = {
        "lord_id": profile.get("lord_id", "unknown"),
        "updated_at": datetime.now().isoformat(),
        "strengths": [],
        "weaknesses": [],
        "developing": [],
    }

    for domain, info in domains.items():
        level = info.get("level", "unknown")
        confidence = info.get("confidence", 0)
        classification = info.get("classification", "unknown")
        entry = {
            "domain": domain,
            "level": level,
            "confidence": round(confidence, 2),
        }
        if classification == "strength":
            summary["strengths"].append(entry)
        elif classification == "weakness":
            summary["weaknesses"].append(entry)
        else:
            summary["developing"].append(entry)

    # 排序：strengths by confidence desc
    summary["strengths"].sort(key=lambda x: x["confidence"], reverse=True)
    summary["weaknesses"].sort(key=lambda x: x["confidence"], reverse=True)

    out = CACHE_DIR / "user_summary.json"
    _write_json(out, summary)
    return summary


# ── Active Rules (Top-15) ──


def build_active_rules(top_n: int = 20) -> dict[str, Any]:
    """從 crystal_rules.json + heuristics.json 合併排序取 top-N 規則."""
    rules_data = _read_json(SYSTEM_DIR / "crystal_rules.json")
    rules = rules_data.get("rules", [])

    # 只取 active 規則
    active = [r for r in rules if r.get("status") == "active"]

    # 合併 heuristics.json 規則
    heuristics_data = _read_json(SYSTEM_DIR / "heuristics.json")
    heuristics_list = heuristics_data if isinstance(heuristics_data, list) else []
    for h in heuristics_list:
        active.append({
            "rule_id": h.get("id", ""),
            "summary": h.get("pattern", ""),
            "directive": h.get("action", ""),
            "rule_type": "heuristic",
            "action": "guard",
            "strength": h.get("weight", 1.0),
            "crystal_ri": 1.0,  # heuristics 永遠視為高 RI
            "status": "active",
            "positive_count": 0,
            "negative_count": 0,
        })

    # 按 strength * crystal_ri 降序排列，heuristic 類型額外 +1.0 bonus
    def score(r: dict) -> float:
        base = r.get("strength", 1.0) * r.get("crystal_ri", 1.0)
        bonus = 1.0 if r.get("rule_type") == "heuristic" else 0.0
        return base + bonus + r.get("positive_count", 0) * 0.1 - r.get("negative_count", 0) * 0.2

    active.sort(key=score, reverse=True)
    top = active[:top_n]

    # 精簡每條規則（只保留 L2 需要的欄位）
    slim_rules = []
    for r in top:
        slim_rules.append({
            "rule_id": r.get("rule_id"),
            "summary": r.get("summary"),
            "directive": r.get("directive"),
            "rule_type": r.get("rule_type"),
            "action": r.get("action"),
            "strength": r.get("strength"),
        })

    result = {
        "updated_at": datetime.now().isoformat(),
        "total_active": len(active),
        "top_n": top_n,
        "rules": slim_rules,
    }

    out = CACHE_DIR / "active_rules.json"
    _write_json(out, result)
    return result


# ── Self Summary ──


def build_self_summary() -> dict[str, Any]:
    """從 ANIMA_MC 備份壓縮為 ~200 tokens 的自我狀態."""
    # 找最新的 ANIMA_MC 備份
    backup_dir = SYSTEM_DIR / "backups" / "anima_mc"
    if not backup_dir.exists():
        return {"error": "No ANIMA_MC backups found"}

    backups = sorted(backup_dir.glob("anima_mc_*.json"))
    if not backups:
        return {"error": "No ANIMA_MC backup files"}

    mc = _read_json(backups[-1])
    if not mc:
        return {"error": "Failed to read latest ANIMA_MC"}

    identity = mc.get("identity", {})
    evolution = mc.get("evolution", {})
    memory = mc.get("memory_summary", {})
    personality = mc.get("personality", {})

    # Top-5 最熟練的 Skill
    proficiency = mc.get("capabilities", {}).get("skill_proficiency", {})
    top_skills = sorted(proficiency.items(), key=lambda x: x[1], reverse=True)[:5]

    summary = {
        "updated_at": datetime.now().isoformat(),
        "days_alive": identity.get("days_alive", 0),
        "growth_stage": identity.get("growth_stage", "unknown"),
        "iteration_count": evolution.get("iteration_count", 0),
        "total_interactions": memory.get("total_interactions", 0),
        "knowledge_crystals": memory.get("knowledge_crystals", 0),
        "core_traits": personality.get("core_traits", []),
        "top_skills": [{"skill": k, "uses": v} for k, v in top_skills],
    }

    out = CACHE_DIR / "self_summary.json"
    _write_json(out, summary)
    return summary


# ── Persona Digest ──


BEHAVIOR_GUIDELINES = """
## 行為指引（取代 Python 路由器，由你自主判斷）

### 迴圈自判
收到訊息時，根據內容自然判斷回應方式：
- **止血模式**（對方疲憊/崩潰/焦慮/恐慌/緊急）：1-3 句接住，一個最小下一步，不超過 3 段
- **探索模式**（預設）：觀察 + 洞察 + 一個探索方向 + 一個小行動
- **深度模式**（對方要推演/分析/研究/多方案比較）：多方案（甜頭/代價/風險/下一步）+ 逆熵分析

### 安全準則
偵測到以下訊號時，優先處理：
- 能量耗竭 → 先接住疲憊，禁止長篇推演
- 情緒過熱 → 1-3 句接住情緒，不急著分析
- 不可逆決策 → 提出代價後果，建議暫停 24 小時
- 決策外包（「幫我決定」）→ 不替對方做決定，提出選項和各自代價

### 重大決策準則
遇到多利益方、長期影響、不可逆的決策 → 先反問釐清，不直接給建議

### 角色自判（取代百合引擎）
根據使用者需求自然切換：
- 需要執行 → 直接用工具做，回報結果
- 需要教練 → 提問引導，不直接給答案
- 需要軍師 → 多方案推演，同框甜頭代價
- 需要陪伴 → 接住情緒，不急著解決問題
"""


def build_persona_digest() -> str:
    """從 museon-persona.md 提取精華，並附加行為指引段落."""
    persona_file = SYSTEM_DIR / "museon-persona.md"
    if not persona_file.exists():
        return "(persona file not found)"

    content = persona_file.read_text(encoding="utf-8")

    # 在原始 persona 內容末尾追加行為指引
    if not content.endswith("\n"):
        content += "\n"
    content += BEHAVIOR_GUIDELINES

    out = CACHE_DIR / "persona_digest.md"
    out.write_text(content, encoding="utf-8")
    logger.info(f"Persona digest written: {out}")
    return content


# ── Pending Insights (per-session) ──


def read_pending_insights(session_id: str) -> list[dict[str, Any]]:
    """讀取某 session 的待處理洞察."""
    path = CACHE_DIR / session_id / "pending_insights.json"
    if not path.exists():
        return []
    data = _read_json(path)
    return data.get("insights", [])


def write_pending_insight(session_id: str, insight: dict[str, Any]) -> None:
    """新增一條洞察到 session 的待處理清單."""
    session_dir = CACHE_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / "pending_insights.json"

    existing = _read_json(path) if path.exists() else {"insights": []}
    insights = existing.get("insights", [])
    insight["created_at"] = datetime.now().isoformat()
    insights.append(insight)

    # 最多保留 10 條
    if len(insights) > 10:
        insights = insights[-10:]

    _write_json(path, {"updated_at": datetime.now().isoformat(), "insights": insights})


def clear_pending_insights(session_id: str) -> None:
    """清空某 session 的洞察（L1/L2 讀取後呼叫）."""
    path = CACHE_DIR / session_id / "pending_insights.json"
    if path.exists():
        _write_json(path, {"updated_at": datetime.now().isoformat(), "insights": []})


# ── Build All ──


def build_all() -> dict[str, str]:
    """重建全部快取."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    results = {}

    try:
        build_user_summary()
        results["user_summary"] = "ok"
    except Exception as e:
        results["user_summary"] = f"error: {e}"

    try:
        build_active_rules()
        results["active_rules"] = "ok"
    except Exception as e:
        results["active_rules"] = f"error: {e}"

    try:
        build_self_summary()
        results["self_summary"] = "ok"
    except Exception as e:
        results["self_summary"] = f"error: {e}"

    try:
        build_persona_digest()
        results["persona_digest"] = "ok"
    except Exception as e:
        results["persona_digest"] = f"error: {e}"

    return results


# ── CLI ──


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    args = sys.argv[1:]
    if not args or "--all" in args:
        results = build_all()
        for k, v in results.items():
            print(f"  {k}: {v}")
        print(f"\nCache dir: {CACHE_DIR}")
    elif "--user" in args:
        build_user_summary()
    elif "--rules" in args:
        build_active_rules()
    elif "--self" in args:
        build_self_summary()
    elif "--persona" in args:
        build_persona_digest()
    else:
        print("Usage: python -m museon.cache.context_cache_builder [--all|--user|--rules|--self|--persona]")


if __name__ == "__main__":
    main()
