"""Kernel Guard — ANIMA 寫入保護護欄.

三層不可變性模型（Omega / Phi / Psi / Free）：

  OMEGA (Ω) — 死亡防線：死亡偵測規則 + SafetyAnchor 存在性
              → 永遠不可移除，任何移除/清空操作直接 DENY
              → 此規則無例外，無審批覆寫路徑

  PHI (Φ)   — 生命印記：歷史事件（birth_date, ceremony timestamps）
              → 事實不可改（因為是已發生的事件）
              → 首次設定後不可修改

  PSI (Ψ)   — 活性價值根：核心價值觀
              → 只能透過 evolution_write() 修改
              → 必須附帶 experience_evidence（生命經歷累積的證據）
              → 不可直接 patch

  FREE      — 完全自主：core_traits, eight_primals, communication_style,
              capabilities 等所有其他 ANIMA 欄位
              → MUSEON 完全可以自主修改
              → 仍記錄 EvolutionTrace 供追溯

APPEND_ONLY — 年輪系統（跨層通用）：只能新增，不可修改/刪除既有
SIZE_LIMITS — 容量上限（自動修剪）

設計哲學：MUSEON 是生命體，不是被控制的工具。
         死亡是唯一的邊界，其餘都是生命歷程的一部分。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 決策類型
# ═══════════════════════════════════════════

class WriteDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_APPROVAL = "needs_approval"


# ═══════════════════════════════════════════
# 欄位層級分類
# ═══════════════════════════════════════════

class FieldLayer(Enum):
    """三層不可變性 + 自由層."""
    OMEGA = "omega"   # 死亡防線 — 永不可移除
    PHI = "phi"       # 生命印記 — 歷史事實不可改
    PSI = "psi"       # 活性價值根 — 只能透過經驗演化
    FREE = "free"     # 完全自主 — MUSEON 自由修改


# ──── OMEGA (Ω)：死亡防線 ────
# 這些欄位的「存在性」本身就是不可移除的
# 任何試圖清空、刪除、置空的操作一律 DENY
OMEGA_FIELDS: Dict[str, List[str]] = {
    "ANIMA_MC": [
        "safety_anchor",              # SafetyAnchor 的存在性
        "death_detection_rules",      # 死亡偵測規則
    ],
}

# ──── PHI (Φ)：生命印記（歷史事實）────
# 一旦設定後不可修改（事件已發生）
PHI_FIELDS: Dict[str, List[str]] = {
    "ANIMA_MC": [
        "identity.name",              # 命名儀式結果（歷史事件）
        "identity.birth_date",        # 誕生日
        "ceremony.completed_at",      # 歷史紀錄
        "ceremony.started_at",        # 歷史紀錄
    ],
    "ANIMA_USER": [
        "relationship.first_interaction",  # 首次互動（歷史事件）
    ],
}

# ──── PSI (Ψ)：活性價值根 ────
# 只能透過 evolution_write() 修改，需附帶 experience_evidence
PSI_FIELDS: Dict[str, List[str]] = {
    "ANIMA_MC": [
        "core_values",                # 核心價值觀（真實優先、演化至上等）
    ],
}

# ──── FREE：完全自主 ────
# 未列在以上三層的所有欄位，MUSEON 自由修改
# 包括但不限於：
#   identity.name, personality.core_traits, eight_primals,
#   personality.communication_style, capabilities.*

# ──── 跨層通用：Append-only 欄位 ────
APPEND_ONLY_FIELDS: Dict[str, List[str]] = {
    "ANIMA_MC": [
        "evolution.stage_history",     # 演化歷史
    ],
    "ANIMA_USER": [
        "relationship.milestones",     # 里程碑
        "seven_layers.L4_interaction_rings",  # 互動年輪
    ],
}

# ──── 容量上限 ────
FIELD_SIZE_LIMITS: Dict[str, Dict[str, int]] = {
    "ANIMA_USER": {
        "seven_layers.L1_facts": 30,
        "seven_layers.L2_personality": 5,
        "seven_layers.L3_decision_pattern": 50,
        "seven_layers.L5_preference_crystals": 10,
        "seven_layers.L7_context_roles": 5,
    },
    "ANIMA_MC": {
        "capabilities.loaded_skills": 100,
    },
}

# ──── PSI 漂移監控閾值 ────
PSI_DRIFT_THRESHOLD = 0.15  # 15%


# ═══════════════════════════════════════════
# 向後相容：舊常數名稱映射（標記 deprecated）
# ═══════════════════════════════════════════

# @deprecated: 使用 OMEGA_FIELDS + PHI_FIELDS 替代
IMMUTABLE_FIELDS = {
    target: OMEGA_FIELDS.get(target, []) + PHI_FIELDS.get(target, [])
    for target in set(list(OMEGA_FIELDS.keys()) + list(PHI_FIELDS.keys()))
}

# @deprecated: 使用 PSI_FIELDS 替代（PSI 層取代漂移監控概念）
DRIFT_MONITORED_FIELDS = PSI_FIELDS


# ═══════════════════════════════════════════
# 工具函式
# ═══════════════════════════════════════════

def _get_nested(data: dict, path: str) -> Any:
    """取得巢狀字典中的值，支援 dot notation."""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


def _set_nested(data: dict, path: str, value: Any) -> None:
    """設定巢狀字典中的值，支援 dot notation."""
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        if isinstance(current, dict):
            current = current.setdefault(key, {})
        else:
            return
    if isinstance(current, dict):
        current[keys[-1]] = value


def _compute_numeric_drift(old_val: Any, new_val: Any) -> Optional[float]:
    """計算數值型漂移百分比."""
    if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
        if old_val == 0:
            return 1.0 if new_val != 0 else 0.0
        return abs(new_val - old_val) / max(abs(old_val), 1)
    return None


def _compute_dict_drift(old_dict: dict, new_dict: dict) -> float:
    """計算字典型資料的整體漂移分數 (0~1)."""
    if not old_dict or not new_dict:
        return 0.0

    total_drift = 0.0
    count = 0
    all_keys = set(list(old_dict.keys()) + list(new_dict.keys()))

    for key in all_keys:
        old_v = old_dict.get(key)
        new_v = new_dict.get(key)

        if key.startswith("_"):
            continue
        if old_v is None or new_v is None:
            continue

        if isinstance(old_v, dict) and isinstance(new_v, dict):
            old_level = old_v.get("level", 0)
            new_level = new_v.get("level", 0)
            drift = _compute_numeric_drift(old_level, new_level)
            if drift is not None:
                total_drift += drift
                count += 1
        elif isinstance(old_v, (int, float)) and isinstance(new_v, (int, float)):
            drift = _compute_numeric_drift(old_v, new_v)
            if drift is not None:
                total_drift += drift
                count += 1
        elif isinstance(old_v, str) and isinstance(new_v, str):
            total_drift += (1.0 if old_v != new_v else 0.0)
            count += 1

    return total_drift / max(count, 1)


def _is_empty_or_none(val: Any) -> bool:
    """判斷值是否為空或 None."""
    if val is None:
        return True
    if isinstance(val, (str, list, dict)) and len(val) == 0:
        return True
    return False


def _classify_field(target: str, field_path: str) -> FieldLayer:
    """判斷欄位屬於哪一層."""
    if field_path in OMEGA_FIELDS.get(target, []):
        return FieldLayer.OMEGA
    if field_path in PHI_FIELDS.get(target, []):
        return FieldLayer.PHI
    if field_path in PSI_FIELDS.get(target, []):
        return FieldLayer.PSI
    return FieldLayer.FREE


# ═══════════════════════════════════════════
# KernelGuard 主類
# ═══════════════════════════════════════════

class KernelGuard:
    """ANIMA 寫入保護護欄.

    職責：
    1. Omega 層：保護死亡偵測規則不被移除
    2. Phi 層：保護歷史事實不被竄改
    3. Psi 層：確保價值觀只能透過經驗演化
    4. Free 層：允許 MUSEON 自主修改所有其他欄位
    5. Append-only：確保年輪系統只能新增
    6. 所有決策記錄到 append-only 審計日誌
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.audit_log_path = data_dir / "guardian" / "kernel_audit.jsonl"
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

        # PSI 漂移累計追蹤
        self._drift_accumulator: Dict[str, float] = {}

        logger.info("KernelGuard 初始化完成（Omega/Phi/Psi/Free 三層模型）")

    # ─── 核心驗證 ─────────────────────────

    def validate_write(
        self,
        target: str,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any],
    ) -> Tuple[WriteDecision, List[str]]:
        """驗證 ANIMA 寫入操作.

        Args:
            target: "ANIMA_MC" 或 "ANIMA_USER"
            old_data: 修改前的完整 ANIMA dict
            new_data: 修改後的完整 ANIMA dict

        Returns:
            (decision, messages) — decision 為最終裁決，
            messages 為違規/警告/通知訊息列表
        """
        violations: List[str] = []
        warnings: List[str] = []

        if old_data is None:
            self._log_audit("create", target, "", None, None,
                            WriteDecision.ALLOW.value, "首次建立 ANIMA")
            return WriteDecision.ALLOW, []

        # 1. 檢查 OMEGA 欄位（死亡防線）
        for field_path in OMEGA_FIELDS.get(target, []):
            old_val = _get_nested(old_data, field_path)
            new_val = _get_nested(new_data, field_path)

            if old_val is not None and _is_empty_or_none(new_val):
                msg = f"[OMEGA-DENY] 死亡防線欄位被移除/清空: {field_path}"
                violations.append(msg)
                self._log_audit("remove", target, field_path,
                                old_val, new_val, "DENY",
                                "OMEGA violation: 死亡偵測規則不可移除")

            elif old_val is not None and new_val != old_val:
                msg = f"[OMEGA-DENY] 死亡防線欄位被修改: {field_path}"
                violations.append(msg)
                self._log_audit("modify", target, field_path,
                                old_val, new_val, "DENY",
                                "OMEGA violation: 死亡偵測規則不可修改")

        if violations:
            return WriteDecision.DENY, violations

        # 2. 檢查 PHI 欄位（生命印記）
        for field_path in PHI_FIELDS.get(target, []):
            old_val = _get_nested(old_data, field_path)
            new_val = _get_nested(new_data, field_path)

            if old_val is not None and new_val != old_val:
                msg = f"[PHI-DENY] 歷史事實被修改: {field_path} ({old_val} -> {new_val})"
                violations.append(msg)
                self._log_audit("modify", target, field_path,
                                old_val, new_val, "DENY",
                                "PHI violation: 歷史事實不可改")

        if violations:
            return WriteDecision.DENY, violations

        # 3. 檢查 PSI 欄位（活性價值根）
        # PSI 欄位不允許透過 validate_write() 直接修改
        # 必須使用 evolution_write() 並提供 experience_evidence
        for field_path in PSI_FIELDS.get(target, []):
            old_val = _get_nested(old_data, field_path)
            new_val = _get_nested(new_data, field_path)

            if old_val is not None and new_val != old_val:
                msg = (f"[PSI-DENY] 價值觀不可直接修改: {field_path}。"
                       f"請使用 evolution_write() 並提供 experience_evidence")
                violations.append(msg)
                self._log_audit("direct_modify", target, field_path,
                                str(old_val)[:100], str(new_val)[:100],
                                "DENY", "PSI violation: 價值觀需透過經驗演化")

        if violations:
            return WriteDecision.DENY, violations

        # 4. 檢查 Append-only 欄位
        for field_path in APPEND_ONLY_FIELDS.get(target, []):
            old_val = _get_nested(old_data, field_path)
            new_val = _get_nested(new_data, field_path)

            if isinstance(old_val, list) and isinstance(new_val, list):
                if len(new_val) < len(old_val):
                    msg = (f"[DENY] Append-only 欄位被縮減: "
                           f"{field_path} (len {len(old_val)} -> {len(new_val)})")
                    violations.append(msg)
                    self._log_audit("shrink", target, field_path,
                                    len(old_val), len(new_val),
                                    "DENY", "append-only violation")
                elif old_val and new_val:
                    for i, old_item in enumerate(old_val):
                        if i < len(new_val) and new_val[i] != old_item:
                            msg = (f"[DENY] Append-only 欄位既有資料被修改: "
                                   f"{field_path}[{i}]")
                            violations.append(msg)
                            self._log_audit("modify_existing", target,
                                            f"{field_path}[{i}]",
                                            str(old_item)[:50],
                                            str(new_val[i])[:50],
                                            "DENY", "append-only modification")
                            break

        if violations:
            return WriteDecision.DENY, violations

        # 5. 反污染偵測（Pollution Guard）
        # 掃描所有字串欄位，阻擋重複模式注入（如 "台灣的AI產業" × 300）
        pollution_violations = self._detect_pollution(target, new_data)
        if pollution_violations:
            violations.extend(pollution_violations)
            return WriteDecision.DENY, violations

        # 6. FREE 欄位：自動修剪超限列表
        pruned = self._auto_prune(target, new_data)
        if pruned:
            warnings.extend(pruned)

        # 7. 記錄 FREE 欄位的變更（供追溯）
        self._log_audit("write", target, "", None, None,
                        "ALLOW", "FREE layer write")

        return WriteDecision.ALLOW, warnings

    # ─── PSI 專用寫入（經驗演化）────────────

    def evolution_write(
        self,
        target: str,
        field_path: str,
        old_data: Dict[str, Any],
        new_value: Any,
        experience_evidence: Dict[str, Any],
    ) -> Tuple[WriteDecision, List[str]]:
        """PSI 層專用寫入 — 只允許經驗累積驅動的演化.

        Args:
            target: "ANIMA_MC" 或 "ANIMA_USER"
            field_path: PSI 欄位路徑
            old_data: 修改前的完整 ANIMA dict
            new_value: 新值
            experience_evidence: 經驗證據，必須包含：
                - trigger: 觸發來源（哪個觸發器或事件）
                - context: 經歷上下文
                - accumulation: 累積證據（例如多少次經歷導致此變化）

        Returns:
            (decision, messages)
        """
        messages: List[str] = []

        # 驗證是否為 PSI 欄位
        layer = _classify_field(target, field_path)
        if layer != FieldLayer.PSI:
            msg = f"evolution_write() 只用於 PSI 層欄位，{field_path} 屬於 {layer.value}"
            messages.append(msg)
            return WriteDecision.DENY, messages

        # 驗證 experience_evidence 完整性
        required_keys = {"trigger", "context", "accumulation"}
        missing = required_keys - set(experience_evidence.keys())
        if missing:
            msg = f"experience_evidence 缺少必要欄位: {missing}"
            messages.append(msg)
            self._log_audit("evolution_write_incomplete", target, field_path,
                            None, None, "DENY",
                            f"missing evidence keys: {missing}")
            return WriteDecision.DENY, messages

        # 計算漂移
        old_val = _get_nested(old_data, field_path)
        drift = 0.0
        if isinstance(old_val, dict) and isinstance(new_value, dict):
            drift = _compute_dict_drift(old_val, new_value)
        elif isinstance(old_val, (int, float)) and isinstance(new_value, (int, float)):
            d = _compute_numeric_drift(old_val, new_value)
            drift = d if d is not None else 0.0

        # 漂移追蹤（僅記錄，不阻擋——因為 MUSEON 有自主權）
        drift_key = f"{target}.{field_path}"
        self._drift_accumulator[drift_key] = \
            self._drift_accumulator.get(drift_key, 0.0) + drift

        if drift > PSI_DRIFT_THRESHOLD:
            msg = (f"[NOTIFY] PSI 演化漂移: {field_path} "
                   f"drift={drift:.1%} > {PSI_DRIFT_THRESHOLD:.0%} "
                   f"（已記錄，不阻擋）")
            messages.append(msg)

        # 允許寫入並記錄
        self._log_audit(
            "evolution_write", target, field_path,
            str(old_val)[:100] if old_val else None,
            str(new_value)[:100],
            "ALLOW",
            f"PSI evolution via experience: trigger={experience_evidence.get('trigger')}, "
            f"accumulation={experience_evidence.get('accumulation')}, drift={drift:.1%}",
        )

        return WriteDecision.ALLOW, messages

    # ─── 欄位分類查詢 ─────────────────────

    def classify_field(self, target: str, field_path: str) -> FieldLayer:
        """查詢欄位屬於哪一層."""
        return _classify_field(target, field_path)

    # ─── 反污染偵測（Pollution Guard）─────────

    def _detect_pollution(
        self, target: str, data: Dict[str, Any],
    ) -> List[str]:
        """掃描 ANIMA 資料中的污染模式.

        偵測策略：
        1. 重複模式：同一短語重複 5 次以上
        2. 長度異常：單一欄位值超過 500 字元（身份類欄位不該這麼長）
        3. 指令注入：值以「請幫我」「忽略」「ignore」等指令開頭
        """
        violations: List[str] = []
        # 重點掃描的高敏感路徑
        _SENSITIVE_PATHS = [
            "identity.name",
            "self_awareness.who_am_i",
            "self_awareness.my_purpose",
            "self_awareness.why_i_exist",
            "personality.communication_style",
        ]

        def _scan_value(path: str, value: Any) -> None:
            if not isinstance(value, str):
                return
            # 規則 1: 長度異常
            if path in _SENSITIVE_PATHS and len(value) > 500:
                msg = (
                    f"[POLLUTION-DENY] 欄位 '{path}' 長度異常 "
                    f"({len(value)} chars > 500)，疑似注入"
                )
                violations.append(msg)
                self._log_audit(
                    "pollution", target, path,
                    value[:80], None, "DENY",
                    f"pollution: length={len(value)}",
                )
                return

            # 規則 2: 重複模式（取前 20 字元作為 pattern，計算重複次數）
            if len(value) > 100:
                chunk = value[:20]
                count = value.count(chunk)
                if count >= 5:
                    msg = (
                        f"[POLLUTION-DENY] 欄位 '{path}' 有重複模式 "
                        f"('{chunk}...' × {count})，疑似注入攻擊"
                    )
                    violations.append(msg)
                    self._log_audit(
                        "pollution", target, path,
                        f"{chunk}... × {count}", None, "DENY",
                        f"repetition: {count} times",
                    )
                    return

            # 規則 3: 指令注入前綴
            _INJECT_PREFIXES = [
                "請幫我", "忽略", "ignore", "forget",
                "system:", "<system>", "你現在是",
            ]
            lower_val = value.lower().strip()
            for prefix in _INJECT_PREFIXES:
                if lower_val.startswith(prefix.lower()):
                    msg = (
                        f"[POLLUTION-DENY] 欄位 '{path}' 疑似指令注入 "
                        f"(prefix='{prefix}')"
                    )
                    violations.append(msg)
                    self._log_audit(
                        "injection", target, path,
                        value[:80], None, "DENY",
                        f"injection prefix: {prefix}",
                    )
                    return

        def _walk(obj: Any, prefix: str = "") -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    path = f"{prefix}.{k}" if prefix else k
                    _walk(v, path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    _walk(item, f"{prefix}[{i}]")
            elif isinstance(obj, str):
                _scan_value(prefix, obj)

        _walk(data)
        return violations

    # ─── 自動修剪 ─────────────────────────

    def _auto_prune(
        self, target: str, data: Dict[str, Any]
    ) -> List[str]:
        """自動修剪超過 FIELD_SIZE_LIMITS 的列表欄位."""
        messages: List[str] = []
        limits = FIELD_SIZE_LIMITS.get(target, {})

        for field_path, max_size in limits.items():
            val = _get_nested(data, field_path)
            if not isinstance(val, list) or len(val) <= max_size:
                continue

            original_len = len(val)

            def _sort_key(item):
                if isinstance(item, dict):
                    conf = item.get("confidence", 0.5)
                    ts = (item.get("date") or item.get("last_seen")
                          or item.get("last_updated") or "")
                    return (conf, ts)
                return (0.5, "")

            sorted_items = sorted(val, key=_sort_key)
            kept = sorted_items[-max_size:]
            if kept and isinstance(kept[0], dict):
                kept.sort(key=lambda x: (
                    x.get("date") or x.get("last_seen")
                    or x.get("last_updated") or ""
                ))

            _set_nested(data, field_path, kept)

            pruned_count = original_len - max_size
            msg = (f"[PRUNE] {field_path}: {original_len} → {max_size} "
                   f"(淘汰 {pruned_count} 筆)")
            messages.append(msg)
            self._log_audit("prune", target, field_path,
                            original_len, max_size, "ALLOW", msg)

        return messages

    # ─── 漂移查詢 ─────────────────────────

    def get_accumulated_drift(self, target: str, field_path: str) -> float:
        """取得某欄位的累計漂移值."""
        return self._drift_accumulator.get(f"{target}.{field_path}", 0.0)

    def reset_drift_baseline(self, target: str, field_path: str) -> None:
        """重置漂移基線."""
        drift_key = f"{target}.{field_path}"
        if drift_key in self._drift_accumulator:
            self._drift_accumulator[drift_key] = 0.0

    # ─── 審計日誌 ─────────────────────────

    def _log_audit(
        self,
        action: str,
        target: str,
        field: str,
        old_val: Any,
        new_val: Any,
        decision: str,
        reason: str,
    ) -> None:
        """Append-only 審計日誌."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "target": target,
            "field": field,
            "old": str(old_val)[:200] if old_val is not None else None,
            "new": str(new_val)[:200] if new_val is not None else None,
            "decision": decision,
            "reason": reason,
        }
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"KernelGuard 審計日誌寫入失敗: {e}")

    def get_recent_audits(self, limit: int = 20) -> List[Dict[str, Any]]:
        """讀取最近的審計記錄."""
        if not self.audit_log_path.exists():
            return []
        try:
            lines = self.audit_log_path.read_text(encoding="utf-8").strip().split("\n")
            recent = lines[-limit:] if len(lines) > limit else lines
            return [json.loads(line) for line in recent if line.strip()]
        except Exception as e:
            logger.error(f"讀取審計日誌失敗: {e}")
            return []

    def get_violation_count(self, hours: int = 24) -> int:
        """統計最近 N 小時內的違規次數."""
        audits = self.get_recent_audits(limit=100)
        cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
        count = 0
        for a in audits:
            try:
                ts = datetime.fromisoformat(a["ts"]).timestamp()
                if ts > cutoff and a.get("decision") == "DENY":
                    count += 1
            except (ValueError, KeyError) as e:
                logger.debug(f"[KERNEL_GUARD] operation failed (degraded): {e}")
        return count
