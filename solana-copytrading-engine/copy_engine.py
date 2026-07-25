"""
Motor de copy-trading SIMULADO (sem dinheiro real).

Modelo de banca/stake (diferente do paper_trader.py, que copiava o valor
exato da wallet): aqui voce define uma banca inicial e cada operacao usa
um percentual (stake) dessa banca. Quando uma wallet-alvo compra, abrimos
uma posicao do tamanho do stake. Fechamos quando:
  - a wallet vende (vendemos junto, ao preco de venda dela), ou
  - o PnL da posicao atinge -stop_loss%.

Roda numa thread propria; a UI le snapshots via get_state() (thread-safe).
"""
from __future__ import annotations

import threading
import time
import itertools

import requests

from collector import fetch_transactions, parse_swap, SOL_MINT  # noqa: F401

DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/{mint}"

# ignora "compras" minusculas da wallet (pernas de taxa/dust que vimos nos dados)
MIN_COPY_BUY_SOL = 0.05


def fetch_current_price_sol(mint: str) -> float | None:
    """Preco atual do token em SOL (priceNative), via DexScreener. None se indisponivel."""
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
    try:
        return float(price) if price else None
    except (TypeError, ValueError):
        return None


# em modo real, reserva pra taxas/rent de ATA antes de calcular a stake
LIVE_FEE_BUFFER_SOL = 0.01

# tempo maximo que um token fica em observacao esperando o gatilho de +X%
MAX_WATCH_SECONDS = 1800  # 30 min


class CopyTradingEngine:
    def __init__(self, wallets, initial_bankroll, max_positions, stop_loss_pct, poll_interval=15,
                 log_callback=None, live_mode=False, entry_trigger_pct=20.0,
                 max_drawdown_pct=40.0):
        self.wallets = list(wallets)
        self.initial_bankroll = float(initial_bankroll)
        self.max_positions = int(max_positions)
        self.stop_loss_pct = float(stop_loss_pct)
        self.poll_interval = int(poll_interval)
        self.log_callback = log_callback or (lambda msg: None)
        self.live_mode = bool(live_mode)
        self.entry_trigger_pct = float(entry_trigger_pct)
        self.max_drawdown_pct = float(max_drawdown_pct)  # disjuntor: % abaixo da banca inicial
        self.halted = False  # vira True quando o disjuntor dispara

        # executor real (so em live); construido aqui pra falhar cedo se faltar .env
        self.executor = None
        if self.live_mode:
            from live_executor import LiveExecutor
            self.executor = LiveExecutor()
            self.initial_bankroll = self.executor.sol_balance()  # banca = saldo da carteira

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._id_counter = itertools.count(1)

        # estado
        self.cash = self.initial_bankroll
        self.pending = []          # tokens em observacao aguardando o gatilho de +X%
        self.open_positions = []   # list[dict]
        self.closed_positions = []  # list[dict]
        self.realized_pnl = 0.0
        self._processed = set()     # signatures ja vistas
        self.last_poll_ts = None    # batimento: timestamp do ultimo ciclo
        self.cycles = 0             # quantos ciclos de varredura ja rodaram

    # ---- ciclo de vida ----------------------------------------------------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    # ---- loop principal ---------------------------------------------------

    def _run(self):
        modo = "REAL (live)" if self.live_mode else "simulado"
        self.log_callback(f"Bot iniciado [{modo}]. Banca {self.initial_bankroll:.3f} SOL, "
                          f"max {self.max_positions} posicoes, gatilho +{self.entry_trigger_pct:.0f}%, "
                          f"stop-loss -{self.stop_loss_pct:.1f}%, disjuntor -{self.max_drawdown_pct:.0f}%.")
        if self.live_mode:
            self.log_callback(f"Carteira de execucao: {self.executor.pubkey}")
        self._bootstrap_processed()
        self.log_callback(f"Pronto. Monitorando {len(self.wallets)} wallet(s) — "
                          f"so copio trades a partir de agora.")
        while not self._stop.is_set():
            try:
                self._refresh_cash()
                self._process_new_trades()
                self._check_pending()
                self._check_stop_losses()
                self._check_circuit_breaker()
            except Exception as e:  # nunca deixar a thread morrer silenciosamente
                self.log_callback(f"[erro] {e}")
            with self._lock:
                self.last_poll_ts = time.time()
                self.cycles += 1
            self._stop.wait(self.poll_interval)
        self.log_callback("Bot parado.")

    def _refresh_cash(self):
        """Em modo real, sincroniza o caixa com o saldo real da carteira."""
        if not self.live_mode:
            return
        try:
            bal = self.executor.sol_balance()
        except Exception:
            return
        with self._lock:
            self.cash = bal

    def _bootstrap_processed(self):
        """Marca tudo que ja aconteceu como visto, pra so copiar trades novos."""
        for wallet in self.wallets:
            try:
                txs = fetch_transactions(wallet, limit=100)
            except requests.RequestException:
                continue
            for tx in txs:
                self._processed.add(tx["signature"])

    def _process_new_trades(self):
        for wallet in self.wallets:
            try:
                txs = fetch_transactions(wallet, limit=25)  # so recentes; _processed deduplica
            except requests.RequestException as e:
                self.log_callback(f"[warn] falha ao buscar {wallet[:6]}…: {e}")
                continue

            for tx in reversed(txs):  # mais antigo -> mais novo
                sig = tx["signature"]
                if sig in self._processed:
                    continue
                self._processed.add(sig)

                trade = parse_swap(tx, wallet)
                if not trade:
                    continue

                if trade["action"] == "buy":
                    self._register_pending(trade)
                elif trade["action"] == "sell":
                    self._drop_pending(trade["wallet"], trade["token_mint"])
                    self._close_on_wallet_sell(trade)

    # ---- observacao (gatilho de momentum) --------------------------------

    def _register_pending(self, trade):
        """Carteira comprou: poe o token em observacao com o preco de entrada dela
        como referencia. So vamos comprar quando subir entry_trigger_pct%."""
        if trade["sol_amount"] < MIN_COPY_BUY_SOL:
            return  # ignora dust/taxa
        tokens_wallet = trade["token_amount"] or 0
        if tokens_wallet <= 0:
            return
        ref_price = trade["sol_amount"] / tokens_wallet
        trigger_price = ref_price * (1 + self.entry_trigger_pct / 100)
        mint = trade["token_mint"]
        with self._lock:
            # evita duplicar observacao do mesmo par wallet+mint
            if any(p["wallet"] == trade["wallet"] and p["mint"] == mint for p in self.pending):
                return
            self.pending.append({
                "id": next(self._id_counter),
                "wallet": trade["wallet"],
                "mint": mint,
                "entry_ts": trade["timestamp"],
                "ref_price": ref_price,
                "trigger_price": trigger_price,
                "current_price": ref_price,
                "watch_since": time.time(),
            })
        self.log_callback(f"[OBSERVA] {trade['wallet'][:6]}… {mint[:8]}… "
                          f"alvo +{self.entry_trigger_pct:.0f}% (ref {ref_price:.2e})")

    def _drop_pending(self, wallet, mint):
        with self._lock:
            self.pending = [p for p in self.pending
                            if not (p["wallet"] == wallet and p["mint"] == mint)]

    def _check_pending(self):
        """A cada ciclo: busca preco dos tokens em observacao; dispara a compra
        nos que ja subiram o gatilho e descarta os que expiraram."""
        with self._lock:
            snapshot = [(p["id"], p["mint"]) for p in self.pending]
        if not snapshot:
            return

        prices = {}
        for _id, mint in snapshot:
            if mint not in prices:
                prices[mint] = fetch_current_price_sol(mint)

        now = time.time()
        to_enter = []   # (wallet, mint, entry_ts, price)
        with self._lock:
            keep = []
            for p in self.pending:
                price = prices.get(p["mint"])
                if price is not None:
                    p["current_price"] = price
                    if price >= p["trigger_price"]:
                        to_enter.append((p["wallet"], p["mint"], p["entry_ts"], price))
                        continue  # sai da observacao
                if now - p["watch_since"] > MAX_WATCH_SECONDS:
                    self.log_callback(f"[OBSERVA expirou] {p['mint'][:8]}… nao subiu "
                                      f"+{self.entry_trigger_pct:.0f}% em "
                                      f"{MAX_WATCH_SECONDS // 60}min")
                    continue  # descarta
                keep.append(p)
            self.pending = keep

        for wallet, mint, entry_ts, price in to_enter:  # executa fora do lock
            self.log_callback(f"[GATILHO] {mint[:8]}… subiu +{self.entry_trigger_pct:.0f}% — entrando")
            self._open_position(wallet, mint, entry_ts, price)

    # ---- abertura / fechamento -------------------------------------------

    def _open_position(self, wallet, mint, entry_ts, sim_entry_price):
        # calcula a stake sob lock (1/N, depois 1/(N-1), ...)
        with self._lock:
            slots_livres = self.max_positions - len(self.open_positions)
            if slots_livres <= 0:
                self.log_callback(f"[skip] limite de {self.max_positions} posicoes atingido — "
                                  f"ignorando {mint[:8]}…")
                return
            usable = self.cash - (LIVE_FEE_BUFFER_SOL if self.live_mode else 0)
            stake = usable / slots_livres
            if stake > self.cash:
                stake = self.cash
            if stake < 0.001:
                self.log_callback(f"[skip] sem caixa pra copiar {mint[:8]}…")
                return

        if self.live_mode:
            # ---- execucao REAL (fora do lock; so a thread do loop abre posicoes) ----
            self.log_callback(f"[COMPRA real] {wallet[:6]}… {stake:.4f} SOL "
                              f"mint={mint[:8]}… (enviando…)")
            try:
                res = self.executor.buy(mint, stake)
            except Exception as e:
                self.log_callback(f"[COMPRA falhou] {mint[:8]}…: {e}")
                return
            tokens = res["tokens"]
            spent = res["spent_sol"] or stake
            if tokens <= 0:
                self.log_callback(f"[COMPRA] confirmou mas sem tokens recebidos ({mint[:8]}…)")
                return
            entry_price = spent / tokens
            stake_real = spent
            sig = res["sig"]
        else:
            entry_price = sim_entry_price  # entramos no preco atual (apos o gatilho)
            tokens = stake / entry_price if entry_price else 0
            stake_real = stake
            sig = None

        with self._lock:
            if not self.live_mode:
                self.cash -= stake_real
            pos = {
                "id": next(self._id_counter),
                "wallet": wallet,
                "mint": mint,
                "entry_ts": entry_ts,
                "entry_price": entry_price,
                "stake_sol": stake_real,
                "tokens": tokens,
                "current_price": entry_price,
                "buy_sig": sig,
            }
            self.open_positions.append(pos)
        extra = f" sig={sig[:12]}…" if sig else ""
        self.log_callback(f"[COMPRA] {wallet[:6]}… stake {stake_real:.4f} SOL "
                          f"mint={mint[:8]}…{extra}")

    def _close_on_wallet_sell(self, trade):
        tokens_wallet = trade["token_amount"] or 0
        sell_price = (trade["sol_amount"] / tokens_wallet) if tokens_wallet else None
        with self._lock:
            pos = self._oldest_open(trade["wallet"], trade["token_mint"])
            if not pos:
                return
            pid = pos["id"]
            price = sell_price if sell_price else pos["current_price"]
        self._exit_position(pid, "venda_wallet", price)

    def _check_stop_losses(self):
        # coleta mints abertos sob lock, busca precos fora do lock, decide sob lock
        with self._lock:
            snapshot = [(p["id"], p["mint"]) for p in self.open_positions]

        prices = {}
        for _id, mint in snapshot:
            if mint not in prices:
                prices[mint] = fetch_current_price_sol(mint)

        to_sell = []
        with self._lock:
            for pos in self.open_positions:
                price = prices.get(pos["mint"])
                if price is None:
                    continue
                pos["current_price"] = price
                pnl_pct = (price - pos["entry_price"]) / pos["entry_price"] * 100
                if pnl_pct <= -self.stop_loss_pct:
                    to_sell.append((pos["id"], price))

        for pid, price in to_sell:  # executa fora do lock
            self._exit_position(pid, "stop_loss", price)

    def _check_circuit_breaker(self):
        """Disjuntor: se a equity cair abaixo de (banca - max_drawdown%), fecha
        tudo e para o bot. Protege contra sangria descontrolada."""
        with self._lock:
            open_value = sum(p["tokens"] * p["current_price"] for p in self.open_positions)
            equity = self.cash + open_value
            floor = self.initial_bankroll * (1 - self.max_drawdown_pct / 100)
            ids = [p["id"] for p in self.open_positions]
        if equity > floor:
            return

        self.halted = True
        self.log_callback(f"[DISJUNTOR] equity {equity:.3f} SOL <= limite {floor:.3f} "
                          f"(-{self.max_drawdown_pct:.0f}% da banca). Fechando tudo e parando o bot.")
        for pid in ids:
            self.manual_sell(pid)  # fecha cada posicao ao preco atual
        # tambem descarta o que estava so em observacao
        with self._lock:
            self.pending = []
        self._stop.set()
        self.log_callback("[DISJUNTOR] bot parado. Revise antes de reiniciar.")

    def manual_sell(self, position_id):
        """Fecha manualmente a posicao pelo id, ao preco atual. Retorna (ok, msg)."""
        with self._lock:
            pos = next((p for p in self.open_positions if p["id"] == position_id), None)
            if not pos:
                return False, "posicao nao encontrada"
            mint = pos["mint"]
            fallback = pos["current_price"]

        price = fetch_current_price_sol(mint) or fallback  # busca fora do lock
        ok = self._exit_position(position_id, "manual", price)
        return (ok, "vendida" if ok else "falha na venda")

    def close_positions_for_wallet(self, wallet):
        """Fecha todas as posicoes abertas de uma carteira, ao preco atual. Retorna qtd fechada."""
        with self._lock:
            ids = [p["id"] for p in self.open_positions if p["wallet"] == wallet]
        closed = 0
        for pid in ids:
            ok, _ = self.manual_sell(pid)
            if ok:
                closed += 1
        return closed

    def _oldest_open(self, wallet, mint):
        for pos in self.open_positions:
            if pos["wallet"] == wallet and pos["mint"] == mint:
                return pos
        return None

    def _exit_position(self, pos_id, reason, sim_exit_price):
        """
        Fecha a posicao. Em modo real, executa a venda FORA do lock (chamada de
        rede longa). Se a venda falhar, devolve a posicao para retentativa.
        Retorna True se fechou.
        """
        # 1) "reivindica" a posicao removendo-a da lista de abertas
        with self._lock:
            pos = next((p for p in self.open_positions if p["id"] == pos_id), None)
            if not pos:
                return False
            self.open_positions.remove(pos)

        # 2) calcula proventos (rede, sem lock)
        if self.live_mode:
            try:
                res = self.executor.sell(pos["mint"], pos["tokens"])
            except Exception as e:
                with self._lock:                      # devolve pra tentar de novo
                    self.open_positions.append(pos)
                self.log_callback(f"[VENDA falhou] {reason} {pos['mint'][:8]}…: {e}")
                return False
            proceeds = res["proceeds_sol"]
            sig = res["sig"]
            exit_price = proceeds / pos["tokens"] if pos["tokens"] else 0
        else:
            exit_price = sim_exit_price if sim_exit_price else pos["current_price"]
            proceeds = pos["tokens"] * exit_price
            sig = None

        pnl = proceeds - pos["stake_sol"]
        pnl_pct = (proceeds / pos["stake_sol"] - 1) * 100 if pos["stake_sol"] else 0

        # 3) registra o fechamento
        with self._lock:
            if self.live_mode:
                try:
                    self.cash = self.executor.sol_balance()
                except Exception:
                    self.cash += proceeds
            else:
                self.cash += proceeds
            self.realized_pnl += pnl
            closed = {**pos, "exit_price": exit_price, "exit_reason": reason,
                      "pnl_sol": pnl, "pnl_pct": pnl_pct, "exit_ts": int(time.time()),
                      "sell_sig": sig}
            self.closed_positions.append(closed)
        extra = f" sig={sig[:12]}…" if sig else ""
        self.log_callback(f"[VENDA ] {reason}  pnl={pnl:+.3f} SOL ({pnl_pct:+.0f}%)  "
                          f"mint={pos['mint'][:8]}…{extra}")
        return True

    # ---- snapshot para a UI ----------------------------------------------

    def get_state(self):
        with self._lock:
            open_value = sum(p["tokens"] * p["current_price"] for p in self.open_positions)
            equity = self.cash + open_value
            open_copy = []
            for p in self.open_positions:
                cur_val = p["tokens"] * p["current_price"]
                pnl = cur_val - p["stake_sol"]
                pnl_pct = (p["current_price"] / p["entry_price"] - 1) * 100 if p["entry_price"] else 0
                open_copy.append({**p, "pnl_sol": pnl, "pnl_pct": pnl_pct})
            closed_copy = list(self.closed_positions)
            pending_copy = []
            for p in self.pending:
                prog = (p["current_price"] / p["ref_price"] - 1) * 100 if p["ref_price"] else 0
                pending_copy.append({**p, "progress_pct": prog})
            last_poll = self.last_poll_ts
            cycles = self.cycles
        return {
            "cash": self.cash,
            "equity": equity,
            "realized_pnl": self.realized_pnl,
            "open_positions": open_copy,
            "pending": pending_copy,
            "closed_positions": closed_copy,
            "initial_bankroll": self.initial_bankroll,
            "last_poll_ts": last_poll,
            "cycles": cycles,
            "halted": self.halted,
            "running": self.is_running(),
        }
