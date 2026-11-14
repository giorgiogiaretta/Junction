"""TEMPORARY CI diagnostic (no local python): where does the scripted ideal square rollout lose the cube? Removed before merge."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))
from robot.scene import Scene, GRASP_Z_FOR
from test_replay_square import _scripted_rollout

d = _scripted_rollout(); xyz = np.array(d["xyz"]); grip = np.array(d["grip"]); hz = d["hz"]; half = d["side_m"] / 2
cq = {"BL": (-half, -half), "TL": (-half, half), "TR": (half, half), "BR": (half, -half)}
wrist = np.stack([xyz[:, 0], xyz[:, 1], GRASP_Z_FOR["cube"] + xyz[:, 2]], 1)
sc = Scene("cube", obj_xy=cq["BL"], pedestals=tuple(cq.values()), ped_half=(0.03, 0.03)); sc.place_hand(*wrist[0])
print("tick t  grip | wrist_tgt xyz | hand xyz | obj xyz | force")
for i in range(len(grip)):
    sc.step([float(grip[i])] * 5, tuple(wrist[i]), 1.0 / hz)
    if i % 15 == 0 or (i and grip[i] != grip[i - 1]):
        h, o = sc.hand_pos(), sc.obj_pos()
        print(f"{i:4d} {i / hz:5.2f} {grip[i]:.1f} | {np.round(wrist[i], 3)} | {np.round(h, 3)} | {np.round(o, 3)} | {sc.force:.2f}")
