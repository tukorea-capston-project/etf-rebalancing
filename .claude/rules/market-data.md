---
paths:
  - "backend/app/market_data/**"
  - "backend/tests/market_data/**"
  - "backend/config/distribution_overrides.yaml"
---

# 시세·분배금 수집 규칙

상세 설계는 `docs/market-data.md`를 따른다. 로직을 바꾸기 전에 그 문서를 읽고, 설계가 바뀌면 문서도 함께 고친다.

- 저장 대상은 화이트리스트 ETF와 KODEX 200(`069500`)뿐이다.
- 호출한 날짜마다 수집 이력(영업일/휴장일/실패)을 남긴다. 최근 며칠의 빈 응답은 휴장일로 확정하지 않는다.
- 전 기간 수집을 마치지 않은 화이트리스트 ETF가 있으면 모든 영업일을 다시 호출해 채운다.
- 분배금은 매번 yfinance 전체 이력을 받아 갱신하고, 그 위에 보정 YAML을 덮어 적용한다. DB를 직접 고치지 않는다.
- 수집 로직은 `service.py`에 두고 CLI와 (나중의) 스케줄러가 같은 함수를 부른다.
- KRX 하루 호출 한도(10,000회)를 넘으면 멈추고, 다음 실행 때 이어서 받는다.
