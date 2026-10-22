"""B02 evidence classification at direct and retry boundaries."""
import importlib.util
from pathlib import Path
import pytest

@pytest.fixture
def gateway(monkeypatch):
    spec = importlib.util.spec_from_file_location('r13_outcomes', Path(__file__).resolve().parents[1] / 'services/gateway/app.py')
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    g.TOKEN = 'test-token'
    g.HANDS_SECRET = 'secret'
    monkeypatch.setattr(g, '_ensure_receipt_thread', lambda: None)
    return g

CASES = [
    (200, None, 'unknown-outcome'), (200, [], 'unknown-outcome'),
    (200, {}, 'unknown-outcome'), (200, {'ok': 1}, 'unknown-outcome'),
    (200, {'ok': 'true'}, 'unknown-outcome'),
    (200, {'ok': None}, 'unknown-outcome'),
    (500, {'ok': True}, 'unknown-outcome'),
    (200, {'ok': True, 'aborted': True}, 'unknown-outcome'),
    (200, {'ok': True}, 'applied'),
    (200, {'ok': False, 'error_code': 'operation_failed'}, 'failed'),
    (409, {'ok': False, 'error_code': 'yield', 'chars_typed': 1, 'chars': 2}, 'unknown-outcome'),
    (409, {'ok': False, 'error_code': 'locked', 'chars_typed': 3, 'chars': 2}, 'unknown-outcome'),
    (409, {'error': 'user active — control yielded'}, 'unknown-outcome'),
]

@pytest.mark.parametrize('status,body,state', CASES)
@pytest.mark.parametrize('path', ['direct', 'queued', 'held'])
def test_boundary_classification(gateway, monkeypatch, status, body, state, path):
    calls = []
    def forward(*a):
        calls.append(a)
        return status, body
    monkeypatch.setattr(gateway, '_forward_act', forward)
    if path == 'held':
        r = dict(id='r', state='held', op='click', deadline=100)
        gateway._store_receipt(r, {'text': 'PRIVATE-SENTINEL'})
        gateway._pump_receipt(r, 1)
    else:
        endpoint = '/v1/act' + ('/queued' if path == 'queued' else '')
        response = gateway.app.test_client().post(endpoint, headers={'X-Relay-Token': 'test-token'}, json={'op': 'click'})
        if state == 'unknown-outcome':
            assert response.status_code == 502
            assert response.json['error_code'] == 'unknown_outcome'
        assert response.json['ok'] is (state == 'applied')
        if path == 'direct':
            return
        r = gateway._receipts[response.json['id']]
    assert r['state'] == state
    assert r['id'] not in gateway._pending_payloads
    gateway._pump_receipt(r, 2)
    assert len(calls) == 1
    assert 'PRIVATE-SENTINEL' not in repr(r)
    if state == 'unknown-outcome':
        assert r['result']['error_code'] == 'unknown_outcome'


def test_configuration_rejection_never_sends(gateway, monkeypatch):
    gateway.HANDS_SECRET = ''
    monkeypatch.setattr(gateway.requests, 'post', lambda *a, **k: pytest.fail('sent'))
    state, status, body, _ = gateway._attempt_act('click', {})
    assert (state, status, body['error_code']) == ('failed', 503, 'configuration_error')


def test_receipt_exists_before_send_and_exception_never_replays(gateway, monkeypatch):
    calls = []
    def forward(*a):
        calls.append(a)
        assert len(gateway._receipts) == 1
        assert next(iter(gateway._receipts.values()))['state'] == 'in-flight'
        raise RuntimeError('PRIVATE-SENTINEL')
    monkeypatch.setattr(gateway, '_forward_act', forward)
    response = gateway.app.test_client().post('/v1/act/queued', headers={'X-Relay-Token': 'test-token'}, json={'op': 'click'})
    r = gateway._receipts[response.json['id']]
    gateway._pump_receipt(r, 100)
    assert r['state'] == 'unknown-outcome'
    assert len(calls) == 1
    assert 'PRIVATE-SENTINEL' not in repr(r)
