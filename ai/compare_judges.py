"""TOMORROW 3.3: run the same episode judge (ai/judge.py, v1 or v2) with TWO backends on the same summaries and compare them.
  python -m ai.compare_judges --a nemotron --b gemini                  # all data/episodes/take_*.npz
  python -m ai.compare_judges --a nemotron --b gemini --limit 5        # quick smoke test
Backends (OpenAI-compatible, keys only from the environment, never committed):
  nemotron: ai.llm defaults (VERDA_INFERENCE_KEY or NVIDIA_API_KEY, LLM_BASE_URL/LLM_MODEL overrides)
  gemini:   GEMINI_API_KEY (or GOOGLE_API_KEY), Google's OpenAI-compatible endpoint, GEMINI_MODEL (default below, UNVERIFIED id)
Output: data/judge_compare.jsonl (one row per episode) + a markdown table on stdout: per-model agreement with the human labels
(precision/recall per class, ai.judge.agreement) and model-vs-model agreement (raw + Cohen's kappa over good/bad/unclear).
Human labels have no negatives yet, so precision is not measurable until failed takes are labelled (docs/JUDGE_RESULTS.md)."""
import json, os
from ai.llm import ChatClient
from ai.judge import SYSTEM, SYSTEM_V2, agreement, judge_episode, summarize_episode

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
GEMINI_MODEL = "gemini-2.5-flash"  # UNVERIFIED for this event: override with GEMINI_MODEL
VERDICTS = ("good", "bad", "unclear")


def make_client(name, **kw):
    """'nemotron' -> ai.llm defaults; 'gemini' -> Google OpenAI-compatible endpoint. A missing key gives a client that falls back cleanly."""
    if name == "nemotron": return ChatClient(**kw)
    if name == "gemini":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        c = ChatClient(api_key=key, base_url=GEMINI_URL, model=os.environ.get("GEMINI_MODEL", GEMINI_MODEL), **kw)
        c.key = key  # never send the NVIDIA/Verda key (ChatClient's env fallback) to Google; no key -> clean 'no API key' fallback
        return c
    raise ValueError(f"unknown backend {name!r} (nemotron|gemini)")


def kappa(a, b, cats=VERDICTS):
    """Cohen's kappa between two raters (lists of labels). None if fewer than 1 item; 1.0 if both are constant and identical."""
    n = len(a)
    if n == 0: return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return round((po - pe) / (1 - pe), 2) if pe < 1 else (1.0 if po == 1 else 0.0)


def compare(summaries, labels, clients, system):
    """summaries: list of dicts, labels: list of 1|0|-1, clients: {name: ChatClient}. Returns (rows, report)."""
    rows = []
    for s, l in zip(summaries, labels):
        rows.append({"episode": s.get("episode"), "series": s.get("series"), "human": l,
                     **{n: judge_episode(c, s, system) for n, c in clients.items()}})
    names = list(clients)
    v = {n: [r[n]["verdict"] for r in rows] for n in names}
    report = {"n_episodes": len(rows), "models": {n: {"agreement_with_human": agreement(v[n], labels),
              "verdicts": {k: v[n].count(k) for k in VERDICTS}, "fallbacks": sum(r[n]["source"] == "fallback" for r in rows)} for n in names}}
    if len(names) == 2:
        a, b = v[names[0]], v[names[1]]
        report["model_vs_model"] = {"raw_agreement": round(sum(x == y for x, y in zip(a, b)) / len(a), 2) if a else None, "kappa": kappa(a, b),
                                    "disagreements": [r["episode"] for r, x, y in zip(rows, a, b) if x != y]}
    return rows, report


def markdown(report):
    names = list(report["models"]); f = lambda x: "n/a" if x is None else x
    out = ["| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    m = report["models"]
    for label, get in [("verdicts good/bad/unclear", lambda r: "/".join(str(r["verdicts"][k]) for k in VERDICTS)),
                       ("fallbacks (API/parse failures)", lambda r: r["fallbacks"]),
                       ("human-positive judged good (recall good)", lambda r: f(r["agreement_with_human"]["good"]["recall"])),
                       ("precision good", lambda r: f(r["agreement_with_human"]["good"]["precision"])),
                       ("labelled pos/neg used", lambda r: "{positive}/{negative}".format(**r["agreement_with_human"]["label_balance"]))]:
        out.append(f"| {label} | " + " | ".join(str(get(m[n])) for n in names) + " |")
    if "model_vs_model" in report:
        mm = report["model_vs_model"]
        out.append(f"\nModel vs model: raw agreement {f(mm['raw_agreement'])}, Cohen's kappa {f(mm['kappa'])}, {len(mm['disagreements'])} disagreements.")
    return "\n".join(out)


if __name__ == "__main__":
    import argparse, glob
    import numpy as np
    ap = argparse.ArgumentParser(); ap.add_argument("episodes", nargs="*", default=sorted(glob.glob("data/episodes/take_*.npz")))
    ap.add_argument("--a", default="nemotron"); ap.add_argument("--b", default="gemini"); ap.add_argument("--version", type=int, default=2, choices=[1, 2])
    ap.add_argument("--limit", type=int); ap.add_argument("--out", default="data/judge_compare.jsonl"); a = ap.parse_args()
    eps = a.episodes[: a.limit] if a.limit else a.episodes
    clients = {a.a: make_client(a.a, timeout=60), a.b: make_client(a.b, timeout=60)}
    rows, report = compare([summarize_episode(p, a.version) for p in eps], [int(np.load(p, allow_pickle=True)["success"]) for p in eps],
                           clients, SYSTEM_V2 if a.version == 2 else SYSTEM)
    with open(a.out, "w") as fh:
        for r in rows: fh.write(json.dumps(r) + "\n")
    print(json.dumps(report)); print(markdown(report))
