"""End-to-end in simulation (B4 bridge): photo -> object label -> grasp profile (cap) -> G1 Dex3 MuJoCo grasp -> held / broken, with and without the cap.
  python -m robot.e2e_g1 --image imgs/egg/egg-001.jpg --recogniser nemotron|gemini        # label from a vision model (needs its key)
  python -m robot.e2e_g1 --label egg                                                    # label given (no model, no key)
  python -m robot.e2e_g1 --true egg --label stress_ball                                 # what if the recogniser mixes egg and ball up
Uses g1/sim/grasp_physics.py (Giorgio) READ-ONLY: same G1 Dex3 model, retargeter and contact physics. Needs data/g1sim/assets_g1 (run g1/sim/g1_sim.py once).
ASSUMED/PROVISIONAL: servo gains, object sizes and break thresholds (egg 20 N): force numbers are model outputs, only the closure levels transfer. Right hand only, fixed base.
The can is vision-only (supported=false in g1/object_profiles.json): no grasp is simulated for it."""
import argparse, json, os, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "g1", "sim"))
from ai.object_profile import behaviour

SIM_KEY = {"egg": "egg", "stress_ball": "ball", "can": "can"}


def label_from_image(path, recogniser):
    from ai.eval_objects import make_client, recognize, prep_image
    r = recognize(make_client(recogniser), prep_image(open(path, "rb").read()))
    if not r["ok"]: raise SystemExit(f"recogniser '{recogniser}' failed: {r.get('error')} (use --label to skip the model)")
    return r["object"], r


def simulate(true_obj, label, kp=1.5, kv=0.1, render_dir=None):
    """Returns dict with the behaviour chosen for `label`, and the result of gripping `true_obj` capped (cap) and uncapped (closure 1.0)."""
    import grasp_physics as gp
    b = behaviour(label); key = SIM_KEY.get(true_obj)
    out = {"label": label, "true": true_obj, "cap": b["max_closure"], "profile": b["profile"], "supported": b.get("supported", True)}
    if key is None or key == "can" and not behaviour("can").get("supported", True):
        out["note"] = "true object not graspable by the G1 in this posture (vision only) or unknown: no grasp simulated"; return out
    rig = gp.Rig(key, kp, kv); brk = gp.OBJECTS[key]["brk"]
    for name, closure in (("capped", min(1.0, b["max_closure"])), ("uncapped", 1.0)):
        r = rig.run(closure); r["broken"] = bool(brk is not None and r["force_peak_N"] > brk); r["closure"] = closure; out[name] = r
        if render_dir:
            os.makedirs(render_dir, exist_ok=True); rig.render(os.path.join(render_dir, f"{true_obj}_as_{label}_{name}.png"), closure)
    return out


def verdict(res):
    if "capped" not in res: return res.get("note", "")
    c, u = res["capped"], res["uncapped"]
    state = lambda r: ("HELD" if r["held"] else "DROPPED") + (" + BROKEN" if r["broken"] else " intact")
    return f"cap {res['cap']:.2f}: {state(c)} ({c['force_peak_N']} N peak) | no cap (1.00): {state(u)} ({u['force_peak_N']} N peak)"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--image"); ap.add_argument("--recogniser", default="nemotron", choices=["nemotron", "gemini"])
    ap.add_argument("--label", help="skip the model: object label (egg, stress_ball, can)"); ap.add_argument("--true", help="real object (default: same as label)")
    ap.add_argument("--render-dir", default="data/e2e"); ap.add_argument("--json"); a = ap.parse_args()
    if a.label: label, meta = a.label, {}
    elif a.image: label, meta = label_from_image(a.image, a.recogniser)
    else: raise SystemExit("give --image or --label")
    true = a.true or label
    res = simulate(true, label, render_dir=a.render_dir); res["model"] = meta
    print(f"label={label} true={true} profile={res['profile']} supported={res['supported']}\n{verdict(res)}")
    if a.json: json.dump(res, open(a.json, "w"), indent=1)
