# DSE #1: Electron+Python Desktop App Integration Patterns

**Date**: 2026-02-26
**Trigger**: Gateway connectivity failed 4 times despite multiple fix attempts (ASAR paths, PYTHONPATH, auto-spawn, getDataDir). User requested: "問題依然沒解決，擴大研究的範圍。DSE 網路上其他人怎麼做到的"

---

## Research Targets

| Project | Stack | Communication | Python Bundling |
|---------|-------|---------------|-----------------|
| JupyterLab Desktop | Electron + Python | **HTTP polling** | conda bundling |
| Datasette Desktop | Electron + Python | **HTTP** | python-build-standalone + `extraResources` |
| Jan.ai | Electron + local LLM | HTTP REST API | N/A (C++ backend) |
| Modern consensus | Electron + FastAPI | **HTTP is the standard** | `process.resourcesPath` + `extraResources` |

## Key Findings

### 1. HTTP Polling is the Industry Standard

Every successful Electron+Python desktop app uses HTTP for IPC:
- FastAPI/uvicorn on a localhost port
- Health check via `GET /health`
- Polling with exponential backoff on startup

**Nobody uses Unix Sockets** for Electron-Python communication.

### 2. ASAR Path Resolution

- `process.resourcesPath` + `extraResources` avoids ASAR path issues entirely
- JupyterLab Desktop uses this pattern for the Python environment
- The `__dirname` walk-up approach is fragile inside ASAR bundles

### 3. Python Bundling Strategies

| Strategy | Pros | Cons |
|----------|------|------|
| `python-build-standalone` | Self-contained, no system dependency | Large bundle size |
| conda | Reproducible environments | Requires conda installer |
| System Python + venv | Smallest bundle | Depends on user's Python |

MUSEON uses Strategy 3 (system Python + venv), which is appropriate for a developer-oriented tool.

## Root Cause Discovery

**The fundamental bug**: Electron `main.js` used **Unix Socket** (`/tmp/museon.sock`) for Gateway communication and Watchdog health checks. But Gateway `server.py` is a **FastAPI HTTP server** on port 8765 — it NEVER creates a Unix socket. The socket file never exists, so Watchdog always reports offline.

All 4 previous fix attempts addressed the wrong problem:
- Fix #1: ASAR path resolution → Wrong problem
- Fix #2: PYTHONPATH in spawn → Wrong problem
- Fix #3: Auto-spawn Gateway → Wrong problem
- Fix #4: getDataDir fallback chain → Wrong problem

## Action Taken

Complete rewrite of `electron/main.js`:
- Removed: `net` module, `IPC_SOCKET_PATH`, `gatewaySocket`, `connectToGateway()`, `sendToGateway()`
- Added: `http` module, `checkGatewayHealth()`, `waitForGatewayReady(maxWaitMs)`, HTTP-based Watchdog
- All communication now uses HTTP (GET /health, POST /webhook, etc.)

**Status**: Landed and verified. Gateway connectivity working.
