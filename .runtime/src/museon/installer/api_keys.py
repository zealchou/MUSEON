"""API Key 設定

對應 features/installation.feature Section 6
管理 .env 檔案中的 API Key
"""

from pathlib import Path

from .models import StepResult, StepStatus


class ApiKeyConfigurator:
    """API Key 設定管理（.env 檔案）"""

    ENV_TEMPLATE = """\
# MUSEON 環境設定
# 請填入你的 API Key

# Telegram Bot Token (從 @BotFather 取得)
# TELEGRAM_BOT_TOKEN=

# Anthropic API Key (從 console.anthropic.com 取得)
# ANTHROPIC_API_KEY=
"""

    def write_key(self, env_file: Path, key_name: str, key_value: str) -> StepResult:
        """寫入或更新一個 API Key 到 .env 檔案

        Args:
            env_file: .env 檔案路徑
            key_name: key 名稱 (e.g. "TELEGRAM_BOT_TOKEN")
            key_value: key 值
        """
        try:
            lines = []
            key_found = False

            if env_file.exists():
                lines = env_file.read_text(encoding="utf-8").splitlines()
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    # 匹配已有的 key（含註解掉的）
                    if stripped.startswith(f"{key_name}=") or stripped.startswith(f"# {key_name}="):
                        lines[i] = f"{key_name}={key_value}"
                        key_found = True
                        break

            if not key_found:
                lines.append(f"{key_name}={key_value}")

            env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

            return StepResult(
                step_name=f"設定 {key_name}",
                status=StepStatus.SUCCESS,
                message=f"已儲存 {key_name}",
            )
        except OSError as e:
            return StepResult(
                step_name=f"設定 {key_name}",
                status=StepStatus.FAILED,
                message=f"寫入 {env_file} 失敗: {e}",
            )

    def create_env_file(self, env_file: Path) -> StepResult:
        """建立空的 .env 檔案（含註解模板）

        Args:
            env_file: .env 檔案路徑
        """
        try:
            if not env_file.exists():
                env_file.write_text(self.ENV_TEMPLATE, encoding="utf-8")

            return StepResult(
                step_name="建立 .env",
                status=StepStatus.SUCCESS,
                message=f"已建立 {env_file}",
            )
        except OSError as e:
            return StepResult(
                step_name="建立 .env",
                status=StepStatus.FAILED,
                message=f"建立 .env 失敗: {e}",
            )

    def has_key(self, env_file: Path, key_name: str) -> bool:
        """檢查 .env 檔案中是否已有指定的 key（且有值）

        Args:
            env_file: .env 檔案路徑
            key_name: key 名稱
        """
        if not env_file.exists():
            return False

        content = env_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            # 排除註解行
            if stripped.startswith("#"):
                continue
            if stripped.startswith(f"{key_name}="):
                value = stripped[len(f"{key_name}="):]
                return len(value.strip()) > 0

        return False
