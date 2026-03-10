"""Drift Detector — ANIMA 漂移偵測系統.

每 10 次觀察後檢查 ANIMA 狀態與基線的加權漂移分數，
超過 15% 閾值則暫停演化 + 通知 Zeal。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DriftReport:
    """漂移偵測報告."""
    drift_score: float  # 0~1，加權漂移分數
    should_pause: bool
    details: List[Dict[str, Any]] = field(default_factory=list)
    checked_at: str = ""

    def to_dict(self) -> dict:
        return {
            "drift_score": round(self.drift_score, 4),
            "should_pause": self.should_pause,
            "details": self.details,
            "checked_at": self.checked_at,
        }


class DriftDetector:
    """ANIMA 漂移偵測器.

    職責：
    1. 快照 ANIMA 基線
    2. 週期性比較當前值與基線
    3. 加權漂移分數 > 15% → 暫停演化
    """

    DRIFT_THRESHOLD = 0.15  # 15%
    CHECK_INTERVAL = 10     # 每 10 次觀察後檢查
    MIN_BASELINE_INTERVAL_S = 3600 * 4  # 4 小時最短基線重建間隔

    # 加權維度
    WEIGHTS = {
        "eight_primals": 0.30,
        "L5_preference_crystals": 0.20,
        "L6_communication_style": 0.20,
        "L7_context_roles": 0.15,
        "expression_style": 0.15,
    }

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.baseline_path = data_dir / "anima" / "drift_baseline.json"
        self.baseline_path.parent.mkdir(parents=True, exist_ok=True)
        self.drift_log_path = data_dir / "guardian" / "drift_log.jsonl"
        self.drift_log_path.parent.mkdir(parents=True, exist_ok=True)

        self._observation_count = 0
        self._baseline: Optional[Dict[str, Any]] = None
        self._last_baseline_ts: float = 0.0  # 上次基線建立時間戳
        self._cumulative_drift: float = 0.0  # 累計漂移（不隨基線重置）

        # 載入既有基線
        if self.baseline_path.exists():
            try:
                self._baseline = json.loads(
                    self.baseline_path.read_text(encoding="utf-8")
                )
                # 從基線的 taken_at 推算時間戳
                taken_at = self._baseline.get("taken_at", "")
                if taken_at:
                    from datetime import datetime as _dt
                    try:
                        self._last_baseline_ts = _dt.fromisoformat(taken_at).timestamp()
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"載入漂移基線失敗: {e}")

        logger.info("DriftDetector 初始化完成")

    def take_baseline(
        self,
        anima_mc: Dict[str, Any],
        anima_user: Dict[str, Any],
        force: bool = False,
    ) -> bool:
        """快照當前 ANIMA 狀態作為漂移基線.

        Returns:
            是否成功建立基線（間隔不足時跳過，返回 False）
        """
        import time as _time
        now = _time.time()

        # 防止過於頻繁重建基線（最少間隔 4 小時）
        if not force and self._last_baseline_ts > 0:
            elapsed = now - self._last_baseline_ts
            if elapsed < self.MIN_BASELINE_INTERVAL_S:
                logger.info(
                    f"漂移基線重建跳過：距上次僅 {elapsed/3600:.1f}h "
                    f"(需 {self.MIN_BASELINE_INTERVAL_S/3600:.0f}h)"
                )
                return False

        baseline = {
            "taken_at": datetime.now(timezone.utc).isoformat(),
            "mc_primals": anima_mc.get("eight_primal_energies", anima_mc.get("eight_primals", {})),
            "mc_expression": anima_mc.get("self_awareness", {}).get(
                "expression_style", {}
            ),
            "user_primals": anima_user.get("eight_primals", {}),
            "user_L5": anima_user.get("seven_layers", {}).get(
                "L5_preference_crystals", []
            ),
            "user_L6": anima_user.get("seven_layers", {}).get(
                "L6_communication_style", {}
            ),
            "user_L7": anima_user.get("seven_layers", {}).get(
                "L7_context_roles", []
            ),
        }
        try:
            self.baseline_path.write_text(
                json.dumps(baseline, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._baseline = baseline
            self._last_baseline_ts = now
            logger.info("漂移基線已建立")
            return True
        except Exception as e:
            logger.error(f"寫入漂移基線失敗: {e}")
            return False

    def should_check(self) -> bool:
        """是否應該進行漂移檢查（每 CHECK_INTERVAL 次觀察一次）."""
        self._observation_count += 1
        return self._observation_count % self.CHECK_INTERVAL == 0

    def check_drift(
        self,
        anima_mc: Dict[str, Any],
        anima_user: Dict[str, Any],
    ) -> DriftReport:
        """比較當前值與基線，計算加權漂移分數."""
        now_iso = datetime.now(timezone.utc).isoformat()

        if not self._baseline:
            # 沒有基線 → 建立基線，不報告漂移
            self.take_baseline(anima_mc, anima_user)
            return DriftReport(
                drift_score=0.0,
                should_pause=False,
                details=[{"note": "首次建立基線"}],
                checked_at=now_iso,
            )

        details = []
        weighted_sum = 0.0

        # 1. 八原語漂移 (MC + USER 混合)
        primals_drift = self._compute_primals_drift(
            self._baseline.get("user_primals", {}),
            anima_user.get("eight_primals", {}),
        )
        weighted_sum += primals_drift * self.WEIGHTS["eight_primals"]
        details.append({
            "dimension": "eight_primals",
            "drift": round(primals_drift, 4),
            "weight": self.WEIGHTS["eight_primals"],
        })

        # 2. L5 偏好變化
        l5_drift = self._compute_list_drift(
            self._baseline.get("user_L5", []),
            anima_user.get("seven_layers", {}).get("L5_preference_crystals", []),
        )
        weighted_sum += l5_drift * self.WEIGHTS["L5_preference_crystals"]
        details.append({
            "dimension": "L5_preference_crystals",
            "drift": round(l5_drift, 4),
            "weight": self.WEIGHTS["L5_preference_crystals"],
        })

        # 3. L6 風格變化
        l6_drift = self._compute_style_drift(
            self._baseline.get("user_L6", {}),
            anima_user.get("seven_layers", {}).get("L6_communication_style", {}),
        )
        weighted_sum += l6_drift * self.WEIGHTS["L6_communication_style"]
        details.append({
            "dimension": "L6_communication_style",
            "drift": round(l6_drift, 4),
            "weight": self.WEIGHTS["L6_communication_style"],
        })

        # 4. L7 角色變化
        l7_drift = self._compute_list_drift(
            self._baseline.get("user_L7", []),
            anima_user.get("seven_layers", {}).get("L7_context_roles", []),
        )
        weighted_sum += l7_drift * self.WEIGHTS["L7_context_roles"]
        details.append({
            "dimension": "L7_context_roles",
            "drift": round(l7_drift, 4),
            "weight": self.WEIGHTS["L7_context_roles"],
        })

        # 5. 表達風格變化
        expr_drift = self._compute_style_drift(
            self._baseline.get("mc_expression", {}),
            anima_mc.get("self_awareness", {}).get("expression_style", {}),
        )
        weighted_sum += expr_drift * self.WEIGHTS["expression_style"]
        details.append({
            "dimension": "expression_style",
            "drift": round(expr_drift, 4),
            "weight": self.WEIGHTS["expression_style"],
        })

        # 最終漂移分數
        should_pause = weighted_sum > self.DRIFT_THRESHOLD

        report = DriftReport(
            drift_score=weighted_sum,
            should_pause=should_pause,
            details=details,
            checked_at=now_iso,
        )

        # 累計漂移追蹤（不隨基線重置）
        self._cumulative_drift = max(self._cumulative_drift, weighted_sum)

        # 記錄漂移日誌
        self._log_drift(report)

        # 如果漂移過大，嘗試更新基線（受最短間隔保護）
        if should_pause:
            logger.warning(
                f"ANIMA 漂移超過閾值: {weighted_sum:.1%} > {self.DRIFT_THRESHOLD:.0%} "
                f"(累計最高: {self._cumulative_drift:.1%})"
            )
            rebuilt = self.take_baseline(anima_mc, anima_user)
            if rebuilt:
                logger.info("漂移基線已重建（暫停觸發後自動更新）")
            else:
                logger.info("漂移基線未重建（最短間隔保護）")

        return report

    # ─── 內部計算 ─────────────────────────

    def _compute_primals_drift(
        self, old: Dict[str, Any], new: Dict[str, Any]
    ) -> float:
        """計算八原語 level 的平均漂移."""
        if not old or not new:
            return 0.0

        total_drift = 0.0
        count = 0
        for key in set(list(old.keys()) + list(new.keys())):
            old_level = old.get(key, {}).get("level", 0) if isinstance(old.get(key), dict) else 0
            new_level = new.get(key, {}).get("level", 0) if isinstance(new.get(key), dict) else 0
            if old_level > 0:
                total_drift += abs(new_level - old_level) / max(old_level, 1)
            elif new_level > 0:
                total_drift += 1.0
            count += 1

        return total_drift / max(count, 1)

    def _compute_list_drift(
        self, old: List[Any], new: List[Any]
    ) -> float:
        """計算列表型資料的漂移（基於長度和內容變化）."""
        old_len = len(old) if old else 0
        new_len = len(new) if new else 0

        if old_len == 0 and new_len == 0:
            return 0.0

        # 長度變化比率
        len_drift = abs(new_len - old_len) / max(old_len, new_len, 1)

        return min(1.0, len_drift)

    def _compute_style_drift(
        self, old: Dict[str, Any], new: Dict[str, Any]
    ) -> float:
        """計算風格型資料的漂移（基於欄位值變化）."""
        if not old or not new:
            return 0.0

        all_keys = set(list(old.keys()) + list(new.keys()))
        if not all_keys:
            return 0.0

        changed = 0
        total = 0
        for key in all_keys:
            old_val = old.get(key)
            new_val = new.get(key)
            if old_val is None and new_val is None:
                continue
            total += 1
            if old_val != new_val:
                changed += 1

        return changed / max(total, 1)

    # ─── 日誌 ─────────────────────────

    def _log_drift(self, report: DriftReport) -> None:
        """Append-only 漂移日誌."""
        try:
            with open(self.drift_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(report.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"漂移日誌寫入失敗: {e}")
