import sqlite3
from solana_trade_bot.core.config import DATABASE_FILE # Assuming sqlite_db still uses this for default path
import logging # It's good practice to log errors

logger = logging.getLogger(__name__)

def get_db_connection_sqlite() -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    # If DATABASE_FILE is ":memory:", it will be an in-memory DB.
    # Otherwise, it's a file-based DB.
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn

def init_db_sqlite() -> None:
    """Initializes the SQLite database and creates tables if they don't exist."""
    conn = get_db_connection_sqlite()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            linked_solana_address TEXT UNIQUE,
            buy_amount_sol REAL,
            is_trading_enabled BOOLEAN DEFAULT True,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("PRAGMA table_info(users)")
    columns = [column['name'] for column in cursor.fetchall()]
    if 'is_trading_enabled' not in columns:
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN is_trading_enabled BOOLEAN DEFAULT True")
            conn.commit()
            logger.info("SQLite schema migration: Added 'is_trading_enabled' column to 'users' table.")
        except sqlite3.OperationalError as e:
            logger.warning(f"SQLite: Could not add 'is_trading_enabled' column, might already exist or other DB issue: {e}")

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS update_users_updated_at_sqlite
        AFTER UPDATE ON users
        FOR EACH ROW
        BEGIN
            UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE chat_id = OLD.chat_id;
        END;
    """)

    # Trades table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            token_mint_address TEXT NOT NULL,
            dev_wallet_source TEXT,
            sol_price_at_buy REAL,
            tokens_bought REAL,
            sol_spent REAL,
            status TEXT NOT NULL,
            notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            buy_confirmed_at TIMESTAMP,
            last_tp_notified_level INTEGER,
            sell_initiated_at TIMESTAMP,
            sell_confirmed_at TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES users (chat_id) ON DELETE CASCADE
        )
    """)

    # Monitored Mints table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitored_mints (
            mint_address TEXT PRIMARY KEY,
            dev_wallet_source TEXT NOT NULL,
            initial_liquidity_info TEXT,
            transaction_signature TEXT,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_by_bot_at TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    logger.info("SQLite database schema initialized/verified.")

def get_user_sqlite(chat_id: int) -> sqlite3.Row | None:
    conn = get_db_connection_sqlite()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
    user_row = cursor.fetchone()
    conn.close()
    return user_row

def upsert_user_settings_sqlite(
    chat_id: int,
    solana_address: str | None = None,
    buy_amount_sol: float | None = None,
    is_trading_enabled: bool | None = None
) -> None:
    conn = get_db_connection_sqlite()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id FROM users WHERE chat_id = ?", (chat_id,))
    user_exists = cursor.fetchone()

    if user_exists:
        updates = []
        params = []
        if solana_address is not None:
            updates.append("linked_solana_address = ?")
            params.append(solana_address if solana_address.strip() else None)
        if buy_amount_sol is not None:
            updates.append("buy_amount_sol = ?")
            params.append(buy_amount_sol)
        if is_trading_enabled is not None:
            updates.append("is_trading_enabled = ?")
            params.append(is_trading_enabled)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            query = f"UPDATE users SET {', '.join(updates)} WHERE chat_id = ?"
            params.append(chat_id)
            cursor.execute(query, tuple(params))
            updated_fields_log = [u.split(" = ")[0] for u in updates if u != "updated_at = CURRENT_TIMESTAMP"]
            logger.info(f"SQLite: Updated user {chat_id}. Fields: {updated_fields_log}")
    else:
        db_sol_address = solana_address if solana_address and solana_address.strip() else None
        db_is_trading_enabled = True if is_trading_enabled is None else is_trading_enabled
        cursor.execute(
            "INSERT INTO users (chat_id, linked_solana_address, buy_amount_sol, is_trading_enabled) VALUES (?, ?, ?, ?)",
            (chat_id, db_sol_address, buy_amount_sol, db_is_trading_enabled)
        )
        logger.info(f"SQLite: Inserted new user {chat_id} with trading_enabled={db_is_trading_enabled}")

    conn.commit()
    conn.close()

def get_user_linked_wallet_sqlite(chat_id: int) -> str | None:
    user = get_user_sqlite(chat_id)
    return user['linked_solana_address'] if user and user['linked_solana_address'] else None

def get_user_buy_amount_sqlite(chat_id: int) -> float | None:
    user = get_user_sqlite(chat_id)
    return float(user['buy_amount_sol']) if user and user['buy_amount_sol'] is not None else None

def get_user_trading_status_sqlite(chat_id: int) -> bool:
    user = get_user_sqlite(chat_id)
    return bool(user['is_trading_enabled']) if user and user['is_trading_enabled'] is not None else False

def get_all_user_chat_ids_sqlite() -> list[int]:
    conn = get_db_connection_sqlite()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT chat_id FROM users")
        rows = cursor.fetchall()
        return [row['chat_id'] for row in rows]
    except sqlite3.Error as e:
        logger.error(f"SQLite Database error in get_all_user_chat_ids_sqlite: {e}")
        return []
    finally:
        conn.close()

# --- Trades Table CRUD Operations (SQLite) ---
def add_trade_notification_sqlite(chat_id: int, token_mint_address: str, dev_wallet_source: str, status: str = 'notified_buy') -> int | None:
    conn = get_db_connection_sqlite()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO trades (chat_id, token_mint_address, dev_wallet_source, status, notified_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (chat_id, token_mint_address, dev_wallet_source, status)
        )
        trade_id = cursor.lastrowid
        conn.commit()
        logger.info(f"SQLite: Added trade notification for chat_id {chat_id}, mint {token_mint_address}. Trade ID: {trade_id}")
        return trade_id
    except sqlite3.Error as e:
        logger.error(f"SQLite Database error in add_trade_notification_sqlite: {e}")
        return None
    finally:
        conn.close()

def update_trade_on_buy_confirmation_sqlite(trade_id: int, tokens_bought: float, sol_spent: float, sol_price_at_buy: float) -> bool:
    conn = get_db_connection_sqlite()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE trades SET tokens_bought = ?, sol_spent = ?, sol_price_at_buy = ?, status = 'confirmed_buy', buy_confirmed_at = CURRENT_TIMESTAMP WHERE trade_id = ?",
            (tokens_bought, sol_spent, sol_price_at_buy, trade_id)
        )
        updated_rows = cursor.rowcount
        conn.commit()
        return updated_rows > 0
    except sqlite3.Error as e:
        logger.error(f"SQLite Database error in update_trade_on_buy_confirmation_sqlite for trade_id {trade_id}: {e}")
        return False
    finally:
        conn.close()

def get_user_trades_sqlite(chat_id: int, only_open: bool = True) -> list[sqlite3.Row]:
    conn = get_db_connection_sqlite()
    cursor = conn.cursor()
    query = "SELECT * FROM trades WHERE chat_id = ?"
    params: list[any] = [chat_id]
    if only_open:
        query += " AND status = 'confirmed_buy'"
    query += " ORDER BY notified_at DESC"
    cursor.execute(query, params)
    trades = cursor.fetchall()
    conn.close()
    return trades

def get_trade_by_id_sqlite(trade_id: int) -> sqlite3.Row | None:
    conn = get_db_connection_sqlite()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,))
    trade_row = cursor.fetchone()
    conn.close()
    return trade_row

def update_trade_status_sqlite(trade_id: int, new_status: str, last_tp_notified_level: int | None = None) -> bool:
    conn = get_db_connection_sqlite()
    cursor = conn.cursor()
    updates = ["status = ?"]
    params = [new_status]
    if last_tp_notified_level is not None:
        updates.append("last_tp_notified_level = ?")
        params.append(last_tp_notified_level)
    params.append(trade_id)
    try:
        query = f"UPDATE trades SET {', '.join(updates)} WHERE trade_id = ?"
        cursor.execute(query, tuple(params))
        updated_rows = cursor.rowcount
        conn.commit()
        return updated_rows > 0
    except sqlite3.Error as e:
        logger.error(f"SQLite Database error in update_trade_status_sqlite for trade_id {trade_id}: {e}")
        return False
    finally:
        conn.close()

# --- Monitored Mints Table CRUD Operations (SQLite) ---
def add_monitored_mint_sqlite(mint_address: str, dev_wallet_source: str, transaction_signature: str, initial_liquidity_info: str | None = None) -> bool:
    conn = get_db_connection_sqlite()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO monitored_mints (mint_address, dev_wallet_source, transaction_signature, initial_liquidity_info, detected_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (mint_address, dev_wallet_source, transaction_signature, initial_liquidity_info)
        )
        conn.commit()
        logger.info(f"SQLite: Added monitored mint: {mint_address} from dev {dev_wallet_source}")
        return True
    except sqlite3.IntegrityError:
        logger.info(f"SQLite: Mint address {mint_address} already exists in monitored_mints.")
        return False
    except sqlite3.Error as e:
        logger.error(f"SQLite Database error in add_monitored_mint_sqlite for {mint_address}: {e}")
        return False
    finally:
        conn.close()

def get_monitored_mint_sqlite(mint_address: str) -> sqlite3.Row | None:
    conn = get_db_connection_sqlite()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM monitored_mints WHERE mint_address = ?", (mint_address,))
    mint_row = cursor.fetchone()
    conn.close()
    return mint_row

def update_mint_processed_time_sqlite(mint_address: str) -> bool:
    conn = get_db_connection_sqlite()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE monitored_mints SET processed_by_bot_at = CURRENT_TIMESTAMP WHERE mint_address = ?",
            (mint_address,)
        )
        updated_rows = cursor.rowcount
        conn.commit()
        return updated_rows > 0
    except sqlite3.Error as e:
        logger.error(f"SQLite Database error in update_mint_processed_time_sqlite for {mint_address}: {e}")
        return False
    finally:
        conn.close()

if __name__ == '__main__':
    logger.info(f"Initializing SQLite database '{DATABASE_FILE}' for direct testing...")
    init_db_sqlite()
    logger.info("SQLite database initialization process complete.")

    # Example minimal test for SQLite user functions
    test_sqlite_chat_id = 123
    upsert_user_settings_sqlite(test_sqlite_chat_id, "TestSQLiteWallet", 0.77, True)
    user_info = get_user_sqlite(test_sqlite_chat_id)
    if user_info:
        logger.info(f"SQLite Test User Info: {dict(user_info)}")
        logger.info(f"SQLite Test Trading Status: {get_user_trading_status_sqlite(test_sqlite_chat_id)}")
    else:
        logger.error("SQLite Test: User info not found.")
