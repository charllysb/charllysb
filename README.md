# Hi, I'm Charllys 👋

**I build automations and integrations — the plumbing between the tools your team keeps copying data between by hand.**

Python and n8n engineer. I work on lead routing, document extraction, system-to-system sync, and the dashboards that make those pipelines observable. I care as much about **what happens when an API fails at 3am** as about the happy path — my workflows ship with retries, error branches, idempotent writes, and an explicit answer for every case where two systems disagree.

**I work async-first:** scope in writing, detailed written updates, no meeting overhead. Most integration projects ship in 3–7 days.

---

### 🔧 What I build

- **Workflow automation** — n8n, Make, webhooks, cron, queue-backed retries
- **AI inside pipelines** — LLM extraction and classification with schema validation and confidence gating, so a bad read never silently becomes a database row
- **Backend & data** — Python, FastAPI, PostgreSQL, pandas, REST/GraphQL integration
- **Frontend** — Next.js, React, TypeScript, Tailwind

### 📌 Featured projects

**Automation & integration**

| Project | What it demonstrates |
|---|---|
| **[n8n-automation-workflows](https://github.com/charllysb/n8n-automation-workflows)** | Five production-shaped workflows — lead routing, invoice processing, content pipeline, support triage with SLA escalation, bidirectional sync with per-field conflict resolution |

**Systems engineering** — built in the trading domain, but the engineering is what integration work needs: unreliable third-party APIs, partial failure, credentials kept out of code, and honest measurement.

| Project | What it demonstrates |
|---|---|
| **[solana-copytrading-engine](https://github.com/charllysb/solana-copytrading-engine)** | Live on-chain execution — encrypted key vault, stop-loss, circuit breaker |
| **[pumpfun-momentum-bot](https://github.com/charllysb/pumpfun-momentum-bot)** | Real-time WebSocket processing with slippage/latency modeling, paper → live modes |
| **[onchain-wallet-analytics](https://github.com/charllysb/onchain-wallet-analytics)** | High-volume data pipeline — collect swaps, FIFO PnL, wallet profiling |
| **[llm-trading-backtest](https://github.com/charllysb/llm-trading-backtest)** | Backtest harness (`ccxt` + `pandas`) benchmarking LLM and rule-based strategies vs. a baseline |

### 🧰 Stack

`Python` · `n8n` · `asyncio` · `FastAPI` · `PostgreSQL` · `pandas` · `Next.js` · `TypeScript` · `Docker` · `WebSockets` · `cryptography`

### 🧭 How I work

**I test before I trust.** Every pipeline is run against realistic friction — rate limits, partial failures, malformed payloads, the row that arrives twice — and benchmarked before it touches anything that matters. When something doesn't work, I document **why**, because knowing what *doesn't* work is worth more than an automation that promises what it can't deliver.

**You own everything.** Code, credentials, and infrastructure stay in your accounts. Workflows are exportable and documented so your team can maintain them without me.

---

📫 **charllys.lock@gmail.com** — available for freelance and contract work in automation, integrations, and internal tooling.
