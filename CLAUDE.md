# 프로젝트 개요

사용자의 자연어 입력으로 투자 전략을 완성하고, 그 전략에 따라 국내 ETF 포트폴리오를 리밸런싱하는 시스템.
운영 범위는 **백테스트 + 모의투자**까지다.

# 기술 스택

- 백엔드: Python 3.13 + FastAPI
- 패키지 관리: uv (Python 버전과 의존성은 uv로 관리하며 `uv.lock`을 커밋한다)
  - 패키지 추가·제거는 `uv add` / `uv remove`로만 한다. `pip install`은 쓰지 않는다.
- 백엔드 품질 도구: pytest(테스트), ruff(린트·포맷), pyright(타입 체크)
- 프론트엔드: React + Vite + TypeScript, 패키지 매니저는 npm
  - Node.js 26을 쓴다. `frontend/package.json`의 `engines`와 `frontend/.npmrc`의 `engine-strict=true`로 버전을 고정한다.
- 프론트엔드 품질 도구: Vitest(테스트), Oxlint(린트), Prettier(포맷)
- 증권사 API: 한국투자증권 KIS Open API (모의투자)
- LLM: Ollama로 실행하는 로컬 Qwen 계열 모델 (팀원 최저 사양 16GB 기준, 7~8B급)
  <!-- TODO: 정확한 모델 태그(예: ollama pull <모델명>) 확정 후 기입 -->
- 데이터 저장소: 팀원 각자 로컬 PostgreSQL 18. 코드에서는 SQLModel로 접근한다.

# 프로젝트 구조

- 모노레포다. `backend/`(FastAPI, uv 프로젝트)와 `frontend/`(React + Vite)를 한 저장소에 두고, `compose.yaml`과 `.env.example`은 루트에 둔다.
- 백엔드 코드는 `backend/app/` 아래에 기능(도메인)별 폴더로 나눈다.
  - `core/`: 설정, DB 연결
  - `strategy/`: 자연어 → 전략 변환, 전략 스키마
  - `portfolio/`: 포트폴리오, 리밸런싱
  - `backtest/`: 백테스트
  - `trading/`: KIS 모의투자
  - `market_data/`, `news/`, `disclosure/`: 시세·뉴스(감성 분석)·공시 수집. 백엔드의 DB 모델과 설정을 그대로 쓴다.
  - 시세 수집은 출처별 구현을 분리해, 나머지 코드를 고치지 않고 출처만 교체할 수 있게 한다.
  - 백테스트용 과거 시세는 KRX Open API의 ETF 일별매매정보에서 수집한다. 팀원마다 각자의 KRX 인증키를 쓴다.
    - 호출 1회에 기준일자(`basDd`) 하나의 전체 ETF 데이터가 온다. 기간 데이터는 날짜를 바꿔 가며 반복 호출한다.
    - 인증키당 하루 호출 한도는 10,000회이고, 데이터는 2010년 이후부터 있다.
    - 응답 필드는 모두 문자열이다. 가격·거래량 등 숫자 필드는 변환해서 저장하고, 종목코드(`ISU_CD`)는 문자열 그대로 둔다.
    - NAV, 기초지수 종가도 함께 제공된다. 분배금 필드는 없다.
  - 분배금 이력은 yfinance(Yahoo Finance)에서 수집한다. 티커 형식은 `<종목코드>.KS`이다.
    - yfinance의 분배금 날짜는 지급기준일이 아니라 분배락일(지급기준일 하루 전 영업일)이다.
    - 비공식 출처라 누락이 있을 수 있다. 화이트리스트 ETF마다 최근 분배금 몇 건을 KIND 공시나 SEIBro와 대조해 누락 여부를 확인한다.
- 각 기능 폴더는 `router.py`(API), `models.py`(DB 모델), `service.py`(로직)로 구성한다. `api/`, `services/` 같은 계층별 폴더는 만들지 않는다.
- 마이그레이션은 `backend/alembic/`, 테스트는 `backend/tests/`에 둔다.

# 데이터베이스와 설정

- DB 접속 정보, KIS 모의투자 앱키, KRX Open API 인증키 등 비밀값은 `.env`에 두고 pydantic-settings로 읽는다. `.env`는 커밋하지 않고, 필요한 키 목록은 값을 비운 `.env.example`로 커밋한다.
- 테이블 구조 변경은 SQLModel 모델을 수정한 뒤 Alembic 마이그레이션을 생성하는 방식으로만 한다. 마이그레이션 파일은 커밋하고, DB에서 테이블을 직접 수정하지 않는다.
- 새 기능 폴더에 `models.py`를 만들면 `backend/alembic/env.py`에서 import해야 한다. import하지 않으면 Alembic autogenerate가 그 테이블을 인식하지 못한다.
- PostgreSQL은 개발용·테스트용 모두 루트의 `compose.yaml`로 실행한다. 각자 직접 설치하지 않는다.
- 자동 테스트는 Compose에 정의된 테스트 전용 PostgreSQL 서비스에서 돌린다. 개발용 DB에서는 테스트를 돌리지 않는다.
- `backend/tests/conftest.py`는 앱이 설정을 읽기 전에 `POSTGRES_PORT`를 테스트 DB 포트(15433)로 덮어쓴다. 이 동작을 없애거나 우회하지 않는다.
- DB 비밀번호는 `.env`의 `POSTGRES_PASSWORD` 한 곳에만 쓴다. 접속 주소는 `backend/app/core/config.py`가 `POSTGRES_*` 값으로 만든다. `.env`에 `DATABASE_URL`을 따로 두지 않는다.
- 포트는 개발 DB `15432`, 테스트 DB `15433`이다. 직접 설치한 PostgreSQL의 기본 포트 5432와 충돌하지 않게 하려는 것이다.

# 명령어

처음 설정: 루트의 `.env.example`을 복사해 `.env`를 만들고 값을 채운다.

DB (루트에서)
- 개발·테스트 DB 실행: `docker compose up -d`

백엔드 (`backend/`에서)
- 의존성 설치: `uv sync`
- 개발 서버: `uv run fastapi dev app/main.py`
- 전체 테스트: `uv run pytest`
- 테스트 파일 하나: `uv run pytest tests/<경로>/test_<이름>.py`
- 린트: `uv run ruff check .` / 포맷: `uv run ruff format .`
- 타입 체크: `uv run pyright`
- 마이그레이션 생성: `uv run alembic revision --autogenerate -m "<변경 내용>"`
- 마이그레이션 적용: `uv run alembic upgrade head`

프론트엔드 (`frontend/`에서)
- 의존성 설치: `npm install`
- 개발 서버: `npm run dev`
- 전체 테스트: `npx vitest run`
- 테스트 파일 하나: `npx vitest run <경로>`
- 린트: `npm run lint` / 포맷: `npx prettier --write .`
- 타입 체크: `npx tsc -b`

# 도메인 규칙

## 자연어 → 전략 변환
- LLM 출력은 정해진 스키마로 받아 검증한 뒤, 사용자가 확인해야만 전략으로 확정한다.
- 전략 스키마는 `backend/app/strategy/` 안에 Pydantic 모델로 정의한다.

## 투자 대상
- 투자 대상은 사전 정의된 ETF 목록(화이트리스트) 안에서만 고른다.
- 화이트리스트는 저장소에 커밋된 설정 파일로 관리한다. DB는 팀원마다 따로라서, 목록을 DB에만 두면 팀원 간에 어긋난다.
- 화이트리스트 파일은 `backend/config/` 아래에 YAML 형식으로 둔다.
- 종목코드는 코드 전체에서 항상 6자리 문자열로 다룬다. YAML에서는 반드시 따옴표로 감싼다(`"012450"`). 따옴표가 없으면 PyYAML이 `012450`을 8진수 `5416`으로 읽는다.

## 리밸런싱
- 리밸런싱 조건(주기, 비중 이탈 밴드, 혼합 등)은 고정하지 않고 사용자 전략에 정의된 대로 따른다.

## 백테스트
- 백테스트 수익률은 ETF 분배금을 재투자했다고 가정한 총수익률로 계산한다. 가격은 KRX의 실제 종가(비수정)를 쓰고, 분배금은 분배락일에 재투자한다.
- 분배금이 이미 반영된 수정주가(FinanceDataReader 가격, yfinance `Adj Close`)를 KRX 종가와 섞어 쓰지 않는다. 분배금이 두 번 반영된다.
- 백테스트에는 수수료와 슬리피지를 반영한다.
- 비용 가정치는 코드에 하드코딩하지 않고 설정값으로 분리한다.

## 모의투자 / KIS
- KIS는 모의투자 도메인만 쓴다. REST는 `https://openapivts.koreainvestment.com:29443`, WebSocket은 `ws://ops.koreainvestment.com:31000`이다.
- 실전투자 도메인(`openapi.koreainvestment.com:9443`, WebSocket 포트 `21000`)은 시세 조회를 포함해 어떤 용도로도 쓰지 않는다.
- 실전투자용 앱키·시크릿·계좌번호는 발급하거나 보관하지 않으며 `.env`에도 두지 않는다.
- KIS 클라이언트의 주소는 코드에서 모의투자 주소로 고정한다. 설정값이 실전 주소이면 서버가 시작되지 않도록 검사한다.
- 접근 토큰은 캐시해서 재사용하고 요청마다 새로 발급하지 않는다. 토큰 유효기간은 1일이고, 재발급은 1분에 1회로 제한되며, 발급할 때마다 알림톡이 발송된다.
- 모의투자는 REST 호출 제한이 낮다. 호출 간격을 조절하고, 초당 호출 초과 오류(`EGW00201`)가 나면 재시도한다.

# 협업 규칙

- 팀 프로젝트다. 이 파일은 git으로 공유하며, 개인 설정은 `CLAUDE.local.md`(gitignore 대상)에 둔다.
- 코드 주석, 문서, 커밋 메시지는 한국어로 작성한다.
- 팀 개발 환경은 macOS와 Windows가 섞여 있다. 스크립트, 명령어, 파일 경로는 두 OS에서 모두 동작해야 한다.
