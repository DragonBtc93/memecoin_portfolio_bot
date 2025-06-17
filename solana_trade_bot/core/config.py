# List of developer wallet addresses to track for new token mints.
# IMPORTANT: Replace these placeholders with actual Solana public key strings.
DEV_WALLETS_TO_TRACK = [
    "ReplaceWithDevWalletAddress1", # Example: A known developer or project wallet
    "ReplaceWithDevWalletAddress2", # Example: Another wallet of interest
    # Add more wallet addresses here
]

# Solana Network Configuration
# Default to Mainnet Beta. Consider using environment variables for sensitive data or for switching networks.
SOLANA_RPC_URL: str = "https://api.mainnet-beta.solana.com"
# Example Testnet RPC: "https://api.testnet.solana.com"
# Example Devnet RPC:  "https://api.devnet.solana.com"

# User Buy Order Configuration
# Minimum and maximum SOL amount a user can configure for a single buy order.
MIN_BUY_SOL: float = 0.01 # Example: Minimum 0.01 SOL
MAX_BUY_SOL: float = 5.0  # Example: Maximum 5 SOL

# Take Profit Configuration
# Percentage gains at which users might be notified to consider taking profits.
# These are relative to their conceptual bought price.
TAKE_PROFIT_LEVELS_PERCENTAGES: list[float] = [
    25.0,  # Notify at +25% gain
    50.0,  # Notify at +50% gain
    100.0, # Notify at +100% gain (2x)
    200.0, # Notify at +200% gain (3x)
]

# Other potential configurations (examples):
DATABASE_FILE: str = "solana_bot.db" # SQLite database file
# PRICE_API_ENDPOINT: str = "https://api.jup.ag/v4/" # Example Jupiter API for prices
# LOG_LEVEL: str = "INFO"
