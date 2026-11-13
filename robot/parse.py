"""Parse glove UDP messages into {"left":[5]|None,"right":[5]|None}.
Accepts bimanual {"left":[5]|null,"right":[5]|null,"t":..} (port 14053) and single-hand {"fingers":[5],"hand":"left|right","t":..} (port 14043; hand defaults to right).
"""


def parse_hands(m):
    def ok(v):
        return [float(x) for x in v[:5]] if v is not None and len(v) >= 5 else None
    if "left" in m or "right" in m:
        return {"left": ok(m.get("left")), "right": ok(m.get("right"))}
    hand = "left" if str(m.get("hand", "right")).lower().startswith("l") else "right"
    out = {"left": None, "right": None}
    out[hand] = ok(m.get("fingers"))
    return out
