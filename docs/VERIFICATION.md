# Manual verification steps

Checks that need the owner's Windows PC (real hands, real desktop) and
could not be run in the environment that wrote the code. Each entry says
what was verified automatically and what is still **unverified** until the
owner runs it.

## WP0 — smoke script

Verified automatically: `python tools/smoke.py --mock-hands` (7/7 PASS on
Linux against the mock hands) and the hands-not-running path (hand checks
reported as SKIP with the reason, exit 0).

**Unverified — run on the Windows PC:**

1. Install deps: `pip install -r services\gateway\requirements.txt -r services\parser\requirements.txt`
2. With the packaged app **closed**, start only the standalone hands
   (`python hands\muse_relay_hands.py`), then run `python tools\smoke.py`.
   Expect PASS on all checks, including "screenshot via /v1/screen" and
   "harmless action via /v1/act".
3. Close the hands and run `python tools\smoke.py` again. Expect the two
   hand checks as SKIP with "hands are not running", and `SMOKE PASS`.
4. With the packaged app running (Start pressed), copy its gateway token,
   `$env:RELAY_GATEWAY_TOKEN = "<token>"`, then `python tools\smoke.py --use-running`.
   Expect all PASS.
