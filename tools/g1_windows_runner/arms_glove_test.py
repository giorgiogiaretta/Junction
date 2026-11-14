import sys, os, json, socket, time, threading
import numpy as np
os.chdir(r"C:\Users\giorg\Desktop\Junction"); sys.path.insert(0, r"C:\Users\giorg\Desktop\Junction\g1")
import arms_glove as A
from aaltonomous.interface import safety as AS
arm0 = np.array([-0.2244, -0.0975, -0.0983, 1.0749, -0.0929, -1.0633, 0.0657, -0.1542, -0.0803, -0.3242, 0.6424, 0.009, -0.6977, 0.269])
hand0 = np.array([-0.029, 0.914, 1.63, -1.575, -1.715, -1.579, -1.7, 0.391, -0.008, -1.448, 1.55, 1.708, 1.458, 1.717])
PORT = 14099
p = A.ArmsGlove(f"udp:{PORT}", viz=len(sys.argv) > 1)
f = AS.SafetyFilter(AS.JointSpec()); f.reset(arm0, hand0, 0.0)
# fake gloves: open 6 s, close 6 s, open 5 s ... both hands
out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sched = [(0, 0.0)] + [(6 + 11 * k, 0.9) for k in range(4)] + [(12 + 11 * k, 0.0) for k in range(4)]
t0 = time.time()
def glove():
    while time.time() - t0 < 60:
        t = time.time() - t0; g = [v for s, v in sorted(sched) if s <= t][-1]
        out.sendto(json.dumps({"left": [g] * 5, "right": [g] * 5}).encode(), ("127.0.0.1", PORT)); time.sleep(0.02)
threading.Thread(target=glove, daemon=True).start()
obs = {"arm_q": arm0.copy(), "hand_q": hand0.copy()}
k = 0; trace = []; states = set(); clipped = 0; tt = 0.0
print("down", p is not None)
while time.time() - t0 < 50:
    r = p.act(obs)
    for a, h in zip(r["arm_q_target"], r["hand_q_target"]):
        res = f.filter({"arm_q_target": a, "hand_q_target": h}, tt, obs["arm_q"], obs["hand_q"]); tt += 1 / 30
        if res.clipped: clipped += 1; print("CLIP", tt, res.reasons) if clipped < 6 else None
        obs["arm_q"] = res.arm_q_cmd.copy(); obs["hand_q"] = res.hand_q_cmd.copy()
        time.sleep(1 / 30)
    states.add(json.dumps(p.state)); trace.append((time.time() - t0, json.dumps(p.state), float(np.abs(p.vel).max())))
print("clipped", clipped, "mode", f.mode); print(sorted(states))
print("down-rest", np.round(p.down - p.rest, 3)); print("up-rest", np.round(p.up - p.rest, 3))
for nm, q in (("rest", p.rest), ("down", p.down), ("up", p.up)):
    print(nm, "wrist/palm pelvis z", np.round(A.WS.positions(q)[:, 2], 3), "x", np.round(A.WS.positions(q)[:, 0], 3))



prev=None
for tt_, st, v in trace:
    if st != prev: print(round(tt_, 2), st, round(v, 2)); prev = st
print('max joint speed rad/s', round(max(v for _, _, v in trace), 3))

