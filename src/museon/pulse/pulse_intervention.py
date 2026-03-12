"""Pulse Intervention (PI) — Morphenix 對 Pulse 的三級介入系統.

PI-1（觀察介入）：讀取 Pulse 行為日誌，產出觀察報告供 Morphenix 結晶
PI-2（參數熱更新）：Morphenix 可寫入 pulse_config.json，Pulse 讀取生效
PI-3（行為注入）：Morphenix 生成新觸發規則，帶損失函數護欄

架構原則：
  - PI 層級與 Morphenix 既有 L1/L2/L3（程式碼變更分級）完全獨立
  - pulse_config.json 是 PI-2 的唯一接口
  - PI-3 需要損失函數 + 品質門禁 + 自動回滾三重護欄
"""

import json
import logging
import math
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# PI 配置讀取器（PI-2 核心）
# ═══════════════════════════════════════════

_CONFIG_PATH: Optional[Path] = None
_CONFIG_CACHE: Dict[str, Any] = {}
_CONFIG_MTIME: float = 0.0


def init_config(data_dir: str) -> None:
    """初始化配置路徑（Gateway 啟動時呼叫一次）."""
    global _CONFIG_PATH
    _CONFIG_PATH = Path(data_dir) / "_system" / "pulse_config.json"
    _reload_config()


def _reload_config() -> None:
    """重新載入配置（檔案修改時間變更才讀取）."""
    global _CONFIG_CACHE, _CONFIG_MTIME
    if _CONFIG_PATH is None or not _CONFIG_PATH.exists():
        return
    try:
        mtime = _CONFIG_PATH.stat().st_mtime
        if mtime != _CONFIG_MTIME:
            _CONFIG_CACHE = json.loads(
                _CONFIG_PATH.read_text(encoding="utf-8")
            )
            _CONFIG_MTIME = mtime
            logger.debug("PulseConfig reloaded (mtime changed)")
    except Exception as e:
        logger.warning(f"PulseConfig reload failed: {e}")


def get_config(section: str, key: str, default: Any = None) -> Any:
    """取得配置值，支援熱更新.

    每次呼叫會檢查檔案修改時間，若有變更則重新載入。
    這是 PI-2 的核心機制：Morphenix 寫入 JSON → Pulse 下次讀取即生效。

    Args:
        section: 配置區段（pulse_engine / proactive_bridge / explorer）
        key: 配置鍵
        default: 預設值（config 不存在或 key 不存在時回傳）
    """
    _reload_config()
    return _CONFIG_CACHE.get(section, {}).get(key, default)


def update_config(section: str, key: str, value: Any,
                  modified_by: str = "morphenix") -> bool:
    """更新配置值（PI-2：Morphenix 寫入端）.

    安全約束：
    - 只能修改已存在的 key（不可新增任意 key）
    - 寫入前備份到 _history
    """
    if _CONFIG_PATH is None:
        return False
    try:
        _reload_config()
        if section not in _CONFIG_CACHE:
            logger.warning(f"PI-2 update rejected: unknown section '{section}'")
            return False
        if key not in _CONFIG_CACHE[section]:
            logger.warning(f"PI-2 update rejected: unknown key '{section}.{key}'")
            return False

        old_value = _CONFIG_CACHE[section][key]

        # 記錄歷史
        _log_config_change(section, key, old_value, value, modified_by)

        # 寫入
        _CONFIG_CACHE[section][key] = value
        _CONFIG_CACHE["_meta"]["last_modified_by"] = modified_by
        _CONFIG_PATH.write_text(
            json.dumps(_CONFIG_CACHE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        global _CONFIG_MTIME
        _CONFIG_MTIME = _CONFIG_PATH.stat().st_mtime
        logger.info(f"PI-2 config updated: {section}.{key} = {value} (was {old_value})")
        return True
    except Exception as e:
        logger.error(f"PI-2 config update failed: {e}")
        return False


def _log_config_change(section: str, key: str,
                       old_val: Any, new_val: Any, by: str) -> None:
    """記錄配置變更歷史（不可竄改的 JSONL 審計軌跡）."""
    if _CONFIG_PATH is None:
        return
    history_file = _CONFIG_PATH.parent / "pulse_config_history.jsonl"
    entry = {
        "ts": datetime.now(TZ8).isoformat(),
        "section": section,
        "key": key,
        "old": old_val,
        "new": new_val,
        "by": by,
    }
    try:
        with open(history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ═══════════════════════════════════════════
# PI-1 觀察引擎
# ═══════════════════════════════════════════

class PulseObserver:
    """PI-1：觀察 Pulse 行為並產出分析報告.

    讀取 Pulse 推送日誌、使用者回應，產出摘要供 Morphenix 結晶提案。
    純讀取，不做任何修改。
    """

    def __init__(self, data_dir: str) -> None:
        self._data_dir = Path(data_dir)
        self._signal_file = self._data_dir / "_system" / "pi_signals.jsonl"

    def collect_signal(self, event: Dict[str, Any]) -> None:
        """收集一筆 Pulse 互動信號.

        由 ProactiveBridge 在每次推送後呼叫。

        信號四維度：
        1. timing_quality: 推送時機品質
        2. content_relevance: 內容相關度
        3. response_depth: 回應深度
        4. diversity: 主題多樣性
        """
        signal = {
            "ts": datetime.now(TZ8).isoformat(),
            "push_id": event.get("push_id", ""),
            "push_content_len": event.get("push_content_len", 0),
            "push_topic": event.get("push_topic", ""),
            "push_type": event.get("push_type", ""),  # functional / companion / exploration
            "minutes_since_last_interaction": event.get("minutes_since_last_interaction", -1),
            "user_active": event.get("user_active", False),
            "response_received": False,
            "response_len": 0,
            "response_sentiment": "neutral",
            "response_delay_minutes": -1,
        }
        try:
            self._signal_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._signal_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(signal, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"PI-1 signal collect failed: {e}")

    def record_response(self, push_id: str, response: Dict[str, Any]) -> None:
        """記錄使用者對 Pulse 推送的回應.

        由 Brain 在處理使用者訊息時，若該訊息是對 Pulse 推送的回覆，呼叫此方法。
        """
        if not self._signal_file.exists():
            return

        try:
            lines = self._signal_file.read_text(encoding="utf-8").splitlines()
            updated = False
            new_lines = []
            for line in lines:
                try:
                    sig = json.loads(line)
                    if sig.get("push_id") == push_id and not sig.get("response_received"):
                        sig["response_received"] = True
                        sig["response_len"] = response.get("length", 0)
                        sig["response_sentiment"] = response.get("sentiment", "neutral")
                        push_ts = datetime.fromisoformat(sig["ts"])
                        now = datetime.now(TZ8)
                        sig["response_delay_minutes"] = round(
                            (now - push_ts).total_seconds() / 60, 1
                        )
                        updated = True
                    new_lines.append(json.dumps(sig, ensure_ascii=False))
                except Exception:
                    new_lines.append(line)

            if updated:
                self._signal_file.write_text(
                    "\n".join(new_lines) + "\n", encoding="utf-8"
                )
        except Exception as e:
            logger.warning(f"PI-1 record_response failed: {e}")

    def generate_observation_report(self, days: int = 7) -> Dict[str, Any]:
        """產出觀察報告（供 Morphenix Nightly 結晶用）.

        PI-1 的核心輸出：分析過去 N 天的 Pulse 表現。
        """
        signals = self._load_signals(days)
        if not signals:
            return {"status": "no_data", "days": days}

        total = len(signals)
        responded = [s for s in signals if s.get("response_received")]
        response_rate = len(responded) / total if total > 0 else 0

        # 回應深度（回應長度 / 推送長度）
        depth_scores = []
        for s in responded:
            push_len = s.get("push_content_len", 1)
            resp_len = s.get("response_len", 0)
            if push_len > 0:
                depth_scores.append(min(resp_len / push_len, 3.0))

        avg_depth = sum(depth_scores) / len(depth_scores) if depth_scores else 0

        # 回應延遲
        delays = [s.get("response_delay_minutes", 0)
                  for s in responded if s.get("response_delay_minutes", -1) >= 0]
        avg_delay = sum(delays) / len(delays) if delays else -1

        # 主題多樣性（unique topics / total pushes）
        topics = [s.get("push_topic", "") for s in signals if s.get("push_topic")]
        unique_topics = len(set(topics))
        diversity = unique_topics / len(topics) if topics else 0

        # 負面情緒比例
        neg_count = sum(1 for s in responded
                        if s.get("response_sentiment") == "negative")
        neg_rate = neg_count / len(responded) if responded else 0

        return {
            "status": "ok",
            "days": days,
            "total_pushes": total,
            "response_rate": round(response_rate, 3),
            "avg_response_depth": round(avg_depth, 3),
            "avg_response_delay_minutes": round(avg_delay, 1) if avg_delay >= 0 else None,
            "topic_diversity": round(diversity, 3),
            "negative_sentiment_rate": round(neg_rate, 3),
            "unique_topics": unique_topics,
        }

    def _load_signals(self, days: int) -> List[Dict]:
        """載入最近 N 天的信號."""
        if not self._signal_file.exists():
            return []
        cutoff = datetime.now(TZ8) - timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        signals = []
        try:
            for line in self._signal_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    sig = json.loads(line)
                    if sig.get("ts", "") >= cutoff_str:
                        signals.append(sig)
                except Exception:
                    continue
        except Exception:
            pass
        return signals


# ═══════════════════════════════════════════
# PI-3 品質門禁（Loss Function + Quality Gate）
# ═══════════════════════════════════════════

class PulseQualityGate:
    """PI-3 護欄：損失函數 + 反事實評估 + 自動回滾.

    在 Morphenix 提出行為注入提案時，先通過品質門禁才允許執行。
    """

    # ── 評分權重 ──
    W_RESPONSE_RATE = 0.30
    W_RESPONSE_DEPTH = 0.20
    W_TIMING = 0.15
    W_DIVERSITY = 0.20
    W_SENTIMENT = 0.15

    # ── 回滾閾值 ──
    ROLLBACK_Z_THRESHOLD = -2.0      # Z-score 低於 -2σ 觸發回滾
    MIN_SAMPLES_FOR_EVAL = 50        # 最低樣本數（不足則不允許 PI-3）
    OBSERVATION_WINDOW_DAYS = 7      # 變更後觀察窗
    BASELINE_WINDOW_DAYS = 21        # 基準線取樣窗口

    def __init__(self, data_dir: str) -> None:
        self._data_dir = Path(data_dir)
        self._observer = PulseObserver(data_dir)
        self._gate_log = self._data_dir / "_system" / "pi3_gate_log.jsonl"

    def compute_quality_score(self, signals: List[Dict]) -> float:
        """計算 Pulse 品質綜合分（0.0 ~ 1.0）.

        四維度加權：
        1. 回應率（response_rate）
        2. 回應深度（response_depth）
        3. 時機品質（timing）= 1 - normalize(delay)
        4. 多樣性（diversity）
        5. 情緒（sentiment）= 1 - negative_rate
        """
        if not signals:
            return 0.0

        total = len(signals)
        responded = [s for s in signals if s.get("response_received")]
        response_rate = len(responded) / total if total > 0 else 0

        # depth
        depth_scores = []
        for s in responded:
            push_len = max(s.get("push_content_len", 1), 1)
            resp_len = s.get("response_len", 0)
            depth_scores.append(min(resp_len / push_len, 3.0) / 3.0)  # normalize to 0-1
        avg_depth = sum(depth_scores) / len(depth_scores) if depth_scores else 0

        # timing (lower delay = better, cap at 240 minutes)
        delays = [s.get("response_delay_minutes", 240)
                  for s in responded if s.get("response_delay_minutes", -1) >= 0]
        if delays:
            avg_delay = sum(delays) / len(delays)
            timing = max(0, 1.0 - avg_delay / 240.0)
        else:
            timing = 0.5  # 無資料時中性

        # diversity
        topics = [s.get("push_topic", "") for s in signals if s.get("push_topic")]
        unique = len(set(topics))
        diversity = unique / len(topics) if topics else 0.5

        # sentiment
        neg = sum(1 for s in responded if s.get("response_sentiment") == "negative")
        sentiment = 1.0 - (neg / len(responded)) if responded else 0.7

        score = (
            self.W_RESPONSE_RATE * response_rate
            + self.W_RESPONSE_DEPTH * avg_depth
            + self.W_TIMING * timing
            + self.W_DIVERSITY * diversity
            + self.W_SENTIMENT * sentiment
        )
        return round(min(max(score, 0.0), 1.0), 4)

    def get_baseline(self) -> Tuple[float, float, int]:
        """取得基準線（均值、標準差、樣本數）.

        Returns:
            (mean, std, sample_count)
        """
        signals = self._observer._load_signals(self.BASELINE_WINDOW_DAYS)
        if len(signals) < self.MIN_SAMPLES_FOR_EVAL:
            return 0.0, 0.0, len(signals)

        # 滑動窗口：每 7 天一個分數
        window_scores = []
        days = self.BASELINE_WINDOW_DAYS
        for offset in range(0, days - 6):
            start = datetime.now(TZ8) - timedelta(days=days - offset)
            end = start + timedelta(days=7)
            start_str = start.isoformat()
            end_str = end.isoformat()
            window = [s for s in signals
                      if start_str <= s.get("ts", "") <= end_str]
            if len(window) >= 5:
                window_scores.append(self.compute_quality_score(window))

        if not window_scores:
            overall = self.compute_quality_score(signals)
            return overall, 0.1, len(signals)

        mean = sum(window_scores) / len(window_scores)
        variance = sum((s - mean) ** 2 for s in window_scores) / len(window_scores)
        std = math.sqrt(variance) if variance > 0 else 0.05  # 最小標準差

        return round(mean, 4), round(std, 4), len(signals)

    def evaluate_proposal(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        """評估 PI-3 行為注入提案是否通過品質門禁.

        Returns:
            {
                "approved": bool,
                "reason": str,
                "baseline_mean": float,
                "baseline_std": float,
                "current_score": float,
                "sample_count": int,
            }
        """
        mean, std, count = self.get_baseline()

        # 門禁 1：樣本不足
        if count < self.MIN_SAMPLES_FOR_EVAL:
            result = {
                "approved": False,
                "reason": f"insufficient_samples ({count} < {self.MIN_SAMPLES_FOR_EVAL})",
                "baseline_mean": mean,
                "baseline_std": std,
                "current_score": 0,
                "sample_count": count,
            }
            self._log_gate(proposal, result)
            return result

        # 門禁 2：當前品質分是否在正常區間
        recent = self._observer._load_signals(self.OBSERVATION_WINDOW_DAYS)
        current_score = self.compute_quality_score(recent)

        z_score = (current_score - mean) / std if std > 0 else 0

        # 如果當前品質已經低於 -1σ，不允許再做激進改動
        if z_score < -1.0:
            result = {
                "approved": False,
                "reason": f"quality_degraded (z={z_score:.2f}, score={current_score:.4f})",
                "baseline_mean": mean,
                "baseline_std": std,
                "current_score": current_score,
                "z_score": round(z_score, 2),
                "sample_count": count,
            }
            self._log_gate(proposal, result)
            return result

        # 通過
        result = {
            "approved": True,
            "reason": "quality_gate_passed",
            "baseline_mean": mean,
            "baseline_std": std,
            "current_score": current_score,
            "z_score": round(z_score, 2),
            "sample_count": count,
        }
        self._log_gate(proposal, result)
        return result

    def check_rollback_needed(self) -> Optional[Dict[str, Any]]:
        """檢查是否需要自動回滾（觀察窗結束後）.

        由 Nightly Pipeline 每天呼叫。
        如果最近 7 天的品質分 Z-score < -2σ，觸發回滾信號。

        Returns:
            None（正常）或 {"rollback": True, "reason": ..., ...}
        """
        mean, std, count = self.get_baseline()
        if count < self.MIN_SAMPLES_FOR_EVAL or std == 0:
            return None

        recent = self._observer._load_signals(self.OBSERVATION_WINDOW_DAYS)
        if len(recent) < 10:
            return None

        current_score = self.compute_quality_score(recent)
        z_score = (current_score - mean) / std

        if z_score < self.ROLLBACK_Z_THRESHOLD:
            return {
                "rollback": True,
                "reason": f"quality_z_score={z_score:.2f} < {self.ROLLBACK_Z_THRESHOLD}",
                "current_score": current_score,
                "baseline_mean": mean,
                "baseline_std": std,
                "z_score": round(z_score, 2),
            }
        return None

    def _log_gate(self, proposal: Dict, result: Dict) -> None:
        """記錄門禁決策."""
        entry = {
            "ts": datetime.now(TZ8).isoformat(),
            "proposal_id": proposal.get("id", ""),
            "proposal_title": proposal.get("title", ""),
            **result,
        }
        try:
            self._gate_log.parent.mkdir(parents=True, exist_ok=True)
            with open(self._gate_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


# ═══════════════════════════════════════════
# PI-3 行為規則注入引擎
# ═══════════════════════════════════════════

class PulseBehaviorInjector:
    """PI-3：Morphenix 生成的行為規則注入管理器.

    規則格式：
    {
        "id": "rule_xxx",
        "condition": "time_since_last_push > 7200",
        "action": "reduce_push_interval",
        "params": {"new_interval": 3600},
        "created_by": "morphenix_proposal_xxx",
        "created_at": "2026-03-12T...",
        "expires_at": "2026-03-19T...",  # 7 天後到期
        "status": "active"  # active / expired / rolled_back
    }
    """

    RULE_TTL_DAYS = 7  # 規則存活期（到期後自動停用）

    def __init__(self, data_dir: str) -> None:
        self._rules_file = Path(data_dir) / "_system" / "pi3_behavior_rules.json"
        self._quality_gate = PulseQualityGate(data_dir)

    def inject_rule(self, rule: Dict[str, Any],
                    proposal: Dict[str, Any]) -> Dict[str, Any]:
        """注入一條新行為規則（需通過品質門禁）.

        Returns:
            {"success": bool, "reason": str, ...}
        """
        # Step 1: 品質門禁
        gate_result = self._quality_gate.evaluate_proposal(proposal)
        if not gate_result.get("approved"):
            return {
                "success": False,
                "reason": f"quality_gate_rejected: {gate_result.get('reason', '')}",
                "gate_result": gate_result,
            }

        # Step 2: 寫入規則
        now = datetime.now(TZ8)
        rule["created_at"] = now.isoformat()
        rule["expires_at"] = (now + timedelta(days=self.RULE_TTL_DAYS)).isoformat()
        rule["status"] = "active"

        rules = self._load_rules()
        rules.append(rule)
        self._save_rules(rules)

        logger.info(f"PI-3 rule injected: {rule.get('id', 'unknown')}")
        return {
            "success": True,
            "reason": "rule_injected",
            "rule_id": rule.get("id", ""),
            "expires_at": rule["expires_at"],
            "gate_result": gate_result,
        }

    def get_active_rules(self) -> List[Dict]:
        """取得所有生效中的規則（已過期的自動停用）."""
        rules = self._load_rules()
        now_str = datetime.now(TZ8).isoformat()
        active = []
        changed = False
        for r in rules:
            if r.get("status") == "active":
                if r.get("expires_at", "") < now_str:
                    r["status"] = "expired"
                    changed = True
                    logger.info(f"PI-3 rule expired: {r.get('id', '')}")
                else:
                    active.append(r)
        if changed:
            self._save_rules(rules)
        return active

    def rollback_all(self, reason: str = "") -> int:
        """回滾所有 active 規則（品質退化時由 Nightly 觸發）."""
        rules = self._load_rules()
        count = 0
        for r in rules:
            if r.get("status") == "active":
                r["status"] = "rolled_back"
                r["rollback_reason"] = reason
                r["rolled_back_at"] = datetime.now(TZ8).isoformat()
                count += 1

        if count > 0:
            self._save_rules(rules)

            # 同時回滾 pulse_config 到預設值
            self._restore_config_defaults()

            logger.warning(f"PI-3 rollback: {count} rules rolled back — {reason}")

        return count

    def _restore_config_defaults(self) -> None:
        """回滾 pulse_config.json 到出廠預設值."""
        defaults = {
            "pulse_engine": {
                "active_hours_start": 7,
                "active_hours_end": 25,
                "daily_push_limit": 25,
                "breath_interval_base": 1800,
                "exploration_daily_limit": 10,
            },
            "proactive_bridge": {
                "silent_ack_threshold": 8,
                "companion_ack_threshold": 10,
                "active_hours_start": 8,
                "active_hours_end": 25,
                "daily_push_limit": 25,
                "proactive_interval": 1800,
                "daily_minimum_interval": 3600,
                "daily_minimum_hour": 14,
                "watchdog_alert_hours": 3,
                "proactive_model": "claude-haiku-4-5-20251001",
            },
            "explorer": {
                "max_cost_per_exploration": 0.50,
                "max_explorations_per_day": 3,
                "max_daily_cost": 1.50,
                "scout_model": "claude-haiku-4-5-20251001",
                "deep_model": "claude-sonnet-4-20250514",
            },
        }
        for section, kvs in defaults.items():
            for key, value in kvs.items():
                update_config(section, key, value, modified_by="pi3_rollback")

    def _load_rules(self) -> List[Dict]:
        if self._rules_file.exists():
            try:
                return json.loads(self._rules_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_rules(self, rules: List[Dict]) -> None:
        try:
            self._rules_file.parent.mkdir(parents=True, exist_ok=True)
            self._rules_file.write_text(
                json.dumps(rules, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"PI-3 rules save failed: {e}")
