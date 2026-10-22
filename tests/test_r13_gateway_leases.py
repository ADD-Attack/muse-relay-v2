"""B05 actual negotiation boundary, deadline and concurrency tests."""
import importlib.util
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading
import pytest

@pytest.fixture
def gateway():
    spec = importlib.util.spec_from_file_location('b05_gateway', Path(__file__).resolve().parents[1] / 'services/gateway/app.py')
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    g.HANDS_SECRET = 'secret'
    return g

class Response:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status
    def json(self):
        return self.body

@pytest.mark.parametrize('caps', [{}, {'ok': True}, {'ok': True, 'execution_lease_version': 0, 'boot': 'old'}, {'ok': True, 'execution_lease_version': True, 'boot': 'old'}])
def test_old_hands_never_gets_action(gateway, monkeypatch, caps):
    monkeypatch.setattr(gateway.requests, 'get', lambda *a, **k: Response(caps))
    monkeypatch.setattr(gateway.requests, 'post', lambda *a, **k: pytest.fail('no mint/action allowed'))
    state, status, result, _ = gateway._queued_attempt('click', {}, {'hold': 10, 'lease': None})
    assert state == 'failed' and status == 409
    assert result['error_code'] == 'capability_refused'


def test_same_lease_across_yield_no_renewal(gateway, monkeypatch):
    calls = []
    monkeypatch.setattr(gateway.requests, 'get', lambda *a, **k: Response({
        'ok': True, 'execution_lease_version': 1, 'boot': 'boot', 'foreground_hwnd': 42}))
    def post(url, **kwargs):
        calls.append((url, kwargs['json']))
        if url.endswith('/execution/lease'):
            return Response({'ok': True, 'lease': {'version': 1, 'boot': 'boot', 'token': 'opaque'}})
        return Response({'ok': False, 'error_code': 'yield'}, 409)
    monkeypatch.setattr(gateway.requests, 'post', post)
    context = {'hold': 10, 'lease': None}
    payload = {'x': 1}
    for _ in range(2):
        assert gateway._queued_attempt('click', payload, context)[0] == 'held'
    assert len(calls) == 3
    assert calls[1][1]['_execution_lease'] == calls[2][1]['_execution_lease']
    assert payload['expect_focus'] == {'hwnd': 42}
    assert '_execution_lease' not in payload


def test_one_dispatch_and_eviction_preserves_uncertainty(gateway, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def forward(*args):
        calls.append(args)
        entered.set()
        assert release.wait(3)
        return 200, {'ok': True}
    monkeypatch.setattr(gateway, '_forward_act', forward)
    r = {'id': 'r', 'op': 'click', 'state': 'held', 'deadline': 100}
    gateway._store_receipt(r, {'x': 1})
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(gateway._pump_receipt, r, 1)
        assert entered.wait(3)
        assert pool.submit(gateway._pump_receipt, r, 1).result()['state'] == 'held'
        gateway.RECEIPT_MAX = 1
        gateway._store_receipt({'id': 'new', 'state': 'applied'})
        release.set()
        first.result()
    assert len(calls) == 1
    assert r['state'] == 'unknown-outcome'
    assert 'r' not in gateway._pending_payloads


def test_slow_first_receipt_expires_second(gateway, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(gateway.time, 'monotonic', lambda: clock[0])
    def forward(*a):
        clock[0] = 20
        return 200, {'ok': True}
    monkeypatch.setattr(gateway, '_forward_act', forward)
    a = dict(id='a', state='held', op='click', deadline=100, _deadline_mono=10)
    b = dict(id='b', state='held', op='click', deadline=100, _deadline_mono=10)
    for r in (a, b):
        gateway._store_receipt(r, {'x': 1})
        gateway._pump_receipt(r, 0)
    assert a['state'] == 'applied'
    assert b['state'] == 'refused-yielded'
    assert b['result']['error_code'] == 'deadline_expired'
