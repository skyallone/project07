# Flask EKS 배포 및 GitHub Actions CI/CD 안내

## 1. Docker 이미지 빌드 및 ECR 푸시
- Dockerfile이 이미 포함되어 있습니다.
- AWS ECR(Elastic Container Registry)에 이미지를 푸시해야 합니다.

## 2. Kubernetes 배포
- `deployment.yaml`, `service.yaml`을 사용해 EKS에 배포합니다.
- 환경변수(Secrets)는 Kubernetes Secret으로 관리합니다.

## 3. GitHub Actions (CI/CD)
- `.github/workflows/deploy.yml`에서 빌드, ECR 푸시, EKS 배포를 자동화합니다.
- 필요한 GitHub Secrets:
  - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`
  - `ECR_REGISTRY`, `ECR_REPOSITORY`, `EKS_CLUSTER_NAME`, `EKS_ROLE_ARN`
  - (앱 환경변수) `GEMINI_API_KEY`, `TAGO_API_KEY`, `API_KEY`, `FLASK_SECRET_KEY`, ...

## 4. 예시 명령어
```bash
# ECR 로그인
aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin <ECR_REGISTRY>
# 빌드 및 푸시
TAG=latest
docker build -t $ECR_REPOSITORY:$TAG .
docker tag $ECR_REPOSITORY:$TAG $ECR_REGISTRY/$ECR_REPOSITORY:$TAG
docker push $ECR_REGISTRY/$ECR_REPOSITORY:$TAG
# EKS 배포
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
```

## 5. 참고
- `.env.example` 참고하여 환경변수 준비
- secrets는 깃허브/쿠버네티스에 안전하게 저장 

## 6. 전체 인프라 및 앱 배포 순서 (Terraform + K8s)

### 1) Terraform으로 인프라 생성
```bash
cd ../terraform
terraform init
terraform apply
```
- VPC, EKS, ALB, Karpenter, ECR, S3 등 인프라가 자동 생성됩니다.
- terraform apply 후, 출력되는 EKS 정보/ALB 주소/ECR URI 등을 확인하세요.

### 2) (수동) Karpenter Helm 설치
Terraform은 Karpenter용 IAM, SQS 등 리소스만 생성합니다. 실제 Karpenter 컨트롤러는 Helm으로 직접 설치해야 합니다.
```bash
# kubeconfig 세팅 (terraform output 참고)
aws eks update-kubeconfig --region <REGION> --name <CLUSTER_NAME>

# Karpenter Helm 설치
helm repo add karpenter https://charts.karpenter.sh
helm repo update
helm install karpenter karpenter/karpenter \
  --namespace karpenter --create-namespace \
  --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"=<KARPENTER_IAM_ROLE_ARN> \
  --set clusterName=<CLUSTER_NAME> \
  --set clusterEndpoint=<EKS_ENDPOINT> \
  --set aws.defaultInstanceProfile=<INSTANCE_PROFILE_NAME>
```
- 위 값들은 terraform output 또는 AWS 콘솔에서 확인

### 3) (수동) ECR에 Docker 이미지 빌드/푸시
```bash
cd ../project07
chmod +x push_ecr.sh
export AWS_REGION=<리전>
export ECR_REPO=<ECR_URI>
export IMAGE_TAG=latest
./push_ecr.sh
```
- ECR_REPO는 terraform output의 ECR URI 사용

### 4) (수동) Kubernetes 리소스 배포
```bash
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f karpenter-nodepool.yaml # Karpenter 노드풀 생성
kubectl apply -f ingress.yaml            # ALB Ingress 생성
```
- ingress.yaml을 통해 ALB가 외부 트래픽을 서비스로 연결
- ALB 주소는 kubectl get ingress로 확인

### 5) (선택) GitHub Actions로 CI/CD 자동화
- `.github/workflows/deploy.yml` 참고 (Secrets 필요)

---

## 7. 직접 해야 하는 주요 작업
- Karpenter Helm 설치 (수동)
- ECR 빌드/푸시 (push_ecr.sh 사용)
- Ingress 리소스 배포 (ingress.yaml)
- 환경변수/시크릿 관리 (ConfigMap/Secret)
- (옵션) CI/CD 연동 및 GitHub Secrets 세팅

---

## 8. 참고
- ALB Ingress Controller가 설치되어 있어야 ingress.yaml이 정상 동작합니다.
- Karpenter, ALB, ECR 등은 terraform output 또는 AWS 콘솔에서 정보 확인
- 문제 발생 시 terraform output, kubectl logs, AWS 콘솔 참고 