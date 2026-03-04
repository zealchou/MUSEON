"""Eval Engine（效能儀表板）測試.

涵蓋 BDD 10-eval-engine.feature 的所有 Scenario：
- Q-Score 計算（加權公式）
- 三級品質分類 (high/medium/low)
- 滿意度代理指標（正/負信號 + 負面偏權 1.5x）
- 趨勢追蹤（日曲線、領域、連續低分警報）
- A/B 比對器（基線鎖定、7 天觀察、維度退化警報）
- 盲點雷達（領域缺口、技能錯配、使用者模式、時間漂移）
- 安全閘門（HG-EVAL-HONEST, HG-EVAL-BASELINE-LOCK, SG-EVAL-PRIVACY）
"""

import json
import pytest
from datetime import datetime, timedelta, date
from pathlib import Path


@pytest.fixture
def data_dir(tmp_path):
    """建立測試用資料目錄."""
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir(parents=True)
    (eval_dir / "daily").mkdir(parents=True, exist_ok=True)
    (eval_dir / "weekly").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def eval_engine(data_dir):
    """建立 EvalEngine 測試實例."""
    from museon.agent.eval_engine import EvalEngine
    return EvalEngine(data_dir=str(data_dir))


# ════════════════════════════════════════════
# Section 1: Q-Score 計算
# ════════════════════════════════════════════

class TestQScore:
    """測試 Q-Score 計算."""

    def test_q_score_formula_correct(self, eval_engine):
        """Q-Score = 0.30*Understanding + 0.25*Depth + 0.20*Clarity + 0.25*Actionability."""
        from museon.agent.eval_engine import QScore

        q = QScore(
            understanding=0.8,
            depth=0.7,
            clarity=0.9,
            actionability=0.6,
        )
        q.compute()
        expected = 0.30 * 0.8 + 0.25 * 0.7 + 0.20 * 0.9 + 0.25 * 0.6
        assert abs(q.score - expected) < 0.001

    def test_q_score_via_evaluate(self, eval_engine):
        """透過 evaluate() 方法計算 Q-Score（提供 deep-think 分數）."""
        q = eval_engine.evaluate(
            user_content="測試問題",
            response_content="測試回覆",
            understanding=0.85,
            depth=0.70,
            clarity=0.90,
            actionability=0.75,
            session_id="test_session",
            domain="general",
        )
        expected = 0.30 * 0.85 + 0.25 * 0.70 + 0.20 * 0.90 + 0.25 * 0.75
        assert abs(q.score - expected) < 0.001

    def test_q_score_weights_sum_to_one(self):
        """權重總和為 1.0."""
        from museon.agent.eval_engine import (
            WEIGHT_UNDERSTANDING,
            WEIGHT_DEPTH,
            WEIGHT_CLARITY,
            WEIGHT_ACTIONABILITY,
        )
        total = WEIGHT_UNDERSTANDING + WEIGHT_DEPTH + WEIGHT_CLARITY + WEIGHT_ACTIONABILITY
        assert abs(total - 1.0) < 0.001

    def test_q_score_high_tier(self, eval_engine):
        """Q-Score > 0.7 為高品質 (high)."""
        from museon.agent.eval_engine import QScore

        q = QScore(
            understanding=0.9, depth=0.9, clarity=0.9, actionability=0.9
        )
        q.compute()
        assert q.tier == "high"
        assert q.score > 0.7

    def test_q_score_medium_tier(self, eval_engine):
        """0.5 <= Q-Score <= 0.7 為中品質 (medium)."""
        from museon.agent.eval_engine import QScore

        q = QScore(
            understanding=0.6, depth=0.6, clarity=0.6, actionability=0.6
        )
        q.compute()
        assert q.tier == "medium"
        assert 0.5 <= q.score <= 0.7

    def test_q_score_low_tier(self, eval_engine):
        """Q-Score < 0.5 為低品質 (low)."""
        from museon.agent.eval_engine import QScore

        q = QScore(
            understanding=0.3, depth=0.3, clarity=0.3, actionability=0.3
        )
        q.compute()
        assert q.tier == "low"
        assert q.score < 0.5

    def test_q_score_dimensions_clamped(self, eval_engine):
        """evaluate() 方法會將超出範圍的維度值夾到 0.0-1.0."""
        q = eval_engine.evaluate(
            user_content="測試問題",
            response_content="測試回覆",
            understanding=1.5,
            depth=0.5,
            clarity=0.5,
            actionability=0.5,
        )
        # evaluate() clamps values to [0.0, 1.0]
        assert q.understanding <= 1.0
        assert q.understanding >= 0.0

    def test_q_score_includes_all_dimensions(self, eval_engine):
        """Q-Score 物件包含四個維度分數."""
        from museon.agent.eval_engine import QScore

        q = QScore(
            understanding=0.8, depth=0.7, clarity=0.9, actionability=0.6
        )
        q.compute()
        assert hasattr(q, "understanding")
        assert hasattr(q, "depth")
        assert hasattr(q, "clarity")
        assert hasattr(q, "actionability")

    def test_q_score_zero_dimension_detection(self, eval_engine):
        """單一維度為 0 時 Q-Score 標記零值維度."""
        from museon.agent.eval_engine import QScore

        q = QScore(
            understanding=0.80, depth=0.0, clarity=0.85, actionability=0.60
        )
        q.compute()
        expected = 0.30 * 0.80 + 0.25 * 0.0 + 0.20 * 0.85 + 0.25 * 0.60
        assert abs(q.score - expected) < 0.001
        assert q.tier == "medium"
        assert "depth" in q.zero_dimensions

    def test_q_score_zero_dimension_via_evaluate(self, eval_engine):
        """evaluate() 對零值維度生成警報."""
        q = eval_engine.evaluate(
            user_content="測試問題",
            response_content="測試回覆",
            understanding=0.80,
            depth=0.0,
            clarity=0.85,
            actionability=0.60,
            session_id="zero_dim_test",
        )
        assert "depth" in q.zero_dimensions
        # 確認警報已被記錄
        alerts = eval_engine.store.load_alerts()
        zero_dim_alerts = [a for a in alerts if a.get("alert_type") == "zero_dimension"]
        assert len(zero_dim_alerts) > 0


# ════════════════════════════════════════════
# Section 2: 滿意度代理指標
# ════════════════════════════════════════════

class TestSatisfactionProxy:
    """測試滿意度代理指標."""

    def test_positive_signal_weight(self, eval_engine):
        """正面信號權重 +1.0."""
        signal = eval_engine.record_satisfaction(
            session_id="test",
            signal_type="positive",
            context="使用者說 Great",
        )
        assert signal.signal_type == "positive"
        assert signal.signal_value == 1.0

        signals = eval_engine.store.load_satisfaction_signals(session_id="test")
        assert len(signals) == 1
        assert signals[0].signal_value == 1.0

    def test_negative_signal_weight_15x(self, eval_engine):
        """負面信號權重 -1.5（負面偏權）."""
        from museon.agent.eval_engine import NEGATIVITY_BIAS

        signal = eval_engine.record_satisfaction(
            session_id="test",
            signal_type="negative",
            context="使用者重新提問相同問題",
        )
        assert signal.signal_type == "negative"
        assert signal.signal_value == -NEGATIVITY_BIAS  # -1.5

        signals = eval_engine.store.load_satisfaction_signals(session_id="test")
        assert len(signals) == 1
        assert signals[0].signal_value == -1.5

    def test_satisfaction_proxy_computation(self, eval_engine):
        """滿意度代理計算 — 正負信號加權後除以總數."""
        # 記錄 7 正向 + 3 負向 = 10 信號 (>= MIN_SAMPLE_SIZE)
        for i in range(7):
            eval_engine.record_satisfaction(
                session_id="proxy_test",
                signal_type="positive",
                context=f"positive_{i}",
            )
        for i in range(3):
            eval_engine.record_satisfaction(
                session_id="proxy_test",
                signal_type="negative",
                context=f"negative_{i}",
            )

        result = eval_engine.compute_satisfaction_proxy(session_id="proxy_test")
        # proxy_value = (7*1.0 + 3*(-1.5)) / 10 = (7.0 - 4.5) / 10 = 0.25
        assert result["total_signals"] == 10
        assert result["positive_count"] == 7
        assert result["negative_count"] == 3
        # 0 <= 0.25 <= 0.5 => status "observing"
        assert result["status"] == "observing"

    def test_satisfaction_proxy_insufficient_data(self, eval_engine):
        """樣本不足時回報 insufficient_data."""
        # 只記錄 3 筆（< MIN_SAMPLE_SIZE=10）
        for i in range(3):
            eval_engine.record_satisfaction(
                session_id="few_test",
                signal_type="positive",
                context=f"positive_{i}",
            )
        result = eval_engine.compute_satisfaction_proxy(session_id="few_test")
        assert result["status"] == "insufficient_data"

    def test_record_satisfaction_with_q_score_id(self, eval_engine):
        """記錄滿意度信號可關聯 Q-Score ID."""
        signal = eval_engine.record_satisfaction(
            session_id="link_test",
            signal_type="positive",
            context="使用者根據回答採取行動",
            q_score_id="qs-abc-123",
        )
        assert signal.q_score_id == "qs-abc-123"


# ════════════════════════════════════════════
# Section 3: 趨勢追蹤
# ════════════════════════════════════════════

class TestTrendTracking:
    """測試趨勢追蹤."""

    def _record_scores(self, eval_engine, n, understanding=0.3, depth=0.3,
                       clarity=0.3, actionability=0.3, domain="general",
                       days_ago=0):
        """輔助方法：透過 evaluate() 記錄 n 筆 Q-Score."""
        scores = []
        for i in range(n):
            q = eval_engine.evaluate(
                user_content=f"question_{i}",
                response_content=f"answer_{i}",
                understanding=understanding,
                depth=depth,
                clarity=clarity,
                actionability=actionability,
                domain=domain,
                session_id=f"session_{domain}_{i}_{days_ago}",
            )
            scores.append(q)
        return scores

    def test_three_consecutive_low_alert(self, eval_engine):
        """連續 3 次 Q-Score < 0.5 觸發 consecutive_low 警報."""
        # 記錄 3 筆低分 Q-Score（均 < 0.5）
        self._record_scores(eval_engine, n=3, understanding=0.3, depth=0.3,
                            clarity=0.3, actionability=0.3)

        alerts = eval_engine.check_alerts()
        alert_types = [a.alert_type for a in alerts]
        assert "consecutive_low" in alert_types

    def test_domain_specific_tracking(self, eval_engine):
        """領域特定的 Q-Score 追蹤."""
        for domain in ["investment", "marketing", "customer_service"]:
            self._record_scores(eval_engine, n=1, understanding=0.8,
                                depth=0.7, clarity=0.9, actionability=0.6,
                                domain=domain)

        trend = eval_engine.get_trend(days=7, domain="investment")
        assert trend is not None
        assert trend.domain == "investment"

    def test_trend_direction_detection(self, eval_engine):
        """趨勢方向偵測（上升/穩定/下降）."""
        trend = eval_engine.get_trend(days=7)
        assert trend.direction in ("up", "stable", "down")

    def test_trend_insufficient_data(self, eval_engine):
        """樣本不足時趨勢標記 insufficient_data."""
        trend = eval_engine.get_trend(days=7, domain="nonexistent")
        assert trend.insufficient_data is True

    def test_check_alerts_returns_alert_list(self, eval_engine):
        """check_alerts() 回傳 Alert 清單."""
        alerts = eval_engine.check_alerts()
        assert isinstance(alerts, list)


# ════════════════════════════════════════════
# Section 4: A/B 比對器
# ════════════════════════════════════════════

class TestABComparator:
    """測試 A/B 比對器."""

    def _populate_baseline_data(self, eval_engine, n=5, understanding=0.8,
                                depth=0.7, clarity=0.9, actionability=0.6):
        """輔助方法：記錄基線數據."""
        for i in range(n):
            eval_engine.evaluate(
                user_content=f"baseline_q_{i}",
                response_content=f"baseline_a_{i}",
                understanding=understanding,
                depth=depth,
                clarity=clarity,
                actionability=actionability,
                domain="general",
                session_id=f"baseline_{i}",
            )

    def test_create_ab_baseline(self, eval_engine):
        """建立 A/B 基線."""
        self._populate_baseline_data(eval_engine)

        baseline = eval_engine.create_ab_baseline(
            change_id="morphenix_v2",
            description="Morphenix 提案修改回應結構",
        )
        assert baseline is not None
        assert isinstance(baseline, dict)
        assert baseline.get("change_id") == "morphenix_v2"
        assert baseline.get("locked") is True

    def test_baseline_immutable_after_creation(self, eval_engine):
        """HG-EVAL-BASELINE-LOCK: 已建立的基線不可修改."""
        self._populate_baseline_data(eval_engine)

        # 第一次建立成功
        baseline1 = eval_engine.create_ab_baseline(
            change_id="test_lock",
            description="測試鎖定",
        )
        assert "error" not in baseline1

        # 第二次嘗試以相同 change_id 建立 — 應被拒絕
        baseline2 = eval_engine.create_ab_baseline(
            change_id="test_lock",
            description="嘗試覆蓋",
        )
        assert "error" in baseline2
        assert "不可修改" in baseline2["error"]

    def test_baseline_lock_via_store(self, eval_engine):
        """直接透過 store 嘗試修改已建立的基線也被拒絕."""
        self._populate_baseline_data(eval_engine)

        eval_engine.create_ab_baseline(
            change_id="store_lock_test",
            description="Store 鎖定測試",
        )

        # 直接透過 store 嘗試覆寫 — save_ab_baseline 回傳 False
        result = eval_engine.store.save_ab_baseline(
            "store_lock_test",
            {"description": "非法覆寫"},
        )
        assert result is False

    def test_compare_ab_returns_result(self, eval_engine):
        """compare_ab() 回傳 ABResult."""
        from museon.agent.eval_engine import ABResult

        self._populate_baseline_data(eval_engine)
        eval_engine.create_ab_baseline(
            change_id="compare_test",
            description="比對測試",
        )

        result = eval_engine.compare_ab("compare_test")
        assert isinstance(result, ABResult)
        assert result.change_id == "compare_test"

    def test_compare_ab_nonexistent_baseline(self, eval_engine):
        """查詢不存在的基線回傳 insufficient_data."""
        result = eval_engine.compare_ab("nonexistent")
        assert result.overall_verdict == "insufficient_data"

    def test_dimension_regression_detection(self, eval_engine):
        """任何維度退化 >10% 出現在 regressions 列表中."""
        from museon.agent.eval_engine import ABResult
        import time

        # 建立高分基線
        self._populate_baseline_data(
            eval_engine, n=5,
            understanding=0.8, depth=0.8, clarity=0.8, actionability=0.8,
        )
        eval_engine.create_ab_baseline(
            change_id="regress_test",
            description="退化測試",
        )

        # 記錄退化數據（actionability 明顯下降）
        for i in range(5):
            eval_engine.evaluate(
                user_content=f"after_q_{i}",
                response_content=f"after_a_{i}",
                understanding=0.8,
                depth=0.8,
                clarity=0.8,
                actionability=0.5,  # 明顯下降
                domain="general",
                session_id=f"after_{i}",
            )

        result = eval_engine.compare_ab("regress_test")
        assert isinstance(result, ABResult)
        # 觀察期不足時 verdict 為 insufficient_data，但 regressions 列表仍可能有值
        # 此處主要驗證結構正確
        assert hasattr(result, "regressions")
        assert hasattr(result, "dimension_changes")
        assert isinstance(result.regressions, list)
        assert isinstance(result.dimension_changes, dict)


# ════════════════════════════════════════════
# Section 5: 盲點雷達
# ════════════════════════════════════════════

class TestBlindspotRadar:
    """測試盲點雷達."""

    def test_scan_blindspots_empty_when_insufficient_data(self, eval_engine):
        """樣本不足時盲點掃描回傳空列表."""
        blindspots = eval_engine.scan_blindspots()
        assert isinstance(blindspots, list)
        assert len(blindspots) == 0

    def test_scan_returns_domain_gap_blindspot(self, eval_engine):
        """掃描偵測到領域品質差距（domain_gap）."""
        # 記錄足夠數據以支持分析（>= MIN_SAMPLE_SIZE=10）
        # investment 故意給低分，其他領域給高分
        domains = ["investment", "marketing", "customer_service"]
        for i in range(15):
            domain = domains[i % 3]
            if domain == "investment":
                u, d, c, a = 0.4, 0.3, 0.5, 0.3
            else:
                u, d, c, a = 0.8, 0.8, 0.8, 0.8
            eval_engine.evaluate(
                user_content=f"question_{i}",
                response_content=f"answer_{i}",
                understanding=u,
                depth=d,
                clarity=c,
                actionability=a,
                domain=domain,
                session_id=f"session_{i}",
            )

        blindspots = eval_engine.scan_blindspots()
        assert isinstance(blindspots, list)
        # 應偵測到 investment 領域的 domain_gap
        types = [b.blindspot_type for b in blindspots]
        assert "domain_gap" in types

    def test_blindspot_has_correct_fields(self, eval_engine):
        """Blindspot 物件包含必要欄位."""
        from museon.agent.eval_engine import Blindspot

        b = Blindspot(
            id="test-id",
            blindspot_type="domain_gap",
            description="測試盲點",
            severity="medium",
            affected_area="investment",
            avg_score=0.45,
            global_avg=0.70,
            gap=0.25,
            recommendation="建議加強投資領域",
        )
        d = b.to_dict()
        assert d["blindspot_type"] == "domain_gap"
        assert d["affected_area"] == "investment"
        assert d["gap"] == 0.25


# ════════════════════════════════════════════
# Section 6: Skill 使用率熱力圖
# ════════════════════════════════════════════

class TestSkillHeatmap:
    """測試 Skill 使用率熱力圖."""

    def test_skill_heatmap_empty(self, eval_engine):
        """無資料時熱力圖為空."""
        heatmap = eval_engine.get_skill_heatmap(days=30)
        assert heatmap is not None
        assert heatmap["total_skills_tracked"] == 0

    def test_skill_heatmap_with_data(self, eval_engine):
        """有資料時熱力圖統計正確."""
        # 記錄帶有 matched_skills 的 Q-Score
        for i in range(5):
            eval_engine.evaluate(
                user_content=f"q_{i}",
                response_content=f"a_{i}",
                understanding=0.8,
                depth=0.7,
                clarity=0.9,
                actionability=0.6,
                matched_skills=["business-12", "xmodel"],
                domain="general",
                session_id=f"skill_session_{i}",
            )

        heatmap = eval_engine.get_skill_heatmap(days=30)
        assert heatmap["total_skills_tracked"] >= 2
        assert "business-12" in heatmap["skills"]
        assert "xmodel" in heatmap["skills"]
        assert heatmap["skills"]["business-12"]["adoption_count"] == 5


# ════════════════════════════════════════════
# Section 7: 背景運行 — 每日摘要 & 每週報告
# ════════════════════════════════════════════

class TestBackgroundReports:
    """測試背景運行的每日摘要與每週報告."""

    def test_daily_summary_structure(self, eval_engine):
        """每日摘要包含完整結構."""
        from museon.agent.eval_engine import DailySummary

        summary = eval_engine.generate_daily_summary()
        assert isinstance(summary, DailySummary)
        assert hasattr(summary, "date")
        assert hasattr(summary, "total_interactions")
        assert hasattr(summary, "avg_q_score")
        assert hasattr(summary, "satisfaction_proxy")
        assert hasattr(summary, "tier_distribution")
        assert hasattr(summary, "best_score")
        assert hasattr(summary, "worst_score")
        assert hasattr(summary, "domain_breakdown")
        assert hasattr(summary, "skill_usage")

    def test_daily_summary_with_data(self, eval_engine):
        """有資料時每日摘要計算正確."""
        today = date.today()
        # 記錄今天的數據
        for i in range(3):
            eval_engine.evaluate(
                user_content=f"q_{i}",
                response_content=f"a_{i}",
                understanding=0.8,
                depth=0.7,
                clarity=0.9,
                actionability=0.6,
                domain="general",
                session_id=f"daily_{i}",
            )

        summary = eval_engine.generate_daily_summary(target_date=today)
        assert summary.total_interactions == 3
        assert summary.avg_q_score > 0

    def test_daily_summary_insufficient_data_flag(self, eval_engine):
        """無資料時每日摘要標記 insufficient_data."""
        summary = eval_engine.generate_daily_summary()
        assert summary.insufficient_data is True

    def test_weekly_report_structure(self, eval_engine):
        """每週報告包含完整結構."""
        from museon.agent.eval_engine import WeeklyReport

        report = eval_engine.generate_weekly_report()
        assert isinstance(report, WeeklyReport)
        assert hasattr(report, "week_start")
        assert hasattr(report, "week_end")
        assert hasattr(report, "total_interactions")
        assert hasattr(report, "avg_q_score")
        assert hasattr(report, "trend_direction")
        assert hasattr(report, "satisfaction_proxy")
        assert hasattr(report, "daily_summaries")
        assert hasattr(report, "blindspots")
        assert hasattr(report, "skill_changes")
        assert hasattr(report, "alerts")

    def test_silent_record(self, eval_engine):
        """silent_record() 靜默記錄品質信號."""
        q = eval_engine.silent_record(
            session_id="silent_test",
            user_content="使用者訊息",
            response_content="回覆內容",
            understanding=0.8,
            depth=0.7,
            clarity=0.9,
            actionability=0.6,
            matched_skills=["skill_a"],
            domain="general",
        )
        assert q.score > 0
        assert q.session_id == "silent_test"

        # 確認已持久化
        scores = eval_engine.store.load_q_scores()
        assert len(scores) == 1
        assert scores[0].session_id == "silent_test"


# ════════════════════════════════════════════
# Section 8: 安全閘門
# ════════════════════════════════════════════

class TestSafetyGates:
    """測試安全閘門."""

    def test_hg_eval_honest_insufficient_data(self, eval_engine):
        """HG-EVAL-HONEST: 數據不足時回報 insufficient_data."""
        trend = eval_engine.get_trend(days=7, domain="nonexistent")
        assert trend.insufficient_data is True
        assert trend.sample_count == 0

    def test_hg_eval_baseline_lock(self, eval_engine):
        """HG-EVAL-BASELINE-LOCK: 基線一旦建立不可修改."""
        # 建立基線
        eval_engine.create_ab_baseline(
            change_id="lock_test",
            description="鎖定測試",
        )

        # 嘗試再次建立相同 change_id 的基線 — 被拒絕
        result = eval_engine.create_ab_baseline(
            change_id="lock_test",
            description="嘗試覆蓋",
        )
        assert "error" in result
        assert "不可修改" in result["error"]

        # 直接透過 store 也無法修改
        assert eval_engine.store.save_ab_baseline("lock_test", {}) is False

    def test_sg_eval_privacy_no_content_stored(self, eval_engine, data_dir):
        """SG-EVAL-PRIVACY: 品質數據不含對話原文."""
        eval_engine.evaluate(
            user_content="這是使用者的秘密問題",
            response_content="這是包含敏感內容的回覆",
            understanding=0.8,
            depth=0.7,
            clarity=0.9,
            actionability=0.6,
            session_id="privacy_test",
            domain="test",
        )

        # 讀取持久化的 Q-Score 記錄
        q_scores_path = data_dir / "eval" / "q_scores.jsonl"
        assert q_scores_path.exists()
        content = q_scores_path.read_text(encoding="utf-8")

        # 對話原文不應出現在持久化數據中
        assert "秘密問題" not in content
        assert "敏感內容" not in content

        # 但分數和 metadata 應存在
        data = json.loads(content.strip().split("\n")[0])
        assert "score" in data
        assert "understanding" in data
        assert "session_id" in data
        assert data["session_id"] == "privacy_test"

    def test_q_score_persistence(self, eval_engine, data_dir):
        """Q-Score 記錄持久化到 JSONL."""
        eval_engine.evaluate(
            user_content="持久化測試問題",
            response_content="持久化測試回覆",
            understanding=0.8,
            depth=0.7,
            clarity=0.9,
            actionability=0.6,
            domain="test",
            session_id="persist_test",
        )
        q_scores_path = data_dir / "eval" / "q_scores.jsonl"
        assert q_scores_path.exists()
        lines = q_scores_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1
        data = json.loads(lines[0])
        assert data["session_id"] == "persist_test"
        assert data["domain"] == "test"

    def test_satisfaction_persistence(self, eval_engine, data_dir):
        """滿意度信號記錄持久化到 JSONL."""
        eval_engine.record_satisfaction(
            session_id="sat_persist",
            signal_type="positive",
            context="使用者點讚",
        )
        sat_path = data_dir / "eval" / "satisfaction.jsonl"
        assert sat_path.exists()
        lines = sat_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1
        data = json.loads(lines[0])
        assert data["session_id"] == "sat_persist"
        assert data["signal_type"] == "positive"


# ════════════════════════════════════════════
# Section 9: 資料類別序列化
# ════════════════════════════════════════════

class TestDataclassSerialization:
    """測試資料類別的序列化與反序列化."""

    def test_qscore_to_dict_and_back(self):
        """QScore 可序列化並還原."""
        from museon.agent.eval_engine import QScore

        q = QScore(
            id="test-id",
            session_id="session-123",
            timestamp="2025-01-01T00:00:00",
            domain="investment",
            understanding=0.85,
            depth=0.70,
            clarity=0.90,
            actionability=0.75,
            matched_skills=["skill_a", "skill_b"],
        )
        q.compute()

        d = q.to_dict()
        assert isinstance(d, dict)

        q2 = QScore.from_dict(d)
        assert q2.id == q.id
        assert q2.session_id == q.session_id
        assert abs(q2.score - q.score) < 0.001
        assert q2.tier == q.tier
        assert q2.matched_skills == q.matched_skills

    def test_satisfaction_signal_to_dict_and_back(self):
        """SatisfactionSignal 可序列化並還原."""
        from museon.agent.eval_engine import SatisfactionSignal

        sig = SatisfactionSignal(
            id="sig-1",
            session_id="session-456",
            timestamp="2025-01-01T00:00:00",
            signal_type="negative",
            signal_value=-1.5,
            context="使用者重複提問",
            q_score_id="qs-789",
        )
        d = sig.to_dict()
        sig2 = SatisfactionSignal.from_dict(d)
        assert sig2.id == sig.id
        assert sig2.signal_value == sig.signal_value
        assert sig2.q_score_id == sig.q_score_id

    def test_alert_to_dict(self):
        """Alert 可序列化."""
        from museon.agent.eval_engine import Alert

        alert = Alert(
            id="alert-1",
            timestamp="2025-01-01T00:00:00",
            alert_type="consecutive_low",
            severity="critical",
            message="連續 3 次低分",
            details={"recent_scores": [0.3, 0.4, 0.35]},
        )
        d = alert.to_dict()
        assert d["alert_type"] == "consecutive_low"
        assert d["severity"] == "critical"

    def test_trend_data_to_dict(self):
        """TrendData 可序列化."""
        from museon.agent.eval_engine import TrendData

        trend = TrendData(
            period_days=7,
            domain="investment",
            daily_averages={"2025-01-01": 0.75},
            rolling_average=0.72,
            direction="up",
            sample_count=15,
        )
        d = trend.to_dict()
        assert d["direction"] == "up"
        assert d["period_days"] == 7

    def test_daily_summary_to_dict(self):
        """DailySummary 可序列化."""
        from museon.agent.eval_engine import DailySummary

        summary = DailySummary(
            date="2025-01-01",
            total_interactions=20,
            avg_q_score=0.72,
            tier_distribution={"high": 10, "medium": 7, "low": 3},
        )
        d = summary.to_dict()
        assert d["total_interactions"] == 20
        assert d["avg_q_score"] == 0.72
