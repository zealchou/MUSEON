/**
 * MuseClaw Dashboard - Electron Preload Script
 *
 * Exposes safe IPC communication to renderer process
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('museclaw', {
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
   * Get auto-launch setting
   * @returns {Promise<boolean>} Auto-launch enabled
   */
  getAutoLaunch: () => ipcRenderer.invoke('get-auto-launch'),

  /**
   * Set auto-launch setting
   * @param {boolean} enable - Enable auto-launch
   * @returns {Promise<boolean>} Success
   */
  setAutoLaunch: (enable) => ipcRenderer.invoke('set-auto-launch', enable)
});
