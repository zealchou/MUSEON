"""Probe Layer — CPU 級主動探針聚合器.

從荒謬雷達收集信號，用 CPU 閘門控制頻率，
選出最緊急的探針問題注入 Brain prompt。
零 LLM token 消耗（偵測），注入時僅 ~30 tokens。
"""

import json
import logging
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

UNCERTAINTY_KEYWORDS = (
    "不知道", "不確定", "不太清楚", "沒想過",
    "還在想", "猶豫", "迷茫", "困惑",
)


def _probes_dir(data_dir: str = "data") -> Path:
    """探針狀態目錄（與探針庫分開存放）。"""
    return Path(data_dir) / "_system" / "probe_states"


def load_probe_library(data_dir: str = "data") -> Dict[str, Dict[str, List[str]]]:
    """載入探針庫。

    實際路徑：data/_system/constellations/probe_library.json
    格式：{"version": ..., "probes": {constellation: {dimension: [questions]}}}
    回傳 probes 鍵的內容，供 select_probe 使用。
    """
    path = Path(data_dir) / "_system" / "constellations" / "probe_library.json"
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            # 支援包裝格式（含 version/description）和扁平格式
            return raw.get("probes", raw)
    except Exception as e:
        logger.warning(f"[ProbeLayer] load_probe_library failed: {e}")
    return {}


def load_probe_state(session_id: str, data_dir: str = "data") -> Dict:
    """載入探針狀態（上次探測的輪次、最近用過的探針）"""
    path = _probes_dir(data_dir) / f"state_{session_id}.json"
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "last_probe_turn": int(data.get("last_probe_turn", 0)),
                "recent_probes": list(data.get("recent_probes", [])),
                "last_phase": data.get("last_phase"),
                "phase_constellation": data.get("phase_constellation"),
                "phase_dimension": data.get("phase_dimension"),
            }
    except Exception as e:
        logger.warning(f"[ProbeLayer] load_probe_state failed for {session_id}: {e}")
    return {"last_probe_turn": 0, "recent_probes": [], "last_phase": None,
            "phase_constellation": None, "phase_dimension": None}


def save_probe_state(session_id: str, state: Dict, data_dir: str = "data") -> None:
    """持久化探針狀態"""
    path = _probes_dir(data_dir) / f"state_{session_id}.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[ProbeLayer] save_probe_state failed for {session_id}: {e}")


def should_probe(
    interaction_count: int,
    last_probe_turn: int,
    min_interval: int = 5,
    max_interval: int = 8,
    user_signal: Optional[str] = None,
    is_emotional: bool = False,
) -> bool:
    """CPU 閘門判斷是否應該探測。

    規則：
    1. gap < min_interval → False
    2. is_emotional → False（情緒爆發時不探測）
    3. user_signal 含 uncertainty keywords → True（提前開閘）
    4. gap >= max_interval → True（太久沒問了）
    5. 否則隨機 30% 機率 True
    """
    gap = interaction_count - last_probe_turn
    if gap < min_interval:
        logger.info(f"[ProbeLayer] should_probe=False reason=gap_too_small gap={gap} min={min_interval}")
        return False
    if is_emotional:
        logger.info("[ProbeLayer] should_probe=False reason=emotional_state")
        return False
    if user_signal and any(kw in user_signal for kw in UNCERTAINTY_KEYWORDS):
        logger.info("[ProbeLayer] should_probe=True reason=uncertainty_keyword")
        return True
    if gap >= max_interval:
        logger.info(f"[ProbeLayer] should_probe=True reason=max_interval gap={gap}")
        return True
    result = random.random() < 0.30
    logger.info(f"[ProbeLayer] should_probe={result} reason=random_30pct")
    return result


def select_probe(
    constellation_name: str,
    weakest_dim: str,
    probe_library: Dict,
    recent_probes: List[str],
    max_recent: int = 5,
) -> Optional[str]:
    """選出一個探針問題，避免重複最近用過的。"""
    candidates = probe_library.get(constellation_name, {}).get(weakest_dim, [])
    if not candidates:
        return None
    recent_set = set(recent_probes[-max_recent:])
    available = [q for q in candidates if q not in recent_set] or candidates
    return random.choice(available)


def determine_phase(
    state: Dict,
    interaction_count: int,
    last_probe_turn: int,
) -> int:
    """判斷下次探針應該用哪個 Phase。

    - 從未探測過（last_phase 不存在） → Phase 1
    - 上次 Phase 1 且距離 < 3 輪 → Phase 2（延續議題）
    - 上次 Phase 2 且距離 < 3 輪 → Phase 3
    - 上次 Phase 3 或距離 ≥ 3 輪 → Phase 1（新議題）
    """
    last_phase = state.get("last_phase")
    gap = interaction_count - last_probe_turn
    if last_phase is None:
        return 1
    if gap >= 3:
        return 1
    if last_phase == 1:
        return 2
    if last_phase == 2:
        return 3
    return 1


def get_phase_prefix(phase: int) -> str:
    """根據 phase 產生不同的注入指示。"""
    if phase == 1:
        return "幫助使用者命名問題——讓他能清楚說出卡在哪裡。"
    elif phase == 2:
        return "使用者已經命名了問題，現在引導他思考可能的方向和資源。"
    elif phase == 3:
        return "引導使用者從理想的終點狀態逆推——如果問題已經解決了，那個狀態長什麼樣？從那裡往回看，需要經過哪些步驟？"
    return ""


def format_probe_injection(probe_question: str, phase: int = 1) -> str:
    """格式化為 Brain prompt 注入文本。"""
    prefix = get_phase_prefix(phase)
    prefix_line = f"{prefix}\n" if prefix else ""
    return (
        "## 主動探針（本輪注入）\n"
        f"{prefix_line}"
        "在回覆的自然結尾處，帶入以下問題：\n"
        f"「{probe_question}」\n"
        "不要生硬插入，用你的判斷找到最自然的銜接點。"
        "如果這輪對話完全不適合，可以跳過。"
    )


def aggregate_signals(
    constellations: Dict[str, Dict[str, float]],
    data_dir: str = "data",
) -> Optional[Tuple[str, str, str]]:
    """從所有星座雷達中找出最緊急的信號。

    回傳：(constellation_name, weakest_dim, probe_question) 或 None

    優先級邏輯：
    1. 信心 > 0.1 的星座才參與
    2. 各星座最弱維度取出
    3. gap = 0.5 - weakest_score（低於 0.5 才算缺口）
    4. 最大 gap 的勝出
    """
    probe_library = load_probe_library(data_dir)
    if not probe_library:
        logger.warning("[ProbeLayer] probe_library is empty")
        return None

    best: Optional[Tuple[float, str, str]] = None

    for cname, scores in constellations.items():
        if scores.get("confidence", 0.0) <= 0.1:
            continue
        dim_scores = {k: v for k, v in scores.items()
                      if k != "confidence" and isinstance(v, (int, float))}
        if not dim_scores:
            continue
        weakest_dim = min(dim_scores, key=lambda d: dim_scores[d])
        gap = 0.5 - dim_scores[weakest_dim]
        if gap > 0 and (best is None or gap > best[0]):
            best = (gap, cname, weakest_dim)

    if best is None:
        return None

    _, cname, weakest_dim = best
    question = select_probe(cname, weakest_dim, probe_library, [])
    if question is None:
        return None

    logger.info(f"[ProbeLayer] signal: {cname}/{weakest_dim} gap={best[0]:.2f}")
    return (cname, weakest_dim, question)


def run_probe_cycle(
    interaction_count: int,
    session_id: str,
    constellations: Dict[str, Dict[str, float]],
    user_signal: Optional[str] = None,
    is_emotional: bool = False,
    data_dir: str = "data",
) -> Optional[str]:
    """完整探針週期：閘門判斷 → 信號聚合 → 選問句 → 格式化注入文本。

    回傳 Brain prompt 注入文本，或 None（不探測）。
    呼叫方負責將此文本附加到 prompt 末尾。
    """
    state = load_probe_state(session_id, data_dir)
    last_probe_turn = state["last_probe_turn"]
    recent_probes = state["recent_probes"]

    _probe_gate = should_probe(
        interaction_count=interaction_count,
        last_probe_turn=last_probe_turn,
        user_signal=user_signal,
        is_emotional=is_emotional,
    )
    logger.info(
        f"[ProbeLayer] run_probe_cycle: session={session_id} "
        f"interaction={interaction_count} last_probe={last_probe_turn} "
        f"gate={_probe_gate}"
    )
    if not _probe_gate:
        return None

    probe_library = load_probe_library(data_dir)
    if not probe_library:
        return None

    phase = determine_phase(state, interaction_count, last_probe_turn)

    # Phase 2/3：嘗試延續上次的星座和維度
    cname: Optional[str] = None
    weakest_dim: Optional[str] = None
    if phase in (2, 3) and state.get("phase_constellation") and state.get("phase_dimension"):
        cname = state["phase_constellation"]
        weakest_dim = state["phase_dimension"]
        logger.debug(f"[ProbeLayer] phase={phase} reusing {cname}/{weakest_dim}")

    if cname is None or weakest_dim is None:
        result = aggregate_signals(constellations=constellations, data_dir=data_dir)
        if result is None:
            return None
        cname, weakest_dim, _ = result

    question = select_probe(cname, weakest_dim, probe_library, recent_probes)
    if question is None:
        return None

    recent_probes.append(question)
    state["last_probe_turn"] = interaction_count
    state["recent_probes"] = recent_probes[-10:]
    state["last_phase"] = phase
    state["phase_constellation"] = cname
    state["phase_dimension"] = weakest_dim
    save_probe_state(session_id, state, data_dir)

    logger.info(
        f"[ProbeLayer] phase={phase} probe selected: "
        f"constellation={cname} dim={weakest_dim} "
        f"question={question[:60]}..."
    )
    return format_probe_injection(question, phase=phase)
