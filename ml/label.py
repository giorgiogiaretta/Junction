"""Human labels for takes (stored in data/raw/takes.jsonl).
  python ml/label.py 12 y                        grasp success (y/n)
  python ml/label.py 12 y --obj 0.1 0.0 0.02     also pick-object position, Coil frame metres (x y z)
  python ml/label.py --obj-series A 0.1 0 0.02   same obj_pos for every take of a series
  python ml/label.py --list
"""
import json, sys
LOG = "data/raw/takes.jsonl"
ts = [json.loads(l) for l in open(LOG)]
a = sys.argv[1:]
if not a or a[0] == "--list":
    for t in ts: print(t["take"], t["series"], "success=%s" % t.get("success"), "obj_pos=%s" % t.get("obj_pos"))
    sys.exit()
if a[0] == "--obj-series":
    p = [float(x) for x in a[2:5]]
    for t in ts:
        if t["series"] == a[1].upper(): t["obj_pos"] = p
else:
    n = int(a[0].lower().replace("take_", "")); t = next(x for x in ts if x["take"] == n)
    if len(a) > 1 and a[1].lower() in ("y", "n"): t["success"] = a[1].lower() == "y"
    if "--obj" in a: i = a.index("--obj"); t["obj_pos"] = [float(x) for x in a[i + 1:i + 4]]
open(LOG, "w").write("".join(json.dumps(t) + "\n" for t in ts))
