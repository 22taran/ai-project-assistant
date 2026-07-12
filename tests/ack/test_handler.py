import base64, json, hashlib, hmac, time, os, sys, pathlib
from unittest.mock import MagicMock

ACK_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "ack"
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

import urllib.parse as _uparse

def _slash_event(command="/kt", text="deployment", user="U01"):
    body = _uparse.urlencode({
        "command": command, "text": text, "user_id": user,
        "team_id": "T01", "channel_id": "C01",
        "response_url": "https://hooks.slack.test/cmd",
    })
    ts = str(int(time.time()))
    sig = "v0=" + hmac.new(SECRET.encode(), f"v0:{ts}:{body}".encode(), hashlib.sha256).hexdigest()
    return {
        "headers": {
            "x-slack-signature": sig,
            "x-slack-request-timestamp": ts,
            "content-type": "application/x-www-form-urlencoded",
        },
        "body": body,
        "isBase64Encoded": False,
    }

def _load_handler(monkeypatch, fake_boto_invoke, roster_users=("U01",), ssm_raises=False):
    os.environ["SLACK_SIGNING_SECRET_ARN"] = "arn:secret"
    os.environ["WORKER_FUNCTION_NAME"] = "worker-fn"
    os.environ["ROSTER_PARAM_NAME"] = "/kt/dev/roster"
    os.environ["BOT_TOKEN_ARN"] = "arn:bot"
    import importlib, types, json as _json
    fake_sm = MagicMock()
    fake_sm.get_secret_value.return_value = {"SecretString": SECRET}
    fake_lambda = MagicMock()
    fake_lambda.invoke = fake_boto_invoke
    fake_ssm = MagicMock()
    if ssm_raises:
        fake_ssm.get_parameter.side_effect = RuntimeError("ssm down")
    else:
        fake_ssm.get_parameter.return_value = {
            "Parameter": {"Value": _json.dumps({"users": list(roster_users)})}
        }
    def fake_client(name, *a, **k):
        return {"secretsmanager": fake_sm, "lambda": fake_lambda, "ssm": fake_ssm}[name]
    fake_boto3 = types.SimpleNamespace(client=fake_client)
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    if "handler" in sys.modules:
        del sys.modules["handler"]
    mod = importlib.import_module("handler")
    monkeypatch.setattr(mod, "_post_message", MagicMock())
    return mod

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
    body = json.dumps({"type": "event_callback", "event": {"channel": "C01", "user": "U01", "text": "hi"}})
    resp = h.handler(_event(body), None)
    assert resp["statusCode"] == 200
    invoke.assert_called_once()
    kwargs = invoke.call_args.kwargs
    assert kwargs["InvocationType"] == "Event"
    assert kwargs["FunctionName"] == "worker-fn"

def test_slack_retry_is_acked_without_reinvoking(monkeypatch):
    invoke = MagicMock()
    h = _load_handler(monkeypatch, invoke)
    body = json.dumps({"type": "event_callback", "event": {"channel": "C01", "user": "U01", "text": "hi"}})
    ev = _event(body)
    ev["headers"]["x-slack-retry-num"] = "1"  # Slack marks re-deliveries
    resp = h.handler(ev, None)
    assert resp["statusCode"] == 200
    invoke.assert_not_called()  # no duplicate worker invocation

def test_bot_message_is_ignored(monkeypatch):
    invoke = MagicMock()
    h = _load_handler(monkeypatch, invoke)
    body = json.dumps({"type": "event_callback",
                       "event": {"type": "message", "bot_id": "B01", "text": "hi"}})
    resp = h.handler(_event(body), None)
    assert resp["statusCode"] == 200
    invoke.assert_not_called()

def test_subtype_message_is_ignored(monkeypatch):
    invoke = MagicMock()
    h = _load_handler(monkeypatch, invoke)
    body = json.dumps({"type": "event_callback",
                       "event": {"type": "message", "subtype": "message_changed", "text": "x"}})
    resp = h.handler(_event(body), None)
    assert resp["statusCode"] == 200
    invoke.assert_not_called()

def test_dm_message_is_forwarded(monkeypatch):
    invoke = MagicMock()
    h = _load_handler(monkeypatch, invoke)
    body = json.dumps({"type": "event_callback",
                       "event": {"type": "message", "channel": "D01", "user": "U01", "text": "hi"}})
    resp = h.handler(_event(body), None)
    assert resp["statusCode"] == 200
    invoke.assert_called_once()

def test_unauthorized_user_gets_reply_no_invoke(monkeypatch):
    invoke = MagicMock()
    h = _load_handler(monkeypatch, invoke, roster_users=("U99",))  # U01 not allowed
    body = json.dumps({"type": "event_callback",
                       "event": {"channel": "D01", "user": "U01", "text": "hi"}})
    resp = h.handler(_event(body), None)
    assert resp["statusCode"] == 200
    invoke.assert_not_called()
    h._post_message.assert_called_once()
    assert h._post_message.call_args.args[1] == "D01"  # replied to the DM channel

def test_authorized_user_is_forwarded(monkeypatch):
    invoke = MagicMock()
    h = _load_handler(monkeypatch, invoke, roster_users=("U01",))
    body = json.dumps({"type": "event_callback",
                       "event": {"channel": "D01", "user": "U01", "text": "hi"}})
    resp = h.handler(_event(body), None)
    invoke.assert_called_once()
    h._post_message.assert_not_called()

def test_roster_cached_within_ttl(monkeypatch):
    invoke = MagicMock()
    h = _load_handler(monkeypatch, invoke, roster_users=("U01",))
    body = json.dumps({"type": "event_callback",
                       "event": {"channel": "D01", "user": "U01", "text": "hi"}})
    ev = _event(body)
    h.handler(ev, None)
    h.handler(_event(body), None)
    fake_ssm = sys.modules["boto3"].client("ssm")
    assert fake_ssm.get_parameter.call_count == 1  # second call served from cache

def test_deny_reply_failure_still_acks(monkeypatch):
    invoke = MagicMock()
    h = _load_handler(monkeypatch, invoke, roster_users=("U99",))  # U01 not allowed
    h._post_message.side_effect = RuntimeError("slack down")
    body = json.dumps({"type": "event_callback",
                       "event": {"channel": "D01", "user": "U01", "text": "hi"}})
    resp = h.handler(_event(body), None)
    assert resp["statusCode"] == 200
    invoke.assert_not_called()

def test_ssm_failure_denies(monkeypatch):
    invoke = MagicMock()
    h = _load_handler(monkeypatch, invoke, ssm_raises=True)
    body = json.dumps({"type": "event_callback",
                       "event": {"channel": "D01", "user": "U01", "text": "hi"}})
    resp = h.handler(_event(body), None)
    assert resp["statusCode"] == 200
    invoke.assert_not_called()  # fail closed

def test_slash_kt_normalized_and_invoked(monkeypatch):
    invoke = MagicMock()
    h = _load_handler(monkeypatch, invoke, roster_users=("U01",))
    resp = h.handler(_slash_event(text="deployment"), None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["response_type"] == "ephemeral"
    invoke.assert_called_once()
    payload = json.loads(invoke.call_args.kwargs["Payload"])
    assert payload["mode"] == "kt"
    assert payload["text"] == "deployment"
    assert payload["reply"] == {"kind": "response_url", "target": "https://hooks.slack.test/cmd"}
    assert payload["user"] == "U01"

def test_slash_unauthorized_user_not_invoked(monkeypatch):
    invoke = MagicMock()
    h = _load_handler(monkeypatch, invoke, roster_users=("U99",))
    resp = h.handler(_slash_event(user="U01"), None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["response_type"] == "ephemeral"  # ask-admin ephemeral
    invoke.assert_not_called()

def test_event_normalized_to_qa(monkeypatch):
    invoke = MagicMock()
    h = _load_handler(monkeypatch, invoke, roster_users=("U01",))
    body = json.dumps({"type": "event_callback",
                       "event": {"channel": "D01", "user": "U01", "text": "how does auth work"}})
    resp = h.handler(_event(body), None)
    assert resp["statusCode"] == 200
    payload = json.loads(invoke.call_args.kwargs["Payload"])
    assert payload["mode"] == "qa"
    assert payload["text"] == "how does auth work"
    assert payload["reply"] == {"kind": "channel", "target": "D01"}
    assert payload["user"] == "U01"
