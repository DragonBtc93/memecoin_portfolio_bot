import logging
from .config import DATABASE_TYPE

# Import functions from the specific database modules
from .sqlite_db import (
    init_db_sqlite,
    get_user_sqlite,
    upsert_user_settings_sqlite,
    get_user_linked_wallet_sqlite,
    get_user_buy_amount_sqlite,
    get_user_trading_status_sqlite,
    get_all_user_chat_ids_sqlite,
    add_trade_notification_sqlite,
    update_trade_on_buy_confirmation_sqlite,
    get_user_trades_sqlite,
    get_trade_by_id_sqlite,
    update_trade_status_sqlite,
    add_monitored_mint_sqlite,
    get_monitored_mint_sqlite,
    update_mint_processed_time_sqlite
)
from .pg_db import (
    init_db_pg,
    get_user_pg,
    upsert_user_settings_pg,
    get_user_linked_wallet_pg,
    get_user_buy_amount_pg,
    get_user_trading_status_pg,
    get_all_user_chat_ids_pg,
    add_trade_notification_pg,
    update_trade_on_buy_confirmation_pg,
    get_user_trades_pg,
    get_trade_by_id_pg,
    update_trade_status_pg,
    add_monitored_mint_pg,
    get_monitored_mint_pg,
    update_mint_processed_time_pg
)

logger = logging.getLogger(__name__)

# --- Dispatcher functions ---

def init_db():
    if DATABASE_TYPE == "postgres":
        logger.info("Using PostgreSQL database backend for init_db.")
        init_db_pg()
    else: # Default to sqlite
        logger.info("Using SQLite database backend for init_db.")
        init_db_sqlite()

def get_user(chat_id: int):
    if DATABASE_TYPE == "postgres":
        return get_user_pg(chat_id)
    else:
        return get_user_sqlite(chat_id)

def upsert_user_settings(chat_id: int, solana_address: str | None = None,
                         buy_amount_sol: float | None = None,
                         is_trading_enabled: bool | None = None):
    if DATABASE_TYPE == "postgres":
        upsert_user_settings_pg(chat_id, solana_address, buy_amount_sol, is_trading_enabled)
    else:
        upsert_user_settings_sqlite(chat_id, solana_address, buy_amount_sol, is_trading_enabled)

def get_user_linked_wallet(chat_id: int) -> str | None:
    if DATABASE_TYPE == "postgres":
        return get_user_linked_wallet_pg(chat_id)
    else:
        return get_user_linked_wallet_sqlite(chat_id)

def get_user_buy_amount(chat_id: int) -> float | None:
    if DATABASE_TYPE == "postgres":
        return get_user_buy_amount_pg(chat_id)
    else:
        return get_user_buy_amount_sqlite(chat_id)

def get_user_trading_status(chat_id: int) -> bool:
    if DATABASE_TYPE == "postgres":
        return get_user_trading_status_pg(chat_id)
    else:
        return get_user_trading_status_sqlite(chat_id)

def get_all_user_chat_ids() -> list[int]:
    if DATABASE_TYPE == "postgres":
        return get_all_user_chat_ids_pg()
    else:
        return get_all_user_chat_ids_sqlite()

# --- Trades ---
def add_trade_notification(chat_id: int, token_mint_address: str, dev_wallet_source: str, status: str = 'notified_buy'):
    if DATABASE_TYPE == "postgres":
        return add_trade_notification_pg(chat_id, token_mint_address, dev_wallet_source, status)
    else:
        return add_trade_notification_sqlite(chat_id, token_mint_address, dev_wallet_source, status)

def update_trade_on_buy_confirmation(trade_id: int, tokens_bought: float, sol_spent: float, sol_price_at_buy: float) -> bool:
    if DATABASE_TYPE == "postgres":
        return update_trade_on_buy_confirmation_pg(trade_id, tokens_bought, sol_spent, sol_price_at_buy)
    else:
        return update_trade_on_buy_confirmation_sqlite(trade_id, tokens_bought, sol_spent, sol_price_at_buy)

def get_user_trades(chat_id: int, only_open: bool = True):
    if DATABASE_TYPE == "postgres":
        return get_user_trades_pg(chat_id, only_open)
    else:
        return get_user_trades_sqlite(chat_id, only_open)

def get_trade_by_id(trade_id: int):
    if DATABASE_TYPE == "postgres":
        return get_trade_by_id_pg(trade_id)
    else:
        return get_trade_by_id_sqlite(trade_id)

def update_trade_status(trade_id: int, new_status: str, last_tp_notified_level: int | None = None) -> bool:
    if DATABASE_TYPE == "postgres":
        return update_trade_status_pg(trade_id, new_status, last_tp_notified_level)
    else:
        return update_trade_status_sqlite(trade_id, new_status, last_tp_notified_level)

# --- Monitored Mints ---
def add_monitored_mint(mint_address: str, dev_wallet_source: str, transaction_signature: str, initial_liquidity_info: str | None = None) -> bool:
    if DATABASE_TYPE == "postgres":
        return add_monitored_mint_pg(mint_address, dev_wallet_source, transaction_signature, initial_liquidity_info)
    else:
        return add_monitored_mint_sqlite(mint_address, dev_wallet_source, transaction_signature, initial_liquidity_info)

def get_monitored_mint(mint_address: str):
    if DATABASE_TYPE == "postgres":
        return get_monitored_mint_pg(mint_address)
    else:
        return get_monitored_mint_sqlite(mint_address)

def update_mint_processed_time(mint_address: str) -> bool:
    if DATABASE_TYPE == "postgres":
        return update_mint_processed_time_pg(mint_address)
    else:
        return update_mint_processed_time_sqlite(mint_address)

if __name__ == '__main__':
    # This block can be used for basic dispatcher testing or left empty.
    # The actual DB initialization and testing should be done by running the bot
    # or specific test files (e.g., tests/core/test_db.py after adapting it).
    logger.info(f"DB Dispatcher configured for DATABASE_TYPE: {DATABASE_TYPE}")
    logger.info("Running init_db via dispatcher...")
    init_db()
    logger.info("init_db via dispatcher finished.")
    # Example: Test user upsert and get for current DB_TYPE
    # test_chat_id_dispatcher = 9990001
    # upsert_user_settings(test_chat_id_dispatcher, "DispatcherWallet", 0.123, True)
    # user = get_user(test_chat_id_dispatcher)
    # if user:
    #     logger.info(f"Dispatcher test for user {test_chat_id_dispatcher}: {dict(user)}")
    # else:
    #     logger.error(f"Dispatcher test: User {test_chat_id_dispatcher} not found using {DATABASE_TYPE}.")
