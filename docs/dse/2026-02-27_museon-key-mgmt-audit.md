# MUSEON Key Management & Security Audit

**Date**: 2026-02-27
**Context**: Supplementary to OpenClaw DSE. Internal audit of MUSEON's current credential management architecture.

---

## Current Architecture

```
User types key in Setup Wizard (renderer)
  ↓ IPC (plaintext string)
main.js: writeEnvKey() → fs.writeFileSync(.env)
  ↓ Gateway restart (setup-complete)
server.py: _parse_env() → os.environ["ANTHROPIC_API_KEY"]
  ↓
brain.py: _call_llm() → os.environ.get("ANTHROPIC_API_KEY")
  ↓ Anthropic SDK
AsyncAnthropic(api_key=key).messages.create(...)
```

## .env Resolution Chain

```
Priority (high to low):
1. $MUSEON_HOME/.env
2. Walk up from __file__ → find pyproject.toml → .env beside it
   (special: if inside .runtime/, go one level up)
3. ~/MUSEON/.env (fallback)
```

## Bugs Found & Fixed (2026-02-27)

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| Key updates not applied | `_parse_env()` had `if key not in os.environ` guard blocking API key overwrites | Changed to SYSTEM_VARS whitelist (only PATH/PYTHONPATH/MUSEON_HOME protected) |
| Stale keys forwarded | `spawnGateway()` passed `...process.env` including old API keys | Added `cleanEnv` that deletes ANTHROPIC_API_KEY and TELEGRAM_BOT_TOKEN before spawn |
| No auto-restart on key change | `setup-complete` didn't restart Gateway | Added gatewayNeedsRestart flag + auto Gateway restart in setup-complete |

## Existing Modules (Unwired)

### BudgetMonitor (`src/museon/llm/budget.py`)
- `daily_limit = 200,000` tokens
- `warning_threshold = 0.8` (80%)
- `track_usage(input_tokens, output_tokens)`
- `check_budget(required_tokens)` — pre-flight check
- `get_usage_stats()` → `{daily_limit, used, remaining, percentage, should_warn}`
- **Status**: Complete class, NOT called by brain.py

### InputSanitizer (`src/museon/security/sanitizer.py`)
- Prompt injection detection (regex patterns)
- Role-playing attack detection
- XML tag injection detection
- Instruction keyword detection
- **Status**: Complete, NOT called by brain.py (brain uses SafetyAnchor only)

### AuditLogger (`src/museon/security/audit.py`)
- In-memory SHA-256 hash chain
- Immutability verification
- File write: **commented out** (`# Would also write to file in production`)
- **Status**: Partially complete, no file persistence

### Security Module Overview (`src/museon/security/`)

| File | Layer | Wired to brain.py? |
|------|-------|-------------------|
| `sanitizer.py` | L2 Input | No |
| `sandbox.py` | L3 Execution | No |
| `guardrails.py` | L4 Behavior | No |
| `trust.py` | Trust hierarchy | No |
| `audit.py` | L6 Audit | No |

**Critical gap**: The entire `security/` module is well-designed but completely disconnected from `brain.py`. Only `SafetyAnchor` (from `agent/safety_anchor.py`) is wired in.

## Dashboard Settings Tab

- Token Budget section: **hardcoded** `300,000 tokens / 80%`
- No API to read real usage data
- No Gateway endpoint for budget stats
- Setup Wizard: fully functional 5-step flow

## Key Security Properties (Confirmed Good)

1. API key never enters system prompt or messages (verified in brain.py)
2. Gateway binds to 127.0.0.1 only
3. .env file permissions: 600 (owner read/write only)
4. Setup Wizard validates key format before save
5. Setup Wizard live-tests key via API before completing
6. Model fallback chain: Sonnet -> Haiku -> offline CPU mode
