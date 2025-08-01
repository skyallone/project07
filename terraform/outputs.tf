output "eks_cluster_name" {
  value = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  value = aws_eks_cluster.main.endpoint
}

output "eks_node_group_name" {
  value = aws_eks_node_group.main.node_group_name
}

output "s3_bucket_name" {
  value = aws_s3_bucket.project07.bucket
}

output "ecr_repository_url" {
  value = aws_ecr_repository.project07.repository_url
}

output "ecr_registry" {
  description = "ECR registry URL (host part only)"
  value       = regex("^(.*)/.*$", aws_ecr_repository.project07.repository_url)[0]
}

output "ecr_repository" {
  description = "ECR repository name"
  value       = aws_ecr_repository.project07.name
}

output "eks_role_arn" {
  description = "EKS cluster IAM role ARN"
  value       = aws_iam_role.eks_cluster.arn
}

output "s3_bucket" {
  description = "S3 bucket name"
  value       = aws_s3_bucket.project07.bucket
}

output "public_subnet_ids" {
  value = [aws_subnet.public_a.id, aws_subnet.public_c.id]
}

output "private_eks_subnet_ids" {
  value = [aws_subnet.private_eks_a.id, aws_subnet.private_eks_c.id]
}

output "private_rds_subnet_ids" {
  value = [aws_subnet.private_rds_a.id, aws_subnet.private_rds_c.id]
}

output "nat_gateway_ids" {
  value = [aws_nat_gateway.a.id, aws_nat_gateway.c.id]
}

output "dynamodb_table" {
  description = "DynamoDB table name"
  value       = aws_dynamodb_table.project.name
}

output "rds_endpoint" {
  value = aws_db_instance.mysql.endpoint
}

output "rds_username" {
  value = aws_db_instance.mysql.username
}

output "rds_password" {
  value     = aws_db_instance.mysql.password
  sensitive = true
}

output "rds_db_name" {
  value = "project"
} 