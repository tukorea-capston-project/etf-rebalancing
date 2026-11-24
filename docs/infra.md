# 인프라·실행 환경

서비스를 어디서 실행하고, 어떻게 연결하고 배포하는지 정의합니다. 실제 서비스로 배포할 수 있는 구성을 목표로 합니다.
이 주제의 기준 문서입니다. CLAUDE.md에는 이 중 어기면 사고가 나는 규칙만 한 줄씩 있고, 상세와 이유는 이 문서에 둡니다. 프로세스 구성과 작업 실행 방식은 `docs/architecture.md`를 봅니다.
팀원 PC의 개발 환경은 끝의 "개발 환경" 섹션에 따로 둡니다.

## 구성

```
[사용자 브라우저]
     │  HTTPS (서비스 도메인)
     ▼
[CloudFront (CDN)] ──── 정적 파일 ────► [S3] 프론트엔드 빌드 결과
     │  /api/* · HTTPS (오리진용 하위 도메인)
     ▼
[AWS EC2]  Docker Compose: Caddy + API 서버 + 워커 + PostgreSQL 18(서비스 DB)
     │
     │  Tailscale 사설망
     ▼
[LLM PC]   Ollama :11434   ← EC2 백엔드가 호출하는 유일한 LLM

[GitHub Actions]  CI: PR마다 검사 · CD: 백엔드 이미지(GHCR) → EC2, 프론트엔드 → S3
```

- 사용자는 서비스 도메인(CloudFront)으로만 접속합니다. EC2에 직접 접속하지 않습니다.
- AWS에서는 LLM을 돌리지 않습니다. GPU 인스턴스 비용을 피하고, 팀원 PC 중 성능이 좋은 한 대를 LLM PC로 씁니다. Tailscale은 이 LLM PC를 EC2에 사설망으로 잇기 위해 씁니다.
- DB, SSH, Ollama 포트는 인터넷에 열지 않습니다. Tailscale 사설망 안에서만 접근합니다.

## 공개 범위와 HTTPS

- 서비스(프론트엔드와 API)는 **인터넷에 공개합니다.**
- 도메인을 하나 사서 씁니다. 구매처는 미정입니다(아래 "미정").
- 구간마다 HTTPS를 씁니다.

| 구간 | 인증서 | 비고 |
|---|---|---|
| 브라우저 → CloudFront | ACM 인증서(무료), 서비스 도메인 | CloudFront용 인증서는 `us-east-1` 리전에서 발급해야 합니다 |
| CloudFront → EC2 | Let's Encrypt 인증서, 오리진용 하위 도메인(예: `origin.<도메인>`) | EC2의 Caddy가 발급·갱신합니다 |

- CloudFront → EC2 구간을 HTTP로 두지 않습니다. 로그인 비밀번호와 KIS 앱키가 이 구간을 평문으로 지나가게 됩니다.
- 오리진용 하위 도메인은 EC2를 가리키지만, 보안그룹이 CloudFront 요청만 받으므로 사용자가 이 주소로 직접 접속할 수 없습니다.

### CloudFront 경로별 전달

| 경로 | 보내는 곳 | 캐시 |
|---|---|---|
| `/api/*` | EC2 (Caddy → API 서버) | 하지 않습니다. 쿠키·쿼리·헤더를 그대로 전달합니다 |
| 그 밖 | S3 (프론트엔드 빌드 결과) | 합니다 |

- 브라우저 입장에서는 정적 파일과 API가 모두 서비스 도메인 하나에서 옵니다. 그래서 프론트엔드와 API가 **같은 오리진**이고 CORS 설정이나 크로스 도메인 쿠키가 필요 없습니다(`docs/auth.md`).
- `/api/*`는 `Host` 헤더를 EC2로 넘기지 않습니다(오리진 요청 정책 `AllViewerExceptHostHeader`). `Host`를 넘기면 CloudFront가 서비스 도메인으로 EC2 인증서를 검증하려 해서 연결이 실패합니다.
- CloudFront의 오리진 응답 타임아웃은 기본 30초(최대 60초)입니다. 전략 변환은 LLM을 동기로 호출하므로, LLM 호출 타임아웃은 이 값보다 짧아야 합니다.
- 웹 푸시 등 HTTPS에서만 동작하는 브라우저 기능도 쓸 수 있습니다.

## AWS

### EC2

- EC2 한 대에서 Docker Compose(`deploy/compose.yaml`)로 Caddy, API 서버, 워커, 서비스 DB를 한 번에 띄웁니다. 이미지는 CD가 GHCR에 올린 것을 받습니다.
- 워커(예약 작업, 백테스트 대기열)는 EC2에서만 하나 실행합니다. 팀원 PC에서는 서비스 DB에 붙은 워커를 실행하지 않습니다(`docs/architecture.md`).
- 보안그룹 인바운드
  - `443`: CloudFront에서 오는 요청만 허용합니다(AWS 관리형 접두사 목록 `com.amazonaws.global.cloudfront.origin-facing`).
  - `15432`(DB), `22`(SSH): 열지 않습니다. 팀원은 Tailscale로 접속합니다. Tailscale은 인바운드 포트를 열지 않아도 연결됩니다.
- 실전 주문은 EC2 백엔드에서만 냅니다. `REAL_TRADING_ENABLED=true`는 EC2의 `.env`에만 둡니다.
- EC2에는 IAM 역할(인스턴스 프로파일)을 붙입니다. KMS(아래)와 SSM(배포 명령 실행) 권한을 이 역할로 받습니다. 액세스 키를 `.env`에 두지 않습니다.

### S3 + CloudFront

- S3 버킷은 공개하지 않습니다. CloudFront만 읽을 수 있게 합니다(OAC, Origin Access Control).
- 프론트엔드는 CD가 빌드해 S3에 올리고, CloudFront 캐시를 무효화합니다.

### KIS 자격 증명 암호화

사용자 KIS 자격 증명은 DB에 암호화해 저장합니다. 상세는 `docs/trading.md`를 봅니다.

| 실행 위치 | 마스터키 | `.env` |
|---|---|---|
| AWS EC2 | AWS KMS | `CREDENTIAL_KEY_PROVIDER=kms`, `KMS_KEY_ID` |
| 팀원 PC | 로컬 키 | `CREDENTIAL_KEY_PROVIDER=local`, `CREDENTIAL_LOCAL_KEY` |

- IAM 역할에는 그 KMS 키 하나에 대한 암호화·복호화·데이터 키 생성 권한만 줍니다.
- 팀원 PC에는 KMS 권한을 주지 않습니다. 그래서 서비스 DB의 자격 증명은 팀원 PC 백엔드에서 복호화되지 않습니다.

## Tailscale

- 용도는 두 가지입니다.
  - **EC2 ↔ LLM PC 연결**: EC2 백엔드가 LLM PC의 Ollama를 호출합니다. Tailscale을 쓰는 주 목적입니다.
  - **팀원 관리 접근**: 팀원 PC가 서비스 DB와 EC2 SSH에 접속합니다.
- 사용자의 서비스 접속에는 쓰지 않습니다. 사용자는 인터넷으로 CloudFront에 접속합니다.
- 참여 기기: EC2, LLM PC, 개발 팀원 PC.
- 무료 Personal 플랜은 사용자 6명까지, 사용자 기기 수는 무제한입니다. 플랜 조건은 바뀔 수 있으므로 가입할 때 공식 가격 페이지에서 확인합니다.
- 기본 접근 정책은 "모든 기기 간 모두 허용"입니다. Ollama에는 인증이 없으므로 기본 정책을 그대로 쓰지 않고 아래처럼 좁힙니다.
  - LLM PC의 `11434`: EC2만 접근 허용
  - EC2의 `15432`(DB): 팀원 PC만 접근 허용 (EC2 백엔드는 같은 서버 안에서 접속)
  - EC2의 SSH: 팀원 PC만 접근 허용
- 정책 파일의 구체적 내용은 Tailscale 관리 콘솔에서 설정할 때 확정하고, 확정하면 이 문서에 옮겨 적습니다.

## LLM

### 호출 주소

LLM 호출 주소는 `.env`의 `OLLAMA_BASE_URL` 하나로 정합니다. 코드는 주소를 몰라도 됩니다.

| 실행 위치 | `OLLAMA_BASE_URL` | 비고 |
|---|---|---|
| 팀원 PC(개발) | `http://localhost:11434` | 자기 PC의 Ollama. LLM PC가 없어도 개발할 수 있습니다 |
| EC2 백엔드 | `http://<LLM PC의 Tailscale 주소>:11434` | LLM PC 한 대만 호출합니다 |

- EC2 백엔드는 LLM PC가 꺼져 있어도 다른 PC로 대체하지 않습니다. 대체 목록을 두면 요청이 팀원이 작업 중인 PC로 가서 자원을 쓰고, 어느 PC가 응답했는지에 따라 결과가 달라집니다.
- LLM PC가 꺼져 있으면 EC2 백엔드의 전략 변환은 실패합니다. LLM 호출에는 타임아웃을 두고 "LLM 서버에 연결할 수 없음"을 명확히 돌려줍니다. 국면 판단의 LLM 지표(뉴스 분위기 점수, 금통위 결정문 판정)도 받을 수 없으며, 이때의 처리는 `docs/macro.md`를 따릅니다. 백테스트·리밸런싱·시세 수집 등 나머지 기능은 LLM 없이도 동작해야 합니다.

### 모델

- 개발 PC와 LLM PC는 같은 모델 태그를 씁니다. 모델이 다르면 같은 입력에도 스키마 검증 결과가 달라집니다.
- 모델 태그는 CLAUDE.md 기술 스택에 적습니다.

### LLM PC 설정

1. Tailscale에 로그인하고 이 PC의 Tailscale 주소(`100.x.y.z`)를 확인합니다.
2. Ollama를 그 주소에만 바인딩합니다. `OLLAMA_HOST`를 설정하고 Ollama를 재시작합니다.
   - macOS(앱): `launchctl setenv OLLAMA_HOST "100.x.y.z:11434"`
   - Windows: 시스템 환경 변수에 `OLLAMA_HOST=100.x.y.z:11434` 추가
   - `0.0.0.0`은 쓰지 않습니다. 같은 와이파이의 다른 기기에도 인증 없이 노출됩니다.
3. 정해진 모델을 받습니다: `ollama pull <모델 태그>`

- Tailscale 주소는 기기마다 고정이라 한 번 정하면 바뀌지 않습니다. 단, Tailscale이 연결되지 않은 상태에서 Ollama가 먼저 시작되면 그 주소에 바인딩하지 못하므로, Tailscale을 먼저 켭니다.
- `tailscale serve`로 `localhost:11434`를 노출하는 방법은 쓰지 않습니다. `tailscale serve`는 원래 Host 헤더(`*.ts.net`)를 그대로 넘기는데, Ollama는 localhost가 아닌 Host 헤더를 거부해 403 오류가 날 수 있습니다.

## DB

| DB | 위치 | 포트 | 용도 |
|---|---|---|---|
| 서비스 DB | AWS EC2(Docker) | `15432` | 서비스, 팀원 PC의 개발 서버 |
| 테스트 DB | 팀원 PC(Compose `db-test`) | `15433` | 자동 테스트, 머지 전 스키마 변경 확인 |

- 로컬 개발 DB는 두지 않습니다. 평소 개발도 서비스 DB로 합니다. 팀원 PC의 개발 서버는 `.env`의 `POSTGRES_HOST`에 EC2의 Tailscale 주소를 넣어 서비스 DB에 붙습니다.
  - 서비스 DB에는 실제 사용자 데이터가 있습니다. 작업 중인 코드가 잘못된 데이터를 쓰면 서비스 데이터가 오염될 수 있습니다. 실제 사용자가 생기면 개발용 DB를 따로 둬야 합니다.
- 서비스 DB에는 main에 머지된 마이그레이션만 적용합니다. 적용은 CD가 배포할 때 합니다. 서비스 DB를 머지 전 스키마로 바꾸면 배포된 서버와 다른 팀원의 개발 서버가 깨집니다.
- 머지 전 스키마 변경은 개발 서버를 테스트 DB에 붙여 확인합니다(`.env`의 `POSTGRES_HOST=localhost`, `POSTGRES_PORT=15433`).
  - 테스트 DB는 tmpfs라 컨테이너를 내리면 데이터가 사라집니다. 시세 등 필요한 데이터는 그때마다 넣습니다.
  - 마이그레이션이 빈 DB에 끝까지 적용되는지는 CI가 검사합니다(아래 "배포").
- 테스트는 `.env` 값과 무관하게 항상 로컬 테스트 DB에서 돕니다. `backend/tests/conftest.py`가 `POSTGRES_HOST`와 `POSTGRES_PORT`를 덮어씁니다.
- 서비스 DB 시세 수집은 한 곳에서만 합니다. 상세는 `docs/market-data.md`를 봅니다.

## 배포 (GitHub Actions)

워크플로는 `.github/workflows/`에 둡니다. 저장소가 공개라 Actions와 GHCR을 무료로 씁니다.

### CI

PR마다, 그리고 main에 머지될 때 실행합니다. 통과해야 머지할 수 있게 브랜치 보호 규칙을 겁니다.

| 대상 | 검사 |
|---|---|
| 백엔드 | `ruff check`, `ruff format --check`, `pyright`, `pytest`, 빈 DB에 `alembic upgrade head` |
| 프론트엔드 | `npm run lint`, `prettier --check`, `tsc -b`, `vitest run` |

- 백엔드 테스트는 PostgreSQL 18 서비스 컨테이너를 `15433` 포트로 띄워 돌립니다. 로컬과 같은 포트라 `conftest.py`를 그대로 씁니다.

### CD

- 사람의 승인 없이 자동으로 배포합니다.
- 실행 시점
  - main에 머지될 때
  - 예약 실행: 평일 17:05 KST
  - 수동 실행(`workflow_dispatch`)
- **배포 금지 시간대: 평일 07:30–17:00 KST.** 첫 단계에서 현재 시각을 확인하고, 이 시간대면 배포하지 않고 끝냅니다. 수동 실행도 같습니다.
  - 워커가 수집·계산·주문하는 도중에 재시작되면 작업이 중간에 끊깁니다. 아침 수집(08:00부터, 재시도 14:00 마감)과 국면 판단, 주문(14:30~15:15), 리밸런싱 계산(16:00)이 모두 이 시간대에 들어갑니다(`docs/architecture.md` 예약 작업).
  - 금지 시간대에 머지된 변경은 그날 예약 실행에서 배포됩니다.
  - 예약 실행을 금지 시간대가 끝난 직후인 17:05로 두는 이유는 18:00 저녁 수집과 거리를 두기 위해서입니다. GitHub의 예약 실행은 UTC 기준이고(평일 17:05 KST = 월–금 08:05 UTC) 늦게 시작될 수 있습니다.
  - 매시 정각의 뉴스 수집은 배포로 한 번 끊겨도 다음 실행에서 이어서 받습니다.
- 순서
  1. 백엔드 이미지를 빌드해 GHCR에 올립니다.
  2. EC2에서 새 이미지를 받고, 서비스 DB에 마이그레이션(`alembic upgrade head`)을 적용한 뒤 `docker compose up -d`로 다시 띄웁니다.
  3. 프론트엔드를 빌드해 S3에 올리고 CloudFront 캐시를 무효화합니다. 백엔드보다 나중에 올려, 새 화면이 아직 없는 API를 부르지 않게 합니다.
- AWS 인증은 GitHub OIDC로 IAM 역할을 받아 씁니다. AWS 액세스 키를 GitHub Secrets에 두지 않습니다.
- EC2 명령은 SSM Run Command로 실행합니다. SSH 키를 GitHub에 두지 않고 `22` 포트도 열지 않습니다.

## 개발 환경

- 팀원 PC 구성
  - 백엔드: 자기 PC에서 API 서버(`uv run fastapi dev`)를 띄웁니다. DB는 서비스 DB(Tailscale), LLM은 자기 PC의 Ollama를 씁니다.
  - 테스트 DB: 루트 `compose.yaml`의 `db-test`(`docker compose up -d db-test`).
  - 마스터키는 로컬 키(`CREDENTIAL_KEY_PROVIDER=local`)를 씁니다. 서비스 DB의 KIS 자격 증명은 복호화되지 않습니다.
- 워커는 팀원 PC에서 서비스 DB를 대상으로 실행하지 않습니다.
- 팀원 PC의 `.env`에서는 `REAL_TRADING_ENABLED`를 항상 `false`로 둡니다.

## 개발 서버 구축 (현재 단계)

위 구성을 한 번에 만들지 않고, 같은 EC2에 단계별로 덧붙여 최종 구성으로 키웁니다.

### 현재 단계

```
[팀원 PC] 백엔드 + 자기 Ollama + 테스트 DB ── Tailscale ──► [EC2] 서비스 DB (deploy/compose.yaml)
```

- EC2에는 서비스 DB만 띄웁니다. 백엔드는 각 팀원 PC에서 띄우고(위 "개발 환경"), EC2의 서비스 DB를 공용 데이터로 씁니다.
- 외부에 공개하지 않습니다. 보안그룹 인바운드는 하나도 열지 않고, 팀원은 Tailscale로 서비스 DB(`<EC2의 Tailscale 주소>:15432`)에 접속합니다.
- EC2에서 LLM을 부르는 프로세스가 없으므로 LLM PC는 아직 필요 없습니다.
- CD가 없으므로 서비스 DB 마이그레이션은 팀원이 적용합니다(아래 "마이그레이션").

| 다음에 붙일 것 | 붙이는 시점 |
|---|---|
| 워커(백엔드 이미지, LLM PC 연결) | `backend/app/worker/` 코드가 생겨 예약 작업을 EC2에서 돌릴 때 |
| Caddy, API 서버, 도메인, CloudFront, S3 | 외부에 공개할 때 |
| GitHub Actions CD | 백엔드 이미지를 EC2에 올리기 시작할 때 |
| KMS | 실전 투자를 켤 때 |

### EC2 만들기 (AWS 콘솔)

1. AWS Budgets로 예산 알림을 먼저 설정합니다(예: 월 $20 초과 시 이메일).
2. EC2를 만듭니다.
   - 리전: 서울(`ap-northeast-2`), AMI: Ubuntu 24.04, 디스크: gp3 30GB
   - 유형: DB만 띄우는 지금은 `t3.micro`로 충분합니다. 워커를 붙일 때 인스턴스를 중지하고 유형만 바꿉니다(`t3.small` 이상).
   - 보안그룹 인바운드: 없음
   - IAM 역할: `AmazonSSMManagedInstanceCore` 정책을 붙인 역할. 콘솔의 Session Manager로 접속합니다(22 포트를 열지 않음).
   - 종료 보호를 켜고, 루트 볼륨의 "종료 시 삭제"를 끕니다.
3. 백업: Data Lifecycle Manager로 루트 볼륨 EBS 스냅샷을 하루 1회 찍습니다.

- 쓰지 않는 기간에는 인스턴스를 **중지(stop)** 하면 디스크 요금만 나갑니다. 데이터와 Tailscale 주소는 그대로 남습니다. **종료(terminate)** 는 인스턴스를 지우는 것이므로 쓰지 않습니다.

### EC2 안에서 처음 설정

Session Manager로 접속해 실행합니다.

```bash
# swap 1GB (메모리가 작은 인스턴스에서 DB가 메모리 부족으로 죽지 않게)
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Docker, Tailscale
curl -fsSL https://get.docker.com | sudo sh
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up   # 출력되는 링크로 로그인합니다. 주소 확인: tailscale ip -4

# 저장소와 .env
git clone https://github.com/tukorea-capston-project/etf-rebalancing.git && cd etf-rebalancing
cp .env.example .env   # POSTGRES_PASSWORD를 채웁니다 (팀원 PC의 .env와 같은 값)

# 서비스 DB 실행
sudo docker compose -f deploy/compose.yaml up -d
```

- `.env`는 저장소 루트에 하나 둡니다. 서비스 DB는 이 중 `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`만 씁니다.
- DB 데이터는 Docker 볼륨(`db-data`)에 있습니다. `docker compose down -v`는 볼륨까지 지우므로 쓰지 않습니다.

### 팀원 PC를 사설망에 연결

EC2와 팀원 PC를 직접 잇는 것이 아니라, 각 기기가 같은 Tailscale 사설망(tailnet)에 들어갑니다. 같은 tailnet에 들어가면 EC2의 Tailscale 주소로 서비스 DB에 접속할 수 있습니다.

1. Tailscale을 설치하고 EC2와 같은 tailnet(팀 계정)으로 로그인합니다.
2. `.env`의 `POSTGRES_HOST`에 EC2의 Tailscale 주소를 넣습니다(`POSTGRES_PORT`는 기본값 `15432`).
3. 백엔드를 띄워 서비스 DB에 붙는지 확인합니다(`uv run fastapi dev app/main.py`).

- 기기가 모두 연결되면 Tailscale 접근 정책을 좁힙니다(위 "Tailscale"). 현재 단계에서는 팀원 PC → EC2의 `15432`만 있으면 됩니다.

### 마이그레이션

- 서비스 DB에는 main에 머지된 마이그레이션만 적용합니다. CD가 생기기 전까지는 마이그레이션이 머지되면, 그 PR을 올린 팀원이 최신 main에서 서비스 DB에 적용합니다.

```bash
# backend/에서. .env의 POSTGRES_HOST가 EC2의 Tailscale 주소인 상태로
git switch main && git pull
uv run alembic upgrade head
```

- 머지 전 마이그레이션은 서비스 DB가 아니라 테스트 DB에서 확인합니다(위 "DB").

## 시연 체크리스트

- [ ] 시연 장소 네트워크에서 LLM PC의 Tailscale 연결 확인 (미리 방문해 LLM PC를 연결하고 `tailscale status`로 EC2가 보이는지, 아래 `curl` 확인까지 해 봅니다. 방화벽이 엄격한 망이면 중계 서버 경유로 느려지거나 막힐 수 있습니다)
- [ ] LLM PC: 전원 연결, 절전·잠자기 해제
- [ ] LLM PC: Tailscale 연결 → Ollama 실행 순서로 켭니다
- [ ] LLM PC: 정해진 모델 태그가 받아져 있습니다 (`ollama list`)
- [ ] EC2에서 LLM PC 연결 확인: `curl http://<LLM PC의 Tailscale 주소>:11434/api/tags` 응답에 모델이 보입니다
- [ ] 시연 장소 네트워크에서 서비스 도메인 접속 확인
- [ ] 서비스 DB에 최신 시세·분배금이 수집되어 있습니다
- [ ] 시연 시간이 배포 금지 시간대 밖이면, 시연 중 main 머지·수동 배포를 하지 않습니다
- [ ] 전략 변환 한 번을 미리 실행해 모델을 메모리에 올려 둡니다 (첫 호출은 모델 로딩 때문에 느립니다)

## 미정

- 도메인 구매처 (Route 53 추천: ACM 인증서 검증과 CloudFront 연결을 AWS 안에서 끝낼 수 있습니다)
- Caddy의 Let's Encrypt 인증서 검증 방식. 보안그룹이 `443`만 CloudFront에 열면 기본 방식(HTTP·TLS 검증)이 막힙니다. DNS 검증(Caddy DNS 플러그인) 또는 `80` 포트 개방 중에서 고릅니다
- EC2 인스턴스 사양, 서비스 DB 백업 방식
- 배포 실패 시 되돌리는 방법 (이전 이미지 태그로 재배포, 마이그레이션 되돌리기)
- 프론트엔드 개발 서버(`npm run dev`)의 `/api` 전달 대상 (서비스 도메인 또는 자기 PC의 백엔드)
- Tailscale 접근 정책 파일의 구체적 내용
- KMS 키 생성과 IAM 정책(EC2 역할의 KMS·SSM 권한, GitHub OIDC 역할)의 구체적 내용
