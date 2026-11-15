"""Illustration renders for the submission video/deck (MuJoCo, G1 + Dex3 assets already in the repo). NOT results, only visuals.
  python3 robot/render_illustration.py --what hand  -> data/video/dex3_turn_illustration_raw.mp4 (10 s, 360 deg, black background, 1920x1080, 30 fps)
  python3 robot/render_illustration.py --what table -> data/video/g1_table_three_objects.png (G1 with egg, ball and can on the table, no number labels)
Needs data/g1sim/assets_g1 (run g1/sim/g1_sim.py once). Re-encode to H.264 with ffmpeg afterwards (see the commands printed at the end)."""
import argparse, os, sys
import cv2, mujoco, numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "g1", "sim"))
import demo_cv as DC   # same scene builder as the simulation demo

W, H, FPS, SECS = 1920, 1080, 30, 10


def label(img, text="illustration"):
    cv2.putText(img, text, (28, H - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (200, 200, 205), 2, cv2.LINE_AA)
    return img


def hand_video(out):
    demo = DC.Demo(); m, d = demo.m, demo.d
    demo.place("stress_ball")
    for n in demo.names:                       # a relaxed, slightly curled hand reads better than a flat one
        d.qpos[demo.jq[n]] = 0.25 * (1 if "thumb" not in n else 0.6)
    mujoco.mj_forward(m, d)
    palm = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "right_wrist_yaw_link")   # the Dex3 palm geometry hangs on this link
    hbodies = set(demo.hand_bodies) | {palm}
    hand = sorted(hbodies)
    centre = np.mean([d.xpos[b] for b in hand], axis=0)
    hand_geoms = np.array([m.geom_bodyid[g] in hbodies for g in range(m.ngeom)])
    r = mujoco.Renderer(m, H, W); cam = mujoco.MjvCamera()
    cam.lookat[:] = centre; cam.distance, cam.elevation = 0.55, -18
    vw = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    n = FPS * SECS
    for i in range(n):
        cam.azimuth = 360.0 * i / n
        r.update_scene(d, cam); rgb = r.render().copy()
        r.enable_segmentation_rendering(); r.update_scene(d, cam); seg = r.render().copy(); r.disable_segmentation_rendering()
        gid = seg[:, :, 0]; keep = (seg[:, :, 1] == int(mujoco.mjtObj.mjOBJ_GEOM)) & (gid >= 0)
        keep[keep] = hand_geoms[gid[keep]]
        rgb[~keep] = 0                                         # only the hand, on black
        vw.write(label(np.ascontiguousarray(rgb[:, :, ::-1])))
    vw.release(); r.close(); print("wrote", out)


def table_png(out):
    demo = DC.Demo(); m, d = demo.m, demo.d
    demo.place("stress_ball")                                    # ball at the work spot, egg and can parked on the table
    r = mujoco.Renderer(m, H, W); cam = mujoco.MjvCamera()
    cam.lookat[:] = [0.22, -0.02, DC.D.PELVIS_Z + 0.08]; cam.distance, cam.azimuth, cam.elevation = 1.05, 196, -16
    r.update_scene(d, cam); img = r.render().copy(); r.close()
    cv2.imwrite(out, img[:, :, ::-1]); print("wrote", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--what", choices=["hand", "table"], required=True)
    a = ap.parse_args(); os.makedirs(os.path.join(ROOT, "data", "video"), exist_ok=True)
    if a.what == "hand": hand_video(os.path.join(ROOT, "data", "video", "dex3_turn_illustration_raw.mp4"))
    else: table_png(os.path.join(ROOT, "data", "video", "g1_table_three_objects.png"))
