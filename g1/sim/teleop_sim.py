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

RATE = 30
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


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--obj", default="egg", choices=list(D.OBJECTS)); ap.add_argument("--replay", type=int)
    ap.add_argument("--hands", default="both", choices=["both", "right", "left"]); ap.add_argument("--spot", default="0.35,-0.15")
    ap.add_argument("--scale", type=float, default=0.8); ap.add_argument("--no-assist", action="store_true"); ap.add_argument("--cam", action="store_true")
    ap.add_argument("--headless", action="store_true"); ap.add_argument("--seconds", type=float, default=900)
    a = ap.parse_args(); obj = a.obj; pr = D.PROFILE[obj]; spot = [float(x) for x in a.spot.split(",")]
    hands = ["left", "right"] if a.hands == "both" else [a.hands]
    cal = json.load(open(arm_ik.CALIB))["R_coil_to_body"]; R_cb = {h: np.array(cal.get(h, cal.get("right"))) for h in ("left", "right")}
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
    ref = {}; engaged = {h: False for h in hands}; lock = {h: None for h in hands}; fade = {h: 0.0 for h in hands}; cmd_f = {h: 0.0 for h in hands}
    viewer = None
    if not a.headless:
        from mujoco import viewer as mjv
        viewer = mjv.launch_passive(m, d)
    rend = mujoco.Renderer(m, 240, 320) if a.cam else None
    spt = int(round(1 / RATE / m.opt.timestep)); f6 = np.zeros(6); t_start = time.time(); tick = 0
    hb = {b for b in range(m.nbody) if "_hand_" in (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, b) or "")}
    blocked = 0
    while time.time() - t_start < a.seconds and (viewer is None or viewer.is_running()):
        t_tick = time.time(); fingers = {"left": None, "right": None}; status = []
        for h in hands:
            s = read(h)
            if s is None or s[1] is None or s[2] is None or np.isnan(s[1]).any() or np.isnan(s[2]).any():
                status.append(f"{h}: no Coil pose"); continue
            F, P, Q = s; g = 0.5 * (F[1] + F[2])
            if h not in ref: ref[h] = (P.copy(), arm_ik.quat_wxyz_to_mat(Q))      # clutch: first valid sample = robot home pose
            p_tel = home[h][0] + a.scale * R_cb[h] @ (P - ref[h][0])
            R_tel = R_cb[h] @ arm_ik.quat_wxyz_to_mat(Q) @ ref[h][1].T @ R_cb[h].T @ home[h][1]
            tgt_p, tgt_R, mode, arrived = p_tel, R_tel, "teleop", False
            if G[h] is not None:
                gp, gR, pin_t = G[h]; dv = pinch(kin, h) - seen; arrived = np.linalg.norm(kin.a.d.xpos[kin.a.ee[h]] - gp) < 0.012   # wrist on the grasp pose (pinch moves with the fingers)
                dist = float(np.hypot(dv[0], dv[1])) if -0.03 < dv[2] < 0.15 else 9.9   # near in plan, anywhere from just below to 15 cm above
                if lock[h] is None and g > 0.3 * pr["g_ref"] and dist < 0.07: engaged[h] = True     # you are closing near the object
                if g < 0.15 * pr["g_ref"]: engaged[h] = False                                            # opened: assist off
                if lock[h] is None and engaged[h]:                                                       # assist: go to the grasp pose and stay there
                    w = 1.0
                    tgt_p = (1 - w) * p_tel + w * gp; tgt_R = gR if w > 0.5 else R_tel; mode = f"assist {w:.1f}"
                    if arrived and g > 0.6 * pr["g_ref"]: lock[h] = (gp - p_tel, gR @ R_tel.T); fade[h] = 1.0
                    elif not arrived: mode += " (fingers wait: hand not on the object yet)"
                if lock[h] is not None:
                    off, dR = lock[h]
                    tgt_p = p_tel + fade[h] * off; tgt_R = dR @ R_tel if fade[h] > 0.5 else R_tel; mode = "grasp (object follows you)"
                    if g < 0.25 * pr["g_ref"]: fade[h] = max(0.0, fade[h] - 1.0 / RATE); mode = "release"
                    if fade[h] <= 0: lock[h] = None
            floor = kin.base[2] + D.KEEP["z"] + 0.01; tgt_p = tgt_p.copy(); tgt_p[2] = max(tgt_p[2], floor)
            q_prev = dict(kin.a.q); kin.a.solve(h, tgt_p, tgt_R, q_rest=rest)
            if unsafe(kin):                                            # lift the target until wrist and palm are above the counter keep-out
                low = floor - min(kin.a.d.xpos[kin.a.ee[h]][2], palm(kin, h)[2])
                kin.a.q.update(q_prev); kin.a.apply(); kin.a.solve(h, tgt_p + np.array([0, 0, max(low, 0) + 0.01]), tgt_R, q_rest=rest); mode += " [raised]"
                if unsafe(kin): kin.a.q.update(q_prev); kin.a.apply(); blocked += 1; mode += " [BLOCKED by safety]"
            c = pr["cap"] * float(np.clip(g / pr["g_ref"], 0, 1))
            if G[h] is not None and lock[h] is None and "assist" in mode and not arrived: c = min(c, 0.3 * pr["cap"])   # pre-shape until the hand is on the object
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
            with viewer.lock(): viewer.set_texts([(mujoco.mjtFontScale.mjFONTSCALE_150, mujoco.mjtGridPos.mjGRID_TOPLEFT, obj, line)])
            viewer.sync()
        if tick % 15 == 0: print(line, flush=True)
        if rend is not None and tick % 4 == 0:
            rend.update_scene(d, "head_cam"); im = rend.render()[:, :, ::-1].copy(); cv2.imshow("camera in testa G1", im); k = cv2.waitKey(1) & 0xFF
            if k in (ord("c"), ord("C")): ref.clear(); print("[clutch] re-centred: your current hands = robot home", flush=True)
            if k in (ord("q"), ord("Q")): break
        tick += 1; time.sleep(max(0.0, 1 / RATE - (time.time() - t_tick)))


if __name__ == "__main__":
    main()
