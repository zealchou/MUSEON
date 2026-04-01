"""Drift Detector — ANIMA 漂移偵測系統 v2.0.

每 10 次觀察後檢查 ANIMA 狀態與基線的連續相似度漂移分數。
- drift < 50%：寫入覺察日誌（drift_awareness.jsonl），不觸發任何暫停
- drift >= 50%：凍結 morphenix 提案（L2/L3 級），核心學習全繼續
- 基線採用 EMA 指數加權平滑，避免振盪
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DriftReport:
    """漂移偵測報告."""
    drift_score: float  # 0~1，加權漂移分數
    should_restrict_morphenix: bool  # 是否限制 morphenix 提案
    awareness_log: str = ""  # 自我覺察日誌文字
    details: List[Dict[str, Any]] = field(default_factory=list)
    checked_at: str = ""
    drift_direction: str = "neutral"           # "toward_user" | "away_from_user" | "stable" | "neutral"
    personality_capture_risk: float = 0.0      # 0-1, cosine similarity with user profile

    def to_dict(self) -> dict:
        return {
            "drift_score": round(self.drift_score, 4),
            "should_restrict_morphenix": self.should_restrict_morphenix,
            "awareness_log": self.awareness_log,
            "details": self.details,
            "checked_at": self.checked_at,
            "drift_direction": self.drift_direction,
            "personality_capture_risk": round(self.personality_capture_risk, 4),
        }


class DriftDetector:
    """ANIMA 漂移偵測器 v2.0.

    職責：
    1. 快照 ANIMA 基線（EMA 指數加權平滑）
    2. 週期性比較當前值與基線（連續相似度）
    3. 加權漂移分數 >= 50% → 限制 morphenix 提案
    4. 所有漂移檢查寫入覺察日誌
    """

    DRIFT_THRESHOLD = 0.50  # 50% — 極端漂移才觸發限制
    CHECK_INTERVAL = 10     # 每 10 次觀察後檢查
    EMA_ALPHA = 0.3         # EMA 平滑係數（新值權重 30%）

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
        self.awareness_log_path = data_dir / "anima" / "drift_awareness.jsonl"
        self.awareness_log_path.parent.mkdir(parents=True, exist_ok=True)

        self._observation_count = 0
        self._baseline: Optional[Dict[str, Any]] = None
        self._cumulative_drift: float = 0.0  # 累計漂移（不隨基線重置）

        # 載入既有基線
        if self.baseline_path.exists():
            try:
                self._baseline = json.loads(
                    self.baseline_path.read_text(encoding="utf-8")
                )
            except Exception as e:
                logger.warning(f"載入漂移基線失敗: {e}")

        logger.info("DriftDetector v2.0 初始化完成")

    def take_baseline(
        self,
        anima_mc: Dict[str, Any],
        anima_user: Dict[str, Any],
        force: bool = False,
    ) -> bool:
        """快照當前 ANIMA 狀態作為漂移基線.

        使用 EMA 指數加權平滑：new_baseline = α * current + (1-α) * old_baseline
        首次建立或 force=True 時直接快照。
        """
        current = self._extract_snapshot(anima_mc, anima_user)

        if self._baseline and not force:
            # EMA 平滑更新——數值欄位漸進調整
            baseline = self._ema_merge(self._baseline, current, self.EMA_ALPHA)
        else:
            baseline = current

        baseline["taken_at"] = datetime.now(timezone.utc).isoformat()

        try:
            self.baseline_path.write_text(
                json.dumps(baseline, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._baseline = baseline
            logger.info("漂移基線已更新（EMA 平滑）")
            return True
        except Exception as e:
            logger.error(f"寫入漂移基線失敗: {e}")
            return False

    def _extract_snapshot(
        self, anima_mc: Dict[str, Any], anima_user: Dict[str, Any]
    ) -> Dict[str, Any]:
        """從 ANIMA 狀態提取快照欄位."""
        return {
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

    def _ema_merge(
        self, old: Dict[str, Any], new: Dict[str, Any], alpha: float
    ) -> Dict[str, Any]:
        """EMA 指數加權合併基線（數值型欄位漸進調整，非數值型直接替換）."""
        merged = {}
        for key in set(list(old.keys()) + list(new.keys())):
            if key == "taken_at":
                continue
            old_val = old.get(key)
            new_val = new.get(key)
            if new_val is None:
                merged[key] = old_val
            elif old_val is None:
                merged[key] = new_val
            elif isinstance(old_val, dict) and isinstance(new_val, dict):
                merged[key] = self._ema_merge_dict(old_val, new_val, alpha)
            elif isinstance(old_val, list) and isinstance(new_val, list):
                merged[key] = new_val  # 列表型直接取新值
            else:
                merged[key] = new_val
        return merged

    def _ema_merge_dict(
        self, old: Dict[str, Any], new: Dict[str, Any], alpha: float
    ) -> Dict[str, Any]:
        """EMA 合併字典（遞迴處理巢狀數值）."""
        merged = {}
        for key in set(list(old.keys()) + list(new.keys())):
            old_val = old.get(key)
            new_val = new.get(key)
            if new_val is None:
                merged[key] = old_val
            elif old_val is None:
                merged[key] = new_val
            elif isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                merged[key] = alpha * new_val + (1 - alpha) * old_val
            elif isinstance(old_val, dict) and isinstance(new_val, dict):
                merged[key] = self._ema_merge_dict(old_val, new_val, alpha)
            else:
                merged[key] = new_val
        return merged

    def should_check(self) -> bool:
        """是否應該進行漂移檢查（每 CHECK_INTERVAL 次觀察一次）."""
        self._observation_count += 1
        return self._observation_count % self.CHECK_INTERVAL == 0

    def check_drift(
        self,
        anima_mc: Dict[str, Any],
        anima_user: Dict[str, Any],
    ) -> DriftReport:
        """比較當前值與基線，計算連續相似度加權漂移分數.

        v2.0 改進：
        - 連續相似度取代二進制比較
        - 50% 極端閾值取代 15%
        - 每次檢查都 EMA 微調基線
        - 寫入覺察日誌而非觸發暫停
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        drift_direction = "neutral"
        personality_capture_risk = 0.0

        if not self._baseline:
            self.take_baseline(anima_mc, anima_user, force=True)
            return DriftReport(
                drift_score=0.0,
                should_restrict_morphenix=False,
                awareness_log="首次建立基線",
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

        # 3. L6 風格變化（改用連續相似度）
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
        should_restrict = weighted_sum >= self.DRIFT_THRESHOLD

        # 生成覺察日誌
        awareness = self._generate_awareness_log(weighted_sum, details, should_restrict)

        # ── Directional drift analysis (Phase 8) ──
        try:
            from museon.agent.momentum_brake import MomentumBrake
            mb = MomentumBrake()

            # Get trait_history for directional analysis
            trait_history = anima_mc.get("evolution", {}).get("trait_history", [])
            if trait_history:
                directional = mb.compute_directional_drift(trait_history, days=7)
                # Determine overall direction
                positive_drifts = sum(1 for v in directional.values() if v.get("direction") == "positive")
                negative_drifts = sum(1 for v in directional.values() if v.get("direction") == "negative")
                if positive_drifts > negative_drifts + 1:
                    drift_direction = "positive_bias"
                elif negative_drifts > positive_drifts + 1:
                    drift_direction = "negative_bias"
                else:
                    drift_direction = "stable"

            # Check personality capture risk
            user_primals = anima_user.get("eight_primals", {}) if anima_user else {}
            if trait_history and user_primals:
                # Get recent trait deltas
                cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
                recent_deltas = {}
                for entry in trait_history:
                    if entry.get("at", "") >= cutoff:
                        tid = entry.get("trait", "")
                        recent_deltas[tid] = recent_deltas.get(tid, 0) + entry.get("delta", entry.get("new", 0) - entry.get("old", 0))

                if recent_deltas:
                    user_primal_levels = {
                        k: v.get("level", 0) if isinstance(v, dict) else v
                        for k, v in user_primals.items()
                    }
                    capture_risk, capture_dir = mb.check_capture_risk(recent_deltas, user_primal_levels)
                    personality_capture_risk = capture_risk
                    if capture_dir == "toward_user":
                        drift_direction = "toward_user"
                    elif capture_dir == "away_from_user":
                        drift_direction = "away_from_user"
        except Exception as e:
            logger.debug(f"Directional drift analysis skipped: {e}")

        report = DriftReport(
            drift_score=weighted_sum,
            should_restrict_morphenix=should_restrict,
            awareness_log=awareness,
            details=details,
            checked_at=now_iso,
            drift_direction=drift_direction,
            personality_capture_risk=personality_capture_risk,
        )

        # 累計漂移追蹤（不隨基線重置）
        self._cumulative_drift = max(self._cumulative_drift, weighted_sum)

        # 記錄漂移日誌
        self._log_drift(report)

        # 寫入覺察日誌（每次檢查都寫）
        self._log_awareness(report)

        # 每次檢查都 EMA 微調基線（消除振盪）
        self.take_baseline(anima_mc, anima_user)

        if should_restrict:
            logger.warning(
                f"ANIMA 漂移極端: {weighted_sum:.1%} >= {self.DRIFT_THRESHOLD:.0%} "
                f"→ morphenix 提案受限"
            )
        else:
            logger.info(f"ANIMA 漂移正常: {weighted_sum:.1%}")

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
        """計算風格型資料的連續相似度漂移.

        v2.0：取代二進制 != 比較
        - 數值型：abs(old - new) / max(abs(old), abs(new), 1e-6)
        - 字串型：1 - SequenceMatcher.ratio()
        - 列表型：Jaccard distance
        - 最終取加權平均
        """
        if not old or not new:
            return 0.0

        all_keys = set(list(old.keys()) + list(new.keys()))
        if not all_keys:
            return 0.0

        total_drift = 0.0
        count = 0
        for key in all_keys:
            old_val = old.get(key)
            new_val = new.get(key)
            if old_val is None and new_val is None:
                continue
            count += 1

            if old_val is None or new_val is None:
                total_drift += 1.0  # 新增或消失的欄位 = 完全漂移
            elif isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                # 數值型：連續差異比率
                max_abs = max(abs(old_val), abs(new_val), 1e-6)
                total_drift += abs(old_val - new_val) / max_abs
            elif isinstance(old_val, str) and isinstance(new_val, str):
                # 字串型：序列相似度
                ratio = SequenceMatcher(None, old_val, new_val).ratio()
                total_drift += 1.0 - ratio
            elif isinstance(old_val, list) and isinstance(new_val, list):
                # 列表型：Jaccard distance
                total_drift += self._jaccard_distance(old_val, new_val)
            elif isinstance(old_val, dict) and isinstance(new_val, dict):
                # 巢狀字典：遞迴計算
                total_drift += self._compute_style_drift(old_val, new_val)
            else:
                # 類型不同 = 完全漂移
                total_drift += 1.0 if old_val != new_val else 0.0

        return min(1.0, total_drift / max(count, 1))

    @staticmethod
    def _jaccard_distance(a: List[Any], b: List[Any]) -> float:
        """Jaccard distance for lists."""
        set_a = set(str(x) for x in a)
        set_b = set(str(x) for x in b)
        if not set_a and not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return 1.0 - (intersection / max(union, 1))

    # ─── 覺察日誌 ─────────────────────────

    def _generate_awareness_log(
        self, drift_score: float, details: List[Dict], is_extreme: bool
    ) -> str:
        """生成自我覺察日誌文字."""
        top_dims = sorted(details, key=lambda d: d["drift"], reverse=True)[:3]
        dim_desc = ", ".join(
            f'{d["dimension"]}({d["drift"]:.1%})' for d in top_dims if d["drift"] > 0.01
        )

        if is_extreme:
            return (
                f"極端漂移 {drift_score:.1%}：{dim_desc}。"
                f"morphenix 提案已限制，核心學習繼續。"
            )
        elif drift_score > 0.20:
            return f"中等漂移 {drift_score:.1%}：{dim_desc}。持續觀察中。"
        elif drift_score > 0.05:
            return f"輕微漂移 {drift_score:.1%}：{dim_desc}。正常範圍。"
        else:
            return f"穩定 {drift_score:.1%}。無顯著變化。"

    def _log_awareness(self, report: DriftReport) -> None:
        """Append-only 覺察日誌."""
        try:
            entry = {
                "timestamp": report.checked_at,
                "drift_score": round(report.drift_score, 4),
                "restricted": report.should_restrict_morphenix,
                "awareness": report.awareness_log,
            }
            with open(self.awareness_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"覺察日誌寫入失敗: {e}")

    # ─── 日誌 ─────────────────────────

    def _log_drift(self, report: DriftReport) -> None:
        """Append-only 漂移日誌."""
        try:
            with open(self.drift_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(report.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"漂移日誌寫入失敗: {e}")
