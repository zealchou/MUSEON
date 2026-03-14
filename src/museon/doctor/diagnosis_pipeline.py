"""DiagnosisPipeline — 三層診斷管線.

三層架構（逐層升級，節省 Token）：
  D1: 靜態分析（CPU）— CodeAnalyzer AST 規則掃描
  D2: 動態探測（CPU）— LogAnalyzer 日誌異常 + HeartbeatEngine 狀態
  D3: LLM 輔助（Token）— 僅當 D1/D2 發現問題時觸發，分析根因並生成修復提案
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from museon.doctor.code_analyzer import CodeAnalyzer, CodeIssue
from museon.doctor.log_analyzer import LogAnalyzer, LogAnomaly

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# DiagnosisResult
# ═══════════════════════════════════════════


@dataclass
class SurgeryProposal:
    """D3 LLM 產生的修復提案."""

    title: str
    description: str
    affected_files: List[str]
    changes: List[Dict[str, str]]  # [{"file": ..., "old": ..., "new": ...}]
    confidence: float = 0.0  # 0.0 ~ 1.0
    risk_level: str = "low"  # "low" | "medium" | "high"


@dataclass
class DiagnosisResult:
    """診斷結果."""

    # D1 靜態分析
    code_issues: List[CodeIssue] = field(default_factory=list)

    # D2 動態探測
    log_anomalies: List[LogAnomaly] = field(default_factory=list)

    # D3 LLM 分析
    root_cause: str = ""
    proposals: List[SurgeryProposal] = field(default_factory=list)

    # 元資料
    diagnosis_level: str = ""  # "D1" | "D2" | "D3"
    summary: str = ""

    @property
    def has_issues(self) -> bool:
        return bool(self.code_issues) or bool(self.log_anomalies)

    @property
    def critical_count(self) -> int:
        c1 = sum(1 for i in self.code_issues if i.severity == "critical")
        c2 = sum(1 for a in self.log_anomalies if a.severity == "critical")
        return c1 + c2


# ═══════════════════════════════════════════
# LLM Adapter Protocol（避免直接耦合）
# ═══════════════════════════════════════════


@runtime_checkable
class DiagnosisLLM(Protocol):
    """診斷用 LLM 介面."""

    async def call(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        model: str = "sonnet",
        max_tokens: int = 8192,
        tools: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
    ) -> Any:
        ...


# ═══════════════════════════════════════════
# DiagnosisPipeline
# ═══════════════════════════════════════════


_D3_SYSTEM_PROMPT = """\
你是 MUSEON 的內部診斷引擎。你的任務是分析程式碼問題的根因，並提出精確的修復方案。

規則：
1. 只修改必要的程式碼，不做不相關的重構
2. 每個修復方案必須包含明確的 old_text 和 new_text
3. 不可修改以下檔案：morphenix_standards.py, morphenix_executor.py, kernel_guard.py, drift_detector.py, safety_anchor.py
4. 不可在程式碼中硬編碼密鑰或 token
5. 修復方案的 confidence 必須誠實評估

回應格式（JSON）：
{
  "root_cause": "問題根因描述",
  "proposals": [
    {
      "title": "修復標題",
      "description": "修復描述",
      "affected_files": ["path/to/file.py"],
      "changes": [
        {"file": "path/to/file.py", "old": "原始碼", "new": "修改後"}
      ],
      "confidence": 0.85,
      "risk_level": "low"
    }
  ]
}
"""


class DiagnosisPipeline:
    """三層診斷管線.

    D1 → D2 → D3（逐層升級）
    """

    def __init__(
        self,
        source_root: Optional[Path] = None,
        logs_dir: Optional[Path] = None,
        heartbeat_state_path: Optional[Path] = None,
        llm_adapter: Optional[DiagnosisLLM] = None,
    ):
        self._source_root = source_root or Path("src/museon")
        self._code_analyzer = CodeAnalyzer(source_root=self._source_root)
        self._log_analyzer = LogAnalyzer(
            logs_dir=logs_dir,
            heartbeat_state_path=heartbeat_state_path,
        )
        self._llm = llm_adapter

    async def run(
        self,
        skip_d3: bool = False,
        target_files: Optional[List[Path]] = None,
        target_rules: Optional[List[str]] = None,
    ) -> DiagnosisResult:
        """執行診斷管線.

        Args:
            skip_d3: 跳過 D3 LLM 分析（省 Token，用於定期掃描）
            target_files: 限定掃描的檔案（None = 掃描全部）
            target_rules: 限定執行的規則 ID
        """
        result = DiagnosisResult()

        # ── D1: 靜態分析（CPU-bound → to_thread 避免阻塞 event loop）──
        import asyncio
        logger.info("DiagnosisPipeline: D1 靜態分析開始")
        if target_files:
            for f in target_files:
                if target_rules:
                    issues = await asyncio.to_thread(
                        self._code_analyzer.scan_specific_rules, f, target_rules
                    )
                else:
                    issues = await asyncio.to_thread(
                        self._code_analyzer.scan_file, f
                    )
                result.code_issues.extend(issues)
        else:
            result.code_issues = await asyncio.to_thread(
                self._code_analyzer.scan_all
            )
        result.diagnosis_level = "D1"
        logger.info(
            f"DiagnosisPipeline: D1 完成 — {len(result.code_issues)} 個問題"
        )

        # ── D2: 動態探測（CPU-bound → to_thread）──
        logger.info("DiagnosisPipeline: D2 動態探測開始")
        result.log_anomalies = await asyncio.to_thread(
            self._log_analyzer.analyze, lookback_hours=24
        )
        result.diagnosis_level = "D2"
        logger.info(
            f"DiagnosisPipeline: D2 完成 — {len(result.log_anomalies)} 個異常"
        )

        # ── D3: LLM 輔助（僅在有問題且有 LLM 時觸發）──
        if not skip_d3 and result.has_issues and self._llm:
            logger.info("DiagnosisPipeline: D3 LLM 分析開始")
            try:
                d3_result = await self._run_d3(result)
                result.root_cause = d3_result.get("root_cause", "")
                result.proposals = self._parse_proposals(
                    d3_result.get("proposals", [])
                )
                result.diagnosis_level = "D3"
                logger.info(
                    f"DiagnosisPipeline: D3 完成 — "
                    f"{len(result.proposals)} 個修復提案"
                )
            except Exception as e:
                logger.error(f"DiagnosisPipeline: D3 失敗: {e}")
                result.diagnosis_level = "D2"  # 降級

        # 摘要
        result.summary = self._build_summary(result)

        # 發佈 EventBus 事件
        try:
            from museon.core.event_bus import (
                get_event_bus,
                SELF_DIAGNOSIS_COMPLETED,
            )
            get_event_bus().publish(SELF_DIAGNOSIS_COMPLETED, {
                "diagnosis_level": result.diagnosis_level,
                "has_issues": result.has_issues,
                "code_issues_count": len(result.code_issues),
                "log_anomalies_count": len(result.log_anomalies),
                "proposals_count": len(result.proposals),
            })
        except Exception as e:
            logger.debug(f"[DIAGNOSIS_PIPELINE] diagnosis failed (degraded): {e}")

        return result

    async def _run_d3(self, result: DiagnosisResult) -> Dict[str, Any]:
        """D3: 呼叫 LLM 分析根因."""
        # 構建上下文
        context_parts = []

        if result.code_issues:
            context_parts.append("## 靜態分析發現的問題\n")
            for issue in result.code_issues[:20]:  # 限制數量避免 Token 爆炸
                context_parts.append(
                    f"- [{issue.rule_id}] {issue.file_path}:{issue.line} "
                    f"— {issue.message}"
                )
                if issue.context:
                    context_parts.append(f"  程式碼: `{issue.context}`")

        if result.log_anomalies:
            context_parts.append("\n## 日誌異常\n")
            for anomaly in result.log_anomalies[:10]:
                context_parts.append(
                    f"- [{anomaly.anomaly_type}] {anomaly.message}"
                )

        # 讀取相關檔案的源碼（供 LLM 分析）
        source_context = await self._read_relevant_sources(result)
        if source_context:
            context_parts.append("\n## 相關原始碼\n")
            context_parts.append(source_context)

        user_message = "\n".join(context_parts)

        response = await self._llm.call(
            system_prompt=_D3_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            model="sonnet",
            max_tokens=4096,
        )

        # 解析 JSON 回應
        text = response.text if hasattr(response, "text") else str(response)
        return self._extract_json(text)

    async def _read_relevant_sources(
        self, result: DiagnosisResult
    ) -> str:
        """讀取問題相關的源碼片段."""
        files_to_read = set()
        for issue in result.code_issues[:10]:
            files_to_read.add(issue.file_path)

        parts = []
        for file_path in list(files_to_read)[:5]:  # 最多 5 個檔案
            try:
                path = Path(file_path)
                if not path.exists():
                    continue
                source = path.read_text(encoding="utf-8")
                lines = source.splitlines()
                # 截取前 200 行或全部（取較小者）
                excerpt = "\n".join(lines[:200])
                parts.append(f"### {file_path}\n```python\n{excerpt}\n```\n")
            except Exception as e:
                logger.debug(f"[DIAGNOSIS_PIPELINE] data read failed (degraded): {e}")
        return "\n".join(parts)

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """從 LLM 回應中提取 JSON."""
        # 嘗試找 JSON 區塊
        import re
        json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError as e:
                logger.debug(f"[DIAGNOSIS_PIPELINE] JSON failed (degraded): {e}")

        # 嘗試直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.debug(f"[DIAGNOSIS_PIPELINE] JSON failed (degraded): {e}")

        # 嘗試找任何 JSON 物件
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start:brace_end + 1])
            except json.JSONDecodeError as e:
                logger.debug(f"[DIAGNOSIS_PIPELINE] JSON failed (degraded): {e}")

        logger.warning("DiagnosisPipeline: 無法從 LLM 回應中提取 JSON")
        return {"root_cause": text[:500], "proposals": []}

    @staticmethod
    def _parse_proposals(
        raw_proposals: List[Dict[str, Any]],
    ) -> List[SurgeryProposal]:
        """解析 LLM 的修復提案."""
        proposals = []
        for raw in raw_proposals:
            try:
                proposals.append(SurgeryProposal(
                    title=raw.get("title", "未命名提案"),
                    description=raw.get("description", ""),
                    affected_files=raw.get("affected_files", []),
                    changes=raw.get("changes", []),
                    confidence=float(raw.get("confidence", 0.0)),
                    risk_level=raw.get("risk_level", "medium"),
                ))
            except Exception as e:
                logger.warning(f"DiagnosisPipeline: 提案解析失敗: {e}")
        return proposals

    @staticmethod
    def _build_summary(result: DiagnosisResult) -> str:
        """建構診斷摘要."""
        parts = [f"診斷層級: {result.diagnosis_level}"]

        if result.code_issues:
            critical = sum(1 for i in result.code_issues if i.severity == "critical")
            warning = sum(1 for i in result.code_issues if i.severity == "warning")
            parts.append(f"靜態分析: {critical} critical, {warning} warning")

        if result.log_anomalies:
            parts.append(f"日誌異常: {len(result.log_anomalies)} 個")

        if result.root_cause:
            parts.append(f"根因: {result.root_cause[:100]}")

        if result.proposals:
            parts.append(f"修復提案: {len(result.proposals)} 個")

        return " | ".join(parts)
