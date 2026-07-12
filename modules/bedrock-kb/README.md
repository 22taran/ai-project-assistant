# bedrock-kb module

VECTOR knowledge base (Titan Embeddings V2, dim 1024) with S3_VECTORS storage and
an S3 data source (FIXED_SIZE chunking, 500 tokens / 20% overlap). depends_on the
KB role policy so the role is propagated before the KB is created.
