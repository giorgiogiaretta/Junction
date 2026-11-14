"""Policy for the ONE live G1 test: the robot's head camera recognises the object, the glove drives the Dex3 hand, the object decides
how far the robot hand closes. Arms HOLD the measured pose (safest). Runs behind the organisers' runner + safety filter.
  py -3.11 g1/live_policy.py --source udp:14043 [--object egg|stress_ball|can|none] [--hand right] [--port 8000]
  py -3.11 g1/live_policy.py --source replay:77            (rehearsal with a recorded take, right_fingers01)
  cd <aaltonomous clone>; py -3.11 -m aaltonomous.deploy.runner --backend mock --policy ws://localhost:8000 --team giorgio --episodes 1
Env: AALTO_REPO (default C:/Users/giorg/Desktop/aaltonomous-humanoid), G1_MAX_CLOSURE (retargeter scale, 0.1 on the first real run).
Object recognition: on the first non-black obs["head_rgb"] the frame is saved to data/live/head_<t>.jpg and `python -m ai.pick_profile
--image <jpg>` (Tommaso's picker: Nemotron, Gemini backup, safety rules that only soften) runs ONCE in a background thread. Until it
answers, on failure, or on an unclear answer the CONSERVATIVE cap (unknown, 0.68) is used. --object = operator sets the object
(source=manual), which is the ONLY way a model-free run unlocks full force for the ball.
CAP: single source of truth is ai.object_profile.cap_for() (owner: ai/, reads g1/object_profiles.json): ball 1.0 only when
operator-set or >=2 recognisers agree (pick['agree']; ai.pick_profile is ONE model, so never here); can never full force while
vision-only; egg / ball-unconfirmed share the robust cap (0.70); unknown 0.68. No local cap table here.
GRIP: g = mean(index, middle) fingers01 of the operating hand; robot closure c = cap * clip(g / g_ref, 0, 1); [thumb=c, index=c,
middle=c] -> G1Dex3Retargeter. g_ref = the operator's typical grip on that object (data of 14/11, takes 75-89), so their usual grip
becomes the object's cap. Every tick is logged to data/live/live_log.jsonl.
SCALE RISK: g_ref values come from the episodes (fingers01 normalised with data/calib.json, series E). Live fingers come from
Rokoko/src/rgmp_client.py, normalised by its own 8 s open/close sweep: do a FULL open hand + FULL fist during that sweep so the two scales match.
UNTESTED ON HARDWARE. TODO --arms glove (arm IK from the Coil wrist pose, g1/arm_ik.py): not wired here on purpose."""
import argparse, json, os, socket, subprocess, sys, threading, time
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
from ai.object_profile import cap_for

CHUNK = 3            # same as g1/glove_policy.py: >= 27 Hz command rate, no hold ticks
SPEED_MARGIN = 0.7   # 70 % of the 3.0 rad/s hand cap (rehearsal found clips at 100 %)
LIVE = os.path.join(ROOT, "data", "live")
G_REF = {"egg": 0.29, "stress_ball": 0.36, "can": 0.52, "other": 0.30}   # operator's typical grip per object (episodes 75-89)
OBJECTS = ("egg", "stress_ball", "can", "none")
FALLBACK = {"source": "fallback"}


def cap(pick):
    """{'object','max_closure','why'} from ai.object_profile.cap_for. Accepts both cap_for signatures seen on main (dict pick, or
    label/confidence/agree/manual) so a refactor of ai/ does not silently break the live run; any error -> conservative fallback."""
    try:
        r = cap_for(pick)
        if isinstance(r, dict): return r
    except TypeError: pass
    try:
        manual = pick.get("source") == "manual"
        label = (pick.get("object_key") or pick.get("profile")) if manual else pick.get("object")
        from ai.object_profile import normalize
        c = cap_for(label, confidence=pick.get("confidence"), agree=int(pick.get("agree", 1)), manual=manual)
        return {"object": normalize(label), "max_closure": float(c), "why": "cap_for(label, ...)"}
    except Exception as e:
        return {"object": "other", "max_closure": 0.68, "why": f"cap_for failed ({type(e).__name__}): conservative"}


class LivePolicy:
    name = "live-g1-vision-glove"; action_horizon = CHUNK

    def __init__(self, source, hand="right", force_obj=None):
        self.src, self.hand = source, hand; self.sock = None; self.ep = None; self.i = 0; self.last = None; self.r = None; self.home = None
        if source.startswith("udp:"):
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.sock.bind(("0.0.0.0", int(source[4:]))); self.sock.setblocking(False)
        else:
            tk = int(source.split(":")[1]); z = np.load(os.path.join(ROOT, f"data/episodes/take_{tk:02d}.npz"), allow_pickle=True)
            self.ep = z[f"{hand}_fingers01"]
        os.makedirs(LIVE, exist_ok=True); self.log = open(os.path.join(LIVE, "live_log.jsonl"), "a")
        self.pick = {"source": "manual", "object_key": force_obj} if force_obj else FALLBACK
        self.prof = cap(self.pick); self.asked = bool(force_obj); self.t0 = time.time()
        print(f"[live] start: {self.prof}", flush=True)

    def reset(self, instruction, task=None, seed=None):
        self.home = None; self.r = None; self.i = 0; self.t0 = time.time()

    # ---- object recognition (once, background) ----
    def _ask(self, rgb):
        path = None
        try:
            import cv2
            path = os.path.join(LIVE, f"head_{int(time.time())}.jpg"); cv2.imwrite(path, np.asarray(rgb)[:, :, ::-1])
            out = subprocess.run([sys.executable, "-m", "ai.pick_profile", "--image", path], cwd=ROOT, capture_output=True, text=True, timeout=60)
            line = next((l for l in reversed(out.stdout.splitlines()) if l.strip().startswith("{")), None)
            res = json.loads(line) if line else {"source": "fallback", "error": (out.stderr or "no output")[-300:]}
        except Exception as e:
            res = {"source": "fallback", "error": f"{type(e).__name__}: {e}"}
        res["image"] = path; self.pick = res; self.prof = cap(res)
        print(f"[live] picker -> {res.get('object')} ({res.get('source')}, conf {res.get('confidence')}) => {self.prof}", flush=True)

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
        from robot.g1_dex3 import G1Dex3Retargeter
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
        p = self.prof; top = float(p["max_closure"]); g_ref = G_REF.get(p["object"], G_REF["other"]); qs = []; g = c = 0.0
        for _ in range(CHUNK):
            f = self._fingers()
            if f is None: g = c = 0.0; cmd = None                            # no glove yet: hold open
            else:
                g = float(np.mean([f[1], f[2]])); c = top * float(np.clip(g / g_ref, 0.0, 1.0)); cmd = [c, c, c, 0.0, 0.0]
            qs.append(self.r.step(**{self.hand: cmd}))
        self.log.write(json.dumps({"t": round(time.time() - self.t0, 3), "object": p["object"], "why": p["why"],
                                   "pick": {k: self.pick.get(k) for k in ("object", "object_key", "profile", "source", "confidence")},
                                   "g": round(g, 3), "c": round(c, 3), "cap": top, "g1_max_closure": self.r.max_closure, "hand_q": [round(x, 4) for x in qs[-1]]}) + "\n"); self.log.flush()
        return {"arm_q_target": np.tile(self.home, (CHUNK, 1)), "hand_q_target": np.array(qs)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--source", default="udp:14043"); ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--hand", default="right", choices=["left", "right"]); ap.add_argument("--object", choices=OBJECTS)
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 if the organisers' runner runs on ANOTHER machine (ws://<this PC IP>:8000)")
    a = ap.parse_args()
    REPO = os.environ.get("AALTO_REPO", r"C:\Users\giorg\Desktop\aaltonomous-humanoid")
    assert os.path.isdir(REPO), "set AALTO_REPO to the aaltonomous-humanoid clone"; sys.path.insert(0, REPO)
    from aaltonomous.deploy.policy_server import Policy, serve
    serve(type("LivePolicyServed", (LivePolicy, Policy), {})(a.source, a.hand, a.object), port=a.port, host=a.host)
