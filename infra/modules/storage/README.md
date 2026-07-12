# storage module

Creates the docs S3 bucket (versioned, private, SSE) and the S3 Vectors bucket +
index (dimension 1024, cosine) used by the Bedrock Knowledge Base.

## Inputs
| name | type | default | description |
|------|------|---------|-------------|
| name_prefix | string | — | prefix for names |
| tags | map(string) | — | tags for all resources |
| vector_dimension | number | 1024 | must match embedding model |

## Outputs
`docs_bucket_arn`, `docs_bucket_name`, `vector_bucket_arn`, `vector_index_arn`
