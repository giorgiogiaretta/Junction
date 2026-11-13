"""Jetson Nano side (Python 3.6 compatible, stdlib only).
Receives finger values over UDP from the laptop and drives servos (PCA9685 over I2C) if available.
Message format (JSON): {"fingers": [f0..f4]}  values 0..1.
Run: python3 receiver.py [--port 5005]
"""
import argparse, json, socket, time

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=5005)
a = ap.parse_args()

servo = None
try:  # optional: pip3 install adafruit-circuitpython-servokit
    from adafruit_servokit import ServoKit
    servo = ServoKit(channels=16)
    print("PCA9685 servos ready")
except Exception as e:
    print("no servo driver (dry run):", e)

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", a.port))
print("listening UDP", a.port)
last = time.time(); n = 0
while True:
    data, addr = s.recvfrom(4096)
    try:
        fingers = json.loads(data.decode())["fingers"]
    except Exception:
        continue
    n += 1
    if servo:
        for i, f in enumerate(fingers[:5]):
            servo.servo[i].angle = max(0.0, min(180.0, 180.0 * float(f)))
    if time.time() - last > 1:
        print("%d msg/s from %s fingers=%s" % (n, addr[0], [round(x, 2) for x in fingers])); n = 0; last = time.time()
