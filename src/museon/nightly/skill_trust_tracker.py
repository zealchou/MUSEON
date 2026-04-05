"""skill_trust_tracker.py — Skill 信任分數追蹤器（Trust Tracker Prototype）.

設計原則：
- 純 CPU 運算，不依賴 LLM
- JSON 檔案持久化到 data/_system/skill_trust_scores.json
- 三個信任等級：T1 / T2 / T3
- 預設分數：內部 Skill = 0.9，外部 Skill = 0.3
- 更新機制：Q-Score 評估後由 SkillHealthTracker 呼叫 update_trust_score()

信任等級說明：
  T1 (< 0.4)  — 僅允許 instruction-only，不可呼叫工具
  T2 (0.4-0.7) — 有限工具存取（唯讀、無網路）
  T3 (> 0.7)  — 完整能力（預設內部 Skill 等級）
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# 信任等級邊界
TRUST_T1_MAX = 0.4   # T1: 低信任，instruction only
TRUST_T2_MAX = 0.7   # T2: 中信任，有限工具
# T3: > 0.7，完整能力

# 預設分數
DEFAULT_TRUST_INTERNAL = 0.9   # 內部 Skill 預設
DEFAULT_TRUST_EXTERNAL = 0.3   # 外部 Skill 預設（未經驗證）

# 分數邊界
SCORE_MIN = 0.0
SCORE_MAX = 1.0

# 分數衰減上下限（每次 update）
DELTA_MIN = -0.5   # 最多一次減 0.5
DELTA_MAX = 0.2    # 最多一次加 0.2


class SkillTrustTracker:
    """Skill 信任分數追蹤器.

    使用方式：
        tracker = SkillTrustTracker(workspace=Path("~/MUSEON").expanduser())
        score = tracker.get_trust_score("brand-builder")
        tracker.update_trust_score("external-discovery", delta=-0.1)
        tier = tracker.get_trust_tier("external-discovery")
        tracker.persist()
    """

    def __init__(self, workspace: Path) -> None:
        """初始化信任追蹤器.

        Args:
            workspace: MUSEON 根目錄（~/MUSEON）
        """
        self._workspace = workspace
        self._scores_path = workspace / "data" / "_system" / "skill_trust_scores.json"
        self._scores: Dict[str, dict] = {}
        self._load()

    # -------------------------------------------------------------------------
    # 公開介面
    # -------------------------------------------------------------------------

    def get_trust_score(self, skill_name: str, origin: str = "internal") -> float:
        """取得指定 Skill 的信任分數.

        若 Skill 尚未有記錄，回傳預設值（internal=0.9 / external=0.3）。

        Args:
            skill_name: Skill 名稱
            origin: "internal" | "external"（僅在首次建立紀錄時使用）

        Returns:
            0.0 ~ 1.0 的信任分數
        """
        if skill_name in self._scores:
            return float(self._scores[skill_name].get("score", DEFAULT_TRUST_INTERNAL))

        # 首次查詢，根據 origin 回傳預設值（不寫入，等 persist 時一起）
        default = DEFAULT_TRUST_INTERNAL if origin == "internal" else DEFAULT_TRUST_EXTERNAL
        return default

    def update_trust_score(self, skill_name: str, delta: float, origin: str = "internal") -> float:
        """更新指定 Skill 的信任分數.

        Args:
            skill_name: Skill 名稱
            delta: 分數變化量（正 = 提升信任，負 = 降低信任）
            origin: "internal" | "external"（首次建立紀錄時使用）

        Returns:
            更新後的分數
        """
        # 限制 delta 範圍，防止單次暴力修改
        delta = max(DELTA_MIN, min(DELTA_MAX, delta))

        # 取得現有分數（或預設值）
        current = self.get_trust_score(skill_name, origin)

        # 計算新分數，限制在 [0.0, 1.0]
        new_score = max(SCORE_MIN, min(SCORE_MAX, current + delta))
        new_score = round(new_score, 4)

        # 更新記錄
        self._scores[skill_name] = {
            "score": new_score,
            "origin": self._scores.get(skill_name, {}).get("origin", origin),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        logger.debug(
            "TrustTracker: %s %s → %.4f (delta=%.3f)",
            skill_name, current, new_score, delta,
        )
        return new_score

    def get_trust_tier(self, skill_name: str, origin: str = "internal") -> str:
        """取得信任等級.

        Returns:
            "T1" | "T2" | "T3"
        """
        score = self.get_trust_score(skill_name, origin)
        if score < TRUST_T1_MAX:
            return "T1"
        elif score <= TRUST_T2_MAX:
            return "T2"
        else:
            return "T3"

    def ensure_skill_registered(self, skill_name: str, origin: str = "internal") -> None:
        """確保 Skill 已有信任記錄，若無則以預設值建立.

        Args:
            skill_name: Skill 名稱
            origin: "internal" | "external"
        """
        if skill_name not in self._scores:
            default = DEFAULT_TRUST_INTERNAL if origin == "internal" else DEFAULT_TRUST_EXTERNAL
            self._scores[skill_name] = {
                "score": default,
                "origin": origin,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

    def get_all_scores(self) -> Dict[str, dict]:
        """取得所有 Skill 的信任記錄.

        Returns:
            {skill_name: {"score": float, "origin": str, "last_updated": str}}
        """
        return dict(self._scores)

    def list_low_trust_skills(self, threshold: float = TRUST_T2_MAX) -> list:
        """列出低信任 Skill（score <= threshold）.

        Args:
            threshold: 門檻值（預設 T2 邊界 0.7）

        Returns:
            [(skill_name, score, tier), ...]，按分數升序排列
        """
        low = []
        for name, data in self._scores.items():
            score = float(data.get("score", 0.0))
            if score <= threshold:
                low.append((name, score, self.get_trust_tier(name)))
        low.sort(key=lambda x: x[1])
        return low

    def persist(self) -> bool:
        """將當前信任分數持久化到 JSON 檔案.

        Returns:
            True = 成功，False = 失敗
        """
        try:
            self._scores_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._scores_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._scores, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.rename(self._scores_path)
            logger.debug("TrustTracker: persisted %d skills", len(self._scores))
            return True
        except Exception as exc:
            logger.error("TrustTracker persist failed: %s", exc)
            return False

    # -------------------------------------------------------------------------
    # 私有方法
    # -------------------------------------------------------------------------

    def _load(self) -> None:
        """從 JSON 檔案載入信任分數（檔案不存在則初始化空字典）."""
        if not self._scores_path.exists():
            self._scores = {}
            return
        try:
            raw = json.loads(self._scores_path.read_text(encoding="utf-8"))
            # 驗證格式
            if isinstance(raw, dict):
                self._scores = raw
            else:
                logger.warning("TrustTracker: invalid format in %s, resetting", self._scores_path)
                self._scores = {}
        except Exception as exc:
            logger.warning("TrustTracker load failed: %s", exc)
            self._scores = {}


# ─────────────────────────────────────────────────────────
# 模組層級便利函數（供 nightly_pipeline 直接呼叫）
# ─────────────────────────────────────────────────────────

def get_trust_score(skill_name: str, workspace: Optional[Path] = None, origin: str = "internal") -> float:
    """便利函數：取得信任分數（自動建立 tracker 實例）."""
    ws = workspace or Path("data")
    tracker = SkillTrustTracker(workspace=ws)
    return tracker.get_trust_score(skill_name, origin)


def update_trust_score(skill_name: str, delta: float, workspace: Optional[Path] = None, origin: str = "internal") -> float:
    """便利函數：更新信任分數並持久化."""
    ws = workspace or Path("data")
    tracker = SkillTrustTracker(workspace=ws)
    new_score = tracker.update_trust_score(skill_name, delta, origin)
    tracker.persist()
    return new_score
