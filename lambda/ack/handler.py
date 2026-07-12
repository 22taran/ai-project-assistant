import json
import os
import time

import boto3

from slack_verify import verify

_SECRET = None


def _signing_secret():
    global _SECRET
    if _SECRET is None:
        arn = os.environ["SLACK_SIGNING_SECRET_ARN"]
        sm = boto3.client("secretsmanager")
        _SECRET = sm.get_secret_value(SecretId=arn)["SecretString"]
    return _SECRET


_ROSTER = None
_ROSTER_AT = 0.0
ROSTER_TTL = 300  # seconds
_TOKEN = None


def _roster():
    """Approved Slack user IDs from SSM. Cached with a TTL. Fail closed."""
    global _ROSTER, _ROSTER_AT
    now = time.time()
    if _ROSTER is None or now - _ROSTER_AT > ROSTER_TTL:
        try:
            name = os.environ["ROSTER_PARAM_NAME"]
            raw = boto3.client("ssm").get_parameter(Name=name)["Parameter"]["Value"]
            _ROSTER = set(json.loads(raw).get("users", []))
            _ROSTER_AT = now
        except Exception:
            # Fail closed: an SSM error must not open access.
            return set()
    return _ROSTER


def _bot_token():
    global _TOKEN
    if _TOKEN is None:
        arn = os.environ["BOT_TOKEN_ARN"]
        _TOKEN = boto3.client("secretsmanager").get_secret_value(SecretId=arn)["SecretString"]
    return _TOKEN


def _post_message(token, channel, text):
    import urllib.request
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps({"channel": channel, "text": text}).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.read()


def _get(headers, key):
    for k, v in (headers or {}).items():
        if k.lower() == key:
            return v
    return None


def handler(event, context):
    headers = event.get("headers", {})
    raw = event.get("body", "") or ""
    if event.get("isBase64Encoded"):
        import base64
        raw = base64.b64decode(raw).decode("utf-8", "replace")

    sig = _get(headers, "x-slack-signature")
    ts = _get(headers, "x-slack-request-timestamp")
    if not verify(_signing_secret(), ts, raw.encode(), sig):
        return {"statusCode": 401, "body": "invalid signature"}

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}

    if payload.get("type") == "url_verification":
        return {"statusCode": 200, "body": json.dumps({"challenge": payload.get("challenge")})}

    # Slack re-delivers an event if it doesn't get a 200 within 3s (e.g. a cold
    # start). Retries carry X-Slack-Retry-Num; ack them without re-invoking the
    # worker, otherwise one question yields duplicate answers.
    if _get(headers, "x-slack-retry-num"):
        return {"statusCode": 200, "body": "duplicate retry ignored"}

    # Slack's message.im fires on every DM message, including the bot's own
    # replies and system notices (joins, edits). Drop anything that isn't a
    # human message, or the bot answers itself in a loop.
    inner = payload.get("event", {})
    if inner.get("bot_id") or inner.get("subtype"):
        return {"statusCode": 200, "body": "ignored non-user event"}

    user = inner.get("user")
    if user not in _roster():
        print(f"unauthorized user {user} team {payload.get('team_id')}")
        _post_message(
            _bot_token(),
            inner.get("channel"),
            "You're not set up for the project assistant yet — ask your project admin to add you.",
        )
        return {"statusCode": 200, "body": "user not in roster"}

    boto3.client("lambda").invoke(
        FunctionName=os.environ["WORKER_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps(payload).encode(),
    )
    return {"statusCode": 200, "body": ""}
