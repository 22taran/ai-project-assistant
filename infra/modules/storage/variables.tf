variable "name_prefix" {
  type        = string
  description = "Prefix for bucket/index names."
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to all resources."
}

variable "vector_dimension" {
  type        = number
  default     = 1024
  description = "Embedding dimension; must match the embedding model."
}
