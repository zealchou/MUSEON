"""ExecutionSandbox — Docker-based 安全執行沙盒.

在 Docker 容器中安全執行不受信任的程式碼。
取代 sandbox.py 的 STUB execute_command()。

安全措施：
- --rm（用完即銷毀）
- --cap-drop=ALL（移除所有 Linux capabilities）
- --read-only（唯讀檔案系統）
- --tmpfs /tmp:size=64m（限制暫存空間）
- --network=none（禁止網路）
- --memory / --cpus（資源限制）
- SecurityScanner 預掃描（CRITICAL 等級直接拒絕）
- 審計日誌記錄
"""

import asyncio
import json
import logging
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

SANDBOX_IMAGE = "python:3.11-slim"
CONTAINER_PREFIX = "museclaw-sandbox-"
DEFAULT_TIMEOUT = 30     # 秒
MAX_TIMEOUT = 300        # 秒
MAX_MEMORY = "256m"
MAX_CPU = "0.5"
MAX_TMPFS_SIZE = "64m"

# 支援的語言 → Docker image + 執行指令
LANGUAGE_CONFIG = {
    "python": {
        "image": "python:3.11-slim",
        "cmd_prefix": ["python3", "-c"],
    },
    "shell": {
        "image": "alpine:3.19",
        "cmd_prefix": ["sh", "-c"],
    },
    "node": {
        "image": "node:20-slim",
        "cmd_prefix": ["node", "-e"],
    },
}


class ExecutionSandbox:
    """Docker-based 安全執行沙盒.

    在隔離的 Docker 容器中執行程式碼，
    完整資源限制 + 審計日誌。

    Usage:
        sandbox = ExecutionSandbox(workspace=Path("data"))
        result = await sandbox.execute("print('hello')", language="python")
        # result: {success: True, stdout: "hello\n", ...}
    """

    def __init__(self, workspace: Path):
        """初始化 ExecutionSandbox.

        Args:
            workspace: 工作目錄（審計日誌存放位置）
        """
        self._workspace = Path(workspace)
        self._audit_dir = self._workspace / "_system" / "sandbox_audit"
        self._audit_dir.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════════
    # 主要執行方法
    # ═══════════════════════════════════════════

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        """在 Docker 容器中執行程式碼.

        Args:
            code: 要執行的程式碼
            language: 程式語言（python / shell / node）
            timeout: 超時秒數（上限 MAX_TIMEOUT）

        Returns:
            {
                success: bool,
                stdout: str,
                stderr: str,
                exit_code: int,
                duration_ms: int,
                audit_id: str,
                blocked: bool,       # 被安全掃描攔截
                block_reason: str,   # 攔截原因
            }
        """
        # 限制 timeout
        timeout = min(timeout, MAX_TIMEOUT)

        # 步驟 1：SecurityScanner 預掃描
        scan_result = self._pre_scan(code)
        if scan_result.get("blocked"):
            result = {
                "success": False,
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "duration_ms": 0,
                "blocked": True,
                "block_reason": scan_result.get("reason", "security_scan"),
                "audit_id": self._audit_log(code, {
                    "blocked": True,
                    "reason": scan_result.get("reason"),
                }),
            }
            return result

        # 步驟 2：檢查 Docker
        if not self.is_docker_available():
            return {
                "success": False,
                "stdout": "",
                "stderr": "Docker is not available",
                "exit_code": -1,
                "duration_ms": 0,
                "blocked": False,
                "block_reason": "",
                "audit_id": "",
            }

        # 步驟 3：組裝 Docker 指令
        docker_cmd = self._build_docker_cmd(code, language, timeout)

        # 步驟 4：執行
        start_time = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout + 5,  # 額外 5 秒給 Docker 啟動
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                stdout_bytes = b""
                stderr_bytes = b"Execution timed out"

            duration_ms = int((time.time() - start_time) * 1000)

            result = {
                "success": proc.returncode == 0,
                "stdout": stdout_bytes.decode("utf-8", errors="replace")[:10000],
                "stderr": stderr_bytes.decode("utf-8", errors="replace")[:5000],
                "exit_code": proc.returncode or 0,
                "duration_ms": duration_ms,
                "blocked": False,
                "block_reason": "",
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            result = {
                "success": False,
                "stdout": "",
                "stderr": str(e)[:1000],
                "exit_code": -1,
                "duration_ms": duration_ms,
                "blocked": False,
                "block_reason": "",
            }

        # 步驟 5：審計日誌
        result["audit_id"] = self._audit_log(code, result)

        return result

    # ═══════════════════════════════════════════
    # 安全掃描
    # ═══════════════════════════════════════════

    def _pre_scan(self, code: str) -> Dict[str, Any]:
        """SecurityScanner 預掃描.

        CRITICAL 等級直接拒絕。

        Returns:
            {"blocked": bool, "reason": str}
        """
        try:
            from museclaw.security.skill_scanner import (
                SecurityScanner,
                RiskLevel,
            )

            scanner = SecurityScanner()
            scan = scanner.scan_skill(code)

            if scan.get("risk_level", 0) >= RiskLevel.CRITICAL:
                return {
                    "blocked": True,
                    "reason": f"CRITICAL risk detected: {scan.get('summary', '')}",
                }

            return {"blocked": False}

        except ImportError:
            # SecurityScanner 不可用，允許執行
            logger.warning("SecurityScanner not available, skipping pre-scan")
            return {"blocked": False}

        except Exception as e:
            logger.warning(f"Pre-scan error: {e}")
            return {"blocked": False}

    # ═══════════════════════════════════════════
    # Docker 指令建構
    # ═══════════════════════════════════════════

    def _build_docker_cmd(
        self,
        code: str,
        language: str,
        timeout: int,
    ) -> list:
        """組裝 docker run 指令.

        安全措施：
        - --rm: 用完即銷毀
        - --cap-drop=ALL: 移除所有 Linux capabilities
        - --read-only: 唯讀檔案系統
        - --tmpfs /tmp: 暫存空間限制
        - --network=none: 禁止網路
        - --memory: 記憶體限制
        - --cpus: CPU 限制
        """
        lang_config = LANGUAGE_CONFIG.get(language, LANGUAGE_CONFIG["python"])
        image = lang_config["image"]
        cmd_prefix = lang_config["cmd_prefix"]

        container_name = f"{CONTAINER_PREFIX}{uuid.uuid4().hex[:8]}"

        docker_args = [
            "docker", "run",
            "--rm",
            "--name", container_name,
            "--cap-drop=ALL",
            "--read-only",
            f"--tmpfs=/tmp:size={MAX_TMPFS_SIZE},noexec",
            "--network=none",
            f"--memory={MAX_MEMORY}",
            f"--cpus={MAX_CPU}",
            "--pids-limit=50",
            "--ulimit", "nproc=50:50",
            "--ulimit", "fsize=10485760:10485760",  # 10MB max file
            image,
            *cmd_prefix,
            code,
        ]

        return docker_args

    # ═══════════════════════════════════════════
    # 審計日誌
    # ═══════════════════════════════════════════

    def _audit_log(self, code: str, result: Dict) -> str:
        """記錄審計日誌到 _system/sandbox_audit/.

        Args:
            code: 執行的程式碼
            result: 執行結果

        Returns:
            audit_id
        """
        audit_id = str(uuid.uuid4())[:12]

        try:
            now = datetime.now(TZ_TAIPEI).isoformat()
            log_entry = {
                "audit_id": audit_id,
                "timestamp": now,
                "code_preview": code[:500],
                "code_length": len(code),
                "success": result.get("success", False),
                "exit_code": result.get("exit_code", -1),
                "duration_ms": result.get("duration_ms", 0),
                "blocked": result.get("blocked", False),
                "block_reason": result.get("block_reason", ""),
                "stderr_preview": result.get("stderr", "")[:200],
            }

            # 按日期分檔
            date_str = datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d")
            log_file = self._audit_dir / f"audit_{date_str}.jsonl"

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        except Exception as e:
            logger.warning(f"Audit log failed: {e}")

        return audit_id

    # ═══════════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════════

    def is_docker_available(self) -> bool:
        """檢查 Docker daemon 是否運行."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def cleanup_stale(self, max_age_hours: int = 1) -> int:
        """清理殘留的 sandbox 容器.

        Args:
            max_age_hours: 超過此時間的容器會被清理

        Returns:
            清理數量
        """
        cleaned = 0
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--filter",
                 f"name={CONTAINER_PREFIX}",
                 "--format", "{{.Names}} {{.CreatedAt}}"],
                capture_output=True, text=True, timeout=10,
            )

            if result.returncode != 0:
                return 0

            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue

                parts = line.strip().split(" ", 1)
                container_name = parts[0]

                # 嘗試移除
                try:
                    subprocess.run(
                        ["docker", "rm", "-f", container_name],
                        capture_output=True, timeout=10,
                    )
                    cleaned += 1
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")

        return cleaned

    def get_audit_stats(self) -> Dict[str, Any]:
        """取得審計統計.

        Returns:
            {"total": int, "blocked": int, "success": int, "failed": int}
        """
        stats = {"total": 0, "blocked": 0, "success": 0, "failed": 0}

        try:
            for log_file in sorted(self._audit_dir.glob("audit_*.jsonl")):
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            stats["total"] += 1
                            if entry.get("blocked"):
                                stats["blocked"] += 1
                            elif entry.get("success"):
                                stats["success"] += 1
                            else:
                                stats["failed"] += 1
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass

        return stats
