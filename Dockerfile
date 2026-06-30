# 1. 경량화된 파이썬 공식 이미지 사용
FROM python:3.11-slim

# 2. 컨테이너 내부 작업 디렉토리 설정
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1

# 3. gcc 등 confluent-kafka 빌드에 필요한 리눅스 의존성 라이브러리 가볍게 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    && rm -rf /var/lib/apt/lists/*

# 4. 종속성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt