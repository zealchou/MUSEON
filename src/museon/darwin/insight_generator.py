"""
insight_generator.py — DARWIN 麥肯錫級策略分析引擎 v2

從 run_real_data_simulation() 的回傳 dict 產出六大維度的顧問報告。

公開 API：
    generate_insights(simulation_result: dict) -> dict
"""

from __future__ import annotations

from typing import Any

# ──────────────────────────────────────────────────────────────
# 八方位含義對照表（One Muse 語言）
# ──────────────────────────────────────────────────────────────

_PRIMAL_MEANINGS = {
    "天": "目標破框",
    "風": "溝通成交",
    "水": "關係照顧",
    "山": "紀律累積",
    "地": "穩定承載",
    "雷": "覺察探索",
    "火": "展現投入",
    "澤": "社群品牌",
}

_PRIMAL_BUSINESS_STRENGTH = {
    "天": "目標感強烈、願景領導力旺盛，客群具備高度自我突破動機",
    "風": "溝通穿透力與說服力強，口語行銷與轉介紹成本低",
    "水": "深層關係信任度高，長尾口碑與客戶黏著度為市場優勢",
    "山": "紀律與系統信任感強，品牌可信度與長線口碑積累效率高",
    "地": "消費基底穩固、客群購買力充裕，高端定價策略可行性高",
    "雷": "市場好奇心旺盛、探索動能強，教育型行銷與體驗設計接受度高",
    "火": "展現慾與個人投入強，早期使用者社群驅動力顯著",
    "澤": "社群互動活躍、品牌共鳴敏感度高，口碑裂變與 KOL 策略效率極佳",
}

_PRIMAL_BUSINESS_WEAKNESS = {
    "天": "市場缺乏引領者，需自力教育市場格局，前期投入成本偏高",
    "風": "溝通網絡薄弱，獲客嚴重依賴付費管道，自然流量不足",
    "水": "社群連結度低，缺乏轉介紹驅動力，客戶關係深度不足",
    "山": "系統信任積累緩慢，品牌說服力需長期投入，短期轉換困難",
    "地": "消費承載力弱，市場對高定價敏感，需以低門檻方案驅動試用",
    "雷": "認知探索慾不足，客群缺乏主動學習動力，教育成本偏高",
    "火": "展現驅動力不足，缺乏「明星用戶」帶頭效應，社群能量低迷",
    "澤": "品牌感染力薄弱，無法靠口碑自然裂變，每次獲客均需主動推動",
}

_PRIMAL_PORTER_MAP = {
    "rivalry": {"天": 0.2, "風": 0.3, "澤": 0.2, "火": 0.3},
    "new_entrants": {"天": 0.5, "火": 0.3, "地": -0.4},
    "substitutes": {"澤": 0.4, "風": 0.3, "山": -0.4},
    "buyer_power": {"澤": 0.3, "雷": 0.2, "地": -0.3},
    "supplier_power": {"地": 0.4, "山": 0.3, "水": 0.2},
}

_CHASM_THRESHOLD = 0.16


# ──────────────────────────────────────────────────────────────
# 核心入口
# ──────────────────────────────────────────────────────────────

def generate_insights(simulation_result: dict) -> dict:
    """
    麥肯錫級策略分析。

    Args:
        simulation_result: run_real_data_simulation() 的回傳值

    Returns:
        六大維度分析報告 dict
    """
    district = simulation_result.get("district", "未知區域")
    energy = simulation_result.get("energy", {})
    inner = energy.get("inner", {})
    outer = energy.get("outer", {})
    coverage = simulation_result.get("coverage", {})
    tam = simulation_result.get("tam", 0)
    population = simulation_result.get("population", 0)
    final_state = simulation_result.get("final_state", {})
    snapshots = simulation_result.get("snapshots", [])
    indicators = simulation_result.get("indicators", {})

    # 計算合併能量
    combined = _compute_combined_energy(inner, outer)

    # 六大維度分析
    diagnosis = _gen_diagnosis(district, final_state, tam, snapshots, combined)
    energy_landscape = _gen_energy_landscape(district, inner, outer, combined, indicators)
    timeline_narrative = _gen_timeline_narrative(snapshots, final_state, tam, combined)
    frameworks = _gen_frameworks(combined, final_state, indicators, snapshots, tam)
    action_plan = _gen_action_plan(combined, final_state, snapshots, indicators, diagnosis)
    risk_matrix = _gen_risk_matrix(combined, final_state, coverage, indicators, snapshots)

    return {
        "diagnosis": diagnosis,
        "energy_landscape": energy_landscape,
        "timeline_narrative": timeline_narrative,
        "frameworks": frameworks,
        "action_plan": action_plan,
        "risk_matrix": risk_matrix,
    }


# ──────────────────────────────────────────────────────────────
# 工具函式
# ──────────────────────────────────────────────────────────────

def _compute_combined_energy(inner: dict, outer: dict) -> dict[str, float]:
    """合併內外能量（外在 60%、內在 40%）"""
    primals = set(list(inner.keys()) + list(outer.keys()))
    combined: dict[str, float] = {}
    for p in primals:
        iv = inner.get(p, 0.0)
        ov = outer.get(p, 0.0)
        combined[p] = round(iv * 0.4 + ov * 0.6, 2)
    return combined


def _get_snap_dist(snap: dict | Any) -> dict:
    """相容 WeeklySnapshot 物件或純 dict 的快照取值"""
    if hasattr(snap, "business_metrics"):
        return snap.business_metrics.get("state_distribution", {})
    return snap.get("business_metrics", {}).get("state_distribution", {})


def _get_snap_week(snap: dict | Any) -> int:
    if hasattr(snap, "week"):
        return snap.week
    return snap.get("week", 0)


def _get_snap_metrics(snap: dict | Any) -> dict:
    if hasattr(snap, "business_metrics"):
        return snap.business_metrics
    return snap.get("business_metrics", {})


def _get_snap_is_tp(snap: dict | Any) -> bool:
    if hasattr(snap, "is_turning_point"):
        return snap.is_turning_point
    return snap.get("is_turning_point", False)


def _verdict_from_penetration(pct: float) -> str:
    if pct > 30:
        return "強勁"
    elif pct >= 20:
        return "穩健"
    elif pct >= 10:
        return "需調整"
    else:
        return "警告"


def _force_level_from_score(score: float) -> str:
    if score > 0.3:
        return "高"
    elif score > 0.0:
        return "中"
    else:
        return "低"


# ──────────────────────────────────────────────────────────────
# 一、策略診斷摘要
# ──────────────────────────────────────────────────────────────

def _gen_diagnosis(
    district: str,
    final_state: dict,
    tam: int,
    snapshots: list,
    combined: dict,
) -> dict:
    loyal_ratio = final_state.get("loyal", {}).get("ratio", 0.0)
    loyal_count = final_state.get("loyal", {}).get("count", 0)
    decided_ratio = final_state.get("decided", {}).get("ratio", 0.0)
    considering_ratio = final_state.get("considering", {}).get("ratio", 0.0)
    resistant_ratio = final_state.get("resistant", {}).get("ratio", 0.0)

    penetration_rate = round((loyal_ratio + decided_ratio) * 100, 1)
    chasm_crossed = loyal_ratio >= _CHASM_THRESHOLD
    verdict = _verdict_from_penetration(penetration_rate)

    # 最高能量方位
    top_primal = max(combined, key=combined.get) if combined else "澤"
    top_val = combined.get(top_primal, 0.0)

    # 最終週收益
    final_revenue = 0
    if snapshots:
        last_snap = snapshots[-1]
        m = _get_snap_metrics(last_snap)
        final_revenue = m.get("revenue_ntd", loyal_count * 12000)

    # 計算增長加速週
    inflection_week = _find_inflection_week(snapshots)

    # 一句話結論
    chasm_text = "已突破鴻溝、進入自我擴散軌道" if chasm_crossed else "尚在早期採用者圈層、未跨越鴻溝"
    headline = (
        f"{district}市場策略評估：滲透率 {penetration_rate}%，{chasm_text}，"
        f"以「{top_primal}」（{top_val:+.1f}）為市場主導能量，整體判定【{verdict}】"
    )

    # 關鍵數字
    key_numbers = {
        "採用率": f"{penetration_rate}%（忠實 {loyal_ratio * 100:.0f}% + 決策中 {decided_ratio * 100:.0f}%）",
        "忠實用戶數": f"{loyal_count} 人",
        "觀望比例": f"{considering_ratio * 100:.0f}%（潛在轉化池）",
        "年化收益估算": f"NT$ {final_revenue:,}",
        "鴻溝狀態": "已跨越 ✓" if chasm_crossed else "未跨越 ✗（16% 門檻）",
    }
    if inflection_week:
        key_numbers["口碑拐點"] = f"第 {inflection_week} 週"

    # 完整摘要段落
    growth_phase = "規模化" if penetration_rate > 30 else ("鴻溝跨越") if penetration_rate > 15 else "早期市場"
    chasm_paragraph = (
        "忠實用戶已突破 Rogers 鴻溝門檻（16%），自然口碑開始接棒，後續行銷投報率將顯著改善。"
        if chasm_crossed
        else f"忠實用戶尚未達到 16% 鴻溝門檻，策略停留在早期採用者圈層，需要強化社會認同觸媒才能突破到主流市場。"
    )
    resistant_paragraph = (
        f"抵制率達 {resistant_ratio * 100:.0f}%，需要調查負向口碑根源並介入。"
        if resistant_ratio > 0.05
        else ""
    )
    one_paragraph = (
        f"本次 52 週模擬在 {district} 呈現{verdict}表現，整體採用率達 {penetration_rate}%，"
        f"目前處於{growth_phase}階段。"
        f"{chasm_paragraph}"
        f"觀望族群佔 {considering_ratio * 100:.0f}%，為最大的短期轉化潛力池，"
        f"若能降低試用門檻，預估可在 8 週內提升 20-35% 的轉化率。"
        f"{resistant_paragraph}"
    )

    return {
        "headline": headline,
        "verdict": verdict,
        "key_numbers": key_numbers,
        "one_paragraph": one_paragraph.strip(),
    }


def _find_inflection_week(snapshots: list) -> int | None:
    """找出忠實用戶增長最快的週（口碑拐點）"""
    if not snapshots:
        return None
    max_growth = 0.0
    inflection = None
    prev_loyal = 0.0
    for snap in snapshots:
        dist = _get_snap_dist(snap)
        loyal = dist.get("loyal", 0.0)
        growth = loyal - prev_loyal
        if growth > max_growth:
            max_growth = growth
            inflection = _get_snap_week(snap)
        prev_loyal = loyal
    return inflection


# ──────────────────────────────────────────────────────────────
# 二、市場能量地景
# ──────────────────────────────────────────────────────────────

def _gen_energy_landscape(
    district: str,
    inner: dict,
    outer: dict,
    combined: dict,
    indicators: dict,
) -> dict:
    sorted_combined = sorted(combined.items(), key=lambda x: x[1], reverse=True)
    top3 = sorted_combined[:3]
    bottom3 = sorted_combined[-3:]

    # 前 3 強方位
    dominant_energies = []
    for primal, val in top3:
        biz_meaning = _PRIMAL_BUSINESS_STRENGTH.get(primal, "")
        dominant_energies.append({
            "primal": primal,
            "score": round(val, 2),
            "label": _PRIMAL_MEANINGS.get(primal, ""),
            "business_implication": biz_meaning,
            "inner": round(inner.get(primal, 0.0), 2),
            "outer": round(outer.get(primal, 0.0), 2),
        })

    # 後 3 弱方位
    weak_energies = []
    for primal, val in bottom3:
        biz_meaning = _PRIMAL_BUSINESS_WEAKNESS.get(primal, "")
        weak_energies.append({
            "primal": primal,
            "score": round(val, 2),
            "label": _PRIMAL_MEANINGS.get(primal, ""),
            "risk_implication": biz_meaning,
        })

    # 市場性格
    top_primal = top3[0][0] if top3 else "澤"
    second_primal = top3[1][0] if len(top3) > 1 else ""

    if top_primal == "澤" and second_primal in ("天", "火"):
        market_character = f"這是一個品牌共鳴驅動、追求自我展現的市場——消費者在乎「我選擇了什麼品牌」勝過產品本身的功能性。"
    elif top_primal in ("天", "火"):
        market_character = f"這是一個創新優先、個性彰顯的市場——率先採用新產品的先驅者擁有強大的社群影響力。"
    elif top_primal in ("地", "山"):
        market_character = f"這是一個穩定信任優先的市場——消費者重視長期品質承諾，對飛速崛起的新品牌持謹慎態度。"
    elif top_primal in ("水", "雷"):
        market_character = f"這是一個關係深度主導的市場——口碑傳播依賴真實的情感連結，而非廣告曝光量。"
    elif top_primal == "風":
        market_character = f"這是一個資訊流動快、決策效率高的市場——優質溝通者可以快速建立信任並推動成交。"
    else:
        market_character = f"這是一個多元動能並存的市場——沒有單一主導方位，策略需要兼顧多個消費者面向。"

    # 消費者心理
    household_income = indicators.get("household_income", 0)
    population_density = indicators.get("population_density", 0)
    澤_val = combined.get("澤", 0)
    地_val = combined.get("地", 0)
    山_val = combined.get("山", 0)

    if 澤_val > 2.0 and 地_val > 0:
        customer_psychology = "這裡的消費者具備強烈的社群認同需求，對於「圈內人都在用」的訊號高度敏感，品牌歸屬感是購買決策的核心驅動力。"
    elif 地_val > 1.5 and household_income > 600:
        customer_psychology = "這裡的消費者購買力充裕且消費決策成熟，不以價格為首要考量，轉而追求品質保證與使用體驗的深度。"
    elif 山_val > 2.0:
        customer_psychology = "這裡的消費者偏保守謹慎，傾向在充分了解後才行動，重視他人使用評價與品牌歷史，新品需要更長的信任建立期。"
    elif combined.get("雷", 0) > 1.5:
        customer_psychology = "這裡的消費者具備高度好奇心與探索慾，對於新知識和突破性概念有主動吸收的動力，教育型行銷效果顯著。"
    else:
        customer_psychology = "這裡的消費者呈現多元面貌，採購決策受個人情境影響明顯，策略需針對不同客群生命週期設計差異化訊息。"

    # 競爭環境描述
    cafe_density = indicators.get("cafe_density", 0)
    if cafe_density > 1.0 or 澤_val > 2.5:
        competitive_environment = "競爭環境高度激烈，市場已充斥大量同類服務與替代選項，差異化定位是生存的必要條件而非加分項。"
    elif 地_val > 1.5 and 山_val > 1.5:
        competitive_environment = "競爭環境相對穩定，市場有一定進入壁壘（租金成本或品牌信任積累），先進入者具備顯著優勢。"
    else:
        competitive_environment = "競爭環境處於動態平衡，市場尚有進入空間，但需在 12 個月內完成品牌定錨，否則窗口將逐漸關閉。"

    return {
        "dominant_energies": dominant_energies,
        "weak_energies": weak_energies,
        "market_character": market_character,
        "customer_psychology": customer_psychology,
        "competitive_environment": competitive_environment,
    }


# ──────────────────────────────────────────────────────────────
# 三、52 週戰場回放
# ──────────────────────────────────────────────────────────────

def _gen_timeline_narrative(
    snapshots: list,
    final_state: dict,
    tam: int,
    combined: dict,
) -> dict:
    if not snapshots:
        return {
            "phases": [],
            "critical_weeks": [],
            "chasm_analysis": "無快照資料，無法進行時間軸分析。",
            "momentum_narrative": "無快照資料。",
        }

    # 切四個季度
    q1 = [s for s in snapshots if 1 <= _get_snap_week(s) <= 13]
    q2 = [s for s in snapshots if 14 <= _get_snap_week(s) <= 26]
    q3 = [s for s in snapshots if 27 <= _get_snap_week(s) <= 39]
    q4 = [s for s in snapshots if 40 <= _get_snap_week(s) <= 52]

    phases = [
        _analyze_quarter(q1, 1, 13, "認知建立期", combined, tam),
        _analyze_quarter(q2, 14, 26, "早期滲透期", combined, tam),
        _analyze_quarter(q3, 27, 39, "鴻溝跨越期", combined, tam),
        _analyze_quarter(q4, 40, 52, "規模化鞏固期", combined, tam),
    ]

    # 找關鍵週（turning points + 特殊狀態轉折）
    critical_weeks = _find_critical_weeks(snapshots, tam)

    # 鴻溝分析
    chasm_week = None
    for snap in snapshots:
        dist = _get_snap_dist(snap)
        if dist.get("loyal", 0.0) >= _CHASM_THRESHOLD:
            chasm_week = _get_snap_week(snap)
            break

    loyal_final = final_state.get("loyal", {}).get("ratio", 0.0)
    chasm_crossed_final = loyal_final >= _CHASM_THRESHOLD
    if chasm_week:
        chasm_analysis = (
            f"策略在第 {chasm_week} 週成功突破 Rogers 鴻溝（忠實用戶達 16%）。"
            f"突破點在第二季度結束前實現，顯示社群口碑在中段就開始自我擴散，"
            f"建議未來將突破鴻溝的資源集中在第 {max(1, chasm_week - 4)}-{chasm_week} 週的關鍵窗口。"
        )
    elif chasm_crossed_final:
        chasm_analysis = (
            f"忠實用戶最終達 {loyal_final * 100:.0f}%，已超越 16% 鴻溝門檻，策略可行性已獲市場確認。"
            f"但快照記錄中未找到明確的單一突破週，代表鴻溝是以漸進式方式跨越——"
            f"這意味著下一輪策略應聚焦在識別並強化那些加速漸進突破的關鍵觸媒，讓過程更快、更確定性。"
        )
    elif loyal_final >= 0.10:
        chasm_analysis = (
            f"策略未在 52 週內完成鴻溝突破，忠實用戶達 {loyal_final * 100:.0f}%，"
            f"距離 16% 門檻仍差 {(0.16 - loyal_final) * 100:.1f} 個百分點。"
            f"建議在第二年的前 13 週集中投入社會認同信號（案例見證、媒體露出），"
            f"鴻溝突破可能就在臨界點的一次關鍵觸媒之後。"
        )
    else:
        chasm_analysis = (
            f"策略尚在早期採用者圈層（忠實用戶 {loyal_final * 100:.0f}%），"
            f"鴻溝尚未形成突破條件。根本原因可能在於早期使用者的「展示價值」不足——"
            f"需要打造 3-5 個強力成功案例，讓觀望中的主流市場看到同類型用戶的成果。"
        )

    # 動能敘事
    momentum_narrative = _gen_momentum_narrative(snapshots, combined)

    return {
        "phases": phases,
        "critical_weeks": critical_weeks,
        "chasm_analysis": chasm_analysis,
        "momentum_narrative": momentum_narrative,
    }


def _analyze_quarter(
    snaps: list,
    week_start: int,
    week_end: int,
    name: str,
    combined: dict,
    tam: int,
) -> dict:
    if not snaps:
        return {
            "name": name,
            "weeks": f"{week_start}-{week_end}",
            "what_happened": "本季度無快照資料。",
            "why": "—",
            "turning_points": [],
            "strategy_effectiveness": "無資料",
            "should_have_done": "補充快照資料後重新分析。",
        }

    first_dist = _get_snap_dist(snaps[0])
    last_dist = _get_snap_dist(snaps[-1])
    last_metrics = _get_snap_metrics(snaps[-1])

    aware_start = first_dist.get("aware", 0.0)
    aware_end = last_dist.get("aware", 0.0)
    considering_end = last_dist.get("considering", 0.0)
    decided_end = last_dist.get("decided", 0.0)
    loyal_end = last_dist.get("loyal", 0.0)
    penetration_end = round((decided_end + loyal_end) * 100, 1)
    revenue_end = last_metrics.get("revenue_ntd", 0)

    # 找本季轉折點
    turning_points = []
    for snap in snaps:
        if _get_snap_is_tp(snap):
            w = _get_snap_week(snap)
            dist = _get_snap_dist(snap)
            loyal_tp = dist.get("loyal", 0.0)
            aware_tp = dist.get("aware", 0.0)
            turning_points.append({
                "week": w,
                "description": f"第 {w} 週市場動能轉折——認知率 {aware_tp * 100:.0f}%、忠實率 {loyal_tp * 100:.0f}%",
            })

    # 依季度生成不同分析語言
    top_primal = max(combined, key=combined.get) if combined else "澤"

    if name == "認知建立期":
        what_happened = (
            f"第一季度完成市場認知鋪底。目標客群認知率從 {aware_start * 100:.0f}% 推進至 {aware_end * 100:.0f}%，"
            f"已有 {considering_end * 100:.0f}% 進入考慮評估階段，整體採用率達 {penetration_end}%。"
        )
        why = (
            f"「{top_primal}」能量作為區域主導力，在初期建立認知時提供了天然的傳播土壤——"
            f"{_PRIMAL_BUSINESS_STRENGTH.get(top_primal, '方位優勢顯著')}。"
            f"然而，早期採用者的稀疏性使口碑尚未形成網絡效應，擴散仍依賴主動推廣。"
        )
        strategy_effectiveness = (
            "初步有效" if aware_end > 0.15 else "低於預期——認知建立速度偏慢，建議在 Q2 加倍曝光投入"
        )
        should_have_done = (
            "應更早鎖定「超級連結者」（super-connector）——即在社群中有高影響力的早期採用者，"
            "透過他們的背書加速認知擴散，而非依賴廣泛但淺薄的媒體購買。"
        )

    elif name == "早期滲透期":
        what_happened = (
            f"第二季度轉型為主動滲透。考慮中族群達 {considering_end * 100:.0f}%，"
            f"已有部分轉為決策行動（{decided_end * 100:.0f}%），採用率累積至 {penetration_end}%，"
            f"估算季末年化收益 NT$ {revenue_end:,}。"
        )
        why = (
            f"早期使用者的真實使用案例開始形成口碑壓力，但鴻溝尚未跨越——"
            f"觀望族群（{considering_end * 100:.0f}%）正在等待「更多同類型用戶的驗證」再行動。"
            f"這是 Rogers 擴散理論中最典型的早期多數猶豫期，需要主動製造社會認同信號。"
        )
        strategy_effectiveness = (
            "良好" if decided_end > 0.10 else "轉換率偏低——觀望族群卡關，需要優化 CTA 設計與試用門檻"
        )
        should_have_done = (
            "應在季初就設計「第一批客戶展示計畫」——精選 5-10 個成功案例進行深度包裝，"
            "讓他們成為可見的品牌大使，主動在目標社群曝光成果，降低後進者的心理採用門檻。"
        )

    elif name == "鴻溝跨越期":
        chasm_crossed_q = loyal_end >= _CHASM_THRESHOLD
        what_happened = (
            f"第三季度是鴻溝決戰關鍵期。忠實用戶{'突破 16% 鴻溝門檻（' + str(round(loyal_end * 100, 0)) + '%）' if chasm_crossed_q else '達 ' + str(round(loyal_end * 100, 1)) + '%，但仍在鴻溝前'}，"
            f"採用率整體達 {penetration_end}%。"
        )
        why = (
            f"{'鴻溝突破成功，代表口碑已從「早期採用者背書」升級為「主流市場認可」，自我擴散動能正式啟動。' if chasm_crossed_q else '鴻溝尚未突破，原因可能在於目標客群對產品的「主流適用性」尚有疑慮——他們需要看到「跟自己類似的人已成功採用」的具體證據。'}"
        )
        strategy_effectiveness = (
            "突破性進展" if chasm_crossed_q else "關鍵期未能突破鴻溝，Q4 需要全力衝刺"
        )
        should_have_done = (
            "鴻溝跨越的決定性武器是「利基市場聚焦」——選定最容易突破的一個客群垂直市場集中火力，"
            "而非同時打多個市場。建議 Q3 應鎖定一個明確的社群（如特定職業或生活圈），"
            "做到「這個圈子幾乎人人知道我們」，再向外擴散。"
        )

    else:  # 規模化鞏固期
        what_happened = (
            f"第四季度進入成果收割與基盤鞏固。季末忠實用戶達 {loyal_end * 100:.1f}%，"
            f"採用率 {penetration_end}%，估算年化收益 NT$ {revenue_end:,}。"
        )
        why = (
            f"{'口碑自然擴散已接棒，每位忠實用戶平均帶動 1-2 位新採用者進入漏斗，行銷投報率顯著改善。' if loyal_end >= _CHASM_THRESHOLD else '尚未跨越鴻溝，口碑效應受限，成長依然高度依賴主動行銷投入，邊際效益未能提升。'}"
        )
        strategy_effectiveness = (
            "規模化條件成熟" if penetration_end > 25 else "需要修正後再啟動規模化"
        )
        should_have_done = (
            "Q4 應更積極推動「忠實客戶轉介紹激勵計畫」——給予現有忠實用戶有吸引力的推薦獎勵，"
            "將口碑動能轉化為系統性的低成本獲客引擎，同時開始為下一個地區市場的複製做準備。"
        )

    return {
        "name": name,
        "weeks": f"{week_start}-{week_end}",
        "what_happened": what_happened,
        "why": why,
        "turning_points": turning_points,
        "strategy_effectiveness": strategy_effectiveness,
        "should_have_done": should_have_done,
    }


def _find_critical_weeks(snapshots: list, tam: int) -> list[dict]:
    """找出全年最關鍵的 3-5 週"""
    critical = []

    # 1. 所有 turning point 週
    for snap in snapshots:
        if _get_snap_is_tp(snap):
            w = _get_snap_week(snap)
            dist = _get_snap_dist(snap)
            critical.append({
                "week": w,
                "type": "market_turning_point",
                "description": f"市場動能轉折：認知率 {dist.get('aware', 0) * 100:.0f}%、忠實率 {dist.get('loyal', 0) * 100:.0f}%",
                "strategic_significance": "動能轉折週代表口碑效應的質變時刻，此週前後 2 週的行銷投入效率最高。",
            })

    # 2. 忠實用戶首次達 5% 的週
    seen_5pct = False
    for snap in snapshots:
        dist = _get_snap_dist(snap)
        if not seen_5pct and dist.get("loyal", 0) >= 0.05:
            w = _get_snap_week(snap)
            critical.append({
                "week": w,
                "type": "early_loyalty_milestone",
                "description": f"第 {w} 週：忠實用戶首次突破 5%，早期核心社群成形。",
                "strategic_significance": "早期 5% 忠實用戶是口碑引擎的種子群體，此時需集中資源深化他們的體驗，而非分散去獲取更多新客。",
            })
            seen_5pct = True

    # 3. 鴻溝突破週
    for snap in snapshots:
        dist = _get_snap_dist(snap)
        if dist.get("loyal", 0) >= _CHASM_THRESHOLD:
            w = _get_snap_week(snap)
            critical.append({
                "week": w,
                "type": "chasm_crossing",
                "description": f"第 {w} 週：成功跨越 Rogers 鴻溝（忠實用戶 ≥ 16%），策略進入自我擴散階段。",
                "strategic_significance": "鴻溝突破是市場採用的分水嶺事件，此後行銷費用效益比將顯著改善，可啟動規模化預算。",
            })
            break

    # 依週排序，取前 5
    critical.sort(key=lambda x: x["week"])
    return critical[:5]


def _gen_momentum_narrative(snapshots: list, combined: dict) -> str:
    """市場動能敘事（全年一段話）"""
    if not snapshots:
        return "無快照資料，無法生成動能敘事。"

    # 計算各階段的週平均增長
    q1_snaps = [s for s in snapshots if 1 <= _get_snap_week(s) <= 13]
    q2_snaps = [s for s in snapshots if 14 <= _get_snap_week(s) <= 26]
    q3_snaps = [s for s in snapshots if 27 <= _get_snap_week(s) <= 39]
    q4_snaps = [s for s in snapshots if 40 <= _get_snap_week(s) <= 52]

    def quarter_end_penetration(q_snaps: list) -> float:
        if not q_snaps:
            return 0.0
        d = _get_snap_dist(q_snaps[-1])
        return (d.get("decided", 0) + d.get("loyal", 0)) * 100

    q1_pct = quarter_end_penetration(q1_snaps)
    q2_pct = quarter_end_penetration(q2_snaps)
    q3_pct = quarter_end_penetration(q3_snaps)
    q4_pct = quarter_end_penetration(q4_snaps)

    top_primal = max(combined, key=combined.get) if combined else "澤"

    return (
        f"市場動能呈現典型的 S 型擴散曲線：Q1 以「{top_primal}」能量為引擎完成認知鋪底（採用率 {q1_pct:.1f}%），"
        f"Q2 轉入早期滲透，觀望族群開始轉化（{q2_pct:.1f}%），"
        f"Q3 是決定性關卡{'——策略成功突破鴻溝進入自我擴散軌道（' + str(round(q3_pct, 1)) + '%）' if q3_pct > q2_pct * 1.3 else '——增長相對溫和，鴻溝突破仍需催化劑（' + str(round(q3_pct, 1)) + '%）'}，"
        f"Q4 進入鞏固期（{q4_pct:.1f}%）。"
        f"整體動能呈現{'前慢後快的加速型曲線，顯示口碑網絡效應在後半年顯著生效' if q4_pct > q1_pct * 3 else '相對線性的穩步增長，缺乏明顯的病毒式爆發，建議下一輪策略重點強化口碑觸媒設計'}。"
    )


# ──────────────────────────────────────────────────────────────
# 四、策略框架分析
# ──────────────────────────────────────────────────────────────

def _gen_frameworks(
    combined: dict,
    final_state: dict,
    indicators: dict,
    snapshots: list,
    tam: int,
) -> dict:
    swot = _gen_swot(combined, final_state, snapshots)
    porter = _gen_porter(combined, indicators)
    marketing_4p = _gen_4p(combined, indicators, final_state)

    return {
        "swot": swot,
        "porter_five_forces": porter,
        "marketing_4p": marketing_4p,
    }


def _gen_swot(
    combined: dict,
    final_state: dict,
    snapshots: list,
) -> dict:
    strengths = []
    weaknesses = []
    opportunities = []
    threats = []

    # Strengths — 能量 > 2.0 的方位
    for primal, val in combined.items():
        if val >= 2.0:
            biz = _PRIMAL_BUSINESS_STRENGTH.get(primal, "")
            strengths.append(f"【{primal}能量優勢 {val:+.1f}】{biz}")
        elif val >= 1.2:
            biz = _PRIMAL_BUSINESS_STRENGTH.get(primal, "")
            strengths.append(f"【{primal}能量支撐 {val:+.1f}】{biz}（中等優勢，可進一步強化）")

    # 從模擬結果找 Strengths：忠實用戶比例
    loyal_ratio = final_state.get("loyal", {}).get("ratio", 0.0)
    if loyal_ratio >= _CHASM_THRESHOLD:
        strengths.append(f"【市場驗證】忠實用戶已達 {loyal_ratio * 100:.0f}%，超越鴻溝門檻，策略可行性已獲市場確認")

    # Weaknesses — 能量 < -1.5 的方位
    for primal, val in combined.items():
        if val <= -1.5:
            biz = _PRIMAL_BUSINESS_WEAKNESS.get(primal, "")
            weaknesses.append(f"【{primal}能量缺口 {val:.1f}】{biz}")
        elif val < -0.8:
            biz = _PRIMAL_BUSINESS_WEAKNESS.get(primal, "")
            weaknesses.append(f"【{primal}能量偏弱 {val:.1f}】{biz}（中度劣勢，需要策略補位）")

    # 從模擬結果找 Weaknesses：resistant 過高
    resistant_ratio = final_state.get("resistant", {}).get("ratio", 0.0)
    if resistant_ratio > 0.05:
        weaknesses.append(f"【負向口碑風險】抵制比例達 {resistant_ratio * 100:.0f}%，顯示定位或溝通方式引發部分族群的主動排斥")

    # Opportunities — 從模擬動態找
    considering_ratio = final_state.get("considering", {}).get("ratio", 0.0)
    if considering_ratio >= 0.20:
        opportunities.append(
            f"【轉化紅利】觀望族群佔 {considering_ratio * 100:.0f}%，為最大的即期商業機會——"
            f"這批已知曉品牌的潛客只差「最後一哩路」的推力，轉化成本遠低於開發全新客戶"
        )

    # 從快照找增長加速信號
    inflection = _find_inflection_week(snapshots)
    if inflection and inflection <= 30:
        opportunities.append(
            f"【口碑引擎啟動】市場動能拐點在第 {inflection} 週提前出現，"
            f"顯示口碑擴散效率高於平均值，適合加碼投入觸媒行銷以放大此優勢"
        )

    # 能量組合機會
    if combined.get("澤", 0) > 2.0:
        opportunities.append("【社群裂變機會】澤能量強勁，KOL 合作與口碑計畫的 ROI 將遠高於廣告投放，建議將 30%+ 行銷預算導入社群策略")
    if combined.get("雷", 0) > 1.5:
        opportunities.append("【知識付費切入】雷能量旺盛，市場對深度內容有高度渴求，可考慮以「入門課程或工作坊」為行銷漏斗的前端，降低首次接觸門檻")
    if combined.get("天", 0) > 2.0:
        opportunities.append("【高端定位突破】天能量強，市場中存在一批渴望格局突破的高意願客群，具備精品定價的承接空間")

    # Threats — 從能量弱點找
    for primal, val in combined.items():
        if val <= -2.0:
            threats.append(f"【{primal}能量嚴重不足 {val:.1f}】市場在此方位的阻力為最高級別，若策略核心依賴此方位，推進將遭遇系統性阻力")

    # 鴻溝風險
    if loyal_ratio < _CHASM_THRESHOLD:
        threats.append(
            f"【鴻溝陷阱】忠實用戶僅 {loyal_ratio * 100:.0f}%，仍在鴻溝前——"
            f"若無法在接下來 13 週內實現突破，早期採用者圈層的熱度將消退，"
            f"後續推動將比現在困難 2-3 倍"
        )

    if resistant_ratio > 0.03:
        threats.append(f"【負向口碑擴散】抵制族群（{resistant_ratio * 100:.0f}%）若進入社群活躍期，可能對觀望族群造成 5-10 倍的負向影響力")

    # 確保每個區塊至少有內容
    if not strengths:
        strengths.append("能量分析顯示方位優勢不明顯，策略需依靠執行力與市場教育建立競爭優勢")
    if not weaknesses:
        weaknesses.append("未偵測到顯著能量缺口，需持續監測市場動態以識別新興弱點")
    if not opportunities:
        opportunities.append("市場尚有未開發的利基機會，建議進行客群細分研究以識別高潛力切入點")
    if not threats:
        threats.append("短期未發現重大威脅，但需警惕競爭者可能在鴻溝突破期加大力度阻截")

    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "opportunities": opportunities,
        "threats": threats,
    }


def _gen_porter(combined: dict, indicators: dict) -> dict:
    """Porter 五力分析（以能量向量推估）"""
    cafe_density = indicators.get("cafe_density", 0)
    household_income = indicators.get("household_income", 0)
    population_density = indicators.get("population_density", 0)

    # ── 同業競爭（Rivalry）──
    rivalry_score = 0.0
    rivalry_score += min(cafe_density * 0.15, 0.3)
    rivalry_score += combined.get("澤", 0) * 0.06
    rivalry_score += combined.get("火", 0) * 0.05
    rivalry_level = _force_level_from_score(rivalry_score - 0.1)
    rivalry_analysis = (
        f"同業競爭強度【{rivalry_level}】。"
        f"{'咖啡廳密度 ' + str(cafe_density) + ' 家/千人，市場飽和度高，' if cafe_density > 0.8 else '市場密度尚可，'}"
        f"加上澤能量（{combined.get('澤', 0):+.1f}）反映品牌導向的消費文化——"
        f"競爭已從價格戰進化為品牌認同之爭，差異化定位是唯一的護城河。"
    )

    # ── 新進入者威脅（New Entrants）──
    entrant_score = combined.get("天", 0) * 0.08 - combined.get("地", 0) * 0.06
    entrant_level = _force_level_from_score(entrant_score)
    entrant_analysis = (
        f"新進入者威脅【{entrant_level}】。"
        f"天能量（{combined.get('天', 0):+.1f}）{'高，創業氛圍活躍，市場持續吸引新玩家進入；' if combined.get('天', 0) > 1.0 else '一般，新進入壓力尚可控；'}"
        f"地能量（{combined.get('地', 0):+.1f}）{'高，高租金與資本門檻形成自然進入壁壘，保護現有玩家。' if combined.get('地', 0) > 1.5 else '偏低，進入成本門檻不高，需要以品牌護城河防禦。'}"
    )

    # ── 替代品威脅（Substitutes）──
    sub_score = combined.get("澤", 0) * 0.07 + combined.get("風", 0) * 0.05 - combined.get("山", 0) * 0.06
    sub_level = _force_level_from_score(sub_score)
    sub_analysis = (
        f"替代品威脅【{sub_level}】。"
        f"澤能量（{combined.get('澤', 0):+.1f}）高的市場消費選擇豐富，替代品選項多元；"
        f"山能量（{combined.get('山', 0):+.1f}）{'高，消費者具備品牌黏著性，替代轉換成本較高。' if combined.get('山', 0) > 1.5 else '偏低，客戶忠誠度需要主動建立，否則替代轉換率偏高。'}"
    )

    # ── 買方議價力（Buyer Power）──
    buyer_score = combined.get("澤", 0) * 0.05 - combined.get("地", 0) * 0.05
    if household_income > 600:
        buyer_score -= 0.2  # 高收入 = 不計較價格，買方議價力下降
    elif household_income < 400:
        buyer_score += 0.15
    buyer_level = _force_level_from_score(buyer_score)
    buyer_analysis = (
        f"買方議價力【{buyer_level}】。"
        f"家戶所得 NT$ {household_income:.0f}K，"
        f"{'高消費力客群對價格不敏感，品牌溢價空間大；' if household_income > 600 else '消費力一般，價格敏感度中等；'}"
        f"人口密度 {population_density:,} 人/km²，"
        f"{'選擇豐富，消費者比較購買意願強，議價心理強。' if population_density > 15000 else '密度較低，同類服務選項有限，議價空間受限。'}"
    )

    # ── 供應商議價力（Supplier Power）──
    supplier_score = combined.get("地", 0) * 0.06 + combined.get("山", 0) * 0.05
    supplier_level = _force_level_from_score(0.1 - supplier_score)
    supplier_analysis = (
        f"供應商議價力【{supplier_level}】。"
        f"地能量（{combined.get('地', 0):+.1f}）{'高，區域供應鏈成熟完善，採購選擇多元，不易受單一供應商制約；' if combined.get('地', 0) > 1.0 else '偏低，供應鏈可能較為集中，需注意關鍵供應商的議價風險；'}"
        f"建議優先建立 2 個以上的替代供應來源以分散風險。"
    )

    # 整體判斷
    forces_summary = f"五力合計來看，最大的競爭壓力來自{'同業競爭' if rivalry_level == '高' else '買方議價' if buyer_level == '高' else '替代品威脅'}，"
    forces_summary += f"策略重點應放在{'強化品牌差異化以擺脫純同業廝殺' if rivalry_level == '高' else '提升服務深度與客戶黏著度以抵禦替代品威脅'}。"

    return {
        "rivalry": {"level": rivalry_level, "analysis": rivalry_analysis},
        "new_entrants": {"level": entrant_level, "analysis": entrant_analysis},
        "substitutes": {"level": sub_level, "analysis": sub_analysis},
        "buyer_power": {"level": buyer_level, "analysis": buyer_analysis},
        "supplier_power": {"level": supplier_level, "analysis": supplier_analysis},
        "overall": forces_summary,
    }


def _gen_4p(
    combined: dict,
    indicators: dict,
    final_state: dict,
) -> dict:
    household_income = indicators.get("household_income", 0)
    population_density = indicators.get("population_density", 0)

    澤_val = combined.get("澤", 0)
    天_val = combined.get("天", 0)
    山_val = combined.get("山", 0)
    地_val = combined.get("地", 0)
    火_val = combined.get("火", 0)
    雷_val = combined.get("雷", 0)
    風_val = combined.get("風", 0)
    水_val = combined.get("水", 0)

    loyal_ratio = final_state.get("loyal", {}).get("ratio", 0.0)
    penetration_pct = (final_state.get("loyal", {}).get("ratio", 0.0) + final_state.get("decided", {}).get("ratio", 0.0)) * 100

    # ── Product ──
    if 澤_val > 2.0:
        product_current = "服務/產品的功能性層面已基本成立"
        product_rec = "重心轉移到「品牌體驗包裝」——不只賣功能，賣的是客戶使用後所感受到的身份認同感。設計品牌儀式感（Unboxing、專屬歡迎流程）和社群歸屬標誌（標籤、稱謂、認證）。"
        product_energy = f"澤能量 {澤_val:+.1f}：市場對品牌感染力高度敏感，品牌體驗>產品功能"
    elif 火_val > 1.5:
        product_current = "早期版本已驗證核心價值主張"
        product_rec = "維持每季新品或限定版策略，以「常有新鮮感」維繫早期使用者的持續投入與分享動力。"
        product_energy = f"火能量 {火_val:+.1f}：客群展現慾強，需要定期提供「值得分享」的新體驗"
    elif 山_val > 2.0:
        product_current = "品質基盤已初步建立"
        product_rec = "聚焦打造可量化的品質證據——第三方認證、案例成果數字化、用戶見證標準化，讓潛客在研究階段就能被這些證據說服。"
        product_energy = f"山能量 {山_val:+.1f}：客群信任品質累積，需要具體可見的成果佐證"
    else:
        product_current = "核心產品需要持續迭代以配合市場反饋"
        product_rec = "建立「早期使用者反饋迴圈」——定期訪談忠實用戶找出最具說服力的使用場景，將其轉化為產品開發的優先排序依據。"
        product_energy = "方位能量分布均衡，產品迭代應以用戶反饋為主要驅動力"

    # ── Price ──
    if 地_val > 1.5 and household_income > 600:
        price_current = "定價尚未充分反映市場的消費力上限"
        price_rec = "可採「精品定價策略」——比對標市場高 20-30%，搭配明確的優質服務承諾（如無問題保證、專屬顧問服務）。高定價反而能過濾「錯誤客戶」，提升服務品質一致性。"
        price_energy = f"地能量 {地_val:+.1f} × 家戶所得 NT${household_income:.0f}K：消費力充裕，精品定價空間成立"
    elif 地_val < -1.0 or household_income < 400:
        price_current = "現有定價對部分目標客群可能形成門檻"
        price_rec = "設計「零風險進入方案」——免費體驗課、付費試用期（30 天退款保證），將首次採用的心理成本降至最低。方案分層：入門版→完整版→進階版，給客戶自主升級路徑。"
        price_energy = f"地能量 {地_val:.1f}：消費承載力偏弱，需以低門檻方案驅動首次試用"
    else:
        price_current = "定價結構尚在市場接受範圍內"
        price_rec = "建議測試「結果導向定價」——以客戶的成果指標作為部分收費基礎，降低潛客的財務風險感知，同時強化服務提供方的交付承諾。"
        price_energy = "能量配置適中，定價策略應兼顧進入門檻與品牌溢價"

    # ── Place ──
    if population_density > 15000:
        place_current = "地點選擇集中於高人流核心商圈"
        place_rec = "在核心據點之外，建立「衛星接觸點」策略——在目標客群日常聚集的場所（共同工作空間、健身房、特定餐廳）設立無壓力的品牌接觸機會，以降低首次相遇的距離感。"
        place_energy = f"人口密度 {population_density:,}：高密度環境需要更細緻的分層接觸策略"
    elif combined.get("水", 0) > 1.5:
        place_current = "服務交付主要依賴固定場地"
        place_rec = "在固定據點外增加「關係型接觸」——定期的小型私人聚會、一對一深度諮詢，利用水能量的關係紐帶力創造高信任的場域。"
        place_energy = f"水能量 {水_val:+.1f}：關係型接觸比廣播型接觸更能觸動客群"
    else:
        place_current = "通路結構以直接銷售為主"
        place_rec = "考慮增加「戰略合作通路」——與目標客群高度重疊的非競爭品牌建立互推協議，用他人的信任背書降低自己的獲客成本。"
        place_energy = "通路策略應兼顧直銷效率與合作夥伴背書效果"

    # ── Promotion ──
    if 澤_val > 2.0:
        promo_current = "以廣告投放為主要獲客管道"
        promo_rec = "轉向「口碑飛輪策略」：精選 10-15 位具有社群影響力的忠實用戶，為其提供專屬的品牌大使方案（獨家優惠＋共同行銷機會），以 UGC 和 KOL 口碑取代高成本廣告採購。"
        promo_energy = f"澤能量 {澤_val:+.1f}：口碑傳播 ROI 將顯著高於廣告投放"
    elif 雷_val > 1.5:
        promo_current = "品牌知名度尚在建立初期"
        promo_rec = "以「知識型行銷」為主軸——打造深度長文、Podcast 系列或線上工作坊，在目標客群中建立「這個領域最值得信賴的聲音」的地位。知識輸出是雷能量市場最高效的信任建立工具。"
        promo_energy = f"雷能量 {雷_val:+.1f}：深度內容行銷效率遠高於廣告型推廣"
    elif 風_val > 1.5:
        promo_current = "行銷策略以單向傳播為主"
        promo_rec = "轉向「合作行銷矩陣」——與互補性品牌、意見領袖和行業組織建立系統性的互推關係，借助風能量的溝通穿透力快速擴大觸達範圍，同時分攤行銷成本。"
        promo_energy = f"風能量 {風_val:+.1f}：異業合作與聯名是高效的低成本獲客路徑"
    else:
        promo_current = "推廣策略尚無明確主軸"
        promo_rec = "建議先執行「80/20 行銷聚焦」——將 80% 的行銷預算集中在一個最有可能產生口碑效應的主推管道，跑滿 13 週取得足夠數據後再決定是否擴展管道矩陣。"
        promo_energy = "行銷資源應集中投入而非分散試探，單點突破後再擴展"

    return {
        "product": {
            "current": product_current,
            "recommendation": product_rec,
            "energy_basis": product_energy,
        },
        "price": {
            "current": price_current,
            "recommendation": price_rec,
            "energy_basis": price_energy,
        },
        "place": {
            "current": place_current,
            "recommendation": place_rec,
            "energy_basis": place_energy,
        },
        "promotion": {
            "current": promo_current,
            "recommendation": promo_rec,
            "energy_basis": promo_energy,
        },
    }


# ──────────────────────────────────────────────────────────────
# 五、分階段行動計畫
# ──────────────────────────────────────────────────────────────

def _gen_action_plan(
    combined: dict,
    final_state: dict,
    snapshots: list,
    indicators: dict,
    diagnosis: dict,
) -> list[dict]:
    verdict = diagnosis.get("verdict", "需調整")
    loyal_ratio = final_state.get("loyal", {}).get("ratio", 0.0)
    considering_ratio = final_state.get("considering", {}).get("ratio", 0.0)
    chasm_crossed = loyal_ratio >= _CHASM_THRESHOLD

    top_primal = max(combined, key=combined.get) if combined else "澤"
    household_income = indicators.get("household_income", 0)

    plan = []

    # ── Q1：認知建立期 ──
    q1_actions = [
        {
            "action": f"啟動「{top_primal}能量」市場進入計畫——以市場主導方位設計品牌登場方式（若澤高則以快閃體驗活動；若天高則以高端沙龍；若山高則以深度內容），建立強烈的第一印象",
            "expected_impact": "目標 13 週後認知率 ≥ 20%",
            "resources": "預算：40%，人力：2 人全時",
            "kpi": "品牌認知率（aware）≥ 20%",
        },
        {
            "action": "招募「創始會員計畫」——設計 30-50 名限額的特殊創始身份（獨家優惠 + 命名機會），篩選出最熱情的早期採用者作為種子社群",
            "expected_impact": "建立核心早期使用者圈層，為鴻溝跨越儲備口碑動能",
            "resources": "預算：15%，需 1 人專職管理社群關係",
            "kpi": "招募 30-50 名創始會員，NPS ≥ 60",
        },
        {
            "action": "建立轉換漏斗追蹤——從曝光→認知→考慮→決策的每一個環節設置追蹤指標，每兩週回顧一次數據找出最大漏水口",
            "expected_impact": "識別轉換效率最低的環節，集中改善以提升整體漏斗效率",
            "resources": "預算：5%，每兩週 2 小時分析時間",
            "kpi": "建立追蹤儀表板，從認知到考慮的轉換率 ≥ 30%",
        },
    ]

    plan.append({
        "phase": "Q1：認知建立期（第 1-13 週）",
        "objective": f"以「{top_primal}」能量為錨點建立品牌認知，招募核心種子社群，並架設數據追蹤基礎設施",
        "actions": q1_actions,
        "budget_allocation": "總預算的 35%，重心在曝光與早期社群建設",
    })

    # ── Q2：早期滲透期 ──
    q2_actions = [
        {
            "action": "啟動「首批成功案例計畫」——深度服務 10 名早期採用者，記錄完整的使用歷程與成果數字，產出 3-5 個可對外分享的精華案例（含影片見證或書面深訪）",
            "expected_impact": "案例將成為後續觀望族群最有力的社會認同觸媒，預計提升 25-40% 的考慮→決策轉換率",
            "resources": "預算：20%（包括案例製作費），1 人負責案例管理",
            "kpi": "完成 5 個以上有量化成果的客戶案例；考慮→決策轉換率 ≥ 20%",
        },
        {
            "action": f"{'設計「帶朋友來」口碑激勵計畫' if combined.get('澤', 0) > 1.5 else '建立合作夥伴轉介紹管道'}——給予現有客戶有吸引力的推薦獎勵，將口碑動能轉化為系統性獲客",
            "expected_impact": "口碑轉介紹成本通常比廣告獲客低 60-80%，且轉換率更高",
            "resources": "預算：10%（推薦獎勵成本），無需額外人力",
            "kpi": "口碑轉介紹佔總新增客戶比例 ≥ 20%",
        },
        {
            "action": f"{'降低觀望族群試用門檻' if considering_ratio > 0.25 else '強化決策轉換 CTA 設計'}——針對觀望族群設計「零風險試用方案」，以降低首次採用的心理門檻",
            "expected_impact": f"當前觀望比例 {considering_ratio * 100:.0f}%，若轉換提升 30% 可顯著加速採用率",
            "resources": "預算：5%（試用成本），設計改版 1 週",
            "kpi": "觀望→決策轉換率提升 25% 以上",
        },
    ]

    plan.append({
        "phase": "Q2：早期滲透期（第 14-26 週）",
        "objective": "以成功案例建立社會認同，啟動口碑轉介紹引擎，突破觀望族群的採用心理門檻",
        "actions": q2_actions,
        "budget_allocation": "總預算的 30%，重心在案例建設與口碑機制",
    })

    # ── Q3：鴻溝跨越期 ──
    q3_focus = "全力衝刺鴻溝突破" if not chasm_crossed else "加速鴻溝後的擴散動能"
    q3_actions = [
        {
            "action": f"{'聚焦一個垂直市場的鴻溝突破策略' if not chasm_crossed else '啟動第二圈層擴散計畫'}——{'選定一個最容易突破的客群垂直市場（如特定職業、生活圈），集中資源做到「這個圈子幾乎人人知道我們」' if not chasm_crossed else '以鴻溝後的忠實客戶為中心，向其社交圈第二圈層主動擴展，利用已建立的信任光環加速傳播'}",
            "expected_impact": f"{'成功突破鴻溝（忠實用戶 ≥ 16%），啟動自我擴散動能' if not chasm_crossed else '在現有採用率基礎上加速 1.5x 增長速度'}",
            "resources": "預算：30%，需全力投入",
            "kpi": f"{'第 39 週達到忠實用戶 ≥ 16%' if not chasm_crossed else '第 39 週採用率較 Q2 末提升 50%'}",
        },
        {
            "action": "建立「品牌大使生態系」——正式招募 5-10 位最活躍的忠實客戶成為有組織的品牌大使，提供他們獨家資訊、發言平台和合理的激勵，讓其成為持續產出社群內容的引擎",
            "expected_impact": "品牌大使的影響力可達普通廣告的 5-7 倍，且可持續數月自主運作",
            "resources": "預算：10%（含大使激勵費用），1 人兼職管理",
            "kpi": "5 名以上品牌大使每月產出 2 篇以上有機內容，觸及 5 倍於追蹤者的潛在客群",
        },
    ]

    plan.append({
        "phase": "Q3：鴻溝跨越期（第 27-39 週）",
        "objective": f"{'全力突破 Rogers 鴻溝門檻（16%），將策略從早期採用者推入主流市場' if not chasm_crossed else '加速鴻溝後的主流市場滲透，建立品牌大使生態系'}",
        "actions": q3_actions,
        "budget_allocation": "總預算的 25%，集中在鴻溝突破的關鍵催化劑",
    })

    # ── Q4：規模化鞏固期 ──
    q4_actions = [
        {
            "action": f"{'啟動地理複製計畫' if loyal_ratio >= _CHASM_THRESHOLD else '深化忠誠度鞏固現有基盤'}——{'以本區域驗證的成功策略模板，快速複製到相鄰行政區，預計複製成本比初次進入低 40%' if loyal_ratio >= _CHASM_THRESHOLD else '聚焦服務現有客戶，提升 LTV，以現金流支撐明年的鴻溝突破行動'}",
            "expected_impact": f"{'6 個月內新增 1-2 個覆蓋市場' if loyal_ratio >= _CHASM_THRESHOLD else '提升忠實客戶 LTV 20%，為下一輪增長儲備資源'}",
            "resources": f"{'預算：30%（新市場啟動）' if loyal_ratio >= _CHASM_THRESHOLD else '預算：15%，重心在現有客戶深化'}",
            "kpi": f"{'新市場在 13 週內達到 5% 認知覆蓋' if loyal_ratio >= _CHASM_THRESHOLD else '忠實客戶 Churn Rate ≤ 5%，NPS 維持 ≥ 60'}",
        },
        {
            "action": "建立年度策略回顧機制——彙整全年數據（各管道 CAC、LTV、NPS、口碑轉介紹率），與 Bass 模擬數據對比，提取策略教訓並更新下一年模擬參數",
            "expected_impact": "將本年度的試錯成本轉化為明年的精準決策資本",
            "resources": "預算：2%，1 週分析時間",
            "kpi": "完成年度策略報告，識別 3 個以上可量化改進的策略槓桿點",
        },
    ]

    plan.append({
        "phase": "Q4：規模化鞏固期（第 40-52 週）",
        "objective": f"{'在現有市場基盤上啟動規模化複製，開拓下一個地理市場' if loyal_ratio >= _CHASM_THRESHOLD else '深化現有市場忠誠度，完善策略數據，為下一輪增長奠定基礎'}",
        "actions": q4_actions,
        "budget_allocation": "總預算的 10%（以前三季度投入換取 Q4 的規模化收益）",
    })

    return plan


# ──────────────────────────────────────────────────────────────
# 六、風險矩陣
# ──────────────────────────────────────────────────────────────

def _gen_risk_matrix(
    combined: dict,
    final_state: dict,
    coverage: dict,
    indicators: dict,
    snapshots: list,
) -> list[dict]:
    risks = []

    loyal_ratio = final_state.get("loyal", {}).get("ratio", 0.0)
    considering_ratio = final_state.get("considering", {}).get("ratio", 0.0)
    resistant_ratio = final_state.get("resistant", {}).get("ratio", 0.0)
    coverage_pct = coverage.get("coverage_pct", 100.0)

    # ── 風險 1：鴻溝陷阱 ──
    if loyal_ratio < _CHASM_THRESHOLD:
        risks.append({
            "risk": "鴻溝陷阱——早期採用者熱度消退但主流市場未接棒",
            "probability": "高" if loyal_ratio < 0.08 else "中",
            "impact": "高",
            "quadrant": "critical",
            "mitigation": (
                "在 Q3 鎖定一個垂直利基市場全力突破（而非廣泛散射），"
                "集中打造 5 個具說服力的主流市場成功案例，"
                "讓早期多數看到「跟自己類似的人已成功採用」的社會認同信號。"
            ),
        })

    # ── 風險 2：觀望族群流失 ──
    if considering_ratio > 0.20:
        risks.append({
            "risk": f"高比例觀望族群（{considering_ratio * 100:.0f}%）最終決策為不採用",
            "probability": "中",
            "impact": "高",
            "quadrant": "critical",
            "mitigation": (
                "設計「限時歸零方案」——給予觀望族群一個有截止日期的特惠進入機會，"
                "配合真實的稀缺性（名額限制）製造決策急迫感，"
                "預計可轉化 20-30% 的長期觀望者。"
            ),
        })

    # ── 風險 3：負向口碑擴散 ──
    if resistant_ratio > 0.03:
        risks.append({
            "risk": f"抵制族群（{resistant_ratio * 100:.0f}%）在社群中主動散播負向口碑",
            "probability": "中" if resistant_ratio < 0.06 else "高",
            "impact": "高",
            "quadrant": "critical" if resistant_ratio > 0.06 else "monitor",
            "mitigation": (
                "立即進行「抵制根因調查」——深訪 3-5 位抵制者了解核心不滿，"
                "若是溝通誤解可透過個案溝通修復；若是產品缺陷需優先修復並公開改善聲明，"
                "讓潛在抵制者看到品牌的回應誠意。"
            ),
        })

    # ── 風險 4：能量缺口導致策略推進受阻 ──
    weak_primals = [(p, v) for p, v in combined.items() if v <= -1.5]
    if weak_primals:
        worst = min(weak_primals, key=lambda x: x[1])
        risks.append({
            "risk": f"「{worst[0]}」能量嚴重不足（{worst[1]:.1f}），策略核心方位受阻",
            "probability": "高",
            "impact": "中",
            "quadrant": "monitor",
            "mitigation": (
                f"迴避在「{worst[0]}」方位上直接對抗，改以優勢方位（"
                f"{max(combined, key=combined.get)}）為主軸設計策略，"
                f"弱勢方位以合作夥伴或外部資源補位，而非試圖在短期內改變市場能量結構。"
            ),
        })

    # ── 風險 5：數據覆蓋不足導致決策失準 ──
    if coverage_pct < 60.0:
        risks.append({
            "risk": f"能量分析數據覆蓋率不足（{coverage_pct:.0f}%），模擬結果可能偏離真實市場",
            "probability": "中",
            "impact": "中",
            "quadrant": "prepare",
            "mitigation": (
                f"投入 2 週進行「田野數據補充」——針對缺失的 {100 - coverage_pct:.0f}% 指標，"
                "設計焦點座談或街頭訪談收集一手數據，"
                "優先補充對能量向量影響最大的前 3 個缺失指標。"
            ),
        })

    # ── 風險 6：競爭者跟進複製 ──
    cafe_density = indicators.get("cafe_density", 0)
    if cafe_density > 0.8 or combined.get("天", 0) > 2.0:
        risks.append({
            "risk": "競爭者在鴻溝突破期前後快速跟進，壓縮品牌的差異化空間",
            "probability": "中",
            "impact": "中",
            "quadrant": "prepare",
            "mitigation": (
                "在鴻溝突破前，優先完成「品牌護城河建設」——"
                "建立只有你擁有的資產（客戶故事資料庫、專屬社群、獨特的服務交付體驗），"
                "讓競爭者即使複製策略，也無法複製你的品牌資產。"
            ),
        })

    # ── 風險 7：增長停滯在飽和點之前 ──
    if snapshots:
        last_snap = snapshots[-1]
        prev_snap = snapshots[-5] if len(snapshots) > 5 else snapshots[0]
        last_pct = sum(_get_snap_dist(last_snap).get(k, 0) for k in ("decided", "loyal"))
        prev_pct = sum(_get_snap_dist(prev_snap).get(k, 0) for k in ("decided", "loyal"))
        if last_pct - prev_pct < 0.02 and last_pct < 0.30:
            risks.append({
                "risk": "增長動能提前趨緩，採用率卡在飽和點之前（增長停滯於低水平）",
                "probability": "中",
                "impact": "高",
                "quadrant": "critical",
                "mitigation": (
                    "診斷增長停滯的根本原因——是市場教育不足（awareness 天花板）、"
                    "轉換阻力（considering 堆積）、還是口碑缺口（loyal 增長停滯）？"
                    "針對最大的漏水口設計針對性介入，而非在全漏斗加大預算。"
                ),
            })

    # 按影響力排序
    quadrant_order = {"critical": 0, "monitor": 1, "prepare": 2, "accept": 3}
    risks.sort(key=lambda r: quadrant_order.get(r["quadrant"], 3))

    return risks
