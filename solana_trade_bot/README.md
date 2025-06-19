# Solana Memecoin Sniper & Trading Bot

## Project Description

This project is a Python-based Telegram bot designed to monitor specific Solana developer wallets for new token mints. When a new mint is detected that matches certain criteria (not yet fully implemented), it notifies users via Telegram. Users can then receive a conceptual (experimental) Phantom deep link to attempt a quick purchase of the newly minted token. The bot also includes features for users to link their own Solana wallets, set buy preferences, and track conceptual profits on trades initiated through the bot.

**Disclaimer:** This bot is experimental software. Trading memecoins is highly risky. Use this bot at your own risk. The information and tools provided by this bot do not constitute financial advice. Always do your own research (DYOR) before making any investment decisions.

## Scalability & Performance Considerations

**Important:** The current version of this bot is designed primarily for **single-user operation or very low concurrency levels.** It is **not suitable** for deployment to a large user base (e.g., hundreds or thousands of users) without significant architectural changes.

Key limitations include:

*   **Database:** Uses SQLite, which is file-based and not designed for high concurrent read/write loads. Scaling to many users would require migrating to a more robust database system like PostgreSQL or MySQL.
*   **API Rate Limits:** Makes direct calls to public Solana RPC endpoints and other third-party APIs (e.g., Jupiter for price data). These public endpoints have rate limits that would be quickly exhausted under the load of many users or very frequent polling for many wallets.
*   **Request Handling:** Lacks sophisticated request management, such as request queues, caching for API calls, or optimized handling of Solana RPC calls.
*   **Concurrency Model:** While `asyncio` is used (including an asynchronous queue and worker system for sending new mint notifications to improve responsiveness), scaling to a large number of simultaneous users and background tasks would likely require a more robust architecture, potentially involving dedicated background workers (e.g., Celery) for tasks like mass notifications, intensive database operations, or managing a large number of individual user monitoring loops.

**Attempting to use the bot with a large number of users in its current state will likely lead to severe performance issues, API rate-limiting, and database contention.** Significant re-architecture and infrastructure considerations (e.g., private RPC nodes, database scaling solutions) are necessary for high-load scenarios.

## Features

*   **Developer Wallet Monitoring:** Continuously monitors a list of specified Solana developer wallets for new transaction activity.
*   **New Mint Detection:** Identifies potential new SPL token mint transactions using on-chain data. (Currently checks for `InitializeMint` / `InitializeMint2` instructions).
*   **Telegram Notifications:** Alerts users via Telegram when a new token mint is detected from a monitored developer wallet.
*   **User Wallet Linking:** Allows users to link their Solana wallet address to the bot.
*   **Buy Preferences:** Users can set a preferred SOL amount for potential buys.
*   **Conceptual Buy Transactions:**
    *   Generates a conceptual Raydium swap transaction for a SOL-to-token purchase.
    *   Provides a Phantom deep link for the user to sign and send this (experimental) transaction.
*   **Buy Confirmation:** Users can confirm their actual purchase details (tokens bought, SOL spent) to the bot.
*   **Profit Tracking (Conceptual):**
    *   Displays a list of user's trades initiated via the bot.
    *   Calculates and shows conceptual profit/loss on confirmed buys using live market prices from Jupiter API for the token and SOL.
*   **Take-Profit Notifications:**
    *   Alerts users when their confirmed trades reach predefined percentage profit levels (defined in `TAKE_PROFIT_LEVELS_PERCENTAGES`).
    *   **Configurable Sell Suggestions:** Suggests a percentage of current token holdings to sell at each take-profit level, based on the `TAKE_PROFIT_SELL_SCHEDULE` configuration.
*   **User-Controlled Trading Notifications:** Enable or disable receiving buy notifications for new mints via `/trade_on` and `/trade_off` commands. Trading status is ON by default for new users.
*   **Database Persistence:** Uses SQLite to store user settings (including trading status), monitored mints, and trade lifecycle information.
*   **Unit Tests:** Includes a basic testing framework.

## Prerequisites

*   Python 3.10+
*   Access to a Solana RPC endpoint (public or private).
*   A Telegram Bot Token.

## Setup Instructions

1.  **Clone the Repository:**
    ```bash
    git clone <repository_url>
    cd solana-memecoin-bot
    ```
    *(Replace `<repository_url>` with the actual URL of this repository. The directory name might be `solana_trade_bot` based on current structure).*

2.  **Navigate to Project Directory:**
    The primary project code is inside the `solana_trade_bot` subdirectory if you cloned a parent directory.
    ```bash
    cd solana_trade_bot
    ```
    *(If you cloned directly into `solana_trade_bot`, you might already be there).*

3.  **Create a Virtual Environment (Recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
    *(On Windows, use `venv\Scripts\activate`)*

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

All primary configurations are located in `solana_trade_bot/core/config.py`. You **must** edit this file before running the bot.

Key configuration variables:

*   `TELEGRAM_BOT_TOKEN` (in `solana_trade_bot/bot/config.py`): Your Telegram Bot API token. **This is mandatory.**
    *Example: `TELEGRAM_BOT_TOKEN = "1234567890:ABCDEFGHIJKLMN0PQRSTUVWXYZ1234567890"`*
*   `DEV_WALLETS_TO_TRACK` (in `solana_trade_bot/core/config.py`): A Python list of Solana public key strings. These are the developer/deployer wallets the bot will monitor for new mints.
    *Example: `DEV_WALLETS_TO_TRACK = ["DevWalletAddress1...", "DevWalletAddress2..."]`*
*   `SOLANA_RPC_URL` (in `solana_trade_bot/core/config.py`): The HTTP URL for your Solana RPC node. Public nodes can be rate-limited. Used for fetching transaction details, token information, and market data.
    *Example: `SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"`*
*   `SOLANA_WS_URL` (in `solana_trade_bot/core/config.py`): The WebSocket URL for your Solana RPC node. Used for real-time subscription to logs for new mint detection.
    *Example: `SOLANA_WS_URL = "wss://api.mainnet-beta.solana.com"`*
*   `MIN_BUY_SOL` / `MAX_BUY_SOL` (in `solana_trade_bot/core/config.py`): Minimum and maximum SOL amount a user can set for a single buy notification.
*   `TAKE_PROFIT_POLLING_INTERVAL_SECONDS` (in `solana_trade_bot/core/config.py`): How often (in seconds) the bot checks for take-profit conditions on confirmed trades. Default is `300` (5 minutes).
*   `TAKE_PROFIT_LEVELS_PERCENTAGES` (in `solana_trade_bot/core/config.py`): A list of profit percentages (e.g., `[25.0, 50.0, 100.0, 200.0]`) that trigger take-profit alerts.
*   `TAKE_PROFIT_SELL_SCHEDULE` (in `solana_trade_bot/core/config.py`): A dictionary defining what percentage of current holdings to suggest selling when a take-profit level is triggered.
    *Example: `{25.0: 0.30, 50.0: 0.50, 100.0: 1.0}` means at 25% profit, sell 30% of tokens; at 50% profit, sell 50% of remaining tokens for that trade; at 100% profit, sell all remaining tokens.
    *If a level in `TAKE_PROFIT_LEVELS_PERCENTAGES` is not a key in `TAKE_PROFIT_SELL_SCHEDULE`, the notification will be a price alert without a specific sell suggestion.*
*   `NUM_NOTIFICATION_WORKERS` (in `solana_trade_bot/core/config.py`): Number of concurrent worker tasks that process and send Telegram notifications for new mints. This helps in managing the load of sending multiple messages. Default is `3`.
*   `DATABASE_FILE` (in `solana_trade_bot/core/config.py`): Name of the SQLite database file. Defaults to `solana_bot.db`.
*   `SOL_MINT_ADDRESS` / `USDC_MINT_ADDRESS` (in `solana_trade_bot/core/config.py`): Mint addresses for Wrapped SOL and USDC, used for price conversions.
*   **Note on User Defaults:** New users who `/start` the bot will have trading notifications ON by default. They can use `/trade_off` to disable them.

## Database Initialization

The bot uses an SQLite database (`solana_bot.db` by default) to store user information, trades, and monitored mints. The `users` table includes an `is_trading_enabled` column (`BOOLEAN DEFAULT True`) to manage each user's preference for receiving new mint buy notifications.

*   **Automatic Initialization:** The database and necessary tables (including the `is_trading_enabled` column with migration for existing databases) are automatically created or verified when the bot starts up (`python solana_trade_bot/bot/main.py`).
*   **Manual Initialization:** You can also initialize the database manually by running:
    ```bash
    python solana_trade_bot/core/db.py
    ```
    *(Ensure your current working directory is the project root `/app` or adjust path accordingly if running from within `solana_trade_bot` dir, e.g. `python core/db.py`)*

*   **Local PostgreSQL Setup for Development/Testing (Optional):**
    If you intend to use or test with PostgreSQL (`DATABASE_TYPE = "postgres"` in `core/config.py`), you'll need a running PostgreSQL instance. Docker is recommended for easy setup:
    1.  **Run PostgreSQL in Docker:**
        ```bash
        docker run --name solana-bot-postgres \
          -e POSTGRES_USER=your_pg_user \
          -e POSTGRES_PASSWORD=your_pg_password \
          -e POSTGRES_DB=solana_bot_db \
          -p 5432:5432 \
          -d postgres
        ```
        **Note:** Replace `your_pg_user`, `your_pg_password`, and `solana_bot_db` with the actual values you've set in your `solana_trade_bot/core/config.py` file for `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DBNAME`.
    2.  **Connect via `psql` (optional, for verification):**
        ```bash
        docker exec -it solana-bot-postgres psql -U your_pg_user -d solana_bot_db
        ```
        Once connected, you can use commands like:
        *   `\dt` to list tables (after running `python solana_trade_bot/core/pg_db.py` or the bot to initialize the schema).
        *   `SELECT * FROM users;` to inspect data.
        *   `\q` to quit `psql`.
    3.  **Initialize Schema for PostgreSQL:**
        If using PostgreSQL for the first time, after starting the Docker container and ensuring your `core/config.py` points to it with `DATABASE_TYPE = "postgres"`, run:
        ```bash
        python solana_trade_bot/core/pg_db.py
        ```
        Or simply start the bot, which will also attempt to initialize the configured database type.

## Running the Bot

1.  Ensure all configurations in `solana_trade_bot/core/config.py` and `solana_trade_bot/bot/config.py` are correctly set.
2.  From the project root directory (e.g., `/app` if that's where `solana_trade_bot` directory and `test_runner.py` are):
    ```bash
    python -m solana_trade_bot.bot.main
    ```
    Or, if you are inside the `solana_trade_bot` directory:
    ```bash
    python bot/main.py
    ```

**Production Deployment (Conceptual):**
For production, running the bot directly via `python` is not recommended for long-term stability. Consider using process managers like:
*   `systemd` (for Linux systems)
*   `supervisor`
*   Docker containers

These tools can handle automatic restarts on crashes and manage logging more effectively.

## Using the Bot (Telegram Commands)

Once the bot is running and you've started a chat with it on Telegram:

*   `/start`: Initializes your interaction with the bot and registers you in the database.
*   `/help`: Displays a list of available commands and their usage.
*   `/link_wallet <your_solana_address>`: Links your Solana wallet address to the bot for tracking and personalized actions. Send the command without an address to unlink.
*   `/my_wallet`: Shows your currently linked Solana wallet address.
*   `/set_buy_amount <SOL_amount>`: Sets your preferred SOL amount for buy notifications (e.g., `/set_buy_amount 0.1`). Send without an amount to clear.
*   `/get_buy_amount`: Shows your currently set preferred buy amount in SOL.
*   `/view_profits`: Displays a conceptual profit/loss summary for trades you've confirmed through the bot.
*   `/confirm_buy <trade_id> <tokens_bought> <sol_spent>`: Confirms the details of a purchase you made after a bot notification. The `trade_id` is provided in the notification.
    *Example: `/confirm_buy 123 1000000 0.5` (bought 1,000,000 tokens for 0.5 SOL)*
*   `/confirm_sell <trade_id> <tokens_sold> <sol_received>`: (Conceptual) Confirms details of a sale. Not fully implemented for P/L updates yet.
*   `/trade_on`: Enables receiving buy notifications for new token mints.
*   `/trade_off`: Disables receiving buy notifications for new token mints.
*   `/trade_status`: Checks if your buy notifications are currently ON or OFF.

**Note on Notifications:**
*   **New Mint Alerts:** Include the token mint address, the developer wallet source, a `trade_id` for `/confirm_buy`, and an experimental Phantom deep link for a quick buy.
*   **Take-Profit Alerts:** Inform you when a confirmed trade reaches a profit target defined in `TAKE_PROFIT_LEVELS_PERCENTAGES`. If a corresponding sell percentage is set in `TAKE_PROFIT_SELL_SCHEDULE`, the alert will also suggest selling that portion of your holdings for that trade.

## Testing

The project includes unit tests to verify functionality.

1.  **Ensure Dependencies:** Make sure all project dependencies and test dependencies (if any specific ones are added later) are installed.
2.  **Set PYTHONPATH:** From the project root directory (e.g., `/app` which contains `solana_trade_bot` and `tests` directories):
    ```bash
    export PYTHONPATH=/app:$PYTHONPATH
    ```
    *(Adjust `/app` if your project root is elsewhere relative to where you run the command).*
3.  **Run All Tests:**
    A `test_runner.py` script is provided at the project root:
    ```bash
    python test_runner.py
    ```
    Alternatively, use the `unittest` module:
    ```bash
    python -m unittest discover -s tests -v
    ```

4.  **Run Specific Test Files or Classes/Methods:**
    ```bash
    python -m unittest -v tests.solana_actions.test_trading
    python -m unittest -v tests.core.test_monitor.TestMonitorLogic.test_take_profit_flow
    ```

**Known Test Issues:**
*   `tests.core.test_monitor.TestMonitorLogic.test_new_mint_processing_flow`: This test is currently skipped (`self.skipTest(...)`) due to persistent `TypeError` issues related to mock argument injection with a large stack of `@patch` decorators on an `async def` method using the custom `async_test` wrapper. The problem appears to be one of the patchers not correctly injecting its argument, leading to an argument count mismatch.
    *   **Diagnostic Suggestion:** The issue was narrowed down to the interaction between `@patch` and the `async_test` decorator.
    *   **Suggested Fix for Future Work:** Refactor `TestMonitorLogic` to inherit from `unittest.IsolatedAsyncioTestCase` (available Python 3.8+) which natively supports `async def` test methods and should work more reliably with `@patch` decorators. This would remove the need for the custom `async_test` wrapper.

## Disclaimer

*   This bot is for educational and experimental purposes only.
*   Trading cryptocurrencies, especially memecoins, is extremely volatile and risky. You can lose all of your investment.
*   This bot does NOT provide financial advice. Any actions taken based on its notifications or features are solely your responsibility.
*   The developers and contributors are not liable for any financial losses or other damages incurred from using this software.
*   Always do your own research (DYOR) and understand the risks before trading.
*   The transaction construction features are highly conceptual and may not produce valid or optimal transactions for real use. Always verify transactions in your wallet before signing.
