"""V1 live senza Coil: camera + guanti, due oggetti forzati e presa autonoma.

Avvio policy: py -3.11 g1/live_policy_v1.py --source udp:14043 --right egg --left can_empty --right-xy 0.35,-0.15 --left-xy 0.35,0.15
Replay:       py -3.11 g1/live_policy_v1.py --source replay:77,78 --right egg --left can_empty --right-xy 0.35,-0.15 --left-xy 0.35,0.15
Runner mock (secondo terminale): cd C:\\Users\\giorg\\Desktop\\aaltonomous-humanoid; py -3.11 -m aaltonomous.deploy.runner --backend mock --policy ws://localhost:8000 --team giorgio --episodes 1
G1_MAX_CLOSURE=0.1 alla prima prova. I target xy CLI sono nel frame pelvis e in metri.
"""
import argparse, json, os, socket, subprocess, sys, time
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
arm_ik.ARM_STEP = 0.7 / RATE          # IK steps within 70 % of the 1 rad/s arm cap (the same margin the safety check enforces)
LIM = json.load(open(os.path.join(ROOT, "docs", "g1_dex3_limits.json")))
PROFILE = {"egg": {"cap": .70, "g_ref": .29}, "can_empty": {"cap": 1., "g_ref": .52},
           "stress_ball": {"cap": 1., "g_ref": .36}}
MIRROR = np.diag([1., -1., 1.])


def _valid_image(rgb, depth):
    return rgb is not None and depth is not None and np.asarray(rgb).size and np.asarray(depth).size and np.asarray(rgb).any() and np.asarray(depth).any()


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
        try:
            while True:
                d = json.loads(self.sock.recv(65536).decode())
                for h in ("left", "right"):
                    if d.get(h) is not None: self.last[h] = d[h]
                if "fingers" in d and d.get("hand") in self.last: self.last[d["hand"]] = d["fingers"]
        except BlockingIOError: pass
        return None if self.last[side] is None else np.asarray(self.last[side], float)

    def start(self): self.t0 = time.time()


class LivePolicy(Policy):
    name = "live-g1-vision-glove-v1"; action_horizon = CHUNK

    def __init__(self, source, right, left, right_xy=None, left_xy=None):
        self.source = GloveInput(source); self.source.start(); self.obj = {"right": right, "left": left}
        self.xy = {"right": right_xy, "left": left_xy}; self.caps = G1Dex3Retargeter().max_closure
        self.rt = G1Dex3Retargeter(); self.rt.max_step *= .7
        self.kin = D.Kin(); self.initialized = False; self.targets = {}; self.states = {h: "HOVER" for h in self.obj}
        self.t_state = {h: 0. for h in self.obj}; self.lift = {h: 0. for h in self.obj}; self.blocked = 0; self.abort = False
        os.makedirs(LIVE, exist_ok=True); self.log = open(os.path.join(LIVE, "live_policy_v1.jsonl"), "a")
        self.pick = None; self.pick_started = False

    def reset(self, instruction, task=None, seed=None):
        self.initialized = False; self.blocked = 0; self.abort = False; self.t0 = time.time()

    def _recognize(self, rgb):
        try:
            import cv2
            path = os.path.join(LIVE, f"head_{int(time.time())}.jpg"); cv2.imwrite(path, np.asarray(rgb)[:, :, ::-1])
            p = subprocess.run([sys.executable, "-m", "ai.pick_profile", "--image", path], cwd=ROOT, capture_output=True, text=True, timeout=60)
            line = next((x for x in reversed(p.stdout.splitlines()) if x.strip().startswith("{")), "{}")
            self.pick = json.loads(line)
        except Exception as e: self.pick = {"error": str(e)}

    def _locate(self, rgb, depth, side):
        import importlib
        locate_mod = importlib.import_module("ai.locate")
        calmod = importlib.import_module("aaltonomous.interface.calibration")
        cal = getattr(calmod, "calibration", None) or getattr(calmod, "cal", None)
        def pixel_to_pelvis(u, v, d):
            if cal is None: raise RuntimeError("calibrazione camera organizzatori non disponibile")
            return cal.pixel_to_pelvis("head", u, v, d)
        dep = np.asarray(depth)
        if float(np.nanmedian(dep)) < 10.: dep = dep * 1000.
        result = locate_mod.locate(rgb, dep, pixel_to_pelvis, label=self.obj[side])
        if isinstance(result, tuple): result = result[0]
        if isinstance(result, dict):
            for k in ("position", "xyz", "point", "pelvis"):
                if k in result: result = result[k]; break
        p = np.asarray(result, float).reshape(-1)[:3]
        if p.size != 3 or not np.isfinite(p).all(): raise ValueError("locate returned no finite 3D point")
        # locate/calibration produce pelvis coordinates in metres; detect mm output conservatively.
        if np.linalg.norm(p) > 3.: p /= 1000.
        return p

    def _grasp_pose(self, side, obj, seen):
        bg = D.best_grasp(obj)
        if not bg: raise RuntimeError(f"missing best_grasp for {obj}")
        posture, aim, _ = bg; k = D.Kin(); rt = G1Dex3Retargeter(max_closure=1.)
        for _ in range(30): hq = rt.step(left=[.5*PROFILE[obj]["cap"]]*3+[0,0], right=[.5*PROFILE[obj]["cap"]]*3+[0,0])
        q = dict(posture)
        if side == "left":
            for key in list(q):
                if key.startswith("right_"):
                    val = q.pop(key); q[key.replace("right_", "left_")] = -val if any(x in key for x in ("shoulder_roll", "shoulder_yaw", "wrist_roll", "wrist_yaw")) else val
        k.a.q.update(q); k.a.apply(hq); ee = k.a.ee[side]; R = k.a.d.xmat[ee].reshape(3,3).copy()
        aim = np.asarray(aim) * ([1,-1,1] if side == "left" else 1)
        # Align the simulated pinch point to the located object plus the searched aim offset.
        b = ee; pinch_offset = np.array([.0415, .003 if side == "left" else -.003, 0.])
        pinch = k.a.d.xpos[b] + R @ pinch_offset
        grasp = k.a.d.xpos[b] + (seen + aim - pinch)
        return grasp, R

    def _init_targets(self, obs):
        self.kin.a.q.update({n: float(v) for n,v in zip(arm_ik.ARM_NAMES, np.asarray(obs["arm_q"],float))}); self.kin.a.apply()
        rgb, depth = obs.get("head_rgb"), obs.get("head_depth")
        if not _valid_image(rgb, depth):
            # no camera frame yet: wait; after 3 s, if the staff gave the positions on the command line, use them (mock runner = black images)
            if not hasattr(self, "t_wait"): self.t_wait = time.time()
            if time.time() - self.t_wait < 3.0 or any(self.xy[sd] is None for sd in self.obj): return False
            rgb = depth = None
        for side in self.obj:
            try:
                if rgb is None: raise RuntimeError("no camera frame")
                seen = self._locate(rgb, depth, side); origin = "camera"
            except Exception as e:
                if self.xy[side] is None:
                    self._write({"event":"NO_POSE", "hand":side, "error":str(e)}); return False
                seen = np.array([self.xy[side][0], self.xy[side][1], D.COUNTER_Z + D.half_h(self.obj[side])]); origin = "cli_fallback"
            gp, R = self._grasp_pose(side, self.obj[side], seen)
            # setup is only for target geometry; start every IK solution from measured robot joints.
            self.kin.a.q.update({n: float(v) for n,v in zip(arm_ik.ARM_NAMES, np.asarray(obs["arm_q"],float))}); self.kin.a.apply()
            self.targets[side] = (gp, R, origin, seen.tolist())
            self._write({"event":"POSE", "hand":side, "object":self.obj[side], "position":seen.tolist(), "source":origin})
        return True

    def _write(self, d):
        d["t"] = round(time.time()-getattr(self,"t0",time.time()),3); self.log.write(json.dumps(d)+"\n"); self.log.flush()

    def act(self, obs):
        """CHUNK consecutive ticks: each step starts from the previous COMMAND (the measured joints only for the first)."""
        o = dict(obs); arms, hands = [], []
        for k in range(CHUNK):
            r = self._act1(o); arms.append(r["arm_q_target"][0]); hands.append(r["hand_q_target"][0])
            o["arm_q"] = arms[-1]; o["hand_q"] = hands[-1]
        return {"arm_q_target": np.array(arms), "hand_q_target": np.array(hands)}

    def _act1(self, obs):
        arm = np.asarray(obs["arm_q"],float); hand = np.asarray(obs["hand_q"],float)
        if not self.pick_started and _valid_image(obs.get("head_rgb"), obs.get("head_depth")):
            self.pick_started = True
            import threading
            threading.Thread(target=self._recognize,args=(np.asarray(obs["head_rgb"]).copy(),),daemon=True).start()
        if not self.initialized: self.initialized = self._init_targets(obs)
        if not getattr(self, "hand_initialized", False):
            self.rt.q = [float(np.clip(v,*j["filter"])) for v,j in zip(hand,self.rt.joints)]; self.hand_initialized = True
        self.finger_now = {}
        candidates = {}
        for side in self.obj:
            f = self.source.read(side); self.finger_now[side] = f; g = 0. if f is None else float(np.mean([f[1],f[2]])); pr=PROFILE[self.obj[side]]; st=self.states[side]; now=time.time()
            if st=="HOVER" and g>.3*pr["g_ref"]: self.states[side]="DESCEND"; self.t_state[side]=now
            elif st=="DESCEND" and g<.25*pr["g_ref"]: self.states[side]="HOVER"
            elif st=="DESCEND" and now-self.t_state[side]>=1.: self.states[side]="GRASP"; self.t_state[side]=now
            elif st in ("GRASP","LIFT") and g<.25*pr["g_ref"]: self.states[side]="RELEASE"; self.t_state[side]=now
            elif st=="GRASP" and now-self.t_state[side]>=1.5: self.states[side]="LIFT"; self.t_state[side]=now
            elif st=="RELEASE" and now-self.t_state[side]>=1.: self.states[side]="HOVER"
            gp,R,_,_=self.targets.get(side,(None,None,None,None)); clear={"HOVER":.10,"DESCEND":.10*max(0.,1-(now-self.t_state[side])),"GRASP":0.,"LIFT":0.,"RELEASE":.10*min(1.,now-self.t_state[side])}[self.states[side]]
            if self.states[side]=="LIFT": self.lift[side]=min(.12,self.lift[side]+.12/30.)
            elif self.states[side] in ("HOVER","DESCEND","GRASP"): self.lift[side]=0.
            elif self.states[side]=="RELEASE": self.lift[side]=max(0.,self.lift[side]-.12/30.)
            if gp is not None:
                target=gp+np.array([0,0,clear+self.lift[side]]); target[2]=max(target[2], self.kin.base[2]+D.KEEP["z"]+.01)
                candidates[side]=(target,R)
        prev = dict(self.kin.a.q); safe=self.initialized and not self.abort
        if safe:
            for side,(p,R) in candidates.items(): self.kin.a.solve(side,p,R)
            reasons=[]
            for side in self.obj:
                if side not in candidates: continue
                for point in (self.kin.a.d.xpos[self.kin.a.ee[side]], self.kin.a.d.xpos[self.kin.a.ee[side]]+self.kin.a.d.xmat[self.kin.a.ee[side]].reshape(3,3)@np.array([.0415,.003 if side=="left" else -.003,0])):
                    q=self.kin.pel(point)
                    if not (D.BOX["x"][0]<=q[0]<=D.BOX["x"][1] and D.BOX["y"][0]<=q[1]<=D.BOX["y"][1] and D.BOX["z"][0]<=q[2]<=D.BOX["z"][1]): reasons.append("box")
                    if D.KEEP["x"][0]<=q[0]<=D.KEEP["x"][1] and D.KEEP["y"][0]<=q[1]<=D.KEEP["y"][1] and q[2]<D.KEEP["z"]: reasons.append("table")
            if self.kin.a.self_collisions(): reasons.append("self_collision")
            if len(self.obj)==2:
                palms=[]
                for s in self.obj:
                    b=self.kin.a.ee[s]; palms.append(self.kin.a.d.xpos[b]+self.kin.a.d.xmat[b].reshape(3,3)@np.array([.0415,.003 if s=="left" else -.003,0]))
                if np.linalg.norm(palms[0]-palms[1])<.10: reasons.append("palms_too_close")
            qcmd=np.asarray(self.kin.a.arm_q());
            if any(v< LIM["arm_q"][i]["filter"][0] or v>LIM["arm_q"][i]["filter"][1] for i,v in enumerate(qcmd)): reasons.append("joint_filter")
            ref = getattr(self, "last_cmd", None); ref = arm if ref is None else ref        # the runner checks speed against the LAST COMMAND
            if np.any(np.abs(qcmd-ref)>.7/RATE+1e-4): reasons.append("arm_speed")
            if reasons:
                self.kin.a.q.update(prev); self.kin.a.apply(); self.blocked+=1
                if self.blocked>=3: self.abort=True; self._write({"event":"ABORT","reasons":reasons,"consecutive_blocks":self.blocked})
                safe=False
            else: self.blocked=0
        arm_target=np.asarray(self.kin.a.arm_q()) if safe else (self.last_cmd.copy() if getattr(self, "last_cmd", None) is not None else arm.copy())
        self.last_cmd = np.asarray(arm_target, float).copy()
        fingers={"left":None,"right":None}
        for side in self.obj:
            f=self.finger_now.get(side)
            g=0. if f is None else float(np.mean([f[1],f[2]])); pr=PROFILE[self.obj[side]]
            c=pr["cap"]*float(np.clip(g/pr["g_ref"],0,1)) if self.states[side] in ("GRASP","LIFT") else 0.
            fingers[side]=[c,c,c,0,0]
        hq=self.rt.step(left=fingers["left"],right=fingers["right"])
        if not safe or self.abort:
            hq = hand.copy()
            self.rt.q = list(hand)
        if not self.initialized: arm_target=arm.copy(); hq=hand.copy()
        self._write({"state":self.states,"blocked":self.blocked,"abort":self.abort,"objects":self.obj,"pick":self.pick,"hand_q":np.asarray(hq).tolist(),"initialized":self.initialized})
        return {"arm_q_target":np.asarray(arm_target).reshape(1,-1),"hand_q_target":np.asarray(hq).reshape(1,-1)}


if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--source",default="udp:14043"); ap.add_argument("--right",choices=PROFILE,required=True); ap.add_argument("--left",choices=PROFILE,required=True)
    ap.add_argument("--right-xy",type=lambda s:tuple(map(float,s.split(",")))); ap.add_argument("--left-xy",type=lambda s:tuple(map(float,s.split(","))))
    ap.add_argument("--port",type=int,default=8000); ap.add_argument("--host",default="127.0.0.1"); a=ap.parse_args()
    serve(LivePolicy(a.source,a.right,a.left,a.right_xy,a.left_xy),port=a.port,host=a.host)
