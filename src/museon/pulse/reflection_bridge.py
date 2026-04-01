"""reflection_bridge — 反思→修復橋接層.

當 PulseEngine 的反思（晨感/暮感/探索）中偵測到問題關鍵字時，
自動寫入 triage_queue，讓 Nightly 的 triage_step 分診處理。

這是「意識→修復」的關鍵接線。
"""

import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


def bridge_reflection_to_triage(
    data_dir: Path,
    reflection_text: str,
    source: str = "pulse_reflection",
) -> int:
    """掃描反思文本中的問題訊號，寫入 triage_queue.

    Args:
        data_dir: MUSEON data 目錄路徑（即 PulseEngine._data_dir）
        reflection_text: 反思文本（來自 PULSE.md 的感知層/反思層）
        source: 訊號來源標識

    Returns:
        寫入的訊號數量
    """
    if not reflection_text or len(reflection_text) < 20:
        return 0

    # 問題關鍵字 → severity 映射
    PROBLEM_PATTERNS = {
        "CRITICAL": ["系統崩潰", "服務中斷", "資料損壞", "完全失效"],
        "HIGH": ["品質下降", "反覆出現", "持續惡化", "嚴重退化", "功能受損"],
        "MEDIUM": ["需要改善", "效率不佳", "偶爾失敗", "輕微異常", "值得關注"],
    }

    signals_written = 0
    triage_queue = data_dir / "_system" / "triage_queue.jsonl"
    triage_queue.parent.mkdir(parents=True, exist_ok=True)

    for severity, keywords in PROBLEM_PATTERNS.items():
        for kw in keywords:
            if kw in reflection_text:
                signal = {
                    "id": f"refl_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{signals_written}",
                    "timestamp": datetime.now().isoformat(),
                    "type": "reflection_finding",
                    "severity": severity,
                    "source": source,
                    "title": f"反思偵測: {kw}",
                    "detail": reflection_text[:500],
                    "actionability": "auto" if severity == "CRITICAL" else "human",
                }
                try:
                    with open(triage_queue, "a", encoding="utf-8") as f:
                        f.write(json.dumps(signal, ensure_ascii=False) + "\n")
                    signals_written += 1
                    logger.info(
                        "[ReflectionBridge] 反思→修復: %s [%s] → triage_queue",
                        kw, severity,
                    )
                except Exception as e:
                    logger.error("[ReflectionBridge] 寫入失敗: %s", e)
                break  # 每個 severity 只匹配一次

    if signals_written > 0:
        logger.info(
            "[ReflectionBridge] 共 %d 個反思訊號寫入 triage_queue", signals_written
        )

    return signals_written
