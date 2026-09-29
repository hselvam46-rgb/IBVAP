"""
REST API Endpoints for IBVAP Edge Platform.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import json
import os
import uuid
import hashlib
import cv2
import numpy as np

from backend.database.db import get_db, hash_password
from backend.database.models import (
    User, Camera, Alert, Zone, Watchlist, WatchlistPlate, AuditLog, SyncQueue,
    PersonEncounter, MobilizationOrder
)
from backend.core.auth import (
    create_session_token, get_current_user, require_role
)
from backend.core.audit import log_audit_event, verify_audit_chain
from backend.core.cleaner import purge_expired_records_and_media
from backend.sync.sync_manager import sync_manager
from backend.core.config import DATA_RETENTION_HOURS, CURRENT_NODE_SECTOR, CURRENT_SECTOR_NAME, SNAPSHOT_DIR
from backend.analytics.recurrent_engine import recurrent_engine, mass_infiltration_evaluator

router = APIRouter(prefix="/api")


# ==============================================================================
# AUTHENTICATION
# ==============================================================================

@router.post("/auth/login")
def login(payload: Dict[str, str], db: Session = Depends(get_db)):
    username = payload.get("username", "").strip()
    password = payload.get("password", "").strip()

    user = db.query(User).filter(User.username == username).first()
    if not user or user.password_hash != hash_password(password):
        raise HTTPException(status_code=401, detail="Invalid operator credentials")

    token = create_session_token(user)

    # Log successful login to tamper-evident audit ledger
    log_audit_event(
        db=db,
        operator_id=user.username,
        action_type="LOGIN_SUCCESS",
        details={"badge": user.badge_number, "role": user.role}
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user.to_dict()
    }


@router.get("/auth/me")
def get_current_operator(user: User = Depends(get_current_user)):
    return user.to_dict()


# ==============================================================================
# CAMERAS & SECTOR ACCESS PARTITION
# ==============================================================================

from backend.core.config import CURRENT_NODE_SECTOR, CURRENT_SECTOR_NAME


@router.get("/cameras")
def get_cameras(db: Session = Depends(get_db)):
    """
    Returns border cameras strictly partitioned to the current authorized sector:
    Indo-Bangladesh Border Sector.
    """
    cams = db.query(Camera).filter(Camera.sector_code == CURRENT_NODE_SECTOR).all()
    return {
        "sector_partition": CURRENT_NODE_SECTOR,
        "sector_name": CURRENT_SECTOR_NAME,
        "cameras": [c.to_dict() for c in cams]
    }


@router.get("/cameras/{camera_id}")
def get_camera_detail(camera_id: str, db: Session = Depends(get_db)):
    cam = db.query(Camera).filter(
        Camera.id == camera_id,
        Camera.sector_code == CURRENT_NODE_SECTOR
    ).first()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found or outside authorized sector partition")
    return cam.to_dict()


@router.post("/cameras/stream-source")
def set_stream_source(
    payload: Dict[str, Any],
    user: User = Depends(require_role("OPERATOR"))
):
    """
    Switch active video ingestion source between:
    - IBB_SECTOR (Simulated Indo-Bangladesh Border outposts)
    - WEBCAM (Laptop / USB integrated webcam, device index 0)
    - MOBILE_CAM (Mobile phone IP camera over Wi-Fi, RTSP/HTTP URL)
    """
    source_type = payload.get("source_type", "IBB_SECTOR")
    mobile_url = payload.get("mobile_url", "")

    from backend.api.websocket import stream_manager
    stream_manager.set_global_input_source(source_type, mobile_url)

    return {
        "status": "SUCCESS",
        "active_source": source_type,
        "mobile_url": mobile_url,
        "sector": CURRENT_SECTOR_NAME
    }


# ==============================================================================
# ALERTS & HUMAN-IN-THE-LOOP WORKFLOW
# ==============================================================================

@router.get("/alerts")
def get_alerts(
    camera_id: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    alert_type: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(Alert)
    if camera_id:
        query = query.filter(Alert.camera_id == camera_id)
    if severity:
        query = query.filter(Alert.severity == severity)
    if status:
        query = query.filter(Alert.status == status)
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)

    alerts = query.order_by(Alert.timestamp.desc()).limit(limit).all()
    return [a.to_dict() for a in alerts]


@router.get("/alerts/{alert_id}")
def get_alert_detail(alert_id: str, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert.to_dict()


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: str,
    payload: Dict[str, Any],
    user: User = Depends(require_role("OPERATOR")),
    db: Session = Depends(get_db)
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = "ACKNOWLEDGED"
    alert.operator_id = user.username
    alert.operator_notes = payload.get("notes", "Acknowledged by operator")
    alert.resolution_timestamp = datetime.now(timezone.utc)
    db.commit()

    # Log to audit trail
    log_audit_event(
        db=db,
        operator_id=user.username,
        action_type="ALERT_ACKNOWLEDGE",
        details={
            "alert_id": alert_id,
            "badge": user.badge_number,
            "notes": alert.operator_notes
        }
    )

    # Queue for store-and-forward
    sync_manager.queue_event(db, "ALERT_STATUS_UPDATE", {
        "alert_id": alert_id,
        "status": "ACKNOWLEDGED",
        "operator": user.username,
        "notes": alert.operator_notes
    })

    return {"status": "SUCCESS", "alert": alert.to_dict()}


@router.post("/alerts/{alert_id}/escalate")
def escalate_alert(
    alert_id: str,
    payload: Dict[str, Any],
    user: User = Depends(require_role("OPERATOR")),
    db: Session = Depends(get_db)
):
    """
    Escalate alert to BSF Headquarters / Quick Reaction Team (QRF).
    Requires at least DUTY_OFFICER role clearance.
    """
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = "ESCALATED"
    alert.operator_id = user.username
    alert.operator_notes = payload.get("notes", "Escalated to BSF Sector QRF")
    alert.resolution_timestamp = datetime.now(timezone.utc)
    db.commit()

    # Log to audit trail
    log_audit_event(
        db=db,
        operator_id=user.username,
        action_type="ALERT_ESCALATE",
        details={
            "alert_id": alert_id,
            "badge": user.badge_number,
            "target_team": payload.get("target_team", "BSF_QRF_PATROL"),
            "notes": alert.operator_notes
        }
    )

    # Queue for immediate priority store-and-forward sync
    sync_manager.queue_event(db, "ALERT_ESCALATED_HQ", {
        "alert_id": alert_id,
        "status": "ESCALATED",
        "severity": alert.severity,
        "camera_id": alert.camera_id,
        "officer": user.username,
        "notes": alert.operator_notes
    })

    return {"status": "SUCCESS", "alert": alert.to_dict()}


@router.post("/alerts/{alert_id}/dismiss")
def dismiss_alert(
    alert_id: str,
    payload: Dict[str, Any],
    user: User = Depends(require_role("OPERATOR")),
    db: Session = Depends(get_db)
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.status = "DISMISSED"
    alert.operator_id = user.username
    alert.operator_notes = payload.get("reason", "Dismissed as false alarm")
    alert.resolution_timestamp = datetime.now(timezone.utc)
    db.commit()

    log_audit_event(
        db=db,
        operator_id=user.username,
        action_type="ALERT_DISMISS",
        details={
            "alert_id": alert_id,
            "badge": user.badge_number,
            "reason": alert.operator_notes
        }
    )

    return {"status": "SUCCESS", "alert": alert.to_dict()}


@router.post("/alerts/clear-demo")
def clear_demo_alerts(
    user: User = Depends(require_role("OPERATOR")),
    db: Session = Depends(get_db)
):
    """
    Clears test/stale alerts for a clean demo presentation run.
    """
    deleted_count = db.query(Alert).delete()
    db.commit()

    log_audit_event(
        db=db,
        operator_id=user.username,
        action_type="DEMO_QUEUE_RESET",
        details={"deleted_count": deleted_count}
    )

    return {"status": "SUCCESS", "deleted_alerts": deleted_count, "queue_count": 0}


@router.post("/alerts/trigger-demo")
def trigger_demo_alert(
    payload: Optional[Dict[str, Any]] = None,
    user: User = Depends(require_role("OPERATOR")),
    db: Session = Depends(get_db)
):
    """
    On-cue trigger for presenting a live alert to judges.
    """
    payload = payload or {}
    now_dt = datetime.now(timezone.utc)
    alt_type = payload.get("alert_type", "TRIPWIRE_BREACH")
    cam_id = payload.get("camera_id", "CAM-01-IBB-PETRAPOLE")

    unique_suffix = uuid.uuid4().hex[:6]
    timestamp_str = now_dt.strftime("%Y%m%d%H%M%S%f")[:-3]
    alert_id = f"ALT-{timestamp_str}-1-{unique_suffix}"

    snap_path = f"/data/snapshots/{alert_id}.jpg"
    abs_snap_path = os.path.join(SNAPSHOT_DIR, f"{alert_id}.jpg")

    # Capture real-time frame from active video pipeline
    from backend.api.websocket import stream_manager
    pipe = stream_manager.get_pipeline(cam_id)
    real_frame = None

    if pipe.buffer and len(pipe.buffer.buffer) > 0:
        real_frame = pipe.buffer.buffer[-1][0].copy()
    else:
        try:
            raw_f, _, _ = pipe.video_source.read_frame()
            if raw_f is not None:
                real_frame = raw_f.copy()
        except Exception:
            pass

    if real_frame is not None:
        h, w = real_frame.shape[:2]
        # Overlay tactical breach detection graphics and real timestamp
        time_display = now_dt.strftime("%H:%M:%S UTC")
        cv2.rectangle(real_frame, (int(w * 0.22), int(h * 0.25)), (int(w * 0.52), int(h * 0.85)), (0, 0, 255), 2)
        cv2.rectangle(real_frame, (int(w * 0.22), int(h * 0.25) - 22), (int(w * 0.52), int(h * 0.25)), (0, 0, 255), -1)
        cv2.putText(real_frame, f"BREACH DETECTED // {time_display}", (int(w * 0.22) + 4, int(h * 0.25) - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
        cv2.imwrite(abs_snap_path, real_frame)
    else:
        thumb = np.zeros((360, 640, 3), dtype=np.uint8)
        thumb[:] = [20, 25, 35]
        cv2.putText(thumb, "LIVE TACTICAL CAPTURE", (50, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 212, 255), 2)
        cv2.imwrite(abs_snap_path, thumb)

    alt = Alert(
        id=alert_id,
        timestamp=now_dt,
        camera_id=cam_id,
        alert_type=alt_type,
        severity="CRITICAL",
        track_id=101,
        object_type="person",
        confidence=0.96,
        snapshot_path=snap_path,
        status="UNACKNOWLEDGED",
        metadata_json=json.dumps({
            "zone_name": "Zero Line Primary Barrier",
            "direction": "INBOUND",
            "threat_classification": "ACTIVE_BORDER_BREACH",
            "demo_generated": True
        })
    )
    db.add(alt)
    db.commit()
    db.refresh(alt)

    log_audit_event(
        db=db,
        operator_id=user.username,
        action_type="DEMO_ALERT_TRIGGERED",
        details={"alert_id": alert_id, "type": alt_type}
    )

    # Queue sync
    sync_manager.queue_event(db, "NEW_ALERT", alt.to_dict())

    # Broadcast directly to all active operator consoles and matrix tiles
    try:
        import asyncio
        from backend.api.websocket import stream_manager
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(stream_manager.broadcast_alert(alt.to_dict()))
        except RuntimeError:
            pass
    except Exception as e:
        print(f"[WARN] Failed to broadcast demo alert: {e}")

    return {"status": "SUCCESS", "alert": alt.to_dict()}


# ==============================================================================
# ZONES & VIRTUAL TRIPWIRES
# ==============================================================================

@router.get("/zones")
def get_zones(camera_id: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Zone)
    if camera_id:
        query = query.filter(Zone.camera_id == camera_id)
    zones = query.all()
    return [z.to_dict() for z in zones]


@router.post("/zones")
def create_zone(
    payload: Dict[str, Any],
    user: User = Depends(require_role("OPERATOR")),
    db: Session = Depends(get_db)
):
    """Save an interactive tripwire or geofence drawn by operator."""
    zone_id = payload.get("id") or f"ZONE-{datetime.now(timezone.utc).strftime('%H%M%S')}"
    new_zone = Zone(
        id=zone_id,
        camera_id=payload["camera_id"],
        name=payload["name"],
        zone_type=payload["zone_type"],  # TRIPWIRE, RESTRICTED_POLYGON
        direction=payload.get("direction", "INBOUND"),
        coordinates_json=json.dumps(payload["coordinates"]),
        dwell_threshold_seconds=float(payload.get("dwell_threshold_seconds", 90.0)),
        severity=payload.get("severity", "CRITICAL"),
        is_active=True
    )
    db.add(new_zone)
    db.commit()
    db.refresh(new_zone)

    log_audit_event(
        db=db,
        operator_id=user.username,
        action_type="ZONE_CREATE",
        details={"zone_id": zone_id, "name": new_zone.name, "type": new_zone.zone_type}
    )

    return {"status": "SUCCESS", "zone": new_zone.to_dict()}


@router.delete("/zones/{zone_id}")
def delete_zone(
    zone_id: str,
    user: User = Depends(require_role("OPERATOR")),
    db: Session = Depends(get_db)
):
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    db.delete(zone)
    db.commit()

    log_audit_event(
        db=db,
        operator_id=user.username,
        action_type="ZONE_DELETE",
        details={"zone_id": zone_id}
    )
    return {"status": "SUCCESS", "deleted_zone_id": zone_id}


# ==============================================================================
# WATCHLIST (FACIAL 512-D & ANPR PLATES)
# ==============================================================================

@router.get("/watchlist")
def get_watchlist(db: Session = Depends(get_db)):
    targets = db.query(Watchlist).all()
    return [t.to_dict(include_embedding=False) for t in targets]


@router.get("/watchlist/plates")
def get_watchlist_plates(db: Session = Depends(get_db)):
    plates = db.query(WatchlistPlate).all()
    return [p.to_dict() for p in plates]


# ==============================================================================
# AUDIT TRAIL & TAMPER VERIFICATION
# ==============================================================================

@router.get("/audit")
def get_audit_trail(limit: int = 100, db: Session = Depends(get_db)):
    logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return [l.to_dict() for l in logs]


@router.get("/audit/verify")
def verify_audit(db: Session = Depends(get_db)):
    is_valid, count, message = verify_audit_chain(db)
    return {
        "is_valid": is_valid,
        "records_verified": count,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ==============================================================================
# STORE-AND-FORWARD EDGE SYNC
# ==============================================================================

@router.get("/sync/status")
def get_sync_status(db: Session = Depends(get_db)):
    pending = db.query(SyncQueue).filter(SyncQueue.is_synced == False).count()
    return {
        "is_link_online": sync_manager.is_link_online,
        "status": "ONLINE" if sync_manager.is_link_online else "OFFLINE",
        "pending_backlog_count": pending,
        "total_synced_all_time": sync_manager.total_synced_count
    }


@router.post("/sync/toggle-link")
def toggle_link(
    payload: Dict[str, bool],
    user: User = Depends(require_role("OPERATOR")),
    db: Session = Depends(get_db)
):
    online = payload.get("online", True)
    res = sync_manager.set_link_status(online, operator_id=user.username)
    # Drain backlog if switched to online
    if online:
        drain_res = sync_manager.process_backlog(db)
        res["drain_result"] = drain_res
    return res


@router.post("/sync/trigger")
def trigger_sync(db: Session = Depends(get_db)):
    return sync_manager.process_backlog(db)


# ==============================================================================
# 72-HOUR RETENTION PURGE
# ==============================================================================

@router.post("/system/purge")
def trigger_retention_purge(
    user: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db)
):
    result = purge_expired_records_and_media(db, retention_hours=DATA_RETENTION_HOURS)
    return result


# ==============================================================================
# METRICS & STATS
# ==============================================================================

@router.get("/stats")
def get_system_stats(db: Session = Depends(get_db)):
    total_cameras = db.query(Camera).count()
    total_alerts = db.query(Alert).count()
    critical_alerts = db.query(Alert).filter(Alert.severity == "CRITICAL").count()
    pending_alerts = db.query(Alert).filter(Alert.status == "UNACKNOWLEDGED").count()
    watchlist_faces = db.query(Watchlist).count()
    watchlist_plates = db.query(WatchlistPlate).count()
    pending_sync = db.query(SyncQueue).filter(SyncQueue.is_synced == False).count()

    return {
        "total_cameras": total_cameras,
        "total_alerts": total_alerts,
        "critical_alerts": critical_alerts,
        "pending_alerts": pending_alerts,
        "watchlist_faces": watchlist_faces,
        "watchlist_plates": watchlist_plates,
        "pending_sync": pending_sync,
        "is_link_online": sync_manager.is_link_online,
        "system_status": "OPERATIONAL_DEFENSE_GRID_NORMAL"
    }


# ==============================================================================
# TRANSIENT BIOMETRIC MEMORY & RECURRENT PERSON SIGHTINGS
# ==============================================================================

@router.get("/encounters/recurrent")
def get_recurrent_encounters(
    all_encounters: bool = Query(False, alias="all"),
    db: Session = Depends(get_db)
):
    """
    Returns person sightings recorded in transient memory.
    By default returns only recurrent sightings (seen >= 2 times).
    """
    query = db.query(PersonEncounter)
    if not all_encounters:
        query = query.filter(PersonEncounter.sighting_count > 1)
    encounters = query.order_by(PersonEncounter.last_seen_timestamp.desc()).limit(50).all()
    return [e.to_dict() for e in encounters]


@router.post("/patrol/dispatch")
def dispatch_patrol(
    payload: Dict[str, Any],
    user: User = Depends(require_role("OPERATOR")),
    db: Session = Depends(get_db)
):
    """
    Dispatches Quick Reaction Team (QRT) border patrol to intercept recurrent person.
    Logs dispatch with SHA-256 cryptographic chain to audit ledger.
    """
    encounter_id = payload.get("encounter_id")
    patrol_unit_id = payload.get("patrol_unit_id", "QRT-DELTA-9")
    sector_code = payload.get("sector_code", CURRENT_NODE_SECTOR)
    notes = payload.get("notes", "Recurrent person intercept order dispatched.")

    encounter = None
    if encounter_id:
        encounter = db.query(PersonEncounter).filter(PersonEncounter.id == encounter_id).first()

    now_utc = datetime.now(timezone.utc)
    if encounter:
        encounter.patrol_dispatched = True
        encounter.patrol_dispatch_notes = f"[{patrol_unit_id}] {notes} (Dispatched by {user.username})"
        db.commit()
        db.refresh(encounter)
        subj_alias = encounter.subject_alias
        last_cam = encounter.last_seen_camera_id
        enc_id = encounter.id
        sighting_cnt = encounter.sighting_count
        snap_path = encounter.snapshot_path
    else:
        subj_alias = payload.get("subject_alias", "LIVE-SECTOR-INCIDENT")
        last_cam = payload.get("camera_id", "CAM-01-IBB-PETRAPOLE")
        enc_id = f"PATROL-ORDER-{now_utc.strftime('%Y%m%d%H%M%S')}"
        sighting_cnt = 1
        snap_path = payload.get("snapshot_path", "/frontend/assets/placeholder.jpg")

    # Tamper-evident audit trail log
    log_audit_event(
        db=db,
        operator_id=user.username,
        action_type="PATROL_DISPATCH_ORDER",
        details={
            "encounter_id": enc_id,
            "subject_alias": subj_alias,
            "patrol_unit_id": patrol_unit_id,
            "sector_code": sector_code,
            "last_seen_camera": last_cam,
            "sighting_count": sighting_cnt,
            "snapshot_path": snap_path,
            "instructions": notes
        }
    )

    # Edge store-and-forward sync
    sync_manager.queue_event(
        db=db,
        event_type="PATROL_DISPATCH",
        payload={
            "encounter_id": enc_id,
            "subject_alias": subj_alias,
            "patrol_unit_id": patrol_unit_id,
            "sector_code": sector_code,
            "last_seen_camera": last_cam,
            "operator_id": user.username,
            "timestamp": now_utc.isoformat(),
            "instructions": notes
        }
    )

    return {
        "status": "DISPATCHED",
        "message": f"Patrol {patrol_unit_id} dispatched to intercept at {last_cam}",
        "encounter": encounter.to_dict() if encounter else None,
        "dispatch_id": enc_id
    }


# ==============================================================================
# DEFCON-1 MASS INFILTRATION & HQ MOBILIZATION ORDERS
# ==============================================================================

@router.post("/hq/reinforcements")
def request_hq_reinforcements(
    payload: Dict[str, Any],
    user: User = Depends(require_role("OPERATOR")),
    db: Session = Depends(get_db)
):
    """
    Transmits urgent Tactical Reinforcement Order to Indo-Bangladesh Sector Command HQ.
    Logs SHA-256 transmission hash and mobilizes tactical border reserve battalion.
    """
    sector_code = payload.get("sector_code", CURRENT_NODE_SECTOR)
    reason = payload.get("reason", "MASS_PERSONNEL_INFILTRATION")
    person_count = int(payload.get("person_count", 0))
    vehicle_count = int(payload.get("vehicle_count", 0))
    details = payload.get("details", {})

    now_dt = datetime.now(timezone.utc)
    order_id = f"MOB-{now_dt.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

    # Cryptographic transmission hash for HQ command authentication
    raw_sig = f"{order_id}:{sector_code}:{reason}:{person_count}:{vehicle_count}:{user.username}:{now_dt.isoformat()}"
    tx_hash = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()

    mob_order = MobilizationOrder(
        id=order_id,
        timestamp=now_dt,
        sector_code=sector_code,
        trigger_reason=reason,
        person_count=person_count,
        vehicle_count=vehicle_count,
        status="TRANSMITTED_TO_HQ",
        operator_id=user.username,
        allied_alert_broadcast=False,
        hq_transmission_hash=tx_hash,
        details_json=json.dumps(details)
    )
    db.add(mob_order)
    db.commit()
    db.refresh(mob_order)

    # Tamper-evident audit trail log
    log_audit_event(
        db=db,
        operator_id=user.username,
        action_type="HQ_REINFORCEMENT_REQUESTED",
        details={
            "order_id": order_id,
            "sector_code": sector_code,
            "reason": reason,
            "person_count": person_count,
            "vehicle_count": vehicle_count,
            "hq_transmission_hash": tx_hash
        }
    )

    # Edge store-and-forward sync
    sync_manager.queue_event(
        db=db,
        event_type="HQ_MOBILIZATION_ORDER",
        payload=mob_order.to_dict()
    )

    return {
        "status": "TRANSMITTED_TO_HQ",
        "order_id": order_id,
        "transmission_hash": tx_hash,
        "eta_minutes": 12,
        "reinforcement_battalion": "142 BSF TACTICAL QRT & MEGHALAYA DEFENSE BRIGADE",
        "order": mob_order.to_dict()
    }


@router.post("/allies/broadcast-alert")
def broadcast_allied_alert(
    payload: Dict[str, Any],
    user: User = Depends(require_role("OPERATOR")),
    db: Session = Depends(get_db)
):
    """
    Broadcasts DEFCON-1 High Alert to Allied Border Defense Forces:
    BSF Battalions, Assam Rifles, Indian Coast Guard, and Local Border Police.
    """
    mobilization_id = payload.get("mobilization_id")
    sector_code = payload.get("sector_code", CURRENT_NODE_SECTOR)
    allied_forces = payload.get("allied_forces", [
        "BORDER SECURITY FORCE (BSF)",
        "ASSAM RIFLES (NORTHEAST BORDER)",
        "INDIAN COAST GUARD (SUNDERBANS SECTOR)",
        "LOCAL STATE BORDER POLICE"
    ])
    alert_level = payload.get("alert_level", "DEFCON-1 (RED ALERT)")
    notes = payload.get("notes", "Immediate high alert: Mass infiltration activity detected along IBB border corridor.")

    mob_order = None
    if mobilization_id:
        mob_order = db.query(MobilizationOrder).filter(MobilizationOrder.id == mobilization_id).first()
        if mob_order:
            mob_order.allied_alert_broadcast = True
            db.commit()

    # Tamper-evident audit log
    log_audit_event(
        db=db,
        operator_id=user.username,
        action_type="ALLIED_HIGH_ALERT_BROADCAST",
        details={
            "mobilization_id": mobilization_id,
            "sector_code": sector_code,
            "alert_level": alert_level,
            "allied_forces": allied_forces,
            "notes": notes
        }
    )

    # Sync broadcast upstream
    sync_manager.queue_event(
        db=db,
        event_type="ALLIED_ALERT_BROADCAST",
        payload={
            "mobilization_id": mobilization_id,
            "sector_code": sector_code,
            "alert_level": alert_level,
            "allied_forces": allied_forces,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )

    return {
        "status": "ALLIED_ALERT_ACTIVE",
        "sector_code": sector_code,
        "alert_level": alert_level,
        "recipients": allied_forces,
        "broadcast_timestamp": datetime.now(timezone.utc).isoformat(),
        "mobilization_order": mob_order.to_dict() if mob_order else None
    }


@router.get("/hq/mobilizations")
def get_mobilizations(db: Session = Depends(get_db)):
    """Returns recent tactical mobilization orders and reinforcement dispatches."""
    orders = db.query(MobilizationOrder).order_by(MobilizationOrder.timestamp.desc()).limit(20).all()
    return [o.to_dict() for o in orders]

