"""Aaltonomous policy server that drives the G1 Dex3 HANDS from a glove stream and holds the ARMS (hardware-test bridge).
Runs through the organisers' runner + safety filter (mock backend here: no GPU/Isaac needed), so the exact path used on the real robot is rehearsed.
  AALTO_REPO=<clone of zupermiez/aaltonomous-humanoid> python g1/glove_policy.py --source replay:51 [--port 8000]
  python -m aaltonomous.deploy.runner --backend mock --policy ws://localhost:8000 --team giorgio --episodes 1     (run inside AALTO_REPO)
Sources: replay:<take> (data/episodes/take_NN.npz fingers01, L+R, looped) | udp:<port> (live hand_state JSON 'left'/'right' or 'fingers'+'hand').
Safety: arms = the first measured arm_q (never moved); hands start from the MEASURED hand_q (no jump), then Dex3 retarget clamped to the filter bounds and slew-limited."""
import argparse, json, os, socket, sys, time
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
REPO = os.environ.get("AALTO_REPO"); assert REPO and os.path.isdir(REPO), "set AALTO_REPO to the aaltonomous-humanoid clone"; sys.path.insert(0, REPO)
from aaltonomous.deploy.policy_server import Policy, serve
from robot.g1_dex3 import G1Dex3Retargeter


CHUNK = 3            # targets per policy call: fewer calls/s -> no hold ticks, command rate stays >= 27 Hz
SPEED_MARGIN = 0.7   # use 70 % of the 3.0 rad/s hand cap: real-time jitter made 100 % clip (rehearsal found 3 clipped steps)


class GlovePolicy(Policy):
    name = "glove-dex3"; action_horizon = CHUNK

    def __init__(self, source):
        self.src = source; self.sock = None; self.ep = None; self.i = 0
        if source.startswith("udp:"):
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.sock.bind(("0.0.0.0", int(source[4:]))); self.sock.setblocking(False)
        else:
            tk = int(source.split(":")[1]); z = np.load(os.path.join(ROOT, f"data/episodes/take_{tk:02d}.npz"), allow_pickle=True)
            self.ep = {h: z[f"{h}_fingers01"] for h in ("left", "right") if f"{h}_fingers01" in z.files}
        self.last = {"left": None, "right": None}

    def reset(self, instruction, task=None, seed=None):
        self.home = None; self.r = None; self.i = 0

    def _fingers(self):
        if self.ep is not None:
            n = min(len(v) for v in self.ep.values()); k = self.i % n; self.i += 1
            return {h: v[k].tolist() for h, v in self.ep.items()}
        try:
            while True:
                d = json.loads(self.sock.recv(65536).decode())
                if "left" in d or "right" in d: self.last.update({"left": d.get("left"), "right": d.get("right")})
                elif "fingers" in d: self.last[d.get("hand", "right")] = d["fingers"]
        except BlockingIOError: pass
        return self.last

    def act(self, obs):
        arm = np.array(obs["arm_q"], float); hand = np.array(obs["hand_q"], float)
        if self.home is None: self.home = arm.copy()                       # arms: hold the first measured pose forever
        if self.r is None:
            self.r = G1Dex3Retargeter()
            self.r.q = [min(max(float(v), j["filter"][0]), j["filter"][1]) for v, j in zip(hand, self.r.joints)]   # start from the measured hands
            self.r.max_step *= SPEED_MARGIN
        qs = []
        for _ in range(CHUNK):
            f = self._fingers(); qs.append(self.r.step(left=f.get("left"), right=f.get("right")))
        return {"arm_q_target": np.tile(self.home, (CHUNK, 1)), "hand_q_target": np.array(qs)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--source", default="replay:51"); ap.add_argument("--port", type=int, default=8000); a = ap.parse_args()
    serve(GlovePolicy(a.source), port=a.port, host="127.0.0.1")
