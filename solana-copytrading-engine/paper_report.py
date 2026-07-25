"""
Resumo do desempenho do paper trading (posicoes abertas e fechadas).

Uso:
    python paper_report.py
"""
from __future__ import annotations

import db


def main():
    db.init_db()
    db.init_paper_tables()

    with db.get_conn() as conn:
        closed = [dict(r) for r in conn.execute(
            "SELECT * FROM paper_positions WHERE status = 'closed' ORDER BY exit_ts"
        )]
        open_pos = [dict(r) for r in conn.execute(
            "SELECT * FROM paper_positions WHERE status = 'open'"
        )]

    print(f"posicoes abertas (aguardando stop-loss ou venda real): {len(open_pos)}")
    print(f"posicoes fechadas: {len(closed)}\n")

    if not closed:
        return

    total_pnl = sum(c["pnl_sol"] for c in closed)
    wins = [c for c in closed if c["pnl_sol"] > 0]
    losses = [c for c in closed if c["pnl_sol"] <= 0]
    stop_exits = [c for c in closed if c["exit_reason"] == "stop_loss"]
    wallet_exits = [c for c in closed if c["exit_reason"] == "wallet_sell"]

    print(f"PnL total: {total_pnl:+.3f} SOL")
    print(f"hit-rate: {len(wins)}/{len(closed)} ({len(wins)/len(closed)*100:.1f}%)")
    print(f"saidas por stop-loss: {len(stop_exits)}  |  saidas por venda da wallet: {len(wallet_exits)}")

    if stop_exits:
        print(f"PnL medio (stop-loss): {sum(c['pnl_sol'] for c in stop_exits)/len(stop_exits):+.3f} SOL")
    if wallet_exits:
        print(f"PnL medio (venda wallet): {sum(c['pnl_sol'] for c in wallet_exits)/len(wallet_exits):+.3f} SOL")

    print("\nultimas 10 posicoes fechadas:")
    for c in closed[-10:]:
        print(f"  {c['wallet'][:6]}…  {c['mint'][:10]}…  {c['exit_reason']:11}  {c['pnl_sol']:+.3f} SOL ({c['pnl_pct']:+.0f}%)")


if __name__ == "__main__":
    main()
