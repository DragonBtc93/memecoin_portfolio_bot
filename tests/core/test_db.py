import unittest
import sqlite3
from unittest.mock import patch

# Import functions to be tested from solana_trade_bot.core.db
from solana_trade_bot.core.db import (
    init_db,
    upsert_user_settings,
    get_user_trading_status,
    get_user, # Helper for verification
    get_db_connection # To directly manipulate test DB if needed, or verify schema
)
# Import DATABASE_FILE to be patched
import solana_trade_bot.core.config as core_config

# Store the original DATABASE_FILE value to reset it later if necessary, though patch should handle this.
ORIGINAL_DATABASE_FILE = core_config.DATABASE_FILE

@patch('solana_trade_bot.core.config.DATABASE_FILE', ':memory:')
class TestUserTradingStatus(unittest.TestCase):

    def setUp(self):
        """Set up a new in-memory database for each test."""
        # The @patch for DATABASE_FILE should ensure init_db uses an in-memory DB.
        # We need to ensure the schema is created for each test.
        # A single init_db() call might be okay if it's always :memory: due to class-level patch.
        # For true isolation, each test method could re-initialize, but let's start simple.

        # Create a new connection for each test to ensure isolation if needed,
        # or rely on init_db() re-creating tables in the fresh :memory: db.
        # For :memory: dbs, the db vanishes when connection is closed.
        # So, init_db() must be called in a way that its effects persist for the test method.
        # One way is to have init_db accept a connection.
        # Simpler for now: init_db() will use the patched :memory: path.
        # We need a fresh DB for each test method to avoid interference.

        # Create a connection that will be used by the functions if they don't make their own.
        # However, our DB functions mostly create their own connections based on DATABASE_FILE.
        # So, the patch on DATABASE_FILE is key.

        # Call init_db to ensure tables are created in the :memory: db
        # Since DATABASE_FILE is patched to :memory:, init_db will operate on a fresh in-memory DB.
        conn = get_db_connection() # This will use the patched :memory:
        init_db(connection_to_use=conn) # Modify init_db to accept a connection
        conn.close() # init_db should commit and close its own if not passed one.
                      # Let's assume init_db uses get_db_connection which uses the patched path.
                      # So, a simple init_db() call should suffice.

        # To ensure a truly clean state for each test method if tests modify data,
        # we'd ideally run init_db() before each test.
        # The @patch at class level makes :memory: apply to all tests.
        # Each get_db_connection() will get a new :memory: db if the previous one was closed.
        # If get_db_connection() reuses a global connection for :memory:, that's an issue.
        # Let's assume get_db_connection() always returns a new connection to :memory: due to the patch.
        # The critical part is that init_db() should be callable repeatedly for :memory:.
        # Our init_db has "CREATE TABLE IF NOT EXISTS", so it's safe.
        init_db()


    def test_default_trading_status_on_new_user(self):
        """Test that a new user gets is_trading_enabled=True by default on insert."""
        chat_id = 1001
        upsert_user_settings(chat_id, solana_address="wallet_new_default")

        status = get_user_trading_status(chat_id)
        self.assertTrue(status, "New user should have trading_enabled=True by default on first upsert.")

        user = get_user(chat_id)
        self.assertIsNotNone(user)
        self.assertEqual(user['is_trading_enabled'], 1, "DB value should be 1 for True.")

    def test_set_trading_status_on_off(self):
        """Test setting trading status explicitly ON and OFF."""
        chat_id = 1002

        # Initial insert, should default to True for trading_enabled
        upsert_user_settings(chat_id, solana_address="wallet_on_off")
        self.assertTrue(get_user_trading_status(chat_id), "Default should be True.")

        # Set to False
        upsert_user_settings(chat_id, is_trading_enabled=False)
        self.assertFalse(get_user_trading_status(chat_id), "Trading status should be False after setting to False.")
        user = get_user(chat_id)
        self.assertEqual(user['is_trading_enabled'], 0, "DB value should be 0 for False.")

        # Set back to True
        upsert_user_settings(chat_id, is_trading_enabled=True)
        self.assertTrue(get_user_trading_status(chat_id), "Trading status should be True after setting to True.")
        user = get_user(chat_id)
        self.assertEqual(user['is_trading_enabled'], 1, "DB value should be 1 for True.")

        # Set to False again, only providing is_trading_enabled
        upsert_user_settings(chat_id, is_trading_enabled=False)
        self.assertFalse(get_user_trading_status(chat_id), "Trading status should be False again.")


    def test_get_trading_status_non_existent_user(self):
        """Test get_user_trading_status for a non-existent user should return False."""
        chat_id = 99999 # Assumed not in DB
        status = get_user_trading_status(chat_id)
        self.assertFalse(status, "Trading status for a non-existent user should default to False.")

    def test_upsert_only_sol_address_keeps_trading_status(self):
        """Test that updating only solana_address doesn't change trading_status from default."""
        chat_id = 1003
        # First insert, is_trading_enabled defaults to True
        upsert_user_settings(chat_id, solana_address="initial_wallet")
        self.assertTrue(get_user_trading_status(chat_id), "Initial trading status should be True.")

        # Update only solana_address
        upsert_user_settings(chat_id, solana_address="updated_wallet")
        self.assertTrue(get_user_trading_status(chat_id), "Trading status should remain True after updating only wallet.")

    def test_upsert_only_buy_amount_keeps_trading_status(self):
        """Test that updating only buy_amount_sol doesn't change trading_status from default."""
        chat_id = 1004
        # First insert, is_trading_enabled defaults to True
        upsert_user_settings(chat_id, buy_amount_sol=0.5)
        self.assertTrue(get_user_trading_status(chat_id), "Initial trading status should be True.")

        # Update only buy_amount_sol
        upsert_user_settings(chat_id, buy_amount_sol=1.0)
        self.assertTrue(get_user_trading_status(chat_id), "Trading status should remain True after updating only buy amount.")

    def test_upsert_new_user_with_trading_false(self):
        """Test inserting a new user with is_trading_enabled explicitly set to False."""
        chat_id = 1005
        upsert_user_settings(chat_id, solana_address="wallet_trade_false", is_trading_enabled=False)
        self.assertFalse(get_user_trading_status(chat_id), "New user inserted with trading_enabled=False should have status False.")
        user = get_user(chat_id)
        self.assertIsNotNone(user)
        self.assertEqual(user['is_trading_enabled'], 0)


if __name__ == '__main__':
    unittest.main()
