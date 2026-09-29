"""
Database Engine & Session Management for IBVAP.
Seeds initial default data for border posts, cameras, zones, and users.
"""

import os
import hashlib
import json
import numpy as np
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database.models import (
    Base, User, Camera, Zone, Alert, Watchlist, WatchlistPlate, AuditLog, SyncQueue,
    PersonEncounter, MobilizationOrder
)

from backend.core.config import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "ibvap_edge.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def generate_synthetic_512d_embedding(seed_str: str) -> list:
    """Generate a deterministic 512-dimensional normalized unit vector for demo watchlist."""
    seed = int(hashlib.sha256(seed_str.encode()).hexdigest()[:8], 16)
    rng = np.random.RandomState(seed)
    vector = rng.randn(512).astype(np.float32)
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    return vector.tolist()


def init_db():
    """Create all tables and seed default baseline configurations."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 1. Seed Users if not present
        if db.query(User).count() == 0:
            users = [
                User(
                    username="operator",
                    password_hash=hash_password("operator123"),
                    full_name="Constable R. Sharma",
                    role="OPERATOR",
                    badge_number="BSF-PB-4409"
                ),
                User(
                    username="duty_officer",
                    password_hash=hash_password("officer123"),
                    full_name="Inspector V. K. Rawat",
                    role="DUTY_OFFICER",
                    badge_number="BSF-PB-1021"
                ),
                User(
                    username="admin",
                    password_hash=hash_password("admin123"),
                    full_name="Commandant S. Sengupta",
                    role="ADMIN",
                    badge_number="BSF-HQ-0012"
                )
            ]
            db.add_all(users)
            db.commit()

        # 2. Seed Border Surveillance Cameras (Scoped to Indo-Bangladesh Border Sector)
        if db.query(Camera).count() == 0:
            cameras = [
                Camera(
                    id="CAM-01-IBB-PETRAPOLE",
                    name="Tower 7A - Zero Line Perimeter",
                    sector="Eastern Sector - BOP Petrapole (South Bengal)",
                    sector_code="INDO_BANGLADESH_BORDER",
                    source_type="OPTICAL",
                    rtsp_url="",
                    status="ACTIVE",
                    latitude=23.0415,
                    longitude=88.8972,
                    bop_post="BOP Petrapole Zero Point",
                    fov_heading=90.0
                ),
                Camera(
                    id="CAM-02-IBB-ICHAMATI",
                    name="Thermal Ambush - Ichamati River Gap",
                    sector="South Bengal Riverine Sector - BOP Hasnabad/Taki",
                    sector_code="INDO_BANGLADESH_BORDER",
                    source_type="THERMAL_IRONBOW",
                    rtsp_url="",
                    status="ACTIVE",
                    latitude=22.5912,
                    longitude=88.9221,
                    bop_post="BOP Ichamati Reach",
                    fov_heading=85.0
                ),
                Camera(
                    id="CAM-03-IBB-ICP-ANPR",
                    name="ICP Barrier Gate - Petrapole Cargo Checkpost",
                    sector="North 24 Parganas - ICP Petrapole",
                    sector_code="INDO_BANGLADESH_BORDER",
                    source_type="CHECKPOST",
                    rtsp_url="",
                    status="ACTIVE",
                    latitude=23.0398,
                    longitude=88.8950,
                    bop_post="ICP Cargo Terminal",
                    fov_heading=180.0
                ),
                Camera(
                    id="CAM-04-IBB-DAWKI",
                    name="IR Smart Fence - Dawki Sector Culvert 12",
                    sector="Meghalaya Frontier - BOP Dawki Outpost",
                    sector_code="INDO_BANGLADESH_BORDER",
                    source_type="THERMAL_WHITEHOT",
                    rtsp_url="",
                    status="ACTIVE",
                    latitude=25.1834,
                    longitude=92.0192,
                    bop_post="BOP Dawki River Gorge",
                    fov_heading=175.0
                )
            ]
            db.add_all(cameras)
            db.commit()

        # 3. Seed Default Zones and Tripwires
        if db.query(Zone).count() == 0:
            zones = [
                Zone(
                    id="ZONE-TRIP-01",
                    camera_id="CAM-01-IBB-PETRAPOLE",
                    name="Zero Line Primary Tripwire (Inbound Infiltration)",
                    zone_type="TRIPWIRE",
                    direction="INBOUND",
                    coordinates_json=json.dumps([
                        {"x": 0.15, "y": 0.55},
                        {"x": 0.85, "y": 0.60}
                    ]),
                    dwell_threshold_seconds=90.0,
                    severity="CRITICAL",
                    is_active=True
                ),
                Zone(
                    id="ZONE-POLY-01",
                    camera_id="CAM-01-IBB-PETRAPOLE",
                    name="Exclusion Buffer Area (90s Dwell Loitering)",
                    zone_type="RESTRICTED_POLYGON",
                    direction="INBOUND",
                    coordinates_json=json.dumps([
                        {"x": 0.20, "y": 0.35},
                        {"x": 0.80, "y": 0.35},
                        {"x": 0.85, "y": 0.75},
                        {"x": 0.15, "y": 0.75}
                    ]),
                    dwell_threshold_seconds=90.0,
                    severity="HIGH",
                    is_active=True
                ),
                Zone(
                    id="ZONE-TRIP-02",
                    camera_id="CAM-02-IBB-ICHAMATI",
                    name="Ichamati River Bank Ingress Tripwire",
                    zone_type="TRIPWIRE",
                    direction="INBOUND",
                    coordinates_json=json.dumps([
                        {"x": 0.10, "y": 0.50},
                        {"x": 0.90, "y": 0.50}
                    ]),
                    dwell_threshold_seconds=90.0,
                    severity="CRITICAL",
                    is_active=True
                )
            ]
            db.add_all(zones)
            db.commit()

        # 4. Seed Local Watchlist Targets (512-dimensional ArcFace embeddings)
        if db.query(Watchlist).count() == 0:
            targets = [
                Watchlist(
                    id="WLIST-001",
                    subject_id="SUBJECT-0091",
                    name="PROFILE-TEST-01",
                    alias="SYNTHETIC-TARGET-ALPHA",
                    threat_level="CALIBRATION_FLAG",
                    biometric_embedding_512d=json.dumps(generate_synthetic_512d_embedding("synthetic_test_profile_01")),
                    reference_photo_path="/frontend/assets/placeholder_face.jpg",
                    notes="Synthetic benchmark vector for 512-d ArcFace facial similarity calibration."
                ),
                Watchlist(
                    id="WLIST-002",
                    subject_id="SUBJECT-0119",
                    name="PROFILE-TEST-02",
                    alias="SYNTHETIC-TARGET-BETA",
                    threat_level="CALIBRATION_FLAG",
                    biometric_embedding_512d=json.dumps(generate_synthetic_512d_embedding("synthetic_test_profile_02")),
                    reference_photo_path="/frontend/assets/placeholder_face.jpg",
                    notes="Synthetic reference vector for cross-border surveillance evaluation."
                ),
                Watchlist(
                    id="WLIST-003",
                    subject_id="SUBJECT-0882",
                    name="PROFILE-TEST-03",
                    alias="SYNTHETIC-TARGET-GAMMA",
                    threat_level="CALIBRATION_FLAG",
                    biometric_embedding_512d=json.dumps(generate_synthetic_512d_embedding("synthetic_test_profile_03")),
                    reference_photo_path="/frontend/assets/placeholder_face.jpg",
                    notes="Synthetic calibration profile for algorithmic threshold validation."
                )
            ]
            db.add_all(targets)
            db.commit()

        # 5. Seed Watchlist Plates
        if db.query(WatchlistPlate).count() == 0:
            plates = [
                WatchlistPlate(
                    id="PLATE-001",
                    plate_number="WB02TEST9912",
                    vehicle_description="White Patrol Utility Vehicle",
                    threat_level="HOTLIST",
                    remarks="Synthetic test vehicle registration for ANPR checkpost evaluation."
                ),
                WatchlistPlate(
                    id="PLATE-002",
                    plate_number="ML05TEST4411",
                    vehicle_description="Dark Grey Transport Van",
                    threat_level="HOTLIST",
                    remarks="Synthetic test vehicle record for Dawki checkpost benchmark."
                ),
                WatchlistPlate(
                    id="PLATE-003",
                    plate_number="21BHTEST4490",
                    vehicle_description="Silver 4x4 Patrol Rover",
                    threat_level="HOTLIST",
                    remarks="Synthetic Bharat Series test registration format."
                )
            ]
            db.add_all(plates)
            db.commit()

        # 6. Seed Genesis Audit Log with Hash Chain
        if db.query(AuditLog).count() == 0:
            from backend.core.audit import log_audit_event
            log_audit_event(
                db=db,
                operator_id="SYSTEM",
                action_type="INITIALIZE",
                details={"event": "SYSTEM_INITIALIZATION", "node": "EDGE_BOP_88"}
            )

    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
