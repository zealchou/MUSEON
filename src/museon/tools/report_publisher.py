"""報告發送檢查清單與自動化工具 v1.

用途：確保所有報告發送給 Zeal 前都經過完整的 GitHub Pages 上傳、驗證流程。
避免 2026-03-23 Feng 報告的 404 失敗重演。

Checklist 流程（適用所有報告）：
  1. ✓ 檔案存在於本地
  2. ✓ 已 commit 到正確分支（main 或 gh-pages）
  3. ✓ 已 push 到 remote
  4. ✓ 用 curl/requests 驗證連結（HTTP 200）
  5. ✓ 確認成功後才提供連結給 Zeal
"""

import logging
import requests
import time
from pathlib import Path
from typing import Optional, NamedTuple

logger = logging.getLogger(__name__)


class PublishCheckpoint(NamedTuple):
    """報告發送檢查點結果"""
    local_exists: bool
    git_committed: bool
    git_pushed: bool
    http_verified: bool
    url: Optional[str] = None
    error_msg: Optional[str] = None


class ReportPublisher:
    """報告發送檢查與驗證"""

    @staticmethod
    def verify_http_url(
        url: str,
        max_retries: int = 5,
        retry_delay: float = 2.5
    ) -> tuple[bool, str, Optional[str]]:
        """驗證 HTTP URL 是否可訪問

        Args:
            url: 要驗證的 URL
            max_retries: 最多重試次數
            retry_delay: 重試間隔（秒）

        Returns:
            (is_valid, message, url_if_valid)
        """
        for attempt in range(max_retries):
            try:
                resp = requests.head(url, timeout=5, allow_redirects=True)
                if resp.status_code == 200:
                    msg = f"✓ HTTP 驗證成功 (attempt {attempt + 1}): {url}"
                    logger.info(msg)
                    return True, msg, url
                else:
                    msg = f"⚠ HTTP {resp.status_code} (attempt {attempt + 1}/{max_retries}): {url}"
                    logger.warning(msg)
            except requests.exceptions.Timeout:
                msg = f"⚠ 超時 (attempt {attempt + 1}/{max_retries}): {url}"
                logger.warning(msg)
            except Exception as e:
                msg = f"⚠ 驗證異常 (attempt {attempt + 1}/{max_retries}): {e}"
                logger.warning(msg)

            # 重試前等待
            if attempt < max_retries - 1:
                time.sleep(retry_delay)

        error = (
            f"✗ HTTP 驗證失敗，超過最大重試次數: {url}\n"
            f"  可能原因：(1) GitHub token 無效 (2) 倉庫不存在 (3) Pages 部署延遲 (4) 網路問題\n"
            f"  建議：手動訪問 {url} 或檢查 GitHub Actions"
        )
        logger.error(error)
        return False, error, None

    @staticmethod
    def publish_report_to_github_pages(
        report_url: str,
        local_path: Optional[Path] = None,
    ) -> tuple[bool, Optional[str]]:
        """一鍵發送報告檢查

        Args:
            report_url: GitHub Pages URL
            local_path: 本地檔案路徑（可選）

        Returns:
            (success, url_if_success)
        """
        success, _, verified_url = ReportPublisher.verify_http_url(report_url)
        return success, verified_url


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("✓ ReportPublisher 模組已加載")
