"""Absurdity Radar — 六大荒謬缺口追蹤.

追蹤使用者在六大荒謬維度上的發展程度，
供 SkillRouter Layer 4 使用，將對話自然推向最弱的維度。

v1.0: 初始版本
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 六大荒謬維度
ABSURDITY_DIMENSIONS = (
    "self_awareness",
    "direction_clarity",
    "gap_visibility",
    "accumulation",
    "relationship_leverage",
    "strategic_integration",
)

# Skill 使用 → 維度更新的映射（從 Skill manifest absurdity_affinity 動態讀取）
# 這裡只定義更新幅度
UPDATE_ALPHA = 0.15  # 每次使用 Skill 的更新幅度


def _radar_dir(data_dir: str = "data") -> Path:
    return Path(data_dir) / "_system" / "absurdity_radar"


def load_radar(user_id: str = "boss", data_dir: str = "data") -> Dict[str, float]:
    """讀取使用者的荒謬雷達.

    回傳格式：{"self_awareness": 0.5, ..., "confidence": 0.1}
    如果檔案不存在，回傳全 0.5 + confidence 0.0 的初始值。
    """
    path = _radar_dir(data_dir) / f"{user_id}.json"
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                dim: data.get(dim, 0.5) for dim in ABSURDITY_DIMENSIONS
            } | {"confidence": data.get("confidence", 0.0)}
    except Exception as e:
        logger.warning(f"[AbsurdityRadar] load failed for {user_id}: {e}")

    # 預設值
    return {dim: 0.5 for dim in ABSURDITY_DIMENSIONS} | {"confidence": 0.0}


def save_radar(
    radar: Dict[str, float],
    user_id: str = "boss",
    data_dir: str = "data",
) -> None:
    """持久化荒謬雷達."""
    path = _radar_dir(data_dir) / f"{user_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "user_id": user_id,
        **{dim: round(radar.get(dim, 0.5), 4) for dim in ABSURDITY_DIMENSIONS},
        "confidence": round(radar.get("confidence", 0.0), 4),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def update_radar_from_skill(
    radar: Dict[str, float],
    skill_affinity: Dict[str, float],
    alpha: float = UPDATE_ALPHA,
) -> Dict[str, float]:
    """根據 Skill 使用更新雷達.

    skill_affinity: 該 Skill 的 absurdity_affinity（從 manifest 讀取）
    效果：使用了處理某維度的 Skill → 該維度的分數上升（代表使用者正在發展此維度）
    """
    updated = dict(radar)
    for dim, aff in skill_affinity.items():
        if dim in ABSURDITY_DIMENSIONS and dim in updated:
            old = updated[dim]
            # 漸進更新：使用了處理此維度的 Skill → 分數微升
            updated[dim] = old + alpha * aff * (1.0 - old)

    # 信心隨使用次數漸增
    old_conf = updated.get("confidence", 0.0)
    updated["confidence"] = min(1.0, old_conf + 0.02)

    return updated
