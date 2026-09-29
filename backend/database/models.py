"""
IBVAP Database Models
SQLAlchemy ORM models for on-premise edge storage.
"""

from datetime import datetime, timezone
import json
from typing import List, Dict, Any, Optional
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    full_name = Column(String(128), nullable=False)
    role = Column(String(32), nullable=False, default="OPERATOR")  # OPERATOR, DUTY_OFFICER, ADMIN
    badge_number = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "full_name": self.full_name,
            "role": self.role,
            "badge_number": self.badge_number,
        }


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    sector = Column(String(128), nullable=False)
    sector_code = Column(String(64), default="INDO_BANGLADESH_BORDER", index=True)
    source_type = Column(String(64), nullable=False, default="OPTICAL")  # OPTICAL, THERMAL_IRONBOW, THERMAL_WHITEHOT, CHECKPOST
    rtsp_url = Column(String(256), nullable=True)
    status = Column(String(32), default="ACTIVE")  # ACTIVE, OFFLINE, MAINTENANCE
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    bop_post = Column(String(64), nullable=False)
    fov_heading = Column(Float, default=0.0)  # Angle in degrees
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    zones = relationship("Zone", back_populates="camera", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="camera", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "sector": self.sector,
            "sector_code": self.sector_code,
            "source_type": self.source_type,
            "status": self.status,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "bop_post": self.bop_post,
            "fov_heading": self.fov_heading,
        }


class Zone(Base):
    __tablename__ = "zones"

    id = Column(String(64), primary_key=True)
    camera_id = Column(String(64), ForeignKey("cameras.id"), nullable=False)
    name = Column(String(128), nullable=False)
    zone_type = Column(String(32), nullable=False)  # TRIPWIRE, RESTRICTED_POLYGON
    direction = Column(String(32), default="BIDIRECTIONAL")  # INBOUND, OUTBOUND, BIDIRECTIONAL
    coordinates_json = Column(Text, nullable=False)  # JSON array of points [{x, y}, ...] in relative 0.0-1.0
    dwell_threshold_seconds = Column(Float, default=90.0)  # Standardized default: 90s
    severity = Column(String(32), default="CRITICAL")  # CRITICAL, HIGH, MEDIUM
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    camera = relationship("Camera", back_populates="zones")

    def get_coordinates(self):
        try:
            return json.loads(self.coordinates_json)
        except Exception:
            return []

    def to_dict(self):
        return {
            "id": self.id,
            "camera_id": self.camera_id,
            "name": self.name,
            "zone_type": self.zone_type,
            "direction": self.direction,
            "coordinates": self.get_coordinates(),
            "dwell_threshold_seconds": self.dwell_threshold_seconds,
            "severity": self.severity,
            "is_active": self.is_active,
        }


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String(64), primary_key=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    camera_id = Column(String(64), ForeignKey("cameras.id"), nullable=False)
    alert_type = Column(String(64), nullable=False, index=True)
    severity = Column(String(32), nullable=False, index=True)  # CRITICAL, HIGH, MEDIUM, LOW
    track_id = Column(Integer, nullable=False)
    object_type = Column(String(32), nullable=False)  # person, vehicle, animal
    confidence = Column(Float, nullable=False)
    metadata_json = Column(Text, default="{}")  # Contains details, probe embedding (if match), plates, etc.
    snapshot_path = Column(String(256), nullable=False)
    clip_path = Column(String(256), nullable=True)
    status = Column(String(32), default="UNACKNOWLEDGED", index=True)  # UNACKNOWLEDGED, ACKNOWLEDGED, ESCALATED, DISMISSED
    operator_id = Column(String(64), nullable=True)
    operator_notes = Column(Text, nullable=True)
    resolution_timestamp = Column(DateTime, nullable=True)
    synced_upstream = Column(Boolean, default=False, index=True)

    camera = relationship("Camera", back_populates="alerts")

    def get_metadata(self):
        try:
            return json.loads(self.metadata_json)
        except Exception:
            return {}

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "camera_id": self.camera_id,
            "camera_name": self.camera.name if self.camera else self.camera_id,
            "sector": self.camera.sector if self.camera else "Sector Alpha",
            "alert_type": self.alert_type,
            "severity": self.severity,
            "track_id": self.track_id,
            "object_type": self.object_type,
            "confidence": round(self.confidence, 3),
            "metadata": self.get_metadata(),
            "snapshot_path": self.snapshot_path,
            "clip_path": self.clip_path,
            "status": self.status,
            "operator_id": self.operator_id,
            "operator_notes": self.operator_notes,
            "resolution_timestamp": self.resolution_timestamp.isoformat() if self.resolution_timestamp else None,
            "synced_upstream": self.synced_upstream,
        }


class Watchlist(Base):
    """
    Local biometric watchlist.
    Only 512-d normalized numeric ArcFace embeddings are stored.
    No unencrypted identifying facial photos stored with identity.
    """
    __tablename__ = "watchlist"

    id = Column(String(64), primary_key=True)
    subject_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    alias = Column(String(128), nullable=True)
    threat_level = Column(String(64), default="HIGH_VALUE_TARGET")
    biometric_embedding_512d = Column(Text, nullable=False)  # JSON serialized list of 512 floats
    reference_photo_path = Column(String(256), nullable=True)  # Reference preview for operator sign-off
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def get_embedding(self):
        try:
            return json.loads(self.biometric_embedding_512d)
        except Exception:
            return []

    def to_dict(self, include_embedding=False):
        data = {
            "id": self.id,
            "subject_id": self.subject_id,
            "name": self.name,
            "alias": self.alias,
            "threat_level": self.threat_level,
            "reference_photo_path": self.reference_photo_path,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_embedding:
            data["embedding"] = self.get_embedding()
        return data


class WatchlistPlate(Base):
    __tablename__ = "watchlist_plates"

    id = Column(String(64), primary_key=True)
    plate_number = Column(String(32), unique=True, nullable=False, index=True)
    vehicle_description = Column(String(128), nullable=False)
    threat_level = Column(String(64), default="HOTLIST")
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "plate_number": self.plate_number,
            "vehicle_description": self.vehicle_description,
            "threat_level": self.threat_level,
            "remarks": self.remarks,
        }


class AuditLog(Base):
    """
    Append-only tamper-evident audit log with SHA-256 hash chaining.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    operator_id = Column(String(64), nullable=False)
    action_type = Column(String(64), nullable=False, index=True)
    details_json = Column(Text, nullable=False)
    ip_address = Column(String(64), default="127.0.0.1")
    prev_hash = Column(String(64), nullable=False)
    sha256_hash = Column(String(64), nullable=False, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "operator_id": self.operator_id,
            "action_type": self.action_type,
            "details": json.loads(self.details_json) if self.details_json else {},
            "ip_address": self.ip_address,
            "prev_hash": self.prev_hash,
            "sha256_hash": self.sha256_hash,
        }


class SyncQueue(Base):
    """
    Store-and-forward queue for offline-first edge resilience.
    """
    __tablename__ = "sync_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    event_type = Column(String(64), nullable=False)
    payload_json = Column(Text, nullable=False)
    is_synced = Column(Boolean, default=False, index=True)
    synced_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "event_type": self.event_type,
            "is_synced": self.is_synced,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
        }


class PersonEncounter(Base):
    """
    Transient biometric memory for recurrent person recognition.
    Tracks re-appearances over time across different border camera outposts.
    """
    __tablename__ = "person_encounters"

    id = Column(String(64), primary_key=True)
    subject_alias = Column(String(64), nullable=False, index=True)
    embedding_json = Column(Text, nullable=False)
    first_seen_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    first_seen_camera_id = Column(String(64), nullable=False)
    last_seen_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    last_seen_camera_id = Column(String(64), nullable=False)
    sighting_count = Column(Integer, default=1)
    snapshot_path = Column(String(256), nullable=False)
    patrol_dispatched = Column(Boolean, default=False)
    patrol_dispatch_notes = Column(Text, nullable=True)

    def get_embedding(self) -> List[float]:
        return json.loads(self.embedding_json)

    def to_dict(self):
        delta_sec = 0.0
        if self.first_seen_timestamp and self.last_seen_timestamp:
            try:
                delta_sec = max(0.0, (self.last_seen_timestamp - self.first_seen_timestamp).total_seconds())
            except Exception:
                delta_sec = 0.0

        return {
            "id": self.id,
            "subject_alias": self.subject_alias,
            "first_seen_timestamp": self.first_seen_timestamp.isoformat() if self.first_seen_timestamp else None,
            "first_seen_camera_id": self.first_seen_camera_id,
            "last_seen_timestamp": self.last_seen_timestamp.isoformat() if self.last_seen_timestamp else None,
            "last_seen_camera_id": self.last_seen_camera_id,
            "sighting_count": self.sighting_count,
            "time_delta_seconds": round(delta_sec, 1),
            "snapshot_path": self.snapshot_path,
            "patrol_dispatched": self.patrol_dispatched,
            "patrol_dispatch_notes": self.patrol_dispatch_notes,
        }


class MobilizationOrder(Base):
    """
    Emergency tactical mobilization orders:
    HQ Reinforcement requests and Allied Force High-Alert warnings.
    """
    __tablename__ = "mobilization_orders"

    id = Column(String(64), primary_key=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    sector_code = Column(String(64), nullable=False)
    trigger_reason = Column(String(64), nullable=False)  # MASS_PERSONNEL_INFILTRATION, VEHICLE_CONVOY_BREACH
    person_count = Column(Integer, default=0)
    vehicle_count = Column(Integer, default=0)
    status = Column(String(32), default="TRANSMITTED_TO_HQ")  # TRANSMITTED_TO_HQ, ACKNOWLEDGED, RESOLVED
    operator_id = Column(String(64), nullable=False)
    allied_alert_broadcast = Column(Boolean, default=False)
    hq_transmission_hash = Column(String(64), nullable=False)
    details_json = Column(Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "sector_code": self.sector_code,
            "trigger_reason": self.trigger_reason,
            "person_count": self.person_count,
            "vehicle_count": self.vehicle_count,
            "status": self.status,
            "operator_id": self.operator_id,
            "allied_alert_broadcast": self.allied_alert_broadcast,
            "hq_transmission_hash": self.hq_transmission_hash,
            "details": json.loads(self.details_json) if self.details_json else {},
        }
