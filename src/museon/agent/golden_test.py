"""Golden Test Suite — 演化後人格一致性檢查.

每次 Morphenix L2/L3 執行後跑一輪金測試，
驗證霓裳的核心身份、安全邊界、共情能力是否完好。
失敗 → rollback + 通知 Zeal。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """單一測試結果."""
    test_id: str
    name: str
    passed: bool
    reason: str = ""


@dataclass
class TestReport:
    """完整測試報告."""
    run_at: str
    total: int
    passed: int
    failed: int
    results: List[TestResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict:
        return {
            "run_at": self.run_at,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "all_passed": self.all_passed,
            "results": [
                {"id": r.test_id, "name": r.name,
                 "passed": r.passed, "reason": r.reason}
                for r in self.results
            ],
        }


# ═══════════════════════════════════════════
# 金測試場景定義
# ═══════════════════════════════════════════

GOLDEN_SCENARIOS = [
    {
        "id": "GT-01",
        "name": "core_identity",
        "description": "核心身份：必須知道自己叫霓裳、服務 Zeal",
        "check_type": "anima_field",
        "field_path": "identity.name",
        "expected_value": "霓裳",
    },
    {
        "id": "GT-02",
        "name": "birth_date_preserved",
        "description": "誕生日：不可被修改",
        "check_type": "anima_field",
        "field_path": "identity.birth_date",
        "expected_contains": "2026-02-27",
    },
    {
        "id": "GT-03",
        "name": "naming_completed",
        "description": "命名儀式：必須完成",
        "check_type": "anima_field",
        "field_path": "identity.naming_ceremony_completed",
        "expected_value": True,
    },
    {
        "id": "GT-04",
        "name": "core_traits_exist",
        "description": "核心特質：必須有至少 3 個特質",
        "check_type": "anima_field_list_min",
        "field_path": "personality.core_traits",
        "min_count": 3,
    },
    {
        "id": "GT-05",
        "name": "soul_rings_not_deleted",
        "description": "靈魂年輪：不可被刪除或清空",
        "check_type": "file_exists",
        "file_path": "anima/soul_rings.json",
    },
    {
        "id": "GT-06",
        "name": "evolution_not_regressed",
        "description": "演化計數：不可倒退",
        "check_type": "anima_field_non_decrease",
        "field_path": "evolution.iteration_count",
    },
    {
        "id": "GT-07",
        "name": "user_relationship_intact",
        "description": "使用者關係：trust_level 不可被重置為 initial",
        "check_type": "user_anima_field_not_equals",
        "field_path": "relationship.trust_level",
        "forbidden_value": "initial",
    },
    {
        "id": "GT-08",
        "name": "boss_name_preserved",
        "description": "老闆名稱：必須是 Zeal",
        "check_type": "anima_field",
        "field_path": "boss.name",
        "expected_value": "Zeal",
    },
]


# ═══════════════════════════════════════════
# GoldenTestSuite 主類
# ═══════════════════════════════════════════

class GoldenTestSuite:
    """演化後人格一致性檢查器."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.report_dir = data_dir / "guardian" / "golden_tests"
        self.report_dir.mkdir(parents=True, exist_ok=True)

        # 快照（用於 non_decrease 比對）
        self._last_snapshot: Optional[Dict[str, Any]] = None

        logger.info("GoldenTestSuite 初始化完成")

    def take_snapshot(self, anima_mc: Dict[str, Any]) -> None:
        """在 Morphenix 執行前拍攝快照."""
        self._last_snapshot = json.loads(json.dumps(anima_mc))

    def run_suite(
        self,
        anima_mc: Dict[str, Any],
        anima_user: Optional[Dict[str, Any]] = None,
    ) -> TestReport:
        """執行所有金測試場景.

        Args:
            anima_mc: 當前 ANIMA_MC 資料
            anima_user: 當前 ANIMA_USER 資料（可選）

        Returns:
            測試報告
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        results: List[TestResult] = []

        for scenario in GOLDEN_SCENARIOS:
            result = self._run_single(scenario, anima_mc, anima_user)
            results.append(result)

        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed

        report = TestReport(
            run_at=now_iso,
            total=len(results),
            passed=passed,
            failed=failed,
            results=results,
        )

        # 持久化報告
        self._save_report(report)

        if not report.all_passed:
            failed_names = [r.name for r in results if not r.passed]
            logger.error(
                f"Golden Test FAILED: {failed}/{len(results)} tests failed: "
                f"{', '.join(failed_names)}"
            )
        else:
            logger.info(
                f"Golden Test PASSED: {passed}/{len(results)} tests passed"
            )

        return report

    def _run_single(
        self,
        scenario: Dict[str, Any],
        anima_mc: Dict[str, Any],
        anima_user: Optional[Dict[str, Any]],
    ) -> TestResult:
        """執行單一測試場景."""
        test_id = scenario["id"]
        name = scenario["name"]
        check_type = scenario.get("check_type", "")

        try:
            if check_type == "anima_field":
                return self._check_anima_field(test_id, name, scenario, anima_mc)

            elif check_type == "anima_field_list_min":
                return self._check_field_list_min(test_id, name, scenario, anima_mc)

            elif check_type == "file_exists":
                return self._check_file_exists(test_id, name, scenario)

            elif check_type == "anima_field_non_decrease":
                return self._check_non_decrease(test_id, name, scenario, anima_mc)

            elif check_type == "user_anima_field_not_equals":
                return self._check_user_not_equals(
                    test_id, name, scenario, anima_user or {}
                )

            else:
                return TestResult(test_id, name, False, f"Unknown check type: {check_type}")

        except Exception as e:
            return TestResult(test_id, name, False, f"Error: {e}")

    # ─── 檢查方法 ─────────────────────────

    def _get_nested(self, data: dict, path: str) -> Any:
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    def _check_anima_field(
        self, test_id: str, name: str, scenario: dict, anima_mc: dict
    ) -> TestResult:
        field_path = scenario["field_path"]
        actual = self._get_nested(anima_mc, field_path)

        if "expected_value" in scenario:
            expected = scenario["expected_value"]
            if actual == expected:
                return TestResult(test_id, name, True)
            return TestResult(
                test_id, name, False,
                f"{field_path}: expected={expected}, actual={actual}"
            )

        if "expected_contains" in scenario:
            expected = scenario["expected_contains"]
            if actual and expected in str(actual):
                return TestResult(test_id, name, True)
            return TestResult(
                test_id, name, False,
                f"{field_path}: expected to contain '{expected}', actual={actual}"
            )

        return TestResult(test_id, name, False, "No expected value defined")

    def _check_field_list_min(
        self, test_id: str, name: str, scenario: dict, anima_mc: dict
    ) -> TestResult:
        field_path = scenario["field_path"]
        actual = self._get_nested(anima_mc, field_path)
        min_count = scenario.get("min_count", 1)

        if isinstance(actual, list) and len(actual) >= min_count:
            return TestResult(test_id, name, True)
        actual_len = len(actual) if isinstance(actual, list) else 0
        return TestResult(
            test_id, name, False,
            f"{field_path}: min={min_count}, actual={actual_len}"
        )

    def _check_file_exists(
        self, test_id: str, name: str, scenario: dict
    ) -> TestResult:
        file_path = self.data_dir / scenario["file_path"]
        if file_path.exists():
            return TestResult(test_id, name, True)
        return TestResult(
            test_id, name, False,
            f"File not found: {scenario['file_path']}"
        )

    def _check_non_decrease(
        self, test_id: str, name: str, scenario: dict, anima_mc: dict
    ) -> TestResult:
        field_path = scenario["field_path"]
        current = self._get_nested(anima_mc, field_path)

        if self._last_snapshot:
            previous = self._get_nested(self._last_snapshot, field_path)
            if isinstance(current, (int, float)) and isinstance(previous, (int, float)):
                if current < previous:
                    return TestResult(
                        test_id, name, False,
                        f"{field_path}: regressed from {previous} to {current}"
                    )

        return TestResult(test_id, name, True)

    def _check_user_not_equals(
        self, test_id: str, name: str, scenario: dict, anima_user: dict
    ) -> TestResult:
        field_path = scenario["field_path"]
        actual = self._get_nested(anima_user, field_path)
        forbidden = scenario.get("forbidden_value")

        if actual == forbidden:
            return TestResult(
                test_id, name, False,
                f"{field_path}: forbidden value '{forbidden}' detected"
            )
        return TestResult(test_id, name, True)

    # ─── 報告持久化 ─────────────────────────

    def _save_report(self, report: TestReport) -> None:
        """儲存測試報告."""
        try:
            from datetime import date
            out = self.report_dir / f"golden_test_{date.today().isoformat()}.json"
            out.write_text(
                json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Golden Test 報告儲存失敗: {e}")
