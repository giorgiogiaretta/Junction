"""Per-take stream quality for the recorded episodes (#13).  python Rokoko/src/episode_quality.py [data/raw] [--json out.json]
Per take and hand, from the RAW glove stream (not the resampled npz): rate_hz, dt jitter (std of the inter-sample interval, ms),
dropouts (gaps > 3x the median interval), max_gap_ms, coil_ok (fraction of samples with a Coil Pro wrist position).
duration_mismatch_s = wall-clock recording length (t_stop - t_start) minus the stream span: a proxy for start/stop lag,
NOT a glove-to-PC latency measurement (that needs a shared visible/audible event, see cam.py).
"""
import json, os, sys
import numpy as np

def stream_quality(ts, has_pos, gap_factor=3.0):
    """ts: sample times in s (glove clock), has_pos: bool per sample. Returns a dict of metrics (empty stream -> n=0)."""
    ts = np.asarray(ts, float); has_pos = np.asarray(has_pos, bool)
    if len(ts) < 2: return {"n": int(len(ts))}
    dt = np.diff(ts); med = float(np.median(dt))
    gaps = dt[dt > gap_factor * med] if med > 0 else dt[:0]
    return {"n": int(len(ts)), "span_s": round(float(ts[-1] - ts[0]), 3),
            "rate_hz": round(1 / med, 1) if med > 0 else None, "jitter_ms": round(1e3 * float(dt.std()), 2),
            "dropouts": int(len(gaps)), "max_gap_ms": round(1e3 * float(dt.max()), 1),
            "coil_ok": round(float(has_pos.mean()), 3)}

def main():
    sys.path.insert(0, os.path.dirname(__file__))
    from analyze_takes import parse
    d = next((x for x in sys.argv[1:] if not x.startswith("--")), "data/raw")
    out_path = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    rows = []
    for t in (json.loads(l) for l in open(f"{d}/takes.jsonl")):
        if not os.path.exists(t["file"]): continue
        for h, r in parse(t["file"]).items():
            q = stream_quality([x[0] for x in r], [x[2] is not None for x in r])
            if q["n"] < 2: continue
            wall = t.get("t_stop", 0) - t.get("t_start", 0)
            rows.append({"take": t["take"], "series": t.get("series"), "hand": h, **q,
                         "duration_mismatch_s": round(wall - q["span_s"], 3) if wall > 0 else None})
    print(f"{'take':>4} {'ser':>3} {'hand':>5} {'n':>5} {'Hz':>6} {'jit ms':>7} {'drop':>4} {'maxgap':>7} {'coil':>5} {'ddur s':>7}")
    for q in rows:
        print(f"{q['take']:>4} {q['series'] or '':>3} {q['hand']:>5} {q['n']:>5} {q['rate_hz'] or 0:>6} {q['jitter_ms']:>7} "
              f"{q['dropouts']:>4} {q['max_gap_ms']:>7} {q['coil_ok']:>5} {q['duration_mismatch_s'] if q['duration_mismatch_s'] is not None else '':>7}")
    if rows:
        print(f"takes={len({q['take'] for q in rows})} streams={len(rows)} with dropouts={sum(q['dropouts'] > 0 for q in rows)} "
              f"median jitter={np.median([q['jitter_ms'] for q in rows]):.2f} ms  median coil_ok={np.median([q['coil_ok'] for q in rows]):.3f}")
    if out_path: json.dump(rows, open(out_path, "w"), indent=1)

if __name__ == "__main__":
    main()
