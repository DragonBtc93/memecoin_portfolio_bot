import asyncio
import time
import logging
import telegram # For telegram.Bot type hint

from solana.rpc.api import Client

from solana_trade_bot.core.config import (
    DEV_WALLETS_TO_TRACK,
    SOLANA_RPC_URL,
    MONITOR_POLLING_INTERVAL_SECONDS,
    SOL_MINT_ADDRESS # Added import
)
from solana_trade_bot.core import db as core_db
from solana_trade_bot.solana_actions.tracker import (
    get_transaction_history,
    get_transaction_details,
    is_new_token_mint
)
from solana_trade_bot.solana_actions import trading as solana_trading # Added import
# Import the specific notification function
from solana_trade_bot.bot.main import notify_user_of_new_mint

# Setup logger for this module
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

processed_signatures_this_session = set() # In-memory set for current session

async def monitor_wallets(bot: telegram.Bot):
    """
    Continuously monitors specified Solana developer wallets for new token mints
    and notifies users via the Telegram bot.
    """
    logger.info("Wallet monitor started.")
    solana_client = Client(SOLANA_RPC_URL) # Initialize client once

    while True:
        logger.info(f"Starting new monitoring cycle for {len(DEV_WALLETS_TO_TRACK)} dev wallets.")

        for dev_wallet_address in DEV_WALLETS_TO_TRACK:
            if not dev_wallet_address or "ReplaceWithDevWallet" in dev_wallet_address:
                logger.debug(f"Skipping placeholder or empty dev wallet address: {dev_wallet_address}")
                continue

            logger.info(f"Fetching transactions for dev wallet: {dev_wallet_address}")
            try:
                # Use asyncio.to_thread for synchronous blocking calls
                signatures_info = await asyncio.to_thread(
                    get_transaction_history, dev_wallet_address, limit=20 # Increased limit
                )

                if not signatures_info:
                    logger.info(f"No recent transaction signatures found for {dev_wallet_address}.")
                    continue

                logger.info(f"Found {len(signatures_info)} signatures for {dev_wallet_address}. Processing...")

                for tx_sig in signatures_info: # get_transaction_history now returns list of sig strings
                    if tx_sig in processed_signatures_this_session:
                        logger.debug(f"Transaction {tx_sig} already processed in this session. Skipping.")
                        continue

                    logger.info(f"Processing transaction {tx_sig} for dev wallet {dev_wallet_address}.")

                    transaction_details = await asyncio.to_thread(get_transaction_details, tx_sig)

                    if not transaction_details:
                        logger.warning(f"Could not retrieve details for transaction {tx_sig}.")
                        processed_signatures_this_session.add(tx_sig) # Add here to avoid re-fetching erroring tx
                        continue

                    new_mint_address = await asyncio.to_thread(is_new_token_mint, transaction_details)

                    if new_mint_address:
                        logger.info(f"SUCCESS! New mint detected: {new_mint_address} from tx {tx_sig} by dev {dev_wallet_address}.")

                        # Check if this mint is already in our monitored_mints DB
                        db_mint_entry = await asyncio.to_thread(core_db.get_monitored_mint, new_mint_address)

                        if db_mint_entry is None:
                            logger.info(f"Mint {new_mint_address} is new to the database. Adding and preparing to notify.")

                            # Add to monitored_mints DB
                            # Assuming initial_liquidity_info might be extracted or is None for now
                            await asyncio.to_thread(
                                core_db.add_monitored_mint,
                                new_mint_address,
                                dev_wallet_address,
                                tx_sig,
                                None # Placeholder for initial_liquidity_info
                            )

                            # Get all users to notify
                            user_chat_ids = await asyncio.to_thread(core_db.get_all_user_chat_ids)
                            logger.info(f"Notifying {len(user_chat_ids)} users about new mint {new_mint_address}.")

                            for user_chat_id in user_chat_ids:
                                try:
                                    trading_enabled = await asyncio.to_thread(core_db.get_user_trading_status, user_chat_id)
                                    if trading_enabled:
                                        logger.info(f"User {user_chat_id} has trading ON. Notifying for new mint {new_mint_address}.")
                                        await notify_user_of_new_mint(
                                            bot=bot,
                                            solana_client=solana_client,
                                            chat_id=user_chat_id,
                                            new_token_mint_address=new_mint_address,
                                            dev_wallet_address=dev_wallet_address
                                        )
                                    else:
                                        logger.info(f"User {user_chat_id} has trading OFF. Skipping new mint buy notification for {new_mint_address}.")
                                except Exception as e_notify:
                                    logger.error(f"Error during notification process for user {user_chat_id}, mint {new_mint_address}: {e_notify}")

                            # Mark mint as processed (notifications sent/attempted or skipped based on user pref)
                            await asyncio.to_thread(core_db.update_mint_processed_time, new_mint_address)
                            logger.info(f"Finished processing and notifying for mint {new_mint_address}.")
                        else:
                            logger.info(f"Mint {new_mint_address} (from tx {tx_sig}) already in DB (processed at {db_mint_entry['processed_by_bot_at']}). Skipping notification.")
                    # else:
                        # logger.debug(f"Transaction {tx_sig} is not a new token mint.")

                    processed_signatures_this_session.add(tx_sig) # Add to session cache after processing

            except Exception as e:
                logger.error(f"Error processing wallet {dev_wallet_address}: {e}", exc_info=True)

        # Clean up older signatures from the session cache to prevent unbounded growth if bot runs for very long
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
        sol_price_usdc_for_tp = await asyncio.to_thread(
            solana_trading.get_current_token_price,
            SOL_MINT_ADDRESS, # Use imported SOL_MINT_ADDRESS directly
            vs_token="USDC"
        )
        if sol_price_usdc_for_tp is None:
            logger.warning("Could not fetch SOL/USDC price for TP calculations. Skipping TP checks for this cycle.")
        else:
            logger.info(f"Current SOL/USDC price for TP calcs: ${sol_price_usdc_for_tp:.2f}")
            for chat_id in all_user_chat_ids:
                logger.debug(f"Checking take-profits for user {chat_id}")
                confirmed_trades = await asyncio.to_thread(core_db.get_user_trades, chat_id, only_open=True)

                if not confirmed_trades:
                    logger.debug(f"No confirmed_buy trades found for user {chat_id}.")
                    continue

                for trade in confirmed_trades:
                    token_mint = trade['token_mint_address']
                    bought_price_sol_per_token = trade['sol_price_at_buy']
                    last_tp_notified_level_db = trade['last_tp_notified_level'] # This is an INT or None

                    if bought_price_sol_per_token is None: # Should not happen for 'confirmed_buy'
                        logger.warning(f"Skipping TP check for trade_id {trade['trade_id']} (user {chat_id}): missing bought_price_sol_per_token.")
                        continue

                    current_token_price_usdc = await asyncio.to_thread(
                        solana_trading.get_current_token_price, token_mint, vs_token="USDC"
                    )

                    if current_token_price_usdc is None:
                        logger.warning(f"Could not fetch current price for {token_mint} (user {chat_id}, trade {trade['trade_id']}). Skipping TP check.")
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
