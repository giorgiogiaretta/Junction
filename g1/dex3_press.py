"""Dex3 fingertip pressure on the real G1, READ ONLY (rt/dex3/{left,right}/state; this module sends nothing).

Measured 15/11 (tools/g1_windows_runner/dex3_pressure.py): 9 pads x 12 cells per hand at ~30 Hz; only 3-4 cells per pad are real
(absolute pressure in Pa, ~100 kPa at rest), the rest read a constant 30000 placeholder; rest noise ~10 Pa. Pressing the robot
fingertips by hand lit only pads 1, 3, 5 (7-30 kPa rise each), on both hands: TIP_PADS. Pads 0, 2, 4, 6, 7, 8 never moved.

Dex3Press(iface): a daemon thread polls both hands (raw non-blocking take, no Python listener in the DDS receive thread),
keeps a per-pad rest baseline (median of the first second, then re-based slowly while the caller says the hand is open),
and logs every sample to data/live/dex3_press_<time>.jsonl. rise(side) -> kPa rise per pad (9), tip(side) -> max over TIP_PADS.
"""
import json, os, threading, time

import numpy as np

ROOT_A = r"C:\Users\giorg\Desktop\aaltonomous-humanoid"
TIP_PADS = (1, 3, 5)
PLACEHOLDER = 30000.0


class Dex3Press:
    def __init__(self, iface, log_dir, hz=50.0):
        if os.path.isdir(ROOT_A + r"\third_party\cyclonedds\install\bin"):
            os.add_dll_directory(ROOT_A + r"\third_party\cyclonedds\install\bin")
        from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
        from unitree_sdk2py.idl.unitree_hg.msg.dds_ import HandState_
        ChannelFactoryInitialize(0, iface)
        self.rd, self.subs = {}, []
        for side in ("left", "right"):
            s = ChannelSubscriber(f"rt/dex3/{side}/state", HandState_); s.Init(); self.subs.append(s)
            self.rd[side] = s._ChannelSubscriber__channel._Channel__reader._Reader__reader
        os.makedirs(log_dir, exist_ok=True)
        self.path = os.path.join(log_dir, time.strftime("dex3_press_%Y%m%d_%H%M%S.jsonl"))
        self.f = open(self.path, "w")
        self.lock = threading.Lock(); self.cur, self.base, self.boot, self.t_last = {}, {}, {}, {}
        self.t0 = time.time(); self.dt = 1.0 / hz
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            for side, r in self.rd.items():
                try:
                    got = r.take(N=16)
                except Exception:
                    got = None
                if not got: continue
                m = got[-1]; t = time.time() - self.t0
                P = np.array([list(p.pressure) for p in m.press_sensor_state], float)
                if P.size == 0: continue
                pad = np.where(P != PLACEHOLDER, P, 0.0).sum(1)                  # real cells summed per pad [Pa]
                with self.lock:
                    self.cur[side] = pad; self.t_last[side] = t
                    if side not in self.base:
                        self.boot.setdefault(side, []).append(pad)
                        if len(self.boot[side]) >= 30: self.base[side] = np.median(self.boot[side], 0)
                self.f.write(json.dumps({"t": round(t, 3), "hand": side, "pressure": P.round(1).tolist(),
                                         "q": [round(ms.q, 4) for ms in m.motor_state]}) + "\n")
            self.f.flush()
            time.sleep(self.dt)

    def rise(self, side):
        """kPa rise per pad over the rest baseline, or None (no data / still learning / older than 0.3 s)."""
        with self.lock:
            if side not in self.base or time.time() - self.t0 - self.t_last.get(side, -9) > 0.3: return None
            return (self.cur[side] - self.base[side]) / 1000.0

    def tip(self, side):
        r = self.rise(side)
        return None if r is None else float(max(r[list(TIP_PADS)]))

    def rebase(self, side, alpha=0.02):
        """Hand open (no commanded closure): drift the baseline slowly toward the current reading (temperature drift)."""
        with self.lock:
            if side in self.base and side in self.cur: self.base[side] += alpha * (self.cur[side] - self.base[side])
