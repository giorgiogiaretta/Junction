"""Robot hand abstraction. Contract: set_fingers([5 floats 0..1]) (0=open, 1=closed).
Order: thumb, index, middle, ring, pinky.
Backends: inspire (G1/Inspire RH56, see inspire.py), sim (MuJoCo), serial (Arduino, line "f0,f1,f2,f3,f4\n" as 0-180 ints), pca9685 (I2C servos), dry (print).
Usage: from robot.hand import make_hand; h = make_hand("sim"); h.set_fingers([0,.5,1,1,0])
"""
import time


def clamp5(fingers):
    f = [max(0.0, min(1.0, float(x))) for x in list(fingers)[:5]]
    return f + [0.0] * (5 - len(f))


class Hand:
    def set_fingers(self, fingers):
        raise NotImplementedError

    def close(self):
        pass


class DryHand(Hand):
    def set_fingers(self, fingers):
        print("fingers", [round(x, 2) for x in clamp5(fingers)])


class SerialHand(Hand):
    """Arduino: sketch parses 'a,b,c,d,e\\n' (0-180) and writes servos."""
    def __init__(self, port, baud=115200):
        import serial  # pip install pyserial
        self.s = serial.Serial(port, baud, timeout=0.1)
        time.sleep(2)  # Arduino resets on open

    def set_fingers(self, fingers):
        a = ",".join(str(int(180 * x)) for x in clamp5(fingers))
        self.s.write((a + "\n").encode())

    def close(self):
        self.s.close()


class PCA9685Hand(Hand):
    """Servos on PCA9685 channels 0-4 (run on Jetson/RPi)."""
    def __init__(self, channels=(0, 1, 2, 3, 4)):
        from adafruit_servokit import ServoKit
        self.kit = ServoKit(channels=16)
        self.ch = channels

    def set_fingers(self, fingers):
        for c, x in zip(self.ch, clamp5(fingers)):
            self.kit.servo[c].angle = 180.0 * x


def make_hand(kind="dry", **kw):
    if kind == "sim":
        from robot.sim import SimHand
        return SimHand(**kw)
    if kind == "g1dex3":
        return G1Dex3Hand(**kw)
    if kind == "inspire":
        from robot.inspire import InspireHand
        return InspireHand(**kw)
    return {"dry": DryHand, "serial": SerialHand, "pca9685": PCA9685Hand}[kind](**kw)


class G1Dex3Hand(Hand):
    """DRY backend: computes the 14-value G1 Dex3 hand_q (robot/g1_dex3.py) and keeps it in `last_q`; no DDS output yet. hand = 'left'|'right' = which side this glove drives."""
    def __init__(self, hand="right", verbose=False):
        from robot.g1_dex3 import G1Dex3Retargeter
        self.rt, self.hand, self.verbose, self.last_q = G1Dex3Retargeter(), hand, verbose, None

    def set_fingers(self, fingers):
        f = clamp5(fingers)
        self.last_q = self.rt.step(left=f if self.hand == "left" else None, right=f if self.hand == "right" else None)
        if self.verbose: print("g1dex3 hand_q", [round(v, 2) for v in self.last_q])
