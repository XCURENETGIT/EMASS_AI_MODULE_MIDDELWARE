import requests, base64, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from logger_config import logger

load_dotenv(dotenv_path=".env")

DETECT_API_URL = os.environ.get("CLASSIFY")
# HTTP 타임아웃(연결, 응답) 초 — 모델 서버가 멈춰도 워커 스레드가 무한 대기하지 않도록
CLASSIFY_TIMEOUT = (
    float(os.environ.get("CLASSIFY_CONNECT_TIMEOUT", "5")),
    float(os.environ.get("CLASSIFY_READ_TIMEOUT", "60")),
)
# 첨부 항목 병렬 처리 동시성
CLASSIFY_MAX_WORKERS = int(os.environ.get("CLASSIFY_MAX_WORKERS", "8"))

# 커넥션 풀링을 위해 세션을 전역으로 재사용 (매 호출 새 커넥션 셋업 방지)
_session = requests.Session()

def encode_text_to_base64(text: str) -> str:
    if not text:
        return ""
    text_bytes = text.encode("utf-8")
    base64_bytes = base64.b64encode(text_bytes)
    return base64_bytes.decode("utf-8")

def text_classify_code_detect(encoded_text: str):
    url = DETECT_API_URL
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    payload = {"text": encoded_text}

    try:
        response = _session.post(url, json=payload, headers=headers, timeout=CLASSIFY_TIMEOUT)
        response.raise_for_status()
        api_result = response.json()

        custom_response = {
            "success": True,
            "message": "OK",
            "status": "200",  # result 키를 status로 변경하고 값은 "OK"
            "data": {
                "code_exist": api_result.get("code_exist"),
                "keywords": api_result.get("keywords"),
                "probs": api_result.get("probs"),
                "class": api_result.get("class")
            }
        }
        return custom_response

    except requests.exceptions.HTTPError as http_err:   
        logger.error(f"문서분류 및 코드탐지 HTTP 에러 발생: {http_err}")
        if 'response' in locals() and response.text:
            logger.error(f"문서분류 및 코드탐지 에러 상세 내용: {response.text}")
        return {"success": False, "error": f"HTTP Error: {http_err}"}
    except Exception as err:
        logger.error(f"문서분류 및 코드탐지 기타 에러 발생: {err}")
        return {"success": False, "error": str(err)}

def _classify_one(key, text_value):
    encoded_text = encode_text_to_base64(text_value)
    t0 = time.perf_counter()
    detection_result = text_classify_code_detect(encoded_text)
    logger.info(f"[타이밍] classify 항목[{key}] len={len(text_value or '')} 소요: {time.perf_counter() - t0:.3f}초")
    return key, detection_result


def process_dynamic_classify_list(data_list: list) -> dict:
    processed_item = {
        "body": {},
        "attach": []
    }

    # (key, text) 쌍으로 평탄화 후 항목별 병렬 호출 — 가장 느린 단일 항목 수준으로 단축
    tasks = [(key, text_value) for item in data_list for key, text_value in item.items()]
    if not tasks:
        return processed_item

    max_workers = min(CLASSIFY_MAX_WORKERS, len(tasks))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = pool.map(lambda kv: _classify_one(kv[0], kv[1]), tasks)

        for key, detection_result in results:
            if key == "body":
                processed_item["body"] = detection_result
            else:
                processed_item["attach"].append({key: detection_result})
    return processed_item
