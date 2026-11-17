from fastapi import FastAPI

from app.core.config import get_settings

# 시작 시 설정을 읽어, 실전 스위치와 암호화 마스터키 설정이 맞지 않으면 여기서 바로 실패한다.
get_settings()

app = FastAPI(title="ETF 리밸런싱 시스템")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
