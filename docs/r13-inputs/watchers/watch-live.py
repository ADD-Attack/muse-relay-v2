#!/usr/bin/env python3
"""Continuous latest-frame poller (Christopher's design, 2026-10-19).

Polls the relay every ~3 s and ALWAYS overwrites the latest-frame files
with the newest fetch — there is no fire/baseline/queue. The agent
reads only the most recent frame, so a description can be at most one
poll old at read time. Files:
  screen-live.png      latest frame, 1440w (what the agent reads)
  screen-live-full.png latest frame, native 1920x1080
  screen-live.txt      epoch of the latest frame
  screen-live.log      one line per poll: epoch, masked hash (short),
                       changed=1/0 vs the previous poll
Runs until killed. PID recorded in watch-live.pid by the launcher.
"""
import sys, time, hashlib, subprocess, io, os
from PIL import Image

TOKEN = sys.argv[1]
URL = "http://100.119.30.72:5010/v1/screen"
HOME = os.path.expanduser("~/workspace")
LIVE = os.path.join(HOME, "screen-live.png")
FULL = os.path.join(HOME, "screen-live-full.png")
EPOCH = os.path.join(HOME, "screen-live.txt")
LOG = os.path.join(HOME, "screen-live.log")

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
