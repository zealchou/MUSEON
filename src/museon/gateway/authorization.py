"""Gateway Authorization Engine — 配對碼動態授權 + 工具授權迴圈 + 分級授權策略.

Architecture:
- ApprovalQueue: 通用佇列基底（FIFO + 超時 + asyncio.Event 非阻塞等待）
- ToolAuthorizationQueue: 工具授權專用佇列，支援 session-level grant
- PairingManager: 配對碼動態授權（6 位英數碼 + 5 分鐘有效 + 3 次嘗試上限）
- AuthorizationPolicy: 三級策略（auto / ask / block）

Persistent state:
- ~/.museon/auth/allowlist.json — 動態授權使用者清單
- ~/.museon/auth/policy.json — 分級授權策略設定
"""

import asyncio
import json
import logging
import random
import string
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

# ── Runtime directory ──
_AUTH_DIR = Path.home() / ".museon" / "auth"


# ══════════════════════════════════════════════════
# ApprovalQueue — 通用佇列基底
# ══════════════════════════════════════════════════


class ApprovalQueue:
    """通用審批佇列：FIFO + 超時 + asyncio.Event 非阻塞等待.

    EscalationQueue 與 ToolAuthorizationQueue 的共用基底。
    """

    DEFAULT_TIMEOUT_SECONDS = 600  # 10 minutes

    def __init__(self, timeout_seconds: int = None):
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._order: list = []
        self._events: Dict[str, asyncio.Event] = {}
        self._timeout_seconds = timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS

    def add(self, entry_id: str, payload: Dict[str, Any]) -> None:
        """新增一筆待審批項目."""
        payload["created_at"] = datetime.now()
        payload["resolved"] = False
        payload["approved"] = None
        self._pending[entry_id] = payload
        self._order.append(entry_id)
        self._events[entry_id] = asyncio.Event()

    def resolve(self, entry_id: str, approved: bool) -> bool:
        """解決指定項目."""
        if entry_id not in self._pending:
            return False
        self._pending[entry_id]["resolved"] = True
        self._pending[entry_id]["approved"] = approved
        # 觸發等待中的 Event
        event = self._events.get(entry_id)
        if event:
            event.set()
        return True

    def resolve_latest(self, approved: bool) -> Optional[str]:
        """解決最早的未處理項目（FIFO）."""
        for eid in self._order:
            if eid in self._pending:
                entry = self._pending[eid]
                if not entry["resolved"] and not self.is_timed_out(eid):
                    self.resolve(eid, approved)
                    return eid
        return None

    def is_timed_out(self, entry_id: str) -> bool:
        entry = self._pending.get(entry_id)
        if not entry:
            return True
        if entry["resolved"]:
            return False
        return (datetime.now() - entry["created_at"]) > timedelta(
            seconds=self._timeout_seconds
        )

    def get(self, entry_id: str) -> Optional[Dict]:
        return self._pending.get(entry_id)

    def get_latest(self) -> Optional[Dict]:
        """取得最早的未處理項目."""
        for eid in self._order:
            if eid in self._pending:
                entry = self._pending[eid]
                if not entry["resolved"] and not self.is_timed_out(eid):
                    return entry
        return None

    def has_pending(self) -> bool:
        return self.pending_count() > 0

    def pending_count(self) -> int:
        return sum(
            1
            for eid in self._order
            if eid in self._pending
            and not self._pending[eid]["resolved"]
            and not self.is_timed_out(eid)
        )

    async def wait_for_resolution(
        self, entry_id: str, timeout_seconds: int = None
    ) -> Optional[bool]:
        """非阻塞等待項目被解決. 回傳 approved (True/False) 或 None (超時)."""
        timeout = timeout_seconds or self._timeout_seconds
        event = self._events.get(entry_id)
        if not event:
            return None
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            entry = self._pending.get(entry_id)
            if entry:
                return entry.get("approved")
            return None
        except asyncio.TimeoutError:
            # 超時自動拒絕
            self.resolve(entry_id, approved=False)
            return False

    def purge_old(self, hours: int = 2) -> None:
        cutoff = datetime.now() - timedelta(hours=hours)
        to_delete = [
            k for k, v in self._pending.items() if v["created_at"] < cutoff
        ]
        for k in to_delete:
            del self._pending[k]
            self._events.pop(k, None)
        self._order = [eid for eid in self._order if eid in self._pending]


# ══════════════════════════════════════════════════
# ToolAuthorizationQueue — 工具授權專用佇列
# ══════════════════════════════════════════════════


class ToolAuthorizationQueue(ApprovalQueue):
    """工具授權佇列：紀錄工具名、參數摘要、請求來源.

    支援 session-level grant（「本工具全允許」）。
    """

    TOOL_AUTH_TIMEOUT = 300  # 5 minutes

    def __init__(self):
        super().__init__(timeout_seconds=self.TOOL_AUTH_TIMEOUT)
        self._session_grants: Dict[str, Set[str]] = {}
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"tauth_{self._counter}_{int(datetime.now().timestamp())}"

    def has_session_grant(self, session_id: str, tool_name: str) -> bool:
        """檢查 session 是否已授權此工具."""
        return tool_name in self._session_grants.get(session_id, set())

    def grant_session(self, session_id: str, tool_name: str) -> None:
        """授予 session-level 工具授權."""
        self._session_grants.setdefault(session_id, set()).add(tool_name)
        logger.info(
            f"Session grant: {tool_name} for session {session_id}"
        )

    async def request_authorization(
        self,
        tool_name: str,
        args_summary: str,
        session_id: str,
        user_name: str,
    ) -> tuple:
        """建立授權請求，回傳 (entry_id, asyncio.Event).

        Caller 拿到 entry_id 後：
        1. 推 inline keyboard 到老闆 DM
        2. await wait_for_resolution(entry_id)

        Returns:
            (entry_id, event) — entry_id 用於 callback 辨識
        """
        # 快速路徑：session grant
        if self.has_session_grant(session_id, tool_name):
            return None, None  # 已授權，不需要等待

        entry_id = self._next_id()
        payload = {
            "tool_name": tool_name,
            "args_summary": args_summary,
            "session_id": session_id,
            "user_name": user_name,
        }
        self.add(entry_id, payload)
        return entry_id, self._events[entry_id]


# ══════════════════════════════════════════════════
# PairingManager — 配對碼動態授權
# ══════════════════════════════════════════════════

# 排除容易混淆的字元
_PAIRING_ALPHABET = "".join(
    c for c in string.ascii_uppercase + string.digits if c not in "OI01"
)


class PairingManager:
    """配對碼系統：6 位英數碼 + 5 分鐘有效 + 3 次嘗試上限.

    持久化到 ~/.museon/auth/allowlist.json。
    """

    CODE_LENGTH = 6
    CODE_EXPIRY_SECONDS = 300  # 5 minutes
    MAX_ATTEMPTS = 3

    def __init__(self, auth_dir: Path = None):
        self._auth_dir = auth_dir or _AUTH_DIR
        self._auth_dir.mkdir(parents=True, exist_ok=True)
        self._allowlist_path = self._auth_dir / "allowlist.json"
        # 動態允許清單 {user_id: {display_name, trust_level, added_at, ttl}}
        self._allowlist: Dict[str, Dict[str, Any]] = {}
        # 待驗證配對碼 {code: {user_id, display_name, created_at, attempts}}
        self._pending_codes: Dict[str, Dict[str, Any]] = {}
        self.load()

    def generate_code(self, telegram_user_id: str, display_name: str) -> str:
        """生成配對碼. 若該 user 已有未過期碼，回傳同一組."""
        # 清理過期碼
        self._purge_expired_codes()

        # 已有碼？
        for code, info in self._pending_codes.items():
            if info["user_id"] == str(telegram_user_id):
                return code

        code = "".join(random.choices(_PAIRING_ALPHABET, k=self.CODE_LENGTH))
        # 避免碰撞
        while code in self._pending_codes:
            code = "".join(random.choices(_PAIRING_ALPHABET, k=self.CODE_LENGTH))

        self._pending_codes[code] = {
            "user_id": str(telegram_user_id),
            "display_name": display_name,
            "created_at": datetime.now(),
            "attempts": 0,
        }
        return code

    def verify_code(self, code: str) -> Optional[Dict[str, str]]:
        """驗證配對碼. 成功回傳 {user_id, display_name}，失敗回傳 None."""
        self._purge_expired_codes()
        code = code.upper().strip()

        info = self._pending_codes.get(code)
        if not info:
            return None

        info["attempts"] += 1
        if info["attempts"] > self.MAX_ATTEMPTS:
            del self._pending_codes[code]
            return None

        # 驗證成功
        result = {
            "user_id": info["user_id"],
            "display_name": info["display_name"],
        }
        del self._pending_codes[code]
        return result

    def add_user(
        self,
        user_id: str,
        display_name: str,
        trust_level: str = "VERIFIED",
        ttl: int = None,
    ) -> None:
        """新增動態授權使用者. ttl 為秒數，None 表示永久."""
        self._allowlist[str(user_id)] = {
            "display_name": display_name,
            "trust_level": trust_level,
            "added_at": datetime.now().isoformat(),
            "ttl": ttl,
        }
        self.save()
        logger.info(
            f"PairingManager: user {user_id} ({display_name}) "
            f"added with trust={trust_level}, ttl={ttl}"
        )

    def remove_user(self, user_id: str) -> bool:
        if str(user_id) in self._allowlist:
            del self._allowlist[str(user_id)]
            self.save()
            return True
        return False

    def is_paired(self, user_id: str) -> bool:
        """檢查使用者是否在動態允許清單中（含 TTL 檢查）."""
        entry = self._allowlist.get(str(user_id))
        if not entry:
            return False
        # TTL 檢查
        ttl = entry.get("ttl")
        if ttl is not None:
            added = datetime.fromisoformat(entry["added_at"])
            if datetime.now() > added + timedelta(seconds=ttl):
                del self._allowlist[str(user_id)]
                self.save()
                return False
        return True

    def get_dynamic_trust(self, user_id: str) -> Optional[str]:
        """取得動態信任等級. 不在清單中回傳 None."""
        if not self.is_paired(user_id):
            return None
        return self._allowlist[str(user_id)].get("trust_level", "VERIFIED")

    def list_users(self) -> Dict[str, Dict[str, Any]]:
        """列出所有動態授權使用者（自動清除過期）."""
        # 清除過期
        expired = []
        for uid, entry in self._allowlist.items():
            ttl = entry.get("ttl")
            if ttl is not None:
                added = datetime.fromisoformat(entry["added_at"])
                if datetime.now() > added + timedelta(seconds=ttl):
                    expired.append(uid)
        for uid in expired:
            del self._allowlist[uid]
        if expired:
            self.save()
        return dict(self._allowlist)

    def load(self) -> None:
        """從 allowlist.json 載入."""
        if self._allowlist_path.exists():
            try:
                data = json.loads(
                    self._allowlist_path.read_text(encoding="utf-8")
                )
                self._allowlist = data.get("users", {})
                logger.info(
                    f"PairingManager: loaded {len(self._allowlist)} users"
                )
            except Exception as e:
                logger.warning(f"PairingManager: load failed: {e}")
                self._allowlist = {}

    def save(self) -> None:
        """原子寫入 allowlist.json."""
        self._auth_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0.0",
            "updated_at": datetime.now().isoformat(),
            "users": self._allowlist,
        }
        # 原子寫入：先寫暫存檔再 rename
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(self._auth_dir), suffix=".tmp"
            )
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            Path(tmp_path).replace(self._allowlist_path)
        except Exception as e:
            logger.error(f"PairingManager: save failed: {e}")

    def _purge_expired_codes(self) -> None:
        now = datetime.now()
        expired = [
            code
            for code, info in self._pending_codes.items()
            if (now - info["created_at"]).total_seconds() > self.CODE_EXPIRY_SECONDS
        ]
        for code in expired:
            del self._pending_codes[code]


# ══════════════════════════════════════════════════
# AuthorizationPolicy — 三級授權策略
# ══════════════════════════════════════════════════

DEFAULT_POLICY: Dict[str, list] = {
    "auto": [
        "museon_memory_read",
        "museon_health_status",
        "museon_anima_status",
        "museon_skill_track",
        "museon_pulse_status",
        "museon_federation_status",
        "museon_auth_status",
    ],
    "ask": [
        "shell_exec",
        "write_file",
        "file_write_rich",
        "delete_file",
        "create_directory",
        "send_message",
        "post_social",
        "telegram_send",
        "line_send",
        "instagram_post",
        "museon_memory_write",
    ],
    "block": [
        "modify_security",
        "delete_account",
        "delete_user_data",
        "transfer_money",
    ],
}


class AuthorizationPolicy:
    """三級授權策略：auto / ask / block.

    持久化到 ~/.museon/auth/policy.json。
    未列入任何級別的工具預設為 ask。
    """

    def __init__(self, auth_dir: Path = None):
        self._auth_dir = auth_dir or _AUTH_DIR
        self._auth_dir.mkdir(parents=True, exist_ok=True)
        self._policy_path = self._auth_dir / "policy.json"
        self._policy: Dict[str, list] = {}
        self.load()

    def classify(self, tool_name: str) -> str:
        """分類工具為 auto / ask / block."""
        for tier in ("block", "auto", "ask"):
            if tool_name in self._policy.get(tier, []):
                return tier
        # MCP 工具預設 auto（唯讀查詢類）
        if tool_name.startswith("museon_") and "write" not in tool_name:
            return "auto"
        # 未列入的工具預設 ask
        return "ask"

    def move_tool(self, tool_name: str, target_tier: str) -> bool:
        """移動工具到指定級別."""
        if target_tier not in ("auto", "ask", "block"):
            return False
        # 從所有級別移除
        for tier in ("auto", "ask", "block"):
            tools = self._policy.get(tier, [])
            if tool_name in tools:
                tools.remove(tool_name)
        # 加入目標級別
        self._policy.setdefault(target_tier, []).append(tool_name)
        self.save()
        return True

    def list_policy(self) -> Dict[str, list]:
        return dict(self._policy)

    def load(self) -> None:
        """從 policy.json 載入. 不存在則使用預設."""
        if self._policy_path.exists():
            try:
                data = json.loads(
                    self._policy_path.read_text(encoding="utf-8")
                )
                self._policy = {
                    "auto": data.get("auto", DEFAULT_POLICY["auto"]),
                    "ask": data.get("ask", DEFAULT_POLICY["ask"]),
                    "block": data.get("block", DEFAULT_POLICY["block"]),
                }
                return
            except Exception as e:
                logger.warning(f"AuthorizationPolicy: load failed: {e}")
        # 使用預設
        self._policy = {k: list(v) for k, v in DEFAULT_POLICY.items()}

    def save(self) -> None:
        """原子寫入 policy.json."""
        self._auth_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0.0",
            "updated_at": datetime.now().isoformat(),
            **self._policy,
        }
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(self._auth_dir), suffix=".tmp"
            )
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            Path(tmp_path).replace(self._policy_path)
        except Exception as e:
            logger.error(f"AuthorizationPolicy: save failed: {e}")


# ── Singletons ──

_tool_auth_queue: Optional[ToolAuthorizationQueue] = None
_pairing_manager: Optional[PairingManager] = None
_authorization_policy: Optional[AuthorizationPolicy] = None


def get_tool_auth_queue() -> ToolAuthorizationQueue:
    global _tool_auth_queue
    if _tool_auth_queue is None:
        _tool_auth_queue = ToolAuthorizationQueue()
    return _tool_auth_queue


def get_pairing_manager() -> PairingManager:
    global _pairing_manager
    if _pairing_manager is None:
        _pairing_manager = PairingManager()
    return _pairing_manager


def get_authorization_policy() -> AuthorizationPolicy:
    global _authorization_policy
    if _authorization_policy is None:
        _authorization_policy = AuthorizationPolicy()
    return _authorization_policy
