"""Strategy Accumulator — 策略成熟度累積器.

追蹤洞見的 confidence 隨證據累積的變化。
"""

import logging
from typing import Dict, List, Optional
from museon.learning.insight_extractor import InsightExtractor

logger = logging.getLogger(__name__)


class StrategyAccumulator:
    """追蹤策略成熟度，從 insights 中識別可升級為信條的模式."""

    def __init__(self, extractor: InsightExtractor):
        self._extractor = extractor

    def check_supporting_evidence(self, new_insight: Dict, existing_insights: List[Dict]) -> List[Dict]:
        """檢查新洞見是否支持或矛盾已有洞見."""
        matches = []
        new_tags = set(new_insight.get("tags", []))
        new_domain = new_insight.get("domain", "")

        for existing in existing_insights:
            if existing["id"] == new_insight["id"]:
                continue
            ex_tags = set(existing.get("tags", []))
            ex_domain = existing.get("domain", "")

            # 同 domain 或 tag 重疊 > 1
            overlap = new_tags & ex_tags
            if ex_domain == new_domain or len(overlap) > 1:
                # 判斷支持或矛盾（簡化版：pattern 相似 = 支持，anti_pattern 相似 = 矛盾）
                relation = "supports"  # 預設支持
                if (new_insight.get("anti_pattern") and
                    existing.get("pattern") and
                    any(w in existing["pattern"].lower() for w in new_insight["anti_pattern"].lower().split()[:3])):
                    relation = "contradicts"

                matches.append({
                    "insight_id": existing["id"],
                    "relation": relation,
                    "overlap_tags": list(overlap),
                })
        return matches

    def accumulate(self, new_insight: Dict) -> Dict:
        """根據新洞見更新相關已有洞見的 confidence."""
        all_insights = self._extractor._load_all_insights()
        evidence = self.check_supporting_evidence(new_insight, all_insights)

        updated = []
        for ev in evidence:
            delta = 0.05 if ev["relation"] == "supports" else -0.1
            self._extractor.update_confidence(ev["insight_id"], delta)
            updated.append({"id": ev["insight_id"], "delta": delta, "relation": ev["relation"]})

        return {
            "new_insight_id": new_insight["id"],
            "evidence_found": len(evidence),
            "updates": updated,
        }
