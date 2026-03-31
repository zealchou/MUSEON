# Blast Radius — 模組影響半徑表 v1.90

> **用途**：修改任何模組前，查閱此表確認「改了會影響誰、觸發什麼連鎖反應」。
> **比喻**：施工影響範圍圖——在哪裡動工、要封哪些路、通知哪些住戶。
> **更新時機**：改變模組的 import 關係或共享狀態存取時，必須在同一個 commit 中同步更新此文件。
> **建立日期**：2026-03-15（DSE 第二輪排查後建立）
> **搭配**：`docs/joint-map.md`（接頭圖）提供共享狀態細節、`docs/operational-contract.md`（操作契約表）提供外部操作預期失敗
> **v1.90 (2026-03-31)**：Persona Evolution 系統六模組新增——🟡黃區：`evolution/trait_engine.py`（扇入=2：brain_observation._observe_self + nightly_reflection，扇出=1：anima_mc_store via kernel_guard，寫入 ANIMA_MC.personality.trait_dimensions）、`evolution/nightly_reflection.py`（扇入=1：nightly_pipeline Step 34，扇出=4：anima_mc_store + kernel_guard + soul_ring + momentum_brake，讀寫 ANIMA_MC.personality.trait_dimensions + soul_rings.json）、`evolution/mask_engine.py`（扇入=2：brain.py Step 2.2 + Step 9.9，扇出=1：寫入 _system/mask_states.json）；🟢綠區：`evolution/growth_stage.py`（扇入=2：brain_observation._update_growth_stage + nightly_pipeline Step 34.5，扇出=0，純計算，讀 ANIMA_MC.evolution.stage_history）、`evolution/dissent_engine.py`（扇入=1：brain.py Step 3.655，扇出=1：讀 crystal_rules.json，無狀態）、`evolution/momentum_brake.py`（扇入=2：nightly_reflection + drift_detector，扇出=0，純計算，讀 ANIMA_MC.evolution.trait_history）。新增共享狀態：_system/mask_states.json（#70）。綠區葉子模組 171→173，黃區 62→65。
> **v1.89 (2026-03-31)**：結晶記憶架構重構——`agent/knowledge_lattice.py` 新增 `_classify_domain()` 輔助函數 + `_DOMAIN_KEYWORDS` 常數（7 domain 關鍵詞表），在 `crystallize()` Step 2→2.5 之間自動填入 domain（扇入不變，扇出不變，純內部邏輯擴充）；`nightly/nightly_pipeline.py` 新增 Step 32 `_step_crystal_decay`（ri_score 每日 *0.995 衰減，<0.1 歸檔）+ Step 33 `_step_crystal_promotion`（reinforcement_count≥3 的 Lesson/Procedure/Pattern 自動升級 heuristics.json，每次最多 3 條，總上限 50）；nightly_pipeline 步驟數 47→49；crystal.db 存取模式從 R 升級為 RW（Step 32 直接 SQL UPDATE）；heuristics.json 寫入路徑新增 nightly Step 33（via IntuitionEngine）。
> **v1.88 (2026-03-31)**：多租戶敏感度 LLM 驗證 + 報告發布工具——`governance/multi_tenant.py` 新增 `TRUSTED_PARTNERS` dict 與 `SENSITIVITY_LLM_PROMPT` 常數，`SensitivityChecker.check()` 新增 `user_id` 參數（扇入不變，仍為 3：telegram_pump, brain_observation, brain_prompt_builder；扇出不變）；`agent/tool_schemas.py` 新增 `publish_report` 工具定義（綠區扇入=0，不影響既有模組）；`agent/tools.py` 新增 `publish_report` 路由 + `_execute_publish_report()` 執行方法，透過 `subprocess` 呼叫 `scripts/publish-report.sh`（扇出+1：scripts/publish-report.sh via subprocess）；`gateway/telegram_pump.py` 新增 LLM 上下文驗證機制——lazy import `SENSITIVITY_LLM_PROMPT` from multi_tenant，呼叫 `brain._call_llm_with_model()` 以 Haiku 進行敏感度二次驗證（扇出+1：brain._call_llm_with_model()）。
> **v1.87 (2026-03-31)**：9 條斷裂接線修復——修改模組：`agent/skill_router.py` 新增 tuned_parameters.json 讀取（扇出+1：_system/evolution/tuned_parameters.json(R)）；`nightly/periodic_cycles.py` 高原警報→write_signal（扇出+1：triage_step.write_signal）；`evolution/wee_engine.py` payload 加 blind_spots:[]（純 schema 補齊，扇出不變）；`agent/brain_prompt_builder.py` insight update_confidence +0.05（扇出+0，InsightExtractor 已接線）；`core/session_adjustment.py` _promote_to_lesson→crystallize（扇出已含 crystal.db，不變）；`evolution/feedback_loop.py` 品質下降→LEARNING_GAP write_signal（扇出+1：triage_step.write_signal）；`doctor/surgeon.py` 手術完成→SYSTEM_FAULT write_signal（扇出+1：triage_step.write_signal）；`nightly/morphenix_executor.py` 迭代完成/失敗→SYSTEM_FAULT/BEHAVIOR_DRIFT write_signal（扇出+2：triage_step.write_signal x2）；`doctor/finding.py` record_occurrence 持久化計數（扇出+1：finding_counts.json(W)）；`doctor/museoff.py` ≥3次→SYSTEM_FAULT write_signal + escalate_to_morphenix（扇出+1：triage_step.write_signal）。triage_step.write_signal 扇入 +6（surgeon/morphenix_executor/feedback_loop/museoff/periodic_cycles）。新增共享狀態 #69 `data/_system/museoff/finding_counts.json`。同步 joint-map v1.57、system-topology v1.69、persistence-contract v1.43。
> **v1.86 (2026-03-31)**：體液系統迭代——新增 7 個模組到安全分級表：🟢 綠區：`core/awareness.py`（AwarenessSignal 統一覺察訊號，扇入=0，扇出=0，純 dataclass 無副作用）、`core/session_adjustment.py`（SessionAdjustment 即時行為調整管理器，扇入=2（brain_prompt_builder + triage_step），扇出=1：_system/session_adjustments/）、`nightly/triage_step.py`（Nightly 分診步驟，扇入=0，扇出=3：triage_queue.jsonl + awareness_log.jsonl + nightly_priority_queue.json）、`nightly/triage_to_morphenix.py`（HIGH → Morphenix 迭代筆記橋接，扇入=1（nightly_pipeline），扇出=1：morphenix/proposals/）、`governance/algedonic_alert.py`（治理警報 Telegram 推播，扇入=1（governor），扇出=2：event_bus GOVERNANCE_ALGEDONIC_SIGNAL + PROACTIVE_MESSAGE）；修改模組：`gateway/telegram_pump.py` 新增 CHANNEL_MESSAGE_RECEIVED publish（扇出+1）、`governance/governor.py` 初始化 AlgedonicAlert（扇出+1）、`governance/response_guard.py` 新增 strip_markdown() 靜態方法（扇出不變，功能擴充）、`agent/brain_prompt_builder.py` 新增四路接線（MemoryReflector + Skill 教訓預載 + SessionAdjustment + code 層自動觸發，扇出+3）、`nightly/nightly_pipeline.py` Step 5.8 前置 triage_to_morphenix（扇出+1）。新增共享狀態 7 個（#62-#68）。同步 joint-map v1.56、system-topology v1.68、memory-router v1.18、persistence-contract v1.42。
> **v1.85 (2026-03-30)**：Skill 自動演化管線（Organ Growth Pipeline）——新增 4 個 🟢 綠區模組：`nightly/skill_draft_forger.py`（扇入=1 from nightly_pipeline，扇出=3：skills_draft/ + morphenix/proposals/ + Anthropic API）、`nightly/skill_install_worker.py`（扇入=1 from telegram callback，扇出=6：~/.claude/skills/ + plugin-registry + topology + memory-router + validate_connections.py + sync_topology_to_3d.py）、`nightly/skill_qa_gate.py`（扇入=1 from nightly_pipeline，扇出=2：skills_draft/ + Anthropic API）、`nightly/skill_health_tracker.py`（扇入=1 from nightly_pipeline，扇出=3：skill_usage_log.jsonl + q_scores.jsonl + skill_health/）。nightly_pipeline.py 新增 Step 19.5/19.6/19.7（扇入不變，新增 4 個 import）。morphenix_executor.py 新增 L1 四道護欄（扇入不變）。同步 system-topology v1.67、joint-map v1.55、memory-router v1.17。
> **v1.84 (2026-03-30)**：13 個新 Skill Post-Build 補登——批次新增 Skill 到安全分級表：🟡黃區：ad-pilot（扇入=3，扇出=5）、equity-architect（扇入=3，扇出=5）、course-forge（扇入=4，扇出=5）、brand-project-engine（扇入=2，扇出=2）、finance-pilot（扇入=2，扇出=4）、prompt-stresstest（扇入=2，扇出=5）；🟢綠區：biz-collab（扇入=0，扇出=4）、biz-diagnostic（扇入=0，扇出=3）、video-strategy（扇入=0，扇出=4）、shadow-muse（扇入=0，扇出=4）、daily-pilot（扇入=0，扇出=4）、talent-match（扇入=0，扇出=4）、workflow-brand-consulting（扇入=0，扇出=6）。同步 system-topology v1.66、joint-map v1.54、memory-router v1.16。
> **v1.83 (2026-03-30)**：市場戰神（Market Ares）——新增 `src/museon/market_ares/` 模組群（9 子包 16 檔），全部 🟢 綠區扇入=0。子模組：config.py / storage/{db,models}.py / mapping/{energy_mapper,mapping_config.yaml} / clustering/{hierarchical,kmeans_refine,archetype_namer}.py / simulation/{engine,strategy_impact,social_contagion,oscillation}.py / coaching/{self_drive_coach,chauffeur_coach}.py / analysis/{weekly_insight,turning_point,strategy_optimizer,final_report}.py / visualization/{charts,dashboard,report_renderer}.py / crawler/tw_demographics.py。新增儲存：`data/market_ares/market_ares.db`（SQLite WAL，6 表）。無跨模組 import，不影響既有系統。同步 system-topology v1.64、joint-map v1.53、memory-router v1.14、persistence-contract v1.41。
> **v1.82 (2026-03-29)**：統一發送出口防漏修復——ResponseGuard.sanitize_for_group() 取消群組/私訊分流，所有通道統一過濾全部 18 組 _INTERNAL_PATTERNS（修復 Bug1 群組術語洩漏 + Bug2 私訊自言自語的共同根因）；telegram_pump.py 消除 9 處 bot.send_message() 直送改走 adapter._safe_send()（Phase 0/1/2/3 + SLA interim + Escalation）；cron_registry.py Ares alert 改走 _safe_send()；telegram_menu.py 2 個函數加 ResponseGuard sanitize；update_processing_status() 加 sanitize；response_guard 扇入 2→3（新增 telegram_menu.py）。同步 system-topology v1.63。
> **v1.80 (2026-03-29)**：戰神系統（Ares）——新增 2 個 Skill 到綠區：`anima-individual`（ANIMA 個體追蹤引擎，扇入=1 from ares，扇出=8：wan-miu-16/energy-reading/combined-reading/shadow/master-strategy/xmodel/knowledge-lattice/user-model）、`ares`（戰神系統工作流，扇入=0，扇出=14：anima-individual/wan-miu-16/energy-reading/combined-reading/master-strategy/shadow/xmodel/pdeif/roundtable/business-12/ssa-consultant/knowledge-lattice/user-model/c15）。新增 Python 模組 `src/museon/ares/`（profile_store.py/graph_renderer.py/external_bridge.py）；新增儲存路徑 `data/ares/profiles/`。同步 system-topology v1.62、joint-map v1.52、memory-router v1.13、persistence-contract v1.40。
> **v1.79 (2026-03-29)**：OneMuse 能量解讀技能群——新增 3 個 Skill 到綠區：`energy-reading`（八方位能量解讀，扇入=0，扇出=4：dharma/resonance/knowledge-lattice/user-model）、`wan-miu-16`（萬謬16型人格，扇入=0，扇出=3：energy-reading/knowledge-lattice/user-model）、`combined-reading`（合盤能量比對，扇入=0，扇出=4：energy-reading/wan-miu-16/knowledge-lattice/user-model）。唯讀參考 `data/knowledge/onemuse/`（36 檔）。同步 system-topology v1.61、joint-map v1.51、memory-router v1.12、persistence-contract v1.39。
> **v1.78 (2026-03-28)**：新增 `doctor/musedoctor.py`（MuseDoctor 第六虎將，持續巡邏員，綠區扇入=0，扇出=2：topology_report.json 讀取 + nightly_pipeline.py 讀取）；`gateway/cron_registry.py` 新增 `musedoctor-patrol` job（每 8 分鐘）；新增共享狀態 `data/_system/doctor/patrol_state.json`（單一寫入者 musedoctor.py）。
> **v1.77 (2026-03-28)**：死碼清理 20 個模組後藍圖同步——從 topology_report.json 更新 fan_in 數據：event_bus 45→46、data_bus 16→15（channels/line 已刪）、gateway.message 13→14、pulse_db 10→11（新增 pulse/group_digest）、vector_bridge 7→9；移除已刪除模組條目：channels/electron、channels/line、llm/client、llm/vision、agent/dna27、agent/pending_sayings、agent/routing_bridge、doctor/scalpel_lessons、governance/cognitive_receipt、learning/strategy_accumulator、memory/epigenetic_router、memory/proactive_predictor、multiagent/flywheel_flow、pulse/heartbeat_activation、pulse/group_session_proactive、pulse/proactive_activation、pulse/telegram_pusher、security/trust、tools/document_export、tools/report_publisher；破損 import 修復：brain_fast.py 的 input_sanitizer + ceremony 兩個殘留 import；系統健康度快照更新。
> **v1.76 (2026-03-28)**：doctor 模組舊架構清除——`doctor/auto_repair.py` `repair_start_gateway()` + `repair_load_daemon()` 從 launchctl load/unload 改為 supervisorctl start（扇入不變）；`doctor/health_check.py` daemon 狀態檢查從 `launchctl list com.museon.gateway` 改為 `supervisorctl status museon-gateway`；`plist_path` 從 `com.museon.gateway.plist` 改為 `com.museon.supervisord.plist`；`doctor/surgeon.py` `_try_launchd_selfkill()` 從 launchctl 改為 supervisorctl（扇入不變）。完全消除舊 launchd-direct 架構在 doctor 模組的殘留，防止 auto_repair 觸發雙重管理衝突。
> **v1.75 (2026-03-28)**：supervisord 進程管理層——新增 `data/_system/supervisord.conf`（綠區扇入=0，純設定檔）；新建 `com.museon.supervisord.plist`（launchd 服務，KeepAlive=true）；`doctor/museoff.py` `_triage("restart_gateway")` 從呼叫 restart-gateway.sh 改為 supervisorctl start（Green 扇入=2，不影響其他模組）；`scripts/workflows/restart-gateway.sh` v3.0（從 launchctl 改 supervisorctl restart）。`com.museon.gateway.plist` 已 unload，launchd 改為 launchd→supervisord→gateway 三層架構，消除雙實例衝突根因。blast-radius 無新模組扇入變化（supervisord 是 infra 層，不引入 Python import）。
> **v1.74 (2026-03-28)**：Gateway 穩定性三項減法——`server.py` 新增 `/health/live` 純 liveness endpoint（不查 Brain/Telegram，綠區扇入=0，新增 endpoint）；`doctor/probes/liveness.py` 改查 `/health/live`（棄用 `/health` 深度檢查）+ 連續 3 次失敗才觸發重啟（消除暫時 timeout 誤判）；`scripts/workflows/restart-gateway.sh` v2.1（移除 `kickstart -k`，改用 `stop + kickstart`，等待改查 `/health/live`，等待時間 30→60s）；macOS fork() 限制確認 Gunicorn pre-fork 不可用（objc_initializeAfterForkError）。plist PATH 新增 `/usr/sbin`（修復 lsof 可用性）。gunicorn_config.py + start-gateway.sh 備用腳本存入 scripts/。
> **v1.73 (2026-03-27)**：MUSEON 自主能力三合一——tool_schemas.py 新增 restart_gateway + pending_action 2 個工具定義（綠區扇入=0）；tools.py 新增 3 個執行方法（_execute_restart_gateway、_execute_pending_action、mcp_add_server 同步 .mcp.json）；self_summary.json 新增 capabilities 欄位（can_do 14 項 + cannot_do 6 項）。
> **v1.72 (2026-03-27)**：MCP 工具擴充——新增 `.mcp.json` Playwright + Fetch 外部依賴（綠區扇入=0，純 MCP 設定）；外部服務節點 playwright-mcp + fetch-mcp 經由 mcp-server 接入，不影響既有模組。
> **v1.71 (2026-03-27)**：有機體進化計畫——新增 `pulse/proactive_dispatcher.py`（綠區扇入=2 from telegram+proactive_bridge）；`memory/memory_graph.py`（綠區扇入=1 from brain）；`learning/insight_extractor.py`（綠區扇入=1 from brain）；`learning/strategy_accumulator.py`（綠區扇入=0）；`doctor/shared_board.py`（綠區扇入=4 from museoff/qa/doc/worker）；`billing/trust_points.py`（綠區扇入=1 from brain_tools）；`nightly_pipeline.py` _FULL_STEPS 52→49（移除 7.5/10.5/11，新增 19）；`cron_registry.py` 9 處 push_notification 設置 source。
> **v1.70 (2026-03-26)**：v2 Brain 四層架構 + 死碼清理——新增 `brain_deep.py`（L2 Opus 引擎，綠區扇入=1）、`brain_tool_loop.py`（獨立 tool-use 迴圈，綠區扇入=1）；`brain_fast.py` 重寫為 L1 Sonnet + escalation JSON + L4 回饋迴路；新增 `brain_observer.py`（L4 觀察者，綠區扇入=1）；`tool_schemas.py` 新增 trigger_job/memory_search/spawn_perspectives 3 個工具；`nightly_pipeline.py` 新增 Step 31 context_cache 重建。死碼移除：`federation/`（skill_market + sync）、`installer/`（整個目錄）、`nightly_v2.py`。
> **v1.69 (2026-03-25)**：五虎將通知人類化——新增 `doctor/notify.py`（綠區扇入=2 from museoff+museqa，共用通知：notify_owner 中文嚴重度+來源+說明、explain_finding 15 種模式翻譯、generate_review_summary 待審閱摘要）；MuseOff WAL 偵測改 PRAGMA journal_mode（修復 .db-wal 假陽性）+新增 3 DB 檢查；MuseOff/MuseQA 刪除各自 _notify_owner 改用共用版。
> **v1.68 (2026-03-25)**：L2 Worker 分離 + AIORateLimiter——新增 `gateway/brain_worker.py`（BrainWorkerManager，subprocess + Pipe IPC，auto-restart，綠區扇入=1 from telegram_pump.py + server.py init/shutdown）；`llm/rate_limiter.py` 新增 `AsyncTokenBucket`（token bucket 頻率控制，4 req/s 預設，支援 pause/slow_down/speed_up）+ `get_api_bucket()` singleton；`gateway/telegram_pump.py` `_brain_process_with_sla` 新增 worker 優先路徑 + fallback in-process 改用 token bucket 取代 semaphore；`gateway/server.py` startup/shutdown 新增 worker lifecycle 管理。
> **v1.67 (2026-03-25)**：訊息佇列持久化 + 全鏈路 trace_id——新增 `gateway/message_queue_store.py`（SQLite 持久化佇列，綠區扇入=1 from telegram_pump.py + server.py lazy init）；`gateway/message.py` InternalMessage 新增 trace_id 欄位（uuid hex[:12] 自動生成）；`gateway/telegram_pump.py` 新增 `_recover_pending_messages()`（啟動恢復）+ pump 主迴圈持久化 enqueue/mark_done + 關鍵 log 全加 trace_id；`agent/brain.py` process() 入口 log trace_id；`gateway/server.py` startup 初始化 MessageQueueStore。
> **v1.66 (2026-03-25)**：Brain 90 秒 SLA + Circuit Breaker——`telegram_pump.py` 新增 `_brain_process_with_sla()` wrapper（90 秒未完成送暫時回覆，繼續等待），brain.process() 兩處主要呼叫改走 SLA wrapper；`bulkhead.py` 新增 `BrainCircuitBreaker` class + `get_brain_circuit_breaker()` singleton（CLOSED→OPEN→HALF_OPEN 三態，連續 3 次失敗斷路，60 秒 cooldown 試探恢復），telegram_pump.py lazy import；`server.py` startup 新增 Circuit Breaker 通知回調（DM 老闆）+ /health 端點新增 circuit_breaker 狀態。扇入變化：bulkhead.py 扇入 1→2（server.py + telegram_pump.py）。
> **v1.65 (2026-03-25)**：對話持久化+教訓蒸餾+斷裂管線修復——telegram.py 新增 DM/Bot 回覆落地；group_context.py 截斷 8000+personality 欄位；nightly_pipeline Step 5.6.5+18.5+_FULL_STEPS 補列+報告歷史；crystal_actuator 類型過濾+保護規則；brain_prompt_builder Intuition+record_success+logger 升級；server.py Guardian queue 消費；multi_tenant dict topics+str→Path；knowledge_lattice 門檻+limit；brain.py user_id→boss；morphenix_validator str→dict；telegram_pump session_manager→dict；cron_registry NameError 修復；musedoc Fix-Verify 整合。新增 fix-verify Workflow。
> **v1.64 (2026-03-25)**：server.py 拆分藍圖補齊 + 三層內部標記洩漏預防——server.py 從 5749→3800 行，拆出 `telegram_pump.py`（754 行，Telegram 訊息泵+ResponseGuard 整合，黃區扇入=1 扇出=8）、`routes_api.py`（689 行，SkillHub+外部整合 API 端點，綠區扇入=1）、`cron_registry.py`（1424 行，系統 cron 任務註冊，綠區扇入=1）。修正 response_guard 重複條目。三層防禦：L1 `brain_prompt_builder.py` 新增 Style Never #6/#7（禁止【】標記+操作確認句）；L2 `telegram_pump.py` v10.8 Brain 輸出結構化剝離（regex 移除思考標記區塊）；L3 `response_guard.py` `_INTERNAL_PATTERNS` 新增 3 組 pattern（【】標記/操作確認句/AI 後設描述）。`restart-gateway.sh` 新增 Step 1.5 強制 rsync（防 .runtime 過期）。
> **v1.62 (2026-03-24)**：全面審計修正——event_bus 扇入 117→45（區分直接 import vs 事件關聯度）；message 20→13、data_bus 13→16、pulse_db 14→10、brain 3→1、module_registry 4→1；tool_registry 從紅區降為黃區（18→4）；dispatch 從紅區降為黃區（11→2）；補列 8 個新模組（brain_*.py Mixin 系列 + chat_context + deterministic_router + vision + push_budget）；更新統計摘要。
> **v1.61 (2026-03-24)**：操作記憶層架構——新增第六張藍圖 `operational-contract.md`；新增 `scripts/workflows/` 可執行工作流腳本（publish-report.sh v4.0 綠區扇入=0、restart-gateway.sh v1.0 綠區扇入=0）；CLAUDE.md 新增 Tier 0 可執行性檢查 + 驗證鐵律。扇入扇出不變（純文件/腳本/CI 層變更，不影響 Python 模組）。
> **v1.60 (2026-03-24)**：跨群組洩漏防禦 + 軍師認知升級——新增 `governance/response_guard.py` 到綠區（扇入=2：server.py + brain.py，ResponseGuard 發送前 chat_id 二次驗證閘門）；`governance/multi_tenant.py` 新增 `resolve_by_id()` 精確匹配（取代 FIFO `resolve_latest()`）；`brain.py` 新增 `_check_smart_completeness()` SMART 回答門檻 + `process()` finally 清空 `self._ctx` 及 6 個 alias（防跨群組殘留）+ `route()` 新增 `is_group` 參數傳遞；`brain_prompt_builder.py` 注入「軍師認知框架」system prompt + 群組禁止確認詞規則；`brain_p3_fusion.py` 新增 Roundtable ≥3 Skill 自動觸發融合；`reflex_router.py` `select_loop()`/`route()` 新增 `is_group` 參數（群組路由升級）；`server.py` session lock 改為 `wait_and_acquire(30s)` timeout 守衛。**注意**：軍師認知升級的修改在 `.runtime/src/museon/agent/` 中（gitignored），`src/` 合併版未同步。
> **v1.58 (2026-03-23)**：OAuth Token 韌性重構——`adapters.py` `ClaudeCLIAdapter._get_oauth_token()` 從 2 層來源升級為 4 層：環境變數 → 持久化文件 → Claude Desktop credentials（`~/.claude/.credentials.json` 自動續期）→ 備份文件（永不刪除的最後防線）；Token 過期時不再 `unlink` 而是備份到 `.bak` + 標記 `.stale`（永不刪除策略）；`create_adapter_sync()` CLI-only 模式也包裝為 FallbackAdapter（支援 extended_thinking 等進階參數）；`preflight.py` ANTHROPIC_API_KEY 從必要降為選填（Max 方案用 CLI OAuth）。
> **v1.57 (2026-03-23)**：Claude 原生能力全面接入——新增 `llm/vision.py`（Multimodal 圖片+PDF content block 構建，扇入 1：brain.py）；`brain.py` L1211 注入 `build_multimodal_content()` 構建 Vision/PDF content blocks（扇出 +1：vision.py）；`adapters.py` AnthropicAPIAdapter.call() 新增 `extended_thinking` + `thinking_budget` 參數，AdapterResponse 新增 `thinking` 欄位，新增 `count_tokens()` / `create_batch()` / `get_batch_status()` / `get_batch_results()` 方法（API 面不變）；FallbackAdapter.call() 新增 `extended_thinking` 傳遞（thinking 時直接走 API，CLI 不支援）；`brain_tools.py` `_call_llm()` 新增 `loop` 參數，SLOW_LOOP + 無 tool-use 時自動啟用 Extended Thinking；`budget.py` 新增 `count_tokens_precise()` + `set_api_adapter()` 接入 Token Counting API；`adapters.py` CLI `_build_prompt()` 新增 image/document type graceful degradation。
> **v1.56 (2026-03-23)**：DSE 根因修復——`server.py` `_pre_start_cleanup` 失敗後 `sys.exit(1)` 停止 crash loop；`adapters.py` OAuth token 清除條件精準化（排除 stdin timeout）；`tool_registry.py` Docker 容器停止保持 enabled=True；`gateway_lock.py` timeout 5→30s；`adapters.py` FallbackAdapter 雙失敗友善降級回覆。
> **v1.55 (2026-03-23)**：194 節點健康檢查——`budget.py` fd 雙重關閉修復；`server.py` 3 處 data_dir NameError 修復；`brain.py` AnimaChangelog 接線（getattr→正式初始化）；`brain_dispatch.py` @staticmethod self→類別引用；`brain_tools.py` model 記錄從二元判斷改為實際值。
> **v1.54 (2026-03-23)**：推送品質修復——新增 `pulse/push_budget.py`（PushBudget 全局推送預算管理器，扇入 0、扇出 1：pulse_db）；`pulse_engine.py` 新增 import push_budget（扇出 +1）；`proactive_bridge.py` 新增 import push_budget（扇出 +1）；`gateway/server.py` 新增 PushBudget 初始化注入（扇出 +1）；`channels/telegram.py` 新增 `_split_long_text()` 靜態方法（扇入扇出不變）；`pulse/explorer.py` `_topics_similar()` 閾值修改（扇入扇出不變）。
> **v1.52 (2026-03-23)**：三層調度員架構——新增 dispatcher/thinker/worker 扇入扇出分析；新增 museon-persona.md 影響分析。Brain P3 Fusion 健康檢查——`agent/brain_p3_fusion.py` 常數化 25+ 個魔術值（P2 決策層 LLM 參數/P3 策略層 LLM 參數/信號偵測閾值/決策偵測閾值/融合決策權重與閾值/精煉偏好）收斂到類別頂部；7 個 LLM 視角生成失敗從 `logger.debug` → `logger.warning`（production 不再隱藏 API 呼叫失敗）；`asyncio.get_event_loop()` → `asyncio.get_running_loop()`（2 處，修復 Python 3.10+ 棄用警告）；`_execute_p3_parallel_fusion` 死碼清理（移除未使用 `lines` 變數 + DEPRECATED 標記格式化）；`_refine_with_precog_feedback` anima_user 載入失敗從 `logger.debug` → `logger.warning`；新增 `tests/unit/test_brain_p3_fusion.py`（48 個測試涵蓋常數/P3 信號偵測/P2 決策偵測/反問綜合/融合權重/asyncio API/前置融合/精煉邏輯）。扇入扇出不變、無新增 import。
> **v1.51 (2026-03-22)**：Brain Prompt Builder 健康檢查——`agent/brain_prompt_builder.py` 常數化 20+ 個魔術值（Token 預算 zone/動態倍數/結晶閾值/演化覺醒閾值/失敗蒸餾）收斂到類別頂部；Token zone 耗盡時 logger.warning（提示哪些 zone 被沉默截斷）；`budget.remaining()` 返回 None 防禦（`or 0`）；新增 `tests/unit/test_brain_prompt_builder.py`（22 個測試涵蓋常數/演化覺醒/身份生成）；system-topology v1.41 補齊 brain-prompt-builder→anima-mc-store/data-bus/anthropic-api 3 條遺漏連線。扇入扇出不變、無新增 import。
> **v1.50 (2026-03-22)**：Brain Tools 健康檢查——`agent/brain_tools.py` 常數化 8 個魔術值（_MAX_TOKENS_PRIMARY/DISPATCH/HEALTH_PROBE、_MAX_TOOL_ITERATIONS_COMPLEX/SIMPLE、_TOOL_RESULT_TRUNCATE_LEN、_COMPLEX_KEYWORDS、_OFFLINE_PROBE_INTERVAL）收斂到類別頂部；`nightly/nightly_pipeline.py` Step 27 擴充按日期 JSONL 清理（cache_log_*/routing_log_* 保留 30 天超齡刪除）；新增 `tests/unit/test_brain_tools.py`（16 個測試涵蓋常數/LLM 呼叫/離線/Session）；system-topology v1.40 補齊 brain-tools→anthropic-api + brain-tools→data-bus 2 條遺漏連線。扇入扇出不變、無新增 import。
> **v1.49 (2026-03-22)**：Zeal 節點健康檢查修復——`gateway/authorization.py` PairingManager.load() + AuthorizationPolicy.load() 首次載入時自動初始化空檔案（allowlist.json / policy.json），解決重啟後配對使用者遺忘問題；system-topology.md v1.39 補齊 3 條遺漏連線（zeal/verified-user/external-user → anima-mc-store）。扇入扇出不變、無新增 import。
> **v1.48 (2026-03-22)**：DeterministicRouter 三項外部化——`agent/deterministic_router.py` 移除 `_CATEGORY_PRIORITY`（27 個 Skill 硬編碼）和 `force_sonnet`（5 個 Skill 硬編碼），改為：(1) 優先級由 Skill Manifest 的 `hub` 欄位透過 `_HUB_PRIORITY` 映射表驅動（9 個 Hub → 8 級優先級），新增 Skill 時無需改源碼；(2) `model_preference` 由 Manifest 欄位驅動，5 個 Skill SKILL.md 新增 `model_preference: sonnet`；(3) `depends_on` 由 `io.inputs[].from` 推導任務間依賴。`agent/skill_router.py` `_extract_metadata` 新增提取 `model_preference` + `io_inputs` 欄位，新增 `_extract_io_inputs()` 靜態方法。扇入扇出不變、無新增 import 路徑。
> **v1.48 (2026-03-22)**：L3-A2 Brain Mixin 拆分——brain.py 從 9164 行拆分為核心（2575 行）+ 5 個 Mixin：`brain_prompt_builder.py`（1668 行，system prompt 建構）、`brain_dispatch.py`（1082 行，任務分派）、`brain_observation.py`（2003 行，觀察與演化）、`brain_p3_fusion.py`（948 行，P3 策略融合與決策層）、`brain_tools.py`（966 行，LLM 呼叫與 session 管理）。新增 `brain_types.py`（共享 dataclass：DecisionSignal、P3FusionSignal）。實作方式為 Python Mixin Pattern（多重繼承），`server.py` 的 `from museon.agent.brain import MuseonBrain` 不變。brain.py 扇入扇出不變、外部 API 不變。更新 `test_brain_observe_scope.py` 支援 Mixin 檔案 AST 掃描。
> **v1.47 (2026-03-22)**：Brain 三層治療——L1 止血：`_build_memory_inject` metadata NameError 修復（`self._current_metadata`）、`_parse_orchestrator_response` JSON 解析增強（code fence strip + 單物件 fallback + debug 日誌）、Orchestrator prompt 尾部 JSON 約束強化、RootCause 空字串日誌過濾；L2 免疫：新增 `agent/chat_context.py`（ChatContext dataclass，取代 7 個 self._* per-turn 變數，扇入 1：brain.py）、`_build_system_prompt` memory inject except 分級示範（CORE/OPTIONAL 分離）、PulseDB 新增 `orchestrator_calls` 表（診斷數據收集）；L3-A1：新增 `agent/deterministic_router.py`（確定性任務分解器，取代 LLM Orchestrator 呼叫，扇入 1：brain.py），`_dispatch_mode` 改為確定性路由優先、LLM fallback。扇入扇出：brain.py 新增 2 個 import（chat_context、deterministic_router），PulseDB 新增 1 張表。外部 API 不變。
> **v1.46 (2026-03-22)**：P0-P3 升級——report-forge 新增 crystal.db 寫入依賴（via knowledge-lattice API，report_crystal 結晶化）；token_optimizer.py buffer 預算 2800→1800（strategic zone 1000 新增）；brain.py 新增 `_build_strategic_context()`（純新增方法，不改既有流程）；anima_mc_store.py/pulse_engine.py 新增 `_backup_before_write()`/`_backup_pulse_md()`（寫入前快照，新增共享狀態 `_system/backups/`）；plan_engine.py bug 修復（plan.changes → plan.change_list，純內部修正）
> **v1.44 (2026-03-22)**：InteractionRequest 跨通道互動層——新增 `gateway/interaction.py`（InteractionQueue，扇入 4：telegram/discord/line callback + server.py message pump）；`gateway/message.py` 純新增 3 個 dataclass（ChoiceOption/InteractionRequest/InteractionResponse）+ BrainResponse.interaction 欄位（不改現有消費者）；`channels/base.py` 新增 `present_choices()` 非抽象方法（帶 fallback，不影響現有 8 adapter）；`channels/telegram.py` 新增 CallbackQueryHandler `choice:` prefix + `present_choices()` 覆寫 + freetext 攔截（不改現有 `pair:/auth:/morphenix:` handlers）；`channels/discord.py` 新增 `present_choices()` + Button/Select View；新增 `channels/line.py`（LINE adapter，扇入 0）；`gateway/server.py` message pump 新增互動攔截邏輯（BrainResponse.has_interaction() → present → wait → followup）
> **v1.43 (2026-03-22)**：Recommender 激活修復——`agent/recommender.py` 資料來源從過時的 JSON 掃描（`data/crystals/*.json` + `data/skills/*.json` + `_system/knowledge_graph.json`）改為 CrystalStore API（`load_crystals_raw()` + `load_links()`）；`__init__()` 新增 `crystal_store` 參數（取代 `memory_manager`）；互動歷史路徑從 `_system/recommendations/` 改為 `data/_system/recommendations/`；`_save_interactions()` 改用原子寫入（tmp→rename）；`brain.py` `__init__()` 新增 `_recommender` 初始化（~L320，降級保護）+ init log 新增 recommender 狀態；`server.py` `/api/recommendations` 改用 Brain 常駐實例（移除每次重新實例化模式）；扇入 0→1（brain.py import），新增共享狀態 `_system/recommendations/interactions.json`
> **v1.42 (2026-03-22)**：Workflow Hub 健康檢查——P0: 清除「案例結晶」幽靈殘留（Qdrant skills 1 筆、synapses.json 8 筆、PulseDB metacognition 3 筆），Business Hub 修復漏清下游資料池的根因補完；P0b: `evolution/skill_synapse.py` co_fire() 新增 Skill 名稱合法性驗證（regex `^[a-z][a-z0-9\-]{0,60}$`），防止非法名稱建立突觸；P1: `agent/brain.py` `_dispatch_orchestrate` 排除 `type: workflow` 的 Skill 不注入 Orchestrator skill_roster（Workflow 是編排範本非 Worker 候選），`_parse_orchestrator_response` 改用 worker_skills 驗證；P2: `agent/metacognition.py` `_emit_quality_flag` 新增 `_WORKFLOW_SKILL_NAMES` 白名單，過濾 workflow 類 Skill 不計入品質旗標，missing_action 類別且全為 workflow 時跳過發布；扇入扇出不變、無新增 import/共享狀態
> **v1.40 (2026-03-22)**：Business Hub 健康檢查——skill_router.py `_extract_metadata` YAML 解析修復：只匹配頂層（未縮排）`name:`/`description:`/`type:` 欄位，防止 workflow stages 的巢狀 `name:` 覆蓋頂層 Skill 名稱（幽靈 Skill `"案例結晶"` 根因）；同時剝除 YAML 引號防止 literal quote 汙染；清理 synapses.json 3 筆幽靈條目；consultant-communication memory.writes 補齊 target/type/condition 結構；扇入不變（2）、無新增 import
> **v1.39 (2026-03-22)**：Thinking Hub 健康檢查——brain.py `_dispatch_orchestrate` Orchestrator system prompt 移除硬編碼 Skill 名稱範例（`resonance`），Rule 4 強化約束防止 LLM 幻覺引用 roster 外 Skill；shadow SKILL.md `layer: business` → `layer: thinking` 修正欄位漂移；純 prompt 文字修改，扇入扇出不變、無新增 import/共享狀態
> **v1.36 (2026-03-21)**：Evolution Hub 健康檢查修復——outward_trigger `_ensure_state_files()` 初始化 + tantra 孤立輸出修復 + morphenix/proposals 目錄補建
> **v1.35 (2026-03-21)**：Telegram 授權系統升級——新增 `gateway/authorization.py`（ApprovalQueue + ToolAuthorizationQueue + PairingManager + AuthorizationPolicy）；`security.py` check_tool_access() 三級策略路由；`telegram.py` 配對/授權 handlers；`server.py` 授權回覆分支；`mcp_server.py` museon_auth_status 工具；新增持久狀態 `~/.museon/auth/`
> **v1.34 (2026-03-21)**：環境感知 + 工程護欄——brain.py 新增 `_build_environment_awareness()` v11.3（modules zone 環境能力宣告）+ `_build_self_modification_protocol()` v11.4（buffer zone 自我修改協議）+ `_current_source` + `_self_modification_detected`；新增 Claude Code Hooks（PreToolUse blast-radius 自動查核 + Stop 未 commit 提醒）；新增 `scripts/generate_iteration_report.py`（迭代報告 HTML 生成器）
> **v1.33 (2026-03-21)**：Skill 鍛造膠合層修復——VectorBridge 新增 index_all_skills()/reindex_all()；server.py startup 新增 skills 索引；nightly Step 8.6 skill_vector_reindex；plugin-registry v2.3（+12 Skill）；49 個 Skill Manifest 補齊 memory/io 欄位
> **v1.27 (2026-03-20)**：brain.py P3 前置交織融合——新增 `_p3_gather_pre_fusion_insights()`，Phase 4.5 輕量簽名，`_execute_p3_parallel_fusion` 降級為向後相容

---

## 快速索引 — 修改安全分級

| 級別 | 定義 | 模組數 | 施工規則 |
|------|------|--------|---------|
| 🔴 **禁區** | 扇入 ≥ 40，修改影響全系統 | 1 | 除非系統級重構計畫，**禁止修改** |
| 🟠 **紅區** | 扇入 10-39 或系統核心（扇出極大） | 4 | 必須回報使用者 + 全量 pytest + 影響分析 |
| 🟡 **黃區** | 扇入 2-9，修改影響 2+ 模組 | 65 | 查 blast-radius + joint-map，跑相關測試 |
| 🟢 **綠區** | 扇入 0-1，修改不影響上游 | 174 | 可直接修改，跑單元測試即可 |

---

## 🔴 禁區模組（1 個）

### core/event_bus.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 46（直接 import，19% 的模組依賴它） |
| **角色** | 全域事件匯流排，定義 215 個事件常量 |
| **共享狀態** | 無直接檔案讀寫，但事件流是隱性共享狀態 |

#### 影響半徑

| 影響類型 | 數量 | 說明 |
|---------|------|------|
| 直接 import | 46 個模組 | agent(7), channels(5), nightly(7), pulse(4), governance(5), evolution(5), doctor(4), tools(3), 其他(6)（注：channels/line、channels/electron 已刪除，tools/rss_aggregator、tools/zotero_bridge 已確認接線） |
| 間接影響 | 全系統 | 事件常量或 API 改動 → 所有訂閱/發布模組失效 |
| 事件發布者 | 47 個模組 | 發布 59 種事件 |
| 事件訂閱者 | 16 個模組 | 訂閱 31 種事件 |

#### 安全操作 vs 危險操作

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增事件常量（不影響現有） | 修改/刪除事件常量名稱 |
| 新增 `on()`/`emit()` 方法的 optional 參數 | 修改 `emit()` 或 `on()` 的簽名 |
| 新增文件/註釋 | 修改事件分發邏輯 |
| — | 修改 EventBus 初始化邏輯 |

#### 事件健康度

```
已定義事件：215 | 實際發布：59 | 有訂閱者：31 | 孤兒事件：38 | 幽靈訂閱：0（已全部修復）
事件健康度 ≈ 67.9%（幽靈訂閱清零後提升）
```

---

## 🟠 紅區模組（5 個）

### gateway/server.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 0（入口點，無人 import） |
| **扇出** | 50+（import 50+ 模組） |
| **行數** | 3800 行（v1.64 拆分後；原 5749 行拆出 telegram_pump/routes_api/cron_registry） |
| **角色** | FastAPI 閘道器，管理 30+ app.state；訊息泵/API 端點/cron 註冊已拆至獨立模組 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態讀寫 | ANIMA_MC.json(RW), ANIMA_USER.json(R), nightly_report.json(R), PulseDB(RW — P2 新增 incidents 寫入) |
| 事件訂閱 | 5 個：BRAIN_RESPONSE_COMPLETE, EXPLORATION_CRYSTALLIZED, EXPLORATION_INSIGHT, NIGHTLY_COMPLETED, RELATIONSHIP_SIGNAL |
| 直接影響 | 所有 API 端點、WebSocket 連線、前端 Electron |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增獨立 API 端點 | 修改 `app.state` 的共享變數 |
| 修改 API 回應格式（不影響前端時） | 修改 `_build_system_prompt()` |
| 新增中間件（不影響既有路由） | 修改 `lifespan()` 初始化順序 |
| 修改日誌格式 | 修改 ANIMA_MC.json 的讀寫邏輯 |
| `wait_and_acquire()` timeout 守衛（v1.60） | 修改 `_process_lock` 鎖策略 |

---

### gateway/message.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 14 |
| **角色** | 訊息格式定義（Message, ChatMessage 等資料類別） |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 直接 import | 14 個模組：server.py, brain.py, workflow_executor.py, interaction.py, webhook.py, telegram.py, slack.py, email.py, discord.py, base.py, tools.py, brain_worker.py, routes_api.py, telegram_pump.py（注：channels/line、channels/electron 已刪除） |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增 optional 欄位 | 修改/刪除既有 Message 欄位 |
| 新增新的 Message 子類 | 修改序列化/反序列化邏輯 |

---

### core/data_bus.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 16 |
| **角色** | 資料層路由器 + DataContract 協議 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 直接 import | 15 個模組：agent(3), core(3), pulse(2), nightly(1), governance(2), memory(1), workflow(2)（注：channels/line 已刪除，data_bus fan_in 從 16→15） |
| 共享狀態 | DataContract 規範所有 Store 的讀寫格式 |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增 Store 類型 | 修改 DataContract 介面 |
| 新增查詢方法 | 修改 `get_store()` / `register_store()` |
| 新增監控指標 | 修改 Store spec 格式 |

---

### pulse/pulse_db.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 11 |
| **角色** | VITA 生命力引擎的 SQLite 後端（14 張表） |
| **共享狀態** | PulseDB (pulse.db) — 詳見 joint-map #8 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 直接 import | 11 個模組：server.py, brain.py, nightly_pipeline.py, telegram.py, eval_engine.py, metacognition.py, brain_prompt_builder.py, brain_dispatch.py, onboarding/ceremony.py, cron_registry.py, pulse/group_digest.py（fan_in 從 10→11，基於 topology_report） |
| 資料依賴 | 11 個模組讀取其表 |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增表 | 修改既有表的 schema |
| 新增查詢方法 | 修改 `get_pulse_db()` 單例邏輯 |
| 新增索引 | 修改 WAL/busy_timeout 設定 |
| — | 修改 threading.Lock 策略 |

---

## 🟠 紅區模組（續）— 以扇出/關鍵度入列

### agent/brain.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 1（server.py；入列紅區因扇出 32+ 且為系統核心） |
| **扇出** | 32+（import 32 個模組，初始化全系統——含 PrimalDetector, MultiAgentExecutor, MemoryGate） |
| **角色** | 系統核心——LLM 對話、記憶、自我觀察、所有子系統初始化、多代理並行呼叫、記憶閘門意圖判斷、認知追蹤（trace_decision+trace_cognitive）、P3 並行融合（Step 6.2-6.5）、P0 訊號六類分流（_classify_p0_signal）、事實糾正偵測（_detect_fact_correction）、外部使用者觀察（_observe_external_user v3.0 含 trust evolution + 八原語 + L6 溝通風格）、環境感知宣告（_build_environment_awareness v11.3）、自我修改協議（_build_self_modification_protocol v11.4） |
| **檔案數** | v1.48 起拆分為 7 個檔案：`brain.py`（核心 2575 行）+ 5 個 Mixin（`brain_prompt_builder.py` 1668 行、`brain_dispatch.py` 1082 行、`brain_observation.py` 2003 行、`brain_p3_fusion.py` 948 行、`brain_tools.py` 966 行）+ `brain_types.py`（共享 dataclass）。Python Mixin Pattern 多重繼承，外部 import 路徑不變。 |

**P3 方法群：**
- `_p3_gather_pre_fusion_insights()` (新增 v1.22: 前置融合注入 system_prompt)
- `_detect_p3_strategy_layer_signal()`
- `_execute_p3_parallel_fusion()` (v1.22 起降級為向後相容)
- `_p3_strategy_perspective()`
- `_p3_human_perspective()`
- `_p3_risk_perspective()`

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態讀寫 | ANIMA_MC.json(RW), ANIMA_USER.json(RW+L8群組), PULSE.md(R), PulseDB(R), Qdrant(W), Qdrant:primals(R via PrimalDetector), diary_entries(R), synapses(R), memory(R/W+dept_id+chat_scope), fact_corrections.jsonl(RW), cognitive_trace.jsonl(W via footprint.trace_cognitive+trace_decision), lord_profile.json(RW: R via Step 3.65 百合引擎, W via _observe_lord), external_users/{uid}.json(RW via ExternalAnimaManager v3.0), activity_log.jsonl(R via search()) |
| 子系統初始化 | 31 個模組在 Brain.__init__() 中初始化（含 PrimalDetector, DiaryStore, MultiAgentExecutor, FlywheelCoordinator） |
| System Prompt | `_build_soul_context()` + `_build_system_prompt()` 決定 AI 所有行為 |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 修改 `_chat()` 的回應後處理 | 修改 `__init__()` 的初始化順序 |
| 新增獨立觀察方法（如 `_handle_fact_correction()`, `_observe_lord()`, `_observe_external_user()`, `_classify_p0_signal()`, `_detect_fact_correction()`, `_build_environment_awareness()`, `_build_self_modification_protocol()`, `_build_strategic_context()`, `_check_smart_completeness()`） | 修改 `_build_soul_context()` |
| Step 8 trace_decision/trace_cognitive 呼叫（純寫入足跡） | 修改 trace 呼叫的觸發條件 |
| 修改日誌格式 | 修改 `_save_anima_mc()` / `_load_anima_mc()` |
| — | 修改 `_anima_mc_lock` 鎖策略 |
| — | 新增/修改 system prompt 注入來源 |

#### ⚠️ 必須同時檢查的模組組

修改 brain.py 時，必須檢查 **G1（ANIMA 數值）+ G3（記憶管線）**（見 joint-map）

---

---

## 🟡 黃區重點模組

> 以下列出扇入 2-9 且觸及共享狀態的重要模組。完整黃區模組不逐一列出。

### tools/tool_registry.py（v1.62 從紅區降級）

| 屬性 | 值 |
|------|-----|
| **扇入** | 3（server.py, nightly_pipeline.py, doctor/self_diagnosis.py） |
| **角色** | 工具註冊與管理中心 |
| **事件發布** | TOOL_DEGRADED, TOOL_HEALTH_CHANGED, TOOL_RECOVERED |

---

### agent/dispatch.py（v1.62 從紅區降級）

| 屬性 | 值 |
|------|-----|
| **扇入** | 2（server.py, brain_dispatch.py） |
| **角色** | 訊息分發路由器 |

---

### evolution/outward_trigger.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 2（nightly_pipeline, wee_engine） |
| **角色** | 外向演化觸發器——偵測品質下滑、技能高原，觸發外部研究 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態讀寫 | `_system/outward/` 目錄（6 個 JSON）、`_system/wee/plateau_alerts.json`(R)、`_system/morphenix/notes/`(R) |
| 事件訂閱 | SKILL_QUALITY_SCORED, USER_FEEDBACK_SIGNAL |
| 事件發布 | OUTWARD_SEARCH_NEEDED |
| 下游影響 | intention_radar → research_engine → digest_engine |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 修改觸發閾值 | 修改事件發布格式 |
| 新增觸發訊號來源 | 修改 cooldown 邏輯 |

---

### evolution/wee_engine.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 3（nightly_pipeline, data_bus, brain） |
| **角色** | WEE 演化引擎——工作流五維度評分、結晶寫入 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態 | WorkflowStateDB(RW)、crystal.db(W via CrystalStore) |
| 事件發布 | SKILL_QUALITY_SCORED, WEE_CYCLE_COMPLETE |
| 跨模組依賴 | workflow/models.py, workflow/workflow_engine.py, agent/knowledge_lattice.py |

---

### evolution/evolution_velocity.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 2（nightly_pipeline） |
| **角色** | 演化速度測量——週間快照、多維指標計算 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態讀取 | crystal.db(R via CrystalStore), immunity/events.jsonl(R), accuracy_stats.json(R), skill_usage_log.jsonl(R), morphenix/proposals/(R) |
| 共享狀態寫入 | velocity_log.jsonl(W) |

---

### guardian/daemon.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 1（gateway/server.py 啟動） |
| **角色** | 系統守護 Daemon——核心檔案修復、健康巡邏 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態讀寫 | ANIMA_MC.json(RW), ANIMA_USER.json(RW), crystal.db(R via CrystalStore), diary_entries(R), workflow/workflows.json(RW) |
| 共享狀態寫入 | guardian/repair_log.jsonl(W), guardian/unresolved.json(W), guardian/state.json(W) |
| 跨模組依賴 | security/audit.py, doctor/code_analyzer.py |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增巡邏項目 | 修改 ANIMA_MC/USER 修復邏輯 |
| 修改日誌格式 | 修改守護循環間隔 |

#### ⚠️ 必須同時檢查的模組組

修改 guardian/daemon.py 時，必須檢查 **G1（ANIMA 數值）+ G6（免疫系統）**（見 joint-map）

---

### doctor/system_audit.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 2（nightly_pipeline, service_health） |
| **角色** | 7 層 46 項系統審計 + Skill Doctor 認知層審計（12 項 `_sd_check_*` 子檢查） |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態讀取 | ANIMA_MC.json(R), ANIMA_USER.json(R), diary_entries(R), crystal.db(R via CrystalStore), pulse.db(R), cognitive_trace.jsonl(R) |
| 事件發布 | AUDIT_COMPLETED |
| 跨模組依賴 | service_health（交叉驗證）, data_watchdog（健康檢查）, health_check |
| 新增方法 | `_audit_skill_doctor()` + 12 個 `_sd_check_*` 子方法（認知層檢查）；`_check_skills` glob bug 修復 |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增審計層/項目 | 修改審計結果格式（影響 governor 訂閱） |
| 新增 `_sd_check_*` 子檢查 | 修改 health_check 整合邏輯 |
| 修改日誌輸出 | 修改 `_check_skills` glob 路徑 |

---

### mcp_server.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 0（獨立入口點） |
| **扇出** | 5+（讀取 ANIMA_MC, ANIMA_USER, PulseDB 等） |
| **角色** | Claude Code MCP 介面——暴露 MUSEON 狀態給外部 AI |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態讀取 | ANIMA_MC.json(R), ANIMA_USER.json(R) |
| 外部影響 | Claude Code 使用此介面查詢 MUSEON 狀態 |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增暴露的查詢端點 | 修改回傳的 ANIMA 資料格式 |
| 新增過濾/摘要邏輯 | 新增寫入能力（目前只讀） |

---

---

### nightly/morphenix_validator.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 1（nightly_pipeline.py） |
| **角色** | Docker 沙盒驗證器——L2+ 提案在隔離容器中跑 pytest，通過才放行到 executor |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 外部依賴 | Docker daemon + `museon-validator:latest` image |
| 共享狀態讀 | morphenix/proposals/（#15）|
| 降級行為 | Docker 不可用→跳過驗證（`docker_unavailable_skip`），image 缺失→跳過（`docker_image_missing_skip`） |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 修改 DOCKER_TIMEOUT | 修改 passed=True 的 skip 邏輯（會讓不安全提案放行） |
| 修改 RSYNC_EXCLUDES | 移除 `--network=none` 隔離（安全護欄） |
| 新增語法檢查規則 | 修改 Docker CMD（影響 pytest 範圍） |

---

### pulse/pulse_engine.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 4 |
| **角色** | VITA 生命脈搏引擎——探索、反思、PULSE.md 寫入 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態寫入 | PULSE.md（7 種寫入方法）、question_queue.json(R)、`_system/backups/pulse_md/`（寫入前快照） |
| 事件發布 | EXPLORATION_CRYSTALLIZED, EXPLORATION_INSIGHT, PROACTIVE_MESSAGE, PULSE_EXPLORATION_DONE |
| 下游影響 | brain.py（透過 PULSE.md → system prompt）、exploration_bridge、curiosity_router |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 修改反思文字生成邏輯 | 修改 PULSE.md 的 section header |
| 新增統計指標 | 修改探索佇列的格式 |
| — | 修改 `_seed_followup_topics()` |
| — | 修改 `_write_reflection_to_pulse()` 的保留策略 |

---

### pulse/anima_mc_store.py ★ NEW

| 屬性 | 值 |
|------|-----|
| **扇入** | 4（brain, anima_tracker, micro_pulse, server） |
| **角色** | ANIMA_MC.json 統一存取層（合約 1）+ 寫入前快照備份 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態 | ANIMA_MC.json — **所有讀寫的唯一入口**；`_system/backups/anima_mc/`（寫入前快照） |
| 上游依賴 | brain.py, anima_tracker.py, micro_pulse.py, server.py |
| 鎖機制 | ✅ `threading.Lock` + KernelGuard + 原子寫入（三重保護） |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增健康檢查指標 | 修改 Lock 策略 |
| 新增 update 便利方法 | 修改 KernelGuard 整合邏輯 |
| 修改日誌格式 | 修改原子寫入機制 |

#### 必須同時檢查：**G1（ANIMA 數值組）**

---

### pulse/anima_tracker.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 3 |
| **角色** | 八元素能量追蹤 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態 | ANIMA_MC.json — `eight_primal_energies` 區段 |
| 下游 | brain.py, soul_ring.py (DiaryStore), periodic_cycles.py |
| 鎖風險 | ✅ 已修復：經由 AnimaMCStore 統一鎖保護（合約 1） |

#### 必須同時檢查：**G1（ANIMA 數值組）**

---

### nightly/nightly_pipeline.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 2 |
| **角色** | 夜間整合管線（49 步驟，含 Step 30 藍圖一致性驗證 + Step 31 context_cache 重建 + Step 32 crystal_decay + Step 33 crystal_promotion） |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態讀寫 | question_queue(RW), scout_queue(R), nightly_report(W), PulseDB(RW), crystal.db(RW via CrystalStore+直接SQL), accuracy_stats(R), heuristics.json(W via IntuitionEngine, Step 33) |
| 事件發布 | 6 個：NIGHTLY_COMPLETED, IMMUNE_MEMORY_LEARNED, MORPHENIX_PROPOSAL_CREATED, SOUL_IDENTITY_TAMPERED, SYNAPSE_PRELOAD, TRIGGER_FIRED, TOOL_MUSCLE_DORMANT |
| 子步驟呼叫 | curiosity_router, exploration_bridge, skill_forge_scout, crystal_actuator, parameter_tuner, morphenix_validator, morphenix_executor, evolution_velocity, periodic_cycles, blueprint_reader, workflow_engine(lazy), cache/context_cache_builder(Step 31), CrystalStore(Step 32), IntuitionEngine(Step 33) |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 修改步驟的日誌輸出 | 修改步驟執行順序 |
| 新增獨立步驟（不影響既有） | 修改 question_queue 的讀寫邏輯 |
| 修改報告格式 | 修改 `_step_curiosity_scan()` 的問句過濾 |

---

### vector/vector_bridge.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 9 |
| **角色** | Qdrant 向量庫的統一存取層 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態 | Qdrant 8 個 dense collections + N 個 sparse collections（`{name}_sparse`）；memories collection 新增 status=deprecated 軟刪除過濾 |
| 直接 import | 9 個模組（brain, brain_observation, memory_manager, reflex_router, skill_router, knowledge_lattice, primal_detector, server.py, nightly_pipeline.py）（fan_in 從 7→9，基於 topology_report） |
| 新增方法 | `mark_deprecated()` — 軟刪除；`hybrid_search()` — Dense+Sparse RRF 融合（已被 4 模組主動消費：skill_router、memory_manager、knowledge_lattice、server）；`index_sparse()` / `backfill_sparse()` / `build_sparse_idf()` — 稀疏向量管理；`index_all_skills()` — skills collection 全量索引（Gateway startup + Nightly 8.6 + API reindex）；`reindex_all()` — 全部 collection 重索引 |
| 降級影響 | Qdrant 離線 → 檢索降級為 TF-IDF（0.3 折扣）；Sparse 不可用 → hybrid_search 降級為純 dense；hybrid_search 已全面啟用（skill_router、memory_manager、knowledge_lattice、server 四模組均已從 search() 切換為 hybrid_search()） |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增 collection（含 sparse） | 修改 embedding 維度或模型 |
| 新增查詢參數（如 `filter_deprecated`） | 修改 graceful degradation 邏輯 |
| 新增 hybrid_search 參數 | 修改 collection schema |

---

### nightly/curiosity_router.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 2 |
| **共享狀態** | question_queue.json(RW) |
| **必須同時檢查** | **G2（探索結晶管線）** |

---

### nightly/exploration_bridge.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 2 |
| **共享狀態** | scout_queue/pending.json(W) |
| **事件訂閱** | EXPLORATION_CRYSTALLIZED, EXPLORATION_INSIGHT, NIGHTLY_COMPLETED, SCOUT_DRAFT_READY |
| **必須同時檢查** | **G2（探索結晶管線）** |

---

### governance/governor.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 3 |
| **角色** | 治理層中樞——事件訂閱與決策 |
| **事件訂閱** | AUDIT_COMPLETED, MORPHENIX_AUTO_APPROVED, SOUL_IDENTITY_TAMPERED |

---

### governance/refractory.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 2（server.py, governor.py） |
| **角色** | 跨重啟斷路器（不應期）——三態 + 半開試探 |
| **狀態機** | proceed → backoff → hibernate ⇌ half_open → proceed |
| **持久狀態** | `~/.museon/refractory_state.json`（failure_count, hibernating, half_open, env_mtime） |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 調整退避時間常數 | 修改狀態持久化檔案路徑 |
| 新增喚醒條件 | 移除 hibernate 門檻 |
| 修改日誌格式 | 修改 `_find_env_file()` 路徑解析邏輯 |

---

### core/module_registry.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 1（brain.py；v1.62 從黃區降為綠區） |
| **角色** | 模組三層信任等級管理（CORE / OPTIONAL / EDGE） |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 修改模組的信任等級分類 | 修改 `register()` / `get()` API |
| 新增信任等級 | 修改信任等級的行為邏輯 |

---

## PDR 模組（Progressive Depth Response）

> v1.70 新增。PDR 漸進深度回應系統，含調控參數、九策軍師、統一能力目錄三個模組。

### agent/pdr_params.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 4（telegram_pump, brain, pdr_council, museqa） |
| **扇出** | 0 |
| **安全分級** | 🟡 黃區 |

> 修改 pdr_params 會影響 telegram_pump 的回應深度判斷、brain 的 prompt 建構、pdr_council 的策略選擇、museqa 的自動調控。

### agent/pdr_council.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 1（telegram_pump） |
| **扇出** | 2（pdr_params, LLM adapter） |
| **安全分級** | 🟢 綠區 |

### agent/agent_registry.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 1（pdr_council） |
| **扇出** | 0 |
| **安全分級** | 🟢 綠區 |

> **注意**：telegram_pump 的扇出因 PDR 增加了 pdr_council + pdr_params 兩個依賴。brain 的扇出增加了 pdr_params。museqa 的扇出增加了 pdr_params。

---

## 🟢 綠區安全模組（45 個葉子模組）

> 以下模組無人 import（扇入 = 0），修改不影響任何上游，可直接修改。

### Agent 層（22 個）
`agent/crystal_store.py`（★ v1.41 新增，扇入=2（knowledge_lattice + crystal_actuator），CrystalStore 統一存取層——crystal.db SQLite WAL 模式，`threading.Lock` + singleton factory `get_crystal_store()`），
`agent/recommender.py`（★ v1.43 新增，扇入=1（brain.py），知識推薦引擎——CrystalStore 經由 brain 注入，互動歷史 `data/_system/recommendations/interactions.json` 原子寫入），
`agent/brain_prompt_builder.py`（★ v1.48 Mixin，扇入=1（brain.py），system prompt 建構，1668 行），
`agent/brain_dispatch.py`（★ v1.48 Mixin，扇入=1（brain.py），任務分派，1082 行），
`agent/brain_observation.py`（★ v1.48 Mixin，扇入=1（brain.py），觀察與演化，2003 行），
`agent/brain_p3_fusion.py`（★ v1.48 Mixin，扇入=1（brain.py），P3 融合與決策層，948 行），
`agent/brain_tools.py`（★ v1.48 Mixin，扇入=1（brain.py），LLM 呼叫與 session 管理，966 行），
`agent/brain_fast.py`（★ v1.70 重寫，扇入=1（server.py/telegram_pump.py），L1 接待層——Sonnet + escalation JSON + L4 回饋迴路，扇出含 brain_deep.py（L2 委派）+ brain_observer.py（L4 觀察）），
`agent/brain_deep.py`（★ v1.70 新增，扇入=1（brain_fast.py），L2 深度思考引擎——Opus + tool_use，扇出 3：brain_tool_loop.py, tool_schemas.py, context_cache 檔案），
`agent/brain_tool_loop.py`（★ v1.70 新增，扇入=1（brain_deep.py），獨立 tool-use 迴圈——從 brain_tools.py 提取，扇出 2：llm/adapters.py, agent/tools.py ToolExecutor），
`agent/brain_observer.py`（★ v1.70 新增，扇入=1（brain_fast.py），L4 觀察者——記憶落地 + 洞察偵測，扇出 1：context_cache/pending_insights.json），
`agent/chat_context.py`（★ v1.47 新增，扇入=1（brain.py），ChatContext dataclass 取代 per-turn 變數），
`agent/deterministic_router.py`（★ v1.47 新增，扇入=1（brain_dispatch.py），確定性任務分解器取代 LLM Orchestrator），
`agent/tool_schemas.py`（★ v1.70 擴充，扇入=1（brain_deep.py），工具定義目錄——v1.70 新增 trigger_job/memory_search/spawn_perspectives 3 個工具），
`agent/drift_detector.py`, `agent/intuition.py`, `agent/kernel_guard.py`, `agent/plan_engine.py`, `agent/primal_detector.py`, `agent/safety_anchor.py`, `agent/sub_agent.py`
（注：`agent/dna27.py`、`agent/routing_bridge.py`、`agent/pending_sayings.py` 已於 v1.77 刪除）

### Memory 層（1 個）
`memory/memory_gate.py`（★ v1.19 新增，扇入=1，僅 brain.py import；純 CPU 規則引擎，零 LLM 成本，判斷記憶寫入意圖）

### LLM 層（0 個）
（注：`llm/vision.py`、`llm/client.py` 已於 v1.77 刪除）

### Pulse 層（1 個）
`pulse/push_budget.py`（★ v1.54 新增，扇入=1（server.py），PushBudget 全局推送預算管理器）

### Governance 層（2 個）
`governance/response_guard.py`（★ v1.60 新增，扇入=3（telegram_pump.py + channels/telegram.py + channels/telegram_menu.py），ResponseGuard 發送前 chat_id 二次驗證閘門；三方法統一 _normalize_id(abs()) 正規化：validate() 靜態驗證 + allow_send() 實例驗證 + validate_escalation() escalation 專用；sanitize_for_group() 內容黑名單清理——v1.65 收窄【】pattern 避免誤殺合法中文；v1.68 新增 [empty] 佔位符 + Skill 路由鏈（emoji→arrow）過濾；**v1.82 取消群組/私訊分流，所有通道統一過濾全部 18 組 _INTERNAL_PATTERNS**；telegram_pump.py 9 處直送改走 _safe_send()、cron_registry.py Ares alert 改走 _safe_send()、telegram_menu.py 加 sanitize、update_processing_status 加 sanitize）
（注：`governance/cognitive_receipt.py` 已於 v1.77 刪除）

### Doctor 層（2 個）
`doctor/memory_reset.py`（★ v1.20 新增，扇入=0，CLI 工具；一鍵重置 25 個持久層，涵蓋 ANIMA_MC/USER、PULSE.md、PulseDB、Qdrant、sessions、memory_v3 等全部記憶/知識/行為/評估/日誌層）
`MUSEON_observatory.html`（★ v1.21 新增，扇入=0，純前端儀表板；讀取 cognitive_trace.jsonl 視覺化認知追蹤）

### Vector 層（1 個）
`vector/sparse_embedder.py`（★ v1.30 新增，扇入=1，僅 vector_bridge.py import；BM25 稀疏向量產生器，jieba 中文分詞 + IDF 持久化；v1.35 起已全面啟用——hybrid_search 被 4 模組主動消費，Nightly Step 8.7 定期重建 IDF，Gateway startup 驗證 IDF 可用性）

### Gateway 層（7 個）
`gateway/cron.py`, `gateway/security.py`, `gateway/session.py`, `gateway/authorization.py`
（★ v1.35 新增 `authorization.py`，扇入=2（security.py + telegram.py），授權引擎：ApprovalQueue + ToolAuthorizationQueue + PairingManager + AuthorizationPolicy）

`gateway/routes_api.py`（★ v1.64 從 server.py 拆出，扇入=1（server.py），689 行；SkillHub + External Integration API 端點註冊，含 `/api/market/*`、`/api/image/*`、`/api/voice/*` 等 Phase 3-5 端點），
`gateway/cron_registry.py`（★ v1.64 從 server.py 拆出，扇入=1（server.py），1424 行；系統 cron 任務註冊，含五虎將 + Nightly + 41 項排程），
`gateway/telegram_pump.py`（★ v1.64 從 server.py 拆出，扇入=1（server.py），754 行；Telegram 訊息泵核心邏輯——收訊→Brain 處理→ResponseGuard.validate() 驗證→發送；v1.65 移除手寫 chat_id 比對改用 ResponseGuard.validate()；**v1.82 消除全部 9 處 bot.send_message() 直送，統一改走 adapter._safe_send() 確保 ResponseGuard 覆蓋所有出口**（Phase 0/1/2/3 + SLA interim + Escalation）；lazy import 8 個模組：response_guard, rate_limiter, group_context, multi_tenant, authorization, interaction, session, message）

### LLM 層
`llm/` 下大部分模組

### OneMuse 能量解讀技能群（3 個）
`skills/energy-reading`（★ v1.79 新增，扇入=0，扇出=4（dharma, resonance, knowledge-lattice, user-model），八方位能量解讀——唯讀參考 `data/knowledge/onemuse/`，結晶化至 knowledge-lattice energy_crystal），
`skills/wan-miu-16`（★ v1.79 新增，扇入=1（combined-reading），扇出=3（energy-reading, knowledge-lattice, user-model），萬謬16型人格——依賴 energy-reading 能量數據，結晶化至 knowledge-lattice persona_crystal），
`skills/combined-reading`（★ v1.79 新增，扇入=0，扇出=4（energy-reading, wan-miu-16, knowledge-lattice, user-model），合盤能量比對——同時讀取 energy-reading 與 wan-miu-16 數據，結晶化至 knowledge-lattice relationship_crystal）

### 戰神系統 Ares（2 個）
`skills/anima-individual`（★ v1.80 新增，扇入=1（ares），扇出=8（wan-miu-16, energy-reading, combined-reading, shadow, master-strategy, xmodel, knowledge-lattice, user-model），ANIMA 個體追蹤引擎——為第三方人物建立七層鏡像+八大槓桿持久化畫像，儲存 `data/ares/profiles/{profile_id}.json`，結晶化至 knowledge-lattice individual_crystal），
`skills/ares`（★ v1.80 新增，扇入=0，扇出=14（anima-individual, wan-miu-16, energy-reading, combined-reading, master-strategy, shadow, xmodel, pdeif, roundtable, business-12, ssa-consultant, knowledge-lattice, user-model, c15），戰神系統工作流——編排 ANIMA 個體引擎+多 Skill 產出人物分析/策略建議/多層槓桿路徑/連動模擬/戰前簡報，Python 模組 `src/museon/ares/`（profile_store/graph_renderer/external_bridge），結晶化至 knowledge-lattice strategy_crystal）

### 新 Skill 批次（13 個，v1.84 新增）

#### 🟡 黃區（扇入 2-9）

`skills/ad-pilot`（★ v1.84 新增，扇入=3（business-12, ssa-consultant, finance-pilot），扇出=5，廣告投放策略分析——從商業診斷到廣告創意到媒體採買到轉化優化，結晶化至 knowledge-lattice Insight），
`skills/equity-architect`（★ v1.84 新增，扇入=3（business-12, master-strategy, shadow），扇出=5，合夥結構設計——股權分配/合夥協議設計/三種模式 A/B/C 選擇，結晶化至 knowledge-lattice decision_crystal），
`skills/course-forge`（★ v1.84 新增，扇入=4（storytelling-engine, consultant-communication, script-optimizer, pdeif），扇出=5，課程架構設計引擎——學習地圖/單元架構/教學法選擇/作業設計，結晶化至 knowledge-lattice Pattern），
`skills/brand-project-engine`（★ v1.84 新增，扇入=2（brand-builder, brand-identity），扇出=2，品牌專案管理引擎——品牌建構專案管理/里程碑追蹤/工作流程同步），
`skills/finance-pilot`（★ v1.84 新增，扇入=2（daily-pilot, business-12），扇出=4，財務管理副駕駛——記帳/月結/現金流預測/成本結構優化，結晶化至 knowledge-lattice Insight/Pattern），
`skills/prompt-stresstest`（★ v1.84 新增，扇入=2（acsf, fix-verify），扇出=5，提示詞壓力測試——多維度 LLM 提示詞品質驗證，結晶化至 knowledge-lattice Pattern），

#### 🟢 綠區（扇入 0-1）

`skills/biz-collab`（★ v1.84 新增，扇入=0，扇出=4（xmodel, business-12, biz-diagnostic, ssa-consultant），商業合作戰略——合作機會評估/合作模式設計/談判策略，結晶化至 knowledge-lattice collab_patterns），
`skills/biz-diagnostic`（★ v1.84 新增，扇入=0，扇出=3（business-12, darwin, report-forge），商業模式健檢——四層診斷/DARWIN 模擬/優先問題排序，結晶化至 knowledge-lattice diagnostic_crystal），
`skills/video-strategy`（★ v1.84 新增，扇入=0，扇出=4（storytelling-engine, brand-identity, script-optimizer, report-forge），影片策略規劃——內容策略/短影音工作流/跨平台分發計畫），
`skills/shadow-muse`（★ v1.84 新增，扇入=0，扇出=4（shadow, resonance, deep-think, user-model），潛意識創意激發引擎——創意蹲點/夢境日誌/原型探索/異化訓練），
`skills/daily-pilot`（★ v1.84 新增，扇入=0，扇出=4（plan-engine, deep-think, wee, user-model），每日決策副駕駛——日常優先序/精力管理/微決策系統），
`skills/talent-match`（★ v1.84 新增，扇入=0，扇出=4（onemuse-core, business-12, shadow, user-model），人才評估與招募策略——崗位設計/評估框架/面試設計/招募策略，結晶化至 knowledge-lattice Insight），
`skills/workflow-brand-consulting`（★ v1.84 新增，扇入=0，扇出=6（brand-discovery, brand-builder, brand-identity, storytelling-engine, aesthetic-sense, report-forge），品牌諮詢完整工作流——從品牌探索到品牌手冊 HTML 全流程編排，結晶化至 knowledge-lattice brand_crystal），

### 三層調度員架構（3 個）

#### dispatcher（L1 調度員）

| 屬性 | 值 |
|------|-----|
| **扇入** | 0（channels session 入口） |
| **扇出** | 1（spawn thinker） |
| **角色** | 收到訊息後 1 秒內 spawn L2 思考者，不做任何思考或回覆——郵局分揀員 |
| **安全分級** | 🟢 綠區 |

#### thinker（L2 思考者）

| 屬性 | 值 |
|------|-----|
| **扇入** | 1（dispatcher spawn） |
| **扇出** | 2（讀 `data/_system/museon-persona.md`、spawn worker） |
| **角色** | 讀取人格檔 → 分析訊息 → 撰寫回覆 → spawn L3 工人執行 MCP 工具 |
| **安全分級** | 🟢 綠區 |

#### worker（L3 工人）

| 屬性 | 值 |
|------|-----|
| **扇入** | 1（thinker spawn） |
| **扇出** | 3+（MCP 工具：telegram/gmail/gcal） |
| **角色** | 執行單一 MCP 工具呼叫後銷毀——純工具執行層 |
| **安全分級** | 🟢 綠區 |

### museon-persona.md 影響分析

| 屬性 | 值 |
|------|-----|
| **路徑** | `data/_system/museon-persona.md` |
| **讀取者** | 所有 L2 thinker subagent |
| **寫入者** | 人工維護（手動編輯） |
| **修改影響** | 改了人格檔 = 改了所有 L2 的行為——等同全域行為變更，影響所有對話回覆的語氣、判斷準則、行為模式 |

> ⚠️ `museon-persona.md` 雖然不是 Python 模組，但實質上是所有 L2 thinker 的「系統提示源」。修改此檔案等同於修改紅區模組，建議視為 🟠 紅區對待。

### 體液系統（5 個，v1.86 新增）

`core/awareness.py`（★ v1.86 新增，扇入=0，AwarenessSignal 統一覺察訊號格式——dataclass 含 Severity/SignalType/Actionability enum，to_dict()/from_dict() 序列化，純資料結構無副作用），
`core/session_adjustment.py`（★ v1.86 新增，扇入=2（brain_prompt_builder + triage_step），SessionAdjustment 即時行為調整管理器——get_manager() singleton，add/get_active/format_for_prompt/clear 四個方法，寫入 `_system/session_adjustments/{id}.json`，expires_after_turns 自動過期），
`nightly/triage_step.py`（★ v1.86 新增，扇入=0（Nightly Step 5.8 前置呼叫），Nightly 分診步驟——write_signal()/drain_queue()/accumulate_signals()/escalate_high()/emit_adjustments() 五個函數，寫入 triage_queue.jsonl + awareness_log.jsonl + nightly_priority_queue.json），
`nightly/triage_to_morphenix.py`（★ v1.86 新增，扇入=1（nightly_pipeline Step 5.8），HIGH→Morphenix 迭代筆記橋接——drain_priority_queue()/write_morphenix_proposal() 兩個函數，消費 nightly_priority_queue.json 寫入 morphenix/proposals/），
`governance/algedonic_alert.py`（★ v1.86 新增，扇入=1（governor.py 初始化），治理警報 Telegram 推播——AlgedonicAlert class，訂閱 GOVERNANCE_ALGEDONIC_SIGNAL 事件，防洪閘（rate limit）+ 嚴重度過濾，發布 PROACTIVE_MESSAGE 到 event_bus）

### Persona Evolution 系統（6 個，v1.90 新增）

#### 🟡 黃區（扇入 2-9）

`evolution/trait_engine.py`（★ v1.90 新增，扇入=2（brain_observation._observe_self + nightly_reflection），扇出=1（anima_mc_store via kernel_guard），人格特質引擎——計算並寫入 ANIMA_MC.personality.trait_dimensions；kernel_guard 作為唯一寫入閘門，防止並發衝突），
`evolution/nightly_reflection.py`（★ v1.90 新增，扇入=1（nightly_pipeline Step 34），扇出=4（anima_mc_store + kernel_guard + soul_ring + momentum_brake），夜間人格反思管線——整合單日互動資料、計算特質趨勢、觸發 soul_ring 寫入與 momentum_brake 煞車評估；讀寫共享狀態：ANIMA_MC.personality.trait_dimensions + soul_rings.json），
`evolution/mask_engine.py`（★ v1.90 新增，扇入=2（brain.py Step 2.2 + Step 9.9），扇出=1（寫 _system/mask_states.json），人格面具引擎——根據對話情境動態切換/合成人格面具；共享狀態 _system/mask_states.json（#70）單一寫入者）

#### 🟢 綠區（扇入 0-1）

`evolution/growth_stage.py`（★ v1.90 新增，扇入=2（brain_observation._update_growth_stage + nightly_pipeline Step 34.5），扇出=0，純計算，成長階段評估器——讀取 ANIMA_MC.evolution.stage_history 計算當前階段，不寫入任何持久層），
`evolution/dissent_engine.py`（★ v1.90 新增，扇入=1（brain.py Step 3.655），扇出=1（讀 crystal_rules.json），無狀態，反異見引擎——在 Brain 回覆生成前注入反向視角；讀取 crystal_rules.json 取得反異見規則，無寫入副作用），
`evolution/momentum_brake.py`（★ v1.90 新增，扇入=2（nightly_reflection + drift_detector），扇出=0，純計算，人格動量煞車器——評估特質演化速度，防止劇烈人格漂移；讀取 ANIMA_MC.evolution.trait_history，返回計算結果不寫入）

### 其他
各子系統的終端執行模組（無人 import 的工具、通道適配器等）

> **注意**：「無人 import」不代表「不重要」——許多是入口點（cron, server）或由 __init__.py re-export。
> 修改前仍需檢查 joint-map 確認是否觸及共享狀態。

---

## 事件影響半徑

### 高影響事件（訂閱者 ≥ 2）

| 事件 | 發布者 | 訂閱者 | 修改影響 |
|------|--------|--------|---------|
| `EXPLORATION_CRYSTALLIZED` | pulse_engine | server, exploration_bridge | 探索結果雙向傳播 |
| `EXPLORATION_INSIGHT` | pulse_engine | server, exploration_bridge | 探索洞見雙向傳播 |
| `NIGHTLY_COMPLETED` | nightly_pipeline | server, exploration_bridge | 凌晨管線完成同步點 |
| `MORPHENIX_EXECUTION_COMPLETED` | morphenix_executor | skill_router, telegram | 演化執行完成廣播 |
| `SKILL_QUALITY_SCORED` | eval_engine, wee_engine | dendritic_scorer, outward_trigger | 技能評分（多源雙消） |

### 孤兒事件（只發不收）：38 個

> 這些事件被發布但無人訂閱——修改/刪除它們是安全的。

**關鍵孤兒**（可能是設計遺漏）：
- `DNA27_WEIGHTS_UPDATED` — 演化權重變化無人監聽
- `CRYSTAL_CREATED` — 知識結晶無人應用
- `SOUL_RING_DEPOSITED` — 日記條目存入無人確認
- `MEMORY_PROMOTED` / `MEMORY_RECALLED` — 記憶事件無人監聽
- `AUTONOMIC_REPAIR` — 自主修復無人知曉

### 幽靈訂閱（只收不發）：0 個（v1.5 全部修復）

| 事件 | 原訂閱者 | 修復方式 |
|------|----------|---------|
| `PULSE_RHYTHM_CHECK` | telegram | ✅ 已移除訂閱 + 死處理器 `_on_rhythm_check()` |
| `PULSE_NIGHTLY_DONE` | telegram | ✅ 已移除訂閱 + 死處理器 `_on_nightly_done()` |
| `EVOLUTION_HEARTBEAT` | server (ActivityLogger) | ✅ 已從 `_log_events` 移除 |
| `MORPHENIX_EXECUTED` | server (ActivityLogger) | ✅ 已修正為正確常量名 `MORPHENIX_EXECUTION_COMPLETED` |

---

## 必須同時修改的模組組（交叉引用 joint-map）

| 組 ID | 觸發條件 | 必須一起改的模組 | 共享的狀態 |
|-------|---------|----------------|-----------|
| **G1** | 改 ANIMA 數值邏輯 | anima_tracker + brain + server + micro_pulse + kernel_guard | ANIMA_MC.json |
| **G2** | 改探索/好奇心邏輯 | pulse_engine + curiosity_router + exploration_bridge + nightly_pipeline + skill_forge_scout | question_queue.json + scout_queue/pending.json + PULSE.md |
| **G3** | 改記憶存取 | memory_manager + brain + vector_bridge + reflex_router | MemoryStore + Qdrant |
| **G4** | 改演化速度計算 | evolution_velocity + parameter_tuner + periodic_cycles + metacognition | accuracy_stats.json + tuned_parameters.json |
| **G5** | 改知識晶格 | knowledge_lattice + crystal_store + crystal_actuator + recommender + brain（Layer 2.5 社群摘要 + 經驗回放） | crystal.db (via CrystalStore)；knowledge_lattice.py 新增 `recall_procedures()` RO 方法 + 再結晶 Lesson↔Procedure 升降級規則 |
| **G6** | 改免疫系統 | immunity + immune_memory + immune_research + daemon | events.jsonl + immune_memory.json |
| **G7** | 改品質回饋閉環（DNA-Inspired） | metacognition + morphenix_executor + pulse_db | PulseDB.metacognition 表（`METACOGNITION_QUALITY_FLAG` 事件） |
| **G8** | 改衰減參數或老化邏輯 | knowledge_lattice + crystal_store + crystal_actuator + recommender + memory_manager + dendritic_scorer + adaptive_decay | crystal.db(RI via CrystalStore) + Qdrant memories(TTL) + PulseDB health_scores(半衰期) + 推薦排序(近因性) |
| **G9** | 改記憶反思 | memory_reflector + adaptive_decay + brain_prompt_builder | Qdrant memories + soul_rings + crystals（RO）；反思摘要注入 system_prompt memory zone（注：epigenetic_router 已刪除） |

> **G8 衰減組說明**：四個衰減引擎（結晶 RI、記憶 TTL、健康分數半衰期、推薦近因性）各自獨立但交叉影響——修改結晶 RI 衰減速度會間接影響 recommender 的推薦排序；修改 dendritic_scorer 半衰期會影響 governor 治理決策進而影響 brain Step 5.5 融合品質。修改任一衰減參數前，必須查閱 `persistence-contract.md` §衰減與優先級模型的完整公式表。

---

## 修改決策流程圖

```
要修改模組 X
    │
    ├─ 查扇入（本表）→ 扇入 = 0？
    │       ├─ 是 → 🟢 查 joint-map 確認無共享狀態 → 直接修改
    │       └─ 否 → 繼續 ↓
    │
    ├─ 扇入 ≥ 10？
    │       ├─ 是 → 🟠 必須回報使用者 + 完整影響分析
    │       └─ 否 → 🟡 查 joint-map + 跑相關測試
    │
    ├─ 查模組組（G1-G6）→ 屬於任一組？
    │       ├─ 是 → 必須同時檢查同組所有模組
    │       └─ 否 → 正常流程
    │
    ├─ 查事件影響 → 修改的事件有多個訂閱者？
    │       ├─ 是 → 通知所有訂閱模組的維護者
    │       └─ 否 → 正常流程
    │
    └─ 動手修改 → 跑 pytest → 更新本表（如果改了 import）→ 更新 joint-map（如果改了共享狀態）
```

---

## 系統健康度快照（2026-03-28 v1.77 死碼清理後更新）

| 指標 | 數值 | 說明 |
|------|------|------|
| 總模組數 | 220 | 死碼清理後（刪除 20 個模組）；topology_report: 240 含 __init__ |
| 禁區模組（扇入 ≥ 40） | 1 | event_bus(46) |
| Hub 模組（扇入 10-39） | 3 | message(14), data_bus(15), pulse_db(11)；brain(2,扇出 42+,系統核心) |
| 中間模組（扇入 2-9） | 60+ | vector_bridge(9), knowledge_lattice(7), channels.base(6), crystal_store(5), doctor.shared_board(5) 等 |
| 單引用模組（扇入 1） | 90+ | 含 brain_*.py Mixin 系列 |
| 葉子模組（扇入 0） | 80+ | 可安全修改 |
| 共享可變狀態 | 53 | 詳見 joint-map.md v1.49 |
| 事件健康度 | 67.9% | 幽靈訂閱清零（v1.5 修復） |
| 致命單點 | event_bus | 佔全系統 21% 直接依賴（46/220） |
| 破損 import | 2 | brain_fast.py → input_sanitizer, ceremony（待修復） |

---

## 變更日誌

| 日期 | 版本 | 變更 |
|------|------|------|
| 2026-03-31 | v1.90 | Persona Evolution 系統——新增 trait_engine.py（🟡 扇入=2）、nightly_reflection.py（🟡 扇入=1，扇出=4）、mask_engine.py（🟡 扇入=2）、growth_stage.py（🟢 扇入=2，純計算）、dissent_engine.py（🟢 扇入=1，無狀態）、momentum_brake.py（🟢 扇入=2，純計算）；新增共享狀態 #70 _system/mask_states.json；黃區 62→65、綠區 171→174 |
| 2026-03-31 | v1.86 | 體液系統——新增 awareness.py（🟢 扇入=0）、session_adjustment.py（🟢 扇入=2）、triage_step.py（🟢 扇入=0）、triage_to_morphenix.py（🟢 扇入=1）、algedonic_alert.py（🟢 扇入=1）；brain_prompt_builder 四路接線（扇出+3）；nightly_pipeline Step 5.8 前置（扇出+1）；response_guard 新增 strip_markdown()；governor 初始化 algedonic_alert（扇出+1）；telegram_pump 新增 CHANNEL_MESSAGE_RECEIVED publish（扇出+1） |
| 2026-03-26 | v1.70 | v2 Brain 四層架構 + 死碼清理——新增 `brain_deep.py`（L2 Opus 引擎，綠區扇入=1）、`brain_tool_loop.py`（獨立 tool-use 迴圈，綠區扇入=1）、`brain_observer.py`（L4 觀察者，綠區扇入=1）、`brain_fast.py` 重寫為 L1 Sonnet + escalation JSON + L4 回饋迴路、`tool_schemas.py` 新增 3 工具（trigger_job/memory_search/spawn_perspectives）、`nightly_pipeline.py` Step 31 context_cache 重建。死碼移除：federation/（skill_market + sync）、installer/（整個目錄）、nightly_v2.py |
| 2026-03-25 | v1.68 | L2 Worker 分離 + AIORateLimiter——新增 brain_worker.py（subprocess + Pipe IPC）、AsyncTokenBucket（token bucket 取代 semaphore）；telegram_pump worker 優先路徑 + fallback；server.py worker lifecycle。response_guard 新增 [empty]+路由鏈過濾 |
| 2026-03-25 | v1.67 | 訊息佇列持久化 + 全鏈路 trace_id——新增 message_queue_store.py（SQLite crash recovery）；InternalMessage trace_id 欄位；telegram_pump 持久化+恢復+log trace_id；brain.py process() trace_id |
| 2026-03-25 | v1.66 | Brain 90s SLA + Circuit Breaker——telegram_pump _brain_process_with_sla()；bulkhead.py BrainCircuitBreaker 三態機；server.py CB 通知+/health 端點。bulkhead 扇入 1→2 |
| 2026-03-25 | v1.65 | 對話持久化+教訓蒸餾+7 條斷裂管線修復——87 檔案 +4623/-2934 行。五虎將升級+Fix-Verify 工作流鍛造 |
| 2026-03-25 | v1.64 | server.py 拆分（5749→3800 行）——拆出 telegram_pump/routes_api/cron_registry 三模組。三層洩漏預防（L1 prompt→L2 剝離→L3 guard） |
| 2026-03-30 | v1.84 | 13 個新 Skill Post-Build 補登——🟡黃區新增：ad-pilot（扇入=3）、equity-architect（扇入=3）、course-forge（扇入=4）、brand-project-engine（扇入=2）、finance-pilot（扇入=2）、prompt-stresstest（扇入=2）；🟢綠區新增：biz-collab、biz-diagnostic、video-strategy、shadow-muse、daily-pilot、talent-match、workflow-brand-consulting（扇入均=0）。同步 topology v1.66、joint-map v1.54、memory-router v1.16 |
| 2026-03-30 | v1.83 | 市場戰神（Market Ares）——market_ares 模組群（9 子包 16 檔，扇入=0），新增 market_ares.db SQLite WAL。同步 topology v1.64、joint-map v1.53、memory-router v1.14、persistence-contract v1.41 |
| 2026-03-29 | v1.80 | 戰神系統（Ares）——新增 2 個 Skill 到綠區：anima-individual（扇入=1, 扇出=8, individual_crystal）、ares（扇入=0, 扇出=14, strategy_crystal）；新增 Python 模組 src/museon/ares/ + 儲存路徑 data/ares/profiles/。同步 topology v1.62、joint-map v1.52、memory-router v1.13、persistence-contract v1.40 |
| 2026-03-29 | v1.79 | OneMuse 能量解讀技能群——新增 3 個 Skill 到綠區（energy-reading 扇出=4、wan-miu-16 扇出=3、combined-reading 扇出=4），唯讀參考 data/knowledge/onemuse/（36 檔）。同步 topology v1.61、joint-map v1.51、memory-router v1.12、persistence-contract v1.39 |
| 2026-03-24 | v1.62 | 全面審計修正——扇入重算（event_bus 117→45）、8 個新模組補列 |
| 2026-03-24 | v1.61 | 操作記憶層架構——第六張藍圖 operational-contract.md + scripts/workflows/ 可執行腳本 |
| 2026-03-24 | v1.60 | 跨群組洩漏防禦 + 軍師認知升級——新增 `governance/response_guard.py` 到綠區（扇入=2，ResponseGuard chat_id 二次驗證閘門）；`governance/multi_tenant.py` 新增 `resolve_by_id()` 精確匹配取代 FIFO；brain.py `process()` finally 清空 `self._ctx` + 6 個 alias + 新增 `_check_smart_completeness()` + `route()` 新增 `is_group` 傳遞；server.py session lock 升級 `wait_and_acquire(30s)` timeout 守衛。軍師認知升級：`reflex_router.py` select_loop/route 新增 `is_group`；`brain_prompt_builder.py` 軍師認知框架 + 群組禁止確認詞；`brain_p3_fusion.py` ≥3 Skill Roundtable 自動融合。**注意**：認知升級修改在 `.runtime/src/museon/agent/`（gitignored）。同步 system-topology v1.47 |
| 2026-03-23 | v1.59 | Brain 思考品質 5 項修復（DSE 分析結果落地）——(1) reflex_router.py `select_loop()` 移除 RC-D1 從 EXPLORATION_LOOP 攔截（D1 屬 D-tier 應走 SLOW_LOOP）；(2) brain.py `_check_behavior_patterns()` action_verbs 擴充 8 個高頻動詞（分析/規劃/評估/整理/計算/比較/歸納/總結）+ 移除 `len(content)<30` 短訊息誤判；(3) rc_affinity_loader.py `get_suppressed_skills()` 新增 cluster_scores + threshold 0.5 參數（低分 RC 不再壓制策略 Skill）；reflex_router.py RoutingSignal 新增 `cluster_scores` 欄位；skill_router.py 呼叫端同步傳入 cluster_scores；(4) brain_p3_fusion.py 新增 `_P3_CONFIDENCE_EXPLORE_MULTI=0.7`（EXPLORATION_LOOP + 多策略 Skill → 0.70 取代恆定 0.60）；(5) brain.py Step 3.1c P0 訊號分流提前——戰略信號自動注入 master-strategy 到 matched_skills。全部為內部邏輯修改，不改公開介面/持久層格式/import 關係。RoutingSignal 新增 optional 欄位（向後相容）。 |
| 2026-03-23 | v1.56 | Session 自動清理升級——brain_tools.py `_save_session_to_disk()` 新增 metadata 層，記錄 `last_active` ISO 時間戳；`_load_session_from_disk()` 相容舊格式（pure list）和新格式（metadata + messages），自動轉換舊檔案；session_cleanup.py `cleanup_dormant_sessions()` 新增 `_get_session_last_active()` 優先讀 metadata.last_active、fallback 到檔案 mtime；server.py cron engine 每小時執行清理（超過 3 天未互動的 session 自動刪除）。brain_tools.py 扇入扇出不變、無新增 import；session_cleanup.py 扇入不變（1）；server.py 扇出不變（cron job 已註冊）；共享狀態讀寫格式變更（向後相容）。同步 persistence-contract v1.33 |
| 2026-03-23 | v1.55 | Project Epigenesis 接線——brain.py `__init__()` 新增 EpigeneticRouter 初始化（注入 memory_manager/diary_store/knowledge_lattice/anima_changelog/pulse_db）；brain_prompt_builder.py `_build_memory_inject()` 新增反思摘要注入（EpigeneticRouter.activate() → reflection.summary → memory zone）。新增 G9 記憶反思組（epigenetic_router + memory_reflector + adaptive_decay + brain_prompt_builder）。brain.py 扇出 +1（epigenetic_router）；brain_prompt_builder.py 扇出 +1。memory_reflector 扇入 1（epigenetic_router）；adaptive_decay 扇入 1（memory_reflector）；epigenetic_router 扇入 1（brain.py）。同步 joint-map v1.40、memory-router v1.6、persistence-contract v1.32 |
| 2026-03-23 | v1.54 | Doctor 群組健康檢查——四處修復：(1) P0 `brain_dispatch.py` `_strip_system_leakage()` NameError 修復：`@staticmethod` 內引用 `self._LEAKAGE_FILTER_RATIO` → `BrainDispatchMixin._LEAKAGE_FILTER_RATIO`，修復 dispatch 合成階段必定 crash；(2) P1 `tool_registry.py` + `service_health.py` Docker PATH 修復：launchd PATH 不含 `/usr/local/bin` 導致 docker binary 找不到，新增 `shutil.which()` + fallback 路徑解析，消除每 5 分鐘的 38000+ 行 log 噪音；(3) P2 `message.py` 空 content 防禦：Telegram 空訊息從 ValueError crash 改為 fallback `[empty]`；(4) P3 `server.py` Gateway 重啟 port reuse：`uvicorn.run()` 改為 `uvicorn.Server(Config).run()` 啟用 SO_REUSEADDR。全部為內部修復，不改公開介面/共享狀態/import 關係。扇入扇出不變。 |
| 2026-03-23 | v1.53 | 三層並行架構實作——`_telegram_message_pump()` 從循序處理重構為並行派送：提取 `_handle_telegram_message()` 為獨立 async function，主迴圈 receive → `asyncio.create_task()` → 立刻接下一則。不同 session（群組/私訊）完全並行，同一 session 由 session_manager lock 保護。純內部重構，不改介面/import/共享狀態。 |
| 2026-03-23 | v1.52 | 三層調度員架構——新增 dispatcher/thinker/worker 扇入扇出分析（L1 調度員扇入 0/扇出 1、L2 思考者扇入 1/扇出 2、L3 工人扇入 1/扇出 3+）；新增 museon-persona.md 影響分析（所有 L2 thinker 讀取，修改等同全域行為變更）；全部為綠區。Brain P3 Fusion 健康檢查——brain_p3_fusion.py 常數化 25+ 魔術值 + logger 提升 + asyncio 修復 + 死碼清理 + 48 個單元測試。 |
| 2026-03-22 | v1.35 | Sparse Embedder 全面啟動：skill_router.py `_vec_search()` 從 `vb.search()` 切換為 `vb.hybrid_search()`；memory_manager.py `_vector_search()` 從 `vb.search()` 切換為 `vb.hybrid_search()`；knowledge_lattice.py 結晶搜尋從 `vb.search()` 切換為 `vb.hybrid_search()`；server.py `/api/vector/search` 從 `vb.search()` 切換為 `vb.hybrid_search()`；Nightly Pipeline 新增 Step 8.7 `_step_sparse_idf_rebuild()`（build_sparse_idf + backfill_sparse）；Gateway startup 新增 SparseEmbedder IDF 驗證；sparse_embedder.py 扇入不變（1，僅 vector_bridge import）；vector_bridge.py 扇入不變（7）；同步 joint-map v1.35、persistence-contract v1.30 |
| 2026-03-22 | v1.46 | P0-P3 升級——report-forge Skill 新增 knowledge-lattice 輸出依賴（report_crystal 結晶化，via knowledge-lattice API，不改 report-forge 扇入扇出）；token_optimizer.py buffer 預算 2800→1800 + strategic zone 1000 新增（brain.py `_build_strategic_context()` 純新增方法）；anima_mc_store.py 共享狀態新增 `_system/backups/anima_mc/`（寫入前快照）；pulse_engine.py 共享狀態新增 `_system/backups/pulse_md/`（寫入前快照）；plan_engine.py bug 修復 plan.changes→plan.change_list（純內部修正，扇入不變）；共享狀態 33→34 |
| 2026-03-22 | v1.45 | 經驗諮詢閘門——brain.py 共享狀態讀取新增 activity_log.jsonl(R)；knowledge_lattice.py 新增 recall_procedures() 方法（RO）+再結晶 Lesson↔Procedure 升降級規則；crystal_store.py schema 新增 4 欄位（向後相容 ALTER TABLE）；activity_logger.py 新增 search() 方法（純讀） |
| 2026-03-22 | v1.43 | Recommender 激活修復：`agent/recommender.py` 從綠區扇入 0→1（brain.py import）；資料來源從過時 JSON 掃描改為 CrystalStore API；brain.py 新增 `_recommender` 初始化 + init log；server.py API 改用常駐實例；新增共享狀態 `_system/recommendations/interactions.json`；G5 知識晶格組 recommender 接線正式啟用 |
| 2026-03-22 | v1.41 | Knowledge Lattice 持久層遷移：新增 `agent/crystal_store.py` 到綠區（扇入=2，CrystalStore SQLite WAL + threading.Lock 統一存取層）；G5 知識晶格組新增 crystal_store，共享狀態從 crystals.json 改為 crystal.db (via CrystalStore)；G8 衰減組同步更新；evolution_velocity、guardian/daemon、system_audit、nightly_pipeline、wee_engine 共享狀態引用從 crystals.json 改為 crystal.db；同步 persistence-contract v1.26、joint-map v1.29、system-topology v1.31 |
| 2026-03-22 | v1.40 | Business Hub 健康檢查：skill_router.py `_extract_metadata` 頂層 YAML 解析修復（防 workflow stages 巢狀 name 覆蓋）+ synapses.json 幽靈條目清理（3 筆 `"案例結晶"`）+ consultant-communication memory.writes 補齊結構 |
| 2026-03-22 | v1.39 | Thinking Hub 健康檢查：brain.py `_dispatch_orchestrate` Orchestrator prompt 移除硬編碼 `resonance` 範例 + Rule 4 強化約束（防 LLM 幻覺引用 roster 外 Skill）；shadow SKILL.md `layer: business` → `layer: thinking`；純 prompt 文字修改，扇入扇出不變 |
| 2026-03-21 | v1.38 | dispatch 路徑 q_score 修復：brain.py `q_score`/`thinking_path_summary`/`p3_fusion_result` 三個 P3 審查變數的初始化從 else 分支（正常 pipeline L1297）提前到 dispatch 分支之前（L1069），修復 dispatch 路徑的 `UnboundLocalError`；純位置移動，無新增變數/方法/共享狀態；brain.py 扇入扇出不變 |
| 2026-03-21 | v1.37 | 兩筆藍圖欠債補齊：(1) `skill_router.py` L130 always_on 判定從子字串搜尋（`"常駐" in content`，67% 虛假正報率）改為 YAML frontmatter `type == "always-on"` 精確判定（0% 虛假正報率）——純內部邏輯最佳化，扇入扇出不變、無新增 import/共享狀態；(2) `eval_engine.py` 新增 `get_blindspot_hint_for_query()`（22 Skill 盲點提示表）、`metacognition.py` 新增 `extract_thinking_summary()`（五維度思考摘要），兩個函數尚未接線（無呼叫者），扇入扇出不變 |
| 2026-03-21 | v1.36 | Evolution Hub 健康檢查修復：`evolution/outward_trigger.py` 新增 `_ensure_state_files()`（__init__ 時建立 outward/ 4 個預設 JSON，解決空目錄導致外向演化永不觸發）；tantra Manifest 移除孤立輸出 `→ gateway`（validate_connections 警告清零）；`morphenix/proposals/` 目錄補建；扇入不變（2）、無新增 import、無共享狀態格式變更 |
| 2026-03-21 | v1.35 | Telegram 授權系統升級：新增 `gateway/authorization.py` 到綠區（扇入=2，ApprovalQueue + ToolAuthorizationQueue + PairingManager + AuthorizationPolicy）；`gateway/security.py` check_tool_access() 新增三級策略路由（auto/ask/block + "pending" 狀態）；`channels/telegram.py` 新增 4 個 handler（pair/auth command + pairing/auth callback）+ get_trust_level() 整合動態配對；`gateway/server.py` 訊息泵新增工具授權回覆分支（~15 行）；`mcp_server.py` 新增 museon_auth_status 工具；`governance/multi_tenant.py` EscalationQueue docstring 更新（說明與 ApprovalQueue 的關係）；新增持久狀態 `~/.museon/auth/allowlist.json` + `policy.json`；同步 joint-map v1.28、persistence-contract v1.25、system-topology v1.30 |
| 2026-03-21 | v1.34 | 環境感知 + 工程護欄落地：brain.py 新增 `_build_environment_awareness()` v11.3 + `_build_self_modification_protocol()` v11.4 + `_current_source` + `_self_modification_detected`（modules/buffer zone 注入，純新增方法不改既有流程）；新增 Claude Code Hooks（`.claude/settings.json`：PreToolUse blast-radius 自動查核 + Stop 未 commit 提醒）；新增 `scripts/generate_iteration_report.py`（迭代報告 HTML → Gist）；新增 `scripts/hooks/pre_edit_blast_check.py` + `stop_checklist.py`；brain.py 扇出不變、扇入不變、無新增共享狀態、無新增 import |
| 2026-03-21 | v1.33 | Skill 鍛造膠合層修復：VectorBridge 新增 `index_all_skills()`/`reindex_all()`（skills collection 全量索引）；server.py startup 新增 skills 向量索引步驟；nightly Step 8.6 `skill_vector_reindex`；plugin-registry v2.3（+12 Skill 註冊）；49 個 Skill Manifest 補齊 memory/io 欄位；skills collection 寫入者從 skill_router.py 修正為 vector_bridge.py |
| 2026-03-21 | v1.32 | 群組對話 DSE 三階段修復：brain.py 新增 `_classify_p0_signal()`（P0 六類訊號分流啟發式）+ `_detect_fact_correction()`（群組事實糾正啟用）+ `_observe_external_user()` v3.0 升級（trust evolution 四階段 + PrimalDetector 八原語 + L6 溝通風格 + L1 事實萃取）+ `_P0_SIGNAL_KEYWORDS` 四類關鍵字表 + `_FACT_CORRECTION_PATTERNS` 28 條糾正模式；memory_manager.py store() 新增 chat_scope/group_id 參數 + recall() 新增 chat_scope_filter/exclude_scopes 過濾 + _keyword_fallback()/\_vector_index() 同步支援；server.py 群組事實糾正啟用（skip_fact_correction=False）+ 錯誤顯示啟用（show_error_details=True）；governance/multi_tenant.py ExternalAnimaManager v3.0 schema（profile/relationship/seven_layers + v2→v3 遷移）；同步 joint-map v1.26、memory-router v1.1、persistence-contract v1.23、system-topology v1.26 |
| 2026-03-21 | v1.31 | GraphRAG 社群偵測：knowledge_lattice.py 新增 `detect_communities()`（Label Propagation）+ `_summarize_community()`（Extract-based 摘要）+ `has_communities()`（快速檢查）+ `recall_with_community()`（語義社群召回）（全部為純新增方法，不改既有 API）；brain.py L3221-3233 新增 Layer 2.5 社群摘要注入（~12 行，`has_communities()` + `recall_with_community()`，降級 try/except 保護）；G5 影響範圍：brain 新增為社群摘要消費者；無新增持久層（社群偵測為即時計算）；同步 joint-map v1.25、persistence-contract v1.22（不變）、system-topology v1.23（不變） |
| 2026-03-21 | v1.30 | 混合檢索（Hybrid Retrieval）：vector_bridge.py 新增 `hybrid_search()` + `_sparse_search()` + `_rrf_merge()` + `index_sparse()` + `backfill_sparse()` + `build_sparse_idf()`（全部為新增方法，不修改既有 API）；新增 `vector/sparse_embedder.py` 到綠區（扇入=1，僅 vector_bridge import）；Qdrant 共享狀態：新增 N 個 sparse collections（分離式 Route A，不碰原 dense schema）+ `_system/sparse_idf.json`；vector_bridge 扇入不變（7）；同步 joint-map v1.24、persistence-contract v1.22 |
| 2026-03-21 | v1.29 | MemGPT 分層結晶召回：knowledge_lattice.py 新增 `recall_tiered()` 方法（Hot/Warm/Cold 三層策略）；brain.py L3208 結晶注入從 `recall_with_chains()` 切換為 `recall_tiered()`（1 行改動，降級路徑保留 auto_recall）；G5 影響範圍不變（`recall_with_chains` 仍為 `recall_tiered` 內部引擎）；同步 joint-map v1.23 |
| 2026-03-20 | v1.28 | 衰減生命週期補全：新增 G8 衰減組（knowledge_lattice + crystal_actuator + recommender + memory_manager + dendritic_scorer），標記衰減參數修改的跨模組影響；同步 persistence-contract v1.21、system-topology v1.22、joint-map v1.22 |
| 2026-03-20 | v1.27 | brain.py P3 前置交織融合：新增 _p3_gather_pre_fusion_insights()，Phase 4.5 從「追加多視角區塊」改為「輕量簽名」，_execute_p3_parallel_fusion 降級為向後相容 |
| 2026-03-20 | v1.26 | P3 策略層並行融合落地實作：brain.py 新增 P3FusionSignal 資料類別 + _detect_p3_strategy_layer_signal() + _execute_p3_parallel_fusion() + _p3_strategy_perspective() + _p3_human_perspective() + _p3_risk_perspective()（共 5 個新方法）；brain.py 扇入不變，新方法扇出：_call_llm_with_model × 3（已有連線）；無新增共享狀態；版本同步 system-topology v1.20、joint-map v1.20、persistence-contract v1.19 |
| 2026-03-20 | v1.25 | P0-P3 思維引擎升級（純 Skill .md 認知行為變更，無結構性改動）：deep-think v2.0（P0 思考路徑可見化 + P1 主動盲點提醒 + P2 重大決策先問後答）、query-clarity v2.0（P1 主動觸發「你可能沒想到」）、orchestrator v3.0（P3 並行融合模式）、dna27 v2.2（回應合約對齊）；無新增/修改模組扇入扇出、無新增共享狀態、無事件變更；版本同步 system-topology v1.19、persistence-contract v1.19、joint-map v1.20 |
| 2026-03-19 | v1.24 | P1-P3 PersonaRouter 全接線：brain.py Step 3.65 baihe_decide context 從空 `{}` 填入 routing_signal+matched_skills+commitment+session_len+is_late_night；新增 Step 3.66 根因偵測層（`_detect_root_cause_hint()` Haiku 分析重複模式）；brain.py 新增共享狀態 baihe_cache.json(W)（原子寫入，供 ProactiveBridge 讀取）；proactive_bridge.py 新增 `_read_baihe_cache()`（讀 baihe_cache.json）、`_call_brain()` 根據象限注入語氣指引、`_build_context_messages()` 注入象限上下文；共享狀態 29→30 |
| 2026-03-17 | v1.23 | 軍師架構 Phase 1：brain.py 共享狀態 lord_profile.json 從 W 升級為 RW（Step 3.65 百合引擎讀取+進諫冷卻寫回）；brain.py 新增 `_format_baihe_guidance()` 方法；Pipeline 註解新增 Step 3.65 |
| 2026-03-17 | v1.22 | 軍師架構 Phase 0：brain.py 共享狀態新增 lord_profile.json(W)（`_observe_lord()` 原子寫入）；修改安全邊界「安全」欄新增 `_observe_lord()`（獨立觀察方法）；共享狀態 28→29 |
| 2026-03-17 | v1.21 | 認知可觀測性：brain.py 角色新增 trace_decision+trace_cognitive（Step 8 認知追蹤）、共享狀態新增 cognitive_trace.jsonl(W)；system_audit.py 新增 `_audit_skill_doctor()` + 12 個 `_sd_check_*` 子方法（認知層檢查）、共享狀態讀取新增 cognitive_trace.jsonl(R)、`_check_skills` glob bug 修復；綠區新增 `governance/cognitive_receipt.py`（扇入=1，CognitiveReceipt dataclass）+ `MUSEON_observatory.html`（扇入=0，前端儀表板）；葉子模組 45→47；共享狀態 27→28 |
| 2026-03-16 | v1.20 | Memory Reset 一鍵重置工具：新增 `doctor/memory_reset.py` 到綠區（扇入=0，純 CLI 工具）；覆蓋 25 個持久層（7 大類：A.身份×3、B.對話×7、C.知識×4、D.行為×3、E.評估×3、F.日誌×3、G.狀態×2）；葉子模組 44→45；不影響任何運行中模組（僅 Gateway 停機後使用） |
| 2026-03-16 | v1.19 | Memory Gate 記憶閘門：新增 `memory/memory_gate.py` 到綠區（扇入=1，brain.py import）；brain.py 扇出 31→32+（新增 MemoryGate 初始化）；brain.py Step 9.0 新增意圖分類閘門（classify_intent → decide_action → suppress_primals/suppress_facts）；brain.py `_observe_user()` 新增 suppress 參數（修改安全：不影響 G1/G3 外部模組） |
| 2026-03-16 | v1.18 | P5 斷路器半開 + Nightly 藍圖驗證：refractory.py 新增 `half_open` / `half_open_since` 狀態欄位，`check()` 支援半開試探性恢復（hibernate 30 分鐘→half_open→proceed），`record_failure()` 半開失敗→回到 hibernate，`record_success()` 半開成功→完全恢復；nightly_pipeline.py 新增 Step 30 `_step_blueprint_consistency()`（3 項檢查：藍圖存在性、新鮮度 72h 閾值、禁區模組路徑）；新增 `governance/refractory.py` 到黃區 |
| 2026-03-16 | v1.17 | P4 Doctor 藍圖感知：新增 `core/blueprint_reader.py`（綠區，扇入=0），解析 blast-radius.md 和 joint-map.md；system_audit.py 新增 Layer 8 BLUEPRINT（3 項檢查：藍圖存在性、新鮮度、禁區保護）；surgeon.py safety_review 新增 4.5b 動態扇入安全檢查（blast-radius 禁區/紅區攔截）；morphenix_standards.py 新增 B1 藍圖禁區規則（Hard Rule 層級攔截） |
| 2026-03-16 | v1.16 | P3 健康分數真實化：governor.py Step 4.1 `_dendritic.tick()` 之前新增 immunity 未解決事件注入（`immunity._incidents` → `dendritic.record_event()`），DendriticScorer 健康分數首次反映 immunity 未解決事件 |
| 2026-03-16 | v1.15 | P2 事件匯聯：governor.py 新增 `_on_incident_callback` + `set_incident_callback()` + `_fire_incident_callback()`（incident 回調機制），`_run_immunity_cycle()` 三個分支新增回調觸發（先天/後天/未知）；server.py 新增 `_bridge_incident_to_pulsedb()` 回調橋接 PulseDB.incidents 表——Governor 的 immunity 事件首次同步到 PulseDB |
| 2026-03-16 | v1.14 | P1 後天免疫路徑修復：governor.py `_run_immunity_cycle()` 先天/後天免疫匹配成功後新增 `immunity.learn(incident)` 呼叫（2 處）——接通抗體學習路徑；immunity.py `resolve_by_symptom()` 事件解決後新增 `self.learn(inc)` 呼叫——事後解決也能生成抗體 |
| 2026-03-16 | v1.13 | P4 PULSE.md 自省清洗：brain.py 新增 `_get_fact_correction_declarations()`（讀 fact_corrections.jsonl 注入 soul context）；proactive_bridge.py 新增 `_read_recent_fact_corrections()`（讀 fact_corrections.jsonl 注入自省上下文）；pulse_engine.py 新增 `_reflection_contains_stale_facts()`（寫入前過濾過期事實）+ `_write_reflection_to_pulse()` 新增過濾閘 |
| 2026-03-16 | v1.12 | P2 靜默閾值上調+推送品質門檻：proactive_bridge.py `SILENT_ACK_THRESHOLD` 8→200、`COMPANION_ACK_THRESHOLD` 10→100、`DAILY_PUSH_LIMIT` 15→8；`should_push()` 新增問句比率門檻（>50%→靜默）+`_is_duplicate_push()` Jaccard 重複度門檻（>0.7→靜默）；無新增共享狀態、無新增 import |
| 2026-03-16 | v1.11 | P1 推送上下文串接：telegram.py `_on_proactive_message()` 推送成功後呼叫 `_write_push_to_session()` 寫入 Brain session history（新增 Brain session 寫入副作用）；BDD feature 共享狀態數 26→27 |
| 2026-03-16 | v1.10 | P0 記憶事實覆寫：brain.py 新增 `_detect_fact_correction()`+`_handle_fact_correction()`+`_log_fact_correction()`（安全操作：獨立觀察方法）；vector_bridge.py 新增 `mark_deprecated()`、search() 新增 `filter_deprecated` 參數（向後相容，預設 True）；共享狀態 26→27 個 |
| 2026-03-16 | v1.9 | Phase 4 飛輪多代理實質化：department_config 新增 full_system_prompt/model_tier；新增 multi_agent_executor.py（綠區，扇入=1）、response_synthesizer.py（綠區，扇入=1）、flywheel_flow.py（綠區，扇入=0）；okr_router 新增 route_extended() 回傳輔助部門；brain.py 扇出 29→31+（新增 MultiAgentExecutor, ResponseSynthesizer）；memory_manager 新增 dept_id/dept_filter 參數（向後相容） |
| 2026-03-16 | v1.8 | Phase 3 日記+群組ANIMA：SoulRingStore→DiaryStore 重命名（新增 entry_type/highlights/learnings 欄位）；brain.py 群組訊息更新 ANIMA_USER（L1-L7 半權重+L8_context_behavior_notes）；新增 pulse/group_session_proactive.py（綠區，扇入=1，監聽 GROUP_SESSION_END）；telegram.py 新增群組閒置偵測+GROUP_SESSION_END 事件發布；heartbeat_engine.py 新增 schedule_delayed_task()；server.py 新增 /api/anima/user/group-behaviors；nightly _step_soul_nightly→_step_diary_generation |
| 2026-03-16 | v1.7 | Phase 2 八原語接線：新增 agent/primal_detector.py 到綠區（扇入=1）；brain.py 扇出 28→29+（新增 PrimalDetector 初始化）；vector_bridge.py 扇入 6→7、collections 7→8（新增 primals）；skill_router/persona_router/reflex_router/okr_router 新增 Optional user_primals 參數（向後相容） |
| 2026-03-16 | v1.6 | Docker 沙盒驗證器上線：新增 nightly/morphenix_validator.py 到綠區（扇入=1），Dockerfile 修復（補齊專案依賴 + jieba + PYTHONPATH + addopts 覆蓋），image `museon-validator:latest` 已建構並驗證（1637 passed） |
| 2026-03-15 | v1.5 | DNA27 深度修復：幽靈訂閱 3→0（telegram 2 個移除 + server ActivityLogger 2 個修正）、事件健康度 52.5%→67.9%、ANIMA_MC 殘餘漏洞已修復（_observe_self + _merge_ceremony 改用 Store.update()） |
| 2026-03-15 | v1.4 | 9.5 精度修復：健康快照共享狀態 24→26（同步 joint-map v1.5） |
| 2026-03-15 | v1.3 | 全面覆蓋修復：新增 doctor/system_audit、mcp_server、federation/skill_market、federation/sync 到黃區；健康快照同步（共享狀態 16→24） |
| 2026-03-15 | v1.2 | 藍圖完整性修復：新增 evolution/outward_trigger, evolution/wee_engine, evolution/evolution_velocity, guardian/daemon 到黃區 |
| 2026-03-15 | v1.1 | 合約 1：新增 AnimaMCStore 模組，anima_tracker 鎖風險標記為已修復 |
| 2026-03-15 | v1.0 | 初始建立，176 模組分析，6 Hub + 42 葉子，38 孤兒事件 |
