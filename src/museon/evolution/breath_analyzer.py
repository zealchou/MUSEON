"""breath_analyzer — Breath Protocol 模式分析層.

五層深度分析，每一層是獨立的思考步驟。
三視角交叉：spawn 三個獨立 context 各自看同一份觀察。

核心原則：不急。每一層想清楚再往下一層。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 五層分析的 prompt 模板
_LAYER_PROMPTS: dict[int, str] = {
    1: (
        "你是一個客觀的系統觀察者。\n\n"
        "以下是 MUSEON AI 系統這週的原始觀察資料（四條河流：Zeal 互動、客戶互動、自我指標、外部探索）。\n\n"
        "任務：列出這些觀察中的事實。\n"
        "規則：\n"
        "- 不加判斷\n"
        "- 不推測原因\n"
        "- 只說「發生了什麼」\n"
        "- 每條事實一行，用「・」開頭\n\n"
        "觀察資料：\n{observations_summary}\n"
    ),
    2: (
        "你是一個系統分析師。\n\n"
        "基於以下事實列表，分析每個事實的直接原因。\n\n"
        "事實：\n{previous_output}\n\n"
        "任務：為什麼會這樣？\n"
        "規則：\n"
        "- 找直接原因（不是根因）\n"
        "- 每條事實對應一條原因\n"
        "- 格式：事實 → 直接原因\n"
    ),
    3: (
        "你是一個系統架構師。\n\n"
        "基於以下直接原因，找出背後的結構性原因。\n\n"
        "直接原因：\n{previous_output}\n\n"
        "任務：為什麼這些直接原因存在？\n"
        "規則：\n"
        "- 找共同的結構性問題（幾個直接原因可能指向同一個結構問題）\n"
        "- 區分「設計決策」和「執行問題」\n"
        "- 格式：結構問題 + 它導致了哪些直接原因\n"
    ),
    4: (
        "你是一個系統耦合分析師。\n\n"
        "基於以下結構性問題，分析耦合關係。\n\n"
        "結構性問題：\n{previous_output}\n\n"
        "任務：這個結構問題還影響了系統的哪些其他地方？\n"
        "規則：\n"
        "- 列出受影響的模組/功能\n"
        "- 估計影響程度（直接/間接）\n"
        "- 注意：MUSEON 有五張藍圖（神經圖/水電圖/接頭圖/爆炸圖/郵路圖），考慮各個維度\n"
    ),
    5: (
        "你是一個第一性原理思考者。\n\n"
        "基於以下耦合分析，找出根本解決方案。\n\n"
        "耦合分析：\n{previous_output}\n\n"
        "任務：要從根本解決，需要改變什麼設計假設？\n"
        "規則：\n"
        "- 問「這個問題是因為我們假設了什麼？」\n"
        "- 優先考慮減法（刪掉什麼）而不是加法（加什麼）\n"
        "- 每個假設給出：當前假設 → 更好的假設 → 需要改變什麼\n"
    ),
}

_SYNTHESIS_PROMPT = (
    "你是一個整合分析師。\n\n"
    "以下是三個獨立分析視角對同一份 MUSEON 系統觀察的結論：\n\n"
    "視角 1：\n{perspective_1}\n\n"
    "視角 2：\n{perspective_2}\n\n"
    "視角 3：\n{perspective_3}\n\n"
    "任務：\n"
    "1. 找出三個視角的共識（都同意的問題）\n"
    "2. 找出三個視角的分歧（各自看到不同的問題）\n"
    "3. 列出最重要的 3 個模式（最需要關注的）\n"
    "4. 你自己的綜合判斷：下週最值得處理的根因是什麼？\n"
)


async def analyze_patterns(workspace: Path, week_id: str) -> dict[str, Any]:
    """讀觀察資料，跑五層深度分析 + 三視角交叉驗證.

    Args:
        workspace: MUSEON 根目錄
        week_id: 週次 ID，格式 "YYYY-wNN"

    Returns:
        patterns dict，同時寫入 patterns/{week_id}.json
    """
    obs_path = workspace / f"data/_system/breath/observations/{week_id}.jsonl"
    if not obs_path.exists():
        logger.warning(f"[BreathAnalyzer] 觀察檔案不存在: {obs_path}")
        return {"error": f"observations/{week_id}.jsonl 不存在，請先執行 Day 1-2 觀察"}

    # 讀觀察資料
    observations: list[dict] = []
    for line in obs_path.read_text(encoding="utf-8").strip().splitlines():
        try:
            observations.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    if not observations:
        return {"error": "觀察資料為空", "week_id": week_id}

    observations_summary = _summarize_observations(observations)

    # 三個獨立視角（各自跑五層）
    perspectives = []
    for i in range(1, 4):
        perspective = await _run_five_layers(observations_summary, perspective_id=i)
        perspectives.append(perspective)

    # 整合三個視角
    synthesis = await _synthesize_perspectives(perspectives)

    result: dict[str, Any] = {
        "week_id": week_id,
        "observations_count": len(observations),
        "generated_at": datetime.now().isoformat(),
        "perspectives": perspectives,
        "synthesis": synthesis,
        "top_patterns": _extract_top_patterns(synthesis),
    }

    # 寫入 patterns 目錄
    output_dir = workspace / "data/_system/breath/patterns"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{week_id}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"[BreathAnalyzer] patterns 已寫入: {output_path}")
    return result


async def _run_five_layers(observations_summary: str, perspective_id: int) -> dict:
    """一個視角的五層分析."""
    layers: list[dict] = []
    previous_output = observations_summary

    for layer_num in range(1, 6):
        prompt_template = _LAYER_PROMPTS[layer_num]

        if layer_num == 1:
            prompt = prompt_template.format(observations_summary=observations_summary)
        else:
            prompt = prompt_template.format(previous_output=previous_output)

        try:
            output = await _call_llm(
                prompt=prompt,
                model="haiku",
                system=(
                    f"你是 MUSEON 系統分析的 Layer {layer_num} 分析師（視角 {perspective_id}）。"
                    "保持客觀，聚焦於系統結構問題，不要關注個人。"
                ),
            )
        except NotImplementedError:
            output = f"[PLACEHOLDER] Layer {layer_num} 視角 {perspective_id} — LLM adapter 尚未接入"

        layers.append({
            "layer": layer_num,
            "output": output,
        })
        previous_output = output

    return {
        "id": perspective_id,
        "layers": layers,
        "conclusion": previous_output,  # Layer 5 的輸出是最終結論
    }


async def _synthesize_perspectives(perspectives: list[dict]) -> str:
    """整合三個視角的結論."""
    prompt = _SYNTHESIS_PROMPT.format(
        perspective_1=perspectives[0]["conclusion"] if len(perspectives) > 0 else "（無）",
        perspective_2=perspectives[1]["conclusion"] if len(perspectives) > 1 else "（無）",
        perspective_3=perspectives[2]["conclusion"] if len(perspectives) > 2 else "（無）",
    )

    try:
        return await _call_llm(
            prompt=prompt,
            model="sonnet",
            system="你是一個系統架構整合分析師，任務是從多個視角中找出共識和最重要的模式。",
        )
    except NotImplementedError:
        return "[PLACEHOLDER] synthesis — LLM adapter 尚未接入"


def _summarize_observations(observations: list[dict]) -> str:
    """將觀察資料壓縮成可以放進 prompt 的摘要."""
    by_river: dict[str, list] = {}
    for obs in observations:
        river = obs.get("river", "unknown")
        if river not in by_river:
            by_river[river] = []
        by_river[river].append(obs)

    lines = []
    for river, river_obs in by_river.items():
        lines.append(f"\n### {river} ({len(river_obs)} 條)")
        for obs in river_obs[:10]:  # 每條河流最多 10 條
            content = obs.get("content", "")
            if isinstance(content, dict):
                content = json.dumps(content, ensure_ascii=False)[:300]
            elif isinstance(content, str):
                content = content[:300]
            lines.append(f"- [{obs.get('type', '?')}] {content}")

    return "\n".join(lines)


def _extract_top_patterns(synthesis: str) -> list[str]:
    """從 synthesis 文字中提取 top patterns（簡單的行解析）."""
    patterns = []
    for line in synthesis.splitlines():
        line = line.strip()
        if line.startswith(("・", "-", "•", "1.", "2.", "3.")):
            cleaned = line.lstrip("・-•0123456789. ")
            if cleaned and len(cleaned) > 10:
                patterns.append(cleaned[:200])
        if len(patterns) >= 5:
            break
    return patterns


async def _call_llm(prompt: str, model: str = "haiku", system: str = "") -> str:
    """呼叫 LLM。使用 MUSEON 現有的 LLM adapter.

    TODO: 後續整合——需要 adapter 實例。
    目前為 placeholder，breath_scheduler 在實際跑時會注入 adapter。
    """
    # 嘗試用 create_adapter 取得 adapter
    try:
        from museon.llm.adapters import create_adapter  # noqa: PLC0415
        adapter = await create_adapter()
        messages = [{"role": "user", "content": prompt}]
        response = await adapter.call(
            system_prompt=system,
            messages=messages,
            model=model,
        )
        return response.text
    except Exception as e:
        logger.warning(f"[BreathAnalyzer] LLM 呼叫失敗: {e}，回傳 placeholder")
        raise NotImplementedError(f"LLM adapter 呼叫失敗: {e}") from e
