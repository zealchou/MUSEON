"""Constellation Radar — 泛化多維追蹤框架.

任何「星座」（多維追蹤結構）都可用此框架，無需修改核心邏輯。
星座定義從 JSON 讀取；使用者雷達資料按星座獨立存放。

用法範例：
    defn = load_definition("business_twelve")
    dims = tuple(defn["dimensions"])
    radar = load_radar("business_twelve", "boss")
    radar = update_from_skill(radar, skill_affinity, dims, defn["alpha"])
    save_radar("business_twelve", radar, "boss")

v1.0: 初始版本（由 absurdity_radar.py 泛化而來）
"""

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# --- 路徑輔助 ---

def _constellation_dir(constellation_name: str, data_dir: str = "data") -> Path:
    """星座定義目錄."""
    return Path(data_dir) / "_system" / "constellations" / constellation_name


def _radar_path(constellation_name: str, user_id: str, data_dir: str = "data") -> Path:
    """使用者雷達檔案路徑."""
    return _constellation_dir(constellation_name, data_dir) / "radars" / f"{user_id}.json"


def _registry_path(data_dir: str = "data") -> Path:
    """星座 registry 路徑."""
    return Path(data_dir) / "_system" / "constellations" / "registry.json"


def _links_path(constellation_name: str, data_dir: str = "data") -> Path:
    """跨星座觸發規則路徑."""
    return _constellation_dir(constellation_name, data_dir) / "links.json"


# --- 定義讀取 ---

def load_definition(
    constellation_name: str,
    data_dir: str = "data",
) -> Optional[Dict]:
    """載入星座定義（維度清單、衰減率、alpha 等）.

    回傳 definition.json 的完整內容，或 None（檔案不存在或解析失敗）。
    """
    path = _constellation_dir(constellation_name, data_dir) / "definition.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("[ConstellationRadar] definition not found: %s", path)
        return None
    except Exception as exc:
        logger.error("[ConstellationRadar] load_definition failed for %s: %s", constellation_name, exc)
        return None


# --- 雷達 I/O ---

def load_radar(
    constellation_name: str,
    user_id: str = "boss",
    data_dir: str = "data",
) -> Dict[str, float]:
    """載入使用者在某星座的雷達狀態.

    不存在則用定義中的 default_value 初始化；定義也不存在則全部 0.5。
    回傳格式：{dim: float, ..., "confidence": float}
    """
    path = _radar_path(constellation_name, user_id, data_dir)
    defn = load_definition(constellation_name, data_dir)
    dimensions: Tuple[str, ...] = tuple(defn["dimensions"]) if defn else ()
    default_val: float = defn.get("default_value", 0.5) if defn else 0.5

    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            base = {dim: data.get(dim, default_val) for dim in dimensions}
            base["confidence"] = data.get("confidence", 0.0)
            return base
    except Exception as exc:
        logger.warning("[ConstellationRadar] load_radar failed for %s/%s: %s", constellation_name, user_id, exc)

    # 初始值
    base = {dim: default_val for dim in dimensions}
    base["confidence"] = 0.0
    return base


def save_radar(
    constellation_name: str,
    radar: Dict[str, float],
    user_id: str = "boss",
    data_dir: str = "data",
) -> None:
    """持久化雷達."""
    defn = load_definition(constellation_name, data_dir)
    dimensions: Tuple[str, ...] = tuple(defn["dimensions"]) if defn else tuple(
        k for k in radar if k != "confidence"
    )

    path = _radar_path(constellation_name, user_id, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload: Dict = {
        "constellation": constellation_name,
        "user_id": user_id,
        **{dim: round(radar.get(dim, 0.5), 4) for dim in dimensions},
        "confidence": round(radar.get("confidence", 0.0), 4),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.debug("[ConstellationRadar] saved radar for %s/%s", constellation_name, user_id)


# --- 雷達更新 ---

def update_from_skill(
    radar: Dict[str, float],
    skill_affinity: Dict[str, float],
    dimensions: Tuple[str, ...],
    alpha: float = 0.15,
) -> Dict[str, float]:
    """Skill 使用後更新雷達.

    公式：new = old + alpha × affinity × (1 - old)
    skill_affinity 中不在 dimensions 的鍵一律忽略。
    信心隨使用次數漸增（+confidence_increment，預設 0.02）。
    """
    updated = dict(radar)
    for dim, aff in skill_affinity.items():
        if dim in dimensions and dim in updated:
            old = updated[dim]
            updated[dim] = min(1.0, old + alpha * aff * (1.0 - old))

    old_conf = updated.get("confidence", 0.0)
    updated["confidence"] = min(1.0, old_conf + 0.02)
    return updated


def decay_radar(
    radar: Dict[str, float],
    dimensions: Tuple[str, ...],
    decay_rate: float = 0.02,
) -> Dict[str, float]:
    """每晚衰減：dim = dim - decay_rate × (dim - 0.5)，信心也衰減.

    dim > 0.5 → 向 0.5 收斂；dim < 0.5 → 繼續遠離 0.5（代表惡化）。
    """
    updated = dict(radar)
    for dim in dimensions:
        if dim in updated:
            old = updated[dim]
            updated[dim] = round(old - decay_rate * (old - 0.5), 4)

    old_conf = updated.get("confidence", 0.0)
    updated["confidence"] = round(max(0.0, old_conf - 0.01), 4)
    return updated


# --- 維度查詢 ---

def get_weakest(
    radar: Dict[str, float],
    dimensions: Tuple[str, ...],
) -> Tuple[str, float]:
    """找出最弱維度（分數最低）.

    dimensions 為空或雷達無對應維度時，回傳 ("", 0.0)。
    """
    candidates = [(dim, radar[dim]) for dim in dimensions if dim in radar]
    if not candidates:
        return ("", 0.0)
    return min(candidates, key=lambda x: x[1])


def get_strongest(
    radar: Dict[str, float],
    dimensions: Tuple[str, ...],
) -> Tuple[str, float]:
    """找出最強維度（分數最高）.

    dimensions 為空或雷達無對應維度時，回傳 ("", 0.0)。
    """
    candidates = [(dim, radar[dim]) for dim in dimensions if dim in radar]
    if not candidates:
        return ("", 0.0)
    return max(candidates, key=lambda x: x[1])


# --- 星座列表 & 跨星座觸發 ---

def list_constellations(data_dir: str = "data") -> List[str]:
    """列出所有已註冊的星座名稱（從 registry.json 讀取）."""
    path = _registry_path(data_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("constellations", [])
    except FileNotFoundError:
        logger.warning("[ConstellationRadar] registry.json not found at %s", path)
        return []
    except Exception as exc:
        logger.error("[ConstellationRadar] list_constellations failed: %s", exc)
        return []


def check_cross_triggers(
    constellation_name: str,
    radar: Dict[str, float],
    data_dir: str = "data",
) -> List[Dict]:
    """檢查跨星座觸發：某維度低於門檻時，建議切換到相關星座.

    從 links.json 讀取 triggers 規則（when_dim / below / suggest_constellation / reason）。
    回傳滿足條件的物件列表，每項額外附加 current_value。
    """
    path = _links_path(constellation_name, data_dir)
    try:
        rules = json.loads(path.read_text(encoding="utf-8")).get("triggers", [])
    except FileNotFoundError:
        logger.debug("[ConstellationRadar] links.json not found for %s", constellation_name)
        return []
    except Exception as exc:
        logger.error("[ConstellationRadar] check_cross_triggers failed for %s: %s", constellation_name, exc)
        return []

    triggered: List[Dict] = []
    for rule in rules:
        dim = rule.get("when_dim", "")
        threshold = rule.get("below", 0.0)
        if dim in radar and radar[dim] < threshold:
            triggered.append({**rule, "current_value": round(radar[dim], 4)})

    return triggered


# --- 湧現屬性計算 ---

def classify_stage(
    score: float,
    stages: List[Dict],
) -> Tuple[str, str]:
    """根據分數判斷所處階段.

    遍歷 stages 列表，找到 score 落入的 range。
    若所有 range 都不匹配（例如 score=1.0），回傳最後一個階段。
    回傳 (stage_name, stage_label)。
    """
    for stage in stages:
        low, high = stage["range"]
        if low <= score < high:
            return stage["name"], stage["label"]
    # score 剛好等於最高邊界（1.0）時，取最後一個階段
    if stages:
        last = stages[-1]
        return last["name"], last["label"]
    return ("unknown", "未知")


def compute_emergent_property(
    radar: Dict[str, float],
    emergent_config: Dict,
) -> Dict:
    """計算星座的湧現屬性.

    演算法（geometric_mean_with_threshold_gate）：
    1. 對每個維度，計算 excess = max(0, score - threshold)
    2. 計算通過門檻的維度數 pass_count
    3. gate = (pass_count / n) ^ 2（門檻閘門，懲罰未全部通過的情況）
    4. core = 幾何平均(所有 excess)，如果有任一 excess=0 則為 0
    5. raw = gate * core
    6. 用 Sigmoid 正規化到 [0, 1]：score = raw / (raw + k)，k=0.3
    7. 根據分數判斷所處階段

    回傳：
    {
        "name": str,           # 湧現屬性名稱
        "score": float,        # 0.0-1.0
        "stage": str,          # 階段名稱
        "stage_label": str,    # 階段中文標籤
        "pass_count": int,     # 通過門檻的維度數
        "total_dims": int,     # 總維度數
        "per_dim": {dim: {"score": float, "threshold": float, "passed": bool}}
    }
    """
    thresholds: Dict[str, float] = emergent_config.get("thresholds", {})
    stages: List[Dict] = emergent_config.get("stages", [])
    name: str = emergent_config.get("name", "emergent_property")

    # Step 1 & 2：計算每個維度的 excess，並統計通過門檻數
    per_dim: Dict[str, Dict] = {}
    excesses: List[float] = []
    pass_count: int = 0

    for dim, threshold in thresholds.items():
        dim_score = radar.get(dim, 0.0)
        excess = max(0.0, dim_score - threshold)
        passed = dim_score >= threshold
        per_dim[dim] = {
            "score": round(dim_score, 4),
            "threshold": threshold,
            "passed": passed,
        }
        excesses.append(excess)
        if passed:
            pass_count += 1

    n = len(thresholds)
    if n == 0:
        return {
            "name": name,
            "score": 0.0,
            "stage": "absorption",
            "stage_label": "吸納",
            "pass_count": 0,
            "total_dims": 0,
            "per_dim": {},
        }

    # Step 3：門檻閘門
    gate: float = (pass_count / n) ** 2

    # Step 4：幾何平均（任一 excess=0 則整體為 0）
    if any(e == 0.0 for e in excesses):
        core: float = 0.0
    else:
        core = math.exp(sum(math.log(e) for e in excesses) / n)

    # Step 5：raw = gate * core
    raw: float = gate * core

    # Step 6：Sigmoid 正規化，k=0.3
    k: float = 0.3
    final_score: float = raw / (raw + k) if (raw + k) > 0 else 0.0
    final_score = round(min(1.0, max(0.0, final_score)), 4)

    # Step 7：判斷階段
    stage_name, stage_label = classify_stage(final_score, stages)

    return {
        "name": name,
        "score": final_score,
        "stage": stage_name,
        "stage_label": stage_label,
        "pass_count": pass_count,
        "total_dims": n,
        "per_dim": per_dim,
    }
