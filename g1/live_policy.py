"""Policy for the ONE live G1 test: the robot's head camera recognises the object, the glove drives the Dex3 hand, the object decides
how far the robot hand closes. Arms HOLD the measured pose (safest). Runs behind the organisers' runner + safety filter.
  py -3.11 g1/live_policy.py --source udp:14043 [--object egg|stress_ball|can_empty|can|none] [--hand right] [--port 8000]
  py -3.11 g1/live_policy.py --source replay:77            (rehearsal with a recorded take, right_fingers01)
  cd <aaltonomous clone>; py -3.11 -m aaltonomous.deploy.runner --backend mock --policy ws://localhost:8000 --team giorgio --episodes 1
Env: AALTO_REPO (default C:/Users/giorg/Desktop/aaltonomous-humanoid), G1_MAX_CLOSURE (retargeter scale, 0.1 on the first real run).
Object recognition: on the first non-black obs["head_rgb"] the frame is saved to data/live/head_<t>.jpg and `python -m ai.pick_profile
--image <jpg>` (Tommaso's picker: Nemotron, Gemini backup, safety rules that only soften) runs ONCE in a background thread. Until it
answers, on failure, or on an unclear answer the CONSERVATIVE profile (unknown, cap 0.68) is used. --object forces the object (no model).
Profile mapping (data of 14/11, takes 75-89): g = mean(index, middle) fingers01 of the operating hand; robot closure
c = cap * clip(g / g_ref, 0, 1); [thumb=c, index=c, middle=c] -> G1Dex3Retargeter. So the operator's typical grip on that object
becomes the object's robot closure: egg gentle (0.70; sim: holds from 0.65, breaks above 0.75), stress ball full (1.0; sim: does not
break), empty can strong (1.0; may dent, acceptable). Caps from g1/object_profiles.json where present, else PROFILE below.
Every tick is logged to data/live/live_log.jsonl.
SCALE RISK: g_ref values come from the episodes (fingers01 normalised with data/calib.json, series E). Live fingers come from
Rokoko/src/rgmp_client.py, normalised by its own 8 s open/close sweep: do a FULL open hand + FULL fist during that sweep so the two scales match.
UNTESTED ON HARDWARE. TODO --arms glove (arm IK from the Coil wrist pose, g1/arm_ik.py): not wired here on purpose."""
import argparse, json, os, re, socket, subprocess, sys, threading, time
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
REPO = os.environ.get("AALTO_REPO", r"C:\Users\giorg\Desktop\aaltonomous-humanoid")
assert os.path.isdir(REPO), "set AALTO_REPO to the aaltonomous-humanoid clone"; sys.path.insert(0, REPO)
from aaltonomous.deploy.policy_server import Policy, serve
from robot.g1_dex3 import G1Dex3Retargeter

CHUNK = 3            # same as g1/glove_policy.py: >= 27 Hz command rate, no hold ticks
SPEED_MARGIN = 0.7   # 70 % of the 3.0 rad/s hand cap (rehearsal found clips at 100 %)
LIVE = os.path.join(ROOT, "data", "live")
# Giorgio's requested behaviour (14/11). g1/object_profiles.json is NOT edited here: its ball (0.60) / can (unsupported) entries predate
# today's decision, so this table wins for stress_ball / can_empty; egg and unknown follow the sim + Tommaso's conservative rule.
PROFILE = {"egg": {"cap": 0.70, "g_ref": 0.29}, "stress_ball": {"cap": 1.0, "g_ref": 0.36}, "can_empty": {"cap": 1.0, "g_ref": 0.52},
           "can": {"cap": 1.0, "g_ref": 0.52}, "none": {"cap": 0.68, "g_ref": 0.30}}
UNKNOWN = "none"


def load_caps():
    """egg cap from g1/object_profiles.json if present (the sim number owner is g1/); others from PROFILE (see note above)."""
    p = {k: dict(v) for k, v in PROFILE.items()}
    try:
        j = json.load(open(os.path.join(ROOT, "g1", "object_profiles.json")))
        if "egg" in j and j["egg"].get("max_closure"): p["egg"]["cap"] = float(j["egg"]["max_closure"])
    except Exception: pass
    return p


def to_key(res):
    """Picker result -> our object key. Profile 'egg' (incl. the 'ball with low confidence -> egg' safety rule) always wins;
    fallback / 'cup' / anything unclear -> UNKNOWN (conservative)."""
    if not res or res.get("source") == "fallback": return UNKNOWN
    prof, obj = str(res.get("profile", "")), str(res.get("object", "")).lower()
    if prof == "egg" or re.search(r"\begg|uovo", obj): return "egg"
    if prof == "cup": return UNKNOWN
    if re.search(r"ball|sphere|pallina|stress", obj): return "stress_ball"
    if re.search(r"\bcan\b|lattina|tin|soda|drink", obj): return "can_empty"   # the demo can is EMPTY (crushable, strong grip wanted)
    return UNKNOWN


class LivePolicy(Policy):
    name = "live-g1-vision-glove"; action_horizon = CHUNK

    def __init__(self, source, hand="right", force_obj=None):
        self.src, self.hand, self.force = source, hand, force_obj
        self.caps = load_caps(); self.sock = None; self.ep = None; self.i = 0; self.last = None
        if source.startswith("udp:"):
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.sock.bind(("0.0.0.0", int(source[4:]))); self.sock.setblocking(False)
        else:
            tk = int(source.split(":")[1]); z = np.load(os.path.join(ROOT, f"data/episodes/take_{tk:02d}.npz"), allow_pickle=True)
            self.ep = z[f"{hand}_fingers01"]
        os.makedirs(LIVE, exist_ok=True); self.log = open(os.path.join(LIVE, "live_log.jsonl"), "a")
        self.obj = force_obj or UNKNOWN; self.pick = {"source": "manual"} if force_obj else None; self.asked = bool(force_obj); self.t0 = time.time()

    def reset(self, instruction, task=None, seed=None):
        self.home = None; self.r = None; self.i = 0; self.t0 = time.time()

    # ---- object recognition (once, background) ----
    def _ask(self, rgb):
        try:
            import cv2
            path = os.path.join(LIVE, f"head_{int(time.time())}.jpg"); cv2.imwrite(path, np.asarray(rgb)[:, :, ::-1])
            out = subprocess.run([sys.executable, "-m", "ai.pick_profile", "--image", path], cwd=ROOT, capture_output=True, text=True, timeout=60)
            line = next((l for l in reversed(out.stdout.splitlines()) if l.strip().startswith("{")), None)
            res = json.loads(line) if line else {"source": "fallback", "error": (out.stderr or "no output")[-300:]}
        except Exception as e:
            res = {"source": "fallback", "error": f"{type(e).__name__}: {e}"}
        res["image"] = locals().get("path"); self.pick = res; self.obj = to_key(res)
        print(f"[live] picker -> {res.get('object')} / {res.get('profile')} ({res.get('source')}) => profile {self.obj} cap {self.caps[self.obj]['cap']}", flush=True)

    def _fingers(self):
        if self.ep is not None:
            f = self.ep[self.i % len(self.ep)].tolist(); self.i += 1; return f
        try:
            while True:
                d = json.loads(self.sock.recv(65536).decode())
                if self.hand in d and d[self.hand] is not None: self.last = d[self.hand]
                elif "fingers" in d and d.get("hand", "right") == self.hand: self.last = d["fingers"]
        except BlockingIOError: pass
        return self.last

    def act(self, obs):
        arm = np.array(obs["arm_q"], float); hand = np.array(obs["hand_q"], float)
        if not self.asked:
            rgb = obs.get("head_rgb")
            if rgb is not None and np.asarray(rgb).any():
                self.asked = True; threading.Thread(target=self._ask, args=(np.asarray(rgb).copy(),), daemon=True).start()
        if self.home is None: self.home = arm.copy()                     # arms: hold the first measured pose
        if self.r is None:
            self.r = G1Dex3Retargeter()                                    # max_closure from env G1_MAX_CLOSURE (0.1 first real run)
            self.r.q = [min(max(float(v), j["filter"][0]), j["filter"][1]) for v, j in zip(hand, self.r.joints)]
            self.r.max_step *= SPEED_MARGIN
        p = self.caps[self.obj]; qs = []
        for _ in range(CHUNK):
            f = self._fingers()
            if f is None: g = c = 0.0; cmd = None                            # no glove yet: hold open
            else:
                g = float(np.mean([f[1], f[2]])); c = p["cap"] * float(np.clip(g / p["g_ref"], 0.0, 1.0)); cmd = [c, c, c, 0.0, 0.0]
            qs.append(self.r.step(**{self.hand: cmd}))
        self.log.write(json.dumps({"t": round(time.time() - self.t0, 3), "object": self.obj, "pick": self.pick and {k: self.pick.get(k) for k in ("object", "profile", "source", "confidence")},
                                   "g": round(g, 3), "c": round(c, 3), "cap": p["cap"], "g1_max_closure": self.r.max_closure, "hand_q": [round(x, 4) for x in qs[-1]]}) + "\n"); self.log.flush()
        return {"arm_q_target": np.tile(self.home, (CHUNK, 1)), "hand_q_target": np.array(qs)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--source", default="udp:14043"); ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--hand", default="right", choices=["left", "right"]); ap.add_argument("--object", choices=list(PROFILE))
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 if the organisers' runner runs on ANOTHER machine (ws://<this PC IP>:8000)")
    a = ap.parse_args()
    serve(LivePolicy(a.source, a.hand, a.object), port=a.port, host=a.host)
