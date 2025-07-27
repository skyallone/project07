resource "aws_s3_bucket" "project07" {
  bucket = "project07-bucket-${random_id.s3_id.hex}"
  force_destroy = true
}

resource "aws_s3_bucket_ownership_controls" "project07" {
  bucket = aws_s3_bucket.project07.id

  rule {
    object_ownership = "ObjectWriter"
  }
}

resource "aws_s3_bucket_acl" "project07" {
  depends_on = [aws_s3_bucket_ownership_controls.project07]
  bucket = aws_s3_bucket.project07.id
  acl    = "public-read"
}

resource "aws_s3_bucket_public_access_block" "project07" {
  bucket = aws_s3_bucket.project07.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "project07" {
  bucket = aws_s3_bucket.project07.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowPublicRead"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.project07.arn}/*"
      }
    ]
  })
}

resource "random_id" "s3_id" {
  byte_length = 4
}

resource "aws_ecr_repository" "project07" {
  name = "project07-ecr"
  image_tag_mutability = "MUTABLE"
  force_delete = true
  image_scanning_configuration {
    scan_on_push = true
  }
}

 