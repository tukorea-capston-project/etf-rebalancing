# JSON 파일별 설명

전체 흐름과 개념(칸, 묶음, 이슈, minimax·HRP, 정적 층·동적 층 등)은 [전체 로직 설명](json-flow.md)을 참고합니다.

> 예시 JSON의 미정 값은 `null`, 예시 규칙은 `"status": "예시"`로 표시합니다. 이전 구조(이중 밴드, 경기·업종 레짐, 동적 조정 규칙)에서 바뀐 부분은 각 파일의 **변경** 표시로 적어 둡니다.

## 폴더 구성

| 폴더 | 내용 |
|---|---|
| `llm_json/state/` | 서버가 저장하고 계속 갱신하는 상태. 설정, 사용자 요청 초안, 포트폴리오, 시장 상태, 백테스트, 국면 전환 기록 |
| `llm_json/llm/` | LLM이 돌려주는 출력 형식. LLM은 정해진 형식의 JSON만 내야 하고, 서버가 검증한 뒤 사용합니다 |

## 파일 간 연결

| 파일 | 만드는 재료 | LLM 출력 | 다음으로 가는 곳 |
|---|---|---|---|
| `catalog.json`, `policy.json` | 저장소 설정 | - | `draft.json` |
| `draft.json` | 사용자 메시지, 되묻기 답변, 카탈로그, 정책 | `parse_request` | `portfolio.json` |
| `portfolio.json` | 확인된 `draft.json`, 국면 전환 결과(`operation`) | - | `backtest.json` |
| `backtest.json` | `portfolio.json`, 과거 시세, 과거 시점의 `market.json` | - | `portfolio.json` (승인) |
| `market.json` | 국면 지표(금리, 환율, VKOSPI, 신용융자, 예탁금, 뉴스 분위기, 금통위 판정) | `news_mood`, `bok_policy` | `regime_switch.json` |
| `regime_switch.json` | `market.json`의 국면 변화, `portfolio.json` | - | `portfolio.operation` |

- 모든 상태 파일에 `schema_version`이 있습니다. JSON 구조 자체의 버전입니다
- `catalog_version`, `policy_version`은 그 데이터를 만들 때 쓴 설정 버전입니다. 설정이 바뀌어도 예전 데이터가 어떤 기준으로 만들어졌는지 추적할 수 있습니다

---

## state/

### catalog.json — 선택지 목록(카탈로그)

LLM과 서버가 쓸 수 있는 **값의 목록**을 모아 둔 파일입니다. LLM 출력의 값은 반드시 여기 있는 값 중 하나여야 합니다.

| 필드 | 설명 |
|---|---|
| `version`, `status`, `decided_on` | 카탈로그 버전과 확정 여부. 지금은 `초안` |
| `intents` | 사용자 요청의 종류(의도). 포트폴리오생성, 포트폴리오수정, 단순질문, 범위밖, 부적절 |
| `out_of_scope_reasons` | 처리할 수 없는 요청의 이유. 개별종목, 가상자산, 레버리지인버스 등 |
| `goals` | 투자 목적. 노후, 주택자금, 목돈마련 등 |
| `risk_asset_classes` | 위험자산으로 보는 자산군. 주식, 원자재, 리츠. 기간 경고에 씁니다 |
| `slot_sources` | 칸 값의 출처. 사용자발화, 질문답변, 생성, 기본값 |
| `issue_levels` | 이슈 심각도. 차단, 조정, 확인, 경고 |
| `rebalance_conditions`, `rebalance_cycles` | 리밸런싱 조건(주기·밴드·혼합)과 주기(월·분기·반기·연) |
| `switch_kinds` | 국면 전환의 계기. `정기`(매주 국면 판단), `이벤트`(큰 악재·호재, 미정) |
| `backtest_modes` | 백테스트 실행 종류. `고정비중`, `거시판단`, `거시판단LLM제외`(토글로만 보여 줌) |
| `expressions` | 자주 쓰는 말과 칸 값의 연결. 예: "전세" → `goal`=주택자금 |
| `whitelist` | 투자 가능한 ETF 목록(화이트리스트) 파일 위치. 선정 조건으로 전환하기 전까지 씁니다 |
| `categories` | ETF 분류(category)가 어느 자산군(asset_class)에 속하는지 |
| `aliases` | ETF 별칭. 예: "S&P", "미국 주식" → `360750`. 묶음을 자연어로 찾는 방법, "현금"을 현금 비중으로 볼지는 미정입니다 |
| `questions` | 되묻기와 `확인` 이슈에서 사용자에게 할 질문과 선택지 문구. 리밸런싱 조건(`rebalance`)과 투자 금액(`capital`)의 문구·선택지는 미정, 비중 충돌(`weight_conflict`) |

**변경**: 비중 표현(`shares`, "조금만"·"많이" 등의 `expressions`)을 없앴습니다. 동적 전환 계기(`trigger_kinds`)를 `switch_kinds`로 바꿨습니다. 리밸런싱 조건 목록을 다시 두고, 되묻기 질문 자리를 추가했습니다.

### policy.json — 운용 규칙(정책)

시스템이 따르는 **기본값과 규칙**입니다. 숫자 기준은 전부 여기 있습니다.

| 필드 | 설명 |
|---|---|
| `dialog` | 대화 규칙. 질문 최대 3회, LLM 재시도 최대 2회, 필수 값(`required_slots`: 투자금, 리밸런싱 조건) |
| `defaults` | 사용자가 말하지 않은 값의 기본값. 현금 0%, 밴드 폭 5%p / 25%, 백테스트 설정(수수료·슬리피지·무위험수익률, 실행 종류 `modes`, LLM 지표 사용 `llm_indicators`) |
| `construction` | 포트폴리오 생성 규칙. 아래 표 참고 |
| `checks` | 이슈 규칙 목록. 규칙마다 `check_id`, `level`(차단·조정·확인·경고), 처리 방식, 사용자 문구 |
| `rebalance` | 정적 층. 조건 목록, 밴드 확인 시점(매주 마지막 영업일), 밴드 폭 계산(절대·상대 중 좁은 쪽), 일자 규칙 |
| `fixed_rules` | 고정 규칙. 적립금은 부족한 자산부터 매수, 분배금은 같은 ETF에 재투자 |
| `macro` | 동적 층(거시판단 운용). 아래 표 참고 |
| `fear_warning` | 투자심리가 공포일 때 계획 외 매도(전략 중지, 직접 비중 축소)에 경고 |

**변경**: 기본 자산군 비중(`defaults.asset_classes`, 60/40)을 없앴습니다. 비중을 말하지 않으면 HRP가 정합니다. 이중 밴드(`inner_band`, `outer_band`, `repeat_breach`)를 사용자가 고르는 조건으로 바꿨습니다. `dynamic`을 `macro`로 바꾸고, 경기·업종 레짐(`regime`), 시장 분위기(`mood`), 동적 조정 규칙(`adjustments`)과 한도(`limit`), 최소 점검일(`min_check`), 근접 구간(`near_threshold`)을 없앴습니다. 백테스트 비교 대상(`benchmarks`)을 없앴습니다.

`defaults.backtest.llm_indicators`:

| 필드 | 설명 |
|---|---|
| `use` | 백테스트에서도 LLM 지표를 씁니다(`true`) |
| `compare_without` | LLM 지표를 뺀 거시판단도 항상 함께 계산합니다 |
| `without_display` | 뺀 결과는 화면에서 토글을 켰을 때만 보여 줍니다 |
| `leakage_test` | 미래 정보가 섞였는지 시험하는 방법. 미정 |

`construction`:

| 필드 | 설명 |
|---|---|
| `selection` | 묶음별 대표 선택 방식. `minimax`(대표들 간 최대 상관계수가 가장 작은 조합). 탐색 방법(`selection_search`)은 미정 |
| `weighting` | 비중 계산 방식. `HRP` |
| `compare_weightings` | 비교용 비중 방식. `역변동성`, `동일비중` |
| `scope` | 사용자가 자산군 비중을 줬으면 자산군 안에서만, 안 줬으면 자산군 배분까지 HRP |
| `selection_days`, `min_history_days` | 선정 기간 길이, 후보가 되려면 필요한 최소 데이터 기간. 미정 |
| `default_groups` | 기본 묶음 세트(예시). 사용자 문장의 묶음을 더하거나 뺍니다 |
| `limits` | ETF 하나 최대 50%(잠정)·최소 5%, 최대 10개, 묶음 최대 10개, 1% 단위 |
| `postprocess` | 5% 미만은 5%로 올리고 나머지 비례 축소, 최대잔여법 반올림 |
| `regenerate` | HRP를 다시 계산하는 때. 생성, 국면 전환 |

**변경**: 비중 표현 배수(`share_multipliers`), 변동성·거래량 기준 대표 선택(`representative`)을 없앴습니다.

`macro` (동적 층):

| 필드 | 설명 |
|---|---|
| `schedule` | 국면 판단 시점. 매주 마지막 영업일 종가 |
| `classifier` | 국면 분류 방식. Z-Score 점수제. 확장 과제는 HMM |
| `zscore_window_days` | Z-Score 기준 기간. 미정 |
| `indicators` | 국면 지표 목록. 지표마다 출처와 LLM 지표 여부(`llm`). LLM 지표는 `거시판단LLM제외` 백테스트에서 뺍니다 |
| `regimes` | 국면 축과 상태(예시). 금리 상승/하락, 환율 과열/안정, 고변동/저변동, 투자심리 공포/탐욕 |
| `hysteresis` | 진입·복귀 기준. 미정. 잦은 전환은 이것으로만 막습니다 |
| `on_switch` | 국면이 바뀌었을 때. 묶음별 속성 매칭 점수(`RegimeFit − λ·SwitchCost`)로 ETF 선택, HRP로 비중 재계산, 사용자 지정 값(`keep_user`)은 유지 |
| `events` | 큰 악재·호재 대응. 미정 |
| `static_dynamic_priority` | 국면 신호가 기준선 근처일 때 밴드 리밸런싱을 보류할지. 미정 |

### draft.json — 포트폴리오 초안

사용자와 대화하며 채워 가는 **작성 중인 포트폴리오**입니다. 사용자가 확인하면 `portfolio.json`이 됩니다.

| 필드 | 설명 |
|---|---|
| `status` | 초안 상태. 예시는 `확인대기`(사용자 확인 기다리는 중) |
| `base_portfolio_id` | 기존 포트폴리오 수정이면 원래 포트폴리오 ID. 새로 만들면 `null` |
| `question_rounds` | 지금까지 질문한 횟수 |
| `turns` | 사용자가 보낸 메시지 기록. 각 메시지를 해석한 LLM 출력 ID(`llm_output_id`)를 함께 저장합니다 |
| `slots` | 채워진 칸 전체. 아래 표 참고 |
| `questions` | 되묻기와 `확인` 이슈로 사용자에게 한 질문과 답변 |
| `issues` | 규칙에 어긋난 부분. 아래 표 참고 |
| `construction` | 생성 결과. 아래 표 참고 |
| `confirm_text` | 사용자에게 보여 줄 확인 문장 |

`slots`:

| 필드 | 설명 |
|---|---|
| `intent` | 요청 종류 |
| `profile` | 목적, 기간, 투자금, 월 적립금, 적립일 |
| `asset_classes` | 사용자가 말한 자산군 비중. 비어 있으면 HRP가 정합니다 |
| `cash` | 현금 비중. 말하지 않으면 `기본값` 0% |
| `groups` | 묶음 목록. 기본 묶음 세트(`기본값`)와 사용자가 넣거나 뺀 묶음(`사용자발화`) |
| `etfs` | ETF 목록. 종목코드, 사용자가 직접 말한 비중(`weight`). 사용자가 지정한 것과 minimax가 고른 것(`생성`)이 함께 있고 출처로 구분합니다 |
| `rebalance` | 리밸런싱 조건(주기·밴드·혼합과 그 값). 필수 값이라 비면 되묻습니다 |

**변경**: 기본 자산군 비중 대신 HRP가 정하므로 `asset_classes`는 사용자가 말한 것만 담습니다. `cash`, `groups`, `rebalance`를 추가하고 `etfs`의 비중 표현(`share`)을 없앴습니다.

칸 하나는 다음 필드로 이루어집니다. 예시는 "2년 뒤에" → 기간 24개월입니다.

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
| `case` | 네 경우 중 무엇인지. `weight_given`, `etf_given` 두 값으로 표시합니다 |
| `as_of`, `selection_days` | 계산 기준일과 선정 기간 |
| `selection`, `weighting` | 쓴 방식(`minimax`, `HRP`) |
| `groups` | 묶음별 계산 과정. 사용자가 고정한 ETF(`fixed`), 후보(`candidates`), 고른 대표(`representative`) |
| `minimax` | 고른 조합에서 가장 높은 상관계수와 그 쌍 |
| `hrp` | HRP 비중 |
| `limits_applied` | 제한(최대·최소 비중 등) 때문에 바뀐 비중 |
| `result` | 최종 비중. 전략 비중(`base`)이 됩니다 |
| `stats` | 고른 ETF의 변동성과 서로의 상관계수 |
| `excluded` | 후보에서 뺀 ETF와 이유(데이터 부족 등) |

확인 문장에서 "왜 이 종목·비중인지"를 설명하는 재료가 됩니다.

### portfolio.json — 확정된 포트폴리오

사용자가 확인한 **실제 운용 대상**입니다. 사용자가 확인하거나 직접 수정할 때만 `revision`이 올라갑니다.

| 필드 | 설명 |
|---|---|
| `revision`, `prev_revision` | 현재 버전과 이전 버전 |
| `origin` | 이 버전이 어떻게 만들어졌는지. `생성`(초안 확인), `직접수정` |
| `stage` | 운용 단계. `백테스트` → `승인` → `모의운용` / `실전운용` |
| `profile` | 목적, 기간 |
| `cash` | 현금의 전략 비중과 출처 |
| `holdings` | 보유 ETF. `base`는 전략 비중, `group`은 묶음, `source`는 `사용자비중`(직접 정함) / `사용자종목`(종목만 정함) / `생성` |
| `rules` | 이 포트폴리오에 적용할 규칙. 사용자가 고른 리밸런싱 조건(`rebalance`), 비중 제한, 국면 전환에서 지킬 사용자 값(`keep_user`) |
| `operation` | 운용 상태. 지금 국면, 국면 시작일, 현재 목표 비중(`target`, `target_cash`), 전환 기록 ID, 거시판단 작동 여부 |
| `backtest` | `backtest_id`와 승인 시각(`approved_at`) |
| `trading` | 모의·실전투자 설정. 계좌 종류, 주문 방식(잠정: 장전 동시호가 08:40, 최소 1만원), 주문 전 점검. 자동 주문 정지 상태는 사용자 단위라 여기 두지 않습니다([모의·실전투자](trading.md)) |

**변경**: 국면 전환이 새 `revision`을 만들지 않습니다(이전 `origin`: `동적조정`을 없앰). `holdings.target`을 `operation.target`으로 옮겼습니다. 이중 밴드·동적 조정 한도 규칙과 `band_state`를 없앴습니다.

`trading.pre_order_checks`:

| 필드 | 설명 |
|---|---|
| `max_premium` | ETF 가격이 실제 가치(NAV)보다 1% 넘게 비싸면 주문하지 않습니다 |
| `skip_halted` | 거래정지 종목은 건너뜁니다 |
| `check_balance` | 주문 전 잔고 확인 |

### backtest.json — 백테스트

운용 로직을 **과거 시점으로 옮겨 돌린 결과**입니다.

| 필드 | 설명 |
|---|---|
| `backtest_id`, `portfolio_id`, `portfolio_revision` | 어느 포트폴리오의 몇 번째 버전을 돌렸는지 |
| `settings` | 기간, 투자금·적립금, 리밸런싱 조건, 수수료·슬리피지·무위험수익률, 체결 가정, 분배금 재투자, 세금 |
| `construction` | 백테스트 시작일 기준으로 다시 고르고 계산한 생성 결과(`draft.construction`과 같은 형식). 시작일까지의 데이터(선정 기간)만 씁니다. 실제 운용 비중(`portfolio.holdings`)과 다를 수 있어서 결과 화면에 둘을 함께 보여 줍니다 |
| `excluded_etfs` | 시작일에 데이터가 없어 뺀 사용자 ETF. 처리 방식은 미정 |
| `macro_active_from` | 거시판단이 작동하기 시작한 날. 그 전은 국면 지표가 모자라 고정비중과 똑같이 돌립니다 |
| `runs` | 실행 결과 목록. `mode`(`고정비중` / `거시판단` / `거시판단LLM제외`), 화면 표시(`display`: 기본 / 토글), 성과 지표([백테스트](backtest.md)), 기간 중 국면 전환 기록(`switch_ids`) |
| `leakage_test` | LLM 지표의 미래 정보 시험 결과. 설계 미정 |
| `approved_at` | 사용자가 승인한 시각 |

**변경**: 비교 대상(`benchmarks`: 리밸런싱 안 함, KODEX 200 보유)과 `llm_used`를 없앴습니다. LLM 지표는 항상 쓰고, 뺀 결과를 `거시판단LLM제외` 실행으로 함께 계산합니다.

### market.json — 시장 상태

**국면 지표와 국면 판단 결과**입니다. 매주 마지막 영업일에 만들고 동적 층의 근거로 씁니다. 백테스트에서는 과거 시점마다 같은 형식으로 다시 만듭니다.

| 필드 | 설명 |
|---|---|
| `as_of` | 기준일. 발표일(`released_at`)이 이 날짜 이전인 지표만 씁니다 |
| `classifier`, `zscore_window_days` | 국면 분류 방식과 Z-Score 기준 기간 |
| `indicators` | 지표별 값, Z-Score(`z`), 기준 기간, 발표일, 출처. LLM 지표는 근거가 된 LLM 출력 ID(`llm_output_ids`)도 둡니다 |
| `regimes` | 축별 국면. 지금 상태, 이전 상태, 바뀌었는지, 점수, 진입·복귀 기준 |
| `switched`, `switched_axes` | 이번 판단에서 국면이 바뀌었는지, 바뀐 축 |

**변경**: 경기·업종 레짐(`regime.economy`, `regime.sectors`), 점프모형(`market_model`), 시장 분위기(`mood`), 신호(`signals`), LLM 근거 확인(`regime_state.check`)을 없애고, 지표별 Z-Score와 축별 국면으로 바꿨습니다.

### regime_switch.json — 국면 전환 기록 **(변경, 이전 `adjustment.json`)**

국면이 바뀌어 **목표 종목·비중을 자동으로 다시 정한 기록**입니다. 실운용과 백테스트가 같은 형식을 씁니다.

| 필드 | 설명 |
|---|---|
| `switch_id` | 전환 ID |
| `mode` | `실운용` / `백테스트` |
| `portfolio_id`, `portfolio_revision` | 어느 포트폴리오의 몇 번째 버전에서 일어났는지 |
| `kind` | `정기` / `이벤트` |
| `market_state_id`, `regime_from`, `regime_to` | 근거로 쓴 시장 상태와 전환 전·후 국면 |
| `crossed` | 기준을 넘은 지표. 알림에 씁니다 |
| `selections` | 묶음별 ETF 선택. 이전 ETF, 새 ETF, 속성 매칭 점수(`regime_fit`, `switch_cost`, `lambda`, 미정), 이유 |
| `kept` | 사용자가 지정해 바꾸지 않은 ETF |
| `weights` | 이전 목표 비중과 HRP로 다시 계산한 새 목표 비중 |
| `notice` | 사용자에게 보낼 알림 문장. LLM이 쓰지 않습니다(만드는 방식은 미정) |
| `applied_at` | 주문으로 반영한 시각 |

**변경**: 이전에는 국면별 규칙(`rules_applied`)으로 비중을 ±%p 조정하고 한도(`limited`)를 확인했습니다. 묶음별 ETF 선택 + HRP 재계산으로 바뀌었습니다. 조정 이유 문장을 LLM이 쓰던 것(`text`, `llm_output_id`)을 없애고, LLM이 쓰지 않는 알림 문장(`notice`)으로 바꿨습니다. 포트폴리오 새 버전(`new_revision`)을 만들지 않습니다.

---

## llm/

LLM이 출력하는 JSON 형식입니다. `_record.json`을 뺀 나머지는 LLM이 실제로 내는 **출력 본문**입니다.

모든 출력에 공통 규칙이 있습니다.
- 값은 카탈로그에 있는 것만 씁니다
- 근거는 원문을 그대로 옮긴 `quote`로 남깁니다. 서버가 원문에 그 문장이 실제로 있는지 확인할 수 있습니다
- 입력 문서는 `ref`(`d1`, `d2` …)로 가리킵니다

**변경**: `evidence_check.json`(국면 전환 근거 확인)과 `adjustment_text.json`(조정 이유 문장)을 없앴습니다. LLM은 사용자 문장 해석, 뉴스 분위기 점수, 금통위 의사록 판정만 맡습니다.

### _record.json — LLM 호출 기록

LLM 출력 하나를 저장할 때 감싸는 **기록 형식**입니다. 다른 파일에서 `llm_output_id`로 가리키는 대상이 이것입니다. 예시는 뉴스 분위기 작업입니다.

| 필드 | 설명 |
|---|---|
| `output_id` | 기록 ID |
| `task` | 작업 종류. 아래 파일 이름 중 하나 |
| `model`, `model_cutoff`, `prompt_version` | 사용한 모델(`qwen3:8b`), 모델의 학습 데이터 기준 시점, 프롬프트 버전 |
| `as_of` | 기준일. 이 날짜 이후 정보를 입력으로 쓰지 않았다는 표시 |
| `inputs` | 입력 문서 목록. `ref`, 문서 ID, 발행 시각 |
| `validation` | 형식 검증 결과. 통과 여부, 시도 횟수, 오류 |
| `output` | LLM 출력 본문 |

### parse_request.json — 사용자 요청 해석

사용자 메시지를 칸 단위로 쪼갠 결과입니다. `draft.json`의 `slots`를 채우는 재료입니다.

| 필드 | 설명 |
|---|---|
| `intent` | 요청 종류 |
| `profile` | 목적, 기간(개월), 투자금, 월 적립금, 적립일. 말하지 않은 건 `null` |
| `asset_classes` | 자산군 비중을 말했을 때. 예: "주식 70%" → 주식 0.7 |
| `cash` | 현금 비중을 말했을 때 |
| `groups` | 넣거나 뺄 묶음. 묶음을 자연어로 찾는 방법은 미정 |
| `etfs` | 직접 지정한 ETF의 종목코드와 직접 말한 비중(`weight`) |
| `rebalance` | 리밸런싱 조건을 말했을 때 |
| `out_of_scope` | 처리할 수 없는 부분과 이유. 서버가 `차단` 이슈로 옮깁니다 |

**변경**: `etfs`의 비중 표현(`share`)을 없애고 `cash`, `groups`, `rebalance`를 추가했습니다.

### news_mood.json — 뉴스 분위기 점수

뉴스 헤드라인마다 시장 관련 여부, 감성 점수, 테마를 매긴 결과입니다. `market.json`의 `news_mood` 지표 계산에 쓰입니다. 백테스트에서도 씁니다.

| 필드 | 설명 |
|---|---|
| `market_related` | 시장과 관련 있는 뉴스인지. 관련 없으면 점수를 매기지 않습니다 |
| `score` | 감성 점수. 양수는 긍정, 음수는 부정 |
| `theme` | 관련 테마. 없으면 `없음` |

### bok_policy.json — 금통위 의사록 판정

한국은행 금통위 의사록을 읽고 통화정책 방향이 바뀌었는지 판단한 결과입니다. `market.json`의 `bok_minutes` 지표로 씁니다. 백테스트에서도 씁니다.

| 필드 | 설명 |
|---|---|
| `evidence` | 근거 문장 |
| `policy_shift` | 정책 변화 여부. 예시는 `안바뀜` |
| `direction` | 바뀌었다면 방향. 안 바뀌었으면 `null` |
