"""g1/arm_ik.py: axis calibration from a synthetic series K take, and direction check (operator forward/left/up -> robot hand forward/left/up)."""
import json, os, sys
import numpy as np, pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "g1"))
arm_ik = pytest.importorskip("arm_ik")
if not os.path.exists(arm_ik.ASSETS): pytest.skip("G1 model not fetched (run g1/sim/g1_sim.py)", allow_module_level=True)

# a Coil frame rotated 90 deg about z and tilted 20 deg: body forward/left/up expressed in Coil coordinates
a, t = np.radians(90), np.radians(20)
Rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]]); Ry = np.array([[np.cos(t), 0, np.sin(t)], [0, 1, 0], [-np.sin(t), 0, np.cos(t)]])
B2C = Rz @ Ry   # columns = body axes in Coil coords


def k_take(path, hand):
    rest = np.array([0.5, -0.2, 0.3]); seq = [np.zeros(3), [0.2, 0, 0], np.zeros(3), [0, 0.2, 0], np.zeros(3), [0, 0, 0.2], np.zeros(3)]
    P = []
    for i, off in enumerate(seq):
        tgt = rest + B2C @ np.array(off, float)
        if P: P += list(np.linspace(P[-1], tgt, 15))      # 0.5 s move
        P += [tgt] * 60                                    # 2 s dwell
    P = np.array(P) + np.random.default_rng(0).normal(0, 0.001, (len(P), 3))
    q = np.tile([1.0, 0, 0, 0], (len(P), 1))
    np.savez(path, t=np.arange(len(P)) / 30.0, series="K", **{f"{hand}_wrist_pos": P.astype(np.float32), f"{hand}_wrist_quat": q.astype(np.float32),
             f"{hand}_fingers01": np.zeros((len(P), 5), np.float32)})


def test_calib_from_axes_recovers_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr(arm_ik, "CALIB", str(tmp_path / "arm_calib.json"))
    k_take(tmp_path / "take_90.npz", "right")
    R, lens = arm_ik.calib_from_axes({"right": [90]}, ep_dir=str(tmp_path))
    assert np.allclose(R["right"], B2C.T, atol=0.02)              # rows = body axes in Coil coords
    assert abs(lens["right"]["mean_excursion_m"] - 0.2) < 0.01 and lens["right"]["up_axis_check_deg"] < 2
    assert json.load(open(tmp_path / "arm_calib.json"))["R_coil_to_body"]["right"]


@pytest.mark.parametrize("axis,expect", [(0, 0), (1, 1), (2, 2)])
def test_operator_direction_moves_robot_hand_same_way(axis, expect):
    rig = arm_ik.G1Arms(with_cam=False); p0, R0 = rig.home["right"]
    step = np.zeros(3); step[axis] = 0.10                         # 10 cm along the operator's forward / left / up
    for _ in range(60): rig.solve("right", p0 + step, R0)
    moved = rig.d.xpos[rig.ee["right"]] - p0
    assert np.argmax(np.abs(moved)) == expect and moved[expect] > 0.07
