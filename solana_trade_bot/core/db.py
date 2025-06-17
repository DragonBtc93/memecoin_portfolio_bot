import sqlite3
from solana_trade_bot.core.config import DATABASE_FILE

def get_db_connection() -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn

def init_db() -> None:
    """Initializes the database and creates tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users table: Stores user preferences and linked wallet
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            linked_solana_address TEXT UNIQUE,
            buy_amount_sol REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Using UNIQUE for linked_solana_address assuming one bot user per Solana address for simplicity.
    # Added updated_at trigger for users table
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS update_users_updated_at
        AFTER UPDATE ON users
        FOR EACH ROW
        BEGIN
            UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE chat_id = OLD.chat_id;
        END;
    """)

    # Trades table: Records details about each trade initiated or tracked by the bot for a user
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            token_mint_address TEXT NOT NULL,
            dev_wallet_source TEXT,
            sol_price_at_buy REAL,      -- Store the SOL price of the token at the time of buy signal/confirmation
            tokens_bought REAL,         -- Amount of the new token bought by the user
            sol_spent REAL,             -- Amount of SOL spent by the user
            status TEXT NOT NULL,       -- e.g., 'notified_buy', 'confirmed_buy', 'notified_tp1', 'confirmed_sell_partial', 'confirmed_sell_all', 'monitoring_failed'
            notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- When the user was first notified about this mint
            buy_confirmed_at TIMESTAMP, -- When the user confirmed they bought
            last_tp_notified_level INTEGER, -- e.g., 0 (no TP), 1 (TP1), 2 (TP2)
            sell_initiated_at TIMESTAMP, -- When user initiated a sell through the bot (if feature exists)
            sell_confirmed_at TIMESTAMP, -- When user confirmed they sold
            FOREIGN KEY (chat_id) REFERENCES users (chat_id)
        )
    """)
    # Consider adding indexes later on frequently queried columns like chat_id, token_mint_address in trades.

    # Monitored Mints table: Keeps track of new mints detected from dev wallets
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitored_mints (
            mint_address TEXT PRIMARY KEY,
            dev_wallet_source TEXT NOT NULL, -- The developer wallet that minted this token
            initial_liquidity_info TEXT, -- Could be JSON string with details if available
            transaction_signature TEXT, -- Signature of the mint transaction
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_by_bot_at TIMESTAMP -- Timestamp when the bot finished initial processing (e.g., notifying users)
        )
    """)
    # Consider adding an index on dev_wallet_source or detected_at if queried often.

    conn.commit()
    conn.close()
    print("Database schema initialized/verified.")

if __name__ == '__main__':
    print(f"Initializing database '{DATABASE_FILE}'...")
    init_db()
    print("Database initialization process complete.")
    # Example: Test connection and list tables
    # conn = get_db_connection()
    # cursor = conn.cursor()
    # cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    # tables = cursor.fetchall()
    # print("Tables found:", [table['name'] for table in tables])
    # conn.close()
