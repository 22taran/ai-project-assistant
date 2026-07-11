variable "name_prefix" {
  type = string
}

variable "tags" {
  type = map(string)
}

variable "kb_role_arn" {
  type = string
}

variable "embedding_model_arn" {
  type = string
}

variable "vector_bucket_arn" {
  type = string
}

variable "vector_index_arn" {
  type = string
}

variable "docs_bucket_arn" {
  type = string
}

variable "vector_dimension" {
  type    = number
  default = 1024
}

variable "kb_role_policy_dep" {
  type        = any
  default     = null
  description = "Pass the KB role policy resource to force creation ordering."
}
