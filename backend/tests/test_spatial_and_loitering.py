"""
Automated Test: Directional Tripwire, Polygon Geofence & Loitering Engine.
Verifies vector intersection, Inbound vs Outbound enforcement,
and standardized 90-second loitering dwell threshold.
"""

import time
from backend.analytics.spatial_engine import SpatialEngine, point_in_polygon
from backend.analytics.loitering_engine import LoiteringEngine


def test_directional_tripwire():
    spatial = SpatialEngine()
    zone_id = "ZONE-TRIP-TEST"
    # Horizontal tripwire from x=0.2, y=0.5 to x=0.8, y=0.5
    zone_coords = [{"x": 0.2, "y": 0.5}, {"x": 0.8, "y": 0.5}]

    # 1. Inbound movement: target moves from y=0.3 to y=0.6 (crossing line going downwards/inbound)
    inbound_trail = [(0.5, 0.3), (0.5, 0.6)]
    breached, direction = spatial.check_tripwire(
        zone_id=zone_id,
        zone_coords=zone_coords,
        direction_rule="INBOUND",
        track_id=1,
        trail=inbound_trail
    )
    assert breached is True, "Inbound movement must trigger inbound tripwire breach"
    assert direction == "INBOUND"

    # Reset for track 2
    spatial.cleanup_lost_tracks([])

    # 2. Outbound movement: target moves from y=0.6 to y=0.3 (crossing line going upwards/outbound)
    outbound_trail = [(0.5, 0.6), (0.5, 0.3)]
    breached_out, direction_out = spatial.check_tripwire(
        zone_id=zone_id,
        zone_coords=zone_coords,
        direction_rule="INBOUND",
        track_id=2,
        trail=outbound_trail
    )
    assert breached_out is False, "Outbound movement must NOT trigger inbound-only tripwire"

    # 3. Bidirectional rule
    breached_bi, direction_bi = spatial.check_tripwire(
        zone_id=zone_id,
        zone_coords=zone_coords,
        direction_rule="BIDIRECTIONAL",
        track_id=3,
        trail=outbound_trail
    )
    assert breached_bi is True, "Bidirectional tripwire must trigger on either direction"

    print("[PASS] Directional tripwire vector crossing verified (Inbound vs Outbound)")


def test_polygon_geofence():
    # Box from 0.2, 0.2 to 0.8, 0.8
    polygon = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]

    # Inside point
    assert point_in_polygon((0.5, 0.5), polygon) is True
    # Outside points
    assert point_in_polygon((0.1, 0.5), polygon) is False
    assert point_in_polygon((0.5, 0.9), polygon) is False

    print("[PASS] Polygon geofence ray casting verified")


def test_loitering_engine_90s_threshold():
    loiter = LoiteringEngine(default_threshold_seconds=90.0)
    zone_id = "ZONE-POLY-BUFFER"
    track_id = 42

    # Step 1: Target enters zone -> no alarm initially
    alarm1, dwell1, inside1 = loiter.update_dwell(zone_id, track_id, is_inside=True)
    assert alarm1 is False
    assert inside1 is True
    assert dwell1 == 0.0

    # Step 2: Simulate 45 seconds elapsed (below 90s default threshold)
    entry_key = (zone_id, track_id)
    loiter.dwell_tracker[entry_key]["entry_time"] -= 45.0
    alarm2, dwell2, inside2 = loiter.update_dwell(zone_id, track_id, is_inside=True)
    assert alarm2 is False, "45s is below 90s threshold, must not trigger loitering alarm"
    assert dwell2 >= 45.0

    # Step 3: Simulate 92 seconds elapsed (exceeds 90s threshold)
    loiter.dwell_tracker[entry_key]["entry_time"] -= 47.0  # Total 92s
    alarm3, dwell3, inside3 = loiter.update_dwell(zone_id, track_id, is_inside=True)
    assert alarm3 is True, "92s exceeds 90s threshold, MUST trigger loitering alarm"
    assert dwell3 >= 90.0

    # Step 4: Repeating frames should not trigger duplicate alarm spam
    alarm4, dwell4, inside4 = loiter.update_dwell(zone_id, track_id, is_inside=True)
    assert alarm4 is False, "Loitering alert must not re-fire continuously"

    # Step 5: Target leaves zone
    loiter.update_dwell(zone_id, track_id, is_inside=False)
    # Simulate gap
    time.sleep(0.01)
    loiter.dwell_tracker[entry_key]["last_seen"] -= 3.0
    loiter.update_dwell(zone_id, track_id, is_inside=False)
    assert entry_key not in loiter.dwell_tracker, "Tracker must reset when target leaves zone"

    print("[PASS] Loitering & Dwell engine verified with standardized 90s default threshold")


if __name__ == "__main__":
    test_directional_tripwire()
    test_polygon_geofence()
    test_loitering_engine_90s_threshold()
    print("\nALL SPATIAL & LOITERING TESTS PASSED!")
