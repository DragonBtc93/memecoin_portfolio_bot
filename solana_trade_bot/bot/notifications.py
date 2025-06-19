import logging
import asyncio
import telegram # For telegram.Bot type hint
from solana.rpc.api import Client # For type hinting solana_client

# Assuming core_db and solana_trading are needed by notify_user_of_new_mint
from solana_trade_bot.core import db as core_db
from solana_trade_bot.solana_actions import trading as solana_trading

logger = logging.getLogger(__name__)

async def notify_user_of_new_mint(
    bot: telegram.Bot,
    solana_client: Client,
    chat_id: int,
    new_token_mint_address: str,
    dev_wallet_address: str
) -> None:
    """
    Notifies a user about a new token mint, provides a conceptual buy action,
    and logs the notification to the trades table.
    Accepts a telegram.Bot instance and a Solana Client instance.
    (Moved from bot/main.py)
    """
    logger.info(f"Attempting to notify chat_id {chat_id} about mint {new_token_mint_address} from dev {dev_wallet_address}")
    try:
        # These DB calls are synchronous, so run in a thread from this async function
        user_wallet = await asyncio.to_thread(core_db.get_user_linked_wallet, chat_id)
        buy_amount_sol = await asyncio.to_thread(core_db.get_user_buy_amount, chat_id)

        if user_wallet and buy_amount_sol is not None: # buy_amount_sol can be 0.0
            trade_id = await asyncio.to_thread(
                core_db.add_trade_notification,
                chat_id=chat_id,
                token_mint_address=new_token_mint_address,
                dev_wallet_source=dev_wallet_address
            )

            if not trade_id:
                logger.error(f"Failed to log trade notification for chat_id {chat_id}, mint {new_token_mint_address}")

            sol_amount_lamports = int(buy_amount_sol * 1e9)

            # prepare_buy_transaction is synchronous
            prepared_action_message, _ = await asyncio.to_thread(
                solana_trading.prepare_buy_transaction,
                solana_client,
                new_token_mint_address,
                user_wallet,
                sol_amount_lamports
            )

            trade_id_message_part = f"Trade ID: `{trade_id}` (use for /confirm_buy)\n\n" if trade_id else ""

            full_message = (
                f"🔥 New token mint from dev ({dev_wallet_address[:6]}...)!\n"
                f"Token: `{new_token_mint_address}`\n{trade_id_message_part}{prepared_action_message}"
            )
            await bot.send_message(chat_id=chat_id, text=full_message, parse_mode='Markdown')
            logger.info(f"Sent new mint notification (Trade ID: {trade_id}) to chat_id {chat_id} for {new_token_mint_address}")
        else:
            if not user_wallet:
                logger.info(f"Cannot notify chat_id {chat_id} for mint {new_token_mint_address}: No wallet linked.")
            if buy_amount_sol is None:
                logger.info(f"Cannot notify chat_id {chat_id} for mint {new_token_mint_address}: No buy amount set.")
    except Exception as e:
        logger.error(f"Error in notify_user_of_new_mint for chat_id {chat_id}, token {new_token_mint_address}: {e}", exc_info=True)
