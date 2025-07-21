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

resource "aws_eks_cluster" "main" {
  name     = var.cluster_name
  role_arn = aws_iam_role.eks_cluster.arn

  vpc_config {
    subnet_ids = [aws_subnet.private_eks_a.id, aws_subnet.private_eks_c.id]
  }
}

resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = var.node_group_name
  node_role_arn   = aws_iam_role.eks_node.arn
  subnet_ids      = [aws_subnet.private_eks_a.id, aws_subnet.private_eks_c.id]
  instance_types  = [var.node_instance_type]
  scaling_config {
    desired_size = 2
    max_size     = 3
    min_size     = 1
  }
} 