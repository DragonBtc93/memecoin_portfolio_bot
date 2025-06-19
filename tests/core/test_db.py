import unittest
import sqlite3
from unittest.mock import patch, MagicMock # Added MagicMock

# Import functions to be tested from solana_trade_bot.core.sqlite_db
from solana_trade_bot.core.sqlite_db import (
    init_db_sqlite as init_db, # Use _sqlite suffixed functions
    upsert_user_settings_sqlite as upsert_user_settings,
    get_user_trading_status_sqlite as get_user_trading_status,
    get_user_sqlite as get_user,
    get_db_connection_sqlite as get_db_connection
)
# Import DATABASE_FILE to be patched from where it's defined
from solana_trade_bot.core import config as core_config

# Store the original DATABASE_FILE value to reset it later if necessary, though patch should handle this.
ORIGINAL_DATABASE_FILE = core_config.DATABASE_FILE

# Using 'file::memory:?cache=shared' for SQLite in-memory to ensure the same DB is used across connections in the same process.
# However, a more robust way for tests is to manage a single connection per test method or class.
# We will patch get_db_connection_sqlite to return a connection managed by the test class.

class TestUserTradingStatus(unittest.TestCase):

    def setUp(self):
        """Set up an in-memory SQLite database for each test method."""
        # Use a unique in-memory database name for each test method or ensure it's truly isolated.
        # sqlite3.connect(':memory:') creates a new DB each time if the old one was closed.
        # To ensure all operations in a test use the same DB, we create one connection
        # and patch get_db_connection_sqlite to return it.
        self.conn = sqlite3.connect('file::memory:?cache=shared', uri=True) # Persists as long as one connection is open
        self.conn.row_factory = sqlite3.Row

        # Patch get_db_connection_sqlite within the solana_trade_bot.core.sqlite_db module
        self.get_conn_patcher = patch('solana_trade_bot.core.sqlite_db.get_db_connection_sqlite')
        mock_get_db_connection_sqlite = self.get_conn_patcher.start()

        # Create a mock connection object that will be returned by get_db_connection_sqlite
        # This mock_connection will delegate calls to the real self.conn, except for close()
        mock_connection = MagicMock(spec=sqlite3.Connection)
        mock_connection.cursor.side_effect = lambda: self.conn.cursor()
        mock_connection.commit.side_effect = lambda: self.conn.commit()
        mock_connection.rollback.side_effect = lambda: self.conn.rollback()
        # conn.row_factory is set on the real connection, mock doesn't need to handle it here
        # The close method on the mock does nothing, preventing the real connection from closing.
        mock_connection.close = MagicMock()

        mock_get_db_connection_sqlite.return_value = mock_connection

        # Now initialize the schema. init_db() will use the mocked get_db_connection_sqlite,
        # which returns our mock_connection. Operations inside init_db will use mock_connection,
        # which delegates to self.conn but doesn't close it.
        init_db()

    def tearDown(self):
        """Stop the patcher and close the real connection."""
        self.get_conn_patcher.stop()
        if self.conn:
            self.conn.close() # Close the actual connection to the in-memory DB

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
