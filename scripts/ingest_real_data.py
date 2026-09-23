#!/usr/bin/env python3
"""一鍵灌入台股 + 美股歷史數據。"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from app.data.composite import CompositeProvider
from app.data.warehouse import MarketWarehouse
from app.domain.models import Market


class IngestStats:
    def __init__(self):
        self.total = 0
        self.success = 0
        self.failed = 0
        self.skipped = 0
        self.total_rows = 0
        self.errors: list[dict] = []

    def add_success(self, symbol, rows, source):
        self.total += 1
        self.success += 1
        self.total_rows += rows

    def add_skip(self, symbol, reason):
        self.total += 1
        self.skipped += 1

    def add_failure(self, symbol, error):
        self.total += 1
        self.failed += 1
        self.errors.append({"symbol": symbol, "error": str(error)})

    def print_summary(self):
        print(f"\n{'=' * 70}")
        print("灌入統計")
        print(f"{'=' * 70}")
        print(f"  總計:     {self.total}")
        print(f"  成功:     {self.success}")
        print(f"  跳過:     {self.skipped}")
        print(f"  失敗:     {self.failed}")
        print(f"  總行數:   {self.total_rows:,}")
        if self.errors:
            print(f"\n失敗明細:")
            for e in self.errors[:10]:
                print(f"  ❌ {e['symbol']}: {e['error'][:100]}")


async def ingest_tw(symbols, start, end, provider, stats, with_chips=False):
    print(f"\n[台股] 準備灌入 {len(symbols)} 檔標的")
    print(f"  時間範圍: {start} → {end}")
    print(f"  籌碼數據: {'開啟' if with_chips else '關閉'}\n")

    for i, sym in enumerate(symbols, 1):
        print(f"  [{i}/{len(symbols)}] {sym} ...", end=" ", flush=True)
        try:
            bars = await provider.get_bars(sym, Market.TW, start, end)
            if bars is None or bars.empty:
                print("無數據")
                stats.add_skip(sym, "no data")
                continue
            print(f"{len(bars):,} 筆 ({bars['timestamp'].iloc[0].date()} → {bars['timestamp'].iloc[-1].date()})")
            stats.add_success(sym, len(bars), "FinMind")

            if with_chips:
                try:
                    from app.factors.tw_chips import TWChipsFactorEngine
                    chip_engine = TWChipsFactorEngine()
                    chips = chip_engine.build_chip_table(sym, start, end)
                    if chips is not None and not chips.empty:
                        print(f"       籌碼 {len(chips):,} 筆")
                except Exception as e:
                    print(f"       籌碼失敗: {e}")
        except Exception as e:
            print(f"失敗: {e}")
            stats.add_failure(sym, e)


async def ingest_us(symbols, start, end, provider, stats):
    print(f"\n[美股] 準備灌入 {len(symbols)} 檔標的")
    print(f"  時間範圍: {start} → {end}\n")

    for i, sym in enumerate(symbols, 1):
        print(f"  [{i}/{len(symbols)}] {sym} ...", end=" ", flush=True)
        try:
            bars = await provider.get_bars(sym, Market.US, start, end)
            if bars is None or bars.empty:
                print("無數據")
                stats.add_skip(sym, "no data")
                continue
            print(f"{len(bars):,} 筆 ({bars['timestamp'].iloc[0].date()} → {bars['timestamp'].iloc[-1].date()})")
            stats.add_success(sym, len(bars), "yfinance")
        except Exception as e:
            print(f"失敗: {e}")
            stats.add_failure(sym, e)


def verify_warehouse(warehouse):
    print(f"\n{'=' * 70}")
    print("數據倉庫驗證")
    print(f"{'=' * 70}")
    try:
        with warehouse._conn() as con:
            bars_stats = con.execute("""
                SELECT market, COUNT(DISTINCT symbol) AS symbols, COUNT(*) AS rows,
                       MIN(timestamp) AS min_date, MAX(timestamp) AS max_date
                FROM bars GROUP BY market ORDER BY market
            """).df()
            if not bars_stats.empty:
                print("\nbars 表:")
                print(bars_stats.to_string(index=False))
    except Exception as e:
        print(f"驗證失敗: {e}")


def parse_args():
    parser = argparse.ArgumentParser(description="一鍵灌入歷史數據")
    parser.add_argument("--market", type=str, default="TW", choices=["TW", "US", "BOTH"])
    parser.add_argument("--symbols", type=str, default=None)
    parser.add_argument("--tw-symbols", type=str, default=None)
    parser.add_argument("--us-symbols", type=str, default=None)
    parser.add_argument("--start", type=str, default="2020-01-01")
    parser.add_argument("--end", type=str, default=None)
    parser.add_argument("--with-chips", action="store_true")
    return parser.parse_args()


async def main():
    args = parse_args()
    if args.end is None:
        args.end = datetime.now().strftime("%Y-%m-%d")

    if args.market == "BOTH":
        tw_symbols = [s.strip() for s in (args.tw_symbols or "2330").split(",") if s.strip()]
        us_symbols = [s.strip() for s in (args.us_symbols or "AAPL").split(",") if s.strip()]
    else:
        symbols_arg = args.symbols or ("2330" if args.market == "TW" else "AAPL")
        symbols = [s.strip() for s in symbols_arg.split(",") if s.strip()]
        if args.market == "TW":
            tw_symbols, us_symbols = symbols, []
        else:
            tw_symbols, us_symbols = [], symbols

    print(f"\n{'=' * 70}")
    print("數據灌入")
    print(f"{'=' * 70}")
    print(f"  市場: {args.market}")
    print(f"  台股: {len(tw_symbols)} 檔 · 美股: {len(us_symbols)} 檔")
    print(f"  時間: {args.start} → {args.end}")

    provider = CompositeProvider()
    warehouse = MarketWarehouse()
    stats = IngestStats()
    t0 = datetime.now()

    if tw_symbols:
        await ingest_tw(tw_symbols, args.start, args.end, provider, stats, args.with_chips)
    if us_symbols:
        await ingest_us(us_symbols, args.start, args.end, provider, stats)

    elapsed = (datetime.now() - t0).total_seconds()
    stats.print_summary()
    print(f"  耗時: {elapsed:.1f} 秒")
    verify_warehouse(warehouse)

    print(f"\n{'=' * 70}")
    print("✅ 灌入完成" if stats.failed == 0 else f"⚠️  有 {stats.failed} 筆失敗")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    asyncio.run(main())
