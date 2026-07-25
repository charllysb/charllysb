"""
Cruza a tracao inicial de cada token (momentum.py) com o resultado real
(ganho/perda) das posicoes fechadas das 5 wallets-alvo.

Uso:
    python momentum_analysis.py
"""
from __future__ import annotations

import statistics
from collections import defaultdict

import db
from analyze import close_positions, load_trades_by_mint


def bucket_by_traders(traders_60s: int) -> str:
    if traders_60s == 0:
        return "0"
    if traders_60s <= 5:
        return "1-5"
    if traders_60s <= 20:
        return "6-20"
    return "21+"


def main():
    db.init_db()
    db.init_momentum_table()

    with db.get_conn() as conn:
        wallets = [r["wallet"] for r in conn.execute("SELECT DISTINCT wallet FROM trades")]

    buckets = defaultdict(list)  # bucket -> [pnl_pct, ...]
    skipped_no_momentum = 0

    for wallet in wallets:
        by_mint = load_trades_by_mint(wallet)
        for mint, trades in by_mint.items():
            closed = close_positions(trades)
            if not closed:
                continue
            mom = db.get_token_momentum(mint)
            if not mom or mom["traders_60s"] is None:
                skipped_no_momentum += len(closed)
                continue
            bucket = bucket_by_traders(mom["traders_60s"])
            for c in closed:
                buckets[bucket].append(c["pnl_pct"])

    print(f"posicoes sem dado de momentum (ignoradas): {skipped_no_momentum}\n")
    print("traders_60s = quantos traders unicos distintos compraram o token nos primeiros 60s\n")
    print(f"{'bucket':>10} | {'n trades':>9} | {'win-rate':>9} | {'pnl_pct mediana':>16}")
    print("-" * 55)

    order = ["0", "1-5", "6-20", "21+"]
    for b in order:
        if b not in buckets:
            continue
        pnls = buckets[b]
        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / len(pnls) * 100
        median_pnl = statistics.median(pnls)
        print(f"{b:>10} | {len(pnls):>9} | {win_rate:>8.1f}% | {median_pnl:>15.1f}%")


if __name__ == "__main__":
    main()
