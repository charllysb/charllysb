# On-Chain Wallet Analytics

Pipeline de análise de carteiras de memecoin na Solana: coleta o histórico de
swaps on-chain, reconstrói posições por FIFO, calcula lucratividade real e testa
hipóteses sobre o que separa uma entrada boa de uma ruim.

É a camada de **pesquisa** por trás dos bots — a parte que responde "essa
estratégia tem vantagem?" antes de arriscar capital.

## Pipeline

```
collector.py    coleta swaps via Helius (paginado, dedupe por signature)
      └─ db.py  SQLite

analyze.py      pareamento FIFO compra→venda  →  PnL realizado por posição
      │
      ├─ wallet_analysis.py   score da carteira: hit-rate, PnL, médias
      ├─ backtest.py          testa limiares de stop-loss no histórico
      ├─ features.py          extrai atributos de cada entrada
      ├─ clustering.py        sobreposição entre carteiras (smart money?)
      ├─ momentum.py          tração inicial do token (traders nos 1ºs 60/120s)
      ├─ momentum_analysis.py cruza tração × resultado
      ├─ mint_age.py          idade real do token (tx CREATE on-chain)
      └─ enrich.py            metadados de token (DexScreener)
```

## Achados

O objetivo era encontrar um filtro de entrada com poder preditivo. Resultado
honesto, com ~370 posições fechadas:

- **Exit beats entry.** Nenhum filtro de *entrada* testado (idade do token,
  liquidez, sobreposição entre carteiras, tração inicial) separou vencedores de
  perdedores de forma consistente. O que mais melhorou o resultado foi
  **disciplina de saída** — um stop-loss em -15% teria adicionado ganho
  relevante nas carteiras indisciplinadas.
- **O lucro vive na cauda.** Todo o resultado positivo veio de tokens que
  passaram de +30% após a entrada; os que ficaram abaixo de +10% concentraram a
  perda. Como o pico é desconhecido na entrada, a estratégia depende de cortar
  perdedor rápido e deixar vencedor correr.
- **"Smart money" não se confirmou.** Praticamente não houve sobreposição de
  tokens entre as carteiras lucrativas analisadas — o sinal não é coletivo.
- **Atrito domina.** Medido em transações reais: a taxa de rede é irrisória
  (~0.0001 SOL/tx), mas taxa de protocolo + slippage custam ~3-5% por
  ida-e-volta. Uma estratégia com trade mediano de -6% e cauda longa não
  sobrevive a isso.

Detalhe metodológico que mudou a conclusão: uma medição inicial acusou perda
grande, mas a **verificação contra o saldo on-chain** mostrou que o cálculo
estava errado (medição concorrente do saldo global). Conferir o número na fonte
é parte do método.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # HELIUS_API_KEY e TARGET_WALLETS

python collector.py --backfill    # baixa o histórico das carteiras
python analyze.py                 # PnL e hit-rate por carteira
python wallet_analysis.py <WALLET>  # score de uma carteira específica
python backtest.py                # testa limiares de stop-loss
```

## Stack

Python · Helius Enhanced Transactions API · DexScreener · SQLite · análise
FIFO de posições
