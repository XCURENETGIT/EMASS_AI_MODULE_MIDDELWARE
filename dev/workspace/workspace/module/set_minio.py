from minio import Minio
import os, sys

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from logger_config import logger
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

MINIO_SERVER_URL = os.environ.get("MINIO_SERVER_URL")
KAFKA_SERVER_URL = os.environ.get("KAFKA_SERVER_URL")
MINIO_PORT = os.environ.get("MINIO_PORT")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET")
ACCESS_KEY = os.environ.get("ACCESS_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY")
SECURE = os.environ.get("SECURE", "False").lower() == "true"
REGION = os.environ.get("REGION")

# MinIO 는 단일 엔드포인트다. 전용 MINIO_SERVER_URL 이 있으면 그걸 쓰고,
# 없으면 (구버전 호환) KAFKA_SERVER_URL 의 '첫 번째' 호스트를 사용한다.
# ※ KAFKA_SERVER_URL 이 콤마 다중 호스트여도 여기서 첫 호스트만 취하므로 안전.
minio_host = (MINIO_SERVER_URL or (KAFKA_SERVER_URL or "").split(",")[0]).strip()
MINIO_URL = f'{minio_host}:{MINIO_PORT}'

m = Minio(MINIO_URL,access_key=ACCESS_KEY,secret_key=SECRET_KEY,secure=SECURE,region=REGION)

def get_minio_attach_text(path):
    resp = m.get_object(MINIO_BUCKET, path)
    data = resp.read()
    return data.decode('utf-8')