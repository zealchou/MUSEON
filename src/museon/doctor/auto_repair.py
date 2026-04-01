"""MUSEON Doctor — 自動修復引擎（Layer 2）

純 CPU 修復動作，零 Token。
每個修復動作都是冪等的（可安全重複執行）。
"""

import json
import os
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from .health_check import HealthChecker


class RepairStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    REPAIRED = "repaired"


@dataclass
class RepairResult:
    action: str
    status: RepairStatus
    message: str
    duration_ms: int = 0


class AutoRepair:
    """自動修復引擎 — 純 CPU"""

    def __init__(self, checker: Optional[HealthChecker] = None):
        self.checker = checker or HealthChecker()
        self.home = self.checker.home
        self.runtime_dir = self.checker.runtime_dir
        self.data_dir = self.checker.data_dir
        self.logs_dir = self.checker.logs_dir
        self.env_path = self.checker.env_path
        self.venv_dir = self.checker.venv_dir

    def _find_project_dir(self) -> Path:
        """找到 pyproject.toml 所在的目錄（支援 dev 和 production 佈局）.

        Production: pyproject.toml 在 .runtime/ 內
        Dev:        pyproject.toml 在 home 根目錄
        """
        if (self.runtime_dir / "pyproject.toml").exists():
            return self.runtime_dir
        if (self.home / "pyproject.toml").exists():
            return self.home
        return self.runtime_dir  # fallback

    def _find_src_dir(self) -> Path:
        """找到 src/ 目錄（支援 dev 和 production 佈局）."""
        if (self.runtime_dir / "src").exists():
            return self.runtime_dir / "src"
        if (self.home / "src").exists():
            return self.home / "src"
        return self.runtime_dir / "src"  # fallback

    def _find_venv_python(self) -> Optional[Path]:
        """找到 venv 的 python（支援 dev 和 production 佈局）."""
        for venv in [self.venv_dir, self.home / ".venv"]:
            p = venv / "bin" / "python"
            if p.exists():
                return p
        return None

    def _find_venv_pip(self) -> Optional[Path]:
        """找到 venv 的 pip（支援 dev 和 production 佈局）."""
        for venv in [self.venv_dir, self.home / ".venv"]:
            p = venv / "bin" / "pip"
            if p.exists():
                return p
        return None

    def execute(self, action: str) -> RepairResult:
        """執行指定修復動作"""
        start = datetime.now()
        handler = getattr(self, f"repair_{action}", None)
        if not handler:
            return RepairResult(
                action=action,
                status=RepairStatus.FAILED,
                message=f"未知的修復動作: {action}",
            )

        try:
            result = handler()
            result.duration_ms = int(
                (datetime.now() - start).total_seconds() * 1000
            )
            return result
        except Exception as e:
            return RepairResult(
                action=action,
                status=RepairStatus.FAILED,
                message=f"修復失敗: {e}",
                duration_ms=int(
                    (datetime.now() - start).total_seconds() * 1000
                ),
            )

    # ─── 修復動作 ───

    def repair_create_directories(self) -> RepairResult:
        """建立必要目錄結構"""
        dirs = [
            self.home,
            self.data_dir,
            self.logs_dir,
            self.data_dir / "anima",
            self.data_dir / "lattice",
            self.data_dir / "eval",
            self.data_dir / "memory",
            self.data_dir / "skills" / "native",
            self.data_dir / "skills" / "forged",
        ]
        created = []
        for d in dirs:
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                created.append(str(d.relative_to(self.home)))

        if not created:
            return RepairResult(
                action="create_directories",
                status=RepairStatus.SKIPPED,
                message="所有目錄已存在",
            )
        return RepairResult(
            action="create_directories",
            status=RepairStatus.SUCCESS,
            message=f"已建立 {len(created)} 個目錄: {', '.join(created)}",
        )

    def repair_create_env_file(self) -> RepairResult:
        """建立預設 .env 檔案"""
        if self.env_path.exists():
            return RepairResult(
                action="create_env_file",
                status=RepairStatus.SKIPPED,
                message=".env 已存在",
            )

        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.env_path.write_text(
            "# MUSEON 設定檔\n"
            "# 請填入你的 API Keys\n\n"
            "ANTHROPIC_API_KEY=\n"
            "TELEGRAM_BOT_TOKEN=\n"
            "TELEGRAM_TRUSTED_IDS=\n",
            encoding="utf-8",
        )
        os.chmod(str(self.env_path), 0o600)

        return RepairResult(
            action="create_env_file",
            status=RepairStatus.SUCCESS,
            message="已建立 .env（請填入 API Keys）",
        )

    def repair_fix_env_permissions(self) -> RepairResult:
        """修復 .env 權限為 600"""
        if not self.env_path.exists():
            return RepairResult(
                action="fix_env_permissions",
                status=RepairStatus.FAILED,
                message=".env 不存在",
            )

        os.chmod(str(self.env_path), 0o600)
        return RepairResult(
            action="fix_env_permissions",
            status=RepairStatus.SUCCESS,
            message=".env 權限已修正為 600",
        )

    def repair_recreate_venv(self) -> RepairResult:
        """重建 Python 虛擬環境"""
        # 找 Python >= 3.11
        python_path = None
        for candidate in ["python3.13", "python3.12", "python3.11", "python3"]:
            try:
                result = subprocess.run(
                    [candidate, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    version = result.stdout.strip()
                    parts = version.split()[-1].split(".")
                    if int(parts[0]) >= 3 and int(parts[1]) >= 11:
                        python_path = candidate
                        break
            except (subprocess.TimeoutExpired, OSError, ValueError):
                continue

        if not python_path:
            return RepairResult(
                action="recreate_venv",
                status=RepairStatus.FAILED,
                message="找不到 Python >= 3.11（請安裝: brew install python@3.13）",
            )

        # 刪除壞的 venv
        if self.venv_dir.exists():
            subprocess.run(
                ["rm", "-rf", str(self.venv_dir)],
                capture_output=True,
                timeout=30,
            )

        # 重建
        result = subprocess.run(
            [python_path, "-m", "venv", str(self.venv_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return RepairResult(
                action="recreate_venv",
                status=RepairStatus.FAILED,
                message=f"venv 建立失敗: {result.stderr[:200]}",
            )

        # 安裝依賴
        pip = self.venv_dir / "bin" / "pip"
        project_dir = self._find_project_dir()
        pyproject = project_dir / "pyproject.toml"
        if pyproject.exists():
            result = subprocess.run(
                [str(pip), "install", "-e", f"{project_dir}[dev]"],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(project_dir),
            )
            if result.returncode != 0:
                return RepairResult(
                    action="recreate_venv",
                    status=RepairStatus.FAILED,
                    message=f"pip install 失敗: {result.stderr[-500:]}",
                )

        return RepairResult(
            action="recreate_venv",
            status=RepairStatus.SUCCESS,
            message=f"已用 {python_path} 重建 venv",
        )

    def repair_start_gateway(self) -> RepairResult:
        """啟動 Gateway"""
        # 先檢查 port 是否被占用
        try:
            result = subprocess.run(
                ["lsof", "-i", f":{self.checker.gateway_port}", "-t"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split("\n")
                # 殺掉占用 port 的進程
                for pid in pids:
                    subprocess.run(
                        ["kill", "-9", pid.strip()],
                        capture_output=True,
                        timeout=5,
                    )
        except (subprocess.TimeoutExpired, OSError) as e:
            pass  # degraded: PID check

        # 透過 supervisorctl 啟動（supervisord 序列化管理，不直接操作 plist）
        supervisorctl = "/Users/ZEALCHOU/Library/Python/3.9/bin/supervisorctl"
        conf = str(self.home / "data/_system/supervisord.conf")
        result = subprocess.run(
            [supervisorctl, "-c", conf, "start", "museon-gateway"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return RepairResult(
                action="start_gateway",
                status=RepairStatus.SUCCESS,
                message="已透過 supervisorctl 啟動 Gateway",
            )

        return RepairResult(
            action="start_gateway",
            status=RepairStatus.FAILED,
            message=f"supervisorctl start 失敗: {result.stderr[:100]}",
        )

    def repair_load_daemon(self) -> RepairResult:
        """透過 supervisorctl 啟動 Gateway（supervisord 序列化管理）"""
        supervisorctl = "/Users/ZEALCHOU/Library/Python/3.9/bin/supervisorctl"
        conf = str(self.home / "data/_system/supervisord.conf")
        result = subprocess.run(
            [supervisorctl, "-c", conf, "start", "museon-gateway"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return RepairResult(
                action="load_daemon",
                status=RepairStatus.SUCCESS,
                message="Gateway 已透過 supervisorctl 啟動",
            )
        return RepairResult(
            action="load_daemon",
            status=RepairStatus.FAILED,
            message=f"supervisorctl start 失敗: {result.stderr[:100]}",
        )

    def repair_rotate_logs(self) -> RepairResult:
        """清理過大的日誌"""
        if not self.logs_dir.exists():
            return RepairResult(
                action="rotate_logs",
                status=RepairStatus.SKIPPED,
                message="logs/ 不存在",
            )

        rotated = []
        for f in self.logs_dir.iterdir():
            if f.is_file() and f.stat().st_size > 100 * 1024 * 1024:
                # 保留最後 1000 行
                try:
                    lines = f.read_text("utf-8", errors="replace").splitlines()
                    f.write_text("\n".join(lines[-1000:]) + "\n", "utf-8")
                    rotated.append(f.name)
                except OSError as e:
                    pass  # degraded: data write

        if not rotated:
            return RepairResult(
                action="rotate_logs",
                status=RepairStatus.SKIPPED,
                message="無需清理",
            )
        return RepairResult(
            action="rotate_logs",
            status=RepairStatus.SUCCESS,
            message=f"已清理: {', '.join(rotated)}",
        )

    def repair_reinstall_packages(self) -> RepairResult:
        """重新安裝 Python 依賴"""
        pip = self._find_venv_pip()
        if not pip:
            return RepairResult(
                action="reinstall_packages",
                status=RepairStatus.FAILED,
                message="venv 不存在，請先 recreate_venv",
            )

        project_dir = self._find_project_dir()
        result = subprocess.run(
            [str(pip), "install", "-e", f"{project_dir}[dev]"],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(project_dir),
        )
        if result.returncode == 0:
            return RepairResult(
                action="reinstall_packages",
                status=RepairStatus.SUCCESS,
                message="依賴已重新安裝",
            )
        return RepairResult(
            action="reinstall_packages",
            status=RepairStatus.FAILED,
            message=f"pip install 失敗: {result.stderr[-500:]}",
        )

    def repair_reinstall_daemon(self) -> RepairResult:
        """重新建立 supervisord 服務（installer 模組已移除）."""
        return RepairResult(
            action="reinstall_daemon",
            status=RepairStatus.FAILED,
            message="請手動執行: supervisorctl -c ~/MUSEON/data/_system/supervisord.conf restart museon-gateway",
        )

    def repair_rebuild_dashboard(self) -> RepairResult:
        """重建 Dashboard（Electron 已移除，此修復不再適用）."""
        return RepairResult(
            action="rebuild_dashboard",
            status=RepairStatus.FAILED,
            message="Electron dashboard 已廢棄，不需重建",
        )

    def repair_apply_crystal_procedures(self) -> RepairResult:
        """從 KnowledgeLattice 讀取 Procedure 結晶並執行安全操作步驟。

        此方法不會被自動排程調用，僅在 MuseOff triage 或手動觸發時執行。
        只執行三種安全操作：restart_service、check_file_exists、create_directory。
        """
        crystal_db = self.data_dir / "lattice" / "crystal.db"

        # crystal.db 不存在 → 靜默 SKIPPED
        if not crystal_db.exists():
            return RepairResult(
                action="apply_crystal_procedures",
                status=RepairStatus.SKIPPED,
                message="無可用的結晶修復程序",
            )

        # 查詢 type='procedure' 且 status='active' 的結晶
        try:
            conn = sqlite3.connect(str(crystal_db))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, title, content FROM crystals "
                "WHERE type='procedure' AND status='active'"
            )
            procedures = cursor.fetchall()
            conn.close()
        except sqlite3.Error:
            return RepairResult(
                action="apply_crystal_procedures",
                status=RepairStatus.SKIPPED,
                message="無可用的結晶修復程序",
            )

        if not procedures:
            return RepairResult(
                action="apply_crystal_procedures",
                status=RepairStatus.SKIPPED,
                message="無可用的結晶修復程序",
            )

        # 確保 guardian 目錄存在
        guardian_dir = self.data_dir / "guardian"
        guardian_dir.mkdir(parents=True, exist_ok=True)
        log_path = guardian_dir / "crystal_repair_log.jsonl"

        # 安全操作白名單
        SAFE_OPERATIONS = {"restart_service", "check_file_exists", "create_directory"}

        executed_count = 0
        skipped_count = 0

        for proc in procedures:
            proc_id = proc["id"]
            proc_title = proc["title"] or proc_id

            # 解析 content 中的 steps 欄位
            steps = []
            try:
                content_data = json.loads(proc["content"] or "{}")
                raw_steps = content_data.get("steps", [])
                if isinstance(raw_steps, list):
                    steps = raw_steps
            except (json.JSONDecodeError, TypeError):
                # content 不是 JSON 或 steps 格式不符 → 跳過此 procedure
                self._append_jsonl(log_path, {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "procedure_id": proc_id,
                    "procedure_title": proc_title,
                    "step_index": None,
                    "operation": None,
                    "status": "skipped",
                    "message": "content 無法解析或缺少 steps 欄位",
                })
                skipped_count += 1
                continue

            # 逐步執行
            for idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue
                operation = step.get("operation", "")
                params = step.get("params", {})

                # 只執行安全操作
                if operation not in SAFE_OPERATIONS:
                    self._append_jsonl(log_path, {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "procedure_id": proc_id,
                        "procedure_title": proc_title,
                        "step_index": idx,
                        "operation": operation,
                        "status": "skipped",
                        "message": f"操作 '{operation}' 不在安全白名單，已略過",
                    })
                    skipped_count += 1
                    continue

                step_status, step_message = self._execute_safe_operation(
                    operation, params
                )
                self._append_jsonl(log_path, {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "procedure_id": proc_id,
                    "procedure_title": proc_title,
                    "step_index": idx,
                    "operation": operation,
                    "params": params,
                    "status": step_status,
                    "message": step_message,
                })
                executed_count += 1

        return RepairResult(
            action="apply_crystal_procedures",
            status=RepairStatus.SUCCESS,
            message=(
                f"已處理 {len(procedures)} 個結晶程序，"
                f"執行 {executed_count} 步，略過 {skipped_count} 步"
            ),
        )

    def _execute_safe_operation(
        self, operation: str, params: dict
    ) -> tuple[str, str]:
        """執行單一安全操作，回傳 (status, message)."""
        try:
            if operation == "create_directory":
                target = params.get("path", "")
                if not target:
                    return "failed", "缺少 path 參數"
                Path(target).mkdir(parents=True, exist_ok=True)
                return "success", f"目錄已確保存在：{target}"

            elif operation == "check_file_exists":
                target = params.get("path", "")
                if not target:
                    return "failed", "缺少 path 參數"
                exists = Path(target).exists()
                return "success", f"檔案存在：{exists}（{target}）"

            elif operation == "restart_service":
                service = params.get("service", "")
                if not service:
                    return "failed", "缺少 service 參數"
                supervisorctl = "/Users/ZEALCHOU/Library/Python/3.9/bin/supervisorctl"
                conf = str(self.home / "data/_system/supervisord.conf")
                result = subprocess.run(
                    [supervisorctl, "-c", conf, "restart", service],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    return "success", f"服務 '{service}' 已重啟"
                return "failed", f"重啟 '{service}' 失敗：{result.stderr[:100]}"

        except Exception as e:
            return "failed", f"執行例外：{e}"

        return "skipped", "未知操作"

    def _append_jsonl(self, path: Path, record: dict) -> None:
        """將一筆記錄以 JSONL 格式追加到檔案。"""
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass  # degraded: log write

    def repair_restore_anima(self) -> RepairResult:
        """修復 ANIMA_MC.json 損壞的情況。

        如果 ANIMA_MC.json 有效，直接 SKIPPED。
        如果無效或不存在，嘗試從 .bak 還原；.bak 也無效則返回 FAILED。
        """
        anima_path = self.data_dir / "ANIMA_MC.json"
        bak_path = self.data_dir / "ANIMA_MC.json.bak"

        def is_valid_anima(path: Path) -> bool:
            """檢查 ANIMA_MC JSON 是否可解析且包含 identity.name。"""
            if not path.exists():
                return False
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                identity = data.get("identity", {})
                return bool(identity.get("name"))
            except (json.JSONDecodeError, OSError, AttributeError):
                return False

        # 1. 已存在且有效 → SKIPPED
        if is_valid_anima(anima_path):
            return RepairResult(
                action="restore_anima",
                status=RepairStatus.SKIPPED,
                message="ANIMA_MC.json 有效，無需修復",
            )

        # 2. 嘗試從 .bak 還原
        if is_valid_anima(bak_path):
            try:
                shutil.copy2(str(bak_path), str(anima_path))
            except OSError as e:
                return RepairResult(
                    action="restore_anima",
                    status=RepairStatus.FAILED,
                    message=f"複製備份失敗：{e}",
                )

            # 寫入修復日誌
            guardian_dir = self.data_dir / "guardian"
            guardian_dir.mkdir(parents=True, exist_ok=True)
            action = "restore_anima"
            self._append_jsonl(guardian_dir / "repair_log.jsonl", {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "status": "repaired",
                "source": str(bak_path),
                "target": str(anima_path),
                "message": "ANIMA_MC 已從備份還原",
            })

            # 重大修復事件 → 沉積 soul ring 候選
            try:
                ring_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "ring_type": "resilience",
                    "content": f"系統身份資料損壞，已從備份成功還原。修復動作：{action}",
                    "metadata": {"repair_action": "restore_anima", "outcome": "success"},
                }
                pending_path = self.data_dir / "anima" / "pending_rings.jsonl"
                pending_path.parent.mkdir(parents=True, exist_ok=True)
                with open(pending_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(ring_entry, ensure_ascii=False) + "\n")
            except Exception:
                pass

            return RepairResult(
                action="restore_anima",
                status=RepairStatus.REPAIRED,
                message="ANIMA_MC 已從備份還原",
            )

        # 3. .bak 也無效
        return RepairResult(
            action="restore_anima",
            status=RepairStatus.FAILED,
            message="ANIMA_MC 損壞且無有效備份，需要人工介入",
        )

    def repair_backup_anima(self) -> RepairResult:
        """將 ANIMA_MC.json 備份為 .bak（設計為 Nightly 定期調用）。

        僅在 ANIMA_MC.json 存在、可解析、有 identity.name、
        且大小 > 100 bytes 時執行備份。
        """
        anima_path = self.data_dir / "ANIMA_MC.json"
        bak_path = self.data_dir / "ANIMA_MC.json.bak"

        if not anima_path.exists():
            return RepairResult(
                action="backup_anima",
                status=RepairStatus.SKIPPED,
                message="ANIMA_MC.json 不存在，略過備份",
            )

        # 檢查大小
        if anima_path.stat().st_size <= 100:
            return RepairResult(
                action="backup_anima",
                status=RepairStatus.SKIPPED,
                message="ANIMA_MC.json 大小 ≤ 100 bytes，略過備份",
            )

        # 檢查 JSON 格式與 identity.name
        try:
            data = json.loads(anima_path.read_text(encoding="utf-8"))
            identity = data.get("identity", {})
            if not isinstance(identity, dict) or not identity.get("name"):
                return RepairResult(
                    action="backup_anima",
                    status=RepairStatus.SKIPPED,
                    message="ANIMA_MC.json 缺少 identity.name，略過備份以免覆蓋好的 .bak",
                )
        except (json.JSONDecodeError, OSError) as e:
            return RepairResult(
                action="backup_anima",
                status=RepairStatus.SKIPPED,
                message=f"ANIMA_MC.json 無法解析（{e}），略過備份以免覆蓋好的 .bak",
            )

        # 執行備份
        try:
            shutil.copy2(str(anima_path), str(bak_path))
        except OSError as e:
            return RepairResult(
                action="backup_anima",
                status=RepairStatus.FAILED,
                message=f"備份失敗：{e}",
            )

        # 定期備份成功 → 沉積 soul ring 候選
        try:
            ring_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ring_type": "maintenance",
                "content": f"系統身份資料定期備份完成。備份至 {bak_path.name}",
                "metadata": {"repair_action": "backup_anima", "outcome": "success"},
            }
            pending_path = self.data_dir / "anima" / "pending_rings.jsonl"
            pending_path.parent.mkdir(parents=True, exist_ok=True)
            with open(pending_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(ring_entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

        return RepairResult(
            action="backup_anima",
            status=RepairStatus.REPAIRED,
            message=f"ANIMA_MC.json 已備份至 {bak_path.name}",
        )
