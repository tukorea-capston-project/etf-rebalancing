# 인프라·실행 환경

서비스를 어디서 실행하고, 어떻게 연결하고 배포하는지 정의함. 실제 서비스로 배포할 수 있는 구성을 목표로 함.
핵심 규칙은 CLAUDE.md의 "실행 환경"과 "데이터베이스와 설정"에 있음. 프로세스 구성과 작업 실행 방식은 `docs/architecture.md`.
팀원 PC의 개발 환경은 끝의 "개발 환경" 섹션에 따로 둠.

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

- 사용자는 서비스 도메인(CloudFront)으로만 접속함. EC2에 직접 접속하지 않음.
- AWS에서는 LLM을 돌리지 않음. GPU 인스턴스 비용을 피하고, 팀원 PC 중 성능이 좋은 한 대를 LLM PC로 씀. Tailscale은 이 LLM PC를 EC2에 사설망으로 잇기 위해 씀.
- DB, SSH, Ollama 포트는 인터넷에 열지 않음. Tailscale 사설망 안에서만 접근함.

## 공개 범위와 HTTPS

- 서비스(프론트엔드와 API)는 **인터넷에 공개함.**
- 도메인을 하나 사서 씀. 구매처는 미정(아래 "미정").
- 구간마다 HTTPS를 씀.

| 구간 | 인증서 | 비고 |
|---|---|---|
| 브라우저 → CloudFront | ACM 인증서(무료), 서비스 도메인 | CloudFront용 인증서는 `us-east-1` 리전에서 발급해야 함 |
| CloudFront → EC2 | Let's Encrypt 인증서, 오리진용 하위 도메인(예: `origin.<도메인>`) | EC2의 Caddy가 발급·갱신함 |

- CloudFront → EC2 구간을 HTTP로 두지 않음. 로그인 비밀번호와 KIS 앱키가 이 구간을 평문으로 지나가게 됨.
- 오리진용 하위 도메인은 EC2를 가리키지만, 보안그룹이 CloudFront 요청만 받으므로 사용자가 이 주소로 직접 접속할 수 없음.

### CloudFront 경로별 전달

| 경로 | 보내는 곳 | 캐시 |
|---|---|---|
| `/api/*` | EC2 (Caddy → API 서버) | 하지 않음. 쿠키·쿼리·헤더를 그대로 전달함 |
| 그 밖 | S3 (프론트엔드 빌드 결과) | 함 |

- 브라우저 입장에서는 정적 파일과 API가 모두 서비스 도메인 하나에서 옴. 그래서 프론트엔드와 API가 **같은 오리진**이고 CORS 설정이나 크로스 도메인 쿠키가 필요 없음(`docs/auth.md`).
- `/api/*`는 `Host` 헤더를 EC2로 넘기지 않음(오리진 요청 정책 `AllViewerExceptHostHeader`). `Host`를 넘기면 CloudFront가 서비스 도메인으로 EC2 인증서를 검증하려 해서 연결이 실패함.
- CloudFront의 오리진 응답 타임아웃은 기본 30초(최대 60초)임. 전략 변환은 LLM을 동기로 호출하므로, LLM 호출 타임아웃은 이 값보다 짧아야 함.
- 웹 푸시 등 HTTPS에서만 동작하는 브라우저 기능도 쓸 수 있음.

## AWS

### EC2

- EC2 한 대에서 Docker Compose(`deploy/compose.yaml`)로 Caddy, API 서버, 워커, 서비스 DB를 한 번에 띄움. 이미지는 CD가 GHCR에 올린 것을 받음.
- 워커(예약 작업, 백테스트 대기열)는 EC2에서만 하나 실행함. 팀원 PC에서는 서비스 DB에 붙은 워커를 실행하지 않음(`docs/architecture.md`).
- 보안그룹 인바운드
  - `443`: CloudFront에서 오는 요청만 허용(AWS 관리형 접두사 목록 `com.amazonaws.global.cloudfront.origin-facing`).
  - `15432`(DB), `22`(SSH): 열지 않음. 팀원은 Tailscale로 접속함. Tailscale은 인바운드 포트를 열지 않아도 연결됨.
- 실전 주문은 EC2 백엔드에서만 냄. `REAL_TRADING_ENABLED=true`는 EC2의 `.env`에만 둠.
- EC2에는 IAM 역할(인스턴스 프로파일)을 붙임. KMS(아래)와 SSM(배포 명령 실행) 권한을 이 역할로 받음. 액세스 키를 `.env`에 두지 않음.

### S3 + CloudFront

- S3 버킷은 공개하지 않음. CloudFront만 읽을 수 있게 함(OAC, Origin Access Control).
- 프론트엔드는 CD가 빌드해 S3에 올리고, CloudFront 캐시를 무효화함.

### KIS 자격 증명 암호화

사용자 KIS 자격 증명은 DB에 암호화해 저장함. 상세는 `docs/trading.md`.

| 실행 위치 | 마스터키 | `.env` |
|---|---|---|
| AWS EC2 | AWS KMS | `CREDENTIAL_KEY_PROVIDER=kms`, `KMS_KEY_ID` |
| 팀원 PC | 로컬 키 | `CREDENTIAL_KEY_PROVIDER=local`, `CREDENTIAL_LOCAL_KEY` |

- IAM 역할에는 그 KMS 키 하나에 대한 암호화·복호화·데이터 키 생성 권한만 줌.
- 팀원 PC에는 KMS 권한을 주지 않음. 그래서 서비스 DB의 자격 증명은 팀원 PC 백엔드에서 복호화되지 않음.

## Tailscale

- 용도는 두 가지임.
  - **EC2 ↔ LLM PC 연결**: EC2 백엔드가 LLM PC의 Ollama를 호출함. Tailscale을 쓰는 주 목적임.
  - **팀원 관리 접근**: 팀원 PC가 서비스 DB와 EC2 SSH에 접속함.
- 사용자의 서비스 접속에는 쓰지 않음. 사용자는 인터넷으로 CloudFront에 접속함.
- 참여 기기: EC2, LLM PC, 개발 팀원 PC.
- 무료 Personal 플랜은 사용자 6명까지, 사용자 기기 수는 무제한임. 플랜 조건은 바뀔 수 있으므로 가입할 때 공식 가격 페이지에서 확인함.
- 기본 접근 정책은 "모든 기기 간 모두 허용"임. Ollama에는 인증이 없으므로 기본 정책을 그대로 쓰지 않고 아래처럼 좁힘.
  - LLM PC의 `11434`: EC2만 접근 허용
  - EC2의 `15432`(DB): 팀원 PC만 접근 허용 (EC2 백엔드는 같은 서버 안에서 접속)
  - EC2의 SSH: 팀원 PC만 접근 허용
- 정책 파일의 구체적 내용은 Tailscale 관리 콘솔에서 설정할 때 확정하고, 확정하면 이 문서에 옮겨 적음.

## LLM

### 호출 주소

LLM 호출 주소는 `.env`의 `OLLAMA_BASE_URL` 하나로 정함. 코드는 주소를 몰라도 됨.

| 실행 위치 | `OLLAMA_BASE_URL` | 비고 |
|---|---|---|
| 팀원 PC(개발) | `http://localhost:11434` | 자기 PC의 Ollama. LLM PC가 없어도 개발할 수 있음 |
| EC2 백엔드 | `http://<LLM PC의 Tailscale 주소>:11434` | LLM PC 한 대만 호출함 |

- EC2 백엔드는 LLM PC가 꺼져 있어도 다른 PC로 대체하지 않음. 대체 목록을 두면 요청이 팀원이 작업 중인 PC로 가서 자원을 쓰고, 어느 PC가 응답했는지에 따라 결과가 달라짐.
- LLM PC가 꺼져 있으면 EC2 백엔드의 전략 변환은 실패함. LLM 호출에는 타임아웃을 두고 "LLM 서버에 연결할 수 없음"을 명확히 돌려줌. 백테스트·리밸런싱·시세 수집 등 나머지 기능은 LLM 없이도 동작해야 함.

### 모델

- 개발 PC와 LLM PC는 같은 모델 태그를 씀. 모델이 다르면 같은 입력에도 스키마 검증 결과가 달라짐.
- 모델 태그는 CLAUDE.md 기술 스택에 확정해 적음. (미정)

### LLM PC 설정

1. Tailscale에 로그인하고 이 PC의 Tailscale 주소(`100.x.y.z`)를 확인함.
2. Ollama를 그 주소에만 바인딩함. `OLLAMA_HOST`를 설정하고 Ollama를 재시작함.
   - macOS(앱): `launchctl setenv OLLAMA_HOST "100.x.y.z:11434"`
   - Windows: 시스템 환경 변수에 `OLLAMA_HOST=100.x.y.z:11434` 추가
   - `0.0.0.0`은 쓰지 않음. 같은 와이파이의 다른 기기에도 인증 없이 노출됨.
3. 정해진 모델을 받음: `ollama pull <모델 태그>`

- Tailscale 주소는 기기마다 고정이라 한 번 정하면 바뀌지 않음. 단, Tailscale이 연결되지 않은 상태에서 Ollama가 먼저 시작되면 그 주소에 바인딩하지 못하므로, Tailscale을 먼저 켬.
- `tailscale serve`로 `localhost:11434`를 노출하는 방법은 쓰지 않음. `tailscale serve`는 원래 Host 헤더(`*.ts.net`)를 그대로 넘기는데, Ollama는 localhost가 아닌 Host 헤더를 거부해 403 오류가 날 수 있음.

## DB

| DB | 위치 | 포트 | 용도 |
|---|---|---|---|
| 서비스 DB | AWS EC2(Docker) | `15432` | 서비스, 팀원 PC의 개발 서버 |
| 테스트 DB | 팀원 PC(Compose `db-test`) | `15433` | 자동 테스트, 머지 전 스키마 변경 확인 |

- 로컬 개발 DB는 두지 않음. 평소 개발도 서비스 DB로 함. 팀원 PC의 개발 서버는 `.env`의 `POSTGRES_HOST`에 EC2의 Tailscale 주소를 넣어 서비스 DB에 붙음.
  - 서비스 DB에는 실제 사용자 데이터가 있음. 작업 중인 코드가 잘못된 데이터를 쓰면 서비스 데이터가 오염될 수 있음. 실제 사용자가 생기면 개발용 DB를 따로 둬야 함.
- 서비스 DB에는 main에 머지된 마이그레이션만 적용함. 적용은 CD가 배포할 때 함. 서비스 DB를 머지 전 스키마로 바꾸면 배포된 서버와 다른 팀원의 개발 서버가 깨짐.
- 머지 전 스키마 변경은 개발 서버를 테스트 DB에 붙여 확인함(`.env`의 `POSTGRES_HOST=localhost`, `POSTGRES_PORT=15433`).
  - 테스트 DB는 tmpfs라 컨테이너를 내리면 데이터가 사라짐. 시세 등 필요한 데이터는 그때마다 넣음.
  - 마이그레이션이 빈 DB에 끝까지 적용되는지는 CI가 검사함(아래 "배포").
- 테스트는 `.env` 값과 무관하게 항상 로컬 테스트 DB에서 돎. `backend/tests/conftest.py`가 `POSTGRES_HOST`와 `POSTGRES_PORT`를 덮어씀.
- 서비스 DB 시세 수집은 한 곳에서만 함. 상세는 `docs/market-data.md`.

## 배포 (GitHub Actions)

워크플로는 `.github/workflows/`에 둠. 저장소가 공개라 Actions와 GHCR을 무료로 씀.

### CI

PR마다, 그리고 main에 머지될 때 실행함. 통과해야 머지할 수 있게 브랜치 보호 규칙을 검.

| 대상 | 검사 |
|---|---|
| 백엔드 | `ruff check`, `ruff format --check`, `pyright`, `pytest`, 빈 DB에 `alembic upgrade head` |
| 프론트엔드 | `npm run lint`, `prettier --check`, `tsc -b`, `vitest run` |

- 백엔드 테스트는 PostgreSQL 18 서비스 컨테이너를 `15433` 포트로 띄워 돌림. 로컬과 같은 포트라 `conftest.py`를 그대로 씀.

### CD

- 사람의 승인 없이 자동으로 배포함.
- 실행 시점
  - main에 머지될 때
  - 예약 실행: 평일 17:30 KST
  - 수동 실행(`workflow_dispatch`)
- **배포 금지 시간대: 평일 07:30–17:00 KST.** 첫 단계에서 현재 시각을 확인하고, 이 시간대면 배포하지 않고 끝냄. 수동 실행도 같음.
  - 워커가 수집·계산·주문하는 도중에 재시작되면 작업이 중간에 끊김. 시세 수집(08시 이후), 장중 주문, 장 마감 후 계산이 모두 이 시간대에 들어감.
  - 금지 시간대에 머지된 변경은 그날 예약 실행에서 배포됨.
  - 임시값임. 주문 시각(#13)이 정해지면 다시 정함.
  - GitHub의 예약 실행은 UTC 기준이고(평일 17:30 KST = 월–금 08:30 UTC) 몇 분 늦게 시작될 수 있음.
- 순서
  1. 백엔드 이미지를 빌드해 GHCR에 올림.
  2. EC2에서 새 이미지를 받고, 서비스 DB에 마이그레이션(`alembic upgrade head`)을 적용한 뒤 `docker compose up -d`로 다시 띄움.
  3. 프론트엔드를 빌드해 S3에 올리고 CloudFront 캐시를 무효화함. 백엔드보다 나중에 올려, 새 화면이 아직 없는 API를 부르지 않게 함.
- AWS 인증은 GitHub OIDC로 IAM 역할을 받아 씀. AWS 액세스 키를 GitHub Secrets에 두지 않음.
- EC2 명령은 SSM Run Command로 실행함. SSH 키를 GitHub에 두지 않고 `22` 포트도 열지 않음.

## 개발 환경

- 팀원 PC 구성
  - 백엔드: 자기 PC에서 API 서버(`uv run fastapi dev`)를 띄움. DB는 서비스 DB(Tailscale), LLM은 자기 PC의 Ollama를 씀.
  - 테스트 DB: 루트 `compose.yaml`의 `db-test`(`docker compose up -d db-test`).
  - 마스터키는 로컬 키(`CREDENTIAL_KEY_PROVIDER=local`)를 씀. 서비스 DB의 KIS 자격 증명은 복호화되지 않음.
- 워커는 팀원 PC에서 서비스 DB를 대상으로 실행하지 않음.
- 팀원 PC의 `.env`에서는 `REAL_TRADING_ENABLED`를 항상 `false`로 둠.

## 시연 체크리스트

- [ ] 시연 장소 네트워크에서 LLM PC의 Tailscale 연결 확인 (미리 방문해 LLM PC를 연결하고 `tailscale status`로 EC2가 보이는지, 아래 `curl` 확인까지 해 봄. 방화벽이 엄격한 망이면 중계 서버 경유로 느려지거나 막힐 수 있음)
- [ ] LLM PC: 전원 연결, 절전·잠자기 해제
- [ ] LLM PC: Tailscale 연결 → Ollama 실행 순서로 켬
- [ ] LLM PC: 정해진 모델 태그가 받아져 있음 (`ollama list`)
- [ ] EC2에서 LLM PC 연결 확인: `curl http://<LLM PC의 Tailscale 주소>:11434/api/tags` 응답에 모델이 보임
- [ ] 시연 장소 네트워크에서 서비스 도메인 접속 확인
- [ ] 서비스 DB에 최신 시세·분배금이 수집되어 있음
- [ ] 시연 시간이 배포 금지 시간대 밖이면, 시연 중 main 머지·수동 배포를 하지 않음
- [ ] 전략 변환 한 번을 미리 실행해 모델을 메모리에 올려 둠 (첫 호출은 모델 로딩 때문에 느림)

## 미정

- 도메인 구매처 (Route 53 추천: ACM 인증서 검증과 CloudFront 연결을 AWS 안에서 끝낼 수 있음)
- Caddy의 Let's Encrypt 인증서 검증 방식. 보안그룹이 `443`만 CloudFront에 열면 기본 방식(HTTP·TLS 검증)이 막힘. DNS 검증(Caddy DNS 플러그인) 또는 `80` 포트 개방 중에서 고름
- EC2 인스턴스 사양, 서비스 DB 백업 방식
- 배포 실패 시 되돌리는 방법 (이전 이미지 태그로 재배포, 마이그레이션 되돌리기)
- 프론트엔드 개발 서버(`npm run dev`)의 `/api` 전달 대상 (서비스 도메인 또는 자기 PC의 백엔드)
- 배포 금지 시간대 확정 (#13 주문 시각이 정해진 뒤)
- Tailscale 접근 정책 파일의 구체적 내용
- 모델 태그
- KMS 키 생성과 IAM 정책(EC2 역할의 KMS·SSM 권한, GitHub OIDC 역할)의 구체적 내용
