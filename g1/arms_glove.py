"""NEXT version of g1/arms_simple.py (which WORKED on the real G1, 14/11): same behaviour, faster and smoother, optional 3D view.

Per hand: glove OPEN -> arm UP, fingers open. Glove CLOSED -> arm DOWN, fingers close as it arrives (closure follows the glove, capped).
Glove OPEN again -> fingers open, then the arm goes back UP.
Changes vs arms_simple:
  - speed: trapezoid profile, max 0.80 rad/s (filter cap 1.0), accel 4 rad/s^2 -> the 11 cm move takes ~0.8 s instead of ~1.6 s.
    G1_ARM_SPEED / G1_ARM_ACC override (the speed is clamped to 0.9 rad/s).
  - fingers start closing when the arm is 85 % of the way down; on release the arm starts up after 0.35 s (was 0.8 s).
  - --viz: MuJoCo window with the G1 model following the COMMANDED joints (arms + hands), the table keep-out box and per-hand state.
Joint-space only; every command passes the organisers' own WorkspaceChecker (same rule as the runner filter) before it is sent.

  $env:G1_MAX_CLOSURE="0.6"; py -3.11 g1/arms_glove.py --source udp:14043 --host 0.0.0.0 [--viz]
"""
import argparse, json, os, socket, sys, threading, time
import numpy as np

AH = os.environ.get("AALTO_REPO", r"C:\Users\giorg\Desktop\aaltonomous-humanoid")
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
for p in (os.path.join(AH, "winshim"), AH, ROOT, HERE):
    if p not in sys.path: sys.path.insert(0, p)
from aaltonomous.interface import safety as AS

WS = AS.WorkspaceChecker(AS.JointSpec(), AS.SafetyConfig())
LIM = json.load(open(os.path.join(ROOT, "docs", "g1_dex3_limits.json")))
ALO = np.array([e["filter"][0] for e in sorted(LIM["arm_q"], key=lambda e: e["idx"])]) + 0.01
AHI = np.array([e["filter"][1] for e in sorted(LIM["arm_q"], key=lambda e: e["idx"])]) - 0.01
RATE, CHUNK, DT = 30.0, 3, 1 / 30.0
V_MAX = min(float(os.environ.get("G1_ARM_SPEED", "0.80")), 0.9)     # rad/s, per joint (runner filter: 1.0)
A_MAX = float(os.environ.get("G1_ARM_ACC", "4.0"))                    # rad/s^2
SP = {"left": 0, "right": 7}
UP_EXTRA = float(os.environ.get("G1_UP_RAD", "0.35"))
CLEAR = 0.015
G_CLOSE, G_OPEN = 0.45, 0.25
FINGERS_AT = 0.85            # fraction of the way down at which the fingers start closing
RELEASE_S = 0.35


def lift(q, side, a):
    q = q.copy(); i = SP[side]; q[i] -= a; q[i + 3] -= 0.5 * a
    return np.clip(q, ALO, AHI)


def build(q_rest):
    down = q_rest.copy(); lo, hi = WS.ko
    for side in ("left", "right"):
        idx = [0, 1] if side == "left" else [2, 3]; a = 0.0
        while a < 1.2:
            p = WS.positions(lift(down, side, a))
            if not np.any(np.all((p[idx] > lo - CLEAR) & (p[idx] < hi + CLEAR), axis=1)): break
            a += 0.01
        down = lift(down, side, a)
    return down, lift(lift(down, "left", UP_EXTRA), "right", UP_EXTRA)


class Gloves:
    def __init__(self, port):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.s.bind(("127.0.0.1", port)); self.s.setblocking(False)
        self.last = {"left": None, "right": None}

    def read(self):
        try:
            while True:
                d = json.loads(self.s.recv(65536).decode())
                for h in ("left", "right"):
                    if d.get(h) is not None: self.last[h] = d[h]
        except BlockingIOError:
            pass
        return self.last


class Viz:
    """MuJoCo passive viewer showing the COMMANDED pose (runs in its own thread, never blocks the policy)."""
    def __init__(self):
        import mujoco, mujoco.viewer, arm_ik
        self.mj, self.ik = mujoco, arm_ik
        self.a = arm_ik.G1Arms(with_cam=False); self.lock = threading.Lock(); self.arm = None; self.hand = None; self.text = ""
        threading.Thread(target=self._run, daemon=True).start()

    def push(self, arm, hand, text):
        with self.lock: self.arm, self.hand, self.text = np.array(arm), np.array(hand), text

    def _run(self):
        mj = self.mj; a = self.a
        with mj.viewer.launch_passive(a.m, a.d) as v:
            v.cam.azimuth, v.cam.elevation, v.cam.distance, v.cam.lookat[:] = 150, -25, 1.6, [0.25, 0, 0.85]
            lo, hi = WS.ko; base = np.array([0, 0, 0.793])
            while v.is_running():
                with self.lock: arm, hand, text = self.arm, self.hand, self.text
                if arm is not None:
                    for n, q in zip(self.ik.ARM_NAMES, arm): a.q[n] = float(q)
                    a.apply(hand)
                with v.lock():
                    v.user_scn.ngeom = 0
                    c = base + (np.maximum(lo, [-1, -1, -0.3]) + np.minimum(hi, [1.2, 1, 0.03])) / 2
                    s = (np.minimum(hi, [1.2, 1, 0.03]) - np.maximum(lo, [-1, -1, -0.3])) / 2
                    mj.mjv_initGeom(v.user_scn.geoms[0], mj.mjtGeom.mjGEOM_BOX, s, c, np.eye(3).flatten(), np.array([0.6, 0.4, 0.2, 0.25], np.float32))
                    v.user_scn.ngeom = 1
                    try: v.set_texts((None, mj.mjtGridPos.mjGRID_TOPLEFT, "G1 commanded pose", text))
                    except Exception: pass
                v.sync(); time.sleep(1 / 30)


class ArmsGlove:
    def __init__(self, source, viz=False):
        self.g = Gloves(int(source.split(":")[1]))
        os.makedirs(os.path.join(ROOT, "data", "live"), exist_ok=True)
        self.log = open(os.path.join(ROOT, "data", "live", "arms_glove.jsonl"), "a")
        self.viz = Viz() if viz else None
        self.tap = os.path.join(ROOT, "data", "live", "head_latest.jpg"); self.t_tap = 0.0; self.cam_seen = False; self.tap_busy = False
        self.reset()

    def _save_head(self, obs):
        """Head camera FEEDBACK only (not used for control): every 0.3 s write data/live/head_latest.jpg for the console."""
        rgb = obs.get("head_rgb"); now = time.time()
        if rgb is None or now - self.t_tap < 0.3 or self.tap_busy: return
        rgb = np.asarray(rgb)
        if not rgb.any(): return                      # blank = no camera (PC2 192.168.123.164 off)
        self.t_tap = now; self.tap_busy = True
        if not self.cam_seen: self.cam_seen = True; self.log.write(json.dumps({"event": "CAMERA", "shape": list(rgb.shape)}) + "\n")
        def w(img):
            try:
                import cv2
                tmp = self.tap + ".tmp.jpg"; cv2.imwrite(tmp, cv2.cvtColor(img, cv2.COLOR_RGB2BGR)); os.replace(tmp, self.tap)
            except Exception: pass
            finally: self.tap_busy = False
        threading.Thread(target=w, args=(rgb.copy(),), daemon=True).start()

    def metadata(self):
        return {"name": "g1-arms-glove-v2", "action_horizon": CHUNK}

    def reset(self, *a, **k):
        self.cmd = None; self.vel = np.zeros(14); self.r = None
        self.state = {"left": "START", "right": "START"}; self.t_state = {"left": 0.0, "right": 0.0}; self.start_phase = 0; self.t0 = time.time()

    def _profile(self, tgt):
        """Per-joint trapezoid toward tgt: |v| <= V_MAX, |dv| <= A_MAX*DT, decelerates to stop exactly at the target."""
        e = tgt - self.cmd
        v_stop = np.sqrt(2 * A_MAX * np.abs(e)) * np.sign(e)                 # fastest speed that still stops at the target
        v_des = np.clip(v_stop, -V_MAX, V_MAX)
        self.vel = self.vel + np.clip(v_des - self.vel, -A_MAX * DT, A_MAX * DT)
        step = self.vel * DT
        over = np.abs(step) > np.abs(e); step[over] = e[over]; self.vel[over] = 0.0   # never overshoot
        return self.cmd + step

    def _safe(self, new):
        allowed = max(WS.violation(self.cmd), 1e-4) - 1e-6
        if WS.violation(new) <= allowed: return new
        lo, hi, st = 0.0, 1.0, new - self.cmd
        for _ in range(12):
            mid = .5 * (lo + hi)
            if WS.violation(self.cmd + mid * st) <= allowed: lo = mid
            else: hi = mid
        self.vel *= lo
        return self.cmd + lo * st

    def _frac_down(self, side):
        sl = slice(SP[side], SP[side] + 7); tot = np.abs(self.down[sl] - self.up[sl]).max()
        return 1.0 - np.abs(self.cmd[sl] - self.down[sl]).max() / max(tot, 1e-6)

    def act(self, obs):
        from robot.g1_dex3 import G1Dex3Retargeter
        arm = np.asarray(obs["arm_q"], float); hand = np.asarray(obs["hand_q"], float)
        self._save_head(obs)
        if self.cmd is None:
            self.cmd = np.clip(arm, ALO, AHI); self.rest = self.cmd.copy(); self.down, self.up = build(self.rest)
            self.log.write(json.dumps({"event": "START", "v_max": V_MAX, "a_max": A_MAX, "rest": self.rest.round(4).tolist(),
                                       "down": self.down.round(4).tolist(), "up": self.up.round(4).tolist()}) + "\n")
        if self.r is None:
            self.r = G1Dex3Retargeter(); self.r.q = [min(max(float(v), j["filter"][0]), j["filter"][1]) for v, j in zip(hand, self.r.joints)]
            self.r.max_step *= 0.7
        arms, hands = [], []; now = time.time()
        for _ in range(CHUNK):
            f = self.g.read(); fingers = {}; tgt = self.cmd.copy()
            if self.start_phase < 2:                      # rest -> DOWN -> UP, gloves ignored
                goal = self.down if self.start_phase == 0 else self.up
                tgt = goal.copy()
                if np.abs(self.cmd - goal).max() < 1e-3 and np.abs(self.vel).max() < 1e-3:
                    self.start_phase += 1
                    if self.start_phase == 2: self.state = {"left": "UP", "right": "UP"}
                fingers = {"left": [0.0] * 3 + [0.0, 0.0], "right": [0.0] * 3 + [0.0, 0.0]}
            else:
                for side in ("left", "right"):
                    sl = slice(SP[side], SP[side] + 7); gl = f[side]; g = 0.0 if gl is None else float(np.mean([gl[1], gl[2]]))
                    st = self.state[side]
                    if st == "UP" and g > G_CLOSE: st = "DOWN"
                    elif st == "DOWN" and g < G_OPEN: st = "UP"
                    elif st == "DOWN" and self._frac_down(side) >= FINGERS_AT: st = "GRASP"
                    elif st == "GRASP" and g < G_OPEN: st = "RELEASE"; self.t_state[side] = now
                    elif st == "RELEASE" and now - self.t_state[side] > RELEASE_S: st = "UP"
                    self.state[side] = st
                    tgt[sl] = (self.down if st in ("DOWN", "GRASP", "RELEASE") else self.up)[sl]
                    c = float(np.clip(g / 0.6, 0, 1)) if st == "GRASP" else 0.0
                    fingers[side] = [c, c, c, 0.0, 0.0]
            self.cmd = self._safe(self._profile(tgt))
            arms.append(self.cmd.copy()); hands.append(np.asarray(self.r.step(left=fingers["left"], right=fingers["right"]), float))
        self.log.write(json.dumps({"t": round(now - self.t0, 2), "state": dict(self.state), "viol": round(WS.violation(self.cmd), 4),
                                   "vmax": round(float(np.abs(self.vel).max()), 3), "fingers": {k: round(v[0], 3) for k, v in fingers.items()},
                                   "arm_q_target": np.round(arms[-1], 4).tolist(), "hand_q_target": np.round(hands[-1], 4).tolist()}) + "\n")
        self.log.flush()
        if self.viz is not None: self.viz.push(arms[-1], hands[-1], f"L {self.state['left']}   R {self.state['right']}")
        return {"arm_q_target": np.array(arms), "hand_q_target": np.array(hands)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--source", default="udp:14043"); ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--viz", action="store_true")
    a, _ignored = ap.parse_known_args()          # the console also passes --right/--left/--right-xy...: not used here
    from aaltonomous.deploy.policy_server import Policy, serve
    serve(type("ArmsGloveServed", (ArmsGlove, Policy), {})(a.source, viz=a.viz), port=a.port, host=a.host)
