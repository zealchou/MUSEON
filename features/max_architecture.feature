Feature: MAX Architecture — Claude CLI Adapter & System Integration
  MUSEON MAX 架構全面驗證：
  涵蓋 ClaudeCLIAdapter、RateLimitGuard、Gateway E2E、MCP Server、
  Nightly Pipeline MAX 步驟、以及壓力韌性測試。

  Background:
    Given MUSEON is running with MAX subscription mode
    And the Gateway is healthy at http://127.0.0.1:8765

  # ─── A. ClaudeCLIAdapter ───────────────────────────────

  Scenario: Adapter correctly invokes claude -p
    When the ClaudeCLIAdapter sends a simple prompt "回答 OK"
    Then the response contains meaningful text
    And stop_reason is "end_turn"
    And model field is not empty

  Scenario: Adapter handles model mapping
    When the adapter is called with model "haiku"
    Then the subprocess uses "--model haiku"
    When the adapter is called with model "sonnet"
    Then the subprocess uses "--model sonnet"

  Scenario: Adapter fallback to API when CLI unavailable
    Given the claude CLI path is set to "/nonexistent/claude"
    When create_adapter() is called
    Then it falls back to AnthropicAPIAdapter
    And logs a warning message

  Scenario: Adapter handles timeout gracefully
    When the adapter processes a request exceeding 120 seconds
    Then it raises a timeout error
    And does not leave zombie subprocesses

  Scenario: Adapter tracks call statistics
    Given a fresh ClaudeCLIAdapter instance
    When 3 calls are made sequentially
    Then adapter stats call_count equals 3
    And total_duration_ms is positive

  # ─── B. RateLimitGuard（五級降級）────────────────────────

  Scenario: Guard starts at L0 with zero calls
    Given a fresh RateLimitGuard instance
    Then the level is 0
    And all priorities can proceed

  Scenario: Guard escalates through 5 levels correctly
    Given a RateLimitGuard with weekly_limit of 100
    When 59 calls are recorded
    Then the level is 0
    When 16 more calls are recorded (total 75)
    Then the level is 1
    And breath_multiplier is 2.0
    When 10 more calls are recorded (total 85)
    Then the level is 2
    And exploration priority is blocked
    When 10 more calls are recorded (total 95)
    Then the level is 3
    And nightly priority is blocked
    When 6 more calls are recorded (total 101)
    Then the level is 4
    And only human_interaction can proceed

  Scenario: Guard persists state across restarts
    Given 50 calls have been recorded
    When the RateLimitGuard is destroyed and recreated
    Then the weekly call count is still 50
    And the level is correct

  Scenario: Guard cleans up calls older than 7 days
    Given calls recorded 8 days ago
    When get_weekly_calls() is called
    Then old calls are excluded from the count

  Scenario: Guard breath multiplier reflects level
    Given the guard is at level 0
    Then breath_multiplier is 1.0
    Given the guard is at level 1
    Then breath_multiplier is 2.0

  # ─── C. Gateway 端對端（真實 LLM 呼叫）─────────────────

  Scenario: Simple conversation via Gateway
    When a message "你好" is sent to the Gateway
    Then the response is not an offline template
    And the response contains meaningful Chinese text
    And response time is under 30 seconds

  Scenario: Tool-use conversation via Gateway
    When a message "今天台北天氣如何？" is sent to the Gateway
    Then the Brain attempts to use search tools
    And the response references weather information

  Scenario: Concurrent requests do not crash Gateway
    When 3 messages are sent simultaneously to the Gateway
    Then all 3 responses are received
    And no response is a 500 error

  Scenario: Long conversation maintains context
    When message "記住數字 42" is sent
    And then message "我剛才說的數字是什麼？" is sent in the same session
    Then the response references "42"

  # ─── D. MCP Server ────────────────────────────────────

  Scenario: MCP initialize handshake
    When an "initialize" JSON-RPC message is sent
    Then the response contains protocolVersion "2024-11-05"
    And serverInfo name is "museon-gateway"

  Scenario: MCP tools/list returns all 7 tools
    When a "tools/list" JSON-RPC message is sent
    Then the response contains 7 tools
    And tool names include "museon_memory_read" and "museon_health_status"

  Scenario: MCP museon_health_status returns valid data
    When "museon_health_status" tool is called
    Then the result contains "museon_home"
    And "data_dir_exists" is true

  Scenario: MCP museon_memory_write and read roundtrip
    When "museon_memory_write" is called with level "L2_sem" key "test_bdd" content "hello"
    And "museon_memory_read" is called with level "L2_sem" key "test_bdd"
    Then the read result contains "hello"

  Scenario: MCP handles unknown tool gracefully
    When a tool call for "nonexistent_tool" is sent
    Then the response is a JSON-RPC error with code -32601

  # ─── E. Nightly Pipeline（MAX 改動步驟）────────────────

  Scenario: Budget settlement reports MAX subscription mode
    When _step_budget_settlement() is executed
    Then the result contains mode "max_subscription"
    And daily_calls is a non-negative integer

  Scenario: SOUL.md identity check passes with correct hash
    Given SOUL.md exists with valid SHA-256 hash
    When _step_soul_identity_check() is executed
    Then the result status is "verified"
    And no tamper event is published

  Scenario: SOUL.md identity check detects tampering
    Given SOUL.md core identity has been modified
    When _step_soul_identity_check() is executed
    Then the result status is "TAMPERED"
    And a tamper event is published

  Scenario: Federation upload runs without error in standalone mode
    Given MUSEON_FEDERATION_MODE is not set
    When _step_federation_upload() is executed
    Then it returns gracefully with a skipped status

  # ─── F. 壓力韌性 ─────────────────────────────────────

  Scenario: 10 rapid-fire messages within 60 seconds
    When 10 messages are sent within 60 seconds
    Then all 10 receive responses
    And no response is a 500 error
    And average response time is under 15 seconds

  Scenario: System audit passes after stress test
    When the full stress test suite completes
    Then system_audit reports 0 failures
    And Gateway is still healthy

  Scenario: No memory leak after 20 adapter calls
    Given the adapter's initial stats
    When 20 calls are made sequentially
    Then no subprocess is left running
    And adapter call_count equals 20
