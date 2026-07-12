output "kb_role_arn" { value = aws_iam_role.kb.arn }
output "kb_role_policy_id" { value = aws_iam_role_policy.kb.id }
output "ack_role_arn" { value = aws_iam_role.ack.arn }
output "worker_role_arn" { value = aws_iam_role.worker.arn }
output "ack_role_name" { value = aws_iam_role.ack.name }
output "worker_role_name" { value = aws_iam_role.worker.name }

# expose policy JSON for the no-wildcard grep test
output "kb_policy_json" { value = data.aws_iam_policy_document.kb.json }
output "ack_policy_json" { value = data.aws_iam_policy_document.ack.json }
output "worker_policy_json" { value = data.aws_iam_policy_document.worker.json }
