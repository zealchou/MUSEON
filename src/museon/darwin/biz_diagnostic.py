"""
biz-diagnostic 參數轉換器

將商業模式健檢的回答轉換為 DARWIN 模擬參數（strategy_brief）。
"""

import re


def convert_to_strategy_brief(
    answers: dict,           # 健檢問答 raw_answers
    diagnosis: dict | None = None,  # 診斷結果（如果有）
) -> dict:
    """
    從健檢回答轉換為 strategy_brief JSON。

    answers 結構：
    {
        "product_description": str,   # Q1
        "customer_outcome": str,      # Q2
        "acquisition_channel": str,   # Q3
        "conversion_bottleneck": str, # Q4
        "win_reason": str,            # Q5
        "delivery_process": str,      # Q6
        "repurchase_referral": str,   # Q7
        "partnerships": str,          # Q8
        "pricing_objection": str,     # Q9
        "priority_problem": str,      # Q10
        "marketing_budget_channel": str,  # Q11（新增）
        "price_point": str,           # Q12（新增）
        "existing_audience": str,     # Q13（新增）
    }

    Returns:
        strategy_brief JSON — 可直接傳給 DARWIN 模擬引擎
    """
    product_description = answers.get("product_description", "")
    repurchase_referral  = answers.get("repurchase_referral", "")
    marketing_budget_channel = answers.get("marketing_budget_channel", "")
    price_point_text     = answers.get("price_point", "")
    existing_audience    = answers.get("existing_audience", "")
    conversion_bottleneck = answers.get("conversion_bottleneck", "")
    win_reason           = answers.get("win_reason", "")

    # ----- 基礎推斷 -----
    product_type  = infer_product_type(product_description)
    price         = parse_price_point(price_point_text) if price_point_text else parse_price_point(
        answers.get("pricing_objection", "500")
    )
    trial_barrier = price_to_trial_barrier(price)
    budget, channels = parse_marketing_budget(marketing_budget_channel)
    awareness_speed  = budget_to_awareness_speed(budget)
    q_multiplier     = parse_repurchase(repurchase_referral)
    initial_aware    = parse_existing_audience(existing_audience)

    # ----- 風險指數（從診斷結果或預設） -----
    overall_risk = 40  # 預設中等風險
    if diagnosis:
        overall_risk = diagnosis.get("overall_risk", 40)
    resistance_rate = risk_to_resistance_rate(overall_risk)

    # ----- 轉換瓶頸 → conversion_rate 調整 -----
    base_conversion = _infer_conversion_rate(conversion_bottleneck, product_type)

    # ----- 勝出原因 → brand_strength -----
    brand_strength = _infer_brand_strength(win_reason)

    # ----- 組裝 strategy_brief -----
    brief = {
        "product": {
            "type": product_type,
            "description": product_description,
            "price_point": price,
            "brand_strength": brand_strength,
        },
        "simulation_params": {
            "awareness_speed": awareness_speed,
            "trial_barrier": trial_barrier,
            "conversion_rate": base_conversion,
            "q_multiplier_boost": q_multiplier,
            "resistance_rate": resistance_rate,
            "initial_aware_pct": initial_aware,
        },
        "channels": {
            "primary_primals": channels,
            "monthly_budget": budget,
        },
        "diagnostic_meta": {
            "priority_problem": answers.get("priority_problem", ""),
            "delivery_process": answers.get("delivery_process", ""),
            "partnerships": answers.get("partnerships", ""),
            "customer_outcome": answers.get("customer_outcome", ""),
            "acquisition_channel": answers.get("acquisition_channel", ""),
            "overall_risk": overall_risk,
        },
    }

    return brief


# ─────────────────────────────────────────────────────────
# 子函數
# ─────────────────────────────────────────────────────────

def infer_product_type(description: str) -> str:
    """從產品描述推斷品類"""
    keywords = {
        "cafe": ["咖啡", "飲料", "餐廳", "小吃", "餐飲", "美食", "甜點", "早午餐", "brunch"],
        "beauty": ["美容", "美甲", "美髮", "SPA", "按摩", "沙龍", "護膚", "美業"],
        "b2b_saas": ["SaaS", "軟體", "平台", "系統", "API", "雲端", "B2B", "訂閱"],
        "education": ["課程", "教學", "培訓", "工作坊", "教練", "諮詢", "身心靈", "療癒"],
        "manufacturing": ["工廠", "製造", "生產", "代工", "OEM", "零件"],
        "retail": ["零售", "電商", "網購", "實體店", "選物", "服飾"],
        "consulting": ["顧問", "諮詢", "策略", "企管", "輔導"],
    }
    desc_lower = description.lower()
    for ptype, kws in keywords.items():
        for kw in kws:
            if kw in desc_lower or kw.lower() in desc_lower:
                return ptype
    return "retail"  # 預設


def parse_price_point(text: str) -> float:
    """從文字描述提取價格"""
    numbers = re.findall(r'[\d]+', text.replace(',', ''))
    if numbers:
        return float(numbers[0])
    return 500.0  # 預設


def price_to_trial_barrier(price: float) -> float:
    """定價 → trial_barrier"""
    if price < 100:   return 0.05
    if price < 500:   return 0.15
    if price < 2000:  return 0.35
    if price < 10000: return 0.55
    return 0.75


def parse_marketing_budget(text: str) -> tuple:
    """從文字描述提取月行銷預算和管道"""
    # 先嘗試匹配「X 萬」或「X萬」格式
    wan_match = re.search(r'([\d]+(?:\.\d+)?)\s*萬', text)
    if wan_match:
        budget = float(wan_match.group(1)) * 10000
    else:
        numbers = re.findall(r'[\d]+', text.replace(',', ''))
        budget = float(numbers[0]) if numbers else 30000.0

    channel_map = {
        "ig": "澤", "instagram": "澤", "tiktok": "澤",
        "line": "風", "email": "風",
        "google": "天", "廣告": "天",
        "活動": "風", "實體": "風",
        "kol": "澤", "網紅": "澤",
        "內容": "雷", "部落格": "雷", "podcast": "雷",
        "seo": "天",
    }
    primals = set()
    text_lower = text.lower()
    for keyword, primal in channel_map.items():
        if keyword in text_lower:
            primals.add(primal)

    return budget, list(primals) if primals else ["澤"]


def budget_to_awareness_speed(budget: float) -> float:
    """月行銷預算 → awareness_speed"""
    if budget < 10000:  return 0.5
    if budget < 50000:  return 1.0
    if budget < 200000: return 1.5
    return 2.0


def parse_repurchase(text: str) -> float:
    """從回購/介紹描述推斷 q_multiplier_boost"""
    positive_words = ["常", "很多", "都會", "經常", "高", "不錯", "口碑"]
    negative_words = ["很少", "不太", "沒有", "低", "幾乎不"]

    for w in positive_words:
        if w in text:
            return 1.5
    for w in negative_words:
        if w in text:
            return 0.8
    return 1.2  # 中等


def parse_existing_audience(text: str) -> float:
    """從既有客群描述推斷 initial_aware_pct"""
    # 先嘗試提取數字（優先於關鍵字判斷）
    numbers = re.findall(r'[\d]+', text.replace(',', ''))
    if numbers:
        count = float(max(numbers, key=lambda x: float(x)))  # 取最大值
        if count < 100:  return 0.01
        if count < 1000: return 0.03
        if count < 5000: return 0.05
        return 0.08

    # 無數字時用關鍵字判斷
    if "沒有" in text or "零" in text:
        return 0.0
    return 0.01


def risk_to_resistance_rate(overall_risk: int) -> float:
    """風險指數 → resistance_rate"""
    if overall_risk > 70: return 0.015
    if overall_risk > 40: return 0.008
    return 0.003


# ─────────────────────────────────────────────────────────
# 私有輔助函數
# ─────────────────────────────────────────────────────────

def _infer_conversion_rate(bottleneck_text: str, product_type: str) -> float:
    """轉換瓶頸文字 → base_conversion_rate"""
    default_by_type = {
        "cafe": 0.35,
        "beauty": 0.40,
        "b2b_saas": 0.15,
        "education": 0.25,
        "manufacturing": 0.30,
        "retail": 0.30,
        "consulting": 0.20,
    }
    base = default_by_type.get(product_type, 0.30)

    # 轉換瓶頸關鍵字 → 下調
    friction_words = ["太貴", "價格", "走了", "猶豫", "慢", "等", "複雜"]
    for w in friction_words:
        if w in bottleneck_text:
            base *= 0.8
            break

    return round(max(0.05, min(0.9, base)), 2)


def _infer_brand_strength(win_reason_text: str) -> float:
    """勝出原因 → brand_strength（0~1）"""
    strong_words = ["好喝", "好吃", "好用", "最好", "口碑", "推薦", "愛", "忠實"]
    weak_words = ["便宜", "方便", "地點", "剛好", "湊合"]

    for w in strong_words:
        if w in win_reason_text:
            return 0.75
    for w in weak_words:
        if w in win_reason_text:
            return 0.40
    return 0.55  # 預設中等
