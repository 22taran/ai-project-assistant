import hashlib
import hmac
import time

MAX_SKEW_SECONDS = 300


def verify(signing_secret, timestamp, raw_body, signature, now=None):
    """Timing-safe Slack request verification with replay protection."""
    now = int(time.time()) if now is None else now
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(now - ts) > MAX_SKEW_SECONDS:
        return False
    if isinstance(raw_body, bytes):
        body = raw_body.decode("utf-8", "replace")
    else:
        body = raw_body
    base = f"v0:{timestamp}:{body}".encode()
    digest = hmac.new(signing_secret.encode(), base, hashlib.sha256).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, signature or "")
