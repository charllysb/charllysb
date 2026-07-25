"""
Analise de lucratividade de uma carteira — usado pela GUI antes de adicionar
uma wallet ao copy-trading, e como CLI.

Faz backfill do historico de SWAPs da wallet via Helius, calcula PnL por
posicao fechada (FIFO) e retorna um resumo: hit-rate, PnL total, medias.

Uso (CLI):
    python wallet_analysis.py <WALLET>
"""
from __future__ import annotations

import db
from analyze import close_positions, load_trades_by_mint
from collector import fetch_transactions, parse_swap


def _quiet_backfill(wallet: str, max_pages: int = 20) -> int:
    """Igual ao collector.backfill_wallet, mas sem prints (para a GUI)."""
    total = 0
    before = None
    for _ in range(max_pages):
        txs = fetch_transactions(wallet, limit=100, before=before)
        if not txs:
            break
        for tx in txs:
            if db.trade_exists(tx["signature"]):
                continue
            trade = parse_swap(tx, wallet)
            if trade:
                db.insert_trade(trade)
                total += 1
        if len(txs) < 100:
            break
        before = txs[-1]["signature"]
    return total


def analyze_wallet(wallet: str, backfill: bool = True) -> dict:
    """
    Retorna um resumo da lucratividade da wallet. Em caso de erro de rede,
    retorna {"error": <msg>}.
    """
    db.init_db()
    try:
        if backfill:
            _quiet_backfill(wallet)
    except Exception as e:  # rede/Helius
        return {"wallet": wallet, "error": str(e)}

    by_mint = load_trades_by_mint(wallet)
    all_closed = []
    open_count = 0
    for _mint, trades in by_mint.items():
        closed = close_positions(trades)
        all_closed.extend(closed)
        buys = sum(1 for t in trades if t["action"] == "buy")
        sells = sum(1 for t in trades if t["action"] == "sell")
        open_count += max(0, buys - sells)

    if not all_closed:
        return {
            "wallet": wallet, "error": None, "closed": 0, "open_count": open_count,
            "hit_rate": 0.0, "total_pnl": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "best": None, "worst": None,
        }

    wins = [c for c in all_closed if c["pnl_sol"] > 0]
    losses = [c for c in all_closed if c["pnl_sol"] <= 0]
    return {
        "wallet": wallet,
        "error": None,
        "closed": len(all_closed),
        "open_count": open_count,
        "hit_rate": len(wins) / len(all_closed) * 100,
        "total_pnl": sum(c["pnl_sol"] for c in all_closed),
        "avg_win": (sum(c["pnl_sol"] for c in wins) / len(wins)) if wins else 0.0,
        "avg_loss": (sum(c["pnl_sol"] for c in losses) / len(losses)) if losses else 0.0,
        "best": max(all_closed, key=lambda x: x["pnl_sol"])["pnl_pct"],
        "worst": min(all_closed, key=lambda x: x["pnl_sol"])["pnl_pct"],
    }


def format_summary(r: dict) -> str:
    """Texto amigavel do resultado, para exibir num dialog."""
    if r.get("error"):
        return f"Erro ao analisar a carteira:\n{r['error']}"
    if r["closed"] == 0:
        return ("Nenhuma posicao fechada no historico recente.\n"
                f"(posicoes ainda abertas: {r['open_count']})\n\n"
                "Sem dados suficientes para avaliar lucratividade.")
    veredito = "LUCRATIVA" if r["total_pnl"] > 0 else "NO PREJUIZO"
    return (
        f"Veredito: {veredito}\n\n"
        f"Posicoes fechadas : {r['closed']}\n"
        f"Hit-rate          : {r['hit_rate']:.1f}%\n"
        f"PnL total         : {r['total_pnl']:+.3f} SOL\n"
        f"Media de ganho    : {r['avg_win']:+.3f} SOL\n"
        f"Media de perda    : {r['avg_loss']:+.3f} SOL\n"
        f"Melhor / pior trade: {r['best']:+.0f}% / {r['worst']:+.0f}%\n"
        f"Posicoes abertas   : {r['open_count']}"
    )


def main():
    import sys
    if len(sys.argv) < 2:
        sys.exit("Uso: python wallet_analysis.py <WALLET>")
    r = analyze_wallet(sys.argv[1].strip())
    print(format_summary(r))


if __name__ == "__main__":
    main()
