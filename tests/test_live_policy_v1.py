"""g1/live_policy_v1.py takes object poses AND closure caps from perception (one call at the first valid frame), the can never above its crush-safe cap."""
import json, os, sys, time, types
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "g1"))   # the policy runs as a script from g1/
from g1 import perception_v1 as PV


def test_can_cap_is_the_profile_cap_never_full_force():
    can = json.load(open(os.path.join(ROOT, "g1", "object_profiles.json")))["can"]["max_closure"]
    assert PV.CAP["can_empty"] == can < 1.0
    geo_can = {"name": "geometry", "object": "can_empty", "confidence": None, "ok": True}
    assert PV.cap_for("can_empty", 0.99, 3, geo_can) == can


REPO = os.environ.get("AALTO_REPO", r"C:\Users\giorg\Desktop\aaltonomous-humanoid")


@pytest.mark.skipif(not os.path.isdir(REPO), reason="needs the aaltonomous-humanoid clone (AALTO_REPO)")
def test_policy_uses_perceived_pose_and_cap(monkeypatch):
    pytest.importorskip("mujoco"); pytest.importorskip("msgpack")
    from g1 import live_policy_v1 as L
    assert all(L.PROFILE[o]["cap"] < 1.0 for o in ("egg", "can_empty", "unknown"))
    seen = {"table_z": None, "objects": [{"label": "can_empty", "depth_ok": True, "p_pelvis": [.33, .16, .02], "cap": .45},
                                         {"label": "egg", "depth_ok": True, "p_pelvis": [.33, -.16, .02], "cap": .7}]}
    monkeypatch.setattr(PV, "perceive_with_ai", lambda rgb, d, f, **k: seen)
    monkeypatch.setattr(PV, "robot_mask", lambda *a, **k: (lambda d: np.zeros(np.asarray(d).shape, bool)))
    monkeypatch.setattr(L, "Camera", lambda test_frames=None: types.SimpleNamespace(frames=None, K=np.eye(3), T=np.eye(4), p2p=lambda *a: [0., 0., 0.]))
    pol = L.LivePolicy("replay:77,78")
    from robot.g1_dex3 import G1Dex3Retargeter
    obs = {"arm_q": np.zeros(14), "hand_q": np.zeros(len(G1Dex3Retargeter().joints)),
           "head_rgb": np.full((48, 64, 3), 100, np.uint8), "head_depth": np.full((48, 64), 900, np.uint16)}
    pol.reset("pick")
    for _ in range(100):
        pol.act(obs)
        if pol.initialized: break
        time.sleep(.02)
    assert pol.initialized
    assert pol.cap == {"right": .7, "left": .45} and pol.obj == {"right": "egg", "left": "can_empty"}
    assert pol.targets["right"][2] == "camera" and pol.targets["right"][3] == [.33, -.16, .02]
    assert pol.targets["left"][3] == [.33, .16, .02]
