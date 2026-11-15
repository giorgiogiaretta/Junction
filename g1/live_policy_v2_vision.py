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
Log: data/live/live_policy_v2_vision.jsonl (per tick arm_q_target 14 + hand_q 14); head frame: data/live/head_latest.jpg (<= 2 Hz).
Vision (15/11, docs/COIL_REVIEW.md): after the start-up path, ONE head RGB-D frame goes to a persistent background worker (ai.perceive via
g1/perception_v1.perceive_with_ai, no API keys); act() only polls it, the arms hold, after G1_VISION_TIMEOUT s (10) -> CLI object + xy.
The camera label can only LOWER the finger cap (egg <= 0.50 light, can_empty 0.90, stress_ball 1.0: operator 15/11); position from the
camera only when it is within G1_XY_GATE (0.12 m) of --right-xy/--left-xy. --right/--left stay the object profile (override)."""
import argparse, json, os, socket, sys, threading, time
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "g1"), os.path.join(ROOT, "g1", "sim"), os.path.join(ROOT, "Rokoko", "src")): sys.path.insert(0, p)
REPO = os.environ.get("AALTO_REPO", r"C:\Users\giorg\Desktop\aaltonomous-humanoid")
if os.path.isdir(REPO): sys.path.insert(0, REPO)
import arm_ik, demo_e2e as D, teleop_sim as T, coil_chain as CC
# Real-G1 posture prior (Tommaso's aalto data, 19,371 real frames): IK null-space target = the postures the real robot used for that
# wrist pose. Sim, recorded Coil takes: left arm delay 487 -> 157 ms, wrist error 5.8 -> 1.5 cm. G1_PRIOR=0 turns it off.
if os.environ.get("G1_PRIOR", "1") != "0":
    try:
        import arm_prior; CC.PRIOR = arm_prior.RealArmPrior(); print("[v2-vision] real-G1 posture prior ON", flush=True)
    except Exception as _e: print("[v2-vision] posture prior NOT loaded:", _e, flush=True)
from robot.g1_dex3 import G1Dex3Retargeter

CHUNK = int(os.environ.get("G1_CHUNK", "2"))   # targets per call. 3 = one glove reading per 100 ms (the 14/11 night delay); 1 = fresh every tick
RATE = 30.0
FAST = os.environ.get("G1_FAST") == "1"
JOINT_SPEED = 1.8 if FAST else 0.9  # rad/s (runner: 2.0 with G1_FAST, else 1.0) (14/11 evening: was 0.7, operator wanted less delay)
START_SPEED = 1.0 if FAST else 0.9  # rad/s, startup move from the robot's real rest pose to the palm-down front pose
# The organisers' OWN workspace check (same code as the runner filter): the real rest pose has the wrists INSIDE the counter keep-out,
# the runner rejects any step that increases the penetration -> lift out first, then never send a step it would clip.
try:
    for _p in (os.path.join(REPO, "winshim"), REPO):
        if _p not in sys.path: sys.path.insert(0, _p)
    from aaltonomous.interface import safety as _AS
    FAST = os.environ.get("G1_FAST") == "1"     # staff-approved 15/11: no counter keep-out, faster arms (self-collision kept)
    WS = _AS.WorkspaceChecker(_AS.JointSpec(), _AS.SafetyConfig(counter_keepout_min=None, counter_keepout_max=None) if FAST else _AS.SafetyConfig())
except Exception as _e:
    print("[v2] organisers' workspace check NOT loaded:", _e); WS = None
FRAGILE_R, FRAGILE_V, FRAGILE_JOINT = 0.08, 0.20, 0.9   # was 0.12, 0.06, 0.3 (the egg hand crawled); finger cap 0.50 protects the egg
try:
    import perception_v1 as PV           # CAP, robot_mask, perceive_with_ai, assign, pinhole_pixel_to_pelvis (one module identity)
except Exception as _e:
    print("[v2] perception_v1 NOT loaded, vision off (CLI object + xy):", _e); PV = None
VISION_TIMEOUT = float(os.environ.get("G1_VISION_TIMEOUT", "10"))   # s; the arms HOLD meanwhile, act() never waits on the worker
XY_GATE = float(os.environ.get("G1_XY_GATE", "0.12"))                # m: camera xy further than this from the CLI xy -> CLI xy
VLM = tuple(v for v in os.environ.get("G1_VLM", "").split(",") if v)       # e.g. "nemotron,gemma" (keys from env, ai.recognize); default: local colour + geometry only
LOG_FLUSH_S = 0.5                                                    # s for routine tick lines; events and blocked ticks flush at once
# hard finger caps per object (the camera label can only LOWER the CLI object's cap): egg 0.70 never more; empty can = perception_v1's
# rule (0.45, object_profiles.json); stress_ball keeps demo_e2e's 1.0 (cannot break, the real grip is weak: a lower cap only drops it)
CAP_DEFAULT = 0.60     # no recognised object near the hand (or only the CLI fallback): the most careful cap
SELECT_R = 0.15        # m: the object nearest to the robot pinch within this radius gives the cap and the assist/snap target
REDETECT_S = 3.0       # s: the head camera re-detects all objects in the background while no hand is grasping
_GP = {}


def gpose(name, side, seen, rest):
    """T.grasp_pose is linear in the object position: cache the offsets per (object, hand) (a fresh one costs ~190 ms)."""
    if (name, side) not in _GP: _GP[(name, side)] = T.grasp_pose(name, side, np.zeros(3), rest)
    g = _GP[(name, side)]
    return None if g is None else (g[0] + seen, g[1], g[2] + seen)


CAP_HARD = {"egg": 0.60, "can_empty": 0.90, "stress_ball": 1.0}   # operator 15/11: camera sees egg -> never above 0.60, can 0.90, ball 1.0
LABELS = {"can": "can_empty", "ball": "stress_ball", "egg": "egg", "can_empty": "can_empty", "stress_ball": "stress_ball"}
LIVE = os.path.join(ROOT, "data", "live")
LIM = json.load(open(os.path.join(ROOT, "docs", "g1_dex3_limits.json")))
SAFE_LO = {k: np.array([e["filter"][0] for e in sorted(LIM[k], key=lambda e: e["idx"])]) + 0.005 for k in ("arm_q", "hand_q")}
SAFE_HI = {k: np.array([e["filter"][1] for e in sorted(LIM[k], key=lambda e: e["idx"])]) - 0.005 for k in ("arm_q", "hand_q")}


class CoilInput:
    """udp:<port> (rgmp_client packets) or replay:<right take>[,<left take>] (recorded wrist + fingers, aligned to the grasp, see coil_chain.align_take)."""
    def __init__(self, source):
        self.sock = None; self.last = {"left": None, "right": None}; self.rep = None; self.takes = None
        if source.startswith("udp:"):
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.sock.bind(("0.0.0.0", int(source[4:]))); self.sock.setblocking(False)
            # RECORD every raw glove + Coil packet (to replay the same movements later without the Coil)
            os.makedirs(LIVE, exist_ok=True)
            self.rec = open(os.path.join(LIVE, time.strftime("coil_input_%Y%m%d_%H%M%S.jsonl")), "a")
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
                raw = self.sock.recv(65536).decode(); d = json.loads(raw)
                self.rec.write(json.dumps({"t_rx": time.time(), "pkt": d}) + "\n")
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
    name = "live-g1-coil-v2-vision"; action_horizon = CHUNK

    def __init__(self, source, objs, xy, dry=False):
        self.src = CoilInput(source); self.obj = objs; self.xy = xy; self.dry = dry
        from finger_map import DirectRetargeter                 # thumb/index/middle one-to-one
        self.rt = DirectRetargeter(max_closure=float(os.environ.get("G1_MAX_CLOSURE", "1.0"))); self.rt.max_step *= .7
        self.kin = D.Kin(); self.rest = CC.palm_down_rest(self.kin, D.COUNTER_Z)      # rest = hands open, palm down, in front (as the sim)
        self.rest_q = np.array([self.rest[n] for n in arm_ik.ARM_NAMES])
        self.rest_pose = {h: (self.kin.a.d.xpos[self.kin.a.ee[h]].copy(), self.kin.a.d.xmat[self.kin.a.ee[h]].reshape(3, 3).copy()) for h in ("left", "right")}
        self.floor = self.kin.base[2] + (D.KEEP["z"] - 0.25 if FAST else D.KEEP["z"] + 0.01)
        self.cfg = CC.Cfg(joint_speed=JOINT_SPEED, **(dict(vmax=1.3, vfinal=1.2, wfinal=np.radians(400)) if FAST else {}))
        replay = source.startswith("replay:")
        self.Rh = {h: (CC.TAKE64_R if replay else CC.load_axes(arm_ik.CALIB, h)) for h in objs}
        miss = [h for h in objs if self.Rh[h] is None]
        if miss: raise SystemExit(f"no seated calibration for {miss}: run  py -3.11 g1/live_policy_v2.py --source udp:14044 --calib")
        if not replay: CC.load_neutral(arm_ik.CALIB, list(objs))   # calibration's last step: open, palm down, in front = robot rest
        os.makedirs(LIVE, exist_ok=True); self.log = open(os.path.join(LIVE, "live_policy_v2_vision.jsonl"), "a"); self.t_img = 0.0
        # ONE persistent perception worker: the MuJoCo renderer of the self-mask is bound to the thread that created it (a new thread
        # per episode rendered garbage after a runner reset in live_policy_v1); results of an older episode are dropped (self.ep)
        import concurrent.futures as cf
        self.worker = cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="perception"); self.ep = 0; self.ep_lock = threading.Lock()
        self.reset("")

    def reset(self, instruction, task=None, seed=None):
        if hasattr(self, "log"): self.log.flush()
        self.initialized = False; self.chains = {}; self.seen = {}; self.blocked = 0; self.consec = 0; self.abort = False
        self.last_cmd = None; self.hand_init = False; self.tick = 0; self.t0 = time.time(); self.t_wait = None
        self.started = False; self.stall = 0; self.t_last = None; self.t_flush = time.time()
        with self.ep_lock: self.ep += 1; self.perc = None
        self.vision_future = None; self.vision_started = None; self.vision_logged = False; self.pose_failed = set()
        self.chains_fallback = {}; self.cands = {}; self.sel = {}; self.objs = []; self.redetect = None; self.t_detect = time.time()
        self.head_busy = False; self.head_err = None

    def _ws_safe(self, q):
        """Runner filter rule: never more counter keep-out penetration than the last command; bisect the step. Returns (q, fraction)."""
        q = np.clip(np.asarray(q, float), SAFE_LO["arm_q"], SAFE_HI["arm_q"])
        if WS is None: return q, 1.0
        allowed = max(WS.violation(self.last_cmd), 1e-4)
        if WS.violation(q) <= allowed: return q, 1.0
        lo, hi, st = 0.0, 1.0, q - self.last_cmd
        for _ in range(12):
            mid = .5 * (lo + hi)
            if WS.violation(self.last_cmd + mid * st) <= allowed: lo = mid
            else: hi = mid
        return self.last_cmd + lo * st, lo

    def _startup(self, obs, hand):
        """Real rest pose -> lift out of the counter keep-out (joint space, as g1/arms_simple.py that worked on the robot) -> palm-down
        front rest pose, hands open. The Coil chains engage only after this (robot = your 'open, palm down, in front' pose)."""
        # path planned in the background by g1/start_path.py (hand back/up first if needed, as the raised robot of 14/11 night
        # requires); straight segments at START_SPEED; re-plan from here if the filter rule stalls a segment. Arms hold meanwhile.
        import threading, start_path
        q = self.last_cmd.copy(); phase = "planning"
        if getattr(self, "wps", None) is None and not getattr(self, "planning", False):
            self.planning = True; self.wp_i = 0; q0 = q.copy()
            def run():
                try: self.wps = start_path.plan(WS, q0, self.rest_q, SAFE_LO["arm_q"], SAFE_HI["arm_q"]) if WS is not None else [self.rest_q]
                except Exception as e: self.wps = None; print("[v2] start path error:", e, flush=True)
                if self.wps is None: print("[v2] NO start-up path the runner accepts: arms stay still", flush=True)
                self.planning = False
            threading.Thread(target=run, daemon=True).start()
        if getattr(self, "wps", None) is not None:
            w = self.wps[self.wp_i]; d = w - q; m = float(np.abs(d).max()); st = START_SPEED / RATE
            q2 = w.copy() if m <= st else q + d * st / m
            q2, frac = self._ws_safe(q2); phase = f"path {self.wp_i + 1}/{len(self.wps)}"
            if np.abs(q2 - w).max() < 1e-6:
                self.wp_i += 1; self.stall = 0
                if self.wp_i >= len(self.wps): self.started = True; phase = "at_rest"
            elif np.abs(q2 - q).max() < 1e-4:
                self.stall += 1
                if self.stall > 6: self.stall = 0; self.wps = None; phase = "replan"
            q = q2
        self.kin.a.q.update({n: float(v) for n, v in zip(arm_ik.ARM_NAMES, q)}); self.kin.a.apply(); self.last_cmd = q.copy()
        hq = np.clip(np.asarray(self.rt.step(left=None, right=None)), SAFE_LO["hand_q"], SAFE_HI["hand_q"])   # hands open
        self._write({"tick": self.tick, "startup": phase, "arm_q_target": np.round(q, 4).tolist(), "hand_q": np.round(hq, 4).tolist(),
                     "ws_violation": None if WS is None else round(WS.violation(q), 4), "dry": self.dry})
        if self.dry: return np.asarray(obs["arm_q"], float), hand.copy()
        return q, hq

    def _write(self, d):
        """ONE writer (the act thread). Routine tick lines are flushed every LOG_FLUSH_S (was: a flush per target = 60/s on the control
        thread); events and blocked ticks are flushed at once, so the tail a human reads after a problem is on disk."""
        d["t"] = round(time.time() - self.t0, 3); self.log.write(json.dumps(d, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x)) + "\n")
        if "event" in d or d.get("reasons") or time.time() - self.t_flush >= LOG_FLUSH_S: self.log.flush(); self.t_flush = time.time()

    def _head(self, rgb):
        """head frame for the operator console: <= 2 Hz, atomic write, in a thread (a JPEG encode + disk write is 5-30 ms on this PC)"""
        if time.time() - self.t_img < 0.5 or self.head_busy or not _valid_image(rgb): return
        self.t_img = time.time(); self.head_busy = True
        threading.Thread(target=self._save_head, args=(np.asarray(rgb).copy(),), daemon=True).start()

    def _save_head(self, rgb):
        try:
            import cv2
            tmp = os.path.join(LIVE, "head_latest.tmp.jpg"); cv2.imwrite(tmp, rgb[:, :, ::-1]); os.replace(tmp, os.path.join(LIVE, "head_latest.jpg"))
        except Exception as e: self.head_err = str(e)                # logged by the act thread (one log writer)
        finally: self.head_busy = False

    def _vision(self, rgb, depth, arm, hand, ep):
        """Perception worker (once per episode). Never raises. Same K/T as live_policy_v1.Camera, without importing live_policy_v1
        (its import asserts AALTO_REPO and rewrites arm_ik.ARM_STEP, a global the act thread uses)."""
        t0 = time.time()
        try:
            from aaltonomous.interface.calibration import Calibration
            cal = Calibration.load(); K, Tc = cal.cams["head"].K, cal._T("head")
            sm = PV.robot_mask(arm, hand, K, Tc, shape=np.asarray(depth).shape[:2])(depth)   # robot's own pixels out (hands near the objects)
            res = PV.perceive_with_ai(rgb, depth, PV.pinhole_pixel_to_pelvis(K, Tc), vlm=VLM, vlm_timeout=0.8 * VISION_TIMEOUT, self_mask=sm)
            asg = PV.assign(res.get("objects", []), sides=tuple(self.obj)); out = {}
            for s in self.obj:
                try:
                    o = asg.get(s)
                    out[s] = None if o is None else {"label": LABELS.get(str(o.get("label")), "unknown"), "raw_label": o.get("label"),
                                                    "conf": o.get("conf"), "pv_cap": o.get("cap"), "depth_ok": bool(o.get("depth_ok")),
                                                    "p": None if o.get("p_pelvis") is None else np.asarray(o["p_pelvis"], float)}
                except Exception as e: out[s] = None; print("[v2] vision object error:", s, e, flush=True)
            objs = []
            for o in res.get("objects", []):
                lb = LABELS.get(str(o.get("label")), "unknown")
                if o.get("p_pelvis") is not None and o.get("depth_ok"): objs.append({"label": lb, "p": np.asarray(o["p_pelvis"], float)})
            payload = (out, res.get("table_z"), res.get("engine"), res.get("error") or res.get("ai_error"), time.time() - t0, objs)
        except Exception as e:
            payload = ({}, None, None, f"{type(e).__name__}: {e}", time.time() - t0)
        with self.ep_lock:
            if ep == self.ep: self.perc = payload                    # a result from before a runner reset is dropped

    def _init(self, obs):
        """Poll the vision worker (never wait on it; the arms hold at the rest pose meanwhile), then one HandChain per hand."""
        rgb, depth = obs.get("head_rgb"), obs.get("head_depth")
        valid = _valid_image(rgb) and depth is not None and np.asarray(depth).any()
        if self.perc is None:
            if valid and PV is not None and self.vision_future is None:
                self.vision_started = time.time()
                self.vision_future = self.worker.submit(self._vision, np.asarray(rgb).copy(), np.asarray(depth).copy(),
                                                        np.asarray(obs["arm_q"], float).copy(), np.asarray(obs["hand_q"], float).copy(), self.ep)
            if self.vision_future is None:                           # no camera frame (or no perception module): 3 s grace, then CLI
                if self.t_wait is None: self.t_wait = time.time()
                if time.time() - self.t_wait < 3.0 or any(self.xy[s] is None for s in self.obj): return False
            elif time.time() - self.vision_started < VISION_TIMEOUT: return False
        found, table_z, engine, error, lat = self.perc[:5] if self.perc is not None else \
            ({}, None, None, "vision timeout" if self.vision_future is not None else "no camera frame", time.time() - (self.vision_started or time.time()))
        self.objs = list(self.perc[5]) if self.perc is not None and len(self.perc) > 5 else []
        if not self.vision_logged:
            self.vision_logged = True
            self._write({"event": "VISION", "engine": engine, "error": error, "table_z": table_z, "latency_s": round(lat, 2),
                         "found": {s: (None if v is None else {**v, "p": None if v["p"] is None else np.round(v["p"], 4).tolist()}) for s, v in found.items()}})
        # measured table height only if plausible (a bad frame must not move the grasp height): within 5 cm of the nominal counter
        z0 = float(table_z) if table_z is not None and abs(float(table_z) - D.COUNTER_Z) < 0.05 else D.COUNTER_Z
        for side, name in self.obj.items():
            if side in self.chains: continue                          # never rebuilt: that would reset the Coil anchor/filters every tick
            det = found.get(side) or {}; lab = det.get("label") if det.get("label") in CAP_HARD else None
            seen, origin = None, "cli_fallback"
            if det.get("depth_ok") and det.get("p") is not None and (self.xy[side] is None or np.hypot(*(det["p"][:2] - np.asarray(self.xy[side]))) <= XY_GATE):
                seen, origin = self.kin.base + det["p"], "camera"     # camera/CLI positions are pelvis frame; the model has the pelvis at kin.base
            elif self.xy[side] is not None:
                seen = self.kin.base + np.array([self.xy[side][0], self.xy[side][1], z0 + D.half_h(name)])
            if seen is None:
                if side not in self.pose_failed:
                    self.pose_failed.add(side); self._write({"event": "NO_POSE", "hand": side, "error": error or f"no camera pose and no --{side}-xy"})
                return False
            # finger cap = the CLI object's profile cap, LOWERED by the camera label; never above the hard caps (egg 0.50, can 0.90, ball 1.0)
            cap = float(D.PROFILE.get(name, D.PROFILE["unknown"])["cap"])
            for lb in (name, lab):
                if lb in CAP_HARD: cap = min(cap, CAP_HARD[lb])
            gp, gR, pin_t = T.grasp_pose(name, side, seen, self.rest)
            self.seen[side] = seen
            pr = dict(D.PROFILE.get(name, D.PROFILE["unknown"])); pr["cap"] = cap     # the chain and the finger command both read pr["cap"]
            self.chains[side] = CC.HandChain(side, self.Rh[side], self.rest_pose[side], (gp, gR, pin_t, name, pr), self.cfg, self.floor)
            self.chains_fallback[side] = {"name": name, "seen": seen.copy(), "grasp": (gp, gR, pin_t),
                                          "cap": cap if lab is not None else min(cap, CAP_DEFAULT), "src": "camera" if lab is not None else "cli"}
            self._write({"event": "POSE", "hand": side, "object": name, "camera_label": lab, "cap": round(cap, 3), "source": origin,
                         "position_pelvis": (seen - self.kin.base).round(4).tolist()})
        if self.src.takes is not None: self.src.prepare_replay(self.chains)
        ok = all(s in self.chains for s in self.obj)
        if ok: self._build_cands()
        return ok

    def _build_cands(self):
        """Per hand: every object the camera recognised (its own cap) + the CLI/assigned one (careful cap unless the camera confirmed it)."""
        self.cands = {}
        for side, ch in self.chains.items():
            c = []
            for o in getattr(self, "objs", []):
                if o["label"] not in CAP_HARD: continue
                seen = self.kin.base + o["p"]; g = gpose(o["label"], side, seen, self.rest)
                if g is not None: c.append({"name": o["label"], "seen": seen, "grasp": g, "cap": CAP_HARD[o["label"]], "src": "camera"})
            fb = self.chains_fallback.get(side)
            if fb is not None and not any(np.linalg.norm(x["seen"][:2] - fb["seen"][:2]) < 0.06 for x in c): c.append(fb)
            self.cands[side] = c
        self._write({"event": "CANDIDATES", "objects": {s: [(x["name"], x["src"], round(x["cap"], 2), np.round(x["seen"] - self.kin.base, 3).tolist()) for x in v] for s, v in self.cands.items()}})

    def _select(self, side, ch, pin):
        """While the hand is not grasping: the candidate nearest to the robot pinch becomes the target; cap = its cap if within SELECT_R,
        else CAP_DEFAULT (nothing recognised near the hand)."""
        if ch.stage is not None or not self.cands.get(side): return
        best = min(self.cands[side], key=lambda x: np.linalg.norm(pin - x["seen"])); d = float(np.linalg.norm(pin - best["seen"]))
        cap = best["cap"] if d <= SELECT_R else min(best["cap"], CAP_DEFAULT)
        pr = dict(D.PROFILE.get(best["name"], D.PROFILE["unknown"])); pr["cap"] = cap
        gp, gR, pin_t = best["grasp"]; ch.grasp = (gp, gR, pin_t, best["name"], pr); self.seen[side] = best["seen"]
        key = (best["name"], round(cap, 2))
        if self.sel.get(side) != key:
            self.sel[side] = key; self._write({"event": "TARGET", "hand": side, "object": best["name"], "cap": round(cap, 2), "dist_cm": round(100 * d, 1), "src": best["src"]})

    def _unsafe(self, k):
        r = T.unsafe(k)
        if FAST: r = [x for x in r if x.startswith("self")]          # G1_FAST: only robot-vs-robot collisions block
        if len(self.obj) == 2 and np.linalg.norm(T.palm(k, "left") - T.palm(k, "right")) < 0.10: r.append("palms_too_close")
        return r

    def act(self, obs):
        o = dict(obs); arms, hands = [], []
        if obs.get("head_rgb") is not None: self._head(obs["head_rgb"])
        # Coil-chain time follows the wall clock: with the runner at ~100 ms per call and 2 targets, tick/RATE ran at 2/3 of real time,
        # so every filter / timer of coil_chain was 1.5x slower (OneEuro 5 Hz -> 3.3 Hz, grip tau 40 -> 60 ms, assist 0.4 -> 0.6 s).
        # Sub-ticks stay exactly 1/RATE apart and catch-up is bounded (dt <= 2/RATE); offline (fast loop) it equals tick/RATE.
        # The per-target joint step (ARM_STEP = JOINT_SPEED/RATE) and the arm_speed check do not depend on t: unchanged.
        self._redetect(obs)
        wall = time.time() - self.t0; lag = (CHUNK - 1) / RATE
        if self.t_last is None: base = max(0.0, wall - lag)
        else: base = min(max(self.t_last + 1.0 / RATE, wall - lag), self.t_last + 2.0 / RATE)
        for i in range(CHUNK):
            r = self._act1(o, base + i / RATE); arms.append(r[0]); hands.append(r[1]); o["arm_q"] = r[0]; o["hand_q"] = r[1]
        self.t_last = base + lag
        return {"arm_q_target": np.array(arms), "hand_q_target": np.array(hands)}

    def _redetect(self, obs):
        if not (self.initialized and self.started) or PV is None: return
        if self.redetect is not None:
            if not self.redetect.done(): return
            try:
                res = self.redetect.result()
                if res is not None: self.objs = res; self._build_cands(); self.sel = {}
            except Exception as e: self._write({"event": "REDETECT_ERROR", "error": str(e)})
            self.redetect = None; self.t_detect = time.time(); return
        if time.time() - self.t_detect < REDETECT_S or any(ch.stage is not None for ch in self.chains.values()): return
        rgb, depth = obs.get("head_rgb"), obs.get("head_depth")
        if not (_valid_image(rgb) and depth is not None and np.asarray(depth).any()): return
        ep = self.ep; a = np.asarray(obs["arm_q"], float).copy(); h = np.asarray(obs["hand_q"], float).copy()
        def job():
            self._vision(np.asarray(rgb).copy(), np.asarray(depth).copy(), a, h, ep)
            return list(self.perc[5]) if self.perc is not None and len(self.perc) > 5 and ep == self.ep else None
        self.redetect = self.worker.submit(job)

    def _act1(self, obs, t):
        arm = np.asarray(obs["arm_q"], float); hand = np.asarray(obs["hand_q"], float); self.tick += 1
        if self.head_err: self._write({"event": "HEAD_IMG_ERROR", "error": self.head_err}); self.head_err = None
        if self.last_cmd is None:                                     # IK starts from the MEASURED joints
            self.kin.a.q.update({n: float(v) for n, v in zip(arm_ik.ARM_NAMES, arm)}); self.kin.a.apply(); self.last_cmd = arm.copy()
        if not self.hand_init: self.rt.q = [float(np.clip(v, *j["filter"])) for v, j in zip(hand, self.rt.joints)]; self.hand_init = True
        if not self.started: return self._startup(obs, hand)
        if not self.initialized: self.initialized = self._init(obs)
        fingers = {"left": None, "right": None}; info = {}; prev = dict(self.kin.a.q); reasons = []
        if self.initialized and not self.abort:
            for side, ch in self.chains.items():
                s = self.src.read(side, self.tick)
                if s is None or s[1] is None or s[2] is None or not np.isfinite(s[1]).all():
                    info[side] = "no wrist"; out = None
                    s = (np.zeros(5) if s is None else s[0], None, None)
                else:
                    self._select(side, ch, T.pinch(self.kin, side))
                    near = lambda p: (FRAGILE_V if np.linalg.norm(p - self.seen[side]) > FRAGILE_R / 2 else FRAGILE_V / 2) \
                        if ch.grasp[3] == "egg" and np.linalg.norm(p - self.seen[side]) < FRAGILE_R else None
                    pin = T.pinch(self.kin, side)
                    out = ch.update(s[0], s[1], s[2], t, pin, self.kin.a.d.xmat[self.kin.a.ee[side]].reshape(3, 3),
                                    near_egg=near, wrist_p_now=self.kin.a.d.xpos[self.kin.a.ee[side]].copy())
                    step0 = arm_ik.ARM_STEP; arm_ik.ARM_STEP = (FRAGILE_JOINT if near(pin) is not None else JOINT_SPEED) / RATE
                    why = CC.solve_arm(self.kin, side, out, self.cfg, self.rest, self._unsafe, self.floor, T.palm); arm_ik.ARM_STEP = step0
                    reasons += why; info[side] = out["mode"] + (f" ev:{out['ev']}" if out["ev"] else "")
                    # each robot finger follows its own glove finger; the chain's limit (pre-shape 50 % while approaching,
                    # 0 while releasing) scales them all
                    pr = ch.grasp[4]; F = np.asarray(s[0], float); g = 0.5 * (F[1] + F[2])
                    full = pr["cap"] * float(np.clip(g / pr["g_ref"], 0, 1)); k = 0.0 if full < 1e-6 else min(1.0, out["c"] / full)
                    fingers[side] = [k * pr["cap"] * float(np.clip(F[i] / pr["g_ref"], 0, 1)) for i in range(3)] + [0.0, 0.0]
            qcmd = np.asarray(self.kin.a.arm_q())
            if any(v < LIM["arm_q"][i]["filter"][0] or v > LIM["arm_q"][i]["filter"][1] for i, v in enumerate(qcmd)): reasons.append("joint_filter")
            if np.any(np.abs(qcmd - self.last_cmd) > JOINT_SPEED / RATE + 1e-4): reasons.append("arm_speed")
            if reasons:
                self.kin.a.q.update(prev); self.kin.a.apply(); self.blocked += 1; self.consec += 1
                fingers = {"left": None, "right": None}
                if self.consec == 3: self._write({"event": "HOLD", "reasons": reasons, "consecutive_blocks": self.consec})   # hold the last command, NOT latched: tracking resumes as soon as a step is safe (was ABORT_HOLD for the whole episode)
            else: self.consec = 0
        ok = self.initialized and not self.abort and not reasons
        arm_t = np.asarray(self.kin.a.arm_q()) if ok else self.last_cmd.copy()
        arm_t, frac = self._ws_safe(arm_t)
        if frac < 1.0: self.kin.a.q.update({n: float(v) for n, v in zip(arm_ik.ARM_NAMES, arm_t)}); self.kin.a.apply(); reasons = reasons + ["ws_scaled"]
        hq = np.asarray(self.rt.step(left=fingers["left"], right=fingers["right"])) if ok else np.asarray(self.rt.q, float)
        hq = np.clip(hq, SAFE_LO["hand_q"], SAFE_HI["hand_q"])     # the real resting fingers sit past the URDF limits
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
