variable "project_name" {
  type        = string
  description = "Short project slug; used to derive resource names."
  validation {
    condition     = can(regex("^[a-z0-9-]{3,30}$", var.project_name))
    error_message = "project_name must be 3-30 chars, lowercase letters/digits/hyphens."
  }
}

variable "aws_region" {
  type        = string
  description = "AWS region for all resources."
}

variable "environment" {
  type        = string
  description = "Deployment environment (e.g. dev, prod)."
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of dev, staging, prod."
  }
}

variable "embedding_model_id" {
  type    = string
  default = "amazon.titan-embed-text-v2:0"
}

variable "generation_model_id" {
  type    = string
  default = "amazon.nova-lite-v1:0"
}

variable "generation_inference_profile_id" {
  type        = string
  default     = "us.amazon.nova-lite-v1:0"
  description = "Bedrock system-defined inference profile ID for the generation model (geo-prefixed). Used as the RetrieveAndGenerate modelArn."
}

variable "signing_secret_name" {
  type        = string
  description = "Name of the pre-existing Secrets Manager secret holding the Slack signing secret."
}

variable "bot_token_name" {
  type        = string
  description = "Name of the pre-existing Secrets Manager secret holding the Slack bot token."
}
