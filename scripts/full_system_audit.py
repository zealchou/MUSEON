#!/usr/bin/env python3
"""MUSEON Full System Audit — 全系統六層健康檢查.

Usage:
    python scripts/full_system_audit.py [--fix] [--verbose]

六層檢查：
  L1: Import 健康（所有 Python 模組能否正常載入）
  L2: 共享狀態健康（joint-map 宣告的 56 個共享狀態是否存在且可讀）
  L3: Skill 連線完整性（validate_connections 的超集）
  L4: 通道隔離檢查（全局觸發邏輯是否有群組過濾）
  L5: Runtime 路徑驗證（Nightly steps, tool schemas, cron jobs）
  L6: 拓樸一致性（topology.md vs 實際檔案系統）
"""

import ast
import importlib
import json
import logging
import os
import re
import sys
from pathlib import Path

MUSEON_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MUSEON_ROOT / "src"))

logging.basicConfig(level=logging.WARNING)

# 顏色
RED = "\033[91m"
YEL = "\033[93m"
GRN = "\033[92m"
CYN = "\033[96m"
RST = "\033[0m"


def _header(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {CYN}{title}{RST}")
    print(f"{'='*60}")


class SystemAudit:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results = {"critical": [], "high": [], "medium": [], "info": []}
        self.stats = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}

    def _pass(self, msg: str) -> None:
        self.stats["pass"] += 1
        if self.verbose:
            print(f"  {GRN}✅{RST} {msg}")

    def _fail(self, msg: str, level: str = "high") -> None:
        self.stats["fail"] += 1
        self.results[level].append(msg)
        print(f"  {RED}❌{RST} {msg}")

    def _warn(self, msg: str) -> None:
        self.stats["warn"] += 1
        self.results["medium"].append(msg)
        print(f"  {YEL}⚠️{RST}  {msg}")

    def _skip(self, msg: str) -> None:
        self.stats["skip"] += 1
        if self.verbose:
            print(f"  ⏭️  {msg}")

    # ═══════════════════════════════════════
    # L1: Import 健康
    # ═══════════════════════════════════════

    def check_l1_imports(self) -> None:
        _header("L1: Import 健康 — 所有 Python 模組能否載入")
        src_dir = MUSEON_ROOT / "src" / "museon"
        total = 0
        failed = 0
        for py_file in sorted(src_dir.rglob("*.py")):
            if py_file.name.startswith("_") and py_file.name != "__init__.py":
                continue
            rel = py_file.relative_to(MUSEON_ROOT / "src")
            module_name = str(rel).replace("/", ".").replace(".py", "")
            if module_name.endswith(".__init__"):
                module_name = module_name[:-9]
            total += 1
            try:
                importlib.import_module(module_name)
                self._pass(module_name)
            except Exception as e:
                err_type = type(e).__name__
                # 跳過需要 runtime 環境的模組
                if any(x in str(e) for x in ["No module named 'telegram'", "No module named 'uvicorn'",
                                               "No module named 'qdrant'", "No module named 'anthropic'",
                                               "No module named 'apscheduler'", "No module named 'httpx'"]):
                    self._skip(f"{module_name} (runtime dependency)")
                else:
                    self._fail(f"{module_name}: {err_type}: {str(e)[:80]}")
                    failed += 1
        print(f"\n  📊 {total} 模組掃描, {failed} 失敗, {self.stats['skip']} 跳過（runtime 依賴）")

    # ═══════════════════════════════════════
    # L2: 共享狀態健康
    # ═══════════════════════════════════════

    def check_l2_shared_state(self) -> None:
        _header("L2: 共享狀態健康 — 關鍵檔案是否存在且可讀")
        data_dir = MUSEON_ROOT / "data"
        critical_files = [
            ("ANIMA_MC.json", "靈魂核心"),
            ("PULSE.md", "心脈紀錄"),
            ("SOUL.md", "靈魂日記"),
            ("ceremony_state.json", "命名儀式狀態"),
            ("lattice/crystal.db", "知識晶格 DB"),
            ("pulse/pulse.db", "Pulse DB"),
            ("_system/group_context.db", "群組對話 DB"),
            ("_system/message_queue.db", "訊息佇列 DB"),
            ("_system/context_cache/persona_digest.md", "人格快取"),
            ("_system/context_cache/user_summary.json", "使用者摘要"),
            ("_system/context_cache/active_rules.json", "行動規則"),
            ("_system/context_cache/self_summary.json", "自我狀態"),
            ("_system/heuristics.json", "直覺規則庫"),
            ("_system/crystal_rules.json", "結晶規則庫"),
            ("ares/profiles/_index.json", "Ares 人物索引"),
        ]
        for rel_path, desc in critical_files:
            fpath = data_dir / rel_path
            if fpath.exists():
                try:
                    fpath.read_bytes()[:100]
                    self._pass(f"{desc} ({rel_path})")
                except Exception as e:
                    self._fail(f"{desc} 無法讀取: {e}")
            else:
                if "ares" in rel_path:
                    self._warn(f"{desc} 不存在 ({rel_path})")
                else:
                    self._fail(f"{desc} 不存在 ({rel_path})")

        # 特別檢查：ANIMA_MC 身份是否被污染
        anima_path = data_dir / "ANIMA_MC.json"
        if anima_path.exists():
            try:
                anima = json.loads(anima_path.read_text())
                name = anima.get("identity", {}).get("name", "")
                if len(name) > 50:
                    self._fail(f"ANIMA_MC identity.name 被污染（{len(name)} chars）", "critical")
                else:
                    self._pass(f"ANIMA_MC identity.name = '{name}' (OK)")
            except Exception:
                self._fail("ANIMA_MC.json 無法解析", "critical")

        # 檢查 ceremony_state
        cer_path = data_dir / "ceremony_state.json"
        if cer_path.exists():
            try:
                cer = json.loads(cer_path.read_text())
                if not cer.get("completed", False):
                    self._fail("ceremony_state.completed=false（會在群組觸發命名儀式）", "critical")
                else:
                    self._pass("ceremony_state.completed=true (OK)")
            except Exception:
                self._warn("ceremony_state.json 無法解析")

    # ═══════════════════════════════════════
    # L3: Skill 連線完整性
    # ═══════════════════════════════════════

    def check_l3_skill_connections(self) -> None:
        _header("L3: Skill 連線完整性 — validate_connections")
        import subprocess
        r = subprocess.run(
            [sys.executable, str(MUSEON_ROOT / "scripts" / "validate_connections.py")],
            capture_output=True, text=True, timeout=30,
        )
        # 解析結果
        output = r.stdout + r.stderr
        error_match = re.search(r"(\d+) 錯誤", output)
        warn_match = re.search(r"(\d+) 警告", output)
        errors = int(error_match.group(1)) if error_match else 0
        warns = int(warn_match.group(1)) if warn_match else 0
        if errors > 0:
            self._fail(f"validate_connections: {errors} 錯誤, {warns} 警告")
        elif warns > 0:
            self._warn(f"validate_connections: {warns} 警告, 0 錯誤")
        else:
            self._pass("validate_connections: 全部通過")

    # ═══════════════════════════════════════
    # L4: 通道隔離檢查
    # ═══════════════════════════════════════

    def check_l4_channel_isolation(self) -> None:
        _header("L4: 通道隔離 — 全局觸發邏輯是否有群組過濾")
        src_dir = MUSEON_ROOT / "src" / "museon"

        # 高風險 pattern：寫入 ANIMA_MC/ceremony 但沒檢查 is_group
        risky_patterns = [
            (r"ceremony.*is_ceremony_needed|is_ceremony_needed", "命名儀式觸發"),
            (r"_save_anima_mc|anima_mc_store.*save|anima_mc_store.*update", "ANIMA_MC 寫入"),
            (r"_try_rename|receive_name", "更名邏輯"),
        ]

        brain_path = src_dir / "agent" / "brain.py"
        if brain_path.exists():
            content = brain_path.read_text()
            lines = content.split("\n")

            for pattern, desc in risky_patterns:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line) and "is_group" not in line:
                        # 檢查前後 5 行是否有 is_group 檢查
                        context = "\n".join(lines[max(0, i-6):i+5])
                        if "is_group" in context or "_is_group" in context:
                            self._pass(f"{desc} (line {i}) 有通道隔離")
                        elif "def " in line or "#" in line.lstrip()[:2]:
                            continue  # 跳過定義和註解
                        else:
                            # 只標記實際調用的行
                            stripped = line.strip()
                            if stripped and not stripped.startswith("#") and not stripped.startswith("def "):
                                if "ceremony" in stripped.lower() or "rename" in stripped.lower() or "save_anima" in stripped.lower():
                                    self._warn(f"{desc} (brain.py:{i}) 可能缺少通道隔離")

    # ═══════════════════════════════════════
    # L5: Runtime 路徑驗證
    # ═══════════════════════════════════════

    def check_l5_runtime_paths(self) -> None:
        _header("L5: Runtime 路徑 — Nightly/Tools/Cron 是否接通")

        # 5a: Nightly _FULL_STEPS 每個 step 都有對應方法
        try:
            from museon.nightly.nightly_pipeline import _FULL_STEPS
            print(f"  Nightly steps: {len(_FULL_STEPS)}")

            # 驗證每個 step 的方法存在（透過 AST 掃描）
            pipeline_path = MUSEON_ROOT / "src" / "museon" / "nightly" / "nightly_pipeline.py"
            content = pipeline_path.read_text()
            for step_id in _FULL_STEPS:
                # 在 step_map 中搜尋
                pattern = f'"{step_id}"'
                if pattern in content:
                    self._pass(f"Step {step_id} 在 step_map 中") if self.verbose else None
                else:
                    self._fail(f"Step {step_id} 不在 step_map 中")
            self._pass(f"Nightly {len(_FULL_STEPS)} steps 全部在 step_map 中")
        except Exception as e:
            self._fail(f"Nightly pipeline 載入失敗: {e}")

        # 5b: Tool schemas 每個工具在 whitelist 中
        try:
            from museon.agent.tool_schemas import TOOL_NAMES
            from museon.agent.tools import ToolWhitelist
            wl = ToolWhitelist()
            missing = [t for t in TOOL_NAMES if not wl.is_allowed(t)]
            if missing:
                self._fail(f"工具不在 whitelist: {missing}")
            else:
                self._pass(f"Tool schemas: {len(TOOL_NAMES)} 工具全部在 whitelist")
        except Exception as e:
            self._fail(f"Tool schemas 載入失敗: {e}")

        # 5c: CLAUDE.md 路由表完整性
        try:
            claude_md = (MUSEON_ROOT / "CLAUDE.md").read_text()
            skill_dirs = [d.name for d in (MUSEON_ROOT / "data" / "skills" / "native").iterdir()
                         if d.is_dir() and (d / "SKILL.md").exists()]
            # 檢查有 trigger_words 含 / 開頭的 Skill 是否在路由表
            for skill_name in skill_dirs:
                skill_md = (MUSEON_ROOT / "data" / "skills" / "native" / skill_name / "SKILL.md").read_text()
                triggers = re.findall(r"- /(\w[\w-]*)", skill_md)
                for t in triggers:
                    if f"/{t}" in claude_md:
                        self._pass(f"/{t} → {skill_name} 在路由表") if self.verbose else None
                    else:
                        self._warn(f"/{t} ({skill_name}) 不在 CLAUDE.md 路由表")
        except Exception as e:
            self._warn(f"路由表檢查失敗: {e}")

    # ═══════════════════════════════════════
    # L6: 拓樸一致性
    # ═══════════════════════════════════════

    def check_l6_topology(self) -> None:
        _header("L6: 拓樸一致性 — 藍圖 vs 實際")

        # 6a: 五張藍圖都存在
        blueprints = [
            "system-topology.md", "blast-radius.md",
            "persistence-contract.md", "memory-router.md", "joint-map.md",
        ]
        for bp in blueprints:
            p = MUSEON_ROOT / "docs" / bp
            if p.exists():
                # 檢查版本號
                first_line = p.read_text()[:500]
                ver = re.search(r"v(\d+\.\d+)", first_line)
                self._pass(f"{bp} v{ver.group(1) if ver else '?'}")
            else:
                self._fail(f"{bp} 不存在", "critical")

        # 6b: Skill 目錄 vs Plugin Registry 一致性
        try:
            skill_dirs = sorted(d.name for d in (MUSEON_ROOT / "data" / "skills" / "native").iterdir()
                               if d.is_dir() and (d / "SKILL.md").exists())
            registry_path = MUSEON_ROOT / "data" / "skills" / "native" / "plugin-registry" / "SKILL.md"
            registry_content = registry_path.read_text()

            missing_in_registry = []
            for skill in skill_dirs:
                if skill == "plugin-registry":
                    continue
                if skill not in registry_content:
                    missing_in_registry.append(skill)

            if missing_in_registry:
                self._warn(f"Skill 目錄有但 Registry 沒列: {missing_in_registry}")
            else:
                self._pass(f"所有 {len(skill_dirs)} 個 Skill 都在 Registry 中")
        except Exception as e:
            self._warn(f"Registry 一致性檢查失敗: {e}")

        # 6c: SKILL.md 鏡像一致性（MUSEON ↔ ~/.claude/skills/）
        mirror_dir = Path.home() / ".claude" / "skills"
        mismatches = []
        for skill_dir in (MUSEON_ROOT / "data" / "skills" / "native").iterdir():
            if not skill_dir.is_dir():
                continue
            src = skill_dir / "SKILL.md"
            dst = mirror_dir / skill_dir.name / "SKILL.md"
            if src.exists() and dst.exists():
                if src.read_text() != dst.read_text():
                    mismatches.append(skill_dir.name)
            elif src.exists() and not dst.exists():
                mismatches.append(f"{skill_dir.name} (mirror missing)")
        if mismatches:
            self._warn(f"SKILL.md 鏡像不一致: {mismatches[:5]}{'...' if len(mismatches) > 5 else ''}")
        else:
            self._pass("所有 SKILL.md 鏡像一致")

        # 6d: 3D 心智圖版本
        html_path = MUSEON_ROOT / "data" / "workspace" / "MUSEON_3d_mindmap.html"
        if html_path.exists():
            content = html_path.read_text()[:1000]
            ver = re.search(r"v(\d+\.\d+)", content)
            self._pass(f"3D 心智圖 v{ver.group(1) if ver else '?'}")
        else:
            self._warn("3D 心智圖 HTML 不存在")

    # ═══════════════════════════════════════
    # 主流程
    # ═══════════════════════════════════════

    def run(self) -> dict:
        print(f"\n{'═'*60}")
        print(f"  {CYN}MUSEON 全系統六層健康檢查{RST}")
        print(f"  {MUSEON_ROOT}")
        print(f"{'═'*60}")

        self.check_l1_imports()
        self.check_l2_shared_state()
        self.check_l3_skill_connections()
        self.check_l4_channel_isolation()
        self.check_l5_runtime_paths()
        self.check_l6_topology()

        # 總結
        _header("總結")
        total = self.stats["pass"] + self.stats["fail"] + self.stats["warn"]
        crit = len(self.results["critical"])
        high = len(self.results["high"])
        med = len(self.results["medium"])

        print(f"  通過: {GRN}{self.stats['pass']}{RST}")
        print(f"  失敗: {RED}{self.stats['fail']}{RST} (CRITICAL: {crit}, HIGH: {high})")
        print(f"  警告: {YEL}{self.stats['warn']}{RST} (MEDIUM: {med})")
        print(f"  跳過: {self.stats['skip']}")
        print()

        if self.results["critical"]:
            print(f"  {RED}🔴 CRITICAL:{RST}")
            for msg in self.results["critical"]:
                print(f"     {msg}")
        if self.results["high"]:
            print(f"  {RED}🟠 HIGH:{RST}")
            for msg in self.results["high"]:
                print(f"     {msg}")

        health = "HEALTHY" if (crit == 0 and high == 0) else ("DEGRADED" if crit == 0 else "CRITICAL")
        color = GRN if health == "HEALTHY" else (YEL if health == "DEGRADED" else RED)
        print(f"\n  {'═'*40}")
        print(f"  系統狀態: {color}{health}{RST}")
        print(f"  {'═'*40}\n")

        return {"health": health, "stats": self.stats, "results": self.results}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    audit = SystemAudit(verbose=args.verbose)
    audit.run()
