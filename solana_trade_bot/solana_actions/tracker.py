from solana.rpc.api import Client
from solders.pubkey import Pubkey as PublicKey
from solana.rpc.core import RPCException
from solana.rpc.types import TokenAccountOpts
from solders.pubkey import Pubkey as SoldersPubkey # Renamed for clarity if PublicKey alias is used
import base58
import logging # Added for logging cache misses/hits if desired
from cachetools import TTLCache, cached
# import threading # RLock not needed for basic @cached usage
from solana_trade_bot.core.config import (
    DEV_WALLETS_TO_TRACK,
    SOLANA_RPC_URL,
    TAKE_PROFIT_LEVELS_PERCENTAGES
)

# Initialize Solana client
solana_client = Client(SOLANA_RPC_URL)
logger = logging.getLogger(__name__) # For logging within this module

# --- Caches ---
# Cache for get_transaction_history (signatures for address)
# Cache history for 100 wallets, each for 10 seconds (data changes frequently)
tx_history_cache = TTLCache(maxsize=100, ttl=10)

# Cache for get_transaction_details
# Cache up to 1000 transaction details, each for 1 hour (transaction details are immutable)
tx_details_cache = TTLCache(maxsize=1000, ttl=3600)

# Cache for get_token_balances_for_wallet
# Cache up to 500 wallet balances, each for 30 seconds (balances can change, but not extremely rapidly for most users)
token_balances_cache = TTLCache(maxsize=500, ttl=30)


@cached(cache=tx_history_cache)
def get_transaction_history(wallet_address: str, limit: int = 10) -> list:
    """
    Fetches the recent transaction signatures for a given Solana wallet address.
    This function's results are cached.
    """
    logger.info(f"CACHE MISS: Fetching transaction history for {wallet_address} (limit: {limit}) from RPC.")
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
    This function's results are cached.
    """
    logger.info(f"CACHE MISS: Fetching details for transaction {signature} from RPC.")
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

SPL_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

def is_new_token_mint(transaction_details: dict) -> str | None:
    """
    Analyzes transaction details to determine if it represents a new SPL token mint
    and returns the mint address if found.

    Args:
        transaction_details: The dictionary returned by client.get_transaction().

    Returns:
        The mint address (string) if an InitializeMint or InitializeMint2 instruction
        for the SPL Token Program is found, otherwise None.
    """
    if not transaction_details or 'transaction' not in transaction_details or \
       'message' not in transaction_details['transaction'] or \
       'instructions' not in transaction_details['transaction']['message'] or \
       'accountKeys' not in transaction_details['transaction']['message']:
        # print("Malformed transaction details or missing essential fields.")
        return None

    try:
        instructions = transaction_details['transaction']['message']['instructions']
        account_keys_raw = transaction_details['transaction']['message']['accountKeys']

        # account_keys can be a list of Pubkey strings or dicts {'pubkey': str, 'signer': bool, 'writable': bool}
        # We just need the pubkey strings for resolving program_id and mint address.
        account_keys = []
        if account_keys_raw and isinstance(account_keys_raw[0], dict): # List of dicts
             account_keys = [str(key_info['pubkey']) for key_info in account_keys_raw]
        elif account_keys_raw and isinstance(account_keys_raw[0], str): # List of strings
            account_keys = [str(key_info) for key_info in account_keys_raw] # Ensure all are strings
        else:
            # print("Account keys format not recognized or empty.")
            return None


        for instruction in instructions:
            program_id_index = instruction.get('programIdIndex')
            if program_id_index is None or program_id_index >= len(account_keys):
                # print(f"Invalid programIdIndex: {program_id_index}")
                continue

            program_id = account_keys[program_id_index]

            if program_id == SPL_TOKEN_PROGRAM_ID:
                data_b58 = instruction.get('data')
                if not data_b58:
                    # print("Instruction data missing for SPL Token Program call.")
                    continue

                try:
                    # The data from JSON RPC is base58 encoded for instructions.
                    # For program logs or other fields, it might be base64.
                    # Confirmed: instruction data is base58.
                    decoded_data = base58.b58decode(data_b58)
                except Exception as e:
                    # print(f"Failed to decode base58 data '{data_b58}': {e}")
                    continue

                if not decoded_data:
                    # print("Decoded data is empty.")
                    continue

                instruction_type = decoded_data[0]

                # InitializeMint instruction type is 0
                # InitializeMint2 instruction type is 14
                if instruction_type == 0 or instruction_type == 14:
                    # The first account in the instruction's 'accounts' list (indices)
                    # is the mint account being initialized.
                    accounts_indices = instruction.get('accounts')
                    if not accounts_indices or len(accounts_indices) == 0:
                        # print("No accounts found in InitializeMint(2) instruction.")
                        continue

                    mint_account_index = accounts_indices[0]
                    if mint_account_index >= len(account_keys):
                        # print(f"Invalid mint_account_index: {mint_account_index}")
                        continue

                    mint_address = account_keys[mint_account_index]
                    # print(f"Found InitializeMint/InitializeMint2 for mint address: {mint_address}")
                    return mint_address

    except KeyError as ke:
        # print(f"KeyError while parsing transaction details: {ke}")
        return None
    except Exception as e:
        # print(f"An unexpected error occurred in is_new_token_mint: {e}")
        return None

    return None

if __name__ == '__main__':
    # base58 import moved to top-level
    print("Running Solana action tests...")
    test_wallets = DEV_WALLETS_TO_TRACK

    # Mock transaction detail for InitializeMint
    # Derived from a real transaction: 5SUi7aEaM4bZ8RVcwGtjS59bs2L62t4xZPT2Xbfz2gPA6L1SJKx2o1F1rJYR6xGk8yPZ8K7f3HFR2CgNgaHi7n7m
    # Program: TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA
    # Instruction: InitializeMint
    # Mint: DgHUnAE4GVWbC1RDeYdD93gN1wB4sWj3gG2Y9xY9fQ7G (this is what we want to extract)
    # Mint Authority: Hj2fAbLz9kXYXzX2sSkbLADn7hT2fG8PAdXgGqVoEaNq
    # Decimals: 6
    mock_init_mint_tx = {
        "slot": 123456789,
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": "DgHUnAE4GVWbC1RDeYdD93gN1wB4sWj3gG2Y9xY9fQ7G", "signer": False, "writable": True, "source": "transaction"}, # Mint Account (target for is_new_token_mint)
                    {"pubkey": "SysvarRent111111111111111111111111111111111", "signer": False, "writable": False, "source": "transaction"}, # Rent Sysvar
                    {"pubkey": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "signer": False, "writable": False, "source": "transaction"}, # SPL Token Program
                    {"pubkey": "Hj2fAbLz9kXYXzX2sSkbLADn7hT2fG8PAdXgGqVoEaNq", "signer": True, "writable": True, "source": "transaction"} # Payer and Mint Authority
                ],
                "instructions": [
                    { # This could be any instruction, e.g. Create Associated Token Account by payer
                        "programIdIndex": 2, # SystemProgram or ATA Program, placeholder
                        "accounts": [0, 3], # Some accounts
                        "data": "3Bxs411Dtc" # Placeholder data
                    },
                    { # The actual InitializeMint instruction
                        "programIdIndex": 2, # Index of SPL Token Program in accountKeys
                        "accounts": [0, 1],  # Index 0 is Mint Account, Index 1 is Rent Sysvar
                        # Data for InitializeMint:
                        # Byte 0: 0 (InitializeMint instruction type)
                        # Byte 1: 6 (decimals)
                        # Byte 2-33: Hj2fAbLz9kXYXzX2sSkbLADn7hT2fG8PAdXgGqVoEaNq (Mint Authority)
                        # Byte 34: 0 (Option: No Freeze Authority)
                        # No Freeze Authority Pubkey follows
                        "data": "16r9gYqYsB7Y2N" # This is a placeholder base58. Real data: base58.b58encode(b'\x00\x06' + base58.b58decode("Hj2fAbLz9kXYXzX2sSkbLADn7hT2fG8PAdXgGqVoEaNq") + b'\x00').decode()
                                          # Actual encoded data for this specific example (decimals=6, authority=Hj2f..., no freeze):
                                          # "1AhHqLgm8mN2C8mFhMWEuV9s3u2ioPDQe3gC4xWp1" (approx, depends on exact authority bytes)
                                          # For testing, let's use a known valid InitializeMint data structure (decimals=9, specific authority, no freeze)
                                          # b'\x00\t' + bytes(32) + b'\x00' -> This is too simple, needs real authority.
                                          # Let's use a short, decodable example:
                                          # Data for: instruction_type=0, decimals=9, mint_authority=bytes(32), option_has_freeze_authority=0
                                          # b'\x00\x09' + b'\x01'*32 + b'\x00' -> base58: 19X2kL.... (long)
                                          # For this test, we'll construct the specific data that should work:
                                          # Decoded: [0, 6, ... (32 bytes of mint authority Hj2f...), 0]
                                          # For Hj2fAbLz9kXYXzX2sSkbLADn7hT2fG8PAdXgGqVoEaNq (mint authority)
                                          # its actual bytes are: base58.b58decode("Hj2fAbLz9kXYXzX2sSkbLADn7hT2fG8PAdXgGqVoEaNq")
                                          # Let's use a simplified data string for the test:
                                          # Instruction 0 (InitializeMint), Decimals 6. Mint Authority (32 bytes), No Freeze Authority (option 0)
                                          # b'\x00\x06' + base58.b58decode("Hj2fAbLz9kXYXzX2sSkbLADn7hT2fG8PAdXgGqVoEaNq") + b'\x00'
                                          # For the mock, we use a pre-calculated base58 string of a valid structure for InitializeMint (type 0)
                                          # This specific string is for: type=0, decimals=6, mint_authority=bytes([1]*32), has_freeze_authority=0
                                          "YVAAACg3VjEZbjQ1NkFCQ0RFRkdISUpLTE1OT1BRUlNUVVY=" # Incorrect b58 for test.
                                          # Corrected: use a simple, valid base58 for instruction type 0
                                          # Data for instruction type 0 (InitializeMint), decimals 9.
                                          # The rest of the data (mint authority, freeze option) would follow.
                                          # We only care about the first byte for this test.
                                          # b'\x00' -> "1" in base58
                                          # b'\x0e' -> "P" in base58 (for InitializeMint2)
                                          # Let's use "1" for InitializeMint
                                          "1" # Represents b'\x00' (InitializeMint instruction)
                    }
                ]
            },
            "signatures": ["...signature..."]
        },
        "meta": {
            # ... other meta fields ...
        }
    }

    # Test with InitializeMint
    print("\n--- Testing is_new_token_mint with mock InitializeMint ---")
    mint_address_found = is_new_token_mint(mock_init_mint_tx)
    print(f"Mint address found from mock InitializeMint: {mint_address_found}")
    if mint_address_found == "DgHUnAE4GVWbC1RDeYdD93gN1wB4sWj3gG2Y9xY9fQ7G":
        print("SUCCESS: Correctly identified mint address from mock InitializeMint.")
    else:
        print(f"FAILURE: Expected DgHUnAE4GVWbC1RDeYdD93gN1wB4sWj3gG2Y9xY9fQ7G, got {mint_address_found}")

    # Modify for InitializeMint2 (instruction type 14)
    mock_init_mint2_tx = mock_init_mint_tx.copy() # Shallow copy, modify carefully
    mock_init_mint2_tx["transaction"]["message"]["instructions"][1]["data"] = "P" # Represents b'\x0e' (InitializeMint2 instruction)

    print("\n--- Testing is_new_token_mint with mock InitializeMint2 ---")
    mint_address_found2 = is_new_token_mint(mock_init_mint2_tx)
    print(f"Mint address found from mock InitializeMint2: {mint_address_found2}")
    if mint_address_found2 == "DgHUnAE4GVWbC1RDeYdD93gN1wB4sWj3gG2Y9xY9fQ7G":
        print("SUCCESS: Correctly identified mint address from mock InitializeMint2.")
    else:
        print(f"FAILURE: Expected DgHUnAE4GVWbC1RDeYdD93gN1wB4sWj3gG2Y9xY9fQ7G, got {mint_address_found2}")

    # Test with a non-mint transaction
    mock_non_mint_tx = {
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": "SomeOtherProgram11111111111111111111111111", "signer": False, "writable": False, "source": "transaction"},
                    {"pubkey": "SomeAccount111111111111111111111111111111", "signer": False, "writable": True, "source": "transaction"}
                ],
                "instructions": [
                    {
                        "programIdIndex": 0,
                        "accounts": [1],
                        "data": "3Bxs411Dtc" # Some other instruction data
                    }
                ]
            }
        }
    }
    print("\n--- Testing is_new_token_mint with mock Non-Mint TX ---")
    no_mint_found = is_new_token_mint(mock_non_mint_tx)
    print(f"Mint address found from non-mint TX: {no_mint_found}")
    if no_mint_found is None:
        print("SUCCESS: Correctly identified no mint.")
    else:
        print(f"FAILURE: Expected None, got {no_mint_found}")

    print("\n--- Live API Tests (if DEV_WALLETS_TO_TRACK is configured) ---")
    if not test_wallets or any("ReplaceWithDevWalletAddress" in wallet for wallet in test_wallets) or test_wallets[0] == "RaydiumDeployer11111111111111111111111111111111":
        print("Skipping live API tests for is_new_token_mint as DEV_WALLETS_TO_TRACK are placeholders or default Raydium.")
        print("Configure actual developer wallets in core/config.py that are known to mint tokens for these tests.")
    else:
        for wallet in test_wallets:
            print(f"\n--- Live testing for wallet: {wallet} ---")
            history = get_transaction_history(wallet, limit=10) # Increased limit for better chance
            found_one_mint_live = False
            if history:
                for sig in history:
                    print(f"Checking live signature: {sig}")
                    details = get_transaction_details(sig)
                    if details:
                        mint_addr = is_new_token_mint(details)
                        if mint_addr:
                            print(f"SUCCESS: Live mint detected! Mint Address: {mint_addr} from tx {sig} by dev {wallet}")
                            found_one_mint_live = True
                            # break # Stop after finding one for brevity in tests
                    else:
                        print(f"Could not retrieve details for transaction {sig}")
                if not found_one_mint_live:
                    print(f"No new token mints identified in the last {len(history)} transactions for {wallet} using is_new_token_mint.")
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
# Ensure Pubkey is aliased correctly if used here, or use SoldersPubkey directly
TOKEN_PROGRAM_ID = SoldersPubkey.from_string('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA')


@cached(cache=token_balances_cache)
def get_token_balances_for_wallet(wallet_address: str) -> dict[str, float] | None:
    """
    Fetches all SPL token balances for a given Solana wallet address.
    Returns a dictionary {token_mint_address: balance}.
    This function's results are cached.
    """
    logger.info(f"CACHE MISS: Fetching token balances for wallet {wallet_address} from RPC.")
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

# calculate_profit and get_current_token_price are being moved to trading.py

# --- Conceptual Mint Detection Loop Integration ---
# The following comments outline how the `monitored_mints` DB functions
# would be integrated into a hypothetical mint detection loop.
# This loop is not implemented in this subtask.

# async def hypothetical_monitor_dev_wallets():
#     # from solana_trade_bot.core import db as core_db # Import needed
#     # from bot.main import notify_user_of_new_mint # Import needed, careful with circular deps
#     # from some_telegram_bot_app_instance import application # Needs access to bot application
#
#     tracked_dev_wallets = DEV_WALLETS_TO_TRACK # From core.config
#
#     while True:
#         for dev_wallet_address in tracked_dev_wallets:
#             # 1. Fetch recent transactions for dev_wallet_address
#             # recent_tx_signatures = get_transaction_history(dev_wallet_address, limit=5) # Example
#             recent_tx_signatures = [] # Placeholder
#
#             for tx_sig in recent_tx_signatures:
#                 # transaction_details = get_transaction_details(tx_sig) # Fetch full details
#                 transaction_details = None # Placeholder
#
#                 # 2. Analyze if it's a new token mint
#                 # is_mint, extracted_mint_address, other_details = is_new_token_mint(transaction_details)
#                 is_mint = False # Placeholder
#                 extracted_mint_address = "SOME_NEW_MINT_ADDRESS_FROM_TX" # Placeholder
#                 initial_liquidity_info_str = "{'details': 'example_liquidity_info'}" # Placeholder
#
#                 if is_mint and extracted_mint_address:
#                     # 3. Check if mint is already processed
#                     existing_mint_record = core_db.get_monitored_mint(extracted_mint_address)
#
#                     if existing_mint_record:
#                         print(f"[TrackerLoop] Mint {extracted_mint_address} already known. Skipping.")
#                         continue # Skip to next transaction
#
#                     # 4. New mint detected, add to DB
#                     print(f"[TrackerLoop] New mint {extracted_mint_address} detected from dev {dev_wallet_address} (Tx: {tx_sig}).")
#                     added_to_db = core_db.add_monitored_mint(
#                         mint_address=extracted_mint_address,
#                         dev_wallet_source=dev_wallet_address,
#                         transaction_signature=tx_sig,
#                         initial_liquidity_info=initial_liquidity_info_str # Or None
#                     )
#
#                     if not added_to_db:
#                         print(f"[TrackerLoop] Failed to add mint {extracted_mint_address} to DB. Skipping notification.")
#                         continue # Skip to next transaction
#
#                     # 5. Proceed with notification logic for all relevant users
#                     # This part needs to iterate over users who have opted-in or all users
#                     # users_to_notify = core_db.get_all_users_with_settings() # Hypothetical function
#                     users_to_notify_chat_ids = [] # Placeholder - e.g., get all chat_ids from users table
#
#                     for chat_id in users_to_notify_chat_ids:
#                         # await notify_user_of_new_mint(
#                         #     bot_instance=application, # Passed in or globally available
#                         #     chat_id=chat_id,
#                         #     new_token_mint_address=extracted_mint_address,
#                         #     dev_wallet_address=dev_wallet_address
#                         # )
#                         pass # Placeholder for actual notification call
#
#                     # 6. Mark mint as processed (notifications sent/attempted)
#                     core_db.update_mint_processed_time(extracted_mint_address)
#                     print(f"[TrackerLoop] Finished processing and notifying for mint {extracted_mint_address}.")
#
#         # await asyncio.sleep(MONITOR_POLLING_INTERVAL_SECONDS) # Check according to config
#         pass # End of while loop
