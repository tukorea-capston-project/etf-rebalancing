# 프로젝트 개요

사용자의 자연어 입력으로 투자 전략을 완성하고, 그 전략에 따라 국내 ETF 포트폴리오를 리밸런싱하는 시스템.
운영 범위는 **백테스트 + 모의투자 + 실전투자**다.
여러 사용자가 각자 자기 KIS 계좌를 등록해 쓰는 실제 서비스로 배포할 수 있게 만드는 것이 목표다. 개발·시연은 팀원 계정과 팀원 본인 계좌로 한다.
프로세스 구성(CloudFront, 리버스 프록시, API 서버, 워커)과 작업 실행 방식은 `docs/architecture.md`.

# 기술 스택

- 백엔드: Python 3.13 + FastAPI
- 패키지 관리: uv (Python 버전과 의존성은 uv로 관리하며 `uv.lock`을 커밋한다)
  - 패키지 추가·제거는 `uv add` / `uv remove`로만 한다. `pip install`은 쓰지 않는다.
- 백엔드 품질 도구: pytest(테스트), ruff(린트·포맷), pyright(타입 체크)
- 프론트엔드: React + Vite + TypeScript, 패키지 매니저는 npm
  - Node.js 26을 쓴다. `frontend/package.json`의 `engines`와 `frontend/.npmrc`의 `engine-strict=true`로 버전을 고정한다.
- 프론트엔드 품질 도구: Vitest(테스트), Oxlint(린트), Prettier(포맷)
- 증권사 API: 한국투자증권 KIS Open API (모의투자·실전투자)
- LLM: Ollama로 실행하는 로컬 Qwen 계열 모델 (팀원 최저 사양 16GB 기준, 7~8B급). AWS에서는 돌리지 않는다.
  <!-- TODO: 정확한 모델 태그(예: ollama pull <모델명>) 확정 후 기입 -->
- 데이터 저장소: PostgreSQL 18. 서비스 DB는 AWS EC2에 두고, 테스트 DB는 각자 로컬에서 띄운다. 코드에서는 SQLModel로 접근한다.
- 서버: AWS EC2 한 대에 백엔드(Caddy, API 서버, 워커)와 서비스 DB를 Docker Compose로 띄운다. 프론트엔드는 S3 + CloudFront로 배포한다.
- 사설망: Tailscale. EC2와 LLM PC를 잇는 데 쓰고, 팀원 PC는 관리 접근(서비스 DB, SSH)에만 참여한다.
- CI/CD: GitHub Actions. 백엔드 이미지는 GHCR에 올린다.
- 비밀값 암호화: KIS 자격 증명의 암호화 마스터키는 AWS KMS에 둔다(팀원 PC는 로컬 키).

# 실행 환경

상세(구성도, CloudFront·Tailscale 설정, 배포, 시연 체크리스트)는 `docs/infra.md`.

- 서비스(프론트엔드와 API)는 인터넷에 공개한다. 사용자는 서비스 도메인(CloudFront)으로만 접속한다. CloudFront가 `/api/*`는 EC2로, 나머지는 S3의 프론트엔드 빌드 결과로 보내므로 프론트엔드와 API는 같은 오리진이다.
- CloudFront와 EC2 사이도 HTTPS다. EC2의 Caddy가 오리진용 하위 도메인의 인증서로 처리한다. EC2 보안그룹은 `443`을 CloudFront에서 오는 요청에만 연다.
- DB 포트(`15432`), SSH, Ollama 포트(`11434`)는 인터넷에 열지 않는다. Tailscale 사설망으로만 접근한다.
- 예약 작업(시세 수집, 리밸런싱 계산, 주문 등)과 백테스트 대기열은 워커 프로세스에서만 실행하고, 워커는 EC2에서 하나만 띄운다. API 서버는 예약 작업을 돌리지 않는다. 팀원 PC의 API 서버도 서비스 DB에 붙으므로, 예약 작업이 API 서버에 있으면 수집·주문이 여러 곳에서 중복 실행된다.
- 인증은 서버 세션(DB 저장) + `HttpOnly`·`Secure` 쿠키다. 상세는 `docs/auth.md`.
- 배포는 GitHub Actions가 사람의 승인 없이 자동으로 한다. 평일 07:30–17:00 KST에는 배포하지 않는다(워커 작업 보호). 상세는 `docs/infra.md`.
- LLM 호출 주소는 `.env`의 `OLLAMA_BASE_URL` 하나로 정한다. 코드에 주소를 하드코딩하지 않는다.
  - 개발: 각자 PC에서 백엔드를 띄우고 자기 PC의 Ollama(`http://localhost:11434`)를 호출한다. LLM PC가 없어도 개발할 수 있다.
  - AWS 백엔드: LLM PC 한 대만 호출한다. LLM PC가 꺼져 있을 때 팀원 PC로 대체하지 않는다.
- LLM PC의 Ollama는 그 PC의 Tailscale 주소(`100.x.y.z`)에만 바인딩한다(`OLLAMA_HOST=100.x.y.z:11434`). Ollama API에는 인증이 없다. `OLLAMA_HOST=0.0.0.0`은 같은 와이파이(LAN)에도 노출되므로 쓰지 않는다.
- Tailscale 접근 정책(ACL)은 기본값(모든 기기 간 허용)을 쓰지 않는다. LLM PC의 `11434`에는 EC2만 접근할 수 있게 막는다.
- 개발 PC와 LLM PC는 모두 같은 모델 태그를 쓴다. 모델이 다르면 스키마 검증 결과가 PC마다 달라진다.
- LLM 호출에는 타임아웃을 두고, 연결할 수 없으면 원인이 드러나는 오류를 돌려준다. LLM이 꺼져 있어도 전략 변환 외의 기능은 동작해야 한다.

# 프로젝트 구조

- 모노레포다. `backend/`(FastAPI, uv 프로젝트)와 `frontend/`(React + Vite)를 한 저장소에 둔다.
  - 루트: `compose.yaml`(팀원 PC용 테스트 DB), `.env.example`
  - `deploy/compose.yaml`: EC2 운영용 Compose (Caddy, API 서버, 워커, 서비스 DB)
  - `.github/workflows/`: CI/CD 워크플로
- 백엔드 코드는 `backend/app/` 아래에 기능(도메인)별 폴더로 나눈다.
  - `core/`: 설정, DB 연결
  - `auth/`: 사용자, 세션, 로그인
  - `worker/`: 워커 진입점. 예약 작업 시각표와 백테스트 대기열 처리만 두고, 실제 로직은 각 도메인의 `service.py`를 부른다. 도메인 폴더가 아니므로 아래 `router.py`/`models.py`/`service.py` 구성의 예외다.
  - `strategy/`: 자연어 → 전략 변환, 전략 스키마
  - `portfolio/`: 포트폴리오, 리밸런싱
  - `backtest/`: 백테스트
  - `trading/`: KIS 모의·실전투자 주문, KIS 자격 증명
  - `market_data/`, `news/`, `disclosure/`: 시세·뉴스(감성 분석)·공시 수집. 백엔드의 DB 모델과 설정을 그대로 쓴다.
  - 시세 수집은 출처별 구현을 분리해, 나머지 코드를 고치지 않고 출처만 교체할 수 있게 한다.
  - 백테스트용 과거 시세는 KRX Open API의 ETF 일별매매정보에서 수집한다. 서비스 DB에는 한 곳(지금은 담당 팀원, 나중에는 EC2의 워커)에서만 수집하고, KRX 인증키는 수집하는 쪽의 것을 쓴다.
    - 호출 1회에 기준일자(`basDd`) 하나의 전체 ETF 데이터가 온다. 기간 데이터는 날짜를 바꿔 가며 반복 호출한다.
    - 인증키당 하루 호출 한도는 10,000회이고, 데이터는 2010년 이후부터 있다.
    - 응답 필드는 모두 문자열이다. 가격·거래량 등 숫자 필드는 변환해서 저장하고, 종목코드(`ISU_CD`)는 문자열 그대로 둔다.
    - NAV, 기초지수 종가도 함께 제공된다. 분배금 필드는 없다.
  - 분배금 이력은 yfinance(Yahoo Finance)에서 수집한다. 티커 형식은 `<종목코드>.KS`이다.
    - yfinance의 분배금 날짜는 지급기준일이 아니라 분배락일(지급기준일 하루 전 영업일)이다.
    - 비공식 출처라 누락이 있을 수 있다. 틀린 값은 DB가 아니라 저장소의 보정 YAML(`backend/config/distribution_overrides.yaml`)로 고친다.
  - 수집 대상, 수집 이력, 신규 ETF 처리 등 상세는 `docs/market-data.md`.
- 각 기능 폴더는 `router.py`(API), `models.py`(DB 모델), `service.py`(로직)로 구성한다. `api/`, `services/` 같은 계층별 폴더는 만들지 않는다.
- 마이그레이션은 `backend/alembic/`, 테스트는 `backend/tests/`에 둔다.

# 데이터베이스와 설정

- DB 접속 정보, KRX Open API 인증키 등 서버 비밀값은 `.env`에 두고 pydantic-settings로 읽는다. `.env`는 커밋하지 않고, 필요한 키 목록은 값을 비운 `.env.example`로 커밋한다.
- KIS 앱키·시크릿·계좌번호는 사용자의 것이므로 `.env`에 두지 않는다. 사용자별로 등록받아 DB에 암호화해 저장한다.
- 테이블 구조 변경은 SQLModel 모델을 수정한 뒤 Alembic 마이그레이션을 생성하는 방식으로만 한다. 마이그레이션 파일은 커밋하고, DB에서 테이블을 직접 수정하지 않는다.
- 새 기능 폴더에 `models.py`를 만들면 `backend/alembic/env.py`에서 import해야 한다. import하지 않으면 Alembic autogenerate가 그 테이블을 인식하지 못한다.
- 서비스 DB는 AWS EC2에서 Docker로 실행한다. 팀원 PC에서는 테스트 DB만 루트의 `compose.yaml`로 실행한다. 로컬 개발 DB는 두지 않는다. PostgreSQL을 직접 설치하지 않는다.
  - 팀원 PC의 개발 서버는 `.env`의 `POSTGRES_HOST`에 EC2의 Tailscale 주소를 넣어 서비스 DB에 붙는다. 서비스 DB에는 실제 사용자 데이터가 있다.
- 서비스 DB에는 main에 머지된 마이그레이션만 적용하고, 적용은 CD가 배포할 때 한다. 서비스 DB를 머지 전 스키마로 바꾸면 배포된 서버와 다른 팀원의 개발 서버가 깨진다.
  - 머지 전 스키마 변경은 개발 서버를 테스트 DB(`POSTGRES_HOST=localhost`, `POSTGRES_PORT=15433`)에 붙여 확인한다. 마이그레이션이 빈 DB에 끝까지 적용되는지는 CI가 검사한다.
- 자동 테스트는 Compose에 정의된 테스트 전용 PostgreSQL 서비스(각자 로컬)에서 돌린다. 서비스 DB에서는 테스트를 돌리지 않는다.
- `backend/tests/conftest.py`는 앱이 설정을 읽기 전에 `POSTGRES_HOST`를 `localhost`로, `POSTGRES_PORT`를 테스트 DB 포트(15433)로 덮어쓴다. 이 동작을 없애거나 우회하지 않는다.
- DB 비밀번호는 `.env`의 `POSTGRES_PASSWORD` 한 곳에만 쓴다. 접속 주소는 `backend/app/core/config.py`가 `POSTGRES_*` 값으로 만든다. `.env`에 `DATABASE_URL`을 따로 두지 않는다.
- 포트는 서비스 DB `15432`, 테스트 DB `15433`이다. 직접 설치한 PostgreSQL의 기본 포트 5432와 충돌하지 않게 하려는 것이다.

# 명령어

처음 설정: 루트의 `.env.example`을 복사해 `.env`를 만들고 값을 채운다.

DB (루트에서)
- 테스트 DB 실행: `docker compose up -d db-test`

백엔드 (`backend/`에서)
- 의존성 설치: `uv sync`
- 개발 서버: `uv run fastapi dev app/main.py`
- 전체 테스트: `uv run pytest`
- 테스트 파일 하나: `uv run pytest tests/<경로>/test_<이름>.py`
- 린트: `uv run ruff check .` / 포맷: `uv run ruff format .`
- 타입 체크: `uv run pyright`
- 마이그레이션 생성: `uv run alembic revision --autogenerate -m "<변경 내용>"`
- 마이그레이션 적용: `uv run alembic upgrade head`
- 시세·분배금 수집: `uv run python -m app.market_data` (서비스 DB에는 담당 팀원만 실행. `docs/market-data.md`)

프론트엔드 (`frontend/`에서)
- 의존성 설치: `npm install`
- 개발 서버: `npm run dev`
- 전체 테스트: `npx vitest run`
- 테스트 파일 하나: `npx vitest run <경로>`
- 린트: `npm run lint` / 포맷: `npx prettier --write .`
- 타입 체크: `npx tsc -b`

# 도메인 규칙

상세 설계(알고리즘, 계산 규칙)는 `docs/<도메인>.md`에 둔다. 도메인 코드를 다룰 때 Claude가 지킬 핵심 규칙은 `.claude/rules/<도메인>.md`에 `paths`로 범위를 걸어 둔다. 설계가 바뀌면 둘 다 고친다.

## 자연어 → 전략 변환
- LLM 출력은 정해진 스키마로 받아 검증한 뒤, 사용자가 확인해야만 전략으로 확정한다.
- 전략 스키마는 `backend/app/strategy/` 안에 Pydantic 모델로 정의한다. 상세는 `docs/strategy-schema.md`.

## 투자 대상
- 투자 대상은 사전 정의된 ETF 목록(화이트리스트) 안에서만 고른다.
- 화이트리스트는 저장소에 커밋된 설정 파일로 관리한다. 목록을 DB에만 두면 변경이 리뷰·이력으로 남지 않고, 테스트 DB와도 어긋난다.
- 화이트리스트 파일은 `backend/config/` 아래에 YAML 형식으로 둔다.
- 종목코드는 코드 전체에서 항상 6자리 문자열로 다룬다. 최근 상장 종목은 영문 대문자가 섞이므로(예: `"0184E0"`) 숫자로 변환하거나 숫자만 허용하지 않는다. YAML에서는 반드시 따옴표로 감싼다(`"012450"`). 따옴표가 없으면 PyYAML이 `012450`을 8진수 `5416`으로 읽는다.

## 리밸런싱
- 리밸런싱 조건(주기, 비중 이탈 밴드, 혼합 등)은 고정하지 않고 사용자 전략에 정의된 대로 따른다. 상세는 `docs/rebalancing.md`.

## 백테스트
- 백테스트 수익률은 ETF 분배금을 재투자했다고 가정한 총수익률로 계산한다. 가격은 KRX의 실제 종가(비수정)를 쓰고, 분배금은 분배락일에 그 ETF에 재투자한다.
- 분배금이 이미 반영된 수정주가(FinanceDataReader 가격, yfinance `Adj Close`)를 KRX 종가와 섞어 쓰지 않는다. 분배금이 두 번 반영된다.
- 백테스트에는 수수료와 슬리피지를 반영한다.
- 비용 가정치는 코드에 하드코딩하지 않고 설정값으로 분리한다.
- 상세(체결 가정, 세금, 성과 지표, 비교 기준)는 `docs/backtest.md`.

## 모의·실전투자 / KIS
- KIS 주소는 모드별로 두 개뿐이다. 코드 상수로 고정하고 모드로 고르며, 설정값으로 주소를 받지 않는다.
  - 모의: REST `https://openapivts.koreainvestment.com:29443`, WebSocket `ws://ops.koreainvestment.com:31000`
  - 실전: REST `https://openapi.koreainvestment.com:9443`, WebSocket `ws://ops.koreainvestment.com:21000`
- 모드는 사용자가 프론트엔드에서 전환한다. 실전 전환 조건(서버 실전 스위치, 실전 자격 증명 검증, 비밀번호 재입력, 경고 확인)은 백엔드가 검사한다.
- 서버 실전 스위치 `REAL_TRADING_ENABLED`는 기본 `false`이고 EC2에서만 켠다. 켜려면 마스터키가 KMS여야 하며, 아니면 서버가 시작되지 않는다.
- KIS 자격 증명 원문은 API 응답, 로그, 예외 메시지, 알림에 남기지 않는다.
- 실전도 사람의 승인 없이 자동 주문한다. 금액 상한은 두지 않는다. 대신 주문 직전 이상 감지에 걸리면 그 회차 주문을 보내지 않고 자동 주문을 정지한 뒤 알리며, 사용자별 긴급 중지 버튼을 둔다.
- 접근 토큰은 사용자·모드별로 캐시해서 재사용하고 요청마다 새로 발급하지 않는다. 토큰 유효기간은 1일이고, 재발급은 1분에 1회로 제한되며, 발급할 때마다 알림톡이 발송된다.
- 호출 간격을 조절하고, 초당 호출 초과 오류(`EGW00201`)가 나면 재시도한다. 모의투자는 호출 제한이 더 낮다.
- 자동 테스트는 KIS를 실제로 호출하지 않는다.
- 상세(모드 전환, 자격 증명 저장, 안전장치, 알림)는 `docs/trading.md`.

# 협업 규칙

- 팀 프로젝트다. 이 파일은 git으로 공유하며, 개인 설정은 `CLAUDE.local.md`(gitignore 대상)에 둔다.
- 코드 주석, 문서, 커밋 메시지는 한국어로 작성한다.
- 팀 개발 환경은 macOS와 Windows가 섞여 있다. 스크립트, 명령어, 파일 경로는 두 OS에서 모두 동작해야 한다.
