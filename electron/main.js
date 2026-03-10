/**
 * MUSEON - Electron Main Process
 *
 * Features:
 * - Token usage monitoring
 * - Gateway health check
 * - Auto-launch on system startup
 * - IPC communication with Python Gateway
 * - Watchdog mechanism
 */

const { app, BrowserWindow, ipcMain, Menu, Tray } = require('electron');
const path = require('path');
const fs = require('fs');
const https = require('https');
const http = require('http');
const { spawn, execSync } = require('child_process');

// Configuration — Gateway 是 FastAPI HTTP 伺服器
const GATEWAY_HTTP_PORT = 8765;
const GATEWAY_BASE_URL = `http://127.0.0.1:${GATEWAY_HTTP_PORT}`;
const GATEWAY_CHECK_INTERVAL = 30000; // 30 seconds
const AUTO_LAUNCH_KEY = 'museon-autolaunch';

let mainWindow = null;
let tray = null;
let trayMenu = null;
let gatewayOnline = false;  // Gateway 連線狀態（HTTP 健檢）
let gatewayStartTime = null; // Gateway 啟動時間（用於計算 Uptime）
let watchdogInterval = null;
let gatewayProcess = null;  // Child process for Gateway

/**
 * Create the main dashboard window
 * @param {object} opts - { installerMode: bool } 安裝模式使用小視窗
 */
function createWindow(opts = {}) {
  const isInstaller = opts.installerMode || false;
  mainWindow = new BrowserWindow({
    width: isInstaller ? 600 : 1200,
    height: isInstaller ? 720 : 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    icon: path.join(__dirname, 'assets', 'icon.png'),
    title: 'MUSEON',
    ...(isInstaller ? {
      titleBarStyle: 'hiddenInset',
      resizable: false,
      maximizable: false,
    } : {}),
  });

  mainWindow.loadFile(path.join(__dirname, 'src', 'index.html'));

  // Open DevTools in development mode
  if (process.argv.includes('--dev')) {
    mainWindow.webContents.openDevTools();
  }

  // 頁面載入失敗時顯示錯誤頁面（而非空白）
  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
    console.error('[MUSEON] Page load failed:', errorCode, errorDescription);
    mainWindow.loadURL(`data:text/html;charset=utf-8,
      <html><body style="font-family:system-ui;padding:40px;background:#141b2d;color:#e8dcc6">
      <h2>MUSEON</h2>
      <p>頁面載入失敗: ${errorDescription} (${errorCode})</p>
      <p>請重新啟動應用程式。</p>
      </body></html>`);
  });

  // Renderer crash recovery
  mainWindow.webContents.on('render-process-gone', (event, details) => {
    console.error('[MUSEON] Renderer crashed:', details.reason);
    mainWindow.loadURL(`data:text/html;charset=utf-8,
      <html><body style="font-family:system-ui;padding:40px;background:#141b2d;color:#e8dcc6">
      <h2>MUSEON</h2>
      <p>渲染程序異常: ${details.reason}</p>
      <button onclick="location.reload()" style="padding:8px 16px;margin-top:12px;cursor:pointer">
        重新載入
      </button>
      </body></html>`);
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // Minimize to tray instead of closing
  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
}

/**
 * Create system tray icon
 */
function createTray() {
  tray = new Tray(path.join(__dirname, 'assets', 'tray-icon.png'));

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show Dashboard',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
        } else {
          createWindow();
        }
      }
    },
    {
      label: 'Gateway Status',
      enabled: false,
      id: 'gateway-status'
    },
    { type: 'separator' },
    {
      label: 'Quit MUSEON',
      click: () => {
        app.isQuitting = true;
        app.quit();
      }
    }
  ]);

  tray.setToolTip('MUSEON');
  tray.setContextMenu(contextMenu);
  trayMenu = contextMenu;

  tray.on('click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
      }
    } else {
      createWindow();
    }
  });
}

/**
 * Check Gateway health via HTTP GET /health
 * Gateway 是 FastAPI 伺服器，只提供 HTTP 介面（無 Unix Socket）
 * @returns {Promise<object|null>} 健康資訊或 null
 */
async function checkGatewayHealth() {
  return new Promise((resolve) => {
    const req = http.get(`${GATEWAY_BASE_URL}/health`, { timeout: 3000 }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(data);
          resolve(result);
        } catch {
          resolve(null);
        }
      });
    });
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
  });
}

/**
 * Wait for Gateway HTTP to become ready (polling with backoff)
 * @param {number} maxWaitMs - 最長等待毫秒數
 * @returns {Promise<boolean>} true if Gateway came online
 */
async function waitForGatewayReady(maxWaitMs = 15000) {
  const start = Date.now();
  let interval = 500;  // 起始 500ms，逐步增加
  while (Date.now() - start < maxWaitMs) {
    const health = await checkGatewayHealth();
    if (health && health.status === 'healthy') {
      return true;
    }
    await new Promise(r => setTimeout(r, interval));
    interval = Math.min(interval * 1.5, 2000);  // 最多 2 秒一次
  }
  return false;
}

/**
 * Watchdog mechanism - monitor Gateway health via HTTP
 * 每 30 秒 GET /health，回報 online/offline 狀態
 */
function startWatchdog() {
  watchdogInterval = setInterval(async () => {
    const health = await checkGatewayHealth();
    const online = !!(health && health.status === 'healthy');
    const changed = (online !== gatewayOnline);
    gatewayOnline = online;

    // Update tray status
    if (tray) {
      const statusItem = trayMenu.getMenuItemById('gateway-status');
      if (statusItem) {
        statusItem.label = online ? 'Gateway: Online ✓' : 'Gateway: Offline ✗';
      }
    }

    // Notify renderer (always send, so UI stays current)
    safeSend('gateway-health', {
      online,
      telegram: health ? health.telegram : 'unknown',
      skills: health ? health.skills_indexed : 0,
    });

    if (changed) {
      console.log(`[MUSEON] Watchdog: Gateway ${online ? 'ONLINE' : 'OFFLINE'}`);
    }
  }, GATEWAY_CHECK_INTERVAL);
}

/**
 * Handle IPC messages from renderer — 透過 HTTP POST /webhook 送到 Gateway
 */
ipcMain.handle('query-gateway', async (event, query) => {
  if (!gatewayOnline) {
    throw new Error('Gateway 離線');
  }
  try {
    return await gatewayHttpPost('/webhook', {
      user_id: 'electron_dashboard',
      content: query,
      timestamp: new Date().toISOString(),
    });
  } catch (err) {
    throw new Error(`Gateway 查詢失敗: ${err.message}`);
  }
});

ipcMain.handle('get-auto-launch', () => {
  return app.getLoginItemSettings().openAtLogin;
});

ipcMain.handle('set-auto-launch', (event, enable) => {
  app.setLoginItemSettings({
    openAtLogin: enable,
    openAsHidden: false
  });
  return true;
});

// ─── Open External URL ───
ipcMain.handle('open-external', async (event, url) => {
  const { shell } = require('electron');
  if (typeof url === 'string' && (url.startsWith('https://') || url.startsWith('http://'))) {
    await shell.openExternal(url);
    return true;
  }
  return false;
});

// ─── Gateway Restart / Repair ───

/**
 * Resolve project root (where pyproject.toml lives)
 * 搜尋順序：
 *   1. MUSEON_HOME 環境變數（最優先）
 *   2. 從 __dirname 往上找 pyproject.toml（開發模式 / electron . 直接跑）
 *   3. 常見安裝路徑候選清單（ASAR 打包後 __dirname 在 app.asar 內找不到）
 */
function getProjectRoot() {
  // 1. 環境變數最優先
  //    生產佈局: MUSEON_HOME/.runtime/pyproject.toml（pyproject 在 .runtime 底下）
  //    開發佈局: MUSEON_HOME/pyproject.toml（pyproject 在根目錄）
  if (process.env.MUSEON_HOME) {
    const home = process.env.MUSEON_HOME;
    if (fs.existsSync(path.join(home, 'pyproject.toml')) ||
        fs.existsSync(path.join(home, '.runtime', 'pyproject.toml')) ||
        fs.existsSync(path.join(home, '.env'))) {
      return home;
    }
  }

  // 2. 從 __dirname 往上找（開發模式有效）
  let dir = __dirname;
  for (let i = 0; i < 5; i++) {
    const parent = path.dirname(dir);
    if (fs.existsSync(path.join(parent, 'pyproject.toml'))) {
      if (path.basename(parent) === '.runtime') return path.dirname(parent);
      return parent;
    }
    dir = parent;
  }

  // 3. ASAR 打包模式 — 候選路徑
  const homeDir = require('os').homedir();
  const candidates = [
    // 正式安裝路徑（優先）
    path.join(homeDir, 'MUSEON 正式版', 'MUSEON'),
    path.join(homeDir, 'MUSEON'),
    // 開發路徑（僅開發時 fallback）
    path.join(homeDir, 'museon'),
    path.join(homeDir, 'MUSEON'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(path.join(candidate, 'pyproject.toml')) ||
        fs.existsSync(path.join(candidate, '.runtime', 'pyproject.toml'))) {
      return candidate;
    }
  }

  // 4. 最後 fallback（可能不存在，但保持不 crash）
  return process.env.MUSEON_HOME || path.join(homeDir, 'museon');
}

/**
 * Find best Python binary for running museon
 * 搜尋順序：
 *   1. .runtime/.venv/bin/python3（production 佈局）
 *   2. .venv/bin/python3（dev 佈局）
 *   3. 系統 python3
 */
function findPython(projectRoot) {
  const candidates = [
    path.join(projectRoot, '.runtime', '.venv', 'bin', 'python3'),
    path.join(projectRoot, '.runtime', '.venv', 'bin', 'python'),
    path.join(projectRoot, '.venv', 'bin', 'python3'),
    path.join(projectRoot, '.venv', 'bin', 'python'),
  ];
  for (const p of candidates) {
    if (!fs.existsSync(p)) continue;
    // 驗證 venv 可用性：確認 fastapi 有安裝（避免殭屍 venv）
    try {
      const { execFileSync } = require('child_process');
      execFileSync(p, ['-c', 'import fastapi'], { timeout: 5000, stdio: 'ignore' });
      return p;
    } catch {
      console.warn(`[MUSEON] findPython: ${p} exists but fastapi not importable, skipping`);
    }
  }
  return 'python3';
}

/**
 * 安全地向 renderer 發送訊息（防止 mainWindow 已銷毀時 crash）
 */
function safeSend(channel, data) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, data);
  }
}

/**
 * Spawn Gateway 子進程（共用邏輯，消除重複）
 * 回傳 spawn 的 process，呼叫端負責後續連線
 */
function spawnGateway() {
  const projectRoot = getProjectRoot();
  const pythonBin = findPython(projectRoot);
  // PYTHONPATH: 支援 production (.runtime/src) 和 dev (./src) 佈局
  const runtimeSrc = path.join(projectRoot, '.runtime', 'src');
  const srcDir = fs.existsSync(runtimeSrc) ? runtimeSrc : path.join(projectRoot, 'src');
  console.log('[MUSEON] spawnGateway: projectRoot =', projectRoot, ', pythonBin =', pythonBin, ', srcDir =', srcDir);

  // 建立乾淨的環境：只傳系統路徑變數，不轉發 API Key。
  // Gateway 自己會從 .env 讀取 ANTHROPIC_API_KEY / TELEGRAM_BOT_TOKEN，
  // 確保 Setup Wizard 更新 Key 後重啟能讀到最新值。
  const cleanEnv = { ...process.env };
  delete cleanEnv.ANTHROPIC_API_KEY;
  delete cleanEnv.TELEGRAM_BOT_TOKEN;

  const proc = spawn(pythonBin, ['-m', 'museon.gateway.server'], {
    cwd: projectRoot,
    env: {
      ...cleanEnv,
      PYTHONPATH: srcDir,
      MUSEON_HOME: projectRoot,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
  });

  gatewayStartTime = Date.now();

  // 同時將日誌寫入檔案，方便除錯
  const logDir = path.join(projectRoot, 'logs');
  if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
  const logStream = fs.createWriteStream(path.join(logDir, 'gateway.log'), { flags: 'a' });
  const errStream = fs.createWriteStream(path.join(logDir, 'gateway.err'), { flags: 'a' });

  proc.stdout.on('data', (data) => {
    const msg = data.toString().trim();
    if (msg) {
      safeSend('gateway-log', { level: 'info', message: msg });
      logStream.write(msg + '\n');
    }
  });
  proc.stderr.on('data', (data) => {
    const msg = data.toString().trim();
    if (msg) {
      safeSend('gateway-log', { level: 'error', message: msg });
      errStream.write(msg + '\n');
    }
  });
  proc.on('exit', (code) => {
    console.log('[MUSEON] Gateway exited with code:', code);
    gatewayProcess = null;
    gatewayStartTime = null;
    safeSend('gateway-health', { online: false });
  });

  return proc;
}

ipcMain.handle('gateway-restart', async () => {
  const steps = [];
  try {
    // 1. Kill existing process
    if (gatewayProcess && !gatewayProcess.killed) {
      gatewayProcess.kill('SIGTERM');
      await new Promise(r => setTimeout(r, 1000));
      if (!gatewayProcess.killed) gatewayProcess.kill('SIGKILL');
      steps.push('已終止舊 Gateway 進程');
    }

    // 2. Spawn new Gateway process（使用共用函式）
    gatewayProcess = spawnGateway();
    const projectRoot = getProjectRoot();
    steps.push(`projectRoot: ${projectRoot}`);
    steps.push(`pythonBin: ${findPython(projectRoot)}`);
    steps.push('已啟動新 Gateway 進程 (PID: ' + gatewayProcess.pid + ')');

    // 3. Wait for Gateway HTTP /health to respond（最多 15 秒）
    const ready = await waitForGatewayReady(15000);
    if (ready) {
      gatewayOnline = true;
      steps.push('Gateway HTTP 健檢通過 ✓');
      safeSend('gateway-health', { online: true });
      return { success: true, steps };
    } else {
      steps.push('Gateway 已啟動但 HTTP 健檢未通過（可能仍在初始化）');
      return { success: false, steps, error: 'Health check timeout' };
    }
  } catch (err) {
    steps.push('錯誤：' + err.message);
    return { success: false, steps, error: err.message };
  }
});

// ─── Doctor 健檢 & 修復 (via Gateway HTTP API) ───

ipcMain.handle('doctor-check', async () => {
  try {
    return await gatewayHttpGet('/api/doctor/check');
  } catch (err) {
    // Gateway 不通時用本地健檢
    try {
      const { execFileSync } = require('child_process');
      const projectRoot = getProjectRoot();
      const pythonBin = findPython(projectRoot);
      const result = execFileSync(pythonBin, [
        '-c',
        'from museon.doctor.health_check import HealthChecker; import json; print(json.dumps(HealthChecker().run_all().to_dict()))'
      ], {
        env: { ...process.env, PYTHONPATH: fs.existsSync(path.join(projectRoot, '.runtime', 'src')) ? path.join(projectRoot, '.runtime', 'src') : path.join(projectRoot, 'src'), MUSEON_HOME: projectRoot },
        timeout: 30000,
      });
      return JSON.parse(result.toString());
    } catch (fallbackErr) {
      return { error: fallbackErr.message, overall: 'unknown', checks: [] };
    }
  }
});

ipcMain.handle('doctor-repair', async (event, action) => {
  try {
    return await gatewayHttpPost('/api/doctor/repair', { action });
  } catch (err) {
    return { action, status: 'failed', message: err.message };
  }
});

// ─── Gateway HTTP Client（統一 HTTP 通訊層）───

function gatewayHttpGet(urlPath) {
  return new Promise((resolve, reject) => {
    const req = http.get(`${GATEWAY_BASE_URL}${urlPath}`, { timeout: 5000 }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch { resolve({ error: 'Invalid JSON', raw: data }); }
      });
    });
    req.on('error', (err) => reject(err));
    req.on('timeout', () => { req.destroy(); reject(new Error('Timeout')); });
  });
}

function gatewayHttpPost(urlPath, body = null) {
  return new Promise((resolve, reject) => {
    const postData = body ? JSON.stringify(body) : '';
    const req = http.request({
      hostname: '127.0.0.1', port: GATEWAY_HTTP_PORT,
      path: urlPath, method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(postData ? { 'Content-Length': Buffer.byteLength(postData) } : {}),
      },
      timeout: 10000,
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch { resolve({ error: 'Invalid JSON', raw: data }); }
      });
    });
    req.on('error', (err) => reject(err));
    req.on('timeout', () => { req.destroy(); reject(new Error('Timeout')); });
    if (postData) req.write(postData);
    req.end();
  });
}

ipcMain.handle('telegram-get-status', async () => {
  try {
    return await gatewayHttpGet('/api/telegram/status');
  } catch (err) {
    // Gateway 不通時，直接讀 .env 判斷是否已設定（讓 UI 顯示正確狀態）
    try {
      const envPath = getEnvFilePath();
      const env = parseEnvFile(envPath);
      const token = env['TELEGRAM_BOT_TOKEN'] || '';
      const hasToken = token.length > 5;
      return {
        configured: hasToken,
        running: false,
        masked_value: hasToken ? token.substring(0, 6) + '***' : '',
        error: 'Gateway 離線',
      };
    } catch (envErr) {
      return { configured: false, running: false, error: err.message };
    }
  }
});

ipcMain.handle('telegram-restart', async () => {
  try {
    return await gatewayHttpPost('/api/telegram/restart');
  } catch (err) {
    return { success: false, steps: [], error: err.message };
  }
});

// ─── Dashboard Data Reading (零 Token — 純本地檔案讀取) ───

/**
 * Resolve the data/ directory path.
 * 複用 getProjectRoot()，不重複 walk-up 邏輯（避免 ASAR 路徑 bug 再發）
 */
function getDataDir() {
  return path.join(getProjectRoot(), 'data');
}

/** Safely read a JSON file, returns null on failure */
function readJSON(filePath) {
  try {
    if (!fs.existsSync(filePath)) return null;
    return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
  } catch (err) {
    console.warn('[Dashboard] Failed to read JSON:', filePath, err.message);
    return null;
  }
}

/** Read a JSONL file, returns array of parsed objects */
function readJSONL(filePath) {
  try {
    if (!fs.existsSync(filePath)) return [];
    const content = fs.readFileSync(filePath, 'utf-8');
    return content.split('\n')
      .filter(line => line.trim())
      .map(line => {
        try { return JSON.parse(line); }
        catch { return null; }
      })
      .filter(Boolean);
  } catch (err) {
    console.warn('[Dashboard] Failed to read JSONL:', filePath, err.message);
    return [];
  }
}

/** Read last line of a JSONL file (for latest Q-Score) */
function readLastJSONL(filePath) {
  try {
    if (!fs.existsSync(filePath)) return null;
    const content = fs.readFileSync(filePath, 'utf-8');
    const lines = content.split('\n').filter(l => l.trim());
    if (lines.length === 0) return null;
    return JSON.parse(lines[lines.length - 1]);
  } catch (err) {
    return null;
  }
}

/** Read all JSON files in a directory, returns array */
function readDailyDir(dirPath) {
  try {
    if (!fs.existsSync(dirPath)) return [];
    return fs.readdirSync(dirPath)
      .filter(f => f.endsWith('.json'))
      .sort()
      .map(f => readJSON(path.join(dirPath, f)))
      .filter(Boolean);
  } catch (err) {
    return [];
  }
}

/** Count number of dated directories in memory/ */
function countMemoryDays(memoryDir) {
  try {
    if (!fs.existsSync(memoryDir)) return 0;
    let count = 0;
    const years = fs.readdirSync(memoryDir).filter(f => /^\d{4}$/.test(f));
    for (const year of years) {
      const months = fs.readdirSync(path.join(memoryDir, year)).filter(f => /^\d{2}$/.test(f));
      for (const month of months) {
        const days = fs.readdirSync(path.join(memoryDir, year, month)).filter(f => /^\d{2}$/.test(f));
        count += days.length;
      }
    }
    return count;
  } catch (err) {
    return 0;
  }
}

/**
 * Dashboard Tab 1: 大腦即時狀態
 * 讀取本地 data/ 目錄，零 Token
 */
ipcMain.handle('dashboard-get-brain-state', async () => {
  const dataDir = getDataDir();

  // 直覺系統：計算 context 檔案數
  let intuitionCount = 0;
  const intuitionDir = path.join(dataDir, 'intuition', 'contexts');
  try {
    if (fs.existsSync(intuitionDir)) {
      intuitionCount = fs.readdirSync(intuitionDir).filter(f => f.endsWith('.json')).length;
    }
  } catch (e) { /* ignore */ }

  // 計畫引擎：讀取活躍計畫
  let planCount = 0;
  const planActiveDir = path.join(dataDir, 'plans', 'active');
  try {
    if (fs.existsSync(planActiveDir)) {
      planCount = fs.readdirSync(planActiveDir).filter(f => f.endsWith('.md') || f.endsWith('.json')).length;
    }
  } catch (e) { /* ignore */ }

  // WEE 工作流
  const weeData = readJSON(path.join(dataDir, 'wee', 'workflows.json')) || { workflows: [] };

  // Morphenix 迭代筆記
  const morphenix = readJSON(path.join(dataDir, 'morphenix', 'iteration_notes.json')) || { notes: [], proposals: [] };

  // 技能使用統計
  const skillUsageLog = readJSONL(path.join(dataDir, 'skill_usage_log.jsonl')) || [];

  // 心跳數據
  const heartbeats = readJSONL(path.join(dataDir, 'heartbeat.jsonl')) || [];

  return {
    persona: readJSON(path.join(dataDir, 'ANIMA_MC.json')),
    userProfile: readJSON(path.join(dataDir, 'ANIMA_USER.json')),
    soulRings: readJSON(path.join(dataDir, 'anima', 'soul_rings.json')) || [],
    observationRings: readJSON(path.join(dataDir, 'anima', 'observation_rings.json')) || [],
    latestQScore: readLastJSONL(path.join(dataDir, 'eval', 'q_scores.jsonl')),
    qScoreHistory: readJSONL(path.join(dataDir, 'eval', 'q_scores.jsonl')),
    crystals: readJSON(path.join(dataDir, 'lattice', 'crystals.json')) || [],
    crystalLinks: readJSON(path.join(dataDir, 'lattice', 'links.json')) || [],
    memoryDays: countMemoryDays(path.join(dataDir, 'memory')),
    alerts: readJSON(path.join(dataDir, 'eval', 'alerts.json')) || [],
    blindspots: readJSON(path.join(dataDir, 'eval', 'blindspots.json')) || [],
    // 子系統活性數據
    intuition: { active: intuitionCount > 0, count: intuitionCount },
    planEngine: { active: planCount > 0, count: planCount },
    wee: weeData,
    morphenix: morphenix,
    skillUsageLog: skillUsageLog,
    heartbeats: heartbeats.slice(-24),
    dataDir: dataDir,
  };
});

/**
 * Dashboard Tab 6: Agent 即時狀態（純本地讀取，零 Token）
 */
ipcMain.handle('dashboard-get-agent-state', async () => {
  const dataDir = getDataDir();
  const persona = readJSON(path.join(dataDir, 'ANIMA_MC.json')) || {};
  const identity = (persona.identity) || {};
  const skillUsageLog = readJSONL(path.join(dataDir, 'skill_usage_log.jsonl')) || [];
  // Sub-agent 結果
  const subAgentDir = path.join(dataDir, 'sub_agents');
  let subAgents = [];
  try {
    if (fs.existsSync(subAgentDir)) {
      const files = fs.readdirSync(subAgentDir).filter(f => f.endsWith('.json')).sort().slice(-10);
      subAgents = files.map(f => readJSON(path.join(subAgentDir, f))).filter(Boolean);
    }
  } catch (e) { /* ignore */ }

  // 模組活性（從最近技能使用推算）
  const recentSkills = skillUsageLog.slice(-50);
  const moduleActivity = {};
  recentSkills.forEach(s => {
    const name = s.skill || s.name || 'unknown';
    moduleActivity[name] = (moduleActivity[name] || 0) + 1;
  });

  return {
    growthStage: identity.growth_stage || 'unknown',
    birthDate: identity.birth_date || null,
    name: identity.name || 'MUSEON',
    subAgents,
    moduleActivity,
    skillCount: recentSkills.length,
    gatewayOnline: gatewayOnline,
    gatewayPid: gatewayProcess && !gatewayProcess.killed ? gatewayProcess.pid : null,
  };
});

/**
 * Dashboard Tab 2: 演化資料
 * 讀取歷史資料用於圖表，零 Token
 */
ipcMain.handle('dashboard-get-evolution-data', async () => {
  const dataDir = getDataDir();

  // 技能使用統計
  const skillUsageLog = readJSONL(path.join(dataDir, 'skill_usage_log.jsonl')) || [];

  // Morphenix
  const morphenix = readJSON(path.join(dataDir, 'morphenix', 'iteration_notes.json')) || { notes: [], proposals: [] };

  // WEE
  const weeData = readJSON(path.join(dataDir, 'wee', 'workflows.json')) || { workflows: [] };

  // Guardian
  const guardian = readJSON(path.join(dataDir, 'guardian', 'state.json')) || {};

  return {
    qScoreHistory: readJSONL(path.join(dataDir, 'eval', 'q_scores.jsonl')),
    dailySummaries: readDailyDir(path.join(dataDir, 'eval', 'daily')),
    soulRings: readJSON(path.join(dataDir, 'anima', 'soul_rings.json')) || [],
    crystals: readJSON(path.join(dataDir, 'lattice', 'crystals.json')) || [],
    persona: readJSON(path.join(dataDir, 'ANIMA_MC.json')),
    userProfile: readJSON(path.join(dataDir, 'ANIMA_USER.json')),
    skillUsageLog: skillUsageLog,
    morphenix: morphenix,
    wee: weeData,
    guardian: guardian,
  };
});

/**
 * Dashboard Tab 4: 記憶瀏覽 — 列出所有有記憶的日期
 */
ipcMain.handle('dashboard-get-memory-dates', async () => {
  const dataDir = getDataDir();
  const memoryDir = path.join(dataDir, 'memory');
  const dates = [];
  const channels = ['meta-thinking', 'event', 'outcome', 'user-reaction'];

  try {
    if (!fs.existsSync(memoryDir)) return { dates: [], channels };
    const years = fs.readdirSync(memoryDir).filter(f => /^\d{4}$/.test(f)).sort();
    for (const year of years) {
      const months = fs.readdirSync(path.join(memoryDir, year)).filter(f => /^\d{2}$/.test(f)).sort();
      for (const month of months) {
        const days = fs.readdirSync(path.join(memoryDir, year, month)).filter(f => /^\d{2}$/.test(f)).sort();
        for (const day of days) {
          dates.push(`${year}-${month}-${day}`);
        }
      }
    }
  } catch (err) {
    console.warn('[Dashboard] Failed to read memory dates:', err.message);
  }
  return { dates: dates.reverse(), channels };  // 最新日期在前
});

/**
 * Dashboard Tab 4: 讀取特定日期的記憶頻道內容
 */
ipcMain.handle('dashboard-read-memory', async (event, date, channel) => {
  const dataDir = getDataDir();
  const [year, month, day] = date.split('-');
  const filePath = path.join(dataDir, 'memory', year, month, day, `${channel}.md`);

  try {
    if (!fs.existsSync(filePath)) return '';
    const raw = fs.readFileSync(filePath, 'utf-8');
    // 最新在頂端：以 markdown 段落分隔符（---/空行+標題）反轉順序
    const sections = raw.split(/\n(?=---|\n##?\s)/);
    return sections.reverse().join('\n');
  } catch (err) {
    console.warn('[Dashboard] Failed to read memory:', filePath, err.message);
    return '';
  }
});

/**
 * Dashboard Tab 4 v2: 合併全頻道日誌（剝除技術欄位）
 */
function parseMemoryEntries(md) {
  if (!md) return [];
  const sections = md.split(/\n(?=## \d{2}:\d{2}:\d{2})/).filter(s => s.trim());
  return sections.map(section => {
    const timeMatch = section.match(/^## (\d{2}:\d{2}:\d{2})/);
    if (!timeMatch) return null;
    const time = timeMatch[1];
    const fields = {};
    const fieldRegex = /\*\*(.+?):\*\*\s*([\s\S]*?)(?=\n\*\*|\n---|$)/g;
    let m;
    while ((m = fieldRegex.exec(section)) !== null) {
      fields[m[1].trim()] = m[2].trim();
    }
    return { time, fields };
  }).filter(Boolean);
}

ipcMain.handle('dashboard-read-memory-merged', async (event, date) => {
  const dataDir = getDataDir();
  const [year, month, day] = date.split('-');
  const dayDir = path.join(dataDir, 'memory', year, month, day);

  try {
    if (!fs.existsSync(dayDir)) return { date, blocks: [] };

    // 讀取所有頻道
    const channelFiles = ['event.md', 'meta-thinking.md', 'outcome.md'];
    const allEntries = new Map(); // time → merged fields

    for (const file of channelFiles) {
      const fp = path.join(dayDir, file);
      if (!fs.existsSync(fp)) continue;
      const raw = fs.readFileSync(fp, 'utf-8');
      const entries = parseMemoryEntries(raw);
      for (const entry of entries) {
        const existing = allEntries.get(entry.time) || {};
        // Merge fields from this channel
        if (entry.fields['User Message']) existing.userMessage = entry.fields['User Message'];
        if (entry.fields['Reasoning']) {
          // 移除 "User asked about: " 前綴
          let reasoning = entry.fields['Reasoning'];
          reasoning = reasoning.replace(/^User asked about:\s*/i, '');
          if (!existing.userMessage) existing.userMessage = reasoning;
        }
        if (entry.fields['Result']) existing.result = entry.fields['Result'];
        if (entry.fields['Response Length']) existing.responseLength = entry.fields['Response Length'];
        existing.time = entry.time;
        allEntries.set(entry.time, existing);
      }
    }

    // 排序 + 群組（5 分鐘內合併）
    const sorted = Array.from(allEntries.values()).sort((a, b) => a.time.localeCompare(b.time));
    const blocks = [];
    let currentBlock = null;

    for (const entry of sorted) {
      if (!entry.userMessage) continue; // 沒有使用者訊息的條目跳過
      if (!currentBlock) {
        currentBlock = { startTime: entry.time, endTime: entry.time, entries: [entry] };
      } else {
        // 計算與前一筆的時間差
        const prevParts = currentBlock.endTime.split(':').map(Number);
        const currParts = entry.time.split(':').map(Number);
        const prevMin = prevParts[0] * 60 + prevParts[1];
        const currMin = currParts[0] * 60 + currParts[1];
        if (currMin - prevMin <= 5) {
          currentBlock.entries.push(entry);
          currentBlock.endTime = entry.time;
        } else {
          blocks.push(currentBlock);
          currentBlock = { startTime: entry.time, endTime: entry.time, entries: [entry] };
        }
      }
    }
    if (currentBlock) blocks.push(currentBlock);

    return { date, blocks };
  } catch (err) {
    console.warn('[Dashboard] Failed to read merged memory:', err.message);
    return { date, blocks: [] };
  }
});

/**
 * Dashboard Tab 4 v2: 全文搜尋記憶
 */
ipcMain.handle('dashboard-search-memory', async (event, query) => {
  const dataDir = getDataDir();
  const memoryDir = path.join(dataDir, 'memory');
  const results = [];
  const lowerQuery = query.toLowerCase();

  try {
    if (!fs.existsSync(memoryDir)) return { query, results: [], totalFound: 0 };
    const years = fs.readdirSync(memoryDir).filter(f => /^\d{4}$/.test(f));
    for (const year of years) {
      const yearDir = path.join(memoryDir, year);
      const months = fs.readdirSync(yearDir).filter(f => /^\d{2}$/.test(f));
      for (const month of months) {
        const monthDir = path.join(yearDir, month);
        const days = fs.readdirSync(monthDir).filter(f => /^\d{2}$/.test(f));
        for (const day of days) {
          const dayDir = path.join(monthDir, day);
          const files = fs.readdirSync(dayDir).filter(f => f.endsWith('.md'));
          for (const file of files) {
            const raw = fs.readFileSync(path.join(dayDir, file), 'utf-8');
            const entries = parseMemoryEntries(raw);
            for (const entry of entries) {
              const userMsg = entry.fields['User Message'] || '';
              let reasoning = entry.fields['Reasoning'] || '';
              reasoning = reasoning.replace(/^User asked about:\s*/i, '');
              const text = userMsg || reasoning;
              if (text.toLowerCase().includes(lowerQuery)) {
                const snippet = text.length > 120 ? text.substring(0, 120) + '...' : text;
                results.push({
                  date: `${year}-${month}-${day}`,
                  time: entry.time,
                  snippet,
                });
              }
            }
          }
        }
      }
    }
  } catch (err) {
    console.warn('[Dashboard] Memory search failed:', err.message);
  }

  // 最新的在前
  results.sort((a, b) => (b.date + b.time).localeCompare(a.date + a.time));
  const limited = results.slice(0, 50);
  return { query, results: limited, totalFound: results.length };
});

/**
 * Dashboard Tab 4 v2: 理解地圖 + 里程碑彙總
 */
ipcMain.handle('dashboard-get-memory-overview', async () => {
  const dataDir = getDataDir();
  const userProfile = readJSON(path.join(dataDir, 'ANIMA_USER.json')) || {};
  const persona = readJSON(path.join(dataDir, 'ANIMA_MC.json')) || {};
  const soulRings = readJSON(path.join(dataDir, 'anima', 'soul_rings.json')) || [];
  const qScores = readJSONL(path.join(dataDir, 'eval', 'q_scores.jsonl'));

  // 統計 matched_skills 出現頻率
  const skillCount = {};
  let totalScore = 0;
  for (const q of qScores) {
    totalScore += q.score || 0;
    for (const skill of (q.matched_skills || [])) {
      skillCount[skill] = (skillCount[skill] || 0) + 1;
    }
  }
  const skillDistribution = Object.entries(skillCount)
    .map(([skill, count]) => ({ skill, count }))
    .sort((a, b) => b.count - a.count);

  const avgQScore = qScores.length > 0 ? totalScore / qScores.length : 0;

  // 計算里程碑
  const relationship = userProfile.relationship || {};
  const totalInteractions = relationship.total_interactions || 0;
  const firstInteraction = relationship.first_interaction || null;
  let daysKnown = 0;
  if (firstInteraction) {
    try {
      daysKnown = Math.max(0, Math.floor((Date.now() - new Date(firstInteraction).getTime()) / 86400000));
    } catch (e) { /* ignore */ }
  }

  const milestoneDefs = [
    { count: 10, label: '初次十次' },
    { count: 50, label: '半百對話' },
    { count: 100, label: '百次記憶' },
    { count: 200, label: '二百默契' },
    { count: 500, label: '五百里程' },
    { count: 1000, label: '千次羈絆' },
  ];
  const achieved = [];
  const upcoming = [];
  for (const ms of milestoneDefs) {
    if (totalInteractions >= ms.count) {
      achieved.push({ count: ms.count, label: ms.label });
    } else {
      upcoming.push({
        count: ms.count,
        label: ms.label,
        progress: totalInteractions / ms.count,
      });
    }
  }

  return {
    userProfile,
    persona,
    skillDistribution,
    avgQScore,
    soulRings,
    milestones: {
      firstInteraction,
      totalInteractions,
      daysKnown,
      trustLevel: relationship.trust_level || 'initial',
      achieved,
      upcoming,
    },
  };
});

// ─── Gateway Info IPC Handler ───

ipcMain.handle('dashboard-get-gateway-info', async () => {
  const pid = gatewayProcess && !gatewayProcess.killed ? gatewayProcess.pid : null;
  const uptimeMs = gatewayStartTime ? Date.now() - gatewayStartTime : 0;
  return {
    pid,
    port: GATEWAY_HTTP_PORT,
    uptime_ms: uptimeMs,
    online: gatewayOnline,
  };
});

// ─── Budget / Key Status IPC Handlers ───

ipcMain.handle('dashboard-get-budget', async () => {
  try {
    return await gatewayHttpGet('/api/budget');
  } catch (err) {
    return { daily_limit: 200000, used: 0, remaining: 200000, percentage: 0, should_warn: false };
  }
});

ipcMain.handle('dashboard-set-budget-limit', async (event, newLimit) => {
  try {
    return await gatewayHttpPost('/api/budget/limit', { daily_limit: newLimit });
  } catch (err) {
    return { success: false, error: err.message };
  }
});

ipcMain.handle('dashboard-get-key-status', async () => {
  try {
    return await gatewayHttpGet('/api/key-status');
  } catch (err) {
    return {};
  }
});

// ─── Guardian 守護者 IPC Handlers（純 CPU）───

ipcMain.handle('dashboard-get-guardian-status', async () => {
  try {
    return await gatewayHttpGet('/api/guardian/status');
  } catch (err) {
    return { error: 'Guardian 不可用', unresolved_count: 0, recent_repairs: [] };
  }
});

ipcMain.handle('dashboard-run-guardian-check', async () => {
  try {
    return await gatewayHttpGet('/api/guardian/check');
  } catch (err) {
    return { error: err.message };
  }
});

// ─── Nightly Pipeline IPC Handlers ───

ipcMain.handle('dashboard-get-nightly-status', async () => {
  try {
    return await gatewayHttpGet('/api/nightly/status');
  } catch (err) {
    return { error: 'Nightly 狀態不可用', status: 'offline' };
  }
});

ipcMain.handle('dashboard-run-nightly', async () => {
  try {
    return await gatewayHttpPost('/api/nightly/run', {});
  } catch (err) {
    return { error: err.message, triggered: false };
  }
});

// ─── Skills IPC Handlers ───

ipcMain.handle('dashboard-get-skills-list', async () => {
  try {
    return await gatewayHttpGet('/api/skills/list');
  } catch (err) {
    return { skills: [], count: 0, error: '技能列表不可用' };
  }
});

ipcMain.handle('dashboard-get-skill-detail', async (event, name) => {
  try {
    return await gatewayHttpGet(`/api/skills/detail/${encodeURIComponent(name)}`);
  } catch (err) {
    return { error: '技能詳情不可用' };
  }
});

ipcMain.handle('dashboard-get-skills-status', async () => {
  try {
    return await gatewayHttpGet('/api/skills-status');
  } catch (err) {
    return { error: '技能狀態不可用' };
  }
});

ipcMain.handle('dashboard-run-skills-scan', async () => {
  try {
    return await gatewayHttpPost('/api/skills/scan', {});
  } catch (err) {
    return { error: err.message };
  }
});

// ─── Multi-Agent IPC Handlers ───

ipcMain.handle('dashboard-get-multiagent-depts', async () => {
  try {
    return await gatewayHttpGet('/api/multiagent/departments');
  } catch (err) {
    return { departments: [], count: 0, error: '部門列表不可用' };
  }
});

ipcMain.handle('dashboard-get-multiagent-status', async () => {
  try {
    return await gatewayHttpGet('/api/multiagent/status');
  } catch (err) {
    return { enabled: false, error: '飛輪狀態不可用' };
  }
});

ipcMain.handle('dashboard-get-multiagent-assets', async () => {
  try {
    return await gatewayHttpGet('/api/multiagent/assets');
  } catch (err) {
    return { assets: [], count: 0, error: '共享資產不可用' };
  }
});

ipcMain.handle('dashboard-test-multiagent-route', async (event, message) => {
  try {
    return await gatewayHttpPost('/api/multiagent/route-test', { message });
  } catch (err) {
    return { error: err.message };
  }
});

// ─── Dispatch IPC Handlers ───

ipcMain.handle('dashboard-get-dispatch-status', async () => {
  try {
    return await gatewayHttpGet('/api/dispatch/status');
  } catch (err) {
    return { active_plans: [], count: 0, error: 'Dispatch 不可用' };
  }
});

ipcMain.handle('dashboard-get-dispatch-history', async () => {
  try {
    return await gatewayHttpGet('/api/dispatch/history');
  } catch (err) {
    return { history: [], count: 0, error: 'Dispatch 不可用' };
  }
});

// ─── Pulse 即時狀態 IPC Handler ───

ipcMain.handle('dashboard-get-pulse-status', async () => {
  try {
    return await gatewayHttpGet('/api/pulse/status');
  } catch (err) {
    return { active_hours: false, interaction_count: 0, error: 'Pulse 不可用' };
  }
});

// ─── Activity Log IPC Handlers ───

ipcMain.handle('dashboard-get-activity-recent', async () => {
  try {
    return await gatewayHttpGet('/api/activity/recent');
  } catch (err) {
    return { events: [], error: 'Activity Log 不可用' };
  }
});

ipcMain.handle('dashboard-get-daily-summary', async (_event, date) => {
  try {
    return await gatewayHttpGet(`/api/daily-summary/${date}`);
  } catch (err) {
    return { error: '日摘要不可用' };
  }
});

ipcMain.handle('dashboard-get-daily-summaries', async () => {
  try {
    return await gatewayHttpGet('/api/daily-summaries');
  } catch (err) {
    return { dates: [], error: '日摘要列表不可用' };
  }
});

// ─── Tools 工具兵器庫 IPC Handlers ───

ipcMain.handle('dashboard-get-tools-list', async () => {
  try {
    return await gatewayHttpGet('/api/tools/list');
  } catch (err) {
    return { tools: [], count: 0, error: '工具庫不可用' };
  }
});

ipcMain.handle('dashboard-get-tools-status', async () => {
  try {
    return await gatewayHttpGet('/api/tools-status');
  } catch (err) {
    return { total: 0, installed: 0, enabled: 0, healthy: 0, error: '工具庫不可用' };
  }
});

ipcMain.handle('dashboard-toggle-tool', async (event, name, enabled) => {
  try {
    return await gatewayHttpPost('/api/tools/toggle', { name, enabled });
  } catch (err) {
    return { success: false, error: err.message };
  }
});

ipcMain.handle('dashboard-run-tools-health', async () => {
  try {
    return await gatewayHttpPost('/api/tools/health');
  } catch (err) {
    return { error: '健康檢查失敗' };
  }
});

ipcMain.handle('dashboard-get-tools-discoveries', async () => {
  try {
    return await gatewayHttpGet('/api/tools/discoveries');
  } catch (err) {
    return { searched: 0, recommended: [], error: '發現紀錄不可用' };
  }
});

ipcMain.handle('dashboard-get-tool-detail', async (event, name) => {
  try {
    return await gatewayHttpGet(`/api/tools/detail/${name}`);
  } catch (err) {
    return { error: '工具不存在' };
  }
});

ipcMain.handle('dashboard-install-tool', async (event, name) => {
  try {
    return await gatewayHttpPost('/api/tools/install', { name });
  } catch (err) {
    return { started: false, error: err.message };
  }
});

ipcMain.handle('dashboard-install-tools-batch', async (event, tools) => {
  try {
    return await gatewayHttpPost('/api/tools/install-batch', { tools });
  } catch (err) {
    return { started: false, error: err.message };
  }
});

ipcMain.handle('dashboard-get-install-progress', async (event, name) => {
  try {
    return await gatewayHttpGet(`/api/tools/install-progress/${name}`);
  } catch (err) {
    return { status: 'idle', progress: 0, message: '查詢失敗', name };
  }
});

// ─── VectorBridge + Sandbox IPC Handlers ───

ipcMain.handle('dashboard-get-vector-status', async () => {
  try {
    return await gatewayHttpGet('/api/vector/status');
  } catch (err) {
    return { available: false, error: err.message, collections: {} };
  }
});

ipcMain.handle('dashboard-vector-search', async (event, collection, query) => {
  try {
    return await gatewayHttpPost('/api/vector/search', { collection, query });
  } catch (err) {
    return { error: err.message, results: [] };
  }
});

ipcMain.handle('dashboard-get-sandbox-status', async () => {
  try {
    return await gatewayHttpGet('/api/sandbox/status');
  } catch (err) {
    return { docker_available: false, error: err.message };
  }
});

// ─── Secretary Dashboard IPC Handlers (零 Token — 本地 JSON 讀寫) ───

ipcMain.handle('dashboard-get-secretary-data', async () => {
  const secDir = path.join(getDataDir(), 'secretary');
  if (!fs.existsSync(secDir)) fs.mkdirSync(secDir, { recursive: true });
  return {
    tasks: readJSON(path.join(secDir, 'tasks.json')) || { tasks: [] },
    projects: readJSON(path.join(secDir, 'projects.json')) || { projects: [] },
    customers: readJSON(path.join(secDir, 'customers.json')) || { customers: [] },
  };
});

ipcMain.handle('dashboard-save-secretary-tasks', async (_event, data) => {
  const secDir = path.join(getDataDir(), 'secretary');
  if (!fs.existsSync(secDir)) fs.mkdirSync(secDir, { recursive: true });
  fs.writeFileSync(path.join(secDir, 'tasks.json'), JSON.stringify(data, null, 2), 'utf-8');
  return { success: true };
});

ipcMain.handle('dashboard-save-secretary-projects', async (_event, data) => {
  const secDir = path.join(getDataDir(), 'secretary');
  if (!fs.existsSync(secDir)) fs.mkdirSync(secDir, { recursive: true });
  fs.writeFileSync(path.join(secDir, 'projects.json'), JSON.stringify(data, null, 2), 'utf-8');
  return { success: true };
});

ipcMain.handle('dashboard-save-secretary-customers', async (_event, data) => {
  const secDir = path.join(getDataDir(), 'secretary');
  if (!fs.existsSync(secDir)) fs.mkdirSync(secDir, { recursive: true });
  fs.writeFileSync(path.join(secDir, 'customers.json'), JSON.stringify(data, null, 2), 'utf-8');
  return { success: true };
});

ipcMain.handle('dashboard-get-secretary-ai-suggestions', async () => {
  const secDir = path.join(getDataDir(), 'secretary');
  const tasks = (readJSON(path.join(secDir, 'tasks.json')) || { tasks: [] }).tasks;
  const projects = (readJSON(path.join(secDir, 'projects.json')) || { projects: [] }).projects;
  const customers = (readJSON(path.join(secDir, 'customers.json')) || { customers: [] }).customers;

  const suggestions = [];
  const today = new Date().toISOString().slice(0, 10);

  // Overdue tasks
  tasks.filter(t => t.status !== 'completed' && t.due_date && t.due_date < today)
    .forEach(t => suggestions.push({
      type: 'warning', source: 'Business-12', icon: '\u26A0\uFE0F',
      title: `${t.title} \u5DF2\u903E\u671F`,
      detail: `\u5230\u671F\u65E5 ${t.due_date}\uFF0C\u5EFA\u8B70\u7ACB\u5373\u8655\u7406\u6216\u91CD\u65B0\u8A55\u4F30\u512A\u5148\u7D1A`,
      related_id: t.id, related_type: 'task'
    }));

  // Due within 3 days
  const threeDaysLater = new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10);
  tasks.filter(t => t.status !== 'completed' && t.due_date && t.due_date >= today && t.due_date <= threeDaysLater && t.priority !== 'low')
    .forEach(t => suggestions.push({
      type: 'urgent', source: '\u4E5D\u7B56\u8ECD\u5E2B', icon: '\uD83C\uDFAF',
      title: `${t.title} \u5373\u5C07\u5230\u671F`,
      detail: `\u5230\u671F\u65E5 ${t.due_date}\uFF0C\u5EFA\u8B70\u4ECA\u5929\u512A\u5148\u8655\u7406`,
      related_id: t.id, related_type: 'task'
    }));

  // Customers needing follow-up (> 14 days no interaction)
  customers.filter(c => c.status === 'active' && c.last_interaction)
    .filter(c => (Date.now() - new Date(c.last_interaction).getTime()) > 14 * 86400000)
    .forEach(c => suggestions.push({
      type: 'reminder', source: 'SSA \u9867\u554F', icon: '\uD83E\uDD1D',
      title: `${c.name} \u8D85\u904E\u5169\u9031\u672A\u806F\u7E6B`,
      detail: `\u4E0A\u6B21\u4E92\u52D5: ${c.last_interaction.slice(0, 10)}\uFF0C\u5EFA\u8B70\u4E3B\u52D5\u8DDF\u9032\u4EE5\u7DAD\u8B77\u95DC\u4FC2`,
      related_id: c.id, related_type: 'customer'
    }));

  // Lead customers with upcoming action dates
  customers.filter(c => c.status === 'lead' && c.next_action_date && c.next_action_date <= threeDaysLater)
    .forEach(c => suggestions.push({
      type: 'opportunity', source: 'Shadow', icon: '\uD83D\uDD0D',
      title: `${c.name} \u65B0\u5BA2\u6236\u7A97\u53E3\u671F`,
      detail: `${c.next_action}\uFF0C\u622A\u6B62 ${c.next_action_date}\uFF0C\u628A\u63E1\u6642\u6A5F\u5EFA\u7ACB\u4FE1\u4EFB`,
      related_id: c.id, related_type: 'customer'
    }));

  // Stalled projects
  projects.filter(p => p.status === 'active' && p.target_date && p.target_date < today && p.progress < 80)
    .forEach(p => suggestions.push({
      type: 'alert', source: 'Business-12', icon: '\uD83D\uDCC9',
      title: `${p.name} \u9032\u5EA6\u843D\u5F8C`,
      detail: `\u76EE\u6A19 ${p.target_date}\uFF0C\u76EE\u524D ${p.progress}%\uFF0C\u5EFA\u8B70\u91CD\u65B0\u8A55\u4F30\u6642\u7A0B\u6216\u8CC7\u6E90\u914D\u7F6E`,
      related_id: p.id, related_type: 'project'
    }));

  // Dependency chain risk: if predecessor not done and successor due soon
  tasks.filter(t => t.status !== 'completed' && t.dependencies && t.dependencies.length > 0)
    .forEach(t => {
      const blockers = t.dependencies.filter(depId => {
        const dep = tasks.find(x => x.id === depId);
        return dep && dep.status !== 'completed';
      });
      if (blockers.length > 0 && t.due_date && t.due_date <= threeDaysLater) {
        const blockerNames = blockers.map(id => (tasks.find(x => x.id === id) || {}).title || id).join('、');
        suggestions.push({
          type: 'chain-risk', source: '\u4E5D\u7B56\u8ECD\u5E2B', icon: '\u26D3\uFE0F',
          title: `${t.title} \u88AB\u524D\u7F6E\u4EFB\u52D9\u5361\u4F4F`,
          detail: `\u4F9D\u8CF4\u65BC\u300C${blockerNames}\u300D\u5C1A\u672A\u5B8C\u6210\uFF0C\u5EFA\u8B70\u512A\u5148\u89E3\u9664\u963B\u585E`,
          related_id: t.id, related_type: 'task'
        });
      }
    });

  return { suggestions, generated_at: new Date().toISOString() };
});

// ─── Setup Wizard IPC Handlers ───

/**
 * Find the .env file path relative to the project directory
 */
function getEnvFilePath() {
  return path.join(getProjectRoot(), '.env');
}

/**
 * Parse .env file into key-value pairs
 */
function parseEnvFile(envPath) {
  const result = {};
  if (!fs.existsSync(envPath)) return result;

  const content = fs.readFileSync(envPath, 'utf-8');
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx > 0) {
      const key = trimmed.substring(0, eqIdx);
      const value = trimmed.substring(eqIdx + 1);
      result[key] = value;
    }
  }
  return result;
}

/**
 * Write a key-value pair to .env file (update existing or append)
 */
function writeEnvKey(envPath, keyName, keyValue) {
  // Ensure directory exists
  const dir = path.dirname(envPath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  let lines = [];
  let keyFound = false;

  if (fs.existsSync(envPath)) {
    lines = fs.readFileSync(envPath, 'utf-8').split('\n');
    for (let i = 0; i < lines.length; i++) {
      const trimmed = lines[i].trim();
      // Match active or commented-out key
      if (trimmed.startsWith(`${keyName}=`) || trimmed.startsWith(`# ${keyName}=`)) {
        lines[i] = `${keyName}=${keyValue}`;
        keyFound = true;
        break;
      }
    }
  }

  if (!keyFound) {
    lines.push(`${keyName}=${keyValue}`);
  }

  fs.writeFileSync(envPath, lines.join('\n') + '\n', 'utf-8');
}

/**
 * Make an HTTPS request and return a Promise
 */
function httpsRequest(url, headers = {}) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const options = {
      hostname: urlObj.hostname,
      port: 443,
      path: urlObj.pathname + urlObj.search,
      method: 'GET',
      headers: headers,
      timeout: 10000,
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        resolve({ status: res.statusCode, data: data });
      });
    });

    req.on('error', (err) => reject(err));
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });
    req.end();
  });
}

/**
 * Check if this is a first run (needs setup wizard)
 */
ipcMain.handle('setup-is-first-run', () => {
  const envPath = getEnvFilePath();
  if (!fs.existsSync(envPath)) return true;

  const env = parseEnvFile(envPath);

  // 即使標記了 SETUP_DONE，如果 API Key 未設定也視為首次
  // 雙重驗證：確保 Key 真的存在且非空
  if (!env['MUSEON_SETUP_DONE']) return true;
  if (!env['ANTHROPIC_API_KEY'] || env['ANTHROPIC_API_KEY'].length < 10) return true;

  return false;
});

// ═══════════════════════════════════════
// Install Mode Detection（版本偵測 + 升級/清裝選擇）
// ═══════════════════════════════════════

/**
 * 計算當前 asar 的 SHA256（生產模式）
 * Dev 模式無 asar，回傳 null
 */
function getCurrentAsarSha256() {
  try {
    const crypto = require('crypto');
    const appPath = app.getAppPath();
    if (appPath.endsWith('.asar') && fs.existsSync(appPath)) {
      const hash = crypto.createHash('sha256');
      hash.update(fs.readFileSync(appPath));
      return hash.digest('hex');
    }
    return null; // dev 模式
  } catch {
    return null;
  }
}

/**
 * 偵測安裝模式：
 *   'fresh'   — 全新安裝（~/MUSEON/ 不存在）
 *   'upgrade' — 偵測到新版本二進位
 *   'normal'  — 一般啟動（版本未變）
 */
function getInstallMode() {
  const homeDir = require('os').homedir();
  const museonHome = path.join(homeDir, 'MUSEON');

  // Case 1: 完全沒有 ~/MUSEON/ → 首次安裝
  if (!fs.existsSync(museonHome)) {
    return { mode: 'fresh' };
  }

  // Case 2: 有舊安裝 → 比對版本
  const markerPath = path.join(museonHome, 'update_marker.json');
  if (!fs.existsSync(markerPath)) {
    return { mode: 'upgrade', reason: 'marker_missing' };
  }

  try {
    const marker = JSON.parse(fs.readFileSync(markerPath, 'utf-8'));
    const currentVersion = app.getVersion();
    const currentSha = getCurrentAsarSha256();
    const lastSha = marker.last_launched_sha256;
    const lastVersion = marker.last_launched_version;

    // 尚未寫入 last_launched_sha256 欄位 → 視為新 binary
    if (!lastSha) {
      return { mode: 'upgrade', reason: 'sha_missing', currentVersion, currentSha };
    }

    // 主要比對：asar SHA256
    if (currentSha && currentSha !== lastSha) {
      return { mode: 'upgrade', reason: 'sha_changed', currentVersion, currentSha };
    }

    // 備援比對：版本號（dev 模式無 asar 用）
    if (!currentSha && currentVersion !== lastVersion) {
      return { mode: 'upgrade', reason: 'version_changed', currentVersion };
    }

    // 相同版本 → 正常啟動
    return { mode: 'normal' };
  } catch (err) {
    console.error('[MUSEON] getInstallMode error:', err);
    return { mode: 'normal' }; // 安全 fallback
  }
}

ipcMain.handle('setup-check-install-mode', () => {
  return getInstallMode();
});

ipcMain.handle('setup-stamp-launched-version', () => {
  const homeDir = require('os').homedir();
  const markerPath = path.join(homeDir, 'MUSEON', 'update_marker.json');

  try {
    let marker = {};
    if (fs.existsSync(markerPath)) {
      marker = JSON.parse(fs.readFileSync(markerPath, 'utf-8'));
    }
    marker.last_launched_version = app.getVersion();
    marker.last_launched_sha256 = getCurrentAsarSha256();
    marker.last_launched_at = new Date().toISOString();

    // 確保目錄存在
    const dir = path.dirname(markerPath);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    fs.writeFileSync(markerPath, JSON.stringify(marker, null, 2), 'utf-8');
    return { success: true };
  } catch (err) {
    return { success: false, message: err.message };
  }
});

ipcMain.handle('setup-archive-data', () => {
  const homeDir = require('os').homedir();
  const museonHome = path.join(homeDir, 'MUSEON');
  const dataDir = path.join(museonHome, 'data');

  if (!fs.existsSync(dataDir)) {
    return { success: true, message: 'No data to archive' };
  }

  const dateStr = new Date().toISOString().slice(0, 10);
  const archiveBase = path.join(museonHome, 'data_archive');
  if (!fs.existsSync(archiveBase)) {
    fs.mkdirSync(archiveBase, { recursive: true });
  }

  // 處理同日多次清裝
  let archiveDir = path.join(archiveBase, dateStr);
  let suffix = 1;
  while (fs.existsSync(archiveDir)) {
    archiveDir = path.join(archiveBase, `${dateStr}-${suffix}`);
    suffix++;
  }

  try {
    // 備份 data/ → data_archive/YYYY-MM-DD/
    fs.renameSync(dataDir, archiveDir);
    fs.mkdirSync(dataDir, { recursive: true }); // 重建空的 data/

    // 備份 .env 並刪除（讓 wizard 重新偵測）
    const envPath = path.join(museonHome, '.env');
    if (fs.existsSync(envPath)) {
      fs.copyFileSync(envPath, path.join(archiveDir, '.env.bak'));
      fs.unlinkSync(envPath);
    }

    return { success: true, archiveDir };
  } catch (err) {
    return { success: false, message: err.message };
  }
});

/**
 * Get setup status for all required keys
 */
ipcMain.handle('setup-get-status', () => {
  const envPath = getEnvFilePath();
  const env = parseEnvFile(envPath);

  const mask = (val) => {
    if (!val) return '';
    if (val.length <= 8) return val.substring(0, 3) + '***';
    return val.substring(0, 8) + '***';
  };

  return {
    ANTHROPIC_API_KEY: {
      configured: !!env['ANTHROPIC_API_KEY'],
      masked_value: mask(env['ANTHROPIC_API_KEY'] || ''),
    },
    TELEGRAM_BOT_TOKEN: {
      configured: !!env['TELEGRAM_BOT_TOKEN'],
      masked_value: mask(env['TELEGRAM_BOT_TOKEN'] || ''),
    },
  };
});

/**
 * Save an API key to .env file
 * 寫入後標記需要重啟 Gateway 以載入新 Key
 */
let gatewayNeedsRestart = false;

ipcMain.handle('setup-save-key', (event, keyName, keyValue) => {
  try {
    const envPath = getEnvFilePath();
    writeEnvKey(envPath, keyName, keyValue);
    gatewayNeedsRestart = true;
    return { success: true, message: `已儲存 ${keyName}` };
  } catch (err) {
    return { success: false, message: `儲存失敗: ${err.message}` };
  }
});

/**
 * Test Anthropic API key
 */
ipcMain.handle('setup-test-anthropic', async (event, key) => {
  try {
    const result = await httpsRequest('https://api.anthropic.com/v1/models', {
      'x-api-key': key,
      'anthropic-version': '2023-06-01',
    });

    if (result.status === 200) {
      return { success: true, message: 'Anthropic API 連線成功' };
    } else if (result.status === 401) {
      return { success: false, message: 'API Key 無效（驗證失敗）' };
    } else {
      return { success: false, message: `API 回應異常: HTTP ${result.status}` };
    }
  } catch (err) {
    return { success: false, message: `連線失敗: ${err.message}` };
  }
});

/**
 * Test Telegram bot token
 */
ipcMain.handle('setup-test-telegram', async (event, token) => {
  try {
    const result = await httpsRequest(`https://api.telegram.org/bot${token}/getMe`);

    if (result.status === 200) {
      const data = JSON.parse(result.data);
      if (data.ok) {
        const botName = data.result.first_name || 'Unknown';
        const botUsername = data.result.username || '';
        const display = botUsername ? `@${botUsername}` : botName;
        return { success: true, message: `Telegram Bot 連線成功 (${display})` };
      }
      return { success: false, message: 'Telegram API 回應異常' };
    } else if (result.status === 401) {
      return { success: false, message: 'Bot Token 無效（驗證失敗）' };
    } else {
      return { success: false, message: `Telegram API 錯誤: HTTP ${result.status}` };
    }
  } catch (err) {
    return { success: false, message: `連線失敗: ${err.message}` };
  }
});

/**
 * Mark setup as complete — 完成後自動重啟 Gateway 以載入新 Key
 */
ipcMain.handle('setup-complete', async () => {
  try {
    const envPath = getEnvFilePath();
    writeEnvKey(envPath, 'MUSEON_SETUP_DONE', '1');

    // 如果 Key 有變更，自動重啟 Gateway 以載入新值
    if (gatewayNeedsRestart) {
      console.log('[MUSEON] Setup complete — restarting Gateway to apply new keys...');
      gatewayNeedsRestart = false;

      // Kill existing Gateway
      if (gatewayProcess && !gatewayProcess.killed) {
        gatewayProcess.kill('SIGTERM');
        await new Promise(r => setTimeout(r, 1000));
        if (!gatewayProcess.killed) gatewayProcess.kill('SIGKILL');
      }

      // Spawn new one (will read updated .env)
      gatewayProcess = spawnGateway();
      const ready = await waitForGatewayReady(15000);
      if (ready) {
        gatewayOnline = true;
        safeSend('gateway-health', { online: true });
        console.log('[MUSEON] Gateway restarted with new keys ✓');
      }
    }

    return { success: true };
  } catch (err) {
    return { success: false, message: err.message };
  }
});

/**
 * 啟動防呆：清除殘留的 MUSEON 進程
 * 安裝/重啟時若有舊進程佔住，會導致新版本無法正常載入
 */
function killStaleProcesses() {
  try {
    const myPid = process.pid;
    // 找出所有 MUSEON 相關進程（不含自己）
    const result = execSync('pgrep -f MUSEON 2>/dev/null || true', { encoding: 'utf8', timeout: 3000 });
    const pids = result.trim().split('\n')
      .map(s => parseInt(s, 10))
      .filter(pid => !isNaN(pid) && pid !== myPid);

    if (pids.length > 0) {
      console.log(`[MUSEON] 偵測到 ${pids.length} 個殘留進程: ${pids.join(', ')}，正在清除...`);
      pids.forEach(pid => {
        try {
          process.kill(pid, 'SIGTERM');
        } catch (e) {
          // 可能已經結束，忽略
        }
      });
      // 等 500ms 後對仍存活的進行強制清除
      const { execSync: es } = require('child_process');
      try { es('sleep 0.5', { timeout: 2000 }); } catch {}
      pids.forEach(pid => {
        try {
          process.kill(pid, 0); // 檢查是否仍存活
          process.kill(pid, 'SIGKILL');
          console.log(`[MUSEON] 強制清除進程 ${pid}`);
        } catch (e) {
          // 已結束，正常
        }
      });
      console.log('[MUSEON] 殘留進程清除完畢 ✓');
    }
  } catch (err) {
    console.warn('[MUSEON] 進程清除檢查失敗（非致命）:', err.message);
  }
}

// ═══════════════════════════════════════
// Runtime Bootstrap（DMG 自帶 Python 原始碼，首次啟動自動部署）
// ═══════════════════════════════════════

/**
 * 取得 DMG 內打包的 runtime-bundle 路徑
 * electron-builder extraResources 會放在 process.resourcesPath 底下
 */
function getBundledRuntimePath() {
  // 生產模式: MUSEON.app/Contents/Resources/runtime-bundle/
  const bundled = path.join(process.resourcesPath, 'runtime-bundle');
  if (fs.existsSync(path.join(bundled, 'pyproject.toml'))) {
    return bundled;
  }
  return null;
}

/**
 * 確保 ~/MUSEON/.runtime/ 已部署 Python 原始碼。
 * 如果 .runtime/ 不存在但 DMG 內有 bundled runtime，自動複製。
 * 如果 venv 不存在，自動建立並安裝依賴。
 *
 * 回傳: { deployed: bool, venvReady: bool, steps: string[] }
 */
async function ensureRuntime() {
  const homeDir = require('os').homedir();
  const museonHome = path.join(homeDir, 'MUSEON');
  const runtimeDir = path.join(museonHome, '.runtime');
  const steps = [];

  // ─── Step 1: 檢查 .runtime/src 是否存在 ───
  if (fs.existsSync(path.join(runtimeDir, 'src', 'museon'))) {
    steps.push('.runtime/src/museon 已存在，跳過部署');

    // 檢查 venv
    const venvPy = path.join(runtimeDir, '.venv', 'bin', 'python3');
    if (fs.existsSync(venvPy)) {
      steps.push('venv 已存在');
      return { deployed: true, venvReady: true, steps };
    }
    // venv 不存在，需要建立
    steps.push('venv 不存在，需要建立');
  } else {
    // ─── Step 2: 從 DMG bundle 複製 ───
    const bundlePath = getBundledRuntimePath();
    if (!bundlePath) {
      steps.push('DMG 內無 runtime-bundle，跳過自動部署');
      return { deployed: false, venvReady: false, steps };
    }

    steps.push(`從 DMG bundle 部署到 ${runtimeDir}...`);

    // 建立目錄
    fs.mkdirSync(runtimeDir, { recursive: true });
    fs.mkdirSync(museonHome, { recursive: true });

    // rsync 複製（保留結構）
    try {
      const { execSync: es } = require('child_process');
      es(`rsync -a "${bundlePath}/" "${runtimeDir}/"`, { timeout: 60000 });
      steps.push('原始碼部署完成');
    } catch (err) {
      steps.push(`部署失敗: ${err.message}`);
      return { deployed: false, venvReady: false, steps };
    }

    // 複製種子資料到使用者目錄（如果是新安裝）
    const userDataDir = path.join(museonHome, 'data');
    if (!fs.existsSync(userDataDir) && fs.existsSync(path.join(runtimeDir, 'data'))) {
      try {
        const { execSync: es } = require('child_process');
        es(`cp -Rn "${runtimeDir}/data/" "${userDataDir}/"`, { timeout: 30000 });
        steps.push('種子資料已複製');
      } catch {
        // cp -n 在目標存在時會失敗，忽略
      }
    }
  }

  // ─── Step 3: 建立 venv + 安裝依賴 ───
  const venvDir = path.join(runtimeDir, '.venv');
  const venvPy = path.join(venvDir, 'bin', 'python3');

  if (!fs.existsSync(venvPy)) {
    // 尋找系統 Python >= 3.11
    const systemPy = findSystemPython();
    if (!systemPy) {
      steps.push('找不到 Python >= 3.11，無法建立 venv');
      return { deployed: true, venvReady: false, steps };
    }

    steps.push(`使用 ${systemPy} 建立 venv...`);
    try {
      const { execSync: es } = require('child_process');
      es(`"${systemPy}" -m venv "${venvDir}"`, { timeout: 30000 });
      steps.push('venv 已建立');
    } catch (err) {
      steps.push(`venv 建立失敗: ${err.message}`);
      return { deployed: true, venvReady: false, steps };
    }
  }

  // 安裝依賴
  try {
    const { execSync: es } = require('child_process');
    // 檢查 fastapi 是否已安裝
    es(`"${venvPy}" -c "import fastapi"`, { timeout: 5000, stdio: 'ignore' });
    steps.push('依賴已安裝');
  } catch {
    steps.push('安裝 Python 依賴（首次需要幾分鐘）...');
    try {
      const { execSync: es } = require('child_process');
      es(`cd "${runtimeDir}" && "${venvPy}" -m pip install -e ".[dev]" --quiet`, {
        timeout: 300000, // 5 分鐘
        stdio: 'pipe',
      });
      steps.push('依賴安裝完成');
    } catch (err) {
      steps.push(`依賴安裝失敗: ${err.message}`);
      return { deployed: true, venvReady: false, steps };
    }
  }

  return { deployed: true, venvReady: true, steps };
}

/**
 * 尋找系統 Python >= 3.11
 */
function findSystemPython() {
  const candidates = ['python3.13', 'python3.12', 'python3.11', 'python3'];
  for (const cmd of candidates) {
    try {
      const { execSync: es } = require('child_process');
      const pyPath = es(`command -v ${cmd}`, { timeout: 3000, encoding: 'utf-8' }).trim();
      if (!pyPath) continue;
      const version = es(`"${pyPath}" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"`, {
        timeout: 3000, encoding: 'utf-8',
      }).trim();
      const [major, minor] = version.split('.').map(Number);
      if (major >= 3 && minor >= 11) return pyPath;
    } catch {
      continue;
    }
  }
  return null;
}

// IPC: 讓 UI 也能觸發 runtime 部署（Setup Wizard 可用）
ipcMain.handle('setup-ensure-runtime', async () => {
  return ensureRuntime();
});

// ═══════════════════════════════════════
// macOS 權限檢查與請求
// ═══════════════════════════════════════

ipcMain.handle('permissions-check-all', async () => {
  const { systemPreferences } = require('electron');
  const { execSync } = require('child_process');
  const permissions = [];

  // 1. Notifications
  permissions.push({
    name: 'notifications',
    label: '通知',
    description: 'Gateway 離線警告、Nightly 完成提醒',
    granted: true,
    canRequest: true,
  });

  // 2. Microphone
  const micStatus = systemPreferences.getMediaAccessStatus('microphone');
  permissions.push({
    name: 'microphone',
    label: '麥克風',
    description: 'Whisper 語音輸入',
    granted: micStatus === 'granted',
    canRequest: micStatus !== 'denied',
  });

  // 3. Camera
  const camStatus = systemPreferences.getMediaAccessStatus('camera');
  permissions.push({
    name: 'camera',
    label: '相機',
    description: '視覺辨識（未來功能）',
    granted: camStatus === 'granted',
    canRequest: camStatus !== 'denied',
  });

  // 4. Accessibility
  let accessibilityGranted = false;
  try {
    execSync(
      'osascript -e \'tell application "System Events" to return name of first process\'',
      { timeout: 3000, encoding: 'utf-8' }
    );
    accessibilityGranted = true;
  } catch { /* not granted */ }
  permissions.push({
    name: 'accessibility',
    label: '輔助使用',
    description: '鍵盤快捷鍵、螢幕朗讀',
    granted: accessibilityGranted,
    canRequest: false,
  });

  // 5. Screen Recording
  let screenGranted = false;
  try {
    execSync(
      'osascript -e \'tell application "System Events" to return name of every window of first process\'',
      { timeout: 5000, encoding: 'utf-8' }
    );
    screenGranted = true;
  } catch { /* not granted */ }
  permissions.push({
    name: 'screen_recording',
    label: '螢幕錄影',
    description: '畫面分析（未來功能）',
    granted: screenGranted,
    canRequest: false,
  });

  // 6. Automation
  let automationGranted = false;
  try {
    execSync(
      'osascript -e \'tell application "Finder" to return name of home\'',
      { timeout: 3000, encoding: 'utf-8' }
    );
    automationGranted = true;
  } catch { /* not granted */ }
  permissions.push({
    name: 'automation',
    label: 'Automation',
    description: '與其他 macOS 應用程式互動',
    granted: automationGranted,
    canRequest: true,
  });

  return { permissions };
});

ipcMain.handle('permissions-request', async (event, name) => {
  const { systemPreferences, shell, Notification } = require('electron');
  const { execSync } = require('child_process');

  switch (name) {
    case 'microphone': {
      const granted = await systemPreferences.askForMediaAccess('microphone');
      return { success: true, granted };
    }
    case 'camera': {
      const granted = await systemPreferences.askForMediaAccess('camera');
      return { success: true, granted };
    }
    case 'notifications': {
      if (Notification.isSupported()) {
        new Notification({ title: 'MUSEON', body: '通知已開啟' }).show();
      }
      return { success: true, granted: true };
    }
    case 'accessibility': {
      shell.openExternal(
        'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'
      );
      return { success: true, granted: false, openedSettings: true };
    }
    case 'screen_recording': {
      shell.openExternal(
        'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture'
      );
      return { success: true, granted: false, openedSettings: true };
    }
    case 'automation': {
      try {
        execSync(
          'osascript -e \'tell application "System Events" to return ""\'',
          { timeout: 10000 }
        );
        return { success: true, granted: true };
      } catch {
        shell.openExternal(
          'x-apple.systempreferences:com.apple.preference.security?Privacy_Automation'
        );
        return { success: true, granted: false, openedSettings: true };
      }
    }
    default:
      return { success: false, error: `Unknown permission: ${name}` };
  }
});

// ═══════════════════════════════════════
// Installer 2.0 — Checkpoint 斷點續裝機制
// ═══════════════════════════════════════

const CHECKPOINT_FILENAME = '.setup_checkpoint.json';

function getCheckpointPath() {
  const homeDir = require('os').homedir();
  return path.join(homeDir, 'MUSEON', CHECKPOINT_FILENAME);
}

function loadCheckpoint() {
  const cpPath = getCheckpointPath();
  try {
    if (fs.existsSync(cpPath)) {
      return JSON.parse(fs.readFileSync(cpPath, 'utf-8'));
    }
  } catch (err) {
    console.warn('[MUSEON] loadCheckpoint error:', err.message);
  }
  return null;
}

function saveCheckpoint(phase, details = {}) {
  const cpPath = getCheckpointPath();
  const dir = path.dirname(cpPath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

  const checkpoint = loadCheckpoint() || { version: app.getVersion(), completed_phase: -1, phase_details: {} };
  checkpoint.version = app.getVersion();
  checkpoint.completed_phase = phase;
  checkpoint.phase_details = { ...checkpoint.phase_details, ...details };
  checkpoint.updated_at = new Date().toISOString();

  // 原子寫入：先寫 .tmp 再 rename
  const tmpPath = cpPath + '.tmp';
  fs.writeFileSync(tmpPath, JSON.stringify(checkpoint, null, 2), 'utf-8');
  fs.renameSync(tmpPath, cpPath);
  return checkpoint;
}

function getResumePhase() {
  const cp = loadCheckpoint();
  if (!cp) return 0; // 全新安裝從 Phase 0 開始
  if (cp.version !== app.getVersion()) return 0; // 版本不同，重新開始
  return Math.min((cp.completed_phase || -1) + 1, 4);
}

/**
 * 判斷是否需要顯示 installer
 * 條件：.env 不存在或 MUSEON_SETUP_DONE 未設定
 */
function needsInstaller() {
  const homeDir = require('os').homedir();
  const envPath = path.join(homeDir, 'MUSEON', '.env');
  if (!fs.existsSync(envPath)) return true;
  const env = parseEnvFile(envPath);
  if (!env['MUSEON_SETUP_DONE']) return true;
  if (!env['ANTHROPIC_API_KEY'] || env['ANTHROPIC_API_KEY'].length < 10) return true;
  return false;
}

// ─── Installer IPC Channels ───

ipcMain.handle('installer-get-checkpoint', () => {
  return loadCheckpoint();
});

ipcMain.handle('installer-save-checkpoint', (event, phase, details) => {
  return saveCheckpoint(phase, details);
});

/**
 * installer-run-bootstrap: Phase 0 全自動引導
 * 拆分 ensureRuntime() 為步驟式，每步推送進度
 */
ipcMain.handle('installer-run-bootstrap', async () => {
  const homeDir = require('os').homedir();
  const museonHome = path.join(homeDir, 'MUSEON');
  const runtimeDir = path.join(museonHome, '.runtime');
  const result = { success: false, steps: [] };

  try {
    // Step 1: 部署 .runtime/（10%）
    safeSend('installer-bootstrap-progress', { percent: 5, status: '準備環境中...' });

    if (!fs.existsSync(path.join(runtimeDir, 'src', 'museon'))) {
      const bundlePath = getBundledRuntimePath();
      if (bundlePath) {
        safeSend('installer-bootstrap-progress', { percent: 8, status: '從安裝包部署原始碼...' });
        fs.mkdirSync(runtimeDir, { recursive: true });
        fs.mkdirSync(museonHome, { recursive: true });
        try {
          execSync(`rsync -a "${bundlePath}/" "${runtimeDir}/"`, { timeout: 60000 });
          result.steps.push('原始碼部署完成');
        } catch (err) {
          result.steps.push(`部署失敗: ${err.message}`);
          safeSend('installer-bootstrap-progress', { percent: 10, status: '部署失敗', error: err.message });
          return result;
        }
        // 複製種子資料
        const userDataDir = path.join(museonHome, 'data');
        if (!fs.existsSync(userDataDir) && fs.existsSync(path.join(runtimeDir, 'data'))) {
          try { execSync(`cp -Rn "${runtimeDir}/data/" "${userDataDir}/"`, { timeout: 30000 }); } catch {}
        }
      } else {
        result.steps.push('開發模式，無需部署 runtime bundle');
      }
    } else {
      result.steps.push('.runtime/src/museon 已存在');
    }
    safeSend('installer-bootstrap-progress', { percent: 10, status: '環境準備完成' });

    // Step 2: 偵測 Python >= 3.11（30%）
    safeSend('installer-bootstrap-progress', { percent: 15, status: '偵測 Python...' });
    const systemPy = findSystemPython();
    if (!systemPy) {
      result.steps.push('找不到 Python >= 3.11');
      safeSend('installer-bootstrap-progress', { percent: 30, status: '找不到 Python >= 3.11', error: 'python_missing' });
      return result;
    }
    result.steps.push(`Python: ${systemPy}`);
    safeSend('installer-bootstrap-progress', { percent: 30, status: `Python: ${systemPy}` });

    // Step 3: 建立 venv + pip install（50%）
    const venvDir = path.join(runtimeDir, '.venv');
    const devVenvDir = path.join(museonHome, '.venv');
    // 支援生產(runtimeDir)和開發(museonHome)兩種佈局
    const targetVenv = fs.existsSync(path.join(runtimeDir, 'src', 'museon')) ? venvDir : devVenvDir;
    const venvPy = path.join(targetVenv, 'bin', 'python3');

    if (!fs.existsSync(venvPy)) {
      safeSend('installer-bootstrap-progress', { percent: 35, status: '建立虛擬環境...' });
      try {
        execSync(`"${systemPy}" -m venv "${targetVenv}"`, { timeout: 30000 });
        result.steps.push('venv 已建立');
      } catch (err) {
        result.steps.push(`venv 建立失敗: ${err.message}`);
        safeSend('installer-bootstrap-progress', { percent: 50, status: 'venv 建立失敗', error: err.message });
        return result;
      }
    }

    // 檢查依賴
    let depsInstalled = false;
    try {
      execSync(`"${venvPy}" -c "import fastapi"`, { timeout: 5000, stdio: 'ignore' });
      depsInstalled = true;
      result.steps.push('依賴已安裝');
    } catch {}

    if (!depsInstalled) {
      safeSend('installer-bootstrap-progress', { percent: 40, status: '安裝 Python 依賴（首次約需 1-3 分鐘）...' });
      const installDir = fs.existsSync(path.join(runtimeDir, 'pyproject.toml')) ? runtimeDir : museonHome;
      try {
        execSync(`cd "${installDir}" && "${venvPy}" -m pip install -e ".[dev]" --quiet`, {
          timeout: 300000, stdio: 'pipe',
        });
        result.steps.push('依賴安裝完成');
      } catch (err) {
        result.steps.push(`依賴安裝失敗: ${err.message}`);
        safeSend('installer-bootstrap-progress', { percent: 50, status: '依賴安裝失敗', error: err.message });
        return result;
      }
    }
    safeSend('installer-bootstrap-progress', { percent: 50, status: 'Python 環境就緒' });

    // Step 4: 偵測 Docker Desktop（80%）
    safeSend('installer-bootstrap-progress', { percent: 60, status: '偵測 Docker...' });
    let dockerStatus = 'unknown';
    try {
      execSync('docker info', { timeout: 10000, stdio: 'ignore' });
      dockerStatus = 'running';
      result.steps.push('Docker Desktop 已運行');
    } catch {
      // 試試 Docker 是否安裝但未啟動
      try {
        execSync('command -v docker', { timeout: 3000, encoding: 'utf-8' });
        dockerStatus = 'installed_not_running';
        result.steps.push('Docker 已安裝但未啟動');
        // 嘗試自動啟動
        try {
          execSync('open -a Docker', { timeout: 5000 });
          result.steps.push('已嘗試啟動 Docker Desktop');
          // 等待 Docker daemon
          for (let i = 0; i < 12; i++) {
            await new Promise(r => setTimeout(r, 5000));
            safeSend('installer-bootstrap-progress', { percent: 65 + i * 1.2, status: `等待 Docker 啟動...（${(i + 1) * 5}s）` });
            try {
              execSync('docker info', { timeout: 5000, stdio: 'ignore' });
              dockerStatus = 'running';
              result.steps.push('Docker 已啟動');
              break;
            } catch {}
          }
        } catch {}
      } catch {
        dockerStatus = 'not_installed';
        result.steps.push('Docker 未安裝');
      }
    }
    safeSend('installer-bootstrap-progress', { percent: 80, status: `Docker: ${dockerStatus}` });

    // Step 5: 完成（100%）
    safeSend('installer-bootstrap-progress', { percent: 100, status: '環境檢查完成' });
    result.success = true;
    result.dockerStatus = dockerStatus;

    // 儲存 checkpoint
    saveCheckpoint(0, {
      bootstrap: {
        runtime_deployed: true,
        venv_ready: true,
        docker_status: dockerStatus,
        python_path: systemPy,
      }
    });

    return result;
  } catch (err) {
    result.steps.push(`未預期錯誤: ${err.message}`);
    safeSend('installer-bootstrap-progress', { percent: 0, status: '錯誤', error: err.message });
    return result;
  }
});

/**
 * installer-run-deploy: Phase 3 全自動部署工具箱
 */
ipcMain.handle('installer-run-deploy', async () => {
  const result = { success: false, steps: [], toolResults: {} };

  try {
    // Step 1: 確保 .env 系統變數完整
    safeSend('installer-deploy-progress', { step: 'env', status: 'running', message: '設定環境變數...' });
    const homeDir = require('os').homedir();
    const museonHome = path.join(homeDir, 'MUSEON');
    const envPath = path.join(museonHome, '.env');
    // 補寫系統變數（不覆蓋已有的 Key）
    const envVars = {
      MUSEON_HOME: museonHome,
      MUSEON_VERSION: app.getVersion(),
    };
    for (const [key, value] of Object.entries(envVars)) {
      const existing = parseEnvFile(envPath);
      if (!existing[key]) {
        writeEnvKey(envPath, key, value);
      }
    }
    result.steps.push('環境變數已設定');
    safeSend('installer-deploy-progress', { step: 'env', status: 'done', message: '環境變數已設定' });

    // Step 2: 啟動 Gateway
    safeSend('installer-deploy-progress', { step: 'gateway', status: 'running', message: '啟動 MUSEON Gateway...' });
    if (gatewayProcess && !gatewayProcess.killed) {
      gatewayProcess.kill('SIGTERM');
      await new Promise(r => setTimeout(r, 1000));
    }
    gatewayProcess = spawnGateway();
    const gwReady = await waitForGatewayReady(20000);
    if (gwReady) {
      gatewayOnline = true;
      result.steps.push('Gateway 啟動成功');
      safeSend('installer-deploy-progress', { step: 'gateway', status: 'done', message: 'Gateway 已啟動' });
    } else {
      result.steps.push('Gateway 啟動逾時（工具安裝仍會繼續）');
      safeSend('installer-deploy-progress', { step: 'gateway', status: 'warning', message: 'Gateway 啟動中...' });
    }

    // Step 3: 偵測/啟動 Docker
    safeSend('installer-deploy-progress', { step: 'docker', status: 'running', message: '偵測 Docker...' });
    let dockerOK = false;
    try {
      execSync('docker info', { timeout: 10000, stdio: 'ignore' });
      dockerOK = true;
      safeSend('installer-deploy-progress', { step: 'docker', status: 'done', message: 'Docker 已就緒' });
    } catch {
      try {
        execSync('command -v docker', { timeout: 3000, encoding: 'utf-8' });
        // Docker 已安裝但未啟動
        safeSend('installer-deploy-progress', { step: 'docker', status: 'running', message: '啟動 Docker Desktop...' });
        try {
          execSync('open -a Docker', { timeout: 5000 });
          // 等待 daemon
          for (let i = 0; i < 12; i++) {
            await new Promise(r => setTimeout(r, 5000));
            try {
              execSync('docker info', { timeout: 5000, stdio: 'ignore' });
              dockerOK = true;
              break;
            } catch {}
          }
        } catch {}
      } catch {}

      if (!dockerOK) {
        result.steps.push('Docker 未就緒');
        safeSend('installer-deploy-progress', { step: 'docker', status: 'docker_missing', message: 'Docker 未安裝或未啟動' });
        // 不回傳失敗，讓 renderer 顯示引導畫面，後續可 retry
        result.dockerMissing = true;
        saveCheckpoint(2, { deploy: { docker_missing: true } });
        return result;
      }
    }
    result.steps.push('Docker 已就緒');

    // Step 4-7: 安裝工具
    const tools = ['searxng', 'qdrant', 'firecrawl', 'whisper'];
    const projectRoot = getProjectRoot();
    const pythonBin = findPython(projectRoot);
    const runtimeSrc = path.join(projectRoot, '.runtime', 'src');
    const srcDir = fs.existsSync(runtimeSrc) ? runtimeSrc : path.join(projectRoot, 'src');

    for (const toolName of tools) {
      safeSend('installer-deploy-progress', {
        step: `tool-${toolName}`, status: 'running',
        message: `安裝 ${toolName}...`
      });
      try {
        const toolResult = await installToolDirect(pythonBin, srcDir, projectRoot, toolName);
        result.toolResults[toolName] = toolResult;
        if (toolResult.success) {
          safeSend('installer-deploy-progress', {
            step: `tool-${toolName}`, status: 'done',
            message: `${toolName} 安裝完成`
          });
        } else {
          safeSend('installer-deploy-progress', {
            step: `tool-${toolName}`, status: 'failed',
            message: `${toolName}: ${toolResult.error || '安裝失敗'}`
          });
        }
      } catch (err) {
        result.toolResults[toolName] = { success: false, error: err.message };
        safeSend('installer-deploy-progress', {
          step: `tool-${toolName}`, status: 'failed',
          message: `${toolName}: ${err.message}`
        });
      }
    }

    // Step 8: 設定 launchd daemon
    safeSend('installer-deploy-progress', { step: 'daemon', status: 'running', message: '設定開機自動啟動...' });
    try {
      setupLaunchdDaemon(projectRoot, pythonBin);
      result.steps.push('launchd daemon 已設定');
      safeSend('installer-deploy-progress', { step: 'daemon', status: 'done', message: '開機自動啟動已設定' });
    } catch (err) {
      result.steps.push(`daemon 設定失敗: ${err.message}`);
      safeSend('installer-deploy-progress', { step: 'daemon', status: 'warning', message: '自動啟動設定失敗（非致命）' });
    }

    result.success = true;
    saveCheckpoint(3, { deploy: { tools: result.toolResults, docker_ok: true } });
    return result;
  } catch (err) {
    result.steps.push(`未預期錯誤: ${err.message}`);
    return result;
  }
});

/**
 * 直接透過 Python 子進程安裝工具（不依賴 Gateway）
 */
function installToolDirect(pythonBin, srcDir, projectRoot, toolName) {
  return new Promise((resolve) => {
    const script = `
import json, sys
sys.path.insert(0, "${srcDir.replace(/"/g, '\\"')}")
try:
    from museon.tools.tool_registry import ToolRegistry
    registry = ToolRegistry()
    result = registry.install_tool("${toolName}")
    print(json.dumps({"success": True, "result": str(result)}))
except Exception as e:
    print(json.dumps({"success": False, "error": str(e)}))
`;
    const proc = spawn(pythonBin, ['-c', script], {
      cwd: projectRoot,
      env: { ...process.env, PYTHONPATH: srcDir, MUSEON_HOME: projectRoot },
      stdio: ['ignore', 'pipe', 'pipe'],
      timeout: 600000, // 10 分鐘
    });

    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (d) => { stdout += d.toString(); });
    proc.stderr.on('data', (d) => { stderr += d.toString(); });
    proc.on('close', (code) => {
      try {
        // 取最後一行 JSON
        const lines = stdout.trim().split('\n');
        for (let i = lines.length - 1; i >= 0; i--) {
          try {
            const parsed = JSON.parse(lines[i]);
            resolve(parsed);
            return;
          } catch {}
        }
        resolve({ success: code === 0, stdout: stdout.slice(-500), stderr: stderr.slice(-500) });
      } catch {
        resolve({ success: false, error: stderr.slice(-500) || `Exit code: ${code}` });
      }
    });
    proc.on('error', (err) => {
      resolve({ success: false, error: err.message });
    });
  });
}

/**
 * 設定 launchd daemon plist
 */
function setupLaunchdDaemon(projectRoot, pythonBin) {
  const homeDir = require('os').homedir();
  const plistDir = path.join(homeDir, 'Library', 'LaunchAgents');
  if (!fs.existsSync(plistDir)) fs.mkdirSync(plistDir, { recursive: true });

  const runtimeSrc = path.join(projectRoot, '.runtime', 'src');
  const srcDir = fs.existsSync(runtimeSrc) ? runtimeSrc : path.join(projectRoot, 'src');

  const plistContent = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.museon.gateway</string>
  <key>ProgramArguments</key>
  <array>
    <string>${pythonBin}</string>
    <string>-m</string>
    <string>museon.gateway.server</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${projectRoot}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>
    <string>${srcDir}</string>
    <key>MUSEON_HOME</key>
    <string>${projectRoot}</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${path.join(projectRoot, 'logs', 'gateway.log')}</string>
  <key>StandardErrorPath</key>
  <string>${path.join(projectRoot, 'logs', 'gateway.err')}</string>
</dict>
</plist>`;

  const plistPath = path.join(plistDir, 'com.museon.gateway.plist');
  fs.writeFileSync(plistPath, plistContent, 'utf-8');

  // 載入 daemon
  try { execSync(`launchctl unload "${plistPath}"`, { timeout: 5000, stdio: 'ignore' }); } catch {}
  execSync(`launchctl load "${plistPath}"`, { timeout: 5000 });
}

/**
 * installer-complete-transition: Installer 完成後切換到 Dashboard 模式
 * 擴大視窗、建立 Tray、啟動 Watchdog
 */
ipcMain.handle('installer-complete-transition', async () => {
  try {
    // 擴大視窗到 Dashboard 尺寸
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.setResizable(true);
      mainWindow.setMaximizable(true);
      mainWindow.setSize(1200, 800, true);
      mainWindow.center();
      // 恢復正常 titleBar
      // 注意：titleBarStyle 無法動態修改，但 hiddenInset 在大視窗也可以接受
    }

    // 建立 Tray
    try { createTray(); } catch (err) { console.warn('[MUSEON] Tray creation failed:', err); }

    // 啟動 Watchdog
    startWatchdog();

    return { success: true };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

/**
 * installer-run-healthcheck: Phase 4 健康檢查
 */
ipcMain.handle('installer-run-healthcheck', async () => {
  const report = {
    gateway: { status: 'unknown' },
    docker: { status: 'unknown' },
    tools: {},
    overall: 'unknown',
  };

  // Gateway 健檢
  const health = await checkGatewayHealth();
  report.gateway = {
    status: health && health.status === 'healthy' ? 'healthy' : 'unhealthy',
    details: health,
  };

  // Docker 健檢
  try {
    execSync('docker info', { timeout: 5000, stdio: 'ignore' });
    report.docker = { status: 'healthy' };
  } catch {
    report.docker = { status: 'unhealthy' };
  }

  // 工具健檢
  const tools = ['searxng', 'qdrant', 'firecrawl', 'whisper'];
  for (const toolName of tools) {
    try {
      const out = execSync(`docker ps --filter "name=museon-${toolName}" --format "{{.Status}}"`, {
        timeout: 5000, encoding: 'utf-8',
      }).trim();
      report.tools[toolName] = { status: out ? 'running' : 'stopped', details: out };
    } catch {
      report.tools[toolName] = { status: 'unknown' };
    }
  }

  // 計算 overall
  const gwOK = report.gateway.status === 'healthy';
  const toolStatuses = Object.values(report.tools);
  const toolsRunning = toolStatuses.filter(t => t.status === 'running').length;
  const toolsFailed = toolStatuses.filter(t => t.status !== 'running' && t.status !== 'unknown').length;

  if (gwOK && toolsRunning === tools.length) {
    report.overall = 'healthy';
  } else if (gwOK && toolsRunning > 0) {
    report.overall = 'partial';
  } else {
    report.overall = 'unhealthy';
  }

  return report;
});

// App lifecycle
app.whenReady().then(async () => {
  // 啟動防呆 — 清除殘留 MUSEON 進程
  killStaleProcesses();

  // ─── 判斷是否需要 installer ───
  const isInstallerMode = needsInstaller();
  console.log('[MUSEON] Install mode:', isInstallerMode ? 'INSTALLER' : 'NORMAL');

  if (isInstallerMode) {
    // ── Installer 模式: 小視窗，由 renderer 驅動全流程 ──
    createWindow({ installerMode: true });

    // 首次啟動預設開啟「開機自動啟動」
    if (!app.getLoginItemSettings().openAtLogin) {
      app.setLoginItemSettings({ openAtLogin: true, openAsHidden: false });
    }

    // Tray 不在 installer 模式建立
    // renderer 的 init() 會偵測 isFirstRun → 啟動 Installer 2.0 流程
    // bootstrap/deploy/healthcheck 全由 IPC handler 處理
  } else {
    // ── 正常模式: 大視窗 + 啟動 Gateway ──

    // DMG 自帶 runtime 首次部署（正常模式也可能需要更新）
    const runtimeResult = await ensureRuntime();
    console.log('[MUSEON] ensureRuntime:', JSON.stringify(runtimeResult));

    createWindow();

    // 首次啟動預設開啟「開機自動啟動」
    if (!app.getLoginItemSettings().openAtLogin) {
      app.setLoginItemSettings({ openAtLogin: true, openAsHidden: false });
      console.log('[MUSEON] Auto-launch enabled by default');
    }

    // Tray 建立失敗不應阻止視窗顯示
    try {
      createTray();
    } catch (err) {
      console.error('[MUSEON] Failed to create tray (non-fatal):', err);
    }

    // Check if Gateway is already running (HTTP health check)
    const existingHealth = await checkGatewayHealth();
    if (existingHealth && existingHealth.status === 'healthy') {
      gatewayOnline = true;
      console.log('[MUSEON] Found existing Gateway (HTTP /health OK)');
      safeSend('gateway-health', { online: true });
    } else {
      // Gateway 不在線 — 先嘗試 launchctl load daemon（如果 plist 存在）
      const plistPath = path.join(
        require('os').homedir(), 'Library', 'LaunchAgents', 'com.museon.gateway.plist'
      );
      if (fs.existsSync(plistPath)) {
        console.log('[MUSEON] Found daemon plist, trying launchctl load...');
        try {
          const { execSync } = require('child_process');
          // 先 unload 清理殘留
          try { execSync(`launchctl unload "${plistPath}"`, { timeout: 5000, stdio: 'ignore' }); } catch {}
          execSync(`launchctl load "${plistPath}"`, { timeout: 5000 });
          console.log('[MUSEON] launchctl load succeeded, waiting for Gateway...');
          const daemonReady = await waitForGatewayReady(10000);
          if (daemonReady) {
            gatewayOnline = true;
            console.log('[MUSEON] Daemon-managed Gateway is online ✓');
            safeSend('gateway-health', { online: true });
            startWatchdog();
            return; // 不需要 spawn，daemon 已經在管了
          }
          console.log('[MUSEON] Daemon Gateway not ready after 10s, falling back to spawn...');
        } catch (daemonErr) {
          console.warn('[MUSEON] launchctl load failed:', daemonErr.message);
        }
      }
      // Fallback: No daemon or daemon failed — auto-spawn
      console.log('[MUSEON] No running Gateway found, auto-spawning...');
      try {
        gatewayProcess = spawnGateway();
        console.log('[MUSEON] Gateway spawned (PID: ' + gatewayProcess.pid + ')');

        // 等 Gateway HTTP /health 變為 healthy（最多 15 秒）
        const ready = await waitForGatewayReady(15000);
        if (ready) {
          gatewayOnline = true;
          console.log('[MUSEON] Auto-spawned Gateway is online ✓');
          safeSend('gateway-health', { online: true });
        } else {
          console.error('[MUSEON] Gateway spawned but HTTP health check failed after 15s');
        }
      } catch (spawnErr) {
        console.error('[MUSEON] Failed to auto-spawn Gateway:', spawnErr.message);
      }
    }

    // Start watchdog
    startWatchdog();
  }

  // macOS dock 點擊 → 顯示已隱藏的視窗或建立新視窗
  app.on('activate', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
      mainWindow.focus();
    } else {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  // Don't quit on macOS when all windows are closed
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  app.isQuitting = true;

  // Clean up
  if (watchdogInterval) {
    clearInterval(watchdogInterval);
  }

  // 結束 Gateway 子進程
  if (gatewayProcess && !gatewayProcess.killed) {
    gatewayProcess.kill('SIGTERM');
  }
});
