"""ml/square_policy rollout export (robot/ contract) and g1/sim/grasp_physics object specs from JSON (no data files)."""
import json
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "ml"))
import square_policy as SP


def test_export_rollout_matches_robot_contract(tmp_path):
    from robot.replay_square import load_rollout
    traj = np.array([[-0.147, -0.147, 0.0], [0.0, 0.0, 0.02], [0.147, 0.147, 0.0]])
    train = [{"grip": np.linspace(0.25, 0.9, 101)}]
    p = tmp_path / "r.json"
    SP.export_rollout({"traj": traj, "grip": np.array([0.25, 0.9, 0.575]), "leg": np.array([0, 0, 1])}, train, p)
    xyz, grip, hz, side = load_rollout(str(p))
    assert hz == SP.FPS and side == 0.297
    assert np.allclose(xyz, traj * 0.297 / SP.SIDE_TARGET, atol=1e-4)
    assert grip[0] == 0.0 and grip[1] == 1.0 and abs(grip[2] - 0.5) < 0.01   # train p5..p95 -> 0..1
    assert json.loads(p.read_text())["leg"] == [0, 0, 1]


def test_object_specs_validated(tmp_path):
    pytest.importorskip("mujoco")
    sys.path.insert(0, os.path.join(ROOT, "g1", "sim"))
    import grasp_physics as GP
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"banana": {"type": "ellipsoid", "size": [0.018, 0.018, 0.09], "mass": 0.12, "brk": 12, "soft": True}}))
    assert GP.load_object_specs(str(ok))["banana"]["brk"] == 12.0
    for bad in ({"type": "box", "size": [0.02], "mass": 0.1, "brk": None, "soft": False},
                {"type": "sphere", "size": [0.02, 0.02], "mass": 0.1, "brk": None, "soft": False},
                {"type": "sphere", "size": [0.02], "mass": 5.0, "brk": None, "soft": False},
                {"type": "sphere", "size": [0.02], "mass": 0.1, "soft": False}):
        b = tmp_path / "bad.json"; b.write_text(json.dumps({"x": bad}))
        with pytest.raises(ValueError):
            GP.load_object_specs(str(b))
