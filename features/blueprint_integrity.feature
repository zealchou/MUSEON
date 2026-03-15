Feature: 工程藍圖完整性
  作為 MUSEON 的架構維護者
  我需要驗證四張工程藍圖（接頭圖、爆炸圖、神經圖、水電圖）
  涵蓋所有已知的模組、共享狀態和跨系統依賴
  以確保「修 A 不壞 B」的施工安全

  Background:
    Given 四張工程藍圖已載入

  # ═══════════════════════════════════════
  # 🔗 接頭圖（joint-map.md）完整性
  # ═══════════════════════════════════════

  Scenario: 接頭圖 — ANIMA_MC.json 所有寫入者皆已登記
    When 掃描 ANIMA_MC.json 的實際寫入模組
    Then 接頭圖應列出 "onboarding/ceremony.py" 為 ANIMA_MC 寫入者
    And 接頭圖應列出 "guardian/daemon.py" 為 ANIMA_MC 讀寫者

  Scenario: 接頭圖 — ANIMA_USER.json 所有寫入者皆已登記
    When 掃描 ANIMA_USER.json 的實際寫入模組
    Then 接頭圖應列出 "onboarding/ceremony.py" 為 ANIMA_USER 寫入者
    And 接頭圖應列出 "guardian/daemon.py" 為 ANIMA_USER 寫入者

  Scenario: 接頭圖 — Evolution 共享檔案已登記
    When 掃描 evolution 目錄的共享檔案寫入
    Then 接頭圖應包含共享狀態 "velocity_log.jsonl"
    And 接頭圖應包含共享狀態 "tuning_audit.jsonl"
    And 接頭圖應包含共享狀態 "trigger_configs.json"
    And 接頭圖應包含共享狀態 "tool_muscles.json"

  Scenario: 接頭圖 — 所有 CRITICAL 共享狀態的寫入者數量正確
    When 檢查 CRITICAL 區域的寫入者清單
    Then ANIMA_MC.json 的寫入者應至少有 6 個模組
    And ANIMA_USER.json 的寫入者應至少有 3 個模組

  # ═══════════════════════════════════════
  # 💥 爆炸圖（blast-radius.md）完整性
  # ═══════════════════════════════════════

  Scenario: 爆炸圖 — Evolution 模組影響半徑已登記
    When 掃描 evolution 目錄的跨模組依賴
    Then 爆炸圖應包含模組 "evolution/outward_trigger.py"
    And 爆炸圖應包含模組 "evolution/wee_engine.py"
    And 爆炸圖應包含模組 "evolution/evolution_velocity.py"

  Scenario: 爆炸圖 — Guardian 模組影響半徑已登記
    When 掃描 guardian 目錄的跨模組依賴
    Then 爆炸圖應包含模組 "guardian/daemon.py"

  Scenario: 爆炸圖 — 模組組 G1-G6 完整性
    When 檢查模組組定義
    Then 應存在模組組 "G1" 包含 "anima_tracker"
    And 應存在模組組 "G2" 包含 "curiosity_router"
    And 應存在模組組 "G6" 包含 "daemon"

  # ═══════════════════════════════════════
  # 🧠 神經圖（system-topology.md）完整性
  # ═══════════════════════════════════════

  Scenario: 神經圖 — S9 Evolution 系統節點已登記
    When 掃描 evolution 系統的實際模組
    Then 神經圖應包含節點 "outward-trigger"
    And 神經圖應包含節點 "intention-radar"
    And 神經圖應包含節點 "digest-engine"
    And 神經圖應包含節點 "evolution-velocity"
    And 神經圖應包含節點 "research-engine"

  Scenario: 神經圖 — S4 Governance 應包含 security 和 guardian
    When 掃描 governance 群組的實際模組
    Then 神經圖應包含節點 "guardian"
    And 神經圖應包含節點 "security"

  Scenario: 神經圖 — S1 Brain 應包含 onboarding 和 multiagent
    When 掃描 agent 群組的實際模組
    Then 神經圖應包含節點 "onboarding"
    And 神經圖應包含節點 "multiagent"

  Scenario: 神經圖 — S10 Tools 系統節點已登記
    When 掃描 tools 系統的實際模組
    Then 神經圖應包含節點 "tool-registry"
    And 神經圖應包含節點 "tool-discovery"

  Scenario: 神經圖 — Evolution 事件鏈連線已登記
    When 掃描 evolution 事件鏈的連線
    Then 神經圖應包含連線從 "outward-trigger" 到 "intention-radar"
    And 神經圖應包含連線從 "intention-radar" 到 "research-engine"
    And 神經圖應包含連線從 "research-engine" 到 "digest-engine"

  Scenario: 神經圖 — 所有群組 Hub 皆連接 event-bus
    When 檢查群組 Hub 與 event-bus 的連線
    Then 每個群組 Hub 應至少有 1 條與 event-bus 的連線

  # ═══════════════════════════════════════
  # 🔧 水電圖（persistence-contract.md）完整性
  # ═══════════════════════════════════════

  Scenario: 水電圖 — Evolution 儲存位置已登記
    When 掃描 evolution 目錄的資料寫入
    Then 水電圖應包含資料路徑 "velocity_log"
    And 水電圖應包含資料路徑 "tuning_audit"
    And 水電圖應包含資料路徑 "tuned_parameters"

  Scenario: 水電圖 — Guardian 儲存位置已登記
    When 掃描 guardian 目錄的資料寫入
    Then 水電圖應包含資料路徑 "guardian"
    And 水電圖應包含資料路徑 "repair_log"

  Scenario: 水電圖 — 每個寫入必有消費者
    When 檢查寫入消費配對表
    Then 不應存在未被標記的 Dead Write

  # ═══════════════════════════════════════
  # 🔄 第二輪全面覆蓋驗證
  # ═══════════════════════════════════════

  Scenario: 接頭圖 — LLM 預算共享狀態已登記
    When 掃描 evolution 目錄的共享檔案寫入
    Then 接頭圖應包含共享狀態 "budget/usage_"

  Scenario: 接頭圖 — Outward 共享狀態已登記
    When 掃描 evolution 目錄的共享檔案寫入
    Then 接頭圖應包含共享狀態 "_system/outward"

  Scenario: 接頭圖 — Federation 共享狀態已登記
    When 掃描 evolution 目錄的共享檔案寫入
    Then 接頭圖應包含共享狀態 "marketplace"

  Scenario: 神經圖 — Nightly 子模組已登記
    When 掃描 evolution 系統的實際模組
    Then 神經圖應包含節點 "curiosity-router"
    And 神經圖應包含節點 "exploration-bridge"
    And 神經圖應包含節點 "crystal-actuator"
    And 神經圖應包含節點 "periodic-cycles"
    And 神經圖應包含節點 "skill-forge-scout"

  Scenario: 神經圖 — Tools 擴充節點已登記
    When 掃描 tools 系統的實際模組
    Then 神經圖應包含節點 "skill-market"
    And 神經圖應包含節點 "federation-sync"
    And 神經圖應包含節點 "zotero-bridge"

  Scenario: 神經圖 — Installer 系統已登記
    When 掃描 tools 系統的實際模組
    Then 神經圖應包含節點 "installer"
    And 神經圖應包含節點 "installer-daemon"

  Scenario: 神經圖 — MCP Server 和 Governance 子模組已登記
    When 掃描 governance 群組的實際模組
    Then 神經圖應包含節點 "mcp-server"
    And 神經圖應包含節點 "dendritic-scorer"
    And 神經圖應包含節點 "footprint"
    And 神經圖應包含節點 "perception"

  Scenario: 爆炸圖 — Doctor 和 MCP 模組影響半徑已登記
    When 掃描 evolution 目錄的跨模組依賴
    Then 爆炸圖應包含模組 "doctor/system_audit.py"
    And 爆炸圖應包含模組 "mcp_server.py"
    And 爆炸圖應包含模組 "federation/skill_market.py"

  Scenario: 水電圖 — Federation 儲存位置已登記
    When 掃描 evolution 目錄的資料寫入
    Then 水電圖應包含資料路徑 "marketplace"
    And 水電圖應包含資料路徑 "Federation"

  Scenario: 水電圖 — Outward 歸屬正確
    When 掃描 evolution 目錄的資料寫入
    Then 水電圖應包含資料路徑 "outward_trigger"

  # ═══════════════════════════════════════
  # 第四輪：9.5 精度修復驗證
  # ═══════════════════════════════════════

  Scenario: 接頭圖 — JSONL 審計日誌群已登記
    When 掃描 JSONL 日誌檔案群
    Then 接頭圖應包含共享狀態 "JSONL 審計日誌群"
    And 接頭圖應包含共享狀態 "activity_log.jsonl"
    And 接頭圖應包含共享狀態 "heartbeat.jsonl"

  Scenario: 接頭圖 — Markdown 記憶檔已登記
    When 掃描記憶系統的讀寫模組
    Then 接頭圖應包含共享狀態 "memory/{date}/{ch}.md"
    And 接頭圖應包含共享狀態 "MemoryStore"

  Scenario: 神經圖 — SQLite DB 子節點已登記
    When 掃描 data 群組的持久層
    Then 神經圖應包含節點 "pulse-db"
    And 神經圖應包含節點 "group-context-db"
    And 神經圖應包含節點 "workflow-state-db"

  Scenario: 水電圖 — Installer 管線已登記
    When 掃描 installer 目錄的資料寫入
    Then 水電圖應包含資料路徑 "Installer"
    And 水電圖應包含資料路徑 "DaemonConfigurator"

  Scenario: 爆炸圖 — 共享狀態數與接頭圖一致
    When 比對爆炸圖和接頭圖的共享狀態計數
    Then 爆炸圖健康快照應包含 "26 個"
