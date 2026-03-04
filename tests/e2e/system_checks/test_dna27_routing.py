"""
DNA27 三迴圈路由 + 系統健康檢測
驗證 DNA27 核心的三迴圈路由、WEE、Morphenix、Eval 等是否實作
"""
import pytest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]  # museon/


class TestDNA27SystemHealth:
    """DNA27 生態系健康檢測（D4 維度）"""

    def test_three_loop_routing_exists(self, collector):
        """三迴圈路由（fast/exploration/slow）是否有實作"""
        targets = ["fast_loop", "exploration_loop", "slow_loop"]
        found = []
        for t in targets:
            hits = list(PROJECT.rglob("*.py"))
            for f in hits:
                if ".venv" in str(f):
                    continue
                try:
                    if t in f.read_text(encoding="utf-8"):
                        found.append(t)
                        break
                except Exception:
                    continue
        if len(found) == 3:
            collector.record("three_loop_routing", "D4.dna27", "PASS",
                             "三迴圈路由完整: fast/exploration/slow")
        elif found:
            collector.record("three_loop_routing", "D4.dna27", "WARN",
                             f"只找到 {found}，缺少 {set(targets)-set(found)}",
                             severity="MEDIUM")
        else:
            collector.record("three_loop_routing", "D4.dna27", "FAIL",
                             "找不到三迴圈路由", severity="CRITICAL")
            pytest.fail("三迴圈路由不存在")

    def test_dna27_skill_exists(self, collector):
        """dna27 核心 Skill 是否存在"""
        skill_dir = PROJECT / "data" / "skills" / "dna27"
        exists = skill_dir.exists() and (skill_dir / "SKILL.md").exists()
        if exists:
            collector.record("dna27_skill", "D4.dna27", "PASS", "dna27 核心 Skill 存在")
        else:
            # 也許放在其他位置
            alt = list(PROJECT.rglob("dna27/SKILL.md"))
            alt = [a for a in alt if ".venv" not in str(a)]
            if alt:
                collector.record("dna27_skill", "D4.dna27", "PASS",
                                 f"dna27 Skill 在 {alt[0]}")
            else:
                collector.record("dna27_skill", "D4.dna27", "FAIL",
                                 "dna27 核心 Skill 不存在", severity="CRITICAL")

    def test_wee_tracking_exists(self, collector):
        """WEE 工作流追蹤是否實作"""
        wee_dir = PROJECT / "data" / "skills" / "wee"
        exists = wee_dir.exists()
        if exists:
            collector.record("wee_tracking", "D4.wee", "PASS", "WEE Skill 存在")
        else:
            alt = list(PROJECT.rglob("wee/SKILL.md"))
            alt = [a for a in alt if ".venv" not in str(a)]
            if alt:
                collector.record("wee_tracking", "D4.wee", "PASS",
                                 f"WEE Skill 在 {alt[0]}")
            else:
                collector.record("wee_tracking", "D4.wee", "WARN",
                                 "WEE Skill 不存在", severity="MEDIUM")

    def test_morphenix_exists(self, collector):
        """Morphenix 自我進化引擎是否實作"""
        mp_dir = PROJECT / "data" / "skills" / "morphenix"
        exists = mp_dir.exists()
        if exists:
            collector.record("morphenix", "D4.morphenix", "PASS", "Morphenix Skill 存在")
        else:
            alt = list(PROJECT.rglob("morphenix/SKILL.md"))
            alt = [a for a in alt if ".venv" not in str(a)]
            if alt:
                collector.record("morphenix", "D4.morphenix", "PASS",
                                 f"Morphenix 在 {alt[0]}")
            else:
                collector.record("morphenix", "D4.morphenix", "WARN",
                                 "Morphenix Skill 不存在", severity="MEDIUM")

    def test_eval_engine_exists(self, collector):
        """Eval-Engine 是否實作"""
        ee_files = list((PROJECT / "src").rglob("eval_engine.py"))
        if ee_files:
            collector.record("eval_engine", "D4.eval", "PASS",
                             f"Eval-Engine 在 {ee_files[0].relative_to(PROJECT)}")
        else:
            collector.record("eval_engine", "D4.eval", "WARN",
                             "Eval-Engine 實作不存在", severity="MEDIUM")

    def test_orchestrator_exists(self, collector):
        """Orchestrator 編排引擎是否實作"""
        orc = list(PROJECT.rglob("orchestrator/SKILL.md"))
        orc = [a for a in orc if ".venv" not in str(a)]
        if orc:
            collector.record("orchestrator", "D4.orchestrator", "PASS",
                             "Orchestrator Skill 存在")
        else:
            collector.record("orchestrator", "D4.orchestrator", "WARN",
                             "Orchestrator Skill 不存在", severity="MEDIUM")

    def test_skill_router_loaded(self, collector, gateway):
        """Skill Router 是否載入了足夠的 Skills"""
        count = gateway.get("skills_indexed", 0)
        if count >= 20:
            collector.record("skill_router", "D4.dna27", "PASS",
                             f"已載入 {count} 個 Skills")
        elif count >= 5:
            collector.record("skill_router", "D4.dna27", "WARN",
                             f"只載入 {count} 個 Skills（預期 20+）",
                             severity="MEDIUM")
        else:
            collector.record("skill_router", "D4.dna27", "FAIL",
                             f"只載入 {count} 個 Skills", severity="HIGH")

    def test_brain_is_alive(self, collector, gateway):
        """Brain 引擎是否存活"""
        brain = gateway.get("brain")
        if brain == "alive":
            collector.record("brain_alive", "D4.dna27", "PASS", "Brain 引擎存活")
        else:
            collector.record("brain_alive", "D4.dna27", "FAIL",
                             f"Brain 狀態: {brain}", severity="CRITICAL")
            pytest.fail("Brain 不存活")

    def test_stress_crucible_skill_installed(self, collector):
        """stress-crucible Skill 是否已安裝"""
        sc_dir = PROJECT / "data" / "skills" / "stress-crucible"
        if sc_dir.exists() and (sc_dir / "SKILL.md").exists():
            collector.record("stress_crucible_installed", "D4.dna27", "PASS",
                             "stress-crucible Skill 已安裝")
        else:
            collector.record("stress_crucible_installed", "D4.dna27", "FAIL",
                             "stress-crucible Skill 未安裝", severity="HIGH")
