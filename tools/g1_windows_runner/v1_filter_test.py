"""V1 vision policy from the REAL G1 rest pose, simulated camera frames, fake gloves, through the organisers' SafetyFilter."""
import sys, os, json, socket, time, threading, collections
import numpy as np
os.chdir(r"C:\Users\giorg\Desktop\Junction"); sys.path[:0] = [r"C:\Users\giorg\Desktop\Junction\g1", r"C:\Users\giorg\Desktop\Junction"]
sys.argv = ["x"]
import live_policy_v1 as L
from aaltonomous.interface import safety as AS
arm0 = np.array([-0.2244, -0.0975, -0.0983, 1.0749, -0.0929, -1.0633, 0.0657, -0.1542, -0.0803, -0.3242, 0.6424, 0.009, -0.6977, 0.269])
hand0 = np.array([-0.029, 0.914, 1.63, -1.575, -1.715, -1.579, -1.7, 0.391, -0.008, -1.448, 1.55, 1.708, 1.458, 1.717])
PORT = 14098
p = L.LivePolicy(f"udp:{PORT}", "stress_ball", "can_empty", (0.35, -0.15), (0.35, 0.15), vlm=[], dry=False, xy_gate=0.08,
                 test_frames=r"data\g1sim\v1_frames.npz", engine="ai")
p.reset("x")
f = AS.SafetyFilter(AS.JointSpec()); f.reset(arm0, hand0, 0.0)
out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sched = [(0, 0.0)] + [(10 + 12 * k, 0.9) for k in range(4)] + [(17 + 12 * k, 0.0) for k in range(4)]
t0 = time.time()
def glove():
    while time.time() - t0 < 70:
        t = time.time() - t0; g = [v for s, v in sorted(sched) if s <= t][-1]
        out.sendto(json.dumps({"left": [g] * 5, "right": [g] * 5}).encode(), ("127.0.0.1", PORT)); time.sleep(0.02)
threading.Thread(target=glove, daemon=True).start()
H, W = 480, 640
obs = {"arm_q": arm0.copy(), "hand_q": hand0.copy(), "head_rgb": np.zeros((H, W, 3), np.uint8), "head_depth": np.zeros((H, W), np.uint16)}
clipped = 0; tt = 0.0; reasons = collections.Counter()
while time.time() - t0 < 60:
    r = p.act(obs)
    for a, h in zip(r["arm_q_target"], r["hand_q_target"]):
        res = f.filter({"arm_q_target": a, "hand_q_target": h}, tt, obs["arm_q"], obs["hand_q"]); tt += 1 / 30
        if res.clipped: clipped += 1; reasons.update(res.reasons)
        obs["arm_q"] = res.arm_q_cmd.copy(); obs["hand_q"] = res.hand_q_cmd.copy(); time.sleep(1 / 30)
    if f.mode == "aborted" or p.abort: break
recs = [json.loads(l) for l in open("data/live/live_policy_v1.jsonl", encoding="utf-8")]
s = max(i for i, x in enumerate(recs) if x.get("event") == "START"); recs = recs[s:]
print("filter clipped", clipped, dict(reasons), "mode", f.mode, "policy abort", p.abort)
for x in recs:
    if x.get("event") in ("PERCEPTION", "POSE", "ABORT"): print({k: v for k, v in x.items() if k in ("event", "hand", "object", "position", "source", "error", "objects", "reasons")})
print("states", collections.Counter(json.dumps(x["state"]) for x in recs if isinstance(x.get("state"), dict)).most_common(8))
print("our blocks", collections.Counter(tuple(x.get("reasons", [])) for x in recs if x.get("reasons")).most_common(5))

