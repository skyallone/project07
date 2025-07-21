# Terraform Infrastructure for project07

## 필수 입력 변수 및 값
- AWS 자격증명(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY): GitHub Secrets에 등록 필요
- (선택) EKS 클러스터/노드그룹 이름, 인스턴스 타입 등은 variables.tf에서 수정 가능

## 주요 Output
- EKS 클러스터 이름: eks_cluster_name
- EKS 엔드포인트: eks_cluster_endpoint
- 노드그룹 이름: eks_node_group_name
- ALB DNS: alb_dns_name
- S3 버킷 이름: s3_bucket_name
- ECR URL: ecr_repository_url
- Karpenter 인스턴스 프로파일 ARN: karpenter_instance_profile_arn

## GitHub Actions CI/CD
- .github/workflows/terraform.yml 파일을 생성하여 CI/CD 자동화
- 필요한 GitHub Secrets:
  - AWS_ACCESS_KEY_ID
  - AWS_SECRET_ACCESS_KEY
  - (필요시) AWS_REGION

## 적용 방법
1. terraform init
2. terraform plan
3. terraform apply

## 참고
- 리소스 이름, 인스턴스 타입 등은 terraform/variables.tf에서 변경 가능
- 직접 입력해야 하는 값은 위의 내용을 참고하여 GitHub Secrets 또는 변수로 지정 