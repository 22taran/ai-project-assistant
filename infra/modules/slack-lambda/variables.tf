variable "name_prefix" { type = string }
variable "tags" { type = map(string) }
variable "ack_role_arn" { type = string }
variable "worker_role_arn" { type = string }
variable "worker_role_name" { type = string }

variable "ack_role_name" {
  type        = string
  description = "Name of the ack Lambda IAM role (for inline roster/bot-token grants)."
}
variable "knowledge_base_id" { type = string }
variable "generation_model_arn" { type = string }
variable "signing_secret_arn" { type = string }
variable "bot_token_arn" { type = string }
variable "ack_source_dir" { type = string }
variable "worker_source_dir" { type = string }

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "assistant_prompt" {
  type        = string
  description = "Prompt template for default Q&A mode (must contain $search_results$)."
}

variable "kt_prompt" {
  type        = string
  description = "Prompt template for /kt overview mode (must contain $search_results$)."
}

variable "gen_temperature" {
  type    = number
  default = 0.2
}

variable "gen_max_tokens" {
  type    = number
  default = 512
}
