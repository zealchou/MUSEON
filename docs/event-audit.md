# Event Bus 審計表 v1.0

> 事件 → 發布者 → 訂閱者 完整映射。找出孤立事件。
>
> 審計日期：2026-03-26
> 事件總數：92（含 6 棄用）
> 資料來源：`src/museon/core/event_bus.py` + 全域 grep

---

## Pulse-related 事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| PULSE_MICRO_BEAT | micro_pulse | perception (動態), server/ActivityLogger (動態) | ✅ 正常 |
| PULSE_RHYTHM_CHECK | _(無發布者)_ | _(無訂閱者，telegram.py 僅 import)_ | ⚠️ 孤立定義（無 publish 無 subscribe） |
| PULSE_NIGHTLY_DONE | _(無發布者)_ | _(無訂閱者，telegram.py 僅 import)_ | ⚠️ 孤立定義（無 publish 無 subscribe） |
| EVOLUTION_HEARTBEAT | _(無發布者)_ | perception (動態) | ⚠️ 孤立訂閱（有 subscribe 無 publish） |
| PROACTIVE_MESSAGE | proactive_bridge, pulse_engine, nightly_pipeline, morphenix_executor, exploration_bridge | telegram._on_proactive_message | ✅ 正常 |
| AUTONOMOUS_TASK_DONE | autonomous_queue | perception (動態), server/ActivityLogger (動態) | ✅ 正常 |

## Nightly pipeline 事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| NIGHTLY_STARTED | nightly_pipeline | server/ActivityLogger (動態) | ✅ 正常 |
| NIGHTLY_COMPLETED | nightly_pipeline | server._on_nightly_completed, exploration_bridge, server/ActivityLogger (動態) | ✅ 正常 |

## Soft Workflow 事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| WORKFLOW_CREATED | routes_api | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| WORKFLOW_EXECUTED | workflow_executor | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| WORKFLOW_COMPLETED | workflow_executor | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| WORKFLOW_FAILED | workflow_executor, workflow_scheduler | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| WORKFLOW_LIFECYCLE_CHANGED | _(無發布者)_ | _(無訂閱者)_ | ⚠️ 孤立定義（無 publish 無 subscribe） |
| WORKFLOW_SCHEDULE_TOGGLED | workflow_scheduler | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |

## WEE / Workflow 自我迭代事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| BRAIN_RESPONSE_COMPLETE | brain | server._on_brain_response (→ WEE), perception (動態), server/ActivityLogger (動態) | ✅ 正常 |
| WEE_RECORDED | workflow_engine | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| WEE_LIFECYCLE_CHANGED | workflow_engine | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| WEE_PLATEAU_DETECTED | workflow_engine | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |

## Self-Diagnosis 事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| SELF_DIAGNOSIS_TRIGGERED | brain | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| SELF_DIAGNOSIS_COMPLETED | self_diagnosis, diagnosis_pipeline | perception (動態) | ✅ 正常 |
| SELF_REPAIR_EXECUTED | _(無發布者)_ | _(無訂閱者)_ | 🔴 棄用 DEPRECATED(v1.42) |

## Self-Surgery 事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| SURGERY_TRIGGERED | surgeon | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| SURGERY_SAFETY_PASSED | surgeon | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| SURGERY_SAFETY_FAILED | surgeon | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| SURGERY_COMPLETED | surgeon | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| SURGERY_FAILED | surgeon | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| SURGERY_ROLLBACK | surgeon | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| SURGERY_VALIDATED | surgeon | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| SURGERY_VALIDATION_FAILED | surgeon | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| SURGERY_DELEGATED_TO_CLAUDE_CODE | surgeon | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |

## Morphenix 演化提案事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| MORPHENIX_L3_PROPOSAL | nightly_pipeline, morphenix_executor | telegram._on_morphenix_l3 | ✅ 正常 |
| MORPHENIX_AUTO_APPROVED | cron_registry | governor._on_morphenix_auto_approved | ✅ 正常 |
| MORPHENIX_EXECUTION_COMPLETED | morphenix_executor | telegram._on_morphenix_executed, skill_router._on_morphenix_completed, server/ActivityLogger (動態), perception (動態) | ✅ 正常 |
| MORPHENIX_ROLLBACK | morphenix_executor | telegram._on_morphenix_rollback | ✅ 正常 |

## DNA-Inspired Quality Feedback 事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| METACOGNITION_QUALITY_FLAG | metacognition | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |

## Governance 治理層事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| GOVERNANCE_CYCLE_COMPLETED | governor | dendritic_scorer._on_governance_cycle | ✅ 正常 |
| GOVERNANCE_HEALTH_CHANGED | governor | dendritic_scorer._on_health_changed | ✅ 正常 |
| GOVERNANCE_ALGEDONIC_SIGNAL | governor | dendritic_scorer._on_algedonic | ✅ 正常 |

## Autonomy Architecture 事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| TOKEN_BUDGET_WARNING | _(無發布者)_ | _(無訂閱者)_ | 🔴 棄用 DEPRECATED(v1.42) |
| TOKEN_BUDGET_CONSERVATION | _(無發布者)_ | _(無訂閱者)_ | 🔴 棄用 DEPRECATED(v1.42) |
| SYNAPSE_PRELOAD | nightly_pipeline | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| TOOL_MUSCLE_DORMANT | nightly_pipeline | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| IMMUNE_MEMORY_LEARNED | nightly_pipeline | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| AUTONOMIC_REPAIR | governor | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| EVOLUTION_TRACE | _(無發布者)_ | _(無訂閱者)_ | 🔴 棄用 DEPRECATED(v1.42) |
| TRIGGER_FIRED | nightly_pipeline | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |

## Immune Defense 五層免疫防禦事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| PREFLIGHT_FAILED | _(無發布者，system_audit 僅引用字串)_ | _(無訂閱者)_ | ⚠️ 孤立定義（無 publish 無 subscribe） |
| PREFLIGHT_PASSED | _(無發布者，system_audit 僅引用字串)_ | _(無訂閱者)_ | ⚠️ 孤立定義（無 publish 無 subscribe） |
| REFRACTORY_BACKOFF | _(無發布者，system_audit 僅引用字串)_ | _(無訂閱者)_ | ⚠️ 孤立定義（無 publish 無 subscribe） |
| REFRACTORY_HIBERNATE | _(無發布者，system_audit 僅引用字串)_ | _(無訂閱者)_ | ⚠️ 孤立定義（無 publish 無 subscribe） |
| REFRACTORY_WAKE | _(無發布者)_ | _(無訂閱者)_ | 🔴 棄用 DEPRECATED(v1.42) |
| GATEWAY_DEGRADED | _(無發布者)_ | _(無訂閱者)_ | 🔴 棄用 DEPRECATED(v1.42) |

## Exploration → Evolution Bridge 事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| EXPLORATION_CRYSTALLIZED | pulse_engine | server._on_exploration_result, exploration_bridge._on_exploration | ✅ 正常 |
| EXPLORATION_INSIGHT | pulse_engine | server._on_exploration_result, exploration_bridge._on_exploration | ✅ 正常 |
| CURIOSITY_RESEARCHED | curiosity_router | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| SCOUT_DRAFT_READY | skill_forge_scout | exploration_bridge._on_scout_draft | ✅ 正常 |
| SCOUT_GAP_DETECTED | exploration_bridge | skill_forge_scout._on_gap_detected | ✅ 正常 |

## Dendritic Layer 免疫觀察層事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| HEALTH_SCORE_UPDATED | dendritic_scorer | proactive_bridge._on_health_score_updated | ✅ 正常 |
| INCIDENT_DETECTED | dendritic_scorer | immune_research._on_incident | ✅ 正常 |
| REPAIR_RESEARCH_READY | immune_research | immune_memory._on_repair_ready | ✅ 正常 |

## Phase 1 神經整合事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| MEMORY_STORED | memory_manager | vector_bridge._on_memory_stored | ✅ 正常 |
| MEMORY_PROMOTED | memory_manager | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| MEMORY_RECALLED | memory_manager | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| MEMORY_VECTOR_INDEXED | vector_bridge | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| SKILL_QUALITY_SCORED | eval_engine, wee_engine | dendritic_scorer._on_skill_quality, outward_trigger._on_skill_quality | ✅ 正常 |
| DNA27_WEIGHTS_UPDATED | morphenix_executor | skill_router._on_dna27_updated | ✅ 正常 |
| SKILL_ROUTER_RELOADED | skill_router | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| RESEARCH_COMPLETED | research_engine | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| TOOL_HEALTH_CHANGED | tool_registry | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| TOOL_DEGRADED | tool_registry | dendritic_scorer._on_tool_degraded | ✅ 正常 |
| TOOL_RECOVERED | tool_registry | dendritic_scorer._on_tool_recovered | ✅ 正常 |

## Phase 2 神經整合事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| NIGHTLY_HEALTH_GATE | nightly_pipeline | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| NIGHTLY_DAG_EXECUTED | nightly_pipeline | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| EVOLUTION_VELOCITY_ALERT | nightly_pipeline | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| AUDIT_TREND_UPDATED | system_audit | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| AUDIT_COMPLETED | system_audit | governor._on_audit_completed | ✅ 正常 |
| IMMUNE_KNOWLEDGE_GAINED | immune_research | immune_memory._on_knowledge_gained | ✅ 正常 |
| SHARED_ASSET_PUBLISHED | shared_assets | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| KNOWLEDGE_GRAPH_UPDATED | nightly_pipeline, course_generator | shared_assets._on_knowledge_graph_updated | ✅ 正常 |
| PULSE_FREQUENCY_ADJUSTED | proactive_bridge | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |

## Phase 3 外部整合事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| CHANNEL_MESSAGE_RECEIVED | slack, email, community, discord | feedback_loop._on_message | ✅ 正常 |
| CHANNEL_MESSAGE_SENT | slack, email, discord | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| GROUP_SESSION_END | telegram | _(無訂閱者，group_session_proactive 有方法但未 subscribe)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| RSS_NEW_ITEMS | rss_aggregator | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| WIKI_PUBLISHED | _(無發布者)_ | _(無訂閱者)_ | ⚠️ 孤立定義（無 publish 無 subscribe） |
| USER_FEEDBACK_SIGNAL | recommender, feedback_loop | outward_trigger._on_feedback_signal | ✅ 正常 |
| USER_QUIET_MODE | brain_observation | proactive_bridge._on_user_quiet_mode | ✅ 正常 |
| DIFY_WORKFLOW_TRIGGERED | dify_scheduler | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| DIFY_WORKFLOW_COMPLETED | dify_scheduler | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |

## Phase 4 外部整合事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| IOT_EVENT_RECEIVED | mqtt | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| IOT_COMMAND_SENT | mqtt | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| EXTENSION_CAPTURE | routes_api | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| EXTENSION_COMMAND | routes_api | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| IMAGE_GENERATED | image_gen | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| VOICE_SYNTHESIZED | voice_clone | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| ZOTERO_ITEM_IMPORTED | zotero_bridge | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |

## 外向型進化事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| OUTWARD_SEARCH_NEEDED | outward_trigger | intention_radar._on_search_needed | ✅ 正常 |
| OUTWARD_SELF_CRYSTALLIZED | digest_engine | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| OUTWARD_SERVICE_CRYSTALLIZED | digest_engine | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| OUTWARD_TRIAL_RECORDED | digest_engine | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| OUTWARD_KNOWLEDGE_ARCHIVED | digest_engine | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |

## Pulse 進階事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| PULSE_PROACTIVE_SENT | telegram | server/ActivityLogger (動態) | ✅ 正常 |
| PULSE_EXPLORATION_DONE | pulse_engine | server/ActivityLogger (動態) | ✅ 正常 |
| RELATIONSHIP_SIGNAL | brain_observation | server._on_relationship_signal | ✅ 正常 |

## Morphenix / WEE / Knowledge 進階事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| MORPHENIX_PROPOSAL_CREATED | nightly_pipeline | server/ActivityLogger (動態) | ✅ 正常 |
| MORPHENIX_EXECUTED | _(無發布者，morphenix_executor 註解已移除)_ | _(無訂閱者)_ | ⚠️ 孤立定義（無 publish 無 subscribe） |
| WEE_CYCLE_COMPLETE | wee_engine | server/ActivityLogger (動態) | ✅ 正常 |
| CRYSTAL_CREATED | knowledge_lattice | server/ActivityLogger (動態) | ✅ 正常 |

## Soul Identity 事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| SOUL_RING_DEPOSITED | soul_ring | server/ActivityLogger (動態) | ✅ 正常 |
| SOUL_IDENTITY_TAMPERED | nightly_pipeline | governor._on_soul_identity_tampered | ✅ 正常 |

## 資料層監控事件

| 事件名稱 | 發布者 | 訂閱者 | 狀態 |
|---------|--------|--------|------|
| DATA_HEALTH_CHECKED | nightly_pipeline | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| DATA_STORE_DEGRADED | nightly_pipeline | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| DATA_STORAGE_WARNING | nightly_pipeline | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |
| DATA_DEAD_WRITE_DETECTED | nightly_pipeline | _(無訂閱者)_ | ⚠️ 孤立發布（有 publish 無 subscribe） |

---

## 統計摘要

| 狀態 | 數量 | 說明 |
|------|------|------|
| ✅ 正常 | 38 | 有發布者 + 有訂閱者 |
| ⚠️ 孤立發布 | 40 | 有 publish 但無 subscribe |
| ⚠️ 孤立訂閱 | 1 | 有 subscribe 但無 publish（EVOLUTION_HEARTBEAT） |
| ⚠️ 孤立定義 | 7 | 無 publish 也無 subscribe（含未標記棄用的） |
| 🔴 棄用 | 6 | 已標記 DEPRECATED(v1.42) |
| **合計** | **92** | |

### 備註

1. **ActivityLogger 動態訂閱**（server.py L3556-3583）：12 個事件透過動態 `getattr` 訂閱記錄到 JSONL。這些事件的「有訂閱者」已計入上表。
2. **Perception 動態訂閱**（perception.py L426-444）：6 個事件透過動態訂閱供四診合參使用。已計入。
3. **孤立發布不一定是 bug**：許多「孤立發布」事件屬於 Phase 3/4 外部整合（IoT、Chrome Extension、RSS 等），設計上是預留介面，待未來消費者接入。Surgery 事件也是同理——作為審計軌跡（audit trail）發布，未來可接監控。
4. **建議優先清理的孤立定義**（無 publish 無 subscribe 且未標記棄用）：
   - `PULSE_RHYTHM_CHECK` — telegram.py 僅 import 未使用
   - `PULSE_NIGHTLY_DONE` — telegram.py 僅 import 未使用
   - `WORKFLOW_LIFECYCLE_CHANGED` — 從未被 publish 或 subscribe
   - `WIKI_PUBLISHED` — 從未被 publish 或 subscribe
   - `MORPHENIX_EXECUTED` — morphenix_executor 已不再發布此事件
   - `PREFLIGHT_FAILED` / `PREFLIGHT_PASSED` / `REFRACTORY_BACKOFF` / `REFRACTORY_HIBERNATE` — 僅在 system_audit 中作為字串常數引用（審計用），無實際 EventBus 流通
5. **EVOLUTION_HEARTBEAT** 有 subscribe（perception）但無 publish — 可能是上游發布者被移除但訂閱者未清理。
