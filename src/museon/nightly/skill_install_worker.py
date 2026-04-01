"""SkillInstallWorker — Skill 自動安裝引擎.

職責：
  將已核准的 Skill 草稿執行完整 9 步安裝鏈：
  1. 寫入 SKILL.md 到 ~/.claude/skills/{name}/
  2. 補齊 frontmatter（hub/type/io 驗證）
  3. 更新 plugin-registry（在表格末尾插入新條目）
  4. 更新 system-topology.md（在 changelog 區追加條目）
  5. 更新 memory-router.md（在路由表末尾加一行）
  6. CLAUDE.md 指令表 → 標記為 MANUAL（不自動執行）
  7. ~/.claude/skills/ 鏡像同步（Step 1 已完成）
  8. 跑 sync_topology_to_3d.py --apply（若腳本存在）
  9. 跑 validate_connections.py 驗證

護欄：
  - 安裝前必須確認 draft["status"] == "approved"
  - 每步 try/except 隔離，一步失敗不影響其他步驟
  - Step 4/5 只在末尾追加，絕不修改既有內容
  - Step 6 永遠標記為 MANUAL，不自動修改
  - 所有檔案寫入使用原子操作（tmp → rename）

安裝記錄：
  每次安裝結果寫入 data/_system/morphenix/install_log/install_log.jsonl
"""

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# 路徑常數
# ═══════════════════════════════════════════

SKILLS_DIR = Path.home() / ".claude" / "skills"
MUSEON_ROOT = Path.home() / "MUSEON"
DOCS_DIR = MUSEON_ROOT / "docs"
DATA_DIR = MUSEON_ROOT / "data"
REGISTRY_PATH = DATA_DIR / "skills" / "native" / "plugin-registry" / "SKILL.md"
INSTALL_LOG_PATH = DATA_DIR / "_system" / "morphenix" / "install_log" / "install_log.jsonl"
TOPOLOGY_PATH = DOCS_DIR / "system-topology.md"
MEMORY_ROUTER_PATH = DOCS_DIR / "memory-router.md"
SYNC_TOPOLOGY_SCRIPT = MUSEON_ROOT / "scripts" / "sync_topology_to_3d.py"
VALIDATE_SCRIPT = MUSEON_ROOT / "scripts" / "validate_connections.py"

# 合法的 hub 值（參照 skill-routing-governance.md）
VALID_HUBS = {
    "core", "infra", "thinking", "market",
    "business", "creative", "product", "evolution", "workflow",
}

# 合法的 type 值
VALID_TYPES = {"skill", "workflow", "reference", "system"}


# ═══════════════════════════════════════════
# 結果資料結構
# ═══════════════════════════════════════════

@dataclass
class InstallResult:
    """安裝結果資料結構."""

    success: bool
    skill_name: str
    steps_completed: List[str] = field(default_factory=list)
    steps_failed: List[str] = field(default_factory=list)
    needs_manual: List[str] = field(default_factory=list)  # 需要人類手動完成的步驟
    install_log: str = ""

    def __str__(self) -> str:
        """安全的字串表示，不洩漏內部結構."""
        status = "成功" if self.success else "失敗"
        return f"SkillInstallResult({self.skill_name}, {status})"


# ═══════════════════════════════════════════
# 主要安裝引擎
# ═══════════════════════════════════════════

class SkillInstallWorker:
    """Skill 自動安裝引擎 — 執行 9 步安裝鏈.

    設計原則：
      - 不依賴 EventBus 或 Brain，可獨立執行
      - 每步驟 try/except 隔離，部分失敗仍完成其他步驟
      - 只接受 status='approved' 的草稿
      - 所有檔案寫入使用原子操作
    """

    def __init__(self, museon_root: Optional[Path] = None) -> None:
        self._root = museon_root or MUSEON_ROOT
        self._docs = self._root / "docs"
        self._data = self._root / "data"
        self._registry = self._data / "skills" / "native" / "plugin-registry" / "SKILL.md"
        self._install_log = self._data / "_system" / "morphenix" / "install_log" / "install_log.jsonl"
        self._topology = self._docs / "system-topology.md"
        self._memory_router = self._docs / "memory-router.md"

    # ─────────────────────────────────────────
    # 公開介面
    # ─────────────────────────────────────────

    def install(self, draft: Dict[str, Any]) -> InstallResult:
        """執行完整安裝鏈.

        Args:
            draft: Morphenix 核准的 Skill 草稿 dict。
                   必須包含 status='approved', name, content, hub, type。

        Returns:
            InstallResult：完整安裝結果，含步驟清單與手動待辦事項。
        """
        skill_name = draft.get("name", "unknown")
        result = InstallResult(success=False, skill_name=skill_name)
        log_lines: List[str] = []

        # ── 前置護欄：只接受已核准的草稿 ──
        if draft.get("status") != "approved":
            msg = f"[護欄] draft status={draft.get('status')!r}，必須為 'approved' 才能安裝"
            logger.warning(msg)
            result.install_log = msg
            self._write_install_log(result)
            return result

        log_lines.append(f"開始安裝 Skill: {skill_name}，時間: {_now_str()}")

        # ── Step 1: 寫入 SKILL.md 到 ~/.claude/skills/{name}/ ──
        self._step1_write_skill_md(draft, result, log_lines)

        # ── Step 2: 補齊 frontmatter（hub/type/io 驗證）──
        self._step2_validate_frontmatter(draft, result, log_lines)

        # ── Step 3: 更新 plugin-registry ──
        self._step3_update_registry(draft, result, log_lines)

        # ── Step 4: 更新 system-topology.md（僅追加 changelog）──
        self._step4_update_topology(draft, result, log_lines)

        # ── Step 5: 更新 memory-router.md（末尾追加一行）──
        self._step5_update_memory_router(draft, result, log_lines)

        # ── Step 6: CLAUDE.md 指令表 → 標記為 MANUAL ──
        self._step6_mark_manual(draft, result, log_lines)

        # ── Step 7: ~/.claude/skills/ 鏡像（Step 1 已完成，記錄即可）──
        self._step7_confirm_mirror(draft, result, log_lines)

        # ── Step 8: 跑 sync_topology_to_3d.py --apply ──
        self._step8_sync_topology_3d(result, log_lines)

        # ── Step 9: 跑 validate_connections.py 驗證 ──
        self._step9_validate_connections(result, log_lines)

        # ── 彙整結果 ──
        result.success = len(result.steps_failed) == 0
        result.install_log = "\n".join(log_lines)

        # 寫入安裝記錄
        self._write_install_log(result)

        # ── Step 10: command_routes 由 plugin-registry 管理 ──
        if result.success:
            try:
                log_lines.append("Step 10: command_routes.json 由 plugin-registry 管理（跳過）")
            except Exception as e:
                log_lines.append(f"Step 10: command_routes rebuild failed: {e}")

        status_str = "完成（全部通過）" if result.success else f"部分失敗（{len(result.steps_failed)} 步失敗）"
        logger.info("[SkillInstallWorker] %s 安裝%s", skill_name, status_str)
        return result

    # ─────────────────────────────────────────
    # 各步驟實作
    # ─────────────────────────────────────────

    def _step1_write_skill_md(
        self, draft: Dict, result: InstallResult, log_lines: List[str]
    ) -> None:
        """Step 1: 寫入 SKILL.md 到 ~/.claude/skills/{name}/SKILL.md."""
        step = "Step1:寫入SKILL.md"
        try:
            skill_name = draft["name"]
            content = draft.get("content", "")
            target_dir = SKILLS_DIR / skill_name
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "SKILL.md"
            _atomic_write(target_file, content)
            log_lines.append(f"[{step}] 完成 → {target_file}")
            result.steps_completed.append(step)
        except Exception as exc:
            _log_step_error(step, exc, result, log_lines)

    def _step2_validate_frontmatter(
        self, draft: Dict, result: InstallResult, log_lines: List[str]
    ) -> None:
        """Step 2: 驗證並補齊 frontmatter（hub / type / io）."""
        step = "Step2:驗證frontmatter"
        try:
            warnings: List[str] = []

            hub = draft.get("hub", "")
            if hub not in VALID_HUBS:
                warnings.append(f"hub={hub!r} 不在合法值清單 {VALID_HUBS}，請確認")

            skill_type = draft.get("type", "")
            if skill_type not in VALID_TYPES:
                warnings.append(f"type={skill_type!r} 不在合法值清單 {VALID_TYPES}，請確認")

            io = draft.get("io", {})
            if not io.get("inputs") and not io.get("outputs"):
                warnings.append("io.inputs 與 io.outputs 皆為空，建議補齊")

            if warnings:
                log_lines.append(f"[{step}] 警告（不阻斷）：{'; '.join(warnings)}")
            else:
                log_lines.append(f"[{step}] 通過（hub={hub}, type={skill_type}）")

            result.steps_completed.append(step)
        except Exception as exc:
            _log_step_error(step, exc, result, log_lines)

    def _step3_update_registry(
        self, draft: Dict, result: InstallResult, log_lines: List[str]
    ) -> None:
        """Step 3: 更新 plugin-registry（在表格最後一行前插入新條目）."""
        step = "Step3:更新plugin-registry"
        try:
            if not self._registry.exists():
                log_lines.append(f"[{step}] 警告：找不到 {self._registry}，跳過")
                result.steps_completed.append(step)
                return

            content = self._registry.read_text(encoding="utf-8")
            name = draft["name"]
            hub = draft.get("hub", "—")
            description = draft.get("description", "")

            # 找到表格末尾（最後一個 | 結尾的行之後）插入新條目
            lines = content.splitlines(keepends=True)
            insert_idx = _find_table_last_row_index(lines)

            # 格式：| name | hub | description |
            new_row = f"| {name} | {hub} | {description} |\n"

            if insert_idx >= 0:
                lines.insert(insert_idx + 1, new_row)
                new_content = "".join(lines)
            else:
                # 找不到表格，追加到末尾（降級處理）
                new_content = content.rstrip() + "\n" + new_row

            _atomic_write(self._registry, new_content)
            log_lines.append(f"[{step}] 完成 → 在 plugin-registry 新增 {name}")
            result.steps_completed.append(step)
        except Exception as exc:
            _log_step_error(step, exc, result, log_lines)

    def _step4_update_topology(
        self, draft: Dict, result: InstallResult, log_lines: List[str]
    ) -> None:
        """Step 4: 更新 system-topology.md（只在 changelog 末尾追加，不修改既有內容）."""
        step = "Step4:更新system-topology"
        try:
            if not self._topology.exists():
                log_lines.append(f"[{step}] 警告：找不到 {self._topology}，跳過")
                result.steps_completed.append(step)
                return

            name = draft["name"]
            hub = draft.get("hub", "—")
            connects_to = draft.get("connects_to", [])
            connects_str = ", ".join(connects_to) if connects_to else "—"
            date_str = _now_str()[:10]  # YYYY-MM-DD

            # 只在末尾追加 changelog 條目，絕不修改既有結構
            changelog_entry = (
                f"\n<!-- skill-install: {name} | hub={hub} | connects_to={connects_str} | {date_str} -->\n"
            )

            content = self._topology.read_text(encoding="utf-8")
            new_content = content.rstrip() + "\n" + changelog_entry
            _atomic_write(self._topology, new_content)
            log_lines.append(f"[{step}] 完成 → 追加 changelog 條目（{name}）")
            result.steps_completed.append(step)
        except Exception as exc:
            _log_step_error(step, exc, result, log_lines)

    def _step5_update_memory_router(
        self, draft: Dict, result: InstallResult, log_lines: List[str]
    ) -> None:
        """Step 5: 更新 memory-router.md（在路由表末尾加一行）."""
        step = "Step5:更新memory-router"
        try:
            if not self._memory_router.exists():
                log_lines.append(f"[{step}] 警告：找不到 {self._memory_router}，跳過")
                result.steps_completed.append(step)
                return

            name = draft["name"]
            memory_target = draft.get("memory_target", "data/memory_v3/skills/")
            memory_format = draft.get("memory_format", "JSON")
            date_str = _now_str()[:10]

            # 在路由表末尾加一行（Markdown 表格格式）
            new_row = f"| {name} | {memory_target} | {memory_format} | {date_str} |\n"

            content = self._memory_router.read_text(encoding="utf-8")
            # 找最後一個表格行，在其後插入
            lines = content.splitlines(keepends=True)
            insert_idx = _find_table_last_row_index(lines)
            if insert_idx >= 0:
                lines.insert(insert_idx + 1, new_row)
                new_content = "".join(lines)
            else:
                new_content = content.rstrip() + "\n" + new_row

            _atomic_write(self._memory_router, new_content)
            log_lines.append(f"[{step}] 完成 → 追加路由條目（{name} → {memory_target}）")
            result.steps_completed.append(step)
        except Exception as exc:
            _log_step_error(step, exc, result, log_lines)

    def _step6_mark_manual(
        self, draft: Dict, result: InstallResult, log_lines: List[str]
    ) -> None:
        """Step 6: CLAUDE.md 指令表更新 → 永遠標記為 MANUAL，不自動修改."""
        step = "Step6:CLAUDE.md指令表"
        # 此步驟永遠標記為手動，不自動寫入任何檔案
        name = draft.get("name", "unknown")
        command = draft.get("command", f"/{name}")
        manual_msg = (
            f"CLAUDE.md 指令表需人工確認：在 /指令處理 表格中新增 {command} → {name}"
        )
        result.needs_manual.append(manual_msg)
        log_lines.append(f"[{step}] MANUAL → {manual_msg}")
        result.steps_completed.append(step)

    def _step7_confirm_mirror(
        self, draft: Dict, result: InstallResult, log_lines: List[str]
    ) -> None:
        """Step 7: 確認 ~/.claude/skills/ 鏡像（Step 1 已完成）."""
        step = "Step7:確認鏡像"
        try:
            skill_name = draft["name"]
            mirror_path = SKILLS_DIR / skill_name / "SKILL.md"
            if mirror_path.exists():
                log_lines.append(f"[{step}] 已確認鏡像存在 → {mirror_path}")
                result.steps_completed.append(step)
            else:
                raise FileNotFoundError(f"鏡像檔案不存在：{mirror_path}（Step 1 可能失敗）")
        except Exception as exc:
            _log_step_error(step, exc, result, log_lines)

    def _step8_sync_topology_3d(
        self, result: InstallResult, log_lines: List[str]
    ) -> None:
        """Step 8: 跑 sync_topology_to_3d.py --apply（若腳本存在）."""
        step = "Step8:sync_topology_to_3d"
        script = self._root / "scripts" / "sync_topology_to_3d.py"
        try:
            if not script.exists():
                log_lines.append(f"[{step}] 跳過（腳本不存在：{script}）")
                result.steps_completed.append(step)
                return

            proc = subprocess.run(
                ["python", str(script), "--apply"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if proc.returncode == 0:
                log_lines.append(f"[{step}] 完成（returncode=0）")
                result.steps_completed.append(step)
            else:
                raise RuntimeError(
                    f"腳本退出碼 {proc.returncode}，stderr={proc.stderr[:200]!r}"
                )
        except subprocess.TimeoutExpired:
            _log_step_error(step, TimeoutError("sync_topology_to_3d.py 超過 60s"), result, log_lines)
        except Exception as exc:
            _log_step_error(step, exc, result, log_lines)

    def _step9_validate_connections(
        self, result: InstallResult, log_lines: List[str]
    ) -> None:
        """Step 9: 跑 validate_connections.py 驗證整體連線健康度."""
        step = "Step9:validate_connections"
        script = self._root / "scripts" / "validate_connections.py"
        try:
            if not script.exists():
                log_lines.append(f"[{step}] 跳過（腳本不存在：{script}）")
                result.steps_completed.append(step)
                return

            proc = subprocess.run(
                ["python", str(script)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode == 0:
                log_lines.append(f"[{step}] 通過（returncode=0）")
                result.steps_completed.append(step)
            else:
                # 驗證警告不視為安裝失敗，但記錄警告
                warning_msg = f"驗證有警告（returncode={proc.returncode}），請人工確認"
                log_lines.append(f"[{step}] 警告：{warning_msg}")
                log_lines.append(f"  stdout={proc.stdout[:300]!r}")
                result.steps_completed.append(step)
                result.needs_manual.append(f"validate_connections.py 有警告：{warning_msg}")
        except subprocess.TimeoutExpired:
            _log_step_error(step, TimeoutError("validate_connections.py 超過 120s"), result, log_lines)
        except Exception as exc:
            _log_step_error(step, exc, result, log_lines)

    # ─────────────────────────────────────────
    # 安裝記錄
    # ─────────────────────────────────────────

    def _write_install_log(self, result: InstallResult) -> None:
        """將安裝結果寫入 install_log.jsonl（append 模式）."""
        try:
            self._install_log.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "timestamp": _now_str(),
                "skill_name": result.skill_name,
                "success": result.success,
                "steps_completed": result.steps_completed,
                "steps_failed": result.steps_failed,
                "needs_manual": result.needs_manual,
            }
            with self._install_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            # 記錄失敗不影響安裝結果
            logger.warning("[SkillInstallWorker] 寫入 install_log 失敗：%s", exc)


# ═══════════════════════════════════════════
# 工具函數
# ═══════════════════════════════════════════

def _atomic_write(path: Path, content: str) -> None:
    """原子寫入：先寫 tmp 再 rename，防止寫入中途崩潰導致檔案損壞."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # 在同一目錄建立 tmp 檔（確保同一 filesystem，rename 為原子操作）
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)  # 原子替換


def _find_table_last_row_index(lines: List[str]) -> int:
    """找到 Markdown 表格最後一個資料行的索引（排除分隔行 |---|）.

    Returns:
        最後一個資料行的索引，找不到時返回 -1。
    """
    last_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            # 排除純分隔行（只有 | - |）
            inner = stripped[1:-1]
            if all(c in "-: |" for c in inner):
                continue
            last_idx = i
    return last_idx


def _log_step_error(
    step: str, exc: Exception, result: InstallResult, log_lines: List[str]
) -> None:
    """統一記錄步驟錯誤."""
    msg = f"[{step}] 失敗：{exc}"
    logger.error("[SkillInstallWorker] %s", msg)
    log_lines.append(msg)
    result.steps_failed.append(step)


def _now_str() -> str:
    """返回當前 UTC+8 時間字串（ISO 8601）."""
    return datetime.now(TZ8).strftime("%Y-%m-%dT%H:%M:%S+08:00")
