"""Inspire RH56 hand backend over Modbus TCP (G1 hand). Default is dry-run printing the commands.
UNVERIFIED on hardware: ANGLE_SET=1486 (6 x uint16, 0..1000), FORCE_SET=1498 (not found in any open source), SPEED_SET=1522, ANGLE_ACT=1546
(third-party README agrees on 1486/1522/1546); factory IP may be 192.168.123.211 (repo default .210); confirm with the Aalto mentors.
Live transport = a tolerant raw Modbus TCP client (default): some firmware echoes a WRONG transaction id (pymodbus then rejects the reply) and wants the
12-byte reply read after every write (third-party report, unconfirmed). `backend="pymodbus"` keeps the library path.
Safety for a one-shot test: `freeze_thumb_rot=True` (or env INSPIRE_FREEZE_THUMB_ROT=1) reads ANGLE_ACT first and then never commands the thumb rotation
(its direction is unverified); if the read fails the hand is NOT started.
Usage: make_hand("inspire", host="192.168.123.210", port=6000, dry=False)
"""
import os
import socket
import struct

from robot.hand import Hand, clamp5
from robot.retarget import Smoother, to_inspire

ANGLE_SET, FORCE_SET, SPEED_SET, ANGLE_ACT = 1486, 1498, 1522, 1546
THUMB_ROT = 5   # index in [pinky, ring, middle, index, thumb_bend, thumb_rot]


class RawModbus:
    """Minimal Modbus TCP master (FC3 read, FC16 write) that ignores the transaction id of the reply and always consumes the full reply."""

    def __init__(self, host, port, timeout=1.0):
        self.s = socket.create_connection((host, port), timeout); self.s.settimeout(timeout); self.tid = 0

    def _rx(self, n):
        b = b""
        while len(b) < n:
            c = self.s.recv(n - len(b))
            if not c: raise ConnectionError("modbus connection closed")
            b += c
        return b

    def _xchg(self, unit, pdu, fc):
        self.tid = (self.tid + 1) & 0xFFFF
        self.s.sendall(struct.pack(">HHHB", self.tid, 0, len(pdu) + 1, unit) + pdu)
        hdr = self._rx(7); body = self._rx(struct.unpack(">H", hdr[4:6])[0] - 1)      # transaction id of the reply is deliberately NOT checked
        if body[0] == (fc | 0x80): raise IOError(f"modbus exception code {body[1]}")
        if body[0] != fc: raise IOError(f"unexpected function code {body[0]}")
        return body

    def write_registers(self, addr, vals, unit):
        vals = [int(v) & 0xFFFF for v in vals]
        return self._xchg(unit, struct.pack(">BHHB", 16, addr, len(vals), 2 * len(vals)) + struct.pack(">%dH" % len(vals), *vals), 16)

    def read_registers(self, addr, n, unit):
        body = self._xchg(unit, struct.pack(">BHH", 3, addr, n), 3)
        return list(struct.unpack(">%dH" % n, body[2:2 + 2 * n]))

    def close(self):
        self.s.close()


def _write(client, addr, vals, unit):
    """pymodbus renamed the unit kwarg across versions (unit -> slave -> device_id): try each (found by the fake-server preflight test)."""
    if isinstance(client, RawModbus): return client.write_registers(addr, vals, unit)
    last = None
    for kw in ("device_id", "slave", "unit"):
        try:
            return client.write_registers(addr, vals, **{kw: unit})
        except TypeError as e:
            last = e
    raise last


class InspireHand(Hand):
    def __init__(self, host="192.168.123.210", port=6000, unit=1, dry=True, close_cap=1.0, force_limit=None, speed=500, backend="raw", freeze_thumb_rot=None):
        self.sm, self.cap, self.dry, self.unit, self.frozen = Smoother(), close_cap, dry, unit, None
        self.c = None
        if freeze_thumb_rot is None: freeze_thumb_rot = os.environ.get("INSPIRE_FREEZE_THUMB_ROT", "") not in ("", "0")
        if not dry:
            if backend == "pymodbus":
                from pymodbus.client import ModbusTcpClient
                self.c = ModbusTcpClient(host, port=port); self.c.connect()
            else:
                self.c = RawModbus(host, port)
            if freeze_thumb_rot:                  # read-only handshake BEFORE any write: garbage or an error => do not start
                self.frozen = self.read_angles()[THUMB_ROT]
                if not (0 <= self.frozen <= 1000): raise RuntimeError(f"ANGLE_ACT thumb rotation out of range: {self.frozen}")
            if force_limit is not None:  # per-finger grams, 0..1000
                _write(self.c, FORCE_SET, [int(force_limit)] * 6, unit)
            _write(self.c, SPEED_SET, [int(speed)] * 6, unit)

    def read_angles(self):
        """ANGLE_ACT (6 x uint16, 0..1000). Raw backend only."""
        if not isinstance(self.c, RawModbus): raise RuntimeError("read_angles needs the raw backend")
        return self.c.read_registers(ANGLE_ACT, 6, self.unit)

    def set_fingers(self, fingers):
        cmd = to_inspire(self.sm(clamp5(fingers)), close_cap=self.cap)
        if self.frozen is not None: cmd[THUMB_ROT] = int(self.frozen)
        if self.dry: print("inspire", cmd)
        else: _write(self.c, ANGLE_SET, cmd, self.unit)

    def close(self):
        if self.c: self.c.close()
