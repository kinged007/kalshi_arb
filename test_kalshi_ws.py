import unittest
from kalshi_ws import KalshiArbMonitor

class TestKalshiArbMonitor(unittest.TestCase):
    def setUp(self):
        self.monitor = KalshiArbMonitor(["TEST-TICKER"])

    def test_yes_no_ask_calculation_no_arb(self):
        # Resting yes bids
        self.monitor.yes_book["TEST-TICKER"] = {10: 100, 20: 50}  # max yes bid = 20
        # Resting no bids
        self.monitor.no_book["TEST-TICKER"] = {30: 200, 40: 10}   # max no bid = 40
        
        # yes_ask = 100 - no_bid = 60
        # no_ask = 100 - yes_bid = 80
        # sum = 140 -> no arb
        
        yes_bid = max(self.monitor.yes_book["TEST-TICKER"].keys())
        no_bid = max(self.monitor.no_book["TEST-TICKER"].keys())
        yes_ask = 100 - no_bid
        no_ask = 100 - yes_bid
        sum_ask = yes_ask + no_ask
        
        self.assertEqual(yes_ask, 60)
        self.assertEqual(no_ask, 80)
        self.assertEqual(sum_ask, 140)

    def test_yes_no_ask_calculation_arb(self):
        # Resting yes bids
        self.monitor.yes_book["TEST-TICKER"] = {40: 100, 55: 50}  # max yes bid = 55
        # Resting no bids
        self.monitor.no_book["TEST-TICKER"] = {30: 200, 50: 10}   # max no bid = 50
        
        # yes_ask = 100 - 50 = 50
        # no_ask = 100 - 55 = 45
        # sum = 95 < 100 -> ARB found!
        
        yes_bid = max(self.monitor.yes_book["TEST-TICKER"].keys())
        no_bid = max(self.monitor.no_book["TEST-TICKER"].keys())
        yes_ask = 100 - no_bid
        no_ask = 100 - yes_bid
        sum_ask = yes_ask + no_ask
        
        self.assertEqual(yes_ask, 50)
        self.assertEqual(no_ask, 45)
        self.assertEqual(sum_ask, 95)
        self.assertTrue(sum_ask < 100)

    def test_update_book(self):
        snapshot = {
            "market_ticker": "TEST-TICKER",
            "yes": [[10, 5], [20, 10]],
            "no": [[30, 15]]
        }
        self.monitor._init_book(snapshot)
        self.assertEqual(self.monitor.yes_book["TEST-TICKER"], {10: 5, 20: 10})
        self.assertEqual(self.monitor.no_book["TEST-TICKER"], {30: 15})
        
        # Update existing
        delta1 = {"market_ticker": "TEST-TICKER", "side": "yes", "price": 20, "delta": 5}
        self.monitor._update_book(delta1)
        self.assertEqual(self.monitor.yes_book["TEST-TICKER"][20], 15)
        
        # Delete level
        delta2 = {"market_ticker": "TEST-TICKER", "side": "no", "price": 30, "delta": -15}
        self.monitor._update_book(delta2)
        self.assertNotIn(30, self.monitor.no_book["TEST-TICKER"])
        
        # Add new level
        delta3 = {"market_ticker": "TEST-TICKER", "side": "no", "price": 40, "delta": 25}
        self.monitor._update_book(delta3)
        self.assertEqual(self.monitor.no_book["TEST-TICKER"][40], 25)

if __name__ == "__main__":
    unittest.main()
