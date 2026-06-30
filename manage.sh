#!/usr/bin/env bash
#
# emass-ai-middleware 관리 스크립트
# ---------------------------------
# 프로젝트 루트(도커 바깥, docker-compose.yaml 옆)에서 실행한다.
# 컨테이너(서비스)가 올라가면 kafka_worker.py 가 메인 프로세스로 바로 실행된다.
# 따라서 컨테이너 = 워커이며, 시작/중지는 곧 컨테이너 기동/정지를 뜻한다.
#
# 사용법:  ./manage.sh <명령>
#

set -euo pipefail

# ── 경로 설정 ────────────────────────────────────────────────
# 이 스크립트는 프로젝트 루트(docker-compose.yaml 와 같은 폴더)에 있다.
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yaml"

SERVICE="emass-ai-middelware"                   # compose 서비스/컨테이너 이름
CONTAINER="emass-ai-middelware"

LOG_DIR="$PROJECT_DIR/workspace/ai_process_log"  # 날짜별 로그 폴더 (호스트)
LOG_PREFIX="emass_ai_process_"                   # 로그 파일 접두사

ENV_FILE="$PROJECT_DIR/workspace/.env"           # 워커가 읽는 환경설정 파일

# docker compose vs docker-compose 자동 감지
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "❌ docker compose 명령을 찾을 수 없습니다." >&2
  exit 1
fi
DC="$DC -f $COMPOSE_FILE"

# ── 헬퍼 ─────────────────────────────────────────────────────
is_container_up() {
  [ -n "$(docker ps -q -f "name=^${CONTAINER}$" 2>/dev/null)" ]
}

require_container() {
  if ! is_container_up; then
    echo "❌ 컨테이너($CONTAINER)가 떠 있지 않습니다. 먼저 './manage.sh up' 을 실행하세요." >&2
    exit 1
  fi
}

# ── 명령 ─────────────────────────────────────────────────────

# 이미지 빌드
cmd_build() {
  echo "🔨 이미지 빌드..."
  $DC build
}

# 컨테이너 기동 → 워커(kafka_worker.py) 자동 실행
cmd_up() {
  echo "🚀 컨테이너 기동 (워커 자동 실행)..."
  $DC up -d
  sleep 1
  cmd_status
}

# 컨테이너 내리기 (정지 + 제거)
cmd_down() {
  echo "🛑 컨테이너 종료..."
  $DC down
}

# 워커(컨테이너) 시작 — 정지된 컨테이너를 다시 띄운다
cmd_start() {
  echo "▶️  워커 시작..."
  $DC start
  sleep 1
  cmd_status
}

# 워커(컨테이너) 중지 — 컨테이너는 남겨두고 정지만 한다
cmd_stop() {
  echo "⏹️  워커 중지..."
  $DC stop
}

# 워커(컨테이너) 재시작
cmd_restart() {
  echo "🔄 워커 재시작..."
  $DC restart
  sleep 1
  cmd_status
}

# 상태 확인 (컨테이너 = 워커)
cmd_status() {
  if is_container_up; then
    echo "🟢 워커(컨테이너): 실행 중"
  else
    echo "🔴 워커(컨테이너): 중지됨"
  fi
  $DC ps
}

# 워커 실시간 출력 보기 (컨테이너 stdout)
cmd_logs() {
  $DC logs -f --tail=100 "$SERVICE"
}

# 날짜별 AI 처리 로그 파일 보기
#   log                → 오늘 로그
#   log 3              → 3일 전 로그
#   log 2026-06-17     → 특정 날짜 로그
#   log list           → 보관 중인 로그 파일 목록
#   -f 옵션            → 실시간(follow) 보기
cmd_log() {
  local follow="" target_date="" arg
  for arg in "$@"; do
    case "$arg" in
      -f|--follow) follow="1" ;;
      list|ls)     _log_list; return 0 ;;
      *)           target_date="$arg" ;;
    esac
  done

  # 날짜 결정
  local date_str
  if [ -z "$target_date" ]; then
    date_str="$(date +%Y-%m-%d)"                          # 오늘
  elif [[ "$target_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    date_str="$target_date"                              # YYYY-MM-DD
  elif [[ "$target_date" =~ ^[0-9]+$ ]]; then
    date_str="$(date -d "$target_date days ago" +%Y-%m-%d 2>/dev/null \
             || date -v-"${target_date}"d +%Y-%m-%d)"    # N일 전 (GNU/BSD 모두 대응)
  else
    echo "❌ 잘못된 날짜 형식: $target_date  (예: 3  또는  2026-06-17)" >&2
    return 1
  fi

  local file="$LOG_DIR/${LOG_PREFIX}${date_str}.log"
  if [ ! -f "$file" ]; then
    echo "❌ 해당 날짜의 로그가 없습니다: $file" >&2
    echo "   보관 중인 로그: './manage.sh log list'" >&2
    return 1
  fi

  echo "📄 $file"
  echo "────────────────────────────────────────────────────"
  if [ -n "$follow" ]; then
    tail -n 100 -f "$file"
  else
    if command -v less >/dev/null 2>&1; then
      less "$file"
    else
      cat "$file"
    fi
  fi
}

# 보관 중인 로그 파일 목록 (날짜/크기)
_log_list() {
  shopt -s nullglob
  local files=("$LOG_DIR"/${LOG_PREFIX}*.log)
  shopt -u nullglob

  if [ ${#files[@]} -eq 0 ]; then
    echo "보관 중인 로그가 없습니다: $LOG_DIR"
    return 0
  fi

  echo "📂 $LOG_DIR"
  echo "────────────────────────────────────────────────────"
  local f
  for f in $(ls -1t "${files[@]}"); do
    printf "  %-12s  %6s  %s\n" \
      "$(basename "$f" | sed "s/${LOG_PREFIX}//; s/.log//")" \
      "$(du -h "$f" | cut -f1)" \
      "$(basename "$f")"
  done
}

# ── 호스트(.env) 설정 ────────────────────────────────────────
# .env 의 KEY 값을 덮어쓴다. (해당 키가 없으면 새 줄로 추가)
_set_env() {
  local key="$1" val="$2"
  if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env 파일이 없습니다: $ENV_FILE" >&2
    exit 1
  fi
  if grep -qE "^${key}=" "$ENV_FILE"; then
    # 기존 줄 치환 (GNU/BSD sed 모두 대응 위해 임시파일 경유)
    sed "s|^${key}=.*|${key}= \"${val}\"|" "$ENV_FILE" > "$ENV_FILE.tmp" \
      && mv "$ENV_FILE.tmp" "$ENV_FILE"
  else
    echo "${key}= \"${val}\"" >> "$ENV_FILE"
  fi
}

# 인자로 받은 호스트들을 콤마로 결합 (예: h1 h2 h3 → h1,h2,h3)
_join_hosts() {
  local IFS=,
  echo "$*"
}

# 현재 .env 의 호스트 키 한 줄을 보기 좋게 출력
_show_env() {
  local key="$1" line
  line="$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null || true)"
  if [ -n "$line" ]; then
    echo "  $line"
  else
    echo "  ${key}= (미설정)"
  fi
}

# Kafka 브로커 호스트 설정 (클러스터 멤버를 공백으로 여러 개 나열)
#   set-kafka 10.200.10.64 10.200.10.65 10.200.10.66
#   set-kafka 10.200.10.64:9092 10.200.10.65:9093    (host:port 도 가능)
cmd_set_kafka() {
  if [ $# -eq 0 ]; then
    echo "사용법: ./manage.sh set-kafka <host1> [host2] [host3] ..." >&2
    echo "  예) ./manage.sh set-kafka 10.200.10.64 10.200.10.65 10.200.10.66" >&2
    exit 1
  fi
  local hosts; hosts="$(_join_hosts "$@")"
  _set_env "KAFKA_SERVER_URL" "$hosts"
  echo "✅ KAFKA_SERVER_URL = $hosts  (브로커 $#개)"
  echo "   변경 적용: ./manage.sh restart"
}

# MongoDB replicaSet 멤버 호스트 설정 (공백으로 여러 개 나열)
#   set-mongo 10.200.10.65 10.200.10.66 10.200.10.67
cmd_set_mongo() {
  if [ $# -eq 0 ]; then
    echo "사용법: ./manage.sh set-mongo <host1> [host2] [host3] ..." >&2
    echo "  예) ./manage.sh set-mongo 10.200.10.65 10.200.10.66 10.200.10.67" >&2
    exit 1
  fi
  local hosts; hosts="$(_join_hosts "$@")"
  _set_env "MONGODB_SERVER_URL" "$hosts"
  echo "✅ MONGODB_SERVER_URL = $hosts  (멤버 $#개)"
  echo "   변경 적용: ./manage.sh restart"
}

# 현재 설정된 Kafka/Mongo 호스트 확인
cmd_hosts() {
  echo "📡 현재 호스트 설정 ($ENV_FILE)"
  echo "────────────────────────────────────────────────────"
  _show_env "KAFKA_SERVER_URL"
  _show_env "KAFKA_PORT"
  _show_env "MONGODB_SERVER_URL"
  _show_env "MONGO_PORT"
}

# 컨테이너 안 셸 진입
cmd_shell() {
  require_container
  docker exec -it "$CONTAINER" /bin/bash || docker exec -it "$CONTAINER" /bin/sh
}

# 빌드 + 기동 한 번에
cmd_run() {
  cmd_build
  cmd_up
}

usage() {
  cat <<EOF
emass-ai-middleware 관리 스크립트

사용법: ./manage.sh <명령>

  build      이미지 빌드
  up         컨테이너 기동 → 워커 자동 실행
  down       컨테이너 종료 (정지 + 제거)
  run        build + up (한 번에)
  start      워커(컨테이너) 시작 — 정지된 컨테이너 다시 띄움
  stop       워커(컨테이너) 중지 — 컨테이너는 유지
  restart    워커(컨테이너) 재시작
  status     워커(컨테이너) 상태 확인
  set-kafka  Kafka 브로커 호스트 설정 (여러 개는 공백 구분)
               set-kafka 10.200.10.64 10.200.10.65 10.200.10.66
  set-mongo  MongoDB replicaSet 멤버 호스트 설정 (여러 개는 공백 구분)
               set-mongo 10.200.10.65 10.200.10.66 10.200.10.67
  hosts      현재 Kafka/Mongo 호스트 설정 확인
  logs       워커 출력 실시간 보기
  log        날짜별 처리 로그 파일 보기
               log              오늘 로그
               log 3            3일 전 로그
               log 2026-06-17   특정 날짜 로그
               log list         보관 중인 로그 목록
               log 3 -f         실시간(follow) 보기
  shell      컨테이너 안 셸 진입
  help       이 도움말
EOF
}

# ── 디스패치 ─────────────────────────────────────────────────
case "${1:-help}" in
  build)   cmd_build ;;
  up)      cmd_up ;;
  down)    cmd_down ;;
  run)     cmd_run ;;
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_restart ;;
  status)  cmd_status ;;
  set-kafka) shift; cmd_set_kafka "$@" ;;
  set-mongo) shift; cmd_set_mongo "$@" ;;
  hosts)   cmd_hosts ;;
  logs)    cmd_logs ;;
  log)     shift; cmd_log "$@" ;;
  shell)   cmd_shell ;;
  help|-h|--help) usage ;;
  *) echo "알 수 없는 명령: $1"; echo; usage; exit 1 ;;
esac
