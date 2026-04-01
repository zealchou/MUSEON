#!/usr/bin/env python3
"""
inject_health_meta.py
為 MUSEON 3D HTML 的每個節點注入：
  - path  : 對應的 Python 檔案路徑（或 Skill 路徑）
  - fi    : fan_in 數字（來自 topology_report.json）
並替換 doHealthCheck() 為可直接貼給 Claude Code 執行的健康檢查指令。
"""

import json, re
from pathlib import Path

ROOT    = Path("/Users/ZEALCHOU/MUSEON")
HTML    = ROOT / "data/workspace/MUSEON_3d_mindmap.html"
REPORT  = ROOT / "scripts/topology_report.json"
SRC     = "src/museon"
SKILLS  = "~/.claude/skills"

# ──────────────────────────────────────────────
# 1.  node_id → 相對路徑映射表
#     留空字串 = 外部服務 / 概念節點，不需要路徑
# ──────────────────────────────────────────────
PATH_MAP = {
    # ── Channel / Gateway ──
    "gateway":              f"{SRC}/gateway/server.py",
    "brain-worker":         f"{SRC}/gateway/brain_worker.py",
    "cron":                 f"{SRC}/gateway/cron.py",
    "cron-registry":        f"{SRC}/gateway/cron_registry.py",
    "routes-api":           f"{SRC}/gateway/routes_api.py",
    "telegram-pump":        f"{SRC}/gateway/telegram_pump.py",
    "interaction-queue":    f"{SRC}/gateway/interaction.py",
    "message-queue-store":  f"{SRC}/gateway/message_queue_store.py",
    "session":              f"{SRC}/gateway/session.py",
    "session-cleanup":      f"{SRC}/gateway/session_cleanup.py",
    "security-gw":          f"{SRC}/gateway/security.py",
    "telegram":             f"{SRC}/channels/telegram.py",
    "discord":              f"{SRC}/channels/discord.py",
    "webhook":              f"{SRC}/channels/webhook.py",
    "email-ch":             f"{SRC}/channels/email.py",
    "slack":                f"{SRC}/channels/slack.py",
    "mqtt":                 f"{SRC}/channels/mqtt.py",
    "community":            f"{SRC}/channels/community.py",
    "mcp-server":           f"{SRC}/mcp_server.py",

    # ── Agent / Brain ──
    "brain":                f"{SRC}/agent/brain.py",
    "brain-deep":           f"{SRC}/agent/brain_deep.py",
    "brain-fast":           f"{SRC}/agent/brain_fast.py",
    "brain-dispatch":       f"{SRC}/agent/brain_dispatch.py",
    "brain-observation":    f"{SRC}/agent/brain_observation.py",
    "brain-prompt-builder": f"{SRC}/agent/brain_prompt_builder.py",
    "brain-tool-loop":      f"{SRC}/agent/brain_tool_loop.py",
    "brain-tools":          f"{SRC}/agent/brain_tools.py",
    "brain-types":          f"{SRC}/agent/brain_types.py",
    "chat-context":         f"{SRC}/agent/chat_context.py",
    "dispatch":             f"{SRC}/agent/dispatch.py",
    "agent-registry":       f"{SRC}/agent/agent_registry.py",
    "crystal-actuator":     f"{SRC}/agent/crystal_actuator.py",
    "crystal-store":        f"{SRC}/agent/crystal_store.py",
    "deterministic-router": f"{SRC}/agent/deterministic_router.py",
    "drift-detector":       f"{SRC}/agent/drift_detector.py",
    "eval-engine":          f"{SRC}/agent/eval_engine.py",
    "intuition":            f"{SRC}/agent/intuition.py",
    "kernel-guard":         f"{SRC}/agent/kernel_guard.py",
    "knowledge-lattice":    f"{SRC}/agent/knowledge_lattice.py",
    "mcp-connector":        f"{SRC}/agent/mcp_connector.py",
    "metacognition":        f"{SRC}/agent/metacognition.py",
    "pdr-council":          f"{SRC}/agent/pdr_council.py",
    "pdr-params":           f"{SRC}/agent/pdr_params.py",
    "persona-router":       f"{SRC}/agent/persona_router.py",
    "plan-engine":          f"{SRC}/agent/plan_engine.py",
    "primal-detector":      f"{SRC}/agent/primal_detector.py",
    "rc-affinity":          f"{SRC}/agent/rc_affinity_loader.py",
    "rc-utterances":        f"{SRC}/agent/rc_utterances.py",
    "recommender":          f"{SRC}/agent/recommender.py",
    "reflex-router":        f"{SRC}/agent/reflex_router.py",
    "safety-anchor":        f"{SRC}/agent/safety_anchor.py",
    "safety-clusters":      f"{SRC}/agent/safety_clusters.py",
    "signal-skill-map":     f"{SRC}/agent/signal_skill_map.py",
    "skill-router":         f"{SRC}/agent/skill_router.py",
    "skills-py":            f"{SRC}/agent/skills.py",
    "soul-ring":            f"{SRC}/agent/soul_ring.py",
    "sub-agent":            f"{SRC}/agent/sub_agent.py",
    "token-optimizer":      f"{SRC}/agent/token_optimizer.py",
    "tool-schemas":         f"{SRC}/agent/tool_schemas.py",
    "tools-agent":          f"{SRC}/agent/tools.py",
    # ── Memory ──
    "memory":               f"{SRC}/memory/memory_manager.py",
    "memory-gate":          f"{SRC}/memory/memory_gate.py",
    "memory-graph":         f"{SRC}/memory/memory_graph.py",
    "memory-reflector":     f"{SRC}/memory/memory_reflector.py",
    "adaptive-decay":       f"{SRC}/memory/adaptive_decay.py",
    "chromosome-index":     f"{SRC}/memory/chromosome_index.py",
    "quality-gate":         f"{SRC}/memory/quality_gate.py",
    "storage-backend":      f"{SRC}/memory/storage_backend.py",
    "store":                f"{SRC}/memory/store.py",
    "diary-store":          f"{SRC}/memory/store.py",

    # ── Pulse ──
    "pulse":                f"{SRC}/pulse/pulse_engine.py",
    "anima-changelog":      f"{SRC}/pulse/anima_changelog.py",
    "anima-mc-store":       f"{SRC}/pulse/anima_mc_store.py",
    "anima-tracker":        f"{SRC}/pulse/anima_tracker.py",
    "async-write-queue":    f"{SRC}/pulse/async_write_queue.py",
    "autonomous-queue":     f"{SRC}/pulse/autonomous_queue.py",
    "commitment-tracker":   f"{SRC}/pulse/commitment_tracker.py",
    "exploration-report":   f"{SRC}/pulse/exploration_report.py",
    "explorer":             f"{SRC}/pulse/explorer.py",
    "group-digest":         f"{SRC}/pulse/group_digest.py",
    "heartbeat":            f"{SRC}/pulse/heartbeat_engine.py",
    "heartbeat-focus":      f"{SRC}/pulse/heartbeat_focus.py",
    "micro-pulse":          f"{SRC}/pulse/micro_pulse.py",
    "proactive-bridge":     f"{SRC}/pulse/proactive_bridge.py",
    "proactive-dispatcher": f"{SRC}/pulse/proactive_dispatcher.py",
    "push-budget":          f"{SRC}/pulse/push_budget.py",
    "signal-keywords":      f"{SRC}/pulse/signal_keywords.py",
    "silent-digestion":     f"{SRC}/pulse/silent_digestion.py",
    "pulse-db":             f"{SRC}/pulse/pulse_db.py",
    "pulse-intervention":   f"{SRC}/pulse/pulse_intervention.py",
    "token-budget":         f"{SRC}/pulse/token_budget.py",

    # ── Governance ──
    "governance":           f"{SRC}/governance/governor.py",
    "governor":             f"{SRC}/governance/governor.py",
    "anima-bridge":         f"{SRC}/governance/anima_bridge.py",
    "autonomic":            f"{SRC}/governance/autonomic.py",
    "bulkhead":             f"{SRC}/governance/bulkhead.py",
    "context":              f"{SRC}/governance/context.py",
    "dendritic-scorer":     f"{SRC}/governance/dendritic_scorer.py",
    "footprint":            f"{SRC}/governance/footprint.py",
    "gateway-lock":         f"{SRC}/governance/gateway_lock.py",
    "group-context-db":     f"{SRC}/governance/group_context.py",
    "immune-memory":        f"{SRC}/governance/immune_memory.py",
    "immune-research":      f"{SRC}/governance/immune_research.py",
    "immunity":             f"{SRC}/governance/immunity.py",
    "multi-tenant":         f"{SRC}/governance/multi_tenant.py",
    "perception":           f"{SRC}/governance/perception.py",
    "pid-alive":            f"{SRC}/governance/pid_alive.py",
    "preflight":            f"{SRC}/governance/preflight.py",
    "refractory":           f"{SRC}/governance/refractory.py",
    "regulation":           f"{SRC}/governance/regulation.py",
    "response-guard":       f"{SRC}/governance/response_guard.py",
    "service-health":       f"{SRC}/governance/service_health.py",
    "telegram-guard":       f"{SRC}/governance/telegram_guard.py",
    "vital-signs":          f"{SRC}/governance/vital_signs.py",

    # ── Doctor ──
    "doctor":               f"{SRC}/doctor/system_audit.py",
    "auto-repair":          f"{SRC}/doctor/auto_repair.py",
    "code-analyzer":        f"{SRC}/doctor/code_analyzer.py",
    "diagnosis-pipeline":   f"{SRC}/doctor/diagnosis_pipeline.py",
    "fan-in-scanner":       f"{SRC}/doctor/fan_in_scanner.py",
    "field-scanner":        f"{SRC}/doctor/field_scanner.py",
    "finding":              f"{SRC}/doctor/finding.py",
    "health-check":         f"{SRC}/doctor/health_check.py",
    "log-analyzer":         f"{SRC}/doctor/log_analyzer.py",
    "memory-reset":         f"{SRC}/doctor/memory_reset.py",
    "musedoc":              f"{SRC}/doctor/musedoc.py",
    "museoff":              f"{SRC}/doctor/museoff.py",
    "museqa":               f"{SRC}/doctor/museqa.py",
    "museworker":           f"{SRC}/doctor/museworker.py",
    "doctor-notify":        f"{SRC}/doctor/notify.py",
    "observatory":          f"{SRC}/doctor/self_diagnosis.py",
    "self-diagnosis":       f"{SRC}/doctor/self_diagnosis.py",
    "shared-board":         f"{SRC}/doctor/shared_board.py",
    "surgery":              f"{SRC}/doctor/surgeon.py",
    "surgery-log":          f"{SRC}/doctor/surgery_log.py",
    "system-audit":         f"{SRC}/doctor/system_audit.py",
    "guardian":             f"{SRC}/guardian/daemon.py",
    "liveness":             f"{SRC}/doctor/probes/liveness.py",
    "readiness":            f"{SRC}/doctor/probes/readiness.py",

    # ── LLM ──
    "llm-adapters":         f"{SRC}/llm/adapters.py",
    "llm-router":           f"{SRC}/llm/router.py",
    "budget-mgr":           f"{SRC}/llm/budget.py",
    "llm-cache":            f"{SRC}/cache/context_cache_builder.py",
    "rate-limit":           f"{SRC}/llm/rate_limiter.py",

    # ── Core ──
    "event-bus":            f"{SRC}/core/event_bus.py",
    "data-bus":             f"{SRC}/core/data_bus.py",
    "activity-logger":      f"{SRC}/core/activity_logger.py",
    "blueprint-reader":     f"{SRC}/core/blueprint_reader.py",
    "data-watchdog":        f"{SRC}/core/data_watchdog.py",
    "module-registry":      f"{SRC}/core/module_registry.py",
    "skill-manager":        f"{SRC}/core/skill_manager.py",

    # ── Evolution ──
    "evolution":            f"{SRC}/evolution/feedback_loop.py",
    "digest-engine":        f"{SRC}/evolution/digest_engine.py",
    "evolution-velocity":   f"{SRC}/evolution/evolution_velocity.py",
    "feedback-loop":        f"{SRC}/evolution/feedback_loop.py",
    "intention-radar":      f"{SRC}/evolution/intention_radar.py",
    "outward-trigger":      f"{SRC}/evolution/outward_trigger.py",
    "parameter-tuner":      f"{SRC}/evolution/parameter_tuner.py",
    "skill-synapse":        f"{SRC}/evolution/skill_synapse.py",
    "tool-muscle":          f"{SRC}/evolution/tool_muscle.py",
    "trigger-weights":      f"{SRC}/evolution/trigger_weights.py",
    "wee":                  f"{SRC}/evolution/wee_engine.py",

    # ── Nightly ──
    "nightly":              f"{SRC}/nightly/nightly_pipeline.py",
    "context-cache-builder":f"{SRC}/cache/context_cache_builder.py",
    "curiosity-router":     f"{SRC}/nightly/curiosity_router.py",
    "exploration-bridge":   f"{SRC}/nightly/exploration_bridge.py",
    "morphenix":            f"{SRC}/nightly/morphenix_executor.py",
    "morphenix-validator":  f"{SRC}/nightly/morphenix_validator.py",
    "periodic-cycles":      f"{SRC}/nightly/periodic_cycles.py",
    "skill-forge-scout":    f"{SRC}/nightly/skill_forge_scout.py",
    "skill-scout":          f"{SRC}/nightly/skill_scout.py",
    "pipeline-dag":         f"{SRC}/nightly/pipeline_dag.py",
    "morphenix-standards":  f"{SRC}/nightly/morphenix_standards.py",
    "forge":                f"{SRC}/nightly/forge.py",
    "fusion":               f"{SRC}/nightly/fusion.py",
    "nightly-job":          f"{SRC}/nightly/job.py",
    "nightly-batch":        f"{SRC}/nightly/batch.py",
    "optimize":             f"{SRC}/nightly/optimize.py",
    "business-case":        f"{SRC}/nightly/business_case.py",
    "course-generator":     f"{SRC}/nightly/course_generator.py",

    # ── Registry / Workflow ──
    "registry":             f"{SRC}/registry/registry_manager.py",
    "skills-registry":      f"{SRC}/registry/registry_manager.py",
    "workflow-engine":      f"{SRC}/workflow/workflow_engine.py",
    "workflow-state-db":    f"{SRC}/workflow/workflow_engine.py",
    "soft-workflow":        f"{SRC}/workflow/soft_workflow.py",
    "workflow-executor":    f"{SRC}/workflow/workflow_executor.py",
    "workflow-scheduler":   f"{SRC}/workflow/workflow_scheduler.py",

    # ── Learning ──
    "insight-extractor":    f"{SRC}/learning/insight_extractor.py",

    # ── Security ──
    "security":             f"{SRC}/security/audit.py",
    "sandbox":              f"{SRC}/security/execution_sandbox.py",
    "skill-scanner":        f"{SRC}/security/skill_scanner.py",
    "trusted-bins":         f"{SRC}/security/trusted_bins.py",
    "sanitizer":            f"{SRC}/security/sanitizer.py",
    "env-security":         f"{SRC}/security/env_security.py",

    # ── Tools ──
    "dify-scheduler":       f"{SRC}/tools/dify_scheduler.py",
    "image-gen":            f"{SRC}/tools/image_gen.py",
    "mcp-dify":             f"{SRC}/tools/mcp_dify.py",
    "rss-aggregator":       f"{SRC}/tools/rss_aggregator.py",
    "tool-discovery":       f"{SRC}/tools/tool_discovery.py",
    "tool-registry":        f"{SRC}/tools/tool_registry.py",
    "voice-clone":          f"{SRC}/tools/voice_clone.py",
    "zotero-bridge":        f"{SRC}/tools/zotero_bridge.py",

    # ── Vector ──
    "vector-index":         f"{SRC}/vector/vector_bridge.py",
    "vector-bridge":        f"{SRC}/vector/vector_bridge.py",
    "embedder":             f"{SRC}/vector/embedder.py",
    "sparse-embedder":      f"{SRC}/vector/sparse_embedder.py",

    # ── Billing / Onboarding ──
    "billing":              f"{SRC}/billing/trust_points.py",
    "onboarding":           f"{SRC}/onboarding/ceremony.py",
    "multiagent":           f"{SRC}/multiagent/multi_agent_executor.py",
    "multi-agent-executor": f"{SRC}/multiagent/multi_agent_executor.py",
    "context-switch":       f"{SRC}/multiagent/context_switch.py",
    "okr-router":           f"{SRC}/multiagent/okr_router.py",
    "response-synthesizer": f"{SRC}/multiagent/response_synthesizer.py",
    "flywheel-coordinator": f"{SRC}/multiagent/multi_agent_executor.py",
    "dispatcher":           f"{SRC}/agent/dispatch.py",
    "thinker":              f"{SRC}/agent/brain_deep.py",
    "worker":               f"{SRC}/agent/sub_agent.py",
    "fact-correction":      f"{SRC}/agent/metacognition.py",

    # ── Skills (Claude Skills) ──
    "acsf":                      f"{SKILLS}/acsf/SKILL.md",
    "aesthetic-sense":           f"{SKILLS}/aesthetic-sense/SKILL.md",
    "brand-identity":            f"{SKILLS}/brand-identity/SKILL.md",
    "business-12":               f"{SKILLS}/business-12/SKILL.md",
    "c15":                       f"{SKILLS}/c15/SKILL.md",
    "consultant-communication":  f"{SKILLS}/consultant-communication/SKILL.md",
    "decision-tracker":          f"{SKILLS}/decision-tracker/SKILL.md",
    "dharma":                    f"{SKILLS}/dharma/SKILL.md",
    "dse":                       f"{SKILLS}/dse/SKILL.md",
    "env-radar":                 f"{SKILLS}/env-radar/SKILL.md",
    "esg-architect-pro":         f"{SKILLS}/esg-architect-pro/SKILL.md",
    "gap":                       f"{SKILLS}/gap/SKILL.md",
    "group-meeting-notes":       f"{SKILLS}/group-meeting-notes/SKILL.md",
    "human-design-blueprint":    f"{SKILLS}/human-design-blueprint/SKILL.md",
    "info-architect":            f"{SKILLS}/info-architect/SKILL.md",
    "market-core":               f"{SKILLS}/market-core/SKILL.md",
    "market-crypto":             f"{SKILLS}/market-crypto/SKILL.md",
    "market-equity":             f"{SKILLS}/market-equity/SKILL.md",
    "market-macro":              f"{SKILLS}/market-macro/SKILL.md",
    "master-strategy":           f"{SKILLS}/master-strategy/SKILL.md",
    "meeting-intelligence":      f"{SKILLS}/meeting-intelligence/SKILL.md",
    "meta-learning":             f"{SKILLS}/meta-learning/SKILL.md",
    "novel-craft":               f"{SKILLS}/novel-craft/SKILL.md",
    "orchestrator":              f"{SKILLS}/orchestrator/SKILL.md",
    "pdeif":                     f"{SKILLS}/pdeif/SKILL.md",
    "philo-dialectic":           f"{SKILLS}/philo-dialectic/SKILL.md",
    "qa-auditor":                f"{SKILLS}/qa-auditor/SKILL.md",
    "query-clarity":             f"{SKILLS}/query-clarity/SKILL.md",
    "report-forge":              f"{SKILLS}/report-forge/SKILL.md",
    "resonance":                 f"{SKILLS}/resonance/SKILL.md",
    "risk-matrix":               f"{SKILLS}/risk-matrix/SKILL.md",
    "sandbox-lab":               f"{SKILLS}/sandbox-lab/SKILL.md",
    "sentiment-radar":           f"{SKILLS}/sentiment-radar/SKILL.md",
    "shadow":                    f"{SKILLS}/shadow/SKILL.md",
    "ssa-consultant":            f"{SKILLS}/ssa-consultant/SKILL.md",
    "storytelling-engine":       f"{SKILLS}/storytelling-engine/SKILL.md",
    "system-health-check":       f"{SKILLS}/system-health-check/SKILL.md",
    "tantra":                    f"{SKILLS}/tantra/SKILL.md",
    "text-alchemy":              f"{SKILLS}/text-alchemy/SKILL.md",
    "user-model":                f"{SKILLS}/user-model/SKILL.md",
    "workflow-ai-deployment":    f"{SKILLS}/workflow-ai-deployment/SKILL.md",
    "workflow-investment-analysis": f"{SKILLS}/workflow-investment-analysis/SKILL.md",
    "workflow-svc-brand-marketing": f"{SKILLS}/workflow-svc-brand-marketing/SKILL.md",
    "xmodel":                    f"{SKILLS}/xmodel/SKILL.md",
    "deep-think":                f"{SKILLS}/deep-think/SKILL.md",
    "roundtable":                f"{SKILLS}/roundtable/SKILL.md",
    "investment-masters":        f"{SKILLS}/investment-masters/SKILL.md",

    # ── 概念節點（無路徑）──
    "zeal": "", "external-user": "", "verified-user": "",
    "lord-profile": "data/_system/lord_profile.json",
    "anthropic-api": "", "fetch-mcp": "", "firecrawl": "",
    "playwright-mcp": "", "qdrant": "", "searxng": "",
    "skills-business-hub": "", "skills-creative-hub": "",
    "skills-evolution-hub": "", "skills-market-hub": "",
    "skills-product-hub": "", "skills-thinking-hub": "",
    "skills-workflow-hub": "", "skill-counter": "",
}

# ──────────────────────────────────────────────
# 2.  fan_in 映射（node_id → 數字）
# ──────────────────────────────────────────────
report = json.loads(REPORT.read_text())
fi_by_module = {r["module"]: r["fan_in"] for r in report["fan_in_table"]}

# node_id → module 的逆向查找（用 PATH_MAP 的路徑反推）
def path_to_module(path_str):
    """src/museon/agent/brain.py → museon.agent.brain"""
    if not path_str or not path_str.startswith("src/"):
        return None
    p = path_str.replace("src/", "").replace(".py", "").replace("/", ".")
    return p

FI_MAP = {}
for nid, path in PATH_MAP.items():
    mod = path_to_module(path)
    if mod and mod in fi_by_module:
        FI_MAP[nid] = fi_by_module[mod]
    else:
        FI_MAP[nid] = 0

# ──────────────────────────────────────────────
# 3.  注入 path + fi 到 HTML nodes 陣列
# ──────────────────────────────────────────────
html = HTML.read_text(encoding="utf-8")

def escape_js(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")

def inject_node_fields(match):
    full = match.group(0)
    nid_m = re.search(r'\{id:"([^"]+)"', full)
    if not nid_m:
        return full
    nid = nid_m.group(1)

    path = PATH_MAP.get(nid, "")
    fi   = FI_MAP.get(nid, 0)

    # 已有 path/fi 就跳過（冪等）
    if 'path:' in full or ',fi:' in full:
        return full

    # 在結尾 } 前插入
    full = full.rstrip()
    if full.endswith("},"):
        full = full[:-2] + f',path:"{escape_js(path)}",fi:{fi}' + "},"
    elif full.endswith("}"):
        full = full[:-1] + f',path:"{escape_js(path)}",fi:{fi}' + "}"
    return full

# 節點行格式：  {id:"...", ...},
html_new = re.sub(
    r'  \{id:"[^"~][^}]*\}[,]?',
    inject_node_fields,
    html
)

# ──────────────────────────────────────────────
# 4.  替換 doHealthCheck() 函數
# ──────────────────────────────────────────────
NEW_HEALTH_FN = r"""window.doHealthCheck = function() {
  if (!selectedNode) return;
  const node = selectedNode;

  // 收集連線資訊（含 hub 子節點）
  const outLinks = [], inLinks = [];
  links.forEach(l => {
    const src = typeof l.source === 'object' ? l.source.id : l.source;
    const tgt = typeof l.target === 'object' ? l.target.id : l.target;
    if (src === node.id) outLinks.push({...l, source: src, target: tgt});
    if (tgt === node.id) inLinks.push({...l, source: src, target: tgt});
  });
  if (node.hub) {
    nodes.filter(n => n.p === node.id).forEach(kid => {
      links.forEach(l => {
        const src = typeof l.source === 'object' ? l.source.id : l.source;
        const tgt = typeof l.target === 'object' ? l.target.id : l.target;
        if (src === kid.id) outLinks.push({...l, source: src, target: tgt});
        if (tgt === kid.id) inLinks.push({...l, source: src, target: tgt});
      });
    });
  }

  // 安全分級
  const fi = node.fi || 0;
  const safety = fi >= 40 ? '🔴 禁區' : fi >= 10 ? '🟠 紅區' : fi >= 2 ? '🟡 黃區' : '🟢 綠區';

  // 呼叫方（輸入方）列表
  const callerLines = inLinks.slice(0,12).map(l => {
    const srcLabel = nodeMap[l.source]?.label || l.source;
    const lbl = l.label ? `（${l.label.substring(0,40)}）` : '';
    return `  • ${srcLabel}${lbl}`;
  }).join('\n');

  // 被呼叫方（輸出方）列表
  const calleeLines = outLinks.slice(0,12).map(l => {
    const tgtLabel = nodeMap[l.target]?.label || l.target;
    const lbl = l.label ? `（${l.label.substring(0,40)}）` : '';
    return `  • ${tgtLabel}${lbl}`;
  }).join('\n');

  // 路徑說明
  const pathLine = node.path
    ? `路徑: ${node.path}`
    : `路徑: （概念節點，無對應原始碼）`;

  const isSkill = node.path && node.path.includes('.claude/skills');
  const checkSteps = isSkill
    ? `請：
① 讀取上方路徑的 SKILL.md，確認 triggers / output_format / connects_to 定義完整
② 確認此 Skill 在 plugin-registry 中已正確登錄
③ 確認 memory-router.md 中有對應的記憶流向規則
④ 回報：✅ 定義完整 / ⚠️ 缺漏（列出問題）`
    : `請：
① 讀取上方路徑的檔案，列出所有 public class / function（含參數簽名）
② 逐一確認「呼叫我的模組」的 import 路徑存在、參數匹配
③ 逐一確認「我呼叫的模組」的介面存在且未改變
④ grep ~/MUSEON/logs/ 確認此模組無 ERROR / WARNING
⑤ 確認此模組的資料輸入格式與輸出格式符合 docs/joint-map.md 的約定
⑥ 回報：✅ 健康 / ⚠️ 有問題（列出問題與行號）`;

  const cmd = [
    `/health [${node.label}]`,
    `模組：${node.label}（${node.zh || ''}）`,
    pathLine,
    `安全分級：${safety}（fan_in=${fi}）`,
    `所屬群組：${GN[node.group] || node.group}`,
    ``,
    `呼叫我的模組（${inLinks.length}）：`,
    callerLines || `  （無）`,
    ``,
    `我呼叫的模組（${outLinks.length}）：`,
    calleeLines || `  （無）`,
    ``,
    checkSteps,
  ].join('\n');

  navigator.clipboard.writeText(cmd).then(() => {
    const btn = document.getElementById('i-health-btn');
    btn.textContent = '✓ 已複製';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = '健康檢查'; btn.classList.remove('copied'); }, 2000);
  });

  // 計數
  incrementHealth(node.id);
  [...new Set([...inLinks.map(l=>l.source), ...outLinks.map(l=>l.target)])]
    .filter(id => id !== node.id)
    .forEach(id => incrementHealth(id));

  // 更新 info panel
  const health = getNodeHealth(node.id);
  const healthEl = document.getElementById('i-health');
  healthEl.textContent = '已檢查 ' + health.count + ' 次 · 上次：' + formatTimeAgo(health.lastCheck);
  healthEl.className = 'health-status';
  updateCoveragePanel();
  updateHealthBadges();
};"""

# 找到並替換舊函數
old_fn_pattern = r'window\.doHealthCheck\s*=\s*function\(\)\s*\{.*?\};'
html_new = re.sub(old_fn_pattern, NEW_HEALTH_FN, html_new, flags=re.DOTALL)

# ──────────────────────────────────────────────
# 5.  寫入
# ──────────────────────────────────────────────
HTML.write_text(html_new, encoding="utf-8")

# 驗證
node_count  = len(re.findall(r'\{id:"[^"~][^}]*\}', html_new))
link_count  = len(re.findall(r'\{source:"[^"]+",target:', html_new))
path_count  = html_new.count(',path:"')
fi_count    = html_new.count(',fi:')

print(f"✓ 完成")
print(f"  nodes={node_count}, links={link_count}")
print(f"  path 注入: {path_count} 個節點")
print(f"  fi   注入: {fi_count} 個節點")
print(f"  doHealthCheck() 已更新")
