"""Offline tests: pre-grasp crop (ai/crop.py), its wiring into ai/pick_profile.py, and the g1/object_profiles.json overlay (no network, no key)."""
import base64, io, json, pathlib, sys
import pytest
from PIL import Image, ImageDraw
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from ai.crop import ASSUMED_INTRINSICS, annotate, crop_around_hand, load_intrinsics, project, remap
from ai.llm import ChatClient
from ai.profile_picker import CROP_PROMPT, pick_profile

K = ASSUMED_INTRINSICS


def jpeg(w=1920, h=1080, mark=None, size=60):
    img = Image.new("RGB", (w, h), (90, 90, 90)); d = ImageDraw.Draw(img)
    if mark: d.rectangle([mark[0] - size // 2, mark[1] - size // 2, mark[0] + size // 2, mark[1] + size // 2], fill=(255, 0, 0))
    b = io.BytesIO(); img.save(b, "JPEG", quality=95); return b.getvalue()


def red_pixels(image_bytes):
    im = Image.open(io.BytesIO(image_bytes)).convert("RGB"); return sum(1 for r, g, b in im.getdata() if r > 200 and g < 80 and b < 80)


def test_projection_and_axes():
    u, v, z = project([0.1, -0.05, 0.5], K)
    assert (round(u), round(v), z) == (1152, 444, 0.5)
    assert remap([0.1, 0.05, 0.5], "x,-y,z") == [0.1, -0.05, 0.5]
    with pytest.raises(ValueError): remap([0, 0, 1], "x,y")
    with pytest.raises(ValueError): project([0, 0, 0.01], K)


def test_crop_contains_the_projected_hand():
    hand = [0.1, -0.05, 0.5]
    r = crop_around_hand(jpeg(mark=(1152, 444)), hand)
    assert r["cropped"] and r["reason"] == "ok" and r["intrinsics_assumed"]
    x0, y0, x1, y1 = r["bbox"]
    assert x0 <= 1152 <= x1 and y0 <= 444 <= y1 and (x1 - x0) == (y1 - y0) == 576    # 0.30 m * fx / depth
    assert Image.open(io.BytesIO(r["image"])).size == (576, 576)
    assert red_pixels(r["image"]) > 1500                                              # the red marker is inside the crop


def test_axes_remap_changes_the_crop():
    up = crop_around_hand(jpeg(), [0.0, 0.10, 0.6], axes="x,-y,z")                    # sensor y up -> hand above the image centre
    down = crop_around_hand(jpeg(), [0.0, 0.10, 0.6], axes="x,y,z")
    assert up["pixel"][1] < 540 < down["pixel"][1]


def test_camera_offset_is_applied():
    base = crop_around_hand(jpeg(), [0.0, 0.0, 0.5])
    off = crop_around_hand(jpeg(), [0.0, 0.0, 0.5], offset=[0.05, 0.0, 0.0])           # head origin 5 cm to the camera's right
    assert off["pixel"][0] == pytest.approx(base["pixel"][0] + 96, abs=1)


def test_window_is_clamped_inside_the_image_and_stays_square():
    r = crop_around_hand(jpeg(), [-0.45, 0.0, 0.5])                                    # u = 96, window 576 -> shifted to x0 = 0 (not shrunk)
    assert r["cropped"] and r["bbox"][0] == 0 and r["bbox"][2] - r["bbox"][0] == r["bbox"][3] - r["bbox"][1]


def test_far_hand_uses_minimum_window():
    r = crop_around_hand(jpeg(), [0.0, 0.0, 10.0], min_px=64)
    assert r["bbox"][2] - r["bbox"][0] == 64


def test_intrinsics_refer_to_another_resolution():
    big = crop_around_hand(jpeg(1920, 1080), [0.1, -0.05, 0.5])
    small = crop_around_hand(jpeg(960, 540), [0.1, -0.05, 0.5])                        # same intrinsics (1920x1080), half-size image
    assert [round(v / 2) for v in big["bbox"]] == small["bbox"]


@pytest.mark.parametrize("hand,reason", [(None, "no valid hand position"), ([float("nan"), 0, 1], "no valid hand position"), ([0, 0], "no valid hand position"),
                                         ([0, 0, -0.5], "behind"), ([0, 0, 0.0], "behind"), ([5.0, 0, 1.0], "outside")])
def test_fallbacks_return_the_full_image(hand, reason):
    src = jpeg(); r = crop_around_hand(src, hand)
    assert not r["cropped"] and reason in r["reason"] and r["bbox"] == [0, 0, 1920, 1080]
    assert Image.open(io.BytesIO(r["image"])).size == (1920, 1080)


def test_undecodable_image_is_passed_through():
    r = crop_around_hand(b"not an image", [0, 0, 1]); assert not r["cropped"] and "decode" in r["reason"] and r["image"] == b"not an image"


def test_intrinsics_file(tmp_path):
    p = tmp_path / "k.json"; p.write_text(json.dumps({"fx": 700, "fy": 700, "cx": 640, "cy": 360, "width": 1280, "height": 720}))
    k = load_intrinsics(str(p)); assert k["fx"] == 700 and k["assumed"] is False
    p.write_text(json.dumps({"fx": 700})); assert load_intrinsics(str(p))["assumed"] is True
    assert load_intrinsics(None)["assumed"] is True


def test_annotate_for_visual_check(tmp_path):
    src = jpeg(mark=(1152, 444)); r = crop_around_hand(src, [0.1, -0.05, 0.5])
    out = annotate(src, r["bbox"], r["pixel"]); assert Image.open(io.BytesIO(out)).size == (1920, 1080)
    (tmp_path / "crop_check.jpg").write_bytes(out)


# ---- wiring into pick_profile
def fake_client(sent):
    call = {"id": "1", "type": "function", "function": {"name": "set_grasp_profile", "arguments": json.dumps({"object": "egg", "profile": "egg", "reason": "r"})}}
    def tr(url, h, p, t): sent.append(p); return 200, {"choices": [{"message": {"content": None, "tool_calls": [call]}}]}
    return ChatClient("k", transport=tr, sleep=lambda s: None, rpm=6000)


def sent_image(payload):
    url = next(c["image_url"]["url"] for c in payload["messages"][0]["content"] if c["type"] == "image_url")
    return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))


def test_main_sends_only_the_crop_with_the_crop_prompt(tmp_path, capsys):
    from ai.pick_profile import main
    img = tmp_path / "head.jpg"; img.write_bytes(jpeg(mark=(1152, 444)))
    sent = []
    res = main(["--image", str(img), "--hand-in-head", "0.1", "-0.05", "0.5", "--port", "45999"], client=fake_client(sent))
    text = sent[0]["messages"][0]["content"][0]["text"]
    assert CROP_PROMPT in text and "set_grasp_profile" in text
    assert sent_image(sent[0]).size == (576, 576)
    assert res["profile"] == "egg" and res["crop"]["cropped"] and res["crop"]["intrinsics_assumed"]


def test_main_without_hand_keeps_the_original_behaviour(tmp_path):
    from ai.pick_profile import main
    img = tmp_path / "head.jpg"; img.write_bytes(jpeg()); sent = []
    res = main(["--image", str(img), "--port", "45999"], client=fake_client(sent))
    assert "about to grasp the object on the table" in sent[0]["messages"][0]["content"][0]["text"] and sent_image(sent[0]).size == (1920, 1080) and "crop" not in res


def test_main_falls_back_to_full_image_when_hand_is_behind_camera(tmp_path):
    from ai.pick_profile import main
    img = tmp_path / "head.jpg"; img.write_bytes(jpeg()); sent = []
    res = main(["--image", str(img), "--hand-in-head", "0", "0", "-1", "--port", "45999"], client=fake_client(sent))
    assert sent_image(sent[0]).size == (1920, 1080) and res["crop"]["cropped"] is False and "behind" in res["crop"]["reason"]


def test_pick_profile_prompt_param_is_backward_compatible():
    sent = []; r = pick_profile(fake_client(sent), None, "hint")
    assert r["source"] == "model" and sent[0]["messages"][0]["content"][0]["text"].endswith("call set_grasp_profile. hint")


# ---- g1/object_profiles.json overlay
def test_object_profile_overlay_follows_the_g1_file_schema(tmp_path):
    import ai.object_profile as op
    saved = {k: dict(v) for k, v in op.OBJECTS.items()}
    f = tmp_path / "object_profiles.json"
    f.write_text(json.dumps({"_note": "x", "egg": {"max_closure": 0.70, "min_hold_closure": 0.65, "max_speed": 0.5, "supported": True},
                             "ball": {"max_closure": 0.60, "min_hold_closure": 0.50, "max_speed": 1.0, "supported": True},
                             "can": {"max_closure": 0.45, "min_hold_closure": None, "max_speed": 0.5, "supported": False, "why": "squeezed out"}}))
    try:
        assert sorted(op.load_overrides(str(f))) == ["can", "egg", "stress_ball"]
        assert op.behaviour("egg")["max_closure"] == 0.70 and op.behaviour("egg")["profile"] == "egg"
        assert op.behaviour("stress ball")["max_closure"] == 0.60 and op.behaviour("can")["supported"] is False
        assert op.load_overrides(str(tmp_path / "missing.json")) == []
    finally:
        for k, v in saved.items(): op.OBJECTS[k].clear(); op.OBJECTS[k].update(v)
