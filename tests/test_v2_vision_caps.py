"""g1/live_policy_v2_vision.py: the camera label sets the finger cap (operator 15/11): egg never above 0.60, empty can 0.90, ball 1.0;
the camera can only LOWER the cap of the CLI object, and the finger command never exceeds the cap."""
import os, sys
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "g1"), os.path.join(ROOT, "g1", "sim")]


@pytest.fixture(scope="module")
def V():
    pytest.importorskip("mujoco")
    os.environ["G1_PRIOR"] = "0"
    import live_policy_v2_vision as V
    return V


def caps(V, cli, cam):
    p = V.LivePolicyV2("replay:77", {"right": cli}, {"right": (0.35, -0.15)})
    p.reset("x")
    found = {"right": None if cam is None else {"label": cam, "depth_ok": False, "p": None}}
    p.perc = (found, None, "test", None, 0.1); p.vision_future = object()
    assert p._init({"head_rgb": None, "head_depth": None, "arm_q": np.zeros(14), "hand_q": np.zeros(14)})
    return p.chains["right"].grasp[4]["cap"]


@pytest.mark.parametrize("cli,cam,want", [
    ("stress_ball", "egg", 0.60), ("stress_ball", "can_empty", 0.90), ("stress_ball", "stress_ball", 1.00),
    ("egg", "stress_ball", 0.60), ("can_empty", "egg", 0.60), ("can_empty", None, 0.90), ("stress_ball", None, 1.00)])
def test_cap_follows_camera_label(V, cli, cam, want):
    assert caps(V, cli, cam) == pytest.approx(want)


def test_hard_caps(V):
    assert V.CAP_HARD == {"egg": 0.60, "can_empty": 0.90, "stress_ball": 1.0}
