/**
 * MuseClaw Dashboard - Main App Component
 */

import React, { useState, useEffect } from 'react';
import Dashboard from './components/Dashboard';
import Settings from './components/Settings';
import Health from './components/Health';

const App = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [gatewayOnline, setGatewayOnline] = useState(false);

  useEffect(() => {
    // Listen for gateway health updates
    window.museclaw.onGatewayHealth((data) => {
      setGatewayOnline(data.online);
    });
  }, []);

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <Dashboard />;
      case 'health':
        return <Health />;
      case 'settings':
        return <Settings />;
      default:
        return <Dashboard />;
    }
  };

  return (
    <div id="app">
      <nav className="nav">
        <div className="nav-title">MuseClaw Dashboard</div>
        <div className="nav-tabs">
          <button
            className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveTab('dashboard')}
          >
            Dashboard
          </button>
          <button
            className={`nav-tab ${activeTab === 'health' ? 'active' : ''}`}
            onClick={() => setActiveTab('health')}
          >
            Health
          </button>
          <button
            className={`nav-tab ${activeTab === 'settings' ? 'active' : ''}`}
            onClick={() => setActiveTab('settings')}
          >
            Settings
          </button>
        </div>
        <div className="status-indicator">
          <div className={`status-dot ${gatewayOnline ? '' : 'offline'}`}></div>
          <span>{gatewayOnline ? 'Gateway Online' : 'Gateway Offline'}</span>
        </div>
      </nav>
      <div className="content">{renderContent()}</div>
    </div>
  );
};

export default App;
