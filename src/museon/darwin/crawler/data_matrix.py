"""
data_matrix.py — DARWIN 數據來源矩陣
系統化追蹤 40 個 indicator 的數據狀態、可用性和缺口。
"""

from typing import Dict, Any, List

# ---------------------------------------------------------------------------
# 產業輪廓：各產業關鍵方位 + 關鍵指標
# ---------------------------------------------------------------------------

INDUSTRY_PROFILES: Dict[str, Dict[str, Any]] = {
    "餐飲": {
        "critical_primals": ["澤", "風", "地"],
        "critical_indicators": [
            "cafe_density",
            "mall_density",
            "population_density",
            "household_income",
        ],
    },
    "美業": {
        "critical_primals": ["澤", "火", "山"],
        "critical_indicators": [
            "brand_store_density",
            "gym_density",
            "household_income",
            "fine_dining_density",
        ],
    },
    "SaaS_B2B": {
        "critical_primals": ["天", "風", "火"],
        "critical_indicators": [
            "startup_density",
            "business_survival_rate",
            "training_enrollment",
            "research_firm_density",
        ],
    },
    "製造業": {
        "critical_primals": ["地", "山", "水"],
        "critical_indicators": [
            "household_income",
            "home_ownership_rate",
            "franchise_density",
            "household_size",
        ],
    },
    "教育_身心靈": {
        "critical_primals": ["雷", "火", "水"],
        "critical_indicators": [
            "counseling_density",
            "wellness_course_density",
            "meditation_search_trend",
            "training_enrollment",
        ],
    },
}

# ---------------------------------------------------------------------------
# 40 個 indicator 的數據狀態字典
# ---------------------------------------------------------------------------

_DATA_STATUS: Dict[str, Dict[str, Any]] = {

    # ===== Available（有真實政府數據）— 8 個 =====

    "population_density": {
        "status": "available",
        "source": "內政部戶政司 open data",
        "source_file": "population_density_113.json",
        "quality": "high",
        "update_freq": "yearly",
        "notes": "直接取用，鄉鎮市區層級",
    },
    "household_income": {
        "status": "available",
        "source": "財政部綜合所得稅統計 / 主計處",
        "source_file": "income_111.csv",
        "quality": "high",
        "update_freq": "yearly",
        "notes": "用鄉鎮市區平均應申報所得",
    },
    "birth_rate": {
        "status": "available",
        "source": "內政部戶政司統計",
        "source_file": "birth_rate_113.csv",
        "quality": "high",
        "update_freq": "yearly",
        "notes": "每千人出生數",
    },
    "divorce_rate": {
        "status": "available",
        "source": "內政部戶政司統計",
        "source_file": "divorce_rate_113.csv",
        "quality": "high",
        "update_freq": "yearly",
        "notes": "每千人離婚對數",
    },
    "marriage_rate": {
        "status": "available",
        "source": "內政部戶政司統計",
        "source_file": "marriage_rate_113.csv",
        "quality": "high",
        "update_freq": "yearly",
        "notes": "每千人結婚對數",
    },
    "household_size": {
        "status": "available",
        "source": "內政部戶政司統計",
        "source_file": "household_size_113.csv",
        "quality": "high",
        "update_freq": "yearly",
        "notes": "每戶平均人口數",
    },
    "home_ownership_rate": {
        "status": "available",
        "source": "內政部不動產資訊平台",
        "source_file": "home_ownership_112.csv",
        "quality": "high",
        "update_freq": "yearly",
        "notes": "自有住宅比率",
    },
    "passive_income_ratio": {
        "status": "available",
        "source": "財政部稅務統計",
        "source_file": "income_111.csv",
        "quality": "medium",
        "update_freq": "yearly",
        "notes": "用租賃+利息+股利所得／總所得估算，非直接統計",
    },

    # ===== Places API（Google Maps POI）— 7 個 =====

    "cafe_density": {
        "status": "places_api",
        "source": "Google Maps Places API",
        "source_file": "places_cache.json",
        "quality": "medium",
        "update_freq": "quarterly",
        "notes": "飽和度指標（0-1），每次查詢上限 20 筆，都會區可能飽和",
    },
    "gym_density": {
        "status": "places_api",
        "source": "Google Maps Places API",
        "source_file": "places_cache.json",
        "quality": "medium",
        "update_freq": "quarterly",
        "notes": "含健身房、瑜珈、武道館等",
    },
    "mall_density": {
        "status": "places_api",
        "source": "Google Maps Places API",
        "source_file": "places_cache.json",
        "quality": "medium",
        "update_freq": "quarterly",
        "notes": "百貨、商場、購物中心",
    },
    "religious_venue_density": {
        "status": "places_api",
        "source": "Google Maps Places API",
        "source_file": "places_cache.json",
        "quality": "medium",
        "update_freq": "quarterly",
        "notes": "廟宇、教堂、清真寺等",
    },
    "fine_dining_density": {
        "status": "places_api",
        "source": "Google Maps Places API",
        "source_file": "places_cache.json",
        "quality": "low",
        "update_freq": "quarterly",
        "notes": "用價位標籤 price_level≥3 篩選，分類不準確",
    },
    "outdoor_venue_density": {
        "status": "places_api",
        "source": "Google Maps Places API",
        "source_file": "places_cache.json",
        "quality": "medium",
        "update_freq": "quarterly",
        "notes": "登山步道、攀岩場、划船等戶外活動場所",
    },
    "brand_store_density": {
        "status": "places_api",
        "source": "Google Maps Places API",
        "source_file": "places_cache.json",
        "quality": "medium",
        "update_freq": "quarterly",
        "notes": "連鎖品牌門市，用 chain stores keyword 查詢",
    },

    # ===== Derived（推導估算）— 5 個 =====

    "savings_rate": {
        "status": "derived",
        "source": "income_111.csv 推導",
        "quality": "low",
        "update_freq": "yearly",
        "notes": "用鄉鎮所得中位數 / 全國中位數近似儲蓄傾向，非實際儲蓄率",
    },
    "insurance_penetration": {
        "status": "derived",
        "source": "保險事業發展中心縣市統計 + 戶籍人口推導",
        "quality": "low",
        "update_freq": "yearly",
        "notes": "縣市層級數字下推鄉鎮，精度低；直接 API 取得縣市層級較可信",
    },
    "counseling_density": {
        "status": "derived",
        "source": "衛福部心理健康司公告機構清單",
        "quality": "medium",
        "update_freq": "yearly",
        "notes": "用機構地址 geocoding 後統計密度，需爬蟲輔助",
    },
    "community_group_count": {
        "status": "derived",
        "source": "內政部社會團體立案查詢系統",
        "quality": "medium",
        "update_freq": "yearly",
        "notes": "需爬蟲抓取 API，地址歸鄉鎮後計密度",
    },
    "franchise_density": {
        "status": "derived",
        "source": "經濟部商業司公司登記 + Google Places 交叉比對",
        "quality": "low",
        "update_freq": "yearly",
        "notes": "無直接政府統計，用連鎖品牌關鍵字比對推估，誤差大",
    },

    # ===== Missing（缺口）— 20 個 =====

    "startup_density": {
        "status": "missing",
        "potential_source": "經濟部商業司公司登記 open data（含設立年份）",
        "priority": "high",
        "effort": "medium",
        "notes": "近 3 年新設公司數 / 人口推算；API 已開放，需解析地址",
    },
    "political_participation": {
        "status": "missing",
        "potential_source": "中央選舉委員會歷次選舉投票率統計",
        "priority": "medium",
        "effort": "low",
        "notes": "中選會有公開 CSV，鄉鎮市區層級，接入容易",
    },
    "volunteer_org_density": {
        "status": "missing",
        "potential_source": "衛福部社會救助及社工司志工管理系統",
        "priority": "low",
        "effort": "high",
        "notes": "需申請開放資料，目前無公開 API",
    },
    "sales_job_ratio": {
        "status": "missing",
        "potential_source": "勞動部勞動統計查詢網（職業別就業人數）",
        "priority": "medium",
        "effort": "medium",
        "notes": "縣市層級有數據，但鄉鎮層級細度不足",
    },
    "partnership_ratio": {
        "status": "missing",
        "potential_source": "經濟部商業司公司登記 API（組織型態欄位）",
        "priority": "medium",
        "effort": "medium",
        "notes": "合夥組織登記有公開資料，需統計比例",
    },
    "business_survival_rate": {
        "status": "missing",
        "potential_source": "經濟部中小企業處存活率報告 / 商業司解散登記",
        "priority": "high",
        "effort": "high",
        "notes": "需用設立年份 + 解散紀錄交叉計算；縣市層級可行，鄉鎮難",
    },
    "mediation_success_rate": {
        "status": "missing",
        "potential_source": "司法院統計年報（鄉鎮市區調解委員會）",
        "priority": "low",
        "effort": "medium",
        "notes": "司法院有公開年報，但需手動解析 PDF 或 Excel",
    },
    "care_facility_density": {
        "status": "missing",
        "potential_source": "衛福部社區照顧關懷據點公開資料",
        "priority": "medium",
        "effort": "low",
        "notes": "衛福部有公開 CSV 清單，geocoding 後可計密度",
    },
    "longterm_care_density": {
        "status": "missing",
        "potential_source": "衛福部長照機構評鑑名冊",
        "priority": "medium",
        "effort": "low",
        "notes": "衛福部有公開清單，可直接取用地址計密度",
    },
    "wellness_course_density": {
        "status": "missing",
        "potential_source": "Google Maps Places API + Accupass 活動爬蟲",
        "priority": "high",
        "effort": "high",
        "notes": "無政府統計，需多源合併：Google Places + 活動平台爬蟲",
    },
    "art_event_count": {
        "status": "missing",
        "potential_source": "文化部藝文活動資訊系統 open data",
        "priority": "medium",
        "effort": "low",
        "notes": "文化部有 API，可按地區統計年度活動場次",
    },
    "subculture_density": {
        "status": "missing",
        "potential_source": "Google Maps Places API（刺青店、獨立書店、二手唱片行等）",
        "priority": "low",
        "effort": "medium",
        "notes": "需多個 keyword 組合查詢，分類主觀性高",
    },
    "meditation_search_trend": {
        "status": "missing",
        "potential_source": "Google Trends API（非官方 pytrends）",
        "priority": "medium",
        "effort": "medium",
        "notes": "只有縣市層級，鄉鎮細度不足；可作補充指標",
    },
    "exhibition_attendance": {
        "status": "missing",
        "potential_source": "文化部文化統計 / 各館所售票平台",
        "priority": "low",
        "effort": "high",
        "notes": "無統一 API，售票平台（Kktix/Accupass）需爬蟲",
    },
    "training_enrollment": {
        "status": "missing",
        "potential_source": "勞動部 ilearn 訓練平台統計 / 職訓局年報",
        "priority": "high",
        "effort": "medium",
        "notes": "勞動部有公開統計，含縣市別報名數據",
    },
    "subscription_usage": {
        "status": "missing",
        "potential_source": "產業調查報告估算（無公開政府統計）",
        "priority": "low",
        "effort": "high",
        "notes": "無法從政府數據直接取得；可用替代指標（電商活躍度）",
    },
    "research_firm_density": {
        "status": "missing",
        "potential_source": "經濟部商業司公司登記（行業代碼 7320）",
        "priority": "medium",
        "effort": "medium",
        "notes": "市場研究業 ISIC 7320，商業司 API 可按行業代碼查詢",
    },
    "creator_ratio": {
        "status": "missing",
        "potential_source": "社群平台 API 估算（YouTube/Instagram）",
        "priority": "medium",
        "effort": "high",
        "notes": "無官方統計，社群 API 地區數據不精確到鄉鎮",
    },
    "social_interaction_rate": {
        "status": "missing",
        "potential_source": "社群平台 API（Facebook Graph API / IG API）",
        "priority": "medium",
        "effort": "high",
        "notes": "地理層級限縣市；隱私政策限制日益嚴格",
    },
    "kol_density": {
        "status": "missing",
        "potential_source": "KOL 資料庫平台（DailyView、Influenxio 等）",
        "priority": "low",
        "effort": "high",
        "notes": "商業資料庫，需付費或爬蟲；無政府統計",
    },
}


# ---------------------------------------------------------------------------
# 公開函數
# ---------------------------------------------------------------------------

def get_data_status() -> Dict[str, Dict[str, Any]]:
    """
    回傳所有 40 個 indicator 的數據狀態。

    Returns:
        dict: {indicator_name: {status, source, quality, ...}}
    """
    return dict(_DATA_STATUS)


def get_industry_readiness(industry: str) -> Dict[str, Any]:
    """
    評估某產業的數據準備度。

    Args:
        industry: 產業名稱（需在 INDUSTRY_PROFILES 中）

    Returns:
        dict: 包含 readiness_pct、missing_critical、recommendation 等欄位
    """
    if industry not in INDUSTRY_PROFILES:
        raise ValueError(
            f"未知產業 '{industry}'，可用產業：{list(INDUSTRY_PROFILES.keys())}"
        )

    profile = INDUSTRY_PROFILES[industry]
    critical: List[str] = profile["critical_indicators"]

    # 判斷「可用」= available 或 places_api 或 derived（有推導數據）
    USABLE_STATUSES = {"available", "places_api", "derived"}

    available_critical = [
        ind for ind in critical
        if _DATA_STATUS.get(ind, {}).get("status") in USABLE_STATUSES
    ]
    missing_critical = [
        ind for ind in critical
        if _DATA_STATUS.get(ind, {}).get("status") not in USABLE_STATUSES
    ]

    available_count = len(available_critical)
    total_critical = len(critical)
    readiness_pct = (available_count / total_critical * 100) if total_critical > 0 else 0.0

    if readiness_pct >= 100:
        recommendation = "所有關鍵指標已就位，可直接進行分析"
    elif readiness_pct >= 75:
        recommendation = f"建議補齊：{', '.join(missing_critical)}，以提升分析精度"
    elif readiness_pct >= 50:
        recommendation = f"缺口影響顯著，優先補齊：{', '.join(missing_critical)}"
    else:
        recommendation = (
            f"數據準備度不足，建議暫緩此產業分析，先補齊：{', '.join(missing_critical)}"
        )

    return {
        "industry": industry,
        "critical_primals": profile["critical_primals"],
        "critical_indicators": critical,
        "available_count": available_count,
        "total_critical": total_critical,
        "readiness_pct": round(readiness_pct, 1),
        "missing_critical": missing_critical,
        "recommendation": recommendation,
    }


def get_gap_report() -> Dict[str, Any]:
    """
    產出完整的缺口報告：哪些 indicator 缺、可以從哪裡補。

    Returns:
        dict: 包含 total、各狀態計數、missing_by_priority、next_actions
    """
    status_counts: Dict[str, int] = {
        "available": 0,
        "places_api": 0,
        "derived": 0,
        "missing": 0,
    }
    missing_by_priority: Dict[str, List[str]] = {
        "high": [],
        "medium": [],
        "low": [],
    }
    next_actions: List[Dict[str, str]] = []

    # 計算各產業對 missing indicators 的需求次數（用於計算 priority）
    industry_need_count: Dict[str, int] = {}
    for profile in INDUSTRY_PROFILES.values():
        for ind in profile["critical_indicators"]:
            industry_need_count[ind] = industry_need_count.get(ind, 0) + 1

    for name, info in _DATA_STATUS.items():
        st = info.get("status", "missing")
        if st in status_counts:
            status_counts[st] += 1
        else:
            status_counts["missing"] += 1

        if st == "missing":
            # 優先級：indicator 本身標注的 priority
            priority = info.get("priority", "low")
            missing_by_priority[priority].append(name)

            next_actions.append({
                "indicator": name,
                "action": info.get("potential_source", "未知來源"),
                "effort": info.get("effort", "unknown"),
                "priority": priority,
                "notes": info.get("notes", ""),
            })

    # 依 priority 再依 indicator 出現在產業輪廓的次數排序
    for priority_level in missing_by_priority:
        missing_by_priority[priority_level].sort(
            key=lambda x: industry_need_count.get(x, 0), reverse=True
        )

    # next_actions 按 priority 和 effort 排序（high first, low effort first）
    priority_order = {"high": 0, "medium": 1, "low": 2}
    effort_order = {"low": 0, "medium": 1, "high": 2, "unknown": 3}
    next_actions.sort(
        key=lambda x: (
            priority_order.get(x["priority"], 9),
            effort_order.get(x["effort"], 9),
        )
    )

    total = len(_DATA_STATUS)

    return {
        "total": total,
        "available": status_counts["available"],
        "derived": status_counts["derived"],
        "places_api": status_counts["places_api"],
        "missing": status_counts["missing"],
        "missing_by_priority": missing_by_priority,
        "next_actions": next_actions,
    }


# ---------------------------------------------------------------------------
# 快速健全檢查
# ---------------------------------------------------------------------------

def _sanity_check() -> None:
    """驗證 indicator 數量與各分類是否符合預期。"""
    status = get_data_status()
    total = len(status)
    by_status: Dict[str, int] = {}
    for info in status.values():
        st = info.get("status", "unknown")
        by_status[st] = by_status.get(st, 0) + 1

    print(f"Total indicators   : {total}")
    for st, count in sorted(by_status.items()):
        print(f"  {st:<15}: {count}")

    gap = get_gap_report()
    print(f"\nGap report:")
    print(f"  missing total    : {gap['missing']}")
    print(f"  high priority    : {len(gap['missing_by_priority']['high'])}")
    print(f"  medium priority  : {len(gap['missing_by_priority']['medium'])}")
    print(f"  low priority     : {len(gap['missing_by_priority']['low'])}")

    print("\nIndustry readiness:")
    for industry in INDUSTRY_PROFILES:
        r = get_industry_readiness(industry)
        print(f"  {industry:<15}: {r['readiness_pct']:.0f}%  (missing: {r['missing_critical']})")


if __name__ == "__main__":
    _sanity_check()
