# 模組完整程式碼 — Part 1-5

本批次收錄：核心層、數據層、回測層、風控層、因子層，共 22 個模組。

---

# Part 1：核心層

## 1.1 `app/config.py`

**職責**：集中管理環境變數與預設參數。

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "TW/US Invest OS"

    finmind_token: str | None = None

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"

    # 台股費用
    default_tw_fee_rate: float = 0.001425
    default_tw_fee_discount: float = 0.6
    default_tw_min_fee: float = 20.0
    default_tw_tax_rate_sell: float = 0.003

    # 美股費用
    default_us_sec_fee_rate: float = 0.0000278
    default_us_finra_taf_per_share: float = 0.000166
    default_us_commission: float = 0.0


settings = Settings()
```

---

## 1.2 `app/domain/models.py`

**職責**：定義所有核心資料模型（Pydantic v2）。

```python
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Market(str, Enum):
    TW = "TW"
    US = "US"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Bar(BaseModel):
    symbol: str
    market: Market
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class NewsItem(BaseModel):
    title: str
    summary: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    source: str | None = None


class AnalystReport(BaseModel):
    role: str
    symbol: str = ""
    market: Market | None = None
    summary: str = ""
    score: float = 0.0
    key_points: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class DebateResult(BaseModel):
    bull_case: str = ""
    bear_case: str = ""
    rounds: list[dict] = Field(default_factory=list)


class RiskReview(BaseModel):
    max_position_pct: float = 0.1
    stop_loss_pct: float = 0.08
    take_profit_pct: float = 0.2
    approved: bool = False
    notes: str = ""


class FinalDecision(BaseModel):
    symbol: str
    market: Market
    action: Literal["BUY", "HOLD", "SELL", "AVOID"] = "HOLD"
    confidence: float = 0.0
    target_position_pct: float = 0.0
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    thesis: str = ""
    reports: list[AnalystReport] = Field(default_factory=list)
    debate: DebateResult | None = None
    risk: RiskReview | None = None
```

---

## 1.3 `app/markets/base.py`

**職責**：市場規則抽象基類。

```python
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from app.domain.models import Market, Side


class MarketRules(ABC):
    market: Market
    settlement_days: int
    price_limit_pct: float | None
    lot_size: int = 1

    @abstractmethod
    def calc_fees(self, side: Side, price: float, qty: int) -> float:
        ...

    @abstractmethod
    def price_limits(self, prev_close: float):
        ...

    def settlement_date(self, trade_date: datetime) -> datetime:
        return trade_date + timedelta(days=self.settlement_days)

    def round_lot(self, qty: int) -> int:
        if qty <= 0:
            return 0
        if self.lot_size <= 1:
            return int(qty)
        return (int(qty) // self.lot_size) * self.lot_size

    def can_execute(self, side: Side, price: float, prev_close: float | None) -> bool:
        if self.price_limit_pct is None or prev_close is None or prev_close <= 0:
            return True

        upper, lower = self.price_limits(prev_close)

        if side == Side.BUY and upper is not None and price > upper:
            return False
        if side == Side.SELL and lower is not None and price < lower:
            return False
        return True
```

**修復記錄**：第 3 輪加入 `qty <= 0` 邊界與 `prev_close <= 0` 檢查。

---

## 1.4 `app/markets/taiwan.py`

**職責**：台股市場規則（T+2 / ±10% / tick 對齊）。

```python
from app.config import settings
from app.domain.models import Market, Side
from app.markets.base import MarketRules


def _tick_size(price: float) -> float:
    """台股升降單位。"""
    if price < 10:
        return 0.01
    if price < 50:
        return 0.05
    if price < 100:
        return 0.1
    if price < 500:
        return 0.5
    if price < 1000:
        return 1.0
    return 5.0


class TaiwanRules(MarketRules):
    market = Market.TW
    settlement_days = 2
    price_limit_pct = 0.10
    lot_size = 1

    def calc_fees(self, side: Side, price: float, qty: int) -> float:
        gross = price * qty
        fee = gross * settings.default_tw_fee_rate * settings.default_tw_fee_discount
        fee = max(fee, settings.default_tw_min_fee)
        tax = gross * settings.default_tw_tax_rate_sell if side == Side.SELL else 0.0
        return round(fee + tax, 2)

    def price_limits(self, prev_close: float) -> tuple[float, float]:
        raw_upper = prev_close * (1 + self.price_limit_pct)
        raw_lower = prev_close * (1 - self.price_limit_pct)
        upper = self._ceil_tick(raw_upper)
        lower = self._floor_tick(raw_lower)
        return upper, lower

    @staticmethod
    def _ceil_tick(price: float) -> float:
        import math
        tick = _tick_size(price)
        return round(math.ceil(price / tick) * tick, 4)

    @staticmethod
    def _floor_tick(price: float) -> float:
        import math
        tick = _tick_size(price)
        return round(math.floor(price / tick) * tick, 4)
```

**修復記錄**：第 3 輪改用 tick 對齊規則（原本用 `round(x, 2)`）。

---

## 1.5 `app/markets/us.py`

**職責**：美股市場規則（T+1 / 無漲跌幅）。

```python
from app.config import settings
from app.domain.models import Market, Side
from app.markets.base import MarketRules


class USRules(MarketRules):
    market = Market.US
    settlement_days = 1
    price_limit_pct = None
    lot_size = 1

    def calc_fees(self, side: Side, price: float, qty: int) -> float:
        commission = settings.default_us_commission
        sec_fee = (
            price * qty * settings.default_us_sec_fee_rate
            if side == Side.SELL else 0.0
        )
        finra_taf = (
            qty * settings.default_us_finra_taf_per_share
            if side == Side.SELL else 0.0
        )
        finra_taf = min(finra_taf, 8.30)
        return round(commission + sec_fee + finra_taf, 4)

    def price_limits(self, prev_close: float):
        return None, None
```

**修復記錄**：第 3 輪加入 FINRA TAF $8.30 上限。

---

## 1.6 `app/markets/registry.py`

**職責**：市場規則查找。

```python
from app.domain.models import Market
from app.markets.taiwan import TaiwanRules
from app.markets.us import USRules

RULES = {
    Market.TW: TaiwanRules(),
    Market.US: USRules(),
}


def get_rules(market: Market):
    return RULES[market]
```

---

# Part 2：數據層

## 2.1 `app/data/base.py`

**職責**：數據提供者抽象基類。

```python
from abc import ABC, abstractmethod

import pandas as pd

from app.domain.models import Market, NewsItem


class DataProvider(ABC):
    @abstractmethod
    async def get_bars(
        self,
        symbol: str,
        market: Market,
        start: str,
        end: str,
        interval: str = "1d",
    ) -> pd.DataFrame:
        ...

    @abstractmethod
    async def get_fundamentals(self, symbol: str, market: Market) -> dict:
        ...

    @abstractmethod
    async def get_news(self, symbol: str, market: Market, limit: int = 20) -> list[NewsItem]:
        ...
```

---

## 2.2 `app/data/warehouse.py`

**職責**：DuckDB + Parquet 本地數據倉庫。

```python
import os
from pathlib import Path

import duckdb
import pandas as pd

from app.domain.models import Market

DATA_ROOT = Path(os.getenv("DATA_ROOT", "./data_lake"))
PARQUET_DIR = DATA_ROOT / "parquet"
DB_PATH = DATA_ROOT / "market.duckdb"


def _market_str(market) -> str:
    if isinstance(market, Market):
        return market.value
    return str(market)


class MarketWarehouse:
    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        PARQUET_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(self.db_path)

    def _ensure_tables(self):
        with self._conn() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS bars (
                    symbol VARCHAR, market VARCHAR, timestamp TIMESTAMP,
                    open DOUBLE, high DOUBLE, low DOUBLE,
                    close DOUBLE, volume DOUBLE
                );
            """)
            con.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_bars_unique
                ON bars (symbol, market, timestamp);
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS tw_chips (
                    symbol VARCHAR, date DATE,
                    foreign_buy DOUBLE, foreign_sell DOUBLE, foreign_net DOUBLE,
                    trust_buy DOUBLE, trust_sell DOUBLE, trust_net DOUBLE,
                    dealer_net DOUBLE, margin_balance DOUBLE,
                    short_balance DOUBLE, day_trade_volume DOUBLE
                );
            """)
            con.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_tw_chips_unique
                ON tw_chips (symbol, date);
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS us_options (
                    symbol VARCHAR, date DATE, expiry DATE,
                    option_type VARCHAR, strike DOUBLE,
                    volume DOUBLE, open_interest DOUBLE,
                    implied_volatility DOUBLE, bid DOUBLE,
                    ask DOUBLE, last_price DOUBLE
                );
            """)
            con.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_us_options_unique
                ON us_options (symbol, date, expiry, option_type, strike);
            """)

    # ---------- bars ----------

    def upsert_bars(self, df: pd.DataFrame):
        if df is None or df.empty:
            return

        required = ["symbol", "market", "timestamp",
                    "open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"upsert_bars missing column: {col}")

        df = df[required].copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["market"] = df["market"].apply(_market_str)

        with self._conn() as con:
            con.register("incoming", df)
            con.execute("""
                DELETE FROM bars
                WHERE (symbol, market, timestamp) IN (
                    SELECT symbol, market, timestamp FROM incoming
                );
            """)
            con.execute("INSERT INTO bars SELECT * FROM incoming;")
            con.unregister("incoming")

    def save_bars_parquet(self, df: pd.DataFrame, market: str):
        if df is None or df.empty:
            return
        df = df.copy()
        df["market"] = df["market"].apply(_market_str)
        market_str = _market_str(market)

        for symbol, group in df.groupby("symbol"):
            path = PARQUET_DIR / f"{market_str.lower()}_bars" / f"symbol={symbol}"
            path.mkdir(parents=True, exist_ok=True)
            group.reset_index(drop=True).to_parquet(
                path / "data.parquet", index=False
            )

    def query_bars(
        self, symbol: str, market,
        start: str | None = None, end: str | None = None,
    ) -> pd.DataFrame:
        sql = "SELECT * FROM bars WHERE symbol = ? AND market = ?"
        params: list = [symbol, _market_str(market)]

        if start:
            sql += " AND timestamp >= ?"
            params.append(pd.Timestamp(start))
        if end:
            sql += " AND timestamp <= ?"
            params.append(pd.Timestamp(end))

        sql += " ORDER BY timestamp"

        with self._conn() as con:
            df = con.execute(sql, params).df()

        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    # ---------- tw_chips ----------

    def upsert_tw_chips(self, df: pd.DataFrame):
        if df is None or df.empty:
            return
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date

        expected = [
            "symbol", "date", "foreign_buy", "foreign_sell", "foreign_net",
            "trust_buy", "trust_sell", "trust_net", "dealer_net",
            "margin_balance", "short_balance", "day_trade_volume",
        ]
        for col in expected:
            if col not in df.columns:
                df[col] = 0.0
        df = df[expected]

        with self._conn() as con:
            con.register("incoming_chips", df)
            con.execute("""
                DELETE FROM tw_chips
                WHERE (symbol, date) IN (SELECT symbol, date FROM incoming_chips);
            """)
            con.execute("INSERT INTO tw_chips SELECT * FROM incoming_chips;")
            con.unregister("incoming_chips")

    def query_tw_chips(
        self, symbol: str,
        start: str | None = None, end: str | None = None,
    ) -> pd.DataFrame:
        sql = "SELECT * FROM tw_chips WHERE symbol = ?"
        params: list = [symbol]

        if start:
            sql += " AND date >= ?"
            params.append(pd.Timestamp(start).date())
        if end:
            sql += " AND date <= ?"
            params.append(pd.Timestamp(end).date())

        sql += " ORDER BY date"

        with self._conn() as con:
            df = con.execute(sql, params).df()

        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
        return df

    # ---------- us_options ----------

    def upsert_us_options(self, df: pd.DataFrame):
        if df is None or df.empty:
            return
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df["expiry"] = pd.to_datetime(df["expiry"]).dt.date

        expected = [
            "symbol", "date", "expiry", "option_type", "strike",
            "volume", "open_interest", "implied_volatility",
            "bid", "ask", "last_price",
        ]
        for col in expected:
            if col not in df.columns:
                df[col] = 0.0
        df = df[expected]

        with self._conn() as con:
            con.register("incoming_options", df)
            con.execute("""
                DELETE FROM us_options
                WHERE (symbol, date, expiry, option_type, strike) IN (
                    SELECT symbol, date, expiry, option_type, strike
                    FROM incoming_options
                );
            """)
            con.execute("INSERT INTO us_options SELECT * FROM incoming_options;")
            con.unregister("incoming_options")

    def query_us_options(self, symbol: str, date: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM us_options WHERE symbol = ?"
        params: list = [symbol]

        if date:
            sql += " AND date = ?"
            params.append(pd.Timestamp(date).date())

        sql += " ORDER BY expiry, option_type, strike"

        with self._conn() as con:
            return con.execute(sql, params).df()
```

**修復記錄**：第 2 輪 DuckDB UPSERT 改為 DELETE + INSERT；Parquet 分區修正；enum 轉換統一。

---

## 2.3 `app/data/finmind_provider.py`

**職責**：FinMind 台股數據接入。

```python
import pandas as pd
from FinMind.data import DataLoader

from app.config import settings
from app.data.base import DataProvider
from app.data.warehouse import MarketWarehouse
from app.domain.models import Market, NewsItem


class FinMindProvider(DataProvider):
    def __init__(self):
        self.dl = DataLoader()
        if settings.finmind_token:
            try:
                self.dl.login_by_token(api_token=settings.finmind_token)
            except Exception as e:
                print(f"FinMind login failed: {e}")
        self.warehouse = MarketWarehouse()

    async def get_bars(
        self, symbol: str, market: Market,
        start: str, end: str, interval: str = "1d",
    ) -> pd.DataFrame:
        if market != Market.TW:
            raise ValueError("FinMindProvider only supports TW")

        cached = self.warehouse.query_bars(symbol, market, start, end)
        if not cached.empty:
            return cached

        try:
            df = self.dl.taiwan_stock_daily(
                stock_id=symbol, start_date=start, end_date=end,
            )
        except Exception as e:
            print(f"FinMind fetch error: {e}")
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={
            "date": "timestamp",
            "max": "high",
            "min": "low",
            "Trading_Volume": "volume",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["symbol"] = symbol
        df["market"] = Market.TW.value

        df = df[["timestamp", "symbol", "market",
                 "open", "high", "low", "close", "volume"]]

        self.warehouse.upsert_bars(df)
        self.warehouse.save_bars_parquet(df, Market.TW.value)
        return df

    async def get_fundamentals(self, symbol: str, market: Market) -> dict:
        return {}

    async def get_news(self, symbol: str, market: Market, limit: int = 20) -> list[NewsItem]:
        return []
```

**已知限制**：`get_fundamentals` 和 `get_news` 是佔位實現。

---

## 2.4 `app/data/yfinance_provider.py`

**職責**：yfinance 美股數據接入。

```python
import pandas as pd
import yfinance as yf

from app.data.base import DataProvider
from app.data.warehouse import MarketWarehouse
from app.domain.models import Market, NewsItem


class YFinanceProvider(DataProvider):
    def __init__(self):
        self.warehouse = MarketWarehouse()

    async def get_bars(
        self, symbol: str, market: Market,
        start: str, end: str, interval: str = "1d",
    ) -> pd.DataFrame:
        cached = self.warehouse.query_bars(symbol, market, start, end)
        if not cached.empty:
            return cached

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start, end=end,
                                interval=interval, auto_adjust=False)
        except Exception as e:
            print(f"yfinance fetch error: {e}")
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.reset_index()
        df = df.rename(columns={
            "Date": "timestamp", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
        df["symbol"] = symbol
        df["market"] = Market.US.value

        df = df[["timestamp", "symbol", "market",
                 "open", "high", "low", "close", "volume"]]

        self.warehouse.upsert_bars(df)
        self.warehouse.save_bars_parquet(df, Market.US.value)
        return df

    async def get_fundamentals(self, symbol: str, market: Market) -> dict:
        try:
            info = yf.Ticker(symbol).info
            return info or {}
        except Exception:
            return {}

    async def get_news(self, symbol: str, market: Market, limit: int = 20) -> list[NewsItem]:
        try:
            raw = yf.Ticker(symbol).news or []
        except Exception:
            return []

        out = []
        for item in raw[:limit]:
            published_at = None
            if item.get("providerPublishTime"):
                published_at = pd.to_datetime(item["providerPublishTime"], unit="s")

            out.append(NewsItem(
                title=item.get("title", ""),
                summary=item.get("summary"),
                url=item.get("link"),
                published_at=published_at,
                source=item.get("publisher"),
            ))
        return out
```

---

## 2.5 `app/data/composite.py`

**職責**：組合數據提供者。

```python
from app.data.base import DataProvider
from app.data.finmind_provider import FinMindProvider
from app.data.yfinance_provider import YFinanceProvider
from app.domain.models import Market, NewsItem


class CompositeProvider(DataProvider):
    def __init__(self):
        self.tw = FinMindProvider()
        self.us = YFinanceProvider()

    def _pick(self, market: Market) -> DataProvider:
        if market == Market.TW:
            return self.tw
        if market == Market.US:
            return self.us
        raise ValueError(f"Unsupported market: {market}")

    async def get_bars(
        self, symbol: str, market: Market,
        start: str, end: str, interval: str = "1d",
    ):
        return await self._pick(market).get_bars(symbol, market, start, end, interval)

    async def get_fundamentals(self, symbol: str, market: Market) -> dict:
        return await self._pick(market).get_fundamentals(symbol, market)

    async def get_news(
        self, symbol: str, market: Market, limit: int = 20,
    ) -> list[NewsItem]:
        return await self._pick(market).get_news(symbol, market, limit)
```

**修復記錄**：第 1 輪改用明確簽名。

---

# Part 3：回測層

## 3.1 `app/backtest/signal_dsl.py`

**職責**：輕量級信號 DSL 解析器，支援嵌套函數與高階時序運算。

支援函數：
- 基礎：`sma, ema, mean, std, stdev, rsi, atr, zscore, highest, lowest, max, min, slope`
- 時序：`delay, delta, ts_rank, ts_argmax, ts_argmin, ts_sum, ts_mean, ts_std, ts_min, ts_max`
- 截面：`rank, sign, abs, log`
- 雙序列：`correlation, covariance`
- 分位：`quantile`
- 其他：`signedpower, rsquare, residual`

```python
import re

import numpy as np
import pandas as pd


class SignalDSL:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy().reset_index(drop=True)

        for col in ["close", "open", "high", "low", "volume"]:
            if col not in self.df.columns:
                self.df[col] = np.nan

        self.df["returns"] = self.df["close"].pct_change()
        self.df["vwap"] = (
            (self.df["high"] + self.df["low"] + self.df["close"]) / 3
        )

    # ---------- 基礎指標 ----------

    def sma(self, col, n):
        return self.df[col].rolling(int(n)).mean()

    def mean(self, col, n):
        return self.df[col].rolling(int(n)).mean()

    def ema(self, col, n):
        return self.df[col].ewm(span=int(n), adjust=False).mean()

    def std(self, col, n):
        return self.df[col].rolling(int(n)).std()

    def stdev(self, col, n):
        return self.df[col].rolling(int(n)).std()

    def rsi(self, col, n=14):
        n = int(n)
        delta = self.df[col].diff()
        gain = delta.clip(lower=0).rolling(n).mean()
        loss = (-delta.clip(upper=0)).rolling(n).mean()
        rs = gain / (loss + 1e-9)
        return 100 - 100 / (1 + rs)

    def atr(self, n=14):
        n = int(n)
        tr = pd.concat([
            self.df["high"] - self.df["low"],
            (self.df["high"] - self.df["close"].shift()).abs(),
            (self.df["low"] - self.df["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(n).mean()

    def zscore(self, col, n):
        n = int(n)
        m = self.df[col].rolling(n).mean()
        s = self.df[col].rolling(n).std() + 1e-9
        return (self.df[col] - m) / s

    def highest(self, col, n):
        return self.df[col].rolling(int(n)).max()

    def lowest(self, col, n):
        return self.df[col].rolling(int(n)).min()

    def max(self, col, n):
        return self.df[col].rolling(int(n)).max()

    def min(self, col, n):
        return self.df[col].rolling(int(n)).min()

    def slope(self, col, n):
        n = int(n)

        def _slope(x):
            if len(x) < 2 or np.isnan(x).all():
                return np.nan
            return np.polyfit(range(len(x)), x, 1)[0]

        return self.df[col].rolling(n).apply(_slope, raw=True)

    # ---------- 時序函數 ----------

    def delay(self, col, n):
        return self.df[col].shift(int(n))

    def delta(self, col, n):
        return self.df[col].diff(int(n))

    def ts_sum(self, col, n):
        return self.df[col].rolling(int(n)).sum()

    def ts_mean(self, col, n):
        return self.df[col].rolling(int(n)).mean()

    def ts_std(self, col, n):
        return self.df[col].rolling(int(n)).std()

    def ts_min(self, col, n):
        return self.df[col].rolling(int(n)).min()

    def ts_max(self, col, n):
        return self.df[col].rolling(int(n)).max()

    def ts_rank(self, col, n):
        n = int(n)

        def _rank(x):
            if len(x) < 2:
                return np.nan
            return (x[:-1] < x[-1]).sum() / (len(x) - 1)

        return self.df[col].rolling(n).apply(_rank, raw=True)

    def ts_argmax(self, col, n):
        n = int(n)
        return self.df[col].rolling(n).apply(
            lambda x: len(x) - 1 - np.argmax(x) if not np.isnan(x).all() else np.nan,
            raw=True,
        )

    def ts_argmin(self, col, n):
        n = int(n)
        return self.df[col].rolling(n).apply(
            lambda x: len(x) - 1 - np.argmin(x) if not np.isnan(x).all() else np.nan,
            raw=True,
        )

    # ---------- 截面函數 ----------

    def rank(self, col):
        return self.df[col].rank(pct=True)

    def sign(self, col):
        return np.sign(self.df[col])

    def abs(self, col):
        return np.abs(self.df[col])

    def log(self, col):
        return np.log(self.df[col].clip(lower=1e-9))

    # ---------- 雙序列 ----------

    def correlation(self, col1, col2, n):
        n = int(n)
        return self.df[col1].rolling(n).corr(self.df[col2])

    def covariance(self, col1, col2, n):
        n = int(n)
        return self.df[col1].rolling(n).cov(self.df[col2])

    # ---------- 分位 ----------

    def quantile(self, col, n, q):
        n = int(n)
        q = float(q)
        return self.df[col].rolling(n).quantile(q)

    # ---------- 其他 ----------

    def signedpower(self, col, power):
        power = float(power)
        return np.sign(self.df[col]) * (np.abs(self.df[col]) ** power)

    def rsquare(self, col, n):
        n = int(n)

        def _r2(x):
            if len(x) < 2 or np.isnan(x).all():
                return np.nan
            t = np.arange(len(x))
            corr = np.corrcoef(t, x)[0, 1]
            return corr ** 2 if not np.isnan(corr) else np.nan

        return self.df[col].rolling(n).apply(_r2, raw=True)

    def residual(self, col, n):
        n = int(n)

        def _resid(x):
            if len(x) < 2 or np.isnan(x).all():
                return np.nan
            t = np.arange(len(x))
            try:
                slope, intercept = np.polyfit(t, x, 1)
                return x[-1] - (slope * t[-1] + intercept)
            except Exception:
                return np.nan

        return self.df[col].rolling(n).apply(_resid, raw=True)

    # ---------- 表達式求值 ----------

    def evaluate(self, expr: str) -> pd.Series:
        try:
            expr = str(expr).strip()
        except Exception:
            return pd.Series(0, index=self.df.index)

        max_iter = 20
        for _ in range(max_iter):
            m = re.search(r"(\w+)\(([^()]*)\)", expr)
            if not m:
                break

            func = m.group(1)
            args_str = m.group(2)

            parsed = []
            for a in args_str.split(","):
                a = a.strip()
                if not a:
                    continue
                if a in ("close", "open", "high", "low", "volume", "returns", "vwap"):
                    parsed.append(f"'{a}'")
                    continue
                try:
                    parsed.append(str(int(a)))
                    continue
                except ValueError:
                    pass
                try:
                    parsed.append(str(float(a)))
                    continue
                except ValueError:
                    pass
                parsed.append(a)

            replacement = f"__RESULT_{abs(hash(m.group(0))) % 1000000}__"

            if hasattr(self, func):
                try:
                    args_eval = []
                    for p in parsed:
                        if p.startswith("'"):
                            args_eval.append(p.strip("'"))
                        elif p.lstrip("-").isdigit():
                            args_eval.append(int(p))
                        else:
                            try:
                                args_eval.append(float(p))
                            except ValueError:
                                args_eval.append(p)

                    result = getattr(self, func)(*args_eval)
                    if isinstance(result, pd.Series):
                        expr = expr.replace(m.group(0), replacement)
                        if not hasattr(self, "_results"):
                            self._results = {}
                        self._results[replacement] = result
                        continue
                except Exception:
                    pass

            expr = expr.replace(m.group(0), "0")

        for var in ["close", "open", "high", "low", "volume", "returns", "vwap"]:
            expr = re.sub(rf"\b{var}\b", f"self.df['{var}']", expr)

        if hasattr(self, "_results"):
            for key in list(self._results.keys()):
                expr = expr.replace(key, f"self._results['{key}']")

        try:
            result = eval(expr, {"__builtins__": {}},
                          {"self": self, "np": np, "pd": pd})
            if isinstance(result, pd.Series):
                return result
            if isinstance(result, (int, float, np.number)):
                return pd.Series(float(result), index=self.df.index)
        except Exception as e:
            print(f"DSL eval error: {e} | expr={expr}")

        return pd.Series(0, index=self.df.index)

    def discretize(self, score: pd.Series, upper: float = 0.5, lower: float = -0.5) -> pd.Series:
        pos = pd.Series(0, index=score.index)
        pos[score > upper] = 1
        pos[score < lower] = -1
        return pos
```

**修復記錄**：
- 第 1 輪：正則替換邏輯改為提取 + 還原雙階段。
- 第 3 輪：擴展約 20 個高階函數。

---

## 3.2 `app/backtest/engine.py`

**職責**：事件驅動回測引擎，含交割佔用資金、滑點、風控。

```python
import pandas as pd

from app.domain.models import Market, Side
from app.markets.registry import get_rules


class BacktestEngine:
    def __init__(
        self,
        market: Market,
        initial_cash: float = 1_000_000.0,
        slippage_pct: float = 0.001,
        position_pct: float = 0.1,
        risk_guard=None,
    ):
        self.market = market
        self.rules = get_rules(market)
        self.initial_cash = initial_cash
        self.slippage_pct = slippage_pct
        self.position_pct = position_pct
        self.risk_guard = risk_guard

        self.cash = initial_cash
        self.receivable: list[tuple] = []
        self.positions: dict[str, int] = {}
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []

    def _settle(self, current_date):
        remaining = []
        for settle_date, amount in self.receivable:
            if current_date >= settle_date:
                self.cash += amount
            else:
                remaining.append((settle_date, amount))
        self.receivable = remaining

    def _calc_equity(self, current_price: float) -> float:
        receivable_amount = sum(amount for _, amount in self.receivable)
        position_value = sum(
            qty * current_price for qty in self.positions.values()
        )
        return self.cash + receivable_amount + position_value

    def run(self, bars: pd.DataFrame, signals: pd.Series) -> dict:
        if bars is None or bars.empty:
            return {"trades": [], "equity_curve": [], "final_cash": self.cash,
                    "positions": {}, "metrics": {}}

        df = bars.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)

        symbol = str(df["symbol"].iloc[0]) if "symbol" in df.columns else "UNKNOWN"
        prev_close = None

        if self.risk_guard is not None:
            self.risk_guard.update_equity(self.cash)
            self.risk_guard.reset_daily(self.cash)

        for i, row in df.iterrows():
            current_date = row["timestamp"]
            self._settle(current_date)

            signal = float(signals.iloc[i]) if i < len(signals) else 0.0
            price = float(row["close"])

            if pd.isna(price) or price <= 0:
                equity = self._calc_equity(price if not pd.isna(price) else 0)
                self.equity_curve.append({
                    "date": current_date, "equity": equity,
                    "cash": self.cash,
                    "receivable": sum(a for _, a in self.receivable),
                })
                continue

            equity = self._calc_equity(price)

            if self.risk_guard is not None:
                self.risk_guard.update_equity(equity)

            if signal > 0 and prev_close is not None:
                if self.rules.can_execute(Side.BUY, price, prev_close):
                    target_value = equity * self.position_pct
                    qty = self.rules.round_lot(int(target_value / price)) if price > 0 else 0

                    if qty > 0:
                        if self.risk_guard is not None:
                            check = self.risk_guard.check_order(
                                symbol, "BUY", qty, price,
                                portfolio_value=equity,
                                current_position_value=self.positions.get(symbol, 0) * price,
                                current_equity=equity,
                            )
                            if not check["approved"]:
                                qty = 0
                            else:
                                qty = check.get("adjusted_qty", qty)

                        if qty > 0:
                            buy_price = price * (1 + self.slippage_pct)
                            fee = self.rules.calc_fees(Side.BUY, buy_price, qty)
                            cost = buy_price * qty + fee
                            if cost <= self.cash:
                                self.cash -= cost
                                self.positions[symbol] = self.positions.get(symbol, 0) + qty
                                self.trades.append({
                                    "date": current_date, "side": "BUY",
                                    "price": buy_price, "qty": qty, "fee": fee,
                                })

            elif signal < 0 and self.positions.get(symbol, 0) > 0:
                if prev_close is not None and self.rules.can_execute(Side.SELL, price, prev_close):
                    qty = self.positions[symbol]

                    if self.risk_guard is not None:
                        check = self.risk_guard.check_order(
                            symbol, "SELL", qty, price,
                            portfolio_value=equity,
                            current_position_value=qty * price,
                            current_equity=equity,
                        )
                        if not check["approved"]:
                            qty = 0

                    if qty > 0:
                        sell_price = price * (1 - self.slippage_pct)
                        fee = self.rules.calc_fees(Side.SELL, sell_price, qty)
                        proceeds = sell_price * qty - fee
                        settle_date = self.rules.settlement_date(current_date)

                        self.receivable.append((settle_date, proceeds))
                        self.positions[symbol] = 0
                        self.trades.append({
                            "date": current_date, "side": "SELL",
                            "price": sell_price, "qty": qty, "fee": fee,
                            "settle_date": settle_date,
                        })

            prev_close = price

            equity = self._calc_equity(price)
            self.equity_curve.append({
                "date": current_date, "equity": equity,
                "cash": self.cash,
                "receivable": sum(a for _, a in self.receivable),
            })

        return {
            "trades": self.trades,
            "equity_curve": self.equity_curve,
            "final_cash": self.cash,
            "positions": self.positions,
        }
```

**修復記錄**：
- 第 2 輪：統一簽名，加入 `slippage_pct` 和 `risk_guard`。
- 第 3 輪：修正風控整合時的 `equity` 變數未定義問題。

---

## 3.3 `app/backtest/walk_forward.py`

**職責**：Walk-Forward + CSCV 過擬合檢測。

```python
import numpy as np
import pandas as pd
from itertools import combinations


class WalkForwardEngine:
    def __init__(
        self,
        train_window: int = 252,
        test_window: int = 63,
        step: int = 63,
        n_splits: int = 10,
    ):
        self.train_window = train_window
        self.test_window = test_window
        self.step = step
        self.n_splits = n_splits

    def walk_forward(self, bars, signal_fn, backtest_fn) -> dict:
        df = bars.copy().reset_index(drop=True)
        n = len(df)
        results = []

        start = 0
        while start + self.train_window + self.test_window <= n:
            train = df.iloc[start : start + self.train_window]
            test = df.iloc[
                start + self.train_window :
                start + self.train_window + self.test_window
            ]

            signal_gen = signal_fn(train)
            signals = signal_gen(test)

            result = backtest_fn(test, signals)
            result["window"] = {
                "train_start": str(train["timestamp"].iloc[0]),
                "train_end": str(train["timestamp"].iloc[-1]),
                "test_start": str(test["timestamp"].iloc[0]),
                "test_end": str(test["timestamp"].iloc[-1]),
            }
            results.append(result)
            start += self.step

        all_trades = []
        all_equity = []
        for i, r in enumerate(results):
            for t in r.get("trades", []):
                t["window_idx"] = i
                all_trades.append(t)
            for e in r.get("equity_curve", []):
                e["window_idx"] = i
                all_equity.append(e)

        return {
            "windows": results,
            "summary": self._summarize(results),
            "all_trades": all_trades,
            "all_equity": all_equity,
        }

    def _summarize(self, results) -> dict:
        sharpes, returns, drawdowns = [], [], []

        for r in results:
            eq = pd.DataFrame(r.get("equity_curve", []))
            if eq.empty:
                continue
            eq["return"] = eq["equity"].pct_change()
            sharpe = eq["return"].mean() / (eq["return"].std() + 1e-9) * (252 ** 0.5)
            total_ret = eq["equity"].iloc[-1] / eq["equity"].iloc[0] - 1
            max_dd = ((eq["equity"] / eq["equity"].cummax()) - 1).min()
            sharpes.append(sharpe)
            returns.append(total_ret)
            drawdowns.append(max_dd)

        if not sharpes:
            return {}

        return {
            "num_windows": len(sharpes),
            "sharpe_mean": round(float(np.mean(sharpes)), 4),
            "sharpe_std": round(float(np.std(sharpes)), 4),
            "sharpe_min": round(float(np.min(sharpes)), 4),
            "sharpe_max": round(float(np.max(sharpes)), 4),
            "return_mean": round(float(np.mean(returns)), 4),
            "return_win_rate": round(sum(1 for r in returns if r > 0) / len(returns), 4),
            "max_drawdown_mean": round(float(np.mean(drawdowns)), 4),
            "oos_consistency": round(
                float(np.mean(sharpes)) / (float(np.std(sharpes)) + 1e-9), 4
            ),
        }

    def cscv(self, bars, signal_candidates, backtest_fn) -> dict:
        n = len(bars)
        split_size = n // self.n_splits
        if split_size < 10:
            return {"error": "not enough data for CSCV"}

        splits = []
        for i in range(self.n_splits):
            start = i * split_size
            end = start + split_size
            splits.append(bars.iloc[start:end].copy())

        perf_matrix = {}
        for name, sig_fn in signal_candidates.items():
            perfs = []
            for s in splits:
                signals = sig_fn(s)
                result = backtest_fn(s, signals)
                eq = pd.DataFrame(result.get("equity_curve", []))
                if eq.empty:
                    perfs.append(0)
                    continue
                eq["return"] = eq["equity"].pct_change()
                sharpe = eq["return"].mean() / (eq["return"].std() + 1e-9) * (252 ** 0.5)
                perfs.append(sharpe)
            perf_matrix[name] = perfs

        n_comb = self.n_splits // 2
        combo_indices = list(combinations(range(self.n_splits), n_comb))
        n_combos = len(combo_indices)

        if n_combos > 5000:
            idx = np.random.choice(n_combos, 5000, replace=False)
            combo_indices = [combo_indices[i] for i in idx]

        logits = []
        for combo in combo_indices:
            is_idx = list(combo)
            oos_idx = [i for i in range(self.n_splits) if i not in combo]

            is_perf = {name: np.mean([perfs[i] for i in is_idx])
                       for name, perfs in perf_matrix.items()}
            oos_perf = {name: np.mean([perfs[i] for i in oos_idx])
                        for name, perfs in perf_matrix.items()}

            best_is = max(is_perf, key=is_perf.get)
            rank_oos = sorted(oos_perf, key=oos_perf.get, reverse=True)
            rank = rank_oos.index(best_is) + 1

            omega = rank / (len(rank_oos) + 1)
            logit = np.log(omega / (1 - omega + 1e-9))
            logits.append(logit)

        pbo = sum(1 for l in logits if l <= 0) / len(logits)

        return {
            "PBO": round(pbo, 4),
            "interpretation": (
                "低過擬合風險" if pbo < 0.2
                else "中等過擬合風險" if pbo < 0.5
                else "高過擬合風險"
            ),
            "num_combinations": len(logits),
            "perf_matrix": perf_matrix,
        }
```

**修復記錄**：第 1 輪刪除未使用的 `from math import comb`。

---

## 3.4 `app/backtest/neutrino_engine.py`

**職責**：Numba 向量化回測引擎。

```python
import numpy as np
import pandas as pd


class NeutrinoEngine:
    def __init__(self):
        self._available = self._check_available()

    def _check_available(self) -> bool:
        try:
            import numba
            self.numba = numba
            return True
        except ImportError:
            return False

    def vectorized_backtest(
        self, close, signals,
        fee_rate: float = 0.001,
        slippage_pct: float = 0.001,
        initial_capital: float = 1_000_000,
    ) -> dict:
        close = np.asarray(close, dtype=np.float64)
        signals = np.asarray(signals, dtype=np.float64)

        if len(close) != len(signals):
            return {"error": "close and signals must have same length"}

        if self._available:
            return self._backtest_numba(close, signals, fee_rate, slippage_pct, initial_capital)
        return self._backtest_python(close, signals, fee_rate, slippage_pct, initial_capital)

    def _backtest_python(self, close, signals, fee_rate, slippage_pct, initial_capital) -> dict:
        n = len(close)
        cash = float(initial_capital)
        position = 0.0
        equity = np.zeros(n)
        equity[0] = cash
        trades = []
        prev_signal = 0.0

        for i in range(1, n):
            sig = signals[i]
            price = close[i]
            if np.isnan(price) or price <= 0:
                equity[i] = cash + position * (close[i - 1] if i > 0 else 0)
                continue

            if sig != prev_signal:
                if position > 0 and sig <= 0:
                    sell_price = price * (1 - slippage_pct)
                    proceeds = position * sell_price * (1 - fee_rate)
                    cash += proceeds
                    trades.append({"index": i, "side": "SELL",
                                   "price": sell_price, "qty": position})
                    position = 0.0

                if sig > 0 and position <= 0:
                    buy_price = price * (1 + slippage_pct)
                    qty = (cash * 0.95) / buy_price
                    cost = qty * buy_price * (1 + fee_rate)
                    if cost <= cash:
                        cash -= cost
                        position = qty
                        trades.append({"index": i, "side": "BUY",
                                       "price": buy_price, "qty": qty})

            equity[i] = cash + position * price
            prev_signal = sig

        return self._calc_metrics(equity, trades, close)

    def _backtest_numba(self, close, signals, fee_rate, slippage_pct, initial_capital) -> dict:
        @self.numba.njit(cache=True)
        def _kernel(close, signals, fee_rate, slippage_pct, initial_capital):
            n = len(close)
            cash = float(initial_capital)
            position = 0.0
            equity = np.zeros(n)
            equity[0] = cash
            trade_buf = np.zeros((n, 4), dtype=np.float64)
            trade_count = 0
            prev_signal = 0.0

            for i in range(1, n):
                sig = signals[i]
                price = close[i]
                if np.isnan(price) or price <= 0:
                    equity[i] = cash + position * close[i - 1]
                    continue

                if sig != prev_signal:
                    if position > 0 and sig <= 0:
                        sell_price = price * (1 - slippage_pct)
                        proceeds = position * sell_price * (1 - fee_rate)
                        cash += proceeds
                        trade_buf[trade_count, 0] = i
                        trade_buf[trade_count, 1] = -1
                        trade_buf[trade_count, 2] = sell_price
                        trade_buf[trade_count, 3] = position
                        trade_count += 1
                        position = 0.0

                    if sig > 0 and position <= 0:
                        buy_price = price * (1 + slippage_pct)
                        qty = (cash * 0.95) / buy_price
                        cost = qty * buy_price * (1 + fee_rate)
                        if cost <= cash:
                            cash -= cost
                            position = qty
                            trade_buf[trade_count, 0] = i
                            trade_buf[trade_count, 1] = 1
                            trade_buf[trade_count, 2] = buy_price
                            trade_buf[trade_count, 3] = qty
                            trade_count += 1

                equity[i] = cash + position * price
                prev_signal = sig

            return equity, trade_buf[:trade_count]

        equity, trades = _kernel(close, signals, float(fee_rate),
                                 float(slippage_pct), float(initial_capital))

        trade_list = [
            {"index": int(t[0]), "side": "BUY" if t[1] > 0 else "SELL",
             "price": float(t[2]), "qty": float(t[3])}
            for t in trades
        ]
        return self._calc_metrics(equity, trade_list, close)

    def _calc_metrics(self, equity, trades, close) -> dict:
        eq = pd.Series(equity)
        eq = eq[eq > 0]
        if len(eq) < 2:
            return {"error": "insufficient data"}

        returns = eq.pct_change().dropna()
        total_return = float(eq.iloc[-1] / eq.iloc[0] - 1)
        sharpe = float(returns.mean() / (returns.std() + 1e-9) * (252 ** 0.5))
        max_dd = float(((eq / eq.cummax()) - 1).min())

        downside = returns[returns < 0]
        sortino = float(returns.mean() / (downside.std() + 1e-9) * (252 ** 0.5))
        calmar = float(total_return / (abs(max_dd) + 1e-9))

        return {
            "total_return": round(total_return, 4),
            "sharpe": round(sharpe, 4),
            "sortino": round(sortino, 4),
            "calmar": round(calmar, 4),
            "max_drawdown": round(max_dd, 4),
            "num_trades": len(trades),
            "win_rate": self._calc_win_rate(trades),
        }

    def _calc_win_rate(self, trades) -> float:
        if len(trades) < 2:
            return 0.0
        wins = 0
        pairs = 0
        for i in range(len(trades) - 1):
            t1, t2 = trades[i], trades[i + 1]
            if t1["side"] == "BUY" and t2["side"] == "SELL":
                if t2["price"] > t1["price"]:
                    wins += 1
                pairs += 1
        return round(wins / pairs, 4) if pairs > 0 else 0.0

    def parameter_sweep(self, bars, strategy_fn, param_grid, max_combinations=5000) -> pd.DataFrame:
        import itertools
        import random

        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combinations = list(itertools.product(*values))

        if len(combinations) > max_combinations:
            random.seed(42)
            combinations = random.sample(combinations, max_combinations)

        close = bars["close"].values
        results = []

        for combo in combinations:
            params = dict(zip(keys, combo))
            try:
                signals = strategy_fn(close, **params)
                metrics = self.vectorized_backtest(close, signals)
                if "error" not in metrics:
                    metrics.update(params)
                    results.append(metrics)
            except Exception:
                continue

        df = pd.DataFrame(results)
        if not df.empty:
            df = df.sort_values("sharpe", ascending=False)
        return df
```

**修復記錄**：第 3 輪 Numba 和 fallback 邏輯完全對齊。

---

## 3.5 `app/backtest/vectorbt_engine.py`

**職責**：VectorBT 多資產組合回測包裝器。

```python
import numpy as np
import pandas as pd


class VectorBTEngine:
    def __init__(self):
        self._available = self._check_available()

    def _check_available(self) -> bool:
        try:
            import vectorbt as vbt
            self.vbt = vbt
            return True
        except ImportError:
            return False

    def ma_cross_sweep(self, close, fast_range, slow_range,
                       fees=0.001425, slippage=0.001) -> pd.DataFrame:
        if not self._available:
            return pd.DataFrame({"error": ["vectorbt not installed"]})

        fast_ma = self.vbt.MA.run(close, window=fast_range)
        slow_ma = self.vbt.MA.run(close, window=slow_range)

        entries = fast_ma.ma_crossed_above(slow_ma)
        exits = fast_ma.ma_crossed_below(slow_ma)

        pf = self.vbt.Portfolio.from_signals(
            close, entries, exits, fees=fees, slippage=slippage, freq="1D",
        )

        return pd.DataFrame({
            "total_return": pf.total_return(),
            "sharpe": pf.sharpe_ratio(),
            "max_drawdown": pf.max_drawdown(),
            "win_rate": pf.trades.win_rate(),
            "num_trades": pf.trades.count(),
        }).sort_values("sharpe", ascending=False)

    def multi_asset_portfolio(self, close_matrix, signals, fees=0.001425) -> dict:
        if not self._available:
            return {"error": "vectorbt not installed"}

        entries = signals == 1
        exits = signals == -1

        pf = self.vbt.Portfolio.from_signals(
            close_matrix, entries, exits, fees=fees, freq="1D",
        )

        return {
            "total_return": float(pf.total_return()),
            "sharpe": float(pf.sharpe_ratio()),
            "max_drawdown": float(pf.max_drawdown()),
            "per_asset": {
                col: {
                    "return": float(pf[col].total_return()),
                    "sharpe": float(pf[col].sharpe_ratio()),
                }
                for col in close_matrix.columns
            },
        }
```

---

# Part 4：風控層

## 4.1 `app/risk/guard.py`

**職責**：實盤風控引擎，台股 / 美股雙配置。

```python
import json
from datetime import datetime, timedelta
from pathlib import Path


class RiskGuard:
    def __init__(
        self,
        market: str = "TW",
        max_position_pct: float = 0.15,
        max_daily_loss_pct: float = 0.025,
        max_drawdown_pct: float = 0.12,
        cooldown_minutes: int = 60,
        kelly_fraction: float = 0.4,
        circuit_breaker_levels: dict | None = None,
    ):
        self.market = market
        self.max_position_pct = max_position_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.cooldown_minutes = cooldown_minutes
        self.kelly_fraction = kelly_fraction

        self.circuit_breaker_levels = circuit_breaker_levels or {
            "reduce": 0.06, "halt": 0.10, "kill": 0.15,
        }

        self.peak_equity = 0.0
        self.daily_start_equity = 0.0
        self.circuit_breaker_until = None
        self.circuit_breaker_level = "normal"
        self.kill_switch_active = False

    def update_equity(self, equity: float):
        if equity > self.peak_equity:
            self.peak_equity = equity

    def reset_daily(self, equity: float):
        self.daily_start_equity = equity

    def check_order(
        self, symbol, side, qty, price,
        portfolio_value, current_position_value=0.0, current_equity=1_000_000.0,
    ) -> dict:
        now = datetime.now()

        if self.kill_switch_active:
            return {"approved": False, "reason": "KILL_SWITCH_ACTIVE"}

        if self.circuit_breaker_until and now < self.circuit_breaker_until:
            return {
                "approved": False,
                "reason": f"CIRCUIT_BREAKER_{self.circuit_breaker_level.upper()}",
                "until": self.circuit_breaker_until.isoformat(),
            }

        if self.peak_equity > 0:
            dd = (self.peak_equity - current_equity) / self.peak_equity

            if dd >= self.circuit_breaker_levels["kill"]:
                self.circuit_breaker_until = now + timedelta(minutes=self.cooldown_minutes)
                self.circuit_breaker_level = "kill"
                return {"approved": False, "reason": f"KILL_DRAWDOWN_{dd:.2%}"}

            if dd >= self.circuit_breaker_levels["halt"]:
                self.circuit_breaker_level = "halt"
                return {"approved": False, "reason": f"HALT_DRAWDOWN_{dd:.2%}"}

            if dd >= self.circuit_breaker_levels["reduce"]:
                self.circuit_breaker_level = "reduce"
                return {"approved": True,
                        "adjusted_qty": max(0, int(qty * 0.5)),
                        "reason": f"REDUCE_DRAWDOWN_{dd:.2%}"}

        if self.daily_start_equity > 0:
            daily_loss = (self.daily_start_equity - current_equity) / self.daily_start_equity
            if daily_loss > self.max_daily_loss_pct:
                return {"approved": False, "reason": f"DAILY_LOSS_{daily_loss:.2%}"}

        if side == "BUY" and price > 0:
            new_position = current_position_value + qty * price
            position_pct = new_position / (portfolio_value + 1e-9)

            if position_pct > self.max_position_pct:
                max_qty = int((self.max_position_pct * portfolio_value - current_position_value) / price)
                max_qty = max(0, max_qty)
                return {"approved": True, "adjusted_qty": max_qty,
                        "reason": f"POSITION_LIMIT_{position_pct:.2%}"}

        return {"approved": True, "adjusted_qty": qty, "reason": "PASS"}

    def kelly_position(self, win_rate, avg_win, avg_loss, portfolio_value) -> float:
        if avg_loss <= 0:
            return 0.0
        b = avg_win / avg_loss
        p = win_rate
        q = 1 - p
        kelly = (p * b - q) / (b + 1e-9)
        kelly = max(0.0, min(kelly, 0.25))
        return portfolio_value * kelly * self.kelly_fraction

    def activate_kill_switch(self, reason: str = "manual"):
        self.kill_switch_active = True
        self.circuit_breaker_until = datetime.now() + timedelta(minutes=self.cooldown_minutes)
        return {"kill_switch": "ACTIVE", "reason": reason}

    def deactivate_kill_switch(self):
        self.kill_switch_active = False
        self.circuit_breaker_until = None
        return {"kill_switch": "INACTIVE"}

    def persist(self, path: str):
        state = {
            "market": self.market,
            "peak_equity": self.peak_equity,
            "daily_start_equity": self.daily_start_equity,
            "circuit_breaker_until": (
                self.circuit_breaker_until.isoformat()
                if self.circuit_breaker_until else None
            ),
            "circuit_breaker_level": self.circuit_breaker_level,
            "kill_switch_active": self.kill_switch_active,
            "saved_at": datetime.now().isoformat(),
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f, indent=2)

    def load(self, path: str):
        try:
            with open(path) as f:
                state = json.load(f)
            self.peak_equity = state.get("peak_equity", 0.0)
            self.daily_start_equity = state.get("daily_start_equity", 0.0)
            self.circuit_breaker_level = state.get("circuit_breaker_level", "normal")
            self.kill_switch_active = state.get("kill_switch_active", False)
            cb = state.get("circuit_breaker_until")
            self.circuit_breaker_until = datetime.fromisoformat(cb) if cb else None
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"RiskGuard load error: {e}")


def build_tw_guard() -> RiskGuard:
    return RiskGuard(market="TW", max_position_pct=0.15,
                     max_daily_loss_pct=0.025, max_drawdown_pct=0.12,
                     kelly_fraction=0.4)


def build_us_guard() -> RiskGuard:
    return RiskGuard(market="US", max_position_pct=0.20,
                     max_daily_loss_pct=0.03, max_drawdown_pct=0.15,
                     kelly_fraction=0.5)
```

---

## 4.2 `app/risk/__init__.py`

```python
from app.risk.guard import RiskGuard, build_tw_guard, build_us_guard

__all__ = ["RiskGuard", "build_tw_guard", "build_us_guard"]
```

---

# Part 5：因子層

## 5.1 `app/factors/registry.py`

**職責**：因子註冊表，管理元數據、版本、生命週期。

```python
from pathlib import Path

import duckdb
import pandas as pd


class FactorRegistry:
    def __init__(self, db_path: str = "./data_lake/factors.duckdb"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    def _conn(self):
        return duckdb.connect(self.db_path)

    def _ensure_tables(self):
        with self._conn() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS factors (
                    factor_id VARCHAR, name VARCHAR, version INTEGER DEFAULT 1,
                    expr VARCHAR, category VARCHAR, market VARCHAR,
                    status VARCHAR DEFAULT 'draft',
                    ic_mean DOUBLE, rank_ic_mean DOUBLE, lift DOUBLE,
                    author VARCHAR, manifest_hash VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            con.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_factors_id
                ON factors (factor_id);
            """)
            con.execute("""
                CREATE INDEX IF NOT EXISTS idx_factors_name
                ON factors (name);
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS factor_history (
                    factor_id VARCHAR, version INTEGER, expr VARCHAR,
                    ic_mean DOUBLE, rank_ic_mean DOUBLE, lift DOUBLE,
                    change_reason VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def register(self, name, expr, category="unknown", market="BOTH", author="system") -> str:
        factor_id = f"{name}_v1"
        with self._conn() as con:
            existing = con.execute(
                "SELECT factor_id FROM factors WHERE name = ?", [name]
            ).fetchone()
            if existing:
                raise ValueError(f"Factor '{name}' already exists: {existing[0]}")

            con.execute("""
                INSERT INTO factors
                (factor_id, name, version, expr, category, market, status, author)
                VALUES (?, ?, 1, ?, ?, ?, 'draft', ?)
            """, [factor_id, name, expr, category, market, author])
        return factor_id

    def validate(self, factor_id, ic_mean, rank_ic_mean, lift) -> dict:
        with self._conn() as con:
            row = con.execute(
                "SELECT factor_id FROM factors WHERE factor_id = ?", [factor_id]
            ).fetchone()
            if not row:
                return {"error": "factor not found"}

            new_status = "production" if lift > 0 else "validated"
            con.execute("""
                UPDATE factors
                SET status = ?, ic_mean = ?, rank_ic_mean = ?, lift = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE factor_id = ?
            """, [new_status, ic_mean, rank_ic_mean, lift, factor_id])

            con.execute("""
                INSERT INTO factor_history
                (factor_id, version, expr, ic_mean, rank_ic_mean, lift, change_reason)
                SELECT factor_id, version, expr, ?, ?, ?, 'validation'
                FROM factors WHERE factor_id = ?
            """, [ic_mean, rank_ic_mean, lift, factor_id])

        return {"factor_id": factor_id, "status": new_status, "lift": lift,
                "verdict": "入庫" if lift > 0 else "僅保留不入庫"}

    def list_by_status(self, status: str = "production") -> list[dict]:
        with self._conn() as con:
            df = con.execute(
                "SELECT * FROM factors WHERE status = ? ORDER BY rank_ic_mean DESC NULLS LAST",
                [status],
            ).df()
        return df.to_dict("records")

    def get_production_factors(self, market: str | None = None) -> list[dict]:
        sql = "SELECT * FROM factors WHERE status = 'production'"
        params = []
        if market:
            sql += " AND (market = ? OR market = 'BOTH')"
            params.append(market)
        sql += " ORDER BY rank_ic_mean DESC NULLS LAST"

        with self._conn() as con:
            df = con.execute(sql, params).df()
        return df.to_dict("records")
```

**修復記錄**：第 2 輪 DuckDB PRIMARY KEY 改為 UNIQUE INDEX。

---

## 5.2 `app/factors/tw_chips.py`

**職責**：台股籌碼因子引擎。

```python
import pandas as pd
from FinMind.data import DataLoader

from app.config import settings
from app.data.warehouse import MarketWarehouse


FOREIGN_ALIASES = ["Foreign_Investor", "Foreign_Investor_Dealer",
                   "外資", "外資及陸資", "外陸資"]
TRUST_ALIASES = ["Investment_Trust", "投信", "投信自營商"]
DEALER_ALIASES = ["Dealer_self", "Dealer_Hedging", "Dealer",
                  "自營商", "自營商自行買賣", "自營商避險"]


class TWChipsFactorEngine:
    def __init__(self):
        self.dl = DataLoader()
        if settings.finmind_token:
            try:
                self.dl.login_by_token(api_token=settings.finmind_token)
            except Exception as e:
                print(f"FinMind login failed: {e}")
        self.warehouse = MarketWarehouse()

    def _safe_fetch(self, method_name: str, **kwargs) -> pd.DataFrame:
        try:
            method = getattr(self.dl, method_name, None)
            if method is None:
                return pd.DataFrame()
            df = method(**kwargs)
            return df if df is not None else pd.DataFrame()
        except Exception as e:
            print(f"FinMind fetch error ({method_name}): {e}")
            return pd.DataFrame()

    def fetch_institutional(self, symbol, start, end):
        return self._safe_fetch("taiwan_stock_institutional_investors",
                                stock_id=symbol, start_date=start, end_date=end)

    def fetch_margin(self, symbol, start, end):
        return self._safe_fetch("taiwan_stock_margin_purchase_short_sale",
                                stock_id=symbol, start_date=start, end_date=end)

    def fetch_day_trade(self, symbol, start, end):
        return self._safe_fetch("taiwan_stock_day_trading",
                                stock_id=symbol, start_date=start, end_date=end)

    @staticmethod
    def _match_alias(name_series, aliases):
        mask = pd.Series(False, index=name_series.index)
        for alias in aliases:
            mask |= name_series.str.contains(alias, na=False, case=False)
        return mask

    def build_chip_table(self, symbol, start, end) -> pd.DataFrame:
        inst = self.fetch_institutional(symbol, start, end)
        margin = self.fetch_margin(symbol, start, end)
        day_trade = self.fetch_day_trade(symbol, start, end)

        rows = []

        if not inst.empty and "date" in inst.columns:
            for date, group in inst.groupby("date"):
                foreign_mask = self._match_alias(group["name"], FOREIGN_ALIASES)
                trust_mask = self._match_alias(group["name"], TRUST_ALIASES)
                dealer_mask = self._match_alias(group["name"], DEALER_ALIASES)

                def _sum(mask, col):
                    if col not in group.columns:
                        return 0.0
                    return float(group.loc[mask, col].sum())

                foreign_buy = _sum(foreign_mask, "buy")
                foreign_sell = _sum(foreign_mask, "sell")
                trust_buy = _sum(trust_mask, "buy")
                trust_sell = _sum(trust_mask, "sell")
                dealer_buy = _sum(dealer_mask, "buy")
                dealer_sell = _sum(dealer_mask, "sell")

                rows.append({
                    "date": date, "symbol": symbol,
                    "foreign_buy": foreign_buy, "foreign_sell": foreign_sell,
                    "foreign_net": foreign_buy - foreign_sell,
                    "trust_buy": trust_buy, "trust_sell": trust_sell,
                    "trust_net": trust_buy - trust_sell,
                    "dealer_net": dealer_buy - dealer_sell,
                    "margin_balance": 0.0, "short_balance": 0.0,
                    "day_trade_volume": 0.0,
                })

        chip = pd.DataFrame(rows)
        if chip.empty:
            return chip

        chip = chip.set_index("date")

        if not margin.empty and "date" in margin.columns:
            margin = margin.set_index("date")
            for col, target in [
                ("MarginPurchaseTodayBalance", "margin_balance"),
                ("MarginPurchaseBalance", "margin_balance"),
                ("ShortSaleTodayBalance", "short_balance"),
                ("ShortSaleBalance", "short_balance"),
            ]:
                if col in margin.columns:
                    chip[target] = margin[col].reindex(chip.index).fillna(0.0)

        if not day_trade.empty and "date" in day_trade.columns:
            dt_col = None
            for col in ["volume", "Volume", "trade_volume", "day_trade_volume"]:
                if col in day_trade.columns:
                    dt_col = col
                    break
            if dt_col:
                dt = day_trade.groupby("date")[dt_col].sum()
                chip["day_trade_volume"] = dt.reindex(chip.index).fillna(0.0)

        chip = chip.reset_index()
        chip["symbol"] = symbol
        chip["date"] = pd.to_datetime(chip["date"])

        try:
            self.warehouse.upsert_tw_chips(chip)
        except Exception as e:
            print(f"Warehouse upsert failed: {e}")

        return chip

    def compute_factors(self, symbol, start, end) -> pd.DataFrame:
        raw = self.warehouse.query_tw_chips(symbol, start, end)
        if raw is None or raw.empty:
            raw = self.build_chip_table(symbol, start, end)
        if raw is None or raw.empty:
            return pd.DataFrame()

        raw = raw.sort_values("date").reset_index(drop=True)
        f = pd.DataFrame()
        f["date"] = raw["date"]

        if "foreign_net" in raw.columns:
            f["foreign_net_5d"] = raw["foreign_net"].rolling(5, min_periods=1).sum()
            f["foreign_net_20d"] = raw["foreign_net"].rolling(20, min_periods=1).sum()

        if "trust_net" in raw.columns:
            f["trust_net_5d"] = raw["trust_net"].rolling(5, min_periods=1).sum()
            f["trust_net_20d"] = raw["trust_net"].rolling(20, min_periods=1).sum()

        if "margin_balance" in raw.columns:
            mb = raw["margin_balance"]
            ma20 = mb.rolling(20, min_periods=1).mean()
            f["margin_ratio"] = mb / (ma20 + 1e-9)

        if "short_balance" in raw.columns and "margin_balance" in raw.columns:
            f["short_margin_ratio"] = raw["short_balance"] / (raw["margin_balance"] + 1e-9)

        if "day_trade_volume" in raw.columns:
            dt = raw["day_trade_volume"]
            f["day_trade_ratio"] = dt / (dt.rolling(20, min_periods=1).mean() + 1e-9)

        if "foreign_net" in raw.columns and "trust_net" in raw.columns:
            combined = raw["foreign_net"] + raw["trust_net"]
            std20 = combined.rolling(20, min_periods=1).std()
            f["chip_concentration"] = combined / (std20 + 1e-9)

        f["symbol"] = symbol
        return f
```

**修復記錄**：第 3 輪加入 FinMind API 別名寬鬆匹配；欄位對齊；容錯處理。

---

## 5.3 `app/factors/us_options.py`

**職責**：美股期權因子引擎。

```python
import math

import numpy as np
import pandas as pd
import yfinance as yf

from app.data.warehouse import MarketWarehouse


class USOptionsFactorEngine:
    def __init__(self):
        self.warehouse = MarketWarehouse()

    def fetch_chain(self, symbol: str, max_expiries: int = 4) -> pd.DataFrame:
        try:
            ticker = yf.Ticker(symbol)
            expirations = ticker.options
        except Exception as e:
            print(f"yfinance options error for {symbol}: {e}")
            return pd.DataFrame()

        if not expirations:
            return pd.DataFrame()

        rows = []
        today = pd.Timestamp.today().date()

        for exp in expirations[:max_expiries]:
            try:
                chain = ticker.option_chain(exp)
            except Exception:
                continue

            for opt_type, df in [("CALL", chain.calls), ("PUT", chain.puts)]:
                if df is None or df.empty:
                    continue
                d = df[["strike", "volume", "openInterest",
                        "impliedVolatility", "bid", "ask", "lastPrice"]].copy()
                d["option_type"] = opt_type
                d["expiry"] = pd.Timestamp(exp).date()
                d["date"] = today
                d["symbol"] = symbol
                rows.append(d)

        if not rows:
            return pd.DataFrame()

        result = pd.concat(rows, ignore_index=True)
        result = result.rename(columns={
            "openInterest": "open_interest",
            "impliedVolatility": "implied_volatility",
            "lastPrice": "last_price",
        })

        try:
            self.warehouse.upsert_us_options(result)
        except Exception as e:
            print(f"Warehouse upsert failed: {e}")

        return result

    def compute_factors(self, symbol: str, spot: float | None = None) -> dict:
        chain = self.fetch_chain(symbol)
        if chain is None or chain.empty:
            return {}

        if spot is None:
            try:
                spot = float(yf.Ticker(symbol).history(period="1d")["Close"].iloc[-1])
            except Exception:
                return {}

        calls = chain[chain["option_type"] == "CALL"]
        puts = chain[chain["option_type"] == "PUT"]

        factors = {}

        call_vol = calls["volume"].sum()
        put_vol = puts["volume"].sum()
        factors["put_call_volume_ratio"] = (
            float(put_vol / call_vol) if call_vol > 0 else np.nan
        )

        call_oi = calls["open_interest"].sum()
        put_oi = puts["open_interest"].sum()
        factors["put_call_oi_ratio"] = (
            float(put_oi / call_oi) if call_oi > 0 else np.nan
        )

        atm_calls = calls.iloc[(calls["strike"] - spot).abs().argsort()[:5]]
        atm_puts = puts.iloc[(puts["strike"] - spot).abs().argsort()[:5]]
        atm_iv_series = pd.concat([atm_calls, atm_puts])["implied_volatility"]
        factors["atm_iv"] = (
            float(atm_iv_series.mean()) if not atm_iv_series.empty else np.nan
        )

        otm_puts = puts[puts["strike"] < spot * 0.95]
        otm_calls = calls[calls["strike"] > spot * 1.05]
        put_iv = otm_puts["implied_volatility"].mean() if not otm_puts.empty else np.nan
        call_iv = otm_calls["implied_volatility"].mean() if not otm_calls.empty else np.nan
        factors["iv_skew"] = (
            float(put_iv - call_iv)
            if pd.notna(put_iv) and pd.notna(call_iv) else np.nan
        )

        factors["max_pain"] = self._calc_max_pain_vectorized(chain, spot)
        factors["gamma_exposure"] = self._calc_gamma_exposure(chain, spot)

        total_oi = chain["open_interest"].sum()
        factors["oi_concentration"] = (
            float(chain.nlargest(5, "open_interest")["open_interest"].sum() / total_oi)
            if total_oi > 0 else np.nan
        )

        return factors

    def _calc_max_pain_vectorized(self, chain, spot) -> float:
        strikes = chain["strike"].dropna().unique()
        strikes = np.sort(strikes)
        strikes = strikes[(strikes >= 0.7 * spot) & (strikes <= 1.3 * spot)]
        if len(strikes) == 0:
            return np.nan

        calls = chain[chain["option_type"] == "CALL"][["strike", "open_interest"]].dropna()
        puts = chain[chain["option_type"] == "PUT"][["strike", "open_interest"]].dropna()

        call_strikes = calls["strike"].values
        call_oi = calls["open_interest"].values
        put_strikes = puts["strike"].values
        put_oi = puts["open_interest"].values

        call_matrix = np.maximum(strikes[:, None] - call_strikes[None, :], 0) * call_oi[None, :]
        put_matrix = np.maximum(put_strikes[None, :] - strikes[:, None], 0) * put_oi[None, :]
        total_pain = call_matrix.sum(axis=1) + put_matrix.sum(axis=1)
        return float(strikes[int(np.argmin(total_pain))])

    def _calc_gamma_exposure(self, chain, spot, r=0.05) -> float:
        if chain.empty or spot <= 0:
            return 0.0

        def norm_pdf(x):
            return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

        total = 0.0
        valid = chain[(chain["strike"] > spot * 0.8) & (chain["strike"] < spot * 1.2)]

        for _, row in valid.iterrows():
            k = float(row["strike"])
            iv = float(row["implied_volatility"]) if pd.notna(row["implied_volatility"]) else 0.0
            oi = float(row["open_interest"]) if pd.notna(row["open_interest"]) else 0.0
            if iv <= 0 or oi <= 0 or k <= 0:
                continue
            t = 0.25
            try:
                d1 = (math.log(spot / k) + (r + 0.5 * iv ** 2) * t) / (iv * math.sqrt(t))
                gamma = norm_pdf(d1) / (spot * iv * math.sqrt(t))
                total += gamma * oi * 100 * spot ** 2
            except Exception:
                continue

        return float(total)
```

**修復記錄**：第 3 輪 Max Pain 向量化；伽馬曝險容錯。

---

## 5.4 `app/factors/qweave_loader.py`

**職責**：qweave 內置因子庫（Alpha101/158/191 子集）。

```python
class QweaveFactorLoader:
    ALPHA101_SUBSET = {
        "alpha001": "ts_argmax(signedpower(returns, 2), 5) - 0.5",
        "alpha002": "-1 * correlation(rank(delta(log(volume), 2)), rank(delta(close, 1)), 6)",
        "alpha003": "-1 * correlation(rank(open), rank(volume), 10)",
        "alpha004": "-1 * ts_rank(rank(low), 9)",
        "alpha006": "-1 * correlation(open, volume, 10)",
        "alpha012": "sign(delta(volume, 1)) * (-1 * delta(close, 1))",
        "alpha014": "(-1 * rank(delta(returns, 3))) * correlation(open, volume, 10)",
        "alpha020": "(-1 * rank(delta(delay(close, 1), 1))) * rank(open) * rank(volume)",
    }

    ALPHA158_SUBSET = {
        "ROC5": "close / delay(close, 5) - 1",
        "ROC10": "close / delay(close, 10) - 1",
        "ROC20": "close / delay(close, 20) - 1",
        "MA5": "mean(close, 5) / close - 1",
        "MA10": "mean(close, 10) / close - 1",
        "STD5": "std(close, 5) / close",
        "STD20": "std(close, 20) / close",
        "BETA5": "slope(close, 5) / close",
        "RSQR5": "rsquare(close, 5)",
        "RESI5": "residual(close, 5)",
        "MAX5": "max(high, 5) / close - 1",
        "MIN5": "min(low, 5) / close - 1",
        "QTLU5": "quantile(close, 5, 0.8) / close - 1",
        "QTLD5": "quantile(close, 5, 0.2) / close - 1",
        "TSRANK5": "ts_rank(close, 5)",
    }

    ALPHA191_SUBSET = {
        "gtja001": "-1 * correlation(rank(delta(log(volume), 1)), rank(delta(close, 1)), 6)",
        "gtja002": "-1 * delta(close, 1)",
        "gtja004": "-1 * ts_rank(rank(low), 9)",
    }

    @classmethod
    def get_all_expressions(cls):
        all_factors = {}
        all_factors.update(cls.ALPHA101_SUBSET)
        all_factors.update(cls.ALPHA158_SUBSET)
        all_factors.update(cls.ALPHA191_SUBSET)
        return all_factors

    @classmethod
    def get_by_category(cls, category):
        if category == "alpha101":
            return cls.ALPHA101_SUBSET
        if category == "alpha158":
            return cls.ALPHA158_SUBSET
        if category == "alpha191":
            return cls.ALPHA191_SUBSET
        return {}

    @classmethod
    def batch_evaluate(cls, bars, categories=None):
        from app.backtest.signal_dsl import SignalDSL
        if categories is None:
            categories = ["alpha101", "alpha158", "alpha191"]

        dsl = SignalDSL(bars)
        results = {}

        for cat in categories:
            factors = cls.get_by_category(cat)
            for name, expr in factors.items():
                try:
                    score = dsl.evaluate(expr)
                    if score.abs().sum() > 1e-9:
                        val = score.iloc[-1]
                        if not (isinstance(val, float) and val != val):
                            results[name] = float(val)
                except Exception as e:
                    print(f"qweave factor {name} failed: {e}")
        return results

    @classmethod
    def batch_evaluate_series(cls, bars, categories=None):
        from app.backtest.signal_dsl import SignalDSL
        if categories is None:
            categories = ["alpha101", "alpha158", "alpha191"]

        dsl = SignalDSL(bars)
        results = {}

        for cat in categories:
            factors = cls.get_by_category(cat)
            for name, expr in factors.items():
                try:
                    score = dsl.evaluate(expr)
                    if score.abs().sum() > 1e-9:
                        results[name] = score
                except Exception as e:
                    print(f"qweave factor {name} failed: {e}")
        return results
```

**修復記錄**：第 3 輪對齊擴展後的 DSL。

---

## 5.5 `app/factors/orthogonalize.py`

**職責**：因子正交化（對稱 / 施密特 / PCA）。

```python
import numpy as np
import pandas as pd


class FactorOrthogonalizer:
    @staticmethod
    def symmetric(factors: pd.DataFrame) -> pd.DataFrame:
        X = factors.dropna()
        if X.empty or len(X) < 3:
            return factors

        X_std = (X - X.mean()) / (X.std() + 1e-9)
        cov = np.cov(X_std.T)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)

        idx = eigenvalues.argsort()[::-1]
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]

        D_inv_sqrt = np.diag(1.0 / np.sqrt(np.abs(eigenvalues) + 1e-9))
        S = eigenvectors @ D_inv_sqrt @ eigenvectors.T

        result = X_std.values @ S
        return pd.DataFrame(result, index=X_std.index, columns=factors.columns)

    @staticmethod
    def gram_schmidt(factors: pd.DataFrame, base_col: str | None = None) -> pd.DataFrame:
        X = factors.dropna()
        if X.empty:
            return factors

        cols = list(X.columns)
        if base_col and base_col in cols:
            cols.remove(base_col)
            cols = [base_col] + cols

        X_std = (X[cols] - X[cols].mean()) / (X[cols].std() + 1e-9)
        result = pd.DataFrame(index=X_std.index, columns=cols, dtype=float)

        for i, col in enumerate(cols):
            v = X_std[col].values.copy()
            for j in range(i):
                prev = result[cols[j]].values
                proj = (v @ prev) / (prev @ prev + 1e-9)
                v = v - proj * prev
            result[col] = v
        return result

    @staticmethod
    def pca(factors: pd.DataFrame, n_components: int | None = None) -> pd.DataFrame:
        X = factors.dropna()
        if X.empty:
            return factors

        X_std = (X - X.mean()) / (X.std() + 1e-9)
        cov = np.cov(X_std.T)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        idx = eigenvalues.argsort()[::-1]
        eigenvectors = eigenvectors[:, idx]

        if n_components is None:
            n_components = len(factors.columns)
        n_components = min(n_components, len(eigenvectors.T))
        components = eigenvectors[:, :n_components]
        result = X_std.values @ components

        cols = [f"PC{i + 1}" for i in range(n_components)]
        return pd.DataFrame(result, index=X_std.index, columns=cols)
```

**修復記錄**：第 2 輪賦值邏輯改為直接回傳。

---

## 5.6 `app/factors/inspect.py`

**職責**：因子診斷（IC / 分層 / 衰減）。

```python
import pandas as pd
import numpy as np


class FactorInspector:
    def __init__(self, bars: pd.DataFrame, factors: pd.DataFrame, factor_cols: list[str]):
        self.bars = bars.copy().sort_values("timestamp").reset_index(drop=True)
        self.factors = factors.copy()
        self.factor_cols = factor_cols
        self.fwd_ret = self.bars["close"].pct_change().shift(-1)

    def compute_ic(self, period: int = 1) -> pd.DataFrame:
        results = []
        fwd = self.bars["close"].pct_change(period).shift(-period)

        for col in self.factor_cols:
            if col not in self.factors.columns:
                continue
            f = self.factors[col].reindex(self.bars.index)
            valid = f.notna() & fwd.notna()
            if valid.sum() < 20:
                continue
            ic = f[valid].corr(fwd[valid])
            rank_ic = f[valid].rank().corr(fwd[valid].rank())
            results.append({
                "factor": col, "IC": round(ic, 6),
                "Rank_IC": round(rank_ic, 6),
                "ICIR": round(ic / (f.std() + 1e-9), 4), "period": period,
            })
        return pd.DataFrame(results)

    def layer_returns(self, factor_col: str, n_layers: int = 5) -> pd.DataFrame:
        f = self.factors[factor_col].reindex(self.bars.index)
        try:
            layers = pd.qcut(f, n_layers, labels=False, duplicates="drop")
        except Exception:
            return pd.DataFrame()

        results = []
        for layer in range(n_layers):
            mask = layers == layer
            ret = self.fwd_ret[mask].mean()
            results.append({"layer": layer + 1,
                            "mean_return": round(ret, 6),
                            "count": int(mask.sum())})
        return pd.DataFrame(results)

    def factor_decay(self, factor_col: str, max_period: int = 20) -> pd.DataFrame:
        f = self.factors[factor_col].reindex(self.bars.index)
        results = []
        for p in range(1, max_period + 1):
            fwd = self.bars["close"].pct_change(p).shift(-p)
            valid = f.notna() & fwd.notna()
            if valid.sum() < 20:
                continue
            ic = f[valid].corr(fwd[valid])
            results.append({"period": p, "IC": round(ic, 6)})
        return pd.DataFrame(results)

    def full_report(self, factor_col: str) -> dict:
        return {
            "ic": self.compute_ic(1).to_dict("records"),
            "ic_5d": self.compute_ic(5).to_dict("records"),
            "ic_20d": self.compute_ic(20).to_dict("records"),
            "layers": self.layer_returns(factor_col).to_dict("records"),
            "decay": self.factor_decay(factor_col).to_dict("records"),
        }
```

---

# 本批次完成

**已交付 22 個模組**：
- Part 1 核心層：6 個
- Part 2 數據層：5 個
- Part 3 回測層：5 個
- Part 4 風控層：2 個
- Part 5 因子層：6 個（含 `__init__`）

**下一批次（批次 3）**：Agent 層、組合層、執行層、審計層、監控層、研究層、記憶層、API 層、歸檔說明。

---

# 模組完整程式碼 — Part 6-11

本批次收錄：Agent 層、組合層、執行層、審計監控層、API 層、歸檔說明，共 20 個模組。

---

# Part 6：Agent 層

## 6.1 `app/agents/llm.py`

**職責**：統一 LLM 客戶端，含錯誤回覆格式。

```python
import httpx

from app.config import settings


class LLMClient:
    def __init__(self, base_url=None, api_key=None, model=None, timeout: float = 60.0):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.timeout = timeout

    async def chat(self, messages: list[dict], temperature: float = 0.2) -> str:
        if not self.api_key:
            last = messages[-1]["content"] if messages else ""
            return f"[MOCK LLM] {last[:800]}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                    },
                )
                r.raise_for_status()
                data = r.json()
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            return f"[LLM HTTP Error {e.response.status_code}] {e.response.text[:500]}"
        except httpx.TimeoutException:
            return f"[LLM Timeout after {self.timeout}s]"
        except Exception as e:
            return f"[LLM Error] {type(e).__name__}: {e}"
```

**修復記錄**：第 2 輪統一錯誤回覆格式。

---

## 6.2 `app/agents/analysts.py`

**職責**：多分析師 Agent，依市場自動生成對應角色。

```python
import json

from app.agents.llm import LLMClient
from app.domain.models import AnalystReport, Market


class AnalystAgent:
    def __init__(self, role: str, system_prompt: str, llm: LLMClient | None = None):
        self.role = role
        self.system_prompt = system_prompt
        self.llm = llm or LLMClient()

    async def analyze(self, symbol: str, market: Market, context: dict) -> AnalystReport:
        prompt = f"""
你是{self.role}。請分析 {market.value} 市場股票 {symbol}。

上下文數據：
{json.dumps(context, ensure_ascii=False, default=str)[:6000]}

請只輸出 JSON：
{{
  "summary": "一段話結論",
  "score": -1 到 1,
  "key_points": ["..."],
  "risks": ["..."]
}}
"""
        text = await self.llm.chat([
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt},
        ])

        data = self._extract_json(text) or {
            "summary": text[:500], "score": 0,
            "key_points": [], "risks": [],
        }

        return AnalystReport(
            role=self.role, symbol=symbol, market=market,
            summary=data.get("summary", "")[:1000],
            score=float(data.get("score", 0)),
            key_points=data.get("key_points", [])[:10],
            risks=data.get("risks", [])[:10],
        )

    @staticmethod
    def _extract_json(text):
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            pass
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
        return None


def build_analysts(market: Market) -> list[AnalystAgent]:
    analysts = [
        AnalystAgent("技術面分析師", "你擅長價量、趨勢、支撐壓力、動量與波動率。"),
        AnalystAgent("基本面分析師", "你擅長財報、估值、成長性、自由現金流與護城河。"),
        AnalystAgent("新聞情緒分析師", "你擅長新聞、社群情緒、事件驅動與市場敘事。"),
    ]

    if market == Market.TW:
        analysts += [
            AnalystAgent("三大法人籌碼分析師", "你專注外資、投信、自營商買賣超、融資融券與持股變化。"),
            AnalystAgent("當沖與量能分析師", "你分析當沖熱度、周轉率、隔日沖風險與量能結構。"),
        ]
    else:
        analysts += [
            AnalystAgent("期權市場分析師", "你分析 Put/Call Ratio、隱含波動率、期權持倉與市場預期。"),
            AnalystAgent("財報事件分析師", "你分析財報日曆、Earnings Surprise、指引變化與事件風險。"),
        ]
    return analysts
```

---

## 6.3 `app/agents/debate.py`

**職責**：多空辯論引擎，支援多輪辯論。

```python
from app.agents.llm import LLMClient
from app.domain.models import AnalystReport, DebateResult


class DebateEngine:
    def __init__(self, llm: LLMClient | None = None, n_rounds: int = 2):
        self.llm = llm or LLMClient()
        self.n_rounds = max(1, int(n_rounds))

    async def run(self, symbol: str, reports: list[AnalystReport]) -> DebateResult:
        report_text = "\n".join(
            [f"[{r.role}] {r.summary} (score={r.score})" for r in reports]
        )
        history = []
        bull = ""
        bear = ""

        for i in range(self.n_rounds):
            bull_prompt = f"基於以下分析報告，為 {symbol} 提出最強多頭論點。第 {i + 1} 輪。\n報告：\n{report_text}\n\n歷史辯論：\n{history}"
            bear_prompt = f"基於以下分析報告，為 {symbol} 提出最強空頭論點。第 {i + 1} 輪。\n報告：\n{report_text}\n\n歷史辯論：\n{history}"

            try:
                bull = await self.llm.chat([{"role": "user", "content": bull_prompt}])
            except Exception as e:
                bull = f"[多頭辯論失敗: {e}]"
            try:
                bear = await self.llm.chat([{"role": "user", "content": bear_prompt}])
            except Exception as e:
                bear = f"[空頭辯論失敗: {e}]"

            history.append({"round": i + 1, "bull": bull, "bear": bear})

        return DebateResult(bull_case=bull, bear_case=bear, rounds=history)
```

**修復記錄**：第 2 輪修正 `self.rounds` 參數名衝突（改 `n_rounds`）。

---

## 6.4 `app/agents/risk.py`

**職責**：風控審查 Agent，含 JSON 解析 fallback 與邊界檢查。

```python
import json

from app.agents.llm import LLMClient
from app.domain.models import DebateResult, RiskReview


class RiskAgent:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    async def review(self, symbol: str, debate: DebateResult) -> RiskReview:
        prompt = f"""
你是風險控制官。根據以下多空辯論，給出 {symbol} 的風控參數。

多頭：
{(debate.bull_case or "")[:1500]}

空頭：
{(debate.bear_case or "")[:1500]}

請只輸出 JSON：
{{
  "max_position_pct": 0.1,
  "stop_loss_pct": 0.08,
  "take_profit_pct": 0.2,
  "approved": true,
  "notes": "..."
}}
"""
        try:
            text = await self.llm.chat([{"role": "user", "content": prompt}])
        except Exception as e:
            return RiskReview(max_position_pct=0.05, stop_loss_pct=0.05,
                              take_profit_pct=0.15, approved=False,
                              notes=f"LLM 調用失敗: {e}")

        data = self._extract_json(text)
        if data is None:
            return RiskReview(max_position_pct=0.05, stop_loss_pct=0.05,
                              take_profit_pct=0.15, approved=False,
                              notes=f"無法解析風控輸出: {text[:300]}")

        return RiskReview(
            max_position_pct=min(max(float(data.get("max_position_pct", 0.1)), 0.0), 0.3),
            stop_loss_pct=min(max(float(data.get("stop_loss_pct", 0.08)), 0.01), 0.2),
            take_profit_pct=min(max(float(data.get("take_profit_pct", 0.2)), 0.02), 1.0),
            approved=bool(data.get("approved", False)),
            notes=str(data.get("notes", ""))[:1000],
        )

    @staticmethod
    def _extract_json(text: str):
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            pass
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
        return None
```

**修復記錄**：第 2 輪加入 JSON 解析 fallback；邊界檢查。

---

## 6.5 `app/agents/manager.py`

**職責**：投資組合經理 Agent，風控否決時短路。

```python
import json

from app.agents.llm import LLMClient
from app.agents.risk import RiskAgent
from app.domain.models import (
    AnalystReport, DebateResult, FinalDecision, Market, RiskReview,
)


class PortfolioManagerAgent:
    def __init__(self, llm: LLMClient | None = None):
        self.llm = llm or LLMClient()

    async def decide(self, symbol, market, reports, debate, risk) -> FinalDecision:
        if not risk.approved:
            return FinalDecision(
                symbol=symbol, market=market, action="AVOID",
                confidence=0.0, target_position_pct=0.0,
                thesis=f"風控未通過：{risk.notes}",
                reports=reports, debate=debate, risk=risk,
            )

        reports_dump = [
            r.model_dump() if hasattr(r, "model_dump") else r for r in reports
        ]

        prompt = f"""
你是投資組合經理。請根據以下資訊，對 {market.value}:{symbol} 做最終決策。

分析報告：
{json.dumps(reports_dump, ensure_ascii=False, default=str)[:5000]}

多空辯論：
{debate.model_dump_json()[:3000] if hasattr(debate, "model_dump_json") else str(debate)[:3000]}

風控：
{risk.model_dump_json() if hasattr(risk, "model_dump_json") else str(risk)}

請只輸出 JSON：
{{
  "action": "BUY/HOLD/SELL/AVOID",
  "confidence": 0 到 1,
  "target_position_pct": 0 到 1,
  "entry_price": null,
  "stop_loss": null,
  "take_profit": null,
  "thesis": "..."
}}
"""
        try:
            text = await self.llm.chat([{"role": "user", "content": prompt}])
        except Exception as e:
            return FinalDecision(symbol=symbol, market=market, action="HOLD",
                                 confidence=0.0, target_position_pct=0.0,
                                 thesis=f"LLM 調用失敗: {e}",
                                 reports=reports, debate=debate, risk=risk)

        data = RiskAgent._extract_json(text) or {}
        action = str(data.get("action", "HOLD")).upper()
        if action not in ("BUY", "HOLD", "SELL", "AVOID"):
            action = "HOLD"

        target_pct = min(
            max(float(data.get("target_position_pct", 0.0)), 0.0),
            risk.max_position_pct,
        )

        return FinalDecision(
            symbol=symbol, market=market, action=action,
            confidence=min(max(float(data.get("confidence", 0.5)), 0.0), 1.0),
            target_position_pct=target_pct,
            entry_price=data.get("entry_price"),
            stop_loss=data.get("stop_loss"),
            take_profit=data.get("take_profit"),
            thesis=str(data.get("thesis", text[:500]))[:2000],
            reports=reports, debate=debate, risk=risk,
        )
```

**修復記錄**：第 2 輪統一 JSON 解析；風控否決短路。

---

## 6.6 `app/agents/event_driven.py`

**職責**：事件驅動交易代理，整合新聞與技術面。

```python
import json
from datetime import datetime

from app.agents.llm import LLMClient
from app.domain.models import Market


def _to_dict(item) -> dict:
    if item is None:
        return {}
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "dict"):
        return item.dict()
    return {"value": str(item)}


class EventDrivenTrader:
    def __init__(self):
        self.llm = LLMClient()

    async def generate_decision(self, symbol, market, structured_data, news_items, portfolio_state) -> dict:
        tech = structured_data.get("technicals", {})
        price = structured_data.get("price", {})
        news_dicts = [_to_dict(n) for n in news_items]

        news_text = "\n".join([
            f"- [{n.get('source', 'unknown')}] {n.get('title', '')}: {str(n.get('summary', ''))[:200]}"
            for n in news_dicts[:10]
        ])

        prompt = f"""
你是事件驅動交易代理。根據以下多模態信息，對 {market.value}:{symbol} 生成交易決策。

=== 結構化市場數據 ===
最新價格: {price.get('last', 'N/A')}
日漲跌幅: {price.get('change_pct', 'N/A')}%
成交量: {price.get('volume', 'N/A')}
RSI(14): {tech.get('RSI', 'N/A')}
MACD: {tech.get('MACD', 'N/A')}
MA20: {tech.get('MA20', 'N/A')}
MA50: {tech.get('MA50', 'N/A')}

=== 非結構化新聞 ===
{news_text}

=== 當前持倉 ===
{json.dumps(portfolio_state, ensure_ascii=False, default=str)[:2000]}

請只輸出 JSON：
{{
  "action": "BUY/HOLD/SELL/AVOID",
  "confidence": 0-1,
  "position_size_pct": 0-0.3,
  "entry_price": 價格或null,
  "stop_loss": 價格或null,
  "take_profit": 價格或null,
  "key_catalyst": "驅動此決策的關鍵事件",
  "news_impact": "POSITIVE/NEGATIVE/NEUTRAL",
  "reasoning": "完整推理過程"
}}
"""
        text = await self.llm.chat([{"role": "user", "content": prompt}])

        try:
            decision = json.loads(text)
        except Exception:
            decision = {"action": "HOLD", "confidence": 0.3,
                        "position_size_pct": 0, "reasoning": text[:500]}

        decision["timestamp"] = datetime.now().isoformat()
        decision["symbol"] = symbol
        decision["market"] = market.value
        return decision

    async def batch_event_scan(self, symbols, market, data_provider):
        results = []
        today = datetime.now().strftime("%Y-%m-%d")

        for sym in symbols:
            try:
                bars = await data_provider.get_bars(sym, market, "2025-01-01", today)
                news = await data_provider.get_news(sym, market, limit=5)

                if bars is None or len(bars) == 0:
                    continue

                close = bars["close"]
                tech = {
                    "RSI": self._calc_rsi(close),
                    "MACD": self._calc_macd(close),
                    "MA20": float(close.rolling(20).mean().iloc[-1]),
                    "MA50": float(close.rolling(50).mean().iloc[-1]),
                }
                structured = {
                    "price": {
                        "last": float(close.iloc[-1]),
                        "change_pct": round(float(close.pct_change().iloc[-1] * 100), 2),
                        "volume": float(bars["volume"].iloc[-1]),
                    },
                    "technicals": tech,
                }

                news_dicts = [_to_dict(n) for n in news]
                decision = await self.generate_decision(sym, market, structured, news_dicts, {})
                results.append(decision)
            except Exception as e:
                results.append({"symbol": sym, "error": str(e)})

        return sorted(results, key=lambda x: x.get("confidence", 0), reverse=True)

    def _calc_rsi(self, close, n=14):
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(n).mean()
        loss = (-delta.clip(upper=0)).rolling(n).mean()
        rs = gain / (loss + 1e-9)
        return round(float(100 - 100 / (1 + rs).iloc[-1]), 2)

    def _calc_macd(self, close):
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        return round(float((ema12 - ema26).iloc[-1]), 4)
```

**修復記錄**：第 1 輪 `_to_dict` 統一轉換 pydantic / dict。

---

## 6.7 `app/agents/orchestrator.py`

**職責**：投資編排器，整合多分析師、辯論、風控、事件驅動、因子、記憶。

```python
from app.agents.analysts import build_analysts
from app.agents.debate import DebateEngine
from app.agents.event_driven import EventDrivenTrader, _to_dict
from app.agents.manager import PortfolioManagerAgent
from app.agents.risk import RiskAgent
from app.data.composite import CompositeProvider
from app.domain.models import Market


class InvestmentOrchestrator:
    def __init__(self):
        self.data = CompositeProvider()
        self.debate = DebateEngine()
        self.risk = RiskAgent()
        self.manager = PortfolioManagerAgent()
        self.event_trader = EventDrivenTrader()

    async def analyze(self, symbol, market, start, end,
                      use_event_driven=True, use_memory=True) -> dict:
        bars = await self.data.get_bars(symbol, market, start, end)
        fundamentals = await self.data.get_fundamentals(symbol, market)
        news = await self.data.get_news(symbol, market, limit=20)

        context = {
            "bars_tail": (bars.tail(60).to_dict("records")
                          if bars is not None and not bars.empty else []),
            "fundamentals": fundamentals,
            "news": [_to_dict(n) for n in news],
        }

        # 因子層（可選）
        try:
            from app.factors.registry import FactorRegistry
            from app.backtest.signal_dsl import SignalDSL
            if bars is not None and not bars.empty:
                registry = FactorRegistry()
                production = registry.get_production_factors(market.value)
                if production:
                    dsl = SignalDSL(bars)
                    factor_values = {}
                    for f in production[:20]:
                        try:
                            score = dsl.evaluate(f["expr"])
                            factor_values[f["name"]] = float(score.iloc[-1])
                        except Exception:
                            continue
                    context["active_factors"] = factor_values
        except Exception as e:
            context["factor_error"] = str(e)

        # 台股籌碼 / 美股期權（可選）
        try:
            if market == Market.TW and bars is not None and not bars.empty:
                from app.factors.tw_chips import TWChipsFactorEngine
                chips = TWChipsFactorEngine().compute_factors(symbol, start, end)
                if chips is not None and not chips.empty:
                    context["chip_factors"] = chips.tail(20).to_dict("records")
            if market == Market.US:
                from app.factors.us_options import USOptionsFactorEngine
                context["option_factors"] = USOptionsFactorEngine().compute_factors(symbol)
        except Exception as e:
            context["extra_factor_error"] = str(e)

        # 記憶層（可選）
        if use_memory:
            try:
                from app.memory.trade_memory import TradeMemoryLayer
                memory = TradeMemoryLayer()
                context["similar_trades"] = memory.recall_similar_trades(symbol=symbol, limit=5)
                context["discipline_drift"] = memory.get_discipline_drift()
            except Exception as e:
                context["memory_error"] = str(e)

        # 多分析師
        analysts = build_analysts(market)
        reports = []
        for agent in analysts:
            try:
                reports.append(await agent.analyze(symbol, market, context))
            except Exception as e:
                from app.domain.models import AnalystReport
                reports.append(AnalystReport(
                    role=agent.role, symbol=symbol, market=market,
                    summary=f"分析失敗: {e}", score=0.0,
                    key_points=[], risks=[str(e)],
                ))

        # 辯論
        try:
            debate = await self.debate.run(symbol, reports)
        except Exception as e:
            from app.domain.models import DebateResult
            debate = DebateResult(bull_case=f"辯論失敗: {e}", bear_case="", rounds=[])

        # 風控
        try:
            risk = await self.risk.review(symbol, debate)
        except Exception as e:
            from app.domain.models import RiskReview
            risk = RiskReview(max_position_pct=0.1, stop_loss_pct=0.08,
                              take_profit_pct=0.2, approved=False,
                              notes=f"風控失敗: {e}")

        # 事件驅動
        event_decision = None
        if use_event_driven and bars is not None and not bars.empty:
            try:
                structured = self._build_structured(bars)
                event_decision = await self.event_trader.generate_decision(
                    symbol, market, structured,
                    [_to_dict(n) for n in news], {},
                )
                context["event_driven_decision"] = event_decision
            except Exception as e:
                event_decision = {"error": str(e)}

        # 最終決策
        try:
            decision = await self.manager.decide(symbol, market, reports, debate, risk)
        except Exception as e:
            from app.domain.models import FinalDecision
            decision = FinalDecision(
                symbol=symbol, market=market, action="HOLD",
                confidence=0.0, target_position_pct=0.0,
                thesis=f"經理決策失敗: {e}",
                reports=reports, debate=debate, risk=risk,
            )

        result = decision.model_dump() if hasattr(decision, "model_dump") else decision
        result["event_driven"] = event_decision
        return result

    def _build_structured(self, bars) -> dict:
        close = bars["close"]
        return {
            "price": {
                "last": float(close.iloc[-1]),
                "change_pct": round(float(close.pct_change().iloc[-1] * 100), 2),
                "volume": float(bars["volume"].iloc[-1]),
            },
            "technicals": {
                "RSI": self._rsi(close), "MACD": self._macd(close),
                "MA20": float(close.rolling(20).mean().iloc[-1]),
                "MA50": float(close.rolling(50).mean().iloc[-1]),
            },
        }

    def _rsi(self, close, n=14):
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(n).mean()
        loss = (-delta.clip(upper=0)).rolling(n).mean()
        rs = gain / (loss + 1e-9)
        return round(float(100 - 100 / (1 + rs).iloc[-1]), 2)

    def _macd(self, close):
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        return round(float((ema12 - ema26).iloc[-1]), 4)
```

**修復記錄**：第 2 輪整合因子層 / 記憶層 / 事件驅動；全面容錯。

---

## 6.8 `app/agents/nl_trader.py`

**職責**：自然語言下單，意圖解析 + 風控 + 審計。

```python
import json
from datetime import datetime

from app.agents.llm import LLMClient
from app.domain.models import Market, Side


class NLTrader:
    def __init__(self):
        self.llm = LLMClient()
        self.audit_log: list[dict] = []

    async def parse_intent(self, text: str, portfolio_context: dict) -> dict:
        prompt = f"""
你是交易意圖解析器。將用戶的自然語言指令轉為結構化訂單意圖。

用戶指令：{text}

當前持倉：
{json.dumps(portfolio_context, ensure_ascii=False, default=str)[:3000]}

請只輸出 JSON：
{{
  "action": "BUY/SELL/HOLD/CANCEL_ALL",
  "symbol": "股票代碼",
  "market": "TW/US",
  "qty": 數量（整數）,
  "order_type": "MKT/LMT",
  "limit_price": 限價（可選）,
  "reasoning": "解析理由"
}}
"""
        response = await self.llm.chat([{"role": "user", "content": prompt}])
        try:
            intent = json.loads(response)
        except Exception:
            intent = {"action": "HOLD", "reasoning": response[:300]}

        intent["portfolio_value"] = portfolio_context.get("portfolio_value", 1_000_000)
        intent["current_position_value"] = portfolio_context.get("current_position_value", 0)
        intent["current_equity"] = portfolio_context.get("current_equity", 1_000_000)

        self.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "input": text, "intent": intent, "stage": "parsed",
        })
        return intent

    async def execute(self, intent, risk_guard, broker_tw, broker_us, dry_run=True) -> dict:
        action = intent.get("action", "HOLD")

        if action == "HOLD":
            return {"executed": False, "reason": "no action needed"}

        if action == "CANCEL_ALL":
            self.audit_log.append({
                "timestamp": datetime.now().isoformat(),
                "action": "CANCEL_ALL", "stage": "executed",
            })
            return {"executed": True, "action": "CANCEL_ALL"}

        check = risk_guard.check_order(
            symbol=intent.get("symbol", ""), side=action,
            qty=intent.get("qty", 0),
            price=intent.get("limit_price", 0) or 0,
            portfolio_value=intent["portfolio_value"],
            current_position_value=intent["current_position_value"],
            current_equity=intent["current_equity"],
        )

        if not check["approved"]:
            self.audit_log.append({
                "timestamp": datetime.now().isoformat(),
                "intent": intent, "risk_check": check, "stage": "blocked",
            })
            return {"executed": False, "reason": check["reason"]}

        adjusted_qty = check.get("adjusted_qty", intent.get("qty", 0))

        if dry_run:
            self.audit_log.append({
                "timestamp": datetime.now().isoformat(),
                "intent": intent, "adjusted_qty": adjusted_qty, "stage": "dry_run",
            })
            return {"executed": False, "dry_run": True,
                    "intent": intent, "adjusted_qty": adjusted_qty}

        market = Market(intent.get("market", "TW"))
        side = Side(action)

        if market == Market.TW:
            result = broker_tw.place_order(
                intent["symbol"], side, intent.get("limit_price", 0), adjusted_qty,
            )
        else:
            result = broker_us.place_order(
                intent["symbol"], side, adjusted_qty,
                intent.get("order_type", "MKT"), intent.get("limit_price"),
            )

        self.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "intent": intent, "result": result, "stage": "executed",
        })
        return {"executed": True, "result": result}

    def get_audit_log(self, limit: int = 100) -> list[dict]:
        return self.audit_log[-limit:]
```

**修復記錄**：第 1 輪 `portfolio_value` 注入修正。

---

# Part 7：組合層

## 7.1 `app/portfolio/optimizer.py`

**職責**：組合優化，支援 HRP / 風險平價 / 最大分散化 / 均值-風險，含 skfolio 與 numpy 雙實現。

```python
import numpy as np
import pandas as pd

from app.data.warehouse import MarketWarehouse


class PortfolioOptimizer:
    def __init__(self):
        self.warehouse = MarketWarehouse()
        self._skfolio_available = self._check_skfolio()

    def _check_skfolio(self) -> bool:
        try:
            import skfolio  # noqa: F401
            return True
        except ImportError:
            return False

    def load_returns(self, symbols, market, start, end) -> pd.DataFrame:
        frames = {}
        for sym in symbols:
            bars = self.warehouse.query_bars(sym, market, start, end)
            if bars is None or bars.empty:
                continue
            bars = bars.set_index("timestamp").sort_index()
            frames[sym] = bars["close"].pct_change()
        if not frames:
            return pd.DataFrame()
        return pd.DataFrame(frames).dropna(how="all").fillna(0)

    def optimize(self, returns, method="hrp", risk_measure="cvar", max_weight=0.3) -> dict:
        if returns.empty or len(returns.columns) < 2:
            return {"error": "need at least 2 assets"}
        if self._skfolio_available:
            try:
                return self._optimize_skfolio(returns, method, risk_measure, max_weight)
            except Exception as e:
                print(f"skfolio failed, fallback to numpy: {e}")
        return self._optimize_numpy(returns, method, max_weight)

    def _optimize_skfolio(self, returns, method, risk_measure, max_weight) -> dict:
        from skfolio.optimization import (
            MeanRisk, HierarchicalRiskParity, RiskBudgeting, MaximumDiversification,
        )
        from skfolio.risk_measures import CVaR, Variance

        if method == "hrp":
            model = HierarchicalRiskParity()
        elif method == "risk_budgeting":
            model = RiskBudgeting()
        elif method == "max_diversification":
            model = MaximumDiversification()
        elif method == "mean_risk":
            rm = CVaR() if risk_measure == "cvar" else Variance()
            model = MeanRisk(risk_measure=rm, max_weights=max_weight)
        else:
            model = HierarchicalRiskParity()

        model.fit(returns)
        weights = np.asarray(model.weights_)
        return self._summarize(returns, weights, method)

    def _optimize_numpy(self, returns, method, max_weight) -> dict:
        n = len(returns.columns)
        if method == "hrp":
            weights = self._hrp_numpy(returns)
        elif method == "risk_budgeting":
            weights = self._risk_parity_numpy(returns)
        elif method == "max_diversification":
            weights = self._max_div_numpy(returns)
        else:
            weights = self._equal_weight(n)

        weights = np.minimum(weights, max_weight)
        weights = weights / (weights.sum() + 1e-9)
        return self._summarize(returns, weights, f"{method}_numpy")

    def _hrp_numpy(self, returns) -> np.ndarray:
        cov = returns.cov().values
        n = cov.shape[0]
        std = np.sqrt(np.diag(cov))
        corr = cov / (np.outer(std, std) + 1e-9)
        dist = np.sqrt(np.clip((1 - corr) / 2, 0, 1))

        from scipy.cluster.hierarchy import linkage, leaves_list
        from scipy.spatial.distance import squareform

        condensed = squareform(dist, checks=False)
        link = linkage(condensed, method="single")
        order = leaves_list(link)

        weights = np.ones(n)
        clusters = [list(order)]

        while clusters:
            new_clusters = []
            for cluster in clusters:
                if len(cluster) <= 1:
                    continue
                mid = len(cluster) // 2
                left, right = cluster[:mid], cluster[mid:]

                var_left = self._cluster_var(cov, left)
                var_right = self._cluster_var(cov, right)
                total = var_left + var_right + 1e-9
                alpha = 1 - var_left / total

                for i in left:
                    weights[i] *= alpha
                for i in right:
                    weights[i] *= (1 - alpha)

                new_clusters.extend([left, right])
            clusters = new_clusters

        return weights / (weights.sum() + 1e-9)

    def _cluster_var(self, cov, indices) -> float:
        sub = cov[np.ix_(indices, indices)]
        w = np.ones(len(indices)) / len(indices)
        return float(w @ sub @ w)

    def _risk_parity_numpy(self, returns) -> np.ndarray:
        cov = returns.cov().values
        n = cov.shape[0]
        w = np.ones(n) / n

        for _ in range(200):
            marginal = cov @ w
            rc = w * marginal
            target = rc.mean()
            w = w * (target / (rc + 1e-9))
            w = w / (w.sum() + 1e-9)
        return w

    def _max_div_numpy(self, returns) -> np.ndarray:
        cov = returns.cov().values
        vols = np.sqrt(np.diag(cov))
        inv_vol = 1 / (vols + 1e-9)
        w = inv_vol / inv_vol.sum()

        for _ in range(50):
            marginal = cov @ w
            grad = vols / (np.sqrt(w @ cov @ w) + 1e-9) - marginal
            w = w + 0.01 * grad
            w = np.maximum(w, 1e-6)
            w = w / w.sum()
        return w

    def _equal_weight(self, n) -> np.ndarray:
        return np.ones(n) / n

    def _summarize(self, returns, weights, method) -> dict:
        portfolio_ret = (returns * weights).sum(axis=1)
        cum_ret = (1 + portfolio_ret).cumprod()

        sharpe = float(portfolio_ret.mean() / (portfolio_ret.std() + 1e-9) * (252 ** 0.5))
        max_dd = float(((cum_ret / cum_ret.cummax()) - 1).min())

        return {
            "method": method,
            "weights": {col: round(float(w), 4)
                        for col, w in zip(returns.columns, weights)},
            "metrics": {
                "sharpe": round(sharpe, 4),
                "total_return": round(float(cum_ret.iloc[-1] - 1), 4),
                "max_drawdown": round(max_dd, 4),
                "annual_volatility": round(float(portfolio_ret.std() * (252 ** 0.5)), 4),
            },
        }
```

**修復記錄**：第 3 輪加入 numpy fallback；skfolio 失敗不崩潰。

---

# Part 8：執行層

## 8.1 `app/execution/reasoning_engine.py`

**職責**：執行前 LLM 推理過濾 + 市場狀態檢測。

```python
import json

import numpy as np
import pandas as pd

from app.agents.llm import LLMClient


class ReasoningEngine:
    def __init__(self):
        self.llm = LLMClient()

    async def filter_order(self, symbol, side, qty, price, market_context, risk_state) -> dict:
        prompt = f"""
你是執行層推理引擎。判斷以下訂單是否應該執行。

訂單：{side} {symbol} x{qty} @ {price}
市場狀態：{market_context.get('regime', 'unknown')}
當前回撤：{risk_state.get('current_drawdown', 0):.2%}
單日盈虧：{risk_state.get('daily_pnl', 0):.2%}

請只輸出 JSON：
{{
  "decision": "APPROVE/REJECT/MODIFY",
  "reason": "理由",
  "adjusted_qty": 數量,
  "urgency": "HIGH/MEDIUM/LOW"
}}
"""
        try:
            text = await self.llm.chat([{"role": "user", "content": prompt}])
        except Exception as e:
            return {"decision": "APPROVE", "reason": f"LLM 失敗，默認通過: {e}",
                    "adjusted_qty": qty, "urgency": "MEDIUM"}

        data = self._extract_json(text)
        if data is None:
            return {"decision": "APPROVE", "reason": f"解析失敗，默認通過: {text[:200]}",
                    "adjusted_qty": qty, "urgency": "MEDIUM"}

        if "adjusted_qty" not in data:
            data["adjusted_qty"] = qty
        return data

    @staticmethod
    def _extract_json(text: str):
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            pass
        import re
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except Exception:
                pass
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
        return None


class MarketRegimeDetector:
    @staticmethod
    def detect(bars: pd.DataFrame, lookback: int = 60) -> dict:
        if bars is None or bars.empty or len(bars) < lookback:
            return {"regime": "unknown", "volatility": 0.0,
                    "trend": 0.0, "recommended_position_scale": 0.5}

        close = bars["close"].tail(lookback)
        returns = close.pct_change().dropna()

        vol = float(returns.std() * np.sqrt(252))
        vol_median = float(returns.rolling(max(lookback // 2, 2)).std().median() * np.sqrt(252))

        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else ma20
        trend = float((ma20 - ma60) / (ma60 + 1e-9))

        is_high_vol = vol > vol_median * 1.3 if vol_median > 0 else False

        if abs(trend) < 0.02:
            regime = "sideways"
        elif trend > 0:
            regime = "high_vol_bull" if is_high_vol else "low_vol_bull"
        else:
            regime = "high_vol_bear" if is_high_vol else "low_vol_bear"

        return {
            "regime": regime,
            "volatility": round(vol, 4),
            "trend": round(trend, 4),
            "recommended_position_scale": (
                0.5 if "high_vol" in regime
                else 0.7 if regime == "sideways"
                else 1.0
            ),
        }
```

**修復記錄**：第 2 輪補 numpy / pandas import；JSON 解析統一。

---

## 8.2 `app/broker/shioaji_bridge.py`

**職責**：Shioaji 台股交易橋接，支援 TSE + OTC 雙查找與 CA 憑證。

```python
from app.domain.models import Market, Side


class ShioajiBridge:
    def __init__(self, simulation=True, api_key="", secret_key="",
                 person_id="", passwd="", ca_path="", ca_passwd=""):
        self.simulation = simulation
        self.api_key = api_key
        self.secret_key = secret_key
        self.person_id = person_id
        self.passwd = passwd
        self.ca_path = ca_path
        self.ca_passwd = ca_passwd
        self.api = None

    def connect(self):
        try:
            import shioaji as sj
        except ImportError:
            raise ImportError("pip install shioaji")

        self.api = sj.Shioaji(simulation=self.simulation)

        if self.simulation:
            self.api.login(
                person_id=self.person_id or "PERSON_ID",
                passwd=self.passwd or "PASSWORD",
            )
        else:
            if not self.api_key or not self.secret_key:
                raise ValueError("實盤模式需要 api_key 和 secret_key")
            self.api.login(api_key=self.api_key, secret_key=self.secret_key)
            if self.ca_path:
                self.api.activate_ca(ca_path=self.ca_path,
                                     ca_passwd=self.ca_passwd,
                                     person_id=self.person_id)
        return self.api

    def place_order(self, symbol, side, price, qty,
                    price_type="LMT", order_type="ROD") -> dict:
        import shioaji as sj
        if self.api is None:
            self.connect()

        contract = None
        for exchange in [self.api.Contracts.Stocks.TSE, self.api.Contracts.Stocks.OTC]:
            if symbol in exchange:
                contract = exchange[symbol]
                break

        if contract is None:
            return {"error": f"contract not found: {symbol}"}

        action = sj.constant.Action.Buy if side == Side.BUY else sj.constant.Action.Sell
        order = self.api.Order(
            action=action, price=price, quantity=qty,
            price_type=getattr(sj.constant.StockPriceType, price_type),
            order_type=getattr(sj.constant.TFTOrderType, order_type),
            account=self.api.stock_account,
        )
        trade = self.api.place_order(contract, order)

        return {
            "order_id": str(trade.order.id),
            "symbol": symbol, "side": side.value,
            "price": price, "qty": qty,
            "status": str(trade.status.status),
            "simulation": self.simulation,
        }

    def get_positions(self) -> list[dict]:
        if self.api is None:
            self.connect()
        positions = []
        try:
            for p in self.api.list_positions(self.api.stock_account):
                positions.append({"symbol": p.code, "qty": p.quantity,
                                  "price": p.price, "pnl": p.pnl})
        except Exception as e:
            return [{"error": str(e)}]
        return positions

    def cancel_order(self, order_id: str) -> bool:
        if self.api is None:
            self.connect()
        try:
            self.api.cancel_order(self.api.stock_account, order_id)
            return True
        except Exception:
            return False
```

**修復記錄**：第 2 輪支援 TSE + OTC 雙查找；補完 CA 憑證啟用。

---

## 8.3 `app/broker/ibkr_bridge.py`

**職責**：IBKR 美股交易橋接，Paper Trading 優先。

```python
from app.domain.models import Side


class IBKRBridge:
    def __init__(self, host="127.0.0.1", port=4002, client_id=1, paper=True):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.paper = paper
        self.ib = None

    def connect(self):
        try:
            from ib_insync import IB
        except ImportError:
            raise ImportError("pip install ib_insync")

        self.ib = IB()
        self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=20)
        return self.ib

    def disconnect(self):
        if self.ib is not None and self.ib.isConnected():
            self.ib.disconnect()

    def place_order(self, symbol, side, qty, order_type="MKT", limit_price=None) -> dict:
        from ib_insync import Stock, MarketOrder, LimitOrder
        if self.ib is None or not self.ib.isConnected():
            self.connect()

        contract = Stock(symbol, "SMART", "USD")
        self.ib.qualifyContracts(contract)

        if order_type == "LMT" and limit_price:
            order = LimitOrder(side.value, qty, limit_price)
        else:
            order = MarketOrder(side.value, qty)

        trade = self.ib.placeOrder(contract, order)
        return {
            "order_id": trade.order.orderId,
            "symbol": symbol, "side": side.value, "qty": qty,
            "order_type": order_type,
            "status": trade.orderStatus.status,
            "paper": self.paper,
        }

    def get_positions(self) -> list[dict]:
        if self.ib is None or not self.ib.isConnected():
            self.connect()
        return [
            {"symbol": p.contract.symbol,
             "qty": float(p.position),
             "avg_cost": float(p.avgCost)}
            for p in self.ib.positions()
        ]

    def cancel_order(self, order_id: int) -> bool:
        if self.ib is None or not self.ib.isConnected():
            self.connect()
        for trade in self.ib.trades():
            if trade.order.orderId == order_id:
                self.ib.cancelOrder(trade.order)
                return True
        return False
```

**修復記錄**：第 2 輪加入 `isConnected()` 檢查；補 `disconnect()`。

---

# Part 9：審計與監控層

## 9.1 `app/audit/verifiable_log.py`

**職責**：可驗證審計日誌，SHA-256 哈希鏈 + Merkle 根。

```python
import hashlib
import json
from datetime import datetime
from pathlib import Path


class VerifiableAuditLog:
    def __init__(self, log_path: str = "./data_lake/audit/events.jsonl"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._prev_hash = self._load_last_hash()

    def _load_last_hash(self) -> str:
        if not self.log_path.exists():
            return "0" * 64
        last_hash = "0" * 64
        with open(self.log_path) as f:
            for line in f:
                try:
                    record = json.loads(line)
                    last_hash = record.get("hash", last_hash)
                except Exception:
                    continue
        return last_hash

    def append(self, event_type: str, data: dict) -> dict:
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type, "data": data,
            "prev_hash": self._prev_hash,
        }
        canonical = json.dumps(event, sort_keys=True, default=str)
        event["hash"] = hashlib.sha256(canonical.encode()).hexdigest()

        with open(self.log_path, "a") as f:
            f.write(json.dumps(event, default=str) + "\n")

        self._prev_hash = event["hash"]
        return event

    def log_decision(self, symbol, action, reasoning, signal_sources):
        return self.append("TRADE_DECISION", {
            "symbol": symbol, "action": action,
            "reasoning": reasoning, "signal_sources": signal_sources,
        })

    def log_order(self, order_id, symbol, side, qty, price, status):
        return self.append("ORDER_EVENT", {
            "order_id": order_id, "symbol": symbol, "side": side,
            "qty": qty, "price": price, "status": status,
        })

    def log_risk_check(self, symbol, approved, reason):
        return self.append("RISK_CHECK", {
            "symbol": symbol, "approved": approved, "reason": reason,
        })

    def build_merkle_root(self, start_idx: int = 0, end_idx: int | None = None) -> str:
        hashes = []
        with open(self.log_path) as f:
            for i, line in enumerate(f):
                if i < start_idx:
                    continue
                if end_idx and i >= end_idx:
                    break
                try:
                    hashes.append(json.loads(line).get("hash", ""))
                except Exception:
                    continue

        if not hashes:
            return "0" * 64

        while len(hashes) > 1:
            if len(hashes) % 2 == 1:
                hashes.append(hashes[-1])
            hashes = [
                hashlib.sha256((hashes[i] + hashes[i + 1]).encode()).hexdigest()
                for i in range(0, len(hashes), 2)
            ]
        return hashes[0]

    def verify_integrity(self) -> dict:
        prev_hash = "0" * 64
        errors = []
        count = 0

        if not self.log_path.exists():
            return {"total_records": 0, "errors": 0, "valid": True, "error_details": []}

        with open(self.log_path) as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    errors.append({"line": i, "error": "json parse failed"})
                    continue

                if record.get("prev_hash") != prev_hash:
                    errors.append({"line": i, "error": "hash chain broken",
                                   "expected": prev_hash,
                                   "actual": record.get("prev_hash")})

                actual_hash = record.get("hash")
                check = {k: v for k, v in record.items() if k != "hash"}
                canonical = json.dumps(check, sort_keys=True, default=str)
                expected_hash = hashlib.sha256(canonical.encode()).hexdigest()

                if actual_hash != expected_hash:
                    errors.append({"line": i, "error": "hash mismatch",
                                   "expected": expected_hash,
                                   "actual": actual_hash})

                prev_hash = actual_hash or prev_hash
                count += 1

        return {"total_records": count, "errors": len(errors),
                "valid": len(errors) == 0, "error_details": errors[:10]}
```

**修復記錄**：第 2 輪哈希驗證邏輯修正。

---

## 9.2 `app/monitoring/watchdog.py`

**職責**：心跳監控（dead-man's switch），支援同步與異步。

```python
import asyncio
import functools
import threading
import time
from datetime import datetime


class TradingWatchdog:
    def __init__(self, alert_urls: list[str] | None = None):
        self.alert_urls = alert_urls or []
        self._watchdogs: dict[str, datetime] = {}
        self._watchdog_started: set[str] = set()
        self._ops = None
        self._lock = threading.Lock()

    def _fire_alert(self, name: str, elapsed: float):
        msg = f"[CRITICAL] {name} 已 {elapsed:.0f} 秒無心跳。時間：{datetime.now().isoformat()}"
        print(msg)
        if self._ops:
            try:
                self._ops.fire_critical(msg)
            except Exception:
                pass

    def monitor(self, name: str, timeout_seconds: float = 30.0):
        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                with self._lock:
                    self._watchdogs[name] = datetime.now()

                if name not in self._watchdog_started:
                    self._watchdog_started.add(name)

                    def watchdog_loop():
                        while True:
                            time.sleep(timeout_seconds / 2)
                            with self._lock:
                                last = self._watchdogs.get(name)
                            if last:
                                elapsed = (datetime.now() - last).total_seconds()
                                if elapsed > timeout_seconds:
                                    self._fire_alert(name, elapsed)

                    t = threading.Thread(target=watchdog_loop, daemon=True)
                    t.start()

                return func(*args, **kwargs)
            return wrapper
        return decorator

    def instrument_async(self, name: str, timeout_seconds: float = 30.0):
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                self._watchdogs[name] = datetime.now()

                if name not in self._watchdog_started:
                    self._watchdog_started.add(name)

                    async def watchdog_loop():
                        while True:
                            await asyncio.sleep(timeout_seconds / 2)
                            last = self._watchdogs.get(name)
                            if last:
                                elapsed = (datetime.now() - last).total_seconds()
                                if elapsed > timeout_seconds:
                                    self._fire_alert(name, elapsed)

                    asyncio.create_task(watchdog_loop())

                return await func(*args, **kwargs)
            return wrapper
        return decorator
```

**修復記錄**：第 2 輪異步監控補完。

---

## 9.3 `app/research/rigor.py`

**職責**：研究紀律層，排列檢驗 + 多重檢驗校正。

```python
import numpy as np


class ResearchRigor:
    def __init__(self, min_samples: int = 30):
        self.min_samples = min_samples
        self.test_ledger: list[dict] = []

    def permutation_test(self, factor_values, forward_returns,
                         n_permutations=1000, alternative="two-sided") -> dict:
        valid = ~(np.isnan(factor_values) | np.isnan(forward_returns))
        f = factor_values[valid]
        r = forward_returns[valid]

        n = len(f)
        if n < self.min_samples:
            return {"test": "permutation", "status": "INSUFFICIENT_SAMPLES",
                    "n": n, "min_required": self.min_samples}

        from scipy.stats import spearmanr
        actual_ic, _ = spearmanr(f, r)

        perm_ics = np.zeros(n_permutations)
        for i in range(n_permutations):
            perm_r = np.random.permutation(r)
            perm_ic, _ = spearmanr(f, perm_r)
            perm_ics[i] = perm_ic

        if alternative == "two-sided":
            p_value = np.mean(np.abs(perm_ics) >= np.abs(actual_ic))
        elif alternative == "greater":
            p_value = np.mean(perm_ics >= actual_ic)
        else:
            p_value = np.mean(perm_ics <= actual_ic)

        result = {
            "test": "permutation",
            "actual_ic": round(float(actual_ic), 6),
            "perm_mean": round(float(np.mean(perm_ics)), 6),
            "perm_std": round(float(np.std(perm_ics)), 6),
            "p_value": round(float(p_value), 6),
            "n_samples": n, "n_permutations": n_permutations,
            "significant": bool(p_value < 0.05),
        }
        self.test_ledger.append(result)
        return result

    def multiple_testing_correction(self, method: str = "bh") -> dict:
        if not self.test_ledger:
            return {"error": "no tests in ledger"}

        p_values = [t["p_value"] for t in self.test_ledger if "p_value" in t]
        n_tests = len(p_values)
        if n_tests == 0:
            return {"error": "no valid p-values"}

        if method == "bonferroni":
            corrected = [min(p * n_tests, 1.0) for p in p_values]
        elif method == "bh":
            sorted_idx = np.argsort(p_values)
            sorted_p = np.array(p_values)[sorted_idx]
            corrected_sorted = sorted_p * n_tests / (np.arange(n_tests) + 1)
            corrected_sorted = np.minimum.accumulate(corrected_sorted[::-1])[::-1]
            corrected = np.zeros(n_tests)
            corrected[sorted_idx] = corrected_sorted
        else:
            corrected = p_values

        results = []
        for i, t in enumerate(self.test_ledger):
            if "p_value" not in t:
                continue
            results.append({
                "factor": t.get("factor", f"test_{i}"),
                "raw_p": t["p_value"],
                "corrected_p": round(float(corrected[i]), 6),
                "significant_after_correction": bool(corrected[i] < 0.05),
            })

        return {"method": method, "n_tests": n_tests, "results": results,
                "bonferroni_threshold": 0.05 / n_tests}

    def full_report(self, factor_name, factor_values, forward_returns) -> dict:
        perm = self.permutation_test(factor_values, forward_returns)
        correction = self.multiple_testing_correction()
        return {
            "factor": factor_name,
            "permutation_test": perm,
            "multiple_testing": correction,
            "verdict": "SIGNIFICANT" if perm.get("significant") else "NOT_SIGNIFICANT",
        }
```

**修復記錄**：第 2 輪 `full_report` 改為接收參數。

---

## 9.4 `app/memory/trade_memory.py`

**職責**：Agent 交易記憶層，五層記憶系統。

```python
import hashlib
import json
from datetime import datetime
from pathlib import Path

import duckdb


class TradeMemoryLayer:
    def __init__(self, db_path: str = "./data_lake/memory.duckdb"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    def _conn(self):
        return duckdb.connect(self.db_path)

    def _ensure_tables(self):
        with self._conn() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS episodic_memory (
                    trade_id VARCHAR, symbol VARCHAR, market VARCHAR, side VARCHAR,
                    entry_price DOUBLE, exit_price DOUBLE, qty INTEGER, pnl DOUBLE,
                    entry_reason TEXT, market_regime VARCHAR, confidence DOUBLE,
                    agent_signals TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            con.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_episodic_trade_id
                ON episodic_memory (trade_id);
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS procedural_memory (
                    metric_name VARCHAR, metric_value DOUBLE, sample_size INTEGER,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            con.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_procedural_metric
                ON procedural_memory (metric_name);
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS affective_memory (
                    date DATE, avg_confidence DOUBLE,
                    win_streak INTEGER, lose_streak INTEGER,
                    max_drawdown_today DOUBLE, discipline_drift_score DOUBLE
                );
            """)
            con.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_affective_date
                ON affective_memory (date);
            """)

    def record_trade(self, symbol, market, side, entry_price, exit_price,
                     qty, entry_reason, market_regime="unknown",
                     confidence=0.5, agent_signals=None) -> dict:
        pnl = ((exit_price - entry_price) * qty if side == "BUY"
               else (entry_price - exit_price) * qty)
        trade_id = hashlib.sha256(
            f"{symbol}_{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:16]

        with self._conn() as con:
            con.execute("""
                INSERT INTO episodic_memory
                (trade_id, symbol, market, side, entry_price, exit_price,
                 qty, pnl, entry_reason, market_regime, confidence, agent_signals)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [trade_id, symbol, market, side, entry_price, exit_price,
                  qty, pnl, entry_reason, market_regime, confidence,
                  json.dumps(agent_signals or {})])

        self._reflect(trade_id)
        return {"trade_id": trade_id, "pnl": pnl}

    def _reflect(self, trade_id):
        with self._conn() as con:
            trade = con.execute(
                "SELECT * FROM episodic_memory WHERE trade_id = ?", [trade_id]
            ).fetchone()
        if trade:
            self._update_procedural(trade)
            self._update_affective(trade)

    def _update_procedural(self, trade):
        symbol = trade[1]
        with self._conn() as con:
            row = con.execute(
                "SELECT metric_value, sample_size FROM procedural_memory WHERE metric_name = ?",
                [f"trade_count_{symbol}"],
            ).fetchone()

            if row:
                new_val = (row[0] * row[1] + 1.0) / (row[1] + 1)
                con.execute("""
                    UPDATE procedural_memory
                    SET metric_value = ?, sample_size = ?, last_updated = CURRENT_TIMESTAMP
                    WHERE metric_name = ?
                """, [new_val, row[1] + 1, f"trade_count_{symbol}"])
            else:
                con.execute("""
                    INSERT INTO procedural_memory (metric_name, metric_value, sample_size)
                    VALUES (?, ?, ?)
                """, [f"trade_count_{symbol}", 1.0, 1])

    def _update_affective(self, trade):
        pnl = trade[7]
        today = datetime.utcnow().date()
        with self._conn() as con:
            existing = con.execute(
                "SELECT * FROM affective_memory WHERE date = ?", [today]
            ).fetchone()

            if existing:
                new_win = existing[2] + 1 if pnl > 0 else 0
                new_lose = existing[3] + 1 if pnl < 0 else 0
                con.execute("""
                    UPDATE affective_memory
                    SET win_streak = ?, lose_streak = ?,
                        avg_confidence = (avg_confidence + ?) / 2
                    WHERE date = ?
                """, [new_win, new_lose, trade[10], today])
            else:
                con.execute("""
                    INSERT INTO affective_memory
                    (date, avg_confidence, win_streak, lose_streak)
                    VALUES (?, ?, ?, ?)
                """, [today, trade[10], 1 if pnl > 0 else 0, 1 if pnl < 0 else 0])

    def recall_similar_trades(self, symbol=None, market_regime=None, limit=10) -> list[dict]:
        sql = "SELECT *, ABS(pnl) AS outcome_weight FROM episodic_memory WHERE 1=1"
        params = []
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol)
        if market_regime:
            sql += " AND market_regime = ?"
            params.append(market_regime)
        sql += " ORDER BY outcome_weight DESC LIMIT ?"
        params.append(limit)

        with self._conn() as con:
            df = con.execute(sql, params).df()
        return df.to_dict("records")

    def get_discipline_drift(self, lookback_days: int = 30) -> dict:
        with self._conn() as con:
            recent = con.execute("""
                SELECT AVG(confidence) as avg_conf, COUNT(*) as n
                FROM episodic_memory
                WHERE created_at > CURRENT_TIMESTAMP - INTERVAL ? DAY
            """, [lookback_days]).fetchone()

            historical = con.execute("""
                SELECT AVG(confidence) as avg_conf
                FROM episodic_memory
                WHERE created_at <= CURRENT_TIMESTAMP - INTERVAL ? DAY
            """, [lookback_days]).fetchone()

        if not recent or not historical or historical[0] is None:
            return {"drift_score": 0, "status": "insufficient_data"}

        drift = abs(recent[0] - historical[0]) if recent[0] else 0
        return {
            "recent_avg_confidence": round(recent[0], 4) if recent[0] else None,
            "historical_avg_confidence": round(historical[0], 4),
            "drift_score": round(drift, 4),
            "status": "warning" if drift > 0.2 else "normal",
        }
```

**修復記錄**：第 2 輪 DuckDB UPSERT 語法修正。

---

# Part 10：API 層

## 10.1 `app/api/main.py`

**職責**：FastAPI 入口，雙市場風控。

```python
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.agents.orchestrator import InvestmentOrchestrator
from app.agents.nl_trader import NLTrader
from app.backtest.engine import BacktestEngine
from app.backtest.signal_dsl import SignalDSL
from app.data.composite import CompositeProvider
from app.domain.models import Market, Side
from app.markets.registry import get_rules
from app.risk.guard import build_tw_guard, build_us_guard

app = FastAPI(title="TW/US Invest OS")

orchestrator = InvestmentOrchestrator()
data_provider = CompositeProvider()
_nl_trader = NLTrader()
_risk_tw = build_tw_guard()
_risk_us = build_us_guard()


class AnalyzeReq(BaseModel):
    symbol: str
    market: Market
    start: str = "2024-01-01"
    end: str = "2025-01-01"


class BacktestReq(BaseModel):
    symbol: str
    market: Market
    start: str
    end: str
    expr: str = "ema(close, 10) / ema(close, 30) - 1"
    upper: float = 0.02
    lower: float = -0.02


@app.get("/health")
def health():
    return {"ok": True, "app": "TW/US Invest OS"}


@app.get("/rules/{market}")
def rules(market: Market):
    r = get_rules(market)
    return {"market": market.value, "settlement_days": r.settlement_days,
            "price_limit_pct": r.price_limit_pct, "lot_size": r.lot_size}


@app.post("/analyze")
async def analyze(req: AnalyzeReq):
    return await orchestrator.analyze(req.symbol, req.market, req.start, req.end)


@app.post("/backtest")
async def backtest(req: BacktestReq):
    bars = await data_provider.get_bars(req.symbol, req.market, req.start, req.end)
    if bars is None or bars.empty:
        raise HTTPException(status_code=404, detail="no data")

    dsl = SignalDSL(bars)
    score = dsl.evaluate(req.expr)
    signals = dsl.discretize(score, req.upper, req.lower)

    engine = BacktestEngine(market=req.market)
    result = engine.run(bars, signals)

    eq = pd.DataFrame(result["equity_curve"])
    if not eq.empty:
        eq["return"] = eq["equity"].pct_change()
        sharpe = (eq["return"].mean() / (eq["return"].std() + 1e-9)) * (252 ** 0.5)
        total_return = eq["equity"].iloc[-1] / eq["equity"].iloc[0] - 1
        max_dd = ((eq["equity"] / eq["equity"].cummax()) - 1).min()
    else:
        sharpe = total_return = max_dd = 0

    result["metrics"] = {
        "sharpe": round(float(sharpe), 4),
        "total_return": round(float(total_return), 4),
        "max_drawdown": round(float(max_dd), 4),
        "num_trades": len(result["trades"]),
    }
    return result


@app.post("/trade/order-protected")
async def place_order_protected(
    symbol: str, market: Market, side: Side,
    price: float, qty: int, portfolio_value: float,
    current_position_value: float = 0.0,
    current_equity: float = 1_000_000.0,
    dry_run: bool = True,
):
    guard = _risk_tw if market == Market.TW else _risk_us
    check = guard.check_order(symbol, side.value, qty, price,
                              portfolio_value, current_position_value, current_equity)

    if not check["approved"]:
        return {"blocked": True, "reason": check["reason"]}

    adjusted_qty = check.get("adjusted_qty", qty)

    if dry_run:
        return {"dry_run": True, "symbol": symbol, "side": side.value,
                "original_qty": qty, "adjusted_qty": adjusted_qty,
                "reason": check["reason"]}

    return {"dry_run": False, "message": "broker integration not enabled",
            "adjusted_qty": adjusted_qty}


@app.post("/trade/natural")
async def natural_language_trade(
    text: str, portfolio_value: float = 1_000_000, dry_run: bool = True,
):
    intent = await _nl_trader.parse_intent(text, {"portfolio_value": portfolio_value})
    from app.broker.shioaji_bridge import ShioajiBridge
    from app.broker.ibkr_bridge import IBKRBridge
    result = await _nl_trader.execute(
        intent, _risk_tw, ShioajiBridge(simulation=True),
        IBKRBridge(port=4002, paper=True), dry_run,
    )
    return {"input": text, "parsed_intent": intent, "execution": result}


@app.get("/trade/audit-log")
async def get_audit_log(limit: int = 100):
    return _nl_trader.get_audit_log(limit)
```

**修復記錄**：第 1 輪雙市場風控配置。

---

# Part 11：歸檔的概念代碼

以下模組是**概念性代碼**，依賴外部集群、特定硬件或未穩定的第三方包，建議放在 `app/_archive/`，不參與主流程。

| 模組 | 歸檔理由 |
|------|----------|
| `app/gpu/factor_gpu.py` | 依賴虛構的 `QuantGplearn.gpu_transformer` |
| `app/quantum/quantum_portfolio.py` | 依賴假設的 `double_quant` 導入路徑；需要 Qiskit |
| `app/streaming/flink_jobs.py` | Flink SQL 語法需真實集群驗證 |
| `app/orchestration/daily_flow.py` | Prefect 3.x API 需驗證 |
| `app/portfolio/production_optimizer.py` | `optimalportfolios` API 名稱假設 |
| `app/factors/factor_moe.py` | 需 PyTorch + 訓練邏輯 |
| `app/agents/rl_decision.py` | 需 PyTorch + 大量訓練數據 |
| `app/evolution/causal_replay.py` | 需 6 個月實盤記錄 |
| `app/serving/online_manager.py` | `_infer` 是佔位實現 |
| `app/factors/factorminer_bridge.py` | 依賴外部 FactorMiner 專案 |
| `app/factors/experience_memory.py` | 需真實數據壓力測試 |
| `app/factors/causal_factor.py` | 需 100+ 因子才值得跑 |
| `app/execution/conformal_execution.py` | 需真實 tick 數據 |
| `app/data/lake_pipeline.py` | 需外部 crypto-lake |
| `app/data/realtime.py` | WebSocket 需實時環境 |

在 `app/_archive/__init__.py` 中寫：

```python
"""歸檔的概念代碼。

這些模組不是不能跑，而是：
1. 需要大量訓練數據
2. 需要外部集群（Kafka/Flink/K8s）
3. 需要特定硬件（GPU/量子模擬器）
4. 依賴尚不穩定的第三方包
5. 需要真實實盤數據累積

保留作為未來參考，不參與主流程。
"""
```

---

# 本批次完成

**已交付 20 個模組**：
- Part 6 Agent 層：8 個
- Part 7 組合層：1 個
- Part 8 執行層：3 個
- Part 9 審計監控層：4 個
- Part 10 API 層：1 個
- Part 11 歸檔：3 個（清單 + 說明）

**下一批次（批次 4）**：RUNBOOK.md + CHANGELOG.md。
