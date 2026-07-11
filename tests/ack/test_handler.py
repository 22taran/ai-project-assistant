import base64, json, hashlib, hmac, time, os, sys, pathlib
from unittest.mock import MagicMock

ACK_DIR = pathlib.Path(__file__).resolve().parents[2] / "lambda" / "ack"
sys.path.insert(0, str(ACK_DIR))

SECRET = "s3cr3t"

def _event(body_str, ts=None, sign=True):
    ts = ts or str(int(time.time()))
    if sign:
        base = f"v0:{ts}:{body_str}".encode()
        sig = "v0=" + hmac.new(SECRET.encode(), base, hashlib.sha256).hexdigest()
    else:
        sig = "v0=bad"
    return {
        "headers": {"x-slack-signature": sig, "x-slack-request-timestamp": ts},
        "body": body_str,
        "isBase64Encoded": False,
    }

def _load_handler(monkeypatch, fake_boto_invoke):
    os.environ["SLACK_SIGNING_SECRET_ARN"] = "arn:secret"
    os.environ["WORKER_FUNCTION_NAME"] = "worker-fn"
    import importlib
    # patch boto3 before import
    import types
    fake_sm = MagicMock()
    fake_sm.get_secret_value.return_value = {"SecretString": SECRET}
    fake_lambda = MagicMock()
    fake_lambda.invoke = fake_boto_invoke
    def fake_client(name, *a, **k):
        return fake_sm if name == "secretsmanager" else fake_lambda
    fake_boto3 = types.SimpleNamespace(client=fake_client)
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    if "handler" in sys.modules:
        del sys.modules["handler"]
    return importlib.import_module("handler")

def test_url_verification_echoes_challenge(monkeypatch):
    h = _load_handler(monkeypatch, MagicMock())
    body = json.dumps({"type": "url_verification", "challenge": "abc123"})
    resp = h.handler(_event(body), None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["challenge"] == "abc123"

def test_bad_signature_returns_401(monkeypatch):
    h = _load_handler(monkeypatch, MagicMock())
    body = json.dumps({"type": "event_callback"})
    resp = h.handler(_event(body, sign=False), None)
    assert resp["statusCode"] == 401

def test_valid_event_invokes_worker_and_acks(monkeypatch):
    invoke = MagicMock()
    h = _load_handler(monkeypatch, invoke)
    body = json.dumps({"type": "event_callback", "event": {"text": "hi"}})
    resp = h.handler(_event(body), None)
    assert resp["statusCode"] == 200
    invoke.assert_called_once()
    kwargs = invoke.call_args.kwargs
    assert kwargs["InvocationType"] == "Event"
    assert kwargs["FunctionName"] == "worker-fn"
