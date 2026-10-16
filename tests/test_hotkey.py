"""WP5c — keyboard chords through hands /hotkey and gateway op "hotkey"."""

SECRET_HDR = {"X-Secret": "s" * 32}
TOKEN_HDR = {"X-Relay-Token": "t" * 32}


def test_hotkey_presses_chord(hands, fake_gui):
    r = hands.app.test_client().post(
        "/hotkey", json={"keys": ["Win", "shift", "left"]}, headers=SECRET_HDR
    )
    assert r.status_code == 200
    assert r.get_json() == {"ok": True, "keys": ["win", "shift", "left"]}
    assert fake_gui.calls[-1] == ("hotkey", "win", "shift", "left")


def test_hotkey_rejects_unknown_names_and_presses_nothing(hands, fake_gui):
    r = hands.app.test_client().post(
        "/hotkey", json={"keys": ["win", "shfit", "left"]}, headers=SECRET_HDR
    )
    assert r.status_code == 400
    assert r.get_json()["unknown"] == ["shfit"]
    assert not any(c[0] == "hotkey" for c in fake_gui.calls)


def test_hotkey_rejects_bad_shapes(hands, fake_gui):
    client = hands.app.test_client()
    for body in ({}, {"keys": []}, {"keys": "win+left"}, {"keys": ["a"] * 7},
                 {"keys": ["win", 3]}, {"keys": ["win", ""]}):
        r = client.post("/hotkey", json=body, headers=SECRET_HDR)
        assert r.status_code == 400, body
    assert not any(c[0] == "hotkey" for c in fake_gui.calls)


def test_hotkey_needs_secret_and_respects_takeover(hands, fake_gui):
    client = hands.app.test_client()
    assert client.post("/hotkey", json={"keys": ["alt", "f4"]}).status_code == 401
    hands.TAKEOVER.local_input("key press")
    r = client.post("/hotkey", json={"keys": ["alt", "f4"]}, headers=SECRET_HDR)
    assert r.status_code == 409
    assert not any(c[0] == "hotkey" for c in fake_gui.calls)


def test_single_key_endpoint_unchanged(hands, fake_gui):
    r = hands.app.test_client().post("/key", json={"key": "enter"}, headers=SECRET_HDR)
    assert r.status_code == 200 and r.get_json() == {"ok": True}
    assert fake_gui.calls[-1] == ("press", "enter")


def test_gateway_hotkey_op(hands, fake_gui, gateway, serve_app):
    gateway.HANDS_URL = serve_app(hands.app)
    gateway.HANDS_SECRET = "s" * 32
    gw = gateway.app.test_client()
    r = gw.post("/v1/act", json={"op": "hotkey", "keys": ["win", "shift", "left"]},
                headers=TOKEN_HDR)
    assert r.status_code == 200
    assert fake_gui.calls[-1] == ("hotkey", "win", "shift", "left")
    # validation errors from the hands come back as 400, not a gateway error
    r = gw.post("/v1/act", json={"op": "hotkey", "keys": ["nope"]}, headers=TOKEN_HDR)
    assert r.status_code == 400 and r.get_json()["unknown"] == ["nope"]
    r = gw.post("/v1/act", json={"op": "hotkey", "keys": "win+left"}, headers=TOKEN_HDR)
    assert r.status_code == 400
    # same token auth as every other act call
    assert gw.post("/v1/act", json={"op": "hotkey", "keys": ["win"]}).status_code == 401
