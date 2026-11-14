"""Object label -> grasp behaviour. The camera model names the object; this table says how the hand should behave.
Numbers are TOY defaults until calibrated on the force measured in simulation (owner of the numbers: g1/ calibration). Profiles are those of
ml/grasp_assist.py (cup, egg, can, none). UNKNOWN objects get the CONSERVATIVE profile ('cup'), never full closure.
Published on UDP 127.0.0.1:14070 as {"object", "profile", "max_closure", "max_speed"} (backward compatible with {"profile"})."""
OBJECTS = {
    "egg":         {"profile": "egg", "max_closure": 0.50, "max_speed": 0.5},   # very fragile
    "stress_ball": {"profile": "can", "max_closure": 0.80, "max_speed": 1.0},   # soft: firm hold is safe
    "can":         {"profile": "can", "max_closure": 0.80, "max_speed": 1.0},   # light empty can: do not crush
}
UNKNOWN = {"profile": "cup", "max_closure": 0.68, "max_speed": 0.5}   # 0.68: still holds the egg (hold 0.65 + margin) and stays 0.07 below its break (0.75)
FILE_KEY = {"stress_ball": "ball"}   # our key -> key used in g1/object_profiles.json (owner: Giorgio, g1/)


def load_overrides(path=None):
    """Overlay per-object numbers from g1/object_profiles.json (PROVISIONAL sim numbers) when the file exists: max_closure, max_speed,
    min_hold_closure, supported (+ why). The 'profile' field and any key missing from the file keep the defaults above. Returns the keys updated."""
    import json, os
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "g1", "object_profiles.json")
    if not os.path.exists(path): return []
    try: d = json.load(open(path))
    except (OSError, ValueError): return []
    done = []
    for key, cur in OBJECTS.items():
        e = d.get(FILE_KEY.get(key, key))
        if not isinstance(e, dict) or not isinstance(e.get("max_closure"), (int, float)): continue
        for f in ("max_closure", "max_speed", "min_hold_closure", "break_closure", "supported", "why"):
            if f in e: cur[f] = e[f]
        done.append(key)
    return done


load_overrides()

# --- B3: robust caps for confusable labels -------------------------------------------------------------------------------------
# Break closure per object: from g1/sim/GRASP_REPORT.md (PROVISIONAL, assumed thresholds). None = nothing breaks. Overridable by a "break_closure" field in g1/object_profiles.json.
BREAK_CLOSURE = {"egg": 0.75, "stress_ball": None, "can": 0.50}
CONFUSABLE = (("egg", "stress_ball"),)   # pairs the recogniser really mixed up (2/20 eggs called stress ball)
MARGIN = 0.05                             # stay this far below the break closure


def _band(key):
    """(min closure that holds, closure that breaks or None) for an object, from the loaded numbers."""
    o = OBJECTS[key]; return (o.get("min_hold_closure"), o["break_closure"] if "break_closure" in o else BREAK_CLOSURE.get(key))


def robust_cap(group):
    """Single cap safe for EVERY object of a confusable group: >= the largest hold closure and <= (smallest break - MARGIN).
    Returns (cap, ok). ok=False when the bands do not intersect (no cap protects all): then the cap is the smallest break - MARGIN
    (never crush), and a drop is possible."""
    holds = [_band(k)[0] for k in group if _band(k)[0] is not None]; breaks = [_band(k)[1] for k in group if _band(k)[1] is not None]
    lo = max(holds) if holds else 0.0; hi = (min(breaks) - MARGIN) if breaks else 1.0
    return (round(hi, 2), True) if hi >= lo else (round(hi, 2), False)


def apply_robust_caps():
    """Override max_closure of every member of a confusable group with the group's shared cap (keeps the own value as max_closure_own)."""
    for group in CONFUSABLE:
        if not all(isinstance(OBJECTS[k].get("min_hold_closure"), (int, float)) for k in group if k in OBJECTS): continue  # needs the g1 numbers
        cap, ok = robust_cap(group)
        for k in group:
            OBJECTS[k].setdefault("max_closure_own", OBJECTS[k]["max_closure"]); OBJECTS[k]["max_closure"] = cap; OBJECTS[k]["robust_ok"] = ok


apply_robust_caps()

# --- Ball at FULL force (1.0), only when we are sure it is a ball -----------------------------------------------------------
FULL_FORCE = {"stress_ball": 1.0}      # closure allowed for a CONFIRMED ball (nothing breaks in the sim; the glove operator squeezes as hard as they want)
FULL_FORCE_MIN_CONF = 0.9
FULL_FORCE_MIN_AGREE = 2               # independent recognisers (e.g. Gemini + Gemma/Nemotron/CLIP probe/orange-colour check) that must say stress_ball


def cap_for_votes(label, confidence=None, agree=1, manual=False):
    """Closure cap to use now. A 'stress_ball' gets FULL force only if confidence >= 0.9 AND >= 2 recognisers agree (or the operator set it by hand
    with manual=True, e.g. `--set stress_ball`); otherwise the shared egg/ball cap (0.70). Egg and unknown objects NEVER get full force: an egg called a
    ball with full force breaks (109 N peak in the sim), so a single confident-but-wrong model must not unlock 1.0."""
    key = normalize(label); b = behaviour(label)
    if key in FULL_FORCE and b.get("supported", True):
        sure = isinstance(confidence, (int, float)) and confidence >= FULL_FORCE_MIN_CONF and agree >= FULL_FORCE_MIN_AGREE
        if manual or sure: return FULL_FORCE[key]
    return b["max_closure"]
SYNONYMS = {
    "egg": ("egg", "hen egg", "raw egg", "eggshell", "ovo"),
    "stress_ball": ("stress ball", "stress_ball", "squeeze ball", "foam ball", "ball", "sphere", "pallina"),
    "can": ("can", "soda can", "coke can", "coca-cola can", "tin", "tin can", "beverage can", "cylinder", "lattina"),
}


def normalize(label):
    """Free text -> canonical key in OBJECTS or 'other'."""
    t = (label or "").strip().lower().replace("-", " ")
    for key, words in SYNONYMS.items():
        if t in words or key in t.replace(" ", "_"):
            return key
    for key, words in SYNONYMS.items():
        if any(w in t for w in words if len(w) > 3): return key
    return "other"


def behaviour(label):
    """{'object','profile','max_closure','max_speed','known'} for a free-text label."""
    key = normalize(label)
    b = dict(OBJECTS.get(key, UNKNOWN)); b.update(object=key, known=key in OBJECTS)
    return b


# --- Full force only when we are sure (G1 live policy, Giorgio's request 2026-11-14) ------------------------------------------------
FULL_CAP = {"stress_ball": 1.0, "can": 1.0}   # objects nothing bad happens to at full closure (empty can may dent: accepted by Giorgio)
CONFIDENT = 0.9
# The model's confidence on its WRONG answers is not measured yet (Verda died before the confidence run). Until the 2 eggs called
# 'stress ball' in imgs/ are shown to get confidence < CONFIDENT, a model answer alone never unlocks full force: set True after that check.
CONFIDENCE_VALIDATED = False


def cap_for(pick):
    """Closure cap for a picker result (ai.profile_picker / ai.pick_profile dict). Returns {'object','max_closure','why'}.
    Full force (FULL_CAP) only when: source='manual' (operator --set, label = the object key or profile name), OR the model answered with
    confidence >= CONFIDENT, no safety rule softened it, and CONFIDENCE_VALIDATED. Everything else: behaviour(label) caps (egg/ball share the
    robust cap); fallback -> UNKNOWN."""
    src = pick.get("source")
    if src == "fallback": return {"object": "other", "max_closure": UNKNOWN["max_closure"], "why": "fallback: conservative"}
    key = normalize(pick.get("object") if src != "manual" else (pick.get("object_key") or pick.get("profile")))
    if key in FULL_CAP:
        if src == "manual":
            return {"object": key, "max_closure": FULL_CAP[key], "why": "operator set the object"}
        c = pick.get("confidence")
        if src == "model" and not pick.get("safety") and isinstance(c, (int, float)) and c >= CONFIDENT and CONFIDENCE_VALIDATED:
            return {"object": key, "max_closure": FULL_CAP[key], "why": f"model confident ({c})"}
    b = behaviour(key)
    return {"object": key, "max_closure": b["max_closure"], "why": "robust cap" if key in OBJECTS else "unknown: conservative"}
