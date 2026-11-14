"""Evaluate object recognition on photos (head camera / GoPro / phone): accuracy, confusion, latency, and whether the resulting grasp profile is right.
  python -m ai.eval_objects data/photos [--backend nemotron|gemini] [--limit N] [--out report.md]
Photo names: <object>_<anything>.jpg|png with <object> in {egg, stress_ball, can, other} (e.g. egg_01.jpg, stress_ball_head_3.png).
Keys: nemotron -> VERDA_INFERENCE_KEY; gemini -> GEMINI_API_KEY (+ GEMINI_MODEL, UNVERIFIED default). Each key is only sent to its own endpoint."""
import argparse, base64, collections, glob, json, os, statistics, time
from ai.llm import ChatClient, LLMError
from ai.object_profile import behaviour, normalize

LABELS = ("egg", "stress_ball", "can", "other")
SYSTEM = ('You see the scene in front of a robot hand. Name the single object that the hand should grasp. Reply with ONLY JSON '
          '{"object": "egg"|"stress_ball"|"can"|"other", "confidence": number 0..1}. "stress_ball" = soft squeezable ball; "can" = drink can; '
          '"other" = anything else or nothing graspable.')
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


def make_client(backend):
    if backend == "gemini":
        return ChatClient(api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"), base_url=GEMINI_URL,
                          model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"), timeout=60)  # model id UNVERIFIED
    return ChatClient(timeout=60)


def recognize(client, image_bytes, mime="image/jpeg", fast=True):
    """-> {'object', 'confidence', 'latency_s', 'ok'}. fast=True disables thinking on the Nemotron endpoint (0.4 s instead of seconds)."""
    content = [{"type": "text", "text": "Which object should be grasped?"},
               {"type": "image_url", "image_url": {"url": f"data:{mime};base64," + base64.b64encode(image_bytes).decode()}}]
    t = time.time()
    try:
        extra = {"chat_template_kwargs": {"enable_thinking": False}} if (fast and "datacrunch" in client.url) else None
        msg = client.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}], max_tokens=1500 if not extra else 200, extra=extra)
        txt = (msg.get("content") or ""); r = json.loads(txt[txt.index("{"): txt.rindex("}") + 1])
        return {"object": normalize(r.get("object")), "confidence": r.get("confidence"), "latency_s": time.time() - t, "ok": True}
    except (LLMError, ValueError, KeyError) as e:
        return {"object": "other", "confidence": None, "latency_s": time.time() - t, "ok": False, "error": str(e)}


def expected_label(path):
    stem = os.path.basename(path).rsplit(".", 1)[0].lower()
    for l in sorted(LABELS, key=len, reverse=True):
        if stem.startswith(l): return l
    return None


def evaluate(client, folder, limit=None, recog=recognize):
    files = sorted(sum((glob.glob(os.path.join(folder, e)) for e in ("*.jpg", "*.jpeg", "*.png")), []))
    rows = []
    for p in files[: limit or None]:
        exp = expected_label(p)
        if exp is None: continue
        mime = "image/png" if p.lower().endswith(".png") else "image/jpeg"
        r = recog(client, open(p, "rb").read(), mime); r.update(file=os.path.basename(p), expected=exp)
        r["profile_ok"] = behaviour(r["object"])["profile"] == behaviour(exp)["profile"]; rows.append(r)
    return rows


def report(rows, backend=""):
    n = len(rows)
    if not n: return "no photos found"
    acc = sum(r["object"] == r["expected"] for r in rows) / n
    conf = collections.Counter((r["expected"], r["object"]) for r in rows)
    lat = [r["latency_s"] for r in rows]
    out = [f"# Object recognition ({backend}), {n} photos", f"- accuracy: {acc:.0%}  |  grasp-profile correct: {sum(r['profile_ok'] for r in rows) / n:.0%}",
           f"- latency: median {statistics.median(lat):.2f} s, max {max(lat):.2f} s  |  failed calls: {sum(not r['ok'] for r in rows)}", "", "| expected \\ predicted | " + " | ".join(LABELS) + " |", "|---|" + "---|" * len(LABELS)]
    for e in LABELS: out.append(f"| {e} | " + " | ".join(str(conf[(e, p)]) for p in LABELS) + " |")
    wrong = [r for r in rows if r["object"] != r["expected"]]
    if wrong: out += ["", "Wrong: " + ", ".join(f"{r['file']}->{r['object']}" for r in wrong)]
    return "\n".join(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("folder"); ap.add_argument("--backend", default="nemotron", choices=["nemotron", "gemini"])
    ap.add_argument("--limit", type=int); ap.add_argument("--out"); a = ap.parse_args()
    rows = evaluate(make_client(a.backend), a.folder, a.limit); md = report(rows, a.backend); print(md)
    if a.out: open(a.out, "w").write(md + "\n")
