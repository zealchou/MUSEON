"""DNA27-based Skill Router — 透過 DNA27 反射弧驅動技能喚醒.

v10.1 核心架構：DNA27 RC 叢集觸發 → 查詢每個 skill 自己宣告的 RC 親和 → 喚醒 skills。

三層疊加評分（v10.1 調參）：
  Layer 1: RC 驅動（權重 ×5.0）— 從 skill 檔案的 DNA27 親和對照動態載入
  Layer 2: 關鍵字匹配（觸發詞 + 名稱 + 描述）
  Layer 3: Qdrant 向量語義匹配（權重 ×1.5）

v10.1 修正：
  - RC 權重 3.0→5.0（DNA27 反射弧必須主導 skill 選擇）
  - Vector 權重 2.0→1.5（語義補充，不應蓋過 RC 信號）
  - Always-on 底分 2.0→0.5（常駐 skill 不搶 slot）
  - RC 保底機制：前 2 名 RC-matched skills 保證進入結果
  - RC 歸一化修正：分母 cap=3，避免泛用型 skill 被稀釋

skills 不是外掛模組，而是嵌入在 DNA27 反射弧中的認知迴路。
每個 skill 自己定義自己屬於哪條神經通路（不是硬編碼）。
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Lazy import: rc_affinity_loader 在 __init__ 中按需載入


class SkillRouter:
    """DNA27-based skill routing — 快速匹配使用者需求到技能.

    掃描兩個來源：
    - skills/native/  → 原生技能（DNA 自帶的 45 個）
    - skills/forged/  → 鍛造技能（MUSEON 自己創造的）

    也支援舊結構（skills/ 直接放技能目錄，無 native/forged 子層）。
    """

    def __init__(self, skills_dir: str = "data/skills", event_bus=None):
        self.skills_dir = Path(skills_dir)
        self._event_bus = event_bus
        self._index: List[Dict[str, Any]] = []
        self._vector_bridge = None
        self._rc_index = None  # RCAffinityIndex — DNA27 RC→skill 反向索引
        self._build_index()
        self._build_rc_index()
        self._subscribe_events()

    def _build_index(self) -> None:
        """掃描所有 SKILL.md，建立觸發詞索引."""
        self._index = []
        if not self.skills_dir.exists():
            return

        # 決定掃描路徑：如果有 native/ 子目錄就掃兩層，否則掃平面結構
        native_dir = self.skills_dir / "native"
        forged_dir = self.skills_dir / "forged"

        if native_dir.exists():
            # 新結構：native/ + forged/
            self._scan_directory(native_dir, origin="native")
            if forged_dir.exists():
                self._scan_directory(forged_dir, origin="forged")
        else:
            # 舊結構：直接掃描 skills/ 下的目錄
            self._scan_directory(self.skills_dir, origin="native")

    def _scan_directory(self, directory: Path, origin: str = "native") -> None:
        """掃描一個目錄下的所有技能."""
        for skill_dir in sorted(directory.iterdir()):
            if not skill_dir.is_dir():
                continue
            # 跳過 native/ forged/ 本身（防止舊結構誤掃）
            if skill_dir.name in ("native", "forged"):
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                skill_file = skill_dir / "BRIEF.md"
            if not skill_file.exists():
                continue

            meta = self._extract_metadata(skill_file)
            if meta:
                meta["path"] = str(skill_file)
                meta["dir_name"] = skill_dir.name
                meta["origin"] = origin  # "native" 或 "forged"
                self._index.append(meta)

    def _extract_metadata(self, skill_path: Path) -> Optional[Dict[str, Any]]:
        """從 SKILL.md 提取 name、description、觸發詞."""
        try:
            content = skill_path.read_text(encoding="utf-8")
        except Exception:
            return None

        meta: Dict[str, Any] = {
            "name": skill_path.parent.name,
            "description": "",
            "triggers": [],
            "always_on": False,
        }

        # Parse YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                body = parts[2]

                # 只匹配頂層（未縮排）YAML 欄位，避免巢狀
                # stages[].name 覆蓋頂層 name（#案例結晶 幽靈 Skill 根因）
                for line in frontmatter.splitlines():
                    if line.startswith("name:"):
                        meta["name"] = line[5:].strip().strip('"').strip("'")
                    elif line.startswith("description:"):
                        # May be multi-line (>) — grab first line
                        meta["description"] = line[12:].strip().lstrip(">").strip()
                    elif line.startswith("type:"):
                        meta["type"] = line[5:].strip()
                    elif line.startswith("hub:"):
                        meta["hub"] = line[4:].strip()
                    elif line.startswith("model_preference:"):
                        meta["model_preference"] = line[17:].strip()

                # 提取 io.inputs（用於 DeterministicRouter 依賴推導）
                meta["io_inputs"] = self._extract_io_inputs(frontmatter)

                # Extract trigger words from body
                meta["triggers"] = self._extract_triggers(body, frontmatter)

                # Check if always-on — 僅以 YAML frontmatter type 欄位判定
                # 舊邏輯用子字串搜尋 "常駐" in content 有 67% 虛假正報率
                # （text-alchemy 說「不常駐」也被誤判為 always_on）
                meta["always_on"] = meta.get("type") == "always-on"

                # Get short description from frontmatter if multi-line
                if not meta["description"]:
                    desc_lines = []
                    in_desc = False
                    for line in frontmatter.splitlines():
                        if line.strip().startswith("description:"):
                            remainder = line.split("description:", 1)[1].strip()
                            if remainder.startswith(">"):
                                in_desc = True
                                continue
                            elif remainder:
                                meta["description"] = remainder
                                break
                        elif in_desc:
                            if line.strip() and not line.strip().startswith(("name:", "---")):
                                desc_lines.append(line.strip())
                            else:
                                break
                    if desc_lines:
                        meta["description"] = " ".join(desc_lines)

        return meta

    def get_skills_by_hub(self, hub_name: str) -> List[Dict[str, Any]]:
        """回傳指定 Hub 下的所有 Skill 元資料."""
        return [s for s in self._index if s.get("hub") == hub_name]

    @staticmethod
    def _extract_io_inputs(frontmatter: str) -> List[Dict[str, str]]:
        """從 YAML frontmatter 提取 io.inputs 列表.

        解析格式：
          io:
            inputs:
              - from: skill-name
                field: field_name
                required: true
        回傳 [{"from": "skill-name", "field": "field_name"}, ...]
        """
        inputs = []
        lines = frontmatter.splitlines()
        in_inputs = False
        for line in lines:
            stripped = line.strip()
            # 偵測 inputs: 區塊開始
            if stripped == "inputs:":
                in_inputs = True
                continue
            # 離開 inputs 區塊（遇到同級或更高層級的 key）
            if in_inputs and stripped and not stripped.startswith("-") and not stripped.startswith("from:") and not stripped.startswith("field:") and not stripped.startswith("required:") and not stripped.startswith("trigger:"):
                in_inputs = False
                continue
            if in_inputs and stripped.startswith("- from:"):
                from_val = stripped[7:].strip().strip('"').strip("'")
                inputs.append({"from": from_val})
            elif in_inputs and stripped.startswith("from:") and inputs:
                from_val = stripped[5:].strip().strip('"').strip("'")
                inputs.append({"from": from_val})
            elif in_inputs and stripped.startswith("field:") and inputs:
                inputs[-1]["field"] = stripped[6:].strip()
        return inputs

    def _extract_triggers(self, body: str, frontmatter: str) -> List[str]:
        """從 SKILL.md 內容提取觸發詞."""
        triggers = []

        # Look for trigger words in frontmatter description
        full_text = frontmatter + "\n" + body

        # Pattern: 涵蓋觸發詞：word1、word2、word3
        trigger_match = re.search(r"涵蓋觸發詞[：:](.+?)(?:\n|$)", full_text)
        if trigger_match:
            raw = trigger_match.group(1)
            # Split by Chinese/English delimiters
            words = re.split(r"[、,，；;/\s]+", raw)
            triggers.extend(w.strip() for w in words if w.strip())

        # Pattern: 觸發時機 section — extract /commands
        for match in re.finditer(r"/(\w[\w-]*)", full_text):
            cmd = match.group(1)
            if cmd not in ("self-review", "evolve_now", "set-mission"):
                triggers.append(f"/{cmd}")

        # Pattern: 自然語言偵測——extract quoted keywords
        nat_match = re.search(r"自然語言偵測[——\-]+(.+?)(?:觸發|$)", full_text, re.DOTALL)
        if nat_match:
            section = nat_match.group(1)
            # Extract keywords in quotes
            for qmatch in re.finditer(r"「(.+?)」", section):
                triggers.append(qmatch.group(1))

        return list(set(triggers))

    def _get_vector_bridge(self):
        """Lazy 取得 VectorBridge（靜默失敗）."""
        if self._vector_bridge is not None:
            return self._vector_bridge
        try:
            from museon.vector.vector_bridge import VectorBridge
            # 從 skills_dir 推導 workspace（通常是 data/）
            workspace = self.skills_dir.parent
            vb = VectorBridge(workspace=workspace)
            if vb.is_available():
                self._vector_bridge = vb
                return vb
        except Exception as e:
            logger.debug(f"[SKILL_ROUTER] vector failed (degraded): {e}")
        return None

    def _vector_search_skills(
        self, query: str, limit: int,
    ) -> Dict[str, float]:
        """從 Qdrant skills collection 語義搜尋（靜默失敗回傳空 dict）.

        Returns:
            {skill_name: score, ...}
        """
        try:
            vb = self._get_vector_bridge()
            if vb is None:
                logger.debug("vec_search: VectorBridge 不可用")
                return {}
            results = vb.hybrid_search("skills", query, limit=limit)
            if not results:
                logger.debug(
                    f"vec_search: 搜尋結果為空 (query={query[:50]}..., "
                    f"collection=skills)"
                )
            return {
                r["id"]: r["score"]
                for r in results
            }
        except Exception as e:
            logger.debug(f"vec_search: 搜尋失敗: {e}")
            return {}

    def _build_rc_index(self) -> None:
        """v10: 從 skill 檔案動態載入 RC → skill 映射（取代硬編碼）.

        掃描 skills/native/ 下所有 SKILL.md 的 ## DNA27 親和對照 區段，
        建立 RC → [skills] 反向索引。每個 skill 自己定義自己屬於哪條神經通路。
        """
        try:
            from museon.agent.rc_affinity_loader import RCAffinityIndex

            self._rc_index = RCAffinityIndex()
            native_dir = self.skills_dir / "native"
            if native_dir.is_dir():
                self._rc_index.load_from_skills_dir(str(native_dir))
            elif self.skills_dir.is_dir():
                # 舊結構：直接掃描 skills/
                self._rc_index.load_from_skills_dir(str(self.skills_dir))

            stats = self._rc_index.stats
            logger.info(
                f"[DNA27→Skill] RC affinity index loaded: "
                f"{stats['loaded_skills']} skills, "
                f"{stats['rc_clusters_with_preferred']} RC clusters → "
                f"{stats['total_preferred_links']} preferred links, "
                f"{stats['total_prohibited_links']} prohibited links"
            )
        except Exception as e:
            logger.warning(f"RC affinity index load failed (falling back to keyword-only): {e}")
            self._rc_index = None

    def _subscribe_events(self) -> None:
        """訂閱 Morphenix/DNA27 事件 → 自動熱重載索引."""
        if not self._event_bus:
            return
        try:
            from museon.core.event_bus import (
                MORPHENIX_EXECUTION_COMPLETED,
                DNA27_WEIGHTS_UPDATED,
            )
            self._event_bus.subscribe(
                MORPHENIX_EXECUTION_COMPLETED, self._on_morphenix_completed
            )
            self._event_bus.subscribe(
                DNA27_WEIGHTS_UPDATED, self._on_dna27_updated
            )
        except Exception as e:
            logger.debug(f"SkillRouter event subscription failed: {e}")

    def _on_morphenix_completed(self, data=None) -> None:
        """Morphenix 執行完成 → 檢查是否影響技能，需要重載索引."""
        try:
            affected = []
            if data and isinstance(data, dict):
                for detail in data.get("details", []):
                    affected.extend(detail.get("affected_skills", []))
            if affected or (data and data.get("executed", 0) > 0):
                self.rebuild_index()
                logger.info(
                    f"[SkillRouter] hot-reload after Morphenix "
                    f"(affected_skills={affected})"
                )
                if self._event_bus:
                    from museon.core.event_bus import SKILL_ROUTER_RELOADED
                    self._event_bus.publish(SKILL_ROUTER_RELOADED, {
                        "trigger": "morphenix",
                        "skill_count": self.get_skill_count(),
                    })
        except Exception as e:
            logger.warning(f"SkillRouter hot-reload failed: {e}")

    def _on_dna27_updated(self, data=None) -> None:
        """DNA27 權重更新 → 重建 RC 索引."""
        try:
            self._build_rc_index()
            logger.info("[SkillRouter] RC index rebuilt after DNA27 update")
            if self._event_bus:
                from museon.core.event_bus import SKILL_ROUTER_RELOADED
                self._event_bus.publish(SKILL_ROUTER_RELOADED, {
                    "trigger": "dna27_weights",
                    "skill_count": self.get_skill_count(),
                })
        except Exception as e:
            logger.warning(f"SkillRouter RC rebuild failed: {e}")

    # 演化模式優先技能
    _EVOLUTION_SKILLS = {"morphenix", "wee", "dse", "sandbox-lab", "eval-engine"}

    # 市場/商業類技能（安全觸發時降權）
    _MARKET_SKILLS = {
        "market-core", "market-equity", "market-crypto", "market-macro",
        "investment-masters", "sentiment-radar", "risk-matrix",
        "business-12", "ssa-consultant",
    }

    def match(
        self,
        message: str,
        top_n: int = 5,
        routing_signal: Any = None,
        skill_usage: Optional[Dict[str, int]] = None,
        user_primals: Optional[Dict[str, int]] = None,
        signal_cache: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """v10.5 四層疊加匹配 — RC 驅動 + 關鍵字 + 向量 + 八原語 + MoE 衰減.

        Layer 1: RC 驅動（權重 ×5.0）
          - 從 routing_signal.top_clusters 取得觸發的 RC
          - 查詢 RCAffinityIndex（skill 自己宣告的 RC 親和）
          - 禁止的 skill 被自動壓制

        Layer 2: 關鍵字匹配
          - 觸發詞 + /command + 名稱 + 描述詞

        Layer 3: Qdrant 向量語義搜尋
          - 語義相似度補充

        Layer 4: ★ v10.5 八原語親和評分
          - 使用者當前原語 × 技能原語親和度

        最終分數 = (RC × 5.0 + kw + vec × 1.5 + primal × 2.0) × usage_decay

        ★ v10.4 Route B: MoE-style usage frequency decay
          - 借鏡 MoE auxiliary load balancing loss
          - 頻繁使用的 skill 自動衰減，防止壟斷
          - always_on 超過 3 次額外打折

        DNA27 RoutingSignal 調節：
          - Loop → effective_top_n
          - Mode → EVOLUTION_MODE boost
          - Safety → 市場/商業降權 + 高強度覆寫

        Args:
            message: 使用者訊息
            top_n: 返回前 N 個匹配結果
            routing_signal: DNA27 RoutingSignal（可選）
            skill_usage: ★ v10.4 Route B — {skill_name: usage_count} session 內使用次數
            user_primals: ★ v10.5 — {primal_key: level(0-100)} 使用者八原語

        Returns:
            匹配到的技能列表，按相關度排序
        """
        if not self._index:
            return []

        # ── 維度 1: Loop 調節 effective_top_n ──
        effective_top_n = top_n
        if routing_signal:
            try:
                loop = routing_signal.loop
                if loop == "FAST_LOOP":
                    effective_top_n = min(top_n, 3)
                elif loop == "SLOW_LOOP":
                    effective_top_n = top_n + 2
                # EXPLORATION_LOOP → 維持原 top_n
            except Exception as e:
                logger.debug(f"[SKILL_ROUTER] operation failed (degraded): {e}")

        # ── Layer 1: DNA27 RC 驅動 — 從 skill 自己的 RC 親和宣告匹配 ──
        rc_scores: Dict[str, float] = {}
        suppressed_skills: Set[str] = set()
        safety_override = False
        is_evolution = False
        safety_downweight = False
        fired_clusters: List[str] = []

        if routing_signal:
            try:
                # 提取 RC cluster IDs（去除後綴，如 RC-A1_energy_depletion → RC-A1）
                fired_clusters = [
                    c.split("_")[0].upper()
                    for c in routing_signal.top_clusters
                    if c
                ]

                # v10: 用 RCAffinityIndex（skill 自己宣告的 RC 親和）
                if self._rc_index and fired_clusters:
                    rc_scores = self._rc_index.get_skills_for_clusters(fired_clusters)
                    # v10.2: 傳入叢集分數，只在 RC 分數 >= 0.5 時才壓制
                    _cs = getattr(routing_signal, "cluster_scores", None) or {}
                    suppressed_skills = self._rc_index.get_suppressed_skills(
                        fired_clusters, cluster_scores=_cs,
                    )

                # Mode 過濾
                if routing_signal.mode == "EVOLUTION_MODE":
                    is_evolution = True
                elif routing_signal.tier_scores.get("A", 0) >= 0.5:
                    safety_downweight = True

                # 高強度安全覆寫
                if routing_signal.tier_scores.get("A", 0) >= 1.5:
                    safety_override = True
            except Exception as e:
                logger.debug(f"RC scoring error: {e}")

        # ── Layer 3: Qdrant 向量語義搜尋 ──
        vector_scores = self._vector_search_skills(message, effective_top_n * 2)

        # ── 三層疊加評分 ──
        scored: List[Tuple[float, Dict[str, Any]]] = []
        msg_lower = message.lower()

        for skill in self._index:
            skill_name = skill.get("name", "")

            # 被 RC 禁止的 skill → 壓制
            if skill_name in suppressed_skills:
                continue

            # ── Layer 2: 關鍵字匹配 ──
            kw_score = 0.0

            # v10.3: Always-on 底分從 0.5 再降至 0.2
            # shadow/c15 在 v10.2 出現 26 次但只有 30% 成功——底分太高搶走精準 skill 的位置
            if skill.get("always_on"):
                kw_score += 0.2

            # Check trigger words
            for trigger in skill.get("triggers", []):
                trigger_lower = trigger.lower()
                if trigger_lower in msg_lower:
                    kw_score += 3.0
                elif len(trigger_lower) > 2:
                    for word in msg_lower.split():
                        if trigger_lower in word or word in trigger_lower:
                            kw_score += 1.0
                            break

            # Check name match
            name = skill_name.lower()
            if name in msg_lower:
                kw_score += 2.0

            # Check description keywords
            desc = skill.get("description", "").lower()
            for word in msg_lower.split():
                if len(word) > 2 and word in desc:
                    kw_score += 0.5

            # Check /command match (最高優先)
            if message.startswith("/"):
                cmd = message.split()[0].lower()
                for trigger in skill.get("triggers", []):
                    if trigger.lower() == cmd:
                        kw_score += 10.0

            # ── DNA27 RoutingSignal 調節 ──
            if routing_signal:
                # EVOLUTION_MODE → 演化技能 boost
                if is_evolution and skill_name in self._EVOLUTION_SKILLS:
                    kw_score += 2.0

                # 安全觸發 → 市場/商業技能降權
                v_score_check = vector_scores.get(skill_name, 0.0)
                if safety_downweight and skill_name in self._MARKET_SKILLS:
                    if v_score_check >= 0.3:
                        kw_score *= 0.7  # 語意相關 → 輕微降權
                    else:
                        kw_score *= 0.3  # 無語意相關 → 重度降權

                # 高強度安全覆寫 — 只保留 always-on + RC 親和技能
                if safety_override:
                    if not skill.get("always_on") and skill_name not in rc_scores:
                        kw_score = 0.0

            # ── v10.5 四層疊加：RC × rc_weight + keyword + vector × 1.5 + primal × 2.0 ──
            # RC 預設 5.0（DNA27 反射弧是核心驅動，必須主導）
            # ★ v10.5: 短訊息 + 弱 RC 信號 → 動態降權至 2.0（讓語義有機會補正）
            # Vector 降至 1.5（語義補充，不應蓋過神經迴路信號）
            # Primal 2.0（八原語親和——使用者驅力影響技能選擇）
            rc_s = rc_scores.get(skill_name, 0.0)
            v_score = vector_scores.get(skill_name, 0.0)

            _rc_weight = 5.0
            if len(message.strip()) < 20 and rc_s < 0.3 and rc_s > 0:
                _rc_weight = 2.0

            # ── Layer 4: 八原語親和評分 ──
            primal_score = 0.0
            if user_primals:
                try:
                    from museon.agent.primal_detector import DEFAULT_SKILL_PRIMAL_AFFINITY
                    affinity = DEFAULT_SKILL_PRIMAL_AFFINITY.get(skill_name, {})
                    if affinity:
                        for pk, aff in affinity.items():
                            user_level = user_primals.get(pk, 0)
                            if user_level > 0:
                                primal_score += (user_level / 100.0) * aff
                except Exception:
                    pass

            combined = rc_s * _rc_weight + kw_score + v_score * 1.5 + primal_score * 2.0

            # ── ★ Layer 5: Signal Cache 訊號加權（×3.0）──
            if signal_cache:
                _suggested = signal_cache.get("suggested_skills", [])
                for _skill_name in _suggested:
                    if _skill_name == skill_name:
                        combined += 3.0
                        logger.debug(f"[SkillRouter] Signal boost: {skill_name} +3.0")

            # /command 匹配的絕對優先（不受 usage decay 影響）
            is_command_match = kw_score >= 10.0
            if is_command_match:
                combined = max(combined, 15.0)

            # ── v10.4 Route B: MoE-style usage frequency decay ──
            # 借鏡 MoE auxiliary load balancing loss
            # 頻繁使用的 skill 自動衰減，防止 shadow/c15 壟斷
            if skill_usage and skill_name in skill_usage and not is_command_match:
                usage_count = skill_usage[skill_name]
                # 衰減公式: 1/(1 + count × 0.15) — 溫和衰減
                # count=1 → 0.87, count=3 → 0.69, count=5 → 0.57
                decay = 1.0 / (1.0 + usage_count * 0.15)
                combined *= decay
                # always_on 超過 3 次額外打折（解決 shadow/c15 壟斷）
                if skill.get("always_on") and usage_count >= 3:
                    combined *= 0.5

            if combined > 0:
                scored.append((combined, skill))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # v10.2 Fix: 加入 combined score 詳細 logging（debug 可見三層分數）
        if scored:
            top_detail = [
                f"{s[1].get('name','')}={s[0]:.1f}"
                f"(rc={rc_scores.get(s[1].get('name',''),0):.2f}×5"
                f"+kw={s[0]-rc_scores.get(s[1].get('name',''),0)*5.0-vector_scores.get(s[1].get('name',''),0)*1.5:.1f}"
                f"+vec={vector_scores.get(s[1].get('name',''),0):.2f}×1.5)"
                for s in scored[:8]
            ]
            logger.debug(
                f"[DNA27→Skill] combined_top8: {', '.join(top_detail)}"
            )

        # ── v10.1 RC 保底機制：確保前 2 名 RC-matched skills 進入結果 ──
        # 問題：always-on + vector 分數可能把所有 RC-matched skills 推出 top-N
        # 修正：找出 RC scored skills，如果它們不在 top-N，替換掉最後的 slot
        result = [s[1] for s in scored[:effective_top_n]]
        result_names = {s.get("name", "") for s in result}

        if rc_scores:
            # 按 RC 分數排序，取前 2 名 RC-matched skills
            rc_ranked = sorted(rc_scores.items(), key=lambda x: x[1], reverse=True)
            rc_guarantee_count = min(2, len(rc_ranked))

            for i in range(rc_guarantee_count):
                rc_skill_name = rc_ranked[i][0]
                # v10.2 Fix: RC 保底不得覆蓋 suppressed_skills（安全壓制優先）
                if rc_skill_name in suppressed_skills:
                    continue
                if rc_skill_name not in result_names:
                    # 找到這個 skill 的完整 metadata
                    rc_skill_meta = None
                    for sc, sk in scored:
                        if sk.get("name") == rc_skill_name:
                            rc_skill_meta = sk
                            break
                    if rc_skill_meta:
                        # 替換 result 最後一個（最低分的）slot
                        if len(result) >= effective_top_n:
                            result[-1] = rc_skill_meta
                        else:
                            result.append(rc_skill_meta)
                        result_names.add(rc_skill_name)

        if routing_signal and (rc_scores or fired_clusters):
            top_rc = dict(sorted(rc_scores.items(), key=lambda x: x[1], reverse=True)[:5])
            # v10.1: 加入 vector 分數 logging（debug 可見性）
            top_vec = dict(sorted(vector_scores.items(), key=lambda x: x[1], reverse=True)[:5])
            logger.info(
                f"[DNA27→Skill] fired_clusters={fired_clusters}, "
                f"rc_top5={top_rc}, "
                f"vec_top5={top_vec}, "
                f"suppressed={suppressed_skills}, "
                f"safety_override={safety_override}, "
                f"evolution={is_evolution}, "
                f"effective_top_n={effective_top_n}"
            )

        return result

    def get_always_on_skills(self) -> List[Dict[str, Any]]:
        """取得常駐技能 (dna27, deep-think, c15)."""
        return [s for s in self._index if s.get("always_on")]

    def load_skill_content(self, skill: Dict[str, Any]) -> str:
        """載入技能的完整內容.

        Args:
            skill: 技能 metadata dict

        Returns:
            技能的 Markdown 內容
        """
        path = Path(skill.get("path", ""))
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception as e:
                logger.debug(f"[SKILL_ROUTER] data read failed (degraded): {e}")
        return ""

    def load_skill_summary(self, skill: Dict[str, Any]) -> str:
        """載入技能的摘要（節省 token）.

        只提取 name + description + 觸發時機 + 核心規則.

        Args:
            skill: 技能 metadata dict

        Returns:
            技能摘要
        """
        name = skill.get("name", "unknown")
        desc = skill.get("description", "")
        return f"【{name}】{desc}"

    def get_skill_count(self) -> int:
        """取得已索引的技能數量."""
        return len(self._index)

    def rebuild_index(self) -> None:
        """重建索引（含 RC 親和索引）."""
        self._build_index()
        self._build_rc_index()

    @property
    def rc_affinity_stats(self) -> Dict[str, int]:
        """RC 親和索引統計（供外部查詢）."""
        if self._rc_index:
            return self._rc_index.stats
        return {"loaded_skills": 0, "rc_clusters_with_preferred": 0}
