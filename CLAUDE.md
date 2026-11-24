# 프로젝트 개요

사용자의 자연어 입력으로 투자 전략을 완성하고, 그 전략에 따라 국내 ETF 포트폴리오를 리밸런싱하는 시스템입니다.
운영 범위는 **백테스트 + 모의투자 + 실전투자**입니다.
여러 사용자가 각자 자기 KIS 계좌를 등록해 쓰는 실제 서비스로 배포할 수 있게 만드는 것이 목표입니다. 개발·시연은 팀원 계정과 팀원 본인 계좌로 합니다.
설계 문서는 `docs/`에 있습니다. 어느 주제를 어느 문서에서 보는지는 아래 "문서 관리"의 표를 따릅니다.

# 기술 스택

- 백엔드: Python 3.13 + FastAPI
- 패키지 관리: uv (Python 버전과 의존성은 uv로 관리하며 `uv.lock`을 커밋합니다)
  - 패키지 추가·제거는 `uv add` / `uv remove`로만 합니다. `pip install`은 쓰지 않습니다.
- 백엔드 품질 도구: pytest(테스트), ruff(린트·포맷), pyright(타입 체크)
- 프론트엔드: React + Vite + TypeScript, 패키지 매니저는 npm
  - Node.js 26을 씁니다. `frontend/package.json`의 `engines`와 `frontend/.npmrc`의 `engine-strict=true`로 버전을 고정합니다.
- 프론트엔드 품질 도구: Vitest(테스트), Oxlint(린트), Prettier(포맷)
- 증권사 API: 한국투자증권 KIS Open API (모의투자·실전투자)
- 외부 데이터: KRX Open API(ETF 일별 시세), yfinance(분배금), 한국은행 ECOS(CD금리, 백테스트 무위험수익률). 국면 지표의 출처는 `docs/macro.md`를 봅니다.
- LLM: Ollama로 실행하는 로컬 Qwen 계열 모델 (팀원 최저 사양 16GB 기준, 7~8B급). AWS에서는 돌리지 않습니다.
  <!-- TODO: 정확한 모델 태그(예: ollama pull <모델명>) 확정 후 기입 -->
- 데이터 저장소: PostgreSQL 18. 서비스 DB는 AWS EC2에 두고, 테스트 DB는 각자 로컬에서 띄웁니다. 코드에서는 SQLModel로 접근합니다.
- 서버: AWS EC2 한 대에 백엔드(Caddy, API 서버, 워커)와 서비스 DB를 Docker Compose로 띄웁니다. 프론트엔드는 S3 + CloudFront로 배포합니다.
- 사설망: Tailscale. EC2와 LLM PC를 잇는 데 쓰고, 팀원 PC는 관리 접근(서비스 DB, SSH)에만 참여합니다.
- CI/CD: GitHub Actions. 백엔드 이미지는 GHCR에 올립니다.
- 비밀값 암호화: KIS 자격 증명의 암호화 마스터키는 AWS KMS에 둡니다(팀원 PC는 로컬 키).

# 실행 환경

구성, HTTPS, CloudFront·Tailscale 설정, LLM 연결, 배포, 시연 체크리스트는 `docs/infra.md`, 프로세스 구성과 작업 실행 방식은 `docs/architecture.md`, 인증은 `docs/auth.md`를 봅니다.
아래는 어기면 사고가 나는 규칙만 적습니다.

- DB 포트(`15432`), SSH, Ollama 포트(`11434`)는 인터넷에 열지 않습니다. Tailscale 사설망으로만 접근합니다.
- 예약 작업(시세 수집, 리밸런싱 계산, 주문 등)과 백테스트 대기열은 워커 프로세스에서만 실행하고, 워커는 EC2에서 하나만 띄웁니다. API 서버에는 스케줄러나 백그라운드 작업을 넣지 않습니다. 팀원 PC의 API 서버도 서비스 DB에 붙으므로, 그러면 수집·주문이 여러 곳에서 중복 실행됩니다.
- CD 워크플로를 고칠 때 배포 금지 시간대 검사(`docs/infra.md` 배포)를 없애지 않습니다.
- LLM 호출 주소는 `.env`의 `OLLAMA_BASE_URL` 하나로 정합니다. 코드에 주소를 하드코딩하지 않습니다.
- Ollama를 `OLLAMA_HOST=0.0.0.0`으로 띄우지 않습니다. Ollama API에는 인증이 없어 같은 LAN에 노출됩니다.
- LLM 호출에는 타임아웃을 두고, 연결할 수 없으면 원인이 드러나는 오류를 돌려줍니다. LLM을 쓰는 기능(전략 변환, 국면 판단의 LLM 지표) 외에는 LLM이 꺼져 있어도 동작해야 합니다.

# 프로젝트 구조

- 모노레포입니다. `backend/`(FastAPI, uv 프로젝트)와 `frontend/`(React + Vite)를 한 저장소에 둡니다.
  - 루트: `compose.yaml`(팀원 PC용 테스트 DB), `.env.example`
  - `docs/`: 설계 문서
  - `llm_json/`: JSON 상태 파일과 LLM 출력 형식의 예시(`docs/json-files.md`)
  - `deploy/compose.yaml`: EC2 운영용 Compose (Caddy, API 서버, 워커, 서비스 DB)
  - `.github/workflows/`: CI/CD 워크플로
- 백엔드 코드는 `backend/app/` 아래에 기능(도메인)별 폴더로 나눕니다.
  - `core/`: 설정, DB 연결, LLM(Ollama) 클라이언트
  - `auth/`: 사용자, 세션, 로그인
  - `worker/`: 워커 진입점. 예약 작업 시각표와 백테스트 대기열 처리만 두고, 실제 로직은 각 도메인의 `service.py`를 부릅니다. 도메인 폴더가 아니므로 아래 `router.py`/`models.py`/`service.py` 구성의 예외입니다.
  - `strategy/`: 자연어 → 전략 변환, 전략 스키마
  - `portfolio/`: 포트폴리오, 리밸런싱
  - `backtest/`: 백테스트
  - `trading/`: KIS 모의·실전투자 주문, KIS 자격 증명
  - `market_data/`: 시세·분배금·국면 지표 수집
  - `news/`: 국면 지표용 뉴스 수집
  - `macro/`: 거시판단. 축 점수, 국면 판단·전환, LLM 지표(뉴스 분위기, 금통위 결정문 판정) 채점
  - 수집 코드(`market_data/`, `news/`)도 백엔드의 DB 모델과 설정을 그대로 씁니다.
- 각 기능 폴더는 `router.py`(API), `models.py`(DB 모델), `service.py`(로직)로 구성합니다. `api/`, `services/` 같은 계층별 폴더는 만들지 않습니다.
- 마이그레이션은 `backend/alembic/`, 테스트는 `backend/tests/`에 둡니다.

# 데이터베이스와 설정

DB 구성과 각 규칙의 이유는 `docs/infra.md` DB를 봅니다.

- DB 접속 정보, KRX Open API 인증키 등 서버 비밀값은 `.env`에 두고 pydantic-settings로 읽습니다. `.env`는 커밋하지 않고, 필요한 키 목록은 값을 비운 `.env.example`로 커밋합니다.
- KIS 앱키·시크릿·계좌번호는 사용자의 것이므로 `.env`에 두지 않습니다. 사용자별로 등록받아 DB에 암호화해 저장합니다.
- 테이블 구조 변경은 SQLModel 모델을 수정한 뒤 Alembic 마이그레이션을 생성하는 방식으로만 합니다. 마이그레이션 파일은 커밋하고, DB에서 테이블을 직접 수정하지 않습니다.
- 새 기능 폴더에 `models.py`를 만들면 `backend/alembic/env.py`에서 import해야 합니다. import하지 않으면 Alembic autogenerate가 그 테이블을 인식하지 못합니다.
- 서비스 DB는 AWS EC2에서 Docker로 실행합니다. 팀원 PC에서는 테스트 DB만 루트의 `compose.yaml`로 실행합니다. 로컬 개발 DB는 두지 않습니다. PostgreSQL을 직접 설치하지 않습니다.
  - 팀원 PC의 개발 서버는 `.env`의 `POSTGRES_HOST`에 EC2의 Tailscale 주소를 넣어 서비스 DB에 붙습니다. 서비스 DB에는 실제 사용자 데이터가 있습니다.
- 서비스 DB에는 main에 머지된 마이그레이션만 적용하고, 적용은 CD가 배포할 때 합니다.
  - 머지 전 스키마 변경은 개발 서버를 테스트 DB(`POSTGRES_HOST=localhost`, `POSTGRES_PORT=15433`)에 붙여 확인합니다.
- 자동 테스트는 Compose에 정의된 테스트 전용 PostgreSQL 서비스(각자 로컬)에서 돌립니다. 서비스 DB에서는 테스트를 돌리지 않습니다.
- `backend/tests/conftest.py`는 앱이 설정을 읽기 전에 `POSTGRES_HOST`를 `localhost`로, `POSTGRES_PORT`를 테스트 DB 포트(15433)로 덮어씁니다. 이 동작을 없애거나 우회하지 않습니다.
- DB 비밀번호는 `.env`의 `POSTGRES_PASSWORD` 한 곳에만 씁니다. 접속 주소는 `backend/app/core/config.py`가 `POSTGRES_*` 값으로 만듭니다. `.env`에 `DATABASE_URL`을 따로 두지 않습니다.
- 포트는 서비스 DB `15432`, 테스트 DB `15433`입니다. 직접 설치한 PostgreSQL의 기본 포트 5432와 충돌하지 않게 하려는 것입니다.

# 명령어

처음 설정: 루트의 `.env.example`을 복사해 `.env`를 만들고 값을 채웁니다.

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
- 시세·분배금·국면 지표 수집: `uv run python -m app.market_data` (서비스 DB에는 담당 팀원만 실행. `docs/market-data.md`)

EC2 서버 (저장소 루트에서. 처음 설정과 현재 단계는 `docs/infra.md`의 "개발 서버 구축")
- 서비스 DB 실행: `docker compose -f deploy/compose.yaml up -d`

프론트엔드 (`frontend/`에서)
- 의존성 설치: `npm install`
- 개발 서버: `npm run dev`
- 전체 테스트: `npx vitest run`
- 테스트 파일 하나: `npx vitest run <경로>`
- 린트: `npm run lint` / 포맷: `npx prettier --write .`
- 타입 체크: `npx tsc -b`

# 문서 관리

- 한 내용은 한 문서(기준 문서)에만 씁니다. 다른 문서에서는 다시 설명하지 않고 링크만 겁니다.
- 주제별 기준 문서는 아래 표를 따릅니다. 새 주제가 생기면 표에 먼저 추가합니다.
- CLAUDE.md에는 도메인 로직(알고리즘, 계산 규칙, 수치, 출처별 처리)을 쓰지 않고, 어느 문서를 봐야 하는지만 씁니다.
- 예외: 어기면 사고(데이터 오염, 비밀값 유출, 중복 주문, 호출 한도 소진, 미래 정보 누설)가 나는 규칙은 한 줄로 둡니다. 전체에 적용되면 CLAUDE.md에, 한 도메인에만 적용되면 `.claude/rules/<도메인>.md`에 둡니다. 이유와 상세는 기준 문서에 씁니다.
- `.claude/rules/<도메인>.md`에는 `paths`, 기준 문서 안내, 그 도메인의 사고 방지 규칙만 둡니다. 로직을 요약하지 않습니다.
- 설계가 바뀌면 기준 문서만 고칩니다. 사고 방지 규칙이 바뀌면 그 규칙이 있는 곳과 기준 문서를 함께 고칩니다.
- `docs/json-flow.md`에는 흐름과 예시만 두고, 규칙과 개념은 기준 문서로 링크합니다. `docs/json-files.md`에는 필드의 뜻만 두고, 규칙과 수치는 기준 문서로 링크합니다.
- 코드를 고치기 전에 그 주제의 기준 문서를 읽습니다.
- 정하지 않았거나 잠정인 내용은 기준 문서의 "미정"(잠정값은 그 문서 본문의 해당 위치)에만 씁니다. 다른 문서와 `llm_json/` 예시에는 쓰지 않습니다. JSON 예시의 미정 값은 `null`로 둡니다.
- 이전 설계와 달라진 점을 적는 "변경" 메모는 쓰지 않습니다. 바뀐 이력은 git에 남깁니다.
- `llm_json/` 예시 값이 기준 문서와 다르면 기준 문서가 맞습니다. 기준 문서를 고치면 예시도 맞춥니다.
- 새 기준 문서를 만들면 아래 표와 `docs/index.md`의 문서 목록에 함께 추가합니다.
- 주제에 도메인 코드 폴더가 생기면 `.claude/rules/<도메인>.md`를 만들고 표의 "규칙 파일" 칸을 채웁니다.
- 미정 항목에 GitHub 이슈가 있으면 번호(`#n`)를 적습니다. 결정되면 기준 문서 본문에 반영하고 미정에서 지운 뒤 이슈를 닫습니다.

| 주제 | 기준 문서 | 규칙 파일 |
|---|---|---|
| 프로세스 구성, 워커, 요청 처리 방식 | `docs/architecture.md` | `worker.md` |
| 서버, HTTPS, Tailscale, LLM 연결, DB 운영, 배포 | `docs/infra.md` | — |
| 로그인, 세션, 소유 관계 | `docs/auth.md` | `auth.md` |
| 전략 구성·제약, 포트폴리오 생성(minimax·HRP), 자연어 → 전략, 확정·버전 | `docs/strategy-schema.md` | `strategy.md` |
| 투자 대상: 선정 조건, 슬롯 분류 | `docs/universe.md` | — |
| 리밸런싱 실행: 시점, 종류, 목표 금액, 주문 수량 | `docs/rebalancing.md` | `rebalancing.md` |
| 거시판단: 국면 지표와 출처(뉴스 포함), 국면 판단, 국면 전환 | `docs/macro.md` | `macro.md` |
| 백테스트: 가정, 비용, 세금, 지표, LLM 지표와 미래 정보 | `docs/backtest.md` | `backtest.md` |
| 시세·분배금·국면 지표 수집 | `docs/market-data.md` | `market-data.md` |
| 모의·실전투자, KIS | `docs/trading.md` | `trading.md` |
| 화면: 화면별 기능과 보여 줄 내용 | `docs/frontend.md` | `frontend.md` |
| 전체 흐름 예시 | `docs/json-flow.md` | — |
| JSON 상태 파일, LLM 출력 형식 | `docs/json-files.md` | — |

## 공통 사고 방지 규칙

- 종목코드는 코드 전체에서 항상 6자리 문자열로 다룹니다. 최근 상장 종목은 영문 대문자가 섞이므로(예: `"0184E0"`) 숫자로 변환하거나 숫자만 허용하지 않습니다. YAML에서는 반드시 따옴표로 감쌉니다(`"012450"`). 따옴표가 없으면 PyYAML이 `012450`을 8진수 `5416`으로 읽습니다.
- 계산, 투자 대상 선정, 국면 판단에는 그 시점까지 공개된 데이터만 씁니다. 백테스트에서 미래 정보가 섞이면 결과가 부풀려집니다.
- 투자 대상 선정 조건, 슬롯 분류 규칙(보정표 포함), 분배금 보정, 휴장일은 `backend/config/`의 YAML로만 관리합니다. DB에만 두거나 DB를 직접 고치지 않습니다.
- KIS 자격 증명 원문은 API 응답, 로그, 예외 메시지, 알림에 남기지 않습니다.
- 서버 실전 스위치 `REAL_TRADING_ENABLED`는 기본 `false`이고 EC2에서만 켭니다. 켜려면 마스터키가 KMS여야 하며, 아니면 서버가 시작되지 않습니다.
- 자동 테스트는 외부 API(KIS, KRX, yfinance, ECOS, 공공데이터포털)를 실제로 호출하지 않습니다.

# 협업 규칙

- 팀 프로젝트입니다. 이 파일은 git으로 공유하며, 개인 설정은 `CLAUDE.local.md`(gitignore 대상)에 둡니다.
- 코드 주석, 문서, 커밋 메시지는 한국어로 작성합니다.
  - md 문서의 문장은 "~합니다/~입니다" 말투로 씁니다. "~한다"나 "~함/~임" 같은 개조식은 쓰지 않습니다. 표 안의 짧은 명사구는 예외입니다.
- 팀 개발 환경은 macOS와 Windows가 섞여 있습니다. 스크립트, 명령어, 파일 경로는 두 OS에서 모두 동작해야 합니다.
