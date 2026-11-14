"""G1 Dex3 grasp physics in MuJoCo: how hard does the RIGHT hand squeeze each object at each commanded closure, and does it hold it?
  py -3.11 g1/sim/grasp_physics.py [--objects egg,ball,can] [--kp 1.5] [--render]  -> data/g1sim/grasp/{report.json,REPORT.md,*.png}
Setup: official G1 29-DoF + Dex3 MJCF (fetched by g1_sim.py), base fixed, body held by stiff position servos + gravity compensation,
only the right-hand subtree collides. Hand joints = position servos (kp, kv) with the URDF torque limits (1.4 / 2.45 Nm), commands from
robot.g1_dex3.G1Dex3Retargeter (unchanged, same mapping as the real robot path) with closure c in 0..1 on index+middle (thumb coupled).
Object rests on a thin pedestal between thumb and fingers; per closure level: close, settle, read the normal contact force hand<->object,
then drop the pedestal and check whether the object stays in the hand (held = moved < 1.5 cm in 1 s).
ASSUMPTIONS (to replace with measurements): servo gains kp/kv of the real Dex3, object sizes/masses, friction 1.0, break thresholds
(egg 20 N, empty can 15 N, stress ball none). Rigid objects except the ball (soft contact only, no real deformation).
The force numbers are MODEL outputs, not measurements: what transfers to the robot is the CLOSURE at which contact starts, holding
succeeds and force grows, i.e. a per-object closure cap."""
import argparse, json, os, sys
import numpy as np, mujoco

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from robot.g1_dex3 import G1Dex3Retargeter

ASSETS = os.path.join(ROOT, "data", "g1sim", "assets_g1", "g1_body29_hand14.xml")
OUT = os.path.join(ROOT, "data", "g1sim", "grasp")

# name: geom spec, mass kg, break threshold N (None = cannot break), soft contact?
OBJECTS = {
    "egg":  dict(type="ellipsoid", size=[0.021, 0.021, 0.028], mass=0.060, brk=20.0, soft=False),
    "ball": dict(type="sphere",    size=[0.033],               mass=0.030, brk=None, soft=True),
    "can":  dict(type="cylinder",  size=[0.033, 0.058],        mass=0.015, brk=15.0, soft=False),
}
# right arm posture: forearm forward (elbow 0 = horizontal), wrist rolled so the palm faces the body midline and fingers close sideways (checked with --render)
ARM = {"right_shoulder_pitch_joint": -0.4, "right_shoulder_roll_joint": -0.25, "right_shoulder_yaw_joint": 0.0,
       "right_elbow_joint": 0.3, "right_wrist_roll_joint": -1.57, "right_wrist_pitch_joint": 0.0, "right_wrist_yaw_joint": 0.0}


def build(obj, kp, kv):
    spec = mujoco.MjSpec.from_file(ASSETS)
    spec.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    spec.delete(spec.joint("floating_base_joint"))
    spec.body("pelvis").pos = [0, 0, 0.8]
    for b in spec.bodies: b.gravcomp = 1.0
    hand = set()
    def collect(b):
        hand.add(b.name)
        for c in b.bodies: collect(c)
    collect(spec.body("right_wrist_yaw_link"))
    for g in spec.geoms:
        if g.parent.name in hand: g.contype, g.conaffinity, g.friction, g.condim = 1, 1, [1.0, 0.005, 0.0001], 4
        else: g.contype, g.conaffinity = 0, 0
    for a in spec.actuators:
        j = spec.joint(a.target)
        is_hand = "_hand_" in a.target
        k, d = (kp, kv) if is_hand else (300.0, 20.0)
        a.gaintype = mujoco.mjtGain.mjGAIN_FIXED; a.gainprm[0] = k
        a.biastype = mujoco.mjtBias.mjBIAS_AFFINE; a.biasprm[0] = 0; a.biasprm[1] = -k; a.biasprm[2] = -d
        a.ctrllimited = 0
        if is_hand and j.armature < 1e-4: j.armature = 0.002   # motor rotor inertia through the gearbox (assumed; keeps the servo stable)
    o = OBJECTS[obj]
    body = spec.worldbody.add_body(name="obj", pos=[0, 0, 0])
    body.add_freejoint()
    gt = {"ellipsoid": mujoco.mjtGeom.mjGEOM_ELLIPSOID, "sphere": mujoco.mjtGeom.mjGEOM_SPHERE, "cylinder": mujoco.mjtGeom.mjGEOM_CYLINDER}[o["type"]]
    g = body.add_geom(name="obj_g", type=gt, size=o["size"] + [0] * (3 - len(o["size"])), mass=o["mass"], rgba=[0.95, 0.85, 0.6, 1],
                      contype=3, conaffinity=3, friction=[1.0, 0.005, 0.0001], condim=4)
    if o["soft"]: g.solref = [0.03, 1.0]; g.solimp = [0.5, 0.95, 0.015, 0.5, 2]   # compliant contact: a foam ball sinks ~1-1.5 cm
    ped = spec.worldbody.add_body(name="ped", mocap=True, pos=[0, 0, 0])
    ped.add_geom(type=mujoco.mjtGeom.mjGEOM_CYLINDER, size=[0.008, 0.25, 0], contype=2, conaffinity=2, rgba=[0.5, 0.5, 0.5, 1])
    m = spec.compile(); d = mujoco.MjData(m)
    return m, d


class Rig:
    def __init__(self, obj, kp, kv):
        self.obj, self.m, self.d = obj, *build(obj, kp, kv)
        m = self.m
        self.act = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, m.actuator_trnid[a, 0]): a for a in range(m.nu)}
        self.jq = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j): m.jnt_qposadr[j] for j in range(m.njnt)}
        self.ob = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "obj"); self.og = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "obj_g")
        self.hand_bodies = {b for b in range(m.nbody) if "right_hand" in (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, b) or "")}
        self.names = [j["joint"] for j in G1Dex3Retargeter().joints]

    def set_ctrl(self, hand_q):
        for n, v in ARM.items(): self.d.ctrl[self.act[n]] = v
        for n, v in zip(self.names, hand_q): self.d.ctrl[self.act[n]] = v

    def place(self):
        """Pose the arm with the hand open, then put the object centre between the thumb tip and the index/middle tips."""
        m, d = self.m, self.d
        mujoco.mj_resetData(m, d)
        for n, v in ARM.items(): d.qpos[self.jq[n]] = v
        rt = G1Dex3Retargeter(max_closure=1.0); q0 = rt.step(right=[0.0] * 5)
        for n, v in zip(self.names, q0): d.qpos[self.jq[n]] = v
        a = m.jnt_qposadr[m.body_jntadr[self.ob]]; d.qpos[a:a + 3] = [0, 0, -5]   # park the object away while measuring the hand
        mujoco.mj_forward(m, d)
        tip = lambda n: d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, n)]
        fingers = (tip("right_hand_index_1_link") + tip("right_hand_middle_1_link")) / 2
        thumb = tip("right_hand_thumb_2_link"); palm = d.xpos[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "right_wrist_yaw_link")]
        c0 = 0.5 * (fingers + thumb)   # midpoint of the opening
        self.fit, self.shift_cm = False, None
        g = np.arange(-0.04, 0.0401, 0.01)               # nearest non-intersecting centre in a 8 cm cube around the opening midpoint
        cands = sorted(((float(np.linalg.norm([x, y, z])), np.array([x, y, z])) for x in g for y in g for z in g), key=lambda t: t[0])
        for dist, off in cands:
            c = c0 + off
            d.qpos[a:a + 3] = c; d.qpos[a + 3:a + 7] = [1, 0, 0, 0]; mujoco.mj_forward(m, d)
            pen = max([-con.dist for con in d.contact[:d.ncon] if self.og in (con.geom1, con.geom2)] + [0.0])
            if pen < 1e-3: self.fit, self.shift_cm = True, round(100 * dist, 1); break
        if not self.fit: c = c0
        d.qpos[a:a + 3] = c
        bottom = self._half_height()
        d.mocap_pos[0] = c - np.array([0, 0, bottom + 0.25 + 1e-4])
        mujoco.mj_forward(m, d)
        self.center0 = c.copy()
        return q0

    def _half_height(self):
        o = OBJECTS[self.obj]; s = o["size"]
        return s[2] if o["type"] == "ellipsoid" else (s[1] if o["type"] == "cylinder" else s[0])

    def force(self):
        """Sum of normal contact forces hand<->object (N) and number of distinct hand bodies touching."""
        m, d = self.m, self.d; f6 = np.zeros(6); tot = 0.0; touching = set()
        for i in range(d.ncon):
            c = d.contact[i]; b1, b2 = m.geom_bodyid[c.geom1], m.geom_bodyid[c.geom2]
            if self.og not in (c.geom1, c.geom2): continue
            other = b2 if c.geom1 == self.og else b1
            if other not in self.hand_bodies: continue
            mujoco.mj_contactForce(m, d, i, f6); tot += abs(f6[0]); touching.add(other)
        return tot, len(touching)

    def run(self, closure, settle_s=1.0, hold_s=1.0):
        m, d = self.m, self.d
        self.place()
        rt = G1Dex3Retargeter(max_closure=1.0)
        steps_per_tick = int(round(1 / 30 / m.opt.timestep))
        f_close = []                                    # per-tick force, averaged over the physics substeps (contact chatter filtered)
        for _ in range(int(settle_s * 30)):            # 30 Hz command stream with the retargeter slew limit, like the robot path
            self.set_ctrl(rt.step(right=[0, closure, closure, 0, 0]))
            acc = 0.0
            for _ in range(steps_per_tick): mujoco.mj_step(m, d); acc += self.force()[0]
            f_close.append(acc / steps_per_tick)
        f_settled = float(np.mean(f_close[-6:])); n_touch = self.force()[1]
        a = m.jnt_qposadr[m.body_jntadr[self.ob]]; before = d.qpos[a:a + 3].copy()
        f_hold = []
        for k in range(int(hold_s * 30)):               # pedestal drops 30 cm: does the hand alone hold the object?
            d.mocap_pos[0][2] -= 0.01
            acc = 0.0
            for _ in range(steps_per_tick): mujoco.mj_step(m, d); acc += self.force()[0]
            f_hold.append(acc / steps_per_tick)
        moved = float(np.linalg.norm(d.qpos[a:a + 3] - before))
        peak = float(max(f_close + f_hold))
        return dict(closure=closure, fits_open_hand=self.fit, shift_cm=self.shift_cm, force_settled_N=round(f_settled, 2), force_peak_N=round(peak, 2), fingers_touching=n_touch,
                    held=bool(moved < 0.015), moved_cm=round(min(100 * moved, 99.0), 1))

    def render(self, path, closure):
        self.run(closure, hold_s=0.0)
        r = mujoco.Renderer(self.m, 480, 640); cam = mujoco.MjvCamera(); cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        cam.lookat[:] = self.center0; cam.distance, cam.azimuth, cam.elevation = 0.35, 150, -25
        r.update_scene(self.d, cam); img = r.render()
        import cv2; cv2.imwrite(path, img[:, :, ::-1])


def summarize(obj, rows):
    brk = OBJECTS[obj]["brk"]
    if not rows[0]["fits_open_hand"]: return dict(fits_open_hand=False, note="object intersects the open hand in this posture: no measurement", break_threshold_N=brk)
    contact = next((r["closure"] for r in rows if r["force_settled_N"] > 0.2), None)
    hold = next((r["closure"] for r in rows if r["held"]), None)
    broke = next((r["closure"] for r in rows if brk is not None and r["force_peak_N"] > brk), None)
    cap = None
    if hold is not None:
        cap = round(hold + 0.10, 2)
        if broke is not None: cap = min(cap, round(broke - 0.05, 2))
        if broke is not None and broke <= hold: cap = None
    return dict(contact_closure=contact, min_hold_closure=hold, break_closure=broke, recommended_max_closure=cap, break_threshold_N=brk)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--objects", default="egg,ball,can"); ap.add_argument("--kp", type=float, default=1.5); ap.add_argument("--kv", type=float, default=0.1)
    ap.add_argument("--levels", default="0,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.0"); ap.add_argument("--render", action="store_true")
    a = ap.parse_args(); os.makedirs(OUT, exist_ok=True)
    if not os.path.exists(ASSETS): sys.exit("run g1/sim/g1_sim.py once to fetch the G1 model")
    levels = [float(x) for x in a.levels.split(",")]
    report = {"kp": a.kp, "kv": a.kv, "objects": {}}
    for obj in a.objects.split(","):
        rig = Rig(obj, a.kp, a.kv); rows = [rig.run(c) for c in levels]
        report["objects"][obj] = {"spec": OBJECTS[obj], "rows": rows, "summary": summarize(obj, rows)}
        print(obj, report["objects"][obj]["summary"])
        for r in rows: print("   ", r)
        if a.render:
            for c in (0.0, 0.5, 1.0): rig.render(os.path.join(OUT, f"{obj}_{int(c * 100):03d}.png"), c)
    json.dump(report, open(os.path.join(OUT, f"report_kp{a.kp}.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
