"""Nearest real posture for a wrist target: 7 arm joints the real G1 actually used near that wrist pose.

Use it as the IK seed (or as the answer when the match is close enough) when a Coil / glove gives a wrist pose.
Pure numpy; data = g1_wrist_arm_pairs.npz (see wrist_arm_pairs.py and FOR_GIORGIO.md).

    from knn_arm_seed import ArmPrior
    prior = ArmPrior("aalto/data/g1_wrist_arm_pairs.npz")
    q7, dist_m = prior.seed("left", pos=[0.30, 0.15, 0.15])                       # position only
    q7, dist_m = prior.seed("right", pos=[0.30, -0.15, 0.15], quat=[0, 0, 0, 1])  # + orientation (x y z w)
"""
from __future__ import annotations

import numpy as np


class ArmPrior:
    def __init__(self, path, frame="wrist", rot_weight_m=0.05):
        z = np.load(path)
        self.q = {"left": z["arm_q"][:, :7].astype(np.float64), "right": z["arm_q"][:, 7:].astype(np.float64)}
        self.pose = {s: z[f"{s}_{frame}"].astype(np.float64) for s in ("left", "right")}
        self.w = float(rot_weight_m)   # 1 rad of orientation error costs as much as this many metres

    def seed(self, side, pos, quat=None, k=1):
        P = self.pose[side]
        d = np.linalg.norm(P[:, :3] - np.asarray(pos, float), axis=1)
        if quat is not None:
            q = np.asarray(quat, float) / np.linalg.norm(quat)
            ang = 2 * np.arccos(np.clip(np.abs(P[:, 3:] @ q), 0, 1))   # geodesic angle, sign-invariant
            d = d + self.w * ang
        idx = np.argsort(d)[:k]
        q7 = self.q[side][idx].mean(0) if k > 1 else self.q[side][idx[0]]
        return q7, float(d[idx[0]])


if __name__ == "__main__":
    import sys
    p = ArmPrior(sys.argv[1] if len(sys.argv) > 1 else "g1_wrist_arm_pairs.npz")
    for side, pos in (("left", [0.30, 0.15, 0.15]), ("right", [0.30, -0.15, 0.15]), ("left", [0.25, 0.20, 0.30])):
        q7, dm = p.seed(side, pos)
        print(side, pos, "->", np.round(q7, 3), f"(nearest real wrist {100 * dm:.1f} cm away)")
