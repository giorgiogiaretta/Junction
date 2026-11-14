"""g1/perception_v1 decision rules (no MuJoCo, no network): fragile-first labels, conservative caps, nearest-object-per-side assignment."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from g1.perception_v1 import decide, cap_for, assign

GEO_CAN = {"name": "geometry", "object": "can_empty", "confidence": 0.8, "ok": True}
GEO_UNK = {"name": "geometry", "object": "unknown", "confidence": None, "ok": False}


def test_egg_vote_wins_fragile_first():
    lab, *_ = decide([GEO_CAN, {"name": "gemma", "object": "egg", "confidence": 0.7, "ok": True}], GEO_CAN)
    assert lab == "egg" and cap_for(lab, None, 1, GEO_CAN) == 0.70


def test_disagreement_is_unknown_and_conservative():
    lab, *_ = decide([GEO_CAN, {"name": "gemma", "object": "stress ball", "confidence": 0.9, "ok": True}], GEO_CAN)
    assert lab == "unknown" and cap_for(lab, None, 0, GEO_CAN) == 0.68


def test_can_never_above_crush_safe_cap():
    vlm_can = {"name": "gemma", "object": "can", "confidence": 0.95, "ok": True}
    lab, conf, agree, _ = decide([GEO_UNK, vlm_can], GEO_UNK)
    assert lab == "can_empty" and cap_for(lab, conf, agree, GEO_UNK) == 0.45     # empty can crushes: object_profiles.json can 0.45
    lab, conf, agree, _ = decide([GEO_CAN, vlm_can], GEO_CAN)
    assert cap_for(lab, conf, agree, GEO_CAN) == 0.45                            # geometry too: still 0.45, never 1.0


def test_dead_backend_falls_back_to_geometry():
    lab, *_ = decide([GEO_CAN, {"name": "gemma", "object": "other", "confidence": None, "ok": False, "error": "HTTP 402"}], GEO_CAN)
    assert lab == "can_empty"


def test_assign_nearest_per_side_prefers_depth_ok():
    o = lambda x, y, ok=True: {"p_pelvis": [x, y, 0.03], "depth_ok": ok, "label": "egg"}
    near_bad, far_ok, left = o(0.30, -0.15, False), o(0.45, -0.20), o(0.35, 0.15)
    a = assign([near_bad, far_ok, left])
    assert a["right"] is far_ok and a["left"] is left
    assert assign([left])["right"] is None
