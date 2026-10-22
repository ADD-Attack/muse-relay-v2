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
