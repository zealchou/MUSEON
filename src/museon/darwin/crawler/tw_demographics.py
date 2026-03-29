"""Market Ares — 台灣人口統計數據爬蟲

數據來源：
- 政府資料開放平台 (data.gov.tw)
- 內政部統計處
- 主計總處
- 財政部稅務統計

第一版：內建台灣主要城市的基準數據（手動整理）
未來版本：串接 API 自動更新
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ═══════════════════════ 台灣基準數據 ═══════════════════════
# 全國平均值（用於正規化計算，來源：2024-2025 年統計）

TAIWAN_BENCHMARKS: dict[str, dict[str, float]] = {
    # ── 天能量指標 ──
    "startup_density": {"min": 0.5, "max": 15.0, "mean": 3.5},     # 每萬人新創公司數
    "outdoor_venue_density": {"min": 0.1, "max": 5.0, "mean": 1.2}, # 每萬人戶外活動場所
    "political_participation": {"min": 0.45, "max": 0.78, "mean": 0.66}, # 投票率
    "volunteer_org_density": {"min": 0.5, "max": 8.0, "mean": 2.5},  # 每萬人志工組織
    "community_group_count": {"min": 1.0, "max": 20.0, "mean": 6.0}, # 每萬人社團數

    # ── 風能量指標 ──
    "sales_job_ratio": {"min": 0.03, "max": 0.15, "mean": 0.08},     # 業務職占比
    "partnership_ratio": {"min": 0.05, "max": 0.30, "mean": 0.12},   # 合夥企業比例
    "business_survival_rate": {"min": 0.40, "max": 0.85, "mean": 0.62}, # 五年存活率
    "marriage_rate": {"min": 3.0, "max": 8.0, "mean": 5.2},          # 千人結婚率
    "mediation_success_rate": {"min": 0.30, "max": 0.75, "mean": 0.55}, # 調解成功率

    # ── 水能量指標 ──
    "household_size": {"min": 2.0, "max": 4.5, "mean": 2.9},         # 戶均人口
    "divorce_rate": {"min": 1.5, "max": 4.0, "mean": 2.3},           # 千人離婚率
    "birth_rate": {"min": 4.0, "max": 12.0, "mean": 6.5},            # 千人出生率
    "care_facility_density": {"min": 0.2, "max": 3.0, "mean": 1.0},  # 每萬人照護機構
    "longterm_care_density": {"min": 0.1, "max": 2.0, "mean": 0.6},  # 每萬人長照設施

    # ── 山能量指標 ──
    "gym_density": {"min": 0.3, "max": 8.0, "mean": 2.5},            # 每萬人健身房
    "fine_dining_density": {"min": 0.1, "max": 5.0, "mean": 1.0},    # 每萬人高檔餐廳
    "religious_venue_density": {"min": 1.0, "max": 15.0, "mean": 5.0}, # 每萬人宗教場所
    "savings_rate": {"min": 0.10, "max": 0.40, "mean": 0.22},        # 儲蓄率
    "insurance_penetration": {"min": 0.60, "max": 0.95, "mean": 0.82}, # 投保率

    # ── 地能量指標 ──
    "household_income": {"min": 400000, "max": 2500000, "mean": 1050000}, # 戶均年所得
    "home_ownership_rate": {"min": 0.45, "max": 0.92, "mean": 0.78}, # 自有率
    "franchise_density": {"min": 0.5, "max": 10.0, "mean": 3.0},     # 每萬人連鎖店
    "population_density": {"min": 50, "max": 30000, "mean": 650},     # 每平方公里人口
    "passive_income_ratio": {"min": 0.02, "max": 0.20, "mean": 0.08}, # 被動收入比

    # ── 雷能量指標 ──
    "wellness_course_density": {"min": 0.05, "max": 3.0, "mean": 0.5}, # 每萬人身心靈課程
    "art_event_count": {"min": 1, "max": 200, "mean": 30},           # 年度藝文活動數
    "subculture_density": {"min": 0.05, "max": 2.0, "mean": 0.3},    # 每萬人次文化據點
    "meditation_search_trend": {"min": 10, "max": 100, "mean": 40},   # Google Trends 指數
    "counseling_density": {"min": 0.1, "max": 3.0, "mean": 0.8},     # 每萬人諮商所

    # ── 火能量指標 ──
    "exhibition_attendance": {"min": 0.05, "max": 0.40, "mean": 0.15}, # 參與率
    "training_enrollment": {"min": 0.02, "max": 0.20, "mean": 0.08},  # 報名率
    "subscription_usage": {"min": 0.10, "max": 0.60, "mean": 0.30},   # 訂閱率
    "research_firm_density": {"min": 0.01, "max": 1.0, "mean": 0.15}, # 每萬人市調公司

    # ── 澤能量指標 ──
    "cafe_density": {"min": 0.5, "max": 15.0, "mean": 4.0},          # 每萬人咖啡廳
    "mall_density": {"min": 0.05, "max": 2.0, "mean": 0.5},          # 每萬人百貨
    "creator_ratio": {"min": 0.001, "max": 0.02, "mean": 0.005},     # 創作者比例
    "social_interaction_rate": {"min": 0.10, "max": 0.60, "mean": 0.30}, # 社群互動率
    "kol_density": {"min": 0.001, "max": 0.01, "mean": 0.003},       # KOL 密度
    "brand_store_density": {"min": 0.5, "max": 8.0, "mean": 2.5},    # 每萬人品牌店
}


# ═══════════════════════ 城市範例數據 ═══════════════════════

CITY_DATA: dict[str, dict[str, float]] = {
    "台南永康": {
        # 天
        "startup_density": 2.8, "outdoor_venue_density": 1.0,
        "political_participation": 0.68, "volunteer_org_density": 3.0,
        "community_group_count": 7.0,
        # 風
        "sales_job_ratio": 0.07, "partnership_ratio": 0.10,
        "business_survival_rate": 0.58, "marriage_rate": 5.0,
        "mediation_success_rate": 0.52,
        # 水
        "household_size": 3.2, "divorce_rate": 2.1, "birth_rate": 6.0,
        "care_facility_density": 0.8, "longterm_care_density": 0.5,
        # 山
        "gym_density": 1.8, "fine_dining_density": 0.6,
        "religious_venue_density": 8.0, "savings_rate": 0.20,
        "insurance_penetration": 0.80,
        # 地
        "household_income": 850000, "home_ownership_rate": 0.82,
        "franchise_density": 3.5, "population_density": 4200,
        "passive_income_ratio": 0.06,
        # 雷
        "wellness_course_density": 0.3, "art_event_count": 15,
        "subculture_density": 0.15, "meditation_search_trend": 30,
        "counseling_density": 0.4,
        # 火
        "exhibition_attendance": 0.10, "training_enrollment": 0.06,
        "subscription_usage": 0.25, "research_firm_density": 0.05,
        # 澤
        "cafe_density": 3.0, "mall_density": 0.3, "creator_ratio": 0.003,
        "social_interaction_rate": 0.25, "kol_density": 0.002,
        "brand_store_density": 2.0,
    },

    "台北信義": {
        # 天
        "startup_density": 12.0, "outdoor_venue_density": 2.5,
        "political_participation": 0.72, "volunteer_org_density": 6.0,
        "community_group_count": 15.0,
        # 風
        "sales_job_ratio": 0.12, "partnership_ratio": 0.22,
        "business_survival_rate": 0.70, "marriage_rate": 4.5,
        "mediation_success_rate": 0.60,
        # 水
        "household_size": 2.4, "divorce_rate": 2.8, "birth_rate": 5.0,
        "care_facility_density": 1.5, "longterm_care_density": 0.8,
        # 山
        "gym_density": 6.0, "fine_dining_density": 4.0,
        "religious_venue_density": 3.0, "savings_rate": 0.28,
        "insurance_penetration": 0.90,
        # 地
        "household_income": 1800000, "home_ownership_rate": 0.55,
        "franchise_density": 8.0, "population_density": 9500,
        "passive_income_ratio": 0.15,
        # 雷
        "wellness_course_density": 2.0, "art_event_count": 150,
        "subculture_density": 1.5, "meditation_search_trend": 75,
        "counseling_density": 2.5,
        # 火
        "exhibition_attendance": 0.30, "training_enrollment": 0.15,
        "subscription_usage": 0.50, "research_firm_density": 0.80,
        # 澤
        "cafe_density": 12.0, "mall_density": 1.5, "creator_ratio": 0.015,
        "social_interaction_rate": 0.50, "kol_density": 0.008,
        "brand_store_density": 7.0,
    },

    "台北市+新北市": {
        # 台北+新北合併數據（人口約 670 萬，全台最大都會區）
        # 混合信義區的高能量和板橋/三重/中和的中低能量
        # 天
        "startup_density": 7.5, "outdoor_venue_density": 1.8,
        "political_participation": 0.70, "volunteer_org_density": 4.5,
        "community_group_count": 10.0,
        # 風
        "sales_job_ratio": 0.10, "partnership_ratio": 0.18,
        "business_survival_rate": 0.63, "marriage_rate": 4.2,
        "mediation_success_rate": 0.58,
        # 水
        "household_size": 2.6, "divorce_rate": 2.6, "birth_rate": 5.2,
        "care_facility_density": 1.2, "longterm_care_density": 0.7,
        # 山
        "gym_density": 3.8, "fine_dining_density": 2.0,
        "religious_venue_density": 4.5, "savings_rate": 0.24,
        "insurance_penetration": 0.86,
        # 地（新北拉低平均，但整體仍高於全國）
        "household_income": 1200000, "home_ownership_rate": 0.65,
        "franchise_density": 6.0, "population_density": 7200,
        "passive_income_ratio": 0.10,
        # 雷
        "wellness_course_density": 1.2, "art_event_count": 80,
        "subculture_density": 0.8, "meditation_search_trend": 55,
        "counseling_density": 1.5,
        # 火
        "exhibition_attendance": 0.20, "training_enrollment": 0.10,
        "subscription_usage": 0.38, "research_firm_density": 0.40,
        # 澤
        "cafe_density": 7.0, "mall_density": 0.8, "creator_ratio": 0.008,
        "social_interaction_rate": 0.38, "kol_density": 0.005,
        "brand_store_density": 4.5,
    },

    "高雄鳳山": {
        # 天
        "startup_density": 2.0, "outdoor_venue_density": 1.5,
        "political_participation": 0.70, "volunteer_org_density": 2.5,
        "community_group_count": 5.5,
        # 風
        "sales_job_ratio": 0.06, "partnership_ratio": 0.08,
        "business_survival_rate": 0.55, "marriage_rate": 5.5,
        "mediation_success_rate": 0.50,
        # 水
        "household_size": 3.0, "divorce_rate": 2.5, "birth_rate": 5.5,
        "care_facility_density": 0.7, "longterm_care_density": 0.4,
        # 山
        "gym_density": 1.5, "fine_dining_density": 0.4,
        "religious_venue_density": 10.0, "savings_rate": 0.18,
        "insurance_penetration": 0.78,
        # 地
        "household_income": 750000, "home_ownership_rate": 0.85,
        "franchise_density": 2.5, "population_density": 6800,
        "passive_income_ratio": 0.05,
        # 雷
        "wellness_course_density": 0.2, "art_event_count": 20,
        "subculture_density": 0.2, "meditation_search_trend": 25,
        "counseling_density": 0.3,
        # 火
        "exhibition_attendance": 0.08, "training_enrollment": 0.05,
        "subscription_usage": 0.20, "research_firm_density": 0.03,
        # 澤
        "cafe_density": 2.5, "mall_density": 0.4, "creator_ratio": 0.002,
        "social_interaction_rate": 0.22, "kol_density": 0.001,
        "brand_store_density": 1.5,
    },
}


def get_city_data(city: str) -> dict[str, float]:
    """取得城市數據"""
    if city not in CITY_DATA:
        available = ", ".join(CITY_DATA.keys())
        raise ValueError(f"城市 '{city}' 不在資料庫中。可用城市：{available}")
    return CITY_DATA[city]


def get_benchmarks() -> dict[str, dict[str, float]]:
    """取得台灣全國基準數據"""
    return TAIWAN_BENCHMARKS


def list_available_cities() -> list[str]:
    """列出可用的城市"""
    return list(CITY_DATA.keys())
