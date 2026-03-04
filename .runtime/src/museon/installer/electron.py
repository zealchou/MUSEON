"""Electron Dashboard 打包

對應 features/installation.feature Section 4
npm install、electron-builder 打包、安裝到 /Applications
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .models import StepResult, StepStatus


class ElectronPackager:
    """Electron Dashboard 打包與安裝"""

    APP_NAME = "MUSEON.app"
    # electron-builder 可能的輸出目錄
    DIST_DIRS = [
        "dist/mac-arm64",
        "dist/mac",
        "dist/mac-universal",
    ]

    def npm_install(self, electron_dir: Path) -> StepResult:
        """執行 npm install

        Args:
            electron_dir: electron/ 目錄路徑
        """
        try:
            result = subprocess.run(
                ["npm", "install"],
                capture_output=True, text=True,
                cwd=str(electron_dir),
                timeout=300,
            )
            if result.returncode == 0:
                return StepResult(
                    step_name="npm install",
                    status=StepStatus.SUCCESS,
                    message="npm install 完成",
                )
            return StepResult(
                step_name="npm install",
                status=StepStatus.WARNING,
                message=f"npm install 失敗: {result.stderr.strip()[:200]}",
            )
        except subprocess.TimeoutExpired:
            return StepResult(
                step_name="npm install",
                status=StepStatus.WARNING,
                message="npm install 超時（>5 分鐘），跳過 Dashboard",
            )
        except (OSError, FileNotFoundError) as e:
            return StepResult(
                step_name="npm install",
                status=StepStatus.WARNING,
                message=f"npm install 失敗: {e}",
            )

    def build_app(self, electron_dir: Path) -> StepResult:
        """執行 electron-builder 打包

        使用 Popen 串流輸出，避免使用者看到空白畫面。

        Args:
            electron_dir: electron/ 目錄路徑
        """
        try:
            env = {
                **os.environ,
                "CSC_IDENTITY_AUTO_DISCOVERY": "false",
                "ELECTRON_BUILDER_SIGN": "false",
            }

            result = subprocess.run(
                ["npm", "run", "build"],
                capture_output=True, text=True,
                cwd=str(electron_dir),
                timeout=600,
                env=env,
            )
            if result.returncode == 0:
                return StepResult(
                    step_name="Electron 打包",
                    status=StepStatus.SUCCESS,
                    message="Electron 打包完成",
                )
            # WARNING 而非 FAILED — Gateway 不受影響
            return StepResult(
                step_name="Electron 打包",
                status=StepStatus.WARNING,
                message=f"Electron 打包失敗: {result.stderr.strip()[:200]}",
            )
        except subprocess.TimeoutExpired:
            return StepResult(
                step_name="Electron 打包",
                status=StepStatus.WARNING,
                message="Electron 打包超時（>10 分鐘），跳過 Dashboard",
            )
        except (OSError, FileNotFoundError) as e:
            return StepResult(
                step_name="Electron 打包",
                status=StepStatus.WARNING,
                message=f"Electron 打包失敗: {e}",
            )

    def find_app_bundle(self, electron_dir: Path) -> Optional[Path]:
        """搜尋打包產出的 .app bundle

        Args:
            electron_dir: electron/ 目錄路徑

        Returns:
            .app 路徑，或 None
        """
        for dist_dir in self.DIST_DIRS:
            app_path = electron_dir / dist_dir / self.APP_NAME
            if app_path.exists():
                return app_path

        # 嘗試 glob 搜尋
        dist_path = electron_dir / "dist"
        if dist_path.exists():
            for app in dist_path.rglob("*.app"):
                if "MUSEON" in app.name:
                    return app

        return None

    def check_existing_install(self, app_path: Path) -> bool:
        """檢查 /Applications 中是否已有安裝"""
        return app_path.exists()

    def install_to_applications(
        self, source: Path, dest: Path = None
    ) -> StepResult:
        """安裝 .app 到 /Applications

        Args:
            source: .app bundle 路徑
            dest: 目標路徑 (預設 /Applications/MUSEON.app)
        """
        if dest is None:
            dest = Path("/Applications") / self.APP_NAME

        try:
            # 先移除舊版（防止 cp -R 巢狀覆蓋問題）
            if dest.exists():
                subprocess.run(
                    ["rm", "-rf", str(dest)],
                    capture_output=True, text=True, timeout=30,
                )

            # 複製 .app
            result = subprocess.run(
                ["cp", "-R", str(source), str(dest)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                return StepResult(
                    step_name="安裝 Dashboard",
                    status=StepStatus.WARNING,
                    message=f"安裝失敗: {result.stderr.strip()}",
                )

            # 移除 quarantine 屬性
            subprocess.run(
                ["xattr", "-r", "-d", "com.apple.quarantine", str(dest)],
                capture_output=True, text=True, timeout=30,
            )

            # 設定權限
            subprocess.run(
                ["chmod", "-R", "755", str(dest)],
                capture_output=True, text=True, timeout=30,
            )

            return StepResult(
                step_name="安裝 Dashboard",
                status=StepStatus.SUCCESS,
                message=f"已安裝到 {dest}",
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            return StepResult(
                step_name="安裝 Dashboard",
                status=StepStatus.WARNING,
                message=f"安裝 Dashboard 失敗: {e}",
            )
