"""V1 live senza Coil: la camera della testa trova gli oggetti, i guanti comandano la presa (logica = g1/sim/live_sim.py).
Per ogni mano: HOVER 10 cm sopra l'oggetto piu' vicino dal suo lato -> l'operatore chiude il guanto -> DESCEND -> GRASP (cap per oggetto:
uovo 0.70, lattina vuota 1.0, sconosciuto 0.68) -> LIFT 12 cm -> l'operatore apre -> RELEASE.
Percezione (g1/perception_v1.py: ai.perceive di Tommaso + voto geometrico, una volta al primo frame valido, in un thread; il robot resta fermo):
  oggetti = profondita' sopra il piano del tavolo (meno il robot stesso), etichetta = voto geometria+colore (+ VLM ai.recognize se --vlm),
  posizione = ai.locate. Le etichette CLI (--right/--left) sono OVERRIDE opzionali; --right-xy/--left-xy sono fallback e controllo:
  se la camera e la CLI differiscono piu' di --xy-gate si usa la CLI (loggato).
Avvio robot vero: py -3.11 g1/live_policy_v1.py --source udp:14043 --right-xy 0.35,-0.15 --left-xy 0.35,0.15 [--dry]
Replay:           py -3.11 g1/live_policy_v1.py --source replay:77,86 --right egg --left can_empty --right-xy 0.35,-0.15 --left-xy 0.35,0.15
Test visione sul mock (frame sim, SOLO TEST): ... --test-frames data/g1sim/v1_frames.npz
--dry: calcola tutto (percezione, stati, IK, controlli di sicurezza) e lo logga, ma comanda SEMPRE la posa iniziale misurata (braccia e mani ferme).
Procedura completa: docs/G1_V1_RUN.md. I target xy CLI sono nel frame pelvis, in metri. Log: data/live/live_policy_v1.jsonl
"""
import argparse, json, os, socket, sys, threading, time
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
REPO = os.environ.get("AALTO_REPO", r"C:\Users\giorg\Desktop\aaltonomous-humanoid")
assert os.path.isdir(REPO), "set AALTO_REPO to the aaltonomous-humanoid clone"
sys.path.insert(0, REPO)
from aaltonomous.deploy.policy_server import Policy, serve
from robot.g1_dex3 import G1Dex3Retargeter

CHUNK = 3   # 3 targets per call: ~28 ms of compute per tick cannot keep 30 Hz one tick at a time (mock: 21.7 Hz with CHUNK=1)
RATE = 30.0
LIVE = os.path.join(ROOT, "data", "live")
sys.path.insert(0, os.path.join(ROOT, "g1", "sim"))
import arm_ik, demo_e2e as D
from g1 import perception_v1 as PV
arm_ik.ARM_STEP = 0.7 / RATE          # IK steps within 70 % of the 1 rad/s arm cap (the same margin the safety check enforces)
LIM = json.load(open(os.path.join(ROOT, "docs", "g1_dex3_limits.json")))
try:   # the organisers' OWN workspace check (same code as the runner filter), to never send a step it would clip
    _AH = os.environ.get("AALTO_ROOT", r"C:\Users\giorg\Desktop\aaltonomous-humanoid")
    for _p in (os.path.join(_AH, "winshim"), _AH):
        if _p not in sys.path: sys.path.insert(0, _p)
    from aaltonomous.interface import safety as _AS
    WS = _AS.WorkspaceChecker(_AS.JointSpec(), _AS.SafetyConfig())
except Exception as _e:
    print("[v1] organisers' workspace check NOT loaded:", _e); WS = None
SAFE_LO = {k: np.array([e["filter"][0] for e in sorted(LIM[k], key=lambda e: e["idx"])]) + 0.005 for k in ("arm_q", "hand_q")}
SAFE_HI = {k: np.array([e["filter"][1] for e in sorted(LIM[k], key=lambda e: e["idx"])]) - 0.005 for k in ("arm_q", "hand_q")}
# cap = max hand closure; g_ref = typical glove closure for that object; shape = grasp posture / size used (unknown -> egg posture, gentle)
PROFILE = {"egg": {"cap": .70, "g_ref": .29, "shape": "egg"}, "can_empty": {"cap": PV.CAP["can_empty"], "g_ref": .52, "shape": "can_empty"},
           "stress_ball": {"cap": .70, "g_ref": .36, "shape": "stress_ball"}, "unknown": {"cap": .68, "g_ref": .29, "shape": "egg"}}
PERCEPTION_TIMEOUT = 25.0   # s; the runner holds the robot while we wait
SIDES = ("right", "left")
ARRIVE_M = .03   # wrist within 3 cm of the hover point before DESCEND is allowed
WRIST_FLOOR, PINCH_FLOOR = .02, .008   # m above the table plane: wrist (KEEP z of the sim checks) and pinch point (an egg's centre is 2.1 cm up)


def _valid_image(rgb, depth):
    return rgb is not None and depth is not None and np.asarray(rgb).size and np.asarray(depth).size and np.asarray(rgb).any() and np.asarray(depth).any()


def _fingers(v):
    """>= 3 finite closures in [0, 1] or None."""
    try:
        a = np.asarray(v, float).reshape(-1)
        return a.clip(0, 1).tolist() if a.size >= 3 and np.isfinite(a).all() else None
    except Exception: return None


class GloveInput:
    def __init__(self, source):
        self.sock = None; self.last = {"left": None, "right": None}; self.ep = None; self.i = 0
        if source.startswith("udp:"):
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.sock.bind(("0.0.0.0", int(source[4:]))); self.sock.setblocking(False)
        elif source.startswith("replay:"):
            takes = source[7:].split(",")
            if len(takes) != 2: raise ValueError("replay richiede replay:<take_destra>,<take_sinistra>")
            self.ep = {}
            for side, take in zip(("right", "left"), takes):
                z = np.load(os.path.join(ROOT, "data", "episodes", f"take_{int(take):02d}.npz"), allow_pickle=True)
                self.ep[side] = z[f"{side}_fingers01"] if f"{side}_fingers01" in z.files else z["right_fingers01"]   # head-glove takes: only the right hand recorded
        else: raise ValueError("source deve essere udp:<port> o replay:<destra>,<sinistra>")

    def read(self, side):
        if self.ep is not None:
            if not hasattr(self, "t_rep"): self.t_rep = time.time()          # replay starts at the first read and LOOPS (test only)
            a = self.ep[side]; value = a[int((time.time()-self.t_rep)*RATE) % len(a)]
            return np.asarray(value, float)
        while True:
            try: raw = self.sock.recv(65536)
            except (BlockingIOError, ConnectionResetError): break
            try:                                   # a malformed packet is dropped, never crashes the server
                d = json.loads(raw.decode())
                for h in ("left", "right"):
                    if d.get(h) is not None: self.last[h] = _fingers(d[h]) or self.last[h]
                if "fingers" in d and d.get("hand") in self.last: self.last[d["hand"]] = _fingers(d["fingers"]) or self.last[d["hand"]]
            except Exception: self.bad = getattr(self, "bad", 0) + 1
        return None if self.last[side] is None else np.asarray(self.last[side], float)

    def start(self): self.t0 = time.time()


class Camera:
    """pixel_to_pelvis + K/T of the head camera: organisers' calibration.yaml on the robot, or the K/T stored with --test-frames."""
    def __init__(self, test_frames=None):
        self.frames = None
        if test_frames:
            z = np.load(test_frames); self.frames = (z["rgb"], z["depth"]); self.K, self.T = z["K"], z["T"]
            self.frame_arm_q = z["arm_q"] if "arm_q" in z.files else None   # the pose the frames were rendered with (self-mask)
        else:
            from aaltonomous.interface.calibration import Calibration
            cal = Calibration.load(); self.K = cal.cams["head"].K; self.T = cal._T("head")
        self.p2p = PV.pinhole_pixel_to_pelvis(self.K, self.T)


class LivePolicy(Policy):
    name = "live-g1-vision-glove-v1"; action_horizon = CHUNK

    def __init__(self, source, right=None, left=None, right_xy=None, left_xy=None, vlm=(), dry=False, xy_gate=0.08, test_frames=None, engine="ai"):
        self.source = GloveInput(source); self.source.start()
        self.override = {"right": right, "left": left}; self.xy = {"right": right_xy, "left": left_xy}
        self.engine = engine; self.vlm = list(vlm); self.dry = dry; self.xy_gate = xy_gate; self.cam = Camera(test_frames)
        # ONE persistent worker: the MuJoCo renderer of the self-mask is bound to the GL context of the thread that created it
        # (a new thread per episode rendered garbage after the runner's reset -> objects merged with the hands)
        import concurrent.futures as cf
        self.worker = cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="perception")
        from finger_map import DirectRetargeter
        self.rt = DirectRetargeter(); self.rt.max_step *= .7          # thumb/index/middle one-to-one (14/11 evening)
        os.makedirs(LIVE, exist_ok=True); self.log = open(os.path.join(LIVE, "live_policy_v1.jsonl"), "a")
        self._write({"event": "START", "engine": engine, "dry": dry, "vlm": self.vlm, "override": self.override, "cli_xy": self.xy, "test_frames": test_frames})
        self.reset(None)

    def reset(self, instruction, task=None, seed=None):
        if not hasattr(self, "lock"): self.lock = threading.Lock()
        with self.lock: self.ep = getattr(self, "ep", 0) + 1; self.perc = None
        self.initialized = False; self.blocked = 0; self.abort = False; self.t0 = time.time()
        self.kin = D.Kin(); self.targets = {}; self.obj = {}; self.cap = {}
        self.states = {h: "HOVER" for h in SIDES}; self.t_state = {h: 0. for h in SIDES}; self.lift = {h: 0. for h in SIDES}
        self.perc_thread = None; self.t_perc = None; self.t_wait = None
        self.hold = None; self.last_cmd = None; self.last_hand = None; self.hand_initialized = False; self.table_z = D.COUNTER_Z

    # ---------------- perception ----------------
    def _perceive(self, rgb, depth, arm_q, hand_q, ep):
        try:
            sm = PV.robot_mask(arm_q, hand_q, self.cam.K, self.cam.T, shape=np.asarray(depth).shape)(depth)
            fn = PV.perceive_with_ai if self.engine == "ai" else PV.perceive
            res = fn(rgb, depth, self.cam.p2p, vlm=self.vlm, self_mask=sm)
        except Exception as e:
            res = {"objects": [], "error": f"{type(e).__name__}: {e}"}
        with self.lock:
            if ep == self.ep: self.perc = res      # a result from before a runner reset is dropped

    def _frame(self, obs):
        rgb, depth = obs.get("head_rgb"), obs.get("head_depth")
        if _valid_image(rgb, depth): return np.asarray(rgb).copy(), np.asarray(depth).copy(), "camera"
        if self.cam.frames is not None: return self.cam.frames[0], self.cam.frames[1], "test_frames"
        return None, None, None

    def _cli_point(self, side, label, table_z):
        x, y = self.xy[side]; z0 = D.COUNTER_Z if table_z is None else table_z
        return np.array([x, y, z0 + D.half_h(PROFILE[label]["shape"])])

    def _init_targets(self, obs):
        if self.perc_thread is None:
            rgb, depth, src = self._frame(obs)
            if rgb is not None:
                self.frame_src = src; self.t_perc = time.time()
                armq = self.cam.frame_arm_q if src == "test_frames" and getattr(self.cam, "frame_arm_q", None) is not None else obs["arm_q"]
                self.perc_thread = self.worker.submit(self._perceive, rgb, depth, np.asarray(armq, float).copy(), np.asarray(obs["hand_q"], float).copy(), self.ep)
                return False
            # no camera frame: after 3 s use the CLI positions if the staff gave both (mock runner = black images)
            if self.t_wait is None: self.t_wait = time.time()
            if time.time() - self.t_wait < 3.0 or any(self.xy[s] is None for s in SIDES): return False
            self.perc = {"objects": [], "error": "no camera frame in 3 s"}; self.frame_src = None
        elif self.perc is None:
            if time.time() - self.t_perc < PERCEPTION_TIMEOUT: return False
            self.perc = {"objects": [], "error": f"perception timeout {PERCEPTION_TIMEOUT} s"}
        p = self.perc
        self._write({"event": "PERCEPTION", "engine": p.get("engine", self.engine), "ai_error": p.get("ai_error"), "frame": self.frame_src, "table_z": p.get("table_z"), "error": p.get("error"), "t_s": p.get("t_s"),
                     "objects": [{k: o.get(k) for k in ("label", "cap", "ai_label", "ai_cap", "p_pelvis", "depth_ok", "height", "why", "votes")} for o in p["objects"]]})
        asg = PV.assign(p["objects"]); arm = np.asarray(obs["arm_q"], float)
        if p.get("table_z") is not None: self.table_z = float(p["table_z"])   # measured table plane (pelvis z); else the sim counter
        for side in SIDES:
            o = asg[side]
            if o is not None and o["depth_ok"] and self.xy[side] is not None and np.hypot(*(np.asarray(o["p_pelvis"][:2]) - np.asarray(self.xy[side]))) > self.xy_gate:
                self._write({"event": "VISION_CLI_DISAGREE", "hand": side, "camera": o["p_pelvis"], "camera_label": o["label"], "cli": self.xy[side], "gate_m": self.xy_gate})
                o = None
            elif o is not None and not o["depth_ok"]:
                self._write({"event": "VISION_REFUSED", "hand": side, "camera": o["p_pelvis"], "camera_label": o["label"], "why": o.get("locate_why")}); o = None
            # the camera label is used ONLY with the camera position of the same object; otherwise CLI override or unknown (0.68)
            label = self.override[side] or (o["label"] if o else "unknown")
            cap = PROFILE[label]["cap"] if self.override[side] else (o["cap"] if o else PROFILE["unknown"]["cap"])
            if self.override[side] and o is not None and o["label"] == "egg" and o["cap"] < cap:   # fragile-first beats the override's cap
                self._write({"event": "OVERRIDE_CAP_LOWERED", "hand": side, "override": label, "camera_label": "egg", "cap": o["cap"]}); cap = o["cap"]
            if o is not None:
                seen = np.asarray(o["p_pelvis"], float); origin = "camera"
            elif self.xy[side] is not None:
                seen = self._cli_point(side, label, p.get("table_z")); origin = "cli_fallback"
            else:
                self._write({"event": "NO_OBJECT", "hand": side, "why": "no usable object on this side and no --%s-xy" % side}); continue
            gp, R = self._grasp_pose(side, label, cap, seen, arm)
            self.obj[side] = label; self.cap[side] = cap; self.targets[side] = (gp, R, origin, seen.tolist())
            self._write({"event": "POSE", "hand": side, "object": label, "cap": cap, "override": bool(self.override[side]),
                         "position": np.round(seen, 4).tolist(), "source": origin})
        self.kin.a.q.update({n: float(v) for n, v in zip(arm_ik.ARM_NAMES, arm)}); self.kin.a.apply()
        return True

    def _grasp_pose(self, side, label, cap, seen, arm):
        shape = PROFILE[label]["shape"]; bg = D.best_grasp(shape)
        if not bg: raise RuntimeError(f"missing best_grasp for {shape}")
        posture, aim, _ = bg; k = D.Kin(); rt = G1Dex3Retargeter(max_closure=1.)
        for _ in range(30): hq = rt.step(left=[.5*cap]*3+[0,0], right=[.5*cap]*3+[0,0])
        q = dict(posture)
        if side == "left":
            for key in list(q):
                if key.startswith("right_"):
                    val = q.pop(key); q[key.replace("right_", "left_")] = -val if any(x in key for x in ("shoulder_roll", "shoulder_yaw", "wrist_roll", "wrist_yaw")) else val
        k.a.q.update(q); k.a.apply(hq); ee = k.a.ee[side]; R = k.a.d.xmat[ee].reshape(3,3).copy()
        aim = np.asarray(aim) * ([1,-1,1] if side == "left" else 1)
        # Align the simulated pinch point to the located object plus the searched aim offset. seen is PELVIS frame, the Kin model is
        # WORLD (pelvis at z 0.793): convert, as g1/sim/live_sim.py does (before: targets were 0.79 m low and clamped to the table floor).
        pinch_offset = np.array([.0415, .003 if side == "left" else -.003, 0.])
        pinch = k.a.d.xpos[ee] + R @ pinch_offset
        grasp = k.a.d.xpos[ee] + (k.base + seen + aim - pinch)
        return grasp, R

    def _write(self, d):
        d["t"] = round(time.time()-getattr(self,"t0",time.time()),3); self.log.write(json.dumps(d, default=str)+"\n"); self.log.flush()

    def _save_head(self, obs):
        """Operator console (PR #153): latest head frame as data/live/head_latest.jpg, at most 2 Hz, atomic replace."""
        now = time.time()
        if now - getattr(self, "t_head", 0.) < 0.5 or not _valid_image(obs.get("head_rgb"), obs.get("head_depth")): return
        self.t_head = now
        try:
            import cv2
            tmp = os.path.join(LIVE, "head_latest.tmp.jpg"); cv2.imwrite(tmp, np.asarray(obs["head_rgb"], np.uint8)[:, :, ::-1])
            os.replace(tmp, os.path.join(LIVE, "head_latest.jpg"))
        except Exception as e: self._write({"event": "HEAD_JPG_ERROR", "error": str(e)})

    # ---------------- control ----------------
    def act(self, obs):
        """CHUNK consecutive ticks: each step starts from the previous COMMAND (the measured joints only for the first)."""
        self._save_head(obs)
        o = dict(obs); arms, hands = [], []
        for k in range(CHUNK):
            r = self._act1(o); arms.append(r["arm_q_target"][0]); hands.append(r["hand_q_target"][0])
            if not self.dry: o["arm_q"] = arms[-1]; o["hand_q"] = hands[-1]
        # Real G1: the measured rest pose can sit just past the URDF limits (left index/middle curled at -1.58..-1.70):
        # commanding it back counts as a safety clip every tick -> runner abort after 30. Keep every target inside the
        # filter range (URDF minus margin), with 5 mrad of slack.
        arms = np.clip(np.array(arms), SAFE_LO["arm_q"], SAFE_HI["arm_q"])
        hands = np.clip(np.array(hands), SAFE_LO["hand_q"], SAFE_HI["hand_q"])
        return {"arm_q_target": arms, "hand_q_target": hands}

    def _geom_violations(self, sides):
        """{reason: severity (m)} of the current IK pose: box, table_wrist/table_pinch (depth under the floor), self_collision (penetration)."""
        out = {}
        def add(k, v): out[k] = max(out.get(k, 0.), float(v))
        for side in sides:
            wr = self.kin.a.d.xpos[self.kin.a.ee[side]]; pinch = wr+self.kin.a.d.xmat[self.kin.a.ee[side]].reshape(3,3)@np.array([.0415,.003 if side=="left" else -.003,0])
            for point, floor in ((wr, WRIST_FLOOR), (pinch, PINCH_FLOOR)):
                q=self.kin.pel(point)
                bv = sum(max(D.BOX[a][0]-q[i], 0.)+max(q[i]-D.BOX[a][1], 0.) for i, a in enumerate("xyz"))
                if bv > 0: add("box", bv)
                if D.KEEP["x"][0]<=q[0]<=D.KEEP["x"][1] and D.KEEP["y"][0]<=q[1]<=D.KEEP["y"][1] and q[2]<self.table_z+floor:
                    add(f"table_{'wrist' if floor==WRIST_FLOOR else 'pinch'}", self.table_z+floor-q[2])
        sc = self.kin.a.self_collisions()
        if sc: add("self_collision", max(0.02-c[2] for c in sc))
        return out

    def _act1(self, obs):
        arm = np.asarray(obs["arm_q"],float); hand = np.asarray(obs["hand_q"],float)
        if self.hold is None: self.hold = (arm.copy(), hand.copy())           # --dry commands this pose forever
        if not self.initialized:
            self.initialized = self._init_targets(obs)
            if not self.initialized:
                hold_arm = self.hold[0] if self.dry else arm
                self._write({"state": "WAIT_PERCEPTION", "dry": self.dry, "arm_q_target": np.round(hold_arm, 4).tolist()})
                return {"arm_q_target": (self.hold[0] if self.dry else arm).reshape(1,-1), "hand_q_target": (self.hold[1] if self.dry else hand).reshape(1,-1)}
        if not self.hand_initialized:
            self.rt.q = [float(np.clip(v,*j["filter"])) for v,j in zip(hand,self.rt.joints)]; self.hand_initialized = True
        self.finger_now = {}; candidates = {}; now = time.time()
        for side in self.obj:
            f = self.source.read(side); self.finger_now[side] = f; g = 0. if f is None else float(np.mean([f[1],f[2]])); pr=PROFILE[self.obj[side]]; st=self.states[side]
            # descend only once the wrist is AT the hover point (a glove already closed at start would descend from the home pose)
            arrived = np.linalg.norm(self.kin.a.d.xpos[self.kin.a.ee[side]] - (self.targets[side][0] + [0, 0, .10])) < ARRIVE_M
            if st=="HOVER" and g>.3*pr["g_ref"] and arrived: self.states[side]="DESCEND"; self.t_state[side]=now
            elif st=="DESCEND" and g<.25*pr["g_ref"]: self.states[side]="HOVER"
            elif st=="DESCEND" and now-self.t_state[side]>=1.: self.states[side]="GRASP"; self.t_state[side]=now
            elif st in ("GRASP","LIFT") and g<.25*pr["g_ref"]: self.states[side]="RELEASE"; self.t_state[side]=now
            elif st=="GRASP" and now-self.t_state[side]>=1.5: self.states[side]="LIFT"; self.t_state[side]=now
            elif st=="RELEASE" and now-self.t_state[side]>=1.: self.states[side]="HOVER"
            gp,R,_,_=self.targets[side]; clear={"HOVER":.10,"DESCEND":.10*max(0.,1-(now-self.t_state[side])),"GRASP":0.,"LIFT":0.,"RELEASE":.10*min(1.,now-self.t_state[side])}[self.states[side]]
            if self.states[side]=="LIFT": self.lift[side]=min(.12,self.lift[side]+.12/30.)
            elif self.states[side] in ("HOVER","DESCEND","GRASP"): self.lift[side]=0.
            elif self.states[side]=="RELEASE": self.lift[side]=max(0.,self.lift[side]-.12/30.)
            target=gp+np.array([0,0,clear+self.lift[side]]); target[2]=max(target[2], self.kin.base[2]+self.table_z+WRIST_FLOOR+.01)
            candidates[side]=(target,R)
        # ESCAPE: the real rest pose has wrists/palms inside the organisers' counter keep-out. Their filter rejects any step that
        # increases the total penetration, so first lift every wrist STRAIGHT UP (same x, y, orientation) until it is out.
        ref_cmd = arm if self.last_cmd is None else self.last_cmd
        # JOINT-SPACE lift (as g1/arms_simple.py, which worked on the robot): shoulder pitch -0.02, elbow -0.01 rad per tick.
        # (Cartesian IK from that pose moved the wrists DOWN: the rest pose sits on joint limits.)
        self.escape_up = WS is not None and WS.violation(ref_cmd) > 1e-4
        if self.escape_up:
            q = np.asarray(ref_cmd, float).copy()
            for i in (0, 7): q[i] -= 0.02; q[i + 3] -= 0.01
            q = np.clip(q, SAFE_LO["arm_q"], SAFE_HI["arm_q"])
            for n, v in zip(arm_ik.ARM_NAMES, q): self.kin.a.q[n] = float(v)
            self.kin.a.apply()
        prev = dict(self.kin.a.q); safe = not self.abort; reasons = []
        if safe and not self.escape_up:
            old = self._geom_violations(candidates)              # violations of the CURRENT pose (real start pose may already have some)
            for side,(p,R) in candidates.items(): self.kin.a.solve(side,p,R)
            new = self._geom_violations(candidates)
            # a geometric violation blocks only if it is NEW or gets WORSE: from a start pose that is already low / close
            # to the body the arm may still move OUT of it (escape), never deeper.
            for k, v in new.items():
                if k not in old or v > old[k] + 1e-4: reasons.append(k)
            self.escape = sorted(k for k in new if k not in reasons)
            if len(self.obj)==2:
                palms=[]
                for s in self.obj:
                    b=self.kin.a.ee[s]; palms.append(self.kin.a.d.xpos[b]+self.kin.a.d.xmat[b].reshape(3,3)@np.array([.0415,.003 if s=="left" else -.003,0]))
                if np.linalg.norm(palms[0]-palms[1])<.10: reasons.append("palms_too_close")
            qcmd=np.asarray(self.kin.a.arm_q())
            if any(v< LIM["arm_q"][i]["filter"][0] or v>LIM["arm_q"][i]["filter"][1] for i,v in enumerate(qcmd)): reasons.append("joint_filter")
            ref = arm if self.last_cmd is None else self.last_cmd        # the runner checks speed against the LAST COMMAND
            if np.any(np.abs(qcmd-ref)>.7/RATE+1e-4): reasons.append("arm_speed")
            if reasons:
                self.kin.a.q.update(prev); self.kin.a.apply()
                # hitting the table floor while descending = simply stop lower (hold the last command): not an abort reason
                self.blocked = self.blocked + 1 if any(not r.startswith("table_") for r in reasons) else self.blocked
                if self.blocked>=3: self.abort=True; self._write({"event":"ABORT","reasons":reasons,"consecutive_blocks":self.blocked})
                safe=False
            else: self.blocked=0
        arm_target=np.asarray(self.kin.a.arm_q()) if safe else (self.last_cmd.copy() if self.last_cmd is not None else arm.copy())
        if WS is not None:   # same rule as the runner filter: never more penetration than the last command (bisect the step)
            allowed = max(WS.violation(ref_cmd), 1e-4); arm_target = np.asarray(arm_target, float)   # exactly the runner filter rule
            if WS.violation(arm_target) > allowed:
                lo_s, hi_s, step = 0.0, 1.0, arm_target - ref_cmd
                for _ in range(10):
                    mid = .5 * (lo_s + hi_s)
                    if WS.violation(ref_cmd + mid * step) <= allowed: lo_s = mid
                    else: hi_s = mid
                arm_target = ref_cmd + lo_s * step; reasons = reasons + ["ws_scaled"]
                self.kin.a.q.update({n: v for n, v in zip(self.kin.a.q, prev.values())}) if lo_s == 0 else None
        self.last_cmd = np.asarray(arm_target, float).copy()
        fingers={"left":None,"right":None}
        for side in self.obj:
            f=self.finger_now.get(side)
            g=0. if f is None else float(np.mean([f[1],f[2]])); pr=PROFILE[self.obj[side]]
            import finger_map as FM   # each robot finger follows its own glove finger, capped by the object profile (egg 0.70)
            fingers[side]=FM.closures(f, pr["g_ref"], self.cap[side]) if self.states[side] in ("GRASP","LIFT") else [0.]*5
        hq=self.rt.step(left=fingers["left"],right=fingers["right"])
        if not safe:   # hold the LAST COMMAND (not the measured hand: the runner checks hand speed against the last command)
            hq = (hand if self.last_hand is None else self.last_hand).copy(); self.rt.q = list(hq)
        self.last_hand = np.asarray(hq, float).copy()
        tgt = {s: np.round(self.kin.pel(self.kin.a.d.xpos[self.kin.a.ee[s]]), 3).tolist() for s in self.obj}
        self._write({"state":{s:self.states[s] for s in self.obj},"blocked":self.blocked,"reasons":reasons,"escape":getattr(self,"escape",[]),"abort":self.abort,"objects":self.obj,"cap":self.cap,
                     "wrist_pelvis":tgt,"hand_q":np.round(np.asarray(hq),3).tolist(),"dry":self.dry,
                     "arm_q_target":np.round(self.hold[0] if self.dry else np.asarray(arm_target),4).tolist(),       # what is SENT (console sim view)
                     **({"arm_q_plan":np.round(np.asarray(arm_target),4).tolist()} if self.dry else {})})          # --dry: what WOULD be sent
        if self.dry: return {"arm_q_target":self.hold[0].reshape(1,-1),"hand_q_target":self.hold[1].reshape(1,-1)}
        return {"arm_q_target":np.asarray(arm_target).reshape(1,-1),"hand_q_target":np.asarray(hq).reshape(1,-1)}


if __name__ == "__main__":
    def xy(s):
        v = tuple(map(float, s.split(",")))
        if len(v) != 2: raise argparse.ArgumentTypeError("x,y in metri, frame pelvis")
        return v
    ap=argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source",default="udp:14043")
    ap.add_argument("--right",choices=PROFILE,default=None,help="override dell'etichetta vista dalla camera (default: camera)")
    ap.add_argument("--left",choices=PROFILE,default=None,help="override dell'etichetta vista dalla camera (default: camera)")
    ap.add_argument("--right-xy",type=xy,help="x,y pelvis (m): fallback senza camera e controllo della camera");ap.add_argument("--left-xy",type=xy)
    ap.add_argument("--xy-gate",type=float,default=0.08,help="m: camera e CLI piu' lontane di cosi' -> usa la CLI")
    ap.add_argument("--vlm",default="none",help="none | auto (backend con chiave nell'ambiente) | lista es. nemotron,gemma")
    ap.add_argument("--perception",default="ai",choices=["ai","g1"],help="ai = ai.perceive (Tommaso) + voto geometrico; g1 = solo g1/perception_v1")
    ap.add_argument("--dry",action="store_true",help="solo log: braccia e mani restano ferme nella posa iniziale")
    ap.add_argument("--test-frames",default=None,help="SOLO TEST: npz con rgb/depth/K/T usato quando la camera manda frame vuoti (mock)")
    ap.add_argument("--port",type=int,default=8000); ap.add_argument("--host",default="127.0.0.1"); a=ap.parse_args()
    vlm = [] if a.vlm == "none" else (PV.available_vlm() if a.vlm == "auto" else [b for b in a.vlm.split(",") if b])
    serve(LivePolicy(a.source,a.right,a.left,a.right_xy,a.left_xy,vlm=vlm,dry=a.dry,xy_gate=a.xy_gate,test_frames=a.test_frames,engine=a.perception),port=a.port,host=a.host)
