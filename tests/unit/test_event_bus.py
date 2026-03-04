"""Tests for event_bus.py — 全域事件匯流排.

依據 THREE_LAYER_PULSE BDD Spec §8 的 BDD scenarios 驗證。
"""

import threading

import pytest

from museon.core.event_bus import (
    EVOLUTION_HEARTBEAT,
    PULSE_MICRO_BEAT,
    PULSE_NIGHTLY_DONE,
    PULSE_RHYTHM_CHECK,
    EventBus,
    _reset_event_bus,
    get_event_bus,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """每個測試前重置 EventBus 單例."""
    _reset_event_bus()
    yield
    _reset_event_bus()


# ═══════════════════════════════════════════
# Singleton Tests
# ═══════════════════════════════════════════


class TestSingleton:
    """單例模式測試."""

    def test_same_instance(self):
        """BDD: 多次呼叫 get_event_bus() 回傳同一個實例."""
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    def test_reset_creates_new_instance(self):
        """重置後取得新實例."""
        bus1 = get_event_bus()
        _reset_event_bus()
        bus2 = get_event_bus()
        assert bus1 is not bus2


# ═══════════════════════════════════════════
# Event Constants
# ═══════════════════════════════════════════


class TestEventConstants:
    """事件常數驗證."""

    def test_pulse_events_defined(self):
        assert PULSE_MICRO_BEAT == "PULSE_MICRO_BEAT"
        assert PULSE_RHYTHM_CHECK == "PULSE_RHYTHM_CHECK"
        assert PULSE_NIGHTLY_DONE == "PULSE_NIGHTLY_DONE"
        assert EVOLUTION_HEARTBEAT == "EVOLUTION_HEARTBEAT"


# ═══════════════════════════════════════════
# Subscribe & Publish Tests
# ═══════════════════════════════════════════


class TestSubscribeAndPublish:
    """訂閱與發布測試（BDD Spec §8.3）."""

    def test_subscribe_and_publish(self):
        """BDD: 訂閱後收到事件."""
        bus = EventBus()
        received = []
        bus.subscribe("TEST", lambda data: received.append(data))
        bus.publish("TEST", {"beat_count": 5})
        assert len(received) == 1
        assert received[0]["beat_count"] == 5

    def test_multiple_subscribers(self):
        """BDD: 3 個 callback 全部被呼叫."""
        bus = EventBus()
        results = []
        bus.subscribe("TEST", lambda d: results.append("a"))
        bus.subscribe("TEST", lambda d: results.append("b"))
        bus.subscribe("TEST", lambda d: results.append("c"))
        bus.publish("TEST")
        assert len(results) == 3
        assert set(results) == {"a", "b", "c"}

    def test_subscriber_exception_no_affect(self):
        """BDD: 訂閱者異常不影響其他訂閱者."""
        bus = EventBus()
        results = []

        def bad_callback(data):
            raise RuntimeError("boom")

        def good_callback(data):
            results.append("ok")

        bus.subscribe("TEST", bad_callback)
        bus.subscribe("TEST", good_callback)
        bus.publish("TEST")
        assert results == ["ok"]

    def test_unsubscribe(self):
        """BDD: 取消訂閱後不再收到事件."""
        bus = EventBus()
        received = []
        cb = lambda data: received.append(data)
        bus.subscribe("TEST", cb)
        bus.publish("TEST", {"n": 1})
        assert len(received) == 1

        bus.unsubscribe("TEST", cb)
        bus.publish("TEST", {"n": 2})
        assert len(received) == 1  # 不再收到

    def test_publish_no_subscribers(self):
        """BDD: 無訂閱者時 publish 不報錯."""
        bus = EventBus()
        bus.publish("NONEXISTENT", {"data": True})

    def test_no_duplicate_subscribe(self):
        """BDD: 同一 callback 重複訂閱只註冊一次."""
        bus = EventBus()
        results = []
        cb = lambda data: results.append(1)
        bus.subscribe("TEST", cb)
        bus.subscribe("TEST", cb)
        bus.publish("TEST")
        assert len(results) == 1

    def test_subscriber_count(self):
        """BDD: subscriber_count 正確."""
        bus = EventBus()
        assert bus.subscriber_count("TEST") == 0
        bus.subscribe("TEST", lambda d: None)
        assert bus.subscriber_count("TEST") == 1
        bus.subscribe("TEST", lambda d: None)
        assert bus.subscriber_count("TEST") == 2

    def test_clear(self):
        """BDD: clear 後無訂閱者."""
        bus = EventBus()
        bus.subscribe("A", lambda d: None)
        bus.subscribe("B", lambda d: None)
        bus.clear()
        assert bus.subscriber_count("A") == 0
        assert bus.subscriber_count("B") == 0

    def test_publish_none_data(self):
        """BDD: data=None 正常處理."""
        bus = EventBus()
        received = []
        bus.subscribe("TEST", lambda d: received.append(d))
        bus.publish("TEST")
        assert received == [None]

    def test_different_events_independent(self):
        """BDD: 不同事件的訂閱者獨立."""
        bus = EventBus()
        a_results = []
        b_results = []
        bus.subscribe("A", lambda d: a_results.append(1))
        bus.subscribe("B", lambda d: b_results.append(1))
        bus.publish("A")
        assert len(a_results) == 1
        assert len(b_results) == 0


# ═══════════════════════════════════════════
# Thread Safety Tests
# ═══════════════════════════════════════════


class TestThreadSafety:
    """執行緒安全測試."""

    def test_concurrent_publish(self):
        """BDD: 並行發布不會 race condition."""
        bus = EventBus()
        counter = {"count": 0}
        lock = threading.Lock()

        def increment(data):
            with lock:
                counter["count"] += 1

        bus.subscribe("TEST", increment)
        threads = []
        for _ in range(20):
            t = threading.Thread(target=bus.publish, args=("TEST", {}))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert counter["count"] == 20

    def test_concurrent_subscribe_and_publish(self):
        """BDD: 並行訂閱和發布無 race condition."""
        bus = EventBus()
        errors = []

        def subscriber_worker():
            try:
                for i in range(10):
                    bus.subscribe(f"EVT_{i}", lambda d: None)
            except Exception as e:
                errors.append(e)

        def publisher_worker():
            try:
                for i in range(10):
                    bus.publish(f"EVT_{i}", {"n": i})
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(5):
            threads.append(threading.Thread(target=subscriber_worker))
            threads.append(threading.Thread(target=publisher_worker))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
