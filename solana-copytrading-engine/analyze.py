"""
Fase 2 — calcula PnL por trade fechado (buy->sell no mesmo mint, FIFO)
e o hit-rate da wallet.

Uso:
    python analyze.py
"""
from __future__ import annotations

from collections import defaultdict

import db


def load_trades_by_mint(wallet: str) -> dict[str, list[dict]]:
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE wallet = ? ORDER BY timestamp ASC",
            (wallet,),
        ).fetchall()

    by_mint = defaultdict(list)
    for r in rows:
        by_mint[r["token_mint"]].append(dict(r))
    return by_mint


def close_positions(trades: list[dict]) -> list[dict]:
    """
    FIFO simples: empilha buys (sol_amount, token_amount), consome na ordem
    quando aparece um sell. Retorna lista de posicoes fechadas com PnL em SOL.
    """
    buy_queue = []  # [{"sol": x, "tokens": y}]
    closed = []

    for t in trades:
        if t["action"] == "buy":
            buy_queue.append(
                {"sol": t["sol_amount"], "tokens": t["token_amount"] or 0, "ts": t["timestamp"]}
            )
        elif t["action"] == "sell" and buy_queue:
            entry = buy_queue.pop(0)
            pnl = t["sol_amount"] - entry["sol"]
            pct = (pnl / entry["sol"] * 100) if entry["sol"] else 0
            closed.append(
                {
                    "mint": t["token_mint"],
                    "buy_sol": entry["sol"],
                    "sell_sol": t["sol_amount"],
                    "pnl_sol": pnl,
                    "pnl_pct": pct,
                    "buy_ts": entry["ts"],
                    "sell_ts": t["timestamp"],
                }
            )
    return closed


def main():
    db.init_db()
    with db.get_conn() as conn:
        wallets = [r["wallet"] for r in conn.execute("SELECT DISTINCT wallet FROM trades")]

    for wallet in wallets:
        by_mint = load_trades_by_mint(wallet)
        all_closed = []
        for mint, trades in by_mint.items():
            all_closed.extend(close_positions(trades))

        if not all_closed:
            print(f"{wallet}: nenhuma posicao fechada (so buys sem sell correspondente)")
            continue

        wins = [c for c in all_closed if c["pnl_sol"] > 0]
        losses = [c for c in all_closed if c["pnl_sol"] <= 0]
        hit_rate = len(wins) / len(all_closed) * 100
        total_pnl = sum(c["pnl_sol"] for c in all_closed)

        print(f"\n=== {wallet} ===")
        print(f"posicoes fechadas: {len(all_closed)}")
        print(f"hit-rate: {hit_rate:.1f}%  ({len(wins)} ganhos / {len(losses)} perdas)")
        print(f"PnL total: {total_pnl:+.3f} SOL")
        if wins:
            print(f"media ganho: {sum(c['pnl_sol'] for c in wins) / len(wins):+.3f} SOL")
        if losses:
            print(f"media perda: {sum(c['pnl_sol'] for c in losses) / len(losses):+.3f} SOL")

        print("\ntop 5 melhores trades:")
        for c in sorted(all_closed, key=lambda x: -x["pnl_sol"])[:5]:
            print(f"  {c['mint'][:10]}…  {c['pnl_sol']:+.3f} SOL ({c['pnl_pct']:+.0f}%)")

        print("top 5 piores trades:")
        for c in sorted(all_closed, key=lambda x: x["pnl_sol"])[:5]:
            print(f"  {c['mint'][:10]}…  {c['pnl_sol']:+.3f} SOL ({c['pnl_pct']:+.0f}%)")


if __name__ == "__main__":
    main()
