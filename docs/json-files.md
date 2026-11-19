# JSON 파일별 설명

전체 흐름과 개념(칸, 이슈, 기본 자산군 비중, HRP, 정적 층·동적 층 등)은 [전체 로직 설명](json-flow.md) 참고.

> 이 문서는 개편안 기준임. 이전 구조에서 바뀐 부분은 각 파일의 **변경** 표시로 적어 둠. 예시 JSON의 미정 값은 `null`, 예시 규칙은 `"status": "예시"`로 표시함.

## 폴더 구성

| 폴더 | 내용 |
|---|---|
| `llm_json/state/` | 서버가 저장하고 계속 갱신하는 상태. 설정, 사용자 요청 초안, 포트폴리오, 시장 상태, 백테스트, 동적 조정 기록 |
| `llm_json/llm/` | LLM이 돌려주는 출력 형식. LLM은 정해진 형식의 JSON만 내야 하고, 서버가 검증한 뒤 사용함 |

## 파일 간 연결

| 파일 | 만드는 재료 | LLM 출력 | 다음으로 가는 곳 |
|---|---|---|---|
| `catalog.json`, `policy.json` | 저장소 설정 | - | `draft.json` |
| `draft.json` | 사용자 메시지, 카탈로그, 정책 | `parse_request` | `portfolio.json` |
| `portfolio.json` | 확인된 `draft.json`, 반영된 `adjustment.json` | - | `backtest.json` |
| `backtest.json` | `portfolio.json`, 과거 시세, 과거 시점의 `market.json` | - | `portfolio.json` (승인) |
| `market.json` | 국면 지표(변동성, 추세, 금리 스프레드, 국면 확률, 경기·업종), 분위기 지표 | `evidence_check`, `bok_policy`, `news_mood` | `adjustment.json` |
| `adjustment.json` | `market.json`의 국면 신호, `portfolio.json` | `adjustment_text` | `portfolio.json` (새 revision) |

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
| `risk_asset_classes` **(신규)** | 위험자산으로 보는 자산군. 주식, 원자재, 리츠. 기간 경고에 씀 |
| `shares` | ETF 비중을 말로 표현한 정도. 조금, 보통, 많이. HRP 비중에 곱하는 배수로 씀 |
| `slot_sources` **(신규)** | 칸 값의 출처. 사용자발화, 질문답변, 생성, 기본값 |
| `issue_levels` **(신규)** | 이슈 심각도. 차단, 조정, 확인, 경고 |
| `trigger_kinds` **(신규)** | 동적 전환이 일어난 계기. `신호`(기준 넘음), `밴드재평가`(바깥 밴드·반복 이탈 후 재평가), `최소점검일`(분기 재평가) |
| `backtest_modes` **(신규)** | 백테스트 실행 종류. 거시판단(실제 운용 로직), 고정비중(비교용, 동적 층 끔) |
| `expressions` | 자주 쓰는 말과 칸 값의 연결. 예: "전세" → `goal`=주택자금, "조금만" → `share`=조금 |
| `whitelist` | 투자 가능한 ETF 목록(화이트리스트) 파일 위치 |
| `categories` | 화이트리스트의 ETF 분류(category)가 어느 자산군(asset_class)에 속하는지 |
| `aliases` | ETF 별칭. 예: "S&P", "미국 주식" → `360750` |
| `questions` | `확인` 이슈에서 사용자에게 할 질문과 선택지 문구 |

**변경**: 투자 성향을 쓰지 않으므로 `risk_levels`, `risk_grades`, `risk_level_grades`, `risk_templates`, 성향 질문, 성향 관련 `expressions`를 없앰. 정적 리밸런싱이 이중 밴드로 바뀌어 `rebalance_cycles`, `rebalance_methods`를 없앰. `horizon_warnings`는 `policy.checks`로 옮김.

### policy.json — 운용 규칙(정책)

시스템이 따르는 **기본값과 규칙**. 숫자 기준은 전부 여기 있음.

| 필드 | 설명 |
|---|---|
| `dialog` | 대화 규칙. 질문 최대 3회, LLM 재시도 최대 2회. **변경**: 꼭 채워야 하는 칸(`required_slots`)을 없앰. 빈 칸은 모두 기본값으로 채움 |
| `construction` **(신규)** | 포트폴리오 생성 규칙. 아래 표 참고. **변경**: 이전 `allocation`의 제한값이 여기 `limits`로 옮겨 옴 |
| `checks` **(신규)** | 이슈 규칙 목록. 규칙마다 `check_id`, `level`(차단·조정·확인·경고), 처리 방식, 사용자 문구. 이전의 `allocation` 제한 위반, `horizon_warnings`(기간이 짧은데 위험자산 비중이 높음)를 이 형식으로 모음 |
| `defaults` | 사용자가 말하지 않은 값의 기본값. 투자금 1,000만원, **자산군 비중(`asset_classes`, 신규, 잠정 주식 60 / 채권 40)**, 밴드 폭, 백테스트 설정(수수료·슬리피지, 실행 종류 `modes`, 비교 대상) |
| `rebalance` **(변경)** | 정적 층(이중 밴드). 아래 표 참고. 이전의 주기·밴드·혼합 방식 선택을 없앰 |
| `fixed_rules` | 고정 규칙. 적립금은 부족한 자산부터 매수, 분배금은 같은 ETF에 재투자 |
| `dynamic` **(신규)** | 동적 층(국면 신호). 아래 표 참고 |
| `regime` | 경기·업종 상태 판단 규칙(상태 목록, 업종별 지표와 ETF). 동적 층의 국면 지표 중 하나. **변경**: 비중 조정 규칙(`adjustments`)은 `dynamic`으로 옮김. 판단 보류 기간(`turning_down_months`, `hold_days`)은 `dynamic.signals`의 확인 기간과 겹쳐서 없앰 |
| `mood` | 시장 분위기(공포·보통·탐욕) 판단 기준과 공포 시 경고. **변경**: 탐욕 시 리밸런싱 알림(`greed`)은 이중 밴드와 겹쳐서 없앰 |

**변경**: 위험등급 산정 규칙(`product_risk`)을 없앰.

`construction`:

| 필드 | 설명 |
|---|---|
| `weighting` | 자산군 안의 비중 계산 방식. `HRP`(기본). 비교용 `역변동성`, `동일비중` |
| `lookback` | 상관계수·변동성을 계산할 기간 |
| `min_history` | 자동 후보가 되려면 필요한 최소 데이터 기간. 짧으면 사용자가 고른 경우에만 담음 |
| `representative` | 묶음마다 대표 ETF를 고르는 기준(변동성, 거래량). 사용자가 고른 ETF가 묶음에 있으면 그것을 우선 |
| `share_multipliers` | 비중 표현 배수. 조금 0.5, 보통 1, 많이 1.5(잠정) |
| `limits` | ETF 하나 최대 50%·최소 5%, 최대 10개, 1% 단위 |
| `budget` | 자산군 비중의 출처. 사용자가 말했으면 그대로, 아니면 `defaults.asset_classes` |

`rebalance` (정적 층):

| 필드 | 설명 |
|---|---|
| `check` | 밴드 확인 시점. 매일 장 마감 뒤(국면 신호 점검과 함께) |
| `inner_band` | 안쪽 밴드. 5%p / 25% 중 좁은 쪽(잠정). 이탈하면 벗어난 자산만 목표로 되돌림 |
| `outer_band` | 바깥 밴드. 10%p / 50% 중 좁은 쪽(잠정). 이탈하면 되돌리기 전에 국면 재평가 |
| `repeat_breach` | 같은 자산이 같은 방향으로 이 횟수 이상 이탈하면 바깥 밴드 이탈과 똑같이 처리. 횟수와 세는 기간(미정) |

`dynamic` (동적 층):

| 필드 | 설명 |
|---|---|
| `monitoring` | 국면 지표 점검 주기(매일). 월간 지표는 발표일에 갱신 |
| `min_check` | 최소 점검일. 분기마다 신호가 없어도 국면을 재평가함 |
| `signals` | 국면 신호 목록. 신호마다 지표, 진입 기준(`enter`), 해제 기준(`exit`), 확인 기간(`confirm_days`). 진입·해제 기준을 다르게 두고 확인 기간을 채워야 전환해서 휩쏘를 막음. 구체 값은 거시판단 로직에서 정함(추후) |
| `near_threshold` | 기준선 근접 구간. 신호가 이 안에 있으면 밴드 리밸런싱을 보류하고 동적 판단을 먼저 함. 최대 보류 기간(`max_hold_days`) 포함(미정) |
| `limit` | 기준 비중에서 잰 조정 한도. 10%p / 50% 중 좁은 쪽. 넘으면 한도까지만 반영(잠정). 종목을 새로 넣거나 뺄 때의 한도는 미정. **변경**: 이전 `suggestion_limit` |
| `lock_user_weights` | 사용자가 직접 정한 비중은 조정하지 않음(잠정 `true`) |
| `adjustments` | 국면별 목표 종목·비중 규칙. 목표 비중 = 기준 비중 + 지금 국면의 조정(누적 안 함). 거시판단 로직이 정해지면 바뀜 |

**변경**: 이전의 `schedule`(월 1회 정기), `events`, `cooldown`을 없앰. 달력 대신 신호로 감지하고, 휩쏘는 진입·해제 기준과 확인 기간으로 막음.

`dynamic.adjustments`의 지금 규칙 두 개(예시):

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
| `slots` | 채워진 칸 전체. 아래 표 참고 |
| `questions` | `확인` 이슈로 사용자에게 한 질문과 답변 |
| `issues` **(변경)** | 규칙에 어긋난 부분. 이전의 `out_of_scope`, `conflicts`, `warnings`를 하나로 합침. 아래 표 참고 |
| `construction` **(신규)** | 생성 결과. 아래 표 참고 |
| `confirm_text` | 사용자에게 보여 줄 확인 문장 |

`slots`:

| 필드 | 설명 |
|---|---|
| `intent` | 요청 종류 |
| `profile` | 목적, 기간, 투자금, 월 적립금, 적립일. **변경**: 위험 성향(`risk_level`)을 없앰 |

**변경**: 리밸런싱 설정 칸(`rules`)을 없앰. 밴드 폭 같은 운용 규칙은 사용자 입력이 아니라 정책 값을 씀
| `asset_classes` **(신규)** | 자산군 비중. 사용자가 말했으면 `사용자발화`, 아니면 `기본값` |
| `etfs` | ETF 목록. 종목코드, 비중 표현(`share`), 비중(`weight`). 사용자가 말한 것과 HRP가 고른 것(`생성`)이 함께 있고 출처로 구분함 |

칸 하나는 다음 필드로 이루어짐. 예시는 "2년 뒤에" → 기간 24개월.

| 필드 | 설명 | 예시 |
|---|---|---|
| `value` | 칸의 값 | `24` |
| `source` | 값의 출처. `catalog.slot_sources` 중 하나 | `사용자발화` |
| `quote` | 근거가 된 사용자 원문. 사용자가 말한 게 아니면 `null` | `2년 뒤에` |
| `ref` | 근거 위치. 메시지 ID(`t1`), 질문 ID(`q1`), 생성 결과(`construction`) | `t1` |

`issues`의 이슈 하나:

| 필드 | 설명 |
|---|---|
| `issue_id`, `check_id` | 이슈 ID와 걸린 규칙(`policy.checks`) |
| `level` | 차단·조정·확인·경고 |
| `quote`, `ref` | 관련 사용자 원문과 위치 |
| `options` | `확인` 단계일 때 사용자에게 준 선택지 |
| `resolution` | 결과. 사용자가 고른 선택지, 또는 서버가 조정한 값과 조정 전 값 |

`construction`:

| 필드 | 설명 |
|---|---|
| `case` | 네 경우 중 무엇인지. `weight_given`, `etf_given` 두 값으로 표시 |
| `as_of`, `lookback` | 계산 기준일과 기간 |
| `weighting` | 쓴 방식(`HRP` 등) |
| `asset_classes` | 자산군별 계산 과정. 자산군 비중(`budget`), 사용자가 고정한 비중(`fixed`), 후보 범위(`candidates`), 묶음(`clusters`: 묶음에 든 ETF, 고른 대표, 고른 이유), HRP 비중(`hrp`), 비중 표현 반영 후(`after_share`) |
| `limits_applied` | 제한(최대·최소 비중 등) 때문에 바뀐 비중 |
| `result` | 최종 비중. 기준 비중(`base`)이 됨 |
| `stats` | 고른 ETF의 변동성과 서로의 상관계수 |
| `excluded` | 후보에서 뺀 ETF와 이유(데이터 부족, 같은 묶음 등) |

확인 문장에서 "왜 이 종목·비중인지"를 설명하는 재료가 됨.

### portfolio.json — 확정된 포트폴리오

사용자가 확인한 **실제 운용 대상**. 덮어쓰지 않고 바뀔 때마다 `revision`이 올라감.

| 필드 | 설명 |
|---|---|
| `revision`, `prev_revision` | 현재 버전과 이전 버전 |
| `origin` | 이 버전이 어떻게 만들어졌는지. `생성`(초안 확인), `직접수정`, `동적조정`(`adjustment_id`). **변경**: 이전 `제안반영` |
| `stage` | 운용 단계. `백테스트` → `승인` → `모의운용` / `실전운용` |
| `profile` | 목적, 기간. **변경**: 위험 성향을 없앰 |
| `holdings` | 보유 ETF. `base`는 기준 비중, `target`은 목표 비중, `asset_class`는 자산군, `source`(신규)는 `사용자비중`(직접 정함) / `사용자종목`(종목만 정함) / `생성` |
| `rules` | 이 포트폴리오에 적용할 규칙(ETF 최대 비중, 이중 밴드, 동적 조정 한도). 만들 때의 정책 값을 복사해 둠. 나중에 정책이 바뀌어도 이 포트폴리오가 어떤 규칙으로 운용됐는지 남음 |
| `band_state` **(신규)** | 정적 층의 상태. 자산별 최근 밴드 이탈 방향·횟수(반복 이탈 판정용), 기준선 근접으로 밴드 리밸런싱을 보류하기 시작한 날 |
| `backtest` | **변경**: 설정과 결과는 `backtest.json`으로 옮기고, 여기에는 `backtest_id`와 승인 시각(`approved_at`)만 남김 |
| `trading` | 모의·실전투자 설정. 계좌 종류, 주문 방식(장전 동시호가 08:40), 주문 전 점검. 자동 주문 정지 상태는 사용자 단위라 여기 두지 않음([모의·실전투자](trading.md)) |

`trading.pre_order_checks`:

| 필드 | 설명 |
|---|---|
| `max_premium` | ETF 가격이 실제 가치(NAV)보다 1% 넘게 비싸면 주문하지 않음 |
| `skip_halted` | 거래정지 종목은 건너뜀 |
| `check_balance` | 주문 전 잔고 확인 |

### backtest.json — 백테스트 **(신규)**

운용 로직을 **과거 시점으로 옮겨 돌린 결과**. 이전에는 `portfolio.json` 안에 설정만 있었음.

| 필드 | 설명 |
|---|---|
| `backtest_id`, `portfolio_id`, `portfolio_revision` | 어느 포트폴리오의 몇 번째 버전을 돌렸는지 |
| `settings` | 기간, 투자금·적립금, 수수료·슬리피지, 체결 가정, 분배금 재투자, 세금 |
| `settings` 기간 보정 | `requested_start`(요청한 시작일)와 실제 시작일. 사용자가 고른 ETF의 데이터가 부족해 시작일을 늦췄으면 그 이유 |
| `construction` | 백테스트 시작일 기준으로 HRP를 다시 돌린 생성 결과(`draft.construction`과 같은 형식). 미래 정보 누설을 막기 위해 시작일까지의 데이터만 씀. 실제 운용 비중(`portfolio.holdings`)과 다를 수 있어서 결과 화면에 둘을 함께 보여 줌 |
| `excluded_etfs` | 시작일에 데이터가 없어 백테스트에서 뺀 사용자 ETF와 이유 |
| `runs` | 실행 결과 목록. `mode`(`거시판단` / `고정비중`), 성과 지표([백테스트](backtest.md)), 거시판단이면 기간 중 동적 전환 기록(`adjustment_ids`). 고정비중은 동적 층을 끈 비교용 |
| `benchmarks` | 비교 대상 결과. 리밸런싱 안 함, KODEX 200 보유 |
| `llm_used` | 백테스트에서 LLM 판단을 썼는지. 잠정 `false`(지표 신호만) |
| `approved_at` | 사용자가 승인한 시각 |

### market.json — 시장 상태

**국면 지표와 신호, 시장 분위기 판단 결과**. 매일 갱신하고 동적 층의 근거로 씀. 백테스트에서는 과거 시점마다 같은 형식으로 다시 만듦.

| 필드 | 설명 |
|---|---|
| `as_of` | 기준일. 발표일(`released_at`)이 이 날짜 이전인 지표만 씀 |
| `regime.economy` | 경기 상태(좋아짐·꺾임·나쁨)와 근거 지표(경기선행지수 방향, 기준금리, 국고채 금리, 환율, 수출) |
| `regime.sectors` | 업종별 상태(늘어남·줄어듦)와 근거 지표(업종 수출 증감률) |
| `regime.market_model` | 통계 모형(점프모형)이 계산한 상승·하락 확률 |
| `mood` | 시장 분위기(공포·보통·탐욕), 그 상태가 이어진 일수, 근거 지표 |
| `signals` **(신규)** | 국면 신호별 현재 값, 진입·해제 기준, 기준을 넘은 상태가 이어진 일수, 기준선 근접 여부(`near`), 전환 확정 여부. 일간 지표(변동성, 추세, 금리 스프레드, 국면 확률)와 월간 지표(경기·업종)를 함께 담음 |
| `regime_state` **(신규)** | 지금 확정된 국면과 확정일. 전환할 때 LLM이 근거를 확인한 결과(`check`: 판정, 보류 기한 `hold_until`, LLM 출력 ID)도 여기 둠 |

각 상태에 공통으로 있는 필드:

| 필드 | 설명 |
|---|---|
| `state`, `prev_state`, `changed` | 지금 상태, 이전 상태, 바뀌었는지 |
| `indicators` / `indicator` | 근거 지표. 값, 기준 기간, 발표일, 출처 |

**변경**: 상태마다 있던 LLM 근거 확인(`check`)을 `regime_state.check` 하나로 모음. 근거 확인은 개별 지표가 아니라 국면 전환에 대해 함

`mood.indicators`:

| 필드 | 설명 |
|---|---|
| `vkospi_pct_1y` | 변동성 지수(VKOSPI)가 최근 1년 중 어느 위치인지(0~1) |
| `margin_loan_z` | 신용융자(빚내서 투자한 돈)가 평소보다 얼마나 많은지 |
| `deposits_z` | 투자자 예탁금이 평소보다 얼마나 많은지 |
| `news_score_mean` | 뉴스 감성 점수 평균. LLM이 매긴 점수 |
| `theme_count_z` | 특정 테마 뉴스가 평소보다 얼마나 몰렸는지 |

이름 끝의 `_z`는 z점수(평균에서 표준편차 몇 배만큼 떨어졌는지)임.

### adjustment.json — 동적 조정 기록 **(신규, 이전 `suggestion.json`)**

동적 층이 **목표 종목·비중을 자동으로 바꾼 기록**. 모든 포트폴리오에 적용됨. 실운용과 백테스트가 같은 형식을 씀.

**변경**: 이전에는 후보 여러 개(`candidates`)를 내고 사용자가 골랐음(`decision`). 자동 반영으로 바뀌어 둘 다 없앰. 사용자 선택은 백테스트에서 재현할 수 없기 때문.

| 필드 | 설명 |
|---|---|
| `adjustment_id` | 조정 ID |
| `mode` | `실운용` / `백테스트` |
| `portfolio_id`, `portfolio_revision` | 어느 포트폴리오의 몇 번째 버전에서 출발했는지 |
| `trigger_kind` | `신호` / `밴드재평가` / `최소점검일` |
| `signals` | 전환을 일으킨 신호(`market.signals` 중). 밴드재평가면 이탈한 자산과 밴드도 기록 |
| `regime_from`, `regime_to` | 전환 전·후 국면 |
| `market_state_id` | 근거로 쓴 시장 상태 |
| `rules_applied` | 적용한 규칙 목록. `rule_id`, 업종 |
| `changes` | 종목·비중 변경 내용. ETF마다 기준 비중, 이전 목표, 새 목표, 한도로 줄였는지(`limited`). 새로 넣거나 뺀 종목도 여기 |
| `result` | `반영` / `변경없음`(재평가했지만 국면 그대로) / `미반영`(이유: 근거 확인 실패 등) |
| `text`, `llm_output_id` | 사용자에게 알릴 조정 이유 문장. LLM이 작성(`adjustment_text`) |
| `applied_at`, `new_revision` | 반영 시각과 새로 만들어진 포트폴리오 버전 |

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
| `profile` | 목적, 기간(개월), 투자금, 월 적립금, 적립일. 말하지 않은 건 `null` |
| `asset_classes` **(신규)** | 자산군 비중을 말했을 때. 예: "주식 70%" → 주식 0.7 |
| `etfs` | 언급한 ETF의 종목코드와 비중 표현(`share`) 또는 직접 말한 비중(`weight`) |
| `out_of_scope` | 처리할 수 없는 부분과 이유. 서버가 `차단` 이슈로 옮김 |

### evidence_check.json — 상태 변화 근거 확인

국면 전환이 정해졌을 때, 뉴스·문서에 그 변화를 뒷받침하는 내용이 있는지 확인한 결과. 실운용에서만 쓰고, 근거가 부족하면 전환을 보류함.

| 필드 | 설명 |
|---|---|
| `evidence` | 근거 문장 |
| `verdict` | 판정. 예시는 `뒷받침` |

### bok_policy.json — 한국은행 통화정책 해석

한국은행 의사록 등을 읽고 통화정책 방향이 바뀌었는지 판단한 결과. 국면 지표 중 하나로 씀.

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

### adjustment_text.json — 조정 이유 문장 **(변경, 이전 `suggestion_text.json`)**

서버가 계산한 동적 전환 결과에 사용자용 이유 문장을 붙인 결과. 숫자는 서버가 정하고, LLM은 문장만 씀. 결과는 `adjustment.json`의 `text`에 들어감.

**변경**: 후보마다 제목·이유를 쓰던 것에서, 반영된 조정 하나의 이유만 씀.
