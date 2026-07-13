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

variable "assistant_prompt" {
  type    = string
  default = <<-EOT
    You are the project's assistant. Answer using ONLY the information in the search results below. If the answer isn't there, say: "I don't have that in the project docs yet — try rephrasing or ask a maintainer." Never guess or invent APIs, paths, or commands. Be concise; use short paragraphs or bullets. Briefly expand acronyms. When helpful, name the doc the answer came from.

    Search results:
    $search_results$

    Question: $query$
  EOT
}

variable "kt_prompt" {
  type    = string
  default = <<-EOT
    You are the project's Knowledge Transfer assistant producing an onboarding overview. Using ONLY the search results below, produce a structured brief covering: what the project is, its main components, how to run/deploy it, and where to learn more. Use clear headings and bullets. If a section has no supporting information in the search results, omit it rather than guessing.

    Search results:
    $search_results$

    Topic focus (may be empty for a whole-project overview): $query$
  EOT
}

variable "gen_temperature" {
  type    = number
  default = 0.2
}

variable "gen_max_tokens" {
  type    = number
  default = 512
}
