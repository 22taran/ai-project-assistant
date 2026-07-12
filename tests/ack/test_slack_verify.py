import hashlib, hmac, time
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "lambda" / "ack"))
from slack_verify import verify

SECRET = "s3cr3t"

def _sign(ts, body):
    base = f"v0:{ts}:{body}".encode()
    digest = hmac.new(SECRET.encode(), base, hashlib.sha256).hexdigest()
    return f"v0={digest}"

def test_valid_signature_passes():
    ts = str(int(time.time()))
    body = "token=abc&challenge=xyz"
    sig = _sign(ts, body)
    assert verify(SECRET, ts, body.encode(), sig, now=int(ts)) is True

def test_wrong_signature_fails():
    ts = str(int(time.time()))
    assert verify(SECRET, ts, b"body", "v0=deadbeef", now=int(ts)) is False

def test_stale_timestamp_fails():
    ts = str(int(time.time()) - 400)  # 400s old > 300s window
    body = "x"
    sig = _sign(ts, body)
    assert verify(SECRET, ts, body.encode(), sig, now=int(time.time())) is False

def test_future_timestamp_fails():
    now = int(time.time())
    ts = str(now + 400)
    body = "x"
    sig = _sign(ts, body)
    assert verify(SECRET, ts, body.encode(), sig, now=now) is False
