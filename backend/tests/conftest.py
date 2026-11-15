"""테스트 공통 설정.

테스트는 개발용 DB에서 돌리지 않는다. 앱이 설정을 읽기 전에 DB 포트를
테스트 DB(15433)로 덮어쓴다. 환경변수는 .env보다 우선한다.
"""

import os

TEST_DB_PORT = "15433"

os.environ["POSTGRES_PORT"] = TEST_DB_PORT
