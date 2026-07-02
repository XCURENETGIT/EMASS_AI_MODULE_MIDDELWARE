# emass-ai-middleware 현장(배포지) 운영 가이드

**소스 코드 없이 `.so` 로 컴파일된 이미지만으로** AI 분석 미들웨어를 올리고 운영하는
방법입니다. 빌드는 사내에서 끝났고, 현장에는 **이미지 파일만** 들고 온다는 전제입니다.
모든 작업은 **`prod-manage.sh`** 한 파일로 처리합니다.

> 사내(빌드 서버)에서의 빌드·반출은 개발용 `manage.sh` / `manage-guide.md` 를 보세요.
> (`./manage.sh prod build` → `./manage.sh prod save`)

## 현장에 필요한 파일

이미지 안에 실행 코드(`.so`)가 다 들어있으므로 **소스(`.py`)는 필요 없습니다.**
현장에는 이 **`deploy/` 폴더만** 들고 나가면 됩니다.

```
deploy/
├── prod-manage.sh                    ← 현장 운영 스크립트
├── prod-manage.md                    ← 이 문서
├── docker-compose.prod.yaml          ← 런타임 전용 compose (build 섹션 없음)
├── emass-ai-middelware-prod.tar.gz   ← 사내에서 반출한 .so 이미지 (여기에 넣는다)
└── workspace/
    ├── .env                          ← 접속 설정 (호스트/포트/키)
    └── ai_process_log/               ← 로그 폴더 (없으면 자동 생성)
```

## 사전 준비

- Docker / Docker Compose 설치 (스크립트가 `docker compose`·`docker-compose` 자동 감지)
- 실행 위치: **위 파일들이 있는 폴더**

```bash
chmod +x prod-manage.sh        # 최초 1회 실행 권한 부여
```

## 빠른 시작 (현장 최초 배포)

```bash
# 1) 이미지 반입 (.so 가 든 이미지를 도커에 로드)
./prod-manage.sh load emass-ai-middelware-prod.tar.gz

# 2) 접속 호스트 설정 (클러스터/replicaSet 멤버는 공백으로 여러 개)
./prod-manage.sh set-kafka 10.200.10.64 10.200.10.65 10.200.10.66
./prod-manage.sh set-mongo 10.200.10.65 10.200.10.66 10.200.10.67
./prod-manage.sh hosts        # 설정 확인

# 3) 서비스 기동 (빌드 없이 반입된 이미지로 실행)
./prod-manage.sh up
./prod-manage.sh status       # 잘 떴는지 확인
./prod-manage.sh logs         # 실시간 로그 (기동 시 bootstrap.servers / Mongo 호스트 출력)
```

종료할 때:

```bash
./prod-manage.sh down
```

## 명령어 전체

| 명령 | 설명 |
|------|------|
| `./prod-manage.sh load <파일>` | 반출한 `.so` 이미지(tar.gz)를 도커에 반입 |
| `./prod-manage.sh up` | 서비스 기동 (반입된 이미지만 사용, **빌드 안 함**) |
| `./prod-manage.sh down` | 서비스 종료 (정지 + 제거) |
| `./prod-manage.sh start` | 워커(컨테이너) 시작 — 정지된 컨테이너 다시 띄움 |
| `./prod-manage.sh stop` | 워커(컨테이너) 중지 — 컨테이너는 유지 |
| `./prod-manage.sh restart` | 워커(컨테이너) 재시작 |
| `./prod-manage.sh status` | 상태 확인 (이미지 반입 여부 + 실행 여부) |
| `./prod-manage.sh set-kafka <h1> [h2]...` | Kafka 브로커 호스트 설정 (`.env`) |
| `./prod-manage.sh set-mongo <h1> [h2]...` | MongoDB replicaSet 멤버 호스트 설정 (`.env`) |
| `./prod-manage.sh hosts` | 현재 Kafka/Mongo/MinIO 호스트 설정 확인 |
| `./prod-manage.sh logs` | 워커 출력 실시간 보기 |
| `./prod-manage.sh log ...` | 날짜별 처리 로그 파일 보기 (아래 참고) |
| `./prod-manage.sh shell` | 컨테이너 안 셸 진입 |
| `./prod-manage.sh help` | 도움말 |

> `build`·`run`·`save` 는 소스가 필요해 현장에서는 막혀 있습니다. 실행하면 안내가 나옵니다.

## 접속 설정 (Kafka·MongoDB 호스트)

Kafka 브로커와 MongoDB replicaSet 멤버는 **여러 개를 공백으로 나열**하면 됩니다.
(내부적으로 `.env` 에 콤마로 묶여 저장됩니다.)

```bash
# 브로커 3개 (한 클러스터)
./prod-manage.sh set-kafka 10.200.10.64 10.200.10.65 10.200.10.66

# replicaSet 멤버 3개
./prod-manage.sh set-mongo 10.200.10.65 10.200.10.66 10.200.10.67

./prod-manage.sh hosts        # 현재 설정 확인
./prod-manage.sh restart      # 변경 적용 (워커 재시작)
```

- 포트는 `.env` 의 `KAFKA_PORT`·`MONGO_PORT` 가 모든 호스트에 공통 적용됩니다.
  호스트마다 포트가 다르면 `host:port` 형태로 직접 지정할 수 있습니다.
  예: `./prod-manage.sh set-kafka 10.200.10.64:9092 10.200.10.65:9093`
- 호스트를 1개만 적으면 단일 노드로 동작합니다. (MongoDB는 이때만 `directConnection=true`)
- **MinIO**·모델 API 주소, 접속 키 등 그 외 설정은 `workspace/.env` 를 직접 편집한 뒤
  `./prod-manage.sh restart` 하면 반영됩니다. (`.env` 는 컨테이너에 마운트됩니다)

## 로그 보기

### 실시간 출력 — `logs`

```bash
./prod-manage.sh logs         # 워커 실시간 출력 (docker compose logs)
```

### 날짜별 처리 로그 파일 — `log`

`workspace/ai_process_log/` 에 하루 단위로 쌓입니다(90일 보관).
호스트에서 직접 읽으므로 **컨테이너가 꺼져 있어도 조회 가능**합니다.

```bash
./prod-manage.sh log               # 오늘 로그
./prod-manage.sh log 3             # 3일 전 로그
./prod-manage.sh log 2026-06-17    # 특정 날짜 로그 (YYYY-MM-DD)
./prod-manage.sh log list          # 보관 중인 로그 목록
./prod-manage.sh log 3 -f          # 실시간(follow) 보기
```

## 이미지 업데이트 (새 버전 배포)

사내에서 새로 빌드·반출한 이미지 파일을 받아, 현장에서 다시 반입 후 재기동합니다.

```bash
./prod-manage.sh load emass-ai-middelware-prod.tar.gz   # 새 이미지 반입 (같은 태그면 교체)
./prod-manage.sh up                                     # 새 이미지로 재기동
# 또는 이미 떠 있으면:  ./prod-manage.sh restart
```

## 문제 확인

```bash
./prod-manage.sh status       # 이미지 반입 여부 + 워커 실행 여부
./prod-manage.sh logs         # 실시간 출력 (연결 실패 등 원인 확인)
./prod-manage.sh log          # 오늘 처리 로그
./prod-manage.sh shell        # 컨테이너 들어가서 직접 확인
```

자주 나오는 상황:

- **`up` 했는데 "이미지가 없습니다"** → 먼저 `load` 로 이미지를 반입하세요.
- **Kafka/Mongo 연결 실패 로그** → `hosts` 로 주소 확인 후 `set-kafka`/`set-mongo` 로
  교정하고 `restart`. 방화벽/포트도 확인하세요.
- **로그에 `bootstrap.servers` 가 1개만 찍힘** → 호스트를 1개만 넣은 것입니다.
  클러스터면 3개를 다 넣어야 장애 시 페일오버가 원활합니다.

## 참고

- 이미지 안에는 `.so` 만 있고 원본 `.py` 는 없습니다. 현장에 소스가 남지 않습니다.
- 컨테이너가 올라가면 `run.py` 가 컴파일된 워커(`kafka_worker.so`)의 `main()` 을
  실행합니다. 워커가 죽으면 `restart: always` 로 자동 재기동됩니다.
- `.so` 는 **CPython 3.11 + CPU 아키텍처(x86_64) 리눅스** 용입니다. 다른 아키텍처
  서버에서는 동작하지 않으니, 그 경우 사내에서 해당 아키텍처로 다시 빌드해야 합니다.
