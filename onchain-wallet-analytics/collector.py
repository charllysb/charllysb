"""
Coletor Fase 1 — escuta wallets-alvo via Helius Enhanced Transactions API
(polling) e grava cada swap como buy/sell no SQLite.

Uso:
    pip install -r requirements.txt
    cp .env.example .env   # preencha HELIUS_API_KEY e TARGET_WALLETS
    python collector.py
"""
from __future__ import annotations

import os
import threading
import time
import json

import requests
from dotenv import load_dotenv

import db

load_dotenv()

API_KEY = os.environ.get("HELIUS_API_KEY", "")

if not API_KEY:
    raise SystemExit(
        "[config] HELIUS_API_KEY nao definido. "
        "Copie .env.example para .env e preencha a chave "
        "(gratis em https://dev.helius.xyz)"
    )
WALLETS = [w.strip() for w in os.environ.get("TARGET_WALLETS", "").split(",") if w.strip()]
POLL = int(os.environ.get("POLL_INTERVAL_SECONDS", "15"))

SOL_MINT = "So11111111111111111111111111111111111111112"
BASE = "https://api.helius.xyz/v0/addresses/{addr}/transactions"

# --- throttle global de chamadas a Helius (free tier tem limite de req/s) ---
# espacamento minimo entre QUALQUER chamada a fetch_transactions (segundos)
HELIUS_MIN_INTERVAL = float(os.environ.get("HELIUS_MIN_INTERVAL", "0.3"))
_rate_lock = threading.Lock()
_last_call = [0.0]


def _throttle():
    with _rate_lock:
        wait = HELIUS_MIN_INTERVAL - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()


def fetch_transactions(wallet: str, limit: int = 100, before: str | None = None,
                       max_retries: int = 3) -> list[dict]:
    url = BASE.format(addr=wallet)
    params = {"api-key": API_KEY, "limit": limit, "type": "SWAP"}
    if before:
        params["before"] = before

    last_exc = None
    for attempt in range(max_retries):
        _throttle()
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 429:  # rate limit: respeita Retry-After e tenta de novo
            retry_after = resp.headers.get("Retry-After")
            backoff = float(retry_after) if retry_after else (0.5 * (2 ** attempt))
            time.sleep(min(backoff, 5.0))
            last_exc = requests.HTTPError("429 Too Many Requests", response=resp)
            continue
        resp.raise_for_status()
        return resp.json()
    if last_exc:
        raise last_exc
    return []


def backfill_wallet(wallet: str, max_pages: int = 50) -> int:
    """Pagina o historico completo de SWAPs da wallet (limite Helius: 100/pagina)."""
    total = 0
    before = None
    for page in range(max_pages):
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
        print(f"  pagina {page + 1}: {len(txs)} txs lidas, {total} trades gravados ate agora")
        if len(txs) < 100:
            break
        before = txs[-1]["signature"]
    return total


def _wallet_sol_delta(tx: dict, wallet: str) -> float:
    """SOL liquido (com taxas) que entrou/saiu da wallet, via accountData."""
    for acc in tx.get("accountData") or []:
        if acc.get("account") == wallet:
            return acc.get("nativeBalanceChange", 0) / 1e9
    return 0.0


def parse_swap(tx: dict, wallet: str) -> dict | None:
    """
    Extrai trade buy/sell da perspectiva da wallet a partir de tokenTransfers.
    Pump.fun/Raydium nao preenchem events.swap, entao usamos os transfers brutos.
    buy  = wallet RECEBE o token (toUserAccount)
    sell = wallet ENVIA o token  (fromUserAccount)
    """
    leg = None
    action = None
    for t in tx.get("tokenTransfers") or []:
        if t.get("mint") == SOL_MINT:
            continue
        if t.get("toUserAccount") == wallet:
            leg, action = t, "buy"
            break
        if t.get("fromUserAccount") == wallet:
            leg, action = t, "sell"
            break

    if leg is None:
        return None

    return {
        "signature": tx["signature"],
        "wallet": wallet,
        "timestamp": tx.get("timestamp", 0),
        "action": action,
        "token_mint": leg.get("mint"),
        "token_amount": leg.get("tokenAmount"),
        "sol_amount": abs(_wallet_sol_delta(tx, wallet)),
        "source": tx.get("source"),
        "raw": json.dumps({"tokenTransfers": tx.get("tokenTransfers")}),
    }


def poll_once():
    new = 0
    for wallet in WALLETS:
        try:
            txs = fetch_transactions(wallet)
        except requests.RequestException as e:
            print(f"[warn] falha ao buscar {wallet[:8]}…: {e}")
            continue

        for tx in txs:
            if db.trade_exists(tx["signature"]):
                continue
            trade = parse_swap(tx, wallet)
            if trade:
                db.insert_trade(trade)
                new += 1
                print(
                    f"[{trade['action'].upper():4}] {wallet[:6]}… "
                    f"{trade['sol_amount']:.3f} SOL  mint={trade['token_mint']}"
                )
    return new


def main():
    import sys

    db.init_db()

    if "--backfill" in sys.argv:
        for wallet in WALLETS:
            print(f"Backfill {wallet}…")
            total = backfill_wallet(wallet)
            print(f"  -> {total} trades novos gravados (historico completo)")
        return

    print(f"Monitorando {len(WALLETS)} wallet(s), poll a cada {POLL}s. Ctrl+C pra parar.")
    while True:
        added = poll_once()
        if added:
            print(f"  -> {added} novos trades gravados")
        time.sleep(POLL)


if __name__ == "__main__":
    main()
