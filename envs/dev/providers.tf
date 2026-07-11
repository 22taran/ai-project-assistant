terraform {
  required_version = ">= 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.27"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
  # backend "s3" {}  # configure per-team; left local for first apply
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = local.common_tags
  }
}
