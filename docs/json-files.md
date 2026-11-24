# JSON 파일별 설명

`llm_json/`의 상태 파일과 LLM 출력 형식에 어떤 필드가 있는지 설명합니다.
이 문서에는 필드의 뜻만 둡니다. 필드에 담기는 규칙과 수치는 괄호 안의 기준 문서를 따릅니다. 예시 흐름은 [전체 로직 설명](json-flow.md)을 봅니다.

> 예시 JSON의 미정 값은 `null`, 예시 규칙은 `"status": "예시"`로 표시합니다. 예시 JSON의 값이 기준 문서와 다르면 기준 문서가 맞습니다.

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
| `market.json` | 국면 지표([거시판단](macro.md) 국면 지표) | `news_mood`, `bok_policy` | `regime_switch.json` |
| `regime_switch.json` | `market.json`의 국면 변화, `portfolio.json` | - | `portfolio.operation` |

- 모든 상태 파일에 `schema_version`이 있습니다. JSON 구조 자체의 버전입니다
- `catalog_version`, `policy_version`은 그 데이터를 만들 때 쓴 설정 버전입니다. 설정이 바뀌어도 예전 데이터가 어떤 기준으로 만들어졌는지 추적할 수 있습니다

---

## state/

### catalog.json — 선택지 목록(카탈로그)

LLM과 서버가 쓸 수 있는 **값의 목록**을 모아 둔 파일입니다. LLM 출력의 값은 반드시 여기 있는 값 중 하나여야 합니다.

| 필드 | 설명 |
|---|---|
| `version`, `status`, `decided_on` | 카탈로그 버전과 확정 여부 |
| `intents` | 사용자 요청의 종류(의도). 포트폴리오생성, 포트폴리오수정, 단순질문, 범위밖, 부적절 |
| `out_of_scope_reasons` | 처리할 수 없는 요청의 이유. 개별종목, 가상자산, 레버리지인버스 등 |
| `goals` | 투자 목적. 노후, 주택자금, 목돈마련 등 |
| `risk_asset_classes` | 위험자산으로 보는 자산군. 기간 경고에 씁니다([전략 스키마](strategy-schema.md) 이슈 4단계) |
| `slot_sources` | 칸 값의 출처([전략 스키마](strategy-schema.md) 칸과 출처) |
| `issue_levels` | 이슈 심각도([전략 스키마](strategy-schema.md) 이슈 4단계) |
| `rebalance_conditions`, `rebalance_cycles` | 리밸런싱 조건과 주기([전략 스키마](strategy-schema.md) 리밸런싱 조건) |
| `switch_kinds` | 국면 전환의 계기. `정기`, `이벤트`([거시판단](macro.md)) |
| `backtest_modes` | 백테스트 실행 종류([백테스트](backtest.md) 대상) |
| `expressions` | 자주 쓰는 말과 칸 값의 연결. 예: "전세" → `goal`=주택자금 |
| `slot_axes` | 자산군마다 고를 수 있는 지역(`regions`)과 섹터(`sectors`). `null`은 그 계층을 나누지 않음([투자 대상](universe.md) 슬롯 분류) |
| `aliases` | ETF 별칭. 예: "S&P", "미국 주식" → `360750` |
| `questions` | 되묻기와 `확인` 이슈에서 사용자에게 할 질문과 선택지 문구. 리밸런싱 조건(`rebalance`), 투자 금액(`capital`), 비중 충돌(`weight_conflict`) |

### policy.json — 운용 규칙(정책)

시스템이 따르는 **기본값과 규칙**을 JSON으로 옮긴 것입니다.

| 필드 | 설명 |
|---|---|
| `dialog` | 대화 규칙. 질문 횟수, LLM 재시도 횟수, 필수 값(`required_slots`)([전략 스키마](strategy-schema.md) 자연어 → 전략 변환) |
| `defaults` | 사용자가 말하지 않은 값의 기본값. 현금 비중, 밴드 폭, 백테스트 설정(비용·무위험수익률, 실행 종류 `modes`, LLM 지표 사용 `llm_indicators`, 견고성 표 `robustness`, 과최적화 확률 `pbo`) |
| `construction` | 포트폴리오 생성 규칙. 아래 표 참고 |
| `checks` | 이슈 규칙 목록. 규칙마다 `check_id`, `level`, 처리 방식, 사용자 문구 |
| `rebalance` | 정적 층. 조건 목록, 밴드 확인 시점, 밴드 폭 계산, 일자 규칙([리밸런싱](rebalancing.md)) |
| `fixed_rules` | 고정 규칙. 적립금 매수, 분배금 재투자([리밸런싱](rebalancing.md)) |
| `macro` | 동적 층(거시판단 운용). 아래 표 참고 |
| `fear_warning` | 위험회피 국면 때 계획 외 매도 경고([거시판단](macro.md)) |

`defaults.backtest.llm_indicators` ([백테스트](backtest.md) LLM 지표와 미래 정보):

| 필드 | 설명 |
|---|---|
| `use` | 백테스트에서 LLM 지표를 쓰는지 |
| `compare_without` | LLM 지표를 뺀 거시판단도 함께 계산하는지 |
| `without_display` | 뺀 결과를 화면에 보여 주는 방식([화면 설계](frontend.md) 백테스트 결과) |
| `leakage_test` | 미래 정보 시험의 구성과 시험 4의 사건 목록([백테스트](backtest.md) 미래 정보 시험) |

`construction` ([전략 스키마](strategy-schema.md) 포트폴리오 생성):

| 필드 | 설명 |
|---|---|
| `selection` | 묶음별 대표 선택 방식(`minimax`), 탐색 방법(`selection_search`), 같은 기초지수 ETF를 줄이는 기준(`dedupe_same_index`), 동점 처리(`tie_break`)([전략 스키마](strategy-schema.md) 종목 선택 탐색) |
| `weighting` | 비중 계산 방식(`HRP`) |
| `compare_weightings` | 비교용 비중 방식 |
| `scope` | HRP를 적용하는 범위(자산군 안 / 자산군 배분까지) |
| `selection_weeks`, `returns` | 선정 기간 길이(주), 변동성·상관계수에 쓰는 수익률 주기. 투자 대상의 상장 후 경과 기간도 선정 기간과 같습니다 |
| `default_groups` | 기본 묶음 세트 |
| `limits` | 비중 제한(종목당 최대·최소 비중, 최대 종목 수, 최대 묶음 수, 비중 단위) |
| `postprocess` | 후처리 방식(최소 비중 맞추기, 반올림) |
| `regenerate` | HRP를 다시 계산하는 때 |

`macro` ([거시판단](macro.md)):

| 필드 | 설명 |
|---|---|
| `schedule` | 국면 판단 시점 |
| `classifier` | 국면 분류 방식 |
| `zscore_window_weeks`, `change_windows_weeks`, `z_method`, `z_clip` | Z-Score 기준 기간, 변화를 재는 기간, Z-Score 계산 방식, Z-Score를 자르는 값 |
| `indicators` | 국면 지표 목록. 지표마다 축(`axis`), 쓰는 값(`transform`), 방향(`direction`), 출처, LLM 지표 여부(`llm`) |
| `axis_score` | 축 안의 지표를 합치는 방식([거시판단](macro.md) 축 점수) |
| `regimes` | 국면 축과 상태, 축이 바꾸는 ETF 속성 |
| `hysteresis`, `hedge_cost_threshold`, `stock_bond_corr_threshold` | 축 점수, 환헤지 비용, 주식·채권 상관계수의 진입·복귀 기준([거시판단](macro.md) 기준값) |
| `on_switch` | 국면이 바뀌었을 때의 처리. ETF 선택 점수(`RegimeFit − λ·SwitchCost`)와 구성(`lambda`, `rank_scale`, `switch_cost`), 상관 제약(`max_corr_rule`), 위험선호 축을 적용하지 않는 슬롯(`risk_axis_excluded_slots`), ETF 속성과 재는 방법(`etf_attributes`), 비중 재계산, 유지할 사용자 값(`keep_user`)([거시판단](macro.md) 속성 매칭 점수) |
| `events` | 큰 악재·호재 대응 |
| `static_dynamic_priority` | 국면 신호가 기준선 근처일 때 밴드 리밸런싱을 보류할지 |

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
| `asset_classes` | 사용자가 말한 자산군 비중 |
| `cash` | 현금 비중 |
| `groups` | 묶음 목록. 기본 묶음 세트(`기본값`)와 사용자가 넣거나 뺀 묶음(`사용자발화`) |
| `etfs` | ETF 목록. 종목코드, 사용자가 직접 말한 비중(`weight`). 사용자가 지정한 것과 minimax가 고른 것(`생성`)이 함께 있고 출처로 구분합니다 |
| `rebalance` | 리밸런싱 조건(주기·밴드·혼합과 그 값) |

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
| `as_of`, `selection_weeks` | 계산 기준일과 선정 기간 |
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

사용자가 확인한 **실제 운용 대상**입니다. 버전 규칙은 [전략 스키마](strategy-schema.md) 확정, 승인, 버전 관리를 따릅니다.

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
| `trading` | 모의·실전투자 설정. 계좌 종류, 주문 방식, 주문 전 점검([모의·실전투자](trading.md) 주문 실행). 자동 주문 정지 상태는 사용자 단위라 여기 두지 않습니다 |

`trading.pre_order_checks`:

| 필드 | 설명 |
|---|---|
| `max_premium` | NAV 대비 가격 괴리 상한 |
| `skip_halted` | 거래정지 종목을 건너뛸지 |

### backtest.json — 백테스트

운용 로직을 **과거 시점으로 옮겨 돌린 결과**입니다. 가정과 지표는 [백테스트](backtest.md)를 따릅니다.

| 필드 | 설명 |
|---|---|
| `backtest_id`, `portfolio_id`, `portfolio_revision` | 어느 포트폴리오의 몇 번째 버전을 돌렸는지 |
| `settings` | 기간, 투자금·적립금, 리밸런싱 조건, 비용·무위험수익률, 체결 가정, 분배금 재투자, 세금 |
| `construction` | 백테스트 시작일 기준으로 다시 고르고 계산한 생성 결과(`draft.construction`과 같은 형식) |
| `settings.requested_start`, `settings.start_adjusted_reason` | 사용자가 요청한 시작일과, 시작일을 늦췄다면 그 이유([백테스트](backtest.md#슬롯에-후보가-없을-때)) |
| `substitutions` | 시작일에 쓸 수 없던 지정 ETF와 대신 쓴 대용 ETF, 교체일([백테스트](backtest.md#지정-etf를-아직-쓸-수-없을-때)) |
| `macro_active_from` | 거시판단이 작동하기 시작한 날 |
| `runs` | 실행 결과 목록. `mode`(실행 종류), 화면 표시(`display`: 기본 / 토글), 성과 지표, 기간 중 국면 전환 기록(`switch_ids`) |
| `robustness`, `pbo` | 견고성 표(공통 기간, 변형별 지표)와 과최적화 확률·성과 저하·손실 확률([백테스트](backtest.md) 견고성 표, 과최적화 확률) |
| `leakage_test` | LLM 지표의 미래 정보 시험 결과. 시험한 모델·프롬프트 버전과 시험별 값([백테스트](backtest.md) 미래 정보 시험) |
| `approved_at` | 사용자가 승인한 시각 |

### market.json — 시장 상태

**국면 지표와 국면 판단 결과**입니다. 국면 판단일마다 만들고 동적 층의 근거로 씁니다. 백테스트에서는 과거 시점마다 같은 형식으로 다시 만듭니다. 규칙은 [거시판단](macro.md)을 따릅니다.

| 필드 | 설명 |
|---|---|
| `as_of` | 기준일. 날짜(`period`)가 이 날 이하인 지표만 씁니다 |
| `judged_on` | 판단한 날(기준일 다음 영업일 아침). 발표일(`released_at`)이 이 날 판단 전인 지표만 씁니다 |
| `classifier`, `zscore_window_weeks` | 국면 분류 방식과 Z-Score 기준 기간 |
| `indicators` | 지표별 값, Z-Score(`z`), 기준 기간, 발표일, 출처. 범주 지표(금통위 판정)는 Z-Score 대신 점수(`score`)를 둡니다. LLM 지표는 근거가 된 LLM 출력 ID(`llm_output_ids`)도 둡니다 |
| `regimes` | 축별 국면. 지금 상태, 이전 상태, 바뀌었는지, 점수, 진입·복귀 기준 |
| `missing_indicators` | 받지 못해 빼고 판단한 지표([거시판단](macro.md) LLM PC가 꺼져 있을 때) |
| `switched`, `switched_axes` | 이번 판단에서 국면이 바뀌었는지, 바뀐 축 |

### regime_switch.json — 국면 전환 기록

국면이 바뀌어 **목표 종목·비중을 자동으로 다시 정한 기록**입니다. 실운용과 백테스트가 같은 형식을 씁니다. 규칙은 [거시판단](macro.md) 국면 전환을 따릅니다.

| 필드 | 설명 |
|---|---|
| `switch_id` | 전환 ID |
| `mode` | `실운용` / `백테스트` |
| `portfolio_id`, `portfolio_revision` | 어느 포트폴리오의 몇 번째 버전에서 일어났는지 |
| `kind` | `정기` / `이벤트` |
| `market_state_id`, `regime_from`, `regime_to` | 근거로 쓴 시장 상태와 전환 전·후 국면 |
| `crossed` | 기준을 넘은 축 점수와 기여가 큰 지표 순서. 알림에 씁니다 |
| `selections` | 묶음별 ETF 선택. 이전 ETF, 새 ETF, 속성 매칭 점수(`regime_fit`, `switch_cost`, `lambda`), 이유 |
| `kept` | 사용자가 지정해 바꾸지 않은 ETF |
| `weights` | 이전 목표 비중과 HRP로 다시 계산한 새 목표 비중 |
| `notice` | 사용자에게 보낼 알림 문장 |
| `applied_at` | 주문으로 반영한 시각 |

---

## llm/

LLM이 출력하는 JSON 형식입니다. `_record.json`을 뺀 나머지는 LLM이 실제로 내는 **출력 본문**입니다.

LLM 작업은 사용자 문장 해석(`parse_request`), 뉴스 분위기 점수(`news_mood`), 금통위 결정문 판정(`bok_policy`) 세 가지뿐입니다. 종목 선택, 비중 계산, 국면 판단, 규칙 적용, 주문은 서버 코드가 합니다.

모든 출력에 공통 규칙이 있습니다.
- 값은 카탈로그에 있는 것만 씁니다
- 근거는 원문을 그대로 옮긴 `quote`로 남깁니다. 서버가 원문에 그 문장이 실제로 있는지 확인할 수 있습니다
- 입력 문서는 `ref`(`d1`, `d2` …)로 가리킵니다

### _record.json — LLM 호출 기록

모든 LLM 호출을 이 **기록 형식**으로 감싸 저장합니다. 어떤 모델·프롬프트로, 어떤 문서를 보고, 검증을 통과했는지 나중에 추적할 수 있습니다. 다른 파일에서 `llm_output_id`로 가리키는 대상이 이것입니다. 예시는 뉴스 분위기 작업입니다.

| 필드 | 설명 |
|---|---|
| `output_id` | 기록 ID |
| `task` | 작업 종류. 아래 파일 이름 중 하나 |
| `model`, `model_cutoff`, `prompt_version` | 사용한 모델 태그, 모델의 학습 데이터 기준 시점, 프롬프트 버전 |
| `as_of` | 기준일. 이 날짜 이후 정보를 입력으로 쓰지 않았다는 표시 |
| `inputs` | 입력 문서 목록. `ref`, 문서 ID, 발행 시각 |
| `validation` | 형식 검증 결과. 통과 여부, 시도 횟수, 오류 |
| `output` | LLM 출력 본문 |

### parse_request.json — 사용자 요청 해석

사용자 메시지를 칸 단위로 쪼갠 결과입니다. `draft.json`의 `slots`를 채우는 재료입니다. 해석 규칙은 [전략 스키마](strategy-schema.md) 요청 해석을 따릅니다.

| 필드 | 설명 |
|---|---|
| `intent` | 요청 종류 |
| `profile` | 목적, 기간(개월), 투자금, 월 적립금, 적립일. 말하지 않은 건 `null` |
| `asset_classes` | 자산군 비중을 말했을 때. 예: "주식 70%" → 주식 0.7 |
| `cash` | 현금 비중을 말했을 때 |
| `groups` | 넣거나 뺄 묶음 |
| `etfs` | 직접 지정한 ETF의 종목코드와 직접 말한 비중(`weight`) |
| `rebalance` | 리밸런싱 조건을 말했을 때 |
| `out_of_scope` | 처리할 수 없는 부분과 이유. 서버가 `차단` 이슈로 옮깁니다 |

### news_mood.json — 뉴스 분위기 점수

뉴스 헤드라인마다 시장 관련 여부, 감성 점수, 테마를 매긴 결과입니다. `market.json`의 `news_mood` 지표 계산에 쓰입니다([거시판단](macro.md) 뉴스).

| 필드 | 설명 |
|---|---|
| `market_related` | 시장과 관련 있는 뉴스인지. 관련 없으면 점수를 매기지 않습니다 |
| `score` | 감성 점수. 양수는 긍정, 음수는 부정 |
| `theme` | 관련 테마. 없으면 `없음` |

### bok_policy.json — 금통위 결정문 판정

한국은행 금통위 통화정책방향 결정문을 읽고 통화정책 방향이 바뀌었는지 판단한 결과입니다. `market.json`의 `bok_statement` 지표로 씁니다([거시판단](macro.md)).

| 필드 | 설명 |
|---|---|
| `evidence` | 근거 문장 |
| `policy_shift` | 정책 변화 여부. 예시는 `안바뀜` |
| `direction` | 바뀌었다면 방향. 안 바뀌었으면 `null` |
