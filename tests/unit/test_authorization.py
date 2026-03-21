"""Tests for gateway/authorization.py — 配對碼 + 工具授權 + 分級策略."""

import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from museon.gateway.authorization import (
    ApprovalQueue,
    AuthorizationPolicy,
    PairingManager,
    ToolAuthorizationQueue,
)


# ══════════════════════════════════════════════════
# ApprovalQueue
# ══════════════════════════════════════════════════


class TestApprovalQueue:
    def test_add_and_resolve(self):
        q = ApprovalQueue()
        q.add("e1", {"msg": "hello"})
        assert q.pending_count() == 1
        assert q.resolve("e1", approved=True)
        assert q.pending_count() == 0
        entry = q.get("e1")
        assert entry["approved"] is True

    def test_resolve_latest_fifo(self):
        q = ApprovalQueue()
        q.add("e1", {"msg": "first"})
        q.add("e2", {"msg": "second"})
        eid = q.resolve_latest(approved=True)
        assert eid == "e1"
        eid2 = q.resolve_latest(approved=False)
        assert eid2 == "e2"

    def test_resolve_nonexistent(self):
        q = ApprovalQueue()
        assert not q.resolve("nonexistent", approved=True)

    def test_timeout(self):
        q = ApprovalQueue(timeout_seconds=1)
        q.add("e1", {"msg": "timeout"})
        # Manually backdate created_at
        q._pending["e1"]["created_at"] = datetime.now() - timedelta(seconds=5)
        assert q.is_timed_out("e1")
        assert q.pending_count() == 0

    def test_has_pending(self):
        q = ApprovalQueue()
        assert not q.has_pending()
        q.add("e1", {"msg": "test"})
        assert q.has_pending()

    def test_get_latest(self):
        q = ApprovalQueue()
        assert q.get_latest() is None
        q.add("e1", {"msg": "test"})
        entry = q.get_latest()
        assert entry is not None
        assert entry["msg"] == "test"

    def test_purge_old(self):
        q = ApprovalQueue()
        q.add("e1", {"msg": "old"})
        q._pending["e1"]["created_at"] = datetime.now() - timedelta(hours=3)
        q.add("e2", {"msg": "new"})
        q.purge_old(hours=2)
        assert q.get("e1") is None
        assert q.get("e2") is not None

    @pytest.mark.asyncio
    async def test_wait_for_resolution_approved(self):
        q = ApprovalQueue()
        q.add("e1", {"msg": "wait"})

        async def resolver():
            await asyncio.sleep(0.05)
            q.resolve("e1", approved=True)

        asyncio.create_task(resolver())
        result = await q.wait_for_resolution("e1", timeout_seconds=2)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_resolution_timeout(self):
        q = ApprovalQueue()
        q.add("e1", {"msg": "timeout"})
        result = await q.wait_for_resolution("e1", timeout_seconds=0.1)
        assert result is False  # 超時自動拒絕


# ══════════════════════════════════════════════════
# ToolAuthorizationQueue
# ══════════════════════════════════════════════════


class TestToolAuthorizationQueue:
    def test_session_grant(self):
        taq = ToolAuthorizationQueue()
        assert not taq.has_session_grant("s1", "write_file")
        taq.grant_session("s1", "write_file")
        assert taq.has_session_grant("s1", "write_file")
        assert not taq.has_session_grant("s1", "delete_file")

    @pytest.mark.asyncio
    async def test_request_authorization_with_session_grant(self):
        taq = ToolAuthorizationQueue()
        taq.grant_session("s1", "write_file")
        entry_id, event = await taq.request_authorization(
            "write_file", "path=test.txt", "s1", "user1"
        )
        assert entry_id is None  # 已授權，不需要等待
        assert event is None

    @pytest.mark.asyncio
    async def test_request_authorization_pending(self):
        taq = ToolAuthorizationQueue()
        entry_id, event = await taq.request_authorization(
            "write_file", "path=test.txt", "s1", "user1"
        )
        assert entry_id is not None
        assert event is not None
        assert taq.pending_count() == 1

    def test_timeout_5_minutes(self):
        taq = ToolAuthorizationQueue()
        assert taq._timeout_seconds == 300


# ══════════════════════════════════════════════════
# PairingManager
# ══════════════════════════════════════════════════


class TestPairingManager:
    @pytest.fixture
    def pm(self, tmp_path):
        return PairingManager(auth_dir=tmp_path)

    def test_generate_code_format(self, pm):
        code = pm.generate_code("12345", "Test User")
        assert len(code) == 6
        # 不包含混淆字元
        for c in code:
            assert c not in "OI01"

    def test_generate_same_code_for_same_user(self, pm):
        code1 = pm.generate_code("12345", "Test")
        code2 = pm.generate_code("12345", "Test")
        assert code1 == code2

    def test_verify_code_success(self, pm):
        code = pm.generate_code("12345", "Test User")
        result = pm.verify_code(code)
        assert result is not None
        assert result["user_id"] == "12345"
        assert result["display_name"] == "Test User"

    def test_verify_code_invalid(self, pm):
        assert pm.verify_code("INVALID") is None

    def test_verify_code_expired(self, pm):
        code = pm.generate_code("12345", "Test")
        # Backdate the code
        pm._pending_codes[code]["created_at"] = datetime.now() - timedelta(seconds=600)
        assert pm.verify_code(code) is None

    def test_verify_code_max_attempts(self, pm):
        code = pm.generate_code("12345", "Test")
        # 消耗 3 次嘗試
        pm._pending_codes[code]["attempts"] = 3
        assert pm.verify_code(code) is None

    def test_add_and_check_user(self, pm):
        pm.add_user("12345", "Test", trust_level="VERIFIED")
        assert pm.is_paired("12345")
        assert pm.get_dynamic_trust("12345") == "VERIFIED"

    def test_ttl_expiry(self, pm):
        pm.add_user("12345", "Test", trust_level="VERIFIED", ttl=1)
        assert pm.is_paired("12345")
        # Backdate added_at
        pm._allowlist["12345"]["added_at"] = (
            datetime.now() - timedelta(seconds=5)
        ).isoformat()
        assert not pm.is_paired("12345")

    def test_remove_user(self, pm):
        pm.add_user("12345", "Test")
        assert pm.remove_user("12345")
        assert not pm.is_paired("12345")

    def test_remove_nonexistent(self, pm):
        assert not pm.remove_user("nonexistent")

    def test_persistence(self, tmp_path):
        pm1 = PairingManager(auth_dir=tmp_path)
        pm1.add_user("12345", "Test", trust_level="VERIFIED")
        # 新實例應該能讀到
        pm2 = PairingManager(auth_dir=tmp_path)
        assert pm2.is_paired("12345")
        assert pm2.get_dynamic_trust("12345") == "VERIFIED"

    def test_list_users_cleans_expired(self, pm):
        pm.add_user("12345", "Fresh", ttl=3600)
        pm.add_user("67890", "Expired", ttl=1)
        pm._allowlist["67890"]["added_at"] = (
            datetime.now() - timedelta(seconds=5)
        ).isoformat()
        users = pm.list_users()
        assert "12345" in users
        assert "67890" not in users


# ══════════════════════════════════════════════════
# AuthorizationPolicy
# ══════════════════════════════════════════════════


class TestAuthorizationPolicy:
    @pytest.fixture
    def policy(self, tmp_path):
        return AuthorizationPolicy(auth_dir=tmp_path)

    def test_default_classify(self, policy):
        assert policy.classify("museon_memory_read") == "auto"
        assert policy.classify("shell_exec") == "ask"
        assert policy.classify("modify_security") == "block"

    def test_unknown_tool_defaults_to_ask(self, policy):
        assert policy.classify("some_unknown_tool") == "ask"

    def test_museon_readonly_defaults_to_auto(self, policy):
        assert policy.classify("museon_health_status") == "auto"

    def test_move_tool(self, policy):
        assert policy.classify("shell_exec") == "ask"
        policy.move_tool("shell_exec", "auto")
        assert policy.classify("shell_exec") == "auto"

    def test_move_tool_invalid_tier(self, policy):
        assert not policy.move_tool("shell_exec", "invalid")

    def test_persistence(self, tmp_path):
        p1 = AuthorizationPolicy(auth_dir=tmp_path)
        p1.move_tool("shell_exec", "auto")
        # 新實例應該能讀到
        p2 = AuthorizationPolicy(auth_dir=tmp_path)
        assert p2.classify("shell_exec") == "auto"

    def test_list_policy(self, policy):
        p = policy.list_policy()
        assert "auto" in p
        assert "ask" in p
        assert "block" in p


# ══════════════════════════════════════════════════
# SecurityGate 三級策略整合
# ══════════════════════════════════════════════════


class TestSecurityGateIntegration:
    def test_block_tier(self):
        from museon.gateway.security import SecurityGate
        sg = SecurityGate()
        result = sg.check_tool_access("modify_security", "telegram", "TRUSTED")
        assert result["allowed"] is False

    def test_auto_tier_verified(self, tmp_path):
        from museon.gateway.security import SecurityGate
        sg = SecurityGate()
        result = sg.check_tool_access("museon_memory_read", "telegram", "VERIFIED")
        assert result["allowed"] is True

    def test_ask_tier_trusted_passes(self):
        from museon.gateway.security import SecurityGate
        sg = SecurityGate()
        result = sg.check_tool_access("shell_exec", "telegram", "TRUSTED")
        assert result["allowed"] is True

    def test_ask_tier_verified_pending(self):
        from museon.gateway.security import SecurityGate
        sg = SecurityGate()
        result = sg.check_tool_access("shell_exec", "telegram", "VERIFIED")
        assert result["allowed"] == "pending"
        assert result["reason"] == "awaiting_authorization"

    def test_ask_tier_unknown_blocked(self):
        from museon.gateway.security import SecurityGate
        sg = SecurityGate()
        result = sg.check_tool_access("shell_exec", "telegram", "UNKNOWN")
        assert result["allowed"] is False
