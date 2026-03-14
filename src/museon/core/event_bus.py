"""EventBus — 全域事件匯流排（發布/訂閱模式）.

依據 THREE_LAYER_PULSE BDD Spec §8 實作。
"""

import logging
import threading
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Pulse-related event types
# ═══════════════════════════════════════════

PULSE_MICRO_BEAT = "PULSE_MICRO_BEAT"
PULSE_RHYTHM_CHECK = "PULSE_RHYTHM_CHECK"
PULSE_NIGHTLY_DONE = "PULSE_NIGHTLY_DONE"
EVOLUTION_HEARTBEAT = "EVOLUTION_HEARTBEAT"
PROACTIVE_MESSAGE = "PROACTIVE_MESSAGE"
AUTONOMOUS_TASK_DONE = "AUTONOMOUS_TASK_DONE"

# Nightly pipeline events
NIGHTLY_STARTED = "NIGHTLY_STARTED"
NIGHTLY_COMPLETED = "NIGHTLY_COMPLETED"

# Soft Workflow 軟工作流事件
WORKFLOW_CREATED = "WORKFLOW_CREATED"
WORKFLOW_EXECUTED = "WORKFLOW_EXECUTED"
WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"
WORKFLOW_FAILED = "WORKFLOW_FAILED"
WORKFLOW_LIFECYCLE_CHANGED = "WORKFLOW_LIFECYCLE_CHANGED"
WORKFLOW_SCHEDULE_TOGGLED = "WORKFLOW_SCHEDULE_TOGGLED"

# WEE / Workflow 自我迭代事件
BRAIN_RESPONSE_COMPLETE = "BRAIN_RESPONSE_COMPLETE"
WEE_RECORDED = "WEE_RECORDED"
WEE_LIFECYCLE_CHANGED = "WEE_LIFECYCLE_CHANGED"
WEE_PLATEAU_DETECTED = "WEE_PLATEAU_DETECTED"

# Self-Diagnosis 自我診斷事件
SELF_DIAGNOSIS_TRIGGERED = "SELF_DIAGNOSIS_TRIGGERED"
SELF_DIAGNOSIS_COMPLETED = "SELF_DIAGNOSIS_COMPLETED"
SELF_REPAIR_EXECUTED = "SELF_REPAIR_EXECUTED"                # DEPRECATED: 無發布/訂閱者

# Self-Surgery 自我手術事件
SURGERY_TRIGGERED = "SURGERY_TRIGGERED"
SURGERY_SAFETY_PASSED = "SURGERY_SAFETY_PASSED"
SURGERY_SAFETY_FAILED = "SURGERY_SAFETY_FAILED"
SURGERY_COMPLETED = "SURGERY_COMPLETED"
SURGERY_FAILED = "SURGERY_FAILED"
SURGERY_ROLLBACK = "SURGERY_ROLLBACK"
SURGERY_VALIDATED = "SURGERY_VALIDATED"
SURGERY_VALIDATION_FAILED = "SURGERY_VALIDATION_FAILED"
SURGERY_DELEGATED_TO_CLAUDE_CODE = "SURGERY_DELEGATED_TO_CLAUDE_CODE"

# Morphenix 演化提案事件
MORPHENIX_L3_PROPOSAL = "MORPHENIX_L3_PROPOSAL"
MORPHENIX_AUTO_APPROVED = "MORPHENIX_AUTO_APPROVED"
MORPHENIX_EXECUTION_COMPLETED = "MORPHENIX_EXECUTION_COMPLETED"
MORPHENIX_ROLLBACK = "MORPHENIX_ROLLBACK"

# ═══════════════════════════════════════════
# Governance 治理層事件（Phase 3d）
# ═══════════════════════════════════════════
GOVERNANCE_CYCLE_COMPLETED = "GOVERNANCE_CYCLE_COMPLETED"
GOVERNANCE_HEALTH_CHANGED = "GOVERNANCE_HEALTH_CHANGED"
GOVERNANCE_ALGEDONIC_SIGNAL = "GOVERNANCE_ALGEDONIC_SIGNAL"

# ═══════════════════════════════════════════
# Autonomy Architecture 自主演化事件
# ═══════════════════════════════════════════
TOKEN_BUDGET_WARNING = "TOKEN_BUDGET_WARNING"                # DEPRECATED: 無發布/訂閱者
TOKEN_BUDGET_CONSERVATION = "TOKEN_BUDGET_CONSERVATION"      # DEPRECATED: 無發布/訂閱者
SYNAPSE_PRELOAD = "SYNAPSE_PRELOAD"
TOOL_MUSCLE_DORMANT = "TOOL_MUSCLE_DORMANT"
IMMUNE_MEMORY_LEARNED = "IMMUNE_MEMORY_LEARNED"
AUTONOMIC_REPAIR = "AUTONOMIC_REPAIR"
EVOLUTION_TRACE = "EVOLUTION_TRACE"                          # DEPRECATED: 無發布/訂閱者
TRIGGER_FIRED = "TRIGGER_FIRED"

# ═══════════════════════════════════════════
# Immune Defense 五層免疫防禦事件
# ═══════════════════════════════════════════
PREFLIGHT_FAILED = "PREFLIGHT_FAILED"
PREFLIGHT_PASSED = "PREFLIGHT_PASSED"
REFRACTORY_BACKOFF = "REFRACTORY_BACKOFF"
REFRACTORY_HIBERNATE = "REFRACTORY_HIBERNATE"
REFRACTORY_WAKE = "REFRACTORY_WAKE"                          # DEPRECATED: 無發布/訂閱者
GATEWAY_DEGRADED = "GATEWAY_DEGRADED"                        # DEPRECATED: 無發布/訂閱者

# ═══════════════════════════════════════════
# Exploration → Evolution Bridge 事件
# ═══════════════════════════════════════════
EXPLORATION_CRYSTALLIZED = "EXPLORATION_CRYSTALLIZED"      # 探索完成且有結晶
EXPLORATION_INSIGHT = "EXPLORATION_INSIGHT"                 # 探索產出洞見（未必結晶）
CURIOSITY_RESEARCHED = "CURIOSITY_RESEARCHED"              # 好奇問題已研究
SCOUT_DRAFT_READY = "SCOUT_DRAFT_READY"                    # Scout 產出技能草稿
SCOUT_GAP_DETECTED = "SCOUT_GAP_DETECTED"                  # Scout 偵測到能力缺口

# ═══════════════════════════════════════════
# Dendritic Layer 免疫觀察層事件
# ═══════════════════════════════════════════
HEALTH_SCORE_UPDATED = "HEALTH_SCORE_UPDATED"              # Health Score 變化
INCIDENT_DETECTED = "INCIDENT_DETECTED"                    # 結構化事件偵測
REPAIR_RESEARCH_READY = "REPAIR_RESEARCH_READY"            # 免疫研究完成，修復方案就緒

# ═══════════════════════════════════════════
# Phase 1 神經整合事件
# ═══════════════════════════════════════════

# WP-01: Memory EventBus 閉環
MEMORY_STORED = "MEMORY_STORED"                            # 記憶已存儲
MEMORY_PROMOTED = "MEMORY_PROMOTED"                        # 記憶已晉升
MEMORY_RECALLED = "MEMORY_RECALLED"                        # 記憶已召回
MEMORY_VECTOR_INDEXED = "MEMORY_VECTOR_INDEXED"            # 記憶已向量索引

# WP-02: Skill-Evolution 閉環
SKILL_QUALITY_SCORED = "SKILL_QUALITY_SCORED"              # 技能品質已評分（WEE 5D）
DNA27_WEIGHTS_UPDATED = "DNA27_WEIGHTS_UPDATED"            # DNA27 權重已更新
SKILL_ROUTER_RELOADED = "SKILL_ROUTER_RELOADED"            # SkillRouter 已熱重載

# WP-05: Research 去重
RESEARCH_COMPLETED = "RESEARCH_COMPLETED"                  # 研究已完成

# WP-07: Tools Registry 即時降級
TOOL_HEALTH_CHANGED = "TOOL_HEALTH_CHANGED"                # 工具健康狀態變化
TOOL_DEGRADED = "TOOL_DEGRADED"                            # 工具已降級
TOOL_RECOVERED = "TOOL_RECOVERED"                          # 工具已恢復

# ═══════════════════════════════════════════
# Phase 2 神經整合事件
# ═══════════════════════════════════════════

# WP-03: Governance-Nightly 雙向適應
NIGHTLY_HEALTH_GATE = "NIGHTLY_HEALTH_GATE"                # Nightly 健康閘門決策
NIGHTLY_DAG_EXECUTED = "NIGHTLY_DAG_EXECUTED"              # Nightly DAG 排程已執行
EVOLUTION_VELOCITY_ALERT = "EVOLUTION_VELOCITY_ALERT"      # 演化速度警報（高原/退化）
AUDIT_TREND_UPDATED = "AUDIT_TREND_UPDATED"                # 審計趨勢更新

# WP-04: Doctor-Governance-Research 閉環
AUDIT_COMPLETED = "AUDIT_COMPLETED"                        # 系統審計完成
IMMUNE_KNOWLEDGE_GAINED = "IMMUNE_KNOWLEDGE_GAINED"        # 免疫系統學到新知識

# WP-06: Nightly→SharedAssets 知識發布
SHARED_ASSET_PUBLISHED = "SHARED_ASSET_PUBLISHED"          # 共享資產已發布
KNOWLEDGE_GRAPH_UPDATED = "KNOWLEDGE_GRAPH_UPDATED"        # 知識圖譜已更新

# WP-08: Pulse 心跳自適應
PULSE_FREQUENCY_ADJUSTED = "PULSE_FREQUENCY_ADJUSTED"      # 脈搏頻率已調整
HEALTH_SCORE_UPDATED = "HEALTH_SCORE_UPDATED"              # Health Score 更新

# ═══════════════════════════════════════════
# Phase 3 外部整合事件
# ═══════════════════════════════════════════

# EXT-04: 多通道通訊
CHANNEL_MESSAGE_RECEIVED = "CHANNEL_MESSAGE_RECEIVED"      # 通道訊息接收
CHANNEL_MESSAGE_SENT = "CHANNEL_MESSAGE_SENT"              # 通道訊息發送

# EXT-01: RSS 聚合器
RSS_NEW_ITEMS = "RSS_NEW_ITEMS"                            # RSS 新條目

# EXT-08: Wiki 自動發布
WIKI_PUBLISHED = "WIKI_PUBLISHED"                          # Wiki 已發布

# EXT-12: 使用者反饋
USER_FEEDBACK_SIGNAL = "USER_FEEDBACK_SIGNAL"              # 使用者反饋信號

# EXT-07: Dify 排程
DIFY_WORKFLOW_TRIGGERED = "DIFY_WORKFLOW_TRIGGERED"        # Dify 工作流觸發
DIFY_WORKFLOW_COMPLETED = "DIFY_WORKFLOW_COMPLETED"        # Dify 工作流完成

# ═══════════════════════════════════════════
# Phase 4 外部整合事件
# ═══════════════════════════════════════════

# EXT-02: IoT (MQTT)
IOT_EVENT_RECEIVED = "IOT_EVENT_RECEIVED"                  # IoT 事件接收
IOT_COMMAND_SENT = "IOT_COMMAND_SENT"                      # IoT 指令發送

# EXT-03: Chrome Extension
EXTENSION_CAPTURE = "EXTENSION_CAPTURE"                    # 瀏覽器擷取
EXTENSION_COMMAND = "EXTENSION_COMMAND"                    # 瀏覽器指令

# EXT-05: 圖片生成
IMAGE_GENERATED = "IMAGE_GENERATED"                        # 圖片已生成

# EXT-06: 語音克隆
VOICE_SYNTHESIZED = "VOICE_SYNTHESIZED"                    # 語音已合成

# EXT-11: Zotero 文獻
ZOTERO_ITEM_IMPORTED = "ZOTERO_ITEM_IMPORTED"              # Zotero 文獻匯入

# ═══════════════════════════════════════════
# 外向型進化事件（Outward Evolution）
# ═══════════════════════════════════════════
OUTWARD_SEARCH_NEEDED = "OUTWARD_SEARCH_NEEDED"              # 外向搜尋觸發
OUTWARD_SELF_CRYSTALLIZED = "OUTWARD_SELF_CRYSTALLIZED"      # Track A 自我進化結晶固化
OUTWARD_SERVICE_CRYSTALLIZED = "OUTWARD_SERVICE_CRYSTALLIZED"  # Track B 服務進化結晶固化
OUTWARD_TRIAL_RECORDED = "OUTWARD_TRIAL_RECORDED"            # 外部知識試用結果記錄
OUTWARD_KNOWLEDGE_ARCHIVED = "OUTWARD_KNOWLEDGE_ARCHIVED"    # 外部知識淘汰歸檔

# Pulse 進階事件
PULSE_PROACTIVE_SENT = "PULSE_PROACTIVE_SENT"                  # 主動推送已發送
PULSE_EXPLORATION_DONE = "PULSE_EXPLORATION_DONE"              # 探索完成
RELATIONSHIP_SIGNAL = "RELATIONSHIP_SIGNAL"                    # 關係訊號（情感偵測）

# Morphenix 進階事件
MORPHENIX_PROPOSAL_CREATED = "MORPHENIX_PROPOSAL_CREATED"      # 演化提案已建立
MORPHENIX_EXECUTED = "MORPHENIX_EXECUTED"                      # 演化已執行

# WEE 進階事件
WEE_CYCLE_COMPLETE = "WEE_CYCLE_COMPLETE"                      # WEE 週期完成

# Knowledge Lattice 事件
CRYSTAL_CREATED = "CRYSTAL_CREATED"                            # 結晶已建立

# Soul Identity 事件
SOUL_RING_DEPOSITED = "SOUL_RING_DEPOSITED"                    # 靈魂環已存入
SOUL_IDENTITY_TAMPERED = "SOUL_IDENTITY_TAMPERED"            # SOUL.md 完整性被篡改

# ═══════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════

_instance: Optional["EventBus"] = None
_lock = threading.Lock()


def get_event_bus() -> "EventBus":
    """全域單例."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = EventBus()
    return _instance


def _reset_event_bus() -> None:
    """重置單例（僅供測試用）."""
    global _instance
    with _lock:
        if _instance is not None:
            _instance.clear()
        _instance = None


# ═══════════════════════════════════════════
# EventBus
# ═══════════════════════════════════════════


class EventBus:
    """全域事件匯流排 — 發布/訂閱模式.

    設計原則：
    - 訂閱者異常不影響其他訂閱者
    - 執行緒安全
    - 同步呼叫（訂閱者應快速完成，重工作請另起執行緒）
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, callback: Callable) -> None:
        """訂閱事件."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """取消訂閱."""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                except ValueError as e:
                    logger.debug(f"[EVENT_BUS] operation failed (degraded): {e}")

    def publish(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """發布事件 — 呼叫所有訂閱者."""
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))

        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error(
                    f"EventBus subscriber error on '{event_type}': {e}"
                )

    def subscriber_count(self, event_type: str) -> int:
        """回傳指定事件的訂閱者數量."""
        with self._lock:
            return len(self._subscribers.get(event_type, []))

    def clear(self) -> None:
        """清除所有訂閱."""
        with self._lock:
            self._subscribers.clear()
