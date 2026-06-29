from minio import Minio
import os, sys

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from logger_config import logger
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

KAFKA_SERVER_URL = os.environ.get("KAFKA_SERVER_URL")
MINIO_PORT = os.environ.get("MINIO_PORT")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET")
ACCESS_KEY = os.environ.get("ACCESS_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY")
SECURE = os.environ.get("SECURE", "False").lower() == "true"
REGION = os.environ.get("REGION")
MINIO_URL = f'{KAFKA_SERVER_URL}:{MINIO_PORT}'

m = Minio(MINIO_URL,access_key=ACCESS_KEY,secret_key=SECRET_KEY,secure=SECURE,region=REGION)

def get_minio_attach_text(path):
    resp = m.get_object(MINIO_BUCKET, path)
    data = resp.read()
    return data.decode('utf-8')
