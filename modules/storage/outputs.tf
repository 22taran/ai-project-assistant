output "docs_bucket_arn" {
  value = aws_s3_bucket.docs.arn
}

output "docs_bucket_name" {
  value = aws_s3_bucket.docs.bucket
}

output "vector_bucket_arn" {
  value = aws_s3vectors_vector_bucket.vectors.vector_bucket_arn
}

output "vector_index_arn" {
  value = aws_s3vectors_index.index.index_arn
}
