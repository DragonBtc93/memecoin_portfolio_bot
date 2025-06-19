import asyncio
import logging
import json # For potentially parsing raw messages if needed, though solana-py might handle it

# Solana specific imports
from solana.rpc.websocket_api import connect as ws_connect # Direct import for connect
from solana.rpc.commitment import Confirmed
from solders.pubkey import Pubkey # Already aliased as PublicKey in other files, use directly or alias
from solders.rpc.config import RpcTransactionLogsFilterMentions # Correct import path
from solders.rpc.responses import LogsNotification, SubscriptionResult, ErrorNotification # For type checking
from solana.rpc.api import Client as HttpClient # For get_transaction_details

# Websockets library for specific exceptions
import websockets

# Project-specific imports
from solana_trade_bot.core.config import (
    SOLANA_WS_URL,
    DEV_WALLETS_TO_TRACK,
    WS_RECONNECT_DELAY_SECONDS,
    SOLANA_RPC_URL # For the HTTP client
)
from solana_trade_bot.core import db as core_db
from solana_trade_bot.solana_actions.tracker import get_transaction_details, is_new_token_mint
# Assuming notification_q and bot are passed in, so direct import of notify_user_of_new_mint is for the worker
from solana_trade_bot.bot.notifications import notify_user_of_new_mint # Used by the worker, not directly here

logger = logging.getLogger(__name__)

# In-memory set for short-term de-duplication of signatures within a session
processed_signatures_this_session = set()

async def subscribe_to_dev_wallet_logs(
    bot: telegram.Bot, # telegram.Bot instance from python-telegram-bot
    notification_q: asyncio.Queue,
    solana_http_client: HttpClient # HTTP client passed from main_async
):
    """
    Connects to Solana WebSocket, subscribes to logs mentioning dev wallets,
    and processes them to find new mints.
    """
    # solana_http_client is now passed in, no need to create it here.
    # logger.info(f"Using shared HTTP client: {solana_http_client.endpoint}") # Example if you need to log its usage

    dev_wallet_pubkeys = [Pubkey.from_string(addr) for addr in DEV_WALLETS_TO_TRACK if addr and "Replace" not in addr]
    if not dev_wallet_pubkeys:
        logger.warning("No valid developer wallets configured in DEV_WALLETS_TO_TRACK for WebSocket monitoring. Exiting.")
        return

    logs_filter = RpcTransactionLogsFilterMentions([str(pk) for pk in dev_wallet_pubkeys])

    while True: # Outer loop for reconnection
        try:
            logger.info(f"Attempting to connect to WebSocket: {SOLANA_WS_URL}")
            async with ws_connect(SOLANA_WS_URL) as websocket: # websocket is SolanaWsClientProtocol
                logger.info(f"WebSocket connected: {SOLANA_WS_URL}")

                # Subscription
                await websocket.logs_subscribe(filter_=logs_filter, commitment=Confirmed)
                logger.info(f"Attempted logs_subscribe for dev wallets: {[str(pk) for pk in dev_wallet_pubkeys]}")

                # Message processing loop
                async for message_wrapper_list in websocket: # solana-py's ws yields a list of notifications
                    for message_wrapper in message_wrapper_list: # Iterate through items in the list
                        if isinstance(message_wrapper, SubscriptionResult):
                            subscription_id = message_wrapper.result
                            logger.info(f"Successfully subscribed to logs. Subscription ID: {subscription_id}")

                        elif isinstance(message_wrapper, LogsNotification):
                            log_details = message_wrapper.result.value
                            tx_sig = str(log_details.signature) # Convert Solders.Signature

                            if log_details.err:
                                logger.debug(f"Tx {tx_sig} had an error, skipping: {log_details.err}")
                                processed_signatures_this_session.add(tx_sig) # Add even if error to avoid re-fetch
                                continue

                            if tx_sig in processed_signatures_this_session:
                                logger.debug(f"Tx {tx_sig} already processed in this session via WS, skipping.")
                                continue

                            logger.info(f"Log notification received for tx: {tx_sig}")
                            processed_signatures_this_session.add(tx_sig) # Add early

                            # How to determine which dev_wallet was mentioned?
                            # The logs_filter mentions *any* of them. The log_details.logs may contain it.
                            # For now, using a generic source. A better way is one sub per dev wallet, or parse logs.
                            # Let's assume for now the dev_wallet_source is ambiguous if multiple are watched by one filter.
                            # We can try to find which dev_wallet is in account_keys of the tx later.

                            # Fetch full transaction details using HTTP client
                            logger.debug(f"Fetching details for tx {tx_sig}...")
                            tx_details = await asyncio.to_thread(get_transaction_details, tx_sig) # get_transaction_details uses its own client

                            if tx_details:
                                # Determine which dev wallet was actually involved for better logging/attribution
                                actual_dev_wallet_source = "WS_LOG_MENTION" # Default
                                if tx_details.get("transaction", {}).get("message", {}).get("accountKeys"):
                                    acc_keys = [str(key_info.get('pubkey') if isinstance(key_info, dict) else key_info)
                                                for key_info in tx_details["transaction"]["message"]["accountKeys"]]
                                    for dev_pk_str in DEV_WALLETS_TO_TRACK: # Check against original string list
                                        if dev_pk_str in acc_keys:
                                            actual_dev_wallet_source = dev_pk_str
                                            break

                                new_mint_address = await asyncio.to_thread(is_new_token_mint, tx_details)
                                if new_mint_address:
                                    logger.info(f"New mint via WS: {new_mint_address} from tx {tx_sig} (Dev: {actual_dev_wallet_source})")
                                    db_mint_entry = await asyncio.to_thread(core_db.get_monitored_mint, new_mint_address)

                                    if db_mint_entry is None:
                                        logger.info(f"Mint {new_mint_address} is new to DB. Adding and queuing.")
                                        await asyncio.to_thread(
                                            core_db.add_monitored_mint,
                                            new_mint_address,
                                            actual_dev_wallet_source, # Use determined source
                                            tx_sig,
                                            None # initial_liquidity_info placeholder
                                        )

                                        all_user_chat_ids = await asyncio.to_thread(core_db.get_all_user_chat_ids)
                                        users_to_notify_count = 0
                                        for user_chat_id in all_user_chat_ids:
                                            trading_enabled = await asyncio.to_thread(core_db.get_user_trading_status, user_chat_id)
                                            if trading_enabled:
                                                # Item for queue: (user_chat_id, new_mint_address, dev_wallet_source)
                                                # solana_client for prepare_tx is passed to worker at its init
                                                await notification_q.put((user_chat_id, new_mint_address, actual_dev_wallet_source))
                                                users_to_notify_count += 1

                                        if users_to_notify_count > 0:
                                            logger.info(f"Queued {users_to_notify_count} notifications for mint {new_mint_address}.")

                                        await asyncio.to_thread(core_db.update_mint_processed_time, new_mint_address)
                                        logger.info(f"Mint {new_mint_address} marked as processed for notification queuing.")
                                    else:
                                        logger.info(f"Mint {new_mint_address} (from WS tx {tx_sig}) already in DB (processed at {db_mint_entry['processed_by_bot_at']}). Skipping.")
                            else:
                                logger.warning(f"Could not get tx_details for {tx_sig} found via WS.")

                        elif isinstance(message_wrapper, ErrorNotification):
                            logger.error(f"WebSocket Error Notification: Code: {message_wrapper.error.code}, Message: {message_wrapper.error.message}")

                        else:
                            logger.warning(f"Received other/unknown WS message type: {type(message_wrapper)} - {message_wrapper}")

        except (websockets.exceptions.ConnectionClosed, websockets.exceptions.WebSocketException, psycopg2.OperationalError) as e: # Added psycopg2.OperationalError for DB issues
            logger.error(f"WebSocket connection issue or DB operational error: {e}. Reconnecting in {WS_RECONNECT_DELAY_SECONDS}s...")
            await asyncio.sleep(WS_RECONNECT_DELAY_SECONDS)
        except Exception as e:
            logger.critical(f"Critical error in WebSocket monitor: {e}. Reconnecting in {WS_RECONNECT_DELAY_SECONDS}s...", exc_info=True)
            await asyncio.sleep(WS_RECONNECT_DELAY_SECONDS)
        finally:
            # This finally block is for the 'async with ws_connect'
            # If connection drops, the 'async with' block exits, and this finally runs.
            # The outer 'while True' ensures reconnection.
            logger.info("WebSocket connection attempt finished or failed. Will retry if in main loop.")
            # Ensure any specific cleanup related to `websocket` object if needed, though `async with` handles it.

# Note: The notification_worker is defined in core/monitor.py (the polling monitor)
# If this WS monitor is to run *instead* of the polling one, notification_worker should be here.
# If they run *together*, they need to share the same queue and bot instance,
# and worker creation should be centralized or passed around.
# For this task, assume this WS monitor might be primary and would need its own workers
# if the polling monitor's workers are not accessible/shared.
# However, the task implies passing notification_q, so workers are likely managed in main_async.
# The `notification_worker` is already in `core/monitor.py` which is fine.
# This `subscribe_to_dev_wallet_logs` will be started as a task similar to `monitor_wallets`.

if __name__ == '__main__':
    # Example of how to run this subscriber (for testing purposes)
    # This requires a running bot instance for the 'bot' and 'notification_q'
    # and also an HTTP client for 'solana_client_for_details'

    # Setup basic logging for direct script run
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("WebSocket monitor direct run (conceptual test)...")

    class MockBot: # Mock Telegram Bot
        async def send_message(self, chat_id, text, parse_mode):
            logger.info(f"MOCK BOT to {chat_id}: {text[:100]}...")

    async def test_run():
        mock_bot_instance = MockBot()
        q = asyncio.Queue()

        # Create a dummy notification worker for this test
        async def dummy_notification_worker(name: str, queue: asyncio.Queue, bot_obj, client_obj):
            logger.info(f"Dummy worker {name} started.")
            while True:
                item = await queue.get()
                logger.info(f"Dummy worker {name} got: {item}")
                # Simulate calling notify_user_of_new_mint
                await asyncio.sleep(0.1) # Simulate work
                queue.task_done()

        # Start dummy workers
        # solana_http_client = HttpClient(SOLANA_RPC_URL)
        # worker_tasks = [
        #     asyncio.create_task(dummy_notification_worker(f"DW-{i}", q, mock_bot_instance, solana_http_client))
        #     for i in range(2)
        # ]

        try:
            # The main function to test is subscribe_to_dev_wallet_logs
            # It needs the real notification_worker setup if we want to test the full E2E queue.
            # For now, this __main__ is mostly for validating it can run without syntax errors.
            # Actual test would involve starting the bot and this monitor.
            logger.info("Conceptual: In a real test, you'd start this with a bot instance and queue.")
            # await subscribe_to_dev_wallet_logs(mock_bot_instance, q)
            logger.info("If it were running, it would connect to Solana WebSocket now.")
            await asyncio.sleep(5) # Run for a bit then stop for this test
        except KeyboardInterrupt:
            logger.info("Test run interrupted.")
        # finally:
            # for task in worker_tasks:
            #     task.cancel()
            # await asyncio.gather(*worker_tasks, return_exceptions=True)
            # if solana_http_client: await solana_http_client.close()


    # asyncio.run(test_run())
    print("WebSocket monitor module can be imported. Run via main bot logic.")
    pass
