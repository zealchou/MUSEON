"""Tool execution with whitelist and sandbox - Layer 3 security defense.

Based on plan-v7.md Chapter 7 (Layer 3: Execution Environment Isolation):
- All shell commands go through whitelist (no arbitrary execution)
- File system access restricted to workspace directory
- Path traversal prevention (禁止 ../ and symlinks)
- Network access whitelist (only registered APIs)
- Subprocess maximum execution time limit

Security principle: Whitelist thinking - what's not explicitly allowed is forbidden.
"""

from typing import Dict, Any, Optional
from pathlib import Path
import asyncio
import os


class ToolWhitelist:
    """Whitelist of allowed tools and their configurations."""

    def __init__(self):
        """Initialize tool whitelist."""
        # Tools allowed in v1
        self.allowed_tools = {
            # Read-only operations (safe)
            "web_search",
            "read_file",
            "list_directory",
            "get_file_info",
            # Write operations (sandboxed to workspace)
            "write_file",
            "create_directory",
            # Platform APIs (authenticated)
            "instagram_post",
            "telegram_send",
            "line_send",
            # Analysis (CPU-bound, safe)
            "analyze_text",
            "generate_summary",
        }

        # Tools explicitly blocked
        self.blocked_tools = {
            # Dangerous operations
            "execute_code",
            "system_command",
            "eval",
            "exec",
            # Destructive operations
            "delete_file",
            "delete_directory",
            "truncate_file",
            # Network operations (except whitelisted APIs)
            "raw_http_request",
            "ssh_connect",
            "ftp_connect",
            # System operations
            "modify_permissions",
            "change_owner",
            "install_package",
        }

    def is_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed to execute.

        Args:
            tool_name: Name of the tool

        Returns:
            True if allowed, False otherwise
        """
        # Explicitly blocked takes precedence
        if tool_name in self.blocked_tools:
            return False

        # Must be in allowed list
        return tool_name in self.allowed_tools


class PathSandbox:
    """Sandbox for file path operations."""

    def __init__(self, workspace_dir: str = "data/workspace"):
        """Initialize path sandbox.

        Args:
            workspace_dir: Root directory for workspace
        """
        self.workspace_root = Path(workspace_dir).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def sanitize_path(self, user_path: str) -> Optional[Path]:
        """Sanitize a user-provided path.

        Prevents:
        - Path traversal (../)
        - Symlink escapes
        - Access outside workspace

        Args:
            user_path: User-provided path (relative or absolute)

        Returns:
            Sanitized Path object within workspace, or None if invalid
        """
        try:
            # Convert to Path
            path = Path(user_path)

            # If absolute, reject unless within workspace
            if path.is_absolute():
                resolved = path.resolve()
                if not self._is_within_workspace(resolved):
                    return None
                return resolved

            # If relative, resolve relative to workspace
            full_path = (self.workspace_root / path).resolve()

            # Check it's still within workspace (防 symlink escape)
            if not self._is_within_workspace(full_path):
                return None

            return full_path

        except (ValueError, OSError):
            return None

    def _is_within_workspace(self, path: Path) -> bool:
        """Check if path is within workspace.

        Args:
            path: Resolved path

        Returns:
            True if within workspace
        """
        try:
            # Use resolve() to handle symlinks
            resolved_path = path.resolve()
            workspace_root = self.workspace_root.resolve()

            # Check if path is relative to workspace
            resolved_path.relative_to(workspace_root)
            return True

        except (ValueError, OSError):
            return False


class ToolExecutor:
    """Executes tools with security controls."""

    def __init__(
        self,
        workspace_dir: str = "data/workspace",
        timeout: float = 30.0,
    ):
        """Initialize tool executor.

        Args:
            workspace_dir: Workspace directory for file operations
            timeout: Maximum execution time per tool (seconds)
        """
        self.whitelist = ToolWhitelist()
        self.sandbox = PathSandbox(workspace_dir=workspace_dir)
        self.timeout = timeout

    async def execute(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a tool with security checks.

        Args:
            tool_name: Name of tool to execute
            arguments: Tool arguments

        Returns:
            Result dict with success, result/error
        """
        # Step 1: Whitelist check
        if not self.whitelist.is_allowed(tool_name):
            return {
                "success": False,
                "error": f"Tool '{tool_name}' is not allowed",
                "reason": "Tool not in whitelist or explicitly blocked",
            }

        # Step 2: Execute with timeout
        try:
            result = await asyncio.wait_for(
                self._execute_tool(tool_name, arguments),
                timeout=self.timeout,
            )
            return result

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Tool execution timeout",
                "timeout": self.timeout,
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Tool execution failed: {str(e)}",
            }

    async def _execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute tool (internal).

        Args:
            tool_name: Tool name
            arguments: Arguments

        Returns:
            Result dict
        """
        # Route to specific tool implementation
        if tool_name == "web_search":
            return await self._execute_web_search(arguments)
        elif tool_name == "read_file":
            return await self._execute_read_file(arguments)
        elif tool_name == "list_directory":
            return await self._execute_list_directory(arguments)
        elif tool_name == "write_file":
            return await self._execute_write_file(arguments)
        elif tool_name == "create_directory":
            return await self._execute_create_directory(arguments)
        else:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not implemented yet",
            }

    async def _execute_web_search(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute web search.

        Args:
            arguments: Must contain 'query'

        Returns:
            Search results
        """
        query = arguments.get("query")
        if not query:
            return {"success": False, "error": "Missing 'query' parameter"}

        # Placeholder implementation
        # In production, this would call actual search API
        return {
            "success": True,
            "result": {
                "query": query,
                "results": [
                    {"title": "Example result", "snippet": "Sample content"}
                ],
            },
        }

    async def _execute_read_file(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute read file operation.

        Args:
            arguments: Must contain 'path'

        Returns:
            File content
        """
        user_path = arguments.get("path")
        if not user_path:
            return {"success": False, "error": "Missing 'path' parameter"}

        # Sanitize path
        safe_path = self.sandbox.sanitize_path(user_path)
        if safe_path is None:
            return {
                "success": False,
                "error": "Invalid path or path outside workspace",
            }

        # Check file exists
        if not safe_path.exists():
            return {"success": False, "error": "File not found"}

        if not safe_path.is_file():
            return {"success": False, "error": "Path is not a file"}

        # Read file
        try:
            content = safe_path.read_text(encoding="utf-8")
            return {
                "success": True,
                "result": {
                    "path": str(safe_path),
                    "content": content,
                    "size": len(content),
                },
            }

        except Exception as e:
            return {"success": False, "error": f"Failed to read file: {str(e)}"}

    async def _execute_list_directory(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute list directory operation.

        Args:
            arguments: May contain 'path' (defaults to workspace root)

        Returns:
            Directory listing
        """
        user_path = arguments.get("path", ".")

        # Sanitize path
        safe_path = self.sandbox.sanitize_path(user_path)
        if safe_path is None:
            return {
                "success": False,
                "error": "Invalid path or path outside workspace",
            }

        # Check directory exists
        if not safe_path.exists():
            return {"success": False, "error": "Directory not found"}

        if not safe_path.is_dir():
            return {"success": False, "error": "Path is not a directory"}

        # List directory
        try:
            entries = []
            for item in safe_path.iterdir():
                entries.append(
                    {
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None,
                    }
                )

            return {
                "success": True,
                "result": {
                    "path": str(safe_path),
                    "entries": entries,
                    "count": len(entries),
                },
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to list directory: {str(e)}",
            }

    async def _execute_write_file(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute write file operation.

        Args:
            arguments: Must contain 'path' and 'content'

        Returns:
            Write result
        """
        user_path = arguments.get("path")
        content = arguments.get("content")

        if not user_path:
            return {"success": False, "error": "Missing 'path' parameter"}

        if content is None:
            return {"success": False, "error": "Missing 'content' parameter"}

        # Sanitize path
        safe_path = self.sandbox.sanitize_path(user_path)
        if safe_path is None:
            return {
                "success": False,
                "error": "Invalid path or path outside workspace",
            }

        # Write file
        try:
            # Create parent directories if needed
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            safe_path.write_text(content, encoding="utf-8")

            return {
                "success": True,
                "result": {
                    "path": str(safe_path),
                    "size": len(content),
                },
            }

        except Exception as e:
            return {"success": False, "error": f"Failed to write file: {str(e)}"}

    async def _execute_create_directory(
        self, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute create directory operation.

        Args:
            arguments: Must contain 'path'

        Returns:
            Creation result
        """
        user_path = arguments.get("path")

        if not user_path:
            return {"success": False, "error": "Missing 'path' parameter"}

        # Sanitize path
        safe_path = self.sandbox.sanitize_path(user_path)
        if safe_path is None:
            return {
                "success": False,
                "error": "Invalid path or path outside workspace",
            }

        # Create directory
        try:
            safe_path.mkdir(parents=True, exist_ok=True)

            return {
                "success": True,
                "result": {
                    "path": str(safe_path),
                },
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create directory: {str(e)}",
            }
