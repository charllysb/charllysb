"""
Backtest simples: testa se limitar o tamanho das perdas (stop-loss
hipotetico) teria melhorado o PnL real de cada wallet.

Para cada posicao fechada, se a perda real excede o threshold testado,
recalcula o PnL como se tivesse vendido exatamente no threshold.
Ganhos nunca sao alterados (so testamos disciplina de saida em perda).

Limitacao: retrospectivo - nao sabemos se o preco realmente passou pelo
threshold antes do preco final (podia ter caido mais e voltado, ou o
contrario). E uma estimativa, nao uma simulacao tick-a-tick.

Uso:
    python backtest.py
"""
from __future__ import annotations

import db
from analyze import close_positions, load_trades_by_mint

THRESHOLDS_PCT = [15, 25, 40]  # testa stop-loss em -15%, -25%, -40%


def apply_stop_loss(closed: list[dict], threshold_pct: float) -> float:
    """Retorna PnL total (SOL) se toda perda > threshold tivesse sido cortada no threshold."""
    total = 0.0
    for c in closed:
        if c["pnl_pct"] < -threshold_pct:
            capped_pnl = -threshold_pct / 100 * c["buy_sol"]
            total += capped_pnl
        else:
            total += c["pnl_sol"]
    return total


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
            continue

        real_pnl = sum(c["pnl_sol"] for c in all_closed)
        worst_loss_pct = min(c["pnl_pct"] for c in all_closed)

        print(f"\n=== {wallet} ===")
        print(f"PnL real: {real_pnl:+.3f} SOL  (pior trade: {worst_loss_pct:+.0f}%)")

        for thr in THRESHOLDS_PCT:
            hyp_pnl = apply_stop_loss(all_closed, thr)
            delta = hyp_pnl - real_pnl
            affected = sum(1 for c in all_closed if c["pnl_pct"] < -thr)
            sign = "+" if delta >= 0 else ""
            print(
                f"  stop em -{thr}%: PnL hipotetico {hyp_pnl:+.3f} SOL  "
                f"(diff {sign}{delta:.3f})  [{affected} trades teriam sido cortados]"
            )


if __name__ == "__main__":
    main()
