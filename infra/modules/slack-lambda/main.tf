terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.27"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

data "archive_file" "ack" {
  type        = "zip"
  source_dir  = var.ack_source_dir
  output_path = "${path.module}/.build/ack.zip"
}

data "archive_file" "worker" {
  type        = "zip"
  source_dir  = var.worker_source_dir
  output_path = "${path.module}/.build/worker.zip"
}

# ---- DLQ for failed async worker invocations ----
resource "aws_sqs_queue" "worker_dlq" {
  name = "${var.name_prefix}-worker-dlq"
  tags = var.tags
}

# ---- Worker Lambda ----
resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${var.name_prefix}-worker"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_lambda_function" "worker" {
  function_name    = "${var.name_prefix}-worker"
  role             = var.worker_role_arn
  runtime          = "python3.13"
  handler          = "handler.handler"
  filename         = data.archive_file.worker.output_path
  source_code_hash = data.archive_file.worker.output_base64sha256
  timeout          = 30
  tags             = var.tags

  environment {
    variables = {
      KNOWLEDGE_BASE_ID    = var.knowledge_base_id
      GENERATION_MODEL_ARN = var.generation_model_arn
      BOT_TOKEN_ARN        = var.bot_token_arn
      ASSISTANT_PROMPT     = var.assistant_prompt
      KT_PROMPT            = var.kt_prompt
      GEN_TEMPERATURE      = tostring(var.gen_temperature)
      GEN_MAX_TOKENS       = tostring(var.gen_max_tokens)
    }
  }
  depends_on = [aws_cloudwatch_log_group.worker]
}

resource "aws_lambda_function_event_invoke_config" "worker" {
  function_name = aws_lambda_function.worker.function_name
  destination_config {
    on_failure {
      destination = aws_sqs_queue.worker_dlq.arn
    }
  }
}

# ---- Ack Lambda ----
resource "aws_cloudwatch_log_group" "ack" {
  name              = "/aws/lambda/${var.name_prefix}-ack"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_lambda_function" "ack" {
  function_name    = "${var.name_prefix}-ack"
  role             = var.ack_role_arn
  runtime          = "python3.13"
  handler          = "handler.handler"
  filename         = data.archive_file.ack.output_path
  source_code_hash = data.archive_file.ack.output_base64sha256
  timeout          = 5
  tags             = var.tags

  environment {
    variables = {
      SLACK_SIGNING_SECRET_ARN = var.signing_secret_arn
      WORKER_FUNCTION_NAME     = aws_lambda_function.worker.function_name
      ROSTER_PARAM_NAME        = aws_ssm_parameter.roster.name
      BOT_TOKEN_ARN            = var.bot_token_arn
    }
  }
  depends_on = [aws_cloudwatch_log_group.ack]
}

resource "aws_lambda_function_url" "ack" {
  function_name      = aws_lambda_function.ack.function_name
  authorization_type = "NONE"
}

# ---- Worker -> DLQ grant ----
# worker_role_name comes directly from modules/iam's worker_role_name output
# (passed in by the root env), avoiding a fragile split() on the role ARN.
data "aws_iam_policy_document" "worker_dlq" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.worker_dlq.arn]
  }
}

resource "aws_iam_role_policy" "worker_dlq" {
  name   = "${var.name_prefix}-worker-dlq"
  role   = var.worker_role_name
  policy = data.aws_iam_policy_document.worker_dlq.json
}

# ---- Roster allow-list (edited out-of-band by admins) ----
resource "aws_ssm_parameter" "roster" {
  name  = "/${var.name_prefix}/roster"
  type  = "String"
  value = jsonencode({ users = [] })
  tags  = var.tags
  lifecycle {
    ignore_changes = [value] # admins edit the roster in the console; don't revert it
  }
}

data "aws_iam_policy_document" "ack_access" {
  statement {
    sid       = "ReadRoster"
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.roster.arn]
  }
  statement {
    sid       = "ReadBotToken"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.bot_token_arn]
  }
}

resource "aws_iam_role_policy" "ack_access" {
  name   = "${var.name_prefix}-ack-access"
  role   = var.ack_role_name
  policy = data.aws_iam_policy_document.ack_access.json
}
