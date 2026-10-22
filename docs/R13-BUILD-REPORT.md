# R13 candidate build report

Build only; no deployment or live R12 changes. Runtime Windows acceptance remains open.

## B00 — inherited

Commit `1933b3b58748d86caf81dca85b99435896c6f1e1`: frozen contracts and reproduced baseline (18 acceptance failures / 3 passes; 229 pre-existing passes / 1 skip).

## B01 — held diagnostics

Added `_held_failure_diagnostics` in `services/gateway/app.py` and used it for terminal held failures. Fresh allowlisted diagnostics exclude arbitrary upstream prose and payloads. Count bounds match hands' 1,000,000-byte request ceiling; contradictory count pairs are omitted, not repaired. Added privacy, mutation, terminal/no-replay, owner/lock and count-boundary tests.

Commands (Python = `/home/openclaw/.venvs/muse-relay-r13/bin/python`):

- `python -m pytest -q tests/test_f4_diagnostics_reference.py tests/test_relay_fix_acceptance.py -k 'count_evidence or partial or retains or omits or rejects_wrong or p04'`: 15 passed, 20 deselected.
- `python -m pytest -q --ignore=tests/test_relay_fix_acceptance.py`: 243 passed, 1 skipped.

Source review: failure exits remove pending payload; second pump cannot dispatch terminal receipts. Direct-path parity and richer terminal states belong to B02/B03. No Windows closure claimed.

## B02 — implementation checkpoint; review gate BLOCKED

Added `classify_act_outcome` and `_attempt_act` in `services/gateway/app.py`; direct, initial queued, and held paths share validated evidence classification. Invalid/lost/contradictory responses return 502 with `unknown_outcome`, never automatic replay. Initial receipt identity exists before dispatch. Safe copied results exclude arbitrary exception text and payload echoes. Added 41 boundary tests covering direct/queued/held malformed results, contradictory evidence, pre-dispatch configuration rejection, pre-send receipt creation and post-send exceptions. B03 abort-state/UI work has not begun.

Commands:

- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q tests/test_relay_fix_acceptance.py -k 'p02 or p03 or p04 or p05'`: 8 passed, 13 deselected.
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q tests/test_r13_outcomes.py tests/test_f4_diagnostics_reference.py tests/test_relay_fix_acceptance.py -k 'not p01 and not p06 and not p07 and not p08 and not p09 and not p10 and not p11 and not p12 and not p13'`: 63 passed, 13 deselected.
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q --ignore=tests/test_relay_fix_acceptance.py`: **1 failed, 283 passed, 1 skipped**.
- `git diff --check`: clean.

### Named blocker: contradictory frozen regression contract

`tests/test_v3r2_remaining.py:204-205` supplies HTTP 409 with only `{"error": "user active — control yielded"}` (no boolean `ok`, no machine-readable refusal) and requires `held`. The F3 Required behavior paragraph explicitly requires a boolean `ok`, makes malformed evidence terminal unknown after possible dispatch, and allows only verified no-effect refusals to retry. The same old test also expects a malformed no-ok `offset mismatch` response to become `failed` rather than unknown (line 211).

The old test is unchanged. Preserving its behavior would violate the R13 acceptance specification; changing its expectations is prohibited by the operator's no-adjusting-expected-outputs boundary. Owner resolution of this contract conflict is required. No fixture sniffing, legacy-only bypass, xfail, or skips were introduced to hide it. B02 remains gate-blocked; B03–B18 have not been started, respecting the sequential package/review requirement. This checkpoint is NOT a completed R13 candidate.

Unresolved: whether the operator authorizes an explicit, reviewed retirement/update of this superseded R12 behavior contract. No production or packaged Windows validation was attempted.
