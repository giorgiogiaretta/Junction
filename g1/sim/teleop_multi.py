"""Two-hand teleoperation with SEVERAL objects on the table (default: egg on the right, empty can on the left).
OpenCV keys: A/C re-anchor (then hands flat + still on the table for 1 s); R reset scene; Q quit.
  py -3.11 g1/sim/teleop_multi.py --calib --cam         # short SEATED calibration (forward/left per hand, ~12 s each), then live
  py -3.11 g1/sim/teleop_multi.py --cam                 # live gloves + Coil with the saved calibration
  py -3.11 g1/sim/teleop_multi.py --replay 77 --hands right --objs "egg:0.35,-0.15" --metrics out.json [--legacy]   # scripted replay + numbers
Seated beside the robot: start with both gloves FLAT and STILL on the table = robot rest pose; a hand resting still on the table for 1 s
re-anchors automatically (Coil drift removed). The whole glove/Coil -> arm chain lives in g1/coil_chain.py (shared with live_policy_v2.py);
--legacy runs the previous chain for before/after numbers (docs/G1_TEST_PLAN.md section A).
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
import coil_chain as CC

RATE = T.RATE
FRAGILE_R, FRAGILE_V, FRAGILE_JOINT = 0.08, 0.20, 0.9    # m, m/s, rad/s near the camera-seen egg (was 0.12, 0.06, 0.3: the right hand crawled; the finger cap 0.50 protects the egg)
FRAGILE_CLOSE = 0.6      # closure units/s near the egg
EGG_SAFE_N, PUSH_N = 17.0, 8.0   # (was 12: the limiter cut the grip to 0.40 and the egg was never lifted; it breaks at a sustained 20 N)   # hand force (0.1 s mean) above which the closure backs off / the arm may not push further


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
    for thr, lab, col in ((20, "egg breaks ~20 N (assumed)", (0, 0, 220)), (15, "can dents ~15 N (assumed)", (0, 140, 255))):
        y = int(H - 20 - (H - 40) * thr / fmax); cv2.line(img, (40, y), (W - 10, y), col, 1); cv2.putText(img, lab, (W - 260, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1)
    for h, col in (("left", (200, 90, 30)), ("right", (40, 160, 40))):
        v = hist[h][-300:]
        if len(v) > 1:
            pts = [(int(40 + (W - 50) * i / 299), int(H - 20 - (H - 40) * min(f, fmax) / fmax)) for i, f in enumerate(v)]
            cv2.polylines(img, [np.array(pts, np.int32)], False, col, 2, cv2.LINE_AA)
        cv2.putText(img, f"{'left' if h == 'left' else 'right'}: {v[-1] if v else 0:5.1f} N", (50 if h == "left" else 250, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2)
    cv2.putText(img, "hand-object force, last 10 s (0-60 N)", (40, H - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (60, 60, 60), 1)
    return img


def assign_objects(O, hands, kin, forced):
    """A5: ONE object per hand for the whole run (CLI --right-obj/--left-obj, else the seen object on that hand's side)."""
    out = {}
    for h in hands:
        if forced.get(h): out[h] = forced[h]; continue
        side = [n for n, o in O.items() if (o["p0"][1] - kin.base[1] < 0) == (h == "right") and o["G"].get(h)]
        out[h] = side[0] if side else next((n for n in O if O[n]["G"].get(h)), None)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--objs", default="egg:0.35,-0.15;can_empty:0.35,0.15"); ap.add_argument("--hands", default="both", choices=["both", "right", "left"])
    ap.add_argument("--right-obj"); ap.add_argument("--left-obj")
    ap.add_argument("--cam", action="store_true"); ap.add_argument("--calib", action="store_true", help="short seated calibration (forward/left per hand), then run")
    ap.add_argument("--zoff", type=float, default=None, help="m: your wrist height above the flat-hand height when you grasp (default 0.04)")
    ap.add_argument("--gain", type=float, default=1.0); ap.add_argument("--seconds", type=float, default=1800)
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--replay", help="scripted replay instead of the live gloves: <right take>[,<left take>] (e.g. 77 or 77,86); runs in sim time")
    ap.add_argument("--legacy", action="store_true", help="the OLD chain (before the A1-A8 fixes), for before/after numbers")
    ap.add_argument("--no-record", action="store_true", help="do not save the session (default: data/live/sim_<time>/ video.mp4 + ticks.jsonl + metrics.json)")
    ap.add_argument("--video", help="write a 1920x1080 mp4 (robot view + head camera with recognition + force plot)")
    ap.add_argument("--fast", action="store_true", help="same limits as the robot's -Fast: joints 1.8 rad/s, faster target, only robot self-collision blocks")
    ap.add_argument("--vision", action="store_true", help="head camera recognises each object (g1/perception_v1, as the robot code) and sets its finger cap (egg 0.50, can 0.90, ball 1.0)")
    ap.add_argument("--assist", action="store_true", help="previous strong grasp assist + snap grasp (default since 15/11: manual grasp)")
    ap.add_argument("--prior", action="store_true", help="real-G1 posture prior (Tommaso's aalto data) as the IK null-space target")
    ap.add_argument("--old-rest", action="store_true", help="previous robot rest pose (wrists rolled, palms sideways)")
    ap.add_argument("--slow", action="store_true", help="previous speed/filter settings (before the 14/11 evening latency tuning)")
    ap.add_argument("--metrics", help="write latency/jerk/blocked/grasp numbers to this JSON file")
    a = ap.parse_args(); hands = ["left", "right"] if a.hands == "both" else [a.hands]
    global EVAL
    import arm_prior; EVAL = arm_prior.RealArmPrior()            # always measured (naturalness), used only with --prior
    if a.prior: CC.PRIOR = arm_prior.RealArmPrior()
    cfg = CC.Cfg.old() if a.legacy else (CC.Cfg.slow() if a.slow else CC.Cfg())
    if a.fast: cfg.fast()                                                 # = robot -Fast (coil_chain.Cfg.fast, same values)
    if not a.legacy and not a.slow: arm_ik.WRIST_GAIN, arm_ik.W_ROT = 1.08, 0.4   # = the -CoilVision robot policy (wrist slightly faster)
    if not a.assist and not a.legacy: cfg.manual_grasp()                  # operator 15/11: manual grasp (no snap, light pull); --assist = old
    REC = None
    if not a.no_record and not a.replay:                                  # every live session is saved: video + all data per tick
        REC = os.path.join(ROOT, "data", "live", time.strftime("sim_%Y%m%d_%H%M%S")); os.makedirs(REC, exist_ok=True)
        a.video = a.video or os.path.join(REC, "video.mp4"); a.metrics = a.metrics or os.path.join(REC, "metrics.json")
        rec_f = open(os.path.join(REC, "ticks.jsonl"), "w"); print(f"[record] saving to {REC}", flush=True)
    raw_in = {}
    cfg.gain = a.gain
    if a.zoff is not None: cfg.zoff = a.zoff
    objs = [(n.split(":")[0], [float(v) for v in n.split(":")[1].split(",")]) for n in a.objs.split(";")]
    if a.calib and not a.replay:
        gs = {h: GloveLive(h) for h in hands}; CC.seated_calib({h: gs[h].read for h in hands}, hands, arm_ik.CALIB)
        for g0 in gs.values(): g0.s.close()
    m, d = build_multi(objs); names = [j["joint"] for j in G1Dex3Retargeter().joints]
    act = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, m.actuator_trnid[i, 0]): i for i in range(m.nu)}
    jq = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j): m.jnt_qposadr[j] for j in range(m.njnt)}
    kin = D.Kin(); rest = dict(kin.a.q) if a.legacy or a.old_rest else CC.palm_down_rest(kin, D.COUNTER_Z)   # hands open, palm down, in front
    for n, v in kin.a.q.items(): d.qpos[jq[n]] = v; d.ctrl[act[n]] = v
    O = {}
    for name, sp in objs:
        ob = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f"obj_{name}"); oa = m.jnt_qposadr[m.body_jntadr[ob]]
        p = kin.base + np.array([sp[0], sp[1], D.COUNTER_Z + D.half_h(name)]); d.qpos[oa:oa + 3] = p; d.qpos[oa + 3:oa + 7] = D.obj_quat(name)
        og = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, f"g_{name}")
        O[name] = dict(body=ob, adr=oa, dof=m.body_dofadr[ob], geom=og, p0=p, q0=D.obj_quat(name), r0=float(m.geom_size[og][0]), rgba0=np.array(D.OBJECTS[name]["rgba"], dtype=float),
                       crush=0.0, broken=False, zmax=float(p[2]))
    mujoco.mj_forward(m, d)
    for name, o in O.items():                                   # head camera: where is each object?
        rgb, dep, mk = PC.render_head(m, d, seg_geom=o["geom"])
        seen, _ = PC.locate(rgb, dep, PC.cam_pose(m, d), name, D.OBJECTS[name]["size"][0], z_plane=o["p0"][2], mask=mk)
        o["seen"] = seen
        print(f"[camera] {name}: " + ("NOT seen" if seen is None else f"seen, error {100 * np.linalg.norm((seen - o['p0'])[:2]):.1f} cm"), flush=True)
        o["G"] = {h: (T.grasp_pose(name, h, seen, rest) if seen is not None and D.best_grasp(name) else None) for h in hands}
    VIS = {}; CAMT = None
    if a.vision:                                                 # same recognition as g1/live_policy_v2_vision.py (CAP_HARD caps)
        from g1.perception_v1 import perceive as pv_perceive, pinhole_pixel_to_pelvis, robot_mask
        Ks = np.array([[PC.FX, 0, PC.CX], [0, PC.FX, PC.CY], [0, 0, 1.0]])
        pos_c, R_c = PC.cam_pose(m, d); CAMT = np.eye(4); CAMT[:3, :3] = R_c @ np.diag([1, -1, -1]); CAMT[:3, 3] = pos_c - kin.base
        rgb_v, dep_v = PC.render_head(m, d); sm = robot_mask([kin.a.q[n] for n in arm_ik.ARM_NAMES], None, Ks, CAMT)(dep_v)
        t_v = time.time(); res_v = pv_perceive(rgb_v, dep_v, pinhole_pixel_to_pelvis(Ks, CAMT), self_mask=sm); t_v = time.time() - t_v
        CAP_HARD = {"egg": 0.50, "can_empty": 0.90, "stress_ball": 1.0}   # egg 0.50 (this sim breaks it from 0.53), can 0.90, ball 1.0
        for name, o in O.items():
            best = None
            for r in res_v["objects"]:
                dd = float(np.hypot(*(np.array(r["p_pelvis"][:2]) - (o["p0"] - kin.base)[:2])))
                if dd < 0.06 and (best is None or dd < best[0]): best = (dd, r)
            lab = best[1]["label"] if best else "unknown"; VIS[name] = (lab, CAP_HARD.get(lab, 0.5))
            print(f"[vision] {name}: recognised as {lab} -> finger cap {VIS[name][1]:.2f}  ({t_v:.2f} s)", flush=True)
    # Mirror the right-hand Cartesian can grasp across the sagittal plane, then solve it on the left.
    if "can_empty" in O and "left" in hands and O["can_empty"]["G"].get("left") is not None:
        M = np.diag([1.0, -1.0, 1.0])
        right_seen = O["can_empty"]["seen"].copy(); right_seen[1] *= -1
        right_pose = T.grasp_pose("can_empty", "right", right_seen, rest)
        if right_pose is not None:
            rp, rR, rpin = right_pose
            O["can_empty"]["G"]["left"] = (M @ rp, M @ rR @ M, M @ rpin)
    floor = kin.base[2] + D.KEEP["z"] + 0.01
    assigned = assign_objects(O, hands, kin, {"right": a.right_obj, "left": a.left_obj})
    rest_pose = {h: (kin.a.d.xpos[kin.a.ee[h]].copy(), kin.a.d.xmat[kin.a.ee[h]].reshape(3, 3).copy()) for h in hands}
    # operator axes: replay = the 14/11 session calibration; live = seated calibration (or the older table calibration)
    Rh = {h: (CC.TAKE64_R if a.replay else CC.load_axes(arm_ik.CALIB, h)) for h in hands}
    miss = [h for h in hands if Rh[h] is None]
    if miss: sys.exit(f"no calibration for {miss}: run with --calib")
    chains = {}
    if not a.replay: CC.load_neutral(arm_ik.CALIB, hands)
    for h in hands:
        n = assigned[h]; gr = None
        if n is not None and O[n]["G"].get(h):
            gp, gR, pin_t = O[n]["G"][h]; prof = dict(D.PROFILE.get(n, D.PROFILE["unknown"]))
            if n in VIS: prof["cap"] = min(prof["cap"], VIS[n][1])          # vision: cap of the RECOGNISED object
            gr = (gp, gR, pin_t, n, prof)
        chains[h] = CC.HandChain(h, Rh[h], rest_pose[h], gr, cfg, floor)
        print(f"[map] {h} hand -> {n}; start pose = robot rest pose (hand flat on your table)", flush=True)
    # input: live gloves or scripted replay (sim time, deterministic)
    if a.replay:
        takes = [int(x) for x in a.replay.split(",")]; src = {}
        for h, tk in zip(["right", "left"], takes + takes[:1] if len(takes) == 1 else takes):
            if h not in hands: continue
            z = np.load(os.path.join(ROOT, "data", "episodes", f"take_{tk:02d}.npz")); P = z["right_wrist_pos"]; P0 = P[:10].mean(0)
            ch = chains[h]; goal = ch.human_target(ch.grasp[0] + np.array([0, 0, 0.02])) if ch.grasp else np.array([0.15, 0, 0.05])
            P2, Q2, F2, info = CC.align_take(P, z["right_wrist_quat"], z["right_fingers01"], CC.TAKE64_R, P0, goal, mirror=(h == "left"))
            src[h] = (F2, P2, Q2); print(f"[replay] {h}: take {tk}, reach scaled x{info['scale']} rotated {info['rot_deg']} deg to land 2 cm above the grasp", flush=True)
        n_ticks = max(len(s[0]) for s in src.values())
        def read(h, i): s = src[h]; j = min(i, len(s[0]) - 1); return s[0][j], s[1][j], s[2][j]
        a.headless = True
    else:
        gl = {h: GloveLive(h) for h in hands}; n_ticks = None
        def read(h, i): return gl[h].read()
    rt = G1Dex3Retargeter(max_closure=float(os.environ.get("G1_MAX_CLOSURE", "1.0")))
    hist = {"left": [], "right": []}; blocked = {h: 0 for h in hands}; consec = {h: 0 for h in hands}; max_consec = 0
    need_align = False; reset_park_until = 0.0; force_window = {h: [] for h in hands}; egg_grip_cap = {h: 0.70 for h in hands}; c_prev = {}
    log = {h: [] for h in hands}; events = []
    egg_force_mean = lambda h: float(np.mean([f for _, f in force_window[h]])) if force_window[h] else 0.0
    viewer = None
    if not a.headless:
        from mujoco import viewer as mjv
        viewer = mjv.launch_passive(m, d)
    rend = mujoco.Renderer(m, 480, 640) if a.cam and not a.headless else None
    spt = int(round(1 / RATE / m.opt.timestep)); f6 = np.zeros(6); t0 = time.time(); tick = 0
    hand_bodies = {h: {b for b in range(m.nbody) if (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, b) or "").startswith(f"{h}_hand_")} for h in ("left", "right")}

    def near_egg_v(pin):
        if "egg" in O and O["egg"]["seen"] is not None:
            de = float(np.linalg.norm(pin - O["egg"]["seen"]))
            if de < FRAGILE_R: return FRAGILE_V if de > FRAGILE_R / 2 else FRAGILE_V / 2
        return None

    def unsafe(k):
        r = T.unsafe(k)
        if len(hands) == 2 and np.linalg.norm(T.palm(k, "left") - T.palm(k, "right")) < 0.10: r.append("palms_too_close")
        return r

    while (n_ticks is None and time.time() - t0 < a.seconds and (viewer is None or viewer.is_running())) or (n_ticks is not None and tick < n_ticks):
        t_tick = time.time(); t_now = tick / RATE if a.replay else t_tick; fingers = {"left": None, "right": None}; status = []
        if need_align:
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
                    for h in hands: chains[h] = CC.HandChain(h, Rh[h], rest_pose[h], chains[h].grasp, cfg, floor)
                    print("[key] A: appoggia le mani piatte e ferme sul tavolo per 1 s", flush=True)
                elif k in (ord("q"), ord("Q")): break
            tick += 1; time.sleep(max(0.0, 1 / RATE - (time.time() - t_tick))); continue
        for h in hands:
            s = read(h, tick)
            if s is None or s[1] is None or s[2] is None or np.isnan(s[1]).any(): status.append(f"{h}: no Coil"); continue
            F, P, Q = s; ch = chains[h]; name = ch.grasp[3] if ch.grasp else None
            raw_in[h] = (np.asarray(F, float).round(3).tolist(), np.asarray(P, float).round(4).tolist(), np.asarray(Q, float).round(4).tolist())
            if VIS and ch.stage is None:                                       # vision: object nearest to the pinch -> cap + target
                pin = T.pinch(kin, h); cands = [(float(np.linalg.norm(pin - O[n]["seen"])), n) for n in O if O[n]["seen"] is not None and O[n]["G"].get(h)]
                if cands:
                    dn, n = min(cands); gp, gR, pin_t = O[n]["G"][h]; prof = dict(D.PROFILE.get(n, D.PROFILE["unknown"]))
                    prof["cap"] = VIS[n][1] if dn <= 0.15 else min(VIS[n][1], 0.50)
                    if not ch.grasp or ch.grasp[3] != n or abs(ch.grasp[4]["cap"] - prof["cap"]) > 1e-6:
                        events.append((round(t_now, 2), h, f"target {n} cap {prof['cap']:.2f} ({100 * dn:.0f} cm)"))
                    ch.grasp = (gp, gR, pin_t, n, prof); name = n
            elif not cfg.fixed_target and ch.stage is None:                     # legacy A5: nearest seen object every tick
                pin = T.pinch(kin, h); cands = [(np.hypot(*(pin - O[n]["seen"])[:2]), n) for n in O if O[n]["seen"] is not None and O[n]["G"].get(h)]
                if cands and min(cands)[1] != name:
                    n = min(cands)[1]; gp, gR, pin_t = O[n]["G"][h]; ch.grasp = (gp, gR, pin_t, n, D.PROFILE.get(n, D.PROFILE["unknown"])); name = n
            def push_block(p_new, p_old, h=h):
                if not (name == "egg" and near_egg_v(T.pinch(kin, h)) is not None and egg_force_mean(h) > PUSH_N): return False
                return np.linalg.norm(p_new - O["egg"]["seen"]) < np.linalg.norm(p_old - O["egg"]["seen"])
            out = ch.update(F, P, Q, t_now, T.pinch(kin, h), kin.a.d.xmat[kin.a.ee[h]].reshape(3, 3), near_egg=near_egg_v, push_block=push_block,
                            wrist_p_now=kin.a.d.xpos[kin.a.ee[h]].copy())
            if out["ev"]: events.append((round(t_now, 2), h, out["ev"])); print(f"[{h}] {out['ev']}", flush=True)
            near = near_egg_v(T.pinch(kin, h)) is not None
            step0 = arm_ik.ARM_STEP; arm_ik.ARM_STEP = (min(cfg.joint_speed, FRAGILE_JOINT) if near else cfg.joint_speed) / RATE
            why = CC.solve_arm(kin, h, out, cfg, rest, (lambda k_: [x for x in unsafe(k_) if x.startswith("self")]) if a.fast else unsafe, floor, T.palm); arm_ik.ARM_STEP = step0
            if EVAL is not None: CC.NATURAL[h].append(EVAL.naturalness(kin, h))
            mode = out["mode"]
            if why:
                blocked[h] += 1; consec[h] += 1; max_consec = max(max_consec, consec[h]); mode += f" [BLOCKED: {why[0]}]"
            else: consec[h] = 0
            if ch.stage == "close" and (not log[h] or log[h][-1]["stage"] != "close"): events.append((round(t_now, 2), h, f"snap grasp on the {name}"))
            g = out["g"]; c = out["c"]
            if name == "egg":                                                          # force limiter in EVERY state
                cap_now = egg_grip_cap[h]; mean_force = egg_force_mean(h)
                if mean_force > EGG_SAFE_N: cap_now = max(0.50, cap_now - 0.02)
                elif mean_force < EGG_SAFE_N - 4: cap_now = min(0.70, cap_now + 0.01)
                egg_grip_cap[h] = cap_now; c = min(c, cap_now)
            if near: c = float(np.clip(c, c_prev.get(h, 0.0) - FRAGILE_CLOSE / RATE, c_prev.get(h, 0.0) + FRAGILE_CLOSE / RATE))
            c_prev[h] = c
            fingers[h] = CC.finger_cmd(ch.grasp[4] if ch.grasp else None, F, c) if not cfg.legacy else [c, c, c, 0, 0]   # thumb/index/middle independent
            status.append(f"{h}: {mode}, grip {g:.2f}->{c:.2f}")
            log[h].append(dict(t=t_now, engaged=ch.P0 is not None, p_raw=out["p_raw"], p_filt=out["p_filt"], p_tel=ch.p_tel.copy(), p_cmd=kin.a.d.xpos[kin.a.ee[h]].copy(),
                               q=[kin.a.q[n] for n in kin.a.arm[h]], mode=out["mode"], stage=ch.stage, blocked=bool(why),
                               pin_err=(T.pinch(kin, h) - ch.grasp[2]) if ch.grasp else np.zeros(3), tgt=out["p"].copy(), c=c,
                               oz=float(d.qpos[O[name]["adr"] + 2] - O[name]["p0"][2]) if name else 0.0,
                               rot_err=float(np.degrees(np.linalg.norm(arm_ik.rot_err(out["R"], kin.a.d.xmat[kin.a.ee[h]].reshape(3, 3)))))))
        hq = rt.step(left=fingers["left"], right=fingers["right"])
        if REC is not None:
            rec_f.write(json.dumps({"t": round(tick / RATE, 3), "in": raw_in, "status": status,
                                    "target": {h: (chains[h].grasp[3], round(chains[h].grasp[4]["cap"], 2), chains[h].stage) if chains[h].grasp else None for h in hands},
                                    "fingers": {h: fingers[h] for h in hands}, "arm_q": [round(kin.a.q[n], 4) for n in arm_ik.ARM_NAMES],
                                    "hand_q": [round(float(x), 4) for x in hq], "wrist": {h: kin.a.d.xpos[kin.a.ee[h]].round(4).tolist() for h in hands}}) + "\n")
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
            tg = chains[h].grasp[3] if chains[h].grasp else None
            force_window[h].append((t_now, fo.get("egg", 0.0) if tg == "egg" else 0.0))
            force_window[h] = [(ts, f) for ts, f in force_window[h] if t_now - ts <= 0.1]
        for h in ("left", "right"): hist[h].append(fh[h])
        for n, o in O.items():                                          # egg breaks / can dents (assumed thresholds)
            o.setdefault("fh", []).append(fo[n]); o["fh"] = o["fh"][-3:]; o["zmax"] = max(o["zmax"], float(d.qpos[o["adr"] + 2]))
            if n == "egg" and np.mean(o["fh"]) > 20 and not o["broken"]:  # sustained 0.1 s, not a 1-substep spike
                o["broken"] = True; m.geom_rgba[o["geom"]] = [0.9, 0.1, 0.1, 1]; print(f"[sim] EGG BROKEN at t={t_now:.2f} s", flush=True)
            if n.startswith("can") and fo[n] > 15:
                o["crush"] = min(1.0, o["crush"] + (fo[n] - 15) / 400.0); m.geom_size[o["geom"]][0] = o["r0"] * (1 - 0.35 * o["crush"])
                m.geom_rgba[o["geom"]] = [0.85, 0.7 - 0.4 * o["crush"], 0.3 - 0.2 * o["crush"], 1]
            if d.qpos[o["adr"] + 2] < kin.base[2] - 0.5:
                d.qpos[o["adr"]:o["adr"] + 3] = o["p0"]; d.qpos[o["adr"] + 3:o["adr"] + 7] = D.obj_quat(n); d.qvel[o["dof"]:o["dof"] + 6] = 0
        line = " | ".join(status) + f" | L {fh['left']:4.1f} N R {fh['right']:4.1f} N | " + " ".join(f"{n}:{'ROTTO' if o['broken'] else ('ammaccata %d%%' % (100 * o['crush']) if o['crush'] > 0 else 'ok')}" for n, o in O.items()) + f" | blocked {sum(blocked.values())}"
        if viewer is not None:
            with viewer.lock():
                viewer.user_scn.ngeom = 0
                viewer.set_texts([(mujoco.mjtFontScale.mjFONTSCALE_150, mujoco.mjtGridPos.mjGRID_TOPLEFT, "teleop", line)])
            viewer.sync()
        if tick % (90 if a.replay else 15) == 0: print(line, flush=True)
        if not a.replay and tick == int(2.0 * RATE):                       # automatic ALIGN 2 s after start (no keyboard needed)
            for h in hands: chains[h] = CC.HandChain(h, Rh[h], rest_pose[h], chains[h].grasp, cfg, floor)
            print("[align] AUTO: put both hands FLAT and STILL on the table for 1 s", flush=True)
        if a.video and tick % 2 == 0:
            if "vw" not in locals():
                m.vis.global_.offwidth, m.vis.global_.offheight = 1920, 1080
                vrend = mujoco.Renderer(m, 760, 1100); hrend = mujoco.Renderer(m, 480, 640); vcam = mujoco.MjvCamera()
                vcam.lookat[:] = [0.28, 0.0, D.PELVIS_Z + 0.05]; vcam.distance, vcam.azimuth, vcam.elevation = 1.5, 200, -24
                vw = cv2.VideoWriter(a.video, cv2.VideoWriter_fourcc(*"mp4v"), 15, (1920, 1080))
            fr = np.full((1080, 1920, 3), (28, 24, 22), np.uint8)
            cv2.rectangle(fr, (0, 0), (1920, 70), (44, 36, 38), -1)
            cv2.putText(fr, "G1  x  ROKOKO GLOVES + COIL PRO  x  COMPUTER VISION", (28, 46), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (240, 235, 235), 2, cv2.LINE_AA)
            vrend.update_scene(d, vcam); fr[90:850, 20:1120] = vrend.render()[:, :, ::-1]
            hrend.update_scene(d, "head_cam"); himg = hrend.render()[:, :, ::-1].copy()
            if VIS and CAMT is not None:
                Ks = np.array([[PC.FX, 0, PC.CX], [0, PC.FX, PC.CY], [0, 0, 1.0]])
                for name, o in O.items():
                    pc_ = CAMT[:3, :3].T @ (d.xpos[o["body"]] - kin.base - CAMT[:3, 3])
                    if pc_[2] <= 0.05: continue
                    u, v, w = Ks @ pc_; u, v = int(u / w), int(v / w); lab, capv = VIS[name]; txt = f"{lab.upper().replace('_', ' ')}  max {capv:.2f}"
                    cv2.rectangle(himg, (u - 34, v - 34), (u + 34, v + 34), (130, 30, 0), 2)
                    (tw, th_), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                    cv2.rectangle(himg, (u - 37, v - 40 - th_), (u - 31 + tw, v - 36), (245, 245, 245), -1)
                    cv2.putText(himg, txt, (u - 34, v - 38), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (130, 30, 0), 2, cv2.LINE_AA)
            fr[90:660, 1140:1900] = cv2.resize(himg, (760, 570))
            cv2.putText(fr, "G1 HEAD CAMERA + object recognition", (1150, 685), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (235, 235, 240), 1, cv2.LINE_AA)
            fp = cv2.resize(force_plot(hist), (760, 260)); fr[720:980, 1140:1900] = fp
            # glove panel (bottom-left corner of the robot view): the 5 finger closures of each glove + Coil state
            gx, gy = 30, 610; cv2.rectangle(fr, (gx - 10, gy - 30), (gx + 520, gy + 225), (40, 34, 36), -1)
            cv2.putText(fr, "ROKOKO GLOVES (live)", (gx, gy - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (235, 235, 240), 1, cv2.LINE_AA)
            for j, h in enumerate(("left", "right")):
                ri = raw_in.get(h); x0 = gx + j * 260
                cv2.putText(fr, f"{h.upper()} {'Coil ok' if ri else 'no Coil'}", (x0, gy + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (120, 220, 140) if ri else (80, 80, 255), 1, cv2.LINE_AA)
                Fv = ri[0] if ri else [0] * 5
                for i, (fn, fv) in enumerate(zip(("thumb", "index", "middle", "ring", "little"), Fv)):
                    y = gy + 45 + i * 34; cv2.putText(fr, fn, (x0, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 210), 1, cv2.LINE_AA)
                    cv2.rectangle(fr, (x0 + 62, y), (x0 + 232, y + 18), (70, 66, 72), -1)
                    cv2.rectangle(fr, (x0 + 62, y), (x0 + 62 + int(170 * float(np.clip(fv, 0, 1))), y + 18), (90, 200, 120), -1)
            for i, (h, st) in enumerate(zip(hands, status)):
                cv2.putText(fr, st[:95], (28, 900 + 40 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (235, 235, 240), 1, cv2.LINE_AA)
            cv2.putText(fr, f"t {tick / RATE:5.1f} s   blocked {sum(blocked.values())}   " + " ".join(f"{n}: {'BROKEN' if o['broken'] else 'ok'}" for n, o in O.items()),
                        (28, 1000), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (120, 220, 140), 1, cv2.LINE_AA)
            cv2.putText(fr, "MuJoCo simulation - operator's recorded glove + Coil takes" if a.replay else "MuJoCo simulation - live gloves + Coil",
                        (24, 1070), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (140, 140, 150), 1, cv2.LINE_AA)
            vw.write(fr)
            if not a.headless: cv2.imshow("G1 dashboard (recorded)", cv2.resize(fr, (1280, 720)))
        if not a.headless and tick % 3 == 0:
            if not a.video: cv2.imshow("forze", force_plot(hist))
            if rend is not None:
                rend.update_scene(d, "head_cam"); cimg = rend.render()[:, :, ::-1].copy()
                if VIS and CAMT is not None:                         # recognised label + cap on each object, following it
                    Ks = np.array([[PC.FX, 0, PC.CX], [0, PC.FX, PC.CY], [0, 0, 1.0]])
                    for name, o in O.items():
                        pc = CAMT[:3, :3].T @ (d.xpos[o["body"]] - kin.base - CAMT[:3, 3])
                        if pc[2] <= 0.05: continue
                        u, v, w = Ks @ pc; u, v = int(u / w), int(v / w); lab, capv = VIS[name]; txt = f"{lab}  max {capv:.2f}"
                        cv2.rectangle(cimg, (u - 34, v - 34), (u + 34, v + 34), (130, 30, 0), 2)
                        (tw, th_), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                        cv2.rectangle(cimg, (u - 37, v - 40 - th_), (u - 31 + tw, v - 36), (245, 245, 245), -1)
                        cv2.putText(cimg, txt, (u - 34, v - 38), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (130, 30, 0), 2, cv2.LINE_AA)
                if not a.video: cv2.imshow("G1 head camera", cimg)
            k = cv2.waitKey(1) & 0xFF
            if k != 255: print(f"[key] {chr(k) if 32 <= k < 127 else k}", flush=True)
            if k in (ord("a"), ord("A"), ord("c"), ord("C")):             # manual re-anchor: hands flat + still on the table for 1 s
                for h in hands: chains[h] = CC.HandChain(h, Rh[h], rest_pose[h], chains[h].grasp, cfg, floor)
                print("[clutch] appoggia le mani piatte e ferme sul tavolo per 1 s", flush=True)
            if k in (ord("r"), ord("R")):
                kin.a.q.update(rest); kin.a.apply()
                for n, v in rest.items():
                    if n in act: d.qpos[jq[n]] = v; d.ctrl[act[n]] = v
                hq = rt.step(left=[0, 0, 0, 0, 0] if "left" in hands else None, right=[0, 0, 0, 0, 0] if "right" in hands else None)
                for n, v in zip(names, hq):
                    d.ctrl[act[n]] = v
                    if n in jq: d.qpos[jq[n]] = v
                for name, o in O.items():
                    d.qpos[o["adr"]:o["adr"] + 3] = o["p0"] + np.array([0.0, 0.0, -1.0]); d.qpos[o["adr"] + 3:o["adr"] + 7] = o["q0"]
                    d.qvel[o["dof"]:o["dof"] + 6] = 0
                    m.geom_size[o["geom"]][0] = o["r0"]; m.geom_rgba[o["geom"]] = o["rgba0"]
                    o["crush"], o["broken"] = 0.0, False
                for h in hands:
                    chains[h] = CC.HandChain(h, Rh[h], rest_pose[h], chains[h].grasp, cfg, floor); force_window[h].clear(); egg_grip_cap[h] = 0.70
                need_align = True; reset_park_until = time.time() + 1.0
                mujoco.mj_forward(m, d)
                print("[key] R: scena resettata, premi A per riallineare", flush=True)
            if k in (ord("q"), ord("Q")): break
        tick += 1
        if not a.replay: time.sleep(max(0.0, 1 / RATE - (time.time() - t_tick)))
    # --- numbers ------------------------------------------------------------------------------------------------------------
    res = {"chain": "legacy" if a.legacy else "new", "replay": a.replay, "ticks": tick, "blocked": blocked, "max_consecutive_blocks": max_consec,
           "events": events, "hands": {}, "objects": {}}
    for h in hands:
        res["hands"][h] = CC.metrics(log[h]); res["hands"][h]["reanchors"] = chains[h].reanchors
        if log[h]: res["hands"][h]["closest_pinch_cm"] = round(100 * min(float(np.linalg.norm(r["pin_err"])) for r in log[h]), 1)
    if os.environ.get("TELEOP_DUMP"): np.save(os.environ["TELEOP_DUMP"], np.array([log[h] for h in hands], dtype=object), allow_pickle=True)
    for n, o in O.items():
        lift = o["zmax"] - o["p0"][2]
        res["objects"][n] = dict(lift_cm=round(100 * lift, 1), broken=o["broken"], crush_pct=round(100 * o["crush"]),
                                 grasp_success=bool(lift > 0.03 and not o["broken"]))
    for h in hands:
        if CC.NATURAL[h]: res["hands"][h]["natural_rms_rad"] = round(float(np.median(CC.NATURAL[h])), 3); res["hands"][h]["natural_p95_rad"] = round(float(np.percentile(CC.NATURAL[h], 95)), 3)
    print("[metrics] " + json.dumps(res["hands"]) + " " + json.dumps(res["objects"]) + f" blocked {blocked}", flush=True)
    if a.metrics: json.dump(res, open(a.metrics, "w"), indent=1, default=float)
    if a.video and "vw" in locals(): vw.release(); print("video:", a.video, flush=True)
    if REC is not None: rec_f.close(); print(f"[record] session saved: {REC}", flush=True)


if __name__ == "__main__":
    main()
