"""
Offline-First Edge Operation & Store-and-Forward Sync Manager.
Buffers event telemetry locally when the tactical network link drops,
and automatically syncs backlog upstream when link heartbeat restores.
"""

import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from backend.database.models import SyncQueue, Alert
from backend.database.db import SessionLocal
from backend.core.audit import log_audit_event


class EdgeSyncManager:
    def __init__(self):
        self.is_link_online: bool = True
        self.sync_in_progress: bool = False
        self.total_synced_count: int = 0

    def set_link_status(self, online: bool, operator_id: str = "OPERATOR") -> Dict[str, Any]:
        """Manually or automatically toggle network link status."""
        prev = self.is_link_online
        self.is_link_online = online

        db = SessionLocal()
        try:
            log_audit_event(
                db=db,
                operator_id=operator_id,
                action_type="LINK_STATUS_CHANGE",
                details={
                    "previous_status": "ONLINE" if prev else "OFFLINE",
                    "new_status": "ONLINE" if online else "OFFLINE"
                }
            )
        finally:
            db.close()

        return {
            "is_link_online": self.is_link_online,
            "status": "ONLINE" if self.is_link_online else "OFFLINE"
        }

    def queue_event(self, db: Session, event_type: str, payload: Dict[str, Any]) -> SyncQueue:
        """Enqueue structured metadata event for store-and-forward."""
        item = SyncQueue(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            payload_json=json.dumps(payload),
            is_synced=False
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def process_backlog(self, db: Session, batch_size: int = 100) -> Dict[str, Any]:
        """
        Drain unsynced backlog if link is online.
        In an offline state, preserves events locally.
        """
        if not self.is_link_online:
            pending_count = db.query(SyncQueue).filter(SyncQueue.is_synced == False).count()
            return {
                "status": "OFFLINE_BUFFERING",
                "is_link_online": False,
                "pending_backlog_count": pending_count,
                "synced_in_batch": 0
            }

        # Fetch unsynced items
        pending_items = db.query(SyncQueue).filter(SyncQueue.is_synced == False).limit(batch_size).all()
        if not pending_items:
            return {
                "status": "IDLE",
                "is_link_online": True,
                "pending_backlog_count": 0,
                "synced_in_batch": 0
            }

        synced_ids = []
        for item in pending_items:
            # Simulate bandwidth-conscious upstream sync transmission (compact JSON metadata)
            item.is_synced = True
            item.synced_at = datetime.now(timezone.utc)
            synced_ids.append(item.id)

            # If it's an alert sync, update alert status as well
            try:
                p = json.loads(item.payload_json)
                if "alert_id" in p:
                    alt = db.query(Alert).filter(Alert.id == p["alert_id"]).first()
                    if alt:
                        alt.synced_upstream = True
            except Exception:
                pass

        db.commit()
        self.total_synced_count += len(synced_ids)

        remaining_count = db.query(SyncQueue).filter(SyncQueue.is_synced == False).count()
        return {
            "status": "SYNCED",
            "is_link_online": True,
            "synced_in_batch": len(synced_ids),
            "pending_backlog_count": remaining_count,
            "total_synced_all_time": self.total_synced_count
        }


# Global Singleton Sync Manager instance
sync_manager = EdgeSyncManager()
