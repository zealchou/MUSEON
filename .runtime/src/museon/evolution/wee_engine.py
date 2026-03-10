"""WEEEngine — Workflow Evolution Engine 自動循環引擎.

每輪互動自動執行：信噪過濾 → 啟發式 5D 評分 → 記錄 → 高原檢查。
搭配壓縮（daily）/ 融合（weekly）管線，驅動持續進化閉環。

5D 評分維度：
  D1 Speed — 執行速度
  D2 Quality — 回應品質
  D3 Alignment — 對齊度
  D4 Leverage — 槓桿效率
  D5 External Integration — 是否有效調用外部知識、資源、工具

零 LLM 依賴。所有評分和偵測為純 Python 啟發式。
"""

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from museon.workflow.models import FiveDScore, FourDScore, WorkflowRecord
from museon.workflow.workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# 信噪過濾常數
# ═══════════════════════════════════════════

_SIGNAL_KEYWORDS_ZH = frozenset({
    "學到", "原來", "發現", "決定", "完成", "失敗", "做完", "教訓",
    "下次", "改進", "規劃", "目標", "策略", "解決", "結晶", "覆盤",
    "反思", "問題", "嘗試", "成功",
})

_MIN_CONTENT_LENGTH = 15

# ═══════════════════════════════════════════
# 啟發式評分常數
# ═══════════════════════════════════════════

_FAILURE_KEYWORDS = frozenset({
    "失敗", "無法", "錯誤", "error", "❌", "fail", "Error",
})

_PROCEDURAL_KW = frozenset({
    "步驟", "流程", "方法", "SOP", "教學", "如何", "怎麼",
})

_ANALYTICAL_KW = frozenset({
    "分析", "比較", "評估", "原因", "為什麼",
})

_DECISIONAL_KW = frozenset({
    "決定", "選擇", "結論", "方案", "建議", "規劃", "目標",
})

# 每 N 輪檢查高原
_PLATEAU_CHECK_INTERVAL = 5

# ═══════════════════════════════════════════
# Per-user 實例快取
# ═══════════════════════════════════════════

_instances: Dict[str, "WEEEngine"] = {}
_instances_lock = threading.Lock()


def get_wee_engine(
    user_id: str,
    workspace: Path,
    event_bus: Optional[Any] = None,
    memory_manager: Optional[Any] = None,
) -> "WEEEngine":
    """取得 per-user WEEEngine 實例（快取）.

    Args:
        user_id: 用戶 ID
        workspace: 工作目錄
        event_bus: EventBus 實例
        memory_manager: MemoryManager 實例

    Returns:
        WEEEngine 實例
    """
    global _instances
    if user_id not in _instances:
        with _instances_lock:
            if user_id not in _instances:
                _instances[user_id] = WEEEngine(
                    user_id=user_id,
                    workspace=workspace,
                    event_bus=event_bus,
                    memory_manager=memory_manager,
                )
    return _instances[user_id]


def _reset_wee_instances() -> None:
    """重置所有 per-user 實例（僅供測試用）."""
    global _instances
    with _instances_lock:
        _instances.clear()


# ═══════════════════════════════════════════
# WEEEngine
# ═══════════════════════════════════════════


class WEEEngine:
    """WEE 自動循環引擎.

    每輪互動：
    1. 信噪過濾 — 只記錄有意義的信號
    2. 啟發式 5D 評分 — 純 Python 規則
    3. 記錄到 WorkflowEngine
    4. 高原檢查（每 N 輪）

    設計原則：
    - 零 LLM 依賴
    - Per-user 實例
    - 所有操作 try/except 包裝
    """

    def __init__(
        self,
        user_id: str,
        workspace: Path,
        event_bus: Optional[Any] = None,
        memory_manager: Optional[Any] = None,
    ) -> None:
        """初始化 WEEEngine.

        Args:
            user_id: 用戶 ID
            workspace: 工作目錄
            event_bus: EventBus 實例
            memory_manager: MemoryManager 實例（用於壓縮/融合）
        """
        self._user_id = user_id
        self._workspace = Path(workspace)
        self._event_bus = event_bus
        self._memory_manager = memory_manager

        # WorkflowEngine（共用同一 DB）
        self._wf_engine = WorkflowEngine(
            workspace=self._workspace,
            event_bus=event_bus,
        )

        # Session 管理
        self._current_session: str = ""
        self._session_date: str = ""
        self._interaction_count: int = 0

        # 統計
        self._total_signals: int = 0
        self._total_noise: int = 0

    # ═══════════════════════════════════════════
    # 信噪過濾
    # ═══════════════════════════════════════════

    def is_signal(self, content: str) -> bool:
        """判斷內容是否為有意義的信號.

        規則：
        1. 含任一信號關鍵字 → True
        2. 長度 >= _MIN_CONTENT_LENGTH → True
        3. 否則 → False（噪音）

        Args:
            content: 使用者輸入或回應內容

        Returns:
            True = 信號, False = 噪音
        """
        if not content or not content.strip():
            return False

        # 關鍵字優先
        if any(kw in content for kw in _SIGNAL_KEYWORDS_ZH):
            return True

        # 長度門檻
        if len(content.strip()) >= _MIN_CONTENT_LENGTH:
            return True

        return False

    # ═══════════════════════════════════════════
    # 啟發式 5D 評分
    # ═══════════════════════════════════════════

    def heuristic_score(self, data: Dict[str, Any]) -> FiveDScore:
        """啟發式 5D 評分.

        基礎分：S=5, Q=5, A=5, L=4, E=3
        根據上下文信號加減分，最後 clamp [0, 10]。

        D5 External Integration 評分邏輯：
          - 使用外部工具（搜尋、API）+1.0
          - 引用外部知識 +0.5
          - 多工具協同 +1.0
          - 無外部資訊時預設 3.0

        Args:
            data: 互動數據
                - user_content: 使用者輸入
                - response_content: AI 回應
                - q_score_tier: "high"/"medium"/"low"
                - matched_skills: 匹配到的 skill 列表
                - tools_used: 使用的工具列表（新增）
                - external_sources: 外部資訊來源數（新增）
                - source: 來源

        Returns:
            FiveDScore（向後相容 FourDScore 的 speed/quality/alignment/leverage）
        """
        speed = 5.0
        quality = 5.0
        alignment = 5.0
        leverage = 4.0
        external_integration = 3.0  # D5 基礎分

        user_content = data.get("user_content", "")
        response_content = data.get("response_content", "")
        q_score_tier = data.get("q_score_tier", "medium")
        matched_skills = data.get("matched_skills", [])
        tools_used = data.get("tools_used", [])
        external_sources = data.get("external_sources", 0)

        combined = f"{user_content} {response_content}"

        # ── Q-Score 調整 ──
        if q_score_tier == "high":
            quality += 1.0
        elif q_score_tier == "low":
            quality -= 1.5

        # ── 回應長度 ──
        if len(response_content) > 500:
            quality += 0.5
        elif len(response_content) < 50:
            quality -= 0.5

        # ── 失敗偵測 ──
        if self._detect_failure(combined):
            quality -= 2.0
            alignment -= 1.0

        # ── 使用者輸入長度 ──
        if len(user_content) > 100:
            alignment += 0.5

        # ── 短輸入 + 長輸出 = 高槓桿 ──
        if len(user_content) < 50 and len(response_content) > 300:
            leverage += 1.0

        # ── 程序性關鍵字 ──
        if any(kw in combined for kw in _PROCEDURAL_KW):
            quality += 0.5

        # ── 分析性關鍵字 ──
        if any(kw in combined for kw in _ANALYTICAL_KW):
            alignment += 0.5

        # ── 決策性關鍵字 ──
        if any(kw in combined for kw in _DECISIONAL_KW):
            leverage += 0.5

        # ── 有匹配技能 ──
        if matched_skills:
            leverage += 0.5

        # ── 信號關鍵字加分 ──
        if any(kw in combined for kw in _SIGNAL_KEYWORDS_ZH):
            quality += 0.5

        # ── D5: External Integration ──
        # 使用外部工具
        if tools_used:
            external_integration += 1.0
            # 多工具協同加分
            if len(tools_used) >= 2:
                external_integration += 1.0

        # 外部資訊來源
        if external_sources > 0:
            external_integration += min(1.0, external_sources * 0.5)

        # 搜尋/引用相關關鍵字
        _ext_kw = {"搜尋", "查詢", "引用", "參考", "來源", "search", "API", "外部"}
        if any(kw in combined for kw in _ext_kw):
            external_integration += 0.5

        return FiveDScore(
            speed=speed,
            quality=quality,
            alignment=alignment,
            leverage=leverage,
            external_integration=external_integration,
        ).clamp()

    def _detect_failure(self, content: str) -> bool:
        """偵測失敗信號.

        Args:
            content: 合併後的內容

        Returns:
            True = 偵測到失敗
        """
        return any(kw in content for kw in _FAILURE_KEYWORDS)

    # ═══════════════════════════════════════════
    # Session 管理
    # ═══════════════════════════════════════════

    def _ensure_session(self) -> str:
        """確保 session 存在，日期切換時自動建立新 session.

        Returns:
            當前 session ID
        """
        today = datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d")
        if self._session_date != today or not self._current_session:
            self._session_date = today
            self._current_session = f"session_{today}_{uuid.uuid4().hex[:8]}"
            self._interaction_count = 0
        return self._current_session

    # ═══════════════════════════════════════════
    # 核心循環
    # ═══════════════════════════════════════════

    def auto_cycle(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """自動循環 — EventBus 回呼入口.

        流程：
        1. 信噪過濾
        2. 啟發式評分
        3. 記錄到 WorkflowEngine
        4. 每 N 輪高原檢查

        Args:
            data: 互動數據（來自 BRAIN_RESPONSE_COMPLETE 事件）
                - user_id: 用戶 ID
                - user_content: 使用者輸入
                - response_content: AI 回應
                - q_score_tier: "high"/"medium"/"low"
                - matched_skills: 匹配到的 skill 列表
                - source: 來源

        Returns:
            記錄摘要 dict 或 None（被過濾的噪音）
        """
        try:
            if not data:
                return None

            user_content = data.get("user_content", "")
            response_content = data.get("response_content", "")

            # 1. 信噪過濾
            if not self.is_signal(user_content) and not self.is_signal(response_content):
                self._total_noise += 1
                return None

            self._total_signals += 1

            # 2. Session 管理
            session_id = self._ensure_session()
            self._interaction_count += 1

            # 3. 啟發式評分
            score = self.heuristic_score(data)

            # 4. 決定 outcome
            combined = f"{user_content} {response_content}"
            outcome = "failed" if self._detect_failure(combined) else "success"

            # 5. 取得或建立工作流
            workflow_name = data.get("source", "general_interaction")
            wf = self._wf_engine.get_or_create(
                user_id=self._user_id,
                name=workflow_name,
                tags=data.get("matched_skills", []),
            )

            # 6. 記錄執行
            context = f"session={session_id} interaction={self._interaction_count}"
            record = self._wf_engine.record_execution(
                workflow_id=wf.workflow_id,
                score=score,
                outcome=outcome,
                context=context,
            )

            # 7. 每 N 輪高原檢查
            plateau_result = None
            if self._interaction_count % _PLATEAU_CHECK_INTERVAL == 0:
                plateau_result = self._wf_engine.check_plateau(wf.workflow_id)

            result = {
                "session_id": session_id,
                "interaction": self._interaction_count,
                "workflow_id": wf.workflow_id,
                "score": score.to_dict(),
                "outcome": outcome,
                "plateau_check": plateau_result,
            }

            # 發布 SKILL_QUALITY_SCORED 事件
            if self._event_bus:
                try:
                    from museon.core.event_bus import SKILL_QUALITY_SCORED
                    self._event_bus.publish(SKILL_QUALITY_SCORED, {
                        "workflow_id": wf.workflow_id,
                        "workflow_name": wf.name,
                        "score": score.to_dict(),
                        "outcome": outcome,
                        "matched_skills": data.get("matched_skills", []),
                    })
                except Exception:
                    pass

            # 發布 WEE_CYCLE_COMPLETE（ActivityLogger 訂閱）
            if self._event_bus:
                try:
                    from museon.core.event_bus import WEE_CYCLE_COMPLETE
                    self._event_bus.publish(WEE_CYCLE_COMPLETE, {
                        "session_id": session_id,
                        "interaction": self._interaction_count,
                        "score": score.to_dict() if score else {},
                        "outcome": outcome,
                        "has_plateau": plateau_result is not None,
                    })
                except Exception:
                    pass

            return result

        except Exception as e:
            logger.error(f"WEEEngine.auto_cycle error: {e}")
            return None

    # ═══════════════════════════════════════════
    # Nightly 壓縮 / 融合
    # ═══════════════════════════════════════════

    def compress_daily(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """Nightly Step 4：壓縮昨日 session → L2_ep crystal.

        將昨日所有執行記錄壓縮為一筆記憶結晶，
        存入 MemoryManager L2_ep 層。

        Args:
            target_date: 目標日期 YYYY-MM-DD（預設：昨天）

        Returns:
            {"compressed": bool, "crystal_id": str, "summary": str}
        """
        try:
            if not target_date:
                yesterday = datetime.now(TZ_TAIPEI) - timedelta(days=1)
                target_date = yesterday.strftime("%Y-%m-%d")

            # 取得用戶所有工作流
            workflows = self._wf_engine.list_workflows(self._user_id)
            if not workflows:
                return {"compressed": False, "reason": "no_workflows"}

            # 收集目標日期的執行記錄
            daily_records = []
            for wf in workflows:
                recent = self._wf_engine.get_recent_executions(
                    wf.workflow_id, limit=50,
                )
                for r in recent:
                    if r.created_at.startswith(target_date):
                        daily_records.append({
                            "workflow": wf.name,
                            "score": r.score.to_dict(),
                            "outcome": r.outcome,
                        })

            if not daily_records:
                return {"compressed": False, "reason": "no_records_for_date"}

            # 計算日均
            total = len(daily_records)
            avg_composite = sum(
                r["score"]["composite"] for r in daily_records
            ) / total

            success_count = sum(
                1 for r in daily_records if r["outcome"] == "success"
            )

            # 建構 crystal 內容
            crystal_content = (
                f"[Daily Crystal {target_date}] "
                f"interactions={total} "
                f"avg_composite={avg_composite:.2f} "
                f"success_rate={success_count}/{total} "
                f"workflows={','.join(set(r['workflow'] for r in daily_records))}"
            )

            # 存入記憶系統（如果可用）
            crystal_id = ""
            if self._memory_manager:
                try:
                    crystal_id = self._memory_manager.store(
                        user_id=self._user_id,
                        content=crystal_content,
                        layer="L2_ep",
                        tags=["wee_daily_crystal", target_date],
                        source="wee_auto",
                        quality_tier="silver",
                    )
                except Exception as e:
                    logger.warning(f"Crystal store failed: {e}")

            return {
                "compressed": True,
                "crystal_id": crystal_id,
                "date": target_date,
                "interactions": total,
                "avg_composite": round(avg_composite, 4),
                "success_rate": f"{success_count}/{total}",
                "summary": crystal_content,
            }

        except Exception as e:
            logger.error(f"WEEEngine.compress_daily error: {e}")
            return {"compressed": False, "reason": str(e)}

    def fuse_weekly(self, iso_week: Optional[str] = None) -> Dict[str, Any]:
        """Nightly Step 5：融合週間 daily crystals → L2_sem weekly crystal.

        需要 3+ daily crystals 才觸發融合。

        Args:
            iso_week: ISO 週 YYYY-WNN（預設：上週）

        Returns:
            {"fused": bool, "crystal_id": str, "summary": str}
        """
        try:
            if not iso_week:
                last_week = datetime.now(TZ_TAIPEI) - timedelta(weeks=1)
                iso_week = f"{last_week.isocalendar()[0]}-W{last_week.isocalendar()[1]:02d}"

            if not self._memory_manager:
                return {"fused": False, "reason": "no_memory_manager"}

            # 查找本週的 daily crystals
            # 使用 MemoryManager recall 搜尋
            daily_crystals = []
            try:
                results = self._memory_manager.recall(
                    user_id=self._user_id,
                    query=f"wee_daily_crystal {iso_week}",
                    layer="L2_ep",
                    limit=10,
                )
                # 過濾出 wee_daily_crystal tag
                for r in results:
                    tags = r.get("tags", [])
                    if "wee_daily_crystal" in tags:
                        daily_crystals.append(r)
            except Exception:
                # recall 可能失敗，嘗試用 iso_week 的日期範圍
                pass

            if len(daily_crystals) < 3:
                return {
                    "fused": False,
                    "reason": "insufficient_crystals",
                    "crystal_count": len(daily_crystals),
                }

            # 融合摘要
            crystal_contents = [c.get("content", "") for c in daily_crystals]
            weekly_content = (
                f"[Weekly Crystal {iso_week}] "
                f"daily_crystals={len(daily_crystals)} "
                f"fused_from={'; '.join(crystal_contents[:5])}"
            )

            # 存入 L2_sem
            crystal_id = ""
            try:
                crystal_id = self._memory_manager.store(
                    user_id=self._user_id,
                    content=weekly_content,
                    layer="L2_sem",
                    tags=["wee_weekly_crystal", iso_week],
                    source="wee_auto",
                    quality_tier="gold",
                )
            except Exception as e:
                logger.warning(f"Weekly crystal store failed: {e}")

            return {
                "fused": True,
                "crystal_id": crystal_id,
                "iso_week": iso_week,
                "daily_crystals": len(daily_crystals),
                "summary": weekly_content,
            }

        except Exception as e:
            logger.error(f"WEEEngine.fuse_weekly error: {e}")
            return {"fused": False, "reason": str(e)}

    # ═══════════════════════════════════════════
    # 狀態查詢
    # ═══════════════════════════════════════════

    def get_status(self) -> Dict[str, Any]:
        """取得 WEEEngine 狀態摘要.

        Returns:
            {
                "user_id": str,
                "current_session": str,
                "interaction_count": int,
                "total_signals": int,
                "total_noise": int,
                "signal_ratio": float,
                "proficiency": dict,
                "active_workflows": int,
            }
        """
        try:
            proficiency = self._wf_engine.get_proficiency(self._user_id)
            workflows = self._wf_engine.list_workflows(self._user_id)

            total = self._total_signals + self._total_noise
            signal_ratio = (
                self._total_signals / total if total > 0 else 0.0
            )

            return {
                "user_id": self._user_id,
                "current_session": self._current_session,
                "interaction_count": self._interaction_count,
                "total_signals": self._total_signals,
                "total_noise": self._total_noise,
                "signal_ratio": round(signal_ratio, 4),
                "proficiency": proficiency,
                "active_workflows": len(workflows),
            }
        except Exception as e:
            logger.error(f"WEEEngine.get_status error: {e}")
            return {
                "user_id": self._user_id,
                "current_session": self._current_session,
                "interaction_count": self._interaction_count,
                "total_signals": self._total_signals,
                "total_noise": self._total_noise,
                "signal_ratio": 0.0,
                "proficiency": {},
                "active_workflows": 0,
            }
