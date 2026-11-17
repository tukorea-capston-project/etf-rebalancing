"""테스트 공통 설정.

테스트는 개발용 DB(AWS 공용 DB, 로컬 개발 DB)에서 돌리지 않는다. 앱이 설정을
읽기 전에 DB 주소를 로컬 테스트 DB(localhost:15433)로 덮어쓴다.
.env의 POSTGRES_HOST가 AWS를 가리켜도 테스트는 로컬에서 돈다.
환경변수는 .env보다 우선한다.
"""

import os

TEST_DB_HOST = "localhost"
TEST_DB_PORT = "15433"

os.environ["POSTGRES_HOST"] = TEST_DB_HOST
os.environ["POSTGRES_PORT"] = TEST_DB_PORT
