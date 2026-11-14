"""One command after a recording session: raw takes -> episodes -> arm-axes calibration (series K) -> per-take data check ->
G1 replay in sim (arms by IK + Dex3 fingers capped per object) -> report.
  py -3.11 g1/process_session.py [--since 61] [--video] [--no-episodes]
Output: data/session/report.md + report.json, replays in data/g1sim/arm/ (npz = the 30 Hz arm_q/hand_q stream the runner would get, mp4 with --video).
Takes considered: series O (object grasp), P (HandOff with object), K (axes). --since = first take of the session (default: first O/P/K take)."""
import argparse, collections, json, os, subprocess, sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "g1"))
import arm_ik

PROFILES = json.load(open(os.path.join(ROOT, "g1", "object_profiles.json")))
OBJ_KEY = {"egg": "egg", "stress_ball": "ball", "can": "can"}
OUT = os.path.join(ROOT, "data", "session")


def data_check(z, hand):
    """Fractions over the take: Coil present, wrist pose missing, finger channels flat (dead) or stuck at the ends."""
    ok = z[f"{hand}_coil_ok"]; P = z[f"{hand}_wrist_pos"]; F = z[f"{hand}_fingers01"]
    span = np.percentile(F, 95, 0) - np.percentile(F, 5, 0)
    w = []
    coil = float(np.mean(ok > 0.5)); miss = float(np.isnan(P).any(1).mean())
    if coil < 0.95: w.append(f"Coil presente solo {coil:.0%}")
    if miss > 0.05: w.append(f"posizione mancante {miss:.0%}")
    if span[1] < 0.15 and span[2] < 0.15: w.append("indice e medio quasi fermi (presa non vista dal guanto?)")
    return {"coil_present": round(coil, 3), "pose_missing": round(miss, 3), "finger_span": [round(float(x), 2) for x in span]}, w


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--since", type=int); ap.add_argument("--video", action="store_true"); ap.add_argument("--no-episodes", action="store_true")
    ap.add_argument("--scale", type=float, default=0.8); ap.add_argument("--series", default="O,P", help="grasp series to replay (test on old data: --series H)")
    a = ap.parse_args()
    if not a.no_episodes: subprocess.run([sys.executable, os.path.join(ROOT, "Rokoko", "src", "episodes.py")], cwd=ROOT, check=True)
    takes = [json.loads(l) for l in open(os.path.join(ROOT, "data", "raw", "takes.jsonl"))]
    since = a.since or next((t["take"] for t in takes if t["series"] in ("O", "P", "K")), None)
    a.series = a.series.upper()
    if since is None: sys.exit("no series O/P/K takes yet")
    sess = [t for t in takes if t["take"] >= since]
    index = {e["take"]: e for e in json.load(open(os.path.join(ROOT, "data", "episodes", "index.json")))}
    ep = lambda tk: np.load(os.path.join(ROOT, "data", "episodes", f"take_{tk:02d}.npz"), allow_pickle=True)
    hand_of = lambda t: {"R": "right", "L": "left"}.get(t.get("hand_used") or "", index.get(t["take"], {}).get("active_hand", "right"))

    K = collections.defaultdict(list)
    for t in sess:
        if t["series"] == "K" and t["take"] in index: K[hand_of(t)].append(t["take"])
    calib = {"used": "existing data/arm_calib.json or series H table"}
    if K:
        R, lens = arm_ik.calib_from_axes(dict(K)); calib = {"used": f"series K {dict(K)}", "check": lens, "hands": list(R)}

    rows, warn = [], []
    for t in sess:
        if t["series"] not in a.series.split(",") or t["take"] not in index: continue
        h = hand_of(t); z = ep(t["take"]); dc, w = data_check(z, h)
        prof = PROFILES.get(OBJ_KEY.get(t.get("object") or "", "none"), PROFILES["none"])
        r = {"take": t["take"], "series": t["series"], "object": t.get("object"), "outcome": t.get("outcome"), "hand": h, "operator": t.get("operator"),
             "video": t.get("video"), **dc, "cap": prof["max_closure"]}
        try:
            m = arm_ik.replay(t["take"], (h,), a.scale, a.video, max_closure=prof["max_closure"])
            r.update(ik_pos_err_cm=m["pos_err_cm"][h]["median"], ik_pos_err_p95_cm=m["pos_err_cm"][h]["p95"], speed_cap_pct=m["ticks_at_speed_cap_pct"],
                     clearance=m["min_clearance_cm"], in_filter=m["arm_q_in_filter"])
            if m["ticks_at_speed_cap_pct"] > 30: w.append(f"braccio al limite di velocita' {m['ticks_at_speed_cap_pct']}% del tempo (muoversi piu' lenti)")
            if isinstance(m["min_clearance_cm"], (int, float)) and m["min_clearance_cm"] < 0: w.append("collisione braccio/corpo nella replica")
        except SystemExit as e: w.append(str(e))
        if not t.get("video"): w.append("nessun video (CAM non impostata?)")
        r["warnings"] = w; rows.append(r); warn += [f"take {t['take']}: {x}" for x in w]

    table = collections.Counter((r["object"], r["outcome"]) for r in rows)
    os.makedirs(OUT, exist_ok=True)
    json.dump({"since": since, "calib": calib, "takes": rows, "counts": {f"{o}|{c}": n for (o, c), n in table.items()}}, open(os.path.join(OUT, "report.json"), "w"), indent=1)
    objs = sorted({o for o, _ in table}, key=str); outs = sorted({c for _, c in table}, key=str)
    md = [f"# Sessione dalla take {since}: {len(rows)} prese con oggetto", "", f"Calibrazione assi: {calib['used']}", ""]
    md += ["| oggetto | " + " | ".join(map(str, outs)) + " | totale |", "|---" * (len(outs) + 2) + "|"]
    for o in objs: md.append(f"| {o} | " + " | ".join(str(table[(o, c)]) for c in outs) + f" | {sum(table[(o, c)] for c in outs)} |")
    good = [r for r in rows if "ik_pos_err_cm" in r]
    if good:
        md += ["", f"Replica G1 (scala {a.scale}): errore posizione mediano {np.median([r['ik_pos_err_cm'] for r in good]):.1f} cm, "
               f"tempo al limite di velocita' mediano {np.median([r['speed_cap_pct'] for r in good]):.0f}%, comandi nei limiti: {all(r['in_filter'] for r in good)}"]
    md += ["", f"## Avvisi ({len(warn)})"] + [f"- {x}" for x in warn] if warn else ["", "Nessun avviso."]
    open(os.path.join(OUT, "report.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
