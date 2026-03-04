"""Anthropic tool_use 工具定義 — v10: 工具永遠開啟，模型自主決定.

基於 Anthropic 官方 tool_use best practice (2025):
- description: 3-4 句，清楚說明用途、觸發時機、回傳內容
- input_schema: JSON Schema，required 最小化
- naming: snake_case，語義清楚

v10 設計原則：
- 工具永遠開啟（移除 should_enable_tools() 啟發式閘門）
- 模型根據使用者需求自主決定是否調用工具
- 包含資料蒐集型、產出型、Shell 執行、MCP 擴充工具
"""

from typing import List, Dict, Any


# ═══════════════════════════════════════
# Anthropic Tool Definitions
# ═══════════════════════════════════════

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "web_search",
        "description": (
            "搜尋網路上的即時資訊。"
            "當使用者詢問最新事件、需要查證事實、或需要即時資料（股價、天氣、新聞等）時使用此工具。"
            "回傳搜尋結果的標題、網址和摘要。每次查詢最多 10 筆結果。"
            "如果搜尋結果不夠詳細，可以接著使用 web_crawl 爬取特定結果的完整內容。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋關鍵字（中文或英文皆可）",
                },
                "language": {
                    "type": "string",
                    "enum": ["zh-TW", "en", "ja"],
                    "description": "搜尋語言偏好，預設繁體中文",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_crawl",
        "description": (
            "爬取並解析指定網頁的完整內容。"
            "當搜尋結果不夠詳細、需要閱讀完整文章、或使用者提供了特定 URL 要求分析時使用此工具。"
            "回傳該頁面的 Markdown 格式全文。適合用於深度閱讀新聞報導、技術文件、部落格文章等。"
            "注意：部分網站可能因反爬蟲機制而無法完整爬取。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要爬取的完整網頁 URL（必須包含 http:// 或 https://）",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "speech_to_text",
        "description": (
            "將語音音檔轉換為文字。支援 mp3、wav、m4a、ogg 格式。"
            "當使用者傳送語音訊息、音檔需要轉錄、或需要分析音訊內容時使用此工具。"
            "回傳轉錄後的完整文字。支援中文、英文、日文等多種語言。"
            "處理時間取決於音檔長度，通常數秒內完成。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "音檔的本地檔案路徑",
                },
                "language": {
                    "type": "string",
                    "description": "音檔語言代碼（zh = 中文, en = 英文, ja = 日文）",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "ocr",
        "description": (
            "辨識圖片中的文字（OCR）。支援 PNG、JPG、BMP 格式。"
            "當使用者傳送截圖、圖片中有需要提取的文字、或需要分析圖片上的資訊時使用此工具。"
            "回傳辨識出的所有文字及其在圖片中的位置座標。"
            "適合用於處理截圖中的文字、名片辨識、文件掃描等場景。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "圖片的本地檔案路徑",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "generate_artifact",
        "description": (
            "產生可交付物檔案並附加到回覆中。"
            "當使用者需要具體產出（計畫書、報告、文案、範本、數據表格）時使用。"
            "支援 Markdown、CSV、HTML 格式。檔案會自動存到 workspace 並透過 Telegram 傳送。"
            "使用時機：使用者說「幫我做/寫/產出/生成」→ 用此工具產出實際檔案。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "檔案名稱（含副檔名，如 business_plan.md, schedule.csv）"},
                "content": {"type": "string", "description": "檔案完整內容"},
                "artifact_type": {
                    "type": "string",
                    "enum": ["document", "template", "data"],
                    "description": "產出類型：document(報告/計畫書), template(範本/SOP), data(數據/排程)"
                },
                "description": {"type": "string", "description": "給使用者的一句話描述（如：IG一週排程表）"}
            },
            "required": ["filename", "content", "artifact_type", "description"]
        }
    },
    # ═══════════════════════════════════════
    # v11 新增工具：認知能力自主取用
    # ═══════════════════════════════════════
    {
        "name": "read_skill",
        "description": (
            "讀取指定認知能力的完整 SKILL.md 指引文件。"
            "當你在 <available_skills> 清單中找到與使用者需求匹配的能力時，"
            "使用此工具讀取該能力的完整操作指引（包含觸發時機、執行步驟、輸出格式等）。"
            "讀取後請按照 SKILL.md 中的指引來組織你的回覆。"
            "注意：只讀取你判斷確實需要的能力，不要一次讀取多個。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": (
                        "能力名稱（如 dse, pdeif, business-12），"
                        "必須是 <available_skills> 中列出的名稱"
                    ),
                },
            },
            "required": ["skill_name"],
        },
    },
    {
        "name": "skill_search",
        "description": (
            "用關鍵字搜尋最相關的認知能力。"
            "當你不確定哪個能力最適合當前任務時，使用此工具搜尋。"
            "回傳最相關的能力名稱、描述和匹配分數，幫助你決定要用 read_skill 讀取哪個能力。"
            "搜尋同時使用關鍵字匹配和語義相似度。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜尋關鍵字或描述（如「品牌定位」「投資分析」「說故事」「情緒支持」）",
                },
                "top_n": {
                    "type": "integer",
                    "description": "回傳前幾個最相關的結果（預設 5，最多 10）",
                },
            },
            "required": ["query"],
        },
    },
    # ═══════════════════════════════════════
    # v10 新增工具
    # ═══════════════════════════════════════
    {
        "name": "shell_exec",
        "description": (
            "在伺服器上執行 Shell 命令。適用於：檔案格式轉換（pandoc md→docx/pdf）、"
            "安裝工具（pip install）、執行腳本、系統操作、查看系統狀態。"
            "安全限制：禁止破壞性命令（rm -rf /、mkfs 等）、timeout 60s。"
            "使用時機：需要執行系統命令、格式轉換、自動化腳本、查看檔案系統時。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要執行的 Shell 命令"},
                "working_dir": {"type": "string", "description": "工作目錄（預設 workspace）"},
                "timeout": {"type": "integer", "description": "超時秒數（預設 60，上限 300）"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "file_write_rich",
        "description": (
            "產生各種格式的檔案並存到 workspace。"
            "支援格式：.md .csv .html .txt .json（直接寫入）、.docx .pdf .pptx .xlsx（需要對應工具已安裝）。"
            "進階格式會先寫入原始內容，再嘗試格式轉換。轉換失敗時回傳原始檔案。"
            "使用時機：需要產出特定格式的文件（計畫書→docx、報表→xlsx、簡報→pptx）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "檔案名稱含副檔名（如 report.docx, data.xlsx）"},
                "content": {"type": "string", "description": "檔案內容（Markdown 或純文字，進階格式會自動轉換）"},
                "description": {"type": "string", "description": "給使用者的一句話描述"}
            },
            "required": ["filename", "content", "description"]
        }
    },
    {
        "name": "mcp_list_servers",
        "description": (
            "列出已連接的 MCP (Model Context Protocol) 伺服器及其提供的工具。"
            "MCP 讓你連接外部服務獲得新能力（如 Google Drive、GitHub、Notion 等）。"
            "使用時機：需要了解目前有哪些外部工具可用，或想要建議使用者連接新的 MCP 伺服器。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "mcp_call_tool",
        "description": (
            "呼叫已連接 MCP 伺服器上的工具。需先用 mcp_list_servers 確認可用工具。"
            "使用時機：需要使用 MCP 伺服器提供的外部能力（如上傳到 Google Drive、操作 GitHub 等）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": "MCP 伺服器名稱"},
                "tool_name": {"type": "string", "description": "工具名稱"},
                "arguments": {"type": "object", "description": "工具參數"}
            },
            "required": ["server", "tool_name"]
        }
    },
    {
        "name": "mcp_add_server",
        "description": (
            "動態新增 MCP 伺服器連接，擴充可用工具。"
            "當現有工具不足以完成任務時，可以建議使用者新增 MCP 伺服器。"
            "使用時機：使用者需要的能力（如 Google Drive、Slack、GitHub 等）目前不支援，"
            "需要引導使用者配置新的 MCP 伺服器來獲得此能力。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "伺服器名稱（如 google-drive, github）"},
                "transport": {"type": "string", "enum": ["stdio", "sse"], "description": "傳輸協議"},
                "command": {"type": "string", "description": "啟動命令（如 npx @anthropic/mcp-server-gdrive）"},
                "env": {"type": "object", "description": "環境變數（如 API keys）"}
            },
            "required": ["name", "transport", "command"]
        }
    },
]

# 工具名稱集合（快速查找）
TOOL_NAMES = frozenset(t["name"] for t in TOOL_DEFINITIONS)


def get_all_tool_definitions(
    dynamic_tools: list = None,
) -> list:
    """v10.2: 合併靜態 + 動態 MCP 工具定義.

    Args:
        dynamic_tools: 從 MCP 伺服器動態發現的工具定義

    Returns:
        完整的工具定義列表（供 Anthropic API 使用）
    """
    all_tools = list(TOOL_DEFINITIONS)  # 複製靜態工具
    if dynamic_tools:
        existing_names = {t["name"] for t in all_tools}
        for tool in dynamic_tools:
            if tool.get("name") not in existing_names:
                all_tools.append(tool)
    return all_tools
