"""BreathAnalyzer — 呼吸系統 Day 3-4 自動化.

每週 Day 3（週三）自動觸發，讀取本週觀察資料，
執行五層深度分析，產出模式假說。

零 LLM 依賴：只做 CPU 級的模式萃取和統計分析。
LLM 級的深度分析由 Nightly 的 Step 16（Dream Engine）
在週三時自動切換為 Breath 分析模式。
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))


def get_current_week_id() -> str:
    """回傳 yyyy-wNN 格式的週 ID."""
    now = datetime.now(TZ_TAIPEI)
    return f"{now.year}-w{now.isocalendar()[1]:02d}"


def load_observations(data_dir: Path, week_id: Optional[str] = None) -> List[Dict]:
    """讀取指定週的觀察資料."""
    week_id = week_id or get_current_week_id()
    obs_file = data_dir / "_system" / "breath" / "observations" / f"{week_id}.jsonl"
    if not obs_file.exists():
        return []
    observations = []
    for line in obs_file.read_text().strip().split("\n"):
        if line.strip():
            try:
                observations.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return observations


def analyze_patterns(observations: List[Dict]) -> Dict[str, Any]:
    """CPU 級五層分析.

    L1: 事實列舉（統計觀察分布）
    L2: 直接原因（頻率異常偵測）
    L3: 結構原因（跨河流關聯）
    L4: 耦合分析（影響範圍估算）
    L5: 第一性原理（減法建議）
    """
    if not observations:
        return {"status": "no_observations", "layers": {}}

    # L1: 事實列舉
    stream_counts: Dict[str, int] = {}  # 河流分布
    signal_types: Dict[str, int] = {}   # 訊號類型分布
    severity_counts = {"info": 0, "warning": 0, "error": 0, "critical": 0}

    for obs in observations:
        stream = obs.get("stream", "unknown")
        stream_counts[stream] = stream_counts.get(stream, 0) + 1

        sig_type = obs.get("type", "unknown")
        signal_types[sig_type] = signal_types.get(sig_type, 0) + 1

        severity = obs.get("severity", "info")
        if severity in severity_counts:
            severity_counts[severity] += 1

    l1 = {
        "total_observations": len(observations),
        "stream_distribution": stream_counts,
        "signal_types": signal_types,
        "severity_distribution": severity_counts,
    }

    # L2: 直接原因 — 異常頻率偵測
    anomalies = []
    avg_per_stream = len(observations) / max(len(stream_counts), 1)
    for stream, count in stream_counts.items():
        if count > avg_per_stream * 2:
            anomalies.append({
                "stream": stream,
                "count": count,
                "expected": round(avg_per_stream, 1),
                "ratio": round(count / max(avg_per_stream, 1), 1),
            })

    # 重複訊號偵測
    repeated_signals = {k: v for k, v in signal_types.items() if v >= 3}

    l2 = {
        "stream_anomalies": anomalies,
        "repeated_signals": repeated_signals,
        "has_critical": severity_counts.get("critical", 0) > 0,
    }

    # L3: 結構原因 — 跨河流關聯
    cross_stream = []
    # 找出同時出現在多條河流的訊號模式
    signal_streams: Dict[str, set] = {}
    for obs in observations:
        sig = obs.get("type", "unknown")
        stream = obs.get("stream", "unknown")
        signal_streams.setdefault(sig, set()).add(stream)

    for sig, streams in signal_streams.items():
        if len(streams) >= 2:
            cross_stream.append({
                "signal": sig,
                "streams": list(streams),
                "count": signal_types.get(sig, 0),
            })

    l3 = {"cross_stream_patterns": cross_stream}

    # L4: 耦合分析 — 影響範圍估算
    # 從 L2 的異常 + L3 的跨河流，推估影響模組數
    affected_scope = "low"
    if len(cross_stream) >= 3 or severity_counts.get("critical", 0) > 0:
        affected_scope = "high"
    elif len(cross_stream) >= 1 or len(anomalies) >= 2:
        affected_scope = "medium"

    l4 = {
        "affected_scope": affected_scope,
        "cross_pattern_count": len(cross_stream),
        "anomaly_count": len(anomalies),
    }

    # L5: 第一性原理 — 減法建議
    suggestions = []
    if repeated_signals:
        suggestions.append({
            "type": "subtraction",
            "description": (
                f"重複訊號 {list(repeated_signals.keys())[:3]} "
                f"可能暗示同一根因，建議先消除重複再處理"
            ),
        })
    if affected_scope == "high":
        suggestions.append({
            "type": "structural",
            "description": "跨河流模式暗示結構性問題，減法優先：找到共同上游並簡化",
        })
    if not suggestions:
        suggestions.append({
            "type": "stable",
            "description": "本週無明顯結構問題，維持觀察",
        })

    l5 = {"suggestions": suggestions}

    return {
        "status": "analyzed",
        "week_id": get_current_week_id(),
        "timestamp": datetime.now(TZ_TAIPEI).isoformat(),
        "layers": {
            "L1_facts": l1,
            "L2_direct_cause": l2,
            "L3_structural_cause": l3,
            "L4_coupling": l4,
            "L5_first_principles": l5,
        },
    }


def run_breath_analysis(data_dir: Path) -> Dict[str, Any]:
    """主入口：執行週度呼吸分析.

    只在 Day 3-4（週三、週四）執行。
    其他天回傳 skip。
    """
    now = datetime.now(TZ_TAIPEI)
    weekday = now.weekday()  # 0=Mon, 2=Wed, 3=Thu

    if weekday not in (2, 3):  # 只在週三、週四執行
        return {"status": "skipped", "reason": f"weekday={weekday}, only runs on Wed/Thu"}

    week_id = get_current_week_id()

    # 檢查是否已分析過本週
    pattern_file = data_dir / "_system" / "breath" / "patterns" / f"{week_id}.json"
    if pattern_file.exists() and weekday == 3:
        # 週四如果已有結果就跳過
        return {"status": "already_analyzed", "week_id": week_id}

    observations = load_observations(data_dir, week_id)
    if not observations:
        return {"status": "no_observations", "week_id": week_id}

    result = analyze_patterns(observations)

    # 寫入 patterns
    pattern_file.parent.mkdir(parents=True, exist_ok=True)
    with open(pattern_file, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(
        f"[BREATH] 週度分析完成 {week_id}: "
        f"{result['layers']['L1_facts']['total_observations']} obs, "
        f"scope={result['layers']['L4_coupling']['affected_scope']}"
    )

    return result
