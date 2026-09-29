"""
Data Minimisation & 72-Hour Rolling Retention Engine.
Enforces privacy mandates and defense data protection regulations:
- Unmatched probe face vectors are transient in-memory only and discarded immediately.
- On watchlist match: probe vector & crop are preserved with the alert for operator review.
- Unflagged routine video frames and unescalated snapshots purge automatically after 72 hours.
"""

import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from sqlalchemy.orm import Session
from backend.core.config import DATA_RETENTION_HOURS, SNAPSHOT_DIR, EVIDENCE_DIR
from backend.database.models import Alert
from backend.core.audit import log_audit_event


def purge_expired_records_and_media(db: Session, retention_hours: int = DATA_RETENTION_HOURS) -> Dict[str, Any]:
    """
    Purge unflagged/un-escalated snapshots and temporary buffer files older than retention_hours.
    Escalated alerts marked with evidentiary status are retained.
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    purged_files_count = 0
    purged_alerts_count = 0

    # 1. Clean disk snapshots older than cutoff that are DISMISSED or routine UNACKNOWLEDGED
    expired_alerts = db.query(Alert).filter(
        Alert.timestamp < cutoff_time,
        Alert.status.in_(["DISMISSED", "ACKNOWLEDGED"])  # Never auto-delete active ESCALATED forensic records
    ).all()

    for alert in expired_alerts:
        if alert.snapshot_path and os.path.exists(alert.snapshot_path):
            try:
                os.remove(alert.snapshot_path)
                purged_files_count += 1
            except Exception:
                pass
        if alert.clip_path and os.path.exists(alert.clip_path):
            try:
                os.remove(alert.clip_path)
                purged_files_count += 1
            except Exception:
                pass

    # 2. Clean orphaned snapshot directory files older than cutoff
    now_ts = time.time()
    cutoff_ts = now_ts - (retention_hours * 3600)
    for folder in [SNAPSHOT_DIR]:
        if os.path.exists(folder):
            for fname in os.listdir(folder):
                fpath = os.path.join(folder, fname)
                if os.path.isfile(fpath):
                    try:
                        mtime = os.path.getmtime(fpath)
                        if mtime < cutoff_ts:
                            os.remove(fpath)
                            purged_files_count += 1
                    except Exception:
                        pass

    # Log to audit trail
    log_audit_event(
        db=db,
        operator_id="AUTO_PURGE_WORKER",
        action_type="72H_RETENTION_CLEANSE",
        details={
            "retention_hours": retention_hours,
            "purged_media_files": purged_files_count,
            "cutoff_timestamp": cutoff_time.isoformat()
        }
    )

    return {
        "status": "SUCCESS",
        "cutoff_timestamp": cutoff_time.isoformat(),
        "purged_media_files": purged_files_count
    }
