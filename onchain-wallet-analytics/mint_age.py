"""
Fase 3 (parte 2b) — busca o timestamp REAL de criacao de cada mint via
a transacao CREATE (program pump.fun), substituindo pair_created_at do
DexScreener (que marca migracao p/ AMM, nao o lancamento real).

Uso:
    python mint_age.py
"""
from __future__ import annotations

import os
import re
import time

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
URL = "https://api.helius.xyz/v0/addresses/{mint}/transactions"

BEFORE_SIG_RE = re.compile(r"before-signature.*?set to (\S+)\.")


def get_creation_ts(mint: str, max_pages: int = 3) -> int | None:
    """
    Busca a tx CREATE do mint. limit=100 cobre a maioria; se o token tiver
    historico muito longo, Helius pede pra paginar com before-signature.
    Limitamos paginas/timeout para nao travar em mints sem CREATE (ex: tokens
    nao-pump.fun como USDC/SOL que nao tem essa instrucao).
    """
    before = None
    for _ in range(max_pages):
        params = {"api-key": API_KEY, "type": "CREATE", "limit": 100}
        if before:
            params["before"] = before
        resp = requests.get(URL.format(mint=mint), params=params, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            return data[0]["timestamp"] if data else None

        body = resp.json()
        m = BEFORE_SIG_RE.search(body.get("error", ""))
        if not m:
            return None
        before = m.group(1)

    return None  # nao achou dentro do limite de paginas


def main():
    db.init_db()
    with db.get_conn() as conn:
        mints = [
            r["mint"]
            for r in conn.execute(
                "SELECT mint FROM token_meta WHERE created_at_chain IS NULL"
            )
        ]

    print(f"{len(mints)} mints sem created_at_chain")
    ok, missing = 0, 0
    for mint in mints:
        try:
            ts = get_creation_ts(mint)
        except requests.RequestException as e:
            print(f"[warn] {mint[:10]}…: {e}", flush=True)
            missing += 1
            continue

        if ts is None:
            print(f"[skip] CREATE nao encontrado para {mint[:10]}…", flush=True)
            missing += 1
            continue

        db.set_created_at_chain(mint, ts)
        ok += 1
        print(f"[ok] {mint[:10]}…  created_at={ts}", flush=True)
        time.sleep(0.2)

    print(f"\nfeito: {ok} ok, {missing} sem resultado", flush=True)


if __name__ == "__main__":
    main()
