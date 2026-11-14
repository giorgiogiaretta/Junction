"""Table calibration ONLY (the --calib step of g1/sim/teleop_sim.py, without starting the teleop sim afterwards).
  py -3.11 tools/console/calib_coil.py [--hands both|right|left]
Beeps + prompts per hand; writes data/arm_calib.json ("hands" entry). Launched by the console's "Calibra (Coil)" button."""
import argparse, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "g1"), os.path.join(ROOT, "g1", "sim"), os.path.join(ROOT, "Rokoko", "src")]
os.chdir(ROOT)
from teleop_sim import table_calib  # noqa: E402
from live_sim import GloveLive  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--hands", default="both", choices=["both", "right", "left"]); a = ap.parse_args()
    hands = ["left", "right"] if a.hands == "both" else [a.hands]
    gs = {h: GloveLive(h) for h in hands}
    try:
        table_calib({h: gs[h].read for h in hands}, hands)
        print("[calib] FATTO: data/arm_calib.json aggiornato", flush=True)
    finally:
        for g in gs.values(): g.s.close()
