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

# --- Database Configuration ---
DATABASE_TYPE: str = "sqlite" # Options: "sqlite", "postgres"

# SQLite Configuration (used if DATABASE_TYPE is "sqlite")
DATABASE_FILE: str = "solana_bot.db"

# PostgreSQL Connection Parameters (only used if DATABASE_TYPE is "postgres")
POSTGRES_HOST: str = "localhost"
POSTGRES_PORT: int = 5432
POSTGRES_USER: str = "your_pg_user"       # Replace with your PostgreSQL username
POSTGRES_PASSWORD: str = "your_pg_password" # Replace with your PostgreSQL password
POSTGRES_DBNAME: str = "solana_bot_db"    # Replace with your PostgreSQL database name
POSTGRES_POOL_MIN_CONN: int = 1
POSTGRES_POOL_MAX_CONN: int = 5 # Max connections in the pool

# Other potential configurations (examples):
TAKE_PROFIT_POLLING_INTERVAL_SECONDS: int = 300 # How often to check for take profits (e.g., 5 minutes)

# Common Token Mint Addresses
USDC_MINT_ADDRESS: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_MINT_ADDRESS: str = "So11111111111111111111111111111111111111112" # Wrapped SOL

# Defines what percentage of current holdings to suggest selling at each TP level.
# Format: {profit_percentage_trigger: percentage_of_tokens_to_sell}
# Example: At 25% profit, suggest selling 30% of current token amount.
# Keys should ideally align with values in TAKE_PROFIT_LEVELS_PERCENTAGES for clarity.
TAKE_PROFIT_SELL_SCHEDULE: dict[float, float] = {
    25.0: 0.30,  # At 25% profit, suggest selling 30%
    50.0: 0.50,  # At 50% profit, suggest selling 50% (of current holding for this trade)
    100.0: 1.0, # At 100% profit, suggest selling 100% (of current holding for this trade)
    # 200.0: 1.0, # Example: if 200% is also a TP level, you might also sell 100%
}

# PRICE_API_ENDPOINT: str = "https://api.jup.ag/v4/" # Example Jupiter API for prices
# LOG_LEVEL: str = "INFO"

NUM_NOTIFICATION_WORKERS: int = 3 # Number of concurrent workers processing notification queue

# --- WebSocket Monitor Configuration ---
SOLANA_WS_URL: str = "wss://api.mainnet-beta.solana.com" # Or your private RPC's WS endpoint
WS_RECONNECT_DELAY_SECONDS: int = 5 # Delay before attempting to reconnect on WS error
