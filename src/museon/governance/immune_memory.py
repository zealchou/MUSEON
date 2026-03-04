"""ImmuneMemory — 免疫記憶學習系統.

模擬生物免疫系統的「後天免疫」機制：
  - 第一次遇到異常 → 記錄（但不產生規則）
  - 第二次遇到相同異常 → 生成防禦規則（confidence=0.5）
  - 規則成功攔截 → confidence 增強
  - 規則誤報 → confidence 降低
  - confidence < 0.2 的弱規則 → 定期清除

與現有 immunity.py 的關係：
  - ImmunityEngine：處理已知、預定義的症狀（先天免疫）
  - ImmuneMemoryBank：學習新型異常、生成動態規則（後天免疫）

設計原則：
  - 零 LLM 依賴，純 CPU 啟發式
  - JSON 持久化
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

INITIAL_CONFIDENCE = 0.5       # 新規則初始信心度
REINFORCE_INCREMENT = 0.1      # 成功攔截的信心增量
FALSE_POSITIVE_DECREMENT = 0.15  # 誤報的信心減量
PRUNE_THRESHOLD = 0.2          # 清除門檻
DEFENSE_CHECK_THRESHOLD = 0.3  # 防禦查詢門檻
MAX_MEMORIES = 200             # 最大記憶數


# ═══════════════════════════════════════════
# ImmuneMemory 資料模型
# ═══════════════════════════════════════════


@dataclass
class ImmuneMemory:
    """單條免疫記憶."""

    anomaly_signature: str            # 異常特徵簽名
    occurrence_count: int = 1         # 發生次數
    defense_rule: str = ""            # 防禦規則描述
    confidence: float = 0.0           # 信心度（0.0 ~ 1.0）
    first_seen: str = ""              # 首次出現
    last_seen: str = ""               # 最後出現
    last_triggered: str = ""          # 最後觸發防禦
    success_count: int = 0            # 成功攔截次數
    false_positive_count: int = 0     # 誤報次數
    context_samples: List[str] = field(default_factory=list)  # 上下文樣本（最多 3 筆）

    @property
    def has_defense(self) -> bool:
        """是否已生成防禦規則."""
        return bool(self.defense_rule) and self.confidence > 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ImmuneMemory":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════
# ImmuneMemoryBank — 免疫記憶庫
# ═══════════════════════════════════════════


class ImmuneMemoryBank:
    """後天免疫記憶庫.

    學習流程：
      1st encounter → 記錄（無規則）
      2nd encounter → 生成防禦規則（conf=0.5）
      規則攔截成功 → conf += 0.1
      規則誤報 → conf -= 0.15
      conf < 0.2 → 定期清除

    提供：
      - record_anomaly(sig, ctx)：記錄異常
      - check_defense(sig)：查詢防禦規則
      - reinforce(sig, success)：強化/削弱規則
      - prune_weak()：清除弱規則
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self._memories: Dict[str, ImmuneMemory] = {}
        self._data_dir = data_dir
        self._file_path: Optional[Path] = None

        if data_dir:
            self._file_path = Path(data_dir) / "_system" / "immune_memory.json"
            self._file_path.parent.mkdir(parents=True, exist_ok=True)

        self._load()
        logger.info("ImmuneMemoryBank 初始化: %d 條記憶", len(self._memories))

    def record_anomaly(
        self,
        signature: str,
        context: str = "",
        defense_rule: str = "",
    ) -> ImmuneMemory:
        """記錄異常.

        第一次：記錄簽名和上下文
        第二次+：生成防禦規則（如果還沒有）

        Args:
            signature: 異常特徵簽名（用於匹配）
            context: 上下文描述
            defense_rule: 自訂防禦規則（可選，否則自動生成）

        Returns:
            更新後的 ImmuneMemory
        """
        now = datetime.now(timezone.utc).isoformat()

        if signature not in self._memories:
            if len(self._memories) >= MAX_MEMORIES:
                self.prune_weak()

            memory = ImmuneMemory(
                anomaly_signature=signature,
                occurrence_count=1,
                first_seen=now,
                last_seen=now,
                context_samples=[context[:200]] if context else [],
            )
            self._memories[signature] = memory
            logger.info("ImmuneMemory: 新異常記錄 [%s]", signature[:50])
        else:
            memory = self._memories[signature]
            memory.occurrence_count += 1
            memory.last_seen = now

            # 保留最多 3 筆上下文樣本
            if context and len(memory.context_samples) < 3:
                memory.context_samples.append(context[:200])

            # 第二次出現且還沒有防禦規則 → 生成規則
            if memory.occurrence_count >= 2 and not memory.has_defense:
                memory.defense_rule = defense_rule or self._auto_generate_rule(
                    signature, memory.context_samples
                )
                memory.confidence = INITIAL_CONFIDENCE
                logger.info(
                    "ImmuneMemory: 生成防禦規則 [%s] conf=%.2f",
                    signature[:50], memory.confidence,
                )

        self._save()
        return memory

    def check_defense(self, signature: str) -> Optional[str]:
        """查詢防禦規則.

        Args:
            signature: 異常特徵簽名

        Returns:
            防禦規則字串，或 None（無可用規則）
        """
        memory = self._memories.get(signature)
        if not memory:
            return None
        if not memory.has_defense:
            return None
        if memory.confidence < DEFENSE_CHECK_THRESHOLD:
            return None
        return memory.defense_rule

    def reinforce(self, signature: str, success: bool) -> Optional[float]:
        """強化或削弱防禦規則.

        Args:
            signature: 異常特徵簽名
            success: True=成功攔截, False=誤報

        Returns:
            更新後的信心度，或 None（找不到記憶）
        """
        memory = self._memories.get(signature)
        if not memory or not memory.has_defense:
            return None

        now = datetime.now(timezone.utc).isoformat()
        memory.last_triggered = now

        if success:
            memory.success_count += 1
            memory.confidence = min(1.0, memory.confidence + REINFORCE_INCREMENT)
        else:
            memory.false_positive_count += 1
            memory.confidence = max(0.0, memory.confidence - FALSE_POSITIVE_DECREMENT)

        self._save()

        logger.info(
            "ImmuneMemory: %s [%s] conf=%.2f",
            "強化" if success else "削弱",
            signature[:50],
            memory.confidence,
        )
        return memory.confidence

    def prune_weak(self, threshold: float = PRUNE_THRESHOLD) -> int:
        """清除弱規則.

        由 NightlyPipeline step_22 呼叫。

        Args:
            threshold: 信心度門檻（低於此值清除）

        Returns:
            清除數量
        """
        to_remove = [
            sig for sig, mem in self._memories.items()
            if mem.has_defense and mem.confidence < threshold
        ]

        for sig in to_remove:
            del self._memories[sig]

        if to_remove:
            self._save()
            logger.info("ImmuneMemory: 清除 %d 條弱規則", len(to_remove))

        return len(to_remove)

    def get_active_defenses(self) -> List[Dict[str, Any]]:
        """取得所有活躍防禦規則.

        Returns:
            活躍防禦列表（conf >= 0.3）
        """
        result = []
        for mem in self._memories.values():
            if mem.has_defense and mem.confidence >= DEFENSE_CHECK_THRESHOLD:
                result.append({
                    "signature": mem.anomaly_signature,
                    "rule": mem.defense_rule,
                    "confidence": round(mem.confidence, 2),
                    "success_count": mem.success_count,
                    "occurrence_count": mem.occurrence_count,
                })
        result.sort(key=lambda x: x["confidence"], reverse=True)
        return result

    def get_stats(self) -> Dict[str, Any]:
        """取得免疫記憶統計."""
        total = len(self._memories)
        with_defense = sum(1 for m in self._memories.values() if m.has_defense)
        active = sum(
            1 for m in self._memories.values()
            if m.has_defense and m.confidence >= DEFENSE_CHECK_THRESHOLD
        )
        return {
            "total_memories": total,
            "with_defense_rules": with_defense,
            "active_defenses": active,
            "avg_confidence": round(
                sum(m.confidence for m in self._memories.values() if m.has_defense)
                / max(1, with_defense),
                4,
            ),
        }

    # ─── 內部方法 ─────────────────────────

    def _auto_generate_rule(
        self, signature: str, context_samples: List[str]
    ) -> str:
        """自動生成防禦規則（啟發式）.

        根據異常簽名和上下文樣本生成簡單的防禦描述。
        """
        ctx = "; ".join(context_samples[:2]) if context_samples else "無上下文"
        return f"自動防禦: 偵測到重複異常 [{signature[:80]}], 上下文: [{ctx[:100]}]"

    def _load(self) -> None:
        """從檔案載入."""
        if not self._file_path or not self._file_path.exists():
            return
        try:
            raw = json.loads(self._file_path.read_text(encoding="utf-8"))
            for sig, data in raw.items():
                self._memories[sig] = ImmuneMemory.from_dict(data)
        except Exception as e:
            logger.warning("ImmuneMemoryBank 載入失敗: %s", e)

    def _save(self) -> None:
        """持久化到檔案."""
        if not self._file_path:
            return
        try:
            data = {k: v.to_dict() for k, v in self._memories.items()}
            self._file_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("ImmuneMemoryBank 儲存失敗: %s", e)
