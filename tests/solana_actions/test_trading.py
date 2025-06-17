import unittest
from solana_trade_bot.solana_actions.trading import check_take_profit_levels
# TAKE_PROFIT_LEVELS_PERCENTAGES is defined in core.config and imported in trading.py
# We rely on its presence in trading.py's scope for check_take_profit_levels.
# If we needed to override it for tests, we could mock trading.TAKE_PROFIT_LEVELS_PERCENTAGES

class TestCheckTakeProfitLevels(unittest.TestCase):

    def test_no_tp_hit(self):
        """Test case 1: No TP hit yet (profit 10%)"""
        level, sell_frac, msg = check_take_profit_levels("MOCK1", 1.10, 1.00, None)
        self.assertIsNone(level)
        self.assertIsNone(sell_frac)
        self.assertIsNone(msg)

    def test_first_tp_hit_with_sell_schedule(self):
        """Test case 2: First TP hit (30% profit), 25% level is in schedule."""
        # Assumes 25.0 is in TAKE_PROFIT_LEVELS_PERCENTAGES and TAKE_PROFIT_SELL_SCHEDULE
        # And TAKE_PROFIT_SELL_SCHEDULE[25.0] = 0.30
        level, sell_frac, msg = check_take_profit_levels("MOCK1", 1.30, 1.00, None)
        self.assertEqual(level, 25)
        self.assertEqual(sell_frac, 0.30)
        self.assertIsNotNone(msg)
        self.assertIn("Target Reached: **+25%**", msg)
        self.assertIn("Consider selling **30%**", msg)

    def test_second_tp_hit_with_sell_schedule(self):
        """Test case 3: Second TP hit (55% profit), last was 25%, 50% level is in schedule."""
        # Assumes 50.0 is in TAKE_PROFIT_LEVELS_PERCENTAGES and TAKE_PROFIT_SELL_SCHEDULE
        # And TAKE_PROFIT_SELL_SCHEDULE[50.0] = 0.50
        level, sell_frac, msg = check_take_profit_levels("MOCK1", 1.55, 1.00, 25)
        self.assertEqual(level, 50)
        self.assertEqual(sell_frac, 0.50)
        self.assertIsNotNone(msg)
        self.assertIn("Target Reached: **+50%**", msg)
        self.assertIn("Consider selling **50%**", msg)

    def test_profit_between_tp_levels_no_new_tp(self):
        """Test case 4: Profit between TP levels (profit 40%, last TP was 25%) - no new TP"""
        level, sell_frac, msg = check_take_profit_levels("MOCK1", 1.40, 1.00, 25)
        self.assertIsNone(level)
        self.assertIsNone(sell_frac)
        self.assertIsNone(msg)

    def test_profit_drop_after_notify(self):
        """Test case 5: Profit below last notified TP (e.g. price dropped)"""
        level, sell_frac, msg = check_take_profit_levels("MOCK1", 1.20, 1.00, 25)
        self.assertIsNone(level)
        self.assertIsNone(sell_frac)
        self.assertIsNone(msg)

    def test_max_tp_hit_with_sell_schedule(self):
        """Test case 6: Max TP hit (110% profit), last was 50%, 100% level is in schedule."""
        # Assumes 100.0 is in TAKE_PROFIT_LEVELS_PERCENTAGES and TAKE_PROFIT_SELL_SCHEDULE
        # And TAKE_PROFIT_SELL_SCHEDULE[100.0] = 1.0
        level, sell_frac, msg = check_take_profit_levels("MOCK1", 2.10, 1.00, 50)
        self.assertEqual(level, 100)
        self.assertEqual(sell_frac, 1.0)
        self.assertIsNotNone(msg)
        self.assertIn("Target Reached: **+100%**", msg)
        self.assertIn("Consider selling **100%**", msg)

    def test_max_tp_already_hit_and_notified(self):
        """Test case 7: Max TP already hit and notified"""
        level, sell_frac, msg = check_take_profit_levels("MOCK1", 2.20, 1.00, 100) # Profit 120%
        # Assuming next level is 200 from config [25,50,100,200]
        # Profit 120% is not >= 200%
        self.assertIsNone(level) # No new *defined* level hit
        self.assertIsNone(sell_frac)
        self.assertIsNone(msg)

        level, sell_frac, msg = check_take_profit_levels("MOCK1", 3.50, 1.00, 200) # Profit 250%
        self.assertIsNone(level) # Already notified for max 200, no new level beyond.
        self.assertIsNone(sell_frac)
        self.assertIsNone(msg)

    def test_zero_bought_price(self):
        """Test case 8: Bought price is zero"""
        level, sell_frac, msg = check_take_profit_levels("MOCK1", 1.50, 0, None)
        self.assertIsNone(level)
        self.assertIsNone(sell_frac)
        self.assertIsNone(msg)

    def test_multiple_tp_levels_surpassed_with_sell_schedule(self):
        """Test case 9: Multiple TP levels surpassed (60% profit), 50% is highest in schedule."""
        level, sell_frac, msg = check_take_profit_levels("MOCK1", 1.60, 1.00, None)
        self.assertEqual(level, 50)
        self.assertEqual(sell_frac, 0.50) # Assumes TAKE_PROFIT_SELL_SCHEDULE[50.0] = 0.50
        self.assertIsNotNone(msg)
        self.assertIn("Target Reached: **+50%**", msg)
        self.assertIn("Consider selling **50%**", msg)

    def test_tp_level_hit_not_in_sell_schedule(self):
        """Test case 10: TP level hit (e.g. 200%) that's not in TAKE_PROFIT_SELL_SCHEDULE."""
        # Assuming 200.0 is in TAKE_PROFIT_LEVELS_PERCENTAGES, but not in TAKE_PROFIT_SELL_SCHEDULE
        # For this test, we'd need to mock TAKE_PROFIT_SELL_SCHEDULE or ensure 200.0 is not a key.
        # Current config: TAKE_PROFIT_SELL_SCHEDULE = {25.0: 0.30, 50.0: 0.50, 100.0: 1.0}
        # TAKE_PROFIT_LEVELS_PERCENTAGES = [25.0, 50.0, 100.0, 200.0]

        level, sell_frac, msg = check_take_profit_levels("MOCK1", 3.1, 1.00, 100) # 210% profit, last was 100
        self.assertEqual(level, 200)
        self.assertIsNone(sell_frac, "Sell fraction should be None if level not in schedule")
        self.assertIsNotNone(msg)
        self.assertIn("Target Reached: **+200%**", msg)
        self.assertNotIn("Consider selling", msg) # Message should not suggest selling

if __name__ == '__main__':
    unittest.main()
