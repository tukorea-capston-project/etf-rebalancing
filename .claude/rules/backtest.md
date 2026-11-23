---
paths:
  - "backend/app/backtest/**"
  - "backend/tests/backtest/**"
---

# 백테스트 규칙

이 폴더를 고치기 전에 `docs/backtest.md`를 읽습니다. 투자 대상은 `docs/universe.md`, 거시판단은 `docs/macro.md`를 함께 봅니다. 로직은 그 문서들에만 쓰고, 설계가 바뀌면 그 문서를 고칩니다. 아래는 어기면 사고가 나는 규칙입니다.

- 오늘 기준 ETF 목록으로 과거를 돌리지 않습니다. 후보는 선정 시점마다 그날 상장돼 있던 ETF 전체에서 만듭니다(생존 편향).
- 가격은 KRX 비수정 종가만 씁니다. 수정주가(FinanceDataReader 가격, yfinance `Adj Close`)와 섞지 않습니다. 분배금이 두 번 반영됩니다.
- 수수료·슬리피지는 `backend/config/backtest.yaml`에서 읽고, 무위험수익률은 수집한 CD금리로 계산합니다. 코드에 숫자를 넣지 않습니다.
- 리밸런싱 판단과 주문 수량은 `backend/app/portfolio/`의 로직을 그대로 씁니다. 백테스트용으로 따로 만들지 않습니다.
- 국면 판단의 임계값·히스테리시스 폭을 백테스트 결과를 보고 고르거나 고치지 않습니다(과최적화).
