"""SkillDigestor — 生態消化引擎.

職責：
  接收 ecosystem_radar 的搜尋結果（scout_ecosystem_*.json），
  過濾重複、萃取核心模式，輸出 scout_queue 候選項。
  供 SkillForgeScout → SkillDraftForger 管線消費。

資料流：
  morphenix/notes/scout_ecosystem_*.json
    → SkillDigestor.digest()
    → bridge/scout_queue/pending.json（追加 pending 項目）

護欄：
  - 與現有 Skill 名稱前 20 字元重複 → 丟棄
  - 同一週已處理過的 query 不重複消化
  - 純獨立模組，不依賴 EventBus / Brain
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))
MIRROR_PREFIX_LEN = 20   # 反鏡像比對前綴長度（字元）


class SkillDigestor:
    """消化 ecosystem_radar 的搜尋結果，萃取可用模式。

    輸入：ecosystem_radar 的搜尋結果（scout_ecosystem_*.json 列表）
    輸出：scout_queue 的候選項（給 SkillForgeScout / SkillDraftForger 消費）
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._queue_file = data_dir / "_system" / "bridge" / "scout_queue" / "pending.json"
        self._skills_dir = Path("/Users/ZEALCHOU/.claude/skills")
        self._queue_file.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 公開介面
    # ------------------------------------------------------------------

    def digest(self, radar_results: list[dict]) -> list[dict]:
        """過濾 + 萃取：去重 → 提取模式 → 輸出 candidate 格式。

        Args:
            radar_results: ecosystem_radar 寫入的 note 字典列表
                           (type="scout_ecosystem_scan")

        Returns:
            成功加入 scout_queue 的 candidate 列表
        """
        if not radar_results:
            logger.debug("[SkillDigestor] radar_results 為空，跳過")
            return []

        existing_queue = self._load_queue()
        processed_queries = self._processed_queries_this_week(existing_queue)

        candidates: list[dict] = []
        for note in radar_results:
            try:
                candidate = self._process_note(note, processed_queries)
                if candidate is None:
                    continue
                existing_queue.append(candidate)
                processed_queries.add(candidate["topic"].lower())
                candidates.append(candidate)
                logger.info("[SkillDigestor] 新增候選: %s", candidate["topic"][:60])
            except Exception as exc:
                logger.warning("[SkillDigestor] 處理 note 失敗: %s", exc)

        if candidates:
            self._save_queue(existing_queue)
            logger.info("[SkillDigestor] 本次消化 %d 筆 → scout_queue", len(candidates))

        return candidates

    # ------------------------------------------------------------------
    # 主處理邏輯
    # ------------------------------------------------------------------

    def _process_note(
        self,
        note: Dict[str, Any],
        processed_queries: set,
    ) -> Optional[Dict[str, Any]]:
        """處理單一 ecosystem note → 回傳 candidate 或 None（過濾掉）。"""
        # 只處理 ecosystem_radar 產出的 note
        if note.get("source") != "ecosystem_radar":
            return None

        topic: str = note.get("topic", "").strip()
        summary: str = note.get("search_results_summary", "").strip()
        query: str = note.get("sample_queries", [topic])[0] if note.get("sample_queries") else topic

        if not topic:
            return None

        # 去重：同一週已處理過的 query 跳過
        if topic.lower() in processed_queries or query.lower() in processed_queries:
            logger.debug("[SkillDigestor] 已處理過，跳過: %s", topic[:50])
            return None

        # 搜尋不可用時 summary 帶 "(搜尋暫不可用" 開頭 → 跳過無意義結果
        if summary.startswith("(搜尋暫不可用"):
            logger.debug("[SkillDigestor] 搜尋無結果，跳過: %s", topic[:50])
            return None

        # 萃取差異化特點（從 summary 取前段作為 findings_snippet）
        findings_snippet = self._extract_findings(summary, topic)

        # 反鏡像檢查：與現有 Skill 太相似則跳過
        if self._check_overlap(topic):
            logger.debug("[SkillDigestor] 與現有 Skill 重複，跳過: %s", topic[:50])
            return None

        now = datetime.now(TZ8)
        return {
            "topic": topic,
            "findings_snippet": findings_snippet,
            "source": "skill_digestor",
            "origin_source": "ecosystem_radar",
            "created_at": now.isoformat(),
            "status": "pending",
        }

    def _extract_findings(self, summary: str, topic: str) -> str:
        """從 search_results_summary 萃取核心發現片段。

        優先取前 800 字（提供足夠上下文給 SkillForgeScout）。
        若 summary 為空，用 topic 組成最小片段。
        """
        if summary:
            return summary[:800]
        return f"外部生態系掃描發現潛在能力缺口：{topic}"

    # ------------------------------------------------------------------
    # 重複檢查
    # ------------------------------------------------------------------

    def _check_overlap(self, topic: str) -> bool:
        """檢查候選主題是否與現有 Skill 名稱或描述前綴重複。

        Returns:
            True  → 重複，應丟棄
            False → 無重複，可繼續
        """
        if not self._skills_dir.exists():
            return False

        pfx = topic[:MIRROR_PREFIX_LEN].lower()
        try:
            for d in self._skills_dir.iterdir():
                md = d / "SKILL.md"
                if not md.exists():
                    continue
                try:
                    lines = md.read_text(encoding="utf-8").splitlines()
                    e_name = next(
                        (l.split(":", 1)[1].strip() for l in lines if l.startswith("name:")), ""
                    )
                    e_desc = next(
                        (l.split(":", 1)[1].strip() for l in lines if l.startswith("description:")), ""
                    )
                    if pfx and (
                        pfx in e_name[:MIRROR_PREFIX_LEN].lower()
                        or pfx in e_desc[:MIRROR_PREFIX_LEN].lower()
                    ):
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # scout_queue I/O
    # ------------------------------------------------------------------

    def _load_queue(self) -> list[dict]:
        """讀取現有 scout_queue/pending.json；不存在時回傳空列表。"""
        if not self._queue_file.exists():
            return []
        try:
            return json.loads(self._queue_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("[SkillDigestor] 讀取 queue 失敗，重置: %s", exc)
            return []

    def _save_queue(self, queue: list[dict]) -> None:
        """將更新後的 queue 寫回 pending.json。"""
        self._queue_file.write_text(
            json.dumps(queue, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _processed_queries_this_week(self, queue: list[dict]) -> set:
        """從現有 queue 中提取本週已處理（source=skill_digestor）的 topic 集合。"""
        now = datetime.now(TZ8)
        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        result: set = set()
        for item in queue:
            if item.get("source") != "skill_digestor":
                continue
            try:
                created = datetime.fromisoformat(item["created_at"])
                if created >= week_start:
                    result.add(item.get("topic", "").lower())
            except Exception:
                pass
        return result
