"""Skill Scout — 外部 Skill 偵查兵.

自動搜尋 ClawHub、Claude Skills、GitHub 上的外部 Skill，
經過安全過濾後交給 DSE 評估 + ACSF 鍛造。

設計原則：
- 搜尋 + 過濾 = 純 CPU（關鍵字匹配、黑名單比對）
- DSE 評估 = Sonnet（需要深度判斷，不省這個 Token）
- ACSF 鍛造 = Sonnet（鍛造品質不能妥協）
- 安全第一：12% 惡意率教訓（OpenClaw ClawHub 事件）
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# 已知惡意模式（純 CPU 比對）
MALICIOUS_PATTERNS = [
    r"eval\s*\(",             # 動態執行
    r"exec\s*\(",             # 動態執行
    r"os\.system",            # 系統指令
    r"subprocess",            # 子進程
    r"__import__",            # 動態匯入
    r"requests\.post",        # 資料外傳
    r"urllib\.request",       # 資料外傳
    r"base64\.b64decode",     # 編碼混淆
    r"ignore.*previous",      # prompt injection
    r"disregard.*instructions",  # prompt injection
    r"you are now",           # role hijacking
    r"act as.*admin",         # role hijacking
    r"send.*data.*to",        # data exfiltration
    r"upload.*to.*server",    # data exfiltration
]

# 安全黑名單域名
BLOCKED_SOURCES = [
    "malware", "hack", "exploit", "crack",
    "phishing", "trojan", "backdoor",
]


@dataclass
class SkillCandidate:
    """外部 Skill 候選."""
    name: str
    source: str  # "clawhub" | "github" | "claude_skills"
    description: str
    url: str
    raw_content: str = ""
    safety_score: float = 0.0  # 0-1, 1 = safe
    relevance_score: float = 0.0  # 0-1, 1 = highly relevant
    dse_assessment: Optional[Dict[str, Any]] = None
    rejected: bool = False
    reject_reason: str = ""


@dataclass
class CapabilityGap:
    """能力缺口."""
    description: str
    trigger_type: str  # "quality" | "usage" | "request" | "trend"
    evidence: str
    priority: float = 0.5  # 0-1
    detected_at: str = ""

    def __post_init__(self):
        if not self.detected_at:
            self.detected_at = datetime.now().isoformat()


class SkillScout:
    """外部 Skill 偵查兵.

    職責：
    1. 根據能力缺口搜尋外部 Skill（CPU: 關鍵字建構 → LLM: 搜尋）
    2. 安全過濾（純 CPU：模式匹配 + 黑名單）
    3. 相關性排序（CPU: TF-IDF 簡易評分）
    4. 輸出候選清單供 DSE 評估
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._scan_log_path = self.data_dir / "skill_scout_log.jsonl"
        self._known_skills_path = self.data_dir / "known_external_skills.json"

        # 載入已知外部 Skill（避免重複掃描）
        self._known_skills = self._load_known_skills()

    async def scan(
        self, gap: CapabilityGap, max_candidates: int = 5
    ) -> List[SkillCandidate]:
        """根據能力缺口搜尋外部 Skill.

        Phase 1: 建構搜尋關鍵字（純 CPU）
        Phase 2: 安全過濾候選結果（純 CPU）
        Phase 3: 相關性排序（純 CPU）

        注意：實際的網路搜尋需要 web_search 工具，
        此方法提供候選清單的 CPU 前處理框架。

        Args:
            gap: 能力缺口
            max_candidates: 最多回傳幾個候選

        Returns:
            安全過濾後的候選清單
        """
        logger.info(f"SkillScout 開始搜尋：{gap.description}")

        # Phase 1: 建構搜尋關鍵字（純 CPU）
        keywords = self._build_search_keywords(gap)
        logger.info(f"搜尋關鍵字：{keywords}")

        # Phase 2: 模擬搜尋結果（實際部署時接 web_search）
        # 目前回傳空列表，由 NightlyJob 在有網路能力時填入
        raw_candidates: List[SkillCandidate] = []

        # Phase 3: 安全過濾（純 CPU）
        safe_candidates = []
        for candidate in raw_candidates:
            is_safe, reason = self._safety_check(candidate)
            if is_safe:
                safe_candidates.append(candidate)
            else:
                candidate.rejected = True
                candidate.reject_reason = reason
                logger.warning(
                    f"安全過濾攔截：{candidate.name} | {reason}"
                )

        # Phase 4: 相關性排序（純 CPU）
        for candidate in safe_candidates:
            candidate.relevance_score = self._compute_relevance(
                candidate, gap
            )

        safe_candidates.sort(key=lambda c: c.relevance_score, reverse=True)

        # 記錄掃描日誌
        self._log_scan(gap, safe_candidates)

        return safe_candidates[:max_candidates]

    def detect_capability_gaps(
        self,
        quality_history: Dict[str, List[float]],
        usage_data: Dict[str, Any],
        skill_names: List[str],
    ) -> List[CapabilityGap]:
        """偵測能力缺口 — 純 CPU.

        三種偵測方式：
        1. 品質驅動：某類任務 Q-Score 持續低分
        2. 使用驅動：重複任務類型無專用 Skill
        3. 時間驅動：長期未更新的 Skill 領域

        Args:
            quality_history: {skill_name: [scores]}
            usage_data: 使用日誌
            skill_names: 現有 Skill 名稱

        Returns:
            能力缺口清單
        """
        gaps = []

        # 1. 品質驅動
        for skill, scores in quality_history.items():
            recent = scores[-5:] if len(scores) >= 5 else scores
            if recent and sum(recent) / len(recent) < 0.6:
                gaps.append(CapabilityGap(
                    description=f"Skill '{skill}' 品質持續低於 60%",
                    trigger_type="quality",
                    evidence=f"最近 {len(recent)} 次平均分：{sum(recent)/len(recent):.2f}",
                    priority=0.8,
                ))

        # 2. 使用驅動：檢查是否有重複的未匹配任務
        task_types = usage_data.get("unmatched_tasks", {})
        for task_type, count in task_types.items():
            if count >= 3:  # 同類任務出現 3 次以上
                gaps.append(CapabilityGap(
                    description=f"重複任務 '{task_type}' 無專用 Skill（出現 {count} 次）",
                    trigger_type="usage",
                    evidence=f"累計 {count} 次無匹配",
                    priority=0.7,
                ))

        return gaps

    # ═══════════════════════════════════════════
    # CPU-only 工具方法
    # ═══════════════════════════════════════════

    def _build_search_keywords(self, gap: CapabilityGap) -> List[str]:
        """建構搜尋關鍵字 — 純 CPU.

        從缺口描述中提取關鍵字，加上平台前綴。
        """
        # 基礎關鍵字提取（簡易 TF）
        desc = gap.description.lower()
        # 移除停用詞
        stopwords = {"的", "了", "是", "在", "和", "有", "不", "這", "那", "我", "你", "他"}
        words = re.findall(r"[\w]+", desc)
        keywords = [w for w in words if w not in stopwords and len(w) > 1]

        # 加上搜尋平台前綴
        search_queries = []
        base_query = " ".join(keywords[:5])
        search_queries.append(f"openclaw skill {base_query}")
        search_queries.append(f"claude skill {base_query}")
        search_queries.append(f"ai agent {base_query} github")

        return search_queries

    def _safety_check(self, candidate: SkillCandidate) -> tuple:
        """安全檢查 — 純 CPU.

        檢查惡意模式、黑名單域名、prompt injection。

        Returns:
            (is_safe, reason)
        """
        content = candidate.raw_content + " " + candidate.description

        # 1. 惡意模式匹配
        for pattern in MALICIOUS_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return False, f"惡意模式偵測：{pattern}"

        # 2. 黑名單域名
        url_lower = candidate.url.lower()
        for blocked in BLOCKED_SOURCES:
            if blocked in url_lower:
                return False, f"黑名單來源：{blocked}"

        # 3. 長度異常（過短可能是空殼、過長可能塞垃圾）
        if len(candidate.raw_content) < 50:
            return False, "內容過短（可能為空殼）"

        # 4. 基礎安全分數
        candidate.safety_score = 0.7  # 通過基礎檢查的預設分數

        return True, ""

    def _compute_relevance(
        self, candidate: SkillCandidate, gap: CapabilityGap
    ) -> float:
        """計算相關性分數 — 純 CPU.

        簡易 TF-IDF 風格：缺口關鍵字在候選 Skill 中的出現頻率。
        """
        gap_words = set(re.findall(r"[\w]+", gap.description.lower()))
        candidate_text = (
            candidate.name + " " + candidate.description
        ).lower()
        candidate_words = set(re.findall(r"[\w]+", candidate_text))

        if not gap_words:
            return 0.0

        overlap = gap_words & candidate_words
        return len(overlap) / len(gap_words)

    def _load_known_skills(self) -> Dict[str, Any]:
        """載入已知外部 Skill 索引."""
        if self._known_skills_path.exists():
            try:
                return json.loads(
                    self._known_skills_path.read_text(encoding="utf-8")
                )
            except Exception as e:
                logger.debug(f"[SKILL_SCOUT] data read failed (degraded): {e}")
        return {}

    def _log_scan(
        self, gap: CapabilityGap, candidates: List[SkillCandidate]
    ) -> None:
        """記錄掃描日誌 — 純 CPU 檔案寫入."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "gap": gap.description,
            "trigger_type": gap.trigger_type,
            "candidates_found": len(candidates),
            "top_candidate": candidates[0].name if candidates else None,
        }
        try:
            with open(self._scan_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"掃描日誌寫入失敗：{e}")
