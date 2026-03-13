Feature: Crystal Closed Loop — 結晶從「記住」到「改變」的完整閉環
  結晶不只是被記住的知識，而是能驅動行為改變的活知識。
  此閉環涵蓋：水源注入 → 行為規則轉化 → prompt 注入 → 回饋代謝。

  Background:
    Given a temporary MUSEON workspace is created

  # ════════════════════════════════════════════
  # P0: Morphenix 執行後回寫結晶狀態
  # ════════════════════════════════════════════

  Scenario: P0 — Morphenix 執行後回寫結晶狀態
    Given a KnowledgeLattice with a downgraded crystal
    When MorphenixExecutor closes the crystal loop for a successful proposal
    Then the crystal counter_evidence_count is reset to 0
    And the crystal status is "active"

  Scenario: P0 — Morphenix 將演化結果結晶化
    Given a MorphenixExecutor with workspace
    When a Morphenix proposal executes successfully
    Then a new Lesson crystal with origin "morphenix_evolution" exists in the lattice

  # ════════════════════════════════════════════
  # P1: 三條結晶水源
  # ════════════════════════════════════════════

  Scenario: P1 — WEE 壓縮結果寫入 Knowledge Lattice
    Given a WEEEngine with workspace
    When WEE compress_daily produces a summary
    Then a new Pattern crystal with origin "wee_reflection" exists in the lattice

  Scenario: P1 — Explorer 探索結果寫入 Knowledge Lattice
    Given a PulseEngine exploration result
    When exploration succeeds with findings
    Then a new Insight crystal with origin "exploration" exists in the lattice

  # ════════════════════════════════════════════
  # P2: Crystal Actuator 行為規則引擎
  # ════════════════════════════════════════════

  Scenario: P2 — 高置信結晶轉化為行為規則
    Given a KnowledgeLattice with eligible crystals
    And a CrystalActuator initialized
    When CrystalActuator.actualize is called
    Then at least 1 new rule is created
    And the rule has a valid rule_type
    And the rule has a valid action

  Scenario: P2 — 低置信結晶不會被轉化
    Given a KnowledgeLattice with only low-confidence crystals
    And a CrystalActuator initialized
    When CrystalActuator.actualize is called
    Then 0 new rules are created

  Scenario: P2 — 規則有 TTL 且過期規則被清除
    Given a CrystalActuator with an expired rule
    When CrystalActuator.actualize is called
    Then the expired rule is removed

  Scenario: P2 — 規則格式化為 prompt 段落
    Given a CrystalActuator with active rules
    When format_rules_for_prompt is called
    Then the output contains action keywords

  # ════════════════════════════════════════════
  # P3: 回饋驗證迴圈（新陳代謝）
  # ════════════════════════════════════════════

  Scenario: P3 — 正面回饋強化規則
    Given a CrystalActuator with a rule that has positive feedback
    When metabolize is called
    Then the rule strength increases
    And the rule TTL is extended

  Scenario: P3 — 負面回饋淘汰規則
    Given a CrystalActuator with a rule that has heavy negative feedback
    When metabolize is called
    Then the rule is removed

  # ════════════════════════════════════════════
  # 整合：Nightly Pipeline + Brain
  # ════════════════════════════════════════════

  Scenario: Nightly Pipeline 包含 Crystal Actuator 步驟
    Given a NightlyPipeline with workspace
    When step 5.7 crystal_actuator is executed
    Then the result contains actualize and metabolize reports

  Scenario: Brain 注入結晶行為規則到 system prompt
    Given a MuseonBrain with CrystalActuator having active rules
    When build_system_prompt is called
    Then the system prompt contains crystal behavior rules section
