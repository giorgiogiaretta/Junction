"""ai/perceive.py on a SYNTHETIC multi-object head RGB-D render (ball + lying egg + standing can on a table). No network: stub recognizer."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[1])); sys.path.insert(0, str(pathlib.Path(__file__).parent))
import numpy as np
import pytest
import test_locate as T
from ai.perceive import perceive, fit_projection

BALL = (np.array([0.33, -0.10, T.TABLE_Z + 0.0325]), (240, 120, 30))
EGG = (np.array([0.38, 0.08, T.TABLE_Z + 0.0215]), (245, 245, 240))
CAN = (np.array([0.45, -0.02, T.TABLE_Z + 0.073]), (40, 90, 200))


def scene(with_box=False):
    r = 0.0325; layers = [T.render(BALL[0], (r, r, r), BALL[1]),
                          T.render(EGG[0], (0.0285, 0.0215, 0.0215), EGG[1]),
                          T.render_can(CAN[0][0], CAN[0][1], 0.029, 0.146, CAN[1])]
    if with_box:   # a 30 cm wide slab 8 cm above the table (robot arm / tray): must be skipped by the footprint limit
        layers.append(T.render(np.array([0.20, 0.0, T.TABLE_Z + 0.03]), (0.05, 0.16, 0.02), (120, 120, 120)))
    rgb = layers[0][0].copy(); depth = layers[0][1].copy()
    for c, d in layers[1:]:
        hit = (c != (90, 70, 50)).any(-1) & ((d < depth) | ~(rgb != (90, 70, 50)).any(-1))
        rgb[hit] = c[hit]; depth[hit] = d[hit]
    return rgb, depth


def stub(crop):
    """Plays the VLM ensemble: names the dominant non-table colour of the crop."""
    px = crop.reshape(-1, 3).astype(int); px = px[(np.abs(px - (90, 70, 50)).sum(1) > 30)]
    m = px.mean(0) if len(px) else np.zeros(3)
    obj = "stress_ball" if m[0] > 180 and m[2] < 120 else "can" if m[2] > 150 and m[0] < 120 else "egg" if m.min() > 180 else "other"
    return {"object": obj, "confidence": 0.95, "agree": 2, "reason": "stub", "votes": [{"name": "gemini", "object": obj, "confidence": 0.95, "ok": True}]}


def test_projection_fit_is_exact_for_a_pinhole_calibration():
    A, res = fit_projection(T.p2p)
    assert res < 1e-6
    assert np.allclose(A @ [300 * 500, 200 * 500, 500, 1], T.p2p(300, 200, 500), atol=1e-6)


def test_three_objects_labelled_and_located():
    rgb, depth = scene(); info = {}
    objs = perceive(rgb, depth, T.p2p, recognizer=stub, debug=info)
    assert abs(info["table_z_est"] - T.TABLE_Z) < 0.005, info
    use = {o["label"]: o for o in objs if o["usable"]}
    assert set(use) == {"egg", "stress_ball", "can_empty"}, objs
    for lab, (c, _) in (("stress_ball", BALL), ("egg", EGG), ("can_empty", CAN)):
        assert np.linalg.norm(np.array(use[lab]["p_pelvis"][:2]) - c[:2]) <= 0.01, (lab, use[lab], c)
    assert use["egg"]["cap"] <= 0.70 and use["can_empty"]["source"] == "depth+vlm"


def test_big_slab_skipped_and_fallbacks():
    rgb, depth = scene(with_box=True); info = {}
    objs = perceive(rgb, depth, T.p2p, table_z=T.TABLE_Z, recognizer=stub, debug=info)
    assert info["skipped"], info                                   # the 30 cm slab is not an object
    def liar(crop):                                                # model calls everything a ball: the white egg is still an egg
        return {"object": "stress_ball", "confidence": 0.99, "agree": 1, "votes": [{"name": "gemini", "object": "stress_ball", "ok": True}]}
    labs = [o["label"] for o in perceive(*scene(), T.p2p, recognizer=liar) if o["usable"]]
    assert "egg" in labs, labs
    def dead(crop): raise TimeoutError("no network")
    objs = perceive(*scene(), T.p2p, recognizer=dead)
    by = {o["label"]: o for o in objs}
    assert by["egg"]["usable"] and by["stress_ball"]["source"] == "depth+colour"
    assert by["stress_ball"]["cap"] < 1.0                          # colour alone never unlocks full force
    assert not by["unknown"]["usable"]                             # the blue can: no model, no colour -> listed, not usable


def test_metres_depth_and_no_objects():
    rgb, depth = scene()
    objs = perceive(rgb, depth.astype(np.float32) / 1000.0, T.p2p, recognizer=stub)
    assert sum(o["usable"] for o in objs) == 3
    flat_rgb = np.full_like(rgb, (90, 70, 50)); _, flat = T.render(np.array([5.0, 5.0, -1.0]), (0.01, 0.01, 0.01), (0, 0, 0))
    assert perceive(flat_rgb, flat, T.p2p, recognizer=stub) == []
