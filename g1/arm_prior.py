"""Real-G1 posture prior for Coil wrist -> arm IK (data: Tommaso, aalto/spike aalto/data/FOR_GIORGIO.md).

19,371 frames of the REAL G1 driven by the Aalto staff (VR teleop, drops 2+3): measured arm joints + FK wrist poses (pelvis frame,
official URDF). For each Coil wrist target we take the k nearest real wrist poses (position + 5 cm/rad of orientation) and use the
distance-weighted mean of their 7-joint postures as the IK NULL-SPACE target, low-pass filtered so the target never jumps between
neighbours. The IK still tracks the wrist exactly; the prior only decides the redundant degree of freedom (elbow / shoulder roll),
so the arm takes the postures the real robot actually used instead of our hand-picked rest posture.

    prior = RealArmPrior()                       # data/aalto/g1_wrist_arm_pairs.npz
    rest = prior.rest(kin, "right", p_world, R_world, rest)   # per tick, before kin.a.solve(..., q_rest=rest)
"""
import os
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "aalto", "g1_wrist_arm_pairs.npz")


def mat_to_xyzw(R):
    R = np.asarray(R, float); t = np.trace(R)
    if t > 0:
        s = 2 * np.sqrt(t + 1); w = 0.25 * s; x = (R[2, 1] - R[1, 2]) / s; y = (R[0, 2] - R[2, 0]) / s; z = (R[1, 0] - R[0, 1]) / s
    else:
        i = int(np.argmax(np.diag(R)))
        if i == 0:
            s = 2 * np.sqrt(1 + R[0, 0] - R[1, 1] - R[2, 2]); w = (R[2, 1] - R[1, 2]) / s; x = 0.25 * s; y = (R[0, 1] + R[1, 0]) / s; z = (R[0, 2] + R[2, 0]) / s
        elif i == 1:
            s = 2 * np.sqrt(1 + R[1, 1] - R[0, 0] - R[2, 2]); w = (R[0, 2] - R[2, 0]) / s; x = (R[0, 1] + R[1, 0]) / s; y = 0.25 * s; z = (R[1, 2] + R[2, 1]) / s
        else:
            s = 2 * np.sqrt(1 + R[2, 2] - R[0, 0] - R[1, 1]); w = (R[1, 0] - R[0, 1]) / s; x = (R[0, 2] + R[2, 0]) / s; y = (R[1, 2] + R[2, 1]) / s; z = 0.25 * s
    q = np.array([x, y, z, w]); return q / np.linalg.norm(q)


class RealArmPrior:
    def __init__(self, path=DATA, k=8, rot_weight_m=0.05, alpha=0.15, max_dist=0.08, every=3):
        z = np.load(path, allow_pickle=True)
        names = [str(n) for n in z["arm_names"]]
        self.names = {"left": names[:7], "right": names[7:]}
        self.q = {"left": z["arm_q"][:, :7].astype(float), "right": z["arm_q"][:, 7:].astype(float)}
        self.pose = {s: z[f"{s}_wrist"].astype(float) for s in ("left", "right")}
        self.k, self.w, self.alpha, self.max_dist = k, rot_weight_m, alpha, max_dist
        self.filt = {}; self.last_dist = {}; self.dists = {"left": [], "right": []}
        from scipy.spatial import cKDTree                  # position index: 32 candidates, then re-ranked with orientation (fast enough per tick)
        self.tree = {s: cKDTree(self.pose[s][:, :3]) for s in ("left", "right")}
        self.every = every; self.n = {"left": 0, "right": 0}

    def target(self, side, p_pelvis, R=None):
        """distance-weighted mean posture of the k nearest real wrist poses; (q7, nearest distance m)"""
        dpos, cand = self.tree[side].query(np.asarray(p_pelvis, float), k=32)
        d = np.asarray(dpos, float).copy()
        if R is not None:
            qx = mat_to_xyzw(R); d = d + self.w * 2 * np.arccos(np.clip(np.abs(self.pose[side][cand, 3:] @ qx), 0, 1))
        o = np.argsort(d)[:self.k]; idx = cand[o]; w = 1.0 / (d[o] + 0.005)
        return (self.q[side][idx] * w[:, None]).sum(0) / w.sum(), float(d[o].min())

    def rest(self, kin, side, p_world, R_world, rest):
        """rest dict with this side's 7 joints replaced by the (filtered) real posture; outside the demos (> max_dist) -> unchanged"""
        self.n[side] += 1
        if side in self.filt and self.n[side] % self.every:                 # the posture changes slowly: re-query every `every` ticks
            out = dict(rest); out.update({n: float(v) for n, v in zip(self.names[side], self.filt[side])}); return out
        q7, dist = self.target(side, np.asarray(p_world, float) - kin.base, R_world)
        self.last_dist[side] = dist; self.dists[side].append(dist)
        if dist > self.max_dist: return rest
        f = self.filt.get(side); f = q7 if f is None else f + min(1.0, self.alpha * self.every) * (q7 - f); self.filt[side] = f
        out = dict(rest); out.update({n: float(v) for n, v in zip(self.names[side], f)}); return out

    def naturalness(self, kin, side):
        """joint-space distance (rad, RMS over 7 joints) between the solved arm and the real postures at that wrist pose"""
        b = kin.a.ee[side]; q7, _ = self.target(side, kin.a.d.xpos[b] - kin.base, kin.a.d.xmat[b].reshape(3, 3))
        cur = np.array([kin.a.q[n] for n in self.names[side]]); return float(np.sqrt(np.mean((cur - q7) ** 2)))
