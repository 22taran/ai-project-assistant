output "function_url" {
  value       = module.slack_lambda.function_url
  description = "Register this as the Slack Events request URL."
}

output "knowledge_base_id" {
  value = module.bedrock_kb.knowledge_base_id
}
