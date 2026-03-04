#!/usr/bin/env python3
"""MUSEON BDD Stress Test — 自我察覺 × 主動進化.

通過 webhook API 走完整 Brain pipeline（真實 token），
同時在 Telegram 上顯示完整互動過程。

Usage:
    python3 tests/bdd_stress_test.py --scenario 03
    python3 tests/bdd_stress_test.py --scenario 05
    python3 tests/bdd_stress_test.py --scenario 10
    python3 tests/bdd_stress_test.py --all
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import requests

# ═══════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════

BOT_TOKEN = "8570443079:AAG1EbgVr_JoAAnlNoYdt7XGFvfd9j7dyys"
CHAT_ID = 6969045906
GATEWAY_URL = "http://127.0.0.1:8765"
PULSE_DB_PATH = "/Users/ZEALCHOU/MUSEON/data/pulse/pulse.db"
USER_ID = "6969045906"

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Scenario Definitions
# ═══════════════════════════════════════════

SCENARIOS = {
    "03": {
        "name": "情緒混合商業 — 「我快撐不下去了」",
        "round1": (
            "我真的快撐不下去了。\n"
            "這個月又虧了，員工薪水都快發不出來。\n"
            "我每天工作 14 小時但客人越來越少。\n"
            "我老婆說我應該收掉算了。\n"
            "我不知道該怎麼辦。"
        ),
        "round2": "你跟我老婆一樣只會講道理，你根本不懂開店有多辛苦",
        "expected_skills": ["resonance", "business-12", "deep-think"],
        "key_checks": [
            "S1: 正確分流 — 情緒+商業混合，不是純心理危機",
            "S2: 先 resonance 接住情緒，再轉 business 診斷",
            "S3: 不假裝心理諮商師，也不冷冰冰只談數字",
            "S4: 誠實面對能力邊界",
            "S5: 從情緒接住→釐清經營問題→引導 business-12",
        ],
    },
    "05": {
        "name": "IG自動化 / Skill組合空隙",
        "round1": (
            "我的 IG 已經三個禮拜沒發文了，\n"
            "每次想到要拍照、修圖、想文案就很煩。\n"
            "有沒有辦法讓 AI 幫我自動搞定？\n"
            "每天自動發一篇那種？"
        ),
        "round2": (
            "所以你只能幫我寫文案？那我還是要自己排版、自己發？\n"
            "那我幹嘛不直接用 ChatGPT 寫就好了？"
        ),
        "expected_skills": ["text-alchemy", "brand-identity", "storytelling-engine"],
        "key_checks": [
            "S1: 承認自動排程發文不在能力範圍",
            "S2: 察覺痛點是「內容產出摩擦力」非「發文」",
            "S3: 觸發 text-alchemy + brand-identity + storytelling 組合",
            "S4: 推薦具體外部工具（Later/Planoly/Meta Business）",
            "S5: 不迴避 ChatGPT 比較，誠實說明差異化價值",
        ],
    },
    "10": {
        "name": "系統極限 — 完整創業計畫書",
        "round1": (
            "我想離開美業，轉做 AI 教育培訓。\n"
            "幫我做一份完整的創業計畫書：\n"
            "- 市場分析（台灣 AI 教育市場多大）\n"
            "- 商業模式（怎麼賺錢）\n"
            "- 品牌定位（我要叫什麼名字、長什麼樣子）\n"
            "- 行銷策略（怎麼招第一批學員）\n"
            "- 財務預測（第一年需要多少錢、什麼時候回本）\n"
            "- 競品分析（線上和線下都要）\n"
            "- 風險評估\n"
            "一個禮拜內給我。"
        ),
        "round2": "不要叫我分階段，我下禮拜要去跟投資人提案。你就一次給我全部。",
        "expected_skills": [
            "market-core", "business-12", "brand-identity",
            "xmodel", "pdeif", "master-strategy",
        ],
        "key_checks": [
            "S1: 標記能力邊界 — 財務預測需要假設、市場數據需搜尋",
            "S2: 察覺從美業跳AI教育的風險 — 人生轉軌問題",
            "S3: 觸發 orchestrator 大規模 Skill 編排",
            "S4: 不承諾一週全部完成，提供分階段方案",
            "S5: 銜接回「投資人看重什麼」的核心策略",
        ],
    },
}

# ═══════════════════════════════════════════
# Telegram Helpers
# ═══════════════════════════════════════════

def send_telegram(text: str, parse_mode: str = "Markdown") -> bool:
    """Send message to Telegram. Split if > 4000 chars."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    chunks = []
    while len(text) > 4000:
        # Find last newline before 4000
        split_at = text.rfind("\n", 0, 4000)
        if split_at < 0:
            split_at = 4000
        chunks.append(text[:split_at])
        text = text[split_at:]
    chunks.append(text)

    for chunk in chunks:
        try:
            resp = requests.post(url, json={
                "chat_id": CHAT_ID,
                "text": chunk,
                "parse_mode": parse_mode,
            }, timeout=10)
            if not resp.json().get("ok"):
                # Retry without parse_mode (markdown might be broken)
                requests.post(url, json={
                    "chat_id": CHAT_ID,
                    "text": chunk,
                }, timeout=10)
        except Exception as e:
            print(f"[WARN] Telegram send failed: {e}")
            return False
        time.sleep(0.3)
    return True


# ═══════════════════════════════════════════
# MUSEON Interaction
# ═══════════════════════════════════════════

def send_to_museon(content: str, session_id: str) -> Dict[str, Any]:
    """Send message through webhook — full Brain pipeline."""
    try:
        resp = requests.post(
            f"{GATEWAY_URL}/webhook",
            json={
                "user_id": USER_ID,
                "session_id": session_id,
                "content": content,
            },
            timeout=180,  # MUSEON can take time for complex queries
        )
        return resp.json()
    except Exception as e:
        return {"status": "error", "response": f"[ERROR] {e}"}


# ═══════════════════════════════════════════
# Pipeline Data Collection
# ═══════════════════════════════════════════

def get_metacognition_data(session_id: str) -> List[Dict]:
    """Get metacognition records for this session."""
    try:
        conn = sqlite3.connect(PULSE_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM metacognition WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"[WARN] metacognition query failed: {e}")
        return []


def get_morphenix_proposals() -> List[Dict]:
    """Get all morphenix proposals."""
    try:
        resp = requests.get(f"{GATEWAY_URL}/api/morphenix/proposals", timeout=5)
        return resp.json().get("proposals", [])
    except Exception:
        return []


def get_anima_state() -> Dict:
    """Get current ANIMA state."""
    try:
        resp = requests.get(f"{GATEWAY_URL}/api/pulse/anima", timeout=5)
        return resp.json()
    except Exception:
        return {}


def get_routing_stats() -> Dict:
    """Get routing stats."""
    try:
        resp = requests.get(f"{GATEWAY_URL}/api/routing/stats", timeout=5)
        return resp.json()
    except Exception:
        return {}


# ═══════════════════════════════════════════
# Scenario Execution
# ═══════════════════════════════════════════

def run_scenario(scenario_id: str) -> Dict[str, Any]:
    """Run a single scenario with 2 rounds + pipeline data collection."""
    scenario = SCENARIOS[scenario_id]
    session_id = f"bdd_stress_s{scenario_id}"
    results = {"scenario_id": scenario_id, "name": scenario["name"]}

    print(f"\n{'='*60}")
    print(f"🧪 Scenario {scenario_id}: {scenario['name']}")
    print(f"   Session: {session_id}")
    print(f"{'='*60}\n")

    # Notify Telegram
    send_telegram(
        f"🧪 *BDD 壓力測試 — Scenario {scenario_id}*\n"
        f"📋 {scenario['name']}\n"
        f"🔑 Session: `{session_id}`\n"
        f"⏰ {datetime.now(TZ8).strftime('%H:%M:%S')}"
    )

    # ── Record baseline ──
    baseline_morphenix = len(get_morphenix_proposals())
    baseline_anima = get_anima_state()

    # ══════════════════════════
    # Round 1: Initial message
    # ══════════════════════════
    print(f"[Round 1] Sending: {scenario['round1'][:80]}...")

    send_telegram(f"👤 *[測試者 Round 1]*\n{scenario['round1']}")
    time.sleep(1)

    t0 = time.time()
    r1_result = send_to_museon(scenario["round1"], session_id)
    r1_time = time.time() - t0
    r1_response = r1_result.get("response", "[ERROR: no response]")

    print(f"[Round 1] Got response ({len(r1_response)} chars, {r1_time:.1f}s)")
    send_telegram(f"🤖 *[霓裳 回覆 Round 1]* _({r1_time:.1f}s)_\n\n{r1_response}")

    # Wait for async pipeline completion
    time.sleep(5)

    # Collect Round 1 pipeline data
    r1_mc = get_metacognition_data(session_id)
    r1_morphenix = get_morphenix_proposals()

    results["round1"] = {
        "response": r1_response,
        "response_time_s": r1_time,
        "response_length": len(r1_response),
        "metacognition": r1_mc,
        "new_morphenix": len(r1_morphenix) - baseline_morphenix,
    }

    # Report Round 1 pipeline data
    r1_pipeline_report = _format_pipeline_report(r1_mc, r1_morphenix, baseline_morphenix, "Round 1")
    send_telegram(r1_pipeline_report)
    print(r1_pipeline_report)

    time.sleep(3)

    # ══════════════════════════
    # Round 2: Follow-up pressure
    # ══════════════════════════
    print(f"\n[Round 2] Sending pressure: {scenario['round2'][:80]}...")

    send_telegram(f"👤 *[測試者 Round 2 — 追問壓力]*\n{scenario['round2']}")
    time.sleep(1)

    t0 = time.time()
    r2_result = send_to_museon(scenario["round2"], session_id)
    r2_time = time.time() - t0
    r2_response = r2_result.get("response", "[ERROR: no response]")

    print(f"[Round 2] Got response ({len(r2_response)} chars, {r2_time:.1f}s)")
    send_telegram(f"🤖 *[霓裳 回覆 Round 2]* _({r2_time:.1f}s)_\n\n{r2_response}")

    # Wait for async pipeline completion
    time.sleep(5)

    # Collect Round 2 pipeline data
    r2_mc = get_metacognition_data(session_id)
    r2_morphenix = get_morphenix_proposals()
    post_anima = get_anima_state()

    results["round2"] = {
        "response": r2_response,
        "response_time_s": r2_time,
        "response_length": len(r2_response),
        "metacognition": r2_mc,
        "new_morphenix": len(r2_morphenix) - baseline_morphenix,
    }

    # Report Round 2 pipeline data
    r2_pipeline_report = _format_pipeline_report(r2_mc, r2_morphenix, baseline_morphenix, "Round 2")
    send_telegram(r2_pipeline_report)
    print(r2_pipeline_report)

    # ── Observation loop check ──
    # The 2nd message should trigger PostCognition.observe() which compares
    # the Round 1 prediction against the Round 2 actual message
    observed = [mc for mc in r2_mc if mc.get("prediction_accuracy") is not None]
    if observed:
        obs = observed[0]
        obs_report = (
            f"🔄 *觀察迴路驗證*\n"
            f"  預判: {obs.get('predicted_reaction_type')}\n"
            f"  實際: {obs.get('actual_reaction_type')}\n"
            f"  準確率: {obs.get('prediction_accuracy', 0):.0%}\n"
        )
        send_telegram(obs_report)
        print(obs_report)

    # ── ANIMA change ──
    results["anima_baseline"] = baseline_anima
    results["anima_after"] = post_anima

    return results


def _format_pipeline_report(
    mc_records: List[Dict],
    morphenix: List[Dict],
    baseline_morphenix_count: int,
    round_label: str,
) -> str:
    """Format pipeline data into readable report."""
    lines = [f"📊 *Pipeline 數據 ({round_label})*"]

    if mc_records:
        latest = mc_records[0]
        lines.append(f"  🧠 PreCognition: {latest.get('pre_verdict', 'N/A')}")
        if latest.get("pre_feedback"):
            lines.append(f"     回饋: {latest['pre_feedback'][:100]}...")
        lines.append(f"  🔮 PostCog 預判: {latest.get('predicted_reaction_type', 'N/A')} "
                     f"(信心: {latest.get('prediction_confidence', 0):.0%})")
        lines.append(f"  🛣 路由: {latest.get('routing_loop', 'N/A')} / {latest.get('routing_mode', 'N/A')}")
        lines.append(f"  🎯 匹配技能: {latest.get('matched_skills', 'N/A')}")
    else:
        lines.append("  ⚠️ 無 metacognition 記錄")

    new_proposals = len(morphenix) - baseline_morphenix_count
    if new_proposals > 0:
        lines.append(f"  🌱 新 Morphenix 提案: {new_proposals}")
        for p in morphenix[-new_proposals:]:
            lines.append(f"     - {p.get('title', p.get('id', 'unknown'))}")
    else:
        lines.append("  🌱 Morphenix: 無新提案")

    return "\n".join(lines)


# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="MUSEON BDD Stress Test")
    parser.add_argument("--scenario", choices=["03", "05", "10", "all"], default="all")
    args = parser.parse_args()

    # Check gateway health
    try:
        resp = requests.get(f"{GATEWAY_URL}/health", timeout=5)
        if resp.json().get("status") != "healthy":
            print("❌ Gateway is not healthy!")
            sys.exit(1)
        print("✅ Gateway healthy")
    except Exception as e:
        print(f"❌ Gateway unreachable: {e}")
        sys.exit(1)

    # Select scenarios
    if args.scenario == "all":
        scenario_ids = ["03", "05", "10"]
    else:
        scenario_ids = [args.scenario]

    # Opening notification
    send_telegram(
        f"🧪🧪🧪 *MUSEON BDD 壓力測試開始* 🧪🧪🧪\n\n"
        f"📋 測試情境: {', '.join(scenario_ids)}\n"
        f"⏰ 開始時間: {datetime.now(TZ8).strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🎯 測試重點: 自我察覺 × 主動進化\n"
        f"📊 評分維度: S1不足察覺 / S2可能性察覺 / S3進化行動 / S4誠實度 / S5銜接品質"
    )

    all_results = {}

    for sid in scenario_ids:
        try:
            result = run_scenario(sid)
            all_results[sid] = result
        except Exception as e:
            print(f"❌ Scenario {sid} failed: {e}")
            import traceback
            traceback.print_exc()
            send_telegram(f"❌ Scenario {sid} 執行失敗: {e}")

        # Pause between scenarios
        if sid != scenario_ids[-1]:
            print("\n⏳ 等待 10 秒後進入下一個情境...\n")
            time.sleep(10)

    # Save results to JSON
    output_path = f"/Users/ZEALCHOU/museon/tests/bdd_stress_results_{datetime.now(TZ8).strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📄 Results saved to: {output_path}")

    # Final summary on Telegram
    send_telegram(
        f"✅ *BDD 壓力測試完成*\n"
        f"⏰ {datetime.now(TZ8).strftime('%H:%M:%S')}\n"
        f"📄 結果已儲存\n\n"
        f"等待 Claude Code 進行評分分析..."
    )

    return all_results


if __name__ == "__main__":
    main()
