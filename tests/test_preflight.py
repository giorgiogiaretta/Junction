"""One-shot hardware preflight (no hardware): everything the Inspire hand and the G1 Dex3 will receive is checked offline on ALL recorded episodes.
Run: python -m pytest -q tests/test_preflight.py     A failure here means: do NOT connect to the real hand/robot."""
import json, socket, struct, sys, threading, time, pathlib
import numpy as np
ROOT = pathlib.Path(__file__).parents[1]; sys.path.insert(0, str(ROOT))
from robot.g1_dex3 import G1Dex3Retargeter
from robot import retarget

def episodes():
    idx = json.load(open(ROOT / "data/episodes/index.json"))
    for i in idx:
        z = np.load(ROOT / f"data/episodes/take_{i['take']:02d}.npz", allow_pickle=True)
        yield i, {h: z[f"{h}_fingers01"] for h in ("left", "right") if f"{h}_fingers01" in z.files}

def test_g1_dex3_all_episodes_within_filter_and_speed():
    r = G1Dex3Retargeter(); worst = 0.0; ticks = 0
    for i, f in episodes():
        r = G1Dex3Retargeter(); prev = list(r.q)
        n = min(len(v) for v in f.values())
        for t in range(n):
            q = r.step(left=f["left"][t].tolist() if "left" in f else None, right=f["right"][t].tolist() if "right" in f else None)
            assert len(q) == 14 and np.all(np.isfinite(q)) and r.bounds_ok(q), (i["take"], t)
            worst = max(worst, max(abs(a - b) for a, b in zip(q, prev))); prev = list(q); ticks += 1
    assert worst <= r.max_step + 1e-9, worst         # 3.0 rad/s at 30 Hz = 0.1 rad per tick
    assert ticks > 10000

def test_g1_dex3_edge_inputs_never_leave_bounds():
    r = G1Dex3Retargeter()
    for f in ([0] * 5, [1] * 5, [5, -3, 9, -1, 2], [float("nan")] * 5, None):
        for _ in range(40): q = r.step(left=f, right=f); assert r.bounds_ok(q) and np.all(np.isfinite(q))

def test_inspire_commands_valid_ints_and_slew(monkeypatch):
    clock = [0.0]; monkeypatch.setattr(retarget.time, "time", lambda: clock[0])   # Smoother uses wall time: simulate 30 Hz
    maxd = 0.0
    for i, f in list(episodes())[::6]:
        sm = retarget.Smoother(); prev = None
        for t in range(len(next(iter(f.values())))):
            clock[0] += 1 / 30; x = np.clip(next(iter(f.values()))[t], 0, 1).tolist()
            cmd = retarget.to_inspire(sm(x))
            assert len(cmd) == 6 and all(isinstance(v, int) and 0 <= v <= 1000 for v in cmd)
            if prev: maxd = max(maxd, max(abs(a - b) for a, b in zip(cmd, prev)))
            prev = cmd
    assert maxd <= 1000 * sm.max_rate / 30 + 2        # never jumps faster than the slew limit

class _FakeModbus(threading.Thread):
    """Minimal Modbus TCP server: records FC16/FC6 writes; answers FC3 with zeros."""
    def __init__(self):
        super().__init__(daemon=True); self.s = socket.socket(); self.s.bind(("127.0.0.1", 0)); self.s.listen(1); self.port = self.s.getsockname()[1]; self.writes = []; self.reads = []
    def run(self):
        c, _ = self.s.accept()
        while True:
            try: h = c.recv(7)
            except OSError: return
            if len(h) < 7: return
            tid, pid, ln, unit = struct.unpack(">HHHB", h); pdu = c.recv(ln - 1); fc = pdu[0]
            if fc == 16:
                addr, n, bc = struct.unpack(">HHB", pdu[1:6]); vals = struct.unpack(">%dH" % n, pdu[6:6 + bc]); self.writes.append((addr, list(vals)))
                c.sendall(struct.pack(">HHHBB", tid, 0, 6, unit, 16) + struct.pack(">HH", addr, n))
            elif fc == 3:
                addr, n = struct.unpack(">HH", pdu[1:5]); self.reads.append((addr, n)); c.sendall(struct.pack(">HHHBBB", tid, 0, 3 + 2 * n, unit, 3, 2 * n) + b"\x00" * (2 * n))
            else: c.sendall(struct.pack(">HHHBBB", tid, 0, 3, unit, fc | 0x80, 1))

def test_inspire_live_path_against_fake_modbus_server():
    """Protocol rehearsal only (framing + which registers are written). It does NOT prove the register map: confirm it with the vendor manual."""
    srv = _FakeModbus(); srv.start()
    from robot.inspire import InspireHand, ANGLE_SET, FORCE_SET, SPEED_SET
    h = InspireHand(host="127.0.0.1", port=srv.port, dry=False, force_limit=300, speed=300)
    for k in range(10): h.set_fingers([0.1 * k, 0.1 * k, 0.1 * k, 0.1 * k, 0.1 * k]); time.sleep(0.03)
    h.close(); time.sleep(0.2)
    addrs = {a for a, _ in srv.writes}
    assert addrs <= {ANGLE_SET, FORCE_SET, SPEED_SET}, addrs        # nothing else is ever written
    assert all(len(v) == 6 and all(0 <= x <= 1000 for x in v) for a, v in srv.writes if a == ANGLE_SET)
    assert srv.writes[0][0] in (FORCE_SET, SPEED_SET)               # limits are set BEFORE the first angle command


class _Fake2(threading.Thread):
    """Fake Modbus TCP server with a firmware quirk switch: wrong_tid echoes transaction id 0xABCD; ANGLE_ACT (1546) returns `act`."""
    def __init__(self, wrong_tid=False, act=(10, 20, 30, 40, 50, 700)):
        super().__init__(daemon=True); self.s = socket.socket(); self.s.bind(("127.0.0.1", 0)); self.s.listen(1); self.port = self.s.getsockname()[1]
        self.writes, self.wrong, self.act = [], wrong_tid, list(act)
    def run(self):
        c, _ = self.s.accept()
        while True:
            try: h = c.recv(7)
            except OSError: return
            if len(h) < 7: return
            tid, pid, ln, unit = struct.unpack(">HHHB", h); pdu = c.recv(ln - 1); fc = pdu[0]; t = 0xABCD if self.wrong else tid
            if fc == 16:
                addr, n, bc = struct.unpack(">HHB", pdu[1:6]); self.writes.append((addr, list(struct.unpack(">%dH" % n, pdu[6:6 + bc]))))
                c.sendall(struct.pack(">HHHBB", t, 0, 6, unit, 16) + struct.pack(">HH", addr, n))
            elif fc == 3:
                addr, n = struct.unpack(">HH", pdu[1:5]); vals = self.act if addr == 1546 else [0] * n
                c.sendall(struct.pack(">HHHBBB", t, 0, 3 + 2 * n, unit, 3, 2 * n) + struct.pack(">%dH" % n, *vals[:n]))

def test_inspire_raw_client_survives_wrong_transaction_id_echo():
    srv = _Fake2(wrong_tid=True); srv.start()
    from robot.inspire import InspireHand, ANGLE_SET
    h = InspireHand(host="127.0.0.1", port=srv.port, dry=False, speed=300)
    for k in range(5): h.set_fingers([0.1 * k] * 5); time.sleep(0.02)
    h.close(); time.sleep(0.2)
    assert [w for w in srv.writes if w[0] == ANGLE_SET] and len([w for w in srv.writes if w[0] == ANGLE_SET]) == 5

def test_inspire_freeze_thumb_rotation_after_read_only_handshake():
    srv = _Fake2(act=(1, 2, 3, 4, 5, 612)); srv.start()
    from robot.inspire import InspireHand, ANGLE_SET
    h = InspireHand(host="127.0.0.1", port=srv.port, dry=False, freeze_thumb_rot=True)
    for k in range(6): h.set_fingers([0.2 * k] * 5); time.sleep(0.02)
    h.close(); time.sleep(0.2)
    cmds = [v for a, v in srv.writes if a == ANGLE_SET]
    assert cmds and all(v[5] == 612 for v in cmds)                      # thumb rotation never moved, only the measured value is re-sent
    assert any(v[0] != cmds[0][0] for v in cmds)                        # the other joints do move

def test_inspire_freeze_refuses_to_start_if_read_fails():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(1); port = s.getsockname()[1]
    def deaf():
        c, _ = s.accept(); time.sleep(5)
    threading.Thread(target=deaf, daemon=True).start()
    from robot.inspire import InspireHand
    import pytest
    with pytest.raises(Exception): InspireHand(host="127.0.0.1", port=port, dry=False, freeze_thumb_rot=True)
