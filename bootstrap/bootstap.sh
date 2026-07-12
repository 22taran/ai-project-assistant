#!/usr/bin/env bash
# =============================================================================
# Bootstrap script: creates S3 bucket for Terraform remote state
# - Versioning enabled (for state history, recovery, and S3-native locking)
# - Server-side encryption (AES-256 or KMS with key rotation)
# - Block public access
# - Uses S3 + use_lockfile for state locking (no DynamoDB)
# - Optional: KMS encryption (audit trail, key rotation, stricter access control)
# - Optional: DynamoDB table for locking (teams with concurrent runs)
# =============================================================================

set -euo pipefail

# Load .env from script directory if present (project_name, environment, etc.)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$SCRIPT_DIR/.env"
  set +a
fi

# ---- Config (override via env or edit here) ----
# Bucket name = terraform-state-{project}-{env}-{timestamp} (PROJECT_NAME and ENVIRONMENT required)
if [[ -z "${PROJECT_NAME:-}" || -z "${ENVIRONMENT:-}" ]]; then
  echo "Error: PROJECT_NAME and ENVIRONMENT are required (set in .env or export)." >&2
  echo "  cp .env.example .env && edit .env" >&2
  exit 1
fi
SANITIZED_PROJECT=$(echo "${PROJECT_NAME}" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9.-')
SANITIZED_ENV=$(echo "${ENVIRONMENT}" | tr '[:upper:] ' '[:lower:]-' | tr -cd 'a-z0-9.-')
TIMESTAMP=$(date +%Y%m%d%H%M%S)
BUCKET_NAME="terraform-state-${SANITIZED_PROJECT}-${SANITIZED_ENV}-${TIMESTAMP}"
REGION="${AWS_REGION:-us-east-2}"
LOCK_TABLE_NAME="${TF_LOCK_TABLE:-terraform-state-lock}"
CREATE_LOCK_TABLE="${CREATE_LOCK_TABLE:-false}"
USE_KMS="${USE_KMS:-false}"

# ---- Help ----
usage() {
  cat <<EOF
Usage: $0 [OPTIONS]

Creates an S3 bucket for Terraform remote state with versioning and encryption.

Environment variables (required in .env):
  PROJECT_NAME         Project name (must match terraform.tfvars)
  ENVIRONMENT          Environment: dev, staging, prod

Environment variables (optional):
  AWS_REGION           AWS region (default: us-east-2)
  TF_LOCK_TABLE        DynamoDB table name (only if CREATE_LOCK_TABLE=true)
  CREATE_LOCK_TABLE    Set to "true" to create DynamoDB for team locking (default: false, S3-only)
  USE_KMS              Set to "true" for KMS encryption (default: false, uses AES-256)

Bucket name is derived: terraform-state-{project}-{env}-{timestamp}

Options:
  -r, --region REGION  Override AWS region
  -k, --kms            Use KMS encryption (key rotation, CloudTrail audit)
  -d, --dynamodb       Create DynamoDB table for state locking (for teams)
  -h, --help           Show this help

Examples:
  source .env && $0
  $0 -r us-west-2
  $0 -k                           # KMS encryption (recommended for prod)
EOF
  exit 0
}

# ---- Parse args ----
while [[ $# -gt 0 ]]; do
  case $1 in
    -r|--region)   REGION="$2"; shift 2 ;;
    -k|--kms)      USE_KMS="true"; shift ;;
    -d|--dynamodb)     CREATE_LOCK_TABLE="true"; shift ;;
    -h|--help)     usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

# ---- Sanity checks ----
if ! command -v aws &>/dev/null; then
  echo "Error: AWS CLI is required. Install: https://aws.amazon.com/cli/" >&2
  exit 1
fi

if ! aws sts get-caller-identity &>/dev/null; then
  echo "Error: AWS credentials not configured. Run: aws configure" >&2
  exit 1
fi

# S3 bucket names must be globally unique and follow naming rules
if [[ ! "$BUCKET_NAME" =~ ^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$ ]]; then
  echo "Error: Invalid bucket name '$BUCKET_NAME'. Use lowercase, numbers, hyphens; 3-63 chars." >&2
  exit 1
fi

echo "Creating Terraform state backend resources..."
echo "  Bucket: $BUCKET_NAME"
echo "  Region: $REGION"
echo "  Encryption: $([ "$USE_KMS" = "true" ] && echo "KMS (key rotation, audit)" || echo "AES-256")"
echo "  State locking: $([ "$CREATE_LOCK_TABLE" = "true" ] && echo "DynamoDB" || echo "S3 (versioning + use_lockfile)")"
echo

# ---- Create S3 bucket ----
if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
  echo "Bucket '$BUCKET_NAME' already exists. Ensuring versioning and encryption..."
else
  echo "Creating S3 bucket: $BUCKET_NAME"
  aws s3api create-bucket \
    --bucket "$BUCKET_NAME" \
    --region "$REGION" \
    $( [[ "$REGION" != "us-east-1" ]] && echo "--create-bucket-configuration LocationConstraint=$REGION" )
fi

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket "$BUCKET_NAME" \
  --versioning-configuration Status=Enabled

# Enable default encryption (AES-256 or KMS)
KMS_KEY_ALIAS=""
if [[ "$USE_KMS" == "true" ]]; then
  KMS_ALIAS_NAME="alias/terraform-state-$(echo "$BUCKET_NAME" | tr '.[]' '-' | cut -c1-32)"
  # Create KMS key if alias doesn't exist
  if ! aws kms describe-key --key-id "$KMS_ALIAS_NAME" --region "$REGION" 2>/dev/null; then
    echo "Creating KMS key for state encryption..."
    KMS_KEY_ID=$(aws kms create-key \
      --description "Terraform state encryption for $BUCKET_NAME" \
      --key-usage ENCRYPT_DECRYPT \
      --origin AWS_KMS \
      --region "$REGION" \
      --query 'KeyMetadata.KeyId' --output text)
    aws kms enable-key-rotation --key-id "$KMS_KEY_ID" --region "$REGION"
    aws kms create-alias --alias-name "$KMS_ALIAS_NAME" --target-key-id "$KMS_KEY_ID" --region "$REGION"
    echo "✓ KMS key created: $KMS_ALIAS_NAME"
  fi
  KMS_KEY_ARN=$(aws kms describe-key --key-id "$KMS_ALIAS_NAME" --region "$REGION" --query 'KeyMetadata.Arn' --output text)
  aws s3api put-bucket-encryption \
    --bucket "$BUCKET_NAME" \
    --server-side-encryption-configuration "{
      \"Rules\": [{
        \"ApplyServerSideEncryptionByDefault\": {
          \"SSEAlgorithm\": \"aws:kms\",
          \"KMSMasterKeyID\": \"$KMS_KEY_ARN\"
        },
        \"BucketKeyEnabled\": true
      }]
    }"
  KMS_KEY_ALIAS="$KMS_ALIAS_NAME"
else
  aws s3api put-bucket-encryption \
    --bucket "$BUCKET_NAME" \
    --server-side-encryption-configuration '{
      "Rules": [{
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "AES256"
        },
        "BucketKeyEnabled": true
      }]
    }'
fi

# Block public access
aws s3api put-public-access-block \
  --bucket "$BUCKET_NAME" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "✓ S3 bucket '$BUCKET_NAME' ready (versioning + $([ "$USE_KMS" = "true" ] && echo "KMS" || echo "AES-256") encryption)"

# ---- Create DynamoDB table for state locking (optional; for teams) ----
if [[ "$CREATE_LOCK_TABLE" == "true" ]]; then
  if aws dynamodb describe-table --table-name "$LOCK_TABLE_NAME" --region "$REGION" 2>/dev/null; then
    echo "DynamoDB table '$LOCK_TABLE_NAME' already exists."
  else
    echo "Creating DynamoDB lock table: $LOCK_TABLE_NAME"
    aws dynamodb create-table \
      --table-name "$LOCK_TABLE_NAME" \
      --attribute-definitions AttributeName=LockID,AttributeType=S \
      --key-schema AttributeName=LockID,KeyType=HASH \
      --billing-mode PAY_PER_REQUEST \
      --region "$REGION"
    echo "Waiting for table to be active..."
    aws dynamodb wait table-exists --table-name "$LOCK_TABLE_NAME" --region "$REGION"
    echo "✓ DynamoDB table '$LOCK_TABLE_NAME' created"
  fi

  echo
  echo "Add to your terraform backend block:"
  echo "  dynamodb_table = \"$LOCK_TABLE_NAME\""
fi

echo
echo "Add to environments/dev/versions.tf (or equivalent):"
echo ---
if [[ "$USE_KMS" == "true" && -n "$KMS_KEY_ALIAS" ]]; then
  KMS_BLOCK="
    kms_key_id    = \"$KMS_KEY_ALIAS\""
fi
if [[ "$CREATE_LOCK_TABLE" == "true" ]]; then
  cat <<TF
  backend "s3" {
    bucket         = "$BUCKET_NAME"
    key            = "environments/dev/terraform.tfstate"
    region         = "$REGION"
    encrypt        = true${KMS_BLOCK:-}
    dynamodb_table = "$LOCK_TABLE_NAME"
    use_lockfile   = true
  }
TF
else
  cat <<TF
  backend "s3" {
    bucket       = "$BUCKET_NAME"
    key          = "environments/dev/terraform.tfstate"
    region       = "$REGION"
    encrypt      = true${KMS_BLOCK:-}
    use_lockfile = true
  }
TF
fi
echo ---
echo
echo "Bootstrap complete."