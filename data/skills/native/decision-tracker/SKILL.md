---
name: decision-tracker
type: on-demand
hub: evolution
tier: T2
io:
  inputs:
    - from: brain
      field: decision_signal
      required: true
    - from: roundtable
      field: arbitration_result
      required: false
    - from: master-strategy
      field: strategic_assessment
      required: false
  outputs:
    - to: knowledge-lattice
      field: decision_crystal
      trigger: on_complete
    - to: user-model
      field: decision_preference
      trigger: on_pattern_detected
connects_to:
  - roundtable
  - deep-think
  - master-strategy
  - eval-engine
  - knowledge-lattice
memory:
  writes:
    - target: knowledge-lattice
      type: decision_crystal
      description: 決策記錄結晶化——包含決策背景、選項、選擇理由、預期結果
  reads:
    - knowledge-lattice
    - user-model
    - eval-engine
triggers:
  - 決策追蹤
  - 決策記錄
  - decision tracking
  - 決策歷史
  - 之前怎麼決定的
  - 上次的決定
  - 決策品質
rc_affinity:
  preferred: [civil_mode, evolution_mode]
  limited: []
  prohibited: []
description: >
  Decision-Tracker（決策歷史追蹤引擎）— DNA27 核心的外掛模組，
  Evolution Hub 的決策治理衛星。在 Brain 偵測到重大決策信號時自動啟動，
  記錄決策的完整生命週期：背景→選項→選擇→執行→結果→回饋。

  四階段追蹤：
  1. 決策捕獲——從 deep-think 的 decision_signal 偵測重大決策
  2. 選項記錄——從 roundtable 或 master-strategy 收集多方觀點
  3. 結果監測——決策執行後追蹤實際結果（14 天效果追蹤）
  4. 模式萃取——累積足夠決策記錄後，偵測使用者的決策偏好與盲點

  與 roundtable 互補：roundtable 提供多角色詰問，decision-tracker 記錄詰問結果和最終裁決。
  與 deep-think 互補：deep-think 偵測決策信號，decision-tracker 追蹤決策全程。
  與 master-strategy 互補：master-strategy 提供戰略評估，decision-tracker 記錄戰略選擇的後果。
  與 eval-engine 互補：eval-engine 度量回答品質，decision-tracker 度量決策品質。
  與 knowledge-lattice 互補：決策記錄結晶化後可被未來的類似決策參照。

  觸發時機：(1) /decision 或 /track 指令強制啟動；
  (2) brain 偵測到 SLOW_LOOP + decision_signal 時自動啟動；
  (3) 自然語言偵測——使用者回顧過去決策、評估決策品質時自動啟用。
---
