import asyncio
import json
import logging
import websockets
from websockets.exceptions import ConnectionClosed
import time

from kalshi_auth import get_auth_headers
from kalshi_trade import place_order

logger = logging.getLogger(__name__)

class NoActiveBidsException(Exception):
    pass

class KalshiArbMonitor:
    def __init__(self, tickers: list[str], trade: bool = False, stake: int = 1, verbose: bool = False, series_mapping: dict = None, requested_series: list = None, reset_int_hours: float = None):
        self.tickers = tickers
        self.trade = trade
        self.stake = stake
        self.uri = "wss://api.elections.kalshi.com/trade-api/ws/v2"
        self.ticker_data = {t: {} for t in tickers}
        self.last_trade = {}
        self.successful_period = False
        self.verbose = verbose
        self.series_mapping = series_mapping or {}
        self.requested_series = requested_series or []
        self.reset_int_hours = reset_int_hours
        self.start_time = time.time()

    async def _log_prices_periodically(self):
        try:
            while True:
                await asyncio.sleep(30)  # Data check loop
                if self.verbose:
                    print("\n--- Current Market Prices (Subscribed) ---")
                    
                active_count = 0
                active_series = set()
                missing_price_data = []
                
                for ticker in self.tickers:
                    data = self.ticker_data.get(ticker, {})
                    yes_bid = data.get("yes_bid", 0)
                    yes_ask = data.get("yes_ask", 100)
                    
                    if yes_bid > 0 or yes_ask < 100:
                        if self.verbose:
                            no_ask = 100 - yes_bid if yes_bid > 0 else 100
                            print(f"[{ticker}] Yes Ask: {yes_ask}c | No Ask: {no_ask}c | Sum: {yes_ask + no_ask}c | Diff: {100 - (yes_ask + no_ask)}c")
                        
                        active_count += 1
                        if ticker in self.series_mapping:
                            active_series.add(self.series_mapping[ticker])
                    else:
                        if self.verbose:
                            # print(f"[{ticker}] Waiting for initial pricing data...")
                            missing_price_data.append(ticker)
                if self.verbose:
                    print(f"Showing prices for {active_count} active markets.")
                    print("Missing price data for:", len(missing_price_data))
                    print("------------------------------------------\n")
                    
                self.successful_period = True
                
                # If any requested series is dead (meaning NO active tickers in that series), trigger refresh
                if self.requested_series:
                    dead_series = [s for s in self.requested_series if s not in active_series]
                    if dead_series:
                        print(f"Data missing for series {dead_series}. Requesting feed refresh...")
                        raise NoActiveBidsException(f"Missing data for {dead_series}")
                else:
                    if active_count == 0:
                        print("No active bids received yet across any markets.")
                        raise NoActiveBidsException("No active bids received yet")
                
                # Check for periodic refresh to clean up memory / update market list
                if self.reset_int_hours is not None:
                    hours_elapsed = (time.time() - self.start_time) / 3600.0
                    if hours_elapsed >= self.reset_int_hours:
                        print(f"Periodic reset interval reached ({self.reset_int_hours}h). Requesting feed refresh to clear memory...")
                        raise NoActiveBidsException("Periodic reset interval reached")
        except asyncio.CancelledError:
            pass

    async def _ws_loop(self):
        headers = get_auth_headers("GET", "/trade-api/ws/v2")
        
        async for websocket in websockets.connect(
            self.uri, 
            additional_headers=headers,
            ping_interval=10,
            ping_timeout=10
        ):
            try:
                # Subscribe to all tickers
                # Kalshi might have limits on tickers per request but 100+ usually fits in one subscribe command
                sub_msg = {
                    "id": 1,
                    "cmd": "subscribe",
                    "params": {
                        "channels": ["ticker"],
                        "market_tickers": self.tickers
                    }
                }
                await websocket.send(json.dumps(sub_msg))
                print(f"Subscribed to {len(self.tickers)} markets using ticker channel")

                async for message in websocket:
                    self.handle_message(message)
            except ConnectionClosed:
                print("Connection closed, reconnecting...")
                continue
            except Exception as e:
                print(f"WebSocket Error: {e}")
                await asyncio.sleep(1)

    async def connect(self):
        ws_task = asyncio.create_task(self._ws_loop())
        logger_task = asyncio.create_task(self._log_prices_periodically())
        
        try:
            done, pending = await asyncio.wait(
                [ws_task, logger_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            for task in pending:
                task.cancel()
                
            for task in done:
                # To prevent raised exceptions from getting lost if they were cancelled
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
        except asyncio.CancelledError:
            ws_task.cancel()
            logger_task.cancel()
            import contextlib
            with contextlib.suppress(asyncio.CancelledError):
                await ws_task
            with contextlib.suppress(asyncio.CancelledError):
                await logger_task
            raise

    def handle_message(self, message: str):
        data = json.loads(message)
        msg_type = data.get("type")
        
        if msg_type == "ticker":
            msg = data.get("msg", {})
            market = msg.get("market_ticker")
            
            if market and market in self.ticker_data:
                yes_bid = msg.get("yes_bid", 0)
                yes_ask = msg.get("yes_ask", 100)
                
                self.ticker_data[market] = {
                    "yes_bid": yes_bid,
                    "yes_ask": yes_ask
                }
                self._check_arb(market)

        elif msg_type == "error":
            error_code = data.get("msg", {}).get("code")
            error_msg = data.get("msg", {}).get("msg")
            print(f"Error {error_code}: {error_msg}")

    def _check_arb(self, ticker: str):
        if not ticker or ticker not in self.ticker_data:
            return
        
        data = self.ticker_data.get(ticker, {})
        yes_bid = data.get("yes_bid", 0)
        yes_ask = data.get("yes_ask", 100)
        # Calculate implicit NO quotes
        no_bid = 100 - yes_ask if yes_ask < 100 else 0
        no_ask = 100 - yes_bid if yes_bid > 0 else 100
        
        sum_ask = yes_ask + no_ask
        
        # print(f"[{ticker}] Yes Ask: {yes_ask}c | No Ask: {no_ask}c | Sum: {sum_ask}c | Diff: {100 - sum_ask}c")
        if sum_ask < 100 and yes_bid > 0 and no_bid > 0:
            print(f"[{ticker}] INEFFICIENCY FOUND: Yes Ask: {yes_ask}c, No Ask: {no_ask}c (Sum: {sum_ask}c)")
            print(f"Trade: Buy YES at {yes_ask}c and Buy NO at {no_ask}c to lock in {(100 - sum_ask)}c profit per contract.")
            print("-" * 50)
            
            if self.trade:
                now = time.time()
                if ticker not in self.last_trade or now - self.last_trade[ticker] > 1: # 1 second cooldown
                    self.last_trade[ticker] = now
                    print(f"[{ticker}] 🚀 Executing DUAL-SIDE LIVE TRADE for {self.stake} contract(s)!")
                    
                    # Execute YES side
                    order_1 = asyncio.create_task(place_order(
                        ticker=ticker,
                        action="buy",
                        side="yes",
                        count=self.stake,
                        yes_price=yes_ask,
                        no_price=0, # unused
                        order_type="immediate_or_cancel"
                    ))
                    
                    # Execute NO side
                    if order_1: # Only execute NO side if YES side was executed
                        order_2 = asyncio.create_task(place_order(
                            ticker=ticker,
                            action="buy",
                            side="no",
                            count=self.stake,
                            yes_price=0, # unused
                            no_price=no_ask,
                            order_type="immediate_or_cancel"
                        ))
                else:
                    print(f"[{ticker}] ⏳ Cooldown active, skipping trade execution.")
