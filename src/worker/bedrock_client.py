def retrieve_and_generate(client, kb_id, model_arn, question,
                          prompt_template="", temperature=None, max_tokens=None):
    kb_config = {
        "knowledgeBaseId": kb_id,
        "modelArn": model_arn,
    }
    gen = {}
    if prompt_template:
        gen["promptTemplate"] = {"textPromptTemplate": prompt_template}
    if temperature is not None or max_tokens is not None:
        tic = {}
        if temperature is not None:
            tic["temperature"] = temperature
        if max_tokens is not None:
            tic["maxTokens"] = max_tokens
        gen["inferenceConfig"] = {"textInferenceConfig": tic}
    if gen:
        kb_config["generationConfiguration"] = gen

    resp = client.retrieve_and_generate(
        input={"text": question},
        retrieveAndGenerateConfiguration={
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": kb_config,
        },
    )
    answer = resp.get("output", {}).get("text", "")
    citations = []
    for c in resp.get("citations", []):
        for ref in c.get("retrievedReferences", []):
            uri = ref.get("location", {}).get("s3Location", {}).get("uri")
            if uri:
                citations.append(uri)
    return {"answer": answer, "citations": citations}
