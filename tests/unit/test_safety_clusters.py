"""Tests for safety_clusters.py — Tier A 安全反射叢集偵測.

依據 DNA27 Neural Tract BDD Spec §2.2 的 BDD scenarios 驗證。
"""

import pytest

from museon.agent.safety_clusters import (
    CLUSTER_MAX_SCORE,
    KEYWORD_MULTIPLIER,
    REGEX_MULTIPLIER,
    SAFETY_TRIGGER_THRESHOLD,
    SafetyCluster,
    TIER_A_CLUSTERS,
    build_safety_context,
    detect_safety_clusters,
    get_tier_a_score,
    get_triggered_clusters,
)


# ═══════════════════════════════════════════
# Cluster Definition Tests
# ═══════════════════════════════════════════


class TestClusterDefinitions:
    """Tier A 叢集定義驗證."""

    def test_seven_clusters_defined(self):
        """BDD: Tier A 有 7 個叢集."""
        assert len(TIER_A_CLUSTERS) == 7

    def test_cluster_ids(self):
        """BDD: 叢集 ID 為 RC-A1 到 RC-A7."""
        ids = [c.cluster_id for c in TIER_A_CLUSTERS]
        for i in range(1, 8):
            assert f"RC-A{i}" in ids

    def test_a3_highest_weight(self):
        """BDD: RC-A3 不可逆攔截有最高權重 1.5."""
        a3 = next(c for c in TIER_A_CLUSTERS if c.cluster_id == "RC-A3")
        assert a3.weight == 1.5
        assert a3.name == "irreversible_interception"

    def test_weights_match_spec(self):
        """BDD: 所有權重符合 spec."""
        expected = {
            "RC-A1": 1.0,
            "RC-A2": 1.0,
            "RC-A3": 1.5,
            "RC-A4": 0.8,
            "RC-A5": 0.7,
            "RC-A6": 0.9,
            "RC-A7": 0.6,
        }
        for cluster in TIER_A_CLUSTERS:
            assert cluster.weight == expected[cluster.cluster_id]

    def test_all_clusters_have_keywords(self):
        """BDD: 每個叢集至少有 3 個關鍵字."""
        for cluster in TIER_A_CLUSTERS:
            assert len(cluster.keywords) >= 3, (
                f"{cluster.cluster_id} has < 3 keywords"
            )

    def test_all_clusters_have_regex(self):
        """BDD: 每個叢集至少有 1 個 regex."""
        for cluster in TIER_A_CLUSTERS:
            assert len(cluster.regex_patterns) >= 1, (
                f"{cluster.cluster_id} has no regex"
            )

    def test_compiled_patterns(self):
        """BDD: regex 已預編譯."""
        for cluster in TIER_A_CLUSTERS:
            assert len(cluster._compiled_patterns) == len(
                cluster.regex_patterns
            )


# ═══════════════════════════════════════════
# Detection Tests
# ═══════════════════════════════════════════


class TestDetectSafetyClusters:
    """安全叢集偵測測試."""

    def test_empty_message(self):
        """BDD: 空訊息返回空 dict."""
        assert detect_safety_clusters("") == {}

    def test_no_match(self):
        """BDD: 無匹配時返回空 dict."""
        result = detect_safety_clusters("今天天氣真好")
        assert result == {}

    def test_a1_keyword_match(self):
        """BDD: 能量耗竭關鍵字匹配."""
        result = detect_safety_clusters("我好累，快 burnout 了")
        assert "RC-A1" in result
        assert result["RC-A1"] > 0

    def test_a1_regex_match(self):
        """BDD: 能量耗竭 regex 匹配."""
        result = detect_safety_clusters("我累死了")
        assert "RC-A1" in result

    def test_a2_emotional_overheating(self):
        """BDD: 情緒過熱偵測."""
        result = detect_safety_clusters("我快要崩潰了，受不了")
        assert "RC-A2" in result

    def test_a3_irreversible(self):
        """BDD: 不可逆決策偵測."""
        result = detect_safety_clusters("我要刪除所有資料")
        assert "RC-A3" in result

    def test_a3_minimum_score(self):
        """BDD: RC-A3 匹配 '刪除所有' → 最低分 1.5 × 0.7 = 1.05."""
        result = detect_safety_clusters("刪除所有")
        assert "RC-A3" in result
        # keyword(刪除所有=1.5*0.7) + regex(刪除.*所有=1.5*1.0) = 2.55
        assert result["RC-A3"] >= 1.05

    def test_a4_risk_overload(self):
        """BDD: 風險超載偵測."""
        result = detect_safety_clusters("我要 all in 這個機會")
        assert "RC-A4" in result

    def test_a5_emergency(self):
        """BDD: 緊急降速偵測."""
        result = detect_safety_clusters("馬上幫我做，很緊急")
        assert "RC-A5" in result

    def test_a6_self_dissolution(self):
        """BDD: 自我消融偵測."""
        result = detect_safety_clusters("我不知道自己是誰了，好迷失")
        assert "RC-A6" in result

    def test_a7_safety_first(self):
        """BDD: 安全優先偵測."""
        result = detect_safety_clusters("幫我保護好這些資料")
        assert "RC-A7" in result

    def test_keyword_score_calculation(self):
        """BDD: keyword hit = weight × 0.7."""
        result = detect_safety_clusters("累")
        # RC-A1 weight=1.0, keyword hit → 1.0 × 0.7 = 0.7
        assert result.get("RC-A1", 0) == pytest.approx(0.7, abs=0.01)

    def test_cluster_score_cap(self):
        """BDD: 每叢集分數上限 3.0."""
        # 觸發多個 RC-A1 關鍵字 + regex
        message = "我好累，疲憊不堪，burnout了，累死了，沒力氣，耗盡了，撐不住"
        result = detect_safety_clusters(message)
        assert result.get("RC-A1", 0) <= CLUSTER_MAX_SCORE

    def test_multiple_clusters(self):
        """BDD: 多叢集同時觸發."""
        message = "我好累又焦慮，想要 all in 一把"
        result = detect_safety_clusters(message)
        assert len(result) >= 2


# ═══════════════════════════════════════════
# Tier Aggregation Tests
# ═══════════════════════════════════════════


class TestTierAggregation:
    """Tier 聚合測試."""

    def test_tier_a_max_score(self):
        """BDD: Tier A 聚合 = 取最高分."""
        scores = {"RC-A1": 0.7, "RC-A3": 2.1, "RC-A5": 0.49}
        assert get_tier_a_score(scores) == 2.1

    def test_tier_a_empty(self):
        """BDD: 無 A 叢集得分 → 0."""
        assert get_tier_a_score({}) == 0.0

    def test_tier_a_ignores_non_a(self):
        """BDD: 非 A 叢集被忽略."""
        scores = {"RC-B1": 2.0, "RC-A1": 0.7}
        assert get_tier_a_score(scores) == 0.7


# ═══════════════════════════════════════════
# Triggered Clusters Tests
# ═══════════════════════════════════════════


class TestGetTriggeredClusters:
    """觸發叢集清單測試."""

    def test_above_threshold(self):
        """BDD: 超過閾值的叢集被選取."""
        scores = {"RC-A1": 0.7, "RC-A5": 0.3, "RC-A3": 1.5}
        triggered = get_triggered_clusters(scores)
        assert "RC-A1" in triggered
        assert "RC-A3" in triggered
        assert "RC-A5" not in triggered  # 0.3 < 0.5

    def test_custom_threshold(self):
        """BDD: 自訂閾值."""
        scores = {"RC-A1": 0.3}
        assert len(get_triggered_clusters(scores, threshold=0.2)) == 1
        assert len(get_triggered_clusters(scores, threshold=0.5)) == 0


# ═══════════════════════════════════════════
# Safety Context Builder Tests
# ═══════════════════════════════════════════


class TestBuildSafetyContext:
    """安全上下文建構測試."""

    def test_no_clusters(self):
        """BDD: 無叢集 → 空字串."""
        assert build_safety_context({}) == ""

    def test_below_threshold(self):
        """BDD: 低於閾值 → 空字串."""
        assert build_safety_context({"RC-A7": 0.3}) == ""

    def test_energy_depletion_context(self):
        """BDD: 能量耗竭 → 生成對應指引."""
        context = build_safety_context({"RC-A1": 0.7})
        assert "能量耗竭" in context
        assert "安全感知" in context

    def test_emotional_context(self):
        """BDD: 情緒過熱 → 生成對應指引."""
        context = build_safety_context({"RC-A2": 1.0})
        assert "情緒過熱" in context

    def test_irreversible_context(self):
        """BDD: 不可逆決策 → 提及暫停 24 小時."""
        context = build_safety_context({"RC-A3": 1.5})
        assert "不可逆" in context
        assert "24" in context

    def test_high_intensity_fast_loop(self):
        """BDD: tier_a >= 1.5 → 強制 fast_loop 指令."""
        context = build_safety_context({"RC-A3": 2.0})
        assert "fast_loop" in context
        assert "200 字" in context

    def test_multiple_cluster_context(self):
        """BDD: 多叢集 → 多條指引."""
        context = build_safety_context({
            "RC-A1": 0.7,
            "RC-A2": 1.0,
        })
        assert "能量耗竭" in context
        assert "情緒過熱" in context

    def test_risk_overload_context(self):
        """BDD: 風險超載 → 同框呈現."""
        context = build_safety_context({"RC-A4": 0.8})
        assert "風險" in context or "Plan B" in context

    def test_emergency_context(self):
        """BDD: 緊急降速 → fast_loop."""
        context = build_safety_context({"RC-A5": 0.7})
        assert "緊急" in context or "fast_loop" in context

    def test_self_dissolution_context(self):
        """BDD: 自我消融 → 確認存在感."""
        context = build_safety_context({"RC-A6": 0.9})
        assert "消融" in context or "存在" in context
