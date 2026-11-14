"""Two-hand teleoperation with SEVERAL objects on the table (default: egg on the right, empty can on the left).
OpenCV keys: A/C align and re-centre; R reset scene; Q quit.
  py -3.11 g1/sim/teleop_multi.py --cam                 # live gloves + Coil, uses the table calibration of teleop_sim.py (--calib to redo it)
  py -3.11 g1/sim/teleop_multi.py --objs "egg:0.35,-0.15;can_empty:0.35,0.15" --cam
What is new vs teleop_sim.py
- both hands collide with the objects; every object is localised by the HEAD CAMERA (perceive.py) and recognised (in sim the label is known;
  on the robot: Tommaso's recognizer); each hand uses the profile of the object it is closest to:
  egg -> robot closure never above 0.70 however hard you squeeze; empty can / ball -> up to 1.0, the can DENTS when squeezed hard.
- a live plot (window "forze") of the contact force of the left and right hand in newtons, with the egg break and can dent thresholds.
Same mapping, filters, safety (counter, box, joint bounds, self-collision, 1 rad/s), soft assist and snap grasp as teleop_sim.py.
Egg break 20 N and can dent 15 N are ASSUMED thresholds; the dent is a visual model (radius shrinks), not a real deformation."""
import argparse, json, os, sys, time
import numpy as np, mujoco, cv2

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "g1")); sys.path.insert(0, os.path.join(ROOT, "Rokoko", "src"))
import demo_e2e as D, perceive as PC, arm_ik
import teleop_sim as T
from robot.g1_dex3 import G1Dex3Retargeter
from live_sim import GloveLive
from teleop_filters import OneEuro, QuatFilter, Deadband

RATE = T.RATE
SNAP_XY, SNAP_Z, SNAP_DEG = 0.04, 0.05, 60
FRAGILE_R, FRAGILE_V, FRAGILE_JOINT = 0.12, 0.06, 0.3    # m, m/s, rad/s inside the camera-seen egg zone
FRAGILE_CLOSE = 0.6      # closure units/s near the egg
EGG_SAFE_N, PUSH_N = 12.0, 8.0   # hand force (0.1 s mean) above which the closure backs off / the arm may not push further
GRIP_TAU = 0.15


def slerp_mat(R0, R1, weight):
    """Interpolate rotation matrices (numpy quaternion slerp; mujoco has no mju_slerp in this version)."""
    q0, q1 = np.zeros(4), np.zeros(4); mujoco.mju_mat2Quat(q0, R0.flatten()); mujoco.mju_mat2Quat(q1, R1.flatten())
    if q0 @ q1 < 0: q1 = -q1
    w = float(np.clip(weight, 0.0, 1.0)); dot = float(np.clip(q0 @ q1, -1, 1)); th = np.arccos(dot)
    q = q0 * (1 - w) + q1 * w if th < 1e-4 else (np.sin((1 - w) * th) * q0 + np.sin(w * th) * q1) / np.sin(th)
    return arm_ik.quat_wxyz_to_mat(q / np.linalg.norm(q))


def build_multi(objs):
    """G1 (fixed base, servos as demo_e2e.build) + counter + several free objects; BOTH hands collide."""
    spec = mujoco.MjSpec.from_file(arm_ik.ASSETS)
    spec.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    spec.delete(spec.joint("floating_base_joint")); spec.body("pelvis").pos = [0, 0, D.PELVIS_Z]
    for b in spec.bodies: b.gravcomp = 1.0
    arm_ik.add_head_cam(spec)
    hand = set()
    def collect(b):
        hand.add(b.name)
        for c in b.bodies: collect(c)
    collect(spec.body("right_wrist_yaw_link")); collect(spec.body("left_wrist_yaw_link"))
    for g in spec.geoms:
        if g.parent.name in hand: g.contype, g.conaffinity, g.friction, g.condim = 1, 1, [1.0, 0.005, 0.0001], 4
        else: g.contype, g.conaffinity = 0, 0
    for a in spec.actuators:
        j = spec.joint(a.target); is_hand = "_hand_" in a.target
        k, dd = (1.5, 0.1) if is_hand else (300.0, 20.0)
        a.gaintype = mujoco.mjtGain.mjGAIN_FIXED; a.gainprm[0] = k
        a.biastype = mujoco.mjtBias.mjBIAS_AFFINE; a.biasprm[0] = 0; a.biasprm[1] = -k; a.biasprm[2] = -dd; a.ctrllimited = 0
        if is_hand and j.armature < 1e-4: j.armature = 0.002
    top = D.PELVIS_Z + D.COUNTER_Z
    spec.worldbody.add_geom(name="counter", type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.53, 0.55, 0.02], pos=[0.14 + 0.53, 0, top - 0.02],
                            rgba=[0.55, 0.42, 0.3, 1], contype=3, conaffinity=3, friction=[1.0, 0.01, 0.004], condim=6)
    spec.worldbody.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.25, 0.45, 0.0005], pos=[0.14 + 0.25, 0, top + 0.0005], rgba=[0.85, 0.85, 0.8, 1], contype=0, conaffinity=0)
    spec.worldbody.add_geom(type=mujoco.mjtGeom.mjGEOM_PLANE, size=[3, 3, 0.1], pos=[0, 0, 0], rgba=[0.3, 0.3, 0.35, 1], contype=3, conaffinity=3)   # floor
    gt = {"ellipsoid": mujoco.mjtGeom.mjGEOM_ELLIPSOID, "sphere": mujoco.mjtGeom.mjGEOM_SPHERE, "cylinder": mujoco.mjtGeom.mjGEOM_CYLINDER}
    for name, _ in objs:
        o = D.OBJECTS[name]; body = spec.worldbody.add_body(name=f"obj_{name}", pos=[0, 0, 0]); body.add_freejoint()
        g = body.add_geom(name=f"g_{name}", type=gt[o["type"]], size=o["size"] + [0] * (3 - len(o["size"])), mass=o["mass"], rgba=o["rgba"],
                          contype=3, conaffinity=3, friction=[1.0, 0.005, 0.0001], condim=4)
        if o["soft"]: g.solref = [0.03, 1.0]; g.solimp = [0.5, 0.95, 0.015, 0.5, 2]
        if o.get("roll_friction"): g.condim = 6; g.friction = [1.0, 0.01, o["roll_friction"]]
    m = spec.compile(); m.vis.global_.offwidth, m.vis.global_.offheight = 640, 480
    return m, mujoco.MjData(m)


def force_plot(hist, W=640, H=220):
    img = np.full((H, W, 3), 250, np.uint8); fmax = 60.0
    for thr, lab, col in ((20, "uovo si rompe ~20 N (ipotesi)", (0, 0, 220)), (15, "lattina si ammacca ~15 N (ipotesi)", (0, 140, 255))):
        y = int(H - 20 - (H - 40) * thr / fmax); cv2.line(img, (40, y), (W - 10, y), col, 1); cv2.putText(img, lab, (W - 260, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1)
    for h, col in (("left", (200, 90, 30)), ("right", (40, 160, 40))):
        v = hist[h][-300:]
        if len(v) > 1:
            pts = [(int(40 + (W - 50) * i / 299), int(H - 20 - (H - 40) * min(f, fmax) / fmax)) for i, f in enumerate(v)]
            cv2.polylines(img, [np.array(pts, np.int32)], False, col, 2, cv2.LINE_AA)
        cv2.putText(img, f"{'sinistra' if h == 'left' else 'destra'}: {v[-1] if v else 0:5.1f} N", (50 if h == "left" else 250, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2)
    cv2.putText(img, "forza mano-oggetto, ultimi 10 s (0-60 N)", (40, H - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (60, 60, 60), 1)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--objs", default="egg:0.35,-0.15;can_empty:0.35,0.15"); ap.add_argument("--hands", default="both", choices=["both", "right", "left"])
    ap.add_argument("--cam", action="store_true"); ap.add_argument("--calib", action="store_true"); ap.add_argument("--zoff", type=float, default=0.10)
    ap.add_argument("--gain", type=float, default=1.0); ap.add_argument("--smooth", type=float, default=0.7); ap.add_argument("--seconds", type=float, default=1800)
    ap.add_argument("--headless", action="store_true")
    a = ap.parse_args(); hands = ["left", "right"] if a.hands == "both" else [a.hands]
    objs = [(n.split(":")[0], [float(v) for v in n.split(":")[1].split(",")]) for n in a.objs.split(";")]
    if a.calib:
        gs = {h: GloveLive(h) for h in hands}; T.table_calib({h: gs[h].read for h in hands}, hands)
        for g0 in gs.values(): g0.s.close()
    TC = json.load(open(arm_ik.CALIB)).get("hands", {})
    miss = [h for h in hands if h not in TC]
    if miss: sys.exit(f"no table calibration for {miss}: run with --calib")
    m, d = build_multi(objs); names = [j["joint"] for j in G1Dex3Retargeter().joints]
    act = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, m.actuator_trnid[i, 0]): i for i in range(m.nu)}
    jq = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j): m.jnt_qposadr[j] for j in range(m.njnt)}
    kin = D.Kin(); rest = dict(kin.a.q)
    for n, v in kin.a.q.items(): d.qpos[jq[n]] = v; d.ctrl[act[n]] = v
    O = {}
    for name, sp in objs:
        ob = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f"obj_{name}"); oa = m.jnt_qposadr[m.body_jntadr[ob]]
        p = kin.base + np.array([sp[0], sp[1], D.COUNTER_Z + D.half_h(name)]); d.qpos[oa:oa + 3] = p; d.qpos[oa + 3:oa + 7] = D.obj_quat(name)
        og = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, f"g_{name}")
        O[name] = dict(body=ob, adr=oa, dof=m.body_dofadr[ob], geom=og, p0=p, q0=D.obj_quat(name), r0=float(m.geom_size[og][0]), rgba0=np.array(D.OBJECTS[name]["rgba"], dtype=float),
                       crush=0.0, broken=False)
    mujoco.mj_forward(m, d)
    for name, o in O.items():                                   # head camera: where is each object?
        rgb, dep, mk = PC.render_head(m, d, seg_geom=o["geom"])
        seen, _ = PC.locate(rgb, dep, PC.cam_pose(m, d), name, D.OBJECTS[name]["size"][0], z_plane=o["p0"][2], mask=mk)
        o["seen"] = seen
        print(f"[camera] {name}: " + ("NOT seen" if seen is None else f"seen, error {100 * np.linalg.norm((seen - o['p0'])[:2]):.1f} cm"), flush=True)
        o["G"] = {h: (T.grasp_pose(name, h, seen, rest) if seen is not None and D.best_grasp(name) else None) for h in hands}
    # Mirror the right-hand Cartesian can grasp across the sagittal plane, then solve it on the left.
    if "can_empty" in O and "left" in hands and O["can_empty"]["G"].get("left") is not None:
        M = np.diag([1.0, -1.0, 1.0])
        right_seen = O["can_empty"]["seen"].copy(); right_seen[1] *= -1
        right_pose = T.grasp_pose("can_empty", "right", right_seen, rest)
        if right_pose is not None:
            rp, rR, rpin = right_pose
            O["can_empty"]["G"]["left"] = (M @ rp, M @ rR @ M, M @ rpin)
    # each hand is anchored on the nearest object on its side (your table centre = that spot)
    anchor, base_R = {}, {}
    for h in hands:
        side = [n for n, o in O.items() if (o["p0"][1] - kin.base[1] < 0) == (h == "right") and o["G"].get(h)]
        pick = side[0] if side else next((n for n in O if O[n]["G"].get(h)), None)
        anchor[h], base_R[h] = (O[pick]["G"][h][0], O[pick]["G"][h][1]) if pick else (kin.a.d.xpos[kin.a.ee[h]].copy(), kin.a.d.xmat[kin.a.ee[h]].reshape(3, 3).copy())
        print(f"[map] {h} hand: table centre = robot hand on the {pick}", flush=True)
    gl = {h: GloveLive(h) for h in hands}
    grip_f = {h: None for h in hands}
    PF = {h: OneEuro(freq=RATE, min_cutoff=a.smooth, beta=0.02) for h in hands}; QF = {h: QuatFilter(freq=RATE, min_cutoff=a.smooth, beta=0.02) for h in hands}
    DB = {h: Deadband(0.003) for h in hands}
    rt = G1Dex3Retargeter(max_closure=float(os.environ.get("G1_MAX_CLOSURE", "1.0")))
    shift = {h: np.zeros(3) for h in hands}; last_t = {}; stage = {h: None for h in hands}; t_st = {h: 0.0 for h in hands}; lock = {h: None for h in hands}
    target = {h: None for h in hands}; raw_last = {}; hist = {"left": [], "right": []}; blocked = 0
    need_align = False; reset_park_until = 0.0; force_window = {h: [] for h in hands}; egg_grip_cap = {h: 0.70 for h in hands}; c_prev = {}
    egg_force_mean = lambda h: float(np.mean([f for _, f in force_window[h]])) if force_window[h] else 0.0
    viewer = None
    if not a.headless:
        from mujoco import viewer as mjv
        viewer = mjv.launch_passive(m, d)
    rend = mujoco.Renderer(m, 240, 320) if a.cam else None
    spt = int(round(1 / RATE / m.opt.timestep)); f6 = np.zeros(6); t0 = time.time(); tick = 0
    hand_bodies = {h: {b for b in range(m.nbody) if (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, b) or "").startswith(f"{h}_hand_")} for h in ("left", "right")}
    while time.time() - t0 < a.seconds and (viewer is None or viewer.is_running()):
        t_tick = time.time(); fingers = {"left": None, "right": None}; status = []
        if need_align:
            # Keep the reset posture and park objects until the operator realigns with A.
            if reset_park_until and t_tick >= reset_park_until:
                for o in O.values():
                    d.qpos[o["adr"]:o["adr"] + 3] = o["p0"]; d.qpos[o["adr"] + 3:o["adr"] + 7] = o["q0"]
                    d.qvel[o["dof"]:o["dof"] + 6] = 0
                mujoco.mj_forward(m, d); reset_park_until = 0.0
            if viewer is not None:
                with viewer.lock(): viewer.user_scn.ngeom = 0
                viewer.sync()
            if not a.headless and tick % 3 == 0:
                k = cv2.waitKey(1) & 0xFF
                if k in (ord("a"), ord("A")) and reset_park_until == 0.0:
                    need_align = False
                    for h in hands:
                        if h in raw_last: shift[h] = -np.array(TC[h]["R"]) @ (raw_last[h] - np.array(TC[h]["origin"]))
                        PF[h].reset(); QF[h].reset(); DB[h].reset(); grip_f[h] = None
                    print("[key] A: teleop riallineato", flush=True)
                elif k in (ord("q"), ord("Q")): break
            tick += 1; time.sleep(max(0.0, 1 / RATE - (time.time() - t_tick))); continue
        for h in hands:
            s = gl[h].read()
            if s is None or s[1] is None or s[2] is None or np.isnan(s[1]).any(): status.append(f"{h}: no Coil"); continue
            F, P, Q = s; g_raw = 0.5 * (F[1] + F[2]); raw_last[h] = np.asarray(P, float).copy()
            if grip_f[h] is None: grip_f[h] = (g_raw, t_tick)
            else:
                dt = max(t_tick - grip_f[h][1], 1e-6); alpha = 1.0 - np.exp(-dt / GRIP_TAU)
                grip_f[h] = (grip_f[h][0] + alpha * (g_raw - grip_f[h][0]), t_tick)
            g = grip_f[h][0]
            P = DB[h](PF[h](P, t_tick)); Q = QF[h](Q, t_tick)
            Tc = TC[h]; Rh_ = np.array(Tc["R"]); rel = Rh_ @ (P - np.array(Tc["origin"])) + shift[h]; rel[2] -= a.zoff
            p_tel = anchor[h] + a.gain * rel
            R_rel = Rh_ @ arm_ik.quat_wxyz_to_mat(Q) @ arm_ik.quat_wxyz_to_mat(np.array(Tc["q_origin"])).T @ Rh_.T
            rv = np.zeros(3); qq = np.zeros(4); mujoco.mju_mat2Quat(qq, R_rel.flatten()); mujoco.mju_quat2Vel(rv, qq, 1.0)
            if np.linalg.norm(rv) > np.radians(T.WRIST_MAX_DEG):
                rv *= np.radians(T.WRIST_MAX_DEG) / np.linalg.norm(rv); qq0 = np.array([1.0, 0, 0, 0]); mujoco.mju_quatIntegrate(qq0, rv, 1.0); R_rel = arm_ik.quat_wxyz_to_mat(qq0)
            R_tel = R_rel @ base_R[h]
            # FRAGILE ZONE: where the head camera sees the egg, the hand slows down (no impacts): 12 cm -> 6 cm/s, 6 cm -> 3 cm/s
            pin_now = T.pinch(kin, h); vmax = T.VMAX; near_egg = False
            if "egg" in O and O["egg"]["seen"] is not None:
                de = float(np.linalg.norm(pin_now - O["egg"]["seen"]))
                if de < FRAGILE_R: vmax = FRAGILE_V if de > FRAGILE_R / 2 else FRAGILE_V / 2; near_egg = True
            dp = p_tel - last_t.get(h, p_tel); nrm = np.linalg.norm(dp)
            if nrm > vmax / RATE: p_tel = last_t[h] + dp * (vmax / RATE) / nrm
            if near_egg and stage[h] is None and egg_force_mean(h) > PUSH_N:      # already pressing the egg without grasping: no closer
                p_tel = last_t.get(h, p_tel) if np.linalg.norm(p_tel - O["egg"]["seen"]) < np.linalg.norm(last_t.get(h, p_tel) - O["egg"]["seen"]) else p_tel
            last_t[h] = p_tel.copy()
            # which object is this hand working on? (nearest seen object to its pinch; its profile = what the camera recognised)
            pin = T.pinch(kin, h)
            if stage[h] is None:
                cands = [(np.hypot(*(pin - O[n]["seen"])[:2]), n) for n in O if O[n]["seen"] is not None and O[n]["G"].get(h)]
                target[h] = min(cands)[1] if cands else None
            name = target[h]; pr = D.PROFILE.get(name, D.PROFILE["unknown"]); tgt_p, tgt_R, mode, hold_f = p_tel, R_tel, "teleop", False
            if name is not None:
                gp, gR, pin_t = O[name]["G"][h]; dv = pin - pin_t; dxy = float(np.hypot(dv[0], dv[1]))
                r_e = np.degrees(np.linalg.norm(arm_ik.rot_err(gR, kin.a.d.xmat[kin.a.ee[h]].reshape(3, 3))))
                st = stage[h]
                if st is None:
                    if dxy < SNAP_XY and abs(dv[2]) < SNAP_Z and r_e < SNAP_DEG and g > 0.3 * pr["g_ref"]:
                        st, t_st[h] = "close", time.time(); print(f"[{h}] snap grasp on the {name}", flush=True)
                    elif dxy < 0.06 and -0.02 < dv[2] < 0.08 and g > 0.2 * pr["g_ref"]:
                        w = float(np.clip((0.06 - dxy) / 0.04, 0, 1)); tgt_p = p_tel + w * np.clip(gp - p_tel, -0.03, 0.03); mode = f"assist {w:.1f} ({name})"
                        tgt_R = slerp_mat(R_tel, gR, w)
                if st == "close":
                    tgt_p, tgt_R, mode = gp, gR, f"closing on the {name}"
                    if g > 0.6 * pr["g_ref"] and time.time() - t_st[h] > 0.5: st = "hold"; lock[h] = gp - p_tel
                    if g < 0.15 * pr["g_ref"]: st = None
                elif st == "hold":
                    tgt_p, tgt_R, mode = p_tel + lock[h], gR, f"holding the {name}"
                    if g < 0.25 * pr["g_ref"]: st, t_st[h] = "retreat", time.time(); lock[h] = p_tel + lock[h]
                elif st == "retreat":
                    u = min(1.0, (time.time() - t_st[h]) / 1.0); tgt_p, tgt_R, hold_f, mode = lock[h] + np.array([0, 0, 0.10 * u]), gR, True, "release"
                    if u >= 1.0: st = None
                stage[h] = st
            floor = kin.base[2] + D.KEEP["z"] + 0.01; tgt_p = tgt_p.copy(); tgt_p[2] = max(tgt_p[2], floor)
            q_prev = dict(kin.a.q); step0 = arm_ik.ARM_STEP
            if near_egg: arm_ik.ARM_STEP = FRAGILE_JOINT / RATE                          # joints slower too near the egg
            kin.a.solve(h, tgt_p, tgt_R, q_rest=rest if stage[h] is None else None); arm_ik.ARM_STEP = step0
            why = T.unsafe(kin)
            if why:
                low = floor - min(kin.a.d.xpos[kin.a.ee[h]][2], T.palm(kin, h)[2])            # below the counter keep-out: try the same target raised
                kin.a.q.update(q_prev); kin.a.apply()
                if low > 0:
                    kin.a.solve(h, tgt_p + np.array([0, 0, low + 0.01]), tgt_R, q_rest=rest if stage[h] is None else None); why = T.unsafe(kin)
                    if why: kin.a.q.update(q_prev); kin.a.apply()
                if why: blocked += 1; mode += f" [BLOCKED: {why[0]}]"
            c = 0.0 if hold_f else pr["cap"] * float(np.clip(g / pr["g_ref"], 0, 1))   # egg: never above 0.70 however hard you squeeze
            if name == "egg":                                                          # force limiter in EVERY state, not only while holding
                cap_now = egg_grip_cap[h]
                mean_force = float(np.mean([f for _, f in force_window[h]])) if force_window[h] else 0.0
                if mean_force > EGG_SAFE_N: cap_now = max(0.40, cap_now - 0.03)
                elif mean_force < EGG_SAFE_N - 4: cap_now = min(0.70, cap_now + 0.01)
                egg_grip_cap[h] = cap_now; c = min(c, cap_now)
            if near_egg: c = float(np.clip(c, c_prev.get(h, 0.0) - FRAGILE_CLOSE / RATE, c_prev.get(h, 0.0) + FRAGILE_CLOSE / RATE))   # slow closing near the egg
            c_prev[h] = c
            fingers[h] = [c, c, c, 0, 0]; status.append(f"{h}: {mode}, grip {g:.2f}->{c:.2f}")
        hq = rt.step(left=fingers["left"], right=fingers["right"])
        for n, v in kin.a.q.items():
            if n in act and "_hand_" not in n: d.ctrl[act[n]] = v
        for n, v in zip(names, hq): d.ctrl[act[n]] = v
        fh = {"left": 0.0, "right": 0.0}; fo = {n: 0.0 for n in O}
        for _ in range(spt):
            mujoco.mj_step(m, d); fs = {"left": 0.0, "right": 0.0}; fso = {n: 0.0 for n in O}
            for i in range(d.ncon):
                cn = d.contact[i]; b1, b2 = m.geom_bodyid[cn.geom1], m.geom_bodyid[cn.geom2]
                for n, o in O.items():
                    if o["geom"] in (cn.geom1, cn.geom2):
                        other = b2 if cn.geom1 == o["geom"] else b1
                        for h in ("left", "right"):
                            if other in hand_bodies[h]: mujoco.mj_contactForce(m, d, i, f6); fs[h] += abs(f6[0]); fso[n] += abs(f6[0])
            for h in fh: fh[h] = max(fh[h], fs[h])
            for n in fo: fo[n] = max(fo[n], fso[n])
        for h in hands:
            force_window[h].append((t_tick, fo.get("egg", 0.0) if target[h] == "egg" else 0.0))
            force_window[h] = [(ts, f) for ts, f in force_window[h] if t_tick - ts <= 0.1]
        for h in ("left", "right"): hist[h].append(fh[h])
        for n, o in O.items():                                          # egg breaks / can dents (assumed thresholds)
            o.setdefault("fh", []).append(fo[n]); o["fh"] = o["fh"][-3:]
            if n == "egg" and np.mean(o["fh"]) > 20 and not o["broken"]:  # sustained 0.1 s, not a 1-substep spike
                o["broken"] = True; m.geom_rgba[o["geom"]] = [0.9, 0.1, 0.1, 1]; print("[sim] EGG BROKEN", flush=True)
            if n.startswith("can") and fo[n] > 15:
                o["crush"] = min(1.0, o["crush"] + (fo[n] - 15) / 400.0); m.geom_size[o["geom"]][0] = o["r0"] * (1 - 0.35 * o["crush"])
                m.geom_rgba[o["geom"]] = [0.85, 0.7 - 0.4 * o["crush"], 0.3 - 0.2 * o["crush"], 1]
            if d.qpos[o["adr"] + 2] < kin.base[2] - 0.5:
                d.qpos[o["adr"]:o["adr"] + 3] = o["p0"]; d.qpos[o["adr"] + 3:o["adr"] + 7] = D.obj_quat(n); d.qvel[o["dof"]:o["dof"] + 6] = 0
        line = " | ".join(status) + f" | L {fh['left']:4.1f} N R {fh['right']:4.1f} N | " + " ".join(f"{n}:{'ROTTO' if o['broken'] else ('ammaccata %d%%' % (100 * o['crush']) if o['crush'] > 0 else 'ok')}" for n, o in O.items()) + f" | blocked {blocked}"
        if viewer is not None:
            with viewer.lock():
                viewer.user_scn.ngeom = 0
                viewer.set_texts([(mujoco.mjtFontScale.mjFONTSCALE_150, mujoco.mjtGridPos.mjGRID_TOPLEFT, "teleop", line)])
            viewer.sync()
        if tick % 15 == 0: print(line, flush=True)
        if not a.headless and tick % 3 == 0:
            cv2.imshow("forze", force_plot(hist));
            if rend is not None:
                rend.update_scene(d, "head_cam"); cv2.imshow("camera in testa G1", rend.render()[:, :, ::-1].copy())
            k = cv2.waitKey(1) & 0xFF
            if k != 255: print(f"[key] {chr(k) if 32 <= k < 127 else k}", flush=True)
            if k in (ord("a"), ord("A"), ord("c"), ord("C")):
                need_align = False
                for h in hands:
                    if h in raw_last: shift[h] = -np.array(TC[h]["R"]) @ (raw_last[h] - np.array(TC[h]["origin"]))
                    PF[h].reset(); QF[h].reset(); DB[h].reset(); grip_f[h] = None; stage[h] = None; lock[h] = None
                print("[clutch] re-centred", flush=True)
            if k in (ord("r"), ord("R")):
                kin.a.q.update(rest); kin.a.apply()
                for n, v in rest.items():
                    if n in act: d.qpos[jq[n]] = v; d.ctrl[act[n]] = v
                hq = rt.step(left=[0, 0, 0, 0, 0] if "left" in hands else None, right=[0, 0, 0, 0, 0] if "right" in hands else None)
                for n, v in zip(names, hq):
                    d.ctrl[act[n]] = v
                    if n in jq: d.qpos[jq[n]] = v
                last_t.clear()
                for name, o in O.items():
                    d.qpos[o["adr"]:o["adr"] + 3] = o["p0"] + np.array([0.0, 0.0, -1.0]); d.qpos[o["adr"] + 3:o["adr"] + 7] = o["q0"]
                    d.qvel[o["dof"]:o["dof"] + 6] = 0
                    m.geom_size[o["geom"]][0] = o["r0"]; m.geom_rgba[o["geom"]] = o["rgba0"]
                    o["crush"], o["broken"] = 0.0, False
                for h in hands:
                    stage[h] = None; lock[h] = None; target[h] = None; t_st[h] = 0.0; grip_f[h] = None
                    shift[h].fill(0); PF[h].reset(); QF[h].reset(); DB[h].reset(); force_window[h].clear(); egg_grip_cap[h] = 0.70
                need_align = True; reset_park_until = time.time() + 1.0
                mujoco.mj_forward(m, d)
                print("[key] R: scena resettata, premi A per riallineare", flush=True)
            if k in (ord("q"), ord("Q")): break
        tick += 1; time.sleep(max(0.0, 1 / RATE - (time.time() - t_tick)))


if __name__ == "__main__":
    main()
