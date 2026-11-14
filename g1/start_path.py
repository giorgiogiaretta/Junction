"""Start-up path from the robot's REAL rest pose to a working pose, accepted by the organisers' runner filter.

Why: the runner rejects any arm step that increases the penetration of the wrist/palm frames into its counter keep-out
(pelvis frame x 0.14..1.2, z < 0.03). On 14/11 night the robot was physically raised: at rest the hands are BELOW the
counter height and at its front edge (wrist x 0.11, palm x 0.15, z -0.03). Rotating the shoulder forward pushes them deeper
-> step fraction 0 -> the arms never rose. Fix: per arm, a shortest path on a (shoulder pitch, elbow) grid from the rest
pose to the goal, where a move is allowed only if the penetration never rises above the current one (the exact runner
rule, tolerance 1e-4). Typically: hand back, then up (elbow), then forward. Arms are planned and moved one after the other
(the other arm still), so each arm's path is valid on its own.
"""
import heapq
import numpy as np

SP = {"left": 0, "right": 7}     # shoulder pitch index; elbow = +3
STEP = 0.04                      # rad, grid resolution


def _ok(WS, a, b, n=6):
    prev_v = max(WS.violation(a), 1e-4)
    for s in np.linspace(0, 1, n + 1)[1:]:
        v = WS.violation(a + s * (b - a))
        if v > prev_v + 1e-9: return False
        prev_v = max(v, 1e-4)
    return True


def plan_arm(WS, q0, goal, side, lo, hi):
    """Waypoints (14-vectors) moving only this arm's shoulder pitch + elbow from q0 to goal's values (other joints: goal's)."""
    i, e = SP[side], SP[side] + 3
    base = q0.copy(); base[SP[side]:SP[side] + 7] = goal[SP[side]:SP[side] + 7]   # wrist/roll/yaw joints of this arm: goal values
    if not _ok(WS, q0, base): base = q0.copy()                                     # (keep the start ones if that would clip)
    def q_of(s, el): q = base.copy(); q[i], q[e] = s, el; return q
    s_lo, s_hi = min(q0[i], goal[i]) - 0.6, max(q0[i], goal[i]) + 0.6
    e_lo, e_hi = min(q0[e], goal[e]) - 0.8, max(q0[e], goal[e]) + 0.8
    s_rng = np.arange(max(lo[i], s_lo), min(hi[i], s_hi) + 1e-9, STEP)
    e_rng = np.arange(max(lo[e], e_lo), min(hi[e], e_hi) + 1e-9, STEP)
    snap = lambda v, r: int(np.argmin(np.abs(r - v)))
    start = (snap(base[i], s_rng), snap(base[e], e_rng)); tgt = (snap(goal[i], s_rng), snap(goal[e], e_rng))
    dist = {start: 0.0}; prev = {}; pq = [(0.0, start)]; qs = {}; vs = {}
    def V(n):
        if n not in qs: qs[n] = q_of(s_rng[n[0]], e_rng[n[1]])
        return qs[n]
    def Vv(n):
        if n not in vs: vs[n] = WS.violation(V(n))
        return vs[n]
    h = lambda n: np.hypot(n[0] - tgt[0], n[1] - tgt[1])          # A*: straight-line grid distance
    while pq:
        f, n = heapq.heappop(pq); d = dist[n]
        if n == tgt: break
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                if not di and not dj: continue
                m = (n[0] + di, n[1] + dj)
                if not (0 <= m[0] < len(s_rng) and 0 <= m[1] < len(e_rng)): continue
                allowed = max(Vv(n), 1e-4) + 1e-9
                if Vv(m) > allowed or any(WS.violation(V(n) + f * (V(m) - V(n))) > allowed for f in (0.25, 0.5, 0.75)): continue
                nd = d + np.hypot(di, dj)
                if nd < dist.get(m, 1e9): dist[m] = nd; prev[m] = n; heapq.heappush(pq, (nd + h(m), m))
    if tgt not in dist: return None
    path = [tgt]
    while path[-1] != start: path.append(prev[path[-1]])
    path = path[::-1]
    pts = [q0.copy()] + [V(n) for n in path[1:]]
    pts[-1] = q_of(goal[i], goal[e]) if _ok(WS, pts[-1], q_of(goal[i], goal[e])) else pts[-1]
    keep = [pts[0]]                                          # drop collinear points (fewer, longer segments)
    for k in range(1, len(pts) - 1):
        a, b, c = keep[-1], pts[k], pts[k + 1]
        if not _ok(WS, a, c, 24): keep.append(b)
    keep.append(pts[-1])
    return keep[1:]


def plan(WS, rest, goal, lo, hi):
    """Waypoints from rest to goal: direct if the runner rule allows it, else left arm then right arm on their own grids."""
    rest, goal = np.asarray(rest, float), np.asarray(goal, float)
    if _ok(WS, rest, goal, 40): return [goal]
    wps, q = [], rest.copy()
    for side in ("left", "right"):
        p = plan_arm(WS, q, goal, side, lo, hi)
        if p is None: return None
        wps += p; q = p[-1].copy()
    if not np.allclose(q, goal, atol=1e-3):
        if _ok(WS, q, goal, 40): wps.append(goal)
        else: return None
    return wps
