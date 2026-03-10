Feature: Session Resilience — 對話歷史防污染機制
  防止離線回覆和異常數據污染 session 歷史。

  Background:
    Given a MuseonBrain instance with test data directory

  # ═══════════════════════════════════════
  # 離線回覆不存入 session
  # ═══════════════════════════════════════

  Scenario: Offline flag is set during offline response
    When the brain generates an offline response
    Then the offline flag should be True

  Scenario: Offline response only extracts user message
    Given messages contain a long assistant response and a short user message
    When the brain generates an offline response
    Then the response should contain the user message
    And the response should not contain the assistant response content

  Scenario: Offline response truncates long user messages
    Given messages contain a user message longer than 100 characters
    When the brain generates an offline response
    Then the response user message excerpt should be at most 100 characters

  # ═══════════════════════════════════════
  # Session 資料清洗
  # ═══════════════════════════════════════

  Scenario: Session loader detects pollution pattern
    Given a session file with repeated chaos patterns
    When the session is loaded from disk
    Then the polluted messages should be filtered out
    And the clean messages should remain

  Scenario: Clean session loads normally
    Given a session file with normal conversation
    When the session is loaded from disk
    Then all messages should be preserved

  Scenario: Empty session file returns empty list
    Given an empty session file
    When the session is loaded from disk
    Then the result should be an empty list
