"""End-to-end simulation of the single live G1 test, as close to the real setup as we can make it.
  py -3.11 g1/sim/demo_e2e.py                         # all scenarios -> data/g1sim/e2e/{report.json, REPORT.md, *.mp4}
  py -3.11 g1/sim/demo_e2e.py --only egg_profile      # one scenario
Inputs (all real, from the 14/11 Coil session): the operator's RIGHT glove (fingers + wrist position + wrist orientation, Coil frame,
30 Hz episodes), the arm-axes calibration (data/arm_calib.json), the DJI head-camera frame of the same take (for the picker),
the official G1 29-DoF + Dex3 model, the organisers' interface numbers (aaltonomous docs/participants/INTERFACE.md, 13/11):
home pose (shoulder roll -0.35 right, elbow -0.5), counter top at pelvis z 0.01 (keep-out z < 0.03, x 0.14-1.20, |y| < 0.55),
workspace box x 0.00-0.80 / |y| < 0.70 / z -0.25..0.60, 30 Hz, arm 1.0 rad/s, hand 3.0 rad/s, URDF limits minus 0.05 / 0.02 rad,
abort after 30 clipped ticks, head D435i (URDF d435_link, 640x480, fx = fy = 615).
Pipeline per scenario:
  1) picker: the take's DJI frame at the 'look' moment -> ai.pick_profile (Gemini/Nemotron) -> object; fallback = take label.
  2) profile: object -> robot hand closure cap + the operator's reference grip g_ref (measured today) -> c = cap * clip(g / g_ref, 0, 1).
  3) arms: the glove wrist pose relative to its start, rotated into the robot frame (calibration), scaled 0.8, added to a start pose
     with the palm at the operator's rest height above the counter; IK (DLS) per tick; per-tick safety checks as the runner's filter.
  4) object on the counter where the robot's pinch is when the operator closes (pass 1, kinematic), physics in pass 2:
     arms stiff position servos, Dex3 position servos (kp 1.5, URDF torque limits), contact force hand<->object, held / dropped / broken.
NOT real: servo gains, break thresholds (egg 20 N, empty can dents above 15 N), object sizes (estimated), wrist sensor offset, the
self-collision and fingertip-table checks are only reported. Pinocchio (organisers' filter) does not install on Windows: the same
checks are re-implemented with MuJoCo FK."""
import argparse, json, os, subprocess, sys, time
import numpy as np, mujoco, cv2

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "g1"))
import arm_ik
from robot.g1_dex3 import G1Dex3Retargeter

OUT = os.path.join(ROOT, "data", "g1sim", "e2e")
PELVIS_Z = 0.793
COUNTER_Z = 0.01                 # pelvis frame (keep-out z < 0.03 = table + 2 cm)
KEEP = dict(x=(0.14, 1.20), y=(-0.55, 0.55), z=0.03)
BOX = dict(x=(0.0, 0.80), y=(-0.70, 0.70), z=(-0.25, 0.60))
HOME = {"left": dict(shoulder_roll=0.35, elbow=-0.5), "right": dict(shoulder_roll=-0.35, elbow=-0.5)}
OBJECTS = {   # estimated sizes: measure ours. brk = break / dent threshold (assumed)
    "egg":         dict(type="ellipsoid", size=[0.021, 0.021, 0.028], mass=0.060, brk=20.0, soft=False, rgba=[0.96, 0.92, 0.85, 1], quat=[0.7071068, 0.7071068, 0, 0]),   # lying, long axis along y
    "stress_ball": dict(type="sphere",    size=[0.033],               mass=0.030, brk=None, soft=True,  rgba=[1.0, 0.45, 0.05, 1]),
    "can_empty":   dict(type="cylinder",  size=[0.029, 0.073],        mass=0.015, brk=15.0, soft=False, rgba=[0.85, 0.7, 0.3, 1]),
}
PROFILE = {   # robot closure cap (Dex3 retargeter closure) and the operator's reference grip g_ref (mean index+middle while holding, 14/11)
    "egg":         dict(cap=0.70, g_ref=0.29, why="gentle: sim holds from 0.65, breaks above 0.75"),
    "stress_ball": dict(cap=1.00, g_ref=0.36, why="full strength: does not break"),
    "can_empty":   dict(cap=1.00, g_ref=0.52, why="strong: empty can, denting accepted"),
    "unknown":     dict(cap=0.68, g_ref=0.30, why="conservative (Tommaso's rule)"),
}
SCENARIOS = {   # name: (take, object on the table, mapping)
    "egg_profile":  (77, "egg", "profile"),
    "egg_naive":    (77, "egg", "naive"),
    "egg_nolimit":  (77, "egg", "nolimit"),
    "ball_profile": (82, "stress_ball", "profile"),
    "can_profile":  (86, "can_empty", "profile"),
}
SCALE = 0.8
ROT = "fixed"
ARMS = os.environ.get("E2E_ARMS", "assisted")   # assisted: robot aims at the object (camera), the operator's glove drives closure + lift; full: full wrist teleop
CLEAR = 0.10
SIDE_APPROACH = {"can_empty": True}
# grasp posture: thumb and index/middle squeeze HORIZONTALLY, palm 7 cm above the pinch -> the hand comes down from above onto an object
# lying on the counter (searched over shoulder/elbow/wrist on the official model; the earlier side posture squeezed vertically, thumb under the object)
GRASP_ARM = {"right_shoulder_pitch_joint": -0.6, "right_shoulder_roll_joint": -0.25, "right_shoulder_yaw_joint": 0.0, "right_elbow_joint": 0.8,
             "right_wrist_roll_joint": -0.8, "right_wrist_pitch_joint": 0.5, "right_wrist_yaw_joint": 0.0}
CAM_DELAY = 0.57


def pick(take, label):
    """Real picker on the take's DJI frame at the 'look' moment (+ measured camera delay). Returns (object, source, detail)."""
    t = next(json.loads(l) for l in open(os.path.join(ROOT, "data", "raw", "takes.jsonl")) if json.loads(l)["take"] == take)
    vid = os.path.join(ROOT, t["video"]) if t.get("video") else None
    if not vid or not os.path.exists(vid): return label, "label", "no video"
    times = json.load(open(vid.replace(".mp4", "_frames.json")))
    look = t["t_start"] + (t["lead_s"] + 1.0 if t.get("guided") else 4.0) + CAM_DELAY
    k = int(np.argmin(np.abs(np.array(times) - look)))
    cap = cv2.VideoCapture(vid); cap.set(cv2.CAP_PROP_POS_FRAMES, k); ok, f = cap.read()
    if not ok: return label, "label", "frame read failed"
    os.makedirs(OUT, exist_ok=True); img = os.path.join(OUT, f"take{take}_look.jpg"); cv2.imwrite(img, f)
    try:
        r = subprocess.run([sys.executable, "-m", "ai.pick_profile", "--image", img], cwd=ROOT, capture_output=True, text=True, timeout=60)
        txt = (r.stdout + r.stderr).strip()
        for obj in ("egg", "stress_ball", "can_empty", "can", "cup", "none"):
            if f'"{obj}"' in txt or f"'{obj}'" in txt or f"profile: {obj}" in txt or f"profile={obj}" in txt:
                return ("can_empty" if obj == "can" and label == "can_empty" else obj), "picker", txt[-300:]
        return label, "label (picker output not parsed)", txt[-300:]
    except Exception as e:
        return label, "label (picker failed)", repr(e)[:200]


def build(obj, stand=None):
    spec = mujoco.MjSpec.from_file(arm_ik.ASSETS)
    spec.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    spec.delete(spec.joint("floating_base_joint")); spec.body("pelvis").pos = [0, 0, PELVIS_Z]
    for b in spec.bodies: b.gravcomp = 1.0
    arm_ik.add_head_cam(spec)
    hand = set()
    def collect(b):
        hand.add(b.name)
        for c in b.bodies: collect(c)
    collect(spec.body("right_wrist_yaw_link"))
    for g in spec.geoms:
        if g.parent.name in hand: g.contype, g.conaffinity, g.friction, g.condim = 1, 1, [1.0, 0.005, 0.0001], 4
        else: g.contype, g.conaffinity = 0, 0
    for a in spec.actuators:
        j = spec.joint(a.target); is_hand = "_hand_" in a.target
        k, d = (1.5, 0.1) if is_hand else (300.0, 20.0)
        a.gaintype = mujoco.mjtGain.mjGAIN_FIXED; a.gainprm[0] = k
        a.biastype = mujoco.mjtBias.mjBIAS_AFFINE; a.biasprm[0] = 0; a.biasprm[1] = -k; a.biasprm[2] = -d; a.ctrllimited = 0
        if is_hand and j.armature < 1e-4: j.armature = 0.002
    # counter: top at pelvis z COUNTER_Z, near edge x 0.14, 1.06 m deep, 1.10 m wide; printed mat 0.90 x 0.50 from the near edge
    top = PELVIS_Z + COUNTER_Z
    spec.worldbody.add_geom(name="counter", type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.53, 0.55, 0.02], pos=[0.14 + 0.53, 0, top - 0.02],
                            rgba=[0.55, 0.42, 0.3, 1], contype=3, conaffinity=3, friction=[1.0, 0.005, 0.0001])
    spec.worldbody.add_geom(type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.25, 0.45, 0.0005], pos=[0.14 + 0.25, 0, top + 0.0005], rgba=[0.85, 0.85, 0.8, 1], contype=0, conaffinity=0)
    o = OBJECTS[obj]
    body = spec.worldbody.add_body(name="obj", pos=[0, 0, 0]); body.add_freejoint()
    gt = {"ellipsoid": mujoco.mjtGeom.mjGEOM_ELLIPSOID, "sphere": mujoco.mjtGeom.mjGEOM_SPHERE, "cylinder": mujoco.mjtGeom.mjGEOM_CYLINDER}[o["type"]]
    g = body.add_geom(name="obj_g", type=gt, size=o["size"] + [0] * (3 - len(o["size"])), mass=o["mass"], rgba=o["rgba"], contype=3, conaffinity=3,
                      friction=[1.0, 0.005, 0.0001], condim=4)
    if o["soft"]: g.solref = [0.03, 1.0]; g.solimp = [0.5, 0.95, 0.015, 0.5, 2]
    if stand is not None:                                           # small stand on the counter (collides with the object only, not the hand)
        x, y, ztop = stand; hgt = max(ztop - top, 0.002)
        spec.worldbody.add_geom(name="stand", type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[0.015, hgt / 2, 0], pos=[x, y, top + hgt / 2],
                                rgba=[0.3, 0.3, 0.35, 1], contype=2, conaffinity=2)
    m = spec.compile(); m.vis.global_.offwidth, m.vis.global_.offheight = 640, 480
    return m, mujoco.MjData(m)


def obj_quat(obj): return OBJECTS[obj].get("quat", [1, 0, 0, 0])


def plot_panel(p, F, lifts, i, brk, W=1280, H=260):
    """bottom strip: operator glove grip g, robot closure c, contact force and object height over time (cursor = now)"""
    img = np.full((H, W, 3), 245, np.uint8); n = len(p["t"]); x = lambda k: int(60 + (W - 80) * k / max(1, n - 1))
    def curve(vals, lo, hi, col, y0, h):
        pts = [(x(k), int(y0 + h - h * (np.clip(v, lo, hi) - lo) / (hi - lo))) for k, v in enumerate(vals)]
        if len(pts) > 1: cv2.polylines(img, [np.array(pts, np.int32)], False, col, 2, cv2.LINE_AA)
    cv2.putText(img, "guanto (operatore, take reale)  vs  chiusura G1", (60, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 40, 40), 1, cv2.LINE_AA)
    curve(p["g"], 0, 1, (200, 120, 30), 25, 95); curve(p["c"], 0, 1, (30, 30, 200), 25, 95)
    cv2.putText(img, "guanto g", (W - 230, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 120, 30), 1); cv2.putText(img, "G1 c", (W - 120, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 200), 1)
    cv2.putText(img, "forza mano-oggetto (N, 0-40)  e  altezza oggetto (cm, 0-25)", (60, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 40, 40), 1, cv2.LINE_AA)
    curve(F, 0, 40, (40, 40, 200), 150, 100); curve([100 * v for v in lifts], 0, 25, (40, 150, 40), 150, 100)
    if brk: yb = int(150 + 100 - 100 * brk / 40); cv2.line(img, (60, yb), (W - 20, yb), (220, 0, 0), 1); cv2.putText(img, f"rottura {brk:.0f} N (ipotesi)", (W - 200, yb - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (220, 0, 0), 1)
    cv2.putText(img, "forza", (W - 230, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40, 40, 200), 1); cv2.putText(img, "altezza", (W - 120, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (40, 150, 40), 1)
    cv2.line(img, (x(i), 20), (x(i), H - 5), (0, 0, 0), 1)
    return img


def half_h(obj):
    o = OBJECTS[obj]; s = o["size"]
    if o.get("quat"): return s[0]                                   # lying ellipsoid: half height = short radius
    return s[2] if o["type"] == "ellipsoid" else (s[1] if o["type"] == "cylinder" else s[0])


class Kin:
    """Kinematic G1 for IK and checks (arm_ik.G1Arms with the organisers' home pose and the pelvis at PELVIS_Z)."""
    def __init__(self):
        self.a = arm_ik.G1Arms(with_cam=False)
        for s, h in HOME.items():
            for k in arm_ik.HOME[s]: self.a.q[f"{s}_{k}_joint"] = 0.0
            for k, v in h.items(): self.a.q[f"{s}_{k}_joint"] = v
        self.a.apply()
        self.base = self.a.d.xpos[mujoco.mj_name2id(self.a.m, mujoco.mjtObj.mjOBJ_BODY, "pelvis")].copy()

    def pel(self, p): return p - self.base           # world -> pelvis frame (no rotation: fixed upright base)

    def palm(self):
        b = self.a.ee["right"]; return self.a.d.xpos[b] + self.a.d.xmat[b].reshape(3, 3) @ np.array([0.0415, -0.003, 0.0])

    def _tip_local(self, body):
        """fingertip = mesh vertex farthest from the distal link origin (body frame), as in g1/sim/g1_sim.py"""
        m = self.a.m; best, bp = -1.0, np.zeros(3)
        for g in range(m.ngeom):
            if m.geom_bodyid[g] != body or m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH: continue
            mid = m.geom_dataid[g]; a, n = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
            R = np.zeros(9); mujoco.mju_quat2Mat(R, m.geom_quat[g]); v = m.mesh_vert[a:a + n] @ R.reshape(3, 3).T + m.geom_pos[g]
            k = int(np.argmax(np.linalg.norm(v, axis=1)))
            if np.linalg.norm(v[k]) > best: best, bp = float(np.linalg.norm(v[k])), v[k].copy()
        return bp

    def tip(self, name):
        if not hasattr(self, "_tips"): self._tips = {}
        b = mujoco.mj_name2id(self.a.m, mujoco.mjtObj.mjOBJ_BODY, name)
        if name not in self._tips: self._tips[name] = self._tip_local(b)
        return self.a.d.xpos[b] + self.a.d.xmat[b].reshape(3, 3) @ self._tips[name]

    def pinch(self):
        """midpoint between the thumb tip and the index/middle tips (where an object sits when the hand closes on it)"""
        return 0.5 * (self.tip("right_hand_thumb_2_link") + 0.5 * (self.tip("right_hand_index_1_link") + self.tip("right_hand_middle_1_link")))


def checks(kin):
    """Organisers' workspace box + counter keep-out on the right wrist and palm frames (pelvis frame). Returns list of reasons."""
    r = []
    for name, p in (("wrist", kin.pel(kin.a.d.xpos[kin.a.ee["right"]])), ("palm", kin.pel(kin.palm()))):
        if not (BOX["x"][0] <= p[0] <= BOX["x"][1] and BOX["y"][0] <= p[1] <= BOX["y"][1] and BOX["z"][0] <= p[2] <= BOX["z"][1]): r.append(f"{name}_box")
        if KEEP["x"][0] <= p[0] <= KEEP["x"][1] and KEEP["y"][0] <= p[1] <= KEEP["y"][1] and p[2] < KEEP["z"]: r.append(f"{name}_counter")
    return r


def best_grasp(obj):
    """per-object posture + aim from g1/sim/grasp_search.py (grasp_postures.json); None -> fall back to GRASP_ARM + calibrate_grasp"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grasp_postures.json")
    b = (json.load(open(p)).get(obj) or {}).get("best") if os.path.exists(p) else None
    if not b: return None
    c = b["posture"]
    q = {"right_shoulder_pitch_joint": c[0], "right_shoulder_roll_joint": -0.25, "right_shoulder_yaw_joint": 0.0, "right_elbow_joint": c[1],
         "right_wrist_roll_joint": c[2], "right_wrist_pitch_joint": c[3], "right_wrist_yaw_joint": c[4]}
    return q, np.array(b["aim"], float), b


OBJ_SPOT = np.array([0.35, -0.15])        # where the staff places the object on the mat (pelvis frame x, y), same as grasp_search.py


def plan(take, obj, mapping, pass1=None, obj_seen=None):
    """Kinematic pass: per tick arm_q (IK) + hand_q (profile mapping). Returns dict of arrays and the pinch point at the grasp moment."""
    z = np.load(os.path.join(ROOT, "data", "episodes", f"take_{take:02d}.npz"), allow_pickle=True)
    R_cb = np.array(json.load(open(arm_ik.CALIB))["R_coil_to_body"]["right"])
    P, Q, F = z["right_wrist_pos"].astype(float), z["right_wrist_quat"].astype(float), z["right_fingers01"].astype(float)
    g = 0.5 * (F[:, 1] + F[:, 2]); pr = PROFILE.get(obj, PROFILE["unknown"])
    if mapping == "profile": c = pr["cap"] * np.clip(g / pr["g_ref"], 0, 1)
    elif mapping == "naive": c = np.clip(g, 0, 1)
    else: c = np.clip(g / pr["g_ref"], 0, 1)                       # nolimit: full fist when the operator holds
    kin = Kin(); rt = G1Dex3Retargeter(max_closure=1.0)
    # grasp moment (human) = first tick the operator's grip reaches 60 % of its reference
    gh = int(np.argmax(g >= 0.9 * pr["g_ref"])) if (g >= 0.9 * pr["g_ref"]).any() else int(np.argmax(g))   # grip almost at its hold level
    # anchor: at the grasp moment the robot's pinch is on the object, which lies on the mat in front of the right hand at the organisers'
    # "arm q = 0" (hands just above the counter over the object band). Motion = the operator's wrist motion RELATIVE to the grasp moment,
    # rotated into the robot frame and scaled; the wrist never goes below the counter safety floor (keep-out z 0.03 + 0.5 cm).
    k0 = Kin()
    bg = best_grasp(obj); posture = bg[0] if bg else GRASP_ARM
    for n, v in posture.items(): k0.a.q[n] = v                       # per-object grasp posture (grasp_search.py) or the generic one
    rt0 = G1Dex3Retargeter(max_closure=1.0)
    for _ in range(30): hq0 = rt0.step(right=[0.5 * pr["cap"]] * 3 + [0, 0])   # fingers half-way to the object's cap: pinch measured near contact
    k0.a.apply(hq0); ee = k0.a.ee["right"]
    w0, Rh = k0.a.d.xpos[ee].copy(), k0.a.d.xmat[ee].reshape(3, 3).copy()
    pin0 = k0.pinch().copy()
    if bg: obj_c = np.array([kin.base[0] + OBJ_SPOT[0], kin.base[1] + OBJ_SPOT[1], kin.base[2] + COUNTER_Z + half_h(obj)]); aim = bg[1]
    else:
        obj_c = pin0.copy(); obj_c[2] = max(obj_c[2], kin.base[2] + COUNTER_Z + half_h(obj)); aim, _ = calibrate_grasp(obj, pr["cap"])
    seen = obj_c if obj_seen is None else np.asarray(obj_seen, float)   # the robot aims where the HEAD CAMERA sees the object
    w_grasp = w0 + (seen + aim - pin0) + (pass1["corr"] if pass1 else 0.0)
    floor = kin.base[2] + KEEP["z"] + 0.01
    pg, Rg = P[gh], arm_ik.quat_wxyz_to_mat(Q[gh])
    appr = np.array([0.0, 0.0, 1.0])                                 # approach from above (egg, ball) ...
    if SIDE_APPROACH.get(obj):                                       # ... or from the side, like the operator did with the can (palm side)
        v = (w0 - pin0); v[2] = 0.0; appr = v / (np.linalg.norm(v) + 1e-9)
    rel = gh + int(np.argmax(g[gh:] < 0.3 * pr["g_ref"])) if (g[gh:] < 0.3 * pr["g_ref"]).any() else len(g)   # release moment
    onset = int(np.argmax(g >= 0.15 * pr["g_ref"])) if (g >= 0.15 * pr["g_ref"]).any() else gh   # fingers start closing
    kk = np.arange(len(g)); clear_w = np.clip((onset - kk) / 30.0, 0, 1) + np.clip((kk - rel) / 30.0, 0, 1)   # down BEFORE closing, up after release
    pre = int(2.0 * 30)                                            # 2 s from home to the first pose (arm speed cap applies)
    arm, hand, reasons, perr, pinch, cc = [], [], [], [], [], []
    for i in range(pre + len(P)):
        k = max(0, i - pre)
        dp = SCALE * R_cb @ ((P[k] if i >= pre else P[0]) - pg)
        if ARMS == "assisted": dp = np.array([0.0, 0.0, max(0.0, dp[2])])   # camera fixes x/y at the object; the glove gives only the lift
        p_t = w_grasp + dp
        # approach / retreat clearance: the operator's rest pose is lower than the robot's pinch; before the grasp and after the release the
        # robot hand stays CLEAR above the object (ramped over 1 s), as an operator watching the robot would do. Grasp itself is unchanged.
        p_t = p_t + CLEAR * (clear_w[min(k, len(clear_w) - 1)] if i >= pre else 1.0) * appr
        p_t[2] = max(p_t[2], floor)
        R_t = Rh if ROT == "fixed" else R_cb @ arm_ik.quat_wxyz_to_mat(Q[k]) @ Rg.T @ R_cb.T @ Rh   # fixed: the hand keeps the grasp orientation
        q_prev = dict(kin.a.q); e, _ = kin.a.solve("right", p_t, R_t)
        low = floor - min(kin.palm()[2], kin.a.d.xpos[kin.a.ee["right"]][2])
        if low > 0:                                                  # re-solve the SAME tick from the previous joints (speed cap kept)
            kin.a.q.update(q_prev); kin.a.apply(); e, _ = kin.a.solve("right", p_t + np.array([0, 0, low + 0.005]), R_t)   # palm/wrist would enter the counter keep-out: lift the target
        perr.append(e)
        ci = 0.0 if i < pre else float(c[k]); cc.append(ci)
        hq = rt.step(right=[ci, ci, ci, 0, 0]); kin.a.apply(hq)
        arm.append(kin.a.arm_q()); hand.append(hq); reasons.append(checks(kin)); pinch.append(kin.pinch().copy())
    arm, hand, pinch, cc = np.array(arm), np.array(hand), np.array(pinch), np.array(cc)
    gi = pre + gh
    return dict(arm=arm, hand=hand, reasons=reasons, perr=np.array(perr), pinch=pinch, c=cc, g=np.r_[np.zeros(pre), g], gi=gi, pre=pre,
                t=np.arange(len(arm)) / 30.0, obj_c=obj_c, base=kin.base, aim=aim, seen=seen)


def simulate(name, take, obj, mapping, picked, video=True):
    p1 = plan(take, obj, mapping); obj_c = p1["obj_c"]; aim = p1["aim"]
    # PERCEPTION: object on the mat, robot in the organisers' home pose, head RGB-D -> object position (perceive.py) -> the arm aims there
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import perceive as PC
    mv, dv = build(obj); kh = Kin(); jqv = {mujoco.mj_id2name(mv, mujoco.mjtObj.mjOBJ_JOINT, j): mv.jnt_qposadr[j] for j in range(mv.njnt)}
    for nm, v in kh.a.q.items(): dv.qpos[jqv[nm]] = v
    obv = mujoco.mj_name2id(mv, mujoco.mjtObj.mjOBJ_BODY, "obj"); av = mv.jnt_qposadr[mv.body_jntadr[obv]]
    dv.qpos[av:av + 3] = obj_c; dv.qpos[av + 3:av + 7] = obj_quat(obj); mujoco.mj_forward(mv, dv)
    rgb_h, dep_h, mk_h = PC.render_head(mv, dv, seg_geom=mujoco.mj_name2id(mv, mujoco.mjtObj.mjOBJ_GEOM, "obj_g"))
    seen, pinfo = PC.locate(rgb_h, dep_h, PC.cam_pose(mv, dv), obj, OBJECTS[obj]["size"][0], z_plane=obj_c[2], mask=mk_h)
    if seen is None: seen = obj_c; pinfo["fallback"] = "ground truth (object not visible)"
    os.makedirs(OUT, exist_ok=True); cv2.imwrite(os.path.join(OUT, f"{name}_headcam.jpg"), rgb_h[:, :, ::-1])
    corr = np.zeros(3)
    p2 = plan(take, obj, mapping, obj_seen=seen); dz = 0.0
    top = p2["base"][2] + COUNTER_Z; stand_top = obj_c[2] - half_h(obj)
    m, d = build(obj, stand=(obj_c[0], obj_c[1], stand_top) if stand_top > top + 0.005 else None)
    act = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, m.actuator_trnid[a, 0]): a for a in range(m.nu)}
    jq = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j): m.jnt_qposadr[j] for j in range(m.njnt)}
    ob = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "obj"); og = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "obj_g")
    hb = {b for b in range(m.nbody) if "right_hand" in (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, b) or "")}
    names = [j["joint"] for j in G1Dex3Retargeter().joints]
    def setq(arm, hand, ctrl=True):
        for n, v in zip(arm_ik.ARM_NAMES, arm):
            if ctrl: d.ctrl[act[n]] = v
            else: d.qpos[jq[n]] = v
        for n, v in zip(names, hand):
            if ctrl: d.ctrl[act[n]] = v
            else: d.qpos[jq[n]] = v
    mujoco.mj_resetData(m, d)
    for nm in act:
        if nm in jq and nm.startswith(("left_", "right_")) and ("shoulder" in nm or "elbow" in nm or "wrist" in nm): pass
    setq(p2["arm"][0], p2["hand"][0], ctrl=False); setq(p2["arm"][0], p2["hand"][0])
    a = m.jnt_qposadr[m.body_jntadr[ob]]; d.qpos[a:a + 3] = obj_c + np.array([0, 2.0, 0]); d.qpos[a + 3:a + 7] = obj_quat(obj)   # parked aside: placed when the arm hovers
    mujoco.mj_forward(m, d)
    spt = int(round(1 / 30 / m.opt.timestep)); brk = OBJECTS[obj]["brk"]
    F, held_t, broke, lifted_max, frames, lifts = [], [], False, 0.0, [], []
    rend = mujoco.Renderer(m, 480, 640) if video else None
    if video:
        cam = mujoco.MjvCamera(); cam.type = mujoco.mjtCamera.mjCAMERA_FREE; cam.lookat[:] = obj_c + np.array([0, 0, 0.05]); cam.distance, cam.azimuth, cam.elevation = 0.75, 145, -20
        look = cv2.imread(os.path.join(OUT, f"take{take}_look.jpg")) if os.path.exists(os.path.join(OUT, f"take{take}_look.jpg")) else None
        if look is not None: look = cv2.resize(look, (640, 360))[:, :, ::-1]
    z0 = obj_c[2]
    for i in range(len(p2["arm"])):
        if i == p2["pre"]:                                          # staff places the object once the robot hovers above the mat
            d.qpos[a:a + 3] = obj_c; d.qpos[a + 3:a + 7] = obj_quat(obj); d.qvel[m.body_dofadr[ob]:m.body_dofadr[ob] + 6] = 0; mujoco.mj_forward(m, d)
        setq(p2["arm"][i], p2["hand"][i]); acc = 0.0
        for _ in range(spt):
            mujoco.mj_step(m, d)
            f6 = np.zeros(6)
            for kk in range(d.ncon):
                cn = d.contact[kk]
                if og in (cn.geom1, cn.geom2):
                    other = m.geom_bodyid[cn.geom2 if cn.geom1 == og else cn.geom1]
                    if other in hb: mujoco.mj_contactForce(m, d, kk, f6); acc += abs(f6[0])
        f = acc / spt; F.append(f)
        if brk and np.mean(F[-3:]) > brk and obj == "egg": broke = True    # 0.1 s mean: contact chatter filtered, a sustained squeeze breaks it
        lift = d.qpos[a + 2] - z0; lifted_max = max(lifted_max, lift); lifts.append(lift)
        if video:
            if broke: m.geom_rgba[og] = [0.9, 0.15, 0.15, 1]
            rend.update_scene(d, cam); A = rend.render().copy(); rend.update_scene(d, "head_cam"); B = rend.render().copy()
            st = "ROTTO" if broke else ("in mano, sollevato %.0f cm" % (100 * lift) if lift > 0.02 else "sul tavolo")
            lines = [f"{name}: {obj} | profilo: {mapping} (oggetto dal picker: {picked})", f"t {p2['t'][i]:4.1f}s  guanto g={p2['g'][i]:.2f} -> chiusura G1 {p2['c'][i]:.2f}",
                     f"forza {f:5.1f} N | {st}", "safety: " + (",".join(p2["reasons"][i]) or "ok")]
            for li, s in enumerate(lines):
                cv2.putText(A, s, (10, 22 + 20 * li), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 0, 0), 3, cv2.LINE_AA); cv2.putText(A, s, (10, 22 + 20 * li), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.putText(B, "camera in testa G1 (D435i, simulata)", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
            row = np.concatenate([A, B], 1)
            row = np.concatenate([row, plot_panel(p2, F, lifts, i, OBJECTS[obj]["brk"])], 0)
            frames.append(row[:, :, ::-1])
    F = np.array(F); g_hold = p2["c"] > 0.05
    clipped = sum(1 for r in p2["reasons"] if r)
    res = {"scenario": name, "take": take, "object": obj, "picked": picked, "mapping": mapping, "cap": PROFILE.get(obj, PROFILE["unknown"])["cap"],
           "robot_closure_max": round(float(p2["c"].max()), 2), "force_peak_N": round(float(F.max()), 1),
           "force_median_while_closed_N": round(float(np.median(F[g_hold])) if g_hold.any() else 0.0, 1),
           "lifted_max_cm": round(100 * lifted_max, 1), "held_and_lifted": bool(lifted_max > 0.05 and not broke), "broken": broke,
           "dented": bool(obj == "can_empty" and F.max() > (OBJECTS[obj]["brk"] or 1e9)),
           "ik_err_median_cm": round(100 * float(np.median(p2["perr"])), 1), "ik_err_p95_cm": round(100 * float(np.percentile(p2["perr"], 95)), 1),
           "safety_ticks_flagged": clipped, "safety_reasons": sorted({x for r in p2["reasons"] for x in r}), "stand_cm": round(100 * float(max(0.0, (obj_c[2] - half_h(obj)) - (p2["base"][2] + COUNTER_Z))), 1), "hand_orientation": ROT, "arms": ARMS, "perception_err_cm": round(100 * float(np.linalg.norm((seen - obj_c)[:2])), 2), "perception": pinfo, "aim_corr_cm": [round(100 * float(x), 1) for x in corr], "pinch_to_aim_at_grasp_cm": round(100 * float(np.linalg.norm(p2["pinch"][p2["gi"]] - obj_c - aim)), 1), "aim_cm": [round(100 * float(x), 1) for x in aim],
           "arm_q_in_filter": bool(all(arm_ik.FILTER[n][0] - 1e-9 <= v <= arm_ik.FILTER[n][1] + 1e-9 for row in p2["arm"] for n, v in zip(arm_ik.ARM_NAMES, row))),
           "max_arm_step_rad": round(float(np.abs(np.diff(p2["arm"], axis=0)).max()), 3), "max_hand_step_rad": round(float(np.abs(np.diff(p2["hand"], axis=0)).max()), 3)}
    if video and frames:
        w = cv2.VideoWriter(os.path.join(OUT, f"{name}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 30, (frames[0].shape[1], frames[0].shape[0]))
        for fr in frames: w.write(fr)
        w.release()
    return res


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--only"); ap.add_argument("--no-video", action="store_true"); ap.add_argument("--no-picker", action="store_true")
    a = ap.parse_args(); os.makedirs(OUT, exist_ok=True)
    picks = {}
    out = []
    for name, (take, obj, mapping) in SCENARIOS.items():
        if a.only and name != a.only: continue
        if take not in picks: picks[take] = (obj, "label", "skipped") if a.no_picker else pick(take, obj)
        picked, src, det = picks[take]
        prof_obj = picked if picked in PROFILE else ("unknown" if src == "picker" else obj)
        r = simulate(name, take, obj if mapping != "profile" else obj, mapping, f"{picked} ({src})", video=not a.no_video)
        if mapping == "profile" and prof_obj != obj: r["warning"] = f"picker said {picked}: the profile used on the robot would be {prof_obj}"
        r["picker_detail"] = det[-200:]; out.append(r); print(json.dumps(r))
    json.dump(out, open(os.path.join(OUT, "report.json"), "w"), indent=1)



def calibrate_grasp(obj, cap, cache=os.path.join(OUT, "grasp_offsets.json")):
    """Physics search for where the object must be relative to the grasp posture so that closing to `cap` and lifting 10 cm HOLDS it.
    Arm at GRASP_ARM moved so the pinch is at object + offset; offsets on a grid (x, y in +-3 cm, z in -2..+2 cm); result cached per object/cap.
    This is the simulated equivalent of the operator aiming by looking. Returns (offset (3,), table of trials)."""
    key = f"{obj}@{cap:.2f}"
    db = json.load(open(cache)) if os.path.exists(cache) else {}
    if key in db: return np.array(db[key]["offset"]), db[key]["trials"]
    kin = Kin(); rt0 = G1Dex3Retargeter(max_closure=1.0)
    for n, v in GRASP_ARM.items(): kin.a.q[n] = v
    for _ in range(30): hq0 = rt0.step(right=[0.5 * cap] * 3 + [0, 0])
    kin.a.apply(hq0); w0 = kin.a.d.xpos[kin.a.ee["right"]].copy(); Rg = kin.a.d.xmat[kin.a.ee["right"]].reshape(3, 3).copy(); pin0 = kin.pinch().copy()
    top = kin.base[2] + COUNTER_Z; obj_c = np.array([pin0[0], pin0[1], top + half_h(obj)])
    m, d = build(obj); names = [j["joint"] for j in G1Dex3Retargeter().joints]
    act = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, m.actuator_trnid[a, 0]): a for a in range(m.nu)}
    jq = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j): m.jnt_qposadr[j] for j in range(m.njnt)}
    ob = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "obj"); oa = m.jnt_qposadr[m.body_jntadr[ob]]; spt = int(round(1 / 30 / m.opt.timestep))
    trials = []
    for dz in (-0.02, -0.01, 0.0, 0.01):
        for dx in (-0.03, -0.015, 0.0, 0.015, 0.03):
            for dy in (-0.03, -0.015, 0.0, 0.015, 0.03):
                off = np.array([dx, dy, dz])
                # IK: pinch at obj_c + off  (wrist shifted by the same vector), then 10 cm straight up
                k2 = Kin()
                for n, v in GRASP_ARM.items(): k2.a.q[n] = v
                k2.a.apply(hq0); wt = w0 + (obj_c + off - pin0)
                for _ in range(80): k2.a.solve("right", wt, Rg)
                if np.linalg.norm(k2.a.d.xpos[k2.a.ee["right"]] - wt) > 0.01: continue
                q_grasp = k2.a.arm_q(); path = []
                for s in range(30): k2.a.solve("right", wt + np.array([0, 0, 0.10 * (s + 1) / 30]), Rg); path.append(k2.a.arm_q())
                mujoco.mj_resetData(m, d)
                for n, v in zip(arm_ik.ARM_NAMES, q_grasp): d.qpos[jq[n]] = v; d.ctrl[act[n]] = v
                for n in names: d.ctrl[act[n]] = 0.0
                d.qpos[oa:oa + 3] = obj_c; d.qpos[oa + 3:oa + 7] = obj_quat(obj); mujoco.mj_forward(m, d)
                if any(og in (c.geom1, c.geom2) and c.dist < -0.002 for c in d.contact[:d.ncon] for og in [mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "obj_g")]): continue
                rt = G1Dex3Retargeter(max_closure=1.0); fpk = 0.0
                for t in range(60):                                   # 2 s: close to the cap
                    hq = rt.step(right=[cap] * 3 + [0, 0])
                    for n, v in zip(names, hq): d.ctrl[act[n]] = v
                    for _ in range(spt): mujoco.mj_step(m, d)
                for t in range(45):                                   # 1.5 s: lift 10 cm (30 ticks) + hold
                    for n, v in zip(arm_ik.ARM_NAMES, path[min(t, 29)]): d.ctrl[act[n]] = v
                    for _ in range(spt): mujoco.mj_step(m, d)
                lift = float(d.qpos[oa + 2] - obj_c[2]); trials.append({"off_cm": [round(100 * x, 1) for x in off], "lift_cm": round(100 * lift, 1)})
    best = max(trials, key=lambda r: (r["lift_cm"] > 7, -np.linalg.norm(r["off_cm"]))) if trials else {"off_cm": [0, 0, 0], "lift_cm": 0}
    db[key] = {"offset": [x / 100 for x in best["off_cm"]], "lift_cm": best["lift_cm"], "n_held": sum(r["lift_cm"] > 7 for r in trials), "n": len(trials), "trials": trials}
    os.makedirs(OUT, exist_ok=True); json.dump(db, open(cache, "w"), indent=1)
    return np.array(db[key]["offset"]), trials


if __name__ == "__main__":
    main()
