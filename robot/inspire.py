"""Inspire RH56 hand backend over Modbus TCP (G1 hand) or serial RTU.
UNVERIFIED on hardware: register ANGLE_SET=1486 (6 x uint16, 0..1000), FORCE_SET=1498, SPEED_SET=1522 per Inspire RH56 manual as remembered;
confirm with Aalto Robotics Club mentors. Needs `pip install pymodbus`. Default is dry-run printing the commands.
Usage: make_hand("inspire", host="192.168.123.210", port=6000, dry=False)
"""
from robot.hand import Hand, clamp5
from robot.retarget import Smoother, to_inspire

ANGLE_SET, FORCE_SET, SPEED_SET = 1486, 1498, 1522


class InspireHand(Hand):
    def __init__(self, host="192.168.123.210", port=6000, unit=1, dry=True, close_cap=1.0, force_limit=None, speed=500):
        self.sm, self.cap, self.dry, self.unit = Smoother(), close_cap, dry, unit
        self.c = None
        if not dry:
            from pymodbus.client import ModbusTcpClient
            self.c = ModbusTcpClient(host, port=port); self.c.connect()
            if force_limit is not None:  # per-finger grams, 0..1000
                self.c.write_registers(FORCE_SET, [int(force_limit)] * 6, slave=unit)
            self.c.write_registers(SPEED_SET, [int(speed)] * 6, slave=unit)

    def set_fingers(self, fingers):
        cmd = to_inspire(self.sm(clamp5(fingers)), close_cap=self.cap)
        if self.dry: print("inspire", cmd)
        else: self.c.write_registers(ANGLE_SET, cmd, slave=self.unit)

    def close(self):
        if self.c: self.c.close()
