"""
Spatial Analytics Engine: Virtual Tripwires & Geofences.
Calculates directional vector intersections and polygon containment.
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np


def ccw(A: Tuple[float, float], B: Tuple[float, float], C: Tuple[float, float]) -> float:
    """Returns the signed cross product of vectors AB and AC."""
    return (B[0] - A[0]) * (C[1] - A[1]) - (B[1] - A[1]) * (C[0] - A[0])


def lines_intersect(
    p1: Tuple[float, float], p2: Tuple[float, float],
    p3: Tuple[float, float], p4: Tuple[float, float]
) -> bool:
    """Check if line segment p1-p2 intersects line segment p3-p4."""
    d1 = ccw(p3, p4, p1)
    d2 = ccw(p3, p4, p2)
    d3 = ccw(p1, p2, p3)
    d4 = ccw(p1, p2, p4)

    return (((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and
            ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)))


def point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
    """Ray casting point-in-polygon test."""
    x, y = point
    n = len(polygon)
    inside = False

    p1x, p1y = polygon[0]
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y

    return inside


class SpatialEngine:
    def __init__(self):
        # Cache of active breaches to prevent repeating alert spam for the same target track
        self.tripwire_breaches = set()  # Set of (zone_id, track_id)
        self.polygon_entries = set()    # Set of (zone_id, track_id)

    def check_tripwire(
        self,
        zone_id: str,
        zone_coords: List[Dict[str, float]],
        direction_rule: str,
        track_id: int,
        trail: List[Tuple[float, float]]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if target trail crossed a directional tripwire line.
        direction_rule: INBOUND, OUTBOUND, BIDIRECTIONAL
        """
        if len(zone_coords) < 2 or len(trail) < 2:
            return False, None

        if (zone_id, track_id) in self.tripwire_breaches:
            return False, None

        p1 = (zone_coords[0]["x"], zone_coords[0]["y"])
        p2 = (zone_coords[1]["x"], zone_coords[1]["y"])

        # Check last step of the target trail
        prev_pt = trail[-2]
        curr_pt = trail[-1]

        if lines_intersect(p1, p2, prev_pt, curr_pt):
            # Determine direction: cross product of tripwire vector (p1->p2) with movement (prev->curr)
            cross_val = ccw(p1, p2, curr_pt)
            actual_dir = "INBOUND" if cross_val > 0 else "OUTBOUND"

            if direction_rule == "BIDIRECTIONAL" or direction_rule == actual_dir:
                self.tripwire_breaches.add((zone_id, track_id))
                return True, actual_dir

        return False, None

    def check_polygon_entry(
        self,
        zone_id: str,
        zone_coords: List[Dict[str, float]],
        track_id: int,
        target_point: Tuple[float, float]
    ) -> bool:
        """
        Check if target base coordinates entered a restricted polygon zone.
        """
        if len(zone_coords) < 3:
            return False

        poly = [(pt["x"], pt["y"]) for pt in zone_coords]
        is_inside = point_in_polygon(target_point, poly)

        if is_inside:
            if (zone_id, track_id) not in self.polygon_entries:
                self.polygon_entries.add((zone_id, track_id))
                return True
        else:
            self.polygon_entries.discard((zone_id, track_id))

        return False

    def is_inside_polygon(
        self,
        zone_coords: List[Dict[str, float]],
        target_point: Tuple[float, float]
    ) -> bool:
        if len(zone_coords) < 3:
            return False
        poly = [(pt["x"], pt["y"]) for pt in zone_coords]
        return point_in_polygon(target_point, poly)

    def cleanup_lost_tracks(self, active_track_ids: List[int]):
        """Clean memory for tracks that left the frame."""
        active_set = set(active_track_ids)
        self.tripwire_breaches = {(zid, tid) for (zid, tid) in self.tripwire_breaches if tid in active_set}
        self.polygon_entries = {(zid, tid) for (zid, tid) in self.polygon_entries if tid in active_set}
