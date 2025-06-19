import asyncio
import time
import logging
import telegram # For telegram.Bot type hint

from solana.rpc.api import Client

from solana_trade_bot.core.config import (
    DEV_WALLETS_TO_TRACK,
    SOLANA_RPC_URL,
    MONITOR_POLLING_INTERVAL_SECONDS,
    SOL_MINT_ADDRESS,
    NUM_NOTIFICATION_WORKERS # Added import
)
from solana_trade_bot.core import db as core_db
from solana_trade_bot.solana_actions.tracker import (
    get_transaction_history,
    get_transaction_details,
    is_new_token_mint
)
from solana_trade_bot.solana_actions import trading as solana_trading
# Import the specific notification function from its new location
from solana_trade_bot.bot.notifications import notify_user_of_new_mint

# Setup logger for this module
# logging.basicConfig already called in bot/main.py, which is the entry point.
# If this module is run standalone for testing, then basicConfig would be needed here.
logger = logging.getLogger(__name__)

processed_signatures_this_session = set() # In-memory set for current session


async def notification_worker(name: str, queue: asyncio.Queue, bot: telegram.Bot, solana_client_instance: Client):
    """Worker that processes notification tasks from the queue."""
    logger.info(f"Notification worker {name} started.")
    while True:
        try:
            # Item from queue: (user_chat_id, new_mint_address, dev_wallet_address)
            # solana_client_instance is passed to worker at init and reused
            user_chat_id, new_mint_address, dev_wallet_address = await queue.get()
            logger.info(f"Worker {name}: Processing notification for user {user_chat_id}, mint {new_mint_address}")

            await notify_user_of_new_mint(
                bot=bot,
                chat_id=user_chat_id,
                new_token_mint_address=new_mint_address,
                dev_wallet_address=dev_wallet_address,
                solana_client=solana_client_instance # Pass the shared client instance
            )
            # logger.info(f"Worker {name}: Successfully sent notification to {user_chat_id} for {new_mint_address}") # Log is in notify_user_of_new_mint
            queue.task_done()
        except asyncio.CancelledError:
            logger.info(f"Notification worker {name} cancelled. Exiting.")
            break
        except Exception as e:
            # Log error but continue worker, and ensure task_done is called
            logger.error(f"Notification worker {name}: Error processing item for user {user_chat_id}, mint {new_mint_address} - {e}", exc_info=True)
            queue.task_done()


async def monitor_wallets(bot: telegram.Bot):
    """
    Continuously monitors specified Solana developer wallets for new token mints
    and queues notifications for users via the Telegram bot.
    """
    logger.info("Wallet monitor started.")
    solana_client = Client(SOLANA_RPC_URL) # Initialize client once for this monitor instance

    notification_q = asyncio.Queue()
    worker_tasks = []
    logger.info(f"Creating {NUM_NOTIFICATION_WORKERS} notification worker tasks...")
    for i in range(NUM_NOTIFICATION_WORKERS):
        # Pass the solana_client instance to each worker
        task = asyncio.create_task(notification_worker(f"Worker-{i+1}", notification_q, bot, solana_client))
        worker_tasks.append(task)
    logger.info(f"{len(worker_tasks)} notification workers started.")

    while True:
        logger.info(f"Starting new monitoring cycle for {len(DEV_WALLETS_TO_TRACK)} dev wallets.")

        for dev_wallet_address in DEV_WALLETS_TO_TRACK:
            if not dev_wallet_address or "ReplaceWithDevWallet" in dev_wallet_address:
                logger.debug(f"Skipping placeholder or empty dev wallet address: {dev_wallet_address}")
                continue

            logger.info(f"Fetching transactions for dev wallet: {dev_wallet_address}")
            try:
                signatures_info = await asyncio.to_thread(
                    get_transaction_history, dev_wallet_address, limit=20
                )

                if not signatures_info:
                    logger.info(f"No recent transaction signatures found for {dev_wallet_address}.")
                    continue

                logger.info(f"Found {len(signatures_info)} signatures for {dev_wallet_address}. Processing...")

                for tx_sig in signatures_info:
                    if tx_sig in processed_signatures_this_session:
                        logger.debug(f"Transaction {tx_sig} already processed in this session. Skipping.")
                        continue

                    logger.info(f"Processing transaction {tx_sig} for dev wallet {dev_wallet_address}.")
                    transaction_details = await asyncio.to_thread(get_transaction_details, tx_sig)

                    if not transaction_details:
                        logger.warning(f"Could not retrieve details for transaction {tx_sig}.")
                        processed_signatures_this_session.add(tx_sig)
                        continue

                    new_mint_address = await asyncio.to_thread(is_new_token_mint, transaction_details)

                    if new_mint_address:
                        logger.info(f"SUCCESS! New mint detected: {new_mint_address} from tx {tx_sig} by dev {dev_wallet_address}.")
                        db_mint_entry = await asyncio.to_thread(core_db.get_monitored_mint, new_mint_address)

                        if db_mint_entry is None:
                            logger.info(f"Mint {new_mint_address} is new to the database. Adding and queuing notifications.")
                            await asyncio.to_thread(
                                core_db.add_monitored_mint,
                                new_mint_address,
                                dev_wallet_address,
                                tx_sig,
                                None
                            )

                            all_user_chat_ids = await asyncio.to_thread(core_db.get_all_user_chat_ids)
                            users_to_notify_count = 0
                            for user_chat_id in all_user_chat_ids:
                                trading_enabled = await asyncio.to_thread(core_db.get_user_trading_status, user_chat_id)
                                if trading_enabled:
                                    # Queue item: (user_chat_id, new_mint_address, dev_wallet_address)
                                    # The solana_client is passed to the worker during its initialization.
                                    await notification_q.put((user_chat_id, new_mint_address, dev_wallet_address))
                                    users_to_notify_count += 1

                            if users_to_notify_count > 0:
                                logger.info(f"Queued {users_to_notify_count} notifications for mint {new_mint_address}.")
                            else:
                                logger.info(f"No users to notify or trading is off for all for mint {new_mint_address}.")

                            await asyncio.to_thread(core_db.update_mint_processed_time, new_mint_address)
                            logger.info(f"Mint {new_mint_address} marked as processed for notification queuing.")
                        else:
                            logger.info(f"Mint {new_mint_address} (from tx {tx_sig}) already in DB (processed at {db_mint_entry['processed_by_bot_at']}). Skipping.")

                    processed_signatures_this_session.add(tx_sig)

            except Exception as e:
                logger.error(f"Error processing wallet {dev_wallet_address}: {e}", exc_info=True)

        # Clean up older signatures
        if len(processed_signatures_this_session) > 10000: # Example threshold
            logger.info(f"Clearing {len(processed_signatures_this_session) - 5000} oldest signatures from session cache.")
            # Convert to list, sort (if order matters, though not strictly necessary for a set), trim, convert back
            # For simplicity, just clear and rebuild in real scenarios or use a more sophisticated cache
            # For this example, let's just clear a portion to show the idea
            items_to_remove = list(processed_signatures_this_session)[:len(processed_signatures_this_session)-5000]
            for item in items_to_remove:
                 processed_signatures_this_session.remove(item)

        # --- Section for Checking Take-Profits ---
        logger.info("Starting take-profit check cycle...")
        all_user_chat_ids = await asyncio.to_thread(core_db.get_all_user_chat_ids)

        # Fetch current SOL price once for the cycle if needed for USD conversion
        prices_to_fetch_in_tp_cycle = {SOL_MINT_ADDRESS} # Use a set to collect unique mints
        unique_trade_mints_for_tp = set()

        # First pass to gather all unique mint addresses from trades across all users
        # This avoids fetching SOL price if no users have trades to check.
        all_user_trades_for_tp_check: dict[int, list] = {}
        if all_user_chat_ids: # Only proceed if there are users
            for chat_id in all_user_chat_ids:
                confirmed_trades = await asyncio.to_thread(core_db.get_user_trades, chat_id, only_open=True)
                if confirmed_trades:
                    all_user_trades_for_tp_check[chat_id] = confirmed_trades
                    for trade in confirmed_trades:
                        unique_trade_mints_for_tp.add(trade['token_mint_address'])

            if unique_trade_mints_for_tp: # Only add SOL if there are trades to process
                 prices_to_fetch_in_tp_cycle.update(unique_trade_mints_for_tp)

        fetched_prices_for_tp = {}
        if prices_to_fetch_in_tp_cycle: # Only fetch if there's something to fetch
            list_of_mints_for_api = list(prices_to_fetch_in_tp_cycle)
            logger.info(f"TP Cycle: Batch fetching prices for {len(list_of_mints_for_api)} unique mints (incl. SOL).")
            fetched_prices_for_tp = await asyncio.to_thread(
                solana_trading.get_current_token_prices_batch,
                list_of_mints_for_api,
                vs_token="USDC"
            )

        sol_price_usdc_for_tp = fetched_prices_for_tp.get(SOL_MINT_ADDRESS)

        if sol_price_usdc_for_tp is None and unique_trade_mints_for_tp: # SOL price needed only if there are trades
            logger.warning("Could not fetch SOL/USDC price for TP calculations. Skipping TP checks for this cycle.")
        elif all_user_trades_for_tp_check: # Only proceed if there are trades to check
            logger.info(f"Current SOL/USDC price for TP calcs: ${sol_price_usdc_for_tp:.2f}" if sol_price_usdc_for_tp else "SOL Price N/A")
            for chat_id, confirmed_trades in all_user_trades_for_tp_check.items():
                logger.debug(f"Checking take-profits for user {chat_id}")
                # confirmed_trades = await asyncio.to_thread(core_db.get_user_trades, chat_id, only_open=True) # Already fetched

                for trade in confirmed_trades:
                    token_mint = trade['token_mint_address']
                    bought_price_sol_per_token = trade['sol_price_at_buy']
                    last_tp_notified_level_db = trade['last_tp_notified_level']

                    if bought_price_sol_per_token is None:
                        logger.warning(f"Skipping TP check for trade_id {trade['trade_id']} (user {chat_id}): missing bought_price_sol_per_token.")
                        continue

                    current_token_price_usdc = fetched_prices_for_tp.get(token_mint)

                    if current_token_price_usdc is None: # Already logged by batch function if API failed for this mint
                        logger.warning(f"TP Check: Current price for {token_mint} (user {chat_id}, trade {trade['trade_id']}) not available from batch. Skipping.")
                        continue

                    # Convert SOL-based buy price to USD for comparison
                    bought_price_usd_per_token = bought_price_sol_per_token * sol_price_usdc_for_tp

                    logger.debug(
                        f"TP Check for trade {trade['trade_id']} ({token_mint}): "
                        f"Bought@ ${bought_price_usd_per_token:.4f} (from {bought_price_sol_per_token:.6f} SOL * ${sol_price_usdc_for_tp:.2f}), "
                        f"Current@ ${current_token_price_usdc:.4f}, Last Notified Level: {last_tp_notified_level_db}%"
                    )

                    new_tp_level, suggested_sell_fraction, message = await asyncio.to_thread(
                        solana_trading.check_take_profit_levels,
                        token_mint,
                        current_token_price_usdc,
                        bought_price_usd_per_token,
                        last_tp_notified_level_db
                    )

                    if new_tp_level and message: # If a new TP level is hit, a message will be generated
                        logger.info(f"Take profit alert for user {chat_id}, trade {trade['trade_id']}, token {token_mint}: {message} (Sell fraction: {suggested_sell_fraction})")
                        try:
                            await bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
                            # Update the last notified level in DB
                            await asyncio.to_thread(
                                core_db.update_trade_status,
                                trade['trade_id'],
                                trade['status'], # Keep current status (e.g. 'confirmed_buy')
                                last_tp_notified_level=new_tp_level
                            )
                            logger.info(f"Successfully notified user {chat_id} and updated trade {trade['trade_id']} last_tp_level to {new_tp_level}%.")
                        except Exception as e_tp_notify:
                            logger.error(f"Error sending TP notification or updating DB for user {chat_id}, trade {trade['trade_id']}: {e_tp_notify}")
        # --- End of Take-Profit Check Section ---

        logger.info(f"Monitoring cycle finished. Sleeping for {MONITOR_POLLING_INTERVAL_SECONDS} seconds.")
        await asyncio.sleep(MONITOR_POLLING_INTERVAL_SECONDS)

if __name__ == '__main__':
    # This is for testing the monitor module directly, requires a mock bot or real token
    # In actual use, monitor_wallets is started by bot/main.py
    print("To test core/monitor.py directly, you would need to mock 'telegram.Bot' and other dependencies.")
    print("Example conceptual call (does not run):")
    print("# async def run_test_monitor():")
    print("#     class MockBot:")
    print("#         async def send_message(self, chat_id, text, parse_mode):")
    print("#             print(f'MockBot SEND to {chat_id}: {text[:70]}...')")
    print("#     mock_bot_instance = MockBot()")
    print("#     print('Initializing DB for monitor test...')")
    print("#     core_db.init_db()")
    print("#     # Add a test user for notifications to work if DB is empty") # Corrected comment
    print("#     core_db.upsert_user_settings(12345, solana_address='TestWallet', buy_amount_sol=0.1)")
    print("#     print('Starting monitor test loop (will run indefinitely)...')")
    print("#     await monitor_wallets(mock_bot_instance)")
    print("# asyncio.run(run_test_monitor())")
    pass
