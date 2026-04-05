# MUSEON 系統拓撲圖 v1.91

> 本文件是 MUSEON 所有子系統及其關聯性的 **唯一真相來源（Single Source of Truth）**。
> 新增模組、Debug、審計時必須參照此文件，確保不遺漏依賴關係。
> **v1.91 (2026-04-06)**：新增 x-ray 透視引擎節點（Product Hub）——product 群組新增 `x-ray` Skill 節點（三維根因透視引擎，plugin，扇入=1 user 觸發，扇出=4）；新增 4 條 cross 連線（x-ray→knowledge-lattice 診斷結晶寫入、x-ray→dse 方案驗證、x-ray→fix-verify 驗收閉環、x-ray→plan-engine 修復行動計畫化）；Product Hub 8→9 個節點，plugin-registry 82→83 個外掛。213+7 節點，連線數 +4。同步 blast-radius v2.09、memory-router v1.31。
> **v1.90 (2026-04-06)**：telegram.py Skill 缺口/重鍛 Inline Keyboard + brain.py ctx.user_id 修復——`channels/telegram.py` Skill 缺口提案流程升級：`_on_skill_gap_proposal` 從同步純文字 DM 改為非同步 Inline Keyboard 互動（新增 `_send_skill_gap_proposal_with_keyboard()` 異步方法 + 4 個 callback action 路由：`skill:gap_approve`/`skill:gap_ignore`/`skill:reforge_approve`/`skill:reforge_ignore`，telegram→skill-requests 新增讀寫路徑（gap_approve/reforge_approve 寫入 pending_dse_confirmed 狀態，gap_ignore/reforge_ignore 刪除 req 檔））；`_handle_skill_callback` 路由分支 4→8；telegram 節點描述更新（Skill 互動新增 gap/reforge 四個 callback 分支）；`agent/brain.py` 三處 `ctx.user_id` 修復為直接使用 `user_id` 參數（v1 殘留 bug，修復 absurdity-radar + constellation-radar 靜默失敗）；brain.py 新增 C-traits 提取注入 skill-router Layer 4（純方法擴充，節點/連線不新增）。節點數不變（212+7），新增 1 條 data 連線（telegram→skill-requests 讀寫路徑新增，gap_accumulator→telegram 觸發鏈已在 v1.85 記錄）。同步 blast-radius v2.08、joint-map v1.75。
> **v1.89 (2026-04-06)**：Nightly 拆分 + e2e probe_health 修復 + skill_qa_gate bug 修復——`nightly_pipeline.py` 拆分為 7 個 Mixin（`nightly_steps_memory.py`、`nightly_steps_morphenix.py`、`nightly_steps_skill.py`、`nightly_steps_identity.py`、`nightly_steps_ecosystem.py`、`nightly_steps_maintenance.py`、`nightly_steps_persona.py`），nightly-pipeline 節點描述更新（從單一 3000 行模組改為 Mixin 組合架構，7 個 Mixin 各自封裝對應步驟群組）；新增 7 個 nightly Mixin 子節點（扇入=1 各自由 nightly-pipeline import，扇出=各 Mixin 擁有的步驟數）；`brain.py` 新增 `probe_health()` 方法（e2e 健康探針，直接呼叫 LLM 確認大腦可應答）；`vital_signs.py` e2e_flow 從手動 LLM 呼叫改為呼叫 `brain.probe_health()`（brain→vital-signs 接線修復，扇入由 0→1）；`skill_qa_gate.py` 修復 `startswith` bug（曾錯誤判斷 Skill 路徑前綴，現已修正）。Nightly Mixin 拆分為純內部重構（節點數統計：212 個主節點 + 7 個 Mixin 子節點，連線數不變）。同步 blast-radius v2.07、persistence-contract v1.58、joint-map v1.74。
> **v1.88 (2026-04-05)**：五虎將自癒管線四修復藍圖同步——nightly 群組 `musedoc`（MuseDoc 修復執行者）內部邏輯補全：rolled_back 分支接線完整；新增 `auto-expire-stale` 子功能（CRITICAL+7 天+服務已恢復→fixed_externally，節點不新增，musedoc 內部方法）；`doctor` 群組新增 `rb-010-sqlite`（RB-010 SQLite 損壞修復 Runbook，C→B→A 瀑布策略，扇入=0，扇出=1：SAFE_DBS 三個 SQLite 檔案）；museoff L6c probe 修復，blast_origin + prescription 物件接線補全。新增 1 條 internal 連線（musedoc→rb-010-sqlite 當 db_error 且 corruption signal 時觸發）。211+1=212 節點，566+1=567 連線。同步 blast-radius v2.05。
> **v1.87 (2026-04-05)**：Phase 4 FV 藍圖同步——生態系雷達 + 語意審計 + 信任追蹤——nightly 群組新增 `ecosystem-radar`（Step 17.5，週一限定外部生態掃描，扇入=1 nightly-pipeline，扇出=1 morphenix/notes/scout_ecosystem_*.json）、`skill-trust-tracker`（Skill 信任分數追蹤器 prototype，扇入=0 目前獨立，扇出=1 _system/skill_trust_scores.json）；skill-qa-gate 節點新增 D1.5 語意審計子元件 `semantic-auditor`（純 CPU 啟發式規則，risk_score≥0.5→直接 quarantine）；新增 4 條連線（nightly-pipeline→ecosystem-radar，ecosystem-radar→morphenix/notes（scout_ecosystem_*.json 寫入），skill-qa-gate→semantic-auditor，semantic-auditor→skill_qa_gate quarantine）；_FULL_STEPS 53→54（新增 17.5）；209+2=211 節點，562+4=566 連線。
> **v1.86 (2026-04-05)**：Phase 0 Nightly 減法手術（純內部步驟調整，節點/連線不變）——nightly-pipeline 節點的 _FULL_STEPS 從歷史峰值 63 縮減至 53；12 個 ghost steps（5.5/6/8/9/10.5/10.6/11/13.7/14/15/16/19）標記 DORMANT（保留 _step_* 方法，移出執行列表）；validate_nightly_steps.py 硬上限 55 守護；nightly_report.json 移入 .gitignore，morning_report 三層降級。節點數、連線數不變。
> **v1.85 (2026-04-05)**：能力缺口偵測系統——nightly 群組新增 `gap-accumulator` 節點（三軌道 A/B/C 缺口累積，扇入=1 brain，扇出=3 vector-bridge/morphenix/event-bus）；新增 5 條 cross 連線（brain→gap-accumulator 兩注入點、gap-accumulator→vector-bridge、gap-accumulator→morphenix/notes/、gap-accumulator→event-bus）+ 1 條 event-bus→telegram 訂閱（SKILL_GAP_PROPOSAL+SKILL_REFORGE_PROPOSAL）；208+1=209 節點，556+6=562 連線。
> **v1.84 (2026-04-05)**：五個新功能補登——nightly 群組新增 `breath-analyzer`（Step 34.8 呼吸五層分析）和 `vision-loop`（Step 34.9 週日願景迴圈）；agent 群組新增 `consultant-supplement`（L2 後補充挑戰/提醒）；data 群組新增 `decision-atlas`（決策圖譜資料節點）；新增 9 條連線（nightly-pipeline→breath-analyzer、nightly-pipeline→vision-loop、vision-loop→constellation-radar(R)、vision-loop→decision-atlas(R)、vision-loop→breath/patterns(R)、brain-prompt-builder→decision-atlas(R)、server→consultant-supplement 初始化、telegram-pump→consultant-supplement 觸發、consultant-supplement→telegram 輸出）；更新統計：205+3=208 節點，547+9=556 連線。
> **v1.83 (2026-04-04)**：星座層級化——群組定義表新增 Layer 欄位（constellation = meta 元層）；新增層級模型說明段落；constellation 群組描述更新為「Skill 之上的多維追蹤框架」。
> **v1.82 (2026-04-04)**：星座系統——新增 `constellation` 群組（1 Hub + 10 節點共 11 個）；新增 10 條 internal 連線（constellation-radar→各星座）+ 15 條 cross 連線（constellation-probe→brain/brain-prompt-builder、荒謬→4個領域星座、5個星座→對應 Skill、absurdity-radar↔constellation-radar 同步、nightly-pipeline→constellation-radar、skill-router→constellation-radar）；群組色碼 `#9B59B6`（紫色系）；統計：194+11=205 節點，522+25=547 連線。
> **v1.81 (2026-04-04)**：Knife 2+3 變更——llm 群組新增 `semantic-response-cache`（Qdrant-backed 語意回覆快取，零 LLM token）；新增 3 條連線（brain→semantic-response-cache L1 查詢快取、l4-cpu-observer→semantic-response-cache 回覆後寫入、semantic-response-cache→qdrant collection 讀寫）；brain_tools.py tool-use loop 改用 --resume session 避免重送 system prompt；cron_registry.py 新增 quota circuit breaker（quota 耗盡跳過 LLM cron jobs）；cron 頻率調整（breath-pulse 每小時1次、curiosity-research 週二次、business-case 週一次）。
> **v1.80 (2026-04-04)**：L4 CPU Observer 架構更新——agent 群組新增 `l4-cpu-observer`（CPU-only 對話後觀察者，取代 Haiku L4 agent spawn，零 LLM 呼叫，<10ms）；brain-tools 描述更新（_classify_complexity 已改為 CPU-only v12）；新增 4 條連線（brain→l4-cpu-observer、l4-cpu-observer→context-cache/session-adjustments/memory）。
> **v1.79 (2026-04-02)**：補齊 absurdity-radar 孤島連線——新增 3 條 internal 連線（`brain→absurdity-radar` load/update/save、`brain-prompt-builder→absurdity-radar` persona zone 注入、`nightly-pipeline→absurdity-radar` Step 32.5 recalc）；absurdity-radar 節點扇入由 0→3，孤島問題修復。
> **v1.78 (2026-04-02)**：荒謬雷達系統——新增 `agent/absurdity_radar.py`（純函數模組，無 class，提供 load/save/update_radar）；
> `skill_router.py` 新增 Layer 4 (absurdity gap affinity)，讀取 Skill manifest 的 `absurdity_affinity` + user radar；
> `brain.py` 新增荒謬雷達讀取/更新呼叫（load_radar → match() → update_radar_from_skill → save_radar）；
> `brain_prompt_builder.py` 新增 `_build_absurdity_radar_context()` 注入 persona zone；
> `nightly_pipeline.py` 新增步驟 32.5 (`_step_absurdity_radar_recalc`) + 步驟 33 crystal rules 硬上限。
> **v1.77 (2026-04-02)**：藍圖交叉引用同步——blast-radius v1.95→v1.96（ares→athena 更名同步），同步 blast-radius v1.96、joint-map v1.64、persistence-contract v1.50、memory-router v1.23。
> **v1.76 (2026-04-01)**：.runtime 路徑廢除——Gateway 統一從 src/ 啟動（supervisord.conf + start-gateway.sh 路徑已改）；8 個 Python 模組移除 .runtime 分支邏輯；排程優化（Step 13.5 全清、30min job 錯開、Step 18.7 快取）。同步 blast-radius v1.95。
> **v1.75 (2026-04-01)**：Phase 1-3 十項修復——AlgedonicAlert 新增靜默時段（23:00-07:00）；Guardian daemon 新增 credential 檢查（L1 巡檢擴充）；Nightly Step 26 session_cleanup 移除（cron 已覆蓋）；cron skill-acquisition-scan/tool-discovery-scan 移除（Nightly 已覆蓋）；Gateway 重啟路徑統一（launchctl 引用全部移除，統一為 restart-gateway.sh）。同步 blast-radius v1.94。
> **v1.74 (2026-04-01)**：Phase A-C 死碼清理 + signal_lite 遷移——移除 `brain-p3-fusion`（P3 融合層已清除）、`brain-observer`（L4 觀察者已刪除）2 個節點；`reflex-router`、~~`dna27`~~ 同步標記刪除（路由功能已退役）；新增 `signal-lite` 節點（輕量信號路由，取代 reflex_router）；移除相關連線：brain→brain-p3-fusion、brain→reflex-router、brain→brain-observer、primal-detector→reflex-router、nightly→reflex-router 共 5 條；更新 brain.py Step 3 描述（DNA27 反射路由器 → signal_lite 信號路由）；同步 blast-radius v1.93。
> **v1.73 (2026-04-01)**：Brain 統一重構——agent 群組刪除 `brain-fast`（L1 Sonnet，已合併回 brain 統一管線）、`brain-deep`（L2 Opus，已合併回 brain）2 個節點；新增 `signal-lite`（輕量信號器，取代 reflex_router 路由功能）1 個節點；`reflex-router` 標記為 deprecated（路由退役，人格定義遷移到 persona_digest）；刪除 brain→brain-deep、brain-fast→brain-observer 2 條 internal 連線；brain 節點名稱從 "Brain-Fast (L1)" 更新為 "Brain (統一管線)"；193→192 節點，521→519 連線。同步 blast-radius v1.92、joint-map v1.60、persistence-contract v1.46。
> **v1.72 (2026-03-31)**：推播系統重構——pulse 群組刪除 `push-budget` 節點（PushBudget 全局推送預算管理器已移除）；刪除 3 條 internal 連線（`pulse-engine→push-budget`、`proactive-bridge→push-budget`、`push-budget→pulse-db`）；新增 1 條 cross 連線（`cron→museoff` cron 健康度讀取，cron.status() 被 museoff.py L7 消費）；新增 1 條 internal 連線（`proactive-dispatcher→haiku-llm` LLM adapter 接入，三桶分級配額決策）；刪除 1 條 cross 連線（`proactive-dispatcher→push-budget` 推播前去重配合已清除）；194→193 節點，522→521 連線（刪除 push-budget 節點 -1、刪除 5 條連線 -5、新增 2 條連線 +2 = 521）。同步 blast-radius v1.91、joint-map v1.59、persistence-contract v1.45。
> **v1.71 (2026-03-31)**：Persona Evolution 系統——agent 群組新增 `trait-engine`（10 維度特質代謝）、`growth-stage-computer`（Kegan 成熟度計算）、`dissent-engine`（Crystal Lattice 矛盾偵測）、`mask-engine`（每用戶臨時人格適應層）、`momentum-brake`（特質 delta 保護）5 個節點；nightly 群組新增 `nightly-reflection-engine`（LLM 自我反思 P-trait 演化）1 個節點；新增 3 條 internal 連線（brain→dissent-engine、brain→mask-engine、nightly-pipeline→nightly-reflection-engine）+ 7 條 cross 連線（brain-observation→trait-engine/growth-stage-computer、drift-detector→momentum-brake、nightly-reflection-engine→anima-mc-store/soul-ring、dissent-engine→crystal-rules、mask-engine→anima-mc-store）；188→194 節點，512→522 連線。同步 blast-radius、joint-map 待更新。
> **v1.69 (2026-03-31)**：9 條斷裂接線修復——新增 6 條 cross 連線：`surgeon→triage-step`（手術完成 SYSTEM_FAULT write_signal）、`morphenix-executor→triage-step`（迭代完成 SYSTEM_FAULT + 迭代失敗 BEHAVIOR_DRIFT write_signal x2）、`feedback-loop→triage-step`（品質下降 LEARNING_GAP write_signal）、`museoff→triage-step`（≥3次 SYSTEM_FAULT + escalate_to_morphenix）、`periodic-cycles→triage-step`（高原警報 LEARNING_GAP write_signal）、`skill-router→tuned-parameters`（讀取 tuned_parameters.json RC 權重）；新增 1 條 internal 連線：`finding→finding-counts`（record_occurrence 持久化計數）。triage-step 扇入由 0→6（新增 surgeon/morphenix-executor/feedback-loop/museoff/periodic-cycles 五個覺察源）。同步 blast-radius v1.87、joint-map v1.57、persistence-contract v1.43。
> **v1.68 (2026-03-31)**：體液系統迭代——governance 群組新增 `algedonic-alert` 節點（治理警報推播引擎，扇入=1 from governor）；nightly 群組新增 `triage-step`（Nightly 分診，Step 5.8 前置）、`triage-to-morphenix`（HIGH 訊號→Morphenix 迭代筆記橋接）2 個節點；core 群組新增 `awareness-signal`（AwarenessSignal 統一格式，純 dataclass）、`session-adjustment`（SessionAdjustment 即時調整管理器）2 個節點；新增 9 條連線（governor→algedonic-alert、nightly-pipeline→triage-step→triage-to-morphenix→morphenix/proposals/、triage-step→session-adjustment、brain-prompt-builder→session-adjustment（讀）、brain-prompt-builder→skill-lessons（讀 _lessons.json）、telegram-pump→event-bus CHANNEL_MESSAGE_RECEIVED）；腦前台（brain_prompt_builder）四路接線完成。同步 blast-radius v1.86、joint-map v1.56、memory-router v1.18、persistence-contract v1.42。
> **v1.67 (2026-03-30)**：Skill 自動演化管線——nightly 群組新增 4 個模組節點：`skill-draft-forger`（Skill 草稿鍛造引擎，Step 19.6）、`skill-install-worker`（9 步自動安裝引擎）、`skill-qa-gate`（三維品質閘門，Step 19.7）、`skill-health-tracker`（Per-Skill 健康度追蹤，Step 19.5）；新增 8 條 internal 連線（nightly-pipeline→skill-health-tracker/skill-draft-forger/skill-qa-gate、skill-draft-forger→skill-qa-gate→skill-install-worker、skill-health-tracker→skill-draft-forger、telegram-callback→skill-install-worker）；channel 群組 telegram 節點新增 `skill:approve/reject` callback handler。Nightly 步驟 51→54（新增 19.5/19.6/19.7）。
> **v1.66 (2026-03-30)**：新增 13 個 Skill 節點（ad-pilot、equity-architect、biz-collab、video-strategy、course-forge、shadow-muse、daily-pilot、talent-match、brand-project-engine、finance-pilot、prompt-stresstest、workflow-brand-consulting（已存在）、biz-diagnostic（已存在））——business hub 新增 ad-pilot/equity-architect/biz-collab；creative hub 新增 video-strategy/course-forge；thinking hub 新增 shadow-muse/daily-pilot/talent-match；product hub 新增 brand-project-engine/finance-pilot；evolution hub 新增 prompt-stresstest；新增對應 13 條 internal 連線。
> **v1.65 (2026-03-30)**：商業模式健檢引擎（biz-diagnostic）——skills-business-hub 新增 `biz-diagnostic` Skill 節點（商業模式健檢引擎，plugin，Business Hub）；新增 Python 模組 `src/museon/darwin/biz_diagnostic.py`（convert_to_strategy_brief() 參數轉換器）；新增 5 條 cross 連線（biz-diagnostic→darwin/business-12/report-forge/ssa-consultant、brand-discovery→biz-diagnostic）；plugin-registry 新增條目（Business Hub 第 9 個 Skill）；memory-router v1.15 新增 diagnostic_crystal 路由。同步 blast-radius（biz-diagnostic 扇入=1，綠區）。
> **v1.64 (2026-03-30)**：市場戰神（Market Ares）——新增 `market_ares` 群組（9 子包 16 個模組節點）；新增儲存路徑 `data/market_ares/market_ares.db`（SQLite WAL，6 表：regions/archetypes/simulations/snapshots/competitors/partners）；模組間內部連線 12 條（engine→strategy_impact/social_contagion/oscillation、dashboard→charts、final_report→turning_point、energy_mapper→mapping_config.yaml、kmeans_refine→hierarchical、self_drive_coach→tw_demographics、chauffeur_coach→tw_demographics、report_renderer→final_report、strategy_optimizer→models、weekly_insight→models）；外部連線 0 條（獨立模組，不影響既有系統）。同步 blast-radius v1.83、joint-map v1.53、memory-router v1.14、persistence-contract v1.41。
> **v1.63 (2026-03-29)**：統一發送出口防漏——response-guard 節點描述更新（全通道內容黑名單清理，取消群組/私訊分流）；telegram-pump→response-guard 連線描述更新（所有發送路徑統一走 _safe_send()，消除 9 處直送）。同步 blast-radius v1.82。
> **v1.62 (2026-03-29)**：戰神系統（Ares）——thinking 群組新增 `anima-individual`（ANIMA 個體追蹤引擎，plugin）、`ares`（戰神系統工作流，workflow）2 個 Skill 節點；新增 Python 模組 `src/museon/ares/`（profile_store.py, graph_renderer.py, external_bridge.py）；新增儲存路徑 `data/ares/profiles/`；新增 22 條 cross 連線（ares→anima-individual/wan-miu-16/energy-reading/combined-reading/master-strategy/shadow/xmodel/pdeif/roundtable/business-12/ssa-consultant/knowledge-lattice/user-model/c15、anima-individual→wan-miu-16/energy-reading/combined-reading/shadow/master-strategy/xmodel/knowledge-lattice/user-model）；同步 blast-radius v1.80、joint-map v1.52、memory-router v1.13、persistence-contract v1.40。
> **v1.61 (2026-03-29)**：OneMuse 能量解讀技能群——thinking 群組新增 `energy-reading`（八方位能量解讀）、`wan-miu-16`（萬謬16型人格）、`combined-reading`（合盤能量比對）3 個 Skill 節點；新增 11 條 cross 連線（energy-reading→dharma/resonance/knowledge-lattice/user-model、wan-miu-16→energy-reading/knowledge-lattice/user-model、combined-reading→energy-reading/wan-miu-16/knowledge-lattice/user-model）；同步 blast-radius v1.79、joint-map v1.51、memory-router v1.12、persistence-contract v1.39。
> **v1.60 (2026-03-28)**：新增 MuseDoctor 第六虎將節點——`musedoctor`（持續巡邏員，綠區扇入=0）；新增 3 條連線：musedoctor→auto-repair（修復引擎）、musedoctor→nightly-pipeline（_FULL_STEPS 驗證）、cron-registry→musedoctor（每 8 分鐘排程）；免疫系統分工補注：Gateway 急症由 museoff 負責，musedoctor 專責慢循環維護。
> **v1.59 (2026-03-28)**：死碼清理 20 個模組後拓撲同步——移除已刪除節點：channels/line（LINE 通道）、channels/electron（Electron 桌面）、agent/dna27（DNA27 反射叢集，由 reflex_router 取代）、agent/pending_sayings、agent/routing_bridge、llm/client、llm/vision、doctor/scalpel_lessons、governance/cognitive_receipt、learning/strategy_accumulator（已移入 insight-extractor 模組）、memory/epigenetic_router、memory/proactive_predictor、multiagent/flywheel_flow、pulse/heartbeat_activation、pulse/group_session_proactive、pulse/proactive_activation、pulse/telegram_pusher、security/trust、tools/document_export、tools/report_publisher；更新 fan_in 數據：event_bus 45→46、data_bus 16→15、message 13→14、pulse_db 10→11、vector_bridge 7→9；新增破損 import 告警（brain_fast.py → input_sanitizer/ceremony 待修）。
> **v1.58 (2026-03-28)**：supervisord 進程管理層引入——架構從 `launchd → uvicorn` 升級為 `launchd → supervisord → uvicorn`；新增 `com.museon.supervisord` launchd 服務節點（KeepAlive=true）；`data/_system/supervisord.conf` 管理 museon-gateway 程序（autorestart=unexpected + exitcodes=0 + startretries=5）；`com.museon.gateway.plist` 已 unload，launchd 不再直接管理 gateway；MuseOff `_triage("restart_gateway")` 改用 `supervisorctl start`（supervisor 路徑 `/Users/ZEALCHOU/Library/Python/3.9/bin/`）；`restart-gateway.sh` v3.0 改用 `supervisorctl restart`。新增 1 個中間層節點（supervisord），其餘節點連線不變。
> **v1.57 (2026-03-28)**：Gateway 穩定性改動——`gateway/server.py` 新增 `/health/live` 純 liveness 端點（不影響節點連線數）；`doctor/probes/liveness.py` 改查 `/health/live` + 連續 3 次閾值（不影響節點）；`scripts/workflows/restart-gateway.sh` v2.1 移除 kickstart -k；plist PATH 新增 `/usr/sbin`（macOS lsof 修復）。Gunicorn pre-fork 在 macOS 下因 objc_initializeAfterForkError 不可用，維持 launchd → uvicorn 直接管理架構。節點連線不變。
> **v1.56 (2026-03-27)**：Skills 新增——creative 群組新增 `human-design-blueprint`（人類圖靈魂藍圖分析引擎）1 個節點；plugin-registry 新增條目；memory-router 新增 user-model 路由（解讀結果→使用者畫像）。
> **v1.55 (2026-03-27)**：MCP 工具擴充——external 群組新增 `playwright-mcp`（瀏覽器自動化）、`fetch-mcp`（網頁讀取）2 個節點 + 2 條 cross 連線（mcp-server→playwright-mcp、mcp-server→fetch-mcp）；`.mcp.json` 新增 Playwright + Fetch 伺服器設定。同步 blast-radius v1.72。
> **v1.54 (2026-03-27)**：有機體進化計畫 Phase 1-9——新增 6 個節點（proactive-dispatcher、memory-graph、insight-extractor、strategy-accumulator、shared-board、skill-counter）；新增 learning 群組；pulse 群組 proactive-dispatcher 統一攔截推播；Nightly 精簡移除 3 個步驟（7.5/10.5/11）；五虎將共享看板協調機制；cron 直接推送全部納管 ProactiveDispatcher。
> **v1.53 (2026-03-26)**：v2 Brain 四層架構 + 死碼清理——agent 群組新增 `brain-deep`（L2 Opus 引擎）、`brain-tool-loop`（獨立 tool-use 迴圈）、`brain-observer`（L4 觀察者）3 個節點 + 5 條連線；`brain-fast` 升級為 L1 Sonnet + escalation 機制；移除 federation 群組（skill-market + federation-sync 2 個節點）+ installer 群組（4 個子節點 + 1 個 Hub 節點）；nightly 新增 Step 31 context_cache。
> **v1.51 (2026-03-25)**：教訓蒸餾+斷裂管線修復+Fix-Verify Workflow——nightly 群組新增 2 個步驟節點（`lesson-distill` Step 5.6.5 教訓蒸餾、`client-profile-update` Step 18.5 客戶互動萃取）；agent 群組 `brain-prompt-builder` 新增 3 條 cross 連線（→intuition-heuristics 注入、→knowledge-lattice record_success、→external-anima search）；gateway 群組 `server` 新增 1 條 cross 連線（→guardian mothership_queue 消費）；doctor 群組 `musedoc` 新增 `_fix_verify` 三維驗證方法；新增 `fix-verify` Workflow Skill（Evolution Hub）；`brain.py` MemoryManager user_id cli_user→boss。同步 blast-radius v1.65、joint-map v1.43、memory-router v1.9。
> **v1.50 (2026-03-25)**：server.py 拆分藍圖補齊 + 三層洩漏預防——channel 群組新增 3 個節點（`telegram-pump` 訊息泵、`routes-api` API 端點註冊、`cron-registry` cron 任務註冊）；新增 6 條連線（gateway→telegram-pump/routes-api/cron-registry internal，telegram-pump→response-guard cross）；gateway 節點職責更新（3800 行，訊息泵/API/cron 已獨立）。三層洩漏預防架構：L1 brain-prompt-builder（prompt 約束）→ L2 telegram-pump（結構化剝離）→ L3 response-guard（黑名單安全網）；telegram-pump→response-guard 連線強化為雙重驗證（L2 剝離 + L3 sanitize）。restart-gateway.sh 新增 rsync 步驟。197 節點 487 連線。同步 blast-radius v1.64、joint-map v1.42。
> **v1.49 (2026-03-24)**：全面審計——修正統計摘要表（184→194 節點、456→481 連線），使摘要與版本紀錄一致。同步 blast-radius v1.62、joint-map v1.41、persistence-contract v1.34。
> **v1.48 (2026-03-24)**：操作記憶層架構——新增第六張藍圖 `operational-contract.md`（操作契約表）；新增 `scripts/workflows/` 可執行工作流目錄（publish-report.sh v4.0, restart-gateway.sh v1.0）；CLAUDE.md 新增 Tier 0 可執行性檢查 + 驗證鐵律；新增 `project-operational-memory.md` Procedure Crystal 設計文件；194 節點 481 連線（無新節點，純文件/腳本層變更）
> **v1.47 (2026-03-24)**：跨群組洩漏防禦——gov 群組新增 `response-guard` 節點（ResponseGuard 發送前 chat_id 二次驗證閘門，`governance/response_guard.py`）；新增 3 條連線（governance→response-guard internal、gateway→response-guard cross 發送前驗證、brain→response-guard cross 註冊 origin_chat_id）；194 節點 481 連線
> **v1.46 (2026-03-23)**：推送品質修復——pulse 群組新增 `push-budget` 節點（PushBudget 全局推送預算管理器）；新增 3 條 internal 連線（push-budget→pulse-db、pulse-engine→push-budget、proactive-bridge→push-budget）；193 節點 478 連線
> **v1.45 (2026-03-23)**：Project Epigenesis（DNA 式記憶系統重構）——agent 群組新增 4 個節點（epigenetic-router 表觀遺傳路由器、memory-reflector 反思引擎、proactive-predictor 需求預判、adaptive-decay ACT-R 衰減）；pulse 群組新增 1 個節點（anima-changelog 差分追蹤）；新增 12 條 cross 連線；VectorBridge 新增 soul_rings collection（第 9 個）；192 節點 475 連線
> **v1.44 (2026-03-23)**：三層調度員架構（腦手分離）——agent 群組新增 3 個節點（`dispatcher` L1 調度員、`thinker` L2 思考者、`worker` L3 工人）；新增 7 條 internal 連線；CLAUDE.md 改寫為 L1 調度員模式；新增 `data/_system/museon-persona.md` 人格隨身檔供 L2 載入；187 節點 463 連線
> **v1.43 (2026-03-23)**：全系統拓撲審計——補齊 70 條遺漏 cross 連線（🔴7 結構斷裂 + 🟠20 重要遺漏 + 🟡43 文件欠債）；移除 2 條幽靈連線（drift-detector→memory、zotero-bridge→vector-index）；修正 1 條方向反轉（federation-sync→nightly 改為 nightly→federation-sync）；拓撲覆蓋率 62.8% → 100%；184 節點 456 連線
> **v1.42 (2026-03-22)**：Sparse Embedder 全面啟動——sparse-embedder 節點升級為已啟動狀態；新增 skill-router→sparse-embedder、memory→sparse-embedder 跨系統連線（hybrid_search 消費者接線）；Nightly Pipeline 新增 Step 8.7（IDF 重建 + 回填）；184 節點 389 連線
> **v1.41 (2026-03-22)**：Brain Prompt Builder 健康檢查——補齊 3 條遺漏連線（brain-prompt-builder→anima-mc-store/data-bus/anthropic-api）；常數化 20+ 個魔術值；Token zone 耗盡 warning 日誌；budget.remaining() None 防禦；新增單元測試；184 節點 387 連線
> **v1.40 (2026-03-22)**：Brain Tools 健康檢查——補齊 2 條遺漏連線（brain-tools→anthropic-api LLM 呼叫、brain-tools→data-bus session/JSONL 持久化）；常數化 8 個魔術值；Nightly Step 27 擴充按日期 JSONL 清理；新增 16 個 brain_tools 單元測試；184 節點 384 連線
> **v1.39 (2026-03-22)**：使用者 ↔ ANIMA 連線補齊——新增 3 條 cross 連線：zeal→anima-mc-store（Owner 互動觸發 ANIMA_MC 更新）、verified-user→anima-mc-store（配對使用者 L1-L8 觀察）、external-user→anima-mc-store（外部使用者觀察）；auth 持久化修復（PairingManager/AuthorizationPolicy 首次 load 時自動初始化空檔案）；184 節點 382 連線
> **v1.38 (2026-03-22)**：L3-A2 Brain Mixin 拆分——brain 節點拆分為 core + 5 Mixin 子模組 + brain_types 共享型別；agent 群組新增 `brain-prompt-builder`、`brain-dispatch`、`brain-observation`、`brain-p3-fusion`、`brain-tools`、`brain-types` 6 個節點 + 6 條 internal 連線；184 節點 379 連線
> **v1.37 (2026-03-22)**：Brain 三層治療——agent 群組新增 `chat-context`（ChatContext dataclass，r=0.7）、`deterministic-router`（確定性任務分解器，r=1.0）2 個節點；新增 2 條 internal 連線（brain→chat-context、brain→deterministic-router）；178 節點 373 連線
> **v1.36 (2026-03-22)**：使用者節點精細化——channel 群組 `user` 拆分為 `zeal`（CORE 主人）、`verified-user`（VERIFIED 動態配對）、`external-user`（EXTERNAL 群組外部成員）三節點；補上遺漏的 `discord` 節點；新增/更新 8 條 flow 連線反映實際使用者分流；175 節點 369 連線
> **v1.35 (2026-03-22)**：P0-P3 升級——Evolution Hub 新增 2 個 Skill 節點（system-health-check、decision-tracker）；新增 5 條跨群組連線（report-forge→knowledge-lattice、system-health-check→knowledge-lattice/morphenix、decision-tracker→knowledge-lattice/user-model）；173 節點 361 連線
> **v1.34 (2026-03-22)**：經驗諮詢閘門——新增 1 條 cross 連線 `brain → data-bus`（經驗回放搜尋 activity_log.search()）；171 節點 351 連線
> **v1.33 (2026-03-22)**：InteractionRequest 跨通道互動層——channel 群組新增 `line` 節點（LINE 通道適配器）；gateway 群組新增 `interaction-queue` 節點（InteractionQueue 非阻塞等待佇列）；新增 8 條連線（interaction-queue ↔ telegram/discord/line/gateway）；171 節點 358 連線
> **v1.32 (2026-03-22)**：Recommender 激活修復——`recommender` 節點半徑 0.7→0.9（從幽靈模組升級為實際接線）；新增 cross 連線 `recommender → crystal-store`（經由 CrystalStore API 讀取結晶+連結）；brain.py `_recommender` 初始化接線確認；169 節點 350 連線
> **v1.31 (2026-03-22)**：Knowledge Lattice 持久層遷移——data 群組新增 `crystal-store` 節點（CrystalStore SQLite WAL 統一存取層）+ 7 條連線
> **v1.30 (2026-03-21)**：授權系統升級——gov 群組新增 `authorization` 節點（配對碼+工具授權+分級策略）+ 5 條連線；持久化 `~/.museon/auth/`
> **v1.29 (2026-03-21)**：Skills 群組治理升級——新增 `hub` 欄位（9 種 Hub 分組）+ Workflow Stage 規格；詳見 `docs/skill-routing-governance.md`
> **v1.28 (2026-03-21)**：補全 skills 群組——7 Hub + 39 Skill 節點 + 91 條連線（從 3D 心智圖回補，修復拓撲⇄HTML 漂移）
> **v1.27 (2026-03-21)**：Skill 鍛造膠合層修復——VectorBridge 新增 index_all_skills()；Nightly Step 8.6 skill_vector_reindex；plugin-registry v2.3（+12 Skill 註冊）
> **v1.26 (2026-03-21)**：群組對話 DSE 三階段修復——brain.py P0 六類訊號分流 + 事實糾正偵測 + _observe_external_user v3.0；memory_manager chat_scope 隔離；multi_tenant ExternalAnimaManager v3.0；server.py 群組事實糾正+錯誤顯示啟用
> **v1.25 (2026-03-21)**：新增 deep-think、roundtable、investment-masters 拓撲節點 + 10 條連線
> **v1.24 (2026-03-21)**：A 區迭代 #1~#3 拓撲同步——MemGPT recall_tiered、Hybrid Retrieval sparse-embedder、GraphRAG 社群摘要 Layer 2.5
> **v1.23 (2026-03-20)**：補記 recommender 節點（知識推薦引擎）+ 3D 心智圖全面同步修復
> **v1.22 (2026-03-20)**：P3 前置交織融合——Step 5.5 前置多視角收集 + system_prompt 注入

---

## 使用方式

| 場景 | 如何使用 |
|------|---------|
| **新增模組** | 在 `nodes` 新增條目 → 在 `links` 定義所有輸入/輸出 → 跑驗證清單 |
| **Debug** | 找到問題節點 → 查上游（輸入）和下游（輸出）→ 逐一排查 |
| **審計** | `system_audit` 載入此文件 → 檢查孤立節點、缺失連線、循環依賴 |
| **迭代** | 修改前查影響範圍（所有相關 links）→ 修改後驗證無回歸 |

---

## 群組定義

| 群組 ID | 名稱 | 職責 | 色碼 | Layer |
|---------|------|------|------|-------|
| `center` | 核心 | 事件匯流排，全系統通訊樞紐 | `#C4502A` | - |
| `channel` | 通道入口 | 使用者訊息收發、WebSocket、排程 | `#C4502A` | - |
| `agent` | Agent / Brain | 主判斷中樞、技能路由、元認知 | `#2A7A6E` | - |
| `pulse` | Pulse 生命力 | 自主探索、推播、心跳、承諾追蹤 | `#B8923A` | - |
| `gov` | Governance | 三焦治理、免疫、護欄、沙盒 | `#2A6A8A` | - |
| `doctor` | Doctor 診斷 | 系統審計、自我診斷、自動修復 | `#2D8A6E` | - |
| `llm` | LLM 路由 | 模型選擇、預算、速限、快取 | `#5A5A6E` | - |
| `data` | 資料持久層 | 記憶、向量索引、技能庫、SQLite | `#7A7888` | - |
| `evolution` | Evolution 演化 | 外向演化、意圖雷達、研究消化、參數調諧 | `#6B3FA0` | - |
| `tools` | Tools 工具 | 工具註冊、探測、排程 | `#8A6A3E` | - |
| `nightly` | Nightly 夜間 | 31+ 步夜間整合管線、演化提案、好奇心路由 | `#9A3A1C` | - |
| `learning` | Learning 學習 | 持續學習引擎（洞見萃取、策略累積） | `#4A8A2A` | - |
| `billing` | Billing 計費 | Skill 調用計數、信任點數 | `#8A7A3E` | - |
| `external` | 外部服務 | SearXNG、Qdrant、Firecrawl、API | `#6A6880` | - |
| `skills` | Skills 生態系 | 外掛 Skill 語義群組（7 子中樞 + 41 Skill）；治理規格見 `skill-routing-governance.md` | `#8B5CF6` | - |
| `constellation` | 星座系統 | MUSEON 多維知識追蹤框架——9 個星座追蹤 Skill 使用模式，荒謬六芒星為底層 OS；Meta 層，在 Skill 之上 | `#9B59B6` | `meta` |

### 層級模型（Layer Model）

| Layer | 說明 | 群組 |
|-------|------|------|
| Meta（元層） | 追蹤 Skill 使用模式的多維知識框架，一個 Skill 可屬多個星座 | constellation |
| Core（核心層） | 所有 Skill、Agent、基礎設施群組 | 其餘所有群組 |

> 星座不「擁有」Skill，而是「追蹤」Skill 的使用對哪些維度產生影響。
> 星座→Skill 的連線在拓撲中表示為 cross 連線，在 3D 圖中渲染為從上方向下的追蹤線。

---

## 節點清單（Nodes）

### center — 核心
| ID | 名稱 | 中文 | Hub | 半徑 |
|----|------|------|-----|------|
| `event-bus` | Event Bus | 核心事件匯流排 | Yes | 3.2 |

### channel — 通道入口

> **使用者分層模型（v1.36）**：程式碼層已實作 TrustLevel 四層（CORE/VERIFIED/EXTERNAL/UNTRUSTED）、
> 私聊 vs 群組分流（session_id 格式 `telegram_{id}` vs `telegram_group_{id}`）、
> ExternalAnimaManager（外部使用者記憶 `data/_system/external_users/{uid}.json`）、
> SensitivityChecker + EscalationQueue（敏感問題升級到 owner 私聊確認）。
> 拓撲節點按信任層級拆分，反映訊息在 `gateway/telegram_pump.py`（v1.50 從 server.py 拆出）中的實際路由決策。

| ID | 名稱 | 中文 | 信任層級 | Hub | 半徑 |
|----|------|------|---------|-----|------|
| `zeal` | Zeal (Owner) | 主人 | CORE | - | 2.0 |
| `verified-user` | Verified User | 動態配對使用者 | VERIFIED | - | 1.2 |
| `external-user` | External User | 群組外部成員 | EXTERNAL | - | 1.4 |
| `telegram` | Telegram | 主通道（私聊 + 群組） | - | - | 1.6 |
| `gateway` | Gateway | WebSocket :8765 | - | - | 1.6 |
| ~~`line`~~ | ~~LINE~~ | ~~LINE@ 通道（已刪除 v1.59）~~ | - | - | - |
| `discord` | Discord | Discord 通道 | - | - | 1.2 |
| `cron` | Cron | 排程入口 | - | - | 1.2 |
| `mcp-server` | MCP Server | Claude Code 介面 | - | - | 1.2 |
| `interaction-queue` | Interaction Queue | 跨通道互動佇列 | - | - | 1.0 |
| `telegram-pump` | Telegram Pump | Telegram 訊息泵（收訊→Brain→驗證→發送） | - | - | 1.4 |
| `message-queue-store` | Message Queue Store | SQLite 訊息佇列持久化（crash recovery） | - | - | 1.0 |
| `brain-worker` | Brain Worker | 獨立 subprocess 運行 Brain.process()（process 隔離） | - | - | 1.0 |
| `routes-api` | Routes API | SkillHub + External API 端點註冊 | - | - | 0.8 |
| `cron-registry` | Cron Registry | 系統 cron 任務註冊（五虎將+41 排程） | - | - | 1.0 |

#### 使用者信任層級與訊息路由

```
zeal（CORE）
  ├─ 私聊 → telegram/line → gateway → brain.process() 直接處理
  ├─ 群組 @mention → telegram/line → gateway → 注入群組上下文 + 標記「老闆」
  └─ EscalationQueue 回覆 → 確認/拒絕外部使用者的敏感問題

verified-user（VERIFIED，經 PairingManager 動態配對）
  └─ 私聊 → telegram → gateway → brain.process()（信任等級略低於 CORE）

external-user（EXTERNAL）
  ├─ 群組 @mention → telegram/line → gateway → SensitivityChecker 分級
  │    ├─ 非敏感 → ExternalAnimaManager.update() + brain 處理
  │    └─ 敏感（L1/L2/L3）→ EscalationQueue → 等待 zeal 私聊確認
  └─ 群組非 @mention → 只記錄到 GroupContextDB + JSONL log，不進入 brain
```

### agent — Agent / Brain
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `brain` | Brain-Fast (L1) | L1 接待層（Sonnet + escalation JSON，簡單自答/複雜派 L2） | Yes | - | 2.8 |
| `brain-prompt-builder` | Brain Prompt Builder | Mixin: system prompt 建構（1668 行） | - | brain | 1.0 |
| `brain-dispatch` | Brain Dispatch | Mixin: 任務分派（1082 行） | - | brain | 1.0 |
| `brain-observation` | Brain Observation | Mixin: 觀察與演化（2003 行） | - | brain | 1.0 |
| `brain-tools` | Brain Tools | Mixin: LLM 呼叫（_call_llm）與 session 管理（966 行）。_classify_complexity 已改為 CPU-only（v12） | - | brain | 1.0 |
| `brain-types` | Brain Types | 共享 dataclass: DecisionSignal | - | brain | 0.7 |
| ~~`dna27`~~ | ~~DNA27~~ | ~~27 反射叢集（已刪除 v1.59）~~ | - | - | - |
| `skill-router` | Skill Router | 技能路由 | - | brain | 1.1 |
| `absurdity-radar` | Absurdity Radar | 荒謬雷達（純函數模組，load/save/update_radar，無 class） | - | brain | 0.8 |
| ~~`reflex-router`~~ | ~~Reflex Router~~ | ~~反射路由（已退役 v1.74，路由功能遷移至 signal_lite）~~ | - | - | - |
| `signal-lite` | Signal Lite | 輕量信號路由（取代 reflex_router，由 brain.py 直接呼叫） | - | brain | 0.8 |
| `dispatch` | Dispatch | 多技能編排 | - | brain | 1.0 |
| `knowledge-lattice` | Knowledge Lattice | 知識晶格 | - | brain | 1.1 |
| `plan-engine` | Plan Engine | 六階段計畫 | - | brain | 1.0 |
| `metacognition` | Metacognition | 元認知審查 | - | brain | 1.0 |
| `intuition` | Intuition | 五層直覺 | - | brain | 0.9 |
| `eval-engine` | Eval Engine | Q-Score | - | brain | 1.0 |
| `diary-store` | Diary Store | 日記存儲（原靈魂年輪） | - | brain | 0.9 |
| `onboarding` | Onboarding | 上線儀式 | - | brain | 0.9 |
| `multiagent` | Multiagent | 多代理協調 | - | brain | 0.9 |
| `multi-agent-executor` | Multi Agent Executor | 並行 LLM 執行器 | - | brain | 1.0 |
| `response-synthesizer` | Response Synthesizer | DNA 交叉重組合成 | - | brain | 0.8 |
| `flywheel-coordinator` | Flywheel Coordinator | 飛輪流動協調 | - | brain | 0.9 |
| `primal-detector` | Primal Detector | 八原語偵測 | - | brain | 1.0 |
| `persona-router` | Persona Router | 人格路由 + 百合引擎決策 | - | brain | 1.1 |
| `deep-think` | Deep Think | 思考前置引擎（P0 訊號分流 / P1 輸入審視 / P2 決策偵測） | - | brain | 1.1 |
| `roundtable` | Roundtable | 圓桌詰問引擎（多角色交叉詰問 + 仲裁） | - | brain | 1.0 |
| `investment-masters` | Investment Masters | 投資軍師團（六位大師模型會診） | - | brain | 0.9 |
| `drift-detector` | Drift Detector | 漂移偵測 | - | brain | 0.8 |
| `okr-router` | OKR Router | 八卦路由 | - | brain | 0.9 |
| `fact-correction` | Fact Correction | 事實覆寫引擎 | - | brain | 0.9 |
| `dendritic-fusion` | Dendritic Fusion | P3 並行融合引擎（MetaCog+Eval+Health） | - | brain | 1.1 |
| `chat-context` | Chat Context | ChatContext dataclass（輕量對話上下文資料結構） | - | brain | 0.7 |
| `deterministic-router` | Deterministic Router | 確定性任務分解器（取代 LLM Orchestrator） | - | brain | 1.0 |
| `recommender` | Recommender | 知識推薦引擎（CrystalStore 結晶推薦） | - | brain | 0.9 |
| `dispatcher` | L1 Dispatcher | 調度員：收訊 → 1 秒內 spawn L2 思考者 → 處理下一則（CLAUDE.md 定義行為） | - | brain | 1.2 |
| `thinker` | L2 Thinker | 思考者 subagent：讀 museon-persona.md → 分析決策 → spawn L3 工人（model: sonnet, run_in_background） | - | brain | 1.0 |
| `worker` | L3 Worker | 工人 subagent：執行 MCP 工具呼叫後銷毀（model: haiku, run_in_background） | - | brain | 0.8 |
| ~~`epigenetic-router`~~ | ~~Epigenetic Router~~ | ~~表觀遺傳路由器（已刪除 v1.59）~~ | - | - | - |
| `memory-reflector` | Memory Reflector | Hindsight 式反思引擎（矛盾偵測/模式發現/時間軸/Activation 排序） | - | brain | 1.0 |
| ~~`proactive-predictor`~~ | ~~Proactive Predictor~~ | ~~需求預判引擎（已刪除 v1.59）~~ | - | - | - |
| `adaptive-decay` | Adaptive Decay | ACT-R 式統一衰減引擎（B_i = ln(Σt^{-d}) + β_i） | - | brain | 0.8 |
| `brain-deep` | Brain-Deep (L2) | L2 深度思考引擎（Opus + tool_use） | - | brain | 1.2 |
| `brain-tool-loop` | Brain-Tool-Loop | 獨立 tool-use 迴圈 | - | brain | 1.0 |
| ~~`brain-observer`~~ | ~~Brain-Observer (L4)~~ | ~~L4 觀察者（已刪除 v1.74，功能整合至 L4 觀察者 Nightly Workflow）~~ | - | - | - |
| `l4-cpu-observer` | L4 CPU Observer | CPU-only 對話後觀察者（v12 新增，取代 Haiku L4 agent spawn）。零 LLM 呼叫，<10ms。四步觀察：記憶寫入、訊號更新、偏好偵測、品質調整。 | - | brain | 0.8 |
| `memory-graph` | Memory Graph | 記憶關聯圖（語意關聯邊 + 存取追蹤 + 過期偵測） | - | brain | 1.0 |
| `trait-engine` | Trait Engine | 10 維度特質代謝引擎，從互動計算特質 delta（C-trait 即時更新） | - | brain | 1.0 |
| `growth-stage-computer` | Growth Stage Computer | Kegan 認知成熟度計算（ABSORB→TRANSCEND），取代硬編碼 adult | - | brain | 0.9 |
| `dissent-engine` | Dissent Engine | Crystal Lattice 矛盾偵測，分階段表達異見（Step 3.655） | - | brain | 0.9 |
| `mask-engine` | Mask Engine | 每位使用者臨時人格適應層，附衰減機制（Step 2.2 啟動 / Step 9.9 衰減） | - | brain | 0.9 |
| `momentum-brake` | Momentum Brake | 特質 delta 上限保護 + 捕獲風險偵測 | - | brain | 0.8 |
| `consultant-supplement` | Consultant Supplement | L2 回覆後補充挑戰/提醒，發送獨立 Telegram 訊息。由 server.py 初始化、telegram_pump.py 觸發 | - | brain | 0.8 |

### agent — PDR (Progressive Depth Response) 模組群

| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `pdr-params` | PDR Params | PDR 調控參數 + 安全護欄 | - | brain | 0.9 |
| `pdr-council` | PDR Council | 九策軍師引擎（Phase 2/3） | - | brain | 1.0 |
| `agent-registry` | Agent Registry | 統一能力目錄 | - | brain | 0.7 |

> **依賴關係**：
> - `pdr_params` ← 被 telegram_pump, brain, pdr_council, museqa 讀取
> - `pdr_council` ← 依賴 pdr_params + LLM adapter；被 telegram_pump 呼叫
> - `agent_registry` ← 被 pdr_council 查詢

### pulse — Pulse 生命力
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `pulse` | Pulse Engine | VITA 生命力 | Yes | - | 2.8 |
| `heartbeat` | Heartbeat | 三脈主控 | - | pulse | 1.0 |
| `explorer` | Explorer | 自主探索 | - | pulse | 1.1 |
| `silent-digestion` | Silent Digestion | 靜默消化 | - | pulse | 1.0 |
| `proactive-bridge` | Proactive Bridge | 主動推播 + 百合引擎象限調適 | - | pulse | 1.2 |
| ~~`push-budget`~~ | ~~Push Budget~~ | ~~全局推送預算管理器（限額+語意去重+持久化）~~ | ~~-~~ | ~~pulse~~ | ~~已刪除 v1.72~~ |
| `micro-pulse` | Micro Pulse | 秒級微脈 | - | pulse | 0.8 |
| `pulse-db` | Pulse DB | 脈搏資料庫 | - | pulse | 0.8 |
| `commitment-tracker` | Commitment | 承諾追蹤 | - | pulse | 0.9 |
| `anima-mc-store` | AnimaMC Store | ANIMA統一存取 | - | pulse | 1.1 |
| `anima-tracker` | Anima Tracker | 八元素追蹤 | - | pulse | 1.0 |
| ~~`group-session-proactive`~~ | ~~Group Session Proactive~~ | ~~群組後主動追問（已刪除 v1.59）~~ | - | - | - |
| `anima-changelog` | Anima Changelog | ANIMA_USER 差分版本追蹤（append-only JSONL） | - | pulse | 0.8 |
| `proactive-dispatcher` | Proactive Dispatcher | 推播大總管（統一攔截推播、24hr 日誌、語意去重、分級） | - | pulse | 1.1 |

### gov — Governance
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `governance` | Governance | 三焦式治理 | Yes | - | 2.8 |
| `governor` | Governor | 上中下焦 | - | governance | 1.0 |
| `immunity` | Immunity | 先天 + 後天免疫 | - | governance | 1.1 |
| `preflight` | Preflight | 啟動門 | - | governance | 0.9 |
| `refractory` | Refractory | 斷路器（三態+半開試探） | - | governance | 0.9 |
| `skill-scanner` | Skill Scanner | 技能掃描 | - | governance | 0.8 |
| `sandbox` | Sandbox | 沙盒隔離 | - | governance | 0.8 |
| `telegram-guard` | TG Guard | Polling 守衛 | - | governance | 0.8 |
| `service-health` | Service Health | 服務監控 | - | governance | 1.0 |
| `guardian` | Guardian | 系統守護 Daemon | - | governance | 1.1 |
| `security` | Security | 安全淨化與稽核 | - | governance | 1.0 |
| `dendritic-scorer` | Dendritic Scorer | 樹突評分器 | - | governance | 0.9 |
| `footprint` | Footprint | 操作足跡追蹤 | - | governance | 0.9 |
| `perception` | Perception | 四診合參感知 | - | governance | 0.9 |
| ~~`cognitive-receipt`~~ | ~~Cognitive Receipt~~ | ~~認知收據格式定義（已刪除 v1.59）~~ | - | - | - |
| `authorization` | Authorization | 配對碼 + 工具授權 + 分級策略 | - | governance | 1.0 |
| `response-guard` | Response Guard | 發送前 chat_id 驗證 + 全通道內容黑名單清理（v1.82 取消群組/私訊分流） | - | governance | 0.9 |

### doctor — Doctor 診斷
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `doctor` | Doctor | 自我診斷修復 | Yes | - | 2.8 |
| `system-audit` | System Audit | 7 層 46 項 | - | doctor | 1.1 |
| `health-check` | Health Check | 12 項基礎 | - | doctor | 0.9 |
| `self-diagnosis` | Self Diagnosis | 診斷管線 | - | doctor | 0.9 |
| `auto-repair` | Auto Repair | 自動修復 | - | doctor | 1.0 |
| `surgery` | Surgery | 精準手術 | - | doctor | 0.8 |
| `log-analyzer` | Log Analyzer | 日誌分析 | - | doctor | 0.8 |
| `code-analyzer` | Code Analyzer | 代碼品質 | - | doctor | 0.8 |
| `memory-reset` | Memory Reset | 一鍵記憶重置 | - | doctor | 0.8 |
| `doctor-notify` | Doctor Notify | 五虎將共用通知（DM 老闆 + 待審閱摘要） | - | doctor | 0.7 |
| `observatory` | Observatory | 認知可觀測性儀表板 | - | doctor | 0.8 |
| `shared-board` | Shared Board | 五虎將共享看板（任務協調、50 筆上限滾動） | - | doctor | 0.9 |

### llm — LLM 路由
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `llm-router` | LLM Router | 智能模型選擇 | Yes | - | 2.2 |
| `budget-mgr` | Budget Mgr | Token 預算 | - | llm-router | 1.0 |
| `rate-limit` | Rate Limit | 速限守衛 | - | llm-router | 0.8 |
| `llm-cache` | Cache | LRU 快取 | - | llm-router | 0.8 |
| `semantic-response-cache` | Semantic Response Cache | Qdrant-backed 語意回覆快取，零 LLM token。v12 新增。 | - | llm-router | 0.8 |

### data — 資料持久層
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `data-bus` | DataBus | 資料層路由器 | Yes | - | 1.8 |
| `crystal-store` | CrystalStore | 知識晶體 SQLite (WAL) | - | data-bus | 1.0 |
| `data-watchdog` | DataWatchdog | 資料層監控 | - | data-bus | 1.0 |
| `memory` | Memory | 六層記憶 | - | data-bus | 1.6 |
| `vector-index` | Vector Index | Qdrant 語義 | - | data-bus | 1.5 |
| `pulse-db` | PulseDB | 生命力 SQLite (15 表) | - | data-bus | 1.4 |
| `group-context-db` | GroupContextDB | 群組上下文 SQLite | - | data-bus | 1.0 |
| `workflow-state-db` | WorkflowStateDB | 工作流 SQLite | - | data-bus | 1.0 |
| `wee` | WEE | 演化引擎 | - | data-bus | 1.2 |
| `skills-registry` | Skills Registry | 技能資料庫 | - | data-bus | 1.2 |
| `registry` | Registry | RegistryDB SQLite | - | data-bus | 1.0 |
| `skill-synapse` | Skill Synapse | 突觸網路 | - | data-bus | 0.9 |
| `blueprint-reader` | Blueprint Reader | 藍圖解析器 | - | data-bus | 0.9 |
| `lord-profile` | Lord Profile | 主人領域畫像 | - | data-bus | 0.8 |
| `sparse-embedder` | Sparse Embedder | BM25 稀疏向量（已啟動） | - | data-bus | 0.9 |
| `decision-atlas` | Decision Atlas | 決策圖譜資料節點（data/_system/decision_atlas/da-*.json），提供決策歷史給 brain_prompt_builder 注入 + vision_loop 匯聚 | - | data-bus | 0.8 |

### evolution — Evolution 演化
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `evolution` | Evolution | 演化系統 | Yes | - | 2.2 |
| `outward-trigger` | Outward Trigger | 外向演化觸發 | - | evolution | 1.1 |
| `intention-radar` | Intention Radar | 意圖雷達 | - | evolution | 1.0 |
| `digest-engine` | Digest Engine | 消化結晶引擎 | - | evolution | 1.0 |
| `research-engine` | Research Engine | 外部研究引擎 | - | evolution | 1.1 |
| `evolution-velocity` | Evolution Velocity | 演化速度測量 | - | evolution | 1.0 |
| `feedback-loop` | Feedback Loop | 使用者回饋迴路 | - | evolution | 0.9 |
| `parameter-tuner` | Parameter Tuner | 參數自動調諧 | - | evolution | 0.9 |
| `tool-muscle` | Tool Muscle | 工具肌肉記憶 | - | evolution | 0.8 |
| `trigger-weights` | Trigger Weights | 觸發器權重 | - | evolution | 0.8 |

### tools — Tools 工具套件
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `tool-registry` | Tool Registry | 工具註冊中心 | Yes | - | 1.8 |
| `tool-discovery` | Tool Discovery | 工具自動探測 | - | tool-registry | 1.0 |
| `dify-scheduler` | Dify Scheduler | Dify 排程器 | - | tool-registry | 0.8 |
| `image-gen` | Image Gen | 圖像生成 | - | tool-registry | 0.8 |
| `rss-aggregator` | RSS Aggregator | RSS 聚合器 | - | tool-registry | 0.8 |
| `voice-clone` | Voice Clone | 語音克隆 | - | tool-registry | 0.7 |
| `zotero-bridge` | Zotero Bridge | 文獻管理橋接 | - | tool-registry | 0.8 |
| `mcp-dify` | MCP Dify | MCP-Dify 連接器 | - | tool-registry | 0.7 |

### nightly — Nightly 夜間
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `nightly` | Nightly Pipeline | 31+ 步夜間整合 | Yes | - | 2.2 |
| `morphenix` | Morphenix | 演化提案 | - | nightly | 1.0 |
| `curiosity-router` | Curiosity Router | 好奇心路由 | - | nightly | 0.9 |
| `exploration-bridge` | Exploration Bridge | 探索橋接 | - | nightly | 0.9 |
| `skill-forge-scout` | Skill Forge Scout | 技能鍛造偵察 | - | nightly | 0.8 |
| `crystal-actuator` | Crystal Actuator | 結晶致動器 | - | nightly | 0.8 |
| `periodic-cycles` | Periodic Cycles | 週期循環 | - | nightly | 0.9 |
| `morphenix-validator` | Morphenix Validator | Docker 沙盒驗證 | - | nightly | 0.7 |
| `context-cache-builder` | Context Cache Builder | Step 31 context_cache 重建 | - | nightly | 0.8 |
| `nightly-reflection-engine` | Nightly Reflection Engine | LLM 自我反思引擎，驅動 P-trait 演化（Steps 34 / 34.5 / 34.7） | - | nightly | 1.0 |
| `breath-analyzer` | Breath Analyzer | 呼吸系統 Day 3-4 CPU 級五層分析（Step 34.8）。讀取 breath/observations/*.jsonl，寫入 breath/patterns/*.json | - | nightly | 0.8 |
| `vision-loop` | Vision Loop | 週日願景迴圈，匯聚四信號源生成方向提案（Step 34.9）。讀取 constellations/registry.json + skill_health/latest.json + decision_atlas/da-*.json + breath/patterns/*.json，寫入 breath/visions/*.json | - | nightly | 0.9 |
| `gap-accumulator` | Gap Accumulator | 能力缺口偵測與累積（三軌道 A/B/C）——A: 對話 Skill 未觸發的低分請求，B: skill_router._match_score 弱匹配偵測，C: Nightly 宏觀分析；聚合寫入 Qdrant gaps collection + morphenix/notes/ + skill_requests/ | - | nightly | 0.9 |

### learning — Learning 學習
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `insight-extractor` | Insight Extractor | 洞見萃取引擎（晨報+探索統一萃取） | Yes | - | 1.2 |
| ~~`strategy-accumulator`~~ | ~~Strategy Accumulator~~ | ~~策略成熟度累積器（已刪除 v1.59，功能由 insight-extractor 整合）~~ | - | - | - |

### billing — Billing 計費
| ID | 名稱 | 中文 | Hub | 半徑 |
|----|------|------|-----|------|
| `skill-counter` | Skill Counter | Skill 調用計數器（月度檔案） | Yes | 1.0 |

### external — 外部服務
| ID | 名稱 | 中文 | Hub | 半徑 |
|----|------|------|-----|------|
| `searxng` | SearXNG | 搜尋 :8888 | - | 1.0 |
| `qdrant` | Qdrant | 向量 DB :6333 | - | 1.0 |
| `firecrawl` | Firecrawl | 爬取 :3002 | - | 0.8 |
| `anthropic-api` | Anthropic API | Claude API | - | 1.1 |
| `playwright-mcp` | Playwright MCP | 瀏覽器自動化（MCP） | - | 0.5 |
| `fetch-mcp` | Fetch MCP | 網頁讀取（MCP） | - | 0.5 |

### skills — Skills 生態系

> **治理文件**：`docs/skill-routing-governance.md`（Hub 路由 + Always-on 中間件 + Workflow Stage 規格）
> **Manifest 規格**：`docs/skill-manifest-spec.md`（YAML frontmatter 欄位定義 + 驗證規則）

#### skills-thinking — 思維類
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `skills-thinking-hub` | Thinking Hub | 思維類技能中樞 | Yes | - | 2.0 |
| `dharma` | DHARMA | 思維轉化引擎 | - | skills-thinking-hub | 1.2 |
| `philo-dialectic` | Philo-Dialectic | 哲學思辨引擎 | - | skills-thinking-hub | 1.2 |
| `resonance` | Resonance | 感性共振引擎 | - | skills-thinking-hub | 1.2 |
| `shadow` | Shadow | 人際博弈辨識引擎 | - | skills-thinking-hub | 1.2 |
| `meta-learning` | Meta-Learning | 元學習引擎 | - | skills-thinking-hub | 1.2 |
| `query-clarity` | Query-Clarity | 問題品質守門層 | - | skills-thinking-hub | 1.2 |
| `user-model` | User-Model | 使用者畫像引擎 | - | skills-thinking-hub | 1.2 |
| `energy-reading` | Energy-Reading | 八方位能量解讀 | - | skills-thinking-hub | 1.2 |
| `wan-miu-16` | Wan-Miu-16 | 萬謬16型人格 | - | skills-thinking-hub | 1.2 |
| `combined-reading` | Combined-Reading | 合盤能量比對 | - | skills-thinking-hub | 1.2 |
| `anima-individual` | Anima-Individual | ANIMA 個體追蹤引擎 | - | skills-thinking-hub | 1.2 |
| `ares` | Ares | 戰神系統工作流 | - | skills-thinking-hub | 1.4 |
| `shadow-muse` | Shadow-Muse | 戰略覺察挑戰教練 | - | skills-thinking-hub | 1.2 |
| `daily-pilot` | Daily-Pilot | 每日導航引擎 | - | skills-thinking-hub | 1.2 |
| `talent-match` | Talent-Match | 智慧人才媒合引擎 | - | skills-thinking-hub | 1.2 |

#### skills-market — 市場類
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `skills-market-hub` | Market Hub | 市場類技能中樞 | Yes | - | 2.0 |
| `market-core` | Market-Core | 市場分析核心 | - | skills-market-hub | 1.4 |
| `market-equity` | Market-Equity | 股票分析衛星 | - | skills-market-hub | 1.2 |
| `market-crypto` | Market-Crypto | 加密貨幣分析 | - | skills-market-hub | 1.2 |
| `market-macro` | Market-Macro | 總體經濟分析 | - | skills-market-hub | 1.2 |
| `risk-matrix` | Risk-Matrix | 風險管理引擎 | - | skills-market-hub | 1.2 |
| `sentiment-radar` | Sentiment-Radar | 市場情緒雷達 | - | skills-market-hub | 1.2 |

#### skills-business — 商業類
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `skills-business-hub` | Business Hub | 商業類技能中樞 | Yes | - | 2.0 |
| `business-12` | Business-12 | 商模十二力 | - | skills-business-hub | 1.2 |
| `ssa-consultant` | SSA-Consultant | 顧問式銷售引擎 | - | skills-business-hub | 1.2 |
| `master-strategy` | Master-Strategy | 戰略判斷引擎 | - | skills-business-hub | 1.4 |
| `consultant-communication` | Consultant-Comm | 顧問溝通引擎 | - | skills-business-hub | 1.2 |
| `xmodel` | X-Model | 破框解方引擎 | - | skills-business-hub | 1.2 |
| `pdeif` | PDEIF | 逆熵流引擎 | - | skills-business-hub | 1.2 |

#### skills-creative — 創意類
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `skills-creative-hub` | Creative Hub | 創意類技能中樞 | Yes | - | 2.0 |
| `c15` | C15 | 敘事張力語言層 | - | skills-creative-hub | 1.2 |
| `text-alchemy` | Text-Alchemy | 文字煉金系統 | - | skills-creative-hub | 1.2 |
| `storytelling-engine` | Storytelling | 說故事引擎 | - | skills-creative-hub | 1.2 |
| `novel-craft` | Novel-Craft | 小說工藝引擎 | - | skills-creative-hub | 1.2 |
| `aesthetic-sense` | Aesthetic-Sense | 美感引擎 | - | skills-creative-hub | 1.2 |
| `brand-identity` | Brand-Identity | 品牌識別引擎 | - | skills-creative-hub | 1.2 |
| `human-design-blueprint` | HD-Blueprint | 人類圖靈魂藍圖 | - | skills-creative-hub | 1.2 |
| `video-strategy` | Video-Strategy | 短影音策略引擎 | - | skills-creative-hub | 1.2 |
| `course-forge` | Course-Forge | 講師課程建構引擎 | - | skills-creative-hub | 1.2 |

#### skills-business — 商業類（補充）
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `esg-architect-pro` | ESG-Architect-Pro | ESG 永續報告鍛造 | - | skills-business-hub | 1.2 |
| `meeting-intelligence` | Meeting-Intel | 會議情報分析 | - | skills-business-hub | 1.2 |
| `brand-discovery` | Brand-Discovery | 漸進式品牌訪談引擎 | - | skills-business-hub | 1.2 |
| `brand-builder` | Brand-Builder | 奧美級品牌建構引擎 | - | skills-business-hub | 1.4 |
| `biz-diagnostic` | Biz-Diagnostic | 商業模式健檢引擎 | - | skills-business-hub | 1.2 |
| `ad-pilot` | Ad-Pilot | 付費廣告成效診斷引擎 | - | skills-business-hub | 1.2 |
| `equity-architect` | Equity-Architect | 合夥股權架構引擎 | - | skills-business-hub | 1.2 |
| `biz-collab` | Biz-Collab | 異業合作媒合引擎 | - | skills-business-hub | 1.2 |

#### skills-product — 產品類
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `skills-product-hub` | Product Hub | 產品類技能中樞 | Yes | - | 2.0 |
| `acsf` | ACSF | 能力結晶鑄造 | - | skills-product-hub | 1.2 |
| `dse` | DSE | 技術融合驗證 | - | skills-product-hub | 1.2 |
| `gap` | GAP | 缺口分析引擎 | - | skills-product-hub | 1.2 |
| `env-radar` | Env-Radar | 環境雷達 | - | skills-product-hub | 1.2 |
| `info-architect` | Info-Architect | 資訊架構引擎 | - | skills-product-hub | 1.2 |
| `report-forge` | Report-Forge | 報告鍛造 | - | skills-product-hub | 1.2 |
| `orchestrator` | Orchestrator | 編排引擎 | - | skills-product-hub | 1.2 |
| `brand-project-engine` | Brand-Project-Engine | 品牌行銷專案引擎 | - | skills-product-hub | 1.2 |
| `finance-pilot` | Finance-Pilot | 財務導航引擎 | - | skills-product-hub | 1.2 |

#### skills-evolution — 演化類
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `skills-evolution-hub` | Evolution Hub | 演化類技能中樞 | Yes | - | 2.0 |
| `sandbox-lab` | Sandbox-Lab | 沙盒實驗室 | - | skills-evolution-hub | 1.2 |
| `qa-auditor` | QA-Auditor | 品質審計引擎 | - | skills-evolution-hub | 1.2 |
| `tantra` | Tantra | 情慾治理引擎 | - | skills-evolution-hub | 1.0 |
| `system-health-check` | System-Health-Check | 系統健康自檢引擎 | - | skills-evolution-hub | 1.0 |
| `decision-tracker` | Decision-Tracker | 決策歷史追蹤引擎 | - | skills-evolution-hub | 1.0 |
| `prompt-stresstest` | Prompt-StressTest | Prompt壓力測試引擎 | - | skills-evolution-hub | 1.2 |

#### skills-workflow — 工作流類
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `skills-workflow-hub` | Workflow Hub | 工作流類技能中樞 | Yes | - | 2.0 |
| `workflow-svc-brand-marketing` | WF-SVC-01 | 品牌行銷工作流 | - | skills-workflow-hub | 1.2 |
| `workflow-investment-analysis` | WF-INV-01 | 投資分析工作流 | - | skills-workflow-hub | 1.2 |
| `workflow-ai-deployment` | WF-AID-01 | AI部署工作流 | - | skills-workflow-hub | 1.2 |
| `workflow-brand-consulting` | WF-BRD-01 | 品牌手冊工作流 | - | skills-workflow-hub | 1.4 |
| `group-meeting-notes` | WF-GMN-01 | 會議記錄引擎 | - | skills-workflow-hub | 1.2 |

### constellation — 星座系統

> **設計文件**：`~/.claude/projects/-Users-ZEALCHOU/memory/project_constellation_system.md`
> **核心邏輯**：荒謬六芒星是底層 OS（補上六大決策盲區），8 個領域星座映射回荒謬，星座雷達引擎追蹤使用者在各星座的位置，探針層負責觸發診斷。
> **色碼**：`#9B59B6`（紫色系，與其他群組一眼可辨）

| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `constellation-radar` | Constellation Radar | 星座雷達引擎（追蹤各星座活躍度、缺口引力） | Yes | - | 2.0 |
| `constellation-probe` | Constellation Probe | 探針層（觸發診斷、注入 Brain Prompt） | - | constellation-radar | 1.4 |
| `constellation-absurdity` | 荒謬六芒星 | 底層 OS——補上六大決策盲區（存在/虛假/資訊/時間/框架/自我） | - | constellation-radar | 1.6 |
| `constellation-business` | 商模十二力星 | 商業模式十二力領域星座 | - | constellation-radar | 1.2 |
| `constellation-brand` | 品牌七芒星 | 品牌建構七芒領域星座 | - | constellation-radar | 1.2 |
| `constellation-strategy` | 戰略三稜鏡 | 戰略判斷三稜鏡領域星座 | - | constellation-radar | 1.2 |
| `constellation-energy` | 能量八芒星 | 八方位能量領域星座 | - | constellation-radar | 1.2 |
| `constellation-conversion` | 轉化漏斗三角星 | 轉化漏斗三角領域星座 | - | constellation-radar | 1.2 |
| `constellation-market` | 市場七芒星 | 市場分析七芒領域星座 | - | constellation-radar | 1.2 |
| `constellation-thinking` | 思維轉化五芒星 | 思維轉化五芒領域星座 | - | constellation-radar | 1.2 |
| `constellation-growth` | 年輪星 | 年度成長週期領域星座 | - | constellation-radar | 1.2 |

---

## 連線清單（Links）

### 連線類型定義

| 類型 | 說明 | 色碼 |
|------|------|------|
| `flow` | 資料流（使用者指令流經的路徑） | `#E0714D` |
| `control` | 控制流（事件分派、排程觸發） | `#7A7888` |
| `internal` | 群組內部連線（Hub ↔ 子節點） | `#9898A8` |
| `cross` | 跨群組連線（系統間協作） | `#C4502A` |
| `async` | 非同步連線（推播、回饋） | `#B8923A` |
| `monitor` | 監控連線（健康檢查） | `#2A6A8A` |
| `decay` | 衰減連線（資料老化、優先級退場） | `#8B6E5A` |

### 衰減連線（decay）

> 橫切關注點：四個模組各自實作衰減邏輯，影響資料的「老化退場」。
> 詳細公式與參數見 `persistence-contract.md` §衰減與優先級模型。

| Source | Target | 說明 |
|--------|--------|------|
| `knowledge-lattice` → `crystal-actuator` | `crystal.db` (via CrystalStore) | RI 指數衰減 `exp(-0.03×days)`，RI<0.05 由 crystal-actuator 執行歸檔 |
| `memory` → `vector-index` | Qdrant memories | TTL 分級（24h/14d/90d）+ 訪問次數晉升/降級 + supersede 事實覆寫 |
| `dendritic-scorer` → `pulse-db` | health_scores 表 | 半衰期 2h 指數衰減，governor 每回合 tick() |
| `recommender` → `knowledge-lattice` | 推薦排序 | 近因性半衰期 7d + 互動衰減 λ=0.95 |
| `nightly` → `skill-synapse` | synapses.json | Synapse Decay（已有連線） |

### 主資料流（flow）
| Source | Target | 說明 |
|--------|--------|------|
| `zeal` | `telegram` | 私聊指令 + 群組 @mention（CORE trust, is_owner=True） |
| `zeal` | `line` | LINE 私聊 + 群組（CORE trust） |
| `verified-user` | `telegram` | 動態配對使用者私聊（VERIFIED trust, PairingManager） |
| `external-user` | `telegram` | 群組對話（EXTERNAL trust, SensitivityChecker 過濾） |
| `external-user` | `line` | LINE 群組對話（EXTERNAL trust） |
| `external-user` | `discord` | Discord 群組對話（EXTERNAL trust） |
| `telegram` | `gateway` | 轉發（InternalMessage + metadata: is_group, is_owner, sender_name） |
| `line` | `gateway` | webhook 轉發 |
| `discord` | `gateway` | 轉發 |
| `gateway` | `event-bus` | 路由 |
| `cron` | `event-bus` | 定時觸發 |

### 控制流（control）
| Source | Target | 說明 |
|--------|--------|------|
| `event-bus` | `brain` | 事件分派 |
| `event-bus` | `pulse` | 脈搏事件 |
| `event-bus` | `governance` | 治理事件 |
| `event-bus` | `doctor` | 診斷事件 |
| `event-bus` | `llm-router` | LLM 事件 |
| `event-bus` | `data-bus` | 資料事件 |
| `event-bus` | `evolution` | 演化事件 |
| `event-bus` | `tool-registry` | 工具事件 |
| `cron` | `nightly` | 03:00 觸發 |

### Agent 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `brain` | `brain-prompt-builder` | Mixin: system prompt 建構 |
| `brain-prompt-builder` | `anima-mc-store` | 讀取 ANIMA_MC（身份/能力/演化/八原語） |
| `brain-prompt-builder` | `data-bus` | 讀取 PULSE.md + fact_corrections + 記憶注入 |
| `brain-prompt-builder` | `anthropic-api` | 結晶壓縮時的 LLM 呼叫（via knowledge_lattice） |
| `brain` | `brain-dispatch` | Mixin: 任務分派 |
| `brain` | `brain-observation` | Mixin: 觀察與演化 |
| `brain` | `brain-tools` | Mixin: LLM 呼叫與 session 管理 |
| `brain-tools` | `anthropic-api` | LLM 呼叫（Fallback 鏈：Opus→Sonnet→Haiku→離線） |
| `brain-tools` | `data-bus` | Session 持久化 + cache/routing/skill_usage JSONL |
| `brain` | `brain-types` | 共享型別: DecisionSignal, P3FusionSignal |
| ~~`brain`~~ | ~~`dna27`~~ | ~~載入反射（dna27 已刪除 v1.59）~~ |
| `brain` | `skill-router` | 技能路由 |
| `brain` | `signal-lite` | signal_lite 信號路由（取代 DNA27 反射路由器） |
| `brain` | `dispatch` | 多技能分派 |
| `brain` | `knowledge-lattice` | 結晶注入 |
| `brain` | `knowledge-lattice` | MemGPT 三層分級召回 recall_tiered() |
| `brain` | `knowledge-lattice` | GraphRAG 社群摘要 Layer 2.5 recall_with_community() |
| `brain` | `plan-engine` | 計畫啟動 |
| `brain` | `metacognition` | 元認知 |
| `brain` | `intuition` | 直覺感知 |
| `brain` | `eval-engine` | 品質評分 |
| `brain` | `diary-store` | 日記記錄 |
| `brain` | `onboarding` | 上線儀式 |
| `brain` | `multiagent` | 多代理協調 |
| `brain` | `multi-agent-executor` | 並行 LLM 呼叫 |
| `brain` | `response-synthesizer` | 回覆合成 |
| `brain` | `flywheel-coordinator` | 飛輪流動 |
| `brain` | `primal-detector` | 八原語偵測 |
| `brain` | `persona-router` | 人格路由 |
| `brain` | `deep-think` | 思考前置 P0/P1/P2 |
| `brain` | `roundtable` | 圓桌詰問 |
| `brain` | `investment-masters` | 軍師會診 |
| `brain` | `drift-detector` | 漂移檢查 |
| `brain` | `okr-router` | 八卦路由 |
| `brain` | `fact-correction` | 事實更正偵測+覆寫 |
| `brain` | `dendritic-fusion` | P3 前置融合（Step 5.5）+ 並行融合（Step 6.2-6.5） |
| `brain` | `recommender` | 知識推薦引擎 |
| `brain` | `chat-context` | 對話上下文封裝 |
| `brain` | `deterministic-router` | 確定性任務分解（取代 LLM Orchestrator） |
| `brain` | `brain-deep` | L1 escalation 委派（複雜訊息→L2 Opus 深度思考） |
| `brain-deep` | `brain-tool-loop` | tool-use 迴圈（L2 需要工具時委派） |
| `brain-tool-loop` | `tool-executor` | 工具執行（MCP 工具呼叫） |
| `dendritic-fusion` | `metacognition` | 並行預認知審查 |
| `dendritic-fusion` | `eval-engine` | 並行品質評分 |
| `multi-agent-executor` | `llm-router` | 多部門 API 呼叫 |
| `dispatcher` | `thinker` | L1→L2：收訊後 spawn 思考者（run_in_background, model: sonnet） |
| `thinker` | `worker` | L2→L3：思考完成後 spawn 工人執行 MCP 工具（run_in_background, model: haiku） |
| `worker` | `telegram` | L3 透過 MCP 工具回覆 Telegram 訊息 |
| `worker` | `gmail` | L3 透過 MCP 工具收發 Email |
| `worker` | `gcal` | L3 透過 MCP 工具管理行程 |
| `thinker` | `worker` | L2→L3（前景）：需要查詢結果時同步等待 L3 回傳資料 |
| `brain` | `dissent-engine` | Step 3.655 矛盾偵測呼叫 |
| `brain` | `mask-engine` | Step 2.2 啟動臨時人格層 / Step 9.9 衰減 |
| `brain` | `agent-registry` | Brain 初始化時載入能力目錄 |
| `brain` | `pdr-params` | PDR 調控參數載入/保存 |
| `brain` | `pdr-council` | 謀定而後動引擎（Phase 2/3 審查） |
| `pdr-council` | `agent-registry` | 查詢可用能力目標（action targets） |
| `pdr-council` | `pdr-params` | 讀取 Phase 2/3 參數 + 安全護欄 |
| `brain` | `absurdity-radar` | load_radar（每請求讀取）→ update_radar_from_skill + save_radar（命中後更新） |
| `brain-prompt-builder` | `absurdity-radar` | _build_absurdity_radar_context() 讀取六維雷達注入 persona zone |
| `brain` | `l4-cpu-observer` | 回覆後呼叫 L4CpuObserver.observe()，CPU-only，<10ms |
| `l4-cpu-observer` | `context-cache` | signal_cache JSON 寫入（訊號更新） |
| `l4-cpu-observer` | `session-adjustments` | 品質調整寫入（規則引擎輸出） |
| `l4-cpu-observer` | `memory` | 記憶寫入（訊息 > 20 字 + 非問候時觸發，optional） |
| `brain` | `semantic-response-cache` | L1 查詢快取，命中則跳過 L2 |
| `l4-cpu-observer` | `semantic-response-cache` | 回覆後寫入快取 |
| `semantic-response-cache` | `qdrant` | semantic_response_cache collection 讀寫 |

### Pulse 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `pulse` | `heartbeat` | 三脈 |
| `pulse` | `explorer` | 探索 |
| `pulse` | `silent-digestion` | 消化 |
| `pulse` | `proactive-bridge` | 推播 |
| `pulse` | `micro-pulse` | 微脈 |
| `pulse` | `pulse-db` | 持久化 |
| `pulse` | `commitment-tracker` | 承諾 |
| `pulse` | `anima-mc-store` | ANIMA 統一存取 |
| `pulse` | `anima-tracker` | 八元素追蹤 |
| `anima-tracker` | `anima-mc-store` | 八元素經由 Store |
| `micro-pulse` | `anima-mc-store` | 微脈經由 Store |
| ~~`pulse`~~ | ~~`group-session-proactive`~~ | ~~群組追問（已刪除 v1.59）~~ |
| ~~`pulse-engine`~~ | ~~`push-budget`~~ | ~~推送預算檢查+記錄~~ ← 已刪除 v1.72 |
| ~~`proactive-bridge`~~ | ~~`push-budget`~~ | ~~推送預算檢查+記錄~~ ← 已刪除 v1.72 |
| ~~`push-budget`~~ | ~~`pulse-db`~~ | ~~push_log 表持久化~~ ← 已刪除 v1.72 |
| `pulse` | `proactive-dispatcher` | 推播大總管 |

### Learning 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| ~~`insight-extractor`~~ | ~~`strategy-accumulator`~~ | ~~洞見成熟度升級（strategy-accumulator 已刪除 v1.59）~~ |

### Doctor — shared-board 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `doctor` | `shared-board` | 看板存取 |

### Governance 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `governance` | `governor` | 三焦 |
| `governance` | `immunity` | 免疫 |
| `governance` | `preflight` | 啟動門 |
| `governance` | `refractory` | 斷路 |
| `governance` | `skill-scanner` | 掃描 |
| `governance` | `sandbox` | 沙盒 |
| `governance` | `telegram-guard` | 守衛 |
| `governance` | `service-health` | 監控 |
| `governance` | `guardian` | 守護 |
| `governance` | `security` | 安全 |
| `governance` | `dendritic-scorer` | 評分 |
| `governance` | `footprint` | 足跡 |
| `governance` | `perception` | 感知 |
| ~~`governance`~~ | ~~`cognitive-receipt`~~ | ~~認知收據（已刪除 v1.59）~~ |
| ~~`footprint`~~ | ~~`cognitive-receipt`~~ | ~~認知追蹤格式定義（已刪除 v1.59）~~ |
| `governor` | `immunity` | learn() 抗體學習 |
| `governor` | `dendritic-scorer` | immunity 未解決→健康分數 |
| `governance` | `authorization` | 授權引擎 |
| `authorization` | `security` | 三級策略查詢 |
| `governance` | `response-guard` | 發送前 chat_id 驗證閘門 |

### Evolution 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `evolution` | `outward-trigger` | 外向觸發 |
| `evolution` | `intention-radar` | 意圖偵測 |
| `evolution` | `digest-engine` | 消化結晶 |
| `evolution` | `research-engine` | 外部研究 |
| `evolution` | `evolution-velocity` | 速度測量 |
| `evolution` | `feedback-loop` | 回饋迴路 |
| `evolution` | `parameter-tuner` | 參數調諧 |
| `evolution` | `tool-muscle` | 肌肉記憶 |
| `evolution` | `trigger-weights` | 觸發權重 |

### Tools 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `tool-registry` | `tool-discovery` | 工具探測 |
| `tool-registry` | `dify-scheduler` | Dify 排程 |
| `tool-registry` | `image-gen` | 圖像生成 |
| `tool-registry` | `rss-aggregator` | RSS 聚合 |
| `tool-registry` | `voice-clone` | 語音克隆 |
| `tool-registry` | `zotero-bridge` | 文獻管理 |
| `tool-registry` | `mcp-dify` | MCP-Dify |

### Doctor 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `doctor` | `system-audit` | 審計 |
| `doctor` | `health-check` | 檢查 |
| `doctor` | `self-diagnosis` | 診斷 |
| `doctor` | `auto-repair` | 修復 |
| `doctor` | `surgery` | 手術 |
| `doctor` | `log-analyzer` | 日誌 |
| `doctor` | `code-analyzer` | 代碼 |
| `doctor` | `memory-reset` | 重置 |
| `doctor` | `observatory` | 認知儀表板 |

### LLM 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `llm-router` | `budget-mgr` | 預算 |
| `llm-router` | `rate-limit` | 速限 |
| `llm-router` | `llm-cache` | 快取 |

### Data 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `data-bus` | `memory` | Store 路由 |
| `data-bus` | `vector-index` | Store 路由 |
| `data-bus` | `wee` | Store 路由 |
| `data-bus` | `skills-registry` | Store 路由 |
| `data-bus` | `registry` | Store 路由 |
| `data-bus` | `skill-synapse` | Store 路由 |
| `data-bus` | `blueprint-reader` | Store 路由 |
| `data-bus` | `sparse-embedder` | Store 路由 |
| `vector-index` | `sparse-embedder` | 混合檢索 BM25+Dense RRF 融合 |
| `data-bus` | `crystal-store` | Store 路由 |
| `data-bus` | `data-watchdog` | 監控注入 |
| `data-bus` | `pulse-db` | Store 路由 |
| `data-bus` | `group-context-db` | Store 路由 |
| `data-bus` | `workflow-state-db` | Store 路由 |
| `wee` | `skill-synapse` | 突觸演化 |
| `data-bus` | `lord-profile` | Store 路由 |
| `skills-registry` | `registry` | 技能資料表 |

### Nightly 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `nightly` | `morphenix` | 演化提案 |
| `nightly` | `curiosity-router` | 好奇心路由 |
| `nightly` | `exploration-bridge` | 探索橋接 |
| `nightly` | `skill-forge-scout` | 技能鍛造 |
| `nightly` | `crystal-actuator` | 結晶致動 |
| `nightly` | `periodic-cycles` | 週期循環 |
| `nightly` | `morphenix-validator` | Docker 沙盒驗證 |
| `nightly` | `context-cache-builder` | Step 31 context_cache 重建 |
| `morphenix-validator` | `morphenix` | 驗證通過→執行 |
| `nightly-pipeline` | `nightly-reflection-engine` | Steps 34 / 34.5 / 34.7 P-trait 演化反思 |
| `nightly-pipeline` | `absurdity-radar` | Step 32.5 _step_absurdity_radar_recalc 重算六維雷達 |
| `nightly-pipeline` | `breath-analyzer` | Step 34.8 呼吸五層分析（Day 3-4 CPU-only） |
| `nightly-pipeline` | `vision-loop` | Step 34.9 週日願景迴圈（週日執行） |

### 跨系統連線（cross）
| Source | Target | 說明 |
|--------|--------|------|
| `primal-detector` | `vector-index` | 八原語語義匹配 |
| `primal-detector` | `skill-router` | 原語加分 |
| `primal-detector` | `persona-router` | 原語調適 |
| `primal-detector` | `okr-router` | 原語路由 |
| `persona-router` | `proactive-bridge` | 象限決策結果回饋（P1-P3） |
| `deep-think` | `metacognition` | Phase 0 元認知觀察 |
| `deep-think` | `persona-router` | Phase 0 訊號分流→百合引擎 |
| `roundtable` | `knowledge-lattice` | 裁決軌跡結晶 |
| `investment-masters` | `knowledge-lattice` | 軍師會診結晶 |
| `investment-masters` | `skill-router` | DNA27 RC 親和觸發 |
| ~~`drift-detector`~~ | ~~`memory`~~ | ~~覺察日誌~~ ❌ **幽靈連線 v1.43 移除**：drift_detector.py 零 cross import，純 dataclass 邏輯 |
| `fact-correction` | `memory` | 記憶覆寫（supersede） |
| `fact-correction` | `vector-index` | 向量廢棄標記（mark_deprecated） |
| `fact-correction` | `llm-router` | Haiku 矛盾判斷 |
| `skill-router` | `vector-index` | 語義匹配 |
| `skill-router` | `skills-registry` | 技能查找 |
| `skill-router` | `llm-router` | API 呼叫 |
| `dispatch` | `llm-router` | API 呼叫 |
| `knowledge-lattice` | `vector-index` | 結晶存取 |
| `metacognition` | `llm-router` | Haiku 審查 |
| `eval-engine` | `memory` | 品質數據 |
| `eval-engine` | `registry` | Q-Score 存取 |
| `dendritic-fusion` | `dendritic-scorer` | P3 並行融合讀取健康分數 |
| `recommender` | `knowledge-lattice` | 近因性衰減 7d + 互動衰減 λ=0.95 |
| `recommender` | `crystal-store` | 結晶讀取（load_crystals_raw + load_links） |
| `diary-store` | `memory` | 日記寫入 |
| `brain-deep` | `anthropic-api` | LLM 呼叫 Opus（L2 深度思考） |
| `brain-tool-loop` | `anthropic-api` | LLM 呼叫（tool-use 迴圈） |
| `brain` | `llm-router` | 生成回應 |
| `brain` | `memory` | 四通道持久化 |
| `commitment-tracker` | `brain` | 承諾自檢 |
| `commitment-tracker` | `registry` | 承諾記錄 |
| `explorer` | `searxng` | 網路搜尋 |
| `explorer` | `llm-router` | 深度分析 |
| `explorer` | `firecrawl` | 頁面爬取 |
| `mcp-server` | `playwright-mcp` | 瀏覽器自動化（截圖/填表/點擊） |
| `mcp-server` | `fetch-mcp` | 網頁純文字讀取 |
| `silent-digestion` | `memory` | 反思寫入 |
| `skill-scanner` | `skills-registry` | 安全掃描 |
| `auto-repair` | `gateway` | 重啟修復 |
| `system-audit` | `service-health` | 交叉驗證 |
| `llm-router` | `anthropic-api` | API 呼叫 |
| `memory` | `vector-index` | 嵌入索引 |
| `memory` | `registry` | 持久化儲存 |
| `vector-index` | `qdrant` | 向量存儲（dense） |
| `sparse-embedder` | `qdrant` | 稀疏向量存儲（sparse collections） |
| `skill-router` | `sparse-embedder` | 混合檢索（hybrid_search） |
| `memory` | `sparse-embedder` | 記憶混合檢索（hybrid_search） |
| `wee` | `skills-registry` | 演化追蹤 |
| `wee` | `registry` | 演化狀態 |
| `pulse-db` | `registry` | 脈搏記錄 |
| `nightly` | `memory` | 記憶壓縮 |
| `nightly` | `skills-registry` | 品質檢查 |
| `nightly` | `wee` | 演化速度 |
| `nightly` | `knowledge-lattice` | 結晶固化 |
| `nightly` | `budget-mgr` | 預算結算 |
| `nightly` | `immunity` | 抗體修剪 |
| `nightly` | `skill-synapse` | Synapse Decay |
| `nightly` | `data-watchdog` | Step 29 健康檢查 |
| `nightly` | `blueprint-reader` | Step 30 藍圖一致性驗證 |
| `blueprint-reader` | `doctor` | 藍圖感知（系統審計） |
| `blueprint-reader` | `surgery` | 藍圖感知（精準手術） |
| `blueprint-reader` | `morphenix` | 藍圖感知（演化提案） |
| `governor` | `pulse-db` | 事件記錄 |
| ~~`group-session-proactive`~~ | ~~`telegram`~~ | ~~群組追問發送（已刪除 v1.59）~~ |
| `data-bus` | `pulse-db` | Store 路由 |
| `data-bus` | `knowledge-lattice` | Store 路由 |
| `data-bus` | `diary-store` | Store 路由 |
| `data-bus` | `eval-engine` | Store 路由 |
| `outward-trigger` | `intention-radar` | 觸發搜尋 |
| `intention-radar` | `research-engine` | 執行研究 |
| `research-engine` | `digest-engine` | 消化結果 |
| `digest-engine` | `knowledge-lattice` | 結晶寫入 |
| `evolution-velocity` | `parameter-tuner` | 速度驅動調諧 |
| `nightly` | `evolution-velocity` | 夜間速度計算 |
| `nightly` | `diary-store` | 每日日記生成 |
| ~~`group-session-proactive`~~ | ~~`event-bus`~~ | ~~GROUP_SESSION_END 訂閱（已刪除 v1.59）~~ |
| `telegram` | `event-bus` | GROUP_SESSION_END 發布 |
| `nightly` | `parameter-tuner` | 夜間參數調諧 |
| `guardian` | `doctor` | 修復委派 |
| `guardian` | `brain` | ANIMA 修復 |
| `onboarding` | `brain` | 初始化身份 |
| `tool-registry` | `skill-router` | 工具查找 |
| `mcp-server` | `brain` | ANIMA 狀態查詢 |
| `brain` | `anima-mc-store` | ANIMA_MC 存取 |
| `gateway` | `anima-mc-store` | API 查詢 ANIMA |
| `dendritic-scorer` | `eval-engine` | 品質評分 |
| `footprint` | `data-bus` | 足跡持久化 |
| `perception` | `brain` | 四診合參 |
| `curiosity-router` | `pulse` | 探索主題 |
| `exploration-bridge` | `skill-forge-scout` | 技能線索 |
| `crystal-actuator` | `crystal-store` | 結晶降級/升級（經由 CrystalStore API） |
| `crystal-actuator` | `knowledge-lattice` | 結晶操作 |
| `knowledge-lattice` | `crystal-store` | 結晶讀寫（經由 CrystalStore API） |
| `nightly` | `crystal-store` | 結晶統計（經由 CrystalStore API） |
| `evolution-velocity` | `crystal-store` | 結晶數量統計 |
| `guardian` | `crystal-store` | 結晶健康檢查 |
| `memory-reset` | `crystal-store` | 一鍵重置（DELETE FROM 三表） |
| `periodic-cycles` | `pulse` | 週期驅動 |
| ~~`zotero-bridge`~~ | ~~`vector-index`~~ | ~~文獻索引~~ ❌ **幽靈連線 v1.43 移除**：zotero_bridge.py 只 import event_bus，無 vector 連線 |
| `metacognition` | `pulse-db` | DNA 品質旗標寫入（METACOGNITION_QUALITY_FLAG） |
| `morphenix` | `pulse-db` | DNA 品質旗標讀取（品質回饋閉環） |
| `response-synthesizer` | `multi-agent-executor` | DNA 交叉重組（片段評分合成） |
| `brain` | `footprint` | Step 8 認知追蹤（trace_decision+trace_cognitive） |
| `brain` | `data-bus` | 經驗回放搜尋（activity_log.search() via ActivityLogger） |
| `authorization` | `telegram` | 配對碼推送 + 授權請求 inline keyboard |
| `authorization` | `gateway` | server.py 訊息泵授權回覆分支 |
| `authorization` | `mcp-server` | museon_auth_status 查詢 |
| `footprint` | `data-bus` | cognitive_trace.jsonl 寫入 |
| `observatory` | `footprint` | 讀取 cognitive_trace.jsonl 視覺化 |
| `observatory` | `service-health` | 讀取健康狀態 |
| `brain` | `lord-profile` | _observe_lord() 領域畫像寫入 |
| `lord-profile` | `persona-router` | 百合引擎讀取領域畫像（Phase 1） |
| `interaction-queue` | `telegram` | present_choices() InlineKeyboard 呈現 |
| `interaction-queue` | `discord` | present_choices() Button/Select 呈現 |
| ~~`interaction-queue`~~ | ~~`line`~~ | ~~present_choices() Quick Reply/Flex 呈現（LINE 已刪除 v1.59）~~ |
| `interaction-queue` | `gateway` | message pump 互動攔截 + asyncio.Event 等待 |
| `gateway` | `interaction-queue` | InteractionQueue 啟動初始化 |
| ~~`line`~~ | ~~`event-bus`~~ | ~~LINE webhook 事件發布（LINE 已刪除 v1.59）~~ |
| `proactive-dispatcher` | `telegram` | 攔截 push_notification，統一推播出口 |
| ~~`proactive-dispatcher`~~ | ~~`push-budget`~~ | ~~推播前去重配合~~ ← 已刪除 v1.72 |
| `proactive-dispatcher` | `haiku-llm` | 三桶分級配額決策（LLM adapter 接入，v1.72 新增） |
| `cron` | `museoff` | cron.status() 健康度讀取，museoff.py L7 消費（v1.72 新增） |
| `proactive-bridge` | `proactive-dispatcher` | 推播前檢查（語意去重+分級） |
| `brain` | `memory-graph` | 初始化記憶關聯圖 |
| `brain` | `insight-extractor` | 初始化洞見萃取引擎 |
| `insight-extractor` | `knowledge-lattice` | 洞見結晶化（case_crystal / exploration_crystal） |
| `museoff` | `shared-board` | 讀寫看板（巡邏結果） |
| `museqa` | `shared-board` | 讀寫看板（品質檢查結果） |
| `museoff` | `doctor-notify` | MuseOff 發送診斷卡通知 |
| `museqa` | `doctor-notify` | MuseQA 發送品質問題通知 |
| `doctor-notify` | `telegram` | DM 老闆 + 待審閱摘要 |
| `musedoc` | `shared-board` | 讀寫看板（文件同步結果） |
| `museworker` | `shared-board` | 讀寫看板（變動記錄） |
| `musedoctor` | `auto-repair` | 呼叫修復引擎（目錄補建、log 輪轉） |
| `musedoctor` | `nightly-pipeline` | 讀取 _FULL_STEPS 驗證 nightly 步驟 |
| `cron-registry` | `musedoctor` | 排程 patrol_tick（每 8 分鐘） |
| `brain-tools` | `skill-counter` | Skill 調用計量 |
| `brain-observation` | `trait-engine` | _observe_self() C-trait 即時更新 |
| `brain-observation` | `growth-stage-computer` | _observe_self() 認知成熟度計算（取代硬編碼 adult） |
| `drift-detector` | `momentum-brake` | 捕獲風險計算（capture risk detection） |
| `nightly-reflection-engine` | `anima-mc-store` | P-trait delta 寫入（evolution_write） |
| `nightly-reflection-engine` | `soul-ring` | value_calibration 積分存入 |
| `dissent-engine` | `crystal-rules` | 讀取 crystal_rules.json 進行矛盾檢測 |
| `mask-engine` | `anima-mc-store` | 讀取 trait_dimensions 計算人格適應 |
| `server` | `consultant-supplement` | Gateway 初始化時建立 ConsultantSupplement 實例 |
| `telegram-pump` | `consultant-supplement` | L2 回覆後觸發補充分析與 Telegram 發送 |
| `consultant-supplement` | `telegram` | 獨立 Telegram 訊息輸出（挑戰/提醒補充）  |
| `brain-prompt-builder` | `decision-atlas` | _build_decision_atlas_context() 讀取 da-*.json 注入 persona zone |
| `vision-loop` | `constellation-radar` | 讀取星座活躍度數據作為方向信號 |
| `vision-loop` | `decision-atlas` | 讀取決策圖譜數據匯聚方向提案 |
| `vision-loop` | `breath-analyzer` | 讀取 breath/patterns/*.json（前序分析結果） |
| `brain` | `gap-accumulator` | brain.py Step 3.1c 弱匹配偵測 + Step 8.1 Nightly 宏觀分析（fire-and-forget，兩個注入點） |
| `gap-accumulator` | `vector-bridge` | gaps collection RW（弱匹配向量索引） |
| `gap-accumulator` | `morphenix` | morphenix/notes/ 寫入（scout_gap_cluster + scout_skill_optimize 筆記） |
| `gap-accumulator` | `event-bus` | 發布 SKILL_GAP_PROPOSAL + SKILL_REFORGE_PROPOSAL 事件 |
| `event-bus` | `telegram` | 訂閱 SKILL_GAP_PROPOSAL + SKILL_REFORGE_PROPOSAL（Stage 2 主動詢問） |

#### v1.43 全系統拓撲審計補齊（70 條）

> **背景**：2026-03-23 全系統 import vs 拓撲交叉審計，發現拓撲覆蓋率僅 62.8%。
> 以下按嚴重度分組補齊。

##### 🔴 結構斷裂（7 條）
| Source | Target | 說明 |
|--------|--------|------|
| `gateway` | `feedback-loop` | server.py:4609 API 端點實例化 FeedbackLoop |
| `pulse` | `knowledge-lattice` | pulse_engine.py:565,:1723 探索→結晶化閉環 |
| `governance` | `heartbeat` | vital_signs.py:554 治理層讀取心跳引擎單例 |
| `immunity` | `research-engine` | immune_research.py:159 免疫研究呼叫外部研究引擎 |
| `wee` | `workflow-state-db` | wee_engine.py:23-24 頂層硬 import workflow.models + workflow_engine |
| `outward-trigger` | `research-engine` | outward_trigger.py:211 演化鏈核心環節（research 為獨立 Python 包） |
| `gateway` | `wee` | server.py:2595,:3336 直接呼叫 get_wee_engine() |

##### 🟠 重要遺漏（20 條）
| Source | Target | 說明 |
|--------|--------|------|
| `wee` | `knowledge-lattice` | wee_engine.py:658 讀取 KnowledgeLattice |
| `evolution-velocity` | `crystal-store` | evolution_velocity.py:373 跨群組讀取 |
| `perception` | `heartbeat` | perception.py:723 感知模組讀取心跳聚焦 |
| `governor` | `morphenix` | governor.py:908 治理者觸發演化執行 |
| `nightly` | `vector-index` | nightly_pipeline.py:1686,:1704 Step 8.5/8.6 向量重建 |
| `nightly` | `memory` | nightly_pipeline.py:665,:1404 ChromosomeIndex 記憶壓縮 |
| `nightly` | `research-engine` | nightly_pipeline.py:2255,:2315 夜間探索研究 |
| `morphenix` | `pulse` | morphenix_executor.py:622,:641,:677 演化執行修改 Pulse 行為 |
| `nightly` | `multiagent` | nightly_pipeline.py:459,:489 Step 3/4 共享資產 |
| `brain` | `heartbeat` | brain.py:868 log_action() 呼叫 |
| `brain` | `pulse-db` | brain.py:393 token_budget（pulse 包下） |
| `brain` | `pulse` | brain.py:361 async_write_queue |
| `gateway` | `nightly` | server.py:1163+ 呼叫 10+ 個 nightly 子模組 |
| `gateway` | `workflow-state-db` | server.py:2988-2991,:4219 WorkflowStore/Engine/Executor/Scheduler |
| `gateway` | `multiagent` | server.py:1700,:1734,:1762 department_config/shared_assets/okr_router |
| `gateway` | `sandbox` | server.py:2519,:2539 ExecutionSandbox |
| `gateway` | `research-engine` | server.py:5721 研究引擎觸發 |
| `brain` | `tool-muscle` | brain.py:227 ModuleSpec + L1442 record_use() |
| `brain` | `trigger-weights` | brain.py:237 ModuleSpec 觸發權重 |

##### 🟡 文件欠債（43 條）
| Source | Target | 說明 |
|--------|--------|------|
| `digest-engine` | `security` | digest_engine.py:487 輸入淨化 sanitizer |
| `nightly` | `crystal-actuator` | nightly_pipeline.py:719 Step 4 結晶降級 |
| `nightly` | `footprint` | nightly_pipeline.py:2853 Step 23.5 足跡統計 |
| `nightly` | `immunity` | nightly_pipeline.py:2936 Step 24 immune_memory 學習（補充粒度） |
| `nightly` | `group-context-db` | nightly_pipeline.py:3295 Step 28 群組上下文清理 |
| `nightly` | `workflow-state-db` | nightly_pipeline.py:3306 Step 28.5 工作流清理 |
| `nightly` | `tool-registry` | nightly_pipeline.py:2623-2624 Step 22 工具探測 |
| ~~`nightly`~~ | ~~`federation-sync`~~ | ~~nightly_pipeline.py:2751 Step 23 母子同步~~ ❌ **v1.53 移除**：federation 模組已刪除 |
| `nightly` | `pulse-db` | nightly_pipeline.py:1103+ 多步驟讀寫 PulseDB（5 處） |
| `nightly` | `tool-muscle` | nightly_pipeline.py:2904 Step 24 肌肉記憶追蹤 |
| `nightly` | `trigger-weights` | nightly_pipeline.py:2973 Step 25 觸發權重 |
| `morphenix` | `knowledge-lattice` | morphenix_executor.py:1357 結晶查詢 |
| `nightly` | `eval-engine` | job.py:111 NightlyJob 品質評分 |
| `periodic-cycles` | `skill-router` | periodic_cycles.py:923 週期統計 SkillLoader |
| `skill-forge-scout` | `research-engine` | skill_forge_scout.py:141 鍛造偵察研究 |
| `brain` | `doctor` | brain.py:571,:1378 self_diagnosis 觸發 |
| `brain` | `multiagent` | brain.py:344 context_switch |
| `brain` | `okr-router` | brain.py:766 OKR 路由呼叫 |
| `brain-observation` | `governance` | brain_observation.py:1072 ExternalAnimaManager |
| `brain-observation` | `vector-index` | brain_observation.py:875 向量索引存取 |
| `brain-prompt-builder` | `governance` | brain_prompt_builder.py:468 外部使用者記憶 |
| `brain-prompt-builder` | `pulse-db` | brain_prompt_builder.py:501 PulseDB 脈搏數據 |
| `brain-dispatch` | `pulse-db` | brain_dispatch.py:652 orchestrator_calls |
| `eval-engine` | `pulse-db` | eval_engine.py:463 Q-Score 存取 |
| `gateway` | `doctor` | server.py:577+ 呼叫 doctor 全部子模組（health_check/audit/repair/surgeon 等） |
| `gateway` | `tool-registry` | server.py:1780+ 呼叫 tools 群組 26 處 import |
| `gateway` | `governance` | server.py:2846,:3709,:3843 bulkhead/multi_tenant/group_context |
| `gateway` | `telegram-pump` | server.py 從 telegram_pump.py import 訊息泵邏輯（v1.50 拆分） |
| `gateway` | `routes-api` | server.py 從 routes_api.py import API 端點註冊（v1.50 拆分） |
| `gateway` | `cron-registry` | server.py 從 cron_registry.py import cron 任務註冊（v1.50 拆分） |
| `telegram-pump` | `response-guard` | telegram_pump.py 所有發送路徑統一走 adapter._safe_send() → ResponseGuard.sanitize_for_group()（v1.82 消除 9 處直送）+ chat_id 交叉驗證 |
| `telegram-pump` | `governance` | telegram_pump.py lazy import: group_context, multi_tenant, rate_limiter |
| `telegram-pump` | `interaction-queue` | telegram_pump.py lazy import: interaction queue |
| `telegram-pump` | `message-queue-store` | telegram_pump.py lazy import: enqueue/mark_done/mark_failed/recover_pending（v1.51 訊息持久化） |
| `gateway` | `message-queue-store` | server.py startup 初始化 MessageQueueStore singleton（v1.51） |
| `gateway` | `brain-worker` | server.py startup 啟動 BrainWorkerManager + shutdown 停止（v1.52） |
| `telegram-pump` | `brain-worker` | telegram_pump.py _brain_process_with_sla worker 優先路徑（v1.52） |
| `brain-worker` | `brain` | subprocess 內 MuseonBrain(data_dir=...) 初始化 + process()（v1.52） |
| `brain` | `response-guard` | brain.py process() 開始時 register_origin() 註冊來源 chat_id（v1.50 備註：實際 validate 在 telegram-pump 中調用） |
| `guardian` | `security` | daemon.py:566 安全審計日誌 |
| `self-diagnosis` | `tool-registry` | self_diagnosis.py:246,:484 工具狀態查詢 |
| `surgery` | `morphenix` | surgeon.py:47 morphenix_standards 引用 |
| `telegram` | `governance` | telegram.py:245,:318 群組上下文讀寫 |
| `telegram` | `multiagent` | telegram.py:444,:461,:478 飛輪部門查詢 |
| `telegram` | `pulse-db` | telegram.py:583 脈搏讀取 |
| `onboarding` | `pulse-db` | ceremony.py:16 上線儀式 PulseDB 寫入 |
| `nightly` | `sparse-embedder` | nightly_pipeline.py:3157 Step 8.7 IDF 重建 |
| `gateway` | `immunity` | server.py:3233 免疫研究初始化 |
| `brain` | `llm-router` | brain.py:319 create_adapter_sync 直接存取 |
| `brain-tools` | `llm-router` | brain_tools.py:134 APICompatResponse 型別引用 |
| `nightly` | `token-budget` | nightly_pipeline.py:2992 Step 26 預算結算（pulse 包下） |
| `gateway` | `cron` | server.py:5000+ cron 排程管理初始化 |
| `gateway` | `event-bus` | server.py:1000+ 事件訂閱註冊（5 事件） |
| `gateway` | `brain` | server.py 訊息泵→Brain.chat()（主要呼叫路徑） |

#### v1.70 tools.py 新工具 + telegram_pump 跨連線（2026-03-31）

##### 新增工具（1 條）
| Source | Target | 說明 |
|--------|--------|------|
| `brain-tools` | `publish-report-sh` | tools.py 新增 `publish_report` 工具，shell out 到 `scripts/publish-report.sh`（外部指令） |

##### 新增跨連線（1 條）
| Source | Target | 說明 |
|--------|--------|------|
| `telegram-pump` | `brain` | telegram_pump.py 群組訊息觸發 `brain._call_llm_with_model()` 做 Haiku LLM 敏感度驗證 |

### Skills 控制連線（control）
| Source | Target | 說明 |
|--------|--------|------|
| `event-bus` | `skills-thinking-hub` | 思維技能事件 |
| `event-bus` | `skills-market-hub` | 市場技能事件 |
| `event-bus` | `skills-business-hub` | 商業技能事件 |
| `event-bus` | `skills-creative-hub` | 創意技能事件 |
| `event-bus` | `skills-product-hub` | 產品技能事件 |
| `event-bus` | `skills-evolution-hub` | 演化技能事件 |
| `event-bus` | `skills-workflow-hub` | 工作流技能事件 |

### Skills 內部連線（internal）

#### Thinking Hub
| Source | Target | 說明 |
|--------|--------|------|
| `skills-thinking-hub` | `dharma` | 思維轉化 |
| `skills-thinking-hub` | `philo-dialectic` | 哲學思辨 |
| `skills-thinking-hub` | `resonance` | 感性共振 |
| `skills-thinking-hub` | `shadow` | 博弈辨識 |
| `skills-thinking-hub` | `meta-learning` | 元學習 |
| `skills-thinking-hub` | `query-clarity` | 問題品質 |
| `skills-thinking-hub` | `user-model` | 使用者畫像 |
| `skills-thinking-hub` | `energy-reading` | 八方位能量解讀 |
| `skills-thinking-hub` | `wan-miu-16` | 萬謬16型人格 |
| `skills-thinking-hub` | `combined-reading` | 合盤能量比對 |
| `skills-thinking-hub` | `anima-individual` | ANIMA 個體追蹤 |
| `skills-thinking-hub` | `ares` | 戰神系統 |
| `skills-thinking-hub` | `shadow-muse` | 挑戰教練 |
| `skills-thinking-hub` | `daily-pilot` | 每日導航 |
| `skills-thinking-hub` | `talent-match` | 人才媒合 |

#### Market Hub
| Source | Target | 說明 |
|--------|--------|------|
| `skills-market-hub` | `market-core` | 市場核心 |
| `skills-market-hub` | `market-equity` | 股票分析 |
| `skills-market-hub` | `market-crypto` | 加密貨幣 |
| `skills-market-hub` | `market-macro` | 總體經濟 |
| `skills-market-hub` | `risk-matrix` | 風險管理 |
| `skills-market-hub` | `sentiment-radar` | 情緒雷達 |
| `market-core` | `market-equity` | 股票衛星 |
| `market-core` | `market-crypto` | 加密衛星 |
| `market-core` | `market-macro` | 總經衛星 |

#### Business Hub
| Source | Target | 說明 |
|--------|--------|------|
| `skills-business-hub` | `business-12` | 商模十二力 |
| `skills-business-hub` | `ssa-consultant` | 顧問銷售 |
| `skills-business-hub` | `master-strategy` | 戰略判斷 |
| `skills-business-hub` | `consultant-communication` | 顧問溝通 |
| `skills-business-hub` | `xmodel` | 破框解方 |
| `skills-business-hub` | `pdeif` | 逆熵流 |
| `skills-business-hub` | `brand-discovery` | 品牌訪談 |
| `skills-business-hub` | `brand-builder` | 品牌建構 |
| `skills-business-hub` | `biz-diagnostic` | 商業模式健檢 |
| `skills-business-hub` | `ad-pilot` | 廣告診斷 |
| `skills-business-hub` | `equity-architect` | 股權架構 |
| `skills-business-hub` | `biz-collab` | 異業合作 |
| `brand-discovery` | `brand-builder` | 訪談資料→品牌分析 |
| `brand-discovery` | `biz-diagnostic` | 品牌訪談資料→健檢參數 |
| `biz-diagnostic` | `darwin` | strategy_brief→DARWIN 模擬 |
| `biz-diagnostic` | `business-12` | 診斷焦點交叉驗證 |
| `biz-diagnostic` | `report-forge` | 診斷報告渲染 |
| `biz-diagnostic` | `ssa-consultant` | SSA Day Level 對照 |

#### Creative Hub
| Source | Target | 說明 |
|--------|--------|------|
| `skills-creative-hub` | `c15` | 敘事張力 |
| `skills-creative-hub` | `text-alchemy` | 文字煉金 |
| `skills-creative-hub` | `storytelling-engine` | 說故事 |
| `skills-creative-hub` | `novel-craft` | 小說工藝 |
| `skills-creative-hub` | `aesthetic-sense` | 美感 |
| `skills-creative-hub` | `brand-identity` | 品牌識別 |
| `skills-creative-hub` | `video-strategy` | 短影音 |
| `skills-creative-hub` | `course-forge` | 課程建構 |
| `text-alchemy` | `c15` | 語言層注入 |
| `text-alchemy` | `novel-craft` | 小說工藝 |
| `text-alchemy` | `storytelling-engine` | 說故事 |

#### Product Hub
| Source | Target | 說明 |
|--------|--------|------|
| `skills-product-hub` | `acsf` | 能力結晶 |
| `skills-product-hub` | `dse` | 技術融合 |
| `skills-product-hub` | `gap` | 缺口分析 |
| `skills-product-hub` | `env-radar` | 環境雷達 |
| `skills-product-hub` | `info-architect` | 資訊架構 |
| `skills-product-hub` | `report-forge` | 報告鍛造 |
| `skills-product-hub` | `orchestrator` | 編排 |
| `skills-product-hub` | `brand-project-engine` | 品牌專案 |
| `skills-product-hub` | `finance-pilot` | 財務導航 |

#### Evolution Hub
| Source | Target | 說明 |
|--------|--------|------|
| `skills-evolution-hub` | `sandbox-lab` | 沙盒實驗 |
| `skills-evolution-hub` | `qa-auditor` | 品質審計 |
| `skills-evolution-hub` | `tantra` | 情慾治理 |
| `skills-evolution-hub` | `system-health-check` | 系統健康自檢 |
| `skills-evolution-hub` | `decision-tracker` | 決策歷史追蹤 |
| `skills-evolution-hub` | `prompt-stresstest` | Prompt壓測 |

#### Workflow Hub
| Source | Target | 說明 |
|--------|--------|------|
| `skills-workflow-hub` | `workflow-svc-brand-marketing` | 品牌行銷 |
| `skills-workflow-hub` | `workflow-investment-analysis` | 投資分析 |
| `skills-workflow-hub` | `workflow-ai-deployment` | AI部署 |
| `skills-workflow-hub` | `workflow-brand-consulting` | 品牌手冊 |
| `skills-workflow-hub` | `group-meeting-notes` | 會議記錄 |
| `workflow-brand-consulting` | `brand-discovery` | 工作流→訪談 |
| `workflow-brand-consulting` | `brand-builder` | 工作流→品牌建構 |

### Skills 跨群組連線（cross）

> 基於 Skill Manifest 的 connects_to 定義

| Source | Target | 說明 |
|--------|--------|------|
| `deep-think` | `resonance` | 共振觸發 |
| `deep-think` | `dharma` | 思維轉化 |
| `deep-think` | `philo-dialectic` | 哲學思辨 |
| `deep-think` | `master-strategy` | 戰略判斷 |
| `investment-masters` | `market-core` | 市場分析 |
| `investment-masters` | `risk-matrix` | 風險管理 |
| `investment-masters` | `sentiment-radar` | 情緒雷達 |
| `roundtable` | `master-strategy` | 戰略詰問 |
| `roundtable` | `shadow` | 博弈辨識 |
| `wee` | `pdeif` | 逆熵流演化 |
| `wee` | `xmodel` | 破框解方 |
| `wee` | `orchestrator` | 編排演化 |
| `morphenix` | `qa-auditor` | 品質審計 |
| `morphenix` | `env-radar` | 環境掃描 |
| ~~`dna27`~~ | ~~`query-clarity`~~ | ~~問題品質守門（dna27 已刪除 v1.59）~~ |
| ~~`dna27`~~ | ~~`c15`~~ | ~~敘事張力（dna27 已刪除 v1.59）~~ |
| `knowledge-lattice` | `skills-thinking-hub` | 記憶接收（思維） |
| `knowledge-lattice` | `skills-market-hub` | 記憶接收（市場） |
| `knowledge-lattice` | `skills-business-hub` | 記憶接收（商業） |
| `knowledge-lattice` | `skills-creative-hub` | 記憶接收（創意） |
| `knowledge-lattice` | `skills-product-hub` | 記憶接收（產品） |
| `knowledge-lattice` | `skills-evolution-hub` | 記憶接收（演化） |
| `knowledge-lattice` | `skills-workflow-hub` | 記憶接收（工作流） |
| `skills-thinking-hub` | `brain` | 思維技能→Brain |
| `skills-market-hub` | `brain` | 市場技能→Brain |
| `skills-business-hub` | `brain` | 商業技能→Brain |
| `skills-creative-hub` | `brain` | 創意技能→Brain |
| `skills-product-hub` | `brain` | 產品技能→Brain |
| `skills-evolution-hub` | `evolution` | 演化技能→Evolution |
| `skills-workflow-hub` | `brain` | 工作流技能→Brain |
| `report-forge` | `knowledge-lattice` | 報告洞見結晶化 |
| `system-health-check` | `knowledge-lattice` | 健康結晶化 |
| `system-health-check` | `morphenix` | 修復提案 |
| `decision-tracker` | `knowledge-lattice` | 決策結晶化 |
| `decision-tracker` | `user-model` | 決策偏好 |
| `energy-reading` | `dharma` | 思維轉化讀取 |
| `energy-reading` | `resonance` | 感性共振讀取 |
| `energy-reading` | `knowledge-lattice` | 能量結晶讀寫 |
| `energy-reading` | `user-model` | 使用者畫像讀寫 |
| `wan-miu-16` | `energy-reading` | 能量數據讀取 |
| `wan-miu-16` | `knowledge-lattice` | 人格結晶讀寫 |
| `wan-miu-16` | `user-model` | 使用者畫像讀寫 |
| `combined-reading` | `energy-reading` | 能量數據讀取 |
| `combined-reading` | `wan-miu-16` | 人格數據讀取 |
| `combined-reading` | `knowledge-lattice` | 關係結晶讀寫 |
| `combined-reading` | `user-model` | 使用者畫像讀寫 |
| `anima-individual` | `wan-miu-16` | 萬謬16型人格數據 |
| `anima-individual` | `energy-reading` | 八方位能量數據 |
| `anima-individual` | `combined-reading` | 合盤能量比對 |
| `anima-individual` | `shadow` | 博弈模式辨識 |
| `anima-individual` | `master-strategy` | 戰略評估 |
| `anima-individual` | `xmodel` | 破框解方 |
| `anima-individual` | `knowledge-lattice` | individual_crystal 結晶讀寫 |
| `anima-individual` | `user-model` | 使用者畫像讀寫 |
| `ares` | `anima-individual` | 個體引擎調用 |
| `ares` | `wan-miu-16` | 萬謬16型人格數據 |
| `ares` | `energy-reading` | 八方位能量數據 |
| `ares` | `combined-reading` | 合盤能量比對 |
| `ares` | `master-strategy` | 九策軍師戰略評估 |
| `ares` | `shadow` | 陰謀博弈辨識 |
| `ares` | `xmodel` | 破框解方 |
| `ares` | `pdeif` | 逆熵流路徑設計 |
| `ares` | `roundtable` | 多角色詰問 |
| `ares` | `business-12` | 商模十二力診斷 |
| `ares` | `ssa-consultant` | 顧問銷售策略 |
| `ares` | `knowledge-lattice` | strategy_crystal 結晶讀寫 |
| `ares` | `user-model` | 使用者畫像讀寫 |
| `ares` | `c15` | 敘事張力語言 |
| `skill-router` | `esg-architect-pro` | Skill 路由匹配 |
| `skill-router` | `human-design-blueprint` | Skill 路由匹配 |
| `skill-router` | `meeting-intelligence` | Skill 路由匹配 |

### 監控連線（monitor）
| Source | Target | 說明 |
|--------|--------|------|
| `service-health` | `gateway` | 監控 |
| `service-health` | `qdrant` | 監控 |
| `service-health` | `searxng` | 監控 |
| `service-health` | `firecrawl` | 監控 |
| `service-health` | `anthropic-api` | 監控 |

### 非同步連線（async）
| Source | Target | 說明 |
|--------|--------|------|
| `proactive-bridge` | `telegram` | 非同步推播 |
| `nightly` | `event-bus` | 回饋迴路 |
| `morphenix` | `event-bus` | 提案回饋 |
| `telegram` | `zeal` | 回傳回應（私聊 + 群組回覆） |
| `telegram` | `external-user` | 群組中回覆外部使用者 |
| `line` | `zeal` | LINE 回傳回應 |
| `data-watchdog` | `event-bus` | 監控事件 |
| `telegram` | `brain` | 推送寫入 session |
| `fact-correction` | `proactive-bridge` | P4 自省清洗推播 |
| `fact-correction` | `pulse` | P4 自省清洗脈搏 |
| `zeal` | `anima-mc-store` | Owner 互動觸發 ANIMA_MC 更新（boss_name、self_awareness） |
| `verified-user` | `anima-mc-store` | 配對使用者互動更新 ANIMA_USER（L1-L8 觀察） |
| `external-user` | `anima-mc-store` | 外部使用者互動更新 external_users/ 觀察 |
| ~~`brain`~~ | ~~`epigenetic-router`~~ | ~~記憶注入前呼叫表觀遺傳路由（epigenetic-router 已刪除 v1.59）~~ |
| ~~`epigenetic-router`~~ | ~~`memory-reflector`~~ | ~~回憶後觸發反思（已刪除）~~ |
| ~~`epigenetic-router`~~ | ~~`diary-store`~~ | ~~時間圖/因果圖遍歷（已刪除）~~ |
| ~~`epigenetic-router`~~ | ~~`anima-changelog`~~ | ~~時間圖遍歷（已刪除）~~ |
| ~~`epigenetic-router`~~ | ~~`knowledge-lattice`~~ | ~~結晶圖遍歷（已刪除）~~ |
| `memory-reflector` | `adaptive-decay` | 反思時計算 Activation 排序 |
| ~~`brain`~~ | ~~`proactive-predictor`~~ | ~~Skill 使用記錄 + 需求預判（proactive-predictor 已刪除 v1.59）~~ |
| ~~`proactive-predictor`~~ | ~~`metacognition`~~ | ~~預判結果回饋元認知（已刪除）~~ |
| `brain` | `anima-changelog` | _save_anima_user 前記錄差分 |
| `diary-store` | `qdrant` | Soul Ring 向量索引到 soul_rings collection |
| `adaptive-decay` | `nightly` | 每日衰減排程（Step 32） |

### 星座系統連線（constellation）

> 以下連線描述星座系統與 Brain/Skills 的整合關係。

#### 星座內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `constellation-radar` | `constellation-absurdity` | 荒謬六芒星作為底層 OS，雷達掛載 |
| `constellation-radar` | `constellation-business` | 商模十二力星追蹤 |
| `constellation-radar` | `constellation-brand` | 品牌七芒星追蹤 |
| `constellation-radar` | `constellation-strategy` | 戰略三稜鏡追蹤 |
| `constellation-radar` | `constellation-energy` | 能量八芒星追蹤 |
| `constellation-radar` | `constellation-conversion` | 轉化漏斗三角星追蹤 |
| `constellation-radar` | `constellation-market` | 市場七芒星追蹤 |
| `constellation-radar` | `constellation-thinking` | 思維轉化五芒星追蹤 |
| `constellation-radar` | `constellation-growth` | 年輪星追蹤 |
| `constellation-radar` | `constellation-probe` | 探針層隸屬雷達引擎 |

#### 星座跨群組連線（cross）
| Source | Target | 說明 |
|--------|--------|------|
| `constellation-probe` | `brain` | 探針觸發時注入診斷上下文至 Brain |
| `constellation-probe` | `brain-prompt-builder` | 星座缺口注入 system prompt（constellation zone） |
| `constellation-absurdity` | `constellation-business` | 商模盲區映射回荒謬六芒星 |
| `constellation-absurdity` | `constellation-brand` | 品牌盲區映射回荒謬六芒星 |
| `constellation-absurdity` | `constellation-strategy` | 戰略盲區映射回荒謬六芒星 |
| `constellation-absurdity` | `constellation-energy` | 能量盲區映射回荒謬六芒星 |
| `constellation-absurdity` | `constellation-conversion` | 轉化漏斗映射回荒謬六芒星 |
| `constellation-absurdity` | `constellation-market` | 市場認知映射回荒謬六芒星 |
| `constellation-absurdity` | `constellation-thinking` | 思維品質映射回荒謬六芒星 |
| `constellation-absurdity` | `constellation-growth` | 決策機器映射回荒謬六芒星 |
| `constellation-business` | `business-12` | 商模十二力星連結商模十二力 Skill |
| `constellation-business` | `ssa-consultant` | 商模十二力星連結 SSA 顧問 Skill |
| `constellation-brand` | `brand-builder` | 品牌七芒星連結品牌建構 Skill |
| `constellation-brand` | `brand-identity` | 品牌七芒星連結品牌識別 Skill |
| `constellation-strategy` | `master-strategy` | 戰略三稜鏡連結戰略判斷 Skill |
| `constellation-strategy` | `shadow` | 戰略三稜鏡連結陰謀辨識 Skill |
| `constellation-energy` | `energy-reading` | 能量八芒星連結八方位能量解讀 Skill |
| `constellation-energy` | `onemuse-core` | 能量八芒星連結 One Muse 核心知識 |
| `constellation-conversion` | `ssa-consultant` | 轉化漏斗連結 SSA 顧問 Skill |
| `constellation-conversion` | `landing-page-forge` | 轉化漏斗連結銷售頁鍛造 Skill |
| `constellation-market` | `market-core` | 市場七芒星連結市場分析核心 Skill |
| `constellation-market` | `market-equity` | 市場七芒星連結股票分析 Skill |
| `constellation-market` | `investment-masters` | 市場七芒星連結投資軍師團 Skill |
| `constellation-thinking` | `dharma` | 思維轉化五芒星連結思維轉化引擎 Skill |
| `constellation-thinking` | `deep-think` | 思維轉化五芒星連結深度思考 Skill |
| `constellation-thinking` | `philo-dialectic` | 思維轉化五芒星連結哲學思辨 Skill |
| `constellation-growth` | `wan-miu-16` | 年輪星連結萬謬16型人格 Skill |
| `constellation-growth` | `anima-individual` | 年輪星連結 ANIMA 個體追蹤 Skill |
| `constellation-growth` | `resonance` | 年輪星連結感性共振 Skill |
| `absurdity-radar` | `constellation-radar` | 荒謬雷達數據同步至星座雷達（缺口引力共享） |
| `nightly-pipeline` | `constellation-radar` | Nightly 步驟定期重算星座活躍度 |
| `skill-router` | `constellation-radar` | Skill 路由讀取星座缺口引力輔助決策 |

---

## 驗證規則（Validation Rules）

### 必要條件 — 每次審計必檢

- [ ] **無孤立節點**：每個節點至少有 1 條連線（輸入或輸出）
- [ ] **Hub 完整性**：每個 Hub 節點必須與其所有 `parent=hub` 的子節點有 `internal` 連線
- [ ] **Event Bus 必達**：每個群組的 Hub 至少有 1 條與 `event-bus` 的連線（control 或 async）
- [ ] **外部服務必監控**：每個 `external` 節點至少被 `service-health` 監控
- [ ] **資料層必連**：任何讀寫持久資料的節點必須與 `data` 群組有 `cross` 連線
- [ ] **雙向一致**：如果 A→B 是 `cross`，B 的影響範圍分析中必須包含 A

### 新增模組必做清單

1. 在本文件 `nodes` 對應群組表格新增條目
2. 定義所有 **輸入連線**（誰呼叫/觸發此模組？）
3. 定義所有 **輸出連線**（此模組呼叫/影響誰？）
4. 如果是 Hub 的子節點，設定 `parent` 並加入 `internal` 連線
5. 如果依賴外部服務，加入 `cross` 連線到 `external` 節點
6. 如果產生/消費持久資料，加入 `cross` 連線到 `data` 群組
7. 更新 3D 心智圖 HTML（`data/workspace/MUSEON_3d_mindmap.html`）的 nodes 和 links 陣列
8. 執行驗證規則確認無違規

### 影響範圍分析模板

修改節點 `X` 前，查詢：

```
直接影響：X 的所有輸出連線 targets
間接影響：targets 的輸出連線 targets（二度關聯）
上游依賴：X 的所有輸入連線 sources
測試範圍：直接影響 + X 本身
```

---

## 統計摘要

| 指標 | 數值 |
|------|------|
| 總節點數 | 208（205 + 3 v1.84 新增：breath-analyzer / vision-loop / consultant-supplement）|
| 總連線數 | 556（547 + 9 v1.84 新增：2 internal nightly + 7 cross）|
| 群組數 | 16 (含 skills、learning、billing、constellation) |
| Hub 節點 | 20 (12 系統 + 7 Skills Hub + 1 constellation-radar) |
| 已刪除節點（v1.59）| 20（含 line/electron/dna27/epigenetic-router/proactive-predictor 等） |
| 已刪除連線（v1.59）| 24（所有涉及已刪除模組的連線，文件中以刪除線標記） |
| 破損 import（未修）| 2（brain_fast.py → input_sanitizer, ceremony） |
| 拓撲覆蓋率 | 100%（v1.43 全系統審計後，v1.59 後需重新確認） |

---

## 版本紀錄

| 版本 | 日期 | 變更 |
|------|------|------|
| v1.85 | 2026-04-05 | 能力缺口偵測系統——nightly 群組新增 gap-accumulator（三軌道 A/B/C 缺口累積，扇入=1 brain，扇出=3 vector-bridge/morphenix/event-bus）；新增 5 cross 連線（brain→gap-accumulator 兩點、gap-accumulator→vector-bridge/morphenix/event-bus）+ 1 event-bus→telegram 訂閱（SKILL_GAP_PROPOSAL+SKILL_REFORGE_PROPOSAL）；208→209 節點，556→562 連線 |
| v1.84 | 2026-04-05 | 五個新功能補登——nightly 群組新增 breath-analyzer（Step 34.8 呼吸五層分析）和 vision-loop（Step 34.9 週日願景迴圈）；agent 群組新增 consultant-supplement（L2 後補充，扇入=2）；data 群組新增 decision-atlas（決策圖譜，資料節點）；新增 2 internal（nightly-pipeline→breath-analyzer/vision-loop）+ 7 cross 連線（server/telegram-pump→consultant-supplement、consultant-supplement→telegram、brain-prompt-builder→decision-atlas、vision-loop→constellation-radar/decision-atlas/breath-analyzer）；205→208 節點，547→556 連線 |
| v1.82 | 2026-04-04 | 星座系統——新增 `constellation` 群組（constellation-radar Hub + constellation-probe + constellation-absurdity/business/brand/strategy/energy/conversion/market/thinking/growth 共 11 節點）；新增 10 internal + 15 cross 連線；群組色碼 `#9B59B6`；194→205 節點，522→547 連線 |
| v1.88 | 2026-04-05 | 五虎將自癒管線四修復——doctor 群組新增 rb-010-sqlite 節點（RB-010 SQLite 損壞修復，C→B→A 瀑布，SAFE_DBS 白名單）；musedoc 新增 auto-expire-stale 子功能（CRITICAL+7 天+服務已恢復→fixed_externally）；museoff L6c blast_origin + prescription 接線補全；RB-007 post_check 路徑優化（pgrep early return + sleep 45 + 無條件 True）。212 節點 567 連線。同步 blast-radius v2.05 |
| v1.81 | 2026-04-04 | Knife 2+3 變更——llm 群組新增 `semantic-response-cache`（Qdrant-backed 語意回覆快取，零 LLM token，v12 新增）；新增 3 條連線（brain→semantic-response-cache 查詢快取、l4-cpu-observer→semantic-response-cache 寫入、semantic-response-cache→qdrant collection 讀寫）；brain_tools.py tool-use loop 改用 --resume session；cron_registry.py 新增 quota circuit breaker；cron 頻率調整（breath-pulse 每小時1次、curiosity-research 週二次、business-case 週一次）|
| v1.80 | 2026-04-04 | L4 CPU Observer 架構更新——agent 群組新增 `l4-cpu-observer`（CPU-only 對話後觀察者，取代 Haiku L4 agent spawn，零 LLM 呼叫，<10ms）；brain-tools 描述更新（_classify_complexity 已改為 CPU-only v12）；新增 4 條連線（brain→l4-cpu-observer、l4-cpu-observer→context-cache/session-adjustments/memory）|
| v1.74 | 2026-04-01 | Phase A-C 死碼清理 + signal_lite 遷移——移除 brain-p3-fusion（P3 融合層已清除）、brain-observer（L4 觀察者已刪除）2 個節點；reflex-router 標記已刪除（路由功能退役）；新增 signal-lite 節點（輕量信號路由）；移除連線：brain→brain-p3-fusion、brain→reflex-router（改為 brain→signal-lite）、brain→brain-observer、primal-detector→reflex-router、nightly→reflex-router 共 5 條；brain.py Step 3 描述更新（signal_lite 信號路由）。同步 blast-radius v1.93 |
| v1.71 | 2026-03-31 | Persona Evolution 系統——agent 群組新增 trait-engine / growth-stage-computer / dissent-engine / mask-engine / momentum-brake 5 個節點；nightly 群組新增 nightly-reflection-engine 1 個節點；新增 3 條 internal 連線（brain→dissent-engine、brain→mask-engine、nightly-pipeline→nightly-reflection-engine）+ 7 條 cross 連線（brain-observation→trait-engine、brain-observation→growth-stage-computer、drift-detector→momentum-brake、nightly-reflection-engine→anima-mc-store、nightly-reflection-engine→soul-ring、dissent-engine→crystal-rules、mask-engine→anima-mc-store）；188→194 節點，512→522 連線 |
| v1.66 | 2026-03-30 | 新增 13 個 Skill 節點（ad-pilot、equity-architect、biz-collab、biz-diagnostic（已存在）、video-strategy、course-forge、shadow-muse、daily-pilot、talent-match、brand-project-engine、finance-pilot、prompt-stresstest、workflow-brand-consulting（已存在））；新增 11 條 internal 連線（business +3、creative +2、thinking +3、product +2、evolution +1） |
| v1.62 | 2026-03-29 | 戰神系統（Ares）——thinking 群組新增 anima-individual（ANIMA 個體追蹤引擎）+ ares（戰神系統工作流）2 個 Skill 節點；新增 Python 模組 src/museon/ares/（profile_store/graph_renderer/external_bridge）；新增 2 條 internal + 23 條 cross 連線。188 節點 512 連線 |
| v1.61 | 2026-03-29 | OneMuse 能量解讀技能群——thinking 群組新增 energy-reading/wan-miu-16/combined-reading 3 個 Skill 節點 + 11 條 cross 連線。186 節點 487 連線 |
| v1.59 | 2026-03-28 | 死碼清理 20 個模組後拓撲同步——節點 203→183（-20）；連線 500→476（-24）；更新 fan_in 數據（event_bus 45→46、data_bus 16→15、message 13→14、pulse_db 10→11、vector_bridge 7→9）；記錄破損 import 2 個（brain_fast → input_sanitizer/ceremony 待修） |
| v1.54 | 2026-03-27 | 有機體進化計畫 Phase 1-9——新增 6 節點（proactive-dispatcher、memory-graph、insight-extractor、strategy-accumulator、shared-board、skill-counter）+ 2 群組（learning、billing）+ 12 條跨系統連線 + 4 條內部連線；Nightly 精簡移除 3 步驟；五虎將共享看板；cron 推送納管 ProactiveDispatcher。203 節點 500 連線 |
| v1.53 | 2026-03-26 | v2 Brain 四層架構 + 死碼清理——agent 群組新增 brain-deep（L2 Opus）、brain-tool-loop（tool-use 迴圈）、brain-observer（L4 觀察者）3 節點 + 7 條連線；brain 升級為 L1 Sonnet + escalation；移除 federation（skill-market + federation-sync 2 節點）+ installer 群組（5 節點）；nightly 新增 Step 31 context_cache + context-cache-builder 節點。197 節點 484 連線 |
| v1.52 | 2026-03-25 | Brain 90s SLA + Circuit Breaker + 訊息佇列持久化 + L2 Worker 分離——新增 message-queue-store、brain-worker 2 節點 + 5 條連線；telegram-pump→message-queue-store/brain-worker、gateway→message-queue-store/brain-worker、brain-worker→brain。200 節點 488 連線 |
| v1.51 | 2026-03-25 | 教訓蒸餾+斷裂管線修復——nightly 新增 lesson-distill/client-profile-update 步驟；brain-prompt-builder 新增 3 條 cross 連線；server→guardian mothership_queue；新增 fix-verify Workflow Skill |
| v1.50 | 2026-03-25 | server.py 拆分——新增 telegram-pump/routes-api/cron-registry 3 節點 + 6 條連線；三層洩漏預防（L1 prompt→L2 剝離→L3 guard）。197 節點 487 連線 |
| v1.49 | 2026-03-24 | 全面審計——統計摘要修正（184→194 節點、456→481 連線）|
| v1.48 | 2026-03-24 | 操作記憶層——第六張藍圖 operational-contract.md + scripts/workflows/。194 節點 481 連線 |
| v1.47 | 2026-03-24 | 跨群組洩漏防禦——新增 response-guard 節點 + 3 條連線。194 節點 481 連線 |
| v1.72 | 2026-03-31 | 推播系統重構——刪除 push-budget 節點（-1）；刪除 5 條連線（pulse-engine→push-budget、proactive-bridge→push-budget、push-budget→pulse-db、proactive-dispatcher→push-budget）；新增 2 條連線（proactive-dispatcher→haiku-llm、cron→museoff）；193→192 節點，521→518 連線 |
| v1.46 | 2026-03-23 | 推送品質修復——新增 push-budget 節點 + 3 條連線。193 節點 478 連線 |
| v1.45 | 2026-03-23 | Project Epigenesis——新增 5 節點（epigenetic-router/memory-reflector/proactive-predictor/adaptive-decay/anima-changelog）+ 12 條 cross 連線。192 節點 475 連線 |
| v1.44 | 2026-03-23 | 三層調度員架構——新增 dispatcher/thinker/worker 3 節點 + 7 條連線。187 節點 463 連線 |
| v1.43 | 2026-03-23 | 全系統拓撲審計——補齊 70 條遺漏 cross 連線（🔴7 結構斷裂 + 🟠20 重要遺漏 + 🟡43 文件欠債）；移除 2 條幽靈連線（drift-detector→memory 源碼零 import、zotero-bridge→vector-index 源碼零 import）；修正 1 條方向反轉（federation-sync→nightly → nightly→federation-sync）；拓撲覆蓋率 62.8% → 100%；184 節點 456 連線 |
| v1.42 | 2026-03-22 | Sparse Embedder 全面啟動——sparse-embedder 節點升級為已啟動狀態；新增 skill-router→sparse-embedder、memory→sparse-embedder 跨系統連線（hybrid_search 消費者接線）；Nightly Pipeline 新增 Step 8.7（IDF 重建 + 回填） |
| v1.38 | 2026-03-22 | L3-A2 Brain Mixin 拆分：brain 節點拆分為 core + 5 Mixin 子模組 + brain_types 共享型別；agent 群組新增 `brain-prompt-builder`（system prompt 建構, 1668 行）、`brain-dispatch`（任務分派, 1082 行）、`brain-observation`（觀察與演化, 2003 行）、`brain-p3-fusion`（P3 融合與決策層, 948 行）、`brain-tools`（LLM 呼叫與 session 管理, 966 行）、`brain-types`（共享 dataclass: DecisionSignal, P3FusionSignal）6 個節點（+6）；新增 6 條 internal 連線；184 節點 379 連線 |
| v1.37 | 2026-03-22 | Brain 三層治療：agent 群組新增 `chat-context`（ChatContext dataclass 輕量對話上下文，r=0.7）、`deterministic-router`（確定性任務分解器取代 LLM Orchestrator，r=1.0）2 個節點（+2）；新增 2 條 internal 連線（brain→chat-context 對話上下文封裝、brain→deterministic-router 確定性任務分解）；同步 persistence-contract v1.29（PulseDB 新增 orchestrator_calls 表）、joint-map v1.34（#35 orchestrator_calls）；178 節點 373 連線 |
| v1.36 | 2026-03-22 | 使用者節點精細化：channel 群組 `user` 拆分為 `zeal`（CORE 主人，r=2.0）、`verified-user`（VERIFIED 動態配對，r=1.2）、`external-user`（EXTERNAL 群組外部成員，r=1.4）三節點（+2 淨增，user→3）；補上遺漏的 `discord` 節點（r=1.2，+1）；flow 連線從 2 條（user→telegram/line）更新為 6 條（zeal→telegram/line、verified-user→telegram、external-user→telegram/line/discord）+ discord→gateway 1 條；async 連線新增 telegram→external-user、line→zeal 2 條；176 節點 369 連線 |
| v1.35 | 2026-03-22 | P0-P3 升級：Evolution Hub 新增 2 個 Skill 節點（system-health-check 系統健康自檢引擎、decision-tracker 決策歷史追蹤引擎）+ 2 條 internal 連線；新增 5 條 cross 連線（report-forge→knowledge-lattice 報告洞見結晶化、system-health-check→knowledge-lattice 健康結晶化、system-health-check→morphenix 修復提案、decision-tracker→knowledge-lattice 決策結晶化、decision-tracker→user-model 決策偏好）；173 節點 363 連線 |
| v1.34 | 2026-03-22 | 經驗諮詢閘門：新增 1 條 cross 連線 `brain → data-bus`（經驗回放搜尋 activity_log.search()）；無新增節點；171 節點 351 連線 |
| v1.32 | 2026-03-22 | Recommender 激活修復：`recommender` 節點半徑 0.7→0.9（幽靈模組→實際接線）；新增 1 條 cross 連線（recommender→crystal-store 結晶讀取）；brain.py `_recommender` 初始化；server.py API 改用常駐實例；169 節點 350 連線 |
| v1.31 | 2026-03-22 | Knowledge Lattice 持久層遷移：data 群組新增 `crystal-store` 節點（CrystalStore SQLite WAL 統一存取層，+1 節點）；新增 8 條連線——internal: data-bus→crystal-store Store 路由（+1）；cross: knowledge-lattice→crystal-store 結晶讀寫、crystal-actuator→crystal-store 結晶降級升級、nightly→crystal-store 結晶統計、evolution-velocity→crystal-store 結晶數量統計、guardian→crystal-store 結晶健康檢查、memory-reset→crystal-store 一鍵重置（+6）；decay: knowledge-lattice→crystal-actuator 描述更新 crystals.json→crystal.db（+0）；舊 JSON 檔案歸檔為 .bak；同步 persistence-contract v1.26、blast-radius v1.41、joint-map v1.29；169 節點 349 連線 |
| v1.30 | 2026-03-21 | 授權系統升級：gov 群組新增 `authorization` 節點（配對碼+工具授權+分級策略）；新增 5 條連線——internal: governance→authorization 授權引擎、authorization→security 三級策略查詢（+2）；cross: authorization→telegram 配對碼推送+inline keyboard、authorization→gateway 訊息泵授權回覆、authorization→mcp-server auth_status 查詢（+3）；持久化 `~/.museon/auth/`（allowlist.json + policy.json）；168 節點 341 連線 |
| v1.29 | 2026-03-21 | Skills 群組治理升級：新增 `hub` 欄位（9 種 Hub 分組：core/infra/thinking/market/business/creative/product/evolution/workflow）至 49 個 Skill Manifest；新增 Workflow Stage 結構化 YAML（3 個 workflow 含 stages + speed_paths）；新增治理文件 `skill-routing-governance.md`；plugin-registry v2.4（Hub 架構樹）；validate_connections.py v1.1（+2 驗證規則）；167 節點 336 連線（不變） |
| v1.28 | 2026-03-21 | 補全 skills 群組：7 Hub + 39 Skill 節點 + 91 條連線（從 3D 心智圖回補，修復拓撲⇄HTML 漂移）；167 節點 336 連線 |
| v1.27 | 2026-03-21 | Skill 鍛造膠合層修復：VectorBridge 新增 `index_all_skills()`（skills collection 全量索引，Gateway startup + Nightly Step 8.6 + API reindex）；Nightly Step 8.6 `skill_vector_reindex`；plugin-registry v2.3（+12 Skill 註冊）；49 個 Skill Manifest 補齊 memory/io 欄位；同步 blast-radius v1.33、joint-map v1.27、persistence-contract v1.24、memory-router v1.2 |
| v1.25 | 2026-03-21 | 軍師互動+思考前置區拓撲補全：agent 群組新增 `deep-think`、`roundtable`、`investment-masters` 3 個節點（+3）；新增 10 條連線——internal: brain→deep-think/roundtable/investment-masters（+3）；cross: deep-think→metacognition Phase 0 元認知、deep-think→persona-router 訊號分流→百合引擎、roundtable→knowledge-lattice 裁決軌跡結晶、investment-masters→knowledge-lattice 軍師會診結晶、investment-masters→skill-router DNA27 RC 親和觸發（+5）；配套百合引擎 27 單元測試 + Telegram 端到端驗證；124 節點 255 連線 |
| v1.24 | 2026-03-21 | A 區迭代 #1~#3 拓撲同步：data 群組新增 `sparse-embedder` 節點（BM25 稀疏向量，+1 節點）；新增 5 條連線——agent internal: brain→knowledge-lattice MemGPT recall_tiered() + GraphRAG Layer 2.5 recall_with_community()（+2）；data internal: data-bus→sparse-embedder Store 路由 + vector-index→sparse-embedder 混合檢索 RRF 融合（+2）；cross: sparse-embedder→qdrant 稀疏向量存儲（+1）；vector-index→qdrant 描述更新為「向量存儲（dense）」；121 節點 245 連線 |
| v1.22 | 2026-03-20 | 衰減生命週期補全：新增 `decay` 連線類型（色碼 #8B6E5A）+ 5 條衰減連線（結晶 RI、記憶 TTL、健康分數半衰期、推薦近因性、Synapse Decay）；同步 persistence-contract v1.21、blast-radius v1.28、joint-map v1.22 |
| v1.21 | 2026-03-20 | P3 前置交織融合——Step 5.5 前置多視角收集 + system_prompt 注入，視角從「追加」變「交織」，dendritic-fusion 連線擴展至 Step 5.5 |
| v1.20 | 2026-03-20 | P3 策略層並行融合落地：brain.py 新增 P3FusionSignal + Step 3.4 偵測 + Phase 4.5 執行管道 + 5 個 P3 方法；120 節點 240 連線不變；無新增節點；P3 Skill 層（orchestrator v3.0）+ P3 程式碼層（brain.py）雙層實作完整 |
| v1.19 | 2026-03-20 | P0-P3 思維引擎升級（純 Skill .md 認知行為變更，無新節點/連線）：deep-think v2.0（思考路徑可見化 P0 + 主動盲點提醒 P1 + 重大決策先問後答 P2）、query-clarity v2.0（主動觸發「你可能沒想到」P1）、orchestrator v3.0（並行融合模式 P3）、dna27 v2.2（回應合約對齊）；120 節點 240 連線（不變） |
| v1.18 | 2026-03-19 | P1-P3 PersonaRouter 全接線 + 四張藍圖同步：persona-router 節點半徑 1.0→1.1、proactive-bridge 節點半徑 1.1→1.2；新增 cross 連線 persona-router→proactive-bridge（象限決策結果回饋）；brain→proactive-bridge 連線描述更新為「推播 + 百合象限上下文注入」；版本統一為 v1.18（同步 blast-radius v1.24, persistence-contract v1.18, joint-map v1.18）；統計無變化；120 節點 240 連線 |
| v1.0 | 2026-03-14 | 初版建立，59 節點 91 連線 |
| v1.12 | 2026-03-17 | 軍師架構 Phase 0：data 群組新增 `lord-profile` 節點（+1 節點）；新增 2 條 cross 連線（brain→lord-profile 領域畫像寫入、lord-profile→persona-router 百合引擎讀取）；116 節點 220 連線 |
| v1.11 | 2026-03-17 | 3D 心智圖全面同步：nightly 群組標籤統一為「30+ 步」；3D 新增 `observatory`+`cognitive-receipt` 節點（+2）、+7 連線（認知可觀測性閉環）；修正 multi-agent-executor/response-synthesizer/flywheel-coordinator 群組歸屬 multiagent→agent；SYNC_META 升級 v1.10；115 節點 218 連線（3D）|
| v1.10 | 2026-03-17 | 認知可觀測性：gov 群組新增 `cognitive-receipt` 節點；doctor 群組新增 `observatory` 節點（+2 節點）；新增 7 條連線（governance→cognitive-receipt internal、footprint→cognitive-receipt internal、doctor→observatory internal、brain→footprint cross 認知追蹤、footprint→data-bus cross JSONL 寫入、observatory→footprint cross 讀取、observatory→service-health cross 健康狀態）；120 節點 240 連線 |
| v1.9 | 2026-03-17 | DNA-Inspired 品質回饋閉環：新增 3 條跨群組連線（metacognition→pulse-db 品質旗標寫入、morphenix→pulse-db 品質旗標讀取、response-synthesizer→multi-agent-executor DNA 交叉重組）；response-synthesizer 描述更新為「DNA 交叉重組合成」；118 節點 233 連線 |
| v1.14 | 2026-03-16 | Memory Reset 一鍵重置：doctor 群組新增 `memory-reset` 節點（+1 節點 +1 內部連線 doctor→memory-reset）；memory-reset 為 CLI 工具，涵蓋 25 個持久層的原子重置；3D 心智圖同步；統計修正（v1.9-v1.13 遺漏）；118 節點 230 連線 |
| v1.13 | 2026-03-16 | 五缺陷修復 3D 心智圖同步：新增 `blueprint-reader` 節點（data 群組）；新增 7 條連線（governor→immunity learn、governor→pulse-db incident、governor→dendritic-scorer immunity注入、blueprint-reader→doctor/surgery/morphenix 藍圖感知、nightly→blueprint-reader Step 30）；refractory 更新為「三態+半開」；system-audit 更新為「8層49項」；117 節點 229 連線 |
| v1.12 | 2026-03-16 | P5 斷路器半開 + Nightly 藍圖驗證：refractory 節點描述更新為「三態+半開試探」；nightly 新增 Step 30→blueprint-reader 連線（+1 連線） |
| v1.91 | 2026-04-06 | x-ray 透視引擎節點新增：product 群組新增 x-ray Skill 節點（三維根因透視，plugin，扇入=1 user，扇出=4：knowledge-lattice/dse/fix-verify/plan-engine）；新增 4 條 cross 連線；Product Hub 8→9；plugin-registry 82→83。213+7 節點，連線數 +4。同步 blast-radius v2.09、memory-router v1.31 |
| v1.90 | 2026-04-06 | telegram.py Skill 缺口/重鍛 Inline Keyboard + brain.py ctx.user_id 修復：telegram Skill 缺口提案升級為 Inline Keyboard 互動（新增 _send_skill_gap_proposal_with_keyboard()，4 個 callback：skill:gap_approve/gap_ignore/reforge_approve/reforge_ignore）；gap_approve/reforge_approve 寫入 skill_requests/ pending_dse_confirmed，gap_ignore/reforge_ignore 刪除 req；brain.py 修復 ctx.user_id→user_id（荒謬雷達+星座雷達靜默失敗）；新增 C-traits 提取注入 skill-router Layer 4。節點數不變（212+7），新增 telegram→skill-requests 讀寫路徑。同步 blast-radius v2.08、joint-map v1.75 |
| v1.89 | 2026-04-06 | Nightly 拆分 + e2e probe_health + skill_qa_gate bug 修復：nightly-pipeline 拆分為 7 Mixin（memory/morphenix/skill/identity/ecosystem/maintenance/persona）；brain.py 新增 probe_health() 方法；vital-signs e2e_flow 改用 probe_health()（扇入 0→1）；skill-qa-gate startswith bug 修復。統計：212 主節點 + 7 Mixin 子節點，連線數不變。同步 blast-radius v2.07、persistence-contract v1.58、joint-map v1.74 |
| v1.11 | 2026-03-16 | P1+P4 3D 心智圖同步：新增 telegram→brain async（P1 推送寫入 session）、fact-correction→proactive-bridge async + fact-correction→pulse async（P4 自省清洗）；112 節點 219 連線 |
| v1.10 | 2026-03-16 | P0 記憶事實覆寫：agent 群組新增 fact-correction 節點（+1 節點 +4 連線：brain→fact-correction internal、fact-correction→memory cross、fact-correction→vector-index cross、fact-correction→llm-router cross）；111 節點 211 連線 |
| v1.9 | 2026-03-16 | Phase 4 飛輪多代理實質化：multiagent 群組新增 multi-agent-executor、response-synthesizer、flywheel-coordinator 節點（+3 節點 +4 連線：brain→multi-agent-executor internal、brain→response-synthesizer internal、brain→flywheel-coordinator internal、multi-agent-executor→llm-router cross）；110 節點 207 連線 |
| v1.8 | 2026-03-16 | Phase 3 日記+群組ANIMA：soul-ring→diary-store 重命名；pulse 群組新增 group-session-proactive 節點（+1 節點 +4 連線）；107 節點 203 連線 |
| v1.7 | 2026-03-16 | Phase 2 八原語接線：agent 群組新增 primal-detector 節點（+1 節點 +2 連線：brain→primal-detector internal + primal-detector→vector-index cross）；106 節點 199 連線 |
| v1.6 | 2026-03-16 | Docker 沙盒驗證器上線：nightly 群組新增 morphenix-validator 節點（+1 節點 +2 內部連線）；105 節點 197 連線 |
| v1.5 | 2026-03-15 | DNA27 深度修復：移除幽靈節點 task-scheduler(pulse) + guardrails(gov)、新增 anima-mc-store + anima-tracker 到 pulse 群組、修正跨系統連線（+6 新連線 -3 幽靈連線）；104 節點 195 連線 |
| v1.4 | 2026-03-15 | 9.5 精度修復：data 群組新增 3 個 SQLite 子節點（pulse-db, group-context-db, workflow-state-db）+ 3 條 Store 路由連線；104 節點 191 連線 |
| v1.3 | 2026-03-15 | 全面覆蓋修復：新增 installer 群組(5節點)；nightly 擴充+5子節點；tools 擴充+7節點(含federation)；gov 擴充+3子節點；channel 加 mcp-server；新增 43 條連線，總計 101 節點 188 連線 |
| v1.2 | 2026-03-15 | 藍圖完整性修復：新增 evolution(10節點)、tools(3節點) 群組；agent 群組加 onboarding+multiagent；gov 群組加 guardian+security；新增 37 條連線 |
| v1.1 | 2026-03-15 | 新增 DataBus/DataWatchdog、data 群組 Hub 化、Nightly 29 步 |
