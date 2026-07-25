"""
Fase 3 (parte 3) — smart-money clustering: quantas OUTRAS wallets-alvo ja
tinham comprado o mesmo mint antes desta wallet comprar.

Hipotese: se varias wallets historicamente lucrativas compram o mesmo token
em sequencia, isso e um sinal social mais forte que qualquer metrica de
mercado isolada (liquidez, idade, etc).

Limitacao: com apenas 5 wallets monitoradas, o "cluster count" maximo
possivel e 4. Sinal fica mais forte conforme adicionamos wallets.

Uso:
    python clustering.py
"""
from __future__ import annotations

import statistics
from collections import defaultdict

import db
from analyze import close_positions, load_trades_by_mint


def load_all_buys_by_mint() -> dict[str, list[tuple[str, int]]]:
    """mint -> lista de (wallet, timestamp) de todas as compras, ordenada por tempo."""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT wallet, token_mint, timestamp FROM trades WHERE action = 'buy' ORDER BY timestamp ASC"
        ).fetchall()

    by_mint = defaultdict(list)
    for r in rows:
        by_mint[r["token_mint"]].append((r["wallet"], r["timestamp"]))
    return by_mint


def cluster_count_before(buys_for_mint: list[tuple[str, int]], wallet: str, buy_ts: int) -> int:
    """Quantas OUTRAS wallets distintas compraram esse mint estritamente antes de buy_ts."""
    others = {w for w, ts in buys_for_mint if w != wallet and ts < buy_ts}
    return len(others)


def main():
    db.init_db()
    buys_by_mint = load_all_buys_by_mint()

    with db.get_conn() as conn:
        wallets = [r["wallet"] for r in conn.execute("SELECT DISTINCT wallet FROM trades")]

    # agrega TODAS as posicoes fechadas (todas as wallets juntas) bucketizadas por cluster_count
    buckets = defaultdict(list)  # cluster_count -> [pnl_pct, ...]

    for wallet in wallets:
        by_mint = load_trades_by_mint(wallet)
        for mint, trades in by_mint.items():
            closed = close_positions(trades)
            buys_for_mint = buys_by_mint.get(mint, [])
            for c in closed:
                cc = cluster_count_before(buys_for_mint, wallet, c["buy_ts"])
                buckets[cc].append(c["pnl_pct"])

    print("cluster_count = quantas OUTRAS wallets-alvo ja tinham comprado esse mint antes\n")
    print(f"{'cluster':>8} | {'n trades':>9} | {'win-rate':>9} | {'pnl_pct mediana':>16} | {'pnl_pct media':>14}")
    print("-" * 70)
    for cc in sorted(buckets):
        pnls = buckets[cc]
        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / len(pnls) * 100
        median_pnl = statistics.median(pnls)
        avg_pnl = sum(pnls) / len(pnls)
        print(f"{cc:>8} | {len(pnls):>9} | {win_rate:>8.1f}% | {median_pnl:>15.1f}% | {avg_pnl:>13.1f}%")


if __name__ == "__main__":
    main()
