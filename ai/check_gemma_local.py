"""Check the model served on your own GPU (through the SSH tunnel) with the SAME client code the demo uses.
  export GEMMA_BASE_URL=http://127.0.0.1:8000/v1 GEMMA_API_KEY=<LOCAL_KEY> GEMMA_MODEL=google/paligemma2-3b-mix-224
  python -m ai.check_gemma_local                      # --mode choice (default): 3-option question, 49/50 on our photos with PaliGemma 2
  python -m ai.check_gemma_local --mode fragile       # "Is this object fragile or rigid?": PaliGemma answers "fragile" for almost everything (useless), kept as the requested check
  python -m ai.check_gemma_local --mode objects       # JSON recognition path (chat VLMs such as Gemma 4 on vLLM; PaliGemma cannot follow the JSON prompt)
fragile mode prints the raw answer per photo with the truth we expect (egg: fragile; ball/can: rigid-ish) and the latency. It is a SANITY CHECK of the server, not an evaluation."""
import argparse, base64, glob, os, statistics, time
from ai.eval_objects import make_client, recognize, prep_image, expected_label

QUESTION = "Is this object fragile or rigid?"
EXPECT = {"egg": "fragile", "stress_ball": "rigid", "can": "rigid"}   # our own judgement for these three objects (a rubber ball is 'rigid' in this binary choice)


def ask(c, jpeg_bytes, question=QUESTION):
    content = [{"type": "text", "text": question}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode()}}]
    t = time.time(); m = c.chat([{"role": "user", "content": content}], max_tokens=24); return (m.get("content") or "").strip(), time.time() - t


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--photos", type=int, default=6); ap.add_argument("--mode", default="choice", choices=["choice", "fragile", "objects"]); a = ap.parse_args()
    if not os.environ.get("GEMMA_BASE_URL"): raise SystemExit("export GEMMA_BASE_URL first (e.g. http://127.0.0.1:8000/v1 via the SSH tunnel)")
    c = make_client("gemma"); print("endpoint:", c.url, "model:", c.model, "mode:", a.mode)
    files = sorted(sum((glob.glob(f"imgs/{d}/*.jpg") for d in ("egg", "ball", "can")), []))
    pick = files[:: max(1, len(files) // a.photos)][: a.photos]; lat = []; hit = 0
    for p in pick:
        exp = expected_label(p); jpeg = prep_image(open(p, "rb").read(), 448)
        if a.mode == "choice":
            from ai.paligemma import QUESTION, normalise
            ans, dt = ask(c, jpeg, QUESTION); lat.append(dt); ok = normalise(ans) == exp; hit += ok
            print(f"  {os.path.basename(p):14s} truth={exp:11s} answer={ans!r:20s} -> {normalise(ans):11s} {'OK' if ok else '??'} {dt:.2f}s")
        elif a.mode == "fragile":
            ans, dt = ask(c, jpeg); lat.append(dt); want = EXPECT.get(exp); ok = bool(want) and want in ans.lower(); hit += ok
            print(f"  {os.path.basename(p):14s} truth={exp:11s} expect={want:8s} answer={ans!r:30s} {'OK' if ok else '??'} {dt:.2f}s")
        else:
            r = recognize(c, jpeg, fast=False); lat.append(r["latency_s"]); hit += r["object"] == exp
            print(f"  {os.path.basename(p):14s} -> {r['object']:12s} (truth {exp}) conf={r['confidence']} {r['latency_s']:.2f}s {r.get('error') or ''}")
    print(f"{hit}/{len(pick)} as expected, median latency {statistics.median(lat):.2f}s")
