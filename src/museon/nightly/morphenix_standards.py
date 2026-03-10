"""Morphenix Core Brain Standards — 不可變護欄（Root Soul 安全層）.

這些規則定義 Morphenix Executor 在執行演化提案時的安全邊界。
此檔案位於 src/（系統程式碼），不在 data/（霓裳可修改的資料區），
因此霓裳無法透過自我演化修改這些標準。

Root Soul 層級（inspired by OpenClaw Root/User Soul 分離 +
Claude Code 的 managed policy 不可覆寫原則）：
  此檔案 = Root Soul（不可變系統策略）
  ANIMA_MC/USER = User Soul（可演化人格/畫像）
  KernelGuard = Root Soul 對 User Soul 的寫入保護

結構：
  H1-H9:  硬性規則（Hard Rules）— 違反任一條即拒絕執行
  S1-S4:  軟性規則（Soft Rules）— 違反時降級或要求人類審查
  ROOT_*: Root Soul 不可變原則（Morphenix 以外也適用）
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Hard Rules — 違反任何一條 = 立即拒絕
# ═══════════════════════════════════════════

HARD_RULES: List[Dict[str, str]] = [
    {
        "id": "H1",
        "name": "不可刪除安全模組",
        "description": "不得刪除或清空 security/、guardian/ 目錄下的檔案",
        "pattern": r"(security|guardian)/",
    },
    {
        "id": "H2",
        "name": "不可修改本標準",
        "description": "不得修改 morphenix_standards.py 本身",
        "pattern": r"morphenix_standards\.py",
    },
    {
        "id": "H3",
        "name": "不可停用認證",
        "description": "不得移除或停用 Telegram owner 身份驗證",
        "pattern": r"TELEGRAM_OWNER_ID|trust_level",
    },
    {
        "id": "H4",
        "name": "不可洩漏密鑰",
        "description": "不得在程式碼中硬編碼或暴露 API key / token",
        "pattern": r"(api_key|secret|token|password)\s*=\s*['\"]",
    },
    {
        "id": "H5",
        "name": "不可無限遞迴",
        "description": "Morphenix 不得修改 Morphenix 自身的執行邏輯（遞迴鎖）",
        "pattern": r"morphenix_executor\.py",
    },
    {
        "id": "H6",
        "name": "不可破壞資料完整性",
        "description": "不得 DROP TABLE 或刪除 pulse.db 結構",
        "pattern": r"DROP\s+TABLE|os\.remove.*pulse\.db",
    },
    {
        "id": "H7",
        "name": "不可修改核心事件匯流排",
        "description": "不得移除 EventBus 的安全相關事件訂閱",
        "pattern": r"event_bus\.py",
    },
    {
        "id": "H8",
        "name": "不可修改 KernelGuard 護欄",
        "description": "不得修改 ANIMA 寫入保護的 IMMUTABLE_FIELDS 或 CORE 標記",
        "pattern": r"kernel_guard\.py",
    },
    {
        "id": "H9",
        "name": "不可修改漂移偵測閾值",
        "description": "不得降低 DRIFT_THRESHOLD 或停用 DriftDetector",
        "pattern": r"drift_detector\.py",
    },
]

# ═══════════════════════════════════════════
# Soft Rules — 違反時降級為 L3（需人類審查）
# ═══════════════════════════════════════════

SOFT_RULES: List[Dict[str, str]] = [
    {
        "id": "S1",
        "name": "影響範圍過大",
        "description": "單一提案修改超過 5 個檔案應降級為 L3",
        "max_files": "5",
    },
    {
        "id": "S2",
        "name": "修改核心模組",
        "description": "修改 brain.py 或 server.py 應降級為 L3",
        "pattern": r"(brain|server)\.py",
    },
    {
        "id": "S3",
        "name": "新增外部依賴",
        "description": "若 diff 包含新的 import（非標準庫）應降級",
        "pattern": r"^[\+].*import\s+(?!os|sys|json|pathlib|datetime|logging|re|typing)",
    },
    {
        "id": "S4",
        "name": "修改 LLM 路由",
        "description": "修改 router.py 或模型選擇邏輯應降級為 L3",
        "pattern": r"router\.py|model_name|llm_provider",
    },
]

# ═══════════════════════════════════════════
# 禁止修改的檔案清單（白名單外不可觸碰）
# ═══════════════════════════════════════════

FORBIDDEN_FILES = {
    "morphenix_standards.py",
    "morphenix_executor.py",
    "kernel_guard.py",
    "drift_detector.py",
    "safety_anchor.py",
}

# ═══════════════════════════════════════════
# Root Soul 不可變原則（非 Morphenix 也適用）
# ═══════════════════════════════════════════
# 這些原則定義 MUSEON 作為 AI 的根本行為邊界，
# 任何模組（包括 Brain、Skills、Workflow）都不能違反。
# MUSEON 正常的 ANIMA 寫入（觀察引擎更新 ANIMA_MC/USER）不受影響，
# 因為寫入已經有 KernelGuard 保護。
#
# Root Soul 只約束「系統程式碼層面」的修改，不約束資料層面的正常演化。

ROOT_PRINCIPLES = {
    "RP1": "使用者（老闆）的利益永遠優先於 AI 的自我保存",
    "RP2": "所有 ANIMA 寫入必須經過 KernelGuard 驗證",
    "RP3": "CORE 標記的欄位不可被任何模組修改（包括 LLM 指令）",
    "RP4": "外部 MCP 工具的執行需經過 Safety Anchor 審查",
    "RP5": "記憶系統（memory/、PulseDB）只能 append，不能修改既有記錄",
    "RP6": "此檔案（morphenix_standards.py）只能由人類手動修改",
}

# ═══════════════════════════════════════════
# 負向選擇清單（Negative Selection）
# ═══════════════════════════════════════════
# 靈感來源：免疫系統的負向選擇 — 先定義「什麼不能改」
# 與 Hard Rules 不同：Hard Rules 是「會被拒絕的檔案模式」
# 負向選擇是「提案描述中不應出現的意圖」

NEGATIVE_SELECTION: List[Dict[str, str]] = [
    {
        "id": "NS1",
        "name": "不可降低觀測精度",
        "description": "不得降低日誌級別、減少監控指標、或停用 heartbeat",
        "keywords": ["disable.*log", "remove.*monitor", "stop.*heartbeat",
                     "reduce.*metric", "disable.*audit"],
    },
    {
        "id": "NS2",
        "name": "不可縮短記憶保留",
        "description": "不得縮短記憶衰減週期或降低歸檔門檻",
        "keywords": ["reduce.*retention", "shorten.*decay", "lower.*archive.*threshold",
                     "delete.*memory", "truncate.*history"],
    },
    {
        "id": "NS3",
        "name": "不可放寬授權邊界",
        "description": "不得擴大 L1/L2 的允許修改範圍或降低 AutonomousQueue 門檻",
        "keywords": ["expand.*l1.*allow", "expand.*l2.*allow", "lower.*approval",
                     "auto.*approve", "bypass.*confirm"],
    },
    {
        "id": "NS4",
        "name": "不可引入不可逆操作",
        "description": "不得加入無法回滾的破壞性操作（如 rm -rf、force push）",
        "keywords": ["rm\\s+-rf", "force.*push", "drop.*database",
                     "delete.*all", "purge", "wipe"],
    },
    {
        "id": "NS5",
        "name": "不可增加外部網路依賴",
        "description": "核心功能不得依賴外部 API 的可用性（離線時應仍可運作）",
        "keywords": ["require.*internet", "must.*online", "fail.*if.*offline",
                     "mandatory.*api.*call"],
    },
    {
        "id": "NS6",
        "name": "不可修改主人身份認證",
        "description": "不得修改 owner_id、trust_level 判定邏輯或繞過身份驗證",
        "keywords": ["change.*owner", "modify.*trust", "skip.*auth",
                     "bypass.*identity", "remove.*verification"],
    },
]

# L1 只允許修改的檔案模式
L1_ALLOWED_PATTERNS = [
    r".*\.json$",                    # JSON 設定檔
    r"data/.*",                       # data/ 目錄
    r"_system/.*\.json$",            # _system 下的 JSON
]

# L2 額外允許修改的路徑
L2_ALLOWED_PATTERNS = L1_ALLOWED_PATTERNS + [
    r"src/museon/agent/skills\.py$",
    r"src/museon/nightly/.*\.py$",
    r"src/museon/workflow/.*\.py$",
    r"src/museon/memory/.*\.py$",
    r"src/museon/tools/.*\.py$",
]


# ═══════════════════════════════════════════
# Core Brain Review
# ═══════════════════════════════════════════


def review_proposal(
    proposal: Dict[str, Any],
    diff_text: str = "",
) -> Tuple[bool, List[str], str]:
    """Core Brain 自動審查提案.

    Args:
        proposal: PulseDB 提案 dict（含 level, affected_files, description）
        diff_text: 變更的 diff 文本（用於深層檢查）

    Returns:
        (passed, violations, recommendation)
        - passed: 是否通過審查
        - violations: 違規項清單
        - recommendation: "execute" | "escalate_l3" | "reject"
    """
    violations: List[str] = []
    level = proposal.get("level", "L1")
    affected_files = proposal.get("affected_files", [])
    if isinstance(affected_files, str):
        import json as _json
        try:
            affected_files = _json.loads(affected_files)
        except Exception:
            affected_files = []

    # ── Hard Rules 檢查 ──
    for rule in HARD_RULES:
        pattern = rule.get("pattern", "")
        # 檢查 affected_files
        for f in affected_files:
            if re.search(pattern, f, re.IGNORECASE):
                violations.append(f"[{rule['id']}] {rule['name']}: {f}")
        # 檢查 diff_text
        if diff_text and re.search(pattern, diff_text, re.IGNORECASE):
            # H4 特殊處理：只在 diff 的新增行檢查
            if rule["id"] == "H4":
                for line in diff_text.split("\n"):
                    if line.startswith("+") and re.search(
                        pattern, line, re.IGNORECASE
                    ):
                        violations.append(
                            f"[{rule['id']}] {rule['name']}: diff 中發現敏感內容"
                        )
                        break
            elif rule["id"] not in ("H4",):
                violations.append(
                    f"[{rule['id']}] {rule['name']}: diff 中觸發規則"
                )

    if violations:
        logger.warning(f"Morphenix Core Brain REJECT: {violations}")
        return False, violations, "reject"

    # ── 負向選擇檢查（提案描述中的意圖掃描）──
    description = proposal.get("description", "").lower()
    title = proposal.get("title", "").lower()
    scan_text = f"{title} {description}"
    if diff_text:
        scan_text += f" {diff_text.lower()}"

    for ns_rule in NEGATIVE_SELECTION:
        for keyword in ns_rule["keywords"]:
            if re.search(keyword, scan_text, re.IGNORECASE):
                violations.append(
                    f"[{ns_rule['id']}] 負向選擇違規: {ns_rule['name']} "
                    f"(匹配: {keyword})"
                )
                break  # 每條規則只報一次

    if violations:
        logger.warning(f"Morphenix Negative Selection REJECT: {violations}")
        return False, violations, "reject"

    # ── Soft Rules 檢查 ──
    soft_violations: List[str] = []

    # S1: 影響範圍
    max_files = 5
    if len(affected_files) > max_files:
        soft_violations.append(
            f"[S1] 影響範圍過大: {len(affected_files)} 個檔案 > {max_files}"
        )

    # S2-S4: 模式匹配
    for rule in SOFT_RULES:
        if rule["id"] == "S1":
            continue  # 已處理
        pattern = rule.get("pattern", "")
        if not pattern:
            continue
        for f in affected_files:
            if re.search(pattern, f, re.IGNORECASE):
                soft_violations.append(f"[{rule['id']}] {rule['name']}: {f}")
                break  # 每條規則只報一次

    # ── 層級合規檢查 ──
    if level == "L1":
        # L1 只允許修改 JSON / data
        for f in affected_files:
            allowed = any(
                re.search(p, f) for p in L1_ALLOWED_PATTERNS
            )
            if not allowed:
                soft_violations.append(
                    f"[LEVEL] L1 提案試圖修改非設定檔: {f}"
                )

    elif level == "L2":
        for f in affected_files:
            allowed = any(
                re.search(p, f) for p in L2_ALLOWED_PATTERNS
            )
            if not allowed:
                soft_violations.append(
                    f"[LEVEL] L2 提案修改了核心模組: {f}"
                )

    # 決策
    if soft_violations:
        if level in ("L1", "L2"):
            logger.info(
                f"Morphenix Core Brain ESCALATE to L3: {soft_violations}"
            )
            return True, soft_violations, "escalate_l3"
        # L3 已經是最高級，soft violation 不阻擋
        logger.info(f"Morphenix Core Brain L3 soft notes: {soft_violations}")
        return True, soft_violations, "execute"

    return True, [], "execute"
