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