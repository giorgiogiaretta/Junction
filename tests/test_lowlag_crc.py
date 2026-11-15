"""winshim/lowlag.py fast CRC must be bit-identical to unitree_sdk2py's pure-Python CRC (the robot drops lowcmd frames
with a wrong CRC). The reference below is a verbatim copy of CRC._crc_py, so this runs without the SDK (CI, Linux)."""
import importlib.util
import random
from pathlib import Path

import pytest

P = Path(__file__).resolve().parents[1] / "tools/g1_windows_runner/winshim/lowlag.py"
spec = importlib.util.spec_from_file_location("lowlag", P)
lowlag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lowlag)


def ref_crc(data):  # unitree_sdk2py/utils/crc.py CRC._crc_py
    crc, polynomial = 0xFFFFFFFF, 0x04C11DB7
    for current in data:
        bit = 1 << 31
        for _ in range(32):
            if crc & 0x80000000:
                crc = (crc << 1) & 0xFFFFFFFF
                crc ^= polynomial
            else:
                crc = (crc << 1) & 0xFFFFFFFF
            if current & bit:
                crc ^= polynomial
            bit >>= 1
    return crc


def test_fast_crc_identical():
    rng = random.Random(0)
    cases = [[], [0], [0xFFFFFFFF], [0x80000000, 1], [0x12345678] * 61]
    cases += [[rng.getrandbits(32) for _ in range(rng.randint(1, 70))] for _ in range(500)]
    for d in cases:
        assert lowlag.fast_crc(d) == ref_crc(d)


def test_patch_on_real_sdk_is_identical():
    pytest.importorskip("unitree_sdk2py.utils.crc")
    from unitree_sdk2py.utils.crc import CRC
    from unitree_sdk2py.idl.default import unitree_hg_msg_dds__LowCmd_
    rng = random.Random(1)
    msgs = []
    for _ in range(20):
        m = unitree_hg_msg_dds__LowCmd_()
        for i in range(35):
            m.motor_cmd[i].q, m.motor_cmd[i].kp = rng.uniform(-3, 3), rng.choice([40.0, 80.0, 300.0])
        msgs.append(m)
    orig = CRC._crc_py
    before = [CRC().Crc(m) for m in msgs]
    try:
        assert "fast CRC on" in lowlag.patch_crc(50) or getattr(CRC._crc_py, "_lowlag", False)
        assert [CRC().Crc(m) for m in msgs] == before
    finally:
        CRC._crc_py = orig
