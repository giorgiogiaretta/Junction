"""DEMO (gloves + computer vision): the G1 head camera recognises each object (Tommaso's ai.perceive + geometry vote, the same code
the real-robot policy uses), the closure cap follows the RECOGNISED object, and the grasp is driven by the operator's REAL glove takes
recorded on 14/11 (no Coil needed). Ends with the same egg take WITHOUT vision (full force) to show why recognition matters.

  py -3.11 g1/sim/demo_cv.py                       # renders data/video/demo_cv.mp4 (~75 s, 1920x1080) and shows it live
  py -3.11 g1/sim/demo_cv.py --no-show             # render only
  py -3.11 g1/sim/demo_cv.py --live                # YOUR right glove (Rokoko driver running) instead of the takes; key N = next object, Q = quit
  py -3.11 g1/sim/demo_cv.py --vlm nemotron        # add the NVIDIA Nemotron VLM to the recogniser ensemble (needs VERDA_INFERENCE_KEY)

Same state machine as g1/sim/live_sim.py (no Coil): glove closed -> descend 1 s -> grasp (closure = cap x grip / usual grip) -> lift 12 cm
after 1.5 s -> glove open -> release. Physics: MuJoCo, hand servos and break thresholds as in the other sims (assumed, not measured)."""
import argparse, os, sys, time
import numpy as np, mujoco, cv2

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, "g1"), os.path.join(ROOT, "Rokoko", "src")]
import demo_e2e as D, perceive as PC, teleop_multi as TM, arm_ik
from robot.g1_dex3 import G1Dex3Retargeter
from g1.perception_v1 import perceive, perceive_with_ai, pinhole_pixel_to_pelvis, robot_mask, CAP as PV_CAP

RATE = 30
K_SIM = np.array([[PC.FX, 0, PC.CX], [0, PC.FX, PC.CY], [0, 0, 1.0]])
SPOT = (0.35, -0.15)                                     # work spot of the right hand (pelvis frame, m)
PARK = {"stress_ball": (0.33, 0.10), "can_empty": (0.43, 0.18), "egg": (0.46, 0.00)}    # waiting objects, in view, left side
TAKES = {"stress_ball": 80, "can_empty": 85, "egg": 77}  # operator's real right-glove takes of 14/11, one per object
NAME = {"stress_ball": "STRESS BALL", "can_empty": "EMPTY CAN", "egg": "EGG", "unknown": "UNKNOWN"}
COL = {"stress_ball": (40, 140, 255), "can_empty": (60, 200, 230), "egg": (235, 235, 235), "unknown": (160, 160, 160)}   # BGR
# closure cap per RECOGNISED object in this simulation (sim egg holds 0.55 and breaks from 0.60, measured with take 77; ball 0.70 and
# can 0.60 lift 13-15 cm). The real robot uses its own caps (g1/perception_v1.CAP: egg 0.70 hardware fraction).
SIM_CAP = {"egg": 0.55, "stress_ball": 1.00, "can_empty": 0.90, "unknown": 0.50}   # operator 15/11: egg light, ball 1.0, can 0.9
W, H = 1920, 1080
BG, PANEL, TXT, ACC = (24, 22, 28), (38, 36, 44), (235, 235, 240), (60, 200, 120)


def put(img, s, xy, sc=0.6, col=TXT, th=1):
    cv2.putText(img, s, xy, cv2.FONT_HERSHEY_SIMPLEX, sc, col, th, cv2.LINE_AA)


class TakeGlove:
    def __init__(self, take):
        z = np.load(os.path.join(ROOT, "data", "episodes", f"take_{take:02d}.npz")); self.F = z["right_fingers01"].astype(float); self.i = 0
    def read(self):
        f = self.F[min(self.i, len(self.F) - 1)] if self.i < len(self.F) else np.zeros(5); self.i += 1; return f
    def done(self): return self.i >= len(self.F) + 2 * RATE


class LiveGlove:
    def __init__(self):
        from live_sim import GloveLive
        self.g = GloveLive("right")
    def read(self):
        r = self.g.read(); return np.zeros(5) if r is None else np.asarray(r[0], float)
    def done(self): return False


class Demo:
    def __init__(self, vlm=(), engine="g1"):
        self.objs = ["stress_ball", "can_empty", "egg"]
        self.m, self.d = TM.build_multi([(o, None) for o in self.objs]); m = self.m
        m.vis.global_.offwidth, m.vis.global_.offheight = 1920, 1080
        self.kin = D.Kin(); self.vlm = tuple(vlm); self.engine = engine; self.assist = True
        self.act = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, m.actuator_trnid[i, 0]): i for i in range(m.nu)}
        self.jq = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j): m.jnt_qposadr[j] for j in range(m.njnt)}
        self.home = dict(self.kin.a.q)
        for n, v in self.kin.a.q.items():
            if n in self.jq: self.d.qpos[self.jq[n]] = v; self.d.ctrl[self.act[n]] = v
        self.ob = {o: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f"obj_{o}") for o in self.objs}
        self.og = {o: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, f"g_{o}") for o in self.objs}
        self.oa = {o: m.jnt_qposadr[m.body_jntadr[self.ob[o]]] for o in self.objs}
        self.od = {o: m.body_dofadr[self.ob[o]] for o in self.objs}
        self.hand_bodies = {b for b in range(m.nbody) if "right_hand" in (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, b) or "")}
        self.rgba0 = {o: m.geom_rgba[self.og[o]].copy() for o in self.objs}
        self.names = [j["joint"] for j in G1Dex3Retargeter().joints]
        self.spt = int(round(1 / RATE / m.opt.timestep))
        self.view = mujoco.Renderer(m, 760, 1100); self.cam = mujoco.MjvCamera()
        self.cam.lookat[:] = [0.30, -0.02, D.PELVIS_Z + 0.02]; self.cam.distance, self.cam.azimuth, self.cam.elevation = 1.45, 205, -24
        self.headr = mujoco.Renderer(m, 480, 640)
        self.fhist, self.chist, self.caphist = [], [], []

    # ---------------------------------------------------------------- scene
    def place(self, work):
        for o in self.objs:
            x, y = SPOT if o == work else PARK[o]
            a = self.oa[o]; self.d.qpos[a:a + 3] = self.kin.base + np.array([x, y, D.COUNTER_Z + D.half_h(o)])
            self.d.qpos[a + 3:a + 7] = D.obj_quat(o); self.d.qvel[self.od[o]:self.od[o] + 6] = 0
            self.m.geom_rgba[self.og[o]] = self.rgba0[o]
        for n, v in self.home.items():
            if n in self.jq: self.d.qpos[self.jq[n]] = v; self.d.ctrl[self.act[n]] = v
        for n in self.names: self.d.qpos[self.jq[n]] = 0.0; self.d.ctrl[self.act[n]] = 0.0
        self.kin.a.q.update(self.home); self.kin.a.apply(); mujoco.mj_forward(self.m, self.d)
        for _ in range(20): mujoco.mj_step(self.m, self.d)

    def cam_T(self):
        pos, R = PC.cam_pose(self.m, self.d); T = np.eye(4); T[:3, :3] = R @ np.diag([1, -1, -1]); T[:3, 3] = pos - self.kin.base; return T

    def project(self, p_world, T):
        pc = T[:3, :3].T @ (p_world - self.kin.base - T[:3, 3])
        if pc[2] <= 0.05: return None
        u, v, w = K_SIM @ pc; return int(u / w), int(v / w)

    # ---------------------------------------------------------------- computer vision (same code as the real-robot policy)
    def recognise(self):
        rgb, dep = PC.render_head(self.m, self.d); T = self.cam_T()
        armq = [self.kin.a.q[n] for n in arm_ik.ARM_NAMES]
        sm = robot_mask(armq, None, K_SIM, T)(dep)
        t0 = time.time(); res = (perceive_with_ai if self.engine == "ai" else perceive)(rgb, dep, pinhole_pixel_to_pelvis(K_SIM, T), vlm=self.vlm, self_mask=sm)
        res["t_wall"] = round(time.time() - t0, 2); return rgb, res, T

    # ---------------------------------------------------------------- one grasp episode
    def grasp(self, work, glove, cap, label, title, sub, writer, show, rec, broken_ok=False):
        m, d, kin = self.m, self.d, self.kin
        pr = D.PROFILE[work]; bg = D.best_grasp(work); posture, aim, _ = bg
        seen = self.kin.base + np.array(rec["p_pelvis"]) if rec is not None else self.kin.base + np.array([SPOT[0], SPOT[1], D.COUNTER_Z + D.half_h(work)])
        k0 = D.Kin(); rt0 = G1Dex3Retargeter(max_closure=1.0)
        for _ in range(30): hq0 = rt0.step(right=[0.5 * pr["cap"]] * 3 + [0, 0])
        for n, v in posture.items(): k0.a.q[n] = v
        k0.a.apply(hq0); ee = k0.a.ee["right"]; w0 = k0.a.d.xpos[ee].copy(); Rg = k0.a.d.xmat[ee].reshape(3, 3).copy()
        w_grasp = w0 + (seen + aim - k0.pinch()); floor = kin.base[2] + D.KEEP["z"] + 0.01
        rt = G1Dex3Retargeter(max_closure=1.0)
        # approach: the can is taken from the SIDE (grasp_search.py best posture, palm facing the can): hover 10 cm out along the
        # palm normal instead of above, so the fingers never brush the top of the can on the way down
        if work == "can_empty":
            n_out = -Rg[:, 1]; n_out[2] = 0.0; n_out /= max(np.linalg.norm(n_out), 1e-6); approach = 0.10 * n_out + np.array([0, 0, 0.02])
        else: approach = np.array([0, 0, 0.10])
        hb = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "right_wrist_yaw_link"); carry = None; a_obj = self.oa[work]; d_obj = self.od[work]
        state, t_s, h_lift, t = "HOVER", 0.0, 0.0, 0.0; brk = D.OBJECTS[work]["brk"]; over = 0; broken = False; z0 = d.qpos[self.oa[work] + 2]
        self.fhist, self.chist, self.caphist = [], [], []; f6 = np.zeros(6); og = self.og[work]; max_lift = 0.0; head_img = None; tick = 0
        while not glove.done():
            F = glove.read(); g = 0.5 * (F[1] + F[2])
            if state == "HOVER" and g > 0.3 * pr["g_ref"]: state, t_s = "DESCEND", t
            elif state == "DESCEND" and g < 0.25 * pr["g_ref"]: state = "HOVER"
            elif state == "DESCEND" and t - t_s > 1.0: state, t_s = "GRASP", t
            elif state in ("GRASP", "LIFT") and g < 0.25 * pr["g_ref"]: state, t_s = "RELEASE", t
            elif state == "GRASP" and t - t_s > 1.5: state = "LIFT"
            elif state == "RELEASE" and t - t_s > 1.0 and h_lift <= 0.003: state = "HOVER"
            if state == "LIFT": h_lift = min(0.12, h_lift + 0.12 / RATE)
            elif state == "RELEASE": h_lift = max(0.0, h_lift - 0.25 / RATE)
            elif state in ("HOVER", "DESCEND", "GRASP"): h_lift = 0.0
            clear = {"HOVER": 1.0, "DESCEND": max(0.0, 1 - (t - t_s)), "GRASP": 0.0, "LIFT": 0.0, "RELEASE": 0.0 if h_lift > 0.003 else min(1.0, t - t_s - 0.5)}[state]
            clear = max(0.0, clear)
            target = w_grasp + clear * approach + np.array([0, 0, h_lift]); target[2] = max(target[2], floor)
            q_prev = dict(kin.a.q); kin.a.solve("right", target, Rg)
            if D.checks(kin): kin.a.q.update(q_prev); kin.a.apply()
            c = cap * float(np.clip(g / pr["g_ref"], 0, 1)) if state in ("GRASP", "LIFT") else 0.0
            hq = rt.step(right=[c, c, c, 0, 0])
            for n, v in zip(arm_ik.ARM_NAMES, kin.a.arm_q()): d.ctrl[self.act[n]] = v
            for n, v in zip(self.names, hq): d.ctrl[self.act[n]] = v
            # DEMO grasp assist: once the hand has closed on the object (>= 60 % of its cap for 0.3 s) the object follows the hand
            # rigidly until release, so a slip in this simple contact model does not drop it ("possible good result", marked on screen)
            if self.assist and carry is None and not broken and state in ("GRASP", "LIFT") and c >= 0.6 * cap and t - t_s > 0.3:
                Rh = d.xmat[hb].reshape(3, 3).copy(); carry = (Rh.T @ (d.qpos[a_obj:a_obj + 3] - d.xpos[hb]), Rh.T @ d.xmat[self.ob[work]].reshape(3, 3).copy())
            if carry is not None and (state == "HOVER" or broken or (state == "RELEASE" and h_lift <= 0.003)):   # put it DOWN first, then let go
                carry = None
                if not broken:      # assist: the object is set down upright where the hand released it (no tumbling from the opening fingers)
                    d.qpos[a_obj + 2] = kin.base[2] + D.COUNTER_Z + D.half_h(work) + 0.001; d.qpos[a_obj + 3:a_obj + 7] = D.obj_quat(work); d.qvel[d_obj:d_obj + 6] = 0.0
                    self.settle = (work, d.qpos[a_obj:a_obj + 7].copy(), 45)
            force = 0.0
            for _ in range(self.spt):
                mujoco.mj_step(m, d); fs = 0.0
                st_ = getattr(self, "settle", None)
                if carry is None and st_ is not None and st_[0] == work and st_[2] > 0:
                    d.qpos[a_obj:a_obj + 7] = st_[1]; d.qvel[d_obj:d_obj + 6] = 0.0
                if carry is not None:
                    Rh = d.xmat[hb].reshape(3, 3); qo = np.zeros(4); mujoco.mju_mat2Quat(qo, (Rh @ carry[1]).flatten())
                    d.qpos[a_obj:a_obj + 3] = d.xpos[hb] + Rh @ carry[0]; d.qpos[a_obj + 3:a_obj + 7] = qo; d.qvel[d_obj:d_obj + 6] = 0.0
                for i in range(d.ncon):
                    cn = d.contact[i]
                    if og in (cn.geom1, cn.geom2) and m.geom_bodyid[cn.geom2 if cn.geom1 == og else cn.geom1] in self.hand_bodies:
                        mujoco.mj_contactForce(m, d, i, f6); fs += abs(f6[0])
                force = max(force, fs)
            if getattr(self, "settle", None) is not None and self.settle[2] > 0: self.settle = (self.settle[0], self.settle[1], self.settle[2] - 1)
            over = over + 1 if (brk and force > brk) else 0
            if over >= 3 and not broken and work == "egg":
                broken = True; m.geom_rgba[og] = [0.95, 0.85, 0.2, 1.0]      # yolk: the egg broke
            lift = 100 * (d.qpos[self.oa[work] + 2] - z0); max_lift = max(max_lift, lift)
            self.fhist.append(force); self.chist.append(c); self.caphist.append(cap)
            if tick % 2 == 0 or head_img is None: head_img = self.head_view(label, rec)
            frame = self.compose(title, sub, state, F, c, cap, force, brk, lift, broken, work, head_img, label, rec)
            if writer is not None: writer.write(frame)
            if show:
                cv2.imshow("G1 x Rokoko x Computer Vision", cv2.resize(frame, (1280, 720))); k = cv2.waitKey(1) & 0xFF
                if k in (ord("q"), 27): raise KeyboardInterrupt
                if k == ord("n") and isinstance(glove, LiveGlove): break
            t += 1 / RATE; tick += 1
        return dict(max_force=round(float(max(self.fhist or [0])), 1), max_lift_cm=round(float(max_lift), 1), broken=broken)

    # ---------------------------------------------------------------- drawing
    def head_view(self, label, rec):
        self.headr.update_scene(self.d, "head_cam"); img = self.headr.render()[:, :, ::-1].copy(); T = self.cam_T()
        for o in self.objs:
            uv = self.project(self.d.xpos[self.ob[o]], T)
            if uv is None: continue
            known = self.det.get(o)
            lab = known["label"] if known else "?"; col = COL.get(lab, COL["unknown"]); r = 34
            cv2.rectangle(img, (uv[0] - r, uv[1] - r), (uv[0] + r, uv[1] + r), col, 2)
            put(img, f"{NAME.get(lab, lab)}  max {known['cap']:.2f}" if known else "?", (uv[0] - r, uv[1] - r - 6), 0.45, col, 1)
        return img

    def compose(self, title, sub, state, F, c, cap, force, brk, lift, broken, work, head_img, label, rec):
        fr = np.full((H, W, 3), BG, np.uint8)
        cv2.rectangle(fr, (0, 0), (W, 70), PANEL, -1)
        put(fr, "G1  x  ROKOKO SMARTGLOVES  x  COMPUTER VISION", (28, 46), 1.05, TXT, 2)
        put(fr, title, (1060, 32), 0.75, ACC, 2); put(fr, sub, (1060, 58), 0.55, (190, 190, 200), 1)
        self.view.update_scene(self.d, self.cam); v = self.view.render()[:, :, ::-1]
        fr[90:850, 20:1120] = v
        put(fr, f"STATE: {state}", (36, 126), 0.9, (255, 255, 255), 2)
        if broken: put(fr, "EGG BROKEN", (36, 170), 1.2, (60, 60, 255), 3)
        hv = cv2.resize(head_img, (760, 570)); fr[90:660, 1140:1900] = hv
        cv2.rectangle(fr, (1140, 90), (1900, 660), (90, 90, 100), 1)
        put(fr, "G1 HEAD CAMERA (RGB-D)  +  object recognition", (1150, 682), 0.6, TXT, 1)
        if rec is not None:
            put(fr, f"seen: {NAME.get(rec['label'], rec['label'])}   max closure {rec['cap']:.2f}   why: {str(rec.get('why', ''))[:60]}", (1150, 708), 0.5, COL.get(rec["label"], TXT), 1)
        else:
            put(fr, "vision OFF: no closure limit (full force)", (1150, 708), 0.55, (80, 80, 255), 2)
        # glove fingers + closure gauge
        cv2.rectangle(fr, (20, 870), (560, 1060), PANEL, -1); put(fr, "ROKOKO GLOVE (operator, recorded 14 Nov)", (32, 896), 0.55, TXT, 1)
        for i, (nm, fv) in enumerate(zip(("thumb", "index", "middle"), F[:3])):
            y = 925 + i * 40; put(fr, nm, (32, y + 14), 0.55, TXT, 1)
            cv2.rectangle(fr, (130, y), (530, y + 20), (70, 70, 80), -1); cv2.rectangle(fr, (130, y), (130 + int(400 * np.clip(fv, 0, 1)), y + 20), ACC, -1)
        cv2.rectangle(fr, (580, 870), (1120, 1060), PANEL, -1); put(fr, "G1 HAND CLOSURE (Dex3)", (592, 896), 0.55, TXT, 1)
        cv2.rectangle(fr, (600, 930), (1100, 970), (70, 70, 80), -1)
        cv2.rectangle(fr, (600, 930), (600 + int(500 * np.clip(c, 0, 1)), 970), (80, 170, 255), -1)
        xc = 600 + int(500 * np.clip(cap, 0, 1)); cv2.line(fr, (xc, 918), (xc, 982), (60, 60, 255), 3)
        put(fr, f"command {c:.2f}   limit from vision {cap:.2f}", (600, 1010), 0.6, TXT, 1)
        put(fr, f"object lifted {max(lift, 0):4.1f} cm", (600, 1045), 0.6, TXT, 1)
        # force plot
        cv2.rectangle(fr, (1140, 730), (1900, 1060), PANEL, -1); put(fr, "HAND-OBJECT FORCE (N)", (1152, 756), 0.55, TXT, 1)
        x0, y0, pw, ph, fmax = 1160, 1040, 720, 260, 40.0
        if brk:
            yb = int(y0 - ph * brk / fmax); cv2.line(fr, (x0, yb), (x0 + pw, yb), (60, 60, 255), 1)
            put(fr, f"break threshold {brk:.0f} N (assumed)", (x0 + pw - 250, yb - 6), 0.45, (90, 90, 255), 1)
        v = self.fhist[-300:]
        if len(v) > 1:
            pts = np.array([(x0 + int(pw * i / 299), int(y0 - ph * min(f, fmax) / fmax)) for i, f in enumerate(v)], np.int32)
            cv2.polylines(fr, [pts], False, (80, 220, 255), 2, cv2.LINE_AA)
        put(fr, f"{force:5.1f} N", (x0 + pw - 110, 790), 0.8, (80, 220, 255), 2)
        put(fr, "MuJoCo simulation" + ("  |  grasp assist ON" if self.assist else ""), (24, 1074), 0.42, (130, 130, 140), 1)
        return fr

    def scan_frames(self, rgb, res, writer, show, secs, title, sub):
        """the camera frame with ALL detections drawn (boxes from the perception output), held on screen for `secs`"""
        img = rgb[:, :, ::-1].copy()
        for o in res["objects"]:
            if not o.get("bbox"): continue
            u0, v0, u1, v1 = o["bbox"]; col = COL.get(o["label"], COL["unknown"])
            cv2.rectangle(img, (u0 - 4, v0 - 4), (u1 + 4, v1 + 4), col, 2)
            put(img, f"{NAME.get(o['label'], o['label'])}  max {o['cap']:.2f}", (u0 - 4, v0 - 10), 0.5, col, 1)
        for i in range(int(secs * RATE)):
            fr = self.compose(title, sub, "SCANNING", np.zeros(5), 0.0, 1.0, 0.0, None, 0.0, False, None, img, None, None)
            y = 760 + 0 * i
            put(fr, f"objects found: {len(res['objects'])}   recognition time {res.get('t_wall', 0)} s   engine: {res.get('engine', '') or 'geometry + colour'}", (36, 822), 0.6, ACC, 2)
            if writer is not None: writer.write(fr)
            if show:
                cv2.imshow("G1 x Rokoko x Computer Vision", cv2.resize(fr, (1280, 720)))
                if (cv2.waitKey(1) & 0xFF) in (ord("q"), 27): raise KeyboardInterrupt


def match(res, demo, work):
    """detection nearest to each object's true position (for labels in the live view) and the one at the work spot"""
    det = {}
    for o in demo.objs:
        p = demo.d.xpos[demo.ob[o]] - demo.kin.base; best = None
        for r in res["objects"]:
            dd = np.hypot(*(np.array(r["p_pelvis"][:2]) - p[:2]))
            if dd < 0.06 and (best is None or dd < best[0]): best = (dd, r)
        if best: det[o] = best[1]
    return det


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--live", action="store_true"); ap.add_argument("--no-show", action="store_true")
    ap.add_argument("--vlm", default=""); ap.add_argument("--engine", default="g1", choices=["g1", "ai"], help="g1 = geometry+colour (offline); ai = + Tommaso ai.perceive ensemble (with --vlm nemotron: NVIDIA)"); ap.add_argument("--out", default=os.path.join(ROOT, "data", "video", "demo_cv.mp4"))
    ap.add_argument("--no-compare", action="store_true", help="skip the final egg-without-vision comparison")
    ap.add_argument("--no-assist", action="store_true", help="pure physics: no grasp assist (objects may slip)")
    a = ap.parse_args(); show = not a.no_show
    demo = Demo(vlm=[b for b in a.vlm.split(",") if b], engine=a.engine); demo.det = {}; demo.assist = not a.no_assist
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    writer = None if a.live else cv2.VideoWriter(a.out, cv2.VideoWriter_fourcc(*"mp4v"), RATE, (W, H))
    summary = []
    try:
        for k, work in enumerate(demo.objs):
            demo.place(work); rgb, res, T = demo.recognise(); demo.det = match(res, demo, work); rec = demo.det.get(work)
            lab = rec["label"] if rec else "unknown"; cap = SIM_CAP.get(lab, SIM_CAP["unknown"])
            for o in list(res["objects"]) + list(demo.det.values()): o["cap"] = SIM_CAP.get(o["label"], SIM_CAP["unknown"])
            print(f"[cv] {work}: seen as {lab}, cap {cap:.2f}, {res.get('t_wall')} s, objects {[(o['label'], o['cap']) for o in res['objects']]}", flush=True)
            demo.scan_frames(rgb, res, writer, show, 3.0, f"{k + 1}/3  THE CAMERA RECOGNISES", f"object at the work spot: {NAME.get(lab, lab)} -> max closure {cap:.2f}")
            glove = LiveGlove() if a.live else TakeGlove(TAKES[work])
            r = demo.grasp(work, glove, cap, lab, f"{k + 1}/3  GRASP: {NAME.get(lab, lab)}", f"real glove take {TAKES[work]} + closure limit from vision {cap:.2f}", writer, show, rec)
            summary.append((work, lab, cap, r)); print(f"[grasp] {work}: {r}", flush=True)
        if not a.no_compare and not a.live:
            demo.place("egg"); demo.det = {}
            r = demo.grasp("egg", TakeGlove(TAKES["egg"]), 1.0, "egg", "COMPARISON: EGG WITHOUT VISION", "same glove take, no limit: full force 1.00", writer, show, None)
            summary.append(("egg (no vision)", "-", 1.0, r)); print(f"[grasp] egg WITHOUT vision: {r}", flush=True)
    except KeyboardInterrupt:
        print("stopped", flush=True)
    finally:
        if writer is not None: writer.release()
        cv2.destroyAllWindows()
    print("\nRESULT"); [print(f"  {w:18s} seen {l:12s} cap {c:.2f}  {r}") for w, l, c, r in summary]
    if writer is not None: print("video:", a.out)


if __name__ == "__main__":
    main()
