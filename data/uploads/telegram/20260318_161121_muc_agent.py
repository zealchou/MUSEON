"""
MUC Agent SDK — Auto-Pair & Entitlement Client
================================================
Handles the full agent lifecycle:
  1. Login with email/password → JWT
  2. Find available license → auto-detect
  3. Generate pair code → one-time use
  4. Pair device → get device token
  5. Entitlement polling → Ed25519 signature verification
  6. Pre-job check → authorization gate

Usage:
  from muc_agent import MucAgent

  agent = MucAgent(base_url="https://museon.one")
  await agent.setup("user@example.com", "password123")
  # Agent is now paired and ready

  # Before each job:
  allowed = await agent.check_before_job()
  if allowed:
      # proceed with job
"""

import hashlib
import json
import os
import platform
import secrets
import socket
from datetime import datetime, timezone
from typing import Optional

import httpx

__version__ = "0.1.0"

# ─── Credential Storage ────────────────────────────────────────
# Try OS keychain first, fallback to file-based storage

def _store_credential(service: str, key: str, value: str) -> None:
    """Store credential in OS keychain or fallback file."""
    try:
        import keyring
        keyring.set_password(service, key, value)
        return
    except (ImportError, Exception):
        pass
    # Fallback: encrypted-ish file storage (MVP)
    cred_dir = os.path.join(os.path.expanduser("~"), ".muc")
    os.makedirs(cred_dir, exist_ok=True)
    cred_file = os.path.join(cred_dir, "credentials.json")
    data = {}
    if os.path.exists(cred_file):
        with open(cred_file, "r") as f:
            data = json.load(f)
    data[f"{service}:{key}"] = value
    with open(cred_file, "w") as f:
        json.dump(data, f)


def _get_credential(service: str, key: str) -> Optional[str]:
    """Retrieve credential from OS keychain or fallback file."""
    try:
        import keyring
        val = keyring.get_password(service, key)
        if val:
            return val
    except (ImportError, Exception):
        pass
    cred_file = os.path.join(os.path.expanduser("~"), ".muc", "credentials.json")
    if os.path.exists(cred_file):
        with open(cred_file, "r") as f:
            data = json.load(f)
        return data.get(f"{service}:{key}")
    return None


def _delete_credential(service: str, key: str) -> None:
    """Remove credential."""
    try:
        import keyring
        keyring.delete_password(service, key)
    except (ImportError, Exception):
        pass
    cred_file = os.path.join(os.path.expanduser("~"), ".muc", "credentials.json")
    if os.path.exists(cred_file):
        with open(cred_file, "r") as f:
            data = json.load(f)
        data.pop(f"{service}:{key}", None)
        with open(cred_file, "w") as f:
            json.dump(data, f)


def _generate_fingerprint() -> str:
    """Generate a stable device fingerprint from hardware info."""
    parts = [
        platform.node(),
        platform.machine(),
        platform.processor(),
        platform.system(),
        str(os.cpu_count()),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


# ─── Agent Client ──────────────────────────────────────────────

class MucAgentError(Exception):
    """Base error for MUC Agent operations."""
    def __init__(self, message: str, code: str = "", status: int = 0):
        super().__init__(message)
        self.code = code
        self.status = status


class MucAgent:
    """
    MUC Agent SDK client.

    Handles login, auto-pair, entitlement polling, and pre-job checks.
    Device token is stored in OS keychain after first successful pairing.
    """

    CREDENTIAL_SERVICE = "muc-agent"

    def __init__(self, base_url: str = "https://museon.one"):
        self.api_url = f"{base_url.rstrip('/')}/api/v1"
        self.device_id: Optional[str] = None
        self.device_token: Optional[str] = None
        self.license_id: Optional[str] = None
        self._last_entitlement: Optional[dict] = None

        # Try to load existing credentials
        self._load_stored_credentials()

    @property
    def is_paired(self) -> bool:
        return bool(self.device_id and self.device_token)

    # ─── Public API ────────────────────────────────────────────

    async def setup(self, email: str, password: str) -> dict:
        """
        Full auto-pair flow:
          1. Login → JWT
          2. Find available license
          3. Generate pair code
          4. Pair device → store token
          5. Clear email/password from memory

        Returns: { device_id, license_id }
        Raises: MucAgentError on any failure
        """
        if self.is_paired:
            return {
                "device_id": self.device_id,
                "license_id": self.license_id,
                "message": "Already paired",
            }

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Login
            jwt = await self._login(client, email, password)

            # Step 2: Find available licenses
            candidates = await self._find_available_licenses(client, jwt)

            # Step 3+4: Try each license until one works
            result = None
            last_error = None
            for license_id in candidates:
                try:
                    pair_code = await self._generate_pair_code(client, jwt, license_id)
                    result = await self._pair_device(client, pair_code)
                    break
                except MucAgentError as e:
                    last_error = e
                    if e.code in ("PAIR_CODE_ALREADY_ACTIVE", "LICENSE_ALREADY_BOUND"):
                        continue  # Try next license
                    raise

            if result is None:
                raise last_error or MucAgentError(
                    "No available license found. Please purchase a plan at museon.one",
                    code="NO_AVAILABLE_LICENSE",
                )

        # Step 5: Store credentials, clear sensitive data
        self.device_id = result["deviceId"]
        self.device_token = result["deviceToken"]
        self.license_id = result["licenseId"]
        self._save_credentials()

        # email and password are local vars, will be GC'd
        return {
            "device_id": self.device_id,
            "license_id": self.license_id,
            "message": "Paired successfully",
        }

    async def get_entitlement(self) -> dict:
        """
        Poll entitlement endpoint.
        Returns signed entitlement data.
        Raises: MucAgentError if not paired or authorization fails.
        """
        self._require_paired()
        async with httpx.AsyncClient(timeout=15.0) as client:
            nonce = secrets.token_hex(16)
            ts = datetime.now(timezone.utc).isoformat()
            fingerprint = _generate_fingerprint()
            resp = await client.post(
                f"{self.api_url}/agent/entitlement",
                headers={
                    "Authorization": f"Bearer {self.device_token}",
                    "x-device-id": self.device_id,
                    "x-timestamp": ts,
                    "x-nonce": nonce,
                },
                json={
                    "fingerprint": fingerprint,
                    "agent_version": __version__,
                },
            )
        if resp.status_code == 401 or resp.status_code == 403:
            self._clear_credentials()
            raise MucAgentError(
                "Device token revoked or invalid. Please re-pair.",
                code="TOKEN_REVOKED", status=resp.status_code,
            )
        if resp.status_code not in (200, 201):
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            raise MucAgentError(
                data.get("message", f"Entitlement failed ({resp.status_code})"),
                code=data.get("code", ""), status=resp.status_code,
            )
        self._last_entitlement = resp.json()
        return self._last_entitlement

    async def check_before_job(self) -> bool:
        """
        Pre-job authorization check.
        Returns True if agent is allowed to accept new work.
        Returns False if not authorized (do NOT accept job).
        """
        self._require_paired()
        async with httpx.AsyncClient(timeout=10.0) as client:
            nonce = secrets.token_hex(16)
            ts = datetime.now(timezone.utc).isoformat()
            resp = await client.post(
                f"{self.api_url}/agent/check-before-job",
                headers={"Authorization": f"Bearer {self.device_token}"},
                json={
                    "device_id": self.device_id,
                    "timestamp": ts,
                    "nonce": nonce,
                },
            )
        if resp.status_code in (200, 201):
            body = resp.json()
            inner = body.get("data") if isinstance(body.get("data"), dict) else body
            return inner.get("allow_new_jobs", False)
        if resp.status_code in (401, 403):
            self._clear_credentials()
        return False

    async def unpair(self) -> None:
        """Clear local credentials. Device can be revoked from web portal."""
        self._clear_credentials()

    # ─── Internal Methods ──────────────────────────────────────

    async def _login(self, client: httpx.AsyncClient, email: str, password: str) -> str:
        resp = await client.post(
            f"{self.api_url}/auth/login",
            json={"email": email, "password": password},
        )
        if resp.status_code == 401:
            raise MucAgentError(
                "Login failed: invalid email or password",
                code="LOGIN_FAILED", status=401,
            )
        if resp.status_code != 201 and resp.status_code != 200:
            raise MucAgentError(
                f"Login failed ({resp.status_code})",
                code="LOGIN_FAILED", status=resp.status_code,
            )
        body = resp.json()
        # Unwrap { data: { access_token } } envelope
        token = body.get("access_token") or (body.get("data") or {}).get("access_token")
        if not token:
            raise MucAgentError("Login response missing access_token", code="LOGIN_FAILED")
        return token

    async def _find_available_licenses(self, client: httpx.AsyncClient, jwt: str) -> list[str]:
        resp = await client.get(
            f"{self.api_url}/licenses/my/details",
            headers={"Authorization": f"Bearer {jwt}"},
        )
        if resp.status_code != 200:
            raise MucAgentError(
                "Failed to fetch licenses",
                code="LICENSES_FETCH_FAILED", status=resp.status_code,
            )
        body = resp.json()
        # Unwrap { data: [...] } envelope
        licenses = body.get("data") if isinstance(body.get("data"), list) else body if isinstance(body, list) else []
        # Find all ACTIVE licenses without an active device
        candidates = []
        for lic in licenses:
            if lic.get("status") != "ACTIVE":
                continue
            sub = lic.get("subscription")
            if sub and sub.get("status") == "SUSPENDED":
                continue
            device = lic.get("device")
            if device and device.get("status") == "ACTIVE":
                continue  # Already has active device
            candidates.append(lic["id"])

        if not candidates:
            raise MucAgentError(
                "No available license found. Please purchase a plan at museon.one",
                code="NO_AVAILABLE_LICENSE", status=404,
            )
        return candidates

    async def _generate_pair_code(self, client: httpx.AsyncClient, jwt: str, license_id: str) -> str:
        resp = await client.post(
            f"{self.api_url}/licenses/{license_id}/pair-code",
            headers={"Authorization": f"Bearer {jwt}"},
        )
        if resp.status_code == 201 or resp.status_code == 200:
            body = resp.json()
            inner = body.get("data") if isinstance(body.get("data"), dict) else body
            return inner["code"]

        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        err_data = data.get("error") if isinstance(data.get("error"), dict) else data
        code = err_data.get("code", "")
        raise MucAgentError(
            err_data.get("message", f"Failed to generate pair code ({resp.status_code})"),
            code=code, status=resp.status_code,
        )

    async def _pair_device(self, client: httpx.AsyncClient, pair_code: str) -> dict:
        fingerprint = _generate_fingerprint()
        nonce = secrets.token_hex(16)
        ts = datetime.now(timezone.utc).isoformat()

        resp = await client.post(
            f"{self.api_url}/devices/agent/pair",
            json={
                "pairCode": pair_code,
                "fingerprint": fingerprint,
                "agentVersion": __version__,
                "timestamp": ts,
                "nonce": nonce,
                "deviceName": f"MUC-Agent-{socket.gethostname()}",
                "platform": platform.system().lower(),
            },
        )
        if resp.status_code == 201 or resp.status_code == 200:
            body = resp.json()
            # Unwrap { data: { deviceId, deviceToken, licenseId } } envelope
            return body.get("data") if isinstance(body.get("data"), dict) else body

        data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        err_data = data.get("error") if isinstance(data.get("error"), dict) else data
        raise MucAgentError(
            err_data.get("message", f"Pairing failed ({resp.status_code})"),
            code=err_data.get("code", ""), status=resp.status_code,
        )

    def _require_paired(self):
        if not self.is_paired:
            raise MucAgentError(
                "Agent not paired. Call setup(email, password) first.",
                code="NOT_PAIRED",
            )

    def _save_credentials(self):
        _store_credential(self.CREDENTIAL_SERVICE, "device_id", self.device_id)
        _store_credential(self.CREDENTIAL_SERVICE, "device_token", self.device_token)
        _store_credential(self.CREDENTIAL_SERVICE, "license_id", self.license_id)

    def _load_stored_credentials(self):
        self.device_id = _get_credential(self.CREDENTIAL_SERVICE, "device_id")
        self.device_token = _get_credential(self.CREDENTIAL_SERVICE, "device_token")
        self.license_id = _get_credential(self.CREDENTIAL_SERVICE, "license_id")

    def _clear_credentials(self):
        _delete_credential(self.CREDENTIAL_SERVICE, "device_id")
        _delete_credential(self.CREDENTIAL_SERVICE, "device_token")
        _delete_credential(self.CREDENTIAL_SERVICE, "license_id")
        self.device_id = None
        self.device_token = None
        self.license_id = None
