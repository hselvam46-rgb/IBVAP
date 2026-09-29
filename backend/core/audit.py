"""
Append-Only Tamper-Evident Audit Trail with SHA-256 Hash Chaining.
Guarantees strict auditability for judicial review and defense integrity.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session
from backend.database.models import AuditLog


def format_ts(dt) -> str:
    """Standardize datetime string format across database engines."""
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    return str(dt)[:19]


def log_audit_event(
    db: Session,
    operator_id: str,
    action_type: str,
    details: Dict[str, Any],
    ip_address: str = "127.0.0.1",
    timestamp: datetime = None
) -> AuditLog:
    """
    Append an audit log record with cryptographic SHA-256 chaining.
    prev_hash links back to the previous entry, forming an immutable ledger.
    """
    latest_log = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
    prev_hash = latest_log.sha256_hash if latest_log else ("0" * 64)

    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    ts_str = format_ts(timestamp)
    details_str = json.dumps(details, sort_keys=True)

    # Cryptographic preimage: timestamp | operator_id | action_type | details_str | prev_hash
    preimage = f"{ts_str}|{operator_id}|{action_type}|{details_str}|{prev_hash}"
    entry_hash = hashlib.sha256(preimage.encode("utf-8")).hexdigest()

    audit_entry = AuditLog(
        timestamp=timestamp,
        operator_id=operator_id,
        action_type=action_type,
        details_json=details_str,
        ip_address=ip_address,
        prev_hash=prev_hash,
        sha256_hash=entry_hash
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(audit_entry)
    return audit_entry


def verify_audit_chain(db: Session) -> Tuple[bool, int, str]:
    """
    Validate the entire audit chain from genesis to head.
    Returns: (is_valid: bool, records_verified: int, message: str)
    """
    logs = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    if not logs:
        return True, 0, "Audit log is empty."

    expected_prev = "0" * 64
    for idx, entry in enumerate(logs):
        if idx == 0:
            # Genesis record starts with 64 zeros
            if entry.prev_hash != expected_prev:
                return False, idx, f"Genesis record #{entry.id} invalid prev_hash."
        else:
            if entry.prev_hash != expected_prev:
                return False, idx, f"Chain broken at record #{entry.id}: prev_hash mismatch."

        # Re-compute hash using exact standardized timestamp string
        ts_str = format_ts(entry.timestamp)
        preimage = f"{ts_str}|{entry.operator_id}|{entry.action_type}|{entry.details_json}|{entry.prev_hash}"
        computed_hash = hashlib.sha256(preimage.encode("utf-8")).hexdigest()

        if computed_hash != entry.sha256_hash:
            return False, idx, f"Tamper detected at record #{entry.id}: hash signature mismatch."

        expected_prev = entry.sha256_hash

    return True, len(logs), f"Chain intact. All {len(logs)} records cryptographically verified."
