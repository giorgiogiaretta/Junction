"""Record the sim head camera (instance a) with a caption, for the hand-in video. Read-only: only subscribes to
the teleimager head camera (same client as aaltonomous/cloud/snap.py) and tails the team policy server log.

    PYTHONPATH=/root/aaltonomous-humanoid python record_head.py --secs 360 --out /root/aalto_demo/run1

Grabs frames at --fps wall-clock rate, overlays wall time + the latest instruction / planner step, then encodes
H.264 with ffmpeg at fps / rtf so the motion plays back at roughly real-robot speed (the sim runs ~0.36x real time).
"""
import argparse
import os
import re
import subprocess
import time
from pathlib import Path

import cv2

LABEL = "Isaac Sim, our recoloured scene, autonomous policy"


def last_lines(path, n=200):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 40000))
            return f.read().decode("utf-8", "ignore").splitlines()[-n:]
    except OSError:
        return []


def caption_from_log(path):
    instr, step = "", ""
    for line in last_lines(path):
        m = re.search(r"instruction='(.*)'", line) or re.search(r'instruction="(.*)"', line)
        if m:
            instr, step = m.group(1), ""
        m = re.search(r"\] (execute \w+ \w+ +arm -> \w+ bin)", line)
        if m:
            step = re.sub(r"\s+", " ", m.group(1))
        if "nothing left to sort" in line:
            step = "done: nothing left to sort"
    return instr, step


def put(img, text, y, scale=0.45, color=(255, 255, 255)):
    cv2.putText(img, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secs", type=float, default=360)
    ap.add_argument("--fps", type=float, default=10)
    ap.add_argument("--rtf", type=float, default=0.36, help="sim real-time factor (playback speed-up = 1/rtf)")
    ap.add_argument("--out", default="/root/aalto_demo/run")
    ap.add_argument("--log", default="/root/fleet/server_a.log")
    ap.add_argument("--port", type=int, default=int(os.environ.get("AALTO_CAM_PORT_BASE", "55555")))
    a = ap.parse_args()
    out = Path(a.out)
    (out / "frames").mkdir(parents=True, exist_ok=True)
    from teleimager.client import TeleImageClient
    cam = TeleImageClient("head_camera", server_host="127.0.0.1", zmq_port=a.port, request_bgr=True)
    speed = 1.0 / a.rtf
    t0, n, dt = time.time(), 0, 1.0 / a.fps
    while time.time() - t0 < a.secs:
        tick = time.time()
        fr = cam.get_frame()
        if fr.bgr is not None:
            img = fr.bgr.copy()
            instr, step = caption_from_log(a.log)
            cv2.rectangle(img, (0, 0), (img.shape[1], 62), (0, 0, 0), -1)
            put(img, f"{LABEL}  |  played x{speed:.1f} (sim runs {a.rtf:.2f}x real time)", 16, 0.42, (200, 230, 255))
            put(img, (instr[:95] + "...") if len(instr) > 98 else instr, 36, 0.42)
            put(img, f"{time.strftime('%H:%M:%S', time.gmtime())} UTC   {step}", 56, 0.42, (180, 255, 180))
            cv2.imwrite(str(out / "frames" / f"{n:06d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            n += 1
        time.sleep(max(0.0, dt - (time.time() - tick)))
    print(f"{n} frames in {time.time() - t0:.0f} s", flush=True)
    fps_out = a.fps * speed
    mp4 = out / "head.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", f"{fps_out:.2f}", "-i",
                    str(out / "frames" / "%06d.jpg"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                    str(mp4)], check=True)
    print("wrote", mp4, f"({n / fps_out:.1f} s at {fps_out:.1f} fps)", flush=True)
    os._exit(0)  # teleimager client threads do not stop on their own


if __name__ == "__main__":
    main()
