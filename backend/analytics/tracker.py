"""
ByteTrack Multi-Object Tracking Engine.
Maintains consistent target IDs through brief visual occlusions using
dual-threshold IoU association and motion estimation.
"""

import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from backend.analytics.detector import Detection


def calculate_iou(boxA: List[float], boxB: List[float]) -> float:
    """Calculate Intersection over Union for [x1, y1, x2, y2]."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interW = max(0.0, xB - xA)
    interH = max(0.0, yB - yA)
    interArea = interW * interH

    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    unionArea = boxAArea + boxBArea - interArea

    if unionArea <= 0.0:
        return 0.0
    return interArea / unionArea


class STrack:
    _count = 0

    def __init__(self, detection: Detection):
        STrack._count += 1
        self.track_id = STrack._count
        self.bbox = detection.bbox  # [x1, y1, x2, y2]
        self.class_name = detection.class_name
        self.confidence = detection.confidence
        self.is_threat = getattr(detection, "is_threat", detection.class_name == "person")
        self.is_vehicle = getattr(detection, "is_vehicle", detection.class_name in ("car", "truck", "bus", "motorcycle", "bicycle"))
        self.is_fauna = getattr(detection, "is_fauna", detection.class_name in ("dog", "cow", "sheep", "horse", "bird", "cat"))

        # Trajectory history: store normalized centroids [(cx, cy), ...]
        cx = (self.bbox[0] + self.bbox[2]) / 2.0
        cy = (self.bbox[1] + self.bbox[3]) / 2.0
        self.trail = [(cx, cy)]
        self.velocity = (0.0, 0.0)

        self.state = "Tracked"  # Tracked, Lost, Removed
        self.frame_id = 0
        self.time_since_update = 0
        self.total_frames = 1
        self.dwell_time_seconds = 0.0
        self.first_seen_time = None
        self.last_seen_time = None

    @property
    def centroid(self) -> Tuple[float, float]:
        """Current normalized centroid (cx, cy)."""
        cx = (self.bbox[0] + self.bbox[2]) / 2.0
        cy = (self.bbox[1] + self.bbox[3]) / 2.0
        return (cx, cy)

    def update(self, detection: Detection, frame_id: int, dt: float = 0.033):
        self.frame_id = frame_id
        self.time_since_update = 0
        self.total_frames += 1
        self.confidence = detection.confidence
        self.is_threat = getattr(detection, "is_threat", self.is_threat)
        self.is_vehicle = getattr(detection, "is_vehicle", self.is_vehicle)
        self.is_fauna = getattr(detection, "is_fauna", self.is_fauna)

        old_cx = (self.bbox[0] + self.bbox[2]) / 2.0
        old_cy = (self.bbox[1] + self.bbox[3]) / 2.0

        self.bbox = detection.bbox
        new_cx = (self.bbox[0] + self.bbox[2]) / 2.0
        new_cy = (self.bbox[1] + self.bbox[3]) / 2.0

        if dt > 0:
            self.velocity = ((new_cx - old_cx) / dt, (new_cy - old_cy) / dt)

        self.trail.append((new_cx, new_cy))
        if len(self.trail) > 40:
            self.trail.pop(0)

        self.dwell_time_seconds += dt
        self.state = "Tracked"

    def mark_missed(self):
        self.time_since_update += 1
        if self.time_since_update > 30:  # ~1 second at 30fps
            self.state = "Removed"
        else:
            self.state = "Lost"

    def to_dict(self) -> Dict[str, Any]:
        cx, cy = self.centroid
        return {
            "track_id": self.track_id,
            "bbox": [round(c, 4) for c in self.bbox],
            "centroid": [round(cx, 4), round(cy, 4)],
            "class_name": self.class_name,
            "confidence": round(self.confidence, 3),
            "is_threat": self.is_threat,
            "state": self.state,
            "velocity": [round(v, 4) for v in self.velocity],
            "dwell_time": round(self.dwell_time_seconds, 1),
            "trail": [[round(x, 4), round(y, 4)] for x, y in self.trail[-15:]]
        }


class ByteTracker:
    def __init__(self, track_thresh: float = 0.50, match_thresh: float = 0.35, max_time_lost: int = 30):
        self.track_thresh = track_thresh
        self.match_thresh = match_thresh
        self.max_time_lost = max_time_lost
        self.tracked_stracks: List[STrack] = []
        self.lost_stracks: List[STrack] = []
        self.frame_id = 0

    def update(self, detections: List[Detection], dt: float = 0.033) -> List[STrack]:
        self.frame_id += 1

        # Separate detections into high and low confidence (ByteTrack principle)
        det_high = [d for d in detections if d.confidence >= self.track_thresh]
        det_low = [d for d in detections if 0.20 <= d.confidence < self.track_thresh]

        # Active track pool
        active_tracks = [t for t in self.tracked_stracks if t.state == "Tracked"]
        pool_tracks = active_tracks + self.lost_stracks

        # --- Step 1: Match high confidence detections with active/lost tracks ---
        matched_tracks_1, unmatched_tracks_1, unmatched_dets_1 = self._associate(
            pool_tracks, det_high, self.match_thresh
        )

        for track, det in matched_tracks_1:
            track.update(det, self.frame_id, dt)

        # --- Step 2: Match remaining tracks with low confidence detections (Handles Occlusion) ---
        remain_tracks = [t for t in pool_tracks if t in unmatched_tracks_1 and t.state == "Tracked"]
        matched_tracks_2, unmatched_tracks_2, _ = self._associate(
            remain_tracks, det_low, self.match_thresh * 0.8
        )

        for track, det in matched_tracks_2:
            track.update(det, self.frame_id, dt)

        # --- Step 3: Handle unmatched tracks ---
        for track in unmatched_tracks_2:
            track.mark_missed()

        # --- Step 4: Initialize new tracks from unmatched high-confidence detections ---
        for det in unmatched_dets_1:
            new_track = STrack(det)
            self.tracked_stracks.append(new_track)

        # Retain only active tracks
        self.tracked_stracks = [t for t in self.tracked_stracks if t.state in ("Tracked", "Lost")]
        self.lost_stracks = [t for t in self.tracked_stracks if t.state == "Lost"]

        # Return tracks currently active in this frame
        return [t for t in self.tracked_stracks if t.state == "Tracked"]

    def _associate(self, tracks: List[STrack], detections: List[Detection], thresh: float):
        """Greedy IoU association between tracks and detections."""
        if len(tracks) == 0 or len(detections) == 0:
            return [], tracks, detections

        # Compute cost matrix (1 - IoU)
        iou_matrix = np.zeros((len(tracks), len(detections)), dtype=np.float32)
        for t_idx, track in enumerate(tracks):
            for d_idx, det in enumerate(detections):
                iou_matrix[t_idx, d_idx] = calculate_iou(track.bbox, det.bbox)

        matched_tracks = []
        matched_t_indices = set()
        matched_d_indices = set()

        # Sort matches by highest IoU
        flat_indices = np.argsort(-iou_matrix, axis=None)
        for flat_idx in flat_indices:
            t_idx, d_idx = np.unravel_index(flat_idx, iou_matrix.shape)
            if iou_matrix[t_idx, d_idx] < thresh:
                break
            if t_idx in matched_t_indices or d_idx in matched_d_indices:
                continue
            matched_tracks.append((tracks[t_idx], detections[d_idx]))
            matched_t_indices.add(t_idx)
            matched_d_indices.add(d_idx)

        unmatched_tracks = [t for i, t in enumerate(tracks) if i not in matched_t_indices]
        unmatched_dets = [d for j, d in enumerate(detections) if j not in matched_d_indices]

        return matched_tracks, unmatched_tracks, unmatched_dets
