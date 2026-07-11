import json, os, sys, types, pathlib
from unittest.mock import MagicMock
WORKER = pathlib.Path(__file__).resolve().parents[2] / "lambda" / "worker"
sys.path.insert(0, str(WORKER))

def _load(monkeypatch, rag_return, post_mock):
    os.environ["KNOWLEDGE_BASE_ID"] = "KB1"
    os.environ["GENERATION_MODEL_ARN"] = "arn:model"
    os.environ["BOT_TOKEN_ARN"] = "arn:secret"
    fake_sm = MagicMock()
    fake_sm.get_secret_value.return_value = {"SecretString": "xoxb-token"}
    fake_agent = MagicMock()
    fake_agent.retrieve_and_generate.return_value = rag_return
    def fake_client(name, *a, **k):
        return {"secretsmanager": fake_sm, "bedrock-agent-runtime": fake_agent}[name]
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=fake_client))
    # stub urllib post
    import importlib
    if "handler" in sys.modules:
        del sys.modules["handler"]
    mod = importlib.import_module("handler")
    monkeypatch.setattr(mod, "_post_message", post_mock)
    return mod

def test_posts_answer_to_channel(monkeypatch):
    post = MagicMock()
    rag = {"output": {"text": "hello"}, "citations": []}
    h = _load(monkeypatch, rag, post)
    event = {"event": {"channel": "C123", "text": "hi there"}}
    h.handler(event, None)
    post.assert_called_once()
    args = post.call_args.args
    assert args[1] == "C123"          # channel
    assert "hello" in args[2]          # message text
