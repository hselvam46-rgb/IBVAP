"""
Loitering & Dwell-Time Detection Engine.
Calculates time spent by targets inside exclusion zones.
Standardized default threshold: 90 seconds (configurable).
"""

import time
from typing import Dict, Any, Tuple, Optional, List
from backend.core.config import LOITERING_DEFAULT_THRESHOLD_SECONDS


class LoiteringEngine:
    def __init__(self, default_threshold_seconds: float = LOITERING_DEFAULT_THRESHOLD_SECONDS):
        self.default_threshold = default_threshold_seconds
        # Dwell registry: key = (zone_id, track_id) -> {"entry_time": float, "last_seen": float, "alert_fired": bool}
        self.dwell_tracker: Dict[Tuple[str, int], Dict[str, Any]] = {}

    def update_dwell(
        self,
        zone_id: str,
        track_id: int,
        is_inside: bool,
        threshold_seconds: Optional[float] = None
    ) -> Tuple[bool, float, bool]:
        """
        Update dwell time for a target in a zone.
        Returns:
            (is_loitering_alarm, current_dwell_seconds, is_inside)
        """
        thresh = threshold_seconds if threshold_seconds is not None else self.default_threshold
        now = time.time()
        key = (zone_id, track_id)

        if is_inside:
            if key not in self.dwell_tracker:
                self.dwell_tracker[key] = {
                    "entry_time": now,
                    "last_seen": now,
                    "alert_fired": False
                }
                return False, 0.0, True

            entry_data = self.dwell_tracker[key]
            entry_data["last_seen"] = now
            dwell_seconds = now - entry_data["entry_time"]

            if dwell_seconds >= thresh and not entry_data["alert_fired"]:
                entry_data["alert_fired"] = True
                return True, dwell_seconds, True

            return False, dwell_seconds, True
        else:
            if key in self.dwell_tracker:
                # If target was seen inside recently, keep for brief gap; otherwise remove
                if now - self.dwell_tracker[key]["last_seen"] > 2.0:
                    del self.dwell_tracker[key]
            return False, 0.0, False

    def get_dwell_time(self, zone_id: str, track_id: int) -> float:
        key = (zone_id, track_id)
        if key in self.dwell_tracker:
            return round(time.time() - self.dwell_tracker[key]["entry_time"], 1)
        return 0.0

    def cleanup_inactive_tracks(self, active_track_ids: List[int]):
        active_set = set(active_track_ids)
        now = time.time()
        to_del = [k for k, v in self.dwell_tracker.items() if k[1] not in active_set or (now - v["last_seen"] > 3.0)]
        for k in to_del:
            del self.dwell_tracker[k]
