resource "random_password" "rds_password" {
  length  = 16
  special = true
}

resource "aws_security_group" "rds" {
  name        = "project-rds-sg"
  description = "Allow MySQL from EKS nodes"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    security_groups = [aws_security_group.eks_node.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "project-rds-sg" }
}

resource "aws_db_subnet_group" "rds" {
  name       = "project-rds-subnet-group"
  subnet_ids = [aws_subnet.private_rds_a.id, aws_subnet.private_rds_c.id]
  tags = { Name = "project-rds-subnet-group" }
}

resource "aws_db_instance" "mysql" {
  allocated_storage    = 20
  engine               = "mysql"
  engine_version       = "8.0"
  instance_class       = "db.t3.micro"
  name                 = "project"
  username             = "admin"
  password             = random_password.rds_password.result
  db_subnet_group_name = aws_db_subnet_group.rds.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  skip_final_snapshot  = true
  publicly_accessible  = false
  multi_az             = false
  deletion_protection  = false
  tags = { Name = "project-rds" }
} 