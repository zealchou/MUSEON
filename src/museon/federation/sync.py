"""FederationSync — 母子體 Git 同步引擎.

透過 GitHub Private Repo + Collaborator 模式實現：
- 子體每日推送匿名化經驗到 GitHub
- 母體收集所有子體經驗，加速演化
- 母體推送演化成果回 origin/，子體拉取更新

Repo 結構:
    museon-federation/
    ├── origin/              ← 母體推送
    │   ├── skills/
    │   ├── workflows/
    │   ├── crystals/
    │   └── evolution_manifest.json
    └── children/
        └── {node_id}/      ← 各子體推送
            ├── crystals/
            ├── skill_stats/
            └── sync_manifest.json
"""

import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FederationSync:
    """母子體 Git 同步引擎."""

    def __init__(self, data_dir: str, node_id: Optional[str] = None):
        """
        Args:
            data_dir: MUSEON data 目錄路徑
            node_id: 節點 ID（從環境變數 MUSEON_NODE_ID 讀取，或自動生成）
        """
        self._data_dir = Path(data_dir)
        self._node_id = node_id or os.getenv("MUSEON_NODE_ID", self._generate_node_id())
        self._mode = os.getenv("MUSEON_FEDERATION_MODE", "origin")  # "origin" | "node"
        self._repo_url = os.getenv("MUSEON_FEDERATION_REPO", "")

        # Federation 本地目錄
        self._fed_dir = self._data_dir / "_system" / "federation"
        self._fed_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _generate_node_id() -> str:
        """自動生成節點 ID."""
        import platform
        import uuid
        hostname = platform.node().lower().replace(" ", "-")[:20]
        short_uuid = uuid.uuid4().hex[:6]
        return f"node-{hostname}-{short_uuid}"

    # ── Git Helpers ──

    def _git(self, *args, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        """執行 git 命令."""
        cmd = ["git"] + list(args)
        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd or self._fed_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result
        except subprocess.TimeoutExpired:
            logger.error(f"Git command timed out: {cmd}")
            raise
        except FileNotFoundError:
            logger.error("Git not found in PATH")
            raise

    def _is_git_repo(self) -> bool:
        """檢查 federation 目錄是否為 git repo."""
        return (self._fed_dir / ".git").exists()

    def _ensure_repo(self) -> bool:
        """確保 git repo 存在.

        Returns:
            True if repo is ready, False otherwise.
        """
        if self._is_git_repo():
            return True

        if not self._repo_url:
            logger.warning("No MUSEON_FEDERATION_REPO configured")
            return False

        # Clone repo
        try:
            result = self._git("clone", self._repo_url, str(self._fed_dir))
            if result.returncode != 0:
                logger.error(f"Git clone failed: {result.stderr}")
                return False
            return True
        except Exception as e:
            logger.error(f"Git clone error: {e}")
            return False

    # ── Anonymization ──

    @staticmethod
    def _anonymize_text(text: str) -> str:
        """移除個人資訊."""
        # 移除常見的個人識別資訊模式
        text = re.sub(r'"user_id"\s*:\s*"[^"]*"', '"user_id": "[REDACTED]"', text)
        text = re.sub(r'"session_id"\s*:\s*"[^"]*"', '"session_id": "[REDACTED]"', text)
        text = re.sub(r'"conversation_id"\s*:\s*"[^"]*"', '"conversation_id": "[REDACTED]"', text)
        # 移除 email 格式
        text = re.sub(r'[\w.+-]+@[\w-]+\.[\w.-]+', '[EMAIL]', text)
        return text

    @staticmethod
    def _anonymize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
        """遞迴匿名化 dict 中的個人資訊."""
        anonymize_keys = {"user_id", "session_id", "conversation_id", "user_name"}
        result = {}
        for k, v in data.items():
            if k in anonymize_keys:
                result[k] = "[REDACTED]"
            elif isinstance(v, dict):
                result[k] = FederationSync._anonymize_dict(v)
            elif isinstance(v, str):
                result[k] = FederationSync._anonymize_text(v)
            else:
                result[k] = v
        return result

    # ── Sync Package (子體 → GitHub) ──

    def build_sync_package(self) -> Dict[str, Any]:
        """建構子體同步包（匿名化後的經驗資料）.

        包含：
        - L2/L3 知識結晶（匿名化）
        - Skill 使用統計
        - Workflow 執行記錄
        """
        package = {
            "node_id": self._node_id,
            "timestamp": datetime.now().isoformat(),
            "crystals": [],
            "skill_stats": {},
            "workflow_records": [],
        }

        # 1. 知識結晶 (L2_sem + L3_procedural)
        for level_dir_name in ("L2_sem", "L3_procedural"):
            level_dir = self._data_dir / "memory" / level_dir_name
            if not level_dir.exists():
                # 嘗試 memory_v3
                level_dir = self._data_dir / "memory_v3" / level_dir_name
            if level_dir.exists():
                for f in level_dir.glob("*.json"):
                    try:
                        raw = json.loads(f.read_text(encoding="utf-8"))
                        anon = self._anonymize_dict(raw) if isinstance(raw, dict) else raw
                        package["crystals"].append({
                            "source": level_dir_name,
                            "filename": f.name,
                            "data": anon,
                        })
                    except Exception:
                        pass

        # 2. Skill 使用統計
        stats_dir = self._data_dir / "_system" / "budget"
        if stats_dir.exists():
            for f in stats_dir.glob("routing_log_*.jsonl"):
                try:
                    lines = f.read_text(encoding="utf-8").strip().split("\n")
                    for line in lines[-100:]:  # 最近 100 筆
                        entry = json.loads(line)
                        task_type = entry.get("task_type", "unknown")
                        package["skill_stats"][task_type] = (
                            package["skill_stats"].get(task_type, 0) + 1
                        )
                except Exception:
                    pass

        # 3. Workflow 執行記錄
        wf_dir = self._data_dir / "_system" / "workflow"
        if wf_dir.exists():
            for f in sorted(wf_dir.glob("*.json"))[-20:]:  # 最近 20 筆
                try:
                    raw = json.loads(f.read_text(encoding="utf-8"))
                    anon = self._anonymize_dict(raw) if isinstance(raw, dict) else raw
                    package["workflow_records"].append(anon)
                except Exception:
                    pass

        return package

    def push_sync_package(self) -> Dict[str, Any]:
        """推送同步包到 GitHub.

        Returns:
            推送結果
        """
        if not self._ensure_repo():
            return {"error": "Federation repo not available"}

        # Pull latest
        self._git("pull", "--rebase", "--quiet")

        # 建構 sync package
        package = self.build_sync_package()

        # 寫入子體目錄
        child_dir = self._fed_dir / "children" / self._node_id
        child_dir.mkdir(parents=True, exist_ok=True)

        # sync_manifest.json
        manifest_path = child_dir / "sync_manifest.json"
        manifest_path.write_text(
            json.dumps(package, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 分別寫入 crystals 和 skill_stats
        crystals_dir = child_dir / "crystals"
        crystals_dir.mkdir(exist_ok=True)
        for i, crystal in enumerate(package.get("crystals", [])):
            cp = crystals_dir / crystal.get("filename", f"crystal_{i}.json")
            cp.write_text(
                json.dumps(crystal.get("data", {}), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        stats_dir = child_dir / "skill_stats"
        stats_dir.mkdir(exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        (stats_dir / f"stats_{today}.json").write_text(
            json.dumps(package.get("skill_stats", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Git commit & push
        self._git("add", f"children/{self._node_id}/")
        result = self._git(
            "commit", "-m",
            f"[{self._node_id}] daily sync {today}",
        )
        if result.returncode != 0 and "nothing to commit" in result.stdout:
            return {"status": "no_changes", "node_id": self._node_id}

        push_result = self._git("push", "--quiet")
        if push_result.returncode != 0:
            return {"error": f"Push failed: {push_result.stderr}", "node_id": self._node_id}

        return {
            "status": "pushed",
            "node_id": self._node_id,
            "crystals": len(package.get("crystals", [])),
            "skill_stats_keys": len(package.get("skill_stats", {})),
            "workflow_records": len(package.get("workflow_records", [])),
        }

    # ── Pull Evolution (子體 ← GitHub origin/) ──

    def pull_evolution(self) -> Dict[str, Any]:
        """從 origin/ 拉取母體演化成果.

        Returns:
            拉取結果
        """
        if not self._ensure_repo():
            return {"error": "Federation repo not available"}

        # Pull latest
        self._git("pull", "--rebase", "--quiet")

        origin_dir = self._fed_dir / "origin"
        if not origin_dir.exists():
            return {"status": "no_origin_updates"}

        updates = {"skills": 0, "workflows": 0, "crystals": 0}

        # Skills 更新
        skills_dir = origin_dir / "skills"
        if skills_dir.exists():
            local_skills = self._data_dir.parent / "skills"
            if local_skills.exists():
                for sf in skills_dir.glob("*.md"):
                    dest = local_skills / sf.name
                    try:
                        shutil.copy2(sf, dest)
                        updates["skills"] += 1
                    except Exception as e:
                        logger.warning(f"Skill copy failed: {sf.name}: {e}")

        # Workflows 更新
        wf_src = origin_dir / "workflows"
        if wf_src.exists():
            wf_dest = self._data_dir.parent / "skills"  # workflow .md 也在 skills 目錄
            if wf_dest.exists():
                for wf in wf_src.glob("*.md"):
                    dest = wf_dest / wf.name
                    try:
                        shutil.copy2(wf, dest)
                        updates["workflows"] += 1
                    except Exception as e:
                        logger.warning(f"Workflow copy failed: {wf.name}: {e}")

        # Crystals 更新（母體從所有子體萃取的共識智慧）
        crystals_src = origin_dir / "crystals"
        if crystals_src.exists():
            crystals_dest = self._data_dir / "memory_v3" / "L2_sem"
            crystals_dest.mkdir(parents=True, exist_ok=True)
            for cf in crystals_src.glob("*.json"):
                dest = crystals_dest / f"fed_{cf.name}"
                try:
                    shutil.copy2(cf, dest)
                    updates["crystals"] += 1
                except Exception as e:
                    logger.warning(f"Crystal copy failed: {cf.name}: {e}")

        return {"status": "pulled", "updates": updates}

    # ── Collect Children (母體收集) ──

    def collect_children(self) -> Dict[str, Any]:
        """母體收集所有子體經驗（僅 origin 模式可用）.

        Returns:
            收集結果
        """
        if self._mode != "origin":
            return {"skipped": "Not in origin mode"}

        if not self._ensure_repo():
            return {"error": "Federation repo not available"}

        self._git("pull", "--rebase", "--quiet")

        children_dir = self._fed_dir / "children"
        if not children_dir.exists():
            return {"status": "no_children"}

        collected = {}
        for child_dir in children_dir.iterdir():
            if not child_dir.is_dir() or child_dir.name.startswith("."):
                continue

            child_id = child_dir.name
            manifest = child_dir / "sync_manifest.json"
            if manifest.exists():
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    collected[child_id] = {
                        "timestamp": data.get("timestamp"),
                        "crystals": len(data.get("crystals", [])),
                        "skill_stats": data.get("skill_stats", {}),
                        "workflow_records": len(data.get("workflow_records", [])),
                    }
                except Exception as e:
                    collected[child_id] = {"error": str(e)}

        return {"status": "collected", "children": collected}

    # ── Status ──

    def get_status(self) -> Dict[str, Any]:
        """取得 Federation 狀態."""
        return {
            "node_id": self._node_id,
            "mode": self._mode,
            "repo_url": self._repo_url or "(not configured)",
            "repo_ready": self._is_git_repo(),
            "fed_dir": str(self._fed_dir),
        }
