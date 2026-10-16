"""Mock hands for tests and tools/smoke.py --mock-hands.

Speaks the real hands HTTP contract (X-Secret / ?secret= auth, /health
ungated, /screenshot PNG, move/click/type/key/scroll) without touching a
real mouse, keyboard, or screen, so the gateway can be exercised on any OS.

Run standalone:  python tests/mock_hands.py --port 5000
The secret comes from the MOCK_HANDS_SECRET environment value; it is
never printed.
"""

import argparse
import hmac
import os
import struct
import zlib

from flask import Flask, Response, jsonify, request

HANDS_OPS = ("move", "click", "type", "key", "scroll")


def _tiny_png(width=4, height=3):
    """A valid all-grey PNG, built without Pillow."""
    raw = b"".join(b"\x00" + b"\x80" * (width * 3) for _ in range(height))

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def create_app(secret):
    app = Flask("mock_hands")
    app.config["actions"] = []  # every accepted action, for assertions

    @app.before_request
    def gate():
        if request.path == "/health":
            return None
        provided = request.headers.get("X-Secret") or request.args.get("secret") or ""
        if not hmac.compare_digest(provided, secret):
            return jsonify({"ok": False, "error": "bad secret"}), 401
        return None

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/screenshot")
    def screenshot():
        resp = Response(_tiny_png(), mimetype="image/png")
        resp.headers["X-Screen-Width"] = "4"
        resp.headers["X-Screen-Height"] = "3"
        return resp

    def _make(op):
        def handler():
            body = request.get_json(force=True, silent=True) or {}
            app.config["actions"].append((op, body))
            return {"ok": True}

        handler.__name__ = f"op_{op}"
        return handler

    for op in HANDS_OPS:
        app.post(f"/{op}")(_make(op))

    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    args = ap.parse_args()
    secret = os.environ.get("MOCK_HANDS_SECRET", "")
    if len(secret) < 16:
        raise SystemExit("MOCK_HANDS_SECRET must be set (16+ chars)")
    from waitress import serve

    serve(create_app(secret), host=args.host, port=args.port, threads=4)


if __name__ == "__main__":
    main()
