"""V2 live, WITH the Coil: the arms follow the operator's wrists (same chain as g1/sim/teleop_multi.py, g1/coil_chain.py), the gloves
drive the fingers, camera (or CLI xy) gives the objects for assist/snap. Seated beside the robot: start with both gloves FLAT and STILL on
the table = robot rest pose; a hand resting still on the table for 1 s re-anchors (no Coil drift).

Glove + wrist input (UDP, use 14044: the operator console sends fingers-only packets on 14043): packets of Rokoko/src/rgmp_client.py run with --hand any, one per glove:
  {"fingers": [5 x 0..1], "hand": "left"|"right", "wrist_position": [x,y,z], "wrist_quaternion": [w,x,y,z], "t": ...}
  (the --bimanual-port stream carries fingers ONLY: a hand without wrist pose stays at the rest pose, fingers open.)
Run:     py -3.11 Rokoko/src/rgmp_client.py --hand any --udp-port 14044
         py -3.11 g1/live_policy_v2.py --source udp:14044 --right egg --left can_empty --right-xy 0.35,-0.15 --left-xy 0.35,0.15 [--dry]
Calib:   py -3.11 g1/live_policy_v2.py --source udp:14044 --calib       (short seated calibration, saved in data/arm_calib.json "seated")
Replay:  py -3.11 g1/live_policy_v2.py --source replay:77,86 --right egg --left can_empty --right-xy 0.35,-0.15 --left-xy 0.35,0.15
Mock:    AALTO_REPO=<clone> py -3.11 g1/run_mock_gate.py --policy ws://localhost:8000 --team giorgio --episodes 1 --time-limit 30
Safety per tick (any failure -> both arms keep the last command, 3 consecutive -> HOLD for the rest of the episode): joint filter bounds,
box + counter keep-out (wrist and palm), self-collision, palms > 10 cm apart, joint speed vs the LAST COMMAND <= 0.7 rad/s (runner 1 rad/s).
G1_MAX_CLOSURE scales the fingers (0.1 on the first run). --dry: computes and logs everything but commands the measured pose (robot still).
Log: data/live/live_policy_v2.jsonl (per tick arm_q_target 14 + hand_q 14); head frame: data/live/head_latest.jpg (<= 2 Hz)."""
import argparse, json, os, socket, sys, time
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "g1"), os.path.join(ROOT, "g1", "sim"), os.path.join(ROOT, "Rokoko", "src")): sys.path.insert(0, p)
REPO = os.environ.get("AALTO_REPO", r"C:\Users\giorg\Desktop\aaltonomous-humanoid")
if os.path.isdir(REPO): sys.path.insert(0, REPO)
import arm_ik, demo_e2e as D, teleop_sim as T, coil_chain as CC
from robot.g1_dex3 import G1Dex3Retargeter

CHUNK = 3          # targets per call (one call per tick cannot keep 30 Hz, see live_policy_v1.py)
RATE = 30.0
JOINT_SPEED = 0.7  # rad/s, 70 % of the runner's 1 rad/s
FRAGILE_R, FRAGILE_V, FRAGILE_JOINT = 0.12, 0.06, 0.3
LIVE = os.path.join(ROOT, "data", "live")
LIM = json.load(open(os.path.join(ROOT, "docs", "g1_dex3_limits.json")))


class CoilInput:
    """udp:<port> (rgmp_client packets) or replay:<right take>[,<left take>] (recorded wrist + fingers, aligned to the grasp, see coil_chain.align_take)."""
    def __init__(self, source):
        self.sock = None; self.last = {"left": None, "right": None}; self.rep = None; self.takes = None
        if source.startswith("udp:"):
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.sock.bind(("0.0.0.0", int(source[4:]))); self.sock.setblocking(False)
        elif source.startswith("replay:"):
            self.takes = [int(x) for x in source[7:].split(",")]
        else: raise ValueError("source: udp:<port> or replay:<right>[,<left>]")

    def prepare_replay(self, chains):
        """replay only: align each take to its hand's grasp (needs the chains, i.e. the object poses)."""
        self.rep = {}
        for h, tk in zip(("right", "left"), self.takes + self.takes[:1] if len(self.takes) == 1 else self.takes):
            if h not in chains: continue
            z = np.load(os.path.join(ROOT, "data", "episodes", f"take_{tk:02d}.npz")); P = z["right_wrist_pos"]; ch = chains[h]
            goal = ch.human_target(ch.grasp[0] + np.array([0, 0, 0.02])) if ch.grasp else np.array([0.15, 0, 0.05])
            self.rep[h] = CC.align_take(P, z["right_wrist_quat"], z["right_fingers01"], CC.TAKE64_R, P[:10].mean(0), goal, mirror=(h == "left"))[:3]

    def read(self, side, i):
        if self.takes is not None:
            if self.rep is None or side not in self.rep: return None
            P, Q, F = self.rep[side]; j = i % len(F); return F[j], P[j], Q[j]      # loops (test only)
        try:
            while True:
                d = json.loads(self.sock.recv(65536).decode())
                h = d.get("hand")
                if h in self.last and d.get("fingers") is not None:
                    wp, wq = d.get("wrist_position"), d.get("wrist_quaternion")
                    self.last[h] = (np.asarray(d["fingers"], float), None if wp is None else np.asarray(wp, float), None if wq is None else np.asarray(wq, float))
                for k in ("left", "right"):                                   # bimanual packet: fingers only, keep the last wrist
                    if "hand" not in d and d.get(k) is not None:
                        old = self.last[k]; self.last[k] = (np.asarray(d[k], float), None if old is None else old[1], None if old is None else old[2])
        except (BlockingIOError, ConnectionResetError): pass
        return self.last[side]


def _valid_image(rgb, depth=None):
    return rgb is not None and np.asarray(rgb).size and np.asarray(rgb).any()


try:
    from aaltonomous.deploy.policy_server import Policy, serve
except Exception:                       # --calib / offline use without the organisers' repo
    Policy, serve = object, None


class LivePolicyV2(Policy):
    name = "live-g1-coil-v2"; action_horizon = CHUNK

    def __init__(self, source, objs, xy, dry=False):
        self.src = CoilInput(source); self.obj = objs; self.xy = xy; self.dry = dry
        self.rt = G1Dex3Retargeter(max_closure=float(os.environ.get("G1_MAX_CLOSURE", "1.0"))); self.rt.max_step *= .7
        self.kin = D.Kin(); self.rest = dict(self.kin.a.q)
        self.rest_pose = {h: (self.kin.a.d.xpos[self.kin.a.ee[h]].copy(), self.kin.a.d.xmat[self.kin.a.ee[h]].reshape(3, 3).copy()) for h in ("left", "right")}
        self.floor = self.kin.base[2] + D.KEEP["z"] + 0.01; self.cfg = CC.Cfg(joint_speed=JOINT_SPEED)
        replay = source.startswith("replay:")
        self.Rh = {h: (CC.TAKE64_R if replay else CC.load_axes(arm_ik.CALIB, h)) for h in objs}
        miss = [h for h in objs if self.Rh[h] is None]
        if miss: raise SystemExit(f"no seated calibration for {miss}: run  py -3.11 g1/live_policy_v2.py --source udp:14044 --calib")
        os.makedirs(LIVE, exist_ok=True); self.log = open(os.path.join(LIVE, "live_policy_v2.jsonl"), "a"); self.t_img = 0.0
        self.reset("")

    def reset(self, instruction, task=None, seed=None):
        self.initialized = False; self.chains = {}; self.seen = {}; self.blocked = 0; self.consec = 0; self.abort = False
        self.last_cmd = None; self.hand_init = False; self.tick = 0; self.t0 = time.time(); self.t_wait = None

    def _write(self, d):
        d["t"] = round(time.time() - self.t0, 3); self.log.write(json.dumps(d) + "\n"); self.log.flush()

    def _head(self, rgb):
        """head frame for the operator console: <= 2 Hz, atomic write"""
        if time.time() - self.t_img < 0.5 or not _valid_image(rgb): return
        try:
            import cv2
            tmp = os.path.join(LIVE, "head_latest.tmp.jpg"); cv2.imwrite(tmp, np.asarray(rgb)[:, :, ::-1]); os.replace(tmp, os.path.join(LIVE, "head_latest.jpg"))
            self.t_img = time.time()
        except Exception as e: self._write({"event": "HEAD_IMG_ERROR", "error": str(e)})

    def _locate(self, rgb, depth, side):
        import live_policy_v1 as V1
        return V1.LivePolicy._locate(self, rgb, depth, side)

    def _init(self, obs):
        rgb, depth = obs.get("head_rgb"), obs.get("head_depth")
        if not (_valid_image(rgb) and depth is not None and np.asarray(depth).any()):
            if self.t_wait is None: self.t_wait = time.time()
            if time.time() - self.t_wait < 3.0 or any(self.xy[s] is None for s in self.obj): return False
            rgb = None
        for side, name in self.obj.items():
            try:
                if rgb is None: raise RuntimeError("no camera frame")
                seen, origin = self._locate(rgb, depth, side), "camera"
            except Exception as e:
                if self.xy[side] is None: self._write({"event": "NO_POSE", "hand": side, "error": str(e)}); return False
                seen, origin = self.kin.base + np.array([self.xy[side][0], self.xy[side][1], D.COUNTER_Z + D.half_h(name)]), "cli_fallback"
            # camera/CLI positions are in the pelvis frame; the kinematic model has the pelvis at kin.base
            if origin == "camera": seen = self.kin.base + np.asarray(seen, float)
            gp, gR, pin_t = T.grasp_pose(name, side, seen, self.rest)
            self.seen[side] = seen
            self.chains[side] = CC.HandChain(side, self.Rh[side], self.rest_pose[side], (gp, gR, pin_t, name, D.PROFILE.get(name, D.PROFILE["unknown"])), self.cfg, self.floor)
            self._write({"event": "POSE", "hand": side, "object": name, "position_pelvis": (seen - self.kin.base).round(4).tolist(), "source": origin})
        if self.src.takes is not None: self.src.prepare_replay(self.chains)
        return True

    def _unsafe(self, k):
        r = T.unsafe(k)
        if len(self.obj) == 2 and np.linalg.norm(T.palm(k, "left") - T.palm(k, "right")) < 0.10: r.append("palms_too_close")
        return r

    def act(self, obs):
        o = dict(obs); arms, hands = [], []
        if obs.get("head_rgb") is not None: self._head(obs["head_rgb"])
        for _ in range(CHUNK):
            r = self._act1(o); arms.append(r[0]); hands.append(r[1]); o["arm_q"] = r[0]; o["hand_q"] = r[1]
        return {"arm_q_target": np.array(arms), "hand_q_target": np.array(hands)}

    def _act1(self, obs):
        arm = np.asarray(obs["arm_q"], float); hand = np.asarray(obs["hand_q"], float); t = self.tick / RATE; self.tick += 1
        if self.last_cmd is None:                                     # IK starts from the MEASURED joints
            self.kin.a.q.update({n: float(v) for n, v in zip(arm_ik.ARM_NAMES, arm)}); self.kin.a.apply(); self.last_cmd = arm.copy()
        if not self.hand_init: self.rt.q = [float(np.clip(v, *j["filter"])) for v, j in zip(hand, self.rt.joints)]; self.hand_init = True
        if not self.initialized: self.initialized = self._init(obs)
        fingers = {"left": None, "right": None}; info = {}; prev = dict(self.kin.a.q); reasons = []
        if self.initialized and not self.abort:
            for side, ch in self.chains.items():
                s = self.src.read(side, self.tick)
                if s is None or s[1] is None or s[2] is None or not np.isfinite(s[1]).all():
                    info[side] = "no wrist"; out = None
                    s = (np.zeros(5) if s is None else s[0], None, None)
                else:
                    near = lambda p: (FRAGILE_V if np.linalg.norm(p - self.seen[side]) > FRAGILE_R / 2 else FRAGILE_V / 2) \
                        if ch.grasp[3] == "egg" and np.linalg.norm(p - self.seen[side]) < FRAGILE_R else None
                    pin = T.pinch(self.kin, side)
                    out = ch.update(s[0], s[1], s[2], t, pin, self.kin.a.d.xmat[self.kin.a.ee[side]].reshape(3, 3),
                                    near_egg=near, wrist_p_now=self.kin.a.d.xpos[self.kin.a.ee[side]].copy())
                    step0 = arm_ik.ARM_STEP; arm_ik.ARM_STEP = (FRAGILE_JOINT if near(pin) is not None else JOINT_SPEED) / RATE
                    why = CC.solve_arm(self.kin, side, out, self.cfg, self.rest, self._unsafe, self.floor, T.palm); arm_ik.ARM_STEP = step0
                    reasons += why; info[side] = out["mode"] + (f" ev:{out['ev']}" if out["ev"] else "")
                    c = out["c"]; fingers[side] = [c, c, c, 0, 0]
            qcmd = np.asarray(self.kin.a.arm_q())
            if any(v < LIM["arm_q"][i]["filter"][0] or v > LIM["arm_q"][i]["filter"][1] for i, v in enumerate(qcmd)): reasons.append("joint_filter")
            if np.any(np.abs(qcmd - self.last_cmd) > JOINT_SPEED / RATE + 1e-4): reasons.append("arm_speed")
            if reasons:
                self.kin.a.q.update(prev); self.kin.a.apply(); self.blocked += 1; self.consec += 1
                fingers = {"left": None, "right": None}
                if self.consec >= 3: self.abort = True; self._write({"event": "ABORT_HOLD", "reasons": reasons, "consecutive_blocks": self.consec})
            else: self.consec = 0
        ok = self.initialized and not self.abort and not reasons
        arm_t = np.asarray(self.kin.a.arm_q()) if ok else self.last_cmd.copy()
        hq = np.asarray(self.rt.step(left=fingers["left"], right=fingers["right"])) if ok else hand.copy()
        if not ok: self.rt.q = list(hand)
        self.last_cmd = arm_t.copy()
        if self.dry: arm_t, hq = np.asarray(obs["arm_q"], float), hand.copy()   # dry run: robot keeps its pose
        self._write({"tick": self.tick, "arm_q_target": np.round(arm_t, 4).tolist(), "hand_q": np.round(hq, 4).tolist(), "modes": info,
                     "blocked": self.blocked, "consecutive": self.consec, "reasons": reasons, "abort": self.abort, "dry": self.dry, "initialized": self.initialized})
        return arm_t, hq


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--source", default="udp:14044")
    ap.add_argument("--right", choices=list(D.PROFILE)); ap.add_argument("--left", choices=list(D.PROFILE))
    xy = lambda s: tuple(map(float, s.split(",")))
    ap.add_argument("--right-xy", type=xy); ap.add_argument("--left-xy", type=xy)
    ap.add_argument("--port", type=int, default=8000); ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--dry", action="store_true"); ap.add_argument("--calib", action="store_true")
    a = ap.parse_args()
    if a.calib:
        src = CoilInput(a.source); hands = [h for h in ("right", "left") if getattr(a, h) or not (a.right or a.left)]
        CC.seated_calib({h: (lambda h=h: src.read(h, 0)) for h in hands}, hands, arm_ik.CALIB); return
    objs = {h: getattr(a, h) for h in ("right", "left") if getattr(a, h)}
    if not objs: ap.error("give --right and/or --left")
    if serve is None: sys.exit("aaltonomous-humanoid not found: set AALTO_REPO")
    serve(LivePolicyV2(a.source, objs, {"right": a.right_xy, "left": a.left_xy}, dry=a.dry), port=a.port, host=a.host)


if __name__ == "__main__":
    main()
