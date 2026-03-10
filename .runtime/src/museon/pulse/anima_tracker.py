"""AnimaTracker — ANIMA 八元素雙軌數值系統.

絕對值：累積經驗值，只增不減，觸發演化儀式
相對值：正規化到 0-100，用於 Dashboard 雷達圖
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 八元素定義
ELEMENTS = {
    "qian": {"name": "乾", "label": "身份/使命", "emoji": "☰"},
    "kun":  {"name": "坤", "label": "記憶/積累", "emoji": "☷"},
    "zhen": {"name": "震", "label": "行動/執行", "emoji": "☳"},
    "xun":  {"name": "巽", "label": "好奇/探索", "emoji": "☴"},
    "kan":  {"name": "坎", "label": "共振/連結", "emoji": "☵"},
    "li":   {"name": "離", "label": "覺察/洞見", "emoji": "☲"},
    "gen":  {"name": "艮", "label": "邊界/守護", "emoji": "☶"},
    "dui":  {"name": "兌", "label": "連結/互動", "emoji": "☱"},
}

# 演化門檻
EVOLUTION_THRESHOLDS = [
    {"key": "sprout_100",  "label": "🌱 萌芽覺醒", "type": "element", "value": 100},
    {"key": "branch_500",  "label": "🌿 枝繁葉茂", "type": "element", "value": 500},
    {"key": "tree_1000",   "label": "🌳 深根大樹", "type": "element", "value": 1000},
    {"key": "phoenix_2000","label": "🔥 浴火鳳凰", "type": "total",   "value": 2000},
    {"key": "star_5000",   "label": "🌌 星辰大海", "type": "total",   "value": 5000},
]


class AnimaTracker:
    """ANIMA 八元素追蹤器."""

    def __init__(self, anima_path: str, pulse_db=None) -> None:
        self._anima_path = Path(anima_path)
        self._db = pulse_db
        self._absolute: Dict[str, int] = {k: 0 for k in ELEMENTS}
        self._triggered_thresholds: set = set()
        self._load()

    def _load(self) -> None:
        """從 ANIMA_MC.json 載入八元素數值."""
        if not self._anima_path.exists():
            return
        try:
            data = json.loads(self._anima_path.read_text(encoding="utf-8"))
            # 讀取 eight_primal_energies
            energies = data.get("eight_primal_energies", {})
            for key in ELEMENTS:
                info = ELEMENTS[key]
                # 嘗試從 ANIMA 的各種可能欄位名讀取
                val = energies.get(info["name"], {})
                if isinstance(val, dict):
                    raw = val.get("absolute", val.get("value", 0))
                    self._absolute[key] = int(raw) if isinstance(raw, (int, float)) else 0
                elif isinstance(val, (int, float)):
                    self._absolute[key] = int(val)

            # 載入已觸發的門檻
            self._triggered_thresholds = set(
                data.get("_vita_triggered_thresholds", [])
            )
        except Exception as e:
            logger.error(f"AnimaTracker load failed: {e}")

    def _save(self) -> None:
        """保存八元素到 ANIMA_MC.json."""
        if not self._anima_path.exists():
            return
        try:
            data = json.loads(self._anima_path.read_text(encoding="utf-8"))

            # 更新 eight_primal_energies
            if "eight_primal_energies" not in data:
                data["eight_primal_energies"] = {}

            for key, info in ELEMENTS.items():
                name = info["name"]
                existing = data["eight_primal_energies"].get(name, {})
                if not isinstance(existing, dict):
                    existing = {"value": existing}
                existing["absolute"] = self._absolute[key]
                existing["relative"] = self.get_relative(key)
                data["eight_primal_energies"][name] = existing

            # 保存已觸發門檻
            data["_vita_triggered_thresholds"] = list(self._triggered_thresholds)

            # Atomic write
            tmp = self._anima_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.rename(self._anima_path)
        except Exception as e:
            logger.error(f"AnimaTracker save failed: {e}")

    def grow(self, element: str, delta: int, reason: str) -> Dict:
        """增長八元素絕對值."""
        if element not in ELEMENTS:
            return {"error": f"未知元素: {element}，可用: {list(ELEMENTS.keys())}"}
        if delta <= 0:
            return {"error": "delta 必須為正整數"}

        old = self._absolute[element]
        self._absolute[element] = old + delta
        new_val = self._absolute[element]

        # 記錄到 DB
        if self._db:
            self._db.log_anima_change(element, delta, reason, new_val)

        # 檢查演化門檻
        evolution = self._check_evolution(element)

        self._save()

        result = {
            "element": element,
            "name": ELEMENTS[element]["name"],
            "label": ELEMENTS[element]["label"],
            "old_absolute": old,
            "new_absolute": new_val,
            "delta": delta,
            "relative": self.get_relative(element),
            "reason": reason,
        }
        if evolution:
            result["evolution_triggered"] = evolution
        return result

    def get_absolute(self, element: str = None) -> Dict[str, int]:
        """取得絕對值."""
        if element:
            return {element: self._absolute.get(element, 0)}
        return dict(self._absolute)

    def get_relative(self, element: str = None) -> Any:
        """取得相對值（0-100，相對於最大元素）."""
        max_val = max(self._absolute.values()) if any(self._absolute.values()) else 1
        if max_val == 0:
            max_val = 1

        if element:
            return round(self._absolute.get(element, 0) / max_val * 100, 1)

        return {
            k: round(v / max_val * 100, 1) for k, v in self._absolute.items()
        }

    def get_total(self) -> int:
        """取得八元素總和."""
        return sum(self._absolute.values())

    def get_radar_data(self) -> Dict:
        """取得 Dashboard 雷達圖資料."""
        relatives = self.get_relative()
        return {
            "labels": [f"{ELEMENTS[k]['emoji']} {ELEMENTS[k]['name']}/{ELEMENTS[k]['label']}" for k in ELEMENTS],
            "values": [relatives[k] for k in ELEMENTS],
            "absolute": {k: self._absolute[k] for k in ELEMENTS},
            "total": self.get_total(),
        }

    def _check_evolution(self, changed_element: str) -> Optional[Dict]:
        """檢查是否觸發演化門檻."""
        for threshold in EVOLUTION_THRESHOLDS:
            key = threshold["key"]
            if key in self._triggered_thresholds:
                continue

            triggered = False
            trigger_element = None

            if threshold["type"] == "element":
                # 任一元素達標
                for elem, val in self._absolute.items():
                    if val >= threshold["value"]:
                        triggered = True
                        trigger_element = elem
                        break
            elif threshold["type"] == "total":
                if self.get_total() >= threshold["value"]:
                    triggered = True

            if triggered:
                self._triggered_thresholds.add(key)
                # 記錄演化事件
                if self._db:
                    self._db.log_evolution_event(
                        threshold=key,
                        element=trigger_element,
                        absolute_values=dict(self._absolute),
                    )
                return {
                    "threshold": key,
                    "label": threshold["label"],
                    "element": trigger_element,
                    "absolute_values": dict(self._absolute),
                }

        return None
