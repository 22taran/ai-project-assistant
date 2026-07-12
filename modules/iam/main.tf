data "aws_iam_policy_document" "kb_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "kb" {
  name               = "${var.name_prefix}-kb-role"
  assume_role_policy = data.aws_iam_policy_document.kb_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "kb" {
  statement {
    sid       = "InvokeEmbeddingModel"
    actions   = ["bedrock:InvokeModel"]
    resources = [var.embedding_model_arn]
  }
  statement {
    sid       = "ReadDocs"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [var.docs_bucket_arn, "${var.docs_bucket_arn}/*"]
  }
  statement {
    sid = "VectorOps"
    actions = [
      "s3vectors:PutVectors",
      "s3vectors:GetVectors",
      "s3vectors:QueryVectors",
      "s3vectors:ListVectors",
      "s3vectors:DeleteVectors",
    ]
    resources = [var.vector_index_arn]
  }
}

resource "aws_iam_role_policy" "kb" {
  name   = "${var.name_prefix}-kb-policy"
  role   = aws_iam_role.kb.id
  policy = data.aws_iam_policy_document.kb.json
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# ---- Ack Lambda role ----
resource "aws_iam_role" "ack" {
  name               = "${var.name_prefix}-ack-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "ack" {
  # InvokeWorker grant lives in root (Task 9 Step 3) to avoid a cycle.
  statement {
    sid       = "ReadSigningSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.signing_secret_arn]
  }
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:log-group:/aws/lambda/${var.name_prefix}-ack:*"]
  }
}

resource "aws_iam_role_policy" "ack" {
  name   = "${var.name_prefix}-ack-policy"
  role   = aws_iam_role.ack.id
  policy = data.aws_iam_policy_document.ack.json
}

# ---- Worker Lambda role ----
resource "aws_iam_role" "worker" {
  name               = "${var.name_prefix}-worker-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "worker" {
  # RetrieveAndGenerate/Retrieve on the KB lives in root (Task 9 Step 3) to
  # avoid a cycle. Only the static-ARN grants live here.
  statement {
    sid       = "InvokeGenModel"
    actions   = ["bedrock:InvokeModel", "bedrock:GetInferenceProfile"]
    resources = var.generation_model_arns
  }
  statement {
    sid       = "ReadBotToken"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.bot_token_arn]
  }
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:log-group:/aws/lambda/${var.name_prefix}-worker:*"]
  }
}

resource "aws_iam_role_policy" "worker" {
  name   = "${var.name_prefix}-worker-policy"
  role   = aws_iam_role.worker.id
  policy = data.aws_iam_policy_document.worker.json
}
