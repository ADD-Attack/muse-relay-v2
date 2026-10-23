#!/usr/bin/env python3
"""Continuous latest-frame poller for the ECU LAPTOP relay (Run 1 watcher path).

Same design as ~/workspace/watch-live.py (Christopher's, 2026-10-19) but pointed
at LAPTOP-UAPTFJ1J (100.76.253.71) with its own state files so the Abraham
walkthrough watcher state is never touched:

  screen-laptop-live.png       latest frame, 1440w (what the agent reads)
  screen-laptop-live-full.png  latest frame, native 1920x1080
  screen-laptop-live.txt       epoch of the latest frame
  screen-laptop-live.log       one line per poll: epoch, masked hash, changed=0/1

Usage: watch-live-laptop.py <gateway-token>
Polls every ~3 s until killed. Change detection = SHA-256 of the frame with the
bottom 80 px (taskbar) masked off.
"""
import sys, time, hashlib, subprocess, io, os
from PIL import Image

if len(sys.argv) < 2:
    sys.exit("usage: watch-live-laptop.py <gateway-token>")
TOKEN = sys.argv[1]
URL = "http://100.76.253.71:5010/v1/screen"
HOME = os.path.expanduser("~/workspace/miata-logs")
LIVE = os.path.join(HOME, "screen-laptop-live.png")
FULL = os.path.join(HOME, "screen-laptop-live-full.png")
EPOCH = os.path.join(HOME, "screen-laptop-live.txt")
LOG = os.path.join(HOME, "screen-laptop-live.log")

def fetch():
    try:
        r = subprocess.run(
            ["curl", "-s", "--proxytunnel", "-x", "http://hatch-egress-proxy:3130",
             "-H", "X-Relay-Token: " + TOKEN, URL],
            capture_output=True, timeout=10)
        if r.returncode == 0 and r.stdout[:4] == b"\x89PNG":
            return r.stdout
    except Exception:
        pass
    return None

prev = None
with open(LOG, "a") as log:
    log.write("START %f\n" % time.time())
while True:
    t0 = time.time()
    png = fetch()
    if png:
        im = Image.open(io.BytesIO(png)).convert("RGB")
        w, h = im.size
        hh = hashlib.sha256(im.crop((0, 0, w, h - 80)).tobytes()).hexdigest()[:12]
        changed = 1 if prev is not None and hh != prev else 0
        prev = hh
        im.save(FULL + ".tmp", format="PNG")
        os.rename(FULL + ".tmp", FULL)
        im.resize((1440, int(1440 * h / w))).save(LIVE + ".tmp", format="PNG")
        os.rename(LIVE + ".tmp", LIVE)
        with open(EPOCH + ".tmp", "w") as f:
            f.write(str(time.time()))
        os.rename(EPOCH + ".tmp", EPOCH)
        with open(LOG, "a") as log:
            log.write("%f %s changed=%d\n" % (time.time(), hh, changed))
    dt = time.time() - t0
    if dt < 3.0:
        time.sleep(3.0 - dt)
