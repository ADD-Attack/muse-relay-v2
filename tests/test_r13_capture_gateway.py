"""B16 / F7-B: variant headers, hashes, and conditional ETags."""
import importlib.util
import io
from pathlib import Path

from PIL import Image


def png(color, size=(100, 100)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def load_gateway():
    path = Path(__file__).resolve().parents[1] / "services/gateway/app.py"
    spec = importlib.util.spec_from_file_location("b16_gateway", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TOKEN = "acceptance-token"
    module.HANDS_SECRET = "hands-secret"
    module.HANDS_URL = "http://hands.test"
    return module


class Response:
    def __init__(self, content, headers):
        self.status_code = 200
        self.content = content
        self.headers = {"Content-Type": "image/png", **headers}


def install(monkeypatch, module, table):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        content, response_headers = table[url]
        return Response(content, response_headers)

    monkeypatch.setattr(module.requests, "get", fake_get)
    return calls


def pixel(data):
    return Image.open(io.BytesIO(data)).getpixel((50, 50))


TOKEN = {"X-Relay-Token": "acceptance-token"}
GREEN = png((0, 128, 0))
BLUE = png((0, 0, 255))
RED = png((255, 0, 0))
SURFACE = {
    "X-Screen-Origin": "-100,0",
    "X-Screen-Surface": "300,100",
}


def test_routes_keep_each_variant_and_do_not_reuse_a_primary_frame(monkeypatch):
    module = load_gateway()
    base = "http://hands.test/screenshot"
    calls = install(monkeypatch, module, {
        base: (RED, {}),
        base + "?region=-100,0,100,100": (GREEN, {
            "X-Screen-Region": "-100,0,100,100",
            "X-Screen-Rect": "-100,0,100,100",
            **SURFACE,
        }),
        base + "?monitor=2": (BLUE, {
            "X-Screen-Monitor": "2",
            "X-Screen-Rect": "100,0,100,100",
            **SURFACE,
        }),
    })
    client = module.app.test_client()
    legacy = client.get("/v1/screen", headers=TOKEN)
    region = client.get("/v1/screen?region=-100,0,100,100", headers=TOKEN)
    monitor = client.get("/v1/screen?monitor=2", headers=TOKEN)
    assert pixel(legacy.data) == (255, 0, 0)
    assert pixel(region.data) == (0, 128, 0)
    assert pixel(monitor.data) == (0, 0, 255)
    assert legacy.headers["X-Screen-Variant"] == "legacy"
    assert region.headers["X-Screen-Variant"] == "region=-100,0,100,100"
    assert region.headers["X-Screen-Origin"] == "-100,0"
    assert monitor.headers["X-Screen-Monitor"] == "2"
    assert legacy.headers["ETag"] != region.headers["ETag"]
    assert region.headers["ETag"] != monitor.headers["ETag"]
    again = client.get(
        "/v1/screen?region=-100,0,100,100",
        headers={**TOKEN, "If-None-Match": region.headers["ETag"]},
    )
    assert again.status_code == 304
    assert again.data == b""
    assert again.headers["X-Screen-Variant"] == "region=-100,0,100,100"
    crossed = client.get(
        "/v1/screen?monitor=2",
        headers={**TOKEN, "If-None-Match": region.headers["ETag"]},
    )
    assert crossed.status_code == 200
    assert pixel(crossed.data) == (0, 0, 255)
    assert calls == [
        base,
        base + "?region=-100,0,100,100",
        base + "?monitor=2",
        base + "?region=-100,0,100,100",
        base + "?monitor=2",
    ]


def test_same_pixels_keep_distinct_variant_etags(monkeypatch):
    module = load_gateway()
    base = "http://hands.test/screenshot"
    install(monkeypatch, module, {
        base: (GREEN, {}),
        base + "?region=-100,0,100,100": (GREEN, {"X-Screen-Region": "-100,0,100,100"}),
    })
    client = module.app.test_client()
    legacy = client.get("/v1/screen/hash", headers=TOKEN)
    region = client.get("/v1/screen/hash?region=-100,0,100,100", headers=TOKEN)
    assert legacy.status_code == 200 and region.status_code == 200
    assert legacy.get_json()["hash"] == region.get_json()["hash"]
    assert legacy.get_json()["variant"] == "legacy"
    assert region.get_json()["variant"] == "region=-100,0,100,100"
    legacy_screen = client.get("/v1/screen", headers=TOKEN)
    region_screen = client.get(
        "/v1/screen?region=-100,0,100,100",
        headers={**TOKEN, "If-None-Match": legacy_screen.headers["ETag"]},
    )
    assert region_screen.status_code == 200
    assert region_screen.headers["ETag"] != legacy_screen.headers["ETag"]


def test_wait_names_the_variant(monkeypatch):
    module = load_gateway()
    install(monkeypatch, module, {
        "http://hands.test/screenshot?monitor=2": (BLUE, {"X-Screen-Monitor": "2"}),
    })
    response = module.app.test_client().get(
        "/v1/screen/wait?monitor=2&since=not-this&timeout=0", headers=TOKEN
    )
    body = response.get_json()
    assert response.status_code == 200
    assert body["timed_out"] is False
    assert body["variant"] == "monitor=2"
    assert body["capture"]["X-Screen-Monitor"] == "2"


def test_contradictory_monitor_header_is_not_hashed(monkeypatch):
    module = load_gateway()
    install(monkeypatch, module, {
        "http://hands.test/screenshot?monitor=2": (RED, {"X-Screen-Monitor": "0"}),
    })
    client = module.app.test_client()
    screen = client.get("/v1/screen?monitor=2", headers=TOKEN)
    hashed = client.get("/v1/screen/hash?monitor=2", headers=TOKEN)
    assert screen.status_code == 502
    assert b"PNG" not in screen.data
    assert "variant" in screen.get_json()["error"]
    assert hashed.status_code == 502
    assert "hash" not in hashed.get_json()
