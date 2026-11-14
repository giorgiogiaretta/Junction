"""Small filters and safety clamps for G1 teleoperation."""

import math

import numpy as np


class OneEuro:
    """One Euro low-pass filter for 3D vectors (Casiez et al., 2012)."""

    def __init__(self, freq=30, min_cutoff=1.0, beta=0.02, d_cutoff=1.0):
        if freq <= 0 or min_cutoff <= 0 or d_cutoff <= 0:
            raise ValueError("freq and cutoff frequencies must be positive")
        self.freq = float(freq)
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self.reset()

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def reset(self):
        """Clear the filter history."""
        self._value = None
        self._derivative = None
        self._time = None

    def __call__(self, x, t=None):
        """Filter a three-component vector; ``t`` is an optional timestamp."""
        value = np.asarray(x, dtype=float)
        if value.shape != (3,):
            raise ValueError("OneEuro expects a 3D vector")
        now = float(t) if t is not None else (0.0 if self._time is None else self._time + 1 / self.freq)
        if self._value is None:
            self._value = value.copy()
            self._derivative = np.zeros(3, dtype=float)
            self._time = now
            return self._value.copy()
        dt = now - self._time
        if dt <= 0:
            dt = 1.0 / self.freq
        derivative = (value - self._value) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self._derivative += a_d * (derivative - self._derivative)
        cutoff = self.min_cutoff + self.beta * np.abs(self._derivative)
        alpha = np.array([self._alpha(c, dt) for c in cutoff])
        self._value += alpha * (value - self._value)
        self._time = now
        return self._value.copy()


class QuatFilter:
    """One Euro smoothing for unit quaternions in ``w, x, y, z`` order."""

    def __init__(self, freq=30, min_cutoff=1.0, beta=0.02, d_cutoff=1.0):
        self.freq = float(freq)
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        if min(self.freq, self.min_cutoff, d_cutoff) <= 0:
            raise ValueError("freq and cutoff frequencies must be positive")
        self.reset()

    def reset(self):
        """Clear the quaternion and angular-speed history."""
        self._q = None
        self._speed = 0.0
        self._time = None

    def __call__(self, q, t=None):
        """Filter a quaternion, choosing the equivalent sign nearest history."""
        q = np.asarray(q, dtype=float)
        if q.shape != (4,) or np.linalg.norm(q) == 0:
            raise ValueError("QuatFilter expects a nonzero wxyz quaternion")
        q = q / np.linalg.norm(q)
        now = float(t) if t is not None else (0.0 if self._time is None else self._time + 1 / self.freq)
        if self._q is None:
            self._q, self._time = q.copy(), now
            return self._q.copy()
        if np.dot(self._q, q) < 0:
            q = -q
        dt = now - self._time
        if dt <= 0:
            dt = 1 / self.freq
        dot = float(np.clip(np.dot(self._q, q), -1.0, 1.0))
        angle = 2.0 * math.acos(dot)
        speed = angle / dt
        a_d = OneEuro._alpha(self.d_cutoff, dt)
        self._speed += a_d * (speed - self._speed)
        cutoff = self.min_cutoff + self.beta * self._speed
        alpha = OneEuro._alpha(cutoff, dt)
        if dot > 0.9995:
            out = (1 - alpha) * self._q + alpha * q
            out /= np.linalg.norm(out)
        else:
            theta = math.acos(dot)
            out = (math.sin((1 - alpha) * theta) * self._q + math.sin(alpha * theta) * q) / math.sin(theta)
        if np.dot(self._q, out) < 0:
            out = -out
        self._q, self._time = out, now
        return out.copy()


def deadband(v, eps=0.004):
    """Suppress motion within ``eps`` metres of the last accepted 3D point."""
    value = np.asarray(v, dtype=float)
    if not hasattr(deadband, "_held") or deadband._held is None:
        deadband._held = value.copy()
    elif value.shape != deadband._held.shape:
        raise ValueError("deadband input shape cannot change")
    elif np.linalg.norm(value - deadband._held) >= eps:
        deadband._held = value.copy()
    return deadband._held.copy()


def clamp_wrist_to_human(robot_wrist_q, human_wrist_rel_deg, limits):
    """Map human roll, pitch and yaw to bounded G1 wrist joints in radians.

    ``limits`` may be the decoded limits document or its ``arm_q`` list. The
    current robot wrist vector is accepted for teleoperation-call compatibility;
    each output is the corresponding human relative angle, safely clamped.
    """
    del robot_wrist_q
    human = np.asarray(human_wrist_rel_deg, dtype=float)
    if human.shape != (3,):
        raise ValueError("human_wrist_rel_deg must contain roll, pitch, yaw")
    entries = limits.get("arm_q", limits) if isinstance(limits, dict) else limits
    by_name = {entry["joint"]: entry["filter"] for entry in entries}
    names = ("wrist_roll_joint", "wrist_pitch_joint", "wrist_yaw_joint")
    # Both arms have identical wrist bounds in the supplied G1 limits.
    result = np.deg2rad(np.clip(human, -70.0, 70.0))
    for i, suffix in enumerate(names):
        bounds = [pair for name, pair in by_name.items() if name.endswith(suffix)]
        if not bounds:
            raise ValueError("limits are missing " + suffix)
        low = max(pair[0] for pair in bounds)
        high = min(pair[1] for pair in bounds)
        result[i] = np.clip(result[i], low, high)
    return result


class Deadband:
    """Per-instance deadband (one per hand): holds the last accepted point until the input moves more than eps (m)."""
    def __init__(self, eps=0.003): self.eps, self._held = eps, None
    def reset(self): self._held = None
    def __call__(self, v):
        v = np.asarray(v, float)
        if self._held is None or np.linalg.norm(v - self._held) >= self.eps: self._held = v.copy()
        return self._held.copy()
