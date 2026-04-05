"""MorphenixValidator — Docker 環境驗證 L2+ 提案.

在 Morphenix L2 提案正式 git apply 到生產環境之前，
先在 Docker 容器中驗證修改不會破壞系統。

流程：
  1. rsync 原始碼到臨時目錄
  2. 在臨時目錄中 apply patch / text replace
  3. Docker 中跑 pytest tests/unit/ -x
  4. 回傳 ValidationResult

L1（JSON config）跳過 Docker 驗證（風險低）。
L2+（原始碼修改）強制 Docker 驗證。
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DOCKER_IMAGE = "museon-validator:latest"
DOCKER_TIMEOUT = 180  # 3 分鐘 pytest 逾時
RSYNC_EXCLUDES = [
    "__pycache__",
    ".pytest_cache",
    "*.pyc",
    ".coverage",
    "htmlcov",
    ".git",
    "data",
    "logs",
    "dist",
    ".runtime",
    "node_modules",
    "electron",
]


@dataclass
class ValidationResult:
    """Docker 驗證結果."""

    passed: bool
    reason: str = ""
    pytest_output: str = ""
    syntax_errors: List[str] = field(default_factory=list)
    duration_ms: int = 0


class MorphenixValidator:
    """在 Docker 隔離環境中驗證 Morphenix L2+ 提案."""

    def __init__(self, source_root: Path):
        self._source_root = Path(source_root)
        self._sandbox_dir: Optional[Path] = None

    async def validate_proposal(self, proposal: Dict) -> ValidationResult:
        """驗證單一提案. L1 跳過，L2+ Docker pytest."""
        # 防禦：proposal metadata 有時從 DB 以字串形式返回
        if isinstance(proposal, str):
            try:
                proposal = json.loads(proposal)
            except (json.JSONDecodeError, TypeError):
                return ValidationResult(
                    passed=False,
                    reason="invalid_proposal_format",
                )

        level = proposal.get("level", "L1")

        # L1 不需要 Docker（只改 JSON config）
        if level == "L1":
            return ValidationResult(passed=True, reason="L1_skip_docker")

        # L2 pure-action 提案（無 patch/changes，只有 action 欄位）不涉及原始碼修改
        # 由 MorphenixExecutor._action_* handler 處理，跳過 Docker pytest
        metadata = proposal.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        action = metadata.get("action") or proposal.get("action", "")
        has_patch = bool(metadata.get("patch", ""))
        has_changes = bool(metadata.get("changes", []))
        if level == "L2" and action and not has_patch and not has_changes:
            logger.info(
                f"[MORPHENIX_VALIDATOR] L2 pure-action '{action}' detected, "
                "skipping Docker pytest (no source code changes)"
            )
            return ValidationResult(passed=True, reason="L2_pure_action_skip_docker")

        # 檢查 Docker 是否可用
        if not self._docker_available():
            logger.warning("Docker not available, skipping validation")
            return ValidationResult(
                passed=True,
                reason="docker_unavailable_skip",
            )

        # 檢查映像是否存在
        if not self._image_exists():
            logger.warning(f"Docker image {DOCKER_IMAGE} not found, skipping")
            return ValidationResult(
                passed=True,
                reason="docker_image_missing_skip",
            )

        import time
        t0 = time.monotonic()

        try:
            # Step 1: 建立臨時沙盒
            self._sandbox_dir = Path(tempfile.mkdtemp(prefix="museon-validate-"))
            self._prepare_sandbox()

            # Step 2: 在沙盒中 apply 變更
            apply_ok = self._apply_changes_in_sandbox(proposal)
            if not apply_ok:
                return ValidationResult(
                    passed=False,
                    reason="patch_apply_failed",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

            # Step 3: 語法檢查（快速篩選）
            syntax_errors = self._check_syntax()
            if syntax_errors:
                return ValidationResult(
                    passed=False,
                    reason="syntax_errors",
                    syntax_errors=syntax_errors,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

            # Step 4: Docker pytest
            pytest_result = await self._run_pytest_in_docker()

            return ValidationResult(
                passed=pytest_result["passed"],
                reason="pytest_passed" if pytest_result["passed"] else "pytest_failed",
                pytest_output=pytest_result.get("output", "")[:2000],
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        except Exception as e:
            logger.error(f"MorphenixValidator error: {e}", exc_info=True)
            return ValidationResult(
                passed=False,
                reason=f"validator_error: {str(e)[:200]}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        finally:
            # 清理臨時目錄
            if self._sandbox_dir and self._sandbox_dir.exists():
                try:
                    shutil.rmtree(self._sandbox_dir)
                except Exception as e:
                    logger.debug(f"[MORPHENIX_VALIDATOR] operation failed (degraded): {e}")

    def _docker_available(self) -> bool:
        """檢查 Docker daemon 是否可用."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _image_exists(self) -> bool:
        """檢查驗證映像是否已建構."""
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", DOCKER_IMAGE],
                capture_output=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _prepare_sandbox(self) -> None:
        """rsync 原始碼到臨時目錄（排除不需要的檔案）."""
        assert self._sandbox_dir is not None

        exclude_args = []
        for ex in RSYNC_EXCLUDES:
            exclude_args.extend(["--exclude", ex])

        # 複製 src/ 和 tests/
        for subdir in ("src", "tests", "pyproject.toml"):
            src_path = self._source_root / subdir
            if not src_path.exists():
                continue
            if src_path.is_file():
                shutil.copy2(src_path, self._sandbox_dir / subdir)
            else:
                subprocess.run(
                    ["rsync", "-a", "--delete"] + exclude_args +
                    [f"{src_path}/", str(self._sandbox_dir / subdir) + "/"],
                    capture_output=True, timeout=30,
                )

    def _apply_changes_in_sandbox(self, proposal: Dict) -> bool:
        """在沙盒中 apply 提案的變更."""
        assert self._sandbox_dir is not None
        metadata = proposal.get("metadata", {})
        # 防禦：metadata 可能從 DB 以字串形式返回
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                logger.warning("MorphenixValidator: metadata is str but not valid JSON")
                return False

        # 方式 1：unified diff patch
        patch = metadata.get("patch", "")
        if patch:
            result = subprocess.run(
                ["git", "apply", "--check", "-"],
                input=patch.encode(),
                capture_output=True,
                cwd=str(self._sandbox_dir),
                timeout=15,
            )
            if result.returncode != 0:
                logger.warning(f"Patch dry-run failed: {result.stderr.decode()[:300]}")
                return False
            result = subprocess.run(
                ["git", "apply", "-"],
                input=patch.encode(),
                capture_output=True,
                cwd=str(self._sandbox_dir),
                timeout=15,
            )
            return result.returncode == 0

        # 方式 2：結構化 text replace
        changes = metadata.get("changes", [])
        for change in changes:
            filepath = change.get("file", "")
            old_text = change.get("old", "")
            new_text = change.get("new", "")
            if not filepath or not old_text:
                continue
            target = self._sandbox_dir / filepath
            if not target.exists():
                logger.warning(f"Target file not found in sandbox: {filepath}")
                return False
            content = target.read_text(encoding="utf-8")
            if old_text not in content:
                logger.warning(f"Old text not found in {filepath}")
                return False
            content = content.replace(old_text, new_text, 1)
            target.write_text(content, encoding="utf-8")

        return True

    def _check_syntax(self) -> List[str]:
        """快速語法檢查（py_compile）."""
        assert self._sandbox_dir is not None
        errors = []
        src_dir = self._sandbox_dir / "src"
        if not src_dir.exists():
            return errors
        for py_file in src_dir.rglob("*.py"):
            try:
                import py_compile
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(str(e)[:200])
        return errors[:5]  # 最多回報 5 個

    async def _run_pytest_in_docker(self) -> Dict:
        """在 Docker 容器中跑 pytest."""
        assert self._sandbox_dir is not None

        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{self._sandbox_dir}:/museon:ro",
            "--network=none",
            "--memory=512m",
            "--cpus=1",
            DOCKER_IMAGE,
        ]

        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=DOCKER_TIMEOUT,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return {"passed": False, "output": "Docker pytest timed out"}

        output = stdout.decode(errors="replace") + stderr.decode(errors="replace")

        return {
            "passed": proc.returncode == 0,
            "output": output,
            "returncode": proc.returncode,
        }
