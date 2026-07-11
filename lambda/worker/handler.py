import json
import os
import urllib.request

import boto3

from bedrock_client import retrieve_and_generate

_TOKEN = None


def _bot_token():
    global _TOKEN
    if _TOKEN is None:
        arn = os.environ["BOT_TOKEN_ARN"]
        sm = boto3.client("secretsmanager")
        _TOKEN = sm.get_secret_value(SecretId=arn)["SecretString"]
    return _TOKEN


def _post_message(token, channel, text):
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps({"channel": channel, "text": text}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urllib.request.urlopen(req) as r:
        return r.read()


def handler(event, context):
    slack_event = event.get("event", {})
    channel = slack_event.get("channel")
    question = slack_event.get("text", "")

    agent = boto3.client("bedrock-agent-runtime")
    result = retrieve_and_generate(
        agent,
        os.environ["KNOWLEDGE_BASE_ID"],
        os.environ["GENERATION_MODEL_ARN"],
        question,
    )

    text = result["answer"] or "I don't know based on the current docs."
    if result["citations"]:
        text += "\n\nSources:\n" + "\n".join(f"• {c}" for c in result["citations"])

    _post_message(_bot_token(), channel, text)
    return {"ok": True}
