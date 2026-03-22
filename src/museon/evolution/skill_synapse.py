"""SkillSynapse — 技能突觸連結網路.

模擬生物突觸的 Skill 共振機制：
  - 兩個 Skill 同時被使用（co-fire）→ 連結權重增強
  - 每日衰減（daily_decay）→ 不常用的連結漸弱
  - 高權重連結 → 預載候選（preload_candidates）

生物隱喻：
  "Neurons that fire together, wire together." — Hebb's Rule

設計原則：
  - 零 LLM 依賴，純 CPU 啟發式
  - JSON 持久化
  - co_fire → +0.05, daily_decay → ×0.98
  - preload 門檻 → weight > 0.7
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

CO_FIRE_INCREMENT = 0.05       # 共振增量
DAILY_DECAY_RATE = 0.98        # 每日衰減率
PRELOAD_THRESHOLD = 0.7        # 預載門檻
PRUNE_THRESHOLD = 0.01         # 修剪門檻（低於此值移除）
MAX_SYNAPSES = 500             # 最大突觸數量

# Skill 名稱合法性：只允許小寫字母、數字、連字號（防幽靈 Skill 汙染）
_VALID_SKILL_NAME_RE = re.compile(r'^[a-z][a-z0-9\-]{0,60}$')


# ═══════════════════════════════════════════
# SkillSynapse 資料模型
# ═══════════════════════════════════════════


@dataclass
class SkillSynapse:
    """單個技能突觸連結."""

    skill_a: str                        # Skill A 名稱
    skill_b: str                        # Skill B 名稱
    weight: float = 0.0                 # 連結權重（0.0 ~ 1.0）
    fire_count: int = 0                 # 共振次數
    last_fired: str = ""                # 最後共振時間
    created_at: str = ""                # 建立時間

    @property
    def key(self) -> str:
        """正規化 key（排序後組合）."""
        a, b = sorted([self.skill_a, self.skill_b])
        return f"{a}::{b}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SkillSynapse":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════
# SynapseNetwork — 突觸網路
# ═══════════════════════════════════════════


class SynapseNetwork:
    """技能突觸連結網路.

    提供：
      - co_fire(a, b)：兩技能共振 → 權重 +0.05
      - daily_decay()：所有突觸 ×0.98
      - get_preload_candidates(skill)：取得預載候選
      - get_strongest_connections()：取得最強連結
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self._synapses: Dict[str, SkillSynapse] = {}
        self._data_dir = data_dir
        self._file_path: Optional[Path] = None

        if data_dir:
            self._file_path = Path(data_dir) / "_system" / "synapses.json"
            self._file_path.parent.mkdir(parents=True, exist_ok=True)

        self._load()
        logger.info("SynapseNetwork 初始化: %d 個突觸", len(self._synapses))

    def co_fire(self, skill_a: str, skill_b: str) -> float:
        """兩技能共振 — Hebb's Rule.

        Args:
            skill_a: Skill A 名稱
            skill_b: Skill B 名稱

        Returns:
            更新後的權重
        """
        if skill_a == skill_b:
            return 0.0

        # 防護：拒絕非法 Skill 名稱（防幽靈 Skill 汙染突觸網路）
        if not _VALID_SKILL_NAME_RE.match(skill_a) or not _VALID_SKILL_NAME_RE.match(skill_b):
            logger.warning("co_fire 拒絕非法 Skill 名稱: %r / %r", skill_a, skill_b)
            return 0.0

        key = self._make_key(skill_a, skill_b)
        now = datetime.now(timezone.utc).isoformat()

        if key not in self._synapses:
            if len(self._synapses) >= MAX_SYNAPSES:
                self._prune_weakest()

            a, b = sorted([skill_a, skill_b])
            self._synapses[key] = SkillSynapse(
                skill_a=a,
                skill_b=b,
                weight=CO_FIRE_INCREMENT,
                fire_count=1,
                last_fired=now,
                created_at=now,
            )
        else:
            syn = self._synapses[key]
            syn.weight = min(1.0, syn.weight + CO_FIRE_INCREMENT)
            syn.fire_count += 1
            syn.last_fired = now

        self._save()
        return self._synapses[key].weight

    def daily_decay(self) -> Dict[str, int]:
        """每日衰減 — 所有突觸權重 ×0.98.

        由 NightlyPipeline step_20 呼叫。

        Returns:
            {"decayed": N, "pruned": M}
        """
        decayed = 0
        to_prune: List[str] = []

        for key, syn in self._synapses.items():
            syn.weight *= DAILY_DECAY_RATE
            decayed += 1

            if syn.weight < PRUNE_THRESHOLD:
                to_prune.append(key)

        for key in to_prune:
            del self._synapses[key]

        self._save()

        result = {"decayed": decayed, "pruned": len(to_prune)}
        if to_prune:
            logger.info("SynapseNetwork decay: %s", result)
        return result

    def get_preload_candidates(self, skill: str) -> List[str]:
        """取得預載候選 — 與指定 skill 連結權重 > 0.7 的 skill.

        Args:
            skill: 當前使用的 Skill 名稱

        Returns:
            預載候選 skill 名稱列表（按權重降序）
        """
        candidates: List[Tuple[str, float]] = []

        for syn in self._synapses.values():
            if syn.weight < PRELOAD_THRESHOLD:
                continue
            if syn.skill_a == skill:
                candidates.append((syn.skill_b, syn.weight))
            elif syn.skill_b == skill:
                candidates.append((syn.skill_a, syn.weight))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in candidates]

    def get_strongest_connections(self, limit: int = 10) -> List[Dict[str, Any]]:
        """取得最強連結.

        Args:
            limit: 最大回傳數量

        Returns:
            按權重降序排列的突觸列表
        """
        sorted_synapses = sorted(
            self._synapses.values(),
            key=lambda s: s.weight,
            reverse=True,
        )
        return [
            {
                "skill_a": s.skill_a,
                "skill_b": s.skill_b,
                "weight": round(s.weight, 4),
                "fire_count": s.fire_count,
            }
            for s in sorted_synapses[:limit]
        ]

    def get_connections_for(self, skill: str) -> List[Dict[str, Any]]:
        """取得某 skill 的所有連結.

        Args:
            skill: Skill 名稱

        Returns:
            相關突觸列表
        """
        result = []
        for syn in self._synapses.values():
            if syn.skill_a == skill or syn.skill_b == skill:
                other = syn.skill_b if syn.skill_a == skill else syn.skill_a
                result.append({
                    "connected_skill": other,
                    "weight": round(syn.weight, 4),
                    "fire_count": syn.fire_count,
                })
        result.sort(key=lambda x: x["weight"], reverse=True)
        return result

    def get_stats(self) -> Dict[str, Any]:
        """取得網路統計."""
        if not self._synapses:
            return {
                "total_synapses": 0,
                "avg_weight": 0.0,
                "max_weight": 0.0,
                "preload_count": 0,
            }

        weights = [s.weight for s in self._synapses.values()]
        return {
            "total_synapses": len(self._synapses),
            "avg_weight": round(sum(weights) / len(weights), 4),
            "max_weight": round(max(weights), 4),
            "preload_count": sum(1 for w in weights if w >= PRELOAD_THRESHOLD),
        }

    # ─── 內部方法 ─────────────────────────

    def _make_key(self, skill_a: str, skill_b: str) -> str:
        a, b = sorted([skill_a, skill_b])
        return f"{a}::{b}"

    def _prune_weakest(self) -> None:
        """修剪最弱的突觸（達到 MAX_SYNAPSES 時）."""
        if len(self._synapses) < MAX_SYNAPSES:
            return
        sorted_keys = sorted(
            self._synapses.keys(),
            key=lambda k: self._synapses[k].weight,
        )
        # 移除最弱的 10%
        to_remove = sorted_keys[:max(1, len(sorted_keys) // 10)]
        for key in to_remove:
            del self._synapses[key]

    def _load(self) -> None:
        """從檔案載入."""
        if not self._file_path or not self._file_path.exists():
            return
        try:
            raw = json.loads(self._file_path.read_text(encoding="utf-8"))
            for key, data in raw.items():
                self._synapses[key] = SkillSynapse.from_dict(data)
        except Exception as e:
            logger.warning("SynapseNetwork 載入失敗: %s", e)

    def _save(self) -> None:
        """持久化到檔案."""
        if not self._file_path:
            return
        try:
            data = {k: v.to_dict() for k, v in self._synapses.items()}
            self._file_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("SynapseNetwork 儲存失敗: %s", e)
