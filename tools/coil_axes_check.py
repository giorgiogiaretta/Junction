"""Axis-by-axis check of the Coil -> G1 arm chain (g1/coil_chain.py + IK), both hands, normal and MIRRORED Coil hemisphere.

A synthetic operator does one movement at a time (forward, left, up 10 cm; pitch fingers-down, roll, yaw 30 deg), the Coil samples are
generated through a known calibration (and, for the mirrored case, reported at -P as the real right glove was on 15/11), the chain +
IK run exactly as in the simulator / robot policy, and for every movement we measure what the ROBOT wrist did:
  sign  = cosine between the robot motion and the operator motion (+1 = same direction, -1 = inverted)
  gain  = robot amplitude / operator amplitude
  t90   = time for the robot to reach 90 % of its final displacement (s)
PASS = sign > 0.9, gain 0.8-1.2, t90 < 0.5 s.     py -3.11 tools/coil_axes_check.py [--prior] [--fast]
"""
import argparse, os, sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "g1"), os.path.join(ROOT, "g1", "sim")]
import coil_chain as CC, demo_e2e as D, arm_ik
RATE = 30.0


def rotz(a): c, s = np.cos(a), np.sin(a); return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])
def axis_rot(ax, a): return CC.from_rotvec(np.asarray(ax, float) * a)


def moves():
    """(name, operator displacement (fwd, left, up) m, operator rotation vector (rad, operator frame))"""
    A = np.radians(30)
    return [("forward 10 cm", [0.10, 0, 0], [0, 0, 0]), ("left 10 cm", [0, 0.10, 0], [0, 0, 0]), ("up 10 cm", [0, 0, 0.10], [0, 0, 0]),
            ("pitch fingers DOWN 30", [0, 0, 0], [0, A, 0]), ("roll 30 (about forward)", [0, 0, 0], [A, 0, 0]),
            ("yaw 30 (fingers to the left)", [0, 0, 0], [0, 0, A])]


def run(side, mirrored, prior=False, fast=False):
    Rh_true = rotz(np.radians(35)) @ axis_rot([1, 0, 0], np.radians(10))       # some Coil placement (coil frame -> operator rows below)
    Rh_true = Rh_true.T                                                          # rows = forward, left, up in Coil coordinates
    D_ = np.diag([-1.0, -1.0, 1.0])
    CC.UP_SIGN.clear(); CC.Q_NEUTRAL.clear()
    Rh_cal = D_ @ Rh_true if mirrored else Rh_true                               # what seated_calib measures from -P samples
    if mirrored: CC.UP_SIGN[side] = -1                                           # what its last step (up check) finds
    cfg = CC.Cfg()
    if fast: cfg.joint_speed, cfg.vmax, cfg.vfinal, cfg.wfinal = 1.8, 1.3, 1.2, np.radians(400)
    CC.PRIOR = None
    if prior:
        import arm_prior; CC.PRIOR = arm_prior.RealArmPrior()
    kin = D.Kin(); rest = CC.palm_down_rest(kin, D.COUNTER_Z)
    rest_pose = (kin.a.d.xpos[kin.a.ee[side]].copy(), kin.a.d.xmat[kin.a.ee[side]].reshape(3, 3).copy())
    ch = CC.HandChain(side, Rh_cal, rest_pose, None, cfg, kin.base[2] - 0.5)
    P_c = np.array([0.3, -0.2, 0.25]); Q_flat = CC.m2q(axis_rot([0.2, 0.5, 0.8], 0.7))   # any flat-hand sensor orientation
    res = []; t = 0.0; F = np.zeros(5)
    def coil(d_op, rv_op):
        P = P_c + Rh_true.T @ np.asarray(d_op, float)
        Rq = Rh_true.T @ CC.from_rotvec(rv_op) @ Rh_true @ CC.q2m(Q_flat)       # operator-frame rotation delta, in Coil coords
        return (-P if mirrored else P), CC.m2q(Rq)
    def step(d_op, rv_op):
        nonlocal t
        P, Q = coil(d_op, rv_op); arm_ik.ARM_STEP = cfg.joint_speed / RATE
        out = ch.update(F, P, Q, t, np.zeros(3), kin.a.d.xmat[kin.a.ee[side]].reshape(3, 3), wrist_p_now=kin.a.d.xpos[kin.a.ee[side]].copy())
        CC.solve_arm(kin, side, out, cfg, rest, lambda k: [], kin.base[2] - 0.5); t += 1 / RATE
        b = kin.a.ee[side]; return kin.a.d.xpos[b].copy(), kin.a.d.xmat[b].reshape(3, 3).copy()
    for _ in range(int(1.5 * RATE)): step([0, 0, 0], [0, 0, 0])           # flat + still: anchors
    p0, R0 = step([0, 0, 0], [0, 0, 0])
    for name, d_op, rv_op in moves():
        traj = []
        for i in range(int(1.6 * RATE)):                                    # 0.3 s ramp to the pose, then hold
            s = min(1.0, (i + 1) / (0.3 * RATE)); p, R = step(np.array(d_op) * s, np.array(rv_op) * s); traj.append((p, R))
        pf, Rf = traj[-1]
        if np.linalg.norm(d_op) > 0:
            v = pf - p0; ref = np.array(d_op, float); amp = np.array([np.linalg.norm(x[0] - p0) for x in traj])
        else:
            v = CC.rotvec(Rf @ R0.T); ref = np.array(rv_op, float); amp = np.array([np.linalg.norm(CC.rotvec(x[1] @ R0.T)) for x in traj])
        sign = float(v @ ref / (np.linalg.norm(v) * np.linalg.norm(ref) + 1e-9)); gain = float(np.linalg.norm(v) / np.linalg.norm(ref))
        t90 = (int(np.argmax(amp >= 0.9 * amp[-1])) + 1) / RATE if amp[-1] > 1e-6 else 9.9
        ok = sign > 0.9 and 0.8 <= gain <= 1.2 and t90 < 0.5
        res.append((name, sign, gain, t90, ok))
        for _ in range(int(1.6 * RATE)): step([0, 0, 0], [0, 0, 0])         # back to flat
        p0, R0 = step([0, 0, 0], [0, 0, 0])
    return res


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--prior", action="store_true"); ap.add_argument("--fast", action="store_true"); a = ap.parse_args()
    allok = True
    for side in ("right", "left"):
        for mirrored in (False, True):
            print(f"\n== {side} hand, Coil {'MIRRORED (-P)' if mirrored else 'normal'}{', prior' if a.prior else ''}{', fast' if a.fast else ''}")
            for name, sign, gain, t90, ok in run(side, mirrored, a.prior, a.fast):
                allok &= ok
                print(f"  {name:30s} sign {sign:+.2f}  gain {gain:4.2f}  t90 {t90:4.2f} s  {'PASS' if ok else 'FAIL'}")
    print("\nALL PASS" if allok else "\nSOME FAIL")


if __name__ == "__main__":
    main()
