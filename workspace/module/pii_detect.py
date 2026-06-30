import grpc, os, sys, time
from google.protobuf.json_format import MessageToDict
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)
sys.path.insert(0, current_dir)

from logger_config import logger
import pii_pb2, pii_pb2_grpc

load_dotenv(dotenv_path=".env")

PII_API_URL = os.environ.get("PII")
# gRPC 호출 타임아웃(초) — 모델 서버가 멈춰도 워커가 무한 대기하지 않도록
PII_TIMEOUT = float(os.environ.get("PII_TIMEOUT", "30"))
# 첨부 항목 병렬 처리 동시성
PII_MAX_WORKERS = int(os.environ.get("PII_MAX_WORKERS", "8"))

# 채널/스텁은 스레드 세이프하므로 모듈 전역에서 1개만 생성해 재사용
# (이전에는 항목마다 새 채널을 열어 연결 셋업 비용이 반복됐음)
_channel = grpc.insecure_channel(PII_API_URL)
_stub = pii_pb2_grpc.PiiDetectorStub(_channel)


def run_pii_detect(target_text, ruleset="default_rules"):
    request_data = pii_pb2.DetectRequest(text=target_text, max_results_per_type=10, ruleset=ruleset)
    try:
        response = _stub.Detect(request_data, timeout=PII_TIMEOUT)
        response_dict = MessageToDict(response, always_print_fields_with_no_presence=True)
        response_dict.pop("meta", None)
        return response_dict
    except grpc.RpcError as e:
        logger.error(f"🚨 gRPC 통신 장애 발생: {e.code()} - {e.details()}")
        return None


def _detect_one(key, text_value, ruleset):
    t0 = time.perf_counter()
    detection_result = run_pii_detect(text_value, ruleset=ruleset)
    logger.info(f"[타이밍] pii 항목[{key}] len={len(text_value or '')} 소요: {time.perf_counter() - t0:.3f}초")
    return key, detection_result


def process_dynamic_pii_list(data_list, ruleset="default_rules"):
    processed_item = {
        "body": {},
        "attach": []
    }

    # (key, text) 쌍으로 평탄화 후 항목별 병렬 호출 — 첨부가 많을수록 선형 지연 제거
    tasks = [(key, text_value) for item in data_list for key, text_value in item.items()]
    if not tasks:
        return processed_item

    max_workers = min(PII_MAX_WORKERS, len(tasks))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = pool.map(lambda kv: _detect_one(kv[0], kv[1], ruleset), tasks)

        for key, detection_result in results:
            if key == "body":
                processed_item["body"] = detection_result
            else:
                processed_item["attach"].append({key: detection_result})
    return processed_item