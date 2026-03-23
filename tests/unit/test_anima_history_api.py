"""PulseDB Anima History API 單元測試.

Project Epigenesis 迭代 2：暴露八元素變化歷史查詢。
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from museon.pulse.pulse_db import PulseDB


@pytest.fixture
def pulse_db():
    """建立帶測試資料的 PulseDB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "pulse.db")
        db = PulseDB(db_path=db_path)

        # 寫入測試資料：模擬 7 天的八元素變化
        now = datetime.now()
        test_data = [
            # Day -6: kun +2
            (now - timedelta(days=6), "kun", 2, "治理: 後天免疫命中 1 次", 102),
            # Day -5: kun +3, xun +1
            (now - timedelta(days=5), "kun", 3, "治理: 後天免疫命中 2 次", 105),
            (now - timedelta(days=5), "xun", 1, "治理: 趨勢惡化，探索根因", 51),
            # Day -3: qian +1
            (now - timedelta(days=3), "qian", 1, "治理: 系統壓力下持續運作", 31),
            # Day -1: kun +2, dui +1
            (now - timedelta(days=1), "kun", 2, "治理: 後天免疫命中 1 次", 107),
            (now - timedelta(days=1), "dui", 1, "治理: 連續健康穩定連結", 21),
            # Today: kun +1
            (now, "kun", 1, "治理: 後天免疫命中 1 次", 108),
        ]

        conn = db._get_conn()
        for ts, elem, delta, reason, abs_after in test_data:
            conn.execute(
                "INSERT INTO anima_log (timestamp, element, delta, reason, absolute_after) "
                "VALUES (?, ?, ?, ?, ?)",
                (ts.isoformat(), elem, delta, reason, abs_after),
            )
        conn.commit()

        yield db


class TestGetAnimaHistoryByDays:
    """get_anima_history_by_days() 測試."""

    def test_raw_granularity(self, pulse_db):
        """raw 粒度返回原始記錄."""
        results = pulse_db.get_anima_history_by_days(
            element="kun", days=7, granularity="raw"
        )
        assert len(results) == 4  # kun 有 4 筆
        assert all(r["element"] == "kun" for r in results)

    def test_raw_all_elements(self, pulse_db):
        """不指定元素返回全部."""
        results = pulse_db.get_anima_history_by_days(
            days=7, granularity="raw"
        )
        assert len(results) == 7
        elements = set(r["element"] for r in results)
        assert elements == {"kun", "xun", "qian", "dui"}

    def test_daily_granularity(self, pulse_db):
        """daily 粒度按天聚合."""
        results = pulse_db.get_anima_history_by_days(
            element="kun", days=7, granularity="daily"
        )
        # kun 在 4 天有變化
        assert len(results) == 4
        # 第一天 delta=2
        assert results[0]["total_delta"] == 2
        assert results[0]["change_count"] == 1
        # 第二天 delta=3
        assert results[1]["total_delta"] == 3

    def test_weekly_granularity(self, pulse_db):
        """weekly 粒度按週聚合."""
        results = pulse_db.get_anima_history_by_days(
            element="kun", days=7, granularity="weekly"
        )
        # 應該是 1-2 週
        assert len(results) >= 1
        total = sum(r["total_delta"] for r in results)
        assert total == 8  # 2+3+2+1

    def test_days_filter(self, pulse_db):
        """天數過濾."""
        results_7d = pulse_db.get_anima_history_by_days(
            element="kun", days=7, granularity="raw"
        )
        results_2d = pulse_db.get_anima_history_by_days(
            element="kun", days=2, granularity="raw"
        )
        assert len(results_7d) > len(results_2d)

    def test_empty_result(self, pulse_db):
        """查無資料時返回空列表."""
        results = pulse_db.get_anima_history_by_days(
            element="gen", days=7, granularity="raw"
        )
        assert results == []


class TestGetAnimaTrend:
    """get_anima_trend() 測試."""

    def test_trend_basic(self, pulse_db):
        """基本趨勢計算."""
        trend = pulse_db.get_anima_trend("kun", days=7)
        assert trend["element"] == "kun"
        assert trend["total_growth"] == 8  # 2+3+2+1
        assert trend["end_absolute"] == 108
        assert trend["primary_reason"] is not None
        assert "後天免疫" in trend["primary_reason"]

    def test_trend_empty_element(self, pulse_db):
        """無資料的元素返回零值."""
        trend = pulse_db.get_anima_trend("gen", days=7)
        assert trend["total_growth"] == 0
        assert trend["avg_daily_growth"] == 0.0
        assert trend["most_active_day"] is None

    def test_trend_growth_rate(self, pulse_db):
        """成長率計算."""
        trend = pulse_db.get_anima_trend("kun", days=7)
        assert trend["growth_rate"] > 0
        # start = 102 - 2 = 100, growth = 8, rate = 8/100 = 0.08
        assert trend["growth_rate"] == 0.08

    def test_trend_most_active_day(self, pulse_db):
        """最活躍的一天."""
        trend = pulse_db.get_anima_trend("kun", days=7)
        assert trend["most_active_day"] is not None
