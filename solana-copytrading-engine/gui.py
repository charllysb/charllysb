"""
Interface Tkinter para o copy-trading simulado.

- Adicione/remova wallets-alvo (persiste em wallets.json)
- Configure banca inicial, stake (%) e stop-loss (%)
- Inicie o bot: ao detectar uma compra de uma wallet ativa, abre uma posicao
  simulada do tamanho do stake e monitora ate a wallet vender ou bater o stop
- Exibe banca atual, posicoes abertas e PnL de cada uma

Uso:
    python gui.py
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from dotenv import load_dotenv

from copy_engine import CopyTradingEngine
from wallet_analysis import analyze_wallet, format_summary

load_dotenv()

WALLETS_FILE = Path(__file__).parent / "wallets.json"
LOG_FILE = Path(__file__).parent / "gui.log"


def load_wallets():
    if WALLETS_FILE.exists():
        try:
            return json.loads(WALLETS_FILE.read_text()).get("wallets", [])
        except (json.JSONDecodeError, OSError):
            pass
    # seed inicial a partir do .env, se existir
    env = os.environ.get("TARGET_WALLETS", "")
    return [w.strip() for w in env.split(",") if w.strip()]


def save_wallets(wallets):
    WALLETS_FILE.write_text(json.dumps({"wallets": wallets}, indent=2))


def short(s, n=8):
    return (s[:n] + "…") if s and len(s) > n else (s or "")


class App:
    def __init__(self, root):
        self.root = root
        root.title("Axiom Copy-Trading")
        root.geometry("980x820")

        self.engine = None
        self.log_queue = queue.Queue()
        self.wallets = load_wallets()
        self._halt_notified = False

        self._build_config()
        self._build_wallets()
        self._build_stats()
        self._build_watchlist()
        self._build_positions()
        self._build_log()

        self._refresh_wallet_list()
        self._tick()  # loop de atualizacao da UI

    # ---- construcao da UI -------------------------------------------------

    def _build_config(self):
        f = ttk.LabelFrame(self.root, text="Configuracao")
        f.pack(fill="x", padx=8, pady=4)

        self.var_bankroll = tk.StringVar(value="10")
        self.var_maxpos = tk.StringVar(value="20")
        self.var_trigger = tk.StringVar(value="20")
        self.var_stop = tk.StringVar(value="15")
        self.var_drawdown = tk.StringVar(value="40")
        self.var_poll = tk.StringVar(value="15")
        self.var_live = tk.BooleanVar(value=False)

        self.entry_bankroll = None
        for i, (label, var) in enumerate([
            ("Banca inicial (SOL)", self.var_bankroll),
            ("Posicoes max", self.var_maxpos),
            ("Gatilho entrada (+%)", self.var_trigger),
            ("Stop-loss (%)", self.var_stop),
            ("Disjuntor (-%)", self.var_drawdown),
            ("Intervalo (s)", self.var_poll),
        ]):
            ttk.Label(f, text=label).grid(row=0, column=i * 2, padx=(8, 2), pady=6, sticky="e")
            e = ttk.Entry(f, textvariable=var, width=8)
            e.grid(row=0, column=i * 2 + 1, padx=(0, 8), pady=6, sticky="w")
            if var is self.var_bankroll:
                self.entry_bankroll = e

        self.config_entries = f

        self.btn_start = ttk.Button(f, text="▶ Iniciar bot", command=self.on_start)
        self.btn_start.grid(row=0, column=12, padx=8)
        self.btn_stop = ttk.Button(f, text="■ Parar", command=self.on_stop, state="disabled")
        self.btn_stop.grid(row=0, column=13, padx=8)

        self.chk_live = ttk.Checkbutton(
            f, text="Operar de verdade (live)", variable=self.var_live,
            command=self.on_toggle_live)
        self.chk_live.grid(row=1, column=0, columnspan=4, padx=8, pady=(0, 6), sticky="w")
        self.lbl_live = ttk.Label(f, text="", foreground="#b00")
        self.lbl_live.grid(row=1, column=4, columnspan=5, padx=8, pady=(0, 6), sticky="w")

    def _build_wallets(self):
        f = ttk.LabelFrame(self.root, text="Wallets-alvo")
        f.pack(fill="x", padx=8, pady=4)

        self.lst_wallets = tk.Listbox(f, height=4)
        self.lst_wallets.pack(side="left", fill="x", expand=True, padx=(8, 4), pady=6)

        right = ttk.Frame(f)
        right.pack(side="left", padx=8, pady=6)
        self.var_new_wallet = tk.StringVar()
        ttk.Entry(right, textvariable=self.var_new_wallet, width=46).pack(pady=2)
        self.btn_add = ttk.Button(right, text="+ Analisar e adicionar", command=self.on_add_wallet)
        self.btn_add.pack(fill="x", pady=2)
        ttk.Button(right, text="− Remover selecionada", command=self.on_remove_wallet).pack(fill="x", pady=2)

    def _build_stats(self):
        f = ttk.LabelFrame(self.root, text="Banca")
        f.pack(fill="x", padx=8, pady=4)

        self.var_equity = tk.StringVar(value="—")
        self.var_cash = tk.StringVar(value="—")
        self.var_realized = tk.StringVar(value="—")
        self.var_nopen = tk.StringVar(value="—")
        self.var_nwatch = tk.StringVar(value="—")
        self.var_lastpoll = tk.StringVar(value="bot parado")

        for i, (label, var) in enumerate([
            ("Banca atual (equity)", self.var_equity),
            ("Caixa livre", self.var_cash),
            ("PnL realizado", self.var_realized),
            ("Posicoes abertas", self.var_nopen),
            ("Em observacao", self.var_nwatch),
            ("Ultima verificacao", self.var_lastpoll),
        ]):
            ttk.Label(f, text=label + ":").grid(row=0, column=i * 2, padx=(8, 2), pady=6, sticky="e")
            ttk.Label(f, textvariable=var, font=("Segoe UI", 10, "bold")).grid(
                row=0, column=i * 2 + 1, padx=(0, 12), pady=6, sticky="w")

    def _build_watchlist(self):
        f = ttk.LabelFrame(self.root, text="Em observacao (aguardando gatilho de entrada)")
        f.pack(fill="both", expand=True, padx=8, pady=4)

        cols = ("wallet", "mint", "ref", "atual", "alvo", "progresso")
        self.watch_tree = ttk.Treeview(f, columns=cols, show="headings", height=4)
        headers = {
            "wallet": "Wallet", "mint": "Mint", "ref": "Ref (entrada)",
            "atual": "Atual", "alvo": "Alvo (gatilho)", "progresso": "Progresso",
        }
        for c in cols:
            self.watch_tree.heading(c, text=headers[c])
            self.watch_tree.column(c, width=120, anchor="center")
        self.watch_tree.pack(fill="both", expand=True, padx=6, pady=6)

    def _build_positions(self):
        f = ttk.LabelFrame(self.root, text="Posicoes abertas")
        f.pack(fill="both", expand=True, padx=8, pady=4)

        cols = ("wallet", "mint", "stake", "entry", "atual", "pnl_sol", "pnl_pct")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=8)
        headers = {
            "wallet": "Wallet", "mint": "Mint", "stake": "Stake (SOL)",
            "entry": "Entrada", "atual": "Atual", "pnl_sol": "PnL (SOL)", "pnl_pct": "PnL %",
        }
        for c in cols:
            self.tree.heading(c, text=headers[c])
            self.tree.column(c, width=120, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=6, pady=(6, 2))

        bar = ttk.Frame(f)
        bar.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(bar, text="Vender selecionada", command=self.on_manual_sell).pack(side="left")
        ttk.Label(bar, text="(fecha a posicao agora, ao preco atual)").pack(side="left", padx=8)

    def _build_log(self):
        f = ttk.LabelFrame(self.root, text="Log")
        f.pack(fill="both", expand=True, padx=8, pady=4)
        self.txt_log = tk.Text(f, height=8, state="disabled", wrap="word")
        self.txt_log.pack(fill="both", expand=True, padx=6, pady=6)

    # ---- acoes de wallets -------------------------------------------------

    def _refresh_wallet_list(self):
        self.lst_wallets.delete(0, tk.END)
        for w in self.wallets:
            self.lst_wallets.insert(tk.END, w)

    def on_add_wallet(self):
        w = self.var_new_wallet.get().strip()
        if not w:
            return
        if w in self.wallets:
            messagebox.showinfo("Wallet", "Essa wallet ja esta na lista.")
            return
        # analisa a lucratividade antes de adicionar (em thread, pra nao travar a UI)
        self.btn_add.config(state="disabled", text="Analisando…")
        self._log(f"Analisando carteira {short(w, 10)}…")
        threading.Thread(target=self._analyze_wallet_worker, args=(w,), daemon=True).start()

    def _analyze_wallet_worker(self, wallet):
        result = analyze_wallet(wallet)
        # volta para a thread da UI para exibir o dialog
        self.root.after(0, lambda: self._on_analysis_done(wallet, result))

    def _on_analysis_done(self, wallet, result):
        self.btn_add.config(state="normal", text="+ Analisar e adicionar")
        summary = format_summary(result)
        self._log(f"Analise de {short(wallet, 10)}: " + summary.replace("\n", " | "))
        if result.get("error"):
            messagebox.showerror("Analise falhou", summary)
            return
        add = messagebox.askyesno(
            "Resultado da analise",
            f"{summary}\n\nAdicionar essa carteira ao copy-trading?",
        )
        if not add:
            return
        self.wallets.append(wallet)
        save_wallets(self.wallets)
        self._refresh_wallet_list()
        self.var_new_wallet.set("")
        if self.engine and self.engine.is_running():
            messagebox.showinfo(
                "Wallet adicionada",
                "Reinicie o bot (Parar -> Iniciar) para passar a monitorar a nova carteira.",
            )

    def on_remove_wallet(self):
        sel = self.lst_wallets.curselection()
        if not sel:
            return
        w = self.wallets[sel[0]]
        running = self.engine and self.engine.is_running()

        # conta posicoes abertas dessa carteira (so faz sentido com o bot rodando)
        n_open = 0
        if running:
            state = self.engine.get_state()
            n_open = sum(1 for p in state["open_positions"] if p["wallet"] == w)

        if n_open > 0:
            choice = messagebox.askyesnocancel(
                "Fechar posicoes?",
                f"A carteira {short(w, 10)} tem {n_open} posicao(oes) aberta(s).\n\n"
                "Sim     = fechar essas posicoes agora e remover a carteira\n"
                "Nao     = remover a carteira e DEIXAR as posicoes abertas\n"
                "Cancelar = nao remover nada",
            )
            if choice is None:
                return
            if choice:
                closed = self.engine.close_positions_for_wallet(w)
                self._log(f"{closed} posicao(oes) de {short(w, 10)} fechadas ao remover a carteira.")

        self.wallets.pop(sel[0])
        save_wallets(self.wallets)
        self._refresh_wallet_list()
        self._log(f"Wallet removida: {short(w, 10)}")
        if running:
            self._log("Obs: reinicie o bot (Parar -> Iniciar) para parar de monitorar essa carteira.")

    # ---- modo real --------------------------------------------------------

    def on_toggle_live(self):
        if self.var_live.get():
            # le o saldo real da carteira e trava o campo de banca
            try:
                from live_executor import LiveExecutor
                ex = LiveExecutor()
                bal = ex.sol_balance()
            except Exception as e:
                self.var_live.set(False)
                messagebox.showerror(
                    "Modo real indisponivel",
                    f"Nao consegui carregar a carteira de execucao:\n{e}\n\n"
                    "Verifique LIVE_SEED_PHRASE (ou LIVE_PRIVATE_KEY) e LIVE_RPC no .env.")
                return
            self.var_bankroll.set(f"{bal:.4f}")
            self.entry_bankroll.config(state="disabled")
            self.lbl_live.config(text=f"⚠ DINHEIRO REAL — carteira {short(ex.pubkey, 10)}, "
                                       f"saldo {bal:.4f} SOL")
        else:
            self.entry_bankroll.config(state="normal")
            self.var_bankroll.set("10")
            self.lbl_live.config(text="")

    # ---- start / stop -----------------------------------------------------

    def on_start(self):
        if not self.wallets:
            messagebox.showwarning("Wallets", "Adicione pelo menos uma wallet.")
            return
        live = self.var_live.get()
        try:
            bankroll = float(self.var_bankroll.get())
            max_pos = int(self.var_maxpos.get())
            trigger = float(self.var_trigger.get())
            stop = float(self.var_stop.get())
            drawdown = float(self.var_drawdown.get())
            poll = int(self.var_poll.get())
            assert (bankroll > 0 and max_pos >= 1 and trigger >= 0 and 0 < stop < 100
                    and 0 < drawdown < 100 and poll >= 5)
        except (ValueError, AssertionError):
            messagebox.showerror("Configuracao", "Valores invalidos. Banca>0, posicoes≥1, "
                                                   "gatilho≥0, 0<stop<100, 0<disjuntor<100, intervalo≥5s.")
            return

        if live:
            if not messagebox.askyesno(
                "Confirmar modo REAL",
                "O bot vai comprar e vender com DINHEIRO REAL da carteira configurada.\n\n"
                f"Saldo: {bankroll:.4f} SOL  |  ate {max_pos} posicoes  |  stop -{stop:.0f}%\n\n"
                "Tem certeza que quer iniciar em modo real?"):
                return

        try:
            self.engine = CopyTradingEngine(
                wallets=self.wallets, initial_bankroll=bankroll, max_positions=max_pos,
                stop_loss_pct=stop, poll_interval=poll, log_callback=self._enqueue_log,
                live_mode=live, entry_trigger_pct=trigger, max_drawdown_pct=drawdown,
            )
        except Exception as e:
            messagebox.showerror("Erro ao iniciar", f"Falha ao preparar o bot:\n{e}")
            return

        self._halt_notified = False
        self.engine.start()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")

    def on_stop(self):
        if self.engine:
            self.engine.stop()
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")

    def on_manual_sell(self):
        if not self.engine or not self.engine.is_running():
            messagebox.showinfo("Bot parado", "Inicie o bot para vender posicoes.")
            return
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Venda manual", "Selecione uma posicao na lista.")
            return
        pos_id = int(sel[0])
        if not messagebox.askyesno("Venda manual", "Fechar essa posicao agora, ao preco atual?"):
            return
        ok, msg = self.engine.manual_sell(pos_id)
        if not ok:
            messagebox.showwarning("Venda manual", f"Nao foi possivel vender: {msg}")

    # ---- logging (thread-safe) -------------------------------------------

    def _enqueue_log(self, msg):
        """Chamado da thread do engine — so empilha; a UI consome no _tick."""
        self.log_queue.put(msg)

    def _log(self, msg):
        stamped = f"{time.strftime('%H:%M:%S')}  {msg}"
        self.txt_log.config(state="normal")
        self.txt_log.insert(tk.END, stamped + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state="disabled")
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(stamped + "\n")
        except OSError:
            pass

    # ---- loop de atualizacao da UI ---------------------------------------

    def _tick(self):
        while not self.log_queue.empty():
            self._log(self.log_queue.get_nowait())

        if self.engine:
            state = self.engine.get_state()

            # disjuntor desligou o bot sozinho -> reseta botoes e avisa uma vez
            if not state.get("running", True) and str(self.btn_stop["state"]) == "normal":
                self.btn_start.config(state="normal")
                self.btn_stop.config(state="disabled")
                if state.get("halted") and not self._halt_notified:
                    self._halt_notified = True
                    messagebox.showwarning(
                        "Disjuntor acionado",
                        f"O bot atingiu o limite de perda e fechou tudo automaticamente.\n"
                        f"Equity: {state['equity']:.3f} SOL "
                        f"(banca inicial {state['initial_bankroll']:.3f} SOL).\n\n"
                        "Revise antes de reiniciar.")

            self.var_equity.set(f"{state['equity']:.3f} SOL")
            self.var_cash.set(f"{state['cash']:.3f} SOL")
            pnl = state["realized_pnl"]
            self.var_realized.set(f"{pnl:+.3f} SOL")
            self.var_nopen.set(str(len(state["open_positions"])))
            self.var_nwatch.set(str(len(state.get("pending", []))))
            if state["last_poll_ts"]:
                hhmmss = time.strftime("%H:%M:%S", time.localtime(state["last_poll_ts"]))
                self.var_lastpoll.set(f"{hhmmss} (ciclo {state['cycles']})")

            self.watch_tree.delete(*self.watch_tree.get_children())
            for p in state.get("pending", []):
                self.watch_tree.insert("", tk.END, values=(
                    short(p["wallet"], 6), short(p["mint"], 8),
                    f"{p['ref_price']:.2e}", f"{p['current_price']:.2e}",
                    f"{p['trigger_price']:.2e}", f"{p['progress_pct']:+.0f}%",
                ))

            self.tree.delete(*self.tree.get_children())
            for p in state["open_positions"]:
                self.tree.insert("", tk.END, iid=str(p["id"]), values=(
                    short(p["wallet"], 6), short(p["mint"], 8),
                    f"{p['stake_sol']:.3f}", f"{p['entry_price']:.2e}",
                    f"{p['current_price']:.2e}", f"{p['pnl_sol']:+.3f}",
                    f"{p['pnl_pct']:+.0f}%",
                ))

        self.root.after(1000, self._tick)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
