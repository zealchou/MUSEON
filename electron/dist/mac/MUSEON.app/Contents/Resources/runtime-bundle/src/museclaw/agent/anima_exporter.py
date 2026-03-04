"""ANIMA Exporter — 雙格式匯出（Markdown + JSON 同步）.

在 Nightly 結束後同步匯出 ANIMA_MC.md 和 ANIMA_USER.md，
提供人類可讀的 ANIMA 狀態報告。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AnimaExporter:
    """ANIMA 雙格式匯出器."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.export_dir = data_dir / "anima"
        self.export_dir.mkdir(parents=True, exist_ok=True)
        logger.info("AnimaExporter 初始化完成")

    def sync_exports(
        self,
        anima_mc: Dict[str, Any],
        anima_user: Dict[str, Any],
    ) -> None:
        """同步匯出 .json 和 .md 兩種格式."""
        try:
            mc_md = self.export_markdown(anima_mc, "MC")
            (self.export_dir / "ANIMA_MC.md").write_text(mc_md, encoding="utf-8")
        except Exception as e:
            logger.error(f"ANIMA_MC.md 匯出失敗: {e}")

        try:
            user_md = self.export_markdown(anima_user, "USER")
            (self.export_dir / "ANIMA_USER.md").write_text(user_md, encoding="utf-8")
        except Exception as e:
            logger.error(f"ANIMA_USER.md 匯出失敗: {e}")

        logger.info("ANIMA 雙格式匯出完成")

    def export_markdown(self, anima_data: dict, target: str) -> str:
        """匯出為人類可讀的 Markdown 格式."""
        if target == "MC":
            return self._export_mc_markdown(anima_data)
        else:
            return self._export_user_markdown(anima_data)

    # ─── MC Markdown ─────────────────────────

    def _export_mc_markdown(self, mc: dict) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        identity = mc.get("identity", {})
        sa = mc.get("self_awareness", {})
        personality = mc.get("personality", {})
        caps = mc.get("capabilities", {})
        evo = mc.get("evolution", {})
        mem = mc.get("memory_summary", {})
        primals = mc.get("eight_primals", {})

        lines = [
            f"# {identity.get('name', 'Unknown')} ANIMA 狀態報告",
            f"> 最後更新：{now}",
            "",
            "## 身份",
            f"- 名稱：{identity.get('name', '?')}",
            f"- 誕生：{identity.get('birth_date', '?')[:10]}",
            f"- 成長階段：{identity.get('growth_stage', '?')} ({identity.get('days_alive', 0)} 天)",
            "",
            "## 自我認知",
            f"- 我是誰：{sa.get('who_am_i', '?')}",
            f"- 目的：{sa.get('my_purpose', '?')}",
            f"- 存在原因：{sa.get('why_i_exist', '?')}",
            "",
            "## 人格特質",
            f"- 核心特質：{', '.join(personality.get('core_traits', []))}",
            f"- 溝通風格：{personality.get('communication_style', '?')}",
            "",
            "## 八原語",
            "| 卦 | 等級 | 信號 |",
            "|-----|------|------|",
        ]

        for key, val in primals.items():
            if isinstance(val, dict):
                level = val.get("level", 0)
                signal = val.get("signal", "")[:40]
                lines.append(f"| {key} | {level} | {signal} |")

        lines.extend([
            "",
            "## 能力",
            f"- 已載入 Skills：{len(caps.get('loaded_skills', []))}",
            f"- Skill 熟練度：{len(caps.get('skill_proficiency', {}))} 筆",
            "",
            "## 演化",
            f"- 當前階段：{evo.get('current_stage', '?')}",
            f"- 迭代次數：{evo.get('iteration_count', 0)}",
            f"- 演化暫停：{'是' if evo.get('paused') else '否'}",
            "",
            "## 記憶摘要",
            f"- 總互動數：{mem.get('total_interactions', 0)}",
            f"- 知識結晶：{mem.get('knowledge_crystals', 0)}",
            "",
        ])

        return "\n".join(lines)

    # ─── USER Markdown ─────────────────────────

    def _export_user_markdown(self, user: dict) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        profile = user.get("profile", {})
        rel = user.get("relationship", {})
        primals = user.get("eight_primals", {})
        layers = user.get("seven_layers", {})

        lines = [
            f"# {profile.get('name', 'Unknown')} ANIMA 使用者鏡像報告",
            f"> 最後更新：{now}",
            "",
            "## 基本資料",
            f"- 名稱：{profile.get('name', '?')}",
            f"- 暱稱：{profile.get('nickname', '?')}",
            f"- 角色：{profile.get('role', '?')}",
            f"- 產業：{profile.get('industry', '?')}",
            "",
            "## 關係",
            f"- 信任等級：{rel.get('trust_level', '?')}",
            f"- 總互動數：{rel.get('total_interactions', 0)}",
            f"- 首次互動：{str(rel.get('first_interaction', '?'))[:10]}",
            "",
            "## 八原語",
            "| 維度 | 等級 | 信心度 | 信號 |",
            "|------|------|--------|------|",
        ]

        for key, val in primals.items():
            if isinstance(val, dict):
                level = val.get("level", 0)
                conf = val.get("confidence", 0)
                signal = val.get("signal", "")[:30]
                lines.append(f"| {key} | {level} | {conf} | {signal} |")

        # 七層摘要
        lines.extend([
            "",
            "## 七層同心圓",
            f"- L1 事實：{len(layers.get('L1_facts', []))} 筆",
            f"- L2 人格：{len(layers.get('L2_personality', []))} 筆",
            f"- L3 決策模式：{len(layers.get('L3_decision_pattern', []))} 筆",
            f"- L4 互動年輪：{len(layers.get('L4_interaction_rings', []))} 筆",
            f"- L5 偏好結晶：{len(layers.get('L5_preference_crystals', []))} 筆",
        ])

        l6 = layers.get("L6_communication_style", {})
        if l6:
            lines.append(f"- L6 溝通風格：tone={l6.get('tone')}, detail={l6.get('detail_level')}, emoji={l6.get('emoji_usage')}")

        lines.append(f"- L7 情境角色：{len(layers.get('L7_context_roles', []))} 筆")
        lines.append("")

        return "\n".join(lines)
