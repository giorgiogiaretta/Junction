"""Intent router (Gemma): a short operator utterance (typed, or text from a speech-to-text step) -> ONE strict JSON action.
  python -m ai.intent_router "Oggetto caduto, cambia in modalita' presa forte" [--object stress_ball]
Hybrid by design: (1) a LOCAL keyword fast path for safety words (stop / fermati / basta ...) that never waits for a model, (2) Gemma (default gemma-4-26b-a4b-it on the
Google API with the free-tier key; override with GEMMA_MODEL / ROUTER_BASE_URL for Featherless, Modal, Verda...) for free-form phrases, (3) validation: anything that is not
{"action": change_profile|stop|none, "target_profile": gentle|rigid|default} becomes {"action": "none"}.
SAFETY: a spoken intent never raises the cap by itself. apply_intent() only allows 'rigid' (firm grip) when the CURRENT object is the stress ball (operator override = cap_for_votes manual);
for an egg, an unknown object or the (unsupported) can the request is REFUSED and the cap stays conservative. 'stop' is never routed through a model.
Latency: Gemma-4 on the free tier is NOT ultra-fast (seconds): run it with route_async() so the simulator never waits; the fast path covers the urgent case."""
import json, os, re, threading
from ai.object_profile import behaviour, cap_for_votes, normalize

ACTIONS = ("change_profile", "stop", "none")
TARGETS = ("gentle", "rigid", "default")
STOP_WORDS = re.compile(r"\b(stop|fermati|ferma|basta|emergenza|emergency|halt|abort|annulla)\b", re.I)
SYSTEM = ('You route a spoken command of a robot-hand operator. Reply with ONLY one JSON object: {"action": "change_profile"|"stop"|"none", "target_profile": "gentle"|"rigid"|"default"|null}. '
          '"change_profile" with "gentle" = softer/more careful grip (fragile object, dropped or crushed something); "rigid" = firmer/stronger grip; "default" = go back to the normal grip for the recognised object. '
          '"stop" = stop moving. "none" = anything else. Commands may be in Italian or English. Do not explain.')


def _valid(raw):
    if not isinstance(raw, dict): return {"action": "none", "target_profile": None}
    a, t = raw.get("action"), raw.get("target_profile")
    if a == "change_profile" and t in TARGETS: return {"action": a, "target_profile": t}
    if a == "stop": return {"action": "stop", "target_profile": None}
    return {"action": "none", "target_profile": None}


def _extract(txt):
    """Gemma-4 writes a <thought>...</thought> block before the answer: take the LAST JSON object that has an "action" key."""
    dec = json.JSONDecoder(); pos = [i for i, ch in enumerate(txt) if ch == "{"]
    for i in reversed(pos):
        try: obj, _ = dec.raw_decode(txt[i:])
        except ValueError: continue
        if isinstance(obj, dict) and "action" in obj: return obj
    raise ValueError("no action JSON")


def make_client():
    from ai.eval_objects import make_client
    c = make_client("gemma"); c.timeout = 15; c.retries = 1      # own GPU when GEMMA_BASE_URL is set, else Google API
    if os.environ.get("ROUTER_BASE_URL"): c.url = os.environ["ROUTER_BASE_URL"].rstrip("/")
    return c


def route(text, client=None):
    """-> {'action','target_profile','via': 'keyword'|'model'|'fallback'}. Never raises."""
    if STOP_WORDS.search(text or ""): return {"action": "stop", "target_profile": None, "via": "keyword"}
    try:
        c = client or make_client()
        msg = c.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}], temperature=0.0, max_tokens=3000)
        raw = _extract(msg.get("content") or "")
        return dict(_valid(raw), via="model")
    except Exception:   # network, quota, bad JSON: the intent is simply not understood (the cap does not change)
        return {"action": "none", "target_profile": None, "via": "fallback"}


def route_async(text, on_done, client=None):
    """Non-blocking: runs route() in a daemon thread and calls on_done(intent). Use this from the simulator loop."""
    t = threading.Thread(target=lambda: on_done(route(text, client)), daemon=True); t.start(); return t


def apply_intent(intent, current_object):
    """Safety gate between a routed intent and the closure cap. -> {'allowed', 'cap', 'message'}."""
    key = normalize(current_object); b = behaviour(key); base = b["max_closure"]
    if intent["action"] == "stop": return {"allowed": True, "cap": 0.0, "message": "stop: hold still"}
    if intent["action"] != "change_profile": return {"allowed": False, "cap": base, "message": "no profile change"}
    t = intent["target_profile"]
    if t == "gentle": return {"allowed": True, "cap": min(base, 0.68), "message": "softer grip (conservative cap)"}
    if t == "default": return {"allowed": True, "cap": base, "message": f"back to the normal grip for {key}"}
    if key == "stress_ball" and b.get("supported", True):
        return {"allowed": True, "cap": cap_for_votes(key, manual=True), "message": "firm grip: operator override for the stress ball"}
    return {"allowed": False, "cap": min(base, 0.68), "message": f"firm grip refused for '{key}': only the stress ball may be squeezed hard"}


if __name__ == "__main__":
    import argparse, time
    ap = argparse.ArgumentParser(); ap.add_argument("text"); ap.add_argument("--object", default="stress_ball"); a = ap.parse_args()
    t0 = time.time(); i = route(a.text); print(json.dumps(i), f"({time.time() - t0:.2f}s)"); print(json.dumps(apply_intent(i, a.object)))
