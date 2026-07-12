resource "aws_bedrockagent_knowledge_base" "this" {
  name     = "${var.name_prefix}-kb"
  role_arn = var.kb_role_arn
  tags     = var.tags

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = var.embedding_model_arn
      embedding_model_configuration {
        bedrock_embedding_model_configuration {
          dimensions          = var.vector_dimension
          embedding_data_type = "FLOAT32"
        }
      }
    }
  }

  storage_configuration {
    type = "S3_VECTORS"
    s3_vectors_configuration {
      index_arn = var.vector_index_arn

    }
  }

  depends_on = [var.kb_role_policy_dep]
}

resource "aws_bedrockagent_data_source" "s3" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.this.id
  name              = "${var.name_prefix}-s3-docs"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = var.docs_bucket_arn
    }
  }
  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration {
        max_tokens         = 512
        overlap_percentage = 20
      }
    }
  }
}
