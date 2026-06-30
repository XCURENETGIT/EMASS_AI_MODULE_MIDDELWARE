# emass-ai-middleware 운영 가이드 (manage.sh)

`kafka_worker.py`(AI 분석 미들웨어)를 도커 컨테이너로 실행/관리하는 방법입니다.
모든 작업은 프로젝트 루트의 **`manage.sh`** 한 파일로 처리합니다.

## 구조

```
emass_ai_module/                ← 도커 바깥 (여기서 manage.sh 실행)
├── manage.sh                   ← 관리 스크립트
├── docker-compose.yaml
├── Dockerfile
├── requirements.txt
└── workspace/                  ← 컨테이너에 /app 으로 마운트
    ├── kafka_worker.py         ← 실제 실행되는 워커 (메인 프로세스)
    ├── logger_config.py        ← 로깅 설정 (날짜별 회전, 90일 보관)
    ├── .env                    ← 카프카/몽고/MinIO/모델 API 설정
    ├── module/                 ← 워커가 임포트하는 처리 모듈
    │   ├── get_data.py         ← 본문/첨부/이미지 데이터 조회
    │   ├── pii_detect.py       ← 개인정보 탐지 (gRPC)
    │   ├── code_text_detect.py ← 문서 분류
    │   ├── image_classify.py   ← 이미지 분류
    │   └── set_minio.py        ← MinIO 연동
    └── ai_process_log/         ← 날짜별 처리 로그 (90일 보관)
        └── emass_ai_process_YYYY-MM-DD.log
```

**동작 방식**: 컨테이너(서비스)가 올라가면 `kafka_worker.py` 가 **메인 프로세스로 바로
실행**됩니다. 즉 **컨테이너 = 워커**이고, 워커가 죽으면 `restart: always` 로 자동 재기동됩니다.
그래서 `start`/`stop`/`restart` 는 곧 컨테이너 기동/정지/재시작을 뜻합니다.

## 사전 준비

- Docker / Docker Compose 설치 (스크립트가 `docker compose`·`docker-compose` 자동 감지)
- 실행 위치: **프로젝트 루트** (`docker-compose.yaml` 이 있는 폴더)

```bash
cd /home/emass_ai_module
chmod +x manage.sh        # 최초 1회 실행 권한 부여
```

## 빠른 시작

```bash
./manage.sh run           # 이미지 빌드 + 컨테이너 기동 (워커 자동 실행)
./manage.sh status        # 잘 떴는지 확인
./manage.sh logs          # 워커 출력 실시간 확인
```

이미 빌드돼 있다면 `run` 대신 `up` 만으로 충분합니다:

```bash
./manage.sh up            # 컨테이너 기동 → 워커 자동 실행
```

종료할 때:

```bash
./manage.sh down          # 컨테이너 종료
```

## 명령어 전체

| 명령 | 설명 |
|------|------|
| `./manage.sh build` | 이미지 빌드 |
| `./manage.sh up` | 컨테이너 기동 → 워커(`kafka_worker.py`) 자동 실행 |
| `./manage.sh run` | `build` + `up` 을 한 번에 |
| `./manage.sh start` | 워커(컨테이너) 시작 — 정지된 컨테이너 다시 띄움 |
| `./manage.sh stop` | 워커(컨테이너) 중지 — 컨테이너는 유지 |
| `./manage.sh restart` | 워커(컨테이너) 재시작 |
| `./manage.sh status` | 워커(컨테이너) 상태 확인 |
| `./manage.sh set-kafka <h1> [h2] [h3] ...` | Kafka 브로커 호스트 설정 (`.env` 반영) |
| `./manage.sh set-mongo <h1> [h2] [h3] ...` | MongoDB replicaSet 멤버 호스트 설정 (`.env` 반영) |
| `./manage.sh hosts` | 현재 Kafka/Mongo 호스트 설정 확인 |
| `./manage.sh down` | 컨테이너 종료 (정지 + 제거) |
| `./manage.sh logs` | 워커 출력 실시간 보기 |
| `./manage.sh log ...` | 날짜별 처리 로그 파일 보기 (아래 참고) |
| `./manage.sh shell` | 컨테이너 안 셸 진입 |
| `./manage.sh help` | 도움말 |

## 로그 보기

실시간 출력과 날짜별 기록 파일은 명령이 다릅니다.

### 실시간 출력 — `logs`

워커가 컨테이너의 메인 프로세스라, 표준출력이 그대로 컨테이너 로그로 나옵니다.
(`PYTHONUNBUFFERED=1` 설정으로 버퍼링 없이 즉시 표시됩니다.)

```bash
./manage.sh logs          # 워커 실시간 출력 (docker compose logs)
```

### 날짜별 처리 로그 파일 — `log`

`workspace/ai_process_log/` 에 하루 단위로 쌓이는 기록(90일 보관)을 봅니다.
호스트에서 직접 읽으므로 **컨테이너가 꺼져 있어도 조회 가능**합니다.

```bash
./manage.sh log                # 오늘 로그
./manage.sh log 3              # 3일 전 로그
./manage.sh log 2026-06-17     # 특정 날짜 로그 (YYYY-MM-DD)
./manage.sh log list           # 보관 중인 로그 목록 (날짜/크기)
./manage.sh log 3 -f           # 실시간(follow) 보기
```

- **숫자** → N일 전, **`YYYY-MM-DD`** → 특정 날짜로 자동 구분
- 기본은 `less`(없으면 `cat`)로 열림, `-f` 를 주면 `tail -f` 로 실시간
- 해당 날짜 로그가 없으면 안내 후 `log list` 로 유도

## 자주 쓰는 흐름

**처음 배포**
```bash
./manage.sh run && ./manage.sh status
```

**코드만 고쳤을 때** (워커 재시작 — `workspace/` 는 마운트라 빌드 불필요)
```bash
./manage.sh restart
```

**의존성(`requirements.txt`)을 바꿨을 때** (이미지 재빌드 필요)
```bash
./manage.sh down && ./manage.sh run
```

**문제 확인**
```bash
./manage.sh status            # 워커(컨테이너) 상태
./manage.sh logs              # 실시간 출력
./manage.sh log               # 오늘 처리 로그
./manage.sh shell             # 컨테이너 들어가서 직접 확인
```

## 설정 변경

카프카·몽고DB·MinIO 주소, 분석 모델 API 주소 등은 **`workspace/.env`** 에 있습니다.
`.env` 는 마운트된 폴더에 있으므로 수정 후 **워커만 재시작**하면 반영됩니다.

```bash
# workspace/.env 수정 후
./manage.sh restart
```

### Kafka·MongoDB 호스트 설정 (다중 호스트 지원)

Kafka 브로커와 MongoDB replicaSet 멤버는 **여러 개를 콤마로 나열**할 수 있습니다.
`.env` 를 직접 고쳐도 되지만, 전용 명령으로 설정하는 편이 안전합니다.
(공백으로 호스트를 나열하면 내부에서 콤마로 묶어 `.env` 에 기록합니다.)

```bash
# Kafka 브로커 3개 (한 클러스터의 멤버)
./manage.sh set-kafka 10.200.10.64 10.200.10.65 10.200.10.66

# MongoDB replicaSet 멤버 3개
./manage.sh set-mongo 10.200.10.65 10.200.10.66 10.200.10.67

./manage.sh hosts          # 현재 설정 확인
./manage.sh restart        # 변경 적용 (워커 재시작)
```

동작 규칙:

- `.env` 에는 `KAFKA_SERVER_URL= "h1,h2,h3"` 형태(콤마 구분)로 저장됩니다.
- 포트는 `KAFKA_PORT`·`MONGO_PORT` 가 모든 호스트에 공통 적용됩니다.
  호스트마다 포트가 다르면 `host:port` 형태로 직접 지정할 수 있습니다.
  예: `./manage.sh set-kafka 10.200.10.64:9092 10.200.10.65:9093`
- 호스트를 **1개만** 적으면 기존처럼 단일 노드로 동작합니다.
  MongoDB는 멤버가 1개일 때만 `directConnection=true` 가 자동으로 붙고,
  2개 이상이면 replicaSet 페일오버를 위해 빠집니다(직결 옵션은 단일 노드 전용).
- 워커 기동 시 실제 사용된 `bootstrap.servers`·Mongo 호스트가 로그에 찍히므로
  `./manage.sh logs` 로 적용 여부를 확인할 수 있습니다.

## 참고

- `manage.sh` 는 반드시 **프로젝트 루트(도커 바깥)** 에서 실행합니다.
  `workspace/` 는 컨테이너 내부(`/app`)로 마운트되는 폴더라 관리 스크립트를 두지 않습니다.
- compose `command` 가 `python3 /app/kafka_worker.py` 라, 컨테이너가 올라가면 워커가
  바로 실행됩니다. 워커가 죽으면 `restart: always` 로 자동 재기동됩니다.
- `Dockerfile` 은 **의존성(`requirements.txt`)만 설치**하고 코드는 굽지 않습니다.
  실제 코드(`kafka_worker.py`·`module/` 등)는 `workspace/` 마운트로 들어오므로, 이 이미지는
  **반드시 `workspace/` 가 마운트된 상태로만 동작**합니다(`manage.sh`/compose 사용 시 자동).
