"""G1_LOWLAG=1 (opt-in, loaded by sitecustomize.py): performance-only patches for the runner process on Windows.

Root cause of the ~1 s arm lag on the real robot (docs/ARM_DELAY.md): on Windows unitree_sdk2py's CRC falls back to a
pure-Python bit loop (`CRC._crc_py`, the C library is Linux-only): 2 ms per rt/lowcmd message at 250 Hz = half a core
holding the GIL. Starved of the GIL, the DDS receive thread (it runs the Python Dex3-state listeners synchronously)
drains its 1 MiB socket buffer slower than the robot fills it, so every rt/lowstate sample the arm controller reads is
~1 s old, and xr_teleoperate's per-tick velocity clip (anchored on that stale measured q) lets the arm advance only
<= 0.12 rad per staleness period: the staircase seen in the logs.

Patches (NO safety rule changes: joint limits, the runner SafetyFilter caps, keep-out, watchdog, the 30 rad/s clip in
robot_arm.py and every other check are untouched; only how fast the same numbers are computed):
  1. CRC._crc_py -> zlib-based CRC-32/MPEG-2, bit-identical. Self-check against the original on random inputs and on a
     real hg LowCmd at startup; on ANY mismatch the original stays in place.
  2. OPTIONAL, off by default: sys.setswitchinterval(G1_LOWLAG_SWITCH seconds, e.g. 0.001; Python default 0.005).
     Offline it added nothing on top of 1 (lowlag_bench.py), so it stays opt-in.
"""
import os
import random
import struct
import sys
import zlib

_REV8 = bytes(int(f"{i:08b}"[::-1], 2) for i in range(256))


def _rev32(x):
    return (_REV8[x & 0xFF] << 24) | (_REV8[(x >> 8) & 0xFF] << 16) | (_REV8[(x >> 16) & 0xFF] << 8) | _REV8[x >> 24]


def fast_crc(data):
    """== CRC._crc_py(data) for a list of uint32 words: CRC-32/MPEG-2 (poly 0x04C11DB7, init 0xFFFFFFFF, no reflection,
    no xorout) over each word's bytes big-endian. zlib.crc32 is the reflected CRC-32 with xorout 0xFFFFFFFF: feed it the
    bit-reversed bytes and bit-reverse its un-xored result."""
    y = struct.pack(f">{len(data)}I", *data).translate(_REV8)
    return _rev32((zlib.crc32(y) & 0xFFFFFFFF) ^ 0xFFFFFFFF)


def patch_crc(n_random=300):
    from unitree_sdk2py.utils import crc as crcmod
    orig = crcmod.CRC._crc_py
    if getattr(orig, "_lowlag", False):
        return "already patched"
    c = crcmod.CRC()
    rng = random.Random(12345)
    cases = [[], [0], [0xFFFFFFFF], [0x80000000, 1]]
    cases += [[rng.getrandbits(32) for _ in range(rng.randint(1, 80))] for _ in range(n_random)]
    try:  # the exact message the arm controller sends
        from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_
        m = unitree_hg_msg_dds__LowCmd_()
        for i in range(35):
            m.motor_cmd[i].q, m.motor_cmd[i].kp, m.motor_cmd[i].kd = rng.uniform(-2, 2), 80.0, 3.0
        cases.append(c._CRC__PackHGLowCmd(m))  # already the uint32 word list (__Trans applied inside)
    except Exception:
        pass
    bad = sum(orig(c, d) != fast_crc(d) for d in cases)
    if bad:
        return f"NOT applied: {bad}/{len(cases)} self-check mismatches (original CRC kept)"

    def _crc_py(self, data):
        return fast_crc(data)
    _crc_py._lowlag = True
    crcmod.CRC._crc_py = _crc_py
    return f"fast CRC on ({len(cases)} self-checks equal)"


def apply():
    msgs = []
    if sys.platform == "win32":
        try:
            msgs.append(patch_crc())
        except Exception as e:  # SDK missing / changed: leave everything as it was
            msgs.append(f"CRC patch skipped ({e!r})")
    sw = float(os.environ.get("G1_LOWLAG_SWITCH", "0") or "0")
    if sw > 0:
        sys.setswitchinterval(sw)
        msgs.append(f"GIL switch interval {sw * 1e3:.1f} ms")
    print("[G1_LOWLAG] " + "; ".join(msgs), flush=True)
    return msgs
