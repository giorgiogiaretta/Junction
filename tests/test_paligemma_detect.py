"""Synthetic parsing and fake transport tests; no GPU/network calls."""
import base64
import io

import pytest
from PIL import Image

from ai.paligemma_detect import detect, parse_detections
from tools.paligemma_server import parse_request


def test_axis_order_and_multiple_objects():
    text = " <loc0123> <loc0456>\n<loc0789><loc1000> egg ; <loc0000><loc0000><loc1023><loc1023> orange   ball "
    assert parse_detections(text, 1024, 2047) == [
        {"label": "egg", "bbox": [456, 246, 1000, 1578]},
        {"label": "orange ball", "bbox": [0, 0, 1023, 2046]},
    ]


def test_clamp_and_round():
    assert parse_detections("<loc0000><loc0512><loc9999><loc2048> egg", 101, 51) == [
        {"label": "egg", "bbox": [50, 0, 100, 50]}]
    assert parse_detections("<loc0000><loc0000><loc1023><loc1023> egg", 1, 1)[0]["bbox"] == [0, 0, 0, 0]


@pytest.mark.parametrize("bad", [
    "egg", "<loc0000><loc0000><loc1023> egg",
    "<loc0000><loc0000><loc1023><loc1023><loc1023> egg",
    "<loc0000><loc00xx><loc1023><loc1023> egg",
    "<loc0000><loc-001><loc1023><loc1023> egg",
    "<loc000><loc0000><loc1023><loc1023> egg",
    "<loc0000><loc0000><loc1023><loc1023>   ",
    "<loc0900><loc0000><loc0100><loc1023> egg",
    "<loc0000><loc0900><loc1023><loc0100> egg",
])
def test_bad_objects_do_not_hide_valid_neighbor(bad):
    good = "<loc0000><loc0000><loc1023><loc1023> can"
    assert parse_detections(bad + " ; " + good, 20, 10) == [
        {"label": "can", "bbox": [0, 0, 19, 9]}]


@pytest.mark.parametrize("text,width,height", [(None, 10, 10), ([], 10, 10), ("", 0, 10), ("", 10, -1), ("", 1.5, 10)])
def test_invalid_input(text, width, height):
    assert parse_detections(text, width, height) == []


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def jpeg():
    stream = io.BytesIO()
    Image.new("RGB", (80, 40)).save(stream, "JPEG")
    return stream.getvalue()


def test_request_matches_server_contract(jpeg):
    client = FakeClient({"content": "<loc0000><loc0000><loc1023><loc1023> egg"})
    assert detect(client, jpeg) == [{"label": "egg", "bbox": [0, 0, 79, 39]}]
    messages, kwargs = client.calls[0]
    assert messages[0]["role"] == "user"
    assert kwargs == {"max_tokens": 128}
    prompt, image = parse_request({"messages": messages})
    assert prompt == "detect egg ; orange ball ; drink can"
    assert image.size == (80, 40)
    url = messages[0]["content"][1]["image_url"]["url"]
    assert base64.b64decode(url.split(",", 1)[1]) == jpeg


def test_custom_labels(jpeg):
    client = FakeClient({"content": ""})
    assert detect(client, jpeg, ("cup", " apple ")) == []
    assert client.calls[0][0][0]["content"][0]["text"] == "detect cup ; apple"


@pytest.mark.parametrize("response", [None, {}, [], {"content": None}, {"content": 42}, {"content": "egg"}])
def test_bad_or_stripped_response(jpeg, response):
    assert detect(FakeClient(response), jpeg) == []


def test_failures(jpeg):
    assert detect(FakeClient(error=ConnectionError("offline")), jpeg) == []
    assert detect(None, jpeg) == []
    client = FakeClient()
    assert detect(client, b"bad JPEG") == []
    for labels in ((), None, "egg", (None,), ("",), ("egg ; can",)):
        assert detect(client, jpeg, labels) == []
    assert client.calls == []
