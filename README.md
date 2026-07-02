# emass-ai-middleware

이메일/메시지 데이터를 대상으로 **AI 분석(개인정보 탐지·문서 분류·이미지 분류)** 을 수행하는
Kafka 기반 미들웨어입니다. Kafka 로 들어온 분석 요청을 받아 MongoDB·MinIO 에서 원문/첨부/이미지를
가져와 분석하고, 결과를 다시 Kafka 로 내보냅니다.

```
        ┌──────────┐   analysis    ┌──────────────────────┐   analysis_result   ┌──────────┐
        │  Kafka   │ ────────────▶ │  emass-ai-middleware │ ─────────────────▶  │  Kafka   │
        │ (source) │               │      (kafka_worker)  │                     │ (target) │
        └──────────┘               └───────────┬──────────┘                     └──────────┘
                                                │ 조회
                                   ┌────────────┼─────────────┐
                                   ▼            ▼             ▼
                              ┌─────────┐  ┌─────────┐  ┌──────────────┐
                              │ MongoDB │  │  MinIO  │  │ AI 모델 API   │
                              │ (본문/  │  │ (첨부   │  │ (PII/분류/    │
                              │  메타)  │  │  텍스트)│  │  이미지)      │
                              └─────────┘  └─────────┘  └──────────────┘
```

## 처리 흐름

1. Kafka `analysis` 토픽에서 메시지(키=문서 ID)를 컨슘
2. 무시 대상 서비스타입(`IGNORE_SVC_PREFIXES`)이면 스킵
3. MongoDB/MinIO 에서 본문·첨부 텍스트·이미지 경로를 조회
4. 3종 분석을 **병렬** 실행 — 개인정보 탐지(gRPC), 문서 분류, 이미지 분류
5. 결과를 합쳐 Kafka `analysis_result` 토픽으로 전송 (at-least-once, 수동 커밋)

## 폴더 구성

이 저장소는 **개발/빌드용(`dev/`)** 과 **현장 배포용(`deploy/`)** 으로 나뉩니다.

```
emass_ai_module/
├── README.md                   ← 이 문서 (프로젝트 전체 설명)
├── dev/                        ← 개발 + 사내 이미지 빌드 (소스 있음)
│   ├── manage.sh               ← 개발 실행 + 프로덕션 이미지 빌드/반출
│   ├── manage-guide.md         ← 개발/빌드 상세 가이드
│   ├── docker-compose.yaml     ← 개발용 (소스 마운트)
│   ├── Dockerfile              ← 개발 이미지 (의존성만)
│   ├── Dockerfile.prod         ← 프로덕션 이미지 빌드 레시피 (.so 컴파일, 멀티스테이지)
│   ├── requirements.txt
│   └── workspace/              ← 실제 소스 (컨테이너에 /app 으로 마운트)
│       ├── kafka_worker.py     ← 메인 워커 (컨슈머/프로듀서 루프)
│       ├── run.py              ← 프로덕션 런처 (.so 의 main() 호출)
│       ├── logger_config.py    ← 로깅 설정 (날짜별 회전, 90일 보관)
│       ├── .env                ← 접속/설정값 (Kafka/Mongo/MinIO/모델 API)
│       └── module/             ← 처리 모듈
│           ├── get_data.py         ← 본문/첨부/이미지 조회 (MongoDB)
│           ├── set_minio.py        ← 첨부 텍스트 조회 (MinIO)
│           ├── pii_detect.py       ← 개인정보 탐지 (gRPC)
│           ├── code_text_detect.py ← 문서 분류
│           └── image_classify.py   ← 이미지 분류
└── deploy/                     ← 현장 배포 (소스 없음, .so 이미지만 실행)
    ├── prod-manage.sh          ← 현장 운영 스크립트 (load/up/운영)
    ├── prod-manage.md          ← 현장 운영 상세 가이드
    ├── docker-compose.prod.yaml← 런타임 전용 (build 섹션 없음)
    ├── (반입) *.tar.gz          ← 사내에서 반출한 .so 이미지
    └── workspace/
        ├── .env                ← 접속/설정값
        └── ai_process_log/     ← 날짜별 처리 로그 (90일 보관)
```

### 왜 두 폴더로 나눴나

- **dev/** 에는 소스가 있고, 개발 실행과 **프로덕션 이미지 빌드**를 담당합니다.
- **deploy/** 에는 소스가 없습니다. 사내에서 빌드한 **`.so` 이미지만** 받아 실행합니다.
  → 현장에 소스(`.py`)가 남지 않아 유출·열람 난이도를 크게 높입니다.

## 전체 워크플로

### 1) 사내(빌드 서버) — `dev/` 에서 빌드·반출

```bash
cd dev
./manage.sh prod build      # 핵심 소스를 Cython 으로 .so 컴파일한 이미지 빌드
./manage.sh prod save       # 이미지를 파일로 반출 → emass-ai-middelware-prod.tar.gz
mv emass-ai-middelware-prod.tar.gz ../deploy/   # 배포용 폴더로 이동
```

개발 중 로컬 실행(소스 마운트)은 prod 접두 없이:

```bash
cd dev
./manage.sh run             # 개발 이미지 빌드 + 기동
./manage.sh logs            # 실시간 로그
```

### 2) 현장(배포지) — `deploy/` 폴더만 들고 가서 실행

`deploy/` 폴더(이미지 tar 포함)만 현장으로 옮긴 뒤:

```bash
cd deploy
./prod-manage.sh load emass-ai-middelware-prod.tar.gz     # 이미지 반입
./prod-manage.sh set-kafka 10.200.10.64 10.200.10.65 10.200.10.66   # 접속 호스트 설정
./prod-manage.sh set-mongo 10.200.10.65 10.200.10.66 10.200.10.67
./prod-manage.sh up                                       # 빌드 없이 기동
./prod-manage.sh logs                                     # 실시간 로그
```

> 현장에서는 빌드하지 않습니다. **`load` → `up`** 만 사용합니다.

## 주요 개념

### 다중 호스트 (Kafka 클러스터 / MongoDB replicaSet)

Kafka 브로커와 MongoDB replicaSet 멤버를 **여러 개(예: 3개)** 지정할 수 있습니다.
`.env` 에 콤마로 나열하거나, 스크립트 명령으로 설정합니다.

```bash
# dev 에서
./manage.sh set-kafka 10.200.10.64 10.200.10.65 10.200.10.66
# 현장에서
./prod-manage.sh set-mongo 10.200.10.65 10.200.10.66 10.200.10.67
```

- 포트는 `.env` 의 `KAFKA_PORT`·`MONGO_PORT` 가 공통 적용됩니다. 호스트별로 다르면
  `host:port` 형태로 지정할 수 있습니다.
- 호스트가 1개면 단일 노드로 동작합니다. (MongoDB 는 이때만 `directConnection=true`)

### 프로덕션 소스 보호 (.so 컴파일)

`Dockerfile.prod` 는 멀티스테이지 빌드로 핵심 소스를 **Cython `.so`** 로 컴파일해 이미지에
구워 넣고, 원본 `.py` 는 제거합니다. 런처 `run.py` 가 컴파일된 워커의 `main()` 을 실행합니다.

- **컴파일 대상**: `kafka_worker.py`, `module/get_data.py`·`pii_detect.py`·
  `code_text_detect.py`·`image_classify.py`·`set_minio.py`
- **평문 유지**: `run.py`, `logger_config.py`, `pii_pb2*.py`(proto 자동생성), `.env`
- `.so` 는 **CPython 3.11 + x86_64 리눅스** 종속입니다. 다른 아키텍처면 그 환경에서 다시 빌드해야 합니다.

## 설정 (.env)

접속/동작 값은 `workspace/.env` 에 있습니다 (dev·deploy 각각 보유). 주요 항목:

| 키 | 설명 |
|----|------|
| `KAFKA_SERVER_URL` | Kafka 브로커 호스트 (콤마로 여러 개 가능) |
| `KAFKA_PORT` / `KAFKA_GROUP` | 포트 / 컨슈머 그룹 |
| `KAFKA_SOURCE_TOPIC` / `KAFKA_TARGET_TOPIC` | 입력 / 출력 토픽 |
| `MONGODB_SERVER_URL` | MongoDB replicaSet 멤버 호스트 (콤마로 여러 개 가능) |
| `MONGO_PORT` / `DATABASE_NAME` | 포트 / DB 이름 |
| `MINIO_SERVER_URL`(선택) / `MINIO_PORT` | MinIO 엔드포인트 (미지정 시 Kafka 첫 호스트 사용) |
| `MINIO_BUCKET` / `ACCESS_KEY` / `SECRET_KEY` / `SECURE` / `REGION` | MinIO 접속 |
| `IGNORE_SVC_PREFIXES` | 분석 제외할 서비스타입 앞자리 (콤마 구분) |
| `PII` / `CLASSIFY` / `IMAGE` | 개인정보·문서분류·이미지 AI 모델 API 주소 |
| `LOG_DIR_PATH` | 처리 로그 폴더 경로 |

## 자세한 문서

- 개발 / 이미지 빌드·반출: [dev/manage-guide.md](dev/manage-guide.md)
- 현장 배포 / 운영: [deploy/prod-manage.md](deploy/prod-manage.md)
