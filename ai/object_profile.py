"""Object label -> grasp behaviour. The camera model names the object; this table says how the hand should behave.
Numbers are TOY defaults until calibrated on the force measured in simulation (owner of the numbers: g1/ calibration). Profiles are those of
ml/grasp_assist.py (cup, egg, can, none). UNKNOWN objects get the CONSERVATIVE profile ('cup'), never full closure.
Published on UDP 127.0.0.1:14070 as {"object", "profile", "max_closure", "max_speed"} (backward compatible with {"profile"})."""
OBJECTS = {
    "egg":         {"profile": "egg", "max_closure": 0.50, "max_speed": 0.5},   # very fragile
    "stress_ball": {"profile": "can", "max_closure": 0.80, "max_speed": 1.0},   # soft: firm hold is safe
    "can":         {"profile": "can", "max_closure": 0.80, "max_speed": 1.0},   # light empty can: do not crush
}
UNKNOWN = {"profile": "cup", "max_closure": 0.65, "max_speed": 0.5}
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
        for f in ("max_closure", "max_speed", "min_hold_closure", "supported", "why"):
            if f in e: cur[f] = e[f]
        done.append(key)
    return done


load_overrides()
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
