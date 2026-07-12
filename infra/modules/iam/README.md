# iam module

Three least-privilege roles: Bedrock KB service role, ack Lambda role, worker
Lambda role. No wildcard resources — every statement targets a specific ARN.
Runtime Bedrock actions use the `bedrock:` prefix (not `bedrock-agent-runtime:`).
