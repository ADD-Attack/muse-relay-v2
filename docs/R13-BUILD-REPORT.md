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

### B02 supersession authorized and gate cleared

Muse's explicit operator authorization resolves the conflict in favor of F3. In `tests/test_v3r2_remaining.py::test_pump_maps_2xx_yield_and_everything_else`, lines 205–206 and 211 only: malformed no-`ok` yield evidence now asserts `unknown-outcome` and no pending payload (previously `held` and retained payload); malformed offset-mismatch evidence now asserts `unknown-outcome` (previously `failed`). Stimuli and every other assertion in that file are unchanged. Authority: framework F3, Required behavior, and operator's specific supersession order. This is not authorization to change further legacy expectations.

Rerun commands:
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q --ignore=tests/test_relay_fix_acceptance.py`: 284 passed, 1 skipped.
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q tests/test_relay_fix_acceptance.py -k 'p02 or p03 or p04 or p05'`: 8 passed, 13 deselected.

## B03 — receipt states and visibility

Added schema-valid `aborted-owner` / `aborted` classification; missing receipt lookup now says `unavailable`, never nonexecution. UI state chips/colors explicitly represent unknown, abort, in-flight and unavailable. README documents injection-vs-effect, no replay, and volatile retention. Existing dashboard snapshot/count/feed functions preserve arbitrary state strings without remapping; new tests exercise those actual functions, polling/list endpoints and eviction. Browser interaction remains unverified; source feed has no replay control.

Commands:
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q --ignore=tests/test_relay_fix_acceptance.py`: 288 passed, 1 skipped.
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q tests/test_relay_fix_acceptance.py -k 'p02 or p03 or p04 or p05'`: 8 passed, 13 deselected.

No further pre-existing test expectations changed. Source map: gateway `classify_act_outcome`, `act_queued_get`; UI `STATE_CHIP`, `STATE_COLOR`; existing model `_snapshot_receipt_rows`, `summarize_receipts`, `receipt_state_counts` audited unchanged.

## B04 — receiver-local execution lease protocol

Hands now provides authenticated `/execution/capabilities` and `/execution/lease` (version 1). `_execution_mint` stores opaque, bounded-lifetime boot-bound identities with canonical private operation digests; `_execution_check` validates operation, boot, consumption and equality expiry and atomically consumes one start. Capacity refuses rather than evicting live identities. No mint/check operation injects input. Source map: these helpers/routes in `hands/muse_relay_hands.py`; gateway negotiation and side-effect consumption are B05/B07 integration work.

Commands:
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q tests/test_r13_execution_leases.py`: 11 passed.
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q --ignore=tests/test_relay_fix_acceptance.py`: 299 passed, 1 skipped.

Fixtures cover independent receiver clock, wall-time jumps, adversarial transit delay/equality expiry, wrong boot/token/operation, invalid lifetimes, authenticated minting, and a two-thread atomic-start race. Old-hands gateway refusal is tested with B05, where capability negotiation is wired. No packaged runtime claim.

## B05 — gateway lease negotiation and atomic retry reservation

Gateway `_prepare_queued_execution` negotiates authenticated version/boot, pins available foreground before digest minting, and fails closed without input on incompatible hands. `_queued_attempt` uses a context-local lease carrier so private metadata is not added to payload-key diagnostics; `_forward_act` sends it only on the wire. A hold retains one lease. Caller internal execution fields are stripped. `_pump_receipt` checks immutable monotonic expiry before dispatch, reserves one attempt under the receipt lock, performs I/O unlocked, and samples elapsed time on settlement. Concurrent eviction leaves uncertainty, not false never-started evidence.

Protocol adapter: the fixture in `tests/test_relay_fix_acceptance.py` now supplies a successful fake `_prepare_queued_execution` result so P02/P03 still inject lost/malformed **action** responses, after the new prerequisite handshake. No stimulus or expected outcome was changed. This follows the framework's explicit new-seam adapter allowance; it is not a further legacy expectation supersession. Real handshake behavior has separate B05 tests.

Commands:
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q tests/test_r13_gateway_leases.py tests/test_relay_fix_acceptance.py -k 'not p06 and not p07 and not p08 and not p09 and not p10 and not p11 and not p12 and not p13'`: 16 passed, 12 deselected.
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q --ignore=tests/test_relay_fix_acceptance.py`: 306 passed, 1 skipped.

Tests cover old/incompatible hands (zero POSTs), same lease through yields, one concurrent dispatch, eviction during dispatch, and a slow first receipt expiring the second. Receipt-only helper fixtures without monotonic metadata use supplied time plus measured monotonic elapsed duration; actual queued receipts always carry receiver-independent local monotonic deadlines. First-effect enforcement remains B07.

## B06 — guarded input checkpoint; review gate BLOCKED

`_input.check` revalidates owner activity, desktop lock, expected foreground and lease after mutex acquisition/hand-travel. Failed `__enter__` releases on every exception, and never resets resting state. `_InputRefused` has a Flask handler. Focus and clipboard-set now use the shared mutex. First-effect/after-preparatory-wait consumption and multistep guards remain B07/B11 work; this checkpoint does not claim them complete.

Commands:
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q tests/test_relay_fix_acceptance.py -k p07`: 3 passed, 18 deselected.
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q tests/test_r13_guarded_input.py tests/test_relay_fix_acceptance.py -k 'lock_change or p07'`: 13 passed, 18 deselected. Includes all ten side-effect routes, no input/ramp reset on post-acquisition lock change, and lock acquisition by a different thread after refusal.
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q --ignore=tests/test_relay_fix_acceptance.py`: **1 failed, 315 passed, 1 skipped**.
- `git diff --check`: clean.

### Further named conflict — R7.2 single-door idle-probe expectation

`tests/test_r72_fixround.py::test_lock_check_is_lock_only_not_self_triggering_idle` is unchanged. At lines 269–271 its fake reports `(None, None)` on the first probe and `(False, 0.0)` on every subsequent probe, even before any key has been injected. Lines 287–288 require complete successful typing and exactly ONE idle probe (`calls["n"] == 1`). F2 requires a new owner/lock check under input access after acquisition, before any side effect. That second check therefore sees newly reported activity and correctly refuses; bypassing it would regress P07.

This is distinct from self-triggered idle *after* injection, which must continue to be ignored/attributed correctly. Proposed narrow resolution for operator review: keep the successful full-text assertion, change the fixture to report zero idle only once `s.written` is nonempty (actual simulated self input), and replace the single-probe assertion with evidence of the required pre-input revalidation. This preserves the original anti-self-trigger purpose without prohibiting F2. No changes to this test, its expectations, or other legacy expected outputs have been made. B07 onward is not started pending this gate, per the one-conflict-at-a-time operator direction.

### B06 supersession authorized and gate cleared

Muse authorized the minimal F2 harness correction. Only `tests/test_r72_fixround.py` lines 271 and 288 changed: simulated zero idle now begins after `s.written` contains an injected key, instead of on the second probe regardless of input; the exact-one-probe assertion becomes at least two (door and post-acquisition revalidation). The full-text successful-typing assertion and remainder of the file are unchanged. Authority: F2's required guard revalidation under input access and explicit operator authorization. This preserves the anti-self-trigger regression purpose.

Reruns:
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q --ignore=tests/test_relay_fix_acceptance.py`: 316 passed, 1 skipped.
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q tests/test_r13_guarded_input.py tests/test_relay_fix_acceptance.py -k 'lock_change or p07'`: 13 passed, 18 deselected.

## B07 — first-side-effect timing checkpoint; review gate BLOCKED

Hands `_input.before_effect`, `_before_effect`, and `_inject` move lease consumption and resting-act start to the injection boundary, after preparatory waits. Every side-effect route calls this boundary, including focus and clipboard-set; clipboard reads may precede it but mutations may not. Once started, lease expiry does not abort completion. Mouse/button releases remain unguarded cleanup. Native click-down exceptions release the button. A refused paste cannot trigger typing fallback or an unnecessary clipboard restore. Existing type partial-count lock checkpoints remain in the typing implementation pending B10; first-effect timing applies to both typing paths now.

Commands:
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q tests/test_r13_first_effect.py`: 15 passed. Covers all ten routes expiring during acquisition, attention delay, clipboard read delay, valid start followed by expiry, consumed-lease replay, no-effect versus injecting context/ramp behavior, and cleanup after a native press exception.
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q tests/test_relay_fix_acceptance.py -k 'p01 or p02 or p03 or p04 or p05 or p07'`: 12 passed, 9 deselected.
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q --ignore=tests/test_relay_fix_acceptance.py`: **1 failed, 330 passed, 1 skipped**.
- `git diff --check`: clean.

### Further named conflict — R11 context entry treated as a real act

`tests/test_r11_resting_watch.py::test_real_act_resets_the_global_ramp`, lines 190–192, opens `_input("mouse")` and immediately expects the resting intensity to reset despite performing no injection. The framework's shared timing contract says a refused action that never started must not reset the resting ramp or clear owner-stop state. An action may acquire input access and subsequently expire during attention/read preparation; therefore entering the mutex cannot irrevocably mark a real act. B07 starts/rests the act only at the first-side-effect boundary.

Proposed minimal harness resolution: add one simulated movement via `_inject` inside this test's input context, before its existing reset assertions. Keep all intensity and `last_act_end` expectations unchanged. This makes the test actually exercise the real act its name promises. New B07 tests separately prove a no-effect context leaves resting state untouched and a real injection calls begin/end. The legacy file remains unchanged; no further expectation/harness supersession is assumed. B08 onward has not started pending this one-at-a-time gate resolution. No deployment or live R12 changes.


### B07 setup adjustment authorized and gate cleared

Muse authorized the minimal setup change in `tests/test_r11_resting_watch.py::test_real_act_resets_the_global_ramp`. Added one simulated movement, `hands._inject(hands.pyautogui.moveTo, 1, 2)`, inside the existing input context and before the existing intensity assertions. No expected values changed. Authority: B07/F1 first-side-effect timing; a context that never injects must not reset the resting ramp.

Reruns after the setup change:
- `/home/openclaw/.venvs/muse-relay-r13/bin/python -m pytest -q --ignore=tests/test_relay_fix_acceptance.py`: 331 passed, 1 skipped (prior interrupted session).
