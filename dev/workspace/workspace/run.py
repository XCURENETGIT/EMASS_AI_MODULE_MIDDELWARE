# run.py — 프로덕션 실행 런처 (로직 없음, 평문 유지)
# ------------------------------------------------------------
# 프로덕션 이미지에서는 kafka_worker 가 .so 로 컴파일되어 있어
# `python3 kafka_worker.py` 로 직접 실행할 수 없다.
# 그래서 컴파일된 kafka_worker 모듈의 main() 을 임포트해 호출하는
# 얇은 런처를 둔다. (개발 환경에서도 그대로 동작한다.)
from kafka_worker import main

if __name__ == "__main__":
    main()
