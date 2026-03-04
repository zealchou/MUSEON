/**
 * MUSEON Dashboard — Pure Vanilla JavaScript
 *
 * No React, no JSX, no bundler needed.
 * Runs directly in Electron's Chromium renderer.
 *
 * 四層防黑畫面機制：
 *   L0 — 全域錯誤攔截（window.onerror + unhandledrejection）
 *   L1 — render() fragment-first error boundary
 *   L2 — init() 超時保護（10 秒強制脫離 loading）
 *   L3 — renderCrashScreen() 診斷畫面（取代黑畫面）
 */

// ═══════════════════════════════════════
// L0: 全域錯誤攔截器 — 最後防線，完全獨立
// ═══════════════════════════════════════
(function installGlobalErrorHandlers() {
  /**
   * 直接用 DOM API 寫入錯誤訊息，不依賴 h() / render() / state
   * 確保即使 app.js 中任何函式壞掉，使用者仍看到錯誤資訊
   */
  function showFatalError(source, message, stack) {
    var root = document.getElementById('root');
    if (!root) return;
    // 如果 root 已有內容（render 成功過），不覆蓋
    if (root.children.length > 0) return;

    root.innerHTML =
      '<div style="padding:3rem;max-width:600px;margin:0 auto;font-family:monospace">' +
        '<div style="font-size:3rem;margin-bottom:1rem">🐾</div>' +
        '<h1 style="color:#e8dcc6;margin-bottom:0.5rem">MUSEON 啟動異常</h1>' +
        '<p style="color:#9a8b70;margin-bottom:1.5rem">來源：' + source + '</p>' +
        '<div style="background:#1a2340;border:1px solid #222d4a;border-radius:0.75rem;padding:1.5rem;' +
          'font-size:0.8rem;white-space:pre-wrap;word-break:break-all">' +
          '<div style="color:#ef4444;font-weight:700;margin-bottom:0.5rem">' +
            message.replace(/</g, '&lt;') +
          '</div>' +
          '<div style="color:#6b5f4a">' +
            (stack || '(no stack)').replace(/</g, '&lt;') +
          '</div>' +
        '</div>' +
        '<button onclick="location.reload()" style="margin-top:1.5rem;padding:0.75rem 2rem;' +
          'background:#c9a96e;color:white;border:none;border-radius:0.5rem;cursor:pointer;font-size:1rem">' +
          '重新載入' +
        '</button>' +
      '</div>';
  }

  window.onerror = function(message, source, lineno, colno, error) {
    console.error('[MUSEON L0] Uncaught error:', message, source, lineno, colno, error);
    showFatalError(
      'window.onerror @ ' + (source || '?') + ':' + (lineno || '?'),
      String(message),
      error ? error.stack : null
    );
    // 回傳 true = 阻止瀏覽器預設的錯誤輸出
    return true;
  };

  window.onunhandledrejection = function(event) {
    var reason = event.reason || {};
    console.error('[MUSEON L0] Unhandled rejection:', reason);
    showFatalError(
      'unhandledrejection',
      String(reason.message || reason),
      reason.stack || null
    );
  };
})();

// ═══════════════════════════════════════
// State
// ═══════════════════════════════════════
const state = {
  activeTab: 'secretary',
  gatewayOnline: false,
  showSetupWizard: false,
  loading: true,
  // Brain state (Tab 1)
  brainState: null,
  // Evolution data (Tab 2)
  evolutionData: null,
  // Memory browser (Tab 3) — v2 shared journal
  memoryDates: [],
  selectedMemoryDate: null,
  memoryLoading: false,
  memorySubTab: 'journal',            // journal | search | understanding | milestones
  memoryJournalBlocks: null,          // parsed conversation blocks for selected date
  memorySearchQuery: '',              // search input text
  memorySearchResults: null,          // search results array
  memorySearchLoading: false,
  memoryOverview: null,               // understanding + milestones data
  memoryOverviewLoading: false,
  // Charts instance tracking
  charts: {},
  // Topology instance
  topology: null,
  // Auto-refresh
  refreshing: false,
  _refreshTimer: null,
  // Gateway repair
  gatewayRepairing: false,
  gatewayLogs: [],       // { level, message, time }
  showGatewayPanel: false,
  // Telegram status
  telegramStatus: null,
  telegramRestarting: false,
  // Doctor
  doctorReport: null,
  doctorLoading: false,
  doctorRepairing: {},  // { action: true/false }
  // Install Mode Selector
  showModeSelector: false,
  installMode: null,
  modeSelected: null,     // 'upgrade' | 'clean' | 'new-instance'
  modeArchiving: false,
  // Setup Wizard
  wizardStep: 0,
  anthropicKey: '',
  telegramToken: '',
  anthropicValid: null,
  telegramValid: null,
  showAnthropicKey: false,
  showTelegramToken: false,
  saving: false,
  testResults: {
    anthropic: { status: 'pending', message: '' },
    telegram: { status: 'pending', message: '' },
  },
  // Secretary Dashboard
  secretaryData: null,
  secretaryLoading: false,
  secretaryModalItem: null,
  secretaryGanttZoom: 'week',
  secretaryAiSuggestions: null,
  // Activity Log + Daily Summary (Evolution tab)
  activityRecent: null,
  dailySummary: null,          // 當前顯示的日摘要
  dailySummaryDates: [],       // 所有可用日期
  dailySummaryDate: null,      // 選中的日期
  evoMemoryCollapsed: true,    // 記憶日誌區塊預設收合
  // 工具兵器庫
  toolsList: null,
  toolsStatus: null,
  toolsLoading: false,
  toolsHealthChecking: false,
  toolsDiscoveries: null,
  // 工具安裝狀態
  toolInstalling: {},        // { name: { status, progress, message } }
  toolInstallPollers: {},     // { name: intervalId }
  // Setup Wizard 工具選擇
  wizardToolsSelected: {},    // { name: true/false }
  wizardToolsInstalling: false,
  wizardToolsProgress: {},    // { name: { status, progress, message } }
  wizardToolsDone: false,
  // Dify 工作流引擎
  difyStatus: null,
  difyToolCount: 4,
  // Budget stats
  budgetStats: null,
  routingStats: null,
  // Gateway info (Hero card)
  gatewayInfo: null,
  // Auto-launch toggle
  autoLaunchEnabled: true,  // 預設 ON（與 main.js 一致）
  // Guardian 守護者
  guardianStatus: null,
  guardianChecking: false,
  // Nightly Pipeline
  nightlyStatus: null,
  nightlyRunning: false,
  // 幣別切換
  costCurrency: 'TWD',  // 'USD' | 'TWD' — 預設新台幣
  // 設定區塊收合（預設收合）
  settingsGeneralCollapsed: true,
  settingsApiKeyCollapsed: true,
  telegramCollapsed: true,
  // 模型分流展開（嵌入節省報告中）
  routingDetailExpanded: false,
  // 自動發現展開（工具庫）
  discoveryExpanded: null,  // index or null
  // Token 節省明細
  savingsBreakdown: null,
  // 語系切換
  lang: 'zh-TW',  // 'zh-TW' | 'en'
  // MCP 連接器管理
  mcpCatalog: null,          // [{ name, display_name, status, tools_count, ... }]
  mcpLoading: false,
  mcpCollapsed: true,        // MCP 面板收合/展開
  mcpModalServer: null,      // 目前開啟 Modal 的 server 物件
  mcpCategoryFilter: 'all',  // 分類篩選：'all' | 'search' | ...
  mcpConnecting: {},         // { name: true/false }
  mcpEnvInputs: {},          // { name: { KEY: value } }
  // 知識結晶分組收合
  crystalGroupExpanded: {},     // { Insight: true, Pattern: false, ... } — 預設全收合
  crystalSearchQuery: '',       // 搜尋框
  crystalSortBy: 'date',       // 'date' | 'quality'
};

const TOTAL_STEPS = 6;
const root = document.getElementById('root');

// Tab configuration
const TAB_IDS = ['secretary', 'organism', 'evolution', 'tools', 'doctor', 'settings'];
const TAB_NAMES_ZH = {
  secretary: '📋 秘書台',
  organism: '🧬 生命',
  evolution: '📈 演化',
  memory: '🧠 記憶',
  tools: '🛠️ 工具庫',
  doctor: '🩺 健檢',
  settings: '⚙️ 設定',
};
const TAB_NAMES_EN = {
  secretary: '📋 Secretary',
  organism: '🧬 Life',
  evolution: '📈 Evolution',
  memory: '🧠 Memory',
  tools: '🛠️ Tools',
  doctor: '🩺 Health',
  settings: '⚙️ Settings',
};
function TAB_NAMES() { return state.lang === 'en' ? TAB_NAMES_EN : TAB_NAMES_ZH; }

// ═══════════════════════════════════════
// Utilities
// ═══════════════════════════════════════
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'className') el.className = v;
      else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
      else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (k === 'disabled') { if (v) el.disabled = true; }
      else if (k === 'type') el.type = v;
      else if (k === 'placeholder') el.placeholder = v;
      else if (k === 'value') el.value = v;
      else if (k === 'href') { el.href = v; }
      else if (k === 'target') el.target = v;
      else if (k === 'rel') el.rel = v;
      else if (k === 'autofocus') el.autofocus = v;
      else if (k === 'id') el.id = v;
      else if (k === 'width') el.width = v;
      else if (k === 'height') el.height = v;
      else el.setAttribute(k, v);
    }
  }
  for (const child of children) {
    if (child == null || child === false) continue;
    if (typeof child === 'string' || typeof child === 'number') {
      el.appendChild(document.createTextNode(child));
    } else if (child instanceof Node) {
      el.appendChild(child);
    } else if (Array.isArray(child)) {
      child.forEach(c => { if (c instanceof Node) el.appendChild(c); });
    }
  }
  return el;
}

// ═══════════════════════════════════════
// Simple Markdown Parser
// ═══════════════════════════════════════
function parseMarkdown(md) {
  if (!md) return [h('p', { style: { color: '#6b5f4a' } }, '此頻道尚無記錄')];
  const lines = md.split('\n');
  const nodes = [];
  let listItems = [];

  function flushList() {
    if (listItems.length > 0) {
      nodes.push(h('ul', { style: { margin: '0.5rem 0', paddingLeft: '1.5rem', color: '#e8dcc6' } }, ...listItems));
      listItems = [];
    }
  }

  function inlineParse(text) {
    // Handle **bold** patterns
    const parts = [];
    let remaining = text;
    while (remaining.length > 0) {
      const boldIdx = remaining.indexOf('**');
      if (boldIdx === -1) {
        parts.push(document.createTextNode(remaining));
        break;
      }
      if (boldIdx > 0) {
        parts.push(document.createTextNode(remaining.slice(0, boldIdx)));
      }
      const endIdx = remaining.indexOf('**', boldIdx + 2);
      if (endIdx === -1) {
        parts.push(document.createTextNode(remaining.slice(boldIdx)));
        break;
      }
      const strong = h('strong', { style: { color: '#f1f5f9' } }, remaining.slice(boldIdx + 2, endIdx));
      parts.push(strong);
      remaining = remaining.slice(endIdx + 2);
    }
    return parts;
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith('# ')) {
      flushList();
      const heading = h('h2', { style: { color: '#e8dcc6', fontSize: '1.25rem', margin: '1rem 0 0.5rem' } });
      inlineParse(line.slice(2)).forEach(n => heading.appendChild(n));
      nodes.push(heading);
    } else if (line.startsWith('## ')) {
      flushList();
      const heading = h('h3', { style: { color: '#cbd5e1', fontSize: '1.1rem', margin: '0.75rem 0 0.4rem' } });
      inlineParse(line.slice(3)).forEach(n => heading.appendChild(n));
      nodes.push(heading);
    } else if (line.startsWith('---')) {
      flushList();
      nodes.push(h('hr', { style: { border: 'none', borderTop: '1px solid #222d4a', margin: '1rem 0' } }));
    } else if (line.startsWith('- ')) {
      const li = h('li', { style: { marginBottom: '0.25rem' } });
      inlineParse(line.slice(2)).forEach(n => li.appendChild(n));
      listItems.push(li);
    } else if (line.trim() === '') {
      flushList();
    } else {
      flushList();
      const p = h('p', { style: { color: '#e8dcc6', margin: '0.4rem 0', lineHeight: '1.6' } });
      inlineParse(line).forEach(n => p.appendChild(n));
      nodes.push(p);
    }
  }
  flushList();
  return nodes;
}

// ═══════════════════════════════════════
// Render Engine
// ═══════════════════════════════════════
function render() {
  try {
    // ── 保存捲軸位置（防止自動刷新跳回頂端）──
    const contentEl = document.querySelector('.content');
    const savedScroll = contentEl ? contentEl.scrollTop : 0;
    const savedTab = state.activeTab;

    const fragment = document.createDocumentFragment();
    if (state.loading) {
      fragment.appendChild(renderLoading());
    } else if (state.showModeSelector) {
      fragment.appendChild(renderModeSelector());
    } else if (state.showSetupWizard) {
      fragment.appendChild(renderSetupWizard());
    } else {
      fragment.appendChild(renderApp());
    }
    // 只有渲染成功才清空並替換（永不黑畫面）
    root.innerHTML = '';
    root.appendChild(fragment);

    // ── 還原捲軸位置（同一個 tab 才還原）──
    if (savedScroll > 0 && state.activeTab === savedTab) {
      requestAnimationFrame(() => {
        const newContentEl = document.querySelector('.content');
        if (newContentEl) {
          newContentEl.scrollTop = savedScroll;
        }
      });
    }

    afterRender();
  } catch (err) {
    console.error('[MUSEON] render() crashed:', err);
    // 錯誤邊界：顯示診斷資訊，永遠不會黑畫面
    root.innerHTML = '';
    root.appendChild(renderCrashScreen(err));
  }
}

/**
 * 錯誤邊界 — 取代黑畫面，顯示可操作的診斷資訊
 */
function renderCrashScreen(err) {
  const envPath = '__dirname: ' + (typeof __dirname !== 'undefined' ? __dirname : 'N/A');
  return h('div', { id: 'app', style: { padding: '3rem', maxWidth: '600px', margin: '0 auto' } },
    h('div', { style: { fontSize: '3rem', marginBottom: '1rem' } }, '🐾'),
    h('h1', { style: { color: '#e8dcc6', marginBottom: '0.5rem' } }, 'MUSEON 控制台發生錯誤'),
    h('p', { style: { color: '#9a8b70', marginBottom: '1.5rem' } },
      '渲染過程中發生異常。以下是診斷資訊：'),
    h('div', {
      className: 'card',
      style: { fontFamily: 'monospace', fontSize: '0.8rem', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }
    },
      h('div', { style: { color: '#ef4444', marginBottom: '0.5rem', fontWeight: '700' } },
        err.name + ': ' + err.message),
      h('div', { style: { color: '#6b5f4a' } }, err.stack || '(no stack)'),
      h('div', { style: { color: '#475569', marginTop: '1rem', borderTop: '1px solid #222d4a', paddingTop: '0.5rem' } },
        'state.loading = ' + state.loading + '\n' +
        'state.showSetupWizard = ' + state.showSetupWizard + '\n' +
        'state.wizardStep = ' + state.wizardStep + '\n' +
        envPath)
    ),
    h('div', { style: { marginTop: '1.5rem', display: 'flex', gap: '1rem' } },
      h('button', {
        className: 'wizard-btn-primary',
        onClick: () => { state.loading = false; state.showSetupWizard = false; render(); }
      }, '嘗試載入控制台'),
      h('button', {
        className: 'wizard-btn-secondary',
        onClick: () => { state.loading = false; state.showSetupWizard = true; state.wizardStep = 0; render(); }
      }, '重新啟動精靈')
    )
  );
}

// ═══════════════════════════════════════
// Loading Screen
// ═══════════════════════════════════════
function renderLoading() {
  return h('div', { id: 'app' },
    h('div', { className: 'loading' },
      h('div', { className: 'spinner' }),
      h('p', null, '載入中...')
    )
  );
}

// ═══════════════════════════════════════
// Main App — Four Tabs
// ═══════════════════════════════════════
function renderApp() {
  return h('div', { id: 'app' },
    renderNav(),
    h('div', { className: 'content' }, renderTabContent()),
    renderCrystalModal()
  );
}

function renderNav() {
  const bs = state.brainState;
  const growthStage = bs && bs.persona && bs.persona.identity
    ? bs.persona.identity.growth_stage : null;

  return h('nav', { className: 'nav' },
    h('div', { className: 'nav-title' },
      'MUSEON',
      growthStage ? h('span', {
        style: {
          marginLeft: '0.75rem', fontSize: '0.75rem', padding: '0.15rem 0.6rem',
          background: '#c9a96e', borderRadius: '9999px', color: '#fff',
        }
      }, stageLabel(growthStage)) : null
    ),
    h('div', { className: 'nav-tabs' },
      ...TAB_IDS.map(tab =>
        h('button', {
          className: `nav-tab ${state.activeTab === tab ? 'active' : ''}`,
          onClick: () => {
            if (state.activeTab === tab) return;
            state.activeTab = tab;
            refreshActiveTab();
          }
        }, TAB_NAMES()[tab])
      )
    ),
    h('div', { className: 'nav-right' },
      h('button', {
        className: 'refresh-btn',
        onClick: () => refreshActiveTab(),
        disabled: state.refreshing,
      }, state.refreshing ? '⏳' : '🔄'),
      h('div', {
        className: 'status-indicator',
        style: { cursor: 'pointer' },
        onClick: () => { state.showGatewayPanel = !state.showGatewayPanel; render(); },
      },
        h('div', { className: `status-dot ${state.gatewayOnline ? '' : 'offline'}` }),
        h('span', null, state.gatewayOnline
          ? (state.lang === 'en' ? 'Online' : '上線中')
          : (state.lang === 'en' ? 'Offline' : '離線中'))
      ),
      !state.gatewayOnline ? h('button', {
        className: 'repair-btn',
        onClick: handleGatewayRepair,
        disabled: state.gatewayRepairing,
      }, state.gatewayRepairing ? '修復中...' : '🔧 修復') : null,
      h('button', {
        className: 'lang-toggle-btn',
        onClick: () => { state.lang = state.lang === 'zh-TW' ? 'en' : 'zh-TW'; render(); },
        title: state.lang === 'zh-TW' ? 'Switch to English' : '切換為繁體中文',
      }, state.lang === 'zh-TW' ? 'EN' : '中')
    )
  );
}

function renderTabContent(overrideTab) {
  const tab = overrideTab || state.activeTab;
  const content = (() => {
    switch (tab) {
      case 'secretary': return renderSecretary();
      case 'organism': return renderOrganism();
      case 'evolution': return renderEvolution();
      case 'tools': return renderTools();
      case 'doctor': return renderDoctor();
      case 'settings': return renderSettings();
      default: return renderOrganism();
    }
  })();

  // Gateway log panel overlay
  if (state.showGatewayPanel) {
    return h('div', { style: { position: 'relative', flex: '1', overflow: 'hidden' } },
      content,
      renderGatewayPanel()
    );
  }
  return content;
}

// ═══════════════════════════════════════
// Tab 1: 🧬 生命 (Organism)
// ═══════════════════════════════════════

// ── 12 級演化體系（逆熵流設計 — 3 年重度使用者封頂逆推）──
const EVOLUTION_STAGES = [
  { key: 'seed',       label: '種子',   emoji: '\u{1F330}', xp: 0,       color: '#6b5f4a' },
  { key: 'sprout',     label: '萌芽',   emoji: '\u{1F331}', xp: 500,     color: '#8bc34a' },
  { key: 'sapling',    label: '幼苗',   emoji: '\u{1F33F}', xp: 2500,    color: '#4caf50' },
  { key: 'bloom',      label: '綻放',   emoji: '\u{1F338}', xp: 8000,    color: '#e91e63' },
  { key: 'branch',     label: '枝展',   emoji: '\u{1F333}', xp: 20000,   color: '#2196f3' },
  { key: 'crystal',    label: '結晶',   emoji: '\u{1F48E}', xp: 45000,   color: '#00bcd4' },
  { key: 'pulse',      label: '脈動',   emoji: '\u{1F4AB}', xp: 85000,   color: '#9c27b0' },
  { key: 'weave',      label: '織網',   emoji: '\u{1F578}\uFE0F', xp: 140000, color: '#673ab7' },
  { key: 'radiance',   label: '輝光',   emoji: '\u2728',    xp: 220000,  color: '#ff9800' },
  { key: 'storm',      label: '風暴',   emoji: '\u{1F300}', xp: 330000,  color: '#f44336' },
  { key: 'cosmos',     label: '星宇',   emoji: '\u{1F30C}', xp: 480000,  color: '#3f51b5' },
  { key: 'transcend',  label: '超越',   emoji: '\u{1F451}', xp: 700000,  color: '#c9a96e' },
];

function getEvolutionStage(totalXP) {
  let stage = EVOLUTION_STAGES[0];
  for (let i = EVOLUTION_STAGES.length - 1; i >= 0; i--) {
    if (totalXP >= EVOLUTION_STAGES[i].xp) { stage = EVOLUTION_STAGES[i]; break; }
  }
  const idx = EVOLUTION_STAGES.indexOf(stage);
  const nextStage = EVOLUTION_STAGES[Math.min(idx + 1, EVOLUTION_STAGES.length - 1)];
  const progress = nextStage.xp > stage.xp
    ? Math.min(100, Math.round(((totalXP - stage.xp) / (nextStage.xp - stage.xp)) * 100))
    : 100;
  return { stage, idx, nextStage, progress };
}

// ── 8 種生物形態（MBTI 式分類）──
const CREATURE_ARCHETYPES = {
  luminos:     { name: '靈光體',   emoji: '\u{1F52E}', desc: '理解+表達',  color: '#3b82f6', axes: ['U','C'] },
  ironroot:    { name: '鐵根獸',   emoji: '\u{1F9A3}', desc: '行動+知識',  color: '#f59e0b', axes: ['A','K'] },
  voidweaver:  { name: '虛空織者', emoji: '\u{1F300}', desc: '深度+直覺',  color: '#8b5cf6', axes: ['D','I'] },
  stormcaller: { name: '風暴使',   emoji: '\u26A1',    desc: '行動+深度',  color: '#ef4444', axes: ['A','D'] },
  crystalmind: { name: '晶核智',   emoji: '\u{1F48E}', desc: '知識+理解',  color: '#06b6d4', axes: ['K','U'] },
  phantasm:    { name: '幻相師',   emoji: '\u{1F319}', desc: '直覺+表達',  color: '#ec4899', axes: ['I','C'] },
  aegis:       { name: '全護衛',   emoji: '\u{1F6E1}\uFE0F', desc: '均衡型', color: '#10b981', axes: [] },
  chimera:     { name: '奇美拉',   emoji: '\u{1F409}', desc: '極端特化',   color: '#c9a96e', axes: [] },
};

function classifyCreature(abilityAxes) {
  // abilityAxes: [{label, value, key:'U'|'D'|'C'|'A'|'K'|'I'}]
  const values = abilityAxes.map(a => a.value);
  const mean = values.reduce((s, v) => s + v, 0) / values.length;
  const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / values.length;
  const stdDev = Math.sqrt(variance);

  // 均衡型
  if (stdDev < 8) return CREATURE_ARCHETYPES.aegis;

  // 排序取 top-2
  const sorted = abilityAxes.map(a => ({ key: a.key, value: a.value }))
    .sort((a, b) => b.value - a.value);
  const top1 = sorted[0], top2 = sorted[1];

  // 極端特化
  if (top1.value > 85 && (top1.value - top2.value) > 25) return CREATURE_ARCHETYPES.chimera;

  // 匹配 top-2 組合
  const pair = new Set([top1.key, top2.key]);
  for (const [id, arch] of Object.entries(CREATURE_ARCHETYPES)) {
    if (arch.axes.length === 2) {
      const archPair = new Set(arch.axes);
      if (pair.size === archPair.size && [...pair].every(k => archPair.has(k))) return arch;
    }
  }
  // fallback: 最接近的
  return CREATURE_ARCHETYPES.aegis;
}

// ── SVG helper ──
function svg(tag, attrs, ...children) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  if (attrs) Object.keys(attrs).forEach(k => {
    if (k.startsWith('on') && typeof attrs[k] === 'function') {
      el.addEventListener(k.slice(2).toLowerCase(), attrs[k]);
    } else if (k === 'style' && typeof attrs[k] === 'string') {
      el.setAttribute('style', attrs[k]);
    } else {
      el.setAttribute(k, attrs[k]);
    }
  });
  children.forEach(c => {
    if (c == null) return;
    if (typeof c === 'string') el.textContent = c;
    else el.appendChild(c);
  });
  return el;
}

// ── SVG 六軸雷達圖 ──
function renderRadarChart(abilityAxes, creature) {
  const CX = 150, CY = 140, R = 105;
  const N = abilityAxes.length; // 6
  const angles = abilityAxes.map((_, i) => (Math.PI * 2 * i / N) - Math.PI / 2);

  function hexPoint(cx, cy, r, angle) {
    return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
  }
  function hexPoints(cx, cy, r) {
    return angles.map(a => hexPoint(cx, cy, r, a));
  }
  function pointsStr(pts) {
    return pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
  }

  // 背景六邊形 (3 層)
  const bgLayers = [0.33, 0.66, 1.0].map(scale =>
    svg('polygon', {
      points: pointsStr(hexPoints(CX, CY, R * scale)),
      fill: 'none', stroke: '#222d4a', 'stroke-width': '1'
    })
  );

  // 軸線
  const axisLines = angles.map(a => {
    const [ex, ey] = hexPoint(CX, CY, R, a);
    return svg('line', {
      x1: String(CX), y1: String(CY), x2: ex.toFixed(1), y2: ey.toFixed(1),
      stroke: '#222d4a', 'stroke-width': '1'
    });
  });

  // 數據多邊形
  const dataPoints = abilityAxes.map((axis, i) => {
    const val = Math.max(3, axis.value) / 100;
    return hexPoint(CX, CY, R * val, angles[i]);
  });
  const dataPolygon = svg('polygon', {
    points: pointsStr(dataPoints),
    fill: (creature.color || '#c9a96e') + '25',
    stroke: creature.color || '#c9a96e',
    'stroke-width': '2',
    'stroke-linejoin': 'round'
  });

  // 數據點
  const dataDots = dataPoints.map((p, i) =>
    svg('circle', {
      cx: p[0].toFixed(1), cy: p[1].toFixed(1), r: '3',
      fill: abilityAxes[i].color, stroke: '#0d1424', 'stroke-width': '1'
    })
  );

  // 軸端標籤
  const labels = abilityAxes.map((axis, i) => {
    const [lx, ly] = hexPoint(CX, CY, R + 22, angles[i]);
    const anchor = lx < CX - 5 ? 'end' : lx > CX + 5 ? 'start' : 'middle';
    const g = svg('g', {});
    g.appendChild(svg('text', {
      x: lx.toFixed(1), y: (ly - 2).toFixed(1),
      'text-anchor': anchor, 'font-size': '10', fill: '#9a8b70',
      'font-weight': '500'
    }, axis.icon + ' ' + axis.label));
    g.appendChild(svg('text', {
      x: lx.toFixed(1), y: (ly + 11).toFixed(1),
      'text-anchor': anchor, 'font-size': '11', fill: axis.color,
      'font-weight': '700'
    }, String(axis.value)));
    return g;
  });

  const svgEl = svg('svg', { viewBox: '0 0 300 300', class: 'radar-svg' },
    ...bgLayers, ...axisLines, dataPolygon, ...dataDots, ...labels
  );

  // 生物形態徽章
  const creatureBadge = h('div', { className: 'creature-badge', style: { borderColor: creature.color + '40' } },
    h('span', { className: 'creature-emoji' }, creature.emoji),
    h('span', { className: 'creature-name', style: { color: creature.color } }, creature.name),
    h('span', { className: 'creature-desc' }, creature.desc)
  );

  return h('div', { className: 'card radar-chart-card' },
    h('div', { className: 'section-header' },
      h('span', { className: 'section-icon' }, '\u2B21'),
      h('span', null, '能力雷達')
    ),
    h('div', { className: 'radar-chart-body' }, svgEl),
    creatureBadge
  );
}

// ── 精簡版 Organism Header ──
function renderOrganismHeader(identity, creature, evolData, totalXP, memDays, qHistory, crystals, soulRings) {
  const { stage, idx, progress } = evolData;
  const name = identity.name || 'MUSEON';
  const birthDate = identity.birth_date ? new Date(identity.birth_date) : null;
  const aliveDays = birthDate ? Math.max(1, Math.floor((Date.now() - birthDate.getTime()) / 86400000)) : memDays || 0;
  const avgQ = qHistory.length > 0
    ? Math.round(qHistory.reduce((s, q) => s + (q.score || 0), 0) / qHistory.length * 100) : 0;

  return h('div', { className: 'organism-header' },
    h('div', { className: 'organism-header-top' },
      h('div', { className: 'organism-identity' },
        h('span', { className: 'organism-stage-emoji' }, stage.emoji),
        h('span', { className: 'organism-name' }, name),
        h('span', { className: 'organism-creature-tag', style: { color: creature.color, borderColor: creature.color + '40' } },
          creature.emoji + ' ' + creature.name),
        h('span', { className: 'organism-level-tag', style: { background: stage.color + '30', color: stage.color } },
          'Lv.' + (idx + 1) + ' ' + stage.label)
      ),
      h('div', { className: `gateway-indicator ${state.gatewayOnline ? 'online' : 'offline'}` },
        h('div', { className: 'gateway-dot' }),
        h('span', null, state.gatewayOnline ? '上線中' : '離線')
      )
    ),
    h('div', { className: 'xp-section' },
      h('div', { className: 'xp-label' },
        h('span', null, '經驗值'),
        h('span', { className: 'xp-value' }, formatNumber(totalXP) + ' XP')
      ),
      h('div', { className: 'xp-bar' },
        h('div', { className: 'xp-bar-fill', style: { width: progress + '%', background: `linear-gradient(90deg, ${stage.color}88, ${stage.color})` } }),
        h('div', { className: 'xp-bar-glow', style: { width: progress + '%' } })
      ),
      h('div', { className: 'xp-sublabel' },
        progress >= 100 ? '已達最高階段' : '距離下個階段 ' + progress + '%')
    ),
    h('div', { className: 'character-stats' },
      renderStatChip('\u{1F4AB}', '品質', avgQ + '%'),
      renderStatChip('\u{1F4C5}', '存活', aliveDays + ' 天'),
      renderStatChip('\u{1F48E}', '結晶', String(crystals.length)),
      renderStatChip('\u{1F300}', '年輪', String(soulRings.length)),
      renderStatChip('\u{1F525}', '互動', String(qHistory.length) + ' 次')
    )
  );
}

function renderOrganism() {
  const bs = state.brainState;
  if (!bs) {
    return h('div', { className: 'tab-empty' },
      h('div', { style: { fontSize: '3rem', marginBottom: '1rem' } }, '\u{1F9EC}'),
      h('p', { style: { color: '#9a8b70', fontSize: '1.1rem' } }, '正在載入生命資料...'),
      h('p', { style: { color: '#6b5f4a', fontSize: '0.875rem', marginTop: '0.5rem' } },
        '如果持續載入，請確認閘道器已啟動')
    );
  }

  const persona = bs.persona || {};
  const identity = persona.identity || {};
  const crystals = bs.crystals || [];
  const soulRings = bs.soulRings || [];
  const memDays = bs.memoryDays || 0;
  const qHistory = bs.qScoreHistory || [];
  const skillUsageLog = bs.skillUsageLog || [];
  const intuition = bs.intuition || {};

  // XP 計算（新 12 級體系）
  const totalXP = qHistory.length * 100 + crystals.length * 250 + soulRings.length * 500 + (intuition.count || 0) * 50;
  const evolData = getEvolutionStage(totalXP);

  // 六維能力值（加上 key 供生物形態分類）
  const dims = { understanding: 0, depth: 0, clarity: 0, actionability: 0 };
  if (qHistory.length > 0) {
    const recent = qHistory.slice(-10);
    recent.forEach(q => {
      dims.understanding += (q.understanding || 0);
      dims.depth += (q.depth || 0);
      dims.clarity += (q.clarity || 0);
      dims.actionability += (q.actionability || 0);
    });
    Object.keys(dims).forEach(k => dims[k] = Math.round((dims[k] / recent.length) * 100));
  }

  const abilityAxes = [
    { label: '理解力',   value: dims.understanding, icon: '\u{1F9E0}', color: '#3b82f6', key: 'U' },
    { label: '思考深度', value: dims.depth,          icon: '\u{1F52C}', color: '#8b5cf6', key: 'D' },
    { label: '表達力',   value: dims.clarity,        icon: '\u{1F4AC}', color: '#10b981', key: 'C' },
    { label: '行動力',   value: dims.actionability,  icon: '\u26A1',    color: '#f59e0b', key: 'A' },
    { label: '知識量',   value: Math.min(100, crystals.length * 10 + soulRings.length * 20), icon: '\u{1F4DA}', color: '#ec4899', key: 'K' },
    { label: '直覺',     value: Math.min(100, (intuition.count || 0) * 3), icon: '\u2728', color: '#06b6d4', key: 'I' },
  ];

  // 生物形態分類
  const creature = classifyCreature(abilityAxes);

  // 技能排行
  const skillCounts = {};
  skillUsageLog.forEach(log => {
    (log.skills || []).forEach(s => { skillCounts[s] = (skillCounts[s] || 0) + 1; });
  });
  const topSkills = Object.entries(skillCounts).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const maxSkillCount = topSkills.length > 0 ? topSkills[0][1] : 1;

  return h('div', { className: 'organism-tab' },
    renderOrganismHeader(identity, creature, evolData, totalXP, memDays, qHistory, crystals, soulRings),
    h('div', { className: 'organism-main-panel' },
      h('div', { className: 'card starmap-container' },
        h('div', { className: 'section-header' },
          h('span', { className: 'section-icon' }, '\u{1F30C}'),
          h('span', null, '知識星圖')
        ),
        h('canvas', { id: 'topology-canvas', width: 900, height: 400, style: { width: '100%', height: '400px', display: 'block' } })
      ),
      renderRadarChart(abilityAxes, creature)
    ),
    renderDualAnimaPanel(),
    h('div', { className: 'rpg-dual-panel' },
      renderSkillEquipment(topSkills, maxSkillCount),
      renderNeuralModules(bs)
    )
  );
}

// ── 雙 ANIMA 八原語面板 ──
function renderDualAnimaPanel() {
  const bs = state.brainState;
  if (!bs) return null;

  const mcAnima = bs.persona || {};
  const userAnima = bs.userProfile || {};
  const mcPrimals = mcAnima.eight_primals || {};
  const userPrimals = userAnima.eight_primals || {};

  // MUSEON 八原語定義（乾坤震巽坎離艮兌）
  const MC_AXES = [
    { key: 'qian_identity',  label: '乾·身份', emoji: '☰', color: '#f59e0b' },
    { key: 'kun_memory',     label: '坤·記憶', emoji: '☷', color: '#8b5cf6' },
    { key: 'zhen_action',    label: '震·行動', emoji: '☳', color: '#ef4444' },
    { key: 'xun_curiosity',  label: '巽·好奇', emoji: '☴', color: '#22c55e' },
    { key: 'kan_resonance',  label: '坎·共振', emoji: '☵', color: '#3b82f6' },
    { key: 'li_awareness',   label: '離·覺察', emoji: '☲', color: '#f97316' },
    { key: 'gen_boundary',   label: '艮·邊界', emoji: '☶', color: '#78716c' },
    { key: 'dui_connection', label: '兌·連結', emoji: '☱', color: '#ec4899' },
  ];

  // User 八原語定義（觀察視角）
  const USER_AXES = [
    { key: 'aspiration',        label: '志向',     emoji: '☰', color: '#f59e0b' },
    { key: 'accumulation',      label: '累積',     emoji: '☷', color: '#8b5cf6' },
    { key: 'action_power',      label: '行動力',   emoji: '☳', color: '#ef4444' },
    { key: 'curiosity',         label: '好奇心',   emoji: '☴', color: '#22c55e' },
    { key: 'emotion_pattern',   label: '情感模式', emoji: '☵', color: '#3b82f6' },
    { key: 'blindspot',         label: '盲點',     emoji: '☲', color: '#f97316' },
    { key: 'boundary',          label: '邊界',     emoji: '☶', color: '#78716c' },
    { key: 'relationship_depth', label: '關係',     emoji: '☱', color: '#ec4899' },
  ];

  function renderOctagonRadar(axes, primals, accentColor, title, subtitle) {
    const CX = 120, CY = 115, R = 90;
    const N = 8;
    const angleStep = (Math.PI * 2) / N;

    function pt(r, i) {
      const a = angleStep * i - Math.PI / 2;
      return { x: CX + r * Math.cos(a), y: CY + r * Math.sin(a) };
    }

    // 背景三環八邊形
    const bgRings = [0.33, 0.66, 1.0].map(pct => {
      const pts = Array.from({ length: N }, (_, i) => pt(R * pct, i));
      return svg('polygon', {
        points: pts.map(p => p.x + ',' + p.y).join(' '),
        fill: 'none', stroke: '#222d4a', 'stroke-width': '0.8'
      });
    });

    // 軸線
    const axisLines = Array.from({ length: N }, (_, i) => {
      const p = pt(R, i);
      return svg('line', { x1: CX, y1: CY, x2: p.x, y2: p.y, stroke: '#1a2540', 'stroke-width': '0.6' });
    });

    // 數據多邊形
    const values = axes.map(a => {
      const p = primals[a.key];
      return p ? (p.level || 0) : 0;
    });
    const dataPts = values.map((v, i) => pt(R * Math.max(v, 3) / 100, i));
    const dataPolygon = svg('polygon', {
      points: dataPts.map(p => p.x + ',' + p.y).join(' '),
      fill: accentColor + '18', stroke: accentColor, 'stroke-width': '1.5', 'stroke-linejoin': 'round'
    });

    // 數據點
    const dataCircles = dataPts.map((p, i) =>
      svg('circle', { cx: p.x, cy: p.y, r: '2.5', fill: axes[i].color, stroke: '#0e1425', 'stroke-width': '1' })
    );

    // 軸標籤
    const labelOffset = 15;
    const labels = axes.map((a, i) => {
      const p = pt(R + labelOffset, i);
      const anchor = p.x < CX - 5 ? 'end' : p.x > CX + 5 ? 'start' : 'middle';
      const dy = p.y < CY - 20 ? '-0.2em' : p.y > CY + 20 ? '1em' : '0.35em';
      return svg('text', {
        x: p.x, y: p.y, fill: a.color, 'font-size': '8.5', 'text-anchor': anchor, dy: dy,
        'font-weight': '600'
      }, a.emoji + ' ' + a.label);
    });

    // 中心數值
    const avgLevel = values.length > 0 ? Math.round(values.reduce((s, v) => s + v, 0) / values.length) : 0;
    const centerText = svg('text', {
      x: CX, y: CY + 2, fill: accentColor, 'font-size': '16', 'text-anchor': 'middle',
      'font-weight': '700', opacity: '0.6'
    }, String(avgLevel));

    const svgEl = svg('svg', { viewBox: '0 0 240 230', style: 'width:100%;max-height:230px' },
      ...bgRings, ...axisLines, dataPolygon, ...dataCircles, ...labels, centerText
    );

    // 八原語小卡片列表
    const detailItems = axes.map(a => {
      const p = primals[a.key] || {};
      const level = p.level || 0;
      const signal = p.signal || '尚無觀察';
      const confidence = p.confidence != null ? Math.round(p.confidence * 100) : null;
      return h('div', { className: 'primal-item' },
        h('div', { className: 'primal-item-header' },
          h('span', { style: { color: a.color, fontWeight: '700', fontSize: '0.75rem' } }, a.emoji + ' ' + a.label),
          h('span', { className: 'primal-level', style: { color: a.color } }, String(level))
        ),
        h('div', { className: 'primal-bar' },
          h('div', { className: 'primal-bar-fill', style: { width: level + '%', background: a.color } })
        ),
        h('div', { className: 'primal-signal' },
          signal.length > 40 ? signal.substring(0, 40) + '…' : signal,
          confidence != null ? h('span', { className: 'primal-conf' }, ' ' + confidence + '% 信心') : null
        )
      );
    });

    return h('div', { className: 'card anima-panel' },
      h('div', { className: 'section-header' },
        h('span', { className: 'section-icon' }, title.charAt(0) === '☰' ? '☰' : '🪞'),
        h('span', null, title),
        h('span', { className: 'anima-subtitle' }, subtitle)
      ),
      svgEl,
      h('div', { className: 'primal-list' }, ...detailItems)
    );
  }

  const mcPanel = renderOctagonRadar(
    MC_AXES, mcPrimals, '#c9a96e',
    '☰ 霓裳八原語', '自我定義 · 乾坤震巽坎離艮兌'
  );

  const userPanel = renderOctagonRadar(
    USER_AXES, userPrimals, '#22c55e',
    '🪞 使用者觀察', '志向 · 累積 · 行動力 · 好奇心 · 情感 · 盲點 · 邊界 · 關係'
  );

  return h('div', { className: 'dual-anima-panel' }, mcPanel, userPanel);
}

// ── renderCharacterCard / renderAbilityRadar — superseded by renderOrganismHeader + renderRadarChart (above) ──

function renderStatChip(icon, label, value) {
  return h('div', { className: 'stat-chip' },
    h('span', { className: 'stat-chip-icon' }, icon),
    h('div', { className: 'stat-chip-body' },
      h('span', { className: 'stat-chip-value' }, value),
      h('span', { className: 'stat-chip-label' }, label)
    )
  );
}

function formatNumber(n) {
  if (n >= 10000) return (n / 1000).toFixed(1) + 'k';
  if (n >= 1000) return n.toLocaleString();
  return String(n);
}

// ── 技能裝備欄 ──
function renderSkillEquipment(topSkills, maxCount) {
  const skillIcons = {
    'c15': '🖋️', 'deep-think': '🧠', 'dna27': '🧬', 'eval-engine': '📊',
    'market-core': '📈', 'plugin-registry': '📦', 'text-alchemy': '✨',
    'user-model': '👤', 'morphenix': '🔥', 'sandbox-lab': '🧪',
    'business-12': '💼', 'brand-identity': '🎨', 'gap': '🔍',
    'ssa-consultant': '🤝', 'storytelling-engine': '📖', 'resonance': '💜',
    'dharma': '☯️', 'xmodel': '🌀', 'pdeif': '🎯', 'orchestrator': '🎼',
    'master-strategy': '⚔️', 'market-equity': '🏛️', 'market-crypto': '₿',
    'market-macro': '🌍', 'plan-engine': '📋', 'workflow-ai-deployment': '🚀',
    'workflow-svc-brand-marketing': '📣', 'knowledge-lattice': '💎',
    'investment-masters': '🎖️', 'aesthetic-sense': '🌸', 'risk-matrix': '🛡️',
    'sentiment-radar': '📡', 'shadow': '🌑', 'philo-dialectic': '⚖️',
    'novel-craft': '📝', 'consultant-communication': '🎙️', 'meta-learning': '🎓',
    'wee': '♻️', 'dse': '🔧', 'env-radar': '🛰️', 'info-architect': '📐',
    'acsf': '⚒️', 'qa-auditor': '🔎',
  };

  return h('div', { className: 'card skill-equip-card' },
    h('div', { className: 'section-header' },
      h('span', { className: 'section-icon' }, '⚔️'),
      h('span', null, '技能裝備'),
      h('span', { className: 'section-count' }, topSkills.length + ' 已裝備')
    ),
    topSkills.length > 0
      ? h('div', { className: 'skill-equip-list' },
          ...topSkills.map(([skill, count]) => {
            const pct = Math.round((count / maxCount) * 100);
            const icon = skillIcons[skill] || '🔮';
            const label = skillLabels[skill] || skill;
            const profLevel = count >= 50 ? 'S' : count >= 20 ? 'A' : count >= 10 ? 'B' : count >= 5 ? 'C' : 'D';
            const profColor = { S: '#c9a96e', A: '#8b5cf6', B: '#3b82f6', C: '#10b981', D: '#6b5f4a' };
            return h('div', { className: 'skill-equip-item' },
              h('span', { className: 'skill-equip-icon' }, icon),
              h('div', { className: 'skill-equip-body' },
                h('div', { className: 'skill-equip-header' },
                  h('span', { className: 'skill-equip-name' }, label),
                  h('span', { className: 'skill-equip-rank', style: { color: profColor[profLevel] } }, profLevel)
                ),
                h('div', { className: 'skill-equip-bar-bg' },
                  h('div', { className: 'skill-equip-bar-fill', style: { width: pct + '%' } })
                )
              ),
              h('span', { className: 'skill-equip-count' }, String(count))
            );
          })
        )
      : h('div', { className: 'equip-empty' }, '尚未裝備任何技能')
  );
}

// ── 神經束模組 ──
function renderNeuralModules(bs) {
  const crystals = bs.crystals || [];
  const soulRings = bs.soulRings || [];
  const qHistory = bs.qScoreHistory || [];
  const intuition = bs.intuition || {};
  const planEngine = bs.planEngine || {};

  const modules = [
    { emoji: '🌀', name: '靈魂年輪', on: soulRings.length > 0, count: soulRings.length, unit: '環', desc: '從失敗中淬煉的成長印記', color: '#8b5cf6' },
    { emoji: '📊', name: '品質引擎', on: qHistory.length > 0, count: qHistory.length, unit: '筆分析', desc: '每次回答的品質追蹤', color: '#3b82f6' },
    { emoji: '✨', name: '直覺迴路', on: !!intuition.active, count: intuition.count || 0, unit: '則記憶', desc: '情境感知與模式識別', color: '#f59e0b' },
    { emoji: '💎', name: '知識晶格', on: crystals.length > 0, count: crystals.length, unit: '結晶', desc: '驗證過的智慧資產', color: '#ec4899' },
    { emoji: '📋', name: '計畫引擎', on: !!planEngine.active, count: planEngine.count || 0, unit: '計畫', desc: '從混沌到清晰的收斂器', color: '#10b981' },
  ];

  return h('div', { className: 'neural-modules' },
    h('div', { className: 'section-header section-header-standalone' },
      h('span', { className: 'section-icon' }, '🧩'),
      h('span', null, '神經束')
    ),
    h('div', { className: 'neural-grid' },
      ...modules.map(m =>
        h('div', { className: `neural-card ${m.on ? 'active' : 'dormant'}` },
          h('div', { className: 'neural-card-header' },
            h('span', { className: 'neural-emoji' }, m.emoji),
            h('div', { className: 'neural-status-dot', style: { background: m.on ? m.color : '#2d3a5c' } })
          ),
          h('div', { className: 'neural-card-name' }, m.name),
          h('div', { className: 'neural-card-count', style: { color: m.on ? m.color : '#4a4035' } },
            String(m.count), h('span', { className: 'neural-card-unit' }, ' ' + m.unit)
          ),
          h('div', { className: 'neural-card-desc' }, m.desc),
          h('div', { className: 'neural-card-bar' },
            h('div', { className: 'neural-card-bar-fill', style: { width: m.on ? '100%' : '0%', background: m.color } })
          )
        )
      )
    )
  );
}

// 後端 growth_stage 值: infant / child / teen / adult
const STAGE_ZH = { infant: '幼生期', child: '成長期', teen: '蛻變期', adult: '成熟期' };
function stageLabel(stage) { return STAGE_ZH[stage] || stage || '未知'; }
function stageColor(stage) {
  const map = { infant: '#c9a96e', child: '#10b981', teen: '#f59e0b', adult: '#8b5cf6' };
  return map[stage] || '#6b5f4a';
}

// renderVitalItem 保留給 evolution 和其他 tab 使用
function renderVitalItem(label, content) {
  return h('div', { className: 'vital-item' },
    h('div', { className: 'vital-label' }, label),
    h('div', { className: 'vital-value' }, content)
  );
}

// ═══════════════════════════════════════
// Tab 2: 📈 演化 (Evolution)
// ═══════════════════════════════════════
function renderEvolution() {
  const ed = state.evolutionData;
  if (!ed) {
    return h('div', { className: 'tab-empty' },
      h('div', { style: { fontSize: '3rem', marginBottom: '1rem' } }, '📈'),
      h('p', { style: { color: '#9a8b70', fontSize: '1.1rem' } }, '正在載入演化資料...'),
      h('div', { className: 'spinner', style: { margin: '1rem auto' } })
    );
  }

  const qHistory = ed.qScoreHistory || [];
  const crystals = ed.crystals || [];
  const soulRings = ed.soulRings || [];
  const dailySummaries = ed.dailySummaries || [];
  const persona = ed.persona || {};
  const identity = persona.identity || {};
  const skillUsageLog = ed.skillUsageLog || [];
  const morphenix = ed.morphenix || { notes: [], proposals: [] };
  const wee = ed.wee || { workflows: [] };

  const totalInteractions = qHistory.length;
  const birthDate = identity.birth_date ? new Date(identity.birth_date) : null;
  const aliveDays = birthDate ? Math.max(1, Math.floor((Date.now() - birthDate.getTime()) / 86400000)) : 0;
  const avgQ = qHistory.length > 0
    ? ((qHistory.reduce((s, q) => s + (q.score || 0), 0) / qHistory.length) * 100).toFixed(1) : '—';

  // Q-Score sparkline data (last 20)
  const sparkData = qHistory.slice(-20).map(q => Math.round((q.score || 0) * 100));
  const sparkMax = Math.max(...sparkData, 1);
  const sparkMin = Math.min(...sparkData, 0);

  // 技能使用排行
  const skillCounts = {};
  skillUsageLog.forEach(log => {
    (log.skills || []).forEach(s => { skillCounts[s] = (skillCounts[s] || 0) + 1; });
  });
  const topSkills = Object.entries(skillCounts).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const maxSkillUsage = topSkills.length > 0 ? topSkills[0][1] : 1;

  return h('div', { className: 'evolution-tab' },
    // ═══ 演化概覽 Hero ═══
    h('div', { className: 'evo-hero' },
      renderEvoHeroStat('🔥', '總互動', String(totalInteractions), '次'),
      renderEvoHeroStat('📅', '存活天數', String(aliveDays), '天'),
      renderEvoHeroStat('💎', '知識結晶', String(crystals.length), '枚'),
      renderEvoHeroStat('📊', '平均品質', String(avgQ), '%'),
      renderEvoHeroStat('🌀', '靈魂年輪', String(soulRings.length), '環')
    ),

    // ═══ 📊 今日摘要 ═══
    renderDailySummary(),

    // ═══ 📋 活動日誌 ═══
    renderActivityLog(),

    // ═══ 雙欄：品質趨勢 + 技能成長 ═══
    h('div', { className: 'evo-dual-panel' },
      // 左：品質趨勢迷你圖
      h('div', { className: 'card evo-chart-card' },
        h('div', { className: 'section-header' },
          h('span', { className: 'section-icon' }, '📈'),
          h('span', null, '品質趨勢')
        ),
        sparkData.length > 1
          ? renderSparkline(sparkData, sparkMin, sparkMax)
          : h('div', { className: 'evo-empty-state' },
              h('div', { className: 'evo-empty-icon' }, '📊'),
              h('div', { className: 'evo-empty-text' }, '累積更多互動後顯示趨勢')
            ),
        // Q-Score 分布條
        qHistory.length > 0 ? renderQDistribution(qHistory) : null
      ),
      // 右：技能熟練度排行
      h('div', { className: 'card evo-chart-card' },
        h('div', { className: 'section-header' },
          h('span', { className: 'section-icon' }, '⚔️'),
          h('span', null, '技能成長排行')
        ),
        topSkills.length > 0
          ? h('div', { className: 'evo-skill-ranks' },
              ...topSkills.map(([skill, count], idx) => {
                const pct = Math.round((count / maxSkillUsage) * 100);
                const label = skillLabels[skill] || skill;
                const medal = idx === 0 ? '🥇' : idx === 1 ? '🥈' : idx === 2 ? '🥉' : '　';
                return h('div', { className: 'evo-skill-rank-item' },
                  h('span', { className: 'evo-skill-medal' }, medal),
                  h('span', { className: 'evo-skill-rank-name' }, label),
                  h('div', { className: 'evo-skill-rank-bar-bg' },
                    h('div', { className: 'evo-skill-rank-bar-fill', style: { width: pct + '%' } })
                  ),
                  h('span', { className: 'evo-skill-rank-count' }, String(count))
                );
              })
            )
          : h('div', { className: 'evo-empty-state' },
              h('div', { className: 'evo-empty-icon' }, '⚔️'),
              h('div', { className: 'evo-empty-text' }, '開始對話後解鎖技能')
            )
      )
    ),

    // ═══ 靈魂年輪時間線 ═══
    h('div', { className: 'card' },
      h('div', { className: 'section-header' },
        h('span', { className: 'section-icon' }, '🌀'),
        h('span', null, '靈魂年輪'),
        h('span', { className: 'section-count' }, soulRings.length + ' 道印記')
      ),
      // 運作說明
      h('div', { className: 'section-explainer' },
        h('div', { className: 'explainer-title' }, '📖 年輪如何鍛造？'),
        h('div', { className: 'explainer-body' },
          '每次互動後系統自動偵測四種訊號：',
          h('strong', null, ' 🔥失敗教訓'),
          '（Q-Score < 0.4）、',
          h('strong', null, '💡認知突破'),
          '（推理路徑改變）、',
          h('strong', null, '⭐服務里程碑'),
          '（品質新高）、',
          h('strong', null, '🔮價值校準'),
          '（核心判斷修正）。',
          ' 年輪不可刪改，用 SHA-256 雜湊鏈保護。',
          ' 相似事件不重複鍛造，而是強化次數 +1。',
          ' 每日即時最多 5 道，其餘由夜間批次精煉。'
        )
      ),
      soulRings.length > 0
        ? h('div', { className: 'soul-ring-timeline' },
            ...soulRings.map((ring, idx) => renderSoulRingItem(ring, idx))
          )
        : h('div', { className: 'evo-empty-state evo-empty-tall' },
            h('div', { className: 'evo-empty-icon' }, '🌀'),
            h('div', { className: 'evo-empty-text' }, '年輪從失敗中淬煉而生'),
            h('div', { className: 'evo-empty-hint' }, '當 Q-Score 低於閾值時，系統會自動記錄教訓並鍛造年輪')
          )
    ),

    // ═══ 知識結晶展示架 ═══
    renderCrystalShowcase(crystals),

    // ═══ Morphenix 進化紀錄 ═══
    h('div', { className: 'card' },
      h('div', { className: 'section-header' },
        h('span', { className: 'section-icon' }, '🔥'),
        h('span', null, '進化紀錄'),
        h('span', { className: 'section-count' }, 'Morphenix')
      ),
      h('div', { className: 'morphenix-status' },
        h('div', { className: 'morphenix-stat' },
          h('span', { className: 'morphenix-stat-value' }, String((morphenix.notes || []).length)),
          h('span', { className: 'morphenix-stat-label' }, '迭代筆記')
        ),
        h('div', { className: 'morphenix-stat' },
          h('span', { className: 'morphenix-stat-value' }, String((morphenix.proposals || []).length)),
          h('span', { className: 'morphenix-stat-label' }, '進化提案')
        ),
        h('div', { className: 'morphenix-stat' },
          h('span', { className: 'morphenix-stat-value' }, String((wee.workflows || []).length)),
          h('span', { className: 'morphenix-stat-label' }, '工作流')
        )
      ),
      (morphenix.notes || []).length === 0 && (morphenix.proposals || []).length === 0
        ? h('div', { className: 'evo-empty-state' },
            h('div', { className: 'evo-empty-icon' }, '🔥'),
            h('div', { className: 'evo-empty-text' }, '浴火鳳凰尚在蓄能'),
            h('div', { className: 'evo-empty-hint' }, '持續互動後，Morphenix 會觀察不足並提出自我改善提案')
          )
        : null
    ),

    // ═══ 🧠 記憶日誌（從 Memory tab 合併） ═══
    renderMemoryJournal()
  );
}

// ── 演化 Hero 統計 ──
function renderEvoHeroStat(icon, label, value, unit) {
  return h('div', { className: 'evo-hero-stat' },
    h('div', { className: 'evo-hero-icon' }, icon),
    h('div', { className: 'evo-hero-value' }, value, h('span', { className: 'evo-hero-unit' }, unit)),
    h('div', { className: 'evo-hero-label' }, label)
  );
}

// ── Sparkline ──
function renderSparkline(data, min, max) {
  const w = 400, h2 = 120, padding = 10;
  const range = Math.max(max - min, 1);
  const step = (w - padding * 2) / Math.max(data.length - 1, 1);

  let pathD = '';
  data.forEach((v, i) => {
    const x = padding + i * step;
    const y = h2 - padding - ((v - min) / range) * (h2 - padding * 2);
    pathD += (i === 0 ? 'M' : 'L') + x.toFixed(1) + ',' + y.toFixed(1);
  });

  // 填充路徑
  const lastX = padding + (data.length - 1) * step;
  const fillD = pathD + `L${lastX},${h2 - padding}L${padding},${h2 - padding}Z`;

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${w} ${h2}`);
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', String(h2));
  svg.style.display = 'block';

  const fill = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  fill.setAttribute('d', fillD);
  fill.setAttribute('fill', 'url(#sparkGrad)');
  fill.setAttribute('opacity', '0.3');

  const line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  line.setAttribute('d', pathD);
  line.setAttribute('fill', 'none');
  line.setAttribute('stroke', '#c9a96e');
  line.setAttribute('stroke-width', '2');
  line.setAttribute('stroke-linecap', 'round');
  line.setAttribute('stroke-linejoin', 'round');

  // 最後一個點
  const lastY = h2 - padding - ((data[data.length - 1] - min) / range) * (h2 - padding * 2);
  const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
  dot.setAttribute('cx', String(lastX));
  dot.setAttribute('cy', String(lastY));
  dot.setAttribute('r', '4');
  dot.setAttribute('fill', '#c9a96e');
  dot.setAttribute('stroke', '#141b2d');
  dot.setAttribute('stroke-width', '2');

  // Gradient
  const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
  const grad = document.createElementNS('http://www.w3.org/2000/svg', 'linearGradient');
  grad.setAttribute('id', 'sparkGrad');
  grad.setAttribute('x1', '0'); grad.setAttribute('y1', '0');
  grad.setAttribute('x2', '0'); grad.setAttribute('y2', '1');
  const s1 = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
  s1.setAttribute('offset', '0%'); s1.setAttribute('stop-color', '#c9a96e');
  const s2 = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
  s2.setAttribute('offset', '100%'); s2.setAttribute('stop-color', '#c9a96e'); s2.setAttribute('stop-opacity', '0');
  grad.appendChild(s1); grad.appendChild(s2); defs.appendChild(grad);

  svg.appendChild(defs);
  svg.appendChild(fill);
  svg.appendChild(line);
  svg.appendChild(dot);

  // 數值標籤
  const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  label.setAttribute('x', String(lastX - 5));
  label.setAttribute('y', String(lastY - 10));
  label.setAttribute('text-anchor', 'end');
  label.setAttribute('fill', '#c9a96e');
  label.setAttribute('font-size', '12');
  label.setAttribute('font-weight', '700');
  label.textContent = String(data[data.length - 1]);
  svg.appendChild(label);

  const wrapper = h('div', { className: 'sparkline-container' });
  wrapper.appendChild(svg);
  return wrapper;
}

// ── Q-Score 分布條 ──
function renderQDistribution(qHistory) {
  const buckets = { excellent: 0, good: 0, medium: 0, low: 0 };
  qHistory.forEach(q => {
    const s = (q.score || 0) * 100;
    if (s >= 80) buckets.excellent++;
    else if (s >= 60) buckets.good++;
    else if (s >= 40) buckets.medium++;
    else buckets.low++;
  });
  const total = qHistory.length || 1;
  const items = [
    { label: '優秀', count: buckets.excellent, color: '#10b981', pct: Math.round(buckets.excellent / total * 100) },
    { label: '良好', count: buckets.good, color: '#3b82f6', pct: Math.round(buckets.good / total * 100) },
    { label: '普通', count: buckets.medium, color: '#f59e0b', pct: Math.round(buckets.medium / total * 100) },
    { label: '待改善', count: buckets.low, color: '#ef4444', pct: Math.round(buckets.low / total * 100) },
  ];

  return h('div', { className: 'q-distribution' },
    h('div', { className: 'q-dist-bar' },
      ...items.filter(i => i.count > 0).map(i =>
        h('div', { className: 'q-dist-segment', style: { width: i.pct + '%', background: i.color } })
      )
    ),
    h('div', { className: 'q-dist-legend' },
      ...items.map(i =>
        h('span', { className: 'q-dist-item' },
          h('span', { className: 'q-dist-dot', style: { background: i.color } }),
          i.label + ' ' + i.count
        )
      )
    )
  );
}

// ── 靈魂年輪項目 ──
function renderSoulRingItem(ring, idx) {
  const type = ring.type || 'unknown';
  const typeIcons = { failure_lesson: '🔥', insight: '💡', milestone: '⭐', pattern: '🔮' };
  const typeLabels = {
    failure_lesson: '失敗教訓', cognitive_breakthrough: '認知突破',
    service_milestone: '服務里程碑', value_calibration: '價值校準',
    insight: '洞見', milestone: '里程碑', pattern: '模式'
  };
  const typeColors = {
    failure_lesson: '#ef4444', cognitive_breakthrough: '#3b82f6',
    service_milestone: '#10b981', value_calibration: '#8b5cf6',
    insight: '#3b82f6', milestone: '#10b981', pattern: '#8b5cf6'
  };
  const timeStr = ring.created_at ? new Date(ring.created_at).toLocaleDateString('zh-TW') : '—';
  const color = typeColors[type] || '#c9a96e';
  const reinforce = ring.reinforcement_count || 0;

  // ── 解析「學到了什麼」而非「發生了什麼」──
  let lessonContent = null;
  if (type === 'failure_lesson') {
    const parts = [];
    if (ring.failure_description && ring.failure_description !== ring.description) {
      parts.push({ label: '問題', text: ring.failure_description });
    }
    if (ring.root_cause && ring.root_cause !== '待分析') {
      parts.push({ label: '根因', text: ring.root_cause });
    }
    if (ring.prevention && ring.prevention !== '待制定') {
      parts.push({ label: '預防', text: ring.prevention });
    }
    if (parts.length === 0 && ring.context) {
      parts.push({ label: '情境', text: ring.context });
    }
    if (parts.length > 0) {
      lessonContent = h('div', { className: 'soul-ring-lessons' },
        ...parts.map(p =>
          h('div', { className: 'soul-ring-lesson-row' },
            h('span', { className: 'soul-ring-lesson-label', style: { color } }, p.label),
            h('span', { className: 'soul-ring-lesson-text' }, p.text)
          )
        )
      );
    }
  } else {
    const detail = ring.impact || ring.context;
    if (detail) {
      lessonContent = h('div', { className: 'soul-ring-lessons' },
        h('div', { className: 'soul-ring-lesson-row' },
          h('span', { className: 'soul-ring-lesson-label', style: { color } }, '影響'),
          h('span', { className: 'soul-ring-lesson-text' }, detail)
        )
      );
    }
  }

  return h('div', { className: 'soul-ring-item' },
    h('div', { className: 'soul-ring-line' },
      h('div', { className: 'soul-ring-dot', style: { background: color, boxShadow: `0 0 6px ${color}55` } }),
      idx < 99 ? h('div', { className: 'soul-ring-connector' }) : null
    ),
    h('div', { className: 'soul-ring-content' },
      h('div', { className: 'soul-ring-header' },
        h('span', { className: 'soul-ring-icon' }, typeIcons[type] || '🌀'),
        h('span', { className: 'soul-ring-type', style: { color } }, typeLabels[type] || type),
        reinforce > 1
          ? h('span', { className: 'soul-ring-reinforce', style: { color } }, `×${reinforce}`)
          : null,
        h('span', { className: 'soul-ring-time' }, timeStr)
      ),
      h('div', { className: 'soul-ring-desc' }, ring.description || '（無描述）'),
      lessonContent,
      ring.context && type === 'failure_lesson'
        ? h('div', { className: 'soul-ring-context' },
            h('span', { style: { color: '#6b5f4a', fontSize: '0.625rem' } }, '📌 '),
            ring.context)
        : null
    )
  );
}

// ── 知識結晶項目 ──
function crystalAutoName(crystal) {
  // 從 g1_summary 中自動萃取標題（取第一個有意義的標題行）
  const g1 = crystal.g1_summary || '';
  // 嘗試取 markdown 標題
  const headingMatch = g1.match(/^#{1,3}\s+(.+)/m);
  if (headingMatch) {
    const heading = headingMatch[1].replace(/[—–\-]+\s*[「「].*/, '').trim();
    if (heading.length > 2 && heading.length <= 40) return heading;
  }
  // 嘗試取 **粗體** 開頭
  const boldMatch = g1.match(/\*\*(.{3,30})\*\*/);
  if (boldMatch) return boldMatch[1];
  // 取前 30 字（去 markdown 符號）
  const clean = g1.replace(/^#+\s*/gm, '').replace(/\*+/g, '').replace(/\n/g, ' ').trim();
  if (clean.length > 30) return clean.substring(0, 28) + '…';
  if (clean.length > 0) return clean;
  return crystal.cuid || '未命名結晶';
}

function crystalSummary(crystal) {
  // 從 g2_structure 或 g4_insights 取摘要
  const g2 = crystal.g2_structure || [];
  if (g2.length > 0) {
    const raw = g2[0] || '';
    // 取前 80 字作為摘要
    const clean = raw.replace(/^#+\s*/gm, '').replace(/\*+/g, '').replace(/\n/g, ' ').trim();
    if (clean.length > 80) return clean.substring(0, 78) + '…';
    return clean;
  }
  return '';
}

/**
 * 📊 今日摘要區塊（Daily Summary）
 */
function renderDailySummary() {
  const ds = state.dailySummary;
  const dates = state.dailySummaryDates || [];

  return h('div', { className: 'card' },
    h('div', { className: 'section-header' },
      h('span', { className: 'section-icon' }, '📊'),
      h('span', null, '每日摘要'),
      dates.length > 0
        ? h('select', {
            value: state.dailySummaryDate || '',
            onChange: (e) => { loadDailySummary(e.target.value); },
            style: {
              marginLeft: 'auto', padding: '0.2rem 0.4rem', fontSize: '0.6875rem',
              background: 'rgba(255,255,255,0.04)', border: '1px solid #2d3a5c',
              borderRadius: '4px', color: '#f3ede0', outline: 'none'
            }
          },
            ...dates.slice(0, 14).map(d =>
              h('option', { value: d }, d)
            )
          )
        : null
    ),
    ds && !ds.error
      ? h('div', { style: { padding: '0.25rem 0' } },
          // Narrative
          ds.narrative
            ? h('div', { style: {
                fontSize: '0.8125rem', color: '#e8dcc6', lineHeight: '1.6',
                whiteSpace: 'pre-line', padding: '0.5rem 0.75rem',
                background: 'rgba(201,169,110,0.05)', borderRadius: '8px',
                borderLeft: '3px solid #c9a96e'
              } }, ds.narrative)
            : null,
          // Stats row
          h('div', { style: { display: 'flex', gap: '1rem', marginTop: '0.5rem', fontSize: '0.75rem', color: '#9a8b70' } },
            h('span', null, `📋 ${ds.event_count || 0} 個事件`),
            h('span', null, `🧠 ${(ds.memory_channels || []).length} 個記憶頻道`),
            ds.generated_at
              ? h('span', null, `⏰ ${new Date(ds.generated_at).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })} 生成`)
              : null
          )
        )
      : h('div', { style: { fontSize: '0.8125rem', color: '#6b5f4a', fontStyle: 'italic', padding: '0.5rem 0' } },
          dates.length === 0
            ? '每日摘要由凌晨 3:00 整合管線自動產生'
            : (ds && ds.error) || '正在載入...'
        )
  );
}

/**
 * 📋 活動日誌區塊（Activity Log）
 */
function renderActivityLog() {
  const events = state.activityRecent || [];
  const eventLabelsZh = {
    'BRAIN_RESPONSE_COMPLETE': '🧠 回覆完成',
    'NIGHTLY_COMPLETED': '🌙 夜間整合',
    'PULSE_PROACTIVE_SENT': '💬 主動推送',
    'PULSE_EXPLORATION_DONE': '🔍 探索完成',
    'MORPHENIX_PROPOSAL_CREATED': '🔥 進化提案',
    'MORPHENIX_EXECUTED': '⚡ 進化執行',
    'WEE_CYCLE_COMPLETE': '🔄 工作流循環',
    'CRYSTAL_CREATED': '💎 結晶生成',
    'SOUL_RING_DEPOSITED': '🌀 年輪沉積',
  };

  return h('div', { className: 'card' },
    h('div', { className: 'section-header' },
      h('span', { className: 'section-icon' }, '📋'),
      h('span', null, '活動日誌'),
      h('span', { className: 'section-count' }, events.length > 0 ? `最近 ${events.length} 筆` : ''),
      h('button', {
        className: 'btn-outline btn-sm',
        style: { marginLeft: 'auto', fontSize: '0.6875rem' },
        onClick: () => { loadActivityRecent(); }
      }, '🔄')
    ),
    events.length > 0
      ? h('div', { style: { display: 'flex', flexDirection: 'column', gap: '0.25rem' } },
          ...events.slice(0, 15).map(evt => {
            const label = eventLabelsZh[evt.event] || evt.event;
            const time = evt.ts ? new Date(evt.ts).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '';
            const detail = typeof evt.data === 'object' && evt.data
              ? (evt.data.summary || evt.data.task_type || evt.data.status || '')
              : '';
            return h('div', {
              style: {
                display: 'flex', alignItems: 'center', gap: '0.5rem',
                fontSize: '0.75rem', padding: '0.25rem 0',
                borderBottom: '1px solid rgba(255,255,255,0.03)'
              }
            },
              h('span', { style: { color: '#6b5f4a', fontSize: '0.6875rem', minWidth: '5rem' } }, time),
              h('span', { style: { color: '#e8dcc6' } }, label),
              detail ? h('span', { style: { color: '#9a8b70', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, detail) : null
            );
          })
        )
      : h('div', { style: { fontSize: '0.8125rem', color: '#6b5f4a', fontStyle: 'italic', padding: '0.5rem 0' } },
          '活動日誌會隨使用自動記錄'
        )
  );
}

/**
 * 🧠 記憶日誌區塊（Memory Journal — 從 Memory tab 搬來）
 */
function renderMemoryJournal() {
  const dates = state.memoryDates || [];
  const blocks = state.memoryJournalBlocks || [];
  const loading = state.memoryLoading;
  const isExpanded = !state.evoMemoryCollapsed;

  return h('div', { className: 'card' },
    h('div', {
      className: 'section-header',
      style: { cursor: 'pointer', userSelect: 'none' },
      onClick: () => { state.evoMemoryCollapsed = !state.evoMemoryCollapsed; render(); }
    },
      h('span', { className: 'section-icon' }, '🧠'),
      h('span', null, '記憶日誌'),
      h('span', { className: 'section-count' }, dates.length > 0 ? `${dates.length} 天` : ''),
      h('span', { style: { marginLeft: 'auto', fontSize: '0.6875rem', color: '#6b5f4a' } },
        isExpanded ? '▾' : '▸')
    ),
    isExpanded ? h('div', { style: { padding: '0.25rem 0' } },
      // 日期選擇器
      dates.length > 0
        ? h('div', { style: { display: 'flex', gap: '0.375rem', flexWrap: 'wrap', marginBottom: '0.75rem' } },
            ...dates.slice(0, 14).map(d =>
              h('button', {
                className: d === state.selectedMemoryDate ? 'wizard-btn-primary' : 'btn-outline btn-sm',
                style: { fontSize: '0.6875rem', padding: '0.2rem 0.5rem' },
                onClick: async () => {
                  state.selectedMemoryDate = d;
                  render();
                  await loadJournalEntries(d);
                  render();
                }
              }, d.slice(5)) // show MM-DD only
            )
          )
        : null,
      // 日誌內容
      loading
        ? h('div', { className: 'spinner', style: { margin: '1rem auto' } })
        : blocks.length > 0
          ? h('div', { style: { display: 'flex', flexDirection: 'column', gap: '0.5rem' } },
              ...blocks.slice(0, 20).map(block => {
                const channel = block.channel || 'event';
                const channelEmoji = { 'meta-thinking': '💭', 'event': '📝', 'outcome': '🎯' };
                return h('div', { style: {
                  padding: '0.5rem 0.75rem', background: 'rgba(255,255,255,0.02)',
                  borderRadius: '6px', borderLeft: '3px solid #2d3a5c'
                } },
                  h('div', { style: { display: 'flex', gap: '0.375rem', alignItems: 'center', marginBottom: '0.25rem' } },
                    h('span', null, channelEmoji[channel] || '📝'),
                    h('span', { style: { fontSize: '0.6875rem', color: '#c9a96e', fontWeight: '600' } }, channel),
                    block.time ? h('span', { style: { fontSize: '0.625rem', color: '#6b5f4a' } }, block.time) : null
                  ),
                  h('div', { style: { fontSize: '0.8125rem', color: '#e8dcc6', lineHeight: '1.5', whiteSpace: 'pre-line' } },
                    (block.content || '').slice(0, 500)
                  )
                );
              })
            )
          : h('div', { style: { fontSize: '0.8125rem', color: '#6b5f4a', fontStyle: 'italic' } },
              dates.length > 0 ? '選擇日期查看記憶' : '尚無記憶日誌'
            )
    ) : null
  );
}

/**
 * 知識結晶展示架 — 按類型分組、預設收合、顯示最新 3 筆
 */
function renderCrystalShowcase(crystals) {
  const typeOrder = ['Insight', 'Pattern', 'Lesson', 'Hypothesis'];
  const typeLabelsZh = { Insight: '💡 洞見', Pattern: '🔮 模式', Lesson: '📖 教訓', Hypothesis: '🧪 假說' };
  const typeColors = { Insight: '#60a5fa', Pattern: '#34d399', Lesson: '#fbbf24', Hypothesis: '#a78bfa' };
  const COLLAPSED_LIMIT = 3;

  if (!crystals || crystals.length === 0) {
    return h('div', { className: 'card' },
      h('div', { className: 'section-header' },
        h('span', { className: 'section-icon' }, '💎'),
        h('span', null, '知識結晶'),
        h('span', { className: 'section-count' }, '0 枚')
      ),
      h('div', { className: 'evo-empty-state evo-empty-tall' },
        h('div', { className: 'evo-empty-icon' }, '💎'),
        h('div', { className: 'evo-empty-text' }, '知識結晶尚未凝聚'),
        h('div', { className: 'evo-empty-hint' }, '當對話中產生經過驗證的洞見，系統會自動結晶保存')
      )
    );
  }

  // 按類型分組
  const groups = {};
  crystals.forEach(c => {
    const t = c.crystal_type || c.type || 'Insight';
    if (!groups[t]) groups[t] = [];
    groups[t].push(c);
  });

  // 排序：每組內按日期倒序
  const sortByDate = (a, b) => {
    const da = a.created_at || a.last_referenced || '';
    const db = b.created_at || b.last_referenced || '';
    return db.localeCompare(da);
  };
  const sortByQuality = (a, b) => (b.ri_score || 0) - (a.ri_score || 0);
  const sortFn = state.crystalSortBy === 'quality' ? sortByQuality : sortByDate;

  Object.values(groups).forEach(arr => arr.sort(sortFn));
  const sortedTypes = typeOrder.filter(t => groups[t] && groups[t].length > 0);

  // 搜尋過濾
  const query = (state.crystalSearchQuery || '').trim().toLowerCase();
  const filterCrystals = (list) => {
    if (!query) return list;
    return list.filter(c => {
      const text = ((c.g1_summary || '') + ' ' + (c.cuid || '')).toLowerCase();
      return text.includes(query);
    });
  };

  // 統計 chips
  const chips = h('div', { style: {
    display: 'flex', gap: '0.375rem', flexWrap: 'wrap', marginBottom: '0.5rem', alignItems: 'center'
  } },
    ...sortedTypes.map(t =>
      h('span', {
        style: {
          fontSize: '0.625rem', padding: '0.2rem 0.5rem', borderRadius: '1rem',
          background: typeColors[t] + '15', color: typeColors[t],
          fontWeight: '600', border: `1px solid ${typeColors[t]}33`,
          cursor: 'pointer'
        },
        onClick: () => {
          state.crystalGroupExpanded[t] = !state.crystalGroupExpanded[t];
          render();
        }
      }, `${typeLabelsZh[t] || t} ${groups[t].length}`)
    )
  );

  // 搜尋 + 排序控制列
  const controls = h('div', { style: {
    display: 'flex', gap: '0.5rem', marginBottom: '0.75rem', alignItems: 'center'
  } },
    h('input', {
      type: 'text',
      placeholder: '搜尋結晶...',
      value: state.crystalSearchQuery || '',
      onInput: (e) => { state.crystalSearchQuery = e.target.value; render(); },
      style: {
        flex: 1, padding: '0.35rem 0.6rem', fontSize: '0.75rem',
        background: 'rgba(255,255,255,0.04)', border: '1px solid #2d3a5c',
        borderRadius: '6px', color: '#f3ede0', outline: 'none'
      }
    }),
    h('select', {
      value: state.crystalSortBy,
      onChange: (e) => { state.crystalSortBy = e.target.value; render(); },
      style: {
        padding: '0.35rem 0.5rem', fontSize: '0.7rem',
        background: 'rgba(255,255,255,0.04)', border: '1px solid #2d3a5c',
        borderRadius: '6px', color: '#f3ede0', outline: 'none'
      }
    },
      h('option', { value: 'date' }, '按時間'),
      h('option', { value: 'quality' }, '按品質')
    )
  );

  // 分組渲染
  const sections = sortedTypes.map(t => {
    const filtered = filterCrystals(groups[t]);
    if (filtered.length === 0 && query) return null;
    const isExpanded = !!state.crystalGroupExpanded[t];
    const visible = isExpanded ? filtered : filtered.slice(0, COLLAPSED_LIMIT);
    const hasMore = filtered.length > COLLAPSED_LIMIT;

    return h('div', { key: t, style: { marginBottom: '0.75rem' } },
      // 分組標題（可點擊展開/收合）
      h('div', {
        style: {
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          fontSize: '0.6875rem', fontWeight: '600', color: typeColors[t],
          marginBottom: '0.375rem', paddingLeft: '0.25rem',
          cursor: hasMore ? 'pointer' : 'default', userSelect: 'none'
        },
        onClick: () => {
          if (hasMore) { state.crystalGroupExpanded[t] = !isExpanded; render(); }
        }
      },
        h('span', null, (typeLabelsZh[t] || t) + ` (${filtered.length})`),
        hasMore
          ? h('span', { style: { fontSize: '0.625rem', color: '#9a8b70', fontWeight: '400' } },
              isExpanded ? '收合 ▴' : `展開全部 ${filtered.length} 筆 ▾`)
          : null
      ),
      // 結晶列表
      h('div', { className: 'crystal-showcase' },
        ...visible.map(c => renderCrystalItem(c))
      )
    );
  }).filter(Boolean);

  return h('div', { className: 'card' },
    h('div', { className: 'section-header' },
      h('span', { className: 'section-icon' }, '💎'),
      h('span', null, '知識結晶'),
      h('span', { className: 'section-count' }, crystals.length + ' 枚')
    ),
    controls,
    chips,
    ...sections
  );
}

function renderCrystalItem(crystal) {
  const typeLabelsZh = { Insight: '洞見', Pattern: '模式', Lesson: '教訓', Hypothesis: '假說' };
  const typeColors = { Insight: '#3b82f6', Pattern: '#10b981', Lesson: '#f59e0b', Hypothesis: '#8b5cf6' };
  const typeIcons = { Insight: '💡', Pattern: '🔮', Lesson: '📖', Hypothesis: '🧪' };
  const verifyLabels = { hypothetical: '假設中', observed: '已觀察', tested: '已測試', proven: '已驗證' };
  const verifyColors = { hypothetical: '#6b5f4a', observed: '#f59e0b', tested: '#3b82f6', proven: '#10b981' };
  const type = crystal.crystal_type || crystal.type || 'Insight';
  const color = typeColors[type] || '#c9a96e';
  const title = crystalAutoName(crystal);
  const summary = crystalSummary(crystal);
  const verify = crystal.verification_level || 'hypothetical';
  const ri = crystal.ri_score || 0;
  const cuid = crystal.cuid || '';
  const expandKey = 'crystalExpand_' + cuid;
  const isExpanded = state[expandKey] || false;

  return h('div', {
    className: 'crystal-item',
    style: { borderColor: color + '33', cursor: 'pointer' },
    onClick: (e) => {
      e.stopPropagation();
      state.crystalModalData = crystal;
      render();
    }
  },
    h('div', { className: 'crystal-icon', style: { background: color + '1a' } },
      typeIcons[type] || '💎'
    ),
    h('div', { className: 'crystal-body' },
      // 類型 + 驗證等級
      h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.375rem', marginBottom: '0.15rem' } },
        h('div', { className: 'crystal-type', style: { color, margin: 0 } }, typeLabelsZh[type] || type),
        h('span', { style: {
          fontSize: '0.6rem', padding: '0.1rem 0.35rem', borderRadius: '0.25rem',
          background: verifyColors[verify] + '1a', color: verifyColors[verify],
          fontWeight: '600', lineHeight: '1.3'
        } }, verifyLabels[verify] || verify),
        ri > 0 ? h('span', { style: { fontSize: '0.6rem', color: '#6b5f4a', marginLeft: 'auto' } },
          `RI ${(ri * 100).toFixed(0)}%`) : null
      ),
      // 標題（自動命名）
      h('div', { className: 'crystal-title' }, title),
      // 摘要（一行）
      summary
        ? h('div', { style: { fontSize: '0.7rem', color: '#6b5f4a', lineHeight: '1.4', marginTop: '0.25rem' } }, summary)
        : null
    )
  );
}

/**
 * 結晶詳情浮動視窗（Modal Overlay）
 */
function renderCrystalModal() {
  const crystal = state.crystalModalData;
  if (!crystal) return null;

  const typeLabelsZh = { Insight: '洞見', Pattern: '模式', Lesson: '教訓', Hypothesis: '假說' };
  const typeColors = { Insight: '#3b82f6', Pattern: '#10b981', Lesson: '#f59e0b', Hypothesis: '#8b5cf6' };
  const typeIcons = { Insight: '💡', Pattern: '🔮', Lesson: '📖', Hypothesis: '🧪' };
  const verifyLabels = { hypothetical: '假設中', observed: '已觀察', tested: '已測試', proven: '已驗證' };
  const type = crystal.crystal_type || crystal.type || 'Insight';
  const color = typeColors[type] || '#c9a96e';
  const title = crystalAutoName(crystal);
  const verify = crystal.verification_level || 'hypothetical';
  const ri = crystal.ri_score || 0;
  const cuid = crystal.cuid || '';

  const stripPrefix = (s) => (s || '').replace(/^(待深入分析：|初步觀察：|待釐清|來源：)/, '').trim();
  const g1Raw = (crystal.g1_summary || '').replace(/^#+\s*/gm, '').replace(/\*+/g, '').trim();
  const g3Clean = stripPrefix(crystal.g3_root_inquiry);
  const g4Clean = (crystal.g4_insights || []).map(s => stripPrefix(s)).filter(s => s.length > 0);
  const evidenceClean = (crystal.evidence || '').replace(/^來源：/, '').trim();
  const assumptionClean = stripPrefix(crystal.assumption);
  const limitClean = stripPrefix(crystal.limitation);

  const g2Raw = crystal.g2_structure || [];
  const g2Items = (Array.isArray(g2Raw) ? g2Raw : [g2Raw]).map(s => (s || '').trim()).filter(s => s.length > 0);
  const g3IsPlaceholder = !g3Clean || g3Clean === '這個觀察背後的核心問題是什麼？';

  const rows = [];
  if (g1Raw) {
    rows.push(h('div', { className: 'crystal-modal-section' },
      h('div', { className: 'crystal-modal-label' }, '📄 摘要'),
      h('div', { className: 'crystal-modal-text' }, g1Raw)
    ));
  }
  // G2: 結構分析（藍底）
  rows.push(h('div', { className: 'crystal-modal-section', style: { background: 'rgba(96,165,250,0.06)', borderRadius: '8px', padding: '0.75rem' } },
    h('div', { className: 'crystal-modal-label', style: { color: '#60a5fa' } }, '📐 結構分析'),
    g2Items.length > 0
      ? g2Items.map(item => h('div', { className: 'crystal-modal-text' }, '· ' + item))
      : h('div', { className: 'crystal-modal-text', style: { color: '#6b5f4a', fontStyle: 'italic' } }, '結構待補充')
  ));
  // G3: 根本問題（琥珀底）
  rows.push(h('div', { className: 'crystal-modal-section', style: { background: 'rgba(251,191,36,0.06)', borderRadius: '8px', padding: '0.75rem' } },
    h('div', { className: 'crystal-modal-label', style: { color: '#fbbf24' } }, '🔍 根源探問'),
    g3IsPlaceholder
      ? h('div', { className: 'crystal-modal-text', style: { color: '#6b5f4a', fontStyle: 'italic' } }, g3Clean || '尚未探問')
      : h('div', { className: 'crystal-modal-text' }, g3Clean)
  ));
  // G4: 洞見（綠底）
  rows.push(h('div', { className: 'crystal-modal-section', style: { background: 'rgba(52,211,153,0.06)', borderRadius: '8px', padding: '0.75rem' } },
    h('div', { className: 'crystal-modal-label', style: { color: '#34d399' } }, '💡 洞見'),
    g4Clean.length > 0
      ? g4Clean.map(insight => h('div', { className: 'crystal-modal-text' }, '· ' + insight))
      : h('div', { className: 'crystal-modal-text', style: { color: '#6b5f4a', fontStyle: 'italic' } }, '尚未產生洞見')
  ));
  if (assumptionClean && assumptionClean.length > 2) {
    rows.push(h('div', { className: 'crystal-modal-section' },
      h('div', { className: 'crystal-modal-label' }, '🧪 假設'),
      h('div', { className: 'crystal-modal-text' }, assumptionClean)
    ));
  }
  if (limitClean && limitClean.length > 2) {
    rows.push(h('div', { className: 'crystal-modal-section' },
      h('div', { className: 'crystal-modal-label' }, '⚠️ 局限'),
      h('div', { className: 'crystal-modal-text' }, limitClean)
    ));
  }
  rows.push(h('div', { className: 'crystal-modal-meta' },
    h('span', null, '來源：' + (evidenceClean || crystal.source_context || '—')),
    h('span', null, '結晶日：' + (crystal.created_at ? new Date(crystal.created_at).toLocaleDateString('zh-TW') : '—')),
    ri > 0 ? h('span', null, `RI：${(ri * 100).toFixed(0)}%`) : null,
    h('span', { style: { color: '#4a4035' } }, cuid)
  ));

  return h('div', {
    className: 'crystal-modal-overlay',
    onClick: (e) => { if (e.target === e.currentTarget) { state.crystalModalData = null; render(); } }
  },
    h('div', { className: 'crystal-modal' },
      h('div', { className: 'crystal-modal-header' },
        h('span', { style: { fontSize: '1.5rem' } }, typeIcons[type] || '💎'),
        h('div', { style: { flex: 1 } },
          h('div', { className: 'crystal-modal-title' }, title),
          h('div', { style: { display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: '0.25rem' } },
            h('span', { style: { color, fontWeight: 600 } }, typeLabelsZh[type] || type),
            h('span', { style: { color: '#6b5f4a' } }, verifyLabels[verify] || verify)
          )
        ),
        h('button', {
          className: 'crystal-modal-close',
          onClick: () => { state.crystalModalData = null; render(); }
        }, '✕')
      ),
      h('div', { className: 'crystal-modal-body' }, ...rows)
    )
  );
}

// ═══════════════════════════════════════
// Tab 3: 🧠 記憶 (Memory) — v2 共享日誌
// ═══════════════════════════════════════

// Skill ID → 中文對照
const skillLabelsZh = {
  // 核心層
  'dna27': '核心判斷', 'deep-think': '深度思考', 'c15': '敘事張力',
  'eval-engine': '品質評估', 'user-model': '使用者理解', 'morphenix': '自我進化',
  'resonance': '情感共振', 'dharma': '思維轉化',
  // 文字 / 敘事
  'text-alchemy': '文字煉金', 'storytelling-engine': '故事引擎', 'novel-craft': '小說工藝',
  'consultant-communication': '顧問溝通',
  // 商業 / 策略
  'business-12': '商業診斷', 'ssa-consultant': '顧問銷售', 'brand-identity': '品牌識別',
  'xmodel': '破框引擎', 'pdeif': '逆熵流', 'master-strategy': '戰略引擎',
  // 市場 / 投資
  'market-core': '市場分析', 'market-equity': '股票分析', 'market-crypto': '加密貨幣',
  'market-macro': '總體經濟', 'investment-masters': '投資軍師',
  'sentiment-radar': '情緒雷達', 'risk-matrix': '風險管理',
  // 工作流 / 工具
  'plan-engine': '計畫引擎', 'orchestrator': '編排引擎', 'gap': '缺口分析',
  'sandbox-lab': '實驗工坊', 'dse': '技術融合', 'acsf': '能力鑄造',
  'wee': '工作流演化', 'qa-auditor': '品質審計', 'env-radar': '環境雷達',
  'knowledge-lattice': '知識晶格',
  // 哲學 / 學習
  'philo-dialectic': '哲學思辨', 'meta-learning': '元學習', 'shadow': '人際洞察',
  // 美感 / 資訊
  'aesthetic-sense': '美感引擎', 'info-architect': '資訊架構',
  // 工作流範本
  'workflow-svc-brand-marketing': '品牌行銷流程', 'workflow-investment-analysis': '投資分析流程',
  'workflow-ai-deployment': '企業AI導入流程',
  // 系統
  'plugin-registry': '外掛註冊表', 'tantra': '情慾研究',
};
const skillLabelsEn = {
  'dna27': 'Core DNA', 'deep-think': 'Deep Think', 'c15': 'Narrative',
  'eval-engine': 'Evaluator', 'user-model': 'User Model', 'morphenix': 'Morphenix',
  'resonance': 'Resonance', 'dharma': 'DHARMA',
  'text-alchemy': 'Text Alchemy', 'storytelling-engine': 'Storytelling', 'novel-craft': 'Novel Craft',
  'consultant-communication': 'Consultant Comm',
  'business-12': 'Business 12', 'ssa-consultant': 'SSA Consulting', 'brand-identity': 'Brand ID',
  'xmodel': 'X-Model', 'pdeif': 'PDEIF', 'master-strategy': 'Strategy',
  'market-core': 'Market Core', 'market-equity': 'Equity', 'market-crypto': 'Crypto',
  'market-macro': 'Macro', 'investment-masters': 'Inv Masters',
  'sentiment-radar': 'Sentiment', 'risk-matrix': 'Risk Matrix',
  'plan-engine': 'Plan Engine', 'orchestrator': 'Orchestrator', 'gap': 'GAP',
  'sandbox-lab': 'Sandbox', 'dse': 'DSE', 'acsf': 'ACSF',
  'wee': 'WEE', 'qa-auditor': 'QA Auditor', 'env-radar': 'Env Radar',
  'knowledge-lattice': 'Knowledge Lattice',
  'philo-dialectic': 'Phil Dialectic', 'meta-learning': 'Meta Learning', 'shadow': 'Shadow',
  'aesthetic-sense': 'Aesthetic', 'info-architect': 'Info Architect',
  'workflow-svc-brand-marketing': 'Brand Mkt WF', 'workflow-investment-analysis': 'Inv Analysis WF',
  'workflow-ai-deployment': 'AI Deploy WF',
  'plugin-registry': 'Plugin Registry', 'tantra': 'Tantra',
};
// 動態取得當前語系的技能標籤
const skillLabels = new Proxy({}, {
  get: (_, key) => {
    const labels = state.lang === 'en' ? skillLabelsEn : skillLabelsZh;
    return labels[key] || undefined;
  }
});

const trustLabels = {
  initial: '初始', building: '建立中', growing: '成長中', established: '已建立',
};

function renderMemory() {
  return h('div', { style: { display: 'flex', flexDirection: 'column', gap: '1rem' } },
    // 頂部：霓裳對你的理解
    renderAnimaUnderstandingCard(),
    // Sub-tab + content
    h('div', { className: 'memory-tab' },
      // 左側 date sidebar — 只在日誌 tab 顯示
      state.memorySubTab === 'journal' ? renderMemoryDateList() : null,
      // 右側內容
      h('div', { className: 'memory-content-panel' },
        renderMemorySubTabs(),
        renderMemorySubTabContent()
      )
    )
  );
}

// ── 頂部理解卡片 ──
function renderAnimaUnderstandingCard() {
  const ov = state.memoryOverview;
  if (!ov) {
    return h('div', { className: 'card understanding-card' },
      h('div', { className: 'understanding-header' },
        h('div', { className: 'understanding-avatar' }, '🌙'),
        h('div', { className: 'understanding-info' },
          h('div', { className: 'understanding-title' }, '霓裳對你的理解'),
          h('div', { className: 'understanding-subtitle' }, '載入中...')
        )
      )
    );
  }

  const up = ov.userProfile || {};
  const relationship = up.relationship || {};
  const prefs = up.preferences || {};
  const skills = ov.skillDistribution || [];

  let relationAge = '—';
  if (relationship.first_interaction) {
    try {
      const days = Math.max(0, Math.floor((Date.now() - new Date(relationship.first_interaction).getTime()) / 86400000));
      relationAge = days > 0 ? days + ' 天' : '今天';
    } catch (e) { /* ignore */ }
  }

  return h('div', { className: 'card understanding-card' },
    // Header
    h('div', { className: 'understanding-header' },
      h('div', { className: 'understanding-avatar' }, '🌙'),
      h('div', { className: 'understanding-info' },
        h('div', { className: 'understanding-title' }, '霓裳對你的理解'),
        h('div', { className: 'understanding-subtitle' },
          '共享體驗 ' + (relationship.total_interactions || 0) + ' 次'
          + ' · 相識 ' + relationAge
          + ' · 信任 ' + (trustLabels[relationship.trust_level] || '初始')
        )
      )
    ),
    // 話題分布（前5）
    skills.length > 0
      ? h('div', { className: 'understanding-topics' },
          h('div', { className: 'understanding-section-label' }, '話題分布'),
          ...skills.slice(0, 5).map(s => renderTopicBar(s.skill, s.count, skills[0].count))
        )
      : null,
    // 偏好 chips
    h('div', { className: 'understanding-prefs' },
      renderPrefChip('🌐', prefs.language || 'zh-TW'),
      renderPrefChip('💬', prefs.communication_style || '探索中'),
      renderPrefChip('📊', '平均品質 ' + (ov.avgQScore ? (ov.avgQScore * 100).toFixed(0) + '%' : '—'))
    )
  );
}

function renderTopicBar(skill, count, maxCount) {
  const pct = maxCount > 0 ? Math.round((count / maxCount) * 100) : 0;
  const label = skillLabels[skill] || skill;
  return h('div', { className: 'topic-bar-row' },
    h('div', { className: 'topic-bar-label' }, label),
    h('div', { className: 'topic-bar-bg' },
      h('div', { className: 'topic-bar-fill', style: { width: pct + '%' } })
    ),
    h('div', { className: 'topic-bar-count' }, String(count))
  );
}

function renderPrefChip(icon, text) {
  return h('div', { className: 'pref-chip' },
    h('span', null, icon),
    h('span', null, text)
  );
}

// ── Sub-tab 切換 ──
function renderMemorySubTabs() {
  const tabs = [
    { id: 'journal', label: '📖 日誌' },
    { id: 'search', label: '🔍 搜尋' },
    { id: 'understanding', label: '🧠 理解' },
    { id: 'milestones', label: '🏆 里程碑' },
  ];
  return h('div', { className: 'memory-channel-tabs' },
    ...tabs.map(t =>
      h('button', {
        className: `memory-channel-tab ${state.memorySubTab === t.id ? 'active' : ''}`,
        onClick: () => {
          if (state.memorySubTab === t.id) return;
          state.memorySubTab = t.id;
          if (t.id === 'journal' && state.selectedMemoryDate && !state.memoryJournalBlocks) {
            loadJournalEntries(state.selectedMemoryDate);
          } else if ((t.id === 'understanding' || t.id === 'milestones') && !state.memoryOverview) {
            loadMemoryOverview();
          }
          render();
        }
      }, t.label)
    )
  );
}

function renderMemorySubTabContent() {
  return h('div', { className: 'memory-content-area' },
    (() => {
      switch (state.memorySubTab) {
        case 'journal': return renderJournalContent();
        case 'search': return renderSearchContent();
        case 'understanding': return renderUnderstandingContent();
        case 'milestones': return renderMilestonesContent();
        default: return renderJournalContent();
      }
    })()
  );
}

// ── 📖 日誌 ──
function renderJournalContent() {
  if (state.memoryLoading) {
    return h('div', { className: 'loading', style: { padding: '2rem' } },
      h('div', { className: 'spinner' }),
      h('p', null, '載入中...')
    );
  }
  if (!state.selectedMemoryDate) {
    return h('div', { className: 'memory-content-empty' },
      h('p', { style: { color: '#6b5f4a', fontSize: '1.1rem' } }, '請選擇一個日期'),
      h('p', { style: { color: '#475569', fontSize: '0.875rem', marginTop: '0.5rem' } },
        '從左側選取日期以瀏覽日誌')
    );
  }
  const blocks = state.memoryJournalBlocks;
  if (!blocks || blocks.length === 0) {
    return h('div', { className: 'memory-content-empty' },
      h('p', { style: { color: '#6b5f4a' } }, '此日尚無對話記錄')
    );
  }
  return h('div', { className: 'journal-content' },
    ...blocks.map(block => renderConversationBlock(block))
  );
}

function renderConversationBlock(block) {
  const timeRange = block.startTime + (block.endTime !== block.startTime ? ' — ' + block.endTime : '');
  return h('div', { className: 'journal-block' },
    h('div', { className: 'journal-block-time' }, timeRange),
    ...block.entries.map(entry =>
      h('div', { className: 'journal-entry' },
        h('div', { className: 'journal-entry-message' }, entry.userMessage || '（系統互動）'),
        entry.result
          ? h('div', { className: 'journal-entry-result' },
              entry.result === 'success' ? '✓ 已回應' : '⟳ ' + entry.result,
              entry.responseLength ? ' (' + entry.responseLength + ' 字)' : ''
            )
          : null
      )
    )
  );
}

// ── 🔍 搜尋 ──
function renderSearchContent() {
  return h('div', { className: 'search-content' },
    h('div', { className: 'search-input-row' },
      h('input', {
        className: 'search-input',
        type: 'text',
        placeholder: '搜尋對話記憶...',
        value: state.memorySearchQuery,
        onInput: (e) => { state.memorySearchQuery = e.target.value; },
        onKeydown: (e) => {
          if (e.key === 'Enter' && state.memorySearchQuery.trim()) {
            performMemorySearch(state.memorySearchQuery.trim());
          }
        }
      }),
      h('button', {
        className: 'search-btn',
        onClick: () => {
          if (state.memorySearchQuery.trim()) {
            performMemorySearch(state.memorySearchQuery.trim());
          }
        },
        disabled: state.memorySearchLoading
      }, state.memorySearchLoading ? '搜尋中...' : '🔍 搜尋')
    ),
    state.memorySearchResults
      ? renderSearchResults()
      : h('div', { className: 'search-empty' },
          h('div', { style: { fontSize: '3rem', marginBottom: '0.5rem' } }, '🔍'),
          h('p', { style: { color: '#6b5f4a' } }, '輸入關鍵字搜尋過去的對話記憶')
        )
  );
}

function renderSearchResults() {
  const results = state.memorySearchResults;
  if (results.length === 0) {
    return h('div', { className: 'search-empty' },
      h('p', { style: { color: '#6b5f4a', marginTop: '1rem' } }, '找不到相關記憶')
    );
  }
  return h('div', { className: 'search-results' },
    h('p', { className: 'search-results-count' }, '找到 ' + results.length + ' 筆記憶'),
    ...results.map(r =>
      h('div', {
        className: 'search-result-item',
        onClick: () => {
          state.selectedMemoryDate = r.date;
          state.memorySubTab = 'journal';
          loadJournalEntries(r.date);
        }
      },
        h('div', { className: 'search-result-date' }, formatDateChinese(r.date) + ' ' + r.time),
        h('div', { className: 'search-result-snippet' }, r.snippet)
      )
    )
  );
}

// ── 🧠 理解 ──
function renderUnderstandingContent() {
  if (state.memoryOverviewLoading || !state.memoryOverview) {
    return h('div', { className: 'loading', style: { padding: '2rem' } },
      h('div', { className: 'spinner' }),
      h('p', null, '載入中...')
    );
  }
  const ov = state.memoryOverview;
  const up = ov.userProfile || {};
  const prefs = up.preferences || {};
  const knowledge = up.knowledge_level || {};
  const needs = up.needs || {};
  const interactions = up.interaction_patterns || {};
  const skills = ov.skillDistribution || [];

  return h('div', { className: 'understanding-content' },
    // 完整話題分布
    h('div', { className: 'card' },
      h('div', { className: 'card-title' }, '📊 話題分布圖'),
      skills.length > 0
        ? h('div', { className: 'understanding-topics-full' },
            ...skills.map(s => renderTopicBar(s.skill, s.count, skills[0] ? skills[0].count : 1))
          )
        : h('p', { style: { color: '#6b5f4a', fontSize: '0.875rem' } }, '尚無足夠資料')
    ),
    // 溝通偏好
    h('div', { className: 'card' },
      h('div', { className: 'card-title' }, '💬 溝通偏好'),
      h('div', { className: 'understanding-detail-grid' },
        renderDetailItem('語言', prefs.language || '繁體中文'),
        renderDetailItem('風格', prefs.communication_style || '探索中'),
        renderDetailItem('長度偏好', prefs.response_length || '探索中'),
        renderDetailItem('活躍時段', prefs.active_hours || '探索中'),
        renderDetailItem('決策風格', interactions.decision_style || '探索中'),
        renderDetailItem('回饋風格', interactions.feedback_style || '探索中')
      )
    ),
    // 知識水平
    h('div', { className: 'card' },
      h('div', { className: 'card-title' }, '🧠 知識水平'),
      h('div', { className: 'understanding-detail-grid' },
        renderDetailItem('技術素養', knowledge.tech_literacy || '探索中'),
        renderDetailItem('AI 熟悉度', knowledge.ai_familiarity || '探索中'),
        renderDetailItem('專業領域', (knowledge.domain_expertise || []).join(', ') || '探索中'),
        renderDetailItem('主要痛點', needs.main_pain_point && needs.main_pain_point !== 'unknown' ? needs.main_pain_point : '探索中'),
        renderDetailItem('即時需求', needs.immediate_need && needs.immediate_need !== 'unknown' ? needs.immediate_need : '探索中')
      )
    )
  );
}

function renderDetailItem(label, value) {
  return h('div', { className: 'detail-item' },
    h('div', { className: 'detail-item-label' }, label),
    h('div', { className: 'detail-item-value' }, value)
  );
}

// ── 🏆 里程碑 ──
function renderMilestonesContent() {
  if (state.memoryOverviewLoading || !state.memoryOverview) {
    return h('div', { className: 'loading', style: { padding: '2rem' } },
      h('div', { className: 'spinner' }),
      h('p', null, '載入中...')
    );
  }
  const ms = state.memoryOverview.milestones || {};
  const achieved = ms.achieved || [];
  const upcoming = ms.upcoming || [];
  const soulRings = state.memoryOverview.soulRings || [];

  return h('div', { className: 'milestones-content' },
    // 關係摘要
    h('div', { className: 'card milestone-hero' },
      h('div', { className: 'milestone-hero-stat' },
        h('div', { className: 'milestone-hero-value' }, String(ms.totalInteractions || 0)),
        h('div', { className: 'milestone-hero-label' }, '次共享體驗')
      ),
      h('div', { className: 'milestone-hero-stat' },
        h('div', { className: 'milestone-hero-value' }, String(ms.daysKnown || 0)),
        h('div', { className: 'milestone-hero-label' }, '天相識')
      ),
      h('div', { className: 'milestone-hero-stat' },
        h('div', { className: 'milestone-hero-value' }, trustLabels[ms.trustLevel] || '初始'),
        h('div', { className: 'milestone-hero-label' }, '信任等級')
      )
    ),
    // 已達成
    h('div', { className: 'card' },
      h('div', { className: 'card-title' }, '🏆 已達成里程碑'),
      achieved.length === 0
        ? h('p', { style: { color: '#6b5f4a', fontSize: '0.875rem' } }, '即將達成第一個里程碑')
        : h('div', { className: 'milestone-list' },
            ...achieved.map(a =>
              h('div', { className: 'milestone-item achieved' },
                h('div', { className: 'milestone-icon' }, '🏅'),
                h('div', { className: 'milestone-body' },
                  h('div', { className: 'milestone-label' }, a.label),
                  h('div', { className: 'milestone-meta' }, '第 ' + a.count + ' 次互動')
                )
              )
            )
          )
    ),
    // 未解鎖
    h('div', { className: 'card' },
      h('div', { className: 'card-title' }, '🔒 即將解鎖'),
      upcoming.length === 0
        ? h('p', { style: { color: '#6b5f4a' } }, '所有里程碑已解鎖！')
        : h('div', { className: 'milestone-list' },
            ...upcoming.map(u =>
              h('div', { className: 'milestone-item locked' },
                h('div', { className: 'milestone-icon locked' }, '🔒'),
                h('div', { className: 'milestone-body' },
                  h('div', { className: 'milestone-label' }, u.label),
                  h('div', { className: 'milestone-progress' },
                    h('div', { className: 'progress-bar' },
                      h('div', { className: 'progress-fill', style: { width: (u.progress * 100) + '%' } })
                    ),
                    h('div', { className: 'milestone-progress-text' },
                      Math.round(u.progress * 100) + '%'
                    )
                  )
                )
              )
            )
          )
    ),
    // 靈魂之環
    soulRings.length > 0
      ? h('div', { className: 'card' },
          h('div', { className: 'card-title' }, '💎 靈魂之環'),
          h('div', { className: 'milestone-list' },
            ...soulRings.map(sr =>
              h('div', { className: 'milestone-item achieved' },
                h('div', { className: 'milestone-icon' }, '💎'),
                h('div', { className: 'milestone-body' },
                  h('div', { className: 'milestone-label' }, sr.name || sr.type || '成長'),
                  h('div', { className: 'milestone-meta' }, sr.description || '')
                )
              )
            )
          )
        )
      : null
  );
}

// ── 日期側邊欄 ──
function renderMemoryDateList() {
  const dates = state.memoryDates;
  if (dates.length === 0) {
    return h('div', { className: 'memory-sidebar' },
      h('div', { className: 'memory-sidebar-title' }, '日期'),
      h('div', { className: 'memory-empty-dates' },
        h('p', { style: { color: '#6b5f4a' } }, '尚無記憶'),
        h('p', { style: { color: '#475569', fontSize: '0.8rem', marginTop: '0.5rem' } },
          '與 MUSEON 對話後，記憶將在此出現')
      )
    );
  }

  return h('div', { className: 'memory-sidebar' },
    h('div', { className: 'memory-sidebar-title' }, '日期'),
    h('div', { className: 'memory-date-list' },
      ...dates.map(date =>
        h('button', {
          className: `memory-date-item ${state.selectedMemoryDate === date ? 'active' : ''}`,
          onClick: () => {
            state.selectedMemoryDate = date;
            loadJournalEntries(date);
          }
        }, formatDateChinese(date))
      )
    )
  );
}

function formatDateChinese(dateStr) {
  try {
    const d = new Date(dateStr);
    const month = d.getMonth() + 1;
    const day = d.getDate();
    const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
    const weekday = weekdays[d.getDay()];
    return month + '月' + day + '日 (週' + weekday + ')';
  } catch (e) {
    return dateStr;
  }
}

// ═══════════════════════════════════════
// Tab: 📋 Secretary — 秘書台
// ═══════════════════════════════════════

async function loadSecretaryData() {
  state.secretaryLoading = true;
  try {
    if (window.museon && window.museon.getSecretaryData) {
      state.secretaryData = await window.museon.getSecretaryData();
    }
    // Load AI suggestions (non-blocking)
    if (window.museon && window.museon.getSecretaryAiSuggestions) {
      window.museon.getSecretaryAiSuggestions()
        .then(result => { state.secretaryAiSuggestions = result; render(); })
        .catch(() => {});
    }
  } catch (err) {
    console.error('[Secretary] Load failed:', err);
    state.secretaryData = { tasks: { tasks: [] }, projects: { projects: [] }, customers: { customers: [] } };
  }
  state.secretaryLoading = false;
}

function renderSecretary() {
  if (state.secretaryLoading && !state.secretaryData) {
    return h('div', { className: 'tab-empty' },
      h('div', { style: { fontSize: '3rem', marginBottom: '1rem' } }, '\uD83D\uDCCB'),
      h('p', { style: { color: '#9a8b70', fontSize: '1.1rem' } }, '\u6B63\u5728\u8B80\u53D6\u79D8\u66F8\u53F0...'),
      h('div', { className: 'spinner', style: { marginTop: '1rem' } })
    );
  }

  const data = state.secretaryData || {};
  const tasks = (data.tasks || {}).tasks || [];
  const projects = (data.projects || {}).projects || [];
  const customers = (data.customers || {}).customers || [];

  return h('div', { className: 'secretary-tab' },
    renderSecretaryBriefing(tasks, projects, customers),
    renderEisenhowerMatrix(tasks),
    renderSecretaryCards(tasks, projects, customers),
    renderGanttChart(tasks),
    renderAiSuggestions(),
    renderSecretaryItemModal(tasks, projects, customers)
  );
}

// ─── Section 1: AI Briefing ───

function renderSecretaryBriefing(tasks, projects, customers) {
  const hour = new Date().getHours();
  const greeting = hour < 12 ? '\u65E9\u5B89' : hour < 18 ? '\u5348\u5B89' : '\u665A\u5B89';
  const pendingTodos = tasks.filter(t => t.status !== 'completed').length;
  const activeProjects = projects.filter(p => p.status === 'active').length;
  const today = new Date().toISOString().slice(0, 10);
  const customerFollowups = customers.filter(c =>
    c.next_action_date && c.next_action_date <= today && c.status !== 'dormant'
  ).length;
  const overdue = tasks.filter(t => t.status !== 'completed' && t.due_date && t.due_date < today).length;

  return h('div', { className: 'secretary-briefing' },
    h('div', { className: 'secretary-greeting' },
      `${greeting}\u8001\u95C6\uFF0C\u4ECA\u5929\u6709 ${pendingTodos} \u4EF6\u4E8B\u60C5\u9700\u8981\u6CE8\u610F`
    ),
    h('div', { className: 'secretary-badges' },
      renderSecBadge('\uD83D\uDCDD', '\u5F85\u8FA6', pendingTodos, '#c9a96e'),
      renderSecBadge('\uD83D\uDCC1', '\u5C08\u6848\u9032\u884C\u4E2D', activeProjects, '#8b5cf6'),
      renderSecBadge('\uD83E\uDD1D', '\u5BA2\u6236\u8DDF\u9032', customerFollowups, '#10b981'),
      overdue > 0 ? renderSecBadge('\u26A0\uFE0F', '\u5DF2\u903E\u671F', overdue, '#ef4444') : null
    )
  );
}

function renderSecBadge(icon, label, value, color) {
  return h('div', { className: 'secretary-badge', style: { borderColor: color + '40' } },
    h('span', { style: { fontSize: '1.25rem' } }, icon),
    h('div', null,
      h('div', { style: { fontSize: '1.5rem', fontWeight: 800, color, fontVariantNumeric: 'tabular-nums' } }, String(value)),
      h('div', { style: { fontSize: '0.75rem', color: '#9a8b70' } }, label)
    )
  );
}

// ─── Section 2: Eisenhower Matrix (SVG) ───

function renderEisenhowerMatrix(tasks) {
  const activeTasks = tasks.filter(t => t.status !== 'completed');
  const W = 500, H = 400, PAD = 40;
  const midX = PAD + (W - 2 * PAD) / 2;
  const midY = PAD + (H - 2 * PAD) / 2;

  const typeColors = { todo: '#c9a96e', project_task: '#8b5cf6', customer_action: '#10b981' };
  const priorityRadius = { critical: 10, high: 8, medium: 6, low: 5 };

  // Map urgency/importance (0-100) to SVG coords
  function toX(urgency) { return PAD + (urgency / 100) * (W - 2 * PAD); }
  function toY(importance) { return PAD + ((100 - importance) / 100) * (H - 2 * PAD); }

  const quadrantLabels = [
    { text: '\u91CD\u8981\u4E14\u7DCA\u6025', x: (midX + W - PAD) / 2, y: PAD + 14, color: '#ef4444' },
    { text: '\u91CD\u8981\u4E0D\u7DCA\u6025', x: (PAD + midX) / 2, y: PAD + 14, color: '#3b82f6' },
    { text: '\u7DCA\u6025\u4E0D\u91CD\u8981', x: (midX + W - PAD) / 2, y: H - PAD - 6, color: '#f59e0b' },
    { text: '\u4E0D\u7DCA\u6025\u4E0D\u91CD\u8981', x: (PAD + midX) / 2, y: H - PAD - 6, color: '#6b5f4a' },
  ];

  return h('div', { className: 'secretary-matrix' },
    h('div', { className: 'card-title' }, '\uD83C\uDFAF \u5168\u5C40\u89C0\u2014\u2014\u7DCA\u6025\xD7\u91CD\u8981\u56DB\u8C61\u9650'),
    h('div', { style: { position: 'relative' } },
      svg('svg', { viewBox: `0 0 ${W} ${H}`, style: 'width:100%;height:auto;' },
        // Quadrant backgrounds
        svg('rect', { x: midX, y: PAD, width: W - PAD - midX, height: midY - PAD, fill: 'rgba(239,68,68,0.06)', rx: 4 }),
        svg('rect', { x: PAD, y: PAD, width: midX - PAD, height: midY - PAD, fill: 'rgba(59,130,246,0.06)', rx: 4 }),
        svg('rect', { x: midX, y: midY, width: W - PAD - midX, height: H - PAD - midY, fill: 'rgba(245,158,11,0.06)', rx: 4 }),
        svg('rect', { x: PAD, y: midY, width: midX - PAD, height: H - PAD - midY, fill: 'rgba(107,95,74,0.06)', rx: 4 }),
        // Axis lines
        svg('line', { x1: midX, y1: PAD, x2: midX, y2: H - PAD, stroke: '#2d3a5c', 'stroke-width': 1 }),
        svg('line', { x1: PAD, y1: midY, x2: W - PAD, y2: midY, stroke: '#2d3a5c', 'stroke-width': 1 }),
        // Axis labels
        svg('text', { x: W - PAD, y: midY + 16, fill: '#6b5f4a', 'font-size': 10, 'text-anchor': 'end' }, '\u7DCA\u6025 \u2192'),
        svg('text', { x: PAD, y: midY + 16, fill: '#6b5f4a', 'font-size': 10 }, '\u2190 \u4E0D\u7DCA\u6025'),
        svg('text', { x: midX + 4, y: PAD + 12, fill: '#6b5f4a', 'font-size': 10 }, '\u2191 \u91CD\u8981'),
        svg('text', { x: midX + 4, y: H - PAD - 4, fill: '#6b5f4a', 'font-size': 10 }, '\u2193 \u4E0D\u91CD\u8981'),
        // Quadrant labels
        ...quadrantLabels.map(q =>
          svg('text', { x: q.x, y: q.y, fill: q.color, 'font-size': 11, 'font-weight': 600, 'text-anchor': 'middle', opacity: 0.7 }, q.text)
        ),
        // Task dots
        ...activeTasks.map(t => {
          const cx = toX(t.urgency || 50);
          const cy = toY(t.importance || 50);
          const r = priorityRadius[t.priority] || 6;
          const fill = typeColors[t.type] || '#c9a96e';
          return svg('circle', {
            cx, cy, r, fill, opacity: 0.85,
            stroke: '#f3ede0', 'stroke-width': 1.5,
            style: 'cursor:pointer;transition:r 0.15s,opacity 0.15s;',
            onmouseover: (e) => showSecretaryTooltip(e, t),
            onmouseout: hideSecretaryTooltip,
            onclick: () => { state.secretaryModalItem = { ...t, _type: 'task' }; render(); }
          });
        })
      )
    )
  );
}

// Shared tooltip for secretary tab
let _secTooltipEl = null;
function showSecretaryTooltip(e, item) {
  if (!_secTooltipEl) {
    _secTooltipEl = document.createElement('div');
    _secTooltipEl.className = 'secretary-tooltip';
    document.body.appendChild(_secTooltipEl);
  }
  const priorityZh = { critical: '\u7DCA\u6025', high: '\u9AD8', medium: '\u4E2D', low: '\u4F4E' };
  const statusZh = { pending: '\u5F85\u8FA6', in_progress: '\u9032\u884C\u4E2D', completed: '\u5B8C\u6210' };
  _secTooltipEl.innerHTML = `<strong>${item.title || ''}</strong><br/>` +
    `\u512A\u5148: ${priorityZh[item.priority] || item.priority || '-'}` +
    (item.due_date ? ` \u00B7 \u5230\u671F: ${item.due_date}` : '') +
    (item.status ? `<br/>\u72C0\u614B: ${statusZh[item.status] || item.status}` : '');
  _secTooltipEl.style.display = 'block';
  const rect = e.target.getBoundingClientRect ? e.target.getBoundingClientRect() : { left: e.clientX, top: e.clientY };
  _secTooltipEl.style.left = (rect.left + 16) + 'px';
  _secTooltipEl.style.top = (rect.top - 10) + 'px';
}
function hideSecretaryTooltip() {
  if (_secTooltipEl) _secTooltipEl.style.display = 'none';
}

// ─── Section 3: Cards ───

function renderSecretaryCards(tasks, projects, customers) {
  return h('div', { className: 'secretary-cards' },
    renderTodoCard(tasks),
    renderProjectsCard(projects),
    renderCustomersCard(customers),
    renderTimelineCard(tasks)
  );
}

function renderTodoCard(tasks) {
  const pending = tasks.filter(t => t.status !== 'completed')
    .sort((a, b) => {
      const pOrder = { critical: 0, high: 1, medium: 2, low: 3 };
      return (pOrder[a.priority] || 3) - (pOrder[b.priority] || 3);
    });
  const priorityColors = { critical: '#ef4444', high: '#f59e0b', medium: '#3b82f6', low: '#6b5f4a' };

  return h('div', { className: 'card' },
    h('div', { className: 'card-title' }, '\uD83D\uDCDD \u5F85\u8FA6\u4E8B\u9805'),
    pending.length === 0
      ? h('p', { style: { color: '#6b5f4a', fontSize: '0.875rem' } }, '\u5168\u90E8\u5B8C\u6210\uFF01')
      : h('div', null,
          ...pending.slice(0, 8).map(t =>
            h('div', {
              className: 'secretary-card-item',
              onClick: () => { state.secretaryModalItem = { ...t, _type: 'task' }; render(); }
            },
              h('div', { className: 'secretary-priority-dot', style: { background: priorityColors[t.priority] || '#6b5f4a' } }),
              h('div', { style: { flex: 1, minWidth: 0 } },
                h('div', { style: { color: '#e8dcc6', fontSize: '0.85rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, t.title),
                t.status === 'in_progress'
                  ? h('span', { style: { fontSize: '0.6875rem', color: '#3b82f6' } }, '\u9032\u884C\u4E2D')
                  : null
              ),
              t.due_date
                ? h('div', { className: 'secretary-due-date' }, formatSecDate(t.due_date))
                : null
            )
          ),
          pending.length > 8
            ? h('div', { style: { fontSize: '0.75rem', color: '#6b5f4a', textAlign: 'center', paddingTop: '0.5rem' } },
                `\u2026\u53CA\u5176\u4ED6 ${pending.length - 8} \u4EF6`)
            : null
        )
  );
}

function renderProjectsCard(projects) {
  const statusColors = { planning: '#6b5f4a', active: '#3b82f6', paused: '#f59e0b', completed: '#10b981' };
  const statusZh = { planning: '\u898F\u5283\u4E2D', active: '\u9032\u884C\u4E2D', paused: '\u66AB\u505C', completed: '\u5B8C\u6210' };

  return h('div', { className: 'card' },
    h('div', { className: 'card-title' }, '\uD83D\uDCC1 \u5C08\u6848\u6982\u6CC1'),
    projects.length === 0
      ? h('p', { style: { color: '#6b5f4a', fontSize: '0.875rem' } }, '\u5C1A\u7121\u5C08\u6848')
      : h('div', null,
          ...projects.map(p =>
            h('div', {
              className: 'secretary-card-item', style: { flexDirection: 'column', alignItems: 'stretch', gap: '0.375rem' },
              onClick: () => { state.secretaryModalItem = { ...p, _type: 'project' }; render(); }
            },
              h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' } },
                h('span', { style: { color: '#e8dcc6', fontSize: '0.85rem', fontWeight: 600 } }, p.name),
                h('span', { style: { fontSize: '0.6875rem', color: statusColors[p.status] || '#6b5f4a', fontWeight: 600 } },
                  statusZh[p.status] || p.status)
              ),
              h('div', { className: 'secretary-progress-bar' },
                h('div', { className: 'secretary-progress-fill', style: {
                  width: (p.progress || 0) + '%',
                  background: `linear-gradient(90deg, ${statusColors[p.status] || '#3b82f6'}, ${statusColors[p.status] || '#3b82f6'}88)`
                } })
              ),
              h('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: '0.6875rem', color: '#6b5f4a' } },
                h('span', null, `${p.progress || 0}%`),
                p.target_date ? h('span', null, `\u76EE\u6A19 ${formatSecDate(p.target_date)}`) : null
              )
            )
          )
        )
  );
}

function renderCustomersCard(customers) {
  const today = new Date().toISOString().slice(0, 10);
  const statusZh = { lead: '\u6F5B\u5BA2', active: '\u6D3B\u8E8D', dormant: '\u6C89\u5BC2' };
  const statusColors = { lead: '#f59e0b', active: '#10b981', dormant: '#6b5f4a' };

  return h('div', { className: 'card' },
    h('div', { className: 'card-title' }, '\uD83E\uDD1D \u5BA2\u6236\u4E8B\u9805'),
    customers.length === 0
      ? h('p', { style: { color: '#6b5f4a', fontSize: '0.875rem' } }, '\u5C1A\u7121\u5BA2\u6236\u8CC7\u6599')
      : h('div', null,
          ...customers.map(c => {
            const daysSince = c.last_interaction
              ? Math.floor((Date.now() - new Date(c.last_interaction).getTime()) / 86400000)
              : null;
            const urgentFollowup = daysSince !== null && daysSince > 14;
            return h('div', {
              className: 'secretary-card-item',
              onClick: () => { state.secretaryModalItem = { ...c, _type: 'customer' }; render(); }
            },
              h('div', { style: {
                width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                background: urgentFollowup ? '#ef4444' : (statusColors[c.status] || '#6b5f4a')
              } }),
              h('div', { style: { flex: 1, minWidth: 0 } },
                h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.375rem' } },
                  h('span', { style: { color: '#e8dcc6', fontSize: '0.85rem' } }, c.name),
                  h('span', { style: { fontSize: '0.625rem', color: statusColors[c.status], background: statusColors[c.status] + '18', padding: '1px 6px', borderRadius: 4 } },
                    statusZh[c.status] || c.status)
                ),
                h('div', { style: { fontSize: '0.6875rem', color: '#6b5f4a', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } },
                  c.next_action || '\u7121\u5F85\u8FA6\u4E8B\u9805')
              ),
              daysSince !== null
                ? h('div', { style: { fontSize: '0.6875rem', color: urgentFollowup ? '#ef4444' : '#6b5f4a', flexShrink: 0 } },
                    daysSince + '\u5929\u524D')
                : null
            );
          })
        )
  );
}

function renderTimelineCard(tasks) {
  const today = new Date();
  const todayStr = today.toISOString().slice(0, 10);
  const twoWeeks = new Date(today.getTime() + 14 * 86400000).toISOString().slice(0, 10);
  const upcoming = tasks
    .filter(t => t.status !== 'completed' && t.due_date && t.due_date >= todayStr && t.due_date <= twoWeeks)
    .sort((a, b) => a.due_date.localeCompare(b.due_date));

  const priorityColors = { critical: '#ef4444', high: '#f59e0b', medium: '#3b82f6', low: '#6b5f4a' };

  return h('div', { className: 'card' },
    h('div', { className: 'card-title' }, '\uD83D\uDCC5 \u8FD1\u671F\u6642\u7A0B'),
    upcoming.length === 0
      ? h('p', { style: { color: '#6b5f4a', fontSize: '0.875rem' } }, '\u8FD1\u5169\u9031\u7121\u622A\u6B62\u65E5')
      : h('div', null,
          ...upcoming.map(t => {
            const daysLeft = Math.ceil((new Date(t.due_date) - today) / 86400000);
            const daysLabel = daysLeft === 0 ? '\u4ECA\u5929' : daysLeft === 1 ? '\u660E\u5929' : `${daysLeft} \u5929\u5F8C`;
            return h('div', {
              className: 'secretary-card-item',
              onClick: () => { state.secretaryModalItem = { ...t, _type: 'task' }; render(); }
            },
              h('div', { style: {
                minWidth: 48, fontSize: '0.6875rem', fontWeight: 700,
                color: daysLeft <= 1 ? '#ef4444' : daysLeft <= 3 ? '#f59e0b' : '#9a8b70'
              } }, daysLabel),
              h('div', { className: 'secretary-priority-dot', style: { background: priorityColors[t.priority] || '#6b5f4a' } }),
              h('div', { style: { flex: 1, color: '#e8dcc6', fontSize: '0.85rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, t.title),
              h('div', { style: { fontSize: '0.6875rem', color: '#6b5f4a', flexShrink: 0 } }, t.due_date.slice(5))
            );
          })
        )
  );
}

// ─── Section 4: Gantt Chart (SVG) ───

function renderGanttChart(tasks) {
  const activeTasks = tasks.filter(t => t.status !== 'completed' && t.start_date && t.due_date)
    .sort((a, b) => a.start_date.localeCompare(b.start_date));

  if (activeTasks.length === 0) {
    return h('div', { className: 'secretary-gantt' },
      h('div', { className: 'card-title' }, '\uD83D\uDCC8 \u7518\u7279\u5716'),
      h('p', { style: { color: '#6b5f4a', fontSize: '0.875rem' } }, '\u7121\u53EF\u986F\u793A\u7684\u4EFB\u52D9')
    );
  }

  // Calculate time range
  const allDates = activeTasks.flatMap(t => [t.start_date, t.due_date]);
  const minDate = new Date(allDates.sort()[0]);
  const maxDate = new Date(allDates.sort().pop());
  // Add buffer
  minDate.setDate(minDate.getDate() - 2);
  maxDate.setDate(maxDate.getDate() + 3);

  const zoom = state.secretaryGanttZoom || 'week';
  const dayWidth = zoom === 'day' ? 40 : zoom === 'week' ? 20 : 8;
  const totalDays = Math.ceil((maxDate - minDate) / 86400000) + 1;
  const ROW_H = 36;
  const LABEL_W = 140;
  const chartW = LABEL_W + totalDays * dayWidth + 20;
  const chartH = 30 + activeTasks.length * ROW_H + 10;

  function dayX(dateStr) {
    const d = new Date(dateStr);
    const diff = Math.floor((d - minDate) / 86400000);
    return LABEL_W + diff * dayWidth;
  }

  const statusColors = { pending: '#4a4035', in_progress: '#3b82f6', completed: '#10b981' };
  const typeColors = { todo: '#c9a96e', project_task: '#8b5cf6', customer_action: '#10b981' };

  // Generate date headers
  const dateHeaders = [];
  const headerDate = new Date(minDate);
  while (headerDate <= maxDate) {
    const ds = headerDate.toISOString().slice(0, 10);
    const dayOfWeek = headerDate.getDay();
    const showLabel = zoom === 'day' || (zoom === 'week' && dayOfWeek === 1) || (zoom === 'month' && headerDate.getDate() === 1);
    if (showLabel) {
      dateHeaders.push({ x: dayX(ds), label: `${headerDate.getMonth() + 1}/${headerDate.getDate()}` });
    }
    headerDate.setDate(headerDate.getDate() + 1);
  }

  // Today line
  const todayStr = new Date().toISOString().slice(0, 10);
  const todayX = dayX(todayStr);

  // Build dependency arrows
  const arrows = [];
  activeTasks.forEach((t, i) => {
    if (!t.dependencies || t.dependencies.length === 0) return;
    t.dependencies.forEach(depId => {
      const depIdx = activeTasks.findIndex(x => x.id === depId);
      if (depIdx < 0) return;
      const dep = activeTasks[depIdx];
      const fromX = dayX(dep.due_date) + dayWidth;
      const fromY = 30 + depIdx * ROW_H + ROW_H / 2;
      const toX = dayX(t.start_date);
      const toY = 30 + i * ROW_H + ROW_H / 2;
      const midX = (fromX + toX) / 2;
      arrows.push({ d: `M${fromX},${fromY} L${midX},${fromY} L${midX},${toY} L${toX},${toY}` });
    });
  });

  return h('div', { className: 'secretary-gantt' },
    h('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' } },
      h('div', { className: 'card-title', style: { marginBottom: 0 } }, '\uD83D\uDCC8 \u7518\u7279\u5716'),
      h('div', { className: 'secretary-gantt-controls' },
        ...['day', 'week', 'month'].map(z =>
          h('button', {
            className: `secretary-gantt-zoom-btn ${zoom === z ? 'active' : ''}`,
            onClick: () => { state.secretaryGanttZoom = z; render(); }
          }, z === 'day' ? '\u65E5' : z === 'week' ? '\u9031' : '\u6708')
        )
      )
    ),
    h('div', { className: 'secretary-gantt-scroll' },
      svg('svg', { viewBox: `0 0 ${chartW} ${chartH}`, width: chartW, height: chartH, style: 'display:block;' },
        // Arrow marker definition
        svg('defs', null,
          svg('marker', { id: 'gantt-arrow', viewBox: '0 0 10 10', refX: 10, refY: 5, markerWidth: 6, markerHeight: 6, orient: 'auto' },
            svg('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: '#9a8b70' })
          )
        ),
        // Date headers
        ...dateHeaders.map(dh =>
          svg('text', { x: dh.x + 2, y: 16, fill: '#6b5f4a', 'font-size': 10 }, dh.label)
        ),
        // Header line
        svg('line', { x1: LABEL_W, y1: 24, x2: chartW, y2: 24, stroke: '#2d3a5c', 'stroke-width': 0.5 }),
        // Today line
        todayX >= LABEL_W && todayX <= chartW
          ? svg('line', { x1: todayX, y1: 24, x2: todayX, y2: chartH, stroke: '#ef4444', 'stroke-width': 1, 'stroke-dasharray': '4,3', opacity: 0.5 })
          : null,
        // Row backgrounds
        ...activeTasks.map((_, i) =>
          svg('rect', { x: 0, y: 30 + i * ROW_H, width: chartW, height: ROW_H, fill: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)' })
        ),
        // Task labels (left)
        ...activeTasks.map((t, i) =>
          svg('text', {
            x: 8, y: 30 + i * ROW_H + ROW_H / 2 + 4,
            fill: '#e8dcc6', 'font-size': 11,
            style: 'cursor:pointer;',
            onclick: () => { state.secretaryModalItem = { ...t, _type: 'task' }; render(); }
          }, t.title.length > 14 ? t.title.slice(0, 14) + '\u2026' : t.title)
        ),
        // Task bars
        ...activeTasks.map((t, i) => {
          const x1 = dayX(t.start_date);
          const x2 = dayX(t.due_date) + dayWidth;
          const barW = Math.max(x2 - x1, dayWidth);
          const y = 30 + i * ROW_H + 8;
          const barH = ROW_H - 16;
          const fill = typeColors[t.type] || statusColors[t.status] || '#4a4035';
          return svg('rect', {
            x: x1, y, width: barW, height: barH,
            fill, rx: 4, opacity: t.status === 'pending' ? 0.5 : 0.85,
            style: 'cursor:pointer;',
            onmouseover: (e) => showSecretaryTooltip(e, t),
            onmouseout: hideSecretaryTooltip,
            onclick: () => { state.secretaryModalItem = { ...t, _type: 'task' }; render(); }
          });
        }),
        // Dependency arrows
        ...arrows.map(a =>
          svg('path', { d: a.d, fill: 'none', stroke: '#9a8b70', 'stroke-width': 1.5, 'marker-end': 'url(#gantt-arrow)', opacity: 0.7 })
        )
      )
    )
  );
}

// ─── Section 5: AI Suggestions ───

function renderAiSuggestions() {
  const data = state.secretaryAiSuggestions || {};
  const suggestions = data.suggestions || [];

  const typeStyles = {
    warning: { border: '#ef4444', bg: 'rgba(239,68,68,0.04)' },
    urgent: { border: '#f59e0b', bg: 'rgba(245,158,11,0.04)' },
    reminder: { border: '#c9a96e', bg: 'rgba(201,169,110,0.04)' },
    opportunity: { border: '#10b981', bg: 'rgba(16,185,129,0.04)' },
    alert: { border: '#8b5cf6', bg: 'rgba(139,92,246,0.04)' },
    'chain-risk': { border: '#f59e0b', bg: 'rgba(245,158,11,0.04)' },
  };

  return h('div', { className: 'secretary-ai-section' },
    h('div', { className: 'card-title' }, '\uD83E\uDDE0 MUSEON \u5EFA\u8B70'),
    suggestions.length === 0
      ? h('div', { className: 'card', style: { textAlign: 'center' } },
          h('p', { style: { color: '#6b5f4a', fontSize: '0.875rem' } }, '\u76EE\u524D\u6C92\u6709\u7279\u5225\u5EFA\u8B70\uFF0C\u4E00\u5207\u6B63\u5E38 \u2705')
        )
      : h('div', null,
          ...suggestions.map(s => {
            const style = typeStyles[s.type] || typeStyles.reminder;
            return h('div', { className: 'secretary-ai-card', style: { borderLeftColor: style.border, background: style.bg } },
              h('div', { className: 'secretary-ai-card-source' }, `${s.icon || '\uD83D\uDCA1'} ${s.source || 'MUSEON'}`),
              h('div', { className: 'secretary-ai-card-title' }, s.title || ''),
              h('div', { className: 'secretary-ai-card-detail' }, s.detail || '')
            );
          })
        )
  );
}

// ─── Floating Detail Modal ───

function renderSecretaryItemModal(tasks, projects, customers) {
  const item = state.secretaryModalItem;
  if (!item) return h('span');

  const close = () => { state.secretaryModalItem = null; render(); };

  let title = '', rows = [];
  const priorityZh = { critical: '\u7DCA\u6025', high: '\u9AD8', medium: '\u4E2D', low: '\u4F4E' };
  const statusZh = { pending: '\u5F85\u8FA6', in_progress: '\u9032\u884C\u4E2D', completed: '\u5B8C\u6210', planning: '\u898F\u5283\u4E2D', active: '\u9032\u884C\u4E2D', paused: '\u66AB\u505C', lead: '\u6F5B\u5BA2', dormant: '\u6C89\u5BC2' };

  if (item._type === 'task') {
    title = '\uD83D\uDCDD ' + (item.title || '');
    rows = [
      { label: '\u72C0\u614B', value: statusZh[item.status] || item.status },
      { label: '\u512A\u5148\u7D1A', value: priorityZh[item.priority] || item.priority },
      item.due_date ? { label: '\u5230\u671F\u65E5', value: item.due_date } : null,
      item.start_date ? { label: '\u958B\u59CB\u65E5', value: item.start_date } : null,
      item.description ? { label: '\u8AAA\u660E', value: item.description } : null,
      item.tags && item.tags.length > 0 ? { label: '\u6A19\u7C64', value: item.tags.join(', ') } : null,
      item.related_customer ? { label: '\u76F8\u95DC\u5BA2\u6236', value: (customers.find(c => c.id === item.related_customer) || {}).name || item.related_customer } : null,
      item.related_project ? { label: '\u76F8\u95DC\u5C08\u6848', value: (projects.find(p => p.id === item.related_project) || {}).name || item.related_project } : null,
      item.dependencies && item.dependencies.length > 0 ? { label: '\u524D\u7F6E\u4EFB\u52D9', value: item.dependencies.map(id => (tasks.find(t => t.id === id) || {}).title || id).join(', ') } : null,
      item.dependents && item.dependents.length > 0 ? { label: '\u5F8C\u7E8C\u4EFB\u52D9', value: item.dependents.map(id => (tasks.find(t => t.id === id) || {}).title || id).join(', ') } : null,
    ];
  } else if (item._type === 'project') {
    title = '\uD83D\uDCC1 ' + (item.name || '');
    rows = [
      { label: '\u72C0\u614B', value: statusZh[item.status] || item.status },
      { label: '\u9032\u5EA6', value: (item.progress || 0) + '%' },
      item.start_date ? { label: '\u958B\u59CB\u65E5', value: item.start_date } : null,
      item.target_date ? { label: '\u76EE\u6A19\u65E5', value: item.target_date } : null,
      item.description ? { label: '\u8AAA\u660E', value: item.description } : null,
      item.task_ids && item.task_ids.length > 0 ? { label: '\u5305\u542B\u4EFB\u52D9', value: item.task_ids.map(id => (tasks.find(t => t.id === id) || {}).title || id).join(', ') } : null,
    ];
  } else if (item._type === 'customer') {
    title = '\uD83E\uDD1D ' + (item.name || '');
    rows = [
      { label: '\u806F\u7D61\u4EBA', value: item.contact_person || '-' },
      { label: '\u72C0\u614B', value: statusZh[item.status] || item.status },
      item.phone ? { label: '\u96FB\u8A71', value: item.phone } : null,
      item.email ? { label: 'Email', value: item.email } : null,
      item.last_interaction ? { label: '\u4E0A\u6B21\u4E92\u52D5', value: item.last_interaction.slice(0, 10) } : null,
      item.next_action ? { label: '\u4E0B\u6B65\u884C\u52D5', value: item.next_action } : null,
      item.next_action_date ? { label: '\u884C\u52D5\u622A\u6B62', value: item.next_action_date } : null,
      item.notes ? { label: '\u5099\u8A3B', value: item.notes } : null,
      item.tags && item.tags.length > 0 ? { label: '\u6A19\u7C64', value: item.tags.join(', ') } : null,
    ];
  }

  rows = rows.filter(Boolean);

  return h('div', {
    className: 'crystal-modal-overlay',
    onClick: (e) => { if (e.target === e.currentTarget) close(); }
  },
    h('div', { className: 'crystal-modal', style: { maxWidth: '480px' } },
      h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem 1.25rem', borderBottom: '1px solid #222d4a' } },
        h('div', { style: { fontSize: '1.125rem', fontWeight: 700, color: '#e8dcc6' } }, title),
        h('button', {
          style: { background: 'none', border: 'none', color: '#6b5f4a', fontSize: '1.25rem', cursor: 'pointer' },
          onClick: close
        }, '\u2715')
      ),
      h('div', { style: { padding: '1rem 1.25rem', overflowY: 'auto', maxHeight: '60vh' } },
        ...rows.map(r =>
          h('div', { style: { display: 'flex', gap: '0.75rem', padding: '0.5rem 0', borderBottom: '1px solid rgba(34,45,74,0.3)' } },
            h('div', { style: { minWidth: 72, fontSize: '0.8125rem', color: '#6b5f4a', fontWeight: 600 } }, r.label),
            h('div', { style: { fontSize: '0.8125rem', color: '#e8dcc6', lineHeight: 1.5 } }, r.value)
          )
        )
      )
    )
  );
}

// ─── Secretary Helpers ───

function formatSecDate(dateStr) {
  try {
    const d = new Date(dateStr);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  } catch (e) {
    return dateStr;
  }
}


function formatAgentTime(isoStr) {
  try {
    const d = new Date(isoStr);
    const month = d.getMonth() + 1;
    const day = d.getDate();
    const hour = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    return `${month}/${day} ${hour}:${min}`;
  } catch (e) {
    return '';
  }
}

// ═══════════════════════════════════════
// Tab 5: 🩺 Doctor
// ═══════════════════════════════════════

async function loadDoctorReport() {
  state.doctorLoading = true;
  render();
  try {
    if (window.museon && window.museon.doctorCheck) {
      const report = await window.museon.doctorCheck();
      state.doctorReport = report;
    } else {
      state.doctorReport = { error: 'doctorCheck API 不可用', overall: 'unknown', checks: [] };
    }
  } catch (err) {
    state.doctorReport = { error: err.message, overall: 'unknown', checks: [] };
  }
  state.doctorLoading = false;
  render();
}

async function handleDoctorRepair(action) {
  state.doctorRepairing[action] = true;
  render();
  try {
    if (!window.museon || !window.museon.doctorRepair) {
      alert('❌ doctorRepair API 不可用');
      state.doctorRepairing[action] = false;
      render();
      return;
    }
    const result = await window.museon.doctorRepair(action);
    // 顯示結果後重新健檢
    alert(`${result.status === 'success' ? '✅' : '❌'} ${result.message}`);
    await loadDoctorReport();
  } catch (err) {
    alert('❌ 修復失敗: ' + err.message);
  }
  state.doctorRepairing[action] = false;
  render();
}

// ─── Guardian 守護者資料載入 ───
// ─── Nightly Pipeline 凌晨整合 ───

async function loadNightlyStatus() {
  try {
    if (window.museon && window.museon.getNightlyStatus) {
      state.nightlyStatus = await window.museon.getNightlyStatus();
    }
  } catch (err) {
    console.error('[MUSEON] loadNightlyStatus error:', err);
    state.nightlyStatus = { error: err.message, status: 'offline' };
  }
  render();
}

async function runNightlyManual() {
  state.nightlyRunning = true;
  render();
  try {
    if (window.museon && window.museon.runNightly) {
      const result = await window.museon.runNightly();
      if (result && result.triggered) {
        state.nightlyStatus = await window.museon.getNightlyStatus();
      }
    }
  } catch (err) {
    console.error('[MUSEON] runNightly error:', err);
  }
  state.nightlyRunning = false;
  render();
}

function renderNightlySection() {
  const ns = state.nightlyStatus;
  const statusIcon = !ns ? '❓' : ns.status === 'ok' ? '✅' : ns.status === 'warning' ? '⚠️' : ns.status === 'never_run' ? '🌑' : '❓';
  const statusColor = !ns ? '#9a8b70' : ns.status === 'ok' ? '#10b981' : ns.status === 'warning' ? '#f59e0b' : '#9a8b70';

  return h('div', { style: { marginTop: '1.5rem' } },
    h('div', { className: 'doctor-summary', style: { marginBottom: '0.75rem' } },
      h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.75rem' } },
        h('span', { style: { fontSize: '1.5rem' } }, '🌙'),
        h('div', null,
          h('div', { style: { fontSize: '1rem', fontWeight: '700', color: '#c9a96e' } }, '凌晨整合管線'),
          h('div', { style: { fontSize: '0.6875rem', color: '#6b5f4a' } },
            ns && ns.completed_at
              ? ('\u4E0A\u6B21\u57F7\u884C: ' + new Date(ns.completed_at).toLocaleString('zh-TW'))
              : '\u5C1A\u672A\u57F7\u884C')
        )
      ),
      h('div', { style: { display: 'flex', gap: '0.5rem', flexShrink: 0 } },
        h('button', {
          className: 'wizard-btn-secondary',
          onClick: loadNightlyStatus,
          style: { fontSize: '0.75rem', padding: '0.3rem 0.75rem' }
        }, '\uD83D\uDD04 \u67E5\u8A62'),
        h('button', {
          className: 'wizard-btn-secondary',
          onClick: runNightlyManual,
          disabled: state.nightlyRunning,
          style: { fontSize: '0.75rem', padding: '0.3rem 0.75rem' }
        }, state.nightlyRunning ? '\u23F3 \u57F7\u884C\u4E2D...' : '\u25B6\uFE0F \u624B\u52D5\u57F7\u884C')
      )
    ),

    ns && ns.summary ? h('div', { style: {
      padding: '0.625rem 1rem', background: 'rgba(255,255,255,0.02)',
      borderRadius: '0.5rem', border: '1px solid ' + statusColor + '22',
      marginBottom: '0.5rem'
    } },
      h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' } },
        h('span', null, statusIcon),
        h('span', { style: { fontSize: '0.8125rem', fontWeight: '600', color: '#e8dcc6' } },
          ns.summary.ok + '/' + ns.summary.total + ' \u6B65\u9A5F\u5B8C\u6210'),
        ns.summary.error > 0
          ? h('span', { style: { color: '#ef4444', fontSize: '0.75rem' } },
              '\u00B7 ' + ns.summary.error + ' \u5931\u6557') : null,
        ns.summary.skipped > 0
          ? h('span', { style: { color: '#f59e0b', fontSize: '0.75rem' } },
              '\u00B7 ' + ns.summary.skipped + ' \u8DF3\u904E') : null,
        ns.elapsed_seconds
          ? h('span', { style: { color: '#9a8b70', fontSize: '0.6875rem' } },
              '\u23F1\uFE0F ' + ns.elapsed_seconds + 's') : null
      )
    ) : null,

    ns && ns.errors && ns.errors.length > 0 ? h('div', { style: {
      paddingLeft: '1rem', fontSize: '0.6875rem', color: '#9a8b70',
      borderLeft: '2px solid #ef444444', marginTop: '0.5rem'
    } },
      h('div', { style: { color: '#ef4444', fontWeight: '600', marginBottom: '0.25rem' } }, '\u5931\u6557\u6B65\u9A5F:'),
      ...(ns.errors.slice(0, 5).map(function(e) {
        return h('div', { style: { marginBottom: '0.125rem' } },
          '\u274C ', h('span', { style: { color: '#e8dcc6' } }, e.step || '?'),
          ': ', (e.error || '').substring(0, 60));
      }))
    ) : null,

    h('div', { style: { fontSize: '0.6875rem', color: '#6b5f4a', marginTop: '0.5rem' } },
      '\u23F0 \u4E0B\u6B21\u6392\u7A0B: ' + (ns && ns.next_scheduled ? ns.next_scheduled : '03:00') + ' | \u65E9\u5831: 07:30')
  );
}

async function loadGuardianStatus() {
  try {
    if (window.museon && window.museon.getGuardianStatus) {
      state.guardianStatus = await window.museon.getGuardianStatus();
    }
  } catch (err) {
    console.error('[MUSEON] loadGuardianStatus error:', err);
    state.guardianStatus = { error: err.message };
  }
  render();
}

async function runGuardianCheck() {
  state.guardianChecking = true;
  render();
  try {
    if (window.museon && window.museon.runGuardianCheck) {
      const result = await window.museon.runGuardianCheck();
      if (result && !result.error) {
        // 巡檢完成後重新載入狀態
        state.guardianStatus = await window.museon.getGuardianStatus();
      } else {
        state.guardianStatus = result;
      }
    }
  } catch (err) {
    console.error('[MUSEON] runGuardianCheck error:', err);
    state.guardianStatus = { error: err.message };
  }
  state.guardianChecking = false;
  render();
}

// ═══════════════════════════════════════
// 工具庫 Tab
// ═══════════════════════════════════════

async function loadToolsState() {
  if (state.toolsLoading) return;
  state.toolsLoading = true;
  render();
  try {
    const [toolsData, statusData, discData] = await Promise.all([
      window.museon.getToolsList(),
      window.museon.getToolsStatus(),
      window.museon.getToolsDiscoveries(),
    ]);
    state.toolsList = toolsData;
    state.toolsStatus = statusData;
    state.toolsDiscoveries = discData;
  } catch (err) {
    console.error('[MUSEON] loadToolsState error:', err);
  }
  state.toolsLoading = false;
  render();
}

async function toggleToolHandler(name, currentEnabled) {
  try {
    await window.museon.toggleTool(name, !currentEnabled);
    await loadToolsState();
  } catch (err) {
    console.error('[MUSEON] toggleTool error:', err);
  }
}

async function checkDifyStatus() {
  try {
    const resp = await fetch('http://127.0.0.1:8765/api/tools/dify/status');
    state.difyStatus = await resp.json();
    const toolsResp = await fetch('http://127.0.0.1:8765/api/tools/dify/tools');
    const toolsData = await toolsResp.json();
    state.difyToolCount = toolsData.count || 4;
  } catch (err) {
    state.difyStatus = { healthy: false, configured: false, error: err.message };
  }
  render();
}

async function runToolsHealthCheck() {
  state.toolsHealthChecking = true;
  render();
  try {
    await window.museon.runToolsHealth();
    await loadToolsState();
  } catch (err) {
    console.error('[MUSEON] runToolsHealth error:', err);
  }
  state.toolsHealthChecking = false;
  render();
}

async function installToolHandler(name) {
  // 開始安裝
  state.toolInstalling[name] = { status: 'installing', progress: 0, message: '準備安裝...' };
  render();

  try {
    await window.museon.installTool(name);
  } catch (err) {
    console.error('[MUSEON] installTool error:', err);
    state.toolInstalling[name] = { status: 'failed', progress: 0, message: '啟動安裝失敗' };
    render();
    return;
  }

  // 輪詢進度
  const poller = setInterval(async () => {
    try {
      const prog = await window.museon.getInstallProgress(name);
      state.toolInstalling[name] = prog;
      render();
      if (prog.status === 'installed' || prog.status === 'failed') {
        clearInterval(poller);
        delete state.toolInstallPollers[name];
        // 刷新工具列表
        setTimeout(() => loadToolsState(), 500);
      }
    } catch (err) {
      // ignore polling errors
    }
  }, 1500);
  state.toolInstallPollers[name] = poller;
}

function renderTools() {
  const status = state.toolsStatus || {};
  const tools = (state.toolsList && state.toolsList.tools) || [];
  const disc = state.toolsDiscoveries || {};

  if (state.toolsLoading && !state.toolsList) {
    return h('div', { className: 'tab-empty', style: { padding: '40px', textAlign: 'center' } },
      h('div', { style: { fontSize: '48px', marginBottom: '16px' } }, '🛠️'),
      h('p', { style: { color: '#9a8b70' } }, '載入工具庫...')
    );
  }

  // Lifecycle badges
  const installBadge = { docker: '🐳', native: '💻', pip: '📦' };

  return h('div', { className: 'tools-tab' },
    // ── 標題 ──
    h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' } },
      h('h2', { style: { color: '#e8dcc6', margin: 0 } }, '🛠️ 工具兵器庫'),
      h('button', {
        className: 'btn-secondary',
        style: { padding: '8px 16px', background: '#1a2340', border: '1px solid #222d4a', borderRadius: '8px', color: '#c9a96e', cursor: 'pointer', fontSize: '0.85rem' },
        onClick: () => runToolsHealthCheck(),
        disabled: state.toolsHealthChecking,
      }, state.toolsHealthChecking ? '檢查中...' : '🔍 健康檢查'),
    ),

    // ── 彙總卡片 ──
    h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '24px' } },
      renderToolSummaryCard('🛠️', '工具總數', `${status.total || 7}`),
      renderToolSummaryCard('✅', '已安裝', `${status.installed || 0}/${status.total || 7}`),
      renderToolSummaryCard('🟢', '已啟用', `${status.enabled || 0}`),
      renderToolSummaryCard('💚', '健康', `${status.healthy || 0}`),
    ),

    // ── Dify 工作流引擎狀態 ──
    h('div', { style: { background: '#0d1525', border: '1px solid #222d4a', borderRadius: '12px', padding: '16px', marginBottom: '20px' } },
      h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' } },
        h('h3', { style: { color: '#c9a96e', margin: 0, fontSize: '1rem' } }, '🔄 Dify 工作流引擎'),
        h('button', {
          style: { padding: '4px 10px', background: 'transparent', border: '1px solid #222d4a', borderRadius: '6px', color: '#9a8b70', cursor: 'pointer', fontSize: '0.75rem' },
          onClick: () => checkDifyStatus(),
        }, '檢查連線'),
      ),
      h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' } },
        h('div', { style: { background: 'rgba(201,169,110,0.05)', padding: '10px', borderRadius: '8px', textAlign: 'center' } },
          h('div', { style: { fontSize: '1.2rem', marginBottom: '4px' } }, state.difyStatus?.healthy ? '🟢' : '🔴'),
          h('div', { style: { color: '#9a8b70', fontSize: '0.75rem' } }, state.difyStatus?.healthy ? '已連線' : '未連線'),
        ),
        h('div', { style: { background: 'rgba(201,169,110,0.05)', padding: '10px', borderRadius: '8px', textAlign: 'center' } },
          h('div', { style: { fontSize: '1.2rem', marginBottom: '4px' } }, '🛠️'),
          h('div', { style: { color: '#9a8b70', fontSize: '0.75rem' } }, `${state.difyToolCount || 4} 工具`),
        ),
        h('div', { style: { background: 'rgba(201,169,110,0.05)', padding: '10px', borderRadius: '8px', textAlign: 'center' } },
          h('div', { style: { fontSize: '1.2rem', marginBottom: '4px' } }, state.difyStatus?.configured ? '⚙️' : '⚠️'),
          h('div', { style: { color: '#9a8b70', fontSize: '0.75rem' } }, state.difyStatus?.configured ? '已設定' : '未設定 API Key'),
        ),
      ),
      h('div', { style: { marginTop: '8px', fontSize: '0.72rem', color: '#6b5f4a' } },
        `Base URL: ${state.difyStatus?.base_url || 'http://localhost:5001'}`
      ),
    ),

    // ── RAM 用量 ──
    status.total_ram_mb > 0
      ? h('div', { style: { background: '#0d1525', border: '1px solid #222d4a', borderRadius: '12px', padding: '12px 16px', marginBottom: '20px', fontSize: '0.85rem', color: '#9a8b70' } },
          `💾 啟用工具 RAM 用量: ${status.total_ram_mb}MB / 32768MB (${Math.round((status.total_ram_mb / 32768) * 100)}%)`,
          h('span', { style: { marginLeft: '12px', color: '#6b5f4a' } },
            `Docker: ${status.docker_count || 0} | 原生: ${status.native_count || 0}`
          )
        )
      : null,

    // ── 工具列表（按成本分類）──
    ...renderToolsByTier(tools, installBadge),

    // ── 自動發現區 ──
    h('div', { style: { marginTop: '24px', background: '#0d1525', border: '1px solid #222d4a', borderRadius: '12px', padding: '16px' } },
      h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' } },
        h('h3', { style: { color: '#c9a96e', margin: 0, fontSize: '1rem' } }, '📡 自動發現'),
        h('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' } },
          disc.timestamp
            ? h('span', { style: { color: '#6b5f4a', fontSize: '0.75rem' } },
                `掃描: ${disc.timestamp.slice(0, 16).replace('T', ' ')}`)
            : h('span', { style: { color: '#6b5f4a', fontSize: '0.75rem' } }, '尚未掃描'),
          disc.found > 0
            ? h('span', { style: { color: '#9a8b70', fontSize: '0.7rem', padding: '2px 6px', background: 'rgba(201,169,110,0.1)', borderRadius: '4px' } },
                `${disc.found} 筆候選`)
            : null,
        ),
      ),
      disc.recommended && disc.recommended.length > 0
        ? h('div', { style: { display: 'flex', flexDirection: 'column', gap: '6px' } },
            ...disc.recommended.map((r, idx) => {
              const isExpanded = state.discoveryExpanded === idx;
              const scoreColor = r.score >= 7 ? '#10b981' : r.score >= 5 ? '#f59e0b' : '#6b5f4a';
              return h('div', {
                style: {
                  background: isExpanded ? '#111b2e' : '#0f1829',
                  border: `1px solid ${isExpanded ? '#222d4a' : 'transparent'}`,
                  borderRadius: '8px', overflow: 'hidden',
                  transition: 'all 0.2s ease',
                },
              },
                // 主列：可點擊展開
                h('div', {
                  style: {
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '8px 12px', cursor: 'pointer',
                  },
                  onClick: () => { state.discoveryExpanded = isExpanded ? null : idx; render(); },
                },
                  h('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: 0 } },
                    h('span', { style: { fontSize: '0.6875rem', color: '#6b5f4a' } }, isExpanded ? '▾' : '▸'),
                    h('span', { style: { color: '#e8dcc6', fontSize: '0.85rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } },
                      r.title || '未知工具'),
                  ),
                  h('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', flexShrink: 0 } },
                    h('span', { style: { color: scoreColor, fontSize: '0.8rem', fontWeight: '700' } }, `${r.score || 0}/10`),
                    r.url && r.url.includes('github.com')
                      ? h('span', { style: { fontSize: '0.7rem', color: '#6b5f4a', padding: '1px 4px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px' } }, '🐙')
                      : null,
                  )
                ),
                // 展開區：詳細資訊 + 操作按鈕
                isExpanded
                  ? h('div', { style: { padding: '0 12px 10px', borderTop: '1px solid rgba(255,255,255,0.05)' } },
                      // 描述（如有）
                      r.content
                        ? h('p', { style: { color: '#9a8b70', fontSize: '0.8rem', margin: '8px 0', lineHeight: '1.4' } },
                            r.content.length > 200 ? r.content.slice(0, 200) + '...' : r.content)
                        : null,
                      // 評分明細
                      h('div', { style: { display: 'flex', gap: '6px', flexWrap: 'wrap', margin: '6px 0' } },
                        h('span', { style: { fontSize: '0.7rem', color: '#6b5f4a', padding: '2px 6px', background: 'rgba(255,255,255,0.04)', borderRadius: '4px' } },
                          `評分 ${r.score}/10`),
                        r.url && r.url.includes('github.com')
                          ? h('span', { style: { fontSize: '0.7rem', color: '#6b5f4a', padding: '2px 6px', background: 'rgba(255,255,255,0.04)', borderRadius: '4px' } }, 'GitHub')
                          : null,
                      ),
                      // 操作按鈕
                      h('div', { style: { display: 'flex', gap: '8px', marginTop: '8px' } },
                        r.url
                          ? h('button', {
                              style: {
                                padding: '5px 12px', fontSize: '0.8rem', cursor: 'pointer',
                                background: 'rgba(201,169,110,0.15)', color: '#c9a96e',
                                border: '1px solid rgba(201,169,110,0.3)', borderRadius: '6px',
                              },
                              onClick: (e) => { e.stopPropagation(); window.museon && window.museon.openExternal ? window.museon.openExternal(r.url) : window.open(r.url); },
                            }, '🔗 查看專案')
                          : null,
                        h('button', {
                          style: {
                            padding: '5px 12px', fontSize: '0.8rem', cursor: 'pointer',
                            background: 'rgba(16,185,129,0.15)', color: '#10b981',
                            border: '1px solid rgba(16,185,129,0.3)', borderRadius: '6px',
                          },
                          onClick: async (e) => {
                            e.stopPropagation();
                            const btn = e.currentTarget;
                            btn.textContent = '⏳ 送出中...';
                            btn.disabled = true;
                            try {
                              const dseMsg = `/dse ${r.title}\n${r.url || ''}`;
                              const resp = await fetch('http://127.0.0.1:8765/api/telegram/inject', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ text: dseMsg }),
                              });
                              if (resp.ok) {
                                btn.textContent = '✅ 已送出';
                              } else {
                                // fallback: 複製到剪貼簿
                                try { await navigator.clipboard.writeText(dseMsg); } catch {}
                                btn.textContent = '📋 已複製';
                                btn.style.color = '#f59e0b';
                              }
                            } catch {
                              try { await navigator.clipboard.writeText(`/dse ${r.title}\n${r.url || ''}`); } catch {}
                              btn.textContent = '📋 已複製';
                              btn.style.color = '#f59e0b';
                            }
                            setTimeout(() => { btn.textContent = '🔬 DSE 研究'; btn.disabled = false; btn.style.color = '#10b981'; }, 3000);
                          },
                        }, '🔬 DSE 研究'),
                      ),
                    )
                  : null
              );
            })
          )
        : h('p', { style: { color: '#6b5f4a', fontSize: '0.85rem', margin: '8px 0 0 0' } },
            '每天凌晨 5:00 自動搜尋新的免費 AI 工具'
          ),
    ),

    // ── MCP 外部工具摘要 ──
    (() => {
      const mcpCat = state.mcpCatalog || [];
      const connectedMcp = mcpCat.filter(s => s.status === 'connected');
      const mcpToolCount = connectedMcp.reduce((sum, s) => sum + (s.tools_count || 0), 0);
      return h('div', { style: { marginTop: '24px', background: '#0d1525', border: '1px solid #222d4a', borderRadius: '12px', padding: '16px' } },
        h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' } },
          h('div', null,
            h('h3', { style: { color: '#c9a96e', margin: '0 0 4px 0', fontSize: '1rem' } }, '🔌 MCP 外部工具'),
            h('p', { style: { color: '#6b5f4a', fontSize: '0.8rem', margin: 0 } },
              connectedMcp.length > 0
                ? `${connectedMcp.length} 個已連線伺服器，共 ${mcpToolCount} 個工具`
                : '尚未連線任何 MCP 伺服器'
            )
          ),
          h('button', {
            className: 'btn-secondary',
            style: { padding: '6px 14px', background: '#1a2340', border: '1px solid #222d4a', borderRadius: '8px', color: '#c9a96e', cursor: 'pointer', fontSize: '0.8rem' },
            onClick: () => { state.activeTab = 'settings'; render(); },
          }, '前往設定 →')
        ),
        connectedMcp.length > 0
          ? h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '10px' } },
              ...connectedMcp.map(s =>
                h('span', { style: {
                  padding: '3px 8px', background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)',
                  borderRadius: '4px', fontSize: '0.75rem', color: '#10b981'
                } }, `${s.icon || '🔌'} ${s.display_name} (${s.tools_count || 0})`)
              )
            )
          : null
      );
    })(),

    // ── 暫緩安裝提醒 ──
    h('div', { style: { marginTop: '16px', padding: '12px', background: '#1a1a0d', border: '1px solid #3a3a1a', borderRadius: '8px', fontSize: '0.8rem', color: '#9a8b70' } },
      '⏸️ ',
      h('strong', {}, '暫緩安裝: '),
      'n8n（CVSS 10.0 漏洞修補中）| Dify（觀察中，未來可自主安裝）',
    ),
  );
}

function renderToolsByTier(tools, installBadge) {
  const TIER_META = {
    cpu:  { label: '🖥️ 佔用 CPU / RAM', color: '#f59e0b', desc: '本地 Docker 容器，佔用系統運算資源' },
    free: { label: '🆓 免費輕量',       color: '#10b981', desc: '無常駐服務，不佔資源，免費使用' },
    paid: { label: '💰 GPU / Token 付費', color: '#ef4444', desc: '使用雲端 API，依用量計費' },
  };
  const tierOrder = ['cpu', 'free', 'paid'];
  const grouped = {};
  for (const t of tools) {
    const tier = t.cost_tier || 'cpu';
    if (!grouped[tier]) grouped[tier] = [];
    grouped[tier].push(t);
  }
  const elements = [];
  for (const tier of tierOrder) {
    const items = grouped[tier];
    if (!items || items.length === 0) continue;
    const meta = TIER_META[tier] || TIER_META.cpu;
    elements.push(
      h('div', { style: { marginBottom: '16px' } },
        h('div', { style: { display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' } },
          h('span', { style: { fontSize: '0.9rem', fontWeight: '700', color: meta.color } }, meta.label),
          h('span', { style: { fontSize: '0.7rem', color: '#6b5f4a' } }, `(${items.length})`)
        ),
        h('div', { style: { fontSize: '0.75rem', color: '#6b5f4a', marginBottom: '8px', paddingLeft: '4px' } }, meta.desc),
        h('div', { style: { display: 'flex', flexDirection: 'column', gap: '8px' } },
          ...items.map(tool => renderToolCard(tool, installBadge))
        )
      )
    );
  }
  return elements;
}

function renderToolSummaryCard(emoji, label, value) {
  return h('div', { style: { background: '#0d1525', border: '1px solid #222d4a', borderRadius: '12px', padding: '14px', textAlign: 'center' } },
    h('div', { style: { fontSize: '1.5rem', marginBottom: '4px' } }, emoji),
    h('div', { style: { color: '#e8dcc6', fontSize: '1.2rem', fontWeight: '700' } }, value),
    h('div', { style: { color: '#6b5f4a', fontSize: '0.75rem', marginTop: '2px' } }, label),
  );
}

function renderToolCard(tool, installBadge) {
  const isEnabled = tool.enabled;
  const isInstalled = tool.installed;
  const isHealthy = tool.healthy;
  const installState = state.toolInstalling[tool.name];
  const isToolInstalling = installState && installState.status === 'installing';
  const isToolFailed = installState && installState.status === 'failed';

  const statusDot = isHealthy ? '🟢' : (isEnabled ? '🟡' : '⚪');
  const statusText = isHealthy ? '運行中' : (isEnabled ? '啟動中' : (isInstalled ? '已停止' : '未安裝'));
  const toggleLabel = isEnabled ? '開' : '關';

  return h('div', { style: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    background: '#0d1525', border: `1px solid ${isToolInstalling ? '#c9a96e' : isToolFailed ? '#ef4444' : '#222d4a'}`,
    borderRadius: '12px', padding: '14px 18px', transition: 'border-color 0.2s',
  }},
    // 左側：emoji + 名稱 + 說明
    h('div', { style: { flex: 1, minWidth: 0 } },
      h('div', { style: { display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' } },
        h('span', { style: { fontSize: '1.3rem' } }, tool.emoji),
        h('span', { style: { color: '#e8dcc6', fontWeight: '700', fontSize: '0.95rem' } }, tool.display_name),
        h('span', { style: { color: '#6b5f4a', fontSize: '0.75rem', padding: '1px 6px', background: '#111b2e', borderRadius: '4px' } },
          `${installBadge[tool.install_type] || ''} ${tool.install_type}`
        ),
        statusDot !== '⚪'
          ? h('span', { style: { color: '#6b5f4a', fontSize: '0.75rem' } }, `${statusDot} ${statusText}`)
          : null,
      ),
      // 安裝中顯示進度條
      isToolInstalling
        ? h('div', { style: { marginTop: '4px' } },
            h('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' } },
              h('div', { style: { flex: 1, height: '6px', background: '#1a2340', borderRadius: '3px', overflow: 'hidden' } },
                h('div', { style: {
                  width: `${installState.progress || 0}%`, height: '100%',
                  background: 'linear-gradient(90deg, #c9a96e, #e8dcc6)',
                  borderRadius: '3px', transition: 'width 0.3s',
                }})
              ),
              h('span', { style: { color: '#c9a96e', fontSize: '0.75rem', minWidth: '36px' } }, `${installState.progress || 0}%`),
            ),
            h('div', { style: { color: '#9a8b70', fontSize: '0.7rem', marginTop: '2px' } }, installState.message || '安裝中...'),
          )
        : isToolFailed
          ? h('div', { style: { color: '#ef4444', fontSize: '0.8rem', marginTop: '2px' } }, `❌ ${installState.message || '安裝失敗'}`)
          : h('div', { style: { color: '#9a8b70', fontSize: '0.8rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } },
              tool.description
            ),
      tool.port > 0
        ? h('span', { style: { color: '#6b5f4a', fontSize: '0.7rem' } }, `RAM: ${tool.ram_mb}MB | Port: ${tool.port}`)
        : h('span', { style: { color: '#6b5f4a', fontSize: '0.7rem' } }, `RAM: ${tool.ram_mb}MB`),
    ),

    // 右側：on/off toggle 或安裝按鈕（必要工具不可關閉）
    isInstalled
      ? tool.required
        ? h('span', {
            style: {
              marginLeft: '16px', padding: '6px 16px', borderRadius: '20px',
              background: '#1a3a2a', color: '#10b981',
              fontWeight: '700', fontSize: '0.8rem', minWidth: '72px', textAlign: 'center',
              display: 'inline-block',
            },
          }, '🔒 必要')
        : h('button', {
            style: {
              marginLeft: '16px', padding: '6px 16px', borderRadius: '20px', border: 'none',
              fontWeight: '700', fontSize: '0.8rem', cursor: 'pointer', minWidth: '60px',
              background: isEnabled ? '#10b981' : '#333', color: isEnabled ? '#fff' : '#999',
            },
            onClick: () => toggleToolHandler(tool.name, isEnabled),
          }, toggleLabel)
      : isToolInstalling
        ? h('span', { style: { color: '#c9a96e', fontSize: '0.8rem', marginLeft: '16px', fontWeight: '700' } }, '安裝中...')
        : h('button', {
            style: {
              marginLeft: '16px', padding: '6px 16px', borderRadius: '20px',
              border: '1px solid #c9a96e', background: 'transparent',
              color: '#c9a96e', fontWeight: '700', fontSize: '0.8rem',
              cursor: 'pointer', minWidth: '72px',
            },
            onClick: () => installToolHandler(tool.name),
          }, '📥 安裝'),
  );
}

function renderDoctor() {
  const report = state.doctorReport;

  if (state.doctorLoading) {
    return h('div', { className: 'doctor-loading', style: { padding: '40px', textAlign: 'center' } },
      h('div', { style: { fontSize: '48px', marginBottom: '16px' } }, '🩺'),
      h('p', { style: { color: '#9a8b70' } }, '正在進行系統健檢...')
    );
  }

  if (!report) {
    return h('div', { style: { padding: '40px', textAlign: 'center' } },
      h('div', { style: { fontSize: '48px', marginBottom: '16px' } }, '🩺'),
      h('p', { style: { color: '#9a8b70', marginBottom: '16px' } }, '尚未執行健檢'),
      h('button', {
        className: 'btn-primary',
        onClick: loadDoctorReport,
        style: { padding: '12px 24px', fontSize: '16px', cursor: 'pointer',
          background: '#c9a96e', color: '#fff', border: 'none', borderRadius: '8px' }
      }, '🔍 開始健檢')
    );
  }

  if (report.error) {
    return h('div', { style: { padding: '40px', textAlign: 'center', color: '#ef4444' } },
      h('p', null, '健檢失敗: ' + report.error),
      h('button', { onClick: loadDoctorReport, style: { marginTop: '12px', padding: '8px 16px',
        cursor: 'pointer', background: '#c9a96e', color: '#fff', border: 'none', borderRadius: '8px' }
      }, '重試')
    );
  }

  // 計算統計
  const summary = report.summary || {};
  const overallColor = { ok: '#22c55e', warning: '#f59e0b', critical: '#ef4444', unknown: '#9a8b70' }[report.overall] || '#9a8b70';
  const overallEmoji = { ok: '✅', warning: '⚠️', critical: '🚨', unknown: '❓' }[report.overall] || '❓';

  return h('div', { className: 'doctor-page' },
    // 頂部概要
    h('div', { className: 'doctor-summary' },
      h('div', { style: { display: 'flex', alignItems: 'center', gap: '1rem' } },
        h('span', { style: { fontSize: '2rem' } }, overallEmoji),
        h('div', null,
          h('div', { style: { fontSize: '1.125rem', fontWeight: '700', color: overallColor } },
            report.overall === 'ok' ? '系統健康' : report.overall === 'warning' ? '需要注意' : '需要修復'
          ),
          h('div', { style: { fontSize: '0.75rem', color: '#6b5f4a', marginTop: '0.125rem' } },
            `${summary.ok || 0} 正常 · ${summary.warning || 0} 警告 · ${summary.critical || 0} 嚴重`)
        )
      ),
      h('div', { style: { display: 'flex', gap: '0.5rem', flexShrink: 0 } },
        h('button', {
          className: 'wizard-btn-secondary',
          onClick: loadDoctorReport,
          disabled: state.doctorLoading,
          style: { fontSize: '0.8125rem', padding: '0.4rem 0.875rem' }
        }, '🔄 重新檢查'),
        h('button', {
          className: 'wizard-btn-primary',
          onClick: () => {
            const repairables = (report.checks || []).filter(c => c.repairable && c.status !== 'ok');
            if (repairables.length === 0) { alert('無需修復'); return; }
            if (confirm(`自動修復 ${repairables.length} 個問題？`)) {
              repairables.forEach(c => handleDoctorRepair(c.repair_action));
            }
          },
          style: { fontSize: '0.8125rem', padding: '0.4rem 0.875rem' }
        }, '🔧 一鍵修復')
      )
    ),

    // 時間戳
    h('div', { style: { padding: '0.5rem 0', fontSize: '0.6875rem', color: '#475569' } },
      `上次檢查: ${report.timestamp ? new Date(report.timestamp).toLocaleString('zh-TW') : '—'}`
    ),

    // 檢查項目列表
    h('div', { className: 'doctor-checks' },
      ...(report.checks || []).map(check => {
        const statusIcon = { ok: '✅', warning: '⚠️', critical: '🚨', unknown: '❓' }[check.status] || '❓';
        const statusColor = { ok: '#22c55e', warning: '#f59e0b', critical: '#ef4444', unknown: '#9a8b70' }[check.status] || '#9a8b70';
        const isRepairing = state.doctorRepairing[check.repair_action];

        return h('div', {
          className: 'doctor-check-item',
          style: {
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '0.75rem 1rem',
            background: 'rgba(255,255,255,0.02)', borderRadius: '0.625rem',
            border: `1px solid ${check.status === 'ok' ? 'rgba(255,255,255,0.04)' : statusColor + '33'}`
          }
        },
          h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.75rem', flex: '1', minWidth: 0 } },
            h('span', { style: { fontSize: '1.125rem', flexShrink: 0 } }, statusIcon),
            h('div', { style: { minWidth: 0 } },
              h('div', { style: { fontWeight: '600', fontSize: '0.8125rem', color: '#e8dcc6' } }, check.name),
              h('div', { style: { fontSize: '0.6875rem', color: '#9a8b70', marginTop: '0.1rem', wordBreak: 'break-word' } }, check.message)
            )
          ),
          check.repairable && check.status !== 'ok'
            ? h('button', {
                onClick: () => handleDoctorRepair(check.repair_action),
                disabled: isRepairing,
                style: {
                  padding: '0.3rem 0.75rem', fontSize: '0.6875rem', cursor: 'pointer',
                  background: isRepairing ? '#475569' : '#f59e0b',
                  color: '#000', border: 'none', borderRadius: '0.375rem',
                  whiteSpace: 'nowrap', flexShrink: 0, fontWeight: 600
                }
              }, isRepairing ? '修復中...' : '🔧 修復')
            : null
        );
      })
    ),

    // ─── Nightly 凌晨整合管線 ───
    renderNightlySection(),

    // ─── Guardian 守護者狀態 ───
    renderGuardianSection()
  );
}

// ─── Guardian 守護者區塊 ───
function renderGuardianSection() {
  const gs = state.guardianStatus;

  return h('div', { style: { marginTop: '1.5rem' } },
    h('div', { className: 'doctor-summary', style: { marginBottom: '0.75rem' } },
      h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.75rem' } },
        h('span', { style: { fontSize: '1.5rem' } }, '🛡️'),
        h('div', null,
          h('div', { style: { fontSize: '1rem', fontWeight: '700', color: '#c9a96e' } }, '守護者'),
          h('div', { style: { fontSize: '0.6875rem', color: '#6b5f4a' } },
            gs && gs.last_l1
              ? `上次 L1: ${new Date(gs.last_l1).toLocaleString('zh-TW')}`
              : '尚未巡檢')
        )
      ),
      h('div', { style: { display: 'flex', gap: '0.5rem', flexShrink: 0 } },
        h('button', {
          className: 'wizard-btn-secondary',
          onClick: loadGuardianStatus,
          style: { fontSize: '0.75rem', padding: '0.3rem 0.75rem' }
        }, '🔄 查詢狀態'),
        h('button', {
          className: 'wizard-btn-primary',
          onClick: runGuardianCheck,
          disabled: state.guardianChecking,
          style: { fontSize: '0.75rem', padding: '0.3rem 0.75rem' }
        }, state.guardianChecking ? '巡檢中...' : '🛡️ 手動巡檢')
      )
    ),

    // Guardian 結果概覽
    gs && !gs.error ? h('div', { style: { display: 'flex', flexDirection: 'column', gap: '0.5rem' } },
      // L1 / L2 / L3 摘要
      gs.l1_summary ? renderGuardianLayer('L1 基礎設施', gs.l1_summary, gs.last_l1) : null,
      gs.l2_summary ? renderGuardianLayer('L2 資料完整', gs.l2_summary, gs.last_l2) : null,
      gs.l3_summary ? renderGuardianLayer('L3 神經束', gs.l3_summary, gs.last_l3) : null,

      // 未解決問題
      gs.unresolved_count > 0
        ? h('div', { style: {
            padding: '0.625rem 1rem', background: 'rgba(239, 68, 68, 0.06)',
            borderRadius: '0.5rem', border: '1px solid rgba(239, 68, 68, 0.15)',
            fontSize: '0.8125rem', color: '#fca5a5'
          } },
          `⚠️ ${gs.unresolved_count} 個問題需人工介入`,
          ...(gs.unresolved || []).map(u =>
            h('div', { style: { fontSize: '0.6875rem', color: '#9a8b70', marginTop: '0.25rem' } },
              `· [${u.layer}] ${u.check}: ${u.details}`)
          )
        ) : null,

      // 母體狀態（預留）
      h('div', { style: {
        padding: '0.5rem 1rem', background: 'rgba(255,255,255,0.02)',
        borderRadius: '0.5rem', fontSize: '0.6875rem', color: '#475569',
        display: 'flex', alignItems: 'center', gap: '0.5rem'
      } },
        h('span', null, '🔴'),
        h('span', null, '母體回報：未連線（預留功能）'),
        gs.mothership_queue_size > 0
          ? h('span', { style: { color: '#f59e0b' } },
              ` · ${gs.mothership_queue_size} 筆待回報`)
          : null
      ),

      // 最近修復紀錄
      gs.recent_repairs && gs.recent_repairs.length > 0
        ? h('div', { className: 'card', style: { marginTop: '0.5rem' } },
            h('div', { className: 'card-title' }, '📋 最近修復紀錄'),
            h('div', { style: { display: 'flex', flexDirection: 'column', gap: '0.25rem' } },
              ...gs.recent_repairs.slice(0, 10).map(r =>
                h('div', { style: {
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '0.375rem 0.5rem', fontSize: '0.6875rem',
                  background: 'rgba(255,255,255,0.02)', borderRadius: '0.375rem'
                } },
                  h('span', { style: { color: '#9a8b70' } },
                    `[${r.layer}] ${r.check}`),
                  h('span', { style: { color: r.status === 'repaired' ? '#10b981' : '#ef4444' } },
                    r.status === 'repaired' ? '✅ 已修復' : '❌ 失敗'),
                  h('span', { style: { color: '#475569', minWidth: '80px', textAlign: 'right' } },
                    r.timestamp ? formatAgentTime(r.timestamp) : '')
                )
              )
            )
          ) : null
    ) : null
  );
}

function renderGuardianLayer(label, summary, lastTime) {
  const total = (summary.ok || 0) + (summary.repaired || 0) + (summary.failed || 0) + (summary.skipped || 0);
  const allOk = (summary.failed || 0) === 0 && (summary.repaired || 0) === 0;
  const icon = allOk ? '✅' : (summary.failed || 0) > 0 ? '🚨' : '⚠️';
  const color = allOk ? '#10b981' : (summary.failed || 0) > 0 ? '#ef4444' : '#f59e0b';

  return h('div', { style: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0.625rem 1rem', background: 'rgba(255,255,255,0.02)',
    borderRadius: '0.5rem', border: `1px solid ${color}22`,
  } },
    h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.5rem' } },
      h('span', null, icon),
      h('span', { style: { fontSize: '0.8125rem', fontWeight: '600', color: '#e8dcc6' } }, label)
    ),
    h('div', { style: { fontSize: '0.6875rem', color: '#9a8b70' } },
      `${summary.ok || 0} 正常`,
      (summary.repaired || 0) > 0
        ? h('span', { style: { color: '#f59e0b' } }, ` · ${summary.repaired} 已修復`) : null,
      (summary.failed || 0) > 0
        ? h('span', { style: { color: '#ef4444' } }, ` · ${summary.failed} 失敗`) : null
    )
  );
}

// ═══════════════════════════════════════
// Tab 6: ⚙️ 設定 (Settings)
// ═══════════════════════════════════════
function renderSettings() {
  return h('div', null,
    // Gateway Hero Card
    renderGatewayHero(),
    // Token Budget 視覺化
    renderTokenBudget(),
    // Telegram status section
    renderTelegramStatus(),
    // ── Token 節省報告（含模型分流明細）──
    renderSavingsBreakdown(),
    // ── MCP 連接器管理 ──
    (() => { try { return renderMCPPanel(); } catch(e) { console.error('[MCP Panel]', e); return null; } })(),
    // ── 可收合設定區 ──
    h('div', { className: 'settings-section settings-collapsible' },
      h('h2', {
        onClick: () => { state.settingsGeneralCollapsed = !state.settingsGeneralCollapsed; render(); },
        style: { cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', userSelect: 'none' }
      },
        h('span', null, '⚙️ 一般'),
        h('span', { style: { fontSize: '0.6875rem', color: '#6b5f4a', transition: 'transform 0.2s' } },
          state.settingsGeneralCollapsed ? '▸' : '▾')
      ),
      !state.settingsGeneralCollapsed
        ? renderSettingToggle('開機自動啟動', 'MUSEON 控制台開機自動啟動', 'autolaunch')
        : null,
    ),
    h('div', { className: 'settings-section settings-collapsible' },
      h('h2', {
        onClick: () => { state.settingsApiKeyCollapsed = !state.settingsApiKeyCollapsed; render(); },
        style: { cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', userSelect: 'none' }
      },
        h('span', null, '🔑 API 金鑰'),
        h('span', { style: { fontSize: '0.6875rem', color: '#6b5f4a', transition: 'transform 0.2s' } },
          state.settingsApiKeyCollapsed ? '▸' : '▾')
      ),
      !state.settingsApiKeyCollapsed
        ? h('div', { className: 'setting-item' },
            h('div', { className: 'setting-label' },
              h('div', { className: 'setting-title' }, '重新執行設定精靈'),
              h('div', { className: 'setting-description' }, '重新設定 API 金鑰和 Bot 令牌')
            ),
            h('button', {
              className: 'wizard-btn-primary',
              style: { padding: '0.5rem 1rem', fontSize: '0.875rem' },
              onClick: () => {
                state.showSetupWizard = true;
                state.wizardStep = 0;
                render();
              }
            }, '開始設定')
          )
        : null,
    )
  );
}

// ─── Gateway Hero Card ───
function renderGatewayHero() {
  const gi = state.gatewayInfo;
  const online = gi ? gi.online : state.gatewayOnline;
  const pid = gi ? gi.pid : null;
  const port = gi ? gi.port : 8765;
  const uptimeMs = gi ? gi.uptime_ms : 0;
  const uptimeStr = formatUptime(uptimeMs);

  return h('div', { className: 'gateway-hero' },
    // Left: Status badge + title
    h('div', { className: 'gateway-hero-left' },
      h('div', { className: `gateway-hero-badge ${online ? 'online' : 'offline'}` },
        h('div', { className: `status-dot ${online ? '' : 'offline'}`, style: { width: '12px', height: '12px' } }),
        h('span', null, online ? '上線中' : '離線中')
      ),
      h('div', { className: 'gateway-hero-title' }, '閘道器'),
      h('div', { className: 'gateway-hero-subtitle' }, `FastAPI · 連接埠 ${port}`)
    ),
    // Center: Stats
    h('div', { className: 'gateway-hero-stats' },
      h('div', { className: 'gateway-hero-stat' },
        h('div', { className: 'gateway-hero-stat-value' }, pid ? String(pid) : '—'),
        h('div', { className: 'gateway-hero-stat-label' }, '程序 ID')
      ),
      h('div', { className: 'gateway-hero-stat' },
        h('div', { className: 'gateway-hero-stat-value' }, uptimeStr),
        h('div', { className: 'gateway-hero-stat-label' }, '運行時間')
      ),
      h('div', { className: 'gateway-hero-stat' },
        h('div', { className: 'gateway-hero-stat-value' }, String(port)),
        h('div', { className: 'gateway-hero-stat-label' }, '連接埠')
      )
    ),
    // Right: Action buttons
    h('div', { className: 'gateway-hero-actions' },
      h('button', {
        className: 'gateway-hero-btn',
        onClick: handleGatewayRepair,
        disabled: state.gatewayRepairing,
      }, state.gatewayRepairing ? '重啟中...' : '🔄 重啟'),
      h('button', {
        className: 'gateway-hero-btn secondary',
        onClick: () => { state.showGatewayPanel = !state.showGatewayPanel; render(); },
      }, '📋 日誌')
    )
  );
}

function formatUptime(ms) {
  if (!ms || ms <= 0) return '—';
  const totalSec = Math.floor(ms / 1000);
  const hours = Math.floor(totalSec / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  const seconds = totalSec % 60;
  if (hours > 0) return `${hours}時${minutes}分`;
  if (minutes > 0) return `${minutes}分${seconds}秒`;
  return `${seconds}秒`;
}

// ─── Token Budget 視覺化 ───
function renderTokenBudget() {
  const bs = state.budgetStats;
  const pct = bs ? bs.percentage : 0;
  const isWarning = bs ? bs.should_warn : false;
  const inputTokens = bs ? (bs.input_tokens || 0) : 0;
  const outputTokens = bs ? (bs.output_tokens || 0) : 0;
  const costUsd = bs ? (bs.estimated_cost_usd || 0) : 0;
  const models = bs ? (bs.models || {}) : {};
  const sonnet = models.sonnet || { input_tokens: 0, output_tokens: 0, total_tokens: 0, calls: 0, cost_usd: 0 };
  const haiku = models.haiku || { input_tokens: 0, output_tokens: 0, total_tokens: 0, calls: 0, cost_usd: 0 };

  // 幣別換算
  const USD_TO_TWD = 32.5;
  const isUsd = state.costCurrency === 'USD';
  const fmtCost = (usd) => isUsd
    ? (usd > 0 ? `$${usd.toFixed(4)}` : '$0')
    : (usd > 0 ? `NT$${(usd * USD_TO_TWD).toFixed(2)}` : 'NT$0');
  const currencyLabel = isUsd ? 'USD' : 'TWD';

  const currencyToggle = h('button', {
    onClick: () => { state.costCurrency = isUsd ? 'TWD' : 'USD'; render(); },
    style: {
      padding: '0.125rem 0.375rem', fontSize: '0.5625rem', fontWeight: '700',
      background: 'rgba(201, 169, 110, 0.15)', color: '#c9a96e',
      border: '1px solid rgba(201, 169, 110, 0.3)', borderRadius: '0.25rem',
      cursor: 'pointer', lineHeight: '1.2', whiteSpace: 'nowrap',
    }
  }, currencyLabel);

  // 預算調整 input
  const budgetInput = h('input', {
    type: 'number',
    value: bs ? bs.daily_limit : 200000,
    min: 10000,
    step: 10000,
    style: {
      width: '7rem', padding: '0.25rem 0.5rem', fontSize: '0.75rem',
      background: 'rgba(255,255,255,0.05)', color: '#e0d5c0',
      border: '1px solid rgba(201,169,110,0.3)', borderRadius: '0.25rem',
      textAlign: 'right',
    }
  });

  const budgetSaveBtn = h('button', {
    onClick: async () => {
      const newLimit = parseInt(budgetInput.value, 10);
      if (isNaN(newLimit) || newLimit < 10000) {
        alert('預算必須 ≥ 10,000');
        return;
      }
      if (window.museon && window.museon.setBudgetLimit) {
        const res = await window.museon.setBudgetLimit(newLimit);
        if (res && res.success) {
          state.budgetStats = await window.museon.getBudgetStats();
          render();
        }
      }
    },
    style: {
      padding: '0.25rem 0.5rem', fontSize: '0.6875rem', fontWeight: '600',
      background: 'rgba(201,169,110,0.2)', color: '#c9a96e',
      border: '1px solid rgba(201,169,110,0.3)', borderRadius: '0.25rem',
      cursor: 'pointer',
    }
  }, '套用');

  return h('div', { className: 'settings-section' },
    h('h2', null, '💰 用量預算'),
    h('div', { className: 'token-budget-card' },
      // ─── 百分比大字 + 進度條 ───
      h('div', { style: { textAlign: 'center', marginBottom: '0.5rem' } },
        h('div', {
          style: {
            fontSize: '2rem', fontWeight: '800', lineHeight: '1.1',
            color: isWarning ? '#ef4444' : pct > 50 ? '#f59e0b' : '#10b981',
          }
        }, bs ? `${pct.toFixed(1)}%` : '—'),
        h('div', { style: { fontSize: '0.6875rem', color: '#6b5f4a', marginTop: '0.125rem' } },
          bs ? `已使用 ${bs.used.toLocaleString()} / ${bs.daily_limit.toLocaleString()} tokens` : '讀取中...'
        )
      ),
      // Progress bar
      h('div', { className: 'progress-bar', style: { height: '8px', marginTop: '0.375rem' } },
        h('div', {
          className: `progress-fill ${isWarning ? 'warning' : ''}`,
          style: { width: `${Math.min(pct, 100)}%` }
        })
      ),
      // Warning
      isWarning
        ? h('div', { className: 'token-budget-warn' }, '⚠️ 接近每日用量上限')
        : null,
      // ─── 每日預算上限調整 ───
      h('div', { style: {
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginTop: '0.75rem', padding: '0.5rem 0.625rem',
        background: 'rgba(255,255,255,0.02)', borderRadius: '0.375rem',
        border: '1px solid rgba(255,255,255,0.05)'
      } },
        h('span', { style: { fontSize: '0.75rem', color: '#9a8b70' } }, '每日上限'),
        h('div', { style: { display: 'flex', gap: '0.375rem', alignItems: 'center' } },
          budgetInput, budgetSaveBtn
        )
      ),
      // Total breakdown row
      h('div', { className: 'token-breakdown', style: { marginTop: '0.75rem' } },
        renderTokenBreakdownItem('📥 輸入', inputTokens, '#c9a96e'),
        renderTokenBreakdownItem('📤 輸出', outputTokens, '#8b5cf6'),
        h('div', { className: 'token-breakdown-item' },
          h('div', {
            className: 'token-breakdown-value',
            style: { color: '#10b981', display: 'flex', alignItems: 'center', gap: '0.375rem', justifyContent: 'center' }
          },
            h('span', null, fmtCost(costUsd)),
            currencyToggle
          ),
          h('div', { className: 'token-breakdown-label' }, '💵 合計成本')
        )
      ),
      // ─── Per-model breakdown ───
      h('div', { style: {
        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem',
        marginTop: '0.75rem', paddingTop: '0.75rem',
        borderTop: '1px solid rgba(255,255,255,0.05)'
      } },
        renderModelUsageCard('⚡ Sonnet', sonnet, '#c9a96e', fmtCost),
        renderModelUsageCard('🍃 Haiku', haiku, '#8b5cf6', fmtCost)
      ),
      // ─── 當月累計 ───
      renderMonthlyCumulative(bs, fmtCost)
    )
  );
}

function renderMonthlyCumulative(bs, fmtCost) {
  const monthly = bs ? (bs.monthly || null) : null;
  if (!monthly || monthly.total_tokens === 0) {
    return h('div', { style: {
      marginTop: '0.75rem', paddingTop: '0.75rem',
      borderTop: '1px solid rgba(255,255,255,0.05)',
      textAlign: 'center', fontSize: '0.75rem', color: '#6b5f4a'
    } }, '📅 本月尚無累計資料');
  }

  const daysTracked = monthly.days_tracked || 0;
  const monthLabel = monthly.month || '—';
  const totalTokens = monthly.total_tokens || 0;
  const costUsd = monthly.estimated_cost_usd || 0;

  // 預測本月總花費（按日均外推）
  const today = new Date();
  const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
  const dailyAvgCost = daysTracked > 0 ? costUsd / daysTracked : 0;
  const projectedCost = dailyAvgCost * daysInMonth;

  return h('div', { style: {
    marginTop: '0.75rem', paddingTop: '0.75rem',
    borderTop: '1px solid rgba(255,255,255,0.05)'
  } },
    h('div', { style: {
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      marginBottom: '0.5rem'
    } },
      h('span', { style: { fontSize: '0.8125rem', fontWeight: '700', color: '#c9a96e' } },
        `📅 ${monthLabel} 累計`),
      h('span', { style: { fontSize: '0.625rem', color: '#6b5f4a' } },
        `已追蹤 ${daysTracked} 天`)
    ),
    h('div', { style: {
      display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.375rem'
    } },
      h('div', { style: { textAlign: 'center' } },
        h('div', { style: { fontSize: '1rem', fontWeight: '700', color: '#e0d5c0' } },
          totalTokens.toLocaleString()),
        h('div', { style: { fontSize: '0.5625rem', color: '#6b5f4a' } }, '總 tokens')
      ),
      h('div', { style: { textAlign: 'center' } },
        h('div', { style: { fontSize: '1rem', fontWeight: '700', color: '#10b981' } },
          fmtCost(costUsd)),
        h('div', { style: { fontSize: '0.5625rem', color: '#6b5f4a' } }, '已花費')
      ),
      h('div', { style: { textAlign: 'center' } },
        h('div', { style: { fontSize: '1rem', fontWeight: '700', color: '#f59e0b' } },
          fmtCost(projectedCost)),
        h('div', { style: { fontSize: '0.5625rem', color: '#6b5f4a' } }, '預估月花費')
      )
    )
  );
}

function renderModelUsageCard(label, data, color, fmtCost) {
  return h('div', { style: {
    background: 'rgba(255,255,255,0.02)', borderRadius: '0.5rem',
    padding: '0.625rem 0.75rem', border: `1px solid ${color}22`
  } },
    h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.375rem' } },
      h('span', { style: { fontSize: '0.75rem', fontWeight: '700', color } }, label),
      h('span', { style: { fontSize: '0.625rem', color: '#6b5f4a' } },
        data.calls > 0 ? `${data.calls} 次呼叫` : '—')
    ),
    h('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: '0.6875rem' } },
      h('span', { style: { color: '#9a8b70' } }, `📥 ${data.input_tokens.toLocaleString()}`),
      h('span', { style: { color: '#9a8b70' } }, `📤 ${data.output_tokens.toLocaleString()}`)
    ),
    h('div', { style: { marginTop: '0.25rem', fontSize: '0.75rem', fontWeight: '600', color: '#10b981' } },
      fmtCost(data.cost_usd))
  );
}

function renderTokenBreakdownItem(label, value, color) {
  const displayVal = typeof value === 'number' ? value.toLocaleString() : value;
  return h('div', { className: 'token-breakdown-item' },
    h('div', { className: 'token-breakdown-value', style: { color } }, displayVal),
    h('div', { className: 'token-breakdown-label' }, label)
  );
}

// ─── 路由分流統計 ───
function renderRoutingStats() {
  const rs = state.routingStats;
  if (!rs || (!rs.savings && !rs.haiku)) {
    return h('div', { className: 'settings-section' },
      h('h2', null, '🔀 模型分流'),
      h('div', { style: {
        textAlign: 'center', padding: '1.5rem', fontSize: '0.75rem', color: '#6b5f4a'
      } }, '尚無路由分流數據（互動後將自動產生）')
    );
  }

  const savings = rs.savings || {};
  const haikuCalls = savings.haiku_calls || 0;
  const totalCalls = savings.total_calls || 0;
  const haikuRatio = savings.haiku_ratio_pct || 0;
  const costSaved = savings.cost_saved_usd || 0;
  const tokensOnHaiku = savings.tokens_on_haiku || 0;

  const isUsd = state.costCurrency === 'USD';
  const USD_TO_TWD = 32.5;
  const fmtCost = (usd) => isUsd
    ? (usd > 0 ? `$${usd.toFixed(4)}` : '$0')
    : (usd > 0 ? `NT$${(usd * USD_TO_TWD).toFixed(2)}` : 'NT$0');

  // 最近的路由記錄
  const todayLog = (rs.today_log || []).slice(-8).reverse();

  return h('div', { className: 'settings-section' },
    h('h2', null, '🔀 模型分流'),
    h('div', { className: 'token-budget-card' },
      // 節省金額大字
      h('div', { style: { textAlign: 'center', marginBottom: '0.5rem' } },
        h('div', {
          style: {
            fontSize: '1.5rem', fontWeight: '800', lineHeight: '1.1',
            color: costSaved > 0 ? '#10b981' : '#6b5f4a',
          }
        }, costSaved > 0 ? `💰 ${fmtCost(costSaved)}` : '—'),
        h('div', { style: { fontSize: '0.6875rem', color: '#6b5f4a', marginTop: '0.125rem' } },
          costSaved > 0 ? '近 7 天因分流節省' : '尚未有 Haiku 分流節省')
      ),
      // 三欄數據
      h('div', { style: {
        display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.375rem',
        marginTop: '0.5rem', paddingTop: '0.5rem',
        borderTop: '1px solid rgba(255,255,255,0.05)'
      } },
        h('div', { style: { textAlign: 'center' } },
          h('div', { style: { fontSize: '1rem', fontWeight: '700', color: '#8b5cf6' } },
            `${haikuCalls}`),
          h('div', { style: { fontSize: '0.5625rem', color: '#6b5f4a' } }, '🍃 Haiku 次數')
        ),
        h('div', { style: { textAlign: 'center' } },
          h('div', { style: { fontSize: '1rem', fontWeight: '700', color: '#c9a96e' } },
            `${totalCalls}`),
          h('div', { style: { fontSize: '0.5625rem', color: '#6b5f4a' } }, '⚡ 總呼叫')
        ),
        h('div', { style: { textAlign: 'center' } },
          h('div', { style: { fontSize: '1rem', fontWeight: '700', color: haikuRatio > 20 ? '#10b981' : '#f59e0b' } },
            `${haikuRatio}%`),
          h('div', { style: { fontSize: '0.5625rem', color: '#6b5f4a' } }, '🎯 Haiku 比例')
        )
      ),
      // Haiku token 量
      tokensOnHaiku > 0
        ? h('div', { style: {
            marginTop: '0.5rem', padding: '0.375rem 0.625rem',
            background: 'rgba(139,92,246,0.08)', borderRadius: '0.375rem',
            border: '1px solid rgba(139,92,246,0.15)',
            fontSize: '0.6875rem', color: '#9a8b70', textAlign: 'center'
          } }, `🍃 Haiku 處理了 ${tokensOnHaiku.toLocaleString()} tokens`)
        : null,
      // 即時路由記錄
      todayLog.length > 0
        ? h('div', { style: {
            marginTop: '0.75rem', paddingTop: '0.5rem',
            borderTop: '1px solid rgba(255,255,255,0.05)'
          } },
            h('div', { style: { fontSize: '0.6875rem', fontWeight: '700', color: '#c9a96e', marginBottom: '0.375rem' } },
              '📋 今日路由記錄'),
            ...todayLog.map(entry =>
              h('div', { style: {
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '0.25rem 0', fontSize: '0.625rem', color: '#9a8b70',
                borderBottom: '1px solid rgba(255,255,255,0.03)'
              } },
                h('span', null,
                  (entry.model === 'haiku' ? '🍃' : '⚡') + ' ' +
                  entry.task_type
                ),
                h('span', null, `${(entry.tokens || 0).toLocaleString()} tok`),
                h('span', { style: { color: '#6b5f4a' } },
                  entry.ts ? entry.ts.split('T')[1]?.substring(0, 8) : '')
              )
            )
          )
        : null
    )
  );
}

// ─── Token 節省報告（各策略明細 + 嵌入模型分流）───
function renderSavingsBreakdown() {
  const sb = state.savingsBreakdown;
  const isUsd = state.costCurrency === 'USD';
  const USD_TO_TWD = 32.5;
  const fmtCost = (usd) => isUsd
    ? (usd > 0 ? `$${usd.toFixed(4)}` : '$0')
    : (usd > 0 ? `NT$${(usd * USD_TO_TWD).toFixed(2)}` : 'NT$0');
  const fmtCostBig = (usd) => isUsd
    ? (usd > 0 ? `$${usd.toFixed(2)}` : '$0')
    : (usd > 0 ? `NT$${(usd * USD_TO_TWD).toFixed(0)}` : 'NT$0');
  const currencyLabel = isUsd ? 'TWD' : 'USD';

  // 還沒載入 → 精簡佔位
  if (!sb) {
    return h('div', { className: 'settings-section' },
      h('h2', null, '💎 Token 節省報告'),
      h('div', { style: {
        textAlign: 'center', padding: '1.5rem', fontSize: '0.75rem', color: '#6b5f4a'
      } }, '載入中...')
    );
  }

  const totalSaved = sb.total_saved_usd || 0;
  const totalTokensSaved = sb.total_tokens_saved || 0;
  const strategies = sb.strategies || [];

  // 路由明細（嵌入 Haiku 策略展開區）
  const rs = state.routingStats;
  const rsSavings = rs && rs.savings ? rs.savings : {};
  const haikuCalls = rsSavings.haiku_calls || 0;
  const totalCalls = rsSavings.total_calls || 0;
  const haikuRatio = rsSavings.haiku_ratio_pct || 0;
  const costSaved = rsSavings.cost_saved_usd || 0;
  const tokensOnHaiku = rsSavings.tokens_on_haiku || 0;
  const todayLog = (rs && rs.today_log || []).slice(-8).reverse();

  return h('div', { className: 'settings-section' },
    h('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' } },
      h('h2', { style: { margin: 0 } }, '💎 Token 節省報告'),
      h('button', {
        onClick: () => { state.costCurrency = isUsd ? 'TWD' : 'USD'; render(); },
        style: {
          padding: '0.125rem 0.375rem', fontSize: '0.5625rem', fontWeight: '700',
          background: 'rgba(201, 169, 110, 0.15)', color: '#c9a96e',
          border: '1px solid rgba(201, 169, 110, 0.3)', borderRadius: '0.25rem',
          cursor: 'pointer', lineHeight: '1.2', whiteSpace: 'nowrap',
        }
      }, currencyLabel)
    ),
    h('div', { className: 'token-budget-card' },
      // ── 總節省大字 ──
      h('div', { style: { textAlign: 'center', marginBottom: '0.625rem' } },
        h('div', {
          style: {
            fontSize: '1.75rem', fontWeight: '800', lineHeight: '1.1',
            color: totalSaved > 0 ? '#10b981' : '#6b5f4a',
          }
        }, totalSaved > 0 ? `💰 ${fmtCostBig(totalSaved)}` : '—'),
        h('div', { style: { fontSize: '0.6875rem', color: '#6b5f4a', marginTop: '0.25rem' } },
          totalSaved > 0
            ? `近 7 天累計節省 · ${totalTokensSaved.toLocaleString()} tokens`
            : '尚無節省數據（互動後將自動計算）')
      ),
      // ── 各策略明細 ──
      strategies.length > 0
        ? h('div', { style: {
            paddingTop: '0.5rem', borderTop: '1px solid rgba(255,255,255,0.05)'
          } },
            ...strategies.map((s, idx) => {
              const pct = s.percentage || 0;
              const barColor = s.color || '#c9a96e';
              const isHaikuRow = idx === 0; // 第一個策略 = Haiku 路由分流
              return h('div', { style: {
                padding: '0.5rem 0', borderBottom: '1px solid rgba(255,255,255,0.03)'
              } },
                // 第一行：策略名 + 金額（Haiku 可點擊展開）
                h('div', {
                  style: {
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem',
                    cursor: isHaikuRow ? 'pointer' : 'default',
                  },
                  onClick: isHaikuRow ? () => { state.routingDetailExpanded = !state.routingDetailExpanded; render(); } : undefined,
                },
                  h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.375rem' } },
                    h('span', { style: { fontSize: '0.8125rem' } }, s.icon || '📊'),
                    h('span', { style: { fontSize: '0.75rem', fontWeight: '600', color: '#e8dcc6' } }, s.name),
                    isHaikuRow
                      ? h('span', { style: { fontSize: '0.5625rem', color: '#6b5f4a', marginLeft: '0.125rem' } },
                          state.routingDetailExpanded ? '▾' : '▸')
                      : null
                  ),
                  h('span', { style: {
                    fontSize: '0.75rem', fontWeight: '700',
                    color: s.tokens_saved > 0 ? '#10b981' : '#6b5f4a'
                  } }, s.tokens_saved > 0 ? fmtCost(s.cost_saved_usd || 0) : '—')
                ),
                // 第二行：token 量 + 比例 bar
                h('div', { style: {
                  display: 'flex', alignItems: 'center', gap: '0.5rem'
                } },
                  h('div', { style: {
                    flex: 1, height: '4px', background: 'rgba(255,255,255,0.06)',
                    borderRadius: '2px', overflow: 'hidden'
                  } },
                    h('div', { style: {
                      width: `${Math.min(pct, 100)}%`, height: '100%',
                      background: barColor, borderRadius: '2px',
                      transition: 'width 0.4s ease'
                    } })
                  ),
                  h('span', { style: { fontSize: '0.5625rem', color: '#9a8b70', whiteSpace: 'nowrap', minWidth: '3.5rem', textAlign: 'right' } },
                    s.tokens_saved > 0
                      ? `${s.tokens_saved.toLocaleString()} tok · ${pct.toFixed(1)}%`
                      : s.status_text || '運行中')
                ),
                // ── Haiku 路由明細（展開區）──
                isHaikuRow && state.routingDetailExpanded
                  ? h('div', { style: {
                      marginTop: '0.5rem', padding: '0.5rem 0.625rem',
                      background: 'rgba(139,92,246,0.06)', borderRadius: '0.375rem',
                      border: '1px solid rgba(139,92,246,0.12)',
                    } },
                      // 三欄數據
                      h('div', { style: {
                        display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.375rem',
                        marginBottom: '0.5rem'
                      } },
                        h('div', { style: { textAlign: 'center' } },
                          h('div', { style: { fontSize: '1rem', fontWeight: '700', color: '#8b5cf6' } }, `${haikuCalls}`),
                          h('div', { style: { fontSize: '0.5625rem', color: '#6b5f4a' } }, '🍃 Haiku 次數')
                        ),
                        h('div', { style: { textAlign: 'center' } },
                          h('div', { style: { fontSize: '1rem', fontWeight: '700', color: '#c9a96e' } }, `${totalCalls}`),
                          h('div', { style: { fontSize: '0.5625rem', color: '#6b5f4a' } }, '⚡ 總呼叫')
                        ),
                        h('div', { style: { textAlign: 'center' } },
                          h('div', { style: { fontSize: '1rem', fontWeight: '700', color: haikuRatio > 20 ? '#10b981' : '#f59e0b' } }, `${haikuRatio}%`),
                          h('div', { style: { fontSize: '0.5625rem', color: '#6b5f4a' } }, '🎯 Haiku 比例')
                        )
                      ),
                      // Haiku token 量
                      tokensOnHaiku > 0
                        ? h('div', { style: {
                            padding: '0.25rem 0.5rem', marginBottom: '0.375rem',
                            background: 'rgba(139,92,246,0.08)', borderRadius: '0.25rem',
                            fontSize: '0.625rem', color: '#9a8b70', textAlign: 'center'
                          } }, `🍃 Haiku 處理了 ${tokensOnHaiku.toLocaleString()} tokens`)
                        : null,
                      // 今日路由記錄
                      todayLog.length > 0
                        ? h('div', { style: { paddingTop: '0.375rem', borderTop: '1px solid rgba(255,255,255,0.05)' } },
                            h('div', { style: { fontSize: '0.625rem', fontWeight: '700', color: '#c9a96e', marginBottom: '0.25rem' } },
                              '📋 今日路由記錄'),
                            ...todayLog.map(entry =>
                              h('div', { style: {
                                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                padding: '0.1875rem 0', fontSize: '0.5625rem', color: '#9a8b70',
                                borderBottom: '1px solid rgba(255,255,255,0.03)'
                              } },
                                h('span', null,
                                  (entry.model === 'haiku' ? '🍃' : '⚡') + ' ' + entry.task_type
                                ),
                                h('span', null, `${(entry.tokens || 0).toLocaleString()} tok`),
                                h('span', { style: { color: '#6b5f4a' } },
                                  entry.ts ? entry.ts.split('T')[1]?.substring(0, 8) : '')
                              )
                            )
                          )
                        : null
                    )
                  : null
              );
            })
          )
        : null
    )
  );
}

async function loadSavingsBreakdown() {
  try {
    const resp = await fetch('http://127.0.0.1:8765/api/savings/breakdown');
    if (resp.ok) {
      state.savingsBreakdown = await resp.json();
      if (state.activeTab === 'settings') render();
    }
  } catch (err) {
    // Gateway 可能未啟動，靜默忽略
  }
}

// ─── MCP 連接器管理 ───

async function loadMCPCatalog() {
  try {
    const resp = await fetch('http://127.0.0.1:8765/api/mcp/catalog');
    if (resp.ok) {
      const data = await resp.json();
      state.mcpCatalog = data.catalog || [];
      if (state.activeTab === 'settings') render();
    }
  } catch (err) {
    // Gateway 可能未啟動，靜默忽略
  }
}

// ═══ MCP 連接器面板（收合 + Grid + Modal）═══

const MCP_CATEGORIES = [
  { key: 'all', label: '全部' },
  { key: 'search', label: '搜尋' },
  { key: 'productivity', label: '生產力' },
  { key: 'development', label: '開發' },
  { key: 'communication', label: '溝通' },
  { key: 'database', label: '資料庫' },
];

const MCP_CATEGORY_LABELS = {
  search: '🔍 搜尋與研究',
  productivity: '📋 生產力工具',
  development: '💻 開發工具',
  communication: '💬 溝通與社群',
  database: '🗃️ 資料庫',
};

function renderMCPPanel() {
  const catalog = state.mcpCatalog;

  // 還沒載入 → 觸發載入
  if (!catalog) {
    if (!state.mcpLoading) {
      state.mcpLoading = true;
      loadMCPCatalog().finally(() => { state.mcpLoading = false; });
    }
    return h('div', { className: 'settings-section settings-collapsible' },
      h('h2', null, '🔌 MCP 連接器'),
      h('div', { style: {
        textAlign: 'center', padding: '1.5rem', fontSize: '0.75rem', color: '#6b5f4a'
      } }, '載入中...')
    );
  }

  const connectedCount = catalog.filter(s => s.status === 'connected').length;

  return h('div', { className: 'settings-section settings-collapsible' },
    // 可收合標題
    h('h2', {
      onClick: () => { state.mcpCollapsed = !state.mcpCollapsed; render(); },
      style: { cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', userSelect: 'none' }
    },
      h('span', null, '🔌 MCP 連接器'),
      h('span', { style: { fontSize: '0.6875rem', color: '#6b5f4a', display: 'flex', alignItems: 'center', gap: '0.375rem' } },
        h('span', { style: { color: connectedCount > 0 ? '#4ade80' : '#9a8b70' } },
          `${connectedCount}/${catalog.length}`),
        state.mcpCollapsed ? '▸' : '▾'
      )
    ),
    // 收合時不顯示內容
    !state.mcpCollapsed ? renderMCPGrid(catalog) : null,
    // Modal 覆蓋層
    state.mcpModalServer ? renderMCPModal() : null
  );
}

function renderMCPGrid(catalog) {
  const filter = state.mcpCategoryFilter || 'all';
  const filtered = filter === 'all' ? catalog : catalog.filter(s => s.category === filter);

  // 分類 tab bar
  const tabBar = h('div', { className: 'mcp-filter-tabs' },
    ...MCP_CATEGORIES.map(cat =>
      h('button', {
        className: `mcp-filter-tab ${filter === cat.key ? 'active' : ''}`,
        onClick: () => { state.mcpCategoryFilter = cat.key; render(); }
      }, cat.label)
    )
  );

  // 按分類分組
  const groups = [];
  if (filter === 'all') {
    // 按分類分組顯示
    const categoryOrder = ['search', 'productivity', 'development', 'communication', 'database'];
    for (const cat of categoryOrder) {
      const servers = filtered.filter(s => s.category === cat);
      if (servers.length === 0) continue;
      groups.push(
        h('div', { className: 'mcp-category-group' },
          h('div', { className: 'mcp-category-label' }, MCP_CATEGORY_LABELS[cat] || cat),
          h('div', { className: 'mcp-grid' },
            ...servers.map(s => renderMCPCard(s))
          )
        )
      );
    }
  } else {
    // 單一分類 → 不需要標題
    groups.push(
      h('div', { className: 'mcp-grid' },
        ...filtered.map(s => renderMCPCard(s))
      )
    );
  }

  return h('div', { style: { marginTop: '0.5rem' } },
    tabBar,
    ...groups
  );
}

function renderMCPCard(server) {
  const isConnected = server.status === 'connected';
  const hasError = server.status === 'error';
  const isConnecting = state.mcpConnecting[server.name];

  // 狀態 badge 文字
  let badgeText, badgeClass;
  if (isConnecting) {
    badgeText = '連線中...';
    badgeClass = 'connecting';
  } else if (isConnected) {
    badgeText = `✅ ${server.tools_count || 0} tools`;
    badgeClass = 'connected';
  } else if (hasError) {
    badgeText = '❌ 錯誤';
    badgeClass = 'error';
  } else if (!server.auth_required) {
    badgeText = '🆓 免費';
    badgeClass = 'free';
  } else {
    badgeText = '🔑 需設定';
    badgeClass = 'needs-auth';
  }

  return h('div', {
    className: `mcp-card ${isConnected ? 'connected' : ''} ${hasError ? 'error' : ''}`,
    onClick: () => { openMCPModal(server); }
  },
    h('div', { className: 'mcp-card-icon' }, server.icon || '🔌'),
    h('div', { className: 'mcp-card-name' }, server.display_name),
    h('div', { className: `mcp-card-badge ${badgeClass}` }, badgeText)
  );
}

function openMCPModal(server) {
  state.mcpModalServer = server;
  // 初始化 env 輸入
  if (!state.mcpEnvInputs[server.name] && server.auth_env && server.auth_env.length > 0) {
    const envObj = {};
    server.auth_env.forEach(k => { envObj[k] = ''; });
    state.mcpEnvInputs[server.name] = envObj;
  }
  render();
}

function closeMCPModal() {
  state.mcpModalServer = null;
  render();
}

function renderMCPModal() {
  const server = state.mcpModalServer;
  if (!server) return null;

  const isConnected = server.status === 'connected';
  const hasError = server.status === 'error';
  const isConnecting = state.mcpConnecting[server.name];

  let modalBody;

  if (isConnected) {
    // ── 狀態 C：已連線 ──
    modalBody = h('div', { className: 'mcp-modal-body' },
      h('div', { style: { textAlign: 'center', padding: '1rem 0' } },
        h('div', { style: { fontSize: '2.5rem', marginBottom: '0.75rem' } }, '✅'),
        h('div', { style: { fontSize: '0.875rem', color: '#4ade80', fontWeight: '600', marginBottom: '0.5rem' } }, '已連線'),
        h('div', { style: { fontSize: '0.75rem', color: '#9a8b70', marginBottom: '0.25rem' } },
          `工具數：${server.tools_count || 0} tools`),
        server.connected_at
          ? h('div', { style: { fontSize: '0.6875rem', color: '#6b5f4a' } },
              `連線時間：${server.connected_at.replace('T', ' ').slice(0, 16)}`)
          : null
      ),
      h('div', { style: { textAlign: 'center', marginTop: '1rem' } },
        h('button', {
          className: 'mcp-disconnect-btn-modal',
          onClick: async () => {
            await fetch('http://127.0.0.1:8765/api/mcp/disconnect', {
              method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: server.name }),
            });
            state.mcpModalServer = null;
            await loadMCPCatalog();
          }
        }, '⛔ 斷開連線')
      )
    );
  } else if (!server.auth_required) {
    // ── 狀態 A：免費安裝 ──
    modalBody = h('div', { className: 'mcp-modal-body' },
      h('div', { style: { fontSize: '0.8125rem', color: '#c8bda6', lineHeight: '1.6', marginBottom: '1rem' } },
        server.description),
      h('div', { style: { marginBottom: '1rem' } },
        h('div', { style: { fontSize: '0.75rem', color: '#4ade80', marginBottom: '0.25rem' } }, '✅ 不需要任何設定'),
        h('div', { style: { fontSize: '0.75rem', color: '#4ade80' } }, '✅ 免費使用')
      ),
      hasError && server.error
        ? h('div', { style: { fontSize: '0.6875rem', color: '#ef4444', marginBottom: '0.75rem', padding: '0.5rem', background: 'rgba(239,68,68,0.1)', borderRadius: '0.375rem' } },
            `⚠️ ${server.error}`)
        : null,
      h('div', { style: { textAlign: 'center' } },
        h('button', {
          className: 'mcp-install-btn',
          disabled: isConnecting,
          onClick: async () => {
            state.mcpConnecting[server.name] = true;
            render();
            try {
              await fetch('http://127.0.0.1:8765/api/mcp/connect', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: server.name, env: {} }),
              });
            } finally {
              state.mcpConnecting[server.name] = false;
              state.mcpModalServer = null;
              await loadMCPCatalog();
            }
          }
        }, isConnecting ? '安裝中...' : '🚀 一鍵安裝')
      ),
      isConnecting
        ? h('div', { className: 'mcp-progress-bar' },
            h('div', { className: 'mcp-progress-fill' }))
        : null
    );
  } else {
    // ── 狀態 B：需要 API Key ──
    const envInputs = state.mcpEnvInputs[server.name] || {};

    const authFields = (server.auth_env || []).map(envKey =>
      h('div', { style: { marginBottom: '0.75rem' } },
        h('label', { style: { display: 'block', fontSize: '0.6875rem', color: '#9a8b70', marginBottom: '0.25rem', fontWeight: '600' } },
          `🔑 ${envKey}`),
        h('input', {
          type: 'password',
          placeholder: `輸入 ${envKey}`,
          value: envInputs[envKey] || '',
          style: {
            width: '100%', padding: '0.5rem 0.625rem', fontSize: '0.75rem',
            background: 'rgba(255,255,255,0.06)', color: '#e0d5c0',
            border: '1px solid rgba(201,169,110,0.3)', borderRadius: '0.5rem',
            boxSizing: 'border-box',
          },
          onInput: (e) => {
            if (!state.mcpEnvInputs[server.name]) state.mcpEnvInputs[server.name] = {};
            state.mcpEnvInputs[server.name][envKey] = e.target.value;
          }
        })
      )
    );

    modalBody = h('div', { className: 'mcp-modal-body' },
      h('div', { style: { fontSize: '0.8125rem', color: '#c8bda6', lineHeight: '1.6', marginBottom: '1rem' } },
        server.description),
      // 設定步驟
      h('div', { className: 'mcp-step-list' },
        h('div', { className: 'mcp-step' },
          h('span', { className: 'mcp-step-num' }, '1'),
          h('span', null, '前往服務設定頁面')
        ),
        server.auth_url
          ? h('button', {
              className: 'mcp-link-btn',
              onClick: () => {
                if (window.museon && window.museon.openExternal) {
                  window.museon.openExternal(server.auth_url);
                } else {
                  window.open(server.auth_url, '_blank');
                }
              }
            }, '🔗 開啟設定頁面')
          : null,
        h('div', { className: 'mcp-step' },
          h('span', { className: 'mcp-step-num' }, '2'),
          h('span', null, '建立 API Key / Token')
        ),
        h('div', { className: 'mcp-step' },
          h('span', { className: 'mcp-step-num' }, '3'),
          h('span', null, '複製並貼到下方')
        )
      ),
      server.auth_guide
        ? h('div', { style: { fontSize: '0.6875rem', color: '#9a8b70', marginBottom: '0.75rem', padding: '0.5rem', background: 'rgba(201,169,110,0.08)', borderRadius: '0.375rem', lineHeight: '1.5' } },
            `💡 ${server.auth_guide}`)
        : null,
      // Auth fields
      ...authFields,
      hasError && server.error
        ? h('div', { style: { fontSize: '0.6875rem', color: '#ef4444', marginBottom: '0.75rem', padding: '0.5rem', background: 'rgba(239,68,68,0.1)', borderRadius: '0.375rem' } },
            `⚠️ ${server.error}`)
        : null,
      // 按鈕
      h('div', { style: { textAlign: 'center', marginTop: '0.5rem' } },
        h('button', {
          className: 'mcp-install-btn',
          disabled: isConnecting,
          onClick: async () => {
            state.mcpConnecting[server.name] = true;
            render();
            try {
              await fetch('http://127.0.0.1:8765/api/mcp/connect', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: server.name, env: envInputs }),
              });
            } finally {
              state.mcpConnecting[server.name] = false;
              state.mcpModalServer = null;
              await loadMCPCatalog();
            }
          }
        }, isConnecting ? '連線中...' : '儲存並連線')
      ),
      isConnecting
        ? h('div', { className: 'mcp-progress-bar' },
            h('div', { className: 'mcp-progress-fill' }))
        : null
    );
  }

  // Modal 外框 — 復用 crystal-modal-overlay pattern
  return h('div', {
    className: 'crystal-modal-overlay',
    onClick: (e) => { if (e.target === e.currentTarget) closeMCPModal(); }
  },
    h('div', { className: 'mcp-modal' },
      // Header
      h('div', { className: 'mcp-modal-header' },
        h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.625rem', flex: 1 } },
          h('span', { style: { fontSize: '1.5rem' } }, server.icon || '🔌'),
          h('span', { className: 'mcp-modal-title' }, server.display_name)
        ),
        h('button', {
          className: 'crystal-modal-close',
          onClick: closeMCPModal
        }, '✕')
      ),
      // Body
      modalBody
    )
  );
}

function renderSettingToggle(title, desc, id) {
  // 讀取對應 state
  let checked = false;
  if (id === 'autolaunch') checked = state.autoLaunchEnabled;

  const checkbox = h('input', { type: 'checkbox', checked });
  checkbox.addEventListener('change', async (e) => {
    const newVal = e.target.checked;
    if (id === 'autolaunch') {
      state.autoLaunchEnabled = newVal;
      try {
        if (window.museon && window.museon.setAutoLaunch) {
          await window.museon.setAutoLaunch(newVal);
        }
      } catch (err) {
        console.error('Failed to set auto-launch:', err);
        state.autoLaunchEnabled = !newVal; // rollback
        render();
      }
    }
  });

  return h('div', { className: 'setting-item' },
    h('div', { className: 'setting-label' },
      h('div', { className: 'setting-title' }, title),
      h('div', { className: 'setting-description' }, desc)
    ),
    h('label', { className: 'toggle' },
      checkbox,
      h('span', { className: 'toggle-slider' })
    )
  );
}

function renderSettingItem(title, value) {
  return h('div', { className: 'setting-item' },
    h('div', { className: 'setting-label' },
      h('div', { className: 'setting-title' }, title)
    ),
    h('span', { style: { color: '#9a8b70' } }, value)
  );
}

function renderTelegramStatus() {
  const ts = state.telegramStatus;
  const isRunning = ts && ts.running;
  const isConfigured = ts && ts.configured;
  const lastMsg = ts && ts.last_message_time
    ? new Date(ts.last_message_time).toLocaleString('zh-TW')
    : '無紀錄';

  // 狀態文字：區分 Gateway 離線 vs 真的沒設定
  let configDesc = '查詢中...';
  if (ts) {
    if (ts.error && !state.gatewayOnline) {
      configDesc = '⚠️ 閘道器離線（無法查詢即時狀態）';
    } else if (isConfigured) {
      configDesc = '✅ 已設定令牌' + (ts.masked_value ? ` (${ts.masked_value})` : '');
    } else {
      configDesc = '尚未設定令牌';
    }
  }

  return h('div', { className: 'settings-section settings-collapsible' },
    h('h2', {
      onClick: () => { state.telegramCollapsed = !state.telegramCollapsed; render(); },
      style: { cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', userSelect: 'none' }
    },
      h('span', null, '📱 Telegram'),
      h('span', { style: { display: 'flex', alignItems: 'center', gap: '0.5rem' } },
        h('span', { style: { fontSize: '0.6875rem', color: isRunning ? '#10b981' : '#ef4444' } },
          isRunning ? '運行中' : '離線'),
        h('span', { style: { fontSize: '0.6875rem', color: '#6b5f4a', transition: 'transform 0.2s' } },
          state.telegramCollapsed ? '▸' : '▾')
      )
    ),
    !state.telegramCollapsed
      ? h('div', null,
          h('div', { className: 'setting-item' },
            h('div', { className: 'setting-label' },
              h('div', { className: 'setting-title' }, '連線狀態'),
              h('div', { className: 'setting-description' }, configDesc)
            ),
            h('div', { style: { display: 'flex', alignItems: 'center', gap: '0.5rem', flexShrink: 0 } },
              h('div', {
                className: `status-dot ${isRunning ? '' : 'offline'}`,
                style: { width: '10px', height: '10px' }
              }),
              h('span', { style: { color: isRunning ? '#10b981' : '#ef4444', fontSize: '0.8125rem' } },
                isRunning ? '運行中' : '離線')
            )
          ),
          h('div', { className: 'setting-item' },
            h('div', { className: 'setting-label' },
              h('div', { className: 'setting-title' }, '最後訊息'),
              h('div', { className: 'setting-description' }, '最近一次收到 Telegram 訊息的時間')
            ),
            h('span', { style: { color: '#9a8b70', fontSize: '0.8125rem' } }, lastMsg)
          ),
          h('div', { className: 'setting-item' },
            h('div', { className: 'setting-label' },
              h('div', { className: 'setting-title' }, '重新連線'),
              h('div', { className: 'setting-description' }, '不重啟閘道器，僅重新連接 Telegram 機器人')
            ),
            h('button', {
              className: 'wizard-btn-primary',
              style: { padding: '0.4rem 0.875rem', fontSize: '0.8125rem' },
              disabled: state.telegramRestarting,
              onClick: handleTelegramRestart,
            }, state.telegramRestarting ? '重新連線中...' : '🔄 重新連線')
          )
        )
      : null
  );
}

async function loadBudgetStats() {
  try {
    if (window.museon && window.museon.getBudgetStats) {
      state.budgetStats = await window.museon.getBudgetStats();
      if (state.activeTab === 'settings') render();
    }
  } catch (err) {
    console.error('Failed to load budget stats:', err);
  }
}

async function loadRoutingStats() {
  try {
    const resp = await fetch('http://127.0.0.1:8765/api/routing/stats');
    if (resp.ok) {
      state.routingStats = await resp.json();
      if (state.activeTab === 'settings') render();
    }
  } catch (err) {
    // Gateway 可能未啟動，靜默忽略
  }
}

async function loadAutoLaunchState() {
  try {
    if (window.museon && window.museon.getAutoLaunch) {
      state.autoLaunchEnabled = await window.museon.getAutoLaunch();
      if (state.activeTab === 'settings') render();
    }
  } catch (err) {
    console.error('Failed to load auto-launch state:', err);
  }
}

async function loadGatewayInfo() {
  try {
    if (window.museon && window.museon.getGatewayInfo) {
      state.gatewayInfo = await window.museon.getGatewayInfo();
      if (state.activeTab === 'settings') render();
    }
  } catch (err) {
    console.error('Failed to load gateway info:', err);
  }
}

async function loadTelegramStatus() {
  try {
    if (window.museon && window.museon.getTelegramStatus) {
      state.telegramStatus = await window.museon.getTelegramStatus();
      if (state.activeTab === 'settings') render();
    }
  } catch (err) {
    console.error('Failed to load Telegram status:', err);
  }
}

async function handleTelegramRestart() {
  if (state.telegramRestarting) return;
  state.telegramRestarting = true;
  render();
  try {
    if (window.museon && window.museon.restartTelegram) {
      const result = await window.museon.restartTelegram();
      if (result.success) {
        addGatewayLog('success', '✅ Telegram 重新連線成功');
      } else {
        addGatewayLog('error', '❌ Telegram 重連失敗：' + (result.error || '未知'));
      }
      // Reload status
      await loadTelegramStatus();
    }
  } catch (err) {
    console.error('Telegram restart error:', err);
  }
  state.telegramRestarting = false;
  render();
}

// ═══════════════════════════════════════
// Install Mode Selector（安裝模式選擇器）
// ═══════════════════════════════════════

function renderModeSelector() {
  return h('div', { className: 'setup-wizard-overlay' },
    h('div', { className: 'wizard-card', style: 'max-width: 560px' },
      h('div', { className: 'wizard-step-content' },
        h('div', { className: 'wizard-emoji-large' }, '🐾'),
        h('h1', { className: 'wizard-title' }, '偵測到新版本'),
        h('p', { className: 'wizard-subtitle' }, 'MUSEON 已更新，請選擇安裝方式'),

        h('div', { className: 'mode-selector-options' },
          // 選項 1：迭代覆蓋（預設）
          renderModeOption('upgrade', '🔄', '迭代覆蓋', 'Upgrade',
            '保留所有資料與記憶，直接升級到新版本', true, false),
          // 選項 2：清空重裝
          renderModeOption('clean', '🧹', '清空重裝', 'Clean Install',
            '備份舊資料到 data_archive/，重新設定 API 金鑰與 Telegram', false, false),
          // 選項 3：另裝新的（Phase 2）
          renderModeOption('new-instance', '📦', '另裝新的', 'New Instance',
            '建立獨立安裝（~/MUSEON-2/），綁定不同 Telegram Bot', false, true),
        ),

        // 備份中指示器
        state.modeArchiving
          ? h('div', { className: 'mode-archiving-status' },
              h('span', { className: 'wizard-spinner' }),
              ' 正在備份資料...'
            )
          : null,
      )
    )
  );
}

function renderModeOption(id, emoji, title, titleEn, desc, isDefault, isPhase2) {
  const isSelected = state.modeSelected === id;
  const disabled = state.modeArchiving || isPhase2;
  const cls = 'mode-option'
    + (isSelected ? ' selected' : '')
    + (disabled ? ' disabled' : '');

  return h('div', {
    className: cls,
    onClick: disabled ? null : function() { handleModeSelect(id); },
  },
    h('span', { className: 'mode-option-emoji' }, emoji),
    h('div', { className: 'mode-option-body' },
      h('div', { className: 'mode-option-header' },
        h('span', { className: 'mode-option-title' }, title),
        h('span', { className: 'mode-option-title-en' }, titleEn),
        isDefault
          ? h('span', { className: 'mode-option-badge default' }, '推薦')
          : null,
        isPhase2
          ? h('span', { className: 'mode-option-badge coming' }, '即將推出')
          : null,
      ),
      h('div', { className: 'mode-option-desc' }, desc),
    )
  );
}

async function handleModeSelect(mode) {
  if (state.modeArchiving) return;

  state.modeSelected = mode;
  render();

  if (mode === 'upgrade') {
    // 迭代覆蓋：蓋章 + 直接進 dashboard
    try { await window.museon.stampLaunchedVersion(); } catch (e) { console.error(e); }
    state.showModeSelector = false;
    state.showSetupWizard = false;
    render();
    loadBrainState();
    loadMemoryDates();
    startAutoRefresh();

  } else if (mode === 'clean') {
    // 清空重裝：備份 → wizard
    state.modeArchiving = true;
    render();
    try {
      const result = await window.museon.archiveData();
      if (!result.success) console.error('Archive failed:', result.message);
      await window.museon.stampLaunchedVersion();
    } catch (e) { console.error(e); }

    state.modeArchiving = false;
    state.showModeSelector = false;
    state.showSetupWizard = true;
    state.wizardStep = 0;
    // 重設 wizard state
    state.anthropicKey = '';
    state.telegramToken = '';
    state.anthropicValid = null;
    state.telegramValid = null;
    state.testResults = {
      anthropic: { status: 'pending', message: '' },
      telegram: { status: 'pending', message: '' },
    };
    state.wizardToolsSelected = {};
    state.wizardToolsInstalling = false;
    state.wizardToolsProgress = {};
    state.wizardToolsDone = false;
    render();
  }
  // 'new-instance' → Phase 2
}

// ═══════════════════════════════════════
// Setup Wizard
// ═══════════════════════════════════════
function renderSetupWizard() {
  return h('div', { className: 'setup-wizard-overlay' },
    h('div', { className: 'wizard-card' },
      renderProgressDots(),
      h('div', { className: 'wizard-body' },
        renderWizardStep()
      )
    )
  );
}

function renderProgressDots() {
  const container = h('div', { className: 'wizard-progress' });
  for (let i = 0; i < TOTAL_STEPS; i++) {
    const dotClass = i === state.wizardStep ? 'active' : i < state.wizardStep ? 'completed' : '';
    container.appendChild(
      h('div', { className: `wizard-step-dot ${dotClass}` }, i < state.wizardStep ? '✓' : '')
    );
    if (i < TOTAL_STEPS - 1) {
      container.appendChild(
        h('div', { className: `wizard-step-line ${i < state.wizardStep ? 'completed' : ''}` })
      );
    }
  }
  return container;
}

function renderWizardStep() {
  switch (state.wizardStep) {
    case 0: return renderStep0Welcome();
    case 1: return renderStep1Anthropic();
    case 2: return renderStep2Telegram();
    case 3: return renderStep3Test();
    case 4: return renderStep4Tools();
    case 5: return renderStep5Complete();
    default: return renderStep0Welcome();
  }
}

// --- Step 0: Welcome ---
function renderStep0Welcome() {
  return h('div', { className: 'wizard-step-content' },
    h('div', { className: 'wizard-emoji-large' }, '🐾'),
    h('h1', { className: 'wizard-title' }, '歡迎使用 MUSEON'),
    h('p', { className: 'wizard-subtitle' },
      '讓我們花 2 分鐘完成初始設定',
      h('br'),
      h('span', { className: 'wizard-subtitle-dim' }, '只需幾個步驟，輕鬆完成設定')
    ),
    h('button', { className: 'wizard-btn-primary', onClick: () => goWizardStep(1) }, '開始設定 →')
  );
}

// --- Step 1: Anthropic Key ---
function renderStep1Anthropic() {
  const validClass = state.anthropicValid === null ? 'wizard-input' :
    state.anthropicValid ? 'wizard-input valid' : 'wizard-input invalid';

  const input = h('input', {
    type: state.showAnthropicKey ? 'text' : 'password',
    className: validClass,
    placeholder: 'sk-ant-api03-...',
    value: state.anthropicKey,
  });
  input.addEventListener('input', (e) => {
    state.anthropicKey = e.target.value;
    if (state.anthropicKey.length > 0) {
      const k = state.anthropicKey.trim();
      state.anthropicValid = k.startsWith('sk-ant-') && k.length >= 20;
    } else {
      state.anthropicValid = null;
    }
    render();
    // Restore focus
    const el = document.querySelector('.wizard-input');
    if (el) { el.focus(); el.setSelectionRange(e.target.selectionStart, e.target.selectionEnd); }
  });

  const validationEl = state.anthropicValid === true
    ? h('div', { className: 'wizard-validation valid' }, '✓ 格式正確')
    : (state.anthropicValid === false && state.anthropicKey.length > 0)
      ? h('div', { className: 'wizard-validation invalid' }, '✗ 應以 sk-ant- 開頭，且長度 >= 20')
      : null;

  return h('div', { className: 'wizard-step-content' },
    h('div', { className: 'wizard-emoji' }, '🔑'),
    h('h2', { className: 'wizard-step-title' }, 'Anthropic API 金鑰'),
    h('p', { className: 'wizard-step-desc' }, "MUSEON 的 AI 大腦需要這把鑰匙"),
    h('div', { className: 'wizard-input-group' },
      h('div', { className: 'wizard-input-wrapper' },
        input,
        h('button', {
          className: 'wizard-eye-btn',
          type: 'button',
          onClick: () => { state.showAnthropicKey = !state.showAnthropicKey; render(); }
        }, state.showAnthropicKey ? '🙈' : '👁️')
      ),
      validationEl
    ),
    h('a', {
      className: 'wizard-help-link',
      href: 'https://console.anthropic.com/settings/keys',
      target: '_blank',
      rel: 'noopener noreferrer'
    }, '💡 還沒有？前往 console.anthropic.com 取得'),
    h('div', { className: 'wizard-btn-row' },
      h('button', { className: 'wizard-btn-secondary', onClick: () => goWizardStep(0) }, '← 上一步'),
      h('button', {
        className: 'wizard-btn-primary',
        disabled: !state.anthropicValid || state.saving,
        onClick: handleSaveAnthropicKey,
      }, state.saving ? '儲存中...' : '下一步 →')
    )
  );
}

// --- Step 2: Telegram Token ---
function renderStep2Telegram() {
  const validClass = state.telegramValid === null ? 'wizard-input' :
    state.telegramValid ? 'wizard-input valid' : 'wizard-input invalid';

  const input = h('input', {
    type: state.showTelegramToken ? 'text' : 'password',
    className: validClass,
    placeholder: '1234567890:ABCdef...',
    value: state.telegramToken,
  });
  input.addEventListener('input', (e) => {
    state.telegramToken = e.target.value;
    if (state.telegramToken.length > 0) {
      state.telegramValid = /^\d+:[A-Za-z0-9_-]+$/.test(state.telegramToken.trim());
    } else {
      state.telegramValid = null;
    }
    render();
    const el = document.querySelector('.wizard-input');
    if (el) { el.focus(); el.setSelectionRange(e.target.selectionStart, e.target.selectionEnd); }
  });

  const validationEl = state.telegramValid === true
    ? h('div', { className: 'wizard-validation valid' }, '✓ 格式正確')
    : (state.telegramValid === false && state.telegramToken.length > 0)
      ? h('div', { className: 'wizard-validation invalid' }, '✗ 格式應為「數字:英數」')
      : null;

  return h('div', { className: 'wizard-step-content' },
    h('div', { className: 'wizard-emoji' }, '🤖'),
    h('h2', { className: 'wizard-step-title' }, 'Telegram Bot 令牌'),
    h('p', { className: 'wizard-step-desc' }, '這是你和 MUSEON 對話的管道'),
    h('div', { className: 'wizard-input-group' },
      h('div', { className: 'wizard-input-wrapper' },
        input,
        h('button', {
          className: 'wizard-eye-btn',
          type: 'button',
          onClick: () => { state.showTelegramToken = !state.showTelegramToken; render(); }
        }, state.showTelegramToken ? '🙈' : '👁️')
      ),
      validationEl
    ),
    h('a', {
      className: 'wizard-help-link',
      href: 'https://t.me/BotFather',
      target: '_blank',
      rel: 'noopener noreferrer'
    }, '💡 需要建立 Bot？前往 @BotFather'),
    h('div', { className: 'wizard-btn-row' },
      h('button', { className: 'wizard-btn-secondary', onClick: () => goWizardStep(1) }, '← 上一步'),
      h('button', { className: 'wizard-btn-skip', onClick: () => goWizardStep(3) }, '稍後設定'),
      h('button', {
        className: 'wizard-btn-primary',
        disabled: !state.telegramValid || state.saving,
        onClick: handleSaveTelegramToken,
      }, state.saving ? '儲存中...' : '下一步 →')
    )
  );
}

// --- Step 3: Connection Test ---
function renderStep3Test() {
  const allDone =
    state.testResults.anthropic.status !== 'pending' &&
    state.testResults.anthropic.status !== 'testing' &&
    state.testResults.telegram.status !== 'pending' &&
    state.testResults.telegram.status !== 'testing';

  return h('div', { className: 'wizard-step-content' },
    h('div', { className: 'wizard-emoji' }, '🔍'),
    h('h2', { className: 'wizard-step-title' }, '連線測試'),
    h('p', { className: 'wizard-step-desc' }, '正在驗證你的設定'),
    h('div', { className: 'test-list' },
      renderTestItem('Anthropic API 連線', state.testResults.anthropic),
      renderTestItem('Telegram 機器人', state.testResults.telegram),
    ),
    h('div', { className: 'wizard-btn-row', style: { marginTop: '2rem' } },
      h('button', { className: 'wizard-btn-secondary', onClick: () => goWizardStep(2) }, '← 上一步'),
      h('button', {
        className: 'wizard-btn-primary',
        disabled: !allDone,
        onClick: () => goWizardStep(4),
      }, allDone ? '選擇工具 →' : '測試中...')
    )
  );
}

function renderTestItem(label, testState) {
  const iconMap = {
    pending: h('span', { className: 'test-icon pending' }, '○'),
    testing: h('span', { className: 'test-icon testing' }, h('span', { className: 'wizard-spinner' })),
    success: h('span', { className: 'test-icon success' }, '✓'),
    error: h('span', { className: 'test-icon error' }, '✗'),
    skipped: h('span', { className: 'test-icon skipped' }, '—'),
  };

  return h('div', { className: `test-item ${testState.status}` },
    iconMap[testState.status] || iconMap.pending,
    h('div', { className: 'test-content' },
      h('div', { className: 'test-label' }, label),
      testState.message ? h('div', { className: 'test-message' }, testState.message) : null
    )
  );
}

// --- Step 4: Tool Selection & Installation ---
function renderStep4Tools() {
  // 工具定義（與 ToolRegistry TOOL_CONFIGS 同步）
  const WIZARD_TOOLS = [
    { name: 'searxng', emoji: '🔍', label: 'SearXNG', desc: '搜尋引擎 — 聚合 70+ 來源，免費無限搜尋', ram: 256, type: 'docker', required: true },
    { name: 'qdrant', emoji: '🗄️', label: 'Qdrant', desc: '向量記憶庫 — 語義搜尋，中英文長期記憶', ram: 512, type: 'docker', required: true },
    { name: 'firecrawl', emoji: '🕷️', label: 'Firecrawl', desc: '網頁爬蟲 — 深度爬取 + Markdown 提取', ram: 256, type: 'docker', required: true },
    { name: 'whisper', emoji: '🎙️', label: 'Whisper.cpp', desc: '語音轉文字 — 支援繁體中文', ram: 500, type: 'native', required: false },
    { name: 'paddleocr', emoji: '📄', label: 'PaddleOCR', desc: '文字辨識 — 名片/發票/文件數位化', ram: 300, type: 'docker', required: false },
    { name: 'kokoro', emoji: '🔊', label: 'Kokoro TTS', desc: '語音合成 — 82M 輕量模型', ram: 200, type: 'pip', required: false },
  ];

  // 初始化選擇狀態（首次進入時：必要工具強制選中，其餘取消）
  if (Object.keys(state.wizardToolsSelected).length === 0) {
    WIZARD_TOOLS.forEach(t => {
      state.wizardToolsSelected[t.name] = t.required;
    });
  }

  const selectedCount = Object.values(state.wizardToolsSelected).filter(Boolean).length;
  const totalRam = WIZARD_TOOLS.filter(t => state.wizardToolsSelected[t.name]).reduce((sum, t) => sum + t.ram, 0);
  const isInstalling = state.wizardToolsInstalling;
  const progress = state.wizardToolsProgress;

  // 檢查是否全部完成
  const selectedTools = WIZARD_TOOLS.filter(t => state.wizardToolsSelected[t.name]);
  const allDone = isInstalling && selectedTools.length > 0 &&
    selectedTools.every(t => {
      const p = progress[t.name];
      return p && (p.status === 'installed' || p.status === 'failed');
    });

  if (allDone && !state.wizardToolsDone) {
    state.wizardToolsDone = true;
  }

  return h('div', { className: 'wizard-step-content' },
    h('div', { className: 'wizard-emoji' }, '🛠️'),
    h('h2', { className: 'wizard-step-title' }, '選擇要安裝的工具'),
    h('p', { className: 'wizard-step-desc' },
      isInstalling
        ? '正在安裝中，請稍候...'
        : `已選 ${selectedCount} 個工具，預估 RAM: ${totalRam}MB / 32GB`
    ),

    // 工具列表（勾選 or 進度）
    h('div', { style: { maxHeight: '320px', overflowY: 'auto', margin: '16px 0', display: 'flex', flexDirection: 'column', gap: '6px' } },
      ...WIZARD_TOOLS.map(tool => {
        const checked = state.wizardToolsSelected[tool.name];
        const prog = progress[tool.name];
        const isToolInstalling = prog && prog.status === 'installing';
        const isToolDone = prog && prog.status === 'installed';
        const isToolFailed = prog && prog.status === 'failed';
        const isQueued = prog && prog.status === 'queued';

        return h('div', {
          style: {
            display: 'flex', alignItems: 'center', gap: '12px',
            padding: '10px 14px', background: '#0d1525', borderRadius: '10px',
            border: `1px solid ${isToolDone ? '#10b981' : isToolFailed ? '#ef4444' : '#222d4a'}`,
            opacity: isInstalling && !checked ? 0.4 : 1,
          }
        },
          // 勾選 or 狀態圖示
          isInstalling
            ? h('span', { style: { fontSize: '1.2rem', width: '28px', textAlign: 'center' } },
                isToolDone ? '✅' : isToolFailed ? '❌' : isToolInstalling ? '⏳' : isQueued ? '⏸️' : '⚪'
              )
            : tool.required
              ? h('span', { style: { fontSize: '1.1rem', width: '28px', textAlign: 'center' } }, '🔒')
              : h('input', {
                  type: 'checkbox',
                  checked: checked,
                  style: { width: '18px', height: '18px', cursor: 'pointer', accentColor: '#c9a96e' },
                  onChange: () => {
                    state.wizardToolsSelected[tool.name] = !checked;
                    render();
                  },
                }),

          // 工具 emoji
          h('span', { style: { fontSize: '1.3rem' } }, tool.emoji),

          // 名稱 + 描述
          h('div', { style: { flex: 1, minWidth: 0 } },
            h('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' } },
              h('span', { style: { color: '#e8dcc6', fontWeight: '700', fontSize: '0.9rem' } }, tool.label),
              h('span', { style: { color: '#6b5f4a', fontSize: '0.7rem', padding: '1px 5px', background: '#111b2e', borderRadius: '4px' } },
                `${tool.type} · ${tool.ram}MB`
              ),
              tool.required ? h('span', { style: { color: '#ef4444', fontSize: '0.65rem', fontWeight: '700' } }, '必要') : null,
            ),
            // 描述 or 進度
            isToolInstalling
              ? h('div', { style: { marginTop: '4px' } },
                  h('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' } },
                    h('div', { style: { flex: 1, height: '6px', background: '#1a2340', borderRadius: '3px', overflow: 'hidden' } },
                      h('div', { style: {
                        width: `${prog.progress || 0}%`, height: '100%',
                        background: 'linear-gradient(90deg, #c9a96e, #e8dcc6)',
                        borderRadius: '3px', transition: 'width 0.3s',
                      }})
                    ),
                    h('span', { style: { color: '#c9a96e', fontSize: '0.7rem', minWidth: '36px' } }, `${prog.progress || 0}%`),
                  ),
                  h('div', { style: { color: '#9a8b70', fontSize: '0.7rem', marginTop: '2px' } }, prog.message || ''),
                )
              : isToolDone
                ? h('div', { style: { color: '#10b981', fontSize: '0.75rem', marginTop: '2px' } }, '✓ 安裝完成')
                : isToolFailed
                  ? h('div', { style: { color: '#ef4444', fontSize: '0.75rem', marginTop: '2px' } }, `✗ ${prog.message || '安裝失敗'}`)
                  : h('div', { style: { color: '#9a8b70', fontSize: '0.75rem', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, tool.desc),
          ),
        );
      }),
    ),

    // 按鈕列
    h('div', { className: 'wizard-btn-row', style: { marginTop: '12px' } },
      h('button', {
        className: 'wizard-btn-secondary',
        onClick: () => goWizardStep(3),
        disabled: isInstalling && !state.wizardToolsDone,
      }, '← 上一步'),
      !isInstalling
        ? h('button', {
            className: 'wizard-btn-skip',
            onClick: () => {
              // 跳過時仍安裝必要工具
              WIZARD_TOOLS.forEach(t => {
                state.wizardToolsSelected[t.name] = t.required;
              });
              handleWizardInstallTools();
            },
          }, '僅安裝必要工具')
        : null,
      !isInstalling
        ? h('button', {
            className: 'wizard-btn-primary',
            disabled: selectedCount === 0,
            onClick: handleWizardInstallTools,
          }, `安裝 ${selectedCount} 個工具 →`)
        : state.wizardToolsDone
          ? h('button', {
              className: 'wizard-btn-primary',
              onClick: () => goWizardStep(5),
            }, '繼續 →')
          : h('button', {
              className: 'wizard-btn-primary',
              disabled: true,
            }, '安裝中...'),
    ),
  );
}

async function handleWizardInstallTools() {
  const selectedTools = Object.entries(state.wizardToolsSelected)
    .filter(([, v]) => v)
    .map(([k]) => k);

  if (selectedTools.length === 0) return;

  state.wizardToolsInstalling = true;
  state.wizardToolsDone = false;
  // 初始化進度
  selectedTools.forEach(name => {
    state.wizardToolsProgress[name] = { status: 'queued', progress: 0, message: '排隊中...' };
  });
  render();

  try {
    await window.museon.installToolsBatch(selectedTools);
  } catch (err) {
    console.error('[MUSEON] batch install failed:', err);
  }

  // 開始輪詢進度
  const pollInterval = setInterval(async () => {
    let allFinished = true;
    for (const name of selectedTools) {
      try {
        const prog = await window.museon.getInstallProgress(name);
        state.wizardToolsProgress[name] = prog;
        if (prog.status === 'installing' || prog.status === 'queued') {
          allFinished = false;
        }
      } catch (err) {
        // ignore
      }
    }
    render();
    if (allFinished) {
      clearInterval(pollInterval);
      state.wizardToolsDone = true;
      render();
    }
  }, 1500);
}

// --- Step 5: Complete ---
function renderStep5Complete() {
  return h('div', { className: 'wizard-step-content' },
    h('div', { className: 'wizard-celebration' },
      h('div', { className: 'wizard-emoji-large celebration-pulse' }, '🎉')
    ),
    h('h1', { className: 'wizard-title' }, '設定完成！'),
    h('p', { className: 'wizard-subtitle' }, 'MUSEON 已經準備好了'),
    h('div', { className: 'wizard-next-steps' },
      h('div', { className: 'wizard-next-step-item' },
        h('span', { className: 'wizard-next-step-icon' }, '📱'),
        h('span', null, '打開 Telegram → 找到你的機器人 → 說第一句話')
      ),
      h('div', { className: 'wizard-next-step-item' },
        h('span', { className: 'wizard-next-step-icon' }, '🐾'),
        h('span', null, '命名儀式即將開始——等你開口')
      )
    ),
    h('button', {
      className: 'wizard-btn-primary wizard-btn-large',
      onClick: handleComplete,
    }, '開始使用 MUSEON')
  );
}

// ═══════════════════════════════════════
// Wizard Actions
// ═══════════════════════════════════════
function goWizardStep(n) {
  state.wizardStep = n;
  // 進入 step 3 時啟動連線測試
  if (n === 3) {
    state.testResults = {
      anthropic: { status: 'pending', message: '' },
      telegram: { status: 'pending', message: '' },
    };
    render();
    runConnectionTests();
    return;
  }
  // 進入 step 4 時重置工具安裝狀態
  if (n === 4) {
    if (!state.wizardToolsInstalling) {
      state.wizardToolsProgress = {};
      state.wizardToolsDone = false;
    }
  }
  render();
}

async function handleSaveAnthropicKey() {
  if (!state.anthropicValid) return;
  state.saving = true;
  render();
  try {
    await window.museon.saveSetupKey('ANTHROPIC_API_KEY', state.anthropicKey.trim());
    state.saving = false;
    goWizardStep(2);
  } catch (err) {
    console.error('Failed to save Anthropic key:', err);
    state.saving = false;
    render();
  }
}

async function handleSaveTelegramToken() {
  if (!state.telegramValid) return;
  state.saving = true;
  render();
  try {
    await window.museon.saveSetupKey('TELEGRAM_BOT_TOKEN', state.telegramToken.trim());
    state.saving = false;
    goWizardStep(3);
  } catch (err) {
    console.error('Failed to save Telegram token:', err);
    state.saving = false;
    render();
  }
}

async function runConnectionTests() {
  // Test Anthropic
  if (state.anthropicKey) {
    state.testResults.anthropic = { status: 'testing', message: 'Anthropic API 連線中...' };
    render();
    try {
      const result = await window.museon.testAnthropicKey(state.anthropicKey.trim());
      state.testResults.anthropic = {
        status: result.success ? 'success' : 'error',
        message: result.message,
      };
    } catch (err) {
      state.testResults.anthropic = { status: 'error', message: `連線失敗: ${err.message}` };
    }
    render();
  } else {
    state.testResults.anthropic = { status: 'error', message: '未設定 API 金鑰' };
    render();
  }

  // Wait a beat
  await new Promise(r => setTimeout(r, 800));

  // Test Telegram
  if (state.telegramToken) {
    state.testResults.telegram = { status: 'testing', message: 'Telegram Bot 驗證中...' };
    render();
    try {
      const result = await window.museon.testTelegramToken(state.telegramToken.trim());
      state.testResults.telegram = {
        status: result.success ? 'success' : 'error',
        message: result.message,
      };
    } catch (err) {
      state.testResults.telegram = { status: 'error', message: `連線失敗: ${err.message}` };
    }
  } else {
    state.testResults.telegram = { status: 'skipped', message: '稍後設定' };
  }
  render();
}

async function handleComplete() {
  try {
    await window.museon.completeSetup();
  } catch (err) {
    console.error('Failed to complete setup:', err);
  }
  // 安全：清除 renderer 記憶體中的敏感資料
  state.anthropicKey = '';
  state.telegramToken = '';
  state.showSetupWizard = false;
  render();
}

// ═══════════════════════════════════════
// Gateway Repair & Log Panel
// ═══════════════════════════════════════
async function handleGatewayRepair() {
  if (state.gatewayRepairing) return;
  state.gatewayRepairing = true;
  state.showGatewayPanel = true;
  addGatewayLog('info', '🔧 開始修復閘道器...');
  render();

  try {
    if (window.museon && window.museon.restartGateway) {
      const result = await window.museon.restartGateway();
      result.steps.forEach(step => {
        addGatewayLog(result.success ? 'info' : 'warn', step);
      });
      if (result.success) {
        addGatewayLog('success', '✅ 閘道器修復成功！');
        // Auto-close panel after 5 seconds
        setTimeout(() => {
          if (state.showGatewayPanel && state.gatewayOnline) {
            state.showGatewayPanel = false;
            render();
          }
        }, 5000);
      } else {
        addGatewayLog('error', '❌ 修復失敗：' + (result.error || '未知錯誤'));
      }
    } else {
      addGatewayLog('error', '❌ restartGateway API 不可用');
    }
  } catch (err) {
    addGatewayLog('error', '❌ 修復過程異常：' + err.message);
  }
  state.gatewayRepairing = false;
  render();
}

function addGatewayLog(level, message) {
  const now = new Date();
  const time = String(now.getHours()).padStart(2, '0') + ':' +
    String(now.getMinutes()).padStart(2, '0') + ':' +
    String(now.getSeconds()).padStart(2, '0');
  state.gatewayLogs.push({ level, message, time });
  // Keep max 100 entries
  if (state.gatewayLogs.length > 100) {
    state.gatewayLogs = state.gatewayLogs.slice(-100);
  }
}

function renderGatewayPanel() {
  const logs = state.gatewayLogs;
  return h('div', { className: 'gateway-panel' },
    h('div', { className: 'gateway-panel-header' },
      h('span', null, '🖥️ 閘道器運作狀態'),
      h('div', { style: { display: 'flex', gap: '0.5rem' } },
        h('button', {
          className: 'gateway-panel-btn',
          onClick: () => { state.gatewayLogs = []; render(); },
        }, '清除'),
        h('button', {
          className: 'gateway-panel-btn',
          onClick: () => { state.showGatewayPanel = false; render(); },
        }, '✕')
      )
    ),
    h('div', { className: 'gateway-panel-body', id: 'gateway-log-body' },
      logs.length === 0
        ? h('div', { style: { color: '#6b5f4a', padding: '1rem', textAlign: 'center' } },
            '尚無紀錄。點擊「修復」或等待閘道器輸出...')
        : h('div', null,
            ...logs.map(log => {
              const colorMap = {
                info: '#9a8b70', success: '#10b981',
                error: '#ef4444', warn: '#f59e0b',
              };
              return h('div', { className: 'gateway-log-line' },
                h('span', { style: { color: '#475569', marginRight: '0.5rem' } }, log.time),
                h('span', { style: { color: colorMap[log.level] || '#9a8b70' } }, log.message)
              );
            })
          )
    )
  );
}

// ═══════════════════════════════════════
// Data Loading
// ═══════════════════════════════════════
async function loadBrainState() {
  try {
    if (window.museon && window.museon.getBrainState) {
      const newState = await window.museon.getBrainState();
      // 比對 JSON 避免無變化時重繪
      const changed = JSON.stringify(newState) !== JSON.stringify(state.brainState);
      state.brainState = newState;
      if (changed && !state.showSetupWizard) render();
    }
  } catch (err) {
    console.error('Failed to load brain state:', err);
  }
}

async function loadEvolutionData() {
  try {
    if (window.museon && window.museon.getEvolutionData) {
      const newData = await window.museon.getEvolutionData();
      const changed = JSON.stringify(newData) !== JSON.stringify(state.evolutionData);
      state.evolutionData = newData;
      if (changed && state.activeTab === 'evolution') render();
    }
  } catch (err) {
    console.error('Failed to load evolution data:', err);
  }
}

async function loadActivityRecent() {
  try {
    if (window.museon && window.museon.getActivityRecent) {
      const result = await window.museon.getActivityRecent();
      state.activityRecent = result.events || [];
      if (state.activeTab === 'evolution') render();
    }
  } catch (err) {
    console.error('Failed to load activity log:', err);
  }
}

async function loadDailySummaries() {
  try {
    if (window.museon && window.museon.getDailySummaries) {
      const result = await window.museon.getDailySummaries();
      state.dailySummaryDates = result.dates || [];
      // Auto-load today's summary
      if (state.dailySummaryDates.length > 0) {
        const latestDate = state.dailySummaryDates[0];
        if (!state.dailySummaryDate) state.dailySummaryDate = latestDate;
        await loadDailySummary(state.dailySummaryDate);
      }
    }
  } catch (err) {
    console.error('Failed to load daily summaries:', err);
  }
}

async function loadDailySummary(date) {
  try {
    if (window.museon && window.museon.getDailySummary) {
      state.dailySummaryDate = date;
      state.dailySummary = await window.museon.getDailySummary(date);
      if (state.activeTab === 'evolution') render();
    }
  } catch (err) {
    console.error('Failed to load daily summary:', err);
  }
}

async function loadMemoryDates() {
  try {
    if (window.museon && window.museon.getMemoryDates) {
      const result = await window.museon.getMemoryDates();
      state.memoryDates = (result.dates || []).sort().reverse();
      if (state.memoryDates.length > 0 && !state.selectedMemoryDate) {
        state.selectedMemoryDate = state.memoryDates[0];
      }
    }
  } catch (err) {
    console.error('Failed to load memory dates:', err);
  }
  // 自動載入日誌 + overview
  if (state.selectedMemoryDate) {
    await loadJournalEntries(state.selectedMemoryDate);
  }
  loadMemoryOverview(); // fire-and-forget
}

async function loadJournalEntries(date) {
  state.memoryLoading = true;
  render();
  try {
    if (window.museon && window.museon.readMemoryMerged) {
      const result = await window.museon.readMemoryMerged(date);
      state.memoryJournalBlocks = result.blocks || [];
    }
  } catch (err) {
    console.error('Failed to load journal entries:', err);
    state.memoryJournalBlocks = [];
  }
  state.memoryLoading = false;
  render();
}

async function performMemorySearch(query) {
  state.memorySearchLoading = true;
  render();
  try {
    if (window.museon && window.museon.searchMemory) {
      const result = await window.museon.searchMemory(query);
      state.memorySearchResults = result.results || [];
    }
  } catch (err) {
    console.error('Failed to search memory:', err);
    state.memorySearchResults = [];
  }
  state.memorySearchLoading = false;
  render();
}

async function loadMemoryOverview() {
  state.memoryOverviewLoading = true;
  try {
    if (window.museon && window.museon.getMemoryOverview) {
      state.memoryOverview = await window.museon.getMemoryOverview();
    }
  } catch (err) {
    console.error('Failed to load memory overview:', err);
  }
  state.memoryOverviewLoading = false;
  render();
}

// ═══════════════════════════════════════
// Auto-refresh & Manual Refresh
// ═══════════════════════════════════════
const AUTO_REFRESH_MS = 1800000; // 30 分鐘自動刷新（達達把拔指定）
const DOCTOR_REFRESH_MS = 3600000; // Doctor 專用：1 小時自動刷新
let lastDoctorAutoRefresh = 0; // 上次 Doctor 自動刷新時間戳

async function refreshActiveTab() {
  if (state.refreshing) return;
  state.refreshing = true;
  // 不在這裡 render() — 等數據載入完再一次性渲染，避免畫面閃爍
  try {
    switch (state.activeTab) {
      case 'secretary':
        await loadSecretaryData();
        break;
      case 'organism':
        await loadBrainState();
        break;
      case 'evolution':
        await loadEvolutionData();
        // Also load memory dates + activity for the merged Evolution tab
        await Promise.all([
          loadMemoryDates().catch(() => {}),
          loadActivityRecent().catch(() => {}),
          loadDailySummaries().catch(() => {}),
        ]);
        break;
      case 'tools':
        await loadToolsState();
        if (!state.mcpCatalog) loadMCPCatalog();  // MCP 摘要用
        break;
      case 'doctor': {
        // Doctor 節流：自動刷新每小時一次（手動按鈕不受限）
        const now = Date.now();
        if (now - lastDoctorAutoRefresh >= DOCTOR_REFRESH_MS) {
          lastDoctorAutoRefresh = now;
          await loadDoctorReport();
          await loadGuardianStatus();
          await loadNightlyStatus();
        }
        break;
      }
      case 'settings':
        await loadTelegramStatus();
        await loadBudgetStats();
        await loadRoutingStats();
        await loadSavingsBreakdown();
        await loadMCPCatalog();
        await loadGatewayInfo();
        break;
      default:
        break;
    }
  } catch (err) {
    console.error('[MUSEON] refreshActiveTab error:', err);
  }
  state.refreshing = false;
  render();
}

function startAutoRefresh() {
  if (state._refreshTimer) clearInterval(state._refreshTimer);
  state._refreshTimer = setInterval(() => {
    // 只在非 wizard、非 loading 時自動刷新
    if (!state.showSetupWizard && !state.loading) {
      refreshActiveTab();
    }
  }, AUTO_REFRESH_MS);
}

// ═══════════════════════════════════════
// Post-render Hooks (Canvas initialization)
// ═══════════════════════════════════════
function afterRender() {
  if (state.activeTab === 'organism' && state.brainState) {
    requestAnimationFrame(() => initTopology());
  }
  // 演化頁已改用內建 SVG sparkline，不再需要 Chart.js
}

function initTopology() {
  const canvas = document.getElementById('topology-canvas');
  if (!canvas) return;
  try {
    // Support both new KnowledgeStarMap and legacy BrainTopology
    const TopoClass = (typeof KnowledgeStarMap !== 'undefined') ? KnowledgeStarMap
                     : (typeof BrainTopology !== 'undefined') ? BrainTopology : null;
    if (TopoClass) {
      // Destroy previous instance
      if (state.topology && state.topology.destroy) {
        state.topology.destroy();
      }
      state.topology = new TopoClass(canvas);
      const bs = state.brainState;
      state.topology.setData(bs.crystals || [], bs.crystalLinks || []);
    }
  } catch (err) {
    console.error('Failed to initialize KnowledgeStarMap:', err);
  }
}

function initCharts() {
  const ed = state.evolutionData;
  if (!ed) return;
  if (typeof Chart === 'undefined') {
    console.warn('Chart.js not loaded — skipping chart initialization');
    return;
  }

  // Destroy old charts
  Object.values(state.charts).forEach(c => {
    if (c && c.destroy) c.destroy();
  });
  state.charts = {};

  const darkGrid = { color: '#222d4a' };
  const darkTick = { color: '#9a8b70' };
  const defaultPlugins = { legend: { labels: { color: '#9a8b70' } } };
  const defaultScales = {
    x: { grid: darkGrid, ticks: darkTick },
    y: { grid: darkGrid, ticks: darkTick },
  };

  // 1. 表現評分 Trend
  const qCanvas = document.getElementById('chart-qscore');
  if (qCanvas) {
    const dailySummaries = ed.dailySummaries || [];
    const labels = dailySummaries.map(d => d.date);
    const data = dailySummaries.map(d => d.avg_q_score);
    state.charts.qscore = new Chart(qCanvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          label: '表現評分',
          data,
          borderColor: '#c9a96e',
          backgroundColor: 'rgba(201,169,110,0.1)',
          fill: true,
          tension: 0.3,
          pointRadius: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: defaultPlugins,
        scales: defaultScales,
        backgroundColor: 'transparent',
      },
    });
  }

  // 2. 知識累積
  const CRYSTAL_TYPE_ZH = { insight: '洞見', pattern: '模式', lesson: '經驗', hypothesis: '假說', other: '其他' };
  const cCanvas = document.getElementById('chart-crystals');
  if (cCanvas) {
    const crystals = ed.crystals || [];
    const typeColors = {
      insight: '#c9a96e', pattern: '#10b981',
      lesson: '#f59e0b', hypothesis: '#8b5cf6',
    };
    const typeCounts = {};
    crystals.forEach(c => {
      const t = (c.type || 'other').toLowerCase();
      typeCounts[t] = (typeCounts[t] || 0) + 1;
    });
    const typeLabels = Object.keys(typeCounts);
    const typeData = Object.values(typeCounts);
    const bgColors = typeLabels.map(t => typeColors[t] || '#6b5f4a');

    state.charts.crystals = new Chart(cCanvas, {
      type: 'bar',
      data: {
        labels: typeLabels.map(t => CRYSTAL_TYPE_ZH[t] || t),
        datasets: [{
          label: '結晶數',
          data: typeData,
          backgroundColor: bgColors,
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: defaultPlugins,
        scales: defaultScales,
        backgroundColor: 'transparent',
      },
    });
  }

  // 3. 成長里程碑時間軸
  const RING_TYPE_ZH = { breakthrough: '突破', milestone: '里程碑', lesson: '教訓', value_calibration: '校準' };
  const srCanvas = document.getElementById('chart-soulrings');
  if (srCanvas) {
    const soulRings = ed.soulRings || [];
    const typeMap = { breakthrough: 0, milestone: 1, lesson: 2, value_calibration: 3 };
    const typeColorMap = {
      breakthrough: '#c9a96e', milestone: '#10b981',
      lesson: '#f59e0b', value_calibration: '#8b5cf6',
    };
    const datasets = {};
    soulRings.forEach(sr => {
      const t = sr.type || 'breakthrough';
      if (!datasets[t]) {
        datasets[t] = {
          label: RING_TYPE_ZH[t] || t,
          data: [],
          backgroundColor: typeColorMap[t] || '#6b5f4a',
          pointRadius: [],
        };
      }
      datasets[t].data.push({
        x: sr.date || sr.created_at || '',
        y: typeMap[t] != null ? typeMap[t] : 0,
      });
      datasets[t].pointRadius.push(Math.min(3 + (sr.reinforcement_count || 0) * 2, 15));
    });

    state.charts.soulrings = new Chart(srCanvas, {
      type: 'scatter',
      data: { datasets: Object.values(datasets) },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: defaultPlugins,
        scales: {
          x: { type: 'category', grid: darkGrid, ticks: darkTick },
          y: {
            grid: darkGrid,
            ticks: {
              ...darkTick,
              callback: (v) => ['突破', '里程碑', '教訓', '校準'][v] || '',
              stepSize: 1,
            },
            min: -0.5,
            max: 3.5,
          },
        },
        backgroundColor: 'transparent',
      },
    });
  }

  // 4. 技能使用分佈
  const skCanvas = document.getElementById('chart-skills');
  if (skCanvas) {
    const dailySummaries = ed.dailySummaries || [];
    const skillAgg = {};
    dailySummaries.forEach(d => {
      const usage = d.skill_usage || {};
      Object.entries(usage).forEach(([skill, count]) => {
        skillAgg[skill] = (skillAgg[skill] || 0) + count;
      });
    });
    const sorted = Object.entries(skillAgg).sort((a, b) => b[1] - a[1]).slice(0, 10);

    state.charts.skills = new Chart(skCanvas, {
      type: 'bar',
      data: {
        labels: sorted.map(s => s[0]),
        datasets: [{
          label: '使用次數',
          data: sorted.map(s => s[1]),
          backgroundColor: '#c9a96e',
          borderRadius: 4,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: defaultPlugins,
        scales: {
          x: { grid: darkGrid, ticks: darkTick },
          y: { grid: darkGrid, ticks: darkTick },
        },
        backgroundColor: 'transparent',
      },
    });
  }
}

// ═══════════════════════════════════════
// ═══════════════════════════════════════
// Initialization
// ═══════════════════════════════════════

/** L2: 超時保護 — 如果 IPC 卡住，10 秒後強制脫離 loading */
const INIT_TIMEOUT_MS = 10000;

async function init() {
  render(); // Show loading

  // L2: 超時計時器（不覆蓋 wizard 狀態，只脫離 loading）
  let initDone = false;
  const timeoutId = setTimeout(() => {
    if (!initDone) {
      console.warn('[MUSEON L2] init() timeout after ' + INIT_TIMEOUT_MS + 'ms — forcing render');
      state.loading = false;
      // 不強制關閉 wizard — 如果已偵測到 firstRun，保持 wizard 開啟
      render();
    }
  }, INIT_TIMEOUT_MS);

  try {
    // 檢查 preload bridge 是否可用
    if (typeof window.museon === 'undefined' || !window.museon) {
      console.warn('[MUSEON] window.museon not available — preload may have failed');
      state.showSetupWizard = false;
    } else {
      try {
        // ── 安裝模式偵測 ──
        const installMode = await window.museon.checkInstallMode();
        state.installMode = installMode;

        if (installMode.mode === 'fresh') {
          // 全新安裝 → 直接進 wizard
          state.showSetupWizard = true;
          state.showModeSelector = false;
        } else if (installMode.mode === 'upgrade') {
          // 新版本 → 顯示模式選擇器
          state.showModeSelector = true;
          state.showSetupWizard = false;
        } else {
          // 正常啟動 → 檢查 .env 是否完整
          const isFirstRun = await window.museon.isFirstRun();
          state.showSetupWizard = isFirstRun;
          state.showModeSelector = false;
          // 蓋章確保 marker 同步
          window.museon.stampLaunchedVersion().catch(() => {});
        }
      } catch (err) {
        console.error('Failed to check install mode:', err);
        // Fallback 到舊邏輯
        try {
          const isFirstRun = await window.museon.isFirstRun();
          state.showSetupWizard = isFirstRun;
        } catch (e2) {
          state.showSetupWizard = false;
        }
        state.showModeSelector = false;
      }
    }
  } catch (err) {
    console.error('[MUSEON] init() outer error:', err);
    state.showSetupWizard = false;
    state.showModeSelector = false;
  }

  initDone = true;
  clearTimeout(timeoutId);
  state.loading = false;

  // Mode preference removed

  render();

  // Listen for gateway health updates
  try {
    if (window.museon && window.museon.onGatewayHealth) {
      window.museon.onGatewayHealth((data) => {
        const changed = state.gatewayOnline !== data.online;
        state.gatewayOnline = data.online;
        // 只在狀態實際改變時才重繪 — 防止每 30 秒跳動
        if (changed && !state.showSetupWizard) render();
      });
    }
  } catch (err) {
    console.error('Gateway health listener error:', err);
  }

  // Listen for Gateway log output (real-time from process stdout/stderr)
  try {
    if (window.museon && window.museon.onGatewayLog) {
      window.museon.onGatewayLog((data) => {
        addGatewayLog(data.level || 'info', data.message);
        // Auto-render only if panel is open
        if (state.showGatewayPanel) render();
      });
    }
  } catch (err) {
    console.error('Gateway log listener error:', err);
  }

  // 只在正常啟動（非 wizard / 非 mode selector）時載入資料
  if (!state.showSetupWizard && !state.showModeSelector) {
    loadBrainState();
    loadMemoryDates();
    startAutoRefresh();
  }
}

// Start!
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
