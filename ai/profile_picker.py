"""PLAN 3.4 (pre-grasp): ask the vision-language model what the target object is and which Force Cushion profile to use.
The model sees ONE frame (optional) + a short text and must call tool set_grasp_profile(object, profile). Any failure -> fallback profile.
Profiles are those of ml/grasp_assist.py: cup, egg, can, none. Called once per grasp, never inside the control loop.
SAFETY (apply_safety, on by default): failure -> 'cup' (conservative; never 'none' = no cap); confidence missing or below MIN_CONF -> never
firmer than 'cup'; a ball/sphere answer below BALL_CONF -> 'egg' profile, because on Tommaso's real photos the only errors were small white
eggs called 'stress ball' (docs/OBJECT_RECOGNITION_RESULTS.md). The rules only ever make the grip softer."""
import base64, json
from ai.llm import ChatClient, LLMError

PROFILES = ("cup", "egg", "can", "none")
TOOL = {"type": "function", "function": {"name": "set_grasp_profile",
        "description": "Choose the grip-closure profile for the object about to be grasped. Use 'egg' for very fragile, 'cup' for deformable thin-walled, 'can' for sturdy but not rigid, 'none' for rigid solid objects. Always give your confidence 0..1.",
        "parameters": {"type": "object", "properties": {"object": {"type": "string"}, "profile": {"type": "string", "enum": list(PROFILES)},
                       "reason": {"type": "string"},
                       "confidence": {"type": "number", "description": "0..1, how sure you are of the object"}}, "required": ["object", "profile"]}}}


CROP_PROMPT = "Look at this image of the hand approaching the object. Answer with the grasp force profile."


GENTLE = {"egg": 0, "cup": 1, "can": 2, "none": 3}   # lower = softer cap on finger closure
MIN_CONF, BALL_CONF = 0.6, 0.9
BALL_WORDS = ("ball", "sphere", "pallina", "round")


def _conf(x):
    try: x = float(x)
    except (TypeError, ValueError): return None
    return x if 0.0 <= x <= 1.0 else None


def apply_safety(res, min_conf=MIN_CONF, ball_conf=BALL_CONF):
    """Make a model answer softer, never firmer. Adds 'safety' (rules applied) and keeps the raw answer in 'model_profile'."""
    if res.get("source") != "model": return res
    c, prof, rules = _conf(res.get("confidence")), res["profile"], []
    obj = str(res.get("object", "")).lower()
    if any(w in obj for w in BALL_WORDS) and (c is None or c < ball_conf) and GENTLE[prof] > GENTLE["egg"]:
        prof = "egg"; rules.append(f"ball with confidence {c} < {ball_conf}: egg profile (egg-called-ball was the only real error)")
    if (c is None or c < min_conf) and GENTLE[prof] > GENTLE["cup"]:
        prof = "cup"; rules.append(f"confidence {c} < {min_conf}: capped at cup")
    return dict(res, model_profile=res["profile"], profile=prof, safety=rules) if rules else res


def pick_profile(client, image_bytes=None, hint="", fallback="cup", prompt=None, mime="image/jpeg", safety=True):
    """Returns {'object','profile','reason','source'} where source is 'model' or 'fallback' (with 'error').
    prompt=None keeps the original wording; pass CROP_PROMPT when image_bytes is a pre-grasp crop around the hand (ai/crop.py).
    The answer is always a set_grasp_profile tool call."""
    text = (prompt + " Call set_grasp_profile. " if prompt else "A robot hand is about to grasp the object on the table. Identify it and call set_grasp_profile. ") + hint
    content = [{"type": "text", "text": text}]
    if image_bytes:
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64," + base64.b64encode(image_bytes).decode()}})
    try:
        msg = client.chat([{"role": "user", "content": content}], tools=[TOOL])
        for tc in msg.get("tool_calls") or []:
            if tc["function"]["name"] == "set_grasp_profile":
                args = json.loads(tc["function"]["arguments"])
                if args.get("profile") in PROFILES:
                    res = {"object": args.get("object", "?"), "profile": args["profile"], "reason": args.get("reason", ""), "source": "model",
                           "confidence": _conf(args.get("confidence"))}
                    return apply_safety(res) if safety else res
        raise LLMError("no valid tool call")
    except (LLMError, ValueError, KeyError) as e:
        return {"object": "?", "profile": fallback, "reason": "", "source": "fallback", "error": str(e)}
