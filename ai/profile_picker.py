"""PLAN 3.4 (pre-grasp): ask the vision-language model what the target object is and which Force Cushion profile to use.
The model sees ONE frame (optional) + a short text and must call tool set_grasp_profile(object, profile). Any failure -> fallback profile.
Profiles are those of ml/grasp_assist.py: cup, egg, can, none. Called once per grasp, never inside the control loop."""
import base64, json
from ai.llm import ChatClient, LLMError

PROFILES = ("cup", "egg", "can", "none")
TOOL = {"type": "function", "function": {"name": "set_grasp_profile",
        "description": "Choose the grip-closure profile for the object about to be grasped. Use 'egg' for very fragile, 'cup' for deformable thin-walled, 'can' for sturdy but not rigid, 'none' for rigid solid objects.",
        "parameters": {"type": "object", "properties": {"object": {"type": "string"}, "profile": {"type": "string", "enum": list(PROFILES)},
                       "reason": {"type": "string"}}, "required": ["object", "profile"]}}}


CROP_PROMPT = "Look at this image of the hand approaching the object. Answer with the grasp force profile."


def pick_profile(client, image_bytes=None, hint="", fallback="none", prompt=None, mime="image/jpeg"):
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
                    return {"object": args.get("object", "?"), "profile": args["profile"], "reason": args.get("reason", ""), "source": "model"}
        raise LLMError("no valid tool call")
    except (LLMError, ValueError, KeyError) as e:
        return {"object": "?", "profile": fallback, "reason": "", "source": "fallback", "error": str(e)}
