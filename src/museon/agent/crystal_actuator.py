"""Crystal Actuator — 結晶行為規則引擎.

將高置信度結晶轉化為「行為規則」，讓結晶從「建議」升級為「系統行為」。

設計原則：
  - 不同來源的結晶驅動不同類型的行為改變
    * 使用者互動結晶 → 溝通風格偏好
    * 外部探索結晶   → 能力邊界擴展
    * 自我反芻結晶   → 流程優化調整
  - 規則有 TTL：套用後追蹤效果，正面強化、負面淘汰
  - 不可變安全底線：規則不能覆蓋 Kernel 護欄

依據 DSE 分析實作：知識→行為 的翻譯層。
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# 規則類型定義
# ═══════════════════════════════════════════

RULE_TYPE_STYLE = "style"            # 溝通風格（來自使用者互動）
RULE_TYPE_CAPABILITY = "capability"  # 能力邊界（來自外部探索）
RULE_TYPE_PROCESS = "process"        # 流程優化（來自自我反芻）

# 結晶 origin → 規則類型映射
ORIGIN_TO_RULE_TYPE = {
    "conversation": RULE_TYPE_STYLE,
    "soul_pulse_reflection": RULE_TYPE_PROCESS,
    "exploration": RULE_TYPE_CAPABILITY,
    "wee_reflection": RULE_TYPE_PROCESS,
    "morphenix_evolution": RULE_TYPE_PROCESS,
    "outward_self": RULE_TYPE_CAPABILITY,
    "outward_service": RULE_TYPE_CAPABILITY,
}

# 結晶類型 → 規則動作映射
CRYSTAL_TYPE_ACTION = {
    "Lesson": "guard",        # 教訓 → 防護規則
    "Insight": "preference",  # 洞見 → 偏好規則
    "Pattern": "predict",     # 模式 → 預測規則
    "Hypothesis": "experiment",  # 假設 → 實驗規則
}

# 規則最大存活天數
RULE_TTL_DAYS = 30

# 規則最大數量（防止膨脹）
MAX_ACTIVE_RULES = 50

# 結晶晉升為規則的門檻
RI_THRESHOLD = 0.4              # 共振指數門檻
REFERENCE_COUNT_THRESHOLD = 3   # 最低引用次數
VERIFICATION_ELIGIBLE = {"observed", "tested", "proven"}  # 驗證等級門檻


# ═══════════════════════════════════════════
# CrystalActuator
# ═══════════════════════════════════════════


class CrystalActuator:
    """結晶行為規則引擎 — 把「學到的」轉化為「做到的」.

    職責：
      1. 掃描結晶池 → 識別可轉化的高置信結晶
      2. 翻譯結晶 → 行為規則（JSON）
      3. 載入規則 → 供 Brain 讀取並影響行為
      4. 追蹤回饋 → 規則的正/負面效果
      5. 新陳代謝 → 淘汰無效規則、強化有效規則
    """

    def __init__(self, workspace: Path, event_bus: Optional[Any] = None) -> None:
        self._workspace = Path(workspace)
        self._event_bus = event_bus
        self._rules_file = self._workspace / "_system" / "crystal_rules.json"
        self._rules_file.parent.mkdir(parents=True, exist_ok=True)
        self._rules: List[Dict[str, Any]] = []
        self._load_rules()

    # ═══════════════════════════════════════════
    # 公開 API
    # ═══════════════════════════════════════════

    def actualize(self, knowledge_lattice: Any) -> Dict[str, Any]:
        """掃描結晶池並轉化為行為規則（Nightly 呼叫）.

        Args:
            knowledge_lattice: KnowledgeLattice 實例

        Returns:
            {"new_rules": int, "expired_rules": int, "total_active": int}
        """
        result = {"new_rules": 0, "expired_rules": 0, "total_active": 0}

        # Step 1: 淘汰過期規則
        result["expired_rules"] = self._expire_stale_rules()

        # Step 2: 掃描可轉化的結晶
        eligible = self._scan_eligible_crystals(knowledge_lattice)

        # Step 3: 翻譯為規則（去重）
        for crystal in eligible:
            if self._already_has_rule(crystal.cuid):
                continue
            if len(self._rules) >= MAX_ACTIVE_RULES:
                logger.info("Crystal Actuator: 規則數量已達上限，跳過新增")
                break

            rule = self._translate_to_rule(crystal)
            if rule:
                self._rules.append(rule)
                result["new_rules"] += 1
                logger.info(
                    f"Crystal Actuator: 新規則 [{rule['rule_type']}] "
                    f"← {crystal.cuid}: {crystal.g1_summary[:30]}"
                )

        result["total_active"] = len(self._rules)
        self._save_rules()

        if result["new_rules"] > 0 or result["expired_rules"] > 0:
            logger.info(
                f"Crystal Actuator: +{result['new_rules']} 新規則, "
                f"-{result['expired_rules']} 過期, "
                f"={result['total_active']} 活躍"
            )

        return result

    def get_active_rules(self, rule_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """取得活躍規則（供 Brain 讀取）.

        Args:
            rule_type: 可選，篩選特定類型

        Returns:
            活躍規則列表
        """
        now = datetime.now(TZ8).isoformat()
        active = [
            r for r in self._rules
            if r.get("status") == "active"
            and r.get("expires_at", "9999") > now
        ]
        if rule_type:
            active = [r for r in active if r.get("rule_type") == rule_type]
        return active

    def record_feedback(self, rule_id: str, positive: bool) -> None:
        """記錄規則的使用回饋（P3 回饋迴圈）.

        Args:
            rule_id: 規則 ID
            positive: True=正面效果, False=負面效果
        """
        for rule in self._rules:
            if rule.get("rule_id") == rule_id:
                if positive:
                    rule["positive_count"] = rule.get("positive_count", 0) + 1
                else:
                    rule["negative_count"] = rule.get("negative_count", 0) + 1
                rule["last_feedback"] = datetime.now(TZ8).isoformat()
                break
        self._save_rules()

    def metabolize(self) -> Dict[str, Any]:
        """新陳代謝：強化有效規則、淘汰無效規則（P3 核心）.

        Returns:
            {"strengthened": int, "weakened": int, "removed": int}
        """
        result = {"strengthened": 0, "weakened": 0, "removed": 0}

        to_remove = []
        for rule in self._rules:
            pos = rule.get("positive_count", 0)
            neg = rule.get("negative_count", 0)
            total = pos + neg

            if total < 3:
                continue  # 回饋不足，跳過

            ratio = pos / total if total > 0 else 0

            if ratio >= 0.7:
                # 正面回饋 >= 70% → 強化（延長 TTL）
                rule["strength"] = min(rule.get("strength", 1.0) + 0.1, 2.0)
                expires = datetime.now(TZ8) + timedelta(days=RULE_TTL_DAYS)
                rule["expires_at"] = expires.isoformat()
                result["strengthened"] += 1
            elif ratio <= 0.3:
                # 負面回饋 >= 70% → 弱化
                rule["strength"] = max(rule.get("strength", 1.0) - 0.3, 0)
                if rule["strength"] <= 0:
                    to_remove.append(rule["rule_id"])
                    result["removed"] += 1
                else:
                    result["weakened"] += 1

        # 移除失效規則
        self._rules = [r for r in self._rules if r.get("rule_id") not in to_remove]
        self._save_rules()

        if any(v > 0 for v in result.values()):
            logger.info(f"Crystal Actuator metabolism: {result}")

        return result

    def format_rules_for_prompt(self) -> str:
        """將活躍規則格式化為 Brain 可注入的 prompt 段落.

        Returns:
            格式化的規則文本（如果無規則則回空字串）
        """
        active = self.get_active_rules()
        if not active:
            return ""

        lines = ["## 行為規則（來自已驗證的知識結晶）\n"]

        for rule in active:
            strength = rule.get("strength", 1.0)
            icon = "🔴" if strength >= 1.5 else "🟡" if strength >= 1.0 else "⚪"
            action = rule.get("action", "note")
            summary = rule.get("summary", "")
            directive = rule.get("directive", "")

            if action == "guard":
                lines.append(f"- {icon} ⛔ 教訓防護：{summary}")
                if directive:
                    lines.append(f"  → {directive}")
            elif action == "preference":
                lines.append(f"- {icon} 💡 偏好規則：{summary}")
                if directive:
                    lines.append(f"  → {directive}")
            elif action == "predict":
                lines.append(f"- {icon} 🔮 模式預測：{summary}")
                if directive:
                    lines.append(f"  → {directive}")
            elif action == "experiment":
                lines.append(f"- {icon} 🧪 實驗規則：{summary}")
                if directive:
                    lines.append(f"  → {directive}")

        lines.append("\n請依據以上規則調整你的回答行為。")
        return "\n".join(lines)

    # ═══════════════════════════════════════════
    # 內部方法
    # ═══════════════════════════════════════════

    def _scan_eligible_crystals(self, lattice: Any) -> list:
        """掃描符合轉化條件的結晶."""
        eligible = []
        try:
            all_crystals = lattice.get_all_crystals()
            for crystal in all_crystals:
                if crystal.archived or crystal.status != "active":
                    continue
                if crystal.ri_score < RI_THRESHOLD:
                    continue
                if crystal.reference_count < REFERENCE_COUNT_THRESHOLD:
                    continue
                if crystal.verification_level not in VERIFICATION_ELIGIBLE:
                    continue
                eligible.append(crystal)
        except Exception as e:
            logger.warning(f"Crystal Actuator scan error: {e}")
        return eligible

    def _translate_to_rule(self, crystal: Any) -> Optional[Dict[str, Any]]:
        """將結晶翻譯為行為規則."""
        try:
            origin = crystal.origin or crystal.source_context or "conversation"
            # 推斷 origin 類型
            rule_type = RULE_TYPE_STYLE  # 預設
            for key, rtype in ORIGIN_TO_RULE_TYPE.items():
                if key in origin:
                    rule_type = rtype
                    break

            action = CRYSTAL_TYPE_ACTION.get(crystal.crystal_type, "note")

            # 從結晶內容生成行為指令
            directive = ""
            if crystal.g4_insights:
                directive = crystal.g4_insights[0]
            elif crystal.g3_root_inquiry:
                directive = f"注意：{crystal.g3_root_inquiry}"

            now = datetime.now(TZ8)
            expires = now + timedelta(days=RULE_TTL_DAYS)

            return {
                "rule_id": f"rule-{crystal.cuid}-{now.strftime('%m%d')}",
                "source_cuid": crystal.cuid,
                "rule_type": rule_type,
                "action": action,
                "summary": crystal.g1_summary,
                "directive": directive,
                "strength": 1.0,
                "status": "active",
                "created_at": now.isoformat(),
                "expires_at": expires.isoformat(),
                "positive_count": 0,
                "negative_count": 0,
                "last_feedback": "",
                "crystal_ri": crystal.ri_score,
                "crystal_type": crystal.crystal_type,
                "crystal_origin": origin,
            }
        except Exception as e:
            logger.warning(f"Crystal Actuator translate error: {e}")
            return None

    def _already_has_rule(self, cuid: str) -> bool:
        """檢查是否已有來自此結晶的活躍規則."""
        return any(
            r.get("source_cuid") == cuid and r.get("status") == "active"
            for r in self._rules
        )

    def _expire_stale_rules(self) -> int:
        """淘汰過期規則."""
        now = datetime.now(TZ8).isoformat()
        before = len(self._rules)
        self._rules = [
            r for r in self._rules
            if r.get("expires_at", "9999") > now
        ]
        expired = before - len(self._rules)
        return expired

    def _load_rules(self) -> None:
        """從檔案載入規則."""
        if self._rules_file.exists():
            try:
                data = json.loads(self._rules_file.read_text(encoding="utf-8"))
                self._rules = data.get("rules", [])
            except Exception as e:
                logger.warning(f"Crystal Actuator load error: {e}")
                self._rules = []
        else:
            self._rules = []

    def _save_rules(self) -> None:
        """存儲規則到檔案."""
        try:
            data = {
                "version": "1.0",
                "updated_at": datetime.now(TZ8).isoformat(),
                "rules": self._rules,
            }
            self._rules_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Crystal Actuator save error: {e}")
