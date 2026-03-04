"""SkillManager BDD 測試.

依據 SKILL_MANAGER_BDD_SPEC §5-§13 驗證。
"""

import json
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from museon.core.skill_manager import (
    SkillManager,
    PROMOTE_MIN_SUCCESS,
    DEPRECATE_FAIL_RATE,
    ARCHIVE_INACTIVE_DAYS,
    MAX_ACTIVE_PROMPT,
    _DEFAULT_META,
)


TZ_TAIPEI = timezone(timedelta(hours=8))


# ═══════════════════════════════════════════
# Helpers — 建立測試用 skill 目錄結構
# ═══════════════════════════════════════════

def _make_skill(base_dir: Path, origin: str, name: str,
                content: str = "---\nname: {name}\ndescription: A test skill\n---\n# {name}\nSafe text.",
                meta: dict = None):
    """在 base_dir/skills/{origin}/{name}/ 建立 SKILL.md（可選 _meta.json）."""
    skill_dir = base_dir / "skills" / origin / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    resolved = content.replace("{name}", name)
    (skill_dir / "SKILL.md").write_text(resolved, encoding="utf-8")
    if meta is not None:
        (skill_dir / "_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return skill_dir


def _make_manager(tmp_path: Path) -> SkillManager:
    """建立指向 tmp_path 的 SkillManager."""
    (tmp_path / "skills" / "native").mkdir(parents=True, exist_ok=True)
    (tmp_path / "skills" / "forged").mkdir(parents=True, exist_ok=True)
    return SkillManager(workspace=tmp_path)


# ═══════════════════════════════════════════
# TestConstants — 常數驗證
# ═══════════════════════════════════════════

class TestConstants:
    """Scenario: lifecycle 常數與預設 meta."""

    def test_promote_min_success(self):
        assert PROMOTE_MIN_SUCCESS == 3

    def test_deprecate_fail_rate(self):
        assert DEPRECATE_FAIL_RATE == 0.5

    def test_archive_inactive_days(self):
        assert ARCHIVE_INACTIVE_DAYS == 30

    def test_max_active_prompt(self):
        assert MAX_ACTIVE_PROMPT == 10

    def test_default_meta_has_lifecycle(self):
        assert _DEFAULT_META["lifecycle"] == "experimental"

    def test_default_meta_has_zero_counts(self):
        assert _DEFAULT_META["use_count"] == 0
        assert _DEFAULT_META["success_count"] == 0
        assert _DEFAULT_META["failure_count"] == 0


# ═══════════════════════════════════════════
# TestDiscoverSkills — 發現技能
# ═══════════════════════════════════════════

class TestDiscoverSkills:
    """Scenario: discover_skills() 掃描結果."""

    def test_empty_workspace(self, tmp_path):
        mgr = _make_manager(tmp_path)
        result = mgr.discover_skills()
        assert result == []

    def test_finds_native_skill(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "native", "test-skill")
        result = mgr.discover_skills()
        assert len(result) == 1
        assert result[0]["name"] == "test-skill"
        assert result[0]["origin"] == "native"

    def test_native_default_lifecycle_stable(self, tmp_path):
        """Native skill 無 _meta.json 時預設 lifecycle=stable."""
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "native", "test-skill")
        result = mgr.discover_skills()
        assert result[0]["lifecycle"] == "stable"

    def test_forged_default_lifecycle_experimental(self, tmp_path):
        """Forged skill 無 _meta.json 時預設 lifecycle=experimental."""
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "forged", "test-forged")
        result = mgr.discover_skills()
        assert result[0]["lifecycle"] == "experimental"

    def test_respects_meta_json_lifecycle(self, tmp_path):
        """有 _meta.json 時使用其 lifecycle 值."""
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "native", "custom-lc",
                     meta={"lifecycle": "deprecated", "use_count": 5})
        result = mgr.discover_skills()
        assert result[0]["lifecycle"] == "deprecated"
        assert result[0]["use_count"] == 5

    def test_finds_both_origins(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "native", "skill-a")
        _make_skill(tmp_path, "forged", "skill-b")
        result = mgr.discover_skills()
        names = {s["name"] for s in result}
        assert names == {"skill-a", "skill-b"}

    def test_skips_dir_without_skill_md(self, tmp_path):
        mgr = _make_manager(tmp_path)
        # 建立空目錄（無 SKILL.md）
        empty = tmp_path / "skills" / "native" / "empty-skill"
        empty.mkdir(parents=True, exist_ok=True)
        result = mgr.discover_skills()
        assert result == []


# ═══════════════════════════════════════════
# TestListSkills — 篩選列出
# ═══════════════════════════════════════════

class TestListSkills:
    """Scenario: list_skills() lifecycle 過濾."""

    def test_no_filter(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "native", "a")
        _make_skill(tmp_path, "forged", "b")
        result = mgr.list_skills()
        assert len(result) == 2

    def test_filter_by_lifecycle(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "native", "stable-one")
        _make_skill(tmp_path, "forged", "exp-one")
        result = mgr.list_skills(lifecycle="experimental")
        assert len(result) == 1
        assert result[0]["name"] == "exp-one"


# ═══════════════════════════════════════════
# TestGetSkill — 單一技能詳情
# ═══════════════════════════════════════════

class TestGetSkill:
    """Scenario: get_skill() 完整資訊."""

    def test_existing_skill(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "native", "test-get",
                     content="---\nname: test-get\ndescription: Get me\n---\n# Test\nBody.")
        result = mgr.get_skill("test-get")
        assert result is not None
        assert result["name"] == "test-get"
        assert result["description"] == "Get me"
        assert result["meta"]["lifecycle"] == "stable"

    def test_nonexistent_skill(self, tmp_path):
        mgr = _make_manager(tmp_path)
        result = mgr.get_skill("no-such-skill")
        assert result is None


# ═══════════════════════════════════════════
# TestInstallSkill — 安裝流程
# ═══════════════════════════════════════════

class TestInstallSkill:
    """Scenario: install_skill() 安全掃描 + 寫入."""

    def test_safe_install(self, tmp_path):
        mgr = _make_manager(tmp_path)
        content = "---\nname: new-skill\ndescription: Safe\n---\n# New\nJust text."
        result = mgr.install_skill("new-skill", content, source="forged")
        assert result["installed"] is True
        assert result["name"] == "new-skill"
        assert result["lifecycle"] == "experimental"
        # 確認檔案存在
        assert (tmp_path / "skills" / "forged" / "new-skill" / "SKILL.md").exists()
        assert (tmp_path / "skills" / "forged" / "new-skill" / "_meta.json").exists()

    def test_unsafe_blocked(self, tmp_path):
        mgr = _make_manager(tmp_path)
        content = "Use eval(user_input) to compute"
        result = mgr.install_skill("evil-skill", content)
        assert result["installed"] is False
        assert result["reason"] == "security_scan_failed"
        # 確認目錄未建立
        assert not (tmp_path / "skills" / "forged" / "evil-skill" / "SKILL.md").exists()

    def test_force_bypass(self, tmp_path):
        mgr = _make_manager(tmp_path)
        content = "Use eval(user_input) to compute"
        result = mgr.install_skill("force-skill", content, force=True)
        assert result["installed"] is True
        assert (tmp_path / "skills" / "forged" / "force-skill" / "SKILL.md").exists()

    def test_meta_json_created_on_install(self, tmp_path):
        mgr = _make_manager(tmp_path)
        content = "---\nname: meta-check\ndescription: Test\n---\nSafe."
        mgr.install_skill("meta-check", content)
        meta_path = tmp_path / "skills" / "forged" / "meta-check" / "_meta.json"
        meta = json.loads(meta_path.read_text())
        assert meta["lifecycle"] == "experimental"
        assert meta["source"] == "forged"
        assert meta["security_scan"] is not None
        assert meta["security_scan"]["safe"] is True


# ═══════════════════════════════════════════
# TestRecordUse — 使用追蹤 + 即時 lifecycle
# ═══════════════════════════════════════════

class TestRecordUse:
    """Scenario: record_use() 計數與 lifecycle 轉換."""

    def test_increment_counts(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "forged", "count-test",
                     meta={"lifecycle": "experimental", "use_count": 0,
                           "success_count": 0, "failure_count": 0})
        result = mgr.record_use("count-test", success=True)
        assert result["recorded"] is True
        assert result["use_count"] == 1

    def test_failure_count(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "forged", "fail-test",
                     meta={"lifecycle": "experimental", "use_count": 0,
                           "success_count": 0, "failure_count": 0})
        mgr.record_use("fail-test", success=False)
        meta_path = tmp_path / "skills" / "forged" / "fail-test" / "_meta.json"
        meta = json.loads(meta_path.read_text())
        assert meta["failure_count"] == 1

    def test_lifecycle_promotion(self, tmp_path):
        """experimental + 3 次成功 → stable."""
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "forged", "promo-test",
                     meta={"lifecycle": "experimental", "use_count": 2,
                           "success_count": 2, "failure_count": 0})
        result = mgr.record_use("promo-test", success=True)
        assert result["lifecycle"] == "stable"
        assert result["transitioned"] is True

    def test_not_found_skill(self, tmp_path):
        mgr = _make_manager(tmp_path)
        result = mgr.record_use("nonexistent")
        assert result["recorded"] is False
        assert result["reason"] == "skill_not_found"

    def test_stable_deprecation(self, tmp_path):
        """stable + >50% 失敗率 → deprecated."""
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "forged", "deprecate-test",
                     meta={"lifecycle": "stable", "use_count": 5,
                           "success_count": 2, "failure_count": 3})
        # 再加一次失敗 → success=2, failure=4 → 失敗率 4/6=66% > 50%
        result = mgr.record_use("deprecate-test", success=False)
        assert result["lifecycle"] == "deprecated"
        assert result["transitioned"] is True


# ═══════════════════════════════════════════
# TestScanSkill — 安全掃描
# ═══════════════════════════════════════════

class TestScanSkill:
    """Scenario: scan_skill() + scan_all()."""

    def test_scan_single_safe(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "native", "safe-scan",
                     content="---\nname: safe-scan\ndescription: Safe\n---\nJust text.")
        result = mgr.scan_skill("safe-scan")
        assert result["safe"] is True

    def test_scan_updates_meta(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "forged", "scan-meta",
                     meta={"lifecycle": "experimental", "security_scan": None})
        result = mgr.scan_skill("scan-meta")
        meta_path = tmp_path / "skills" / "forged" / "scan-meta" / "_meta.json"
        meta = json.loads(meta_path.read_text())
        assert meta["security_scan"] is not None
        assert "last_scanned" in meta["security_scan"]

    def test_scan_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        result = mgr.scan_skill("ghost")
        assert "error" in result

    def test_scan_all(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "native", "all-a")
        _make_skill(tmp_path, "native", "all-b")
        result = mgr.scan_all()
        assert result["total_scanned"] == 2
        assert result["safe_count"] == 2
        assert result["unsafe_count"] == 0


# ═══════════════════════════════════════════
# TestNightlyMaintenance — 夜間維護
# ═══════════════════════════════════════════

class TestNightlyMaintenance:
    """Scenario: nightly_maintenance() lifecycle 處理."""

    def test_deprecated_archived_after_30_days(self, tmp_path):
        """deprecated + 30 天閒置 → archived."""
        mgr = _make_manager(tmp_path)
        old_date = (datetime.now(TZ_TAIPEI) - timedelta(days=35)).isoformat()
        _make_skill(tmp_path, "forged", "old-deprecated",
                     meta={"lifecycle": "deprecated", "use_count": 5,
                           "success_count": 2, "failure_count": 3,
                           "last_used": old_date})
        result = mgr.nightly_maintenance()
        assert result["archived"] == 1
        # 確認 meta 已更新
        meta_path = tmp_path / "skills" / "forged" / "old-deprecated" / "_meta.json"
        meta = json.loads(meta_path.read_text())
        assert meta["lifecycle"] == "archived"

    def test_stable_not_touched(self, tmp_path):
        """stable 不受夜間維護影響（無失敗記錄時）."""
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "forged", "stable-ok",
                     meta={"lifecycle": "stable", "use_count": 10,
                           "success_count": 10, "failure_count": 0,
                           "last_used": datetime.now(TZ_TAIPEI).isoformat()})
        result = mgr.nightly_maintenance()
        assert result["promoted"] == 0
        assert result["deprecated"] == 0
        assert result["archived"] == 0

    def test_nightly_promotes_experimental(self, tmp_path):
        """experimental + 3+ 成功 → stable（夜間也會檢查）."""
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "forged", "promo-nightly",
                     meta={"lifecycle": "experimental", "use_count": 5,
                           "success_count": 4, "failure_count": 1})
        result = mgr.nightly_maintenance()
        assert result["promoted"] == 1

    def test_skips_no_meta(self, tmp_path):
        """無 _meta.json 的 skill 不處理."""
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "native", "no-meta")
        result = mgr.nightly_maintenance()
        assert result == {"promoted": 0, "deprecated": 0, "archived": 0}


# ═══════════════════════════════════════════
# TestGetActiveSkillsPrompt — Prompt 注入
# ═══════════════════════════════════════════

class TestGetActiveSkillsPrompt:
    """Scenario: get_active_skills_prompt() 輸出."""

    def test_empty_returns_empty_string(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.get_active_skills_prompt() == ""

    def test_max_10_skills(self, tmp_path):
        mgr = _make_manager(tmp_path)
        for i in range(15):
            _make_skill(tmp_path, "native", f"skill-{i:02d}")
        prompt = mgr.get_active_skills_prompt()
        lines = [l for l in prompt.split("\n") if l.strip()]
        assert len(lines) == MAX_ACTIVE_PROMPT

    def test_excludes_deprecated(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "forged", "active-one",
                     meta={"lifecycle": "stable", "use_count": 1})
        _make_skill(tmp_path, "forged", "dead-one",
                     meta={"lifecycle": "deprecated", "use_count": 10})
        prompt = mgr.get_active_skills_prompt()
        assert "active-one" in prompt
        assert "dead-one" not in prompt

    def test_sorted_by_use_count(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "forged", "low-use",
                     meta={"lifecycle": "stable", "use_count": 1})
        _make_skill(tmp_path, "forged", "high-use",
                     meta={"lifecycle": "stable", "use_count": 100})
        prompt = mgr.get_active_skills_prompt()
        # high-use 在前
        assert prompt.index("high-use") < prompt.index("low-use")


# ═══════════════════════════════════════════
# TestWorkflows — Workflow 篩選與解析
# ═══════════════════════════════════════════

class TestWorkflows:
    """Scenario: discover_workflows() + get_workflow_steps()."""

    def test_discover_workflows(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "native", "regular-skill")
        _make_skill(tmp_path, "native", "workflow-invest")
        result = mgr.discover_workflows()
        assert len(result) == 1
        assert result[0]["name"] == "workflow-invest"

    def test_get_workflow_steps(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _make_skill(tmp_path, "native", "skill-a")
        workflow_content = (
            "---\nname: workflow-test\ndescription: Test WF\n---\n"
            "# Workflow Test\n\n"
            "### Stage 1: Analyze\nUse skill-a for analysis.\n\n"
            "### Stage 2: Synthesize\nCombine results.\n"
        )
        _make_skill(tmp_path, "native", "workflow-test", content=workflow_content)
        steps = mgr.get_workflow_steps("workflow-test")
        assert len(steps) == 2
        assert steps[0]["stage"] == 1
        assert steps[0]["title"] == "Analyze"
        assert "skill-a" in steps[0]["referenced_skills"]
        assert steps[1]["stage"] == 2

    def test_workflow_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        steps = mgr.get_workflow_steps("nonexistent-wf")
        assert steps == []
