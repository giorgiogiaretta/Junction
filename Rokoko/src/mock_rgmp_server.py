"""Fake Rokoko RGMP server (Smartgloves II, right hand) to test rgmp_client.py without hardware. Port 12276."""
import json, math, socket, struct, time
F = ["thumb", "index", "middle", "ring", "little"]
sd = {"protocol_name": "RGMP", "protocol_version": "2.0.0", "device_id": 1, "device_type": "Smartgloves II", "timestamp_epoch": "unix_epoch",
      "device_info": {"hand": "right"}, "static_data": [], "groups": [{"name": "default", "expected_rate_hz": 83.33,
      "streams": [{"data_type": "FLOAT[7]", "measure_type": "TRANSFORM", "target_frame": f + "_finger_sensor", "reference_frame": "hub"} for f in F]}]}
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); srv.bind(("127.0.0.1", 12276)); srv.listen(1)
print("mock RGMP on 12276"); c, _ = srv.accept()
j = json.dumps(sd).encode(); c.sendall(struct.pack("<II", 1, len(j)) + j); t0 = time.time()
while True:
    t = time.time() - t0; vals = []
    for i in range(5):
        a = (0.5 + 0.5 * math.sin(2 * t + i)) * 1.4; vals += [0, 0, 0, math.sin(a / 2), 0, 0, math.cos(a / 2)]
    p = struct.pack("<IIQ", 1, 0, int(time.time() * 1e6)) + struct.pack("<35f", *vals)
    c.sendall(struct.pack("<II", 2, len(p)) + p); time.sleep(1 / 83.33)
