import json, os, sys, types, pathlib
from unittest.mock import MagicMock
WORKER = pathlib.Path(__file__).resolve().parents[2] / "src" / "worker"
sys.path.insert(0, str(WORKER))

def _load(monkeypatch, rag_return):
    os.environ["KNOWLEDGE_BASE_ID"] = "KB1"
    os.environ["GENERATION_MODEL_ARN"] = "arn:model"
    os.environ["BOT_TOKEN_ARN"] = "arn:secret"
    os.environ["ASSISTANT_PROMPT"] = "QA $search_results$ $query$"
    os.environ["KT_PROMPT"] = "KT $search_results$ $query$"
    os.environ["GEN_TEMPERATURE"] = "0.2"
    os.environ["GEN_MAX_TOKENS"] = "512"
    fake_sm = MagicMock()
    fake_sm.get_secret_value.return_value = {"SecretString": "xoxb-token"}
    fake_agent = MagicMock()
    fake_agent.retrieve_and_generate.return_value = rag_return
    def fake_client(name, *a, **k):
        return {"secretsmanager": fake_sm, "bedrock-agent-runtime": fake_agent}[name]
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=fake_client))
    import importlib
    if "handler" in sys.modules:
        del sys.modules["handler"]
    mod = importlib.import_module("handler")
    return mod, fake_agent

def test_qa_mode_posts_to_channel(monkeypatch):
    rag = {"output": {"text": "auth uses JWT"}, "citations": []}
    h, agent = _load(monkeypatch, rag)
    post = MagicMock(); monkeypatch.setattr(h, "_post_message", post)
    event = {"mode": "qa", "text": "how does auth work",
             "reply": {"kind": "channel", "target": "D01"}, "user": "U01"}
    h.handler(event, None)
    # query is the raw text; QA prompt used
    call = agent.retrieve_and_generate.call_args.kwargs
    assert call["input"]["text"] == "how does auth work"
    gen = call["retrieveAndGenerateConfiguration"]["knowledgeBaseConfiguration"]["generationConfiguration"]
    assert gen["promptTemplate"]["textPromptTemplate"].startswith("QA ")
    post.assert_called_once()
    assert post.call_args.args[1] == "D01"
    assert "auth uses JWT" in post.call_args.args[2]

def test_kt_mode_builds_overview_and_posts_ephemeral(monkeypatch):
    rag = {"output": {"text": "Overview: ..."}, "citations": []}
    h, agent = _load(monkeypatch, rag)
    resp = MagicMock(); monkeypatch.setattr(h, "_post_response_url", resp)
    event = {"mode": "kt", "text": "deployment",
             "reply": {"kind": "response_url", "target": "https://hooks.slack.test/cmd"}, "user": "U01"}
    h.handler(event, None)
    call = agent.retrieve_and_generate.call_args.kwargs
    q = call["input"]["text"]
    assert "overview" in q.lower() and "deployment" in q.lower()
    gen = call["retrieveAndGenerateConfiguration"]["knowledgeBaseConfiguration"]["generationConfiguration"]
    assert gen["promptTemplate"]["textPromptTemplate"].startswith("KT ")
    resp.assert_called_once()
    assert resp.call_args.args[0] == "https://hooks.slack.test/cmd"
    assert "Overview" in resp.call_args.args[1]

def test_kt_empty_topic_is_whole_project(monkeypatch):
    rag = {"output": {"text": "x"}, "citations": []}
    h, agent = _load(monkeypatch, rag)
    monkeypatch.setattr(h, "_post_response_url", MagicMock())
    event = {"mode": "kt", "text": "",
             "reply": {"kind": "response_url", "target": "u"}, "user": "U01"}
    h.handler(event, None)
    q = agent.retrieve_and_generate.call_args.kwargs["input"]["text"]
    assert "overview" in q.lower()
