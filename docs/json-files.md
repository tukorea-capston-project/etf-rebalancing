# JSON 파일별 설명

전체 흐름과 개념(자산군, 블록, 칸 등)은 [전체 로직 설명](json-flow.md) 참고.

## 폴더 구성

| 폴더 | 내용 |
|---|---|
| `llm_json/state/` | 서버가 저장하고 계속 갱신하는 상태. 설정, 사용자 요청 초안, 포트폴리오, 시장 상태, 제안 |
| `llm_json/llm/` | LLM이 돌려주는 출력 형식. LLM은 정해진 형식의 JSON만 내야 하고, 서버가 검증한 뒤 사용함 |

## 파일 간 연결

| 파일 | 만드는 재료 | LLM 출력 | 다음으로 가는 곳 |
|---|---|---|---|
| `catalog.json`, `policy.json` | 저장소 설정 | - | `draft.json` |
| `draft.json` | 사용자 메시지, 카탈로그, 정책 | `parse_request` | `portfolio.json` |
| `portfolio.json` | 확정된 `draft.json`, 수락된 `suggestion.json` | - | - |
| `market.json` | 경기·업종·분위기 지표 | `evidence_check`, `bok_policy`, `news_mood` | `suggestion.json` |
| `suggestion.json` | `market.json`, `portfolio.json` | `suggestion_text` | `portfolio.json` (새 revision) |

- 모든 상태 파일에 `schema_version`이 있음. JSON 구조 자체의 버전임
- `catalog_version`, `policy_version`은 그 데이터를 만들 때 쓴 설정 버전임. 설정이 바뀌어도 예전 데이터가 어떤 기준으로 만들어졌는지 추적 가능함

---

## state/

### catalog.json — 선택지 목록(카탈로그)

LLM과 서버가 쓸 수 있는 **값의 목록**을 모아 둔 파일. LLM 출력의 값은 반드시 여기 있는 값 중 하나여야 함.

| 필드 | 설명 |
|---|---|
| `version`, `status`, `decided_on` | 카탈로그 버전과 확정 여부. 지금은 `초안` |
| `intents` | 사용자 요청의 종류(의도). 포트폴리오생성, 포트폴리오수정, 단순질문, 범위밖, 부적절 |
| `out_of_scope_reasons` | 처리할 수 없는 요청의 이유. 개별종목, 가상자산, 레버리지인버스 등 |
| `goals` | 투자 목적. 노후, 주택자금, 목돈마련 등 |
| `risk_levels` | 위험 성향 5단계. 안정형 → 공격투자형 |
| `shares` | ETF 비중을 말로 표현한 정도. 조금, 보통, 많이 |
| `rebalance_cycles`, `rebalance_methods` | 리밸런싱 주기(월·분기·반기·연)와 방식(주기·밴드·혼합) |
| `expressions` | 자주 쓰는 말과 칸 값의 연결. 예: "안전하게" → `risk_level`=안정형 |
| `whitelist` | 투자 가능한 ETF 목록(화이트리스트) 파일 위치 |
| `categories` | 화이트리스트의 ETF 분류(category)가 어느 자산군(asset_class)에 속하는지 |
| `aliases` | ETF 별칭. 예: "S&P", "미국 주식" → `360750` |
| `risk_templates` | 위험 성향별 기본 구성. 자산군 블록마다 목표 비중과 기본 ETF |
| `horizon_warnings` | 투자 기간이 짧은데 위험 성향이 높을 때 보여 줄 경고 |
| `questions` | 필수 정보가 빠졌을 때 사용자에게 할 질문과 선택지 |

### policy.json — 운용 규칙(정책)

시스템이 따르는 **기본값과 규칙**. 숫자 기준은 전부 여기 있음.

| 필드 | 설명 |
|---|---|
| `dialog` | 대화 규칙. 꼭 채워야 하는 칸(`risk_level`, `horizon_months`), 질문 최대 3회, LLM 재시도 최대 2회 |
| `defaults` | 사용자가 말하지 않은 값의 기본값. 투자금 1,000만원, 리밸런싱 혼합·분기, 백테스트 수수료·슬리피지 등 |
| `rebalance` | 밴드 확인 시점(밴드형은 주 1회, 혼합형은 주기 리밸런싱일)과 밴드 이탈 시 처리(해당 자산만 되돌림) |
| `fixed_rules` | 고정 규칙. 적립금은 부족한 자산부터 매수, 분배금은 같은 ETF에 재투자 |
| `allocation` | 비중 계산 규칙. 조금:보통:많이 = 1:2:3, ETF 하나 최대 50%·최소 5%, 최대 10개, 1% 단위 |
| `suggestion_limit` | 제안으로 바꿀 수 있는 비중 한도. 기준 비중에서 10%p / 50% 중 좁은 쪽 |
| `regime` | 경기·업종 상태 판단 규칙과, 상태에 따른 비중 조정 규칙(`adjustments`) |
| `mood` | 시장 분위기(공포·보통·탐욕) 판단 기준과 상태별 대응 |

`regime.adjustments`의 규칙 두 개:

| `rule_id` | 조건 | 조정 |
|---|---|---|
| `regime_up_sector` | 경기 좋아짐 + 업종 늘어남 | 그 업종 ETF +3%p, 같은 만큼 다른 주식 ETF에서 뺌 |
| `regime_down_defense` | 경기 나쁨 | 채권·현금성 +5%p, 같은 만큼 주식에서 뺌 |

### draft.json — 포트폴리오 초안

사용자와 대화하며 채워 가는 **작성 중인 포트폴리오**. 사용자가 확인하면 `portfolio.json`이 됨.

| 필드 | 설명 |
|---|---|
| `status` | 초안 상태. 예시는 `확인대기`(사용자 확인 기다리는 중) |
| `base_portfolio_id` | 기존 포트폴리오 수정이면 원래 포트폴리오 ID. 새로 만들면 `null` |
| `question_rounds` | 지금까지 질문한 횟수 |
| `turns` | 사용자가 보낸 메시지 기록. 각 메시지를 해석한 LLM 출력 ID(`llm_output_id`)를 함께 저장 |
| `slots` | 채워진 칸 전체. `profile`(목적·기간·성향·금액), `etfs`, `rules`(리밸런싱 설정) |
| `missing` | 아직 비어 있는 필수 칸. 비어 있으면 질문함 |
| `questions` | 사용자에게 한 질문과 답변 |
| `out_of_scope` | 처리할 수 없는 요청. 예시는 "삼성전자도요" → 개별종목 |
| `conflicts`, `warnings` | 요청끼리 충돌하는 부분, 사용자에게 보여 줄 경고 |
| `confirm_text` | 사용자에게 보여 줄 확인 문장 |

칸 하나는 다음 필드로 이루어짐. 예시는 "2년 뒤에" → 기간 24개월.

| 필드 | 설명 | 예시 |
|---|---|---|
| `value` | 칸의 값 | `24` |
| `source` | 값의 출처. `사용자발화`, `질문답변`, `템플릿`, `기본값` | `사용자발화` |
| `quote` | 근거가 된 사용자 원문. 사용자가 말한 게 아니면 `null` | `2년 뒤에` |
| `ref` | 근거 위치. 메시지 ID(`t1`), 질문 ID(`q1`), 템플릿 이름(`안정추구형`) | `t1` |

### portfolio.json — 확정된 포트폴리오

사용자가 확인한 **실제 운용 대상**. 덮어쓰지 않고 바뀔 때마다 `revision`이 올라감.

| 필드 | 설명 |
|---|---|
| `revision`, `prev_revision` | 현재 버전과 이전 버전 |
| `origin` | 이 버전이 어떻게 만들어졌는지. 예시는 `제안반영`(제안 `sg_20261201`의 후보 `c1`을 수락) |
| `stage` | 운용 단계. 예시는 `모의운용` |
| `profile` | 목적, 기간, 위험 성향 |
| `holdings` | 보유 ETF. `base`는 기준 비중, `target`은 목표 비중 |
| `rules` | 이 포트폴리오에 적용할 규칙(ETF 최대 비중, 리밸런싱, 제안 한도). 정책 기본값을 복사한 뒤 사용자가 바꿀 수 있음 |
| `backtest` | 백테스트 설정과 결과 ID, 사용자가 결과를 승인한 시각 |
| `trading` | 모의·실전투자 설정. 계좌 종류, 주문 방식(장전 동시호가 08:40), 주문 전 점검 |

`trading.pre_order_checks`:

| 필드 | 설명 |
|---|---|
| `max_premium` | ETF 가격이 실제 가치(NAV)보다 1% 넘게 비싸면 주문하지 않음 |
| `skip_halted` | 거래정지 종목은 건너뜀 |
| `check_balance` | 주문 전 잔고 확인 |

### market.json — 시장 상태

매달 계산하는 **경기·업종·시장 분위기 판단 결과**. 제안을 만들 때 근거로 씀.

| 필드 | 설명 |
|---|---|
| `as_of` | 기준일 |
| `regime.economy` | 경기 상태(좋아짐·꺾임·나쁨)와 근거 지표(경기선행지수 방향, 기준금리, 국고채 금리, 환율, 수출) |
| `regime.sectors` | 업종별 상태(늘어남·줄어듦)와 근거 지표(업종 수출 증감률) |
| `regime.market_model` | 통계 모형(점프모형)이 계산한 상승·하락 확률 |
| `mood` | 시장 분위기(공포·보통·탐욕), 그 상태가 이어진 일수, 근거 지표 |

각 상태에 공통으로 있는 필드:

| 필드 | 설명 |
|---|---|
| `state`, `prev_state`, `changed` | 지금 상태, 이전 상태, 바뀌었는지 |
| `check` | 상태가 바뀌었을 때 LLM이 근거를 확인한 결과. `verdict`(판정), `hold_until`(판단 보류 기한), 확인에 쓴 LLM 출력 ID |
| `indicators` / `indicator` | 근거 지표. 값, 기준 기간, 발표일, 출처 |

`mood.indicators`:

| 필드 | 설명 |
|---|---|
| `vkospi_pct_1y` | 변동성 지수(VKOSPI)가 최근 1년 중 어느 위치인지(0~1) |
| `margin_loan_z` | 신용융자(빚내서 투자한 돈)가 평소보다 얼마나 많은지 |
| `deposits_z` | 투자자 예탁금이 평소보다 얼마나 많은지 |
| `news_score_mean` | 뉴스 감성 점수 평균. LLM이 매긴 점수 |
| `theme_count_z` | 특정 테마 뉴스가 평소보다 얼마나 몰렸는지 |

이름 끝의 `_z`는 z점수(평균에서 표준편차 몇 배만큼 떨어졌는지)임.

### suggestion.json — 비중 변경 제안

시장 상태를 보고 만든 **포트폴리오 변경 후보 목록**과 사용자의 선택.

| 필드 | 설명 |
|---|---|
| `kind` | 제안 종류. 예시는 `월간개선` |
| `portfolio_id`, `portfolio_revision` | 어느 포트폴리오의 몇 번째 버전에 대한 제안인지 |
| `market_state_id` | 근거로 쓴 시장 상태 |
| `candidates` | 후보 목록 |
| `decision` | 사용자 선택. 고른 후보, 반영 방식(`지금리밸런싱`), 새로 만들어진 포트폴리오 버전 |

후보 하나의 필드:

| 필드 | 설명 |
|---|---|
| `trigger` | 후보가 나온 이유. `레짐`(시장 상태 규칙), `리밸런싱`(목표로 되돌리기만), `유지`(그대로 두기) |
| `rule_id`, `sector` | 적용한 정책 규칙과 업종 |
| `changes` | 비중 변경 내용(`from` → `to`) |
| `total_change` | 옮긴 비중 합계 |
| `title`, `reason` | 사용자에게 보여 줄 제목과 이유. LLM이 작성 |

---

## llm/

LLM이 출력하는 JSON 형식. `_record.json`을 뺀 나머지는 LLM이 실제로 내는 **출력 본문**임.

모든 출력에 공통 규칙이 있음.
- 값은 카탈로그에 있는 것만 씀
- 근거는 원문을 그대로 옮긴 `quote`로 남김. 서버가 원문에 그 문장이 실제로 있는지 확인할 수 있음
- 입력 문서는 `ref`(`d1`, `d2` …)로 가리킴

### _record.json — LLM 호출 기록

LLM 출력 하나를 저장할 때 감싸는 **기록 형식**. 다른 파일에서 `llm_output_id`로 가리키는 대상이 이것임.

| 필드 | 설명 |
|---|---|
| `output_id` | 기록 ID |
| `task` | 작업 종류. 아래 파일 이름 중 하나 |
| `model`, `prompt_version` | 사용한 모델(`qwen3:8b`)과 프롬프트 버전 |
| `as_of` | 기준일. 이 날짜 이후 정보를 쓰지 않았다는 표시 |
| `inputs` | 입력 문서 목록. `ref`, 문서 ID, 발행 시각 |
| `validation` | 형식 검증 결과. 통과 여부, 시도 횟수, 오류 |
| `output` | LLM 출력 본문 |

### parse_request.json — 사용자 요청 해석

사용자 메시지를 칸 단위로 쪼갠 결과. `draft.json`의 `slots`를 채우는 재료임.

| 필드 | 설명 |
|---|---|
| `intent` | 요청 종류 |
| `profile` | 목적, 기간(개월), 위험 성향, 투자금, 월 적립금, 적립일. 말하지 않은 건 `null` |
| `etfs` | 언급한 ETF의 종목코드와 비중 표현(`share`) 또는 직접 말한 비중(`weight`) |
| `rules` | 리밸런싱 설정 중 사용자가 말한 것 |
| `out_of_scope` | 처리할 수 없는 부분과 이유 |

### evidence_check.json — 상태 변화 근거 확인

경기·업종 상태가 바뀌었을 때, 뉴스·문서에 그 변화를 뒷받침하는 내용이 있는지 확인한 결과.

| 필드 | 설명 |
|---|---|
| `evidence` | 근거 문장 |
| `verdict` | 판정. 예시는 `뒷받침` |

### bok_policy.json — 한국은행 통화정책 해석

한국은행 의사록 등을 읽고 통화정책 방향이 바뀌었는지 판단한 결과.

| 필드 | 설명 |
|---|---|
| `evidence` | 근거 문장 |
| `policy_shift` | 정책 변화 여부. 예시는 `안바뀜` |
| `direction` | 바뀌었다면 방향. 안 바뀌었으면 `null` |

### news_mood.json — 뉴스 감성 분석

뉴스 문장마다 시장 관련 여부, 감성 점수, 테마를 매긴 결과. `market.json`의 `news_score_mean`, `theme_count_z` 계산에 쓰임.

| 필드 | 설명 |
|---|---|
| `market_related` | 시장과 관련 있는 뉴스인지. 관련 없으면 점수를 매기지 않음 |
| `score` | 감성 점수. 양수는 긍정, 음수는 부정 |
| `theme` | 관련 테마. 없으면 `없음` |

### suggestion_text.json — 제안 문구 작성

서버가 계산한 제안 후보에 사용자용 제목과 이유를 붙인 결과. 숫자는 서버가 정하고, LLM은 문장만 씀. 결과는 `suggestion.json`의 `title`, `reason`에 들어감.
