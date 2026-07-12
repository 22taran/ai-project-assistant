locals {
  name_prefix = "${var.project_name}-${var.environment}"
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

module "storage" {
  source      = "../../modules/storage"
  name_prefix = local.name_prefix
  tags        = local.common_tags
}

data "aws_caller_identity" "current" {}

data "aws_secretsmanager_secret" "signing" {
  name = var.signing_secret_name
}
data "aws_secretsmanager_secret" "bot_token" {
  name = var.bot_token_name
}

locals {
  embedding_model_arn = "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.embedding_model_id}"
  # Inference-profile ARN: Claude Haiku 4.5 rejects on-demand RetrieveAndGenerate
  # with a bare foundation-model ARN, so this is the modelArn passed to the worker.
  generation_model_arn = "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.generation_inference_profile_id}"
  # Underlying foundation-model ARN(s) the inference profile routes to; region wildcard,
  # specific model — needed so the worker's InvokeModel grant matches at runtime.
  generation_foundation_model_arn = "arn:aws:bedrock:*::foundation-model/${var.generation_model_id}"
}

module "iam" {
  source                = "../../modules/iam"
  name_prefix           = local.name_prefix
  tags                  = local.common_tags
  docs_bucket_arn       = module.storage.docs_bucket_arn
  vector_index_arn      = module.storage.vector_index_arn
  embedding_model_arn   = local.embedding_model_arn
  generation_model_arns = [local.generation_model_arn, local.generation_foundation_model_arn]
  signing_secret_arn    = data.aws_secretsmanager_secret.signing.arn
  bot_token_arn         = data.aws_secretsmanager_secret.bot_token.arn
}

module "bedrock_kb" {
  source              = "../../modules/bedrock-kb"
  name_prefix         = local.name_prefix
  tags                = local.common_tags
  kb_role_arn         = module.iam.kb_role_arn
  embedding_model_arn = local.embedding_model_arn
  vector_bucket_arn   = module.storage.vector_bucket_arn
  vector_index_arn    = module.storage.vector_index_arn
  docs_bucket_arn     = module.storage.docs_bucket_arn
  kb_role_policy_dep  = module.iam.kb_role_policy_id
}

module "slack_lambda" {
  source               = "../../modules/slack-lambda"
  name_prefix          = local.name_prefix
  tags                 = local.common_tags
  ack_role_arn         = module.iam.ack_role_arn
  worker_role_arn      = module.iam.worker_role_arn
  worker_role_name     = module.iam.worker_role_name
  knowledge_base_id    = module.bedrock_kb.knowledge_base_id
  generation_model_arn = local.generation_model_arn
  signing_secret_arn   = data.aws_secretsmanager_secret.signing.arn
  bot_token_arn        = data.aws_secretsmanager_secret.bot_token.arn
  ack_source_dir       = "${path.root}/../../lambda/ack"
  worker_source_dir    = "${path.root}/../../lambda/worker"
}

# --- Deferred grants attached at root to break the two module cycles ---
# These are intentionally NOT in the iam module: passing the KB ARN or the worker
# function ARN into iam would make iam depend on bedrock_kb / slack_lambda, which
# already depend on iam. Attaching them here closes the graph acyclically.

# worker role → RetrieveAndGenerate/Retrieve on the KB (attached post-KB)
data "aws_iam_policy_document" "worker_kb" {
  statement {
    actions   = ["bedrock:RetrieveAndGenerate", "bedrock:Retrieve"]
    resources = [module.bedrock_kb.knowledge_base_arn]
  }
}

resource "aws_iam_role_policy" "worker_kb" {
  name   = "${local.name_prefix}-worker-kb"
  role   = module.iam.worker_role_name
  policy = data.aws_iam_policy_document.worker_kb.json
}

# ack role → InvokeFunction on the worker (attached post-lambda)
data "aws_iam_policy_document" "ack_invoke" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = [module.slack_lambda.worker_function_arn]
  }
}

resource "aws_iam_role_policy" "ack_invoke" {
  name   = "${local.name_prefix}-ack-invoke"
  role   = module.iam.ack_role_name
  policy = data.aws_iam_policy_document.ack_invoke.json
}
