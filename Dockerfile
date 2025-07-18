# syntax=docker/dockerfile:1
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 환경변수 파일 복사 (로컬 개발용, 실제 배포는 secrets로 주입)
# COPY .env .env

EXPOSE 5000

CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:app"] 