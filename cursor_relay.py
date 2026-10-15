"""
cursor_relay.py -- let Muse drive your Windows mouse/keyboard, with your consent.

HOW IT WORKS
  1. You run this on your PC. It listens on 127.0.0.1:5000 (localhost only --
     nothing on your network can reach it directly).
  2. You expose it with Cloudflare Tunnel (outbound connection from your PC,
     no firewall or router changes):
         cloudflared tunnel --url http://127.0.0.1:5000
     Cloudflare prints a https://<random>.trycloudflare.com URL.
  3. When YOU want a driving session, you paste that URL + your SHARED_SECRET
     to Muse in chat.
  4. Muse loops: screenshot -> decide where to click -> send the action ->
     screenshot again.
  5. Close this window any time to kill it instantly. It runs nothing on boot
     unless you set that up yourself.

SECURITY NOTES (read these)
  - This is remote-control software. Only run it while you want Muse driving,
    and keep an eye on the screen.
  - The tunnel URL is reachable by anyone who guesses it -- the shared secret
    is the only lock. Use a long random secret and don't reuse it across sessions.
  - Screenshots go to Muse so it can see where to click. Don't run it with
    sensitive documents open unless you're fine with that.
  - pyautogui.FAILSAFE is on: slam the mouse into any screen corner to abort
    the current action.

SETUP (Windows)
  1. Install Python 3.10+ from python.org (check "Add python.exe to PATH").
  2. pip install flask pyautogui pillow
  3. Set SHARED_SECRET below to something long and random.
  4. python cursor_relay.py
  5. In another terminal: cloudflared tunnel --url http://127.0.0.1:5000
     (get cloudflared: winget install cloudflare.cloudflared, or GitHub releases)
  6. Paste the tunnel URL + secret to Muse when you want a session.

WHAT MUSE CAN DO WITH IT
  GET  /screenshot          PNG of your screen (+ X-Screen-Width/Height headers
                            so it knows the coordinate space)
  POST /move    {x, y}      move the cursor
  POST /click   {x, y, button="left"|"right"|"middle"}
  POST /type    {text}      type text
  POST /key     {key}       press a key: "enter", "tab", "esc", "f5", ...
  POST /scroll  {clicks}    scroll up (positive) / down (negative)
  Every call except /health needs the secret, as header  X-Secret: <your secret>
  or, equivalently, as a query parameter:  ?secret=<your secret>
  (The query form exists because some tunnel paths strip or mangle custom
  headers; a URL parameter survives every proxy. Prefer the header when both
  work -- URLs are more likely to be logged.)

LIMITS (honest)
  - Roughly 1-2 seconds per action round-trip. Fine for deliberate work
    (installers, forms, settings, file organizing). Useless for games.
  - Coordinates are screen pixels; screenshots keep Muse oriented.
"""

import io
from flask import Flask, request, jsonify, send_file
import pyautogui

# ---- CHANGE THIS ----
SHARED_SECRET = "change-me-to-something-long-and-random"
PORT = 5000
# ---------------------

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.15

app = Flask(__name__)


@app.before_request
def gate():
    if request.path == "/health":
        return
    provided = request.headers.get("X-Secret") or request.args.get("secret") or ""
    if provided != SHARED_SECRET:
        return jsonify({"ok": False, "error": "bad secret"}), 401


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/screenshot")
def screenshot():
    img = pyautogui.screenshot()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    resp = send_file(buf, mimetype="image/png")
    resp.headers["X-Screen-Width"] = str(img.size[0])
    resp.headers["X-Screen-Height"] = str(img.size[1])
    return resp


@app.post("/move")
def move():
    d = request.get_json(force=True)
    pyautogui.moveTo(int(d["x"]), int(d["y"]), duration=0.2)
    return {"ok": True}


@app.post("/click")
def click():
    d = request.get_json(force=True)
    pyautogui.click(x=int(d["x"]), y=int(d["y"]), button=d.get("button", "left"))
    return {"ok": True}


@app.post("/type")
def type_text():
    d = request.get_json(force=True)
    pyautogui.write(d["text"], interval=0.02)
    return {"ok": True}


@app.post("/key")
def key():
    d = request.get_json(force=True)
    pyautogui.press(d["key"])
    return {"ok": True}


@app.post("/scroll")
def scroll():
    d = request.get_json(force=True)
    pyautogui.scroll(int(d.get("clicks", 3)))
    return {"ok": True}


if __name__ == "__main__":
    if SHARED_SECRET == "change-me-to-something-long-and-random":
        print("Set SHARED_SECRET first. Exiting.")
        raise SystemExit(1)
    print(f"Listening on 127.0.0.1:{PORT} -- localhost only.")
    print("Expose with: cloudflared tunnel --url http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=PORT, threaded=True)
