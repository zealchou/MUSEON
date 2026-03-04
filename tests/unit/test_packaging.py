"""
MUSEON 自解壓安裝包測試

對應 features/packaging.feature 的 10 個 Scenario
嚴格 BDD：先寫測試，再寫實作
"""

import base64
import os
import tarfile
from pathlib import Path

import pytest

from museon.installer.models import StepStatus


# ═══════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════

@pytest.fixture
def fake_project(tmp_path):
    """建立一個模擬的 MUSEON 專案目錄結構"""
    # src/museon/__init__.py
    src = tmp_path / "src" / "museon"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text('__version__ = "0.1.0"\n')

    # src/museon/installer/
    installer = src / "installer"
    installer.mkdir()
    (installer / "__init__.py").write_text("")
    (installer / "models.py").write_text("# models\n")

    # pyproject.toml
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "museon"\n')

    # electron/ (不含 node_modules)
    electron = tmp_path / "electron"
    electron.mkdir()
    (electron / "package.json").write_text('{"name": "museon-dashboard"}\n')
    (electron / "package-lock.json").write_text("{}\n")
    (electron / "main.js").write_text("// main\n")
    (electron / "preload.js").write_text("// preload\n")
    (electron / ".babelrc").write_text("{}\n")
    esrc = electron / "src"
    esrc.mkdir()
    (esrc / "App.jsx").write_text("// App\n")

    # electron/node_modules (應該被排除)
    nm = electron / "node_modules" / "some-pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("// pkg\n")

    # electron/dist (應該被排除)
    edist = electron / "dist"
    edist.mkdir()
    (edist / "output.js").write_text("// dist\n")

    # features/
    features = tmp_path / "features"
    features.mkdir()
    (features / "installation.feature").write_text("Feature: install\n")

    # data/
    data = tmp_path / "data"
    data.mkdir()
    for sub in ["memory", "skills", "vector", "workspace"]:
        (data / sub).mkdir()

    # Install-MUSEON.command
    (tmp_path / "Install-MUSEON.command").write_text("#!/bin/bash\n# installer\n")

    # 應該被排除的
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / ".DS_Store").write_text("")
    (tmp_path / ".coverage").write_text("")
    (tmp_path / "htmlcov").mkdir()
    (tmp_path / ".pytest_cache").mkdir()

    return tmp_path


@pytest.fixture
def packager():
    """建立 Packager 實例"""
    from museon.installer.packager import InstallerPackager
    return InstallerPackager()


@pytest.fixture
def output_dir(tmp_path):
    """輸出目錄"""
    d = tmp_path / "output"
    d.mkdir()
    return d


# ═══════════════════════════════════════
# Section 1: 來源檔案收集 (Scenarios 1-2)
# ═══════════════════════════════════════

class TestSourceFileCollection:
    """對應 features/packaging.feature Section 1"""

    def test_collect_includes_required_dirs(self, packager, fake_project):
        """Scenario: 收集來源檔案 — 包含必要目錄"""
        files = packager.collect_source_files(fake_project)
        rel_paths = [str(f.relative_to(fake_project)) for f in files]

        assert any(p.startswith("src/") for p in rel_paths)
        assert any(p.startswith("electron/src/") for p in rel_paths)
        assert any(p.startswith("features/") for p in rel_paths)

    def test_collect_includes_required_files(self, packager, fake_project):
        """Scenario: 收集來源檔案 — 包含必要檔案"""
        files = packager.collect_source_files(fake_project)
        rel_paths = [str(f.relative_to(fake_project)) for f in files]

        assert "pyproject.toml" in rel_paths
        assert "electron/package.json" in rel_paths
        assert "Install-MUSEON.command" in rel_paths

    def test_collect_excludes_ephemeral(self, packager, fake_project):
        """Scenario: 排除不需要的檔案"""
        files = packager.collect_source_files(fake_project)
        rel_paths = [str(f.relative_to(fake_project)) for f in files]

        for p in rel_paths:
            assert not p.startswith(".venv")
            assert not p.startswith(".git")
            assert "node_modules" not in p
            assert "__pycache__" not in p
            assert "htmlcov" not in p
            assert ".coverage" not in p
            assert ".pytest_cache" not in p
            assert ".DS_Store" not in p
            assert not p.startswith("electron/dist")


# ═══════════════════════════════════════
# Section 2: tar.gz 建立 (Scenarios 3-4)
# ═══════════════════════════════════════

class TestTarGzCreation:
    """對應 features/packaging.feature Section 2"""

    def test_create_tarball_success(self, packager, fake_project, output_dir):
        """Scenario: 建立壓縮封存檔 — 成功"""
        tarball = output_dir / "payload.tar.gz"
        result = packager.create_tarball(fake_project, tarball)

        assert result.status == StepStatus.SUCCESS
        assert tarball.exists()
        size = tarball.stat().st_size
        assert size > 0
        assert size < 5 * 1024 * 1024  # < 5MB

    def test_tarball_contents_correct(self, packager, fake_project, output_dir):
        """Scenario: tar.gz 內容結構正確"""
        tarball = output_dir / "payload.tar.gz"
        packager.create_tarball(fake_project, tarball)

        with tarfile.open(tarball, "r:gz") as tf:
            names = tf.getnames()

        assert any("src/museon/__init__.py" in n for n in names)
        assert any("pyproject.toml" in n for n in names)
        assert not any(".venv" in n for n in names)
        assert not any("node_modules" in n for n in names)


# ═══════════════════════════════════════
# Section 3: Base64 編碼 (Scenario 5)
# ═══════════════════════════════════════

class TestBase64Encoding:
    """對應 features/packaging.feature Section 3"""

    def test_base64_roundtrip(self, packager, fake_project, output_dir):
        """Scenario: Base64 編碼 — 往返測試"""
        tarball = output_dir / "payload.tar.gz"
        packager.create_tarball(fake_project, tarball)

        b64_path = output_dir / "payload.b64"
        result = packager.encode_base64(tarball, b64_path)

        assert result.status == StepStatus.SUCCESS
        assert b64_path.exists()

        # Round-trip: 解碼後應與原始 tar.gz 完全相同
        encoded = b64_path.read_bytes()
        decoded = base64.b64decode(encoded)
        original = tarball.read_bytes()
        assert decoded == original


# ═══════════════════════════════════════
# Section 4: 自解壓標頭 (Scenarios 6-7)
# ═══════════════════════════════════════

class TestSelfExtractingHeader:
    """對應 features/packaging.feature Section 4"""

    def test_header_structure(self, packager):
        """Scenario: 自解壓標頭 — 結構正確"""
        header = packager.generate_header()

        lines = header.split("\n")
        assert lines[0] == "#!/bin/bash"
        assert any("__PAYLOAD_BELOW__" in line for line in lines)
        assert any("base64" in line and "-D" in line for line in lines)
        assert any("tar" in line for line in lines)

    def test_header_install_flow(self, packager):
        """Scenario: 自解壓標頭 — 安裝流程完整"""
        header = packager.generate_header()

        # 基本安裝流程
        assert "INSTALL_DIR" in header
        assert "mkdir" in header
        assert "python3" in header
        assert "venv" in header
        assert "pip install" in header
        assert "museon.installer" in header

        # 新版: 提取到 .runtime/ 子目錄
        assert "RUNTIME_DIR" in header
        assert ".runtime" in header

        # 新版: osascript 資料夾選擇器
        assert "osascript" in header

        # 新版: venv 在 $RUNTIME_DIR/.venv
        assert 'VENV_DIR="$RUNTIME_DIR/.venv"' in header

        # 新版: 設定 MUSEON_HOME 為使用者根目錄
        assert "MUSEON_HOME" in header
        assert 'MUSEON_HOME="$INSTALL_DIR"' in header

        # 新版: cd 到 RUNTIME_DIR 後再 pip install
        assert 'cd "$RUNTIME_DIR"' in header


# ═══════════════════════════════════════
# Section 5: 組裝與驗證 (Scenarios 8-10)
# ═══════════════════════════════════════

class TestAssembly:
    """對應 features/packaging.feature Section 5"""

    def test_assemble_command_file(self, packager, fake_project, output_dir):
        """Scenario: 組裝 .command 檔案 — 成功"""
        output = output_dir / "Install-MUSEON.command"
        result = packager.build(fake_project, output)

        assert result.status == StepStatus.SUCCESS
        assert output.exists()
        assert os.access(output, os.X_OK)
        assert output.stat().st_size < 10 * 1024 * 1024  # < 10MB

    def test_payload_roundtrip(self, packager, fake_project, output_dir, tmp_path):
        """Scenario: 載荷提取往返測試"""
        output = output_dir / "Install-MUSEON.command"
        packager.build(fake_project, output)

        # 從組裝好的 .command 提取載荷
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        result = packager.extract_payload(output, extract_dir)
        assert result.status == StepStatus.SUCCESS
        assert (extract_dir / "src" / "museon" / "__init__.py").exists()
        assert (extract_dir / "pyproject.toml").exists()

        # 內容應完全一致
        original = (fake_project / "pyproject.toml").read_text()
        extracted = (extract_dir / "pyproject.toml").read_text()
        assert original == extracted

    def test_update_preserves_user_data(self, packager, fake_project, output_dir, tmp_path):
        """Scenario: 更新安裝 — 保留使用者資料"""
        # 模擬已有舊版安裝
        install_dir = tmp_path / "museon-install"
        install_dir.mkdir()
        env_file = install_dir / ".env"
        env_file.write_text("TELEGRAM_BOT_TOKEN=secret123\n")
        data_dir = install_dir / "data" / "memory"
        data_dir.mkdir(parents=True)
        (data_dir / "user-data.json").write_text('{"key": "value"}\n')

        # 打包
        output = output_dir / "Install-MUSEON.command"
        packager.build(fake_project, output)

        # 備份 → 解壓 → 還原
        preserved = packager.preserve_user_data(install_dir)
        packager.extract_payload(output, install_dir)
        packager.restore_user_data(install_dir, preserved)

        # 驗證使用者資料被保留
        assert env_file.exists()
        assert "secret123" in env_file.read_text()
        assert (data_dir / "user-data.json").exists()
