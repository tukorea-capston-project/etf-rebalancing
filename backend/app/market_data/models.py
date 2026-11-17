"""시세·분배금 DB 모델. 설계는 docs/market-data.md."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, Numeric, String
from sqlmodel import Field, SQLModel


class EtfDailyPrice(SQLModel, table=True):
    """ETF 일별 시세 (KRX ETF 일별매매정보). 종가가 있는 행만 저장한다."""

    __tablename__ = "etf_daily_price"  # pyright: ignore[reportAssignmentType]

    trade_date: date = Field(primary_key=True)  # BAS_DD
    code: str = Field(primary_key=True, max_length=6)  # ISU_CD
    name: str  # ISU_NM. 그날의 종목명
    close: int = Field(sa_type=BigInteger)  # TDD_CLSPRC
    change: int | None = Field(default=None, sa_type=BigInteger)  # CMPPREVDD_PRC
    change_rate: Decimal | None = Field(default=None, sa_type=Numeric)  # FLUC_RT
    nav: Decimal | None = Field(default=None, sa_type=Numeric)  # NAV
    open: int | None = Field(default=None, sa_type=BigInteger)  # TDD_OPNPRC
    high: int | None = Field(default=None, sa_type=BigInteger)  # TDD_HGPRC
    low: int | None = Field(default=None, sa_type=BigInteger)  # TDD_LWPRC
    volume: int | None = Field(default=None, sa_type=BigInteger)  # ACC_TRDVOL
    trade_value: int | None = Field(default=None, sa_type=BigInteger)  # ACC_TRDVAL
    market_cap: int | None = Field(default=None, sa_type=BigInteger)  # MKTCAP
    # INVSTASST_NETASST_TOTAMT
    net_assets: int | None = Field(default=None, sa_type=BigInteger)
    listed_shares: int | None = Field(default=None, sa_type=BigInteger)  # LIST_SHRS
    index_name: str | None = None  # IDX_IND_NM
    index_close: Decimal | None = Field(default=None, sa_type=Numeric)  # OBJ_STKPRC_IDX
    index_change: Decimal | None = Field(default=None, sa_type=Numeric)  # CMPPREVDD_IDX
    # FLUC_RT_IDX
    index_change_rate: Decimal | None = Field(default=None, sa_type=Numeric)


class CollectionStatus(StrEnum):
    BUSINESS_DAY = "business_day"  # 종가 있는 행이 왔다
    HOLIDAY = "holiday"  # 종가가 모두 빈 행이 왔거나, 유예 기간이 지난 날짜의 빈 목록
    PENDING = "pending"  # 유예 기간 안의 빈 목록. 아직 제공 전일 수 있어 다시 호출한다
    FAILED = "failed"  # 오류. 다시 호출한다


class PriceCollectionLog(SQLModel, table=True):
    """날짜별 KRX 시세 수집 이력. 영업일 행은 과거 영업일 달력으로도 쓴다."""

    __tablename__ = "price_collection_log"  # pyright: ignore[reportAssignmentType]

    trade_date: date = Field(primary_key=True)
    status: CollectionStatus = Field(sa_type=String)
    saved_rows: int | None = None  # 저장한 대상 ETF 행 수 (영업일만)
    error: str | None = None  # 실패 사유 (실패만)
    checked_at: datetime = Field(sa_type=DateTime(timezone=True))  # 마지막 호출 시각


class EtfBackfill(SQLModel, table=True):
    """ETF별 전 기간 시세 수집 완료 기록. 화이트리스트에 있는데 여기 없으면 신규 ETF다."""

    __tablename__ = "etf_backfill"  # pyright: ignore[reportAssignmentType]

    code: str = Field(primary_key=True, max_length=6)
    completed_at: datetime = Field(sa_type=DateTime(timezone=True))


class DistributionSource(StrEnum):
    YFINANCE = "yfinance"
    OVERRIDE = "override"  # 보정 YAML


class EtfDistribution(SQLModel, table=True):
    """ETF 분배금. yfinance 값 위에 보정 YAML을 덮어 적용한 최종값이다. 2010-01-01 이후만 저장한다."""

    __tablename__ = "etf_distribution"  # pyright: ignore[reportAssignmentType]

    code: str = Field(primary_key=True, max_length=6)
    ex_date: date = Field(primary_key=True)  # 분배락일
    amount: Decimal = Field(sa_type=Numeric)  # 주당 분배금(세전, 원)
    source: DistributionSource = Field(sa_type=String)
