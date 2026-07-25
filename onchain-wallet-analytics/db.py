"""Camada de persistencia: SQLite para trades coletados."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "trades.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                signature   TEXT PRIMARY KEY,
                wallet      TEXT NOT NULL,
                timestamp   INTEGER NOT NULL,
                action      TEXT NOT NULL,          -- buy | sell
                token_mint  TEXT,
                token_amount REAL,
                sol_amount  REAL,
                source      TEXT,                   -- pump.fun, raydium, etc
                raw         TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_wallet ON trades(wallet)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_mint ON trades(token_mint)")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_meta (
                mint              TEXT PRIMARY KEY,
                pair_created_at   INTEGER,   -- unix seconds: criacao do PAR (migracao p/ AMM), nao do token
                created_at_chain  INTEGER,   -- unix seconds: tx CREATE real do mint (idade verdadeira)
                dex_id            TEXT,
                liquidity_usd_now REAL,      -- snapshot no momento da consulta, NAO no momento da compra
                volume_h24_now    REAL,
                fdv_now           REAL,
                fetched_at        INTEGER NOT NULL
            )
            """
        )
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(token_meta)")}
        if "created_at_chain" not in cols:
            conn.execute("ALTER TABLE token_meta ADD COLUMN created_at_chain INTEGER")


def get_token_meta(mint: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM token_meta WHERE mint = ?", (mint,)).fetchone()
        return dict(row) if row else None


def upsert_token_meta(m: dict):
    m = {**m, "created_at_chain": m.get("created_at_chain")}
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO token_meta
            (mint, pair_created_at, created_at_chain, dex_id, liquidity_usd_now, volume_h24_now, fdv_now, fetched_at)
            VALUES (:mint, :pair_created_at, :created_at_chain, :dex_id, :liquidity_usd_now, :volume_h24_now, :fdv_now, :fetched_at)
            ON CONFLICT(mint) DO UPDATE SET
                pair_created_at=excluded.pair_created_at,
                dex_id=excluded.dex_id,
                liquidity_usd_now=excluded.liquidity_usd_now,
                volume_h24_now=excluded.volume_h24_now,
                fdv_now=excluded.fdv_now,
                fetched_at=excluded.fetched_at
            """,
            m,
        )


def set_created_at_chain(mint: str, ts: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE token_meta SET created_at_chain = ? WHERE mint = ?", (ts, mint)
        )


def init_paper_tables():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_processed (
                signature TEXT PRIMARY KEY
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS paper_positions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet          TEXT NOT NULL,
                mint            TEXT NOT NULL,
                entry_sol       REAL NOT NULL,
                entry_tokens    REAL NOT NULL,
                entry_price_sol REAL NOT NULL,   -- SOL por token
                entry_ts        INTEGER NOT NULL,
                status          TEXT NOT NULL DEFAULT 'open',  -- open | closed
                exit_reason     TEXT,             -- stop_loss | wallet_sell
                exit_price_sol  REAL,
                exit_ts         INTEGER,
                pnl_sol         REAL,
                pnl_pct         REAL
            )
            """
        )


def bootstrap_paper_processed():
    """Marca todo trade ja coletado (historico) como processado, para o paper
    trading so reagir a compras/vendas genuinamente novas a partir de agora."""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO paper_processed (signature) "
            "SELECT signature FROM trades"
        )


def is_paper_processed(signature: str) -> bool:
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM paper_processed WHERE signature = ?", (signature,)
        ).fetchone() is not None


def mark_paper_processed(signature: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO paper_processed (signature) VALUES (?)", (signature,)
        )


def open_paper_position(wallet: str, mint: str, entry_sol: float, entry_tokens: float, entry_ts: int):
    entry_price = entry_sol / entry_tokens if entry_tokens else 0
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO paper_positions
            (wallet, mint, entry_sol, entry_tokens, entry_price_sol, entry_ts)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (wallet, mint, entry_sol, entry_tokens, entry_price, entry_ts),
        )


def get_open_position(wallet: str, mint: str):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM paper_positions
            WHERE wallet = ? AND mint = ? AND status = 'open'
            ORDER BY entry_ts ASC LIMIT 1
            """,
            (wallet, mint),
        ).fetchone()
        return dict(row) if row else None


def get_all_open_positions():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM paper_positions WHERE status = 'open'").fetchall()
        return [dict(r) for r in rows]


def init_momentum_table():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_momentum (
                mint              TEXT PRIMARY KEY,
                trade_count_60s   INTEGER,
                traders_60s       INTEGER,
                trade_count_120s  INTEGER,
                traders_120s      INTEGER,
                computed_at       INTEGER NOT NULL
            )
            """
        )


def get_token_momentum(mint: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM token_momentum WHERE mint = ?", (mint,)).fetchone()
        return dict(row) if row else None


def upsert_token_momentum(m: dict):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO token_momentum
            (mint, trade_count_60s, traders_60s, trade_count_120s, traders_120s, computed_at)
            VALUES (:mint, :trade_count_60s, :traders_60s, :trade_count_120s, :traders_120s, :computed_at)
            ON CONFLICT(mint) DO UPDATE SET
                trade_count_60s=excluded.trade_count_60s,
                traders_60s=excluded.traders_60s,
                trade_count_120s=excluded.trade_count_120s,
                traders_120s=excluded.traders_120s,
                computed_at=excluded.computed_at
            """,
            m,
        )


def close_paper_position(position_id: int, exit_reason: str, exit_price_sol: float, exit_ts: int,
                           entry_sol: float, entry_tokens: float):
    exit_sol = exit_price_sol * entry_tokens
    pnl_sol = exit_sol - entry_sol
    pnl_pct = (pnl_sol / entry_sol * 100) if entry_sol else 0
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE paper_positions
            SET status = 'closed', exit_reason = ?, exit_price_sol = ?,
                exit_ts = ?, pnl_sol = ?, pnl_pct = ?
            WHERE id = ?
            """,
            (exit_reason, exit_price_sol, exit_ts, pnl_sol, pnl_pct, position_id),
        )


def trade_exists(signature: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("SELECT 1 FROM trades WHERE signature = ?", (signature,))
        return cur.fetchone() is not None


def insert_trade(t: dict):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO trades
            (signature, wallet, timestamp, action, token_mint,
             token_amount, sol_amount, source, raw)
            VALUES (:signature, :wallet, :timestamp, :action, :token_mint,
                    :token_amount, :sol_amount, :source, :raw)
            """,
            t,
        )
