variable "region" {
  description = "AWS region"
  type        = string
  default     = "ap-northeast-2"
}

variable "project_name" {
  description = "Project name prefix"
  type        = string
  default     = "project07"
}

variable "environment" {
  description = "Environment (dev, prod, etc)"
  type        = string
  default     = "dev"
}

variable "cluster_name" {
  description = "EKS Cluster name"
  type        = string
  default     = "projectflask"
}

variable "node_group_name" {
  description = "EKS Node Group name"
  type        = string
  default     = "project-node-group"
}

variable "node_instance_type" {
  description = "EC2 instance type for EKS nodes"
  type        = string
  default     = "t3.medium"
}

variable "desired_capacity" {
  description = "Desired number of EKS nodes"
  type        = number
  default     = 2
}

variable "max_capacity" {
  description = "Max number of EKS nodes"
  type        = number
  default     = 3
}

variable "min_capacity" {
  description = "Min number of EKS nodes"
  type        = number
  default     = 1
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "172.16.0.0/16"
}

variable "s3_bucket_name" {
  description = "S3 bucket name for state or app"
  type        = string
  default     = "project-terraform25"
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name for state lock"
  type        = string
  default     = "terraform"
} 