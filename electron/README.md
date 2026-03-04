# MUSEON Dashboard

Real-time monitoring and control panel for MUSEON.

## Features

- **Token Dashboard**: Real-time token consumption tracking
  - Today's usage and cost
  - Monthly cumulative stats
  - 30-day trend chart
  - Model distribution (Haiku vs Sonnet)
  - Top 5 token-consuming scenarios
  - Optimization history

- **Health Monitor**: Gateway daemon status
  - Connection status
  - System uptime
  - Active sessions
  - Component health
  - Recent activity log

- **Settings**: Configuration and preferences
  - Auto-launch on startup
  - Token budget settings
  - Notification preferences

- **Watchdog**: Automatic Gateway monitoring
  - 30-second health checks
  - Auto-reconnect on disconnect
  - System tray status indicator

## Installation

```bash
cd electron
npm install
```

## Development

```bash
# Run in development mode (with DevTools)
npm run dev

# Build for production
npm run build

# Package as DMG/AppImage/NSIS
npm run pack
```

## IPC Communication

The Dashboard communicates with the Python Gateway via Unix socket:
- Default socket: `/tmp/museon.sock`
- Length-prefixed JSON messages
- Bidirectional communication

## Requirements

- Node.js 18+
- Electron 28+
- React 18+
- Chart.js 4+

## Architecture

```
electron/
├── main.js              # Main process (IPC, watchdog, tray)
├── preload.js           # Preload script (safe IPC bridge)
├── package.json         # Dependencies and build config
└── src/
    ├── index.html       # HTML shell
    ├── styles.css       # Global styles
    ├── app.js           # React entry point
    ├── App.jsx          # Main app component
    └── components/
        ├── Dashboard.jsx # Token dashboard
        ├── Health.jsx    # Health monitor
        └── Settings.jsx  # Settings panel
```

## Auto-Launch

The Dashboard can be configured to launch automatically on system startup via Settings.

## System Tray

The Dashboard minimizes to the system tray instead of closing. Click the tray icon to show/hide the window.

## Troubleshooting

**Gateway Offline**
- Check that the Gateway daemon is running
- Verify IPC socket path in settings
- Check file permissions on `/tmp/museon.sock`

**Charts Not Displaying**
- Ensure Gateway is online
- Check browser console for errors
- Verify token data is being returned

## License

MIT
