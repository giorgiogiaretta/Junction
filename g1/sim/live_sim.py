"""LIVE: Rokoko glove -> simulated G1 (MuJoCo window + head-camera window), the same logic planned for the real robot.
  py -3.11 g1/sim/live_sim.py --obj egg                 # live gloves (driver rokoko-sdk running), right glove on the hand
  py -3.11 g1/sim/live_sim.py --obj egg --replay 77     # no gloves: replays a recorded take at real speed
  options: --hand R|L (glove on the hand), --spot 0.35,-0.15 (object on the mat, pelvis frame m), --cam (head camera window)
How it behaves (state machine, printed in the window):
  HOVER   robot hand open 10 cm above where the HEAD CAMERA sees the object (perceive.py, organisers' camera)
  DESCEND you start closing the glove (grip > 30 % of your usual grip on that object) -> the hand goes down in 1 s, fingers kept open
  GRASP   robot closure = object cap x (your grip / your usual grip), e.g. egg cap 0.70, ball and empty can 1.0
  LIFT    you lift your wrist -> the robot lifts by the same height x 0.8 (0..25 cm)
  RELEASE you open the glove -> the robot opens and goes back up to HOVER
Finger calibration = data/calib.json (series E), exactly as the recorded episodes, so 'your usual grip' g_ref matches the 14/11 data.
Every command passes the same checks as the organisers' filter (counter keep-out, box, joint bounds, 1 rad/s arm, 3 rad/s hand)."""
import argparse, json, os, socket, struct, sys, time
import numpy as np, mujoco, cv2

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "g1")); sys.path.insert(0, os.path.join(ROOT, "Rokoko", "src"))
import demo_e2e as D, perceive as PC, arm_ik
from robot.g1_dex3 import G1Dex3Retargeter

RATE = 30


class GloveLive:
    """raw RGMP from the driver -> (fingers01 via data/calib.json, wrist pos, wrist quat) of the hand glove"""
    def __init__(self, hand):
        import analyze_takes as A, calib
        self.A, self.cal, self.hand = A, calib.load(), hand
        self.s = socket.create_connection(("127.0.0.1", 12276), timeout=5); self.s.settimeout(0.002)
        self.buf, self.lay, self.names, self.used, self.last = b"", {}, {}, {}, None

    def read(self):
        try:
            while True:
                c = self.s.recv(65536)
                if not c: self.last = None; print("[glove] driver closed the stream: hand opens", flush=True); break
                self.buf += c
        except (socket.timeout, BlockingIOError): pass
        R = self.A.R
        while len(self.buf) >= 8:
            typ, ln = struct.unpack_from("<II", self.buf, 0)
            if len(self.buf) < 8 + ln: break
            p, self.buf = self.buf[8:8 + ln], self.buf[8 + ln:]
            if typ == 1:
                sd = json.loads(p.decode()); d = sd["device_id"]; self.lay[d] = R.build_layout(sd); self.names[d] = (sd.get("device_info") or {}).get("hand", "?")
            elif typ == 2:
                d = struct.unpack_from("<I", p, 0)[0]
                if d not in self.lay or self.names[d] != self.hand: continue
                _, name, ts, items = R.decode(self.lay[d], p)
                if name != "default": continue
                ang, pos, q = [0.0] * 5, None, None
                for st, v in items:
                    tf, mt = st["target_frame"], st["measure_type"]
                    if mt == "TRANSFORM" and tf.endswith("finger_sensor"): ang[self.A.FRAMES.index(tf.split("_")[0])] = R.angle_of(R.quat(v))
                    elif mt == "TRANSFORM" and tf == "arm_sensor" and st.get("reference_frame") == "coil_pro": pos, q = v[:3], [v[6], v[3], v[4], v[5]]
                import calib
                f01 = calib.to01(np.array([ang]), self.cal[self.hand])[0] if self.hand in self.cal else np.clip(np.array(ang) / 2.5, 0, 1)
                self.last = (np.asarray(f01, float), None if pos is None else np.asarray(pos, float), None if q is None else np.asarray(q, float))
        return self.last


class GloveReplay:
    def __init__(self, take, hand):
        z = np.load(os.path.join(ROOT, "data", "episodes", f"take_{take:02d}.npz")); self.F = z[f"{hand}_fingers01"]; self.P = z[f"{hand}_wrist_pos"]; self.Q = z[f"{hand}_wrist_quat"]
        self.t0 = time.time()

    def read(self):
        i = min(int((time.time() - self.t0) * RATE), len(self.F) - 1)
        return self.F[i].astype(float), self.P[i].astype(float), self.Q[i].astype(float)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--obj", default="egg", choices=list(D.OBJECTS)); ap.add_argument("--replay", type=int)
    ap.add_argument("--hand", default="R", choices=["R", "L"]); ap.add_argument("--spot", default="0.35,-0.15"); ap.add_argument("--cam", action="store_true")
    ap.add_argument("--seconds", type=float, default=600); ap.add_argument("--headless", action="store_true")
    a = ap.parse_args(); hand = "right" if a.hand == "R" else "left"; spot = [float(x) for x in a.spot.split(",")]
    obj = a.obj; pr = D.PROFILE[obj]; bg = D.best_grasp(obj)
    if not bg: sys.exit(f"no grasp posture for {obj}: run g1/sim/grasp_search.py --objects {obj}")
    posture, aim, _ = bg
    cal_all = json.load(open(arm_ik.CALIB))["R_coil_to_body"]
    if hand not in cal_all: sys.exit(f"no arm-axes calibration for the {hand} glove: record series K with that hand")
    R_cb = np.array(cal_all[hand])
    m, d = D.build(obj); names = [j["joint"] for j in G1Dex3Retargeter().joints]
    act = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, m.actuator_trnid[i, 0]): i for i in range(m.nu)}
    jq = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j): m.jnt_qposadr[j] for j in range(m.njnt)}
    ob = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "obj"); oa = m.jnt_qposadr[m.body_jntadr[ob]]
    kin = D.Kin(); home = kin.a.arm_q()
    for n, v in zip(arm_ik.ARM_NAMES, home): d.qpos[jq[n]] = v; d.ctrl[act[n]] = v
    obj_c = kin.base + np.array([spot[0], spot[1], D.COUNTER_Z + D.half_h(obj)])
    d.qpos[oa:oa + 3] = obj_c; d.qpos[oa + 3:oa + 7] = D.obj_quat(obj); mujoco.mj_forward(m, d)
    rgb, dep, mk = PC.render_head(m, d, seg_geom=mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "obj_g"))
    seen, info = PC.locate(rgb, dep, PC.cam_pose(m, d), obj, D.OBJECTS[obj]["size"][0], z_plane=obj_c[2], mask=mk)
    if seen is None: sys.exit("the head camera does not see the object at this spot: move it (--spot)")
    print(f"[camera] {obj} seen at {np.round(seen - kin.base, 3)} (pelvis), error {100 * np.linalg.norm((seen - obj_c)[:2]):.1f} cm", flush=True)
    # grasp pose for the SEEN position (orientation of the object's posture), hover 10 cm above
    k0 = D.Kin(); rt0 = G1Dex3Retargeter(max_closure=1.0)
    for _ in range(30): hq0 = rt0.step(right=[0.5 * pr["cap"]] * 3 + [0, 0])
    for n, v in posture.items(): k0.a.q[n] = v
    k0.a.apply(hq0); ee = k0.a.ee["right"]; w0 = k0.a.d.xpos[ee].copy(); Rg = k0.a.d.xmat[ee].reshape(3, 3).copy()
    w_grasp = w0 + (seen + aim - k0.pinch()); floor = kin.base[2] + D.KEEP["z"] + 0.01
    src = GloveReplay(a.replay, hand) if a.replay else GloveLive(hand)
    rt = G1Dex3Retargeter(max_closure=float(os.environ.get("G1_MAX_CLOSURE", "1.0")))
    viewer = None
    if not a.headless:
        from mujoco import viewer as mjv
        viewer = mjv.launch_passive(m, d)
    rend = mujoco.Renderer(m, 240, 320) if a.cam else None
    state, t_desc, z_lift0, grip0_up, h_lift = "HOVER", 0.0, None, None, 0.0
    spt = int(round(1 / RATE / m.opt.timestep)); t_start = time.time(); tick = 0; f6 = np.zeros(6); og = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "obj_g")
    hb = {b for b in range(m.nbody) if "right_hand" in (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, b) or "")}
    while time.time() - t_start < a.seconds and (viewer is None or viewer.is_running()):
        t_tick = time.time(); g_in = src.read()
        F, P, Q = g_in if g_in else (np.zeros(5), None, None)
        g = 0.5 * (F[1] + F[2]); up = None if P is None else float((R_cb @ P)[2])
        # state machine
        if state == "HOVER" and g > 0.3 * pr["g_ref"]: state, t_desc = "DESCEND", time.time()
        elif state == "DESCEND" and g < 0.25 * pr["g_ref"]: state = "HOVER"                     # operator opened again: abort the descent
        elif state == "DESCEND" and time.time() - t_desc > 1.0: state, grip0_up = "GRASP", up
        elif state in ("GRASP", "LIFT") and g < 0.25 * pr["g_ref"]: state = "RELEASE"; t_desc = time.time()
        elif state == "GRASP" and up is not None and grip0_up is not None and up - grip0_up > 0.03: state = "LIFT"
        elif state == "RELEASE" and time.time() - t_desc > 1.0: state = "HOVER"
        if state == "GRASP" and grip0_up is None and up is not None: grip0_up = up             # wrist pose was missing at the transition
        if state == "LIFT" and up is not None and grip0_up is not None: h_lift = float(np.clip(0.8 * (up - grip0_up), 0, 0.25))
        elif state in ("HOVER", "DESCEND", "GRASP"): h_lift = 0.0
        elif state == "RELEASE": h_lift = max(0.0, h_lift - 0.25 / RATE)                        # come down slowly, no jump
        clear = {"HOVER": 0.10, "DESCEND": 0.10 * max(0.0, 1 - (time.time() - t_desc)), "GRASP": 0.0, "LIFT": 0.0,
                 "RELEASE": 0.10 * min(1.0, time.time() - t_desc)}[state]
        target = w_grasp + np.array([0, 0, clear + h_lift]); target[2] = max(target[2], floor)
        q_prev = dict(kin.a.q); kin.a.solve("right", target, Rg)
        if D.checks(kin): kin.a.q.update(q_prev); kin.a.apply()        # a step that would break the organisers' rules is not sent
        c = pr["cap"] * float(np.clip(g / pr["g_ref"], 0, 1)) if state in ("GRASP", "LIFT") else 0.0
        hq = rt.step(right=[c, c, c, 0, 0])
        for n, v in zip(arm_ik.ARM_NAMES, kin.a.arm_q()): d.ctrl[act[n]] = v
        for n, v in zip(names, hq): d.ctrl[act[n]] = v
        force = 0.0
        for _ in range(spt):                                             # peak contact force over the substeps of this tick
            mujoco.mj_step(m, d); fs = 0.0
            for i in range(d.ncon):
                cn = d.contact[i]
                if og in (cn.geom1, cn.geom2) and m.geom_bodyid[cn.geom2 if cn.geom1 == og else cn.geom1] in hb: mujoco.mj_contactForce(m, d, i, f6); fs += abs(f6[0])
            force = max(force, fs)
        lift = 100 * (d.qpos[oa + 2] - obj_c[2]); brk = D.OBJECTS[obj]["brk"]
        status = f"{state:7s} | guanto {g:.2f} (tipico {pr['g_ref']:.2f}) -> G1 {c:.2f} (max {pr['cap']:.2f}) | forza {force:5.1f} N{' > SOGLIA' if brk and force > brk else ''} | oggetto {lift:+5.1f} cm"
        if viewer is not None:
            with viewer.lock(): viewer.set_texts([(mujoco.mjtFontScale.mjFONTSCALE_150, mujoco.mjtGridPos.mjGRID_TOPLEFT, obj, status)])
            viewer.sync()
        if tick % 15 == 0: print(status, flush=True)
        if rend is not None and tick % 6 == 0:
            rend.update_scene(d, "head_cam"); im = rend.render()[:, :, ::-1].copy(); cv2.imshow("camera in testa G1", im); cv2.waitKey(1)
        tick += 1; time.sleep(max(0.0, 1 / RATE - (time.time() - t_tick)))


if __name__ == "__main__":
    main()
