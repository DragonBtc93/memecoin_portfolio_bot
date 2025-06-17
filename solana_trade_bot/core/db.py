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
            is_trading_enabled BOOLEAN DEFAULT True, -- Added new column
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Schema migration: Add is_trading_enabled if it doesn't exist
    cursor.execute("PRAGMA table_info(users)")
    columns = [column['name'] for column in cursor.fetchall()]
    if 'is_trading_enabled' not in columns:
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN is_trading_enabled BOOLEAN DEFAULT True")
            conn.commit()
            print("Schema migration: Added 'is_trading_enabled' column to 'users' table.")
        except sqlite3.OperationalError as e:
            # This might happen in rare race conditions or if the PRAGMA check is somehow insufficient.
            print(f"Could not add 'is_trading_enabled' column, might already exist or other DB issue: {e}")

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

def get_user(chat_id: int) -> sqlite3.Row | None:
    """Fetches a user by chat_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
    user_row = cursor.fetchone()
    conn.close()
    return user_row

def upsert_user_settings(
    chat_id: int,
    solana_address: str | None = None,
    buy_amount_sol: float | None = None,
    is_trading_enabled: bool | None = None
) -> None:
    """
    Inserts a new user or updates existing user's settings.
    Fields are updated only if a new value is provided.
    For new users, is_trading_enabled defaults to True if not specified.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT chat_id FROM users WHERE chat_id = ?", (chat_id,))
    user_exists = cursor.fetchone()

    if user_exists:
        # User exists, prepare an UPDATE statement
        updates = []
        params = []
        if solana_address is not None: # Allows setting to empty string (which becomes NULL)
            updates.append("linked_solana_address = ?")
            params.append(solana_address if solana_address.strip() else None)
        if buy_amount_sol is not None: # Allows setting to 0.0
            updates.append("buy_amount_sol = ?")
            params.append(buy_amount_sol)
        if is_trading_enabled is not None:
            updates.append("is_trading_enabled = ?")
            params.append(is_trading_enabled)

        if not updates: # Nothing to update
            conn.close()
            return

        # Always update the 'updated_at' timestamp
        updates.append("updated_at = CURRENT_TIMESTAMP")

        query = f"UPDATE users SET {', '.join(updates)} WHERE chat_id = ?"
        params.append(chat_id)

        cursor.execute(query, tuple(params))
        # Log which fields were updated for clarity
        updated_fields_log = [u.split(" = ")[0] for u in updates if u != "updated_at = CURRENT_TIMESTAMP"]
        print(f"Updated user {chat_id}. Fields: {updated_fields_log}")
    else:
        # User does not exist, INSERT new user
        db_sol_address = solana_address if solana_address and solana_address.strip() else None
        # Explicitly handle default for is_trading_enabled on insert
        db_is_trading_enabled = True if is_trading_enabled is None else is_trading_enabled

        cursor.execute(
            """
            INSERT INTO users (chat_id, linked_solana_address, buy_amount_sol, is_trading_enabled)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, db_sol_address, buy_amount_sol, db_is_trading_enabled)
        )
        print(f"Inserted new user {chat_id} with trading_enabled={db_is_trading_enabled}")

    conn.commit()
    conn.close()

def get_user_linked_wallet(chat_id: int) -> str | None:
    """Fetches the linked Solana address for a user."""
    user = get_user(chat_id)
    if user and user['linked_solana_address']:
        return user['linked_solana_address']
    return None

def get_user_buy_amount(chat_id: int) -> float | None:
    """Fetches the buy amount for a user."""
    user = get_user(chat_id)
    if user and user['buy_amount_sol'] is not None: # Check for not None, as 0.0 is a valid amount
        return float(user['buy_amount_sol'])
    return None

def get_user_trading_status(chat_id: int) -> bool:
    """
    Fetches the is_trading_enabled status for a user.
    Defaults to False if user not found or status is NULL.
    """
    user = get_user(chat_id)
    if user and user['is_trading_enabled'] is not None:
        return bool(user['is_trading_enabled']) # Ensure it's a boolean
    return False # Default to False if no user or no value


if __name__ == '__main__':
    print(f"Initializing database '{DATABASE_FILE}'...")
    init_db() # This will also run the migration if column doesn't exist
    print("Database initialization process complete.")

    # Example Usage & Testing for users table:
    test_chat_id1 = 12345
    test_chat_id2 = 67890
    test_chat_id3 = 55555 # For testing trading status defaults

    print(f"\n--- Testing User Settings for chat_id {test_chat_id1} ---")
    # These tests are now primarily covered by tests/core/test_db.py
    # Leaving a minimal set for quick ad-hoc checks if needed.
    upsert_user_settings(test_chat_id1, solana_address="MainWalletXYZ", buy_amount_sol=0.25, is_trading_enabled=True)
    user1_data = get_user(test_chat_id1)
    if user1_data:
        print(f"User {test_chat_id1} data: Wallet={user1_data['linked_solana_address']}, BuyAmt={user1_data['buy_amount_sol']}, Trading={user1_data['is_trading_enabled']}")
    else:
        print(f"User {test_chat_id1} not found.")


# --- Trades Table CRUD Operations ---

def add_trade_notification(chat_id: int, token_mint_address: str, dev_wallet_source: str, status: str = 'notified_buy') -> int | None:
    """
    Inserts a new trade notification record into the trades table.
    Returns the trade_id of the newly inserted row, or None if insertion fails.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO trades (chat_id, token_mint_address, dev_wallet_source, status, notified_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (chat_id, token_mint_address, dev_wallet_source, status)
        )
        trade_id = cursor.lastrowid
        conn.commit()
        print(f"Added trade notification for chat_id {chat_id}, mint {token_mint_address}. Trade ID: {trade_id}")
        return trade_id
    except sqlite3.Error as e:
        print(f"Database error in add_trade_notification: {e}")
        return None
    finally:
        conn.close()

def update_trade_on_buy_confirmation(trade_id: int, tokens_bought: float, sol_spent: float, sol_price_at_buy: float) -> bool:
    """
    Updates an existing trade record upon user's buy confirmation.
    Sets status to 'confirmed_buy' and records purchase details.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE trades
            SET tokens_bought = ?, sol_spent = ?, sol_price_at_buy = ?,
                status = 'confirmed_buy', buy_confirmed_at = CURRENT_TIMESTAMP
            WHERE trade_id = ?
            """,
            (tokens_bought, sol_spent, sol_price_at_buy, trade_id)
        )
        updated_rows = cursor.rowcount
        conn.commit()
        if updated_rows > 0:
            print(f"Trade {trade_id} updated to 'confirmed_buy'.")
            return True
        else:
            print(f"Trade {trade_id} not found for buy confirmation update.")
            return False
    except sqlite3.Error as e:
        print(f"Database error in update_trade_on_buy_confirmation for trade_id {trade_id}: {e}")
        return False
    finally:
        conn.close()

def get_user_trades(chat_id: int, only_open: bool = True) -> list[sqlite3.Row]:
    """
    Fetches trades for a given chat_id.
    If only_open is True, fetches trades with status 'notified_buy' or 'confirmed_buy'.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM trades WHERE chat_id = ?"
    params: tuple = (chat_id,)

    if only_open:
        # For take-profit, only 'confirmed_buy' trades have a cost basis
        query += " AND status = 'confirmed_buy'"
    # else, if not only_open, it fetches all trades for that user regardless of status.

    query += " ORDER BY notified_at DESC" # Show newest first

    cursor.execute(query, params)
    trades = cursor.fetchall()
    conn.close()
    return trades

def get_trade_by_id(trade_id: int) -> sqlite3.Row | None:
    """Fetches a specific trade by its trade_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,))
    trade_row = cursor.fetchone()
    conn.close()
    return trade_row

def update_trade_status(trade_id: int, new_status: str, last_tp_notified_level: int | None = None) -> bool:
    """
    Updates the status of a trade.
    Optionally updates the last_tp_notified_level.
    """
    conn = get_db_connection()
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
        if updated_rows > 0:
            print(f"Trade {trade_id} status updated to '{new_status}'. TP level: {last_tp_notified_level if last_tp_notified_level is not None else 'N/A'}")
            return True
        else:
            print(f"Trade {trade_id} not found for status update.")
            return False
    except sqlite3.Error as e:
        print(f"Database error in update_trade_status for trade_id {trade_id}: {e}")
        return False
    finally:
        conn.close()

# Conceptual: User Confirmation of Buy
# Future bot commands like:
# /confirm_buy <trade_id> <tokens_bought> <sol_spent> <sol_price_token>
#   - <trade_id>: Provided in the initial buy notification.
#   - <tokens_bought>: How many tokens the user actually bought.
#   - <sol_spent>: How much SOL they spent in total.
#   - <sol_price_token>: The price of the token in SOL at the time of their purchase (tokens_bought / sol_spent).
# This command would then call `core_db.update_trade_on_buy_confirmation(...)`.
# The `notify_user_of_new_mint` function in `bot/main.py` should be modified
# to include the `trade_id` in the notification message to enable this.
# Example: "New mint detected! Token: MINT_XYZ. Trade ID: 123. [Phantom Link]"
#
# Similarly, for sells:
# /confirm_sell <trade_id> <tokens_sold> <sol_received> <status ('partial' or 'full')>
# This would call a new DB function like `update_trade_on_sell_confirmation(...)`.


if __name__ == '__main__':
    # (Existing __main__ content for init_db and user tests remains)
    # ... [previous test code for users table] ...
    print("\n--- Testing Trades Table Operations ---")
    test_user_for_trades = 12345 # Assuming this user exists from previous tests
    core_db.upsert_user_settings(test_user_for_trades, "WalletForTrades", 1.0)


    # 1. Add a trade notification
    trade_id1 = add_trade_notification(test_user_for_trades, "MintAddressXYZ123", "DevWalletABC")
    if trade_id1:
        print(f"Added trade notification with ID: {trade_id1}")
        trade_info = get_trade_by_id(trade_id1)
        print(f"Trade info: {dict(trade_info) if trade_info else 'Not found'}")

        # 2. Confirm the buy for this trade
        confirmed = update_trade_on_buy_confirmation(trade_id1, tokens_bought=1000.0, sol_spent=0.5, sol_price_at_buy=(0.5/1000.0))
        if confirmed:
            trade_info_after_confirm = get_trade_by_id(trade_id1)
            print(f"Trade info after confirmation: {dict(trade_info_after_confirm) if trade_info_after_confirm else 'Not found'}")

    # 3. Add another trade notification
    trade_id2 = add_trade_notification(test_user_for_trades, "MintAddressABC456", "DevWalletXYZ", status='notified_buy')
    if trade_id2:
         print(f"Added another trade notification with ID: {trade_id2}")

    # 4. Get all open trades for the user
    print(f"\nOpen trades for user {test_user_for_trades}:")
    open_trades = get_user_trades(test_user_for_trades, only_open=True)
    for trade in open_trades:
        print(dict(trade))

    # 5. Get all trades for the user
    print(f"\nAll trades for user {test_user_for_trades}:")
    all_trades = get_user_trades(test_user_for_trades, only_open=False) # Should show both
    for trade in all_trades:
        print(dict(trade))

    # 6. Update status of a trade (e.g., a take profit level was hit and notified)
    if trade_id1:
        status_updated = update_trade_status(trade_id1, new_status='notified_tp1', last_tp_notified_level=1)
        if status_updated:
            trade_info_after_status_update = get_trade_by_id(trade_id1)
            print(f"Trade info after status update: {dict(trade_info_after_status_update) if trade_info_after_status_update else 'Not found'}")

    # 7. Get open trades again (trade_id1 should no longer be 'confirmed_buy' or 'notified_buy')
    print(f"\nOpen trades for user {test_user_for_trades} after TP notification:")
    open_trades_after_tp = get_user_trades(test_user_for_trades, only_open=True)
    for trade in open_trades_after_tp: # Should only show trade_id2 if trade_id1 status changed from open states
        print(dict(trade))

    # Test with a trade that remains open
    if trade_id2:
        open_trades_check = get_user_trades(test_user_for_trades, only_open=True)
        found_trade2 = any(t['trade_id'] == trade_id2 for t in open_trades_check)
        print(f"Trade ID {trade_id2} still found in open trades: {found_trade2}")


def get_all_user_chat_ids() -> list[int]:
    """Fetches all unique chat_ids from the users table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT chat_id FROM users")
        rows = cursor.fetchall()
        return [row['chat_id'] for row in rows]
    except sqlite3.Error as e:
        print(f"Database error in get_all_user_chat_ids: {e}")
        return []
    finally:
        conn.close()


# --- Monitored Mints Table CRUD Operations ---

def add_monitored_mint(mint_address: str, dev_wallet_source: str, transaction_signature: str, initial_liquidity_info: str | None = None) -> bool:
    """
    Inserts a new mint record into the monitored_mints table.
    Returns True on successful insertion, False if the mint_address already exists or other error.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO monitored_mints (mint_address, dev_wallet_source, transaction_signature, initial_liquidity_info, detected_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (mint_address, dev_wallet_source, transaction_signature, initial_liquidity_info)
        )
        conn.commit()
        print(f"Added monitored mint: {mint_address} from dev {dev_wallet_source}")
        return True
    except sqlite3.IntegrityError: # Handles PRIMARY KEY constraint violation (mint_address already exists)
        print(f"Mint address {mint_address} already exists in monitored_mints.")
        return False
    except sqlite3.Error as e:
        print(f"Database error in add_monitored_mint for {mint_address}: {e}")
        return False
    finally:
        conn.close()

def get_monitored_mint(mint_address: str) -> sqlite3.Row | None:
    """Fetches a monitored mint record by mint_address."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM monitored_mints WHERE mint_address = ?", (mint_address,))
    mint_row = cursor.fetchone()
    conn.close()
    return mint_row

def update_mint_processed_time(mint_address: str) -> bool:
    """Updates the processed_by_bot_at timestamp for a given mint_address."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE monitored_mints SET processed_by_bot_at = CURRENT_TIMESTAMP WHERE mint_address = ?",
            (mint_address,)
        )
        updated_rows = cursor.rowcount
        conn.commit()
        if updated_rows > 0:
            print(f"Updated processed_by_bot_at for mint: {mint_address}")
            return True
        else:
            print(f"Mint {mint_address} not found for processed_by_bot_at update.")
            return False
    except sqlite3.Error as e:
        print(f"Database error in update_mint_processed_time for {mint_address}: {e}")
        return False
    finally:
        conn.close()
