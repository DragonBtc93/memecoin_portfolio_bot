import psycopg2
from psycopg2 import sql # For dynamic SQL query building, if needed, though not for schema
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
        # Depending on how this is called, we might want to exit or let the caller handle.
        # For init_db_pg, if connection fails, it should not proceed.
        raise # Re-raise the exception to be handled by the caller or to stop execution

def init_db_pg():
    """
    Initializes the PostgreSQL database: creates tables if they don't exist
    and sets up necessary triggers.
    """
    conn = None  # Initialize conn to None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
            # Users table
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

            # Trades table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id SERIAL PRIMARY KEY,
                    chat_id BIGINT REFERENCES users(chat_id) ON DELETE CASCADE, -- Added ON DELETE CASCADE
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

            # Monitored Mints table
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

            # Function and Trigger for users.updated_at
            cur.execute("""
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                   NEW.updated_at = NOW(); -- Use NOW() for current transaction timestamp
                   RETURN NEW;
                END;
                $$ language 'plpgsql';
            """)

            # Drop trigger if it exists, then create it - makes script idempotent
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
        # If conn is None, get_pg_connection() failed. If conn is not None, an error occurred after connection.
        if conn:
            conn.rollback() # Rollback any partial changes if error occurred mid-transaction
    except Exception as e:
        logger.error(f"An unexpected error occurred during PostgreSQL init: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# --- Trades Table CRUD Operations (PostgreSQL) ---
# TODO: Implement PostgreSQL-specific versions of these functions.
# For now, core/db.py dispatcher will use SQLite versions as fallback.

# def add_trade_notification_pg(chat_id: int, token_mint_address: str, dev_wallet_source: str, status: str = 'notified_buy') -> int | None:
#     # ... PG implementation ...
#     pass

# def update_trade_on_buy_confirmation_pg(trade_id: int, tokens_bought: float, sol_spent: float, sol_price_at_buy: float) -> bool:
#     # ... PG implementation ...
#     pass

# def get_user_trades_pg(chat_id: int, only_open: bool = True) -> list: # list[psycopg2.extras.DictRow]
#     # ... PG implementation ...
#     pass

# def get_trade_by_id_pg(trade_id: int): # -> psycopg2.extras.DictRow | None
#     # ... PG implementation ...
#     pass

# def update_trade_status_pg(trade_id: int, new_status: str, last_tp_notified_level: int | None = None) -> bool:
#     # ... PG implementation ...
#     pass

# --- Monitored Mints Table CRUD Operations (PostgreSQL) ---
# TODO: Implement PostgreSQL-specific versions of these functions.

# def add_monitored_mint_pg(mint_address: str, dev_wallet_source: str, transaction_signature: str, initial_liquidity_info: str | None = None) -> bool:
#     # ... PG implementation ...
#     pass

# def get_monitored_mint_pg(mint_address: str): # -> psycopg2.extras.DictRow | None
#     # ... PG implementation ...
#     pass

# def update_mint_processed_time_pg(mint_address: str) -> bool:
#     # ... PG implementation ...
#     pass
            logger.debug("PostgreSQL connection closed after init.")


if __name__ == '__main__':
    # This block is for direct testing of this module.
    # It assumes PostgreSQL is running and configured in core/config.py.
    # Basic logging setup for direct script run
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Attempting to initialize PostgreSQL database directly...")

    # Example: Test connection first (optional)
    # test_conn = None
    # try:
    #     test_conn = get_pg_connection()
    #     if test_conn:
    #         logger.info("Direct connection test successful.")
    #         init_db_pg() # Initialize schema
    # except Exception as e:
    #     logger.error(f"Direct test connection or init failed: {e}")
    # finally:
    #     if test_conn:
    #         test_conn.close()

    # User needs to set them up for their environment.
    logger.info("PostgreSQL database initialization script finished.")

    # Example Usage for User CRUD operations (requires DB to be running and configured)
    # This section will only run if `python core/pg_db.py` is executed directly
    # and if the PostgreSQL connection details in config.py are valid.
    if POSTGRES_USER != "your_pg_user": # Basic check if config might be updated
        logger.info("--- Running PostgreSQL User CRUD Examples ---")
        test_pg_chat_id1 = 123456
        test_pg_chat_id2 = 789012

        # Initial insert for user 1
        upsert_user_settings_pg(test_pg_chat_id1, solana_address="WalletAbcPg", buy_amount_sol=0.5, is_trading_enabled=True)
        user1 = get_user_pg(test_pg_chat_id1)
        if user1:
            logger.info(f"User1 after initial insert: {dict(user1)}")

        # Update user 1
        upsert_user_settings_pg(test_pg_chat_id1, buy_amount_sol=0.6, is_trading_enabled=False)
        user1_updated = get_user_pg(test_pg_chat_id1)
        if user1_updated:
            logger.info(f"User1 after update: {dict(user1_updated)}")

        logger.info(f"User1 Trading Status: {get_user_trading_status_pg(test_pg_chat_id1)}")
        logger.info(f"User1 Wallet: {get_user_linked_wallet_pg(test_pg_chat_id1)}")
        logger.info(f"User1 Buy Amount: {get_user_buy_amount_pg(test_pg_chat_id1)}")

        # Insert user 2
        upsert_user_settings_pg(test_pg_chat_id2, solana_address="WalletXyzPg", is_trading_enabled=False)
        user2 = get_user_pg(test_pg_chat_id2)
        if user2:
            logger.info(f"User2 after initial insert: {dict(user2)}")
            logger.info(f"User2 Trading Status: {get_user_trading_status_pg(test_pg_chat_id2)}")


        all_ids = get_all_user_chat_ids_pg()
        logger.info(f"All user chat IDs: {all_ids}")

        logger.info("--- PostgreSQL User CRUD Examples Finished ---")
    else:
        logger.warning("Skipping User CRUD examples in __main__ because default PostgreSQL credentials are used.")
        logger.warning("Please update POSTGRES_USER, POSTGRES_PASSWORD, etc., in core/config.py to test.")

# --- User Table CRUD Operations (PostgreSQL) ---

def get_user_pg(chat_id: int): # Return type can be psycopg2.extras.DictRow or None
    """Fetches a user by chat_id from PostgreSQL."""
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur: # Use DictCursor for named column access
            cur.execute("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
            user_row = cur.fetchone()
            return user_row
    except psycopg2.Error as e:
        logger.error(f"Error fetching user {chat_id} from PostgreSQL: {e}")
        return None
    finally:
        if conn:
            conn.close()

def upsert_user_settings_pg(
    chat_id: int,
    solana_address: str | None = None,
    buy_amount_sol: float | None = None,
    is_trading_enabled: bool | None = None
) -> None:
    """
    Inserts a new user or updates existing user's settings in PostgreSQL.
    Fields are updated only if a new value is provided.
    For new users, is_trading_enabled defaults to TRUE in the schema if not specified.
    The updated_at field is handled by a database trigger.
    """
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
            # Prepare fields for INSERT. Use schema defaults if values are None.
            # For is_trading_enabled, if None is passed, schema default (TRUE) will be used.
            # If False is passed, False will be used.
            insert_sol_address = solana_address if solana_address and solana_address.strip() else None
            insert_buy_amount = buy_amount_sol
            insert_trading_enabled = is_trading_enabled if is_trading_enabled is not None else True

            # Prepare fields for UPDATE on conflict.
            # We only want to update fields that were explicitly passed.
            update_parts = []
            update_values = []

            if solana_address is not None:
                update_parts.append("linked_solana_address = %s")
                update_values.append(insert_sol_address) # Use the processed version
            if buy_amount_sol is not None:
                update_parts.append("buy_amount_sol = %s")
                update_values.append(buy_amount_sol)
            if is_trading_enabled is not None:
                update_parts.append("is_trading_enabled = %s")
                update_values.append(is_trading_enabled)

            if not update_parts: # Only chat_id provided, ensure user exists
                # If user exists, DO NOTHING. If not, INSERT with defaults.
                sql_query = """
                    INSERT INTO users (chat_id, linked_solana_address, buy_amount_sol, is_trading_enabled)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (chat_id) DO NOTHING;
                """
                cur.execute(sql_query, (chat_id, insert_sol_address, insert_buy_amount, insert_trading_enabled))
                logger.info(f"Upsert (ensure exists) for user {chat_id}. Trading enabled by default if new: {insert_trading_enabled}")
            else:
                # If there are fields to update, also update 'updated_at' via trigger.
                # The trigger handles updated_at, so no need to add it here for PG.
                # update_parts.append("updated_at = CURRENT_TIMESTAMP") # Not needed due to trigger

                set_clause = ", ".join(update_parts)
                sql_query = f"""
                    INSERT INTO users (chat_id, linked_solana_address, buy_amount_sol, is_trading_enabled)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (chat_id) DO UPDATE SET {set_clause};
                """
                # Parameters for INSERT part (defaults for those not provided for update)
                # Need to fetch current values if we want to preserve them on INSERT if not provided for update.
                # This simplified version just uses the passed values or None for INSERT part.
                # A true upsert that preserves existing unspecified fields on INSERT is more complex
                # or relies on COALESCE(EXCLUDED.field, users.field) which is more verbose here.
                # Let's use a simpler INSERT with potentially NULLs for unspecified fields,
                # and the UPDATE will only touch specified fields.
                # The schema defaults will apply for INSERT if values are NULL here.

                # For INSERT: use passed value or NULL if not specified (schema default will apply for is_trading_enabled)
                final_insert_sol_address = solana_address if solana_address is not None else None
                final_insert_buy_amount = buy_amount_sol if buy_amount_sol is not None else None
                final_insert_trading_enabled = is_trading_enabled if is_trading_enabled is not None else True # Default for insert path

                params_for_insert_then_update = [
                    chat_id, final_insert_sol_address, final_insert_buy_amount, final_insert_trading_enabled
                ]
                params_for_insert_then_update.extend(update_values) # Add values for the SET clause

                cur.execute(sql_query, tuple(params_for_insert_then_update))
                updated_fields_log = [u.split(" = ")[0] for u in update_parts]
                logger.info(f"Upserted user {chat_id}. Updated fields on conflict: {updated_fields_log}")

            conn.commit()
    except psycopg2.Error as e:
        logger.error(f"Database error in upsert_user_settings_pg for chat_id {chat_id}: {e}")
        if conn:
            conn.rollback()
    except Exception as e:
        logger.error(f"Unexpected error in upsert_user_settings_pg for chat_id {chat_id}: {e}", exc_info=True)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def get_user_trading_status_pg(chat_id: int) -> bool:
    """Fetches the is_trading_enabled status for a user from PostgreSQL. Defaults to False."""
    user = get_user_pg(chat_id)
    if user and user['is_trading_enabled'] is not None:
        return bool(user['is_trading_enabled'])
    return False

def get_user_linked_wallet_pg(chat_id: int) -> str | None:
    """Fetches the linked Solana address for a user from PostgreSQL."""
    user = get_user_pg(chat_id)
    if user and user['linked_solana_address']:
        return user['linked_solana_address']
    return None

def get_user_buy_amount_pg(chat_id: int) -> float | None:
    """Fetches the buy amount for a user from PostgreSQL."""
    user = get_user_pg(chat_id)
    if user and user['buy_amount_sol'] is not None:
        return float(user['buy_amount_sol'])
    return None

def get_all_user_chat_ids_pg() -> list[int]:
    """Fetches all unique chat_ids from the users table in PostgreSQL."""
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM users")
            rows = cur.fetchall()
            # cur.fetchall() for psycopg2 default cursor returns list of tuples
            return [row[0] for row in rows]
    except psycopg2.Error as e:
        logger.error(f"Database error in get_all_user_chat_ids_pg: {e}")
        return []
    finally:
        if conn:
            conn.close()
