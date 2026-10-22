"""B01 F4 diagnostic retention; simulated gateway boundary tests."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def gateway():
    path = Path(__file__).resolve().parents[1] / "services/gateway/app.py"
    spec = importlib.util.spec_from_file_location("f4_reference_gateway", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_retains_known_partial_type_fields(gateway):
    source = {"ok": False, "error_code": "type_aborted", "aborted": True,
              "abort_reason": "owner", "owner_guard": "hook", "method_used": "keys",
              "chars": 40, "chars_typed": 12}
    assert gateway._held_failure_diagnostics(source) == source


def test_omits_payloads_and_arbitrary_messages(gateway):
    secret = "DO-NOT-PERSIST"
    source = {"error": secret, "text": secret, "error_code": secret,
              "debug": {"payload": secret}, "owner_guard": {"payload": secret}}
    safe = gateway._held_failure_diagnostics(source)
    assert safe == {"ok": False}


def test_rejects_wrong_field_types_and_bounds(gateway):
    safe = gateway._held_failure_diagnostics({"chars": True, "chars_typed": -1,
                                            "aborted": "true", "owner_guard": ["hook"]})
    assert safe == {"ok": False}
    assert gateway._held_failure_diagnostics(None) == {"ok": False}
    assert "chars" not in gateway._held_failure_diagnostics({"chars": 1_000_001})


def test_partial_failure_is_terminal_and_not_retained_by_reference(gateway, monkeypatch):
    gateway._reset_coordination_state()
    receipt = {"id": "reference", "op": "type", "state": "held", "deadline": 100}
    gateway._store_receipt(receipt, {"text": "private payload"})
    result = {"ok": False, "error_code": "type_aborted", "abort_reason": "owner",
              "chars_typed": 12, "chars": 40}
    calls = []

    def forward(*args):
        calls.append(args)
        return 409, result

    monkeypatch.setattr(gateway, "_forward_act", forward)
    gateway._pump_receipt(receipt, 1)
    result["chars_typed"] = 30
    gateway._pump_receipt(receipt, 2)
    assert receipt["state"] == "failed"
    assert receipt["result"]["chars_typed"] == 12
    assert "reference" not in gateway._pending_payloads
    assert len(calls) == 1


@pytest.mark.parametrize("reason", ["owner", "locked"])
@pytest.mark.parametrize("counts, expected", [
    ({"chars": 40, "chars_typed": 0}, {"chars": 40, "chars_typed": 0}),
    ({"chars": 40}, {"chars": 40}),
    ({"chars": 40, "chars_typed": 41}, {}),
    ({"chars": -1, "chars_typed": float("inf")}, {}),
    ({"chars": 1_000_000, "chars_typed": 1_000_000},
     {"chars": 1_000_000, "chars_typed": 1_000_000}),
])
def test_count_evidence(gateway, reason, counts, expected):
    assert gateway._held_failure_diagnostics(
        {"abort_reason": reason, **counts}) == {
            "ok": False, "abort_reason": reason, **expected}
