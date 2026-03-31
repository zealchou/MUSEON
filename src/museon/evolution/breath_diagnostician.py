"""breath_diagnostician — Breath Protocol 診斷層.

用乾淨的 context 看 patterns 結論。
讀五張藍圖，找結構性問題。
減法優先。

核心問題不是「怎麼修」，是「哪個設計假設已經不成立了」。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DIAGNOSIS_PROMPT = """你是一個系統架構診斷師，剛剛收到一份系統觀察摘要。

你的任務是找出根因並提出修復方案。你不知道這份報告是怎麼產生的，只看結果。

## 系統背景

這是 MUSEON — 一個 AI-powered 教練系統，服務於台灣用戶，透過 Telegram 傳遞洞見。
系統包含以下主要模組：Brain（核心 LLM）、ANIMA（人格核心）、Nightly（夜間批次）、
各類 Skill（技能插件）、Memory（三層記憶：L1/L2/L3）。

## 系統藍圖摘要

{blueprints_summary}

## 本週觀察的三視角共識與 Top Patterns

{patterns_synthesis}
{top_patterns}

---

請產出以下診斷報告（JSON 格式）：

```json
{{
  "root_cause_hypothesis": "一句話說清楚根本原因",
  "subtraction_option": {{
    "description": "優先考慮刪掉/簡化什麼",
    "blast_radius": 1,
    "effort": "low|medium|high",
    "why_this_first": "為什麼減法優先"
  }},
  "addition_option": {{
    "description": "如果減法不可行，加什麼",
    "blast_radius": 2,
    "effort": "low|medium|high",
    "why_addition": "為什麼減法不可行"
  }},
  "recommended": "subtraction|addition|none",
  "acceptance_criteria": ["驗收條件 1", "驗收條件 2"],
  "consumption_chain": "做了之後，誰會用到這個改動？效果會怎麼測量？",
  "red_flags": ["如果 X 沒改善代表沒修到根因", "如果 Y 發生代表方向錯了"]
}}
```

只輸出 JSON，不要其他文字。"""


async def diagnose(workspace: Path, week_id: str) -> dict[str, Any]:
    """讀 patterns 結論 + 五張藍圖，產出結構診斷.

    Args:
        workspace: MUSEON 根目錄
        week_id: 週次 ID，格式 "YYYY-wNN"

    Returns:
        diagnosis dict，同時寫入 diagnoses/{week_id}.json
    """
    # 讀 patterns 結論
    patterns_path = workspace / f"data/_system/breath/patterns/{week_id}.json"
    if not patterns_path.exists():
        logger.warning(f"[BreathDiagnostician] patterns 檔案不存在: {patterns_path}")
        return {"error": f"patterns/{week_id}.json 不存在，請先執行 Day 3-4 分析"}

    patterns_data = json.loads(patterns_path.read_text(encoding="utf-8"))
    synthesis = patterns_data.get("synthesis", "")
    top_patterns = patterns_data.get("top_patterns", [])

    # 讀五張藍圖摘要
    blueprints_summary = _read_blueprints_summary(workspace)

    # 格式化 top_patterns
    top_patterns_text = "\n".join(f"- {p}" for p in top_patterns) if top_patterns else "（無）"

    # 用乾淨 context 做診斷（不帶 patterns 的分析過程，只帶結論）
    prompt = _DIAGNOSIS_PROMPT.format(
        blueprints_summary=blueprints_summary,
        patterns_synthesis=synthesis[:2000],
        top_patterns=top_patterns_text,
    )

    raw_diagnosis = ""
    try:
        raw_diagnosis = await _call_llm(
            prompt=prompt,
            model="sonnet",
            system=(
                "你是一個客觀的系統架構診斷師。"
                "你剛收到這份報告，沒有先入為主的假設。"
                "優先考慮減法方案。只輸出 JSON，不要解釋。"
            ),
        )
    except NotImplementedError:
        raw_diagnosis = json.dumps({
            "root_cause_hypothesis": "[PLACEHOLDER] LLM adapter 尚未接入",
            "subtraction_option": {
                "description": "待 LLM 分析",
                "blast_radius": 1,
                "effort": "unknown",
                "why_this_first": "待分析",
            },
            "addition_option": {
                "description": "待 LLM 分析",
                "blast_radius": 2,
                "effort": "unknown",
                "why_addition": "待分析",
            },
            "recommended": "none",
            "acceptance_criteria": [],
            "consumption_chain": "待分析",
            "red_flags": [],
        })

    # 解析 LLM 回傳的 JSON
    diagnosis_content = _parse_json_response(raw_diagnosis)

    result: dict[str, Any] = {
        "week_id": week_id,
        "generated_at": datetime.now().isoformat(),
        "patterns_source": str(patterns_path),
        **diagnosis_content,
    }

    # 寫入 diagnoses 目錄
    output_dir = workspace / "data/_system/breath/diagnoses"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{week_id}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"[BreathDiagnostician] diagnosis 已寫入: {output_path}")
    return result


def _read_blueprints_summary(workspace: Path) -> str:
    """讀五張藍圖，提取關鍵統計資訊."""
    docs_dir = workspace / "docs"
    summaries: list[str] = []

    blueprint_files = {
        "神經圖 (system-topology)": "system-topology.md",
        "水電圖 (persistence-contract)": "persistence-contract.md",
        "接頭圖 (joint-map)": "joint-map.md",
        "爆炸圖 (blast-radius)": "blast-radius.md",
        "郵路圖 (memory-router)": "memory-router.md",
    }

    for name, filename in blueprint_files.items():
        file_path = docs_dir / filename
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                # 只取前 500 字元（藍圖可能很長）
                summaries.append(f"### {name}\n{content[:500]}\n...")
            except OSError:
                summaries.append(f"### {name}\n（讀取失敗）")
        else:
            summaries.append(f"### {name}\n（檔案不存在: {file_path}）")

    return "\n\n".join(summaries) if summaries else "（五張藍圖均無法讀取）"


def _parse_json_response(raw: str) -> dict:
    """從 LLM 回傳中提取 JSON."""
    # 嘗試直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 嘗試找 ```json ... ``` 塊
    import re
    match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 嘗試找第一個 { ... }
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # 全部失敗，回傳原始文字
    return {
        "root_cause_hypothesis": raw[:500],
        "parse_error": "無法從 LLM 回傳中解析 JSON",
    }


async def _call_llm(prompt: str, model: str = "sonnet", system: str = "") -> str:
    """呼叫 LLM。使用 MUSEON 現有的 LLM adapter."""
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
        logger.warning(f"[BreathDiagnostician] LLM 呼叫失敗: {e}")
        raise NotImplementedError(f"LLM adapter 呼叫失敗: {e}") from e
