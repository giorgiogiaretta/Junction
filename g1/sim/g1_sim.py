"""One-command lightweight G1 Dex3 check in MuJoCo (kinematic, no physics, no Isaac).
  python g1/sim/g1_sim.py [--take 51] [--out data/g1sim] [--no-video]
What it does:
  1. fetches the official G1 29-DoF + Dex3 model (unitreerobotics/xr_teleoperate, assets/g1, Apache-2.0, pinned to the Aalto rev) into data/g1sim/assets_g1 if missing;
  2. runs robot.g1_dex3.G1Dex3Retargeter (unmodified) at closure 0/10/50/100 % per hand and renders side+palm views (png);
  3. replays data/episodes/take_NN.npz fingers01 through the retargeter and renders an mp4;
  4. checks, per Dex3 joint, whether the commanded 'closed' direction really closes the finger/thumb in the URDF geometry -> g1/sim/REPORT.md.
Kinematic only: it validates the URDF axes/limits against the retargeter signs, NOT the motor direction/zero offsets of the physical robot."""
import argparse, os, shutil, subprocess, sys, json
import numpy as np, cv2, mujoco

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from robot.g1_dex3 import G1Dex3Retargeter

XR_REV = "817fb00c63cde15e5f24a0f8fa08e1e33ed89d3b"   # pinned by aaltonomous/cloud/setup_instance.sh (XRTELEOP_REV)
XR_URL = "https://github.com/unitreerobotics/xr_teleoperate.git"
XML = "g1_body29_hand14.xml"
FINGERS = ("thumb", "index", "middle")
DIST = {"thumb": 2, "index": 1, "middle": 1}   # distal link index per finger
OBJ = mujoco.mjtObj


def ensure_assets(out):
    dst = os.path.join(out, "assets_g1")
    if os.path.exists(os.path.join(dst, XML)): return dst
    tmp = os.path.join(out, "_xr_tmp"); shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
    run = lambda *a: subprocess.run(["git", *a], cwd=tmp, check=True, capture_output=True)
    run("init", "-q"); run("remote", "add", "origin", XR_URL); run("fetch", "-q", "--depth", "1", "origin", XR_REV)
    run("checkout", "-q", "FETCH_HEAD", "--", "assets/g1")
    shutil.copytree(os.path.join(tmp, "assets", "g1"), dst); shutil.rmtree(tmp, ignore_errors=True)
    return dst


class Rig:
    """One MuJoCo model + helpers to pose a hand, measure fingertip geometry and render it."""
    def __init__(self, assets):
        self.m = m = mujoco.MjModel.from_xml_path(os.path.join(assets, XML))
        m.vis.global_.offwidth = 720; m.vis.global_.offheight = 720
        self.d = mujoco.MjData(m)
        self.jadr = {mujoco.mj_id2name(m, OBJ.mjOBJ_JOINT, i): m.jnt_qposadr[i] for i in range(m.njnt)}
        self.tip_local, self.palm_geoms, self.keep = {}, {}, {}
        for side in ("left", "right"):
            wy = self.bid(f"{side}_wrist_yaw_link"); self.keep[side] = self._subtree(wy)
            self.palm_geoms[side] = [g for g in range(m.ngeom) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH
                                     and (mujoco.mj_id2name(m, OBJ.mjOBJ_MESH, m.geom_dataid[g]) or "") == f"{side}_hand_palm_link"]
            for f in FINGERS: self.tip_local[side, f] = self._tip(self.bid(f"{side}_hand_{f}_{DIST[f]}_link"))
        self.rgba0 = m.geom_rgba.copy()
        self.base = {s: self._base_for(s) for s in ("left", "right")}

    def bid(self, n): return mujoco.mj_name2id(self.m, OBJ.mjOBJ_BODY, n)

    def _subtree(self, root):
        m = self.m; ids = {root}
        for b in range(m.nbody):
            p = b
            while p != 0 and p not in ids: p = m.body_parentid[p]
            if p in ids: ids.add(b)
        return ids

    def _tip(self, body):
        """Fingertip = distal-link mesh vertex farthest from the link origin (body frame)."""
        m = self.m; best, bp = -1, None
        for g in range(m.ngeom):
            if m.geom_bodyid[g] != body or m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH: continue
            mid = m.geom_dataid[g]; a, n = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
            R = np.zeros(9); mujoco.mju_quat2Mat(R, m.geom_quat[g]); v = m.mesh_vert[a:a + n] @ R.reshape(3, 3).T + m.geom_pos[g]
            k = np.argmax(np.linalg.norm(v, axis=1))
            if np.linalg.norm(v[k]) > best: best, bp = np.linalg.norm(v[k]), v[k].copy()
        return bp

    def _base_for(self, side):
        """Free-joint qpos that puts the wrist_yaw frame at a canonical pose: fingers +x, curl plane = world x-z, palm facing +z (up)."""
        m, d = self.m, self.d
        d.qpos[:] = 0; d.qpos[3] = 1; mujoco.mj_forward(m, d)
        b = self.bid(f"{side}_wrist_yaw_link"); Rh = d.xmat[b].reshape(3, 3).copy(); ph = d.xpos[b].copy()
        ex, ey, ez = np.eye(3)
        Rd = np.stack([ex, -ez, ey], 1) if side == "left" else np.stack([ex, ez, -ey], 1)   # columns = images of local x,y,z
        T = Rd @ Rh.T; Rb = T @ d.xmat[1].reshape(3, 3)   # body 1 = pelvis (free joint)
        q = np.zeros(4); mujoco.mju_mat2Quat(q, Rb.flatten())
        return np.concatenate([T @ (d.xpos[1] - ph), q])

    def pose(self, side, hand_q, names):
        d = self.d; d.qpos[:] = 0; d.qpos[:7] = self.base[side]
        for n, v in zip(names, hand_q): d.qpos[self.jadr[n]] = v
        mujoco.mj_forward(self.m, d)

    def tip(self, side, f):
        b = self.bid(f"{side}_hand_{f}_{DIST[f]}_link")
        return self.d.xpos[b] + self.d.xmat[b].reshape(3, 3) @ self.tip_local[side, f]

    def palm_center(self, side):
        m, d = self.m, self.d; pts = []
        for g in self.palm_geoms[side]:
            mid = m.geom_dataid[g]; a, n = m.mesh_vertadr[mid], m.mesh_vertnum[mid]
            pts.append(m.mesh_vert[a:a + n] @ d.geom_xmat[g].reshape(3, 3).T + d.geom_xpos[g])
        return np.concatenate(pts).mean(0)

    def contacts(self, side):
        """(count, max penetration m) between hand-subtree geoms (parent-child pairs are skipped by MuJoCo)."""
        m, d = self.m, self.d; pen = 0.0; n = 0
        for c in d.contact[:d.ncon]:
            if m.geom_bodyid[c.geom1] in self.keep[side] and m.geom_bodyid[c.geom2] in self.keep[side] and c.dist < -1e-3: pen = max(pen, -c.dist); n += 1
        return n, pen

    # ---- rendering ----
    def hide_others(self, side):
        m = self.m; m.geom_rgba[:] = self.rgba0
        for g in range(m.ngeom):
            if m.geom_bodyid[g] not in self.keep[side]: m.geom_rgba[g, 3] = 0

    def render(self, side, rend, kind):
        cam = mujoco.MjvCamera(); cam.type = mujoco.mjtCamera.mjCAMERA_FREE
        cam.lookat[:] = self.palm_center(side) + np.array([0.04, 0, 0]); cam.distance = 0.30
        cam.azimuth, cam.elevation = (90, 0) if kind == "side" else (90, -75)   # side: x right, z up; palm: from above, palm faces camera
        rend.update_scene(self.d, cam); return rend.render()


def closed_end(j): lo, hi = j["filter"]; return lo if abs(lo) > abs(hi) else hi
def open_val(j): lo, hi = j["filter"]; return min(max(0.0, lo), hi)


def settle(rt, left, right, n=60):
    for _ in range(n): q = rt.step(left=left, right=right)
    return q


def label(img, txt):
    img = np.ascontiguousarray(img); cv2.putText(img, txt, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA); return img


def split(names, q):
    return (("left", q[:7], names[:7]), ("right", q[7:], names[7:]))


def render_levels(rig, out):
    names = [j["joint"] for j in G1Dex3Retargeter().joints]
    levels = [("open", 0.0, 1.0), ("10pct", 0.1, 1.0), ("50pct", 0.5, 1.0), ("100pct", 1.0, 1.0), ("preflight_cap10", 1.0, 0.1)]
    rend = mujoco.Renderer(rig.m, 360, 360); rows = {"left": [], "right": []}
    for name, c, cap in levels:
        rt = G1Dex3Retargeter(max_closure=cap); q = settle(rt, [c] * 5, [c] * 5)
        for side, qs, nm in split(names, q):
            rig.hide_others(side); rig.pose(side, qs, nm)
            img = np.hstack([label(rig.render(side, rend, "side"), f"{side} {name} side"), label(rig.render(side, rend, "palm"), f"{side} {name} palm")])
            rows[side].append(img); cv2.imwrite(os.path.join(out, f"{side}_{name}.png"), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    for side in rows: cv2.imwrite(os.path.join(out, f"{side}_levels.png"), cv2.cvtColor(np.vstack(rows[side]), cv2.COLOR_RGB2BGR))
    rend.close()


def render_take(rig, take, out):
    names = [j["joint"] for j in G1Dex3Retargeter().joints]
    z = np.load(os.path.join(ROOT, "data", "episodes", f"take_{take:02d}.npz"), allow_pickle=True)
    L, R = z["left_fingers01"], z["right_fingers01"]; n = len(z["t"]); rt = G1Dex3Retargeter(max_closure=1.0)
    rend = mujoco.Renderer(rig.m, 360, 360); tmp = os.path.join(out, f"take_{take:02d}_raw.mp4")
    vw = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), 30, (1440, 360))
    for i in range(n):
        q = rt.step(left=L[i].tolist(), right=R[i].tolist()); panels = []
        for side, qs, nm in split(names, q):
            rig.hide_others(side); rig.pose(side, qs, nm); f = (L if side == "left" else R)[i]
            panels += [label(rig.render(side, rend, "side"), f"{side} take {take} t={i/30:.1f}s idx={f[1]:.2f}"), rig.render(side, rend, "palm")]
        vw.write(cv2.cvtColor(np.hstack(panels), cv2.COLOR_RGB2BGR))
    vw.release(); rend.close(); final = os.path.join(out, f"take_{take:02d}.mp4")
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-c:v", "libx264", "-pix_fmt", "yuv420p", final], check=True); os.remove(tmp)
    else: os.replace(tmp, final)
    return final, float(L.max()), float(R.max()), n


# ------------------------------------------------------------------ direction checks
def snapshot(rig, side):
    pc = rig.palm_center(side); t = {f: rig.tip(side, f) for f in FINGERS}
    return {"palm": {f: float(np.linalg.norm(t[f] - pc)) for f in FINGERS},
            "pinch": float(np.linalg.norm(t["thumb"] - 0.5 * (t["index"] + t["middle"]))), "cont": rig.contacts(side)}


def sweep(rig, side, qbase, names, jname, tgt, steps=24):
    """Move ONE joint from its base value to tgt, the others stay at qbase."""
    res = []; i = names.index(jname)
    for a in np.linspace(0, 1, steps + 1):
        q = list(qbase); q[i] = qbase[i] + a * (tgt - qbase[i]); rig.pose(side, q, names); res.append(snapshot(rig, side))
    return res


def verdict(delta_mm, tol=3.0): return "si" if delta_mm < -tol else ("no" if delta_mm > tol else "incerto")


def check_directions(rig):
    J = G1Dex3Retargeter(max_closure=1.0).joints; rows = []; mirror = {}
    for side, sl in (("left", slice(0, 7)), ("right", slice(7, 14))):
        js = J[sl]; names = [j["joint"] for j in js]; qopen = [open_val(j) for j in js]; half = list(qopen)
        for j in js:   # reference pose for thumb tests: index/middle half closed, thumb open
            if "thumb" not in j["joint"]: half[names.index(j["joint"])] = open_val(j) + 0.5 * (closed_end(j) - open_val(j))
        for j in js:
            n = j["joint"]; fing = n.split("_")[2]; k = int(n.split("_")[3]); tgt = closed_end(j)
            sw = sweep(rig, side, qopen if fing != "thumb" else half, names, n, tgt); a, b = sw[0], sw[-1]
            dp = (b["palm"][fing] - a["palm"][fing]) * 1000; dpin = (b["pinch"] - a["pinch"]) * 1000
            vals = [s["palm"][fing] for s in sw]; mono = bool(all(np.diff(vals) <= 1e-5))
            row = {"joint": n, "closed_cmd": round(tgt, 3), "d_tip_palm_mm": round(dp, 1), "d_pinch_mm": round(dpin, 1), "monotonic": mono}
            if fing != "thumb":
                row["verdict"] = verdict(dp)
            elif k == 0:
                lo, hi = j["filter"]; sw2 = sweep(rig, side, half, names, n, min(max(-tgt, lo), hi))
                row["note"] = f"opposite sign ({-tgt:+.2f}): d pinch {(sw2[-1]['pinch'] - sw2[0]['pinch']) * 1000:+.1f} mm"
                row["verdict"] = "n/d (never commanded, held at 0)"
            else:
                v1, v2 = verdict(dp), verdict(dpin)
                row["verdict"] = "si" if v1 == v2 == "si" else ("no" if "si" not in (v1, v2) and "no" in (v1, v2) else "incerto")
            rows.append(row); mirror[side, fing, k] = (dp, dpin)
    mm = {f"{f}_{k}": round(max(abs(mirror['left', f, k][0] - mirror['right', f, k][0]), abs(mirror['left', f, k][1] - mirror['right', f, k][1])), 2)
          for f in FINGERS for k in range(3 if f == "thumb" else 2)}
    full = {}
    for c in (0.0, 0.5, 1.0):
        q = settle(G1Dex3Retargeter(max_closure=1.0), [c] * 5, [c] * 5)
        for side, sl in (("left", slice(0, 7)), ("right", slice(7, 14))):
            rig.pose(side, q[sl], [j["joint"] for j in J[sl]]); s = snapshot(rig, side)
            full[side, c] = {"pinch_mm": round(s["pinch"] * 1000, 1), "pen_mm": round(s["cont"][1] * 1000, 1), "n": s["cont"][0],
                             "tp": "/".join(str(round(s["palm"][f] * 1000, 1)) for f in FINGERS)}
    return rows, mm, full


def write_report(rows, mm, full, info, path):
    L = ["# G1 Dex3 simulation report (MuJoCo, kinematic)", "",
         "**Summary:** " + ("all commanded joints close in the right direction in the URDF geometry (si: " + str(sum(r['verdict'] == 'si' for r in rows)) + "/" + str(len(rows)) + "), left and right are exact mirrors for thumb_1/2." if all(r['verdict'].startswith(('si', 'n/d')) for r in rows) else "WRONG/UNCERTAIN DIRECTIONS FOUND: " + ", ".join(r['joint'] for r in rows if not r['verdict'].startswith(('si', 'n/d')))) + " This is URDF geometry only, not the physical robot.", "",
         "Generated by `python g1/sim/g1_sim.py`. Model: official G1 29-DoF + Dex3 (`g1_body29_hand14.xml`, same geometry as the URDF) from unitreerobotics/xr_teleoperate at the rev pinned by the Aalto setup script (Apache-2.0).",
         "Retargeter under test: `robot/g1_dex3.py` (unmodified); `closed` = the filter bound farthest from 0 (what the retargeter drives to at closure 1).", "",
         "## Method",
         "- Per joint: sweep ONLY that joint from open to its `closed` bound; other joints open (thumb tests: index/middle at 50 %).",
         "- Finger joints: correct if fingertip-to-palm-centre distance decreases (tip = distal mesh vertex farthest from the link origin).",
         "- Thumb joints: correct if BOTH thumb tip->palm centre and thumb tip->midpoint(index, middle tips) decrease (pinch).",
         "- thumb_0 is never commanded (held at 0): informational, with the opposite-sign pinch change.",
         "- verdict: si (decrease > 3 mm), no (increase > 3 mm), incerto (|change| < 3 mm, or the two thumb metrics disagree).", "",
         "## Joint -> does increasing closure close it?", "", "| joint | closed cmd (rad) | d tip-palm (mm) | d pinch (mm) | monotonic | verdict | note |", "|---|---|---|---|---|---|---|"]
    for r in rows: L.append(f"| {r['joint']} | {r['closed_cmd']} | {r['d_tip_palm_mm']} | {r['d_pinch_mm']} | {'y' if r['monotonic'] else 'n'} | **{r['verdict']}** | {r.get('note', '')} |")
    L += ["", "## Left/right mirror consistency", "Max |left - right| of the metric deltas (mm). ~0 means the retargeter's L/R sign choice is the exact geometric mirror.", "",
          "| joint | max diff (mm) |", "|---|---|"] + [f"| {k} | {v} |" for k, v in mm.items()]
    L += ["", "## Full retargeter pose (all five inputs at closure c, cap 1.0)", "",
          "| hand | c | thumb tip to mid(index,middle) tip (mm) | tip-palm thumb/index/middle (mm) | max self-penetration (mm) | contacts > 1 mm |", "|---|---|---|---|---|---|"]
    for (side, c), v in full.items(): L.append(f"| {side} | {c} | {v['pinch_mm']} | {v['tp']} | {v['pen_mm']} | {v['n']} |")
    if info: L += ["", "## Replay", f"take_{info[0]:02d}: {info[4]} ticks, max closure left {info[2]:.2f} / right {info[3]:.2f}; video `{info[1]}` (not committed, regenerate with the command above)."]
    L += ["", "## What this does NOT prove",
          "- It checks URDF geometry (axes, limits, zero pose) against the retargeter signs. It cannot see motor-direction or zero-offset differences on the physical robot; the Aalto doc says left-negative / right-positive was measured on the real robot.",
          "- Kinematic only: no object contact, no PD/torque dynamics, no hand-object interaction.",
          "- A thumb `si` means the commanded direction moves the thumb tip towards the palm and the fingertips in the URDF. It does not prove that the resulting posture is a good grasp.", ""]
    open(path, "w", encoding="utf-8").write("\n".join(L))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--take", type=int, default=51); ap.add_argument("--out", default=os.path.join(ROOT, "data", "g1sim"))
    ap.add_argument("--no-video", action="store_true"); a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True); rig = Rig(ensure_assets(a.out))
    rows, mm, full = check_directions(rig); render_levels(rig, a.out); info = None
    if not a.no_video:
        f, lm, rm, n = render_take(rig, a.take, a.out); info = (a.take, os.path.relpath(f, ROOT), lm, rm, n)
    rp = os.path.join(ROOT, "g1", "sim", "REPORT.md"); write_report(rows, mm, full, info, rp)
    print("report:", rp, "| images/video:", a.out)
    for r in rows: print(f"{r['joint']:28s} {r['verdict']:34s} tip-palm {r['d_tip_palm_mm']:7.1f} mm  pinch {r['d_pinch_mm']:7.1f} mm")


if __name__ == "__main__":
    main()
