"""
Tests for Transient Biometric Memory, Recurrent Person Recognition,
Patrol Intercept Dispatch, and DEFCON-1 Mass Infiltration Defense Protocols.
"""

import os
import sys
import numpy as np
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.database.db import SessionLocal, init_db
from backend.database.models import PersonEncounter, MobilizationOrder, AuditLog
from backend.analytics.recurrent_engine import RecurrentPersonEngine, MassInfiltrationEvaluator
from backend.core.audit import log_audit_event, verify_audit_chain
from backend.sync.sync_manager import sync_manager


def test_recurrent_person_memory_and_cross_camera():
    init_db()
    db = SessionLocal()
    try:
        # Create a fresh test engine with 2.0s gap for fast unit testing
        engine = RecurrentPersonEngine(match_threshold=0.70, min_recurrent_gap_seconds=2.0)

        # Generate a unique synthetic 512-d ArcFace probe vector
        import time
        np.random.seed(int(time.time() * 1000) % 1000000)
        probe_vector = np.random.randn(512).astype(np.float32)
        probe_vector = (probe_vector / np.linalg.norm(probe_vector)).tolist()

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        person_bbox = [0.2, 0.2, 0.4, 0.8]

        # 1. First sighting at Petrapole Outpost
        is_rec, enc, score, delta, is_cross = engine.process_person_sighting(
            db=db,
            frame=dummy_frame,
            person_bbox=person_bbox,
            camera_id="CAM-01-IBB-PETRAPOLE",
            probe_emb=probe_vector
        )

        assert not is_rec, "First encounter must not be flagged as recurrent"
        assert enc is not None
        assert enc.sighting_count == 1
        assert enc.first_seen_camera_id == "CAM-01-IBB-PETRAPOLE"
        encounter_id = enc.id

        # 2. Ongoing sighting in same temporal window (no time gap)
        is_rec2, enc2, score2, delta2, is_cross2 = engine.process_person_sighting(
            db=db,
            frame=dummy_frame,
            person_bbox=person_bbox,
            camera_id="CAM-01-IBB-PETRAPOLE",
            probe_emb=probe_vector
        )
        assert not is_rec2, "Immediate next frame sighting must not trigger false re-appearance alarm"

        # 3. Simulate passage of time (>2.0s min gap) and reappearance at Dawki Meghalaya Outpost
        enc.first_seen_timestamp = datetime.now(timezone.utc) - timedelta(seconds=120)
        enc.last_seen_timestamp = datetime.now(timezone.utc) - timedelta(seconds=35)
        db.commit()

        # Probe with slight biometric variation (cosine sim ~0.95)
        noisy_probe = np.array(probe_vector) + np.random.normal(0, 0.02, 512)
        noisy_probe = (noisy_probe / np.linalg.norm(noisy_probe)).tolist()

        is_rec3, enc3, score3, delta3, is_cross3 = engine.process_person_sighting(
            db=db,
            frame=dummy_frame,
            person_bbox=person_bbox,
            camera_id="CAM-04-IBB-DAWKI",
            probe_emb=noisy_probe
        )

        assert is_rec3, "Target re-appearing after cooldown must trigger RECURRENT_PERSON_SIGHTING"
        assert enc3.id == encounter_id
        assert enc3.sighting_count == 2
        assert is_cross3, "Movement between Petrapole and Dawki must be flagged as cross-post"
        assert delta3 >= 30.0, f"Time delta should be >= 30s, got {delta3}"
        assert score3 >= 70.0, f"Similarity score should be >= 70%, got {score3}"

        print(f"  [PASS] Recurrent Person Memory: Alias={enc3.subject_alias}, Sightings={enc3.sighting_count}, Sim={score3}%, Delta={delta3}s, CrossPost={is_cross3}")
    finally:
        db.close()


def test_patrol_dispatch_and_audit_ledger():
    db = SessionLocal()
    try:
        # Fetch or create an encounter
        enc = db.query(PersonEncounter).first()
        if not enc:
            enc = PersonEncounter(
                id="ENC-TEST-PATROL-1",
                subject_alias="SUBJECT-P1",
                embedding_json="[]",
                first_seen_camera_id="CAM-01-IBB-PETRAPOLE",
                last_seen_camera_id="CAM-01-IBB-PETRAPOLE",
                sighting_count=2,
                snapshot_path="/data/snapshots/test.jpg"
            )
            db.add(enc)
            db.commit()

        # Perform patrol dispatch
        enc.patrol_dispatched = True
        enc.patrol_dispatch_notes = "[QRT-DELTA-9] Intercept target for credentials verification"
        db.commit()

        log_audit_event(
            db=db,
            operator_id="operator",
            action_type="PATROL_DISPATCH_ORDER",
            details={
                "encounter_id": enc.id,
                "subject_alias": enc.subject_alias,
                "patrol_unit_id": "QRT-DELTA-9",
                "sector_code": "INDO_BANGLADESH_BORDER"
            }
        )

        # Verify audit ledger chain
        is_valid, count, msg = verify_audit_chain(db)
        assert is_valid, f"Audit chain must remain valid after patrol dispatch logging: {msg}"

        # Verify sync queue
        sync_item = sync_manager.queue_event(
            db=db,
            event_type="PATROL_DISPATCH",
            payload={"encounter_id": enc.id, "unit": "QRT-DELTA-9"}
        )
        assert sync_item.id is not None
        assert not sync_item.is_synced

        print(f"  [PASS] Patrol Intercept Dispatch: Unit=QRT-DELTA-9, Dispatched=True, AuditChainValid={is_valid}")
    finally:
        db.close()


def test_mass_infiltration_density_evaluator():
    evaluator = MassInfiltrationEvaluator(personnel_threshold=15, vehicle_threshold=3)

    class DummyTrack:
        def __init__(self, class_name, is_vehicle=False):
            self.class_name = class_name
            self.is_vehicle = is_vehicle

    # Scenario 1: Normal border activity (3 persons, 1 vehicle)
    tracks_normal = [
        DummyTrack("person"), DummyTrack("person"), DummyTrack("person"),
        DummyTrack("car", is_vehicle=True)
    ]
    res_normal = evaluator.evaluate(tracks_normal, cooldown_seconds=0.0)
    assert not res_normal["is_mass_threat"], "3 persons must not trigger mass infiltration"
    assert res_normal["person_count"] == 3
    assert res_normal["vehicle_count"] == 1

    # Scenario 2: Mass Personnel Infiltration (16 persons)
    tracks_mass_personnel = [DummyTrack("person") for _ in range(16)]
    res_mass_personnel = evaluator.evaluate(tracks_mass_personnel, cooldown_seconds=0.0)
    assert res_mass_personnel["is_mass_threat"], "16 persons must trigger mass threat"
    assert res_mass_personnel["reason"] == "MASS_PERSONNEL_INFILTRATION"
    assert res_mass_personnel["defcon_level"] == "DEFCON-1 (CRITICAL)"
    assert res_mass_personnel["person_count"] == 16

    # Scenario 3: Unauthorized Vehicle Convoy (4 vehicles)
    tracks_convoy = [DummyTrack("truck", is_vehicle=True) for _ in range(4)]
    res_convoy = evaluator.evaluate(tracks_convoy, cooldown_seconds=0.0)
    assert res_convoy["is_mass_threat"], "4 vehicles must trigger vehicle convoy breach"
    assert res_convoy["reason"] == "VEHICLE_CONVOY_BREACH"
    assert res_convoy["vehicle_count"] == 4

    print(f"  [PASS] Mass Infiltration Evaluator: PersonnelInfiltration=16 (DEFCON-1), ConvoyBreach=4 (DEFCON-1)")


def test_hq_mobilization_order_and_allied_broadcast():
    import hashlib
    import uuid

    db = SessionLocal()
    try:
        now_dt = datetime.now(timezone.utc)
        order_id = f"MOB-TEST-{uuid.uuid4().hex[:6]}"
        raw_sig = f"{order_id}:INDO_BANGLADESH_BORDER:MASS_PERSONNEL_INFILTRATION:18:2:operator:{now_dt.isoformat()}"
        tx_hash = hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()

        order = MobilizationOrder(
            id=order_id,
            timestamp=now_dt,
            sector_code="INDO_BANGLADESH_BORDER",
            trigger_reason="MASS_PERSONNEL_INFILTRATION",
            person_count=18,
            vehicle_count=2,
            status="TRANSMITTED_TO_HQ",
            operator_id="operator",
            allied_alert_broadcast=True,
            hq_transmission_hash=tx_hash,
            details_json='{"sector": "PETRAPOLE_ZERO_LINE"}'
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        assert order.id == order_id
        assert len(order.hq_transmission_hash) == 64
        assert order.allied_alert_broadcast is True

        order_dict = order.to_dict()
        assert order_dict["person_count"] == 18
        assert order_dict["vehicle_count"] == 2
        assert order_dict["status"] == "TRANSMITTED_TO_HQ"

        # Audit log verification
        log_audit_event(
            db=db,
            operator_id="operator",
            action_type="HQ_REINFORCEMENT_REQUESTED",
            details={
                "order_id": order_id,
                "transmission_hash": tx_hash,
                "person_count": 18
            }
        )
        is_valid, count, msg = verify_audit_chain(db)
        assert is_valid, f"Audit chain must be intact: {msg}"

        print(f"  [PASS] HQ Mobilization & Allied Broadcast: Order={order_id}, Hash={tx_hash[:16]}..., AlliedAlert=True")
    finally:
        db.close()


if __name__ == "__main__":
    print("--- RUNNING RECURRENT MEMORY & MASS DEFENSE TESTS ---")
    test_recurrent_person_memory_and_cross_camera()
    test_patrol_dispatch_and_audit_ledger()
    test_mass_infiltration_density_evaluator()
    test_hq_mobilization_order_and_allied_broadcast()
    print("--- ALL TESTS PASSED ---")
