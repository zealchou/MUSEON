"""GovernanceGrowthDriver — 治理事件驅動 ANIMA 八元素成長

問題：八元素中 qian/kun/zhen/gen/dui 五個缺少成長來源。
解法：在每次上焦迴圈後，將治理事件映射為 ANIMA 成長。

成長映射：
┌──────────┬────────────────────────────┬───────┬────────────────┐
│ 元素      │ 成長條件                    │ delta │ 含義           │
├──────────┼────────────────────────────┼───────┼────────────────┤
│ qian(使命) │ 在系統壓力下持續運作          │ +1    │ 逆境中的使命堅定 │
│ qian(使命) │ 從壓力恢復到健康             │ +3    │ 韌性展現         │
│ kun(積累)  │ 後天免疫記憶被調用            │ +N    │ 經驗積累發揮作用 │
│ zhen(行動) │ 調節引擎產出修正行動          │ +1    │ 果斷執行         │
│ gen(邊界)  │ 先天免疫防禦觸發             │ +N    │ 邊界守護         │
│ dui(連結)  │ 連續 3+ 次健康              │ +1    │ 穩定連結         │
│ li(覺察)   │ 切診產出交叉症狀             │ +1    │ 深層洞見（強化）  │
│ xun(好奇)  │ 偵測到趨勢惡化              │ +1    │ 探索根因（強化）  │
│ kan(共振)  │ 從壓力恢復                  │ +2    │ 內外共振（強化）  │
└──────────┴────────────────────────────┴───────┴────────────────┘

Phase 3b — 2026-03-03
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class GovernanceGrowthDriver:
    """治理事件 → ANIMA 八元素成長映射。

    在每次上焦迴圈後由 Governor 呼叫 on_governance_cycle()，
    根據治理上下文和診斷報告驅動 ANIMA 成長。
    """

    def __init__(self, anima_tracker: Any) -> None:
        """初始化成長驅動器。

        Args:
            anima_tracker: AnimaTracker 實例，提供 grow(element, delta, reason) 方法
        """
        self._tracker = anima_tracker
        self._consecutive_healthy = 0
        self._was_strained = False  # 追蹤是否曾處於壓力狀態

    def on_governance_cycle(
        self,
        context: Any,  # GovernanceContext
        report: Optional[Any] = None,  # DiagnosticReport
    ) -> None:
        """在每次上焦迴圈後被 Governor 呼叫。

        根據治理上下文和診斷報告，映射為 ANIMA 八元素的成長。
        所有操作都以 try/except 保護，單一元素成長失敗不影響其他。

        Args:
            context: GovernanceContext 快照
            report: 最新 DiagnosticReport（可能為 None）
        """
        try:
            self._drive_qian(context)  # 使命
            self._drive_kun(context)   # 積累
            self._drive_zhen(context)  # 行動
            self._drive_gen(context)   # 邊界
            self._drive_dui(context)   # 連結
            self._drive_li(report)     # 覺察
            self._drive_xun(context)   # 好奇
            self._drive_kan(context)   # 共振
        except Exception as e:
            logger.debug(f"GovernanceGrowthDriver error: {e}")

    # ─── 個別元素成長邏輯 ───

    def _drive_qian(self, ctx: Any) -> None:
        """乾(使命) — 逆境中的使命堅定 + 韌性展現。"""
        try:
            # 在壓力下持續運作 → 使命堅定
            if ctx.needs_caution:
                self._was_strained = True
                self._tracker.grow("qian", 1, "治理: 系統壓力下持續運作")

            # 從壓力恢復到健康 → 韌性展現
            if self._was_strained and ctx.is_healthy:
                self._was_strained = False
                self._tracker.grow("qian", 3, "治理: 從壓力恢復，展現韌性")
        except Exception as e:
            logger.debug(f"[ANIMA_BRIDGE] health check failed (degraded): {e}")

    def _drive_kun(self, ctx: Any) -> None:
        """坤(積累) — 後天免疫記憶被調用。"""
        try:
            if ctx.adaptive_hits > 0:
                delta = min(ctx.adaptive_hits, 3)  # 上限 3
                self._tracker.grow(
                    "kun", delta,
                    f"治理: 後天免疫命中 {ctx.adaptive_hits} 次",
                )
        except Exception as e:
            logger.debug(f"[ANIMA_BRIDGE] operation failed (degraded): {e}")

    def _drive_zhen(self, ctx: Any) -> None:
        """震(行動) — 調節引擎產出修正行動。"""
        try:
            # 有症狀且 immune_hit_rate > 0 表示有活躍的調節行為
            if ctx.symptom_count > 0 and ctx.immune_hit_rate > 0:
                self._tracker.grow("zhen", 1, "治理: 調節引擎產出修正行動")
        except Exception as e:
            logger.debug(f"[ANIMA_BRIDGE] immune failed (degraded): {e}")

    def _drive_gen(self, ctx: Any) -> None:
        """艮(邊界) — 先天免疫防禦觸發。"""
        try:
            if ctx.innate_defenses > 0:
                delta = min(ctx.innate_defenses, 3)  # 上限 3
                self._tracker.grow(
                    "gen", delta,
                    f"治理: 先天免疫防禦 {ctx.innate_defenses} 次",
                )
        except Exception as e:
            logger.debug(f"[ANIMA_BRIDGE] operation failed (degraded): {e}")

    def _drive_dui(self, ctx: Any) -> None:
        """兌(連結) — 連續健康表示穩定連結。"""
        try:
            if ctx.is_healthy:
                self._consecutive_healthy += 1
                if self._consecutive_healthy >= 3:
                    self._tracker.grow("dui", 1, "治理: 連續健康穩定連結")
                    self._consecutive_healthy = 0  # 重置計數
            else:
                self._consecutive_healthy = 0
        except Exception as e:
            logger.debug(f"[ANIMA_BRIDGE] health check failed (degraded): {e}")

    def _drive_li(self, report: Optional[Any]) -> None:
        """離(覺察) — 切診產出交叉症狀，深層洞見。"""
        try:
            if report is None:
                return
            # 尋找交叉分析產出的症狀（category 含 cross 或 systemic）
            cross_count = 0
            for sym in report.symptoms:
                cat = getattr(sym, "category", None)
                if cat and hasattr(cat, "value"):
                    cat_val = cat.value
                    if "cross" in cat_val or "systemic" in cat_val:
                        cross_count += 1
            if cross_count > 0:
                self._tracker.grow(
                    "li", 1,
                    f"治理: 切診交叉分析產出 {cross_count} 個深層洞見",
                )
        except Exception as e:
            logger.debug(f"[ANIMA_BRIDGE] operation failed (degraded): {e}")

    def _drive_xun(self, ctx: Any) -> None:
        """巽(好奇) — 偵測到趨勢惡化，探索根因。"""
        try:
            if ctx.trend == "declining":
                self._tracker.grow("xun", 1, "治理: 趨勢惡化，探索根因")
        except Exception as e:
            logger.debug(f"[ANIMA_BRIDGE] operation failed (degraded): {e}")

    def _drive_kan(self, ctx: Any) -> None:
        """坎(共振) — 從壓力恢復，內外共振回歸。"""
        try:
            # 這和 qian 的恢復不同：kan 追蹤的是從不健康到健康比率提升
            if ctx.healthy_ratio > 0.8 and ctx.trend == "improving":
                self._tracker.grow("kan", 2, "治理: 系統共振回歸穩定")
        except Exception as e:
            logger.debug(f"[ANIMA_BRIDGE] health check failed (degraded): {e}")
