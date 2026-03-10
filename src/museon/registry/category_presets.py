"""Category Presets — 預設分類體系.

提供收入、支出、轉帳三大類的預設分類樹。
所有系統預設分類 is_system=1，使用者自訂分類 is_system=0。

分類 ID 格式：
  income.salary        → 收入 > 薪資
  expense.food.dining  → 支出 > 餐飲 > 外食
  transfer.internal    → 轉帳 > 帳戶互轉
"""

from typing import Dict, List, Tuple


# (category_id, parent_id, name_zh, name_en)
CATEGORY_PRESETS: List[Tuple[str, str, str, str]] = [
    # ═══════════════════════════════════════
    # 收入 (income)
    # ═══════════════════════════════════════
    ("income", "", "收入", "Income"),
    ("income.salary", "income", "薪資", "Salary"),
    ("income.freelance", "income", "接案收入", "Freelance"),
    ("income.investment", "income", "投資收入", "Investment"),
    ("income.bonus", "income", "獎金", "Bonus"),
    ("income.gift", "income", "禮金/紅包", "Gift"),
    ("income.refund", "income", "退款", "Refund"),
    ("income.other", "income", "其他收入", "Other Income"),

    # ═══════════════════════════════════════
    # 支出 (expense)
    # ═══════════════════════════════════════
    ("expense", "", "支出", "Expense"),

    # 餐飲
    ("expense.food", "expense", "餐飲", "Food"),
    ("expense.food.dining_out", "expense.food", "外食", "Dining Out"),
    ("expense.food.groceries", "expense.food", "食材/超市", "Groceries"),
    ("expense.food.drinks", "expense.food", "飲料/咖啡", "Drinks"),
    ("expense.food.delivery", "expense.food", "外送", "Delivery"),

    # 交通
    ("expense.transport", "expense", "交通", "Transport"),
    ("expense.transport.public", "expense.transport", "大眾運輸", "Public Transit"),
    ("expense.transport.taxi", "expense.transport", "計程車/網約車", "Taxi"),
    ("expense.transport.fuel", "expense.transport", "油費", "Fuel"),
    ("expense.transport.parking", "expense.transport", "停車費", "Parking"),

    # 住宿/居住
    ("expense.housing", "expense", "住宿/居住", "Housing"),
    ("expense.housing.rent", "expense.housing", "房租", "Rent"),
    ("expense.housing.utilities", "expense.housing", "水電瓦斯", "Utilities"),
    ("expense.housing.internet", "expense.housing", "網路", "Internet"),
    ("expense.housing.hotel", "expense.housing", "旅館", "Hotel"),

    # 購物
    ("expense.shopping", "expense", "購物", "Shopping"),
    ("expense.shopping.clothing", "expense.shopping", "服飾", "Clothing"),
    ("expense.shopping.electronics", "expense.shopping", "3C/電子", "Electronics"),
    ("expense.shopping.daily", "expense.shopping", "日用品", "Daily Necessities"),

    # 娛樂
    ("expense.entertainment", "expense", "娛樂", "Entertainment"),
    ("expense.entertainment.subscription", "expense.entertainment", "訂閱服務", "Subscription"),
    ("expense.entertainment.travel", "expense.entertainment", "旅遊", "Travel"),

    # 醫療
    ("expense.medical", "expense", "醫療", "Medical"),
    ("expense.medical.hospital", "expense.medical", "看診/醫院", "Hospital"),
    ("expense.medical.medicine", "expense.medical", "藥品", "Medicine"),

    # 教育
    ("expense.education", "expense", "教育", "Education"),
    ("expense.education.course", "expense.education", "課程/培訓", "Course"),
    ("expense.education.books", "expense.education", "書籍", "Books"),

    # 社交
    ("expense.social", "expense", "社交", "Social"),
    ("expense.social.gift", "expense.social", "禮物/紅包", "Gift"),
    ("expense.social.meal", "expense.social", "請客", "Treating"),

    # 工作/商務
    ("expense.business", "expense", "工作/商務", "Business"),
    ("expense.business.tools", "expense.business", "工具/軟體", "Tools"),
    ("expense.business.office", "expense.business", "辦公費用", "Office"),

    # 其他支出
    ("expense.other", "expense", "其他支出", "Other Expense"),

    # ═══════════════════════════════════════
    # 轉帳 (transfer)
    # ═══════════════════════════════════════
    ("transfer", "", "轉帳", "Transfer"),
    ("transfer.internal", "transfer", "帳戶互轉", "Internal Transfer"),
    ("transfer.to_others", "transfer", "轉帳給他人", "Transfer to Others"),
]


def get_all_presets() -> List[Tuple[str, str, str, str]]:
    """取得所有預設分類.

    Returns:
        List of (category_id, parent_id, name_zh, name_en)
    """
    return CATEGORY_PRESETS


def get_categories_by_type(category_type: str) -> List[Tuple[str, str, str, str]]:
    """依分類大類篩選.

    Args:
        category_type: "income", "expense", or "transfer"

    Returns:
        該大類下的所有分類。
    """
    return [
        c for c in CATEGORY_PRESETS
        if c[0] == category_type or c[0].startswith(f"{category_type}.")
    ]


def count_presets() -> int:
    """取得預設分類總數."""
    return len(CATEGORY_PRESETS)


def get_category_tree() -> Dict[str, list]:
    """建構分類樹結構.

    Returns:
        {"income": [...], "expense": [...], "transfer": [...]}
    """
    tree: Dict[str, list] = {}
    for cat_id, parent_id, name_zh, name_en in CATEGORY_PRESETS:
        if not parent_id:
            tree[cat_id] = []
    for cat_id, parent_id, name_zh, name_en in CATEGORY_PRESETS:
        if parent_id and parent_id in tree:
            tree[parent_id].append({
                "id": cat_id,
                "name_zh": name_zh,
                "name_en": name_en,
            })
    return tree
