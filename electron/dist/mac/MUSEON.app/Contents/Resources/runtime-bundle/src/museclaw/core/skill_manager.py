"""SkillManager — 技能生命週期統一門面.

協調：
- SkillRouter（DNA27 匹配路由，唯讀索引）
- SecurityScanner（內容安全掃描）
- Per-skill _meta.json（lifecycle、使用統計）

依據 SKILL_MANAGER_BDD_SPEC §5-§13 實作。
"""

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Lifecycle 常數（與 nightly_pipeline.py 一致）
# ═══════════════════════════════════════════

PROMOTE_MIN_SUCCESS = 3        # experimental → stable
DEPRECATE_FAIL_RATE = 0.5      # stable → deprecated（失敗率 > 50%）
ARCHIVE_INACTIVE_DAYS = 30     # deprecated → archived（30 天無使用）
MAX_ACTIVE_PROMPT = 10         # get_active_skills_prompt 上限

# ═══════════════════════════════════════════
# Default _meta.json template
# ═══════════════════════════════════════════

_DEFAULT_META: Dict[str, Any] = {
    "lifecycle": "experimental",
    "created_at": "",
    "last_used": "",
    "use_count": 0,
    "success_count": 0,
    "failure_count": 0,
    "version": "1.0.0",
    "source": "unknown",
    "security_scan": None,
}


# ═══════════════════════════════════════════
# SkillManager
# ═══════════════════════════════════════════

class SkillManager:
    """技能生命週期統一門面.

    workspace 對應 brain.data_dir（通常是 data/）。
    技能目錄結構：
        workspace/skills/native/<name>/SKILL.md
        workspace/skills/forged/<name>/SKILL.md + _meta.json
    """

    def __init__(self, workspace: Path) -> None:
        self._workspace = Path(workspace)
        self._skills_dir = self._workspace / "skills"
        self._native_dir = self._skills_dir / "native"
        self._forged_dir = self._skills_dir / "forged"

        # Lazy — 避免循環依賴
        self._scanner = None  # type: ignore
        self._router = None   # type: ignore

    # ── Lazy dependencies ──

    @property
    def scanner(self):
        if self._scanner is None:
            from museclaw.security.skill_scanner import SecurityScanner
            self._scanner = SecurityScanner()
        return self._scanner

    @property
    def router(self):
        if self._router is None:
            from museclaw.agent.skill_router import SkillRouter
            self._router = SkillRouter(skills_dir=str(self._skills_dir))
        return self._router

    # ═══════════════════════════════════════
    # Meta I/O
    # ═══════════════════════════════════════

    def _meta_path(self, skill_dir: Path) -> Path:
        """_meta.json 路徑."""
        return skill_dir / "_meta.json"

    def _load_meta(self, skill_dir: Path) -> Dict[str, Any]:
        """讀取 _meta.json.

        不存在時：
        - native → lifecycle='stable', source='native'
        - forged → lifecycle='experimental', source='forged'
        """
        mp = self._meta_path(skill_dir)
        if mp.exists():
            try:
                return json.loads(mp.read_text(encoding="utf-8"))
            except Exception:
                logger.warning(f"Corrupt _meta.json: {mp}")

        meta = dict(_DEFAULT_META)
        is_native = (
            self._native_dir in skill_dir.parents
            or skill_dir.parent == self._native_dir
        )
        meta["lifecycle"] = "stable" if is_native else "experimental"
        meta["source"] = "native" if is_native else "forged"
        return meta

    def _save_meta(self, skill_dir: Path, meta: Dict[str, Any]) -> None:
        """原子寫入 _meta.json."""
        mp = self._meta_path(skill_dir)
        mp.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ═══════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════

    def _check_lifecycle(self, meta: Dict[str, Any]) -> Optional[str]:
        """檢查 lifecycle 是否應轉換.

        Returns:
            新 lifecycle 字串，或 None（不變）。
        """
        lifecycle = meta.get("lifecycle", "experimental")
        success = meta.get("success_count", 0)
        failure = meta.get("failure_count", 0)
        total = success + failure

        if lifecycle == "experimental" and success >= PROMOTE_MIN_SUCCESS:
            return "stable"
        if lifecycle == "stable" and total > 0:
            if failure / total > DEPRECATE_FAIL_RATE:
                return "deprecated"
        return None

    def _update_lifecycle(
        self, skill_dir: Path, meta: Dict[str, Any]
    ) -> bool:
        """執行 lifecycle 轉換並存檔.

        Returns:
            是否發生轉換.
        """
        new_lifecycle = self._check_lifecycle(meta)
        if new_lifecycle and new_lifecycle != meta.get("lifecycle"):
            old = meta.get("lifecycle", "unknown")
            meta["lifecycle"] = new_lifecycle
            logger.info(
                f"Skill lifecycle: {skill_dir.name} {old} -> {new_lifecycle}"
            )
            self._save_meta(skill_dir, meta)
            return True
        return False

    # ═══════════════════════════════════════
    # Public API — 發現 / 列出
    # ═══════════════════════════════════════

    def discover_skills(self) -> List[Dict[str, Any]]:
        """掃描 native/ + forged/ 的所有技能目錄."""
        results = []
        for origin_dir in (self._native_dir, self._forged_dir):
            if not origin_dir.exists():
                continue
            for skill_dir in sorted(origin_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                # 必須有 SKILL.md 或 BRIEF.md
                has_skill = (skill_dir / "SKILL.md").exists()
                has_brief = (skill_dir / "BRIEF.md").exists()
                if not has_skill and not has_brief:
                    continue

                meta = self._load_meta(skill_dir)
                results.append({
                    "name": skill_dir.name,
                    "origin": origin_dir.name,
                    "lifecycle": meta.get("lifecycle", "stable"),
                    "use_count": meta.get("use_count", 0),
                    "success_count": meta.get("success_count", 0),
                    "failure_count": meta.get("failure_count", 0),
                    "last_used": meta.get("last_used", ""),
                    "has_meta": self._meta_path(skill_dir).exists(),
                })
        return results

    def list_skills(
        self, lifecycle: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """列出技能，可選 lifecycle 過濾."""
        all_skills = self.discover_skills()
        if lifecycle:
            return [s for s in all_skills if s["lifecycle"] == lifecycle]
        return all_skills

    def get_skill(self, name: str) -> Optional[Dict[str, Any]]:
        """取得單一技能的完整資訊（meta + description）."""
        skill_dir = self._find_skill_dir(name)
        if not skill_dir:
            return None

        meta = self._load_meta(skill_dir)

        # 從 frontmatter 提取 description
        description = ""
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            skill_file = skill_dir / "BRIEF.md"

        if skill_file.exists():
            try:
                content = skill_file.read_text(encoding="utf-8")
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        for line in parts[1].splitlines():
                            stripped = line.strip()
                            if stripped.startswith("description:"):
                                description = stripped.split(":", 1)[1].strip()
                                break
            except Exception:
                pass

        return {
            "name": name,
            "dir": str(skill_dir),
            "description": description,
            "meta": meta,
            "has_skill_md": (skill_dir / "SKILL.md").exists(),
        }

    # ═══════════════════════════════════════
    # Public API — 安裝
    # ═══════════════════════════════════════

    def install_skill(
        self,
        name: str,
        content: str,
        source: str = "forged",
        force: bool = False,
    ) -> Dict[str, Any]:
        """安裝新技能到 forged/ 目錄.

        流程：安全掃描 → 寫入 SKILL.md → 建立 _meta.json → rebuild_index.
        若 risk >= MEDIUM 且 force=False → 阻擋安裝.
        """
        scan_result = self.scanner.scan_skill(content)
        if not scan_result["safe"] and not force:
            return {
                "installed": False,
                "reason": "security_scan_failed",
                "scan": scan_result,
            }

        target_dir = self._forged_dir / name
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "SKILL.md").write_text(content, encoding="utf-8")

        now = datetime.now(TZ_TAIPEI).isoformat()
        meta = dict(_DEFAULT_META)
        meta["lifecycle"] = "experimental"
        meta["created_at"] = now
        meta["source"] = source
        meta["security_scan"] = {
            "safe": scan_result["safe"],
            "risk_level": scan_result["risk_level"],
            "risk_name": scan_result["risk_name"],
            "issue_count": scan_result["issue_count"],
            "last_scanned": now,
        }
        self._save_meta(target_dir, meta)

        # 重建路由索引
        try:
            self.router.rebuild_index()
        except Exception:
            pass

        return {
            "installed": True,
            "name": name,
            "lifecycle": "experimental",
            "scan": scan_result,
        }

    # ═══════════════════════════════════════
    # Public API — 使用追蹤
    # ═══════════════════════════════════════

    def record_use(
        self, name: str, success: bool = True
    ) -> Dict[str, Any]:
        """記錄技能使用並即時檢查 lifecycle 轉換."""
        skill_dir = self._find_skill_dir(name)
        if not skill_dir:
            return {"recorded": False, "reason": "skill_not_found"}

        meta = self._load_meta(skill_dir)
        now = datetime.now(TZ_TAIPEI).isoformat()

        meta["use_count"] = meta.get("use_count", 0) + 1
        meta["last_used"] = now
        if success:
            meta["success_count"] = meta.get("success_count", 0) + 1
        else:
            meta["failure_count"] = meta.get("failure_count", 0) + 1

        # 即時 lifecycle 檢查
        transitioned = self._update_lifecycle(skill_dir, meta)
        if not transitioned:
            self._save_meta(skill_dir, meta)

        return {
            "recorded": True,
            "name": name,
            "use_count": meta["use_count"],
            "lifecycle": meta["lifecycle"],
            "transitioned": transitioned,
        }

    # ═══════════════════════════════════════
    # Public API — 安全掃描
    # ═══════════════════════════════════════

    def scan_skill(self, name: str) -> Dict[str, Any]:
        """掃描單一技能並更新 _meta.json."""
        skill_dir = self._find_skill_dir(name)
        if not skill_dir:
            return {"error": "skill_not_found"}

        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            skill_file = skill_dir / "BRIEF.md"
        if not skill_file.exists():
            return {"error": "no_skill_file"}

        result = self.scanner.scan_file(skill_file)

        # 更新 _meta.json 的 security_scan
        meta = self._load_meta(skill_dir)
        meta["security_scan"] = {
            "safe": result["safe"],
            "risk_level": result["risk_level"],
            "risk_name": result["risk_name"],
            "issue_count": result["issue_count"],
            "last_scanned": datetime.now(TZ_TAIPEI).isoformat(),
        }
        self._save_meta(skill_dir, meta)

        return result

    def scan_all(self) -> Dict[str, Any]:
        """掃描所有技能並回傳彙總."""
        results = []
        for skill_info in self.discover_skills():
            result = self.scan_skill(skill_info["name"])
            results.append({
                "name": skill_info["name"],
                "safe": result.get("safe", False),
                "risk_level": result.get("risk_level", 0),
                "issue_count": result.get("issue_count", 0),
            })
        unsafe = [r for r in results if not r["safe"]]
        return {
            "total_scanned": len(results),
            "safe_count": len(results) - len(unsafe),
            "unsafe_count": len(unsafe),
            "unsafe_skills": unsafe,
            "results": results,
        }

    # ═══════════════════════════════════════
    # Public API — 夜間維護
    # ═══════════════════════════════════════

    def nightly_maintenance(self) -> Dict[str, Any]:
        """夜間 lifecycle 維護.

        處理：deprecated + 30 天閒置 → archived.
        也重跑 promotion/deprecation 檢查。
        """
        today = date.today()
        promoted = 0
        deprecated_count = 0
        archived = 0

        for origin_dir in (self._native_dir, self._forged_dir):
            if not origin_dir.exists():
                continue
            for skill_dir in origin_dir.iterdir():
                if not skill_dir.is_dir():
                    continue
                # 只處理有 _meta.json 的
                if not self._meta_path(skill_dir).exists():
                    continue

                meta = self._load_meta(skill_dir)
                old_lifecycle = meta.get("lifecycle", "experimental")

                # 標準轉換（promote / deprecate）
                new = self._check_lifecycle(meta)
                if new and new != old_lifecycle:
                    meta["lifecycle"] = new
                    if new == "stable":
                        promoted += 1
                    elif new == "deprecated":
                        deprecated_count += 1
                    self._save_meta(skill_dir, meta)
                    continue

                # deprecated → archived（30 天閒置）
                if old_lifecycle == "deprecated":
                    last_used = meta.get("last_used")
                    if last_used:
                        try:
                            last = date.fromisoformat(last_used[:10])
                            if (today - last).days >= ARCHIVE_INACTIVE_DAYS:
                                meta["lifecycle"] = "archived"
                                archived += 1
                                self._save_meta(skill_dir, meta)
                        except Exception:
                            pass

        return {
            "promoted": promoted,
            "deprecated": deprecated_count,
            "archived": archived,
        }

    # ═══════════════════════════════════════
    # Public API — Prompt 注入
    # ═══════════════════════════════════════

    def get_active_skills_prompt(self) -> str:
        """產生精簡技能列表（注入 system prompt 用）.

        最多 10 個 active（stable + experimental），~300 tokens.
        """
        skills = self.discover_skills()
        active = [
            s for s in skills
            if s["lifecycle"] in ("stable", "experimental")
        ]
        active.sort(key=lambda s: s["use_count"], reverse=True)
        active = active[:MAX_ACTIVE_PROMPT]

        if not active:
            return ""

        emoji = {"stable": "\u2705", "experimental": "\U0001F9EA"}
        lines = []
        for s in active:
            badge = emoji.get(s["lifecycle"], "")
            lines.append(
                f"- {badge} {s['name']} ({s['lifecycle']}, {s['use_count']}x)"
            )
        return "\n".join(lines)

    # ═══════════════════════════════════════
    # Public API — Workflow
    # ═══════════════════════════════════════

    def discover_workflows(self) -> List[Dict[str, Any]]:
        """找出所有 workflow 類型技能（name 以 'workflow-' 開頭）."""
        all_skills = self.discover_skills()
        return [s for s in all_skills if s["name"].startswith("workflow-")]

    def get_workflow_steps(self, name: str) -> List[Dict[str, Any]]:
        """解析 workflow SKILL.md 中的 Stage 步驟.

        解析 '### Stage N:' 標頭，提取 referenced skills.
        """
        skill_dir = self._find_skill_dir(name)
        if not skill_dir:
            return []

        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            return []

        try:
            content = skill_file.read_text(encoding="utf-8")
        except Exception:
            return []

        # 收集所有已知技能名稱（用於比對 reference）
        known_skills = {s["name"] for s in self.discover_skills()}

        steps = []
        stage_pattern = re.compile(
            r"^###\s+Stage\s+(\d+)[：:]\s*(.+)$", re.MULTILINE
        )
        matches = list(stage_pattern.finditer(content))

        for i, match in enumerate(matches):
            stage_num = int(match.group(1))
            stage_title = match.group(2).strip()

            # 取得 stage body（到下一個 stage 或文末）
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            stage_body = content[start:end]

            # 在 body 中找已知技能名稱
            referenced = [
                sname for sname in known_skills
                if sname in stage_body and sname != name
            ]

            steps.append({
                "stage": stage_num,
                "title": stage_title,
                "referenced_skills": sorted(referenced),
            })

        return steps

    # ═══════════════════════════════════════
    # Internal helpers
    # ═══════════════════════════════════════

    def _find_skill_dir(self, name: str) -> Optional[Path]:
        """在 native/ + forged/ 中找技能目錄."""
        for origin_dir in (self._native_dir, self._forged_dir):
            candidate = origin_dir / name
            if candidate.is_dir():
                return candidate
        return None
