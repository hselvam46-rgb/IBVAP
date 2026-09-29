"""
IBVAP Automated Master Test Suite.
Runs all verification tests across AI detection, ByteTrack tracking,
512-d ArcFace facial recognition, Indian ANPR format validation,
spatial tripwires & geofences, 90s loitering, offline store-and-forward sync,
SHA-256 audit chaining, and 72-hour retention purge.
"""

import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.tests.test_detector_and_tracker import (
    test_iou_calculation,
    test_detector_threat_classification,
    test_bytetrack_id_consistency
)
from backend.tests.test_face_and_anpr import (
    test_face_512d_embeddings_and_matching,
    test_indian_plate_format_validation,
    test_plate_preprocessing
)
from backend.tests.test_spatial_and_loitering import (
    test_directional_tripwire,
    test_polygon_geofence,
    test_loitering_engine_90s_threshold
)
from backend.tests.test_store_forward_and_audit import (
    setup_module,
    test_session_auth_and_roles,
    test_store_and_forward_offline_sync,
    test_sha256_audit_hash_chaining_and_tamper_detection,
    test_72hour_retention_purge
)
from backend.tests.test_recurrent_and_mass_defense import (
    test_recurrent_person_memory_and_cross_camera,
    test_patrol_dispatch_and_audit_ledger,
    test_mass_infiltration_density_evaluator,
    test_hq_mobilization_order_and_allied_broadcast
)

if __name__ == "__main__":
    print("=" * 65)
    print("  IBVAP BORDER SURVEILLANCE PLATFORM - MASTER TEST SUITE")
    print("=" * 65)

    setup_module()

    print("\n[SUITE 1: DETECTION & TRACKING]")
    test_iou_calculation()
    test_detector_threat_classification()
    test_bytetrack_id_consistency()

    print("\n[SUITE 2: 512-D ARCFACE BIOMETRICS & PADDLE-OCR ANPR]")
    test_face_512d_embeddings_and_matching()
    test_indian_plate_format_validation()
    test_plate_preprocessing()

    print("\n[SUITE 3: SPATIAL TRIPWIRES & 90-SECOND LOITERING DWELL]")
    test_directional_tripwire()
    test_polygon_geofence()
    test_loitering_engine_90s_threshold()

    print("\n[SUITE 4: STORE-AND-FORWARD SYNC, SHA-256 AUDIT & 72H PURGE]")
    test_session_auth_and_roles()
    test_store_and_forward_offline_sync()
    test_sha256_audit_hash_chaining_and_tamper_detection()
    test_72hour_retention_purge()

    print("\n[SUITE 5: TRANSIENT BIOMETRICS, PATROL DISPATCH & DEFCON-1 DEFENSE]")
    test_recurrent_person_memory_and_cross_camera()
    test_patrol_dispatch_and_audit_ledger()
    test_mass_infiltration_density_evaluator()
    test_hq_mobilization_order_and_allied_broadcast()

    print("\n" + "=" * 65)
    print("  ALL 17 VERIFICATION SUITES PASSED SUCCESSFULLY! (100% PASS)")
    print("=" * 65)
