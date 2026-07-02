#!/usr/bin/env bash
#
# emass-ai-middleware 현장(배포지) 운영 스크립트  [프로덕션 전용]
# ------------------------------------------------------------------
# 이 스크립트는 "소스(.py) 없이" .so 로 컴파일된 이미지만으로 서비스를
# 운영하기 위한 것이다. 빌드는 사내에서 끝냈고, 현장에는 이미지 파일만
# 들고 나온다는 전제다. (그래서 build/save 같은 명령은 없다.)
#
# 현장에 필요한 파일:
#   prod-manage.sh              ← 이 스크립트
#   docker-compose.prod.yaml    ← 프로덕션 compose
#   <이미지>.tar.gz             ← 사내에서 반출한 .so 이미지
#   workspace/.env              ← 접속 설정 (호스트/포트/키)
#   workspace/ai_process_log/   ← 로그 폴더 (없으면 자동 생성)
#
# 사용법:  ./prod-manage.sh <명령>
#

set -euo pipefail

# ── 경로 설정 ────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yaml"

SERVICE="emass-ai-middelware"                    # compose 서비스/컨테이너 이름
CONTAINER="emass-ai-middelware"
IMAGE_TAG="emass-ai-middelware:prod"             # 반입할 .so 이미지 태그

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
    echo "❌ 컨테이너($CONTAINER)가 떠 있지 않습니다. 먼저 './prod-manage.sh up' 을 실행하세요." >&2
    exit 1
  fi
}

image_exists() {
  [ -n "$(docker images -q "$IMAGE_TAG" 2>/dev/null)" ]
}

# ── 명령 ─────────────────────────────────────────────────────

# 반출한 이미지 파일을 도커에 반입
#   ./prod-manage.sh load emass-ai-middelware-prod.tar.gz
cmd_load() {
  local f="${1:-}"
  if [ -z "$f" ]; then
    echo "사용법: ./prod-manage.sh load <이미지파일.tar.gz>" >&2
    exit 1
  fi
  case "$f" in /*) ;; *) f="$PROJECT_DIR/$f" ;; esac
  if [ ! -f "$f" ]; then
    echo "❌ 파일이 없습니다: $f" >&2
    exit 1
  fi
  echo "📥 이미지 반입: $f"
  case "$f" in
    *.gz) gunzip -c "$f" | docker load ;;
    *)    docker load -i "$f" ;;
  esac
  echo "✅ 완료. 기동: ./prod-manage.sh up"
}

# 서비스 기동 (빌드하지 않음 — 반입된 이미지만 사용)
cmd_up() {
  if ! image_exists; then
    echo "❌ 이미지가 없습니다: $IMAGE_TAG" >&2
    echo "   먼저 이미지를 반입하세요:  ./prod-manage.sh load <이미지파일.tar.gz>" >&2
    exit 1
  fi
  echo "🚀 서비스 기동 (워커 자동 실행)..."
  $DC up -d --no-build
  sleep 1
  cmd_status
}

# 서비스 내리기 (정지 + 제거)
cmd_down() {
  echo "🛑 서비스 종료..."
  $DC down
}

# 워커(컨테이너) 시작 — 정지된 컨테이너 다시 띄움
cmd_start() {
  echo "▶️  워커 시작..."
  $DC start
  sleep 1
  cmd_status
}

# 워커(컨테이너) 중지 — 컨테이너는 유지
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
  echo "🧭 모드: prod  (compose: $(basename "$COMPOSE_FILE"), 이미지: $IMAGE_TAG)"
  if image_exists; then
    echo "🖼️  이미지: 반입됨"
  else
    echo "🖼️  이미지: 없음 (load 필요)"
  fi
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

  local date_str
  if [ -z "$target_date" ]; then
    date_str="$(date +%Y-%m-%d)"
  elif [[ "$target_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    date_str="$target_date"
  elif [[ "$target_date" =~ ^[0-9]+$ ]]; then
    date_str="$(date -d "$target_date days ago" +%Y-%m-%d 2>/dev/null \
             || date -v-"${target_date}"d +%Y-%m-%d)"
  else
    echo "❌ 잘못된 날짜 형식: $target_date  (예: 3  또는  2026-06-17)" >&2
    return 1
  fi

  local file="$LOG_DIR/${LOG_PREFIX}${date_str}.log"
  if [ ! -f "$file" ]; then
    echo "❌ 해당 날짜의 로그가 없습니다: $file" >&2
    echo "   보관 중인 로그: './prod-manage.sh log list'" >&2
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
cmd_set_kafka() {
  if [ $# -eq 0 ]; then
    echo "사용법: ./prod-manage.sh set-kafka <host1> [host2] [host3] ..." >&2
    echo "  예) ./prod-manage.sh set-kafka 10.200.10.64 10.200.10.65 10.200.10.66" >&2
    exit 1
  fi
  local hosts; hosts="$(_join_hosts "$@")"
  _set_env "KAFKA_SERVER_URL" "$hosts"
  echo "✅ KAFKA_SERVER_URL = $hosts  (브로커 $#개)"
  echo "   변경 적용: ./prod-manage.sh restart"
}

# MongoDB replicaSet 멤버 호스트 설정 (공백으로 여러 개 나열)
cmd_set_mongo() {
  if [ $# -eq 0 ]; then
    echo "사용법: ./prod-manage.sh set-mongo <host1> [host2] [host3] ..." >&2
    echo "  예) ./prod-manage.sh set-mongo 10.200.10.65 10.200.10.66 10.200.10.67" >&2
    exit 1
  fi
  local hosts; hosts="$(_join_hosts "$@")"
  _set_env "MONGODB_SERVER_URL" "$hosts"
  echo "✅ MONGODB_SERVER_URL = $hosts  (멤버 $#개)"
  echo "   변경 적용: ./prod-manage.sh restart"
}

# 현재 설정된 Kafka/Mongo 호스트 확인
cmd_hosts() {
  echo "📡 현재 호스트 설정 ($ENV_FILE)"
  echo "────────────────────────────────────────────────────"
  _show_env "KAFKA_SERVER_URL"
  _show_env "KAFKA_PORT"
  _show_env "MONGODB_SERVER_URL"
  _show_env "MONGO_PORT"
  _show_env "MINIO_SERVER_URL"
  _show_env "MINIO_PORT"
}

# 컨테이너 안 셸 진입
cmd_shell() {
  require_container
  docker exec -it "$CONTAINER" /bin/bash || docker exec -it "$CONTAINER" /bin/sh
}

usage() {
  cat <<EOF
emass-ai-middleware 현장 운영 스크립트 [프로덕션 전용 / 소스 없이 이미지만]

사용법: ./prod-manage.sh <명령>

  ── 배포 ──
  load <파일>  반출한 .so 이미지(tar.gz)를 도커에 반입
  up           서비스 기동 (반입된 이미지만 사용, 빌드 안 함)
  down         서비스 종료 (정지 + 제거)

  ── 운영 ──
  start        워커(컨테이너) 시작 — 정지된 컨테이너 다시 띄움
  stop         워커(컨테이너) 중지 — 컨테이너는 유지
  restart      워커(컨테이너) 재시작
  status       상태 확인 (이미지 반입 여부 + 실행 여부)

  ── 설정 ──
  set-kafka <h1> [h2] [h3] ...   Kafka 브로커 호스트 설정 (.env)
  set-mongo <h1> [h2] [h3] ...   MongoDB replicaSet 멤버 호스트 설정 (.env)
  hosts        현재 Kafka/Mongo/MinIO 호스트 설정 확인

  ── 로그/진단 ──
  logs         워커 출력 실시간 보기
  log          날짜별 처리 로그 파일 보기
                 log              오늘 로그
                 log 3            3일 전 로그
                 log 2026-06-17   특정 날짜 로그
                 log list         보관 중인 로그 목록
                 log 3 -f         실시간(follow) 보기
  shell        컨테이너 안 셸 진입
  help         이 도움말

빠른 시작(현장):
  ./prod-manage.sh load emass-ai-middelware-prod.tar.gz
  ./prod-manage.sh set-kafka 10.200.10.64 10.200.10.65 10.200.10.66
  ./prod-manage.sh set-mongo 10.200.10.65 10.200.10.66 10.200.10.67
  ./prod-manage.sh up
  ./prod-manage.sh logs
EOF
}

# ── 디스패치 ─────────────────────────────────────────────────
case "${1:-help}" in
  load)      shift; cmd_load "$@" ;;
  up)        cmd_up ;;
  down)      cmd_down ;;
  start)     cmd_start ;;
  stop)      cmd_stop ;;
  restart)   cmd_restart ;;
  status)    cmd_status ;;
  set-kafka) shift; cmd_set_kafka "$@" ;;
  set-mongo) shift; cmd_set_mongo "$@" ;;
  hosts)     cmd_hosts ;;
  logs)      cmd_logs ;;
  log)       shift; cmd_log "$@" ;;
  shell)     cmd_shell ;;
  help|-h|--help) usage ;;
  build|run|save)
    echo "❌ '$1' 은 현장에서 쓸 수 없습니다. (소스가 필요한 작업)" >&2
    echo "   현장에서는 사내에서 반출한 이미지를 'load' 후 'up' 하세요." >&2
    exit 1 ;;
  *) echo "알 수 없는 명령: $1"; echo; usage; exit 1 ;;
esac
