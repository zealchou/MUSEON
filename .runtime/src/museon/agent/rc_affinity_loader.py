"""RC 親和載入器 — 從 SKILL.md 的 DNA27 親和對照區段解析 RC 宣告.

v10 核心架構：讓 DNA27 反射弧真正貫穿所有 45 個 skill。

每個 skill 的 SKILL.md 裡都有 `## DNA27 親和對照` 區段，宣告了：
  - 偏好觸發的反射叢集（preferred）
  - 限制使用的反射叢集（limited）
  - 禁止觸發時啟動的反射叢集（prohibited）

本模組在啟動時掃描所有 skill 檔案，建立三個反向索引：
  - preferred_by[RC-A2] = ["resonance", "shadow", ...]
  - limited_by[RC-B1]   = ["business-12", "xmodel", ...]
  - prohibited_by[RC-A1] = ["xmodel", "master-strategy", ...]

當 DNA27 ReflexRouter 觸發某些 RC 叢集時，
本模組查詢反向索引找出應喚醒的 skills —— 不需要關鍵字匹配。

設計原則：
  - skill 自己定義自己屬於哪條神經通路（不是我們硬編碼）
  - 禁止的 skill 會被 suppressed（當它宣告的禁止 RC 也被觸發時）
  - Shadow + Tantra 不特殊處理——它們的 RC 宣告跟其他 skill 一樣被解析
"""

import logging
import re
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# 解析 SKILL.md 中的 RC 代碼（支援 RC-A1 到 RC-F9）
_RC_PATTERN = re.compile(r"RC-[A-F]\d+", re.IGNORECASE)

# 偏好觸發的關鍵字模式
_PREFERRED_KEYWORDS = ("偏好觸發", "preferred_cluster_hits", "優先處理")
# 限制使用的關鍵字模式
_LIMITED_KEYWORDS = ("限制使用",)
# 禁止觸發的關鍵字模式
_PROHIBITED_KEYWORDS = ("禁止觸發", "禁止")


class RCAffinityIndex:
    """DNA27 RC → Skills 反向索引.

    從 skill 檔案的自我宣告建立，讓 DNA27 反射弧直接驅動 skill 選擇。
    """

    def __init__(self):
        # RC → skills 反向索引
        self.preferred_by: Dict[str, List[str]] = {}   # RC → skills that prefer it
        self.limited_by: Dict[str, List[str]] = {}     # RC → skills limited by it
        self.prohibited_by: Dict[str, List[str]] = {}  # RC → skills prohibited by it

        # skill → RCs 正向索引
        self.skill_preferred: Dict[str, Set[str]] = {}   # skill → its preferred RCs
        self.skill_limited: Dict[str, Set[str]] = {}     # skill → its limited RCs
        self.skill_prohibited: Dict[str, Set[str]] = {}  # skill → its prohibited RCs

        # 載入統計
        self._loaded_skills: List[str] = []
        self._skipped_skills: List[str] = []

    def load_from_skills_dir(self, skills_dir: str) -> None:
        """掃描 native skills 目錄，解析所有 SKILL.md 的 RC 宣告.

        Args:
            skills_dir: skills/native 目錄路徑
        """
        skills_path = Path(skills_dir)
        if not skills_path.is_dir():
            logger.warning(f"Skills dir not found: {skills_dir}")
            return

        for skill_dir in sorted(skills_path.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                self._skipped_skills.append(skill_dir.name)
                continue
            try:
                content = skill_md.read_text("utf-8")
                self._parse_skill(skill_dir.name, content)
                self._loaded_skills.append(skill_dir.name)
            except Exception as e:
                logger.warning(f"Failed to parse {skill_dir.name}/SKILL.md: {e}")
                self._skipped_skills.append(skill_dir.name)

        # 載入統計
        total_links = sum(len(v) for v in self.preferred_by.values())
        logger.info(
            f"RC affinity loaded: {len(self._loaded_skills)} skills, "
            f"{len(self.preferred_by)} RC clusters → {total_links} preferred links"
        )
        if self._skipped_skills:
            logger.debug(f"RC affinity skipped: {self._skipped_skills}")

    def _parse_skill(self, skill_name: str, content: str) -> None:
        """解析單個 SKILL.md 的 DNA27 親和對照區段."""
        section = self._extract_dna27_section(content)
        if not section:
            return

        for line in section.split("\n"):
            rcs = _RC_PATTERN.findall(line)
            if not rcs:
                continue

            # 標準化 RC 代碼為大寫
            rcs = [rc.upper() for rc in rcs]

            # 判斷這行是 preferred / limited / prohibited
            # 注意：「禁止」也包含「禁止觸發」，所以先檢查更具體的
            if any(kw in line for kw in _PREFERRED_KEYWORDS):
                for rc in rcs:
                    self.preferred_by.setdefault(rc, []).append(skill_name)
                self.skill_preferred.setdefault(skill_name, set()).update(rcs)
            elif any(kw in line for kw in _PROHIBITED_KEYWORDS):
                # v10.1: 偵測語義反轉模式
                # ❌ "禁止觸發：RC-C1 在 Resonance 中不啟動" = RC 被本 skill 壓制（反向）
                # ✅ "禁止觸發時啟動的反射叢集：RC-A1" = 本 skill 被 RC 壓制（正向）
                # 反轉信號：「中不啟動」「進行中不啟動」出現在 RC 代碼之後
                is_inverted = "中不啟動" in line or "進行中不啟動" in line
                if not is_inverted:
                    for rc in rcs:
                        self.prohibited_by.setdefault(rc, []).append(skill_name)
                    self.skill_prohibited.setdefault(skill_name, set()).update(rcs)
                # else: 反轉語義 → 不加入 prohibited_by（這些 RC 是被本 skill 壓制的）
            elif any(kw in line for kw in _LIMITED_KEYWORDS):
                for rc in rcs:
                    self.limited_by.setdefault(rc, []).append(skill_name)
                self.skill_limited.setdefault(skill_name, set()).update(rcs)

    def _extract_dna27_section(self, content: str) -> str:
        """提取 ## DNA27 親和對照 到下一個 ## 之間的內容.

        支援多種格式：
        - 標準格式：## DNA27 親和對照
        - business-12 格式：preferred_cluster_hits 在其他區段中
        """
        marker = "## DNA27 親和對照"
        idx = content.find(marker)
        if idx >= 0:
            # 找到標準區段 → 提取到下一個 ## 之間
            end = content.find("\n## ", idx + len(marker))
            return content[idx:end] if end > 0 else content[idx:]

        # 備用：business-12 等用不同格式
        if "preferred_cluster_hits" in content:
            # 提取包含 RC 宣告的段落
            lines = content.split("\n")
            result_lines = []
            for line in lines:
                if _RC_PATTERN.search(line) and any(
                    kw in line for kw in
                    _PREFERRED_KEYWORDS + _LIMITED_KEYWORDS + _PROHIBITED_KEYWORDS
                ):
                    result_lines.append(line)
            return "\n".join(result_lines) if result_lines else ""

        return ""

    def get_skills_for_clusters(
        self, fired_clusters: List[str]
    ) -> Dict[str, float]:
        """給定觸發的 RC 叢集，回傳應喚醒的 skills 及其分數.

        Args:
            fired_clusters: 被觸發的 RC 叢集 ID 列表（如 ["RC-A1", "RC-A2"]）

        Returns:
            Dict[skill_name, score]: 每個 skill 的喚醒分數
            禁止的 skill 會被排除。

        v10.1 歸一化修正：
          - 分母上限 cap=3，避免宣告多條 RC 的泛用型 skill 被稀釋
          - 保底提升至 0.3（有命中就有意義的分數）
          - 舊公式: hit/total → resonance(3RC, 1hit)=0.33, xmodel(5RC, 1hit)=0.20
          - 新公式: hit/min(total,3) → resonance=0.33, xmodel=0.33 ← 公平
        """
        if not fired_clusters:
            return {}

        # 標準化
        fired = [rc.upper() for rc in fired_clusters]

        scores: Dict[str, float] = {}
        suppressed: Set[str] = set()

        # 1. 收集所有被禁止的 skills
        for rc in fired:
            for skill in self.prohibited_by.get(rc, []):
                suppressed.add(skill)

        # 2. 收集所有偏好觸發的 skills 及其命中計數
        for rc in fired:
            for skill in self.preferred_by.get(rc, []):
                if skill not in suppressed:
                    scores[skill] = scores.get(skill, 0) + 1.0

        # 3. v10.1 歸一化：cap denominator at 3 + raise floor to 0.3
        for skill in list(scores.keys()):
            total_preferred = len(self.skill_preferred.get(skill, set()))
            if total_preferred > 0:
                # Cap denominator: 宣告 8 條 RC 不應比宣告 2 條弱 4 倍
                effective_denom = min(total_preferred, 3)
                scores[skill] = min(scores[skill] / effective_denom, 1.0)
            # 保底 0.3（有 RC 命中就有意義的喚醒信號）
            scores[skill] = max(scores[skill], 0.3)

        return scores

    def get_suppressed_skills(
        self, fired_clusters: List[str]
    ) -> Set[str]:
        """回傳應被壓制的 skills（它們宣告禁止當前觸發的 RC）."""
        fired = [rc.upper() for rc in fired_clusters]
        suppressed: Set[str] = set()
        for rc in fired:
            for skill in self.prohibited_by.get(rc, []):
                suppressed.add(skill)
        return suppressed

    @property
    def stats(self) -> Dict[str, int]:
        """載入統計."""
        return {
            "loaded_skills": len(self._loaded_skills),
            "skipped_skills": len(self._skipped_skills),
            "rc_clusters_with_preferred": len(self.preferred_by),
            "rc_clusters_with_prohibited": len(self.prohibited_by),
            "total_preferred_links": sum(len(v) for v in self.preferred_by.values()),
            "total_prohibited_links": sum(len(v) for v in self.prohibited_by.values()),
        }
