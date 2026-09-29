"""
Automated Test: Store-and-Forward Edge Sync, SHA-256 Audit Hash Chaining,
and 72-Hour Data Minimisation Purge.
"""

import os
import time
from datetime import datetime, timezone, timedelta
from backend.database.db import SessionLocal, init_db
from backend.database.models import User, AuditLog, SyncQueue, Alert
from backend.core.audit import log_audit_event, verify_audit_chain
from backend.sync.sync_manager import sync_manager
from backend.core.cleaner import purge_expired_records_and_media
from backend.core.auth import create_session_token, verify_session_token
from backend.core.config import SNAPSHOT_DIR


def setup_module():
    init_db()


def test_session_auth_and_roles():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "operator").first()
        token = create_session_token(user)
        assert token is not None
        assert "." in token

        payload = verify_session_token(token)
        assert payload is not None
        assert payload["username"] == "operator"
        assert payload["role"] == "OPERATOR"
        assert payload["badge_number"] == user.badge_number

        # Test invalid token tampering
        bad_token = token[:-5] + "XXXXX"
        assert verify_session_token(bad_token) is None, "Tampered token must be rejected"

        print("[PASS] Operator session auth token and signature validation verified")
    finally:
        db.close()


def test_store_and_forward_offline_sync():
    db = SessionLocal()
    try:
        # 1. Set Edge Link to OFFLINE
        sync_manager.set_link_status(False, operator_id="TEST_RUNNER")
        assert sync_manager.is_link_online is False

        # 2. Queue 3 events during outage
        q1 = sync_manager.queue_event(db, "TEST_ALERT_1", {"alert_id": "T-001"})
        q2 = sync_manager.queue_event(db, "TEST_ALERT_2", {"alert_id": "T-002"})
        q3 = sync_manager.queue_event(db, "TEST_ALERT_3", {"alert_id": "T-003"})

        # Try draining while offline -> must buffer locally
        drain_offline = sync_manager.process_backlog(db)
        assert drain_offline["status"] == "OFFLINE_BUFFERING"
        assert drain_offline["synced_in_batch"] == 0
        assert drain_offline["pending_backlog_count"] >= 3

        # 3. Restore Edge Link to ONLINE
        sync_manager.set_link_status(True, operator_id="TEST_RUNNER")
        assert sync_manager.is_link_online is True

        # Process backlog -> must sync events upstream
        drain_online = sync_manager.process_backlog(db)
        assert drain_online["status"] == "SYNCED"
        assert drain_online["synced_in_batch"] >= 3

        # Check records updated in DB
        db.refresh(q1)
        assert q1.is_synced is True
        assert q1.synced_at is not None

        print("[PASS] Offline-first store-and-forward edge synchronization verified")
    finally:
        db.close()


def test_sha256_audit_hash_chaining_and_tamper_detection():
    db = SessionLocal()
    try:
        # 1. Verify existing chain
        is_valid, count, msg = verify_audit_chain(db)
        assert is_valid is True, f"Initial chain must be valid: {msg}"

        # 2. Append new event
        new_entry = log_audit_event(
            db=db,
            operator_id="DUTY_OFFICER_RAWAT",
            action_type="TEST_ACTION_CHAIN",
            details={"step": "testing_hash_chain"}
        )
        assert new_entry.sha256_hash is not None
        assert len(new_entry.sha256_hash) == 64

        # 3. Verify chain intact
        is_valid2, count2, _ = verify_audit_chain(db)
        assert is_valid2 is True
        assert count2 > count

        # 4. Simulate tampering (e.g. malicious direct database edit)
        original_details = new_entry.details_json
        new_entry.details_json = '{"tampered": true}'
        db.commit()

        # Chain verification must catch the discrepancy!
        is_valid_tampered, _, tamper_msg = verify_audit_chain(db)
        assert is_valid_tampered is False, "Cryptographic audit chain must detect tampering"
        assert "Tamper detected" in tamper_msg or "prev_hash mismatch" in tamper_msg

        # Revert tampering to restore clean state
        new_entry.details_json = original_details
        db.commit()

        is_valid_restored, _, _ = verify_audit_chain(db)
        assert is_valid_restored is True, "Restored chain must validate"

        print("[PASS] SHA-256 hash-chained immutable audit ledger & tamper detection verified")
    finally:
        db.close()


def test_72hour_retention_purge():
    db = SessionLocal()
    try:
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)

        # 1. Create expired snapshot file (>72 hours old)
        old_snap = os.path.join(SNAPSHOT_DIR, "test_old_expired_72h.jpg")
        with open(old_snap, "wb") as f:
            f.write(b"OLD_FRAME_DATA")
        # Backdate mtime to 80 hours ago
        past_ts = time.time() - (80 * 3600)
        os.utime(old_snap, (past_ts, past_ts))

        # 2. Create fresh snapshot file (<72 hours old)
        new_snap = os.path.join(SNAPSHOT_DIR, "test_fresh_recent.jpg")
        with open(new_snap, "wb") as f:
            f.write(b"NEW_FRAME_DATA")

        # 3. Run retention purge (72 hours)
        result = purge_expired_records_and_media(db, retention_hours=72)
        assert result["status"] == "SUCCESS"

        # Check file outcomes
        assert not os.path.exists(old_snap), "Expired file older than 72 hours must be purged"
        assert os.path.exists(new_snap), "Recent file must be preserved"

        # Cleanup
        if os.path.exists(new_snap):
            os.remove(new_snap)

        print("[PASS] 72-hour rolling retention policy auto-purge verified")
    finally:
        db.close()


if __name__ == "__main__":
    setup_module()
    test_session_auth_and_roles()
    test_store_and_forward_offline_sync()
    test_sha256_audit_hash_chaining_and_tamper_detection()
    test_72hour_retention_purge()
    print("\nALL STORE-AND-FORWARD, AUDIT & RETENTION TESTS PASSED!")
