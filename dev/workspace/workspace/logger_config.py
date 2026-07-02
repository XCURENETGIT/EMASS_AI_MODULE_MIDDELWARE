import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
import datetime
from dotenv import load_dotenv

# .env 로드
load_dotenv()

LOG_DIR_PATH = os.environ.get("LOG_DIR_PATH")

# 로그 폴더 자동 생성
if not os.path.exists(LOG_DIR_PATH):
    try:
        os.makedirs(LOG_DIR_PATH, exist_ok=True)
    except Exception as e:
        print(f"로그 폴더 생성 실패: {e}", file=sys.stderr)
        sys.exit(1)

# 시스템 전체에서 쓸 전역 로거 설정
logger = logging.getLogger("EMASS_MIDDELWARE_LOGGER")
logger.setLevel(logging.INFO)

if not logger.handlers:
    log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] (%(filename)s:%(lineno)d) %(message)s")

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    log_file_path = os.path.join(LOG_DIR_PATH, f"emass_ai_process_{today_str}.log")
    
    file_handler = TimedRotatingFileHandler(
        filename=log_file_path,
        when="midnight",
        interval=1,
        backupCount=90,
        encoding="utf-8"
    )
    
    file_handler.suffix = "%Y-%m-%d"
    def custom_namer(default_name):
        if default_name.endswith(file_handler.suffix):
            base_path = default_name.rsplit(f"_{file_handler.suffix}.log.", 1)[0]
            date_part = default_name.rsplit(".", 1)[1]
            return f"{base_path}_{date_part}.log"
        return default_name

    file_handler.namer = custom_namer
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)