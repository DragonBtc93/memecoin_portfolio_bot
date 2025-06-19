import unittest
import psycopg2 # To catch specific PG errors if needed, and for connection type
from unittest.mock import patch, MagicMock

# Import functions to be tested directly from solana_trade_bot.core.pg_db
from solana_trade_bot.core.pg_db import (
    init_db_pg,
    upsert_user_settings_pg,
    get_user_trading_status_pg,
    get_user_pg,
    get_pg_connection_from_pool, # Updated for connection pooling
    put_pg_connection_to_pool,   # Updated for connection pooling
    get_user_linked_wallet_pg,
    get_user_buy_amount_pg
)
# Import config to check if default credentials are used (to skip tests if so)
from solana_trade_bot.core import config as core_config

# Conditional skipping of tests if default PG credentials are used
skip_if_default_pg_credentials = unittest.skipIf(
    core_config.POSTGRES_USER == "your_pg_user" or core_config.POSTGRES_PASSWORD == "your_pg_password",
    "PostgreSQL default credentials are used in config; skipping PG DB tests."
)

@skip_if_default_pg_credentials
class TestPgUserTradingStatus(unittest.TestCase):

    def _clear_tables(self, conn):
        """Helper to clear tables before a test (or after)."""
        with conn.cursor() as cur:
            # Truncate tables in an order that respects foreign keys, or disable triggers.
            # For now, only users table is primarily tested for insert/update.
            # If testing trades, trades should be truncated first.
            cur.execute("TRUNCATE TABLE users RESTART IDENTITY CASCADE;") # CASCADE will also truncate dependent tables like trades
            # cur.execute("TRUNCATE TABLE trades RESTART IDENTITY CASCADE;")
            # cur.execute("TRUNCATE TABLE monitored_mints RESTART IDENTITY CASCADE;")
        conn.commit()

    def setUp(self):
        """Set up a connection and initialize schema in the test PostgreSQL database."""
        try:
            # Initialize schema - this should be idempotent
            init_db_pg()

            # Get a connection to clear tables for test isolation
            self.conn = get_pg_connection_from_pool()
            self._clear_tables(self.conn)
        except psycopg2.Error as e:
            self.skipTest(f"Skipping PostgreSQL tests: Cannot connect to or initialize PG database: {e}")
        except Exception as e: # Catch any other setup errors
            self.skipTest(f"Skipping PostgreSQL tests due to other setup error: {e}")


    def tearDown(self):
        """Return the connection to the pool after each test."""
        if hasattr(self, 'conn') and self.conn:
            # Clear tables again to leave DB clean after tests if desired
            # self._clear_tables(self.conn)
            put_pg_connection_to_pool(self.conn)
            self.conn = None # Ensure it's not accidentally reused

    def test_default_trading_status_on_new_user_pg(self):
        """Test that a new PG user gets is_trading_enabled=True by default on insert."""
        chat_id = 2001
        upsert_user_settings_pg(chat_id, solana_address="wallet_new_default_pg")

        status = get_user_trading_status_pg(chat_id)
        self.assertTrue(status, "New PG user should have trading_enabled=True by default on first upsert.")

        user = get_user_pg(chat_id)
        self.assertIsNotNone(user)
        self.assertEqual(user['is_trading_enabled'], True, "DB value should be True.") # PG returns bool

    def test_set_trading_status_on_off_pg(self):
        """Test setting PG trading status explicitly ON and OFF."""
        chat_id = 2002

        upsert_user_settings_pg(chat_id, solana_address="wallet_on_off_pg", is_trading_enabled=True)
        self.assertTrue(get_user_trading_status_pg(chat_id), "Initial should be True.")

        upsert_user_settings_pg(chat_id, is_trading_enabled=False)
        self.assertFalse(get_user_trading_status_pg(chat_id), "Trading status should be False after setting to False.")
        user = get_user_pg(chat_id)
        self.assertEqual(user['is_trading_enabled'], False)

        upsert_user_settings_pg(chat_id, is_trading_enabled=True)
        self.assertTrue(get_user_trading_status_pg(chat_id), "Trading status should be True after setting to True.")
        user = get_user_pg(chat_id)
        self.assertEqual(user['is_trading_enabled'], True)

    def test_get_trading_status_non_existent_user_pg(self):
        """Test get_user_trading_status_pg for a non-existent user should return False."""
        chat_id = 999999 # Assumed not in DB
        status = get_user_trading_status_pg(chat_id)
        self.assertFalse(status, "Trading status for a non-existent PG user should default to False.")

    def test_upsert_new_user_with_trading_false_pg(self):
        """Test inserting a new PG user with is_trading_enabled explicitly set to False."""
        chat_id = 2005
        upsert_user_settings_pg(chat_id, solana_address="wallet_trade_false_pg", is_trading_enabled=False)
        self.assertFalse(get_user_trading_status_pg(chat_id), "New PG user inserted with trading_enabled=False should have status False.")
        user = get_user_pg(chat_id)
        self.assertIsNotNone(user)
        self.assertEqual(user['is_trading_enabled'], False)

    def test_pg_upsert_only_sol_address_preserves_settings(self):
        """Test updating only sol_address preserves other settings for PG user."""
        chat_id = 2006
        upsert_user_settings_pg(chat_id, solana_address="pg_wallet1", buy_amount_sol=0.7, is_trading_enabled=False)

        upsert_user_settings_pg(chat_id, solana_address="pg_wallet2_updated") # Only update address

        user = get_user_pg(chat_id)
        self.assertEqual(user['linked_solana_address'], "pg_wallet2_updated")
        self.assertEqual(user['buy_amount_sol'], 0.7) # Should remain 0.7
        self.assertEqual(user['is_trading_enabled'], False) # Should remain False

    def test_pg_upsert_only_buy_amount_preserves_settings(self):
        """Test updating only buy_amount preserves other settings for PG user."""
        chat_id = 2007
        upsert_user_settings_pg(chat_id, solana_address="pg_wallet_buy", buy_amount_sol=0.8, is_trading_enabled=True)

        upsert_user_settings_pg(chat_id, buy_amount_sol=0.9) # Only update buy amount

        user = get_user_pg(chat_id)
        self.assertEqual(user['linked_solana_address'], "pg_wallet_buy")
        self.assertEqual(user['buy_amount_sol'], 0.9)
        self.assertEqual(user['is_trading_enabled'], True)

    def test_pg_upsert_only_trading_status_preserves_settings(self):
        """Test updating only trading_status preserves other settings for PG user."""
        chat_id = 2008
        upsert_user_settings_pg(chat_id, solana_address="pg_wallet_trade_status", buy_amount_sol=1.1, is_trading_enabled=True)

        upsert_user_settings_pg(chat_id, is_trading_enabled=False) # Only update trading status

        user = get_user_pg(chat_id)
        self.assertEqual(user['linked_solana_address'], "pg_wallet_trade_status")
        self.assertEqual(user['buy_amount_sol'], 1.1)
        self.assertEqual(user['is_trading_enabled'], False)


if __name__ == '__main__':
    # This allows running this test file directly if PG is configured.
    # Note: The skip_if_default_pg_credentials decorator will apply.
    unittest.main()


@skip_if_default_pg_credentials
class TestPgTradesTable(unittest.TestCase):

    def setUp(self):
        try:
            init_db_pg() # Ensure schema exists
            self.conn = get_pg_connection_from_pool()
            with self.conn.cursor() as cur:
                # Clear tables in order respecting FK constraints, or use CASCADE
                cur.execute("TRUNCATE TABLE trades RESTART IDENTITY CASCADE;")
                cur.execute("TRUNCATE TABLE users RESTART IDENTITY CASCADE;") # Also clears users for FK
            self.conn.commit()
            # Add a dummy user for FK constraints in trades table
            upsert_user_settings_pg(1, "dummy_wallet_for_trades", 0.1, True)
        except psycopg2.Error as e:
            self.skipTest(f"Skipping PostgreSQL Trades tests: Cannot connect/init PG DB: {e}")

    def tearDown(self):
        if hasattr(self, 'conn') and self.conn:
            put_pg_connection_to_pool(self.conn)
            self.conn = None # Ensure it's not accidentally reused

    def test_add_and_get_trade_notification_pg(self):
        trade_id = add_trade_notification_pg(1, "mint1", "dev1", "notified_buy")
        self.assertIsNotNone(trade_id)
        trade = get_trade_by_id_pg(trade_id)
        self.assertIsNotNone(trade)
        self.assertEqual(trade['chat_id'], 1)
        self.assertEqual(trade['token_mint_address'], "mint1")
        self.assertEqual(trade['status'], "notified_buy")

    def test_update_trade_on_buy_confirmation_pg(self):
        trade_id = add_trade_notification_pg(1, "mint2", "dev2")
        self.assertIsNotNone(trade_id)

        updated = update_trade_on_buy_confirmation_pg(trade_id, 1000.0, 0.5, 0.0005)
        self.assertTrue(updated)

        trade = get_trade_by_id_pg(trade_id)
        self.assertIsNotNone(trade)
        self.assertEqual(trade['status'], "confirmed_buy")
        self.assertEqual(trade['tokens_bought'], 1000.0)
        self.assertEqual(trade['sol_spent'], 0.5)
        self.assertEqual(trade['sol_price_at_buy'], 0.0005)
        self.assertIsNotNone(trade['buy_confirmed_at'])

    def test_get_user_trades_pg(self):
        upsert_user_settings_pg(2, "user2_wallet", 0.2, True) # Another user
        add_trade_notification_pg(1, "mint_A", "devA", "notified_buy")
        trade_id_B = add_trade_notification_pg(1, "mint_B", "devB", "notified_buy")
        update_trade_on_buy_confirmation_pg(trade_id_B, 500, 0.2, 0.0004) # status becomes 'confirmed_buy'
        add_trade_notification_pg(1, "mint_C", "devC", "sold_all") # Not an open trade
        add_trade_notification_pg(2, "mint_D_user2", "devD", "confirmed_buy") # Trade for another user

        open_trades_user1 = get_user_trades_pg(1, only_open=True)
        self.assertEqual(len(open_trades_user1), 1) # Only mint_B should be 'confirmed_buy'
        self.assertEqual(open_trades_user1[0]['token_mint_address'], "mint_B")

        all_trades_user1 = get_user_trades_pg(1, only_open=False)
        self.assertEqual(len(all_trades_user1), 3) # mint_A, mint_B, mint_C

        open_trades_user2 = get_user_trades_pg(2, only_open=True)
        self.assertEqual(len(open_trades_user2), 1)
        self.assertEqual(open_trades_user2[0]['token_mint_address'], "mint_D_user2")

    def test_update_trade_status_pg(self):
        trade_id = add_trade_notification_pg(1, "mint_status_test", "dev_status")
        self.assertIsNotNone(trade_id)

        updated = update_trade_status_pg(trade_id, "notified_tp1", 25)
        self.assertTrue(updated)
        trade = get_trade_by_id_pg(trade_id)
        self.assertEqual(trade['status'], "notified_tp1")
        self.assertEqual(trade['last_tp_notified_level'], 25)

        updated_again = update_trade_status_pg(trade_id, "sold_partial")
        self.assertTrue(updated_again)
        trade_again = get_trade_by_id_pg(trade_id)
        self.assertEqual(trade_again['status'], "sold_partial")
        self.assertEqual(trade_again['last_tp_notified_level'], 25) # Should remain if not updated


@skip_if_default_pg_credentials
class TestPgMonitoredMintsTable(unittest.TestCase):

    def setUp(self):
        try:
            init_db_pg() # Ensure schema exists
            self.conn = get_pg_connection_from_pool()
            with self.conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE monitored_mints RESTART IDENTITY CASCADE;")
            self.conn.commit()
        except psycopg2.Error as e:
            self.skipTest(f"Skipping PostgreSQL MonitoredMints tests: Cannot connect/init PG DB: {e}")

    def tearDown(self):
        if hasattr(self, 'conn') and self.conn:
            put_pg_connection_to_pool(self.conn)
            self.conn = None # Ensure it's not accidentally reused

    def test_add_and_get_monitored_mint_pg(self):
        mint_addr = "TestMintPG001"
        added1 = add_monitored_mint_pg(mint_addr, "DevWalletSourcePG", "TxSigPG001", "{'pool':'xyz'}")
        self.assertTrue(added1)

        mint_info = get_monitored_mint_pg(mint_addr)
        self.assertIsNotNone(mint_info)
        self.assertEqual(mint_info['dev_wallet_source'], "DevWalletSourcePG")
        self.assertEqual(mint_info['initial_liquidity_info'], "{'pool':'xyz'}")

        # Try adding the same mint again
        added2 = add_monitored_mint_pg(mint_addr, "AnotherDev", "AnotherTx")
        self.assertFalse(added2, "Adding the same mint address again should return False due to ON CONFLICT DO NOTHING if rowcount is 0")

        mint_info_after = get_monitored_mint_pg(mint_addr) # Should still be the first one
        self.assertEqual(mint_info_after['dev_wallet_source'], "DevWalletSourcePG")


    def test_update_mint_processed_time_pg(self):
        mint_addr = "TestMintPG002"
        add_monitored_mint_pg(mint_addr, "DevWalletSourcePG2", "TxSigPG002")

        mint_before = get_monitored_mint_pg(mint_addr)
        self.assertIsNotNone(mint_before)
        self.assertIsNone(mint_before['processed_by_bot_at'])

        updated = update_mint_processed_time_pg(mint_addr)
        self.assertTrue(updated)

        mint_after = get_monitored_mint_pg(mint_addr)
        self.assertIsNotNone(mint_after)
        self.assertIsNotNone(mint_after['processed_by_bot_at'])

        # Test update on non-existent mint
        updated_non_existent = update_mint_processed_time_pg("NonExistentMintAddressPG")
        self.assertFalse(updated_non_existent)
