import sys, pathlib
from unittest.mock import MagicMock
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "lambda" / "worker"))
from bedrock_client import retrieve_and_generate

def test_returns_answer_and_citations():
    client = MagicMock()
    client.retrieve_and_generate.return_value = {
        "output": {"text": "The answer is 42."},
        "citations": [
            {"retrievedReferences": [
                {"location": {"s3Location": {"uri": "s3://docs/a.md"}}}
            ]}
        ],
    }
    out = retrieve_and_generate(client, "KB123", "arn:model", "what is it?")
    assert out["answer"] == "The answer is 42."
    assert out["citations"] == ["s3://docs/a.md"]
    call = client.retrieve_and_generate.call_args.kwargs
    assert call["input"]["text"] == "what is it?"
    cfg = call["retrieveAndGenerateConfiguration"]["knowledgeBaseConfiguration"]
    assert cfg["knowledgeBaseId"] == "KB123"
    assert cfg["modelArn"] == "arn:model"
