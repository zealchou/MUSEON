"""Market Ares — 原型命名器

用 LLM（Sonnet）為聚類產生的原型命名。
"""

from __future__ import annotations

import json
import logging

from museon.darwin.config import PRIMALS
from museon.darwin.storage.models import Archetype

logger = logging.getLogger(__name__)

_NAMING_PROMPT = """你是 One Muse 八方位能量系統的專家。以下是一個市場人群原型的能量指紋。
請根據能量特徵，為這個原型取一個白話名稱（2-4 個中文字）和一句話描述（20 字以內）。

名稱要求：
- 中小企業主看得懂
- 有畫面感
- 不用八卦/易經術語

能量指紋：
內在：{inner}
外在：{outer}
佔人口比例：{weight_pct}%
創新採用階段：{stage}

最高內在能量：{top_inner}
最低內在能量：{bottom_inner}

回覆 JSON 格式：
{{"name": "原型名稱", "description": "一句話描述"}}
"""


def generate_naming_prompt(archetype: Archetype) -> str:
    """生成命名 prompt"""
    inner = archetype.inner_energy.to_dict()
    outer = archetype.outer_energy.to_dict()

    # 找最高和最低的方位
    sorted_inner = sorted(inner.items(), key=lambda x: x[1], reverse=True)
    top_inner = f"{sorted_inner[0][0]}({sorted_inner[0][1]:+.1f}), {sorted_inner[1][0]}({sorted_inner[1][1]:+.1f})"
    bottom_inner = f"{sorted_inner[-1][0]}({sorted_inner[-1][1]:+.1f}), {sorted_inner[-2][0]}({sorted_inner[-2][1]:+.1f})"

    return _NAMING_PROMPT.format(
        inner=json.dumps(inner, ensure_ascii=False),
        outer=json.dumps(outer, ensure_ascii=False),
        weight_pct=round(archetype.weight * 100, 1),
        stage=archetype.adoption_stage,
        top_inner=top_inner,
        bottom_inner=bottom_inner,
    )


def batch_naming_prompt(archetypes: list[Archetype]) -> str:
    """生成批次命名 prompt（省 token）

    一次傳入多個原型，讓 LLM 一次命名完。
    """
    prompt_parts = [
        "你是 One Muse 八方位能量系統的專家。以下是多個市場人群原型的能量指紋。",
        "請為每個原型取一個白話名稱（2-4 個中文字）和一句話描述（20 字以內）。",
        "名稱要有畫面感，中小企業主看得懂，不用八卦術語。",
        "",
        "回覆 JSON 陣列格式：",
        '[{"id": 0, "name": "xxx", "description": "xxx"}, ...]',
        "",
    ]

    for a in archetypes:
        inner = a.inner_energy.to_dict()
        sorted_inner = sorted(inner.items(), key=lambda x: x[1], reverse=True)
        top2 = f"{sorted_inner[0][0]}({sorted_inner[0][1]:+.1f}), {sorted_inner[1][0]}({sorted_inner[1][1]:+.1f})"
        bot2 = f"{sorted_inner[-1][0]}({sorted_inner[-1][1]:+.1f}), {sorted_inner[-2][0]}({sorted_inner[-2][1]:+.1f})"

        prompt_parts.append(
            f"原型 {a.id}：最高={top2}｜最低={bot2}｜佔比={a.weight*100:.1f}%｜階段={a.adoption_stage}"
        )

    return "\n".join(prompt_parts)


def apply_names(archetypes: list[Archetype], naming_results: list[dict]) -> list[Archetype]:
    """將 LLM 命名結果套用到原型上

    Args:
        archetypes: 原型列表
        naming_results: [{"id": 0, "name": "xxx", "description": "xxx"}, ...]
    """
    result_map = {r["id"]: r for r in naming_results}

    for a in archetypes:
        if a.id in result_map:
            a.name = result_map[a.id].get("name", a.name)
            a.description = result_map[a.id].get("description", a.description)

    return archetypes
