"""SkillDraftForger — Skill 草稿鍛造引擎.

職責：
  根據 Scout 研究筆記與 WEE 弱項提案，用 LLM（Haiku）鍛造 SKILL.md 草稿。
  支援兩種模式：
    forge_new        — 從零鍛造全新 Skill
    optimize_existing — 讀現有 SKILL.md + 退化診斷 → 輸出優化版草稿

資料流：
  morphenix/notes/scout_*.json  ──┐
  morphenix/proposals/proposal_wee_gap_*.json ─┤→ LLM → skills_draft/draft_{id}.json
  skill_health/*.json（退化診斷）──┘              → morphenix/proposals/proposal_skill_candidate_*.json

護欄：
  - 每週上限 2 個新 Skill 草稿（forge_new 計數）
  - 反鏡像：名稱/描述前 20 字元與現有 Skill 重複則拒絕
  - 草稿只寫 skills_draft/，不進 ~/.claude/skills/
  - 純獨立模組，不依賴 EventBus / Brain
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))
WEEKLY_FORGE_LIMIT = 2       # 每週新草稿上限
MIRROR_PREFIX_LEN = 20       # 反鏡像比對前綴長度（字元）
FORGE_MODEL = "claude-haiku-4-5-20251001"

# SKILL.md 草稿範本
_SKILL_MD_TPL = """\
---
name: {skill_name}
type: on-demand
layer: product
hub: {hub}
description: >
  {description}
io:
  inputs: []
  outputs:
    - to: user
      field: analysis_result
      trigger: always
connects_to: []
---
# {skill_name}
## 觸發時機
{triggers}
## 處理方式
{handling}
## 護欄
- 不做超出範圍的事
"""


class SkillDraftForger:
    """Skill 草稿鍛造引擎 — 讀筆記/提案，呼叫 Haiku，輸出草稿 JSON."""

    def __init__(self, workspace: Optional[Path] = None) -> None:
        ws = workspace or Path("/Users/ZEALCHOU/MUSEON")
        self._notes_dir     = ws / "data/_system/morphenix/notes"
        self._proposals_dir = ws / "data/_system/morphenix/proposals"
        self._draft_dir     = ws / "data/_system/skills_draft"
        self._health_dir    = ws / "data/_system/skill_health"
        self._skills_dir    = Path("/Users/ZEALCHOU/.claude/skills")
        self._draft_dir.mkdir(parents=True, exist_ok=True)
        self._proposals_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 公開介面
    # ------------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """Nightly 主入口：掃描來源 → 鍛造草稿."""
        results: Dict[str, Any] = {"forged": [], "skipped": [], "errors": []}

        # forge_new 任務
        for src in self._collect_sources():
            try:
                draft = self._forge_new(src)
                (results["forged"] if draft else results["skipped"]).append(
                    src.get("_source_file", "?")
                )
            except Exception as exc:
                logger.error("[SkillDraftForger] forge_new 失敗: %s", exc, exc_info=True)
                results["errors"].append(str(exc))

        # optimize_existing 任務
        for skill_name, health in self._find_degraded_skills().items():
            try:
                draft = self._optimize_existing(skill_name, health)
                (results["forged"] if draft else results["skipped"]).append(skill_name)
            except Exception as exc:
                logger.error("[SkillDraftForger] optimize_existing 失敗: %s", exc, exc_info=True)
                results["errors"].append(str(exc))

        logger.info(
            "[SkillDraftForger] 完成 — 鍛造:%d 跳過:%d 錯誤:%d",
            len(results["forged"]), len(results["skipped"]), len(results["errors"]),
        )
        return results

    # ------------------------------------------------------------------
    # 來源收集
    # ------------------------------------------------------------------

    def _collect_sources(self) -> List[Dict[str, Any]]:
        """讀取尚未處理的 Scout 筆記與 WEE 提案."""
        done = {
            json.loads(p.read_text()).get("source_file")
            for p in self._draft_dir.glob("draft_*.json")
            if p.stat().st_size > 0
        }
        items: List[Dict[str, Any]] = []
        for pattern, stype in [("scout_*.json", "scout_note"), ("proposal_wee_gap_*.json", "wee_gap")]:
            base = self._notes_dir if stype == "scout_note" else self._proposals_dir
            for p in sorted(base.glob(pattern)):
                if p.name in done:
                    continue
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    data["_source_file"] = p.name
                    data["_source_type"] = stype
                    items.append(data)
                except Exception as exc:
                    logger.warning("[SkillDraftForger] 跳過 %s: %s", p.name, exc)
        return items

    def _find_degraded_skills(self) -> Dict[str, Dict[str, Any]]:
        """回傳 avg_quality < 0.5 或 trend == declining 的 Skill 健康度字典."""
        if not self._health_dir.exists():
            return {}
        result: Dict[str, Dict[str, Any]] = {}
        for p in self._health_dir.glob("*.json"):
            try:
                h = json.loads(p.read_text(encoding="utf-8"))
                if h.get("avg_quality", 1.0) < 0.5 or h.get("trend") == "declining":
                    result[h["skill_name"]] = h
            except Exception:
                pass
        return result

    # ------------------------------------------------------------------
    # 護欄
    # ------------------------------------------------------------------

    def _weekly_forge_count(self) -> int:
        """計算本週（週一起算）已產出的 forge_new 草稿數."""
        now = datetime.now(TZ8)
        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        count = 0
        for p in self._draft_dir.glob("draft_*.json"):
            try:
                d = json.loads(p.read_text())
                if d.get("mode") != "forge_new":
                    continue
                if datetime.fromisoformat(d["created_at"]) >= week_start:
                    count += 1
            except Exception:
                pass
        return count

    def _mirror_check(self, skill_name: str, description: str) -> Tuple[bool, str]:
        """若名稱或描述前 N 字元與現有 Skill 重複，回傳 (True, 衝突名稱)."""
        pfx_name = skill_name[:MIRROR_PREFIX_LEN].lower()
        pfx_desc = description[:MIRROR_PREFIX_LEN].lower()
        for d in self._skills_dir.iterdir():
            md = d / "SKILL.md"
            if not md.exists():
                continue
            try:
                lines = md.read_text(encoding="utf-8").splitlines()
                e_name = next((l.split(":", 1)[1].strip() for l in lines if l.startswith("name:")), "")
                e_desc = next((l.split(":", 1)[1].strip() for l in lines if l.startswith("description:")), "")
                if pfx_name and pfx_name in e_name[:MIRROR_PREFIX_LEN].lower():
                    return True, e_name
                if pfx_desc and pfx_desc in e_desc[:MIRROR_PREFIX_LEN].lower():
                    return True, e_name
            except Exception:
                pass
        return False, ""

    # ------------------------------------------------------------------
    # 鍛造流程
    # ------------------------------------------------------------------

    def _forge_new(self, source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """從零鍛造新 Skill 草稿；護欄阻擋時回傳 None."""
        if self._weekly_forge_count() >= WEEKLY_FORGE_LIMIT:
            logger.info("[SkillDraftForger] 已達本週上限（%d），跳過", WEEKLY_FORGE_LIMIT)
            return None

        summary = json.dumps(source, ensure_ascii=False, indent=2)[:2000]
        prompt = (
            f"你是 MUSEON Skill 設計師。根據以下研究資料設計一個新 Skill。\n\n## 來源資料\n{summary}\n\n"
            "## 輸出格式（純 JSON，不加 markdown 代碼區塊）\n"
            '{"skill_name":"kebab-case","hub":"strategy|coaching|content|analytics|intelligence|creative|productivity|relationship|general 其中之一",'
            '"description":"50 字以內","triggers":"2-3 句","handling":"2-3 句","quality_self_score":0.0}'
        )
        spec = self._call_llm(prompt)
        if not spec:
            return None

        is_mirror, conflict = self._mirror_check(spec.get("skill_name", ""), spec.get("description", ""))
        if is_mirror:
            logger.info("[SkillDraftForger] 反鏡像阻擋 — 與 '%s' 重複", conflict)
            return None

        return self._save_and_emit(spec, "forge_new", source.get("_source_type", "scout_note"),
                                   source.get("_source_file", ""), None)

    def _optimize_existing(self, skill_name: str, health: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """讀現有 SKILL.md + 退化診斷，輸出優化版草稿."""
        md_path = self._skills_dir / skill_name / "SKILL.md"
        if not md_path.exists():
            logger.warning("[SkillDraftForger] 找不到 SKILL.md: %s", md_path)
            return None

        existing = md_path.read_text(encoding="utf-8")[:1500]
        prompt = (
            f"你是 MUSEON Skill 優化師。Skill「{skill_name}」表現退化，請提出優化版本。\n\n"
            f"## 健康度診斷\n{json.dumps(health, ensure_ascii=False)}\n\n"
            f"## 現有 SKILL.md（前段）\n{existing}\n\n"
            "## 輸出格式（純 JSON，不加 markdown 代碼區塊）\n"
            f'{{"skill_name":"{skill_name}","hub":"保留或更合適的 hub",'
            '"description":"50 字以內","triggers":"優化後觸發時機","handling":"優化後處理方式","quality_self_score":0.0}}'
        )
        spec = self._call_llm(prompt)
        if not spec:
            return None

        return self._save_and_emit(spec, "optimize_existing", "skill_degradation",
                                   f"skill_health/{skill_name}.json", skill_name)

    # ------------------------------------------------------------------
    # LLM 呼叫
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str) -> Optional[Dict[str, Any]]:
        """呼叫 Anthropic Haiku；失敗時 graceful degrade，回傳 None."""
        try:
            from anthropic import Anthropic  # 延遲 import，模組載入失敗不影響其他步驟
            client = Anthropic()
            resp = client.messages.create(
                model=FORGE_MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
            # 去除可能的 markdown 代碼區塊包裝
            if raw.startswith("```"):
                lines = raw.splitlines()
                raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw
            return json.loads(raw)
        except Exception as exc:
            logger.error("[SkillDraftForger] LLM 失敗，graceful degrade: %s", exc)
            return None

    # ------------------------------------------------------------------
    # 檔案輸出
    # ------------------------------------------------------------------

    def _save_and_emit(
        self,
        spec: Dict[str, Any],
        mode: str,
        source: str,
        source_file: str,
        target_skill: Optional[str],
    ) -> Dict[str, Any]:
        """組裝 draft JSON → 寫入 skills_draft/ → 發 Morphenix 提案."""
        now = datetime.now(TZ8)
        stamp = now.strftime("%Y%m%d_%H%M%S")
        skill_name = spec.get("skill_name", "unknown-skill")

        # 組裝 SKILL.md 草稿內容
        skill_md = _SKILL_MD_TPL.format(
            skill_name=skill_name,
            hub=spec.get("hub", "general"),
            description=spec.get("description", ""),
            triggers=spec.get("triggers", "使用者明確請求此 Skill 時"),
            handling=spec.get("handling", "依據輸入資料分析並輸出結果"),
        )

        draft: Dict[str, Any] = {
            "id": f"draft_{stamp}_{skill_name}",
            "mode": mode,
            "source": source,
            "source_file": source_file,
            "skill_name": skill_name,
            "skill_md_content": skill_md,
            "quality_self_score": spec.get("quality_self_score", 0.7),
            "created_at": now.isoformat(),
            "status": "pending_qa",
            "target_skill": target_skill,
            "version": "candidate",
        }

        # 寫草稿
        dp = self._draft_dir / f"{draft['id']}.json"
        dp.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[SkillDraftForger] 草稿儲存: %s", dp.name)

        # 寫 Morphenix L3 提案
        proposal = {
            "id": f"proposal_skill_candidate_{skill_name}_{stamp}",
            "type": "skill_candidate",
            "status": "pending_review",
            "skill_name": skill_name,
            "draft_id": draft["id"],
            "mode": mode,
            "quality_self_score": draft["quality_self_score"],
            "created_at": now.isoformat(),
            "notes": f"SkillDraftForger 自動產出，來源：{source_file}",
        }
        pp = self._proposals_dir / f"{proposal['id']}.json"
        pp.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[SkillDraftForger] Morphenix 提案: %s", pp.name)

        return draft


# ---------------------------------------------------------------------------
# 獨立執行入口（供手動測試）
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    summary = SkillDraftForger().run()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
