"""Guided check of the takeover interlock (WP0b) against a running gateway.

Run on the Windows PC with the relay running (packaged app, Start pressed):

    $env:RELAY_GATEWAY_TOKEN = "<token from the app window>"
    python tools\\takeover_check.py

Steps:
  1. 20 agent-issued moves through /v1/act — none may be refused.
  2. You press Enter, then (after control returns) move the physical
     mouse — each time the next act must get 409 and /v1/info must
     report "control": "yielded".
  3. You keep hands off — after the quiet period acts must succeed again.

The cursor is moved in a small box around the screen centre; nothing is
clicked or typed. The token is never printed.
"""

import argparse
import os
import sys
import time

import requests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway", default="http://127.0.0.1:5010")
    ap.add_argument("--x", type=int, default=600, help="centre of the move box")
    ap.add_argument("--y", type=int, default=400)
    args = ap.parse_args()
    token = os.environ.get("RELAY_GATEWAY_TOKEN", "")
    if not token:
        print("Set RELAY_GATEWAY_TOKEN to the gateway token first.")
        return 1
    gw = args.gateway.rstrip("/")
    auth = {"X-Relay-Token": token}
    results = []

    def act(x, y):
        return requests.post(f"{gw}/v1/act", headers=auth,
                             json={"op": "move", "x": x, "y": y}, timeout=30)

    def control():
        return requests.get(f"{gw}/v1/info", headers=auth, timeout=10).json().get("control")

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))

    print("Hands off the mouse and keyboard for step 1 (about 10 seconds)...")
    time.sleep(3)
    initial = control()
    if initial == "yielded":
        print("Control is currently yielded (recent local input). Waiting for it to return...")
        for _ in range(30):
            time.sleep(1)
            if control() == "agent":
                break
    refused = 0
    for i in range(20):
        r = act(args.x + (i % 5) * 20, args.y + (i // 5) * 20)
        if r.status_code != 200:
            refused += 1
    check("20 agent moves never trip the interlock", refused == 0, f"{refused} refused")
    check("/v1/info shows agent control", control() == "agent")

    # Keyboard: pressing Enter in this console is local key input.
    input("\nPress Enter here (a local key press)... ")
    r = act(args.x, args.y)
    check("key press: next act refused with 409", r.status_code == 409, f"HTTP {r.status_code}")
    check("key press: /v1/info shows yielded", control() == "yielded")

    print("\nHands off — waiting for control to return before the mouse test...")
    if not wait_for(control, "agent", 60):
        check("control returned after the quiet period", False)
        return finish(results)

    # Mouse: no keyboard involved, so only cursor/mouse detection can trip it.
    print("Now MOVE THE PHYSICAL MOUSE (you have 20 seconds)...")
    tripped = wait_for(control, "yielded", 20)
    check("mouse move: /v1/info shows yielded", tripped)
    r = act(args.x, args.y)
    check("mouse move: next act refused with 409", r.status_code == 409, f"HTTP {r.status_code}")

    print("\nHands off now — waiting for the quiet period...")
    wait_for(control, "agent", 60)
    r = act(args.x, args.y)
    check("acts succeed again after the quiet period", r.status_code == 200, f"HTTP {r.status_code}")
    return finish(results)


def wait_for(get, want, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if get() == want:
            return True
        time.sleep(0.5)
    return False


def finish(results):
    ok = all(results)
    print(f"\nTAKEOVER CHECK {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
