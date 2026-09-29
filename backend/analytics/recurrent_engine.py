"""
Transient Biometric Memory & Recurrent Person Recognition Engine.
Also evaluates Mass Infiltration Density (>=15 persons or >=3 vehicles)
for Tactical HQ Reinforcement & Allied High Alert protocols.
"""

import time
import os
import json
import uuid
import numpy as np
import cv2
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional
from sqlalchemy.orm import Session

from backend.database.models import PersonEncounter
from backend.core.config import SNAPSHOT_DIR


class RecurrentPersonEngine:
    def __init__(self, match_threshold: float = 0.70, min_recurrent_gap_seconds: float = 30.0):
        self.match_threshold = match_threshold
        self.min_recurrent_gap_seconds = min_recurrent_gap_seconds
        # In-memory vector cache for sub-10ms lookup: list of (encounter_id, np_array_embedding)
        self.cached_encounters: List[Tuple[str, np.ndarray]] = []
        self._cache_loaded = False

    def _ensure_cache_loaded(self, db: Session):
        if not self._cache_loaded:
            encs = db.query(PersonEncounter).order_by(PersonEncounter.last_seen_timestamp.desc()).limit(200).all()
            self.cached_encounters = []
            for e in encs:
                emb = np.array(e.get_embedding(), dtype=np.float32)
                norm = np.linalg.norm(emb)
                if norm > 0:
                    emb = emb / norm
                self.cached_encounters.append((e.id, emb))
            self._cache_loaded = True

    def process_person_sighting(
        self,
        db: Session,
        frame: np.ndarray,
        person_bbox: List[float],
        camera_id: str,
        probe_emb: List[float]
    ) -> Tuple[bool, Optional[PersonEncounter], float, float, bool]:
        """
        Process a detected person's 512-d embedding.
        Returns:
            (is_recurrent, encounter_obj, similarity_score, time_delta_seconds, is_cross_post)
        """
        self._ensure_cache_loaded(db)
        now_dt = datetime.now(timezone.utc)
        probe_arr = np.array(probe_emb, dtype=np.float32)
        norm = np.linalg.norm(probe_arr)
        if norm > 0:
            probe_arr = probe_arr / norm

        best_score = 0.0
        best_id = None

        # Compare against transient memory
        for enc_id, ref_arr in self.cached_encounters:
            score = float(np.dot(probe_arr, ref_arr))
            if score > best_score:
                best_score = score
                best_id = enc_id

        # Check if match meets re-appearance threshold
        if best_id and best_score >= self.match_threshold:
            encounter = db.query(PersonEncounter).filter(PersonEncounter.id == best_id).first()
            if encounter:
                # Calculate time since last sighting
                last_seen = encounter.last_seen_timestamp
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                elapsed_sec = max(0.0, (now_dt - last_seen).total_seconds())

                first_seen = encounter.first_seen_timestamp
                if first_seen.tzinfo is None:
                    first_seen = first_seen.replace(tzinfo=timezone.utc)
                total_delta_sec = max(0.0, (now_dt - first_seen).total_seconds())

                is_cross_post = (encounter.last_seen_camera_id != camera_id)

                # If reappeared after the minimum time separation gap
                if elapsed_sec >= self.min_recurrent_gap_seconds:
                    encounter.sighting_count += 1
                    encounter.last_seen_timestamp = now_dt
                    encounter.last_seen_camera_id = camera_id
                    db.commit()
                    db.refresh(encounter)

                    return True, encounter, round(best_score * 100, 1), round(total_delta_sec, 1), is_cross_post
                else:
                    # Ongoing sighting in same temporal window
                    encounter.last_seen_timestamp = now_dt
                    encounter.last_seen_camera_id = camera_id
                    db.commit()
                    return False, encounter, round(best_score * 100, 1), 0.0, False

        # If not matched, register as a new encounter in transient memory
        h, w = frame.shape[:2]
        x1 = max(0, int(person_bbox[0] * w))
        y1 = max(0, int(person_bbox[1] * h))
        x2 = min(w, int(person_bbox[2] * w))
        y2 = min(h, int(person_bbox[3] * h))

        crop = frame[y1:y2, x1:x2] if (x2 > x1 and y2 > y1) else frame

        # If crop is pitch black (e.g. privacy shutter closed or test frame), generate a high-tech tactical biometric probe visual
        if crop is None or crop.size == 0 or float(np.mean(crop)) < 15.0:
            crop = np.zeros((130, 110, 3), dtype=np.uint8)
            crop[:] = [24, 18, 12]  # Dark navy background
            # Biometric grid & crosshairs
            cv2.rectangle(crop, (15, 12), (95, 118), (255, 212, 0), 1)  # Cyan frame
            cv2.circle(crop, (55, 48), 24, (70, 50, 30), -1)  # Head silhouette
            cv2.circle(crop, (55, 48), 24, (255, 212, 0), 1)  # Head outline
            cv2.ellipse(crop, (55, 115), (42, 35), 0, 180, 360, (70, 50, 30), -1)  # Torso
            cv2.ellipse(crop, (55, 115), (42, 35), 0, 180, 360, (255, 212, 0), 1)
            # Reticle lines
            cv2.line(crop, (35, 48), (75, 48), (163, 229, 0), 1)
            cv2.line(crop, (55, 28), (55, 68), (163, 229, 0), 1)
            cv2.putText(crop, "512-D PROBE", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.30, (255, 255, 255), 1)

        enc_id = f"ENC-{now_dt.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        alias = f"SUBJECT-{enc_id[-4:].upper()}"
        snap_fname = f"{enc_id}.jpg"
        snap_path = os.path.join(SNAPSHOT_DIR, snap_fname)
        cv2.imwrite(snap_path, crop)
        web_snap_path = f"/data/snapshots/{snap_fname}"

        new_enc = PersonEncounter(
            id=enc_id,
            subject_alias=alias,
            embedding_json=json.dumps(probe_emb),
            first_seen_timestamp=now_dt,
            first_seen_camera_id=camera_id,
            last_seen_timestamp=now_dt,
            last_seen_camera_id=camera_id,
            sighting_count=1,
            snapshot_path=web_snap_path,
            patrol_dispatched=False
        )
        db.add(new_enc)
        db.commit()
        db.refresh(new_enc)

        # Add to in-memory cache
        self.cached_encounters.insert(0, (enc_id, probe_arr))
        if len(self.cached_encounters) > 200:
            self.cached_encounters.pop()

        return False, new_enc, 0.0, 0.0, False


class MassInfiltrationEvaluator:
    """
    Evaluates mass personnel infiltration (>= 15 members)
    or multiple vehicle convoy incursions (>= 3 vehicles).
    """
    def __init__(self, personnel_threshold: int = 15, vehicle_threshold: int = 3):
        self.personnel_threshold = personnel_threshold
        self.vehicle_threshold = vehicle_threshold
        self.last_alert_time = 0.0

    def evaluate(self, tracks: List[Any], cooldown_seconds: float = 30.0) -> Dict[str, Any]:
        persons = 0
        vehicles = 0

        for t in tracks:
            cname = getattr(t, "class_name", "")
            if cname == "person":
                persons += 1
            elif getattr(t, "is_vehicle", False) or cname in ("car", "truck", "bus", "motorcycle"):
                vehicles += 1

        is_threat = (persons >= self.personnel_threshold) or (vehicles >= self.vehicle_threshold)

        if not is_threat:
            return {
                "is_mass_threat": False,
                "person_count": persons,
                "vehicle_count": vehicles,
                "defcon_level": "DEFCON-4 (NORMAL)"
            }

        now = time.time()
        should_alert = (now - self.last_alert_time >= cooldown_seconds)
        if should_alert:
            self.last_alert_time = now

        reason = "MASS_PERSONNEL_INFILTRATION" if persons >= self.personnel_threshold else "VEHICLE_CONVOY_BREACH"
        msg = (
            f"MASS INFILTRATION DETECTED: {persons} personnel active in sector (Threshold: {self.personnel_threshold})!"
            if persons >= self.personnel_threshold else
            f"CONVOY BREACH DETECTED: {vehicles} unauthorized vehicles moving in formation (Threshold: {self.vehicle_threshold})!"
        )

        return {
            "is_mass_threat": True,
            "should_broadcast": should_alert,
            "person_count": persons,
            "vehicle_count": vehicles,
            "defcon_level": "DEFCON-1 (CRITICAL)",
            "reason": reason,
            "message": msg,
            "recommended_action": "IMMEDIATE_HQ_REINFORCEMENTS_AND_ALLIED_WARNING"
        }


# Singletons
recurrent_engine = RecurrentPersonEngine()
mass_infiltration_evaluator = MassInfiltrationEvaluator()

