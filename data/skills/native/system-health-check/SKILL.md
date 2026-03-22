---
name: system-health-check
type: on-demand
hub: evolution
tier: T3
io:
  inputs:
    - from: doctor
      field: audit_report
      required: true
    - from: eval-engine
      field: quality_metrics
      required: false
  outputs:
    - to: knowledge-lattice
      field: health_crystal
      trigger: on_complete
    - to: morphenix
      field: repair_proposal
      trigger: on_critical
connects_to:
  - qa-auditor
  - eval-engine
  - morphenix
  - sandbox-lab
memory:
  writes:
    - target: knowledge-lattice
      type: health_crystal
      description: 系統健康檢查結果結晶化，追蹤長期健康趨勢
  reads:
    - eval-engine
    - knowledge-lattice
triggers:
  - 系統健康
  - 健康檢查
  - system health
  - 自檢
  - 連線完整性
  - 拓撲檢查
  - 診斷
rc_affinity:
  preferred: [civil_mode, evolution_mode]
  limited: []
  prohibited: []
description: >
  System-Health-Check（系統健康自檢引擎）— DNA27 核心的外掛模組，
  Evolution Hub 的防禦型衛星。定期自動診斷 MUSEON 的連線完整性、
  記憶流向健康度、Skill 協作狀態，產出結構化健康報告並在發現
  CRITICAL 級問題時自動生成 Morphenix 修復提案。

  三層診斷架構：
  1. 拓撲層——掃描 system-topology.md 與實際 import 的一致性
  2. 記憶層——檢查 memory-router.md 路由覆蓋率、結晶健康度
  3. 協作層——驗證 Skill 間的 io 銜接完整性（via validate_connections.py）

  與 qa-auditor 互補：qa-auditor 審計程式碼品質（T-Score），
  system-health-check 審計系統拓撲健康度（H-Score）。
  與 eval-engine 互補：eval-engine 度量回答品質（Q-Score），
  system-health-check 度量基礎設施品質。
  與 morphenix 互補：發現 CRITICAL 問題時自動生成修復提案。
  與 sandbox-lab 互補：修復提案可先在沙盒中測試再正式執行。

  觸發時機：(1) /health 或 /system-check 指令強制啟動；
  (2) nightly pipeline 定期執行；
  (3) 自然語言偵測——使用者詢問系統狀態、連線是否正常時自動啟用。
---
