resource "aws_vpc" "main" {
  cidr_block           = "172.16.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = {
    Name = "project-vpc"
  }
}

# Public Subnets
resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "172.16.1.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "ap-northeast-2a"
  tags = { Name = "project-public-a" }
}
resource "aws_subnet" "public_c" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "172.16.2.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "ap-northeast-2c"
  tags = { Name = "project-public-c" }
}

# Private Subnets for EKS
resource "aws_subnet" "private_eks_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "172.16.11.0/24"
  availability_zone = "ap-northeast-2a"
  tags = { Name = "project-private-eks-a" }
}
resource "aws_subnet" "private_eks_c" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "172.16.12.0/24"
  availability_zone = "ap-northeast-2c"
  tags = { Name = "project-private-eks-c" }
}
# Private Subnets for RDS
resource "aws_subnet" "private_rds_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "172.16.21.0/24"
  availability_zone = "ap-northeast-2a"
  tags = { Name = "project-private-rds-a" }
}
resource "aws_subnet" "private_rds_c" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "172.16.22.0/24"
  availability_zone = "ap-northeast-2c"
  tags = { Name = "project-private-rds-c" }
}

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id
  tags = { Name = "project-igw" }
}

# NAT Gateways (one per AZ)
resource "aws_eip" "nat_a" {}
resource "aws_eip" "nat_c" {}
resource "aws_nat_gateway" "a" {
  allocation_id = aws_eip.nat_a.id
  subnet_id     = aws_subnet.public_a.id
  tags = { Name = "project-nat-a" }
}
resource "aws_nat_gateway" "c" {
  allocation_id = aws_eip.nat_c.id
  subnet_id     = aws_subnet.public_c.id
  tags = { Name = "project-nat-c" }
}

# Route Tables
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }
  tags = { Name = "project-public-rt" }
}
resource "aws_route_table" "private_a" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.a.id
  }
  tags = { Name = "project-private-rt-a" }
}
resource "aws_route_table" "private_c" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.c.id
  }
  tags = { Name = "project-private-rt-c" }
}

# Route Table Associations
resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}
resource "aws_route_table_association" "public_c" {
  subnet_id      = aws_subnet.public_c.id
  route_table_id = aws_route_table.public.id
}
resource "aws_route_table_association" "private_eks_a" {
  subnet_id      = aws_subnet.private_eks_a.id
  route_table_id = aws_route_table.private_a.id
}
resource "aws_route_table_association" "private_eks_c" {
  subnet_id      = aws_subnet.private_eks_c.id
  route_table_id = aws_route_table.private_c.id
}
resource "aws_route_table_association" "private_rds_a" {
  subnet_id      = aws_subnet.private_rds_a.id
  route_table_id = aws_route_table.private_a.id
}
resource "aws_route_table_association" "private_rds_c" {
  subnet_id      = aws_subnet.private_rds_c.id
  route_table_id = aws_route_table.private_c.id
} 