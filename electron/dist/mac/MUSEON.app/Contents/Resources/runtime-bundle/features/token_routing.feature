Feature: Token Routing - Smart Model Selection

  Background:
    Given the LLM Client is configured with Haiku and Sonnet
    And the Router is initialized with classification rules
    And Prompt Caching is enabled

  Scenario: Router classifies simple greeting for Haiku
    Given a user message "Hello!"
    When the Router classifies the message
    Then the message is routed to Haiku
    And the reason is "simple greeting"

  Scenario: Router routes skill-based task to Sonnet
    Given a user message "Help me write an Instagram post for my cafe"
    When the Router classifies the message
    Then the message is routed to Sonnet
    And the reason is "skill orchestration required"

  Scenario: Router routes business consulting to Sonnet
    Given a user message "My business revenue dropped this month, what should I do?"
    When the Router classifies the message
    Then the message is routed to Sonnet
    And the reason is "business consulting"

  Scenario: Prompt Caching reduces token cost
    Given a system prompt of 3000 tokens
    When the same prompt is used twice within cache window
    Then the second call uses cached prompt
    And input tokens are reduced by 90%

  Scenario: Token-Efficient Tool Use header is sent
    Given the LLM Client makes a request
    When tools are included in the request
    Then the anthropic-beta header includes "token-efficient-tools-2025-02-19"
    And tool definitions are compressed

  Scenario: Budget monitor tracks token usage
    Given a daily budget of 200K tokens
    When 150K tokens have been consumed
    Then the budget monitor reports 75% usage
    And sends warning notification

  Scenario: Budget monitor blocks requests when exceeded
    Given a daily budget of 200K tokens
    When 210K tokens have been consumed
    Then subsequent requests are blocked
    And user is notified of budget exhaustion

  Scenario: Reflex Engine matches template response
    Given a user message "What's your phone number?"
    When the Reflex Engine checks templates
    Then a template match is found
    And response is returned without LLM call
    And zero tokens are consumed

  Scenario: Router maintains Sonnet for ongoing skill usage
    Given a conversation with active DNA27 skills
    When a new message arrives in same session
    Then the Router maintains Sonnet model
    And does not downgrade to Haiku
