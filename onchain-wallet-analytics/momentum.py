"""
Fase 3 (parte 3) — mede a "tracao inicial" de cada token: quantos trades e
quantos traders unicos apareceram nos primeiros 60s e 120s apos a criacao
(tx CREATE), via Helius, paginando o historico do mint de tras pra frente
ate cobrir essa janela.

Hipotese: tokens que "pegam" tem multiplos compradores rapido; os que
morrem ficam parados. Esse sinal e do TOKEN, nao da wallet que copiamos.

Uso:
    python momentum.py
"""
from __future__ import annotations

import os
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
PAGE_LIMIT = 100
MAX_PAGES = 30  # cap de seguranca: ate 3000 txs escaneados por mint


def fetch_early_window(mint: str, created_at: int) -> dict | None:
    """
    Pagina pra tras ate cobrir [created_at, created_at+120s], retorna metricas
    da janela. Se nao conseguir voltar longe o suficiente (token com MUITA
    atividade), retorna None em vez de zero falso-negativo - importante pra
    nao confundir "nao alcancamos" com "sem atividade real".
    """
    collected = []
    before = None
    reached = False

    for _ in range(MAX_PAGES):
        params = {"api-key": API_KEY, "type": "SWAP", "limit": PAGE_LIMIT}
        if before:
            params["before"] = before
        resp = requests.get(URL.format(mint=mint), params=params, timeout=20)

        if resp.status_code != 200:
            break  # sem mais historico ou erro - usa o que ja coletou

        txs = resp.json()
        if not txs:
            reached = True  # historico acabou antes da janela - token tem pouquissima atividade
            break

        collected.extend(txs)
        oldest_ts = min(t["timestamp"] for t in txs)
        if oldest_ts <= created_at + 120:
            reached = True
            break
        before = txs[-1]["signature"]

    if not reached:
        return None  # nao conseguimos paginar longe o suficiente - dado incompleto

    in_60s = [t for t in collected if created_at <= t["timestamp"] <= created_at + 60]
    in_120s = [t for t in collected if created_at <= t["timestamp"] <= created_at + 120]

    return {
        "trade_count_60s": len(in_60s),
        "traders_60s": len({t.get("feePayer") for t in in_60s if t.get("feePayer")}),
        "trade_count_120s": len(in_120s),
        "traders_120s": len({t.get("feePayer") for t in in_120s if t.get("feePayer")}),
    }


def main():
    db.init_db()
    db.init_momentum_table()

    with db.get_conn() as conn:
        mints = [
            r["mint"]
            for r in conn.execute(
                "SELECT mint FROM token_meta WHERE created_at_chain IS NOT NULL"
            )
        ]

    print(f"{len(mints)} mints com created_at_chain conhecido", flush=True)
    ok, failed = 0, 0
    for mint in mints:
        if db.get_token_momentum(mint):
            continue
        meta = db.get_token_meta(mint)
        created_at = meta["created_at_chain"]
        try:
            metrics = fetch_early_window(mint, created_at)
        except requests.RequestException as e:
            print(f"[warn] {mint[:10]}…: {e}", flush=True)
            failed += 1
            continue

        if metrics is None:
            failed += 1
            continue

        db.upsert_token_momentum({"mint": mint, "computed_at": int(time.time()), **metrics})
        ok += 1
        print(
            f"[ok] {mint[:10]}…  trades_60s={metrics['trade_count_60s']} "
            f"traders_60s={metrics['traders_60s']}",
            flush=True,
        )
        time.sleep(0.2)

    print(f"\nfeito: {ok} ok, {failed} falharam", flush=True)


if __name__ == "__main__":
    main()
