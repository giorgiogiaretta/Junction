"""Glove + Coil Pro wrist pose -> G1 arm joints (7 per arm) by damped-least-squares IK on the official G1 MJCF, plus Dex3 fingers.
  py -3.11 g1/arm_ik.py --take 47 [--hand right|left|both] [--video] [--scale 0.8]
     -> data/g1sim/arm/take_NN.npz (30 Hz arm_q 14 + hand_q 14 = what the runner would receive), take_NN.mp4, take_NN.json (metrics)
Mapping (relative, no absolute registration needed):
  body frame B = operator frame (x forward, y left, z up) obtained from the Coil frame with R_cb (data/arm_calib.json; derived from the
  table corners of series H or, better, from series K 'arm axes' takes), robot hand home pose = forearm forward (as in grasp_physics.py),
  p_robot(t) = p_home + scale * R_cb (p_coil(t) - p_coil(t0)),  R_robot(t) = R_cb R_coil(t) R_coil(t0)^T R_cb^T R_home.
IK: position + 0.3 * orientation error, DLS lambda 0.05, joints clamped to the Aalto FILTER bounds and slew-limited to the arm speed cap
(1.0 rad/s at 30 Hz = 0.033 rad per tick), same caps as the runner's safety filter. Errors from the cap are reported, not hidden.
UNVERIFIED: R_cb from the table is approximate (Coil tilt 12-25 deg), the wrist sensor offset vs the robot wrist frame is ignored
(relative orientation only), no collision avoidance between arms and torso (reported as min distance)."""
import argparse, json, os, sys
import numpy as np, mujoco

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from robot.g1_dex3 import G1Dex3Retargeter

ASSETS = os.path.join(ROOT, "data", "g1sim", "assets_g1", "g1_body29_hand14.xml")
LIM = json.load(open(os.path.join(ROOT, "docs", "g1_dex3_limits.json")))
CALIB = os.path.join(ROOT, "data", "arm_calib.json")
OUT = os.path.join(ROOT, "data", "g1sim", "arm")
RATE = LIM["rate_hz"]; ARM_STEP = LIM["speed_caps_rad_s"]["arm"] / RATE
ARM_NAMES = [j["joint"] for j in LIM["arm_q"]]
FILTER = {j["joint"]: j["filter"] for j in LIM["arm_q"]}
HOME = {"right": {"shoulder_pitch": -0.4, "shoulder_roll": -0.25, "shoulder_yaw": 0.0, "elbow": 0.3, "wrist_roll": -1.57, "wrist_pitch": 0.0, "wrist_yaw": 0.0}}
HOME["left"] = {k: (-v if k in ("shoulder_roll", "shoulder_yaw", "wrist_roll", "wrist_yaw") else v) for k, v in HOME["right"].items()}   # mirror
# Head camera = Intel RealSense D435i, official Unitree URDF (unitree_ros g1_29dof_rev_1_0.urdf, d435_joint): in torso_link at xyz (0.0576, 0.0175, 0.4299),
# pitch 0.8308 rad (47.6 deg down). RGB stream vertical FOV ~42 deg (69x42); depth 87x58, min depth ~0.3-0.4 m (retailer spec).
HEAD_CAM = dict(pos=[0.0576235, 0.01753, 0.42987], pitch=0.8307767239493009, fovy=42.0)


def add_head_cam(spec, name="head_cam"):
    p = HEAD_CAM["pitch"]; fwd = np.array([np.cos(p), 0, -np.sin(p)])          # MuJoCo cameras look along their -z, image up = +y
    cx = np.array([0.0, -1.0, 0.0]); cz = -fwd; cy = np.cross(cz, cx)
    q = np.zeros(4); mujoco.mju_mat2Quat(q, np.stack([cx, cy, cz], 1).flatten())
    spec.body("torso_link").add_camera(name=name, pos=HEAD_CAM["pos"], quat=q, fovy=HEAD_CAM["fovy"])


def quat_wxyz_to_mat(q):
    m = np.zeros(9); mujoco.mju_quat2Mat(m, np.asarray(q, float)); return m.reshape(3, 3)


def rot_err(R_target, R):
    """axis-angle vector rotating R onto R_target (world frame)."""
    q = np.zeros(4); mujoco.mju_mat2Quat(q, (R_target @ R.T).flatten()); v = np.zeros(3); mujoco.mju_quat2Vel(v, q, 1.0); return v


class G1Arms:
    def __init__(self, with_cam=True):
        spec = mujoco.MjSpec.from_file(ASSETS)
        spec.delete(spec.joint("floating_base_joint")); spec.body("pelvis").pos = [0, 0, 0.793]
        if with_cam: add_head_cam(spec)
        self.m = m = spec.compile(); self.d = mujoco.MjData(m)
        m.vis.global_.offwidth, m.vis.global_.offheight = 640, 480
        self.jid = {n: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, n) for n in [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j) for j in range(m.njnt)]}
        self.qadr = {n: m.jnt_qposadr[j] for n, j in self.jid.items()}; self.dadr = {n: m.jnt_dofadr[j] for n, j in self.jid.items()}
        self.ee = {s: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f"{s}_wrist_yaw_link") for s in ("left", "right")}
        self.arm = {s: [n for n in ARM_NAMES if n.startswith(s)] for s in ("left", "right")}
        self.hand_names = [j["joint"] for j in G1Dex3Retargeter().joints]
        self.q = {n: 0.0 for n in ARM_NAMES}
        for s in ("left", "right"):
            for k, v in HOME[s].items(): self.q[f"{s}_{k}_joint"] = v
        self.apply(); self.home = {s: (self.d.xpos[self.ee[s]].copy(), self.d.xmat[self.ee[s]].reshape(3, 3).copy()) for s in ("left", "right")}

    def apply(self, hand_q=None):
        for n, v in self.q.items(): self.d.qpos[self.qadr[n]] = v
        if hand_q is not None:
            for n, v in zip(self.hand_names, hand_q): self.d.qpos[self.qadr[n]] = v
        mujoco.mj_kinematics(self.m, self.d); mujoco.mj_comPos(self.m, self.d)

    def solve(self, side, p_t, R_t, iters=12, w_rot=0.3, lam=0.05):
        """DLS from the current solution; per-tick joint change clamped to ARM_STEP, joints to FILTER bounds. Returns (pos err m, rot err rad)."""
        m, d, names = self.m, self.d, self.arm[side]; dofs = [self.dadr[n] for n in names]
        q0 = np.array([self.q[n] for n in names]); q = q0.copy()
        jp, jr = np.zeros((3, m.nv)), np.zeros((3, m.nv))
        for _ in range(iters):
            ep = p_t - d.xpos[self.ee[side]]; er = rot_err(R_t, d.xmat[self.ee[side]].reshape(3, 3))
            mujoco.mj_jacBody(m, d, jp, jr, self.ee[side])
            J = np.vstack([jp[:, dofs], w_rot * jr[:, dofs]]); e = np.concatenate([ep, w_rot * er])
            dq = J.T @ np.linalg.solve(J @ J.T + lam ** 2 * np.eye(6), e)
            q = np.clip(q + dq, q0 - ARM_STEP, q0 + ARM_STEP)
            q = np.array([np.clip(v, *FILTER[n]) for v, n in zip(q, names)])
            for n, v in zip(names, q): self.q[n] = float(v)
            self.apply()
        return float(np.linalg.norm(p_t - d.xpos[self.ee[side]])), float(np.linalg.norm(rot_err(R_t, d.xmat[self.ee[side]].reshape(3, 3))))

    def arm_q(self): return [self.q[n] for n in ARM_NAMES]

    def min_clearance(self):
        """Smallest distance between an arm/hand geom and the torso/pelvis/legs or the other arm (m); < 0 = collision."""
        mujoco.mj_forward(self.m, self.d); best = 1.0
        for c in self.d.contact[:self.d.ncon]: best = min(best, c.dist)
        return best


def load_calib(path=CALIB):
    if os.path.exists(path):
        c = json.load(open(path)); return {h: np.array(R) for h, R in c["R_coil_to_body"].items()}, c
    return None, None


def calib_from_square(fit_path=os.path.join(ROOT, "data", "square_fit.json")):
    """Operator frame from the series H table corners (Coil frame), PER HAND (the left and right sessions differ by ~90 deg about z:
    the Coil or the corner labelling was rotated between them): forward = BL->TL, left = BR->BL, up = forward x left, averaged over takes."""
    fit = json.load(open(fit_path)); acc = {}
    for e in fit.values():
        c = {k: np.array(v) for k, v in e["corners"].items()}
        F, L = acc.setdefault(e["hand"], ([], []))
        F.append(c["TL"] - c["BL"] + c["TR"] - c["BR"]); L.append(c["BL"] - c["BR"] + c["TL"] - c["TR"])
    out = {}
    for h, (F, L) in acc.items():
        f = np.mean(F, 0); f /= np.linalg.norm(f); l = np.mean(L, 0); l -= f * (l @ f); l /= np.linalg.norm(l)
        out[h] = np.stack([f, l, np.cross(f, l)])   # rows = body axes in Coil coordinates: R @ v_coil = v_body
    json.dump({"R_coil_to_body": {h: R.round(5).tolist() for h, R in out.items()}, "source": "series H table corners (square_fit.json), per hand, approximate",
               "n_takes": {h: len(v[0]) for h, v in acc.items()}}, open(CALIB, "w"), indent=1)
    return out


def calib_from_axes(takes_by_hand, ep_dir=os.path.join(ROOT, "data", "episodes")):
    """Series K 'arm axes' takes (Rokoko/src/take.py): rest -> forward 20 cm -> rest -> left 20 cm -> rest -> up 20 cm -> rest, 2 s dwell each.
    Dwell centres (speed < 5 cm/s for > 0.5 s) farther than 8 cm from the rest pose, in time order = forward, left, up.
    Writes per-hand R_coil_to_body (rows = forward, left, up in Coil coordinates, Gram-Schmidt) and the measured 20 cm lengths."""
    out, lens = {}, {}
    for h, takes in takes_by_hand.items():
        F, L, U, ln = [], [], [], []
        for tk in takes:
            z = np.load(os.path.join(ep_dir, f"take_{tk:02d}.npz")); P = z[f"{h}_wrist_pos"].astype(float); ok = ~np.isnan(P).any(1)
            Ps = np.array(P); Ps[~ok] = 0
            k = np.ones(9) / 9; Ps = np.stack([np.convolve(Ps[:, c], k, mode="same") for c in range(3)], 1)   # smooth sensor noise before speed
            v = np.r_[0, np.linalg.norm(np.diff(Ps, axis=0), axis=1) * RATE]; slow = ok & (v < 0.05)
            segs, i = [], 0
            while i < len(P):
                if slow[i]:
                    j = i
                    while j < len(P) and slow[j]: j += 1
                    if j - i > 0.5 * RATE: segs.append(np.median(P[i:j], 0))
                    i = j
                else: i += 1
            if len(segs) < 4: print(f"[calib] take {tk}: only {len(segs)} dwells, skipped"); continue
            rest = segs[0]; far = [s - rest for s in segs if np.linalg.norm(s - rest) > 0.08]
            if len(far) < 3: print(f"[calib] take {tk}: {len(far)} excursions (need forward, left, up), skipped"); continue
            F.append(far[0]); L.append(far[1]); U.append(far[2]); ln += [float(np.linalg.norm(x)) for x in far[:3]]
        if not F: continue
        f = np.mean(F, 0); f /= np.linalg.norm(f); l = np.mean(L, 0); l -= f * (l @ f); l /= np.linalg.norm(l); u = np.cross(f, l)
        u_meas = np.mean(U, 0); u_meas /= np.linalg.norm(u_meas)
        out[h] = np.stack([f, l, u]); lens[h] = {"mean_excursion_m": round(float(np.mean(ln)), 3), "up_axis_check_deg": round(float(np.degrees(np.arccos(np.clip(u @ u_meas, -1, 1)))), 1)}
    if out:
        json.dump({"R_coil_to_body": {h: R.round(5).tolist() for h, R in out.items()}, "source": f"series K arm axes {takes_by_hand}", "check": lens}, open(CALIB, "w"), indent=1)
    return out, lens


def replay(take, hands=("right",), scale=0.8, video=False, out=OUT, max_closure=None):
    z = np.load(os.path.join(ROOT, "data", "episodes", f"take_{take:02d}.npz"), allow_pickle=True)
    R_all, cal = load_calib()
    if R_all is None: R_all = calib_from_square()
    rig = G1Arms(with_cam=video); rt = G1Dex3Retargeter(max_closure=max_closure); n = len(z["t"])
    have = {s: f"{s}_wrist_quat" in z.files and not np.isnan(z[f"{s}_wrist_pos"]).all() for s in hands}
    if not all(have.values()): raise SystemExit(f"take {take}: missing wrist pose/quat for {[s for s, h in have.items() if not h]} (re-run Rokoko/src/episodes.py; needs the Coil)")
    ref = {}
    for s in hands:
        P, Q = z[f"{s}_wrist_pos"].astype(float), z[f"{s}_wrist_quat"].astype(float)
        i0 = int(np.argmax(~np.isnan(P).any(1) & ~np.isnan(Q).any(1)))
        ref[s] = (P[i0], quat_wxyz_to_mat(Q[i0]))
    arm, hand, perr, rerr, clear, capped = [], [], {s: [] for s in hands}, {s: [] for s in hands}, [], 0
    frames = []
    if video:
        rend = mujoco.Renderer(rig.m, 480, 640); cam3 = mujoco.MjvCamera(); cam3.type = mujoco.mjtCamera.mjCAMERA_FREE
        cam3.lookat[:] = [0.3, 0, 1.0]; cam3.distance, cam3.azimuth, cam3.elevation = 1.6, 150, -15
    for i in range(n):
        q_before = np.array(rig.arm_q())
        for s in hands:
            p, q = z[f"{s}_wrist_pos"][i].astype(float), z[f"{s}_wrist_quat"][i].astype(float)
            if np.isnan(p).any() or np.isnan(q).any(): continue        # Coil dropout: hold the last pose
            ph, Rh = rig.home[s]; p0, R0 = ref[s]; R_cb = R_all[s]
            p_t = ph + scale * R_cb @ (p - p0)
            R_t = R_cb @ quat_wxyz_to_mat(q) @ R0.T @ R_cb.T @ Rh
            e_p, e_r = rig.solve(s, p_t, R_t); perr[s].append(e_p); rerr[s].append(e_r)
        if np.any(np.abs(np.array(rig.arm_q()) - q_before) > ARM_STEP - 1e-6): capped += 1
        L = z["left_fingers01"][i] if "left" in hands and "left_fingers01" in z.files else None
        Rf = z["right_fingers01"][i] if "right" in hands and "right_fingers01" in z.files else None
        hq = rt.step(left=L, right=Rf); rig.apply(hq)
        arm.append(rig.arm_q()); hand.append(hq)
        if i % 3 == 0: clear.append(rig.min_clearance())
        if video:
            rend.update_scene(rig.d, cam3); a = rend.render().copy()
            rend.update_scene(rig.d, "head_cam"); b = rend.render().copy(); frames.append(np.concatenate([a, b], 1))
    os.makedirs(out, exist_ok=True); base = os.path.join(out, f"take_{take:02d}")
    np.savez_compressed(base + ".npz", t=z["t"], arm_q=np.array(arm, np.float32), hand_q=np.array(hand, np.float32), arm_names=np.array(ARM_NAMES))
    met = {"take": take, "max_closure": rt.max_closure, "series": str(z["series"]), "hands": list(hands), "frames": n, "scale": scale, "calib": (cal or {}).get("source", "square_fit (just derived)"),
           "pos_err_cm": {s: {"median": round(100 * float(np.median(v)), 1), "p95": round(100 * float(np.percentile(v, 95)), 1)} for s, v in perr.items() if v},
           "rot_err_deg": {s: {"median": round(float(np.degrees(np.median(v))), 1), "p95": round(float(np.degrees(np.percentile(v, 95))), 1)} for s, v in rerr.items() if v},
           "ticks_at_speed_cap_pct": round(100 * capped / max(n, 1), 1), "min_clearance_cm": (round(100 * float(min(clear)), 1) if clear and min(clear) < 1.0 else "no contact"),
           "arm_q_in_filter": bool(all(FILTER[nm][0] - 1e-9 <= v <= FILTER[nm][1] + 1e-9 for row in arm for nm, v in zip(ARM_NAMES, row)))}
    json.dump(met, open(base + ".json", "w"), indent=1)
    if video and frames:
        import cv2
        w = cv2.VideoWriter(base + ".mp4", cv2.VideoWriter_fourcc(*"mp4v"), RATE, (frames[0].shape[1], frames[0].shape[0]))
        for f in frames: w.write(f[:, :, ::-1])
        w.release()
    return met


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--take", type=int, required=True); ap.add_argument("--hand", default="auto"); ap.add_argument("--scale", type=float, default=0.8)
    ap.add_argument("--video", action="store_true"); ap.add_argument("--recalib", action="store_true", help="re-derive data/arm_calib.json from square_fit.json")
    a = ap.parse_args()
    if not os.path.exists(ASSETS): sys.exit("run g1/sim/g1_sim.py once to fetch the G1 model")
    if a.recalib: calib_from_square()
    if a.hand == "auto":
        idx = {e["take"]: e for e in json.load(open(os.path.join(ROOT, "data", "episodes", "index.json")))}
        hands = (idx[a.take]["active_hand"],)
    else: hands = ("left", "right") if a.hand == "both" else (a.hand,)
    print(json.dumps(replay(a.take, hands, a.scale, a.video), indent=1))


if __name__ == "__main__":
    main()
