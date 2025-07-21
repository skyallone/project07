#!/bin/bash
# ECR 리포지토리, 리전, 태그를 환경변수로 지정하세요.
# 예시:
# export AWS_REGION=ap-northeast-2
# export ECR_REPO=123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/project07
# export IMAGE_TAG=latest

if [ -z "$AWS_REGION" ] || [ -z "$ECR_REPO" ] || [ -z "$IMAGE_TAG" ]; then
  echo "환경변수(AWS_REGION, ECR_REPO, IMAGE_TAG)를 먼저 설정하세요."
  exit 1
fi

aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REPO
docker build -t $ECR_REPO:$IMAGE_TAG .
docker push $ECR_REPO:$IMAGE_TAG 