"""V2 (Coil) robot policy from the REAL G1 rest pose (14/11), recorded Coil+glove take, through the organisers' SafetyFilter (offline)."""
import sys, os, json, time, collections
import numpy as np
J = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); os.chdir(J); sys.path[:0] = [os.path.join(J, "g1"), J]   # this checkout (was hard-coded to the main one)
sys.argv = ["x"]
import live_policy_v2_vision as V2
from aaltonomous.interface import safety as AS
arm0 = np.array([-0.2244, -0.0975, -0.0983, 1.0749, -0.0929, -1.0633, 0.0657, -0.1542, -0.0803, -0.3242, 0.6424, 0.009, -0.6977, 0.269])
hand0 = np.array([-0.029, 0.914, 1.63, -1.575, -1.715, -1.579, -1.7, 0.391, -0.008, -1.448, 1.55, 1.708, 1.458, 1.717])
p = V2.LivePolicyV2("replay:77", {"right": "stress_ball"}, {"right": (0.35, -0.15)})
p.reset("x")
f = AS.SafetyFilter(AS.JointSpec()); f.reset(arm0, hand0, 0.0)
H, W = 480, 640
obs = {"arm_q": arm0.copy(), "hand_q": hand0.copy(), "head_rgb": np.zeros((H, W, 3), np.uint8), "head_depth": np.zeros((H, W), np.uint16)}
clipped = 0; tt = 0.0; reasons = collections.Counter(); t0 = time.time(); start_ticks = None; dts = []
for k in range(int(sys.argv[1]) if len(sys.argv) > 1 else 500):
    ta = time.perf_counter(); r = p.act(obs); dts.append(time.perf_counter() - ta)
    for a, h in zip(r["arm_q_target"], r["hand_q_target"]):
        res = f.filter({"arm_q_target": a, "hand_q_target": h}, tt, obs["arm_q"], obs["hand_q"]); tt += 1 / 30
        if res.clipped: clipped += 1; reasons.update(res.reasons)
        obs["arm_q"] = res.arm_q_cmd.copy(); obs["hand_q"] = res.hand_q_cmd.copy()
    if p.started and start_ticks is None: start_ticks = p.tick
    if f.mode == "aborted": break
recs = [json.loads(l) for l in open("data/live/live_policy_v2_vision.jsonl", encoding="utf-8")][-3 * 500:]
print("filter clipped", clipped, dict(reasons), "mode", f.mode, "| policy abort", p.abort, "blocked", p.blocked)
print("act() ms: mean %.1f p95 %.1f max %.1f (CHUNK %d -> max call rate %.0f Hz of targets)" % (1e3 * np.mean(dts), 1e3 * np.percentile(dts, 95), 1e3 * max(dts), V2.CHUNK, V2.CHUNK / np.mean(dts)))
print("startup done after", start_ticks, "ticks (", None if start_ticks is None else round(start_ticks / 30, 1), "s)")
print("startup phases", collections.Counter(x.get("startup") for x in recs if x.get("startup")))
print("modes", collections.Counter(str(x.get("modes")) for x in recs if x.get("modes")).most_common(6))
print("our reasons", collections.Counter(tuple(x.get("reasons", [])) for x in recs if x.get("reasons")).most_common(4))
