from solana.rpc.api import Client
from solana.publickey import PublicKey
from solana.rpc.core import RPCException
from solana.rpc.types import TokenAccountOpts
from solders.pubkey import Pubkey # For Token Program ID
from solana_trade_bot.core.config import (
    DEV_WALLETS_TO_TRACK,
    SOLANA_RPC_URL,
    TAKE_PROFIT_LEVELS_PERCENTAGES
)

# Initialize Solana client
solana_client = Client(SOLANA_RPC_URL)

def get_transaction_history(wallet_address: str, limit: int = 10) -> list:
    """
    Fetches the recent transaction signatures for a given Solana wallet address.
    """
    print(f"Fetching transaction history for {wallet_address} (limit: {limit})...")
    try:
        public_key = PublicKey(wallet_address)
        response = solana_client.get_signatures_for_address(public_key, limit=limit)
        if response and response.get('result'):
            signatures = [tx['signature'] for tx in response['result']]
            print(f"Found {len(signatures)} transactions.")
            return signatures
        else:
            print("No transactions found or error in response.")
            return []
    except RPCException as e:
        print(f"RPC Error fetching transaction history for {wallet_address}: {e}")
        return []
    except ValueError as e: # For invalid PublicKey
        print(f"Invalid wallet address format for {wallet_address}: {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred while fetching history for {wallet_address}: {e}")
        return []

def get_transaction_details(signature: str) -> dict | None:
    """
    Fetches detailed information for a given transaction signature.
    """
    print(f"Fetching details for transaction {signature}...")
    try:
        transaction = solana_client.get_transaction(signature, max_supported_transaction_version=0) # Specify version to avoid potential issues
        if transaction and transaction.get('result'):
            print("Transaction details fetched successfully.")
            return transaction['result']
        else:
            print("Could not fetch transaction details or error in response.")
            return None
    except RPCException as e:
        print(f"RPC Error fetching transaction details for {signature}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while fetching details for {signature}: {e}")
        return None

def is_new_token_mint(transaction_details: dict) -> bool:
    """
    Analyzes transaction details to determine if it represents a new token mint.
    Placeholder: This function needs significant refinement.
    """
    if not transaction_details:
        return False

    # Highly simplified placeholder logic.
    # Real logic would involve checking for specific instructions like:
    # - SystemProgram.create_account
    # - TokenProgram.initialize_mint
    # - Instructions involving the SPL Token program ID (TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA)
    print("Analyzing transaction for new token mint (placeholder logic)...")

    # Example: Look for 'initializeMint' in log messages (very naive)
    log_messages = transaction_details.get("meta", {}).get("logMessages", [])
    for message in log_messages:
        if "InitializeMint" in message: # This is a common log message for token mints
            print("Potential new token mint detected based on log messages.")
            return True

    # Look for instructions interacting with the SPL Token Program
    if transaction_details.get("transaction"):
        instructions = transaction_details["transaction"].get("message", {}).get("instructions", [])
        for instruction in instructions:
            # This needs a proper way to get program ID and decode instruction data
            # For now, just a placeholder check
            # print(f"Instruction: {instruction}")
            pass # Add more sophisticated checks here

    print("No clear indication of a new token mint in this transaction (based on placeholder logic).")
    return False

if __name__ == '__main__':
    print("Running Solana action tests...")
    test_wallets = DEV_WALLETS_TO_TRACK

    if not test_wallets or any("ReplaceWithDevWalletAddress" in wallet for wallet in test_wallets):
        print("\nWARNING: No actual developer wallets configured in core.config.py or using placeholders.")
        print("Please add actual developer wallet addresses to solana_trade_bot/core/config.py.")
        print("Using a generic known address for demonstration (e.g., Raydium Deployer).")
        # Be mindful of rate limits if using public endpoints heavily.
        # You can comment out the line below if you have actual DEV_WALLETS_TO_TRACK configured.
        test_wallets = ["RaydiumDeployer11111111111111111111111111111111"]

    for wallet in test_wallets:
        print(f"\n--- Testing for wallet: {wallet} ---")
        history = get_transaction_history(wallet, limit=5)
        if history:
            for sig in history:
                details = get_transaction_details(sig)
                if details:
                    # print(f"Transaction Details for {sig}: {details}") # Can be very verbose
                    is_mint = is_new_token_mint(details)
                    print(f"Transaction {sig} is a new token mint: {is_mint}")
                    if is_mint:
                        print(f"!!! New token mint potentially found in transaction: {sig} for wallet {wallet}")
                else:
                    print(f"Could not retrieve details for transaction {sig}")
        else:
            print(f"No transaction history found for {wallet}")

    print("\nSolana action tests finished.")


def prepare_buy_transaction(new_token_mint_address: str, buyer_wallet_address: str, sol_amount: float) -> str:
    """
    Conceptually prepares the necessary details for a buy transaction.
    This is a placeholder. Real implementation would involve DEX interaction.
    """
    # For now, this function just returns a descriptive string.
    # In a real scenario, this would involve:
    # 1. Choosing a DEX (e.g., Raydium, Orca).
    # 2. Finding the liquidity pool for the new_token_mint_address against SOL.
    # 3. Constructing the transaction with appropriate instructions (e.g., swap).
    # 4. Potentially returning a serialized transaction to be signed by the user,
    #    or handling the signing and sending if the bot controls the private keys (not recommended for user funds).

    action_message = (
        f"Action Required: Buy {sol_amount:.4f} SOL worth of token {new_token_mint_address}.\n"
        f"Your wallet: {buyer_wallet_address}.\n"
        f"Please execute this buy order manually via your preferred wallet interface or a trusted DEX aggregator (e.g., Jupiter - jup.ag).\n"
        f"Ensure you verify the token address and contract details before swapping."
    )
# Token Program ID for SPL tokens
TOKEN_PROGRAM_ID = Pubkey.from_string('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA')

def get_token_balances_for_wallet(wallet_address: str) -> dict[str, float] | None:
    """
    Fetches all SPL token balances for a given Solana wallet address.
    Returns a dictionary {token_mint_address: balance}.
    """
    print(f"Fetching token balances for wallet: {wallet_address}")
    try:
        public_key = PublicKey(wallet_address)
        opts = TokenAccountOpts(program_id=TOKEN_PROGRAM_ID)
        response = solana_client.get_token_accounts_by_owner(public_key, opts=opts, encoding="jsonParsed")

        if response and response.get('result') and response['result'].get('value'):
            balances: dict[str, float] = {}
            for account_info in response['result']['value']:
                parsed_info = account_info.get('account', {}).get('data', {}).get('parsed', {}).get('info', {})
                if parsed_info:
                    mint_address = parsed_info.get('mint')
                    token_amount_ui = parsed_info.get('tokenAmount', {}).get('uiAmount')
                    # token_amount_decimals = parsed_info.get('tokenAmount', {}).get('decimals') # Available if needed

                    if mint_address and token_amount_ui is not None:
                        balances[mint_address] = balances.get(mint_address, 0.0) + float(token_amount_ui)

            print(f"Found {len(balances)} token mints for wallet {wallet_address}.")
            return balances
        else:
            print(f"No token accounts found or error in response for wallet {wallet_address}.")
            return {} # Return empty dict if no tokens or error
    except RPCException as e:
        print(f"RPC Error fetching token balances for {wallet_address}: {e}")
        return None
    except ValueError as e: # For invalid PublicKey
        print(f"Invalid wallet address format for {wallet_address}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while fetching token balances for {wallet_address}: {e}")
        return None

def get_current_token_price(token_mint_address: str) -> float | None:
    """
    Placeholder function to get the current market price of a token.
    In a real implementation, this would query a DEX or a price API.
    """
    print(f"Fetching price for token: {token_mint_address} (using mock data)")
    # Mock prices for demonstration.
    # Replace with actual API calls to Jupiter, Birdeye, CoinGecko, etc.
    # Example known tokens (replace with actual mints you might test with)
    # USDC mint address on mainnet
    if token_mint_address == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v":
        return 1.0
    # Some other known token, e.g., Raydium (RAY)
    elif token_mint_address == "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R":
        return 1.5 # Mock price for RAY
    # A test token you might have created
    elif token_mint_address == "TESTMINTADDRESS1234567890123456789012345":
        return 0.5
    else:
        # For unknown tokens, or if the price API fails, return None or a default.
        # Returning a mock price for a few for testing purposes.
        if len(token_mint_address) % 2 == 0 : # Simple arbitrary logic for more mock variety
             return 0.25
        # return None
        return 0.1 # Default mock for other tokens for testing profit calc

def calculate_profit(bought_price: float, current_price: float, amount: float) -> float:
    """
    Calculates profit or loss.
    """
    if amount == 0:
        return 0.0
    return (current_price - bought_price) * amount

# Conceptual Data Store for User Trades:
# To accurately track profits, the bot would need to store records of user trades.
# This could be a list associated with each user (chat_id) in a database or a persistent file.
# Example structure:
# user_trades = {
#     chat_id_1: [
#         {"token_mint": "MINT_ADDRESS_A", "bought_amount": 100.0, "bought_price_sol": 0.05, "bought_price_usd": 1.50, "timestamp": "2023-10-26T10:00:00Z"},
#         {"token_mint": "MINT_ADDRESS_B", "bought_amount": 50.0, "bought_price_sol": 0.02, "bought_price_usd": 0.80, "timestamp": "2023-10-27T14:30:00Z"}
#     ],
#     chat_id_2: [
#         ...
#     ]
# }
# This data would be populated when a user confirms they have acted on a buy signal/recommendation from the bot.
# The `view_profits_command` would then use the actual `bought_price_usd` (or SOL) from this store.
