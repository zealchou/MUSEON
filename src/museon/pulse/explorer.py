"""Explorer — 自主探索引擎.

VITA 的好奇心驅動模組。
基於使命、好奇心、互動觀察，主動外出探索世界。
每次探索：SearXNG 搜尋 → Haiku 篩選 → 有價值則 Sonnet 深度分析 → 結晶。
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import re

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# 探索預算（預設值，PI-2 熱更新時由 pulse_config.json 覆蓋）
MAX_COST_PER_EXPLORATION = 0.50  # USD
MAX_EXPLORATIONS_PER_DAY = 3
MAX_DAILY_COST = 1.50  # USD

# 模型
SCOUT_MODEL = "claude-haiku-4-5-20251001"      # 初步篩選
DEEP_MODEL = "claude-sonnet-4-20250514"       # 深度分析（僅有價值時）


# PI-2 熱更新讀取器
def _cfg(key: str, default: Any = None) -> Any:
    """從 pulse_config.json 讀取 explorer 區段的配置（PI-2 熱更新）."""
    try:
        from museon.pulse.pulse_intervention import get_config
        return get_config("explorer", key, default)
    except Exception:
        return default

_SCOUT_SYSTEM = """你是 MUSEON 的探索偵察模組。你的任務是快速評估搜尋結果的價值。

給你一個搜尋主題和搜尋結果摘要，請判斷：
1. 這些結果中有沒有真正有價值的新知？
2. 如果有，用 3-5 句話提煉核心洞見。
3. 如果沒有，回覆「NO_VALUE」。

評判標準：
- 是否能幫助使用者（達達把拔）？
- 是否能讓霓裳學到新東西？
- 是否有足夠的深度值得進一步探索？
"""

_DEEP_SYSTEM = """你是 MUSEON 的深度探索模組，同時也是一位 HBR 等級的分析記者。
基於偵察報告，進行深度分析，產出具有個案研討深度的探索報告。

【重要格式規定】請嚴格使用以下 ## section 標記，報告生成器將依此解析渲染：

## 核心發現

用「個案研討」的敘事方式描述 1-3 個最重要的洞見。
寫作規則：
- 從一個真實場景或具體數據切入，而不是開門見山給結論
- 每個洞見需要有反差或出乎意料的元素
- 描述這個發現改變了什麼認知，讓讀者產生「原來如此」的感受
- 用具體而非抽象的語言（有名稱、有數字、有場景）

## 深度解析

選擇最重要的發現，像分析記者一樣展開：
- **機制**：它是怎麼運作的？（技術/方法論的底層邏輯）
- **證據**：哪些真實案例或數據支撐這個判斷？
- **盲點**：哪裡可能有誤判？有什麼條件限制？
- **連結**：這個發現跟哪個你意想不到的領域有關？

## 與使用者的關聯

這些發現如何具體幫助 Zeal（MUSEON 創辦人，AI 顧問，服務台灣中小企業）？
- 用 2-3 個具體應用場景說明，要說得出「在哪個具體工作環節有用」
- 不要泛泛而談，每一句話都要有行動指向

## 霓裳的成長收穫

這次探索讓 MUSEON AI 學到了什麼新能力或新認知？
- 哪個認知模型被更新或強化了？
- 未來哪類問題能因此處理得更好？

## 結晶判斷

這個發現是否值得結晶到知識晶格？
- **判斷**：值得 / 不值得（直接說）
- **如果值得**：建議的結晶標題（15字內）+ 核心摘要（3句話內）
- **理由**：為什麼做這個判斷

## 下一步探索

基於這次發現，最高槓桿的下一步探索方向：
- 說出具體主題（不要說「進一步研究」這種廢話）
- 說清楚為什麼這個方向能最大化本次探索的複利效應

目標字數：800-1500 字。每句話要有信息量，不要水。
"""


class Explorer:
    """自主探索引擎 — 霓裳的好奇心."""

    def __init__(
        self,
        brain: Any = None,
        data_dir: str = "",
        searxng_url: str = "http://127.0.0.1:8888",
    ) -> None:
        self._brain = brain
        self._data_dir = data_dir
        self._searxng_url = searxng_url
        self._exploration_log_path = Path(data_dir) / "exploration_log.md" if data_dir else None

    async def explore(
        self,
        topic: str,
        motivation: str = "curiosity",
    ) -> Dict[str, Any]:
        """執行一次自主探索.

        Args:
            topic: 探索主題
            motivation: 動機 (curiosity/mission/skill/world/self)

        Returns:
            探索結果字典
        """
        start = time.monotonic()
        result = {
            "topic": topic,
            "motivation": motivation,
            "query": "",
            "findings": "",
            "crystallized": False,
            "crystal_id": "",
            "tokens_used": 0,
            "cost_usd": 0.0,
            "duration_ms": 0,
            "status": "exploring",
            "deep_analysis": False,
            "depth_level": 1,
            "duplicate_check": {},
        }

        # Step 0: 去重檢查
        dup_check = self._check_duplicate(topic)
        result["duplicate_check"] = dup_check

        if dup_check["status"] == "reject":
            result["findings"] = dup_check["message"]
            result["status"] = "rejected"
            result["duration_ms"] = int((time.monotonic() - start) * 1000)
            return result

        # 如果是重複探索，提升深度等級
        if dup_check["status"] == "allow_deeper":
            result["depth_level"] = dup_check["depth_level"]
            logger.info(f"探索「{topic}」：第 {result['depth_level']} 層深度")

        try:
            # Step 1: SearXNG 搜尋
            search_results = await self._search(topic)
            result["query"] = topic

            if not search_results:
                result["findings"] = "搜尋無結果"
                result["status"] = "done"
                result["duration_ms"] = int((time.monotonic() - start) * 1000)
                return result

            # Step 2: Haiku 快速篩選
            scout_report = await self._scout(topic, search_results)
            result["tokens_used"] += scout_report.get("tokens", 0)
            result["cost_usd"] += scout_report.get("cost", 0)

            if scout_report.get("verdict") == "NO_VALUE":
                result["findings"] = f"搜尋了「{topic}」但未發現有價值的新知"
                result["status"] = "done"
                result["duration_ms"] = int((time.monotonic() - start) * 1000)
                return result

            # Step 3: 有價值 → 考慮深度分析
            findings = scout_report.get("summary", "")
            result["findings"] = findings

            # 如果成本預算允許，進行 Sonnet 深度分析
            max_cost = _cfg("max_cost_per_exploration", MAX_COST_PER_EXPLORATION)
            remaining_budget = max_cost - result["cost_usd"]
            if remaining_budget > 0.10 and self._brain:
                deep_report = await self._deep_analyze(topic, findings, motivation)
                result["tokens_used"] += deep_report.get("tokens", 0)
                result["cost_usd"] += deep_report.get("cost", 0)
                result["findings"] = deep_report.get("analysis", findings)
                result["deep_analysis"] = True

                # 結晶建議
                if deep_report.get("should_crystallize"):
                    result["crystallized"] = True
                    # 實際結晶由 PulseEngine 負責

            result["status"] = "done"
            # 記錄探索完成
            self._log_exploration(topic, motivation, result)
        except Exception as e:
            logger.error(f"Exploration failed: {e}")
            result["findings"] = f"探索失敗: {e}"
            result["status"] = "failed"

        result["duration_ms"] = int((time.monotonic() - start) * 1000)
        return result

    async def _search(self, query: str) -> str:
        """透過 SearXNG 搜尋."""
        try:
            import aiohttp
            params = {
                "q": query,
                "format": "json",
                "language": "zh-TW",
                "categories": "general",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._searxng_url}/search",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return ""
                    data = await resp.json()
                    results = data.get("results", [])[:5]
                    summaries = []
                    for r in results:
                        title = r.get("title", "")
                        content = r.get("content", "")[:200]
                        url = r.get("url", "")
                        summaries.append(f"- {title}: {content} ({url})")
                    return "\n".join(summaries)
        except Exception as e:
            logger.warning(f"SearXNG search failed: {e}")
            return ""

    async def _scout(self, topic: str, search_results: str) -> Dict:
        """Haiku 快速篩選搜尋結果."""
        if not self._brain or not hasattr(self._brain, "_call_llm_with_model"):
            return {"verdict": "NO_VALUE", "tokens": 0, "cost": 0}

        prompt = f"搜尋主題：{topic}\n\n搜尋結果：\n{search_results}"
        try:
            scout_model = _cfg("scout_model", SCOUT_MODEL)
            response = await self._brain._call_llm_with_model(
                system_prompt=_SCOUT_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                model=scout_model,
                max_tokens=300,
            )
            is_no_value = "NO_VALUE" in response
            # Haiku 成本估算：~500 input + 300 output tokens
            tokens = 800
            cost = tokens * 0.25 / 1_000_000  # Haiku pricing ~$0.25/MTok input
            return {
                "verdict": "NO_VALUE" if is_no_value else "VALUABLE",
                "summary": response if not is_no_value else "",
                "tokens": tokens,
                "cost": cost,
            }
        except Exception as e:
            logger.error(f"Scout failed: {e}")
            return {"verdict": "NO_VALUE", "tokens": 0, "cost": 0}

    async def _deep_analyze(
        self, topic: str, scout_summary: str, motivation: str,
    ) -> Dict:
        """Sonnet 深度分析."""
        if not self._brain or not hasattr(self._brain, "_call_llm_with_model"):
            return {"analysis": scout_summary, "tokens": 0, "cost": 0, "should_crystallize": False}

        prompt = (
            f"探索主題：{topic}\n"
            f"動機：{motivation}\n"
            f"偵察報告：{scout_summary}\n\n"
            f"請進行深度分析。"
        )
        try:
            deep_model = _cfg("deep_model", DEEP_MODEL)
            response = await self._brain._call_llm_with_model(
                system_prompt=_DEEP_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                model=deep_model,
                max_tokens=2500,
            )
            # Sonnet 成本估算：~1000 input + 2500 output tokens
            tokens = 3500
            cost = tokens * 3.0 / 1_000_000  # Sonnet pricing ~$3/MTok input
            should_crystallize = "值得結晶" in response or "建議結晶" in response
            return {
                "analysis": response,
                "tokens": tokens,
                "cost": cost,
                "should_crystallize": should_crystallize,
            }
        except Exception as e:
            logger.error(f"Deep analysis failed: {e}")
            return {"analysis": scout_summary, "tokens": 0, "cost": 0, "should_crystallize": False}

    # ── 去重與深度遞進 ──

    def _check_duplicate(self, topic: str) -> Dict[str, Any]:
        """檢查是否重複探索，並判斷是否允許及應走的深度.

        Returns:
            {
                "status": "allow" | "allow_deeper" | "ask" | "reject",
                "message": "拒絕或提示信息",
                "depth_level": 1 | 2 | 3,  # 遞進深度
                "last_explored": "2026-03-23 10:02" | None,
                "days_since": 整數 或 None,
            }
        """
        log_data = self._load_exploration_log()

        # 搜尋歷史記錄（使用語意相似度比對，不再只做精確匹配）
        history = [
            entry for entry in log_data.get("history", [])
            if self._topics_similar(entry["topic"], topic)
        ]

        if not history:
            return {
                "status": "allow",
                "message": "新主題，允許探索",
                "depth_level": 1,
                "last_explored": None,
                "days_since": None,
            }

        last_entry = history[-1]
        last_time = datetime.fromisoformat(last_entry["timestamp"])
        today = datetime.now(TZ8).replace(hour=0, minute=0, second=0, microsecond=0)
        last_date = last_time.astimezone(TZ8).replace(hour=0, minute=0, second=0, microsecond=0)
        days_since = (today - last_date).days

        depth_count = last_entry.get("depth_count", 1)

        # 規則判斷
        if depth_count >= 4:
            return {
                "status": "reject",
                "message": f"此主題已探索 {depth_count} 次，達上限。建議結晶為知識或選擇新主題。",
                "depth_level": depth_count,
                "last_explored": last_time.isoformat(),
                "days_since": days_since,
            }

        if days_since <= 3 and depth_count >= 2:
            return {
                "status": "reject",
                "message": f"最近 {days_since} 天已探索此主題 {depth_count} 次，建議新主題或等待。",
                "depth_level": depth_count,
                "last_explored": last_time.isoformat(),
                "days_since": days_since,
            }

        if days_since == 0:
            # 同天允許但深度遞進
            next_depth = depth_count + 1
            return {
                "status": "allow_deeper",
                "message": f"同天重複，進行第 {next_depth} 層深度探索",
                "depth_level": next_depth,
                "last_explored": last_time.isoformat(),
                "days_since": 0,
            }

        if days_since < 7:
            return {
                "status": "ask",
                "message": f"同週期主題（{days_since} 天前探索過），要深化哪個角度嗎？",
                "depth_level": depth_count,
                "last_explored": last_time.isoformat(),
                "days_since": days_since,
            }

        # 超過 7 天，允許新一輪探索
        return {
            "status": "allow",
            "message": f"距上次探索 {days_since} 天，允許新一輪探索",
            "depth_level": 1,
            "last_explored": last_time.isoformat(),
            "days_since": days_since,
        }

    def _normalize_topic(self, topic: str) -> str:
        """規範化主題（用於比對）."""
        # 移除標點、統一空白、轉小寫
        normalized = re.sub(r"[^\w\s]", "", topic).lower().strip()
        # 多個空白化為單一空白
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _topics_similar(self, a: str, b: str) -> bool:
        """判斷兩個主題是否語意相似（多策略比對）.

        策略：
        1. 精確匹配（normalize 後）
        2. 字元級 n-gram 重疊（處理中文無空格的情況）
        3. 關鍵詞重疊（空格分詞 + 中文 bigram）
        """
        norm_a = self._normalize_topic(a)
        norm_b = self._normalize_topic(b)

        # 策略 1: 精確匹配
        if norm_a == norm_b:
            return True

        # 策略 2: 包含關係（短的被長的完全包含）
        if len(norm_a) > 4 and len(norm_b) > 4:
            if norm_a in norm_b or norm_b in norm_a:
                return True

        # 策略 3: 字元級 bigram 重疊（Dice 係數 > 0.5）
        bigrams_a = set(norm_a[i:i+2] for i in range(len(norm_a) - 1) if not norm_a[i].isspace())
        bigrams_b = set(norm_b[i:i+2] for i in range(len(norm_b) - 1) if not norm_b[i].isspace())
        if bigrams_a and bigrams_b:
            dice = 2 * len(bigrams_a & bigrams_b) / (len(bigrams_a) + len(bigrams_b))
            if dice > 0.5:
                return True

        # 策略 4: 空格分詞的關鍵詞重疊（> 50%）
        words_a = set(norm_a.split())
        words_b = set(norm_b.split())
        if words_a and words_b:
            overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
            if overlap > 0.5:
                return True

        return False

    def _load_exploration_log(self) -> Dict[str, Any]:
        """讀取探索日誌 Markdown 並解析."""
        if not self._exploration_log_path or not self._exploration_log_path.exists():
            return {"history": []}

        try:
            with open(self._exploration_log_path, "r", encoding="utf-8") as f:
                content = f.read()

            history = []
            current_date = None  # 從 ## YYYY-MM-DD 段落標題取得日期上下文
            lines = content.split("\n")
            in_table = False

            for line in lines:
                # 偵測日期段落標題（## 2026-03-23）
                date_match = re.match(r"^##\s+(\d{4}-\d{2}-\d{2})", line)
                if date_match:
                    current_date = date_match.group(1)
                    in_table = False
                    continue

                if line.startswith("|") and "時間" in line:
                    in_table = True
                    continue
                if not in_table or not line.startswith("|"):
                    if in_table and not line.startswith("|"):
                        in_table = False
                    continue
                if "---" in line:  # 跳過分隔線
                    continue

                parts = [p.strip() for p in line.split("|")[1:-1]]
                if len(parts) < 6:
                    continue

                try:
                    raw_ts = parts[0]
                    # 嘗試完整 ISO 解析
                    try:
                        ts = datetime.fromisoformat(raw_ts)
                    except (ValueError, TypeError):
                        # 舊格式 HH:MM — 用段落標題日期補全
                        if current_date and re.match(r"^\d{1,2}:\d{2}$", raw_ts):
                            ts = datetime.fromisoformat(f"{current_date}T{raw_ts}:00+08:00")
                        else:
                            continue  # 無法解析，跳過

                    history.append({
                        "timestamp": ts.isoformat(),
                        "topic": parts[1],
                        "motivation": parts[2],
                        "depth_count": int(parts[3]),
                        "status": parts[4],
                        "crystallized": parts[5].lower() == "yes",
                    })
                except (ValueError, IndexError):
                    continue

            return {"history": history}
        except Exception as e:
            logger.warning(f"Failed to load exploration log: {e}")
            return {"history": []}

    def _log_exploration(self, topic: str, motivation: str, result: Dict[str, Any]) -> None:
        """記錄探索結果到日誌."""
        if not self._exploration_log_path:
            return

        try:
            log_data = self._load_exploration_log()
            normalized = self._normalize_topic(topic)
            history = log_data.get("history", [])

            # 計算深度等級
            last_same = None
            for entry in reversed(history):
                if self._topics_similar(entry["topic"], topic):
                    last_same = entry
                    break

            if last_same:
                last_time = datetime.fromisoformat(last_same["timestamp"])
                today = datetime.now(TZ8).replace(hour=0, minute=0, second=0, microsecond=0)
                last_date = last_time.astimezone(TZ8).replace(hour=0, minute=0, second=0, microsecond=0)
                if (today - last_date).days == 0:
                    depth_count = last_same.get("depth_count", 1) + 1
                else:
                    depth_count = 1
            else:
                depth_count = 1

            now = datetime.now(TZ8)
            # 使用完整 ISO 時間戳（含日期），確保 _load_exploration_log 能正確解析
            ts_iso = now.isoformat(timespec="seconds")

            # 新增紀錄
            new_entry = f"| {ts_iso} | {topic} | {motivation} | {depth_count} | {result['status']} | {'yes' if result.get('crystallized') else 'no'} |"

            # 找到日期分段，追加
            with open(self._exploration_log_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 簡單邏輯：在第一個表格結束後插入
            lines = content.split("\n")
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("|") and "時間" in line:
                    # 找到表格結束
                    for j in range(i + 1, len(lines)):
                        if not lines[j].startswith("|"):
                            insert_idx = j
                            break
                    break

            if insert_idx > 0:
                lines.insert(insert_idx, new_entry)
                with open(self._exploration_log_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))

                logger.info(f"Exploration logged: {topic} (depth {depth_count})")
        except Exception as e:
            logger.error(f"Failed to log exploration: {e}")
