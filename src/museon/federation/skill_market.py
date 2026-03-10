"""Skill Market — 技能交易市場（打包、簽章、交換、支付）.

將 MUSEON 技能打包為可分發的 .mskill 格式，
支援簽章驗證、本地市集註冊、安裝。

設計原則：
- SHA256 簽章確保包完整性
- 本地市集（離線優先），可選性連線交換
- 所有外部呼叫 try/except 包裹
- 市集資料持久化到 _system/marketplace/
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

MSKILL_EXTENSION = ".mskill"
MANIFEST_FILENAME = "manifest.json"
SIGNATURE_FILENAME = "signature.sha256"
MARKETPLACE_REGISTRY = "registry.json"
MAX_PACKAGE_SIZE_MB = 50


class SkillMarket:
    """技能交易市場 — 打包、簽章、交換、支付."""

    def __init__(
        self,
        workspace: Optional[str] = None,
        event_bus: Any = None,
    ) -> None:
        ws = workspace or os.getenv("MUSEON_WORKSPACE", str(Path.home() / "MUSEON"))
        self._workspace = Path(ws)
        self._event_bus = event_bus

        # 市集目錄
        self._market_dir = self._workspace / "_system" / "marketplace"
        self._market_dir.mkdir(parents=True, exist_ok=True)

        # 套件暫存目錄
        self._packages_dir = self._market_dir / "packages"
        self._packages_dir.mkdir(parents=True, exist_ok=True)

        # 已安裝技能目錄
        self._installed_dir = self._market_dir / "installed"
        self._installed_dir.mkdir(parents=True, exist_ok=True)

        # 市集註冊表
        self._registry_path = self._market_dir / MARKETPLACE_REGISTRY
        self._registry: Dict = self._load_registry()

    # ── Registry Persistence ────────────────────────────

    def _load_registry(self) -> Dict:
        """載入市集註冊表."""
        if self._registry_path.exists():
            try:
                return json.loads(self._registry_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to load marketplace registry: {e}")
        return {"skills": {}, "metadata": {"created_at": datetime.now(TZ8).isoformat()}}

    def _save_registry(self) -> None:
        """持久化市集註冊表."""
        try:
            self._registry["metadata"]["updated_at"] = datetime.now(TZ8).isoformat()
            self._registry_path.write_text(
                json.dumps(self._registry, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to save marketplace registry: {e}")

    # ── Package ─────────────────────────────────────────

    def package_skill(self, skill_id: str, version: str = "1.0.0") -> Dict:
        """將技能打包為可分發的 .mskill 格式.

        Args:
            skill_id: 技能 ID
            version: 版本號

        Returns:
            Dict: {package_path, manifest, size_bytes} 或 {error}
        """
        # 找到技能來源
        skill_path = self._find_skill_source(skill_id)
        if skill_path is None:
            return {"error": f"Skill '{skill_id}' not found"}

        # 讀取技能資料
        try:
            skill_data = json.loads(skill_path.read_text(encoding="utf-8"))
        except Exception as e:
            return {"error": f"Failed to read skill: {e}"}

        # 建立 manifest
        manifest = self._create_manifest(skill_data, version)

        # 打包為 .mskill (zip)
        package_name = f"{skill_id}-{version}{MSKILL_EXTENSION}"
        package_path = self._packages_dir / package_name

        try:
            with zipfile.ZipFile(str(package_path), "w", zipfile.ZIP_DEFLATED) as zf:
                # 寫入 manifest
                zf.writestr(MANIFEST_FILENAME, json.dumps(manifest, ensure_ascii=False, indent=2))
                # 寫入技能定義
                zf.writestr("skill.json", json.dumps(skill_data, ensure_ascii=False, indent=2))
                # 如果有附帶的 prompt 模板
                prompt_path = skill_path.parent / f"{skill_id}_prompt.txt"
                if prompt_path.exists():
                    zf.write(str(prompt_path), "prompt.txt")
        except Exception as e:
            return {"error": f"Packaging failed: {e}"}

        size_bytes = package_path.stat().st_size
        logger.info(f"Packaged skill: {package_name} ({size_bytes} bytes)")

        return {
            "package_path": str(package_path),
            "manifest": manifest,
            "size_bytes": size_bytes,
        }

    def _find_skill_source(self, skill_id: str) -> Optional[Path]:
        """在技能目錄中尋找技能來源檔案."""
        candidates = [
            self._workspace / "data" / "skills" / f"{skill_id}.json",
            self._workspace / "data" / "skills" / "community" / f"{skill_id}.json",
            self._workspace / "data" / "skills" / "forged" / f"{skill_id}.json",
        ]
        for p in candidates:
            if p.exists():
                return p
        return None

    def _create_manifest(self, skill_data: Dict, version: str = "1.0.0") -> Dict:
        """建立套件 manifest.

        Args:
            skill_data: 技能 JSON 資料
            version: 版本號

        Returns:
            Manifest dict
        """
        return {
            "format_version": "1.0",
            "skill_id": skill_data.get("id", skill_data.get("name", "unknown")),
            "name": skill_data.get("name", "Unnamed Skill"),
            "version": version,
            "description": skill_data.get("description", ""),
            "author": skill_data.get("author", os.getenv("MUSEON_NODE_ID", "anonymous")),
            "tags": skill_data.get("tags", []),
            "created_at": datetime.now(TZ8).isoformat(),
            "museon_min_version": "0.5.0",
            "dependencies": skill_data.get("dependencies", []),
            "checksum": "",  # 由 sign_package 填入
        }

    # ── Sign & Verify ───────────────────────────────────

    def sign_package(self, package_path: str) -> str:
        """簽章套件（SHA256）.

        Args:
            package_path: .mskill 檔案路徑

        Returns:
            SHA256 hex digest 字串
        """
        p = Path(package_path)
        if not p.exists():
            raise FileNotFoundError(f"Package not found: {package_path}")

        sha256 = hashlib.sha256()
        with open(str(p), "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)

        signature = sha256.hexdigest()

        # 寫入簽章檔
        sig_path = p.with_suffix(f"{MSKILL_EXTENSION}.sha256")
        try:
            sig_path.write_text(signature, encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write signature file: {e}")

        logger.info(f"Package signed: {p.name} -> {signature[:16]}...")
        return signature

    def verify_package(self, package_path: str, signature: str) -> bool:
        """驗證套件簽章.

        Args:
            package_path: .mskill 檔案路徑
            signature: 預期的 SHA256 hex digest

        Returns:
            True if valid
        """
        p = Path(package_path)
        if not p.exists():
            return False

        sha256 = hashlib.sha256()
        try:
            with open(str(p), "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            actual = sha256.hexdigest()
            is_valid = actual == signature
            if not is_valid:
                logger.warning(f"Signature mismatch for {p.name}: expected {signature[:16]}..., got {actual[:16]}...")
            return is_valid
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False

    # ── Marketplace ─────────────────────────────────────

    async def list_marketplace(self, category: Optional[str] = None) -> List[Dict]:
        """列出市集中的可用技能.

        Args:
            category: 可選的分類篩選

        Returns:
            技能列表
        """
        skills = list(self._registry.get("skills", {}).values())

        if category:
            skills = [s for s in skills if category.lower() in [t.lower() for t in s.get("tags", [])]]

        # 按發布時間排序
        skills.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        return skills

    async def publish_skill(
        self,
        package_path: str,
        price: float = 0.0,
        description: str = "",
    ) -> Dict:
        """發布技能到市集.

        Args:
            package_path: .mskill 檔案路徑
            price: 價格（0.0 = 免費）
            description: 補充描述

        Returns:
            發布結果 Dict
        """
        p = Path(package_path)
        if not p.exists():
            return {"error": f"Package not found: {package_path}"}

        # 讀取 manifest
        manifest = self._read_manifest_from_package(str(p))
        if manifest is None:
            return {"error": "Invalid package: no manifest found"}

        skill_id = manifest.get("skill_id", p.stem)

        # 簽章
        signature = self.sign_package(package_path)

        # 複製到市集套件目錄
        dest = self._packages_dir / p.name
        if str(p.resolve()) != str(dest.resolve()):
            try:
                shutil.copy2(str(p), str(dest))
            except Exception as e:
                return {"error": f"Failed to copy package: {e}"}

        # 註冊到 registry
        entry = {
            "skill_id": skill_id,
            "name": manifest.get("name", skill_id),
            "version": manifest.get("version", "1.0.0"),
            "description": description or manifest.get("description", ""),
            "author": manifest.get("author", "anonymous"),
            "tags": manifest.get("tags", []),
            "price": price,
            "signature": signature,
            "package_path": str(dest),
            "published_at": datetime.now(TZ8).isoformat(),
            "downloads": 0,
        }
        self._registry.setdefault("skills", {})[skill_id] = entry
        self._save_registry()

        # 發布事件
        try:
            if self._event_bus is not None:
                from museon.core.event_bus import SHARED_ASSET_PUBLISHED
                self._event_bus.publish(SHARED_ASSET_PUBLISHED, {
                    "asset_type": "skill",
                    "skill_id": skill_id,
                    "version": manifest.get("version", "1.0.0"),
                    "timestamp": datetime.now(TZ8).isoformat(),
                })
        except Exception as e:
            logger.warning(f"Failed to publish marketplace event: {e}")

        logger.info(f"Skill published: {skill_id} v{manifest.get('version', '1.0.0')}")
        return {"skill_id": skill_id, "status": "published", "entry": entry}

    async def install_skill(self, skill_id: str) -> Dict:
        """從市集安裝技能.

        Args:
            skill_id: 技能 ID

        Returns:
            安裝結果 Dict
        """
        entry = self._registry.get("skills", {}).get(skill_id)
        if entry is None:
            return {"error": f"Skill '{skill_id}' not found in marketplace"}

        package_path = entry.get("package_path", "")
        signature = entry.get("signature", "")

        # 驗證簽章
        if not self.verify_package(package_path, signature):
            return {"error": "Package signature verification failed"}

        # 解壓到已安裝目錄
        install_dir = self._installed_dir / skill_id
        install_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                zf.extractall(str(install_dir))
        except Exception as e:
            return {"error": f"Installation failed: {e}"}

        # 複製 skill.json 到技能目錄
        skill_json = install_dir / "skill.json"
        if skill_json.exists():
            dest_skill = self._workspace / "data" / "skills" / "community" / f"{skill_id}.json"
            dest_skill.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(str(skill_json), str(dest_skill))
            except Exception as e:
                logger.warning(f"Failed to copy skill to skills dir: {e}")

        # 更新下載數
        entry["downloads"] = entry.get("downloads", 0) + 1
        self._save_registry()

        logger.info(f"Skill installed: {skill_id}")
        return {
            "skill_id": skill_id,
            "status": "installed",
            "install_path": str(install_dir),
            "version": entry.get("version", "1.0.0"),
        }

    # ── Helpers ──────────────────────────────────────────

    @staticmethod
    def _read_manifest_from_package(package_path: str) -> Optional[Dict]:
        """從 .mskill 套件中讀取 manifest."""
        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                if MANIFEST_FILENAME in zf.namelist():
                    return json.loads(zf.read(MANIFEST_FILENAME).decode("utf-8"))
        except Exception as e:
            logger.warning(f"Failed to read manifest from {package_path}: {e}")
        return None
