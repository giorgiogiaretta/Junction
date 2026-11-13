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


def parse_state(m):
    """Full hand_state for one hand: fingers + Coil Pro wrist + glove button.
    Accepts `wrist_position` [x,y,z] (m), `wrist_quaternion` [w,x,y,z] or v1 `wrist_quat` [x,y,z,w] (both returned as xyzw),
    `button_pressed` or v1 `button`. Missing fields -> None/False. Single-hand packets only (use parse_hands for bimanual)."""
    hand = "left" if str(m.get("hand", "right")).lower().startswith("l") else "right"
    f = m.get("fingers")
    q = None
    if m.get("wrist_quaternion") is not None and len(m["wrist_quaternion"]) == 4:
        w, x, y, z = [float(v) for v in m["wrist_quaternion"]]; q = [x, y, z, w]
    elif m.get("wrist_quat") is not None and len(m["wrist_quat"]) == 4:
        q = [float(v) for v in m["wrist_quat"]]
    pos = m.get("wrist_position")
    return {"t": m.get("t"), "hand": hand, "fingers": [float(x) for x in f[:5]] if f is not None and len(f) >= 5 else None,
            "wrist_position": [float(v) for v in pos[:3]] if pos is not None and len(pos) >= 3 else None,
            "wrist_quat_xyzw": q, "button": bool(m.get("button_pressed", m.get("button", False)))}
