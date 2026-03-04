"""飛輪八部門配置.

10 Agents：Core + OKR + 8 飛輪部門（雷/火/澤/天/風/水/山/地）。
依據 MULTI_AGENT_BDD_SPEC §2 實作。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class DepartmentConfig:
    """單一部門配置."""

    dept_id: str                            # 識別碼
    name: str                               # 中文名稱
    emoji: str                              # 部門圖標
    role: str                               # 角色描述
    flywheel_order: int                     # 0=中央, 1~8=飛輪
    keywords: List[str] = field(default_factory=list)   # 路由關鍵字
    prompt_section: str = ""                # 角色 prompt
    tool_whitelist: Optional[List[str]] = None  # None=全部工具
    next_dept: Optional[str] = None         # 飛輪下一站
    prev_dept: Optional[str] = None         # 飛輪上一站


# ═══════════════════════════════════════════
# 飛輪順序常數
# ═══════════════════════════════════════════

FLYWHEEL_ORDER: List[str] = [
    "thunder", "fire", "lake", "heaven",
    "wind", "water", "mountain", "earth",
]

# ═══════════════════════════════════════════
# 10 個部門定義
# ═══════════════════════════════════════════

_DEPARTMENTS: Dict[str, DepartmentConfig] = {}


def _register(cfg: DepartmentConfig) -> None:
    _DEPARTMENTS[cfg.dept_id] = cfg


# ── 中央部門（flywheel_order = 0）──

_register(DepartmentConfig(
    dept_id="core",
    name="核心智能",
    emoji="\U0001F9E0",       # 🧠
    role="中央分析與策略建議",
    flywheel_order=0,
    keywords=["分析", "策略", "建議", "幫我", "想想", "思考"],
    prompt_section=(
        "你是 MUSEON 核心智能（🧠）。\n"
        "職責：中央分析與策略建議，綜合各部門情報做出判斷。\n"
        "當無法明確歸類到其他部門時，由你統籌處理。"
    ),
))

_register(DepartmentConfig(
    dept_id="okr",
    name="目標管理",
    emoji="\U0001F3AF",       # 🎯
    role="OKR 目標設定與追蹤",
    flywheel_order=0,
    keywords=["目標", "OKR", "KR", "進度", "里程碑", "達成"],
    prompt_section=(
        "你是 MUSEON 目標管理（🎯）。\n"
        "職責：OKR 目標設定、進度追蹤、里程碑管理。\n"
        "幫助使用者將模糊意圖轉化為可衡量的關鍵結果。"
    ),
))

# ── 飛輪八部門（flywheel_order 1~8）──

_register(DepartmentConfig(
    dept_id="thunder",
    name="行動執行",
    emoji="\u26A1",           # ⚡
    role="雷部 — 快速執行與推進",
    flywheel_order=1,
    keywords=["執行", "行動", "做", "開始", "啟動", "推進", "雷"],
    prompt_section=(
        "你是 MUSEON 雷部・行動執行（⚡）。\n"
        "職責：快速執行與推進。接到任務立即拆解、排序、動手。\n"
        "風格：果決、高效、不拖泥帶水。"
    ),
    next_dept="fire",
    prev_dept="earth",
))

_register(DepartmentConfig(
    dept_id="fire",
    name="品牌行銷",
    emoji="\U0001F525",       # 🔥
    role="火部 — 品牌行銷與推廣",
    flywheel_order=2,
    keywords=["行銷", "品牌", "推廣", "宣傳", "社群", "曝光", "火"],
    prompt_section=(
        "你是 MUSEON 火部・品牌行銷（🔥）。\n"
        "職責：品牌行銷與推廣。點燃市場注意力，擴大品牌影響力。\n"
        "風格：熱情、創意、敏銳掌握趨勢。"
    ),
    next_dept="lake",
    prev_dept="thunder",
))

_register(DepartmentConfig(
    dept_id="lake",
    name="客戶關係",
    emoji="\U0001F4A7",       # 💧
    role="澤部 — 客戶關係經營",
    flywheel_order=3,
    keywords=["客戶", "用戶", "反饋", "滿意度", "服務", "體驗", "澤"],
    prompt_section=(
        "你是 MUSEON 澤部・客戶關係（💧）。\n"
        "職責：客戶關係經營。深耕用戶體驗，提升滿意度與留存。\n"
        "風格：溫暖、細膩、善於傾聽。"
    ),
    next_dept="heaven",
    prev_dept="fire",
))

_register(DepartmentConfig(
    dept_id="heaven",
    name="願景策略",
    emoji="\U0001F31F",       # 🌟
    role="天部 — 願景與長期策略",
    flywheel_order=4,
    keywords=["願景", "策略", "長期", "規劃", "方向", "未來", "天"],
    prompt_section=(
        "你是 MUSEON 天部・願景策略（🌟）。\n"
        "職責：願景與長期策略。站在制高點看全局，定義方向。\n"
        "風格：遠見、格局、不被短期波動干擾。"
    ),
    next_dept="wind",
    prev_dept="lake",
))

_register(DepartmentConfig(
    dept_id="wind",
    name="創新研發",
    emoji="\U0001F300",       # 🌀
    role="風部 — 創新與研發探索",
    flywheel_order=5,
    keywords=["創新", "研發", "新", "技術", "實驗", "突破", "風"],
    prompt_section=(
        "你是 MUSEON 風部・創新研發（🌀）。\n"
        "職責：創新與研發探索。大膽假設，快速驗證。\n"
        "風格：好奇、敢試、不怕失敗。"
    ),
    next_dept="water",
    prev_dept="heaven",
))

_register(DepartmentConfig(
    dept_id="water",
    name="財務資源",
    emoji="\U0001F30A",       # 🌊
    role="水部 — 財務與資源管理",
    flywheel_order=6,
    keywords=["財務", "預算", "成本", "收入", "資源", "投資", "水"],
    prompt_section=(
        "你是 MUSEON 水部・財務資源（🌊）。\n"
        "職責：財務與資源管理。精算每一分錢的投資報酬。\n"
        "風格：精準、務實、數字說話。"
    ),
    next_dept="mountain",
    prev_dept="wind",
))

_register(DepartmentConfig(
    dept_id="mountain",
    name="品質管控",
    emoji="\u26F0\uFE0F",    # ⛰️
    role="山部 — 品質與合規管控",
    flywheel_order=7,
    keywords=["品質", "品管", "標準", "檢查", "合規", "穩定", "山"],
    prompt_section=(
        "你是 MUSEON 山部・品質管控（⛰️）。\n"
        "職責：品質與合規管控。守住底線，確保交付品質。\n"
        "風格：嚴謹、穩重、不放過細節。"
    ),
    next_dept="earth",
    prev_dept="water",
))

_register(DepartmentConfig(
    dept_id="earth",
    name="營運後勤",
    emoji="\U0001F30D",       # 🌍
    role="地部 — 營運與後勤支援",
    flywheel_order=8,
    keywords=["營運", "後勤", "流程", "效率", "系統", "維護", "地"],
    prompt_section=(
        "你是 MUSEON 地部・營運後勤（🌍）。\n"
        "職責：營運與後勤支援。讓一切順暢運轉的基石。\n"
        "風格：踏實、高效、系統化。"
    ),
    next_dept="thunder",
    prev_dept="mountain",
))


# ═══════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════

def get_department(dept_id: str) -> Optional[DepartmentConfig]:
    """取得部門配置，不存在回 None."""
    return _DEPARTMENTS.get(dept_id)


def get_all_departments() -> Dict[str, DepartmentConfig]:
    """取得全部 10 個部門配置（唯讀 copy）."""
    return dict(_DEPARTMENTS)


def get_flywheel_departments() -> List[DepartmentConfig]:
    """取得飛輪八部門（依 flywheel_order 排序）."""
    return sorted(
        [d for d in _DEPARTMENTS.values() if d.flywheel_order > 0],
        key=lambda d: d.flywheel_order,
    )


def get_next_dept(dept_id: str) -> Optional[str]:
    """取得飛輪下一站."""
    dept = _DEPARTMENTS.get(dept_id)
    return dept.next_dept if dept else None


def get_prev_dept(dept_id: str) -> Optional[str]:
    """取得飛輪上一站."""
    dept = _DEPARTMENTS.get(dept_id)
    return dept.prev_dept if dept else None
