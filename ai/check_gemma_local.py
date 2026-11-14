"""Check the Gemma server on your own GPU (vLLM through an SSH tunnel) with the SAME code path the demo uses.
  export GEMMA_BASE_URL=http://127.0.0.1:8000/v1 GEMMA_MODEL=google/gemma-4-26b-a4b-it GEMMA_API_KEY=<the key you gave vllm>
  python -m ai.check_gemma_local [--photos 6]        # ping, text routing, N photos from imgs/: answer + latency
Prints median latency; no daily quota on your own GPU."""
import argparse, glob, os, statistics, time
from ai.eval_objects import make_client, recognize, prep_image, expected_label


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--photos", type=int, default=6); a = ap.parse_args()
    if not os.environ.get("GEMMA_BASE_URL"): raise SystemExit("export GEMMA_BASE_URL first (e.g. http://127.0.0.1:8000/v1 via the SSH tunnel)")
    c = make_client("gemma"); print("endpoint:", c.url, "model:", c.model)
    t = time.time(); m = c.chat([{"role": "user", "content": "Reply with: pong"}], max_tokens=200); print("ping:", repr((m.get("content") or "")[:40]), f"{time.time() - t:.2f}s")
    files = sorted(sum((glob.glob(f"imgs/{d}/*.jpg") for d in ("egg", "ball", "can")), []))
    pick = files[:: max(1, len(files) // a.photos)][: a.photos]; lat = []; ok = 0
    for p in pick:
        r = recognize(c, prep_image(open(p, "rb").read()), fast=False); lat.append(r["latency_s"]); exp = expected_label(p); ok += r["object"] == exp
        print(f"  {os.path.basename(p):14s} -> {r['object']:12s} (truth {exp}) conf={r['confidence']} {r['latency_s']:.2f}s {r.get('error') or ''}")
    print(f"{ok}/{len(pick)} right, median latency {statistics.median(lat):.2f}s")
