# 인프라·실행 환경

개발·시연 때 백엔드, DB, LLM을 어디서 실행하고 어떻게 연결하는지 정의함.
핵심 규칙은 CLAUDE.md의 "실행 환경"과 "데이터베이스와 설정"에 있음. 프로세스 구성과 작업 실행 방식은 `docs/architecture.md`.

## 구성

```
[AWS EC2]   리버스 프록시(HTTPS) + API 서버 + 워커 + PostgreSQL 18(공용 개발 DB, Docker)
     │
     │  Tailscale 사설망 (기기마다 100.x.y.z 주소)
     │
     ├── [LLM PC]   Ollama :11434   ← AWS 백엔드가 호출하는 유일한 LLM
     │
     └── [팀원 PC]  브라우저로 EC2 서비스 접속 (https://<기기명>.<tailnet명>.ts.net)
                    개발 때는 로컬 API 서버 + 자기 PC의 Ollama + 테스트 DB(Compose)
                    공용 개발 DB에는 Tailscale로 접속
```

- AWS에서는 LLM을 돌리지 않음. GPU 인스턴스 비용을 피하고, 팀원 PC 중 성능이 좋은 한 대를 LLM PC로 씀.
- DB와 Ollama 포트는 인터넷에 열지 않음. Tailscale 사설망 안에서만 접근함.

## 공개 범위와 HTTPS

- 서비스(프론트엔드와 API)는 **인터넷에 공개하지 않음.** Tailscale 사설망에 참여한 기기에서만 접속함. 실제로 서비스하지 않으므로(졸업작품) 공개할 필요가 없음.
- 그래도 HTTPS로 제공함. Tailscale의 MagicDNS와 HTTPS 인증서 기능을 켜고, EC2의 `*.ts.net` 인증서를 리버스 프록시에 붙임.
  - Tailscale 구간은 이미 암호화되지만, HTTP면 브라우저가 로그인·KIS 앱키 입력 화면에 경고를 띄우고 `Secure` 쿠키를 쓸 수 없음. 실제 서비스를 가정한 설계(`docs/auth.md`, `docs/trading.md`)와 시연 환경을 일치시키려는 것임.
  - 웹 푸시 등 HTTPS에서만 동작하는 브라우저 기능도 쓸 수 있음.
  - 인증서 유효기간은 90일임. 리버스 프록시가 자동으로 갱신하게 함.
  - 인증서를 발급하면 `<기기명>.<tailnet명>.ts.net` 이름이 공개 인증서 투명성(CT) 로그에 기록됨. 이름만 드러나고 접속은 여전히 Tailscale 안에서만 됨. 기기명에 개인 정보를 넣지 않음.
- 프론트엔드는 EC2에서 API와 **같은 오리진**으로 서빙함. 리버스 프록시가 정적 파일과 `/api`를 함께 처리하므로 CORS 설정이 필요 없음.

## AWS (EC2)

- EC2 한 대에 리버스 프록시, API 서버, 워커, 공용 개발 DB를 둠.
- 워커(예약 작업, 백테스트 대기열)는 EC2에서만 하나 실행함. 팀원 PC에서는 공용 DB에 붙은 워커를 실행하지 않는다(`docs/architecture.md`).
- PostgreSQL은 EC2 안에서 Docker로 실행함. 포트는 로컬과 같은 `15432`를 써서, 팀원은 `.env`의 `POSTGRES_HOST`만 바꾸면 됨.
- 보안그룹에서 `15432`(DB)는 열지 않음. Tailscale은 인바운드 포트를 열지 않아도 연결되므로, 팀원은 사설망으로 DB에 접속함.
- 공용 개발 DB에는 main에 머지된 마이그레이션만 적용함. 머지 전 스키마 변경은 로컬 개발 DB(`docker compose up -d`)에서 확인함.
- 실전 주문은 EC2 백엔드에서만 냄. `REAL_TRADING_ENABLED=true`는 EC2의 `.env`에만 둠.

## KIS 자격 증명 암호화

사용자 KIS 자격 증명은 DB에 암호화해 저장함. 상세는 `docs/trading.md`.

| 실행 위치 | 마스터키 | `.env` |
|---|---|---|
| AWS EC2 | AWS KMS | `CREDENTIAL_KEY_PROVIDER=kms`, `KMS_KEY_ID` |
| 팀원 PC | 로컬 키 | `CREDENTIAL_KEY_PROVIDER=local`, `CREDENTIAL_LOCAL_KEY` |

- EC2에는 IAM 역할(인스턴스 프로파일)을 붙여 KMS 키를 쓰게 함. 액세스 키를 `.env`에 두지 않음.
- IAM 역할에는 그 KMS 키 하나에 대한 암호화·복호화·데이터 키 생성 권한만 줌.
- 팀원 PC에는 KMS 권한을 주지 않음. 그래서 공용 개발 DB의 자격 증명은 팀원 PC 백엔드에서 복호화되지 않음.

## Tailscale

- 참여 기기: EC2, LLM PC, 개발 팀원 PC.
- 무료 Personal 플랜은 사용자 6명까지, 사용자 기기 수는 무제한임. 플랜 조건은 바뀔 수 있으므로 가입할 때 공식 가격 페이지에서 확인함.
- 기본 접근 정책은 "모든 기기 간 모두 허용"임. Ollama에는 인증이 없으므로 기본 정책을 그대로 쓰지 않고 아래처럼 좁힘.
  - LLM PC의 `11434`: EC2만 접근 허용
  - EC2의 `15432`(DB): 팀원 PC만 접근 허용 (EC2 백엔드는 같은 서버 안에서 접속)
  - EC2의 SSH와 HTTPS(`443`, 리버스 프록시): 팀원 PC만 접근 허용
- 정책 파일의 구체적 내용은 Tailscale 관리 콘솔에서 설정할 때 확정하고, 확정하면 이 문서에 옮겨 적음.

## LLM

### 호출 주소

LLM 호출 주소는 `.env`의 `OLLAMA_BASE_URL` 하나로 정함. 코드는 주소를 몰라도 됨.

| 실행 위치 | `OLLAMA_BASE_URL` | 비고 |
|---|---|---|
| 팀원 PC(개발) | `http://localhost:11434` | 자기 PC의 Ollama. LLM PC가 없어도 개발할 수 있음 |
| AWS 백엔드 | `http://<LLM PC의 Tailscale 주소>:11434` | LLM PC 한 대만 호출함 |

- AWS 백엔드는 LLM PC가 꺼져 있어도 다른 PC로 대체하지 않음. 대체 목록을 두면 요청이 팀원이 작업 중인 PC로 가서 자원을 쓰고, 어느 PC가 응답했는지에 따라 결과가 달라짐.
- LLM PC가 꺼져 있으면 AWS 백엔드의 전략 변환은 실패함. LLM 호출에는 타임아웃을 두고 "LLM 서버에 연결할 수 없음"을 명확히 돌려줌. 백테스트·리밸런싱·시세 수집 등 나머지 기능은 LLM 없이도 동작해야 함.

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
| 공용 개발 DB | AWS EC2(Docker) | `15432` | 평소 개발, AWS 백엔드, 시연 |
| 로컬 개발 DB | 팀원 PC(Compose `db`) | `15432` | 머지 전 스키마 변경 확인 등 (선택) |
| 테스트 DB | 팀원 PC(Compose `db-test`) | `15433` | 자동 테스트 전용 |

- 공용·로컬 개발 DB 전환은 `.env`의 `POSTGRES_HOST`로 한다(EC2의 Tailscale 주소 또는 `localhost`).
- 테스트는 `.env` 값과 무관하게 항상 로컬 테스트 DB에서 돎. `backend/tests/conftest.py`가 `POSTGRES_HOST`와 `POSTGRES_PORT`를 덮어씀.
- 공용 DB 시세 수집은 한 곳에서만 함. 상세는 `docs/market-data.md`.

## 시연 체크리스트

- [ ] 시연 장소 네트워크에서 Tailscale 연결 확인 (미리 방문해 LLM PC를 연결하고 `tailscale status`로 EC2가 보이는지, 아래 `curl` 확인까지 해 봄. 방화벽이 엄격한 망이면 중계 서버 경유로 느려지거나 막힐 수 있음)
- [ ] LLM PC: 전원 연결, 절전·잠자기 해제
- [ ] LLM PC: Tailscale 연결 → Ollama 실행 순서로 켬
- [ ] LLM PC: 정해진 모델 태그가 받아져 있음 (`ollama list`)
- [ ] EC2에서 LLM PC 연결 확인: `curl http://<LLM PC의 Tailscale 주소>:11434/api/tags` 응답에 모델이 보임
- [ ] 공용 DB에 최신 시세·분배금이 수집되어 있음
- [ ] 전략 변환 한 번을 미리 실행해 모델을 메모리에 올려 둠 (첫 호출은 모델 로딩 때문에 느림)

## 미정

- API 서버·워커·리버스 프록시를 EC2에서 실행하는 방식(Docker 여부, 프로세스 관리)과 배포 절차
- 리버스 프록시 구현: Caddy 또는 `tailscale serve` (`docs/architecture.md`)
- EC2의 Tailscale 기기명
- EC2 인스턴스 사양, 공용 DB 백업 방식
- Tailscale 접근 정책 파일의 구체적 내용
- 모델 태그
- KMS 키 생성과 IAM 정책의 구체적 내용
