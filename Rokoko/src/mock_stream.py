"""Fake glove stream (sine finger angles) to test the pipeline without hardware."""
import json, math, socket, time
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
t0 = time.time()
while True:
    t = time.time() - t0
    fingers = [0.5 + 0.5 * math.sin(t * 2 + i) for i in range(5)]
    s.sendto(json.dumps({"mock": True, "fingers": fingers}).encode(), ("127.0.0.1", 14043))
    time.sleep(1 / 60)
