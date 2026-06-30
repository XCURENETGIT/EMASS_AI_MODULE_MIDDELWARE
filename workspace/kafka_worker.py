import json, os, time
from datetime import datetime, timezone
from confluent_kafka import Consumer, Producer, KafkaError, KafkaException
from logger_config import logger
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from module.get_data import get_body_text, get_image_path, get_attach_text
from module.image_classify import image_classify
from module.code_text_detect import process_dynamic_classify_list
from module.pii_detect import process_dynamic_pii_list

load_dotenv()

# 환경변수 바인딩
KAFKA_HOSTS_RAW = os.environ.get("KAFKA_SERVER_URL")
KAFKA_PORT = os.environ.get("KAFKA_PORT")
CONSUMER_GROUP_ID = os.environ.get("KAFKA_GROUP")
CONSUMER_TOPIC_NAME = os.environ.get("KAFKA_SOURCE_TOPIC")
PRODUCER_TOPIC_NAME = os.environ.get("KAFKA_TARGET_TOPIC")
raw_prefixes = os.environ.get("IGNORE_SVC_PREFIXES")
IGNORE_PREFIXES = tuple(p.strip().upper() for p in raw_prefixes.split(",") if p.strip())


# 콤마로 구분된 다중 브로커 호스트를 bootstrap.servers 문자열로 변환.
#   - "h1,h2,h3"        → "h1:PORT,h2:PORT,h3:PORT"  (클러스터 브로커 3개)
#   - "h1:9092,h2:9093" → 호스트에 포트가 이미 있으면 그대로 사용
def build_bootstrap(hosts_raw, default_port):
    servers = []
    for h in (hosts_raw or "").split(","):
        h = h.strip()
        if not h:
            continue
        servers.append(h if ":" in h else f"{h}:{default_port}")
    if not servers:
        raise ValueError("KAFKA_SERVER_URL 이 비어 있습니다. (.env 또는 ./manage.sh set-kafka 로 설정)")
    return ",".join(servers)


BOOTSTRAP_SERVERS = build_bootstrap(KAFKA_HOSTS_RAW, KAFKA_PORT)
logger.info(f"Kafka bootstrap.servers: {BOOTSTRAP_SERVERS}")

# (이하 카프카 설정 및 메인 루프 코드는 동일)
consumer_config = {
    "bootstrap.servers": BOOTSTRAP_SERVERS,
    "group.id": CONSUMER_GROUP_ID,
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
}

producer_config = {
    "bootstrap.servers": BOOTSTRAP_SERVERS,
    "acks": "all",
    "compression.type": "snappy"
}

# 모듈별 처리 시간 측정용 헬퍼 (반환값은 그대로 전달)
def timed(name, fn, *args, **kwargs):
    t0 = time.perf_counter()
    try:
        return fn(*args, **kwargs)
    finally:
        logger.info(f"[타이밍] {name} 소요: {time.perf_counter() - t0:.3f}초")


# 프로듀서 전송 결과 비동기 콜백 함수
def delivery_report(err, msg):
    if err is not None:
        logger.error(f"프로듀서 메시지 전달 실패: {err}")
    else:
        # 분리된 로그 파일에 프로듀서 전송 성공 팩트 기록
        logger.info(f"프로듀서 전송 완료 ➡️ 토픽: {msg.topic()} [파티션: {msg.partition()}]")



def process_message(msg,executor):
    try:
        if msg.key() is not None:
            msgKey = msg.key().decode("utf-8")
        else:
            logger.info("Received message with no key content")
            msgKey = None

        if msg.value() is not None:
            msgContents = msg.value().decode("utf-8")
            msgJson = json.loads(msgContents)
        else:
            logger.info("Received message with no content")
            return None

        # svc 가 환경설정에 있는 서비스타입이 아닌 경우에만 진행
        svc_value = msgJson.get('svc', '').strip().upper()
        if svc_value and svc_value.startswith(IGNORE_PREFIXES):
            # 처리 대상이 아닌 메시지는 타이밍/로그 없이 조용히 스킵
            return None

        # 여기서부터가 실제 처리 대상 메시지 (타이밍 측정 시작)
        start_time = time.perf_counter()
        try:
            logger.info(f"Processing message key: {msgKey}")
            body = timed("get_body_text", get_body_text, msgKey)
            image_path = timed("get_image_path", get_image_path, msgKey)
            text = timed("get_attach_text", get_attach_text, msgKey)
            #text['body'] = body
            text.append({'body':body})
            future_to_task = {
            executor.submit(timed, "pii", process_dynamic_pii_list, text): "pii",
            executor.submit(timed, "classify", process_dynamic_classify_list, text): "classify",
            executor.submit(timed, "image", image_classify, image_path): "image"
            }

            task_results = {}

            for future in as_completed(future_to_task):
                task_name = future_to_task[future]
                try:
                    data = future.result()  # 개별 스레드 작업 완료 결과물 획득
                    task_results[task_name] = data
                except Exception as exc:
                    logger.error(f"하위 스레드 [{task_name}] 실행 중 예외 터짐: {exc}")
                    task_results[task_name] = None

            processed = {"type" : "normal", "key": msgKey, "data": task_results}
            logger.info(f'최종 결과물 : {processed}')
            return processed
        finally:
            elapsed = time.perf_counter() - start_time
            logger.info(f"메시지 처리 소요 시간: {elapsed:.3f}초")

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        return None




def main():
    consumer = Consumer(consumer_config)
    producer = Producer(producer_config)

    consumer.subscribe([CONSUMER_TOPIC_NAME])
    logger.info(f"emass 파이프라인 엔진 가동... [그룹 ID: {CONSUMER_GROUP_ID}]")

    with ThreadPoolExecutor(max_workers=4) as executor:
        try:
            while True:
                msg = consumer.poll(timeout=1.0)
                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.info(f"End of partition reached {msg.topic()} [{msg.partition()}] at offset {msg.offset()}")
                    else:
                        raise KafkaException(msg.error())
                else:
                    try:
                        # ----------------------------------------------------
                        # [데이터 가공 및 비즈니스 파싱 영역]
                        processed_result = process_message(msg,executor)

                        if processed_result is None:
                            consumer.commit(asynchronous=False)
                            continue
                        # ----------------------------------------------------

                        # 3. [MISSING RESOLVED] 프로듀서로 가공된 데이터 전송 로직
                        serialized_output = json.dumps(processed_result, ensure_ascii=False).encode('utf-8')
                        
                        producer.produce(
                            topic=PRODUCER_TOPIC_NAME,
                            value=serialized_output,
                            key=msg.key(),  # 메시지 순서 유지를 위해 원본 키 상속
                            callback=delivery_report
                        )
                        
                        # 내부 프로듀서 버퍼 비동기 이벤트 트리거
                        producer.poll(0)

                        # 4. 전송 무결성 검증 후 최종 오프셋 수동 동기 커밋 (At-least-once 보장)
                        consumer.commit(asynchronous=False)

                    except json.JSONDecodeError:
                        logger.error("JSON 디코딩 장애 발생. 파싱 실패 원문 격리 조치.")
                        consumer.commit(asynchronous=False)
                    except Exception as e:
                        logger.error(f"컨슘 로직 내부 예외 발생 처리 보류: {e}")

        except KeyboardInterrupt:
            logger.info("정지 시그널 감지. 워커 프로세스를 안전하게 종료합니다.")
        finally:
            # 종료 전 클린업 가동 (남은 프로듀서 메시지 강제 플러시 후 컨슈머 닫기)
            producer.flush()
            consumer.close()
            logger.info("모든 인프라 스트림 파이프라인 자원이 정상적으로 반납되었습니다.")

if __name__ == "__main__":
    main()

# with ThreadPoolExecutor(max_workers=4) as executor:
#     start_time = time.perf_counter()
#     try:
#         #msgKey="20260507143827.Z4MA6HMMJDSRHDU5NQX67Q4BMIZUEKGF"
#         msgKey="20260507162153.2GZAAADRD2EWNSVUKQPDLFAOB55CK66L"
#         logger.info(f"Processing message key: {msgKey}")
#         body = timed("get_body_text", get_body_text, msgKey)
#         image_path = timed("get_image_path", get_image_path, msgKey)
#         text = timed("get_attach_text", get_attach_text, msgKey)
#         text.append({'body':body})
#         future_to_task = {
#         executor.submit(timed, "pii", process_dynamic_pii_list, text): "pii",
#         executor.submit(timed, "classify", process_dynamic_classify_list, text): "classify",
#         executor.submit(timed, "image", image_classify, image_path): "image"
#         }

#         task_results = {}

#         for future in as_completed(future_to_task):
#             task_name = future_to_task[future]
#             try:
#                 data = future.result()  # 개별 스레드 작업 완료 결과물 획득
#                 task_results[task_name] = data
#             except Exception as exc:
#                 logger.error(f"하위 스레드 [{task_name}] 실행 중 예외 터짐: {exc}")
#                 task_results[task_name] = None

#         processed = {"type" : "normal", "msgid": msgKey, "data": task_results}
#         logger.info(f'최종 결과물 : {processed}')

#     except Exception as e:
#         logger.error(f"Error processing message: {e}")
#     finally:
#         elapsed = time.perf_counter() - start_time
#         logger.info(f"메시지 처리 소요 시간: {elapsed:.3f}초")