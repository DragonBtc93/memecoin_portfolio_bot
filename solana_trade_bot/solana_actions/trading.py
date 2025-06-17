import urllib.parse
import requests # For Jupiter API
import logging
import base58

from solana_trade_bot.core.config import TAKE_PROFIT_LEVELS_PERCENTAGES, SOL_MINT_ADDRESS, TAKE_PROFIT_SELL_SCHEDULE

# Solana-py and Solders specific imports
from solders.pubkey import Pubkey as PublicKey
from solana.rpc.api import Client # For type hinting, actual client passed in
from solders.transaction import VersionedTransaction as Transaction # Changed to VersionedTransaction
from solders.instruction import Instruction as TransactionInstruction, AccountMeta
from spl.token.instructions import get_associated_token_address
from spl.token.constants import TOKEN_PROGRAM_ID as SPL_TOKEN_PROGRAM_ID_CONSTANT
from solders.keypair import Keypair # For temporary delegate

logger = logging.getLogger(__name__)

# Raydium Liquidity Pool V4 Program ID
RAYDIUM_LP_V4_PROGRAM_ID = PublicKey.from_string("675kPX9MHTjS2zt1qfr1ci8rCPwQU4ayq5gAuzSBAobr")
# Wrapped SOL Mint
WSOL_MINT = PublicKey.from_string(SOL_MINT_ADDRESS)

# Known token mint addresses for convenience (can be moved to config or a constants file)
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
RAY_MINT = "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"


def generate_phantom_sign_and_send_tx_deep_link(
    serialized_tx_base58: str,
    redirect_url: str = "https://phantom.app/ul/v1/transaction-sent"
) -> str:
    encoded_transaction = urllib.parse.quote(serialized_tx_base58)
    encoded_redirect_link = urllib.parse.quote(redirect_url)
    deep_link = f"phantom://v1/signAndSendTransaction?transaction={encoded_transaction}&redirect_link={encoded_redirect_link}"
    return deep_link

def prepare_buy_transaction(
    solana_client: Client,
    new_token_mint_address_str: str,
    buyer_public_key_str: str,
    sol_amount_lamports: int
) -> tuple[str, str | None]:
    logger.info(f"Preparing buy tx for {new_token_mint_address_str} by {buyer_public_key_str} for {sol_amount_lamports} lamports.")
    try:
        buyer_pk = PublicKey.from_string(buyer_public_key_str)
        token_mint_pk = PublicKey.from_string(new_token_mint_address_str)

        PLACEHOLDER_AMM_ID = PublicKey.from_string("11111111111111111111111111111111111111111111")
        PLACEHOLDER_AMM_AUTHORITY = PublicKey.from_string("5Q544fKrFoe6tsEbD7S8sodEJiXbrgoGGu8audPNvpiw")
        PLACEHOLDER_AMM_OPEN_ORDERS = PublicKey.from_string("22222222222222222222222222222222222222222222")
        PLACEHOLDER_AMM_COIN_VAULT = PublicKey.from_string("33333333333333333333333333333333333333333333")
        PLACEHOLDER_AMM_PC_VAULT = PublicKey.from_string("44444444444444444444444444444444444444444444")
        PLACEHOLDER_SERUM_PROGRAM_ID = PublicKey.from_string("9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin")
        PLACEHOLDER_SERUM_MARKET_ID = PublicKey.from_string("55555555555555555555555555555555555555555555")
        PLACEHOLDER_SERUM_BIDS = PublicKey.from_string("66666666666666666666666666666666666666666666")
        PLACEHOLDER_SERUM_ASKS = PublicKey.from_string("77777777777777777777777777777777777777777777")
        PLACEHOLDER_SERUM_EVENT_QUEUE = PublicKey.from_string("88888888888888888888888888888888888888888888")
        PLACEHOLDER_SERUM_COIN_VAULT = PublicKey.from_string("99999999999999999999999999999999999999999999")
        PLACEHOLDER_SERUM_PC_VAULT = PublicKey.from_string("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
        PLACEHOLDER_SERUM_VAULT_SIGNER = PublicKey.from_string("BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")

        instructions = []
        user_wsol_ata = get_associated_token_address(buyer_pk, WSOL_MINT)
        user_new_token_ata = get_associated_token_address(buyer_pk, token_mint_pk)
        temp_delegate = Keypair()

        approve_instruction = TransactionInstruction( # Using solders.Instruction aliased
            program_id=SPL_TOKEN_PROGRAM_ID_CONSTANT,
            data=b'\x04' + sol_amount_lamports.to_bytes(8, 'le'), # spl-token approve instruction data with amount
            accounts=[
                AccountMeta(pubkey=user_wsol_ata, is_signer=False, is_writable=True),
                AccountMeta(pubkey=temp_delegate.pubkey(), is_signer=True, is_writable=False), # Delegate is a signer here
                AccountMeta(pubkey=buyer_pk, is_signer=True, is_writable=False), # Owner of source must sign
            ]
        )
        # Note: spl.token.instructions.approve() is a helper that creates this.
        # Using raw TransactionInstruction to show structure and ensure solders types.
        # The actual `approve` helper might be more robust.
        # For now, this matches the need for program_id, data, accounts.
        # Data for approve: instruction_type (1 byte = 4 for Approve), amount (8 bytes)
        # The spl.token.instructions.approve helper is more reliable.
        # Reverting to spl.token.instructions.approve for correctness of data construction:
        from spl.token.instructions import approve as spl_approve
        approve_instruction = spl_approve(
            program_id=SPL_TOKEN_PROGRAM_ID_CONSTANT,
            source=user_wsol_ata,
            delegate=temp_delegate.pubkey(),
            owner=buyer_pk,
            amount=sol_amount_lamports
        )
        instructions.append(approve_instruction)

        min_amount_out_tokens = 0
        swap_instruction_data = b'\x09' + sol_amount_lamports.to_bytes(8, 'le') + min_amount_out_tokens.to_bytes(8, 'le') \
                               + b"PLACEHOLDER_AMM_ID" # Ensure this is bytes

        accounts_meta = [
            AccountMeta(pubkey=SPL_TOKEN_PROGRAM_ID_CONSTANT, is_signer=False, is_writable=False),
            AccountMeta(pubkey=PLACEHOLDER_AMM_ID, is_signer=False, is_writable=True),
            AccountMeta(pubkey=PLACEHOLDER_AMM_AUTHORITY, is_signer=False, is_writable=False),
            AccountMeta(pubkey=PLACEHOLDER_AMM_OPEN_ORDERS, is_signer=False, is_writable=True),
            AccountMeta(pubkey=PLACEHOLDER_AMM_COIN_VAULT, is_signer=False, is_writable=True),
            AccountMeta(pubkey=PLACEHOLDER_AMM_PC_VAULT, is_signer=False, is_writable=True),
            AccountMeta(pubkey=PLACEHOLDER_SERUM_PROGRAM_ID, is_signer=False, is_writable=False),
            AccountMeta(pubkey=PLACEHOLDER_SERUM_MARKET_ID, is_signer=False, is_writable=True),
            AccountMeta(pubkey=PLACEHOLDER_SERUM_BIDS, is_signer=False, is_writable=True),
            AccountMeta(pubkey=PLACEHOLDER_SERUM_ASKS, is_signer=False, is_writable=True),
            AccountMeta(pubkey=PLACEHOLDER_SERUM_EVENT_QUEUE, is_signer=False, is_writable=True),
            AccountMeta(pubkey=PLACEHOLDER_SERUM_COIN_VAULT, is_signer=False, is_writable=True),
            AccountMeta(pubkey=PLACEHOLDER_SERUM_PC_VAULT, is_signer=False, is_writable=True),
            AccountMeta(pubkey=PLACEHOLDER_SERUM_VAULT_SIGNER, is_signer=False, is_writable=False),
            AccountMeta(pubkey=user_wsol_ata, is_signer=False, is_writable=True),
            AccountMeta(pubkey=user_new_token_ata, is_signer=False, is_writable=True),
            AccountMeta(pubkey=temp_delegate.pubkey(), is_signer=True, is_writable=False)
        ]

        raydium_swap_instruction = TransactionInstruction(
            keys=accounts_meta,
            program_id=RAYDIUM_LP_V4_PROGRAM_ID,
            data=swap_instruction_data
        )
        instructions.append(raydium_swap_instruction)

        recent_blockhash_str = "11111111111111111111111111111111" # Placeholder
        try:
            blockhash_resp = solana_client.get_latest_blockhash()
            if blockhash_resp.value.blockhash:
                 recent_blockhash_str = str(blockhash_resp.value.blockhash)
            logger.info(f"Using recent blockhash: {recent_blockhash_str}")
        except Exception as e:
            logger.error(f"Failed to get recent blockhash, using placeholder: {e}")
            # Using placeholder if RPC call fails

        tx = Transaction(recent_blockhash=PublicKey.from_string(recent_blockhash_str), fee_payer=buyer_pk)
        tx.add(*instructions)
        tx.sign_partial(temp_delegate)

        serialized_tx = tx.serialize(verify_signatures=False)
        base58_encoded_tx = base58.b58encode(serialized_tx).decode('utf-8')

        instructional_text = (
            f"Action: Buy token `{new_token_mint_address_str}` with approx. {sol_amount_lamports / 1e9:.4f} SOL (via wSOL).\n"
            f"This is an EXPERIMENTAL transaction for Raydium. Pool details are placeholders.\n"
            f"The temporary delegate for this transaction was: {temp_delegate.pubkey()}"
        )
        deep_link = generate_phantom_sign_and_send_tx_deep_link(base58_encoded_tx)
        final_text = f"{instructional_text}\n\n**Execute with Phantom (EXPERIMENTAL):** {deep_link}\n\n**Raw TX (Conceptual & EXPERIMENTAL):** `{base58_encoded_tx}`"

        logger.info(f"Prepared conceptual Raydium buy TX for {new_token_mint_address_str}. Delegate: {temp_delegate.pubkey()}")
        return (final_text, base58_encoded_tx)

    except Exception as e:
        logger.error(f"Error in prepare_buy_transaction: {e}", exc_info=True)
        error_text = f"Error preparing buy transaction for {new_token_mint_address_str}: {e}. This is experimental."
        return (error_text, None)

def check_take_profit_levels(
    token_mint_address: str,
    current_price_usd: float,
    bought_price_usd_per_token: float,
    last_notified_tp_level_percent: int | None
) -> tuple[int | None, float | None, str | None]: # Added float for sell_fraction
    if bought_price_usd_per_token <= 0:
        logger.debug(f"Invalid bought_price_usd_per_token: {bought_price_usd_per_token} for {token_mint_address}")
        return None, None, None

    profit_percent = ((current_price_usd - bought_price_usd_per_token) / bought_price_usd_per_token) * 100.0
    logger.debug(f"Token: {token_mint_address}, Buy: ${bought_price_usd_per_token:.4f}, Current: ${current_price_usd:.4f}, Profit: {profit_percent:.2f}%")

    new_highest_achieved_level: int | None = None
    sorted_tp_levels = sorted(TAKE_PROFIT_LEVELS_PERCENTAGES)

    for level_percent in sorted_tp_levels:
        if profit_percent >= level_percent:
            if last_notified_tp_level_percent is None or level_percent > last_notified_tp_level_percent:
                if new_highest_achieved_level is None or level_percent > new_highest_achieved_level:
                    new_highest_achieved_level = int(level_percent)
        else:
            break

    if new_highest_achieved_level is not None:
        sell_fraction = TAKE_PROFIT_SELL_SCHEDULE.get(float(new_highest_achieved_level)) # Ensure key is float

        if sell_fraction is not None:
            message = (
                f"📈 **Take Profit Alert** for token `{token_mint_address}`!\n"
                f"Current profit: **+{profit_percent:.2f}%** (Target Reached: **+{new_highest_achieved_level}%**)\n"
                f"Bought at (USD): ${bought_price_usd_per_token:.4f}\n"
                f"Current Price (USD): ${current_price_usd:.4f}\n"
                f"Consider selling **{sell_fraction*100:.0f}%** of your holdings for this trade."
            )
        else: # TP level hit, but no specific sell percentage defined for it in schedule
            message = (
                f"📈 **Price Alert** for token `{token_mint_address}`!\n"
                f"Current profit: **+{profit_percent:.2f}%** (Target Reached: **+{new_highest_achieved_level}%**)\n"
                f"Bought at (USD): ${bought_price_usd_per_token:.4f}\n"
                f"Current Price (USD): ${current_price_usd:.4f}"
            )

        logger.info(f"TP Level {new_highest_achieved_level}% hit for {token_mint_address} (Profit: {profit_percent:.2f}%). Sell fraction: {sell_fraction}")
        return new_highest_achieved_level, sell_fraction, message

    return None, None, None

def calculate_profit(bought_price: float, current_price: float, amount: float) -> float:
    if amount == 0:
        return 0.0
    return (current_price - bought_price) * amount

def get_current_token_price(token_mint_address: str, vs_token: str = "USDC") -> float | None:
    api_url = f"https://price.jup.ag/v4/price?ids={token_mint_address}&vsToken={vs_token}"
    logger.info(f"Fetching price for {token_mint_address} vs {vs_token} from Jupiter API: {api_url}")
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        response_data = response.json()
        logger.debug(f"Jupiter API response: {response_data}")
        if 'data' in response_data and token_mint_address in response_data['data']:
            price_data = response_data['data'][token_mint_address]
            price = price_data.get('price')
            if price is not None:
                logger.info(f"Price for {token_mint_address} ({price_data.get('mintSymbol', 'N/A')}) vs {vs_token}: {price}")
                return float(price)
            else:
                logger.warning(f"Price data not found for {token_mint_address} in Jupiter response. Full data: {price_data}")
                return None
        else:
            logger.warning(f"Token {token_mint_address} not found in Jupiter API response data. Full response: {response_data}")
            return None
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred while fetching price for {token_mint_address}: {http_err} - Response: {response.text if 'response' in locals() else 'No response object'}")
        return None
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request error occurred while fetching price for {token_mint_address}: {req_err}")
        return None
    except ValueError as json_err:
        logger.error(f"JSON decoding error while fetching price for {token_mint_address}: {json_err} - Response: {response.text if 'response' in locals() else 'No response object'}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching price for {token_mint_address}: {e}", exc_info=True)
        return None

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    print("--- Testing Solana Trading Actions ---")

    mock_tx_str_for_link_test = "AVasteOfTimeAndMoneyButItIsAMockTransactionStringAnyway..."
    link = generate_phantom_sign_and_send_tx_deep_link(mock_tx_str_for_link_test)
    print(f"\nGenerated Phantom link: {link}")

    print("\n--- Testing prepare_buy_transaction (Conceptual) ---")
    mock_buyer_pk_str = str(Keypair().pubkey())
    mock_token_mint_str = "TESTMINTADDRESS1234567890123456789012345"
    mock_sol_lamports = int(0.01 * 1e9)

    class MockSolanaClient: # Simplified mock
        def get_latest_blockhash(self, commitment=None):
            class MockRpcResponseContext: slot = 1
            class MockBlockhash: blockhash = "11111111111111111111111111111111"; last_valid_block_height = 100
            class MockRpcResponse: value = MockBlockhash(); context = MockRpcResponseContext()
            return MockRpcResponse()

    mock_client = MockSolanaClient()
    instructional_text, base58_tx = prepare_buy_transaction(
        solana_client=mock_client,
        new_token_mint_address_str=mock_token_mint_str,
        buyer_public_key_str=mock_buyer_pk_str,
        sol_amount_lamports=mock_sol_lamports
    )
    print(f"\nInstructional Text:\n{instructional_text}")
    print(f"\nBase58 Serialized TX (Conceptual):\n{base58_tx}")

    print(f"\nCalculated profit: {calculate_profit(1.0, 1.5, 10)}")
    print(f"USDC vs USDC price: {get_current_token_price(USDC_MINT, vs_token='USDC')}")
    print(f"RAY vs USDC price: {get_current_token_price(RAY_MINT, vs_token='USDC')}")
    print(f"SOL vs USDC price: {get_current_token_price(SOL_MINT_ADDRESS, vs_token='USDC')}")

    print("\nMinimal __main__ in trading.py. Run unit tests for detailed checks.")
    print("Example: python -m unittest tests.solana_actions.test_trading")
    print("\nAll trading action tests in __main__ finished.")
