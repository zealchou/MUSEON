"""Tests for museon.installer.permissions — macOS 權限檢查模組."""

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from museon.installer.permissions import (
    PermissionChecker,
    PermissionStatus,
    PermissionType,
)


class TestPermissionType:
    def test_enum_members(self):
        """有 FULL_DISK_ACCESS 和 AUTOMATION 兩個成員."""
        assert PermissionType.FULL_DISK_ACCESS is not None
        assert PermissionType.AUTOMATION is not None
        assert len(PermissionType) == 2


class TestPermissionStatus:
    def test_dataclass_fields(self):
        """PermissionStatus 有正確的欄位."""
        ps = PermissionStatus(
            permission=PermissionType.FULL_DISK_ACCESS,
            granted=True,
            message="OK",
            system_prefs_url="x-apple.systempreferences:test",
        )
        assert ps.permission == PermissionType.FULL_DISK_ACCESS
        assert ps.granted is True
        assert ps.message == "OK"
        assert ps.system_prefs_url.startswith("x-apple.systempreferences:")


class TestPermissionChecker:
    def setup_method(self):
        self.checker = PermissionChecker()

    def test_system_prefs_urls_complete(self):
        """每個 PermissionType 都有對應的系統設定 URL."""
        for ptype in PermissionType:
            assert ptype in PermissionChecker.SYSTEM_PREFS_URLS
            url = PermissionChecker.SYSTEM_PREFS_URLS[ptype]
            assert url.startswith("x-apple.systempreferences:")

    @patch("museon.installer.permissions.subprocess.run")
    def test_check_full_disk_access_granted(self, mock_run):
        """FDA 已授權時回傳 granted=True."""
        mock_run.return_value = MagicMock(returncode=0)
        result = self.checker.check_full_disk_access()
        assert result.permission == PermissionType.FULL_DISK_ACCESS
        assert result.granted is True

    @patch("museon.installer.permissions.subprocess.run")
    def test_check_full_disk_access_denied(self, mock_run):
        """FDA 未授權時回傳 granted=False."""
        mock_run.return_value = MagicMock(returncode=1)
        result = self.checker.check_full_disk_access()
        assert result.permission == PermissionType.FULL_DISK_ACCESS
        assert result.granted is False

    @patch("museon.installer.permissions.subprocess.run")
    def test_check_automation_granted(self, mock_run):
        """Automation 已授權時回傳 granted=True."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = self.checker.check_automation()
        assert result.permission == PermissionType.AUTOMATION
        assert result.granted is True

    @patch("museon.installer.permissions.subprocess.run")
    def test_check_automation_denied(self, mock_run):
        """Automation 未授權時（error -1743）回傳 granted=False."""
        mock_run.return_value = MagicMock(returncode=1, stderr="error -1743")
        result = self.checker.check_automation()
        assert result.permission == PermissionType.AUTOMATION
        assert result.granted is False

    @patch("museon.installer.permissions.subprocess.run")
    def test_check_all_returns_list(self, mock_run):
        """check_all() 回傳包含所有權限的列表."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        results = self.checker.check_all()
        assert isinstance(results, list)
        assert len(results) == len(PermissionType)
        names = {r.permission for r in results}
        assert names == set(PermissionType)

    @patch("museon.installer.permissions.subprocess.run")
    def test_open_system_preferences(self, mock_run):
        """open_system_preferences 使用正確的 URL."""
        mock_run.return_value = MagicMock(returncode=0)
        result = self.checker.open_system_preferences(PermissionType.FULL_DISK_ACCESS)
        assert result is True
        call_args = mock_run.call_args[0][0]
        assert "open" in call_args
        assert "x-apple.systempreferences:" in call_args[-1]
