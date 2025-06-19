import unittest
import psycopg2 # To catch specific PG errors if needed, and for connection type
from unittest.mock import patch, MagicMock

# Import functions to be tested directly from solana_trade_bot.core.pg_db
from solana_trade_bot.core.pg_db import (
    init_db_pg,
    upsert_user_settings_pg,
    get_user_trading_status_pg,
    get_user_pg,
    get_pg_connection, # For clearing tables
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
            self.conn = get_pg_connection()
            self._clear_tables(self.conn)
        except psycopg2.Error as e:
            self.skipTest(f"Skipping PostgreSQL tests: Cannot connect to or initialize PG database: {e}")
        except Exception as e: # Catch any other setup errors
            self.skipTest(f"Skipping PostgreSQL tests due to other setup error: {e}")


    def tearDown(self):
        """Close the connection after each test."""
        if hasattr(self, 'conn') and self.conn:
            # Clear tables again to leave DB clean after tests if desired
            # self._clear_tables(self.conn)
            self.conn.close()

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
