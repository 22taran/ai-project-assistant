# ---- Docs bucket ----
resource "aws_s3_bucket" "docs" {
  bucket = "${var.name_prefix}-docs"
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "docs" {
  bucket = aws_s3_bucket.docs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "docs" {
  bucket                  = aws_s3_bucket.docs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "docs" {
  bucket = aws_s3_bucket.docs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ---- S3 Vectors bucket + index ----
resource "aws_s3vectors_vector_bucket" "vectors" {
  vector_bucket_name = "${var.name_prefix}-vectors"
  tags               = var.tags
}

resource "aws_s3vectors_index" "index" {
  vector_bucket_name = aws_s3vectors_vector_bucket.vectors.vector_bucket_name
  index_name         = "${var.name_prefix}-index"
  data_type          = "float32"
  dimension          = var.vector_dimension
  distance_metric    = "cosine"
  tags               = var.tags
}
