"""PeriodicCycles — 週期性演化循環（週報 + 月報）.

擴展每日 NightlyPipeline，提供更長期的反饋迴路：
  - WeeklyCycle: 每週日 03:30 執行（緊接在 NightlyPipeline 之後）
  - MonthlyCycle: 每月 1 日 04:00 執行

設計原則：
  - 每步獨立錯誤隔離（_safe_step），單步失敗不中斷整條管線
  - 外部模組一律 try/except ImportError
  - 所有 IO 操作包裹 try/except
  - 零 LLM 依賴
  - 報告以人類可讀的繁體中文 Markdown 輸出
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

TZ_TAIPEI = timezone(timedelta(hours=8))

# 排程時間
WEEKLY_CRON_HOUR = 3
WEEKLY_CRON_MINUTE = 30
MONTHLY_CRON_HOUR = 4
MONTHLY_CRON_MINUTE = 0

# 報告截斷上限
REPORT_TRUNCATE_CHARS = 200

# ANIMA 八元素鍵值
ANIMA_ELEMENTS = ("qian", "kun", "zhen", "xun", "kan", "li", "gen", "dui")
ANIMA_ELEMENT_NAMES = {
    "qian": "乾（身份/使命）",
    "kun": "坤（記憶/積累）",
    "zhen": "震（行動/執行）",
    "xun": "巽（好奇/探索）",
    "kan": "坎（共振/連結）",
    "li": "離（覺察/洞見）",
    "gen": "艮（邊界/守護）",
    "dui": "兌（連結/互動）",
}

# ANIMA 趨勢偵測
ANIMA_IMBALANCE_RATIO = 3.0  # 最大 / 最小超過此比例視為失衡

# 技能生態健康
SKILL_OVERUSE_THRESHOLD = 50   # 月使用超過此次數視為過度使用
SKILL_UNUSED_THRESHOLD = 0     # 月使用等於此數視為未使用

# 月度 Morphenix L3 觸發：連續 N 天出現相同失敗模式
L3_CONSISTENT_FAILURE_DAYS = 7


# ═══════════════════════════════════════════
# 工具函式
# ═══════════════════════════════════════════


def _read_json(path: Path) -> Optional[Dict]:
    """安全讀取 JSON 檔案."""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"讀取 JSON 失敗 ({path}): {e}")
    return None


def _read_jsonl(path: Path) -> List[Dict]:
    """安全讀取 JSONL 檔案，回傳所有行."""
    results: List[Dict] = []
    try:
        if not path.exists():
            return results
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.warning(f"讀取 JSONL 失敗 ({path}): {e}")
    return results


def _write_json(path: Path, data: Any) -> None:
    """安全寫入 JSON 檔案."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.rename(path)
    except Exception as e:
        logger.error(f"寫入 JSON 失敗 ({path}): {e}")


def _write_markdown(path: Path, content: str) -> None:
    """安全寫入 Markdown 檔案."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.rename(path)
    except Exception as e:
        logger.error(f"寫入 Markdown 失敗 ({path}): {e}")


def _trend_arrow(current: float, previous: float) -> str:
    """回傳趨勢箭頭符號."""
    if current > previous + 0.005:
        return "↑"
    elif current < previous - 0.005:
        return "↓"
    return "→"


def _iso_week_str(dt: datetime) -> str:
    """回傳 ISO 週字串，例如 2026-W10."""
    cal = dt.isocalendar()
    return f"{cal[0]}-W{cal[1]:02d}"


# ═══════════════════════════════════════════
# WeeklyCycle
# ═══════════════════════════════════════════


class WeeklyCycle:
    """每週演化循環 — 每週日 03:30 執行.

    五個步驟：
      1. 參數調諧（ParameterTuner.tune_weekly）
      2. 演化速度計算（EvolutionVelocity.calculate_weekly）
      3. 知識晶格深層再結晶（跨週合併掃描）
      4. 預判校準（MetaCognition 準確率趨勢分析）
      5. 週報生成
    """

    def __init__(
        self,
        workspace: Path,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._workspace = Path(workspace)
        self._event_bus = event_bus

    def run(self) -> Dict:
        """執行週期循環.

        Returns:
            執行報告（steps 為 dict 格式）
        """
        started_at = datetime.now(TZ_TAIPEI)
        start = time.time()

        self._publish("WEEKLY_CYCLE_STARTED", {
            "started_at": started_at.isoformat(),
        })

        # 各步驟的累積結果
        context: Dict[str, Any] = {}

        steps_dict: Dict[str, Dict] = {}

        # Step 1: 參數調諧
        result = self._safe_step(
            "step_01_parameter_tuning",
            lambda: self._step_parameter_tuning(context),
        )
        steps_dict["step_01_parameter_tuning"] = result

        # Step 2: 演化速度計算
        result = self._safe_step(
            "step_02_evolution_velocity",
            lambda: self._step_evolution_velocity(context),
        )
        steps_dict["step_02_evolution_velocity"] = result

        # Step 3: 知識晶格深層再結晶
        result = self._safe_step(
            "step_03_knowledge_lattice_deep",
            lambda: self._step_knowledge_lattice_deep(context),
        )
        steps_dict["step_03_knowledge_lattice_deep"] = result

        # Step 4: 預判校準
        result = self._safe_step(
            "step_04_metacognition_calibration",
            lambda: self._step_metacognition_calibration(context),
        )
        steps_dict["step_04_metacognition_calibration"] = result

        # Step 5: 週報生成
        result = self._safe_step(
            "step_05_weekly_report",
            lambda: self._step_weekly_report(context),
        )
        steps_dict["step_05_weekly_report"] = result

        elapsed = round(time.time() - start, 2)
        completed_at = datetime.now(TZ_TAIPEI)

        ok_count = sum(1 for s in steps_dict.values() if s["status"] == "ok")
        error_count = sum(
            1 for s in steps_dict.values() if s["status"] == "error"
        )
        skipped_count = sum(
            1 for s in steps_dict.values() if s["status"] == "skipped"
        )

        report = {
            "cycle": "weekly",
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "elapsed_seconds": elapsed,
            "steps": steps_dict,
            "summary": {
                "total": len(steps_dict),
                "ok": ok_count,
                "error": error_count,
                "skipped": skipped_count,
            },
        }

        # 持久化執行報告
        self._persist_report(report)

        self._publish("WEEKLY_CYCLE_COMPLETED", {
            "elapsed_seconds": elapsed,
            "summary": report["summary"],
        })

        return report

    # ─── 步驟實作 ───

    def _step_parameter_tuning(self, ctx: Dict) -> Dict:
        """Step 1: 參數調諧 — 呼叫 ParameterTuner.tune_weekly()."""
        try:
            from museon.evolution.parameter_tuner import ParameterTuner
        except ImportError:
            ctx["tuning"] = None
            return {"skipped": "ParameterTuner 模組不可用"}

        tuner = ParameterTuner(workspace=self._workspace)
        report = tuner.tune_weekly()
        result = report.to_dict() if hasattr(report, "to_dict") else str(report)
        ctx["tuning"] = result
        return {
            "total_adjustments": result.get("total_adjustments", 0)
            if isinstance(result, dict) else 0,
            "drift_paused": result.get("drift_paused", False)
            if isinstance(result, dict) else False,
        }

    def _step_evolution_velocity(self, ctx: Dict) -> Dict:
        """Step 2: 演化速度計算 — 呼叫 EvolutionVelocity.calculate_weekly()."""
        try:
            from museon.evolution.evolution_velocity import EvolutionVelocity
        except ImportError:
            ctx["velocity"] = None
            return {"skipped": "EvolutionVelocity 模組不可用"}

        engine = EvolutionVelocity(workspace=self._workspace)
        snapshot = engine.calculate_weekly()
        snapshot_dict = (
            snapshot.to_dict() if hasattr(snapshot, "to_dict") else {}
        )
        ctx["velocity"] = snapshot_dict

        # 同時取得趨勢
        trend = engine.get_trend()
        ctx["velocity_trend"] = trend

        # 高原警報 → 覺察訊號（不再只印 log）
        if snapshot and getattr(snapshot, 'plateau_alert', False):
            try:
                from museon.nightly.triage_step import write_signal
                from museon.core.awareness import (
                    AwarenessSignal, Severity, SignalType, Actionability,
                )
                write_signal(self._workspace, AwarenessSignal(
                    source="evolution_velocity",
                    severity=Severity.HIGH,
                    signal_type=SignalType.LEARNING_GAP,
                    title="演化高原期：連續數週無進步，建議觸發外部知識搜尋",
                    actionability=Actionability.AUTO,
                    suggested_action="trigger_outward_search",
                ))
            except Exception:
                pass

        return {
            "iso_week": snapshot_dict.get("iso_week", ""),
            "composite_velocity": round(
                snapshot_dict.get("composite_velocity", 0.0), 4
            ),
            "trend": trend,
            "plateau_alert": bool(getattr(snapshot, 'plateau_alert', False)),
        }

    def _step_knowledge_lattice_deep(self, ctx: Dict) -> Dict:
        """Step 3: 知識晶格深層再結晶 — 跨週合併掃描.

        與每日 nightly_maintenance 不同，此步驟執行更深度的跨週掃描，
        尋找跨越不同天的相似結晶進行合併。
        """
        try:
            from museon.agent.knowledge_lattice import KnowledgeLattice
        except ImportError:
            ctx["lattice"] = None
            return {"skipped": "KnowledgeLattice 模組不可用"}

        lattice = KnowledgeLattice(data_dir=str(self._workspace))

        # 先執行標準夜間維護（如果尚未執行）
        maintenance_report = lattice.nightly_maintenance()

        # 取得結晶統計
        total_crystals = maintenance_report.get("total_crystals", 0)
        merged = maintenance_report.get("merged", 0)
        new_crystals = maintenance_report.get("new_crystals", 0)
        ri_updated = maintenance_report.get("ri_updated", 0)

        ctx["lattice"] = {
            "total_crystals": total_crystals,
            "merged": merged,
            "new_crystals": new_crystals,
            "ri_updated": ri_updated,
        }

        return {
            "total_crystals": total_crystals,
            "weekly_merged": merged,
            "weekly_new": new_crystals,
        }

    def _step_metacognition_calibration(self, ctx: Dict) -> Dict:
        """Step 4: 預判校準 — 分析 accuracy_stats.json 的週趨勢.

        讀取最近 7 天的準確率數據，計算趨勢並寫入 weekly_calibration.json。
        """
        meta_dir = self._workspace / "_system" / "metacognition"
        stats_file = meta_dir / "accuracy_stats.json"

        data = _read_json(stats_file)
        if not data:
            ctx["calibration"] = None
            return {"skipped": "accuracy_stats.json 不存在或無法讀取"}

        # 從 accuracy_stats.json 提取每日準確率
        # 預期格式: {"daily_records": [{"date": "...", "accuracy": 0.xx, ...}]}
        daily_records = data.get("daily_records", [])

        # 也嘗試從頂層讀取（另一種常見格式）
        if not daily_records and "accuracy" in data:
            # 單一快照格式
            daily_records = [data]

        now = datetime.now(TZ_TAIPEI)
        week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        this_week_acc: List[float] = []
        last_week_acc: List[float] = []

        for record in daily_records:
            date_str = record.get("date", record.get("timestamp", ""))
            acc = record.get("accuracy", record.get("overall_accuracy", 0.0))
            if not date_str or not isinstance(acc, (int, float)):
                continue
            try:
                # 嘗試解析日期
                if "T" in date_str:
                    dt = datetime.fromisoformat(date_str)
                else:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=TZ_TAIPEI)

                if dt >= week_ago:
                    this_week_acc.append(float(acc))
                elif dt >= two_weeks_ago:
                    last_week_acc.append(float(acc))
            except (ValueError, TypeError):
                continue

        # 計算週均準確率
        this_week_avg = (
            statistics.mean(this_week_acc) if this_week_acc else 0.0
        )
        last_week_avg = (
            statistics.mean(last_week_acc) if last_week_acc else 0.0
        )

        trend = _trend_arrow(this_week_avg, last_week_avg)
        delta = this_week_avg - last_week_avg

        calibration = {
            "iso_week": _iso_week_str(now),
            "timestamp": now.isoformat(),
            "this_week_accuracy": round(this_week_avg, 4),
            "last_week_accuracy": round(last_week_avg, 4),
            "delta": round(delta, 4),
            "trend": trend,
            "sample_count_this_week": len(this_week_acc),
            "sample_count_last_week": len(last_week_acc),
        }

        # 寫入 weekly_calibration.json
        cal_file = meta_dir / "weekly_calibration.json"
        _write_json(cal_file, calibration)

        ctx["calibration"] = calibration

        return {
            "this_week_accuracy": round(this_week_avg, 4),
            "last_week_accuracy": round(last_week_avg, 4),
            "trend": trend,
        }

    def _step_weekly_report(self, ctx: Dict) -> Dict:
        """Step 5: 週報生成 — 彙總所有步驟結果為 Markdown."""
        now = datetime.now(TZ_TAIPEI)
        iso_week = _iso_week_str(now)

        # ── 組裝 Markdown ──
        lines: List[str] = []
        lines.append(f"# 霓裳週報 — {iso_week}")
        lines.append("")
        lines.append(
            f"> 產生時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)"
        )
        lines.append("")

        # 演化速度
        lines.append("## 演化速度")
        lines.append("")
        vel = ctx.get("velocity")
        if vel and isinstance(vel, dict):
            composite = vel.get("composite_velocity", 0.0)
            trend = ctx.get("velocity_trend", "N/A")

            # 嘗試取得上週數值（從歷史中）
            prev_composite = self._get_previous_velocity()
            arrow = _trend_arrow(composite, prev_composite)

            trend_label_map = {
                "accelerating": "加速中",
                "decelerating": "減速中",
                "plateau": "高原期",
                "insufficient_data": "資料不足",
            }
            trend_label = trend_label_map.get(trend, trend)

            lines.append(
                f"- 綜合速度指數: {composite:.2f} "
                f"({arrow} vs 上週 {prev_composite:.2f})"
            )
            lines.append(f"- 趨勢: {trend_label}")

            # 細項指標
            if vel.get("capability_expansion_rate"):
                lines.append(
                    f"- 能力擴展率: {vel['capability_expansion_rate']:.4f}"
                )
            if vel.get("prediction_improvement"):
                lines.append(
                    f"- 預判進步率: {vel['prediction_improvement']:+.4f}"
                )
            if vel.get("skill_hit_rate_delta"):
                lines.append(
                    f"- 技能命中率變化: {vel['skill_hit_rate_delta']:+.4f}"
                )
            if vel.get("iteration_efficiency"):
                lines.append(
                    f"- 迭代效率: {vel['iteration_efficiency']:.4f}"
                )

            # 警報
            if vel.get("plateau_alert"):
                lines.append("- ⚠ 高原期警報：建議觸發突變策略")
            if vel.get("regression_alert"):
                lines.append("- ⚠ 退化警報：建議進行根因分析")
        else:
            lines.append("- （演化速度模組不可用）")
        lines.append("")

        # 參數調整
        lines.append("## 參數調整")
        lines.append("")
        tuning = ctx.get("tuning")
        if tuning and isinstance(tuning, dict):
            adjustments = tuning.get("adjustments", [])
            if adjustments:
                for adj in adjustments:
                    group = adj.get("parameter_group", "")
                    name = adj.get("parameter_name", "")
                    old = adj.get("old_value", "")
                    new = adj.get("new_value", "")
                    lines.append(f"- {group}/{name}: {old} → {new}")
            else:
                lines.append("- 本週無參數調整")
            if tuning.get("drift_paused"):
                lines.append("- ⚠ 漂移暫停：累積漂移超過閾值")
            if tuning.get("drift_alerts"):
                for alert in tuning["drift_alerts"]:
                    lines.append(f"- ⚠ 漂移警報: {alert}")
        else:
            lines.append("- （參數調諧模組不可用）")
        lines.append("")

        # 知識晶格
        lines.append("## 知識晶格")
        lines.append("")
        lattice = ctx.get("lattice")
        if lattice and isinstance(lattice, dict):
            lines.append(
                f"- 活躍結晶: {lattice.get('total_crystals', 0)}"
            )
            lines.append(f"- 本週合併: {lattice.get('merged', 0)} 對")
            lines.append(f"- 本週新增: {lattice.get('new_crystals', 0)}")
        else:
            lines.append("- （知識晶格模組不可用）")
        lines.append("")

        # 預判校準
        lines.append("## 預判校準")
        lines.append("")
        cal = ctx.get("calibration")
        if cal and isinstance(cal, dict):
            this_acc = cal.get("this_week_accuracy", 0.0)
            last_acc = cal.get("last_week_accuracy", 0.0)
            trend = cal.get("trend", "→")
            lines.append(
                f"- 本週準確率: {this_acc:.0%} "
                f"({trend} vs 上週 {last_acc:.0%})"
            )
            lines.append(
                f"- 本週樣本數: {cal.get('sample_count_this_week', 0)}"
            )
        else:
            lines.append("- （預判校準資料不可用）")
        lines.append("")

        # 組合並寫檔
        md_content = "\n".join(lines)

        report_dir = self._workspace / "_system" / "evolution"
        report_path = report_dir / f"weekly_report_{iso_week}.md"
        _write_markdown(report_path, md_content)

        logger.info(f"週報已生成: {report_path}")

        return {"report_path": str(report_path), "iso_week": iso_week}

    # ─── 輔助方法 ───

    def _get_previous_velocity(self) -> float:
        """從 velocity_log.jsonl 取得上週的 composite_velocity."""
        log_file = self._workspace / "_system" / "evolution" / "velocity_log.jsonl"
        records = _read_jsonl(log_file)
        if len(records) >= 2:
            # 倒數第二筆 = 上週
            return records[-2].get("composite_velocity", 0.0)
        return 0.0

    def _safe_step(self, name: str, func: Callable) -> Dict:
        """單步執行 + 錯誤隔離."""
        try:
            result = func()
            result_str = str(result)
            if len(result_str) > REPORT_TRUNCATE_CHARS:
                result_str = result_str[:REPORT_TRUNCATE_CHARS] + "..."
            return {"status": "ok", "result": result_str}
        except NotImplementedError:
            return {"status": "skipped", "result": "subsystem not available"}
        except Exception as e:
            logger.error(f"[WEEKLY] Step {name} failed: {e}")
            return {"status": "error", "error": str(e)}

    def _publish(self, event_type: str, data: Dict) -> None:
        """發布事件到 EventBus."""
        if self._event_bus:
            try:
                self._event_bus.publish(event_type, data)
            except Exception as e:
                logger.warning(f"EventBus publish {event_type} failed: {e}")

    def _persist_report(self, report: Dict) -> None:
        """儲存週期循環報告."""
        state_dir = self._workspace / "_system" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / "weekly_cycle_report.json"
        _write_json(path, report)


# ═══════════════════════════════════════════
# MonthlyCycle
# ═══════════════════════════════════════════


class MonthlyCycle:
    """每月演化循環 — 每月 1 日 04:00 執行.

    四個步驟：
      1. ANIMA 趨勢分析（30 天八元素趨勢 + 失衡偵測）
      2. 架構層 Morphenix L3 提案（持續失敗模式偵測）
      3. 技能生態健康（44+ 技能使用掃描）
      4. 月報生成
    """

    def __init__(
        self,
        workspace: Path,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._workspace = Path(workspace)
        self._event_bus = event_bus

    def run(self) -> Dict:
        """執行月度循環.

        Returns:
            執行報告（steps 為 dict 格式）
        """
        started_at = datetime.now(TZ_TAIPEI)
        start = time.time()

        self._publish("MONTHLY_CYCLE_STARTED", {
            "started_at": started_at.isoformat(),
        })

        context: Dict[str, Any] = {}
        steps_dict: Dict[str, Dict] = {}

        # Step 1: ANIMA 趨勢分析
        result = self._safe_step(
            "step_01_anima_trend",
            lambda: self._step_anima_trend(context),
        )
        steps_dict["step_01_anima_trend"] = result

        # Step 2: 架構層 Morphenix L3 提案
        result = self._safe_step(
            "step_02_morphenix_l3",
            lambda: self._step_morphenix_l3(context),
        )
        steps_dict["step_02_morphenix_l3"] = result

        # Step 3: 技能生態健康
        result = self._safe_step(
            "step_03_skill_ecosystem_health",
            lambda: self._step_skill_ecosystem_health(context),
        )
        steps_dict["step_03_skill_ecosystem_health"] = result

        # Step 4: 月報生成
        result = self._safe_step(
            "step_04_monthly_report",
            lambda: self._step_monthly_report(context),
        )
        steps_dict["step_04_monthly_report"] = result

        elapsed = round(time.time() - start, 2)
        completed_at = datetime.now(TZ_TAIPEI)

        ok_count = sum(1 for s in steps_dict.values() if s["status"] == "ok")
        error_count = sum(
            1 for s in steps_dict.values() if s["status"] == "error"
        )
        skipped_count = sum(
            1 for s in steps_dict.values() if s["status"] == "skipped"
        )

        report = {
            "cycle": "monthly",
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "elapsed_seconds": elapsed,
            "steps": steps_dict,
            "summary": {
                "total": len(steps_dict),
                "ok": ok_count,
                "error": error_count,
                "skipped": skipped_count,
            },
        }

        self._persist_report(report)

        self._publish("MONTHLY_CYCLE_COMPLETED", {
            "elapsed_seconds": elapsed,
            "summary": report["summary"],
        })

        return report

    # ─── 步驟實作 ───

    def _step_anima_trend(self, ctx: Dict) -> Dict:
        """Step 1: ANIMA 趨勢分析 — 30 天八元素變化 + 失衡偵測.

        讀取 ANIMA_MC.json 中的 eight_primal_energies，
        結合歷史日誌計算 30 天趨勢。
        """
        # 讀取當前 ANIMA 狀態
        anima_path = self._workspace / "data" / "ANIMA_MC.json"
        if not anima_path.exists():
            # 嘗試不帶 data/ 的路徑
            anima_path = self._workspace / "ANIMA_MC.json"

        anima_data = _read_json(anima_path)
        if not anima_data:
            ctx["anima_trend"] = None
            return {"skipped": "ANIMA_MC.json 不存在或無法讀取"}

        # 解析八元素當前值
        energies = anima_data.get("eight_primal_energies", {})
        element_name_map = {
            "qian": "乾", "kun": "坤", "zhen": "震", "xun": "巽",
            "kan": "坎", "li": "離", "gen": "艮", "dui": "兌",
        }

        current_values: Dict[str, float] = {}
        for key in ANIMA_ELEMENTS:
            cname = element_name_map.get(key, key)
            val = energies.get(cname, {})
            if isinstance(val, dict):
                current_values[key] = float(
                    val.get("absolute", val.get("value", 0))
                )
            elif isinstance(val, (int, float)):
                current_values[key] = float(val)
            else:
                current_values[key] = 0.0

        # 讀取歷史日誌（如果存在）
        history_file = (
            self._workspace / "_system" / "anima" / "anima_history.jsonl"
        )
        history_records = _read_jsonl(history_file)

        now = datetime.now(TZ_TAIPEI)
        month_ago = now - timedelta(days=30)

        # 計算 30 天前的數值（從歷史中找最接近 30 天前的記錄）
        baseline_values: Dict[str, float] = {k: 0.0 for k in ANIMA_ELEMENTS}
        for record in history_records:
            ts_str = record.get("timestamp", "")
            try:
                if "T" in ts_str:
                    dt = datetime.fromisoformat(ts_str)
                else:
                    dt = datetime.strptime(ts_str, "%Y-%m-%d")
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=TZ_TAIPEI)
                if dt <= month_ago:
                    elements = record.get("elements", {})
                    for k in ANIMA_ELEMENTS:
                        if k in elements:
                            baseline_values[k] = float(elements[k])
            except (ValueError, TypeError):
                continue

        # 計算趨勢
        trends: Dict[str, Dict] = {}
        for key in ANIMA_ELEMENTS:
            current = current_values.get(key, 0.0)
            baseline = baseline_values.get(key, 0.0)
            delta = current - baseline
            trends[key] = {
                "current": current,
                "baseline_30d": baseline,
                "delta": delta,
                "label": ANIMA_ELEMENT_NAMES.get(key, key),
            }

        # 失衡偵測
        active_values = [v for v in current_values.values() if v > 0]
        imbalances: List[str] = []
        if active_values:
            max_val = max(active_values)
            min_val = min(active_values) if min(active_values) > 0 else 1.0
            ratio = max_val / min_val
            if ratio > ANIMA_IMBALANCE_RATIO:
                # 找出最高和最低的元素
                max_key = max(current_values, key=current_values.get)
                min_key = min(
                    (k for k, v in current_values.items() if v > 0),
                    key=lambda k: current_values[k],
                    default=min(current_values, key=current_values.get),
                )
                imbalances.append(
                    f"失衡比例 {ratio:.1f}x: "
                    f"{ANIMA_ELEMENT_NAMES[max_key]} ({max_val:.0f}) vs "
                    f"{ANIMA_ELEMENT_NAMES[min_key]} ({min_val:.0f})"
                )

        ctx["anima_trend"] = {
            "trends": trends,
            "imbalances": imbalances,
            "current_values": current_values,
        }

        return {
            "elements_analyzed": len(trends),
            "imbalances_found": len(imbalances),
        }

    def _step_morphenix_l3(self, ctx: Dict) -> Dict:
        """Step 2: 架構層 Morphenix L3 提案.

        掃描最近 30 天的 Nightly 報告和錯誤日誌，
        偵測持續性失敗模式，若發現一致的系統級問題則生成 L3 提案。
        """
        proposals_dir = (
            self._workspace / "_system" / "morphenix" / "proposals"
        )
        proposals_dir.mkdir(parents=True, exist_ok=True)

        state_dir = self._workspace / "_system" / "state"
        now = datetime.now(TZ_TAIPEI)
        month_ago = now - timedelta(days=30)

        # 收集最近 30 天的 nightly 報告錯誤
        failure_counter: Counter = Counter()
        error_details: Dict[str, List[str]] = defaultdict(list)

        # 掃描 nightly 報告歷史
        nightly_log = state_dir / "nightly_history.jsonl"
        nightly_records = _read_jsonl(nightly_log)

        for record in nightly_records:
            ts_str = record.get("completed_at", "")
            try:
                if ts_str:
                    dt = datetime.fromisoformat(ts_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=TZ_TAIPEI)
                    if dt < month_ago:
                        continue
            except (ValueError, TypeError):
                continue

            errors = record.get("errors", [])
            for err in errors:
                step = err.get("step", "unknown")
                error_msg = err.get("error", "")
                failure_counter[step] += 1
                if len(error_details[step]) < 5:  # 保留最多 5 個範例
                    error_details[step].append(error_msg[:200])

        # 偵測持續失敗模式（同一步驟連續 N 天以上失敗）
        l3_proposals_created = 0
        consistent_failures: List[Dict] = []

        for step_name, count in failure_counter.items():
            if count >= L3_CONSISTENT_FAILURE_DAYS:
                consistent_failures.append({
                    "step": step_name,
                    "failure_count": count,
                    "sample_errors": error_details.get(step_name, []),
                })

                # 生成 L3 提案
                proposal_id = (
                    f"L3_monthly_{now.strftime('%Y%m')}_"
                    f"{step_name.replace(' ', '_')}"
                )
                proposal = {
                    "id": proposal_id,
                    "category": "L3",
                    "source": "monthly_cycle_failure_pattern",
                    "title": (
                        f"架構級修復：{step_name} 持續失敗 "
                        f"({count} 次/月)"
                    ),
                    "description": (
                        f"過去 30 天內，步驟 {step_name} 連續失敗 {count} 次，"
                        f"顯示存在系統架構層級的問題，建議進行根因分析與架構修復。"
                    ),
                    "evidence": error_details.get(step_name, []),
                    "status": "awaiting_human_approval",
                    "created_at": now.isoformat(),
                }

                proposal_path = proposals_dir / f"{proposal_id}.json"
                _write_json(proposal_path, proposal)
                l3_proposals_created += 1
                logger.info(
                    f"L3 提案已生成: {proposal_id} "
                    f"(step={step_name}, failures={count})"
                )

        ctx["morphenix_l3"] = {
            "proposals_created": l3_proposals_created,
            "consistent_failures": consistent_failures,
            "total_failure_steps": len(failure_counter),
        }

        return {
            "l3_proposals_created": l3_proposals_created,
            "consistent_failure_patterns": len(consistent_failures),
        }

    def _step_skill_ecosystem_health(self, ctx: Dict) -> Dict:
        """Step 3: 技能生態健康 — 掃描 44+ 技能的月使用量.

        從 skill_usage_log.jsonl 統計每個技能在過去 30 天的使用次數，
        找出未使用和過度使用的技能。
        """
        now = datetime.now(TZ_TAIPEI)
        month_ago = now - timedelta(days=30)

        # 讀取技能使用日誌
        usage_file = self._workspace / "skill_usage_log.jsonl"
        usage_records = _read_jsonl(usage_file)

        # 讀取可用技能清單
        all_skills: set = set()
        try:
            from museon.agent.skills import SkillLoader
            loader = SkillLoader(
                skills_dir=str(self._workspace / "data" / "skills")
            )
            all_skills = set(loader.list_skills())
        except ImportError:
            logger.debug("SkillLoader 模組不可用，僅統計已使用技能")
        except Exception as e:
            logger.debug(f"載入技能清單失敗: {e}")

        # 統計月使用量
        skill_usage: Counter = Counter()
        for record in usage_records:
            ts_str = record.get("timestamp", record.get("ts", ""))
            try:
                if ts_str:
                    if "T" in ts_str:
                        dt = datetime.fromisoformat(ts_str)
                    else:
                        dt = datetime.strptime(ts_str, "%Y-%m-%d")
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=TZ_TAIPEI)
                    if dt < month_ago:
                        continue
            except (ValueError, TypeError):
                continue

            skill_name = record.get(
                "skill_name", record.get("task_type", "unknown")
            )
            skill_usage[skill_name] += 1

        # 合併從日誌中發現的技能名稱
        used_skills = set(skill_usage.keys())
        all_known = all_skills | used_skills

        # 分類
        unused_skills = sorted(all_skills - used_skills) if all_skills else []
        overused_skills = sorted(
            [
                (name, count)
                for name, count in skill_usage.items()
                if count >= SKILL_OVERUSE_THRESHOLD
            ],
            key=lambda x: x[1],
            reverse=True,
        )

        # 計算總使用次數和平均
        total_usage = sum(skill_usage.values())
        avg_usage = (
            total_usage / len(skill_usage) if skill_usage else 0.0
        )

        ecosystem = {
            "total_known_skills": len(all_known),
            "total_used_skills": len(used_skills),
            "unused_skills": unused_skills,
            "overused_skills": [
                {"name": name, "count": count}
                for name, count in overused_skills
            ],
            "total_invocations": total_usage,
            "avg_usage_per_skill": round(avg_usage, 1),
            "top_skills": [
                {"name": name, "count": count}
                for name, count in skill_usage.most_common(10)
            ],
        }

        ctx["skill_ecosystem"] = ecosystem

        return {
            "total_skills": len(all_known),
            "used": len(used_skills),
            "unused": len(unused_skills),
            "overused": len(overused_skills),
        }

    def _step_monthly_report(self, ctx: Dict) -> Dict:
        """Step 4: 月報生成 — 綜合 Markdown 報告."""
        now = datetime.now(TZ_TAIPEI)
        year_month = now.strftime("%Y-%m")

        lines: List[str] = []
        lines.append(f"# 霓裳月報 — {year_month}")
        lines.append("")
        lines.append(
            f"> 產生時間：{now.strftime('%Y-%m-%d %H:%M:%S')} (UTC+8)"
        )
        lines.append("")

        # ── ANIMA 趨勢分析 ──
        lines.append("## ANIMA 八元素趨勢")
        lines.append("")
        anima = ctx.get("anima_trend")
        if anima and isinstance(anima, dict):
            trends = anima.get("trends", {})
            lines.append("| 元素 | 當前值 | 30天前 | 變化 |")
            lines.append("|------|--------|--------|------|")
            for key in ANIMA_ELEMENTS:
                t = trends.get(key, {})
                label = t.get("label", key)
                current = t.get("current", 0.0)
                baseline = t.get("baseline_30d", 0.0)
                delta = t.get("delta", 0.0)
                arrow = _trend_arrow(current, baseline)
                lines.append(
                    f"| {label} | {current:.0f} | {baseline:.0f} | "
                    f"{arrow} {delta:+.0f} |"
                )
            lines.append("")

            imbalances = anima.get("imbalances", [])
            if imbalances:
                lines.append("### 失衡警報")
                lines.append("")
                for imb in imbalances:
                    lines.append(f"- ⚠ {imb}")
                lines.append("")
        else:
            lines.append("- （ANIMA 資料不可用）")
            lines.append("")

        # ── Morphenix L3 提案 ──
        lines.append("## 架構層演化提案 (L3)")
        lines.append("")
        morphenix = ctx.get("morphenix_l3")
        if morphenix and isinstance(morphenix, dict):
            proposals = morphenix.get("proposals_created", 0)
            failures = morphenix.get("consistent_failures", [])
            if proposals > 0:
                lines.append(f"- 本月新增 L3 提案: {proposals} 個")
                lines.append("")
                for f in failures:
                    step = f.get("step", "")
                    count = f.get("failure_count", 0)
                    lines.append(f"  - `{step}`: 失敗 {count} 次/月")
                    samples = f.get("sample_errors", [])
                    if samples:
                        lines.append(
                            f"    - 範例: {samples[0][:100]}"
                        )
            else:
                lines.append("- 本月無持續性失敗模式，系統架構穩定")
        else:
            lines.append("- （Morphenix L3 分析不可用）")
        lines.append("")

        # ── 技能生態健康 ──
        lines.append("## 技能生態健康")
        lines.append("")
        eco = ctx.get("skill_ecosystem")
        if eco and isinstance(eco, dict):
            lines.append(
                f"- 已知技能總數: {eco.get('total_known_skills', 0)}"
            )
            lines.append(
                f"- 本月有使用的技能: {eco.get('total_used_skills', 0)}"
            )
            lines.append(
                f"- 月總調用次數: {eco.get('total_invocations', 0)}"
            )
            lines.append(
                f"- 平均每技能調用: {eco.get('avg_usage_per_skill', 0):.1f} 次"
            )
            lines.append("")

            # Top 10 技能
            top = eco.get("top_skills", [])
            if top:
                lines.append("### 使用排行 (Top 10)")
                lines.append("")
                lines.append("| 排名 | 技能 | 調用次數 |")
                lines.append("|------|------|----------|")
                for i, s in enumerate(top, 1):
                    lines.append(
                        f"| {i} | {s['name']} | {s['count']} |"
                    )
                lines.append("")

            # 過度使用
            overused = eco.get("overused_skills", [])
            if overused:
                lines.append("### 過度使用的技能")
                lines.append("")
                for s in overused:
                    lines.append(
                        f"- ⚠ {s['name']}: {s['count']} 次"
                        f"（閾值 {SKILL_OVERUSE_THRESHOLD}）"
                    )
                lines.append("")

            # 未使用
            unused = eco.get("unused_skills", [])
            if unused:
                lines.append("### 未使用的技能")
                lines.append("")
                for name in unused:
                    lines.append(f"- {name}")
                lines.append("")
        else:
            lines.append("- （技能生態資料不可用）")
            lines.append("")

        # ── 總結 ──
        lines.append("## 月度總結")
        lines.append("")
        lines.append(
            f"- 報告週期: {year_month}-01 ~ "
            f"{now.strftime('%Y-%m-%d')}"
        )

        # 演化速度月均（從週報歷史計算）
        velocity_log = (
            self._workspace / "_system" / "evolution" / "velocity_log.jsonl"
        )
        monthly_velocities = self._get_monthly_velocities(velocity_log, now)
        if monthly_velocities:
            avg_vel = statistics.mean(monthly_velocities)
            lines.append(f"- 月均演化速度: {avg_vel:.2f}")
        lines.append("")

        # 組合並寫檔
        md_content = "\n".join(lines)

        report_dir = self._workspace / "_system" / "evolution"
        report_path = report_dir / f"monthly_report_{year_month}.md"
        _write_markdown(report_path, md_content)

        logger.info(f"月報已生成: {report_path}")

        return {"report_path": str(report_path), "year_month": year_month}

    # ─── 輔助方法 ───

    def _get_monthly_velocities(
        self, log_file: Path, now: datetime
    ) -> List[float]:
        """從 velocity_log.jsonl 取得本月的所有 composite_velocity."""
        records = _read_jsonl(log_file)
        month_start = now.replace(day=1, hour=0, minute=0, second=0)

        velocities: List[float] = []
        for record in records:
            ts_str = record.get("timestamp", "")
            try:
                if ts_str:
                    dt = datetime.fromisoformat(ts_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=TZ_TAIPEI)
                    if dt >= month_start:
                        vel = record.get("composite_velocity", 0.0)
                        velocities.append(float(vel))
            except (ValueError, TypeError):
                continue
        return velocities

    def _safe_step(self, name: str, func: Callable) -> Dict:
        """單步執行 + 錯誤隔離."""
        try:
            result = func()
            result_str = str(result)
            if len(result_str) > REPORT_TRUNCATE_CHARS:
                result_str = result_str[:REPORT_TRUNCATE_CHARS] + "..."
            return {"status": "ok", "result": result_str}
        except NotImplementedError:
            return {"status": "skipped", "result": "subsystem not available"}
        except Exception as e:
            logger.error(f"[MONTHLY] Step {name} failed: {e}")
            return {"status": "error", "error": str(e)}

    def _publish(self, event_type: str, data: Dict) -> None:
        """發布事件到 EventBus."""
        if self._event_bus:
            try:
                self._event_bus.publish(event_type, data)
            except Exception as e:
                logger.warning(f"EventBus publish {event_type} failed: {e}")

    def _persist_report(self, report: Dict) -> None:
        """儲存月度循環報告."""
        state_dir = self._workspace / "_system" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / "monthly_cycle_report.json"
        _write_json(path, report)
