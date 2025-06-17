import logging
import re # For basic wallet validation
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackContext

from solana_trade_bot.bot.config import TELEGRAM_BOT_TOKEN
from solana_trade_bot.core.config import MIN_BUY_SOL, MAX_BUY_SOL
# Updated import for prepare_buy_transaction
from solana_trade_bot.solana_actions import trading as solana_trading
from solana_trade_bot.solana_actions import tracker as solana_tracker # Still needed for other tracker functions

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# In-memory storage for user wallets (chat_id: wallet_address)
# For simplicity in this example. A database would be better for persistence.
user_wallets = {}
user_buy_preferences = {} # Stores chat_id: sol_amount

# Basic Solana address validation (length and base58 characters)
# A full validation is more complex and might involve checksums or specific libraries.
SOLANA_ADDRESS_REGEX = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    await update.message.reply_text("Welcome to the Solana Trading Bot!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a helpful message when the /help command is issued."""
    help_text = (
        "Available commands:\n"
        "/start - Welcome message\n"
        "/help - Shows this help message\n"
        "/link_wallet <your_solana_address> - Link your Solana wallet for tracking.\n"
        "/my_wallet - Shows your currently linked Solana wallet.\n"
        "/set_buy_amount <SOL_amount> - Set your desired SOL amount for buys (e.g., 0.1).\n"
        "/get_buy_amount - Shows your current buy amount setting.\n"
        "/view_profits - View conceptual profits for your tokens."
    )
    await update.message.reply_text(help_text)

async def link_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Links a Solana wallet address to the user's chat ID."""
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text(
            "Please provide your Solana wallet address after the command.\n"
            "Usage: /link_wallet YOUR_SOLANA_ADDRESS"
        )
        return

    wallet_address = context.args[0]

    if not SOLANA_ADDRESS_REGEX.match(wallet_address):
        await update.message.reply_text(
            f"The provided address '{wallet_address}' does not look like a valid Solana address. "
            "Please check the address and try again. It should be 32-44 characters long and contain only base58 characters."
        )
        return

    user_wallets[chat_id] = wallet_address
    logger.info(f"Wallet {wallet_address} linked for chat_id {chat_id}")
    await update.message.reply_text(f"Wallet {wallet_address} linked successfully!")

async def my_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's linked Solana wallet."""
    chat_id = update.effective_chat.id
    wallet_address = user_wallets.get(chat_id)

    if wallet_address:
        await update.message.reply_text(f"Your linked wallet is: {wallet_address}")
    else:
        await update.message.reply_text(
            "You haven't linked a wallet yet. Use /link_wallet <your_wallet_address>."
        )

async def set_buy_amount_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sets the user's desired SOL amount for buys."""
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text(
            f"Please provide the SOL amount after the command.\n"
            f"Usage: /set_buy_amount <SOL_amount>\n"
            f"Min: {MIN_BUY_SOL} SOL, Max: {MAX_BUY_SOL} SOL."
        )
        return

    try:
        sol_amount_str = context.args[0]
        sol_amount = float(sol_amount_str)
        if not (MIN_BUY_SOL <= sol_amount <= MAX_BUY_SOL):
            await update.message.reply_text(
                f"Invalid amount: {sol_amount_str}. "
                f"Please set an amount between {MIN_BUY_SOL} and {MAX_BUY_SOL} SOL."
            )
            return
        user_buy_preferences[chat_id] = sol_amount
        logger.info(f"Buy amount {sol_amount} SOL set for chat_id {chat_id}")
        await update.message.reply_text(f"Buy amount set to: {sol_amount} SOL.")
    except ValueError:
        await update.message.reply_text(
            f"Invalid amount: {context.args[0]}. Please enter a valid number."
        )

async def get_buy_amount_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's set SOL buy amount."""
    chat_id = update.effective_chat.id
    sol_amount = user_buy_preferences.get(chat_id)
    if sol_amount is not None:
        await update.message.reply_text(f"Your current buy amount is: {sol_amount} SOL.")
    else:
        await update.message.reply_text(
            f"You haven't set a buy amount yet. Use /set_buy_amount <SOL_amount>.\n"
            f"Min: {MIN_BUY_SOL} SOL, Max: {MAX_BUY_SOL} SOL."
        )

async def notify_user_of_new_mint(
    bot_instance: Application, # Pass the application or bot instance
    chat_id: int,
    new_token_mint_address: str,
    dev_wallet_address: str
) -> None:
    """
    Notifies a user about a new token mint and provides a conceptual buy action.
    This function would be triggered by the tracker logic.
    """
    logger.info(f"Attempting to notify chat_id {chat_id} about new mint {new_token_mint_address} from dev {dev_wallet_address}")
    user_wallet = user_wallets.get(chat_id)
    buy_amount_sol = user_buy_preferences.get(chat_id)

    if user_wallet and buy_amount_sol:
        prepared_action_message = solana_trading.prepare_buy_transaction(
            new_token_mint_address=new_token_mint_address,
            buyer_wallet_address=user_wallet,
            sol_amount=buy_amount_sol
        )
        full_message = (
            f"🔥 New token mint detected from a tracked developer wallet ({dev_wallet_address})!\n"
            f"Token Mint Address: {new_token_mint_address}\n\n"
            f"{prepared_action_message}"
        )
        try:
            await bot_instance.bot.send_message(chat_id=chat_id, text=full_message)
            logger.info(f"Successfully sent new mint notification to chat_id {chat_id} for token {new_token_mint_address}")
        except Exception as e:
            logger.error(f"Failed to send message to chat_id {chat_id}: {e}")
    else:
        if not user_wallet:
            logger.info(f"Cannot notify chat_id {chat_id}: No wallet linked.")
        if not buy_amount_sol:
            logger.info(f"Cannot notify chat_id {chat_id}: No buy amount set.")


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("link_wallet", link_wallet_command))
    application.add_handler(CommandHandler("my_wallet", my_wallet_command))
    application.add_handler(CommandHandler("set_buy_amount", set_buy_amount_command))
    application.add_handler(CommandHandler("get_buy_amount", get_buy_amount_command))
    application.add_handler(CommandHandler("view_profits", view_profits_command))

    # Example of how notify_user_of_new_mint could be tested/used conceptually
    # In a real scenario, this would be triggered by the Solana event listener.
    # async def _test_notify(app: Application):
    #     await asyncio.sleep(10) # Wait for bot to connect
    #     chat_ids = list(user_wallets.keys())
    #     if chat_ids:
    #         first_chat_id = chat_ids[0]
    #         if user_buy_preferences.get(first_chat_id):
    #             logger.info(f"Simulating notification for chat_id {first_chat_id}")
    #             await notify_user_of_new_mint(app, first_chat_id, "NEW_MINT_ADDRESS_TEST", "DEV_WALLET_TEST")
    #         else:
    #             logger.info(f"Simulating notification: chat_id {first_chat_id} has no buy preferences set.")
    #     else:
    #         logger.info("Simulating notification: No users have linked wallets.")

    # if __name__ == "__main__": # This check is already outside, ensure main() is called within it.
    #    application.job_queue.run_once(lambda _: asyncio.create_task(_test_notify(application)), 0)


    # Run the bot until the user presses Ctrl-C
    logger.info("Starting bot polling...")
    application.run_polling()

# Conceptual: Placeholder for where actual trade records would be stored/retrieved.
# See solana_actions/tracker.py for a more detailed structure.
# user_trades_history = { chat_id: [{"token_mint": "...", "bought_price": ..., "amount": ...}] }

async def view_profits_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays conceptual profit/loss for tokens in the user's linked wallet."""
    chat_id = update.effective_chat.id
    user_wallet_address = user_wallets.get(chat_id)

    if not user_wallet_address:
        await update.message.reply_text("Please link your Solana wallet first using /link_wallet.")
        return

    await update.message.reply_text("Fetching your token balances and calculating conceptual profits...\nThis might take a moment.")

    token_balances = solana_tracker.get_token_balances_for_wallet(user_wallet_address)

    if token_balances is None:
        await update.message.reply_text("Sorry, there was an error fetching your token balances. Please try again later.")
        return

    if not token_balances:
        await update.message.reply_text("You don't seem to hold any SPL tokens in your linked wallet, or they couldn't be fetched.")
        return

    profit_messages = []
    total_conceptual_profit = 0.0
    MOCK_BOUGHT_PRICE_USD = 0.05 # General mock bought price for tokens if not found in a (future) trade history

    for mint_address, amount in token_balances.items():
        if amount == 0: # Skip if balance is zero
            continue

        current_price_usd = solana_tracker.get_current_token_price(mint_address)

        # Conceptual part: Use a real 'bought_price' from user_trades_history if available
        # For now, using a general mock bought price.
        # In a real system, you'd look up this mint_address in user_trades_history for this chat_id.
        actual_bought_price = MOCK_BOUGHT_PRICE_USD
        # Example: if mint_address == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": # USDC
        #    actual_bought_price = 1.0 # USDC bought price is usually $1

        if current_price_usd is not None:
            profit = solana_tracker.calculate_profit(actual_bought_price, current_price_usd, amount)
            total_conceptual_profit += profit
            profit_messages.append(
                f"Token: `{mint_address}`\n"
                f"  Amount: {amount:.4f}\n"
                f"  Mock Bought Price: ${actual_bought_price:.4f}\n"
                f"  Current Price: ${current_price_usd:.4f}\n"
                f"  Conceptual P/L: ${profit:+.4f}"
            )
        else:
            profit_messages.append(
                f"Token: `{mint_address}`\n"
                f"  Amount: {amount:.4f}\n"
                f"  Current Price: Not available (mock)"
            )

    if profit_messages:
        response_message = "Your Conceptual Token Profits/Losses:\n\n" + "\n\n".join(profit_messages)
        response_message += f"\n\nTotal Conceptual P/L: ${total_conceptual_profit:+.4f}"
        response_message += "\n\nDisclaimer: This is a conceptual calculation with mock bought prices. Actual profits depend on your true entry prices and execution."
    else:
        response_message = "Could not calculate profits for any of your tokens (e.g., no price data found or zero balances)."

    await update.message.reply_text(response_message, parse_mode='Markdown')


if __name__ == "__main__":
    main()
