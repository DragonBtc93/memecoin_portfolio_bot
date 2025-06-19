import psycopg2
from psycopg2 import extras as psycopg2_extras
from psycopg2.pool import SimpleConnectionPool
import logging

from solana_trade_bot.core.config import (
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    POSTGRES_DBNAME,
    POSTGRES_POOL_MIN_CONN,
    POSTGRES_POOL_MAX_CONN
)

logger = logging.getLogger(__name__)

# Global PostgreSQL connection pool
pg_connection_pool = None

def init_connection_pool():
    """Initializes the PostgreSQL connection pool."""
    global pg_connection_pool
    if pg_connection_pool is None:
        try:
            logger.info(f"Initializing PostgreSQL connection pool for db '{POSTGRES_DBNAME}' at {POSTGRES_HOST}:{POSTGRES_PORT} (min: {POSTGRES_POOL_MIN_CONN}, max: {POSTGRES_POOL_MAX_CONN})")
            pg_connection_pool = SimpleConnectionPool(
                POSTGRES_POOL_MIN_CONN,
                POSTGRES_POOL_MAX_CONN,
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                dbname=POSTGRES_DBNAME
            )
            logger.info("PostgreSQL connection pool initialized successfully.")
        except psycopg2.Error as e:
            logger.error(f"Error initializing PostgreSQL connection pool: {e}", exc_info=True)
            pg_connection_pool = None # Ensure it's None if init fails
            raise # Re-raise to signal catastrophic failure to the application
    # else:
        # logger.debug("PostgreSQL connection pool already initialized.")

def close_connection_pool():
    """Closes all connections in the PostgreSQL connection pool."""
    global pg_connection_pool
    if pg_connection_pool:
        logger.info("Closing PostgreSQL connection pool.")
        try:
            pg_connection_pool.closeall()
            pg_connection_pool = None
            logger.info("PostgreSQL connection pool closed.")
        except Exception as e: # Broad exception as closeall() might have its own issues
            logger.error(f"Error closing PostgreSQL connection pool: {e}", exc_info=True)
            pg_connection_pool = None # Attempt to nullify even on error


def get_pg_connection_from_pool(): # Renamed to avoid confusion with old direct get_pg_connection
    """Gets a connection from the pool. Must be returned using put_pg_connection."""
    global pg_connection_pool
    if pg_connection_pool is None:
        logger.error("Connection pool not initialized. Call init_connection_pool() at startup.")
        raise Exception("PostgreSQL connection pool not initialized.")

    logger.debug("Attempting to get connection from pool...")
    try:
        conn = pg_connection_pool.getconn()
        logger.debug(f"Got connection {id(conn)} from pool.")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error getting connection from pool: {e}", exc_info=True)
        raise

def put_pg_connection_to_pool(conn):
    """Returns a connection to the pool."""
    global pg_connection_pool
    if pg_connection_pool and conn:
        logger.debug(f"Returning connection {id(conn)} to pool.")
        try:
            pg_connection_pool.putconn(conn)
        except psycopg2.Error as e: # Handle cases like returning a closed connection
            logger.error(f"Error returning connection to pool: {e}", exc_info=True)
            # If returning fails, may need to discard connection and let pool manage itself
        except Exception as e: # Other unexpected errors
            logger.error(f"Unexpected error returning connection to pool: {e}", exc_info=True)


def init_db_pg():
    conn = None
    try:
        conn = get_pg_connection_from_pool()
        with conn.cursor() as cur:
            # Schema creation (same as before)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    chat_id BIGINT PRIMARY KEY,
                    linked_solana_address TEXT UNIQUE,
                    buy_amount_sol REAL,
                    is_trading_enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            logger.info("Users table schema verified/created.")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id SERIAL PRIMARY KEY,
                    chat_id BIGINT REFERENCES users(chat_id) ON DELETE CASCADE,
                    token_mint_address TEXT NOT NULL,
                    dev_wallet_source TEXT,
                    sol_price_at_buy REAL,
                    tokens_bought REAL,
                    sol_spent REAL,
                    status TEXT NOT NULL,
                    notified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    buy_confirmed_at TIMESTAMP WITH TIME ZONE,
                    last_tp_notified_level INTEGER,
                    sell_initiated_at TIMESTAMP WITH TIME ZONE,
                    sell_confirmed_at TIMESTAMP WITH TIME ZONE
                );
            """)
            logger.info("Trades table schema verified/created.")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS monitored_mints (
                    mint_address TEXT PRIMARY KEY,
                    dev_wallet_source TEXT NOT NULL,
                    initial_liquidity_info TEXT,
                    transaction_signature TEXT,
                    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    processed_by_bot_at TIMESTAMP WITH TIME ZONE
                );
            """)
            logger.info("Monitored_mints table schema verified/created.")
            cur.execute("""
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                   NEW.updated_at = NOW();
                   RETURN NEW;
                END;
                $$ language 'plpgsql';
            """)
            cur.execute("DROP TRIGGER IF EXISTS users_updated_at_trigger ON users;")
            cur.execute("""
                CREATE TRIGGER users_updated_at_trigger
                BEFORE UPDATE ON users
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();
            """)
            logger.info("Users updated_at trigger function and trigger verified/created.")

            # Indexes for 'trades' table
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_chat_id ON trades (chat_id);")
            logger.info("Index idx_trades_chat_id on trades.chat_id verified/created.")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades (status);")
            logger.info("Index idx_trades_status on trades.status verified/created.")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_token_mint_address ON trades (token_mint_address);")
            logger.info("Index idx_trades_token_mint_address on trades.token_mint_address verified/created.")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_chat_id_status ON trades (chat_id, status);")
            logger.info("Index idx_trades_chat_id_status on trades (chat_id, status) verified/created.")

            # Indexes for 'monitored_mints' table
            cur.execute("CREATE INDEX IF NOT EXISTS idx_monitored_mints_dev_wallet_source ON monitored_mints (dev_wallet_source);")
            logger.info("Index idx_monitored_mints_dev_wallet_source on monitored_mints.dev_wallet_source verified/created.")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_monitored_mints_detected_at ON monitored_mints (detected_at DESC);")
            logger.info("Index idx_monitored_mints_detected_at on monitored_mints (detected_at DESC) verified/created.")

            conn.commit()
            logger.info("PostgreSQL database schema initialization complete (including indexes).")
    except (Exception, psycopg2.Error) as e: # Broader catch for init
        logger.error(f"Error during PostgreSQL database initialization: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if conn: put_pg_connection_to_pool(conn)


# --- User Table CRUD Operations (PostgreSQL) ---
def get_user_pg(chat_id: int):
    conn = None
    try:
        conn = get_pg_connection_from_pool()
        with conn.cursor(cursor_factory=psycopg2_extras.DictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
            user_row = cur.fetchone()
            return user_row
    except (Exception, psycopg2.Error) as e:
        logger.error(f"Error fetching user {chat_id} from PostgreSQL: {e}", exc_info=True)
        return None
    finally:
        if conn: put_pg_connection_to_pool(conn)

def upsert_user_settings_pg(
    chat_id: int,
    solana_address: str | None = None,
    buy_amount_sol: float | None = None,
    is_trading_enabled: bool | None = None
) -> None:
    conn = None
    try:
        conn = get_pg_connection_from_pool()
        with conn.cursor() as cur:
            # ... (rest of upsert logic, same as before but with commit at end of 'with cur') ...
            insert_sol_address = solana_address if solana_address and solana_address.strip() else None
            insert_buy_amount = buy_amount_sol
            insert_trading_enabled = is_trading_enabled if is_trading_enabled is not None else True

            update_parts = []
            update_values = []
            if solana_address is not None:
                update_parts.append("linked_solana_address = %s")
                update_values.append(insert_sol_address)
            if buy_amount_sol is not None:
                update_parts.append("buy_amount_sol = %s")
                update_values.append(buy_amount_sol)
            if is_trading_enabled is not None:
                update_parts.append("is_trading_enabled = %s")
                update_values.append(is_trading_enabled)

            if not update_parts:
                sql_query = """
                    INSERT INTO users (chat_id, linked_solana_address, buy_amount_sol, is_trading_enabled)
                    VALUES (%s, %s, %s, %s) ON CONFLICT (chat_id) DO NOTHING;"""
                cur.execute(sql_query, (chat_id, insert_sol_address, insert_buy_amount, insert_trading_enabled))
            else:
                set_clause = ", ".join(update_parts)
                final_insert_sol_address = solana_address if solana_address is not None else None
                final_insert_buy_amount = buy_amount_sol if buy_amount_sol is not None else None
                final_insert_trading_enabled = is_trading_enabled if is_trading_enabled is not None else True

                insert_params = (chat_id, final_insert_sol_address, final_insert_buy_amount, final_insert_trading_enabled)
                sql_query = f"""
                    INSERT INTO users (chat_id, linked_solana_address, buy_amount_sol, is_trading_enabled)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (chat_id) DO UPDATE SET {set_clause};"""
                cur.execute(sql_query, insert_params + tuple(update_values))
            conn.commit()
            # Logging moved after commit
            if not update_parts:
                logger.info(f"Upsert (ensure exists) for user {chat_id}. Trading enabled by default if new: {insert_trading_enabled}")
            else:
                updated_fields_log = [u.split(" = ")[0] for u in update_parts]
                logger.info(f"Upserted user {chat_id}. Updated fields on conflict: {updated_fields_log}")

    except (Exception, psycopg2.Error) as e:
        logger.error(f"Database error in upsert_user_settings_pg for chat_id {chat_id}: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if conn: put_pg_connection_to_pool(conn)

def get_user_trading_status_pg(chat_id: int) -> bool:
    user = get_user_pg(chat_id) # This will get/put connection from pool
    return bool(user['is_trading_enabled']) if user and user['is_trading_enabled'] is not None else False

def get_user_linked_wallet_pg(chat_id: int) -> str | None:
    user = get_user_pg(chat_id) # Uses pooled connection
    return user['linked_solana_address'] if user and user['linked_solana_address'] else None

def get_user_buy_amount_pg(chat_id: int) -> float | None:
    user = get_user_pg(chat_id) # Uses pooled connection
    return float(user['buy_amount_sol']) if user and user['buy_amount_sol'] is not None else None

def get_all_user_chat_ids_pg() -> list[int]:
    conn = None
    try:
        conn = get_pg_connection_from_pool()
        with conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM users")
            rows = cur.fetchall()
            return [row[0] for row in rows]
    except (Exception, psycopg2.Error) as e:
        logger.error(f"Database error in get_all_user_chat_ids_pg: {e}", exc_info=True)
        return []
    finally:
        if conn: put_pg_connection_to_pool(conn)

# --- Trades Table CRUD Operations (PostgreSQL) --- (Refactored for pooling)
def add_trade_notification_pg(chat_id: int, token_mint_address: str, dev_wallet_source: str, status: str = 'notified_buy') -> int | None:
    conn = None
    trade_id = None
    try:
        conn = get_pg_connection_from_pool()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO trades (chat_id, token_mint_address, dev_wallet_source, status, notified_at) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP) RETURNING trade_id;",
                (chat_id, token_mint_address, dev_wallet_source, status)
            )
            trade_id_row = cur.fetchone()
            if trade_id_row: trade_id = trade_id_row[0]
        conn.commit()
        if trade_id: logger.info(f"PostgreSQL: Added trade notification for chat_id {chat_id}, mint {token_mint_address}. Trade ID: {trade_id}")
        return trade_id
    except (Exception, psycopg2.Error) as e:
        logger.error(f"PostgreSQL error in add_trade_notification_pg: {e}", exc_info=True)
        if conn: conn.rollback()
        return None
    finally:
        if conn: put_pg_connection_to_pool(conn)

def update_trade_on_buy_confirmation_pg(trade_id: int, tokens_bought: float, sol_spent: float, sol_price_at_buy: float) -> bool:
    conn = None
    updated_rows = 0
    try:
        conn = get_pg_connection_from_pool()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE trades SET tokens_bought = %s, sol_spent = %s, sol_price_at_buy = %s, status = 'confirmed_buy', buy_confirmed_at = CURRENT_TIMESTAMP WHERE trade_id = %s;",
                (tokens_bought, sol_spent, sol_price_at_buy, trade_id)
            )
            updated_rows = cur.rowcount
        conn.commit()
        if updated_rows > 0: logger.info(f"PostgreSQL: Trade {trade_id} updated to 'confirmed_buy'.")
        return updated_rows > 0
    except (Exception, psycopg2.Error) as e:
        logger.error(f"PostgreSQL error in update_trade_on_buy_confirmation_pg for trade_id {trade_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        return False
    finally:
        if conn: put_pg_connection_to_pool(conn)

def get_user_trades_pg(chat_id: int, only_open: bool = True) -> list:
    conn = None
    try:
        conn = get_pg_connection_from_pool()
        with conn.cursor(cursor_factory=psycopg2_extras.DictCursor) as cur:
            query = "SELECT * FROM trades WHERE chat_id = %s"
            params: list[any] = [chat_id]
            if only_open:
                query += " AND status = 'confirmed_buy'"
            query += " ORDER BY notified_at DESC"
            cur.execute(query, tuple(params))
            trades = cur.fetchall()
            return trades
    except (Exception, psycopg2.Error) as e:
        logger.error(f"PostgreSQL error in get_user_trades_pg for chat_id {chat_id}: {e}", exc_info=True)
        return []
    finally:
        if conn: put_pg_connection_to_pool(conn)

def get_trade_by_id_pg(trade_id: int):
    conn = None
    try:
        conn = get_pg_connection_from_pool()
        with conn.cursor(cursor_factory=psycopg2_extras.DictCursor) as cur:
            cur.execute("SELECT * FROM trades WHERE trade_id = %s", (trade_id,))
            trade_row = cur.fetchone()
            return trade_row
    except (Exception, psycopg2.Error) as e:
        logger.error(f"PostgreSQL error in get_trade_by_id_pg for trade_id {trade_id}: {e}", exc_info=True)
        return None
    finally:
        if conn: put_pg_connection_to_pool(conn)

def update_trade_status_pg(trade_id: int, new_status: str, last_tp_notified_level: int | None = None) -> bool:
    conn = None
    updated_rows = 0
    try:
        conn = get_pg_connection_from_pool()
        with conn.cursor() as cur:
            update_fields = ["status = %s"]
            params = [new_status]
            if last_tp_notified_level is not None:
                update_fields.append("last_tp_notified_level = %s")
                params.append(last_tp_notified_level)
            params.append(trade_id)
            query = f"UPDATE trades SET {', '.join(update_fields)} WHERE trade_id = %s;"
            cur.execute(query, tuple(params))
            updated_rows = cur.rowcount
        conn.commit()
        if updated_rows > 0: logger.info(f"PostgreSQL: Trade {trade_id} status updated to '{new_status}'.")
        return updated_rows > 0
    except (Exception, psycopg2.Error) as e:
        logger.error(f"PostgreSQL error in update_trade_status_pg for trade_id {trade_id}: {e}", exc_info=True)
        if conn: conn.rollback()
        return False
    finally:
        if conn: put_pg_connection_to_pool(conn)

# --- Monitored Mints Table CRUD Operations (PostgreSQL) ---
def add_monitored_mint_pg(mint_address: str, dev_wallet_source: str, transaction_signature: str, initial_liquidity_info: str | None = None) -> bool:
    conn = None
    rowcount = 0
    try:
        conn = get_pg_connection_from_pool()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO monitored_mints (mint_address, dev_wallet_source, transaction_signature, initial_liquidity_info, detected_at) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP) ON CONFLICT (mint_address) DO NOTHING;",
                (mint_address, dev_wallet_source, transaction_signature, initial_liquidity_info)
            )
            rowcount = cur.rowcount
        conn.commit()
        if rowcount > 0:
            logger.info(f"PostgreSQL: Added monitored mint: {mint_address} from dev {dev_wallet_source}")
        else:
            logger.info(f"PostgreSQL: Mint address {mint_address} already exists or ON CONFLICT DO NOTHING.")
        return rowcount > 0
    except (Exception, psycopg2.Error) as e:
        logger.error(f"PostgreSQL error in add_monitored_mint_pg for {mint_address}: {e}", exc_info=True)
        if conn: conn.rollback()
        return False
    finally:
        if conn: put_pg_connection_to_pool(conn)

def get_monitored_mint_pg(mint_address: str):
    conn = None
    try:
        conn = get_pg_connection_from_pool()
        with conn.cursor(cursor_factory=psycopg2_extras.DictCursor) as cur:
            cur.execute("SELECT * FROM monitored_mints WHERE mint_address = %s", (mint_address,))
            mint_row = cur.fetchone()
            return mint_row
    except (Exception, psycopg2.Error) as e:
        logger.error(f"PostgreSQL error in get_monitored_mint_pg for {mint_address}: {e}", exc_info=True)
        return None
    finally:
        if conn: put_pg_connection_to_pool(conn)

def update_mint_processed_time_pg(mint_address: str) -> bool:
    conn = None
    updated_rows = 0
    try:
        conn = get_pg_connection_from_pool()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE monitored_mints SET processed_by_bot_at = CURRENT_TIMESTAMP WHERE mint_address = %s;",
                (mint_address,)
            )
            updated_rows = cur.rowcount
        conn.commit()
        if updated_rows > 0: logger.info(f"PostgreSQL: Updated processed_by_bot_at for mint: {mint_address}")
        return updated_rows > 0
    except (Exception, psycopg2.Error) as e:
        logger.error(f"PostgreSQL error in update_mint_processed_time_pg for {mint_address}: {e}", exc_info=True)
        if conn: conn.rollback()
        return False
    finally:
        if conn: put_pg_connection_to_pool(conn)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Attempting to initialize PostgreSQL connection pool and database schema directly...")
    try:
        init_connection_pool() # Initialize pool first
        init_db_pg() # Then initialize schema using pooled connections
        logger.info("PostgreSQL direct initialization script finished successfully.")

        if POSTGRES_USER != "your_pg_user":
            logger.info("--- Running PostgreSQL CRUD Examples (requires non-default config) ---")
            test_pg_chat_id1 = 1234567
            # User operations
            upsert_user_settings_pg(test_pg_chat_id1, solana_address="WalletPoolTest", buy_amount_sol=0.1, is_trading_enabled=True)
            user_info = get_user_pg(test_pg_chat_id1)
            if user_info: logger.info(f"User info: {dict(user_info)}")

            # Trade operations
            trade_id = add_trade_notification_pg(test_pg_chat_id1, "PoolTestMint1", "DevPoolWallet")
            if trade_id:
                logger.info(f"Added trade ID: {trade_id}")
                update_trade_on_buy_confirmation_pg(trade_id, 100, 0.1, 0.001)
                trade_info = get_trade_by_id_pg(trade_id)
                if trade_info: logger.info(f"Trade info: {dict(trade_info)}")

            # Monitored mint operations
            add_monitored_mint_pg("PoolTestMint1", "DevPoolWallet", "TxPoolSig1")
            mint_info = get_monitored_mint_pg("PoolTestMint1")
            if mint_info: logger.info(f"Monitored mint: {dict(mint_info)}")
            update_mint_processed_time_pg("PoolTestMint1")
            logger.info("--- PostgreSQL CRUD Examples Finished ---")
        else:
            logger.warning("Skipping CRUD examples as default PostgreSQL credentials are used.")

    except Exception as e:
        logger.error(f"Error during direct initialization or example run: {e}", exc_info=True)
    finally:
        close_connection_pool() # Clean up the pool
        logger.info("PostgreSQL connection pool closed after direct script run.")
