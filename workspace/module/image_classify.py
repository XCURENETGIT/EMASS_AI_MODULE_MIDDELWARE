import requests,os,sys
from dotenv import load_dotenv
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from logger_config import logger

load_dotenv(dotenv_path=".env")

IMG_API_URL = os.environ.get("IMAGE")
# HTTP 타임아웃(연결, 응답) 초 — 모델 서버가 멈춰도 워커 스레드가 무한 대기하지 않도록
IMAGE_TIMEOUT = (
    float(os.environ.get("IMAGE_CONNECT_TIMEOUT", "5")),
    float(os.environ.get("IMAGE_READ_TIMEOUT", "60")),
)

# 커넥션 풀링을 위해 세션을 전역으로 재사용 (매 호출 새 커넥션 셋업 방지)
_session = requests.Session()

def image_classify(items):
    url = IMG_API_URL
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if items == []:
        logger.info("이미지가 존재하지않음")
        return None
    else:
        payload = {"items": items}

        try:
            response = _session.post(url, json=payload, headers=headers, timeout=IMAGE_TIMEOUT)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as http_err:
            logger.error(f"이미지 분류 HTTP 에러 발생: {http_err}")
            if response.text:
                logger.error(f"이미지 분류 에러 상세 내용: {response.text}")
        except Exception as err:
            logger.error(f"이미지 분류 기타 에러 발생: {err}")
        return None
