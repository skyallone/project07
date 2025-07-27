resource "aws_dynamodb_table" "project" {
  name           = "project-chat"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "user_id"
  range_key      = "timestamp"

  attribute {
    name = "user_id"
    type = "S"
  }
  attribute {
      name = "timestamp"
      type = "N"
  }

  tags = {
    Environment = "production"
    Project     = "flask-app"
  }
} 