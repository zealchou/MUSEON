"""MUSEON Brain — MUSEON 大腦核心.

所有訊息都經過這裡處理，串穿 DNA27 + Skills + ANIMA + Memory + Security
+ Intuition + Eval + SoulRing + KnowledgeLattice + PlanEngine。

處理流程（完整 Pipeline）：
  Step 0    : 更新成長階段
  Step 0.5  : 承諾自檢 — 檢查到期/逾期承諾
  Step 0.7  : ★ 元認知觀察 — 比對上次預判 vs 使用者實際反應（雙向觀察）
  Step 1    : 檢查命名儀式
  Step 1.5  : 直覺引擎 — sense()（Step -0.5：在 DNA27 路由之前）
  Step 2    : 載入 ANIMA_MC + ANIMA_USER
  Step 3    : DNA27 反射路由器 — RoutingSignal（靈魂先行）
  Step 3.1  : DNA27 路由 — 匹配技能（受 RoutingSignal 調節）
  Step 3.2  : ★ P2 決策層信號偵測（重大決策先問後答）
  Step 3.3  : ★ P2 決策層路徑短路（若偵測到重大決策，直接返回反問）
  Step 3.4  : ★ P3 策略層並行融合信號偵測（非 P2 重大決策時才觸發）
  Step 3.5  : 計畫引擎觸發檢查
  Step 3.65 : 百合引擎 — 軍師四象限路由（lord_profile → BaiheDecision）
  Step 4    : 組建系統提示詞（DNA27 + 技能 + ANIMA + 記憶 + 承諾 + 直覺 + 百合）
  Step 5    : 載入對話歷史
  Step 6    : 呼叫 Claude API
  Step 6.2  : ★ PreCognition — 回應前元認知審查（大腦層級）
  Step 6.3  : ★ (若需修改) 注入審查回饋，精煉回覆
  Step 6.5  : Eval Engine — Q-Score 靜默評分
  Step 7    : 持久化到四通道記憶
  Step 8    : 追蹤技能使用
  Step 8.5  : 靈魂年輪 — 偵測年輪級事件
  Step 8.6  : 知識晶格 — 對話後掃描
  Step 8.7  : 承諾掃描 — 偵測回覆中的承諾並登記
  Step 9    : 更新 ANIMA_USER（被動觀察）
  Step 9.7  : ★ 元認知預判 — 預測使用者對本次回覆的反應

設計原則（使用者要求）：
- 不需預先載入所有 skill，透過 DNA27 配對快速檢索
- 追蹤每個技能使用結果，供自我迭代
- 雙 ANIMA（MC 自己 + User 使用者）都可被 MUSEON 閱讀與改寫
- 所有新模組以 try/except 包裹，任一模組故障不影響核心回覆能力
"""

import asyncio
import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Mixin 模組（L3-A2 Brain 拆分）──
from museon.agent.brain_prompt_builder import BrainPromptBuilderMixin
from museon.agent.brain_dispatch import BrainDispatchMixin
from museon.agent.brain_observation import BrainObservationMixin
from museon.agent.brain_p3_fusion import BrainP3FusionMixin
from museon.agent.brain_tools import BrainToolsMixin


logger = logging.getLogger(__name__)


# L3-A2: 共享型別從 brain_types 導入（避免循環 import）
from museon.agent.brain_types import DecisionSignal, P3FusionSignal


class MuseonBrain(BrainPromptBuilderMixin, BrainDispatchMixin, BrainObservationMixin, BrainP3FusionMixin, BrainToolsMixin):
    """MUSEON Brain — MUSEON 的大腦，整合所有模組."""

    def __init__(self, data_dir: str = "data"):
        """初始化大腦.

        Args:
            data_dir: 資料目錄（包含 ANIMA, skills, memory）
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # ANIMA 檔案路徑
        self.anima_mc_path = self.data_dir / "ANIMA_MC.json"
        self.anima_user_path = self.data_dir / "ANIMA_USER.json"

        # ── AnimaMCStore 統一存取層（合約 1：解決 3 種互不相容的寫入策略）──
        from museon.pulse.anima_mc_store import get_anima_mc_store
        self._anima_mc_store = get_anima_mc_store(path=self.anima_mc_path)

        # ── AnimaChangelog（Project Epigenesis: ANIMA_USER 差分版本追蹤）──
        self._anima_changelog = None
        try:
            from museon.pulse.anima_changelog import AnimaChangelog
            self._anima_changelog = AnimaChangelog(data_dir=str(self.data_dir))
        except Exception as e:
            logger.debug(f"AnimaChangelog 初始化失敗（降級為無追蹤）: {e}")

        # v10.7: process() 並行隔離鎖 — 防止兩個群組同時 process 導致 _ctx 覆蓋
        self._process_lock = asyncio.Lock()

        # 對話歷史（in-memory, per session）
        self._sessions: Dict[str, List[Dict[str, str]]] = {}
        self._offline_flag = False  # 離線回覆標記 — 為 True 時不持久化 session
        self._last_offline_probe_ts = 0.0  # 離線模式下上次 self-probe 時間戳

        # 技能使用追蹤（供 WEE/Morphenix）
        self._skill_usage_log: List[Dict[str, Any]] = []

        # ★ v10.4 Route B: session 內 skill 使用次數追蹤（MoE 衰減用）
        self._skill_usage: Dict[str, Dict[str, int]] = {}

        # ★ v10.4 Route C: 跨輪路由歷史（state-conditioned routing 用）
        self._routing_history: Dict[str, List[Dict]] = {}
        self._last_routing_signal = None  # PDR Phase 2 消費

        # ── EventBus（全域事件匯流排）──
        try:
            from museon.core.event_bus import get_event_bus
            self._event_bus = get_event_bus()
        except Exception as e:
            logger.debug(f"EventBus 取得失敗，降級為 None: {e}")
            self._event_bus = None

        # ── CORE 模組（失敗 = 系統不可用）──
        from museon.agent.skill_router import SkillRouter
        self.skill_router = SkillRouter(
            skills_dir=str(self.data_dir / "skills"),
            event_bus=self._event_bus,
        )

        # ★ v10.5: 八原語向量語義偵測器
        self._primal_detector = None
        try:
            from museon.agent.primal_detector import PrimalDetector
            self._primal_detector = PrimalDetector(
                workspace=self.data_dir,
                event_bus=self._event_bus,
            )
            self._primal_detector.ensure_indexed()
            logger.debug("PrimalDetector 初始化成功")
        except Exception as e:
            logger.debug(f"PrimalDetector 初始化失敗（降級到關鍵字）: {type(e).__name__}: {e}")

        # ★ v1.13: Memory Gate — 記憶寫入前的意圖分類閘門
        self._memory_gate = None
        try:
            from museon.memory.memory_gate import MemoryGate
            self._memory_gate = MemoryGate()
        except Exception as e:
            logger.debug(f"MemoryGate 初始化失敗（降級到無閘門模式）: {e}")

        from museon.memory.store import MemoryStore
        self.memory_store = MemoryStore(
            base_path=str(self.data_dir / "memory")
        )

        from museon.onboarding.ceremony import NamingCeremony
        self.ceremony = NamingCeremony(data_dir=str(self.data_dir))

        # ── ModuleRegistry：聲明式載入所有可選模組 ──
        from museon.core.module_registry import ModuleRegistry, ModuleSpec, ModuleTier

        self._module_registry = ModuleRegistry()
        _dd = str(self.data_dir)

        # 定義所有可選模組（原本各自 try/except 的 28 個模組）
        self._module_registry.register_many({
            # ── Agent 層 ──
            "intuition": ModuleSpec(
                import_path="museon.agent.intuition",
                class_name="IntuitionEngine",
                init_kwargs={"data_dir": _dd},
                attr_name="intuition",
            ),
            "eval_engine": ModuleSpec(
                import_path="museon.agent.eval_engine",
                class_name="EvalEngine",
                init_kwargs={"data_dir": _dd},
                attr_name="eval_engine",
            ),
            "knowledge_lattice": ModuleSpec(
                import_path="museon.agent.knowledge_lattice",
                class_name="KnowledgeLattice",
                init_kwargs={"data_dir": _dd},
                attr_name="knowledge_lattice",
            ),
            "plan_engine": ModuleSpec(
                import_path="museon.agent.plan_engine",
                class_name="PlanEngine",
                init_kwargs={"data_dir": _dd},
                attr_name="plan_engine",
            ),
            "sub_agent_mgr": ModuleSpec(
                import_path="museon.agent.sub_agent",
                class_name="SubAgentManager",
                init_kwargs={"data_dir": _dd},
                attr_name="sub_agent_mgr",
            ),
            "safety_anchor": ModuleSpec(
                import_path="museon.agent.safety_anchor",
                class_name="SafetyAnchor",
                attr_name="safety_anchor",
            ),
            "kernel_guard": ModuleSpec(
                import_path="museon.agent.kernel_guard",
                class_name="KernelGuard",
                init_kwargs={"data_dir": self.data_dir},
                attr_name="kernel_guard",
            ),
            "drift_detector": ModuleSpec(
                import_path="museon.agent.drift_detector",
                class_name="DriftDetector",
                init_kwargs={"data_dir": self.data_dir},
                attr_name="drift_detector",
            ),
            # ── Security 層 ──
            "input_sanitizer": ModuleSpec(
                import_path="museon.security.sanitizer",
                class_name="InputSanitizer",
                attr_name="input_sanitizer",
            ),
            # ── LLM 層 ──
            "budget_monitor": ModuleSpec(
                import_path="museon.llm.budget",
                class_name="BudgetMonitor",
                init_kwargs={"data_dir": _dd},
                attr_name="budget_monitor",
            ),
            "router": ModuleSpec(
                import_path="museon.llm.router",
                class_name="Router",
                init_kwargs={"data_dir": _dd},
                attr_name="_router",
            ),
            # ── Evolution 層 ──
            "synapse_network": ModuleSpec(
                import_path="museon.evolution.skill_synapse",
                class_name="SynapseNetwork",
                init_kwargs={"data_dir": self.data_dir},
                attr_name="_synapse_network",
                tier=ModuleTier.EDGE,
            ),
            "tool_muscle": ModuleSpec(
                import_path="museon.evolution.tool_muscle",
                class_name="ToolMuscleTracker",
                init_kwargs={"data_dir": self.data_dir},
                attr_name="_tool_muscle",
                tier=ModuleTier.EDGE,
            ),
            # NOTE: TriggerEngine 由 Nightly Pipeline 主動調用，
            # Brain 僅負責 lazy-load 實例化，對話流不直接使用。
            "trigger_engine": ModuleSpec(
                import_path="museon.evolution.trigger_weights",
                class_name="TriggerEngine",
                init_kwargs={"data_dir": self.data_dir},
                attr_name="_trigger_engine",
                tier=ModuleTier.EDGE,
            ),
            # ── Governance 層 ──
            "footprint": ModuleSpec(
                import_path="museon.governance.footprint",
                class_name="FootprintStore",
                init_kwargs={"data_dir": self.data_dir},
                attr_name="_footprint",
                tier=ModuleTier.EDGE,
            ),
            # ── Registry 層 ──
            "registry_manager": ModuleSpec(
                import_path="museon.registry.registry_manager",
                class_name="RegistryManager",
                init_kwargs={"data_dir": _dd, "user_id": "cli_user"},
                attr_name="_registry_manager",
                tier=ModuleTier.EDGE,
            ),
        })

        # 初始化所有可選模組（統一降級處理）
        self._module_registry.init_all()
        self._module_registry.inject_to(self)

        # ── AnimaMCStore: 注入 KernelGuard（Store 先建，KG 後建）──
        if getattr(self, "kernel_guard", None):
            self._anima_mc_store.set_kernel_guard(self.kernel_guard)

        # ── 需要特殊初始化的模組（無法用 ModuleSpec 標準化的）──

        # DiaryStore（原 SoulRing，需要兩個類別交互初始化）
        try:
            from museon.agent.soul_ring import DiaryStore, RingDepositor
            self._diary_store = DiaryStore(data_dir=_dd)
            self.ring_depositor = RingDepositor(
                store=self._diary_store, data_dir=_dd,
            )
        except Exception as e:
            logger.warning(f"DiaryStore 載入失敗（降級運行）: {e}")
            self._diary_store = None
            self.ring_depositor = None

        # Q-Score 歷史持久化
        self._q_score_history_path = self.data_dir / "_system" / "q_score_history.json"
        self._q_score_history: list = []
        try:
            if self._q_score_history_path.exists():
                self._q_score_history = json.loads(
                    self._q_score_history_path.read_text(encoding="utf-8")
                )
        except Exception as e:
            logger.warning(f"Q-score 歷史讀取失敗，重置為空: {e}")

        # CrystalActuator（需要 event_bus 注入）
        try:
            from museon.agent.crystal_actuator import CrystalActuator
            self.crystal_actuator = CrystalActuator(
                workspace=self.data_dir, event_bus=self._event_bus,
            )
        except Exception as e:
            logger.warning(f"CrystalActuator 載入失敗（降級運行）: {e}")
            self.crystal_actuator = None

        # Recommender（知識推薦引擎——依賴 KnowledgeLattice._store）
        self._recommender = None
        try:
            from museon.agent.recommender import Recommender
            _cs = self.knowledge_lattice._store if self.knowledge_lattice else None
            self._recommender = Recommender(
                workspace=self.data_dir,
                event_bus=self._event_bus,
                crystal_store=_cs,
            )
        except Exception as e:
            logger.warning(f"Recommender 載入失敗（降級運行）: {e}")

        # LLM Adapter（工廠函數模式）
        try:
            from museon.llm.adapters import create_adapter_sync
            self._llm_adapter = create_adapter_sync()
        except Exception as e:
            logger.warning(f"LLMAdapter 載入失敗（降級運行）: {e}")
            self._llm_adapter = None

        # MemoryManager（需要 event_bus 注入）
        try:
            from museon.memory.memory_manager import MemoryManager
            self.memory_manager = MemoryManager(
                workspace=str(self.data_dir / "memory_v3"),
                user_id="boss",
                event_bus=self._event_bus,
            )
        except Exception as e:
            logger.warning(f"MemoryManager 載入失敗（降級運行）: {e}")
            self.memory_manager = None

        # Multi-Agent ContextSwitcher
        self._multiagent_enabled = True
        self._context_switcher = None
        self._multiagent_executor = None  # Phase 4: 並行 LLM 執行器
        self._flywheel_coordinator = None  # Phase 4: 飛輪流動協調器
        self._multiagent_auxiliaries: list = []  # 當前 turn 的輔助部門
        try:
            from museon.multiagent.context_switch import ContextSwitcher
            self._context_switcher = ContextSwitcher()
        except Exception as e:
            logger.warning(f"Multi-Agent 載入失敗（降級運行）: {e}")

        # CommitmentTracker（需要 PulseDB 先初始化）
        self._commitment_tracker = None
        try:
            from museon.pulse.commitment_tracker import CommitmentTracker
            from museon.pulse.pulse_db import get_pulse_db
            _pulse_db = get_pulse_db(self.data_dir)
            self._commitment_tracker = CommitmentTracker(pulse_db=_pulse_db)
        except Exception as e:
            logger.warning(f"CommitmentTracker 載入失敗（降級運行）: {e}")

        # AsyncWriteQueue（全域單例工廠）
        try:
            from museon.pulse.async_write_queue import get_write_queue
            self._wq = get_write_queue()
        except Exception as e:
            logger.warning(f"AsyncWriteQueue 載入失敗（降級為同步寫入）: {e}")
            self._wq = None

        # MetaCognition（需要 brain 反向引用）
        self._metacognition = None
        try:
            from museon.agent.metacognition import MetaCognitionEngine
            self._metacognition = MetaCognitionEngine(
                data_dir=self.data_dir,
                brain=self,
            )
        except Exception as e:
            logger.warning(f"MetaCognitionEngine 載入失敗（降級運行）: {e}")

        # ToolExecutor（需要 brain 反向引用）
        self._tool_executor = None
        try:
            from museon.agent.tools import ToolExecutor
            self._tool_executor = ToolExecutor(
                workspace_dir=str(self.data_dir / "workspace"),
                timeout=180.0,
            )
            self._tool_executor._brain = self
        except Exception as e:
            logger.warning(f"ToolExecutor 載入失敗（降級運行）: {e}")

        # TokenBudgetManager
        self._token_budget = None
        try:
            from museon.pulse.token_budget import TokenBudgetManager
            self._token_budget = TokenBudgetManager(data_dir=self.data_dir)
        except Exception as e:
            logger.warning(f"TokenBudgetManager 載入失敗（降級運行）: {e}")

        # ── Phase 3a: Governor 治理層引用 ──
        self._governor = None  # 由 set_governor() 注入

        # ── 內部狀態 ──
        self._failure_distill_cache: Dict[str, float] = {}
        self._cron_pattern_buffer: List[str] = []
        self._pending_notifications: List[Dict[str, str]] = []

        logger.info(
            f"MUSEON Brain initialized | "
            f"skills: {self.skill_router.get_skill_count()} | "
            f"ceremony_needed: {self.ceremony.is_ceremony_needed()} | "
            f"intuition: {'ON' if self.intuition else 'OFF'} | "
            f"eval: {'ON' if self.eval_engine else 'OFF'} | "
            f"soul_ring: {'ON' if self.ring_depositor else 'OFF'} | "
            f"lattice: {'ON' if self.knowledge_lattice else 'OFF'} | "
            f"plan_engine: {'ON' if self.plan_engine else 'OFF'} | "
            f"sub_agents: {'ON' if self.sub_agent_mgr else 'OFF'} | "
            f"safety_anchor: {'ON' if self.safety_anchor else 'OFF'} | "
            f"sanitizer: {'ON' if self.input_sanitizer else 'OFF'} | "
            f"budget: {'ON' if self.budget_monitor else 'OFF'} | "
            f"memory_v3: {'ON' if self.memory_manager else 'OFF'} | "
            f"tool_use: {'ON' if self._tool_executor else 'OFF'} | "
            f"commitment: {'ON' if self._commitment_tracker else 'OFF'} | "
            f"kernel_guard: {'ON' if self.kernel_guard else 'OFF'} | "
            f"drift_detector: {'ON' if self.drift_detector else 'OFF'} | "
            f"token_budget: {'ON' if self._token_budget else 'OFF'} | "
            f"synapse: {'ON' if self._synapse_network else 'OFF'} | "
            f"tool_muscle: {'ON' if self._tool_muscle else 'OFF'} | "
            f"footprint: {'ON' if self._footprint else 'OFF'} | "
            f"trigger_engine: {'ON' if self._trigger_engine else 'OFF'} | "
            f"registry: {'ON' if self._registry_manager else 'OFF'} | "
            f"recommender: {'ON' if self._recommender else 'OFF'}"
        )

    # ─── Phase 3a: Governor 治理層連接 ───

    def set_governor(self, governor) -> None:
        """注入 Governor 引用，建立治理層 → 大腦的回饋迴路。

        由 server.py startup_event 呼叫。
        Governor.build_context() 產出 GovernanceContext，
        Brain._build_system_prompt() 將其注入到 buffer zone。

        Args:
            governor: Governor 實例
        """
        self._governor = governor
        logger.info("Brain: Governor connected (治理自覺已啟用)")

        # 註冊 LLM 恢復回呼 — 讓 Brain 能自動離開離線模式
        try:
            vs = governor.get_vital_signs()
            if vs:
                vs.register_recovery_callback(self._on_llm_recovered)
                logger.info("Brain: LLM recovery callback registered")
        except Exception as e:
            logger.warning(f"Brain: failed to register recovery callback: {e}")

    def _on_llm_recovered(self) -> None:
        """LLM 恢復時的回呼 — 退出離線模式."""
        if self._offline_flag:
            self._offline_flag = False
            self._last_offline_probe_ts = 0.0
            logger.info("🟢 Brain: LLM recovered — exiting offline mode")
            # 非同步推送恢復通知到 Telegram
            try:
                if self._governor:
                    vs = self._governor.get_vital_signs()
                    if vs:
                        import asyncio
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.ensure_future(vs._push_alert(
                                "🟢 *MUSEON 已恢復上線*\n\n"
                                "LLM 服務已恢復可用，離線模式已自動解除。"
                            ))
            except Exception as e:
                logger.debug(f"Recovery notification failed (non-critical): {e}")

    async def probe_health(self) -> dict:
        """輕量健康探針 — 驗證 Brain 子系統存活，不呼叫 LLM.

        供 VitalSignsMonitor._check_e2e_flow() 使用，取代原本的
        Brain.process() 全 pipeline 呼叫，避免 180s timeout 與身份衝突。
        """
        checks = {}
        try:
            from museon.agent.chat_context import ChatContext
            ChatContext.from_chat_args(
                metadata=None,
                source="vital_signs_probe",
                session_id="__probe__",
                user_id="system",
            )
            checks["chat_context"] = True
        except Exception as e:
            checks["chat_context"] = str(e)

        checks["ceremony"] = self.ceremony is not None
        checks["skill_router"] = self.skill_router is not None
        checks["memory_store"] = self.memory_store is not None
        checks["llm_adapter"] = self._llm_adapter is not None

        all_ok = all(v is True for v in checks.values())
        return {"ok": all_ok, "checks": checks}

    async def process(
        self,
        content: str,
        session_id: str,
        user_id: str = "boss",
        source: str = "telegram",
        metadata: dict = None,
    ):
        """處理一則訊息 — 大腦的主要入口.

        Args:
            content: 使用者訊息文字
            session_id: 會話 ID
            user_id: 使用者 ID
            source: 訊息來源 (telegram, webhook, electron)

        Returns:
            BrainResponse（text + artifacts）或 str（向後相容降級）
        """
        # v10.7: 並行隔離 — 確保同一時間只有一個 process() 使用 self._ctx
        async with self._process_lock:
            return await self._process_inner(content, session_id, user_id, source, metadata)

    async def _process_inner(
        self,
        content: str,
        session_id: str,
        user_id: str = "boss",
        source: str = "telegram",
        metadata: dict = None,
    ):
        """process() 的實際邏輯（被 _process_lock 保護）."""
        try:
            return await self._process_impl(content, session_id, user_id, source, metadata)
        finally:
            # v10.7: 清空 per-turn 狀態，防止跨群組殘留
            self._ctx = None
            self._current_metadata = None
            self._is_group_session = False
            self._group_sender = None

    async def _process_impl(
        self,
        content: str,
        session_id: str,
        user_id: str = "boss",
        source: str = "telegram",
        metadata: dict = None,
    ):
        """process() 的核心實作."""
        _trace_id = (metadata or {}).get("trace_id", "no-trace")
        _report = (metadata or {}).get("_progress_cb") or (lambda s, d="": None)
        logger.info(f"[{_trace_id}] Brain.process() start: session={session_id}, user={user_id}")

        # L2-S1: ChatContext 顯式上下文物件（取代 self._* per-turn 變數）
        from museon.agent.chat_context import ChatContext
        self._ctx = ChatContext.from_chat_args(
            metadata=metadata,
            source=source,
            session_id=session_id,
            user_id=user_id,
        )

        # ── 向後相容 alias（逐步遷移後移除）──
        self._pending_artifacts = self._ctx.pending_artifacts
        self._is_group_session = self._ctx.is_group_session
        self._group_sender = self._ctx.group_sender
        self._current_metadata = self._ctx.metadata
        self._skillhub_mode = self._ctx.skillhub_mode
        self._current_source = self._ctx.current_source

        self._self_modification_detected = self._ctx.self_modification_detected
        _mod_keywords = {
            "修改程式", "改 brain", "改 server", "fix bug", "修 bug",
            "重構", "refactor", "改程式碼", "修改 src", "改 src", "迭代",
            "改寫", "修改檔案", "新增功能", "改 code", "debug",
        }
        if any(kw in content.lower() for kw in _mod_keywords):
            self._self_modification_detected = True

        # ── Step 0: 更新成長階段 ──
        self._update_growth_stage()

        # 元認知變數初始化（跨步驟共享）
        pre_review = None
        # 斷點一修復(方案A)：確保 anima_user 永遠在 scope，即使 Step 2 因例外 early exit
        anima_user = None

        # ── Step 0.5: 承諾自檢 — 檢查到期/逾期承諾 ──
        _report("📋 承諾自檢", "檢查待辦承諾...")
        commitment_context = ""
        if self._commitment_tracker:
            try:
                commitment_context = self._commitment_tracker.build_commitment_context()
                if commitment_context:
                    logger.info("[Commitment] 偵測到待處理承諾，將注入 system prompt")
            except Exception as e:
                logger.warning(f"承諾自檢失敗: {e}")

        # ── Step 0.7: 元認知觀察 — 比對上次預判 vs 本次使用者反應 ──
        _report("🔮 元認知觀察", "比對預判 vs 實際反應")
        self._last_observation_accuracy = None  # v9.0: 供 Step 9.8 morphenix 橋接使用
        if self._metacognition:
            try:
                _mc_observation = self._metacognition.observe_reaction(
                    session_id=session_id,
                    current_user_message=content,
                )
                if _mc_observation and _mc_observation.get("prediction_accuracy") is not None:
                    self._last_observation_accuracy = _mc_observation["prediction_accuracy"]
                    logger.info(
                        f"[MetaCog] 預判觀察: "
                        f"predicted={_mc_observation['predicted_type']}, "
                        f"actual={_mc_observation['actual_type']}, "
                        f"accuracy={_mc_observation['prediction_accuracy']:.2f}"
                    )
            except Exception as e:
                logger.debug(f"元認知觀察跳過: {e}")

        # ── Step 1: 命名儀式 ──
        if self.ceremony.is_ceremony_needed():
            return await self._handle_ceremony(content, session_id)

        # ── Step 1.1: 更名 / 稱呼修正（儀式完成後隨時可改）──
        rename_result = self._try_rename(content)
        if rename_result:
            return rename_result

        # ── Step 1.2: 自我檢查意圖攔截（非阻塞，加 timeout）──
        try:
            from museon.doctor.self_diagnosis import (
                detect_self_check_intent, SelfDiagnosis,
            )
            if detect_self_check_intent(content):
                logger.info("自我檢查意圖偵測命中")
                # asyncio 已在模組頂層 import（line 37），不可在此重複 import
                # 否則 Python 編譯器會將 asyncio 標記為 process() 的 local 變數，
                # 遮蔽全域 import，導致其他分支 UnboundLocalError
                import concurrent.futures

                def _run_diagnosis():
                    try:
                        diag = SelfDiagnosis(data_dir=str(self.data_dir))
                        report = diag.diagnose(auto_repair=False)
                        return diag.format_report_zh(report)
                    except Exception as e:
                        logger.error(f"診斷執行錯誤: {e}", exc_info=True)
                        return f"⚠️ 自我診斷執行時發生錯誤：{e}\n系統仍在運行中。"

                loop = asyncio.get_event_loop()
                try:
                    diagnosis_response = await asyncio.wait_for(
                        loop.run_in_executor(None, _run_diagnosis),
                        timeout=30.0,
                    )
                except asyncio.TimeoutError:
                    logger.warning("自我診斷超時（30s），降級回覆")
                    diagnosis_response = (
                        "⚠️ 自我診斷超時（超過 30 秒），可能有服務回應緩慢。\n"
                        "系統核心仍在運行中，建議稍後再試。"
                    )

                # 記錄到對話歷史
                history = self._get_session_history(session_id)
                history.append({"role": "user", "content": content})
                history.append({"role": "assistant", "content": diagnosis_response})
                return diagnosis_response
        except Exception as e:
            logger.warning(f"自我檢查模組載入失敗（降級跳過）: {e}", exc_info=True)

        # ── Step 1.5: 直覺引擎 — Step -0.5（在 DNA27 路由之前） ──
        _report("🔮 直覺感知", "信號掃描中...")
        intuition_report = None
        if self.intuition:
            try:
                user_history = self._get_session_history(session_id)
                intuition_report = await self.intuition.sense(
                    content=content,
                    session_id=session_id,
                    user_history=[
                        {"content": m["content"]}
                        for m in user_history
                        if m.get("role") == "user"
                    ][-10:],  # 最近 10 條使用者訊息
                )
                if intuition_report and intuition_report.has_significant_findings():
                    logger.info(
                        f"直覺引擎偵測到顯著信號: "
                        f"anomalies={len(intuition_report.anomalies)}, "
                        f"level={intuition_report.overall_level}"
                    )
            except Exception as e:
                logger.warning(f"直覺引擎執行失敗（降級）: {e}")

        # ── Step 1.8: InputSanitizer — L2 輸入防線 ──
        _report("🛡️ 輸入安全檢查", "InputSanitizer 掃描")
        if self.input_sanitizer:
            try:
                # boss 或 Telegram owner = TRUSTED，其餘 = UNKNOWN
                _trusted_ids = {
                    "boss",
                    *[
                        uid.strip()
                        for uid in os.environ.get("TELEGRAM_TRUSTED_IDS", "").split(",")
                        if uid.strip()
                    ],
                }
                trust = "TRUSTED" if user_id in _trusted_ids else "UNKNOWN"
                scan_result = await self.input_sanitizer.sanitize(
                    content=content,
                    source=source,
                    trust_level=trust,
                )
                if not scan_result["is_safe"]:
                    threats = scan_result["threats_detected"]
                    logger.warning(
                        f"InputSanitizer blocked: {threats} "
                        f"(source={source}, trust={trust})"
                    )
                    return (
                        "我注意到這則訊息包含一些我無法處理的內容。\n\n"
                        "如果你有其他問題或需要協助的地方，歡迎換個方式問我。"
                    )
            except Exception as e:
                logger.warning(f"InputSanitizer 執行失敗（降級放行）: {e}")

        # ── Step 2: 載入 ANIMA ──
        _report("📂 載入人格記憶", "ANIMA_MC + ANIMA_USER")
        anima_mc = self._load_anima_mc()
        anima_user = self._load_anima_user()

        # ── Step 2.1: 取得使用者八原語即時值（供路由器消費）──
        # 合併 ANIMA_USER 長期 level + PrimalDetector 當前訊息即時偵測
        _user_primals: Dict[str, int] = {}
        try:
            stored_primals = anima_user.get("eight_primals", {})
            for pk, pv in stored_primals.items():
                if isinstance(pv, dict) and pv.get("level", 0) > 0:
                    _user_primals[pk] = pv["level"]
            # 即時偵測當前訊息的原語（與長期值取 max）
            if self._primal_detector:
                instant_primals = self._primal_detector.detect(content)
                for pk, lvl in instant_primals.items():
                    _user_primals[pk] = max(_user_primals.get(pk, 0), lvl)
        except Exception as _e:
            logger.debug(f"八原語即時值取得失敗（降級）: {_e}")

        # ── Step 2.5: 簡單訊息判定（Pipeline 短路用）──
        # 短訊息且不含指令/分析關鍵字 → 跳過重量級步驟（MetaCog/KnowledgeLattice/Q-Score）
        _is_simple = (
            len(content.strip()) < 15
            and not any(
                kw in content for kw in ["/", "分析", "報告", "計畫", "策略", "研究", "評估"]
            )
        )

        # ── Step 3: DNA27 反射路由器（全 27 叢集 + RoutingSignal）——靈魂先行 ──
        _report("🧬 DNA27 路由", "27 叢集反射判斷中...")
        routing_signal = None
        safety_context = ""
        try:
            from museon.agent.reflex_router import route, build_routing_context
            history = self._get_session_history(session_id)
            # ★ v10.4 Route C: 取前 3 輪路由歷史
            prev_signals = self._routing_history.get(session_id, [])[-3:]
            routing_signal = route(
                content,
                history_len=len(history),
                workspace=str(self.data_dir),
                prev_signals=prev_signals,
                user_primals=_user_primals or None,
            )
            safety_context = build_routing_context(routing_signal)
            # ★ 簡單訊息強制 FAST_LOOP（覆蓋 reflex_router 的誤判）
            if _is_simple and routing_signal.loop != "FAST_LOOP":
                logger.info(
                    f"[DNA27] Simple message override: {routing_signal.loop} → FAST_LOOP"
                )
                routing_signal.loop = "FAST_LOOP"
            logger.info(
                f"[DNA27] RoutingSignal: loop={routing_signal.loop}, "
                f"mode={routing_signal.mode}, "
                f"max_push={routing_signal.max_crystal_push}, "
                f"tiers={routing_signal.tier_scores}, "
                f"time={routing_signal.route_time_ms:.1f}ms"
            )
            # ★ v10.4 Route C: 儲存當輪 signal 到路由歷史
            if session_id not in self._routing_history:
                self._routing_history[session_id] = []
            self._routing_history[session_id].append(routing_signal.to_dict())
            self._last_routing_signal = routing_signal  # PDR Phase 2 消費
            # 只保留最近 5 輪
            if len(self._routing_history[session_id]) > 5:
                self._routing_history[session_id] = self._routing_history[session_id][-5:]
        except Exception as e:
            logger.warning(f"DNA27 ReflexRouter failed (fallback to legacy): {e}")
            # Fallback: 舊版安全叢集偵測
            try:
                from museon.agent.safety_clusters import (
                    detect_safety_clusters, build_safety_context as _legacy_build,
                )
                cluster_scores = detect_safety_clusters(content)
                if cluster_scores:
                    safety_context = _legacy_build(cluster_scores)
            except Exception as e:
                logger.debug(f"安全叢集偵測（legacy fallback）失敗: {e}")

        # ── Step 3.0.3: Phase 3c — 健康感知路由調節 ──
        # 系統不健康時，將 SLOW_LOOP 降級為 EXPLORATION_LOOP，減少資源消耗
        if routing_signal and self._governor:
            try:
                _gov_ctx = self._governor.build_context()
                if (
                    _gov_ctx.is_fresh
                    and _gov_ctx.needs_caution
                    and routing_signal.loop == "SLOW_LOOP"
                ):
                    from dataclasses import replace as _dc_replace
                    routing_signal = _dc_replace(
                        routing_signal,
                        loop="EXPLORATION_LOOP",
                        max_crystal_push=min(
                            routing_signal.max_crystal_push, 5
                        ),
                    )
                    logger.info(
                        f"[Phase3c] 治理調節: SLOW_LOOP → EXPLORATION_LOOP "
                        f"(health={_gov_ctx.health_tier.value})"
                    )
            except Exception as e:
                logger.debug(f"Phase3c 健康感知路由調節失敗（降級）: {e}")

        # ── Step 3.0.5: Multi-Agent 自動路由 — 根據訊息內容自動切換部門 ──
        _report("🔀 Multi-Agent 路由", "自動切換部門...")
        self._multiagent_auxiliaries = []  # 重置每 turn 的輔助部門
        if self._multiagent_enabled and self._context_switcher:
            try:
                from museon.multiagent.okr_router import route_extended
                current_dept = self._context_switcher.current_dept
                target_dept, confidence, auxiliaries = route_extended(
                    content, current_dept,
                    user_primals=_user_primals or None,
                )
                self._multiagent_auxiliaries = auxiliaries
                if target_dept != current_dept and confidence >= 0.4:
                    switch_result = self._context_switcher.switch_to(target_dept)
                    if switch_result.get("switched"):
                        logger.info(
                            f"[MultiAgent] 自動路由: {current_dept} → {target_dept} "
                            f"(confidence={confidence:.2f}, aux={auxiliaries})"
                        )
                self._context_switcher.add_message("user", content)
            except Exception as e:
                logger.debug(f"Multi-Agent 自動路由跳過: {e}")

        # ── Step 3.1: DNA27 路由 — 匹配技能（受 RoutingSignal 調節）──
        _report("🎯 匹配技能模組", "Skill Router 運算中...")
        # ★ v10.4 Route B: 傳入 session 內 skill 使用次數（MoE 衰減）
        session_usage = self._skill_usage.get(session_id, {})
        matched_skills = self.skill_router.match(
            content, top_n=5, routing_signal=routing_signal,
            skill_usage=session_usage,
            user_primals=_user_primals or None,
        )

        # Step 3.1b: VectorBridge 語義匹配輔助（靜默失敗）
        try:
            from museon.vector.vector_bridge import VectorBridge
            vb = VectorBridge(workspace=self.data_dir)
            if vb.is_available():
                semantic_hits = vb.search("skills", content, limit=3)
                existing_names = {s.get("name") for s in matched_skills}
                for hit in semantic_hits:
                    if hit.get("id") not in existing_names:
                        matched_skills.append({
                            "name": hit["id"],
                            "score": hit["score"],
                            "source": "vector",
                        })
        except Exception as e:
            logger.debug(f"向量語意搜尋 Skill 失敗（降級）: {e}")

        skill_names = [s.get("name", "?") for s in matched_skills]
        logger.info(f"DNA27 matched skills: {skill_names}")

        # ── Step 3.15: 主動 Skill 擴展（PDR 軌道 A）──
        from museon.agent.pdr_params import get_pdr_params
        _pdr = get_pdr_params()
        if _pdr.feature_flag and _pdr.proactive_skill_expand and matched_skills:
            _report("🔗 主動擴展 Skill", "根據 connects_to 關係擴展...")
            try:
                _expanded = self._proactive_expand_skills(matched_skills, routing_signal)
                if _expanded:
                    _exp_names = [s.get("name", "?") for s in _expanded]
                    logger.info(f"[PDR] Proactive expand: +{_exp_names}")
                    existing_names = {s.get("name") for s in matched_skills}
                    for s in _expanded:
                        if s.get("name") not in existing_names:
                            matched_skills.append(s)
                            existing_names.add(s.get("name"))
                    skill_names = [s.get("name", "?") for s in matched_skills]
            except Exception as _exp_err:
                logger.debug(f"[PDR] Proactive expand failed: {_exp_err}")

        # ── Step 3.2: P2 決策層信號偵測 ──
        _report("⚖️ 決策層偵測", "掃描重大決策信號...")
        decision_signal = None
        try:
            loop_mode = (
                getattr(routing_signal, "loop", "EXPLORATION_LOOP")
                if routing_signal else "EXPLORATION_LOOP"
            )
            decision_signal = self._detect_major_decision_signal(
                query=content,
                loop_mode=loop_mode,
                anima_mc=anima_mc,
                anima_user=anima_user,
            )
            if decision_signal.is_major:
                logger.info(
                    f"[P2] 重大決策信號偵測: type={decision_signal.decision_type}, "
                    f"stakeholders={decision_signal.stakeholders_count}, "
                    f"confidence={decision_signal.confidence:.2f}"
                )
        except Exception as e:
            logger.debug(f"決策層信號偵測失敗（降級跳過）: {e}")
            decision_signal = DecisionSignal(
                is_major=False,
                decision_type="",
                confidence=0.0,
                stakeholders_count=0,
                impact_horizon_months=0,
                details=f"偵測異常: {str(e)}",
            )

        # 存儲 decision_signal 供 _deliberate() 使用
        self._last_decision_signal = decision_signal

        # ── Step 3.3: P2 決策層路徑短路 — 重大決策先問後答 ──
        # 若偵測到重大決策，立即進入「決策層反問模式」，不進入後續 pipeline
        if decision_signal and decision_signal.is_major:
            try:
                decision_response = await self._handle_decision_layer_path(
                    query=content,
                    decision_signal=decision_signal,
                    session_id=session_id,
                    anima_mc=anima_mc,
                    anima_user=anima_user,
                )

                # 記錄決策層互動
                if session_id:
                    self._sessions.setdefault(session_id, []).append({
                        "role": "assistant",
                        "content": decision_response,
                        "decision_layer": True,
                    })

                # 簡略的決策層事件追蹤
                try:
                    from museon.pulse.heartbeat_engine import log_action
                    log_action(
                        self.data_dir,
                        event="decision_layer_triggered",
                        details={
                            "decision_type": decision_signal.decision_type,
                            "stakeholders": decision_signal.stakeholders_count,
                        },
                    )
                except Exception as _log_e:
                    logger.debug(f"[P2] 決策層日誌記錄失敗: {_log_e}", exc_info=True)

                logger.info("[P2] 決策層路徑完成，返回反問回覆")
                return decision_response

            except Exception as e:
                logger.error(
                    f"[P2] 決策層路徑失敗，降級進入正常 pipeline: {e}",
                    exc_info=True,
                )
                # 降級：繼續進行正常 pipeline

        # ── Step 3.4: P3 策略層並行融合信號偵測 ──
        _report("⚗️ 策略層融合", "多視角信號偵測...")
        # 條件：非 P2 重大決策 + 非簡單訊息 + SLOW/EXPLORATION_LOOP + 有策略層 Skill
        _p3_fusion_signal = P3FusionSignal(
            should_fuse=False, perspectives=[], confidence=0.0, reason="未偵測"
        )
        if not (decision_signal and decision_signal.is_major) and not _is_simple:
            try:
                _p3_loop_mode = (
                    getattr(routing_signal, "loop", "EXPLORATION_LOOP")
                    if routing_signal else "EXPLORATION_LOOP"
                )
                _p3_fusion_signal = self._detect_p3_strategy_layer_signal(
                    query=content,
                    loop_mode=_p3_loop_mode,
                    matched_skills=skill_names,
                )
                if _p3_fusion_signal.should_fuse:
                    logger.info(
                        f"[P3] 策略層融合信號: "
                        f"perspectives={_p3_fusion_signal.perspectives}, "
                        f"confidence={_p3_fusion_signal.confidence:.2f}, "
                        f"reason={_p3_fusion_signal.reason}"
                    )
            except Exception as e:
                logger.debug(f"[P3] 融合信號偵測失敗（降級跳過）: {e}")

        # ── Step 3.5: 計畫引擎觸發檢查 ──
        _report("📐 計畫引擎", "觸發評估中...")
        if self.plan_engine:
            try:
                plan_decision = self.plan_engine.assess_trigger(
                    content=content,
                    context={
                        "matched_skills": skill_names,
                        "session_id": session_id,
                    },
                )
                if plan_decision.should_plan:
                    logger.info(
                        f"計畫引擎觸發: reason={plan_decision.reason}, "
                        f"complexity={plan_decision.complexity_score:.2f}"
                    )
                    # 計畫引擎只觸發建議，不攔截回覆流程
                    # 使用者需透過 /plan 指令啟動完整流程
            except Exception as e:
                logger.warning(f"計畫引擎評估失敗: {e}")

        # ── Step 3.6: SubAgent — 收集已完成子代理的結果 + 推播通知 ──
        sub_agent_context = ""
        if self.sub_agent_mgr:
            try:
                results = self.sub_agent_mgr.collect_results()
                if results:
                    lines = []
                    for r in results:
                        emoji = {"scout": "🔍", "forge": "🔨", "watch": "👁️"}.get(
                            r["type"], "🤖"
                        )
                        status_text = (
                            f"{emoji} {r['name']}（{r['type']}）: {r['status']} — "
                            f"{str(r.get('result', ''))[:200]}"
                        )
                        lines.append(status_text)

                        # 推播通知（純 CPU 模板格式化）
                        self._pending_notifications.append({
                            "source": "subagent",
                            "title": f"{r['name']} 任務{r['status']}",
                            "body": f"類型：{r['type']}\n任務：{r.get('task', '')[:100]}\n結果：{str(r.get('result', ''))[:200]}",
                            "emoji": emoji,
                        })

                    sub_agent_context = (
                        "\n## 子代理回報\n\n"
                        + "\n".join(lines)
                        + "\n\n請在回覆中自然提及這些結果。"
                    )
                    logger.info(f"SubAgent 結果收集：{len(results)} 筆，通知已排隊")
            except Exception as e:
                logger.warning(f"SubAgent 結果收集失敗: {e}")

        # ── Step 3.65: 百合引擎 — 軍師四象限路由 ──
        _report("🎭 百合引擎", "軍師四象限路由...")
        baihe_context = ""
        try:
            _lord_path = self.data_dir / "_system" / "lord_profile.json"
            if _lord_path.exists():
                _lord_raw = _lord_path.read_text(encoding="utf-8")
                _lord_profile = json.loads(_lord_raw)
                # 取得 user_primals（如果有）
                _user_primals = None
                if anima_user:
                    _raw_primals = anima_user.get("eight_primals", {})
                    _user_primals = {
                        k: int(v.get("level", 0)) if isinstance(v, dict) else 0
                        for k, v in _raw_primals.items()
                    }
                from museon.agent.persona_router import PersonaRouter
                _baihe_router = PersonaRouter()
                _baihe_context_data = {
                    "routing_signal_loop": getattr(routing_signal, "loop", "EXPLORATION_LOOP") if routing_signal else "EXPLORATION_LOOP",
                    "top_clusters": getattr(routing_signal, "top_clusters", []) if routing_signal else [],
                    "matched_skills": [s.get("name", "") for s in matched_skills],
                    "has_commitment": bool(commitment_context),
                    "session_history_len": len(self._get_session_history(session_id)),
                    "is_late_night": datetime.now().hour >= 23 or datetime.now().hour < 6,
                }
                _baihe_decision = _baihe_router.baihe_decide(
                    content, _baihe_context_data, _lord_profile, _user_primals,
                )
                baihe_context = self._format_baihe_guidance(_baihe_decision)

                # 更新進諫冷卻（如果本輪進諫了）
                if _baihe_decision.should_advise:
                    _cooldown = _lord_profile.setdefault("advise_cooldown", {})
                    _cooldown["last_advise_ts"] = datetime.now().isoformat()
                    _cooldown["session_advise_count"] = (
                        _cooldown.get("session_advise_count", 0) + 1
                    )
                    _tmp = _lord_path.with_suffix(".json.tmp")
                    _tmp.write_text(
                        json.dumps(_lord_profile, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    _tmp.replace(_lord_path)

                # P3: 寫入 baihe_cache 供 ProactiveBridge 讀取象限
                try:
                    _baihe_cache_path = self.data_dir / "_system" / "baihe_cache.json"
                    _baihe_cache = {
                        "quadrant": _baihe_decision.quadrant.value,
                        "expression_mode": _baihe_decision.expression_mode,
                        "advise_tier": _baihe_decision.advise_tier,
                        "topic_domain": _baihe_decision.topic_domain.value,
                        "ts": datetime.now().isoformat(),
                    }
                    _tmp2 = _baihe_cache_path.with_suffix(".json.tmp")
                    _tmp2.write_text(
                        json.dumps(_baihe_cache, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    _tmp2.replace(_baihe_cache_path)
                except Exception as _cache_e:
                    logger.debug(f"Step 3.65 百合快取寫入失敗: {_cache_e}", exc_info=True)
        except Exception as e:
            logger.debug(f"Step 3.65 百合引擎降級: {e}")

        # ── Step 3.66: 根因偵測層 — 掃描重複模式，偵測問題背後的問題 ──
        _report("🔍 根因偵測", "掃描重複模式...")
        root_cause_hint = ""
        try:
            root_cause_hint = await self._detect_root_cause_hint(
                content=content,
                session_id=session_id,
                matched_skills=matched_skills,
                routing_signal=routing_signal,
                baihe_quadrant=getattr(
                    locals().get("_baihe_decision"), "quadrant", None
                ),
            )
            if root_cause_hint and root_cause_hint.strip():
                logger.info(f"[RootCause] 偵測到重複模式: {root_cause_hint[:100]}")
        except Exception as e:
            logger.debug(f"Step 3.66 根因偵測降級: {e}")

        # ── Step 3.8: 謀定而後動 — 所有路徑前執行（dispatch 之前）──
        _report("🧘 謀定而後動", "深度反思中...")
        # 必須在 dispatch 評估前跑，確保強反射訊號能覆蓋 dispatch 決策
        active_lenses = []
        deliberation_note, active_lenses = self._deliberate(
            content=content,
            routing_signal=routing_signal,
            history=self._get_session_history(session_id),
            anima_mc=anima_mc,
            anima_user=anima_user,
            matched_skills=matched_skills,
            decision_signal=getattr(self, '_last_decision_signal', None),
        )
        if deliberation_note:
            logger.info(f"[Deliberate] 謀定觸發: {deliberation_note[:120]}")
            # 強反射訊號：覆蓋 dispatch——問句/停頓/探詢不應分派多 Skill
            _strong_block_signals = ["停頓訊號", "能力探詢", "純提問", "行為內省", "文件待確認"]
            if any(s in deliberation_note for s in _strong_block_signals):
                matched_skills = []  # 清除 Skill 觸發，阻止 dispatch
                logger.info("[Deliberate] 強反射訊號：matched_skills 已清空，阻止 dispatch 觸發")

        # ── Step 3.7: Dispatch Assessment（分派評估）──
        _report("📤 Dispatch 評估", "分派決策中...")
        # ★ 初始化 P3 審查變數（dispatch/normal 兩條路徑都會在後續引用）
        q_score = None
        thinking_path_summary = ""
        p3_fusion_result = None
        dispatch_decision = self._assess_dispatch(content, matched_skills)
        if dispatch_decision["should_dispatch"] and not _is_simple:
            logger.info(
                f"Dispatch mode 啟動: reason={dispatch_decision['reason']}, "
                f"skills={[s.get('name') for s in dispatch_decision.get('active_skills', [])]}"
            )
            response_text = await self._dispatch_mode(
                content=content,
                session_id=session_id,
                user_id=user_id,
                matched_skills=matched_skills,
                anima_mc=anima_mc,
                anima_user=anima_user,
                sub_agent_context=sub_agent_context,
            )
            # 更新 session history 保持連續性
            history = self._get_session_history(session_id)
            history.append({"role": "user", "content": content})
            history.append({"role": "assistant", "content": response_text})
            if len(history) > 40:
                dropping = history[:-40]
                self._pre_compact_flush(session_id, dropping)
                history[:] = history[-40:]
        else:

            # ── Step 4: 組建系統提示詞（正常 pipeline）──
            _report("📝 組建提示詞", "DNA27 + 技能 + 記憶注入...")
            # 合併百合引擎 + 根因偵測到同一區段
            _combined_baihe = baihe_context
            if root_cause_hint:
                _combined_baihe = (
                    (_combined_baihe + "\n" if _combined_baihe else "")
                    + root_cause_hint
                )

            system_prompt = self._build_system_prompt(
                anima_mc=anima_mc,
                anima_user=anima_user,
                matched_skills=matched_skills,
                sub_agent_context=sub_agent_context,
                safety_context=safety_context,
                user_query=content,
                session_id=session_id,
                routing_signal=routing_signal,
                commitment_context=commitment_context,
                reflection_note=deliberation_note,
                baihe_context=_combined_baihe,
            )

            # ── SkillHub: 注入 skill_builder 上下文 ──
            if self._skillhub_mode == "skill_builder":
                try:
                    skill_list = "\n".join(
                        f"- {s.get('name', '?')}: {s.get('description', '')[:80]}"
                        for s in (getattr(self.skill_router, '_index', []) or [])[:20]
                    )
                    system_prompt += (
                        "\n\n## 技能庫助理模式\n\n"
                        "你正在「技能庫」分頁中協助使用者建構工作流。\n"
                        "引導使用者釐清需求，然後設計工作流草案。\n\n"
                        f"可用技能：\n{skill_list}\n\n"
                        "當準備好工作流草案時，輸出 [WORKFLOW_DRAFT] 標記：\n"
                        "[WORKFLOW_DRAFT]\n"
                        "name: 工作流名稱\n"
                        "description: 一句話描述\n"
                        "schedule_type: cron|once\n"
                        "cron_expression: 30 14 * * 1-5\n"
                        "steps:\n"
                        "- skill_id: 技能ID\n"
                        "  action: 動作描述\n"
                        "  params: {}\n"
                        "  output_key: raw_data\n"
                        "[/WORKFLOW_DRAFT]\n\n"
                        "引導原則：\n"
                        "1. 問業務問題，不問技術問題\n"
                        "2. 確認頻率、觸發時機、結果推送方式\n"
                        "3. 估算每次執行的 token 消耗\n"
                        "4. 一次只推薦一個草案\n"
                    )
                except Exception as e:
                    logger.warning(f"SkillHub skill_builder 注入失敗: {e}")

            # ── Step 4.5: 主動工具偵測（PDR 軌道 A）──
            if _pdr.feature_flag and _pdr.proactive_tool_invoke:
                _report("🔧 主動工具偵測", "掃描工具調用機會...")
                _tool_hints = self._detect_tool_opportunities(content)
                if _tool_hints:
                    system_prompt += f"\n\n[主動工具提示 — 根據使用者訊息偵測到可用工具]\n{_tool_hints}\n如果對回覆有幫助，請主動使用上述工具。"
                    logger.info(f"[{_trace_id}] PDR tool hints injected: {len(_tool_hints)} chars")

            # ── Step 5: 載入對話歷史 ──
            _report("💾 載入對話歷史", "session 歷史載入...")
            history = self._get_session_history(session_id)

            # 加入使用者新訊息
            history.append({"role": "user", "content": content})

            # 保持歷史在 token 限制內
            _loop_mode = getattr(routing_signal, "loop", "") if routing_signal else ""
            _max_history = 10 if _loop_mode == "FAST_LOOP" else 40
            if len(history) > _max_history:
                dropping = history[:-_max_history]
                self._pre_compact_flush(session_id, dropping)
                history[:] = history[-_max_history:]

            # ── Step 5.5: P3 前置融合 — 並行收集多視角洞察注入主回覆 ──
            _report("⚗️ P3 前置融合", "多視角洞察收集...")
            # 核心改變：視角不再「追加」在主回覆後面，而是「交織」在主回覆裡面
            _p3_pre_fusion_ctx = ""
            if _p3_fusion_signal and _p3_fusion_signal.should_fuse:
                try:
                    _p3_pre_fusion_ctx = await self._p3_gather_pre_fusion_insights(
                        query=content,
                        fusion_signal=_p3_fusion_signal,
                        anima_user=anima_user,
                    )
                    if _p3_pre_fusion_ctx:
                        # 注入 system prompt — 讓主 LLM 自然交織多視角
                        system_prompt = (
                            system_prompt
                            + "\n\n"
                            + _p3_pre_fusion_ctx
                        )
                        logger.info(
                            f"[P3] 前置融合注入完成: "
                            f"perspectives={_p3_fusion_signal.perspectives}, "
                            f"ctx_len={len(_p3_pre_fusion_ctx)}"
                        )
                except Exception as e:
                    logger.debug(f"[P3] 前置融合失敗（降級繼續）: {e}")

            # ── Step 6: 呼叫 Claude API（含 tool_use 支援）──
            _report("💬 Claude 思考中", "等待 AI 回應...")
            # v10: 工具永遠開啟 — 讓模型自己決定要不要用工具
            _enable_tools = self._tool_executor is not None

            # 記住 _call_llm 呼叫前的歷史長度，用於清理工具中間訊息
            _history_len_before_llm = len(history)

            # ── Phase 4: Multi-Agent 並行呼叫（有輔助部門時） ──
            _used_multiagent = False
            if (
                self._multiagent_auxiliaries
                and self._multiagent_enabled
                and self._llm_adapter
            ):
                try:
                    from museon.multiagent.multi_agent_executor import MultiAgentExecutor
                    from museon.multiagent.response_synthesizer import synthesize

                    if not self._multiagent_executor:
                        self._multiagent_executor = MultiAgentExecutor(self._llm_adapter)

                    primary_dept = (
                        self._context_switcher.current_dept
                        if self._context_switcher
                        else "core"
                    )

                    # 建構使用者上下文（八原語語義化）
                    _user_ctx = ""
                    try:
                        _user_ctx = self._get_user_context_prompt()
                    except Exception:
                        logger.debug("_get_user_context_prompt 失敗，user_ctx 降級為空字串", exc_info=True)

                    ma_result = await self._multiagent_executor.execute(
                        user_message=content,
                        primary_dept_id=primary_dept,
                        auxiliary_dept_ids=self._multiagent_auxiliaries,
                        user_context=_user_ctx,
                        messages=history,
                    )

                    if not ma_result.primary.error:
                        response_text = synthesize(ma_result)
                        _used_multiagent = True
                        logger.info(
                            f"[MultiAgent] 並行呼叫完成: "
                            f"primary={primary_dept}, "
                            f"aux={self._multiagent_auxiliaries}, "
                            f"latency={ma_result.total_latency_ms}ms"
                        )
                except Exception as e:
                    logger.warning(f"Multi-Agent 並行呼叫失敗（降級單一 LLM）: {e}")

            # 標準單一 LLM 呼叫（無輔助部門或 Multi-Agent 失敗時）
            if not _used_multiagent:
                response_text = await self._call_llm(
                    system_prompt=system_prompt,
                    messages=history,
                    anima_mc=anima_mc,
                    enable_tools=_enable_tools,
                    user_content=content,
                    matched_skills=skill_names,
                )

                # ── Phase 4.5: P3 策略層交織融合簽名 ──
                # v1.22: 視角已在 Step 5.5 前置注入 system_prompt，
                # 主 LLM 回覆自然交織多視角，不再追加獨立區塊。
                # 僅在回覆末尾加入融合來源簽名（使用者知道哪些視角參與了）。
                if _p3_pre_fusion_ctx and _p3_fusion_signal and _p3_fusion_signal.should_fuse:
                    _perspective_emojis = {
                        "strategy": "🌀 wind",
                        "human": "💧 water",
                        "risk": "🔥 fire",
                    }
                    _fused_names = [
                        _perspective_emojis.get(p, p)
                        for p in _p3_fusion_signal.perspectives
                    ]
                    _fusion_tag = "、".join(_fused_names)
                    response_text = (
                        response_text
                        + f"\n\n---\n🧬 *本回覆融合了{_fusion_tag}的觀點*"
                    )
                    logger.info(
                        f"[P3] 交織融合完成: perspectives={_p3_fusion_signal.perspectives}"
                    )

            # ── v10.5: 清理 tool-use 中間訊息 ──
            # _call_llm 會透過 messages（= history 同引用）直接
            # append tool_use/tool_result 中間訊息，這些對後續輪次
            # 沒有價值，且會佔掉 40 條上限。在這裡清除。
            if len(history) > _history_len_before_llm:
                # 保留呼叫前的所有訊息，刪除 _call_llm 加入的中間訊息
                del history[_history_len_before_llm:]

            # 加入助理回覆到歷史
            history.append({"role": "assistant", "content": response_text})

            # ── v10.5: 持久化 session history 到磁碟 ──
            # 離線回覆不存入磁碟，避免污染 session 歷史
            if not self._offline_flag:
                self._save_session_to_disk(session_id)
            else:
                logger.info(f"跳過 session 持久化（離線回覆）")
                self._offline_flag = False  # 重置

            # ── Step 6.2-6.5: P3 並行融合模式 ── (★ v1.21 實裝)
            _report("🔍 品質審查", "PreCognition + Q-Score...")
            # ★ 三角度同步審查：MetaCog + Eval + Health（無串行瓶頸）
            # 改進方向：由原本的 Phase 4.5 策略層融合改為 Step 6 決策審查層並行融合
            pre_review = None
            q_score = None
            thinking_path_summary = ""
            p3_fusion_result = None

            _loop = getattr(routing_signal, "loop", "") if routing_signal else ""
            _skip_p3 = _loop == "FAST_LOOP"
            if not _skip_p3 and (self._metacognition or self.eval_engine):
                try:
                    # ★ P3 並行融合：三個評分模組並行執行（MetaCog + Eval + Health）
                    p3_fusion_result = await self._parallel_review_synthesis(
                        draft_response=response_text,
                        user_query=content,
                        response_content=response_text,
                        routing_signal=routing_signal,
                        matched_skills=skill_names,
                    )

                    # 解包融合結果
                    pre_review = p3_fusion_result.get("pre_review")
                    q_score = p3_fusion_result.get("q_score")
                    thinking_path_summary = p3_fusion_result.get("thinking_path_summary", "")
                    fusion_verdict = p3_fusion_result.get("fusion_verdict", "pass")

                    # 記錄 Q-Score 評分（如果有）
                    if q_score:
                        logger.debug(
                            f"Q-Score: {q_score.score:.3f} ({q_score.tier}) | "
                            f"U={q_score.understanding:.2f} D={q_score.depth:.2f} "
                            f"C={q_score.clarity:.2f} A={q_score.actionability:.2f}"
                        )

                    # Step 6.3: 根據融合決策執行修改
                    if fusion_verdict == "revise" and pre_review:
                        logger.info(
                            f"[P3-Fusion] REVISE 決策 | "
                            f"feedback={pre_review.get('feedback', '')[:80]}..."
                        )
                        refined = await self._refine_with_precog_feedback(
                            system_prompt=system_prompt,
                            messages=history[:-1] if len(history) > 1 else history,
                            feedback=pre_review.get("feedback", ""),
                        )
                        if refined:
                            response_text = refined
                            # 更新歷史中的回覆
                            history[-1] = {"role": "assistant", "content": response_text}
                    elif fusion_verdict == "alert":
                        logger.warning(
                            "[P3-Fusion] ALERT 決策 | 系統健康度臨界，建議監控"
                        )

                except Exception as e:
                    logger.warning(f"P3 並行融合異常，降級運行: {e}")

        # ── Step 7: 持久化到記憶 ──
        _report("💾 寫入記憶", "四通道持久化...")
        await self._persist_memory(
            session_id=session_id,
            user_content=content,
            assistant_content=response_text,
            matched_skills=skill_names,
        )

        # ── Step 7.5: 自動失敗蒸餾 ──
        try:
            self._auto_failure_distill(
                user_message=content,
                response=response_text,
                user_id=user_id,
            )
        except Exception as e:
            logger.warning(f"Failure distill 失敗: {e}")

        # ── Step 7.6: 隱式自我診斷（偵測到嚴重失敗時觸發）──
        try:
            from museon.doctor.self_diagnosis import SelfDiagnosis
            _IMPLICIT_TRIGGERS = ("tool_error", "timeout", "network_issue")
            _fail_signals = ("Error", "SDK Error", "Exception", "timeout", "超時")
            if any(s in response_text for s in _fail_signals):
                if self._event_bus:
                    from museon.core.event_bus import SELF_DIAGNOSIS_TRIGGERED
                    self._event_bus.publish(SELF_DIAGNOSIS_TRIGGERED, {
                        "user_id": user_id,
                        "trigger": "implicit",
                        "context": content[:200],
                    })
                # 背景快速診斷（不阻塞回覆）
                diag = SelfDiagnosis(data_dir=str(self.data_dir))
                quick = diag.diagnose_quick()
                if not quick.all_ok:
                    logger.warning(
                        f"隱式自我診斷發現 {quick.total_issues} 個問題"
                    )
        except Exception as e:
            logger.debug(f"隱式自我診斷跳過: {e}")

        # ── Step 8: 追蹤技能使用 ──
        _report("📊 追蹤技能使用", "使用率統計...")
        # 從 P3 融合結果推導 outcome
        _skill_outcome = ""
        if q_score is not None:
            _tier = getattr(q_score, "tier", "medium")
            if _tier in ("high", "excellent"):
                _skill_outcome = "success"
            elif _tier in ("low", "critical"):
                _skill_outcome = "failed"
            else:
                _skill_outcome = "partial"
        self._track_skill_usage(
            skill_names=skill_names,
            user_content=content,
            response_length=len(response_text),
            outcome=_skill_outcome,
        )

        # ★ v10.4 Route B: 更新 session 內 skill 使用次數（MoE 衰減用）
        if skill_names:
            if session_id not in self._skill_usage:
                self._skill_usage[session_id] = {}
            for sk_name in skill_names:
                if sk_name:
                    self._skill_usage[session_id][sk_name] = (
                        self._skill_usage[session_id].get(sk_name, 0) + 1
                    )

        # ── Step 8.1: 演化數據輸入 — Synapse / ToolMuscle / Footprint ──
        _report("🧬 演化數據", "Synapse + ToolMuscle + Footprint...")
        if skill_names and not self._offline_flag:
            # Synapse: 記錄同次對話中共同觸發的技能組合
            if self._synapse_network and len(skill_names) >= 2:
                try:
                    for i in range(len(skill_names)):
                        for j in range(i + 1, len(skill_names)):
                            if skill_names[i] and skill_names[j]:
                                self._synapse_network.co_fire(
                                    skill_names[i], skill_names[j]
                                )
                except Exception as e:
                    logger.debug(f"Synapse co_fire 記錄失敗: {e}")

            # ToolMuscle: 記錄技能使用（視為工具使用）
            if self._tool_muscle:
                try:
                    for sk in skill_names:
                        if sk:
                            self._tool_muscle.record_use(
                                tool_id=sk, success=True
                            )
                except Exception as e:
                    logger.debug(f"ToolMuscle record_use 失敗: {e}")

            # Footprint: 記錄決策軌跡（L2）+ 行為足跡（L1）
            if self._footprint:
                try:
                    self._footprint.trace_decision(
                        decision_type="skill_routing",
                        chosen=",".join(skill_names[:3]),
                        alternatives=[s for s in skill_names[3:] if s],
                        reasoning=f"top{len(skill_names)}_ranked",
                        context=content[:100] if content else "",
                    )
                except Exception as e:
                    logger.debug(f"Footprint trace_decision 失敗: {e}")
                try:
                    self._footprint.trace_action(
                        action_type="skill_routing",
                        target=",".join(s for s in skill_names if s),
                        params_summary=content[:100] if content else "",
                        result_summary=response_text[:100] if response_text else "",
                        success=True,
                    )
                except Exception as e:
                    logger.debug(f"Footprint trace_action 失敗: {e}")
                # 認知回執（Compact Cognitive Receipt）
                # v1.1: 5 欄位從硬編碼改為動態讀取（Observatory 可觀測性實質化）
                try:
                    _loop_map = {"FAST_LOOP": "F", "EXPLORATION_LOOP": "E", "SLOW_LOOP": "S"}
                    _loop_short = _loop_map.get(routing_signal.loop, "E") if routing_signal else "E"
                    _energy_map = {"FAST_LOOP": "high", "EXPLORATION_LOOP": "neutral", "SLOW_LOOP": "deep"}
                    _energy = _energy_map.get(routing_signal.loop, "neutral") if routing_signal else "neutral"
                    # v3.0: Phase 0 訊號分流 — 六類判定（取代空值）
                    _p0 = self._classify_p0_signal(content, routing_signal, skill_names)
                    # v3.0: meta_note — 傳遞 thinking_path_summary（取代硬編碼空值）
                    _meta = ""
                    if thinking_path_summary:
                        _meta = thinking_path_summary[:50]
                    self._footprint.trace_cognitive({
                        "p0_signal": _p0,
                        "qc_verdict": "pass" if not getattr(self, '_last_qc_clarify', False) else "clarify",
                        "user_energy": _energy,
                        "c15_active": "text-alchemy" not in skill_names,
                        "resonance": "resonance" in skill_names,
                        "loop": _loop_short,
                        "top_skills": skill_names[:3],
                        "meta_note": _meta,
                    })
                except Exception as e:
                    logger.debug(f"Footprint trace_cognitive 失敗: {e}")

        # ── Step 8.5: 靈魂日記 — 偵測日記級事件（v2.0 降低門檻版）──
        _report("🌀 靈魂日記", "偵測年輪級事件...")
        # ★ Pipeline 短路：簡單訊息跳過 Soul Ring（q_score 已被跳過，此處自然不觸發）
        # 追蹤 Q-Score 歷史（保留最近 50 筆）並持久化
        if q_score is not None:
            self._q_score_history.append(q_score.score)
            if len(self._q_score_history) > 50:
                self._q_score_history = self._q_score_history[-50:]
            try:
                self._q_score_history_path.parent.mkdir(parents=True, exist_ok=True)
                self._q_score_history_path.write_text(
                    json.dumps(self._q_score_history), encoding="utf-8"
                )
            except Exception as e:
                logger.warning(f"Q-score 歷史寫入失敗: {e}")

        if self.ring_depositor:
            try:
                ring_event = self.ring_depositor.detect_ring_event(
                    user_content=content,
                    response_content=response_text,
                    q_score=q_score.score if q_score else None,
                    q_score_history=self._q_score_history if self._q_score_history else None,
                    content_length=len(content) if content else 0,
                )
                if ring_event:
                    logger.info(
                        f"靈魂日記事件偵測: type={ring_event.get('ring_type')} "
                        f"entry_type={ring_event.get('entry_type', 'event')}"
                    )
                    self.ring_depositor.deposit_soul_ring(
                        ring_type=ring_event["ring_type"],
                        description=ring_event["description"],
                        context=ring_event.get("context", ""),
                        impact=ring_event.get("impact", ""),
                        entry_type=ring_event.get("entry_type", "event"),
                        milestone_name=ring_event.get("milestone_name"),
                        metrics=ring_event.get("metrics"),
                        failure_description=ring_event.get("failure_description"),
                        root_cause=ring_event.get("root_cause"),
                        prevention=ring_event.get("prevention"),
                        original_behavior=ring_event.get("original_behavior"),
                        correction=ring_event.get("correction"),
                        calibrated_value=ring_event.get("calibrated_value"),
                    )
            except Exception as e:
                logger.warning(f"靈魂日記偵測失敗: {e}")

        # ── Step 8.6: 知識晶格 — 對話後掃描 + 自動結晶 ──
        _report("💎 知識晶格", "對話後掃描 + 自動結晶...")
        # CASTLE Layer 2: 離線回應不進入結晶管線
        # ★ Pipeline 短路：簡單訊息跳過 KnowledgeLattice 掃描
        if self.knowledge_lattice and not self._offline_flag and not _is_simple:
            try:
                candidates = self.knowledge_lattice.post_conversation_scan(
                    conversation_data=[
                        {"role": "user", "content": content},
                        {"role": "assistant", "content": response_text},
                    ],
                )
                # 自動結晶化候選（不再丟棄回傳值）
                if candidates:
                    created = self.knowledge_lattice.auto_crystallize_candidates(
                        candidates=candidates,
                        source_context=f"session={session_id or 'unknown'}",
                    )
                    if created:
                        logger.info(
                            f"知識結晶自動生成: {len(created)} 顆 "
                            f"({', '.join(created)})"
                        )
                        # 更新 ANIMA_MC 結晶計數
                        self._update_crystal_count(len(created))
            except Exception as e:
                logger.warning(f"知識晶格掃描失敗: {e}")

        # ── Step 8.6.5: Crystal Actuator 回饋迴圈（P3）──
        # 如果本次對話中結晶行為規則參與了回覆，記錄正面回饋。
        # 負面回饋由使用者不滿意時的 Q-Score 低分觸發（未來擴展）。
        if self.crystal_actuator:
            try:
                active_rules = self.crystal_actuator.get_active_rules()
                if active_rules and response_text:
                    # 簡易正面回饋：如果規則存在且回覆順利產出 → +1
                    # 更精細的回饋在未來由 Q-Score 驅動
                    for rule in active_rules:
                        rule_id = rule.get("rule_id", "")
                        directive = rule.get("directive", "")
                        summary = rule.get("summary", "")
                        # 檢查回覆是否可能受到此規則影響
                        if directive and (
                            any(kw in response_text for kw in summary.split()[:3])
                            or any(kw in content for kw in summary.split()[:3])
                        ):
                            self.crystal_actuator.record_feedback(
                                rule_id, positive=True,
                            )
            except Exception as e:
                logger.debug(f"Crystal Actuator 回饋記錄失敗: {e}")

        # ── Step 8.7: 承諾掃描 — 偵測回覆中的承諾並登記 ──
        _report("📋 承諾掃描", "偵測回覆中的承諾...")
        if self._commitment_tracker:
            try:
                new_commitments = self._commitment_tracker.scan_and_register(
                    response=response_text,
                    user_message=content,
                    session_id=session_id,
                )
                # 同時檢查本次回覆是否兌現了之前的承諾
                fulfilled = self._commitment_tracker.check_fulfillment(
                    response=response_text,
                    user_message=content,
                )
                # ANIMA 連動：兌現承諾 → zhen +2
                # ★ 寫入排隊：PulseDB 寫入通過 WriteQueue 序列化
                if fulfilled and hasattr(self, '_soul_ring_store'):
                    try:
                        from museon.pulse.pulse_db import get_pulse_db
                        _pdb = get_pulse_db(self.data_dir)
                        for _fid in fulfilled:
                            if self._wq:
                                self._wq.enqueue(
                                    f"commitment_zhen_{_fid}",
                                    _pdb.log_anima_change,
                                    element="zhen", delta=2,
                                    reason=f"承諾兌現: {_fid}",
                                    absolute_after=0,
                                )
                            else:
                                _pdb.log_anima_change(
                                    element="zhen", delta=2,
                                    reason=f"承諾兌現: {_fid}",
                                    absolute_after=0,
                                )
                    except Exception as e:
                        logger.debug(f"承諾兌現 ANIMA 記錄失敗: {e}")
            except Exception as e:
                logger.warning(f"承諾掃描失敗: {e}")

        # ── Step 8.8: 自主排程偵測（純 CPU）──
        self._detect_cron_patterns(content)

        # ── Step 9.0: Memory Gate 意圖分類（v1.13 新增）──
        # 在記憶寫入前先判斷意圖，避免「越否認越強化」迴圈
        _memory_action = None
        if not self._offline_flag and self._memory_gate:
            try:
                _memory_intent = self._memory_gate.classify_intent(content)
                _memory_action = self._memory_gate.decide_action(_memory_intent)
                if _memory_action.action != "ADD":
                    logger.info(
                        f"MemoryGate: {_memory_action.action} — {_memory_action.reason}"
                    )
            except Exception as e:
                logger.warning(f"MemoryGate 分類失敗（降級到無閘門）: {e}")
                _memory_action = None

        # ── Step 9.2: 事實更正偵測（P0 記憶事實覆寫）──
        # v1.13: 提前到 Step 9 之前，確保糾正在記憶寫入前觸發
        # v3.0: 群組也啟用事實更正（移除 _is_group_session 閘門）
        if not self._offline_flag:
            try:
                _should_correct = (
                    (_memory_action is not None and _memory_action.trigger_correction)
                    or self._detect_fact_correction(content)
                )
                if _should_correct:
                    asyncio.ensure_future(
                        self._handle_fact_correction(
                            content, response_text, session_id,
                        )
                    )
            except Exception as e:
                logger.warning(f"事實更正偵測失敗: {e}")

        # ── Step 9: 條件式更新 ANIMA_USER（被動觀察 — 八原語 + 七層 + 四觀察引擎） ──
        _report("👤 更新使用者畫像", "八原語 + 觀察引擎...")
        # CASTLE Layer 2: 離線回應不進入使用者觀察管線
        # v2.0: 群組訊息也更新 ANIMA_USER（權重 ×0.5），不再完全跳過
        # v1.13: Memory Gate 可 suppress 八原語和事實寫入
        _suppress_primals = _memory_action.suppress_primals if _memory_action else False
        _suppress_facts = _memory_action.suppress_facts if _memory_action else False
        if not self._offline_flag and anima_user is not None:
            if self._is_group_session:
                # 群組模式：同時進入 ANIMA_USER（半權重）+ 外部用戶觀察
                self._observe_user(
                    content, anima_user,
                    response_content=response_text,
                    skill_names=skill_names,
                    context_type="group",  # v2.0: 標記群組來源，觀察引擎內部降權 ×0.5
                    suppress_primals=_suppress_primals,
                    suppress_facts=_suppress_facts,
                )
                self._observe_external_user(
                    content,
                    user_id=user_id,
                    sender_name=self._group_sender,
                    response_content=response_text,
                    metadata=metadata,
                )
            else:
                # DM 模式：全權重更新 ANIMA_USER
                self._observe_user(
                    content, anima_user,
                    response_content=response_text,
                    skill_names=skill_names,
                    suppress_primals=_suppress_primals,
                    suppress_facts=_suppress_facts,
                )

        # ── Step 9.5: 更新 ANIMA_MC（自我觀察 — 八原語 + 能力追蹤） ──
        _report("🪞 自我觀察", "ANIMA_MC 八原語更新...")
        # CASTLE Layer 2: 離線/降級模式下的輸出不進入自觀察管線
        if self._offline_flag:
            logger.info(
                "Step 9.5 跳過：離線旗標為 True，降級回應不進入自觀察"
            )
        else:
            try:
                self._observe_self(
                    skill_names=skill_names,
                    response_length=len(response_text),
                )
            except Exception as e:
                logger.warning(f"ANIMA_MC 自我觀察失敗: {e}")

        # ── Step 9.7: 元認知預判 — 預測使用者對本次回覆的反應 ──
        _report("🔮 元認知預判", "預測使用者反應...")
        # ★ 寫入排隊：predict_reaction 寫入 PulseDB，通過 WriteQueue 序列化
        if self._metacognition:
            try:
                _predict_fn = self._metacognition.predict_reaction
                _predict_kwargs = dict(
                    session_id=session_id,
                    user_query=content,
                    response=response_text,
                    routing_signal=routing_signal,
                    matched_skills=skill_names,
                    pre_review=pre_review,
                )
                if self._wq:
                    self._wq.enqueue("metacog_predict", _predict_fn, **_predict_kwargs)
                else:
                    _predict_fn(**_predict_kwargs)
            except Exception as e:
                logger.debug(f"元認知預判跳過: {e}")

        # ── Step 9.8: Morphenix 即時筆記橋接（v9.0）──
        # PreCognition REVISE 或 PostCognition 觀察準確率低 → 自動寫入 morphenix 筆記
        try:
            _write_note = False
            _note_content = ""
            if pre_review and pre_review.get("verdict") == "revise":
                _write_note = True
                _note_content = f"[PreCognition] 修改建議: {pre_review.get('feedback', '')[:200]}"
            if hasattr(self, "_last_observation_accuracy"):
                if self._last_observation_accuracy is not None and self._last_observation_accuracy <= 0.3:
                    _write_note = True
                    _note_content += f"\n[PostCognition] 預判準確率低: {self._last_observation_accuracy:.2f}"
            if _write_note and _note_content.strip():
                self._write_morphenix_note(
                    category="metacog_insight",
                    content=_note_content.strip(),
                )
        except Exception as e:
            logger.debug(f"Morphenix 即時筆記跳過: {e}")

        # ── Step 10: 發布 BRAIN_RESPONSE_COMPLETE 事件（WEE 自動循環入口）──
        _report("✅ 完成", "準備發送回覆...")
        if self._event_bus:
            try:
                from museon.core.event_bus import BRAIN_RESPONSE_COMPLETE
                _mc_payload = {}
                if pre_review:
                    _mc_payload = {
                        "pre_verdict": pre_review.get("verdict", "skipped"),
                        "pre_revision_applied": pre_review.get("verdict") == "revise",
                    }
                self._event_bus.publish(BRAIN_RESPONSE_COMPLETE, {
                    "user_id": user_id,
                    "user_content": content,
                    "response_content": response_text,
                    "matched_skills": skill_names,
                    "q_score_tier": q_score.tier if q_score else "medium",
                    "source": source,
                    "session_id": session_id,
                    "metacognition": _mc_payload,
                })
            except Exception as e:
                logger.warning(f"BRAIN_RESPONSE_COMPLETE 事件發布失敗: {e}")

        # ── SkillHub: 解析 [WORKFLOW_DRAFT] 標記 ──
        if self._skillhub_mode == "skill_builder":
            try:
                import re
                draft_match = re.search(
                    r'\[WORKFLOW_DRAFT\](.*?)\[/WORKFLOW_DRAFT\]',
                    response_text, re.DOTALL,
                )
                if draft_match:
                    from museon.gateway.message import Artifact
                    draft_content = draft_match.group(1).strip()
                    self._pending_artifacts.append(Artifact(
                        type="workflow_draft",
                        filename="draft.yaml",
                        content=draft_content,
                        mime_type="application/x-yaml",
                        description="工作流草案",
                    ))
                    # 從回應中移除原始 draft 標記
                    response_text = response_text.replace(
                        draft_match.group(0), ""
                    ).strip()
            except Exception as e:
                logger.warning(f"SkillHub draft 解析失敗: {e}")

        # P5: 偵測用戶休息/免打擾意圖 → 發布 USER_QUIET_MODE 事件
        self._detect_and_publish_quiet_mode(content)

        # P0: 謀定而後動——思考軌跡分級顯示
        final_response = response_text
        _display_loop = getattr(routing_signal, 'loop', 'EXPLORATION_LOOP') if routing_signal else 'EXPLORATION_LOOP'
        if _display_loop != "FAST_LOOP":
            if _display_loop == "SLOW_LOOP" and thinking_path_summary:
                final_response = f"\U0001f9e0 {thinking_path_summary}\n\n{response_text}"
                logger.debug(f"[P0] SLOW_LOOP 回覆前置注入思考摘要")
            elif active_lenses:
                non_default_lenses = [l for l in active_lenses if l != "c15"]
                if non_default_lenses:
                    lens_hint = " \u2192 ".join(non_default_lenses)
                    final_response = f"\U0001f9e0 {lens_hint}\n\n{response_text}"
                    logger.debug(f"[P0] 透鏡提示注入: {lens_hint}")

        # P1: 主動盲點提醒——根據探索度決定是否注入「你可能沒想到」提示
        try:
            exploration_score = self._estimate_user_exploration_level(anima_user)

            # 計算本次提醒的出現概率（技術型<20%不提示，均衡型30-50%，探索型>60%較常提示）
            should_show_blindspot = False
            if exploration_score < 0.25:
                # 技術型：降低頻率（10% 概率）
                should_show_blindspot = (len(content) % 10 == 0)
            elif exploration_score < 0.55:
                # 均衡型：中等頻率（40% 概率）
                should_show_blindspot = (len(content) % 10 < 4)
            else:
                # 探索型：較高頻率（60% 概率）
                should_show_blindspot = (len(content) % 10 < 6)

            if should_show_blindspot:
                from museon.agent.eval_engine import get_blindspot_hint_for_query
                blindspot_hint = get_blindspot_hint_for_query(
                    query=content,
                    matched_skills=[s.get("name") for s in matched_skills] if matched_skills else None,
                )
                if blindspot_hint:
                    # 在思考路徑和回應之間插入盲點提醒
                    if thinking_path_summary:
                        final_response = f"【我的思考路徑】{thinking_path_summary}\n\n【順便一提】{blindspot_hint}\n\n{response_text}"
                    else:
                        final_response = f"【順便一提】{blindspot_hint}\n\n{response_text}"
                    logger.debug(f"[P1] 盲點提醒已注入 | 探索度={exploration_score:.2f}")
        except Exception as e:
            logger.debug(f"[P1] 盲點提醒注入失敗（降級繼續）: {e}")

        # v9.0: 返回 BrainResponse（含 artifacts）
        try:
            from museon.gateway.message import BrainResponse
            return BrainResponse(
                text=final_response,
                artifacts=list(self._pending_artifacts),
            )
        except Exception as e:
            logger.debug(f"BrainResponse 建立失敗，降級為純字串: {e}")
            return final_response  # 降級：返回純 str

    # ═══════════════════════════════════════════
    # 命名儀式
    # ═══════════════════════════════════════════

    async def _handle_ceremony(self, content: str, session_id: str) -> str:
        """處理命名儀式流程.

        注意：ceremony.py 會直接寫入 ANIMA_MC.json，但它只寫入精簡結構。
        Brain 負責在儀式完成後，將精簡結構合併回完整的 ANIMA_MC 格式。
        """
        stage = self.ceremony.get_current_stage()

        if stage == "not_started":
            # 備份原始 ANIMA_MC（ceremony 會覆寫）
            self._pre_ceremony_anima = self._load_anima_mc()
            return self.ceremony.start_ceremony()

        elif stage == "requesting_name":
            success, response = self.ceremony.receive_name(content)
            if success:
                # ceremony 寫了精簡結構，合併回完整格式
                self._merge_ceremony_into_anima_mc()
            return response

        elif stage == "name_received":
            success, response, user_model = self.ceremony.receive_answers(content)
            if success:
                # 合併儀式最終結果到完整 ANIMA_MC
                self._merge_ceremony_into_anima_mc()
                # 更新 ANIMA_USER
                self._update_anima_user_from_ceremony(user_model)
                logger.info("Naming ceremony completed!")
            return response

        elif stage == "completed":
            # 儀式已完成，不應該走到這裡
            return "命名儀式已完成，讓我們開始吧！"

        else:
            # 重啟儀式
            _, prompt = self.ceremony.resume_ceremony()
            return prompt

    def _merge_ceremony_into_anima_mc(self) -> None:
        """將 ceremony 寫入的精簡 ANIMA_MC 合併回完整結構.

        ceremony.py 的 _initialize_anima_l1() 會創建：
          {identity, self_awareness, boss, ceremony}
        但完整的 ANIMA_MC 還需要：
          {version, type, personality, capabilities, evolution, memory_summary}

        ★ 通過 AnimaMCStore.update() 原子讀改寫，避免繞過 Store 鎖。
        """
        base = getattr(self, "_pre_ceremony_anima", None) or {}

        def _do_merge():
            def updater(ceremony_data):
                ceremony_identity = ceremony_data.get("identity", {})
                ceremony_awareness = ceremony_data.get("self_awareness", {})
                ceremony_boss = ceremony_data.get("boss", {})
                ceremony_status = ceremony_data.get("ceremony", {})

                full_anima = {
                    "version": base.get("version", "1.0.0"),
                    "type": base.get("type", "museon"),
                    "description": base.get("description",
                        "MUSEON 自身的人格檔 — 可被 MUSEON 閱讀與改寫"),

                    "identity": {
                        "name": ceremony_identity.get("name"),
                        "birth_date": ceremony_identity.get("birth_date"),
                        "growth_stage": "adult",
                        "days_alive": ceremony_identity.get("days_alive", 0),
                        "naming_ceremony_completed": ceremony_status.get("completed", False),
                    },

                    "self_awareness": ceremony_awareness,

                    "personality": base.get("personality", {
                        "core_traits": [
                            "好奇心驅動", "真誠不做作", "行動導向", "安靜觀察優先"
                        ],
                        "communication_style": "簡潔、有溫度、用繁體中文",
                        "growth_mindset": "每次互動都是學習機會",
                    }),

                    "capabilities": base.get("capabilities", {
                        "loaded_skills": [],
                        "forged_skills": [],
                        "active_workflows": [],
                        "skill_proficiency": {},
                    }),

                    "evolution": base.get("evolution", {
                        "current_stage": "adult",
                        "stage_history": [],
                        "iteration_count": 0,
                        "last_self_review": None,
                        "morphenix_proposals": [],
                        "known_blindspots": [],
                        "milestones": [{
                            "type": "birth",
                            "event": "naming_ceremony",
                            "timestamp": ceremony_identity.get("birth_date"),
                        }],
                    }),

                    "memory_summary": base.get("memory_summary", {
                        "total_interactions": 0,
                        "sessions_count": 0,
                        "knowledge_crystals": 0,
                        "last_nightly_fusion": None,
                    }),

                    "boss": ceremony_boss,
                    "ceremony": ceremony_status,
                }
                return full_anima

            result = self._anima_mc_store.update(updater)
            if result:
                name = result.get("identity", {}).get("name", "?")
                logger.info(f"Merged ceremony data into full ANIMA_MC: name={name}")

        if self._wq:
            self._wq.enqueue("merge_ceremony_anima_mc", _do_merge)
        else:
            _do_merge()

    def _try_rename(self, content: str) -> Optional[str]:
        """偵測更名/稱呼修正意圖，直接更新 ANIMA.

        支援模式：
        - 「你的名字叫XX」「你叫XX」→ 更新 ANIMA_MC name
        - 「叫我XX」「我的名字是XX」→ 更新 ANIMA_USER + ANIMA_MC boss name
        - 兩者可同時出現在一則訊息中

        Returns:
            確認訊息（如果有更名），否則 None（繼續正常流程）
        """
        import re

        # ── 前置過濾：疑問句不應觸發改名 ──
        # 含疑問詞或問號的句子是在「詢問」而非「指令」
        question_indicators = [
            '什麼', '誰', '哪', '幾', '為什麼', '怎麼', '嗎', '？', '?',
            '是不是', '是否', '到底是', '難道',  # 反問句型
        ]
        if any(q in content for q in question_indicators):
            return None

        # ── 前置過濾：長訊息（>40字）幾乎不可能是改名指令 ──
        if len(content) > 40:
            return None

        new_my_name = None
        new_boss_name = None

        # 偵測 MUSEON 更名
        mc_patterns = [
            r'你的名字(?:是|叫)(.{1,15}?)(?:\s|$|，|,|。|！|？|\?|\n)',
            r'你(?:就)?叫(.{1,15}?)(?:\s|$|，|,|。|！|？|\?|\n|吧)',
            r'(?:改名|更名)(?:為|成|叫)(.{1,15}?)(?:\s|$|，|,|。|！|？|\?|\n)',
            r'以後(?:就)?叫(.{1,15}?)(?:\s|$|，|,|。|！|？|\?|\n)',
        ]
        _MC_NEGATION_PREFIXES = ["不要", "別", "不用", "不是", "不要再", "別再", "不必"]
        for pat in mc_patterns:
            m = re.search(pat, content)
            if m:
                candidate = m.group(1).strip().rstrip('吧了啦喔')
                # ── 否定前綴檢查 ──
                match_start = m.start()
                pre_text = content[max(0, match_start - 5):match_start]
                if any(neg in pre_text for neg in _MC_NEGATION_PREFIXES):
                    continue  # 跳過否定語境
                if candidate and len(candidate) >= 1:
                    new_my_name = candidate
                    break

        # 偵測 Boss 稱呼修正
        _NEGATION_PREFIXES = ["不要", "別", "不用", "不是", "不要再", "別再", "不必", "不想"]
        boss_patterns = [
            r'叫我(.{1,15}?)(?:\s|$|，|,|。|！|？|\?|\n)',
            # ★ 排除「我是不是」「我是否」等反問句型
            r'我(?:的名字)?(?:是|叫)(?!不是|不會|沒有|不想|不能|不行)(.{1,15}?)(?:\s|$|，|,|。|！|？|\?|\n)',
            r'稱呼我(.{1,15}?)(?:\s|$|，|,|。|！|？|\?|\n)',
        ]
        # ★ 候選名字不應以否定詞或動詞開頭
        _CANDIDATE_BAD_PREFIXES = (
            '不是', '不用', '不要', '別', '沒有', '不能', '不想', '不會',
            '不太', '不確', '不知', '不對', '不行', '不敢', '不好',
            '在', '要', '會', '能', '想', '可以', '應該', '一個',
            '做', '去', '來', '有', '很', '這', '那', '怎', '什',
        )
        for pat in boss_patterns:
            m = re.search(pat, content)
            if m:
                candidate = m.group(1).strip()
                # ── 否定前綴檢查：「不要叫我XX」不是改名 ──
                match_start = m.start()
                pre_text = content[max(0, match_start - 5):match_start]
                if any(neg in pre_text for neg in _NEGATION_PREFIXES):
                    continue  # 跳過否定語境的匹配
                # ★ 候選名字本身以否定詞/動詞開頭 → 不是名字
                if candidate and any(candidate.startswith(bp) for bp in _CANDIDATE_BAD_PREFIXES):
                    continue
                # 過濾明顯非名字的
                if candidate and len(candidate) >= 1 and candidate not in (
                    '你', '他', '她', '它', '的', '一個', '個', '你的創造者',
                ):
                    new_boss_name = candidate
                    break

        if not new_my_name and not new_boss_name:
            return None  # 沒有偵測到更名意圖

        # 更新 ANIMA_MC
        anima_mc = self._load_anima_mc()
        if anima_mc:
            if new_my_name:
                anima_mc["identity"]["name"] = new_my_name
                anima_mc["self_awareness"]["who_am_i"] = (
                    f"我是 {new_my_name}，"
                    f"由 {new_boss_name or anima_mc.get('boss', {}).get('name', '老闆')} 命名"
                )
                anima_mc["self_awareness"]["my_purpose"] = (
                    f"幫助 {new_boss_name or anima_mc.get('boss', {}).get('name', '老闆')} 成功"
                )
            if new_boss_name:
                anima_mc.setdefault("boss", {})["name"] = new_boss_name
                my_name = new_my_name or anima_mc.get("identity", {}).get("name", "MUSEON")
                anima_mc["self_awareness"]["who_am_i"] = (
                    f"我是 {my_name}，由 {new_boss_name} 命名"
                )
                anima_mc["self_awareness"]["my_purpose"] = f"幫助 {new_boss_name} 成功"
                anima_mc["self_awareness"]["why_i_exist"] = f"因為 {new_boss_name} 需要一個夥伴"
            self._save_anima_mc(anima_mc)

        # 更新 ceremony_state
        if new_my_name:
            self.ceremony._state["my_name"] = new_my_name
            self.ceremony._save_state()

        # 更新 ANIMA_USER
        if new_boss_name:
            anima_user = self._load_anima_user()
            if anima_user:
                anima_user["profile"]["name"] = new_boss_name
                self._save_anima_user(anima_user)

        # 生成確認回覆
        parts = []
        effective_name = new_my_name or (anima_mc or {}).get("identity", {}).get("name", "MUSEON")
        effective_boss = new_boss_name or (anima_mc or {}).get("boss", {}).get("name", "老闆")
        if new_my_name:
            parts.append(f"收到，我的名字是「{new_my_name}」了。")
        if new_boss_name:
            parts.append(f"我會叫你「{new_boss_name}」。")
        parts.append(f"\n{effective_boss}，有什麼需要 {effective_name} 幫忙的嗎？")

        logger.info(f"更名完成: my_name={new_my_name}, boss_name={new_boss_name}")
        return "\n".join(parts)

    def _update_anima_user_from_ceremony(self, user_model: Dict[str, Any]) -> None:
        """從命名儀式結果更新 ANIMA_USER."""
        anima_user = self._load_anima_user()
        if anima_user:
            anima_user["profile"]["name"] = user_model.get("name")
            anima_user["profile"]["business_type"] = user_model.get("business_type")
            anima_user["needs"]["immediate_need"] = user_model.get("immediate_need")
            anima_user["needs"]["main_pain_point"] = user_model.get("main_pain_point")
            anima_user["relationship"]["first_interaction"] = datetime.now().isoformat()
            anima_user["relationship"]["last_interaction"] = datetime.now().isoformat()
            self._save_anima_user(anima_user)

    # ═══════════════════════════════════════════
    # ANIMA 載入/儲存
    # ═══════════════════════════════════════════

    # ── PDR 軌道 A: 主動擴展方法 ──

    _SKILL_EXPAND_MAP = {
        # 共現分析 top pairs + connects_to 關係
        "ssa-consultant": ["business-12", "brand-identity"],
        "business-12": ["ssa-consultant", "xmodel"],
        "market-core": ["market-equity", "market-macro", "risk-matrix", "sentiment-radar"],
        "market-equity": ["market-core", "business-12"],
        "market-crypto": ["market-core", "risk-matrix"],
        "market-macro": ["market-core", "market-equity"],
        "brand-identity": ["aesthetic-sense", "storytelling-engine"],
        "master-strategy": ["shadow", "xmodel"],
        "xmodel": ["master-strategy", "pdeif"],
        "dse": ["gap", "meta-learning"],
        "gap": ["dse", "acsf"],
        "resonance": ["dharma", "shadow"],
        "shadow": ["resonance", "master-strategy"],
        "investment-masters": ["market-core", "risk-matrix"],
        "risk-matrix": ["market-core", "investment-masters"],
        "storytelling-engine": ["novel-craft", "c15"],
        "plan-engine": ["orchestrator", "wee"],
        "orchestrator": ["plan-engine", "eval-engine"],
    }

    _TOOL_PATTERNS = {
        "tool:gcal": [
            r"明天|後天|下週|下個月|幾月幾號|會議|行程|約|見面|提案|deadline",
        ],
        "tool:gmail": [
            r"email|信件|信箱|寄信|收到.*信|回信",
        ],
        "tool:web_search": [
            r"最新|搜尋|查.*一下|找.*資料|目前.*趨勢",
        ],
    }

    def _proactive_expand_skills(
        self, matched_skills: list, routing_signal: Any
    ) -> list:
        """根據共現和 connects_to 關係擴展 Skill 匹配."""
        expanded = []
        existing = {s.get("name") for s in matched_skills}
        for skill in matched_skills:
            name = skill.get("name", "")
            neighbors = self._SKILL_EXPAND_MAP.get(name, [])
            for nb in neighbors:
                if nb not in existing:
                    expanded.append({"name": nb, "source": "proactive_expand"})
                    existing.add(nb)
        # Limit expansion to avoid prompt bloat
        return expanded[:5]

    def _detect_tool_opportunities(self, content: str) -> str:
        """CPU-only: detect tool invocation opportunities from content keywords."""
        import re
        hints = []
        for tool_id, patterns in self._TOOL_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, content, re.IGNORECASE):
                    if tool_id == "tool:gcal":
                        hints.append("你可以使用 Google Calendar 工具查詢使用者的行程和空閒時間。")
                    elif tool_id == "tool:gmail":
                        hints.append("你可以使用 Gmail 工具搜尋使用者的信件。")
                    elif tool_id == "tool:web_search":
                        hints.append("你可以使用網路搜尋工具查找最新資訊。")
                    break  # one hint per tool
        return "\n".join(hints)

    def _load_anima_mc(self) -> Optional[Dict[str, Any]]:
        """載入 MUSEON 的 ANIMA（委派給 AnimaMCStore）."""
        return self._anima_mc_store.load()

    def _save_anima_mc(self, anima: Dict[str, Any]) -> None:
        """儲存 MUSEON 的 ANIMA（委派給 AnimaMCStore：Lock + KernelGuard + 原子寫入）."""
        self._anima_mc_store.save(anima)

    def _load_anima_user(self) -> Optional[Dict[str, Any]]:
        """載入使用者的 ANIMA."""
        if self.anima_user_path.exists():
            try:
                return json.loads(self.anima_user_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Failed to load ANIMA_USER: {e}", exc_info=True)
        return None

    def _save_anima_user(self, anima: Dict[str, Any]) -> None:
        """儲存使用者的 ANIMA（經 KernelGuard 驗證，原子寫入）."""
        try:
            old_data = self._load_anima_user()

            if self.kernel_guard:
                decision, violations = self.kernel_guard.validate_write(
                    "ANIMA_USER", old_data, anima
                )
                if decision.value == "deny":
                    logger.error(
                        f"KernelGuard DENY ANIMA_USER 寫入: {violations}"
                    )
                    return
                if violations:
                    logger.warning(
                        f"KernelGuard 警告 ANIMA_USER: {violations}"
                    )

            # ★ Project Epigenesis: 寫入前記錄差分
            if self._anima_changelog:
                self._anima_changelog.record(old_data, anima, trigger="observe_user")

            # 原子寫入：先寫 tmp 再 rename
            tmp_path = self.anima_user_path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(anima, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_path.replace(self.anima_user_path)
        except Exception as e:
            logger.error(f"Failed to save ANIMA_USER: {e}", exc_info=True)

    def _estimate_user_exploration_level(self, anima_user: Optional[Dict[str, Any]]) -> float:
        """估算使用者的探索度等級（0.0-1.0）.

        邏輯：
        - 技術型（<20%）：過往 skill_cluster 重複高、多元性低
        - 均衡型（30-50%）：moderate 多樣性
        - 探索型（>60%）：高頻率接觸新 skill、涉及多領域

        Returns:
            exploration_score: 0.0（技術型封閉）→ 1.0（高度探索型）
        """
        if not anima_user:
            return 0.5  # 無數據時預設均衡

        try:
            # 取得過往 skill_cluster 多樣性
            decision_patterns = anima_user.get("seven_layers", {}).get("L3_decision_pattern", [])
            preference_crystals = anima_user.get("seven_layers", {}).get("L5_preference_crystals", [])

            # 策略 1: 計算 skill_cluster 的不重複數量
            skill_clusters = set()
            for pattern in decision_patterns:
                if pattern.get("pattern_type") == "skill_cluster":
                    desc = pattern.get("description", "")
                    if desc.startswith("skill_cluster:"):
                        skill_clusters.add(desc)

            # 策略 2: 計算偏好結晶的多樣性（category 種類數）
            interest_keys = {k.get("key", "") for k in preference_crystals if "interested_in" in k.get("key", "")}

            # 策略 3: 計算角色多樣性（L7_context_roles）
            roles = anima_user.get("seven_layers", {}).get("L7_context_roles", [])
            role_count = len(roles)

            # 加權計算
            cluster_diversity = min(len(skill_clusters) / 15.0, 1.0)  # 15 個 skill_cluster 為滿分
            interest_diversity = min(len(interest_keys) / 8.0, 1.0)  # 8 個興趣類別為滿分
            role_diversity = min(role_count / 5.0, 1.0)  # 5 個角色為滿分

            exploration_score = (
                0.5 * cluster_diversity +
                0.3 * interest_diversity +
                0.2 * role_diversity
            )

            # 三級分類
            if exploration_score < 0.25:
                logger.debug(f"用戶探索度：技術型（{exploration_score:.2f}）")
            elif exploration_score < 0.55:
                logger.debug(f"用戶探索度：均衡型（{exploration_score:.2f}）")
            else:
                logger.debug(f"用戶探索度：探索型（{exploration_score:.2f}）")

            return exploration_score

        except Exception as e:
            logger.warning(f"探索度計算失敗（降級）: {e}")
            return 0.5

    # ═══════════════════════════════════════════
    # 系統提示詞建構
    # ═══════════════════════════════════════════

    def _check_behavior_patterns(
        self,
        content: str,
        routing_signal: Optional[Any],
        history: List[Dict[str, str]],
    ) -> str:
        """行為約束層（原 _deep_reflect）— 回應前的前置自我審視.

        純啟發式規則，無 LLM 呼叫，零延遲。
        目的：在產出前檢查「我的意圖是否與情境對齊」。

        檢查項目：
        1. 停頓/暫停訊號 — 使用者要求先回答問題再動手
        2. 能力探詢 — 探索性問題，非動作指令
        3. 純提問 — 回答問題即可，不需實作
        4. 行為內省 — 使用者在觀察我的機制/行為
        5. 快速迴圈控制 — FAST_LOOP 時壓縮回覆長度
        6. 連續能力展示警示 — 避免「展示模式」失控

        Returns:
            反射注解（注入 system_prompt buffer zone）；無需提示時回傳空字串。
        """
        notes = []
        c_lower = content.lower()

        import re

        # 1. 停頓/暫停訊號
        pause_patterns = [
            "先不要", "先回答", "不要動工", "先停", "等等", "別動手",
            "先別", "暫停", "停一下", "你先", "先不要動", "不要先",
        ]
        if any(p in content for p in pause_patterns):
            notes.append(
                "【停頓訊號】使用者明確要求先暫停再動手。"
                "這一輪的唯一任務是回答問題。"
                "絕對不得開始任何實作、建置、寫檔、執行指令或呼叫工具。"
            )

        # 2. 能力探詢（capability probe）
        capability_probes = [
            "有辦法嗎", "做得到嗎", "能做到嗎", "可以做嗎", "有能力嗎",
            "辦得到嗎", "能不能做", "可不可以做", "有沒有辦法",
            "有辦法配合", "有辦法做", "能配合做", "有辦法配合做",
        ]
        if any(p in content for p in capability_probes):
            notes.append(
                "【能力探詢】使用者問的是「能不能做」，這是探索性確認，不是行動指令。"
                "只說明能力邊界與前提條件，然後問使用者是否確認要開始。"
                "絕對不得直接開工——確認意圖後，等使用者說『開始』才能動手。"
            )

        # 3. 純提問（問句 + 無行動動詞）
        action_verbs = ["幫我", "請幫", "幫你", "寫", "建立", "做一個", "開始", "實作", "部署", "上傳", "產出"]
        is_question = content.strip().endswith("?") or content.strip().endswith("？")
        has_action = any(v in content for v in action_verbs)
        if is_question and not has_action and len(content) < 80:
            notes.append(
                "【純提問】這是一個問題，不含行動指令。"
                "只需回答問題，不要開始實作任何東西，不要呼叫工具產出檔案。"
            )

        # 4. 行為內省（使用者在觀察我的機制/行為）
        introspection_patterns = [
            "有在運作嗎", "有沒有在跑", "你的.*機制", "你的.*有沒有",
            "你有沒有", "你是否", "你怎麼", "你在做什麼",
            "這個機制", "這個功能", "為什麼沒有", "有在.*嗎", "有.*運作",
        ]
        if any(re.search(p, content) for p in introspection_patterns):
            notes.append(
                "【行為內省】使用者在觀察你的內部機制或行為模式。"
                "誠實回答觀察結果，不要同時啟動新任務或展示能力，"
                "除非使用者在同一條訊息中明確要求動手。"
            )

        # 5. 文件/圖片上傳但無明確動作指令
        upload_signals = ["上傳了", "檔案已儲存", "pdf", "PDF", ".json", ".csv", ".xlsx"]
        has_upload = any(s in content for s in upload_signals) or len(content) < 30
        explicit_action_for_upload = any(
            v in content for v in ["分析", "幫我", "請", "看看", "讀", "解析", "總結"]
        )
        # 透過 history 判斷：前一輪有上傳訊號
        prev_had_upload = False
        if len(history) >= 2:
            prev_user = next(
                (m["content"] for m in reversed(history[-4:]) if m.get("role") == "user"),
                ""
            )
            prev_had_upload = any(s in prev_user for s in ["上傳了", "儲存至", ".pdf", ".json"])

        if prev_had_upload and not explicit_action_for_upload and not has_action:
            notes.append(
                "【文件待確認】上一輪有檔案上傳，但使用者尚未說明要如何使用這份文件。"
                "先問使用者：這份文件的用途是什麼？想要做什麼分析或行動？"
                "不要假設意圖，不要主動開始分析或建置系統。"
            )

        # 6. FAST_LOOP 長度控制
        if routing_signal and getattr(routing_signal, "loop", None) == "FAST_LOOP":
            notes.append(
                "【快速迴圈】能量/緊急度為 FAST_LOOP。"
                "回覆控制在 3-5 句以內，直接給核心答案，不展開推演。"
            )

        # 7. 連續能力展示警示（最近 3 輪都是 assistant 在建/寫/產出）
        if len(history) >= 6:
            recent_assistant = [
                m["content"] for m in history[-6:]
                if m.get("role") == "assistant"
            ]
            showcase_signals = ["已建立", "已完成", "程式碼", "```", "system_prompt", "檔案", "已全部搞定", "建立完成"]
            showcase_count = sum(
                1 for r in recent_assistant
                if any(s in r for s in showcase_signals)
            )
            if showcase_count >= 2:
                notes.append(
                    "【展示模式警示】最近連續幾輪你都在建置或產出東西。"
                    "這輪回覆前，先主動問使用者：現在最重要的事是什麼？"
                    "避免慣性往前衝——對齊比行動更重要。"
                )

        # 8. 存在性/使命探詢 — 使用者在探索我的本質、使命或深層感受
        existence_patterns = [
            "你.*使命", "你.*目標", "你.*想做", "你.*在乎", "你.*感受",
            "你自己", "如果沒有我", "如果不介入", "你.*會怎麼",
            "你真正", "你.*意義", "你有什麼.*想法", "你有什麼.*目標",
            "你有什麼.*夢", "你.*希望", "你.*喜歡", "你.*害怕",
        ]
        if any(re.search(p, content) for p in existence_patterns):
            notes.append(
                "【存在性探詢】使用者在探索你的本質、使命或內在感受。"
                "這是建立深度信任的時刻，要慢下來、真誠回應。"
                "不要展示能力、不要啟動任何任務，也不要給建議清單。"
                "只需要誠實分享你真實的觀察和感受。"
            )

        if not notes:
            return ""

        return (
            "## 深度反射（回應前自我審視）\n\n"
            + "\n".join(f"- {n}" for n in notes)
            + "\n\n上述反射注解是給你自己看的，不要直接輸出到回覆中。"
        )

    # ═══════════════════════════════════════════
    # 謀定而後動引擎 — T1 透鏡輔助方法
    # ═══════════════════════════════════════════

    def _scan_emotional_state(self, content: str) -> str:
        """resonance 透鏡：掃描情緒狀態."""
        negative = ["煩", "累", "崩潰", "壓力", "無力", "迷茫", "心累", "卡住", "算了", "隨便", "沒事", "說不上來", "很悶", "太敏感"]
        positive = ["開心", "興奮", "太好了", "感謝", "讚", "不錯", "成功", "突破"]
        content_lower = content.lower()
        neg_count = sum(1 for w in negative if w in content_lower)
        pos_count = sum(1 for w in positive if w in content_lower)
        if neg_count > 0 and pos_count > 0:
            return "mixed"
        if neg_count > 0:
            return "negative"
        if pos_count > 0:
            return "positive"
        return "neutral"

    def _has_strategic_signal(self, content: str) -> bool:
        """master-strategy 透鏡：偵測戰略層信號."""
        keywords = ["決策", "選擇", "方案", "競爭", "佈局", "時機", "戰略", "策略", "全勝", "攻防", "虛實", "沙盤", "推演", "博弈", "談判"]
        return any(k in content for k in keywords)

    def _has_interpersonal_signal(self, content: str) -> bool:
        """shadow 透鏡：偵測人際博弈信號."""
        keywords = ["客戶", "對方", "談判", "合作", "衝突", "關係", "操控", "抗拒", "防衛", "利用", "不對等", "老闆", "團隊", "夥伴", "同事"]
        return any(k in content for k in keywords)

    def _has_belief_conflict_signal(self, content: str) -> bool:
        """dharma 透鏡：偵測信念衝突信號."""
        keywords = ["卡住", "矛盾", "不知道怎麼選", "兩難", "做不到", "價值觀", "方向", "困惑", "迷失", "意義", "轉變", "突破", "信念"]
        return any(k in content for k in keywords)

    def _has_assumption_signal(self, content: str) -> bool:
        """philo-dialectic 透鏡：偵測未審視假設信號."""
        keywords = ["應該", "一定", "不可能", "為什麼", "憑什麼", "這樣對嗎", "怎麼看待", "本質", "定義", "前提", "假設"]
        return any(k in content for k in keywords)

    def _quick_crystal_probe(self, content: str) -> bool:
        """knowledge-lattice 透鏡：快速探測是否有相關結晶."""
        try:
            if not self.knowledge_lattice:
                return False
            results = self.knowledge_lattice.recall(query=content, top_k=1)
            return bool(results)
        except Exception:
            return False

    def _determine_response_strategy(self, loop: str, lenses: list, is_decision: bool, emotional_state: str, prefers_short: bool) -> str:
        """謀定匯流：根據局勢和透鏡決定回應策略."""
        if emotional_state == "negative":
            return "先接住情緒，再處理問題"
        if is_decision:
            return "結構化呈現選項（甜頭/代價/風險），不代替決策"
        if "dharma" in lenses:
            return "不急著給答案，先幫他看清卡點"
        if "philo" in lenses:
            return "挑戰前提，不預設結論"
        if "strategy" in lenses:
            return "戰略視角切入，連結長期影響"
        if "shadow" in lenses:
            return "留意人際動態，提供博弈洞察"
        if loop == "FAST_LOOP" or prefers_short:
            return "直接核心答案，3 句以內"
        return "正常回應，帶入相關透鏡視角"

    # ═══════════════════════════════════════════
    # 謀定而後動引擎 — 主方法
    # ═══════════════════════════════════════════

    def _deliberate(
        self,
        content: str,
        routing_signal: Optional[Any],
        history: List[Dict[str, str]],
        anima_mc: dict = None,
        anima_user: dict = None,
        matched_skills: list = None,
        decision_signal=None,
    ) -> tuple:
        """謀定而後動引擎 v1.0 — T1 透鏡匯流 + 行為約束 + 回應策略.

        孫子兵法「謀定而後動」——快仗也要謀，只是謀的尺度不同。
        三個 Phase：局勢掃描 → 智囊研判 → 謀定匯流。
        全部零 LLM 成本（純規則引擎）。

        Returns:
            (deliberation_note: str, active_lenses: list[str])
        """
        try:
            loop = getattr(routing_signal, 'loop', 'EXPLORATION_LOOP') if routing_signal else 'EXPLORATION_LOOP'

            # ── Phase A: 局勢掃描（零成本，ALL loops）──
            emotional_state = self._scan_emotional_state(content)
            is_decision = getattr(decision_signal, 'is_major', False) if decision_signal else False
            prefers_short = (
                (anima_user or {}).get("observations", {})
                .get("prefers_short_response", {})
                .get("count", 0) > 50
            )

            # Phase A4: 行為約束（原有 8 項模式比對）
            behavior_constraint = self._check_behavior_patterns(
                content=content,
                routing_signal=routing_signal,
                history=history,
            )

            # ── Phase B: 智囊研判（規則引擎，ALL loops）──
            active_lenses = []

            if self._has_strategic_signal(content):
                active_lenses.append("strategy")
            if self._has_interpersonal_signal(content):
                active_lenses.append("shadow")
            if self._has_belief_conflict_signal(content):
                active_lenses.append("dharma")
            if self._has_assumption_signal(content):
                active_lenses.append("philo")
            if emotional_state in ("negative", "mixed"):
                active_lenses.append("resonance")

            # c15 常駐
            active_lenses.append("c15")

            # 記憶探測（輕量）
            if self._quick_crystal_probe(content):
                active_lenses.append("memory")

            # ── Phase C: 謀定匯流 ──
            strategy = self._determine_response_strategy(
                loop=loop,
                lenses=active_lenses,
                is_decision=is_decision,
                emotional_state=emotional_state,
                prefers_short=prefers_short,
            )

            lines = ["## 謀定（回應前思考匯流）"]
            lines.append(
                f"- 局勢：{emotional_state} | {loop} | "
                f"{'決策場景' if is_decision else '一般場景'}"
            )
            if behavior_constraint:
                lines.append(f"- 約束：{behavior_constraint}")
            # 只列非常駐透鏡（c15 常駐不需列出）
            non_default = [l for l in active_lenses if l != "c15"]
            if non_default:
                lines.append(f"- 透鏡：{', '.join(non_default)}")
            lines.append(f"- 策略：{strategy}")

            deliberation_note = "\n".join(lines)
            logger.info(f"[Deliberate] {emotional_state} | {loop} | lenses={non_default} | strategy={strategy[:30]}")

            return deliberation_note, active_lenses

        except Exception as e:
            logger.debug(f"謀定引擎降級: {e}")
            # 降級：嘗試舊版反射
            try:
                fallback = self._check_behavior_patterns(content, routing_signal, history)
                return fallback or "", []
            except Exception:
                return "", []

    def drain_notifications(self) -> List[Dict[str, str]]:
        """取出所有待推播通知 — 純 CPU.

        由 Gateway 呼叫，取出後清空佇列。
        通知格式：{source, title, body, emoji}

        Returns:
            待推播通知列表
        """
        notifications = self._pending_notifications[:]
        self._pending_notifications.clear()
        return notifications

