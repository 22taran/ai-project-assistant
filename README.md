# KT Assistant

A private **project knowledge assistant** on Slack. Team members DM the bot (or
@-mention it) and ask anything about the project; it answers grounded in your
docs, with source citations. Access is gated by an allow-list, so only approved
people get answers.

Built on AWS Bedrock Knowledge Bases + S3 Vectors, provisioned entirely with
Terraform.

---

## How it works

### Runtime — a question, answered

```
                          ┌─────────────────────────────────────────────┐
  Slack DM ──────────────▶│  ACK LAMBDA  (Function URL, auth=NONE)        │
  or @mention             │                                              │
                          │  1. verify Slack HMAC signature   → 401 bad  │
                          │  2. ignore Slack retries (dedupe)            │
                          │  3. loop guard: drop bot's own / system msgs │
                          │  4. roster check: user approved?             │
                          │       └─ no ─▶ "ask admin" reply, stop       │
                          │  5. async-invoke worker, return 200 (<3s)    │
                          └───────────────────────┬─────────────────────┘
                                                  │ InvocationType=Event
                                                  ▼
                          ┌─────────────────────────────────────────────┐
                          │  WORKER LAMBDA                               │
                          │  RetrieveAndGenerate ─▶ Bedrock KB           │
                          │  post answer + citations ─▶ chat.postMessage │
                          └───────────────────────┬─────────────────────┘
                                                  ▼
                     ┌───────────────┐   embed    ┌────────────────────┐
                     │ Bedrock KB    │──────query▶│ S3 Vectors index   │
                     │ Titan v2      │            │ (cosine, dim 1024) │
                     │ Nova Lite gen │            └────────────────────┘
                     └───────────────┘

  Secrets Manager: signing secret, bot token   │   SSM: roster (approved user IDs)
```

### Ingestion — docs become searchable

```
  S3 docs bucket ──start-ingestion-job──▶ Bedrock data source
     (your .md files)                         │ chunk: FIXED_SIZE 512 tok / 20% overlap
                                              ▼
                                       Titan v2 embed (1024-d)
                                              ▼
                                       S3 Vectors index  (AMAZON_BEDROCK_TEXT
                                                          + _METADATA non-filterable)
```

### Access model

```
  DM ─▶ ack reads roster from SSM (cached ~5 min, FAIL CLOSED on error)
        user in {"users":[...]}?  ── yes ─▶ answered
                                  ── no  ─▶ "ask admin" reply + logged to CloudWatch
```

---

## Repo layout

```
KT-assistant/
├── infra/
│   ├── modules/
│   │   ├── storage/        # docs S3 bucket + S3 Vectors bucket & index
│   │   ├── iam/            # least-privilege roles (KB, ack, worker), no wildcards
│   │   ├── bedrock-kb/     # knowledge base + S3 data source
│   │   └── slack-lambda/   # ack + worker Lambdas, Function URL, DLQ, SSM roster, grants
│   └── envs/dev/           # composes the modules, wires ARNs, builds model ARNs
├── src/
│   ├── ack/                # verify sig, loop guard, roster gate, async-invoke worker
│   └── worker/             # RetrieveAndGenerate + post to Slack
├── tests/                  # pytest (ack + worker)
├── docs/                   # sample project docs to seed the KB
└── docs/superpowers/       # design specs + implementation plans
```

---

## Setup — step by step

### Prerequisites
- AWS account with Bedrock enabled, AWS CLI configured, Terraform ≥ 1.9.
- **Bedrock model access** granted for **Amazon Titan Text Embeddings V2** and
  **Amazon Nova Lite** (Bedrock console → *Model access* → enable → wait "Access granted").
- A Slack workspace where you can create an app.

### 1. Create the Slack app
1. Go to **api.slack.com/apps → Create New App → From scratch**. Name it, pick your workspace.
2. **Basic Information → App Credentials** → copy the **Signing Secret**.
3. **OAuth & Permissions → Bot Token Scopes** → add: `app_mentions:read`, `chat:write`.
4. **Install to Workspace** → copy the **Bot User OAuth Token** (`xoxb-…`).

### 2. Store the secrets (never in Terraform state)
```bash
aws secretsmanager create-secret --name kt-assistant/signing-secret \
  --secret-string 'PASTE_SIGNING_SECRET' --region us-east-1
aws secretsmanager create-secret --name kt-assistant/bot-token \
  --secret-string 'xoxb-PASTE_BOT_TOKEN' --region us-east-1
```

### 3. Configure and deploy
```bash
cd infra/envs/dev
cp terraform.tfvars.example terraform.tfvars
# set: project_name, aws_region, environment,
#      signing_secret_name = "kt-assistant/signing-secret"
#      bot_token_name      = "kt-assistant/bot-token"
terraform init
terraform apply
```
> IAM role propagation is eventually consistent — a fresh `apply` can occasionally
> fail on Bedrock KB creation with `AccessDenied`. If so, just re-run `terraform apply`.

### 4. Seed docs and index them
```bash
KB=$(terraform output -raw knowledge_base_id)
REGION=us-east-1

# upload your project docs
aws s3 cp ../../../docs/ s3://<project>-<env>-docs/ --recursive --include "*.md" --region $REGION

# run an ingestion job
DS=$(aws bedrock-agent list-data-sources --knowledge-base-id $KB --region $REGION \
     --query 'dataSourceSummaries[0].dataSourceId' --output text)
JOB=$(aws bedrock-agent start-ingestion-job --knowledge-base-id $KB --data-source-id $DS \
      --region $REGION --query 'ingestionJob.ingestionJobId' --output text)

# wait for COMPLETE with documents indexed
aws bedrock-agent get-ingestion-job --knowledge-base-id $KB --data-source-id $DS \
    --ingestion-job-id $JOB --region $REGION \
    --query 'ingestionJob.{status:status,stats:statistics}'
```

### 5. Register the Slack event endpoint
```bash
terraform output -raw function_url
```
- Slack app → **Event Subscriptions** → toggle **On** → paste the Function URL as the **Request URL**.
- It must show **Verified ✓** (your ack Lambda answers Slack's signed challenge).

### 6. Turn on DMs
1. **App Home → Show Tabs → Messages Tab** → toggle **ON**, and tick
   **"Allow users to send Slash commands and messages from the messages tab."**
   *(The checkbox — not just the toggle — is what removes the "Sending messages to
   this app has been turned off" banner.)*
2. **Event Subscriptions → Subscribe to bot events** → add **`message.im`** → **Save**.
3. **OAuth & Permissions → Scopes** → add **`im:history`**.
4. **Reinstall to Workspace** (scopes changed).
5. **Reinstalling rotates the bot token** — update it and reload the Lambdas:
   ```bash
   aws secretsmanager put-secret-value --secret-id kt-assistant/bot-token \
     --secret-string 'xoxb-NEW-TOKEN' --region us-east-1
   aws lambda update-function-configuration --function-name <project>-<env>-ack \
     --description "reload $(date +%s)" --region us-east-1
   aws lambda update-function-configuration --function-name <project>-<env>-worker \
     --description "reload $(date +%s)" --region us-east-1
   ```
6. In Slack, **Cmd+R / restart** the client and reopen the bot's DM (the banner is cached).

### 7. Approve users (the roster)
The bot answers only approved Slack user IDs. Seed the roster:
```bash
aws ssm put-parameter --name /<project>-<env>/roster --overwrite \
  --value '{"users":["U01ALICE","U02BOB"]}' --region us-east-1
```
Changes go live within ~5 minutes (TTL cache), no redeploy.

### 8. Test
- DM the bot as an **approved** user → grounded answer + sources within ~10s.
- DM as a **non-roster** user → "ask your project admin" reply; their user ID is
  logged to CloudWatch so you can approve them.

---

## Administering access

**Find a user's Slack ID:**
- UI: profile → **⋮ → Copy member ID** (`U…`).
- From the bot: when someone unapproved DMs it, their ID is logged —
  `aws logs tail /aws/lambda/<project>-<env>-ack --since 1h | grep unauthorized`.
- API: `curl -H "Authorization: Bearer xoxb-…" "https://slack.com/api/users.lookupByEmail?email=alice@company.com"` (needs `users:read.email`).

**Add / remove:** edit the SSM roster JSON (`aws ssm put-parameter … --overwrite`).
Live within the TTL, no deploy. The roster is stored in SSM with Terraform
`ignore_changes` so applies never overwrite it.

---

## Swapping the generation model

Both model IDs are Terraform variables in `infra/envs/dev/variables.tf`:
```hcl
generation_model_id             = "amazon.nova-lite-v1:0"          # foundation-model (for IAM)
generation_inference_profile_id = "us.amazon.nova-lite-v1:0"       # profile (RetrieveAndGenerate modelArn)
```
Change both to switch (e.g. `amazon.nova-micro-v1:0` for cheapest, or
`anthropic.claude-haiku-4-5-20251001-v1:0` / `us.anthropic.claude-haiku-4-5-20251001-v1:0`
for stronger). Embedding model stays Titan v2, so **no re-ingestion** is needed —
`terraform apply` and you're done.

> Bedrock requires an **inference-profile** ARN (the `us.…` id) for on-demand
> RetrieveAndGenerate on Nova and Claude 3.5+. A bare `foundation-model/` ARN is
> rejected — that's why there are two variables.

---

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `"Sending messages to this app has been turned off"` | Tick the **checkbox** under App Home → Messages Tab (not just the toggle), reinstall, then **Cmd+R** the Slack client. |
| Two answers per question | Slack retried during a cold start. Handled by the retry guard; if it recurs, bump ack Lambda memory to cut cold-start latency. |
| Empty citations / "cannot find sufficient information" | The KB index has no vectors — run an ingestion job (step 4) and confirm `COMPLETE` with `numberOfDocumentsIndexed > 0`. |
| Sync fails: `Filterable metadata must have at most 2048 bytes` | The index must mark `AMAZON_BEDROCK_TEXT` + `AMAZON_BEDROCK_METADATA` **non-filterable** (already set in `infra/modules/storage`). |
| `on-demand throughput isn't supported for this model` | Use the **inference-profile** ARN (the `us.…` id), not a bare foundation-model ARN. |
| `Not authorized to call GetInferenceProfile` | The worker role needs `bedrock:GetInferenceProfile` (already granted in `infra/modules/iam`). |
| `Invalid Bedrock Foundation Model Parser Provided` | Don't set a `parsing_configuration` pointing an embedding model as a parser — markdown needs only chunking. |
| DM says "ask your project admin" for a real user | They're not in the SSM roster — add their user ID (step 7). |
| Bot answers nobody after deploy | The roster seeds empty (`{"users":[]}`) and fails **closed** — populate it (step 7). |

---

## Scope

- **Phase 1–6 built:** Bedrock KB over S3 Vectors + Slack channel mentions + private
  DM assistant with roster access control.
- **Deferred:** Confluence/Jira ingestion and an SSO web front door (the retrieval
  core is reusable for it). Confluence via Bedrock's native connector requires
  OpenSearch Serverless (~$345/mo floor) — a custom S3 sync keeps the cheap
  S3-Vectors setup. See `docs/superpowers/specs/`.
