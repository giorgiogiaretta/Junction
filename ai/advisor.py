"""Grasp Advisor (EXPERIMENTAL): for ANY object in front of the head camera (not only egg / ball / can) a vision-language model says what it is, how fragile
it is on the egg(1.0)..ball(0.0) scale, a rough mass/size and how to handle it. The advice is turned into a CONSERVATIVE closure cap.
  python -m ai.advisor photo.jpg [--backend gemma|nemotron|gemini] [--json]
HONESTY: mass/size/fragility are the model's PRIORS (a guess from the picture), not measurements. They are evaluated against a kitchen scale and a human
fragility ranking (docs/ADVISOR.md); until then they are shown to the operator and logged, and they only ever LOWER the cap or ask for confirmation:
an unknown/uncertain object gets the conservative cap (0.68), a very fragile one asks the operator to confirm, nothing here unlocks full force."""
import argparse, json
from ai.object_profile import UNKNOWN, OBJECTS

SYSTEM = ('You help a robot hand decide how gently to grasp an object seen in one photo. Reply with ONLY a JSON object: '
          '{"object": short name, "material": short, "rigid": true|false, "fragility": number 0..1 (1 = as fragile as a raw egg, 0 = as robust as a rubber ball), '
          '"est_mass_g": number (a rough guess), "est_size_mm": [length, width, height], "handling": one short sentence, "confidence": number 0..1}. '
          "If you cannot see a single graspable object, use object \"none\" and confidence 0.")
CONSERVATIVE = UNKNOWN["max_closure"]                      # 0.68
SHARED = OBJECTS["egg"]["max_closure"]                     # 0.70: the egg/ball shared cap
CONFIRM_FRAGILITY = 0.75


def _num(x, lo, hi, default=None):
    try: x = float(x)
    except (TypeError, ValueError): return default
    return max(lo, min(hi, x))


def clean(raw):
    """Validate/clamp the model's JSON; anything malformed becomes None (-> conservative)."""
    if not isinstance(raw, dict): return None
    return {"object": str(raw.get("object", "unknown"))[:40], "material": str(raw.get("material", ""))[:40], "rigid": bool(raw.get("rigid", False)),
            "fragility": _num(raw.get("fragility"), 0.0, 1.0), "est_mass_g": _num(raw.get("est_mass_g"), 0.0, 5000.0),
            "est_size_mm": [_num(v, 1.0, 1000.0, None) for v in (raw.get("est_size_mm") or [])[:3]] if isinstance(raw.get("est_size_mm"), list) else None,
            "handling": str(raw.get("handling", ""))[:160], "confidence": _num(raw.get("confidence"), 0.0, 1.0, 0.0)}


def advice_cap(adv):
    """-> {'cap', 'needs_operator_confirm', 'why'}. Only conservative outcomes: never above the shared 0.70, never full force."""
    if not adv or adv.get("fragility") is None or adv["object"] in ("none", "unknown") or adv["confidence"] < 0.6:
        return {"cap": CONSERVATIVE, "needs_operator_confirm": True, "why": "no usable advice or low confidence: conservative cap"}
    if adv["fragility"] >= CONFIRM_FRAGILITY:
        return {"cap": CONSERVATIVE, "needs_operator_confirm": True, "why": f"very fragile ({adv['fragility']:.2f}): conservative cap, operator confirms"}
    return {"cap": SHARED, "needs_operator_confirm": False, "why": f"fragility {adv['fragility']:.2f}: shared cap (egg/ball band)"}


def advise(client, image_bytes, mime="image/jpeg", hint=""):
    """Ask the model; returns {'advice', 'cap', 'needs_operator_confirm', 'why', 'source'}. Any failure -> conservative."""
    import base64
    from ai.llm import LLMError
    content = [{"type": "text", "text": "Describe the object to be grasped. " + hint},
               {"type": "image_url", "image_url": {"url": f"data:{mime};base64," + base64.b64encode(image_bytes).decode()}}]
    try:
        msg = client.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}], max_tokens=3500)
        txt = msg.get("content") or ""; raw, _ = json.JSONDecoder().raw_decode(txt[txt.index("{"):]); adv = clean(raw); src = "model"
    except (LLMError, ValueError, KeyError) as e:
        adv, src = None, f"fallback ({type(e).__name__})"
    return dict(advice=adv, source=src, **advice_cap(adv))


if __name__ == "__main__":
    from ai.eval_objects import make_client, prep_image
    ap = argparse.ArgumentParser(); ap.add_argument("image"); ap.add_argument("--backend", default="nemotron", choices=["nemotron", "gemini", "gemma"])
    ap.add_argument("--json", action="store_true"); a = ap.parse_args()
    c = make_client("nemotron" if a.backend == "nemotron" else "gemini")
    if a.backend == "gemma": c.model = "gemma-4-26b-a4b-it"
    r = advise(c, prep_image(open(a.image, "rb").read()))
    if a.json: print(json.dumps(r, indent=1))
    else:
        d = r["advice"] or {}
        print(f"{d.get('object')} | rigid={d.get('rigid')} fragility={d.get('fragility')} mass~{d.get('est_mass_g')} g size~{d.get('est_size_mm')} mm | {d.get('handling')}")
        print(f"-> cap {r['cap']}  confirm={r['needs_operator_confirm']}  [{r['why']}]  ({r['source']})")
