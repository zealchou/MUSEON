"""部門配置 BDD 測試.

依據 MULTI_AGENT_BDD_SPEC §2 驗證。
"""

import pytest

from museon.multiagent.department_config import (
    FLYWHEEL_ORDER,
    DepartmentConfig,
    get_all_departments,
    get_department,
    get_flywheel_departments,
    get_next_dept,
    get_prev_dept,
)


class TestDepartmentConfigBasics:
    """Scenario: 基礎結構驗證."""

    def test_total_10_departments(self):
        assert len(get_all_departments()) == 10

    def test_flywheel_order_has_8(self):
        assert len(FLYWHEEL_ORDER) == 8

    def test_flywheel_depts_count(self):
        fw = get_flywheel_departments()
        assert len(fw) == 8

    def test_flywheel_depts_sorted(self):
        fw = get_flywheel_departments()
        orders = [d.flywheel_order for d in fw]
        assert orders == list(range(1, 9))


class TestFlywheelCycle:
    """Scenario: 飛輪循環完整性."""

    def test_each_next_points_forward(self):
        """每個部門的 next_dept 指向下一個."""
        for i, dept_id in enumerate(FLYWHEEL_ORDER):
            dept = get_department(dept_id)
            expected_next = FLYWHEEL_ORDER[(i + 1) % 8]
            assert dept.next_dept == expected_next, (
                f"{dept_id}.next_dept should be {expected_next}, "
                f"got {dept.next_dept}"
            )

    def test_each_prev_points_back(self):
        """每個部門的 prev_dept 指向上一個."""
        for i, dept_id in enumerate(FLYWHEEL_ORDER):
            dept = get_department(dept_id)
            expected_prev = FLYWHEEL_ORDER[(i - 1) % 8]
            assert dept.prev_dept == expected_prev

    def test_earth_next_is_thunder(self):
        assert get_next_dept("earth") == "thunder"

    def test_thunder_prev_is_earth(self):
        assert get_prev_dept("thunder") == "earth"


class TestCentralDepartments:
    """Scenario: 中央部門不參與飛輪."""

    def test_core_no_flywheel(self):
        core = get_department("core")
        assert core.flywheel_order == 0
        assert core.next_dept is None
        assert core.prev_dept is None

    def test_okr_no_flywheel(self):
        okr = get_department("okr")
        assert okr.flywheel_order == 0
        assert okr.next_dept is None
        assert okr.prev_dept is None


class TestUniqueEmojis:
    """Scenario: 所有部門有唯一 emoji."""

    def test_all_emojis_unique(self):
        depts = get_all_departments()
        emojis = [d.emoji for d in depts.values()]
        assert len(emojis) == len(set(emojis))

    def test_all_dept_ids_unique(self):
        depts = get_all_departments()
        assert len(depts) == 10


class TestDepartmentKeywords:
    """Scenario: 每個部門都有關鍵字."""

    def test_all_have_keywords(self):
        for dept_id, dept in get_all_departments().items():
            assert len(dept.keywords) >= 3, (
                f"{dept_id} should have at least 3 keywords"
            )

    def test_all_have_prompt_section(self):
        for dept_id, dept in get_all_departments().items():
            assert dept.prompt_section, (
                f"{dept_id} should have a prompt_section"
            )


class TestGetDepartmentAPI:
    """Scenario: Public API 驗證."""

    def test_get_existing(self):
        dept = get_department("thunder")
        assert dept is not None
        assert dept.name == "行動執行"

    def test_get_nonexistent(self):
        assert get_department("nonexistent") is None

    def test_get_next_nonexistent(self):
        assert get_next_dept("nonexistent") is None

    def test_get_prev_nonexistent(self):
        assert get_prev_dept("nonexistent") is None
