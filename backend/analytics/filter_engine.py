"""
False-Alarm & Non-Threat Suppression Engine.
Filters out wind-blown vegetation, tree shadows, dust devils, and small roaming animals.
"""

from typing import List, Tuple, Dict, Any
import numpy as np
from backend.analytics.detector import Detection
from backend.analytics.tracker import STrack
from backend.core.config import DETECTION_CONFIDENCE_THRESHOLD, FALSE_ALARM_MIN_BBOX_AREA


class FalseAlarmFilter:
    def __init__(
        self,
        min_confidence: float = DETECTION_CONFIDENCE_THRESHOLD,
        min_bbox_area: float = FALSE_ALARM_MIN_BBOX_AREA
    ):
        self.min_confidence = min_confidence
        self.min_bbox_area = min_bbox_area

    def is_valid_detection(self, det: Detection) -> Tuple[bool, str]:
        """
        Evaluate if a raw detection passes false alarm criteria.
        Returns: (is_valid, reason)
        """
        # 1. Confidence threshold check
        if det.confidence < self.min_confidence:
            return False, f"Low confidence: {det.confidence:.2f} < {self.min_confidence:.2f}"

        # 2. Minimum bounding box area check (filters insects, small rodents, leaves)
        w = max(0.0, det.bbox[2] - det.bbox[0])
        h = max(0.0, det.bbox[3] - det.bbox[1])
        area = w * h
        if area < self.min_bbox_area:
            return False, f"Sub-scale trigger (area: {area:.5f} < {self.min_bbox_area:.5f})"

        return True, "PASSED"

    def is_vegetation_jitter(self, track: STrack) -> bool:
        """
        Detect wind-blown foliage / brush oscillation.
        Foliage moves back and forth with high path distance but near-zero net displacement.
        """
        if len(track.trail) < 10:
            return False

        # Calculate net displacement between start and end of recent trail
        start_pt = np.array(track.trail[0])
        end_pt = np.array(track.trail[-1])
        net_disp = np.linalg.norm(end_pt - start_pt)

        # Calculate total accumulated path length
        path_length = 0.0
        for i in range(1, len(track.trail)):
            path_length += np.linalg.norm(np.array(track.trail[i]) - np.array(track.trail[i - 1]))

        # If path length is large but net displacement is tiny, it's oscillating foliage
        if path_length > 0.15 and net_disp < 0.02:
            return True

        return False

    def categorize_threat_level(self, track: STrack, zone_severity: str = "HIGH") -> Tuple[str, bool]:
        """
        Assign severity level and determine if alert should be emitted.
        Returns: (severity: CRITICAL|HIGH|MEDIUM|LOW, should_alert: bool)
        """
        if self.is_vegetation_jitter(track):
            return "LOW", False  # Suppressed as vegetation

        is_fauna = getattr(track, "is_fauna", False) or (getattr(track, "class_name", "") in ("dog", "cow", "sheep", "horse", "bird", "cat"))
        if is_fauna:
            # Roaming animals (cow, dog, sheep) receive LOW severity and do not trigger sirens
            return "LOW", False

        if track.is_threat or track.class_name == "person":
            return zone_severity, True

        if track.is_vehicle:
            return "HIGH", True

        return "MEDIUM", True
