import psycopg2
from psycopg2 import extras as psycopg2_extras # For DictCursor
import logging

from solana_trade_bot.core.config import (
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    POSTGRES_DBNAME
)

logger = logging.getLogger(__name__)

def get_pg_connection():
    """Establishes and returns a new connection to the PostgreSQL database."""
    logger.debug(f"Attempting to connect to PostgreSQL: dbname='{POSTGRES_DBNAME}' user='{POSTGRES_USER}' host='{POSTGRES_HOST}' port={POSTGRES_PORT}")
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            dbname=POSTGRES_DBNAME
        )
        logger.info(f"Successfully connected to PostgreSQL database: {POSTGRES_DBNAME}")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error connecting to PostgreSQL database '{POSTGRES_DBNAME}': {e}")
        raise

def init_db_pg():
    """
    Initializes the PostgreSQL database: creates tables if they don't exist
    and sets up necessary triggers.
    """
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
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
            conn.commit()
            logger.info("PostgreSQL database schema initialization complete.")
    except psycopg2.Error as e:
        logger.error(f"Error during PostgreSQL database initialization: {e}")
        if conn: conn.rollback()
    except Exception as e:
        logger.error(f"An unexpected error occurred during PostgreSQL init: {e}")
        if conn: conn.rollback()
    finally:
        if conn: conn.close()

# --- User Table CRUD Operations (PostgreSQL) ---
def get_user_pg(chat_id: int):
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor(cursor_factory=psycopg2_extras.DictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
            user_row = cur.fetchone()
            return user_row
    except psycopg2.Error as e:
        logger.error(f"Error fetching user {chat_id} from PostgreSQL: {e}")
        return None
    finally:
        if conn: conn.close()

def upsert_user_settings_pg(
    chat_id: int,
    solana_address: str | None = None,
    buy_amount_sol: float | None = None,
    is_trading_enabled: bool | None = None
) -> None:
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
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
                logger.info(f"Upsert (ensure exists) for user {chat_id}. Trading enabled by default if new: {insert_trading_enabled}")
            else:
                set_clause = ", ".join(update_parts)
                final_insert_sol_address = solana_address if solana_address is not None else None
                final_insert_buy_amount = buy_amount_sol if buy_amount_sol is not None else None
                final_insert_trading_enabled = is_trading_enabled if is_trading_enabled is not None else True

                params_for_insert_then_update = [
                    chat_id, final_insert_sol_address, final_insert_buy_amount, final_insert_trading_enabled
                ]
                params_for_insert_then_update.extend(update_values)

                sql_query = f"""
                    INSERT INTO users (chat_id, linked_solana_address, buy_amount_sol, is_trading_enabled)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (chat_id) DO UPDATE SET {set_clause};"""

                insert_params = (chat_id,
                                 solana_address if solana_address is not None else None,
                                 buy_amount_sol if buy_amount_sol is not None else None,
                                 is_trading_enabled if is_trading_enabled is not None else True)
                cur.execute(sql_query, insert_params + tuple(update_values))
                updated_fields_log = [u.split(" = ")[0] for u in update_parts]
                logger.info(f"Upserted user {chat_id}. Updated fields on conflict: {updated_fields_log}")
            conn.commit()
    except psycopg2.Error as e:
        logger.error(f"Database error in upsert_user_settings_pg for chat_id {chat_id}: {e}")
        if conn: conn.rollback()
    except Exception as e:
        logger.error(f"Unexpected error in upsert_user_settings_pg for chat_id {chat_id}: {e}", exc_info=True)
        if conn: conn.rollback()
    finally:
        if conn: conn.close()

def get_user_trading_status_pg(chat_id: int) -> bool:
    user = get_user_pg(chat_id)
    return bool(user['is_trading_enabled']) if user and user['is_trading_enabled'] is not None else False

def get_user_linked_wallet_pg(chat_id: int) -> str | None:
    user = get_user_pg(chat_id)
    return user['linked_solana_address'] if user and user['linked_solana_address'] else None

def get_user_buy_amount_pg(chat_id: int) -> float | None:
    user = get_user_pg(chat_id)
    return float(user['buy_amount_sol']) if user and user['buy_amount_sol'] is not None else None

def get_all_user_chat_ids_pg() -> list[int]:
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur: # No DictCursor needed for single column
            cur.execute("SELECT chat_id FROM users")
            rows = cur.fetchall()
            return [row[0] for row in rows]
    except psycopg2.Error as e:
        logger.error(f"Database error in get_all_user_chat_ids_pg: {e}")
        return []
    finally:
        if conn: conn.close()

# --- Trades Table CRUD Operations (PostgreSQL) ---
def add_trade_notification_pg(chat_id: int, token_mint_address: str, dev_wallet_source: str, status: str = 'notified_buy') -> int | None:
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO trades (chat_id, token_mint_address, dev_wallet_source, status, notified_at) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP) RETURNING trade_id;",
                (chat_id, token_mint_address, dev_wallet_source, status)
            )
            trade_id_row = cur.fetchone()
            conn.commit()
            if trade_id_row:
                logger.info(f"PostgreSQL: Added trade notification for chat_id {chat_id}, mint {token_mint_address}. Trade ID: {trade_id_row[0]}")
                return trade_id_row[0]
            return None
    except psycopg2.Error as e:
        logger.error(f"PostgreSQL error in add_trade_notification_pg: {e}")
        if conn: conn.rollback()
        return None
    finally:
        if conn: conn.close()

def update_trade_on_buy_confirmation_pg(trade_id: int, tokens_bought: float, sol_spent: float, sol_price_at_buy: float) -> bool:
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE trades SET tokens_bought = %s, sol_spent = %s, sol_price_at_buy = %s, status = 'confirmed_buy', buy_confirmed_at = CURRENT_TIMESTAMP WHERE trade_id = %s;",
                (tokens_bought, sol_spent, sol_price_at_buy, trade_id)
            )
            updated_rows = cur.rowcount
            conn.commit()
            if updated_rows > 0: logger.info(f"PostgreSQL: Trade {trade_id} updated to 'confirmed_buy'.")
            return updated_rows > 0
    except psycopg2.Error as e:
        logger.error(f"PostgreSQL error in update_trade_on_buy_confirmation_pg for trade_id {trade_id}: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def get_user_trades_pg(chat_id: int, only_open: bool = True) -> list:
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor(cursor_factory=psycopg2_extras.DictCursor) as cur:
            query = "SELECT * FROM trades WHERE chat_id = %s"
            params = [chat_id]
            if only_open:
                query += " AND status = 'confirmed_buy'"
            query += " ORDER BY notified_at DESC"
            cur.execute(query, tuple(params))
            trades = cur.fetchall()
            return trades
    except psycopg2.Error as e:
        logger.error(f"PostgreSQL error in get_user_trades_pg for chat_id {chat_id}: {e}")
        return []
    finally:
        if conn: conn.close()

def get_trade_by_id_pg(trade_id: int):
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor(cursor_factory=psycopg2_extras.DictCursor) as cur:
            cur.execute("SELECT * FROM trades WHERE trade_id = %s", (trade_id,))
            trade_row = cur.fetchone()
            return trade_row
    except psycopg2.Error as e:
        logger.error(f"PostgreSQL error in get_trade_by_id_pg for trade_id {trade_id}: {e}")
        return None
    finally:
        if conn: conn.close()

def update_trade_status_pg(trade_id: int, new_status: str, last_tp_notified_level: int | None = None) -> bool:
    conn = None
    try:
        conn = get_pg_connection()
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
    except psycopg2.Error as e:
        logger.error(f"PostgreSQL error in update_trade_status_pg for trade_id {trade_id}: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

# --- Monitored Mints Table CRUD Operations (PostgreSQL) ---
def add_monitored_mint_pg(mint_address: str, dev_wallet_source: str, transaction_signature: str, initial_liquidity_info: str | None = None) -> bool:
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO monitored_mints (mint_address, dev_wallet_source, transaction_signature, initial_liquidity_info, detected_at) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP) ON CONFLICT (mint_address) DO NOTHING;",
                (mint_address, dev_wallet_source, transaction_signature, initial_liquidity_info)
            )
            conn.commit()
            if cur.rowcount > 0:
                logger.info(f"PostgreSQL: Added monitored mint: {mint_address} from dev {dev_wallet_source}")
            else:
                logger.info(f"PostgreSQL: Mint address {mint_address} already exists or ON CONFLICT DO NOTHING.")
            return cur.rowcount > 0
    except psycopg2.Error as e:
        logger.error(f"PostgreSQL error in add_monitored_mint_pg for {mint_address}: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

def get_monitored_mint_pg(mint_address: str):
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor(cursor_factory=psycopg2_extras.DictCursor) as cur:
            cur.execute("SELECT * FROM monitored_mints WHERE mint_address = %s", (mint_address,))
            mint_row = cur.fetchone()
            return mint_row
    except psycopg2.Error as e:
        logger.error(f"PostgreSQL error in get_monitored_mint_pg for {mint_address}: {e}")
        return None
    finally:
        if conn: conn.close()

def update_mint_processed_time_pg(mint_address: str) -> bool:
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE monitored_mints SET processed_by_bot_at = CURRENT_TIMESTAMP WHERE mint_address = %s;",
                (mint_address,)
            )
            updated_rows = cur.rowcount
            conn.commit()
            if updated_rows > 0: logger.info(f"PostgreSQL: Updated processed_by_bot_at for mint: {mint_address}")
            return updated_rows > 0
    except psycopg2.Error as e:
        logger.error(f"PostgreSQL error in update_mint_processed_time_pg for {mint_address}: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Attempting to initialize PostgreSQL database directly...")
    # init_db_pg() # Call this to ensure schema is created/updated when running file directly

    logger.info("PostgreSQL database schema functions script finished.")

    if POSTGRES_USER != "your_pg_user":
        logger.info("--- Running PostgreSQL User CRUD Examples ---")
        test_pg_chat_id1 = 123456
        upsert_user_settings_pg(test_pg_chat_id1, solana_address="WalletMainPg", buy_amount_sol=0.5, is_trading_enabled=True)
        user1 = get_user_pg(test_pg_chat_id1)
        if user1: logger.info(f"User1: {dict(user1)}")
        upsert_user_settings_pg(test_pg_chat_id1, buy_amount_sol=0.6, is_trading_enabled=False)
        user1_updated = get_user_pg(test_pg_chat_id1)
        if user1_updated: logger.info(f"User1 updated: {dict(user1_updated)}")
        logger.info(f"User1 Trading Status: {get_user_trading_status_pg(test_pg_chat_id1)}")
        logger.info("--- PostgreSQL User CRUD Examples Finished ---")

        logger.info("--- Running PostgreSQL Trades & Mints CRUD Examples ---")
        if get_user_pg(test_pg_chat_id1):
            trade_id = add_trade_notification_pg(test_pg_chat_id1, "TestTokenMintPG1", "DevWalletPG1")
            if trade_id:
                logger.info(f"Added trade with ID: {trade_id}")
                trade_details = get_trade_by_id_pg(trade_id)
                if trade_details: logger.info(f"Trade details: {dict(trade_details)}")
                update_trade_on_buy_confirmation_pg(trade_id, 1000, 0.5, 0.0005)
                updated_trade_details = get_trade_by_id_pg(trade_id)
                if updated_trade_details: logger.info(f"Updated trade details: {dict(updated_trade_details)}")

            mint_added = add_monitored_mint_pg("TestTokenMintPG1", "DevWalletPG1", "TxSigPG1")
            if mint_added: logger.info(f"Added monitored mint: TestTokenMintPG1")
            else: logger.info(f"Monitored mint TestTokenMintPG1 likely already existed.")
            update_mint_processed_time_pg("TestTokenMintPG1")
            updated_mint_details = get_monitored_mint_pg("TestTokenMintPG1")
            if updated_mint_details: logger.info(f"Updated monitored mint: {dict(updated_mint_details)}")
        else:
            logger.warning(f"User {test_pg_chat_id1} not found, skipping Trades & Mints examples.")
        logger.info("--- PostgreSQL Trades & Mints CRUD Examples Finished ---")
    else:
        logger.warning("Skipping CRUD examples in __main__ because default PostgreSQL credentials are used.")
        logger.warning("Please update POSTGRES_USER, POSTGRES_PASSWORD, etc., in core/config.py to test.")
