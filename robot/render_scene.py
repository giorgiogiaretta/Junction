"""Offscreen render of the scripted grasp (MuJoCo Renderer -> GIF). Scripted grip + mock wrist, NOT real glove data.
  python -m robot.render_scene --obj egg [--assist egg] --out docs/media/egg_cushion.gif
Frames are annotated with closure cap, contact force and BROKEN/intact via the title text in the filename only (no font deps)."""
import argparse
import imageio.v2 as imageio
import mujoco
import numpy as np
from robot.scene import Scene, mock_wrist, mock_fingers


def render(obj="egg", assist=None, out="out.gif", w=400, h=300, fps=15, duration=5.0):
    sc = Scene(obj); r = mujoco.Renderer(sc.m, h, w)
    cam = mujoco.MjvCamera(); cam.lookat[:] = (0, 0, 0.08); cam.distance = 0.55; cam.azimuth = 135; cam.elevation = -22
    ga = None
    if assist:
        from ml.grasp_assist import GraspAssist; ga = GraspAssist(profile=assist)
    frames, t, dt, nxt = [], 0.0, 1 / 60, 0.0
    while t < duration:
        f = mock_fingers(t, close=(2.0, 3.0), open_=(99, 100))
        if ga: f, _ = ga.apply(f)
        s = sc.step(f, mock_wrist(t), dt)
        if t >= nxt:
            r.update_scene(sc.d, cam); img = r.render().copy()
            if s["broken"]: img[:12, :, :] = (220, 40, 40)   # red bar = egg broken
            elif s["force"] > 0.05: img[:12, :, :] = (40, 160, 70)  # green bar = gripping intact
            frames.append(img); nxt += 1 / fps
        t += dt
    imageio.mimsave(out, frames, duration=1 / fps, loop=0)
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--obj", default="egg"); ap.add_argument("--assist", default=None); ap.add_argument("--out", required=True)
    a = ap.parse_args(); s = render(a.obj, a.assist, a.out)
    print(f"{a.out}: held={s['held']} broken={s['broken']} peak={s['peak_force']:.2f}N")
