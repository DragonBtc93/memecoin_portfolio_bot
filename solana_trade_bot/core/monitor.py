import asyncio
import logging
import telegram # For telegram.Bot type hint
from solana.rpc.api import Client # For type hinting the passed client

from solana_trade_bot.core.config import (
    SOLANA_RPC_URL, # May not be needed if client always passed
    TAKE_PROFIT_POLLING_INTERVAL_SECONDS,
    SOL_MINT_ADDRESS,
    # NUM_NOTIFICATION_WORKERS # This is used in main.py to create workers
)
from solana_trade_bot.core import db as core_db
from solana_trade_bot.solana_actions import trading as solana_trading
# Import the specific notification function from its new location
from solana_trade_bot.bot.notifications import notify_user_of_new_mint

logger = logging.getLogger(__name__)

# This global set is for the new mint detection, which is being moved to monitor_ws.py
# If check_take_profits_periodically doesn't do any signature processing itself, it can be removed.
# For now, let's assume it's not needed here.
# processed_signatures_this_session = set()


async def notification_worker(name: str, queue: asyncio.Queue, bot: telegram.Bot, solana_client_instance: Client):
    """Worker that processes notification tasks from the queue."""
    logger.info(f"Notification worker {name} started.")
    while True:
        try:
            # Item from queue: (user_chat_id, new_mint_address, dev_wallet_address)
            # solana_client_instance is passed to worker at init and reused
            user_chat_id, new_mint_address, dev_wallet_address = await queue.get() # The WS monitor will put 3 items
            logger.info(f"Worker {name}: Processing new mint notification for user {user_chat_id}, mint {new_mint_address}")

            await notify_user_of_new_mint(
                bot=bot,
                chat_id=user_chat_id,
                new_token_mint_address=new_mint_address,
                dev_wallet_address=dev_wallet_address,
                solana_client=solana_client_instance
            )
            queue.task_done()
        except asyncio.CancelledError:
            logger.info(f"Notification worker {name} cancelled. Exiting.")
            break
        except Exception as e:
            logger.error(f"Notification worker {name}: Error processing new mint notification item for user {user_chat_id} - {e}", exc_info=True)
            queue.task_done()


async def check_take_profits_periodically(bot: telegram.Bot, solana_http_client: Client):
    """
    Periodically checks for take-profit conditions for users' confirmed trades.
    This function is intended to be run as a separate asyncio task.
    """
    logger.info("Take-profit checker polling process started.")
    # solana_http_client is now passed in.

    while True:
        logger.info("Starting take-profit check cycle...")
        all_user_chat_ids = []
        try:
            all_user_chat_ids = await asyncio.to_thread(core_db.get_all_user_chat_ids)
            if not all_user_chat_ids:
                logger.info("No users found to check take-profits for this cycle.")
            else:
                logger.info(f"Found {len(all_user_chat_ids)} users to check for take-profits.")
        except Exception as e:
            logger.error(f"Error fetching all user chat IDs for TP check: {e}", exc_info=True)
            # Sleep before retrying to avoid hammering DB on persistent errors
            await asyncio.sleep(TAKE_PROFIT_POLLING_INTERVAL_SECONDS)
            continue # Skip this cycle if we can't get users

        # Fetch current SOL price once for the cycle if needed for USD conversion
        sol_price_usdc_for_tp = None
        if all_user_chat_ids: # Only fetch SOL price if there are users to check
            try:
                sol_price_usdc_for_tp = await asyncio.to_thread(
                    solana_trading.get_current_token_price,
                    SOL_MINT_ADDRESS,
                    vs_token="USDC"
                )
                if sol_price_usdc_for_tp is None:
                    logger.warning("Could not fetch SOL/USDC price for TP calculations. Will skip P/L calculation in USD for this cycle.")
                else:
                    logger.info(f"Current SOL/USDC price for TP calcs: ${sol_price_usdc_for_tp:.2f}")
            except Exception as e:
                logger.error(f"Error fetching SOL/USDC price for TP check: {e}", exc_info=True)
                sol_price_usdc_for_tp = None # Ensure it's None if fetch fails

        for chat_id in all_user_chat_ids:
            logger.debug(f"Checking take-profits for user {chat_id}")
            try:
                confirmed_trades = await asyncio.to_thread(core_db.get_user_trades, chat_id, only_open=True)
                if not confirmed_trades:
                    logger.debug(f"No confirmed_buy trades found for user {chat_id}.")
                    continue

                # Collect mints for batch price fetching for this user's trades
                trade_mints_to_fetch = {trade['token_mint_address'] for trade in confirmed_trades}
                fetched_token_prices_usd = {}
                if trade_mints_to_fetch:
                    list_of_mints = list(trade_mints_to_fetch)
                    logger.debug(f"TP Check for user {chat_id}: Batch fetching prices for {len(list_of_mints)} token mints.")
                    fetched_token_prices_usd = await asyncio.to_thread(
                        solana_trading.get_current_token_prices_batch,
                        list_of_mints,
                        vs_token="USDC"
                    )

                for trade in confirmed_trades:
                    token_mint = trade['token_mint_address']
                    bought_price_sol_per_token = trade['sol_price_at_buy']
                    last_tp_notified_level_db = trade['last_tp_notified_level']

                    if bought_price_sol_per_token is None:
                        logger.warning(f"Skipping TP check for trade_id {trade['trade_id']} (user {chat_id}): missing bought_price_sol_per_token.")
                        continue

                    current_token_price_usdc = fetched_token_prices_usd.get(token_mint)

                    if current_token_price_usdc is None:
                        logger.warning(f"TP Check: Current price for {token_mint} (user {chat_id}, trade {trade['trade_id']}) not available from batch. Skipping TP for this token.")
                        continue

                    if sol_price_usdc_for_tp is None: # If SOL price fetch failed, cannot convert buy price to USD
                        logger.warning(f"Skipping USD P/L calculation for {token_mint} (trade {trade['trade_id']}) as SOL/USDC price is unavailable.")
                        continue

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

                    if new_tp_level and message:
                        logger.info(f"Take profit alert for user {chat_id}, trade {trade['trade_id']}, token {token_mint}: {message} (Sell fraction: {suggested_sell_fraction})")
                        try:
                            await bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
                            await asyncio.to_thread(
                                core_db.update_trade_status,
                                trade['trade_id'],
                                trade['status'],
                                last_tp_notified_level=new_tp_level
                            )
                            logger.info(f"Successfully notified user {chat_id} and updated trade {trade['trade_id']} last_tp_level to {new_tp_level}%.")
                        except Exception as e_tp_notify:
                            logger.error(f"Error sending TP notification or updating DB for user {chat_id}, trade {trade['trade_id']}: {e_tp_notify}", exc_info=True)
            except Exception as e_user_tp:
                 logger.error(f"Error processing take-profits for user {chat_id}: {e_user_tp}", exc_info=True)

        logger.info(f"Take-profit check cycle finished. Sleeping for {TAKE_PROFIT_POLLING_INTERVAL_SECONDS} seconds.")
        await asyncio.sleep(TAKE_PROFIT_POLLING_INTERVAL_SECONDS)

if __name__ == '__main__':
    print("This module is not intended to be run directly anymore for monitoring.")
    print("The notification_worker and check_take_profits_periodically functions are started by bot/main.py.")
    pass
