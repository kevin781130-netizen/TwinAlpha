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
