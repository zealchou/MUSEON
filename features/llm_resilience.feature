Feature: LLM Resilience — LLM 連線韌性機制
  確保 LLM 呼叫的環境隔離和降級機制正常運作。

  # ═══════════════════════════════════════
  # ENV 隔離：ANTHROPIC_API_KEY 不污染 CLI
  # ═══════════════════════════════════════

  Scenario: CLI adapter strips ANTHROPIC_API_KEY from subprocess env
    Given ANTHROPIC_API_KEY is set in os.environ
    When ClaudeCLIAdapter prepares subprocess environment
    Then the subprocess env should not contain ANTHROPIC_API_KEY
    And the subprocess env should not contain CLAUDECODE

  # ═══════════════════════════════════════
  # FallbackAdapter 降級機制
  # ═══════════════════════════════════════

  Scenario: FallbackAdapter starts with CLI
    Given a FallbackAdapter with CLI and API adapters
    Then the active adapter should be "cli"

  Scenario: FallbackAdapter switches to API after CLI failures
    Given a FallbackAdapter with CLI and API adapters
    When CLI fails 2 consecutive times
    Then the active adapter should be "api"

  Scenario: FallbackAdapter probes CLI recovery
    Given a FallbackAdapter using API after CLI failures
    When 20 API calls complete
    Then a CLI probe should be attempted

  # ═══════════════════════════════════════
  # Brain 離線模式觸發 Sentinel
  # ═══════════════════════════════════════

  Scenario: Brain offline response triggers Sentinel via Governor
    Given a brain with a Governor that has VitalSigns
    When all LLM models fail
    Then the offline response should be returned
    And the VitalSigns sentinel should be notified

  Scenario: Brain LLM success resets VitalSigns counter
    Given a brain with a Governor that has VitalSigns
    When LLM call succeeds
    Then VitalSigns consecutive failures should be 0
