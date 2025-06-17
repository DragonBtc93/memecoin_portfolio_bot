import unittest
from solana_trade_bot.solana_actions.trading import check_take_profit_levels
# TAKE_PROFIT_LEVELS_PERCENTAGES is defined in core.config and imported in trading.py
# We rely on its presence in trading.py's scope for check_take_profit_levels.
# If we needed to override it for tests, we could mock trading.TAKE_PROFIT_LEVELS_PERCENTAGES

class TestCheckTakeProfitLevels(unittest.TestCase):

    def test_no_tp_hit(self):
        """Test case 1: No TP hit yet (profit 10%)"""
        level, msg = check_take_profit_levels("MOCK1", 1.10, 1.00, None)
        self.assertIsNone(level, "Level should be None when no TP is hit.")
        self.assertIsNone(msg, "Message should be None when no TP is hit.")

    def test_first_tp_hit(self):
        """Test case 2: First TP hit (profit 30%, TP levels include 25%)"""
        # Assuming 25.0 is in TAKE_PROFIT_LEVELS_PERCENTAGES
        level, msg = check_take_profit_levels("MOCK1", 1.30, 1.00, None)
        self.assertEqual(level, 25, "Should hit the 25% TP level.")
        self.assertIsNotNone(msg, "Should return a message for TP hit.")
        self.assertIn("Target Reached: **+25%**", msg) # Account for Markdown

    def test_second_tp_hit(self):
        """Test case 3: Second TP hit (profit 55%, last TP was 25%)"""
        # Assuming 50.0 is in TAKE_PROFIT_LEVELS_PERCENTAGES
        level, msg = check_take_profit_levels("MOCK1", 1.55, 1.00, 25)
        self.assertEqual(level, 50, "Should hit the 50% TP level.")
        self.assertIsNotNone(msg, "Should return a message for TP hit.")
        self.assertIn("Target Reached: **+50%**", msg) # Account for Markdown

    def test_profit_between_tp_levels_no_new_tp(self):
        """Test case 4: Profit between TP levels (profit 40%, last TP was 25%) - no new TP"""
        level, msg = check_take_profit_levels("MOCK1", 1.40, 1.00, 25)
        self.assertIsNone(level, "Level should be None if profit is between notified TPs.")
        self.assertIsNone(msg, "Message should be None if profit is between notified TPs.")

    def test_profit_drop_after_notify(self):
        """Test case 5: Profit below last notified TP (e.g. price dropped)"""
        level, msg = check_take_profit_levels("MOCK1", 1.20, 1.00, 25)
        self.assertIsNone(level, "Level should be None if profit drops below last notified TP.")
        self.assertIsNone(msg, "Message should be None if profit drops below last notified TP.")

    def test_max_tp_hit(self):
        """Test case 6: Max TP hit (profit 110%, last TP was 50%)"""
        # Assuming 100.0 is in TAKE_PROFIT_LEVELS_PERCENTAGES
        level, msg = check_take_profit_levels("MOCK1", 2.10, 1.00, 50)
        self.assertEqual(level, 100, "Should hit the 100% TP level.") # Assumes 100 is a level
        self.assertIsNotNone(msg, "Should return a message for TP hit.")
        self.assertIn("Target Reached: **+100%**", msg) # Account for Markdown


    def test_max_tp_already_hit_and_notified(self):
        """Test case 7: Max TP already hit and notified"""
        # Profit (e.g. 120%) is higher than last notified (100%), but not enough to hit next TP level (200%)
        level, msg = check_take_profit_levels("MOCK1", 2.20, 1.00, 100) # Profit 120%
        self.assertIsNone(level, "Should be None as 120% does not cross a new defined TP level beyond 100% if next is 200%.")
        self.assertIsNone(msg)

        # Profit (e.g. 250%) is higher than last notified (200% - assuming 200 is max defined TP)
        level, msg = check_take_profit_levels("MOCK1", 3.50, 1.00, 200) # Profit 250%
        self.assertIsNone(level, "Should be None if profit is beyond max defined TP that was already notified.")
        self.assertIsNone(msg)


    def test_zero_bought_price(self):
        """Test case 8: Bought price is zero"""
        level, msg = check_take_profit_levels("MOCK1", 1.50, 0, None)
        self.assertIsNone(level, "Level should be None if bought price is zero.")
        self.assertIsNone(msg, "Message should be None if bought price is zero.")

    def test_multiple_tp_levels_surpassed(self):
        """Test case 9: Multiple TP levels surpassed from no prior TP (e.g. direct to 60% profit)"""
        # Assuming 25.0 and 50.0 are in TAKE_PROFIT_LEVELS_PERCENTAGES
        level, msg = check_take_profit_levels("MOCK1", 1.60, 1.00, None)
        self.assertEqual(level, 50, "Should pick the highest surpassed TP level (50%).")
        self.assertIsNotNone(msg, "Should return a message.")
        self.assertIn("Target Reached: **+50%**", msg) # Account for Markdown

if __name__ == '__main__':
    unittest.main()
