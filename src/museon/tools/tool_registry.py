"""Tool Registry — 免費工具兵器庫管理.

管理 MUSEON 的自建工具棧：
- Docker 容器工具（SearXNG, Qdrant, PaddleOCR, Firecrawl）
- 原生安裝工具（Whisper.cpp）
- pip 安裝工具（Kokoro TTS）

每個工具獨立管理（安全至上），支援 on/off 開關、健康檢查、
一鍵安裝（Installer 用）、Dashboard 狀態呈現。

必要工具（required=True）：SearXNG, Qdrant, Firecrawl
- 安裝流程必裝，不可關閉
"""

import json
import logging
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))


# ═══════════════════════════════════════════
# 工具設定
# ═══════════════════════════════════════════

@dataclass
class ToolConfig:
    """工具設定."""

    name: str                    # 唯一 ID: searxng, qdrant, ...
    display_name: str            # 儀表板顯示名稱
    emoji: str                   # 圖示
    description: str             # 繁體中文說明
    category: str                # search | perception | memory | crawl | tts
    install_type: str            # docker | native | pip
    cost_tier: str = "cpu"       # cpu | free | paid  （佔用CPU / 免費 / Token付費）
    docker_image: str = ""       # Docker image name
    docker_port: int = 0         # Docker 對外 port
    docker_internal_port: int = 0  # Docker 容器內 port
    ram_mb: int = 0              # 預估 RAM 用量
    health_url: str = ""         # 健康檢查 URL
    install_cmd: str = ""        # 安裝指令
    required: bool = False       # 必要工具：不可關閉、安裝流程必裝
    extra_config: Dict[str, Any] = field(default_factory=dict)


# 7 個工具定義
TOOL_CONFIGS: Dict[str, ToolConfig] = {
    "searxng": ToolConfig(
        name="searxng",
        display_name="SearXNG",
        emoji="🔍",
        description="元搜尋引擎 — 聚合 70+ 搜尋引擎，免費無限搜尋，替代 Brave/Serper",
        category="search",
        install_type="docker",
        cost_tier="cpu",
        docker_image="searxng/searxng:latest",
        docker_port=8888,
        docker_internal_port=8080,
        ram_mb=256,
        health_url="http://127.0.0.1:8888/",
        required=True,
        extra_config={
            "settings_yml": {
                "use_default_settings": True,
                "server": {
                    "secret_key": "museon-searxng-secret",
                    "limiter": False,
                },
                "search": {
                    "safe_search": 0,
                    "formats": ["html", "json"],
                },
            },
        },
    ),
    "qdrant": ToolConfig(
        name="qdrant",
        display_name="Qdrant",
        emoji="📦",
        description="向量記憶庫 — 語義搜尋引擎，讓 AI 擁有長期記憶能力（中英文）",
        category="memory",
        install_type="docker",
        cost_tier="cpu",
        docker_image="qdrant/qdrant",
        docker_port=6333,
        docker_internal_port=6333,
        ram_mb=512,
        health_url="http://127.0.0.1:6333/",
        required=True,
        extra_config={
            "embedding_model": "bge-small-zh-v1.5",
            "note": "搭配 fastembed 做中英文 embedding",
        },
    ),
    "whisper": ToolConfig(
        name="whisper",
        display_name="Whisper.cpp",
        emoji="🎙️",
        description="語音轉文字 — 客戶訪談錄音自動轉逐字稿，支援繁體中文",
        category="perception",
        install_type="native",
        cost_tier="cpu",
        ram_mb=500,
        health_url="",  # 無常駐服務
        install_cmd="git clone https://github.com/ggerganov/whisper.cpp && cd whisper.cpp && make",
        extra_config={
            "model": "large-v3",
            "note": "繁體中文需要 --initial_prompt '以下是繁體中文的逐字稿'",
        },
    ),
    "paddleocr": ToolConfig(
        name="paddleocr",
        display_name="PaddleOCR",
        emoji="📝",
        description="文字辨識 — 名片/發票/文件自動數位化，繁體中文辨識準確",
        category="perception",
        install_type="docker",
        cost_tier="cpu",
        docker_image="987846/paddleocr:latest",
        docker_port=8866,
        docker_internal_port=8866,
        ram_mb=300,
        health_url="http://127.0.0.1:8866/",
        extra_config={
            "model": "chinese_cht",
            "note": "987846/paddleocr 支援 arm64/amd64，OCR-V4 模型",
        },
    ),
    "kokoro": ToolConfig(
        name="kokoro",
        display_name="Kokoro TTS",
        emoji="🔊",
        description="文字轉語音 — 82M 輕量模型，中文語音合成，Agent 語音回覆",
        category="tts",
        install_type="pip",
        cost_tier="free",
        ram_mb=300,
        health_url="",  # 非常駐服務
        install_cmd="kokoro-onnx",  # 套件名稱（由 _install_pip 用 sys.executable -m pip 安裝）
    ),
    "firecrawl": ToolConfig(
        name="firecrawl",
        display_name="Firecrawl",
        emoji="🕷️",
        description="深度爬取 — 網頁全文提取為 Markdown，搭配 SearXNG 完成完整研究流程",
        category="crawl",
        install_type="compose",
        cost_tier="cpu",
        docker_image="ghcr.io/firecrawl/firecrawl:latest",
        docker_port=3002,
        docker_internal_port=3002,
        ram_mb=512,
        health_url="http://127.0.0.1:3002/",
        required=True,
        extra_config={
            "note": "需要 docker compose 啟動多容器（API + Redis + Playwright）",
            "playwright_image": "ghcr.io/firecrawl/playwright-service:latest",
        },
    ),
    "dify": ToolConfig(
        name="dify",
        display_name="Dify",
        emoji="🔄",
        description="工作流引擎 — MUSEON 的手腳，視覺化 AI 工作流建構平台，自動化排程與跨系統整合",
        category="automation",
        install_type="compose",
        cost_tier="cpu",
        docker_image="langgenius/dify-api:latest",
        docker_port=5001,
        docker_internal_port=5001,
        ram_mb=1024,
        health_url="http://127.0.0.1:5001/",
        required=False,
        extra_config={
            "note": "Dify 自架版，需要 docker compose 啟動多容器（API + Web + Worker + PostgreSQL + Redis + Weaviate）",
            "web_port": 3000,
            "web_image": "langgenius/dify-web:latest",
            "github": "https://github.com/langgenius/dify",
            "mcp_support": "v1.6.0+ 雙向 MCP 支援",
            "integration": "MUSEON 透過 REST API 自主執行工作流",
        },
    ),

    # ── Phase 3-5 外部整合工具 ──

    "freshrss": ToolConfig(
        name="freshrss",
        display_name="FreshRSS",
        emoji="📡",
        description="RSS 聚合器 — 自建 RSS 閱讀器，自動追蹤技術部落格與新聞來源",
        category="feed",
        install_type="docker",
        cost_tier="cpu",
        docker_image="freshrss/freshrss:latest",
        docker_port=8080,
        docker_internal_port=80,
        ram_mb=128,
        health_url="http://127.0.0.1:8080/api/greader.php",
        required=False,
        extra_config={
            "note": "FreshRSS 自架版，支援 Google Reader API",
            "github": "https://github.com/FreshRSS/FreshRSS",
            "integration": "MUSEON 透過 RSSAggregator 定期拉取新文章",
        },
    ),

    "stability": ToolConfig(
        name="stability",
        display_name="Stability AI",
        emoji="🎨",
        description="圖片生成 — Stability AI / SDXL API，文字到圖片生成",
        category="generation",
        install_type="api",
        cost_tier="paid",
        health_url="https://api.stability.ai/v1/engines/list",
        required=False,
        extra_config={
            "note": "需要 STABILITY_API_KEY 環境變數",
            "api_base": "https://api.stability.ai",
            "integration": "MUSEON 透過 ImageGenerator 生成圖片",
            "pricing": "依解析度和步數計費",
        },
    ),

    "xtts": ToolConfig(
        name="xtts",
        display_name="XTTS v2",
        emoji="🗣️",
        description="語音克隆 — Coqui XTTS v2 Docker，多語言語音合成與克隆",
        category="tts",
        install_type="docker",
        cost_tier="cpu",
        docker_image="ghcr.io/coqui-ai/xtts-streaming-server:latest",
        docker_port=8020,
        docker_internal_port=80,
        ram_mb=2048,
        health_url="http://127.0.0.1:8020/docs",
        required=False,
        extra_config={
            "note": "XTTS v2 Docker 伺服器，支援語音克隆和多語言合成",
            "github": "https://github.com/coqui-ai/TTS",
            "integration": "MUSEON 透過 VoiceCloner 進行語音合成",
            "gpu_recommended": True,
        },
    ),

    "zotero": ToolConfig(
        name="zotero",
        display_name="Zotero",
        emoji="📚",
        description="文獻管理 — Zotero API 整合，學術文獻匯入與向量搜尋",
        category="research",
        install_type="api",
        cost_tier="free",
        health_url="https://api.zotero.org/keys/current",
        required=False,
        extra_config={
            "note": "需要 ZOTERO_API_KEY 和 ZOTERO_USER_ID 環境變數",
            "api_base": "https://api.zotero.org",
            "integration": "MUSEON 透過 ZoteroBridge 同步文獻到 Qdrant",
        },
    ),
}

# 工具安裝順序（Phase 排序，必要工具優先）
INSTALL_ORDER = [
    "searxng",     # Phase 1 (required)
    "qdrant",      # Phase 1 (required)
    "firecrawl",   # Phase 1 (required)
    "dify",        # Phase 2 (optional, 工作流自動化)
    "whisper",     # Phase 2
    "paddleocr",   # Phase 2
    "kokoro",      # Phase 3
    "freshrss",    # Phase 3 (RSS 聚合)
    "stability",   # Phase 4 (圖片生成, API)
    "xtts",        # Phase 4 (語音克隆)
    "zotero",      # Phase 4 (文獻管理, API)
]

# 分類名稱
CATEGORY_NAMES = {
    "search": "🔍 搜尋能力",
    "perception": "👁️ 感知能力",
    "memory": "📦 記憶能力",
    "crawl": "🕷️ 爬取能力",
    "tts": "🔊 語音能力",
    "feed": "📡 資訊串流",
    "generation": "🎨 生成能力",
    "automation": "🔄 自動化",
    "research": "📚 研究能力",
}


# ═══════════════════════════════════════════
# ToolState — 每個工具的運行狀態
# ═══════════════════════════════════════════

@dataclass
class ToolState:
    """工具運行狀態（持久化到 registry.json）."""

    name: str
    installed: bool = False
    enabled: bool = False
    healthy: bool = False
    last_health_check: str = ""
    last_started: str = ""
    install_progress: int = 0     # 0-100
    install_status: str = ""      # installing | installed | failed | ""
    error_message: str = ""


# ═══════════════════════════════════════════
# ToolRegistry
# ═══════════════════════════════════════════

class ToolRegistry:
    """工具兵器庫管理中心.

    - 管理 6 個工具的安裝、啟停、健康檢查
    - 必要工具（required=True）不可關閉
    - 每個工具獨立 Docker/原生/pip 管理
    - 狀態持久化到 _system/tools/registry.json
    - Docker daemon 自動偵測與啟動（macOS Docker Desktop）
    """

    def __init__(self, workspace: Path, auto_detect: bool = True, event_bus=None) -> None:
        self._workspace = Path(workspace)
        self._event_bus = event_bus
        self._dir = self._workspace / "_system" / "tools"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._state_path = self._dir / "registry.json"
        self._states: Dict[str, ToolState] = {}
        # 追蹤前一次健康狀態（用於偵測變化）
        self._prev_health: Dict[str, bool] = {}
        self._load_states()
        # 首次載入時自動偵測已安裝的工具（純 CPU, 零 Token）
        if auto_detect:
            try:
                self.auto_detect()
            except Exception as e:
                logger.debug(f"Auto-detect skipped: {e}")

    # ── Docker Daemon 管理 ──

    def check_docker_status(self) -> Dict[str, Any]:
        """檢查 Docker 安裝與 daemon 狀態.

        Returns:
            {
                "installed": bool,     # Docker CLI 是否安裝
                "daemon_running": bool, # Docker daemon 是否運行
                "error": str,          # 錯誤訊息
            }
        """
        # 1. 檢查 Docker CLI 是否存在
        try:
            result = subprocess.run(
                ["which", "docker"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return {
                    "installed": False,
                    "daemon_running": False,
                    "error": "Docker 未安裝。請先安裝 Docker Desktop。",
                }
        except Exception:
            return {
                "installed": False,
                "daemon_running": False,
                "error": "無法檢查 Docker 狀態。",
            }

        # 2. 檢查 Docker daemon 是否運行
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return {
                    "installed": True,
                    "daemon_running": True,
                    "error": "",
                }
            else:
                return {
                    "installed": True,
                    "daemon_running": False,
                    "error": "Docker 已安裝但 daemon 未啟動。",
                }
        except subprocess.TimeoutExpired:
            return {
                "installed": True,
                "daemon_running": False,
                "error": "Docker daemon 回應超時。",
            }
        except Exception:
            return {
                "installed": True,
                "daemon_running": False,
                "error": "Docker daemon 未啟動。",
            }

    def ensure_docker_running(self, timeout: int = 60) -> Dict[str, Any]:
        """確保 Docker daemon 正在運行，必要時嘗試自動啟動.

        macOS: 嘗試 `open -a Docker` 啟動 Docker Desktop
        Linux: 嘗試 `systemctl start docker`

        Args:
            timeout: 等待 daemon 啟動的最長秒數

        Returns:
            {"success": bool, "message": str, "was_already_running": bool}
        """
        status = self.check_docker_status()

        if not status["installed"]:
            return {
                "success": False,
                "message": "Docker 未安裝。請至 https://www.docker.com/products/docker-desktop/ 下載安裝。",
                "was_already_running": False,
            }

        if status["daemon_running"]:
            return {
                "success": True,
                "message": "Docker daemon 已在運行。",
                "was_already_running": True,
            }

        # 嘗試自動啟動
        logger.info("Docker daemon not running, attempting to start...")

        import platform
        system = platform.system()

        try:
            if system == "Darwin":
                # macOS: 啟動 Docker Desktop
                subprocess.run(
                    ["open", "-a", "Docker"],
                    capture_output=True, timeout=10,
                )
                logger.info("Sent 'open -a Docker' command")
            elif system == "Linux":
                # Linux: systemctl
                subprocess.run(
                    ["sudo", "systemctl", "start", "docker"],
                    capture_output=True, timeout=15,
                )
                logger.info("Sent 'systemctl start docker' command")
            else:
                return {
                    "success": False,
                    "message": f"不支援在 {system} 上自動啟動 Docker。請手動啟動。",
                    "was_already_running": False,
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"啟動 Docker 失敗：{e}",
                "was_already_running": False,
            }

        # 等待 daemon 就緒
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                result = subprocess.run(
                    ["docker", "info"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    logger.info(
                        f"Docker daemon started in "
                        f"{int(time.time() - start_time)}s"
                    )
                    return {
                        "success": True,
                        "message": f"Docker Desktop 已自動啟動（等待 {int(time.time() - start_time)} 秒）。",
                        "was_already_running": False,
                    }
            except Exception as e:
                logger.debug(f"[TOOL_REGISTRY] docker failed (degraded): {e}")
            time.sleep(3)

        return {
            "success": False,
            "message": f"Docker Desktop 啟動超時（{timeout}秒）。請手動開啟 Docker Desktop。",
            "was_already_running": False,
        }

    def get_docker_dependent_tools(self) -> List[str]:
        """取得所有依賴 Docker 的工具名稱."""
        return [
            name for name, cfg in TOOL_CONFIGS.items()
            if cfg.install_type in ("docker", "compose")
        ]

    # ── 狀態持久化 ──

    def _load_states(self) -> None:
        """從 registry.json 載入狀態."""
        if self._state_path.exists():
            try:
                data = json.loads(
                    self._state_path.read_text(encoding="utf-8")
                )
                for name, s in data.items():
                    # 只載入 TOOL_CONFIGS 中存在的工具（過濾殘留）
                    if name in TOOL_CONFIGS:
                        self._states[name] = ToolState(**s)
                    else:
                        logger.info(
                            f"Skipping stale registry entry: {name}"
                        )
            except Exception:
                logger.warning("Failed to load tool registry, resetting")
                self._states = {}

        # 確保所有工具都有狀態
        for name in TOOL_CONFIGS:
            if name not in self._states:
                self._states[name] = ToolState(name=name)

    def _save_states(self) -> None:
        """持久化狀態到 registry.json."""
        data = {
            name: asdict(state) for name, state in self._states.items()
        }
        self._state_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 公開 API ──

    def list_tools(self) -> List[Dict]:
        """列出所有工具（含設定 + 狀態）."""
        tools = []
        for name in INSTALL_ORDER:
            config = TOOL_CONFIGS[name]
            state = self._states.get(name, ToolState(name=name))
            tools.append({
                "name": name,
                "display_name": config.display_name,
                "emoji": config.emoji,
                "description": config.description,
                "category": config.category,
                "category_name": CATEGORY_NAMES.get(config.category, ""),
                "install_type": config.install_type,
                "cost_tier": config.cost_tier,
                "ram_mb": config.ram_mb,
                "port": config.docker_port,
                "required": config.required,
                "installed": state.installed,
                "enabled": state.enabled,
                "healthy": state.healthy,
                "last_health_check": state.last_health_check,
                "install_progress": state.install_progress,
                "install_status": state.install_status,
                "error_message": state.error_message,
            })
        return tools

    def get_tool(self, name: str) -> Optional[Dict]:
        """取得單一工具詳細資訊."""
        config = TOOL_CONFIGS.get(name)
        if not config:
            return None
        state = self._states.get(name, ToolState(name=name))
        return {
            **asdict(config),
            **asdict(state),
            "category_name": CATEGORY_NAMES.get(config.category, ""),
        }

    def get_status_summary(self) -> Dict:
        """取得彙總狀態（Dashboard 用）."""
        total = len(TOOL_CONFIGS)
        installed = sum(
            1 for s in self._states.values() if s.installed
        )
        enabled = sum(
            1 for s in self._states.values() if s.enabled
        )
        healthy = sum(
            1 for s in self._states.values() if s.healthy
        )
        docker_count = sum(
            1 for name, s in self._states.items()
            if s.installed and TOOL_CONFIGS.get(name, ToolConfig(
                name="", display_name="", emoji="", description="",
                category="", install_type=""
            )).install_type == "docker"
        )
        native_count = installed - docker_count
        total_ram = sum(
            TOOL_CONFIGS[name].ram_mb
            for name, s in self._states.items()
            if s.enabled
        )
        return {
            "total": total,
            "installed": installed,
            "enabled": enabled,
            "healthy": healthy,
            "docker_count": docker_count,
            "native_count": native_count,
            "total_ram_mb": total_ram,
        }

    def toggle_tool(self, name: str, enabled: bool) -> Dict:
        """切換工具 on/off.

        ON = 啟動容器/服務
        OFF = 停止容器/服務
        必要工具（required=True）禁止關閉。
        """
        if name not in TOOL_CONFIGS:
            return {"success": False, "reason": "tool_not_found"}

        config = TOOL_CONFIGS[name]

        # 必要工具禁止關閉
        if config.required and not enabled:
            return {
                "success": False,
                "reason": "required_tool_cannot_disable",
                "name": name,
            }

        state = self._states.get(name, ToolState(name=name))
        if not state.installed:
            return {"success": False, "reason": "not_installed"}

        old_enabled = state.enabled

        if enabled and not old_enabled:
            # 啟動
            ok = self._start_tool(name, config)
            state.enabled = ok
            if ok:
                state.last_started = datetime.now(TZ_TAIPEI).isoformat()
        elif not enabled and old_enabled:
            # 停止
            self._stop_tool(name, config)
            state.enabled = False
            state.healthy = False

        self._states[name] = state
        self._save_states()
        return {
            "success": True,
            "name": name,
            "enabled": state.enabled,
        }

    def check_health(self, name: str) -> Dict:
        """健康檢查單一工具（含狀態變化偵測 + EventBus 通知）."""
        if name not in TOOL_CONFIGS:
            return {"name": name, "healthy": False, "reason": "unknown_tool"}

        config = TOOL_CONFIGS[name]
        state = self._states.get(name, ToolState(name=name))

        if not state.installed or not state.enabled:
            state.healthy = False
            self._states[name] = state
            self._save_states()
            return {
                "name": name,
                "healthy": False,
                "reason": "not_running",
            }

        was_healthy = self._prev_health.get(name, True)
        healthy = self._check_tool_health(name, config)
        state.healthy = healthy
        state.last_health_check = datetime.now(TZ_TAIPEI).isoformat()
        self._states[name] = state
        self._save_states()

        # 偵測狀態變化 → 發布 EventBus 事件
        if self._event_bus and was_healthy != healthy:
            try:
                from museon.core.event_bus import (
                    TOOL_HEALTH_CHANGED,
                    TOOL_DEGRADED,
                    TOOL_RECOVERED,
                )
                self._event_bus.publish(TOOL_HEALTH_CHANGED, {
                    "tool_name": name,
                    "was_healthy": was_healthy,
                    "is_healthy": healthy,
                    "required": config.required,
                })
                if not healthy:
                    self._event_bus.publish(TOOL_DEGRADED, {
                        "tool_name": name,
                        "display_name": config.display_name,
                        "required": config.required,
                    })
                    logger.warning(
                        f"Tool degraded: {config.display_name} ({name})"
                    )
                else:
                    self._event_bus.publish(TOOL_RECOVERED, {
                        "tool_name": name,
                        "display_name": config.display_name,
                    })
                    logger.info(
                        f"Tool recovered: {config.display_name} ({name})"
                    )
            except Exception as e:
                logger.debug(f"Tool health event publish failed: {e}")

        self._prev_health[name] = healthy

        return {"name": name, "healthy": healthy}

    def check_all_health(self) -> Dict:
        """健康檢查所有已啟用工具."""
        results = {}
        for name in TOOL_CONFIGS:
            state = self._states.get(name, ToolState(name=name))
            if state.installed and state.enabled:
                results[name] = self.check_health(name)
            else:
                results[name] = {
                    "name": name,
                    "healthy": False,
                    "reason": "disabled",
                }
        return results

    def install_tool(
        self,
        name: str,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> Dict:
        """安裝單一工具.

        Docker/Compose 工具會自動檢查並嘗試啟動 Docker daemon。

        Args:
            name: 工具名稱
            progress_cb: 進度回調 (percent, message)
        """
        if name not in TOOL_CONFIGS:
            return {"success": False, "reason": "tool_not_found"}

        config = TOOL_CONFIGS[name]
        state = self._states.get(name, ToolState(name=name))

        def _progress(pct: int, msg: str):
            state.install_progress = pct
            state.install_status = "installing"
            self._states[name] = state
            self._save_states()
            if progress_cb:
                progress_cb(pct, msg)

        _progress(0, f"開始安裝 {config.display_name}...")

        try:
            # Docker/Compose 工具：先確保 Docker daemon 運行
            if config.install_type in ("docker", "compose"):
                _progress(2, "檢查 Docker 環境...")
                docker_result = self.ensure_docker_running(timeout=60)
                if not docker_result["success"]:
                    state.install_status = "failed"
                    state.error_message = docker_result["message"]
                    self._states[name] = state
                    self._save_states()
                    return {
                        "success": False,
                        "name": name,
                        "installed": state.installed,
                        "enabled": state.enabled,
                        "error": docker_result["message"],
                        "docker_issue": True,
                    }
                if not docker_result["was_already_running"]:
                    _progress(5, docker_result["message"])

            if config.install_type == "docker":
                ok = self._install_docker(name, config, _progress)
            elif config.install_type == "compose":
                ok = self._install_compose(name, config, _progress)
            elif config.install_type == "native":
                ok = self._install_native(name, config, _progress)
            elif config.install_type == "pip":
                ok = self._install_pip(name, config, _progress)
            else:
                ok = False

            if ok:
                state.installed = True
                state.enabled = True
                state.install_status = "installed"
                state.install_progress = 100
                state.error_message = ""
                state.last_started = datetime.now(TZ_TAIPEI).isoformat()
            else:
                state.install_status = "failed"
                if not state.error_message:
                    state.error_message = "安裝失敗"
        except Exception as e:
            state.install_status = "failed"
            state.error_message = str(e)[:200]
            logger.error(f"Install {name} failed: {e}")
            ok = False

        self._states[name] = state
        self._save_states()
        return {
            "success": ok,
            "name": name,
            "installed": state.installed,
            "enabled": state.enabled,
        }

    def get_install_order(self) -> List[str]:
        """取得安裝順序."""
        return list(INSTALL_ORDER)

    def get_not_installed(self) -> List[str]:
        """取得未安裝工具."""
        return [
            name for name in INSTALL_ORDER
            if not self._states.get(name, ToolState(name=name)).installed
        ]

    def get_required_tools(self) -> List[str]:
        """取得必要工具名單."""
        return [
            name for name, cfg in TOOL_CONFIGS.items()
            if cfg.required
        ]

    # ── Docker 管理 ──

    def _install_docker(
        self,
        name: str,
        config: ToolConfig,
        progress_cb: Callable,
    ) -> bool:
        """Docker 安裝流程."""
        progress_cb(10, f"拉取 Docker Image: {config.docker_image}")

        try:
            # Pull image
            result = subprocess.run(
                ["docker", "pull", config.docker_image],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                logger.error(f"Docker pull failed: {result.stderr}")
                return False

            progress_cb(50, "建立並啟動容器")

            # Remove existing container if any
            subprocess.run(
                ["docker", "rm", "-f", f"museon-{name}"],
                capture_output=True, timeout=30,
            )

            # Run container
            run_args = [
                "docker", "run", "-d",
                "--name", f"museon-{name}",
                "--restart", "unless-stopped",
                "-p", f"127.0.0.1:{config.docker_port}:{config.docker_internal_port}",
            ]

            # Qdrant: 加 volume
            if name == "qdrant":
                run_args.extend([
                    "-v", f"museon-qdrant-data:/qdrant/storage",
                    "-p", f"127.0.0.1:6334:6334",
                ])

            # SearXNG: 設定 JSON format
            if name == "searxng":
                settings_dir = self._dir / "searxng"
                settings_dir.mkdir(exist_ok=True)
                settings_file = settings_dir / "settings.yml"
                if not settings_file.exists():
                    import yaml
                    yaml_content = (
                        "use_default_settings: true\n"
                        "server:\n"
                        "  secret_key: \"museon-searxng-secret\"\n"
                        "  limiter: false\n"
                        "search:\n"
                        "  safe_search: 0\n"
                        "  formats:\n"
                        "    - html\n"
                        "    - json\n"
                    )
                    settings_file.write_text(yaml_content, encoding="utf-8")
                run_args.extend([
                    "-v", f"{settings_dir}:/etc/searxng",
                ])

            run_args.append(config.docker_image)

            result = subprocess.run(
                run_args,
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                logger.error(f"Docker run failed: {result.stderr}")
                return False

            progress_cb(80, "等待服務啟動")

            # 等待健康（最多 30 秒）
            if config.health_url:
                healthy = self._wait_for_health(config.health_url, timeout=30)
                if not healthy:
                    logger.warning(
                        f"{name} started but health check failed"
                    )

            progress_cb(100, "安裝完成")
            return True

        except subprocess.TimeoutExpired:
            logger.error(f"Docker install {name} timed out")
            return False
        except FileNotFoundError:
            logger.error("Docker CLI not found — is Docker installed?")
            return False
        except OSError as e:
            if "Cannot connect" in str(e) or "connection refused" in str(e).lower():
                logger.error(f"Docker daemon not running: {e}")
            else:
                logger.error(f"Docker OS error: {e}")
            return False

    def _install_native(
        self,
        name: str,
        config: ToolConfig,
        progress_cb: Callable,
    ) -> bool:
        """原生安裝流程."""
        progress_cb(10, f"安裝 {config.display_name}")

        if name == "whisper":
            return self._install_whisper(progress_cb)

        return False

    def _install_whisper(self, progress_cb: Callable) -> bool:
        """安裝 Whisper.cpp（原生編譯，需要 cmake）."""
        try:
            whisper_dir = self._workspace / "_tools" / "whisper.cpp"

            # Step 1: 確保 cmake 已安裝
            progress_cb(10, "檢查 cmake")
            cmake_check = subprocess.run(
                ["which", "cmake"],
                capture_output=True, text=True, timeout=10,
            )
            if cmake_check.returncode != 0:
                progress_cb(15, "安裝 cmake（brew install cmake）")
                result = subprocess.run(
                    ["brew", "install", "cmake"],
                    capture_output=True, text=True, timeout=300,
                )
                if result.returncode != 0:
                    logger.error(
                        f"cmake install failed: {result.stderr}"
                    )
                    return False

            # Step 2: Clone repo
            if not whisper_dir.exists():
                progress_cb(20, "Clone whisper.cpp")
                whisper_dir.parent.mkdir(parents=True, exist_ok=True)
                result = subprocess.run(
                    ["git", "clone", "--depth", "1",
                     "https://github.com/ggerganov/whisper.cpp",
                     str(whisper_dir)],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    logger.error(
                        f"Whisper clone failed: {result.stderr}"
                    )
                    return False

            # Step 3: Build with cmake
            progress_cb(40, "編譯 whisper.cpp（cmake）")
            build_dir = whisper_dir / "build"
            result = subprocess.run(
                ["cmake", "-B", "build"],
                cwd=str(whisper_dir),
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                logger.error(f"cmake configure failed: {result.stderr}")
                return False

            result = subprocess.run(
                ["cmake", "--build", "build", "--config", "Release",
                 "-j"],
                cwd=str(whisper_dir),
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                logger.error(f"cmake build failed: {result.stderr}")
                return False

            # Step 4: Download large-v3 model
            progress_cb(70, "下載 large-v3 模型")
            dl_script = whisper_dir / "models" / "download-ggml-model.sh"
            if dl_script.exists():
                subprocess.run(
                    ["bash", str(dl_script), "large-v3"],
                    cwd=str(whisper_dir),
                    capture_output=True, text=True, timeout=600,
                )

            progress_cb(100, "Whisper.cpp 安裝完成")
            return True

        except Exception as e:
            logger.error(f"Whisper install error: {e}")
            return False

    def _install_pip(
        self,
        name: str,
        config: ToolConfig,
        progress_cb: Callable,
    ) -> bool:
        """pip 安裝流程（使用 sys.executable -m pip）."""
        pkg_name = config.install_cmd  # 套件名稱
        progress_cb(10, f"pip install {pkg_name}")

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg_name],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                logger.error(f"pip install failed: {result.stderr}")
                return False

            progress_cb(100, "安裝完成")
            return True

        except Exception as e:
            logger.error(f"pip install error: {e}")
            return False

    def _install_compose(
        self,
        name: str,
        config: ToolConfig,
        progress_cb: Callable,
    ) -> bool:
        """Docker Compose 安裝流程（多容器服務）."""
        if name == "firecrawl":
            return self._install_firecrawl_compose(progress_cb)
        return False

    def _install_firecrawl_compose(
        self, progress_cb: Callable
    ) -> bool:
        """安裝 Firecrawl（docker compose 多容器）.

        經驗教訓：
        - ghcr.io stale credentials 會導致 public image denied
        - org 從 mendableai → firecrawl（2024 年底改名）
        - playwright-service 有獨立 image
        """
        try:
            # 清除 ghcr.io 過期憑證（避免 denied 錯誤）
            subprocess.run(
                ["docker", "logout", "ghcr.io"],
                capture_output=True, timeout=10,
            )

            compose_dir = self._dir / "firecrawl"
            compose_dir.mkdir(parents=True, exist_ok=True)
            compose_file = compose_dir / "docker-compose.yml"

            progress_cb(10, "建立 Firecrawl compose 設定")

            # 產生 docker-compose.yml（2026-02: org 改名 mendableai → firecrawl）
            compose_content = (
                "services:\n"
                "  redis:\n"
                "    image: redis:7-alpine\n"
                "    container_name: museon-firecrawl-redis\n"
                "    restart: unless-stopped\n"
                "    networks: [firecrawl]\n"
                "  playwright:\n"
                "    image: ghcr.io/firecrawl/playwright-service:latest\n"
                "    container_name: museon-firecrawl-playwright\n"
                "    restart: unless-stopped\n"
                "    command: ['node', 'dist/server.js']\n"
                "    environment:\n"
                "      - PORT=3000\n"
                "    networks: [firecrawl]\n"
                "  api:\n"
                "    image: ghcr.io/firecrawl/firecrawl:latest\n"
                "    container_name: museon-firecrawl-api\n"
                "    restart: unless-stopped\n"
                "    environment:\n"
                "      - REDIS_URL=redis://redis:6379\n"
                "      - PLAYWRIGHT_MICROSERVICE_URL=http://playwright:3000\n"
                "      - USE_DB_AUTHENTICATION=false\n"
                "      - PORT=3002\n"
                "      - HOST=0.0.0.0\n"
                "      - NUM_WORKERS_PER_QUEUE=1\n"
                "      - SELF_HOSTED_WEBHOOK_SECRET=museon\n"
                "    ports:\n"
                "      - '127.0.0.1:3002:3002'\n"
                "    depends_on: [redis, playwright]\n"
                "    command: ['node', '--max-old-space-size=8192', 'dist/src/index.js']\n"
                "    networks: [firecrawl]\n"
                "  worker:\n"
                "    image: ghcr.io/firecrawl/firecrawl:latest\n"
                "    container_name: museon-firecrawl-worker\n"
                "    restart: unless-stopped\n"
                "    environment:\n"
                "      - REDIS_URL=redis://redis:6379\n"
                "      - PLAYWRIGHT_MICROSERVICE_URL=http://playwright:3000\n"
                "      - USE_DB_AUTHENTICATION=false\n"
                "      - NUM_WORKERS_PER_QUEUE=1\n"
                "    depends_on: [redis, playwright]\n"
                "    command: ['node', '--max-old-space-size=8192', 'dist/src/services/queue-worker.js']\n"
                "    networks: [firecrawl]\n"
                "networks:\n"
                "  firecrawl:\n"
                "    driver: bridge\n"
            )
            compose_file.write_text(compose_content, encoding="utf-8")

            progress_cb(20, "拉取 Firecrawl Docker Image")
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file),
                 "pull"],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                logger.error(
                    f"Firecrawl compose pull failed: {result.stderr}"
                )
                return False

            progress_cb(70, "啟動 Firecrawl 服務")
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file),
                 "up", "-d"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                logger.error(
                    f"Firecrawl compose up failed: {result.stderr}"
                )
                return False

            progress_cb(85, "等待服務啟動")
            healthy = self._wait_for_health(
                "http://127.0.0.1:3002/", timeout=30
            )
            if not healthy:
                logger.warning(
                    "Firecrawl started but health check failed"
                )

            progress_cb(100, "Firecrawl 安裝完成")
            return True

        except subprocess.TimeoutExpired:
            logger.error("Firecrawl compose install timed out")
            return False
        except Exception as e:
            logger.error(f"Firecrawl compose error: {e}")
            return False

    def _start_tool(self, name: str, config: ToolConfig) -> bool:
        """啟動工具."""
        if config.install_type == "docker":
            try:
                result = subprocess.run(
                    ["docker", "start", f"museon-{name}"],
                    capture_output=True, text=True, timeout=30,
                )
                return result.returncode == 0
            except Exception:
                return False
        elif config.install_type == "compose":
            return self._compose_action(name, "up", "-d")
        return True  # pip / whisper: 非常駐

    def _stop_tool(self, name: str, config: ToolConfig) -> bool:
        """停止工具."""
        if config.install_type == "docker":
            try:
                result = subprocess.run(
                    ["docker", "stop", f"museon-{name}"],
                    capture_output=True, text=True, timeout=30,
                )
                return result.returncode == 0
            except Exception:
                return False
        elif config.install_type == "compose":
            return self._compose_action(name, "down")
        return True

    def _compose_action(self, name: str, *args: str) -> bool:
        """對 compose 服務執行指令."""
        compose_file = self._dir / name / "docker-compose.yml"
        if not compose_file.exists():
            return False
        try:
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file),
                 *args],
                capture_output=True, text=True, timeout=60,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _check_tool_health(self, name: str, config: ToolConfig) -> bool:
        """檢查工具健康狀態."""
        if not config.health_url:
            # 無常駐服務的工具：檢查是否安裝
            if config.install_type == "docker":
                return self._check_docker_running(name)
            elif config.install_type == "compose":
                return self._check_compose_running(name)
            elif name == "whisper":
                # 新版 cmake build 產出在 build/bin/
                whisper_dir = (
                    self._workspace / "_tools" / "whisper.cpp"
                )
                return (
                    (whisper_dir / "build" / "bin" / "whisper-cli").exists()
                    or (whisper_dir / "main").exists()  # 舊版相容
                )
            return True  # pip installed

        try:
            import urllib.request
            import urllib.error
            req = urllib.request.Request(
                config.health_url, method="GET"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status < 500
        except urllib.error.HTTPError as e:
            # 4xx = 伺服器活著（只是端點方法不對），仍視為健康
            return e.code < 500
        except Exception:
            return False

    def _check_compose_running(self, name: str) -> bool:
        """檢查 compose 服務是否運行."""
        compose_file = self._dir / name / "docker-compose.yml"
        if not compose_file.exists():
            return False
        try:
            result = subprocess.run(
                ["docker", "compose", "-f", str(compose_file),
                 "ps", "--format", "json"],
                capture_output=True, text=True, timeout=10,
            )
            return (
                result.returncode == 0
                and "running" in result.stdout.lower()
            )
        except Exception:
            return False

    def _check_docker_running(self, name: str) -> bool:
        """檢查 Docker 容器是否在運行."""
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}",
                 f"museon-{name}"],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout.strip() == "true"
        except Exception:
            return False

    def _wait_for_health(
        self, url: str, timeout: int = 30
    ) -> bool:
        """等待服務健康."""
        import urllib.error
        import urllib.request

        start = time.time()
        while time.time() - start < timeout:
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status < 500:
                        return True
            except urllib.error.HTTPError as e:
                if e.code < 500:
                    return True  # 4xx = 伺服器已啟動
            except Exception as e:
                logger.debug(f"[TOOL_REGISTRY] file stat failed (degraded): {e}")
            time.sleep(2)
        return False

    # ── 自動偵測已安裝工具 ──

    def auto_detect(self) -> Dict:
        """自動偵測已安裝的工具（首次啟動用）."""
        detected = {}

        for name, config in TOOL_CONFIGS.items():
            state = self._states.get(name, ToolState(name=name))
            was_installed = state.installed

            if config.install_type == "docker":
                # 檢查容器是否存在
                try:
                    result = subprocess.run(
                        ["docker", "inspect", f"museon-{name}"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode == 0:
                        state.installed = True
                        state.enabled = self._check_docker_running(name)
                        if state.enabled:
                            state.healthy = self._check_tool_health(
                                name, config
                            )
                except Exception as e:
                    logger.debug(f"[TOOL_REGISTRY] health check failed (degraded): {e}")

            elif config.install_type == "compose":
                running = self._check_compose_running(name)
                if running:
                    state.installed = True
                    state.enabled = True
                    state.healthy = self._check_tool_health(
                        name, config
                    )

            elif name == "whisper":
                whisper_dir = (
                    self._workspace / "_tools" / "whisper.cpp"
                )
                if (
                    (whisper_dir / "build" / "bin" / "whisper-cli").exists()
                    or (whisper_dir / "main").exists()
                ):
                    state.installed = True
                    state.enabled = True  # 非常駐工具，偵測到即啟用
                    state.healthy = True  # binary 存在 = 健康

            elif config.install_type == "pip":
                # pip 套件：嘗試 import 偵測
                pkg_name = config.install_cmd.replace("-", "_")
                try:
                    __import__(pkg_name)
                    state.installed = True
                    state.enabled = True  # 非常駐工具，偵測到即啟用
                    state.healthy = True  # 可 import = 健康
                except ImportError as e:
                    logger.debug(f"[TOOL_REGISTRY] module import failed (degraded): {e}")

            if state.installed and not was_installed:
                detected[name] = True

            self._states[name] = state

        self._save_states()
        return detected
