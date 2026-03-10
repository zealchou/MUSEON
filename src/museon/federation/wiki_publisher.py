"""Wiki Publisher — GitHub Wiki 自動發布引擎.

透過 GitHub REST API 自動將高品質知識資產發布到 GitHub Wiki：
- 訂閱 SHARED_ASSET_PUBLISHED 事件，自動發布
- 支援手動呼叫 publish_page 建立/更新 Wiki 頁面
- 透過 EventBus 發布 WIKI_PUBLISHED 事件

設計原則：
- GitHub Wiki 實際上是一個 Git repo（{repo}.wiki.git）
- 此模組使用 git clone + commit + push 操作 Wiki
- 所有外部操作以 try/except 保護
- 使用 aiohttp 呼叫 GitHub API（檢查 repo 狀態等）
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))


class WikiPublisher:
    """GitHub Wiki 自動發布器.

    透過 Git 操作（clone / pull / commit / push）管理 Wiki 頁面。
    GitHub Wiki 本質上是一個獨立的 Git repo，格式為：
    https://github.com/{owner}/{repo}.wiki.git

    Features:
    - 自動建立/更新 Wiki 頁面（Markdown）
    - 訂閱 SHARED_ASSET_PUBLISHED 事件自動發布
    - 分類目錄管理（knowledge, skill, report 等）
    - 發布 WIKI_PUBLISHED 事件通知下游
    """

    def __init__(
        self,
        github_token: Optional[str] = None,
        repo: Optional[str] = None,
        event_bus: Any = None,
        workspace: Optional[str] = None,
    ) -> None:
        """
        Args:
            github_token: GitHub Personal Access Token
            repo: GitHub repo 全名（owner/repo）
            event_bus: EventBus 實例（可選）
            workspace: 本地工作區路徑（存放 wiki clone）
        """
        self._token = github_token or os.getenv("GITHUB_TOKEN", "")
        self._repo = repo or os.getenv("MUSEON_WIKI_REPO", "")
        self._event_bus = event_bus

        # Wiki git repo 的 clone URL
        self._wiki_url = ""
        if self._repo:
            if self._token:
                self._wiki_url = (
                    f"https://{self._token}@github.com/"
                    f"{self._repo}.wiki.git"
                )
            else:
                self._wiki_url = (
                    f"https://github.com/{self._repo}.wiki.git"
                )

        self._api_url = (
            f"https://api.github.com/repos/{self._repo}"
            if self._repo else ""
        )

        # 本地 wiki 目錄
        if workspace:
            self._wiki_dir = Path(workspace) / "_wiki"
        else:
            default_home = os.getenv("MUSEON_HOME", os.path.expanduser("~/MUSEON"))
            self._wiki_dir = Path(default_home) / "data" / "_system" / "wiki"

        self._wiki_dir.mkdir(parents=True, exist_ok=True)
        self._publish_count: int = 0

        # 訂閱事件
        if self._event_bus is not None:
            self._subscribe()

    def _subscribe(self) -> None:
        """訂閱 EventBus 事件."""
        try:
            from museon.core.event_bus import SHARED_ASSET_PUBLISHED
            self._event_bus.subscribe(
                SHARED_ASSET_PUBLISHED, self._on_asset_published
            )
            logger.info("WikiPublisher subscribed to SHARED_ASSET_PUBLISHED")
        except Exception as e:
            logger.error(f"WikiPublisher subscribe failed: {e}")

    def _on_asset_published(self, data: Optional[Dict] = None) -> None:
        """處理共享資產發布事件 — 自動發布到 Wiki.

        Args:
            data: 事件資料，需含 title, content, category
        """
        if not data:
            return

        title = data.get("title", "")
        content = data.get("content", "")
        category = data.get("category", "knowledge")
        quality = data.get("quality_score", 0)

        # 只發布高品質資產（品質分數 >= 0.7）
        if quality < 0.7:
            logger.debug(
                f"Skipping low-quality asset '{title}' "
                f"(score={quality:.2f})"
            )
            return

        if not title or not content:
            return

        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(
                    self.publish_page(title, content, category)
                )
            else:
                asyncio.run(
                    self.publish_page(title, content, category)
                )
        except Exception as e:
            logger.error(f"Auto-publish to wiki failed: {e}")

    async def publish_page(
        self,
        title: str,
        content: str,
        category: str = "knowledge",
    ) -> Dict[str, Any]:
        """建立或更新 Wiki 頁面.

        Args:
            title: 頁面標題
            content: Markdown 內容
            category: 分類（knowledge, skill, report, reference）

        Returns:
            發布結果字典
        """
        if not self._repo or not self._wiki_url:
            return {"error": "Wiki repo not configured"}

        try:
            # 確保 wiki repo 已 clone
            if not self._ensure_wiki_repo():
                return {"error": "Failed to clone wiki repo"}

            # Pull 最新
            self._git("pull", "--rebase", "--quiet")

            # 準備檔案名稱（sanitize title）
            safe_title = self._sanitize_filename(title)
            page_filename = f"{safe_title}.md"

            # 加入 metadata header
            now = datetime.now(TZ8)
            header = (
                f"<!-- MUSEON Wiki | Category: {category} | "
                f"Updated: {now.strftime('%Y-%m-%d %H:%M')} -->\n\n"
            )
            full_content = header + f"# {title}\n\n{content}\n"

            # 寫入檔案
            page_path = self._wiki_dir / page_filename
            page_path.write_text(full_content, encoding="utf-8")

            # Git add + commit + push
            self._git("add", page_filename)

            commit_msg = (
                f"[MUSEON] Update {category}: {title} "
                f"({now.strftime('%Y-%m-%d')})"
            )
            commit_result = self._git("commit", "-m", commit_msg)

            if commit_result.returncode != 0:
                stdout = commit_result.stdout or ""
                if "nothing to commit" in stdout:
                    return {
                        "status": "no_changes",
                        "title": title,
                        "category": category,
                    }
                logger.warning(f"Wiki commit issue: {commit_result.stderr}")

            push_result = self._git("push", "--quiet")
            if push_result.returncode != 0:
                logger.error(f"Wiki push failed: {push_result.stderr}")
                return {
                    "error": f"Push failed: {push_result.stderr}",
                    "title": title,
                }

            self._publish_count += 1

            result = {
                "status": "published",
                "title": title,
                "category": category,
                "filename": page_filename,
                "wiki_url": f"https://github.com/{self._repo}/wiki/{safe_title}",
                "timestamp": now.isoformat(),
            }

            # 發布 WIKI_PUBLISHED 事件
            try:
                if self._event_bus is not None:
                    from museon.core.event_bus import WIKI_PUBLISHED
                    self._event_bus.publish(WIKI_PUBLISHED, result)
            except Exception as e:
                logger.error(f"EventBus publish WIKI_PUBLISHED failed: {e}")

            logger.info(f"Wiki published: {title} ({category})")
            return result

        except Exception as e:
            logger.error(f"Wiki publish error: {e}")
            return {"error": str(e), "title": title}

    # ── Git Helpers ──

    def _ensure_wiki_repo(self) -> bool:
        """確保 Wiki git repo 已 clone.

        Returns:
            True if repo is ready
        """
        git_dir = self._wiki_dir / ".git"
        if git_dir.exists():
            return True

        if not self._wiki_url:
            logger.warning("Wiki URL not configured")
            return False

        try:
            result = subprocess.run(
                ["git", "clone", self._wiki_url, str(self._wiki_dir)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.error(f"Wiki clone failed: {result.stderr}")
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.error("Wiki clone timed out")
            return False
        except FileNotFoundError:
            logger.error("Git not found in PATH")
            return False

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        """在 wiki 目錄執行 git 命令.

        Args:
            *args: git 子命令與參數

        Returns:
            CompletedProcess 結果
        """
        cmd = ["git"] + list(args)
        try:
            return subprocess.run(
                cmd,
                cwd=str(self._wiki_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            logger.error(f"Git command timed out: {cmd}")
            raise
        except FileNotFoundError:
            logger.error("Git not found in PATH")
            raise

    @staticmethod
    def _sanitize_filename(title: str) -> str:
        """將標題轉為安全的檔案名稱.

        Args:
            title: 原始標題

        Returns:
            安全的檔案名稱（不含副檔名）
        """
        # 替換空白為連字號
        safe = title.strip().replace(" ", "-")
        # 移除非英數/中文/連字號字元
        safe = re.sub(r"[^\w\u4e00-\u9fff-]", "", safe)
        # 縮減連續連字號
        safe = re.sub(r"-{2,}", "-", safe)
        # 截斷長度
        return safe[:100] if safe else "untitled"

    # ── Status ──

    def get_status(self) -> Dict[str, Any]:
        """取得發布器狀態."""
        return {
            "configured": bool(self._repo and self._token),
            "repo": self._repo or "(not configured)",
            "wiki_dir": str(self._wiki_dir),
            "repo_cloned": (self._wiki_dir / ".git").exists(),
            "publish_count": self._publish_count,
            "has_event_bus": self._event_bus is not None,
        }
