Feature: Vital Signs Monitor — 生命徵象監測系統
  三層偵測架構確保 MUSEON 不會在沉默中壞掉。

  Background:
    Given VitalSignsMonitor is initialized with test data directory

  # ═══════════════════════════════════════
  # Layer 1: Preflight（啟動時預檢）
  # ═══════════════════════════════════════

  Scenario: Preflight detects LLM adapter not registered
    Given no LLM adapter is registered
    When preflight runs
    Then the "llm_alive" check should be "skip"
    And the overall report should not be "fail"

  Scenario: Preflight detects healthy LLM
    Given a healthy LLM adapter is registered
    When preflight runs
    Then the "llm_alive" check should be "pass"

  Scenario: Preflight detects unhealthy LLM
    Given a failing LLM adapter is registered
    When preflight runs
    Then the "llm_alive" check should be "fail"

  Scenario: Preflight checks environment consistency
    When preflight runs
    Then the "env_consistency" check should exist
    And the check result should have a message

  Scenario: Preflight checks session integrity
    When preflight runs
    Then the "session_integrity" check should exist

  # ═══════════════════════════════════════
  # Layer 2: Pulse（定期探針）
  # ═══════════════════════════════════════

  Scenario: Pulse runs periodic health check
    Given a healthy LLM adapter is registered
    When pulse runs
    Then the pulse report should contain at least 3 checks
    And the overall pulse report should not be "fail"

  Scenario: Pulse detects resource issues
    When pulse runs
    Then the "resources" check should exist

  # ═══════════════════════════════════════
  # Layer 3: Sentinel（即時告警）
  # ═══════════════════════════════════════

  Scenario: Sentinel triggers on offline mode
    When offline is triggered with error "OAuth token has expired"
    Then the sentinel count should be 1
    And consecutive LLM failures should be 1

  Scenario: Sentinel rate-limits alerts
    When offline is triggered with error "error1"
    And offline is triggered with error "error2" within same minute
    Then the sentinel count should be 1

  Scenario: LLM success resets failure counter
    Given consecutive LLM failures is 3
    When LLM success is reported
    Then consecutive LLM failures should be 0

  # ═══════════════════════════════════════
  # Integration: Governor ↔ VitalSigns
  # ═══════════════════════════════════════

  Scenario: Governor exposes vital signs status
    Given VitalSignsMonitor is started
    When get_status is called
    Then the status should contain "running" as true
    And the status should contain "sentinel_count"

  Scenario: Diagnose offline cause provides repair guidance
    When diagnosing error "OAuth token has expired"
    Then the guidance should mention "claude auth login"

  Scenario: Diagnose offline cause for API key issue
    When diagnosing error "invalid x-api-key"
    Then the guidance should mention "ANTHROPIC_API_KEY"
