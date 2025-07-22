terraform {
  backend "s3" {
    bucket         = "project-terraform25"
    key            = "state/terraform.tfstate"
    region         = "ap-northeast-2"
    dynamodb_table = "terraform"
    encrypt        = true
  }
}

provider "aws" {
  region = "ap-northeast-2"
} 