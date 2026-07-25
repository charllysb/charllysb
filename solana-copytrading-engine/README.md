# Solana Copy-Trading Engine

Motor de copy-trading on-chain para Solana: monitora carteiras-alvo, replica as
operações delas com gestão de risco própria e executa **transações reais**
assinadas localmente — com interface desktop, kill-switch e stop-loss.

> Projeto de estudo/pesquisa em execução on-chain. Trading de memecoin é de
> altíssimo risco; o código existe para demonstrar a engenharia, não como
> recomendação financeira.

## O que ele faz

- **Monitora carteiras-alvo** na Solana via Helius (Enhanced Transactions API),
  identificando swaps de compra/venda em tempo quase real.
- **Replica as entradas** com dimensionamento próprio de banca — em vez de copiar
  o valor absoluto do trader (inviável para bancas pequenas), calcula o stake por
  número de posições simultâneas: `caixa / vagas_restantes`.
- **Executa de verdade** (modo live) via PumpPortal *local transaction API*: a
  transação é montada remotamente mas **assinada localmente** — a chave privada
  nunca sai da máquina.
- **Gerencia risco** com três camadas: stop-loss por posição, venda quando a
  carteira-alvo vende, e um **disjuntor** que liquida tudo e desliga o bot ao
  atingir um limite de perda.
- **Analisa a carteira antes de seguir**: calcula hit-rate, PnL e médias de
  ganho/perda do histórico dela e pede confirmação antes de adicioná-la.

## Arquitetura

```
collector.py       coleta de swaps on-chain (Helius) + parsing de tokenTransfers
   └─ db.py        persistência SQLite (dedupe por signature)

copy_engine.py     motor: thread própria, estado thread-safe, stop-loss,
                   disjuntor, execução simulada OU real
   └─ live_executor.py   assinatura local (Ed25519/SLIP-0010), envio e
                         confirmação da transação, leitura de saldos

wallet_analysis.py score de lucratividade da carteira (FIFO)
   └─ analyze.py   pareamento FIFO de compras/vendas → PnL realizado

gui.py             interface Tkinter: parâmetros, posições ao vivo, venda
                   manual, log e heartbeat
```

## Decisões técnicas que valem nota

- **Execução fora do lock.** As chamadas de rede (1–3s para confirmar uma
  transação) rodam fora da região crítica; só a mutação de estado é protegida.
  Sem isso, a UI congelaria a cada trade.
- **PnL medido pela própria transação.** O custo real de cada trade vem do
  `pre/postBalance` **daquela** transação, não de ler o saldo global antes/depois
  — que corrompe a medição quando há trades concorrentes (bug real que ocorreu e
  foi corrigido; o saldo global acusava perdas fantasmas).
- **Derivação de chave SLIP-0010** (`m/44'/501'/0'/0'`) a partir da seed BIP39,
  compatível com Phantom, implementada sem depender de bibliotecas externas de
  derivação.
- **Reconciliação com a rede.** O caixa é ressincronizado com o saldo on-chain a
  cada ciclo, em vez de confiar apenas na contabilidade interna.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env     # preencha suas chaves
python gui.py
```

Abre em **modo simulado** por padrão. O modo real exige marcar o checkbox e
confirmar num diálogo — e recomenda-se carteira dedicada com saldo baixo.

## Aprendizado do projeto

Rodando com dinheiro real, o resultado foi **negativo**: o atrito de execução
(taxas do pump.fun/PumpPortal + slippage + latência de 1–3s para confirmar)
consome a vantagem do sinal. A conclusão está documentada porque medir e
descartar uma hipótese é parte do trabalho — o repositório companheiro
[`pumpfun-momentum-bot`](../pumpfun-momentum-bot) traz a medição de slippage que
quantifica isso.

## Stack

Python · asyncio/threading · Solana (`solders`, `solana-py`) · Helius API ·
PumpPortal · SQLite · Tkinter

---

> Os módulos `collector.py`, `db.py`, `analyze.py` e `wallet_analysis.py` também
> aparecem em `onchain-wallet-analytics`; foram duplicados de propósito para que
> cada repositório rode de forma independente.
