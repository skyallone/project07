resource "aws_s3_bucket" "project07" {
  bucket = "project07-bucket-${random_id.s3_id.hex}"
  force_destroy = true
}

resource "random_id" "s3_id" {
  byte_length = 4
}

resource "aws_ecr_repository" "project07" {
  name = "project07-ecr"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
} 