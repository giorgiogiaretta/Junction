"""g1/live_policy_v2_vision.py: the head camera recognises every object; for each hand, the object NEAREST to the robot pinch (within
SELECT_R) gives the finger cap and the assist target: egg 0.60, empty can 0.90, stress ball 1.0. Nothing recognised near the hand, or
only the CLI fallback object: the careful cap 0.60."""
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


def policy(V, objs, cli="stress_ball"):
    p = V.LivePolicyV2("replay:77", {"right": cli}, {"right": (0.35, -0.15)})
    p.reset("x")
    found = {"right": None}
    p.perc = (found, None, "test", None, 0.1, [{"label": l, "p": np.array(xyz, float)} for l, xyz in objs]); p.vision_future = object()
    assert p._init({"head_rgb": None, "head_depth": None, "arm_q": np.zeros(14), "hand_q": np.zeros(14)})
    return p


def cap_at(p, xyz):
    ch = p.chains["right"]; p._select("right", ch, p.kin.base + np.array(xyz, float)); return ch.grasp[3], ch.grasp[4]["cap"]


SCENE = [("egg", (0.35, -0.15, 0.03)), ("can_empty", (0.35, 0.05, 0.08)), ("stress_ball", (0.45, -0.30, 0.04))]


def test_nearest_object_sets_the_cap(V):
    p = policy(V, SCENE)
    assert cap_at(p, (0.36, -0.14, 0.06)) == ("egg", pytest.approx(0.60))
    assert cap_at(p, (0.35, 0.04, 0.10)) == ("can_empty", pytest.approx(0.90))
    assert cap_at(p, (0.44, -0.29, 0.07)) == ("stress_ball", pytest.approx(1.00))


def test_far_from_everything_is_careful(V):
    p = policy(V, SCENE)
    assert cap_at(p, (0.15, -0.40, 0.30))[1] == pytest.approx(V.CAP_DEFAULT)


def test_no_camera_cli_object_is_careful(V):
    p = policy(V, [], cli="stress_ball")
    assert cap_at(p, (0.35, -0.15, 0.06)) == ("stress_ball", pytest.approx(0.60))


def test_no_switch_while_grasping(V):
    p = policy(V, SCENE); ch = p.chains["right"]
    cap_at(p, (0.36, -0.14, 0.06)); ch.stage = "hold"
    assert cap_at(p, (0.35, 0.04, 0.10)) == ("egg", pytest.approx(0.60))      # holding the egg: stays egg / 0.60


def test_hard_caps(V):
    assert V.CAP_HARD == {"egg": 0.60, "can_empty": 0.90, "stress_ball": 1.0} and V.CAP_DEFAULT == 0.60
