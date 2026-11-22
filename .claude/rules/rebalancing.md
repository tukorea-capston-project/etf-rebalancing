---
paths:
  - "backend/app/portfolio/**"
  - "backend/tests/portfolio/**"
---

# 포트폴리오·리밸런싱 규칙

이 폴더를 고치기 전에 `docs/rebalancing.md`를 읽습니다. 포트폴리오 생성(minimax·HRP)은 `docs/strategy-schema.md`, 국면 전환은 `docs/macro.md`를 함께 봅니다. 로직은 그 문서들에만 쓰고, 설계가 바뀌면 그 문서를 고칩니다. 아래는 어기면 사고가 나는 규칙입니다.

- 백테스트와 모의·실전투자는 이 폴더의 같은 로직을 씁니다. 어느 한쪽 전용 로직으로 나누지 않습니다.
