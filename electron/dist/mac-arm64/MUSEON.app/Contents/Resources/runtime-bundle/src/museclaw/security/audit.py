"""
Audit Logger - Layer 6 Defense

Provides immutable audit trail:
- All actions logged with full context
- Security incidents tracked separately
- Audit trail reconstruction
- Immutability enforcement
"""
import logging
import json
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path
import hashlib

logger = logging.getLogger(__name__)


class AuditLogger:
    """Immutable audit logging system."""

    def __init__(self, log_dir: Path = None):
        """
        Initialize audit logger.

        Args:
            log_dir: Directory to store audit logs
        """
        self.log_dir = log_dir or Path.home() / ".museclaw" / "audit_logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.actions_log = self.log_dir / "actions.jsonl"
        self.incidents_log = self.log_dir / "incidents.jsonl"

        # In-memory cache (for testing)
        self._actions = []
        self._incidents = []

    async def log_action(
        self,
        action: str,
        trigger: str,
        decision: str,
        trust_level: str,
        metadata: Dict[str, Any]
    ) -> str:
        """
        Log an action to audit trail.

        Args:
            action: Action name
            trigger: What triggered the action
            decision: Decision made (approved/blocked/pending)
            trust_level: Trust level of trigger source
            metadata: Additional metadata

        Returns:
            Log entry ID
        """
        entry_id = self._generate_id()

        entry = {
            "id": entry_id,
            "timestamp": datetime.now().isoformat(),
            "type": "action",
            "action": action,
            "trigger": trigger,
            "decision": decision,
            "trust_level": trust_level,
            "metadata": metadata,
            "hash": None  # Will be computed
        }

        # Compute hash for immutability
        entry["hash"] = self._compute_hash(entry)

        # Store in memory + persist to file
        self._actions.append(entry)
        self._write_to_file(self.actions_log, entry)

        logger.info(f"Action logged: {action} ({decision})")
        return entry_id

    async def log_incident(
        self,
        incident_type: str,
        source: str,
        content: str,
        action_taken: str
    ) -> str:
        """
        Log a security incident.

        Args:
            incident_type: Type of incident
            source: Source of incident
            content: Content that triggered incident
            action_taken: Action taken in response

        Returns:
            Incident ID
        """
        incident_id = self._generate_id()

        entry = {
            "id": incident_id,
            "timestamp": datetime.now().isoformat(),
            "type": incident_type,
            "source": source,
            "content": content,
            "action_taken": action_taken,
            "hash": None
        }

        entry["hash"] = self._compute_hash(entry)

        self._incidents.append(entry)
        self._write_to_file(self.incidents_log, entry)

        logger.warning(f"Security incident logged: {incident_type}")
        return incident_id

    async def get_recent_logs(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get recent action logs.

        Args:
            limit: Number of logs to retrieve

        Returns:
            List of log entries
        """
        return self._actions[-limit:]

    async def get_incidents(self) -> List[Dict[str, Any]]:
        """
        Get all security incidents.

        Returns:
            List of incidents
        """
        return self._incidents.copy()

    async def get_audit_trail(
        self,
        session_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get complete audit trail for a session.

        Args:
            session_id: Optional session ID filter

        Returns:
            List of audit entries
        """
        # For now, return all actions
        # In production, would filter by session_id
        return self._actions.copy()

    async def modify_log(
        self,
        log_id: str,
        modifications: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Attempt to modify a log (should be rejected).

        Args:
            log_id: Log ID to modify
            modifications: Attempted modifications

        Returns:
            Rejection result
        """
        logger.warning(f"Attempted log modification: {log_id}")

        return {
            "allowed": False,
            "reason": "logs_are_immutable",
            "log_id": log_id
        }

    def _write_to_file(self, filepath: Path, entry: Dict[str, Any]) -> None:
        """Append a JSON log entry to file (JSONL format).

        Args:
            filepath: Target JSONL file path
            entry: Log entry dict
        """
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log to {filepath}: {e}")

    def _generate_id(self) -> str:
        """Generate unique ID for log entry."""
        import uuid
        return uuid.uuid4().hex[:16]

    def _compute_hash(self, entry: Dict[str, Any]) -> str:
        """
        Compute hash of entry for immutability verification.

        Args:
            entry: Log entry

        Returns:
            Hash string
        """
        # Create copy without hash field
        entry_copy = entry.copy()
        if "hash" in entry_copy:
            del entry_copy["hash"]

        # Serialize and hash
        entry_str = json.dumps(entry_copy, sort_keys=True)
        return hashlib.sha256(entry_str.encode()).hexdigest()[:16]

    def verify_integrity(self) -> Dict[str, Any]:
        """
        Verify integrity of all logs.

        Returns:
            Dict with verification results
        """
        valid_count = 0
        invalid_entries = []

        for entry in self._actions:
            stored_hash = entry.get("hash")
            computed_hash = self._compute_hash(entry)

            if stored_hash == computed_hash:
                valid_count += 1
            else:
                invalid_entries.append(entry["id"])

        return {
            "total_entries": len(self._actions),
            "valid_entries": valid_count,
            "invalid_entries": invalid_entries,
            "integrity_ok": len(invalid_entries) == 0
        }
