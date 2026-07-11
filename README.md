# KT Assistant

Slack → Lambda Function URL → Bedrock Knowledge Base (S3 Vectors) → S3 docs.
Ask a question in Slack; get an answer grounded in project docs, with citations.

## Layout
- `modules/storage` — docs bucket + S3 Vectors bucket & index
- `modules/iam` — least-privilege roles (KB, ack, worker), no wildcards
- `modules/bedrock-kb` — knowledge base + S3 data source
- `modules/slack-lambda` — ack + worker Lambdas, Function URL, DLQ
- `envs/dev` — composes the modules
- `lambda/ack`, `lambda/worker` — handler code

## Prereqs (out-of-band, never in Terraform state)
Create two Secrets Manager secrets with the Slack signing secret and bot token:

    aws secretsmanager create-secret --name kt-assistant/signing-secret --secret-string '<value>'
    aws secretsmanager create-secret --name kt-assistant/bot-token --secret-string '<value>'

## Deploy

    cd envs/dev
    cp terraform.tfvars.example terraform.tfvars   # set signing_secret_name + bot_token_name
    terraform init
    terraform apply

## Sync docs into the KB

    aws bedrock-agent start-ingestion-job \
      --knowledge-base-id "$(terraform output -raw knowledge_base_id)" \
      --data-source-id <data_source_id>

## Scope
Phase 1–4 only. Confluence/OpenSearch (Phase 5) is deferred — it changes the cost
profile (~$345/mo OpenSearch floor). Do not enable without a budget alert.
