"""Coil + glove -> G1 arm chain shared by the simulator (g1/sim/teleop_multi.py) and the live policy (g1/live_policy_v2.py).

Seated-beside setup: the operator sits next to the robot, facing the same way, both gloves FLAT on the table at the start.
  hand flat + still on the table  ==  robot hand in its REST pose over the counter (no first-tick jump, A7)
  sliding the hand forward on the table  ->  the robot hand moves toward its object and DESCENDS to grasp height
  (a virtual sloped table: the operator cannot reach below his own table, the robot must reach below its rest height)
  lifting the hand  ->  the robot hand lifts.
Every time a hand rests still on the table for 1 s the anchor is re-taken (Coil drift removed), blended in over 1 s.

Fixes of docs/G1_TEST_PLAN.md section A (new chain; Cfg.legacy() reproduces the old teleop_multi behaviour for before/after numbers):
  A1 filters: One Euro 2.5 Hz + speed-adaptive beta (lag < 80 ms), grip filter 50 ms     (old: 0.7 Hz ~230 ms, grip 150 ms)
  A2 joint-space speed limit 0.7 rad/s with the step SCALED, not clipped per joint        (old: per-joint clip at 1 rad/s)
  A3 assist weight ramps continuously to the grasp pose (rate-limited); snap needs 2 ticks (old: 3 cm assist vs 4 cm snap = jump)
  A4 null-space rest posture fades in/out over 0.5 s                                     (old: switched on/off)
  A5 one object per hand, fixed                                                          (old: nearest object every tick)
  A6 deadband on the RAW signal, as a continuous 1.5 mm leash                            (old: 3 mm hold after the filter)
  A7 start = rest pose, operator's flat hand = neutral orientation                       (old: grasp orientation + anchor at the grasp)
  A8 automatic raise only for the counter keep-out block                                 (old: raise on any block)
Plus a final Cartesian target rate limiter so that no state change can make the target jump."""
import numpy as np, mujoco

import arm_ik

RATE = 30.0
WRIST_MAX_DEG = 70.0
# Calibration of the 14/11 session (take 64): rows = forward, left, up in Coil coordinates. Used to replay the recorded takes.
TAKE64_R = np.array([[0.91964, -0.08849, 0.38266], [-0.06991, -0.99561, -0.06222], [0.38648, 0.03047, -0.92179]])


class Cfg:
    def __init__(self, **kw):
        self.legacy = False
        # 14/11 evening (operator: "smooth is fine, too much delay"): faster filters + higher limits. Cfg.slow() = previous values.
        self.pos_cutoff, self.pos_beta = 5.0, 60.0       # One Euro: Hz, Hz per m/s   (was 2.5, 40; 4.0)
        self.lead = float(__import__("os").environ.get("G1_LEAD", "0.0"))   # s of motion prediction (14/11 night, robot delay)
        self.rot_cutoff, self.rot_beta = 4.0, 3.0        # Hz, Hz per rad/s           (was 2.5, 2)
        self.leash = 0.0015                              # m, raw-signal deadband (continuous)
        self.post_deadband = 0.0                         # m, legacy hold-deadband after the filter
        self.grip_tau = 0.04
        self.joint_speed = 0.92                          # rad/s (runner cap 1.0)    (was 0.7; 0.85 first evening step)
        self.uniform_step = True
        self.vmax = 0.75                                 # m/s, raw teleop target speed limit   (was 0.35; 0.60)
        self.vfinal, self.wfinal = 0.70, np.radians(260)  # final target limiter (m/s, rad/s)  (was 0.30, 150; 0.55, 220)
        self.assist_r, self.snap_xy, self.snap_z, self.snap_deg, self.snap_ticks = 0.06, 0.04, 0.05, 60.0, 2
        self.w_rate = 1 / 0.4                            # assist weight change per second
        self.ns_fade = 0.5                               # s, null-space fade
        self.fixed_target = True
        self.raise_only_counter = True
        self.zoff = 0.04                                 # m: operator wrist height above the flat-hand height when grasping
        self.gain = 1.0
        self.still_s, self.still_tol, self.table_tol, self.reanchor_xy = 1.0, 0.008, 0.025, 0.06
        self.reanchor = True
        for k, v in kw.items(): setattr(self, k, v)

    @classmethod
    def slow(cls, **kw):
        """The new chain with the speed/filter values before the 14/11 evening tuning."""
        return cls(**{**dict(pos_cutoff=2.5, pos_beta=40.0, rot_cutoff=2.5, rot_beta=2.0, grip_tau=0.05, joint_speed=0.7, vmax=0.35,
                             vfinal=0.30, wfinal=np.radians(150), lead=0.0), **kw})

    @classmethod
    def old(cls, **kw):
        """The previous teleop_multi.py chain (for before/after measurements only)."""
        c = cls(legacy=True, pos_cutoff=0.7, pos_beta=0.02, rot_cutoff=0.7, rot_beta=0.02, leash=0.0, post_deadband=0.003, grip_tau=0.15,
                joint_speed=1.0, uniform_step=False, vfinal=None, assist_r=0.06, w_rate=None, ns_fade=None, fixed_target=False,
                raise_only_counter=False, zoff=0.10, reanchor=False, snap_ticks=1, lead=0.0)
        for k, v in kw.items(): setattr(c, k, v)
        return c


# --- small filters -------------------------------------------------------------------------------------------------------
class OneEuro:
    def __init__(self, cutoff, beta, dcut=1.0): self.fc, self.b, self.dc = cutoff, beta, dcut; self.reset()
    def reset(self, x=None): self.x, self.dx, self.t = (None if x is None else np.array(x, float)), np.zeros(3), None
    @staticmethod
    def _a(fc, dt): return 1.0 / (1.0 + 1.0 / (2 * np.pi * fc * dt))
    def __call__(self, x, t):
        x = np.asarray(x, float)
        if self.x is None or self.t is None: self.x, self.t = x.copy(), t; return x.copy()
        dt = max(t - self.t, 1e-3); self.t = t
        self.dx += self._a(self.dc, dt) * ((x - self.x) / dt - self.dx)
        fc = self.fc + self.b * float(np.linalg.norm(self.dx))       # one cutoff for the vector: no direction distortion
        self.x = self.x + self._a(fc, dt) * (x - self.x); return self.x.copy()


class QuatEuro:
    def __init__(self, cutoff, beta, dcut=1.0): self.fc, self.b, self.dc = cutoff, beta, dcut; self.reset()
    def reset(self): self.q, self.w, self.t = None, 0.0, None
    def __call__(self, q, t):
        q = np.asarray(q, float) / np.linalg.norm(q)
        if self.q is None: self.q, self.t = q.copy(), t; return q.copy()
        if q @ self.q < 0: q = -q
        dt = max(t - self.t, 1e-3); self.t = t; dot = float(np.clip(q @ self.q, -1, 1)); th = np.arccos(dot)
        self.w += OneEuro._a(self.dc, dt) * (2 * th / dt - self.w); a = OneEuro._a(self.fc + self.b * self.w, dt)
        out = (1 - a) * self.q + a * q if th < 1e-4 else (np.sin((1 - a) * th) * self.q + np.sin(a * th) * q) / np.sin(th)
        self.q = out / np.linalg.norm(out); return self.q.copy()


class Leash:
    """Continuous deadband: the output follows the input only once it is more than eps away, then trails it by eps (no steps)."""
    def __init__(self, eps): self.eps, self.y = eps, None
    def reset(self, x=None): self.y = None if x is None else np.array(x, float)
    def __call__(self, x):
        x = np.asarray(x, float)
        if self.y is None or self.eps <= 0: self.y = x.copy(); return x.copy()
        d = x - self.y; n = float(np.linalg.norm(d))
        if n > self.eps: self.y = self.y + d * (1 - self.eps / n)
        return self.y.copy()


class HoldDeadband:
    def __init__(self, eps): self.eps, self.y = eps, None
    def reset(self, x=None): self.y = None
    def __call__(self, x):
        x = np.asarray(x, float)
        if self.eps <= 0 or self.y is None or np.linalg.norm(x - self.y) >= self.eps: self.y = x.copy()
        return self.y.copy()


def q2m(q): return arm_ik.quat_wxyz_to_mat(np.asarray(q, float) / np.linalg.norm(q))


def m2q(R): q = np.zeros(4); mujoco.mju_mat2Quat(q, np.asarray(R, float).flatten()); return q


def rotvec(R):
    v = np.zeros(3); mujoco.mju_quat2Vel(v, m2q(R), 1.0); return v


def from_rotvec(v):
    q = np.array([1.0, 0, 0, 0]); mujoco.mju_quatIntegrate(q, np.asarray(v, float), 1.0); return q2m(q)


def slerp(R0, R1, w):
    return from_rotvec(np.clip(w, 0, 1) * rotvec(R1 @ R0.T)) @ R0


def smooth01(x): x = float(np.clip(x, 0, 1)); return x * x * (3 - 2 * x)


# --- one hand ------------------------------------------------------------------------------------------------------------
Q_NEUTRAL = {}       # side -> wxyz quaternion, filled by load_neutral() from the seated calibration
UP_SIGN = {}         # side -> -1 when the calibration's last step found the up axis mirrored (Coil hemisphere flip), else +1


def load_neutral(path, sides):
    import json, os
    if not os.path.exists(path): return
    c = json.load(open(path)).get("seated", {})
    for s in sides:
        if c.get(s, {}).get("q_neutral") is not None: Q_NEUTRAL[s] = np.array(c[s]["q_neutral"], float)
        if c.get(s, {}).get("up_sign") is not None: UP_SIGN[s] = int(c[s]["up_sign"])


class HandChain:
    """Operator glove + Coil sample -> robot wrist target (pos, rot), closure request and mode, for ONE hand.
    grasp = (gp, gR, pin_t, name, profile) of the object assigned to this hand (or None); rest = (p, R) robot rest wrist pose."""

    def __init__(self, side, Rh, rest, grasp, cfg, floor_z):
        self.side, self.Rh, self.cfg, self.floor = side, np.asarray(Rh, float), cfg, floor_z
        self.Rp = self.Rh.copy()                                   # axes for POSITIONS (orientation keeps Rh, a proper rotation)
        if UP_SIGN.get(side, 1) < 0: self.Rp[2] *= -1.0            # Coil hemisphere flip: the glove is reported at -P
        self.rest_p, self.rest_R = np.array(rest[0], float), np.array(rest[1], float)
        self.grasp = grasp; c = cfg
        self.pf, self.qf = OneEuro(c.pos_cutoff, c.pos_beta), QuatEuro(c.rot_cutoff, c.rot_beta)
        self.leash, self.post = Leash(c.leash), HoldDeadband(c.post_deadband)
        self.P0 = self.Q0 = None; self.blend = np.zeros(3); self.blend0 = np.zeros(3); self.blend_t = 0.0; self.table_up = None
        self.hist = []; self.still_used = False; self.reanchors = 0
        self.grip = None; self.stage = None; self.w = 0.0; self.snap_n = 0; self.t_st = 0.0; self.lock = None; self.carry = np.zeros(3)
        self.frac = 0.0; self.ns = 1.0; self.last_raw = None; self.out_p, self.out_R = self.rest_p.copy(), self.rest_R.copy(); self.p_raw = self.rest_p.copy()
        self.p_tel = self.rest_p.copy(); self.p_filt = self.rest_p.copy(); self.first = True; self.t_last = None
        if c.legacy and grasp is not None: self.base_p, self.base_R = grasp[0].copy(), grasp[1].copy()   # old: table centre = grasp pose
        else: self.base_p, self.base_R = self.rest_p.copy(), self.rest_R.copy()
        if grasp is not None:
            d = grasp[0][:2] - self.rest_p[:2]; self.reach = max(float(np.linalg.norm(d)), 0.05); self.reach_u = d / self.reach
            self.drop = grasp[0][2] - self.rest_p[2] - c.zoff
        else: self.reach, self.reach_u, self.drop = 1.0, np.array([1.0, 0.0]), 0.0

    # mapping operator-frame displacement (forward, left, up, m) -> robot wrist position
    def map_rel(self, rel):
        c = self.cfg
        if c.legacy: r = c.gain * rel; r[2] -= c.zoff; return self.base_p + r
        p = self.rest_p + c.gain * rel
        self.frac = frac = smooth01(float(c.gain * rel[:2] @ self.reach_u) / self.reach)
        p[2] += frac * self.drop; return p

    def human_target(self, robot_p):
        """Inverse of map_rel (on the reach line): operator displacement that puts the robot wrist at robot_p (used to align replays)."""
        c = self.cfg
        if c.legacy: return (robot_p - self.base_p + np.array([0, 0, c.zoff])) / c.gain
        d = robot_p - self.rest_p; d[2] -= self.drop * smooth01(float(d[:2] @ self.reach_u) / self.reach); return d / c.gain

    def anchor(self, P, Q, t):
        self.P0 = np.array(P, float); self.table_up = float(self.Rp[2] @ P)
        qn = Q_NEUTRAL.get(self.side)        # operator's "open, palm down, in front" orientation (calibration's last step) = robot rest pose
        self.Q0 = np.array(qn if qn is not None else Q, float)
        self.pf.reset(); self.qf.reset(); self.leash.reset(); self.post.reset()

    def _still(self, P, Q, t, g, pr):
        """Rest detector: 1 s with the raw wrist inside a few mm, hand open. Returns the mean pose when it fires."""
        c = self.cfg; self.hist.append((t, np.array(P, float), np.array(Q, float))); self.hist = [h for h in self.hist if t - h[0] <= c.still_s + 0.05]
        if self.hist[-1][0] - self.hist[0][0] < c.still_s - 0.05: return None
        Ps = np.array([h[1] for h in self.hist]); m = Ps.mean(0)
        if np.max(np.linalg.norm(Ps - m, axis=1)) > c.still_tol: self.still_used = False; return None
        if pr is not None and g > 0.3 * pr["g_ref"]: return None
        return m, self.hist[-1][2]

    def update(self, F, P, Q, t, pinch_now, wrist_R_now, near_egg=None, push_block=None, wrist_p_now=None):
        """One tick. pinch_now / wrist_R_now: robot pinch point and wrist rotation from the last command (for assist/snap).
        near_egg(p) -> speed limit override or None; push_block(p_new, p_old) -> True to keep p_old. Returns dict."""
        c = self.cfg; pr = self.grasp[4] if self.grasp else None
        g_raw = 0.5 * (F[1] + F[2]); dt = 1 / RATE if self.t_last is None else max(t - self.t_last, 1e-3); self.t_last = t
        self.grip = g_raw if self.grip is None else self.grip + (1 - np.exp(-dt / c.grip_tau)) * (g_raw - self.grip)
        g = self.grip; ev = None
        if c.legacy:
            if self.P0 is None: self.anchor(P, Q, t)
        else:
            st = self._still(P, Q, t, g, pr)
            if st is not None and self.P0 is None:
                self.anchor(st[0], st[1], t); ev = "anchored"
            elif st is not None and c.reanchor and not self.still_used and self.stage is None:
                self.still_used = True; d = self.Rp @ (st[0] - self.P0)
                if abs(float(self.Rp[2] @ st[0]) - self.table_up) < c.table_tol:          # resting ON the table
                    shift = np.array([0.0, 0.0, d[2]])
                    if np.linalg.norm(d[:2]) < c.reanchor_xy: shift[:2] = d[:2]          # back at the start spot: full re-anchor
                    if np.linalg.norm(shift) > 0.002:
                        # new anchor; the old->new difference is blended out over 1 s instead of jumping
                        self.blend0 = self.blend + c.gain * shift; self.blend = self.blend0.copy(); self.P0 = self.P0 + self.Rp.T @ shift; self.blend_t = t; self.reanchors += 1
                        ev = f"re-anchored {100 * np.linalg.norm(shift):.1f} cm"
                    if np.linalg.norm(d[:2]) < c.reanchor_xy and Q_NEUTRAL.get(self.side) is None: self.Q0 = np.array(st[1], float)
        if self.P0 is None:                                                   # not engaged yet: hold the rest pose
            self.out_p, self.out_R = self.rest_p.copy(), self.rest_R.copy()
            return dict(p=self.out_p, R=self.out_R, c=0.0, g=g, mode="waiting: hand flat + still on the table", k_rest=0.1, ev=ev, p_raw=self.rest_p.copy(), p_filt=self.rest_p.copy())
        if np.linalg.norm(self.blend0) > 0:                                   # fade the re-anchor difference out linearly in 1 s
            self.blend = self.blend0 * max(0.0, 1.0 - (t - self.blend_t) / 1.0)
            if t - self.blend_t >= 1.0: self.blend0 = np.zeros(3); self.blend = np.zeros(3)
        # position: raw leash -> One Euro -> (legacy hold deadband) -> mapping
        rel_raw = self.Rp @ (np.asarray(P, float) - self.P0)
        self.p_raw = self.map_rel(rel_raw)                                   # unfiltered reference (for the latency measurement)
        x = self.post(self.pf(self.leash(P), t))
        if c.lead and not c.legacy:                                              # prediction: compensate the pipeline delay
            x = x + np.clip(self.pf.dx * c.lead, -0.03, 0.03)                   # (filtered velocity x lead time, max 3 cm)
        p_tel = self.map_rel(self.Rp @ (x - self.P0)) + (self.blend if not c.legacy else 0)
        self.p_filt = p_tel.copy()
        if c.legacy and self.first: self.p_tel = p_tel.copy()                 # old: the first mapped target is taken as is (A7 jump)
        self.first = False
        # orientation: operator rotation relative to his flat hand, expressed in the robot frame, applied to the base (rest) rotation
        Qf = self.qf(Q, t); R_rel = self.Rh @ q2m(Qf) @ q2m(self.Q0).T @ self.Rh.T
        rv = rotvec(R_rel); n = np.linalg.norm(rv)
        if n > np.radians(WRIST_MAX_DEG): R_rel = from_rotvec(rv * np.radians(WRIST_MAX_DEG) / n)
        # new: the neutral (flat-hand) orientation turns from the rest rotation to the grasp rotation as the hand reaches the object
        base_R = slerp(self.base_R, self.grasp[1], self.frac) if (self.grasp is not None and not c.legacy) else self.base_R
        R_tel = R_rel @ base_R
        vmax = c.vmax; ne = near_egg(pinch_now) if near_egg else None
        if ne is not None: vmax = ne
        dp = p_tel - self.p_tel; nd = np.linalg.norm(dp)
        if nd > vmax * dt: p_tel = self.p_tel + dp * vmax * dt / nd
        if push_block and self.stage is None and push_block(p_tel, self.p_tel): p_tel = self.p_tel.copy()
        self.p_tel = p_tel.copy()
        tgt_p, tgt_R, mode, hold_f, conv = p_tel + self.carry, R_tel, "teleop", False, False
        if np.linalg.norm(self.carry) > 0: self.carry *= max(0.0, 1 - dt / 1.5)
        if self.grasp is not None:
            gp, gR, pin_t, name, _ = self.grasp
            dv = pinch_now - pin_t; dxy = float(np.hypot(dv[0], dv[1])); r_e = np.degrees(np.linalg.norm(arm_ik.rot_err(gR, wrist_R_now)))
            st = self.stage
            # new: the wrist really is at the grasp pose (the fingers may close fully / the hold may start only then)
            conv = wrist_p_now is not None and np.linalg.norm(wrist_p_now - gp) < 0.015 and r_e < 15.0
            if c.legacy:
                if st is None:
                    if dxy < c.snap_xy and abs(dv[2]) < c.snap_z and r_e < c.snap_deg and g > 0.3 * pr["g_ref"]: st, self.t_st = "close", t
                    elif dxy < 0.06 and -0.02 < dv[2] < 0.08 and g > 0.2 * pr["g_ref"]:
                        w = float(np.clip((0.06 - dxy) / 0.04, 0, 1)); tgt_p = p_tel + w * np.clip(gp - p_tel, -0.03, 0.03); tgt_R = slerp(R_tel, gR, w); mode = f"assist {w:.1f}"
            else:
                if st is None:
                    # new: assist/snap measured on the WRIST (the mapped quantity), not on the pinch (that depends on the hand rotation)
                    dw = wrist_p_now - gp; ok = np.hypot(dw[0], dw[1]) < c.snap_xy and abs(dw[2]) < c.snap_z and r_e < c.snap_deg and g > 0.3 * pr["g_ref"]
                    dv = p_tel + self.carry - gp; dxy = float(np.hypot(dv[0], dv[1]))
                    self.snap_n = self.snap_n + 1 if ok else 0
                    if self.snap_n >= c.snap_ticks: st, self.t_st, self.snap_n = "close", t, 0
                    w_goal = smooth01((c.assist_r - dxy) / (c.assist_r - 0.02)) if (-0.04 < dv[2] < 0.08 and g > 0.2 * pr["g_ref"]) else 0.0
                else: w_goal = 1.0 if st == "close" else self.w
                self.w = float(np.clip(w_goal, self.w - c.w_rate * dt, self.w + c.w_rate * dt))
                if st is None and self.w > 0:
                    tgt_p = p_tel + self.carry + self.w * (gp - p_tel - self.carry); tgt_R = slerp(R_tel, gR, self.w); mode = f"assist {self.w:.2f}"
            if st == "close":
                if c.legacy: tgt_p, tgt_R = gp, gR
                else: tgt_p, tgt_R = p_tel + self.w * (gp - p_tel), slerp(R_tel, gR, self.w)
                mode = f"closing on the {name}"
                if g > 0.6 * pr["g_ref"] and t - self.t_st > 0.5 and (c.legacy or conv): st = "hold"; self.lock = tgt_p - p_tel
                if g < 0.15 * pr["g_ref"]: st = None
            elif st == "hold":
                tgt_p, tgt_R, mode = p_tel + self.lock, gR, f"holding the {name}"
                if not c.legacy: tgt_p = tgt_p.copy(); tgt_p[2] = max(tgt_p[2], gp[2] - 0.005)   # never press the held object into the table
                if g < 0.25 * pr["g_ref"]: st, self.t_st, self.lock = "retreat", t, p_tel + self.lock
            elif st == "retreat":
                u = min(1.0, (t - self.t_st) / 1.0); tgt_p, tgt_R, hold_f, mode = self.lock + np.array([0, 0, 0.10 * u]), gR, True, "release"
                if u >= 1.0:
                    st = None
                    if not c.legacy: self.carry = tgt_p - p_tel; self.w = 0.0      # robot stays up, then follows the operator again smoothly
            self.stage = st
        tgt_p = tgt_p.copy(); tgt_p[2] = max(tgt_p[2], self.floor)
        if c.vfinal is not None:                                                 # final limiter: no state change can jump the target
            dp = tgt_p - self.out_p; nd = np.linalg.norm(dp)
            if nd > c.vfinal * dt: tgt_p = self.out_p + dp * c.vfinal * dt / nd
            rv = rotvec(tgt_R @ self.out_R.T); n = np.linalg.norm(rv)
            if n > c.wfinal * dt: tgt_R = from_rotvec(rv * c.wfinal * dt / n) @ self.out_R
        self.out_p, self.out_R = tgt_p, tgt_R
        if c.ns_fade:
            goal = 1.0 if self.stage is None else 0.0; self.ns = float(np.clip(goal, self.ns - dt / c.ns_fade, self.ns + dt / c.ns_fade)); k_rest = 0.1 * self.ns
        else: k_rest = 0.1 if self.stage is None else None
        cl = 0.0
        if pr is not None and not hold_f: cl = pr["cap"] * float(np.clip(g / pr["g_ref"], 0, 1))
        if pr is not None and not c.legacy and (self.w > 0 or self.stage == "close") and self.stage != "hold" and not conv:
            cl = min(cl, 0.5 * pr["cap"])      # approaching: fingers only pre-shaped (as in the grasp search) until the wrist is at the grasp pose
        return dict(p=tgt_p, R=tgt_R, c=cl, g=g, mode=mode, k_rest=k_rest, ev=ev, p_raw=self.p_raw.copy(), p_filt=self.p_filt.copy())


# Robot REST pose (14/11 evening, operator request): hands OPEN, PALM DOWN, in front of the robot. Measured on the Dex3 model:
# the palm faces +y of the right wrist frame and -y of the left one; fingers point along wrist +x.
PALM_DOWN_R = {"right": np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]]),     # columns: x fwd, y (palm) down, z
               "left": np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])}
REST_XYZ = (0.27, 0.20, 0.12)        # pelvis frame: 27 cm forward, 20 cm to the side, 12 cm above the counter


def palm_down_rest(kin, counter_z, sides=("left", "right"), iters=150):
    """Solve the arms (in place) to the palm-down front rest pose; returns the joint dict. Errors are printed, never hidden."""
    x, y, z = REST_XYZ
    for s in sides:
        p = kin.base + np.array([x, y if s == "left" else -y, counter_z + z])
        for _ in range(iters): kin.a.solve(s, p, PALM_DOWN_R[s])
        e = np.linalg.norm(kin.a.d.xpos[kin.a.ee[s]] - p); r = np.degrees(np.linalg.norm(arm_ik.rot_err(PALM_DOWN_R[s], kin.a.d.xmat[kin.a.ee[s]].reshape(3, 3))))
        print(f"[rest] {s}: palm-down front pose, error {100 * e:.1f} cm / {r:.0f} deg", flush=True)
    return dict(kin.a.q)


PRIOR = None        # g1/arm_prior.RealArmPrior: real-G1 postures as the IK null-space target (set by the caller; None = old rest posture)
NATURAL = {"left": [], "right": []}   # per-tick RMS joint distance to the real postures (filled when PRIOR is set)


def solve_arm(kin, side, out, cfg, rest, unsafe, floor_z, palm_fn=None):
    """IK one hand toward out['p'], out['R'] within the joint-speed limit, then the safety check. Returns the block reason list ([] = ok).
    Raises the target over the counter keep-out only for a counter block (A8, new) or for any block (legacy)."""
    if PRIOR is not None: rest = PRIOR.rest(kin, side, out["p"], out["R"], rest)
    q_prev = dict(kin.a.q); k = out["k_rest"]
    def go(p, R=None):
        kin.a.solve(side, p, out["R"] if R is None else R, q_rest=rest if k else None, k_rest=k or 0.1, uniform=cfg.uniform_step)
        return unsafe(kin)
    why = go(out["p"])
    if why:
        kin.a.q.update(q_prev); kin.a.apply()
        R_now = kin.a.d.xmat[kin.a.ee[side]].reshape(3, 3).copy()
        low = floor_z - min(kin.a.d.xpos[kin.a.ee[side]][2], palm_fn(kin, side)[2]) if palm_fn else 0.0
        counter = all(w.endswith("_counter") for w in why)
        tries = []
        if low > 0 and (counter or not cfg.raise_only_counter): tries.append((out["p"] + np.array([0, 0, low + 0.01]), None))
        if not cfg.legacy:
            # new: a rotation toward the grasp can dip the palm into the keep-out: try the translation alone, then a 2 cm higher one
            tries += [(out["p"], R_now), (out["p"] + np.array([0, 0, 0.02]), R_now)]
        for p, R in tries:
            why2 = go(p, R)
            if not why2: return []
            kin.a.q.update(q_prev); kin.a.apply()
    return why


def seated_calib(readers, hands, path, move=0.15):
    """Short guided calibration, seated beside the robot (~12 s per hand, beeps): hand FLAT and still on the table, slide ~15 cm FORWARD,
    back, slide ~15 cm LEFT. Only the axes (forward, left, up in Coil coordinates) and the flat-hand rotation are stored: the start point is
    re-taken automatically at every run (hand flat and still for 1 s). readers[h]() -> (fingers, wrist_pos, wrist_quat) or None."""
    import json, os, time
    try:
        import winsound; beep = lambda f=880: winsound.Beep(f, 150)
    except Exception: beep = lambda f=880: None
    out = {}
    for h in hands:
        def hold(msg, secs=2.0):
            print(f"[calib {h}] {msg}", flush=True); beep(); time.sleep(0.8); P, Qs = [], []; t0 = time.time()
            while time.time() - t0 < secs:
                s = readers[h]()
                if s and s[1] is not None and not np.isnan(s[1]).any(): P.append(np.asarray(s[1], float)); Qs.append(np.asarray(s[2], float))
                time.sleep(1 / RATE)
            if len(P) < 10: raise SystemExit(f"[calib] no Coil position from the {h} glove: is it on and seen by the Coil?")
            return np.median(np.array(P[len(P) // 2:]), 0), np.array(Qs[-1])
        name = "DESTRA" if h == "right" else "SINISTRA"
        c, qc = hold(f"mano {name} PIATTA e FERMA sul tavolo (posizione di partenza)")
        f, _ = hold(f"scorri la mano {name} AVANTI di ~{100 * move:.0f} cm e FERMA")
        hold("torna al punto di partenza", 1.5)
        l, _ = hold(f"scorri la mano {name} a SINISTRA di ~{100 * move:.0f} cm e FERMA")
        f, l = f - c, l - c
        if min(np.linalg.norm(f), np.linalg.norm(l)) < 0.07: raise SystemExit(f"[calib {h}] movements too small (need ~{100 * move:.0f} cm): run again")
        fu, lu = f / np.linalg.norm(f), l / np.linalg.norm(l); ang = float(np.degrees(np.arccos(np.clip(fu @ lu, -1, 1))))
        if not 70 <= ang <= 110: raise SystemExit(f"[calib {h}] forward/left {ang:.0f} deg apart (need 70-110): straighter moves, run again (nothing saved)")
        u = np.cross(fu, lu); u /= np.linalg.norm(u); f2 = fu + np.cross(lu, u); f2 /= np.linalg.norm(f2); l2 = np.cross(u, f2)
        out[h] = {"R": np.stack([f2, l2, u]).round(5).tolist(), "q_flat": qc.round(5).tolist(), "origin": c.round(4).tolist(), "angle_deg": round(ang, 1),
                  "measured_cm": round(100 * float(np.mean([np.linalg.norm(f), np.linalg.norm(l)])), 1)}
        print(f"[calib {h}] ok: forward-left {ang:.0f} deg", flush=True); beep(1200)
    # FINAL step (14/11 evening): the neutral pose = robot rest pose (hands open, palm down, in front of the robot)
    print("[calib] ULTIMO PASSO: mani APERTE, PALMO VERSO IL BASSO, davanti a te, SOLLEVATE 10-15 cm sopra il tavolo, FERME", flush=True); beep(); time.sleep(1.5)
    for h in hands:
        Qs, Ps = [], []; t0 = time.time()
        while time.time() - t0 < 1.5:
            s = readers[h]()
            if s and s[2] is not None and not np.isnan(s[2]).any(): Qs.append(np.asarray(s[2], float))
            if s and s[1] is not None and not np.isnan(s[1]).any(): Ps.append(np.asarray(s[1], float))
            time.sleep(1 / RATE)
        if len(Ps) >= 10:            # up check: the neutral pose is ABOVE the flat start; a mirrored up axis = Coil hemisphere flip
            up = float(np.array(out[h]["R"])[2] @ (np.median(np.array(Ps), 0) - np.array(out[h]["origin"])))
            out[h]["up_check_cm"] = round(100 * up, 1)
            if up < -0.03: out[h]["up_sign"] = -1; print(f"[calib {h}] up axis MIRRORED (Coil hemisphere flip, {100 * up:.0f} cm): corrected", flush=True)
            elif up > 0.03: out[h]["up_sign"] = 1; print(f"[calib {h}] up axis ok ({100 * up:.0f} cm above the start)", flush=True)
            else: out[h]["up_sign"] = 1; print(f"[calib {h}] up check unclear ({100 * up:.0f} cm): lift the hands ~10-15 cm in the last step next time", flush=True)
        if len(Qs) >= 10:
            qn = Qs[-1]; out[h]["q_neutral"] = qn.round(5).tolist()
            d = np.degrees(np.linalg.norm(rotvec(q2m(qn) @ q2m(out[h]["q_flat"]).T)))
            print(f"[calib {h}] posa neutra salvata (differenza dalla mano piatta sul tavolo: {d:.0f} gradi)", flush=True)
    beep(1200)
    calj = json.load(open(path)) if os.path.exists(path) else {}
    calj.setdefault("seated", {}).update(out); json.dump(calj, open(path, "w"), indent=1)
    return out


def load_axes(path, side):
    """Operator axes for one hand: the seated calibration, else the older table calibration ("hands"), else None."""
    import json, os
    if not os.path.exists(path): return None
    c = json.load(open(path))
    for key in ("seated", "hands"):
        if side in c.get(key, {}): return np.array(c[key][side]["R"], float)
    return None


def align_take(P, Q, F, Rh, P0, rel_goal, grip_frac=0.6, pre_s=1.5, post_s=2.0, seed=0, mirror=False):
    """Replay helper: keeps the recorded timing, noise and grip of a take, but rotates+scales its reach (operator frame) so that the
    mean wrist position while gripping maps onto rel_goal (operator displacement that lands the robot 2 cm above its grasp pose).
    Adds pre_s seconds of the operator resting still at the start (seated setup) and post_s at the end. mirror: right take -> left hand."""
    P, Q, F = np.asarray(P, float), np.asarray(Q, float), np.asarray(F, float)
    rel = (Rh @ (P - P0).T).T
    M = np.diag([1.0, -1.0, 1.0])
    if mirror: rel = rel @ M
    g = F[:, 1:3].mean(1); i0 = int(np.argmax(g > grip_frac * g.max())); v = rel[i0:i0 + 10].mean(0)   # where the grip starts
    s = float(np.clip(np.linalg.norm(rel_goal) / max(np.linalg.norm(v), 1e-3), 0.5, 2.5))
    a, b = v / np.linalg.norm(v), np.asarray(rel_goal, float) / np.linalg.norm(rel_goal); ax = np.cross(a, b); sn = np.linalg.norm(ax)
    Ra = np.eye(3) if sn < 1e-6 else from_rotvec(ax / sn * np.arctan2(sn, a @ b))
    rel2 = s * (Ra @ rel.T).T; P2 = P0 + (Rh.T @ rel2.T).T
    if mirror:
        Mc = Rh.T @ M @ Rh; Q = np.array([m2q(Mc @ q2m(q) @ Mc) for q in Q])
    rng = np.random.default_rng(seed); n0, n1 = int(pre_s * RATE), int(post_s * RATE)
    P2 = np.vstack([P2[0] + rng.normal(0, 0.0005, (n0, 3)), P2, P2[-1] + rng.normal(0, 0.0005, (n1, 3))])
    Q = np.vstack([np.repeat(Q[:1], n0, 0), Q, np.repeat(Q[-1:], n1, 0)]); F = np.vstack([np.repeat(F[:1], n0, 0), F, np.repeat(F[-1:], n1, 0)])
    return P2, Q, F, dict(scale=round(s, 2), rot_deg=round(float(np.degrees(np.arctan2(sn, a @ b))), 1))


def metrics(log, rate=RATE):
    """log: list of per-tick dicts with t, p_raw, p_tel (filtered teleop), p_cmd (commanded wrist), q (arm joints of this hand), mode, blocked.
    Returns: filter delay (One Euro + leash vs raw), target delay (+ speed limits), arm delay (commanded wrist vs final target: IK + joint
    speed limit), all in ms by best time shift; RMS / p99 jerk of the commanded wrist (m/s^3); jumps (> 1 cm per tick); max joint speed."""
    L = [r for r in log if r.get("engaged")]
    if len(L) < 20: return {}
    raw = np.array([r["p_raw"] for r in L]); tel = np.array([r["p_tel"] for r in L]); fil = np.array([r["p_filt"] for r in L])
    cmd = np.array([r["p_cmd"] for r in L]); tgt = np.array([r["tgt"] for r in L]); q = np.array([r["q"] for r in L])
    mask = np.array([r["t"] - L[0]["t"] > 1.5 for r in L])          # after the first 1.5 s of engagement
    idx = np.arange(len(raw))
    def lag(y, ref):
        """delay (fractional ticks, linear interpolation) that best aligns y with ref"""
        best = (1e9, 0.0)
        for k in np.arange(0.0, 45.0, 0.1):
            sh = np.stack([np.interp(idx - k, idx, ref[:, i]) for i in range(3)], 1); m = mask & (idx - k >= 0)
            if m.sum() < 20: break
            e = np.sqrt(np.mean(np.sum((y - sh)[m] ** 2, 1))); best = min(best, (e, k))
        return 1000 * best[1] / rate
    lf = lag(fil, raw); lt = lag(tel, raw); la = lag(cmd, tgt)
    j = np.diff(cmd, 3, axis=0) * rate ** 3; jn = np.linalg.norm(j, axis=1); step = np.linalg.norm(np.diff(cmd, axis=0), axis=1)
    dq = np.abs(np.diff(q, axis=0)) * rate; ec = np.sqrt(np.mean(np.sum((cmd - tgt)[mask] ** 2, 1)))
    return dict(filter_delay_ms=round(lf), target_delay_ms=round(lt), arm_delay_ms=round(la), arm_track_err_cm=round(100 * ec, 2), jerk_rms=round(float(np.sqrt(np.mean(jn ** 2))), 1),
                jerk_p99=round(float(np.percentile(jn, 99)), 1), jumps_gt1cm=int((step > 0.01).sum()), max_step_cm=round(100 * float(step.max()), 2),
                max_joint_speed=round(float(dq.max()), 3))
