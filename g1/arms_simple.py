"""G1 both arms + both hands from the gloves, NO vision, NO Cartesian IK (joint-space, checked with the organisers' filter code).

Per hand: glove OPEN -> arm UP, fingers open. Glove CLOSED -> arm goes DOWN (toward the object you placed under the hand),
then the fingers close (closure follows the glove, capped). Glove OPEN again -> fingers open first, then the arm goes back UP.
UP / DOWN are built from the robot's measured rest pose by rotating the shoulder pitch forward (+ elbow), so the wrist/palm
leave the organisers' counter keep-out going straight up-forward. Start: rest -> DOWN -> UP slowly.

  $env:G1_MAX_CLOSURE="0.6"; py -3.11 g1/arms_simple.py --source udp:14043 --host 0.0.0.0
"""
import argparse, json, os, socket, sys, time
import numpy as np

AH = os.environ.get("AALTO_REPO", r"C:\Users\giorg\Desktop\aaltonomous-humanoid")
for p in (os.path.join(AH, "winshim"), AH, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
    if p not in sys.path: sys.path.insert(0, p)
from aaltonomous.interface import safety as AS

WS = AS.WorkspaceChecker(AS.JointSpec(), AS.SafetyConfig())
LIM = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "g1_dex3_limits.json")))
ALO = np.array([e["filter"][0] for e in sorted(LIM["arm_q"], key=lambda e: e["idx"])]) + 0.01
AHI = np.array([e["filter"][1] for e in sorted(LIM["arm_q"], key=lambda e: e["idx"])]) - 0.01
RATE, CHUNK = 30.0, 3
ARM_V = 0.45 / RATE           # rad per tick, 45 % of the 1 rad/s filter cap
SP = {"left": 0, "right": 7}  # shoulder_pitch index; elbow = +3
UP_EXTRA = float(os.environ.get("G1_UP_RAD", "0.35"))   # extra shoulder pitch (rad) from DOWN to UP (~10 cm at the hand)
CLEAR = 0.015                 # m: DOWN = first pose with every wrist/palm frame >= 1.5 cm out of the keep-out


def lift(q, side, a):
    """Rotate the arm forward/up: shoulder pitch -a, elbow -0.5a (keeps the forearm roughly level)."""
    q = q.copy(); i = SP[side]; q[i] -= a; q[i + 3] -= 0.5 * a
    return np.clip(q, ALO, AHI)


def keepout_margin(q):
    p = WS.positions(q); lo, hi = WS.ko
    inside = np.all((p > lo - CLEAR) & (p < hi + CLEAR), axis=1)
    return not inside.any()


def build(q_rest):
    """DOWN = smallest lift (per side) with all frames clear of the keep-out by CLEAR; UP = DOWN + UP_EXTRA."""
    down = q_rest.copy()
    for side in ("left", "right"):
        a = 0.0
        while a < 1.2:
            q = lift(down, side, a)
            p = WS.positions(q); lo, hi = WS.ko
            idx = [0, 1] if side == "left" else [2, 3]
            if not np.any(np.all((p[idx] > lo - CLEAR) & (p[idx] < hi + CLEAR), axis=1)): break
            a += 0.01
        down = lift(down, side, a)
    up = lift(lift(down, "left", UP_EXTRA), "right", UP_EXTRA)
    return down, up


class Gloves:
    def __init__(self, port):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); self.s.bind(("127.0.0.1", port)); self.s.setblocking(False)
        self.last = {"left": None, "right": None}

    def read(self):
        try:
            while True:
                d = json.loads(self.s.recv(65536).decode())
                for h in ("left", "right"):
                    if d.get(h) is not None: self.last[h] = d[h]
        except BlockingIOError:
            pass
        return self.last


class ArmsSimple:
    def __init__(self, source):
        self.g = Gloves(int(source.split(":")[1])); self.log = open(os.path.join("data", "live", "arms_simple.jsonl"), "a")
        self.reset()

    def metadata(self):
        return {"name": "g1-arms-simple-gloves", "action_horizon": CHUNK}

    def reset(self, *a, **k):
        self.cmd = None; self.r = None; self.state = {"left": "START", "right": "START"}; self.alpha = {"left": 0.0, "right": 0.0}
        self.t0 = time.time(); self.startup = 0.0

    def _step_toward(self, cur, tgt):
        d = tgt - cur; m = np.abs(d).max()
        return tgt.copy() if m <= ARM_V else cur + d * (ARM_V / m)

    def _safe(self, new):
        """Same rule as the runner filter: never more keep-out penetration than the last command (bisect)."""
        allowed = max(WS.violation(self.cmd), 1e-4) - 1e-6
        if WS.violation(new) <= allowed: return new
        lo, hi, st = 0.0, 1.0, new - self.cmd
        for _ in range(12):
            mid = .5 * (lo + hi)
            if WS.violation(self.cmd + mid * st) <= allowed: lo = mid
            else: hi = mid
        return self.cmd + lo * st

    def act(self, obs):
        from robot.g1_dex3 import G1Dex3Retargeter
        arm = np.asarray(obs["arm_q"], float); hand = np.asarray(obs["hand_q"], float)
        if self.cmd is None:
            self.cmd = np.clip(arm, ALO, AHI); self.rest = self.cmd.copy(); self.down, self.up = build(self.rest)
            self.log.write(json.dumps({"event": "START", "rest": self.rest.round(4).tolist(), "down": self.down.round(4).tolist(),
                                       "up": self.up.round(4).tolist(), "viol_rest": WS.violation(self.rest), "viol_down": WS.violation(self.down)}) + "\n")
        if self.r is None:
            self.r = G1Dex3Retargeter(); self.r.q = [min(max(float(v), j["filter"][0]), j["filter"][1]) for v, j in zip(hand, self.r.joints)]
            self.r.max_step *= 0.7
        arms, hands = [], []
        for _ in range(CHUNK):
            f = self.g.read(); fingers = {}
            tgt = self.cmd.copy()
            for side in ("left", "right"):
                sl = slice(SP[side], SP[side] + 7); gl = f[side]; g = 0.0 if gl is None else float(np.mean([gl[1], gl[2]]))
                st = self.state[side]
                if st == "START":           # rest -> DOWN -> UP, glove ignored
                    goal = self.down if self.startup < 1 else self.up
                    tgt[sl] = goal[sl]
                    if np.abs(self.cmd[sl] - goal[sl]).max() < 1e-3:
                        if self.startup < 1 and np.abs(self.cmd - self.down).max() < 1e-3: self.startup = 1
                        elif self.startup >= 1: self.state[side] = "UP"
                    c = 0.0
                else:
                    closed, opened = g > 0.45, g < 0.25
                    if st == "UP" and closed: st = "DOWN"
                    elif st == "DOWN" and opened: st = "UP"
                    elif st == "DOWN" and np.abs(self.cmd[sl] - self.down[sl]).max() < 1e-3: st = "GRASP"
                    elif st == "GRASP" and opened: st = "RELEASE"; self.t_rel = time.time()
                    elif st == "RELEASE" and time.time() - self.t_rel > 0.8: st = "UP"
                    self.state[side] = st
                    tgt[sl] = (self.down if st in ("DOWN", "GRASP", "RELEASE") else self.up)[sl]
                    c = float(np.clip(g / 0.6, 0, 1)) if st == "GRASP" else 0.0
                fingers[side] = [c, c, c, 0.0, 0.0]
            new = self._safe(self._step_toward(self.cmd, tgt)); self.cmd = new
            arms.append(new.copy()); hands.append(np.asarray(self.r.step(left=fingers["left"], right=fingers["right"]), float))
        self.log.write(json.dumps({"t": round(time.time() - self.t0, 2), "state": dict(self.state), "viol": round(WS.violation(self.cmd), 4),
                                   "fingers": {k: v[0] for k, v in fingers.items()}}) + "\n"); self.log.flush()
        return {"arm_q_target": np.array(arms), "hand_q_target": np.array(hands)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--source", default="udp:14043"); ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1"); a = ap.parse_args()
    from aaltonomous.deploy.policy_server import Policy, serve
    serve(type("ArmsSimpleServed", (ArmsSimple, Policy), {})(a.source), port=a.port, host=a.host)
