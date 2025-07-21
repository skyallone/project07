resource "aws_dynamodb_table" "project" {
  name           = "project-chat"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "user_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  tags = {
    Environment = "production"
    Project     = "flask-app"
  }
} 