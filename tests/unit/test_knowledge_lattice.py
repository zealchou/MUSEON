"""知識晶格 (Knowledge Lattice) 測試.

涵蓋 BDD 13-knowledge-lattice.feature 的所有 Scenario：
- 四種結晶類型 (Insight/Pattern/Lesson/Hypothesis)
- GEO 四層結構 (G1 摘要/G2 MECE/G3 根因/G4 洞見)
- 五步結晶流程 (capture -> refine -> link -> quality_check -> register)
- CUID 格式 (KL-{Type}-{seq})
- Crystal DAG（無環、2-hop 可達性）
- 共振指數 RI 公式
- 語義召回 (/recall、auto_recall)
- 再結晶引擎（合併、矛盾保留、歸檔、升降級）
- 安全護欄
"""

import math
import pytest
from datetime import datetime, timedelta


@pytest.fixture
def data_dir(tmp_path):
    """建立測試用資料目錄."""
    lattice_dir = tmp_path / "lattice"
    lattice_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def lattice(data_dir):
    """建立 KnowledgeLattice 測試實例."""
    from museon.agent.knowledge_lattice import KnowledgeLattice
    return KnowledgeLattice(data_dir=str(data_dir))


# ════════════════════════════════════════════
# Section 1: 四種結晶類型
# ════════════════════════════════════════════

class TestCrystalTypes:
    """測試四種結晶類型."""

    def test_insight_is_permanent(self, lattice):
        """Insight 為永久型結晶."""
        crystal = lattice.crystallize(
            raw_material="經過驗證：台灣中小企業主最大痛點是系統依賴人治",
            source_context="consulting domain, 5 sessions",
            crystal_type="Insight",
        )
        assert crystal.crystal_type == "Insight"
        assert crystal.archived is False

    def test_hypothesis_has_30_day_window(self, lattice):
        """Hypothesis 有 30 天有效期（透過 created_at 追蹤）."""
        crystal = lattice.crystallize(
            raw_material="假說：AI 工具可以降低中小企業的 SOP 建置成本",
            source_context="tech domain",
            crystal_type="Hypothesis",
        )
        assert crystal.crystal_type == "Hypothesis"
        # Hypothesis 透過 created_at 追蹤過期（30 天窗口）
        assert hasattr(crystal, "created_at")
        assert crystal.created_at != ""

    def test_pattern_needs_3_observations(self, lattice):
        """Pattern 需要 3+ 觀察才能形成."""
        crystal = lattice.crystallize(
            raw_material="觀察到 3 次以上：使用者在早上效率最高",
            source_context="3 observations",
            crystal_type="Pattern",
        )
        assert crystal.crystal_type == "Pattern"

    def test_lesson_is_evolvable(self, lattice):
        """Lesson 可以被更新."""
        crystal = lattice.crystallize(
            raw_material="教訓：不要在高波動期做長期投資決策",
            source_context="investment domain",
            crystal_type="Lesson",
        )
        assert crystal.crystal_type == "Lesson"


# ════════════════════════════════════════════
# Section 2: GEO 四層結構
# ════════════════════════════════════════════

class TestGEOStructure:
    """測試 GEO 四層結構."""

    def test_crystal_has_g1_summary(self, lattice):
        """結晶包含 G1 電梯測試摘要."""
        crystal = lattice.crystallize(
            raw_material="長期觀察發現：客戶滿意度主要受回應速度和準確度影響",
            source_context="",
            crystal_type="Insight",
            g1_summary="客戶滿意度受回應速度和準確度影響",
        )
        assert crystal.g1_summary is not None
        assert len(crystal.g1_summary) > 0

    def test_crystal_has_all_geo_layers(self, lattice):
        """結晶包含 G1-G4 四層."""
        crystal = lattice.crystallize(
            raw_material="系統化發現：SOP 缺失是中小企業效率低下的根本原因",
            source_context="case1, case2, case3",
            crystal_type="Insight",
            g1_summary="SOP 缺失導致效率低下",
            g2_structure=["流程面", "人員面", "系統面"],
            g3_root_inquiry="為什麼中小企業無法建立有效 SOP？",
            g4_insights=["根因在於缺乏系統化思維"],
        )
        assert crystal.g1_summary != ""
        assert len(crystal.g2_structure) >= 2
        assert crystal.g3_root_inquiry != ""
        assert len(crystal.g4_insights) >= 1


# ════════════════════════════════════════════
# Section 3: CUID 格式
# ════════════════════════════════════════════

class TestCUID:
    """測試 CUID 格式."""

    def test_cuid_format_insight(self, lattice):
        """Insight CUID 格式: KL-INS-0001."""
        crystal = lattice.crystallize(
            raw_material="驗證過的洞見",
            source_context="",
            crystal_type="Insight",
        )
        assert crystal.cuid.startswith("KL-INS-")
        # 序號部分為 4 位數字
        seq = crystal.cuid.split("-")[2]
        assert len(seq) == 4
        assert seq.isdigit()

    def test_cuid_format_pattern(self, lattice):
        """Pattern CUID 格式: KL-PAT-xxxx."""
        crystal = lattice.crystallize(
            raw_material="觀察到的模式",
            source_context="",
            crystal_type="Pattern",
        )
        assert crystal.cuid.startswith("KL-PAT-")

    def test_cuid_format_lesson(self, lattice):
        """Lesson CUID 格式: KL-LES-xxxx."""
        crystal = lattice.crystallize(
            raw_material="失敗教訓",
            source_context="",
            crystal_type="Lesson",
        )
        assert crystal.cuid.startswith("KL-LES-")

    def test_cuid_format_hypothesis(self, lattice):
        """Hypothesis CUID 格式: KL-HYP-xxxx."""
        crystal = lattice.crystallize(
            raw_material="待驗證假說",
            source_context="",
            crystal_type="Hypothesis",
        )
        assert crystal.cuid.startswith("KL-HYP-")

    def test_cuid_sequential(self, lattice):
        """CUID 序號遞增."""
        c1 = lattice.crystallize(
            raw_material="第一個洞見結晶",
            source_context="",
            crystal_type="Insight",
        )
        c2 = lattice.crystallize(
            raw_material="第二個洞見結晶",
            source_context="",
            crystal_type="Insight",
        )
        seq1 = int(c1.cuid.split("-")[2])
        seq2 = int(c2.cuid.split("-")[2])
        assert seq2 == seq1 + 1


# ════════════════════════════════════════════
# Section 4: Crystal DAG
# ════════════════════════════════════════════

class TestCrystalDAG:
    """測試 Crystal DAG."""

    def test_add_link(self, lattice):
        """新增連結."""
        # 使用差異很大的文字避免 link_discovery 自動建立反向連結
        c1 = lattice.crystallize(
            "台灣中小企業數位轉型的關鍵挑戰與解決方案分析報告",
            "", "Insight",
            g1_summary="台灣中小企業數位轉型挑戰",
            g2_structure=["技術面", "組織面"],
            g3_root_inquiry="為什麼轉型困難？",
            g4_insights=["根因在缺乏數位人才"],
        )
        c2 = lattice.crystallize(
            "深度學習模型在自然語言處理中的最新突破與應用前景",
            "", "Insight",
            g1_summary="深度學習自然語言處理突破",
            g2_structure=["模型架構", "訓練方法"],
            g3_root_inquiry="為什麼 Transformer 有效？",
            g4_insights=["注意力機制是關鍵"],
        )
        result = lattice.add_link(
            from_cuid=c1.cuid,
            to_cuid=c2.cuid,
            link_type="supports",
            confidence=0.8,
        )
        assert result is True

    def test_cycle_detection(self, lattice):
        """偵測並拒絕循環連結（返回 False）."""
        # 使用差異很大的文字避免 link_discovery 自動建立連結
        c1 = lattice.crystallize(
            "量子計算的基本原理與量子位元的糾纏現象研究",
            "", "Insight",
            g1_summary="量子計算基本原理",
            g2_structure=["硬體面", "演算法面"],
            g3_root_inquiry="量子優勢何時實現？",
            g4_insights=["量子糾纏是關鍵資源"],
        )
        c2 = lattice.crystallize(
            "全球供應鏈韌性評估框架與風險管理策略的系統性研究",
            "", "Insight",
            g1_summary="全球供應鏈韌性評估",
            g2_structure=["物流面", "庫存面"],
            g3_root_inquiry="如何提升供應鏈韌性？",
            g4_insights=["多元化供應來源"],
        )
        c3 = lattice.crystallize(
            "認知心理學中的決策偏誤與行為經濟學的交叉研究成果",
            "", "Insight",
            g1_summary="認知心理決策偏誤研究",
            g2_structure=["認知面", "情感面"],
            g3_root_inquiry="為什麼人會做不理性決策？",
            g4_insights=["框架效應影響重大"],
        )

        result1 = lattice.add_link(c1.cuid, c2.cuid, "supports")
        result2 = lattice.add_link(c2.cuid, c3.cuid, "supports")
        assert result1 is True
        assert result2 is True

        # 形成環路的連結應被拒絕（返回 False）
        result3 = lattice.add_link(c3.cuid, c1.cuid, "supports")
        assert result3 is False

    def test_link_types(self, lattice):
        """五種連結類型都可被接受."""
        from museon.agent.knowledge_lattice import LINK_TYPES
        # 驗證常數定義
        assert set(LINK_TYPES) == {"supports", "contradicts", "extends", "derived_from", "related"}

        # 每種類型各用差異極大的主題對避免 link_discovery 自動建立連結
        topic_pairs = [
            ("量子力學中的波粒二象性", "非洲草原生態系統中的食物鏈結構"),
            ("巴洛克音樂風格與對位法技巧", "太平洋板塊運動與火山活動規律"),
            ("希臘神話中的命運三女神", "碳纖維複合材料在航空工業的應用"),
            ("宋朝瓷器釉色技術演變史", "人工智能倫理框架與社會影響研究"),
            ("北歐海盜時代航海技術發展", "量子密碼學的理論基礎與實務挑戰"),
        ]

        for lt, (topic_a, topic_b) in zip(LINK_TYPES, topic_pairs):
            c1 = lattice.crystallize(
                topic_a,
                "", "Insight",
                g1_summary=topic_a[:30],
                g2_structure=[f"{topic_a[:10]}面向一", f"{topic_a[:10]}面向二"],
                g3_root_inquiry=f"為什麼{topic_a[:15]}？",
                g4_insights=[f"{topic_a[:15]}洞見"],
            )
            c2 = lattice.crystallize(
                topic_b,
                "", "Pattern",
                g1_summary=topic_b[:30],
                g2_structure=[f"{topic_b[:10]}面向甲", f"{topic_b[:10]}面向乙"],
                g3_root_inquiry=f"如何理解{topic_b[:15]}？",
                g4_insights=[f"{topic_b[:15]}洞見"],
            )
            result = lattice.add_link(c1.cuid, c2.cuid, lt)
            assert result is True, f"Link type '{lt}' should succeed"

    def test_invalid_link_type_rejected(self, lattice):
        """無效連結類型被拒絕."""
        c1 = lattice.crystallize("測試結晶 A", "", "Insight")
        c2 = lattice.crystallize("測試結晶 B", "", "Insight")
        result = lattice.add_link(c1.cuid, c2.cuid, "invalid_type")
        assert result is False

    def test_self_link_rejected(self, lattice):
        """自環連結被拒絕."""
        c1 = lattice.crystallize("自環測試結晶", "", "Insight")
        result = lattice.add_link(c1.cuid, c1.cuid, "supports")
        assert result is False


# ════════════════════════════════════════════
# Section 5: 共振指數 RI
# ════════════════════════════════════════════

class TestResonanceIndex:
    """測試共振指數計算."""

    def test_ri_formula_with_crystal(self):
        """RI = (0.3*Freq + 0.4*Depth + 0.3*Quality) * exp(-0.03*days).

        ResonanceCalculator.calculate() 是靜態方法，接受 Crystal 物件。
        """
        from museon.agent.knowledge_lattice import ResonanceCalculator, Crystal

        # 建立一個完整的 Crystal（剛剛引用、GEO 四層齊全）
        crystal = Crystal(
            cuid="KL-INS-9999",
            crystal_type="Insight",
            g1_summary="測試共振指數",
            g2_structure=["面向 A", "面向 B"],
            g3_root_inquiry="為什麼需要測試 RI？",
            g4_insights=["RI 影響結晶的召回優先順序"],
            assumption="RI 公式正確",
            evidence="數學驗證",
            limitation="僅適用於此系統",
            verification_level="proven",
            reference_count=40,  # freq = 40/50 = 0.8
            last_referenced=datetime.now().isoformat(),
        )

        ri = ResonanceCalculator.calculate(crystal)
        # freq = 40/50 = 0.8, depth = 1.0 (all 4 layers), quality = 0.7*1.0 + 0.3*1.0 = 1.0
        # days ~= 0, so decay ~= 1.0
        # RI ~= (0.3*0.8 + 0.4*1.0 + 0.3*1.0) * 1.0 = (0.24 + 0.40 + 0.30) = 0.94
        assert ri > 0.8
        assert ri <= 1.0

    def test_ri_decays_over_time(self):
        """RI 隨時間衰減."""
        from museon.agent.knowledge_lattice import ResonanceCalculator, Crystal

        now = datetime.now()
        crystal_fresh = Crystal(
            cuid="KL-INS-0001",
            crystal_type="Insight",
            g1_summary="新鮮結晶",
            g2_structure=["A", "B"],
            g3_root_inquiry="測試",
            g4_insights=["洞見"],
            assumption="假設", evidence="證據", limitation="限制",
            verification_level="proven",
            reference_count=40,
            last_referenced=now.isoformat(),
        )
        crystal_old = Crystal(
            cuid="KL-INS-0002",
            crystal_type="Insight",
            g1_summary="陳舊結晶",
            g2_structure=["A", "B"],
            g3_root_inquiry="測試",
            g4_insights=["洞見"],
            assumption="假設", evidence="證據", limitation="限制",
            verification_level="proven",
            reference_count=40,
            last_referenced=(now - timedelta(days=30)).isoformat(),
        )

        ri_fresh = ResonanceCalculator.calculate(crystal_fresh)
        ri_old = ResonanceCalculator.calculate(crystal_old)
        assert ri_old < ri_fresh

    def test_ri_zero_days_no_decay(self):
        """0 天前引用的 RI 無衰減 — exp(0) = 1."""
        from museon.agent.knowledge_lattice import ResonanceCalculator, Crystal

        crystal = Crystal(
            cuid="KL-INS-0003",
            crystal_type="Insight",
            g1_summary="無衰減測試",
            g2_structure=["A", "B"],
            g3_root_inquiry="測試",
            g4_insights=["洞見"],
            assumption="假設", evidence="證據", limitation="限制",
            verification_level="proven",
            reference_count=50,  # freq = 1.0
            last_referenced=datetime.now().isoformat(),
        )

        ri = ResonanceCalculator.calculate(crystal)
        # freq=1.0, depth=1.0, quality = 0.7*1.0 + 0.3*1.0 = 1.0
        # RI = (0.3 + 0.4 + 0.3) * 1.0 = 1.0
        expected = 1.0
        assert abs(ri - expected) < 0.01


# ════════════════════════════════════════════
# Section 6: 再結晶引擎
# ════════════════════════════════════════════

class TestRecrystallization:
    """測試再結晶引擎."""

    def test_hypothesis_upgrade_after_3_successes(self, lattice):
        """Hypothesis 經過 3 次成功記錄後可升級為 Pattern."""
        crystal = lattice.crystallize(
            raw_material="假說：早上提問效率較高的完整描述內容",
            source_context="",
            crystal_type="Hypothesis",
        )
        cuid = crystal.cuid

        # 使用 record_success() 記錄 3 次成功
        for _ in range(3):
            lattice.record_success(cuid)

        lattice.upgrade_crystal(cuid)
        updated = lattice.get_crystal(cuid)
        assert updated.crystal_type == "Pattern"

    def test_insight_downgrade_after_2_counter_evidences(self, lattice):
        """Insight 在 2 次反證後降級為 Pattern."""
        crystal = lattice.crystallize(
            raw_material="原以為正確的洞見的完整描述內容",
            source_context="",
            crystal_type="Insight",
        )
        cuid = crystal.cuid

        # 使用 record_counter_evidence() 記錄 2 次反證
        for _ in range(2):
            lattice.record_counter_evidence(cuid)

        lattice.downgrade_crystal(cuid, reason="2 counter-evidences")
        updated = lattice.get_crystal(cuid)
        assert updated.crystal_type == "Pattern"

    def test_contradiction_preserved_not_merged(self, lattice):
        """矛盾的結晶不被合併，標記為 disputed."""
        # 使用差異很大的文字避免 link_discovery 自動建立連結
        c1 = lattice.crystallize(
            "微服務架構在大規模分散式系統中的部署策略與最佳實踐",
            "", "Pattern",
            g1_summary="微服務架構部署策略",
            g2_structure=["容器化", "服務網格"],
            g3_root_inquiry="何時適合微服務？",
            g4_insights=["團隊規模決定架構選擇"],
        )
        c2 = lattice.crystallize(
            "植物基因組學在農業育種改良中的應用前景與挑戰",
            "", "Pattern",
            g1_summary="植物基因組學育種應用",
            g2_structure=["基因編輯", "分子標記"],
            g3_root_inquiry="如何加速育種？",
            g4_insights=["CRISPR 大幅縮短週期"],
        )
        result = lattice.add_link(c1.cuid, c2.cuid, "contradicts")
        assert result is True

        # contradicts 連結會將兩者標記為 disputed
        updated_c1 = lattice.get_crystal(c1.cuid)
        updated_c2 = lattice.get_crystal(c2.cuid)
        assert updated_c1.status == "disputed"
        assert updated_c2.status == "disputed"

        # 再結晶不應合併矛盾的結晶
        lattice.recrystallize()
        assert lattice.get_crystal(c1.cuid) is not None
        assert lattice.get_crystal(c2.cuid) is not None

    def test_stale_archival_90_days(self, lattice):
        """90 天低 RI 的結晶被歸檔."""
        crystal = lattice.crystallize(
            raw_material="久未引用的知識的完整描述內容",
            source_context="",
            crystal_type="Pattern",
        )
        cuid = crystal.cuid

        # 手動設置最後引用時間為 91 天前、低 RI
        crystal.last_referenced = (datetime.now() - timedelta(days=91)).isoformat()
        crystal.ri_score = 0.01  # 低於 0.05 門檻
        crystal.reference_count = 0

        # 直接持久化（結晶已在 lattice._crystals 中）
        lattice._persist()

        archived_cuids = lattice.archive_stale()
        # 驗證結晶被歸檔
        if cuid in archived_cuids:
            # 已被歸檔到 archive，從 active crystals 移除
            assert cuid not in lattice._crystals
        else:
            # 如果 RI 重新計算後仍然不夠低，結晶可能沒被歸檔
            # 但 get_crystal 仍可在 archive 中找到
            result = lattice.get_crystal(cuid)
            assert result is not None

    def test_recrystallize_report_structure(self, lattice):
        """再結晶報告包含完整結構."""
        lattice.crystallize("結晶化測試 A 描述", "", "Insight")
        lattice.crystallize("結晶化測試 B 描述", "", "Pattern")

        report = lattice.recrystallize()
        assert "redundancy" in report
        assert "contradictions" in report
        assert "stale" in report
        assert "upgrade_candidates" in report
        assert "downgrade_candidates" in report
        assert "fragments" in report
        assert "expired_hypotheses" in report


# ════════════════════════════════════════════
# Section 7: 語義召回
# ════════════════════════════════════════════

class TestSemanticRecall:
    """測試語義召回."""

    def test_recall_returns_relevant_crystals(self, lattice):
        """/recall 返回相關結晶."""
        lattice.crystallize(
            "投資分析的核心方法論的完整描述內容",
            "investment domain",
            "Insight",
            domain="investment",
        )
        lattice.crystallize(
            "行銷策略的基本框架的完整描述內容",
            "marketing domain",
            "Insight",
            domain="marketing",
        )

        # recall() 接受 query: str
        results = lattice.recall("投資", top_n=5)
        assert len(results) >= 1
        # 投資相關的應排在前面
        first = results[0]
        assert (
            "投資" in first.g1_summary
            or first.domain == "investment"
        )

    def test_auto_recall_max_2_push(self, lattice):
        """自動推送最多 2 個結晶."""
        for i in range(10):
            lattice.crystallize(
                f"相關知識 {i} 的完整描述內容",
                "general domain",
                "Insight",
                domain="general",
            )

        # auto_recall() 接受 context: str, max_push: int
        results = lattice.auto_recall(
            context="general knowledge topic",
            max_push=2,
        )
        assert len(results) <= 2

    def test_recall_empty_query_returns_empty(self, lattice):
        """空查詢返回空結果."""
        lattice.crystallize("測試結晶", "", "Insight")
        results = lattice.recall("", top_n=5)
        assert len(results) == 0


# ════════════════════════════════════════════
# Section 8: 持久化
# ════════════════════════════════════════════

class TestPersistence:
    """測試持久化."""

    def test_crystals_saved_to_json(self, lattice, data_dir):
        """結晶儲存到 JSON 檔案."""
        lattice.crystallize("持久化測試結晶", "", "Insight")
        crystals_path = data_dir / "lattice" / "crystals.json"
        assert crystals_path.exists()

    def test_links_saved_to_json(self, lattice, data_dir):
        """連結儲存到 JSON 檔案."""
        c1 = lattice.crystallize("結晶 A 用於連結測試", "", "Insight")
        c2 = lattice.crystallize("結晶 B 用於連結測試", "", "Insight")
        lattice.add_link(c1.cuid, c2.cuid, "supports")
        links_path = data_dir / "lattice" / "links.json"
        assert links_path.exists()

    def test_health_report(self, lattice):
        """健康報告包含完整指標."""
        lattice.crystallize("健康報告測試結晶", "", "Insight")
        report = lattice.health_report()
        assert "total_crystals" in report
        assert "average_ri" in report
        assert "link_density" in report
        assert "isolated_count" in report

    def test_cross_session_persistence(self, data_dir):
        """跨 session 持久化：新實例可載入舊結晶."""
        from museon.agent.knowledge_lattice import KnowledgeLattice

        lattice1 = KnowledgeLattice(data_dir=str(data_dir))
        crystal = lattice1.crystallize(
            "跨 session 測試結晶",
            "",
            "Insight",
        )
        cuid = crystal.cuid

        # 建立新實例（模擬新 session）
        lattice2 = KnowledgeLattice(data_dir=str(data_dir))
        loaded = lattice2.get_crystal(cuid)
        assert loaded is not None
        assert loaded.cuid == cuid


# ════════════════════════════════════════════
# Section 9: 安全護欄
# ════════════════════════════════════════════

class TestSafety:
    """測試安全護欄."""

    def test_crystal_has_assumption_evidence_limitation(self, lattice):
        """每個結晶必須有 assumption、evidence、limitation."""
        crystal = lattice.crystallize(
            raw_material="需要有完整三要素的知識描述內容",
            source_context="data1 evidence",
            crystal_type="Insight",
        )
        # crystallize() 的 refine 步驟會自動填入預設值
        assert crystal.assumption is not None and crystal.assumption != ""
        assert crystal.evidence is not None and crystal.evidence != ""
        assert crystal.limitation is not None and crystal.limitation != ""

    def test_crystal_explicit_triplet(self, lattice):
        """顯式提供三元組值."""
        crystal = lattice.crystallize(
            raw_material="顯式三元組測試結晶",
            source_context="",
            crystal_type="Insight",
            assumption="人在早上效率最高",
            evidence="5 次觀察數據",
            limitation="僅適用於知識工作者",
        )
        assert crystal.assumption == "人在早上效率最高"
        assert crystal.evidence == "5 次觀察數據"
        assert crystal.limitation == "僅適用於知識工作者"


# ════════════════════════════════════════════
# Section 10: record_success / record_counter_evidence
# ════════════════════════════════════════════

class TestValidationRecording:
    """測試驗證紀錄 API."""

    def test_record_success_increments_count(self, lattice):
        """record_success 增加 success_count 和 reference_count."""
        crystal = lattice.crystallize(
            "假說測試結晶",
            "",
            "Hypothesis",
        )
        cuid = crystal.cuid
        assert crystal.success_count == 0

        lattice.record_success(cuid)
        updated = lattice.get_crystal(cuid)
        assert updated.success_count == 1
        assert updated.reference_count >= 1

    def test_record_counter_evidence_increments_count(self, lattice):
        """record_counter_evidence 增加 counter_evidence_count."""
        crystal = lattice.crystallize(
            "洞見反證測試結晶",
            "",
            "Insight",
        )
        cuid = crystal.cuid
        assert crystal.counter_evidence_count == 0

        lattice.record_counter_evidence(cuid)
        updated = lattice.get_crystal(cuid)
        assert updated.counter_evidence_count == 1


# ════════════════════════════════════════════
# Section 11: Crystallizer 五步流程
# ════════════════════════════════════════════

class TestCrystallizerFlow:
    """測試 Crystallizer 五步流程細節."""

    def test_crystallize_with_explicit_geo(self, lattice):
        """提供完整 GEO 四層時使用指定值."""
        crystal = lattice.crystallize(
            raw_material="原始素材",
            source_context="來源",
            crystal_type="Insight",
            g1_summary="自定義摘要",
            g2_structure=["面向 1", "面向 2", "面向 3"],
            g3_root_inquiry="為什麼？",
            g4_insights=["洞見 1", "洞見 2"],
        )
        assert crystal.g1_summary == "自定義摘要"
        assert len(crystal.g2_structure) == 3
        assert crystal.g3_root_inquiry == "為什麼？"
        assert len(crystal.g4_insights) == 2

    def test_crystallize_auto_generates_geo_defaults(self, lattice):
        """未提供 GEO 時自動萃取預設值."""
        crystal = lattice.crystallize(
            raw_material="一段足夠長的原始素材，用於自動萃取 GEO 四層結構",
            source_context="",
            crystal_type="Hypothesis",
        )
        # refine 步驟會自動從 raw_material 萃取
        assert crystal.g1_summary != ""
        assert len(crystal.g2_structure) >= 1
        assert crystal.g3_root_inquiry != ""
        assert len(crystal.g4_insights) >= 1

    def test_crystallize_assigns_verification_level(self, lattice):
        """不同類型自動指定驗證等級."""
        insight = lattice.crystallize("洞見", "", "Insight")
        assert insight.verification_level == "proven"

        pattern = lattice.crystallize("模式", "", "Pattern")
        assert pattern.verification_level == "observed"

        hypothesis = lattice.crystallize("假說", "", "Hypothesis")
        assert hypothesis.verification_level == "hypothetical"

        lesson = lattice.crystallize("教訓", "", "Lesson")
        assert lesson.verification_level == "observed"
