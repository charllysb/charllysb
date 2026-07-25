# Hi, I'm Charllys 👋

**I build crypto trading & automation systems — on-chain execution, real-time data, and honest backtesting.**

Python engineer focused on Solana/DeFi automation: copy-trading engines, momentum bots, on-chain analytics, and backtesting frameworks. I care as much about **risk controls and measuring what actually works** as about the code — my projects ship with kill-switches, fee/slippage modeling, and honest post-mortems.

---

### 🔧 What I build
- **On-chain execution** — real transaction signing (`solders` / `solana-py`), PumpPortal integration, encrypted key vaults
- **Real-time data** — WebSocket streams, `asyncio` pipelines, Helius / DexScreener integrations
- **Trading logic** — copy-trading, momentum entry/exit, trailing stops, circuit breakers
- **Analysis & backtesting** — FIFO PnL, wallet profiling, strategy backtests vs. buy & hold

### 📌 Featured projects

| Project | What it demonstrates |
|---|---|
| **[solana-copytrading-engine](https://github.com/charllysb/solana-copytrading-engine)** | Live on-chain copy-trading — real execution, encrypted vault, Tkinter GUI, stop-loss + circuit breaker |
| **[pumpfun-momentum-bot](https://github.com/charllysb/pumpfun-momentum-bot)** | Real-time WebSocket momentum bot with slippage/latency modeling and paper → live modes |
| **[onchain-wallet-analytics](https://github.com/charllysb/onchain-wallet-analytics)** | On-chain data pipeline — collect Solana swaps, profile wallets, backtest entry filters |
| **[llm-trading-backtest](https://github.com/charllysb/llm-trading-backtest)** | Backtest engine (`ccxt` + `pandas`) benchmarking LLM-driven and rule-based strategies vs. buy & hold |

### 🧰 Stack
`Python` · `asyncio` · `Solana (solders, solana-py)` · `WebSockets` · `SQLite` · `pandas` · `ccxt` · `cryptography` · `Tkinter`

### 🧭 How I work
I test before I trust. Every strategy is simulated with **realistic friction** (fees, slippage, latency) and benchmarked before any real capital touches it. When a strategy doesn't beat the benchmark, I document **why** — because knowing what *doesn't* work is worth more than a bot that promises what it can't deliver.

---

📫 **charllys.lock@gmail.com** — open to freelance/contract work in crypto automation, trading infra, and on-chain tooling.
