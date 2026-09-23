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
