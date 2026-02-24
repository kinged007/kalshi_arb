import asyncio
import json
import websockets
from kalshi_auth import get_auth_headers
from dotenv import load_dotenv

load_dotenv()

async def main():
    uri = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    headers = get_auth_headers("GET", "/trade-api/ws/v2")
    
    async for websocket in websockets.connect(uri, additional_headers=headers):
        sub_msg = {
            "id": 1,
            "cmd": "subscribe",
            "params": {
                "channels": ["ticker"],
                "market_tickers": ["KXBTC15M-26FEB230945-45"] # just an example
            }
        }
        await websocket.send(json.dumps(sub_msg))
        print("Subscribed. Waiting for messages...")
        
        count = 0
        async for message in websocket:
            print(message)
            count += 1
            if count > 5:
                break
        break

if __name__ == "__main__":
    asyncio.run(main())
