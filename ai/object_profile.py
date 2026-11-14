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
