"""
Fase 4 — paper trading prospectivo.

Copia (so registro, sem dinheiro real) as compras das wallets-alvo e:
  1. fecha a posicao se a propria wallet vender o token (wallet_sell), ou
  2. fecha sozinho se o preco cair STOP_LOSS_PCT% abaixo da entrada (stop_loss)

Limitacoes assumidas (ok para v1):
  - 1 posicao por evento de buy (sem netting entre compras parciais do mesmo mint)
  - stop-loss checado a cada POLL_INTERVAL segundos, nao tick-a-tick:
    pode vender um pouco pior que -STOP_LOSS_PCT exato
  - preco atual via DexScreener priceNative (assume par cotado em SOL,
    valido para pump.fun/pumpswap)
  - sem slippage/fee modelado alem do que ja esta embutido no sol_amount real

Uso:
    python paper_trader.py
"""
from __future__ import annotations

import os
import time

import requests
from dotenv import load_dotenv

import db
from collector import fetch_transactions, parse_swap

load_dotenv()

WALLETS = [w.strip() for w in os.environ.get("TARGET_WALLETS", "").split(",") if w.strip()]
POLL = int(os.environ.get("POLL_INTERVAL_SECONDS", "15"))
STOP_LOSS_PCT = float(os.environ.get("STOP_LOSS_PCT", "15"))

DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/{mint}"


def fetch_current_price_sol(mint: str) -> float | None:
    try:
        resp = requests.get(DEXSCREENER_URL.format(mint=mint), timeout=15)
        resp.raise_for_status()
        pairs = resp.json().get("pairs") or []
    except requests.RequestException:
        return None

    if not pairs:
        return None
    best = max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd", 0) or 0)
    price = best.get("priceNative")
    return float(price) if price else None


def process_new_trades():
    for wallet in WALLETS:
        try:
            txs = fetch_transactions(wallet, limit=100)
        except requests.RequestException as e:
            print(f"[warn] falha ao buscar {wallet[:8]}…: {e}")
            continue

        for tx in reversed(txs):  # processa do mais antigo pro mais novo
            sig = tx["signature"]
            if db.is_paper_processed(sig):
                continue

            trade = parse_swap(tx, wallet)
            db.mark_paper_processed(sig)
            if not trade:
                continue

            if trade["action"] == "buy":
                db.open_paper_position(
                    wallet, trade["token_mint"], trade["sol_amount"],
                    trade["token_amount"] or 0, trade["timestamp"],
                )
                print(f"[PAPER BUY ] {wallet[:6]}… {trade['sol_amount']:.3f} SOL  mint={trade['token_mint'][:10]}…")

            elif trade["action"] == "sell":
                pos = db.get_open_position(wallet, trade["token_mint"])
                if not pos:
                    continue
                exit_price = trade["sol_amount"] / pos["entry_tokens"] if pos["entry_tokens"] else 0
                db.close_paper_position(
                    pos["id"], "wallet_sell", exit_price, trade["timestamp"],
                    pos["entry_sol"], pos["entry_tokens"],
                )
                pnl = trade["sol_amount"] - pos["entry_sol"]
                print(f"[PAPER SELL] {wallet[:6]}… wallet vendeu  pnl={pnl:+.3f} SOL  mint={trade['token_mint'][:10]}…")


def check_stop_losses():
    for pos in db.get_all_open_positions():
        price = fetch_current_price_sol(pos["mint"])
        if price is None or pos["entry_price_sol"] == 0:
            continue
        pnl_pct = (price - pos["entry_price_sol"]) / pos["entry_price_sol"] * 100
        if pnl_pct <= -STOP_LOSS_PCT:
            db.close_paper_position(
                pos["id"], "stop_loss", price, int(time.time()),
                pos["entry_sol"], pos["entry_tokens"],
            )
            exit_sol = price * pos["entry_tokens"]
            pnl = exit_sol - pos["entry_sol"]
            print(f"[STOP LOSS ] {pos['wallet'][:6]}… cortado em {pnl_pct:.1f}%  pnl={pnl:+.3f} SOL  mint={pos['mint'][:10]}…")


def main():
    db.init_db()
    db.init_paper_tables()
    db.bootstrap_paper_processed()
    print(f"Paper trading: {len(WALLETS)} wallet(s), stop-loss -{STOP_LOSS_PCT}%, poll {POLL}s. Ctrl+C pra parar.")
    while True:
        process_new_trades()
        check_stop_losses()
        time.sleep(POLL)


if __name__ == "__main__":
    main()
