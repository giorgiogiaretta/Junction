"""Teleop pipeline used by the truth test and the sim server: hand_state packet -> Force Cushion -> MuJoCo scene.
packet (dict, hand_state): t, fingers[5], optional wrist_position (Coil Pro), button_pressed.
Wrist: Coil Pro wrist_position (relative to the first sample) when present, otherwise `wrist_fallback(elapsed_s)` (mock path).
Force Cushion: ml.grasp_assist.GraspAssist(profile) caps closure; profile None/"none" = full fist passes through.
"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from robot.parse import parse_state
from robot.scene import Scene, wrist_from_coil, mock_wrist


class Pipeline:
    def __init__(self, obj="cube", profile=None, wrist_fallback=mock_wrist, coil_scale=1.0, dt=1 / 60):
        from ml.grasp_assist import GraspAssist
        self.scene, self.dt, self.fallback, self.scale = Scene(obj), dt, wrist_fallback, coil_scale
        self.assist = GraspAssist(profile=profile) if profile and profile != "none" else None
        self.profile = profile or "none"
        self.origin, self.n, self.latencies_ms, self.button = None, 0, [], False

    def set_profile(self, profile):
        """Switch the Force Cushion profile at runtime (cup|egg|can|none)."""
        from ml.grasp_assist import GraspAssist
        self.profile = profile
        self.assist = GraspAssist(profile=profile) if profile and profile != "none" else None

    def process(self, packet):
        """Apply one packet; returns scene state + latency_ms (receive-to-applied compute time) + cap + button."""
        t0 = time.perf_counter()
        s = parse_state(packet)
        if s["fingers"] is None: return None
        f, cap = (self.assist.apply(s["fingers"]) if self.assist else (s["fingers"], 1.0))
        if s["wrist_position"] is not None:
            if self.origin is None: self.origin = s["wrist_position"]
            wrist = wrist_from_coil(s["wrist_position"], self.origin, self.scale)
        else:
            wrist = self.fallback(self.n * self.dt)
        self.button = s["button"]
        st = self.scene.step(f, wrist, self.dt)
        self.n += 1
        lat = (time.perf_counter() - t0) * 1000
        self.latencies_ms.append(lat)
        st.update(latency_ms=lat, cap=cap, button=self.button)
        return st

    def latency_stats(self):
        import numpy as np
        a = np.array(self.latencies_ms or [0.0])
        return {"p50": float(np.percentile(a, 50)), "p95": float(np.percentile(a, 95)), "n": int(a.size)}


def synthetic_stream(duration=4.5, hz=60, button_at=None):
    """Synthetic hand_state packets: hover, descend, close fist, lift (same script as scene.run_script). No wrist_position -> mock wrist."""
    from robot.scene import mock_fingers
    for i in range(int(duration * hz)):
        t = i / hz
        yield {"t": time.time(), "hand": "right", "fingers": mock_fingers(t, (2.0, 3.0), (99, 100)),
               "button_pressed": bool(button_at is not None and t >= button_at)}
