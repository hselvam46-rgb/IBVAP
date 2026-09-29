"""
Real-Time Low-Latency WebSocket Streamer (<1.2s target).
Orchestrates frame capture, YOLOv8 detection, ByteTrack tracking,
spatial geofencing, facial recognition, ANPR, and alert broadcasting.
"""

import asyncio
import base64
import json
import os
import time
import cv2
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any, List, Set, Optional, Tuple, Union
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.database.db import SessionLocal
from backend.database.models import Camera, Zone, Alert, Watchlist, WatchlistPlate
from backend.stream.video_source import BorderVideoSource
from backend.stream.buffer_manager import CircularFrameBuffer
from backend.analytics.detector import YOLOv8Detector
from backend.analytics.tracker import ByteTracker
from backend.analytics.face_engine import FaceEngine
from backend.analytics.anpr_engine import ANPREngine
from backend.analytics.spatial_engine import SpatialEngine
from backend.analytics.loitering_engine import LoiteringEngine
from backend.analytics.thermal_engine import ThermalEngine
from backend.analytics.filter_engine import FalseAlarmFilter
from backend.analytics.recurrent_engine import recurrent_engine, mass_infiltration_evaluator
from backend.sync.sync_manager import sync_manager
from backend.core.config import SNAPSHOT_DIR

ws_router = APIRouter()


class StreamPipeline:
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.video_source = BorderVideoSource(camera_id)
        self.buffer = CircularFrameBuffer(camera_id, max_frames=150)
        self.detector = YOLOv8Detector()
        self.tracker = ByteTracker(track_thresh=0.45)
        self.face_engine = FaceEngine(match_threshold=0.72)
        self.anpr_engine = ANPREngine()
        self.spatial_engine = SpatialEngine()
        self.loitering_engine = LoiteringEngine(default_threshold_seconds=90.0)
        self.thermal_engine = ThermalEngine()
        self.filter_engine = FalseAlarmFilter()

        self.thermal_mode = "OPTICAL"
        self.alert_cooldowns: Dict[str, float] = {}
        self._reload_db_state()

    def can_trigger_alert(self, track_id: int, alert_type: str, cooldown_seconds: float = 8.0) -> bool:
        now = time.time()
        key = f"{track_id}:{alert_type}"
        last_t = self.alert_cooldowns.get(key, 0.0)
        if now - last_t >= cooldown_seconds:
            self.alert_cooldowns[key] = now
            return True
        return False

    def _reload_db_state(self):
        db = SessionLocal()
        try:
            cam = db.query(Camera).filter(Camera.id == self.camera_id).first()
            if cam:
                self.thermal_mode = cam.source_type
            watchlist_items = db.query(Watchlist).all()
            self.face_engine.load_watchlist(watchlist_items)
            self.hotlist_plates = db.query(WatchlistPlate).all()
        finally:
            db.close()


class StreamManager:
    def __init__(self):
        self.pipelines: Dict[str, StreamPipeline] = {}
        self.active_connections: Set[WebSocket] = set()
        self.current_source_mode = "SECTOR"  # SECTOR, WEBCAM, MOBILE_CAM
        self.current_mobile_url = ""

    def get_pipeline(self, camera_id: str) -> StreamPipeline:
        if camera_id not in self.pipelines:
            pipe = StreamPipeline(camera_id)
            pipe.video_source.set_input_mode(self.current_source_mode, self.current_mobile_url)
            self.pipelines[camera_id] = pipe
        return self.pipelines[camera_id]

    def set_global_input_source(self, mode: str, mobile_url: str = ""):
        self.current_source_mode = mode
        self.current_mobile_url = mobile_url
        for pipe in self.pipelines.values():
            pipe.video_source.set_input_mode(mode, mobile_url)

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast_alert(self, alert_dict: Dict[str, Any]):
        """Broadcast new alert to all connected operator consoles."""
        payload = json.dumps({"type": "NEW_ALERT", "data": alert_dict})
        for conn in list(self.active_connections):
            try:
                await conn.send_text(payload)
            except Exception:
                pass

    async def broadcast_custom_event(self, event_dict: Dict[str, Any]):
        """Broadcast custom structured telemetry/notification to consoles."""
        payload = json.dumps(event_dict)
        for conn in list(self.active_connections):
            try:
                await conn.send_text(payload)
            except Exception:
                pass


stream_manager = StreamManager()


@ws_router.websocket("/ws/stream")
async def websocket_video_stream(websocket: WebSocket):
    await stream_manager.connect(websocket)
    query_cam = websocket.query_params.get("camera_id")
    is_grid = websocket.query_params.get("grid") in ("true", "1")
    selected_camera_id = query_cam or "CAM-01-IBB-PETRAPOLE"
    thermal_override = None

    db = SessionLocal()
    pipeline = stream_manager.get_pipeline(selected_camera_id)

    try:
        while True:
            t0 = time.time()

            # Check if any incoming command from operator console
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.001)
                data = json.loads(msg)
                cmd = data.get("command")
                if cmd == "SWITCH_CAMERA":
                    selected_camera_id = data.get("camera_id", selected_camera_id)
                    pipeline = stream_manager.get_pipeline(selected_camera_id)
                elif cmd == "SWITCH_SOURCE_MODE":
                    mode = data.get("mode", "SECTOR")
                    mobile_url = data.get("mobile_url", "")
                    stream_manager.set_global_input_source(mode, mobile_url)
                elif cmd == "SET_THERMAL_MODE":
                    thermal_override = data.get("mode", "OPTICAL")
                elif cmd == "TRIGGER_EVIDENCE":
                    evidence_res = pipeline.buffer.export_evidence_package(
                        alert_id=data.get("alert_id", "LIVE_CAPTURE"),
                        operator_id=data.get("operator_id", "OPERATOR"),
                        notes=data.get("notes", "Manual 1-click evidence capture")
                    )
                    await websocket.send_text(json.dumps({"type": "EVIDENCE_EXPORTED", "data": evidence_res}))
            except asyncio.TimeoutError:
                pass

            # 1. Read Frame from Border Video Source
            raw_frame, detections, sim_targets = pipeline.video_source.read_frame()
            pipeline.buffer.add_frame(raw_frame, t0)

            # 2. Apply Thermal Mode Processing if enabled
            active_mode = thermal_override or pipeline.thermal_mode
            display_frame = pipeline.thermal_engine.apply_thermal_processing(raw_frame, mode=active_mode)

            # 3. Multi-Object Tracking (ByteTrack)
            tracks = pipeline.tracker.update(detections, dt=0.033)
            active_track_ids = [t.track_id for t in tracks]
            pipeline.spatial_engine.cleanup_lost_tracks(active_track_ids)
            pipeline.loitering_engine.cleanup_inactive_tracks(active_track_ids)

            # 4. Fetch Active Zones for this Camera
            zones = db.query(Zone).filter(Zone.camera_id == selected_camera_id, Zone.is_active == True).all()

            frame_alerts = []

            # 5. Evaluate Spatial & Threat Engines per Track
            for track in tracks:
                # A. False Alarm / Vegetation filter
                severity, should_alert = pipeline.filter_engine.categorize_threat_level(track)

                # B. Virtual Tripwires & Geofences
                for zone in zones:
                    zone_coords = zone.get_coordinates()

                    if zone.zone_type == "TRIPWIRE":
                        breached, direction = pipeline.spatial_engine.check_tripwire(
                            zone_id=zone.id,
                            zone_coords=zone_coords,
                            direction_rule=zone.direction,
                            track_id=track.track_id,
                            trail=track.trail
                        )
                        if breached and should_alert and pipeline.can_trigger_alert(track.track_id, "TRIPWIRE_BREACH"):
                            alt = _create_alert(
                                db=db,
                                camera_id=selected_camera_id,
                                alert_type="TRIPWIRE_BREACH",
                                severity=zone.severity,
                                track_id=track.track_id,
                                obj_type=track.class_name,
                                confidence=track.confidence,
                                metadata={
                                    "zone_name": zone.name,
                                    "direction": direction,
                                    "zone_id": zone.id
                                },
                                frame=display_frame
                            )
                            if alt is not None:
                                frame_alerts.append(alt)

                    elif zone.zone_type == "RESTRICTED_POLYGON":
                        target_base = (track.centroid[0], track.bbox[3])
                        is_inside = pipeline.spatial_engine.is_inside_polygon(zone_coords, target_base)

                        # Dwell time tracking (90s default threshold)
                        loiter_alarm, dwell_sec, inside = pipeline.loitering_engine.update_dwell(
                            zone_id=zone.id,
                            track_id=track.track_id,
                            is_inside=is_inside,
                            threshold_seconds=zone.dwell_threshold_seconds
                        )

                        if loiter_alarm and should_alert and pipeline.can_trigger_alert(track.track_id, "LOITERING_DWELL"):
                            alt = _create_alert(
                                db=db,
                                camera_id=selected_camera_id,
                                alert_type="LOITERING_DWELL",
                                severity="CRITICAL",
                                track_id=track.track_id,
                                obj_type=track.class_name,
                                confidence=track.confidence,
                                metadata={
                                    "zone_name": zone.name,
                                    "dwell_seconds": round(dwell_sec, 1),
                                    "threshold_seconds": zone.dwell_threshold_seconds
                                },
                                frame=display_frame
                            )
                            if alt is not None:
                                frame_alerts.append(alt)

                # C. Facial Recognition against Local Watchlist (for persons)
                if track.class_name == "person":
                    # CRITICAL ETHICAL & PRIVACY GUARD:
                    # Real live webcam / mobile camera faces MUST NEVER be matched against watchlist profiles.
                    # Watchlist alerts are strictly restricted to synthetic demo targets with defined target_hints.
                    is_live_camera = (pipeline.video_source.source_mode in ("WEBCAM", "MOBILE_CAM"))

                    target_hint = None
                    if not is_live_camera:
                        for st in sim_targets:
                            if abs(st.x - track.centroid[0]) < 0.1 and abs(st.y - track.centroid[1]) < 0.1:
                                target_hint = st.seed_hint
                                break

                    matched, score, target_data, face_crop, probe_emb = pipeline.face_engine.match_probe(
                        frame=raw_frame,
                        person_bbox=track.bbox,
                        seed_hint=target_hint
                    )

                    # Only trigger watchlist alert on synthetic scenario targets, never on real webcam faces
                    if not is_live_camera and target_hint and matched and target_data and pipeline.can_trigger_alert(track.track_id, "WATCHLIST_FACE_MATCH"):
                        # Matched probe embedding is retained for operator review (Data Minimisation compliance)
                        alt = _create_alert(
                            db=db,
                            camera_id=selected_camera_id,
                            alert_type="WATCHLIST_FACE_MATCH",
                            severity="CRITICAL",
                            track_id=track.track_id,
                            obj_type="person",
                            confidence=score,
                            metadata={
                                "subject_id": target_data["subject_id"],
                                "target_name": target_data["name"],
                                "alias": target_data.get("alias"),
                                "threat_level": target_data["threat_level"],
                                "similarity_score": round(score * 100, 1),
                                "reference_photo": target_data.get("reference_photo"),
                                "probe_embedding_512d": probe_emb[:8] if probe_emb else []
                            },
                            frame=display_frame
                        )
                        if alt is not None:
                            frame_alerts.append(alt)

                    # Transient Biometric Memory: Recurrent Person Recognition
                    try:
                        is_rec, enc, rec_sim, time_delta, is_cross = recurrent_engine.process_person_sighting(
                            db=db,
                            frame=raw_frame,
                            person_bbox=track.bbox,
                            camera_id=selected_camera_id,
                            probe_emb=probe_emb
                        )
                        if is_rec and pipeline.can_trigger_alert(track.track_id, "RECURRENT_PERSON_SIGHTING", cooldown_seconds=15.0):
                            alt_rec = _create_alert(
                                db=db,
                                camera_id=selected_camera_id,
                                alert_type="RECURRENT_PERSON_SIGHTING",
                                severity="HIGH" if is_cross else "WARNING",
                                track_id=track.track_id,
                                obj_type="person",
                                confidence=rec_sim / 100.0,
                                metadata={
                                    "encounter_id": enc.id,
                                    "subject_alias": enc.subject_alias,
                                    "sighting_count": enc.sighting_count,
                                    "first_seen_camera": enc.first_seen_camera_id,
                                    "first_seen_timestamp": enc.first_seen_timestamp.isoformat() if enc.first_seen_timestamp else None,
                                    "last_seen_camera": enc.last_seen_camera_id,
                                    "last_seen_timestamp": enc.last_seen_timestamp.isoformat() if enc.last_seen_timestamp else None,
                                    "time_delta_seconds": time_delta,
                                    "is_cross_post": is_cross,
                                    "similarity_percent": rec_sim,
                                    "snapshot_path": enc.snapshot_path,
                                    "patrol_dispatched": enc.patrol_dispatched,
                                },
                                frame=display_frame
                            )
                            if alt_rec is not None:
                                frame_alerts.append(alt_rec)
                                await stream_manager.broadcast_custom_event({
                                    "type": "RECURRENT_PERSON_SIGHTING",
                                    "data": {
                                        "encounter": enc.to_dict(),
                                        "similarity_score": rec_sim,
                                        "is_cross_post": is_cross,
                                        "alert": alt_rec.to_dict()
                                    }
                                })
                    except Exception:
                        pass

                # D. ANPR on Vehicles
                if track.is_vehicle:
                    plate_hint = None
                    for st in sim_targets:
                        if abs(st.x - track.centroid[0]) < 0.2 and abs(st.y - track.centroid[1]) < 0.2:
                            plate_hint = st.plate_hint
                            break

                    plate_res = pipeline.anpr_engine.read_plate(display_frame, simulated_plate_hint=plate_hint)
                    if plate_res["raw_text"]:
                        is_hot, hot_info = pipeline.anpr_engine.check_hotlist(
                            plate_res["raw_text"],
                            pipeline.hotlist_plates
                        )
                        if is_hot and pipeline.can_trigger_alert(track.track_id, "ANPR_FLAGGED_VEHICLE"):
                            alt = _create_alert(
                                db=db,
                                camera_id=selected_camera_id,
                                alert_type="ANPR_FLAGGED_VEHICLE",
                                severity="CRITICAL",
                                track_id=track.track_id,
                                obj_type=track.class_name,
                                confidence=plate_res["confidence"],
                                metadata={
                                    "plate_number": plate_res["raw_text"],
                                    "format_type": plate_res["format_type"],
                                    "ocr_engine": plate_res["ocr_engine"],
                                    "hotlist_reason": hot_info["remarks"] if hot_info else "Hotlist match"
                                },
                                frame=display_frame
                            )
                            if alt is not None:
                                frame_alerts.append(alt)

            # 5.B Evaluate Mass Infiltration & Convoy Incursions (DEFCON-1)
            mass_threat = mass_infiltration_evaluator.evaluate(tracks, cooldown_seconds=30.0)
            if mass_threat["is_mass_threat"] and mass_threat.get("should_broadcast", False):
                alt_mass = _create_alert(
                    db=db,
                    camera_id=selected_camera_id,
                    alert_type=mass_threat["reason"],
                    severity="CRITICAL",
                    track_id=9999,
                    obj_type="convoy" if "CONVOY" in mass_threat["reason"] else "infiltrators",
                    confidence=0.99,
                    metadata={
                        "person_count": mass_threat["person_count"],
                        "vehicle_count": mass_threat["vehicle_count"],
                        "defcon_level": mass_threat["defcon_level"],
                        "message": mass_threat["message"],
                        "recommended_action": mass_threat["recommended_action"]
                    },
                    frame=display_frame
                )
                if alt_mass is not None:
                    frame_alerts.append(alt_mass)

                await stream_manager.broadcast_custom_event({
                    "type": "MASS_INFILTRATION_ALERT",
                    "data": mass_threat
                })

            # Broadcast any newly generated alerts immediately
            for alt in frame_alerts:
                await stream_manager.broadcast_alert(alt.to_dict())

            # 6. Encode video frame to JPEG for low-latency browser rendering
            _, buffer = cv2.imencode(".jpg", display_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frame_b64 = base64.b64encode(buffer).decode("utf-8")

            # Calculate end-to-end processing latency
            latency_ms = round((time.time() - t0) * 1000, 1)

            # 7. Construct Telemetry Packet
            telemetry = {
                "type": "FRAME_UPDATE",
                "camera_id": selected_camera_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "latency_ms": latency_ms,
                "thermal_mode": active_mode,
                "frame": frame_b64,
                "tracks": [t.to_dict() for t in tracks],
                "zones": [z.to_dict() for z in zones],
                "mass_status": {
                    "is_threat": mass_threat["is_mass_threat"],
                    "person_count": mass_threat["person_count"],
                    "vehicle_count": mass_threat["vehicle_count"],
                    "defcon_level": mass_threat["defcon_level"],
                    "message": mass_threat.get("message", "")
                }
            }

            await websocket.send_text(json.dumps(telemetry))

            # Maintain target streaming rate (~25-30 FPS for single focus, ~12-15 FPS for grid tiles)
            target_interval = 0.075 if is_grid else 0.035
            elapsed = time.time() - t0
            sleep_time = max(0.005, target_interval - elapsed)
            await asyncio.sleep(sleep_time)

    except WebSocketDisconnect:
        stream_manager.disconnect(websocket)
    except Exception as e:
        import traceback
        traceback.print_exc()
        stream_manager.disconnect(websocket)
    finally:
        db.close()


def _create_alert(
    db, camera_id: str, alert_type: str, severity: str, track_id: int,
    obj_type: str, confidence: float, metadata: Dict[str, Any], frame: np.ndarray
) -> Optional[Alert]:
    """Save alert to local database, write snapshot, and enqueue for edge sync."""
    import uuid
    # Use microseconds and uuid to guarantee global uniqueness
    unique_suffix = uuid.uuid4().hex[:6]
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:-3]
    alert_id = f"ALT-{timestamp_str}-{track_id}-{unique_suffix}"

    try:
        # Write snapshot image
        snap_fname = f"{alert_id}.jpg"
        snap_path = os.path.join(SNAPSHOT_DIR, snap_fname)
        cv2.imwrite(snap_path, frame)
        web_snap_path = f"/data/snapshots/{snap_fname}"

        alert = Alert(
            id=alert_id,
            timestamp=datetime.now(timezone.utc),
            camera_id=camera_id,
            alert_type=alert_type,
            severity=severity,
            track_id=track_id,
            object_type=obj_type,
            confidence=confidence,
            metadata_json=json.dumps(metadata),
            snapshot_path=web_snap_path,
            status="UNACKNOWLEDGED",
            synced_upstream=False
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)

        # Queue for store-and-forward edge sync
        sync_manager.queue_event(db, "NEW_ALERT", alert.to_dict())
        return alert
    except Exception as e:
        db.rollback()
        print(f"[WARN] Error saving alert {alert_id}: {e}")
        return None
