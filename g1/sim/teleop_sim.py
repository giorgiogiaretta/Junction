"""Full teleoperation in simulation: BOTH Rokoko gloves + Coil Pro -> BOTH G1 arms (7 DoF IK, natural posture) and BOTH Dex3 hands,
head camera finds the object, grasp ASSIST near the object. The same chain planned for the real robot.
  py -3.11 g1/sim/teleop_sim.py --obj egg                      # live: driver running, gloves + Coil
  py -3.11 g1/sim/teleop_sim.py --obj egg --replay 77          # recorded take (one hand)
  options: --hands both|right|left  --spot 0.35,-0.15  --scale 0.8  --no-assist  --cam
Keys in the camera window (--cam): C = re-centre (clutch: your current hands = robot home pose), Q = quit.
How it works
- Arms: wrist position + orientation from the Coil, rotated into your body frame (data/arm_calib.json, series K; the Coil frame is the same
  for both gloves, so one calibration serves both hands), relative to the re-centre moment, scaled 0.8, on top of the organisers' home pose.
  IK = damped least squares + null-space pull toward the home posture (elbow down, no twisted wrist), 1 rad/s joint cap, URDF filter bounds,
  counter keep-out and workspace box for both wrists/palms (a step that would break them is not sent).
- Grasp assist: when a hand's pinch is within 7 cm of where the HEAD CAMERA sees the object and you start closing, the hand is pulled to the
  object's grasp pose (grasp_postures.json; mirrored for the left hand). Once the grip is closed the offset is frozen, so the object then
  follows YOUR hand freely (lift, move, place). Opening releases and the offset fades in 1 s.
- Fingers: robot closure = object cap x (your grip / your usual grip on that object), 3 rad/s cap.
NOT verified: left-hand grasp postures (mirrored from the right), calibration of the left glove, real latency of the Coil stream."""
import argparse, json, os, sys, time
import numpy as np, mujoco, cv2

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "g1")); sys.path.insert(0, os.path.join(ROOT, "Rokoko", "src"))
import demo_e2e as D, perceive as PC, arm_ik
from robot.g1_dex3 import G1Dex3Retargeter
from live_sim import GloveLive
from teleop_filters import OneEuro, QuatFilter, Deadband

RATE = 30
CLEAR = 0.10
WRIST_MAX_DEG = 70.0
SNAP_XY, SNAP_Z, SNAP_DEG = 0.02, 0.03, 35.0   # soft mode: the reliable grasp takes over only this close to the grasp pose (and your hand ~aligned)
VMAX = 0.35              # m/s, robot hand target speed limit (calm, continuous)
WRIST_ON_TABLE = 0.06    # robot wrist height above the counter when your wrist sensor rests on your table (hand flat)
MIRROR = {"shoulder_roll", "shoulder_yaw", "wrist_roll", "wrist_yaw"}


def side_q(posture_right, side):
    q = {}
    for n, v in posture_right.items():
        k = n.replace("right_", "").replace("_joint", "")
        q[f"{side}_{k}_joint"] = -v if (side == "left" and k in MIRROR) else v
    return q


def tip(kin, name):
    return kin.tip(name)


def pinch(kin, side):
    return 0.5 * (tip(kin, f"{side}_hand_thumb_2_link") + 0.5 * (tip(kin, f"{side}_hand_index_1_link") + tip(kin, f"{side}_hand_middle_1_link")))


def palm(kin, side):
    b = kin.a.ee[side]; off = np.array([0.0415, 0.003 if side == "left" else -0.003, 0.0])
    return kin.a.d.xpos[b] + kin.a.d.xmat[b].reshape(3, 3) @ off


def unsafe(kin):
    r = []
    for side in ("left", "right"):
        for nm, p in (("wrist", kin.pel(kin.a.d.xpos[kin.a.ee[side]])), ("palm", kin.pel(palm(kin, side)))):
            B, K = D.BOX, D.KEEP
            if not (B["x"][0] <= p[0] <= B["x"][1] and B["y"][0] <= p[1] <= B["y"][1] and B["z"][0] <= p[2] <= B["z"][1]): r.append(f"{side}_{nm}_box")
            if K["x"][0] <= p[0] <= K["x"][1] and K["y"][0] <= p[1] <= K["y"][1] and p[2] < K["z"]: r.append(f"{side}_{nm}_counter")
    r += [f"self:{a}-{b}" for a, b, _ in kin.a.self_collisions()]       # arm vs torso / other arm / legs (not in the organisers' filter)
    return r


class Replay:
    def __init__(self, take):
        self.z = np.load(os.path.join(ROOT, "data", "episodes", f"take_{take:02d}.npz")); self.t0 = time.time()
        self.hands = [h for h in ("left", "right") if f"{h}_fingers01" in self.z.files and f"{h}_wrist_quat" in self.z.files]

    def read(self, h):
        if h not in self.hands: return None
        i = min(int((time.time() - self.t0) * RATE), len(self.z["t"]) - 1)
        return self.z[f"{h}_fingers01"][i].astype(float), self.z[f"{h}_wrist_pos"][i].astype(float), self.z[f"{h}_wrist_quat"][i].astype(float)


def grasp_pose(obj, side, seen, rest):
    """wrist target pos/rot for grasping `obj` at `seen` with `side` (right posture from grasp_postures.json, mirrored for the left)"""
    bg = D.best_grasp(obj)
    if not bg: return None
    posture, aim, _ = bg; pr = D.PROFILE[obj]
    k = D.Kin(); rt = G1Dex3Retargeter(max_closure=1.0)
    for _ in range(30): hq = rt.step(left=[0.5 * pr["cap"]] * 3 + [0, 0], right=[0.5 * pr["cap"]] * 3 + [0, 0])
    for n, v in side_q(posture, side).items(): k.a.q[n] = v
    k.a.apply(hq); ee = k.a.ee[side]
    aim_s = aim * (np.array([1, -1, 1]) if side == "left" else 1)
    return k.a.d.xpos[ee] + (seen + aim_s - pinch(k, side)), k.a.d.xmat[ee].reshape(3, 3).copy(), seen + aim_s


def table_calib(readers, hands):
    """Per-hand TABLE calibration (~25 s per hand, beeps): hand FLAT on your table at the centre spot, slide 20 cm forward, back to centre,
    slide 20 cm left. Gives, per hand: axes (forward, left, up), the table height and the centre point = where the robot hand meets the
    object spot on its mat. Saved in data/arm_calib.json under "hands"."""
    try:
        import winsound; beep = lambda f=880: winsound.Beep(f, 150)
    except Exception: beep = lambda f=880: None
    out = {}
    for h in hands:
        def hold(msg, secs=2.5):
            print(f"[calib {h}] {msg}", flush=True); beep(); time.sleep(1.0); P, Qs = [], []
            t0 = time.time()
            while time.time() - t0 < secs:
                s_ = readers[h]()
                if s_ and s_[1] is not None and not np.isnan(s_[1]).any(): P.append(np.asarray(s_[1], float)); Qs.append(np.asarray(s_[2], float))
                time.sleep(1 / RATE)
            if len(P) < 10: raise SystemExit(f"[calib] no Coil position from the {h} glove: is it on and seen by the Coil?")
            k = len(P) // 2; return np.median(np.array(P[k:]), 0), np.array(Qs[-1])
        c, qc = hold(f"mano {'DESTRA' if h == 'right' else 'SINISTRA'} PIATTA sul tavolo, nel punto di partenza davanti a te, FERMA")
        f, _ = hold("SCORRI la mano AVANTI di 20 cm sul tavolo (dritto) e FERMA", 3.0)
        hold("torna al punto di partenza", 2.0)
        l, _ = hold("SCORRI la mano a SINISTRA di 20 cm sul tavolo (dritto) e FERMA", 3.0)
        f, l = f - c, l - c
        if min(np.linalg.norm(f), np.linalg.norm(l)) < 0.10: raise SystemExit(f"[calib {h}] movements too small (need ~20 cm): run again")
        fu, lu = f / np.linalg.norm(f), l / np.linalg.norm(l); ang = float(np.degrees(np.arccos(np.clip(fu @ lu, -1, 1))))
        if not 70 <= ang <= 110: raise SystemExit(f"[calib {h}] forward/left {ang:.0f} deg apart (need 70-110): straighter moves, run again (nothing saved)")
        u = np.cross(fu, lu); u /= np.linalg.norm(u); f2 = fu + np.cross(lu, u); f2 /= np.linalg.norm(f2); l2 = np.cross(u, f2)
        R = np.stack([f2, l2, u]); meas = float(np.mean([np.linalg.norm(f), np.linalg.norm(l)]))
        out[h] = {"R": R.round(5).tolist(), "origin": c.round(4).tolist(), "q_origin": qc.round(5).tolist(), "angle_deg": round(ang, 1), "measured_20cm_as_cm": round(100 * meas, 1)}
        print(f"[calib {h}] ok: forward-left {ang:.0f} deg, your 20 cm measured as {100 * meas:.1f} cm", flush=True); beep(1200)
    calj = json.load(open(arm_ik.CALIB)) if os.path.exists(arm_ik.CALIB) else {}
    calj.setdefault("hands", {}).update(out); calj["R_coil_to_body"] = {h: v["R"] for h, v in calj["hands"].items()}; calj["manual"] = True
    json.dump(calj, open(arm_ik.CALIB, "w"), indent=1)


def live_calib(read, hand):
    """10 s guided axis calibration with the CURRENT Coil placement: rest 2 s, forward 20 cm 2 s, back, left 20 cm 2 s.
    Rows = forward, left, up in Coil coordinates (same Coil frame for both gloves). Saved to data/arm_calib.json (both hands)."""
    try:
        import winsound; beep = lambda f=880: winsound.Beep(f, 150)
    except Exception: beep = lambda f=880: None
    def hold(msg, secs=2.5):
        print(f"[calib] {msg}", flush=True); beep(); time.sleep(0.8); P = []
        t0 = time.time()
        while time.time() - t0 < secs:
            s = read(hand)
            if s and s[1] is not None and not np.isnan(s[1]).any(): P.append(np.asarray(s[1], float))
            time.sleep(1 / RATE)
        if len(P) < 10: raise SystemExit(f"[calib] no Coil position from the {hand} glove")
        P = np.array(P); return np.median(P[len(P) // 2:], 0)
    tb = hold("mano APPOGGIATA PIATTA sul tavolo")
    r0 = hold("mano FERMA davanti al petto"); f = hold("AVANTI 20 cm in linea retta e FERMA", 3.0) - r0
    hold("torna al centro"); l = hold("SINISTRA 20 cm in linea retta e FERMA", 3.0) - r0
    if min(np.linalg.norm(f), np.linalg.norm(l)) < 0.08: raise SystemExit("[calib] movements too small (need ~20 cm): run again")
    f /= np.linalg.norm(f); l /= np.linalg.norm(l); ang = float(np.degrees(np.arccos(np.clip(f @ l, -1, 1))))
    if not 70 <= ang <= 110: raise SystemExit(f"[calib] forward and left are {ang:.0f} deg apart (need 70-110): move straighter and run again (nothing saved)")
    u = np.cross(f, l); u /= np.linalg.norm(u); f2 = f + np.cross(l, u); f2 /= np.linalg.norm(f2); l2 = np.cross(u, f2)
    R = np.stack([f2, l2, u]).round(5).tolist()
    table_up = float((np.array(R) @ tb)[2])
    json.dump({"R_coil_to_body": {"right": R, "left": R}, "table_up": table_up, "source": f"teleop_sim live calibration ({hand} glove), forward-left {ang:.0f} deg", "manual": True},
              open(arm_ik.CALIB, "w"), indent=1)
    print(f"[calib] saved: forward-left angle {ang:.0f} deg (90 ideal; < 70 or > 110 = redo with straighter moves)", flush=True); beep(1200)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--obj", default="egg", choices=list(D.OBJECTS)); ap.add_argument("--replay", type=int)
    ap.add_argument("--hands", default="both", choices=["both", "right", "left"]); ap.add_argument("--spot", default="0.35,-0.15")
    ap.add_argument("--zoff", type=float, default=0.10, help="m: your wrist height above the table at the moment you grasp (sensor above the hand)"); ap.add_argument("--gain", type=float, default=1.0, help="table mapping gain (1.0 = your 10 cm are the robot's 10 cm)"); ap.add_argument("--scale", type=float, default=0.6, help="your motion x scale (0.6 = calmer and more precise)"); ap.add_argument("--smooth", type=float, default=0.7, help="One Euro min cutoff Hz: lower = smoother/slower"); ap.add_argument("--no-assist", action="store_true"); ap.add_argument("--assist", default="soft", choices=["soft", "strong"], help="soft: max 3 cm correction near the object; strong: staged auto-approach"); ap.add_argument("--rotate-held", action="store_true", help="the held object also follows your wrist rotation (default: grasp orientation kept, more stable)"); ap.add_argument("--cam", action="store_true")
    ap.add_argument("--headless", action="store_true"); ap.add_argument("--calib", action="store_true", help="10 s axis calibration at start (do it whenever the Coil moved)"); ap.add_argument("--seconds", type=float, default=900)
    a = ap.parse_args(); obj = a.obj; pr = D.PROFILE[obj]; spot = [float(x) for x in a.spot.split(",")]
    hands = ["left", "right"] if a.hands == "both" else [a.hands]
    if a.calib and not a.replay:
        gs = {h: GloveLive(h) for h in hands}; table_calib({h: gs[h].read for h in hands}, hands)
        for g0 in gs.values(): g0.s.close()
    calj = json.load(open(arm_ik.CALIB)); cal = calj["R_coil_to_body"]; table_up = calj.get("table_up"); R_cb = {h: np.array(cal.get(h, cal.get("right"))) for h in ("left", "right")}
    TC = calj.get("hands", {})                                      # per-hand table calibration (absolute 1:1 mapping) if present
    # scene: G1 + counter + object + floor
    m, d = D.build(obj); spec_floor = None
    names = [j["joint"] for j in G1Dex3Retargeter().joints]
    act = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, m.actuator_trnid[i, 0]): i for i in range(m.nu)}
    jq = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j): m.jnt_qposadr[j] for j in range(m.njnt)}
    ob = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "obj"); oa = m.jnt_qposadr[m.body_jntadr[ob]]; og = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "obj_g")
    kin = D.Kin(); rest = dict(kin.a.q)
    for n, v in kin.a.q.items(): d.qpos[jq[n]] = v; d.ctrl[act[n]] = v
    obj_c = kin.base + np.array([spot[0], spot[1], D.COUNTER_Z + D.half_h(obj)])
    d.qpos[oa:oa + 3] = obj_c; d.qpos[oa + 3:oa + 7] = D.obj_quat(obj); mujoco.mj_forward(m, d)
    rgb, dep, mk = PC.render_head(m, d, seg_geom=og)
    seen, info = PC.locate(rgb, dep, PC.cam_pose(m, d), obj, D.OBJECTS[obj]["size"][0], z_plane=obj_c[2], mask=mk)
    print(f"[camera] {obj}: " + ("NOT seen" if seen is None else f"seen at {np.round(seen - kin.base, 3)} (pelvis), error {100 * np.linalg.norm((seen - obj_c)[:2]):.1f} cm"), flush=True)
    G = {h: (grasp_pose(obj, h, seen, rest) if seen is not None and not a.no_assist else None) for h in hands}
    home = {h: (kin.a.d.xpos[kin.a.ee[h]].copy(), kin.a.d.xmat[kin.a.ee[h]].reshape(3, 3).copy()) for h in ("left", "right")}
    src = Replay(a.replay) if a.replay else None
    if src is not None and seen is not None:
        # replay only: shift the robot home so that, at the operator's grasp moment, the pinch is 4 cm from the seen object
        # (live, YOU aim by watching the simulation; a recorded take was made with the object elsewhere)
        for h in [x for x in hands if x in src.hands]:
            z = src.z; F = z[f"{h}_fingers01"]; P = z[f"{h}_wrist_pos"].astype(float); Q = z[f"{h}_wrist_quat"].astype(float)
            g_ = 0.5 * (F[:, 1] + F[:, 2]); gh = int(np.argmax(g_ >= 0.9 * pr["g_ref"]))
            k2 = D.Kin(); p_t = home[h][0] + a.scale * R_cb[h] @ (P[gh] - P[0])
            R_t = R_cb[h] @ arm_ik.quat_wxyz_to_mat(Q[gh]) @ arm_ik.quat_wxyz_to_mat(Q[0]).T @ R_cb[h].T @ home[h][1]
            for _ in range(150): k2.a.solve(h, p_t, R_t, q_rest=rest)
            sh = seen + np.array([0, 0, 0.04]) - pinch(k2, h)
            home[h] = (home[h][0] + sh, home[h][1]); print(f"[replay] {h} home shifted {np.round(100 * sh, 1)} cm so the take meets the object", flush=True)
    gl = {} if a.replay else {h: GloveLive(h) for h in hands}
    read = (lambda h: src.read(h)) if src else (lambda h: gl[h].read())
    rt = G1Dex3Retargeter(max_closure=float(os.environ.get("G1_MAX_CLOSURE", "1.0")))
    anchor, base_R, last_t, shift = {}, {}, {}, {h: np.zeros(3) for h in hands}
    for h in hands:                                                 # robot wrist pose with its pinch on the object spot (left spot mirrored)
        sp = kin.base + np.array([spot[0], spot[1] if h == "right" else -spot[1], D.COUNTER_Z + D.half_h(obj)])
        gpose = grasp_pose(obj, h, sp, rest) if D.best_grasp(obj) else None
        anchor[h], base_R[h] = (gpose[0], gpose[1]) if gpose is not None else (home[h][0], home[h][1])
    PF = {h: OneEuro(freq=RATE, min_cutoff=a.smooth, beta=0.02) for h in hands}; QF = {h: QuatFilter(freq=RATE, min_cutoff=a.smooth, beta=0.02) for h in hands}
    DB = {h: Deadband(0.003) for h in hands}
    ref = {}; stage = {h: None for h in hands}; t_st = {h: 0.0 for h in hands}; rel_p = {}; lock = {h: None for h in hands}
    APPR = {}
    for h in hands:                                             # approach direction: from above (egg, ball) or from the palm side (can)
        if G.get(h) is None: APPR[h] = np.array([0, 0, 1.0]); continue
        v = G[h][0] - G[h][2]; v[2] = 0
        APPR[h] = v / (np.linalg.norm(v) + 1e-9) if D.SIDE_APPROACH.get(obj) else np.array([0, 0, 1.0]); fade = {h: 0.0 for h in hands}; cmd_f = {h: 0.0 for h in hands}
    viewer = None
    if not a.headless:
        from mujoco import viewer as mjv
        viewer = mjv.launch_passive(m, d)
    rend = mujoco.Renderer(m, 240, 320) if a.cam else None
    spt = int(round(1 / RATE / m.opt.timestep)); f6 = np.zeros(6); t_start = time.time(); tick = 0
    hb = {b for b in range(m.nbody) if "_hand_" in (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, b) or "")}
    blocked = 0; ghost = {}; raw_last = {}
    while time.time() - t_start < a.seconds and (viewer is None or viewer.is_running()):
        t_tick = time.time(); fingers = {"left": None, "right": None}; status = []
        for h in hands:
            s = read(h)
            if s is None or s[1] is None or s[2] is None or np.isnan(s[1]).any() or np.isnan(s[2]).any():
                status.append(f"{h}: no Coil pose"); continue
            F, P, Q = s; g = 0.5 * (F[1] + F[2])
            if h not in ref: ref[h] = (P.copy(), arm_ik.quat_wxyz_to_mat(Q))      # clutch: first valid sample = robot home pose
            raw_last[h] = np.asarray(P, float).copy()
            P = DB[h](PF[h](P, t_tick)); Q = QF[h](Q, t_tick)                      # One Euro on position + rotation, 3 mm deadband: no tremor, no jumps
            if h in TC and not a.replay:                      # ABSOLUTE: your table centre = robot hand on its object spot, 1:1, table = counter
                T = TC[h]; Rh_ = np.array(T["R"]); rel = Rh_ @ (P - np.array(T["origin"])) + shift[h]
                rel[2] -= a.zoff                                  # your wrist sensor sits ~6 cm above the table when you pinch the egg (takes 75-79)
                p_tel = anchor[h] + a.gain * rel
                R_rel = Rh_ @ arm_ik.quat_wxyz_to_mat(Q) @ arm_ik.quat_wxyz_to_mat(np.array(T["q_origin"])).T @ Rh_.T
            else:
                p_tel = home[h][0] + a.scale * R_cb[h] @ (P - ref[h][0])
                R_rel = None
            if table_up is not None and h not in TC:                          # YOUR table = the robot's counter: height mapped 1:1 from the table plane
                p_tel[2] = kin.base[2] + D.COUNTER_Z + WRIST_ON_TABLE + float((R_cb[h] @ P)[2]) - table_up
            if R_rel is None: R_rel = R_cb[h] @ arm_ik.quat_wxyz_to_mat(Q) @ ref[h][1].T @ R_cb[h].T
            rv = np.zeros(3); qq = np.zeros(4); mujoco.mju_mat2Quat(qq, R_rel.flatten()); mujoco.mju_quat2Vel(rv, qq, 1.0)
            ang = np.linalg.norm(rv)
            if ang > np.radians(WRIST_MAX_DEG):              # a human wrist does not rotate more than ~70 deg from the reference
                rv *= np.radians(WRIST_MAX_DEG) / ang; mujoco.mju_quatIntegrate(qq0 := np.array([1.0, 0, 0, 0]), rv, 1.0); R_rel = arm_ik.quat_wxyz_to_mat(qq0)
            R_tel = R_rel @ (base_R[h] if h in TC and not a.replay else home[h][1])
            dp = p_tel - last_t.get(h, p_tel); nrm = np.linalg.norm(dp)        # Cartesian speed limit: smooth, continuous robot motion
            if nrm > VMAX / RATE: p_tel = last_t[h] + dp * (VMAX / RATE) / nrm
            last_t[h] = p_tel.copy()
            tgt_p, tgt_R, mode, arrived = p_tel, R_tel, "teleop", False; ghost[h] = p_tel
            wr = kin.a.d.xpos[kin.a.ee[h]]; hold_fingers = False
            snap = False
            if G[h] is not None and a.assist == "soft" and stage[h] is None:      # REALLY close (2 cm, your hand ~aligned) + closing -> reliable grasp
                gp, gR, pin_t = G[h]; dv0 = pinch(kin, h) - pin_t
                r_e = np.degrees(np.linalg.norm(arm_ik.rot_err(gR, kin.a.d.xmat[kin.a.ee[h]].reshape(3, 3))))
                if np.hypot(dv0[0], dv0[1]) < SNAP_XY and abs(dv0[2]) < SNAP_Z and r_e < SNAP_DEG and g > 0.3 * pr["g_ref"]:
                    stage[h], t_st[h], snap = "close", time.time(), True; print(f"[{h}] snap grasp: {100 * np.linalg.norm(dv0):.1f} cm, {r_e:.0f} deg from the grasp pose", flush=True)
            if G[h] is not None and a.assist == "soft" and stage[h] is None:
                gp, gR, pin_t = G[h]; dv = pinch(kin, h) - pin_t; dxy = float(np.hypot(dv[0], dv[1]))
                if dxy < 0.06 and -0.02 < dv[2] < 0.08 and g > 0.2 * pr["g_ref"]:
                    w = float(np.clip((0.06 - dxy) / 0.04, 0, 1))             # 0 at 6 cm, 1 within 2 cm
                    corr = np.clip(gp - p_tel, -0.03, 0.03)                   # never more than 3 cm per axis: you still do the reaching
                    tgt_p = p_tel + w * corr; mode = f"assist {w:.1f}"
                    if w > 0.5: tgt_R = gR                                    # close enough: grasp orientation
                    if w > 0.8 and g > 0.5 * pr["g_ref"] and float((p_tel - gp)[2]) < 0.02:
                        tgt_p = gp; mode = "assist: holding still while you close"   # no jitter while the fingers close; lifting your hand releases it
            elif G[h] is not None:
                gp, gR, pin_t = G[h]; appr = APPR[h]; pre_p = gp + CLEAR * appr; dv = pinch(kin, h) - seen
                dist = float(np.hypot(dv[0], dv[1])) if -0.03 < dv[2] < 0.20 else 9.9
                st = stage[h]
                if a.assist == "strong" and st is None and g > 0.3 * pr["g_ref"] and dist < 0.10: st, t_st[h] = "pre", time.time()   # strong mode: auto approach
                if st in ("pre", "down") and g < 0.15 * pr["g_ref"]: st = None                               # you opened before the grasp: assist off
                if st == "pre":                       # 1) grasp orientation + pre-grasp pose, AWAY from the object (above, or beside for the can)
                    tgt_p, tgt_R, hold_fingers, mode = pre_p, gR, True, "assist: pre-grasp"
                    r_err = np.degrees(np.linalg.norm(arm_ik.rot_err(gR, kin.a.d.xmat[kin.a.ee[h]].reshape(3, 3))))
                    if np.linalg.norm(wr - pre_p) < 0.015 and r_err < 8: st, t_st[h] = "down", time.time()   # oriented first, then approach
                elif st == "down":                    # 2) straight approach to the grasp pose in 1 s, fingers open
                    u = min(1.0, (time.time() - t_st[h]) / 1.0); tgt_p, tgt_R, hold_fingers, mode = pre_p + u * (gp - pre_p), gR, True, "assist: approach"
                    if u >= 1.0 and np.linalg.norm(wr - gp) < 0.012: st, t_st[h] = "close", time.time()
                elif st == "close":                   # 3) on the object: your grip closes the robot hand (capped); lock when closed for 0.5 s
                    tgt_p, tgt_R, mode = gp, gR, "assist: closing"
                    if g > 0.6 * pr["g_ref"] and time.time() - t_st[h] > 0.5: st = "hold"; lock[h] = (gp - p_tel, gR @ R_tel.T)
                    if g < 0.15 * pr["g_ref"]: st, t_st[h] = "retreat", time.time()
                elif st == "hold":                    # 4) object follows YOUR hand (position + rotation relative to the lock moment)
                    off, dR = lock[h]; tgt_p, tgt_R, mode = p_tel + off, (dR @ R_tel if a.rotate_held else gR), "grasp: object follows you"
                    if g < 0.25 * pr["g_ref"]: st, t_st[h], rel_p[h] = "retreat", time.time(), p_tel + off
                elif st == "retreat":                 # 5) opened: hand open, back away 10 cm in 1 s, then free teleop
                    u = min(1.0, (time.time() - t_st[h]) / 1.0); base_p = rel_p.get(h, gp)
                    tgt_p, tgt_R, hold_fingers, mode = base_p + u * CLEAR * appr, gR, True, "release: back away"
                    if u >= 1.0: st = None; lock[h] = None; ref[h] = (P.copy(), arm_ik.quat_wxyz_to_mat(Q)); home[h] = (tgt_p.copy(), gR.copy())
                if st != stage[h]: print(f"[{h}] {stage[h]} -> {st} | wrist-grasp {100 * np.linalg.norm(wr - gp):.1f} cm, rot err {np.degrees(np.linalg.norm(arm_ik.rot_err(gR, kin.a.d.xmat[kin.a.ee[h]].reshape(3, 3)))):.0f} deg | object {np.round(100 * (d.qpos[oa:oa + 3] - obj_c), 1)} cm", flush=True)
                stage[h] = st
            floor = kin.base[2] + D.KEEP["z"] + 0.01; tgt_p = tgt_p.copy(); tgt_p[2] = max(tgt_p[2], floor)
            qr = rest if stage.get(h) is None else None                # natural-posture pull only in free teleop: during the grasp the pose must be exact
            q_prev = dict(kin.a.q); e_p, e_r = kin.a.solve(h, tgt_p, tgt_R, q_rest=qr)
            if unsafe(kin):                                            # lift the target until wrist and palm are above the counter keep-out
                low = floor - min(kin.a.d.xpos[kin.a.ee[h]][2], palm(kin, h)[2])
                kin.a.q.update(q_prev); kin.a.apply(); kin.a.solve(h, tgt_p + np.array([0, 0, max(low, 0) + 0.01]), tgt_R, q_rest=qr); mode += " [raised]"
                if unsafe(kin): kin.a.q.update(q_prev); kin.a.apply(); blocked += 1; mode += " [BLOCKED by safety]"; hold_fingers = True
            c = 0.0 if hold_fingers else pr["cap"] * float(np.clip(g / pr["g_ref"], 0, 1))   # open while the robot moves to / away from the object
            fingers[h] = [c, c, c, 0, 0]
            status.append(f"{h}: {mode}, grip {g:.2f}->{c:.2f}")
        hq = rt.step(left=fingers["left"], right=fingers["right"])
        for n, v in kin.a.q.items():
            if n in act and "_hand_" not in n: d.ctrl[act[n]] = v
        for n, v in zip(names, hq): d.ctrl[act[n]] = v
        force = 0.0
        for _ in range(spt):
            mujoco.mj_step(m, d); fs = 0.0
            for i in range(d.ncon):
                cn = d.contact[i]
                if og in (cn.geom1, cn.geom2) and m.geom_bodyid[cn.geom2 if cn.geom1 == og else cn.geom1] in hb: mujoco.mj_contactForce(m, d, i, f6); fs += abs(f6[0])
            force = max(force, fs)
        if d.qpos[oa + 2] < kin.base[2] - 0.5:                                              # fell off the table: put it back on its spot
            d.qpos[oa:oa + 3] = obj_c; d.qpos[oa + 3:oa + 7] = D.obj_quat(obj); d.qvel[m.body_dofadr[ob]:m.body_dofadr[ob] + 6] = 0
            print("[sim] object fell off the table: placed back", flush=True)
        brk = D.OBJECTS[obj]["brk"]
        line = " | ".join(status) + f" | force {force:5.1f} N{' > THRESHOLD' if brk and force > brk else ''} | object {100 * (d.qpos[oa + 2] - obj_c[2]):+5.1f} cm | blocked {blocked}"
        if viewer is not None:
            with viewer.lock():
                viewer.user_scn.ngeom = 0
                for h2, pt in ghost.items():                     # where YOUR hand is mapped (green right, blue left)
                    gidx = viewer.user_scn.ngeom
                    mujoco.mjv_initGeom(viewer.user_scn.geoms[gidx], mujoco.mjtGeom.mjGEOM_SPHERE, np.array([0.015, 0, 0]), pt, np.eye(3).flatten(),
                                        np.array([0.1, 0.9, 0.2, 0.6] if h2 == "right" else [0.2, 0.4, 1.0, 0.6], dtype=np.float32))
                    viewer.user_scn.ngeom += 1
                viewer.set_texts([(mujoco.mjtFontScale.mjFONTSCALE_150, mujoco.mjtGridPos.mjGRID_TOPLEFT, obj, line)])
            viewer.sync()
        if tick % 15 == 0: print(line, flush=True)
        if rend is not None and tick % 4 == 0:
            rend.update_scene(d, "head_cam"); im = rend.render()[:, :, ::-1].copy(); cv2.imshow("camera in testa G1", im); k = cv2.waitKey(1) & 0xFF
            if k in (ord("c"), ord("C")):
                ref.clear()
                for h2 in hands:
                    if h2 in TC and h2 in raw_last: shift[h2] = -np.array(TC[h2]["R"]) @ (raw_last[h2] - np.array(TC[h2]["origin"]))
                    PF[h2].reset(); QF[h2].reset(); DB[h2].reset(); stage[h2] = None; lock[h2] = None; rel_p.pop(h2, None); t_st[h2] = 0.0
                print("[clutch] re-centred: your current hands = robot home", flush=True)
            if k in (ord("q"), ord("Q")): break
        tick += 1; time.sleep(max(0.0, 1 / RATE - (time.time() - t_tick)))


if __name__ == "__main__":
    main()
