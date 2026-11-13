"""Webcam hand tracking (mediapipe) -> 5 finger values 0..1 (thumb,index,middle,ring,pinky; 0 open, 1 closed),
sent as UDP JSON {"fingers":[5],"t":time} like the glove stream. Backup/baseline vs Rokoko gloves.
Usage: python src/webcam_fingers.py [--camera 0] [--port 14043] [--show]
"""
import argparse, json, math, socket, time
import cv2, mediapipe as mp

ap = argparse.ArgumentParser()
ap.add_argument("--camera", type=int, default=0)
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=14043)
ap.add_argument("--show", action="store_true")
a = ap.parse_args()

# (MCP, PIP, TIP) landmark ids per finger; thumb uses (MCP=2, IP=3, TIP=4)
FING = [(2, 3, 4), (5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)]

def angle(p, q, r):
    v1 = (p.x - q.x, p.y - q.y, p.z - q.z); v2 = (r.x - q.x, r.y - q.y, r.z - q.z)
    d = sum(x * y for x, y in zip(v1, v2)); n = math.sqrt(sum(x * x for x in v1)) * math.sqrt(sum(x * x for x in v2))
    return math.degrees(math.acos(max(-1, min(1, d / (n + 1e-9)))))

def fingers(lm):
    out = []
    for m, p, t in FING:
        ang = angle(lm[m], lm[p], lm[t])      # ~180 straight, ~60 fully bent
        out.append(round(max(0.0, min(1.0, (170 - ang) / 100)), 3))
    return out

hands = mp.solutions.hands.Hands(max_num_hands=1, min_detection_confidence=0.6)
cap = cv2.VideoCapture(a.camera)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
while cap.isOpened():
    ok, img = cap.read()
    if not ok: break
    res = hands.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if res.multi_hand_landmarks:
        f = fingers(res.multi_hand_landmarks[0].landmark)
        sock.sendto(json.dumps({"fingers": f, "t": time.time(), "src": "webcam"}).encode(), (a.host, a.port))
        if a.show: cv2.putText(img, str(f), (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    if a.show:
        cv2.imshow("webcam_fingers (q to quit)", img)
        if cv2.waitKey(1) & 0xFF == ord("q"): break
