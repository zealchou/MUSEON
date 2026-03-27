"""Insight Extractor — 統一洞見萃取器.

從晨報個案和自主探索中萃取結構化洞見，寫入六層記憶系統。
"""

import json
import logging
import hashlib
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class InsightExtractor:
    """從內容中萃取結構化洞見."""

    def __init__(self, data_dir: str, llm_adapter=None):
        self._data_dir = Path(data_dir)
        self._llm = llm_adapter
        self._insights_dir = self._data_dir / "_system" / "learning" / "insights"
        self._insights_dir.mkdir(parents=True, exist_ok=True)

    async def extract_from_case(self, html_content: str, case_title: str, case_date: str) -> Optional[Dict]:
        """從晨報個案 HTML 中萃取洞見."""
        # 用 LLM 萃取
        prompt = f"""從以下商業個案中萃取可複用的策略洞見。

個案標題：{case_title}
個案日期：{case_date}

內容摘要（前 2000 字）：
{html_content[:2000]}

請用 JSON 格式回覆：
{{
  "pattern": "觀察到的模式（一句話）",
  "principle": "可複用的判斷原則（一句話）",
  "anti_pattern": "應避免的反模式（一句話）",
  "domain": "所屬領域（如 tech_industry, hr_strategy, pricing 等）",
  "applicable_to": ["適用場景1", "適用場景2"],
  "tags": ["標籤1", "標籤2"]
}}

只回覆 JSON，不要其他文字。"""

        try:
            if not self._llm:
                return None
            response = await self._llm.call(
                system_prompt="你是商業洞見萃取專家。從真實案例中提取可複用的策略原則。",
                messages=[{"role": "user", "content": prompt}],
                model="claude-sonnet-4-20250514",
                max_tokens=500,
            )
            # 解析 JSON
            text = response if isinstance(response, str) else getattr(response, 'content', str(response))
            # 嘗試提取 JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                insight_data = json.loads(json_match.group())
            else:
                return None
        except Exception as e:
            logger.debug(f"Case insight extraction failed: {e}")
            return None

        # 建構完整洞見
        insight_id = f"case_{case_date}_{hashlib.sha256(case_title.encode()).hexdigest()[:8]}"
        insight = {
            "id": insight_id,
            "source": "morning_case",
            "source_id": f"{case_date}_{case_title[:30]}",
            "domain": insight_data.get("domain", "general"),
            "pattern": insight_data.get("pattern", ""),
            "principle": insight_data.get("principle", ""),
            "anti_pattern": insight_data.get("anti_pattern", ""),
            "applicable_to": insight_data.get("applicable_to", []),
            "confidence": 0.7,
            "tags": insight_data.get("tags", []),
            "created_at": datetime.now().isoformat(),
            "access_count": 0,
            "status": "active",
        }

        # 持久化
        self._save_insight(insight)
        return insight

    async def extract_from_exploration(self, topic: str, result_text: str, trigger: str) -> Optional[Dict]:
        """從自主探索結果中萃取洞見."""
        prompt = f"""從以下探索結果中萃取可複用的技術/方法論洞見。

探索主題：{topic}
觸發類型：{trigger}

探索結果（前 1500 字）：
{result_text[:1500]}

請用 JSON 格式回覆：
{{
  "pattern": "觀察到的模式（一句話）",
  "principle": "可複用的原則（一句話）",
  "anti_pattern": "應避免的反模式（一句話，沒有則為空字串）",
  "domain": "所屬領域",
  "applicable_to": ["適用場景1", "適用場景2"],
  "tags": ["標籤1", "標籤2"]
}}

只回覆 JSON。"""

        try:
            if not self._llm:
                return None
            response = await self._llm.call(
                system_prompt="你是技術研究洞見萃取專家。從探索結果中提取可操作的方法論原則。",
                messages=[{"role": "user", "content": prompt}],
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
            )
            text = response if isinstance(response, str) else getattr(response, 'content', str(response))
            import re
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                insight_data = json.loads(json_match.group())
            else:
                return None
        except Exception as e:
            logger.debug(f"Exploration insight extraction failed: {e}")
            return None

        insight_id = f"explore_{date.today().isoformat()}_{hashlib.sha256(topic.encode()).hexdigest()[:8]}"
        insight = {
            "id": insight_id,
            "source": "exploration",
            "source_id": f"{topic[:50]}",
            "domain": insight_data.get("domain", "general"),
            "pattern": insight_data.get("pattern", ""),
            "principle": insight_data.get("principle", ""),
            "anti_pattern": insight_data.get("anti_pattern", ""),
            "applicable_to": insight_data.get("applicable_to", []),
            "confidence": 0.6,
            "tags": insight_data.get("tags", []),
            "created_at": datetime.now().isoformat(),
            "access_count": 0,
            "status": "active",
        }

        self._save_insight(insight)
        return insight

    def get_relevant_insights(self, query: str, limit: int = 5) -> List[Dict]:
        """根據查詢取得相關洞見（關鍵字匹配，未來可升級為向量搜尋）."""
        all_insights = self._load_all_insights()
        query_lower = query.lower()
        scored = []
        for ins in all_insights:
            if ins.get("status") != "active":
                continue
            score = 0
            for tag in ins.get("tags", []):
                if tag.lower() in query_lower:
                    score += 2
            if ins.get("domain", "").lower() in query_lower:
                score += 3
            for word in query_lower.split():
                if word in ins.get("pattern", "").lower():
                    score += 1
                if word in ins.get("principle", "").lower():
                    score += 1
            if score > 0:
                scored.append((score, ins))
        scored.sort(key=lambda x: (-x[0], -x[1].get("confidence", 0)))
        return [ins for _, ins in scored[:limit]]

    def update_confidence(self, insight_id: str, delta: float) -> None:
        """更新洞見的 confidence 分數."""
        all_insights = self._load_all_insights()
        for ins in all_insights:
            if ins["id"] == insight_id:
                ins["confidence"] = max(0.0, min(1.0, ins.get("confidence", 0.5) + delta))
                if ins["confidence"] > 0.9:
                    ins["status"] = "conviction"  # 升級為策略信條
                elif ins["confidence"] < 0.3:
                    ins["status"] = "deprecated"  # 降級
                self._save_insight(ins)
                break

    def get_monthly_summary(self) -> Dict[str, Any]:
        """取得本月學習摘要."""
        all_insights = self._load_all_insights()
        this_month = date.today().strftime("%Y-%m")
        monthly = [i for i in all_insights if i.get("created_at", "").startswith(this_month)]
        return {
            "month": this_month,
            "total_new": len(monthly),
            "by_source": {
                "morning_case": len([i for i in monthly if i["source"] == "morning_case"]),
                "exploration": len([i for i in monthly if i["source"] == "exploration"]),
            },
            "convictions": len([i for i in all_insights if i.get("status") == "conviction"]),
            "deprecated": len([i for i in all_insights if i.get("status") == "deprecated"]),
            "top_domains": self._count_domains(monthly),
        }

    def _count_domains(self, insights: List[Dict]) -> Dict[str, int]:
        counts = {}
        for i in insights:
            d = i.get("domain", "unknown")
            counts[d] = counts.get(d, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5])

    # ── 持久化 ───────────────────────────────

    def _save_insight(self, insight: Dict) -> None:
        fp = self._insights_dir / f"{insight['id']}.json"
        try:
            import tempfile, os
            content = json.dumps(insight, ensure_ascii=False, indent=2)
            fd, tmp = tempfile.mkstemp(dir=str(self._insights_dir), suffix=".tmp")
            try:
                os.write(fd, content.encode("utf-8"))
                os.fsync(fd)
                os.close(fd)
                os.replace(tmp, str(fp))
            except Exception:
                os.close(fd)
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        except Exception as e:
            logger.warning(f"Failed to save insight {insight['id']}: {e}")

    def _load_all_insights(self) -> List[Dict]:
        insights = []
        for fp in self._insights_dir.glob("*.json"):
            if fp.name.endswith(".tmp"):
                continue
            try:
                insights.append(json.loads(fp.read_text(encoding="utf-8")))
            except Exception:
                continue
        return insights
