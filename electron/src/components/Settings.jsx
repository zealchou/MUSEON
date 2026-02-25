/**
 * Settings Component
 *
 * Features:
 * - Auto-launch configuration
 * - Token budget settings
 * - Gateway connection settings
 * - Notification preferences
 */

import React, { useState, useEffect } from 'react';

const Settings = () => {
  const [autoLaunch, setAutoLaunch] = useState(false);
  const [tokenBudget, setTokenBudget] = useState(300000);
  const [notifyBudget, setNotifyBudget] = useState(true);
  const [notifyOptimization, setNotifyOptimization] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const autoLaunchEnabled = await window.museclaw.getAutoLaunch();
      setAutoLaunch(autoLaunchEnabled);

      // Load other settings from Gateway
      const response = await window.museclaw.queryGateway('get settings');
      if (response && response.settings) {
        setTokenBudget(response.settings.tokenBudget || 300000);
        setNotifyBudget(response.settings.notifyBudget !== false);
        setNotifyOptimization(response.settings.notifyOptimization !== false);
      }
    } catch (err) {
      console.error('Failed to load settings:', err);
    }
  };

  const handleAutoLaunchToggle = async (enabled) => {
    try {
      await window.museclaw.setAutoLaunch(enabled);
      setAutoLaunch(enabled);
    } catch (err) {
      console.error('Failed to set auto-launch:', err);
    }
  };

  const handleSaveSettings = async () => {
    setSaving(true);
    try {
      await window.museclaw.queryGateway(
        `update settings ${JSON.stringify({
          tokenBudget,
          notifyBudget,
          notifyOptimization
        })}`
      );

      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      console.error('Failed to save settings:', err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="content">
      <div className="settings-section">
        <h2>Application Settings</h2>

        <div className="setting-item">
          <div className="setting-label">
            <div className="setting-title">Launch at Startup</div>
            <div className="setting-description">
              Automatically start MuseClaw Dashboard when you log in
            </div>
          </div>
          <label className="toggle">
            <input
              type="checkbox"
              checked={autoLaunch}
              onChange={(e) => handleAutoLaunchToggle(e.target.checked)}
            />
            <span className="toggle-slider"></span>
          </label>
        </div>
      </div>

      <div className="settings-section">
        <h2>Token Budget Settings</h2>

        <div className="setting-item">
          <div className="setting-label">
            <div className="setting-title">Daily Token Budget</div>
            <div className="setting-description">
              Maximum tokens allowed per day (default: 300,000)
            </div>
          </div>
          <input
            type="number"
            value={tokenBudget}
            onChange={(e) => setTokenBudget(parseInt(e.target.value))}
            min="10000"
            max="1000000"
            step="10000"
            style={{
              padding: '0.5rem',
              borderRadius: '0.5rem',
              border: '1px solid #334155',
              background: '#0f172a',
              color: '#e2e8f0',
              width: '150px'
            }}
          />
        </div>

        <div className="setting-item">
          <div className="setting-label">
            <div className="setting-title">Budget Warnings</div>
            <div className="setting-description">
              Notify when token usage exceeds 80% of budget
            </div>
          </div>
          <label className="toggle">
            <input
              type="checkbox"
              checked={notifyBudget}
              onChange={(e) => setNotifyBudget(e.target.checked)}
            />
            <span className="toggle-slider"></span>
          </label>
        </div>
      </div>

      <div className="settings-section">
        <h2>Notifications</h2>

        <div className="setting-item">
          <div className="setting-label">
            <div className="setting-title">Optimization Notifications</div>
            <div className="setting-description">
              Notify when MuseClaw performs token optimization
            </div>
          </div>
          <label className="toggle">
            <input
              type="checkbox"
              checked={notifyOptimization}
              onChange={(e) => setNotifyOptimization(e.target.checked)}
            />
            <span className="toggle-slider"></span>
          </label>
        </div>
      </div>

      <div style={{ marginTop: '2rem' }}>
        <button
          onClick={handleSaveSettings}
          disabled={saving}
          style={{
            padding: '0.75rem 2rem',
            background: saved ? '#10b981' : '#3b82f6',
            color: 'white',
            border: 'none',
            borderRadius: '0.5rem',
            cursor: 'pointer',
            fontSize: '1rem',
            fontWeight: 600,
            transition: 'all 0.2s'
          }}
        >
          {saving ? 'Saving...' : saved ? 'Saved ✓' : 'Save Settings'}
        </button>
      </div>

      <div className="settings-section" style={{ marginTop: '3rem' }}>
        <h2>About</h2>
        <div className="card">
          <p style={{ marginBottom: '0.5rem' }}>
            <strong>MuseClaw Dashboard</strong> v1.0.0
          </p>
          <p style={{ marginBottom: '0.5rem', color: '#94a3b8' }}>
            Real-time token usage monitoring and optimization
          </p>
          <p style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
            Gateway IPC: {process.env.MUSECLAW_IPC_SOCKET || '/tmp/museclaw.sock'}
          </p>
        </div>
      </div>
    </div>
  );
};

export default Settings;
