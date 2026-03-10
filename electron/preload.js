/**
 * MUSEON Dashboard - Electron Preload Script
 *
 * Exposes safe IPC communication to renderer process
 * Includes Setup Wizard APIs for first-run configuration
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('museon', {
  // ─── Gateway Communication ───

  /**
   * Query Gateway for data
   * @param {string} query - Query string (e.g., "show token usage")
   * @returns {Promise<object>} Gateway response
   */
  queryGateway: (query) => ipcRenderer.invoke('query-gateway', query),

  /**
   * Listen for Gateway messages
   * @param {function} callback - Called when message received
   */
  onGatewayMessage: (callback) => {
    ipcRenderer.on('gateway-message', (event, data) => callback(data));
  },

  /**
   * Listen for Gateway health updates
   * @param {function} callback - Called with {online: boolean}
   */
  onGatewayHealth: (callback) => {
    ipcRenderer.on('gateway-health', (event, data) => callback(data));
  },

  /**
   * Listen for Gateway log output
   * @param {function} callback - Called with {level: string, message: string}
   */
  onGatewayLog: (callback) => {
    ipcRenderer.on('gateway-log', (event, data) => callback(data));
  },

  /**
   * Restart Gateway process (kill → spawn → reconnect)
   * @returns {Promise<object>} { success, steps, error? }
   */
  restartGateway: () => ipcRenderer.invoke('gateway-restart'),

  // ─── Telegram Management ───

  /**
   * Get Telegram adapter status
   * @returns {Promise<object>} { configured, running, last_message_time, queue_size }
   */
  getTelegramStatus: () => ipcRenderer.invoke('telegram-get-status'),

  /**
   * Restart Telegram adapter (reconnect without restarting Gateway)
   * @returns {Promise<object>} { success, steps, error? }
   */
  restartTelegram: () => ipcRenderer.invoke('telegram-restart'),

  // ─── App Settings ───

  /**
   * Get auto-launch setting
   * @returns {Promise<boolean>} Auto-launch enabled
   */
  getAutoLaunch: () => ipcRenderer.invoke('get-auto-launch'),

  /**
   * Set auto-launch setting
   * @param {boolean} enable - Enable auto-launch
   * @returns {Promise<boolean>} Success
   */
  setAutoLaunch: (enable) => ipcRenderer.invoke('set-auto-launch', enable),

  /**
   * Open an external URL in the system browser
   * @param {string} url - URL to open
   * @returns {Promise<boolean>} Success
   */
  openExternal: (url) => ipcRenderer.invoke('open-external', url),

  // ─── Setup Wizard APIs ───

  /**
   * Check if this is a first run (needs setup wizard)
   * @returns {Promise<boolean>} true = needs setup
   */
  isFirstRun: () => ipcRenderer.invoke('setup-is-first-run'),

  /**
   * Get setup status for all required keys
   * @returns {Promise<object>} { ANTHROPIC_API_KEY: { configured, masked_value }, ... }
   */
  getSetupStatus: () => ipcRenderer.invoke('setup-get-status'),

  /**
   * Save an API key to .env file
   * @param {string} keyName - e.g., "ANTHROPIC_API_KEY"
   * @param {string} keyValue - The API key value
   * @returns {Promise<object>} { success, message }
   */
  saveSetupKey: (keyName, keyValue) => ipcRenderer.invoke('setup-save-key', keyName, keyValue),

  /**
   * Test Anthropic API key connection
   * @param {string} key - Anthropic API key
   * @returns {Promise<object>} { success, message }
   */
  testAnthropicKey: (key) => ipcRenderer.invoke('setup-test-anthropic', key),

  /**
   * Test Telegram bot token connection
   * @param {string} token - Telegram bot token
   * @returns {Promise<object>} { success, message }
   */
  testTelegramToken: (token) => ipcRenderer.invoke('setup-test-telegram', token),

  /**
   * Mark setup as complete (won't show wizard again)
   * @returns {Promise<void>}
   */
  completeSetup: () => ipcRenderer.invoke('setup-complete'),

  // ─── Installer 2.0 APIs ───

  /**
   * 取得安裝 checkpoint（斷點續裝）
   * @returns {Promise<object|null>} checkpoint 或 null
   */
  getCheckpoint: () => ipcRenderer.invoke('installer-get-checkpoint'),

  /**
   * 儲存安裝 checkpoint
   * @param {number} phase - 已完成的 phase
   * @param {object} details - phase 細節
   * @returns {Promise<object>} 更新後的 checkpoint
   */
  saveCheckpoint: (phase, details) => ipcRenderer.invoke('installer-save-checkpoint', phase, details),

  /**
   * 執行 Phase 0 全自動引導（Python/venv/Docker 偵測）
   * @returns {Promise<object>} { success, steps, dockerStatus }
   */
  runBootstrap: () => ipcRenderer.invoke('installer-run-bootstrap'),

  /**
   * 監聽 Phase 0 即時進度
   * @param {function} callback - { percent, status, error? }
   */
  onBootstrapProgress: (callback) => {
    ipcRenderer.on('installer-bootstrap-progress', (event, data) => callback(data));
  },

  /**
   * 執行 Phase 3 全自動部署（Gateway + Docker 工具）
   * @returns {Promise<object>} { success, steps, toolResults, dockerMissing? }
   */
  runDeploy: () => ipcRenderer.invoke('installer-run-deploy'),

  /**
   * 監聽 Phase 3 per-tool 進度
   * @param {function} callback - { step, status, message }
   */
  onDeployProgress: (callback) => {
    ipcRenderer.on('installer-deploy-progress', (event, data) => callback(data));
  },

  /**
   * 執行 Phase 4 健康檢查
   * @returns {Promise<object>} { gateway, docker, tools, overall }
   */
  runHealthcheck: () => ipcRenderer.invoke('installer-run-healthcheck'),

  /**
   * Installer 完成後切換到 Dashboard 模式（擴大視窗、啟動 Watchdog）
   * @returns {Promise<object>} { success }
   */
  completeInstallerTransition: () => ipcRenderer.invoke('installer-complete-transition'),

  // ─── 安裝模式偵測 ───

  /**
   * 偵測安裝模式（fresh / upgrade / normal）
   * @returns {Promise<object>} { mode: 'fresh'|'upgrade'|'normal', ... }
   */
  checkInstallMode: () => ipcRenderer.invoke('setup-check-install-mode'),

  /**
   * 蓋章：記錄當前版本已啟動過（下次啟動不再顯示選擇器）
   * @returns {Promise<object>} { success }
   */
  stampLaunchedVersion: () => ipcRenderer.invoke('setup-stamp-launched-version'),

  /**
   * 清空重裝：備份 data/ 到 data_archive/，刪除 .env
   * @returns {Promise<object>} { success, archiveDir? }
   */
  archiveData: () => ipcRenderer.invoke('setup-archive-data'),

  // ─── 版本更新 ───

  /**
   * 檢查是否有新版本
   * @returns {Promise<object|null>} { version, build_at, changes, updateAvailable }
   */
  checkUpdate: () => ipcRenderer.invoke('check-update'),

  /**
   * 套用更新（重啟 App + Gateway）
   * @returns {Promise<object>} { success }
   */
  applyUpdate: () => ipcRenderer.invoke('apply-update'),

  /**
   * 取得版本變更紀錄
   * @returns {Promise<string>} CHANGELOG.md 內容
   */
  getChangelog: () => ipcRenderer.invoke('get-changelog'),

  // ─── Doctor 健檢 & 修復 ───

  /**
   * 執行完整健檢
   * @returns {Promise<object>} { overall, checks: [...], summary }
   */
  doctorCheck: () => ipcRenderer.invoke('doctor-check'),

  /**
   * 執行修復動作
   * @param {string} action - 修復動作名稱
   * @returns {Promise<object>} { action, status, message, duration_ms }
   */
  doctorRepair: (action) => ipcRenderer.invoke('doctor-repair', action),

  // ─── Dashboard Data APIs (零 Token — 本地檔案讀取) ───

  /**
   * Get brain state for Organism tab (topology, vital signs)
   * @returns {Promise<object>} { persona, soulRings, latestQScore, crystals, crystalLinks, ... }
   */
  getBrainState: () => ipcRenderer.invoke('dashboard-get-brain-state'),

  /**
   * Get evolution data for Evolution tab (charts, timelines)
   * @returns {Promise<object>} { qScoreHistory, dailySummaries, soulRings, crystals, persona }
   */
  getEvolutionData: () => ipcRenderer.invoke('dashboard-get-evolution-data'),

  /**
   * Get memory dates for Memory browser
   * @returns {Promise<object>} { dates: ['2026-02-26', ...], channels: [...] }
   */
  getMemoryDates: () => ipcRenderer.invoke('dashboard-get-memory-dates'),

  /**
   * Read a specific memory file
   * @param {string} date - YYYY-MM-DD
   * @param {string} channel - meta-thinking|event|outcome|user-reaction
   * @returns {Promise<string>} Markdown content
   */
  readMemory: (date, channel) => ipcRenderer.invoke('dashboard-read-memory', date, channel),

  /**
   * Read merged memory entries (all channels, technical fields stripped)
   * @param {string} date - YYYY-MM-DD
   * @returns {Promise<object>} { date, blocks: [{ startTime, endTime, entries }] }
   */
  readMemoryMerged: (date) => ipcRenderer.invoke('dashboard-read-memory-merged', date),

  /**
   * Search through all memory files
   * @param {string} query - Search text
   * @returns {Promise<object>} { query, results: [{ date, time, snippet }], totalFound }
   */
  searchMemory: (query) => ipcRenderer.invoke('dashboard-search-memory', query),

  /**
   * Get memory overview (understanding map + milestones)
   * @returns {Promise<object>} { userProfile, persona, skillDistribution, milestones }
   */
  getMemoryOverview: () => ipcRenderer.invoke('dashboard-get-memory-overview'),

  // ─── Gateway Info ───

  /**
   * Get Gateway process info (PID, port, uptime, online status)
   * @returns {Promise<object>} { pid, port, uptime_ms, online }
   */
  getGatewayInfo: () => ipcRenderer.invoke('dashboard-get-gateway-info'),

  // ─── Agent 即時狀態 ───

  /**
   * Get agent state for Agent tab (growth, sub-agents, module activity)
   * @returns {Promise<object>} { growthStage, birthDate, name, subAgents, moduleActivity, skillCount, gatewayOnline, gatewayPid }
   */
  getAgentState: () => ipcRenderer.invoke('dashboard-get-agent-state'),

  // ─── Guardian 守護者 ───

  /**
   * Get Guardian status (last check results, unresolved issues)
   * @returns {Promise<object>} { last_l1, last_l2, last_l3, unresolved_count, recent_repairs, ... }
   */
  getGuardianStatus: () => ipcRenderer.invoke('dashboard-get-guardian-status'),

  /**
   * Run full Guardian check (L1+L2+L3)
   * @returns {Promise<object>} { l1, l2, l3, unresolved }
   */
  runGuardianCheck: () => ipcRenderer.invoke('dashboard-run-guardian-check'),

  // ─── Nightly Pipeline 凌晨整合管線 ───

  /**
   * Get nightly pipeline status (last report)
   * @returns {Promise<object>} { status, completed_at, summary, steps, errors }
   */
  getNightlyStatus: () => ipcRenderer.invoke('dashboard-get-nightly-status'),

  /**
   * Manually trigger nightly pipeline
   * @returns {Promise<object>} { triggered, report }
   */
  runNightly: () => ipcRenderer.invoke('dashboard-run-nightly'),

  // ─── Skills 技能模組 ───

  /**
   * List all skills with lifecycle and stats
   * @returns {Promise<object>} { skills, count }
   */
  getSkillsList: () => ipcRenderer.invoke('dashboard-get-skills-list'),

  /**
   * Get single skill detail
   * @param {string} name - Skill name
   * @returns {Promise<object>} { name, dir, description, meta }
   */
  getSkillDetail: (name) => ipcRenderer.invoke('dashboard-get-skill-detail', name),

  /**
   * Get skills summary by lifecycle
   * @returns {Promise<object>} { total, by_lifecycle, total_uses }
   */
  getSkillsStatus: () => ipcRenderer.invoke('dashboard-get-skills-status'),

  /**
   * Trigger full security scan on all skills
   * @returns {Promise<object>} { total_scanned, safe_count, unsafe_count }
   */
  runSkillsScan: () => ipcRenderer.invoke('dashboard-run-skills-scan'),

  // ─── Multi-Agent 飛輪八部門 ───

  /**
   * Get all 10 departments config
   * @returns {Promise<object>} { departments, count }
   */
  getMultiagentDepts: () => ipcRenderer.invoke('dashboard-get-multiagent-depts'),

  /**
   * Get multiagent status (current dept, switch count, stats)
   * @returns {Promise<object>} { enabled, current_dept, switch_count, ... }
   */
  getMultiagentStatus: () => ipcRenderer.invoke('dashboard-get-multiagent-status'),

  /**
   * Get shared assets list
   * @returns {Promise<object>} { assets, count }
   */
  getMultiagentAssets: () => ipcRenderer.invoke('dashboard-get-multiagent-assets'),

  /**
   * Test routing (debug)
   * @param {string} message
   * @returns {Promise<object>} { routed_to, confidence, flywheel_scores }
   */
  testMultiagentRoute: (message) => ipcRenderer.invoke('dashboard-test-multiagent-route', message),

  // ─── 工具兵器庫 🛠️ ───

  /**
   * List all tools with status
   * @returns {Promise<object>} { tools, count }
   */
  getToolsList: () => ipcRenderer.invoke('dashboard-get-tools-list'),

  /**
   * Get tools summary (installed/enabled/healthy counts)
   * @returns {Promise<object>} { total, installed, enabled, healthy, ... }
   */
  getToolsStatus: () => ipcRenderer.invoke('dashboard-get-tools-status'),

  /**
   * Toggle tool on/off
   * @param {string} name - Tool name
   * @param {boolean} enabled - Target state
   * @returns {Promise<object>} { success, name, enabled }
   */
  toggleTool: (name, enabled) => ipcRenderer.invoke('dashboard-toggle-tool', name, enabled),

  /**
   * Run health check on all tools
   * @returns {Promise<object>} { tool_name: { healthy, ... }, ... }
   */
  runToolsHealth: () => ipcRenderer.invoke('dashboard-run-tools-health'),

  /**
   * Get latest tool discovery results
   * @returns {Promise<object>} { timestamp, searched, found, recommended }
   */
  getToolsDiscoveries: () => ipcRenderer.invoke('dashboard-get-tools-discoveries'),

  /**
   * Get single tool detail
   * @param {string} name - Tool name
   * @returns {Promise<object>} Tool detail
   */
  getToolDetail: (name) => ipcRenderer.invoke('dashboard-get-tool-detail', name),

  /**
   * Install a single tool (background)
   * @param {string} name - Tool name
   * @returns {Promise<object>} { started, name }
   */
  installTool: (name) => ipcRenderer.invoke('dashboard-install-tool', name),

  /**
   * Batch install multiple tools (sequential background)
   * @param {string[]} tools - Tool name array
   * @returns {Promise<object>} { started, tools, count }
   */
  installToolsBatch: (tools) => ipcRenderer.invoke('dashboard-install-tools-batch', tools),

  /**
   * Get install progress for a tool
   * @param {string} name - Tool name
   * @returns {Promise<object>} { status, progress, message, name }
   */
  getInstallProgress: (name) => ipcRenderer.invoke('dashboard-get-install-progress', name),

  // ─── VectorBridge + Sandbox ───

  /**
   * Get VectorBridge (Qdrant) status and collection stats
   * @returns {Promise<object>} { available, collections }
   */
  getVectorStatus: () => ipcRenderer.invoke('dashboard-get-vector-status'),

  /**
   * Semantic search via VectorBridge
   * @param {string} collection - Collection name
   * @param {string} query - Search query
   * @returns {Promise<object>} { results, count }
   */
  vectorSearch: (collection, query) => ipcRenderer.invoke('dashboard-vector-search', collection, query),

  /**
   * Get ExecutionSandbox status and audit stats
   * @returns {Promise<object>} { docker_available, audit_stats }
   */
  getSandboxStatus: () => ipcRenderer.invoke('dashboard-get-sandbox-status'),

  // ─── Dispatch 分派系統 ───

  /**
   * Get active dispatch plans status
   * @returns {Promise<object>} { active_plans, count }
   */
  getDispatchStatus: () => ipcRenderer.invoke('dashboard-get-dispatch-status'),

  /**
   * Get dispatch history (last 20 completed/failed)
   * @returns {Promise<object>} { history, count }
   */
  getDispatchHistory: () => ipcRenderer.invoke('dashboard-get-dispatch-history'),

  // ─── Pulse 即時狀態 ───
  getPulseStatus: () => ipcRenderer.invoke('dashboard-get-pulse-status'),

  // ─── Activity Log + Daily Summary ───
  getActivityRecent: () => ipcRenderer.invoke('dashboard-get-activity-recent'),
  getDailySummary: (date) => ipcRenderer.invoke('dashboard-get-daily-summary', date),
  getDailySummaries: () => ipcRenderer.invoke('dashboard-get-daily-summaries'),

  // ─── Secretary Dashboard ───
  getSecretaryData: () => ipcRenderer.invoke('dashboard-get-secretary-data'),
  saveSecretaryTasks: (data) => ipcRenderer.invoke('dashboard-save-secretary-tasks', data),
  saveSecretaryProjects: (data) => ipcRenderer.invoke('dashboard-save-secretary-projects', data),
  saveSecretaryCustomers: (data) => ipcRenderer.invoke('dashboard-save-secretary-customers', data),
  getSecretaryAiSuggestions: () => ipcRenderer.invoke('dashboard-get-secretary-ai-suggestions'),

  // ─── MCP 連接器管理（走 Gateway HTTP API）───

  /**
   * 取得所有 MCP 伺服器狀態
   * @returns {Promise<object>} { mcp_sdk_available, connections, total_connected, total_tools }
   */
  getMCPStatus: () => fetch('http://127.0.0.1:8765/api/mcp/status').then(r => r.json()).catch(() => ({ connections: {}, total_connected: 0 })),

  /**
   * 取得 MCP 伺服器目錄（含連線狀態）
   * @returns {Promise<object>} { catalog: [...], count }
   */
  getMCPCatalog: () => fetch('http://127.0.0.1:8765/api/mcp/catalog').then(r => r.json()).catch(() => ({ catalog: [], count: 0 })),

  /**
   * 連接指定 MCP 伺服器
   * @param {string} name - 伺服器名稱
   * @param {object} env - 環境變數 { KEY: value }
   * @returns {Promise<object>} { success, ... }
   */
  connectMCP: (name, env) => fetch('http://127.0.0.1:8765/api/mcp/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, env: env || {} }),
  }).then(r => r.json()).catch(e => ({ success: false, error: e.message })),

  /**
   * 斷開指定 MCP 伺服器
   * @param {string} name - 伺服器名稱
   * @returns {Promise<object>} { success, ... }
   */
  disconnectMCP: (name) => fetch('http://127.0.0.1:8765/api/mcp/disconnect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  }).then(r => r.json()).catch(e => ({ success: false, error: e.message })),

  // ─── Budget / Token 用量 ───

  /**
   * Get token budget usage stats
   * @returns {Promise<object>} { daily_limit, used, remaining, percentage, should_warn }
   */
  getBudgetStats: () => ipcRenderer.invoke('dashboard-get-budget'),

  /**
   * Set daily token budget limit
   * @param {number} newLimit - New daily token limit
   * @returns {Promise<object>} { success, daily_limit, message }
   */
  setBudgetLimit: (newLimit) => ipcRenderer.invoke('dashboard-set-budget-limit', newLimit),

  /**
   * Get API key configuration status (no key values returned)
   * @returns {Promise<object>} { ANTHROPIC_API_KEY: { configured, prefix }, ... }
   */
  getKeyStatus: () => ipcRenderer.invoke('dashboard-get-key-status'),

  // ─── Permissions（macOS 權限） ───

  /**
   * 檢查所有 macOS 權限狀態
   * @returns {Promise<object>} { permissions: [{ name, label, granted, canRequest }] }
   */
  checkPermissions: () => ipcRenderer.invoke('permissions-check-all'),

  /**
   * 請求單一 macOS 權限
   * @param {string} name - 權限名稱 (microphone/camera/notifications/accessibility/screen_recording/automation)
   * @returns {Promise<object>} { success, granted, openedSettings? }
   */
  requestPermission: (name) => ipcRenderer.invoke('permissions-request', name),
});
