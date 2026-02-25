/**
 * Health Component
 *
 * Features:
 * - Gateway daemon status
 * - System health metrics
 * - Recent activity log
 * - Connection diagnostics
 */

import React, { useState, useEffect } from 'react';

const Health = () => {
  const [health, setHealth] = useState(null);
  const [gatewayOnline, setGatewayOnline] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadHealth();

    // Listen for gateway health updates from main process
    window.museclaw.onGatewayHealth((data) => {
      setGatewayOnline(data.online);
    });

    // Refresh every 10 seconds
    const interval = setInterval(loadHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  const loadHealth = async () => {
    try {
      const response = await window.museclaw.queryGateway('/health');
      setHealth(response);
      setGatewayOnline(true);
      setLoading(false);
    } catch (err) {
      console.error('Failed to load health:', err);
      setGatewayOnline(false);
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner"></div>
        <p>Checking system health...</p>
      </div>
    );
  }

  const formatUptime = (seconds) => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    if (days > 0) return `${days}d ${hours}h ${minutes}m`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'healthy':
        return '#10b981';
      case 'warning':
        return '#f59e0b';
      case 'error':
        return '#ef4444';
      default:
        return '#94a3b8';
    }
  };

  return (
    <div className="content">
      <div className="dashboard">
        {/* Gateway Status */}
        <div className="card" style={{ gridColumn: '1 / -1' }}>
          <h2 className="card-title">Gateway Daemon Status</h2>
          <div className="stat-grid">
            <div className="stat-item">
              <div className="stat-label">Connection Status</div>
              <div
                className="stat-value"
                style={{ color: gatewayOnline ? '#10b981' : '#ef4444' }}
              >
                {gatewayOnline ? 'Online ✓' : 'Offline ✗'}
              </div>
            </div>
            {health && (
              <>
                <div className="stat-item">
                  <div className="stat-label">Uptime</div>
                  <div className="stat-value">
                    {formatUptime(health.uptime)}
                  </div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Active Sessions</div>
                  <div className="stat-value">{health.activeSessions || 0}</div>
                </div>
                <div className="stat-item">
                  <div className="stat-label">Messages Processed</div>
                  <div className="stat-value">
                    {(health.messagesProcessed || 0).toLocaleString()}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* System Health */}
        {health && health.components && (
          <div className="card" style={{ gridColumn: 'span 2' }}>
            <h2 className="card-title">System Components</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>Component</th>
                  <th>Status</th>
                  <th>Last Check</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {health.components.map((component, idx) => (
                  <tr key={idx}>
                    <td>{component.name}</td>
                    <td>
                      <span
                        style={{
                          color: getStatusColor(component.status),
                          fontWeight: 600
                        }}
                      >
                        {component.status.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
                      {new Date(component.lastCheck).toLocaleTimeString()}
                    </td>
                    <td style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
                      {component.details || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Memory Usage */}
        {health && health.memory && (
          <div className="card">
            <h2 className="card-title">Memory Usage</h2>
            <div className="stat-item">
              <div className="stat-label">Used / Total</div>
              <div className="stat-value">
                {(health.memory.used / 1024 / 1024).toFixed(0)}MB
              </div>
              <div className="progress-bar">
                <div
                  className={`progress-fill ${
                    health.memory.percentage > 80 ? 'warning' : ''
                  }`}
                  style={{ width: `${health.memory.percentage}%` }}
                ></div>
              </div>
              <div className="stat-label">
                {health.memory.percentage.toFixed(1)}% of{' '}
                {(health.memory.total / 1024 / 1024).toFixed(0)}MB
              </div>
            </div>
          </div>
        )}

        {/* Recent Activity */}
        {health && health.recentActivity && (
          <div className="card" style={{ gridColumn: '1 / -1' }}>
            <h2 className="card-title">Recent Activity</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Event</th>
                  <th>Source</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {health.recentActivity.map((activity, idx) => (
                  <tr key={idx}>
                    <td style={{ fontSize: '0.875rem', color: '#94a3b8' }}>
                      {new Date(activity.timestamp).toLocaleString()}
                    </td>
                    <td>{activity.event}</td>
                    <td style={{ color: '#94a3b8' }}>{activity.source}</td>
                    <td>
                      <span
                        style={{
                          color: activity.success ? '#10b981' : '#ef4444'
                        }}
                      >
                        {activity.success ? '✓' : '✗'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Connection Diagnostics */}
        {!gatewayOnline && (
          <div className="card" style={{ gridColumn: '1 / -1' }}>
            <h2 className="card-title">Connection Diagnostics</h2>
            <div className="error">
              <strong>Gateway is offline</strong>
              <p style={{ marginTop: '0.5rem' }}>
                Unable to connect to MuseClaw Gateway daemon.
              </p>
              <p style={{ marginTop: '0.5rem' }}>Possible causes:</p>
              <ul style={{ marginLeft: '1.5rem', marginTop: '0.5rem' }}>
                <li>Gateway daemon is not running</li>
                <li>IPC socket path is incorrect</li>
                <li>Permission issues</li>
              </ul>
              <p style={{ marginTop: '1rem' }}>
                Try restarting the Gateway daemon or check the logs.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Health;
