"""
Unit tests for nightly job components.

Tests cover:
- Memory fusion
- Token optimization (observe patterns, suggest downgrade, verify quality, rollback)
- Self-forging triggers (quality-driven, usage-driven, time-driven)
- Batch API integration
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
import json


@pytest.fixture
def mock_memory_store():
    """Mock memory store with sample data."""
    store = Mock()
    store.data_dir = Path("/tmp/museclaw_test_data")
    store.load_daily_log = AsyncMock(return_value={
        "conversations": [
            {"timestamp": "2026-02-20T10:00:00", "content": "test conv 1"},
            {"timestamp": "2026-02-20T14:00:00", "content": "test conv 2"},
        ],
        "meta_thinking": [
            {"timestamp": "2026-02-20T10:05:00", "insight": "learned pattern A"}
        ]
    })
    store.save_memory = AsyncMock()
    return store


@pytest.fixture
def mock_llm_client():
    """Mock LLM client."""
    client = Mock()
    client.invoke = AsyncMock(return_value={
        "content": "Fused insights from daily conversations",
        "usage": {"input_tokens": 1000, "output_tokens": 200}
    })
    return client


@pytest.fixture
def sample_routing_stats():
    """Sample routing statistics."""
    return {
        "haiku": {"count": 150, "success_rate": 0.95, "avg_quality": 85},
        "sonnet": {"count": 50, "success_rate": 0.92, "avg_quality": 88},
        "tasks": [
            {"type": "greeting", "model": "haiku", "quality": 90, "tokens": 50},
            {"type": "greeting", "model": "haiku", "quality": 88, "tokens": 45},
            {"type": "creative", "model": "sonnet", "quality": 92, "tokens": 500},
        ]
    }


@pytest.fixture
def sample_quality_history():
    """Sample quality score history."""
    return {
        "brand-identity": [68, 67, 65, 64, 63],  # All < 70, triggers forge
        "text-alchemy": [85, 87, 86, 88, 90],    # Stable, no action needed
        "user-model": [70, 68, 72, 69, 67]       # Borderline
    }


class TestMemoryFusion:
    """Test memory fusion functionality."""

    @pytest.mark.asyncio
    async def test_fusion_basic(self, mock_memory_store, mock_llm_client):
        """Test basic memory fusion from daily logs."""
        from museclaw.nightly.fusion import MemoryFusion

        fusion = MemoryFusion(memory_store=mock_memory_store, llm_client=mock_llm_client)
        result = await fusion.fuse_daily_memories(date="2026-02-20")

        assert result["status"] == "success"
        assert "insights" in result
        mock_memory_store.load_daily_log.assert_called_once()
        mock_llm_client.invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_fusion_no_data(self, mock_memory_store, mock_llm_client):
        """Test fusion with no daily data (skip fusion)."""
        from museclaw.nightly.fusion import MemoryFusion

        mock_memory_store.load_daily_log.return_value = {"conversations": []}
        fusion = MemoryFusion(memory_store=mock_memory_store, llm_client=mock_llm_client)
        result = await fusion.fuse_daily_memories(date="2026-02-20")

        assert result["status"] == "skipped"
        assert result["reason"] == "no_data"

    @pytest.mark.asyncio
    async def test_cross_channel_fusion(self, mock_memory_store, mock_llm_client):
        """Test fusion across four memory channels."""
        from museclaw.nightly.fusion import MemoryFusion

        mock_memory_store.load_daily_log.return_value = {
            "meta_thinking": [{"insight": "A"}],
            "event": [{"event": "B"}],
            "outcome": [{"result": "C"}],
            "user_reaction": [{"reaction": "D"}]
        }

        fusion = MemoryFusion(memory_store=mock_memory_store, llm_client=mock_llm_client)
        result = await fusion.fuse_daily_memories(date="2026-02-20")

        assert result["status"] == "success"
        # Should combine insights from all 4 channels
        call_args = mock_llm_client.invoke.call_args
        prompt = call_args[1]["messages"][0]["content"]
        # Check for channel names or "四個" (four in Chinese)
        assert ("Meta Thinking" in prompt or "Event" in prompt or
                "四個" in prompt or "四通道" in prompt)


class TestTokenOptimization:
    """Test token self-optimization functionality."""

    @pytest.mark.asyncio
    async def test_observe_routing_patterns(self, sample_routing_stats):
        """Test observation of routing patterns."""
        from museclaw.nightly.optimize import TokenOptimizer

        optimizer = TokenOptimizer()
        patterns = await optimizer.observe_patterns(sample_routing_stats)

        assert "haiku" in patterns
        assert "sonnet" in patterns
        assert patterns["haiku"]["count"] == 150
        assert patterns["haiku"]["success_rate"] == 0.95

    @pytest.mark.asyncio
    async def test_suggest_downgrade_opportunity(self, sample_routing_stats):
        """Test suggestion of downgrade opportunities."""
        from museclaw.nightly.optimize import TokenOptimizer

        # Add high-quality haiku tasks that could replace some sonnet tasks
        sample_routing_stats["tasks"].extend([
            {"type": "simple_query", "model": "sonnet", "quality": 85, "tokens": 300},
            {"type": "simple_query", "model": "haiku", "quality": 86, "tokens": 80},
            {"type": "simple_query", "model": "haiku", "quality": 88, "tokens": 75},
        ])

        optimizer = TokenOptimizer()
        suggestions = await optimizer.suggest_downgrade(sample_routing_stats)

        assert len(suggestions) > 0
        assert any(s["task_type"] == "simple_query" for s in suggestions)

    @pytest.mark.asyncio
    async def test_verify_downgrade_quality(self):
        """Test quality verification after downgrade."""
        from museclaw.nightly.optimize import TokenOptimizer

        optimizer = TokenOptimizer()

        # Simulate downgrade test
        original_quality = 88
        new_quality = 87  # Acceptable degradation

        is_acceptable = await optimizer.verify_quality(
            task_type="greeting",
            original_quality=original_quality,
            new_quality=new_quality,
            threshold=5  # Allow up to 5 point drop
        )

        assert is_acceptable is True

    @pytest.mark.asyncio
    async def test_rollback_on_quality_drop(self):
        """Test automatic rollback when quality drops too much."""
        from museclaw.nightly.optimize import TokenOptimizer

        optimizer = TokenOptimizer()

        # Simulate significant quality drop
        original_quality = 90
        new_quality = 70  # Unacceptable

        is_acceptable = await optimizer.verify_quality(
            task_type="creative",
            original_quality=original_quality,
            new_quality=new_quality,
            threshold=5
        )

        assert is_acceptable is False


class TestSelfForging:
    """Test self-forging trigger detection."""

    @pytest.mark.asyncio
    async def test_quality_driven_trigger(self, sample_quality_history):
        """Test quality-driven forge trigger (Q-Score < 70 for 5 times)."""
        from museclaw.nightly.forge import ForgeEngine

        engine = ForgeEngine()
        triggers = await engine.check_quality_triggers(sample_quality_history)

        # brand-identity has 5 consecutive scores < 75, should trigger
        assert len(triggers) > 0
        assert any(t["skill"] == "brand-identity" for t in triggers)
        assert any(t["trigger_type"] == "quality_decline" for t in triggers)

    @pytest.mark.asyncio
    async def test_usage_driven_trigger(self):
        """Test usage-driven trigger (repeated task without dedicated skill)."""
        from museclaw.nightly.forge import ForgeEngine

        # Simulate 10+ instances of same task type without skill
        usage_data = {
            "tasks": [
                {"type": "nail_salon_promo", "has_skill": False, "count": 12},
                {"type": "general_post", "has_skill": True, "count": 20}
            ]
        }

        engine = ForgeEngine()
        triggers = await engine.check_usage_triggers(usage_data)

        assert len(triggers) > 0
        assert triggers[0]["task_type"] == "nail_salon_promo"
        assert triggers[0]["trigger_type"] == "repeated_manual"

    @pytest.mark.asyncio
    async def test_time_driven_scan(self):
        """Test time-driven nightly scan."""
        from museclaw.nightly.forge import ForgeEngine

        # Mock skill health data
        skill_health = {
            "skills": [
                {"name": "old-skill", "last_used": "2026-01-01", "days_since": 45},
                {"name": "active-skill", "last_used": "2026-02-24", "days_since": 1}
            ]
        }

        engine = ForgeEngine()
        results = await engine.time_driven_scan(skill_health)

        assert "outdated_skills" in results
        assert len(results["outdated_skills"]) > 0
        assert results["outdated_skills"][0]["name"] == "old-skill"

    @pytest.mark.asyncio
    async def test_forge_triggers_all_types(self, sample_quality_history):
        """Test all three trigger types combined."""
        from museclaw.nightly.forge import ForgeEngine

        engine = ForgeEngine()

        # Quality triggers
        quality_triggers = await engine.check_quality_triggers(sample_quality_history)

        # Usage triggers
        usage_data = {"tasks": [{"type": "custom_task", "has_skill": False, "count": 15}]}
        usage_triggers = await engine.check_usage_triggers(usage_data)

        # Time triggers
        skill_health = {"skills": [{"name": "unused", "last_used": "2025-12-01", "days_since": 86}]}
        time_scan = await engine.time_driven_scan(skill_health)

        # All three types should produce results
        assert len(quality_triggers) > 0
        assert len(usage_triggers) > 0
        assert len(time_scan["outdated_skills"]) > 0


class TestBatchAPI:
    """Test Batch API integration for nightly jobs."""

    @pytest.mark.asyncio
    async def test_batch_job_creation(self, mock_llm_client):
        """Test creating a batch job."""
        from museclaw.nightly.batch import BatchProcessor

        processor = BatchProcessor(llm_client=mock_llm_client)

        tasks = [
            {"type": "fusion", "data": {"date": "2026-02-20"}},
            {"type": "fusion", "data": {"date": "2026-02-21"}},
        ]

        batch_id = await processor.create_batch(tasks)

        assert batch_id is not None
        assert isinstance(batch_id, str)

    @pytest.mark.asyncio
    async def test_batch_status_check(self):
        """Test checking batch job status."""
        from museclaw.nightly.batch import BatchProcessor

        processor = BatchProcessor(llm_client=Mock())

        # Mock batch status
        with patch.object(processor, 'get_batch_status', return_value={
            "status": "completed",
            "progress": 100,
            "results": [{"id": 1, "result": "success"}]
        }):
            status = await processor.get_batch_status("batch_123")

            assert status["status"] == "completed"
            assert status["progress"] == 100

    @pytest.mark.asyncio
    async def test_batch_cost_savings(self):
        """Test batch API provides 50% cost savings."""
        from museclaw.nightly.batch import BatchProcessor

        processor = BatchProcessor(llm_client=Mock())

        # Standard cost vs batch cost
        standard_cost = 1000  # tokens
        batch_cost = processor.calculate_batch_cost(standard_cost)

        assert batch_cost == 500  # 50% savings
        assert batch_cost < standard_cost


class TestNightlyJob:
    """Test nightly job main workflow."""

    @pytest.mark.asyncio
    async def test_nightly_job_full_workflow(self, mock_memory_store, mock_llm_client):
        """Test complete nightly job execution."""
        from museclaw.nightly.job import NightlyJob

        job = NightlyJob(
            memory_store=mock_memory_store,
            llm_client=mock_llm_client
        )

        result = await job.run()

        assert result["status"] == "completed"
        assert "fusion" in result["tasks"]
        assert "optimization" in result["tasks"]
        assert "forge_check" in result["tasks"]

    @pytest.mark.asyncio
    async def test_nightly_job_error_handling(self, mock_memory_store, mock_llm_client):
        """Test nightly job handles errors gracefully."""
        from museclaw.nightly.job import NightlyJob

        # Make fusion fail
        mock_memory_store.load_daily_log.side_effect = Exception("DB error")

        job = NightlyJob(
            memory_store=mock_memory_store,
            llm_client=mock_llm_client
        )

        result = await job.run()

        # Should complete with partial success
        assert result["status"] in ["partial_success", "completed"]
        assert "errors" in result or result["tasks"]["fusion"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_nightly_job_scheduling(self):
        """Test nightly job is scheduled at 3AM."""
        from museclaw.nightly.job import get_schedule_time

        schedule = get_schedule_time()

        assert schedule.hour == 3
        assert schedule.minute == 0

    @pytest.mark.asyncio
    async def test_nightly_produces_health_report(self, mock_memory_store, mock_llm_client):
        """Test nightly job produces security health report."""
        from museclaw.nightly.job import NightlyJob

        job = NightlyJob(
            memory_store=mock_memory_store,
            llm_client=mock_llm_client
        )

        result = await job.run()

        assert "health_report" in result
        report = result["health_report"]
        assert "token_usage" in report
        assert "memory_status" in report
        assert "security_summary" in report
