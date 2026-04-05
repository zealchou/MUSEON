"""skill_qa_gate.py — Skill 品質三維驗證閘門.

設計原則：
- 隔離 subagent 模式：審核者不帶生成 context，避免確認偏誤
- D1 行為驗證（純 CPU）：必要欄位 + hub 合法性 + 觸發詞衝突檢測
- D2 接線驗證（純 CPU）：plugin-registry 存在性 + io.outputs 目標合法性
- D3 壓測驗證（Haiku LLM）：模擬 3 個使用者提問，評估 Skill 的回應能力
- 三維 AND 邏輯：全過才算 PASS，任一失敗即隔離
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 9 種合法 Hub 值（來自 skill-routing-governance.md）
VALID_HUBS = {
    "product",
    "agent",
    "pulse",
    "gov",
    "nightly",
    "evolution",
    "tools",
    "learning",
    "billing",
}

# Skill frontmatter 必要欄位
REQUIRED_FIELDS = {"name", "type", "hub", "description"}

# D3 壓測使用的 Haiku 模型（節省成本，品質足夠）
HAIKU_MODEL = "claude-haiku-4-5-20251001"

# 合格門檻
PASS_THRESHOLD = 0.7


@dataclass
class DimensionResult:
    """單一維度的驗證結果."""

    dimension: str  # "D1_behavior" | "D2_wiring" | "D3_stress"
    passed: bool
    score: float  # 0.0 - 1.0
    details: List[str] = field(default_factory=list)  # 具體驗證項和結果


@dataclass
class QAResult:
    """三維驗證的最終結果."""

    passed: bool
    overall_score: float
    d1: DimensionResult
    d2: DimensionResult
    d3: DimensionResult
    recommendation: str  # "approve" | "quarantine" | "revise"
    evaluated_at: str  # ISO 8601 時間戳


class SkillQAGate:
    """Skill 品質三維驗證閘門.

    D1 行為驗證：觸發詞精準性、io 合理性、不與現有 Skill 衝突
    D2 接線驗證：connects_to 目標是否在 plugin-registry 已存在
    D3 壓測驗證：模擬 3 個使用者提問，Haiku 判斷 Skill 是否能有效回應
    """

    def __init__(self, workspace: Path, skills_dir: Path):
        """初始化驗證閘門.

        Args:
            workspace: MUSEON 根目錄（~/MUSEON）
            skills_dir: ~/.claude/skills/ — Skill 安裝目錄
        """
        self._workspace = workspace
        self._skills_dir = skills_dir
        # plugin-registry SKILL.md 是官方已註冊 Skill 的索引
        self._registry_path = skills_dir / "plugin-registry" / "SKILL.md"

    # -------------------------------------------------------------------------
    # 公開介面
    # -------------------------------------------------------------------------

    def evaluate(self, draft_path: Path) -> QAResult:
        """三維驗證，返回結構化評分.

        Args:
            draft_path: 草稿 JSON 檔案路徑，格式需含 skill_md_content 欄位

        Returns:
            QAResult — 包含三維驗證結果與最終建議
        """
        # 讀取草稿（檔案不存在時 graceful 失敗）
        if not draft_path.exists():
            logger.warning("草稿檔案不存在：%s", draft_path)
            return self._make_error_result(f"草稿檔案不存在：{draft_path}")

        try:
            draft = json.loads(draft_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("讀取草稿失敗：%s", exc)
            return self._make_error_result(f"讀取草稿失敗：{exc}")

        skill_md = draft.get("skill_md_content", "")
        if not skill_md:
            return self._make_error_result("草稿缺少 skill_md_content 欄位")

        # D1.5 語意審計（G2，純 CPU，在 D1 之前擋截意圖不一致）
        d1_5_audit = self._verify_semantic_intent(skill_md)
        if not d1_5_audit.passed:
            # 語意審計失敗 → 直接隔離，跳過後續驗證
            logger.warning(
                "SkillQAGate: D1.5 語意審計失敗，warnings=%s", d1_5_audit.details
            )
            d1_fail = DimensionResult(
                dimension="D1_behavior",
                passed=False,
                score=0.0,
                details=[f"D1.5 pre-check FAIL: {d1_5_audit.details}"],
            )
            d2_skip = DimensionResult(dimension="D2_wiring", passed=False, score=0.0, details=["Skipped due to D1.5 failure"])
            d3_skip = DimensionResult(dimension="D3_stress", passed=False, score=0.0, details=["Skipped due to D1.5 failure"])
            return QAResult(
                passed=False,
                overall_score=0.0,
                d1=d1_fail,
                d2=d2_skip,
                d3=d3_skip,
                recommendation="quarantine",
                evaluated_at=datetime.now(timezone.utc).isoformat(),
            )

        # 三維驗證（依序執行，D3 需要 LLM）
        d1 = self._verify_behavior(skill_md)
        d2 = self._verify_wiring(skill_md)
        d3 = self._verify_stress_test(skill_md)

        passed = d1.passed and d2.passed and d3.passed
        overall_score = (d1.score + d2.score + d3.score) / 3.0

        # 決定最終建議
        if passed and overall_score >= PASS_THRESHOLD:
            recommendation = "approve"
        elif overall_score >= PASS_THRESHOLD:
            recommendation = "revise"  # 部分維度未過，但分數勉強
        else:
            recommendation = "quarantine"

        result = QAResult(
            passed=passed,
            overall_score=round(overall_score, 4),
            d1=d1,
            d2=d2,
            d3=d3,
            recommendation=recommendation,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

        # D3 失敗時將原因寫回草稿 JSON
        if not d3.passed:
            self._write_quarantine_reason(draft_path, draft, d3)

        return result

    # -------------------------------------------------------------------------
    # D1.5：語意審計（純 CPU，G2 安全升級）
    # -------------------------------------------------------------------------

    def _verify_semantic_intent(self, skill_md: str) -> DimensionResult:
        """D1.5 語意審計 — 檢查 description 宣稱與正文指令是否一致.

        使用 skill_scout.semantic_intent_audit 的純 CPU 啟發式規則。
        risk_score >= 0.5 → 立即隔離，後續 D1/D2/D3 跳過。
        """
        from museon.nightly.skill_scout import semantic_intent_audit

        audit_result = semantic_intent_audit(skill_md)
        passed = audit_result["passed"]
        warnings = audit_result["warnings"]
        risk_score = audit_result["risk_score"]

        details: List[str] = []
        if passed:
            details.append(f"✓ D1.5 語意審計通過（risk_score={risk_score:.2f}）")
        else:
            for w in warnings:
                details.append(f"✗ {w}")
            details.append(f"  risk_score={risk_score:.2f} >= 0.5，強制隔離")

        # 將 risk_score 轉換為安全分數（1.0 = 完全安全）
        safety_score = max(0.0, 1.0 - risk_score)

        return DimensionResult(
            dimension="D1.5_semantic_audit",
            passed=passed,
            score=round(safety_score, 4),
            details=details,
        )

    # -------------------------------------------------------------------------
    # D1：行為驗證（純 CPU）
    # -------------------------------------------------------------------------

    def _verify_behavior(self, skill_md: str) -> DimensionResult:
        """D1 行為驗證.

        檢查項目：
        1. frontmatter 必要欄位完整度
        2. hub 是否為 9 種合法值之一
        3. 觸發詞是否與已有 Skill 衝突
        """
        details: List[str] = []
        checks_passed = 0
        checks_total = 3

        # --- 解析 frontmatter ---
        frontmatter = self._parse_frontmatter(skill_md)

        # 1. 必要欄位檢查
        missing = REQUIRED_FIELDS - set(frontmatter.keys())
        if not missing:
            details.append(f"✓ 必要欄位完整：{sorted(REQUIRED_FIELDS)}")
            checks_passed += 1
        else:
            details.append(f"✗ 缺少必要欄位：{sorted(missing)}")

        # 2. hub 合法性檢查
        hub_value = frontmatter.get("hub", "")
        if hub_value in VALID_HUBS:
            details.append(f"✓ hub 合法：{hub_value}")
            checks_passed += 1
        else:
            details.append(
                f"✗ hub 不合法：'{hub_value}'，合法值為 {sorted(VALID_HUBS)}"
            )

        # 3. 觸發詞衝突檢查
        new_triggers = self._extract_triggers(skill_md)
        conflict = self._check_trigger_conflict(new_triggers)
        if not conflict:
            details.append(f"✓ 觸發詞無衝突：{new_triggers or '（無觸發詞）'}")
            checks_passed += 1
        else:
            details.append(f"✗ 觸發詞衝突：{conflict}")

        score = checks_passed / checks_total
        passed = checks_passed == checks_total

        return DimensionResult(
            dimension="D1_behavior",
            passed=passed,
            score=round(score, 4),
            details=details,
        )

    # -------------------------------------------------------------------------
    # D2：接線驗證（純 CPU）
    # -------------------------------------------------------------------------

    def _verify_wiring(self, skill_md: str) -> DimensionResult:
        """D2 接線驗證.

        檢查項目：
        1. connects_to 列出的所有 Skill 是否在 plugin-registry 已存在
        2. io.outputs 的 to 欄位是否指向已註冊 Skill 或 "user"
        """
        details: List[str] = []

        # 載入 registry 已知 Skill 集合
        known_skills = self._load_known_skills()
        if not known_skills:
            details.append("⚠ plugin-registry 無法讀取，接線驗證降級為部分通過")
            return DimensionResult(
                dimension="D2_wiring", passed=True, score=0.5, details=details
            )

        frontmatter = self._parse_frontmatter(skill_md)
        issues: List[str] = []
        checks_ok: List[str] = []

        # 1. connects_to 目標存在性
        connects_to = frontmatter.get("connects_to", [])
        if isinstance(connects_to, list):
            for target in connects_to:
                if target in known_skills or target == "user":
                    checks_ok.append(f"connects_to.{target}")
                else:
                    issues.append(f"connects_to 目標不存在：'{target}'")
        elif connects_to:
            # 字串格式（單一目標）
            if connects_to not in known_skills and connects_to != "user":
                issues.append(f"connects_to 目標不存在：'{connects_to}'")

        # 2. io.outputs.to 欄位
        io_block = frontmatter.get("io", {})
        outputs = []
        if isinstance(io_block, dict):
            outputs = io_block.get("outputs", [])
        for out in outputs if isinstance(outputs, list) else []:
            if isinstance(out, dict):
                to_target = out.get("to", "")
                if to_target in known_skills or to_target == "user":
                    checks_ok.append(f"io.outputs.to={to_target}")
                else:
                    issues.append(f"io.outputs.to 目標不存在：'{to_target}'")

        # 彙整結果
        for ok in checks_ok:
            details.append(f"✓ {ok}")
        for issue in issues:
            details.append(f"✗ {issue}")

        if not checks_ok and not issues:
            details.append("ℹ 無 connects_to 或 io.outputs，跳過接線驗證")
            return DimensionResult(
                dimension="D2_wiring", passed=True, score=1.0, details=details
            )

        total = len(checks_ok) + len(issues)
        score = len(checks_ok) / total if total > 0 else 1.0
        passed = len(issues) == 0

        return DimensionResult(
            dimension="D2_wiring",
            passed=passed,
            score=round(score, 4),
            details=details,
        )

    # -------------------------------------------------------------------------
    # D3：壓測驗證（Haiku LLM）
    # -------------------------------------------------------------------------

    def _verify_stress_test(self, skill_md: str) -> DimensionResult:
        """D3 壓測驗證.

        1. 從 Skill 的觸發詞和描述，自動生成 3 個模擬使用者提問
        2. 用 Haiku 判斷：這個 Skill 的處理方式能否有效回應這些提問？
        3. 分數 = 通過的提問數 / 3
        """
        details: List[str] = []

        try:
            import anthropic
        except ImportError:
            details.append("⚠ anthropic 套件未安裝，D3 壓測降級為跳過（score=0.5）")
            return DimensionResult(
                dimension="D3_stress", passed=True, score=0.5, details=details
            )

        frontmatter = self._parse_frontmatter(skill_md)
        skill_name = frontmatter.get("name", "未知 Skill")
        description = frontmatter.get("description", "")
        triggers = self._extract_triggers(skill_md)

        # 生成 3 個模擬提問（用 Haiku 生成，節省成本）
        test_questions = self._generate_test_questions(
            skill_name, description, triggers
        )
        if not test_questions:
            details.append("⚠ 無法生成測試提問，D3 壓測降級為跳過（score=0.5）")
            return DimensionResult(
                dimension="D3_stress", passed=True, score=0.5, details=details
            )

        # 逐一判斷每個提問
        passed_count = 0
        for i, question in enumerate(test_questions, 1):
            ok, reason = self._judge_question(skill_md, skill_name, question)
            if ok:
                passed_count += 1
                details.append(f"✓ 測試 {i}：{question[:40]}… → 通過")
            else:
                details.append(f"✗ 測試 {i}：{question[:40]}… → 失敗（{reason}）")

        score = passed_count / len(test_questions)
        passed = score >= PASS_THRESHOLD  # 至少 2/3 通過才算過

        return DimensionResult(
            dimension="D3_stress",
            passed=passed,
            score=round(score, 4),
            details=details,
        )

    def _generate_test_questions(
        self,
        skill_name: str,
        description: str,
        triggers: List[str],
    ) -> List[str]:
        """用 Haiku 從 Skill 的觸發詞和描述生成 3 個測試提問."""
        try:
            import anthropic

            _api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not _api_key:
                logger.warning(
                    "skill_qa_gate: ANTHROPIC_API_KEY 未設定，"
                    "_generate_test_questions 跳過（MUSEON 使用 Claude MAX CLI OAuth，"
                    "此模組需要直接 API key 才能運作）"
                )
                return []
            client = anthropic.Anthropic(api_key=_api_key)
            trigger_str = "、".join(triggers) if triggers else "（無觸發詞）"
            prompt = (
                f"你是一個使用者，想測試一個名為「{skill_name}」的 AI 技能。\n"
                f"這個技能的描述：{description}\n"
                f"觸發詞：{trigger_str}\n\n"
                f"請生成 3 個真實使用者可能會問的問題，每行一個，不要編號，不要其他說明。"
                f"問題要能代表這個技能的核心使用場景。"
            )
            resp = client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
            questions = [q.strip() for q in raw.splitlines() if q.strip()]
            return questions[:3]
        except Exception as exc:  # noqa: BLE001
            logger.warning("生成測試提問失敗：%s", exc)
            return []

    def _judge_question(
        self, skill_md: str, skill_name: str, question: str
    ) -> tuple[bool, str]:
        """用 Haiku 判斷 Skill 是否能有效回應指定提問.

        Returns:
            (通過與否, 理由說明)
        """
        try:
            import anthropic

            _api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not _api_key:
                logger.warning(
                    "skill_qa_gate: ANTHROPIC_API_KEY 未設定，"
                    "_judge_question 跳過（MUSEON 使用 Claude MAX CLI OAuth，"
                    "此模組需要直接 API key 才能運作）"
                )
                return False, "ANTHROPIC_API_KEY 未設定，無法執行 LLM 判斷"
            client = anthropic.Anthropic(api_key=_api_key)
            # 只傳遞 Skill 的 frontmatter 摘要，不傳完整 SKILL.md（節省 token）
            frontmatter = self._parse_frontmatter(skill_md)
            skill_summary = (
                f"名稱：{frontmatter.get('name', skill_name)}\n"
                f"類型：{frontmatter.get('type', '未知')}\n"
                f"描述：{frontmatter.get('description', '無')}\n"
                f"hub：{frontmatter.get('hub', '未知')}"
            )
            prompt = (
                f"以下是一個 AI 技能的摘要：\n{skill_summary}\n\n"
                f"使用者問：「{question}」\n\n"
                f"請判斷：這個技能能否對這個問題產出有用的回覆？\n"
                f"只回答：通過 或 不通過，然後用一句話說明理由。"
            )
            resp = client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=128,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = resp.content[0].text.strip()
            clean = answer.lstrip(" \t✓✅▶→·•").strip()
            passed = clean.startswith("通過") and not clean.startswith("不通過")
            return passed, answer
        except Exception as exc:  # noqa: BLE001
            logger.warning("壓測判斷失敗：%s", exc)
            return False, f"LLM 呼叫失敗：{exc}"

    # -------------------------------------------------------------------------
    # 輔助方法
    # -------------------------------------------------------------------------

    def _parse_frontmatter(self, skill_md: str) -> Dict[str, Any]:
        """解析 SKILL.md 的 YAML frontmatter（不依賴 yaml 套件）.

        只解析簡單的 key: value 格式，以及基本的列表（- item）。
        複雜的巢狀結構回傳原始字串值，不嘗試解析。
        """
        result: Dict[str, Any] = {}
        in_frontmatter = False
        current_key: Optional[str] = None
        current_list: Optional[List[str]] = None

        for line in skill_md.splitlines():
            stripped = line.rstrip()

            if stripped == "---":
                if not in_frontmatter:
                    in_frontmatter = True
                    continue
                else:
                    # 結束 frontmatter
                    if current_key and current_list is not None:
                        result[current_key] = current_list
                    break

            if not in_frontmatter:
                continue

            # 列表項目（以 "- " 開頭）
            if stripped.startswith("  - ") or stripped.startswith("- "):
                item = stripped.lstrip(" ").lstrip("- ").strip()
                if current_list is not None:
                    current_list.append(item)
                continue

            # key: value 行
            if ":" in stripped and not stripped.startswith(" "):
                # 先存上一個 list key
                if current_key and current_list is not None:
                    result[current_key] = current_list
                    current_list = None

                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip()

                if value == "" or value == ">":
                    # 可能是列表或多行值的開始
                    current_key = key
                    current_list = []
                else:
                    result[key] = value
                    current_key = key
                    current_list = None
            elif stripped.startswith("  ") and current_key:
                # 多行字串接續（description: >）
                if current_list is not None:
                    current_list.append(stripped.strip())
                else:
                    existing = result.get(current_key, "")
                    result[current_key] = (
                        (existing + " " + stripped.strip()) if existing else stripped.strip()
                    )

        # 補充處理 description 是 list 的情況（合併為字串）
        if isinstance(result.get("description"), list):
            result["description"] = " ".join(result["description"])

        return result

    def _extract_triggers(self, skill_md: str) -> List[str]:
        """從 SKILL.md 內文提取觸發詞（找 trigger: 或觸發詞區塊）."""
        triggers: List[str] = []
        for line in skill_md.splitlines():
            stripped = line.strip()
            if stripped.startswith("trigger:") or stripped.startswith("triggers:"):
                _, _, value = stripped.partition(":")
                value = value.strip().strip('"').strip("'")
                if value:
                    triggers.append(value)
            elif "觸發詞" in stripped and "：" in stripped:
                _, _, value = stripped.partition("：")
                triggers.extend([v.strip() for v in value.split("、") if v.strip()])
        return triggers

    def _check_trigger_conflict(self, new_triggers: List[str]) -> Optional[str]:
        """比對新 Skill 的觸發詞是否與現有 Skill 衝突.

        Returns:
            衝突說明字串，或 None（無衝突）
        """
        if not new_triggers or not self._registry_path.exists():
            return None  # 無觸發詞或無 registry，跳過

        try:
            registry_content = self._registry_path.read_text(encoding="utf-8")
        except OSError:
            return None

        conflicts: List[str] = []
        for trigger in new_triggers:
            if trigger in registry_content:
                conflicts.append(trigger)

        return f"與現有 Skill 觸發詞重疊：{conflicts}" if conflicts else None

    def _load_known_skills(self) -> set:
        """從 skills_dir 掃描已安裝的 Skill 名稱集合."""
        known: set = set()
        known.add("user")  # "user" 永遠是合法的 io 目標

        if not self._skills_dir.exists():
            return known

        try:
            for item in self._skills_dir.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    known.add(item.name)
        except OSError as exc:
            logger.warning("掃描 skills_dir 失敗：%s", exc)

        return known

    def _write_quarantine_reason(
        self, draft_path: Path, draft: Dict[str, Any], d3: DimensionResult
    ) -> None:
        """D3 失敗時將隔離原因寫回草稿 JSON."""
        try:
            draft["quarantine_reason"] = {
                "dimension": "D3_stress",
                "details": d3.details,
                "score": d3.score,
                "quarantined_at": datetime.now(timezone.utc).isoformat(),
            }
            draft_path.write_text(
                json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info("D3 隔離原因已寫回：%s", draft_path)
        except OSError as exc:
            logger.error("寫回隔離原因失敗：%s", exc)

    def _make_error_result(self, reason: str) -> QAResult:
        """建立錯誤情況下的 QAResult（全部失敗）."""
        err = DimensionResult(
            dimension="error", passed=False, score=0.0, details=[reason]
        )
        return QAResult(
            passed=False,
            overall_score=0.0,
            d1=err,
            d2=err,
            d3=err,
            recommendation="quarantine",
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
