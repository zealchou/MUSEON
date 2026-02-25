/**
 * MuseClaw Dashboard - Electron Main Process
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
const net = require('net');
const fs = require('fs');

// Configuration
const IPC_SOCKET_PATH = process.env.MUSECLAW_IPC_SOCKET || '/tmp/museclaw.sock';
const GATEWAY_CHECK_INTERVAL = 30000; // 30 seconds
const AUTO_LAUNCH_KEY = 'museclaw-dashboard-autolaunch';

let mainWindow = null;
let tray = null;
let gatewaySocket = null;
let watchdogInterval = null;

/**
 * Create the main dashboard window
 */
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    icon: path.join(__dirname, 'assets', 'icon.png'),
    title: 'MuseClaw Dashboard'
  });

  mainWindow.loadFile(path.join(__dirname, 'src', 'index.html'));

  // Open DevTools in development mode
  if (process.argv.includes('--dev')) {
    mainWindow.webContents.openDevTools();
  }

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
      label: 'Quit MuseClaw',
      click: () => {
        app.isQuitting = true;
        app.quit();
      }
    }
  ]);

  tray.setToolTip('MuseClaw Dashboard');
  tray.setContextMenu(contextMenu);

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
 * Connect to Python Gateway via Unix socket
 */
async function connectToGateway() {
  return new Promise((resolve, reject) => {
    // Check if socket file exists
    if (!fs.existsSync(IPC_SOCKET_PATH)) {
      reject(new Error('Gateway socket not found'));
      return;
    }

    gatewaySocket = net.createConnection(IPC_SOCKET_PATH, () => {
      console.log('Connected to Gateway');
      resolve();
    });

    gatewaySocket.on('error', (err) => {
      console.error('Gateway connection error:', err);
      gatewaySocket = null;
      reject(err);
    });

    gatewaySocket.on('close', () => {
      console.log('Gateway connection closed');
      gatewaySocket = null;
    });

    gatewaySocket.on('data', (data) => {
      handleGatewayMessage(data);
    });
  });
}

/**
 * Handle messages from Gateway
 */
function handleGatewayMessage(data) {
  try {
    // Parse length-prefixed message
    const messageLength = data.readUInt32BE(0);
    const messageData = data.slice(4, 4 + messageLength);
    const message = JSON.parse(messageData.toString('utf-8'));

    // Send to renderer process
    if (mainWindow) {
      mainWindow.webContents.send('gateway-message', message);
    }
  } catch (err) {
    console.error('Error parsing gateway message:', err);
  }
}

/**
 * Send message to Gateway
 */
function sendToGateway(message) {
  if (!gatewaySocket || gatewaySocket.destroyed) {
    console.error('Gateway not connected');
    return false;
  }

  try {
    const messageData = JSON.stringify(message);
    const messageBuffer = Buffer.from(messageData, 'utf-8');
    const lengthBuffer = Buffer.allocUnsafe(4);
    lengthBuffer.writeUInt32BE(messageBuffer.length, 0);

    gatewaySocket.write(Buffer.concat([lengthBuffer, messageBuffer]));
    return true;
  } catch (err) {
    console.error('Error sending to gateway:', err);
    return false;
  }
}

/**
 * Watchdog mechanism - monitor Gateway health
 */
function startWatchdog() {
  watchdogInterval = setInterval(async () => {
    try {
      // Try to reconnect if disconnected
      if (!gatewaySocket || gatewaySocket.destroyed) {
        await connectToGateway();
      }

      // Send health check
      const healthCheck = {
        user_id: 'electron_dashboard',
        content: '/health',
        timestamp: new Date().toISOString()
      };

      const success = sendToGateway(healthCheck);

      // Update tray status
      if (tray) {
        const menu = tray.getContextMenu();
        const statusItem = menu.getMenuItemById('gateway-status');
        if (statusItem) {
          statusItem.label = success ? 'Gateway: Online ✓' : 'Gateway: Offline ✗';
          statusItem.enabled = false;
        }
      }

      // Notify renderer
      if (mainWindow) {
        mainWindow.webContents.send('gateway-health', { online: success });
      }

    } catch (err) {
      console.error('Watchdog error:', err);

      // Update status to offline
      if (tray) {
        const menu = tray.getContextMenu();
        const statusItem = menu.getMenuItemById('gateway-status');
        if (statusItem) {
          statusItem.label = 'Gateway: Offline ✗';
          statusItem.enabled = false;
        }
      }

      if (mainWindow) {
        mainWindow.webContents.send('gateway-health', { online: false });
      }
    }
  }, GATEWAY_CHECK_INTERVAL);
}

/**
 * Handle IPC messages from renderer
 */
ipcMain.handle('query-gateway', async (event, query) => {
  return new Promise((resolve, reject) => {
    if (!gatewaySocket || gatewaySocket.destroyed) {
      reject(new Error('Gateway not connected'));
      return;
    }

    // Send query
    const success = sendToGateway({
      user_id: 'electron_dashboard',
      content: query,
      timestamp: new Date().toISOString()
    });

    if (!success) {
      reject(new Error('Failed to send query'));
      return;
    }

    // Wait for response (with timeout)
    const timeout = setTimeout(() => {
      reject(new Error('Query timeout'));
    }, 5000);

    // Listen for response
    const responseHandler = (data) => {
      clearTimeout(timeout);
      gatewaySocket.off('data', responseHandler);

      try {
        const messageLength = data.readUInt32BE(0);
        const messageData = data.slice(4, 4 + messageLength);
        const message = JSON.parse(messageData.toString('utf-8'));
        resolve(message);
      } catch (err) {
        reject(err);
      }
    };

    gatewaySocket.once('data', responseHandler);
  });
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

// App lifecycle
app.whenReady().then(async () => {
  createWindow();
  createTray();

  // Try to connect to Gateway
  try {
    await connectToGateway();
    console.log('Successfully connected to Gateway');
  } catch (err) {
    console.error('Failed to connect to Gateway:', err);
  }

  // Start watchdog
  startWatchdog();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
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

  if (gatewaySocket) {
    gatewaySocket.destroy();
  }
});
