"""
Fase 3 (parte 2) — cruza posicoes fechadas (analyze.py) com token_meta
(enrich.py) para comparar trades vencedores vs perdedores.

Metrica confiavel retroativamente: idade do token no momento da compra
(pair_created_at e fixo). Liquidez/volume sao snapshot ATUAL, usados so
como proxy aproximado de "porte" do token, nao do estado na hora da compra.

Uso:
    python features.py
"""
from __future__ import annotations

import db
from analyze import close_positions, load_trades_by_mint

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # ruido: nao e memecoin


def enrich_closed(closed: list[dict]) -> list[dict]:
    out = []
    for c in closed:
        if c["mint"] == USDC_MINT:
            continue
        meta = db.get_token_meta(c["mint"])
        age_at_buy = None
        if meta and meta.get("created_at_chain"):
            age_at_buy = c["buy_ts"] - meta["created_at_chain"]
        out.append(
            {
                **c,
                "age_at_buy_sec": age_at_buy,
                "liquidity_usd_now": meta.get("liquidity_usd_now") if meta else None,
                "dex_id": meta.get("dex_id") if meta else None,
            }
        )
    return out


def fmt_age(sec):
    if sec is None:
        return "?"
    if sec < 0:
        return f"{sec}s (compra ANTES do par criado!)"
    if sec < 3600:
        return f"{sec // 60}min"
    if sec < 86400:
        return f"{sec / 3600:.1f}h"
    return f"{sec / 86400:.1f}d"


def main():
    db.init_db()
    with db.get_conn() as conn:
        wallets = [r["wallet"] for r in conn.execute("SELECT DISTINCT wallet FROM trades")]

    for wallet in wallets:
        by_mint = load_trades_by_mint(wallet)
        all_closed = []
        for mint, trades in by_mint.items():
            all_closed.extend(close_positions(trades))
        all_closed = enrich_closed(all_closed)

        if not all_closed:
            continue

        wins = [c for c in all_closed if c["pnl_sol"] > 0]
        losses = [c for c in all_closed if c["pnl_sol"] <= 0]

        win_ages = [c["age_at_buy_sec"] for c in wins if c["age_at_buy_sec"] is not None]
        loss_ages = [c["age_at_buy_sec"] for c in losses if c["age_at_buy_sec"] is not None]

        win_liq = [c["liquidity_usd_now"] for c in wins if c["liquidity_usd_now"]]
        loss_liq = [c["liquidity_usd_now"] for c in losses if c["liquidity_usd_now"]]

        graduated_wins = sum(1 for c in wins if c["dex_id"] == "pumpswap")
        graduated_losses = sum(1 for c in losses if c["dex_id"] == "pumpswap")

        print(f"\n=== {wallet} ===")
        print(f"vencedores: {len(wins)}  |  perdedores: {len(losses)}")

        if win_ages:
            avg = sum(win_ages) / len(win_ages)
            print(f"idade media na compra (VENCEDORES): {fmt_age(int(avg))}")
        if loss_ages:
            avg = sum(loss_ages) / len(loss_ages)
            print(f"idade media na compra (PERDEDORES): {fmt_age(int(avg))}")

        if win_liq:
            print(f"liquidez atual media (VENCEDORES): ${sum(win_liq)/len(win_liq):,.0f}  (n={len(win_liq)})")
        if loss_liq:
            print(f"liquidez atual media (PERDEDORES): ${sum(loss_liq)/len(loss_liq):,.0f}  (n={len(loss_liq)})")

        print(f"% que migrou p/ pumpswap -> VENCEDORES: {graduated_wins}/{len(wins)}  "
              f"PERDEDORES: {graduated_losses}/{len(losses)}")


if __name__ == "__main__":
    main()
