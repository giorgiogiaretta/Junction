"""g1/live_policy_v1.py takes object poses AND closure caps from ai.perceive (one call), never hard-coded caps (Tommaso's #146 review)."""
import os, sys, time, types
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "g1"))   # the policy runs as a script from g1/
REPO = os.environ.get("AALTO_REPO", r"C:\Users\giorg\Desktop\aaltonomous-humanoid")
if not os.path.isdir(REPO): pytest.skip("needs the aaltonomous-humanoid clone (AALTO_REPO)", allow_module_level=True)
pytest.importorskip("mujoco"); pytest.importorskip("msgpack")
P = pytest.importorskip("ai.perceive")
from g1 import live_policy_v1 as L


def test_match_prefers_hand_side_and_skips_unusable():
    objs = [{"label": "egg", "usable": True, "p_pelvis": [.35, .15, .8]}, {"label": "egg", "usable": True, "p_pelvis": [.35, -.15, .8]},
            {"label": "can_empty", "usable": False, "p_pelvis": [.3, .1, .8]}]
    r = L._match(objs, "egg", "right"); l = L._match(objs, "egg", "left", {id(r)})
    assert r["p_pelvis"][1] < 0 and l["p_pelvis"][1] > 0
    assert L._match(objs, "can_empty", "left") is None


def test_fallback_caps_never_full_force():
    assert all(L._fallback_cap(o) < 1.0 for o in L.PROFILE)


def test_policy_uses_perceived_pose_and_cap(monkeypatch):
    seen = [{"label": "can_empty", "usable": True, "p_pelvis": [.33, .16, .80], "cap": .5},
            {"label": "egg", "usable": True, "p_pelvis": [.33, -.16, .80], "cap": .7}]
    monkeypatch.setattr(P, "perceive", lambda rgb, d, f, **k: seen)
    cal = types.SimpleNamespace(pixel_to_pelvis=lambda *a: [0., 0., 0.])
    monkeypatch.setitem(sys.modules, "aaltonomous.interface.calibration", types.SimpleNamespace(calibration=cal))
    pol = L.LivePolicy("replay:77,78", "egg", "can_empty")
    from robot.g1_dex3 import G1Dex3Retargeter
    obs = {"arm_q": np.zeros(14), "hand_q": np.zeros(len(G1Dex3Retargeter().joints)),
           "head_rgb": np.full((48, 64, 3), 100, np.uint8), "head_depth": np.full((48, 64), 900, np.uint16)}
    pol.reset("pick")
    for _ in range(100):
        pol.act(obs)
        if pol.initialized: break
        time.sleep(.02)
    assert pol.initialized
    assert pol.cap == {"right": .7, "left": .5}
    assert pol.targets["right"][2] == "camera" and pol.targets["right"][3] == [.33, -.16, .80]
    assert pol.targets["left"][3] == [.33, .16, .80]
