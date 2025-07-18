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