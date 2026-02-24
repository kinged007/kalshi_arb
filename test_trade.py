import argparse
import asyncio
import json
import logging
from kalshi_auth import get_auth_headers
from kalshi_trade import place_order
import websockets
from websockets.exceptions import ConnectionClosed
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class KalshiTestTradeMonitor:
    def __init__(self, ticker: str):
        self.ticker = ticker
        self.uri = "wss://api.elections.kalshi.com/trade-api/ws/v2"
        self.yes_book = {}
        self.no_book = {}

    async def connect_and_trade(self):
        headers = get_auth_headers("GET", "/trade-api/ws/v2")
        
        async def trade_after_delay():
            print("⏳ Waiting 5 seconds to accumulate orderbook...")
            await asyncio.sleep(5)
            await self.execute_trade()
            # Cancel the websocket task to exit
            try:
                self.ws_task.cancel()
            except:
                pass

        self.trade_task = asyncio.create_task(trade_after_delay())

        async for websocket in websockets.connect(self.uri, additional_headers=headers):
            try:
                sub_msg = {
                    "id": 1,
                    "cmd": "subscribe",
                    "params": {
                        "channels": ["orderbook_delta"],
                        "market_tickers": [self.ticker]
                    }
                }
                await websocket.send(json.dumps(sub_msg))
                print(f"📡 Subscribed to {self.ticker}")

                self.ws_task = asyncio.current_task()
                async for message in websocket:
                    self.handle_message(message)
            except asyncio.CancelledError:
                print("🛑 Disconnecting websocket.")
                break
            except ConnectionClosed:
                print("⚠️ Connection closed, reconnecting...")
                continue
            except Exception as e:
                print(f"❌ WebSocket Error: {e}")
                await asyncio.sleep(1)

    def handle_message(self, message: str):
        data = json.loads(message)
        msg_type = data.get("type")
        
        if msg_type == "orderbook_snapshot":
            msg = data.get("msg", {})
            self._init_book(msg)
        elif msg_type == "orderbook_delta":
            msg = data.get("msg", {})
            self._update_book(msg)

    def _init_book(self, msg: dict):
        self.yes_book.clear()
        self.no_book.clear()
        
        for price, qty in msg.get("yes", []):
            self.yes_book[price] = qty
            
        for price, qty in msg.get("no", []):
            self.no_book[price] = qty

    def _update_book(self, msg: dict):
        side = msg.get("side")
        price = msg.get("price")
        delta = msg.get("delta", 0)
        
        book = self.yes_book if side == "yes" else self.no_book
        
        current_qty = book.get(price, 0)
        new_qty = current_qty + delta
        if new_qty <= 0:
            book.pop(price, None)
        else:
            book[price] = new_qty

    async def execute_trade(self):
        print("\n--- Evaluating best probability for trade ---")
        yes_bid = max(self.yes_book.keys()) if self.yes_book else 0
        no_bid = max(self.no_book.keys()) if self.no_book else 0

        yes_ask = 100 - no_bid if no_bid > 0 else 100
        no_ask = 100 - yes_bid if yes_bid > 0 else 100

        print(f"Yes Ask: {yes_ask}c | No Ask: {no_ask}c")
        
        if yes_ask == 100 and no_ask == 100:
            print("❌ No valid prices found to trade on.")
            return

        # Buy the side that has the highest implied probability (meaning highest price)
        if yes_bid >= no_bid:
            side_to_buy = "yes"
            target_price = min(yes_ask, 99)
            opp_price = 100 - target_price
            print(f"🎯 Selecting YES side with target ask price {target_price}c.")
        else:
            side_to_buy = "no"
            target_price = min(no_ask, 99)
            opp_price = 100 - target_price
            print(f"🎯 Selecting NO side with target ask price {target_price}c.")

        count = 1
        print(f"🚀 Placing {count} contract(s) BUY order on {self.ticker} for side {side_to_buy} at {target_price}c...")
        
        if side_to_buy == "yes":
            await place_order(
                ticker=self.ticker,
                action="buy",
                side="yes",
                count=count,
                yes_price=target_price,
                no_price=opp_price,
                order_type="limit"
            )
        else:
            await place_order(
                ticker=self.ticker,
                action="buy",
                side="no",
                count=count,
                yes_price=opp_price,
                no_price=target_price,
                order_type="limit"
            )

def main():
    parser = argparse.ArgumentParser(description="Test Kalshi Trade")
    parser.add_argument("ticker", type=str, help="Market Ticker to test trading on (e.g., 'KXBTC-24DEC31')")
    args = parser.parse_args()

    monitor = KalshiTestTradeMonitor(args.ticker)
    
    print(f"Starting test trade script for {args.ticker}...")
    try:
        asyncio.run(monitor.connect_and_trade())
    except KeyboardInterrupt:
        print("\nShutting down.")

if __name__ == "__main__":
    main()
