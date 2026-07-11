variable "name_prefix"          { type = string }
variable "tags"                 { type = map(string) }
variable "docs_bucket_arn"      { type = string }
variable "vector_index_arn"     { type = string }
variable "embedding_model_arn"  { type = string }
variable "generation_model_arn" { type = string }
variable "signing_secret_arn"   { type = string }
variable "bot_token_arn"        { type = string }
# NOTE: no kb_arn / worker_function_arn here — those two grants are attached in
# the root env (Task 9 Step 3) to avoid a module dependency cycle.
