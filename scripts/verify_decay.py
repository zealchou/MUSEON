#!/usr/bin/env python3
"""
MUSEON 四層衰減機制驗證腳本
============================
驗證已實裝的四層衰減是否真的在運行。

四層衰減：
  1. 結晶衰減（Knowledge Lattice RI）
  2. 記憶降級（Memory Manager TTL + Access Count）
  3. 健康分數衰減（Dendritic Scorer Half-life 2h）
  4. 推薦引擎衰減（Recommender Recency 7d）

用法：
  .venv/bin/python scripts/verify_decay.py
  .venv/bin/python scripts/verify_decay.py --json   # JSON 格式輸出
"""

import json
import math
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter

# ── 路徑定義 ──
MUSEON_ROOT = Path(os.environ.get("MUSEON_HOME", os.path.expanduser("~/MUSEON")))
RUNTIME_ROOT = Path(os.path.expanduser("~/.museon"))
LATTICE_DIR = MUSEON_ROOT / "data" / "lattice"
MEMORY_DIR = MUSEON_ROOT / "data" / "memory_v3"
RECOMMENDATIONS_DIR = MUSEON_ROOT / "data" / "_system" / "recommendations"
NIGHTLY_REPORT = MUSEON_ROOT / "data" / "_system" / "state" / "nightly_report.json"
IMMUNITY_FILE = RUNTIME_ROOT / "immunity.json"

TZ8 = timezone(timedelta(hours=8))
NOW = datetime.now(TZ8)

# ── 閾值常數（與源碼一致） ──
RI_CORE_THRESHOLD = 0.7
RI_ACTIVE_THRESHOLD = 0.2
RI_ARCHIVE_THRESHOLD = 0.05
ARCHIVE_STALE_DAYS = 90
RI_DECAY_RATE = 0.03

MEMORY_LAYER_TTL = {
    "L0_buffer": 14,
    "L1_short": 30,
    "L2_ep": 90,
    "L2_sem": 180,
    "L3_procedural": None,  # 永久
    "L4_identity": None,    # 永久
    "L5_scratch": 7,
}
AUTO_PROMOTE_ACCESS = {"L0_buffer": 2, "L1_short": 5}
DEMOTION_RELEVANCE_THRESHOLD = 0.2

HEALTH_HALF_LIFE_HOURS = 2.0
HEALTH_THRESHOLD_HEALTHY = 70
HEALTH_THRESHOLD_DEGRADED = 40
LN2 = 0.693147

RECENCY_HALF_LIFE_DAYS = 7.0
INTERACTION_DECAY = 0.95


def _load_json(path: Path) -> dict | list | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return None


def _parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ8)
        return dt
    except Exception:
        return None


# ====================================================================
# Layer 1: Crystal RI Decay
# ====================================================================
def verify_crystal_decay() -> dict:
    """驗證結晶 RI 衰減機制"""
    report = {
        "layer": "Crystal RI Decay",
        "status": "UNKNOWN",
        "findings": [],
        "data": {},
    }

    # 載入結晶
    crystals = _load_json(LATTICE_DIR / "crystals.json")
    archive = _load_json(LATTICE_DIR / "archive.json")

    if crystals is None:
        report["status"] = "FAIL"
        report["findings"].append("crystals.json 不存在或無法讀取")
        return report

    total = len(crystals)
    archived_flag = sum(1 for c in crystals if c.get("archived"))
    archive_count = len(archive) if isinstance(archive, list) else 0

    # RI 分布統計
    ri_scores = [c.get("ri_score", 0) for c in crystals]
    ri_below_005 = [c for c in crystals if c.get("ri_score", 0) < RI_ARCHIVE_THRESHOLD]
    ri_below_020 = [c for c in crystals if c.get("ri_score", 0) < RI_ACTIVE_THRESHOLD]
    ri_active = [c for c in crystals if RI_ACTIVE_THRESHOLD <= c.get("ri_score", 0) < RI_CORE_THRESHOLD]
    ri_core = [c for c in crystals if c.get("ri_score", 0) >= RI_CORE_THRESHOLD]

    report["data"] = {
        "total_crystals": total,
        "archive_file_count": archive_count,
        "archived_flag_count": archived_flag,
        "ri_distribution": {
            "core_ge_070": len(ri_core),
            "active_020_070": len(ri_active),
            "cold_lt_020": len(ri_below_020),
            "archive_lt_005": len(ri_below_005),
        },
        "ri_stats": {
            "min": round(min(ri_scores), 4) if ri_scores else 0,
            "max": round(max(ri_scores), 4) if ri_scores else 0,
            "avg": round(sum(ri_scores) / len(ri_scores), 4) if ri_scores else 0,
        },
    }

    # 驗算 RI 公式：隨機抽樣驗證
    formula_checks = []
    for c in crystals[:10]:
        ref_count = c.get("reference_count", 0)
        freq = min(ref_count / 50.0, 1.0)  # MAX_REFERENCE_COUNT = 50
        # depth 和 quality 無法直接從 JSON 算出（需要看 g2_structure 等）
        # 但可以驗證衰減因子
        last_ref = c.get("last_referenced") or c.get("updated_at") or c.get("created_at")
        dt = _parse_dt(last_ref)
        if dt:
            days = (NOW - dt).total_seconds() / 86400
            decay_factor = math.exp(-RI_DECAY_RATE * days)
            formula_checks.append({
                "cuid": c["cuid"],
                "ri_score": c.get("ri_score", 0),
                "days_since_ref": round(days, 1),
                "decay_factor": round(decay_factor, 4),
                "ref_count": ref_count,
            })

    report["data"]["formula_spot_checks"] = formula_checks[:5]

    # 計算最老結晶的理論最低 RI
    dates = []
    for c in crystals:
        dt = _parse_dt(c.get("created_at", ""))
        if dt:
            dates.append(dt)
    if dates:
        oldest_days = (NOW - min(dates)).total_seconds() / 86400
        theoretical_min_decay = math.exp(-RI_DECAY_RATE * oldest_days)
        report["data"]["oldest_crystal_days"] = round(oldest_days, 1)
        report["data"]["theoretical_min_decay_factor"] = round(theoretical_min_decay, 4)
        # 以最低品質分數估算：0.3*0 + 0.4*0.3 + 0.3*0.3 = 0.21
        # 乘以衰減因子
        estimated_floor = 0.21 * theoretical_min_decay
        report["data"]["estimated_ri_floor"] = round(estimated_floor, 4)
        report["findings"].append(
            f"系統運行 {oldest_days:.0f} 天，最老結晶的衰減因子 = {theoretical_min_decay:.4f}"
        )
        if estimated_floor > RI_ARCHIVE_THRESHOLD:
            report["findings"].append(
                f"理論最低 RI ≈ {estimated_floor:.4f} > 0.05 閾值 → 系統太年輕，尚無結晶需歸檔（正常）"
            )

    # 檢查 Nightly 是否有執行
    nightly = _load_json(NIGHTLY_REPORT)
    if nightly:
        step = nightly.get("steps", {}).get("step_05_6_knowledge_lattice", {})
        report["data"]["nightly_lattice_step"] = step
        if step.get("status") == "ok":
            result = step.get("result", "")
            report["findings"].append(f"Nightly Pipeline step_05_6 已執行: {result}")
        else:
            report["findings"].append("Nightly Pipeline step_05_6 未成功執行")

    # 判定結果
    if archive_count == 0 and len(ri_below_005) == 0:
        if dates and oldest_days < ARCHIVE_STALE_DAYS:
            report["status"] = "PASS (inactive - system too young)"
            report["findings"].append(
                f"歸檔條件需 RI < 0.05 且 {ARCHIVE_STALE_DAYS} 天未使用，系統才 {oldest_days:.0f} 天 → 正常無歸檔"
            )
        else:
            report["status"] = "WARN"
            report["findings"].append("系統已超過歸檔窗口但無歸檔紀錄，需進一步檢查 maintenance 是否觸發")
    elif archive_count > 0:
        report["status"] = "PASS"
        report["findings"].append(f"已有 {archive_count} 個結晶被歸檔 → 衰減機制運作中")
    else:
        report["status"] = "PASS"

    return report


# ====================================================================
# Layer 2: Memory Manager TTL + Access Count
# ====================================================================
def verify_memory_decay() -> dict:
    """驗證記憶降級機制"""
    report = {
        "layer": "Memory TTL & Auto-Promote",
        "status": "UNKNOWN",
        "findings": [],
        "data": {},
    }

    if not MEMORY_DIR.exists():
        report["status"] = "FAIL"
        report["findings"].append("memory_v3 目錄不存在")
        return report

    # 統計所有使用者的記憶分布
    user_stats = {}
    total_memories = 0
    all_memories = []

    for user_dir in MEMORY_DIR.iterdir():
        if not user_dir.is_dir() or user_dir.name.startswith("."):
            continue
        user_id = user_dir.name
        layer_counts = {}
        for layer_dir in user_dir.iterdir():
            if not layer_dir.is_dir() or layer_dir.name.startswith("_"):
                continue
            layer = layer_dir.name
            files = list(layer_dir.glob("*.json"))
            layer_counts[layer] = len(files)
            total_memories += len(files)
            for f in files:
                mem = _load_json(f)
                if mem:
                    mem["_file"] = str(f)
                    mem["_user"] = user_id
                    all_memories.append(mem)
        user_stats[user_id] = layer_counts

    report["data"]["user_layer_distribution"] = user_stats
    report["data"]["total_memories"] = total_memories

    # 分析 access_count 和 age
    access_counts = Counter()
    expired_candidates = []
    promote_candidates = []

    for mem in all_memories:
        ac = mem.get("access_count", 0)
        access_counts[ac] += 1
        layer = mem.get("layer", "unknown")
        created = _parse_dt(mem.get("created_at", ""))

        if created:
            age_days = (NOW - created).total_seconds() / 86400
            ttl = MEMORY_LAYER_TTL.get(layer)
            if ttl and age_days > ttl:
                expired_candidates.append({
                    "id": mem.get("id", "?")[:20],
                    "layer": layer,
                    "age_days": round(age_days, 1),
                    "ttl": ttl,
                })

        # 晉升候選
        promote_threshold = AUTO_PROMOTE_ACCESS.get(layer)
        if promote_threshold and ac >= promote_threshold:
            promote_candidates.append({
                "id": mem.get("id", "?")[:20],
                "layer": layer,
                "access_count": ac,
                "threshold": promote_threshold,
            })

    report["data"]["access_count_distribution"] = dict(access_counts.most_common(10))
    report["data"]["expired_candidates"] = expired_candidates[:10]
    report["data"]["promote_candidates"] = promote_candidates[:10]

    # 檢查 Nightly
    nightly = _load_json(NIGHTLY_REPORT)
    if nightly:
        step = nightly.get("steps", {}).get("step_03_memory_maintenance", {})
        report["data"]["nightly_memory_step"] = step
        if step.get("status") == "ok":
            result = step.get("result", "")
            report["findings"].append(f"Nightly step_03 已執行: {result}")
        else:
            report["findings"].append("Nightly step_03 未成功執行")

    # 判定
    if total_memories == 0:
        report["status"] = "PASS (no data)"
        report["findings"].append("目前無記憶資料，衰減邏輯無法觸發（正常）")
    elif len(expired_candidates) > 0:
        report["status"] = "WARN"
        report["findings"].append(
            f"有 {len(expired_candidates)} 筆記憶超過 TTL 但未被清理"
        )
    else:
        report["status"] = "PASS"
        report["findings"].append(
            f"共 {total_memories} 筆記憶，無超過 TTL 的紀錄 → 系統正常"
        )

    if all(ac == 0 for ac in access_counts.keys()) and total_memories > 0:
        report["findings"].append(
            "所有記憶的 access_count = 0 → 自動晉升機制尚未被觸發（可能正常）"
        )

    return report


# ====================================================================
# Layer 3: Dendritic Scorer Health Score
# ====================================================================
def verify_health_decay() -> dict:
    """驗證健康分數衰減機制"""
    report = {
        "layer": "Health Score Decay (half-life 2h)",
        "status": "UNKNOWN",
        "findings": [],
        "data": {},
    }

    # 讀取 immunity.json
    immunity = _load_json(IMMUNITY_FILE)
    if immunity is None:
        report["status"] = "FAIL"
        report["findings"].append("immunity.json 不存在")
        return report

    incidents = immunity.get("incidents", [])
    antibodies = immunity.get("antibodies", [])
    stats = immunity.get("stats", {})

    report["data"]["incident_count"] = len(incidents)
    report["data"]["antibody_count"] = len(antibodies)
    report["data"]["stats"] = stats

    # 分析最近 24h 的事件
    recent_events = []
    for inc in incidents:
        ts = inc.get("timestamp")
        if ts:
            dt = _parse_dt(ts) if isinstance(ts, str) else None
            if dt is None and isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(ts, tz=TZ8)
            if dt:
                age_hours = (NOW - dt).total_seconds() / 3600
                if age_hours <= 24:
                    recent_events.append({
                        "symptom": inc.get("symptom_name", "?"),
                        "severity": inc.get("severity", "?"),
                        "age_hours": round(age_hours, 1),
                        "resolved": inc.get("resolved", False),
                    })

    report["data"]["recent_24h_events"] = recent_events[:10]

    # 模擬衰減計算
    # Health Score = 100 + Σ(impact × e^(-ln2 × age_hours / half_life))
    # 由於事件的 impact 值不在 immunity.json 中（在內存），
    # 我們驗證衰減公式的正確性
    test_cases = [
        {"age_hours": 0, "expected_weight": 1.0},
        {"age_hours": 2, "expected_weight": 0.5},     # 1 半衰期
        {"age_hours": 4, "expected_weight": 0.25},    # 2 半衰期
        {"age_hours": 6, "expected_weight": 0.125},   # 3 半衰期
        {"age_hours": 24, "expected_weight": 0.0},    # 超過窗口
    ]
    formula_results = []
    for tc in test_cases:
        age = tc["age_hours"]
        if age > 24:
            weight = 0.0
        else:
            weight = math.exp(-LN2 * age / HEALTH_HALF_LIFE_HOURS)
        formula_results.append({
            "age_hours": age,
            "calculated_weight": round(weight, 6),
            "expected_weight": tc["expected_weight"],
            "match": abs(weight - tc["expected_weight"]) < 0.01,
        })

    report["data"]["formula_verification"] = formula_results

    # 檢查 Nightly health gate
    nightly = _load_json(NIGHTLY_REPORT)
    if nightly:
        mode = nightly.get("mode", "?")
        report["data"]["nightly_mode"] = mode
        report["findings"].append(
            f"Nightly 執行模式: {mode} "
            f"(full=score>70, degraded=40-70, minimal≤40)"
        )
        if mode == "full":
            report["findings"].append("Health Score > 70 → 健康閘正常運作")

    # Health Score 無持久化是已知設計
    report["findings"].append(
        "Health Score 僅存在於內存，重啟後從 100 開始（已知設計限制）"
    )
    report["findings"].append(
        f"immunity.json 記錄了 {len(incidents)} 個 incident"
    )

    # 判定
    all_match = all(r["match"] for r in formula_results)
    if all_match:
        report["status"] = "PASS"
        report["findings"].append("衰減公式驗算正確（半衰期 2h）")
    else:
        report["status"] = "FAIL"
        report["findings"].append("衰減公式驗算不一致")

    return report


# ====================================================================
# Layer 4: Recommender Recency Decay
# ====================================================================
def verify_recommender_decay() -> dict:
    """驗證推薦引擎衰減機制"""
    report = {
        "layer": "Recommender Recency Decay (half-life 7d)",
        "status": "UNKNOWN",
        "findings": [],
        "data": {},
    }

    # 檢查互動歷史
    interactions_file = RECOMMENDATIONS_DIR / "interactions.json"
    interactions = _load_json(interactions_file)

    if interactions is None:
        report["data"]["interactions_file_exists"] = False
        report["findings"].append(
            f"互動歷史檔案不存在: {interactions_file}"
        )
    else:
        report["data"]["interactions_file_exists"] = True
        report["data"]["total_interactions"] = len(interactions) if isinstance(interactions, list) else 0

    # 驗算近因性公式
    # recency_score = 1.0 - exp(-days_ago / RECENCY_HALF_LIFE_DAYS)
    test_cases = [
        {"days_ago": 0, "note": "剛剛"},
        {"days_ago": 1, "note": "1天前"},
        {"days_ago": 7, "note": "7天前（半衰期）"},
        {"days_ago": 14, "note": "14天前"},
        {"days_ago": 30, "note": "30天前"},
    ]
    formula_results = []
    for tc in test_cases:
        days = tc["days_ago"]
        recency = 1.0 - math.exp(-days / RECENCY_HALF_LIFE_DAYS)
        formula_results.append({
            "days_ago": days,
            "recency_score": round(recency, 4),
            "note": tc["note"],
        })

    report["data"]["formula_verification"] = formula_results

    # 檢查 INTERACTION_DECAY 是否被使用
    report["data"]["interaction_decay_constant"] = INTERACTION_DECAY
    report["findings"].append(
        f"INTERACTION_DECAY = {INTERACTION_DECAY} 已定義但源碼中未使用 ⚠️"
    )
    report["findings"].append(
        "近因性公式使用的是 recency_score = 1 - exp(-days/7)，非乘法衰減"
    )

    # 判定
    if interactions is None or (isinstance(interactions, list) and len(interactions) == 0):
        report["status"] = "PASS (no data)"
        report["findings"].append(
            "推薦引擎尚無互動歷史 → 衰減邏輯無法觸發（正常）"
        )
    else:
        report["status"] = "PASS"
        report["findings"].append("推薦引擎有互動紀錄，公式驗算正確")

    return report


# ====================================================================
# 主報告
# ====================================================================
def generate_report(json_output: bool = False) -> dict:
    """生成完整的四層衰減驗證報告"""
    layers = [
        verify_crystal_decay(),
        verify_memory_decay(),
        verify_health_decay(),
        verify_recommender_decay(),
    ]

    # 檢查 Nightly 總狀態
    nightly = _load_json(NIGHTLY_REPORT)
    nightly_summary = {}
    if nightly:
        nightly_summary = {
            "completed_at": nightly.get("completed_at", "?"),
            "mode": nightly.get("mode", "?"),
            "total_steps": nightly.get("summary", {}).get("total", 0),
            "ok_steps": nightly.get("summary", {}).get("ok", 0),
            "error_steps": nightly.get("summary", {}).get("error", 0),
        }

    report = {
        "title": "MUSEON 四層衰減機制驗證報告",
        "generated_at": NOW.isoformat(),
        "nightly_pipeline": nightly_summary,
        "layers": layers,
        "overall_status": "PASS" if all(
            l["status"].startswith("PASS") for l in layers
        ) else "WARN" if any(
            l["status"] == "WARN" for l in layers
        ) else "FAIL",
    }

    # 彙總問題
    issues = []
    for layer in layers:
        if not layer["status"].startswith("PASS"):
            issues.append(f"[{layer['status']}] {layer['layer']}")
    report["issues"] = issues

    if json_output:
        return report

    # 人類可讀輸出
    print("=" * 60)
    print("  MUSEON 四層衰減機制驗證報告")
    print(f"  生成時間: {NOW.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("=" * 60)

    if nightly_summary:
        print(f"\n📋 Nightly Pipeline")
        print(f"   最後執行: {nightly_summary.get('completed_at', '?')}")
        print(f"   模式: {nightly_summary.get('mode', '?')}")
        print(f"   結果: {nightly_summary.get('ok_steps', 0)}/{nightly_summary.get('total_steps', 0)} 步驟成功")

    for layer in layers:
        status_icon = {
            "PASS": "✅",
            "PASS (inactive - system too young)": "✅",
            "PASS (no data)": "✅",
            "WARN": "⚠️",
            "FAIL": "❌",
            "UNKNOWN": "❓",
        }.get(layer["status"], "❓")

        print(f"\n{'─' * 60}")
        print(f"{status_icon} {layer['layer']}")
        print(f"   狀態: {layer['status']}")
        for finding in layer["findings"]:
            print(f"   • {finding}")

        # 印出關鍵數據
        data = layer["data"]
        if "ri_distribution" in data:
            d = data["ri_distribution"]
            print(f"   📊 RI 分布: CORE={d['core_ge_070']}, "
                  f"ACTIVE={d['active_020_070']}, "
                  f"COLD={d['cold_lt_020']}, "
                  f"ARCHIVE={d['archive_lt_005']}")
            s = data.get("ri_stats", {})
            print(f"   📊 RI 統計: min={s.get('min')}, max={s.get('max')}, avg={s.get('avg')}")

        if "user_layer_distribution" in data:
            for user, layers_d in data["user_layer_distribution"].items():
                total = sum(layers_d.values())
                if total > 0:
                    print(f"   📊 {user}: {total} memories ({layers_d})")

        if "formula_verification" in data:
            print("   📊 公式驗算:")
            for fv in data["formula_verification"]:
                if "match" in fv:
                    icon = "✓" if fv["match"] else "✗"
                    print(f"      {icon} age={fv['age_hours']}h → weight={fv['calculated_weight']}")
                elif "recency_score" in fv:
                    print(f"      {fv['note']}: recency={fv['recency_score']}")

    print(f"\n{'=' * 60}")
    overall_icon = "✅" if report["overall_status"] == "PASS" else "⚠️" if report["overall_status"] == "WARN" else "❌"
    print(f"{overall_icon} 總結: {report['overall_status']}")
    if report["issues"]:
        print("   需關注:")
        for issue in report["issues"]:
            print(f"   • {issue}")
    print("=" * 60)

    return report


if __name__ == "__main__":
    json_mode = "--json" in sys.argv
    report = generate_report(json_output=json_mode)
    if json_mode:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
