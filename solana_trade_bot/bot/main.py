import logging
import re
import asyncio
import telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackContext

from solana_trade_bot.bot.config import TELEGRAM_BOT_TOKEN
from solana_trade_bot.core.config import MIN_BUY_SOL, MAX_BUY_SOL, SOL_MINT_ADDRESS
from solana_trade_bot.solana_actions import trading as solana_trading
from solana_trade_bot.solana_actions import tracker as solana_tracker
from solana_trade_bot.core import db as core_db
from solana_trade_bot.core.config import DATABASE_TYPE # Import DATABASE_TYPE
# Import pool functions, ensure pg_db is imported if DATABASE_TYPE could be postgres
# This import might be conditional if pg_db itself fails on non-pg systems without psycopg2
# For now, assume it's safe to import, or handle import error.
from solana_trade_bot.core.pg_db import init_connection_pool, close_connection_pool
import solana_trade_bot.core.monitor as core_monitor_module
from solana.rpc.api import Client # For type hinting solana_client

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

SOLANA_ADDRESS_REGEX = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    # Ensure user exists in DB, trading_enabled defaults to True on insert
    await asyncio.to_thread(core_db.upsert_user_settings, chat_id=chat_id)
    logger.info(f"User {chat_id} started the bot or was ensured in DB.")
    await update.message.reply_text("Welcome to the Solana Trading Bot! Use /help to see available commands.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Available commands:\n"
        "/start - Welcome message & register.\n"
        "/help - Shows this help message.\n"
        "/link_wallet <your_solana_address> - Link your Solana wallet. (Send without address to unlink)\n"
        "/my_wallet - Shows your currently linked Solana wallet.\n"
        "/set_buy_amount <SOL_amount> - Set your SOL amount for buys (e.g., 0.1). (Send without amount to clear)\n"
        "/get_buy_amount - Shows your current buy amount.\n"
        "/trade_on - Enable new mint buy notifications.\n"
        "/trade_off - Disable new mint buy notifications.\n"
        "/trade_status - Check your trading notification status.\n"
        "/view_profits - View conceptual profits for your trades.\n"
        "/confirm_buy <trade_id> <tokens_bought> <sol_spent> - Confirm purchase details.\n"
        "/confirm_sell <trade_id> <tokens_sold> <sol_received> - (Conceptual) Confirm sale details."
    )
    await update.message.reply_text(help_text)

async def link_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    try:
        if not context.args:
            await asyncio.to_thread(core_db.upsert_user_settings, chat_id=chat_id, solana_address="")
            logger.info(f"Wallet unlinked for chat_id {chat_id}")
            await update.message.reply_text("Solana wallet unlinked.")
            return
        wallet_address = context.args[0]
        if not SOLANA_ADDRESS_REGEX.match(wallet_address):
            await update.message.reply_text("Invalid Solana address format.")
            return
        await asyncio.to_thread(core_db.upsert_user_settings, chat_id=chat_id, solana_address=wallet_address)
        logger.info(f"Wallet {wallet_address} linked for chat_id {chat_id} in DB.")
        await update.message.reply_text(f"Wallet {wallet_address} linked successfully!")
    except Exception as e:
        logger.error(f"Error in link_wallet_command for chat_id {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("An error occurred. Please try again.")

async def my_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    try:
        wallet_address = await asyncio.to_thread(core_db.get_user_linked_wallet, chat_id)
        if wallet_address:
            await update.message.reply_text(f"Your linked wallet is: `{wallet_address}`", parse_mode='Markdown')
        else:
            await update.message.reply_text("You haven't linked a wallet yet. Use /link_wallet.")
    except Exception as e:
        logger.error(f"Error in my_wallet_command for chat_id {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("An error occurred. Please try again.")

async def set_buy_amount_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    try:
        if not context.args:
            await asyncio.to_thread(core_db.upsert_user_settings, chat_id=chat_id, buy_amount_sol=None)
            logger.info(f"Buy amount cleared for chat_id {chat_id}")
            await update.message.reply_text(f"Buy amount cleared. Min: {MIN_BUY_SOL} SOL, Max: {MAX_BUY_SOL} SOL.")
            return
        sol_amount_str = context.args[0]
        sol_amount_float = float(sol_amount_str)
        if not (MIN_BUY_SOL <= sol_amount_float <= MAX_BUY_SOL):
            await update.message.reply_text(f"Invalid amount. Must be between {MIN_BUY_SOL} and {MAX_BUY_SOL} SOL.")
            return
        await asyncio.to_thread(core_db.upsert_user_settings, chat_id=chat_id, buy_amount_sol=sol_amount_float)
        logger.info(f"Buy amount {sol_amount_float} SOL set for chat_id {chat_id} in DB.")
        await update.message.reply_text(f"Buy amount set to: {sol_amount_float} SOL.")
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a valid number.")
    except Exception as e:
        logger.error(f"Error in set_buy_amount_command for chat_id {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("An error occurred. Please try again.")

async def get_buy_amount_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    try:
        buy_amount = await asyncio.to_thread(core_db.get_user_buy_amount, chat_id)
        if buy_amount is not None:
            await update.message.reply_text(f"Your current buy amount is: {buy_amount} SOL.")
        else:
            await update.message.reply_text(f"You haven't set a buy amount. Use /set_buy_amount. Min: {MIN_BUY_SOL} SOL, Max: {MAX_BUY_SOL} SOL.")
    except Exception as e:
        logger.error(f"Error in get_buy_amount_command for chat_id {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("An error occurred. Please try again.")

async def trade_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    try:
        await asyncio.to_thread(core_db.upsert_user_settings, chat_id, is_trading_enabled=True)
        await update.message.reply_text("Trading features are now ON. You may receive notifications for new mints.")
        logger.info(f"Trading ON for chat_id {chat_id}")
    except Exception as e:
        logger.error(f"Error in trade_on_command for chat_id {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("Sorry, there was an error enabling trading. Please try again later.")

async def trade_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    try:
        await asyncio.to_thread(core_db.upsert_user_settings, chat_id, is_trading_enabled=False)
        await update.message.reply_text("Trading features are now OFF. You will not receive new mint notifications.")
        logger.info(f"Trading OFF for chat_id {chat_id}")
    except Exception as e:
        logger.error(f"Error in trade_off_command for chat_id {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("Sorry, there was an error disabling trading. Please try again later.")

async def trade_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    try:
        status = await asyncio.to_thread(core_db.get_user_trading_status, chat_id)
        if status:
            await update.message.reply_text("Trading features are currently ON for you.")
        else:
            await update.message.reply_text("Trading features are currently OFF for you.")
    except Exception as e:
        logger.error(f"Error in trade_status_command for chat_id {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("Sorry, there was an error fetching your trading status.")

async def confirm_buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if len(context.args) != 3:
        await update.message.reply_text("Usage: /confirm_buy <trade_id> <tokens_bought> <total_sol_spent>\nExample: /confirm_buy 123 1000000 0.5")
        return
    try:
        trade_id_str, tokens_bought_str, sol_spent_str = context.args
        parsed_trade_id = int(trade_id_str)
        parsed_tokens_bought = float(tokens_bought_str)
        parsed_sol_spent = float(sol_spent_str)
        if parsed_tokens_bought <= 0 or parsed_sol_spent <= 0:
            await update.message.reply_text("Tokens bought and SOL spent must be positive numbers.")
            return
    except ValueError:
        await update.message.reply_text("Invalid input: <trade_id> integer, amounts numbers.")
        return
    try:
        trade = await asyncio.to_thread(core_db.get_trade_by_id, parsed_trade_id)
        if not trade or trade['chat_id'] != chat_id:
            await update.message.reply_text(f"Trade ID {parsed_trade_id} not found or does not belong to you.")
            return
        if trade['status'] != 'notified_buy':
            await update.message.reply_text(f"Trade ID {parsed_trade_id} not awaiting buy confirmation (status: {trade['status']}).")
            return
        sol_price_per_token = parsed_sol_spent / parsed_tokens_bought
        success = await asyncio.to_thread(core_db.update_trade_on_buy_confirmation, parsed_trade_id, parsed_tokens_bought, parsed_sol_spent, sol_price_per_token)
        if success:
            await update.message.reply_text(f"Buy confirmed for trade ID {parsed_trade_id}!\nTokens: {parsed_tokens_bought}, SOL Spent: {parsed_sol_spent}, Price: {sol_price_per_token:.12f} SOL/token.")
            logger.info(f"Buy confirmed by chat_id {chat_id} for trade_id {parsed_trade_id}")
        else:
            await update.message.reply_text("Failed to confirm buy in database.")
    except Exception as e:
        logger.error(f"Error in confirm_buy_command for chat_id {chat_id}, trade_id {parsed_trade_id}: {e}", exc_info=True)
        await update.message.reply_text("An unexpected error occurred.")

async def confirm_sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if len(context.args) != 3:
        await update.message.reply_text("Usage: /confirm_sell <trade_id> <tokens_sold> <sol_received>")
        return
    try:
        trade_id_str, _, _ = context.args
        parsed_trade_id = int(trade_id_str)
        logger.info(f"Conceptual sell by chat_id {chat_id} for trade_id {parsed_trade_id}: args={context.args}")
        await update.message.reply_text(f"Sell for trade ID {parsed_trade_id} noted (conceptual implementation).")
    except ValueError:
        await update.message.reply_text("Invalid input: <trade_id> must be an integer.")
    except Exception as e:
        logger.error(f"Error in confirm_sell_command for chat_id {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("An error occurred.")

# notify_user_of_new_mint function was moved to bot/notifications.py

async def view_profits_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    try:
        user_wallet_address = await asyncio.to_thread(core_db.get_user_linked_wallet, chat_id)
        if not user_wallet_address:
            await update.message.reply_text("Please link your Solana wallet first using /link_wallet.")
            return

        await update.message.reply_text("Fetching trades and calculating conceptual profits...")
        user_trades = await asyncio.to_thread(core_db.get_user_trades, chat_id, only_open=False)

        if not user_trades:
            await update.message.reply_text("No trades logged by the bot yet.")
            return

        mints_to_fetch = {SOL_MINT_ADDRESS}
        for trade in user_trades:
            mints_to_fetch.add(trade['token_mint_address'])

        fetched_prices = await asyncio.to_thread(solana_trading.get_current_token_prices_batch, list(mints_to_fetch))
        sol_price_usdc_live = fetched_prices.get(SOL_MINT_ADDRESS)

        if sol_price_usdc_live is None:
            await update.message.reply_text("Could not fetch SOL/USDC price. Profit calculation unavailable.")
            return

        profit_messages = []
        total_conceptual_profit_usd = 0.0
        for trade in user_trades:
            mint = trade['token_mint_address']
            status = trade['status']
            tokens = trade['tokens_bought']
            sol_price_buy = trade['sol_price_at_buy']
            curr_token_price_usd = fetched_prices.get(mint)

            msg_part = f"Token: `{mint}` (ID: {trade['trade_id']})\nStatus: {status}"
            if status == 'confirmed_buy' and tokens and sol_price_buy and curr_token_price_usd:
                buy_usd_val_approx = sol_price_buy * sol_price_usdc_live
                profit = (curr_token_price_usd - buy_usd_val_approx) * tokens
                curr_val_usd = curr_token_price_usd * tokens
                total_conceptual_profit_usd += profit
                msg_part += (
                    f"\n  Bought: {tokens:.4f} @ {sol_price_buy:.8f} SOL/token (~${buy_usd_val_approx:.4f} USD/token at current SOL price)"
                    f"\n  Curr Price: ${curr_token_price_usd:.4f} USD | Curr Value: ${curr_val_usd:.2f} USD"
                    f"\n  Est. P/L: ${profit:+.2f} USD"
                )
            elif status == 'notified_buy':
                price_info = f"Curr Price: ${curr_token_price_usdc:.4f} USD" if curr_token_price_usdc else "Curr Price: N/A"
                msg_part += f"\n  (Awaiting /confirm_buy) {price_info}"
            else:
                 price_info = f"Curr Price: ${curr_token_price_usdc:.4f} USD" if curr_token_price_usdc else "Curr Price: N/A"
                 msg_part += f"\n {price_info}"
            profit_messages.append(msg_part)

        if profit_messages:
            response = "Your Tracked Trades & Conceptual Profits:\n\n" + "\n\n".join(profit_messages)
            response += f"\n\nTotal Estimated P/L (Confirmed Buys): ${total_conceptual_profit_usd:+.2f} USD"
            response += "\nDisclaimer: P/L is conceptual, uses current SOL price for original SOL costs."
        else:
            response = "No trades with sufficient data for profit display."
        await update.message.reply_text(response, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in view_profits_command for {chat_id}: {e}", exc_info=True)
        await update.message.reply_text("An error occurred calculating profits.")

async def main_async() -> None:
    logger.info(f"Selected DATABASE_TYPE: {DATABASE_TYPE}")
    if DATABASE_TYPE == "postgres":
        logger.info("Initializing PostgreSQL connection pool...")
        try:
            init_connection_pool() # From core.pg_db
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL connection pool: {e}", exc_info=True)
            # Decide if bot should exit or try to run without DB/with fallback if designed
            return # Exit if essential DB pool fails

    logger.info("Initializing database schema (via dispatcher)...")
    core_db.init_db()
    logger.info("Database schema initialized.")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    bot_instance = application.bot

    handlers = [
        CommandHandler("start", start_command),
        CommandHandler("help", help_command),
        CommandHandler("link_wallet", link_wallet_command),
        CommandHandler("my_wallet", my_wallet_command),
        CommandHandler("set_buy_amount", set_buy_amount_command),
        CommandHandler("get_buy_amount", get_buy_amount_command),
        CommandHandler("trade_on", trade_on_command),
        CommandHandler("trade_off", trade_off_command),
        CommandHandler("trade_status", trade_status_command),
        CommandHandler("view_profits", view_profits_command),
        CommandHandler("confirm_buy", confirm_buy_command),
        CommandHandler("confirm_sell", confirm_sell_command),
    ]
    for handler in handlers:
        application.add_handler(handler)

    logger.info("Creating wallet monitoring task...")
    asyncio.create_task(core_monitor_module.monitor_wallets(bot_instance))
    logger.info("Wallet monitoring task created.")

    logger.info("Starting bot polling...")
    try:
        await application.run_polling()
    finally:
        if DATABASE_TYPE == "postgres":
            logger.info("Shutting down PostgreSQL connection pool...")
            close_connection_pool() # From core.pg_db
        logger.info("Bot shut down gracefully.")

if __name__ == "__main__":
    logger.info("Bot application starting...")
    asyncio.run(main_async())
