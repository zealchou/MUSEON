"""MUSEON Gateway MCP Server.

暴露 MUSEON 內部狀態給 Claude Code 互動模式，
讓互動對話能感知 Museon 的完整狀態。

啟動方式：
    python -m museon.mcp_server

Claude Code 設定（~/.claude/settings.json）：
    {
      "mcpServers": {
        "museon": {
          "command": "python",
          "args": ["-m", "museon.mcp_server"],
          "env": {
            "MUSEON_HOME": "/Users/ZEALCHOU/MUSEON"
          }
        }
      }
    }
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# MUSEON 資料目錄
MUSEON_HOME = Path(os.getenv("MUSEON_HOME", os.path.expanduser("~/MUSEON")))
DATA_DIR = MUSEON_HOME / "data"


def _read_json(path: Path) -> Dict[str, Any]:
    """安全讀取 JSON 檔案."""
    if not path.exists():
        return {"error": f"File not found: {path.name}"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": str(e)}


def _read_text(path: Path, max_chars: int = 5000) -> str:
    """安全讀取文字檔案."""
    if not path.exists():
        return f"(File not found: {path.name})"
    try:
        text = path.read_text(encoding="utf-8")
        if len(text) > max_chars:
            return text[:max_chars] + f"\n... (truncated, total {len(text)} chars)"
        return text
    except Exception as e:
        return f"(Error: {e})"


# ── MCP Tool Implementations ──


def museon_memory_read(level: str = "L1", key: str = "") -> Dict[str, Any]:
    """讀取 MUSEON 記憶.

    Args:
        level: 記憶層級 — L1_episodic | L2_sem | L3_procedural | L4_meta | L5_identity | L6_collective
        key: 可選的特定記憶 key（檔案名稱不含副檔名）
    """
    memory_dir = DATA_DIR / "memory_v3" / level
    if not memory_dir.exists():
        memory_dir = DATA_DIR / "memory" / level

    if not memory_dir.exists():
        return {"error": f"Memory level {level} not found"}

    if key:
        fp = memory_dir / f"{key}.json"
        if not fp.exists():
            fp = memory_dir / f"{key}.md"
        return _read_json(fp) if fp.suffix == ".json" else {"content": _read_text(fp)}

    # 列出所有記憶
    files = sorted(memory_dir.glob("*"))[:50]
    return {
        "level": level,
        "count": len(files),
        "items": [f.stem for f in files],
    }


def museon_memory_write(level: str, key: str, content: str) -> Dict[str, Any]:
    """寫入 MUSEON 記憶.

    Args:
        level: 記憶層級
        key: 記憶 key
        content: 記憶內容（JSON string 或純文字）
    """
    memory_dir = DATA_DIR / "memory_v3" / level
    memory_dir.mkdir(parents=True, exist_ok=True)

    fp = memory_dir / f"{key}.json"
    try:
        # 嘗試 JSON 格式
        data = json.loads(content)
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except json.JSONDecodeError:
        # 純文字
        fp = memory_dir / f"{key}.md"
        fp.write_text(content, encoding="utf-8")

    return {"status": "written", "path": str(fp)}


def museon_anima_status() -> Dict[str, Any]:
    """取得 ANIMA 情緒狀態."""
    mc = _read_json(DATA_DIR / "ANIMA_MC.json")
    user = _read_json(DATA_DIR / "ANIMA_USER.json")
    return {"mc_anima": mc, "user_anima": user}


def museon_skill_track() -> Dict[str, Any]:
    """取得 Skill 使用統計."""
    stats_dir = DATA_DIR / "_system" / "budget"
    if not stats_dir.exists():
        return {"error": "No budget stats directory"}

    # 讀取今日路由 log
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = stats_dir / f"routing_log_{today}.jsonl"
    if not log_file.exists():
        return {"date": today, "calls": 0, "stats": {}}

    stats = {}
    total = 0
    try:
        for line in log_file.read_text(encoding="utf-8").strip().split("\n"):
            if not line:
                continue
            entry = json.loads(line)
            task_type = entry.get("task_type", "unknown")
            stats[task_type] = stats.get(task_type, 0) + 1
            total += 1
    except Exception as e:
        logger.debug(f"[MCP_SERVER] file stat failed (degraded): {e}")

    return {"date": today, "calls": total, "stats": stats}


def museon_health_status() -> Dict[str, Any]:
    """取得系統健康狀態."""
    status = {
        "museon_home": str(MUSEON_HOME),
        "data_dir_exists": DATA_DIR.exists(),
        "timestamp": datetime.now().isoformat(),
    }

    # PULSE.md
    pulse_file = DATA_DIR / "PULSE.md"
    if pulse_file.exists():
        status["pulse_md_size"] = pulse_file.stat().st_size
        status["pulse_md_mtime"] = datetime.fromtimestamp(
            pulse_file.stat().st_mtime
        ).isoformat()

    # SOUL.md
    soul_file = DATA_DIR / "SOUL.md"
    if soul_file.exists():
        status["soul_md_exists"] = True
    else:
        status["soul_md_exists"] = False

    # Heartbeat
    hb_file = DATA_DIR / "heartbeat.jsonl"
    if hb_file.exists():
        status["heartbeat_size"] = hb_file.stat().st_size

    # Budget
    budget_file = DATA_DIR / "_system" / "budget"
    if budget_file.exists():
        usage_files = list(budget_file.glob("usage_*.json"))
        status["budget_files"] = len(usage_files)

    # Rate Limit Guard
    guard_file = DATA_DIR / "_system" / "budget" / "rate_limit_guard.json"
    if guard_file.exists():
        try:
            guard_data = json.loads(guard_file.read_text(encoding="utf-8"))
            status["rate_limit_level"] = "check_via_guard"
            status["weekly_calls"] = len(guard_data.get("calls", []))
        except Exception as e:
            logger.debug(f"[MCP_SERVER] WEE failed (degraded): {e}")

    return status


def museon_pulse_status() -> Dict[str, Any]:
    """取得心跳狀態."""
    pulse_md = _read_text(DATA_DIR / "PULSE.md", max_chars=3000)
    return {"pulse_md": pulse_md}


def museon_federation_status() -> Dict[str, Any]:
    """取得 Federation 聯邦狀態."""
    return {
        "mode": os.getenv("MUSEON_FEDERATION_MODE", "(not set)"),
        "node_id": os.getenv("MUSEON_NODE_ID", "(not set)"),
        "repo": os.getenv("MUSEON_FEDERATION_REPO", "(not set)"),
        "fed_dir_exists": (DATA_DIR / "_system" / "federation").exists(),
    }


def museon_auth_status() -> Dict[str, Any]:
    """查詢授權系統狀態（配對使用者、待處理授權、策略設定）."""
    try:
        from museon.gateway.authorization import (
            get_authorization_policy,
            get_pairing_manager,
            get_tool_auth_queue,
        )

        pm = get_pairing_manager()
        taq = get_tool_auth_queue()
        policy = get_authorization_policy()

        return {
            "paired_users": pm.list_users(),
            "pending_authorizations": taq.pending_count(),
            "policy": policy.list_policy(),
        }
    except Exception as e:
        return {"error": str(e)}


# ── MCP Protocol ──

TOOLS = {
    "museon_memory_read": {
        "description": "讀取 MUSEON 記憶（L1-L6 層級）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "string",
                    "description": "記憶層級: L1_episodic | L2_sem | L3_procedural | L4_meta | L5_identity | L6_collective",
                    "default": "L1_episodic",
                },
                "key": {
                    "type": "string",
                    "description": "特定記憶 key（可選）",
                    "default": "",
                },
            },
        },
        "handler": museon_memory_read,
    },
    "museon_memory_write": {
        "description": "寫入 MUSEON 記憶",
        "inputSchema": {
            "type": "object",
            "properties": {
                "level": {"type": "string", "description": "記憶層級"},
                "key": {"type": "string", "description": "記憶 key"},
                "content": {"type": "string", "description": "記憶內容"},
            },
            "required": ["level", "key", "content"],
        },
        "handler": museon_memory_write,
    },
    "museon_anima_status": {
        "description": "取得 ANIMA 情緒狀態",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": museon_anima_status,
    },
    "museon_skill_track": {
        "description": "取得 Skill 使用統計",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": museon_skill_track,
    },
    "museon_health_status": {
        "description": "取得 MUSEON 系統健康狀態",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": museon_health_status,
    },
    "museon_pulse_status": {
        "description": "取得心跳 PULSE 狀態",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": museon_pulse_status,
    },
    "museon_federation_status": {
        "description": "取得 Federation 聯邦同步狀態",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": museon_federation_status,
    },
    "museon_auth_status": {
        "description": "查詢授權系統狀態（配對使用者、待處理授權、策略設定）",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": museon_auth_status,
    },
}


def handle_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """處理 MCP JSON-RPC 訊息."""
    method = message.get("method", "")
    msg_id = message.get("id")
    params = message.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "museon-gateway",
                    "version": "1.0.0",
                },
            },
        }

    if method == "notifications/initialized":
        return None  # No response needed

    if method == "tools/list":
        tool_list = []
        for name, info in TOOLS.items():
            tool_list.append({
                "name": name,
                "description": info["description"],
                "inputSchema": info["inputSchema"],
            })
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": tool_list},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in TOOLS:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }

        try:
            handler = TOOLS[tool_name]["handler"]
            result = handler(**arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, ensure_ascii=False, indent=2),
                        }
                    ]
                },
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main():
    """MCP stdio transport — 讀取 stdin JSON-RPC，寫出到 stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_message(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
