"""
Fase 3 (parte 1) — enriquece cada mint com metadata do DexScreener.

IMPORTANTE: a API do DexScreener so devolve o estado ATUAL do par
(liquidez/volume/fdv de agora), nao um snapshot do momento da compra.
A unica metrica retroativamente precisa e a IDADE do token na hora da
compra, calculada a partir de pair_created_at (fixo) - timestamp do buy.

Uso:
    python enrich.py
"""
from __future__ import annotations

import time

import requests

import db

DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/{mint}"


def fetch_token_info(mint: str) -> dict | None:
    resp = requests.get(DEXSCREENER_URL.format(mint=mint), timeout=20)
    resp.raise_for_status()
    data = resp.json()
    pairs = data.get("pairs") or []
    if not pairs:
        return None

    # pega o par com maior liquidez (token pode ter varios pares/dex)
    best = max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd", 0) or 0)

    pair_created_ms = best.get("pairCreatedAt")
    return {
        "mint": mint,
        "pair_created_at": int(pair_created_ms / 1000) if pair_created_ms else None,
        "dex_id": best.get("dexId"),
        "liquidity_usd_now": (best.get("liquidity") or {}).get("usd"),
        "volume_h24_now": (best.get("volume") or {}).get("h24"),
        "fdv_now": best.get("fdv"),
        "fetched_at": int(time.time()),
    }


def get_distinct_mints() -> list[str]:
    with db.get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT token_mint FROM trades WHERE token_mint IS NOT NULL")
        return [r["token_mint"] for r in rows]


def main():
    db.init_db()
    mints = get_distinct_mints()
    print(f"{len(mints)} mints distintos para enriquecer")

    ok, skipped, failed = 0, 0, 0
    for mint in mints:
        cached = db.get_token_meta(mint)
        if cached:
            skipped += 1
            continue
        try:
            info = fetch_token_info(mint)
        except requests.RequestException as e:
            print(f"[warn] falha em {mint[:10]}…: {e}")
            failed += 1
            continue

        if info is None:
            print(f"[skip] sem par encontrado para {mint[:10]}…")
            failed += 1
            continue

        db.upsert_token_meta(info)
        ok += 1
        print(f"[ok] {mint[:10]}…  liq=${info['liquidity_usd_now'] or 0:,.0f}  dex={info['dex_id']}")
        time.sleep(0.3)  # respeita rate limit informal do DexScreener

    print(f"\nfeito: {ok} novos, {skipped} ja em cache, {failed} falharam")


if __name__ == "__main__":
    main()
