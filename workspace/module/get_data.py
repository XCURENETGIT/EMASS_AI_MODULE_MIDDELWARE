from pymongo import MongoClient
import gridfs
from bs4 import BeautifulSoup
import base64, re, os, sys
from module.set_minio import get_minio_attach_text

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from logger_config import logger
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

BOOTSTRAP_SERVERS = os.environ.get("MONGODB_SERVER_URL")
MONGO_PORT = os.environ.get("MONGO_PORT")
DATABASE_NAME = os.environ.get("DATABASE_NAME")

client = MongoClient(
        f'mongodb://{BOOTSTRAP_SERVERS}:{MONGO_PORT}/{DATABASE_NAME}?replicaSet=shard1rs&readPreference=primary&serverSelectionTimeoutMS=5000&connectTimeoutMS=10000&directConnection=true',
            maxPoolSize=50,  # 최대 연결 수 (기본값: 100)
            minPoolSize=10,  # 최소 연결 수 (기본값: 0)
            maxIdleTimeMS=300000,  # 연결이 유휴 상태로 유지될 최대 시간 (밀리초)
            waitQueueTimeoutMS=5000  # 연결 대기 시간
        )
db = client[DATABASE_NAME]

def cleanhtml(raw_html):
    """HTML 태그를 제거하고 순수 텍스트만 추출"""
    if not raw_html:
        return ""
    clean_text = BeautifulSoup(raw_html, "html.parser")
    return clean_text.get_text()


def is_base64_encoded(data):
    """데이터가 Base64로 인코딩되었는지 검증"""
    base64_pattern = re.compile(r'^[A-Za-z0-9+/=]+$')
    if isinstance(data, str):
        if len(data) % 4 == 0 and base64_pattern.match(data):
            try:
                base64.b64decode(data, validate=True)
                return True
            except Exception:
                return False
    return False


def get_body(bucket_name, filename):
    try:
        bucket = gridfs.GridFSBucket(db, bucket_name=bucket_name)
        file = bucket.open_download_stream_by_name(f"{filename}.body")
        raw_text = file.read().decode("utf-8")
        return cleanhtml(raw_text)
    except gridfs.errors.NoFile:
        print(f"[경고] GridFS 파일 없음: {filename}.body (버킷: {bucket_name})")
        return ""
    except Exception as e:
        print(f"[에러] GridFS 본문 로드 실패: {e}")
        return ""

# 🛠️ 타겟 ID 맨 앞 6자리 서픽스 파싱 로직 반영
def get_body_text(target_id):
    try:
        date_suffix = str(target_id)[:6]
        bucket_name = f"EMS_BODY_{date_suffix}"
        body_text = get_body(bucket_name, target_id)
        return body_text
    except Exception as e:
        print(f"[치명적 오류] get_body_data 처리 실패: {e}")
        return None

def get_image_path(target_id):
    img_ext = ['png','jpg','gif','jpeg','webp','svg','tiff','bmp']
    date_suffix = str(target_id)[:6]
    collection_name = f"EMS_MESSAGE_{date_suffix}"
    collection = db[collection_name]
    filter_query = {"_id": target_id}
    projection = {"_id": 0, "attached": 1, "attach": 1}
    document = collection.find_one(filter_query, projection)

    attach_status = document.get("attached")
    if attach_status == "N":
        return []

    result = []
    if attach_status == "Y":
        attach_list = document.get("attach")
        for item in attach_list:
            ext = str(item.get("ext", "")).lower()
            if ext in img_ext:
                result.append({
                    "hash": item.get("hash"),
                    "ext": item.get("ext"),
                    "path": item.get("path")
                })
            # 2. 본문 삽입 이미지(embeddedImgs) 처리
            if "embeddedImgs" in item and isinstance(item["embeddedImgs"], list):
                for embed_item in item["embeddedImgs"]:
                    if isinstance(embed_item, dict) and embed_item.get("ext", "").lower() in img_ext:
                        result.append({
                            "hash": embed_item.get("hash"),
                            "ext": embed_item.get("ext"),
                            "path": embed_item.get("path")
                        })
    return result
