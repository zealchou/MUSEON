"""Router - Smart model selection between Opus, Sonnet, and Haiku.

v2: 加入中文模式識別 + 路由統計記錄 + Nightly 覆寫支援。
v3: MAX 訂閱方案 — 保留 classify() 供分析統計，模型選擇功能簡化。
v4: 三層路由 — Opus 4.6（複雜）→ Sonnet 4（中等）→ Haiku 4.5（簡單）。
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class Router:
    """
    Router classifies incoming messages and decides whether to use Haiku or Sonnet.

    Default: Sonnet (smarter, more capable)
    Downgrade to Haiku when:
    - Message is short AND matches Haiku-eligible pattern
    - No active skills in session context
    - Nightly 優化引擎尚未將此 task type 標為 Sonnet-only
    """

    MODEL_OPUS = "claude-opus-4-6"
    MODEL_SONNET = "claude-sonnet-4-20250514"
    MODEL_HAIKU = "claude-haiku-4-5-20251001"

    # Patterns that can be handled by Haiku（中英文皆涵蓋）
    HAIKU_PATTERNS = [
        # English
        (r"^(hello|hi|hey|good morning|good afternoon|good evening)(!|\s|$)", "simple_greeting"),
        (r"(what('?s| is) (the )?(time|weather|date|temperature))", "simple_query"),
        (r"^(yes|no|ok|okay|sure|thanks|thank you)(!|\.|\s|$)", "simple_ack"),
        # 中文 — 日常問候
        (r"^(你好|嗨|哈囉|早安|午安|晚安|嘿|哈嘍|安安)(!|！|$|\s)", "simple_greeting"),
        # 中文 — 簡短確認/致謝/應答
        (r"^(好的?|了解|收到|謝謝|感謝|知道了|OK|ok|嗯|嗯嗯|對|沒問題|沒事|可以|行|不用|不了|好啊|好哦|好喔|好唷|是的|算了|隨便|都可以|都行|沒差|可啊|好吧|懂了|明白|OK啦|okok)(!|！|。|$|\s)", "simple_ack"),
        # 中文 — 告別
        (r"^(晚安|掰掰|拜拜|再見|bye|88|886|掰|走了|先這樣)(!|！|$|\s)", "simple_farewell"),
        # 中文 — 簡單查詢
        (r"^.{0,6}(幾點|天氣|幾度|溫度|日期|星期幾)", "simple_query"),
        # 中文 — 情緒表達/閒聊
        (r"^(哈哈|嘻嘻|XD|xd|笑死|讚|👍|❤️|😊|🎉|😂|🤣|哈+|呵呵|嘿嘿|hihi)(!|！|$|\s)", "simple_emoji"),
        # 中文 — 簡短反應
        (r"^(真的嗎|是喔|喔喔|原來|哦|蛤|欸|不會吧|天啊|傻眼|無言|厲害|猛)(!|！|$|\s|？)", "simple_reaction"),
    ]

    # Keywords that require complex model (Opus)（中英文皆涵蓋）
    # P3: v4 三層路由後，這些關鍵字路由到 Opus 而非 Sonnet
    COMPLEX_KEYWORDS = [
        # English
        "write", "create", "generate", "compose", "draft",
        "business", "revenue", "marketing", "strategy", "profit", "customer",
        "brand", "story", "campaign", "content",
        "analyze", "evaluate", "review", "assess", "diagnose",
        "help me", "need advice", "what should i",
        # 中文
        "幫我", "幫忙", "請問", "分析", "規劃", "建議",
        "寫", "撰寫", "草擬", "企劃", "報告", "策略",
        "品牌", "行銷", "銷售", "客戶", "商業", "營收",
        "診斷", "設計", "評估", "研究", "深入", "思考",
        "解釋", "為什麼", "怎麼", "如何",
    ]

    def __init__(self, data_dir: Optional[str] = None):
        self._data_dir = Path(data_dir) if data_dir else None
        # Nightly 覆寫規則（task_type → model）
        self._overrides: Dict[str, str] = {}
        self._load_overrides()

    def _load_overrides(self) -> None:
        """載入 Nightly 優化引擎的覆寫規則."""
        if not self._data_dir:
            return
        fp = self._data_dir / "_system" / "budget" / "router_overrides.json"
        if fp.exists():
            try:
                self._overrides = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                self._overrides = {}

    def classify(
        self, message: str, session_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Classify message and decide which model to use.

        Returns:
            Dict with keys: model ("haiku" | "sonnet"), reason (str), task_type (str)
        """
        session_context = session_context or {}
        message_lower = message.lower().strip()

        # Rule 0: Nightly 覆寫（已驗證可以用 Haiku 的 task type）
        # 保留供未來使用

        # Rule 1: tool_use 相關任務 → Opus（需要工具的複雜任務）
        if session_context.get("pending_tool_use"):
            return {"model": "opus", "reason": "tool_use", "task_type": "tool"}

        # Rule 2: Haiku-eligible patterns（優先檢查，短句直接分流）
        for pattern, task_type in self.HAIKU_PATTERNS:
            if re.search(pattern, message_lower, re.IGNORECASE):
                return {"model": "haiku", "reason": pattern[:30], "task_type": task_type}

        # Rule 3: Opus keywords（複雜意圖關鍵字 → Opus）
        for keyword in self.COMPLEX_KEYWORDS:
            if keyword in message_lower:
                return {"model": "opus", "reason": f"kw:{keyword}", "task_type": "complex"}

        # Rule 4: 長度檢查 — 中文 300 字以上走 Opus
        char_count = len(message)
        if char_count > 300:
            return {"model": "opus", "reason": "msg_too_long", "task_type": "complex"}

        # Rule 4a: 修正/否定模式 → Haiku（使用者反饋類簡單應答）
        _CORRECTION_STARTS = [
            "不是", "不對", "其實", "但是", "可是", "應該是",
            "改成", "換一個", "重新", "再想想", "別的",
            "好的", "了解", "收到", "對", "沒錯", "嗯",
        ]
        if any(message_lower.startswith(p) for p in _CORRECTION_STARTS):
            return {"model": "haiku", "reason": "correction_pattern", "task_type": "clarification"}

        # Rule 4b: 簡單問答模式 → Haiku
        _SIMPLE_QA = [
            "幾點", "什麼時候", "在哪裡", "多少錢", "怎麼說",
            "你叫什麼", "是什麼意思", "翻譯", "怎麼念",
        ]
        if char_count <= 30 and any(p in message_lower for p in _SIMPLE_QA):
            return {"model": "haiku", "reason": "simple_qa", "task_type": "qa"}

        # Rule 5: 超短訊息（≤ 20 字）且沒命中任何規則 → Haiku
        if char_count <= 20:
            return {"model": "haiku", "reason": "ultra_short", "task_type": "simple_ack"}

        # Rule 6: 中等長度（21-300 字）且無複雜關鍵字 → Sonnet
        # 日常閒聊不需要 Opus 但也不該用 Haiku
        return {"model": "sonnet", "reason": "casual_chat", "task_type": "chat"}

    def get_model_id(self, model_label: str) -> str:
        """Convert 'haiku'/'sonnet'/'opus' to full model ID."""
        if model_label == "haiku":
            return self.MODEL_HAIKU
        if model_label == "sonnet":
            return self.MODEL_SONNET
        return self.MODEL_OPUS

    # ── 路由統計記錄 ──

    def record_routing(
        self,
        data_dir: Path,
        model_used: str,
        task_type: str,
        reason: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        q_score: Optional[float] = None,
    ) -> None:
        """記錄一筆路由統計到磁碟，供 Nightly 分析."""
        stats_dir = data_dir / "_system" / "budget"
        stats_dir.mkdir(parents=True, exist_ok=True)

        today_str = datetime.now().strftime("%Y-%m-%d")
        fp = stats_dir / f"routing_log_{today_str}.jsonl"

        entry = {
            "ts": datetime.now().isoformat(),
            "model": model_used,
            "task_type": task_type,
            "reason": reason,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "q_score": q_score,
        }
        try:
            with open(fp, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"路由統計寫入失敗: {e}")
