"""One-screen health table of the recogniser backends (what is reachable RIGHT NOW, latency) so a dead endpoint is known before a live take.
  python -m ai.health [--image imgs/egg/egg-001.jpg]
Needs the same env as the demo (VERDA_INFERENCE_KEY, GEMINI_API_KEY / GEMMA_*, PALIGEMMA_BASE_URL + PALIGEMMA_API_KEY). Prints OK/FAIL, latency, answer per backend and the breaker state."""
import argparse, glob, time
from ai.recognize import BACKENDS, collect, _STATE
from ai.eval_objects import prep_image

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--image"); a = ap.parse_args()
    path = a.image or (sorted(glob.glob("imgs/egg/*.jpg")) or [None])[0]
    if not path: raise SystemExit("give --image (no imgs/egg/ photo found)")
    img = prep_image(open(path, "rb").read()); print("photo:", path)
    for v in collect(img, list(BACKENDS), timeout=20.0):
        print(f"  {v['name']:10s} {'OK  ' if v['ok'] else 'FAIL'} {v['object']:12s} {v.get('latency_s')}s {v.get('error') or ''}")
    print("breakers:", {k: s for k, s in _STATE.items() if s["fails"]})
