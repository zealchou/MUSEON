"""DARWIN — 產品品類參數模組

不同品類的成長曲線差異：
  - 餐飲：高可見度、低進入阻力、高流失率
  - 美業：強口碑、高信任門檻、高黏性
  - B2B SaaS：長決策週期、超寬鴻溝、低流失率
  - 教育：思想領袖主導、社群綁定
  - 製造業：資本決策、極慢週期
  - 零售：高曝光、高流失、高價格敏感度
  - 顧問：推薦制、深度關係
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProductProfile:
    """產品品類的成長曲線參數"""

    name: str  # 品類名稱

    # Bass 參數修正因子（乘在原型的 p/q 上面）
    p_multiplier: float  # 創新係數修正（品類的主動嘗試難度）
    q_multiplier: float  # 模仿係數修正（品類的口碑傳播特性）

    # 漏斗轉化速率（每週的基礎轉化機率加成）
    awareness_speed: float   # unaware → aware 的速度因子（1.0=基準）
    trial_barrier: float     # aware → considering 的阻力（0=無阻力, 1=極高）
    decision_speed: float    # considering → decided 的速度因子
    loyalty_speed: float     # decided → loyal 的速度因子

    # 鴻溝特性
    chasm_width: float       # 鴻溝寬度修正（1.0=標準, 2.0=超寬）
    chasm_threshold: float   # 鴻溝發生在多少採用率（預設 0.15-0.20）

    # 流失與抗性
    resistance_rate: float   # 基礎抗性生成率（每週）
    churn_rate: float        # loyal → 流失的機率（每週）

    # 價格敏感度
    price_sensitivity: float  # 0=不敏感（奢侈品）, 1=極敏感（日用品）

    # 能量共振修正：哪些方位對這個品類特別重要
    critical_primals: list[str] = field(default_factory=list)  # 關鍵方位（共振加成）
    boost_primals: list[str] = field(default_factory=list)     # 輔助方位（小加成）


# 預設品類參數（基於學術文獻 + 實戰經驗）

PRODUCT_PROFILES: dict[str, ProductProfile] = {
    "cafe": ProductProfile(
        name="咖啡廳/餐飲",
        p_multiplier=2.5,        # 路過就看到，主動嘗試容易
        q_multiplier=0.8,        # 口碑一般（太多選擇）
        awareness_speed=2.0,     # 極快（實體可見）
        trial_barrier=0.1,       # 極低（推門進去就好）
        decision_speed=1.5,      # 快（日常消費）
        loyalty_speed=0.8,       # 中等（需要養成習慣）
        chasm_width=0.6,         # 窄（日常消費鴻溝小）
        chasm_threshold=0.10,    # 10% 就到鴻溝
        resistance_rate=0.005,   # 低（咖啡不會被排斥）
        churn_rate=0.02,         # 高（替代品多）
        price_sensitivity=0.6,   # 中高
        critical_primals=["澤", "地"],   # 社群 + 經濟力
        boost_primals=["山", "風"],      # 品質 + 溝通
    ),

    "beauty": ProductProfile(
        name="美業/沙龍",
        p_multiplier=1.0,        # 主動嘗試需要勇氣
        q_multiplier=2.0,        # 口碑超強（效果好會瘋狂推薦）
        awareness_speed=1.2,     # 中等（社群曝光）
        trial_barrier=0.6,       # 高（需要信任、預約）
        decision_speed=0.7,      # 慢（要看別人結果）
        loyalty_speed=1.5,       # 快（關係綁定）
        chasm_width=1.0,         # 標準
        chasm_threshold=0.15,    # 15%
        resistance_rate=0.008,   # 中等
        churn_rate=0.005,        # 極低（關係黏性）
        price_sensitivity=0.4,   # 中低（願意為效果付費）
        critical_primals=["澤", "火"],   # 社群 + 展現
        boost_primals=["水", "山"],      # 關係 + 品質
    ),

    "b2b_saas": ProductProfile(
        name="SaaS B2B",
        p_multiplier=0.5,        # 觸及困難
        q_multiplier=1.5,        # 網絡效應強
        awareness_speed=0.5,     # 慢（精準投放）
        trial_barrier=0.4,       # 中等（免費試用降低門檻）
        decision_speed=0.4,      # 極慢（組織決策）
        loyalty_speed=0.5,       # 慢（合約週期）
        chasm_width=2.0,         # 超寬（組織惰性）
        chasm_threshold=0.12,    # 12%
        resistance_rate=0.01,    # 中高（IT 決策者保守）
        churn_rate=0.008,        # 低（遷移成本高）
        price_sensitivity=0.3,   # 低（看 ROI 不看價格）
        critical_primals=["天", "風"],   # 目標 + 溝通
        boost_primals=["火", "地"],      # 趨勢 + 穩定
    ),

    "education": ProductProfile(
        name="教育/培訓/身心靈",
        p_multiplier=1.5,        # 思想領袖能直接觸及
        q_multiplier=1.2,        # 口碑中高（好老師會被推薦）
        awareness_speed=1.0,     # 標準
        trial_barrier=0.5,       # 中高（需要認知門檻）
        decision_speed=0.8,      # 中等
        loyalty_speed=1.2,       # 中快（學習社群綁定）
        chasm_width=1.2,         # 稍寬
        chasm_threshold=0.15,    # 15%
        resistance_rate=0.006,   # 中等
        churn_rate=0.01,         # 中等
        price_sensitivity=0.5,   # 中等
        critical_primals=["雷", "火"],   # 覺察 + 展現
        boost_primals=["澤", "天"],      # 社群 + 目標
    ),

    "manufacturing": ProductProfile(
        name="製造業/工業",
        p_multiplier=0.3,        # 極難主動嘗試（資本投入）
        q_multiplier=0.5,        # 口碑慢（行業圈小但封閉）
        awareness_speed=0.3,     # 極慢
        trial_barrier=0.8,       # 極高（需要 POC）
        decision_speed=0.3,      # 極慢（月/年級）
        loyalty_speed=0.3,       # 極慢（合約週期長）
        chasm_width=2.5,         # 超寬
        chasm_threshold=0.08,    # 8%
        resistance_rate=0.015,   # 高
        churn_rate=0.002,        # 極低（遷移成本極高）
        price_sensitivity=0.2,   # 低（看 TCO）
        critical_primals=["地", "山"],   # 穩定 + 紀律
        boost_primals=["風", "水"],      # 溝通 + 關係
    ),

    "retail": ProductProfile(
        name="零售/電商",
        p_multiplier=2.0,        # 容易被看到
        q_multiplier=1.0,        # 口碑標準
        awareness_speed=1.8,     # 快（線上線下曝光）
        trial_barrier=0.2,       # 低（下單就好）
        decision_speed=1.2,      # 中快
        loyalty_speed=0.6,       # 慢（替代品多）
        chasm_width=0.8,         # 窄
        chasm_threshold=0.12,    # 12%
        resistance_rate=0.004,   # 低
        churn_rate=0.025,        # 高（品牌忠誠度低）
        price_sensitivity=0.8,   # 高
        critical_primals=["澤", "火"],   # 社群 + 趨勢
        boost_primals=["地", "風"],      # 經濟 + 溝通
    ),

    "consulting": ProductProfile(
        name="顧問/專業服務",
        p_multiplier=0.8,        # 需要主動搜尋
        q_multiplier=1.8,        # 口碑極強（推薦制）
        awareness_speed=0.8,     # 中等
        trial_barrier=0.7,       # 高（需要信任 + 面談）
        decision_speed=0.6,      # 慢
        loyalty_speed=1.3,       # 中快（關係深）
        chasm_width=1.5,         # 寬
        chasm_threshold=0.15,    # 15%
        resistance_rate=0.007,   # 中等
        churn_rate=0.006,        # 低
        price_sensitivity=0.3,   # 低（看價值不看價格）
        critical_primals=["風", "水"],   # 溝通 + 關係
        boost_primals=["天", "山"],      # 目標 + 品質
    ),
}

# 別名映射
_ALIASES: dict[str, str] = {
    "b2b_saas": "b2b_saas", "saas": "b2b_saas",
    "cafe": "cafe", "coffee": "cafe", "restaurant": "cafe",
    "餐飲": "cafe", "咖啡": "cafe",
    "beauty": "beauty", "salon": "beauty", "美業": "beauty",
    "education": "education", "training": "education", "身心靈": "education",
    "manufacturing": "manufacturing", "工業": "manufacturing", "製造": "manufacturing",
    "retail": "retail", "ecommerce": "retail", "零售": "retail",
    "consulting": "consulting", "顧問": "consulting",
}


def get_product_profile(product_type: str) -> ProductProfile:
    """取得產品品類參數。找不到就用 retail 作為預設。"""
    key = _ALIASES.get(product_type, product_type)
    return PRODUCT_PROFILES.get(key, PRODUCT_PROFILES["retail"])
