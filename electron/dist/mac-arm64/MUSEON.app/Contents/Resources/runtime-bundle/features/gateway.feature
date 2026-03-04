Feature: Gateway Core - 24/7 Life Central

  Background:
    Given the Gateway is running on localhost only
    And the Session Manager is initialized
    And the Security Gate is active

  Scenario: Gateway receives message from Telegram
    Given a Telegram message arrives
    When the message passes security validation
    And the session is not currently processing
    Then the message is converted to InternalMessage format
    And the session acquires processing lock
    And the message is routed to Agent Runtime

  Scenario: Gateway enforces session serialization
    Given a session is currently processing a message
    When another message arrives for the same session
    Then the second message is queued
    And waits until the first message completes
    And then processes the second message

  Scenario: Gateway blocks remote access
    Given the Gateway server is configured
    When a connection attempt from non-localhost IP
    Then the connection is rejected
    And an audit log entry is created

  Scenario: Cron Engine runs heartbeat
    Given the Cron Engine is configured with heartbeat schedule
    When the scheduled time arrives
    Then a heartbeat task is triggered
    And the task message is routed through Gateway
    And the task completes successfully

  Scenario: Security Gate validates HMAC
    Given a webhook message with HMAC signature
    When the HMAC signature is valid
    Then the message passes security validation
    And is processed normally

  Scenario: Security Gate rejects invalid HMAC
    Given a webhook message with invalid HMAC signature
    When the Security Gate validates the signature
    Then the message is rejected
    And an audit log entry is created
    And the client receives 403 Forbidden

  Scenario: Rate limiting prevents abuse
    Given a user sends 100 messages in 1 minute
    When the rate limit threshold is exceeded
    Then subsequent messages are rejected
    And the client receives 429 Too Many Requests
    And an audit log entry is created
