import urllib.parse
from solana_trade_bot.core.config import TAKE_PROFIT_LEVELS_PERCENTAGES

# Conceptual Data Store for User Trades (as a reminder, same as in tracker.py)
# user_trades = {
#     chat_id_1: [
#         {"token_mint": "MINT_ADDRESS_A", "bought_amount": 100.0, "bought_price_usd": 1.50, "timestamp": "2023-10-26T10:00:00Z"},
#     ],
# }

def generate_phantom_sign_and_send_tx_deep_link(
    serialized_tx_base58: str,
    redirect_url: str = "https://phantom.app/ul/v1/transaction-sent"
) -> str:
    """
    Generates a Phantom deep link for signing and sending a transaction.
    https://docs.phantom.app/integrating/deeplinks-ios-and-android/sign-and-send-transaction
    """
    # For production, Phantom recommends encrypting the transaction payload for signAndSendTransaction
    # and providing an `app_url` for verification. This is a simplified version without encryption.
    # See: https://docs.phantom.app/integrating/deeplinks-ios-and-android/encryption

    encoded_transaction = urllib.parse.quote(serialized_tx_base58)
    encoded_redirect_link = urllib.parse.quote(redirect_url)

    deep_link = f"phantom://v1/signAndSendTransaction?transaction={encoded_transaction}&redirect_link={encoded_redirect_link}"
    # For dapps running in a mobile browser, use:
    # deep_link = f"https://phantom.app/ul/v1/signAndSendTransaction?transaction={encoded_transaction}&redirect_link={encoded_redirect_link}"
    return deep_link

def prepare_buy_transaction(new_token_mint_address: str, buyer_wallet_address: str, sol_amount: float) -> str:
    """
    Conceptually prepares the necessary details for a buy transaction, including a Phantom deep link.
    """
    # 1. Construct the actual unsigned Solana transaction for the swap.
    #    This is highly complex and would involve:
    #    - Choosing a DEX (e.g., Raydium, Orca).
    #    - Using the DEX's SDK/API to find pools and build swap instructions.
    #    - Potentially fetching market data, slippage settings, etc.
    #    THIS IS A MAJOR PLACEHOLDER.

    # 2. Serialize the transaction and base58 encode it.
    #    For now, using a mock base58 serialized transaction string.
    #    A real transaction string would be much longer and specific to the swap.
    mock_serialized_tx_base58 = (
        "MOCK_SERIALIZED_TRANSACTION_BASE58_PLACEHOLDER_FOR_BUYING_"
        f"{sol_amount}_SOL_OF_TOKEN_{new_token_mint_address}_FOR_WALLET_{buyer_wallet_address}"
        # Example of a *very* short, invalid base58 string for structure: "2DDfsfSsdfe"
        # Real ones are hundreds of chars long.
    )

    # 3. Generate the Phantom deep link.
    #    A more user-friendly redirect could be a page on our (hypothetical) bot's website
    #    that confirms the transaction status.
    phantom_deep_link = generate_phantom_sign_and_send_tx_deep_link(mock_serialized_tx_base58)

    instructional_message = (
        f"Action Required: Buy {sol_amount:.4f} SOL worth of token {new_token_mint_address}.\n"
        f"Your wallet: {buyer_wallet_address}.\n\n"
        f"📱 **Execute with Phantom:** {phantom_deep_link}\n\n"
        f"ℹ️ **Manual TX Data (Conceptual):** `{mock_serialized_tx_base58}`\n\n"
        f"⚠️ **Important:** Always verify transaction details in your wallet before approving. "
        f"This is a conceptual bot; the transaction data is a MOCK."
    )
    print(f"[Trading] Prepared buy message and Phantom link for {new_token_mint_address} for wallet {buyer_wallet_address}.")
    return instructional_message

def check_take_profit_levels(
    # chat_id: int, # Would be needed to fetch user-specific trades
    token_mint_address: str,
    current_price: float,
    bought_price: float,
    amount_held: float
) -> list[str]:
    """
    Conceptual: Checks if any take profit levels have been hit for a token.
    Returns a list of notification messages.
    (Moved from tracker.py)
    """
    if bought_price == 0:
        return []

    profit_percent = ((current_price - bought_price) / bought_price) * 100.0
    notifications = []

    for level in TAKE_PROFIT_LEVELS_PERCENTAGES:
        if profit_percent >= level:
            # Conceptual: Add state management to avoid re-notifying for the same level for the same lot.
            notifications.append(
                f"📈 Take Profit Alert for {token_mint_address[:10]}...:\n"
                f"Currently at +{profit_percent:.2f}% (Target: +{level}%).\n"
                f"Current Price: ${current_price:.4f}, Bought Price: ${bought_price:.4f}.\n"
                f"Amount held: {amount_held:.4f}.\n"
                f"Consider taking some profits!"
            )

    if notifications:
        print(f"[Trading] Generated {len(notifications)} take profit alerts for {token_mint_address} at price ${current_price:.4f} (bought ${bought_price:.4f}).")
    return notifications
