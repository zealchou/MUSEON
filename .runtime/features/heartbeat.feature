Feature: Heartbeat-driven Evolution
  As MUSEON's autonomous system
  I want to perform heartbeat tasks every 30 minutes
  So that I can patrol, learn, and evolve even when the boss is away

  Background:
    Given MUSEON is running 24/7
    And the cron engine is active
    And heartbeat is scheduled "*/30 * * * *"

  Scenario: Heartbeat performs social media patrol
    Given it's time for heartbeat execution
    When heartbeat task starts
    Then it should check Instagram comments
    And it should check LINE messages
    And it should check platform notifications
    And it should record findings in event channel

  Scenario: Heartbeat performs curiosity-driven research
    Given it's time for heartbeat execution
    And the boss hasn't interacted in 2 hours
    When heartbeat task starts
    Then it should research the boss's industry
    And it should browse MoltBook for insights
    And it should record learnings in meta-thinking channel

  Scenario: Heartbeat performs health check
    Given it's time for heartbeat execution
    When heartbeat task starts
    Then it should check RAM usage
    And it should check disk space
    And it should check API quota remaining
    And it should log health metrics

  Scenario: Heartbeat finds urgent item and notifies boss
    Given it's time for heartbeat execution
    When heartbeat finds urgent Instagram comment from VIP customer
    Then it should send Telegram notification to boss
    And it should prepare draft response
    And it should wait for boss approval before posting

  Scenario: Heartbeat respects boss's sleep hours
    Given it's 2 AM (boss's sleep time)
    When heartbeat finds non-urgent notification
    Then it should queue the notification
    But it should not send Telegram message
    And it should wait until morning (8 AM) to notify

  Scenario: Heartbeat accumulates insights for nightly job
    Given heartbeat has run 3 times today
    When nightly job runs at 3 AM
    Then it should access all heartbeat findings
    And it should crystallize patterns into knowledge
    And it should update skill efficiency metrics

  Scenario: Heartbeat detects skill opportunity
    Given heartbeat is patrolling social media
    When it notices repeated manual task (responding to FAQs)
    Then it should log potential skill creation opportunity
    And nightly job should trigger ACSF to create FAQ skill

  Scenario: Heartbeat runs in background without blocking user interaction
    Given the boss is actively chatting with MUSEON
    When it's time for heartbeat execution
    Then heartbeat should run in separate session
    And user interaction should not be interrupted
    And heartbeat should not consume user's token budget

  Scenario: Heartbeat handles failure gracefully
    Given it's time for heartbeat execution
    When Instagram API is temporarily down
    Then heartbeat should log the error
    And it should continue with other patrol tasks
    And it should retry Instagram patrol in next heartbeat

  Scenario: Heartbeat evolution over growth stages
    Given MUSEON is in "infant" stage (Day 1-14)
    When heartbeat runs
    Then it should focus on observing boss's patterns
    And it should not take autonomous actions

    Given MUSEON is in "child" stage (Day 30-60)
    When heartbeat runs
    Then it should actively explore and suggest
    And it should start self-forging skills

    Given MUSEON is in "adult" stage (Day 120+)
    When heartbeat runs
    Then it should operate fully autonomously
    And it should pro actively handle routine tasks
