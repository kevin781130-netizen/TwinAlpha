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
