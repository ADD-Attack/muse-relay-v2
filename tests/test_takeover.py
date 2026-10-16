"""WP0b — takeover interlock: the person at the keyboard always wins."""

from conftest import FakeClock

SECRET_HDR = {"X-Secret": "s" * 32}
TOKEN_HDR = {"X-Relay-Token": "t" * 32}
YIELD_ERROR = "user active — control yielded"


# ---------------------------------------------------------------- unit


def _takeover(hands, pos, **kw):
    clock = FakeClock()
    events = []
    t = hands.Takeover(
        get_position=lambda: pos[0],
        quiet_seconds=10,
        clock=clock,
        on_change=lambda state, reason: events.append((state, reason)),
        **kw,
    )
    return t, clock, events


def test_agent_moves_never_trip(hands):
    pos = [(0, 0)]
    t, clock, events = _takeover(hands, pos)
    t.check_cursor()  # baseline
    for i in range(20):
        with t.agent_action():
            pos[0] = (i * 37 % 1900, i * 53 % 1000)
            t.check_cursor()  # a poll landing mid-move must not count
        t.check_cursor()
        clock.advance(0.5)
    assert not t.is_yielded()
    assert events == []


def test_physical_move_yields_then_quiet_period_returns_control(hands):
    pos = [(10, 10)]
    t, clock, events = _takeover(hands, pos)
    t.check_cursor()
    pos[0] = (400, 300)  # the person grabs the mouse
    t.check_cursor()
    assert t.is_yielded()
    assert t.state()["control"] == "yielded"
    assert t.state()["reason"] == "mouse moved"
    clock.advance(9.5)
    assert t.is_yielded()
    clock.advance(1.0)
    assert not t.is_yielded()
    assert [e[0] for e in events] == ["yielded", "agent"]


def test_continued_local_input_extends_the_yield(hands):
    pos = [(0, 0)]
    t, clock, _ = _takeover(hands, pos)
    t.local_input("key press")
    clock.advance(8)
    t.local_input("key press")
    clock.advance(8)
    assert t.is_yielded()  # 8s since the LAST input, not the first
    clock.advance(2.5)
    assert not t.is_yielded()


def test_jitter_within_tolerance_is_ignored(hands):
    pos = [(500, 500)]
    t, _, _ = _takeover(hands, pos)
    t.check_cursor()
    pos[0] = (502, 499)
    t.check_cursor()
    assert not t.is_yielded()


def test_fallback_detector_suppresses_agent_input_only(hands):
    pos = [(0, 0)]
    t, clock, _ = _takeover(hands, pos, suppress_seconds=0.3)
    t.check_last_input(1)  # baseline
    with t.agent_action():
        t.check_last_input(2)  # agent's own SendInput
    t.check_last_input(3)  # inside the suppression window
    assert not t.is_yielded()
    clock.advance(0.5)
    t.check_last_input(4)  # past the window: that was the person
    assert t.is_yielded()


# ---------------------------------------------------------------- hands HTTP


def test_hands_act_refused_with_409_while_yielded(hands, fake_gui):
    client = hands.app.test_client()
    t = hands.TAKEOVER
    t.check_cursor()
    for i in range(20):
        r = client.post("/move", json={"x": 50 + i * 10, "y": 60 + i * 5}, headers=SECRET_HDR)
        assert r.status_code == 200, r.get_json()
        t.check_cursor()
    assert client.get("/status", headers=SECRET_HDR).get_json()["control"] == "agent"

    fake_gui.pos = (900, 700)  # physical mouse move
    t.check_cursor()
    for path, body in (("/move", {"x": 1, "y": 1}), ("/click", {"x": 1, "y": 1}),
                       ("/type", {"text": "hi"}), ("/key", {"key": "enter"}),
                       ("/scroll", {"clicks": 2})):
        r = client.post(path, json=body, headers=SECRET_HDR)
        assert r.status_code == 409, path
        data = r.get_json()
        assert data["ok"] is False and data["error"] == YIELD_ERROR
        assert int(r.headers["Retry-After"]) >= 1
    assert client.get("/screenshot", headers=SECRET_HDR).status_code == 200  # read-only OK
    st = client.get("/status", headers=SECRET_HDR).get_json()
    assert st["control"] == "yielded"

    hands.clock.advance(10.5)
    r = client.post("/move", json={"x": 5, "y": 5}, headers=SECRET_HDR)
    assert r.status_code == 200


def test_auth_still_comes_first_while_yielded(hands, fake_gui):
    client = hands.app.test_client()
    hands.TAKEOVER.local_input("key press")
    r = client.post("/move", json={"x": 1, "y": 1}, headers={"X-Secret": "wrong" * 8})
    assert r.status_code == 401


def test_typing_stops_mid_string_on_takeover(hands, fake_gui):
    client = hands.app.test_client()
    typed = []

    def on_write(ch):
        typed.append(ch)
        if len(typed) == 3:
            hands.TAKEOVER.local_input("key press")  # person starts typing

    fake_gui.on_write = on_write
    r = client.post("/type", json={"text": "hello world"}, headers=SECRET_HDR)
    assert r.status_code == 409
    data = r.get_json()
    assert data["typed"] == 3 and data["total"] == 11
    assert "".join(typed) == "hel"


# ---------------------------------------------------------------- via gateway


def test_gateway_passes_409_through_and_reports_control(hands, fake_gui, gateway, serve_app):
    gateway.HANDS_URL = serve_app(hands.app)
    gateway.HANDS_SECRET = "s" * 32
    gw = gateway.app.test_client()

    info = gw.get("/v1/info", headers=TOKEN_HDR).get_json()
    assert info["hands_reachable"] is True and info["control"] == "agent"
    assert gw.post("/v1/act", json={"op": "move", "x": 3, "y": 4}, headers=TOKEN_HDR).status_code == 200

    fake_gui.pos = (800, 800)
    hands.TAKEOVER.check_cursor()
    r = gw.post("/v1/act", json={"op": "click", "x": 3, "y": 4}, headers=TOKEN_HDR)
    assert r.status_code == 409
    assert r.get_json() == {"ok": False, "error": YIELD_ERROR, "control": "yielded"}
    assert "Retry-After" in r.headers
    info = gw.get("/v1/info", headers=TOKEN_HDR).get_json()
    assert info["control"] == "yielded" and info["control_retry_after"] > 0

    hands.clock.advance(11)
    assert gw.post("/v1/act", json={"op": "key", "key": "enter"}, headers=TOKEN_HDR).status_code == 200
    assert gw.get("/v1/info", headers=TOKEN_HDR).get_json()["control"] == "agent"


def test_gateway_control_unknown_for_old_hands(gateway, serve_app):
    from flask import Flask

    old = Flask("old_hands")
    old.get("/health")(lambda: {"ok": True})  # no /status: pre-WP0b hands
    gateway.HANDS_URL = serve_app(old)
    gateway.HANDS_SECRET = "s" * 32
    info = gateway.app.test_client().get("/v1/info", headers=TOKEN_HDR).get_json()
    assert info["hands_reachable"] is True and info["control"] == "unknown"
