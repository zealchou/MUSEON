"""DigestEngine — 外部知識消化引擎.

人類讀書模型：進食 → 沉睡 → 試用 → 固化/淘汰。
外部知識不會立刻被認同，需要在實戰中多次驗證後才會固化。

雙軌消化路徑：
  Track A（outward_self）：固化走 Morphenix 提案
  Track B（outward_service）：固化走 Knowledge Lattice 正式結晶
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══ 消化閘門常數 ═══

# 進食
INITIAL_CONFIDENCE = 0.3           # Haiku 篩選後的基礎信心度

# 晉升條件
PROMOTE_MIN_TRIALS = 3             # 至少試用 3 次
PROMOTE_MIN_SUCCESS_RATE = 0.6     # 成功率 ≥ 60%
PROMOTE_MIN_CONFIDENCE = 0.7       # 信心度 ≥ 0.7

# 淘汰條件
DEMOTE_MAX_CONSECUTIVE_FAILS = 3   # 連續失敗 3 次
DEMOTE_MIN_CONFIDENCE = 0.15       # 信心度跌破 0.15

# 生命週期
MAX_QUARANTINE_DAYS = 90           # 最長隔離期
RELEVANCE_MATCH_THRESHOLD = 0.4   # 試用匹配閾值

# 信心度更新
CONFIDENCE_SUCCESS_DELTA = 0.1     # 成功 +0.1
CONFIDENCE_FAILURE_DELTA = 0.15    # 失敗 -0.15


class DigestEngine:
    """外部知識消化引擎."""

    def __init__(
        self,
        workspace: Path,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._workspace = workspace
        self._event_bus = event_bus
        self._quarantine: List[Dict] = []
        self._load_quarantine()

    # ─── 階段 1：進食（Ingest）───

    def ingest(self, research_result: Dict, search_context: Dict) -> Optional[str]:
        """將研究結果存入隔離區.

        Args:
            research_result: ResearchEngine 的 filtered_summary 等資訊
            search_context: IntentionRadar 的查詢上下文（track, trigger_type 等）

        Returns:
            quarantine_id 或 None
        """
        summary = research_result.get("filtered_summary", "")
        if not summary or len(summary) < 20:
            return None

        # 安全護欄：外部搜尋結果必須通過 Sanitizer
        if not self._sanitize_content(summary):
            logger.warning(
                "DigestEngine: ingest rejected — sanitizer detected threat"
            )
            return None

        now = datetime.now(TZ8)
        qid = f"QC-{now.strftime('%Y%m%d_%H%M%S')}-{len(self._quarantine):03d}"

        crystal = {
            # 識別
            "quarantine_id": qid,
            "status": "quarantined",

            # 知識內容（GEO 簡化版）
            "g1_summary": summary[:100],
            "content": summary,
            "tags": self._extract_tags(summary),

            # 來源追溯
            "origin": f"outward_{search_context.get('track', 'service')}",
            "source_urls": research_result.get("source_urls", []),
            "search_query": search_context.get("query", ""),
            "trigger_type": search_context.get("trigger_type", ""),
            "track": search_context.get("track", "service"),

            # 驗證追蹤
            "verification_level": "hypothetical",
            "confidence": INITIAL_CONFIDENCE,
            "trial_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "consecutive_failures": 0,

            # 生命週期
            "quarantined_at": now.isoformat(),
            "max_quarantine_days": MAX_QUARANTINE_DAYS,
            "last_trial_at": None,
        }

        self._quarantine.append(crystal)
        self._save_quarantine()

        logger.info(
            f"DigestEngine: ingested {qid} "
            f"[{crystal['origin']}] '{crystal['g1_summary'][:40]}...'"
        )
        return qid

    # ─── 階段 3：試用（Trial）───

    def scan_for_relevance(self, query_text: str) -> List[Dict]:
        """對話中檢索記憶時，同時掃描隔離區找相關知識.

        純 CPU：SequenceMatcher + 關鍵字重疊。

        Args:
            query_text: 當前對話的查詢文字

        Returns:
            匹配的 quarantined crystals 列表
        """
        if not query_text or not self._quarantine:
            return []

        matches = []
        query_lower = query_text.lower()

        for crystal in self._quarantine:
            if crystal["status"] not in ("quarantined", "provisional"):
                continue

            # 計算相關性
            score = self._relevance_score(query_lower, crystal)
            if score >= RELEVANCE_MATCH_THRESHOLD:
                matches.append(crystal)

        return matches

    def record_trial(self, quarantine_id: str, success: bool) -> Optional[Dict]:
        """記錄一次試用結果.

        Args:
            quarantine_id: 隔離區結晶 ID
            success: 試用是否成功

        Returns:
            更新後的結晶狀態，或 None
        """
        crystal = self._find_crystal(quarantine_id)
        if not crystal:
            return None

        now = datetime.now(TZ8)
        crystal["status"] = "provisional"
        crystal["trial_count"] += 1
        crystal["last_trial_at"] = now.isoformat()

        if success:
            crystal["success_count"] += 1
            crystal["consecutive_failures"] = 0
            crystal["confidence"] = min(
                1.0, crystal["confidence"] + CONFIDENCE_SUCCESS_DELTA
            )
        else:
            crystal["failure_count"] += 1
            crystal["consecutive_failures"] += 1
            crystal["confidence"] = max(
                0.0, crystal["confidence"] - CONFIDENCE_FAILURE_DELTA
            )

        self._save_quarantine()

        # 發布事件
        if self._event_bus:
            try:
                from museon.core.event_bus import OUTWARD_TRIAL_RECORDED
                self._event_bus.publish(OUTWARD_TRIAL_RECORDED, {
                    "quarantine_id": quarantine_id,
                    "success": success,
                    "confidence": crystal["confidence"],
                    "trial_count": crystal["trial_count"],
                    "track": crystal.get("track", "service"),
                })
            except Exception:
                pass

        logger.info(
            f"DigestEngine: trial recorded {quarantine_id} "
            f"success={success} conf={crystal['confidence']:.2f} "
            f"trials={crystal['trial_count']}"
        )
        return crystal

    # ─── 階段 4 & 5：生命週期管理（Nightly Step 13.8）───

    def lifecycle_scan(self) -> Dict:
        """Nightly 生命週期掃描：晉升、淘汰、TTL 清理.

        Returns:
            {
                "promoted": [quarantine_id, ...],
                "archived": [quarantine_id, ...],
                "ttl_expired": [quarantine_id, ...],
                "active_count": int,
            }
        """
        promoted = []
        archived = []
        ttl_expired = []
        now = datetime.now(TZ8)

        for crystal in list(self._quarantine):
            qid = crystal["quarantine_id"]
            status = crystal["status"]

            if status in ("archived", "promoted"):
                continue

            # ─── 檢查晉升條件 ───
            if self._should_promote(crystal):
                result = self._promote(crystal)
                if result:
                    promoted.append(qid)
                continue

            # ─── 檢查淘汰條件 ───
            if self._should_demote(crystal):
                self._archive(crystal, reason="demoted")
                archived.append(qid)
                continue

            # ─── 檢查 TTL ───
            quarantined_at = crystal.get("quarantined_at", "")
            try:
                q_dt = datetime.fromisoformat(quarantined_at)
                days = (now - q_dt).days
                if days > crystal.get("max_quarantine_days", MAX_QUARANTINE_DAYS):
                    self._archive(crystal, reason="ttl_expired")
                    ttl_expired.append(qid)
            except Exception:
                pass

        self._save_quarantine()

        active = [
            c for c in self._quarantine
            if c["status"] in ("quarantined", "provisional")
        ]

        return {
            "promoted": promoted,
            "archived": archived,
            "ttl_expired": ttl_expired,
            "active_count": len(active),
        }

    def _should_promote(self, crystal: Dict) -> bool:
        """檢查是否滿足固化條件."""
        if crystal["trial_count"] < PROMOTE_MIN_TRIALS:
            return False
        if crystal["confidence"] < PROMOTE_MIN_CONFIDENCE:
            return False

        total = crystal["trial_count"]
        success = crystal["success_count"]
        if total > 0 and (success / total) < PROMOTE_MIN_SUCCESS_RATE:
            return False

        return True

    def _should_demote(self, crystal: Dict) -> bool:
        """檢查是否滿足淘汰條件."""
        if crystal["confidence"] < DEMOTE_MIN_CONFIDENCE:
            return True
        if crystal["consecutive_failures"] >= DEMOTE_MAX_CONSECUTIVE_FAILS:
            return True
        return False

    def _promote(self, crystal: Dict) -> bool:
        """固化一個結晶（依軌道分流）."""
        track = crystal.get("track", "service")
        qid = crystal["quarantine_id"]

        crystal["status"] = "promoted"
        crystal["promoted_at"] = datetime.now(TZ8).isoformat()

        if track == "self":
            # Track A：生成 Morphenix L2 提案
            self._create_morphenix_proposal(crystal)
        else:
            # Track B：直接寫入 Knowledge Lattice
            self._write_to_knowledge_lattice(crystal)

        # 發布事件
        if self._event_bus:
            try:
                from museon.core.event_bus import (
                    OUTWARD_SELF_CRYSTALLIZED,
                    OUTWARD_SERVICE_CRYSTALLIZED,
                )
                evt = OUTWARD_SELF_CRYSTALLIZED if track == "self" else OUTWARD_SERVICE_CRYSTALLIZED
                self._event_bus.publish(evt, {
                        "quarantine_id": qid,
                        "track": track,
                        "content": crystal.get("content", ""),
                        "confidence": crystal["confidence"],
                        "trial_count": crystal["trial_count"],
                        "success_rate": (
                            crystal["success_count"] / crystal["trial_count"]
                            if crystal["trial_count"] > 0
                            else 0
                        ),
                    })
            except Exception as e:
                logger.error(f"DigestEngine: publish {evt} failed: {e}")

        logger.info(
            f"DigestEngine: PROMOTED {qid} [{track}] "
            f"conf={crystal['confidence']:.2f} "
            f"trials={crystal['trial_count']}"
        )
        return True

    def _archive(self, crystal: Dict, reason: str = "") -> None:
        """歸檔一個結晶."""
        qid = crystal["quarantine_id"]
        crystal["status"] = "archived"
        crystal["archived_at"] = datetime.now(TZ8).isoformat()
        crystal["archive_reason"] = reason

        # 發布事件
        if self._event_bus:
            try:
                from museon.core.event_bus import OUTWARD_KNOWLEDGE_ARCHIVED
                self._event_bus.publish(OUTWARD_KNOWLEDGE_ARCHIVED, {
                    "quarantine_id": qid,
                    "reason": reason,
                    "track": crystal.get("track", "service"),
                })
            except Exception:
                pass

        logger.info(
            f"DigestEngine: ARCHIVED {qid} reason={reason}"
        )

    def _create_morphenix_proposal(self, crystal: Dict) -> None:
        """Track A 固化：生成 Morphenix L2 提案."""
        notes_dir = self._workspace / "_system" / "morphenix" / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(TZ8)
        note_id = f"outward_{now.strftime('%Y%m%d_%H%M%S')}"
        note_file = notes_dir / f"{note_id}.json"

        note = {
            "type": "outward_self_proposal",
            "topic": crystal.get("g1_summary", ""),
            "observation": crystal.get("content", ""),
            "source": "digest_engine",
            "source_urls": crystal.get("source_urls", []),
            "confidence": crystal["confidence"],
            "trial_count": crystal["trial_count"],
            "success_rate": (
                crystal["success_count"] / crystal["trial_count"]
                if crystal["trial_count"] > 0
                else 0
            ),
            "created_at": now.isoformat(),
            "auto_propose": True,
        }

        try:
            with open(note_file, "w", encoding="utf-8") as fh:
                json.dump(note, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"DigestEngine: write morphenix note failed: {e}")

    # ─── 輔助方法 ───

    def _relevance_score(self, query_lower: str, crystal: Dict) -> float:
        """計算查詢與結晶的相關性分數（純 CPU）."""
        summary = crystal.get("g1_summary", "").lower()
        tags = [t.lower() for t in crystal.get("tags", [])]
        content = crystal.get("content", "").lower()

        # 方法 1：SequenceMatcher 相似度
        seq_score = SequenceMatcher(None, query_lower, summary).ratio()

        # 方法 2：關鍵字重疊
        query_words = set(query_lower.split())
        tag_overlap = len(query_words & set(tags))
        tag_score = min(1.0, tag_overlap / max(len(query_words), 1) * 2)

        # 方法 3：內容關鍵字命中
        content_hits = sum(1 for w in query_words if w in content)
        content_score = min(1.0, content_hits / max(len(query_words), 1))

        # 加權
        return seq_score * 0.4 + tag_score * 0.3 + content_score * 0.3

    def _extract_tags(self, text: str) -> List[str]:
        """從文字中提取標籤（簡易分詞）."""
        # 英文：取空白分隔的長詞
        words = text.split()
        tags = [w.lower().strip(".,;:!?\"'()") for w in words if len(w) > 3]
        # 去重並限制數量
        seen = set()
        unique_tags = []
        for t in tags:
            if t not in seen and len(t) < 30:
                seen.add(t)
                unique_tags.append(t)
        return unique_tags[:15]

    def _find_crystal(self, quarantine_id: str) -> Optional[Dict]:
        """在隔離區中找到指定結晶."""
        for crystal in self._quarantine:
            if crystal.get("quarantine_id") == quarantine_id:
                return crystal
        return None

    # ─── 持久化 ───

    def _load_quarantine(self) -> None:
        """載入隔離區資料."""
        q_file = self._workspace / "_system" / "outward" / "quarantine.json"
        if q_file.exists():
            try:
                with open(q_file, "r", encoding="utf-8") as fh:
                    self._quarantine = json.load(fh)
            except Exception:
                self._quarantine = []
        else:
            self._quarantine = []

    def _save_quarantine(self) -> None:
        """儲存隔離區資料."""
        outward_dir = self._workspace / "_system" / "outward"
        outward_dir.mkdir(parents=True, exist_ok=True)
        q_file = outward_dir / "quarantine.json"
        try:
            with open(q_file, "w", encoding="utf-8") as fh:
                json.dump(self._quarantine, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"DigestEngine: save quarantine failed: {e}")

    # ─── 查詢介面 ───

    def get_stats(self) -> Dict:
        """取得隔離區統計."""
        statuses = {}
        for c in self._quarantine:
            s = c.get("status", "unknown")
            statuses[s] = statuses.get(s, 0) + 1
        return {
            "total": len(self._quarantine),
            "by_status": statuses,
        }

    # ─── 安全護欄 ───

    def _sanitize_content(self, content: str) -> bool:
        """同步版安全檢查：偵測外部搜尋結果的注入攻擊.

        使用 InputSanitizer 的模式匹配（純 CPU，不需 async）。

        Returns:
            True 表示安全，False 表示偵測到威脅
        """
        try:
            from museon.security.sanitizer import InputSanitizer
            sanitizer = InputSanitizer()

            # 同步版模式匹配（不走 async sanitize，直接用偵測方法）
            if sanitizer._detect_injection(content):
                logger.warning("DigestEngine: prompt injection detected in external content")
                return False
            if sanitizer._detect_tag_injection(content):
                logger.warning("DigestEngine: tag injection detected in external content")
                return False
            if sanitizer._detect_role_playing(content):
                logger.warning("DigestEngine: role-playing injection detected in external content")
                return False

            # 額外檢查：指令關鍵字
            content_lower = content.lower()
            for keyword in sanitizer.INSTRUCTION_KEYWORDS:
                if keyword.lower() in content_lower:
                    logger.warning(
                        f"DigestEngine: instruction keyword '{keyword}' detected"
                    )
                    return False

            return True

        except ImportError:
            # Sanitizer 不可用時，降級為允許（但記錄警告）
            logger.warning("DigestEngine: InputSanitizer not available, allowing content")
            return True
        except Exception as e:
            logger.error(f"DigestEngine: sanitize check failed: {e}")
            return True  # 安全檢查失敗不應阻塞流程

    # ─── Track B 固化寫入 ───

    def _write_to_knowledge_lattice(self, crystal: Dict) -> None:
        """Track B 固化：將外向服務知識寫入 Knowledge Lattice.

        將隔離區結晶轉換為正式 Crystal 格式並寫入 crystals.json。
        """
        try:
            from museon.agent.knowledge_lattice import KnowledgeLattice

            lattice = KnowledgeLattice(data_dir=str(self._workspace))

            new_crystal = lattice.crystallize(
                raw_material=crystal.get("content", ""),
                source_context=", ".join(crystal.get("source_urls", [])[:3]),
                crystal_type="Insight",
                g1_summary=crystal.get("g1_summary", "")[:30],
                g2_structure=crystal.get("tags", []),
                g3_root_inquiry=crystal.get("search_query", ""),
                g4_insights=[crystal.get("content", "")],
                assumption=(
                    f"外向搜尋發現，經 {crystal.get('trial_count', 0)} 次試用驗證"
                ),
                evidence=(
                    f"信心度 {crystal.get('confidence', 0):.2f}，"
                    f"成功率 {crystal.get('success_count', 0)}/{crystal.get('trial_count', 0)}"
                ),
                limitation="來源為外部搜尋，適用範圍需進一步驗證",
                tags=crystal.get("tags", []),
                domain=crystal.get("track", "service"),
            )
            # 補充 origin 標記
            new_crystal.origin = "outward_service"
            logger.info(
                f"DigestEngine: Track B crystal written to Knowledge Lattice — "
                f"'{new_crystal.g1_summary}'"
            )

        except ImportError:
            logger.warning(
                "DigestEngine: KnowledgeLattice not available, "
                "Track B crystal not written"
            )
        except Exception as e:
            logger.error(f"DigestEngine: write to lattice failed: {e}")
