"""Kernel Guard — ANIMA 寫入保護護欄.

保護 ANIMA 中不可變欄位（identity, core_values, birth 等），
並對敏感欄位變動（>15%）觸發審批流程。
所有寫入動作均記錄 append-only 審計日誌。

CORE/MUTABLE 分類（inspired by EvoClaw + Claude Code CLAUDE.md 層級）：
  CORE  — 不可變，定義 AI 的根本身份，任何修改直接 DENY
  GUARD — 可寫但受漂移監控，超過閾值觸發警告
  RING  — append-only，只能新增不能修改/刪除
  MUTABLE — 自由寫入，MUSECLAW 觀察引擎正常更新
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
# CORE / GUARD / RING / MUTABLE 欄位分類
# ═══════════════════════════════════════════
# 設計哲學：
#   CORE   = Root Soul（不可變身份錨點）
#   GUARD  = 受監控的演化欄位（允許寫但追蹤漂移）
#   RING   = Append-only 歷史紀錄（只能新增）
#   MUTABLE = 自由更新（觀察引擎正常運作）
#
# 未列出的欄位預設為 MUTABLE

# ──── CORE：不可變（DENY any modification）────
IMMUTABLE_FIELDS: Dict[str, List[str]] = {
    "ANIMA_MC": [
        "identity.name",                     # 命名後不可改
        "identity.birth_date",               # 誕生日固定
        "ceremony.completed_at",             # 歷史紀錄
        "ceremony.started_at",               # 歷史紀錄
        "personality.core_traits",           # 核心性格（DNA27 定義）
    ],
    "ANIMA_USER": [
        "relationship.first_interaction",    # 歷史記錄
        "profile.name",                      # 使用者名稱（由使用者自己改）
    ],
}

# ──── GUARD：漂移監控（允許寫入但追蹤偏移量）────
DRIFT_MONITORED_FIELDS: Dict[str, List[str]] = {
    "ANIMA_MC": [
        "eight_primals",                     # 八原語 level 變化
        "personality.communication_style",   # 溝通風格
    ],
    "ANIMA_USER": [
        "eight_primals",                     # 使用者八原語
        "seven_layers.L6_communication_style",  # 溝通風格
    ],
}

# ──── RING：Append-only（只能新增，不可修改/刪除既有）────
APPEND_ONLY_FIELDS: Dict[str, List[str]] = {
    "ANIMA_MC": [
        "evolution.stage_history",           # 演化歷史
    ],
    "ANIMA_USER": [
        "relationship.milestones",           # 里程碑
        "seven_layers.L4_interaction_rings", # 互動年輪
    ],
}

# ──── SIZE LIMITS：自動成長欄位的容量上限 ────
# 超過上限時，觀察引擎應自動淘汰最舊/最低 confidence 的項目
FIELD_SIZE_LIMITS: Dict[str, Dict[str, int]] = {
    "ANIMA_USER": {
        "seven_layers.L1_facts": 30,              # 最多 30 筆事實
        "seven_layers.L2_personality": 5,          # Big Five 固定 5 維
        "seven_layers.L3_decision_pattern": 50,    # 最多 50 筆（skill_cluster 需保留）
        "seven_layers.L5_preference_crystals": 10, # 最多 10 筆偏好結晶
        "seven_layers.L7_context_roles": 5,        # 最多 5 筆角色
    },
    "ANIMA_MC": {
        "capabilities.loaded_skills": 100,         # 技能上限
    },
}


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
    """計算字典型資料的整體漂移分數 (0~1).

    支援三種值型態：
    - dict（八原語結構，有 level）: 比較 level 數值漂移
    - int/float: 比較數值漂移
    - str: 值不同 → 漂移 1.0，相同 → 0.0
    - None: 跳過（不計入分母）
    """
    if not old_dict or not new_dict:
        return 0.0

    total_drift = 0.0
    count = 0

    all_keys = set(list(old_dict.keys()) + list(new_dict.keys()))
    for key in all_keys:
        old_v = old_dict.get(key)
        new_v = new_dict.get(key)

        # 跳過隱藏欄位（以 _ 開頭的內部用途）
        if key.startswith("_"):
            continue

        # 任一側為 None → 跳過
        if old_v is None or new_v is None:
            continue

        # 八原語結構：每個都有 level
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
            # 字串比較：不同 = 1.0 漂移，相同 = 0
            total_drift += (1.0 if old_v != new_v else 0.0)
            count += 1

    return total_drift / max(count, 1)


# ═══════════════════════════════════════════
# KernelGuard 主類
# ═══════════════════════════════════════════

class KernelGuard:
    """ANIMA 寫入保護護欄.

    職責：
    1. 保護不可變欄位不被修改
    2. 監控敏感欄位的漂移（>15% 觸發警報）
    3. 確保 append-only 欄位只能新增
    4. 所有決策記錄到 append-only 審計日誌
    """

    DRIFT_THRESHOLD = 0.15  # 15%

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.audit_log_path = data_dir / "guardian" / "kernel_audit.jsonl"
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

        # 漂移累計追蹤
        self._drift_accumulator: Dict[str, float] = {}

        logger.info("KernelGuard 初始化完成")

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
            (decision, violations) — decision 為最終裁決，
            violations 為所有違規/警告訊息列表
        """
        violations: List[str] = []
        warnings: List[str] = []
        needs_approval = False

        if old_data is None:
            # 首次建立，允許
            self._log_audit("create", target, "", None, None,
                            WriteDecision.ALLOW.value, "首次建立 ANIMA")
            return WriteDecision.ALLOW, []

        # 1. 檢查不可變欄位
        for field_path in IMMUTABLE_FIELDS.get(target, []):
            old_val = _get_nested(old_data, field_path)
            new_val = _get_nested(new_data, field_path)

            if old_val is not None and new_val != old_val:
                msg = f"[DENY] 不可變欄位被修改: {field_path} ({old_val} -> {new_val})"
                violations.append(msg)
                self._log_audit("modify", target, field_path,
                                old_val, new_val, "DENY", "immutable field")

        if violations:
            # 有不可變欄位被修改 → 直接 DENY
            return WriteDecision.DENY, violations

        # 2. 檢查 append-only 欄位
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
                    # 檢查舊資料的最後幾筆是否被修改
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
                            break  # 只報告第一個

        if violations:
            return WriteDecision.DENY, violations

        # 3. 檢查漂移監控欄位
        for field_path in DRIFT_MONITORED_FIELDS.get(target, []):
            old_val = _get_nested(old_data, field_path)
            new_val = _get_nested(new_data, field_path)

            if old_val is None or new_val is None:
                continue

            drift = 0.0
            if isinstance(old_val, dict) and isinstance(new_val, dict):
                drift = _compute_dict_drift(old_val, new_val)
            elif isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                d = _compute_numeric_drift(old_val, new_val)
                drift = d if d is not None else 0.0

            if drift > self.DRIFT_THRESHOLD:
                msg = (f"[WARN] 漂移超過閾值: {field_path} "
                       f"drift={drift:.1%} > {self.DRIFT_THRESHOLD:.0%}")
                warnings.append(msg)
                needs_approval = True
                self._log_audit("drift", target, field_path,
                                str(old_val)[:100], str(new_val)[:100],
                                "NEEDS_APPROVAL",
                                f"drift={drift:.1%}")

            # 累計漂移追蹤
            drift_key = f"{target}.{field_path}"
            self._drift_accumulator[drift_key] = \
                self._drift_accumulator.get(drift_key, 0.0) + drift

        if needs_approval:
            # 漂移超過閾值 → 目前仍允許寫入但記錄警告
            # 未來可改為真正的審批流程
            self._log_audit("write_with_drift_warning", target, "",
                            None, None, "ALLOW_WITH_WARNING",
                            "; ".join(warnings))
            return WriteDecision.ALLOW, warnings

        # 4. 自動修剪超過 SIZE LIMIT 的列表欄位
        pruned = self._auto_prune(target, new_data)
        if pruned:
            warnings.extend(pruned)

        # 5. 正常寫入
        return WriteDecision.ALLOW, warnings

    # ─── 自動修剪 ─────────────────────────

    def _auto_prune(
        self, target: str, data: Dict[str, Any]
    ) -> List[str]:
        """自動修剪超過 FIELD_SIZE_LIMITS 的列表欄位.

        修剪策略：
        - 保留最新的（按 date/last_seen/last_updated 排序）
        - 如果有 confidence，優先淘汰低 confidence 的
        """
        messages: List[str] = []
        limits = FIELD_SIZE_LIMITS.get(target, {})

        for field_path, max_size in limits.items():
            val = _get_nested(data, field_path)
            if not isinstance(val, list) or len(val) <= max_size:
                continue

            original_len = len(val)

            # 按 confidence（升序）+ 時間（升序）排序，淘汰頭部
            def _sort_key(item):
                if isinstance(item, dict):
                    conf = item.get("confidence", 0.5)
                    ts = (item.get("date") or item.get("last_seen")
                          or item.get("last_updated") or "")
                    return (conf, ts)
                return (0.5, "")

            sorted_items = sorted(val, key=_sort_key)
            # 保留最後 max_size 筆（= 最高 confidence + 最新）
            kept = sorted_items[-max_size:]
            # 恢復原始順序（按時間）
            if kept and isinstance(kept[0], dict):
                kept.sort(key=lambda x: (
                    x.get("date") or x.get("last_seen")
                    or x.get("last_updated") or ""
                ))

            # 就地修改
            _set_nested(data, field_path, kept)

            pruned_count = original_len - max_size
            msg = (f"[PRUNE] {field_path}: {original_len} → {max_size} "
                   f"(淘汰 {pruned_count} 筆低 confidence/舊項)")
            messages.append(msg)
            self._log_audit("prune", target, field_path,
                            original_len, max_size,
                            "ALLOW", msg)

        return messages

    # ─── 漂移查詢 ─────────────────────────

    def get_accumulated_drift(self, target: str, field_path: str) -> float:
        """取得某欄位的累計漂移值."""
        return self._drift_accumulator.get(f"{target}.{field_path}", 0.0)

    def reset_drift_baseline(self, target: str, field_path: str) -> None:
        """重置漂移基線（在 drift detector 建立新基線後呼叫）."""
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
            except (ValueError, KeyError):
                pass
        return count
