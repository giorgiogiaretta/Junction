"""Camera recorder for take.py (DJI Osmo Action 5 Pro in USB 'Webcam' mode = a UVC camera, 1080p30 MJPG; any webcam works).
Frames are timestamped with the PC wall clock at grab time, the same clock take.py uses for t_start/t_stop => no clap needed for sync
(the camera's own latency, typically 0.1-0.3 s, is not compensated: measure it once with a visible/audible event).
Use:  CAM=1 python Rokoko/src/take.py      (CAM = camera index; find it with: python Rokoko/src/cam.py --list)
Output: data/video/take_NN.mp4 + take_NN_frames.json (wall time per frame)."""
import json, os, sys, threading, time
import cv2

class CamRecorder:
    def __init__(self, index, w=1920, h=1080, fps=30):
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")); self.cap.set(3, w); self.cap.set(4, h); self.cap.set(5, fps)
        if not self.cap.isOpened(): raise RuntimeError(f"camera {index} not available")
        self.w, self.h, self.fps = int(self.cap.get(3)), int(self.cap.get(4)), fps
        self.out, self.times, self.path, self.lock, self.alive = None, [], None, threading.Lock(), True
        self.last = None; self.th = threading.Thread(target=self._run, daemon=True); self.th.start()

    def _run(self):
        while self.alive:
            ok, f = self.cap.read(); t = time.time()
            if not ok: time.sleep(0.01); continue
            self.last = f
            with self.lock:
                if self.out is not None: self.out.write(f); self.times.append(t)

    def start(self, take):
        os.makedirs("data/video", exist_ok=True); path = f"data/video/take_{take:02d}"
        with self.lock:
            self.path, self.times = path, []; self.out = cv2.VideoWriter(path + ".mp4", cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (self.w, self.h))

    def stop(self):
        with self.lock:
            if self.out is None: return None
            self.out.release(); self.out = None; json.dump(self.times, open(self.path + "_frames.json", "w"))
            return {"video": self.path + ".mp4", "frames": len(self.times)}

    def close(self): self.alive = False; self.cap.release()

if __name__ == "__main__":
    if "--list" in sys.argv:
        for i in range(6):
            c = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if c.isOpened(): print(f"index {i}: {int(c.get(3))}x{int(c.get(4))}"); c.release()
        sys.exit()
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    r = CamRecorder(idx); time.sleep(1); r.start(99); time.sleep(3); print(r.stop()); r.close()
