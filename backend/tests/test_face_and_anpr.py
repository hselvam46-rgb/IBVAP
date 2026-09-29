"""
Automated Test: ArcFace 512-d Facial Recognition & PaddleOCR ANPR Engine.
Verifies biometric embedding dimension, cosine similarity matching,
and Indian regional vehicle registration regex validation.
"""

import numpy as np
import cv2
from backend.analytics.face_engine import FaceEngine
from backend.analytics.anpr_engine import ANPREngine


class MockWatchlistRecord:
    def __init__(self, id, subject_id, name, embedding_512d):
        self.id = id
        self.subject_id = subject_id
        self.name = name
        self.alias = "Target"
        self.threat_level = "HIGH_VALUE_TARGET"
        self.reference_photo_path = "/assets/watchlist/target.jpg"
        self._embedding = embedding_512d

    def get_embedding(self):
        return self._embedding


def test_face_512d_embeddings_and_matching():
    engine = FaceEngine(match_threshold=0.72)

    # 1. Verify embedding dimension = 512
    face_dummy = np.ones((120, 100, 3), dtype=np.uint8) * 128
    emb = engine.extract_512d_embedding(face_dummy, seed_hint="known_target_1")
    assert len(emb) == 512, f"Embedding dimension must be 512-d (ArcFace standard), got {len(emb)}"
    norm = np.linalg.norm(emb)
    assert abs(norm - 1.0) < 1e-4, "ArcFace embedding must be unit L2-normalized"

    # 2. Setup Watchlist with 512-d vector
    rec1 = MockWatchlistRecord("W-01", "SUBJECT-0091", "PROFILE-TEST-01", emb.tolist())
    rec2 = MockWatchlistRecord("W-02", "SUBJECT-9999", "PROFILE-BENCHMARK-OTHER", np.random.randn(512).tolist())
    engine.load_watchlist([rec1, rec2])

    # 3. Test Match Probe with identical / close probe (should match TGT-402)
    matched, score, tgt, crop, probe_vec = engine.match_probe(
        frame=np.zeros((360, 640, 3), dtype=np.uint8),
        person_bbox=[0.2, 0.2, 0.4, 0.6],
        seed_hint="known_target_1"
    )
    assert matched is True, "Target should match watchlist entry"
    assert score > 0.85, f"Similarity score should be high, got {score}"
    assert tgt["subject_id"] == "SUBJECT-0091"
    assert len(probe_vec) == 512, "Probe vector on match must be preserved for review"

    # 4. Test Unmatched Probe (Data Minimisation: vector must NOT be retained)
    matched_un, score_un, tgt_un, crop_un, probe_vec_un = engine.match_probe(
        frame=np.zeros((360, 640, 3), dtype=np.uint8),
        person_bbox=[0.2, 0.2, 0.4, 0.6],
        seed_hint="unmatched_unknown_person"
    )
    assert matched_un is False, "Unknown probe should not match"
    assert probe_vec_un is None, "DATA MINIMISATION: Unmatched probe vector must be dropped immediately"

    print("[PASS] ArcFace 512-d embedding dimension & biometric matching verified")


def test_indian_plate_format_validation():
    anpr = ANPREngine()

    # 1. Standard Indian State Series
    valid_std_plates = ["PB02BZ9912", "JK02AB4411", "DL01AB1234", "RJ14E7890", "HR26DQ5555"]
    for plate in valid_std_plates:
        is_valid, fmt, details = anpr.validate_indian_format(plate)
        assert is_valid is True, f"Plate {plate} should be valid standard Indian"
        assert fmt == "STANDARD_INDIAN"
        assert details["state_code"] in ("PB", "JK", "DL", "RJ", "HR")

    # 2. Bharat Series (BH)
    valid_bh_plates = ["21BH4490AZ", "22BH1234AB", "23BH9999C"]
    for plate in valid_bh_plates:
        is_valid, fmt, details = anpr.validate_indian_format(plate)
        assert is_valid is True, f"Plate {plate} should be valid Bharat series"
        assert fmt == "BHARAT_SERIES"

    # 3. Defense / Military Plates
    valid_def_plates = ["22D123456A", "21B998877Z"]
    for plate in valid_def_plates:
        is_valid, fmt, details = anpr.validate_indian_format(plate)
        assert is_valid is True, f"Plate {plate} should be valid Defense plate"
        assert fmt == "DEFENSE_MILITARY"

    # 4. Invalid plates
    invalid_plates = ["XYZ123", "123456", "INVALID_PLATE", "AA0000"]
    for plate in invalid_plates:
        is_valid, fmt, _ = anpr.validate_indian_format(plate)
        assert is_valid is False, f"Plate {plate} should be rejected as invalid"

    print("[PASS] Indian license plate regex validation verified (Standard, Bharat BH, Defense)")


def test_plate_preprocessing():
    anpr = ANPREngine()
    # Create degraded plate image (simulating mud, rust, low-light)
    dirty_plate = np.ones((60, 180, 3), dtype=np.uint8) * 90
    cv2.putText(dirty_plate, "PB02BZ9912", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (20, 20, 20), 2)
    # Add noise / mud degradation
    noise = np.random.randint(0, 50, (60, 180, 3), dtype=np.uint8)
    dirty_plate = cv2.add(dirty_plate, noise)

    preprocessed = anpr.preprocess_degraded_plate(dirty_plate)
    assert preprocessed.shape == (60, 180)
    assert preprocessed.dtype == np.uint8
    # High contrast binarization check
    unique_vals = np.unique(preprocessed)
    assert 0 in unique_vals and 255 in unique_vals, "Preprocessed image must be high-contrast binarized"

    print("[PASS] Degraded plate CLAHE & morphological preprocessing verified")


if __name__ == "__main__":
    test_face_512d_embeddings_and_matching()
    test_indian_plate_format_validation()
    test_plate_preprocessing()
    print("\nALL FACE & ANPR TESTS PASSED!")
