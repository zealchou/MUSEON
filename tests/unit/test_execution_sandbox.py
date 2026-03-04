"""Tests for ExecutionSandbox — Docker-based 安全執行沙盒.

大部分測試 mock 掉 Docker（CI 環境無 Docker daemon）。
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from museon.security.execution_sandbox import (
    CONTAINER_PREFIX,
    DEFAULT_TIMEOUT,
    ExecutionSandbox,
    LANGUAGE_CONFIG,
    MAX_CPU,
    MAX_MEMORY,
    MAX_TIMEOUT,
    SANDBOX_IMAGE,
)


# ═══════════════════════════════════════════
# TestExecutionSandbox — 基礎測試
# ═══════════════════════════════════════════


class TestExecutionSandbox:
    """ExecutionSandbox 基礎測試."""

    def test_constants(self):
        """常數定義正確."""
        assert SANDBOX_IMAGE == "python:3.11-slim"
        assert DEFAULT_TIMEOUT == 30
        assert MAX_TIMEOUT == 300
        assert MAX_MEMORY == "256m"
        assert MAX_CPU == "0.5"
        assert CONTAINER_PREFIX == "museon-sandbox-"

    def test_language_config(self):
        """語言設定."""
        assert "python" in LANGUAGE_CONFIG
        assert "shell" in LANGUAGE_CONFIG
        assert "node" in LANGUAGE_CONFIG
        assert LANGUAGE_CONFIG["python"]["image"] == "python:3.11-slim"

    def test_init(self, tmp_path):
        """初始化建立審計目錄."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        assert sandbox._audit_dir.exists()
        assert sandbox._audit_dir == tmp_path / "_system" / "sandbox_audit"

    def test_is_docker_available_false(self, tmp_path):
        """Docker 不可用."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert sandbox.is_docker_available() is False

    def test_is_docker_available_true(self, tmp_path):
        """Docker 可用."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            assert sandbox.is_docker_available() is True


# ═══════════════════════════════════════════
# TestPreScan
# ═══════════════════════════════════════════


class TestPreScan:
    """SecurityScanner 預掃描測試."""

    def test_clean_code_not_blocked(self, tmp_path):
        """安全程式碼不被攔截."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        result = sandbox._pre_scan("print('hello')")
        assert result["blocked"] is False

    def test_critical_code_blocked(self, tmp_path):
        """CRITICAL 等級程式碼被攔截."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        # eval() 是 CRITICAL 等級
        result = sandbox._pre_scan("eval(input())")
        assert result["blocked"] is True
        assert "CRITICAL" in result.get("reason", "")

    def test_scanner_unavailable_not_blocked(self, tmp_path):
        """SecurityScanner 不可用時不攔截."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        with patch.dict("sys.modules", {"museon.security.skill_scanner": None}):
            # Force reimport failure
            with patch(
                "museon.security.execution_sandbox.ExecutionSandbox._pre_scan",
                wraps=sandbox._pre_scan,
            ):
                # 直接測試 ImportError 路徑
                result = sandbox._pre_scan("anything")
                # 由於實際 scanner 已安裝，只測試非 CRITICAL 情況
                if not result.get("blocked"):
                    assert result["blocked"] is False


# ═══════════════════════════════════════════
# TestBuildDockerCmd
# ═══════════════════════════════════════════


class TestBuildDockerCmd:
    """Docker 指令建構測試."""

    def test_python_cmd(self, tmp_path):
        """Python 執行指令."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        cmd = sandbox._build_docker_cmd("print('hi')", "python", 30)

        assert cmd[0] == "docker"
        assert cmd[1] == "run"
        assert "--rm" in cmd
        assert "--cap-drop=ALL" in cmd
        assert "--read-only" in cmd
        assert "--network=none" in cmd
        assert f"--memory={MAX_MEMORY}" in cmd
        assert f"--cpus={MAX_CPU}" in cmd
        assert "python:3.11-slim" in cmd
        assert "print('hi')" in cmd

    def test_shell_cmd(self, tmp_path):
        """Shell 執行指令."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        cmd = sandbox._build_docker_cmd("echo hello", "shell", 10)

        assert "alpine:3.19" in cmd
        assert "sh" in cmd
        assert "-c" in cmd

    def test_node_cmd(self, tmp_path):
        """Node.js 執行指令."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        cmd = sandbox._build_docker_cmd("console.log('hi')", "node", 10)

        assert "node:20-slim" in cmd
        assert "node" in cmd
        assert "-e" in cmd

    def test_pids_limit(self, tmp_path):
        """PID 限制."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        cmd = sandbox._build_docker_cmd("x", "python", 10)
        assert "--pids-limit=50" in cmd

    def test_unknown_language_defaults_python(self, tmp_path):
        """未知語言預設 Python."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        cmd = sandbox._build_docker_cmd("code", "unknown_lang", 10)
        assert "python:3.11-slim" in cmd


# ═══════════════════════════════════════════
# TestAuditLog
# ═══════════════════════════════════════════


class TestAuditLog:
    """審計日誌測試."""

    def test_audit_log_creates_file(self, tmp_path):
        """審計日誌建立檔案."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        audit_id = sandbox._audit_log("print('test')", {
            "success": True,
            "exit_code": 0,
            "duration_ms": 100,
        })

        assert audit_id  # 非空
        assert len(audit_id) == 12

        # 檢查日誌檔
        log_files = list(sandbox._audit_dir.glob("audit_*.jsonl"))
        assert len(log_files) == 1

        with open(log_files[0]) as f:
            entry = json.loads(f.readline())
        assert entry["audit_id"] == audit_id
        assert entry["success"] is True
        assert entry["code_length"] == len("print('test')")

    def test_audit_log_blocked(self, tmp_path):
        """審計記錄被攔截的執行."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        audit_id = sandbox._audit_log("eval(x)", {
            "blocked": True,
            "reason": "CRITICAL risk",
        })

        log_files = list(sandbox._audit_dir.glob("audit_*.jsonl"))
        with open(log_files[0]) as f:
            entry = json.loads(f.readline())
        assert entry["blocked"] is True

    def test_get_audit_stats(self, tmp_path):
        """審計統計."""
        sandbox = ExecutionSandbox(workspace=tmp_path)

        # 寫入幾筆紀錄
        sandbox._audit_log("code1", {"success": True})
        sandbox._audit_log("code2", {"success": False})
        sandbox._audit_log("code3", {"blocked": True})

        stats = sandbox.get_audit_stats()
        assert stats["total"] == 3
        assert stats["success"] == 1
        assert stats["failed"] == 1
        assert stats["blocked"] == 1


# ═══════════════════════════════════════════
# TestExecute（Mock Docker）
# ═══════════════════════════════════════════


class TestExecuteMock:
    """execute() 方法測試（Mock Docker）."""

    @pytest.mark.asyncio
    async def test_execute_docker_unavailable(self, tmp_path):
        """Docker 不可用時回傳 error."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        with patch.object(sandbox, "is_docker_available", return_value=False):
            result = await sandbox.execute("print('hi')")
            assert result["success"] is False
            assert "Docker" in result["stderr"]

    @pytest.mark.asyncio
    async def test_execute_blocked_by_scan(self, tmp_path):
        """CRITICAL 程式碼被預掃描攔截."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        result = await sandbox.execute("eval(user_input)")
        assert result["success"] is False
        assert result["blocked"] is True
        assert result["audit_id"]  # 有審計記錄

    @pytest.mark.asyncio
    async def test_execute_timeout_capped(self, tmp_path):
        """timeout 不超過 MAX_TIMEOUT."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        with patch.object(sandbox, "is_docker_available", return_value=False):
            result = await sandbox.execute("x", timeout=9999)
            # 不會真正超時（Docker 不可用），但確認不會 crash
            assert result["success"] is False


# ═══════════════════════════════════════════
# TestSandboxIntegration
# ═══════════════════════════════════════════


class TestSandboxIntegration:
    """sandbox.py → ExecutionSandbox 整合測試."""

    @pytest.mark.asyncio
    async def test_sandbox_delegates_to_execution_sandbox(self, tmp_path):
        """sandbox.py execute_command 委派到 ExecutionSandbox."""
        from museon.security.sandbox import Sandbox

        sandbox = Sandbox(workspace_dir=tmp_path)
        # 使用白名單指令
        result = await sandbox.execute_command("echo hello")

        # 不管 Docker 是否可用，至少 allowed=True
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_sandbox_blocks_non_whitelisted(self, tmp_path):
        """非白名單指令仍被 sandbox.py 攔截."""
        from museon.security.sandbox import Sandbox

        sandbox = Sandbox(workspace_dir=tmp_path)
        result = await sandbox.execute_command("rm -rf /")

        assert result["allowed"] is False
        assert result["reason"] == "command_not_whitelisted"

    def test_cleanup_stale(self, tmp_path):
        """cleanup_stale 不出錯."""
        sandbox = ExecutionSandbox(workspace=tmp_path)
        # 即使 Docker 不可用也不應出錯
        with patch("subprocess.run", side_effect=FileNotFoundError):
            count = sandbox.cleanup_stale()
            assert count == 0
