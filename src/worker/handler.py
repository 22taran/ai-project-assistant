import json
import os
import urllib.request

import boto3

from bedrock_client import retrieve_and_generate

_TOKEN = None

_NO_ANSWER = "I don't have that in the project docs yet — try rephrasing or ask a maintainer."
_KT_QUERY = ("Project overview: purpose, architecture, key components, "
             "how to run and deploy it, and where to learn more.")


def _bot_token():
    global _TOKEN
    if _TOKEN is None:
        arn = os.environ["BOT_TOKEN_ARN"]
        _TOKEN = boto3.client("secretsmanager").get_secret_value(SecretId=arn)["SecretString"]
    return _TOKEN


def _post_message(token, channel, text):
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps({"channel": channel, "text": text}).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.read()


def _post_response_url(url, text):
    req = urllib.request.Request(
        url,
        data=json.dumps({"response_type": "ephemeral", "text": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.read()
    except Exception:
        print("failed to post to response_url")


def _build_query(mode, text):
    if mode == "kt":
        t = (text or "").strip()
        return f"{_KT_QUERY} Focus specifically on: {t}" if t else _KT_QUERY
    return text or ""


def _deliver(reply, text):
    if reply.get("kind") == "response_url":
        _post_response_url(reply.get("target"), text)
    else:
        _post_message(_bot_token(), reply.get("target"), text)


def handler(event, context):
    mode = event.get("mode", "qa")
    text = event.get("text", "")
    reply = event.get("reply", {})

    prompts = {"qa": os.environ["ASSISTANT_PROMPT"], "kt": os.environ["KT_PROMPT"]}
    prompt = prompts.get(mode, prompts["qa"])
    query = _build_query(mode, text)

    agent = boto3.client("bedrock-agent-runtime")
    result = retrieve_and_generate(
        agent,
        os.environ["KNOWLEDGE_BASE_ID"],
        os.environ["GENERATION_MODEL_ARN"],
        query,
        prompt_template=prompt,
        temperature=float(os.environ.get("GEN_TEMPERATURE", "0.2")),
        max_tokens=int(os.environ.get("GEN_MAX_TOKENS", "512")),
    )

    out = result["answer"] or _NO_ANSWER
    if result["citations"]:
        out += "\n\nSources:\n" + "\n".join(f"• {c}" for c in result["citations"])

    _deliver(reply, out)
    return {"ok": True, "answer": out, "citations": result["citations"]}
