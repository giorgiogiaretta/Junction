"""Explainer video of what the G1 pipeline does today, rendered from the MuJoCo sim (left: outside view, right: the robot's head camera D435i).
  py -3.11 g1/sim/demo_video.py [--take 47] -> data/g1sim/demo.mp4
Parts: 1) recorded glove + Coil wrist motion replayed on the G1 arms (real data, arm IK, Aalto limits);
2) egg grasp with the per-object closure cap (0.70) vs no cap (1.0), live contact force; 3) stress ball with its cap (0.60).
All simulated: forces are model outputs with assumed gains and break threshold (see g1/sim/GRASP_REPORT.md)."""
import argparse, json, os, sys
import numpy as np, mujoco, cv2

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "g1")); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arm_ik, grasp_physics as gp
from robot.g1_dex3 import G1Dex3Retargeter

W, H, FPS = 640, 480, 30
OUT = os.path.join(ROOT, "data", "g1sim", "demo.mp4")


def text(img, lines, y0=30, color=(255, 255, 255), scale=0.6):
    for i, s in enumerate(lines):
        y = y0 + i * int(30 * scale / 0.6)
        cv2.putText(img, s, (14, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, s, (14, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)
    return img


def card(lines, n=FPS * 3):
    img = np.full((H, 2 * W, 3), 24, np.uint8)
    for i, s in enumerate(lines):
        sc = 1.0 if i == 0 else 0.7
        cv2.putText(img, s, (60, 150 + i * 50), cv2.FONT_HERSHEY_SIMPLEX, sc, (235, 235, 235) if i == 0 else (180, 200, 220), 2 if i == 0 else 1, cv2.LINE_AA)
    return [img] * n


def force_bar(img, f, thr, cap_label):
    x0, y0, w, h = 14, H - 60, W - 28, 22
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), (60, 60, 60), -1)
    fmax = 40.0; fw = int(w * min(f, fmax) / fmax)
    col = (230, 60, 60) if (thr and f > thr) else (90, 200, 110)   # frames are RGB until written
    cv2.rectangle(img, (x0, y0), (x0 + fw, y0 + h), col, -1)
    if thr: tx = x0 + int(w * thr / fmax); cv2.line(img, (tx, y0 - 6), (tx, y0 + h + 6), (255, 255, 255), 2); cv2.putText(img, f"rottura ~{thr:.0f} N (ipotesi)", (tx - 90, y0 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(img, f"forza di stretta {f:5.1f} N   {cap_label}", (x0, y0 + h + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)


def part_arms(take):
    z = np.load(os.path.join(ROOT, "data", "episodes", f"take_{take:02d}.npz"), allow_pickle=True)
    hand = str(z["active_hand"]); arm_ik.replay(take, (hand,), 0.8, False, out=os.path.join(ROOT, "data", "g1sim", "arm"))
    r = np.load(os.path.join(ROOT, "data", "g1sim", "arm", f"take_{take:02d}.npz"))
    rig = arm_ik.G1Arms(with_cam=True); rend = mujoco.Renderer(rig.m, H, W)
    cam = mujoco.MjvCamera(); cam.type = mujoco.mjtCamera.mjCAMERA_FREE; cam.lookat[:] = [0.25, -0.05, 1.0]; cam.distance, cam.azimuth, cam.elevation = 1.7, 145, -12
    frames = []
    for i in range(len(r["t"])):
        for n, v in zip(arm_ik.ARM_NAMES, r["arm_q"][i]): rig.q[n] = float(v)
        rig.apply(r["hand_q"][i]); mujoco.mj_forward(rig.m, rig.d)   # camera poses need the full forward pass
        rend.update_scene(rig.d, cam); a = rend.render().copy(); rend.update_scene(rig.d, "head_cam"); b = rend.render().copy()
        text(a, ["1. OGGI: braccia G1 guidate dai dati reali", f"   guanto + Coil, take {take} (lattina nel quadrato)", f"   t = {r['t'][i]:4.1f} s"])
        text(b, ["camera in testa (RealSense D435i)", "posizione dal modello ufficiale Unitree"])
        frames.append(np.concatenate([a, b], 1)[:, :, ::-1])
    return frames


def part_grasp(obj, closure, label, thr, settle_s=1.6, hold_s=1.2):
    rig = gp.Rig(obj, 1.5, 0.1); m, d = rig.m, rig.d; rig.place()
    rend = mujoco.Renderer(m, H, W); cam = mujoco.MjvCamera(); cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = rig.center0; cam.distance, cam.azimuth, cam.elevation = 0.42, 150, -22
    rt = G1Dex3Retargeter(max_closure=1.0); spt = int(round(1 / FPS / m.opt.timestep)); rgba0 = m.geom_rgba[rig.og].copy()
    frames, broke, fpk = [], False, 0.0
    a = m.jnt_qposadr[m.body_jntadr[rig.ob]]
    for k in range(int((settle_s + hold_s) * FPS)):
        rig.set_ctrl(rt.step(right=[0, closure, closure, 0, 0]))
        if k >= settle_s * FPS: d.mocap_pos[0][2] -= 0.01          # pedestal goes away: does the hand hold it?
        acc = 0.0
        for _ in range(spt): mujoco.mj_step(m, d); acc += rig.force()[0]
        f = acc / spt; fpk = max(fpk, f)
        if thr and f > thr: broke = True
        m.geom_rgba[rig.og] = [0.9, 0.2, 0.2, 1] if broke else rgba0
        rend.update_scene(d, cam); A = rend.render().copy(); rend.update_scene(d, "head_cam"); B = rend.render().copy()
        held = np.linalg.norm(d.qpos[a:a + 3] - rig.center0) < 0.03
        state = ("ROTTO" if broke else ("tenuto" if held else "caduto")) if k >= settle_s * FPS else "chiusura..."
        text(A, label + [f"   stato: {state}"]); force_bar(A, f, thr, f"chiusura {closure:.2f}")
        text(B, ["camera in testa: cio' che vede il robot", "qui la visione riconoscera' l'oggetto"])
        frames.append(np.concatenate([A, B], 1)[:, :, ::-1])
    m.geom_rgba[rig.og] = rgba0
    return frames, fpk, broke


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--take", type=int, default=47); a = ap.parse_args()
    fr = card(["G1 + guanti Rokoko: cosa facciamo", "Le mani del robot non sentono la forza.",
               "Guardano l'oggetto e limitano quanto si chiudono.", "Tutto in simulazione MuJoCo (modello ufficiale G1 + Dex3)."])
    fr += part_arms(a.take)
    fr += card(["2. OGGI: perche' serve sapere cos'e' l'oggetto", "Stessa presa sull'uovo, con e senza limite di chiusura.",
                "Il limite (0.70) viene dalla simulazione: tiene da 0.65, si rompe sopra 0.75."], FPS * 3)
    f1, p1, b1 = part_grasp("egg", 0.70, ["2a. uovo CON limite per oggetto (0.70)"], 20.0)
    f2, p2, b2 = part_grasp("egg", 1.00, ["2b. uovo SENZA limite (guanto chiuso del tutto)"], 20.0)
    f3, p3, b3 = part_grasp("ball", 0.60, ["2c. pallina antistress, limite 0.60"], None)
    fr += f1 + f2 + f3
    fr += card(["3. PROSSIMI PASSI", "a) raccolta con Coil: uovo, pallina, lattina, prese buone e fallite",
                "b) camera in testa -> riconosce l'oggetto -> sceglie il limite (Tommaso)",
                "c) oggetto davanti al G1 anche nella replica delle braccia", "d) prova sul G1 vero: fermo, braccia e mani, chiusura ridotta"], FPS * 5)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    w = cv2.VideoWriter(OUT, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (2 * W, H))
    for f in fr: w.write(f)
    w.release()
    print(json.dumps({"video": OUT, "seconds": round(len(fr) / FPS, 1), "egg_cap_peak_N": round(p1, 1), "egg_cap_broke": b1,
                      "egg_nocap_peak_N": round(p2, 1), "egg_nocap_broke": b2, "ball_peak_N": round(p3, 1)}))


if __name__ == "__main__":
    main()
