import asyncio
import json
import logging
import websockets
from websockets.exceptions import ConnectionClosed
import time

from poly_trade import place_order, place_arb_orders

logger = logging.getLogger(__name__)

class NoActiveBidsException(Exception):
    pass

class PolyArbMonitor:
    def __init__(self, markets: list[dict], trade: bool = False, stake: int = 1, verbose: bool = False, reset_int_hours: float = None):
        """
        markets: list of dicts with 'condition_id', 'yes_token', 'no_token', 'question'
        """
        self.markets = markets
        self.trade = trade
        self.stake = stake
        self.uri = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        
        # We need a quick way to map asset_ids back to markets and to track their prices
        self.asset_mapping = {}  # token_id -> { 'market_id': '...', 'side': 'yes'/'no' }
        self.market_data = {}    # market_id -> { 'yes_ask': 100, 'no_ask': 100, 'question': '...' }
        self.last_trade = {}     # market_id -> timestamp (float)
        
        self.verbose = verbose
        for m in markets:
            cond_id = m['condition_id']
            yes_token = m['yes_token']
            no_token = m['no_token']
            
            self.asset_mapping[yes_token] = {'market_id': cond_id, 'side': 'yes'}
            self.asset_mapping[no_token] = {'market_id': cond_id, 'side': 'no'}
            
            self.market_data[cond_id] = {
                'yes_ask': 100,
                'no_ask': 100,
                'yes_bid': 0,
                'no_bid': 0,
                'yes_token': yes_token,
                'no_token': no_token,
                'question': m.get('question', cond_id)
            }
            
        if self.verbose and self.asset_mapping:
            sample_key = list(self.asset_mapping.keys())[0]
            print(f"Sample asset_mapping entry token: {sample_key}")
        self.reset_int_hours = reset_int_hours
        self.start_time = time.time()

    async def _log_prices_periodically(self):
        try:
            while True:
                await asyncio.sleep(30)  # Data check loop
                if self.verbose:
                    print("\n--- Current Polymarket Prices (Subscribed) ---")
                    
                active_count = 0
                missing_price_data = []
                
                for cond_id, data in self.market_data.items():
                    yes_ask = data.get("yes_ask", 100)
                    no_ask = data.get("no_ask", 100)
                    
                    if yes_ask < 100 or no_ask < 100:
                        if self.verbose:
                            print(f"[{cond_id[:8]}...] Yes Ask: {yes_ask}c | No Ask: {no_ask}c | Sum: {yes_ask + no_ask}c")
                        active_count += 1
                    else:
                        missing_price_data.append(cond_id)
                        
                if self.verbose:
                    print(f"Showing prices for {active_count} active markets.")
                    print(f"Missing price data for: {len(missing_price_data)}")
                    print("------------------------------------------\n")
                    
                self.successful_period = True
                
                if active_count == 0:
                    print("No active bids received yet across any markets.")
                    raise NoActiveBidsException("No active bids received yet")
                
                # Check for periodic refresh
                if self.reset_int_hours is not None:
                    hours_elapsed = (time.time() - self.start_time) / 3600.0
                    if hours_elapsed >= self.reset_int_hours:
                        print(f"Periodic reset interval reached ({self.reset_int_hours}h). Requesting feed refresh to clear memory...")
                        raise NoActiveBidsException("Periodic reset interval reached")
        except asyncio.CancelledError:
            pass

    async def _ws_loop(self):
        async for websocket in websockets.connect(
            self.uri, 
            ping_interval=10,
            ping_timeout=10
        ):
            try:
                asset_ids = list(self.asset_mapping.keys())
                
                # Chunk subscriptions to avoid limits
                chunk_size = 50
                for i in range(0, len(asset_ids), chunk_size):
                    chunk = asset_ids[i:i + chunk_size]
                    sub_msg = {
                        "assets_ids": chunk,
                        "type": "market"
                    }
                    await websocket.send(json.dumps(sub_msg))
                
                print(f"Subscribed to {len(asset_ids)} assets ({len(self.markets)} markets) on Polymarket WS")

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
        try:
            data_parsed = json.loads(message)
        except Exception:
            # print(f"Failed to parse WS msg: {message}")
            return
            
            # if self.verbose:
            #     print(f"RAW WS MSG: {str(data_parsed)[:200]}")
            
        # Responses can be lists of events
        if isinstance(data_parsed, list):
            events = data_parsed
        else:
            events = [data_parsed]
            
        for data in events:
            event_type = data.get("event_type")
            
            if event_type == "book":
                # Polymarket sends 'book' events with bids and asks
                asset_id = data.get("asset_id")
                if asset_id and asset_id in self.asset_mapping:
                    mapping = self.asset_mapping[asset_id]
                    market_id = mapping['market_id']
                    side = mapping['side']
                    
                    bids = data.get("bids", [])
                    asks = data.get("asks", [])
                    
                    best_bid = float(bids[0]["price"]) if bids else 0.0
                    best_ask = float(asks[0]["price"]) if asks else 1.0
                    
                    # Convert to cents
                    best_bid_c = int(round(best_bid * 100))
                    best_ask_c = int(round(best_ask * 100))
                    
                    if side == 'yes':
                        self.market_data[market_id]['yes_bid'] = best_bid_c
                        self.market_data[market_id]['yes_ask'] = best_ask_c
                    else:
                        self.market_data[market_id]['no_bid'] = best_bid_c
                        self.market_data[market_id]['no_ask'] = best_ask_c
                        
                    self._check_arb(market_id)
                    
            elif event_type == "price_change" or "price_changes" in data:
                for pc in data.get("price_changes", []):
                    asset_id = pc.get("asset_id")
                    if asset_id and asset_id in self.asset_mapping:
                        mapping = self.asset_mapping[asset_id]
                        market_id = mapping['market_id']
                        side = mapping['side']
                        
                        best_bid = float(pc.get("best_bid", 0.0))
                        best_ask = float(pc.get("best_ask", 1.0))
                        
                        # Convert to cents
                        best_bid_c = int(round(best_bid * 100))
                        best_ask_c = int(round(best_ask * 100))
                        
                        if side == 'yes':
                            self.market_data[market_id]['yes_bid'] = best_bid_c
                            self.market_data[market_id]['yes_ask'] = best_ask_c
                        else:
                            self.market_data[market_id]['no_bid'] = best_bid_c
                            self.market_data[market_id]['no_ask'] = best_ask_c
                            
                        self._check_arb(market_id)

    def _check_arb(self, market_id: str):
        if not market_id or market_id not in self.market_data:
            return
        
        data = self.market_data[market_id]
        yes_ask = data.get("yes_ask", 100)
        no_ask = data.get("no_ask", 100)
        yes_bid = data.get("yes_bid", 0)
        no_bid = data.get("no_bid", 0)
        
        sum_ask = yes_ask + no_ask
        
        # Arbitrage condition: it costs less than 100c to buy a YES and a NO contract
        if sum_ask < 100 and yes_ask > 0 and no_ask > 0:
            question = data['question']
            print(f"[{market_id[:8]}...] INEFFICIENCY FOUND: Yes Ask: {yes_ask}c, No Ask: {no_ask}c (Sum: {sum_ask}c)")
            print(f"Question: {question}")
            print(f"Trade: Buy YES at {yes_ask}c and Buy NO at {no_ask}c to lock in {(100 - sum_ask)}c profit per contract.")
            print("-" * 50)
            
            if self.trade:
                now = time.time()
                cooldown_time = 0
                if market_id not in self.last_trade or now - self.last_trade[market_id] > cooldown_time:
                    self.last_trade[market_id] = now
                    print(f"[{market_id[:8]}] 🚀 Executing BATCH DUAL-SIDE LIVE TRADE for {self.stake} contract(s)!")

                    yes_token_id = str(data.get("yes_token", "0"))
                    no_token_id = str(data.get("no_token", "0"))

                    asyncio.create_task(place_arb_orders(
                        yes_token_id=yes_token_id,
                        no_token_id=no_token_id,
                        yes_price_cents=yes_ask,
                        no_price_cents=no_ask,
                        count=self.stake,
                        # order_type="immediate_or_cancel" # trying with FOK
                    ))
                else:
                    print(f"[{market_id[:8]}] ⏳ Cooldown active, skipping trade execution.")
