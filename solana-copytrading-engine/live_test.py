"""
Round-trip de execucao REAL via PumpPortal (modo local — chave nunca sai da maquina).

Funciona para tokens pump.fun ainda no bonding curve OU ja migrados para PumpSwap.
Nao funciona para tokens que migraram para Raydium (Jupiter bloqueado pela rede).

USO:
    1. Crie uma wallet dedicada nova no Phantom, deposite 0.1 SOL.
    2. Adicione no .env:
           LIVE_SEED_PHRASE=palavra1 palavra2 ... palavra12
           LIVE_RPC=https://mainnet.helius-rpc.com/?api-key=272fc3b1-05b5-4940-a67a-7e75ad2c8a1e
    3. Execute:
           python live_test.py [MINT_DO_TOKEN]
       Se nao passar o mint, o script busca o ultimo token comprado pelas wallets monitoradas.

IMPORTANTE: teste com no maximo 0.01 SOL na primeira vez.
"""
from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod
import json
import os
import struct
import sys
import time

import requests
from dotenv import load_dotenv
from solders.keypair import Keypair  # type: ignore
from solders.transaction import VersionedTransaction  # type: ignore
from solana.rpc.api import Client  # type: ignore
from solana.rpc.types import TxOpts  # type: ignore

load_dotenv()

SEED_PHRASE     = os.environ.get("LIVE_SEED_PHRASE", "").strip()
PRIVATE_KEY_JSON = os.environ.get("LIVE_PRIVATE_KEY", "")
RPC_URL         = os.environ.get("LIVE_RPC", "")
DERIVATION_INDEX = int(os.environ.get("DERIVATION_INDEX", "0"))

TEST_BUY_SOL    = 0.01          # SOL a gastar (mude se quiser)
SLIPPAGE_PCT    = 10            # 10% de tolerancia (memecoins sao volateis)
PRIORITY_FEE    = 0.0001        # SOL de taxa de prioridade

LAMPORTS        = 1_000_000_000
SOL_MINT        = "So11111111111111111111111111111111111111112"
PUMPPORTAL_URL  = "https://pumpportal.fun/api/trade-local"

# ---- derivacao de keypair ---------------------------------------------------

def _slip10_derive(seed: bytes) -> bytes:
    path = f"m/44'/501'/{DERIVATION_INDEX}'/0'"
    h = hmac_mod.new(b"ed25519 seed", seed, hashlib.sha512).digest()
    key, chain = h[:32], h[32:]
    for c in path.split("/")[1:]:
        hardened = c.endswith("'")
        idx = int(c.rstrip("'")) + (0x80000000 if hardened else 0)
        data = b"\x00" + key + struct.pack(">I", idx)
        h = hmac_mod.new(chain, data, hashlib.sha512).digest()
        key, chain = h[:32], h[32:]
    return key


def load_keypair() -> Keypair:
    if SEED_PHRASE:
        try:
            from mnemonic import Mnemonic
            mnemo = Mnemonic("english")
            if not mnemo.check(SEED_PHRASE):
                sys.exit("[erro] LIVE_SEED_PHRASE invalida.")
            seed = mnemo.to_seed(SEED_PHRASE, passphrase="")
            return Keypair.from_seed(_slip10_derive(seed))
        except SystemExit:
            raise
        except Exception as e:
            sys.exit(f"[erro] falha ao derivar keypair: {e}")

    if PRIVATE_KEY_JSON:
        try:
            return Keypair.from_bytes(bytes(json.loads(PRIVATE_KEY_JSON)))
        except Exception as e:
            sys.exit(f"[erro] LIVE_PRIVATE_KEY invalida: {e}")

    sys.exit(
        "[erro] Defina LIVE_SEED_PHRASE ou LIVE_PRIVATE_KEY no .env.\n"
        "  LIVE_SEED_PHRASE=palavra1 palavra2 ... palavra12\n"
        "  LIVE_RPC=https://mainnet.helius-rpc.com/?api-key=SEU_KEY"
    )

# ---- PumpPortal local -------------------------------------------------------

def pumpportal_trade(action: str, mint: str, amount, pubkey: str,
                     denominated_in_sol: bool = True) -> bytes:
    """
    Pede ao PumpPortal uma transacao nao-assinada.
    action: 'buy' | 'sell'
    amount: SOL (se denominated_in_sol=True) ou quantidade de tokens (False)
    Retorna bytes da transacao para assinar localmente.
    """
    payload = {
        "publicKey": pubkey,
        "action": action,
        "mint": mint,
        "amount": amount,
        "denominatedInSol": "true" if denominated_in_sol else "false",
        "slippage": SLIPPAGE_PCT,
        "priorityFee": PRIORITY_FEE,
        "pool": "auto",   # auto: pump bonding curve OU pumpswap, conforme o estado do token
    }
    resp = requests.post(PUMPPORTAL_URL, json=payload, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(
            f"PumpPortal {action} retornou {resp.status_code}: {resp.text[:200]}"
        )
    return resp.content  # bytes da transacao serializada


def sign_and_send(client: Client, keypair: Keypair, tx_bytes: bytes,
                  label: str) -> str:
    """Assina e envia a transacao. Retorna a signature."""
    tx = VersionedTransaction.from_bytes(tx_bytes)
    signed = VersionedTransaction(tx.message, [keypair])
    opts = TxOpts(skip_preflight=False, preflight_commitment="confirmed")
    resp = client.send_raw_transaction(bytes(signed), opts=opts)
    sig = str(resp.value)
    print(f"  [{label}] tx enviada: {sig[:16]}...")
    print(f"  explorer: https://solscan.io/tx/{sig}")

    from solders.signature import Signature  # type: ignore
    sig_obj = Signature.from_string(sig)
    for _ in range(90):
        time.sleep(1)
        status = client.get_signature_statuses([sig_obj]).value[0]
        if status and status.confirmation_status:
            lvl = str(status.confirmation_status)
            if "confirmed" in lvl.lower() or "finalized" in lvl.lower():
                if status.err:
                    raise RuntimeError(f"tx falhou on-chain: {status.err}")
                print(f"  confirmada ({lvl})")
                return sig
    raise TimeoutError(f"{label}: tx nao confirmou em 90s")


def find_recent_mint() -> str | None:
    """Mint mais recentemente comprado pelas wallets monitoradas (do trades.db)."""
    try:
        import db
        db.init_db()
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT token_mint FROM trades WHERE action='buy' "
                "ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        return row["token_mint"] if row else None
    except Exception:
        return None


def wait_for_token(client: Client, pubkey_str: str, mint: str,
                   tries: int = 8, delay: float = 2.0) -> float:
    """Aguarda o saldo do token aparecer no RPC (apos compra ha atraso de indexacao)."""
    for _ in range(tries):
        for t in list_all_tokens(client, pubkey_str):
            if t["mint"] == mint and t["ui_amount"] > 0:
                return t["ui_amount"]
        time.sleep(delay)
    return 0.0


def list_all_tokens(client: Client, pubkey_str: str) -> list[dict]:
    """
    Lista todos os SPL tokens com saldo > 0 na carteira.
    Retorna [{mint, ui_amount}], cobrindo o programa SPL classico e o Token-2022.
    """
    from solders.pubkey import Pubkey  # type: ignore
    from solana.rpc.types import TokenAccountOpts  # type: ignore

    TOKEN_PROGRAM    = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
    TOKEN_2022       = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")

    owner = Pubkey.from_string(pubkey_str)
    found = []
    for program in (TOKEN_PROGRAM, TOKEN_2022):
        opts = TokenAccountOpts(program_id=program, encoding="jsonParsed")
        resp = client.get_token_accounts_by_owner_json_parsed(owner, opts)
        for acc in resp.value:
            info = acc.account.data.parsed["info"]
            amt = info["tokenAmount"]
            ui = float(amt["uiAmountString"] or 0)
            if ui > 0:
                found.append({"mint": info["mint"], "ui_amount": ui})
    return found

# ---- main -------------------------------------------------------------------

def main():
    if not RPC_URL:
        sys.exit(
            "[erro] LIVE_RPC nao definido no .env\n"
            "  Exemplo: LIVE_RPC=https://mainnet.helius-rpc.com/?api-key=SEU_KEY"
        )

    keypair = load_keypair()
    pubkey  = str(keypair.pubkey())
    client  = Client(RPC_URL)

    print(f"Wallet : {pubkey}")
    sol_before = client.get_balance(keypair.pubkey()).value / LAMPORTS
    print(f"Saldo  : {sol_before:.4f} SOL\n")

    # ---- escolha do token ----------------------------------------------------
    if len(sys.argv) > 1:
        mint = sys.argv[1].strip()
        print(f"Token  : {mint} (argumento)")
    else:
        auto = find_recent_mint()
        if auto:
            print(f"Token sugerido (ultimo comprado pelas wallets): {auto}")
            use = input("  Usar esse? [S/n]: ").strip().lower()
            mint = auto if use != "n" else input("  Cole outro mint: ").strip()
        else:
            mint = input("Cole o mint do token pump.fun: ").strip()

    if not mint:
        sys.exit("Nenhum token informado. Abortado.")

    while True:
        try:
            buy_sol = float(input(f"Quantos SOL comprar de {mint[:12]}...? ").strip())
            if buy_sol > 0:
                break
        except ValueError:
            pass
        print("  Valor invalido.")

    if sol_before < buy_sol + 0.002:
        sys.exit(f"[erro] Saldo insuficiente ({sol_before:.4f} SOL).")

    go = input(f"Confirma round-trip: compra {buy_sol} SOL, espera 10s, vende tudo? [s/N]: ").strip().lower()
    if go != "s":
        sys.exit("Abortado.")

    # ---- COMPRA --------------------------------------------------------------
    print(f"\n--- COMPRA: {buy_sol} SOL -> {mint[:12]}... ---")
    try:
        tx_bytes = pumpportal_trade("buy", mint, buy_sol, pubkey, denominated_in_sol=True)
        buy_sig = sign_and_send(client, keypair, tx_bytes, "COMPRA")
    except (RuntimeError, TimeoutError) as e:
        sys.exit(f"[erro] na compra: {e}")
    print(f"  [OK] https://solscan.io/tx/{buy_sig}")

    # ---- ESPERA 10s ----------------------------------------------------------
    print("\nAguardando 10s antes de vender...")
    for i in range(10, 0, -1):
        print(f"  {i}s...", end="\r", flush=True)
        time.sleep(1)
    print()

    # ---- VENDA ---------------------------------------------------------------
    print("Confirmando saldo do token no RPC...")
    sell_amount = wait_for_token(client, pubkey, mint)
    if sell_amount <= 0:
        print("  [aviso] RPC ainda nao indexou o saldo; vendendo 100% mesmo assim.")
    else:
        print(f"  saldo confirmado: {sell_amount:,.4f}")

    # PumpPortal aceita "100%" -> vende todo o saldo sem depender da leitura exata
    print(f"--- VENDA: 100% de {mint[:12]}... ---")
    try:
        tx_bytes = pumpportal_trade("sell", mint, "100%", pubkey, denominated_in_sol=False)
        sell_sig = sign_and_send(client, keypair, tx_bytes, "VENDA")
    except (RuntimeError, TimeoutError) as e:
        sys.exit(f"[erro] na venda: {e}")
    print(f"  [OK] https://solscan.io/tx/{sell_sig}")

    # ---- resumo --------------------------------------------------------------
    sol_after = client.get_balance(keypair.pubkey()).value / LAMPORTS
    print(f"\n{'='*50}")
    print(f"ROUND-TRIP CONCLUIDO")
    print(f"  SOL antes:  {sol_before:.4f}")
    print(f"  SOL depois: {sol_after:.4f}")
    print(f"  Custo real (slippage + fees): {sol_before - sol_after:+.4f} SOL")
    print(f"  Compra: https://solscan.io/tx/{buy_sig}")
    print(f"  Venda:  https://solscan.io/tx/{sell_sig}")
    print(f"{'='*50}")
    print("\nInfra validada (compra + venda). Pronto para plugar no copy_engine como live_mode.")


if __name__ == "__main__":
    main()
