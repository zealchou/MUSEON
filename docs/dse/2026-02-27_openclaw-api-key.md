# DSE #3: OpenClaw API Key Management

**Date**: 2026-02-27
**Trigger**: Telegram bot returned offline mode due to API key chain-of-custody bug. User requested DSE on how OpenClaw handles API key lifecycle.

---

## OpenClaw Overview

- GitHub: openclaw/openclaw (215K+ stars as of 2026-02)
- Open-source personal AI assistant
- Supports: Anthropic, OpenAI, OpenRouter, Google Gemini, Groq, Mistral

---

## 1. Key Storage

| Method | Description | Security Level |
|--------|------------|----------------|
| Default | Plaintext in `~/.openclaw/openclaw.json` | Low |
| Env vars | `${VAR}` syntax in config, actual values in `.env` | Medium |
| AES-256 | `openclaw onboard` stores to `credentials.enc` | High |
| OS Keychain | Proposed (Discussion #6248), not yet merged | Highest |

**Resolution priority**: process env > local .env > ~/.openclaw/.env > config file

### Known vulnerability (Issue #11202)
API keys in config get serialized into LLM request payloads, exposing all provider keys to the current LLM provider. Using `${VAR}` syntax does NOT mitigate this.

---

## 2. Key Validation

| Method | When | What |
|--------|------|------|
| Format check | On input | `sk-ant-api03-` prefix, length >= 20 |
| Live API test | `openclaw onboard` | Real API call to verify |
| Status check | `openclaw models status` | Batch verify all providers |
| Health check | `openclaw health` | Full connectivity check |
| Auto-repair | `openclaw doctor --fix` | Detect and fix config issues |

**Cooldown**: After consecutive auth failures, 30-60 min cooldown before retrying that provider.

---

## 3. Key Rotation / Updates

| Feature | Description |
|---------|------------|
| Hot reload | Gateway monitors `openclaw.json` for changes, auto-applies most fields |
| RPC update | `config.patch` RPC for live update without full restart |
| Rate limiting | 3 writes per 60s per deviceId+clientIp |
| Auth Profile rotation | Auto-switch between profiles on rate limit hit |
| Multi-key | Most providers support multiple active keys for zero-downtime rotation |
| Recommended cycle | Every 90 days |

### Zero-downtime rotation SOP:
1. Generate new key at provider console
2. Update OpenClaw config
3. Verify new key works
4. Revoke old key

---

## 4. Usage Tracking

| Tool | Type | Features |
|------|------|----------|
| `/status` (in-chat) | Built-in | Session token usage + estimated cost |
| `/usage tokens` | Built-in | Per-response token count |
| `openclaw status --usage` | CLI | Per-provider usage breakdown |
| openclaw-dashboard | Community | Real-time monitoring, TOTP auth, SSE streaming |
| ClawMetry | Community | Token I/O, cache hits, response time, per-call cost |
| OpenTelemetry | Built-in | Traces, metrics, logs via OTLP export |

---

## 5. Security Best Practices

| Practice | Implementation |
|----------|---------------|
| Key masking | `openclaw secrets list` shows masked values |
| File permissions | `chmod 700` for dirs, `chmod 600` for files |
| Memory-only | Keys exist in memory only during request, not in logs or agent memory |
| Gateway binding | `127.0.0.1` only (localhost) |
| SSRF prevention | Built-in domain whitelist |

### Critical vulnerabilities found:
- **Issue #11202**: Key leaks into LLM context (unresolved as of 2026-02)
- **CVE-2026-25253**: WebSocket hijack RCE when gateway exposed to internet (patched in 2026.1.29)

### Community proposals:
- **Agent-Blind Architecture** (#9676): Keys never visible to agent, Credential Broker injects at request time
- **OS Keychain** (#6248): `$KEYCHAIN:secret-name` syntax, resolved at startup via `security find-generic-password`

---

## Recommendations for MUSEON

### Already implemented (matches OpenClaw):
- Live API test on key input (Setup Wizard)
- Gateway binds to 127.0.0.1 only
- API key never enters LLM context/system prompt (confirmed in audit)
- Model fallback chain (Sonnet -> Haiku -> offline)

### Gaps to close:

| Priority | Gap | Effort |
|----------|-----|--------|
| HIGH | Key update requires Gateway restart (no hot reload) | Fixed (setup-complete auto-restart) |
| HIGH | `_parse_env` blocked key updates | Fixed (SYSTEM_VARS whitelist) |
| HIGH | spawnGateway forwarded stale keys | Fixed (cleanEnv) |
| MEDIUM | BudgetMonitor exists but unwired | Easy (3 lines) |
| MEDIUM | InputSanitizer exists but unwired | Easy (~15 lines) |
| MEDIUM | AuditLogger file write commented out | Easy |
| LOW | Renderer keeps key in memory after save | Easy (1 line) |
| FUTURE | macOS Keychain integration | Hard |
| FUTURE | Per-request cost persistence (SQLite) | Hard |
