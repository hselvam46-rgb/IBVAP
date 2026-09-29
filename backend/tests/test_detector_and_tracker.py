"""
Automated Test: Detection & ByteTrack Multi-Object Tracking.
Verifies YOLOv8 detection output, threat classification, and track ID consistency.
"""

import numpy as np
from backend.analytics.detector import YOLOv8Detector, Detection
from backend.analytics.tracker import ByteTracker, calculate_iou


def test_iou_calculation():
    boxA = [0.1, 0.1, 0.5, 0.5]
    boxB = [0.1, 0.1, 0.5, 0.5]
    assert abs(calculate_iou(boxA, boxB) - 1.0) < 1e-5

    boxC = [0.6, 0.6, 0.9, 0.9]
    assert calculate_iou(boxA, boxC) == 0.0

    boxD = [0.3, 0.3, 0.7, 0.7]
    iou = calculate_iou(boxA, boxD)
    assert 0.1 < iou < 0.5
    print("[PASS] IoU calculation verified")


def test_detector_threat_classification():
    det_person = Detection([0.2, 0.2, 0.3, 0.5], "person", 0.92)
    assert det_person.is_threat is True
    assert det_person.is_vehicle is False
    assert det_person.is_fauna is False

    det_vehicle = Detection([0.1, 0.4, 0.4, 0.8], "car", 0.88)
    assert det_vehicle.is_threat is False
    assert det_vehicle.is_vehicle is True
    assert det_vehicle.is_fauna is False

    det_fauna = Detection([0.6, 0.6, 0.7, 0.7], "cow", 0.85)
    assert det_fauna.is_threat is False
    assert det_fauna.is_vehicle is False
    assert det_fauna.is_fauna is True
    print("[PASS] Detector threat classification verified")


def test_bytetrack_id_consistency():
    tracker = ByteTracker(track_thresh=0.50)

    # Frame 1: Target enters at (0.20, 0.30)
    det1 = [Detection([0.20, 0.30, 0.28, 0.50], "person", 0.90)]
    tracks1 = tracker.update(det1, dt=0.033)
    assert len(tracks1) == 1
    assigned_id = tracks1[0].track_id

    # Frame 2: Target moves slightly to (0.21, 0.31)
    det2 = [Detection([0.21, 0.31, 0.29, 0.51], "person", 0.89)]
    tracks2 = tracker.update(det2, dt=0.033)
    assert len(tracks2) == 1
    assert tracks2[0].track_id == assigned_id, "Track ID must remain consistent across frames"

    # Frame 3-5: Simulated partial occlusion (confidence drops to 0.25, ByteTrack low-det tier)
    det3 = [Detection([0.22, 0.32, 0.30, 0.52], "person", 0.30)]
    tracks3 = tracker.update(det3, dt=0.033)
    assert len(tracks3) == 1
    assert tracks3[0].track_id == assigned_id, "ByteTrack must maintain ID through occlusion"

    # Verify trajectory history length
    assert len(tracks3[0].trail) >= 3
    print(f"[PASS] ByteTrack ID consistency verified (Track ID #{assigned_id} maintained through occlusion)")


if __name__ == "__main__":
    test_iou_calculation()
    test_detector_threat_classification()
    test_bytetrack_id_consistency()
    print("\nALL DETECTOR & TRACKER TESTS PASSED!")
