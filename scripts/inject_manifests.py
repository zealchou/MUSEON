#!/usr/bin/env python3
"""
inject_manifests.py — 批次注入 Skill Manifest 到所有 SKILL.md
從 SKILL_MANIFESTS 映射表讀取每個 Skill 的 I/O 合約，
注入到 YAML frontmatter 中（保留原有 name + description）。

用法:
    .venv/bin/python scripts/inject_manifests.py --dry-run   # 只報告會改什麼
    .venv/bin/python scripts/inject_manifests.py --apply      # 實際注入
"""

import re
import sys
import argparse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "data" / "skills" / "native"
MIRROR_DIR = Path.home() / ".claude" / "skills"

# ═══════════════════════════════════════════════════════════════
# 完整 Skill Manifest 映射表（49 個 Skill）
# ═══════════════════════════════════════════════════════════════

SKILL_MANIFESTS: dict[str, dict[str, Any]] = {
    # ──────────── 常駐層（3 個）────────────
    "query-clarity": {
        "type": "always-on",
        "layer": "core-extension",
        "io": {
            "inputs": [
                {"from": "user", "field": "raw_question", "required": True},
            ],
            "outputs": [
                {"to": "deep-think", "field": "validated_question", "trigger": "always"},
                {"to": "roundtable", "field": "suggestion_to_start", "trigger": "conditional"},
            ],
        },
        "connects_to": ["roundtable", "user-model"],
        "memory": {
            "writes": [
                {"target": "user-model", "type": "profile_update", "condition": "問題習慣模式累積更新"},
            ],
            "reads": [
                {"source": "user-model", "field": "user_context"},
            ],
        },
    },
    "deep-think": {
        "type": "always-on",
        "layer": "core-extension",
        "io": {
            "inputs": [
                {"from": "query-clarity", "field": "validated_question", "required": True},
            ],
            "outputs": [
                {"to": "resonance", "field": "emotional_signal", "trigger": "conditional"},
                {"to": "dharma", "field": "transformation_signal", "trigger": "conditional"},
                {"to": "philo-dialectic", "field": "philosophical_signal", "trigger": "conditional"},
                {"to": "master-strategy", "field": "strategic_signal", "trigger": "conditional"},
                {"to": "user", "field": "thinking_trace", "trigger": "always"},
            ],
        },
        "connects_to": ["resonance", "dharma", "philo-dialectic", "master-strategy"],
        "memory": {
            "writes": [
                {"target": "user-model", "type": "profile_update", "condition": "Phase 0 訊號分流累積統計"},
                {"target": "knowledge-lattice", "type": "crystal", "condition": "信心水準高且有新洞見時"},
            ],
            "reads": [
                {"source": "user-model", "field": "thinking_preference"},
                {"source": "knowledge-lattice", "field": "related_crystals"},
            ],
        },
    },
    "c15": {
        "type": "always-on",
        "layer": "core-extension",
        "io": {
            "inputs": [
                {"from": "deep-think", "field": "validated_output", "required": False},
            ],
            "outputs": [
                {"to": "user", "field": "narrativized_output", "trigger": "always"},
            ],
        },
        "connects_to": ["text-alchemy"],
        "memory": {},
    },

    # ──────────── 前置與決策支援（1 個）────────────
    "roundtable": {
        "type": "on-demand",
        "layer": "analysis",
        "io": {
            "inputs": [
                {"from": "query-clarity", "field": "validated_question", "required": True},
                {"from": "user-model", "field": "user_profile", "required": False},
            ],
            "outputs": [
                {"to": "knowledge-lattice", "field": "verdict_with_dissent", "trigger": "always"},
                {"to": "user-model", "field": "decision_pattern", "trigger": "conditional"},
            ],
        },
        "connects_to": ["master-strategy", "shadow"],
        "memory": {
            "writes": [
                {"target": "knowledge-lattice", "type": "crystal", "condition": "使用者做出仲裁決定時"},
                {"target": "user-model", "type": "profile_update", "condition": "從裁決推斷決策偏好"},
            ],
            "reads": [
                {"source": "user-model", "field": "user_profile"},
            ],
        },
    },

    # ──────────── 思維與轉化（5 個）────────────
    "resonance": {
        "type": "on-demand",
        "layer": "thinking",
        "io": {
            "inputs": [
                {"from": "deep-think", "field": "emotional_signal", "required": True},
            ],
            "outputs": [
                {"to": "dharma", "field": "emotional_state_ready", "trigger": "conditional"},
                {"to": "user", "field": "emotional_response", "trigger": "always"},
            ],
        },
        "connects_to": ["dharma"],
        "memory": {
            "writes": [
                {"target": "user-model", "type": "profile_update", "condition": "情緒模式累積更新"},
            ],
            "reads": [],
        },
    },
    "dharma": {
        "type": "on-demand",
        "layer": "thinking",
        "io": {
            "inputs": [
                {"from": "deep-think", "field": "transformation_signal", "required": True},
                {"from": "resonance", "field": "emotional_state_ready", "required": False},
            ],
            "outputs": [
                {"to": "knowledge-lattice", "field": "transformation_milestone", "trigger": "conditional"},
                {"to": "user", "field": "action_plan", "trigger": "always"},
            ],
        },
        "connects_to": ["resonance", "philo-dialectic"],
        "memory": {
            "writes": [
                {"target": "knowledge-lattice", "type": "crystal", "condition": "六步驟完成到 Align 時"},
            ],
            "reads": [],
        },
    },
    "philo-dialectic": {
        "type": "on-demand",
        "layer": "thinking",
        "io": {
            "inputs": [
                {"from": "deep-think", "field": "philosophical_signal", "required": True},
            ],
            "outputs": [
                {"to": "knowledge-lattice", "field": "concept_clarity", "trigger": "conditional"},
                {"to": "user", "field": "dialectic_result", "trigger": "always"},
            ],
        },
        "connects_to": ["dharma", "roundtable"],
        "memory": {
            "writes": [
                {"target": "knowledge-lattice", "type": "crystal", "condition": "思辨推演完成時"},
            ],
            "reads": [],
        },
    },
    "xmodel": {
        "type": "on-demand",
        "layer": "thinking",
        "io": {
            "inputs": [
                {"from": "user", "field": "stuck_problem", "required": True},
            ],
            "outputs": [
                {"to": "knowledge-lattice", "field": "multi_path_solutions", "trigger": "always"},
                {"to": "user", "field": "experiment_designs", "trigger": "always"},
            ],
        },
        "connects_to": ["pdeif", "business-12"],
        "memory": {
            "writes": [
                {"target": "knowledge-lattice", "type": "crystal", "condition": "多方案產出時"},
            ],
            "reads": [],
        },
    },
    "pdeif": {
        "type": "on-demand",
        "layer": "thinking",
        "io": {
            "inputs": [
                {"from": "user", "field": "goal_description", "required": True},
            ],
            "outputs": [
                {"to": "wee", "field": "reverse_path_design", "trigger": "conditional"},
                {"to": "user", "field": "convergence_plan", "trigger": "always"},
            ],
        },
        "connects_to": ["xmodel", "wee"],
        "memory": {
            "writes": [
                {"target": "wee", "type": "proficiency", "condition": "流程設計完成時"},
            ],
            "reads": [],
        },
    },

    # ──────────── 商業與戰略（4 個）────────────
    "business-12": {
        "type": "on-demand",
        "layer": "business",
        "io": {
            "inputs": [
                {"from": "user", "field": "business_problem", "required": True},
            ],
            "outputs": [
                {"to": "knowledge-lattice", "field": "business_diagnosis", "trigger": "always"},
                {"to": "user", "field": "action_plan", "trigger": "always"},
            ],
        },
        "connects_to": ["ssa-consultant", "brand-identity", "xmodel", "master-strategy"],
        "memory": {
            "writes": [
                {"target": "knowledge-lattice", "type": "crystal", "condition": "12 力診斷完成時"},
            ],
            "reads": [],
        },
    },
    "ssa-consultant": {
        "type": "on-demand",
        "layer": "business",
        "io": {
            "inputs": [
                {"from": "user", "field": "sales_scenario", "required": True},
            ],
            "outputs": [
                {"to": "knowledge-lattice", "field": "sales_strategy", "trigger": "always"},
                {"to": "user", "field": "consultative_plan", "trigger": "always"},
            ],
        },
        "connects_to": ["business-12", "master-strategy"],
        "memory": {
            "writes": [
                {"target": "knowledge-lattice", "type": "crystal", "condition": "顧問/教練流程完成時"},
            ],
            "reads": [],
        },
    },
    "master-strategy": {
        "type": "on-demand",
        "layer": "business",
        "io": {
            "inputs": [
                {"from": "user", "field": "strategic_scenario", "required": True},
                {"from": "deep-think", "field": "strategic_signal", "required": False},
            ],
            "outputs": [
                {"to": "knowledge-lattice", "field": "strategic_assessment", "trigger": "always"},
                {"to": "user", "field": "wargame_result", "trigger": "always"},
            ],
        },
        "connects_to": ["shadow", "roundtable", "business-12"],
        "memory": {
            "writes": [
                {"target": "knowledge-lattice", "type": "crystal", "condition": "沙盤推演完成時"},
            ],
            "reads": [],
        },
    },
    "shadow": {
        "type": "on-demand",
        "layer": "business",
        "io": {
            "inputs": [
                {"from": "user", "field": "interpersonal_scenario", "required": True},
            ],
            "outputs": [
                {"to": "knowledge-lattice", "field": "pattern_identification", "trigger": "always"},
                {"to": "user", "field": "defense_strategy", "trigger": "always"},
            ],
        },
        "connects_to": ["master-strategy", "roundtable"],
        "memory": {
            "writes": [
                {"target": "knowledge-lattice", "type": "crystal", "condition": "防禦/洞察分析完成時"},
            ],
            "reads": [],
        },
    },

    # ──────────── 語言與創作（4 個）────────────
    "text-alchemy": {
        "type": "on-demand",
        "layer": "language",
        "io": {
            "inputs": [
                {"from": "user", "field": "writing_task", "required": True},
            ],
            "outputs": [
                {"to": "storytelling-engine", "field": "narrative_task", "trigger": "conditional"},
                {"to": "novel-craft", "field": "fiction_task", "trigger": "conditional"},
                {"to": "consultant-communication", "field": "business_comm_task", "trigger": "conditional"},
                {"to": "user", "field": "styled_output", "trigger": "always"},
            ],
        },
        "connects_to": ["c15", "storytelling-engine", "novel-craft", "consultant-communication"],
        "memory": {},
    },
    "storytelling-engine": {
        "type": "on-demand",
        "layer": "language",
        "io": {
            "inputs": [
                {"from": "text-alchemy", "field": "narrative_task", "required": False},
                {"from": "user", "field": "story_request", "required": False},
            ],
            "outputs": [
                {"to": "user", "field": "narrative_structure", "trigger": "always"},
            ],
        },
        "connects_to": ["text-alchemy", "c15"],
        "memory": {},
    },
    "novel-craft": {
        "type": "on-demand",
        "layer": "language",
        "io": {
            "inputs": [
                {"from": "text-alchemy", "field": "fiction_task", "required": False},
                {"from": "user", "field": "fiction_request", "required": False},
            ],
            "outputs": [
                {"to": "user", "field": "literary_output", "trigger": "always"},
            ],
        },
        "connects_to": ["text-alchemy", "c15"],
        "memory": {},
    },
    "consultant-communication": {
        "type": "on-demand",
        "layer": "language",
        "io": {
            "inputs": [
                {"from": "text-alchemy", "field": "business_comm_task", "required": False},
                {"from": "orchestrator", "field": "execution_summary_request", "required": False},
                {"from": "user", "field": "communication_task", "required": False},
            ],
            "outputs": [
                {"to": "user", "field": "structured_output", "trigger": "always"},
            ],
        },
        "connects_to": ["text-alchemy", "orchestrator"],
        "memory": {},
    },

    # ──────────── 美感與品牌（2 個）────────────
    "aesthetic-sense": {
        "type": "on-demand",
        "layer": "aesthetic",
        "io": {
            "inputs": [
                {"from": "user", "field": "visual_output", "required": True},
            ],
            "outputs": [
                {"to": "user", "field": "aesthetic_audit", "trigger": "always"},
            ],
        },
        "connects_to": ["brand-identity"],
        "memory": {},
    },
    "brand-identity": {
        "type": "on-demand",
        "layer": "aesthetic",
        "io": {
            "inputs": [
                {"from": "user", "field": "brand_task", "required": True},
            ],
            "outputs": [
                {"to": "user", "field": "brand_assets", "trigger": "always"},
            ],
        },
        "connects_to": ["aesthetic-sense", "business-12"],
        "memory": {},
    },

    # ──────────── 元認知與學習（2 個）────────────
    "user-model": {
        "type": "on-demand",
        "layer": "meta",
        "io": {
            "inputs": [
                {"from": "query-clarity", "field": "question_patterns", "required": False},
                {"from": "deep-think", "field": "signal_statistics", "required": False},
                {"from": "roundtable", "field": "decision_pattern", "required": False},
                {"from": "resonance", "field": "emotional_pattern", "required": False},
                {"from": "eval-engine", "field": "satisfaction_proxy", "required": False},
                {"from": "wee", "field": "proficiency_update", "required": False},
                {"from": "knowledge-lattice", "field": "expertise_dimension", "required": False},
            ],
            "outputs": [
                {"to": "query-clarity", "field": "user_context", "trigger": "always"},
                {"to": "deep-think", "field": "thinking_preference", "trigger": "always"},
                {"to": "roundtable", "field": "user_profile", "trigger": "on-request"},
            ],
        },
        "connects_to": ["eval-engine", "knowledge-lattice", "wee"],
        "memory": {
            "writes": [
                {"target": "user-model", "type": "profile_update", "condition": "每次對話被動更新"},
            ],
            "reads": [
                {"source": "knowledge-lattice", "field": "domain_crystals"},
                {"source": "wee", "field": "workflow_proficiency"},
            ],
        },
    },
    "meta-learning": {
        "type": "on-demand",
        "layer": "meta",
        "io": {
            "inputs": [
                {"from": "user", "field": "learning_task", "required": True},
            ],
            "outputs": [
                {"to": "knowledge-lattice", "field": "learning_strategy", "trigger": "conditional"},
                {"to": "user", "field": "learning_plan", "trigger": "always"},
            ],
        },
        "connects_to": ["knowledge-lattice"],
        "memory": {
            "writes": [
                {"target": "knowledge-lattice", "type": "crystal", "condition": "學習模式分析完成時"},
            ],
            "reads": [],
        },
    },

    # ──────────── 演化與治理（7 個）────────────
    "morphenix": {
        "type": "on-demand",
        "layer": "evolution",
        "io": {
            "inputs": [
                {"from": "eval-engine", "field": "quality_trends", "required": False},
                {"from": "env-radar", "field": "external_signals", "required": False},
                {"from": "sandbox-lab", "field": "experiment_results", "required": False},
                {"from": "qa-auditor", "field": "audit_report", "required": False},
            ],
            "outputs": [
                {"to": "user", "field": "evolution_proposals", "trigger": "always"},
            ],
        },
        "connects_to": ["plugin-registry", "eval-engine", "env-radar"],
        "memory": {
            "writes": [
                {"target": "morphenix", "type": "proposal", "condition": "結晶提案流程觸發時"},
            ],
            "reads": [
                {"source": "eval-engine", "field": "blindspot_radar"},
            ],
        },
    },
    "wee": {
        "type": "on-demand",
        "layer": "evolution",
        "io": {
            "inputs": [
                {"from": "orchestrator", "field": "execution_trace", "required": False},
                {"from": "pdeif", "field": "reverse_path_design", "required": False},
                {"from": "user", "field": "workflow_task", "required": False},
            ],
            "outputs": [
                {"to": "user-model", "field": "proficiency_update", "trigger": "conditional"},
                {"to": "knowledge-lattice", "field": "workflow_lessons", "trigger": "conditional"},
                {"to": "user", "field": "proficiency_dashboard", "trigger": "on-request"},
            ],
        },
        "connects_to": ["pdeif", "xmodel", "morphenix", "orchestrator"],
        "memory": {
            "writes": [
                {"target": "wee", "type": "proficiency", "condition": "工作流執行教練迴路完成時"},
                {"target": "knowledge-lattice", "type": "crystal", "condition": "工作流教訓萃取時"},
            ],
            "reads": [],
        },
    },
    "knowledge-lattice": {
        "type": "on-demand",
        "layer": "evolution",
        "io": {
            "inputs": [
                {"from": "roundtable", "field": "verdict_with_dissent", "required": False},
                {"from": "investment-masters", "field": "master_verdict", "required": False},
                {"from": "market-core", "field": "bull_bear_analysis", "required": False},
                {"from": "master-strategy", "field": "strategic_assessment", "required": False},
                {"from": "business-12", "field": "business_diagnosis", "required": False},
                {"from": "dharma", "field": "transformation_milestone", "required": False},
                {"from": "deep-think", "field": "key_insight", "required": False},
                {"from": "xmodel", "field": "multi_path_solutions", "required": False},
                {"from": "dse", "field": "feasibility_report", "required": False},
                {"from": "shadow", "field": "pattern_identification", "required": False},
                {"from": "philo-dialectic", "field": "concept_clarity", "required": False},
                {"from": "wee", "field": "workflow_lessons", "required": False},
            ],
            "outputs": [
                {"to": "deep-think", "field": "related_crystals", "trigger": "always"},
                {"to": "user-model", "field": "expertise_dimension", "trigger": "conditional"},
                {"to": "user", "field": "crystal_recall", "trigger": "on-request"},
            ],
        },
        "connects_to": ["user-model", "wee", "morphenix", "meta-learning"],
        "memory": {
            "writes": [
                {"target": "knowledge-lattice", "type": "crystal", "condition": "結晶萃取觸發時"},
            ],
            "reads": [],
        },
    },
    "eval-engine": {
        "type": "on-demand",
        "layer": "evolution",
        "io": {
            "inputs": [
                {"from": "user", "field": "response_feedback", "required": False},
            ],
            "outputs": [
                {"to": "user-model", "field": "satisfaction_proxy", "trigger": "conditional"},
                {"to": "morphenix", "field": "quality_trends", "trigger": "conditional"},
                {"to": "user", "field": "eval_dashboard", "trigger": "on-request"},
            ],
        },
        "connects_to": ["user-model", "morphenix"],
        "memory": {
            "writes": [
                {"target": "eval-engine", "type": "score", "condition": "每次回答品質評分後"},
            ],
            "reads": [],
        },
    },
    "sandbox-lab": {
        "type": "on-demand",
        "layer": "evolution",
        "io": {
            "inputs": [
                {"from": "user", "field": "experiment_design", "required": True},
            ],
            "outputs": [
                {"to": "morphenix", "field": "experiment_results", "trigger": "conditional"},
                {"to": "eval-engine", "field": "ab_test_results", "trigger": "conditional"},
                {"to": "user", "field": "experiment_report", "trigger": "always"},
            ],
        },
        "connects_to": ["morphenix", "eval-engine", "orchestrator"],
        "memory": {},
    },
    "orchestrator": {
        "type": "on-demand",
        "layer": "evolution",
        "io": {
            "inputs": [
                {"from": "user", "field": "complex_task", "required": True},
            ],
            "outputs": [
                {"to": "wee", "field": "execution_trace", "trigger": "always"},
                {"to": "consultant-communication", "field": "execution_summary_request", "trigger": "conditional"},
                {"to": "user", "field": "orchestrated_result", "trigger": "always"},
            ],
        },
        "connects_to": ["wee", "eval-engine", "consultant-communication", "plugin-registry"],
        "memory": {
            "writes": [
                {"target": "wee", "type": "proficiency", "condition": "多 Skill 編排完成時"},
            ],
            "reads": [],
        },
    },
    "qa-auditor": {
        "type": "on-demand",
        "layer": "evolution",
        "io": {
            "inputs": [
                {"from": "user", "field": "code_delivery", "required": True},
            ],
            "outputs": [
                {"to": "morphenix", "field": "audit_report", "trigger": "conditional"},
                {"to": "user", "field": "qa_report", "trigger": "always"},
            ],
        },
        "connects_to": ["morphenix"],
        "memory": {},
    },

    # ──────────── 產品線（5 個）────────────
    "gap": {
        "type": "on-demand",
        "layer": "product",
        "io": {
            "inputs": [
                {"from": "user", "field": "market_scan_request", "required": True},
            ],
            "outputs": [
                {"to": "dse", "field": "opportunity_list", "trigger": "conditional"},
                {"to": "user", "field": "gap_analysis", "trigger": "always"},
            ],
        },
        "connects_to": ["dse", "env-radar"],
        "memory": {},
    },
    "dse": {
        "type": "on-demand",
        "layer": "product",
        "io": {
            "inputs": [
                {"from": "gap", "field": "opportunity_list", "required": False},
                {"from": "user", "field": "tech_fusion_request", "required": False},
            ],
            "outputs": [
                {"to": "acsf", "field": "feasibility_report", "trigger": "conditional"},
                {"to": "knowledge-lattice", "field": "feasibility_report", "trigger": "conditional"},
                {"to": "user", "field": "dse_report", "trigger": "always"},
            ],
        },
        "connects_to": ["acsf", "knowledge-lattice"],
        "memory": {
            "writes": [
                {"target": "knowledge-lattice", "type": "crystal", "condition": "驗證完成時"},
            ],
            "reads": [],
        },
    },
    "acsf": {
        "type": "on-demand",
        "layer": "product",
        "io": {
            "inputs": [
                {"from": "dse", "field": "feasibility_report", "required": False},
                {"from": "user", "field": "skill_forge_request", "required": False},
            ],
            "outputs": [
                {"to": "plugin-registry", "field": "new_skill_entry", "trigger": "conditional"},
                {"to": "user", "field": "skill_product", "trigger": "always"},
            ],
        },
        "connects_to": ["dse", "plugin-registry"],
        "memory": {},
    },
    "env-radar": {
        "type": "on-demand",
        "layer": "product",
        "io": {
            "inputs": [
                {"from": "user", "field": "scan_request", "required": True},
            ],
            "outputs": [
                {"to": "morphenix", "field": "external_signals", "trigger": "conditional"},
                {"to": "user", "field": "radar_report", "trigger": "always"},
            ],
        },
        "connects_to": ["morphenix", "gap"],
        "memory": {
            "writes": [
                {"target": "morphenix", "type": "proposal", "condition": "發現重要外部變化時"},
            ],
            "reads": [],
        },
    },
    "report-forge": {
        "type": "on-demand",
        "layer": "product",
        "io": {
            "inputs": [
                {"from": "user", "field": "analysis_data", "required": True},
            ],
            "outputs": [
                {"to": "user", "field": "paid_report", "trigger": "always"},
            ],
        },
        "connects_to": ["market-core", "consultant-communication", "aesthetic-sense"],
        "memory": {},
    },

    # ──────────── 市場分析（6 個）────────────
    "market-core": {
        "type": "on-demand",
        "layer": "market",
        "io": {
            "inputs": [
                {"from": "user", "field": "market_query", "required": True},
            ],
            "outputs": [
                {"to": "investment-masters", "field": "bull_bear_analysis", "trigger": "conditional"},
                {"to": "risk-matrix", "field": "bull_bear_analysis", "trigger": "conditional"},
                {"to": "sentiment-radar", "field": "analysis_context", "trigger": "conditional"},
                {"to": "knowledge-lattice", "field": "bull_bear_analysis", "trigger": "always"},
                {"to": "user", "field": "market_report", "trigger": "always"},
            ],
        },
        "connects_to": ["market-equity", "market-crypto", "market-macro", "investment-masters", "risk-matrix", "sentiment-radar"],
        "memory": {
            "writes": [
                {"target": "knowledge-lattice", "type": "crystal", "condition": "分析報告產出時"},
            ],
            "reads": [],
        },
    },
    "market-equity": {
        "type": "on-demand",
        "layer": "market",
        "io": {
            "inputs": [
                {"from": "market-core", "field": "framework", "required": True},
                {"from": "user", "field": "stock_query", "required": False},
            ],
            "outputs": [
                {"to": "market-core", "field": "equity_analysis", "trigger": "always"},
                {"to": "user", "field": "stock_report", "trigger": "always"},
            ],
        },
        "connects_to": ["market-core", "investment-masters"],
        "memory": {},
    },
    "market-crypto": {
        "type": "on-demand",
        "layer": "market",
        "io": {
            "inputs": [
                {"from": "market-core", "field": "framework", "required": True},
                {"from": "user", "field": "crypto_query", "required": False},
            ],
            "outputs": [
                {"to": "market-core", "field": "crypto_analysis", "trigger": "always"},
                {"to": "user", "field": "crypto_report", "trigger": "always"},
            ],
        },
        "connects_to": ["market-core", "investment-masters"],
        "memory": {},
    },
    "market-macro": {
        "type": "on-demand",
        "layer": "market",
        "io": {
            "inputs": [
                {"from": "market-core", "field": "framework", "required": True},
                {"from": "user", "field": "macro_query", "required": False},
            ],
            "outputs": [
                {"to": "market-core", "field": "macro_analysis", "trigger": "always"},
                {"to": "user", "field": "macro_report", "trigger": "always"},
            ],
        },
        "connects_to": ["market-core", "investment-masters"],
        "memory": {},
    },
    "investment-masters": {
        "type": "on-demand",
        "layer": "market",
        "io": {
            "inputs": [
                {"from": "market-core", "field": "bull_bear_analysis", "required": True},
            ],
            "outputs": [
                {"to": "risk-matrix", "field": "master_verdict", "trigger": "conditional"},
                {"to": "knowledge-lattice", "field": "master_verdict", "trigger": "always"},
                {"to": "user", "field": "masters_consultation", "trigger": "always"},
            ],
        },
        "connects_to": ["market-core", "risk-matrix", "sentiment-radar"],
        "memory": {
            "writes": [
                {"target": "knowledge-lattice", "type": "crystal", "condition": "會診完成時"},
            ],
            "reads": [],
        },
    },
    "risk-matrix": {
        "type": "on-demand",
        "layer": "market",
        "io": {
            "inputs": [
                {"from": "market-core", "field": "bull_bear_analysis", "required": True},
                {"from": "investment-masters", "field": "master_verdict", "required": False},
            ],
            "outputs": [
                {"to": "knowledge-lattice", "field": "allocation_plan", "trigger": "always"},
                {"to": "user", "field": "risk_report", "trigger": "always"},
            ],
        },
        "connects_to": ["market-core", "investment-masters"],
        "memory": {
            "writes": [
                {"target": "knowledge-lattice", "type": "crystal", "condition": "配置建議產出時"},
            ],
            "reads": [],
        },
    },
    "sentiment-radar": {
        "type": "on-demand",
        "layer": "market",
        "io": {
            "inputs": [
                {"from": "market-core", "field": "analysis_context", "required": False},
                {"from": "user", "field": "sentiment_query", "required": False},
            ],
            "outputs": [
                {"to": "market-core", "field": "sentiment_score", "trigger": "always"},
                {"to": "user", "field": "sentiment_report", "trigger": "always"},
            ],
        },
        "connects_to": ["market-core", "investment-masters"],
        "memory": {},
    },

    # ──────────── 工作流（3 個）────────────
    "workflow-svc-brand-marketing": {
        "type": "workflow",
        "layer": "workflow",
        "io": {
            "inputs": [
                {"from": "user", "field": "client_brief", "required": True},
            ],
            "outputs": [
                {"to": "wee", "field": "execution_trace", "trigger": "always"},
                {"to": "user", "field": "deliverables", "trigger": "always"},
            ],
        },
        "connects_to": ["ssa-consultant", "business-12", "brand-identity", "storytelling-engine",
                         "xmodel", "pdeif", "master-strategy", "text-alchemy", "c15",
                         "aesthetic-sense", "consultant-communication", "eval-engine",
                         "orchestrator", "knowledge-lattice"],
        "memory": {
            "writes": [
                {"target": "wee", "type": "proficiency", "condition": "工作流完成時"},
            ],
            "reads": [],
        },
    },
    "workflow-investment-analysis": {
        "type": "workflow",
        "layer": "workflow",
        "io": {
            "inputs": [
                {"from": "user", "field": "market_target", "required": True},
            ],
            "outputs": [
                {"to": "wee", "field": "execution_trace", "trigger": "always"},
                {"to": "user", "field": "html_report", "trigger": "always"},
            ],
        },
        "connects_to": ["market-core", "market-equity", "market-crypto", "market-macro",
                         "investment-masters", "sentiment-radar", "risk-matrix",
                         "report-forge", "eval-engine"],
        "memory": {
            "writes": [
                {"target": "wee", "type": "proficiency", "condition": "工作流完成時"},
            ],
            "reads": [],
        },
    },
    "workflow-ai-deployment": {
        "type": "workflow",
        "layer": "workflow",
        "io": {
            "inputs": [
                {"from": "user", "field": "business_assessment", "required": True},
            ],
            "outputs": [
                {"to": "wee", "field": "execution_trace", "trigger": "always"},
                {"to": "user", "field": "ai_deployment_plan", "trigger": "always"},
            ],
        },
        "connects_to": ["ssa-consultant", "business-12", "dse", "xmodel", "pdeif",
                         "master-strategy", "consultant-communication", "eval-engine",
                         "orchestrator", "knowledge-lattice", "report-forge", "aesthetic-sense"],
        "memory": {
            "writes": [
                {"target": "wee", "type": "proficiency", "condition": "工作流完成時"},
            ],
            "reads": [],
        },
    },

    # ──────────── 特殊（1 個）────────────
    "tantra": {
        "type": "on-demand",
        "layer": "special",
        "io": {
            "inputs": [
                {"from": "user", "field": "explicit_activation", "required": True},
            ],
            "outputs": [
                {"to": "user", "field": "research_output", "trigger": "on-request"},
            ],
        },
        "connects_to": ["resonance"],
        "memory": {},
    },

    # ──────────── 參考文件（1 個）────────────
    "plugin-registry": {
        "type": "reference",
        "layer": "evolution",
        "io": {
            "inputs": [
                {"from": "acsf", "field": "new_skill_entry", "required": False},
            ],
            "outputs": [
                {"to": "orchestrator", "field": "skill_catalog", "trigger": "on-request"},
                {"to": "morphenix", "field": "skill_health_data", "trigger": "on-request"},
            ],
        },
        "connects_to": ["dna27", "orchestrator", "morphenix", "acsf"],
        "memory": {},
    },

    # ──────────── 其他（4 個）────────────
    "dna27": {
        "type": "always-on",
        "layer": "core-extension",
        "io": {
            "inputs": [
                {"from": "user", "field": "all_input", "required": True},
            ],
            "outputs": [
                {"to": "query-clarity", "field": "routed_input", "trigger": "always"},
                {"to": "deep-think", "field": "loop_context", "trigger": "always"},
            ],
        },
        "connects_to": ["query-clarity", "deep-think", "c15", "plugin-registry"],
        "memory": {},
    },
    "plan-engine": {
        "type": "on-demand",
        "layer": "evolution",
        "io": {
            "inputs": [
                {"from": "user", "field": "chaotic_start", "required": True},
            ],
            "outputs": [
                {"to": "orchestrator", "field": "clear_plan", "trigger": "conditional"},
                {"to": "user", "field": "plan_document", "trigger": "always"},
            ],
        },
        "connects_to": ["orchestrator"],
        "memory": {},
    },
    "info-architect": {
        "type": "on-demand",
        "layer": "meta",
        "io": {
            "inputs": [
                {"from": "user", "field": "organization_task", "required": True},
            ],
            "outputs": [
                {"to": "user", "field": "organized_structure", "trigger": "always"},
            ],
        },
        "connects_to": ["aesthetic-sense"],
        "memory": {},
    },
    "group-meeting-notes": {
        "type": "workflow",
        "layer": "workflow",
        "io": {
            "inputs": [
                {"from": "user", "field": "meeting_transcript", "required": True},
            ],
            "outputs": [
                {"to": "user", "field": "structured_notes", "trigger": "always"},
            ],
        },
        "connects_to": ["consultant-communication"],
        "memory": {},
    },
}


# ═══════════════════════════════════════════════════════════════
# YAML 生成
# ═══════════════════════════════════════════════════════════════

def yaml_val(v: Any, indent: int = 0) -> str:
    """簡易 YAML 值格式化"""
    prefix = "  " * indent
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        if not v:
            return "[]"
        lines = []
        for item in v:
            if isinstance(item, dict):
                parts = []
                for i, (k2, v2) in enumerate(item.items()):
                    val = yaml_val(v2)
                    if i == 0:
                        parts.append(f"{prefix}- {k2}: {val}")
                    else:
                        parts.append(f"{prefix}  {k2}: {val}")
                lines.append("\n".join(parts))
            else:
                lines.append(f"{prefix}- {yaml_val(item)}")
        return "\n" + "\n".join(lines)
    if isinstance(v, dict):
        if not v:
            return "{}"
        lines = []
        for k2, v2 in v.items():
            val = yaml_val(v2, indent + 1)
            if isinstance(v2, (list, dict)) and v2:
                lines.append(f"{prefix}  {k2}:{val}")
            else:
                lines.append(f"{prefix}  {k2}: {val}")
        return "\n" + "\n".join(lines)
    return str(v)


def build_manifest_yaml(name: str, manifest: dict) -> str:
    """從 manifest dict 生成 YAML 片段（不含 name 和 description）"""
    lines = []
    lines.append(f"type: {manifest['type']}")
    lines.append(f"layer: {manifest['layer']}")

    # io
    io_data = manifest.get("io", {})
    if io_data:
        lines.append("io:")
        for section in ["inputs", "outputs"]:
            items = io_data.get(section, [])
            if items:
                lines.append(f"  {section}:")
                for item in items:
                    first = True
                    for k, v in item.items():
                        val = "true" if v is True else "false" if v is False else str(v)
                        if first:
                            lines.append(f"    - {k}: {val}")
                            first = False
                        else:
                            lines.append(f"      {k}: {val}")

    # connects_to
    ct = manifest.get("connects_to", [])
    if ct:
        lines.append("connects_to:")
        for c in ct:
            lines.append(f"  - {c}")

    # memory
    mem = manifest.get("memory", {})
    if mem:
        lines.append("memory:")
        for section in ["writes", "reads"]:
            items = mem.get(section, [])
            if items:
                lines.append(f"  {section}:")
                for item in items:
                    first = True
                    for k, v in item.items():
                        val = f'"{v}"' if " " in str(v) or "（" in str(v) else str(v)
                        if first:
                            lines.append(f"    - {k}: {val}")
                            first = False
                        else:
                            lines.append(f"      {k}: {val}")

    return "\n".join(lines)


def inject_manifest(skill_path: Path, manifest_yaml: str, dry_run: bool) -> str:
    """將 manifest 注入到 SKILL.md 的 YAML frontmatter 中"""
    content = skill_path.read_text(encoding="utf-8")

    # 偵測 YAML frontmatter
    if not content.startswith("---"):
        return f"SKIP (no YAML frontmatter): {skill_path.name}"

    # 找到第二個 ---
    second_dash = content.index("---", 3)
    yaml_block = content[3:second_dash].strip()
    rest = content[second_dash:]

    # 檢查是否已有 manifest（有 type: 欄位就算有）
    if "\ntype:" in yaml_block or yaml_block.startswith("type:"):
        return f"SKIP (already has manifest): {skill_path.parent.name}"

    # 在 name: 之後、description: 之前插入 manifest
    # 找到 description: 的位置
    desc_match = re.search(r"^description:", yaml_block, re.MULTILINE)
    if not desc_match:
        return f"SKIP (no description field): {skill_path.parent.name}"

    insert_pos = desc_match.start()
    new_yaml = yaml_block[:insert_pos] + manifest_yaml + "\n" + yaml_block[insert_pos:]

    new_content = "---\n" + new_yaml + "\n" + rest

    if dry_run:
        return f"WOULD INJECT: {skill_path.parent.name}"
    else:
        skill_path.write_text(new_content, encoding="utf-8")
        return f"INJECTED: {skill_path.parent.name}"


def main():
    parser = argparse.ArgumentParser(description="Inject Skill Manifests")
    parser.add_argument("--dry-run", action="store_true", help="只報告，不實際修改")
    parser.add_argument("--apply", action="store_true", help="實際注入")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("請指定 --dry-run 或 --apply")
        sys.exit(1)

    dry_run = args.dry_run

    results = {"injected": 0, "skipped": 0, "missing": 0, "errors": 0}

    for skill_name, manifest in SKILL_MANIFESTS.items():
        skill_dir = SKILLS_DIR / skill_name
        skill_file = skill_dir / "SKILL.md"

        if not skill_file.exists():
            print(f"  MISSING: {skill_name} (no SKILL.md)")
            results["missing"] += 1
            continue

        try:
            manifest_yaml = build_manifest_yaml(skill_name, manifest)
            result = inject_manifest(skill_file, manifest_yaml, dry_run)
            print(f"  {result}")
            if "INJECT" in result:
                results["injected"] += 1
            else:
                results["skipped"] += 1
        except Exception as e:
            print(f"  ERROR: {skill_name} — {e}")
            results["errors"] += 1

    print(f"\n{'DRY RUN' if dry_run else 'APPLIED'} Summary:")
    print(f"  Injected: {results['injected']}")
    print(f"  Skipped:  {results['skipped']}")
    print(f"  Missing:  {results['missing']}")
    print(f"  Errors:   {results['errors']}")

    # 同步鏡像
    if not dry_run and results["injected"] > 0:
        print(f"\n同步 ~/.claude/skills/ 鏡像...")
        import shutil
        for skill_name in SKILL_MANIFESTS:
            src = SKILLS_DIR / skill_name / "SKILL.md"
            dst = MIRROR_DIR / skill_name / "SKILL.md"
            if src.exists() and dst.exists():
                shutil.copy2(src, dst)
                print(f"  SYNCED: {skill_name}")


if __name__ == "__main__":
    main()
