# pump.fun Momentum Bot

Bot de momentum para tokens recém-criados na pump.fun (Solana). Consome o
**stream de trades em tempo real** via WebSocket, aplica filtros de entrada,
sai por **reversão** (trailing stop a partir do pico) e mede o resultado com um
**modelo de atrito realista**.

Inclui um estudo honesto de viabilidade: o bot foi rodado com dinheiro real e o
resultado — com a análise do porquê — está documentado abaixo.

> Projeto de pesquisa. Trading de memecoin é de altíssimo risco; nada aqui é
> recomendação financeira.

## Como funciona

```
PumpPortal WebSocket ──► todo token que nasce + trades tick a tick
        │
        ▼
  OBSERVAÇÃO           filtros: valorização mínima, janela de tempo,
                       compradores únicos, anti-dump, corte precoce
        │
        ▼
   ENTRADA             stake fixo, limite de posições simultâneas
        │
        ▼
   SAÍDA               trailing stop do pico · stop duro · stop por
                       inatividade · disjuntor de perda total
```

**Sem take-profit fixo**: a saída é por reversão. O bot guarda o pico desde a
entrada e vende quando o preço cai X% *daquele topo* — deixando o vencedor
correr e cortando na virada.

## Diferenciais

- **Modelo de atrito explícito.** O PnL simulado desconta taxa por lado,
  slippage de entrada/saída e custo fixo por trade. O resumo mostra **bruto
  (só o sinal)** e **líquido (com atrito)** lado a lado — isolando "o sinal é
  bom?" de "sobrevive ao custo?".
- **Medidor de slippage real** (`slippage_test.py`): compara o preço da
  *bonding curve* on-chain no instante da decisão com o preço de preenchimento
  real, e cronometra a latência. Responde com número, não com achismo.
- **Cofre criptografado** (`vault.py`): seed phrase e chaves ficam num arquivo
  cifrado (PBKDF2-SHA256 200k + Fernet). A senha nunca é armazenada — é pedida
  em runtime e os segredos só existem em memória.
- **Modo simulado e real** no mesmo motor, com kill-switch e travas de exposição.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
python bot_gui.py
```

A GUI expõe **todos os parâmetros** (com tooltips), presets salváveis, saldo das
carteiras e o log ao vivo. Começa em modo simulado.

> O stream de trades da PumpPortal exige uma API key com saldo mínimo. Sem ela,
> apenas os eventos de criação de token chegam (nenhuma entrada dispara).

## Resultado do estudo

Duas rodadas de simulação (~370 trades cada) e uma rodada real:

| Cenário | Resultado |
|---|---|
| Simulado, sem atrito | positivo — o sinal existe |
| Simulado, atrito 2%/lado | ainda positivo na v2 (após calibrar filtros) |
| **Real** | **negativo** |

**O que a rodada real revelou:** tokens que subiram +827% no gráfico ainda
fecharam no prejuízo. O motivo é latência — quando o gatilho dispara, a ordem
leva 1–3s para confirmar, e nesse intervalo o preço já reverteu. O sinal é
visível; **capturá-lo com execução de varejo, não**.

Também documentado: uma sessão real subiu +24% nos 4 primeiros minutos e
devolveu tudo nos 32 seguintes — variância inicial mascarando expectativa
negativa, com ~90 ida-e-voltas girando a banca 7×.

**Conclusão:** a estratégia não sobrevive ao atrito de execução em varejo. O
código fica como estudo de arquitetura de tempo real e de metodologia de
validação.

## Stack

Python · asyncio · WebSockets · Solana (`solders`, `solana-py`) · PumpPortal ·
`cryptography` (PBKDF2/Fernet) · Tkinter

---

> `live_executor.py` é compartilhado com
> [`solana-copytrading-engine`](../solana-copytrading-engine); duplicado de
> propósito para manter cada repositório executável de forma independente.
