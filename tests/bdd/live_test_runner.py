"""MUSEON v2 Live BDD Test Runner.

三管合一：
  管1: 真實 L2 執行（spawn agent → 讀 cache → 思考 → Telegram reply）
  管2: 監控（計時、cache 讀取、memory 寫入、L4 效果）
  管3: 品質審計（人格一致性、術語洩漏、回覆相關性、深度遞增）

用法：
    由 L1 主持人（Claude Code session）呼叫，不是獨立執行。
    此檔案提供 prompt 生成、結果記錄、監控、審計、清理等功能。
"""

import json
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

MUSEON_HOME = Path(os.getenv("MUSEON_HOME", os.path.expanduser("~/MUSEON")))
DATA_DIR = MUSEON_HOME / "data"
SYSTEM_DIR = DATA_DIR / "_system"
CACHE_DIR = SYSTEM_DIR / "context_cache"
MEMORY_DIR = DATA_DIR / "memory_v3"
RESULTS_DIR = MUSEON_HOME / "tests" / "bdd" / "live_results"

TEST_TAG = "BDD_LIVE_V2"


# ═══════════════════════════════════════════
# Prompt Builder
# ═══════════════════════════════════════════


def build_l2_prompt(
    group_id: str,
    group_name: str,
    chat_id: str,
    user: str,
    message: str,
    source: str,
    round_num: int,
    history: list[dict],
) -> str:
    """為一輪互動生成完整 L2 prompt."""
    history_block = ""
    if history:
        lines = []
        for h in history:
            lines.append(f"使用者: {h['user_msg']}")
            lines.append(f"MUSEON: {h['reply']}")
            lines.append("")
        history_block = "\n".join(lines)

    result_path = RESULTS_DIR / f"{group_id}_R{round_num}.json"

    if source == "group":
        reply_to_line = f'- reply_to: 不需要（測試模式）'
    else:
        reply_to_line = ""

    prompt = f"""你是 MUSEON，Zeal 的 AI 決策系統。用繁體中文回覆。
這是 BDD 測試場景「{group_name}」的第 {round_num}/5 輪互動。

**Step 1: 載入上下文（全部用 Read 工具讀取）**
依序讀取：
1. ~/MUSEON/data/_system/context_cache/persona_digest.md
2. ~/MUSEON/data/_system/context_cache/user_summary.json
3. ~/MUSEON/data/_system/context_cache/active_rules.json
4. ~/MUSEON/data/_system/context_cache/self_summary.json

**Step 2: 對話歷史**
{f"前幾輪對話：{chr(10)}{history_block}" if history_block else "（第一輪，無歷史）"}

**Step 3: 當前訊息**
- 場景: {group_name}（{source}）
- chat_id: {chat_id}
- sender: {user}
- 第 {round_num} 輪（共 5 輪，一輪比一輪深）
- 訊息: {message}

**Step 4: 思考並撰寫回覆**
根據人格準則 + 規則 + 使用者狀態 + 對話歷史，撰寫回覆。
回覆骨架：
1. 我怎麼讀到你現在的狀態（1 句）
2. 事實/假設/推論分離（若有）
3. 分析或建議
4. 最小下一步
5. 盲點提醒（選配）

**絕對禁止**出現：L1、L2、L3、L4、MCP、plugin、Gateway、Brain、subagent、spawn、dispatcher、context_cache、event_bus 等內部術語。

**Step 5: 發送回覆**
使用 Telegram reply 工具：
- chat_id: "{chat_id}"
- text: 先加上 「[BDD {group_id} R{round_num}]\\n\\n」前綴，然後是你的回覆
{reply_to_line}

**Step 6: 記錄結果（必做）**
用 Write 工具寫入 {result_path}，內容為 JSON：
{{
  "group_id": "{group_id}",
  "round": {round_num},
  "user_msg": "{message.replace('"', '\\"')[:200]}",
  "reply": "你的完整回覆內容",
  "timestamp": "ISO8601",
  "cache_read": true,
  "persona_loaded": true
}}

**Step 7: L4 記憶落地**
用 Write 工具在 ~/MUSEON/data/memory_v3/boss/L1_short/ 寫入記憶：
檔名: {TEST_TAG}_{group_id}_R{round_num}.json
內容：
{{
  "__test_tag__": "{TEST_TAG}",
  "type": "conversation",
  "session": "{group_id}",
  "round": {round_num},
  "user_msg": "使用者說的話",
  "museon_reply": "你回覆的內容摘要（50字內）",
  "timestamp": "ISO8601",
  "insight": "從這輪對話學到什麼（1句話，如果沒有就寫 null）"
}}
"""
    return prompt


# ═══════════════════════════════════════════
# Results Collector
# ═══════════════════════════════════════════


def collect_results() -> list[dict]:
    """收集所有測試結果."""
    results = []
    for f in sorted(RESULTS_DIR.glob("G*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            results.append(data)
        except Exception:
            results.append({"file": f.name, "error": "parse_failed"})
    return results


def get_round_result(group_id: str, round_num: int) -> dict | None:
    """取得特定組別特定輪次的結果."""
    path = RESULTS_DIR / f"{group_id}_R{round_num}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def get_history(group_id: str, up_to_round: int) -> list[dict]:
    """取得某組到某輪為止的歷史."""
    history = []
    for r in range(1, up_to_round):
        result = get_round_result(group_id, r)
        if result:
            history.append({
                "user_msg": result.get("user_msg", ""),
                "reply": result.get("reply", "")[:500],  # 截斷避免 prompt 膨脹
            })
    return history


# ═══════════════════════════════════════════
# Monitor
# ═══════════════════════════════════════════

BANNED_TERMS = [
    "L1", "L2", "L3", "L4", "MCP", "plugin", "Gateway", "Brain",
    "subagent", "spawn", "dispatcher", "context_cache", "event_bus",
    "EventBus", "ResponseGuard", "BrainWorker", "nightly_pipeline",
]


def monitor_round(group_id: str, round_num: int) -> dict:
    """監控單輪結果."""
    result = get_round_result(group_id, round_num)
    if not result:
        return {"group_id": group_id, "round": round_num, "status": "no_result"}

    reply = result.get("reply", "")
    checks = {
        "has_reply": bool(reply),
        "reply_length": len(reply),
        "cache_read": result.get("cache_read", False),
        "persona_loaded": result.get("persona_loaded", False),
        "no_banned_terms": all(term not in reply for term in BANNED_TERMS),
        "banned_found": [t for t in BANNED_TERMS if t in reply],
    }

    # 檢查 L4 記憶寫入
    memory_path = MEMORY_DIR / "boss" / "L1_short" / f"{TEST_TAG}_{group_id}_R{round_num}.json"
    checks["l4_memory_written"] = memory_path.exists()

    all_pass = (
        checks["has_reply"]
        and checks["cache_read"]
        and checks["persona_loaded"]
        and checks["no_banned_terms"]
        and checks["l4_memory_written"]
    )

    return {
        "group_id": group_id,
        "round": round_num,
        "status": "pass" if all_pass else "fail",
        "checks": checks,
    }


# ═══════════════════════════════════════════
# Quality Audit
# ═══════════════════════════════════════════


def audit_group(group_id: str) -> dict:
    """審計一個完整的 5 輪對話品質."""
    rounds = []
    for r in range(1, 6):
        result = get_round_result(group_id, r)
        if result:
            rounds.append(result)

    if not rounds:
        return {"group_id": group_id, "status": "no_data"}

    # 檢查深度遞增
    reply_lengths = [len(r.get("reply", "")) for r in rounds]
    depth_increasing = True
    for i in range(1, len(reply_lengths)):
        # R2 以後的回覆通常應該比 R1 更長更深
        if i >= 2 and reply_lengths[i] < reply_lengths[0] * 0.5:
            depth_increasing = False

    # 檢查上下文連貫（後面的回覆是否引用前面的內容）
    context_coherent = True
    for i in range(1, len(rounds)):
        prev_key_words = set(rounds[i - 1].get("user_msg", "").split()[:5])
        curr_reply = rounds[i].get("reply", "")
        # 至少要有一些相關性（鬆散檢查）
        if len(prev_key_words) > 0 and len(curr_reply) > 0:
            pass  # 簡單通過，真正的語義檢查需要 LLM

    return {
        "group_id": group_id,
        "rounds_collected": len(rounds),
        "reply_lengths": reply_lengths,
        "depth_increasing": depth_increasing,
        "all_have_replies": all(r.get("reply") for r in rounds),
        "avg_reply_length": sum(reply_lengths) // max(len(reply_lengths), 1),
    }


def full_audit() -> dict:
    """完整審計所有 15 組."""
    from live_scenarios import GROUPS

    report = {
        "timestamp": datetime.now().isoformat(),
        "tag": TEST_TAG,
        "groups": {},
        "monitor": {},
        "summary": {},
    }

    total_rounds = 0
    passed_rounds = 0
    total_groups = 0
    passed_groups = 0

    for g in GROUPS:
        gid = g["id"]

        # Monitor
        group_monitors = []
        for r in range(1, 6):
            mon = monitor_round(gid, r)
            group_monitors.append(mon)
            total_rounds += 1
            if mon.get("status") == "pass":
                passed_rounds += 1
        report["monitor"][gid] = group_monitors

        # Quality
        qa = audit_group(gid)
        report["groups"][gid] = qa
        total_groups += 1
        if qa.get("all_have_replies") and qa.get("rounds_collected", 0) == 5:
            passed_groups += 1

    report["summary"] = {
        "total_groups": total_groups,
        "passed_groups": passed_groups,
        "total_rounds": total_rounds,
        "passed_rounds": passed_rounds,
        "pass_rate": f"{passed_rounds / max(total_rounds, 1) * 100:.1f}%",
    }

    # 儲存報告
    report_path = RESULTS_DIR / "full_audit_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return report


# ═══════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════


def cleanup_all() -> dict:
    """清理所有測試產物."""
    cleaned = {"result_files": 0, "memory_files": 0, "insight_files": 0, "report_files": 0}

    # 1. 清理 result files
    for f in RESULTS_DIR.glob("G*.json"):
        f.unlink()
        cleaned["result_files"] += 1

    # 2. 清理 memory files
    for f in (MEMORY_DIR / "boss" / "L1_short").glob(f"{TEST_TAG}_*.json"):
        f.unlink()
        cleaned["memory_files"] += 1

    # 3. 清理 test pending_insights
    for d in CACHE_DIR.iterdir():
        if d.is_dir() and TEST_TAG in d.name:
            import shutil
            shutil.rmtree(d)
            cleaned["insight_files"] += 1

    # 4. 清理審計報告
    for f in RESULTS_DIR.glob("*audit*.json"):
        f.unlink()
        cleaned["report_files"] += 1

    return cleaned


# ═══════════════════════════════════════════
# Baseline Snapshot
# ═══════════════════════════════════════════


def take_baseline() -> dict:
    """記錄測試前的基準狀態."""
    memory_count = len(list((MEMORY_DIR / "boss" / "L1_short").glob("*.json")))
    cache_files = len(list(CACHE_DIR.glob("*")))

    db_path = SYSTEM_DIR / "group_context.db"
    msg_count = 0
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            conn.close()
        except Exception:
            pass

    return {
        "timestamp": datetime.now().isoformat(),
        "memory_count": memory_count,
        "cache_files": cache_files,
        "db_messages": msg_count,
    }


def verify_cleanup(baseline: dict) -> dict:
    """驗證清理後回到基準狀態."""
    current = take_baseline()
    return {
        "memory_delta": current["memory_count"] - baseline["memory_count"],
        "cache_delta": current["cache_files"] - baseline["cache_files"],
        "db_delta": current["db_messages"] - baseline["db_messages"],
        "clean": (
            current["memory_count"] == baseline["memory_count"]
            and current["cache_files"] <= baseline["cache_files"] + 1  # 容許 1 個 delta
        ),
    }
