import json
import os

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

    boto3.client("lambda").invoke(
        FunctionName=os.environ["WORKER_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps(payload).encode(),
    )
    return {"statusCode": 200, "body": ""}
